"""Phase-1 backdrop shim: StarSphere / BackdropSphere materialisation."""
import pytest


def test_star_sphere_create_returns_star_kind():
    import App
    from engine.appc.backdrops import StarSphere, Backdrop
    s = App.StarSphere_Create()
    assert isinstance(s, StarSphere)
    assert s._kind == Backdrop.KIND_STAR


def test_backdrop_sphere_create_returns_backdrop_kind():
    import App
    from engine.appc.backdrops import BackdropSphere, Backdrop
    b = App.BackdropSphere_Create()
    assert isinstance(b, BackdropSphere)
    assert b._kind == Backdrop.KIND_BACKDROP


def test_backdrop_setters_round_trip():
    import App
    s = App.StarSphere_Create()
    s.SetTextureFileName("data/stars.tga")
    s.SetTargetPolyCount(512)
    s.SetHorizontalSpan(0.75)
    s.SetVerticalSpan(0.5)
    s.SetSphereRadius(420.0)
    s.SetTextureHTile(22.0)
    s.SetTextureVTile(11.0)
    assert s._texture_path == "data/stars.tga"
    assert s._target_poly_count == 512
    assert s._horizontal_span == 0.75
    assert s._vertical_span == 0.5
    assert s._sphere_radius == 420.0
    assert s._texture_h_tile == 22.0
    assert s._texture_v_tile == 11.0


def test_backdrop_defaults_match_bc_stock_pattern():
    import App
    s = App.StarSphere_Create()
    # Stock BC StarSphere defaults before any setter calls — derived from
    # the pattern in Systems/Biranu/Biranu1.LoadBackdrops.
    assert s._target_poly_count == 256
    assert s._horizontal_span == 1.0
    assert s._vertical_span == 1.0
    assert s._sphere_radius == 300.0
    assert s._texture_h_tile == 1.0
    assert s._texture_v_tile == 1.0
    assert s._texture_path == ""


def test_rebuild_is_noop():
    import App
    s = App.StarSphere_Create()
    assert s.Rebuild() is None


def test_backdrop_inherits_object_class_align_to_vectors():
    """Backdrop inherits ObjectClass so AlignToVectors works — required
    for the per-backdrop world rotation honored by the renderer."""
    import App
    from engine.appc.math import TGPoint3
    s = App.StarSphere_Create()
    fwd = TGPoint3(); fwd.SetXYZ(0.0, 1.0, 0.0)
    up  = TGPoint3(); up.SetXYZ(0.0, 0.0, 1.0)
    s.AlignToVectors(fwd, up)
    rot = s.GetWorldRotation()
    # Row 1 = forward axis post-AlignToVectors.
    assert rot.GetRow(1).y == pytest.approx(1.0)
