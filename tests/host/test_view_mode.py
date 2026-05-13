"""Unit tests for _ViewModeController — space-bar toggled bridge/exterior
view modality. Mirrors the fake-bindings pattern from
tests/host/test_camera_control.py."""
import pytest


class _FakeKeys:
    KEY_SPACE = 200


class _FakeKeyReader:
    keys = _FakeKeys()

    def __init__(self):
        self.held = set()
        self.pressed_once = set()

    def key_state(self, key):
        return key in self.held

    def key_pressed(self, key):
        if key in self.pressed_once:
            self.pressed_once.discard(key)
            return True
        return False


def test_view_mode_starts_exterior():
    from engine.host_loop import _ViewModeController
    vm = _ViewModeController()
    assert vm.is_exterior is True
    assert vm.is_bridge is False


def test_view_mode_toggle_on_space_pressed():
    from engine.host_loop import _ViewModeController
    vm = _ViewModeController()
    reader = _FakeKeyReader()

    # No space → no change.
    vm.apply(reader)
    assert vm.is_exterior is True

    # Space pressed once → bridge.
    reader.pressed_once.add(reader.keys.KEY_SPACE)
    vm.apply(reader)
    assert vm.is_bridge is True

    # No space → still bridge (edge-triggered, not held).
    vm.apply(reader)
    assert vm.is_bridge is True

    # Space pressed again → back to exterior.
    reader.pressed_once.add(reader.keys.KEY_SPACE)
    vm.apply(reader)
    assert vm.is_exterior is True


class _RecordingInputs:
    """Stand-ins for _PlayerControl / _CameraControl that record whether
    apply() was called and what reader it was handed, without doing any
    work."""
    class _Player:
        def __init__(self): self.calls = []
        def apply(self, player, dt, h): self.calls.append(h)
    class _Camera:
        def __init__(self): self.calls = 0
        def apply(self, dt, h, scroll_y): self.calls += 1

    def __init__(self):
        self.player = self._Player()
        self.camera = self._Camera()


def test_apply_input_calls_both_in_exterior_mode():
    from engine.host_loop import _ViewModeController, _apply_input
    vm = _ViewModeController()  # exterior
    inputs = _RecordingInputs()
    reader = _FakeKeyReader()
    _apply_input(vm, inputs.player, inputs.camera,
                 player=object(), dt=1.0/60, h=reader, scroll_y=0.0)
    assert len(inputs.player.calls) == 1
    assert inputs.player.calls[0] is reader  # exterior forwards live keys
    assert inputs.camera.calls == 1


def test_apply_input_in_bridge_keeps_player_integrating_with_no_input():
    """Bridge mode calls player_control.apply with a no-input reader so
    ship physics keep integrating (engines coast) while live keys are
    ignored. The orbit camera is not stepped at all."""
    from engine.host_loop import _ViewModeController, _apply_input, _NO_INPUT
    vm = _ViewModeController()
    vm.toggle()  # bridge
    inputs = _RecordingInputs()
    reader = _FakeKeyReader()
    reader.held.add(reader.keys.KEY_SPACE)  # held key must not reach player
    _apply_input(vm, inputs.player, inputs.camera,
                 player=object(), dt=1.0/60, h=reader, scroll_y=0.0)
    assert len(inputs.player.calls) == 1
    assert inputs.player.calls[0] is _NO_INPUT
    assert inputs.camera.calls == 0


def test_apply_input_preserves_orbit_state_across_bridge_toggle():
    """Spec test 5: entering bridge mode must not mutate _CameraControl
    orbit state, so toggling back restores the same exterior framing."""
    from engine.host_loop import _ViewModeController, _CameraControl, _apply_input
    cc = _CameraControl()
    cc.orbit_yaw_rad = 1.234
    cc.orbit_pitch_rad = -0.5
    cc.distance = 4242.0
    saved = (cc.orbit_yaw_rad, cc.orbit_pitch_rad, cc.distance)

    vm = _ViewModeController()
    vm.toggle()  # bridge
    reader = _FakeKeyReader()

    # Drive a "tick" with a non-zero scroll delta. In exterior mode that
    # would shrink cc.distance via cc.apply(); in bridge mode _apply_input
    # must not call cc.apply() at all, so the orbit state stays frozen.
    class _NoopPlayer:
        def apply(self, *a, **k): pass
    _apply_input(vm, _NoopPlayer(), cc, player=object(),
                 dt=1.0/60, h=reader, scroll_y=99.0)
    assert (cc.orbit_yaw_rad, cc.orbit_pitch_rad, cc.distance) == saved


