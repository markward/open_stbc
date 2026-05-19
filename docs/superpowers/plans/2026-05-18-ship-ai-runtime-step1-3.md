# Ship AI Runtime — Steps 1-3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `PlainAI` to load real SDK scripts, ship a `TimeSliceProcess`/`PythonMethodProcess` scheduler shim, and add an AI tick driver to the gameloop — proven end-to-end by a `PlainAI("Stay")` smoke test that fires `Update()` at 5 s cadence and writes zero motion setpoints.

**Architecture:** Three independent layers driven from `GameLoop.tick()` in [engine/core/loop.py](../../../engine/core/loop.py): (1) `PlainAI.SetScriptModule` does a real `__import__("AI.PlainAI.<name>")` and instantiates the class with `pCodeAI=self`; (2) a standalone scheduler in `engine/appc/time_slice.py` runs `TimeSliceProcess`-derived objects on game-time or real-time delays in priority order; (3) a tree-walker in `engine/appc/ai_driver.py` iterates every ship's `GetAI()` each tick and dispatches `PlainAI/PriorityListAI/SequenceAI/ConditionalAI/PreprocessingAI` per the SDK semantics. Steps 2 and 3 are deliberately *not* coupled — the AI driver tracks its own per-`PlainAI` next-update-game-time so the smoke test exercises Step 3 alone without needing TimeSliceProcess to be correct. Minimal ship motion stubs (record-only `SetSpeed` / `SetTargetAngularVelocityDirect`) are included so `Stay.Update()` doesn't AttributeError; the full PD/Bullet motion API stays deferred for the next slice.

**Tech Stack:** Python 3, pytest, existing `engine/appc/` Phase-1 shims, existing `_SDKFinder` in [tests/conftest.py](../../../tests/conftest.py) which loads `sdk/Build/scripts/AI/PlainAI/Stay.py` on demand.

---

## File Structure

| File | Responsibility |
|---|---|
| [`engine/appc/ai.py`](../../../engine/appc/ai.py) (modify) | `PlainAI.SetScriptModule` performs real import + instantiation; add `RegisterExternalFunction` + `GetExternalFunctions`; add `_next_update_time` and `_status` fields used by the driver |
| `engine/appc/time_slice.py` (new) | `TimeSliceProcess` + `PythonMethodProcess` class shims and a module-level `g_kAIManager` scheduler that owns registered processes and ticks them on game- or real-time |
| `engine/appc/ai_driver.py` (new) | `tick_all_ai(game_time)` walks every ship's `GetAI()` and dispatches the tree per AI-class type |
| [`engine/appc/ships.py`](../../../engine/appc/ships.py) (modify) | Record-only `SetSpeed(speed, direction, frame)` and `SetTargetAngularVelocityDirect(vec)` so `Stay.Update()` runs without error and tests can observe the setpoint |
| [`engine/core/loop.py`](../../../engine/core/loop.py) (modify) | After timer ticks, call `g_kAIManager.tick()` and then `tick_all_ai(game_time)` |
| [`App.py`](../../../App.py) (modify) | Re-export `TimeSliceProcess`, `PythonMethodProcess`, `g_kAIManager` so SDK code sees them via `App.*` |
| `tests/unit/test_plain_ai_script_loading.py` (new) | Step 1: real-import behaviour + `RegisterExternalFunction` round-trip |
| `tests/unit/test_time_slice.py` (new) | Step 2: scheduler semantics — delay, priority, game vs real time, reschedule |
| `tests/unit/test_ai_driver.py` (new) | Step 3: tree-walk semantics for each composite + cadence for PlainAI |
| `tests/integration/test_ai_stay_smoke.py` (new) | End-to-end: ship + `PlainAI("Stay")` + 11 s of gameloop → Update called 3× with zero setpoints |

---

## Task 1: PlainAI loads real script modules

**Files:**
- Modify: [`engine/appc/ai.py`](../../../engine/appc/ai.py) — `PlainAI` class (lines 219-244)
- Test: `tests/unit/test_plain_ai_script_loading.py` (new)

- [ ] **Step 1.1: Write the failing test for real script loading**

Create `tests/unit/test_plain_ai_script_loading.py`:

```python
import App
from engine.appc.ai import PlainAI, PlainAI_Create
from engine.appc.ships import ShipClass


def test_set_script_module_loads_real_class():
    """SetScriptModule('Stay') imports AI.PlainAI.Stay and instantiates Stay."""
    ship = ShipClass()
    pai = PlainAI_Create(ship, "TestStay")
    pai.SetScriptModule("Stay")
    inst = pai.GetScriptInstance()

    # Must be the real Stay class, not the _AIScriptInstance proxy.
    from AI.PlainAI import Stay as StayModule
    assert isinstance(inst, StayModule.Stay)


def test_script_instance_p_code_ai_points_back():
    """The loaded script's pCodeAI must point to the owning PlainAI."""
    ship = ShipClass()
    pai = PlainAI_Create(ship, "X")
    pai.SetScriptModule("Stay")
    assert pai.GetScriptInstance().pCodeAI is pai


def test_register_external_function_records_mapping():
    """BaseAI.SetExternalFunctions calls pCodeAI.RegisterExternalFunction(name, dict).
    The PlainAI must store the mapping so introspection works."""
    pai = PlainAI_Create(ShipClass(), "X")
    pai.RegisterExternalFunction("SetTarget", {"Name": "MySetTarget"})
    pai.RegisterExternalFunction("Foo", {"CodeID": 42, "FunctionName": "Bar"})
    funcs = pai.GetExternalFunctions()
    assert funcs["SetTarget"] == {"Name": "MySetTarget"}
    assert funcs["Foo"] == {"CodeID": 42, "FunctionName": "Bar"}


def test_stay_get_next_update_time_is_five_seconds():
    """Stay.GetNextUpdateTime returns 5.0 — sanity that the real module loads."""
    pai = PlainAI_Create(ShipClass(), "X")
    pai.SetScriptModule("Stay")
    assert pai.GetScriptInstance().GetNextUpdateTime() == 5.0


def test_set_script_module_replaces_instance():
    """Re-calling SetScriptModule swaps the script instance."""
    pai = PlainAI_Create(ShipClass(), "X")
    pai.SetScriptModule("Stay")
    first = pai.GetScriptInstance()
    pai.SetScriptModule("Stay")
    second = pai.GetScriptInstance()
    assert first is not second
```

