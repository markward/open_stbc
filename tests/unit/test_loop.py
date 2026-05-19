import pytest
import App
from engine.core.loop import GameLoop

TICK = 1.0 / 60.0


@pytest.fixture(autouse=True)
def reset_timer_managers():
    App.g_kTimerManager._time = 0.0
    App.g_kTimerManager._timers.clear()
    App.g_kRealtimeTimerManager._time = 0.0
    App.g_kRealtimeTimerManager._timers.clear()
    yield
    App.g_kTimerManager._time = 0.0
    App.g_kTimerManager._timers.clear()
    App.g_kRealtimeTimerManager._time = 0.0
    App.g_kRealtimeTimerManager._timers.clear()


def test_game_loop_initial_time():
    loop = GameLoop()
    assert loop.game_time == 0.0


def test_game_loop_tick_advances_game_time():
    loop = GameLoop()
    loop.tick()
    assert abs(loop.game_time - TICK) < 1e-9


def test_game_loop_advance_n_ticks():
    loop = GameLoop()
    loop.advance(60)
    assert abs(loop.game_time - 1.0) < 1e-6


def test_game_loop_tick_advances_realtime_manager():
    loop = GameLoop()
    loop.tick()
    assert abs(App.g_kRealtimeTimerManager.get_time() - TICK) < 1e-9


def test_game_loop_game_time_reads_timer_manager():
    loop = GameLoop()
    App.g_kTimerManager._time = 3.14
    assert loop.game_time == 3.14
    App.g_kTimerManager._time = 0.0


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