def test_apply_input_in_bridge_keeps_ship_moving_under_real_player_control():
    """Regression: pressing space while engines are engaged must NOT
    freeze the ship — it should keep coasting forward at its current
    speed. Drives the real _PlayerControl against a fake ship to prove
    that the integration step still runs in bridge mode."""
    from engine.host_loop import _ViewModeController, _PlayerControl, _apply_input
    from engine.appc.math import TGPoint3, TGMatrix3

    class _FakeShip:
        def __init__(self):
            self._loc = TGPoint3(0.0, 0.0, 0.0)
            self._rot = TGMatrix3()
        def GetWorldRotation(self): return self._rot
        def GetTranslate(self):     return self._loc
        def SetMatrixRotation(self, R): self._rot = R
        def SetTranslateXYZ(self, x, y, z):
            self._loc = TGPoint3(x, y, z)
        # No ImpulseEngineSubsystem → _PlayerControl falls back to legacy
        # IMPULSE_UNIT * level for target speed.
        GetImpulseEngineSubsystem = None

    pc = _PlayerControl()
    pc.impulse_level = 5
    pc._current_speed = 5 * _PlayerControl.IMPULSE_UNIT  # already at target
    ship = _FakeShip()

    vm = _ViewModeController()
    vm.toggle()  # bridge

    class _NoopCam:
        def apply(self, *a, **k): pass

    reader = _FakeKeyReader()
    # Tick a few times in bridge mode. The ship must move forward.
    for _ in range(10):
        _apply_input(vm, pc, _NoopCam(),
                     player=ship, dt=1.0/60, h=reader, scroll_y=0.0)

    # Ship-Y is forward in body frame. Identity rotation → world +Y.
    # 10 ticks × (1/60 s) × 250 units/s ≈ 41.67 units along Y.
    assert ship._loc.y > 40.0
    # Throttle setting is preserved across bridge toggle.
    assert pc.impulse_level == 5


class _RecordingRenderer:
    """Stand-in for the _open_stbc_host bindings module. Records calls
    to bridge-pass-related functions so toggle wiring can be asserted
    without booting the real renderer."""
    def __init__(self):
        self.bridge_pass_calls = []   # list of bool
        self.cursor_lock_calls = []   # list of bool

    def bridge_pass_set_enabled(self, enabled):
        self.bridge_pass_calls.append(enabled)

    def set_cursor_locked(self, locked):
        self.cursor_lock_calls.append(locked)


def test_toggle_to_bridge_enables_pass_and_locks_cursor():
    """Toggling exterior → bridge fires bridge_pass_set_enabled(True)
    and set_cursor_locked(True) exactly once each."""
    from engine.host_loop import _ViewModeController, _apply_view_mode_side_effects
    vm = _ViewModeController()  # exterior
    rr = _RecordingRenderer()
    vm.toggle()  # exterior → bridge
    _apply_view_mode_side_effects(vm, rr)
    assert rr.bridge_pass_calls == [True]
    assert rr.cursor_lock_calls == [True]


def test_toggle_to_exterior_disables_pass_and_releases_cursor():
    from engine.host_loop import _ViewModeController, _apply_view_mode_side_effects
    vm = _ViewModeController()
    vm.toggle()  # bridge
    rr = _RecordingRenderer()
    _apply_view_mode_side_effects(vm, rr)  # one true call
    vm.toggle()  # back to exterior
    _apply_view_mode_side_effects(vm, rr)
    assert rr.bridge_pass_calls == [True, False]
    assert rr.cursor_lock_calls == [True, False]