- [ ] **Step 1.2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_plain_ai_script_loading.py -v`
Expected: 5 FAILs — `GetScriptInstance()` currently returns `_AIScriptInstance`, not `Stay.Stay`. `GetExternalFunctions` doesn't exist.

- [ ] **Step 1.3: Implement real script loading in `PlainAI`**

In [`engine/appc/ai.py`](../../../engine/appc/ai.py), replace `PlainAI` (lines 219-244) with:

```python
class PlainAI(ArtificialIntelligence):
    def __init__(self, pShip=None, name: str = ""):
        super().__init__(pShip, name)
        self._script_module: str = ""
        self._script_instance = None
        self._external_functions: dict = {}
        # Driver bookkeeping — first Update fires when game_time >= 0.0,
        # i.e. on the very first AI tick. Updated by ai_driver after each
        # Update() call using the script's GetNextUpdateTime().
        self._next_update_time: float = 0.0

    def SetScriptModule(self, module_name: str) -> None:
        """Import AI.PlainAI.<module_name> and instantiate <module_name>(pCodeAI=self).

        SDK pattern (BaseAI.py:14): the loaded class's __init__ takes pCodeAI
        as a positional arg and stores it on self. The script reaches back
        through self.pCodeAI.GetShip() for all motion + weapon calls.

        Falls back to the _AIScriptInstance data-bag if the module can't be
        imported or doesn't define the expected class — keeps Phase-1 mission
        init working for scripts we haven't validated yet.
        """
        self._script_module = module_name
        try:
            mod = __import__("AI.PlainAI." + module_name, None, None, [module_name])
            cls = getattr(mod, module_name, None)
            if cls is not None:
                self._script_instance = cls(self)
                return
        except Exception:
            pass
        # Fallback: data-bag for unimplemented scripts.
        self._script_instance = _AIScriptInstance(self)

    def GetScriptModule(self) -> str:
        return self._script_module

    def GetScriptInstance(self):
        if self._script_instance is None:
            self._script_instance = _AIScriptInstance(self)
        return self._script_instance

    def RegisterExternalFunction(self, name: str, mapping) -> None:
        """Record an externally-registered function name -> info dict.

        Called by BaseAI.SetExternalFunctions (sdk/.../AI/PlainAI/BaseAI.py:54)
        and by various Conditions/Preprocessors that want to expose a method
        to the AI driver. The mapping is opaque metadata — we store it
        verbatim so future reflection (target selection, weapon firing) can
        pull values back out.
        """
        self._external_functions[name] = mapping

    def GetExternalFunctions(self) -> dict:
        return dict(self._external_functions)

    def StopCallingActivate(self) -> None:
        pass
```

- [ ] **Step 1.4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_plain_ai_script_loading.py -v`
Expected: 5 PASS.

- [ ] **Step 1.5: Verify the existing AI-primitive tests still pass**

Run: `uv run pytest tests/unit/test_ai_primitives.py -v`
Expected: all green — `_AIScriptInstance` fallback path keeps the existing data-bag behaviour for unrecognised script modules.

- [ ] **Step 1.6: Commit**

```bash
git add engine/appc/ai.py tests/unit/test_plain_ai_script_loading.py
git commit -m "feat(ai): PlainAI.SetScriptModule loads real SDK scripts + RegisterExternalFunction"
```

---

## Task 2: TimeSliceProcess + PythonMethodProcess scheduler

**Files:**
- Create: `engine/appc/time_slice.py`
- Test: `tests/unit/test_time_slice.py` (new)

- [ ] **Step 2.1: Write the failing tests**

Create `tests/unit/test_time_slice.py`:

```python
from engine.appc.time_slice import (
    TimeSliceProcess, PythonMethodProcess, TimeSliceProcessManager,
)


def test_priority_constants_distinct():
    p = {TimeSliceProcess.UNSTOPPABLE, TimeSliceProcess.CRITICAL,
         TimeSliceProcess.NORMAL, TimeSliceProcess.LOW}
    assert len(p) == 4


def test_delay_round_trip():
    proc = TimeSliceProcess()
    proc.SetDelay(2.5)
    assert proc.GetDelay() == 2.5


def test_priority_round_trip():
    proc = TimeSliceProcess()
    proc.SetPriority(TimeSliceProcess.LOW)
    assert proc.GetPriority() == TimeSliceProcess.LOW


def test_delay_uses_game_time_round_trip():
    proc = TimeSliceProcess()
    proc.SetDelayUsesGameTime(1)
    assert proc.GetDelayUsesGameTime() == 1
    proc.SetDelayUsesGameTime(0)
    assert proc.GetDelayUsesGameTime() == 0


def test_python_method_process_set_function_invokes_method():
    """SDK signature: pmp.SetFunction(instance, method_name). Update()
    on the manager dispatches by calling getattr(instance, method_name)()."""
    class Holder:
        def __init__(self):
            self.calls = 0
        def Bump(self):
            self.calls += 1

    h = Holder()
    pmp = PythonMethodProcess()
    pmp.SetFunction(h, "Bump")
    pmp.SetDelay(0.1)
    pmp.SetDelayUsesGameTime(1)

    mgr = TimeSliceProcessManager()
    mgr.Add(pmp)
    mgr.tick(game_time=0.05, real_time=0.05)
    assert h.calls == 0
    mgr.tick(game_time=0.11, real_time=0.11)
    assert h.calls == 1


def test_priority_order_normal_runs_before_low():
    order = []
    class H:
        def __init__(self, tag): self.tag = tag
        def Go(self): order.append(self.tag)

    n = PythonMethodProcess(); n.SetFunction(H("N"), "Go"); n.SetDelay(0.1)
    n.SetDelayUsesGameTime(1); n.SetPriority(TimeSliceProcess.NORMAL)
    l = PythonMethodProcess(); l.SetFunction(H("L"), "Go"); l.SetDelay(0.1)
    l.SetDelayUsesGameTime(1); l.SetPriority(TimeSliceProcess.LOW)

    mgr = TimeSliceProcessManager()
    mgr.Add(l); mgr.Add(n)  # add LOW first to prove ordering by priority
    mgr.tick(game_time=0.11, real_time=0.11)
    assert order == ["N", "L"]


def test_game_time_vs_real_time_isolated():
    """Only the game-time process fires when game_time advances; the
    real-time process is dormant until real_time catches up."""
    fired = []
    class H:
        def __init__(self, tag): self.tag = tag
        def Go(self): fired.append(self.tag)

    g = PythonMethodProcess(); g.SetFunction(H("G"), "Go"); g.SetDelay(1.0)
    g.SetDelayUsesGameTime(1)
    r = PythonMethodProcess(); r.SetFunction(H("R"), "Go"); r.SetDelay(1.0)
    r.SetDelayUsesGameTime(0)

    mgr = TimeSliceProcessManager()
    mgr.Add(g); mgr.Add(r)
    mgr.tick(game_time=1.0, real_time=0.0)
    assert fired == ["G"]
    mgr.tick(game_time=1.0, real_time=1.0)
    assert fired == ["G", "R"]


def test_reschedule_after_fire():
    """After dispatch the process re-arms at next_fire += delay."""
    h_calls = []
    class H:
        def Go(self): h_calls.append(1)

    p = PythonMethodProcess(); p.SetFunction(H(), "Go"); p.SetDelay(1.0)
    p.SetDelayUsesGameTime(1)
    mgr = TimeSliceProcessManager()
    mgr.Add(p)
    mgr.tick(game_time=1.0, real_time=0.0)
    mgr.tick(game_time=1.5, real_time=0.0)  # not due yet
    mgr.tick(game_time=2.0, real_time=0.0)
    assert len(h_calls) == 2


def test_remove_stops_dispatch():
    fired = []
    class H:
        def Go(self): fired.append(1)
    p = PythonMethodProcess(); p.SetFunction(H(), "Go"); p.SetDelay(0.5)
    p.SetDelayUsesGameTime(1)
    mgr = TimeSliceProcessManager()
    mgr.Add(p)
    mgr.Remove(p)
    mgr.tick(game_time=1.0, real_time=0.0)
    assert fired == []
```

- [ ] **Step 2.2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_time_slice.py -v`
Expected: ImportError — module doesn't exist yet.

- [ ] **Step 2.3: Implement `engine/appc/time_slice.py`**

```python
"""TimeSliceProcess + PythonMethodProcess shim + scheduler.

Mirrors sdk/Build/scripts/App.py:4468-4511 — the per-tick scheduler the C++
engine uses to drive Python callbacks at game-time or real-time delays
with NORMAL/LOW priority bands (CRITICAL/UNSTOPPABLE are C++-internal,
exposed as constants for SDK code that references them).

Phase 1 model: a single TimeSliceProcessManager owns every registered
process. GameLoop.tick() calls manager.tick(game_time, real_time) once
per 60 Hz frame; the manager fires every process whose next_fire has
been reached, in priority order (UNSTOPPABLE=0 first, LOW=3 last —
lower int == higher priority, matching SDK enum order).
"""


class TimeSliceProcess:
    UNSTOPPABLE = 0
    CRITICAL = 1
    NORMAL = 2
    LOW = 3
    NUM_PRIORITIES = 4

    def __init__(self):
        self._priority: int = TimeSliceProcess.NORMAL
        self._delay: float = 0.0
        self._delay_uses_game_time: int = 1
        # Set on first Add() by the manager — absolute time of next fire
        # in the relevant time stream.
        self._next_fire: float = 0.0

    def SetPriority(self, p) -> None:
        self._priority = int(p)

    def GetPriority(self) -> int:
        return self._priority

    def SetDelay(self, d) -> None:
        self._delay = float(d)

    def GetDelay(self) -> float:
        return self._delay

    def SetDelayUsesGameTime(self, v) -> None:
        self._delay_uses_game_time = 1 if int(v) else 0

    def GetDelayUsesGameTime(self) -> int:
        return self._delay_uses_game_time

    def Update(self) -> None:
        """Default Update — overridden by PythonMethodProcess."""
        pass


class PythonMethodProcess(TimeSliceProcess):
    """SDK signature: pmp.SetFunction(instance, method_name).

    On dispatch, getattr(instance, method_name)() is invoked. The two-arg
    form matches sdk/.../AI/Setup.py and is the only form Python-side SDK
    code actually uses.
    """
    def __init__(self):
        super().__init__()
        self._instance = None
        self._method_name: str = ""

    def SetFunction(self, instance, method_name: str) -> None:
        self._instance = instance
        self._method_name = method_name

    def Update(self) -> None:
        if self._instance is None or not self._method_name:
            return
        getattr(self._instance, self._method_name)()


