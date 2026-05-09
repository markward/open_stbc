# Ship Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add BC-stock movement keybindings (Q/W/E/A/S/D + 0–9 + R) to the renderer host so the player can fly the Galaxy around the M1 Basic scene, plus a third-person camera follow that tracks the ship's orientation.

**Architecture:** `renderer::Window` gains a `key_state(int) -> bool` accessor wrapping `glfwGetKey`. The `_open_stbc_host` pybind11 module exposes that plus a `key_pressed(int) -> bool` rising-edge variant and a `keys` sub-namespace carrying GLFW key-code constants. `engine/host_loop.py` gains a `_PlayerControl` class that reads keys per tick and integrates the ship's transform directly (no Phase 1 physics, since `engine/physics/simulation.py` is empty). Camera-follow updates to use ship-local axes so banking is visible.

**Tech Stack:** C++20, GLFW (already linked), pybind11 (already linked), `engine.appc.math.TGMatrix3` / `TGPoint3` (already in repo).

**Reference:** Spec at `docs/superpowers/specs/2026-05-09-ship-controls-design.md`. Read it once before starting; reference its "Components" / "Constants" sections per task.

**Not in this plan:** weapons, targeting, view modes, HUD, mouse input, BC config-file keybindings, accel/decel curves, auto-damping. All deferred per the spec.

---

## Task 1: Window::key_state

**Files:**
- Modify: `native/src/renderer/include/renderer/window.h`
- Modify: `native/src/renderer/window.cc`
- Modify: `native/tests/renderer/window_test.cc`

**Goal:** `Window` exposes one new method `bool key_state(int glfw_key) const noexcept` that returns the most recent polled state of a GLFW key.

- [ ] **Step 1: Write the failing test**

Append to `native/tests/renderer/window_test.cc` (after the existing `Window.MoveAssignDoesNotLeak` test, before the closing `}  // namespace`):

```cpp
TEST(Window, KeyStateReturnsFalseForUnpressedKeys) {
    try {
        renderer::Window w(64, 64, "key-state-test", /*visible=*/false);
        // Hidden offscreen windows never gain focus, so glfwGetKey reports
        // RELEASE for everything. The test verifies the wiring compiles +
        // links and returns the documented sentinel; real hardware events
        // can't be simulated in a test without a window manager.
        EXPECT_FALSE(w.key_state(GLFW_KEY_W));
        EXPECT_FALSE(w.key_state(GLFW_KEY_SPACE));
        EXPECT_FALSE(w.key_state(GLFW_KEY_0));
    } catch (const std::runtime_error& e) {
        GTEST_SKIP() << "no GL context available: " << e.what();
    }
}
```

- [ ] **Step 2: Run test, verify it fails (no method)**

```bash
cd /Users/mward/Documents/Projects/open_stbc
cmake --build build --target renderer_tests 2>&1 | tail -8
```
Expected: compile error — `'class renderer::Window' has no member named 'key_state'`.

- [ ] **Step 3: Add the declaration to the header**

Modify `native/src/renderer/include/renderer/window.h`. After the existing `void framebuffer_size(int* w, int* h) const noexcept;` line, insert:

```cpp
    /// Cached state of a GLFW keyboard key. Returns true while the key is
    /// held. State is updated by glfwPollEvents() (called by poll_events()).
    bool key_state(int glfw_key) const noexcept;
```

- [ ] **Step 4: Implement the method**

Modify `native/src/renderer/window.cc`. After the existing `framebuffer_size` implementation (the function ends with `else { *w = 0; *h = 0; }`), insert:

```cpp
bool Window::key_state(int glfw_key) const noexcept {
    if (!handle_) return false;
    return glfwGetKey(handle_, glfw_key) == GLFW_PRESS;
}
```

- [ ] **Step 5: Run test, verify it passes**

```bash
cmake --build build --target renderer_tests
ctest --test-dir build -R "Window\.KeyState" --output-on-failure
```
Expected: 1 PASS.

- [ ] **Step 6: Run full ctest suite to confirm no regressions**

```bash
ctest --test-dir build --output-on-failure 2>&1 | tail -3
```
Expected: 119 tests pass (118 existing + 1 new), 0 fail.

- [ ] **Step 7: Commit**

```bash
git add native/src/renderer/include/renderer/window.h \
        native/src/renderer/window.cc \
        native/tests/renderer/window_test.cc
git commit -m "feat(renderer): Window::key_state wraps glfwGetKey"
```

---

## Task 2: Bindings — `keys` constants

**Files:**
- Modify: `native/src/host/host_bindings.cc`
- Create: `tests/host/test_input_bindings.py`

**Goal:** Expose GLFW key-code constants as `_open_stbc_host.keys.KEY_W` etc. via a pybind11 submodule. No `key_state` / `key_pressed` yet — those land in Task 3.

- [ ] **Step 1: Write the failing test**

Create `tests/host/test_input_bindings.py`:

```python
"""Verify _open_stbc_host exposes input-related bindings."""


def test_keys_submodule_exists():
    import _open_stbc_host
    assert hasattr(_open_stbc_host, "keys")


def test_key_constants_exist_and_are_distinct():
    import _open_stbc_host
    k = _open_stbc_host.keys
    names = ["KEY_W", "KEY_S", "KEY_A", "KEY_D", "KEY_Q", "KEY_E", "KEY_R",
             "KEY_0", "KEY_1", "KEY_2", "KEY_3", "KEY_4",
             "KEY_5", "KEY_6", "KEY_7", "KEY_8", "KEY_9"]
    values = []
    for name in names:
        v = getattr(k, name)
        assert isinstance(v, int), f"{name} not an int: {type(v)}"
        values.append(v)
    assert len(set(values)) == len(values), "key constants are not distinct"
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cmake --build build --target _open_stbc_host -j 2>&1 | tail -3
uv run pytest tests/host/test_input_bindings.py -v 2>&1 | tail -10
```
Expected: FAIL — `AssertionError: ... has no attribute 'keys'`.

- [ ] **Step 3: Add the keys submodule to PYBIND11_MODULE**

Modify `native/src/host/host_bindings.cc`. Add an include at the top (alongside the existing `<glad/glad.h>`):

```cpp
#include <GLFW/glfw3.h>
```

Then, in the `PYBIND11_MODULE(_open_stbc_host, m) { ... }` body, after the existing `m.def("set_skybox", ...)` line and before the existing `m.def("read_pixel", ...)` line, insert:

```cpp
    auto keys = m.def_submodule("keys", "GLFW key-code constants for input bindings.");
    keys.attr("KEY_W") = GLFW_KEY_W;
    keys.attr("KEY_S") = GLFW_KEY_S;
    keys.attr("KEY_A") = GLFW_KEY_A;
    keys.attr("KEY_D") = GLFW_KEY_D;
    keys.attr("KEY_Q") = GLFW_KEY_Q;
    keys.attr("KEY_E") = GLFW_KEY_E;
    keys.attr("KEY_R") = GLFW_KEY_R;
    keys.attr("KEY_0") = GLFW_KEY_0;
    keys.attr("KEY_1") = GLFW_KEY_1;
    keys.attr("KEY_2") = GLFW_KEY_2;
    keys.attr("KEY_3") = GLFW_KEY_3;
    keys.attr("KEY_4") = GLFW_KEY_4;
    keys.attr("KEY_5") = GLFW_KEY_5;
    keys.attr("KEY_6") = GLFW_KEY_6;
    keys.attr("KEY_7") = GLFW_KEY_7;
    keys.attr("KEY_8") = GLFW_KEY_8;
    keys.attr("KEY_9") = GLFW_KEY_9;
```

- [ ] **Step 4: Run test, verify it passes**

```bash
cmake --build build --target _open_stbc_host -j
uv run pytest tests/host/test_input_bindings.py -v 2>&1 | tail -10
```
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add native/src/host/host_bindings.cc tests/host/test_input_bindings.py
git commit -m "feat(host): expose GLFW key-code constants as _open_stbc_host.keys"
```

---

## Task 3: Bindings — `key_state` and `key_pressed`

**Files:**
- Modify: `native/src/host/host_bindings.cc`
- Modify: `tests/host/test_input_bindings.py`

**Goal:** Two new bindings — `key_state(key)` (currently held) and `key_pressed(key)` (rising edge — true for one frame on press). The rising-edge tracking uses a TU-local `unordered_map<int, bool>` updated at the START of each `frame()` call (so press → frame() → key_pressed=true; next frame() → key_pressed=false).

- [ ] **Step 1: Write the failing tests**

Append to `tests/host/test_input_bindings.py`:

```python
def test_key_state_false_when_no_window_focus():
    import os
    import _open_stbc_host
    os.environ["OPEN_STBC_HOST_HEADLESS"] = "1"
    try:
        _open_stbc_host.init(64, 64, "key-state-test")
    except RuntimeError as e:
        import pytest
        pytest.skip(f"no GL context: {e}")
    try:
        # Hidden offscreen window never gets focus -> all keys read RELEASE.
        for name in ("KEY_W", "KEY_S", "KEY_A", "KEY_D", "KEY_R"):
            code = getattr(_open_stbc_host.keys, name)
            assert _open_stbc_host.key_state(code) is False, f"{name} reads pressed"
    finally:
        _open_stbc_host.shutdown()


def test_key_pressed_returns_false_when_not_held():
    import os
    import _open_stbc_host
    os.environ["OPEN_STBC_HOST_HEADLESS"] = "1"
    try:
        _open_stbc_host.init(64, 64, "key-pressed-test")
    except RuntimeError as e:
        import pytest
        pytest.skip(f"no GL context: {e}")
    try:
        # Without focus, no rising edges fire across multiple frames.
        for _ in range(3):
            assert _open_stbc_host.key_pressed(_open_stbc_host.keys.KEY_W) is False
            _open_stbc_host.frame()
    finally:
        _open_stbc_host.shutdown()


def test_key_bindings_require_init():
    import _open_stbc_host
    import pytest
    # key_state must throw if init wasn't called (no window to query).
    with pytest.raises(RuntimeError):
        _open_stbc_host.key_state(_open_stbc_host.keys.KEY_W)
    with pytest.raises(RuntimeError):
        _open_stbc_host.key_pressed(_open_stbc_host.keys.KEY_W)
```

- [ ] **Step 2: Run, verify it fails (no key_state binding)**

```bash
uv run pytest tests/host/test_input_bindings.py::test_key_state_false_when_no_window_focus -v 2>&1 | tail -10
```
Expected: FAIL — `AttributeError: module '_open_stbc_host' has no attribute 'key_state'`.

- [ ] **Step 3: Add the rising-edge state map to the bindings**

Modify `native/src/host/host_bindings.cc`. In the anonymous namespace (alongside `g_window`, `g_pipeline`, etc.), add:

```cpp
std::unordered_map<int, bool> g_prev_key_state;
```

Add the include `#include <unordered_map>` to the includes block.