def test_apply_view_mode_side_effects_idempotent_within_a_mode():
    """Calling _apply_view_mode_side_effects twice without toggling
    must not re-fire the renderer calls — bridge_pass_set_enabled is a
    cheap setter but cursor lock has visible side-effects we don't want
    to spam."""
    from engine.host_loop import _ViewModeController, _apply_view_mode_side_effects
    vm = _ViewModeController()
    rr = _RecordingRenderer()
    _apply_view_mode_side_effects(vm, rr)
    _apply_view_mode_side_effects(vm, rr)  # no toggle in between
    # Both lists should have at most 1 entry (the initial-sync call).
    assert len(rr.bridge_pass_calls) <= 1
    assert len(rr.cursor_lock_calls) <= 1


def test_esc_in_bridge_mode_returns_to_exterior():
    """ESC handler: when in bridge mode, ESC toggles back to exterior
    and the side-effect sync releases the cursor + disables the pass."""
    from engine.host_loop import (_ViewModeController,
                                  _handle_esc_for_view_mode,
                                  _apply_view_mode_side_effects)
    vm = _ViewModeController()
    vm.toggle()  # bridge
    rr = _RecordingRenderer()
    _apply_view_mode_side_effects(vm, rr)  # initial sync to bridge
    _handle_esc_for_view_mode(vm)
    _apply_view_mode_side_effects(vm, rr)  # next-tick sync after esc
    assert vm.is_exterior is True
    assert rr.bridge_pass_calls == [True, False]
    assert rr.cursor_lock_calls == [True, False]


def test_esc_in_exterior_mode_is_a_noop():
    from engine.host_loop import _ViewModeController, _handle_esc_for_view_mode
    vm = _ViewModeController()  # exterior
    _handle_esc_for_view_mode(vm)
    assert vm.is_exterior is True


def test_bridge_camera_anchors_at_ship_origin_looking_forward():
    """Spec test 4: bridge camera eye = ship loc, target along ship
    forward (row 1), up along ship up (row 2)."""
    from engine.host_loop import _ViewModeController, _compute_camera
    from engine.appc.math import TGPoint3, TGMatrix3

    class _FakePlayer:
        def __init__(self, loc, rot):
            self._loc, self._rot = loc, rot
        def GetWorldLocation(self): return self._loc
        def GetWorldRotation(self): return self._rot

    loc = TGPoint3(100.0, 200.0, 300.0)
    rot = TGMatrix3()  # identity — forward = (0,1,0), up = (0,0,1)
    player = _FakePlayer(loc, rot)

    vm = _ViewModeController()
    vm.toggle()  # bridge

    eye, target, up_vec = _compute_camera(
        vm, cam_control=None, player=player, dt=1.0/60)

    assert eye    == (100.0, 200.0, 300.0)
    assert target == (100.0, 201.0, 300.0)  # +1 along world-Y (= ship forward)
    assert up_vec == (0.0,   0.0,   1.0)


def test_exterior_camera_delegates_to_cam_control():
    """Sanity check: exterior mode still routes through _CameraControl."""
    from engine.host_loop import _ViewModeController, _compute_camera
    from engine.appc.math import TGPoint3, TGMatrix3

    class _FakePlayer:
        def GetWorldLocation(self): return TGPoint3(0.0, 0.0, 0.0)
        def GetWorldRotation(self): return TGMatrix3()

    class _RecordingCam:
        def __init__(self): self.calls = []
        def compute_camera(self, loc, rot, dt):
            self.calls.append((loc, rot, dt))
            return ((1, 2, 3), (4, 5, 6), (0, 0, 1))

    cam = _RecordingCam()
    eye, target, up_vec = _compute_camera(
        _ViewModeController(), cam_control=cam,
        player=_FakePlayer(), dt=1.0/60)
    assert len(cam.calls) == 1
    assert (eye, target, up_vec) == ((1, 2, 3), (4, 5, 6), (0, 0, 1))