class TimeSliceProcessManager:
    """Module-level scheduler. One instance lives as g_kAIManager.

    GameLoop ticks the manager once per frame with the current game-time
    and real-time absolute clocks. The manager dispatches every process
    whose next_fire has been reached, lowest priority-int first.
    """
    def __init__(self):
        self._procs: list = []

    def Add(self, proc: TimeSliceProcess) -> None:
        # Snap next_fire to the current time stream's "now + delay" on
        # registration so SetDelay before Add behaves intuitively.
        # Manager doesn't know "now" here, so use 0 — manager.tick() will
        # interpret next_fire == 0 as "fire on the first tick where the
        # relevant clock reaches the configured delay."
        if proc not in self._procs:
            proc._next_fire = proc._delay
            self._procs.append(proc)

    def Remove(self, proc: TimeSliceProcess) -> None:
        if proc in self._procs:
            self._procs.remove(proc)

    def tick(self, game_time: float, real_time: float) -> None:
        """Fire every due process in priority order."""
        due = []
        for proc in self._procs:
            t = game_time if proc._delay_uses_game_time else real_time
            if t >= proc._next_fire:
                due.append((proc._priority, t, proc))
        due.sort(key=lambda triple: triple[0])
        for _prio, t_at_fire, proc in due:
            proc.Update()
            # Reschedule at next_fire += delay (avoids drift under
            # variable tick lengths; same semantics as TGTimer._advance).
            if proc._delay > 0:
                proc._next_fire += proc._delay
            else:
                # One-shot: push next_fire far enough out that the process
                # never fires again unless SetDelay re-arms it.
                proc._next_fire = float("inf")


# Module-level scheduler instance — App.py re-exports as g_kAIManager.
g_kAIManager = TimeSliceProcessManager()
```

- [ ] **Step 2.4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_time_slice.py -v`
Expected: 9 PASS.

- [ ] **Step 2.5: Re-export from App.py shim**

In [`App.py`](../../../App.py), add after the existing `engine.appc.ai` import block (around line 99-110):

```python
from engine.appc.time_slice import (
    TimeSliceProcess, PythonMethodProcess, g_kAIManager,
)
```

- [ ] **Step 2.6: Verify the re-export by importing through App**

Run: `uv run python -c "import App; print(App.TimeSliceProcess.NORMAL, App.PythonMethodProcess, App.g_kAIManager)"`
Expected: `2 <class 'engine.appc.time_slice.PythonMethodProcess'> <engine.appc.time_slice.TimeSliceProcessManager object ...>`

- [ ] **Step 2.7: Commit**

```bash
git add engine/appc/time_slice.py tests/unit/test_time_slice.py App.py
git commit -m "feat(ai): add TimeSliceProcess + PythonMethodProcess scheduler shim"
```

---

## Task 3: AI tick driver (tree-walker)

**Files:**
- Create: `engine/appc/ai_driver.py`
- Test: `tests/unit/test_ai_driver.py` (new)

- [ ] **Step 3.1: Write the failing tests**

Create `tests/unit/test_ai_driver.py`:

