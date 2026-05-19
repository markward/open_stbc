# Torpedo Combat (PR 2b of 2c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Closes the visible + damaging loop for torpedoes — right-click with a locked target launches a sprite-composite torpedo that homes for `guidance_lifetime`, impacts the target, applies damage routed shields-face → nearest-subsystem → hull, and broadcasts `ET_WEAPON_HIT` for mission-script handlers. Without lock, it dumbfires straight from the emitter direction.

**Architecture:** SDK projectile scripts (`sdk/Build/scripts/Tactical/Projectiles/PhotonTorpedo.py` and 16 others) are the source of truth for visuals (`CreateTorpedoModel` arg block) and behaviour (`GetLaunchSpeed/Sound/Damage/GuidanceLifetime/MaxAngularAccel`). Engine `Torpedo` runtime class is a data carrier; the script's `Create(t)` populates it. Per-frame `host_loop._advance_combat` advances motion, runs collision, routes damage, and pushes per-frame torpedo + hit-VFX lists to the native renderer. Two new C++ passes (`torpedo_pass` for additive sprite composite, `hit_vfx_pass` for transient impact flares) consume those lists.

**Tech Stack:** Python (engine shim), pytest, C++ (GLFW/OpenGL renderer passes + GLSL shaders).

**Spec:** [docs/superpowers/specs/2026-05-14-torpedo-combat-design.md](../specs/2026-05-14-torpedo-combat-design.md)

---

## File map

- Modify: [engine/appc/properties.py](engine/appc/properties.py) — `WeaponSystemProperty.SetTorpedoScript/GetTorpedoScript` typed.
- Create: `engine/appc/projectiles.py` — `Torpedo` class + `_active` registry + `update_all(dt, ships)`.
- Modify: [engine/appc/events.py](engine/appc/events.py) — `WeaponHitEvent` + `ET_WEAPON_HIT` constant.
- Modify: [engine/appc/objects.py](engine/appc/objects.py) — `DamageableObject.DamageSystem(subsystem, amount)`.
- Create: `engine/appc/combat.py` — `sphere_hit`, `pick_target_subsystem`, `apply_hit`, `shield_face_from_hit_point`.
- Modify: [engine/appc/subsystems.py](engine/appc/subsystems.py) — `TorpedoTube.Fire` spawns the projectile.
- Create: `engine/appc/hit_vfx.py` — `spawn`, `update_ages(dt)`, `snapshot()`, internal age-pruning.
- Modify: [engine/host_loop.py](engine/host_loop.py) — `_advance_combat(ships, dt)`, native renderer pushes, `FriendlyFireHandler` registration.
- Create: `native/src/renderer/torpedo_pass.cc` + `native/src/renderer/include/renderer/torpedo_pass.h`.
- Create: `native/src/renderer/hit_vfx_pass.cc` + `native/src/renderer/include/renderer/hit_vfx_pass.h`.
- Create: `native/src/renderer/shaders/torpedo.{vert,frag}`, `hit_vfx.{vert,frag}`.
- Modify: [native/src/renderer/pipeline.cc](native/src/renderer/pipeline.cc) — schedule new passes.
- Modify: [native/src/host/host_bindings.cc](native/src/host/host_bindings.cc) — `set_torpedoes` + `set_hit_vfx` bindings.
- Create unit tests:
  - `tests/unit/test_weapon_system_property_torpedo_script.py`
  - `tests/unit/test_torpedo_create_model.py`
  - `tests/unit/test_torpedo_advance.py`
  - `tests/unit/test_weapon_hit_event.py`
  - `tests/unit/test_damage_system_method.py`
  - `tests/unit/test_sphere_hit.py`
  - `tests/unit/test_pick_target_subsystem.py`
  - `tests/unit/test_apply_hit_routing.py`
  - `tests/unit/test_hit_vfx_lifecycle.py`
- Create integration tests:
  - `tests/integration/test_torpedo_lock_homes_to_target.py`
  - `tests/integration/test_torpedo_no_lock_dumbfires.py`
  - `tests/integration/test_torpedo_targets_subsystem.py`
  - `tests/integration/test_friendly_fire_handler.py`
  - `tests/integration/test_weapon_hit_event_dispatched.py`

---

## Task 1: `WeaponSystemProperty.SetTorpedoScript` typed accessors

**Files:**
- Modify: `engine/appc/properties.py` (`WeaponSystemProperty` class, find via grep)
- Create: `tests/unit/test_weapon_system_property_torpedo_script.py`

