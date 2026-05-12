"""SetupProperties Pass 2: count TorpedoTubeProperty + seed AT_ONE per tube."""
import App
from engine.appc.ships import ShipClass_Create
from engine.appc.properties import TorpedoTubeProperty, WeaponSystemProperty


def _make_tube(name):
    p = TorpedoTubeProperty(name)
    p.SetMaxCondition(2400.0)
    return p


def test_six_tubes_seed_six_ammo_slots():
    ship = ShipClass_Create("Galaxy")
    # Add 6 tubes (Galaxy: ForwardTorpedo1..4 + AftTorpedo1..2)
    for i in range(6):
        ship.GetPropertySet().AddToSet("Scene Root", _make_tube(f"Torpedo {i}"))
    # Plus the system entry (so dispatch works)
    sys_prop = WeaponSystemProperty("Torpedoes")
    sys_prop.SetWeaponSystemType(WeaponSystemProperty.WST_TORPEDO)
    ship.GetPropertySet().AddToSet("Scene Root", sys_prop)

    ship.SetupProperties()

    ts = ship.GetTorpedoSystem()
    assert ts.GetNumAmmoTypes() == 6
    for i in range(6):
        assert ts.GetAmmoType(i) == App.AT_ONE


def test_no_tubes_no_seeding():
    """A ship whose hardpoint registers no TorpedoTubeProperty and no
    WeaponSystemProperty(WST_TORPEDO) has no torpedo subsystem at all."""
    ship = ShipClass_Create("FedStarbase")
    ship.SetupProperties()
    assert ship.GetTorpedoSystem() is None


def _torpedo_system_property():
    """Real hardpoints register the WeaponSystemProperty(WST_TORPEDO)
    alongside the tube properties (see galaxy.py:1003).  Without it the
    Pass 3 scrub removes the torpedo subsystem, since the tubes alone
    don't back-reference the slot."""
    sys_prop = WeaponSystemProperty("Torpedoes")
    sys_prop.SetWeaponSystemType(WeaponSystemProperty.WST_TORPEDO)
    return sys_prop


def test_idempotent_against_re_run():
    ship = ShipClass_Create("Galaxy")
    ship.GetPropertySet().AddToSet("Scene Root", _torpedo_system_property())
    for i in range(2):
        ship.GetPropertySet().AddToSet("Scene Root", _make_tube(f"Torpedo {i}"))

    ship.SetupProperties()
    assert ship.GetTorpedoSystem().GetNumAmmoTypes() == 2
    # Re-run: should not double-seed.
    ship.SetupProperties()
    assert ship.GetTorpedoSystem().GetNumAmmoTypes() == 2
