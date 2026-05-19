# Ship AI Intercept Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `PlainAI("Intercept")` actually close on a target — load the real SDK script, fill the six engine API holes it calls, ship a teleport-to-near-target `InSystemWarp`, and prove the chain end-to-end with a smoke test where a hostile flies in from +5000 units and halts at intercept range.

**Architecture:** All five components are small additions on top of the just-shipped Ship AI Motion slice (commit `bb3b27c` + `68f6220`). The SDK's [`Intercept.Update`](../../../sdk/Build/scripts/AI/PlainAI/Intercept.py) is already complete; the work is filling in `ShipClass.TurnTowardLocation`, `ShipClass.InSystemWarp`, `ShipClass.StopInSystemWarp`, `PhysicsObjectClass.GetAccelerationTG`, `App.PhysicsObjectClass_Cast`, plus the latent `GetWorldForwardTG` row/col fix (same shape as `68f6220`). The integrator and AI driver are untouched.

**Tech Stack:** Python 3, pytest, existing `engine/appc/` Phase-1 shims, `engine/appc/math.TGPoint3` / `TGMatrix3` (column-vector convention via `MultMatrixLeft` / `GetCol`), real SDK `AI/PlainAI/Intercept.py` loaded via the `_SDKFinder` in [tests/conftest.py](../../../tests/conftest.py).

**Spec:** [docs/superpowers/specs/2026-05-18-ship-ai-intercept-design.md](../specs/2026-05-18-ship-ai-intercept-design.md) — read this first; the non-goals, components, and risks lists are authoritative.

---

## File Structure

| File | Responsibility |
|---|---|
| [`engine/appc/ships.py`](../../../engine/appc/ships.py) (modify) | Add three motion methods: `TurnTowardLocation` (wraps `TurnDirectionsToDirections`), `InSystemWarp` (stateless teleport-to-near-target), `StopInSystemWarp` (no-op). |
| [`engine/appc/objects.py`](../../../engine/appc/objects.py) (modify) | Add `PhysicsObjectClass.GetAccelerationTG()` returning zero vec. Add `PhysicsObjectClass_Cast(obj)` next to existing `ObjectClass_Cast`. Fix `GetWorldForwardTG` row/col bug. |
| [`App.py`](../../../App.py) (modify) | Re-export `PhysicsObjectClass_Cast` in the existing `from engine.appc.objects import (...)` block. |
| `tests/unit/test_physics_object_accel.py` (new) | `GetAccelerationTG` + `PhysicsObjectClass_Cast` unit tests. |
| `tests/unit/test_ship_motion.py` (modify) | Add `GetWorldForwardTG` column-vector regression test. |
| `tests/unit/test_turn_toward_location.py` (new) | `TurnTowardLocation` unit tests covering aligned / behind / perpendicular / zero-distance / setpoint-write paths. |
| `tests/unit/test_in_system_warp.py` (new) | `InSystemWarp` + `StopInSystemWarp` unit tests covering far-teleport / near-no-op / None-target / speed-zeroing / return-value / no-op contract. |
| `tests/integration/test_ai_intercept_smoke.py` (new) | End-to-end: hostile at +5000 closes on player at origin via warp + brake-aware impulse, halts at intercept range, ends `US_DONE`. |
| `sdk/Build/scripts/Custom/Tutorial/Episode/AIIntercept/AIIntercept.py` (new, gitignored) | Visible mission fixture. |
| `sdk/Build/scripts/Custom/Tutorial/Episode/AIIntercept/__init__.py` (new, gitignored) | Empty package marker. |
| [`docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md`](../deferred/2026-05-18-ship-ai-runtime.md) (modify) | Strike completed Intercept items; document warp-visuals + obstacle-avoidance follow-ups. |

---

## Task 1: `GetAccelerationTG` + `PhysicsObjectClass_Cast` + `GetWorldForwardTG` fix

Three small additions to `engine/appc/objects.py`. All needed before `Intercept.Update` can run without `_Stub` fallthrough. Bundled into one task because they all touch the same file and have trivial implementations.

**Files:**
- Modify: [`engine/appc/objects.py`](../../../engine/appc/objects.py)
- Modify: [`App.py`](../../../App.py) (one line in existing import block)
- Test: `tests/unit/test_physics_object_accel.py` (new)
- Test: `tests/unit/test_ship_motion.py` (modify — append one test)

- [ ] **Step 1.1: Write failing tests for `GetAccelerationTG` + `PhysicsObjectClass_Cast`**

Create `tests/unit/test_physics_object_accel.py`:

