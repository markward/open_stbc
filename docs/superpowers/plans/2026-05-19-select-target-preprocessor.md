# SelectTarget Preprocessor Implementation Plan (BasicAttack Slice B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the SDK's `AI.Preprocessors.SelectTarget` work end-to-end so combat Compound trees can pick a target from an `ObjectGroup` using the SDK's weighted-factor rating and propagate the chosen target through the external-`SetTarget`-dispatch chain to leaf AIs.

**Architecture:** Three loose tiers, each its own commit cluster. (1) AI-driver preprocess-signature widening so `Update(dEndTime)` methods dispatch correctly. (2) Engine-surface stubs needed by `SelectTarget` — profiling no-ops, event-type constants, ship-state accessors, an `iter_ais_with_external_function` helper. (3) End-to-end exercises of `SelectTarget` loaded via `_SDKFinder`: rating math, dispatch chain, then a PriorityListAI integration. The SDK class itself ships unmodified; the slice is engine glue + regression tests.

**Tech Stack:** Python 3, pytest, the AI driver from prior slices, real SDK `AI/Preprocessors.py` loaded via the `_SDKFinder` in [tests/conftest.py](../../../tests/conftest.py).

**Spec:** [docs/superpowers/specs/2026-05-19-select-target-preprocessor-design.md](../specs/2026-05-19-select-target-preprocessor-design.md) — read first; non-goals and risks are authoritative.

---

## File Structure

| File | Responsibility |
|---|---|
| [`engine/appc/ai_driver.py`](../../../engine/appc/ai_driver.py) (modify) | `_tick_preprocessing` introspects the preprocess method's arity once and caches the result on the `PreprocessingAI` instance; passes `dEndTime = game_time + 1.0` when the method accepts a positional arg. |
| [`App.py`](../../../App.py) (modify) | `ET_DECLOAK_BEGINNING` constant; `TGProfilingInfo_EndTiming` alias (we already have `_StopTiming`); `g_kSystemWrapper.GetTimeSinceFrameStart()` returning `0.0`. |
| [`engine/appc/subsystems.py`](../../../engine/appc/subsystems.py) (modify) | `ShieldSubsystem.GetShieldPercentage()` aggregating across 6 faces. Verify `GetCombinedConditionPercentage` is uniform across weapon / hull / shield subsystems. |
| [`engine/appc/ships.py`](../../../engine/appc/ships.py) (modify) | `GetCloakingSubsystem() -> None` stub. Real `StartGetSubsystemMatch(CT_WEAPON_SYSTEM)` iteration over child weapon subsystems (currently a no-op stub). |
| [`engine/appc/events.py`](../../../engine/appc/events.py) (modify) | `WeaponHitEvent.GetFiringObject()` alias for `GetSource()`. |
| [`engine/appc/objects.py`](../../../engine/appc/objects.py) (modify) | `ObjectGroupWithInfo.__getitem__(name)` returning the per-name info dict (empty dict on miss). |
| [`engine/appc/ai.py`](../../../engine/appc/ai.py) (modify) | `iter_ais_with_external_function(root_ai, fname)` generator walking the AI subtree shape (Plain / PriorityList / Sequence / Conditional / Preprocessing / Builder). |
| `tests/integration/test_ai_driver_preprocess_arg.py` (new) | 3 tests for the AI-driver signature widening: 1-arg method gets `dEndTime`, 0-arg method doesn't, cache survives multiple ticks. |
| `tests/unit/test_select_target_rating.py` (new) | 7 tests against the real SDK `SelectTarget.GetTargetRating` method. |
| `tests/unit/test_select_target_dispatch.py` (new) | 5 tests for `Update` + the external-`SetTarget`-dispatch chain. |
| `tests/integration/test_select_target_in_priority_list.py` (new) | 3 tests: SelectTarget under a PriorityListAI containing 2 candidate AI branches, multi-tick. |
| [`docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md`](../deferred/2026-05-18-ship-ai-runtime.md) (modify) | Strike Slice B from the follow-up list. |

---

## Task 1: AI-driver preprocess signature widening

Detect via `inspect.signature` whether a `PreprocessingAI`'s preprocess method takes a positional `dEndTime` arg; if yes, pass `game_time + 1.0` when dispatching. Cache the arity decision on the `PreprocessingAI` instance so introspection runs once per AI lifetime.

**Files:**
- Modify: [`engine/appc/ai_driver.py`](../../../engine/appc/ai_driver.py) — `_tick_preprocessing`
- Test: `tests/integration/test_ai_driver_preprocess_arg.py` (new)

- [ ] **Step 1.1: Write the failing tests**

Create `tests/integration/test_ai_driver_preprocess_arg.py`:

```python
"""Unit tests for AI driver preprocess signature widening.

SDK preprocess methods come in two shapes:
  Update(self)              — 0-arg (existing synthetic tests use this)
  Update(self, dEndTime)    — 1-arg (SDK SelectTarget, FireScript, etc.)
The driver detects via inspect.signature and passes game_time + 1.0
when the method accepts a positional arg."""
import App
from engine.appc.ai import PreprocessingAI_Create, PlainAI_Create
from engine.appc.ai_driver import tick_ai
from engine.appc.ships import ShipClass


class _ZeroArgPreprocessor:
    """Synthetic preprocessor with 0-arg Preprocess (matches the
    existing test pattern from prior slices)."""
    def __init__(self):
        self.calls = []

    def Preprocess(self):
        self.calls.append("zero")
        return App.PreprocessingAI.PS_NORMAL


class _OneArgPreprocessor:
    """SDK-shaped preprocessor with 1-arg Update."""
    def __init__(self):
        self.calls = []

    def Update(self, dEndTime):
        self.calls.append(dEndTime)
        return App.PreprocessingAI.PS_NORMAL


def _make_preprocessing_ai(ship, instance, method_name):
    pp = PreprocessingAI_Create(ship, "TestPP")
    pp.SetPreprocessingMethod(instance, method_name)
    return pp


def test_zero_arg_preprocess_called_with_no_args():
    ship = ShipClass()
    spy = _ZeroArgPreprocessor()
    pp = _make_preprocessing_ai(ship, spy, "Preprocess")
    tick_ai(pp, game_time=0.5)
    assert spy.calls == ["zero"]


def test_one_arg_preprocess_receives_game_time_plus_one():
    ship = ShipClass()
    spy = _OneArgPreprocessor()
    pp = _make_preprocessing_ai(ship, spy, "Update")
    tick_ai(pp, game_time=2.0)
    # Driver passes game_time + 1.0 as the deadline.
    assert spy.calls == [3.0]


def test_signature_introspection_caches_after_first_tick():
    """Arity decision is cached on the PreprocessingAI instance after
    the first dispatch — subsequent ticks don't re-introspect."""
    import inspect

    ship = ShipClass()
    spy = _OneArgPreprocessor()
    pp = _make_preprocessing_ai(ship, spy, "Update")

    # First tick: introspection runs, cache is populated.
    tick_ai(pp, game_time=1.0)
    assert hasattr(pp, "_preprocess_arity_cache")
    cached = pp._preprocess_arity_cache

    # Patch inspect.signature so a second call would crash if used.
    real_sig = inspect.signature
    inspect.signature = lambda fn: (_ for _ in ()).throw(
        RuntimeError("re-introspected; cache miss"))
    try:
        tick_ai(pp, game_time=5.0)
    finally:
        inspect.signature = real_sig

    assert pp._preprocess_arity_cache is cached
    assert spy.calls == [2.0, 6.0]
```

