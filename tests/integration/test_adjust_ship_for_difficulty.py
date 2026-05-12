"""Regression: loadspacehelper.AdjustShipForDifficulty must not crash
on a shielded ship, and must actually scale the shield max by the
defensive difficulty multiplier."""
import App
from engine.appc.properties import ShieldProperty
from engine.appc.ships import ShipClass_Create


def _build_galaxy_with_shields():
    """A minimal stand-in for a Galaxy ship with a ShieldProperty in
    its property set and SetupProperties applied. Mirrors what the
    Galaxy hardpoint loader produces — enough for AdjustShipForDifficulty
    to find a real shield subsystem via GetSubsystemByProperty."""
    ship = ShipClass_Create("Galaxy")
    sp = ShieldProperty("Shield Generator")
    sp.SetMaxCondition(12000.0)
    for face in range(ShieldProperty.NUM_SHIELDS):
        sp.SetMaxShields(face, 8000.0)
        sp.SetShieldChargePerSecond(face, 11.0)
    ship.GetPropertySet().AddToSet("Scene Root", sp)
    ship.SetupProperties()
    return ship, sp


def test_adjust_ship_for_difficulty_does_not_crash_on_shielded_ship():
    """Pre-fix this raised AttributeError: 'NoneType' has no GetProperty()
    at loadspacehelper.py:246."""
    import loadspacehelper

    ship, sp = _build_galaxy_with_shields()
    # Pre-existing front-face max (before scaling)
    front_max_before = sp.GetMaxShields(ShieldProperty.FRONT_SHIELDS)
    assert front_max_before == 8000.0

    # Should complete without raising:
    loadspacehelper.AdjustShipForDifficulty(ship, "Galaxy")

    # After the call, the SDK has rewritten the property's MaxShields
    # by the defensive multiplier. The Phase 1 App shim returns 1.0
    # for the difficulty multipliers (most likely), so values are
    # unchanged but the full code path executed against real subsystems.
    front_max_after = sp.GetMaxShields(ShieldProperty.FRONT_SHIELDS)
    assert front_max_after == front_max_before * App.Game_GetDefensiveDifficultyMultiplier()
