"""MissionSession + reset_sdk_globals — backend for in-process mission swaps."""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_reset_sdk_globals_clears_state():
    """After reset, the five SDK globals listed in the spec are empty."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from tools import mission_harness
    mission_harness.setup_sdk()

    import App
    from engine.appc.placement import _waypoint_registry
    from engine.host_loop import reset_sdk_globals

    App.g_kTimerManager._timers["x"] = object()
    App.g_kRealtimeTimerManager._timers["y"] = object()
    App.g_kEventManager._broadcast_handlers["t"] = [object()]
    App.g_kSetManager._sets["s"] = object()
    _waypoint_registry["w"] = object()
    App._next_event_type_id = 999

    reset_sdk_globals()

    assert App.g_kTimerManager._time == 0.0
    assert App.g_kTimerManager._timers == {}
    assert App.g_kRealtimeTimerManager._time == 0.0
    assert App.g_kRealtimeTimerManager._timers == {}
    assert App.g_kEventManager._broadcast_handlers == {}
    assert App.g_kSetManager._sets == {}
    assert _waypoint_registry == {}
    assert App._next_event_type_id == 200