```python
from engine.appc.ai import (
    ArtificialIntelligence, PlainAI, PriorityListAI, SequenceAI,
    ConditionalAI, PreprocessingAI, TGCondition,
)
from engine.appc.ai_driver import tick_ai
from engine.appc.ships import ShipClass


class _FakeLeaf:
    """Minimal stand-in for an AI.PlainAI.<X>.X instance.
    Records Update calls and returns a programmable US_* status."""
    def __init__(self, next_update=1.0, status=ArtificialIntelligence.US_ACTIVE):
        self.calls = 0
        self._next_update = next_update
        self._status = status

    def GetNextUpdateTime(self):
        return self._next_update

    def Update(self):
        self.calls += 1
        return self._status


def _make_plain(ship, leaf):
    pai = PlainAI(ship, "fake")
    pai._script_instance = leaf  # bypass SetScriptModule for unit tests
    return pai


def test_plain_ai_first_update_fires_at_game_time_zero():
    ship = ShipClass()
    leaf = _FakeLeaf(next_update=5.0)
    pai = _make_plain(ship, leaf)
    tick_ai(pai, game_time=0.01)
    assert leaf.calls == 1


def test_plain_ai_respects_get_next_update_time():
    ship = ShipClass()
    leaf = _FakeLeaf(next_update=5.0)
    pai = _make_plain(ship, leaf)
    tick_ai(pai, game_time=0.01)   # fires (next_update_time was 0)
    tick_ai(pai, game_time=3.0)    # before next fire (5.01) -> no call
    tick_ai(pai, game_time=4.99)   # still before -> no call
    tick_ai(pai, game_time=5.02)   # >= 5.01 -> fires
    assert leaf.calls == 2


def test_plain_ai_status_propagates():
    leaf = _FakeLeaf(status=ArtificialIntelligence.US_DONE)
    pai = _make_plain(ShipClass(), leaf)
    tick_ai(pai, game_time=0.01)
    assert pai._status == ArtificialIntelligence.US_DONE


def test_priority_list_runs_highest_priority_active():
    """Lower priority-int is higher priority (matches SDK semantics)."""
    high = _make_plain(ShipClass(), _FakeLeaf())
    low = _make_plain(ShipClass(), _FakeLeaf())
    p = PriorityListAI(ShipClass(), "P")
    p.AddAI(low, priority=10)
    p.AddAI(high, priority=1)
    tick_ai(p, game_time=0.01)
    assert high.GetScriptInstance().calls == 1
    assert low.GetScriptInstance().calls == 0


def test_priority_list_skips_dormant_child():
    high = _make_plain(ShipClass(), _FakeLeaf())
    low = _make_plain(ShipClass(), _FakeLeaf())
    high._status = ArtificialIntelligence.US_DORMANT
    p = PriorityListAI(ShipClass(), "P")
    p.AddAI(high, priority=1)
    p.AddAI(low, priority=10)
    tick_ai(p, game_time=0.01)
    assert high.GetScriptInstance().calls == 0
    assert low.GetScriptInstance().calls == 1


def test_sequence_advances_on_done():
    a = _make_plain(ShipClass(), _FakeLeaf(status=ArtificialIntelligence.US_DONE))
    b = _make_plain(ShipClass(), _FakeLeaf())
    s = SequenceAI(ShipClass(), "S")
    s.AddAI(a); s.AddAI(b)
    tick_ai(s, game_time=0.01)
    assert a.GetScriptInstance().calls == 1
    assert b.GetScriptInstance().calls == 0
    tick_ai(s, game_time=0.02)
    assert b.GetScriptInstance().calls == 1


def test_sequence_completes_when_all_done():
    a = _make_plain(ShipClass(), _FakeLeaf(status=ArtificialIntelligence.US_DONE))
    b = _make_plain(ShipClass(), _FakeLeaf(status=ArtificialIntelligence.US_DONE))
    s = SequenceAI(ShipClass(), "S")
    s.AddAI(a); s.AddAI(b)
    tick_ai(s, game_time=0.01)  # a -> DONE; advance
    tick_ai(s, game_time=0.02)  # b -> DONE; sequence done
    assert s._status == ArtificialIntelligence.US_DONE


def test_conditional_runs_when_condition_active():
    leaf = _FakeLeaf()
    child = _make_plain(ShipClass(), leaf)
    cond = TGCondition(); cond.SetActive(); cond.SetStatus(1)
    cai = ConditionalAI(ShipClass(), "C")
    cai.SetContainedAI(child)
    cai.AddCondition(cond)
    tick_ai(cai, game_time=0.01)
    assert leaf.calls == 1


def test_conditional_does_not_run_when_condition_inactive():
    leaf = _FakeLeaf()
    child = _make_plain(ShipClass(), leaf)
    cond = TGCondition(); cond.SetActive(); cond.SetStatus(0)
    cai = ConditionalAI(ShipClass(), "C")
    cai.SetContainedAI(child)
    cai.AddCondition(cond)
    tick_ai(cai, game_time=0.01)
    assert leaf.calls == 0
    assert cai._status == ArtificialIntelligence.US_DORMANT


class _FakePreprocessor:
    """Preprocessor stand-in. Set status to one of PS_*; tick_ai will call
    Preprocess() each tick and dispatch the contained AI accordingly."""
    def __init__(self, status):
        self.status = status
        self.calls = 0
    def Preprocess(self):
        self.calls += 1
        return self.status


def _make_pp(status, contained):
    pp = PreprocessingAI(ShipClass(), "PP")
    inst = _FakePreprocessor(status)
    pp.SetPreprocessingMethod(inst, "Preprocess")
    pp.SetContainedAI(contained)
    return pp, inst


def test_preprocessing_normal_runs_child():
    leaf = _FakeLeaf()
    child = _make_plain(ShipClass(), leaf)
    pp, inst = _make_pp(PreprocessingAI.PS_NORMAL, child)
    tick_ai(pp, game_time=0.01)
    assert inst.calls == 1
    assert leaf.calls == 1


def test_preprocessing_skip_active_does_not_run_child():
    leaf = _FakeLeaf()
    child = _make_plain(ShipClass(), leaf)
    pp, inst = _make_pp(PreprocessingAI.PS_SKIP_ACTIVE, child)
    tick_ai(pp, game_time=0.01)
    assert inst.calls == 1
    assert leaf.calls == 0
    assert pp._status == ArtificialIntelligence.US_ACTIVE


def test_preprocessing_skip_dormant_marks_dormant():
    leaf = _FakeLeaf()
    child = _make_plain(ShipClass(), leaf)
    pp, inst = _make_pp(PreprocessingAI.PS_SKIP_DORMANT, child)
    tick_ai(pp, game_time=0.01)
    assert leaf.calls == 0
    assert pp._status == ArtificialIntelligence.US_DORMANT


def test_preprocessing_done_completes_pp():
    leaf = _FakeLeaf()
    child = _make_plain(ShipClass(), leaf)
    pp, inst = _make_pp(PreprocessingAI.PS_DONE, child)
    tick_ai(pp, game_time=0.01)
    assert leaf.calls == 0
    assert pp._status == ArtificialIntelligence.US_DONE
```

- [ ] **Step 3.2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_ai_driver.py -v`
Expected: ImportError — module doesn't exist.

- [ ] **Step 3.3: Implement `engine/appc/ai_driver.py`**

```python
"""AI tick driver — walks an AI tree top-down each frame.

Mirrors the SDK ArtificialIntelligence dispatch semantics
(sdk/Build/scripts/App.py:4922-5232):

* PlainAI         — call script_instance.Update() at GetNextUpdateTime() cadence
* PriorityListAI  — run highest-priority non-DORMANT child (lower int == higher priority)
* SequenceAI      — run current child; on US_DONE advance, loop per _loop_count
* ConditionalAI   — if any condition is non-zero, run contained AI; else US_DORMANT
* PreprocessingAI — invoke preprocess method, dispatch contained per PS_*

The driver is *not* TimeSliceProcess-based. PlainAI carries its own
_next_update_time field; the driver consults it each tick. This keeps
Step 3 testable independently of the TimeSliceProcess scheduler (Step 2).
"""
from engine.appc.ai import (
    ArtificialIntelligence, PlainAI, PriorityListAI, SequenceAI,
    ConditionalAI, PreprocessingAI,
)

US_ACTIVE = ArtificialIntelligence.US_ACTIVE
US_DONE = ArtificialIntelligence.US_DONE
US_DORMANT = ArtificialIntelligence.US_DORMANT
PS_NORMAL = PreprocessingAI.PS_NORMAL
PS_SKIP_ACTIVE = PreprocessingAI.PS_SKIP_ACTIVE
PS_SKIP_DORMANT = PreprocessingAI.PS_SKIP_DORMANT
PS_DONE = PreprocessingAI.PS_DONE


def tick_ai(ai, game_time: float) -> int:
    """Tick one AI subtree at the given game time. Returns the resulting status."""
    if ai is None:
        return US_DONE
    if isinstance(ai, PreprocessingAI):
        return _tick_preprocessing(ai, game_time)
    if isinstance(ai, ConditionalAI):
        return _tick_conditional(ai, game_time)
    if isinstance(ai, PriorityListAI):
        return _tick_priority_list(ai, game_time)
    if isinstance(ai, SequenceAI):
        return _tick_sequence(ai, game_time)
    if isinstance(ai, PlainAI):
        return _tick_plain(ai, game_time)
    return ai._status