In the existing `frame()` function, **at the very start** (before the `if (!g_window || !g_pipeline || !g_submitter)` check), add a no-op for now — we'll fill it in below in step 4. For now, place the snapshot logic at the end of frame() so the *current* state becomes prev for the *next* frame:

Actually do this in Step 4 below. Skip this sub-step in Step 3.

In `frame()`, immediately AFTER `g_window->poll_events();` and BEFORE `g_window->swap_buffers();`, insert:

```cpp
    // Snapshot current key state for next frame's rising-edge detection.
    // Only tracks keys that key_pressed was queried for since shutdown,
    // which is enough — rising-edge consumers are the only ones who care.
    for (auto& [k, prev] : g_prev_key_state) {
        prev = (glfwGetKey(g_window->native_handle(), k) == GLFW_PRESS);
    }
```

This requires `<GLFW/glfw3.h>` (already added in Task 2).

In `shutdown()`, after the existing `g_window.reset();` line, add:

```cpp
    g_prev_key_state.clear();
```

- [ ] **Step 4: Add the bindings**

In the `PYBIND11_MODULE` block, after the `keys.attr("KEY_9") = GLFW_KEY_9;` line from Task 2, insert:

```cpp
    m.def("key_state",
          [](int key) {
              if (!g_window) {
                  throw std::runtime_error("key_state: init must be called first");
              }
              return g_window->key_state(key);
          },
          py::arg("key"),
          "Returns true while the key is held.");

    m.def("key_pressed",
          [](int key) {
              if (!g_window) {
                  throw std::runtime_error("key_pressed: init must be called first");
              }
              const bool now = g_window->key_state(key);
              auto it = g_prev_key_state.find(key);
              const bool prev = (it != g_prev_key_state.end()) && it->second;
              if (it == g_prev_key_state.end()) {
                  // First query: register the key for tracking. Initial prev
                  // is the current state, so a key already held when the
                  // caller starts polling does NOT count as a rising edge.
                  g_prev_key_state[key] = now;
              }
              return now && !prev;
          },
          py::arg("key"),
          "Returns true on the first frame the key is pressed (rising edge).");
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
cmake --build build --target _open_stbc_host -j 2>&1 | tail -3
uv run pytest tests/host/test_input_bindings.py -v 2>&1 | tail -15
```
Expected: 5 PASSED.

- [ ] **Step 6: Verify no host-suite regressions**

```bash
uv run pytest tests/host/ tests/tools/ 2>&1 | tail -3
```
Expected: 28 PASSED (24 existing + 4 new — 1 from Task 2 was 2 tests; Task 3 adds 3 tests).

Wait — recount: Task 2 added 2 tests, Task 3 adds 3 tests. Total new = 5. Existing was 24. So 29 PASSED.

- [ ] **Step 7: Commit**

```bash
git add native/src/host/host_bindings.cc tests/host/test_input_bindings.py
git commit -m "feat(host): expose key_state and key_pressed (rising-edge) bindings"
```

---

## Task 4: `_PlayerControl` skeleton + throttle state machine

**Files:**
- Modify: `engine/host_loop.py`
- Create: `tests/host/test_player_control.py`

**Goal:** Define the `_PlayerControl` class with state-machine logic and a fake-key-reader-driven test suite. No transform integration yet — just the throttle level transitions.

- [ ] **Step 1: Write the failing test**

Create `tests/host/test_player_control.py`:

```python
"""Unit tests for _PlayerControl — the keyboard → ship-transform integrator.

Uses a mock `key_reader` (duck-typed to expose key_state, key_pressed, and
a `keys` attribute) so the integration logic is testable without a real
keyboard or window."""
from engine.host_loop import _PlayerControl


class _FakeKeys:
    KEY_W = 1
    KEY_S = 2
    KEY_A = 3
    KEY_D = 4
    KEY_Q = 5
    KEY_E = 6
    KEY_R = 7
    KEY_0 = 10
    KEY_1 = 11
    KEY_2 = 12
    KEY_3 = 13
    KEY_4 = 14
    KEY_5 = 15
    KEY_6 = 16
    KEY_7 = 17
    KEY_8 = 18
    KEY_9 = 19


class _FakeKeyReader:
    """A controllable key reader. `held` is the set of currently-held keys.
    `pressed_once` is consumed on first read (for rising-edge semantics)."""
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


class _FakePoint:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)


class _FakeShip:
    """Minimal duck-typed ship matching the engine.appc.objects.ObjectClass
    transform API used by _PlayerControl."""
    def __init__(self):
        from engine.appc.math import TGMatrix3
        self._pos = _FakePoint(0.0, 0.0, 0.0)
        self._rot = TGMatrix3()  # identity

    def GetTranslate(self):
        return _FakePoint(self._pos.x, self._pos.y, self._pos.z)

    def SetTranslateXYZ(self, x, y, z):
        self._pos = _FakePoint(x, y, z)

    def GetWorldRotation(self):
        from engine.appc.math import TGMatrix3
        out = TGMatrix3()
        out._m = [row[:] for row in self._rot._m]
        return out

    def SetMatrixRotation(self, mat):
        self._rot = mat


def test_initial_impulse_level_is_zero():
    pc = _PlayerControl()
    assert pc.impulse_level == 0


def test_digit_5_sets_forward_5():
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.pressed_once.add(reader.keys.KEY_5)
    pc.apply(ship, dt=1.0/60, h=reader)
    assert pc.impulse_level == 5


def test_R_sets_reverse_negative_two():
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.pressed_once.add(reader.keys.KEY_R)
    pc.apply(ship, dt=1.0/60, h=reader)
    assert pc.impulse_level == -2


def test_0_sets_full_stop():
    pc = _PlayerControl()
    pc.impulse_level = 7
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.pressed_once.add(reader.keys.KEY_0)
    pc.apply(ship, dt=1.0/60, h=reader)
    assert pc.impulse_level == 0


def test_digit_after_R_returns_to_forward():
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    # Press R first, then 7.
    reader.pressed_once.add(reader.keys.KEY_R)
    pc.apply(ship, dt=1.0/60, h=reader)
    assert pc.impulse_level == -2
    reader.pressed_once.add(reader.keys.KEY_7)
    pc.apply(ship, dt=1.0/60, h=reader)
    assert pc.impulse_level == 7


def test_digit_press_overrides_simultaneous_R_press():
    """If R and 1-9 both fire on the same frame (unlikely but possible),
    R is checked first, then digits — so R wins. Document this semantic."""
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.pressed_once.add(reader.keys.KEY_R)
    reader.pressed_once.add(reader.keys.KEY_5)
    pc.apply(ship, dt=1.0/60, h=reader)
    assert pc.impulse_level == -2  # R won
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest tests/host/test_player_control.py -v 2>&1 | tail -10
```
Expected: FAIL — `ImportError: cannot import name '_PlayerControl' from 'engine.host_loop'`.

