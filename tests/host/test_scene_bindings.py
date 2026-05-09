"""Verify scene-graph + camera bindings round-trip through pybind11."""
import os


def test_instance_lifecycle_without_window():
    # No init() — these calls don't need a GL context yet.
    import _open_stbc_host
    iid = _open_stbc_host.create_instance(123)
    assert iid.generation > 0
    _open_stbc_host.set_world_transform(iid, [
        1.0, 0.0, 0.0, 5.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ])
    _open_stbc_host.set_visible(iid, False)
    _open_stbc_host.destroy_instance(iid)


def test_set_world_transform_rejects_wrong_length():
    import _open_stbc_host
    import pytest
    iid = _open_stbc_host.create_instance(0)
    try:
        with pytest.raises(RuntimeError):
            _open_stbc_host.set_world_transform(iid, [0.0] * 12)
    finally:
        _open_stbc_host.destroy_instance(iid)


def test_set_camera_does_not_raise():
    import _open_stbc_host
    _open_stbc_host.set_camera(
        eye=(0.0, 0.0, 5.0),
        target=(0.0, 0.0, 0.0),
        up=(0.0, 1.0, 0.0),
        fov_y_rad=1.0472,
        near=0.1,
        far=10000.0,
    )


def test_set_skybox_does_not_raise():
    import _open_stbc_host
    _open_stbc_host.set_skybox(0)
