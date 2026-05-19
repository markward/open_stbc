# BuilderAI Activation + ConditionScript Evaluation — Design

**Status:** brainstormed 2026-05-18. Next step: implementation plan in `docs/superpowers/plans/`.

**Slice A of the BasicAttack roadmap.** Slices B–E (`SelectTarget` preprocessor, `FireScript` preprocessor, Compound sub-graphs, `FedAttack`/`NonFedAttack` assembly + visible smoke) sit on top of this foundation and are scoped separately.

**Builds on:** [Ship AI Intercept slice](2026-05-18-ship-ai-intercept-design.md) (merged 2026-05-18 as `b662144` + `a65fdd1`) — the AI driver, motion integrator, and condition wiring this slice extends.

**Pulls forward from:** [Ship AI Runtime deferred plan](../deferred/2026-05-18-ship-ai-runtime.md) — partially closes Step 6 (`ConditionScript` actually evaluates) and lays the foundation for Step 5 item 6 (`AI.Compound.BasicAttack`).

## Goal

Make `BuilderAI` actually construct AI trees from its captured dependency graph, and make `ConditionScript_Create` actually instantiate the SDK condition class so events can drive `SetStatus`. After this slice, a real SDK Compound that uses BuilderAI (starting with `CallDamageAI`, the smallest such consumer) can be loaded without crashing, and any ConditionScript whose class doesn't need engine surfaces we lack will instantiate cleanly. Two specific conditions — `ConditionExists` and `ConditionInRange` — are pinned end-to-end so future combat slices have confirmed alive/range gating to consume.

## Non-goals

- Running the full `FedAttack`/`NonFedAttack` tree. Those depend on `FireScript`, `SelectTarget`, and ~30 sub-graphs that are Slices B–E. The integration smoke loads `CallDamageAI` only — the smallest real SDK Compound that uses BuilderAI (579 LOC, 53 blocks).
- Making all 30 SDK conditions work end-to-end. Mechanism plus 2 pinned conditions; the remaining 28 try-eager-fallback-lazy and stay at their default status until a future slice fills in the engine gap a specific consumer needs.
- Per-tick polling of conditions. SDK condition design is event-driven (object-group enter/exit, damage events, timers); the slice wires the existing event manager to drive `SetStatus`, not a per-tick poll loop. The exception is `ProximityCheck` which gets a per-tick evaluator since the SDK relies on it for range gating.
- Visible payoff. This slice is foundation work for the combat AI roadmap; nothing user-visible changes. The headline payoff lands in Slice E.

## Architecture

### BuilderAI activation (eager, first-tick)

`engine/appc/ai_driver.py` gains a `_tick_builder(ai, game_time)` branch dispatched before `_tick_preprocessing` for `BuilderAI` instances. On the first tick the driver sees an un-activated BuilderAI:

1. Topologically sort `_blocks` by `_dependencies` so each block is built after the blocks it depends on.
2. For each block in sorted order, look up the named builder function (e.g. `"BuilderCreate7"`) in the BuilderAI's `_module_name` module: `getattr(__import__(module_name), func_name)`.
3. Call `BuilderCreate7(pShip, *deps_results, **dep_objects)`. The function returns a constructed AI (or `None` if the builder skips this block).
4. Record the result. The last block built (the one nothing else depends on, by sort order) becomes the BuilderAI's `_contained_ai`.
5. Set `ai._activated = True`.

On subsequent ticks `_tick_builder` skips activation and delegates to standard `PreprocessingAI` dispatch (which runs the contained AI). If any builder function raises, the BuilderAI marks `ai._activation_failed = True` with the error stored in `ai._activation_error`, transitions to `US_DONE`, and future ticks short-circuit. Cyclic dependencies are detected during topological sort and produce the same failure path with the cycle's block names in the error.

### ConditionScript eager instantiation with graceful fallback

`engine/appc/ai.py`'s `ConditionScript.__init__` (or the `_Create` factory) does:

```python
try:
    mod = _import_dotted(module_name)   # walks "Conditions.ConditionInRange"
    cls = getattr(mod, class_name)
    self._instance = cls(self, *args)
except Exception as e:
    self._instance = None
    self._init_error = (type(e).__name__, str(e))
```

The instance, once created, wires its own event handlers on `App.g_kEventManager` and calls back into `self._condition.SetStatus(...)` over time. The existing `TGCondition.SetStatus` machinery (from prior slices) fires registered `TGConditionHandler`s — `ConditionalAI` is already such a handler and re-evaluates its contained-AI gating when status flips.

