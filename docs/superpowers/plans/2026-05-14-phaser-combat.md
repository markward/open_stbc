# PR 2c — Phaser Combat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Player-side phasers — hold left-click with target locked, every eligible PhaserBank fires a continuous BC-faithful beam dealing distance-falloff damage through `apply_hit`.

**Architecture:** Reuses PR 2a's charge model + alert-driven power and PR 2b's `apply_hit` + shield-impact splash. Adds three things: arc-aware firing gate, continuous damage tick, beam render pass. Multi-bank simultaneous fire (not torpedo's round-robin).

**Tech Stack:** Python (engine), C++/OpenGL (renderer), GLSL shaders, pytest, CMake.

**Spec:** [docs/superpowers/specs/2026-05-14-phaser-combat-design.md](../specs/2026-05-14-phaser-combat-design.md)

---

## File Structure

**Engine (Python):**

- Modify `engine/appc/properties.py` — typed arc/max-damage accessors on `EnergyWeaponProperty`
- Modify `engine/appc/subsystems.py` — `_emitter_in_arc` helper, `PhaserSystem.StartFiring` override, `_EnergyWeaponFireMixin` charge threshold + Stop SFX, mirror arc data in `ShipSubsystem.SetProperty`
- Modify `engine/host_loop.py` — phaser damage tick in `_advance_combat`, beam render data builder, LBUTTON restore
- Modify `engine/renderer.py` — `set_phaser_beams` wrapper

**Renderer (C++/GLSL):**

- Modify `native/src/renderer/include/renderer/frame.h` — `PhaserBeamDescriptor` struct
- Modify `native/src/renderer/include/renderer/pipeline.h` — `phaser_shader()` accessor
- Modify `native/src/renderer/pipeline.cc` — load phaser shader
- Modify `native/src/renderer/CMakeLists.txt` — embed phaser shaders, add `phaser_pass.cc`
- Modify `native/src/host/host_bindings.cc` — `set_phaser_beams` binding + global + submit
- Create `native/src/renderer/include/renderer/phaser_pass.h`
- Create `native/src/renderer/phaser_pass.cc`
- Create `native/src/renderer/shaders/phaser.vert`
- Create `native/src/renderer/shaders/phaser.frag`

**Tests:**

- Create `tests/unit/test_phaser_property_accessors.py`
- Create `tests/unit/test_arc_gate.py`
- Create `tests/unit/test_phaser_multi_bank_fire.py`
- Create `tests/unit/test_phaser_charge_stops_fire.py`
- Create `tests/unit/test_phaser_damage_falloff.py`
- Create `tests/integration/test_phaser_fire_chain_galaxy.py`
- Create `tests/integration/test_phaser_no_fire_at_green_alert.py`
- Create `tests/integration/test_phaser_target_drifts_out_of_arc.py`
- Create `tests/integration/test_phaser_damage_applied_through_apply_hit.py`

---

## Task 1: Typed EnergyWeaponProperty accessors

**Files:**

- Modify: `engine/appc/properties.py` (EnergyWeaponProperty)
- Modify: `engine/appc/subsystems.py` (ShipSubsystem.SetProperty mirror)
- Test: `tests/unit/test_phaser_property_accessors.py`

Hardpoints call `SetArcWidthAngles(low, high)`, `SetArcHeightAngles(low, high)`, `SetMaxDamage(v)`, `SetMaxDamageDistance(v)` on phaser properties. These currently fall through `TGModelProperty.__getattr__` into a data-bag and return None, so the values are silently lost. Add typed setters that store on the property, and mirror them onto the subsystem in `SetProperty` so emitter code can read them directly.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_phaser_property_accessors.py`:

```python
"""EnergyWeaponProperty typed accessors land hardpoint values on the
property AND mirror them onto an attached subsystem."""
from engine.appc.properties import PhaserProperty
from engine.appc.subsystems import PhaserBank


def test_arc_width_round_trips():
    prop = PhaserProperty("test")
    prop.SetArcWidthAngles(-0.5, 1.2)
    assert prop.GetArcWidthAngles() == (-0.5, 1.2)


def test_arc_height_round_trips():
    prop = PhaserProperty("test")
    prop.SetArcHeightAngles(-0.05, 1.05)
    assert prop.GetArcHeightAngles() == (-0.05, 1.05)


def test_max_damage_round_trips():
    prop = PhaserProperty("test")
    prop.SetMaxDamage(250.0)
    assert prop.GetMaxDamage() == 250.0


def test_max_damage_distance_round_trips():
    prop = PhaserProperty("test")
    prop.SetMaxDamageDistance(60.0)
    assert prop.GetMaxDamageDistance() == 60.0


def test_subsystem_mirrors_arc_and_damage_from_property():
    prop = PhaserProperty("test")
    prop.SetArcWidthAngles(-0.9, 0.9)
    prop.SetArcHeightAngles(-0.05, 1.05)
    prop.SetMaxDamage(250.0)
    prop.SetMaxDamageDistance(60.0)

    bank = PhaserBank("test")
    bank.SetProperty(prop)

    assert bank.GetArcWidthAngles()    == (-0.9, 0.9)
    assert bank.GetArcHeightAngles()   == (-0.05, 1.05)
    assert bank.GetMaxDamage()         == 250.0
    assert bank.GetMaxDamageDistance() == 60.0


def test_subsystem_defaults_when_no_property_bound():
    bank = PhaserBank("test")
    # Defaults: full 360° arc, zero damage. Safe nulls.
    assert bank.GetArcWidthAngles()    == (-3.141592653589793, 3.141592653589793)
    assert bank.GetArcHeightAngles()   == (-1.5707963267948966, 1.5707963267948966)
    assert bank.GetMaxDamage()         == 0.0
    assert bank.GetMaxDamageDistance() == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_phaser_property_accessors.py -v`
Expected: ALL FAIL (`AttributeError` or values None).

- [ ] **Step 3: Add typed accessors on EnergyWeaponProperty**

Edit `engine/appc/properties.py`. After the existing fire-sound accessors in `EnergyWeaponProperty.__init__`, extend init and add accessors:

```python
class EnergyWeaponProperty(WeaponProperty):
    """Energy-weapon hardpoint template — phasers, pulse cannons, tractors.
    ...existing docstring...
    """
    def __init__(self, name: str = ""):
        super().__init__(name)
        self._max_charge: float = 0.0
        self._min_firing_charge: float = 0.0
        self._normal_discharge_rate: float = 0.0
        self._recharge_rate: float = 0.0
        self._fire_sound: str = ""
        # Arc bounds — radians.  Hardpoints call SetArcWidthAngles /
        # SetArcHeightAngles to set firing cone limits.  Defaults are
        # full-sphere (no gate); typed setters narrow them.
        import math as _math
        self._arc_width_lo:  float = -_math.pi
        self._arc_width_hi:  float =  _math.pi
        self._arc_height_lo: float = -_math.pi / 2
        self._arc_height_hi: float =  _math.pi / 2
        self._max_damage:           float = 0.0
        self._max_damage_distance:  float = 0.0

    # ... existing GetMaxCharge / SetMaxCharge / etc. stay unchanged ...

    def GetArcWidthAngles(self) -> tuple:
        return (self._arc_width_lo, self._arc_width_hi)

    def SetArcWidthAngles(self, lo, hi) -> None:
        self._arc_width_lo = float(lo)
        self._arc_width_hi = float(hi)

    def GetArcHeightAngles(self) -> tuple:
        return (self._arc_height_lo, self._arc_height_hi)

    def SetArcHeightAngles(self, lo, hi) -> None:
        self._arc_height_lo = float(lo)
        self._arc_height_hi = float(hi)

    def GetMaxDamage(self) -> float:
        return self._max_damage

    def SetMaxDamage(self, v) -> None:
        self._max_damage = float(v)

    def GetMaxDamageDistance(self) -> float:
        return self._max_damage_distance

    def SetMaxDamageDistance(self, v) -> None:
        self._max_damage_distance = float(v)
```

- [ ] **Step 4: Mirror onto ShipSubsystem**

Edit `engine/appc/subsystems.py`. Extend `ShipSubsystem.__init__` (find `self._right = TGPoint3(1.0, 0.0, 0.0)` and add below it):

```python
        # Arc/damage data mirrored from EnergyWeaponProperty.  Defaults
        # leave the gate fully open so non-arc emitters (torpedo tubes)
        # don't get accidentally restricted.
        import math as _math
        self._arc_width_lo:  float = -_math.pi
        self._arc_width_hi:  float =  _math.pi
        self._arc_height_lo: float = -_math.pi / 2
        self._arc_height_hi: float =  _math.pi / 2
        self._max_damage:           float = 0.0
        self._max_damage_distance:  float = 0.0
```

Add typed accessors on `ShipSubsystem` (place after `GetRight`/`SetRight`):

```python
    def GetArcWidthAngles(self) -> tuple:
        return (self._arc_width_lo, self._arc_width_hi)

    def GetArcHeightAngles(self) -> tuple:
        return (self._arc_height_lo, self._arc_height_hi)

    def GetMaxDamage(self) -> float:
        return self._max_damage

    def GetMaxDamageDistance(self) -> float:
        return self._max_damage_distance
```

Extend `ShipSubsystem.SetProperty` (currently mirrors position/direction/right) to also mirror the new fields:

```python
    def SetProperty(self, prop) -> None:
        self._property = prop
        if prop is None:
            return
        if hasattr(prop, "GetPosition"):
            p = prop.GetPosition()
            if isinstance(p, TGPoint3):
                self._position = TGPoint3(p.x, p.y, p.z)
        if hasattr(prop, "GetDirection"):
            d = prop.GetDirection()
            if isinstance(d, TGPoint3):
                self._direction = TGPoint3(d.x, d.y, d.z)
        if hasattr(prop, "GetRight"):
            r = prop.GetRight()
            if isinstance(r, TGPoint3):
                self._right = TGPoint3(r.x, r.y, r.z)
        if hasattr(prop, "GetArcWidthAngles"):
            lo, hi = prop.GetArcWidthAngles()
            self._arc_width_lo, self._arc_width_hi = float(lo), float(hi)
        if hasattr(prop, "GetArcHeightAngles"):
            lo, hi = prop.GetArcHeightAngles()
            self._arc_height_lo, self._arc_height_hi = float(lo), float(hi)
        if hasattr(prop, "GetMaxDamage"):
            self._max_damage = float(prop.GetMaxDamage())
        if hasattr(prop, "GetMaxDamageDistance"):
            self._max_damage_distance = float(prop.GetMaxDamageDistance())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_phaser_property_accessors.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Run full test suite for regression**

Run: `uv run pytest tests/ -q`
Expected: previous count + 6 new passes, no failures.

- [ ] **Step 7: Commit**

```bash
git add engine/appc/properties.py engine/appc/subsystems.py tests/unit/test_phaser_property_accessors.py
git commit -m "$(cat <<'EOF'
feat(props): typed arc + max-damage accessors on EnergyWeaponProperty

Hardpoints call SetArcWidthAngles / SetArcHeightAngles / SetMaxDamage /
SetMaxDamageDistance on phasers; previously these fell through the
TGObject data-bag and silently lost. ShipSubsystem.SetProperty now
mirrors them onto the subsystem so emitter code can read them directly.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Arc-aware firing gate

**Files:**

- Modify: `engine/appc/subsystems.py` (replace `_emitter_faces` with `_emitter_in_arc`)
- Test: `tests/unit/test_arc_gate.py`

`_emitter_faces` currently uses a 90° dot-product cone. For emitters with explicit arc bounds (phasers/tractors), check the target lies within the rectangular yaw×pitch cone defined by `SetArcWidthAngles` / `SetArcHeightAngles`. Emitters without arc bounds (torpedo tubes) keep the 90° fallback.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_arc_gate.py`:

```python
"""Arc-aware firing gate.

Emitter convention: body-space Direction (forward, +Y), Right (+X).
ArcWidthAngles  = (yaw_lo, yaw_hi) — left-right around the Up axis.
ArcHeightAngles = (pitch_lo, pitch_hi) — up-down around the Right axis.

A target at body-space vector v passes when:
    yaw_lo  <= atan2(Right · v, Direction · v) <= yaw_hi    AND
    pitch_lo <= asin((Up · v) / |v|)            <= pitch_hi
"""
import math
from engine.appc.math import TGPoint3
from engine.appc.subsystems import _emitter_in_arc


class _FakeEmitter:
    """Minimal stand-in for a ShipSubsystem-derived emitter."""
    def __init__(self, direction=(0,1,0), right=(1,0,0),
                 arc_width=(-math.pi/4, math.pi/4),
                 arc_height=(-math.pi/8, math.pi/8)):
        self._direction = TGPoint3(*direction)
        self._right     = TGPoint3(*right)
        self._arc_w     = arc_width
        self._arc_h     = arc_height
    def GetDirection(self):       return self._direction
    def GetRight(self):           return self._right
    def GetArcWidthAngles(self):  return self._arc_w
    def GetArcHeightAngles(self): return self._arc_h


def test_target_dead_ahead_passes():
    emitter = _FakeEmitter()
    assert _emitter_in_arc(emitter, ship=None,
                            aim_world=TGPoint3(0.0, 1.0, 0.0)) is True


def test_target_just_inside_width_passes():
    emitter = _FakeEmitter(arc_width=(-math.pi/4, math.pi/4))
    # Yaw ~ +44° → inside.
    aim = TGPoint3(math.sin(math.radians(44)), math.cos(math.radians(44)), 0.0)
    assert _emitter_in_arc(emitter, None, aim) is True


def test_target_just_outside_width_fails():
    emitter = _FakeEmitter(arc_width=(-math.pi/4, math.pi/4))
    # Yaw ~ +46° → outside.
    aim = TGPoint3(math.sin(math.radians(46)), math.cos(math.radians(46)), 0.0)
    assert _emitter_in_arc(emitter, None, aim) is False


def test_target_above_height_fails():
    emitter = _FakeEmitter(arc_height=(-math.pi/8, math.pi/8))
    # Pitch ~ +30° → outside ±22.5°.
    aim = TGPoint3(0.0, math.cos(math.radians(30)), math.sin(math.radians(30)))
    assert _emitter_in_arc(emitter, None, aim) is False


def test_target_below_height_fails():
    emitter = _FakeEmitter(arc_height=(-math.pi/8, math.pi/8))
    aim = TGPoint3(0.0, math.cos(math.radians(30)), -math.sin(math.radians(30)))
    assert _emitter_in_arc(emitter, None, aim) is False


def test_target_behind_fails_even_with_full_arc():
    # ArcWidth = full ±π/2 (180° cone). Target directly behind: yaw=π → outside.
    emitter = _FakeEmitter(arc_width=(-math.pi/2, math.pi/2))
    aim = TGPoint3(0.0, -1.0, 0.0)
    assert _emitter_in_arc(emitter, None, aim) is False


def test_emitter_without_arc_setters_uses_90deg_cone():
    """A bare emitter (no GetArcWidthAngles) — fallback to dot > 0."""
    class _BareEmitter:
        def __init__(self):
            self._direction = TGPoint3(0.0, 1.0, 0.0)
        def GetDirection(self): return self._direction
    bare = _BareEmitter()
    assert _emitter_in_arc(bare, None, TGPoint3(0.0,  1.0, 0.0)) is True
    assert _emitter_in_arc(bare, None, TGPoint3(0.0, -1.0, 0.0)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_arc_gate.py -v`
Expected: 7 FAIL (`_emitter_in_arc` not defined).

- [ ] **Step 3: Implement `_emitter_in_arc`**

Edit `engine/appc/subsystems.py`. Replace the existing `_emitter_faces` helper with:

```python
def _emitter_in_arc(emitter, ship, aim_world):
    """Returns True if `aim_world` (unit vector) lies inside the emitter's
    firing arc, rotated into world space via the ship's rotation.

    Emitters with explicit SetArcWidthAngles / SetArcHeightAngles use a
    yaw × pitch rectangular cone.  Bare emitters (no arc setters — i.e.
    torpedo tubes) fall back to a 90° dot-product check against the
    emitter's SetDirection.
    """
    if not hasattr(emitter, "GetDirection"):
        return True
    try:
        local_dir = emitter.GetDirection()
    except Exception:
        return True
    if not isinstance(local_dir, TGPoint3):
        return True
    # Rotate emitter direction into world space.
    world_dir = TGPoint3(local_dir.x, local_dir.y, local_dir.z)
    if ship is not None and hasattr(ship, "GetWorldRotation"):
        rot = ship.GetWorldRotation()
        if isinstance(rot, TGMatrix3):
            world_dir.MultMatrixLeft(rot)

    # Bare emitter (no arc data): 90° cone.
    if not hasattr(emitter, "GetArcWidthAngles"):
        return (world_dir.x * aim_world.x
              + world_dir.y * aim_world.y
              + world_dir.z * aim_world.z) > 0.0

    # Rotate Right axis into world too.
    right_local = emitter.GetRight() if hasattr(emitter, "GetRight") else TGPoint3(1.0, 0.0, 0.0)
    world_right = TGPoint3(right_local.x, right_local.y, right_local.z)
    if ship is not None and hasattr(ship, "GetWorldRotation"):
        rot = ship.GetWorldRotation()
        if isinstance(rot, TGMatrix3):
            world_right.MultMatrixLeft(rot)
    # Up = Direction × Right (right-handed body frame).
    world_up = TGPoint3(
        world_dir.y * world_right.z - world_dir.z * world_right.y,
        world_dir.z * world_right.x - world_dir.x * world_right.z,
        world_dir.x * world_right.y - world_dir.y * world_right.x,
    )

    # Project aim onto body frame.
    fwd_dot   = world_dir.x   * aim_world.x + world_dir.y   * aim_world.y + world_dir.z   * aim_world.z
    right_dot = world_right.x * aim_world.x + world_right.y * aim_world.y + world_right.z * aim_world.z
    up_dot    = world_up.x    * aim_world.x + world_up.y    * aim_world.y + world_up.z    * aim_world.z

    import math as _math
    yaw   = _math.atan2(right_dot, fwd_dot)
    pitch = _math.asin(max(-1.0, min(1.0, up_dot)))

    yaw_lo, yaw_hi     = emitter.GetArcWidthAngles()
    pitch_lo, pitch_hi = emitter.GetArcHeightAngles()
    return (yaw_lo <= yaw <= yaw_hi) and (pitch_lo <= pitch <= pitch_hi)
```

Also update the `WeaponSystem.StartFiring` call site (currently uses `_emitter_faces`) to call `_emitter_in_arc`:

```python
            if not _emitter_in_arc(emitter, ship, aim_world):
                continue
```

Delete the old `_emitter_faces` function entirely.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_arc_gate.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: all previous tests + 7 new passes, no regressions (existing torpedo tests still pass because torpedo tubes use the 90° fallback path).

- [ ] **Step 6: Commit**

```bash
git add engine/appc/subsystems.py tests/unit/test_arc_gate.py
git commit -m "$(cat <<'EOF'
feat(weapons): arc-aware firing gate honors ArcWidthAngles/HeightAngles

Replaces the 90° dot-product cone (_emitter_faces) with a yaw×pitch
rectangular check (_emitter_in_arc) that consults each emitter's typed
arc bounds. Emitters without arc setters keep the 90° fallback, so
torpedo tubes continue to work unchanged.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: PhaserSystem multi-bank dispatch

**Files:**

- Modify: `engine/appc/subsystems.py` (`PhaserSystem.StartFiring`)
- Test: `tests/unit/test_phaser_multi_bank_fire.py`

Torpedoes round-robin; phasers fire all eligible banks at once. Specialize `PhaserSystem.StartFiring` to iterate every bank and trigger each that passes alert + arc + charge gates.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_phaser_multi_bank_fire.py`:

```python
"""PhaserSystem.StartFiring fires ALL eligible banks simultaneously
(not round-robin like torpedo tubes).
"""
import math
import sys
import importlib
from unittest.mock import patch

import pytest

import App
from engine.appc.ships import ShipClass, ShipClass_Create


@pytest.fixture
def galaxy_red():
    ship = ShipClass_Create("Galaxy")
    App.g_kModelPropertyManager.ClearLocalTemplates()
    mod_name = "ships.Hardpoints.galaxy"
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
    else:
        importlib.import_module(mod_name)
    mod = sys.modules[mod_name]
    mod.LoadPropertySet(ship.GetPropertySet())
    ship.SetupProperties()
    ship.SetAlertLevel(ShipClass.RED_ALERT)
    yield ship
    App.g_kModelPropertyManager.ClearLocalTemplates()
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]


def _make_target_ahead(player):
    """Build a fake target placed 100 units ahead of the player (+Y)."""
    class _Target:
        def __init__(self, pos):
            self._pos = pos
        def GetWorldLocation(self):  return self._pos
        def IsDead(self):            return 0
    from engine.appc.math import TGPoint3
    p = player.GetWorldLocation()
    return _Target(TGPoint3(p.x, p.y + 100.0, p.z))


def test_target_ahead_fires_all_eligible_banks(galaxy_red):
    """Galaxy at RED + target dead ahead → every PhaserBank in arc fires."""
    ship = galaxy_red
    sys_ = ship.GetPhaserSystem()
    assert sys_ is not None and sys_.GetNumWeapons() > 0
    target = _make_target_ahead(ship)
    # Force every bank fully charged so charge-gate doesn't suppress any.
    for i in range(sys_.GetNumWeapons()):
        bank = sys_.GetWeapon(i)
        bank._charge_level = bank._max_charge

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        sys_.StartFiring(target)

    firing = [sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons())]
    # At least 2 banks should engage a target dead-ahead (Galaxy has
    # forward-facing arcs on multiple dorsal+ventral phasers).
    assert sum(firing) >= 2, f"Expected multiple banks firing, got: {firing}"


def test_target_directly_behind_fires_no_forward_banks(galaxy_red):
    """Target behind the ship → forward-facing banks must NOT fire."""
    ship = galaxy_red
    sys_ = ship.GetPhaserSystem()
    # Target 100 units astern (-Y).
    class _Behind:
        def GetWorldLocation(self):
            from engine.appc.math import TGPoint3
            p = ship.GetWorldLocation()
            return TGPoint3(p.x, p.y - 100.0, p.z)
        def IsDead(self): return 0
    for i in range(sys_.GetNumWeapons()):
        bank = sys_.GetWeapon(i)
        bank._charge_level = bank._max_charge

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        sys_.StartFiring(_Behind())

    # Dorsal/Ventral phasers face forward — none should fire.
    # Galaxy has no aft phasers, so the firing count should be 0.
    firing = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing == 0, f"Expected no forward banks firing on aft target, got {firing}"


def test_uncharged_banks_skipped(galaxy_red):
    """A bank with _charge_level < _min_firing_charge must not fire even
    when alert + arc allow it."""
    ship = galaxy_red
    sys_ = ship.GetPhaserSystem()
    target = _make_target_ahead(ship)
    # Drain every bank below its min firing charge.
    for i in range(sys_.GetNumWeapons()):
        bank = sys_.GetWeapon(i)
        bank._charge_level = 0.0

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        sys_.StartFiring(target)

    firing = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing == 0, f"Drained banks must not fire, got {firing} firing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_phaser_multi_bank_fire.py -v`
Expected: tests FAIL — round-robin still in effect, only 1 bank fires.

- [ ] **Step 3: Override PhaserSystem.StartFiring**

Edit `engine/appc/subsystems.py`. In the `PhaserSystem` class (around line 488), add:

```python
    def StartFiring(self, target=None, offset=None) -> None:
        """Multi-bank dispatch — fire every PhaserBank whose alert + arc +
        charge gates all pass.  Differs from torpedo round-robin: phasers
        engage simultaneously."""
        if not self.IsOn() or target is None:
            return
        ship = self.GetParentShip()
        aim_world = _resolve_aim_world(ship, target)
        self._currently_firing = []
        for i in range(self.GetNumWeapons()):
            bank = self.GetWeapon(i)
            if bank is None:
                continue
            if not _emitter_in_arc(bank, ship, aim_world):
                continue
            if hasattr(bank, "CanFire") and bank.CanFire():
                bank.Fire(target, offset)
                self._currently_firing.append(i)
```

`StopFiring` on the base WeaponSystem already iterates `_currently_firing`, so no changes needed there.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_phaser_multi_bank_fire.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add engine/appc/subsystems.py tests/unit/test_phaser_multi_bank_fire.py
git commit -m "$(cat <<'EOF'
feat(weapons): PhaserSystem fires all eligible banks simultaneously

Specialize StartFiring on PhaserSystem to iterate every bank rather
than torpedo's round-robin. Each bank still gates independently on
alert + arc + charge. Targets dead ahead light up multiple banks at
once; targets astern fire nothing on a Galaxy.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Charge threshold tweak

**Files:**

- Modify: `engine/appc/subsystems.py` (`_EnergyWeaponFireMixin.UpdateCharge`)
- Test: `tests/unit/test_phaser_charge_stops_fire.py`

Currently `UpdateCharge` stops firing only when `_charge_level <= 0`. The cleaner BC-faithful gate is "stop when charge dips below the minimum required to fire", matching `CanFire`'s threshold.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_phaser_charge_stops_fire.py`:

```python
"""Continuous fire drains charge; bank auto-stops when it dips below
its MinFiringCharge threshold."""
import sys
import importlib
from unittest.mock import patch

import pytest

import App
from engine.appc.ships import ShipClass, ShipClass_Create


@pytest.fixture
def galaxy_red():
    ship = ShipClass_Create("Galaxy")
    App.g_kModelPropertyManager.ClearLocalTemplates()
    mod_name = "ships.Hardpoints.galaxy"
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
    else:
        importlib.import_module(mod_name)
    mod = sys.modules[mod_name]
    mod.LoadPropertySet(ship.GetPropertySet())
    ship.SetupProperties()
    ship.SetAlertLevel(ShipClass.RED_ALERT)
    yield ship
    App.g_kModelPropertyManager.ClearLocalTemplates()
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]


def test_firing_stops_when_charge_drops_below_min(galaxy_red):
    """Galaxy phaser: MaxCharge=5, Min=3, Discharge=1/s.  Starting at
    charge=3.5, sustained fire for 1s drains to 2.5, which is below
    Min — bank should auto-stop."""
    ship = galaxy_red
    bank = ship.GetPhaserSystem().GetWeapon(0)
    bank._charge_level = 3.5
    bank._firing = True

    bank.UpdateCharge(1.0)  # drains 1.0/s × 1.0s = 1.0 → 2.5

    assert bank._charge_level == pytest.approx(2.5)
    assert bank.IsFiring() == 0, "Bank should auto-stop below MinFiringCharge"


def test_firing_continues_above_min(galaxy_red):
    """Same bank firing for 0.4s drops 0.4 → still above Min=3."""
    ship = galaxy_red
    bank = ship.GetPhaserSystem().GetWeapon(0)
    bank._charge_level = 5.0
    bank._firing = True

    bank.UpdateCharge(0.4)  # 5.0 → 4.6

    assert bank._charge_level == pytest.approx(4.6)
    assert bank.IsFiring() == 1, "Bank above MinFiringCharge keeps firing"


def test_idle_recharges_only_when_alert_powers_system(galaxy_red):
    """Recharge requires parent.IsOn() (alert-driven power)."""
    ship = galaxy_red
    bank = ship.GetPhaserSystem().GetWeapon(0)
    bank._charge_level = 1.0
    bank._firing = False
    bank.UpdateCharge(1.0)  # parent on (RED alert) → +0.08/s
    assert bank._charge_level == pytest.approx(1.08)

    ship.SetAlertLevel(ShipClass.GREEN_ALERT)
    bank._charge_level = 1.0
    bank.UpdateCharge(1.0)  # parent off → no recharge
    assert bank._charge_level == pytest.approx(1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_phaser_charge_stops_fire.py -v`
Expected: `test_firing_stops_when_charge_drops_below_min` FAILS (bank still firing because old threshold `<= 0`).

- [ ] **Step 3: Update UpdateCharge threshold**

Edit `engine/appc/subsystems.py`. In `_EnergyWeaponFireMixin.UpdateCharge`:

```python
    def UpdateCharge(self, dt: float) -> None:
        if self._firing:
            self._charge_level = max(
                0.0, self._charge_level - self._normal_discharge_rate * dt
            )
            if self._charge_level < self._min_firing_charge:
                self._firing = False
        else:
            parent = self.GetParentSubsystem()
            if parent is not None and parent.IsOn():
                self._charge_level = min(
                    self._max_charge,
                    self._charge_level + self._recharge_rate * dt,
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_phaser_charge_stops_fire.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add engine/appc/subsystems.py tests/unit/test_phaser_charge_stops_fire.py
git commit -m "$(cat <<'EOF'
fix(weapons): phaser auto-stops below MinFiringCharge, not at zero

UpdateCharge previously kept the bank firing until charge hit zero,
making CanFire briefly inconsistent with IsFiring after the dip below
MinFiringCharge. Align both gates on the same threshold.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Continuous damage tick + falloff

**Files:**

- Modify: `engine/host_loop.py` (extend `_advance_combat`)
- Test: `tests/unit/test_phaser_damage_falloff.py`
- Test: `tests/integration/test_phaser_damage_applied_through_apply_hit.py`

While a bank is `_firing`, each tick computes `damage = MaxDamage × max(0, 1 − dist/MaxDamageDistance) × dt` and routes it through `apply_hit`. Arc re-check; if target drifted out, the bank auto-stops.

- [ ] **Step 1: Write the failing unit test for the falloff formula**

Create `tests/unit/test_phaser_damage_falloff.py`:

```python
"""Damage falloff: MaxDamage × max(0, 1 − dist/MaxDamageDistance) × dt."""
from engine.host_loop import _phaser_damage_for_tick


def test_dist_zero_full_damage():
    assert _phaser_damage_for_tick(max_damage=250.0,
                                    max_damage_distance=60.0,
                                    dist=0.0,
                                    dt=0.1) == 25.0  # 250 × 1 × 0.1


def test_dist_half_distance_half_damage():
    assert _phaser_damage_for_tick(max_damage=250.0,
                                    max_damage_distance=60.0,
                                    dist=30.0,
                                    dt=0.1) == 12.5


def test_dist_at_max_zero_damage():
    assert _phaser_damage_for_tick(max_damage=250.0,
                                    max_damage_distance=60.0,
                                    dist=60.0,
                                    dt=0.1) == 0.0


def test_dist_beyond_max_zero_damage():
    assert _phaser_damage_for_tick(max_damage=250.0,
                                    max_damage_distance=60.0,
                                    dist=120.0,
                                    dt=0.1) == 0.0


def test_zero_max_damage_distance_returns_zero():
    """Defensive: if MaxDamageDistance is 0 (uninitialized property),
    return 0 rather than dividing by zero."""
    assert _phaser_damage_for_tick(max_damage=250.0,
                                    max_damage_distance=0.0,
                                    dist=10.0,
                                    dt=0.1) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_phaser_damage_falloff.py -v`
Expected: 5 FAIL (`_phaser_damage_for_tick` not defined).

- [ ] **Step 3: Add the falloff helper**

Edit `engine/host_loop.py`. Place near `_advance_combat`:

```python
def _phaser_damage_for_tick(max_damage: float,
                             max_damage_distance: float,
                             dist: float,
                             dt: float) -> float:
    """Phaser damage falloff: linear from MaxDamage at dist=0 to 0 at
    dist=MaxDamageDistance.  Returns 0 if MaxDamageDistance is 0 or
    dist >= MaxDamageDistance."""
    if max_damage_distance <= 0.0 or dist >= max_damage_distance:
        return 0.0
    return max_damage * (1.0 - dist / max_damage_distance) * dt
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_phaser_damage_falloff.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Write the failing integration test**

Create `tests/integration/test_phaser_damage_applied_through_apply_hit.py`:

```python
"""Hold-fire on a target ahead routes damage through apply_hit each tick."""
import sys
import importlib
from unittest.mock import patch, MagicMock

import pytest

import App
from engine.appc.ships import ShipClass, ShipClass_Create
from engine.host_loop import _advance_combat


@pytest.fixture
def galaxy_and_target():
    player = ShipClass_Create("Galaxy")
    App.g_kModelPropertyManager.ClearLocalTemplates()
    mod_name = "ships.Hardpoints.galaxy"
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
    else:
        importlib.import_module(mod_name)
    mod = sys.modules[mod_name]
    mod.LoadPropertySet(player.GetPropertySet())
    player.SetupProperties()
    player.SetAlertLevel(ShipClass.RED_ALERT)

    target = ShipClass_Create("GalaxyTarget")
    mod.LoadPropertySet(target.GetPropertySet())
    target.SetupProperties()
    target.SetAlertLevel(ShipClass.RED_ALERT)
    from engine.appc.math import TGPoint3
    p = player.GetWorldLocation()
    target_pos = TGPoint3(p.x, p.y + 50.0, p.z)
    target.SetWorldLocation(target_pos)
    player.SetTarget(target)

    yield player, target

    App.g_kModelPropertyManager.ClearLocalTemplates()
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]


def test_held_fire_decreases_target_shield(galaxy_and_target):
    player, target = galaxy_and_target
    sys_ = player.GetPhaserSystem()
    for i in range(sys_.GetNumWeapons()):
        bank = sys_.GetWeapon(i)
        bank._charge_level = bank._max_charge

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        sys_.StartFiring(target)

    shields = target.GetShields()
    front_before = shields.GetCurrentShields(0)  # 0 = front face
    _advance_combat([player, target], dt=0.1, host=None, ship_instances=None)
    front_after  = shields.GetCurrentShields(0)
    assert front_after < front_before, (
        f"Held-fire should decrement front shield; before={front_before}, after={front_after}"
    )


def test_target_drifts_out_of_arc_bank_auto_stops(galaxy_and_target):
    player, target = galaxy_and_target
    sys_ = player.GetPhaserSystem()
    for i in range(sys_.GetNumWeapons()):
        bank = sys_.GetWeapon(i)
        bank._charge_level = bank._max_charge

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        sys_.StartFiring(target)
    firing_before = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing_before >= 2

    # Move target directly astern of the player.
    from engine.appc.math import TGPoint3
    p = player.GetWorldLocation()
    target.SetWorldLocation(TGPoint3(p.x, p.y - 50.0, p.z))

    _advance_combat([player, target], dt=0.1, host=None, ship_instances=None)
    firing_after = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing_after == 0, (
        f"Out-of-arc auto-stop; before={firing_before}, after={firing_after}"
    )
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_phaser_damage_applied_through_apply_hit.py -v`
Expected: 2 FAIL — no phaser tick yet.

- [ ] **Step 7: Extend `_advance_combat` with the phaser tick**

Edit `engine/host_loop.py`. Inside `_advance_combat`, after the existing torpedo-hit loop (after `hit_vfx.update_ages(dt)`):

```python
    # Continuous phaser damage tick.  For every ship's PhaserSystem, walk
    # firing banks: re-check arc (auto-stop drifters), compute distance
    # falloff, and route damage through apply_hit (which already triggers
    # the shield-impact splash via host.shield_hit).
    for ship in ships_list:
        sys_ = ship.GetPhaserSystem() if hasattr(ship, "GetPhaserSystem") else None
        if sys_ is None:
            continue
        for i in range(sys_.GetNumWeapons()):
            bank = sys_.GetWeapon(i)
            if bank is None or not bank.IsFiring():
                continue
            target = bank._target
            if target is None or (hasattr(target, "IsDead") and target.IsDead()):
                bank.StopFiring()
                continue
            target_sub = (ship.GetTargetSubsystem()
                          if hasattr(ship, "GetTargetSubsystem") else None)
            target_pos = (target_sub.GetWorldLocation()
                          if target_sub is not None
                          else target.GetWorldLocation())
            emitter_pos = bank._emitter_world_position()
            from engine.appc.subsystems import _emitter_in_arc
            dx = target_pos.x - emitter_pos.x
            dy = target_pos.y - emitter_pos.y
            dz = target_pos.z - emitter_pos.z
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
            if dist > 1e-6:
                aim_unit = type(emitter_pos)(dx / dist, dy / dist, dz / dist)
                if not _emitter_in_arc(bank, ship, aim_unit):
                    bank.StopFiring()
                    continue
            damage = _phaser_damage_for_tick(
                max_damage=bank.GetMaxDamage(),
                max_damage_distance=bank.GetMaxDamageDistance(),
                dist=dist,
                dt=dt,
            )
            if damage > 0:
                apply_hit(target, damage, target_pos,
                          source=ship, subsystem=target_sub)
                if (host is not None
                        and ship_instances is not None
                        and hasattr(host, "shield_hit")):
                    iid = ship_instances.get(target)
                    if iid is not None:
                        host.shield_hit(
                            instance_id=iid,
                            point=(target_pos.x, target_pos.y, target_pos.z),
                            rgba=(0.0, 0.0, 0.0, 0.0),
                            intensity=1.0,
                        )
```

- [ ] **Step 8: Run the integration test**

Run: `uv run pytest tests/integration/test_phaser_damage_applied_through_apply_hit.py -v`
Expected: 2 PASS.

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: no regressions.

- [ ] **Step 10: Commit**

```bash
git add engine/host_loop.py tests/unit/test_phaser_damage_falloff.py tests/integration/test_phaser_damage_applied_through_apply_hit.py
git commit -m "$(cat <<'EOF'
feat(combat): continuous phaser damage tick with distance falloff

Each frame, walk every ship's firing phaser banks, re-check arc (auto-
stop drifters), compute MaxDamage × (1 − dist/MaxDamageDistance) × dt,
and route through apply_hit. Shield-impact splash piggybacks on the
PR-2b host.shield_hit call.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Phaser-beam render descriptor + host binding

**Files:**

- Modify: `native/src/renderer/include/renderer/frame.h`
- Modify: `native/src/host/host_bindings.cc`
- Modify: `engine/renderer.py`
- Modify: `engine/host_loop.py` (add `_build_phaser_beam_render_data`)

Mirror the torpedo pattern: a `PhaserBeamDescriptor` struct, a host-side global `g_phaser_beams`, a `set_phaser_beams` Python binding, and a Python builder that snapshots firing banks each tick.

- [ ] **Step 1: Add the descriptor struct**

Edit `native/src/renderer/include/renderer/frame.h`. After the existing `HitVfxDescriptor`:

```cpp
/// Phaser-beam render descriptor.  One entry per actively firing
/// PhaserBank: a line segment from emitter_world to target_world,
/// drawn as an additive camera-aligned billboard quad.
struct PhaserBeamDescriptor {
    glm::vec3 emitter_world;
    glm::vec3 target_world;
    glm::vec4 color;     // RGBA additive tint
    float     width;     // world-units half-width of the beam quad
};
```

- [ ] **Step 2: Add the host-side global + Python binding**

Edit `native/src/host/host_bindings.cc`. Near the existing `g_torpedoes` global:

```cpp
std::vector<renderer::PhaserBeamDescriptor> g_phaser_beams;
```

Near the existing `m.def("set_torpedoes", ...)` binding, add:

```cpp
    m.def("set_phaser_beams",
          [](const std::vector<py::dict>& descs) {
              g_phaser_beams.clear();
              g_phaser_beams.reserve(descs.size());
              for (const auto& d : descs) {
                  renderer::PhaserBeamDescriptor b;
                  auto e = d["emitter"].cast<std::tuple<float, float, float>>();
                  auto t = d["target"].cast<std::tuple<float, float, float>>();
                  auto c = d["color"].cast<std::tuple<float, float, float, float>>();
                  b.emitter_world = {std::get<0>(e), std::get<1>(e), std::get<2>(e)};
                  b.target_world  = {std::get<0>(t), std::get<1>(t), std::get<2>(t)};
                  b.color         = {std::get<0>(c), std::get<1>(c), std::get<2>(c), std::get<3>(c)};
                  b.width         = d["width"].cast<float>();
                  g_phaser_beams.push_back(std::move(b));
              }
          },
          py::arg("beams"),
          "Set the active phaser-beam list, applied each frame().");
```

(The actual render call into `PhaserPass` is wired in Task 7.)

- [ ] **Step 3: Add the Python wrapper**

Edit `engine/renderer.py`. Near `set_torpedoes`/`set_hit_vfx`:

```python
def set_phaser_beams(beams) -> None:
    """Push active phaser beams to the renderer.  Each entry is a dict:
        {emitter: (x,y,z), target: (x,y,z), color: (r,g,b,a), width: float}
    """
    if _h is None:
        return
    _h.set_phaser_beams(beams)
```

- [ ] **Step 4: Add the Python beam-data builder**

Edit `engine/host_loop.py`. Place near `_build_torpedo_render_data`:

```python
def _build_phaser_beam_render_data(ships):
    """Snapshot active phaser beams for the renderer.

    Walks every ship's PhaserSystem; for each bank IsFiring()=1, yields
    {emitter, target, color, width}. Color is Federation amber (default
    until per-faction beam color is wired); width is a small constant.
    """
    out = []
    for ship in ships:
        sys_ = ship.GetPhaserSystem() if hasattr(ship, "GetPhaserSystem") else None
        if sys_ is None:
            continue
        for i in range(sys_.GetNumWeapons()):
            bank = sys_.GetWeapon(i)
            if bank is None or not bank.IsFiring():
                continue
            target = bank._target
            if target is None:
                continue
            target_sub = (ship.GetTargetSubsystem()
                          if hasattr(ship, "GetTargetSubsystem") else None)
            target_pos = (target_sub.GetWorldLocation()
                          if target_sub is not None
                          else target.GetWorldLocation())
            emitter_pos = bank._emitter_world_position()
            out.append({
                "emitter": (emitter_pos.x, emitter_pos.y, emitter_pos.z),
                "target":  (target_pos.x,  target_pos.y,  target_pos.z),
                # Federation amber, additive.  Per-faction colors are a
                # follow-up — for PR 2c the player is always Galaxy.
                "color":   (1.0, 0.6, 0.2, 1.0),
                "width":   0.05,
            })
    return out
```

Also push this list each tick. Extend `_advance_combat` at the very end:

```python
    if host is not None and hasattr(host, "set_phaser_beams"):
        host.set_phaser_beams(_build_phaser_beam_render_data(ships_list))
```

- [ ] **Step 5: Build + test**

Run: `cmake --build build -j 2>&1 | tail -3 && uv run pytest tests/ -q 2>&1 | tail -3`
Expected: build succeeds; tests pass (renderer not wired yet but Python bindings compile and the new descriptor/struct doesn't break anything).

- [ ] **Step 6: Commit**

```bash
git add native/src/renderer/include/renderer/frame.h native/src/host/host_bindings.cc engine/renderer.py engine/host_loop.py
git commit -m "$(cat <<'EOF'
feat(renderer): PhaserBeamDescriptor + set_phaser_beams Python binding

Scaffolding for the phaser render pass: per-beam descriptor (emitter →
target, color, width), host-side global, Python wrapper, and a beam-
data builder that snapshots firing banks each tick. The render pass
itself lands in the next task.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: PhaserPass renderer + shaders

**Files:**

- Create: `native/src/renderer/include/renderer/phaser_pass.h`
- Create: `native/src/renderer/phaser_pass.cc`
- Create: `native/src/renderer/shaders/phaser.vert`
- Create: `native/src/renderer/shaders/phaser.frag`
- Modify: `native/src/renderer/CMakeLists.txt`
- Modify: `native/src/renderer/include/renderer/pipeline.h`
- Modify: `native/src/renderer/pipeline.cc`
- Modify: `native/src/host/host_bindings.cc`

Render each beam as a camera-aligned quad spanning emitter → target with `width` perpendicular to the beam-axis × camera-to-beam vector.

- [ ] **Step 1: Create the shaders**

Create `native/src/renderer/shaders/phaser.vert`:

```glsl
#version 330 core
// Six vertex IDs per beam: build a quad spanning emitter→target with
// width perpendicular to the beam-axis × view-direction.
layout(location = 0) in vec3 a_emitter;
layout(location = 1) in vec3 a_target;
layout(location = 2) in float a_corner;   // 0..5 → which quad corner

uniform mat4  u_view_proj;
uniform vec3  u_camera_pos;
uniform float u_width;

out vec2 v_uv;

void main() {
    // Quad layout (corner index → uv, side):
    //  0: emitter, side=-1   3: emitter, side=-1
    //  1: target,  side=-1   4: target,  side=+1
    //  2: target,  side=+1   5: emitter, side=+1
    int idx = int(a_corner);
    float t      = (idx == 1 || idx == 2 || idx == 4) ? 1.0 : 0.0;
    float side   = (idx == 2 || idx == 4 || idx == 5) ? 1.0 : -1.0;
    vec3 base    = mix(a_emitter, a_target, t);
    vec3 axis    = normalize(a_target - a_emitter);
    vec3 to_cam  = normalize(u_camera_pos - base);
    vec3 perp    = normalize(cross(axis, to_cam));
    vec3 world   = base + perp * (side * u_width);
    gl_Position  = u_view_proj * vec4(world, 1.0);
    v_uv         = vec2(t, side * 0.5 + 0.5);
}
```

Create `native/src/renderer/shaders/phaser.frag`:

```glsl
#version 330 core
in  vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform vec4      u_color;

void main() {
    // Sample the beam texture along U (length) × V (width).
    vec4 t = texture(u_texture, v_uv);
    // Fade alpha near endpoints (avoid hard caps).
    float endpoint_fade = smoothstep(0.0, 0.05, v_uv.x) *
                          (1.0 - smoothstep(0.95, 1.0, v_uv.x));
    frag_color = t * u_color;
    frag_color.a *= endpoint_fade;
}
```

- [ ] **Step 2: Create the pass header**

Create `native/src/renderer/include/renderer/phaser_pass.h`:

```cpp
// native/src/renderer/include/renderer/phaser_pass.h
#pragma once

#include <renderer/frame.h>
#include <assets/texture.h>

#include <memory>
#include <vector>

namespace scenegraph { struct Camera; }

namespace renderer {

class Pipeline;

class PhaserPass {
public:
    PhaserPass();
    ~PhaserPass();
    PhaserPass(const PhaserPass&)            = delete;
    PhaserPass& operator=(const PhaserPass&) = delete;

    /// Render every active beam as an additive camera-aligned quad.
    void render(const std::vector<PhaserBeamDescriptor>& beams,
                const scenegraph::Camera& camera,
                Pipeline& pipeline);

private:
    // Per-beam VAO/VBO — rebuilt each frame from the descriptor list.
    unsigned int beam_vao_ = 0;
    unsigned int beam_vbo_ = 0;
    std::unique_ptr<assets::Texture> texture_;
    bool texture_loaded_ = false;

    void ensure_mesh(const std::vector<PhaserBeamDescriptor>& beams);
    void ensure_texture();
};

}  // namespace renderer
```

- [ ] **Step 3: Create the pass implementation**

Create `native/src/renderer/phaser_pass.cc`:

```cpp
// native/src/renderer/phaser_pass.cc
#include "renderer/phaser_pass.h"
#include "renderer/pipeline.h"

#include <assets/texture.h>
#include <scenegraph/camera.h>

#include <glad/glad.h>
#include <glm/glm.hpp>

#include <cstdio>
#include <fstream>

namespace renderer {

namespace {
constexpr const char* kBeamTexturePath = "game/data/Textures/Tactical/PhaserLights.tga";
}

PhaserPass::PhaserPass() = default;

PhaserPass::~PhaserPass() {
    if (beam_vbo_) glDeleteBuffers(1, &beam_vbo_);
    if (beam_vao_) glDeleteVertexArrays(1, &beam_vao_);
}

void PhaserPass::ensure_texture() {
    if (texture_loaded_) return;
    texture_loaded_ = true;
    std::ifstream in(kBeamTexturePath, std::ios::binary);
    if (!in) {
        std::fprintf(stderr, "[phaser_pass] failed to open '%s'\n", kBeamTexturePath);
        texture_ = std::make_unique<assets::Texture>();
        return;
    }
    in.seekg(0, std::ios::end);
    auto size = static_cast<std::size_t>(in.tellg());
    in.seekg(0, std::ios::beg);
    std::vector<std::uint8_t> bytes(size);
    in.read(reinterpret_cast<char*>(bytes.data()),
            static_cast<std::streamsize>(size));
    try {
        assets::Image img = assets::decode_tga(bytes);
        assets::Texture tex = assets::upload_image(img, /*generate_mipmaps=*/true);
        texture_ = std::make_unique<assets::Texture>(std::move(tex));
    } catch (const std::exception& e) {
        std::fprintf(stderr, "[phaser_pass] failed to decode '%s': %s\n",
                     kBeamTexturePath, e.what());
        texture_ = std::make_unique<assets::Texture>();
    }
}

void PhaserPass::ensure_mesh(const std::vector<PhaserBeamDescriptor>& beams) {
    if (beam_vao_ == 0) {
        glGenVertexArrays(1, &beam_vao_);
        glGenBuffers(1, &beam_vbo_);
    }
    // Pack per-vertex: emitter.xyz, target.xyz, corner.
    // Six vertices per beam.
    struct Vertex { glm::vec3 emitter; glm::vec3 target; float corner; };
    std::vector<Vertex> verts;
    verts.reserve(beams.size() * 6);
    for (const auto& b : beams) {
        for (int c = 0; c < 6; ++c) {
            verts.push_back({b.emitter_world, b.target_world,
                             static_cast<float>(c)});
        }
    }
    glBindVertexArray(beam_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, beam_vbo_);
    glBufferData(GL_ARRAY_BUFFER,
                 static_cast<GLsizeiptr>(verts.size() * sizeof(Vertex)),
                 verts.data(), GL_DYNAMIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                          reinterpret_cast<void*>(offsetof(Vertex, emitter)));
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                          reinterpret_cast<void*>(offsetof(Vertex, target)));
    glEnableVertexAttribArray(2);
    glVertexAttribPointer(2, 1, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                          reinterpret_cast<void*>(offsetof(Vertex, corner)));
    glBindVertexArray(0);
}

void PhaserPass::render(const std::vector<PhaserBeamDescriptor>& beams,
                         const scenegraph::Camera& camera,
                         Pipeline& pipeline) {
    if (beams.empty()) return;
    ensure_texture();
    if (!texture_ || texture_->id() == 0) return;
    ensure_mesh(beams);

    auto& shader = pipeline.phaser_shader();
    shader.use();
    const glm::mat4 vp = camera.proj_matrix() * camera.view_matrix();
    shader.set_mat4("u_view_proj", vp);
    shader.set_vec3("u_camera_pos", camera.position());
    shader.set_int ("u_texture",   0);

    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE);
    glEnable(GL_DEPTH_TEST);
    glDepthMask(GL_FALSE);
    glDisable(GL_CULL_FACE);

    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, texture_->id());

    glBindVertexArray(beam_vao_);
    // Each beam has its own color + width; issue one draw call per beam.
    for (std::size_t i = 0; i < beams.size(); ++i) {
        shader.set_vec4 ("u_color", beams[i].color);
        shader.set_float("u_width", beams[i].width);
        glDrawArrays(GL_TRIANGLES, static_cast<GLint>(i * 6), 6);
    }
    glBindVertexArray(0);

    glEnable(GL_CULL_FACE);
    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);
}

}  // namespace renderer
```

- [ ] **Step 4: Wire shaders + pass into the pipeline**

Edit `native/src/renderer/CMakeLists.txt`. Add the phaser pass source + shader embeds. Find the existing shader embed block (look for `embed_shader(SHADER_TORPEDO_VS shaders/torpedo.vert torpedo_vs)`) and add immediately after:

```cmake
embed_shader(SHADER_PHASER_VS shaders/phaser.vert phaser_vs)
embed_shader(SHADER_PHASER_FS shaders/phaser.frag phaser_fs)
```

Find the source list (where `torpedo_pass.cc` lives) and add:

```cmake
    phaser_pass.cc
```

Edit `native/src/renderer/include/renderer/pipeline.h`. Add a `phaser_shader()` accessor next to the `torpedo_shader()` one:

```cpp
    ShaderProgram& phaser_shader() { return phaser_shader_; }
```

And in the private members, next to `ShaderProgram torpedo_shader_;`:

```cpp
    ShaderProgram phaser_shader_;
```

Edit `native/src/renderer/pipeline.cc`. Add includes near the torpedo includes:

```cpp
#include "embedded_phaser_vs.h"
#include "embedded_phaser_fs.h"
```

And in the constructor, after the torpedo shader is loaded:

```cpp
    phaser_shader_.load_from_source(
        reinterpret_cast<const char*>(phaser_vs),
        reinterpret_cast<const char*>(phaser_fs));
```

Edit `native/src/host/host_bindings.cc`. Near `g_torpedo_pass`:

```cpp
std::unique_ptr<renderer::PhaserPass> g_phaser_pass;
```

Include the header at top:

```cpp
#include <renderer/phaser_pass.h>
```

In the initialization block (find where `g_torpedo_pass = std::make_unique<...>();`), add:

```cpp
    g_phaser_pass = std::make_unique<renderer::PhaserPass>();
```

In the reset block (where `g_torpedo_pass.reset();`):

```cpp
    g_phaser_pass.reset();
```

In the frame submit block (after `g_torpedo_pass->render(g_torpedoes, g_camera, *g_pipeline);`):

```cpp
    if (g_phaser_pass) g_phaser_pass->render(g_phaser_beams, g_camera, *g_pipeline);
```

- [ ] **Step 5: Build**

Run: `cmake -B build -S . 2>&1 | tail -2 && cmake --build build -j 2>&1 | tail -3`
Expected: clean build.

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: no regressions (Python tests don't exercise the C++ pass).

- [ ] **Step 7: Commit**

```bash
git add native/src/renderer/include/renderer/phaser_pass.h native/src/renderer/phaser_pass.cc native/src/renderer/shaders/phaser.vert native/src/renderer/shaders/phaser.frag native/src/renderer/CMakeLists.txt native/src/renderer/include/renderer/pipeline.h native/src/renderer/pipeline.cc native/src/host/host_bindings.cc
git commit -m "$(cat <<'EOF'
feat(renderer): PhaserPass — camera-aligned beam billboards

One additive quad per active beam, stretched from emitter to target
with width perpendicular to the beam-axis × view-direction. Uses
PhaserLights.tga; tinted per-bank via u_color. Endpoint alpha fades
to avoid hard caps. Wired into pipeline.cc + host bindings the same
way torpedo_pass + hit_vfx_pass are.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Stop-fire sound discipline

**Files:**

- Modify: `engine/appc/subsystems.py` (`_EnergyWeaponFireMixin.StopFiring`)

`Fire` plays `<name> Start` (existing). `StopFiring` currently sets `_firing=False` without sound. Add a best-effort `<name> Stop` trigger; if the sound doesn't exist, no-op.

- [ ] **Step 1: Write the failing test (extend existing test file)**

Add to `tests/unit/test_phaser_charge_stops_fire.py`:

```python
def test_stop_firing_triggers_stop_sound(galaxy_red):
    """StopFiring() should attempt to play '<FireSound> Stop'."""
    ship = galaxy_red
    bank = ship.GetPhaserSystem().GetWeapon(0)
    bank._charge_level = bank._max_charge
    with patch("engine.audio.tg_sound.TGSoundManager.instance") as inst:
        mgr = inst.return_value
        bank.Fire()
        bank.StopFiring()
        # Look for any PlaySound call ending with " Stop".
        called_names = [c.args[0] for c in mgr.PlaySound.call_args_list]
        assert any(name.endswith(" Stop") for name in called_names), (
            f"Expected a '... Stop' sound, got: {called_names}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_phaser_charge_stops_fire.py::test_stop_firing_triggers_stop_sound -v`
Expected: FAIL (no Stop call yet).

- [ ] **Step 3: Add the Stop sound**

Edit `engine/appc/subsystems.py`. In `_EnergyWeaponFireMixin.StopFiring`:

```python
    def StopFiring(self) -> None:
        was_firing = self._firing
        self._firing = False
        if was_firing:
            name = _resolve_fire_sound(self.GetProperty())
            if name:
                from engine.audio.tg_sound import TGSoundManager
                TGSoundManager.instance().PlaySound(name + " Stop")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_phaser_charge_stops_fire.py -v`
Expected: 4 PASS (3 existing + 1 new).

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add engine/appc/subsystems.py tests/unit/test_phaser_charge_stops_fire.py
git commit -m "$(cat <<'EOF'
feat(weapons): phaser StopFiring plays '<name> Stop' sound

Best-effort — if the Stop sound asset doesn't exist, TGSoundManager
silently no-ops. Brackets the Start sound triggered on Fire().

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Restore left-click forwarding

**Files:**

- Modify: `engine/host_loop.py` (`_poll_mouse_buttons`)
- Test: `tests/integration/test_phaser_fire_chain_galaxy.py`
- Test: `tests/integration/test_phaser_no_fire_at_green_alert.py`

PR 2b dropped left-click forwarding because clicking with no phaser visual was noise. Restore it now that beams render.

- [ ] **Step 1: Write the integration tests**

Create `tests/integration/test_phaser_fire_chain_galaxy.py`:

```python
"""LBUTTON-down on a target ahead drives the input chain through
TacticalInterfaceHandlers → PhaserSystem.StartFiring."""
import sys
import importlib
from unittest.mock import patch

import pytest

import App
from engine.appc.ships import ShipClass, ShipClass_Create


def _setup_input_chain(ship):
    App.Game_GetCurrentPlayer = lambda: ship
    App.g_kInputManager.RegisterUnicodeKey(App.WC_LBUTTON, App.KY_LBUTTON, None, "LButton")
    App.g_kInputManager.RegisterUnicodeKey(App.WC_RBUTTON, App.KY_RBUTTON, None, "RButton")
    tcw = App.TacticalControlWindow_GetTacticalControlWindow()
    tcw.RemoveAllInstanceHandlers()
    App.g_kKeyboardBinding.SetDefaultDestination(tcw)
    import DefaultKeyboardBinding
    DefaultKeyboardBinding.Initialize()
    import TacticalInterfaceHandlers
    TacticalInterfaceHandlers.Initialize(tcw)


@pytest.fixture
def galaxy_with_target():
    player = ShipClass_Create("Galaxy")
    App.g_kModelPropertyManager.ClearLocalTemplates()
    mod_name = "ships.Hardpoints.galaxy"
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
    else:
        importlib.import_module(mod_name)
    mod = sys.modules[mod_name]
    mod.LoadPropertySet(player.GetPropertySet())
    player.SetupProperties()
    player.SetAlertLevel(ShipClass.RED_ALERT)

    target = ShipClass_Create("Tgt")
    mod.LoadPropertySet(target.GetPropertySet())
    target.SetupProperties()
    from engine.appc.math import TGPoint3
    p = player.GetWorldLocation()
    target.SetWorldLocation(TGPoint3(p.x, p.y + 50.0, p.z))
    player.SetTarget(target)

    _setup_input_chain(player)

    for i in range(player.GetPhaserSystem().GetNumWeapons()):
        bank = player.GetPhaserSystem().GetWeapon(i)
        bank._charge_level = bank._max_charge

    yield player

    App.g_kModelPropertyManager.ClearLocalTemplates()
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]
    tcw = App.TacticalControlWindow_GetTacticalControlWindow()
    tcw.RemoveAllInstanceHandlers()
    from engine.core.game import Game_GetCurrentPlayer as _real_gcp
    App.Game_GetCurrentPlayer = _real_gcp


def test_lbutton_down_starts_firing(galaxy_with_target):
    player = galaxy_with_target
    sys_ = player.GetPhaserSystem()
    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        App.g_kInputManager.OnKeyDown(App.WC_LBUTTON)
    firing = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing >= 2, f"LBUTTON-down should fire multiple banks, got {firing}"


def test_lbutton_up_stops_firing(galaxy_with_target):
    player = galaxy_with_target
    sys_ = player.GetPhaserSystem()
    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        App.g_kInputManager.OnKeyDown(App.WC_LBUTTON)
        App.g_kInputManager.OnKeyUp(App.WC_LBUTTON)
    firing = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing == 0, f"LBUTTON-up should stop all firing, got {firing}"
```

Create `tests/integration/test_phaser_no_fire_at_green_alert.py`:

```python
"""GREEN alert + LBUTTON-down → no bank goes _firing."""
import sys
import importlib
from unittest.mock import patch

import pytest

import App
from engine.appc.ships import ShipClass, ShipClass_Create


def _setup_input_chain(ship):
    App.Game_GetCurrentPlayer = lambda: ship
    App.g_kInputManager.RegisterUnicodeKey(App.WC_LBUTTON, App.KY_LBUTTON, None, "LButton")
    App.g_kInputManager.RegisterUnicodeKey(App.WC_RBUTTON, App.KY_RBUTTON, None, "RButton")
    tcw = App.TacticalControlWindow_GetTacticalControlWindow()
    tcw.RemoveAllInstanceHandlers()
    App.g_kKeyboardBinding.SetDefaultDestination(tcw)
    import DefaultKeyboardBinding
    DefaultKeyboardBinding.Initialize()
    import TacticalInterfaceHandlers
    TacticalInterfaceHandlers.Initialize(tcw)


@pytest.fixture
def galaxy_green():
    ship = ShipClass_Create("Galaxy")
    App.g_kModelPropertyManager.ClearLocalTemplates()
    mod_name = "ships.Hardpoints.galaxy"
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
    else:
        importlib.import_module(mod_name)
    mod = sys.modules[mod_name]
    mod.LoadPropertySet(ship.GetPropertySet())
    ship.SetupProperties()
    ship.SetAlertLevel(ShipClass.GREEN_ALERT)
    _setup_input_chain(ship)
    yield ship
    App.g_kModelPropertyManager.ClearLocalTemplates()
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]
    tcw = App.TacticalControlWindow_GetTacticalControlWindow()
    tcw.RemoveAllInstanceHandlers()
    from engine.core.game import Game_GetCurrentPlayer as _real_gcp
    App.Game_GetCurrentPlayer = _real_gcp


def test_lbutton_at_green_alert_silent(galaxy_green):
    ship = galaxy_green
    sys_ = ship.GetPhaserSystem()
    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        App.g_kInputManager.OnKeyDown(App.WC_LBUTTON)
    firing = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing == 0, f"GREEN alert must suppress fire; got {firing} banks firing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_phaser_fire_chain_galaxy.py tests/integration/test_phaser_no_fire_at_green_alert.py -v`
Expected: tests FAIL — LBUTTON not forwarded (the `_poll_mouse_buttons` change isn't reached in unit tests, but `OnKeyDown(WC_LBUTTON)` is also gated upstream because LBUTTON might not be registered in the input chain after PR 2b stripped its forwarding).

(Sanity check: the test calls `OnKeyDown` directly on the input manager, bypassing GLFW polling, so the test isolates the input chain from the mouse-polling layer. The tests will succeed if PhaserSystem.StartFiring is wired in the existing `TacticalInterfaceHandlers.FireWeapons` — which it should already be from PR 2a. If they pass without code changes, even better; the code change is for the actual `_poll_mouse_buttons` mouse-button bridge in the live binary.)

- [ ] **Step 3: Restore LBUTTON in `_poll_mouse_buttons`**

Edit `engine/host_loop.py`. Replace the right-click-only block:

```python
    if host is None or not hasattr(host, "mouse_button_pressed"):
        return
    import App
    # PR 2c re-enables left-click (phasers) alongside right-click
    # (torpedoes).  Middle-click is still out of scope (tractor → PR 2d+).
    for glfw_btn, wc in (
        (host.keys.MOUSE_BUTTON_LEFT,  App.WC_LBUTTON),
        (host.keys.MOUSE_BUTTON_RIGHT, App.WC_RBUTTON),
    ):
        if host.mouse_button_pressed(glfw_btn):
            App.g_kInputManager.OnKeyDown(wc)
        if host.mouse_button_released(glfw_btn):
            App.g_kInputManager.OnKeyUp(wc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_phaser_fire_chain_galaxy.py tests/integration/test_phaser_no_fire_at_green_alert.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add engine/host_loop.py tests/integration/test_phaser_fire_chain_galaxy.py tests/integration/test_phaser_no_fire_at_green_alert.py
git commit -m "$(cat <<'EOF'
feat(input): restore left-click forwarding for phasers

PR 2b dropped LBUTTON because clicking with no phaser visual was noise.
PR 2c re-enables it now that the beam pass renders. Middle-click stays
deferred to a future tractor PR.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Out-of-arc drift integration test + visual smoke verify

**Files:**

- Create: `tests/integration/test_phaser_target_drifts_out_of_arc.py`
- (Visual: built binary)

Final integration coverage + a manual smoke pass in the live build.

- [ ] **Step 1: Write the out-of-arc drift integration test**

Create `tests/integration/test_phaser_target_drifts_out_of_arc.py`:

```python
"""Sustained fire → target moves out of arc mid-fire → bank auto-stops
on the next tick while other banks (if any are still in arc) continue."""
import sys
import importlib
from unittest.mock import patch

import pytest

import App
from engine.appc.ships import ShipClass, ShipClass_Create
from engine.host_loop import _advance_combat


@pytest.fixture
def galaxy_and_target():
    player = ShipClass_Create("Galaxy")
    App.g_kModelPropertyManager.ClearLocalTemplates()
    mod_name = "ships.Hardpoints.galaxy"
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
    else:
        importlib.import_module(mod_name)
    mod = sys.modules[mod_name]
    mod.LoadPropertySet(player.GetPropertySet())
    player.SetupProperties()
    player.SetAlertLevel(ShipClass.RED_ALERT)
    target = ShipClass_Create("Tgt")
    mod.LoadPropertySet(target.GetPropertySet())
    target.SetupProperties()
    from engine.appc.math import TGPoint3
    p = player.GetWorldLocation()
    target.SetWorldLocation(TGPoint3(p.x, p.y + 50.0, p.z))
    player.SetTarget(target)
    for i in range(player.GetPhaserSystem().GetNumWeapons()):
        bank = player.GetPhaserSystem().GetWeapon(i)
        bank._charge_level = bank._max_charge
    yield player, target
    App.g_kModelPropertyManager.ClearLocalTemplates()
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]


def test_drift_astern_auto_stops_all_forward_banks(galaxy_and_target):
    player, target = galaxy_and_target
    sys_ = player.GetPhaserSystem()
    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        sys_.StartFiring(target)
    firing_before = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing_before >= 2

    # Yank the target to directly astern.
    from engine.appc.math import TGPoint3
    p = player.GetWorldLocation()
    target.SetWorldLocation(TGPoint3(p.x, p.y - 50.0, p.z))

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        _advance_combat([player, target], dt=0.1, host=None, ship_instances=None)
    firing_after = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing_after == 0, (
        f"All forward banks should auto-stop on aft drift; "
        f"before={firing_before}, after={firing_after}"
    )
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/integration/test_phaser_target_drifts_out_of_arc.py -v`
Expected: PASS (Task 5 already implemented the auto-stop logic).

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 4: Visual smoke test in the live build**

Run:

```bash
cmake --build build -j 2>&1 | tail -3
./build/dauntless
```

Manual checks:

1. Load a mission with a Galaxy target ahead.
2. Set RED alert. Tab-target the enemy.
3. Hold LBUTTON. Expected:
   - Multiple amber beams trace from saucer + engineering hardpoints to the target.
   - Shield bubble splashes appear at the impact each frame.
   - "Galaxy Phaser Start" plays once on press.
4. Release LBUTTON. Expected:
   - All beams disappear.
   - "Galaxy Phaser Stop" plays once.
5. Hold sustained for ~3 seconds. Expected:
   - Banks drop out as their charge dips below 3.0 (MinFiringCharge).
6. Release; wait several seconds. Hold again. Expected:
   - Banks gradually re-charge and re-engage.
7. Yaw the player to face away from the target. Expected:
   - Beams stop (banks auto-stop on out-of-arc).

If anything looks broken, debug via the existing diagnostic infrastructure (re-add a temporary print).

- [ ] **Step 5: Commit the final test**

```bash
git add tests/integration/test_phaser_target_drifts_out_of_arc.py
git commit -m "$(cat <<'EOF'
test(combat): out-of-arc drift auto-stops firing banks

End-to-end coverage for the arc re-check in _advance_combat's phaser
tick: a target yanked astern mid-fire causes every previously-firing
forward bank to auto-stop on the next tick.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Spec Coverage Check

- **Goal**: ✓ Tasks 1–10 implement the player-side phaser pipeline end-to-end.
- **Architecture / Data flow**: ✓ StartFiring (Task 3) → damage tick (Task 5) → beam render (Tasks 6+7).
- **Component 1 — Arc gate**: Task 2.
- **Component 2 — Multi-bank fire**: Task 3.
- **Component 3 — Continuous damage tick**: Task 5.
- **Component 4 — Charge tweak**: Task 4.
- **Component 5 — Phaser render pass**: Task 7.
- **Component 6 — Host binding + Python wiring**: Task 6.
- **Component 7 — Sound discipline**: Task 8 (Start already in mixin; Stop added).
- **Component 8 — Input wiring**: Task 9.
- **Component 9 — Charging + alert gating (inherited)**: Documented in Task 4 (threshold tweak) and Task 3 (alert check on parent.IsOn()). Inherited gates exercised in Task 9's GREEN-alert test.
- **Testing — unit**: Tasks 1, 2, 3, 4, 5 (falloff).
- **Testing — integration**: Tasks 5 (damage routing), 9 (fire chain + GREEN alert), 10 (drift).
- **Visual smoke**: Task 10 Step 4.
- **Out-of-scope items**: Explicitly deferred in spec, no tasks.
