"""Tests for engine.appc.lens_flare."""
from engine.appc.sets import SetClass


def test_setclass_initializes_empty_lens_flares_list():
    pSet = SetClass()
    assert pSet._lens_flares == []