def test_exterior_camera_lock_bias_zero_aims_at_target():
    """target_lock_bias=0.0 puts the look-at directly on the target,
    centring it in the frame (the previous behaviour)."""
    from engine.host_loop import _ViewModeController, _compute_camera
    from engine.appc.math import TGPoint3, TGMatrix3

    class _Target:
        def GetWorldLocation(self): return TGPoint3(50.0, 60.0, 70.0)

    class _FakePlayer:
        def __init__(self, target): self._target = target
        def GetWorldLocation(self): return TGPoint3(0.0, 0.0, 0.0)
        def GetWorldRotation(self): return TGMatrix3()
        def GetTarget(self): return self._target

    class _StubCam:
        target_lock_enabled = True
        target_lock_bias    = 0.0
        def compute_camera(self, loc, rot, dt):
            return ((1, 2, 3), (4, 5, 6), (0, 0, 1))

    tgt = _Target()
    eye, target, up_vec = _compute_camera(
        _ViewModeController(), cam_control=_StubCam(),
        player=_FakePlayer(tgt), dt=1.0/60)
    assert eye == (1, 2, 3)
    assert target == (50.0, 60.0, 70.0)
    assert up_vec == (0, 0, 1)


def test_exterior_camera_lock_shifts_look_at_down_along_image_up():
    """Non-zero bias shifts the look-at along -up by bias × eye→target
    distance, so the target projects above image centre."""
    import math
    from engine.host_loop import _ViewModeController, _compute_camera
    from engine.appc.math import TGPoint3, TGMatrix3

    class _Target:
        def GetWorldLocation(self): return TGPoint3(0.0, 1000.0, 0.0)

    class _FakePlayer:
        def GetWorldLocation(self): return TGPoint3(0.0, 0.0, 0.0)
        def GetWorldRotation(self): return TGMatrix3()
        def GetTarget(self): return _Target()

    class _StubCam:
        target_lock_enabled = True
        target_lock_bias    = 0.15
        def compute_camera(self, loc, rot, dt):
            return ((0.0, -150.0, 50.0), (0.0, 0.0, 20.0), (0.0, 0.0, 1.0))

    _, target, _ = _compute_camera(
        _ViewModeController(), cam_control=_StubCam(),
        player=_FakePlayer(), dt=1.0/60)
    # eye→target = (0, 1150, -50), distance ≈ 1151.1.
    dist = math.sqrt(1150.0**2 + 50.0**2)
    expected_z = 0.0 - 0.15 * dist * 1.0
    assert target[0] == 0.0
    assert target[1] == 1000.0
    assert target[2] == pytest.approx(expected_z, rel=1e-6)


def test_exterior_camera_lock_disabled_keeps_chase_target():
    """When cam_control.target_lock_enabled is False, the chase look-at
    point is preserved even if the player has a target."""
    from engine.host_loop import _ViewModeController, _compute_camera
    from engine.appc.math import TGPoint3, TGMatrix3

    class _Target:
        def GetWorldLocation(self): return TGPoint3(50.0, 60.0, 70.0)

    class _FakePlayer:
        def GetWorldLocation(self): return TGPoint3(0.0, 0.0, 0.0)
        def GetWorldRotation(self): return TGMatrix3()
        def GetTarget(self): return _Target()

    class _StubCam:
        target_lock_enabled = False
        def compute_camera(self, loc, rot, dt):
            return ((1, 2, 3), (4, 5, 6), (0, 0, 1))

    eye, target, up_vec = _compute_camera(
        _ViewModeController(), cam_control=_StubCam(),
        player=_FakePlayer(), dt=1.0/60)
    assert (eye, target, up_vec) == ((1, 2, 3), (4, 5, 6), (0, 0, 1))


def test_exterior_camera_unchanged_when_no_target():
    """GetTarget() returning None should leave the chase cam output alone."""
    from engine.host_loop import _ViewModeController, _compute_camera
    from engine.appc.math import TGPoint3, TGMatrix3

    class _FakePlayer:
        def GetWorldLocation(self): return TGPoint3(0.0, 0.0, 0.0)
        def GetWorldRotation(self): return TGMatrix3()
        def GetTarget(self): return None

    class _StubCam:
        def compute_camera(self, loc, rot, dt):
            return ((1, 2, 3), (4, 5, 6), (0, 0, 1))

    eye, target, up_vec = _compute_camera(
        _ViewModeController(), cam_control=_StubCam(),
        player=_FakePlayer(), dt=1.0/60)
    assert (eye, target, up_vec) == ((1, 2, 3), (4, 5, 6), (0, 0, 1))
