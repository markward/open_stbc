"""SetupProperties copies all ShipProperty identity fields onto the ship."""
from engine.appc.ships import ShipClass_Create
from engine.appc.properties import ShipProperty


def test_ship_property_propagation():
    ship = ShipClass_Create("Galaxy")
    sp = ShipProperty("Galaxy")
    sp.SetGenus(1)
    sp.SetSpecies(101)
    sp.SetMass(120.0)
    sp.SetRotationalInertia(15000.0)
    sp.SetShipName("Dauntless")
    sp.SetDamageResolution(10.0)
    sp.SetAffiliation(0)
    sp.SetStationary(0)
    sp.SetAIString("FedAttack")
    sp.SetDeathExplosionSound("g_lsDeathExplosions")
    sp.SetModelFilename("")

    ship.GetPropertySet().AddToSet("Scene Root", sp)
    ship.SetupProperties()

    assert ship.GetGenus() == 1
    assert ship.GetSpecies() == 101
    assert ship.GetMass() == 120.0
    assert ship.GetRotationalInertia() == 15000.0
    assert ship.GetShipName() == "Dauntless"
    assert ship.GetDamageResolution() == 10.0
    assert ship.GetAffiliation() == 0
    assert ship.IsStationary() == 0
    assert ship.GetAIString() == "FedAttack"
    assert ship.GetDeathExplosionSound() == "g_lsDeathExplosions"
    assert ship.GetModelFilename() == ""


def test_none_fields_are_skipped():
    """Unset ShipProperty fields don't clobber defaults."""
    ship = ShipClass_Create("X")
    ship.SetAIString("PrevAI")        # pre-set
    sp = ShipProperty("X")
    sp.SetMass(50.0)                   # only mass is set
    ship.GetPropertySet().AddToSet("Scene Root", sp)
    ship.SetupProperties()

    assert ship.GetMass() == 50.0
    assert ship.GetAIString() == "PrevAI"   # not clobbered by None
