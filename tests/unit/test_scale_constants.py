def test_scale_constants_exist():
    from engine.scale import SHIP_SCALE, ASTRO_SCALE, PLANET_NIF_NATIVE_RADIUS
    assert SHIP_SCALE == 1.0
    assert ASTRO_SCALE == 1.0
    assert PLANET_NIF_NATIVE_RADIUS == 45.0
