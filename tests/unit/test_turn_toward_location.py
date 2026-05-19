"""Unit tests for ShipClass.TurnTowardLocation.

Thin wrapper that computes the ship→target world direction and delegates
to the existing TurnDirectionsToDirections solver."""
import math

import pytest

import App
from engine.appc.math import TGPoint3, TGMatrix3
from engine.appc.ships import ShipClass


def test_target_ahead_zero_angular_velocity():
    """Ship at origin, identity rotation (world-forward = +Y),
    target at (0, 100, 0). Already aligned → zero AV."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    ship.TurnTowardLocation(TGPoint3(0.0, 100.0, 0.0))
    av = ship.GetTargetAngularVelocitySetpoint()
    assert av.x == pytest.approx(0.0, abs=1e-9)
    assert av.y == pytest.approx(0.0, abs=1e-9)
    assert av.z == pytest.approx(0.0, abs=1e-9)


def test_target_on_plus_x_yaws_around_minus_z():
    """Ship at origin, identity rotation, target on world +X.
    World-forward (+Y) × world-target-dir (+X) = -Z, so the
    angular velocity is around -Z."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    ship.TurnTowardLocation(TGPoint3(100.0, 0.0, 0.0))
    av = ship.GetTargetAngularVelocitySetpoint()
    assert av.x == pytest.approx(0.0, abs=1e-9)
    assert av.y == pytest.approx(0.0, abs=1e-9)
    assert av.z < 0.0
    assert abs(av.z) == pytest.approx(math.pi / 2.0, rel=1e-6)


def test_target_behind_picks_perpendicular_axis():
    """Ship at origin facing +Y, target at -Y. 180° flip; the solver
    falls back to an arbitrary perpendicular axis. Magnitude must
    still be non-zero (the ship needs to flip)."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    ship.TurnTowardLocation(TGPoint3(0.0, -100.0, 0.0))
    av = ship.GetTargetAngularVelocitySetpoint()
    mag = (av.x * av.x + av.y * av.y + av.z * av.z) ** 0.5
    assert mag > 1.0


def test_target_at_ship_location_is_noop():
    """Zero distance → solver should not blow up. SetTargetAngular-
    VelocityDirect must NOT be called (so any prior setpoint stays)."""
    ship = ShipClass()
    ship.SetTranslateXYZ(5.0, 5.0, 5.0)
    # Seed a non-zero prior setpoint to detect spurious overwrites.
    prior = TGPoint3(0.1, 0.2, 0.3)
    ship.SetTargetAngularVelocityDirect(prior)
    ship.TurnTowardLocation(TGPoint3(5.0, 5.0, 5.0))
    av = ship.GetTargetAngularVelocitySetpoint()
    assert (av.x, av.y, av.z) == pytest.approx((0.1, 0.2, 0.3))


def test_uses_column_vector_forward_after_yaw():
    """Ship yawed +π/2 around Z faces world -X (column-vector
    convention). Target at world (-100, 0, 0) is therefore directly
    ahead → zero AV. Pins that TurnTowardLocation reads forward
    via GetCol(1), not GetRow(1)."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    R = TGMatrix3(); R.MakeZRotation(math.pi / 2.0)
    ship.SetMatrixRotation(R)
    ship.TurnTowardLocation(TGPoint3(-100.0, 0.0, 0.0))
    av = ship.GetTargetAngularVelocitySetpoint()
    assert av.x == pytest.approx(0.0, abs=1e-6)
    assert av.y == pytest.approx(0.0, abs=1e-6)
    assert av.z == pytest.approx(0.0, abs=1e-6)
