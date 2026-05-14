# Weapon Emitter Scaffolding (PR 1 of 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the data and runtime scaffolding so per-emitter charge/reload values from BC hardpoint files propagate onto individual phaser banks, pulse cannons, tractor beams, and torpedo tubes when a ship is constructed.

**Architecture:** Engine already has `PhaserBank`/`PulseWeapon`/`TractorBeam`/`TorpedoTube` runtime classes (in [engine/appc/subsystems.py:327-353](engine/appc/subsystems.py#L327-L353)) and a Pass 4 in `ShipClass.SetupProperties` ([engine/appc/ships.py:317-359](engine/appc/ships.py#L317-L359)) that instantiates them from per-emitter properties. This PR adds (a) typed property setters/getters for the charge/reload fields, (b) the corresponding runtime state on the emitter classes, (c) Pass 4 field-copy helpers that propagate property → runtime, and (d) SDK-faithful `GetWeapon`/`GetNumWeapons` aliases plus a `ShipClass.GetWeaponSystemGroup(eGroup)` accessor that PR 2 will read.

**Tech Stack:** Python (engine shim), pytest. No native code changes.

**Spec:** [docs/superpowers/specs/2026-05-13-weapon-emitter-scaffolding-design.md](../specs/2026-05-13-weapon-emitter-scaffolding-design.md)

---

## Files touched

- Modify: [engine/appc/properties.py](engine/appc/properties.py) — extend `EnergyWeaponProperty`, `PulseWeaponProperty`, `TorpedoTubeProperty`
- Modify: [engine/appc/subsystems.py](engine/appc/subsystems.py) — extend `PhaserBank`, `PulseWeapon`, `TractorBeam`, `TorpedoTube`; add `WeaponSystem.GetWeapon`/`GetNumWeapons`
- Modify: [engine/appc/ships.py](engine/appc/ships.py) — Pass 4 field-copy helpers; add `ShipClass.GetWeaponSystemGroup`
- Create: `tests/unit/test_weapon_property_setters.py`
- Create: `tests/unit/test_weapon_emitter_runtime.py`
- Create: `tests/unit/test_weapon_system_get_weapon.py`
- Create: `tests/unit/test_setup_properties_pass4_field_copy.py`
- Create: `tests/unit/test_ship_get_weapon_system_group.py`
- Create: `tests/integration/test_galaxy_hardpoint_emitters.py`
- Modify (cull): `tests/unit/test_subsystems.py`, `tests/unit/test_setup_properties_pass4_children.py`

---

## Task 1: Typed setters/getters on weapon properties

**Files:**
- Modify: [engine/appc/properties.py:169-186](engine/appc/properties.py#L169-L186)
- Create: `tests/unit/test_weapon_property_setters.py`

Hardpoint files like [sdk/Build/scripts/ships/Hardpoints/galaxy.py:209-214](sdk/Build/scripts/ships/Hardpoints/galaxy.py#L209-L214) call `SetMaxCharge(5.0)` / `SetMinFiringCharge(3.0)` / `SetNormalDischargeRate(1.0)` / `SetRechargeRate(0.08)` on phaser properties, and `SetReloadDelay(40.0)` / `SetMaxReady(1)` on torpedo-tube properties. Today these fall through to `TGModelProperty.__getattr__` which stores values into `_data[(field, args)]` but returns `None` from explicit-typed getters. Pass 4 needs typed reads, so we add explicit fields/accessors that override the catch-all.

### Steps

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_weapon_property_setters.py`:

```python
"""Typed setter/getter pairs added in PR 1 for charge/reload fields.

The catch-all TGModelProperty.__getattr__ already accepts any SetX/GetX,
but stores into _data with `None` defaults. These tests pin down the
typed accessors that Pass 4 reads — explicit fields with real defaults
so the runtime emitters get correct values.
"""
from engine.appc.properties import (
    EnergyWeaponProperty, PhaserProperty, PulseWeaponProperty,
    TractorBeamProperty, TorpedoTubeProperty,
)


# ── EnergyWeaponProperty (inherited by Phaser/Pulse/Tractor) ────────────────

def test_energy_weapon_charge_fields_default_zero():
    p = EnergyWeaponProperty("Test")
    assert p.GetMaxCharge() == 0.0
    assert p.GetMinFiringCharge() == 0.0
    assert p.GetNormalDischargeRate() == 0.0
    assert p.GetRechargeRate() == 0.0


def test_energy_weapon_charge_fields_roundtrip():
    p = EnergyWeaponProperty("Test")
    p.SetMaxCharge(5.0)
    p.SetMinFiringCharge(3.0)
    p.SetNormalDischargeRate(1.0)
    p.SetRechargeRate(0.08)
    assert p.GetMaxCharge() == 5.0
    assert p.GetMinFiringCharge() == 3.0
    assert p.GetNormalDischargeRate() == 1.0
    assert p.GetRechargeRate() == 0.08


def test_energy_weapon_charge_setters_coerce_to_float():
    p = EnergyWeaponProperty("Test")
    p.SetMaxCharge(5)  # int input
    assert isinstance(p.GetMaxCharge(), float)
    assert p.GetMaxCharge() == 5.0


def test_phaser_inherits_energy_weapon_charge_surface():
    p = PhaserProperty("Galaxy Dorsal 1")
    p.SetMaxCharge(5.0)
    assert p.GetMaxCharge() == 5.0


def test_tractor_inherits_energy_weapon_charge_surface():
    p = TractorBeamProperty("Forward Tractor 1")
    p.SetRechargeRate(0.3)
    assert p.GetRechargeRate() == 0.3


# ── PulseWeaponProperty ────────────────────────────────────────────────────

def test_pulse_weapon_inherits_charge_surface():
    p = PulseWeaponProperty("Forward Pulse")
    p.SetMaxCharge(2.0)
    assert p.GetMaxCharge() == 2.0


def test_pulse_weapon_cooldown_default_zero():
    p = PulseWeaponProperty("Forward Pulse")
    assert p.GetCooldownTime() == 0.0


def test_pulse_weapon_cooldown_roundtrip():
    p = PulseWeaponProperty("Forward Pulse")
    p.SetCooldownTime(0.3)
    assert p.GetCooldownTime() == 0.3


# ── TorpedoTubeProperty ────────────────────────────────────────────────────

def test_torpedo_tube_reload_fields_default_zero():
    t = TorpedoTubeProperty("Forward Torpedo 1")
    assert t.GetImmediateDelay() == 0.0
    assert t.GetReloadDelay() == 0.0
    assert t.GetMaxReady() == 0


def test_torpedo_tube_reload_fields_roundtrip():
    t = TorpedoTubeProperty("Forward Torpedo 1")
    t.SetImmediateDelay(0.25)
    t.SetReloadDelay(40.0)
    t.SetMaxReady(1)
    assert t.GetImmediateDelay() == 0.25
    assert t.GetReloadDelay() == 40.0
    assert t.GetMaxReady() == 1


def test_torpedo_tube_max_ready_coerces_to_int():
    t = TorpedoTubeProperty("Forward Torpedo 1")
    t.SetMaxReady(1.0)  # hardpoint files have inconsistent typing
    assert isinstance(t.GetMaxReady(), int)
    assert t.GetMaxReady() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_weapon_property_setters.py -v`
Expected: ALL FAIL. Most with assertion errors comparing `None == 0.0` since the catch-all `__getattr__` returns `None` for unset fields. Confirms the catch-all is being hit instead of typed accessors.

- [ ] **Step 3: Add typed accessors to EnergyWeaponProperty**

In [engine/appc/properties.py](engine/appc/properties.py), replace the empty `EnergyWeaponProperty` (currently at line 169-170, a one-line `pass`) with:

```python
class EnergyWeaponProperty(WeaponProperty):
    """Energy-weapon hardpoint template — phasers, pulse cannons, tractors.

    Charge model (sdk/.../App.py:9271-9274): MaxCharge is the reservoir cap,
    MinFiringCharge is the gate to start firing, NormalDischargeRate drains
    charge while firing, RechargeRate fills it when idle.  Typical galaxy.py
    values: max=5, min=3, discharge=1.0/s, recharge=0.08/s.
    """
    def __init__(self, name: str = ""):
        super().__init__(name)
        self._max_charge: float = 0.0
        self._min_firing_charge: float = 0.0
        self._normal_discharge_rate: float = 0.0
        self._recharge_rate: float = 0.0

    def GetMaxCharge(self) -> float:                       return self._max_charge
    def SetMaxCharge(self, v) -> None:                     self._max_charge = float(v)
    def GetMinFiringCharge(self) -> float:                 return self._min_firing_charge
    def SetMinFiringCharge(self, v) -> None:               self._min_firing_charge = float(v)
    def GetNormalDischargeRate(self) -> float:             return self._normal_discharge_rate
    def SetNormalDischargeRate(self, v) -> None:           self._normal_discharge_rate = float(v)
    def GetRechargeRate(self) -> float:                    return self._recharge_rate
    def SetRechargeRate(self, v) -> None:                  self._recharge_rate = float(v)
```

- [ ] **Step 4: Add cooldown accessor to PulseWeaponProperty**

In [engine/appc/properties.py](engine/appc/properties.py), replace the empty `PulseWeaponProperty` (currently a one-line `pass`) with:

```python
class PulseWeaponProperty(EnergyWeaponProperty):
    """Pulse-weapon template — energy-weapon charge model plus a per-shot
    cooldown timer.  Galaxy.py has no pulse cannons; vorcha/marauder do
    (SetCooldownTime values 0.3-1.6 seconds per cannon).
    """
    def __init__(self, name: str = ""):
        super().__init__(name)
        self._cooldown_time: float = 0.0

    def GetCooldownTime(self) -> float:                    return self._cooldown_time
    def SetCooldownTime(self, v) -> None:                  self._cooldown_time = float(v)
```

- [ ] **Step 5: Add reload accessors to TorpedoTubeProperty**

In [engine/appc/properties.py](engine/appc/properties.py), replace the empty `TorpedoTubeProperty` (currently a one-line `pass`) with:

```python
class TorpedoTubeProperty(WeaponProperty):
    """Torpedo-tube template — per-tube reload timing.  Galaxy.py: each tube
    has immediate=0.25s, reload=40s (per-tube; six tubes give ~6.7s effective
    fire interval), MaxReady=1 (one shot queued before reload).
    """
    def __init__(self, name: str = ""):
        super().__init__(name)
        self._immediate_delay: float = 0.0
        self._reload_delay: float = 0.0
        self._max_ready: int = 0

    def GetImmediateDelay(self) -> float:                  return self._immediate_delay
    def SetImmediateDelay(self, v) -> None:                self._immediate_delay = float(v)
    def GetReloadDelay(self) -> float:                     return self._reload_delay
    def SetReloadDelay(self, v) -> None:                   self._reload_delay = float(v)
    def GetMaxReady(self) -> int:                          return self._max_ready
    def SetMaxReady(self, v) -> None:                      self._max_ready = int(v)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_weapon_property_setters.py -v`
Expected: ALL PASS.

- [ ] **Step 7: Run full unit suite to confirm no regression**

Run: `uv run pytest tests/unit/ -x`
Expected: PASS (no existing test depended on the `__getattr__` catch-all for these specific field names, but verify).

- [ ] **Step 8: Commit**

```bash
git add engine/appc/properties.py tests/unit/test_weapon_property_setters.py
git commit -m "$(cat <<'EOF'
feat(props): typed charge/reload accessors on weapon properties

EnergyWeaponProperty gains MaxCharge/MinFiringCharge/NormalDischargeRate/
RechargeRate; PulseWeaponProperty adds CooldownTime; TorpedoTubeProperty
adds ImmediateDelay/ReloadDelay/MaxReady. Hardpoint files (galaxy.py et
al.) populate these per-emitter; Pass 4 reads them next.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Runtime emitter state + WeaponSystem.GetWeapon aliases

**Files:**
- Modify: [engine/appc/subsystems.py:197-353](engine/appc/subsystems.py#L197-L353)
- Create: `tests/unit/test_weapon_emitter_runtime.py`
- Create: `tests/unit/test_weapon_system_get_weapon.py`

Each existing emitter class (`PhaserBank`/`PulseWeapon`/`TractorBeam`/`TorpedoTube`) becomes stateful instead of being a bare `pass` subclass. A module-private `_init_energy_weapon_state` helper keeps the three energy-weapon emitters DRY. `WeaponSystem` gains `GetWeapon(i)` / `GetNumWeapons()` as SDK-faithful aliases over the existing child-subsystem API.

### Steps

- [ ] **Step 1: Write the failing test for runtime emitter state**

Create `tests/unit/test_weapon_emitter_runtime.py`:

```python
"""Per-emitter runtime classes carry charge/reload state.

PR 1 only verifies defaults and the getter surface.  Pass 4 (Task 3)
populates these via property copies; PR 2 will fill/drain them.
"""
import math

from engine.appc.subsystems import (
    PhaserBank, PulseWeapon, TractorBeam, TorpedoTube,
)


def test_phaser_bank_default_charge_fields_zero():
    b = PhaserBank("Dorsal Phaser 1")
    assert b.GetMaxCharge() == 0.0
    assert b.GetMinFiringCharge() == 0.0
    assert b.GetNormalDischargeRate() == 0.0
    assert b.GetRechargeRate() == 0.0
    assert b.GetChargeLevel() == 0.0


def test_phaser_bank_charge_percentage_handles_zero_max():
    b = PhaserBank("Dorsal Phaser 1")
    # GetChargePercentage must not divide by zero when MaxCharge defaults to 0.
    assert b.GetChargePercentage() == 0.0


def test_phaser_bank_charge_percentage_partial():
    b = PhaserBank("Dorsal Phaser 1")
    b._max_charge = 5.0       # Pass 4 populates this; here we set manually.
    b._charge_level = 2.5
    assert b.GetChargePercentage() == 0.5


def test_phaser_bank_set_charge_level_clamps():
    b = PhaserBank("Dorsal Phaser 1")
    b._max_charge = 5.0
    b.SetChargeLevel(10.0)
    assert b.GetChargeLevel() == 5.0      # clamped to max
    b.SetChargeLevel(-1.0)
    assert b.GetChargeLevel() == 0.0      # clamped to zero


def test_pulse_weapon_has_energy_weapon_state_and_cooldown():
    p = PulseWeapon("Forward Pulse")
    assert p.GetMaxCharge() == 0.0
    assert p.GetCooldownTime() == 0.0


def test_tractor_beam_has_energy_weapon_state():
    t = TractorBeam("Aft Tractor 1")
    assert t.GetMaxCharge() == 0.0
    assert t.GetRechargeRate() == 0.0


def test_torpedo_tube_default_reload_fields():
    t = TorpedoTube("Forward Torpedo 1")
    assert t.GetNumReady() == 0
    assert t.GetImmediateDelay() == 0.0
    assert t.GetReloadDelay() == 0.0
    assert t.GetMaxReady() == 0
    assert t.GetLastFireTime() == -math.inf


def test_torpedo_tube_num_ready_setters():
    t = TorpedoTube("Forward Torpedo 1")
    t.SetNumReady(2)
    assert t.GetNumReady() == 2
    t.IncNumReady()
    assert t.GetNumReady() == 3
    t.DecNumReady()
    assert t.GetNumReady() == 2


def test_torpedo_tube_last_fire_time_roundtrip():
    t = TorpedoTube("Forward Torpedo 1")
    t.SetLastFireTime(123.4)
    assert t.GetLastFireTime() == 123.4
```

- [ ] **Step 2: Write the failing test for WeaponSystem.GetWeapon aliases**

Create `tests/unit/test_weapon_system_get_weapon.py`:

```python
"""WeaponSystem.GetNumWeapons / GetWeapon(i) — SDK-faithful aliases over
GetNumChildSubsystems / GetChildSubsystem.  TacticalInterfaceHandlers.
FireWeapons in PR 2 calls these.
"""
from engine.appc.subsystems import PhaserSystem, PhaserBank


def test_get_num_weapons_empty():
    ps = PhaserSystem("Phasers")
    assert ps.GetNumWeapons() == 0


def test_get_num_weapons_counts_child_emitters():
    ps = PhaserSystem("Phasers")
    ps.AddChildSubsystem(PhaserBank("Dorsal Phaser 1"))
    ps.AddChildSubsystem(PhaserBank("Dorsal Phaser 2"))
    assert ps.GetNumWeapons() == 2


def test_get_weapon_returns_child_at_index():
    ps = PhaserSystem("Phasers")
    b1 = PhaserBank("Dorsal Phaser 1")
    b2 = PhaserBank("Dorsal Phaser 2")
    ps.AddChildSubsystem(b1)
    ps.AddChildSubsystem(b2)
    assert ps.GetWeapon(0) is b1
    assert ps.GetWeapon(1) is b2


def test_get_weapon_out_of_range_returns_none():
    ps = PhaserSystem("Phasers")
    assert ps.GetWeapon(0) is None
    ps.AddChildSubsystem(PhaserBank("Dorsal Phaser 1"))
    assert ps.GetWeapon(5) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_weapon_emitter_runtime.py tests/unit/test_weapon_system_get_weapon.py -v`
Expected: ALL FAIL with `AttributeError: 'PhaserBank' object has no attribute 'GetMaxCharge'` (etc.) and `'PhaserSystem' object has no attribute 'GetNumWeapons'`.

- [ ] **Step 4: Add the `_init_energy_weapon_state` helper and new methods**

In [engine/appc/subsystems.py](engine/appc/subsystems.py), insert this helper near the top of the file (after the imports, before `class ShipSubsystem`):

```python
def _init_energy_weapon_state(self):
    """Shared init for PhaserBank/PulseWeapon/TractorBeam runtime state.

    Field names mirror EnergyWeaponProperty (engine/appc/properties.py).
    Pass 4 in ShipClass.SetupProperties copies the property values onto
    these attributes after instantiation — until then they're all zero.
    """
    self._max_charge: float = 0.0
    self._min_firing_charge: float = 0.0
    self._normal_discharge_rate: float = 0.0
    self._recharge_rate: float = 0.0
    self._charge_level: float = 0.0
```

- [ ] **Step 5: Augment PhaserBank with energy-weapon state**

Replace the existing `PhaserBank` (currently [engine/appc/subsystems.py:327-334](engine/appc/subsystems.py#L327-L334)) with:

```python
class PhaserBank(WeaponSystem):
    """Individual phaser emitter.  Hangs under a parent PhaserSystem
    (WeaponSystemProperty WST_PHASER).  SDK App.py: EnergyWeapon subclass.

    Charge fields are populated by Pass 4 from the parent PhaserProperty.
    See sdk/.../ships/Hardpoints/galaxy.py:209-214 for typical values.
    """
    def __init__(self, name: str = ""):
        super().__init__(name)
        _init_energy_weapon_state(self)

    def GetMaxCharge(self) -> float:               return self._max_charge
    def GetMinFiringCharge(self) -> float:         return self._min_firing_charge
    def GetNormalDischargeRate(self) -> float:     return self._normal_discharge_rate
    def GetRechargeRate(self) -> float:            return self._recharge_rate
    def GetChargeLevel(self) -> float:             return self._charge_level

    def GetChargePercentage(self) -> float:
        if self._max_charge <= 0.0:
            return 0.0
        return self._charge_level / self._max_charge

    def SetChargeLevel(self, v) -> None:
        v = float(v)
        if v < 0.0:                self._charge_level = 0.0
        elif v > self._max_charge: self._charge_level = self._max_charge
        else:                      self._charge_level = v
```

- [ ] **Step 6: Augment PulseWeapon with energy-weapon state + cooldown**

Replace the existing `PulseWeapon` ([engine/appc/subsystems.py:337-340](engine/appc/subsystems.py#L337-L340)) with:

```python
class PulseWeapon(WeaponSystem):
    """Individual pulse-weapon emitter under a parent PulseWeaponSystem
    (WeaponSystemProperty WST_PULSE).  Energy-weapon charge surface plus
    a per-shot cooldown timer; see sdk/.../ships/Hardpoints/vorcha.py for
    SetCooldownTime call sites.
    """
    def __init__(self, name: str = ""):
        super().__init__(name)
        _init_energy_weapon_state(self)
        self._cooldown_time: float = 0.0

    def GetMaxCharge(self) -> float:               return self._max_charge
    def GetMinFiringCharge(self) -> float:         return self._min_firing_charge
    def GetNormalDischargeRate(self) -> float:     return self._normal_discharge_rate
    def GetRechargeRate(self) -> float:            return self._recharge_rate
    def GetChargeLevel(self) -> float:             return self._charge_level
    def GetCooldownTime(self) -> float:            return self._cooldown_time

    def GetChargePercentage(self) -> float:
        if self._max_charge <= 0.0:
            return 0.0
        return self._charge_level / self._max_charge

    def SetChargeLevel(self, v) -> None:
        v = float(v)
        if v < 0.0:                self._charge_level = 0.0
        elif v > self._max_charge: self._charge_level = self._max_charge
        else:                      self._charge_level = v
```

- [ ] **Step 7: Augment TractorBeam with energy-weapon state**

Replace the existing `TractorBeam` ([engine/appc/subsystems.py:343-346](engine/appc/subsystems.py#L343-L346)) with:

```python
class TractorBeam(WeaponSystem):
    """Individual tractor-beam emitter under a parent TractorBeamSystem
    (WeaponSystemProperty WST_TRACTOR).  Tractors use the same energy-weapon
    charge model as phasers; see sdk/.../ships/Hardpoints/galaxy.py:853-854
    for typical values (recharge=0.5 for aft tractors, 0.3 for forward).
    """
    def __init__(self, name: str = ""):
        super().__init__(name)
        _init_energy_weapon_state(self)

    def GetMaxCharge(self) -> float:               return self._max_charge
    def GetMinFiringCharge(self) -> float:         return self._min_firing_charge
    def GetNormalDischargeRate(self) -> float:     return self._normal_discharge_rate
    def GetRechargeRate(self) -> float:            return self._recharge_rate
    def GetChargeLevel(self) -> float:             return self._charge_level

    def GetChargePercentage(self) -> float:
        if self._max_charge <= 0.0:
            return 0.0
        return self._charge_level / self._max_charge

    def SetChargeLevel(self, v) -> None:
        v = float(v)
        if v < 0.0:                self._charge_level = 0.0
        elif v > self._max_charge: self._charge_level = self._max_charge
        else:                      self._charge_level = v
```

- [ ] **Step 8: Augment TorpedoTube with reload state**

Replace the existing `TorpedoTube` ([engine/appc/subsystems.py:349-353](engine/appc/subsystems.py#L349-L353)) with:

```python
class TorpedoTube(WeaponSystem):
    """Individual launcher under a parent TorpedoSystem.  Ammo type tracking
    lives on the parent's slot table; this class owns per-tube reload state.

    Reload model (sdk/.../ships/Hardpoints/galaxy.py:28-30):
        ImmediateDelay - delay from fire request to launch (~0.25s)
        ReloadDelay    - per-tube reload after firing (~40s on Galaxy)
        MaxReady       - shots queued before reload begins (usually 1)
    """
    def __init__(self, name: str = ""):
        super().__init__(name)
        self._num_ready: int = 0
        self._last_fire_time: float = float("-inf")
        self._immediate_delay: float = 0.0
        self._reload_delay: float = 0.0
        self._max_ready: int = 0

    def GetNumReady(self) -> int:                  return self._num_ready
    def SetNumReady(self, v) -> None:              self._num_ready = int(v)
    def IncNumReady(self) -> None:                 self._num_ready += 1
    def DecNumReady(self) -> None:                 self._num_ready -= 1
    def GetLastFireTime(self) -> float:            return self._last_fire_time
    def SetLastFireTime(self, v) -> None:          self._last_fire_time = float(v)
    def GetImmediateDelay(self) -> float:          return self._immediate_delay
    def GetReloadDelay(self) -> float:             return self._reload_delay
    def GetMaxReady(self) -> int:                  return self._max_ready
```

- [ ] **Step 9: Add GetNumWeapons / GetWeapon to WeaponSystem**

In [engine/appc/subsystems.py](engine/appc/subsystems.py), inside `class WeaponSystem` (around [line 197](engine/appc/subsystems.py#L197)), add after the existing `StartFiring`/`StopFiring` methods:

```python
    # SDK-faithful aliases over the child-subsystem API.
    # TacticalInterfaceHandlers.FireWeapons (PR 2) reads these.
    def GetNumWeapons(self) -> int:
        return self.GetNumChildSubsystems()

    def GetWeapon(self, i: int):
        return self.GetChildSubsystem(i)
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_weapon_emitter_runtime.py tests/unit/test_weapon_system_get_weapon.py -v`
Expected: ALL PASS.

- [ ] **Step 11: Run full unit suite to confirm no regression**

Run: `uv run pytest tests/unit/ -x`
Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add engine/appc/subsystems.py tests/unit/test_weapon_emitter_runtime.py tests/unit/test_weapon_system_get_weapon.py
git commit -m "$(cat <<'EOF'
feat(weapons): per-emitter charge/reload runtime state

PhaserBank/PulseWeapon/TractorBeam carry MaxCharge/MinFiringCharge/
Normal-Discharge/Recharge plus current ChargeLevel; TorpedoTube carries
NumReady/LastFireTime/ImmediateDelay/ReloadDelay/MaxReady. Shared init
via _init_energy_weapon_state helper. WeaponSystem gains GetWeapon(i)/
GetNumWeapons() aliases over the existing child-subsystem API so PR 2's
event-manager firing path reads SDK-faithful names.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Pass 4 field-copy helpers + GetWeaponSystemGroup

**Files:**
- Modify: [engine/appc/ships.py:317-359](engine/appc/ships.py#L317-L359)
- Create: `tests/unit/test_setup_properties_pass4_field_copy.py`
- Create: `tests/unit/test_ship_get_weapon_system_group.py`

Pass 4 today copies only `MaxCondition` from property to runtime child. We extend it to copy the new charge/reload fields. `ShipClass.GetWeaponSystemGroup(eGroup)` maps `WG_PRIMARY` → phasers, `WG_SECONDARY` → torpedoes, `WG_TERTIARY` → pulse, `WG_TRACTOR` → tractor — matches SDK [TacticalInterfaceHandlers.py:387-405](sdk/Build/scripts/TacticalInterfaceHandlers.py#L387-L405).

### Steps

- [ ] **Step 1: Write the failing test for field-copy in Pass 4**

Create `tests/unit/test_setup_properties_pass4_field_copy.py`:

```python
"""Pass 4 copies typed charge/reload fields from per-emitter property
to runtime emitter, in addition to the MaxCondition copy that already works.
"""
from engine.appc.ships import ShipClass_Create
from engine.appc.properties import (
    WeaponSystemProperty, PhaserProperty, PulseWeaponProperty,
    TractorBeamProperty, TorpedoTubeProperty,
)
from engine.appc.subsystems import PhaserBank, PulseWeapon, TractorBeam, TorpedoTube


def _phaser_parent_prop():
    p = WeaponSystemProperty("Phasers")
    p.SetWeaponSystemType(WeaponSystemProperty.WST_PHASER)
    return p


def _pulse_parent_prop():
    p = WeaponSystemProperty("Pulse")
    p.SetWeaponSystemType(WeaponSystemProperty.WST_PULSE)
    return p


def _tractor_parent_prop():
    p = WeaponSystemProperty("Tractors")
    p.SetWeaponSystemType(WeaponSystemProperty.WST_TRACTOR)
    return p


def _torpedo_parent_prop():
    p = WeaponSystemProperty("Torpedoes")
    p.SetWeaponSystemType(WeaponSystemProperty.WST_TORPEDO)
    return p


def test_phaser_bank_inherits_property_charge_fields():
    """A PhaserProperty with charge values yields a PhaserBank with
    matching runtime fields, and initial ChargeLevel == MaxCharge."""
    ship = ShipClass_Create("Galaxy")
    ps = ship.GetPropertySet()
    ps.AddToSet("Scene Root", _phaser_parent_prop())

    phaser_prop = PhaserProperty("Dorsal Phaser 1")
    phaser_prop.SetMaxCharge(5.0)
    phaser_prop.SetMinFiringCharge(3.0)
    phaser_prop.SetNormalDischargeRate(1.0)
    phaser_prop.SetRechargeRate(0.08)
    ps.AddToSet("Scene Root", phaser_prop)

    ship.SetupProperties()
    bank = ship.GetPhaserSystem().GetWeapon(0)
    assert isinstance(bank, PhaserBank)
    assert bank.GetMaxCharge() == 5.0
    assert bank.GetMinFiringCharge() == 3.0
    assert bank.GetNormalDischargeRate() == 1.0
    assert bank.GetRechargeRate() == 0.08
    # Fresh ships spawn with phasers fully charged.
    assert bank.GetChargeLevel() == 5.0
    assert bank.GetChargePercentage() == 1.0


def test_pulse_weapon_inherits_property_charge_and_cooldown():
    ship = ShipClass_Create("VorCha")
    ps = ship.GetPropertySet()
    ps.AddToSet("Scene Root", _pulse_parent_prop())

    pulse_prop = PulseWeaponProperty("Forward Pulse")
    pulse_prop.SetMaxCharge(2.0)
    pulse_prop.SetCooldownTime(0.8)
    ps.AddToSet("Scene Root", pulse_prop)

    ship.SetupProperties()
    pulse = ship.GetPulseWeaponSystem().GetWeapon(0)
    assert isinstance(pulse, PulseWeapon)
    assert pulse.GetMaxCharge() == 2.0
    assert pulse.GetCooldownTime() == 0.8
    assert pulse.GetChargeLevel() == 2.0


def test_tractor_beam_inherits_property_charge_fields():
    ship = ShipClass_Create("Galaxy")
    ps = ship.GetPropertySet()
    ps.AddToSet("Scene Root", _tractor_parent_prop())

    tract_prop = TractorBeamProperty("Aft Tractor 1")
    tract_prop.SetMaxCharge(1.0)
    tract_prop.SetRechargeRate(0.5)
    ps.AddToSet("Scene Root", tract_prop)

    ship.SetupProperties()
    beam = ship.GetTractorBeamSystem().GetWeapon(0)
    assert isinstance(beam, TractorBeam)
    assert beam.GetMaxCharge() == 1.0
    assert beam.GetRechargeRate() == 0.5
    assert beam.GetChargeLevel() == 1.0


def test_torpedo_tube_inherits_property_reload_fields():
    ship = ShipClass_Create("Galaxy")
    ps = ship.GetPropertySet()
    ps.AddToSet("Scene Root", _torpedo_parent_prop())

    tube_prop = TorpedoTubeProperty("Forward Torpedo 1")
    tube_prop.SetImmediateDelay(0.25)
    tube_prop.SetReloadDelay(40.0)
    tube_prop.SetMaxReady(1)
    ps.AddToSet("Scene Root", tube_prop)

    ship.SetupProperties()
    tube = ship.GetTorpedoSystem().GetWeapon(0)
    assert isinstance(tube, TorpedoTube)
    assert tube.GetImmediateDelay() == 0.25
    assert tube.GetReloadDelay() == 40.0
    assert tube.GetMaxReady() == 1
    # Tubes start loaded.
    assert tube.GetNumReady() == 1


def test_pass4_field_copy_idempotent():
    """Re-running SetupProperties must not double-fill charge values."""
    ship = ShipClass_Create("Galaxy")
    ps = ship.GetPropertySet()
    ps.AddToSet("Scene Root", _phaser_parent_prop())
    phaser_prop = PhaserProperty("Dorsal Phaser 1")
    phaser_prop.SetMaxCharge(5.0)
    ps.AddToSet("Scene Root", phaser_prop)

    ship.SetupProperties()
    ship.SetupProperties()
    assert ship.GetPhaserSystem().GetNumWeapons() == 1
    bank = ship.GetPhaserSystem().GetWeapon(0)
    assert bank.GetMaxCharge() == 5.0
```

- [ ] **Step 2: Write the failing test for GetWeaponSystemGroup**

Create `tests/unit/test_ship_get_weapon_system_group.py`:

```python
"""ShipClass.GetWeaponSystemGroup(eGroup) — WG enum → WeaponSystem slot.

Matches sdk/Build/scripts/TacticalInterfaceHandlers.py:387-405 +
MapModeInterfaceHandlers.py:131-133 (left=primary, right=secondary,
middle=tertiary).  PR 2's FireWeapons handler reads this.
"""
from engine.appc.ships import ShipClass, ShipClass_Create
from engine.appc.properties import WeaponSystemProperty


def _add_group(ship, name, wst):
    p = WeaponSystemProperty(name)
    p.SetWeaponSystemType(wst)
    ship.GetPropertySet().AddToSet("Scene Root", p)


def test_returns_phasers_for_primary():
    ship = ShipClass_Create("Galaxy")
    _add_group(ship, "Phasers", WeaponSystemProperty.WST_PHASER)
    ship.SetupProperties()
    assert ship.GetWeaponSystemGroup(ShipClass.WG_PRIMARY) is ship.GetPhaserSystem()


def test_returns_torpedoes_for_secondary():
    ship = ShipClass_Create("Galaxy")
    _add_group(ship, "Torpedoes", WeaponSystemProperty.WST_TORPEDO)
    ship.SetupProperties()
    assert ship.GetWeaponSystemGroup(ShipClass.WG_SECONDARY) is ship.GetTorpedoSystem()


def test_returns_pulse_for_tertiary():
    ship = ShipClass_Create("X")
    _add_group(ship, "Pulse", WeaponSystemProperty.WST_PULSE)
    ship.SetupProperties()
    assert ship.GetWeaponSystemGroup(ShipClass.WG_TERTIARY) is ship.GetPulseWeaponSystem()


def test_returns_tractor_for_wg_tractor():
    ship = ShipClass_Create("Galaxy")
    _add_group(ship, "Tractors", WeaponSystemProperty.WST_TRACTOR)
    ship.SetupProperties()
    assert ship.GetWeaponSystemGroup(ShipClass.WG_TRACTOR) is ship.GetTractorBeamSystem()


def test_returns_none_for_invalid_group():
    ship = ShipClass_Create("Bare")
    ship.SetupProperties()
    assert ship.GetWeaponSystemGroup(ShipClass.WG_INVALID) is None
    assert ship.GetWeaponSystemGroup(999) is None


def test_returns_none_when_group_not_on_ship():
    """Ship with no PhaserSystem registered — WG_PRIMARY returns None,
    not a placeholder."""
    ship = ShipClass_Create("Bare")
    ship.SetupProperties()
    assert ship.GetWeaponSystemGroup(ShipClass.WG_PRIMARY) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_setup_properties_pass4_field_copy.py tests/unit/test_ship_get_weapon_system_group.py -v`
Expected: Pass 4 tests fail with `AssertionError: 0.0 == 5.0` (fields not yet copied). GetWeaponSystemGroup tests fail with `AttributeError: 'ShipClass' object has no attribute 'GetWeaponSystemGroup'`.

- [ ] **Step 4: Add field-copy helpers + extend Pass 4**

In [engine/appc/ships.py](engine/appc/ships.py), find the existing Pass 4 block (starts around [line 317](engine/appc/ships.py#L317) with `# Pass 4 — child weapons.`). After the import of the runtime classes (around line 329), before `_CHILD_DISPATCH = (`, add:

```python
        def _copy_energy_weapon_fields(child, prop):
            """Copy MaxCharge/MinFiringCharge/Normal-Discharge/Recharge from
            property to runtime emitter.  Seeds charge to full on init."""
            v = prop.GetMaxCharge()
            if v is not None: child._max_charge = float(v)
            v = prop.GetMinFiringCharge()
            if v is not None: child._min_firing_charge = float(v)
            v = prop.GetNormalDischargeRate()
            if v is not None: child._normal_discharge_rate = float(v)
            v = prop.GetRechargeRate()
            if v is not None: child._recharge_rate = float(v)
            # Fresh ships spawn with phasers/pulse/tractors fully charged.
            child._charge_level = child._max_charge

        def _copy_pulse_weapon_fields(child, prop):
            v = prop.GetCooldownTime()
            if v is not None: child._cooldown_time = float(v)

        def _copy_torpedo_tube_fields(tube, prop):
            """Copy reload constants, then preload tubes to MaxReady."""
            v = prop.GetImmediateDelay()
            if v is not None: tube._immediate_delay = float(v)
            v = prop.GetReloadDelay()
            if v is not None: tube._reload_delay = float(v)
            v = prop.GetMaxReady()
            if v is not None: tube._max_ready = int(v)
            tube._num_ready = tube._max_ready
```

Then, inside the existing Pass 4 loop body (find the line `parent.AddChildSubsystem(child)` and the lines just above it that set `MaxCondition`), insert the field-copy dispatch right before `parent.AddChildSubsystem(child)`:

```python
                child = child_cls(prop.GetName() or "")
                child.SetProperty(prop)
                mc = prop.GetMaxCondition()
                if mc is not None: child.SetMaxCondition(mc)

                # NEW: typed field propagation per emitter family.
                if isinstance(child, PhaserBank):
                    _copy_energy_weapon_fields(child, prop)
                elif isinstance(child, PulseWeapon):
                    _copy_energy_weapon_fields(child, prop)
                    _copy_pulse_weapon_fields(child, prop)
                elif isinstance(child, TractorBeam):
                    _copy_energy_weapon_fields(child, prop)
                elif isinstance(child, TorpedoTube):
                    _copy_torpedo_tube_fields(child, prop)

                parent.AddChildSubsystem(child)
                break
```

- [ ] **Step 5: Add GetWeaponSystemGroup to ShipClass**

In [engine/appc/ships.py](engine/appc/ships.py), inside `class ShipClass`, add after the existing `Set/Get*Subsystem` accessors (around [line 117](engine/appc/ships.py#L117), wherever fits the subsystem-accessor block):

```python
    # ── Weapon-group lookup by WG_* enum ─────────────────────────────────────
    # Matches sdk/.../TacticalInterfaceHandlers.py:387-405 dispatch.  PR 2's
    # FireWeapons event handler calls this; included now so the surface is
    # ready when that wiring lands.
    def GetWeaponSystemGroup(self, eGroup: int):
        if eGroup == ShipClass.WG_PRIMARY:
            return self._phaser_system
        if eGroup == ShipClass.WG_SECONDARY:
            return self._torpedo_system
        if eGroup == ShipClass.WG_TERTIARY:
            return self._pulse_weapon_system
        if eGroup == ShipClass.WG_TRACTOR:
            return self._tractor_beam_system
        return None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_setup_properties_pass4_field_copy.py tests/unit/test_ship_get_weapon_system_group.py -v`
Expected: ALL PASS.

- [ ] **Step 7: Run full unit suite to confirm no regression**

Run: `uv run pytest tests/unit/ -x`
Expected: PASS. The existing Pass 4 children test ([tests/unit/test_setup_properties_pass4_children.py](tests/unit/test_setup_properties_pass4_children.py)) should still pass — it only checks `isinstance` and parent/name relationships, both untouched.

- [ ] **Step 8: Commit**

```bash
git add engine/appc/ships.py tests/unit/test_setup_properties_pass4_field_copy.py tests/unit/test_ship_get_weapon_system_group.py
git commit -m "$(cat <<'EOF'
feat(setup): propagate weapon charge/reload from property to emitter

Pass 4 in ShipClass.SetupProperties now copies MaxCharge/MinFiring/
Discharge/Recharge from PhaserProperty/PulseWeaponProperty/Tractor-
BeamProperty onto the runtime emitter, plus ImmediateDelay/ReloadDelay/
MaxReady from TorpedoTubeProperty onto each tube. ShipClass gains
GetWeaponSystemGroup(eGroup) so the WG_PRIMARY/SECONDARY/TERTIARY enum
maps to the matching WeaponSystem slot — PR 2's event-manager firing
handler reads this.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Galaxy hardpoint end-to-end integration test

**Files:**
- Create: `tests/integration/test_galaxy_hardpoint_emitters.py`

The Galaxy hardpoint ([sdk/.../ships/Hardpoints/galaxy.py](sdk/Build/scripts/ships/Hardpoints/galaxy.py)) is a 1500-line module that creates 8 phaser banks, 6 torpedo tubes, 4 tractor projectors, and the WeaponSystemProperty parents that hold them. End-to-end this test imports that module, runs its `LoadPropertySet`, calls `SetupProperties`, and asserts the runtime emitters inherited the actual hardpoint values.

### Steps

- [ ] **Step 1: Check existing integration test infrastructure**

Run: `ls tests/integration/ 2>/dev/null || ls tests/`
Expected: Either an `integration/` directory exists (use it) or it doesn't (create it). If it doesn't exist, the new test sits at `tests/integration/test_galaxy_hardpoint_emitters.py` with an empty `tests/integration/__init__.py` if conftest discovery needs one (most pytest setups don't).

- [ ] **Step 2: Write the failing integration test**

Create `tests/integration/test_galaxy_hardpoint_emitters.py`:

```python
"""End-to-end: import the real Galaxy hardpoint, run LoadPropertySet on a
ShipClass property set, call SetupProperties, then assert the runtime
emitters inherited the values from sdk/.../ships/Hardpoints/galaxy.py.

This is the canonical proof that PR 1's data + structural plumbing all
the way from hardpoint script to runtime emitter works for a real ship.
"""
import importlib
import sys
import pytest

import App
from engine.appc.ships import ShipClass, ShipClass_Create
from engine.appc.subsystems import PhaserBank, PulseWeapon, TractorBeam, TorpedoTube


@pytest.fixture
def galaxy_ship():
    """Load Galaxy hardpoint into a fresh ShipClass and run SetupProperties.

    Mirrors loadspacehelper.CreateShip:87-94 — clears local templates,
    (re)loads the hardpoint module so its top-level RegisterLocalTemplate
    calls run, then invokes the module's LoadPropertySet(propertySet).
    """
    ship = ShipClass_Create("Galaxy")

    App.g_kModelPropertyManager.ClearLocalTemplates()
    # Force fresh import so the module's top-level Create+Register runs.
    mod_name = "ships.Hardpoints.galaxy"
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
    else:
        importlib.import_module(mod_name)
    mod = sys.modules[mod_name]

    mod.LoadPropertySet(ship.GetPropertySet())
    ship.SetupProperties()
    return ship


# ── Group inventory ─────────────────────────────────────────────────────────

def test_galaxy_has_phaser_system(galaxy_ship):
    assert galaxy_ship.GetPhaserSystem() is not None


def test_galaxy_has_torpedo_system(galaxy_ship):
    assert galaxy_ship.GetTorpedoSystem() is not None


def test_galaxy_has_tractor_system(galaxy_ship):
    assert galaxy_ship.GetTractorBeamSystem() is not None


# ── Emitter counts (matches hardpoint, see galaxy.py header) ───────────────

def test_galaxy_has_eight_phaser_banks(galaxy_ship):
    assert galaxy_ship.GetPhaserSystem().GetNumWeapons() == 8


def test_galaxy_has_six_torpedo_tubes(galaxy_ship):
    assert galaxy_ship.GetTorpedoSystem().GetNumWeapons() == 6


def test_galaxy_has_four_tractor_emitters(galaxy_ship):
    # Aft Tractor 1+2, Forward Tractor 1+2 — see galaxy.py.
    assert galaxy_ship.GetTractorBeamSystem().GetNumWeapons() == 4


# ── Per-emitter charge values (matches hardpoint exactly) ───────────────────

def test_galaxy_phaser_charge_fields_match_hardpoint(galaxy_ship):
    """Every phaser bank on the Galaxy uses MaxCharge=5, MinFiringCharge=3,
    NormalDischargeRate=1.0, RechargeRate=0.08 (galaxy.py:209-214 and
    matching blocks for the other seven banks)."""
    phasers = galaxy_ship.GetPhaserSystem()
    for i in range(phasers.GetNumWeapons()):
        bank = phasers.GetWeapon(i)
        assert isinstance(bank, PhaserBank)
        assert bank.GetMaxCharge()           == 5.0
        assert bank.GetMinFiringCharge()     == 3.0
        assert bank.GetNormalDischargeRate() == 1.0
        assert bank.GetRechargeRate()        == 0.08
        # Spawned ships have fully-charged phasers.
        assert bank.GetChargeLevel()         == 5.0
        assert bank.GetChargePercentage()    == 1.0


def test_galaxy_torpedo_tube_reload_fields_match_hardpoint(galaxy_ship):
    """Every torpedo tube: ImmediateDelay=0.25, ReloadDelay=40, MaxReady=1
    (galaxy.py:28-30, repeated for the other five tubes)."""
    torps = galaxy_ship.GetTorpedoSystem()
    for i in range(torps.GetNumWeapons()):
        tube = torps.GetWeapon(i)
        assert isinstance(tube, TorpedoTube)
        assert tube.GetImmediateDelay() == 0.25
        assert tube.GetReloadDelay()    == 40.0
        assert tube.GetMaxReady()       == 1
        assert tube.GetNumReady()       == 1


def test_galaxy_tractor_charge_fields_match_hardpoint(galaxy_ship):
    """Aft tractors recharge=0.5; forward tractors recharge=0.3
    (galaxy.py:854 + 1054 vs 1257 + 1319)."""
    tractors = galaxy_ship.GetTractorBeamSystem()
    aft_recharge = []
    fwd_recharge = []
    for i in range(tractors.GetNumWeapons()):
        beam = tractors.GetWeapon(i)
        assert isinstance(beam, TractorBeam)
        if beam.GetName().startswith("Aft Tractor"):
            aft_recharge.append(beam.GetRechargeRate())
        elif beam.GetName().startswith("Forward Tractor"):
            fwd_recharge.append(beam.GetRechargeRate())
    assert aft_recharge == [0.5, 0.5]
    assert fwd_recharge == [0.3, 0.3]


# ── WG enum routing (PR 2 reads this) ───────────────────────────────────────

def test_galaxy_get_weapon_system_group_primary_is_phasers(galaxy_ship):
    assert galaxy_ship.GetWeaponSystemGroup(ShipClass.WG_PRIMARY) is galaxy_ship.GetPhaserSystem()


def test_galaxy_get_weapon_system_group_secondary_is_torpedoes(galaxy_ship):
    assert galaxy_ship.GetWeaponSystemGroup(ShipClass.WG_SECONDARY) is galaxy_ship.GetTorpedoSystem()


def test_galaxy_get_weapon_system_group_tractor_is_tractors(galaxy_ship):
    assert galaxy_ship.GetWeaponSystemGroup(ShipClass.WG_TRACTOR) is galaxy_ship.GetTractorBeamSystem()
```

- [ ] **Step 3: Run test to verify it passes (Tasks 1-3 should have done all the work)**

Run: `uv run pytest tests/integration/test_galaxy_hardpoint_emitters.py -v`

Expected: ALL PASS. If the `galaxy_ship` fixture fails on import, debug why — the most likely cause is the hardpoint calls some setter we haven't accounted for. Look at the failing line in the traceback; if it's a setter falling through to `TGModelProperty.__getattr__` and that's fine, great. If it's an actual exception (e.g. `TypeError`), that's the bug — fix the relevant property class.

If `LoadPropertySet` raises because galaxy.py references something else missing in our shim, file a follow-up — do not over-scope this PR.

- [ ] **Step 4: Run full suite for regression check**

Run: `uv run pytest tests/ -x`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_galaxy_hardpoint_emitters.py
git commit -m "$(cat <<'EOF'
test(weapons): end-to-end Galaxy hardpoint → emitter inheritance

Loads ships.Hardpoints.galaxy, runs LoadPropertySet on a fresh
ShipClass, calls SetupProperties, then asserts the eight phaser banks,
six torpedo tubes, and four tractor emitters inherited the exact
charge/reload values from the hardpoint. Pins the data path end-to-end
so PR 2's firing logic builds on a known-good substrate.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Audit and cull redundant tests

**Files:**
- Modify: [tests/unit/test_subsystems.py:40-44](tests/unit/test_subsystems.py#L40-L44)
- Modify: [tests/unit/test_setup_properties_pass4_children.py](tests/unit/test_setup_properties_pass4_children.py)

The new charge/reload + Galaxy integration tests subsume some narrow legacy assertions. Drop the bare-bool firing roundtrip and the per-family "this property type yields this emitter class" tests — those facts are now proven (with field values, not just types) by the Galaxy integration test.

### Steps

- [ ] **Step 1: Read the current state of `tests/unit/test_subsystems.py`**

Run: `cat tests/unit/test_subsystems.py`

Confirm lines 40-44 still read approximately:

```python
def test_weapon_system_firing_roundtrip():
    w = WeaponSystem()
    assert w.IsFiring() == 0
    w.StartFiring()
    assert w.IsFiring() == 1
    w.StopFiring()
    assert w.IsFiring() == 0
```

If the function around lines 40-44 has changed, find the equivalent and adapt. The criterion is: a test that only verifies `StartFiring → IsFiring == 1` without exercising charge gating.

- [ ] **Step 2: Remove the bare-bool firing roundtrip**

Edit [tests/unit/test_subsystems.py](tests/unit/test_subsystems.py): delete the `test_weapon_system_firing_roundtrip` function (or whatever the equivalent is named). The behaviour it tested becomes uninteresting once PR 2 lands gating; the bare flag-flip adds nothing the new emitter-runtime + Pass-4 + Galaxy tests don't already establish.

If after deletion the file has no remaining `WeaponSystem` test, also remove `WeaponSystem` from its imports at the top.

- [ ] **Step 3: Audit `tests/unit/test_setup_properties_pass4_children.py`**

Run: `cat tests/unit/test_setup_properties_pass4_children.py`

Six tests live here:
- `test_tractor_children_attached_to_parent` — checks parent.GetNumChildSubsystems == 4 and per-child name/parent/class. **KEEP** as a single parametrised emitter-type test, or **DROP** in favour of the Galaxy integration test which proves this for all four families with real data.
- `test_phaser_children_attached_to_parent` — same as above. **DROP** (subsumed by Galaxy test).
- `test_pulse_children_attached_to_parent` — Galaxy has no pulse cannons, so dropping leaves the pulse path tested only by the field-copy unit test. **KEEP**.
- `test_torpedo_tubes_attached_as_children` — **DROP** (subsumed).
- `test_pass4_skips_children_when_parent_scrubbed` — orphan-safe behavior, important edge case. **KEEP**.
- `test_pass4_idempotent_against_re_run` — re-entry behavior, important. **KEEP**.
- `test_pass4_copies_child_property_back_reference` — property back-ref, **KEEP**.

- [ ] **Step 4: Remove the three subsumed tests**

Edit [tests/unit/test_setup_properties_pass4_children.py](tests/unit/test_setup_properties_pass4_children.py): delete `test_tractor_children_attached_to_parent`, `test_phaser_children_attached_to_parent`, and `test_torpedo_tubes_attached_as_children`. Keep the pulse test (Galaxy doesn't cover pulse), the orphan-safe test, the idempotency test, and the property-back-reference test.

If any helper function (`_tractor_parent`, `_phaser_parent`, `_torpedo_parent`) is no longer referenced after deletion, remove it too. Same for any unused imports.

- [ ] **Step 5: Run full suite to verify nothing else broke**

Run: `uv run pytest tests/ -x`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_subsystems.py tests/unit/test_setup_properties_pass4_children.py
git commit -m "$(cat <<'EOF'
test(cull): drop legacy weapon-firing + per-family child tests

test_subsystems.py loses the bare WeaponSystem.StartFiring → IsFiring
roundtrip — PR 2 reintroduces gating-aware versions, and the bool flip
in isolation adds no signal.

test_setup_properties_pass4_children.py loses the per-family "PhaserBank
attaches to PhaserSystem" rows for tractor/phaser/torpedo — Galaxy
hardpoint integration test now proves these with real data. Pulse stays
(Galaxy has no pulse cannons); orphan-safe, idempotency, and back-ref
edge cases stay.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review

**Spec coverage check:**

| Spec section | Covered by |
|---|---|
| EnergyWeaponProperty MaxCharge/MinFiringCharge/Normal-Discharge/Recharge | Task 1 |
| PulseWeaponProperty CooldownTime | Task 1 |
| TorpedoTubeProperty ImmediateDelay/ReloadDelay/MaxReady | Task 1 |
| Runtime emitter charge state on PhaserBank/PulseWeapon/TractorBeam | Task 2 |
| Runtime emitter reload state on TorpedoTube | Task 2 |
| WeaponSystem.GetWeapon / GetNumWeapons aliases | Task 2 |
| Pass 4 field propagation | Task 3 |
| ShipClass.GetWeaponSystemGroup | Task 3 |
| Galaxy end-to-end test | Task 4 |
| Cull redundant tests | Task 5 |
| Non-goals (gating / alert / tick / event-mgr) | explicitly deferred to PR 2 |

No spec section is uncovered.

**Placeholder scan:** No `TBD`/`TODO`/`FIXME` in this plan. All code blocks contain real implementation.

**Type consistency:** Across tasks, `_max_charge`/`_min_firing_charge`/etc. are `float`; `_max_ready`/`_num_ready` are `int`; `_last_fire_time` is `float` (initialised to `float("-inf")`, exposed via `math.inf` in tests). `GetWeapon(i)` and `GetNumWeapons()` consistently delegate to `GetChildSubsystem(i)` and `GetNumChildSubsystems()`. Property setter names (`SetMaxCharge` etc.) match getter names (`GetMaxCharge`) exactly.
