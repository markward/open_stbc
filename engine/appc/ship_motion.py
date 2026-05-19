"""Per-tick kinematic integrator for AI-controlled ships.

Reads each ship's _speed_setpoint and _target_angular_velocity_setpoint
(written by AI scripts via ShipClass.SetSpeed / SetImpulse /
SetTargetAngularVelocityDirect), ramps _current_speed and
_current_angular_velocity toward those targets at the ship's
MaxAccel / MaxAngularAccel, and integrates the result into the ship's
world transform.

Mirrors _PlayerControl.apply() in engine/host_loop.py (lines 594-769) —
same row-vector matrix convention, same Y-forward Z-up frame, same
linear ramp helper, same IES-fallback (FALLBACK_MAX_ACCEL = 1e9) for
ships without a populated impulse engine subsystem.

Ships whose setpoints have never been written (both _speed_setpoint
and _target_angular_velocity_setpoint are None) are skipped entirely —
the player ship drives its transform via _PlayerControl directly, not
via setpoints, so this integrator must leave it alone.
"""
from engine.appc.math import TGMatrix3, TGPoint3
from engine.appc.objects import PhysicsObjectClass

# Match _PlayerControl.FALLBACK_MAX_ACCEL in engine/host_loop.py:613.
# Used when a ship has no ImpulseEngineSubsystem with non-zero MaxSpeed
# (i.e. test ships built with ShipClass() directly, before SetupProperties).
FALLBACK_MAX_ACCEL = 1.0e9

# Body-frame axes — matches _PlayerControl convention.
_X_AXIS = TGPoint3(1.0, 0.0, 0.0)
_Y_AXIS = TGPoint3(0.0, 1.0, 0.0)
_Z_AXIS = TGPoint3(0.0, 0.0, 1.0)


def tick_all_ship_motion(dt: float) -> None:
    """Iterate every live ship and advance its motion by `dt` seconds."""
    from engine.appc.ship_iter import iter_ships
    for ship in iter_ships():
        _step_ship_motion(ship, dt)


def _ramp_toward(current: float, target: float, step: float) -> float:
    """Linear ramp: move `current` toward `target` by at most `step`."""
    delta = target - current
    if abs(delta) <= step:
        return target
    return current + (step if delta > 0 else -step)


def _max_accel(ship) -> float:
    ies = ship.GetImpulseEngineSubsystem()
    if ies is not None and ies.GetMaxSpeed() > 0.0:
        a = ies.GetMaxAccel()
        return a if a > 0.0 else FALLBACK_MAX_ACCEL
    return FALLBACK_MAX_ACCEL


def _max_angular_accel(ship) -> float:
    ies = ship.GetImpulseEngineSubsystem()
    if ies is not None and ies.GetMaxAngularVelocity() > 0.0:
        a = ies.GetMaxAngularAccel()
        return a if a > 0.0 else FALLBACK_MAX_ACCEL
    return FALLBACK_MAX_ACCEL


def _step_ship_motion(ship, dt: float) -> None:
    """Advance one ship's transform by one tick.

    Skips entirely if no setpoint has ever been written — preserves the
    player ship (which drives its transform via _PlayerControl, not
    setpoints) and freshly-spawned non-AI props.
    """
    sp = getattr(ship, "_speed_setpoint", None)
    av = getattr(ship, "_target_angular_velocity_setpoint", None)
    if sp is None and av is None:
        return
    # Placeholder for Tasks 2 + 3: zero-setpoint case must be a no-op.
    # If both setpoints have been written but evaluate to zero, the
    # current-state ramp toward zero is also zero, so nothing happens.
    # Tasks 2/3 will replace this body with the real linear + angular
    # integration. For now, return so the Stay-position-unchanged test
    # passes.
    return