Hardpoints already call `Torpedoes.SetTorpedoScript(0, "Tactical.Projectiles.PhotonTorpedo")` (e.g. [sdk/Build/scripts/ships/Hardpoints/akira.py:158-160](sdk/Build/scripts/ships/Hardpoints/akira.py#L158-L160)). PR 1's catch-all `__getattr__` stores these strings. PR 2b promotes them to typed accessors so `TorpedoTube.Fire` has a reliable read path.

### Steps

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_weapon_system_property_torpedo_script.py`:

```python
"""WeaponSystemProperty.SetTorpedoScript / GetTorpedoScript — typed per-slot
accessors. Hardpoint scripts call e.g. SetTorpedoScript(0, "Tactical.
Projectiles.PhotonTorpedo"); PR 2b's TorpedoTube.Fire reads back.
"""
from engine.appc.properties import WeaponSystemProperty


def test_get_torpedo_script_default_none():
    p = WeaponSystemProperty("Torpedoes")
    assert p.GetTorpedoScript(0) is None


def test_set_get_torpedo_script_roundtrip():
    p = WeaponSystemProperty("Torpedoes")
    p.SetTorpedoScript(0, "Tactical.Projectiles.PhotonTorpedo")
    assert p.GetTorpedoScript(0) == "Tactical.Projectiles.PhotonTorpedo"


def test_set_torpedo_script_multiple_slots():
    p = WeaponSystemProperty("Torpedoes")
    p.SetTorpedoScript(0, "Tactical.Projectiles.PhotonTorpedo")
    p.SetTorpedoScript(1, "Tactical.Projectiles.QuantumTorpedo")
    assert p.GetTorpedoScript(0) == "Tactical.Projectiles.PhotonTorpedo"
    assert p.GetTorpedoScript(1) == "Tactical.Projectiles.QuantumTorpedo"


def test_set_torpedo_script_overwrites_existing():
    p = WeaponSystemProperty("Torpedoes")
    p.SetTorpedoScript(0, "Tactical.Projectiles.PhotonTorpedo")
    p.SetTorpedoScript(0, "Tactical.Projectiles.QuantumTorpedo")
    assert p.GetTorpedoScript(0) == "Tactical.Projectiles.QuantumTorpedo"


def test_set_torpedo_script_coerces_slot_to_int():
    p = WeaponSystemProperty("Torpedoes")
    p.SetTorpedoScript(0.0, "Tactical.Projectiles.PhotonTorpedo")
    assert p.GetTorpedoScript(0) == "Tactical.Projectiles.PhotonTorpedo"
```

- [ ] **Step 2: Run test to verify failures**

```
uv run pytest tests/unit/test_weapon_system_property_torpedo_script.py -v
```

Expected: failures. Without the typed methods, `GetTorpedoScript(0)` returns either `None` from `__getattr__` (one arg) or a no-op (function returned). The first test passes coincidentally (`None` matches); the others fail.

- [ ] **Step 3: Add typed accessors to `WeaponSystemProperty`**

In `engine/appc/properties.py`, find `class WeaponSystemProperty(PoweredSubsystemProperty)` (existing). Extend its `__init__` and add two methods. Match the file's existing multi-line accessor style:

```python
class WeaponSystemProperty(PoweredSubsystemProperty):
    """Existing class — extending with typed torpedo-script accessors.

    Hardpoints call e.g. Torpedoes.SetTorpedoScript(0,
    "Tactical.Projectiles.PhotonTorpedo") to bind ammo slots to projectile
    scripts.  PR 2b's TorpedoTube.Fire reads via GetTorpedoScript at fire
    time, imports the module, calls <module>.Create(torpedo).
    """
    def __init__(self, name: str = ""):
        super().__init__(name)
        # ... existing initialisation (preserve everything that's already here)
        self._torpedo_scripts: dict[int, str] = {}

    def SetTorpedoScript(self, slot, module_name) -> None:
        self._torpedo_scripts[int(slot)] = str(module_name)

    def GetTorpedoScript(self, slot) -> "str | None":
        return self._torpedo_scripts.get(int(slot))

    # ... preserve any other existing methods on the class
```

**Important:** read the existing class before editing — it has other state (`_weapon_system_type`, `_single_fire`, `_aimed_weapon`, etc.) you must preserve.

- [ ] **Step 4: Run tests to verify pass**

```
uv run pytest tests/unit/test_weapon_system_property_torpedo_script.py -v
```

Expected: ALL PASS.

- [ ] **Step 5: Full regression check**

```
uv run pytest tests/unit/ -x
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/appc/properties.py tests/unit/test_weapon_system_property_torpedo_script.py
git commit -m "$(cat <<'EOF'
feat(props): typed SetTorpedoScript/GetTorpedoScript per slot

WeaponSystemProperty tracks projectile-script bindings per ammo slot
via a typed dict.  Promotes the field from PR 1's __getattr__ catch-all
so TorpedoTube.Fire (in a later task) can reliably read the bound
"Tactical.Projectiles.<X>" module name and dispatch to the SDK script.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `Torpedo` runtime class + registry

**Files:**
- Create: `engine/appc/projectiles.py`
- Create: `tests/unit/test_torpedo_create_model.py`
- Create: `tests/unit/test_torpedo_advance.py`

The `Torpedo` class is a data carrier — its visual fields are populated by the SDK projectile script's `CreateTorpedoModel(...)` call (see [sdk/Build/scripts/Tactical/Projectiles/PhotonTorpedo.py:22-45](sdk/Build/scripts/Tactical/Projectiles/PhotonTorpedo.py#L22-L45)). Module-level `_active` registry holds in-flight torpedoes; `update_all(dt, ships)` advances motion, runs collision, returns hits.

### Steps

- [ ] **Step 1: Write failing tests for CreateTorpedoModel**

Create `tests/unit/test_torpedo_create_model.py`:

```python
"""Torpedo.CreateTorpedoModel mirrors sdk/Build/scripts/Tactical/Projectiles/
PhotonTorpedo.py:22-45 — 14 args populate visual fields. SetDamage /
SetDamageRadiusFactor / SetGuidanceLifetime / SetMaxAngularAccel /
SetNetType complete the per-projectile init surface.
"""
import App
from engine.appc.projectiles import Torpedo


def _color(r, g, b, a=1.0):
    c = App.TGColorA()
    c.SetRGBA(r, g, b, a)
    return c


def test_create_torpedo_model_stores_all_visual_fields():
    t = Torpedo()
    core_color   = _color(1.0, 0.99, 0.39)
    glow_color   = _color(1.0, 0.25, 0.0)
    flares_color = glow_color
    t.CreateTorpedoModel(
        "data/Textures/Tactical/TorpedoCore.tga",   core_color, 0.2, 1.2,
        "data/Textures/Tactical/TorpedoGlow.tga",   glow_color, 3.0, 0.3, 0.6,
        "data/Textures/Tactical/TorpedoFlares.tga", flares_color, 8, 0.7, 0.4,
    )
    assert t._core_texture   == "data/Textures/Tactical/TorpedoCore.tga"
    assert t._core_color     is core_color
    assert t._core_size_a    == 0.2
    assert t._core_size_b    == 1.2
    assert t._glow_texture   == "data/Textures/Tactical/TorpedoGlow.tga"
    assert t._glow_color     is glow_color
    assert t._glow_size_a    == 3.0
    assert t._glow_size_b    == 0.3
    assert t._glow_size_c    == 0.6
    assert t._flares_texture == "data/Textures/Tactical/TorpedoFlares.tga"
    assert t._flares_color   is flares_color
    assert t._num_flares     == 8
    assert t._flares_size_a  == 0.7
    assert t._flares_size_b  == 0.4


def test_create_torpedo_model_coerces_numeric_types():
    t = Torpedo()
    t.CreateTorpedoModel("core", None, 1, 2,
                          "glow", None, 3, 4, 5,
                          "flares", None, 8.0, 6, 7)
    # core/glow/flares sizes coerced to float; num_flares coerced to int
    assert isinstance(t._core_size_a, float)
    assert isinstance(t._num_flares, int) and t._num_flares == 8


def test_set_damage_setters_coerce():
    t = Torpedo()
    t.SetDamage(500)
    t.SetDamageRadiusFactor(0.13)
    t.SetGuidanceLifetime(6.0)
    t.SetMaxAngularAccel(0.15)
    assert isinstance(t._damage, float) and t._damage == 500.0
    assert t._damage_radius_factor == 0.13
    assert t._guidance_lifetime == 6.0
    assert t._max_angular_accel == 0.15


def test_set_net_type_is_noop_accept():
    """Multiplayer.SpeciesToTorp.PHOTON etc. — accepted but ignored in PR 2b."""
    t = Torpedo()
    t.SetNetType(123)  # must not raise


def test_create_torpedo_model_via_photon_script():
    """Run the actual SDK PhotonTorpedo.Create against a fresh Torpedo and
    confirm the values match what the script encodes (PhotonTorpedo.py:22-50)."""
    import importlib
    mod = importlib.import_module("Tactical.Projectiles.PhotonTorpedo")
    t = Torpedo()
    mod.Create(t)
    assert t._core_texture.endswith("TorpedoCore.tga")
    assert t._core_size_a == 0.2
    assert t._glow_size_a == 3.0
    assert t._num_flares == 8
    assert t._damage == 500.0
    assert t._guidance_lifetime == 6.0
    assert t._max_angular_accel == 0.15
```

- [ ] **Step 2: Write failing tests for motion / collision**

Create `tests/unit/test_torpedo_advance.py`:

```python
"""Torpedo motion: position += velocity*dt, age increments, TTL expires.
Homing: when target_ship is set and age < guidance_lifetime, velocity
turns toward the target up to max_angular_accel × dt.
Collision: sphere_hit against any ship except source; first hit wins.
"""
import math
import pytest
from engine.appc.math import TGPoint3
from engine.appc.projectiles import Torpedo, register, expire, update_all, _active


@pytest.fixture(autouse=True)
def clear_registry():
    _active.clear()
    yield
    _active.clear()


def _torp_at(x, y, z, vx, vy, vz, ttl=30.0, age=0.0, src=None):
    t = Torpedo()
    t._position = TGPoint3(x, y, z)
    t._velocity = TGPoint3(vx, vy, vz)
    t._ttl = ttl
    t._age = age
    t._source_ship = src
    t._damage = 100.0
    register(t)
    return t


class _FakeShip:
    def __init__(self, x, y, z, radius=10.0, dead=False):
        self._loc = TGPoint3(x, y, z)
        self._r = radius
        self._dead = dead
        self._hull = None
        self._children = []
        self._shields = None

    def GetWorldLocation(self): return self._loc
    def GetRadius(self): return self._r
    def IsDead(self): return 1 if self._dead else 0
    def GetHull(self): return self._hull
    def GetShields(self): return self._shields
    def GetNumChildSubsystems(self): return len(self._children)
    def GetChildSubsystem(self, i): return self._children[i]


def test_torpedo_position_advances_by_velocity_dt():
    t = _torp_at(0, 0, 0, 10, 0, 0)
    update_all(dt=0.1, all_ships=[])
    assert t._position.x == pytest.approx(1.0)
    assert t._age == pytest.approx(0.1)


def test_torpedo_ttl_expires_removes_from_registry():
    _torp_at(0, 0, 0, 0, 0, 0, ttl=0.5, age=0.4)
    update_all(dt=0.2, all_ships=[])  # age becomes 0.6 > ttl
    assert _active == []


def test_torpedo_collides_with_ship_sphere():
    src = _FakeShip(-100, 0, 0)
    target = _FakeShip(5, 0, 0, radius=10.0)
    t = _torp_at(0, 0, 0, 10, 0, 0, src=src)
    hits = update_all(dt=0.1, all_ships=[src, target])
    # Position advances to (1,0,0); distance to (5,0,0) = 4 < radius 10 ⇒ hit
    assert len(hits) == 1
    assert hits[0][0] is t
    assert hits[0][1] is target
    assert _active == []  # torpedo expired post-hit


def test_torpedo_skips_source_ship():
    src = _FakeShip(0, 0, 0, radius=10.0)
    t = _torp_at(0, 0, 0, 1, 0, 0, src=src)
    update_all(dt=0.1, all_ships=[src])
    # Torpedo still inside source's sphere but source skipped; no hit
    assert _active == [t]


def test_torpedo_skips_dead_ship():
    src = _FakeShip(-100, 0, 0)
    target = _FakeShip(5, 0, 0, radius=10.0, dead=True)
    _torp_at(0, 0, 0, 10, 0, 0, src=src)
    hits = update_all(dt=0.1, all_ships=[src, target])
    assert hits == []


def test_homing_torpedo_steers_toward_target():
    """Initial velocity 90° off-axis; after dt, velocity vector is
    rotated toward target by at most max_angular_accel × dt radians."""
    src = _FakeShip(-100, 0, 0)
    target = _FakeShip(0, 100, 0, radius=1.0)
    t = _torp_at(0, 0, 0, 10, 0, 0, src=src)
    t._target_ship = target
    t._guidance_lifetime = 10.0
    t._max_angular_accel = 1.0  # rad/sec
    update_all(dt=0.1, all_ships=[src, target])
    # Velocity should have rotated ~0.1 rad toward +Y from +X.
    # Initial: vx=10, vy=0. After: angle ≈ 0.1 rad ⇒ vy > 0 and vx slightly less than 10.
    assert t._velocity.y > 0.5
    assert t._velocity.x < 10.0
    # Magnitude preserved (constant launch_speed).
    speed = (t._velocity.x**2 + t._velocity.y**2 + t._velocity.z**2) ** 0.5
    assert speed == pytest.approx(10.0, abs=0.01)


def test_dumbfire_velocity_unchanged():
    """Torpedo without target_ship doesn't steer."""
    src = _FakeShip(-100, 0, 0)
    t = _torp_at(0, 0, 0, 10, 0, 0, src=src)
    t._target_ship = None
    update_all(dt=0.1, all_ships=[src])
    assert t._velocity.x == 10.0
    assert t._velocity.y == 0.0


def test_homing_past_guidance_lifetime_stops_steering():
    src = _FakeShip(-100, 0, 0)
    target = _FakeShip(0, 100, 0)
    t = _torp_at(0, 0, 0, 10, 0, 0, age=5.0, src=src)
    t._target_ship = target
    t._guidance_lifetime = 3.0  # already past
    t._max_angular_accel = 1.0
    initial_vx = t._velocity.x
    update_all(dt=0.1, all_ships=[src, target])
    assert t._velocity.x == initial_vx  # no steering after guidance expires
```

- [ ] **Step 3: Run tests to verify they fail**

```
uv run pytest tests/unit/test_torpedo_create_model.py tests/unit/test_torpedo_advance.py -v
```

Expected: `ModuleNotFoundError: No module named 'engine.appc.projectiles'`.

- [ ] **Step 4: Create `engine/appc/projectiles.py`**

```python
"""Torpedo runtime projectile + in-flight registry.

The Torpedo class is a data carrier; the SDK projectile scripts
(sdk/Build/scripts/Tactical/Projectiles/*.py) populate it via
CreateTorpedoModel + SetDamage/SetDamageRadiusFactor/SetGuidance-
Lifetime/SetMaxAngularAccel.  Engine never embeds projectile data —
it always reads from the bound script per shot.

Module-level _active registry holds in-flight torpedoes; update_all
advances motion, runs collision, returns the list of (torpedo, hit_ship,
hit_subsystem) tuples for host_loop to route through combat.apply_hit.
"""
import math

from engine.appc.math import TGPoint3
from engine.core.ids import TGObject


class Torpedo(TGObject):
    """Runtime projectile.  Visual fields populated by CreateTorpedoModel;
    behaviour fields by SetDamage/SetGuidanceLifetime/SetMaxAngularAccel.
    """
    __slots__ = (
        "_position", "_velocity", "_age", "_ttl",
        "_damage", "_damage_radius_factor",
        "_target_ship", "_guidance_lifetime", "_max_angular_accel",
        "_source_ship", "_id",
        "_core_texture", "_core_color", "_core_size_a", "_core_size_b",
        "_glow_texture", "_glow_color", "_glow_size_a", "_glow_size_b", "_glow_size_c",
        "_flares_texture", "_flares_color", "_num_flares",
        "_flares_size_a", "_flares_size_b",
    )

    def __init__(self):
        super().__init__()
        self._position = TGPoint3(0.0, 0.0, 0.0)
        self._velocity = TGPoint3(0.0, 0.0, 0.0)
        self._age = 0.0
        self._ttl = 30.0
        self._damage = 0.0
        self._damage_radius_factor = 0.0
        self._target_ship = None
        self._guidance_lifetime = 0.0
        self._max_angular_accel = 0.0
        self._source_ship = None
        self._id = 0
        # Visual fields — populated by CreateTorpedoModel.
        self._core_texture   = ""
        self._core_color     = None
        self._core_size_a    = 0.0
        self._core_size_b    = 0.0
        self._glow_texture   = ""
        self._glow_color     = None
        self._glow_size_a    = 0.0
        self._glow_size_b    = 0.0
        self._glow_size_c    = 0.0
        self._flares_texture = ""
        self._flares_color   = None
        self._num_flares     = 0
        self._flares_size_a  = 0.0
        self._flares_size_b  = 0.0

    def CreateTorpedoModel(self,
            core_tex, core_color, core_a, core_b,
            glow_tex, glow_color, glow_a, glow_b, glow_c,
            flares_tex, flares_color, num_flares, flares_a, flares_b) -> None:
        self._core_texture   = str(core_tex)
        self._core_color     = core_color
        self._core_size_a    = float(core_a)
        self._core_size_b    = float(core_b)
        self._glow_texture   = str(glow_tex)
        self._glow_color     = glow_color
        self._glow_size_a    = float(glow_a)
        self._glow_size_b    = float(glow_b)
        self._glow_size_c    = float(glow_c)
        self._flares_texture = str(flares_tex)
        self._flares_color   = flares_color
        self._num_flares     = int(num_flares)
        self._flares_size_a  = float(flares_a)
        self._flares_size_b  = float(flares_b)

    def SetDamage(self, v) -> None:               self._damage = float(v)
    def SetDamageRadiusFactor(self, v) -> None:   self._damage_radius_factor = float(v)
    def SetGuidanceLifetime(self, v) -> None:     self._guidance_lifetime = float(v)
    def SetMaxAngularAccel(self, v) -> None:      self._max_angular_accel = float(v)
    def SetNetType(self, v) -> None:              pass  # multiplayer; ignored in PR 2b


# ── Registry ────────────────────────────────────────────────────────────────
_active: list[Torpedo] = []
_next_id: int = 1


def register(torpedo: Torpedo) -> None:
    global _next_id
    torpedo._id = _next_id
    _next_id += 1
    _active.append(torpedo)


def expire(torpedo: Torpedo) -> None:
    try:
        _active.remove(torpedo)
    except ValueError:
        pass


def update_all(dt: float, all_ships) -> list[tuple]:
    """Advance every active torpedo by dt.  Returns list of
    (torpedo, hit_ship, hit_subsystem) tuples that connected this tick.
    Expired torpedoes (TTL or impact) are removed from _active.
    """
    from engine.appc.combat import pick_target_subsystem, sphere_hit
    hits: list[tuple] = []
    expired: list[Torpedo] = []

    for t in list(_active):
        # 1. Steer if homing within guidance window.
        if t._target_ship is not None and t._age < t._guidance_lifetime:
            _steer_toward(t, t._target_ship, dt)
        # 2. Advance position + age.
        t._position = t._position + t._velocity * dt
        t._age += dt
        if t._age >= t._ttl:
            expired.append(t)
            continue
        # 3. Collide.
        for ship in all_ships:
            if ship is t._source_ship:
                continue
            if ship.IsDead():
                continue
            if sphere_hit(t._position, ship.GetWorldLocation(), ship.GetRadius()):
                subsystem = pick_target_subsystem(ship, t._position)
                hits.append((t, ship, subsystem))
                expired.append(t)
                break

    for t in expired:
        expire(t)

    return hits


def _steer_toward(torpedo: Torpedo, target_ship, dt: float) -> None:
    """Rotate torpedo._velocity toward target ship position by at most
    max_angular_accel × dt radians.  Preserves velocity magnitude.
    """
    target_pos = target_ship.GetWorldLocation()
    to_target = target_pos - torpedo._position
    dist = to_target.Length()
    if dist < 1e-6:
        return
    desired = TGPoint3(to_target.x / dist, to_target.y / dist, to_target.z / dist)

    speed = torpedo._velocity.Length()
    if speed < 1e-6:
        return
    current = TGPoint3(
        torpedo._velocity.x / speed,
        torpedo._velocity.y / speed,
        torpedo._velocity.z / speed,
    )

    cos_theta = max(-1.0, min(1.0, current.Dot(desired)))
    theta = math.acos(cos_theta)
    max_step = torpedo._max_angular_accel * dt
    if theta <= max_step:
        new_dir = desired
    else:
        # Slerp by max_step from current toward desired.
        sin_theta = math.sin(theta)
        a = math.sin(theta - max_step) / sin_theta
        b = math.sin(max_step) / sin_theta
        new_dir = TGPoint3(
            current.x * a + desired.x * b,
            current.y * a + desired.y * b,
            current.z * a + desired.z * b,
        )
    torpedo._velocity = new_dir * speed
```

- [ ] **Step 5: Run tests to verify pass**

```
uv run pytest tests/unit/test_torpedo_create_model.py tests/unit/test_torpedo_advance.py -v
```

Expected: ALL PASS. If `test_create_torpedo_model_via_photon_script` fails on the SDK import, check that `sdk/Build/scripts` is on the test `sys.path` (it should be — conftest.py wires it).

If `pick_target_subsystem` or `sphere_hit` aren't yet defined in `combat.py` (because Task 5 hasn't run), the failure will be inside `update_all`. Stub them out in `combat.py` for this task ONLY by creating a minimal `combat.py` with:

```python
# engine/appc/combat.py (temporary stub for Task 2; Task 5 replaces)
from engine.appc.math import TGPoint3


def sphere_hit(point: TGPoint3, center: TGPoint3, radius: float) -> bool:
    dx = point.x - center.x
    dy = point.y - center.y
    dz = point.z - center.z
    return (dx * dx + dy * dy + dz * dz) <= radius * radius


def pick_target_subsystem(ship, hit_point):
    """Stub for Task 2.  Task 5 implements the real subsystem walk."""
    return ship.GetHull() if hasattr(ship, "GetHull") else None
```

Task 5 will replace this with the full implementation.

- [ ] **Step 6: Full regression check**

```
uv run pytest tests/unit/ -x
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add engine/appc/projectiles.py engine/appc/combat.py \
        tests/unit/test_torpedo_create_model.py \
        tests/unit/test_torpedo_advance.py
git commit -m "$(cat <<'EOF'
feat(combat): Torpedo runtime + in-flight registry

Torpedo class is a data carrier for SDK projectile scripts:
CreateTorpedoModel stores 14 visual fields, SetDamage / SetGuidance-
Lifetime / SetMaxAngularAccel store behaviour.  Verified against
sdk/Build/scripts/Tactical/Projectiles/PhotonTorpedo.py's actual
Create() call.

Module-level _active registry + register/expire/update_all(dt, ships).
update_all steers homing torpedoes via slerp limited by max_angular_
accel, advances motion, expires on TTL or impact, returns hits as
(torpedo, ship, subsystem) tuples.

engine/appc/combat.py introduced with stub sphere_hit + pick_target_
subsystem; Task 5 will replace with the full implementation.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `WeaponHitEvent` + `ET_WEAPON_HIT`

**Files:**
- Modify: `engine/appc/events.py` — add the event class + constant.
- Modify: `App.py` — re-export.
- Create: `tests/unit/test_weapon_hit_event.py`

### Steps

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_weapon_hit_event.py`:

```python
"""WeaponHitEvent — TGEvent subclass carrying source/target/damage/
hit_point/subsystem. ET_WEAPON_HIT broadcast via g_kEventManager.
"""
from engine.appc.events import (
    TGEventManager, TGEventHandlerObject, WeaponHitEvent, ET_WEAPON_HIT,
)
from engine.appc.math import TGPoint3


class _Recorder(TGEventHandlerObject):
    def __init__(self):
        super().__init__()
        self.received = []

    def ProcessEvent(self, evt):
        self.received.append(evt)


def test_weapon_hit_event_defaults():
    e = WeaponHitEvent()
    assert e.GetEventType() == ET_WEAPON_HIT
    assert e.GetSource() is None
    assert e.GetTarget() is None
    assert e.GetDamage() == 0.0
    assert e.GetHitPoint() is None
    assert e.GetSubsystem() is None


def test_weapon_hit_event_roundtrip():
    src = object()
    tgt = object()
    sub = object()
    pt = TGPoint3(1, 2, 3)
    e = WeaponHitEvent()
    e.SetSource(src)
    e.SetTarget(tgt)
    e.SetDamage(500.0)
    e.SetHitPoint(pt)
    e.SetSubsystem(sub)
    assert e.GetSource() is src
    assert e.GetTarget() is tgt
    assert e.GetDamage() == 500.0
    assert e.GetHitPoint() is pt
    assert e.GetSubsystem() is sub


def test_weapon_hit_event_dispatched_to_destination():
    em = TGEventManager()
    dest = _Recorder()
    e = WeaponHitEvent()
    e.SetDestination(dest)
    e.SetDamage(42.0)
    em.AddEvent(e)
    assert len(dest.received) == 1
    assert dest.received[0].GetDamage() == 42.0


def test_weapon_hit_event_broadcast_handler_fires():
    em = TGEventManager()
    received = []
    def handler(_obj, evt):
        received.append(evt.GetDamage())
    import sys, types
    # Register via a module-level qualified name so AddBroadcastPythonFuncHandler
    # can resolve it (same pattern as test_tg_input_manager.py).
    mod = types.ModuleType("_test_weapon_hit_handler")
    mod.handler = handler
    sys.modules["_test_weapon_hit_handler"] = mod
    em.AddBroadcastPythonFuncHandler(ET_WEAPON_HIT, None,
                                      "_test_weapon_hit_handler.handler")
    e = WeaponHitEvent()
    e.SetDamage(99.0)
    em.AddEvent(e)
    assert received == [99.0]
    del sys.modules["_test_weapon_hit_handler"]
```

- [ ] **Step 2: Run to verify failure**

```
uv run pytest tests/unit/test_weapon_hit_event.py -v
```

Expected: `ImportError: cannot import name 'WeaponHitEvent'`.

- [ ] **Step 3: Add `WeaponHitEvent` + `ET_WEAPON_HIT` to `engine/appc/events.py`**

In `engine/appc/events.py`, after the existing `ET_KEYBOARD_EVENT = 0x1000` constant, add:

```python
ET_WEAPON_HIT: int = 0x1100  # reserved range above input-event ids
```

After the existing `TGKeyboardEvent` class, add:

```python
class WeaponHitEvent(TGEvent):
    """Weapon-impact event.  Broadcast by engine.appc.combat.apply_hit
    after damage is routed.  Mission scripts subscribe to ET_WEAPON_HIT
    (per-ship or broadcast) to react — e.g. MissionLib.FriendlyFireHandler
    triggers XO dialogue when the player damages a friendly NPC.
    """
    def __init__(self):
        super().__init__()
        self._event_type = ET_WEAPON_HIT
        self._source = None
        self._target = None
        self._damage: float = 0.0
        self._hit_point = None
        self._subsystem = None

    def GetSource(self):              return self._source
    def SetSource(self, src) -> None: self._source = src
    def GetTarget(self):              return self._target
    def SetTarget(self, tgt) -> None: self._target = tgt
    def GetDamage(self) -> float:     return self._damage
    def SetDamage(self, v) -> None:   self._damage = float(v)
    def GetHitPoint(self):            return self._hit_point
    def SetHitPoint(self, p) -> None: self._hit_point = p
    def GetSubsystem(self):           return self._subsystem
    def SetSubsystem(self, s) -> None: self._subsystem = s
```

- [ ] **Step 4: Re-export from `App.py`**

In `App.py`, extend the existing `from engine.appc.events import (...)` import block (around line 8) to include:

```python
from engine.appc.events import (
    # ... existing imports ...
    WeaponHitEvent, ET_WEAPON_HIT,
)
```

- [ ] **Step 5: Run tests to verify pass**

```
uv run pytest tests/unit/test_weapon_hit_event.py -v
```

Expected: ALL PASS.

- [ ] **Step 6: Full regression check**

```
uv run pytest tests/unit/ -x
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add engine/appc/events.py App.py tests/unit/test_weapon_hit_event.py
git commit -m "$(cat <<'EOF'
feat(events): WeaponHitEvent + ET_WEAPON_HIT

Reserves event-type id 0x1100 above the input range.  WeaponHitEvent
carries source/target/damage/hit_point/subsystem so mission-script
handlers (FriendlyFireHandler, per-ship damage listeners) receive
enough context to react.  Broadcast via g_kEventManager.AddEvent in
combat.apply_hit (Task 5).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `DamageableObject.DamageSystem`

**Files:**
- Modify: `engine/appc/objects.py` — extend `DamageableObject`.
- Create: `tests/unit/test_damage_system_method.py`

### Steps

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_damage_system_method.py`:

```python
"""DamageableObject.DamageSystem(subsystem, amount) decrements
subsystem condition. Hull-zero triggers SetDying(True).
"""
from engine.appc.ships import ShipClass_Create
from engine.appc.subsystems import HullSubsystem


def _ship_with_hull(max_cond=1000.0):
    ship = ShipClass_Create("Test")
    hull = HullSubsystem("Hull")
    hull.SetMaxCondition(max_cond)
    ship._hull = hull
    return ship, hull


def test_damage_system_decrements_condition():
    ship, hull = _ship_with_hull(max_cond=1000.0)
    ship.DamageSystem(hull, 300.0)
    assert hull.GetCondition() == 700.0


def test_damage_system_floors_at_zero():
    ship, hull = _ship_with_hull(max_cond=100.0)
    ship.DamageSystem(hull, 500.0)
    assert hull.GetCondition() == 0.0


def test_damage_system_no_op_on_none():
    ship, _ = _ship_with_hull()
    ship.DamageSystem(None, 100.0)  # must not raise


def test_damage_system_hull_zero_triggers_dying():
    ship, hull = _ship_with_hull(max_cond=50.0)
    assert ship.IsDying() == 0
    ship.DamageSystem(hull, 50.0)
    assert hull.GetCondition() == 0.0
    assert ship.IsDying() == 1


def test_damage_system_non_hull_zero_does_not_trigger_dying():
    """A subsystem at zero condition that isn't the hull does NOT
    flip the ship to dying — that's a hull-only effect."""
    from engine.appc.subsystems import SensorSubsystem
    ship, hull = _ship_with_hull(max_cond=1000.0)
    sensor = SensorSubsystem("Sensors")
    sensor.SetMaxCondition(100.0)
    ship.DamageSystem(sensor, 100.0)
    assert sensor.GetCondition() == 0.0
    assert ship.IsDying() == 0
```

- [ ] **Step 2: Run to verify failure**

```
uv run pytest tests/unit/test_damage_system_method.py -v
```

Expected: `AttributeError: 'ShipClass' object has no attribute 'DamageSystem'`.

- [ ] **Step 3: Add `DamageSystem` to `DamageableObject`**

In `engine/appc/objects.py`, find `class DamageableObject(PhysicsObjectClass)`. Add this method (multi-line because logic):

```python
    def DamageSystem(self, subsystem, amount: float) -> None:
        """Apply damage to a subsystem.  Decrement its condition floored
        at zero.  If the subsystem is this object's hull and condition
        reaches zero, mark the object as dying — mission scripts trigger
        the destruction sequence via the existing SetDying/SetDead path.
        """
        if subsystem is None:
            return
        amt = float(amount)
        if amt <= 0.0:
            return
        cur = subsystem.GetCondition()
        new_cond = max(0.0, cur - amt)
        subsystem.SetCondition(new_cond)
        # Hull-zero triggers ship-dying; other subsystems do not.
        hull = self.GetHull() if hasattr(self, "GetHull") else None
        if subsystem is hull and new_cond <= 0.0 and hasattr(self, "SetDying"):
            self.SetDying(True)
```

Note: `subsystem.SetCondition(...)` may not exist on every subsystem class. Check `engine/appc/subsystems.py` and add a `SetCondition(v)` setter on `ShipSubsystem` if missing. The existing class has `GetCondition() -> float` (around line 153); the setter pattern follows the same multi-line style:

```python
    def SetCondition(self, value: float) -> None:
        self._condition = max(0.0, float(value))
```

- [ ] **Step 4: Run tests to verify pass**

```
uv run pytest tests/unit/test_damage_system_method.py -v
```

Expected: ALL PASS.

- [ ] **Step 5: Full regression check**

```
uv run pytest tests/unit/ -x
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/appc/objects.py engine/appc/subsystems.py \
        tests/unit/test_damage_system_method.py
git commit -m "$(cat <<'EOF'
feat(damage): DamageableObject.DamageSystem(subsystem, amount)

Decrements subsystem condition floored at zero.  Hull-zero triggers
SetDying(True) so the existing destruction sequence runs.  Other
subsystems at zero just stay at zero — they're still attached to the
ship, just non-functional, matching BC behaviour where you can survive
on a damaged ship with destroyed sensors/weapons/etc.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `combat.py` — collision + damage routing

**Files:**
- Modify: `engine/appc/combat.py` (replace the Task 2 stub).
- Create: `tests/unit/test_sphere_hit.py`
- Create: `tests/unit/test_pick_target_subsystem.py`
- Create: `tests/unit/test_apply_hit_routing.py`

### Steps

- [ ] **Step 1: Write failing tests for sphere_hit**

Create `tests/unit/test_sphere_hit.py`:

```python
from engine.appc.math import TGPoint3
from engine.appc.combat import sphere_hit


def test_point_inside_sphere_hits():
    assert sphere_hit(TGPoint3(1, 0, 0), TGPoint3(0, 0, 0), radius=2.0) is True


def test_point_outside_sphere_misses():
    assert sphere_hit(TGPoint3(5, 0, 0), TGPoint3(0, 0, 0), radius=2.0) is False


def test_point_on_sphere_boundary_hits():
    assert sphere_hit(TGPoint3(2, 0, 0), TGPoint3(0, 0, 0), radius=2.0) is True


def test_sphere_hit_uses_squared_distance():
    # Slight tolerance check: 3-4-5 triangle, distance 5, radius 5 should hit.
    assert sphere_hit(TGPoint3(3, 4, 0), TGPoint3(0, 0, 0), radius=5.0) is True
```

- [ ] **Step 2: Write failing tests for pick_target_subsystem**

Create `tests/unit/test_pick_target_subsystem.py`:

```python
"""pick_target_subsystem walks the ship's subsystem tree; returns the
subsystem whose hardpoint position is closest to hit_point AND within
~2× its radius.  Falls back to hull when no subsystem matches.
"""
from engine.appc.math import TGPoint3
from engine.appc.combat import pick_target_subsystem


class _FakeSubsystem:
    def __init__(self, name, position, radius):
        self._name = name
        self._position = position
        self._radius = radius

    def GetName(self): return self._name
    def GetPosition(self): return self._position
    def GetRadius(self): return self._radius


class _FakeShip:
    def __init__(self, hull=None, children=()):
        self._hull = hull
        self._children = list(children)
        self._loc = TGPoint3(0, 0, 0)

    def GetHull(self): return self._hull
    def GetWorldLocation(self): return self._loc
    def GetNumChildSubsystems(self): return len(self._children)
    def GetChildSubsystem(self, i): return self._children[i]


def test_picks_nearest_subsystem_within_radius():
    hull = _FakeSubsystem("Hull", TGPoint3(0, 0, 0), 5.0)
    bridge = _FakeSubsystem("Bridge", TGPoint3(0, 5, 0), 1.0)
    engines = _FakeSubsystem("Engines", TGPoint3(0, -5, 0), 1.0)
    ship = _FakeShip(hull=hull, children=[bridge, engines])
    # Hit point near Bridge
    picked = pick_target_subsystem(ship, TGPoint3(0, 5.5, 0))
    assert picked is bridge


def test_falls_back_to_hull_when_no_subsystem_close():
    hull = _FakeSubsystem("Hull", TGPoint3(0, 0, 0), 5.0)
    bridge = _FakeSubsystem("Bridge", TGPoint3(0, 5, 0), 1.0)
    ship = _FakeShip(hull=hull, children=[bridge])
    # Hit point far from any subsystem (>2× radius from Bridge)
    picked = pick_target_subsystem(ship, TGPoint3(0, 50, 0))
    assert picked is hull


def test_returns_none_when_no_hull_and_no_match():
    ship = _FakeShip(hull=None, children=[])
    picked = pick_target_subsystem(ship, TGPoint3(0, 0, 0))
    assert picked is None


def test_picks_closer_of_two_in_range():
    hull = _FakeSubsystem("Hull", TGPoint3(0, 0, 0), 5.0)
    bridge = _FakeSubsystem("Bridge", TGPoint3(0, 5, 0), 2.0)
    aux = _FakeSubsystem("Aux", TGPoint3(0, 6, 0), 2.0)
    ship = _FakeShip(hull=hull, children=[bridge, aux])
    # Hit point at y=5.5 — distance 0.5 to Bridge, 0.5 to Aux. Tie-break by iteration order.
    # Adjust to make Bridge unambiguously closer.
    picked = pick_target_subsystem(ship, TGPoint3(0, 5.1, 0))
    assert picked is bridge
```

- [ ] **Step 3: Write failing tests for apply_hit**

Create `tests/unit/test_apply_hit_routing.py`:

```python
"""apply_hit routes damage: shields-face → subsystem → hull bleed.
Broadcasts WeaponHitEvent at the end.
"""
import sys
import types
from engine.appc.math import TGPoint3
from engine.appc.combat import apply_hit
from engine.appc.events import ET_WEAPON_HIT


class _FakeShields:
    def __init__(self, current=1000.0):
        self._cur = [current] * 6

    def ApplyDamage(self, face, amount):
        amt = float(amount)
        cur = self._cur[int(face)]
        if amt <= cur:
            self._cur[int(face)] = cur - amt
            return 0.0
        self._cur[int(face)] = 0.0
        return amt - cur


class _FakeSubsystem:
    def __init__(self, name, max_cond=1000.0, position=None, radius=1.0):
        self._name = name
        self._condition = max_cond
        self._max_condition = max_cond
        self._position = position or TGPoint3(0, 0, 0)
        self._radius = radius

    def GetName(self): return self._name
    def GetCondition(self): return self._condition
    def SetCondition(self, v): self._condition = max(0.0, float(v))
    def GetMaxCondition(self): return self._max_condition
    def GetPosition(self): return self._position
    def GetRadius(self): return self._radius


class _FakeShip:
    def __init__(self, shields=None, hull=None, children=()):
        self._shields = shields
        self._hull = hull
        self._children = list(children)
        self._dying = False
        self._loc = TGPoint3(0, 0, 0)

    def GetShields(self): return self._shields
    def GetHull(self): return self._hull
    def GetNumChildSubsystems(self): return len(self._children)
    def GetChildSubsystem(self, i): return self._children[i]
    def GetWorldLocation(self): return self._loc
    def IsDying(self): return 1 if self._dying else 0
    def SetDying(self, v): self._dying = bool(v)

    def DamageSystem(self, subsystem, amount):
        if subsystem is None: return
        new = max(0.0, subsystem.GetCondition() - float(amount))
        subsystem.SetCondition(new)
        if subsystem is self._hull and new <= 0.0:
            self.SetDying(True)


def test_full_damage_absorbed_by_shields():
    shields = _FakeShields(current=1000.0)
    hull = _FakeSubsystem("Hull", max_cond=2000.0)
    ship = _FakeShip(shields=shields, hull=hull)
    apply_hit(ship, 500.0, TGPoint3(0, 10, 0), source=None)
    # Shields took it; hull untouched.
    assert hull.GetCondition() == 2000.0


def test_excess_bleeds_to_hull_when_no_subsystem_match():
    shields = _FakeShields(current=100.0)
    hull = _FakeSubsystem("Hull", max_cond=1000.0)
    ship = _FakeShip(shields=shields, hull=hull)
    apply_hit(ship, 500.0, TGPoint3(0, 100, 0), source=None)  # far from any subsystem
    # Shields absorbed 100, hull took remaining 400.
    assert hull.GetCondition() == 600.0


def test_excess_routes_to_picked_subsystem_first():
    shields = _FakeShields(current=100.0)
    hull = _FakeSubsystem("Hull", max_cond=1000.0)
    bridge = _FakeSubsystem("Bridge", max_cond=300.0, position=TGPoint3(0, 5, 0), radius=2.0)
    ship = _FakeShip(shields=shields, hull=hull, children=[bridge])
    apply_hit(ship, 500.0, TGPoint3(0, 5, 0), source=None)
    # Shields absorbed 100, bridge took 300 (capped), remaining 100 bled to hull.
    assert bridge.GetCondition() == 0.0
    assert hull.GetCondition() == 900.0


def test_hull_zero_marks_ship_dying():
    shields = _FakeShields(current=0.0)
    hull = _FakeSubsystem("Hull", max_cond=100.0)
    ship = _FakeShip(shields=shields, hull=hull)
    assert ship.IsDying() == 0
    apply_hit(ship, 100.0, TGPoint3(0, 0, 0), source=None)
    assert hull.GetCondition() == 0.0
    assert ship.IsDying() == 1


def test_apply_hit_broadcasts_weapon_hit_event():
    received = []
    def handler(_obj, evt):
        received.append(evt.GetDamage())

    mod = types.ModuleType("_test_apply_hit_broadcast")
    mod.handler = handler
    sys.modules["_test_apply_hit_broadcast"] = mod
    try:
        import App
        App.g_kEventManager.AddBroadcastPythonFuncHandler(
            ET_WEAPON_HIT, None, "_test_apply_hit_broadcast.handler")

        shields = _FakeShields(current=10000.0)
        hull = _FakeSubsystem("Hull")
        ship = _FakeShip(shields=shields, hull=hull)
        apply_hit(ship, 42.0, TGPoint3(0, 0, 0), source=None)
        assert received == [42.0]
    finally:
        del sys.modules["_test_apply_hit_broadcast"]
```

- [ ] **Step 4: Run all three test files to verify failures**

```
uv run pytest tests/unit/test_sphere_hit.py tests/unit/test_pick_target_subsystem.py tests/unit/test_apply_hit_routing.py -v
```

Expected: failures across the board. `sphere_hit` exists from the Task 2 stub (passes); `pick_target_subsystem` is a stub that always returns hull (some tests pass coincidentally); `apply_hit` doesn't exist yet.

- [ ] **Step 5: Replace `engine/appc/combat.py`**

Replace the file with the full implementation:

```python
"""Combat collision + damage routing.

Called by host_loop._advance_combat after engine.appc.projectiles.
update_all reports a torpedo hit.  Routes damage shields-face → picked
subsystem → hull bleed, then broadcasts WeaponHitEvent so mission
handlers (FriendlyFireHandler etc.) see the hit.
"""
import math

from engine.appc.math import TGPoint3


def sphere_hit(point, center, radius: float) -> bool:
    """Point-in-sphere test using squared distance (no sqrt)."""
    dx = point.x - center.x
    dy = point.y - center.y
    dz = point.z - center.z
    r = float(radius)
    return (dx * dx + dy * dy + dz * dz) <= r * r


def pick_target_subsystem(ship, hit_point):
    """Return the subsystem whose hardpoint position is closest to
    hit_point AND within ~2× its radius.  Falls back to ship.GetHull().

    Hit point is in world space; we compare against subsystem.GetPosition()
    which (per engine.appc.subsystems) already returns world coords when
    the subsystem is parented to a ship.
    """
    best = None
    best_dist_sq = float("inf")
    n = ship.GetNumChildSubsystems() if hasattr(ship, "GetNumChildSubsystems") else 0
    for i in range(n):
        sub = ship.GetChildSubsystem(i)
        if sub is None or not hasattr(sub, "GetPosition"):
            continue
        pos = sub.GetPosition()
        r = sub.GetRadius() if hasattr(sub, "GetRadius") else 0.0
        dx = hit_point.x - pos.x
        dy = hit_point.y - pos.y
        dz = hit_point.z - pos.z
        d_sq = dx * dx + dy * dy + dz * dz
        if d_sq > (2.0 * r) ** 2:
            continue
        if d_sq < best_dist_sq:
            best = sub
            best_dist_sq = d_sq
    if best is not None:
        return best
    return ship.GetHull() if hasattr(ship, "GetHull") else None


def _shield_face_from_hit_point(ship, hit_point) -> int:
    """Map a world hit-point to a shield-face index (0-5 per
    ShieldProperty.NUM_SHIELDS).  Front/Rear/Top/Bottom/Left/Right by
    dominant axis of (hit_point - ship_pos) in ship-local frame.

    For PR 2b we approximate using the world delta directly — proper
    transform via ship.GetWorldRotation() is a polish item.
    """
    ship_pos = ship.GetWorldLocation()
    dx = hit_point.x - ship_pos.x
    dy = hit_point.y - ship_pos.y
    dz = hit_point.z - ship_pos.z
    # Pick dominant axis.  Ship local +Y is forward by BC convention.
    abs_x, abs_y, abs_z = abs(dx), abs(dy), abs(dz)
    if abs_y >= abs_x and abs_y >= abs_z:
        return 0 if dy >= 0 else 1   # FRONT / REAR
    if abs_z >= abs_x:
        return 2 if dz >= 0 else 3   # TOP / BOTTOM
    return 4 if dx <= 0 else 5       # LEFT / RIGHT


def apply_hit(ship, damage: float, hit_point, source, subsystem=None) -> None:
    """Route `damage` to `ship`: shields face first → picked subsystem
    → hull bleed.  Broadcast WeaponHitEvent at the end.
    """
    from engine.appc.events import WeaponHitEvent
    import App

    if subsystem is None:
        subsystem = pick_target_subsystem(ship, hit_point)

    remaining = float(damage)

    # 1. Shields take it first.
    shields = ship.GetShields() if hasattr(ship, "GetShields") else None
    if shields is not None:
        face = _shield_face_from_hit_point(ship, hit_point)
        remaining = shields.ApplyDamage(face, remaining)

    # 2. Bleed remainder to picked subsystem.
    if remaining > 0.0 and subsystem is not None and subsystem is not ship.GetHull():
        if hasattr(ship, "DamageSystem"):
            current = subsystem.GetCondition() if hasattr(subsystem, "GetCondition") else remaining
            absorb = min(remaining, current)
            ship.DamageSystem(subsystem, absorb)
            remaining -= absorb

    # 3. Bleed final remainder to hull.
    if remaining > 0.0:
        hull = ship.GetHull() if hasattr(ship, "GetHull") else None
        if hull is not None and hasattr(ship, "DamageSystem"):
            ship.DamageSystem(hull, remaining)

    # 4. Broadcast WeaponHitEvent.
    evt = WeaponHitEvent()
    evt.SetSource(source)
    evt.SetTarget(ship)
    evt.SetDamage(damage)
    evt.SetHitPoint(hit_point)
    evt.SetSubsystem(subsystem)
    App.g_kEventManager.AddEvent(evt)
```

- [ ] **Step 6: Run all combat tests**

```
uv run pytest tests/unit/test_sphere_hit.py tests/unit/test_pick_target_subsystem.py tests/unit/test_apply_hit_routing.py -v
```

Expected: ALL PASS.

- [ ] **Step 7: Full regression check**

```
uv run pytest tests/unit/ -x
```

Expected: PASS (including the Task 2 torpedo-advance tests that depended on the stubs).

- [ ] **Step 8: Commit**

```bash
git add engine/appc/combat.py tests/unit/test_sphere_hit.py \
        tests/unit/test_pick_target_subsystem.py \
        tests/unit/test_apply_hit_routing.py
git commit -m "$(cat <<'EOF'
feat(combat): sphere collision + damage routing

sphere_hit(point, center, radius) — squared-distance point-in-sphere.
pick_target_subsystem(ship, hit_point) — nearest hardpoint within ~2×
its radius; falls back to hull when nothing close.
apply_hit(ship, damage, hit_point, source) — shields-face absorbs first
(via ShieldSubsystem.ApplyDamage overflow return), bleeds remainder to
picked subsystem, then to hull.  Broadcasts WeaponHitEvent so
MissionLib.FriendlyFireHandler + per-ship damage listeners see hits.

Shield face picked by dominant axis of world (hit - ship); proper
ship-local transform is a future polish item.

Replaces the Task 2 stub combat.py.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `TorpedoTube.Fire` spawns the projectile

**Files:**
- Modify: `engine/appc/subsystems.py` — extend `TorpedoTube.Fire`.
- Modify: `engine/appc/subsystems.py` — add a `_climb_to_ship` helper or use existing parent traversal.

This task ties the previous building blocks together: when a tube fires, look up the bound projectile script, import it, instantiate a `Torpedo`, call `<script>.Create(torpedo)` to populate visuals + behaviour, compute initial velocity (homing if target locked, dumbfire from emitter direction otherwise), play launch sound, register with the projectiles module.

### Steps

- [ ] **Step 1: Write integration-style test for the spawn path**

(This is a unit test of `TorpedoTube.Fire` plus the new `_spawn_torpedo` helper, not an end-to-end integration test.)

Add to `tests/unit/test_torpedo_tube_fire.py` (the existing file from PR 2a — extend it):

```python
"""Existing test file from PR 2a — appending PR 2b spawn-path tests."""
# ... existing tests stay ...

from unittest.mock import patch
import App
from engine.appc.projectiles import _active
from engine.appc.properties import WeaponSystemProperty


def _galaxy_tube_loaded_with_photon():
    """Set up a TorpedoTube parented to a TorpedoSystem with a PhotonTorpedo
    script bound at slot 0.  Returns (tube, parent_system, parent_ship)."""
    from engine.appc.ships import ShipClass_Create
    from engine.appc.subsystems import TorpedoSystem, TorpedoTube
    ship = ShipClass_Create("Test")
    parent = TorpedoSystem("Torpedoes")
    parent.TurnOn()
    # Bind script via the property.
    parent_prop = WeaponSystemProperty("Torpedoes")
    parent_prop.SetTorpedoScript(0, "Tactical.Projectiles.PhotonTorpedo")
    parent.SetProperty(parent_prop)
    ship.SetPhaserSystem(None)  # ensure no phaser confusion
    # Attach the parent system to the ship — direct slot assignment.
    ship._torpedo_system = parent
    # Set ship world location/rotation for emitter-world-position math.
    from engine.appc.math import TGPoint3
    ship.SetWorldLocation(TGPoint3(0, 0, 0))
    # Tube with 1 ready torp, parented to the system.
    tube = TorpedoTube("Forward Torpedo 1")
    tube._max_ready = 1
    tube._num_ready = 1
    tube._reload_delay = 40.0
    parent.AddChildSubsystem(tube)
    return tube, parent, ship


def test_fire_spawns_torpedo_with_script_visuals():
    tube, _, _ = _galaxy_tube_loaded_with_photon()
    initial_active = len(_active)
    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        tube.Fire(target=None, offset=None)
    assert len(_active) == initial_active + 1
    torp = _active[-1]
    # Visual fields populated by PhotonTorpedo.Create:
    assert torp._core_texture.endswith("TorpedoCore.tga")
    assert torp._core_size_a == 0.2
    assert torp._damage == 500.0
    assert torp._guidance_lifetime == 6.0
    _active.clear()


def test_fire_dumbfires_when_no_target_lock():
    """No GetTarget on ship → velocity points along emitter direction
    rotated by ship orientation."""
    tube, _, ship = _galaxy_tube_loaded_with_photon()
    ship._target = None  # explicit
    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        tube.Fire(target=None, offset=None)
    torp = _active[-1]
    assert torp._target_ship is None  # no homing target stored
    # Velocity should be non-zero (launch_speed in some direction).
    speed = torp._velocity.Length()
    assert speed > 0.0
    _active.clear()


def test_fire_homes_when_target_locked():
    tube, _, ship = _galaxy_tube_loaded_with_photon()
    # Mock target ship.
    class _Tgt:
        from engine.appc.math import TGPoint3
        def GetWorldLocation(self): return _Tgt.TGPoint3(100, 0, 0)
    ship._target = _Tgt()
    ship._target_subsystem = None
    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        tube.Fire(target=None, offset=None)
    torp = _active[-1]
    assert torp._target_ship is ship._target  # homing target stored
    # Velocity should point roughly toward +X.
    assert torp._velocity.x > 0.0
    _active.clear()


def test_fire_no_script_bound_silent_no_op():
    """If no script bound for slot 0, Fire still consumes ammo but
    doesn't spawn a Torpedo."""
    tube, parent, ship = _galaxy_tube_loaded_with_photon()
    parent.GetProperty()._torpedo_scripts.clear()
    initial_ready = tube.GetNumReady()
    initial_active = len(_active)
    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        tube.Fire(target=None, offset=None)
    # Existing PR 2a behaviour: NumReady decremented.
    assert tube.GetNumReady() == initial_ready - 1
    # But no torpedo spawned.
    assert len(_active) == initial_active
    _active.clear()


def test_fire_plays_launch_sound():
    tube, _, _ = _galaxy_tube_loaded_with_photon()
    with patch("engine.audio.tg_sound.TGSoundManager.instance") as mock_mgr:
        tube.Fire(target=None, offset=None)
        mock_mgr.return_value.PlaySound.assert_called_with("Photon Torpedo")
    _active.clear()
```

- [ ] **Step 2: Run tests to verify failures**

```
uv run pytest tests/unit/test_torpedo_tube_fire.py -v
```

Expected: existing PR 2a tests pass; new tests fail because `TorpedoTube.Fire` doesn't spawn projectiles yet.

- [ ] **Step 3: Extend `TorpedoTube.Fire`**

In `engine/appc/subsystems.py`, find `class TorpedoTube` (around line 580 by current state — confirm with grep). Extend the `Fire` method. The PR 2a body sets `_firing`, decrements `_num_ready`, stamps `_last_fire_time`, auto-clears `_firing`. Add the projectile-spawn block before the auto-clear:

```python
    def Fire(self, target=None, offset=None) -> None:
        if not self.CanFire():
            return
        self._firing = True
        self._target = target
        self._target_offset = offset
        self._num_ready -= 1
        import time as _time
        self._last_fire_time = _time.monotonic()

        # NEW PR 2b: spawn the projectile.
        self._spawn_torpedo()

        # Discrete-shot — auto-stop after launch.
        self._firing = False

    def _spawn_torpedo(self) -> None:
        """Look up the bound projectile script via the parent system property,
        instantiate a Torpedo, call <script>.Create(torpedo) to populate it,
        compute initial velocity (homing if ship has GetTarget, else dumbfire
        from emitter direction), play launch sound.

        Silent no-op when no script is bound — matches BC for unconfigured tubes.
        """
        parent = self.GetParentSubsystem()
        if parent is None:
            return
        parent_prop = parent.GetProperty()
        if parent_prop is None or not hasattr(parent_prop, "GetTorpedoScript"):
            return
        # PR 2b: always slot 0.  Per-tube slot assignment is a future polish item.
        script_name = parent_prop.GetTorpedoScript(0)
        if not script_name:
            return

        import importlib
        try:
            mod = importlib.import_module(script_name)
        except ImportError:
            return  # script missing — silent no-op

        from engine.appc.projectiles import Torpedo, register
        from engine.appc.math import TGPoint3
        from engine.audio.tg_sound import TGSoundManager

        torp = Torpedo()
        source_ship = self._climb_to_ship()
        torp._source_ship = source_ship
        torp._position = self._emitter_world_position()

        mod.Create(torp)

        launch_speed = float(mod.GetLaunchSpeed()) if hasattr(mod, "GetLaunchSpeed") else 0.0

        # Compute initial velocity.
        target_ship = source_ship.GetTarget() if source_ship is not None else None
        if target_ship is not None and not target_ship.IsDead():
            aim_target = (source_ship.GetTargetSubsystem()
                          if hasattr(source_ship, "GetTargetSubsystem")
                             and source_ship.GetTargetSubsystem() is not None
                          else target_ship)
            aim_pt = aim_target.GetWorldLocation()
            direction = aim_pt - torp._position
            length = direction.Length()
            if length > 1e-6:
                torp._velocity = TGPoint3(
                    direction.x / length * launch_speed,
                    direction.y / length * launch_speed,
                    direction.z / length * launch_speed,
                )
            torp._target_ship = target_ship
        else:
            # Dumbfire along emitter local direction rotated by ship.
            forward = self.GetDirection() if hasattr(self, "GetDirection") else TGPoint3(0, 1, 0)
            if forward is None:
                forward = TGPoint3(0, 1, 0)
            # Transform local forward by ship rotation if available.
            if source_ship is not None and hasattr(source_ship, "GetWorldRotation"):
                rot = source_ship.GetWorldRotation()
                world_fwd = TGPoint3(forward.x, forward.y, forward.z)
                world_fwd.MultMatrixLeft(rot)
            else:
                world_fwd = TGPoint3(forward.x, forward.y, forward.z)
            length = world_fwd.Length()
            if length > 1e-6:
                torp._velocity = TGPoint3(
                    world_fwd.x / length * launch_speed,
                    world_fwd.y / length * launch_speed,
                    world_fwd.z / length * launch_speed,
                )
            torp._target_ship = None

        register(torp)

        if hasattr(mod, "GetLaunchSound"):
            sound_name = mod.GetLaunchSound()
            if sound_name:
                TGSoundManager.instance().PlaySound(sound_name)

    def _climb_to_ship(self):
        """Walk GetParentSubsystem chain until we reach the ShipClass."""
        from engine.appc.ships import ShipClass
        node = self.GetParentSubsystem()
        # The parent of a TorpedoTube is its TorpedoSystem; the TorpedoSystem's
        # parent_ship link points to the ShipClass.
        while node is not None:
            if hasattr(node, "GetParentShip") and node.GetParentShip() is not None:
                return node.GetParentShip()
            node = node.GetParentSubsystem() if hasattr(node, "GetParentSubsystem") else None
        return None

    def _emitter_world_position(self):
        """Ship world location + emitter local position rotated into world frame."""
        from engine.appc.math import TGPoint3
        ship = self._climb_to_ship()
        if ship is None:
            return TGPoint3(0, 0, 0)
        ship_pos = ship.GetWorldLocation()
        local = self.GetPosition() if hasattr(self, "GetPosition") else None
        if local is None:
            return TGPoint3(ship_pos.x, ship_pos.y, ship_pos.z)
        if hasattr(ship, "GetWorldRotation"):
            offset = TGPoint3(local.x, local.y, local.z)
            offset.MultMatrixLeft(ship.GetWorldRotation())
            return TGPoint3(ship_pos.x + offset.x,
                            ship_pos.y + offset.y,
                            ship_pos.z + offset.z)
        return TGPoint3(ship_pos.x + local.x,
                        ship_pos.y + local.y,
                        ship_pos.z + local.z)
```

The `GetParentShip` link on `TorpedoSystem` should already exist from PR 1's subsystem tree wiring. If `_parent_ship` isn't set on the system when the tube fires, the test fixture sets it manually.

- [ ] **Step 4: Run tests to verify pass**

```
uv run pytest tests/unit/test_torpedo_tube_fire.py -v
```

Expected: existing PR 2a tests still pass; new tests pass.

If tests fail because the parent system's `_parent_ship` isn't propagated correctly, look at `AddChildSubsystem` in `engine/appc/subsystems.py` and check whether it sets the back-reference. If not, the test fixture in step 1 should `parent._parent_ship = ship` manually.

- [ ] **Step 5: Full regression check**

```
uv run pytest tests/unit/ -x
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/appc/subsystems.py tests/unit/test_torpedo_tube_fire.py
git commit -m "$(cat <<'EOF'
feat(weapons): TorpedoTube.Fire spawns visible projectile

Fire now looks up the parent system's GetTorpedoScript(0), imports
the SDK script (Tactical.Projectiles.PhotonTorpedo or similar),
instantiates a Torpedo, calls <script>.Create(torpedo) to populate
visuals + behaviour, then computes initial velocity:

- Target locked (and not dead) → aim at GetTargetSubsystem() or
  GetTarget() world position; store target on torpedo for homing.
- No target lock → dumbfire along emitter local direction × ship
  world rotation.

Plays <script>.GetLaunchSound() through TGSoundManager.  Silent no-op
when no script is bound for the slot (PR 2b uses slot 0 only; per-tube
slot routing is a future polish item).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `hit_vfx.py` — transient impact sprites

**Files:**
- Create: `engine/appc/hit_vfx.py`
- Create: `tests/unit/test_hit_vfx_lifecycle.py`

Tiny module — single list of `(position, age)` pairs. `spawn(pos)` adds with age 0; `update_ages(dt)` increments and prunes >0.5s; `snapshot()` returns the current list for the renderer push.

### Steps

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_hit_vfx_lifecycle.py`:

```python
"""hit_vfx.spawn / update_ages / snapshot — transient impact sprites."""
import pytest
from engine.appc.math import TGPoint3
from engine.appc.hit_vfx import spawn, update_ages, snapshot, _active


@pytest.fixture(autouse=True)
def clear_registry():
    _active.clear()
    yield
    _active.clear()


def test_spawn_appends_with_age_zero():
    spawn(TGPoint3(1, 2, 3))
    snap = snapshot()
    assert len(snap) == 1
    assert snap[0]["age"] == 0.0
    assert snap[0]["position"].x == 1.0


def test_update_ages_increments_each():
    spawn(TGPoint3(0, 0, 0))
    update_ages(dt=0.1)
    snap = snapshot()
    assert snap[0]["age"] == pytest.approx(0.1)


def test_update_ages_prunes_expired():
    spawn(TGPoint3(0, 0, 0))
    update_ages(dt=0.6)  # > 0.5 lifetime
    assert snapshot() == []


def test_snapshot_returns_copy_not_internal_list():
    spawn(TGPoint3(0, 0, 0))
    snap = snapshot()
    snap.clear()
    assert len(snapshot()) == 1  # internal not affected


def test_multiple_spawns_independent():
    spawn(TGPoint3(1, 0, 0))
    update_ages(dt=0.3)
    spawn(TGPoint3(2, 0, 0))
    update_ages(dt=0.3)
    # First one is now age 0.6 (pruned), second is 0.3.
    snap = snapshot()
    assert len(snap) == 1
    assert snap[0]["position"].x == 2.0
    assert snap[0]["age"] == pytest.approx(0.3)
```

- [ ] **Step 2: Run to verify failure**

```
uv run pytest tests/unit/test_hit_vfx_lifecycle.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create `engine/appc/hit_vfx.py`**

```python
"""Transient impact-VFX registry.  Tiny — just a list of (position, age)
pairs with a 0.5s lifetime.  Host_loop's per-frame combat advance calls
spawn() on each torpedo impact and pushes snapshot() to the renderer.
"""
from engine.appc.math import TGPoint3


_LIFETIME = 0.5  # seconds


# Internal storage: list of dicts with "position" and "age" keys.
# Dict shape matches what the renderer binding expects.
_active: list[dict] = []


def spawn(position: TGPoint3) -> None:
    """Register a new hit VFX at `position` with age 0."""
    _active.append({"position": position, "age": 0.0})


def update_ages(dt: float) -> None:
    """Increment ages by dt; prune expired (>= _LIFETIME)."""
    dt = float(dt)
    survivors = []
    for entry in _active:
        new_age = entry["age"] + dt
        if new_age < _LIFETIME:
            entry["age"] = new_age
            survivors.append(entry)
    _active.clear()
    _active.extend(survivors)


def snapshot() -> list[dict]:
    """Return a shallow copy of active VFX for renderer push."""
    return list(_active)
```

- [ ] **Step 4: Run tests to verify pass**

```
uv run pytest tests/unit/test_hit_vfx_lifecycle.py -v
```

Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/appc/hit_vfx.py tests/unit/test_hit_vfx_lifecycle.py
git commit -m "$(cat <<'EOF'
feat(combat): hit_vfx — transient impact sprite registry

Module-level list of (position, age) pairs with a 0.5s lifetime.
spawn() adds at age 0, update_ages(dt) increments + prunes, snapshot()
copies the list for the renderer push.  Task 8 wires it into
host_loop._advance_combat; Task 10 renders the sprites.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `host_loop._advance_combat` + FriendlyFireHandler registration

**Files:**
- Modify: `engine/host_loop.py` — add `_advance_combat`, wire into frame loop, register FriendlyFireHandler in bootstrap.

### Steps

- [ ] **Step 1: Add `_advance_combat` to `host_loop.py`**

Define at module scope (somewhere near `_advance_weapons`):

```python
def _advance_combat(ships, dt: float, host=None) -> None:
    """Per-frame torpedo motion + collision + damage + renderer push.

    Walks the active torpedo registry, advances motion, routes hits
    through combat.apply_hit (which broadcasts WeaponHitEvent), spawns
    hit VFX, ages out expired VFX, and pushes current torpedo + hit-VFX
    lists to the renderer via host bindings.

    `host` is the _open_stbc_host module (the binding from
    host_bindings.cc).  When None (headless tests), the renderer pushes
    are skipped — combat logic still runs.
    """
    from engine.appc import projectiles, hit_vfx
    from engine.appc.combat import apply_hit

    ships_list = list(ships)
    hits = projectiles.update_all(dt, ships_list)
    for torpedo, ship, subsystem in hits:
        apply_hit(ship, torpedo._damage, torpedo._position,
                  source=torpedo._source_ship, subsystem=subsystem)
        hit_vfx.spawn(torpedo._position)

    hit_vfx.update_ages(dt)

    # Push to renderer if host has the bindings.
    if host is not None and hasattr(host, "set_torpedoes"):
        host.set_torpedoes(_build_torpedo_render_data())
    if host is not None and hasattr(host, "set_hit_vfx"):
        host.set_hit_vfx(_build_hit_vfx_render_data())


def _build_torpedo_render_data():
    """Convert the projectiles._active list into the dict shape
    set_torpedoes expects.  Renderer reads position + visual fields.
    """
    from engine.appc import projectiles
    out = []
    for t in projectiles._active:
        out.append({
            "position":      (t._position.x, t._position.y, t._position.z),
            "core_texture":  t._core_texture,
            "core_color":    _color_tuple(t._core_color),
            "core_size_a":   t._core_size_a,
            "core_size_b":   t._core_size_b,
            "glow_texture":  t._glow_texture,
            "glow_color":    _color_tuple(t._glow_color),
            "glow_size_a":   t._glow_size_a,
            "glow_size_b":   t._glow_size_b,
            "glow_size_c":   t._glow_size_c,
            "flares_texture": t._flares_texture,
            "flares_color":  _color_tuple(t._flares_color),
            "num_flares":    t._num_flares,
            "flares_size_a": t._flares_size_a,
            "flares_size_b": t._flares_size_b,
        })
    return out


def _build_hit_vfx_render_data():
    from engine.appc import hit_vfx
    out = []
    for entry in hit_vfx.snapshot():
        pos = entry["position"]
        out.append({
            "position": (pos.x, pos.y, pos.z),
            "age":      entry["age"],
        })
    return out


def _color_tuple(color) -> tuple:
    """TGColorA → (r, g, b, a) tuple, or (1,1,1,1) when None."""
    if color is None:
        return (1.0, 1.0, 1.0, 1.0)
    return (color.r, color.g, color.b, color.a)
```

- [ ] **Step 2: Wire `_advance_combat` into the frame loop**

In the existing frame loop (look for `_advance_weapons(_all_ships_for_tick(), dt)` from PR 2a), add immediately after:

```python
                _advance_weapons(_all_ships_for_tick(), dt)
                _advance_combat(_all_ships_for_tick(), dt, host=_h)
```

- [ ] **Step 3: Register FriendlyFireHandler in `_bootstrap_firing_pipeline`**

In `_bootstrap_firing_pipeline` (existing from PR 2a), after the `LoadTacticalSounds.LoadSounds()` block, add:

```python
    # Wire FriendlyFireHandler so the player damaging a friendly NPC
    # triggers XO dialogue (existing SDK behaviour).  Mission scripts
    # set up the mission object that the handler reads; we just wire the
    # broadcast.
    try:
        import MissionLib
        import App
        # Bind via the current mission (resolved when ET_WEAPON_HIT
        # actually fires — MissionLib reads g_kUtopiaModule's mission).
        App.g_kEventManager.AddBroadcastPythonFuncHandler(
            App.ET_WEAPON_HIT, None,
            "MissionLib.FriendlyFireHandler",
        )
    except (ImportError, AttributeError) as exc:
        print(f"WARNING: failed to register FriendlyFireHandler: {exc}", flush=True)
```

- [ ] **Step 4: Sanity-check the module loads**

```
uv run python -c "import engine.host_loop; print('host_loop import OK')"
```

Expected: prints "host_loop import OK". If a NameError or ImportError surfaces, fix the import order.

- [ ] **Step 5: Full unit suite**

```
uv run pytest tests/unit/ -x
```

Expected: PASS. No new unit tests in this task — the integration tests (Task 11) exercise this glue end-to-end.

- [ ] **Step 6: Commit**

```bash
git add engine/host_loop.py
git commit -m "$(cat <<'EOF'
feat(host_loop): per-frame combat advance + FriendlyFireHandler

_advance_combat(ships, dt, host) walks active torpedoes via
projectiles.update_all, routes each hit through combat.apply_hit
(which broadcasts WeaponHitEvent), spawns hit_vfx sprites, ages out
expired VFX, then pushes current torpedo + hit_vfx lists to the
renderer via the new host bindings (Tasks 9 + 10).

_bootstrap_firing_pipeline extends to register MissionLib.
FriendlyFireHandler as a broadcast handler for ET_WEAPON_HIT so the
SDK's friendly-fire dialogue chain fires when the player damages a
friendly NPC.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Native — `torpedo_pass` renderer

**Files:**
- Create: `native/src/renderer/include/renderer/torpedo_pass.h`
- Create: `native/src/renderer/torpedo_pass.cc`
- Create: `native/src/renderer/shaders/torpedo.vert`
- Create: `native/src/renderer/shaders/torpedo.frag`
- Modify: `native/src/renderer/pipeline.cc` — schedule the pass.
- Modify: `native/src/host/host_bindings.cc` — `set_torpedoes` Python binding.

Per-torpedo: three additive billboards (core + glow + flares) at the same world position. Camera-aligned quads, additive blend, depth-test on / depth-write off. Texture loading + caching by file path.

This is a meaty C++ task. Follow the existing `lens_flare_pass.cc` pattern — it's the closest existing precedent (camera-aligned additive billboards with per-instance data pushed each frame).

### Steps

- [ ] **Step 1: Read the existing lens flare pass for context**

```
cat native/src/renderer/lens_flare_pass.cc
cat native/src/renderer/include/renderer/lens_flare_pass.h
cat native/src/renderer/shaders/lens_flare.vert
cat native/src/renderer/shaders/lens_flare.frag
```

Note the patterns:
- Per-frame `set_lens_flares(list_of_dicts)` host binding pushes data into a `g_lens_flares` vector.
- Renderer reads `g_lens_flares` in its `frame()` step, draws each as an additive billboard.
- Shader takes a per-vertex offset, computes camera-aligned quad corners, samples texture × color.

The torpedo pass mirrors this with three textures stacked instead of one.

- [ ] **Step 2: Write the vertex shader**

Create `native/src/renderer/shaders/torpedo.vert`:

```glsl
#version 330 core
layout(location = 0) in vec2 a_corner;   // unit-quad corner: (-1,-1)..(+1,+1)

uniform mat4 u_view_proj;
uniform vec3 u_camera_right;             // camera basis in world space
uniform vec3 u_camera_up;
uniform vec3 u_world_position;
uniform float u_size;                    // quad half-size in world units

out vec2 v_uv;

void main() {
    vec3 world_pos = u_world_position
        + u_camera_right * (a_corner.x * u_size)
        + u_camera_up    * (a_corner.y * u_size);
    gl_Position = u_view_proj * vec4(world_pos, 1.0);
    v_uv = a_corner * 0.5 + 0.5;
}
```

- [ ] **Step 3: Write the fragment shader**

Create `native/src/renderer/shaders/torpedo.frag`:

```glsl
#version 330 core
in vec2 v_uv;

uniform sampler2D u_texture;
uniform vec4 u_tint;

out vec4 frag_color;

void main() {
    vec4 sampled = texture(u_texture, v_uv);
    frag_color = sampled * u_tint;
}
```

- [ ] **Step 4: Write the header**

Create `native/src/renderer/include/renderer/torpedo_pass.h`:

```cpp
// native/src/renderer/include/renderer/torpedo_pass.h
#pragma once

#include <string>
#include <vector>

namespace renderer {

struct TorpedoRenderData {
    float position[3];
    std::string core_texture;
    float core_color[4];
    float core_size_a;
    float core_size_b;
    std::string glow_texture;
    float glow_color[4];
    float glow_size_a;
    float glow_size_b;
    float glow_size_c;
    std::string flares_texture;
    float flares_color[4];
    int   num_flares;
    float flares_size_a;
    float flares_size_b;
};

class TorpedoPass {
public:
    TorpedoPass();
    ~TorpedoPass();

    /// Set the current frame's torpedo list.  Replaces the previous list.
    void set_torpedoes(std::vector<TorpedoRenderData> torps) noexcept;

    /// Render all active torpedoes.  Call after lens flares + before HUD.
    /// view_proj is the combined view*projection matrix; camera_right and
    /// camera_up are unit basis vectors in world space.
    void frame(const float view_proj[16],
               const float camera_right[3],
               const float camera_up[3]) noexcept;

private:
    std::vector<TorpedoRenderData> torpedoes_;
    unsigned int program_     = 0;
    unsigned int quad_vao_    = 0;
    unsigned int quad_vbo_    = 0;
    // Texture cache keyed by file path.
    void* texture_cache_impl_ = nullptr;

    unsigned int load_texture(const std::string& path) noexcept;
    void         draw_billboard(unsigned int tex_id,
                                const float position[3],
                                const float color[4],
                                float size,
                                const float view_proj[16],
                                const float camera_right[3],
                                const float camera_up[3]) noexcept;
};

}  // namespace renderer
```

- [ ] **Step 5: Write the implementation**

Create `native/src/renderer/torpedo_pass.cc`. Mirror the structure of `lens_flare_pass.cc` — same OpenGL setup pattern, same shader compile path. The key differences:

- Three billboards per torpedo instead of one.
- Size is `core_size_a * core_size_b` (core), `glow_size_a` (glow), `flares_size_a` (flares). The SDK's exact size formula is encoded in the engine's `CreateTorpedoModel` params; for PR 2b a sensible interpretation is `size = a × b` for the size_a + size_b pairs and `size_a` alone for the single-size cases. This is the open question #5 from the spec — tune by feel during implementation.

I won't include the full ~250 lines of OpenGL boilerplate here; copy from `lens_flare_pass.cc` and adapt the structure. Key parts to NOT skip:

```cpp
// Pseudo-structure of torpedo_pass.cc:

#include "renderer/torpedo_pass.h"
#include "renderer/shader.h"  // existing helper for compile/link
#include <GL/gl3w.h>
#include <unordered_map>

namespace renderer {

namespace {
// Embedded shader strings.  pipeline.cc has a similar pattern using
// embed_shader().  Match it.
const char* kVertSource = R"GLSL(
#version 330 core
... (contents of torpedo.vert) ...
)GLSL";

const char* kFragSource = R"GLSL(
#version 330 core
... (contents of torpedo.frag) ...
)GLSL";
}

struct TorpedoPass::TextureCache {
    std::unordered_map<std::string, unsigned int> by_path;
};

TorpedoPass::TorpedoPass() {
    // Compile + link shader program.
    program_ = compile_program(kVertSource, kFragSource);  // existing helper
    // Set up unit-quad VAO/VBO.
    static const float kQuadVerts[] = {
        -1.0f, -1.0f,
        +1.0f, -1.0f,
        +1.0f, +1.0f,
        -1.0f, -1.0f,
        +1.0f, +1.0f,
        -1.0f, +1.0f,
    };
    glGenVertexArrays(1, &quad_vao_);
    glGenBuffers(1, &quad_vbo_);
    glBindVertexArray(quad_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, quad_vbo_);
    glBufferData(GL_ARRAY_BUFFER, sizeof(kQuadVerts), kQuadVerts, GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * sizeof(float), nullptr);
    glBindVertexArray(0);
    texture_cache_impl_ = new TextureCache;
}

TorpedoPass::~TorpedoPass() {
    if (texture_cache_impl_) {
        auto* cache = static_cast<TextureCache*>(texture_cache_impl_);
        for (auto& [_, tex_id] : cache->by_path) {
            glDeleteTextures(1, &tex_id);
        }
        delete cache;
    }
    if (quad_vbo_) glDeleteBuffers(1, &quad_vbo_);
    if (quad_vao_) glDeleteVertexArrays(1, &quad_vao_);
    if (program_)  glDeleteProgram(program_);
}

void TorpedoPass::set_torpedoes(std::vector<TorpedoRenderData> torps) noexcept {
    torpedoes_ = std::move(torps);
}

unsigned int TorpedoPass::load_texture(const std::string& path) noexcept {
    auto* cache = static_cast<TextureCache*>(texture_cache_impl_);
    auto it = cache->by_path.find(path);
    if (it != cache->by_path.end()) return it->second;
    // Load via the existing TGA loader (e.g. assets/tga_loader.h).
    // Fall back to a 1×1 white texture if load fails.
    unsigned int tex_id = load_tga(path);  // existing helper, see assets/
    if (tex_id == 0) {
        // 1×1 white fallback.
        glGenTextures(1, &tex_id);
        glBindTexture(GL_TEXTURE_2D, tex_id);
        unsigned char white[4] = {255, 255, 255, 255};
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 1, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, white);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    }
    cache->by_path[path] = tex_id;
    return tex_id;
}

void TorpedoPass::frame(const float view_proj[16],
                        const float camera_right[3],
                        const float camera_up[3]) noexcept {
    if (torpedoes_.empty()) return;
    glUseProgram(program_);
    glBindVertexArray(quad_vao_);

    // Additive blend, depth-test on, depth-write off.
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE);
    glDepthMask(GL_FALSE);
    glEnable(GL_DEPTH_TEST);

    for (const auto& t : torpedoes_) {
        // Three layers in additive order — glow is largest+dimmest, then
        // flares, then core (smallest+brightest on top).
        if (!t.glow_texture.empty()) {
            draw_billboard(load_texture(t.glow_texture), t.position,
                           t.glow_color, t.glow_size_a,
                           view_proj, camera_right, camera_up);
        }
        if (!t.flares_texture.empty()) {
            draw_billboard(load_texture(t.flares_texture), t.position,
                           t.flares_color, t.flares_size_a,
                           view_proj, camera_right, camera_up);
        }
        if (!t.core_texture.empty()) {
            draw_billboard(load_texture(t.core_texture), t.position,
                           t.core_color, t.core_size_a * t.core_size_b,
                           view_proj, camera_right, camera_up);
        }
    }

    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);
    glBindVertexArray(0);
    glUseProgram(0);
}

void TorpedoPass::draw_billboard(unsigned int tex_id,
                                  const float position[3],
                                  const float color[4],
                                  float size,
                                  const float view_proj[16],
                                  const float camera_right[3],
                                  const float camera_up[3]) noexcept {
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, tex_id);
    GLint loc = glGetUniformLocation(program_, "u_texture"); if (loc >= 0) glUniform1i(loc, 0);
    loc = glGetUniformLocation(program_, "u_tint");         if (loc >= 0) glUniform4fv(loc, 1, color);
    loc = glGetUniformLocation(program_, "u_world_position");if (loc >= 0) glUniform3fv(loc, 1, position);
    loc = glGetUniformLocation(program_, "u_camera_right"); if (loc >= 0) glUniform3fv(loc, 1, camera_right);
    loc = glGetUniformLocation(program_, "u_camera_up");    if (loc >= 0) glUniform3fv(loc, 1, camera_up);
    loc = glGetUniformLocation(program_, "u_view_proj");    if (loc >= 0) glUniformMatrix4fv(loc, 1, GL_FALSE, view_proj);
    loc = glGetUniformLocation(program_, "u_size");         if (loc >= 0) glUniform1f(loc, size);
    glDrawArrays(GL_TRIANGLES, 0, 6);
}

}  // namespace renderer
```

**Important**: cache uniform locations once at program-link time rather than per-draw `glGetUniformLocation` — the snippet above is hot-loop wasteful. Look at how `lens_flare_pass.cc` caches them and follow that pattern.

- [ ] **Step 6: Wire into `pipeline.cc`**

In `native/src/renderer/pipeline.cc`, find where the existing passes are constructed and called. Add a `TorpedoPass` member to the pipeline struct, construct it alongside the other passes, and call its `frame(...)` after lens flares but before any HUD/UI overlay.

The exact location depends on the existing pipeline shape — read `pipeline.cc` to find the right insertion point.

- [ ] **Step 7: Add `set_torpedoes` host binding**

In `native/src/host/host_bindings.cc`, near the existing `set_lens_flares` binding:

```cpp
m.def("set_torpedoes",
      [](py::list torps) {
          if (!g_pipeline) return;
          std::vector<renderer::TorpedoRenderData> data;
          data.reserve(torps.size());
          for (auto handle : torps) {
              py::dict d = handle.cast<py::dict>();
              renderer::TorpedoRenderData t;
              auto pos = d["position"].cast<std::tuple<float, float, float>>();
              t.position[0] = std::get<0>(pos);
              t.position[1] = std::get<1>(pos);
              t.position[2] = std::get<2>(pos);
              t.core_texture = d["core_texture"].cast<std::string>();
              auto cc = d["core_color"].cast<std::tuple<float, float, float, float>>();
              t.core_color[0] = std::get<0>(cc); t.core_color[1] = std::get<1>(cc);
              t.core_color[2] = std::get<2>(cc); t.core_color[3] = std::get<3>(cc);
              t.core_size_a = d["core_size_a"].cast<float>();
              t.core_size_b = d["core_size_b"].cast<float>();
              t.glow_texture = d["glow_texture"].cast<std::string>();
              auto gc = d["glow_color"].cast<std::tuple<float, float, float, float>>();
              t.glow_color[0] = std::get<0>(gc); t.glow_color[1] = std::get<1>(gc);
              t.glow_color[2] = std::get<2>(gc); t.glow_color[3] = std::get<3>(gc);
              t.glow_size_a = d["glow_size_a"].cast<float>();
              t.glow_size_b = d["glow_size_b"].cast<float>();
              t.glow_size_c = d["glow_size_c"].cast<float>();
              t.flares_texture = d["flares_texture"].cast<std::string>();
              auto fc = d["flares_color"].cast<std::tuple<float, float, float, float>>();
              t.flares_color[0] = std::get<0>(fc); t.flares_color[1] = std::get<1>(fc);
              t.flares_color[2] = std::get<2>(fc); t.flares_color[3] = std::get<3>(fc);
              t.num_flares     = d["num_flares"].cast<int>();
              t.flares_size_a  = d["flares_size_a"].cast<float>();
              t.flares_size_b  = d["flares_size_b"].cast<float>();
              data.push_back(std::move(t));
          }
          g_pipeline->torpedo_pass().set_torpedoes(std::move(data));
      },
      "Push current frame's torpedo list to the renderer.");
```

(Adjust `g_pipeline->torpedo_pass()` to whatever accessor pattern `pipeline.cc` uses for the other passes.)

- [ ] **Step 8: Update CMakeLists.txt**

Add `native/src/renderer/torpedo_pass.cc` to the renderer source list. CMake will pick up the `.h` automatically if it's in a tracked include directory. Re-run cmake configure if necessary.

- [ ] **Step 9: Rebuild**

```
cmake -B build -S . && cmake --build build -j
```

Expected: clean build. Fix any compile errors before continuing.

- [ ] **Step 10: Smoke-test the binding**

```bash
uv run python -c "
import sys
sys.path.insert(0, 'build/python')
import _open_stbc_host as h
print('set_torpedoes:', hasattr(h, 'set_torpedoes'))
"
```

Expected: `set_torpedoes: True`.

- [ ] **Step 11: Commit**

```bash
git add native/src/renderer/torpedo_pass.cc \
        native/src/renderer/include/renderer/torpedo_pass.h \
        native/src/renderer/shaders/torpedo.vert \
        native/src/renderer/shaders/torpedo.frag \
        native/src/renderer/pipeline.cc \
        native/src/host/host_bindings.cc \
        CMakeLists.txt   # if modified
git commit -m "$(cat <<'EOF'
feat(renderer): torpedo billboard composite pass

Per-torpedo: three additive billboards (glow then flares then core)
at the same world position.  Camera-aligned quads, depth-test on /
depth-write off, additive blend.  Texture loading cached by file path
(same .tga loader used by other passes); 1×1 white fallback when a
texture file is missing.

set_torpedoes(list_of_dicts) host binding pushes per-frame data from
host_loop._advance_combat into TorpedoPass.  Renders after lens flares.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Native — `hit_vfx_pass` renderer

**Files:**
- Create: `native/src/renderer/include/renderer/hit_vfx_pass.h`
- Create: `native/src/renderer/hit_vfx_pass.cc`
- Create: `native/src/renderer/shaders/hit_vfx.vert`
- Create: `native/src/renderer/shaders/hit_vfx.frag`
- Modify: `native/src/renderer/pipeline.cc` — schedule the pass.
- Modify: `native/src/host/host_bindings.cc` — `set_hit_vfx` Python binding.

Single additive billboard per active hit VFX. Size scales 0→1 over first 100ms, alpha fades 1→0 over next 400ms. Uses `data/Textures/Tactical/TorpedoFlares.tga` as the impact texture (placeholder; PR 2c may swap).

### Steps

- [ ] **Step 1: Shaders**

Create `native/src/renderer/shaders/hit_vfx.vert` (identical to torpedo.vert — same billboard shape):

```glsl
#version 330 core
layout(location = 0) in vec2 a_corner;

uniform mat4  u_view_proj;
uniform vec3  u_camera_right;
uniform vec3  u_camera_up;
uniform vec3  u_world_position;
uniform float u_size;

out vec2 v_uv;

void main() {
    vec3 world_pos = u_world_position
        + u_camera_right * (a_corner.x * u_size)
        + u_camera_up    * (a_corner.y * u_size);
    gl_Position = u_view_proj * vec4(world_pos, 1.0);
    v_uv = a_corner * 0.5 + 0.5;
}
```

Create `native/src/renderer/shaders/hit_vfx.frag`:

```glsl
#version 330 core
in vec2 v_uv;

uniform sampler2D u_texture;
uniform float     u_alpha;

out vec4 frag_color;

void main() {
    vec4 sampled = texture(u_texture, v_uv);
    frag_color = vec4(sampled.rgb, sampled.a * u_alpha);
}
```

- [ ] **Step 2: Header**

Create `native/src/renderer/include/renderer/hit_vfx_pass.h`:

```cpp
#pragma once

#include <vector>

namespace renderer {

struct HitVfxRenderData {
    float position[3];
    float age;        // seconds since spawn (Python engine clamps lifetime ≤ 0.5)
};

class HitVfxPass {
public:
    HitVfxPass();
    ~HitVfxPass();

    void set_hit_vfx(std::vector<HitVfxRenderData> vfx) noexcept;

    void frame(const float view_proj[16],
               const float camera_right[3],
               const float camera_up[3]) noexcept;

private:
    std::vector<HitVfxRenderData> vfx_;
    unsigned int program_   = 0;
    unsigned int quad_vao_  = 0;
    unsigned int quad_vbo_  = 0;
    unsigned int texture_   = 0;
};

}  // namespace renderer
```

- [ ] **Step 3: Implementation**

Create `native/src/renderer/hit_vfx_pass.cc`. Similar structure to `torpedo_pass.cc` but simpler:
- Single texture (TorpedoFlares.tga) loaded at construction.
- Per-VFX: size = ease-in over first 0.1s, alpha = 1 - max(0, (age - 0.1) / 0.4).
- Additive blend, depth-test on, depth-write off.

```cpp
#include "renderer/hit_vfx_pass.h"
#include "renderer/shader.h"
#include <GL/gl3w.h>
#include <algorithm>

namespace renderer {

namespace {
constexpr float kPeakSize  = 5.0f;   // world-units half-size at full expansion
constexpr float kSpawnDur  = 0.1f;
constexpr float kFadeDur   = 0.4f;

const char* kVertSrc = R"GLSL(
... contents of hit_vfx.vert ...
)GLSL";
const char* kFragSrc = R"GLSL(
... contents of hit_vfx.frag ...
)GLSL";
}