def _tick_plain(ai: PlainAI, game_time: float) -> int:
    if ai._status != US_ACTIVE:
        return ai._status
    if game_time < ai._next_update_time:
        return ai._status
    inst = ai.GetScriptInstance()
    status = inst.Update()
    if status is None:
        status = US_ACTIVE
    ai._status = int(status)
    # Reschedule based on the script's reported interval.
    interval = float(inst.GetNextUpdateTime())
    ai._next_update_time = game_time + interval
    return ai._status


def _tick_priority_list(ai: PriorityListAI, game_time: float) -> int:
    # ai._ais is sorted lowest priority-int first (highest priority).
    for _prio, child in ai._ais:
        if child._status == US_DORMANT:
            continue
        tick_ai(child, game_time)
        return ai._status  # one child per tick (SDK semantics)
    # All children dormant or list empty.
    if ai._ais and all(c._status == US_DONE for _p, c in ai._ais):
        ai._status = US_DONE
    return ai._status


def _tick_sequence(ai: SequenceAI, game_time: float) -> int:
    """Tick the current child; on DONE, advance index inline.

    If the index walks off the end, set the sequence DONE on the same tick
    (loop_count handling is deliberately out of scope for this slice —
    SetLoopCount works as a data getter/setter, but no looping in the
    driver yet; revisit when Compound.BasicAttack arrives).
    """
    if not ai._ais:
        ai._status = US_DONE
        return ai._status
    idx = getattr(ai, "_current_index", 0)
    if idx >= len(ai._ais):
        ai._status = US_DONE
        return ai._status
    child = ai._ais[idx]
    tick_ai(child, game_time)
    if child._status == US_DONE:
        idx += 1
        ai._current_index = idx
        if idx >= len(ai._ais):
            ai._status = US_DONE
    return ai._status


def _tick_conditional(ai: ConditionalAI, game_time: float) -> int:
    active = any(c.GetStatus() != 0 for c in ai._conditions) if ai._conditions else False
    if not active:
        ai._status = US_DORMANT
        return ai._status
    ai._status = US_ACTIVE
    if ai._contained_ai is not None:
        tick_ai(ai._contained_ai, game_time)
    return ai._status


def _tick_preprocessing(ai: PreprocessingAI, game_time: float) -> int:
    inst = ai._preprocessing_instance
    method = ai._preprocessing_method
    if inst is None or not method:
        # No preprocessor configured — fall through to contained AI.
        if ai._contained_ai is not None:
            tick_ai(ai._contained_ai, game_time)
        return ai._status
    result = getattr(inst, method)()
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


def tick_all_ai(game_time: float) -> None:
    """Iterate every ship and tick its attached AI subtree.

    Called once per frame from GameLoop.tick(). Q2 closed at AI-first
    within the tick so this fires before physics + render.
    """
    from engine.appc.ship_iter import iter_ships
    for ship in iter_ships():
        ai = ship.GetAI() if hasattr(ship, "GetAI") else None
        if ai is not None:
            tick_ai(ai, game_time)
```

- [ ] **Step 3.4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_ai_driver.py -v`
Expected: 13 PASS.

- [ ] **Step 3.5: Verify `_status` field exists on every AI class needed by the driver**

The driver reads `ai._status` on `PriorityListAI`, `SequenceAI`, `ConditionalAI`, `PreprocessingAI` children. `ArtificialIntelligence.__init__` already sets `self._status = self.US_ACTIVE` (line 192). Confirm by:

Run: `uv run python -c "from engine.appc.ai import PriorityListAI, SequenceAI, ConditionalAI, PreprocessingAI; from engine.appc.ships import ShipClass; [print(type(a).__name__, a._status) for a in (PriorityListAI(ShipClass()), SequenceAI(ShipClass()), ConditionalAI(ShipClass()), PreprocessingAI(ShipClass()))]"`
Expected: all four print `_status = 0` (US_ACTIVE).

- [ ] **Step 3.6: Commit**

```bash
git add engine/appc/ai_driver.py tests/unit/test_ai_driver.py
git commit -m "feat(ai): add tree-walking AI tick driver for PlainAI + composites"
```

---

## Task 4: Minimal ship motion stubs for Stay

**Files:**
- Modify: [`engine/appc/ships.py`](../../../engine/appc/ships.py) — add `SetSpeed`, `SetTargetAngularVelocityDirect`
- Test: extend `tests/unit/test_ai_primitives.py` *or* a new `tests/unit/test_ship_motion_stubs.py`

These are *recording stubs only* — no PD solver, no Bullet integration. They exist so `Stay.Update()` can call them without AttributeError, and so the integration test can assert the setpoint was zero.

- [ ] **Step 4.1: Write the failing test**

Create `tests/unit/test_ship_motion_stubs.py`:

```python
import App
from engine.appc.ships import ShipClass
from engine.appc.math import TGPoint3, TGPoint3_GetModelForward


def test_set_speed_records_setpoint():
    ship = ShipClass()
    fwd = TGPoint3_GetModelForward()
    ship.SetSpeed(0.0, fwd, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    sp = ship.GetSpeedSetpoint()
    assert sp[0] == 0.0
    assert sp[2] == App.PhysicsObjectClass.DIRECTION_MODEL_SPACE


def test_set_target_angular_velocity_direct_records_setpoint():
    ship = ShipClass()
    v = TGPoint3(); v.SetXYZ(0.0, 0.0, 0.0)
    ship.SetTargetAngularVelocityDirect(v)
    av = ship.GetTargetAngularVelocitySetpoint()
    assert (av.x, av.y, av.z) == (0.0, 0.0, 0.0)


def test_set_speed_nonzero_round_trip():
    ship = ShipClass()
    fwd = TGPoint3_GetModelForward()
    ship.SetSpeed(120.5, fwd, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    sp = ship.GetSpeedSetpoint()
    assert sp[0] == 120.5
```

