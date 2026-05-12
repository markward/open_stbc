"""ship_iter: walk every ship in every active set."""
import App
from engine.appc.sets import SetClass
from engine.appc.ship_iter import iter_ships, iter_set_objects
from engine.appc.ships import ShipClass_Create


def test_iter_ships_empty_when_no_sets():
    """Fresh App.g_kSetManager has no sets — iter yields nothing."""
    App.g_kSetManager._sets.clear()
    assert list(iter_ships()) == []


def test_iter_ships_yields_ships_with_scripts():
    App.g_kSetManager._sets.clear()
    pSet = SetClass()
    App.g_kSetManager.AddSet(pSet, "test_set")
    ship = ShipClass_Create("Galaxy")
    ship.SetScript("test_script")
    pSet.AddObjectToSet(ship, "ship_1")
    found = list(iter_ships())
    assert ship in found


def test_iter_set_objects_yields_via_values():
    """Confirms we still walk _objects.values() rather than GetFirstObject
    — see the comment block in the helper for why."""
    App.g_kSetManager._sets.clear()
    pSet = SetClass()
    App.g_kSetManager.AddSet(pSet, "test_set")
    ship = ShipClass_Create("Galaxy")
    pSet.AddObjectToSet(ship, "ship_1")
    found = list(iter_set_objects(pSet))
    assert ship in found
