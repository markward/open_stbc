"""Bridge Phase 1 mission init/tick to the renderer host.

The constants below are placeholders pinned in Task 25 from the
pick_simplest_mission.py / pick_default_skybox.py scan results.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Iterable, Optional

from engine import renderer as r

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# v1 ship-gate selections — Task 25 pins these from the pick_*.py scan results.
SHIP_GATE_MISSION = "Custom.Tutorial.Episode.M1Basic.M1Basic"
DEFAULT_SKYBOX_NIF: Optional[str] = None  # No skybox NIF in BC assets; spec defers
DEFAULT_TEXTURE_SEARCH = "data/Models/SharedTextures/FedShips/High"
DEFAULT_PLAYER_SET = "Biranu1"  # M1 Basic-specific


def _setup_sdk() -> None:
    """Install SDK finder + AST transforms so SDK script imports work."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from tools import mission_harness
    mission_harness.setup_sdk()


def _init_mission(mission_module_name: str):
    """Initialize a mission via the same path gameloop_harness uses.

    Returns (mission, episode, game, mod) for the caller to use.
    """
    from engine.core.game import Game, Episode, Mission, _set_current_game
    from engine.appc.events import TGEvent
    from engine.appc.placement import _waypoint_registry
    import App

    # Reset state per session (mirror tools/gameloop_harness.py).
    App.g_kTimerManager._time = 0.0
    App.g_kTimerManager._timers.clear()
    App.g_kRealtimeTimerManager._time = 0.0
    App.g_kRealtimeTimerManager._timers.clear()
    App.g_kEventManager._broadcast_handlers.clear()
    App.g_kSetManager._sets.clear()
    _waypoint_registry.clear()
    App._next_event_type_id = 200

    mission = Mission()
    episode = Episode()
    episode.SetCurrentMission(mission)
    game = Game()
    game.SetCurrentEpisode(episode)
    _set_current_game(game)

    mod = importlib.import_module(mission_module_name)
    if hasattr(mod, "PreLoadAssets"):
        mod.PreLoadAssets(mission)
    mod.Initialize(mission)

    start_evt = TGEvent()
    start_evt.SetEventType(App.ET_MISSION_START)
    start_evt.SetDestination(episode)
    App.g_kEventManager.AddEvent(start_evt)

    return mission, episode, game, mod


def _iter_set_objects(pSet) -> Iterable:
    """Walk every object in a set exactly once.

    SetClass.GetNextObject wraps to the first object when iteration completes
    (mirroring the BC engine's iteration semantics). Detect wrap by comparing
    against the first object's id and stop there.
    """
    first = pSet.GetFirstObject()
    if first is None:
        return
    yield first
    if not hasattr(first, "GetObjID"):
        return
    first_id = first.GetObjID()
    obj = pSet.GetNextObject(first_id)
    while obj is not None and hasattr(obj, "GetObjID") and obj.GetObjID() != first_id:
        yield obj
        obj = pSet.GetNextObject(obj.GetObjID())


def _iter_ships() -> Iterable:
    """Walk every ShipClass-like object in every active set."""
    import App
    for _name, pSet in App.g_kSetManager._sets.items():
        for obj in _iter_set_objects(pSet):
            # ShipClass exposes GetScript; non-ship objects (waypoints,
            # characters) typically don't have a non-empty script string.
            if hasattr(obj, "GetScript"):
                yield obj


def _ship_nif_path(ship) -> Optional[str]:
    """Return absolute path to the ship's high-LOD NIF, or None if not found."""
    try:
        script_name = ship.GetScript()
    except Exception:
        return None
    if not script_name:
        return None
    try:
        mod = importlib.import_module(script_name)
        stats = mod.GetShipStats()
    except Exception:
        return None
    rel = stats.get("FilenameHigh") if isinstance(stats, dict) else None
    if not rel:
        return None
    abs_path = PROJECT_ROOT / "game" / rel
    return str(abs_path) if abs_path.is_file() else None


def _world_matrix_row_major(ship) -> list:
    """Convert ship's world-space pose to a 16-float row-major mat4."""
    loc = ship.GetWorldLocation()
    rot = ship.GetWorldRotation()
    return [
        rot._m[0][0], rot._m[0][1], rot._m[0][2], loc.x,
        rot._m[1][0], rot._m[1][1], rot._m[1][2], loc.y,
        rot._m[2][0], rot._m[2][1], rot._m[2][2], loc.z,
        0.0,          0.0,          0.0,          1.0,
    ]


def run(mission_name: str = SHIP_GATE_MISSION,
        max_ticks: Optional[int] = None) -> int:
    """Boot the renderer, init the named mission, run until the window closes
    or max_ticks is reached. Returns 0 on clean exit."""
    _setup_sdk()
    _init_mission(mission_name)

    import App
    from engine.core.loop import GameLoop

    r.init(1280, 720, "open_stbc")
    try:
        if DEFAULT_SKYBOX_NIF:
            sky = r.load_model(DEFAULT_SKYBOX_NIF, DEFAULT_TEXTURE_SEARCH)
            r.set_skybox(sky)

        # Per-NIF cache so the same mesh isn't reloaded once per ship.
        nif_to_handle: dict[str, int] = {}
        instances: dict[object, object] = {}  # ship -> InstanceId
        for ship in _iter_ships():
            nif_path = _ship_nif_path(ship)
            if nif_path is None:
                continue
            handle = nif_to_handle.get(nif_path)
            if handle is None:
                tex_search = str(PROJECT_ROOT / "game" / DEFAULT_TEXTURE_SEARCH)
                try:
                    handle = r.load_model(nif_path, tex_search)
                except Exception:
                    continue
                nif_to_handle[nif_path] = handle
            iid = r.create_instance(handle)
            r.set_world_transform(iid, _world_matrix_row_major(ship))
            instances[ship] = iid

        # Player ship for camera follow.
        player_set = App.g_kSetManager.GetSet(DEFAULT_PLAYER_SET)
        player = player_set.GetObject("player") if player_set is not None else None
        if player is None and instances:
            # Fallback: follow the first ship we found.
            player = next(iter(instances.keys()))

        loop = GameLoop()
        ticks = 0
        while not r.should_close():
            loop.tick()

            # Sync transforms for known instances.
            for ship, iid in instances.items():
                r.set_world_transform(iid, _world_matrix_row_major(ship))

            # Camera: third-person offset behind the player ship (or origin).
            if player is not None:
                p = player.GetWorldLocation()
                eye = (p.x, p.y + 30.0, p.z + 200.0)
                target = (p.x, p.y, p.z)
            else:
                eye = (0.0, 30.0, 200.0)
                target = (0.0, 0.0, 0.0)
            r.set_camera(eye=eye, target=target, up=(0.0, 1.0, 0.0),
                         fov_y_rad=1.0472, near=1.0, far=100000.0)

            r.frame()
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break

        for iid in instances.values():
            r.destroy_instance(iid)
    finally:
        r.shutdown()

    return 0