- [ ] **Step 4.2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_ship_motion_stubs.py -v`
Expected: 3 FAILs — `SetSpeed`, `SetTargetAngularVelocityDirect`, `GetSpeedSetpoint` don't exist on `ShipClass`.

- [ ] **Step 4.3: Implement the stubs**

In [`engine/appc/ships.py`](../../../engine/appc/ships.py), add after the existing `SetAI`/`GetAI` block (around line 67):

```python
    # ── Motion setpoints (AI-driven, no physics yet) ─────────────────────────
    # Stay, GoForward, Intercept, et al. call SetSpeed/SetTargetAngularVelocityDirect
    # each AI tick. The Phase-1 slice records the most-recent setpoint so tests
    # can assert "Stay drove speed to 0 and angular velocity to zero." The full
    # PD-solver + Bullet integration lives in the deferred Step 4 of the AI
    # runtime plan.

    def SetSpeed(self, speed, direction, frame) -> None:
        self._speed_setpoint = (float(speed), direction, int(frame))

    def GetSpeedSetpoint(self):
        return getattr(self, "_speed_setpoint", None)

    def SetTargetAngularVelocityDirect(self, vec) -> None:
        # Defensive copy — vec is a TGPoint3 the caller may mutate.
        from engine.appc.math import TGPoint3
        self._target_angular_velocity_setpoint = TGPoint3(vec.x, vec.y, vec.z)

    def GetTargetAngularVelocitySetpoint(self):
        return getattr(self, "_target_angular_velocity_setpoint", None)
```

- [ ] **Step 4.4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_ship_motion_stubs.py -v`
Expected: 3 PASS.

- [ ] **Step 4.5: Commit**

```bash
git add engine/appc/ships.py tests/unit/test_ship_motion_stubs.py
git commit -m "feat(ships): record-only SetSpeed + SetTargetAngularVelocityDirect setpoints"
```

---

## Task 5: Wire AI driver + scheduler into GameLoop

**Files:**
- Modify: [`engine/core/loop.py`](../../../engine/core/loop.py)
- Test: extend [`tests/unit/test_loop.py`](../../../tests/unit/test_loop.py)

- [ ] **Step 5.1: Write the failing test**

Add to [`tests/unit/test_loop.py`](../../../tests/unit/test_loop.py):

```python
def test_gameloop_ticks_time_slice_manager():
    """GameLoop.tick() should advance g_kAIManager so registered processes fire."""
    from engine.appc.time_slice import PythonMethodProcess, g_kAIManager
    fired = []
    class H:
        def Go(self): fired.append(1)
    proc = PythonMethodProcess()
    proc.SetFunction(H(), "Go")
    proc.SetDelay(0.05)
    proc.SetDelayUsesGameTime(1)
    g_kAIManager.Add(proc)
    try:
        loop = GameLoop()
        loop.advance(6)  # 6/60 = 0.1s — covers the 0.05 delay
        assert len(fired) >= 1
    finally:
        g_kAIManager.Remove(proc)


def test_gameloop_ticks_ai_driver_for_ships_with_ai():
    """GameLoop.tick() should call tick_ai on each ship's AI."""
    import App
    from engine.appc.ai import PlainAI
    from engine.appc.ships import ShipClass

    class _Leaf:
        def __init__(self):
            self.calls = 0
        def GetNextUpdateTime(self): return 1.0
        def Update(self):
            self.calls += 1
            return 0  # US_ACTIVE

    ship = ShipClass()
    pai = PlainAI(ship, "T")
    pai._script_instance = _Leaf()
    ship.SetAI(pai)

    pSet = App.SetClass_Create()
    pSet.SetName("aitest")
    pSet.AddObjectToSet(ship, "testship")
    App.g_kSetManager._sets["aitest"] = pSet
    try:
        loop = GameLoop()
        loop.tick()
        assert pai.GetScriptInstance().calls == 1
    finally:
        App.g_kSetManager._sets.pop("aitest", None)
```

- [ ] **Step 5.2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_loop.py -v -k "ai_driver or time_slice"`
Expected: FAIL — GameLoop doesn't tick the AI manager or driver yet.

- [ ] **Step 5.3: Implement the wiring**

In [`engine/core/loop.py`](../../../engine/core/loop.py), replace the `tick()` method:

```python
import App

from engine.appc.ship_iter import iter_ships

TICK_RATE = 60
TICK_DELTA = 1.0 / TICK_RATE


class GameLoop:
    """Drives App.g_kTimerManager, App.g_kRealtimeTimerManager,
    g_kAIManager (TimeSliceProcess scheduler), the AI tree-walker driver,
    and live-ship subsystem updates at 60 Hz.

    Order per tick (matches Q2 closed at AI-first within the tick):
      1. Timer managers advance.
      2. AI tick:
         a. g_kAIManager dispatches due TimeSliceProcess callbacks.
         b. tick_all_ai walks every ship's AI subtree.
      3. Per-ship subsystem updates (shields etc.).
    Physics + render run downstream in host_loop, not here.
    """

    def tick(self) -> None:
        App.g_kTimerManager.tick(TICK_DELTA)
        App.g_kRealtimeTimerManager.tick(TICK_DELTA)

        from engine.appc.time_slice import g_kAIManager
        from engine.appc.ai_driver import tick_all_ai
        game_time = App.g_kTimerManager.get_time()
        real_time = App.g_kRealtimeTimerManager.get_time()
        g_kAIManager.tick(game_time=game_time, real_time=real_time)
        tick_all_ai(game_time=game_time)

        for ship in iter_ships():
            ss = ship.GetShieldSubsystem()
            if ss is not None:
                ss.Update(TICK_DELTA)

    def advance(self, n: int) -> None:
        for _ in range(n):
            self.tick()

    @property
    def game_time(self) -> float:
        return App.g_kTimerManager.get_time()