- [ ] **Step 3: Implement `_PlayerControl` skeleton**

Modify `engine/host_loop.py`. Add the class definition AFTER the existing module-level constants (`SHIP_GATE_MISSION`, `DEFAULT_SKYBOX_NIF`, etc.) and BEFORE `_setup_sdk()`:

```python
# Camera-follow constants used by run() to position the third-person camera.
CAM_BACK_DIST = 600.0
CAM_UP_DIST   = 200.0


class _PlayerControl:
    """Keyboard-driven ship-transform integrator.

    Reads keys via a duck-typed `h` (the _open_stbc_host bindings module
    or a test fake) and updates the player's transform each tick. v1
    writes _position / _rotation directly because Phase 1's
    engine/physics/simulation.py is empty; when physics lands, this
    becomes target-velocity / target-heading instead.
    """

    TURN_RATE_RAD_PER_S = 1.5   # ~86°/s — half-turn in ~2.1s
    IMPULSE_UNIT        = 50.0  # BC units/s per impulse level
    REVERSE_LEVEL       = -2    # signed level set by R key

    def __init__(self):
        self.impulse_level = 0  # signed: -2..9; 0 = stop

    def apply(self, player, dt: float, h) -> None:
        """Read keys, update player transform.

        `h` is the _open_stbc_host bindings module (or any object with
        key_state, key_pressed, and `keys.KEY_*` attributes).
        """
        # 1. Throttle (one-shot edges). R is checked before digits so a
        #    simultaneous R + digit press picks R; in practice no human
        #    would do that on the same frame.
        if h.key_pressed(h.keys.KEY_R):
            self.impulse_level = self.REVERSE_LEVEL
        elif h.key_pressed(h.keys.KEY_0):
            self.impulse_level = 0
        else:
            digit_codes = [
                h.keys.KEY_1, h.keys.KEY_2, h.keys.KEY_3, h.keys.KEY_4,
                h.keys.KEY_5, h.keys.KEY_6, h.keys.KEY_7, h.keys.KEY_8,
                h.keys.KEY_9,
            ]
            for level, code in enumerate(digit_codes, start=1):
                if h.key_pressed(code):
                    self.impulse_level = level
                    break

        # Tasks 5 and 6 add rotation and position integration here.
```

- [ ] **Step 4: Run, verify all 6 tests pass**

```bash
uv run pytest tests/host/test_player_control.py -v 2>&1 | tail -12
```
Expected: 6 PASSED.

- [ ] **Step 5: Verify no host-suite regressions**

```bash
uv run pytest tests/host/ tests/tools/ 2>&1 | tail -3
```
Expected: all pass (29 + 6 = 35).

- [ ] **Step 6: Commit**

```bash
git add engine/host_loop.py tests/host/test_player_control.py
git commit -m "feat(host): _PlayerControl skeleton with throttle state machine"
```

---

## Task 5: `_PlayerControl` rotation integration

**Files:**
- Modify: `engine/host_loop.py`
- Modify: `tests/host/test_player_control.py`

**Goal:** Pitch / yaw / roll while keys are held. The ship's rotation matrix gets a small ship-local rotation post-multiplied each tick.

- [ ] **Step 1: Write the failing test**

Append to `tests/host/test_player_control.py`:

```python
def test_no_input_no_rotation():
    """With no keys held, rotation stays at identity across many ticks."""
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    initial = ship.GetWorldRotation()
    for _ in range(120):
        pc.apply(ship, dt=1.0/60, h=reader)
    final = ship.GetWorldRotation()
    for r in range(3):
        for c in range(3):
            assert abs(final._m[r][c] - initial._m[r][c]) < 1e-9


def test_pitch_down_rotates_forward_below_horizontal():
    """Hold W (pitch down) for one second of dt at 60Hz. The ship's
    forward vector (row 1 of the rotation matrix) should pitch down from
    +Y toward -Z by 1.5 radians (one second × 1.5 rad/s)."""
    import math
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.held.add(reader.keys.KEY_W)
    for _ in range(60):
        pc.apply(ship, dt=1.0/60, h=reader)
    forward = ship.GetWorldRotation().GetRow(1)
    # After pitching down 1.5 rad: forward.y = cos(1.5), forward.z = -sin(1.5)
    expected_y = math.cos(1.5)
    expected_z = -math.sin(1.5)
    assert abs(forward.x) < 1e-3
    assert abs(forward.y - expected_y) < 1e-3, f"forward.y={forward.y}, expected {expected_y}"
    assert abs(forward.z - expected_z) < 1e-3, f"forward.z={forward.z}, expected {expected_z}"


def test_pitch_up_rotates_forward_above_horizontal():
    """Hold S (pitch up) for one second. Forward should rotate up by
    +1.5 rad (toward +Z)."""
    import math
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.held.add(reader.keys.KEY_S)
    for _ in range(60):
        pc.apply(ship, dt=1.0/60, h=reader)
    forward = ship.GetWorldRotation().GetRow(1)
    expected_y = math.cos(1.5)
    expected_z = math.sin(1.5)
    assert abs(forward.y - expected_y) < 1e-3
    assert abs(forward.z - expected_z) < 1e-3


def test_yaw_left_rotates_forward_toward_minus_x():
    """Hold A (yaw left) for one second. Forward rotates around world Z
    (which is also ship-Z at identity start) by -1.5 rad: from +Y toward -X."""
    import math
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.held.add(reader.keys.KEY_A)
    for _ in range(60):
        pc.apply(ship, dt=1.0/60, h=reader)
    forward = ship.GetWorldRotation().GetRow(1)
    expected_x = -math.sin(1.5)
    expected_y = math.cos(1.5)
    assert abs(forward.x - expected_x) < 1e-3, f"forward.x={forward.x}, expected {expected_x}"
    assert abs(forward.y - expected_y) < 1e-3
    assert abs(forward.z) < 1e-3


def test_roll_left_rotates_up_toward_minus_x():
    """Hold Q (roll left) for one second at identity start. Roll is
    around ship-Y (forward axis). Ship's up (row 2) starts at +Z, rolls
    -1.5 rad around +Y: up goes from +Z toward -X."""
    import math
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.held.add(reader.keys.KEY_Q)
    for _ in range(60):
        pc.apply(ship, dt=1.0/60, h=reader)
    up = ship.GetWorldRotation().GetRow(2)
    expected_x = -math.sin(1.5)
    expected_z = math.cos(1.5)
    assert abs(up.x - expected_x) < 1e-3, f"up.x={up.x}, expected {expected_x}"
    assert abs(up.y) < 1e-3
    assert abs(up.z - expected_z) < 1e-3
```

- [ ] **Step 2: Run, verify it fails**

