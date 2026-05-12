"""ShipClass ship-level identity fields populated by SetupProperties."""
from engine.appc.ships import ShipClass


def test_defaults():
    s = ShipClass()
    assert s.GetGenus() == 0
    assert s.GetSpecies() == 0
    assert s.GetAffiliation() == 0
    assert s.GetShipName() == ""
    assert s.GetAIString() == ""
    assert s.GetDamageResolution() == 0.0
    assert s.GetModelFilename() == ""
    assert s.IsStationary() == 0
    assert s.GetDeathExplosionSound() == ""


def test_setters_persist():
    s = ShipClass()
    s.SetGenus(1)
    s.SetSpecies(101)
    s.SetAffiliation(2)
    s.SetShipName("Dauntless")
    s.SetAIString("FedAttack")
    s.SetDamageResolution(10.0)
    s.SetModelFilename("data/Models/Ships/Galaxy/Galaxy.nif")
    s.SetStationary(1)
    s.SetDeathExplosionSound("g_lsDeathExplosions")
    assert s.GetGenus() == 1
    assert s.GetSpecies() == 101
    assert s.GetAffiliation() == 2
    assert s.GetShipName() == "Dauntless"
    assert s.GetAIString() == "FedAttack"
    assert s.GetDamageResolution() == 10.0
    assert s.GetModelFilename() == "data/Models/Ships/Galaxy/Galaxy.nif"
    assert s.IsStationary() == 1
    assert s.GetDeathExplosionSound() == "g_lsDeathExplosions"
