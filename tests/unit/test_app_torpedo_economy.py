"""g_kUtopiaModule torpedo-economy round-trip.

Covers the four UtopiaModule methods MissionLib.SetMaxTorpsForPlayer /
SetTotalTorpsAtStarbase write and Actions.ShipScriptActions.DockWithStarbase
reads. SDK sentinel -1 means "unset / unlimited".
"""
import App


def _reset_utopia():
    App.g_kUtopiaModule._max_torpedo_load.clear()
    App.g_kUtopiaModule._starbase_torpedo_load.clear()


def test_max_torpedo_load_round_trip():
    _reset_utopia()
    App.g_kUtopiaModule.SetMaxTorpedoLoad(0, 300)
    App.g_kUtopiaModule.SetMaxTorpedoLoad(1, 60)
    assert App.g_kUtopiaModule.GetMaxTorpedoLoad(0) == 300
    assert App.g_kUtopiaModule.GetMaxTorpedoLoad(1) == 60


def test_starbase_torpedo_load_round_trip():
    _reset_utopia()
    App.g_kUtopiaModule.SetCurrentStarbaseTorpedoLoad(0, -1)
    App.g_kUtopiaModule.SetCurrentStarbaseTorpedoLoad(2, 12)
    assert App.g_kUtopiaModule.GetCurrentStarbaseTorpedoLoad(0) == -1
    assert App.g_kUtopiaModule.GetCurrentStarbaseTorpedoLoad(2) == 12


def test_unseen_type_returns_sdk_sentinel():
    _reset_utopia()
    assert App.g_kUtopiaModule.GetMaxTorpedoLoad(7) == -1
    assert App.g_kUtopiaModule.GetCurrentStarbaseTorpedoLoad(7) == -1


def test_methods_not_stubs():
    # Regression: harness saw _NamedStub calls because these fell through
    # _UtopiaModule.__getattr__. Confirm they're real bound methods now.
    import App as _App
    assert not isinstance(_App.g_kUtopiaModule.SetMaxTorpedoLoad, _App._NamedStub)
    assert not isinstance(_App.g_kUtopiaModule.GetMaxTorpedoLoad, _App._NamedStub)
    assert not isinstance(
        _App.g_kUtopiaModule.SetCurrentStarbaseTorpedoLoad, _App._NamedStub
    )
    assert not isinstance(
        _App.g_kUtopiaModule.GetCurrentStarbaseTorpedoLoad, _App._NamedStub
    )