- [ ] **Step 1.2: Run to verify failure**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/integration/test_ai_driver_preprocess_arg.py -v`

Expected: 3 FAILs. The 1-arg test fails because the current driver calls `getattr(inst, method)()` with no args → `TypeError: Update() missing 1 required positional argument: 'dEndTime'`. The 0-arg test may pass already (driver currently calls 0-arg).

- [ ] **Step 1.3: Implement the introspection + cache**

In [`engine/appc/ai_driver.py`](../../../engine/appc/ai_driver.py), replace the existing `_tick_preprocessing` body (lines 116-140 ish). The change is in how the preprocess method is invoked:

Add `import inspect` at the top of the file (next to other imports).

Replace the body of `_tick_preprocessing`:

```python
def _tick_preprocessing(ai: PreprocessingAI, game_time: float) -> int:
    inst = ai._preprocessing_instance
    method = ai._preprocessing_method
    if inst is None or not method:
        # No preprocessor configured — fall through to contained AI.
        if ai._contained_ai is not None:
            tick_ai(ai._contained_ai, game_time)
        return ai._status

    # Introspect once per PreprocessingAI instance whether the method
    # takes a positional dEndTime arg (SDK SelectTarget/FireScript) or
    # is 0-arg (synthetic test fixtures and simpler preprocessors).
    cache = getattr(ai, "_preprocess_arity_cache", None)
    if cache is None or cache[0] is not inst or cache[1] != method:
        bound = getattr(inst, method)
        try:
            sig = inspect.signature(bound)
            arity = sum(
                1 for p in sig.parameters.values()
                if p.kind in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            )
        except (TypeError, ValueError):
            # Builtin / no inspectable signature → assume 0-arg.
            arity = 0
        ai._preprocess_arity_cache = (inst, method, arity)
        cache = ai._preprocess_arity_cache

    arity = cache[2]
    bound = getattr(inst, method)
    if arity >= 1:
        result = bound(game_time + 1.0)
    else:
        result = bound()

    if result is None:
        result = PS_NORMAL
    if result == PS_DONE:
        ai._status = US_DONE
        return ai._status
    if result == PS_SKIP_DORMANT:
        ai._status = US_DORMANT
        return ai._status
    if result == PS_SKIP_ACTIVE:
        ai._status = US_ACTIVE
        return ai._status
    # PS_NORMAL
    ai._status = US_ACTIVE
    if ai._contained_ai is not None:
        tick_ai(ai._contained_ai, game_time)
    return ai._status
```

- [ ] **Step 1.4: Run; expect pass**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/integration/test_ai_driver_preprocess_arg.py -v`
Expected: 3 PASS.

- [ ] **Step 1.5: Regression sweep on the AI driver**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_ai_driver.py tests/unit/test_ai_primitives.py tests/unit/test_builder_ai_activation.py -q`
Expected: green. Synthetic preprocessors used by these tests have 0-arg `Preprocess` methods which the new path keeps calling with no args.

- [ ] **Step 1.6: Commit**

```bash
git add engine/appc/ai_driver.py tests/integration/test_ai_driver_preprocess_arg.py
git commit -m "feat(ai-driver): pass dEndTime to 1-arg preprocess methods via signature introspection"
```

---

## Task 2: Engine constants + profiling stubs + cloak accessor

Mechanical surface additions. Each is small enough that one task covers them all.

**Files:**
- Modify: [`App.py`](../../../App.py)
- Modify: [`engine/appc/ships.py`](../../../engine/appc/ships.py)
- Modify: [`engine/appc/events.py`](../../../engine/appc/events.py)
- Test: `tests/unit/test_select_target_engine_stubs.py` (new)

- [ ] **Step 2.1: Write the failing tests**

Create `tests/unit/test_select_target_engine_stubs.py`:

```python
"""Unit tests for the small engine surfaces SelectTarget needs."""
import App
from engine.appc.events import WeaponHitEvent
from engine.appc.ships import ShipClass


def test_et_decloak_beginning_constant_is_unique():
    """Event-type constant exists and doesn't collide with the existing
    range or with the Slice A condition constants."""
    assert isinstance(App.ET_DECLOAK_BEGINNING, int)
    existing = {App.ET_AI_TIMER, App.ET_ACTION_COMPLETED, App.ET_MISSION_START,
                App.ET_WEAPON_HIT, App.ET_DELETE_OBJECT_PUBLIC,
                App.ET_OBJECT_GROUP_OBJECT_ENTERED_SET,
                App.ET_OBJECT_GROUP_OBJECT_EXITED_SET,
                App.ET_CONDITION_ATK_FORGIVE}
    assert App.ET_DECLOAK_BEGINNING not in existing


def test_tg_profiling_info_endtiming_alias():
    """SDK calls TGProfilingInfo_EndTiming; we already have _StopTiming.
    The alias must be present and accept a token without raising."""
    token = App.TGProfilingInfo_StartTiming("test")
    App.TGProfilingInfo_EndTiming(token)  # must not raise


def test_system_wrapper_time_since_frame_start_returns_zero():
    """SelectTarget compares against `dEndTime`; with deadline = game_time + 1.0
    and time-since-frame-start = 0, the always-zero return keeps us
    inside the budget."""
    assert App.g_kSystemWrapper.GetTimeSinceFrameStart() == 0.0


def test_ship_class_get_cloaking_subsystem_returns_none():
    """FedAttack/NonFedAttack gate cloak usage on this being truthy;
    None keeps the non-cloak path live."""
    ship = ShipClass()
    assert ship.GetCloakingSubsystem() is None


def test_weapon_hit_event_get_firing_object_aliases_get_source():
    """SDK SelectTarget reads pEvent.GetFiringObject(); we expose
    GetSource(). Add an alias that does the same thing."""
    evt = WeaponHitEvent()
    source = ShipClass()
    evt.SetSource(source)
    assert evt.GetFiringObject() is source
```

- [ ] **Step 2.2: Run to verify failure**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_select_target_engine_stubs.py -v`
Expected: 5 FAILs (or `AttributeError` collapses to similar) for missing surfaces.

- [ ] **Step 2.3: Add the event-type constant + profiling alias in `App.py`**

In [`App.py`](../../../App.py), find the event-type constants block (already contains `ET_DELETE_OBJECT_PUBLIC = 200` etc. from Slice A). Add:

```python
# Decloak event used by SelectTarget to re-rate targets when a hostile
# uncloaks. Value picked outside the Slice A 200-203 range.
ET_DECLOAK_BEGINNING = 204
```

Find the existing `TGProfilingInfo_StopTiming` import / definition. Add an `EndTiming` alias right next to it. Locate the import block:

```python
from engine.appc.debug import (
    CPyDebug, TGProfilingInfo,
    TGProfilingInfo_EnableProfiling, TGProfilingInfo_DisableProfiling,
    TGProfilingInfo_IsProfilingEnabled,
    TGProfilingInfo_StartTiming, TGProfilingInfo_StopTiming,
    TGProfilingInfo_GetTotalTime, TGProfilingInfo_ResetTimings,
)
```

After this import block, add:

```python
# SDK callers use TGProfilingInfo_EndTiming; we already have _StopTiming.
TGProfilingInfo_EndTiming = TGProfilingInfo_StopTiming
```

- [ ] **Step 2.4: Add `GetTimeSinceFrameStart` to `_SystemWrapper`**