```python
"""Unit tests for PhysicsObjectClass.GetAccelerationTG and PhysicsObjectClass_Cast.

These two pieces unblock the real SDK Intercept.Update, which calls
GetPredictedPosition(loc, GetVelocityTG(), GetAccelerationTG(), t) and
guards the call with App.PhysicsObjectClass_Cast(target)."""
import App
from engine.appc.math import TGPoint3
from engine.appc.objects import ObjectClass, PhysicsObjectClass
from engine.appc.placement import PlacementObject
from engine.appc.ships import ShipClass


def test_get_acceleration_tg_returns_zero_vector():
    """Phase 1 kinematic model: acceleration is the integrator's per-tick
    ramp, not stored on the object. Zero is the right default — degrades
    GetPredictedPosition(p, v, a, t) gracefully to p + v*t."""
    obj = PhysicsObjectClass()
    a = obj.GetAccelerationTG()
    assert isinstance(a, TGPoint3)
    assert (a.x, a.y, a.z) == (0.0, 0.0, 0.0)


def test_get_acceleration_tg_returns_fresh_vec_each_call():
    """Caller may mutate the returned vec; subsequent calls must not see
    the mutation. Mirrors GetVelocityTG's defensive-copy contract."""
    obj = PhysicsObjectClass()
    a1 = obj.GetAccelerationTG()
    a1.SetXYZ(99.0, 99.0, 99.0)
    a2 = obj.GetAccelerationTG()
    assert (a2.x, a2.y, a2.z) == (0.0, 0.0, 0.0)


def test_physics_object_class_cast_returns_input_for_ship():
    """ShipClass extends DamageableObject extends PhysicsObjectClass, so a
    ShipClass IS a PhysicsObjectClass. Cast returns the ship."""
    ship = ShipClass()
    assert App.PhysicsObjectClass_Cast(ship) is ship


def test_physics_object_class_cast_returns_none_for_non_physics():
    """A bare ObjectClass (e.g. PlacementObject) is NOT a PhysicsObjectClass.
    Cast returns None so SDK guards (`if pPhysicsObject is None:`) work."""
    placement = PlacementObject()
    assert App.PhysicsObjectClass_Cast(placement) is None


def test_physics_object_class_cast_returns_none_for_none():
    """None input → None output, no AttributeError."""
    assert App.PhysicsObjectClass_Cast(None) is None
```

Append to `tests/unit/test_ship_motion.py` (at the end of the file):

```python
def test_get_world_forward_tg_uses_column_convention():
    """After yaw +π/2 around Z, GetWorldForwardTG() must return world -X
    under the column-vector convention used by the integrator + SDK.
    Same shape as the regression test that pinned GetRelativePositionInfo
    (commit 68f6220) — closes the matching latent bug in
    engine/appc/objects.py."""
    ship = ShipClass()
    R = TGMatrix3(); R.MakeZRotation(math.pi / 2.0)
    ship.SetMatrixRotation(R)
    fwd = ship.GetWorldForwardTG()
    assert fwd.x == pytest.approx(-1.0, abs=1e-6)
    assert fwd.y == pytest.approx(0.0, abs=1e-6)
    assert fwd.z == pytest.approx(0.0, abs=1e-9)
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_physics_object_accel.py tests/unit/test_ship_motion.py::test_get_world_forward_tg_uses_column_convention -v`