If a condition class can't be imported or its constructor raises (e.g. it references an engine surface we don't have), the fallback keeps `_instance = None` and the ConditionScript stays at its default `_status = 0`. Future slices that need a specific condition will fix the gap.

### Pinned conditions: `ConditionExists`, `ConditionInRange`

These two are explicit slice scope. Implementing them surfaces engine gaps that the slice fills:

**`ConditionExists(pCodeCondition, sObject)`** needs:
- `App.TGPythonInstanceWrapper()` with `SetPyWrapper(self)` — instance-method dispatch from event handlers.
- `App.ObjectGroup()` with `AddName(s)`, `GetActiveObjectTuple()`, `SetEventFlag(ENTERED_SET)`, `GetObjID()`.
- `App.g_kEventManager.AddBroadcastPythonMethodHandler(eType, wrapper, "MethodName", target)` — named-method dispatch tied to a target object/group.
- `App.ET_DELETE_OBJECT_PUBLIC`, `App.ET_OBJECT_GROUP_OBJECT_ENTERED_SET` event-type constants.

**`ConditionInRange(pCodeCondition, fDistance, sObject1, *lsObjectNames)`** needs everything `ConditionExists` needs, plus:
- `App.ProximityCheck_Create(eEventType)` and `AddObjectToCheckList`, `SetRadius` — already exist as data stubs from prior slices; this slice adds per-tick evaluation that fires the event type when objects cross the radius boundary.
- A per-tick proximity evaluation step in `GameLoop.tick` between `tick_all_ai` and `tick_all_ship_motion` so range transitions fire promptly.

Other 28 conditions get tried via the fallback path but are not required to work end-to-end this slice.

## Components

| File | Change | Surface |
|---|---|---|
| `engine/appc/ai.py` | `BuilderAI` gains `_activated`, `_activation_failed`, `_activation_error` fields. `ConditionScript.__init__` does eager `cls(self, *args)` with try/except + records `_init_error`. Helper `_import_dotted(path)` walks dotted module paths via `__import__`. | ~60 LOC |
| `engine/appc/ai_driver.py` | New `_tick_builder(ai, game_time)` branch dispatched before `_tick_preprocessing` in the main `tick_ai` switch. Topological sort + module-function dispatch on first tick; delegates to standard preprocessing thereafter. | ~70 LOC |
| `engine/appc/sets.py` (or new `engine/appc/object_group.py`) | `ObjectGroup` with `AddName`, `GetActiveObjectTuple` (walks `g_kSetManager._sets` for matching names), `SetEventFlag`, `GetObjID`. Class constant `ENTERED_SET`. | ~70 LOC |
| `engine/appc/events.py` | `g_kEventManager.AddBroadcastPythonMethodHandler(eType, wrapper, method_name, target=None)`, `RemoveBroadcastHandler(eType, wrapper, method_name, target=None)`. Dispatch in `AddEvent` walks the handler list and calls `getattr(wrapper, method_name)(evt)` for matching `(eType, target)` pairs. `TGPythonInstanceWrapper` class with `SetPyWrapper(self)`, `AddPythonMethodHandlerForInstance(eType, method_name)` (single-instance variant). Event-type constants: `ET_DELETE_OBJECT_PUBLIC`, `ET_OBJECT_GROUP_OBJECT_ENTERED_SET`, `ET_OBJECT_GROUP_OBJECT_EXITED_SET`, `ET_WEAPON_HIT` (existing), `ET_CONDITION_ATK_FORGIVE`. | ~150 LOC |
| `engine/appc/planet.py` | `ProximityManager.GetNearObjects(point, radius)` filters `_objects` by world-space distance. New per-set `ProximityCheck` evaluator that compares against `_check_objects` each tick and fires `_event_type` events when objects cross the radius boundary. | ~50 LOC |
| `engine/core/loop.py` | One new call between `tick_all_ai` and `tick_all_ship_motion`: `evaluate_proximity_checks()` walks all sets' proximity managers and fires boundary-crossing events. | ~10 LOC |
| `engine/host_loop.py` reset hook | On mission swap, clear `g_kEventManager`'s handler list so stale handlers from the prior mission don't fire against new state. Hooked into the existing `reset_sdk_globals()` path. | ~5 LOC |

## Test plan

### Unit tests

