import pytest
from engine.core.game import Game, Episode, Mission, Game_GetCurrentGame, _set_current_game
from engine.appc.events import TGEventHandlerObject


def test_game_episode_mission_chain():
    mission = Mission()
    episode = Episode()
    episode.SetCurrentMission(mission)
    game = Game()
    game.SetCurrentEpisode(episode)
    _set_current_game(game)

    assert Game_GetCurrentGame() is game
    assert Game_GetCurrentGame().GetCurrentEpisode() is episode
    assert Game_GetCurrentGame().GetCurrentEpisode().GetCurrentMission() is mission


def test_no_game_returns_none():
    _set_current_game(None)
    assert Game_GetCurrentGame() is None


def test_mission_is_event_handler():
    mission = Mission()
    assert isinstance(mission, TGEventHandlerObject)


def test_game_get_player_initially_none():
    from engine.core.game import Game
    g = Game()
    assert g.GetPlayer() is None


def test_game_set_and_get_player():
    from engine.core.game import Game
    g = Game()
    sentinel = object()
    g.SetPlayer(sentinel)
    assert g.GetPlayer() is sentinel
