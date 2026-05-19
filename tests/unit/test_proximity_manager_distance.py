"""Unit tests for ProximityManager.GetNearObjects — real-distance filter."""
import pytest

import App
from engine.appc.math import TGPoint3
from engine.appc.planet import ProximityManager
from engine.appc.ships import ShipClass


def _make_ship_at(x, y, z):
    s = ShipClass()
    s.SetTranslateXYZ(x, y, z)
    return s


def test_get_near_objects_returns_empty_when_manager_is_empty():
    pm = ProximityManager()
    assert pm.GetNearObjects(TGPoint3(0, 0, 0), 100.0) == ()


def test_get_near_objects_includes_within_radius():
    pm = ProximityManager()
    s_close = _make_ship_at(10.0, 0.0, 0.0)
    s_far = _make_ship_at(500.0, 0.0, 0.0)
    pm.AddObject(s_close); pm.AddObject(s_far)
    result = pm.GetNearObjects(TGPoint3(0, 0, 0), 100.0)
    assert s_close in result
    assert s_far not in result


def test_get_near_objects_includes_exactly_at_radius():
    pm = ProximityManager()
    s_edge = _make_ship_at(100.0, 0.0, 0.0)
    pm.AddObject(s_edge)
    result = pm.GetNearObjects(TGPoint3(0, 0, 0), 100.0)
    assert s_edge in result


def test_get_near_objects_diagonal_distance():
    """Pythagorean — make sure we're using sqrt(x^2+y^2+z^2) not max-norm."""
    pm = ProximityManager()
    # distance = sqrt(60^2 + 80^2) = 100
    s = _make_ship_at(60.0, 80.0, 0.0)
    pm.AddObject(s)
    assert s in pm.GetNearObjects(TGPoint3(0, 0, 0), 100.0)
    assert s not in pm.GetNearObjects(TGPoint3(0, 0, 0), 99.0)