HitVfxPass::HitVfxPass() {
    program_ = compile_program(kVertSrc, kFragSrc);
    static const float kQuad[] = {
        -1.f, -1.f,  +1.f, -1.f,  +1.f, +1.f,
        -1.f, -1.f,  +1.f, +1.f,  -1.f, +1.f,
    };
    glGenVertexArrays(1, &quad_vao_);
    glGenBuffers(1, &quad_vbo_);
    glBindVertexArray(quad_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, quad_vbo_);
    glBufferData(GL_ARRAY_BUFFER, sizeof(kQuad), kQuad, GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * sizeof(float), nullptr);
    glBindVertexArray(0);
    texture_ = load_tga("data/Textures/Tactical/TorpedoFlares.tga");
}

HitVfxPass::~HitVfxPass() {
    if (texture_)  glDeleteTextures(1, &texture_);
    if (quad_vbo_) glDeleteBuffers(1, &quad_vbo_);
    if (quad_vao_) glDeleteVertexArrays(1, &quad_vao_);
    if (program_)  glDeleteProgram(program_);
}

void HitVfxPass::set_hit_vfx(std::vector<HitVfxRenderData> vfx) noexcept {
    vfx_ = std::move(vfx);
}

void HitVfxPass::frame(const float view_proj[16],
                       const float camera_right[3],
                       const float camera_up[3]) noexcept {
    if (vfx_.empty() || !texture_) return;

    glUseProgram(program_);
    glBindVertexArray(quad_vao_);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, texture_);

    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE);
    glDepthMask(GL_FALSE);
    glEnable(GL_DEPTH_TEST);

    GLint loc_tex   = glGetUniformLocation(program_, "u_texture");
    GLint loc_alpha = glGetUniformLocation(program_, "u_alpha");
    GLint loc_size  = glGetUniformLocation(program_, "u_size");
    GLint loc_pos   = glGetUniformLocation(program_, "u_world_position");
    GLint loc_right = glGetUniformLocation(program_, "u_camera_right");
    GLint loc_up    = glGetUniformLocation(program_, "u_camera_up");
    GLint loc_mvp   = glGetUniformLocation(program_, "u_view_proj");

    if (loc_tex   >= 0) glUniform1i(loc_tex, 0);
    if (loc_right >= 0) glUniform3fv(loc_right, 1, camera_right);
    if (loc_up    >= 0) glUniform3fv(loc_up,    1, camera_up);
    if (loc_mvp   >= 0) glUniformMatrix4fv(loc_mvp, 1, GL_FALSE, view_proj);

    for (const auto& v : vfx_) {
        float age = std::max(0.0f, v.age);
        float size_t  = std::min(1.0f, age / kSpawnDur);
        float fade_t  = std::max(0.0f, std::min(1.0f, (age - kSpawnDur) / kFadeDur));
        float size    = kPeakSize * size_t;
        float alpha   = 1.0f - fade_t;
        if (loc_size >= 0)  glUniform1f(loc_size, size);
        if (loc_alpha >= 0) glUniform1f(loc_alpha, alpha);
        if (loc_pos >= 0)   glUniform3fv(loc_pos, 1, v.position);
        glDrawArrays(GL_TRIANGLES, 0, 6);
    }

    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);
    glBindVertexArray(0);
    glUseProgram(0);
}

}  // namespace renderer
```

- [ ] **Step 4: Wire into pipeline.cc**

Add `HitVfxPass` member to the pipeline. Call its `frame(...)` after `TorpedoPass` (so explosion sprites overlay torpedoes).

- [ ] **Step 5: Add `set_hit_vfx` host binding**

In `host_bindings.cc`:

```cpp
m.def("set_hit_vfx",
      [](py::list vfx) {
          if (!g_pipeline) return;
          std::vector<renderer::HitVfxRenderData> data;
          data.reserve(vfx.size());
          for (auto handle : vfx) {
              py::dict d = handle.cast<py::dict>();
              renderer::HitVfxRenderData v;
              auto pos = d["position"].cast<std::tuple<float, float, float>>();
              v.position[0] = std::get<0>(pos);
              v.position[1] = std::get<1>(pos);
              v.position[2] = std::get<2>(pos);
              v.age = d["age"].cast<float>();
              data.push_back(v);
          }
          g_pipeline->hit_vfx_pass().set_hit_vfx(std::move(data));
      },
      "Push current frame's hit-VFX list (position + age).");