In [`App.py`](../../../App.py), find the `class _SystemWrapper:` definition (around line 354 per prior slices' context). Inside the class body, add:

```python
    def GetTimeSinceFrameStart(self) -> float:
        """Seconds since the current frame started. Phase 1 doesn't
        run a frame timer, so this returns 0.0 — SDK preprocessors
        (SelectTarget) compare this against a `dEndTime` budget; with a
        generous deadline the always-zero return keeps work in-budget."""
        return 0.0
```

- [ ] **Step 2.5: Add `GetCloakingSubsystem` to `ShipClass`**

In [`engine/appc/ships.py`](../../../engine/appc/ships.py), inside the `ShipClass` definition (after the existing `Get*Subsystem` accessors), add:

```python
    def GetCloakingSubsystem(self):
        """Returns None — Phase 1 ships have no cloaking subsystem.
        SDK FedAttack/NonFedAttack gate cloak usage on this being
        truthy; None keeps the non-cloak path active."""
        return None
```

- [ ] **Step 2.6: Add `GetFiringObject` alias to `WeaponHitEvent`**

In [`engine/appc/events.py`](../../../engine/appc/events.py), find the `class WeaponHitEvent(TGEvent):` definition. Inside the class, add:

```python
    def GetFiringObject(self):
        """SDK alias for GetSource() — SelectTarget's DamageEvent
        handler reads via GetFiringObject."""
        return self.GetSource()
```

- [ ] **Step 2.7: Run tests; expect pass**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_select_target_engine_stubs.py -v`
Expected: 5 PASS.

- [ ] **Step 2.8: Commit**

```bash
git add App.py engine/appc/ships.py engine/appc/events.py tests/unit/test_select_target_engine_stubs.py
git commit -m "feat(engine): SelectTarget surface stubs (ET_DECLOAK, profiling alias, cloak/firing-object accessors)"
```

---

## Task 3: `ShieldSubsystem.GetShieldPercentage`

Aggregate shield-strength accessor across all 6 faces. Returns `1.0` when no max is set (unshielded ship) so SelectTarget rating doesn't penalize ships that simply lack shields.

**Files:**
- Modify: [`engine/appc/subsystems.py`](../../../engine/appc/subsystems.py)
- Test: `tests/unit/test_shield_percentage.py` (new)

- [ ] **Step 3.1: Write the failing tests**

Create `tests/unit/test_shield_percentage.py`:

```python
"""Unit tests for ShieldSubsystem.GetShieldPercentage — aggregate
ratio across 6 faces. Used by SelectTarget rating."""
from engine.appc.subsystems import ShieldSubsystem
from engine.appc.properties import ShieldProperty


def test_unshielded_ship_returns_one():
    """No max set on any face → defaults to 1.0 so the rating
    doesn't unduly penalize ships that just don't have shields."""
    ss = ShieldSubsystem("X")
    assert ss.GetShieldPercentage() == 1.0


def test_full_shields_returns_one():
    ss = ShieldSubsystem("X")
    for f in range(ShieldProperty.NUM_SHIELDS):
        ss.SetMaxShields(f, 100.0)
    assert ss.GetShieldPercentage() == 1.0


def test_half_shields_returns_half():
    ss = ShieldSubsystem("X")
    for f in range(ShieldProperty.NUM_SHIELDS):
        ss.SetMaxShields(f, 100.0)
        ss.SetCurrentShields(f, 50.0)
    assert ss.GetShieldPercentage() == 0.5


def test_zero_shields_returns_zero():
    ss = ShieldSubsystem("X")
    for f in range(ShieldProperty.NUM_SHIELDS):
        ss.SetMaxShields(f, 100.0)
        ss.SetCurrentShields(f, 0.0)
    assert ss.GetShieldPercentage() == 0.0


def test_mixed_face_strengths_weighted_by_max():
    """Front + Rear at full, rest at zero max → percentage is the
    average of the two faces with max, not 2/6."""
    ss = ShieldSubsystem("X")
    ss.SetMaxShields(0, 100.0); ss.SetCurrentShields(0, 100.0)
    ss.SetMaxShields(1, 100.0); ss.SetCurrentShields(1, 50.0)
    # Total max = 200; total current = 150; ratio = 0.75
    assert ss.GetShieldPercentage() == 0.75
```

- [ ] **Step 3.2: Run; expect fails**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_shield_percentage.py -v`
Expected: 5 FAILs (`GetShieldPercentage` doesn't exist).

- [ ] **Step 3.3: Implement `GetShieldPercentage`**

In [`engine/appc/subsystems.py`](../../../engine/appc/subsystems.py), inside the `ShieldSubsystem` class (after `GetSingleShieldPercentage` around line 1322), add:

```python
    def GetShieldPercentage(self) -> float:
        """Aggregate ratio of total current shields to total max,
        across all 6 faces. Returns 1.0 when no face has max set
        (unshielded ship) so SelectTarget rating treats them as
        "shields not a factor" rather than "shields critically low."""
        total_max = sum(self._max_shields)
        if total_max <= 0:
            return 1.0
        total_cur = sum(self._current_shields)
        return total_cur / total_max
```

- [ ] **Step 3.4: Run; expect pass**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_shield_percentage.py -v`
Expected: 5 PASS.

- [ ] **Step 3.5: Commit**

```bash
git add engine/appc/subsystems.py tests/unit/test_shield_percentage.py
git commit -m "feat(subsystems): ShieldSubsystem.GetShieldPercentage aggregate accessor"
```

---

## Task 4: Subsystem-match iteration honors `CT_WEAPON_SYSTEM` filter

`ShipClass.StartGetSubsystemMatch` currently returns `None` always — the iteration loop in SelectTarget's rating math exits immediately. Implement a real iterator that walks the ship's weapon subsystems when filter is `CT_WEAPON_SYSTEM`. Other filter types remain no-op for this slice.

**Files:**
- Modify: [`engine/appc/ships.py`](../../../engine/appc/ships.py)
- Test: `tests/unit/test_subsystem_match_iteration.py` (new)

- [ ] **Step 4.1: Write the failing tests**

Create `tests/unit/test_subsystem_match_iteration.py`:

```python
"""Unit tests for ShipClass.StartGetSubsystemMatch with CT_WEAPON_SYSTEM
filter. SelectTarget's rating math walks weapon subsystems to compute
fWeaponsGood; the iterator must return them in stable order and
terminate cleanly."""
import App
from engine.appc.ships import ShipClass_Create
from engine.appc.subsystems import (
    PhaserSystem, TorpedoSystem, PulseWeaponSystem, TractorBeamSystem,
)


def _drain_iter(ship, match_type):
    it = ship.StartGetSubsystemMatch(match_type)
    out = []
    sub = ship.GetNextSubsystemMatch(it)
    while sub is not None:
        out.append(sub)
        sub = ship.GetNextSubsystemMatch(it)
    ship.EndGetSubsystemMatch(it)
    return out


def test_no_filter_returns_empty():
    """Backward-compat: zero subsystems → iterator terminates without
    yielding anything."""
    from engine.appc.ships import ShipClass
    ship = ShipClass()  # bare; no subsystems
    out = _drain_iter(ship, App.CT_WEAPON_SYSTEM)
    assert out == []


def test_weapon_filter_yields_phaser_torpedo_pulse_tractor():
    """ShipClass_Create allocates all 4 weapon subsystems; the filter
    yields them all."""
    ship = ShipClass_Create("Test")
    out = _drain_iter(ship, App.CT_WEAPON_SYSTEM)
    classes = {type(s) for s in out}
    assert PhaserSystem in classes
    assert TorpedoSystem in classes
    assert PulseWeaponSystem in classes
    assert TractorBeamSystem in classes


def test_weapon_filter_skips_non_weapon_subsystems():
    """Sensor / impulse / warp / shield / power / repair subsystems
    must NOT appear in a CT_WEAPON_SYSTEM iteration."""
    from engine.appc.subsystems import (
        SensorSubsystem, ImpulseEngineSubsystem,
        WarpEngineSubsystem, ShieldSubsystem,
        PowerSubsystem, RepairSubsystem,
    )
    ship = ShipClass_Create("Test")
    out = _drain_iter(ship, App.CT_WEAPON_SYSTEM)
    classes = {type(s) for s in out}
    for non_weapon in (SensorSubsystem, ImpulseEngineSubsystem,
                       WarpEngineSubsystem, ShieldSubsystem,
                       PowerSubsystem, RepairSubsystem):
        assert non_weapon not in classes


def test_iteration_terminates_after_drain():
    """After iterating all matches, GetNextSubsystemMatch returns
    None — required for SDK while-loops."""
    ship = ShipClass_Create("Test")
    it = ship.StartGetSubsystemMatch(App.CT_WEAPON_SYSTEM)
    while ship.GetNextSubsystemMatch(it) is not None:
        pass
    # Calling again must keep returning None.
    assert ship.GetNextSubsystemMatch(it) is None
    ship.EndGetSubsystemMatch(it)
```

- [ ] **Step 4.2: Run; expect fails**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_subsystem_match_iteration.py -v`
Expected: at least 2 FAILs (the bare-ship empty case may pass trivially; the filtered iterations return empty because the current stub returns None).

- [ ] **Step 4.3: Implement real iteration in `ShipClass`**

In [`engine/appc/ships.py`](../../../engine/appc/ships.py), replace the existing stub iterator (around lines 777-784):

```python
    def StartGetSubsystemMatch(self, match_type=None):
        """Return an iterator over subsystems matching `match_type`.

        `match_type` is one of the CT_* class constants from App.py
        (e.g. CT_WEAPON_SYSTEM = WeaponSystemProperty). Match by
        isinstance check against the subsystem's class hierarchy —
        WeaponSystem and its subclasses (PhaserSystem, TorpedoSystem,
        PulseWeaponSystem, TractorBeamSystem) match CT_WEAPON_SYSTEM.

        Returns an opaque iterator handle. `None` filter terminates
        immediately (SDK pattern: callers expect either matches or a
        clean exit; mid-walk None is undefined)."""
        # Function-local imports — App imports ships at module level,
        # so a top-level `import App` here would loop. Same for
        # WeaponSystem (sibling module also imported by App).
        import App
        from engine.appc.subsystems import WeaponSystem
        if match_type is None:
            return iter(())
        candidates = [
            self._sensor_subsystem, self._impulse_engine_subsystem,
            self._warp_engine_subsystem, self._torpedo_system,
            self._phaser_system, self._pulse_weapon_system,
            self._tractor_beam_system, self._shield_subsystem,
            self._power_subsystem, self._repair_subsystem, self._hull,
        ]
        if match_type is App.CT_WEAPON_SYSTEM:
            target_class = WeaponSystem
        else:
            # Future match types land here. For now, no other filter
            # is implemented — return an empty iter so SDK while-loops
            # terminate cleanly.
            return iter(())
        return iter([s for s in candidates if s is not None and isinstance(s, target_class)])

    def GetNextSubsystemMatch(self, iterator=None):
        """Pull the next subsystem from an iterator returned by
        StartGetSubsystemMatch. Returns None when exhausted (SDK
        while-loop termination contract)."""
        if iterator is None:
            return None
        try:
            return next(iterator)
        except StopIteration:
            return None

    def EndGetSubsystemMatch(self, iterator=None):
        """No-op cleanup hook. Python iterators are GC'd; SDK callers
        invoke this for symmetry with the native Appc iterator API."""
        pass
```

(Don't add a module-level `import App`: `App.py` imports `engine.appc.ships` at module load, so a top-level back-import creates a cycle. The snippet above does function-local `import App` instead — that's the established pattern elsewhere in this file.)

- [ ] **Step 4.4: Run; expect pass**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_subsystem_match_iteration.py -v`
Expected: 4 PASS.

- [ ] **Step 4.5: Regression sweep — confirm the no-op iteration callers (older mission scripts that did `while (pSub != None): ...`) still terminate**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit tests/integration --continue-on-collection-errors -q -k "ship or subsystem" 2>&1 | tail -3`
Expected: green.

- [ ] **Step 4.6: Commit**

```bash
git add engine/appc/ships.py tests/unit/test_subsystem_match_iteration.py
git commit -m "feat(ships): real subsystem-match iteration for CT_WEAPON_SYSTEM filter"
```

---

## Task 5: `ObjectGroupWithInfo.__getitem__`

SelectTarget reads per-target priority info via `pGroupWithInfo[sTarget]["Priority"]`. Our `ObjectGroupWithInfo` doesn't support `__getitem__` yet.

**Files:**
- Modify: [`engine/appc/objects.py`](../../../engine/appc/objects.py)
- Test: append to `tests/unit/test_object_group_active.py` (existing)

- [ ] **Step 5.1: Inspect the existing `ObjectGroupWithInfo` to confirm the per-name info storage**

Run: `grep -n "class ObjectGroupWithInfo\|_info\|AddNameAndInfo\|GetInfo" /Users/mward/Documents/Projects/bc_dauntless/.claude/worktrees/builder-ai-conditions/engine/appc/objects.py` (or the post-merge main checkout path).

Confirm the field name (likely `self._info: dict[str, dict] = {}`). Use that field in the implementation below.

- [ ] **Step 5.2: Write the failing test**

Append to `tests/unit/test_object_group_active.py`:

```python
def test_object_group_with_info_supports_getitem_for_per_name_info():
    """SDK SelectTarget rating reads pGroupWithInfo[sTarget]["Priority"].
    The __getitem__ accessor must return the per-name info dict, or
    empty dict for unknown names (so callers can still .get on it
    without crashing)."""
    from engine.appc.objects import ObjectGroupWithInfo
    g = ObjectGroupWithInfo()
    g.AddNameAndInfo("Bart", {"Priority": 5.0})
    assert g["Bart"] == {"Priority": 5.0}
    # Unknown name → empty dict (SDK callers do `.has_key("Priority")`).
    assert g["Unknown"] == {}
```

- [ ] **Step 5.3: Run; expect fail**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_object_group_active.py::test_object_group_with_info_supports_getitem_for_per_name_info -v`
Expected: FAIL with `TypeError: 'ObjectGroupWithInfo' object is not subscriptable`.

- [ ] **Step 5.4: Implement `__getitem__`**

In [`engine/appc/objects.py`](../../../engine/appc/objects.py), inside the `ObjectGroupWithInfo` class, add:

```python
    def __getitem__(self, name: str) -> dict:
        """Per-name info dict, or empty dict for unknown names.

        SDK SelectTarget rating reads pGroupWithInfo[sTarget]["Priority"]
        then chains `.has_key("Priority")` — the empty-dict fallback
        keeps that pattern safe for targets without recorded info.
        """
        return self._info.get(name, {})
```

(If the field is named differently than `_info`, adjust accordingly. Step 5.1 verified the name.)

- [ ] **Step 5.5: Run; expect pass**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_object_group_active.py -v`
Expected: all PASS (existing tests + the new one).

- [ ] **Step 5.6: Commit**

```bash
git add engine/appc/objects.py tests/unit/test_object_group_active.py
git commit -m "feat(objects): ObjectGroupWithInfo.__getitem__ for SelectTarget priority lookup"
```

---

## Task 6: `iter_ais_with_external_function` helper

SelectTarget propagates the chosen target via a tree walk that finds every AI in the subtree whose `_external_functions` dict has the requested function (typically `"SetTarget"`), then dispatches to the named method on the script instance.

**Files:**
- Modify: [`engine/appc/ai.py`](../../../engine/appc/ai.py)
- Test: `tests/unit/test_ai_external_function_walker.py` (new)

- [ ] **Step 6.1: Write the failing tests**

Create `tests/unit/test_ai_external_function_walker.py`:

```python
"""Unit tests for engine.appc.ai.iter_ais_with_external_function.

Walks an AI subtree (Plain / PriorityList / Sequence / Conditional /
Preprocessing / Builder) and yields PlainAI instances whose
RegisterExternalFunction map contains the requested function name."""
from engine.appc.ai import (
    PlainAI_Create, PriorityListAI_Create, SequenceAI_Create,
    ConditionalAI_Create, PreprocessingAI_Create,
    iter_ais_with_external_function,
)
from engine.appc.ships import ShipClass


def _make_leaf(ship, name, register_set_target=True):
    leaf = PlainAI_Create(ship, name)
    if register_set_target:
        leaf.RegisterExternalFunction(
            "SetTarget", {"FunctionName": f"SetTargetOn_{name}"})
    return leaf


def test_single_leaf_with_registered_function_is_yielded():
    ship = ShipClass()
    leaf = _make_leaf(ship, "Leaf")
    result = list(iter_ais_with_external_function(leaf, "SetTarget"))
    assert result == [leaf]


def test_single_leaf_without_function_yields_nothing():
    ship = ShipClass()
    leaf = _make_leaf(ship, "Leaf", register_set_target=False)
    assert list(iter_ais_with_external_function(leaf, "SetTarget")) == []


def test_priority_list_walks_all_children():
    ship = ShipClass()
    a = _make_leaf(ship, "A")
    b = _make_leaf(ship, "B")
    p = PriorityListAI_Create(ship, "P")
    p.AddAI(a, priority=1); p.AddAI(b, priority=2)
    result = list(iter_ais_with_external_function(p, "SetTarget"))
    assert set(result) == {a, b}


def test_sequence_walks_all_children():
    ship = ShipClass()
    a = _make_leaf(ship, "A")
    b = _make_leaf(ship, "B")
    s = SequenceAI_Create(ship, "S")
    s.AddAI(a); s.AddAI(b)
    assert set(iter_ais_with_external_function(s, "SetTarget")) == {a, b}


def test_conditional_walks_contained():
    ship = ShipClass()
    inner = _make_leaf(ship, "Inner")
    c = ConditionalAI_Create(ship, "C")
    c.SetContainedAI(inner)
    assert list(iter_ais_with_external_function(c, "SetTarget")) == [inner]


def test_preprocessing_walks_contained():
    ship = ShipClass()
    inner = _make_leaf(ship, "Inner")
    pp = PreprocessingAI_Create(ship, "PP")
    pp.SetContainedAI(inner)
    assert list(iter_ais_with_external_function(pp, "SetTarget")) == [inner]


def test_nested_composites_are_walked_recursively():
    """Sequence containing a PriorityList containing leaves — all
    matching leaves come out regardless of depth."""
    ship = ShipClass()
    a = _make_leaf(ship, "A")
    b = _make_leaf(ship, "B")
    p = PriorityListAI_Create(ship, "P")
    p.AddAI(a, priority=1); p.AddAI(b, priority=2)
    s = SequenceAI_Create(ship, "S")
    s.AddAI(p)
    assert set(iter_ais_with_external_function(s, "SetTarget")) == {a, b}


def test_unregistered_function_name_yields_nothing():
    ship = ShipClass()
    leaf = _make_leaf(ship, "Leaf")
    # Leaf registered "SetTarget"; we ask for a different name.
    assert list(iter_ais_with_external_function(leaf, "Fire")) == []


def test_none_root_yields_nothing():
    """Defensive: None root returns empty iterator, no crash."""
    assert list(iter_ais_with_external_function(None, "SetTarget")) == []
```

- [ ] **Step 6.2: Run; expect fails**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_ai_external_function_walker.py -v`
Expected: 9 FAILs with `ImportError: cannot import name 'iter_ais_with_external_function'`.

- [ ] **Step 6.3: Implement the helper in `engine/appc/ai.py`**

At the bottom of [`engine/appc/ai.py`](../../../engine/appc/ai.py), add:

```python
def iter_ais_with_external_function(root_ai, fname: str):
    """Yield every PlainAI in the subtree rooted at `root_ai` whose
    GetExternalFunctions() dict contains `fname` as a key.

    SDK pattern: SelectTarget walks the contained AI tree, finds leaves
    that registered `"SetTarget"` via `RegisterExternalFunction` in
    BaseAI.SetExternalFunctions, and dispatches the picked target name
    through the leaf's `info["FunctionName"]` method on the script
    instance.

    Tree shape:
      PlainAI                 — leaf; yielded if its _external_functions
                                contains fname.
      PriorityListAI          — recurse into each child AI in
                                self._ais (list of (priority, ai)).
      SequenceAI              — recurse into self._ais (list of ai).
      ConditionalAI           — recurse into self._contained_ai.
      PreprocessingAI         — recurse into self._contained_ai.
      BuilderAI (extends PP)  — handled by the PreprocessingAI case
                                after activation; before activation,
                                _contained_ai is None and no leaves yield.
    """
    if root_ai is None:
        return
    if isinstance(root_ai, PlainAI):
        if fname in root_ai._external_functions:
            yield root_ai
        return
    if isinstance(root_ai, PriorityListAI):
        for _prio, child in root_ai._ais:
            yield from iter_ais_with_external_function(child, fname)
        return
    if isinstance(root_ai, SequenceAI):
        for child in root_ai._ais:
            yield from iter_ais_with_external_function(child, fname)
        return
    if isinstance(root_ai, (ConditionalAI, PreprocessingAI)):
        yield from iter_ais_with_external_function(
            root_ai._contained_ai, fname)
        return
    # Unknown AI subclass: silently terminate. Subclasses that contain
    # other AIs should be added here as the project grows.
```

- [ ] **Step 6.4: Run; expect pass**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_ai_external_function_walker.py -v`
Expected: 9 PASS.

- [ ] **Step 6.5: Commit**

```bash
git add engine/appc/ai.py tests/unit/test_ai_external_function_walker.py
git commit -m "feat(ai): iter_ais_with_external_function helper for SelectTarget dispatch"
```

---

## Task 7: `SelectTarget.GetTargetRating` math

Load the real SDK `SelectTarget` via `_SDKFinder`, exercise its rating function with controlled inputs, and confirm each factor (distance / in-front / shield / weapon / hull / damage / priority / is-target) drives the rating in the expected direction.

**Files:**
- Test: `tests/unit/test_select_target_rating.py` (new)
- Possible engine-fix commits if surfaces surface — escalate per the established pattern.

- [ ] **Step 7.1: Re-read the SDK rating function**

Run: `sed -n '1481,1620p' /Users/mward/Documents/Projects/bc_dauntless/sdk/Build/scripts/AI/Preprocessors.py | head -140`

Note the factor weights (`SetRelativeImportance` defaults: distance 1.0, in-front 0.2, is-target 1.0, shield -0.2, weapon -0.2, hull -0.1, damage 1.0, priority 1.0, popularity -1.1) and how each per-target "goodness" value is combined.

- [ ] **Step 7.2: Write the failing tests**

Create `tests/unit/test_select_target_rating.py`:

```python
"""Unit tests for SDK AI.Preprocessors.SelectTarget.GetTargetRating.

Load the real class via _SDKFinder; build a minimal PreprocessingAI
shell with the SelectTarget as preprocess; exercise GetTargetRating
with controlled targets and assert each factor moves the rating
in the expected direction."""
import pytest

import App
from engine.appc.ai import PreprocessingAI_Create
from engine.appc.events import TGEvent_Create
from engine.appc.objects import ObjectGroup
from engine.appc.ships import ShipClass_Create, ShipClass
from engine.appc.subsystems import HullSubsystem


def _reset_app_state():
    App.g_kSetManager._sets.clear()
    if hasattr(App.g_kEventManager, "_method_handlers"):
        App.g_kEventManager._method_handlers.clear()


@pytest.fixture(autouse=True)
def _isolate():
    _reset_app_state()
    yield
    _reset_app_state()


def _make_select_target(our_ship, *target_names):
    """Construct a real SDK SelectTarget with our_ship as the
    pCodeAI's ship."""
    from AI.Preprocessors import SelectTarget
    pp = PreprocessingAI_Create(our_ship, "TestSel")
    grp = ObjectGroup()
    for n in target_names:
        grp.AddName(n)
    inst = SelectTarget(grp)
    inst.pCodeAI = pp
    pp.SetPreprocessingMethod(inst, "Update")
    return inst, pp


def _make_target_ship_at(name, x, y, z, *, hull_max=10000.0):
    pSet = App.g_kSetManager.GetSet("S")
    if pSet is None:
        pSet = App.SetClass_Create(); pSet.SetName("S")
        App.g_kSetManager._sets["S"] = pSet
    t = ShipClass()
    t.SetTranslateXYZ(x, y, z)
    hull = HullSubsystem("Hull"); hull.SetMaxCondition(hull_max)
    t._hull = hull
    pSet.AddObjectToSet(t, name)
    return t


def test_closer_target_rates_higher_than_farther():
    """Distance factor (positive weight) → closer is better."""
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    ours = ShipClass(); ours.SetTranslateXYZ(0, 0, 0)
    pSet.AddObjectToSet(ours, "Ours")
    close = _make_target_ship_at("Close", 0, 50, 0)
    far = _make_target_ship_at("Far", 0, 500, 0)

    inst, _pp = _make_select_target(ours, "Close", "Far")
    rating_close = inst.GetTargetRating(close)
    rating_far = inst.GetTargetRating(far)
    assert rating_close > rating_far


def test_in_front_target_rates_higher_than_behind():
    """Ship at origin facing +Y. Target at +Y rates higher than target
    at -Y (other factors equal)."""
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    ours = ShipClass(); ours.SetTranslateXYZ(0, 0, 0)
    pSet.AddObjectToSet(ours, "Ours")
    ahead = _make_target_ship_at("Ahead", 0, 100, 0)
    behind = _make_target_ship_at("Behind", 0, -100, 0)

    inst, _ = _make_select_target(ours, "Ahead", "Behind")
    assert inst.GetTargetRating(ahead) > inst.GetTargetRating(behind)


def test_target_with_lower_shields_rates_higher_under_default_weights():
    """Shield factor weight is NEGATIVE (-0.2) by default — lower
    shields → less subtraction → higher rating."""
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    ours = ShipClass(); ours.SetTranslateXYZ(0, 0, 0)
    pSet.AddObjectToSet(ours, "Ours")
    from engine.appc.subsystems import ShieldSubsystem
    from engine.appc.properties import ShieldProperty
    full = _make_target_ship_at("Full", 0, 100, 0)
    low = _make_target_ship_at("Low", 0, 100, 0)
    for ship, frac in ((full, 1.0), (low, 0.1)):
        ss = ShieldSubsystem("S")
        for f in range(ShieldProperty.NUM_SHIELDS):
            ss.SetMaxShields(f, 100.0)
            ss.SetCurrentShields(f, 100.0 * frac)
        ship._shield_subsystem = ss

    inst, _ = _make_select_target(ours, "Full", "Low")
    assert inst.GetTargetRating(low) > inst.GetTargetRating(full)


def test_damage_dealt_to_us_boosts_target_rating():
    """fDamage factor (positive weight 1.0) — targets that have damaged
    us recently rate higher."""
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    ours = ShipClass(); ours.SetTranslateXYZ(0, 0, 0)
    ours._hull = HullSubsystem("OursHull"); ours._hull.SetMaxCondition(1000.0)
    pSet.AddObjectToSet(ours, "Ours")
    aggro = _make_target_ship_at("Aggro", 0, 100, 0)
    peaceful = _make_target_ship_at("Peaceful", 0, 100, 0)

    inst, _ = _make_select_target(ours, "Aggro", "Peaceful")
    # Simulate damage from Aggro into our running total.
    inst.dDamageReceived = {aggro.GetObjID(): 0.5}
    assert inst.GetTargetRating(aggro) > inst.GetTargetRating(peaceful)


def test_priority_info_boosts_target_rating():
    """fPriority factor (positive weight 1.0) — ObjectGroupWithInfo
    targets with a Priority key in their info dict rate higher."""
    from engine.appc.objects import ObjectGroupWithInfo
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    ours = ShipClass(); ours.SetTranslateXYZ(0, 0, 0)
    pSet.AddObjectToSet(ours, "Ours")
    vip = _make_target_ship_at("VIP", 0, 100, 0)
    grunt = _make_target_ship_at("Grunt", 0, 100, 0)

    from AI.Preprocessors import SelectTarget
    pp = PreprocessingAI_Create(ours, "TestSel")
    grp = ObjectGroupWithInfo()
    grp.AddNameAndInfo("VIP", {"Priority": 10.0})
    grp.AddNameAndInfo("Grunt", {})
    inst = SelectTarget(grp); inst.pCodeAI = pp
    pp.SetPreprocessingMethod(inst, "Update")

    assert inst.GetTargetRating(vip) > inst.GetTargetRating(grunt)


def test_current_target_gets_is_target_bonus():
    """fIsTarget factor (positive weight 1.0) — when the ship's current
    target matches the rated target, rating gets a boost."""
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    ours = ShipClass(); ours.SetTranslateXYZ(0, 0, 0)
    pSet.AddObjectToSet(ours, "Ours")
    current = _make_target_ship_at("Current", 0, 100, 0)
    other = _make_target_ship_at("Other", 0, 100, 0)
    ours.SetTarget(current)

    inst, _ = _make_select_target(ours, "Current", "Other")
    inst.bSetShipTarget = 1
    assert inst.GetTargetRating(current) > inst.GetTargetRating(other)


def test_rating_returns_minus_one_when_ship_is_none():
    """SDK contract: pCodeAI.GetShip() returning None → rating -1.0."""
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    target = _make_target_ship_at("X", 0, 100, 0)

    from AI.Preprocessors import SelectTarget
    pp = PreprocessingAI_Create(None, "TestSel")
    grp = ObjectGroup(); grp.AddName("X")
    inst = SelectTarget(grp); inst.pCodeAI = pp
    assert inst.GetTargetRating(target) == -1
```

- [ ] **Step 7.3: Run; expect fails or engine-gap escalations**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_select_target_rating.py -v`

Expected: most tests should PASS once the prior tasks land. If any fail because:
- SDK calls a method that doesn't exist (e.g. `pHull.GetCombinedConditionPercentage` not present on HullSubsystem), STOP and report. Land an engine fix in a separate commit, then re-run.
- `_make_target_ship_at` doesn't set up the target the way `GetTargetRating` reads it (e.g. expects `pTarget.GetWorldLocation` rather than `GetTranslate`), update the test fixture, not the SDK class.

**ESCALATION POLICY**: same as Slice A's Tasks 7-8. Each engine gap lands as its own small commit BEFORE the test commit.

- [ ] **Step 7.4: Regression sweep**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit -q -k "select_target or condition or builder_ai or ai_driver" 2>&1 | tail -3`
Expected: green.

- [ ] **Step 7.5: Commit**

```bash
git add tests/unit/test_select_target_rating.py
git commit -m "test(ai): SelectTarget.GetTargetRating factor-by-factor regression"
```

(Engine-gap fixes that surfaced during 7.3 land as separate commits before this one.)

---

## Task 8: `SelectTarget.Update` + external-`SetTarget`-dispatch chain

Drive a full `SelectTarget.Update(dEndTime)` and confirm: (a) the chosen target is the highest-rated of the candidates, (b) `pShip.SetTarget(chosen)` was called when `bSetShipTarget=1`, (c) every AI in the contained subtree with `"SetTarget"` in its external functions had its named method invoked with the target name.

**Files:**
- Test: `tests/unit/test_select_target_dispatch.py` (new)

- [ ] **Step 8.1: Write the failing tests**

Create `tests/unit/test_select_target_dispatch.py`:

```python
"""Unit tests for SelectTarget.Update + external-SetTarget-dispatch
chain. Verifies the chosen target gets propagated to the ship and to
every leaf AI registered via RegisterExternalFunction."""
import pytest

import App
from engine.appc.ai import (
    PreprocessingAI_Create, PlainAI_Create, PriorityListAI_Create,
)
from engine.appc.objects import ObjectGroup
from engine.appc.ships import ShipClass
from engine.appc.subsystems import HullSubsystem


def _reset_app_state():
    App.g_kSetManager._sets.clear()
    if hasattr(App.g_kEventManager, "_method_handlers"):
        App.g_kEventManager._method_handlers.clear()


@pytest.fixture(autouse=True)
def _isolate():
    _reset_app_state()
    yield
    _reset_app_state()


def _setup_scene_with_three_targets():
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    ours = ShipClass(); ours.SetTranslateXYZ(0, 0, 0)
    ours._hull = HullSubsystem("H"); ours._hull.SetMaxCondition(1000.0)
    pSet.AddObjectToSet(ours, "Ours")

    # 3 targets in front, at distances 50, 200, 500.
    t1 = ShipClass(); t1.SetTranslateXYZ(0, 50, 0)
    t1._hull = HullSubsystem("H"); t1._hull.SetMaxCondition(1000.0)
    pSet.AddObjectToSet(t1, "Close")
    t2 = ShipClass(); t2.SetTranslateXYZ(0, 200, 0)
    t2._hull = HullSubsystem("H"); t2._hull.SetMaxCondition(1000.0)
    pSet.AddObjectToSet(t2, "Mid")
    t3 = ShipClass(); t3.SetTranslateXYZ(0, 500, 0)
    t3._hull = HullSubsystem("H"); t3._hull.SetMaxCondition(1000.0)
    pSet.AddObjectToSet(t3, "Far")
    return ours, t1, t2, t3


def _wire_select_target(ours, *target_names):
    from AI.Preprocessors import SelectTarget
    pp = PreprocessingAI_Create(ours, "SelectPP")
    grp = ObjectGroup()
    for n in target_names:
        grp.AddName(n)
    inst = SelectTarget(grp); inst.pCodeAI = pp
    pp.SetPreprocessingMethod(inst, "Update")
    return inst, pp


def test_update_picks_closest_target_under_default_weights():
    """Default weights → distance dominates; closest target wins."""
    ours, close, mid, far = _setup_scene_with_three_targets()
    inst, pp = _wire_select_target(ours, "Close", "Mid", "Far")
    inst.Update(dEndTime=999.0)
    assert inst.sCurrentTarget == "Close"


def test_update_calls_set_target_on_ship_when_bSetShipTarget_is_one():
    """bSetShipTarget=1 (default) → pShip.SetTarget(pChosen) fires."""
    ours, close, _mid, _far = _setup_scene_with_three_targets()
    inst, _pp = _wire_select_target(ours, "Close")
    assert inst.bSetShipTarget == 1
    inst.Update(dEndTime=999.0)
    assert ours.GetTarget() is close


def test_update_does_not_set_ship_target_when_disabled():
    """DontSetShipTarget() → pShip.SetTarget is NOT called."""
    ours, _close, _mid, _far = _setup_scene_with_three_targets()
    inst, _pp = _wire_select_target(ours, "Close")
    inst.DontSetShipTarget()
    ours.SetTarget(None)  # baseline
    inst.Update(dEndTime=999.0)
    assert ours.GetTarget() is None


def test_update_dispatches_set_target_to_contained_leaf_with_registered_function():
    """A PlainAI inside the contained tree, registered with
    RegisterExternalFunction("SetTarget", {"FunctionName": "SetObj"}),
    has its `SetObj(target_name)` method called when SelectTarget picks."""
    ours, _close, _mid, _far = _setup_scene_with_three_targets()
    inst, pp = _wire_select_target(ours, "Close", "Mid", "Far")

    # Build a leaf that registers a SetTarget hook + records calls.
    leaf = PlainAI_Create(ours, "Leaf")
    received = []

    class _Inst:
        def SetObj(self, name):
            received.append(name)

    leaf._script_instance = _Inst()
    leaf.RegisterExternalFunction("SetTarget", {"FunctionName": "SetObj"})
    pp.SetContainedAI(leaf)

    inst.Update(dEndTime=999.0)
    assert received == ["Close"]


def test_update_with_no_targets_returns_skip_dormant():
    """SDK contract: bCallSetTargetFuncsWithNoTarget=0 (default) +
    no targets in group → return PS_SKIP_DORMANT."""
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    ours = ShipClass()
    ours._hull = HullSubsystem("H"); ours._hull.SetMaxCondition(1000.0)
    pSet.AddObjectToSet(ours, "Ours")

    inst, _pp = _wire_select_target(ours)  # empty target group
    result = inst.Update(dEndTime=999.0)
    assert result == App.PreprocessingAI.PS_SKIP_DORMANT
```

- [ ] **Step 8.2: Run; expect fails or escalations**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_select_target_dispatch.py -v`

Expected: tests likely surface a small number of additional engine gaps. Common candidates:
- `SelectTarget.CallSetTargetFunctions` looking up an SDK helper we don't have.
- `pAI.GetID()` round-trip via `_AdditionalSetTargetAITrees` list.
- Module-level lookup of named functions on script instances.

Each gap → small engine commit, then re-run. STOP and report novel gaps that aren't single-line stubs.

- [ ] **Step 8.3: Commit**

```bash
git add tests/unit/test_select_target_dispatch.py
git commit -m "test(ai): SelectTarget.Update + SetTarget dispatch chain end-to-end"
```

---

## Task 9: SelectTarget under a PriorityListAI integration test

Stress the slice with a more realistic configuration: SelectTarget wraps a `PriorityListAI` that contains 2 candidate AI branches. Run multiple ticks. Confirm: target propagates correctly, damage-event integration shifts preference, switching targets re-fires the SetTarget chain.

**Files:**
- Test: `tests/integration/test_select_target_in_priority_list.py` (new)

- [ ] **Step 9.1: Write the failing tests**

Create `tests/integration/test_select_target_in_priority_list.py`:

```python
"""Integration: SelectTarget under a PriorityListAI containing 2
candidate AI branches. Validates dispatch + target propagation across
multiple ticks + damage-event re-rating."""
import pytest

import App
from engine.appc.ai import (
    PreprocessingAI_Create, PlainAI_Create, PriorityListAI_Create,
    ArtificialIntelligence,
)
from engine.appc.ai_driver import tick_ai
from engine.appc.events import TGEvent_Create, WeaponHitEvent
from engine.appc.objects import ObjectGroup
from engine.appc.ships import ShipClass
from engine.appc.subsystems import HullSubsystem


def _reset_app_state():
    App.g_kSetManager._sets.clear()
    if hasattr(App.g_kEventManager, "_method_handlers"):
        App.g_kEventManager._method_handlers.clear()


@pytest.fixture(autouse=True)
def _isolate():
    _reset_app_state()
    yield
    _reset_app_state()


def _build_scene():
    pSet = App.SetClass_Create(); pSet.SetName("S")
    App.g_kSetManager._sets["S"] = pSet
    ours = ShipClass(); ours.SetTranslateXYZ(0, 0, 0)
    ours._hull = HullSubsystem("H"); ours._hull.SetMaxCondition(1000.0)
    pSet.AddObjectToSet(ours, "Ours")
    a = ShipClass(); a.SetTranslateXYZ(0, 100, 0)
    a._hull = HullSubsystem("H"); a._hull.SetMaxCondition(1000.0)
    pSet.AddObjectToSet(a, "Alpha")
    b = ShipClass(); b.SetTranslateXYZ(0, 500, 0)
    b._hull = HullSubsystem("H"); b._hull.SetMaxCondition(1000.0)
    pSet.AddObjectToSet(b, "Bravo")
    return ours, a, b


def _build_tree(ours):
    from AI.Preprocessors import SelectTarget
    branch_alpha = PlainAI_Create(ours, "BranchAlpha")
    branch_bravo = PlainAI_Create(ours, "BranchBravo")

    recvA, recvB = [], []
    class _AInst:
        def SetTarget(self, name): recvA.append(name)
    class _BInst:
        def SetTarget(self, name): recvB.append(name)
    branch_alpha._script_instance = _AInst()
    branch_bravo._script_instance = _BInst()
    branch_alpha.RegisterExternalFunction(
        "SetTarget", {"FunctionName": "SetTarget"})
    branch_bravo.RegisterExternalFunction(
        "SetTarget", {"FunctionName": "SetTarget"})

    pList = PriorityListAI_Create(ours, "Choices")
    pList.AddAI(branch_alpha, priority=1)
    pList.AddAI(branch_bravo, priority=2)

    pp = PreprocessingAI_Create(ours, "SelectPP")
    grp = ObjectGroup()
    grp.AddName("Alpha"); grp.AddName("Bravo")
    inst = SelectTarget(grp); inst.pCodeAI = pp
    pp.SetPreprocessingMethod(inst, "Update")
    pp.SetContainedAI(pList)
    return inst, pp, recvA, recvB


def test_first_tick_dispatches_chosen_to_all_branches():
    """Both leaves are registered for SetTarget → both receive the
    same chosen name on first Update."""
    ours, _a, _b = _build_scene()
    inst, pp, recvA, recvB = _build_tree(ours)
    tick_ai(pp, game_time=0.0)
    # Default weights → Alpha (closer) wins.
    assert recvA == ["Alpha"]
    assert recvB == ["Alpha"]


def test_target_change_re_dispatches_to_branches():
    """When SelectTarget picks a different target on a subsequent
    Update, branches receive the new name."""
    ours, _a, b = _build_scene()
    inst, pp, recvA, recvB = _build_tree(ours)
    # Force initial pick.
    tick_ai(pp, game_time=0.0)
    # Now boost Bravo via simulated damage so it outweighs Alpha's
    # distance advantage.
    inst.dDamageReceived = {b.GetObjID(): 100.0}
    inst.pCodeAI.ForceUpdate()
    tick_ai(pp, game_time=10.0)
    assert recvA[-1] == "Bravo"
    assert recvB[-1] == "Bravo"


def test_damage_event_accumulates_via_broadcast_handler():
    """When a WeaponHitEvent is broadcast with the firing object being
    a target in our group, SelectTarget.DamageEvent records the
    damage into dDamageReceived for that source's ObjID."""
    ours, _a, b = _build_scene()
    inst, pp, _recvA, _recvB = _build_tree(ours)
    # First tick wires the broadcast handler.
    tick_ai(pp, game_time=0.0)

    evt = WeaponHitEvent()
    evt.SetEventType(App.ET_WEAPON_HIT)
    evt.SetSource(b)
    evt.SetDamage(150.0)
    App.g_kEventManager.AddEvent(evt)

    # Damage gets recorded — expressed as fraction of hull max.
    expected = 150.0 / ours._hull.GetMaxCondition()
    assert b.GetObjID() in inst.dDamageReceived
    assert abs(inst.dDamageReceived[b.GetObjID()] - expected) < 1e-9
```

- [ ] **Step 9.2: Run; expect fails or small escalations**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/integration/test_select_target_in_priority_list.py -v`

Expected: the first test should pass once Task 8 lands. The damage-event test may surface integration gaps if the broadcast-handler registration doesn't connect correctly. Each gap → small commit, then re-run.

- [ ] **Step 9.3: Regression sweep**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit tests/integration --continue-on-collection-errors -q -k "select or condition or builder_ai or event_manager or object_group or proximity or ai_driver or ai_primitives or stay or goforward or turn or intercept or ship_motion or events or weapon_hit" 2>&1 | tail -3`
Expected: green.

- [ ] **Step 9.4: Commit**

```bash
git add tests/integration/test_select_target_in_priority_list.py
git commit -m "test(ai): SelectTarget integration under PriorityListAI with damage-event re-rating"
```

---

## Task 10: Update deferred AI-runtime doc

Strike Slice B; mention Slice C/D/E forward refs.

**Files:**
- Modify: [`docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md`](../deferred/2026-05-18-ship-ai-runtime.md)

- [ ] **Step 10.1: Update the "Follow-up after BuilderAI + ConditionScript" section**

In [`docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md`](../deferred/2026-05-18-ship-ai-runtime.md), find the section added by Slice A's Task 10. Update the Slice B bullet:

```markdown
### Follow-up after BuilderAI + ConditionScript (Slice A complete)

The BasicAttack roadmap now has its foundation. Next slices, in order:
- **Slice B**: ✅ done in [SelectTarget plan](../plans/2026-05-19-select-target-preprocessor.md). SelectTarget loads via `_SDKFinder`, picks targets via weighted-factor rating, propagates the chosen target through the external-`SetTarget`-dispatch chain. AI-driver preprocess dispatch now widens to pass `dEndTime` to 1-arg methods.
- **Slice C**: `FireScript` preprocessor port (~1000 LOC). Sits on the SelectTarget infrastructure; consumes the propagated target.
- **Slice D**: PlainAI sub-graphs that FedAttack/NonFedAttack splice in (`TorpRun`, `StationaryAttack`, `TurnToAttack`, `SweepPhasers`, `ICOMove`, `WarpBeforeDeath`, `EvadeTorps`).
- **Slice E**: `NonFedAttack`/`FedAttack` `CreateAI` assembly + visible mission where a hostile flies in and opens fire.
```

- [ ] **Step 10.2: Run the full relevant suite one final time**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit tests/integration --continue-on-collection-errors -q -k "select or condition or builder_ai or event_manager or object_group or proximity or ai_driver or ai_primitives or stay or goforward or turn or intercept or ship_motion or events or weapon_hit" 2>&1 | tail -3`
Expected: green (modulo pre-existing native-binding collection errors).

- [ ] **Step 10.3: Commit**

```bash
git add docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md
git commit -m "docs(deferred): close Slice B + note C/D/E forward refs"
```

---

## Out of scope (deferred to Slices C–E)

- `FireScript` preprocessor — Slice C. Sits on the SelectTarget infrastructure from this slice.
- Compound sub-graphs (`TorpRun`, `StationaryAttack`, `TurnToAttack`, `SweepPhasers`, `ICOMove`, `WarpBeforeDeath`, `EvadeTorps`) — Slice D.
- `FedAttack`/`NonFedAttack` `CreateAI` assembly + visible smoke (hostile opens fire) — Slice E.
- Sensor-visibility filter (`TargetVisible`) — orthogonal subsystem.
- `OptimizedSelectTarget` C-backed replacement — never; we run the Python class.

These remain in [docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md](../deferred/2026-05-18-ship-ai-runtime.md).
