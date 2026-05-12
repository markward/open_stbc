"""After the shield API is wired up, the seven SDK shield-call rows must
not appear in App._stub_tracker.report()."""
import App
from engine.appc.properties import ShieldProperty
from engine.appc.ships import ShipClass_Create


SHIELD_STUB_NAMES = {
    "ShieldClass_Cast",
    "ShieldProperty_Cast",
    # Methods that previously chained off the _NamedStub Cast return:
    "GetMaxShields",
    "SetMaxShields",
    "SetCurShields",
    "GetSingleShieldPercentage",
    "GetShieldChargePerSecond",
    "SetShieldChargePerSecond",
    "GetProperty",
}


def test_difficulty_scale_path_records_no_shield_stubs():
    """Exercise the SDK-style loadspacehelper.SetDifficulty path that the
    stub profile flagged: ShieldClass_Cast(sub).GetProperty().SetMaxShields,
    etc.  After Tasks 1-9 these should all hit real implementations."""
    App._stub_tracker.clear()
    App._stub_tracker.set_mission("regression")

    ship = ShipClass_Create("Galaxy")
    sp = ShieldProperty("Shield Generator")
    for face in range(ShieldProperty.NUM_SHIELDS):
        sp.SetMaxShields(face, 1000.0)
        sp.SetShieldChargePerSecond(face, 10.0)
    ship.GetPropertySet().AddToSet("Scene Root", sp)
    ship.SetupProperties()

    pSubsystem = ship.GetShields()
    pNewProperty = sp
    fDFactor = 2.0

    # Mirrors loadspacehelper.py:243-258 verbatim:
    pShields = App.ShieldClass_Cast(pSubsystem)
    pShieldProperty = App.ShieldProperty_Cast(pNewProperty)
    assert pShields is not None
    assert pShieldProperty is not None

    pCurrentProperty = pShields.GetProperty()
    facings = [
        App.ShieldClass.FRONT_SHIELDS,
        App.ShieldClass.REAR_SHIELDS,
        App.ShieldClass.TOP_SHIELDS,
        App.ShieldClass.BOTTOM_SHIELDS,
        App.ShieldClass.LEFT_SHIELDS,
        App.ShieldClass.RIGHT_SHIELDS,
    ]
    for kFacing in facings:
        fPct = pShields.GetSingleShieldPercentage(kFacing)
        pCurrentProperty.SetMaxShields(
            kFacing, pShieldProperty.GetMaxShields(kFacing) * fDFactor)
        pShields.SetCurShields(
            kFacing, pShields.GetMaxShields(kFacing) * fPct)
        pCurrentProperty.SetShieldChargePerSecond(
            kFacing, pShieldProperty.GetShieldChargePerSecond(kFacing) * fDFactor)

    App._stub_tracker.reset_mission()
    leaked = {name for (name, _, _) in App._stub_tracker.report()
              if any(stub in name for stub in SHIELD_STUB_NAMES)}
    assert leaked == set(), (
        "Shield SDK calls still hit _NamedStub: " + repr(leaked))