Expected outcomes:
- `test_get_acceleration_tg_returns_zero_vector` — FAIL: `GetAccelerationTG` is currently a `_Stub` from the parent `__getattr__`; the returned stub fails the `isinstance(a, TGPoint3)` assertion.
- `test_get_acceleration_tg_returns_fresh_vec_each_call` — FAIL: same underlying issue (stub doesn't have `SetXYZ` or `.x`).
- `test_physics_object_class_cast_returns_input_for_ship` — FAIL: `App.PhysicsObjectClass_Cast` is a `_NamedStub`, calling it returns another stub, not the ship.
- `test_physics_object_class_cast_returns_none_for_non_physics` — FAIL: same.
- `test_physics_object_class_cast_returns_none_for_none` — FAIL: same.
- `test_get_world_forward_tg_uses_column_convention` — FAIL: returns `(1, 0, 0)` (row 1) instead of `(-1, 0, 0)` (col 1).

- [ ] **Step 1.3: Add `GetAccelerationTG` to `PhysicsObjectClass`**

In [`engine/appc/objects.py`](../../../engine/appc/objects.py), inside the `PhysicsObjectClass` definition near `GetVelocityTG` (around line 216), add:

```python
    def GetAccelerationTG(self) -> TGPoint3:
        """Phase 1: kinematic model stores no acceleration on the object —
        acceleration is the integrator's per-tick ramp. Returns a fresh
        zero vec so callers can mutate without leaking state. SDK Intercept
        uses this as the `a` arg to GetPredictedPosition; with a = 0 the
        prediction degenerates to p + v·t, correct at near-constant
        velocity."""
        return TGPoint3(0.0, 0.0, 0.0)
```

- [ ] **Step 1.4: Add `PhysicsObjectClass_Cast` module-level helper**

In [`engine/appc/objects.py`](../../../engine/appc/objects.py), directly after the existing `ObjectClass_Cast` definition (~line 487-496), add:

```python
def PhysicsObjectClass_Cast(obj) -> "PhysicsObjectClass | None":
    """Return obj if it is a PhysicsObjectClass, else None.

    SDK pattern (AI/PlainAI/Intercept.py): cast a generic target to its
    physics-object form before reading velocity/acceleration. Targets
    that are bare ObjectClass / PlacementObject have no velocity, so
    callers fall back to current position when this returns None.
    """
    return obj if isinstance(obj, PhysicsObjectClass) else None
```

- [ ] **Step 1.5: Fix `GetWorldForwardTG` row/col bug**

In [`engine/appc/objects.py`](../../../engine/appc/objects.py), line 185-187 currently reads:

```python
    def GetWorldForwardTG(self) -> TGPoint3:
        """Return forward vector (row 1 of rotation matrix, BC uses Y-forward)."""
        return self._rotation.GetRow(1)
```

Replace with:

```python
    def GetWorldForwardTG(self) -> TGPoint3:
        """World-forward = R · model_forward = column 1 of R.

        Column-vector convention matches the integrator
        (engine/appc/ship_motion.py uses MultMatrixLeft) and the SDK's
        TurnToOrientation.Update. Same fix shape as commit 68f6220
        which closed the equivalent bug in GetRelativePositionInfo.
        """
        return self._rotation.GetCol(1)
```

- [ ] **Step 1.6: Re-export `PhysicsObjectClass_Cast` from `App.py`**

In [`App.py`](../../../App.py), find the existing `from engine.appc.objects import (...)` block (lines 24-30):

```python
from engine.appc.objects import (
    ObjectClass, PhysicsObjectClass, DamageableObject,
    ObjectGroup, ObjectGroupWithInfo,
    ObjectGroup_ForceToGroup, ObjectGroup_FromModule, ObjectGroupWithInfo_Cast,
    ObjectClass_Cast, ObjectClass_GetObject, ObjectClass_GetObjectByID,
    IsNull,
)
```

Add `PhysicsObjectClass_Cast` to the imports — the cleanest spot is alongside `ObjectClass_Cast`:

```python
from engine.appc.objects import (
    ObjectClass, PhysicsObjectClass, DamageableObject,
    ObjectGroup, ObjectGroupWithInfo,
    ObjectGroup_ForceToGroup, ObjectGroup_FromModule, ObjectGroupWithInfo_Cast,
    ObjectClass_Cast, PhysicsObjectClass_Cast,
    ObjectClass_GetObject, ObjectClass_GetObjectByID,
    IsNull,
)
```

- [ ] **Step 1.7: Run the tests; expect all to pass**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_physics_object_accel.py tests/unit/test_ship_motion.py -q`

Expected: 23 PASS — 5 new tests in `test_physics_object_accel.py` plus 18 in `test_ship_motion.py` (the prior 17 — 16 from the Motion slice plus 1 added by commit `68f6220` — plus the new `test_get_world_forward_tg_uses_column_convention`).

If `test_physics_object_class_cast_returns_input_for_ship` fails because `ShipClass` does NOT extend `PhysicsObjectClass`, inspect the class hierarchy at [engine/appc/ships.py:1](../../../engine/appc/ships.py#L1) and [engine/appc/objects.py:308](../../../engine/appc/objects.py#L308). Existing CLAUDE.md confirms the hierarchy: `ObjectClass → PhysicsObjectClass → DamageableObject → ShipClass` — so the cast should succeed.

- [ ] **Step 1.8: Run broader regression suite**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_loop.py tests/unit/test_turn_directions.py tests/integration/test_ai_stay_smoke.py tests/integration/test_ai_goforward_smoke.py tests/integration/test_ai_turn_to_orientation_smoke.py -q`

Expected: all green. The `GetWorldForwardTG` fix is the only behaviour change to existing code paths; nothing in the current test suite reads it under non-identity rotation, so all pre-existing assertions still hold.

- [ ] **Step 1.9: Commit**

```bash
git add engine/appc/objects.py App.py tests/unit/test_physics_object_accel.py tests/unit/test_ship_motion.py
git commit -m "feat(objects): GetAccelerationTG + PhysicsObjectClass_Cast + GetWorldForwardTG col-vec fix"
```

---

## Task 2: `TurnTowardLocation`

Thin wrapper on `TurnDirectionsToDirections` that takes a world-space target point and sets the angular-velocity setpoint to rotate the ship to face it.

**Files:**
- Modify: [`engine/appc/ships.py`](../../../engine/appc/ships.py)
- Test: `tests/unit/test_turn_toward_location.py` (new)

- [ ] **Step 2.1: Write the failing tests**

Create `tests/unit/test_turn_toward_location.py`:

```python
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
```

- [ ] **Step 2.2: Run to verify they fail**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_turn_toward_location.py -v`

Expected: 5 FAILs, all with `AttributeError: 'ShipClass' object has no attribute 'TurnTowardLocation'`.

- [ ] **Step 2.3: Implement `TurnTowardLocation`**

In [`engine/appc/ships.py`](../../../engine/appc/ships.py), add after `TurnDirectionsToDirections` (the method exists from the prior slice; find its definition and add `TurnTowardLocation` immediately after):

```python
    def TurnTowardLocation(self, target_vec) -> None:
        """Set the angular velocity setpoint to rotate this ship to face
        a world-space point.

        Thin wrapper on TurnDirectionsToDirections: compute the unit
        direction from ship to target, read current world-forward from
        column 1 of the world rotation (column-vector convention; matches
        the integrator + SDK), call the solver with (forward, target_dir,
        zero, zero) so primary alignment runs but no secondary roll
        constraint applies. If the ship is already at the target (zero
        distance) this is a no-op so any prior setpoint is preserved
        and the solver doesn't see a NaN direction.

        Called by AI.PlainAI.Intercept.Update each tick to face the
        predicted intercept point.
        """
        loc = self.GetWorldLocation()
        diff = TGPoint3(
            target_vec.x - loc.x,
            target_vec.y - loc.y,
            target_vec.z - loc.z,
        )
        if diff.Length() < 1e-9:
            return
        diff.Unitize()
        forward = self.GetWorldRotation().GetCol(1)
        zero = TGPoint3(0.0, 0.0, 0.0)
        self.TurnDirectionsToDirections(forward, diff, zero, zero)
```

- [ ] **Step 2.4: Run to verify tests pass**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_turn_toward_location.py -v`

Expected: 5 PASS.

If `test_target_on_plus_x_yaws_around_minus_z` fails on the sign of `av.z`, this would indicate a sign issue inside `TurnDirectionsToDirections` — which is already covered by its own unit tests from the Motion slice. Re-run those:

`unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_turn_directions.py -v`

If they still pass, the failure is in your `TurnTowardLocation` glue, not the solver — check the order of args to the solver (must be `forward, target_dir`, not `target_dir, forward`).

- [ ] **Step 2.5: Run regression suite**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_turn_directions.py tests/unit/test_ship_motion.py tests/integration/test_ai_turn_to_orientation_smoke.py -q`

Expected: all green.

- [ ] **Step 2.6: Commit**

```bash
git add engine/appc/ships.py tests/unit/test_turn_toward_location.py
git commit -m "feat(ships): TurnTowardLocation thin wrapper on TurnDirectionsToDirections"
```

---

## Task 3: `InSystemWarp` + `StopInSystemWarp`

Stateless teleport-to-near-target. On call, if ship is farther from target than `distance`, translate the ship to `target_loc − unit_dir · distance`, zero `_current_speed`, return 1. Otherwise return 0 without moving. `StopInSystemWarp` is a no-op companion required only so `Intercept.LostFocus` doesn't `_Stub` through.

**Files:**
- Modify: [`engine/appc/ships.py`](../../../engine/appc/ships.py)
- Test: `tests/unit/test_in_system_warp.py` (new)

- [ ] **Step 3.1: Write the failing tests**

Create `tests/unit/test_in_system_warp.py`:

```python
"""Unit tests for ShipClass.InSystemWarp + ShipClass.StopInSystemWarp.

Stateless teleport model: each InSystemWarp call checks distance to
target and either teleports the ship to the edge of the warp radius
(returning 1) or does nothing (returning 0)."""
import pytest

import App
from engine.appc.math import TGPoint3
from engine.appc.ships import ShipClass


def test_in_system_warp_returns_zero_for_none_target():
    """Defensive: SDK callers (Intercept.Update) gate on truthy target
    but the engine must also be safe to call with None."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    assert ship.InSystemWarp(None, 100.0) == 0
    p = ship.GetTranslate()
    assert (p.x, p.y, p.z) == (0.0, 0.0, 0.0)


def test_in_system_warp_returns_zero_when_already_inside_radius():
    """Ship 50 units from target, warp distance 100 → no-op."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    target = ShipClass()
    target.SetTranslateXYZ(0.0, 50.0, 0.0)
    assert ship.InSystemWarp(target, 100.0) == 0
    p = ship.GetTranslate()
    assert (p.x, p.y, p.z) == (0.0, 0.0, 0.0)


def test_in_system_warp_returns_zero_when_exactly_at_radius():
    """distance == fDistance → no teleport. Boundary check."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    target = ShipClass()
    target.SetTranslateXYZ(0.0, 100.0, 0.0)
    assert ship.InSystemWarp(target, 100.0) == 0
    p = ship.GetTranslate()
    assert (p.x, p.y, p.z) == (0.0, 0.0, 0.0)


def test_in_system_warp_far_call_teleports_to_radius_edge():
    """Ship 1000 from target, warp distance 295 → ship ends up at
    (target - unit_dir * 295) = (0, 705, 0)."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    target = ShipClass()
    target.SetTranslateXYZ(0.0, 1000.0, 0.0)
    assert ship.InSystemWarp(target, 295.0) == 1
    p = ship.GetTranslate()
    assert p.x == pytest.approx(0.0)
    assert p.y == pytest.approx(705.0)
    assert p.z == pytest.approx(0.0)


def test_in_system_warp_far_call_works_diagonally():
    """Ship at origin, target at (300, 400, 0) → distance 500.
    With fDistance=100, unit dir = (0.6, 0.8, 0), arrival =
    target - unit * 100 = (300 - 60, 400 - 80, 0) = (240, 320, 0)."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    target = ShipClass()
    target.SetTranslateXYZ(300.0, 400.0, 0.0)
    assert ship.InSystemWarp(target, 100.0) == 1
    p = ship.GetTranslate()
    assert p.x == pytest.approx(240.0)
    assert p.y == pytest.approx(320.0)
    assert p.z == pytest.approx(0.0, abs=1e-9)


def test_in_system_warp_zeros_current_speed():
    """After teleport, _current_speed is reset so the integrator's
    brake-aware control resumes from rest on the next AI tick. Without
    this, leftover speed would advance the ship past the warp endpoint."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    ship._current_speed = 80.0
    target = ShipClass()
    target.SetTranslateXYZ(0.0, 1000.0, 0.0)
    ship.InSystemWarp(target, 295.0)
    assert ship._current_speed == 0.0


def test_in_system_warp_does_not_change_speed_when_no_teleport():
    """If the call is a no-op (ship already inside radius),
    _current_speed must be left alone — the ship is still under
    impulse control and may have a non-zero speed to preserve."""
    ship = ShipClass()
    ship.SetTranslateXYZ(0.0, 0.0, 0.0)
    ship._current_speed = 50.0
    target = ShipClass()
    target.SetTranslateXYZ(0.0, 50.0, 0.0)  # already inside radius
    ship.InSystemWarp(target, 100.0)
    assert ship._current_speed == 50.0


def test_stop_in_system_warp_is_noop_observable():
    """In the stateless model, StopInSystemWarp has no state to clear.
    Calling it must not raise and must not change ship state."""
    ship = ShipClass()
    ship.SetTranslateXYZ(7.0, 8.0, 9.0)
    ship._current_speed = 42.0
    ship.StopInSystemWarp()
    p = ship.GetTranslate()
    assert (p.x, p.y, p.z) == (7.0, 8.0, 9.0)
    assert ship._current_speed == 42.0
```

- [ ] **Step 3.2: Run to verify they fail**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_in_system_warp.py -v`

Expected: 8 FAILs, all with `AttributeError: 'ShipClass' object has no attribute 'InSystemWarp'` (and one for `StopInSystemWarp`).

- [ ] **Step 3.3: Implement `InSystemWarp` + `StopInSystemWarp`**

In [`engine/appc/ships.py`](../../../engine/appc/ships.py), add after `TurnTowardLocation` (the method you added in Task 2):

```python
    def InSystemWarp(self, target, distance) -> int:
        """Teleport-to-near-target sub-light warp.

        Stateless model: if target is None or the ship is already within
        `distance` of the target, return 0 without moving. Otherwise
        compute unit dir = (target - ship).normalize(), translate the
        ship to (target − unit_dir · distance), zero the integrator's
        current speed (so brake-aware control resumes cleanly on the
        next AI tick rather than overshooting under leftover velocity),
        and return 1.

        SDK callers (Intercept.Update) invoke this each AI tick. The
        stateless model converges: one teleport per warp request,
        subsequent ticks find distance ≤ fDistance and return 0.

        Visual streaks / camera flash / multi-frame animation will hook
        in via a later renderer-side warp pass. The kinematic teleport
        stays correct; visuals stack on top.
        """
        if target is None:
            return 0
        ship_loc = self.GetWorldLocation()
        target_loc = target.GetWorldLocation()
        diff = TGPoint3(
            target_loc.x - ship_loc.x,
            target_loc.y - ship_loc.y,
            target_loc.z - ship_loc.z,
        )
        d = diff.Length()
        if d <= distance:
            return 0
        # Unit dir ship → target, then arrival = target − unit · distance.
        diff.Scale(1.0 / d)
        self.SetTranslateXYZ(
            target_loc.x - diff.x * distance,
            target_loc.y - diff.y * distance,
            target_loc.z - diff.z * distance,
        )
        self._current_speed = 0.0
        return 1

    def StopInSystemWarp(self) -> None:
        """No-op in the stateless teleport model. Required only so
        AI.PlainAI.Intercept.LostFocus doesn't AttributeError when our
        AI driver eventually models focus loss."""
        pass
```

- [ ] **Step 3.4: Run tests; expect 8 PASS**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_in_system_warp.py -v`

Expected: 8 PASS.

- [ ] **Step 3.5: Regression sweep**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit/test_ship_motion.py tests/unit/test_turn_directions.py tests/unit/test_turn_toward_location.py tests/unit/test_loop.py tests/integration/test_ai_stay_smoke.py tests/integration/test_ai_goforward_smoke.py tests/integration/test_ai_turn_to_orientation_smoke.py -q`

Expected: all green.

- [ ] **Step 3.6: Commit**

```bash
git add engine/appc/ships.py tests/unit/test_in_system_warp.py
git commit -m "feat(ships): InSystemWarp stateless teleport + StopInSystemWarp no-op"
```

---

## Task 4: End-to-end Intercept smoke test

Drive the real SDK `AI.PlainAI.Intercept` through the GameLoop. Verify the hostile arrives at intercept range and marks itself `US_DONE`.

**Files:**
- Test: `tests/integration/test_ai_intercept_smoke.py` (new)

- [ ] **Step 4.1: Write the integration test**

Create `tests/integration/test_ai_intercept_smoke.py`:

```python
"""End-to-end smoke: Intercept AI closes on a target via in-system warp
+ brake-aware impulse, halts at fInterceptDistance, returns US_DONE.

Proves the full chain: real SDK script load (Steps 1-3 of the prior
slice), AI driver, motion integrator + TurnTowardLocation + InSystemWarp
+ GetAccelerationTG (this slice), plus the existing TurnDirections-
ToDirections + GetRelativePositionInfo helpers."""
import pytest

import App
from engine.core.loop import GameLoop, TICK_RATE
from engine.appc.ai import PlainAI_Create, ArtificialIntelligence
from engine.appc.math import TGPoint3
from engine.appc.ships import ShipClass
from engine.appc.subsystems import ImpulseEngineSubsystem


def _attach_ies(ship, *, max_speed=120.0, max_accel=50.0,
                 max_ang_vel=1.5, max_ang_accel=1.0):
    """Intercept reads MaxSpeed > 0 to enter its prediction-and-control
    block. Test ships are constructed without subsystems, so we attach
    one explicitly."""
    ies = ImpulseEngineSubsystem("Impulse Engines")
    ies.SetMaxSpeed(max_speed)
    ies.SetMaxAccel(max_accel)
    ies.SetMaxAngularVelocity(max_ang_vel)
    ies.SetMaxAngularAccel(max_ang_accel)
    ship.SetImpulseEngineSubsystem(ies)


def _setup_intercept_scene(hostile_start=(0.0, 5000.0, 0.0),
                            player_start=(0.0, 0.0, 0.0)):
    """Build a fresh set with a stationary player and a hostile that
    has PlainAI('Intercept') targeting "player"."""
    App.g_kTimerManager._time = 0.0
    App.g_kTimerManager._timers.clear()
    App.g_kRealtimeTimerManager._time = 0.0
    App.g_kRealtimeTimerManager._timers.clear()
    App.g_kSetManager._sets.clear()

    pSet = App.SetClass_Create()
    pSet.SetName("intercept_smoke")
    App.g_kSetManager._sets["intercept_smoke"] = pSet

    player = ShipClass()
    player.SetTranslateXYZ(*player_start)
    pSet.AddObjectToSet(player, "player")

    hostile = ShipClass()
    hostile.SetTranslateXYZ(*hostile_start)
    _attach_ies(hostile)
    pSet.AddObjectToSet(hostile, "hostile")

    pai = PlainAI_Create(hostile, "TestIntercept")
    pai.SetScriptModule("Intercept")
    inst = pai.GetScriptInstance()
    inst.SetTargetObjectName("player")
    hostile.SetAI(pai)

    return player, hostile, pai


def _hostile_player_distance(player, hostile):
    p = player.GetTranslate()
    h = hostile.GetTranslate()
    dx, dy, dz = h.x - p.x, h.y - p.y, h.z - p.z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def test_intercept_warp_brings_hostile_close_on_first_ai_tick():
    """After the first AI Update, the hostile must be within the warp
    radius (default fInSystemWarpDistance = 295). Starting distance is
    5000; one warp call should drop the hostile to ~295."""
    player, hostile, pai = _setup_intercept_scene()
    loop = GameLoop()
    # The AI driver fires the first PlainAI Update on the very first
    # tick (game_time >= _next_update_time == 0).
    loop.tick()
    dist = _hostile_player_distance(player, hostile)
    # Default fInSystemWarpDistance is 295; allow a small ε for FP.
    assert dist == pytest.approx(295.0, abs=1.0), (
        f"first-tick warp did not arrive at warp radius; distance={dist}"
    )


def test_intercept_eventually_reaches_intercept_distance():
    """Run until the AI returns US_DONE or we time out. Confirm the
    hostile ended up within fInterceptDistance + ship_radius of the
    player. fInterceptDistance default is 60."""
    player, hostile, pai = _setup_intercept_scene()
    loop = GameLoop()
    max_ticks = TICK_RATE * 60  # 60 simulated seconds is the ceiling
    for _ in range(max_ticks):
        loop.tick()
        if pai._status == ArtificialIntelligence.US_DONE:
            break
    assert pai._status == ArtificialIntelligence.US_DONE, (
        "Intercept never completed within 60s of simulated time"
    )
    final_dist = _hostile_player_distance(player, hostile)
    # fInterceptDistance default = 60; ship radius for a fresh ShipClass
    # is 0 (not set via SetupProperties), so the threshold collapses to
    # fInterceptDistance.
    assert final_dist <= 60.0 + 1.0, (
        f"hostile too far at completion: {final_dist}"
    )


def test_intercept_hostile_faces_player_at_completion():
    """When the hostile halts, it should be roughly facing the player.
    GetWorldForwardTG (column-vector, post-Task-1 fix) gives the world-
    forward; dot with ship→player unit vector must be > 0.9."""
    player, hostile, pai = _setup_intercept_scene()
    loop = GameLoop()
    for _ in range(TICK_RATE * 60):
        loop.tick()
        if pai._status == ArtificialIntelligence.US_DONE:
            break

    fwd = hostile.GetWorldForwardTG()
    h = hostile.GetTranslate()
    p = player.GetTranslate()
    diff = TGPoint3(p.x - h.x, p.y - h.y, p.z - h.z)
    diff.Unitize()
    dot = fwd.x * diff.x + fwd.y * diff.y + fwd.z * diff.z
    assert dot > 0.9, f"hostile not facing player at completion; dot={dot}"


def test_intercept_speed_ramps_up_then_back_toward_zero():
    """Sanity that brake-aware control engaged after the warp: the
    hostile's _current_speed must climb above zero at some point and
    then return near zero by the time the AI completes."""
    player, hostile, pai = _setup_intercept_scene()
    loop = GameLoop()
    peak_speed = 0.0
    for _ in range(TICK_RATE * 60):
        loop.tick()
        peak_speed = max(peak_speed, hostile._current_speed)
        if pai._status == ArtificialIntelligence.US_DONE:
            break
    assert peak_speed > 10.0, (
        f"hostile never accelerated meaningfully; peak={peak_speed}"
    )
    # On completion the brake-aware code should have driven speed
    # toward 0 (within the same tick when fSpeed = 0 is set, since
    # FALLBACK_MAX_ACCEL snaps).
    assert hostile._current_speed < peak_speed, (
        "hostile did not decelerate before completion"
    )


def test_intercept_returns_us_active_while_still_approaching():
    """While the hostile is closing but not yet within fInterceptDistance,
    the AI must report US_ACTIVE. Sample at an intermediate point."""
    player, hostile, pai = _setup_intercept_scene()
    loop = GameLoop()
    # Run a few AI cycles' worth of ticks; the AI fires every ~0.4s, so
    # 60 ticks = 1s = 2-3 AI updates after the initial warp.
    for _ in range(60):
        loop.tick()
    # If we already completed (very unlikely at 1s under brake-aware
    # control with 295 units to cover), this assertion is vacuously
    # interesting — skip in that case.
    dist = _hostile_player_distance(player, hostile)
    if dist > 60.0:
        assert pai._status == ArtificialIntelligence.US_ACTIVE, (
            f"AI reported {pai._status} while still {dist} units out"
        )
```

- [ ] **Step 4.2: Run the test**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/integration/test_ai_intercept_smoke.py -v`

Expected: 5 PASS.

Common failure modes + diagnostics:
- **`test_intercept_warp_brings_hostile_close_on_first_ai_tick` fails** with `dist ≈ 5000`: warp didn't fire. Most likely cause: `Intercept.Update` short-circuits on `fMaxSpeed > 0` (line ~98 of the SDK file) — verify `_attach_ies` populated the IES with `MaxSpeed=120`. Second possible cause: the AI's first Update never fired in this tick. Add a temporary `print(pai.GetScriptInstance()._first_update_called)` (or similar) — but the AI driver from the previous slice fires on tick 1, confirmed by the Stay smoke.
- **`test_intercept_eventually_reaches_intercept_distance` fails** with `pai._status != US_DONE`: brake-aware control never settled. Check the final `hostile._current_speed` — if it's oscillating around a non-zero value, the AI is repeatedly setting `fMaxVel` and the integrator's `FALLBACK_MAX_ACCEL` snap keeps overshooting. Reducing the IES `MaxSpeed` in `_attach_ies` to e.g. 60.0 should help (less momentum to dump).
- **`test_intercept_hostile_faces_player_at_completion` fails** with `dot < 0.9`: turning is too slow. The IES's `MaxAngularVelocity = 1.5` rad/s with a 60-tick run (1 second of simulated time post-warp) gives ~1.5 rad of turn — enough to face from any orientation. If it's not enough, raise `MaxAngularVelocity` in `_attach_ies` to e.g. 3.0 and re-test; the limit isn't load-bearing for the smoke.

- [ ] **Step 4.3: Regression sweep**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit tests/integration -q -k "ai_ or ship_motion or turn_ or in_system or physics_object or test_loop"`

Expected: green.

- [ ] **Step 4.4: Commit**

```bash
git add tests/integration/test_ai_intercept_smoke.py
git commit -m "test(ai): end-to-end smoke for PlainAI('Intercept') with in-system warp"
```

---

## Task 5: Visible mission fixture + deferred-doc update

Mirror the AIMotion mission pattern: a player ship at origin and a hostile far away with `PlainAI("Intercept")` targeting the player. User runs `./build/dauntless`, picks `AIIntercept`, watches the hostile pop in and brake to a halt.

**Files:**
- Create: `sdk/Build/scripts/Custom/Tutorial/Episode/AIIntercept/AIIntercept.py` (gitignored — lives in the SDK tree)
- Create: `sdk/Build/scripts/Custom/Tutorial/Episode/AIIntercept/__init__.py` (gitignored)
- Modify: [`docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md`](../deferred/2026-05-18-ship-ai-runtime.md)

`sdk/` is a gitignored copyrighted directory. The SDK files added by this task ride along but are not tracked. The deferred-doc edit IS tracked and is the single commit for this task.

- [ ] **Step 5.1: Confirm mission discovery picks up Tutorial leaf dirs**

Run: `unset VIRTUAL_ENV && uv run --extra dev python -c "from engine.missions.discovery import discover; r = discover('sdk/Build/scripts'); print(sorted({m.dir_name for f in r.families for ep in f.episodes for m in ep.missions}))"`

Expected: list including `AIMotion`, `M1Basic`, `M2Objects`, `M3Gameflow`, `M4Complex`. Discovery flags any leaf dir containing a `.py` with a top-level `def Initialize(`.

- [ ] **Step 5.2: Create the empty package marker**

Create the file at the absolute path so it doesn't matter whether sdk/ is a symlink or a real directory in your worktree:

```bash
mkdir -p /Users/mward/Documents/Projects/bc_dauntless/sdk/Build/scripts/Custom/Tutorial/Episode/AIIntercept
touch /Users/mward/Documents/Projects/bc_dauntless/sdk/Build/scripts/Custom/Tutorial/Episode/AIIntercept/__init__.py
```

- [ ] **Step 5.3: Create the mission script**

Write `/Users/mward/Documents/Projects/bc_dauntless/sdk/Build/scripts/Custom/Tutorial/Episode/AIIntercept/AIIntercept.py`:

```python
###############################################################################
#  AIIntercept.py
#
#  Visible smoke for the Ship AI Intercept slice. Spawns the player at
#  origin and one hostile +5000 units along ship-forward, then attaches
#  PlainAI("Intercept") targeting "player". The hostile in-system-warps
#  to ~295 units, then drifts in under brake-aware impulse and halts at
#  ~60 units. Run with ./build/dauntless and pick AIIntercept from the
#  mission menu.
#
#  Note: the in-system warp is currently a stateless teleport (no
#  visual streaks / camera flash yet). Renderer-side warp visuals land
#  in a later slice.
###############################################################################
import App
import loadspacehelper
import MissionLib


def PreLoadAssets(pMission):
    loadspacehelper.PreloadShip("Galaxy", 2)


def Initialize(pMission):
    import LoadBridge
    LoadBridge.Load("GalaxyBridge")

    import Systems.Biranu.Biranu
    Systems.Biranu.Biranu.CreateMenus()
    MissionLib.SetupSpaceSet("Systems.Biranu.Biranu1")

    pSet = App.g_kSetManager.GetSet("Biranu1")
    if pSet is None:
        return

    # Player ship — same defensive fleet/mission glue as AIMotion.
    pPlayer = loadspacehelper.CreateShip("Enterprise", pSet, "Galaxy")
    if pPlayer is not None:
        pPlayer.SetTranslateXYZ(0.0, 0.0, 0.0)
        try:
            App.g_kFleetManager.AddShipToFleet(pPlayer, "Federation")
        except Exception:
            pass
        try:
            pMission.SetPlayerShip(pPlayer)
        except Exception:
            pass

    # Hostile at +5000 along the player's model-forward (+Y). Default
    # Intercept parameters keep fMaximumSpeed = 1.0e20 so the warp
    # branch fires on the first AI Update.
    pHostile = loadspacehelper.CreateShip("Hostile", pSet, "Galaxy")
    if pHostile is not None:
        pHostile.SetTranslateXYZ(0.0, 5000.0, 0.0)
        pAI = App.PlainAI_Create(pHostile, "InterceptSmoke")
        pAI.SetScriptModule("Intercept")
        pAI.GetScriptInstance().SetTargetObjectName("player")
        pHostile.SetAI(pAI)
```

- [ ] **Step 5.4: Confirm discovery includes AIIntercept**

Run: `unset VIRTUAL_ENV && uv run --extra dev python -c "from engine.missions.discovery import discover; r = discover('sdk/Build/scripts'); print(sorted({m.dir_name for f in r.families for ep in f.episodes for m in ep.missions}))"`

Expected: list now includes `'AIIntercept'`.

- [ ] **Step 5.5: SKIP renderer launch step**

The visible test (`./build/dauntless` → pick AIIntercept → watch hostile arrive) is for the human reviewer to run after merge. Do not attempt to launch the renderer; it requires a display.

- [ ] **Step 5.6: Update the deferred AI-runtime doc**

In [`docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md`](../deferred/2026-05-18-ship-ai-runtime.md), update Step 4 and Step 5.

Find the Step 4 motion-API section. Update the relevant bullets:

```markdown
### Step 4 — Ship motion APIs on `ShipClass`

Bind to PyBullet rigid bodies (Phase 1 harness) and the C++ engine later:

- `TurnTowardLocation(vec)` — ✅ done in [Ship AI Intercept plan](../plans/2026-05-18-ship-ai-intercept.md). Thin wrapper on `TurnDirectionsToDirections`.
- `SetTargetAngularVelocityDirect(vec)` — ✅ done in Steps 1-3 plan; defensive copy in [Ship AI Motion plan](../plans/2026-05-18-ship-ai-motion.md).
- `SetSpeed(speed, direction, frame)` — ✅ done; defensive copy added in motion slice. `SetImpulse` alias added.
- `GetPredictedPosition(p, v, a, t)` — ✅ done in motion slice.
- `GetRelativePositionInfo(vec)` — ✅ done in motion slice; row→col convention fix in commit `68f6220`.
- `InSystemWarp(target, distance)` — ✅ done in [Ship AI Intercept plan](../plans/2026-05-18-ship-ai-intercept.md). Stateless teleport-to-near-target. Renderer-side visuals (streaks, camera flash) are a separate follow-up.
- `StopInSystemWarp()` — ✅ done; no-op in the stateless model.
- `GetImpulseEngineSubsystem().GetMaxSpeed()` / `GetMaxAccel()` — ✅ exist on the subsystem; motion integrator + TurnDirectionsToDirections solver use them.
```

Find the Step 5 smoke-trail section. Update item 4:

```markdown
4. **`PlainAI.Intercept`** ([`Intercept.py`](../../../sdk/Build/scripts/AI/PlainAI/Intercept.py)) — ✅ done in [Ship AI Intercept plan](../plans/2026-05-18-ship-ai-intercept.md). Closes the gap on the canonical "turn + thrust + warp + prediction" hard-case. Obstacle avoidance still no-op (ProximityManager stub). `bMoveInFront=1` branch correct but untested end-to-end; first NonFedAttack test will cover it.
```

If Step 5 also has follow-up bullets for items 5/6 (FollowObject/BasicAttack), leave them as-is.

Add a new "Follow-up work" sub-section after Step 5 if one doesn't exist, capturing the two deferrals:

```markdown
### Follow-up after Intercept

- **Renderer warp visuals.** `InSystemWarp` currently teleports kinematically with no visual treatment. When the chase-camera / particle / motion-blur subsystems land, hook them in via a renderer-side pass; the engine-side teleport stays correct.
- **Obstacle avoidance.** `Intercept.AdjustDestinationForLargeObstacles` runs but is a no-op because `ProximityManager.GetLineIntersectObjects` returns `()`. Real avoidance lands when the proximity subsystem itself gets real work (planet avoidance, large-ship avoidance).
```

- [ ] **Step 5.7: Run the full relevant suite a final time**

Run: `unset VIRTUAL_ENV && uv run --extra dev pytest tests/unit tests/integration -q -k "ai_ or ship_motion or turn_ or in_system or physics_object or test_loop"`

Expected: green. (Don't expand the test scope further — the broader native-binding-dependent tests are pre-existing failures unrelated to this slice.)

- [ ] **Step 5.8: Commit the deferred-doc edit**

The mission files in the gitignored SDK tree don't get committed (by design — copyrighted content). Commit only the deferred-doc edit:

```bash
git add docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md
git commit -m "docs(deferred): close Intercept items completed in Ship AI Intercept slice"
```

---

## Out of scope (deferred to follow-up slices)

- Renderer-side warp visuals (camera flash, streak particles, motion blur on warp transitions).
- Obstacle avoidance — proximity manager `GetLineIntersectObjects` + line-sphere geometry helper + planet/large-ship avoidance. `Intercept.AdjustDestinationForLargeObstacles` currently runs as a no-op.
- End-to-end test of `bMoveInFront=1` (the fly-by-attack branch). Path is correct after the `GetWorldForwardTG` fix; first NonFedAttack consumer will pin it.
- `FollowObject` / `CircleObject` — sit on top of Intercept's motion API.
- `Compound.BasicAttack` — combat slice; combines Intercept + weapon firing preprocessors + ConditionScript evaluation.

These remain in [docs/superpowers/deferred/2026-05-18-ship-ai-runtime.md](../deferred/2026-05-18-ship-ai-runtime.md) and pick up where this plan leaves off.