```

- [ ] **Step 6: Update CMakeLists.txt + rebuild**

```
cmake -B build -S . && cmake --build build -j
```

Expected: clean build.

- [ ] **Step 7: Smoke-test**

```bash
uv run python -c "
import sys
sys.path.insert(0, 'build/python')
import _open_stbc_host as h
print('set_hit_vfx:', hasattr(h, 'set_hit_vfx'))
"
```

Expected: `True`.

- [ ] **Step 8: Full unit suite (sanity)**

```
uv run pytest tests/unit/ -x
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add native/src/renderer/hit_vfx_pass.cc \
        native/src/renderer/include/renderer/hit_vfx_pass.h \
        native/src/renderer/shaders/hit_vfx.vert \
        native/src/renderer/shaders/hit_vfx.frag \
        native/src/renderer/pipeline.cc \
        native/src/host/host_bindings.cc \
        CMakeLists.txt   # if modified
git commit -m "$(cat <<'EOF'
feat(renderer): hit_vfx — transient impact flare pass

Single additive billboard per active hit VFX.  Size eases 0→1 over
the first 100ms; alpha fades 1→0 over the next 400ms.  Uses
TorpedoFlares.tga as the impact sprite (placeholder; PR 2c may swap
in a proper explosion texture).

set_hit_vfx(list_of_{position, age}) host binding pushes per-frame
data from host_loop._advance_combat (which ages the entries via
hit_vfx.update_ages each frame).  Renders after torpedo pass.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: End-to-end integration tests

