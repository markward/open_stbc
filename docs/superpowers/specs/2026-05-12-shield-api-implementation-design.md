# Shield API implementation — design

**Date:** 2026-05-12
**Status:** Approved, ready for plan
**Related:** [2026-05-12-shield-glow-render-pass-design.md](2026-05-12-shield-glow-render-pass-design.md)

## Problem

The Phase-2 stub-call profile shows seven shield-related rows, each called 6000× across 30 missions:

```
ShieldClass_Cast().GetMaxShields
ShieldClass_Cast().GetProperty().SetMaxShields
ShieldClass_Cast().GetProperty().SetShieldChargePerSecond
ShieldClass_Cast().GetSingleShieldPercentage
ShieldClass_Cast().SetCurShields
ShieldProperty_Cast().GetMaxShields
ShieldProperty_Cast().GetShieldChargePerSecond
```

Real implementations of most of these methods already exist on `engine/appc/subsystems.ShieldSubsystem` and `engine/appc/properties.ShieldProperty`. The reason they appear as stubs is that `App.ShieldClass_Cast` and `App.ShieldProperty_Cast` are not defined in [App.py](../../../App.py), so every call falls through `__getattr__` → `_NamedStub`, and the entire chained call sequence becomes stub calls.

The principal hot path is [sdk/Build/scripts/loadspacehelper.py:241-258](../../../sdk/Build/scripts/loadspacehelper.py#L241-L258) (difficulty-based shield scaling, run once per ship per mission load). Additional callers: [SSDiag.py:249-274](../../../sdk/Build/scripts/SSDiag.py#L249-L274), [MissionLib.py:3502-3514](../../../sdk/Build/scripts/MissionLib.py#L3502-L3514) (`IsAnyShieldBreached`), Bridge handler scripts, and per-mission scripts that drain shields (e.g. E6M1, E7M6).

## Goal

Make every one of the seven stub rows go to zero by exposing the missing engine surface, aligning method names with the SDK, and adding shield regen plus a damage hook so the subsystem behaves like a real game system rather than a static data bag.

## Out of scope

- Weapon-side damage routing. Weapons are a separate Phase-2 system; this spec exposes `ApplyDamage` for them to call but does not wire any caller.
- Shield breach / hit events. The SDK paths in the stub profile don't fire events.
- Renderer-side glow flash from damage. Covered by [2026-05-12-shield-glow-render-pass-design.md](2026-05-12-shield-glow-render-pass-design.md).
- `ShieldClass.GetShieldGlowColor` and other display-only properties — not in the seven stubbed rows.

## Surface to add

### `App.py`

- `def ShieldClass_Cast(obj)` — return `obj` if it's a `ShieldSubsystem`, else `None`.
- `def ShieldProperty_Cast(obj)` — return `obj` if it's a `ShieldProperty`, else `None`.
- `ShieldClass = ShieldSubsystem` — module-level re-export so SDK code can read `App.ShieldClass.NUM_SHIELDS` and the six face constants.

`Cast` semantics match the existing `Cast` helpers in [engine/appc/objects.py:458](../../../engine/appc/objects.py#L458) and friends: lenient pass-through when type matches, `None` otherwise. They must reject `_NamedStub` instances (return `None`) — otherwise stub objects keep slipping through.

### `engine/appc/subsystems.py` — `ShieldSubsystem`

Add as class attributes (copied from `ShieldProperty` so `App.ShieldClass.FRONT_SHIELDS` works):

```python
FRONT_SHIELDS  = 0
REAR_SHIELDS   = 1
TOP_SHIELDS    = 2
BOTTOM_SHIELDS = 3
LEFT_SHIELDS   = 4
RIGHT_SHIELDS  = 5
NUM_SHIELDS    = 6
```

Add instance state:

```python
self._property = None  # back-ref set by ShipClass.LoadPropertySet
```

Add methods:

- `GetSingleShieldPercentage(face) -> float` — returns `current / max` for the face. Returns `0.0` when `max == 0` (no divide-by-zero; mirrors SDK `IsAnyShieldBreached` expectation).
- `SetCurShields(face, value) -> None` — alias for the existing `SetCurrentShields`. Both names remain valid call sites.
- `GetProperty()` — returns `self._property` (may be `None` if the subsystem was constructed standalone).
- `Update(dt) -> None` — for each face, `current = min(current + charge_per_second * dt, max)`. Faces with `max == 0` are skipped so unshielded ships don't accumulate phantom charge.
- `ApplyDamage(face, amount) -> float` — drains `current` toward 0, returns the overflow `(amount - current_before)` clamped to `>= 0`. Caller routes overflow to hull. Does not trigger regen, fire events, or mutate any other face.

`SetCurrentShields` stays as the canonical setter; `SetCurShields` becomes an alias (one-line method delegating to it). This keeps internal callers on the descriptive name while the SDK-facing name maps cleanly.

### `engine/appc/properties.py` — `ShieldProperty`

Promote the four face-indexed accessors to real methods backed by per-face lists. Today they shim through the data-bag `__getattr__`; the SDK calls them frequently enough that explicit per-face arrays remove a layer of indirection and surface mistakes (wrong face index, missing setter) as real errors.

```python
def __init__(self, name=""):
    super().__init__(name)
    self._max_shields = [0.0] * self.NUM_SHIELDS
    self._charge_per_second = [0.0] * self.NUM_SHIELDS

def GetMaxShields(self, face):
    return self._max_shields[int(face)]

def SetMaxShields(self, face, value):
    self._max_shields[int(face)] = float(value)

def GetShieldChargePerSecond(self, face):
    return self._charge_per_second[int(face)]

def SetShieldChargePerSecond(self, face, value):
    self._charge_per_second[int(face)] = float(value)
```

During transition: write into both the new list *and* the data-bag entry (`self._data[("MaxShields", (face,))] = value`) so any existing reader keeps working. Run the full test suite; once no test or game-code path reads the data-bag entry, remove the dual-write. (The dual-write is a transition tool, not a permanent backward-compat shim.)

### `engine/appc/ships.py` — `ShipClass`

- Add `GetShields = GetShieldSubsystem` as an additional accessor name. The descriptive internal name stays; `GetShields` is the SDK-facing alias.
- In `LoadPropertySet`, when copying `ShieldProperty` → `ShieldSubsystem` ([ships.py:184-192](../../../engine/appc/ships.py#L184-L192)), set `self._shield_subsystem._property = prop` so `GetProperty()` works.

### `engine/appc/ship_iter.py` — new file

Extract `iter_ships()` from [host_loop.py:643-655](../../../engine/host_loop.py#L643-L655). Preserve the `_objects.values()` workaround verbatim — the comment block at [host_loop.py:629-637](../../../engine/host_loop.py#L629-L637) explains why `GetFirstObject/GetNextObject` can't be used when stub objects are present, and that constraint still applies. Move both `_iter_set_objects` and `_iter_ships` (rename without the leading underscore on the public-facing one) into the new module; `host_loop.py` imports them.

The new module exists so the headless `engine/core/loop.py` can drive subsystem updates without importing `engine/host_loop.py` (which carries renderer-host dependencies the headless loop doesn't need).

### `engine/core/loop.py` — `GameLoop.tick`

Extend with a subsystem update pass after the timer ticks:

```python
def tick(self) -> None:
    App.g_kTimerManager.tick(TICK_DELTA)
    App.g_kRealtimeTimerManager.tick(TICK_DELTA)
    for ship in iter_ships():
        ss = ship.GetShieldSubsystem()
        if ss is not None:
            ss.Update(TICK_DELTA)
```

Order — timers, then subsystems — matches the instrumented Q2 finding (AI/Python first within a tick). When other subsystems gain per-tick behaviour later, they extend the same loop.

## Tests

Augment [tests/unit/test_shield_subsystem.py](../../../tests/unit/test_shield_subsystem.py) and add files as needed:

1. **Cast factories.** `ShieldClass_Cast(ShieldSubsystem())` returns the same instance; `ShieldClass_Cast(<other type>)` returns `None`; `ShieldClass_Cast(_NamedStub('x'))` returns `None`. Same for `ShieldProperty_Cast`.
2. **`GetSingleShieldPercentage`.** Full (1.0), half (0.5), zero (0.0), `max==0` returns 0.0 without raising.
3. **`SetCurShields` aliasing.** Calling `SetCurShields(face, v)` and reading via `GetCurrentShields(face)` round-trips; vice versa also works.
4. **`GetProperty` back-ref.** After `ShipClass.LoadPropertySet` runs with a `ShieldProperty` in the property set, the ship's shield subsystem's `GetProperty()` returns that property.
5. **`ShieldProperty` per-face state.** `SetMaxShields(FRONT, 8000); SetMaxShields(REAR, 4000)` — faces remain independent; `GetMaxShields` returns the right values per face. Same for `Set/GetShieldChargePerSecond`.
6. **`Update(dt)` regen.** With `charge_per_second=10`, `max=100`, `current=50`: after `Update(1.0)`, current is 60. After enough ticks to overshoot, current is clamped at `max`. `charge_per_second=0` leaves current unchanged. `max=0` face is not touched.
7. **`ApplyDamage`.** `current=100, ApplyDamage(face, 30) -> 0.0` overflow, current becomes 70. `current=20, ApplyDamage(face, 50) -> 30.0` overflow, current becomes 0. Other faces unchanged.
8. **Tick integration.** Construct a ship with a shielded property set, place it in a real `App.g_kSetManager` set, run `GameLoop().advance(60)` — the subsystem's current rises by `charge_per_second` per face. Confirms `iter_ships` finds the ship and the loop drives `Update`.
9. **Stub-tracker regression.** Wire a test that runs the difficulty-scaling path in `loadspacehelper.py` (or a focused harness mimicking it) and asserts the seven stub-tracker rows for shield names are empty in `_stub_tracker.report()`.

## Risks and mitigations

- **`ShieldProperty.SetMaxShields` shadowing the data-bag setter.** Hardpoint scripts and other code may read `prop._data[("MaxShields", (face,))]` today. Mitigation: dual-write into both the new list and the data-bag during transition, run the full test suite, drop the dual-write once nothing depends on it.
- **`iter_ships` extraction.** The `_objects.values()` workaround at [host_loop.py:629-637](../../../engine/host_loop.py#L629-L637) is load-bearing — it routes around `_NamedStub`-induced premature iteration termination. Preserve verbatim. Don't refactor to `GetFirstObject/GetNextObject`.
- **Per-tick walk cost.** Walking every ship every tick adds work to the headless loop. With current mission sizes (~5 ships) and 60 Hz, this is negligible (~300 dict lookups/sec). If mission size grows, revisit by registering only ships with non-zero `max_shields` on any face.
