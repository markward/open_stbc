import App
from engine.appc.ships import ShipClass
from engine.appc.math import TGPoint3, TGPoint3_GetModelForward


def test_set_speed_records_setpoint():
    ship = ShipClass()
    fwd = TGPoint3_GetModelForward()
    ship.SetSpeed(0.0, fwd, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    sp = ship.GetSpeedSetpoint()
    assert sp[0] == 0.0
    assert sp[2] == App.PhysicsObjectClass.DIRECTION_MODEL_SPACE


def test_set_target_angular_velocity_direct_records_setpoint():
    ship = ShipClass()
    v = TGPoint3(); v.SetXYZ(0.0, 0.0, 0.0)
    ship.SetTargetAngularVelocityDirect(v)
    av = ship.GetTargetAngularVelocitySetpoint()
    assert (av.x, av.y, av.z) == (0.0, 0.0, 0.0)


def test_set_speed_nonzero_round_trip():
    ship = ShipClass()
    fwd = TGPoint3_GetModelForward()
    ship.SetSpeed(120.5, fwd, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    sp = ship.GetSpeedSetpoint()
    assert sp[0] == 120.5
