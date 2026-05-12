"""Pin the SetSkinShielding convention.

ShieldProperty has no explicit Set/Get for skin shielding — the Phase 1
data-bag at engine/appc/properties.py:24-46 auto-handles arbitrary Set*
calls. These tests pin the convention so a future refactor of the
data-bag can't silently break the renderer's mode flag without failing
a test.
"""
from engine.appc.properties import ShieldProperty


def test_set_skin_shielding_stores_value_in_databag():
    shield = ShieldProperty("Shield Generator")
    shield.SetSkinShielding(1)
    assert shield._data[("SkinShielding", ())] == 1


def test_default_no_skin_shielding_key():
    shield = ShieldProperty("Shield Generator")
    assert shield._data.get(("SkinShielding", ())) is None


def test_set_skin_shielding_zero_stores_zero():
    shield = ShieldProperty("Shield Generator")
    shield.SetSkinShielding(0)
    assert shield._data[("SkinShielding", ())] == 0


def test_sovereign_hardpoint_opts_into_skin_shielding():
    """Importing the project-root sovereign hardpoint should result in
    SkinShielding=1 on its ShieldGenerator. Indirectly verifies that
    ships/Hardpoints/sovereign.py shadows the SDK copy via _SDKFinder."""
    import sys
    import importlib
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]
    mod = importlib.import_module("ships.Hardpoints.sovereign")
    sg = getattr(mod, "ShieldGenerator")
    assert sg._data.get(("SkinShielding", ())) == 1
