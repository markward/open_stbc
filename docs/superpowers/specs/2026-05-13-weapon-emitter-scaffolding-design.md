# Weapon emitter scaffolding (PR 1 of 2)

**Status:** design
**Date:** 2026-05-13

## Context

The engine models weapon *groups* (`PhaserSystem`, `TorpedoSystem`, `PulseWeaponSystem`, `TractorBeamSystem`) as `WeaponSystem(PoweredSubsystem)` instances on `ShipClass`. Per-emitter runtime classes already exist in [engine/appc/subsystems.py:327-353](engine/appc/subsystems.py#L327-L353) — `PhaserBank`, `PulseWeapon`, `TractorBeam`, `TorpedoTube` — currently as bare `WeaponSystem` subclasses with no extra state. [engine/appc/ships.py:317-359](engine/appc/ships.py#L317-L359) already runs a Pass 4 in `SetupProperties` that instantiates these emitters from per-emitter properties (`PhaserProperty` → `PhaserBank`, etc.) and attaches them via `AddChildSubsystem`. Tests in [tests/unit/test_setup_properties_pass4_children.py](tests/unit/test_setup_properties_pass4_children.py) prove the wiring works for hand-built property sets.

What's missing:

1. **Property setters** for the charge/reload fields. The per-emitter property classes in [engine/appc/properties.py:169-186](engine/appc/properties.py#L169-L186) are still empty stubs — `VentralPhaser3.SetMaxCharge(5.0)` from [sdk/.../galaxy.py:209](sdk/Build/scripts/ships/Hardpoints/galaxy.py#L209) falls through to `TGModelProperty.__getattr__` and stores an untyped value, but no typed accessor reads it back.
2. **Runtime emitter state** for charge/reload. `PhaserBank` has no `_charge_level`, `TorpedoTube` has no `_num_ready`.
3. **Field propagation in Pass 4.** Today Pass 4 copies only `MaxCondition` ([ships.py:357](engine/appc/ships.py#L357)); the new charge/reload fields need the same treatment.
4. **SDK-faithful accessors** `GetWeapon(i)` / `GetNumWeapons()` on the group, plus `ShipClass.GetWeaponSystemGroup(eGroup)`. PR 2's event-manager handler calls these.
5. **End-to-end Galaxy test.** Existing Pass 4 tests use hand-built properties — none drive a real `LoadPropertySet` from `ships.Hardpoints.galaxy`.

The hardpoint files (e.g. [sdk/Build/scripts/ships/Hardpoints/galaxy.py](sdk/Build/scripts/ships/Hardpoints/galaxy.py)) populate one property per emitter. For the Galaxy that's 8 phaser banks, 6 torpedo tubes, plus tractor beams — each with its own `MaxCharge`/`MinFiringCharge`/`NormalDischargeRate`/`RechargeRate` (energy weapons) or `ImmediateDelay`/`ReloadDelay`/`MaxReady` (torpedo tubes) settings.

PR 1 lays the data and structural foundation; gating, alert-driven power policy, the per-frame tick driver, and the event-manager firing path land in PR 2 ([weapon-firing-event-path](#) — design doc to follow).

## Goals

1. Hardpoint files run end-to-end through the engine without raising, populating per-emitter properties on the registered property templates.
2. After `ShipClass.SetupProperties()`, each `WeaponSystem` on a real ship owns a list of runtime emitter objects whose state matches the hardpoint values.
3. A test loads the Galaxy hardpoint, instantiates a `ShipClass`, and asserts the emitter inventory and per-emitter values match the hardpoint.

## Non-goals (deferred to PR 2)

- `WeaponSystem.StartFiring` gating on power / charge.
- `PoweredSubsystem.TurnOn/TurnOff/IsOn` + percentage-wanted.
- `ShipClass.SetAlertLevel` toggling weapon power.
- Per-frame tick to advance charge/reload state.
- Event-manager-routed firing (`ET_INPUT_FIRE_*` handlers).
- Mouse-button input plumbing.
- Projectile spawn / damage / renderer.

The runtime emitters in this PR carry charge fields, but nothing reads them yet. PR 2 is what turns them into a gating signal.

## Class hierarchy (mirrors SDK)

Property side (in [engine/appc/properties.py](engine/appc/properties.py), extending existing stubs):

```
SubsystemProperty
└── WeaponProperty
    ├── EnergyWeaponProperty   (+ Max/MinFiringCharge, Normal/RechargeRate, MaxDamage/Distance)
    │   ├── PhaserProperty     (+ arc/visual fields used at render time; charge inherited)
    │   ├── PulseWeaponProperty (+ CooldownTime)
    │   └── TractorBeamProperty (charge fields only)
    └── TorpedoTubeProperty    (ImmediateDelay, ReloadDelay, MaxReady, Direction, Right, Dumbfire)
```

Runtime side (existing classes in [engine/appc/subsystems.py:327-353](engine/appc/subsystems.py#L327-L353), with PR 1 adding charge/reload state):

```
PoweredSubsystem
└── WeaponSystem                        (group orchestrator; unchanged in PR 1)
    ├── PhaserSystem                    (existing; group)
    ├── PulseWeaponSystem               (existing; group)
    ├── TractorBeamSystem               (existing; group)
    ├── TorpedoSystem                   (existing; group)
    ├── PhaserBank                      (existing; per-bank emitter)
    │   └── + _max_charge/_min_firing_charge/_normal_discharge_rate/_recharge_rate/_charge_level
    │     + GetMaxCharge/GetMinFiringCharge/GetNormalDischargeRate/GetRechargeRate
    │     + GetChargeLevel/GetChargePercentage/SetChargeLevel
    ├── PulseWeapon                     (existing; per-cannon emitter)
    │   └── + same energy-weapon fields above, plus _cooldown_time/GetCooldownTime
    ├── TractorBeam                     (existing; per-projector emitter)
    │   └── + same energy-weapon fields above
    └── TorpedoTube                     (existing; per-tube emitter)
        └── + _num_ready/_last_fire_time/_immediate_delay/_reload_delay/_max_ready
              + GetNumReady/SetNumReady/IncNumReady/DecNumReady
              + Get/SetLastFireTime, GetImmediateDelay/GetReloadDelay/GetMaxReady
```

**Hierarchy divergence from SDK.** SDK has `EnergyWeapon(Weapon)` as the runtime base for phasers/pulse/tractor and `TorpedoTube(Weapon)`, both descending from `Weapon(ShipSubsystem)`. Our engine has each emitter subclass directly under `WeaponSystem`. Re-parenting under proper `Weapon`/`EnergyWeapon` bases is a separate "SDK fidelity" change — out of scope for PR 1. The shared energy-weapon charge fields are added directly on `PhaserBank`/`PulseWeapon`/`TractorBeam` via a small helper (`_init_energy_weapon_state` mixin function applied in each `__init__`) so we don't repeat field declarations.

## Property surface additions

For each property class below, all setters return `None` (matching SDK); all getters return the stored value or a sensible zero default.

### `EnergyWeaponProperty` (new fields)

| Setter | Getter | Default | Source |
|---|---|---|---|
| `SetMaxCharge(float)` | `GetMaxCharge()` | `0.0` | App.py:9272 |
| `SetMinFiringCharge(float)` | `GetMinFiringCharge()` | `0.0` | App.py:9271 |
| `SetNormalDischargeRate(float)` | `GetNormalDischargeRate()` | `0.0` | App.py:9273 |
| `SetRechargeRate(float)` | `GetRechargeRate()` | `0.0` | App.py:9274 |
| `SetMaxDamage(float)` | `GetMaxDamage()` | `0.0` | hardpoint usage |
| `SetMaxDamageDistance(float)` | `GetMaxDamageDistance()` | `0.0` | hardpoint usage |
| `SetFireSound(str)` | `GetFireSound()` | `""` | hardpoint usage |

`PhaserProperty`, `PulseWeaponProperty`, `TractorBeamProperty` inherit these via class inheritance.

### `PulseWeaponProperty` (additional)

| Setter | Getter | Default | Source |
|---|---|---|---|
| `SetCooldownTime(float)` | `GetCooldownTime()` | `0.0` | App.py:9398 |

### `TorpedoTubeProperty` (new fields)

| Setter | Getter | Default | Source |
|---|---|---|---|
| `SetImmediateDelay(float)` | `GetImmediateDelay()` | `0.0` | hardpoint usage |
| `SetReloadDelay(float)` | `GetReloadDelay()` | `0.0` | App.py:9527 |
| `SetMaxReady(int)` | `GetMaxReady()` | `0` | hardpoint usage |
| `SetDumbfire(int)` | `GetDumbfire()` | `0` | hardpoint usage |
| `SetWeaponID(int)` | `GetWeaponID()` | `0` | hardpoint usage |
| `SetDirection(TGPoint3)` | `GetDirection()` | `None` | hardpoint usage |
| `SetRight(TGPoint3)` | `GetRight()` | `None` | hardpoint usage |

Arc/visual setters that PR 1 doesn't need to interpret (`SetArcWidthAngles`, `SetArcHeightAngles`, `SetPhaserTextureStart`, `SetOuterShellColor`, etc.) are already absorbed by `TGModelProperty.__getattr__` ([engine/appc/properties.py:24-51](engine/appc/properties.py#L24-L51)) — every `SetX` it doesn't know about becomes a no-op storing into `_data`, and `GetX` reads it back. Typed setters defined as real methods naturally override the catch-all by Python's normal attribute resolution. See [Accept-and-discard property setters](#accept-and-discard-property-setters) for why no new infrastructure is needed.

## Runtime emitter surface

Each existing emitter class gets typed state and accessors for the property fields it represents. To keep the field set DRY across `PhaserBank`/`PulseWeapon`/`TractorBeam` (the three energy-weapon emitters), a small module-private helper applies the shared init:

```python
# in engine/appc/subsystems.py
def _init_energy_weapon_state(self):
    self._max_charge: float = 0.0
    self._min_firing_charge: float = 0.0
    self._normal_discharge_rate: float = 0.0
    self._recharge_rate: float = 0.0
    self._charge_level: float = 0.0
```

Each energy emitter class calls this from its `__init__`, then defines the matching getters (`GetMaxCharge`, `GetMinFiringCharge`, etc.) plus `GetChargeLevel`/`GetChargePercentage`/`SetChargeLevel`. The setters that propagate from properties (e.g. `SetMaxCharge`) are added at runtime by the Pass 4 field-copy helper so emitter state stays read-only outside the property pipeline; this matches the existing pattern where MaxCondition propagates one-way from property to runtime.

### `PhaserBank` (existing class, augmented)

Inherits all of WeaponSystem (firing state, target, parent linkage). Adds energy-weapon fields via `_init_energy_weapon_state`. Accessors:

| Getter | Reads | Default |
|---|---|---|
| `GetMaxCharge() -> float` | `_max_charge` | `0.0` |
| `GetMinFiringCharge() -> float` | `_min_firing_charge` | `0.0` |
| `GetNormalDischargeRate() -> float` | `_normal_discharge_rate` | `0.0` |
| `GetRechargeRate() -> float` | `_recharge_rate` | `0.0` |
| `GetChargeLevel() -> float` | `_charge_level` | `0.0` |
| `GetChargePercentage() -> float` | `_charge_level / _max_charge` (or `0.0` if max is 0) | `0.0` |
| `SetChargeLevel(v: float)` | clamps to `[0.0, _max_charge]` | — |

### `PulseWeapon` (existing class, augmented)

Same energy-weapon surface as `PhaserBank`, plus `_cooldown_time: float = 0.0`, `GetCooldownTime() -> float`. (`_time_since_last_shot` is PR 2.)

### `TractorBeam` (existing class, augmented)

Same energy-weapon surface as `PhaserBank`. No extras in PR 1; PR 2 may add mode/strength reads.

### `TorpedoTube` (existing class, augmented)

State: `_num_ready: int = 0`, `_last_fire_time: float = -math.inf`, `_immediate_delay: float = 0.0`, `_reload_delay: float = 0.0`, `_max_ready: int = 0`. On instantiation `_num_ready` is left at `0`; Pass 4 sets it to `_max_ready` after copying the property field.

Accessors: `GetNumReady`, `SetNumReady`, `IncNumReady`, `DecNumReady`, `GetLastFireTime`, `SetLastFireTime`, `GetImmediateDelay`, `GetReloadDelay`, `GetMaxReady`. Direction/right vectors are property-side only in PR 1.

## Group ↔ emitter linkage

### Existing wiring

Pass 4 in `ShipClass.SetupProperties` ([engine/appc/ships.py:317-359](engine/appc/ships.py#L317-L359)) already:

- Iterates the property set looking for `PhaserProperty` / `PulseWeaponProperty` / `TractorBeamProperty` / `TorpedoTubeProperty` instances.
- For each match, instantiates the corresponding runtime class (`PhaserBank`/`PulseWeapon`/`TractorBeam`/`TorpedoTube`), copies `MaxCondition` and `Property`, and attaches via `parent.AddChildSubsystem(child)`.
- Skips when the parent slot is `None` (no WeaponSystemProperty registered for that family).
- Is idempotent against re-runs via a `_parents_with_children` set.

PR 1 extends this with field propagation, not new structural code.

### PR 1 changes to Pass 4

Add a small helper next to the dispatch tuple:

```python
def _copy_energy_weapon_fields(child, prop):
    for src, dst in (
        (prop.GetMaxCharge,           "_max_charge"),
        (prop.GetMinFiringCharge,     "_min_firing_charge"),
        (prop.GetNormalDischargeRate, "_normal_discharge_rate"),
        (prop.GetRechargeRate,        "_recharge_rate"),
    ):
        v = src()
        if v is not None:
            setattr(child, dst, float(v))
    # New ships spawn with phasers charged.
    child._charge_level = child._max_charge

def _copy_pulse_weapon_fields(child, prop):
    v = prop.GetCooldownTime()
    if v is not None:
        child._cooldown_time = float(v)

def _copy_torpedo_tube_fields(tube, prop):
    for src, dst in (
        (prop.GetImmediateDelay, "_immediate_delay"),
        (prop.GetReloadDelay,    "_reload_delay"),
        (prop.GetMaxReady,       "_max_ready"),
    ):
        v = src()
        if v is not None:
            setattr(tube, dst, v)
    tube._num_ready = tube._max_ready  # tubes start loaded
    tube._immediate_delay = float(tube._immediate_delay)
    tube._reload_delay    = float(tube._reload_delay)
    tube._max_ready       = int(tube._max_ready)
```

Pass 4's inner loop adds a single call to the right helper after `child.SetProperty(prop)`:

```python
child = child_cls(prop.GetName() or "")
child.SetProperty(prop)
mc = prop.GetMaxCondition()
if mc is not None: child.SetMaxCondition(mc)

# NEW: typed field propagation per emitter family.
if isinstance(child, PhaserBank):     _copy_energy_weapon_fields(child, prop)
elif isinstance(child, PulseWeapon):  _copy_energy_weapon_fields(child, prop); _copy_pulse_weapon_fields(child, prop)
elif isinstance(child, TractorBeam):  _copy_energy_weapon_fields(child, prop)
elif isinstance(child, TorpedoTube):  _copy_torpedo_tube_fields(child, prop)

parent.AddChildSubsystem(child)
```

### `WeaponSystem.GetNumWeapons` / `GetWeapon(i)`

SDK callers use these names ([App.py:5832-5833](sdk/Build/scripts/App.py#L5832-L5833)) rather than `GetNumChildSubsystems` / `GetChildSubsystem`. PR 2's `TacticalInterfaceHandlers.FireWeapons` reads them. Add as thin aliases on `WeaponSystem`:

```python
def GetNumWeapons(self) -> int:
    return self.GetNumChildSubsystems()

def GetWeapon(self, i: int):
    return self.GetChildSubsystem(i)
```

### `ShipClass.GetWeaponSystemGroup(eGroup)`

PR 2 needs this. To keep PR 1's surface minimal but unblock the test scaffolding, add it now:

```python
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

WG→group mapping confirmed against SDK [TacticalInterfaceHandlers.py:387-405](sdk/Build/scripts/TacticalInterfaceHandlers.py#L387-L405) and [MapModeInterfaceHandlers.py:131-133](sdk/Build/scripts/MapModeInterfaceHandlers.py#L131-L133) ("Left-click fires primary [...], right-click fires secondary [...], middle-click fires tertiary.").

## File layout

- **`engine/appc/properties.py`** — extend `EnergyWeaponProperty`, `PulseWeaponProperty`, `TorpedoTubeProperty` in place; this file already owns the property hierarchy.
- **`engine/appc/subsystems.py`** — extend existing `PhaserBank`/`PulseWeapon`/`TractorBeam`/`TorpedoTube` with charge/reload state and typed getters; add `GetNumWeapons`/`GetWeapon` aliases on `WeaponSystem`. Add the `_init_energy_weapon_state` module-private helper.
- **`engine/appc/ships.py`** — add `GetWeaponSystemGroup`; extend Pass 4 in `SetupProperties` to call `_copy_energy_weapon_fields` / `_copy_pulse_weapon_fields` / `_copy_torpedo_tube_fields` (defined locally in `ships.py` next to the existing dispatch tuple).

No new files. No re-parenting of the existing class hierarchy.

## Accept-and-discard property setters

Hardpoint files set many fields PR 1 doesn't need to read (arc geometry, beam colours, phaser texture indices). The existing `TGModelProperty.__getattr__` in [engine/appc/properties.py:24-51](engine/appc/properties.py#L24-L51) already handles this: any `SetX` it doesn't know about becomes a generic setter that stores into `self._data[(X, args)]`, and any `GetX` reads it back as `None`. All the weapon property classes inherit `TGModelProperty` via `SubsystemProperty → WeaponProperty`, so they get this for free.

The enumerated fields in the tables above are *explicit*, real-method setters — they coerce types and store into named attributes (`_max_charge`, `_reload_delay`, etc.) for direct access by the runtime `_copy_*_fields` helpers. Python class-attribute resolution prefers real methods over `__getattr__`, so the explicit setters win wherever they're defined; everything else falls through to the catch-all.

## Testing

### New tests

- **`tests/unit/test_weapon_properties.py`** — for each property setter/getter pair in EnergyWeapon/Pulse/TorpedoTube, set a value and read it back. Confirms typed coercion (float for charge fields, int for `MaxReady`, etc.).
- **`tests/unit/test_weapon_runtime_classes.py`** — instantiate each runtime class with a hand-built property; assert fields propagated correctly (e.g. `EnergyWeapon._charge_level == prop.GetMaxCharge()` on init).
- **`tests/unit/test_weapon_system_emitters.py`** — `WeaponSystem.AddEmitter`/`GetNumWeapons`/`GetWeapon` round-trip; `GetWeapon(out_of_range)` returns `None`; `_parent_subsystem` linkage holds.
- **`tests/integration/test_galaxy_hardpoint_loads_weapons.py`** — the end-to-end test you asked for. Constructs a `ShipClass`, imports `ships.Hardpoints.galaxy`, runs the hardpoint loader against the ship's property set, calls `SetupProperties`, then asserts:
  - `ship.GetPhaserSystem().GetNumWeapons() == 8`
  - `ship.GetTorpedoSystem().GetNumWeapons() == 6`
  - `bank = ship.GetPhaserSystem().GetWeapon(0); bank.GetMaxCharge() == 5.0`
  - `bank.GetMinFiringCharge() == 3.0; bank.GetRechargeRate() == 0.08`
  - `tube = ship.GetTorpedoSystem().GetWeapon(0); tube.GetReloadDelay() == 40.0; tube.GetMaxReady() == 1`
  - `ship.GetWeaponSystemGroup(ShipClass.WG_PRIMARY) is ship.GetPhaserSystem()`
  - and the same for SECONDARY → torpedoes.
- **`tests/unit/test_ship_get_weapon_system_group.py`** — small focused test for the WG-enum → group accessor.

### Redundant tests to remove

Once the new suite lands, audit and prune. Concrete candidates surfaced by `grep`:

- [tests/unit/test_subsystems.py:40-44](tests/unit/test_subsystems.py#L40-L44) — `WeaponSystem.StartFiring → IsFiring == 1` round-trip. PR 2 reintroduces gating-aware versions; the bare flag-flip is uninteresting once charge fields exist. Drop.
- [tests/unit/test_setup_properties_pass4_children.py](tests/unit/test_setup_properties_pass4_children.py) — six tests using hand-built property sets. Keep the parent-scrubbed (orphan-safe), idempotency, and back-reference cases; the four "this property type yields this emitter class" tests overlap with the Galaxy integration test and can either be dropped or trimmed to a single parametrised test.

The implementation plan lists exact files + line ranges so the cull is concrete.

## Implementation order

1. Extend `EnergyWeaponProperty` / `PulseWeaponProperty` / `TorpedoTubeProperty` setter/getter surface in `engine/appc/properties.py`. Land with `test_weapon_property_setters.py`.
2. Extend `PhaserBank` / `PulseWeapon` / `TractorBeam` / `TorpedoTube` runtime classes in `engine/appc/subsystems.py` with typed state and getters. Add `GetNumWeapons`/`GetWeapon` on `WeaponSystem`. Land with `test_weapon_emitter_runtime.py` and `test_weapon_system_get_weapon.py`.
3. Extend Pass 4 in `engine/appc/ships.py` with the three field-copy helpers. Add `GetWeaponSystemGroup`. Land with `test_setup_properties_pass4_field_copy.py` and `test_ship_get_weapon_system_group.py`.
4. Land the Galaxy end-to-end test (`test_galaxy_hardpoint_emitters.py`).
5. Audit and remove redundant tests per the list above.

Each step is independently testable and reviewable.

## Open questions

1. **TorpedoTube `_num_ready` initial value.** Spec sets it to `_max_ready` after Pass 4 copy (tubes pre-loaded). Matches player expectation; SDK behaviour at spawn would refine but isn't blocking.
2. **`_charge_level` initial value.** Spec sets it to `_max_charge` on Pass 4 copy. If combat balance later wants cold-start delay (`_min_firing_charge` instead), it's a one-line change.

These don't block the spec; revisit during PR 2 tuning.
