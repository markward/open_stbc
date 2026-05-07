"""
Integration test: Tutorial M1Basic.Initialize() runs against our Python shim.

Custom.Tutorial.Episode.M1Basic.M1Basic is the SDK's own "minimum a mission
needs to be functional" tutorial. All rendering/UI calls return _Stub;
game-logic calls use our real implementations.

Full path exercised:
  M1Basic.Initialize
    -> LoadBridge.Load (stub)
    -> MissionLib.SetupSpaceSet("Systems.Biranu.Biranu1")
         -> importlib.import_module (fixed __import__)
         -> Biranu1.Initialize() (all App calls -> _Stub)
    -> MissionLib.CreatePlayerShip
         -> Game.GetPlayer() -> None
         -> loadspacehelper.CreateShip -> None (skips player-creation branch)
"""
import sys
import pytest
import App
from engine.core.game import Game, Episode, Mission, _set_current_game

_M1BASIC_PREFIXES = (
    "Custom.Tutorial",
    "Systems.Biranu",
    "ships",
    "Multiplayer",
)


@pytest.fixture(autouse=True)
def game_context():
    mission = Mission()
    episode = Episode()
    episode.SetCurrentMission(mission)
    game = Game()
    game.SetCurrentEpisode(episode)
    _set_current_game(game)
    yield game, episode, mission
    _set_current_game(None)
    # Evict SDK modules loaded during the test so each test starts clean.
    for key in [k for k in sys.modules if k.startswith(_M1BASIC_PREFIXES)]:
        del sys.modules[key]


def test_m1basic_preload_assets_does_not_raise(game_context):
    _, _, mission = game_context
    import Custom.Tutorial.Episode.M1Basic.M1Basic as M1Basic
    M1Basic.PreLoadAssets(mission)


def test_m1basic_initialize_does_not_raise(game_context):
    _, _, mission = game_context
    import Custom.Tutorial.Episode.M1Basic.M1Basic as M1Basic
    M1Basic.PreLoadAssets(mission)
    M1Basic.Initialize(mission)