```bash
uv run pytest tests/host/test_player_control.py -v 2>&1 | tail -15
```
Expected: 6 of the original tests pass; the 5 new tests fail (`assert abs(forward.y - cos(1.5)) < 1e-3` fails because rotation isn't integrated yet).

- [ ] **Step 3: Add rotation integration to `_PlayerControl.apply`**

Modify `engine/host_loop.py`. In `_PlayerControl.apply`, replace the trailing comment line `# Tasks 5 and 6 add rotation and position integration here.` with:

```python
        # 2. Angular rates (continuous while held).
        pitch_rate = 0.0
        yaw_rate   = 0.0
        roll_rate  = 0.0
        if h.key_state(h.keys.KEY_W): pitch_rate -= self.TURN_RATE_RAD_PER_S
        if h.key_state(h.keys.KEY_S): pitch_rate += self.TURN_RATE_RAD_PER_S
        if h.key_state(h.keys.KEY_A): yaw_rate   -= self.TURN_RATE_RAD_PER_S
        if h.key_state(h.keys.KEY_D): yaw_rate   += self.TURN_RATE_RAD_PER_S
        if h.key_state(h.keys.KEY_Q): roll_rate  -= self.TURN_RATE_RAD_PER_S
        if h.key_state(h.keys.KEY_E): roll_rate  += self.TURN_RATE_RAD_PER_S

        # 3. Rotation integration (post-multiply small per-tick rotation
        #    in ship-local frame). Order pitch -> yaw -> roll matches
        #    flight-sim convention; at small dt, composition order is
        #    not visually distinguishable from any other Euler order.
        from engine.appc.math import TGMatrix3, TGPoint3
        X_AXIS = TGPoint3(1.0, 0.0, 0.0)
        Y_AXIS = TGPoint3(0.0, 1.0, 0.0)
        Z_AXIS = TGPoint3(0.0, 0.0, 1.0)

        R = player.GetWorldRotation()
        if pitch_rate or yaw_rate or roll_rate:
            R_pitch = TGMatrix3(); R_pitch.MakeRotation(pitch_rate * dt, X_AXIS)
            R_yaw   = TGMatrix3(); R_yaw.MakeRotation(yaw_rate   * dt, Z_AXIS)
            R_roll  = TGMatrix3(); R_roll.MakeRotation(roll_rate  * dt, Y_AXIS)
            R = R.MultMatrix(R_pitch).MultMatrix(R_yaw).MultMatrix(R_roll)
            player.SetMatrixRotation(R)

        # Task 6 adds position integration here.
```

- [ ] **Step 4: Run, verify all 11 tests pass**

```bash
uv run pytest tests/host/test_player_control.py -v 2>&1 | tail -15
```
Expected: 11 PASSED.

- [ ] **Step 5: Verify no host-suite regressions**

```bash
uv run pytest tests/host/ tests/tools/ 2>&1 | tail -3
```
Expected: 40 PASSED.

- [ ] **Step 6: Commit**

```bash
git add engine/host_loop.py tests/host/test_player_control.py
git commit -m "feat(host): _PlayerControl pitch/yaw/roll rotation integration"
```

---

## Task 6: `_PlayerControl` position integration

**Files:**
- Modify: `engine/host_loop.py`
- Modify: `tests/host/test_player_control.py`

**Goal:** Per-tick position update. Ship's forward direction (row 1 of rotation) × signed impulse level × IMPULSE_UNIT × dt = world-space delta.

- [ ] **Step 1: Write the failing tests**

Append to `tests/host/test_player_control.py`:

```python
def test_no_throttle_no_movement():
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    for _ in range(60):
        pc.apply(ship, dt=1.0/60, h=reader)
    p = ship.GetTranslate()
    assert abs(p.x) < 1e-9
    assert abs(p.y) < 1e-9
    assert abs(p.z) < 1e-9


def test_impulse_5_advances_along_world_y_at_identity():
    """At identity rotation, forward = +Y. After 1.0s at impulse 5,
    position should be (0, 5 * IMPULSE_UNIT * 1.0, 0) = (0, 250, 0)."""
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.pressed_once.add(reader.keys.KEY_5)
    for _ in range(60):
        pc.apply(ship, dt=1.0/60, h=reader)
        # First-tick rising edge consumed; subsequent ticks just integrate.
    p = ship.GetTranslate()
    assert abs(p.x) < 1e-3
    assert abs(p.y - 250.0) < 1e-1, f"p.y={p.y}, expected ~250.0"
    assert abs(p.z) < 1e-3


def test_reverse_advances_negative_along_world_y():
    """R sets level=-2. After 1.0s, position is (0, -100, 0)."""
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.pressed_once.add(reader.keys.KEY_R)
    for _ in range(60):
        pc.apply(ship, dt=1.0/60, h=reader)
    p = ship.GetTranslate()
    assert abs(p.y - (-100.0)) < 1e-1, f"p.y={p.y}, expected ~-100.0"


def test_full_stop_after_movement_stops_advancement():
    """Set impulse 5, run 30 frames, set 0, run 30 more. Position
    advances during the first 30, stays put for the next 30."""
    pc = _PlayerControl()
    ship = _FakeShip()
    reader = _FakeKeyReader()
    reader.pressed_once.add(reader.keys.KEY_5)
    for _ in range(30):
        pc.apply(ship, dt=1.0/60, h=reader)
    pos_after_first_half = ship.GetTranslate()
    assert pos_after_first_half.y > 0
    reader.pressed_once.add(reader.keys.KEY_0)
    for _ in range(30):
        pc.apply(ship, dt=1.0/60, h=reader)
    pos_after_second_half = ship.GetTranslate()
    assert abs(pos_after_second_half.y - pos_after_first_half.y) < 1e-3
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest tests/host/test_player_control.py -v 2>&1 | tail -15
```
Expected: 11 existing pass; 4 new fail (position stays at 0 because integration not added yet).

- [ ] **Step 3: Add position integration**

Modify `engine/host_loop.py`. In `_PlayerControl.apply`, replace the trailing comment line `# Task 6 adds position integration here.` with:

```python
        # 4. Position integration (forward = ship-local Y axis in world).
        if self.impulse_level != 0:
            forward = R.GetRow(1)
            speed   = self.impulse_level * self.IMPULSE_UNIT
            p = player.GetTranslate()
            player.SetTranslateXYZ(
                p.x + forward.x * speed * dt,
                p.y + forward.y * speed * dt,
                p.z + forward.z * speed * dt,
            )
```

- [ ] **Step 4: Run, verify all 15 tests pass**

```bash
uv run pytest tests/host/test_player_control.py -v 2>&1 | tail -20
```
Expected: 15 PASSED.

- [ ] **Step 5: Verify host-suite still clean**

```bash
uv run pytest tests/host/ tests/tools/ 2>&1 | tail -3
```
Expected: 44 PASSED.

- [ ] **Step 6: Commit**

```bash
git add engine/host_loop.py tests/host/test_player_control.py
git commit -m "feat(host): _PlayerControl position integration along ship-forward"
```

---

## Task 7: Wire `_PlayerControl` into the run loop + camera-follow uses ship-local axes

**Files:**
- Modify: `engine/host_loop.py`
- Modify: `tests/host/test_host_loop_unit.py`

**Goal:** `run()` constructs a `_PlayerControl`, calls `apply()` each tick, and updates the camera using ship-local forward/up so banking is visible. Existing `OPEN_STBC_HOST_FIXED_CAMERA=1` override still works.

- [ ] **Step 1: Strengthen the existing 5-tick smoke test**

Modify `tests/host/test_host_loop_unit.py`. Replace the existing `test_run_M1_Basic_for_a_few_ticks` body with:

```python
def test_run_M1_Basic_for_a_few_ticks():
    import os
    from pathlib import Path
    import pytest

    PROJECT_ROOT = Path(__file__).parent.parent.parent
    GALAXY_NIF = PROJECT_ROOT / "game" / "data" / "Models" / "Ships" / "Galaxy" / "Galaxy.nif"
    if not GALAXY_NIF.is_file():
        pytest.skip("BC assets not available")

    os.environ["OPEN_STBC_HOST_HEADLESS"] = "1"
    from engine import host_loop
    rc = host_loop.run("Custom.Tutorial.Episode.M1Basic.M1Basic", max_ticks=5)
    assert rc == 0


def test_run_M1_Basic_player_unmoved_without_input():
    """Headless run with no key input. Player should not move (no auto-
    drift, no physics, no input-leak through key_state in offscreen mode)."""
    import os
    from pathlib import Path
    import pytest

    PROJECT_ROOT = Path(__file__).parent.parent.parent
    GALAXY_NIF = PROJECT_ROOT / "game" / "data" / "Models" / "Ships" / "Galaxy" / "Galaxy.nif"
    if not GALAXY_NIF.is_file():
        pytest.skip("BC assets not available")
    os.environ["OPEN_STBC_HOST_HEADLESS"] = "1"

    # We can't easily probe player state across the run() boundary, so
    # this test just confirms run(max_ticks=5) doesn't crash with the new
    # _PlayerControl integration in the loop. Rotation/position drift in
    # offscreen mode (where keys can never be pressed) would surface as
    # a NaN or assertion in one of the bindings, which would crash the
    # subprocess test below.
    from engine import host_loop
    rc = host_loop.run("Custom.Tutorial.Episode.M1Basic.M1Basic", max_ticks=5)
    assert rc == 0
```

- [ ] **Step 2: Run, verify the new test passes (it's identical to the old one structurally)**

```bash
uv run pytest tests/host/test_host_loop_unit.py -v 2>&1 | tail -10
```
Expected: 5 PASSED (4 existing + 1 new).

- [ ] **Step 3: Wire `_PlayerControl` into `run()`**

Modify `engine/host_loop.py`. In the `run()` function, locate the existing `loop = GameLoop()` line. Before the `while not r.should_close():` line, add:

```python
        # Per-tick player input → ship-transform integrator.
        player_control = _PlayerControl()
        try:
            import _open_stbc_host as _h
        except ImportError:
            _h = None  # bindings module not built; skip input handling.
        TICK_DT = 1.0 / 60.0
```

Then, **inside** the `while not r.should_close():` loop body, immediately AFTER `loop.tick()` and BEFORE the `# Sync transforms for known instances.` block, insert:

```python
            # Apply keyboard input to the player ship's transform.
            if player is not None and _h is not None:
                player_control.apply(player, TICK_DT, _h)
```

- [ ] **Step 4: Update the camera-follow logic to use ship-local axes**

Still in `run()`, replace the existing `elif player is not None:` block (which currently computes `eye = (p.x, p.y + 30.0, p.z + 200.0)` etc.) with:

```python
            elif player is not None:
                R = player.GetWorldRotation()
                forward = R.GetRow(1)
                up      = R.GetRow(2)
                p = player.GetWorldLocation()
                eye = (p.x - forward.x * CAM_BACK_DIST + up.x * CAM_UP_DIST,
                       p.y - forward.y * CAM_BACK_DIST + up.y * CAM_UP_DIST,
                       p.z - forward.z * CAM_BACK_DIST + up.z * CAM_UP_DIST)
                target = (p.x, p.y, p.z)
                up_vec = (up.x, up.y, up.z)
                r.set_camera(eye=eye, target=target, up=up_vec,
                             fov_y_rad=1.0472, near=1.0, far=100000.0)
```

(The branch immediately above — `if fixed_camera:` — and the trailing `else` for the no-player fallback stay unchanged. Only the player-follow branch changes. Locate it by the comment `# Camera: third-person offset behind the player ship (or origin).`)

- [ ] **Step 5: Run all tests**

```bash
cmake --build build --target _open_stbc_host -j 2>&1 | tail -3
uv run pytest tests/host/ tests/tools/ 2>&1 | tail -3
```
Expected: 45 PASSED.

- [ ] **Step 6: Verify the binary still boots cleanly headless**

```bash
OPEN_STBC_HOST_HEADLESS=1 ./build/bin/open_stbc_host --smoke-check && echo "exit=$?"
```
Expected: dict with python_version + app_module printed, exit 0.

- [ ] **Step 7: Manual visible verification**

Run on a machine with a display:

```bash
./build/bin/open_stbc_host
```

Expected:
- Galaxy textured ship visible, sized to fit the viewport (camera now 600 units back instead of 200).
- Pressing **5** advances the ship forward at impulse 5; the camera follows.
- Pressing **W**/**S** pitches; **A**/**D** yaws; **Q**/**E** rolls. Camera tracks the ship's orientation (banking is visible during roll).
- Pressing **R** reverses at level 2.
- Pressing **0** stops the ship.
- Pressing **1**–**9** sets the corresponding forward impulse level.
- Closing the window exits 0.

- [ ] **Step 8: Commit**

```bash
git add engine/host_loop.py tests/host/test_host_loop_unit.py
git commit -m "feat(host): wire _PlayerControl into run loop + ship-local camera follow"
```

---

## Task 8: Sub-project status + deferred-work tracker entry

**Files:**
- Modify: `docs/architecture/sub_project_status.md`
- Modify: `native/src/host/docs/deferred_work.md`

**Goal:** Record the new spec/plan in the project's status doc and add ship-controls deferred items to the renderer-host tracker.

- [ ] **Step 1: Update `sub_project_status.md`**

Modify `docs/architecture/sub_project_status.md`. After the existing renderer-host row in the renderer sub-projects table, add a new row tracking the ship-controls work. Locate the existing row that reads:

```
| 3-6 | Renderer host (combined: ...) | Implemented (v1 ship gate met 2026-05-09; ...) | [2026-05-09-renderer-host-design.md](...) | [`native/src/host/docs/deferred_work.md`](...) |
```

Add a new row immediately below it:

```
| 3-6+ | Ship controls (movement-only keyboard input) | Implemented (2026-05-09; player flies the Galaxy via Q/W/E/A/S/D + 0–9 + R) | [2026-05-09-ship-controls-design.md](../superpowers/specs/2026-05-09-ship-controls-design.md) | (folded into renderer-host's `deferred_work.md`) |
```

- [ ] **Step 2: Append ship-controls deferred items to the renderer-host tracker**

Modify `native/src/host/docs/deferred_work.md`. After the existing item 16 in the "Spec items" list, add:

```
17. **Read turn rate / max impulse from BC config.** `_PlayerControl`'s
    `TURN_RATE_RAD_PER_S` (1.5) and `IMPULSE_UNIT` (50.0) are tuned by
    feel; they should come from the ship's `ImpulseEngineSubsystem`
    properties or `GlobalPropertyTemplates.py` once Phase 1 wires those
    up. Same for `REVERSE_LEVEL`.
18. **Switch to physics integration.** When `engine/physics/simulation.py`
    gets a real PyBullet integrator, `_PlayerControl.apply` should set
    target velocity / target angular velocity on the ship's impulse
    subsystem instead of writing the transform directly.
19. **BC config-file keybindings.** Read user-customized bindings from
    `data/scripts/Custom/Bridge/Keymap.py` (or wherever BC stores them)
    so players who remap keys see those bindings honored.
20. **Mouse input.** Stock BC supports yaw/pitch via mouse-look; v1 is
    keyboard-only.
21. **Acceleration / deceleration curves.** v1 sets impulse level
    instantaneously; BC ramps. Adding ramps depends on item 18 above.
22. **Auto-damping toggle.** Some space sims auto-damp angular velocity
    when no input is held; v1 doesn't (release = stop turning, but no
    re-centering).
```

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/sub_project_status.md native/src/host/docs/deferred_work.md
git commit -m "docs(status): ship-controls v1 implemented; record deferred items"
```

---

## Self-review

**Spec coverage:**
- Spec § Architecture / Component layout: covered by Tasks 1 (Window), 2-3 (bindings), 4-7 (host_loop).
- Spec § Keybindings: Task 2 exposes the constants; Task 4-6 implements the state machine + integration.
- Spec § Constants: TURN_RATE_RAD_PER_S, IMPULSE_UNIT, REVERSE_LEVEL on `_PlayerControl` (Task 4); CAM_BACK_DIST, CAM_UP_DIST module-level (Task 7).
- Spec § Tests: `Window.KeyStateReturnsFalseForUnpressedKeys` (Task 1), `test_keys_submodule_exists` + `test_key_constants_exist_and_are_distinct` (Task 2), `test_key_state_false_when_no_window_focus` + `test_key_pressed_returns_false_when_not_held` + `test_key_bindings_require_init` (Task 3), throttle state machine + rotation + position tests (Tasks 4-6), end-to-end run smoke (Task 7).
- Spec § Deferred / future work: tracker updated in Task 8.

**Placeholder scan:** No "TBD"/"TODO" steps. Step 6's expected-test-count math threads through correctly: 24 existing → +2 (Task 2) → +3 (Task 3) → +6 (Task 4) → +5 (Task 5) → +4 (Task 6) → 44 host+tools, then +1 in Task 7 = 45.

**Type consistency:**
- `_PlayerControl` uses `impulse_level: int` consistently across Tasks 4-6.
- The `keys.KEY_*` attributes are used the same way in bindings (Task 2-3) and tests (Task 4 _FakeKeys).
- `TGMatrix3.MakeRotation(angle, TGPoint3)` signature confirmed by reading `engine/appc/math.py:149`.
- `TGMatrix3.GetRow(i) -> TGPoint3` confirmed by reading `engine/appc/math.py:167`.
- `TGMatrix3.MultMatrix(other) -> TGMatrix3` confirmed by reading `engine/appc/math.py:203`.

**Known weak spots:**
- The math expectations in Task 5's tests assume `MakeRotation` uses Rodrigues' formula and that `MultMatrix` post-multiplies in the conventional order (left * right). Both confirmed in `engine/appc/math.py`. If the convention is different (e.g. column-major vs row-major confusion), the test failures will be informative — the implementer should NOT change the test expectations to match buggy code; instead, surface the inconsistency.
- `_PlayerControl.apply` in Task 5 imports `TGMatrix3` / `TGPoint3` inside the method body rather than at module top. This is intentional — `engine.host_loop` runs in environments where `engine.appc.math` may not be importable until after `_setup_sdk()`. Keep the imports inside `apply`.
