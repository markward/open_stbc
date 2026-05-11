"""Unit tests for _ViewModeController — space-bar toggled bridge/exterior
view modality. Mirrors the fake-bindings pattern from
tests/host/test_camera_control.py."""


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
    apply() was called, without doing any work."""
    class _Player:
        def __init__(self): self.calls = 0
        def apply(self, player, dt, h): self.calls += 1
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
    assert inputs.player.calls == 1
    assert inputs.camera.calls == 1


def test_apply_input_skips_both_in_bridge_mode():
    from engine.host_loop import _ViewModeController, _apply_input
    vm = _ViewModeController()
    vm.toggle()  # bridge
    inputs = _RecordingInputs()
    reader = _FakeKeyReader()
    _apply_input(vm, inputs.player, inputs.camera,
                 player=object(), dt=1.0/60, h=reader, scroll_y=0.0)
    assert inputs.player.calls == 0
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
