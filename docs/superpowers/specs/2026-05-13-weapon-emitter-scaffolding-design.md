# Weapon emitter scaffolding (PR 1 of 2)

**Status:** design
**Date:** 2026-05-13

## Context

The engine currently models weapon *groups* (`PhaserSystem`, `TorpedoSystem`, `PulseWeaponSystem`, `TractorBeamSystem`) as `WeaponSystem(PoweredSubsystem)` instances on `ShipClass`. `WeaponSystem` holds only `_firing`/`_target`/`_weapon_system_type`. There is no per-emitter runtime — no individual phaser bank, no individual torpedo tube — and the per-emitter property classes (`PhaserProperty`, `PulseWeaponProperty`, `TractorBeamProperty`, `TorpedoTubeProperty`) in [engine/appc/properties.py:169-186](engine/appc/properties.py#L169-L186) are empty stub classes with no setters.

The hardpoint files (e.g. [sdk/Build/scripts/ships/Hardpoints/galaxy.py](sdk/Build/scripts/ships/Hardpoints/galaxy.py)) populate one property per emitter. For the Galaxy that's 8 phaser banks, 6 torpedo tubes, plus tractor beams — each with its own `MaxCharge`/`MinFiringCharge`/`NormalDischargeRate`/`RechargeRate` (energy weapons) or `ImmediateDelay`/`ReloadDelay`/`MaxReady` (torpedo tubes) settings. Today these calls would raise `AttributeError` if a hardpoint were loaded through our shim.

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

Runtime side (new module `engine/appc/weapons.py`, or extending [engine/appc/subsystems.py](engine/appc/subsystems.py); see "File layout" below):

```
ShipSubsystem
└── Weapon                     (StopFiring, Fire, IsFiring, SetFiring, IsDumbFire,
    │                           GetDamageRadiusFactor, GetTargetID, GetOverallConditionPercentage,
    │                           IsMemberOfGroup, CanFire, CalculateWeaponAppeal)
    ├── EnergyWeapon           (+ _max_charge/_min_firing_charge/_normal_discharge_rate/_recharge_rate,
    │   │                         _charge_level, GetMaxCharge/GetMinFiringCharge/
    │   │                         GetNormalDischargeRate/GetRechargeRate, GetChargeLevel/
    │   │                         GetChargePercentage, SetChargeLevel, UpdateCharge)
    │   ├── PhaserBank
    │   ├── PulseWeapon        (+ cooldown_time)
    │   └── TractorBeamProjector
    └── TorpedoTube            (+ _num_ready, _last_fire_time, _immediate_delay, _reload_delay,
                                  _max_ready, Set/IncNumReady, Set/GetLastFireTime,
                                  GetImmediateDelay/ReloadDelay/MaxReady, ReloadTorpedo/Unload)
```

Class names match SDK exactly (App.py:5758-5994, 6398-6513, 6751). We diverge from SDK only where SWIG bookkeeping (`thisown`, `Ptr` mirrors) isn't relevant to a native-Python shim.

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

### `Weapon(ShipSubsystem)` base

State: `_firing: bool`, `_target_id: int | None`, `_damage_radius_factor: float`, `_dumbfire: int`, `_weapon_id: int`, `_property: WeaponProperty | None`.

Methods:
- `SetProperty(prop)`, `GetProperty()`
- `IsFiring() -> int`, `SetFiring(int)`
- `Fire(target, offset_tg)` — placeholder; PR 1 just stamps `_firing = True` and stores the target ID. PR 2 wires real firing logic into the group.
- `StopFiring()` — `_firing = False`.
- `CanFire() -> int` — default `1` (overridden by subclasses in PR 2).
- `IsDumbFire() -> int`, `IsMemberOfGroup(int)`, `GetDamageRadiusFactor`, `GetTargetID`, `GetOverallConditionPercentage`, `CalculateWeaponAppeal` — straightforward getters / passthroughs.

### `EnergyWeapon(Weapon)`

Additional state copied from `EnergyWeaponProperty` at instantiation:
- `_max_charge`, `_min_firing_charge`, `_normal_discharge_rate`, `_recharge_rate`
- `_charge_level: float` — starts at `_max_charge` (so a freshly spawned ship has charged phasers).
- `_power_setting: int` — `PhaserSystem.PP_LOW` / `PP_HIGH`, defaults `PP_HIGH`.

Methods: `GetMaxCharge`, `GetMinFiringCharge`, `GetNormalDischargeRate`, `GetRechargeRate`, `GetChargeLevel`, `GetChargePercentage` (= `_charge_level / _max_charge` or `0` when max is 0), `SetChargeLevel`, `GetPowerSetting`, `SetPowerSetting`, `GetMaxDamage`, `GetMaxDamageDistance`, `GetFireSound`. `UpdateCharge(dt)` is a stub in PR 1 (`return None`); PR 2 implements the fill/drain math.

### `PhaserBank(EnergyWeapon)`, `PulseWeapon(EnergyWeapon)`, `TractorBeamProjector(EnergyWeapon)`

PulseWeapon adds `_cooldown_time: float`, `_time_since_last_shot: float = inf`, `GetCooldownTime`, `GetTimeSinceLastShot`. The other two are bare subclasses for type discrimination — needed so `isinstance(emitter, PulseWeapon)` works at hardpoint-load time.

### `TorpedoTube(Weapon)`

State: `_num_ready: int = 0`, `_last_fire_time: float = -inf`, `_immediate_delay: float`, `_reload_delay: float`, `_max_ready: int`, `_skew_fire: int = 0`, `_direction: TGPoint3 | None`, `_right: TGPoint3 | None`. On instantiation, `_num_ready` is set to `_max_ready` (ship spawns with tubes loaded).

Methods: `SetNumReady`, `IncNumReady`, `DecNumReady`, `GetNumReady`, `SetLastFireTime`, `GetLastFireTime`, `GetImmediateDelay`, `GetReloadDelay`, `GetMaxReady`, `SetSkewFire`, `IsSkewFire`, `ReloadTorpedo`, `UnloadTorpedo`, `GetDirection`, `GetRight`. `CanHit`/`IsInArc` return `1` in PR 1 (arcs are PR 3+ targeting work).

## Group ↔ emitter linkage

### `WeaponSystem` gains an emitter list

[engine/appc/subsystems.py:197-226](engine/appc/subsystems.py#L197-L226):

```python
class WeaponSystem(PoweredSubsystem):
    def __init__(self, name=""):
        super().__init__(name)
        self._firing = False
        self._target = None
        self._weapon_system_type: int = 0
        self._emitters: list[Weapon] = []   # new

    def AddEmitter(self, w: Weapon) -> None:
        self._emitters.append(w)
        w._parent_subsystem = self          # mirror AddChildSubsystem

    def GetNumWeapons(self) -> int:         # SDK App.py:5832
        return len(self._emitters)

    def GetWeapon(self, i: int):            # SDK App.py:5833
        return self._emitters[i] if 0 <= i < len(self._emitters) else None
```

Existing `StartFiring`/`StopFiring`/`IsFiring`/`GetTarget`/`SetTarget` stay unchanged for PR 1. The behavior changes in PR 2.

### Hardpoint loader instantiates emitters

`ShipClass.SetupProperties` ([engine/appc/ships.py:163](engine/appc/ships.py#L163)) currently iterates the property set looking for top-level subsystem properties (`HullProperty`, `ShieldProperty`, `SensorProperty`, `WeaponSystemProperty`, …) and copies fields onto the matching subsystem instance. It does *not* see per-emitter properties.

We extend it with a second pass after the existing per-subsystem pass:

```python
# After existing pass — instantiate per-emitter runtimes from per-emitter properties.
for prop in self.GetPropertySet().GetPropertyList():
    if isinstance(prop, TorpedoTubeProperty):
        tube = TorpedoTube(prop.GetName())
        tube.SetProperty(prop)
        _copy_torpedo_tube_fields(tube, prop)
        self._attach_to_weapon_group(tube, WeaponSystemProperty.WST_TORPEDO)
    elif isinstance(prop, PulseWeaponProperty):
        pulse = PulseWeapon(prop.GetName())
        pulse.SetProperty(prop)
        _copy_energy_weapon_fields(pulse, prop)
        _copy_pulse_weapon_fields(pulse, prop)
        self._attach_to_weapon_group(pulse, WeaponSystemProperty.WST_PULSE)
    elif isinstance(prop, TractorBeamProperty):
        beam = TractorBeamProjector(prop.GetName())
        beam.SetProperty(prop)
        _copy_energy_weapon_fields(beam, prop)
        self._attach_to_weapon_group(beam, WeaponSystemProperty.WST_TRACTOR)
    elif isinstance(prop, PhaserProperty):
        bank = PhaserBank(prop.GetName())
        bank.SetProperty(prop)
        _copy_energy_weapon_fields(bank, prop)
        self._attach_to_weapon_group(bank, WeaponSystemProperty.WST_PHASER)
```

Order matters: the existing per-subsystem pass creates the group `WeaponSystem` instances. The new pass attaches emitters to those groups; if a group doesn't exist for a given emitter type, the emitter is dropped on the floor with a single `warnings.warn(...)`-level message (a hardpoint shouldn't list pulse cannons without a `WeaponSystemProperty(WST_PULSE)`, but mission scripts could conceivably; better to log than crash).

`_attach_to_weapon_group(emitter, wst)` looks up the right slot:

```python
def _attach_to_weapon_group(self, emitter, wst):
    receiver = {
        WeaponSystemProperty.WST_PHASER:  self._phaser_system,
        WeaponSystemProperty.WST_TORPEDO: self._torpedo_system,
        WeaponSystemProperty.WST_PULSE:   self._pulse_weapon_system,
        WeaponSystemProperty.WST_TRACTOR: self._tractor_beam_system,
    }.get(wst)
    if receiver is not None:
        receiver.AddEmitter(emitter)
```

PhaserProperty's check for an existing PhaserSystem on the ship matters: stations and small craft without phasers won't have one, and trying to AddEmitter to None is silently skipped.

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

- **`engine/appc/weapons.py`** — new module. Hosts `Weapon`, `EnergyWeapon`, `PhaserBank`, `PulseWeapon`, `TractorBeamProjector`, `TorpedoTube`, and the `_copy_*_fields` helpers. Pulling them out of `subsystems.py` keeps that file focused on group-level subsystems and avoids growing it past comfort.
- **`engine/appc/properties.py`** — extend `EnergyWeaponProperty`, `PulseWeaponProperty`, `TorpedoTubeProperty` in place; this file already owns the property hierarchy.
- **`engine/appc/subsystems.py`** — add `AddEmitter`/`GetNumWeapons`/`GetWeapon` and the `_emitters` list to `WeaponSystem`. Import `Weapon` lazily inside the type hint to avoid a cycle (`from engine.appc.weapons import Weapon` inside `TYPE_CHECKING` block).
- **`engine/appc/ships.py`** — add `GetWeaponSystemGroup`, the per-emitter second pass in `SetupProperties`, and `_attach_to_weapon_group`. Import the runtime classes at top of file (no cycle: `ships → weapons → subsystems` is a DAG).

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

Once the new suite lands, audit and prune (the user asked for this; concrete candidates I'll verify during implementation):

- `tests/unit/test_subsystems.py::test_weapon_system_*` rows that just exercise `StartFiring → IsFiring == 1`. If the new `test_weapon_runtime_classes` and the integration test cover the path, those bare-bool asserts add nothing; remove them (PR 2 reintroduces a gating-aware version anyway).
- Any existing PhaserSystem-specific test that asserts `_phaser_system` is a bare `PhaserSystem` instance without emitters. Either drop or update to expect `GetNumWeapons() > 0` after hardpoint load.

The implementation plan (next step) will list exact files + line ranges after a `grep -rn` pass, so the cull is concrete, not vague.

## Implementation order

1. Extend `EnergyWeaponProperty` / `PulseWeaponProperty` / `TorpedoTubeProperty` setter/getter surface in `engine/appc/properties.py`. Land with `test_weapon_properties.py`.
2. Create `engine/appc/weapons.py` with the runtime hierarchy. Land with `test_weapon_runtime_classes.py`.
3. Add `AddEmitter`/`GetNumWeapons`/`GetWeapon` to `WeaponSystem` in `engine/appc/subsystems.py`. Land with `test_weapon_system_emitters.py`.
4. Add `GetWeaponSystemGroup` and the second-pass emitter instantiation to `ShipClass` in `engine/appc/ships.py`.
5. Land the integration test (Galaxy hardpoint end-to-end).
6. Audit and remove redundant tests.

Each step is independently testable and reviewable.

## Open questions

1. **TorpedoTube `_num_ready` initial value.** Spec assumes `_max_ready` (tubes pre-loaded). SDK behaviour at ship-spawn would clarify, but for our purposes "ship spawns with full ammo" matches player expectation.
2. **`PhaserProperty` vs `EnergyWeaponProperty`.** All Galaxy phasers use `App.PhaserProperty_Create(...)`. We treat `PhaserProperty` as a thin subclass — does it own any state that should NOT be on `EnergyWeaponProperty` parent? Decision: keep `PhaserProperty` for type discrimination (so `isinstance(prop, PhaserProperty)` works at load time). All shared fields live on parent.
3. **Where does `EnergyWeapon._charge_level` initialise from?** Spec says `_max_charge` on construction. PR 2 will revisit if combat balance suggests "phasers start at min_firing_charge" (cold-start delay) instead.

These don't block the spec; flag them at review and decide as part of PR 1 review or punt to PR 2.