```

- [ ] **Step 5.4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_loop.py -v`
Expected: all green (both new tests + pre-existing time/advance tests).

- [ ] **Step 5.5: Commit**

```bash
git add engine/core/loop.py tests/unit/test_loop.py
git commit -m "feat(loop): drive g_kAIManager + tick_all_ai from GameLoop.tick"
```

---

## Task 6: End-to-end `Stay` smoke test

**Files:**
- Test: `tests/integration/test_ai_stay_smoke.py` (new)

- [ ] **Step 6.1: Write the integration test**

Create `tests/integration/test_ai_stay_smoke.py`:

```python
"""End-to-end smoke: Stay AI ticks at 5 s cadence and writes zero motion setpoints.

Proves Tasks 1+3+4+5 work together: real script loading (Task 1),
tree-walk driver (Task 3), ShipClass motion stubs (Task 4), GameLoop
wiring (Task 5). Task 2 (TimeSliceProcess) is exercised by its own unit
tests — Stay doesn't use it.
"""
import App
from engine.core.loop import GameLoop, TICK_RATE
from engine.appc.ai import PlainAI_Create
from engine.appc.ships import ShipClass


def _setup_ship_with_stay():
    """Build a fresh set, place a ship with PlainAI('Stay') attached,
    and return (ship, plain_ai)."""
    App.g_kTimerManager._time = 0.0
    App.g_kTimerManager._timers.clear()
    App.g_kRealtimeTimerManager._time = 0.0
    App.g_kRealtimeTimerManager._timers.clear()
    App.g_kSetManager._sets.clear()

    pSet = App.SetClass_Create()
    pSet.SetName("stay_smoke")
    App.g_kSetManager._sets["stay_smoke"] = pSet
    ship = ShipClass()
    pSet.AddObjectToSet(ship, "testship")

    pai = PlainAI_Create(ship, "TestStay")
    pai.SetScriptModule("Stay")
    ship.SetAI(pai)
    return ship, pai


def test_stay_update_fires_at_five_second_cadence():
    """Run 11 in-game seconds; Stay.Update should fire at t≈0, 5, 10 → 3 calls."""
    ship, pai = _setup_ship_with_stay()
    stay = pai.GetScriptInstance()

    # Decorate Update so we can count calls without touching engine internals.
    original_update = stay.Update
    stay.call_count = 0
    def counting_update():
        stay.call_count += 1
        return original_update()
    stay.Update = counting_update

    loop = GameLoop()
    loop.advance(TICK_RATE * 11)  # 11 seconds at 60 Hz

    assert stay.call_count == 3, f"expected 3 fires (t=0,5,10), got {stay.call_count}"


def test_stay_zeros_ship_motion_setpoints():
    """After Stay runs, the ship's speed setpoint and target angular velocity
    are both zero — Stay's contract is 'don't move, don't turn.'"""
    ship, pai = _setup_ship_with_stay()
    loop = GameLoop()
    loop.advance(TICK_RATE * 6)  # one full Update cycle

    sp = ship.GetSpeedSetpoint()
    assert sp is not None, "Stay never called SetSpeed"
    assert sp[0] == 0.0, f"Stay should drive speed to 0, got {sp[0]}"

    av = ship.GetTargetAngularVelocitySetpoint()
    assert av is not None, "Stay never called SetTargetAngularVelocityDirect"
    assert (av.x, av.y, av.z) == (0.0, 0.0, 0.0)


def test_stay_ai_remains_active():
    """Stay returns US_ACTIVE forever; PlainAI.IsActive should stay 1."""
    ship, pai = _setup_ship_with_stay()
    loop = GameLoop()
    loop.advance(TICK_RATE * 11)
    assert pai.IsActive() == 1
```

- [ ] **Step 6.2: Run the smoke test**

Run: `uv run pytest tests/integration/test_ai_stay_smoke.py -v`
Expected: 3 PASS.

- [ ] **Step 6.3: Run the full unit + integration AI test set**

Run: `uv run pytest tests/unit/test_plain_ai_script_loading.py tests/unit/test_time_slice.py tests/unit/test_ai_driver.py tests/unit/test_ship_motion_stubs.py tests/unit/test_loop.py tests/integration/test_ai_stay_smoke.py -v`
Expected: all green.

- [ ] **Step 6.4: Run the broader suite to confirm no regressions**

Run: `uv run pytest tests/unit tests/integration -x -q`
Expected: green (or pre-existing failures unrelated to this slice — read the failures, don't paper over them).

- [ ] **Step 6.5: Commit**

```bash
git add tests/integration/test_ai_stay_smoke.py
git commit -m "test(ai): end-to-end smoke test for PlainAI('Stay') at 5s cadence"
```

---

## Out of scope (deferred to next slice)

- `TurnTowardLocation`, `InSystemWarp`, `GetPredictedPosition`, `GetRelativePositionInfo` — the full Step 4 motion API of the original deferred plan.
- `GoForward`, `TurnToOrientation`, `Intercept`, `FollowObject`, `CircleObject` smoke trail (deferred plan §Step 5.2-5.6).
- Real `ConditionScript` evaluation (deferred plan §Step 6) — `ConditionalAI` tests in this slice manipulate `TGCondition.SetStatus` directly.
- `OptimizedFireScript` / `OptimizedSelectTarget` preprocessor wiring — `_FakePreprocessor` covers the dispatch contract for now.
- Save/load round-trip for AI graphs (deferred plan §Decisions item 4).
- Renderer-side smoke test (visible hostile intercepting player) — depends on motion API + chase camera.

These remain in [docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md](../deferred/2026-05-18-ship-ai-runtime.md) and pick up from where this plan leaves off.