**Files:**
- Create: `tests/integration/test_torpedo_lock_homes_to_target.py`
- Create: `tests/integration/test_torpedo_no_lock_dumbfires.py`
- Create: `tests/integration/test_torpedo_targets_subsystem.py`
- Create: `tests/integration/test_friendly_fire_handler.py`
- Create: `tests/integration/test_weapon_hit_event_dispatched.py`

These exercise the full Python chain from `OnKeyDown(WC_RBUTTON)` through to `_advance_combat` applying damage. Native renderer not involved (we use a fake host that records the calls).

### Steps

- [ ] **Step 1: Write the fixture helper**

Create `tests/integration/conftest.py` (or extend existing if present). Add a Galaxy-loadout fixture similar to PR 2a's pattern but extended for combat:

```python
"""Shared fixtures for PR 2b integration tests.  Loads Galaxy + sets up
the input pipeline + ammo + a configurable target ship."""
import importlib
import sys
from unittest.mock import MagicMock

import pytest
import App
from engine.appc.ships import ShipClass, ShipClass_Create
from engine.appc.math import TGPoint3


def _setup_input_chain(ship):
    App.Game_GetCurrentPlayer = lambda: ship
    tcw = App.TacticalControlWindow_GetTacticalControlWindow()
    App.g_kKeyboardBinding.SetDefaultDestination(tcw)
    import DefaultKeyboardBinding
    DefaultKeyboardBinding.Initialize()
    import TacticalInterfaceHandlers
    TacticalInterfaceHandlers.Initialize(tcw)


def _load_galaxy_hardpoint(ship):
    App.g_kModelPropertyManager.ClearLocalTemplates()
    mod_name = "ships.Hardpoints.galaxy"
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
    else:
        importlib.import_module(mod_name)
    mod = sys.modules[mod_name]
    mod.LoadPropertySet(ship.GetPropertySet())
    ship.SetupProperties()
    # The Galaxy hardpoint binds Tactical.Projectiles.PhotonTorpedo to slot 0
    # via SetTorpedoScript — confirm it landed.
    torps = ship.GetTorpedoSystem()
    assert torps is not None
    return ship


@pytest.fixture
def galaxy_red():
    """Galaxy at RED alert with hardpoint loaded."""
    from engine.appc import projectiles, hit_vfx
    projectiles._active.clear()
    hit_vfx._active.clear()

    ship = ShipClass_Create("Galaxy")
    _load_galaxy_hardpoint(ship)
    _setup_input_chain(ship)
    ship.SetAlertLevel(ShipClass.RED_ALERT)
    ship.SetWorldLocation(TGPoint3(0, 0, 0))

    yield ship

    projectiles._active.clear()
    hit_vfx._active.clear()
    App.g_kModelPropertyManager.ClearLocalTemplates()
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]


@pytest.fixture
def target_ship_at(galaxy_red):
    """Factory: returns a function that creates a stub target ship at
    a given world position with hull, shields, and adds it to the active
    set for collision detection."""
    def make(x, y, z, hull_max=10000.0, shields_strength=0.0, radius=20.0):
        from engine.appc.ships import ShipClass_Create
        from engine.appc.subsystems import HullSubsystem
        tgt = ShipClass_Create("Target")
        hull = HullSubsystem("Hull")
        hull.SetMaxCondition(hull_max)
        tgt._hull = hull
        tgt.SetWorldLocation(TGPoint3(x, y, z))
        tgt.SetRadius(radius) if hasattr(tgt, "SetRadius") else None
        if shields_strength > 0.0:
            from engine.appc.subsystems import ShieldSubsystem
            from engine.appc.properties import ShieldProperty
            shields = ShieldSubsystem("Shields")
            for f in range(ShieldProperty.NUM_SHIELDS):
                shields.SetMaxShields(f, shields_strength)
            tgt._shield_subsystem = shields
        return tgt
    return make
```

