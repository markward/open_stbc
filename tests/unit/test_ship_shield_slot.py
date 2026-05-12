"""ShipClass exposes a ShieldSubsystem slot."""
from engine.appc.ships import ShipClass, ShipClass_Create
from engine.appc.subsystems import ShieldSubsystem


def test_default_ship_has_none():
    """A bare ShipClass() has no shield until ShipClass_Create or a setter wires one."""
    s = ShipClass()
    assert s.GetShieldSubsystem() is None


def test_shipclass_create_installs_shield():
    s = ShipClass_Create("Galaxy")
    assert isinstance(s.GetShieldSubsystem(), ShieldSubsystem)


def test_set_shield_subsystem():
    s = ShipClass()
    shield = ShieldSubsystem("Shield Generator")
    s.SetShieldSubsystem(shield)
    assert s.GetShieldSubsystem() is shield
