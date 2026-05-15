"""EnergyWeaponProperty typed accessors land hardpoint values on the
property AND mirror them onto an attached subsystem."""
from engine.appc.properties import PhaserProperty
from engine.appc.subsystems import PhaserBank


def test_arc_width_round_trips():
    prop = PhaserProperty("test")
    prop.SetArcWidthAngles(-0.5, 1.2)
    assert prop.GetArcWidthAngles() == (-0.5, 1.2)


def test_arc_height_round_trips():
    prop = PhaserProperty("test")
    prop.SetArcHeightAngles(-0.05, 1.05)
    assert prop.GetArcHeightAngles() == (-0.05, 1.05)


def test_max_damage_round_trips():
    prop = PhaserProperty("test")
    prop.SetMaxDamage(250.0)
    assert prop.GetMaxDamage() == 250.0


def test_max_damage_distance_round_trips():
    prop = PhaserProperty("test")
    prop.SetMaxDamageDistance(60.0)
    assert prop.GetMaxDamageDistance() == 60.0


def test_subsystem_mirrors_arc_and_damage_from_property():
    prop = PhaserProperty("test")
    prop.SetArcWidthAngles(-0.9, 0.9)
    prop.SetArcHeightAngles(-0.05, 1.05)
    prop.SetMaxDamage(250.0)
    prop.SetMaxDamageDistance(60.0)

    bank = PhaserBank("test")
    bank.SetProperty(prop)

    assert bank.GetArcWidthAngles()    == (-0.9, 0.9)
    assert bank.GetArcHeightAngles()   == (-0.05, 1.05)
    assert bank.GetMaxDamage()         == 250.0
    assert bank.GetMaxDamageDistance() == 60.0


def test_subsystem_defaults_when_no_property_bound():
    bank = PhaserBank("test")
    # Defaults: full 360° arc, zero damage. Safe nulls.
    assert bank.GetArcWidthAngles()    == (-3.141592653589793, 3.141592653589793)
    assert bank.GetArcHeightAngles()   == (-1.5707963267948966, 1.5707963267948966)
    assert bank.GetMaxDamage()         == 0.0
    assert bank.GetMaxDamageDistance() == 0.0