Adjust the `tgt.SetRadius(...)` line if `ShipClass` doesn't expose that setter — fall back to `tgt._radius = radius` directly.

- [ ] **Step 2: Test `torpedo_lock_homes_to_target.py`**

Create `tests/integration/test_torpedo_lock_homes_to_target.py`:

```python
"""End-to-end: Galaxy at RED + locked target ahead.  Right-click →
torpedo's initial velocity points at target.  After several ticks
position is closer to target.  Eventually collides; target hull
condition decreases.
"""
from unittest.mock import patch

import App
from engine.appc import projectiles
from engine.appc.math import TGPoint3
from engine.host_loop import _advance_combat


def test_torpedo_homes_to_target_and_damages_hull(galaxy_red, target_ship_at):
    ship = galaxy_red
    target = target_ship_at(0, 200, 0, hull_max=10000.0, shields_strength=0.0)
    ship._target = target

    initial_hull = target.GetHull().GetCondition()

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        App.g_kInputManager.OnKeyDown(App.WC_RBUTTON)
        App.g_kInputManager.OnKeyUp(App.WC_RBUTTON)

    # Should have spawned one torpedo.
    assert len(projectiles._active) == 1
    torp = projectiles._active[0]
    # Initial velocity points roughly +Y.
    assert torp._velocity.y > 0.0
    assert torp._target_ship is target

    # Tick 30 frames at 0.1s → 3s real elapsed.  Torpedo at ~57 units/s
    # (PhotonTorpedo.GetLaunchSpeed=19, * some scalar) should hit by then.
    for _ in range(30):
        _advance_combat([ship, target], dt=0.1)
        if len(projectiles._active) == 0:
            break

    final_hull = target.GetHull().GetCondition()
    assert final_hull < initial_hull
    assert len(projectiles._active) == 0  # torpedo expired on impact
```

