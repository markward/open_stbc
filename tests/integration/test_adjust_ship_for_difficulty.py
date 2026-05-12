"""Regression: loadspacehelper.AdjustShipForDifficulty must not crash
on a shielded ship, and must actually scale the shield max by the
defensive difficulty multiplier."""
import importlib
import sys

import App
from engine.appc.properties import (
    ImpulseEngineProperty,
    SensorProperty,
    ShieldProperty,
    WarpEngineProperty,
    WeaponSystemProperty,
)
from engine.appc.ships import ShipClass_Create
from engine.appc.subsystems import (
    ImpulseEngineSubsystem,
    PhaserSystem,
    SensorSubsystem,
    TorpedoSystem,
    TractorBeamSystem,
    WarpEngineSubsystem,
)


def _build_galaxy_with_shields():
    """Build a Galaxy ship the way loadspacehelper.CreateShip does:
    run ships.Hardpoints.Galaxy.LoadPropertySet on the ship's own
    property set, then SetupProperties. AdjustShipForDifficulty
    iterates pShipList and pNewList in parallel and assumes the two
    have matching length and per-index type (loadspacehelper.py:177-184);
    loading both sets through the same hardpoint module guarantees that."""
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]
    mod = importlib.import_module("ships.Hardpoints.Galaxy")
    ship = ShipClass_Create("Galaxy")
    mod.LoadPropertySet(ship.GetPropertySet())
    ship.SetupProperties()
    sp = next(iter(ship.GetPropertySet().GetPropertiesByType(ShieldProperty)))
    return ship, sp


def test_adjust_ship_for_difficulty_does_not_crash_on_shielded_ship():
    """Pre-fix this raised AttributeError: 'NoneType' has no GetProperty()
    at loadspacehelper.py:246."""
    import loadspacehelper

    ship, sp = _build_galaxy_with_shields()
    front_max_before = sp.GetMaxShields(ShieldProperty.FRONT_SHIELDS)
    assert front_max_before == 8000.0

    loadspacehelper.AdjustShipForDifficulty(ship, "Galaxy")

    # AdjustShipForDifficulty rewrites the ship-side property's MaxShields
    # to (fresh-template MaxShields) × defensive multiplier. Both sides
    # come from the same hardpoint file (Galaxy has FRONT=8000) and the
    # Phase 1 shim returns 1.0 for the multiplier, so the value stays
    # at 8000 — but the full code path executed against real subsystems.
    front_max_after = sp.GetMaxShields(ShieldProperty.FRONT_SHIELDS)
    assert front_max_after == 8000.0 * App.Game_GetDefensiveDifficultyMultiplier()


def test_setup_properties_wires_subsystem_back_references():
    """Every populated single-slot subsystem must point back at the
    source property template loaded from the hardpoint file. Without
    this, loadspacehelper.GetSubsystemByProperty() returns None for
    everything except Hull and Shields, and AdjustShipForDifficulty
    silently skips per-subsystem scaling for impulse/warp/sensors/
    weapons/tractor."""
    ship, _ = _build_galaxy_with_shields()

    # Weapon systems (phaser/torpedo/tractor) are templated by a
    # WeaponSystemProperty with a WST_* discriminator, not by their child
    # weapon properties (PhaserProperty, TorpedoTubeProperty). Engine slots
    # match the parent WeaponSystemProperty — individual weapons aren't
    # modelled as standalone subsystems in Phase 1.
    expected = (
        ("_sensor_subsystem",         SensorSubsystem,        SensorProperty,         None),
        ("_impulse_engine_subsystem", ImpulseEngineSubsystem, ImpulseEngineProperty,  None),
        ("_warp_engine_subsystem",    WarpEngineSubsystem,    WarpEngineProperty,     None),
        ("_phaser_system",            PhaserSystem,           WeaponSystemProperty,   WeaponSystemProperty.WST_PHASER),
        ("_torpedo_system",           TorpedoSystem,          WeaponSystemProperty,   WeaponSystemProperty.WST_TORPEDO),
        ("_tractor_beam_system",      TractorBeamSystem,      WeaponSystemProperty,   WeaponSystemProperty.WST_TRACTOR),
    )
    for slot, sub_cls, prop_cls, wst in expected:
        sub = getattr(ship, slot)
        assert isinstance(sub, sub_cls), f"{slot} not populated"
        prop = sub.GetProperty()
        assert prop is not None, f"{slot}.GetProperty() is None (back-ref missing)"
        assert isinstance(prop, prop_cls), (
            f"{slot}.GetProperty() is {type(prop).__name__}, expected {prop_cls.__name__}"
        )
        if wst is not None:
            assert prop.GetWeaponSystemType() == wst, (
                f"{slot}.GetProperty().GetWeaponSystemType() = "
                f"{prop.GetWeaponSystemType()}, expected {wst}"
            )
        # And the inverse — the ship can find the subsystem by its property.
        assert ship.GetSubsystemByProperty(prop) is sub, (
            f"ship.GetSubsystemByProperty(<{prop_cls.__name__}>) did not return the {slot} instance"
        )
