"""SetupProperties dispatches WeaponSystemProperty by WST_* to the right slot."""
from engine.appc.ships import ShipClass_Create
from engine.appc.properties import WeaponSystemProperty


def _make_ws(name, wst_type, max_c=4000.0, power=300.0, single_fire=1, aimed=0):
    p = WeaponSystemProperty(name)
    p.SetMaxCondition(max_c)
    p.SetNormalPowerPerSecond(power)
    p.SetWeaponSystemType(wst_type)
    p.SetSingleFire(single_fire)
    p.SetAimedWeapon(aimed)
    return p


def test_phaser_dispatch():
    ship = ShipClass_Create("Galaxy")
    p = _make_ws("Phasers", WeaponSystemProperty.WST_PHASER)
    ship.GetPropertySet().AddToSet("Scene Root", p)
    ship.SetupProperties()

    phaser = ship.GetPhaserSystem()
    assert phaser.GetMaxCondition() == 4000.0
    assert phaser.GetNormalPowerPerSecond() == 300.0
    assert phaser.GetWeaponSystemType() == WeaponSystemProperty.WST_PHASER
    assert phaser.GetSingleFire() == 1


def test_torpedo_dispatch():
    ship = ShipClass_Create("Galaxy")
    p = _make_ws("Torpedoes", WeaponSystemProperty.WST_TORPEDO, max_c=2400.0, power=50.0)
    ship.GetPropertySet().AddToSet("Scene Root", p)
    ship.SetupProperties()
    torp = ship.GetTorpedoSystem()
    assert torp.GetMaxCondition() == 2400.0
    assert torp.GetWeaponSystemType() == WeaponSystemProperty.WST_TORPEDO


def test_pulse_and_tractor_dispatch():
    ship = ShipClass_Create("X")
    p = _make_ws("Pulse",   WeaponSystemProperty.WST_PULSE,   power=100.0)
    t = _make_ws("Tractor", WeaponSystemProperty.WST_TRACTOR, power=75.0)
    ship.GetPropertySet().AddToSet("Scene Root", p)
    ship.GetPropertySet().AddToSet("Scene Root", t)
    ship.SetupProperties()

    assert ship.GetPulseWeaponSystem().GetNormalPowerPerSecond() == 100.0
    assert ship.GetTractorBeamSystem().GetNormalPowerPerSecond() == 75.0