- [ ] **Step 3: Test `torpedo_no_lock_dumbfires.py`**

```python
"""End-to-end: Galaxy at RED + no target.  Right-click → torpedo flies
along emitter direction.  No homing.  Expires on TTL without hitting
anything when there's no ship in front.
"""
from unittest.mock import patch

import App
from engine.appc import projectiles
from engine.host_loop import _advance_combat


def test_dumbfire_no_target_torpedo_expires_on_ttl(galaxy_red):
    ship = galaxy_red
    ship._target = None  # explicit

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        App.g_kInputManager.OnKeyDown(App.WC_RBUTTON)
        App.g_kInputManager.OnKeyUp(App.WC_RBUTTON)

    assert len(projectiles._active) == 1
    torp = projectiles._active[0]
    assert torp._target_ship is None  # no homing

    # Snapshot initial velocity.
    vx0, vy0, vz0 = torp._velocity.x, torp._velocity.y, torp._velocity.z

    # Tick 5 seconds — well within 30s TTL but no targets in the test.
    for _ in range(50):
        _advance_combat([ship], dt=0.1)

    # Velocity unchanged (no steering).
    assert torp._velocity.x == vx0
    assert torp._velocity.y == vy0
    assert torp._velocity.z == vz0
    # Still active (within TTL).
    assert len(projectiles._active) == 1

    # Tick until TTL elapses.
    for _ in range(300):  # 30s more
        _advance_combat([ship], dt=0.1)

    # Now expired.
    assert len(projectiles._active) == 0
```