| File | Count | Coverage |
|---|---|---|
| `tests/unit/test_builder_ai_activation.py` (new) | ~10 | Synthetic 3-block graph builds in dep order; activation idempotent (second tick doesn't rebuild); last block becomes `_contained_ai`; missing builder function → `_activation_failed=True`, status `US_DONE`, no crash; cyclic dependency → `_activation_failed`; builder raising → `_activation_failed`; dep_objects passed as kwargs; dep results passed as positional args in declaration order; builder returning None mid-graph → skipped, dependents still build; builder returning None for the last block → `_activation_failed`. |
| `tests/unit/test_condition_script_instantiate.py` (new) | ~6 | `ConditionScript_Create("Conditions.ConditionExists", "ConditionExists", "ship")` instantiates the class; `_instance` is set; missing module → `_init_error` recorded, `_instance` is None, no raise; missing class → same fallback; class constructor raising → fallback; `pCodeCondition.SetStatus(...)` from the instance fires `ConditionalAI.ConditionChanged`. |
| `tests/unit/test_object_group.py` (new) | ~5 | `AddName(s)` records; `GetActiveObjectTuple()` returns currently-in-set objects matching names; `SetEventFlag(ObjectGroup.ENTERED_SET)` records; multi-name groups; idempotent re-add. |
| `tests/unit/test_event_manager_broadcast.py` (new) | ~5 | `AddBroadcastPythonMethodHandler(et, wrapper, method_name, target_obj)` dispatches `wrapper.<method_name>(evt)` on matching `AddEvent`; `RemoveBroadcastHandler` undoes the registration; multiple handlers for the same event fan out; unrelated events don't fire; `target=None` matches all events of the type. |
| `tests/unit/test_proximity_manager_distance.py` (new) | ~4 | `GetNearObjects(point, radius)` filters by `||obj.GetWorldLocation() - point|| ≤ radius`; empty manager → empty tuple; objects beyond radius excluded; objects exactly at radius included. |
| `tests/unit/test_condition_exists.py` (new) | ~4 | Object in set at construction → status 1; object deleted via `ET_DELETE_OBJECT_PUBLIC` → status 0; object enters set later via `ET_OBJECT_GROUP_OBJECT_ENTERED_SET` → status 1; `SetTarget` changes the watched object name. |
| `tests/unit/test_condition_in_range.py` (new) | ~4 | Two objects in same set, ship 1 within `fDistance` of ship 2 → status 1 after first proximity-evaluation tick; pull ship 1 out of range → status 0; one object missing entirely → status 0; `SetTarget` changes the watched object name. |

### Integration test

| File | Count | Coverage |
|---|---|---|
| `tests/integration/test_builder_ai_call_damage_smoke.py` (new) | 2 | Load `AI.Compound.CallDamageAI`, call `CreateAI(pShip, sTargetName, sFriend, sEnemy)` (signature TBC by reading the SDK file at implementation time), drive the resulting AI through one `GameLoop.tick()`: (a) builder activation succeeded (`_activated=True`, `_activation_failed=False`); (b) `_contained_ai` is a non-None composite (PriorityList or Sequence). Doesn't assert per-tick behaviour or sub-tree correctness — that's Slice E. |

Total: ~38 new unit tests + 2 integration on top of the ~280 from prior slices.

### Visible verification

None this slice. Foundation work. The headline visible payoff lands in Slice E when `NonFedAttack`/`FedAttack` produce a hostile that opens fire on the player.

## File map

| File | Change | Lines (est) |
|---|---|---|
| `engine/appc/ai.py` | BuilderAI activation fields + ConditionScript eager instantiation + `_import_dotted` helper | ~60 |
| `engine/appc/ai_driver.py` | `_tick_builder` branch + topological sort | ~70 |
| `engine/appc/sets.py` | ObjectGroup with `AddName`/`GetActiveObjectTuple`/`SetEventFlag` | ~70 |
| `engine/appc/events.py` | Broadcast handler API, `TGPythonInstanceWrapper`, event-type constants | ~150 |
| `engine/appc/planet.py` | `GetNearObjects` real distance filter; per-tick `ProximityCheck` evaluator | ~50 |
| `engine/core/loop.py` | `evaluate_proximity_checks()` call site in `tick()` | ~10 |
| `engine/host_loop.py` | clear `g_kEventManager` handlers on mission swap | ~5 |
| `tests/unit/test_builder_ai_activation.py` | new, ~10 tests | ~180 |
| `tests/unit/test_condition_script_instantiate.py` | new, ~6 tests | ~110 |
| `tests/unit/test_object_group.py` | new, ~5 tests | ~80 |
| `tests/unit/test_event_manager_broadcast.py` | new, ~5 tests | ~100 |
| `tests/unit/test_proximity_manager_distance.py` | new, ~4 tests | ~70 |
| `tests/unit/test_condition_exists.py` | new, ~4 tests | ~100 |
| `tests/unit/test_condition_in_range.py` | new, ~4 tests | ~100 |
| `tests/integration/test_builder_ai_call_damage_smoke.py` | new, ~2 tests | ~80 |
| `docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md` | mark Step 6 partially complete; note Slice B–E forward refs | ~10 |

Total: ~1245 LOC across ~16 files. About 30% larger than the Motion slice; comparable in shape to a moderate-engine slice.

## Implementation sequencing (preview for the plan)

1. **Engine primitives — `ObjectGroup` + event-manager broadcast surface.** Smallest pieces; unblock everything else. Their unit tests pin the contract.
2. **`ProximityCheck` per-tick evaluator + `GameLoop` wiring.** Independent of BuilderAI/ConditionScript work.
3. **BuilderAI activation.** Synthetic-graph unit tests first, then the `_tick_builder` branch.
4. **ConditionScript eager instantiation + fallback.** Mechanism tests with hand-rolled fake conditions.
5. **`ConditionExists` end-to-end.** Surfaces any remaining gap in object-group / event-manager wiring.
6. **`ConditionInRange` end-to-end.** Surfaces any remaining gap in proximity machinery.
7. **`CallDamageAI` integration smoke + deferred-doc update.**

Each task = one TDD cycle. Same shape as the Motion and Intercept slices. Expect 2-4 engine-gap escalations along the way (similar to the Subtract/Unitize/proximity-iter pattern from Intercept).

## Risks + open questions

1. **`ConditionScript` lifecycle on mission swap.** SDK conditions register handlers on `g_kEventManager`. We have `ship_lifecycle.reset()` for ship registry but no equivalent for event handlers. Stale handlers from a prior mission could fire against new mission state. Mitigation: this slice adds a `g_kEventManager` handler-clear to the existing `reset_sdk_globals()` path. Cost: ~5 LOC.

2. **Per-tick proximity evaluation cost.** `ProximityCheck` runs every 16.7ms across all checks across all sets. For dozens of checks and dozens of objects per set, this is O(checks × objects) per tick. Real combat scenarios likely have ≤10 checks and ≤20 objects — fine. Worth flagging for the BasicAttack slice when full FedAttack trees create many ConditionInRange instances.

3. **Topological-sort failure modes.** Cyclic dependency would loop. The activation path uses Kahn's algorithm (decrement in-degree as nodes are scheduled); a non-empty unscheduled set at completion indicates a cycle, which triggers the standard `_activation_failed` path. Real SDK graphs aren't cyclic — `BuilderCreateN` functions cleanly fan out from leaves.

4. **Module-import caching.** `__import__("Conditions.ConditionInRange")` returns the top-level `Conditions` package; the `_import_dotted` helper walks dotted parts. The conftest's `_SDKFinder` handles nested SDK modules so the import should work — verified by unit tests in `test_condition_script_instantiate.py`.

5. **Builder result must be an AI, not None for the LAST block.** Some SDK `BuilderCreate` functions could return None mid-graph (e.g. conditional construction). Mid-graph None is fine — dependents skip the missing block. Last-block None is `_activation_failed`. Real SDK BuilderCreate functions in `CallDamageAI`/`NonFedAttack`/`FedAttack` return constructed AIs unconditionally (verified by grep).

6. **Event-manager dispatch order.** When multiple handlers register for the same `(eType, target)` pair, dispatch order matters for some SDK conditions that rely on observed state from prior handlers. We dispatch in registration order; matches Python list semantics. If a condition turns out to require LIFO ordering, the dispatch list can be reversed without breaking the contract.

7. **Slice scope creep.** Implementing `ConditionInRange` end-to-end requires real proximity evaluation, which is non-trivial work. If the proximity-check implementation surfaces deeper gaps (e.g. the SDK's `ProximityCheck` expects events with specific bidirectional trigger types — `TT_INSIDE` and `TT_OUTSIDE`), the slice could grow. Mitigation: defer `ConditionInRange` to a Slice A.5 if the proximity machinery is too heavy. Try one tick of evaluation logic first; if a single test reveals the gap is bigger than ~150 LOC, escalate and split.

## What this unlocks

After this slice merges:
- Slice B (`SelectTarget` preprocessor) can be developed against a working BuilderAI activator + condition system.
- Slice C (`FireScript` preprocessor) likewise.
- The 30 SDK condition modules can be added one at a time as Slices B–E discover they're needed; the mechanism is in place and the pattern (surface engine gaps, fix them, pin with regression tests) is established.
- `ConditionalAI` (already wired in the Steps 1-3 slice) now has real conditions to gate on, not just data-bag specs.
- The full BasicAttack roadmap stops being blocked on foundation work.
