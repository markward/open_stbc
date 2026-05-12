"""ShipClass.GetSubsystemByProperty — slot scan returning the live
subsystem whose source property matches the requested one."""
from engine.appc.properties import ShieldProperty, SensorProperty
from engine.appc.ships import ShipClass_Create


def test_returns_shield_subsystem_for_its_property():
    ship = ShipClass_Create("Galaxy")
    sp = ShieldProperty("Shield Generator")
    sp.SetMaxShields(ShieldProperty.FRONT_SHIELDS, 100.0)
    ship.GetPropertySet().AddToSet("Scene Root", sp)
    ship.SetupProperties()
    assert ship.GetSubsystemByProperty(sp) is ship.GetShields()


def test_returns_none_for_property_not_on_ship():
    ship = ShipClass_Create("Galaxy")
    sp = ShieldProperty("Shield Generator")
    sp.SetMaxShields(ShieldProperty.FRONT_SHIELDS, 100.0)
    ship.GetPropertySet().AddToSet("Scene Root", sp)
    ship.SetupProperties()
    foreign = ShieldProperty("foreign")
    assert ship.GetSubsystemByProperty(foreign) is None


def test_returns_none_when_no_subsystem_present():
    ship = ShipClass_Create("Galaxy")
    # No SetupProperties call - the ship has a default ShieldSubsystem
    # instance but no _property back-ref.
    sp = ShieldProperty("never registered")
    assert ship.GetSubsystemByProperty(sp) is None


def test_handles_unrelated_property_type():
    ship = ShipClass_Create("Galaxy")
    sp = ShieldProperty("Shield Generator")
    ship.GetPropertySet().AddToSet("Scene Root", sp)
    ship.SetupProperties()
    sensor_prop = SensorProperty("Sensors")
    assert ship.GetSubsystemByProperty(sensor_prop) is None