- [ ] **Step 4: Test `torpedo_targets_subsystem.py`**

```python
"""End-to-end: target lock + target-subsystem cycled to a specific
subsystem.  Fire → damage applied to that subsystem specifically."""
from unittest.mock import patch

import App
from engine.appc import projectiles
from engine.appc.math import TGPoint3
from engine.appc.subsystems import HullSubsystem, SensorSubsystem
from engine.host_loop import _advance_combat


def test_targeted_subsystem_takes_damage(galaxy_red, target_ship_at):
    ship = galaxy_red
    target = target_ship_at(0, 200, 0, hull_max=10000.0)

    # Add a Bridge subsystem at world position close to where the torpedo
    # will hit (front of the target ship).
    bridge = SensorSubsystem("Bridge")
    bridge.SetMaxCondition(500.0)
    bridge._parent_ship = target
    # Position relative to ship: ahead of center.
    bridge._position = TGPoint3(0, 5, 0)
    bridge._radius = 5.0
    target._children = [bridge]
    target._target_subsystem = None  # we'll set on the firing ship below

    ship._target = target
    ship._target_subsystem = bridge

    initial_bridge = bridge.GetCondition()
    initial_hull = target.GetHull().GetCondition()

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        App.g_kInputManager.OnKeyDown(App.WC_RBUTTON)
        App.g_kInputManager.OnKeyUp(App.WC_RBUTTON)

    for _ in range(30):
        _advance_combat([ship, target], dt=0.1)
        if len(projectiles._active) == 0:
            break

    # Bridge took damage; hull either took less or none depending on
    # how much bled through.
    assert bridge.GetCondition() < initial_bridge
```

- [ ] **Step 5: Test `friendly_fire_handler.py`**

```python
"""End-to-end: friendly NPC in front of player + lock + fire →
MissionLib.FriendlyFireHandler broadcast handler invoked."""
import sys
import types
from unittest.mock import patch

import App
from engine.host_loop import _advance_combat


def test_friendly_fire_handler_invoked(galaxy_red, target_ship_at):
    ship = galaxy_red
    target = target_ship_at(0, 100, 0)
    ship._target = target

    # Install a spy handler in place of (or alongside) the real
    # FriendlyFireHandler.  We register an additional broadcast for
    # ET_WEAPON_HIT and check it fires.
    spy = []
    def handler(_obj, evt):
        spy.append(evt.GetTarget())

    mod = types.ModuleType("_test_friendly_fire_spy")
    mod.handler = handler
    sys.modules["_test_friendly_fire_spy"] = mod
    try:
        App.g_kEventManager.AddBroadcastPythonFuncHandler(
            App.ET_WEAPON_HIT, None,
            "_test_friendly_fire_spy.handler",
        )

        with patch("engine.audio.tg_sound.TGSoundManager.instance"):
            App.g_kInputManager.OnKeyDown(App.WC_RBUTTON)
            App.g_kInputManager.OnKeyUp(App.WC_RBUTTON)

        # Tick until impact.
        for _ in range(30):
            _advance_combat([ship, target], dt=0.1)
            if spy:
                break

        assert len(spy) == 1
        assert spy[0] is target
    finally:
        del sys.modules["_test_friendly_fire_spy"]
```

- [ ] **Step 6: Test `weapon_hit_event_dispatched.py`**

```python
"""End-to-end: per-ship instance handler installed on target receives
the ET_WEAPON_HIT event with correct source/target/damage/subsystem."""
from unittest.mock import patch

import App
from engine.host_loop import _advance_combat


def test_per_ship_instance_handler_receives_hit(galaxy_red, target_ship_at):
    ship = galaxy_red
    target = target_ship_at(0, 100, 0, hull_max=10000.0)
    ship._target = target

    received = []
    # Per-ship handler — target subscribes to ET_WEAPON_HIT delivered to it.
    target.AddPythonFuncHandlerForInstance(
        App.ET_WEAPON_HIT, "test_weapon_hit_event_dispatched._capture")
    import sys, types
    spy_mod = types.ModuleType("test_weapon_hit_event_dispatched")
    spy_mod._capture = lambda _obj, evt: received.append(
        (evt.GetSource(), evt.GetTarget(), evt.GetDamage())
    )
    sys.modules["test_weapon_hit_event_dispatched"] = spy_mod
    try:
        with patch("engine.audio.tg_sound.TGSoundManager.instance"):
            App.g_kInputManager.OnKeyDown(App.WC_RBUTTON)
            App.g_kInputManager.OnKeyUp(App.WC_RBUTTON)

        for _ in range(30):
            _advance_combat([ship, target], dt=0.1)
            if received:
                break

        assert len(received) >= 1
        src, tgt, dmg = received[0]
        assert src is ship
        assert tgt is target
        assert dmg > 0.0
    finally:
        del sys.modules["test_weapon_hit_event_dispatched"]
```

Note: `target.AddPythonFuncHandlerForInstance` requires `ShipClass` (or its base `TGEventHandlerObject`) to dispatch instance-handlers to events whose `GetDestination()` is None. The current `TGEventManager.AddEvent` (PR 1) dispatches to `event.GetDestination().ProcessEvent(event)` AND iterates broadcast handlers — but it doesn't iterate per-ship instance handlers unless the event's destination IS that ship. For PR 2b, `apply_hit` sets `evt.SetTarget(ship)` but not `SetDestination(ship)`. If the per-ship-instance dispatch doesn't fire, either:
1. Have `apply_hit` set `evt.SetDestination(target)` so `dest.ProcessEvent(...)` reaches the target's `_handlers` dict, OR
2. Extend `TGEventManager.AddEvent` to also fire each ship's instance handlers for `ET_WEAPON_HIT` events that name it as target.

Option 1 is simpler — add `evt.SetDestination(ship)` to `apply_hit` after the existing `evt.SetTarget(ship)`. Update `combat.py` accordingly.

- [ ] **Step 7: Run all integration tests**

```
uv run pytest tests/integration/ -v
```

Expected: ALL PASS. If a test fails, read the traceback to identify which chain link broke. Most likely culprits:
- Galaxy hardpoint doesn't actually call `SetTorpedoScript` in our shim (it should — hardpoint has the line, but if `WeaponSystemProperty` isn't typed yet for that field, the catch-all swallows it). Verify by manually setting the script in the test fixture.
- `target_ship_at` doesn't produce a valid `ShipClass` with shield/hull structure the combat code expects. Adjust the fake.
- Per-ship handler dispatch (above note on option 1 vs 2).

**Do NOT use `pytest.skip` to hide chain breaks** — project memory has explicit guidance against this.

- [ ] **Step 8: Full suite regression check**

```
uv run pytest tests/ -x
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add tests/integration/conftest.py \
        tests/integration/test_torpedo_lock_homes_to_target.py \
        tests/integration/test_torpedo_no_lock_dumbfires.py \
        tests/integration/test_torpedo_targets_subsystem.py \
        tests/integration/test_friendly_fire_handler.py \
        tests/integration/test_weapon_hit_event_dispatched.py \
        engine/appc/combat.py    # if SetDestination tweak needed
git commit -m "$(cat <<'EOF'
test(combat): end-to-end torpedo + damage integration tests

Five integration scenarios driving the full chain from
OnKeyDown(WC_RBUTTON) through TorpedoTube.Fire → projectile spawn
→ per-frame advance → collision → apply_hit → damage + WeaponHitEvent:

- Target locked: torpedo homes, impacts, target hull condition drops.
- No lock: torpedo dumbfires straight, expires on TTL.
- Sub-target locked: damage routes to the specific subsystem.
- Friendly fire: ET_WEAPON_HIT broadcast handler fires.
- Per-ship instance handler: target ship's own handler receives the
  event with correct source/target/damage.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Manual verification (after merge)

1. Build: `cmake --build build -j`.
2. Run: `./build/dauntless`.
3. Load mission, Shift+3 → RED alert, C-toggle to lock a target ship.
4. Right-click: see torpedo sprite leave the tube, watch it home, see it impact. Debug panel shows target's hull condition decrement.
5. Right-click without lock: torpedo flies straight ahead, disappears into the distance.

If anything looks wrong (no sprite, wrong color, doesn't hit), check:
- Renderer is calling `torpedo_pass.frame()` (pipeline.cc dispatch).
- `host_loop._advance_combat` is invoked each frame.
- Galaxy hardpoint's `SetTorpedoScript(0, "Tactical.Projectiles.PhotonTorpedo")` is reaching the typed accessor.

---

## Self-review

**Spec coverage:**

| Spec section | Covered by |
|---|---|
| `WeaponSystemProperty.SetTorpedoScript/GetTorpedoScript` typed | Task 1 |
| `Torpedo` runtime + `CreateTorpedoModel` + registry | Task 2 |
| Homing turn-rate via slerp | Task 2 |
| `WeaponHitEvent` + `ET_WEAPON_HIT` | Task 3 |
| `DamageableObject.DamageSystem` | Task 4 |
| `sphere_hit`, `pick_target_subsystem`, `apply_hit` | Task 5 |
| Shield face from hit point | Task 5 (`_shield_face_from_hit_point`) |
| `TorpedoTube.Fire` spawns projectile | Task 6 |
| Target-lock homing path | Task 6 + test_homing_torpedo_steers |
| Dumbfire path | Task 6 + test_dumbfire_velocity_unchanged |
| Launch sound | Task 6 + test_fire_plays_launch_sound |
| `hit_vfx` lifecycle | Task 7 |
| `host_loop._advance_combat` + FriendlyFireHandler | Task 8 |
| Renderer push (set_torpedoes / set_hit_vfx) | Task 8 + 9 + 10 |
| Native torpedo billboard composite | Task 9 |
| Native hit_vfx flare | Task 10 |
| Full chain integration | Task 11 |

No gaps.

**Placeholder scan:** No `TBD`/`TODO`/`FIXME` in steps. Forward references to "future polish PRs" are explicit deferrals, not placeholders.

**Type consistency:** Field names match across modules (`_position`, `_velocity`, `_age`, `_target_ship`, `_source_ship`, `_damage`, etc.). Method signatures match between definitions and call sites (`apply_hit(ship, damage, hit_point, source, subsystem=None)`, `register(torpedo)`, `update_all(dt, all_ships)`). The renderer push data shape uses tuples for `position` and `color` consistently.
