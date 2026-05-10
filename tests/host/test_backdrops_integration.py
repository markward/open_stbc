"""End-to-end backdrop rendering tests."""
import os
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent.parent
GAME = PROJECT_ROOT / "game"
GALAXY_NIF = GAME / "data" / "Models" / "Ships" / "Galaxy" / "Galaxy.nif"
STARS_TGA = GAME / "data" / "stars.tga"


def _star_descriptor():
    return {
        "texture_path": str(STARS_TGA),
        "kind": "star",
        "h_tile": 22.0, "v_tile": 11.0,
        "h_span": 1.0, "v_span": 1.0,
        "world_rotation": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "target_poly_count": 256,
    }


def _setup_for_pixel_test():
    if not STARS_TGA.is_file():
        pytest.skip("BC assets not available")
    os.environ["OPEN_STBC_HOST_HEADLESS"] = "1"
    import _open_stbc_host
    _open_stbc_host.init(640, 360, "test_backdrops_integration")
    _open_stbc_host.set_camera(
        eye=(0.0, 0.0, 1500.0),
        target=(0.0, 0.0, 0.0),
        up=(0.0, 1.0, 0.0),
        fov_y_rad=1.0472, near=1.0, far=100000.0,
    )
    return _open_stbc_host


def test_backdrop_renders_into_corner_pixel():
    """Backdrop pixel at corner of viewport (no opaque geometry there)
    must NOT be the clear-color value (~13, 18, 26)."""
    h = _setup_for_pixel_test()
    try:
        h.set_backdrops([_star_descriptor()])
        h.frame()
        r, g, b, a = h.read_pixel(0, 0)
        clear = (13, 18, 26)
        diff = abs(int(r) - clear[0]) + abs(int(g) - clear[1]) + abs(int(b) - clear[2])
        assert diff > 5, (
            f"corner pixel = ({r},{g},{b}) — looks like the clear color; "
            f"backdrop did not render")
    finally:
        h.shutdown()


def _sample_row_brightness_sum(h, y: int) -> int:
    """Walk a horizontal stripe of the framebuffer and sum every R+G+B
    channel. The stars texture is sparse (mostly black with bright dots);
    a single-pixel sample often misses, but a 64-pixel stripe is very
    likely to overlap several stars and produce a deterministic-but-
    rotation-sensitive signature."""
    fw, _ = h.framebuffer_size()
    total = 0
    for i in range(64):
        x = i * (fw // 64)
        r, g, b, _ = h.read_pixel(x, y)
        total += int(r) + int(g) + int(b)
    return total


def test_camera_rotation_changes_pixels_translation_does_not():
    """Rotation reference: rotating the camera 30° about the up axis
    must change the rendered backdrop. Translation along the camera
    forward must NOT change the same row (modulo float noise).

    Samples a 64-pixel horizontal stripe and sums the channels to make
    the test robust against single-pixel sparse-starfield misses."""
    h = _setup_for_pixel_test()
    try:
        h.set_backdrops([_star_descriptor()])

        h.frame()
        baseline = _sample_row_brightness_sum(h, 32)

        # Translate forward 1000 units (camera moves toward origin).
        h.set_camera(
            eye=(0.0, 0.0, 500.0),
            target=(0.0, 0.0, -1000.0),
            up=(0.0, 1.0, 0.0),
            fov_y_rad=1.0472, near=1.0, far=100000.0,
        )
        h.frame()
        translated = _sample_row_brightness_sum(h, 32)

        # Rotation: 30° about up axis from baseline view.
        import math
        a = math.radians(30)
        new_target = (math.sin(a) * -1000.0, 0.0, math.cos(a) * -1000.0)
        h.set_camera(
            eye=(0.0, 0.0, 1500.0),
            target=new_target,
            up=(0.0, 1.0, 0.0),
            fov_y_rad=1.0472, near=1.0, far=100000.0,
        )
        h.frame()
        rotated = _sample_row_brightness_sum(h, 32)

        # Translation: same brightness sum within tolerance.
        assert abs(translated - baseline) <= 10, (
            f"translation should not change rendered stars: "
            f"baseline={baseline}, translated={translated}")

        # Rotation: brightness sum must differ from baseline. Stars are
        # bright enough that a 30° rotation typically swings the sum by
        # hundreds of channel-units.
        assert abs(rotated - baseline) > 50, (
            f"rotation should change rendered stars: "
            f"baseline={baseline}, rotated={rotated}")
    finally:
        h.shutdown()


def test_lighting_still_works_with_backdrops():
    """Regression: opaque pass lighting must not be broken by the new
    backdrop pass. Reuses the existing red-vs-black ambient assertion."""
    if not GALAXY_NIF.is_file():
        pytest.skip("BC assets not available")
    h = _setup_for_pixel_test()
    try:
        h.set_backdrops([_star_descriptor()])
        tex_search = str(GAME / "data" / "Models" / "SharedTextures" /
                         "FedShips" / "High")
        m = h.load_model(str(GALAXY_NIF), tex_search)
        iid = h.create_instance(m)
        h.set_world_transform(iid, [
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            0, 0, 0, 1,
        ])
        fw, fh = h.framebuffer_size()
        cx, cy = fw // 2, fh // 2

        h.set_lighting((1.0, 0.0, 0.0), [])
        h.frame()
        red_r, _, _, _ = h.read_pixel(cx, cy)

        h.set_lighting((0.0, 0.0, 0.0), [])
        h.frame()
        dark_r, _, _, _ = h.read_pixel(cx, cy)

        assert red_r > dark_r + 50, (
            f"lighting regressed after backdrops added: red_r={red_r}, dark_r={dark_r}")

        h.destroy_instance(iid)
    finally:
        h.shutdown()
