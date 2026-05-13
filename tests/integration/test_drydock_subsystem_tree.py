"""End-to-end: loading the drydock hardpoint via loadspacehelper produces
the targets-panel subsystem tree the original game shows.  Pins all
behaviour the spec promises: labels from hardpoint, child emitters
under Tractors parent, Power Plant + Engineering surfaced."""
import importlib
import sys

from engine.appc.ships import ShipClass_Create
from engine.appc.subsystems import (
    HullSubsystem, ShieldSubsystem, SensorSubsystem,
    PowerSubsystem, RepairSubsystem, TractorBeamSystem, TractorBeam,
)


def _build_drydock():
    """Mirror loadspacehelper.CreateShip for ships.Hardpoints.drydock."""
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]
    mod = importlib.import_module("ships.Hardpoints.drydock")
    ship = ShipClass_Create("DryDock")
    mod.LoadPropertySet(ship.GetPropertySet())
    ship.SetupProperties()
    return ship


def test_drydock_hull_present_and_named():
    ship = _build_drydock()
    hull = ship.GetHull()
    assert isinstance(hull, HullSubsystem)
    assert hull.GetName() == "Hull"


def test_drydock_shield_generator_present_and_named():
    ship = _build_drydock()
    ss = ship.GetShieldSubsystem()
    assert isinstance(ss, ShieldSubsystem)
    assert ss.GetName() == "Shield Generator"


def test_drydock_sensor_array_named_from_hardpoint():
    ship = _build_drydock()
    sens = ship.GetSensorSubsystem()
    assert isinstance(sens, SensorSubsystem)
    assert sens.GetName() == "Sensor Array"


def test_drydock_power_plant_surfaced():
    ship = _build_drydock()
    pwr = ship.GetPowerSubsystem()
    assert isinstance(pwr, PowerSubsystem)
    assert pwr.GetName() == "Power Plant"


def test_drydock_engineering_surfaced():
    ship = _build_drydock()
    eng = ship.GetRepairSubsystem()
    assert isinstance(eng, RepairSubsystem)
    assert eng.GetName() == "Engineering"


def test_drydock_tractor_parent_named_tractors():
    ship = _build_drydock()
    parent = ship.GetTractorBeamSystem()
    assert isinstance(parent, TractorBeamSystem)
    assert parent.GetName() == "Tractors"


def test_drydock_tractor_has_four_named_children():
    ship = _build_drydock()
    parent = ship.GetTractorBeamSystem()
    assert parent.GetNumChildSubsystems() == 4
    names = sorted(parent.GetChildSubsystem(i).GetName() for i in range(4))
    assert names == sorted([
        "Aft Tractor 1", "Aft Tractor 2",
        "Forward Tractor 1", "Forward Tractor 2",
    ])
    for i in range(4):
        assert isinstance(parent.GetChildSubsystem(i), TractorBeam)


def test_drydock_has_no_phasers_no_torpedoes_no_pulse():
    """Drydock hardpoint registers no phasers/torps/pulse; Pass 3
    scrubs those slots and Pass 4 has nothing to attach."""
    ship = _build_drydock()
    assert ship.GetPhaserSystem() is None
    assert ship.GetTorpedoSystem() is None
    assert ship.GetPulseWeaponSystem() is None
