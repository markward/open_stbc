"""Integration smoke: load AI.Compound.CallDamageAI, run one tick,
assert BuilderAI activates without crashing.

This is the smallest real SDK Compound that uses BuilderAI. Doesn't
assert per-tick behaviour or sub-tree correctness — that's Slice E
once FireScript / SelectTarget / sub-graphs are in place."""
import App
import pytest
from engine.appc.ai import BuilderAI
from engine.appc.ai_driver import tick_ai
from engine.appc.ships import ShipClass
from engine.core.game import Game, Episode, Mission, _set_current_game


@pytest.fixture
def game_context():
    """Minimal Game/Episode/Mission stack with a script name set.

    CallDamageAI.CreateAI calls pMission.GetScript() and passes it as the
    ``sMissionModuleName`` dependency for half its BuilderCreate functions,
    so the mission must have a non-empty script set.
    """
    mission = Mission()
    mission.SetScript("tests.integration.test_builder_ai_call_damage_smoke")
    episode = Episode()
    episode.SetCurrentMission(mission)
    game = Game()
    game.SetCurrentEpisode(episode)
    _set_current_game(game)
    yield
    _set_current_game(None)


def _reset_app_state():
    """Clear ONLY the state these tests touch. Do NOT clear
    _broadcast_handlers — that dict holds module-import-time
    registrations (e.g. KeyboardBinding._OnKeyboardEvent_Dispatch on
    event type 4096) that downstream weapon-hit / input-pipeline tests
    rely on. CallDamageAI's 53 builder blocks register handlers via
    _method_handlers, never _broadcast_handlers."""
    App.g_kSetManager._sets.clear()
    if hasattr(App.g_kEventManager, "_method_handlers"):
        App.g_kEventManager._method_handlers.clear()


@pytest.fixture(autouse=True)
def _isolate_app_state():
    """Reset condition/builder-touched state BEFORE and AFTER each test
    so downstream tests aren't polluted by the 53-block CallDamageAI
    tree's per-leaf condition wiring."""
    _reset_app_state()
    yield
    _reset_app_state()


def test_call_damage_ai_activates_without_crashing(game_context):
    pSet = App.SetClass_Create(); pSet.SetName("S")
    ship = ShipClass(); pSet.AddObjectToSet(ship, "Test")
    App.g_kSetManager._sets["S"] = pSet

    import AI.Compound.CallDamageAI as call_damage_mod
    builder = call_damage_mod.CreateAI(ship)
    assert isinstance(builder, BuilderAI)

    tick_ai(builder, game_time=0.01)
    assert builder._activated is True, (
        f"BuilderAI activation failed: {builder._activation_error}"
    )
    assert builder._activation_failed is False
    assert builder._contained_ai is not None


def test_call_damage_ai_second_tick_does_not_rebuild(game_context):
    pSet = App.SetClass_Create(); pSet.SetName("S")
    ship = ShipClass(); pSet.AddObjectToSet(ship, "Test")
    App.g_kSetManager._sets["S"] = pSet

    import AI.Compound.CallDamageAI as call_damage_mod
    builder = call_damage_mod.CreateAI(ship)
    tick_ai(builder, game_time=0.01)
    # Snapshot contained AI; second tick must reuse it.
    snapshot = builder._contained_ai
    tick_ai(builder, game_time=0.5)
    assert builder._contained_ai is snapshot
