import pytest


def _make_pose(x, y, z, radius=0.0):
    """Minimal stand-in for a ship or planet object with the pose API."""
    from engine.appc.math import TGPoint3, TGMatrix3

    class _Pose:
        def __init__(self):
            self._loc = TGPoint3(x, y, z)
            self._rot = TGMatrix3()  # identity by default
            self._radius = radius

        def GetWorldLocation(self):
            return self._loc

        def GetWorldRotation(self):
            return self._rot

        def GetRadius(self):
            return self._radius

    return _Pose()


def test_ship_world_matrix_scales_mesh_not_position():
    """Identity rotation: upper-left 3x3 scaled by SHIP_SCALE, translation unchanged."""
    from engine import host_loop
    from engine.scale import SHIP_SCALE

    pose = _make_pose(100.0, 200.0, 300.0)
    m = host_loop._ship_world_matrix(pose)

    assert len(m) == 16
    # Upper-left 3x3: identity * SHIP_SCALE
    assert m[0]  == pytest.approx(SHIP_SCALE)   # row0 col0
    assert m[5]  == pytest.approx(SHIP_SCALE)   # row1 col1
    assert m[10] == pytest.approx(SHIP_SCALE)   # row2 col2
    # Off-diagonal rotation elements -> 0
    assert m[1]  == pytest.approx(0.0)
    assert m[4]  == pytest.approx(0.0)
    # Translation column: unchanged world position
    assert m[3]  == pytest.approx(100.0)
    assert m[7]  == pytest.approx(200.0)
    assert m[11] == pytest.approx(300.0)
    # Homogeneous row
    assert m[12] == pytest.approx(0.0)
    assert m[13] == pytest.approx(0.0)
    assert m[14] == pytest.approx(0.0)
    assert m[15] == pytest.approx(1.0)


def test_camera_constants_match_ship_scale():
    """CAM_BACK_DIST and CAM_UP_DIST must be scaled by SHIP_SCALE relative to
    their original BC values (600 and 200 respectively)."""
    from engine import host_loop
    from engine.scale import SHIP_SCALE

    assert host_loop.CAM_BACK_DIST == pytest.approx(600.0 * SHIP_SCALE)
    assert host_loop.CAM_UP_DIST   == pytest.approx(200.0 * SHIP_SCALE)


def test_ship_world_matrix_columns_are_body_axes_in_world():
    """BC's TGMatrix3 is row-vector (rows = body axes in world). The OpenGL
    shader expects column-vector u_model (columns = body axes in world). The
    matrix sent to the renderer must therefore be the transpose of the BC
    rotation so the rendered ship's body axes match what the camera and
    physics-motion code (which read R.GetRow(j)) think they are.

    Regression test for the bug where pitch/roll/yaw made the camera drift
    off the rendered ship's actual rear because of this row/column mismatch."""
    import math
    from engine import host_loop
    from engine.scale import SHIP_SCALE

    pose = _make_pose(0.0, 0.0, 0.0)
    pose._rot.MakeZRotation(math.radians(45))  # non-symmetric rotation

    m = host_loop._ship_world_matrix(pose)

    # Column j of the row-major mat4 lives at positions j, 4+j, 8+j.
    # It must equal R.GetRow(j) * SHIP_SCALE (BC-convention body axis j in world).
    rgt = pose._rot.GetRow(0)
    fwd = pose._rot.GetRow(1)
    up  = pose._rot.GetRow(2)
    s = SHIP_SCALE

    assert m[0]  == pytest.approx(rgt.x * s)
    assert m[4]  == pytest.approx(rgt.y * s)
    assert m[8]  == pytest.approx(rgt.z * s)
    assert m[1]  == pytest.approx(fwd.x * s)
    assert m[5]  == pytest.approx(fwd.y * s)
    assert m[9]  == pytest.approx(fwd.z * s)
    assert m[2]  == pytest.approx(up.x  * s)
    assert m[6]  == pytest.approx(up.y  * s)
    assert m[10] == pytest.approx(up.z  * s)


def test_astro_world_matrix_columns_are_body_axes_in_world():
    """Same row/column convention as ships, applied to planet/moon meshes
    so non-spherical astro objects render with their BC-convention body axes
    matching the camera/physics view."""
    import math
    from engine import host_loop
    from engine.scale import ASTRO_SCALE, PLANET_NIF_NATIVE_RADIUS

    pose = _make_pose(0.0, 0.0, 0.0, radius=170.0)
    pose._rot.MakeZRotation(math.radians(45))

    m = host_loop._astro_world_matrix(pose)

    rgt = pose._rot.GetRow(0)
    fwd = pose._rot.GetRow(1)
    up  = pose._rot.GetRow(2)
    s = 170.0 * ASTRO_SCALE / PLANET_NIF_NATIVE_RADIUS

    assert m[0]  == pytest.approx(rgt.x * s)
    assert m[4]  == pytest.approx(rgt.y * s)
    assert m[8]  == pytest.approx(rgt.z * s)
    assert m[1]  == pytest.approx(fwd.x * s)
    assert m[5]  == pytest.approx(fwd.y * s)
    assert m[9]  == pytest.approx(fwd.z * s)
    assert m[2]  == pytest.approx(up.x  * s)
    assert m[6]  == pytest.approx(up.y  * s)
    assert m[10] == pytest.approx(up.z  * s)


def test_astro_world_matrix_scales_mesh_and_position():
    """Identity rotation, radius=170: position * ASTRO_SCALE, mesh scale from radius."""
    from engine import host_loop
    from engine.scale import ASTRO_SCALE, PLANET_NIF_NATIVE_RADIUS

    pose = _make_pose(100.0, 200.0, 300.0, radius=170.0)
    m = host_loop._astro_world_matrix(pose)

    expected_mesh_scale = 170.0 * ASTRO_SCALE / PLANET_NIF_NATIVE_RADIUS  # ~37.78

    assert len(m) == 16
    # Upper-left 3x3: identity * expected_mesh_scale
    assert m[0]  == pytest.approx(expected_mesh_scale)
    assert m[5]  == pytest.approx(expected_mesh_scale)
    assert m[10] == pytest.approx(expected_mesh_scale)
    # Off-diagonal rotation elements -> 0
    assert m[1]  == pytest.approx(0.0)
    assert m[4]  == pytest.approx(0.0)
    # Translation column: position * ASTRO_SCALE
    assert m[3]  == pytest.approx(100.0 * ASTRO_SCALE)
    assert m[7]  == pytest.approx(200.0 * ASTRO_SCALE)
    assert m[11] == pytest.approx(300.0 * ASTRO_SCALE)
    # Homogeneous row
    assert m[15] == pytest.approx(1.0)
