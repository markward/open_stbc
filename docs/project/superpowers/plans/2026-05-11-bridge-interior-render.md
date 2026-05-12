# Bridge Interior Render Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the DBridge interior NIF when bridge view is active, with mouse-look from the captain's-chair pose, on a new C++ bridge render pass that pays forward to the eventual viewscreen RTT.

**Architecture:** A two-pass renderer (space pass + bridge pass with `glClear(GL_DEPTH_BUFFER_BIT)` between them). Each `scenegraph::Instance` is tagged with a `Pass` enum (default `Space`). The frame loop calls `submit_opaque` twice — once with the space camera and the space pass, then (only when `g_bridge_pass_enabled`) once with the bridge camera and the bridge pass. New C++ bindings expose the bridge camera, pass-toggle, bridge-instance creation, mouse-delta accumulator, and cursor-lock control. Python adds a `_BridgeCamera` controller wired into the existing `_ViewModeController` toggle.

**Tech Stack:** C++17 (scenegraph + renderer + host bindings), GLFW3 (cursor lock + mouse callback), pybind11, OpenGL 3.3, Python 3 (engine), pytest, gtest (C++ unit tests).

**Spec:** [docs/superpowers/specs/2026-05-11-bridge-interior-render-design.md](../specs/2026-05-11-bridge-interior-render-design.md)

---

## File map

- **Create**
  - `tests/host/test_bridge_camera.py` — `_BridgeCamera` math unit tests (fake bindings).
  - `tests/host/test_bridge_bindings.py` — smoke test that the five new C++ bindings exist with the documented shapes.
- **Modify**
  - `native/src/scenegraph/include/scenegraph/instance.h` — add `Pass` enum + `pass` field on `Instance`.
  - `native/src/scenegraph/include/scenegraph/world.h` — add `set_pass()` + `for_each_visible_in_pass()`.
  - `native/src/scenegraph/src/world.cc` — implement `set_pass()`.
  - `native/tests/scenegraph/world_test.cc` — gtest cases for the new APIs.
  - `native/src/renderer/include/renderer/window.h` — declare `consume_mouse_delta()`, `set_cursor_locked()`.
  - `native/src/renderer/window.cc` — cursor-pos callback, accumulator, lock toggle.
  - `native/src/host/host_bindings.cc` — add bridge globals, five new bindings, frame() bridge pass.
  - `engine/host_loop.py` — add `_BridgeCamera`, extend `_apply_input` / `_compute_camera` / `_ViewModeController.toggle`, ESC handler, startup bridge load.
  - `tests/host/test_view_mode.py` — three new toggle/ESC integration tests + adjust existing assertions.

---

## Task 1: Tag `scenegraph::Instance` with a `Pass` enum

**Files:**
- Modify: `native/src/scenegraph/include/scenegraph/instance.h`
- Modify: `native/src/scenegraph/include/scenegraph/world.h`
- Modify: `native/src/scenegraph/src/world.cc`
- Modify: `native/tests/scenegraph/world_test.cc`

This sets up the data the bridge pass needs without yet plugging anything into rendering. Default `Pass::Space` keeps every existing instance behaving exactly as today.

- [ ] **Step 1: Write the failing C++ tests**

Append to `native/tests/scenegraph/world_test.cc` (after the existing `SetVisibleFlipsFlag` test):

```cpp
TEST(World, NewInstanceDefaultsToSpacePass) {
    World w;
    auto id = w.create_instance(7);
    auto* inst = w.get(id);
    ASSERT_NE(inst, nullptr);
    EXPECT_EQ(inst->pass, scenegraph::Pass::Space);
}

TEST(World, SetPassUpdatesField) {
    World w;
    auto id = w.create_instance(7);
    w.set_pass(id, scenegraph::Pass::Bridge);
    EXPECT_EQ(w.get(id)->pass, scenegraph::Pass::Bridge);
}

TEST(World, ForEachVisibleInPassFiltersByPass) {
    World w;
    auto a = w.create_instance(1);
    auto b = w.create_instance(2);
    auto c = w.create_instance(3);
    w.set_pass(b, scenegraph::Pass::Bridge);
    // Only c stays in Space; b is in Bridge; a is default (Space).

    std::vector<ModelHandle> seen_space;
    w.for_each_visible_in_pass(scenegraph::Pass::Space, [&](const Instance& i) {
        seen_space.push_back(i.model_handle);
    });
    std::vector<ModelHandle> seen_bridge;
    w.for_each_visible_in_pass(scenegraph::Pass::Bridge, [&](const Instance& i) {
        seen_bridge.push_back(i.model_handle);
    });

    EXPECT_EQ(seen_space.size(), 2u);
    EXPECT_EQ(seen_bridge.size(), 1u);
    EXPECT_EQ(seen_bridge[0], 2u);
}

TEST(World, ForEachVisibleInPassRespectsVisibilityFlag) {
    World w;
    auto a = w.create_instance(1);
    w.set_pass(a, scenegraph::Pass::Bridge);
    w.set_visible(a, false);
    int count = 0;
    w.for_each_visible_in_pass(scenegraph::Pass::Bridge, [&](const Instance&) { ++count; });
    EXPECT_EQ(count, 0);
}
```

- [ ] **Step 2: Run the C++ tests to verify they fail**

```bash
cmake --build build -j scenegraph_tests
./build/native/tests/scenegraph/scenegraph_tests --gtest_filter='World.New*:World.Set*:World.ForEach*'
```
Expected: compile failures referencing `scenegraph::Pass`, `set_pass`, and `for_each_visible_in_pass` (none defined yet).

- [ ] **Step 3: Add the `Pass` enum and field**

Edit `native/src/scenegraph/include/scenegraph/instance.h`:

```cpp
// native/src/scenegraph/include/scenegraph/instance.h
#pragma once

#include <cstdint>
#include <glm/glm.hpp>

namespace scenegraph {

using ModelHandle = std::uint64_t;  // Opaque key into the asset cache.

struct InstanceId {
    std::uint32_t index = 0;
    std::uint32_t generation = 0;
    bool operator==(const InstanceId&) const = default;
};

/// Which renderer pass an instance is drawn in.
/// - Space: ships, planets, suns, dust, backdrops (default).
/// - Bridge: the bridge interior geometry, drawn after a depth clear.
enum class Pass : std::uint8_t { Space = 0, Bridge = 1 };

struct Instance {
    ModelHandle model_handle = 0;
    glm::mat4 world{1.0f};
    bool visible = true;
    Pass pass = Pass::Space;
};

}  // namespace scenegraph
```

- [ ] **Step 4: Add `set_pass` + `for_each_visible_in_pass` to `World`**

Edit `native/src/scenegraph/include/scenegraph/world.h`:

```cpp
// native/src/scenegraph/include/scenegraph/world.h
#pragma once

#include "scenegraph/instance.h"

#include <vector>

namespace scenegraph {

class World {
public:
    InstanceId create_instance(ModelHandle model);
    void destroy_instance(InstanceId id);
    void set_world_transform(InstanceId id, const glm::mat4& world);
    void set_visible(InstanceId id, bool visible);
    void set_pass(InstanceId id, Pass pass);

    bool is_valid(InstanceId id) const noexcept;
    Instance* get(InstanceId id) noexcept;
    const Instance* get(InstanceId id) const noexcept;

    void propagate() noexcept {}

    /// Iterate every visible instance regardless of pass.
    template <typename Fn>
    void for_each_visible(Fn&& fn) const {
        for (std::size_t i = 0; i < slots_.size(); ++i) {
            if (slots_[i].alive && slots_[i].instance.visible) {
                fn(slots_[i].instance);
            }
        }
    }

    /// Iterate every visible instance whose `pass` matches `pass`.
    template <typename Fn>
    void for_each_visible_in_pass(Pass pass, Fn&& fn) const {
        for (std::size_t i = 0; i < slots_.size(); ++i) {
            if (slots_[i].alive
                && slots_[i].instance.visible
                && slots_[i].instance.pass == pass) {
                fn(slots_[i].instance);
            }
        }
    }

private:
    struct Slot {
        Instance instance;
        std::uint32_t generation = 0;
        bool alive = false;
    };
    std::vector<Slot> slots_;
    std::vector<std::uint32_t> free_;
};

}  // namespace scenegraph
```

- [ ] **Step 5: Implement `set_pass` in `world.cc`**

Edit `native/src/scenegraph/src/world.cc` — add after `set_visible`:

```cpp
void World::set_pass(InstanceId id, Pass pass) {
    if (auto* inst = get(id)) inst->pass = pass;
}
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cmake --build build -j scenegraph_tests
./build/native/tests/scenegraph/scenegraph_tests --gtest_filter='World.*'
```
Expected: all `World.*` tests pass, including the four new cases.

- [ ] **Step 7: Commit**

```bash
git add native/src/scenegraph/include/scenegraph/instance.h \
        native/src/scenegraph/include/scenegraph/world.h \
        native/src/scenegraph/src/world.cc \
        native/tests/scenegraph/world_test.cc
git commit -m "feat(scenegraph): tag instances with Pass enum + filtered iteration

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Bridge-pass globals + frame() integration in host_bindings.cc

**Files:**
- Modify: `native/src/host/host_bindings.cc`
- Create: `tests/host/test_bridge_bindings.py`

Adds the four renderer-side bindings (`create_bridge_instance`, `set_bridge_camera`, `bridge_pass_set_enabled`) and the second `submit_opaque` call wrapped in a depth clear. Cursor and mouse-delta come in Task 3.

- [ ] **Step 1: Write the failing Python smoke test**

Create `tests/host/test_bridge_bindings.py`:

```python
"""Smoke tests for the bridge-pass C++ bindings. These don't validate
rendering correctness — that's covered by the live visual verify in the
plan's final task — but they confirm the bindings exist with the right
shapes so a missing-attribute error in the host loop fails fast."""
import pytest


@pytest.fixture
def host_module():
    """The compiled _open_stbc_host module; xfail-cleanly if the build
    is stale and the bindings haven't been refreshed."""
    pytest.importorskip("_open_stbc_host")
    import _open_stbc_host as h
    return h


def test_create_bridge_instance_binding_exists(host_module):
    assert hasattr(host_module, "create_bridge_instance")


def test_set_bridge_camera_binding_exists(host_module):
    assert hasattr(host_module, "set_bridge_camera")


def test_bridge_pass_set_enabled_binding_exists(host_module):
    assert hasattr(host_module, "bridge_pass_set_enabled")


def test_bridge_pass_set_enabled_accepts_bool_without_init(host_module):
    """bridge_pass_set_enabled must be safe to call before init() —
    it only mutates a global flag; no GL state is touched until frame()."""
    host_module.bridge_pass_set_enabled(False)
    host_module.bridge_pass_set_enabled(True)
    host_module.bridge_pass_set_enabled(False)  # leave disabled
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/host/test_bridge_bindings.py -v
```
Expected: all four tests FAIL with `AttributeError: module '_open_stbc_host' has no attribute '...'`. (If `_open_stbc_host` itself can't be imported, that's a stale-build problem — rebuild from `build/` per CLAUDE.md.)

- [ ] **Step 3: Add the bridge globals + frame() pass to `host_bindings.cc`**

In `native/src/host/host_bindings.cc`, find the existing globals section (the `g_camera`, `g_lighting`, `g_world`, etc. declarations near the top of the anonymous namespace) and add:

```cpp
scenegraph::Camera g_bridge_camera;     // Per-pass camera for the bridge.
bool g_bridge_pass_enabled = false;     // Mode flag set from Python.
```

Then in the `frame()` function, find the existing dust-pass call and the UI-render block. Insert the bridge pass between them:

```cpp
    if (g_dust_pass) g_dust_pass->render(g_camera, dt, *g_pipeline);

    // ── Bridge pass ──────────────────────────────────────────────────────
    // Renders bridge-tagged instances with the bridge camera, after a
    // depth clear so the bridge geometry overlays the space scene
    // regardless of world-space coordinates. The space pass + special
    // passes above are wasted work in bridge mode but are kept so the
    // future viewscreen RTT can swap the space pass's target without
    // adding a "render space here" path that didn't exist before.
    if (g_bridge_pass_enabled) {
        glClear(GL_DEPTH_BUFFER_BIT);
        if (fh > 0) g_bridge_camera.aspect = static_cast<float>(fw) / static_cast<float>(fh);
        g_submitter->submit_opaque_in_pass(
            g_world, g_bridge_camera, *g_pipeline, lookup, g_lighting,
            scenegraph::Pass::Bridge);
    }

    if (g_ui_system) {
```

(The `submit_opaque_in_pass` overload is added in Step 4.)

- [ ] **Step 4: Add `submit_opaque_in_pass` (a thin wrapper that filters by pass)**

There's only one call site for `submit_opaque` today (frame() in host_bindings.cc, which we're modifying anyway). The cleanest move is to leave `submit_opaque` alone for backward-compat with the existing call and add `submit_opaque_in_pass` as a near-clone that delegates to a shared body via `for_each_visible_in_pass`. The *iteration* is the only line that differs.

In `native/src/renderer/include/renderer/frame.h`, find the existing `submit_opaque` declaration on `FrameSubmitter` and add directly after it:

```cpp
void submit_opaque_in_pass(const scenegraph::World& world,
                           const scenegraph::Camera& camera,
                           Pipeline& pipeline,
                           const ModelLookup& lookup,
                           const Lighting& lighting,
                           scenegraph::Pass pass);
```

(Note `Pipeline&` is non-const, matching the existing `submit_opaque` signature in [native/src/renderer/frame.cc:154](../../../native/src/renderer/frame.cc#L154).)

In `native/src/renderer/frame.cc`, append after the existing `submit_opaque` definition (around line 184):

```cpp
void FrameSubmitter::submit_opaque_in_pass(const scenegraph::World& world,
                                           const scenegraph::Camera& camera,
                                           Pipeline& pipeline,
                                           const ModelLookup& lookup,
                                           const Lighting& lighting,
                                           scenegraph::Pass pass) {
    auto& shader = pipeline.opaque_shader();
    shader.use();
    shader.set_mat4("u_view", camera.view_matrix());
    shader.set_mat4("u_proj", camera.proj_matrix());

    const glm::vec3 cam_pos_ws =
        glm::vec3(glm::inverse(camera.view_matrix())[3]);
    shader.set_vec3("u_camera_pos_ws", cam_pos_ws);

    shader.set_vec3("u_ambient_light", lighting.ambient);
    shader.set_int("u_dir_light_count", lighting.directional_count);
    if (lighting.directional_count > 0) {
        shader.set_vec3_array("u_dir_light_dir_ws",
                              lighting.directional_dir_ws,
                              lighting.directional_count);
        shader.set_vec3_array("u_dir_light_color",
                              lighting.directional_color,
                              lighting.directional_count);
    }

    const GLuint white = ensure_white_texture();
    const GLuint black = ensure_black_texture();

    world.for_each_visible_in_pass(pass, [&](const scenegraph::Instance& inst) {
        const assets::Model* m = lookup(inst.model_handle);
        if (m) draw_model(*m, inst.world, shader, white, black);
    });
}
```

This is intentional copy-paste of `submit_opaque`'s body with one line changed (`for_each_visible` → `for_each_visible_in_pass`). The duplication is fine for now — it's 25 lines, well under the threshold where extracting a helper is worth the indirection. If `submit_opaque` is ever deleted (likely once the bridge pass becomes the standard path), this duplication collapses naturally.

- [ ] **Step 5: Add the four new pybind11 bindings**

In `native/src/host/host_bindings.cc`, immediately after the existing `m.def("set_visible", ...)` block:

```cpp
    m.def("create_bridge_instance",
          [](scenegraph::ModelHandle h) {
              auto id = g_world.create_instance(h);
              g_world.set_pass(id, scenegraph::Pass::Bridge);
              return id;
          },
          py::arg("model"),
          "Like create_instance but tags the new instance for the bridge pass.");

    m.def("set_bridge_camera",
          [](std::tuple<float,float,float> eye,
             std::tuple<float,float,float> target,
             std::tuple<float,float,float> up,
             float fov_y_rad, float near_, float far_) {
              g_bridge_camera.eye    = {std::get<0>(eye),    std::get<1>(eye),    std::get<2>(eye)};
              g_bridge_camera.target = {std::get<0>(target), std::get<1>(target), std::get<2>(target)};
              g_bridge_camera.up     = {std::get<0>(up),     std::get<1>(up),     std::get<2>(up)};
              g_bridge_camera.fov_y_rad = fov_y_rad;
              g_bridge_camera.near_  = near_;
              g_bridge_camera.far_   = far_;
          },
          py::arg("eye"), py::arg("target"), py::arg("up"),
          py::arg("fov_y_rad"), py::arg("near"), py::arg("far"),
          "Set the bridge pass camera. No-op until bridge_pass_set_enabled(True).");

    m.def("bridge_pass_set_enabled",
          [](bool enabled) { g_bridge_pass_enabled = enabled; },
          py::arg("enabled"),
          "Enable or disable the bridge render pass.");
```

If the existing `set_camera` binding above uses different argument names (e.g. `near_` vs `near`), match its style for consistency.

- [ ] **Step 6: Build and verify smoke tests pass**

```bash
cmake --build build -j
uv run pytest tests/host/test_bridge_bindings.py -v
```
Expected: all four tests PASS. If the build fails referring to `g_bridge_camera`, double-check the `scenegraph::Camera` struct in `native/src/scenegraph/include/scenegraph/camera.h` — its field names (`eye`, `target`, `up`, `fov_y_rad`, `near_`, `far_`, `aspect`) should match what `g_camera` uses elsewhere in `host_bindings.cc`.

- [ ] **Step 7: Commit**

```bash
git add native/src/host/host_bindings.cc \
        native/src/renderer/include/renderer/frame.h \
        native/src/renderer/frame.cc \
        tests/host/test_bridge_bindings.py
git commit -m "feat(host): bridge pass + bindings (camera, enable, instance)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Cursor lock + mouse-delta accumulator

**Files:**
- Modify: `native/src/renderer/include/renderer/window.h`
- Modify: `native/src/renderer/window.cc`
- Modify: `native/src/host/host_bindings.cc`
- Modify: `tests/host/test_bridge_bindings.py`

Adds GLFW cursor-pos callback wired into accumulators, plus the `set_cursor_locked` binding.

- [ ] **Step 1: Extend the smoke test to cover the two new bindings**

Append to `tests/host/test_bridge_bindings.py`:

```python
def test_consume_mouse_delta_binding_exists(host_module):
    assert hasattr(host_module, "consume_mouse_delta")


def test_set_cursor_locked_binding_exists(host_module):
    assert hasattr(host_module, "set_cursor_locked")
```

Note: we do NOT call these without an init'd window — `consume_mouse_delta` reads from `g_window` and would throw, and `set_cursor_locked` does the same. Existence checks are enough at this layer.

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/host/test_bridge_bindings.py -v
```
Expected: the two new tests FAIL (existing four still pass).

- [ ] **Step 3: Extend `Window` with cursor lock + delta accumulator**

Edit `native/src/renderer/include/renderer/window.h` — add to the public section:

```cpp
    /// Return the accumulated mouse cursor delta since the last call (in
    /// pixels) and reset the accumulator. Updated from the GLFW cursor
    /// callback during poll_events(). Deltas accumulate even when the
    /// cursor is unlocked; consumers gate use by other means.
    void consume_mouse_delta(double* dx, double* dy) noexcept;

    /// Lock or release the cursor. Locked = hidden + warped to centre
    /// each frame so motion produces unbounded raw deltas. Unlocked =
    /// normal cursor visible inside the window.
    void set_cursor_locked(bool locked) noexcept;
```

Add to the private section:

```cpp
    double mouse_dx_accum_ = 0.0;
    double mouse_dy_accum_ = 0.0;
    double last_cursor_x_  = 0.0;
    double last_cursor_y_  = 0.0;
    bool   cursor_seeded_  = false;  // false until first cursor-pos event
```

- [ ] **Step 4: Wire the callback + implement the new methods**

Edit `native/src/renderer/window.cc`. In the `Window` constructor, immediately after the `glfwSetScrollCallback(...)` block:

```cpp
    glfwSetCursorPosCallback(handle_, [](GLFWwindow* w, double x, double y) {
        if (auto* self = static_cast<Window*>(glfwGetWindowUserPointer(w))) {
            if (self->cursor_seeded_) {
                self->mouse_dx_accum_ += x - self->last_cursor_x_;
                self->mouse_dy_accum_ += y - self->last_cursor_y_;
            }
            self->last_cursor_x_ = x;
            self->last_cursor_y_ = y;
            self->cursor_seeded_ = true;
        }
    });
```

Add at the end of the file (before the closing namespace brace):

```cpp
void Window::consume_mouse_delta(double* dx, double* dy) noexcept {
    *dx = mouse_dx_accum_;
    *dy = mouse_dy_accum_;
    mouse_dx_accum_ = 0.0;
    mouse_dy_accum_ = 0.0;
}

void Window::set_cursor_locked(bool locked) noexcept {
    if (!handle_) return;
    glfwSetInputMode(handle_, GLFW_CURSOR,
                     locked ? GLFW_CURSOR_DISABLED : GLFW_CURSOR_NORMAL);
    // Drop the seed so the next cursor-pos event re-anchors and we
    // don't see a giant warp delta on lock-state change.
    cursor_seeded_ = false;
}
```

Also update the move constructor and move assignment operator to copy the four new fields and reset them on the source — mirror the existing handling of `scroll_y_accum_`. Failing to do this would silently corrupt cursor state on a move (which currently never happens but the existing pattern is to maintain symmetry).

- [ ] **Step 5: Add the two pybind11 bindings**

In `native/src/host/host_bindings.cc`, after the `consume_scroll_y` binding:

```cpp
    m.def("consume_mouse_delta",
          []() {
              if (!g_window) {
                  throw std::runtime_error("consume_mouse_delta: init must be called first");
              }
              double dx = 0.0, dy = 0.0;
              g_window->consume_mouse_delta(&dx, &dy);
              return std::make_tuple(dx, dy);
          },
          "Return (dx, dy) accumulated cursor motion in pixels since the last call. "
          "Reset on each call. GLFW raw mode while cursor is locked.");

    m.def("set_cursor_locked",
          [](bool locked) {
              if (!g_window) {
                  throw std::runtime_error("set_cursor_locked: init must be called first");
              }
              g_window->set_cursor_locked(locked);
          },
          py::arg("locked"),
          "Lock the cursor (hidden + raw deltas) or release it.");
```

- [ ] **Step 6: Build and verify smoke tests pass**

```bash
cmake --build build -j
uv run pytest tests/host/test_bridge_bindings.py -v
```
Expected: all six tests PASS.

- [ ] **Step 7: Commit**

```bash
git add native/src/renderer/include/renderer/window.h \
        native/src/renderer/window.cc \
        native/src/host/host_bindings.cc \
        tests/host/test_bridge_bindings.py
git commit -m "feat(host): cursor lock + mouse-delta accumulator bindings

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: `_BridgeCamera` Python class with mouse-look math

**Files:**
- Create: `tests/host/test_bridge_camera.py`
- Modify: `engine/host_loop.py`

Pure Python — fakes for everything. No window, no renderer. Tests run in milliseconds.

- [ ] **Step 1: Write the failing tests**

Create `tests/host/test_bridge_camera.py`:

```python
"""Unit tests for _BridgeCamera — mouse-look first-person camera anchored
at the MissionLib-pinned DBridge captain's-chair pose. Mirrors the fake-
ship pattern from tests/host/test_camera_control.py."""
import math
import pytest


def _identity_ship_at_origin():
    from engine.appc.math import TGPoint3, TGMatrix3
    return TGPoint3(0.0, 0.0, 0.0), TGMatrix3()


def test_bridge_camera_starts_at_zero_yaw_pitch():
    from engine.host_loop import _BridgeCamera
    bc = _BridgeCamera()
    assert bc.yaw_rad   == pytest.approx(0.0)
    assert bc.pitch_rad == pytest.approx(0.0)


def test_mouse_delta_accumulates_yaw_and_pitch():
    """Right-mouse → look-right (negative yaw), up-mouse → look-up
    (positive pitch). Sign convention checked here so future changes
    can't silently flip it."""
    from engine.host_loop import _BridgeCamera
    bc = _BridgeCamera()
    bc.apply(mouse_dx=100.0, mouse_dy=-50.0)
    expected_yaw   = -100.0 * _BridgeCamera.MOUSE_SENSITIVITY
    expected_pitch = -50.0  * _BridgeCamera.MOUSE_SENSITIVITY
    assert bc.yaw_rad   == pytest.approx(expected_yaw)
    assert bc.pitch_rad == pytest.approx(expected_pitch)


def test_pitch_clamps_at_positive_limit():
    from engine.host_loop import _BridgeCamera
    bc = _BridgeCamera()
    # Drive pitch past PITCH_LIMIT_RAD with one big delta.
    bc.apply(mouse_dx=0.0, mouse_dy=10000.0)
    assert bc.pitch_rad == pytest.approx(_BridgeCamera.PITCH_LIMIT_RAD)


def test_pitch_clamps_at_negative_limit():
    from engine.host_loop import _BridgeCamera
    bc = _BridgeCamera()
    bc.apply(mouse_dx=0.0, mouse_dy=-10000.0)
    assert bc.pitch_rad == pytest.approx(-_BridgeCamera.PITCH_LIMIT_RAD)


def test_yaw_wraps_freely_no_clamp():
    from engine.host_loop import _BridgeCamera
    bc = _BridgeCamera()
    # Drive yaw past 2π with one big delta.
    bc.apply(mouse_dx=100000.0, mouse_dy=0.0)
    expected = -100000.0 * _BridgeCamera.MOUSE_SENSITIVITY
    assert bc.yaw_rad == pytest.approx(expected)


def test_camera_anchor_at_ship_origin_with_identity_ship():
    """At zero yaw/pitch, identity ship rotation, ship at origin: eye
    sits at BRIDGE_LOCAL_OFFSET in world coords (no ship rotation
    applied), and target points along the rotated base forward."""
    from engine.host_loop import _BridgeCamera
    bc = _BridgeCamera()
    ship_loc, ship_rot = _identity_ship_at_origin()
    eye, target, up = bc.compute_camera(ship_loc, ship_rot)
    ox, oy, oz = _BridgeCamera.BRIDGE_LOCAL_OFFSET
    assert eye[0] == pytest.approx(ox)
    assert eye[1] == pytest.approx(oy)
    assert eye[2] == pytest.approx(oz)
    # Target is eye + base forward × small distance; we don't pin the
    # exact direction here (that depends on the BRIDGE_BASE_PITCH_RAD
    # convention which iterates visually). What we DO pin: target is
    # not equal to eye (so the view direction is well-defined), and the
    # up vector is unit length.
    assert (eye[0], eye[1], eye[2]) != (target[0], target[1], target[2])
    up_len_sq = up[0]*up[0] + up[1]*up[1] + up[2]*up[2]
    assert up_len_sq == pytest.approx(1.0, abs=1e-6)


def test_camera_couples_to_ship_rotation():
    """Rotating the ship 90° around its Z axis (yaw) rotates the bridge
    camera's eye point by the same 90° in world space — the bridge is
    rigidly attached to the ship."""
    from engine.host_loop import _BridgeCamera
    from engine.appc.math import TGPoint3, TGMatrix3

    bc = _BridgeCamera()

    # Identity ship: eye at BRIDGE_LOCAL_OFFSET.
    ship_loc = TGPoint3(0.0, 0.0, 0.0)
    eye_id, _, _ = bc.compute_camera(ship_loc, TGMatrix3())

    # Yaw the ship 90° about world-Z. In BC row-vector convention, the
    # ship-local +Y axis (forward) maps to world +X.
    Z_AXIS = TGPoint3(0.0, 0.0, 1.0)
    rot90 = TGMatrix3(); rot90.MakeRotation(math.radians(90.0), Z_AXIS)
    eye_rot, _, _ = bc.compute_camera(ship_loc, rot90)

    # Original local offset (ox, oy, oz) under a +90° yaw becomes
    # (-oy, ox, oz) in world space. Use the math defensively:
    ox, oy, oz = _BridgeCamera.BRIDGE_LOCAL_OFFSET
    assert eye_rot[0] == pytest.approx(-oy, abs=1e-4)
    assert eye_rot[1] == pytest.approx( ox, abs=1e-4)
    assert eye_rot[2] == pytest.approx( oz, abs=1e-4)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/host/test_bridge_camera.py -v
```
Expected: all FAIL with `ImportError: cannot import name '_BridgeCamera' from 'engine.host_loop'`.

- [ ] **Step 3: Implement `_BridgeCamera`**

Add to `engine/host_loop.py`, immediately after the `_ViewModeController` class:

```python
class _BridgeCamera:
    """First-person bridge camera with mouse-look.

    Anchored at the MissionLib-pinned DBridge captain's-chair pose
    (sdk/Build/scripts/MissionLib.py:1475-1483) in ship-local frame.
    Mouse motion accumulates yaw (around bridge-up = +Z) and pitch
    (around bridge-right = +X). Yaw wraps freely; pitch clamps at ±85°
    to avoid pole flip.

    Camera world pose = ship_world_rot * (bridge_local_offset rotated
    by base pitch * mouse yaw * mouse pitch) + ship_world_loc, so the
    bridge banks and pitches with the ship as it manoeuvres.
    """

    # MissionLib.py:1475-1483 — DBridge maincamera pose.
    BRIDGE_LOCAL_OFFSET   = (0.0, 50.0, 47.0)
    # Axis-angle (-1.55, 0, 0, 1): -1.55 rad ≈ -88.8° around X axis.
    # Treated as a base pitch rotation; convention iterated visually.
    BRIDGE_BASE_PITCH_RAD = -1.55

    # PoC starting values; tuned by feel during visual verification.
    NEAR              = 1.0
    FAR               = 800.0
    FOV_Y_RAD         = _math.radians(60.0)
    MOUSE_SENSITIVITY = 0.005           # rad per pixel
    PITCH_LIMIT_RAD   = _math.radians(85)

    def __init__(self):
        self.yaw_rad   = 0.0
        self.pitch_rad = 0.0

    def apply(self, mouse_dx: float, mouse_dy: float) -> None:
        """Accumulate mouse delta into yaw/pitch with sign conventions:
        right-mouse (+dx) → look-right (-yaw); up-mouse (-dy in screen
        coords) → look-up (+pitch). Pitch clamps; yaw wraps freely."""
        self.yaw_rad   -= mouse_dx * self.MOUSE_SENSITIVITY
        self.pitch_rad -= mouse_dy * self.MOUSE_SENSITIVITY
        if self.pitch_rad >  self.PITCH_LIMIT_RAD: self.pitch_rad =  self.PITCH_LIMIT_RAD
        if self.pitch_rad < -self.PITCH_LIMIT_RAD: self.pitch_rad = -self.PITCH_LIMIT_RAD

    def compute_camera(self, ship_loc, ship_rot) -> tuple:
        """Return (eye, target, up) as 3-tuples in world space, matching
        the shape r.set_bridge_camera consumes."""
        from engine.appc.math import TGPoint3, TGMatrix3

        X_AXIS = TGPoint3(1.0, 0.0, 0.0)
        Y_AXIS = TGPoint3(0.0, 1.0, 0.0)
        Z_AXIS = TGPoint3(0.0, 0.0, 1.0)

        # 1. Build the bridge-local pose: start with offset, base pitch
        # tilts the camera to face roughly forward along ship-Y.
        ox, oy, oz = self.BRIDGE_LOCAL_OFFSET
        # Local forward starts as +Y, local up as +Z.
        local_fwd = (0.0, 1.0, 0.0)
        local_up  = (0.0, 0.0, 1.0)

        # 2. Rotate forward/up by base pitch (around X), then by mouse
        # yaw (around local Z), then by mouse pitch (around local X).
        def _rot_around(v, axis_xyz, angle_rad):
            """Rotate v=(x,y,z) around the given unit axis."""
            ax, ay, az = axis_xyz
            ca, sa = _math.cos(angle_rad), _math.sin(angle_rad)
            # Rodrigues' rotation formula.
            vx, vy, vz = v
            dot = vx*ax + vy*ay + vz*az
            cross = (ay*vz - az*vy, az*vx - ax*vz, ax*vy - ay*vx)
            return (
                vx*ca + cross[0]*sa + ax*dot*(1.0 - ca),
                vy*ca + cross[1]*sa + ay*dot*(1.0 - ca),
                vz*ca + cross[2]*sa + az*dot*(1.0 - ca),
            )

        local_fwd = _rot_around(local_fwd, (1.0, 0.0, 0.0), self.BRIDGE_BASE_PITCH_RAD)
        local_up  = _rot_around(local_up,  (1.0, 0.0, 0.0), self.BRIDGE_BASE_PITCH_RAD)

        local_fwd = _rot_around(local_fwd, (0.0, 0.0, 1.0), self.yaw_rad)
        local_up  = _rot_around(local_up,  (0.0, 0.0, 1.0), self.yaw_rad)

        # Pitch is around the local right axis (forward × up).
        right = (
            local_fwd[1]*local_up[2] - local_fwd[2]*local_up[1],
            local_fwd[2]*local_up[0] - local_fwd[0]*local_up[2],
            local_fwd[0]*local_up[1] - local_fwd[1]*local_up[0],
        )
        rlen = _math.sqrt(right[0]**2 + right[1]**2 + right[2]**2)
        right = (right[0]/rlen, right[1]/rlen, right[2]/rlen)

        local_fwd = _rot_around(local_fwd, right, self.pitch_rad)
        local_up  = _rot_around(local_up,  right, self.pitch_rad)

        # 3. Transform the local offset and forward/up into world frame
        # using the ship's row-vector basis (rows = body axes in world).
        rgt_world = ship_rot.GetRow(0)
        fwd_world = ship_rot.GetRow(1)
        up_world  = ship_rot.GetRow(2)

        def _to_world(v):
            x, y, z = v
            return (
                x*rgt_world.x + y*fwd_world.x + z*up_world.x,
                x*rgt_world.y + y*fwd_world.y + z*up_world.y,
                x*rgt_world.z + y*fwd_world.z + z*up_world.z,
            )

        offset_world = _to_world((ox, oy, oz))
        fwd_w        = _to_world(local_fwd)
        up_w         = _to_world(local_up)

        eye = (
            ship_loc.x + offset_world[0],
            ship_loc.y + offset_world[1],
            ship_loc.z + offset_world[2],
        )
        target = (
            eye[0] + fwd_w[0],
            eye[1] + fwd_w[1],
            eye[2] + fwd_w[2],
        )
        return eye, target, up_w
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/host/test_bridge_camera.py -v
```
Expected: all seven tests PASS. If `test_camera_anchor_at_ship_origin_with_identity_ship` fails because `eye` doesn't equal `BRIDGE_LOCAL_OFFSET` exactly, it's because the world-frame transform path was triggered and the row-vector convention is being mis-applied — re-check the `_to_world` function against the existing `_extract_ypr` docstring in `engine/host_loop.py`.

- [ ] **Step 5: Commit**

```bash
git add engine/host_loop.py tests/host/test_bridge_camera.py
git commit -m "feat(bridge): _BridgeCamera with mouse-look + ship-coupled frame

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Bridge NIF eager load at host startup

**Files:**
- Modify: `engine/host_loop.py`

Loads `DBridge.nif` once during `run()`'s init block and creates a single bridge instance. No tests at this layer — failure surfaces immediately as a missing-asset error during host startup.

- [ ] **Step 1: Add the bridge load and instance creation**

In `engine/host_loop.py`, find the constants section near the top (around line 40, after the `DEFAULT_PLAYER_SET` constant) and add:

```python
# Bridge geometry (PoC: hardcoded DBridge for all ships).
DBRIDGE_NIF_REL  = "data/Models/Sets/DBridge/DBridge.nif"
DBRIDGE_TEX_REL  = "data/Models/Sets/DBridge"
```

Then in `run()`, find the block where the existing `controller.session = controller.loader.load(mission_name)` line sits (after `HostController` is constructed). Insert the bridge load *before* the session load so the bridge handle is in `controller.nif_to_handle` before any mission-specific work:

```python
        # Bridge interior — eagerly loaded once and reused across mission swaps.
        # Instance lives on the controller, not the per-mission session, so
        # mission teardown doesn't destroy it.
        bridge_nif_abs = str(PROJECT_ROOT / "game" / DBRIDGE_NIF_REL)
        bridge_tex_abs = str(PROJECT_ROOT / "game" / DBRIDGE_TEX_REL)
        bridge_handle  = r.load_model(bridge_nif_abs, bridge_tex_abs)
        controller.nif_to_handle[bridge_nif_abs] = bridge_handle
        controller.bridge_instance = r.create_bridge_instance(bridge_handle)
        # Identity world transform — the bridge pass camera works in
        # bridge-local frame, so the bridge's world position is irrelevant.
        IDENTITY_MAT4 = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        r.set_world_transform(controller.bridge_instance, IDENTITY_MAT4)
```

Also add the `bridge_instance` field to `HostController.__init__`:

```python
    def __init__(self) -> None:
        self.renderer: Any = None
        self.loader: Any = None
        self.nif_to_handle: dict[str, int] = {}
        self.session: Optional[MissionSession] = None
        self.pending_swap: Optional[str] = None
        self.bridge_instance: Optional[Any] = None  # InstanceId from create_bridge_instance
```

- [ ] **Step 2: Smoke-build and run the existing host smoke test**

```bash
cmake --build build -j  # ensure the bindings from Task 2/3 are present
uv run pytest tests/host/test_host_loop_unit.py -v
```
Expected: all five tests PASS. The smoke test exercises `run()` for a few ticks with a hidden window; the new bridge load runs alongside without affecting behaviour because `bridge_pass_set_enabled` is still False.

- [ ] **Step 3: Commit**

```bash
git add engine/host_loop.py
git commit -m "feat(bridge): eager-load DBridge.nif on host startup

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Wire `_BridgeCamera` + cursor lock + bridge_pass into the toggle and per-tick loop

**Files:**
- Modify: `engine/host_loop.py`
- Modify: `tests/host/test_view_mode.py`

This is the integration step that makes the bridge actually appear when you press space. Tests cover the toggle wiring (using a recording fake renderer); per-tick camera computation reuses `_compute_camera` extended for bridge mode.

- [ ] **Step 1: Write the failing tests**

Append to `tests/host/test_view_mode.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/host/test_view_mode.py -v
```
Expected: the three new tests FAIL with `ImportError: cannot import name '_apply_view_mode_side_effects' from 'engine.host_loop'`. The other 8 existing tests still pass.

- [ ] **Step 3: Implement `_apply_view_mode_side_effects`**

In `engine/host_loop.py`, immediately after the `_ViewModeController` class (and after the `_BridgeCamera` class added in Task 4):

```python
def _apply_view_mode_side_effects(view_mode: "_ViewModeController", h) -> None:
    """Mirror the view-mode flag into renderer-side state. Idempotent —
    only fires when the mode has changed since the last call. `h` is
    the bindings module (or fake) exposing bridge_pass_set_enabled and
    set_cursor_locked.
    """
    target = view_mode.is_bridge
    last = getattr(view_mode, "_last_synced_is_bridge", None)
    if last == target:
        return
    h.bridge_pass_set_enabled(target)
    h.set_cursor_locked(target)
    view_mode._last_synced_is_bridge = target
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/host/test_view_mode.py -v
```
Expected: all 11 tests PASS.

- [ ] **Step 5: Wire into `host_loop.run()`**

In `engine/host_loop.py`, inside `run()`'s while loop, find the existing block that constructs `_ViewModeController` (around the Task 6 wiring from the previous PoC). Add the bridge camera alongside:

```python
        view_mode      = _ViewModeController()
        bridge_camera  = _BridgeCamera()
```

Inside the per-tick body, after the existing `view_mode.apply(_h)` poll, add the side-effect sync:

```python
            if _h is not None:
                view_mode.apply(_h)
                _apply_view_mode_side_effects(view_mode, _h)
```

In the camera-compute block, when bridge mode is active, additionally compute + push the bridge camera. Find the block inside `run()`:

```python
            elif player is not None:
                eye, target, up_vec = _compute_camera(
                    view_mode, cam_control,
                    player=player, dt=TICK_DT)
```

And replace it with:

```python
            elif player is not None:
                eye, target, up_vec = _compute_camera(
                    view_mode, cam_control,
                    player=player, dt=TICK_DT)
                if view_mode.is_bridge:
                    mouse_dx, mouse_dy = _h.consume_mouse_delta() if _h else (0.0, 0.0)
                    bridge_camera.apply(mouse_dx, mouse_dy)
                    b_eye, b_target, b_up = bridge_camera.compute_camera(
                        player.GetWorldLocation(), player.GetWorldRotation())
                    r.set_bridge_camera(
                        eye=b_eye, target=b_target, up=b_up,
                        fov_y_rad=_BridgeCamera.FOV_Y_RAD,
                        near=_BridgeCamera.NEAR,
                        far=_BridgeCamera.FAR,
                    )
```

(The space-pass `r.set_camera(...)` call below this block is unchanged — both passes get their cameras pushed each tick.)

- [ ] **Step 6: Run the existing host smoke test to confirm nothing regressed**

```bash
uv run pytest tests/host/test_host_loop_unit.py -v
```
Expected: all five PASS. The smoke test runs in exterior mode by default, so the new bridge-camera path doesn't execute, but the side-effect sync runs and the new wiring must not crash on an init'd renderer.

- [ ] **Step 7: Commit**

```bash
git add engine/host_loop.py tests/host/test_view_mode.py
git commit -m "feat(bridge): wire bridge camera + cursor lock into view-mode toggle

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: ESC handler — exit bridge mode + release cursor

**Files:**
- Modify: `engine/host_loop.py`
- Modify: `tests/host/test_view_mode.py`

The existing ESC handler in `run()` only dismisses the mission picker. Extend it to also exit bridge mode. The mission-picker dismissal stays unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/host/test_view_mode.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/host/test_view_mode.py -v
```
Expected: the two new tests FAIL with `ImportError: cannot import name '_handle_esc_for_view_mode'`.

- [ ] **Step 3: Implement the handler**

In `engine/host_loop.py`, immediately after `_apply_view_mode_side_effects`:

```python
def _handle_esc_for_view_mode(view_mode: "_ViewModeController") -> None:
    """ESC in bridge mode returns to exterior. ESC in exterior mode
    does nothing here (the existing mission-picker handler still gets
    its turn — see run()). The side-effect sync runs on the next tick
    and releases the cursor / disables the bridge pass."""
    if view_mode.is_bridge:
        view_mode.toggle()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/host/test_view_mode.py -v
```
Expected: all 13 tests PASS.

- [ ] **Step 5: Wire into `run()`**

In `engine/host_loop.py`, find the existing ESC block:

```python
            if _h is not None and _h.key_pressed(_h.keys.KEY_ESCAPE):
                picker.handle_key_esc()
```

Replace with:

```python
            if _h is not None and _h.key_pressed(_h.keys.KEY_ESCAPE):
                _handle_esc_for_view_mode(view_mode)
                picker.handle_key_esc()
```

Order matters: handle the view-mode exit *before* the picker dismissal, because if the picker is open and you're in bridge mode, ESC should exit both — bridge first, picker second.

- [ ] **Step 6: Re-run the existing smoke test**

```bash
uv run pytest tests/host/test_host_loop_unit.py -v
```
Expected: all five PASS.

- [ ] **Step 7: Commit**

```bash
git add engine/host_loop.py tests/host/test_view_mode.py
git commit -m "feat(bridge): ESC exits bridge mode in addition to dismissing picker

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Live visual verification

**Files:** None modified. Live build + manual verify.

- [ ] **Step 1: Final clean build**

```bash
cmake --build build -j
```
Expected: clean build, no warnings or errors related to the bridge code.

- [ ] **Step 2: Run the broader regression suite**

```bash
uv run pytest tests/host tests/ui tests/unit tests/test_mission_picker.py
```
Expected: all PASS. (Earlier suites had ~903 passing; this should be ~916+ with the new tests.)

- [ ] **Step 3: Launch the live binary and verify the bridge interactively**

```bash
./build/open_stbc
```

Manually verify the following — if the agent can't drive a window, it must ask the user to perform these steps and report the outcome rather than mark this step done:

1. **Default exterior view unchanged.** Window opens with the third-person ship view. "BRIDGE VIEW" panel is hidden. Cursor is visible in the window.
2. **Existing controls work.** W/A/S/D pitches/yaws the ship. Throttle digits 1–9 / 0 / R work. Arrow keys orbit the camera. F7 toggles dust. C resets orbit. ESC dismisses the (closed) mission picker silently.
3. **Engage engines** (e.g. press `5` for 5/9 impulse). Watch the ship move forward.
4. **Press SPACE.** The view swaps to the bridge interior — DBridge geometry visible, "BRIDGE VIEW" panel showing at top of screen. Cursor disappears. Ship continues coasting forward.
5. **Move the mouse.** The bridge camera looks around (yaw + pitch). Pitch clamps at the upper / lower limits without flipping. Yaw rotates freely 360°.
6. **Press SPACE again.** View returns to exterior orbit, "BRIDGE VIEW" panel hides, cursor reappears, orbit framing matches what it was before entering bridge mode (preserved from the previous PoC).
7. **Press SPACE → mouse-look → press ESC.** Same exit behaviour as step 6: returns to exterior, cursor released, bridge pass disabled.
8. **Press SPACE → bank the ship in exterior mode? wait, controls are disabled in bridge.** Skip — flag if the bridge appears to drift or rotate independently of the ship under any condition.

If anything in steps 1–7 doesn't match: do not mark this step complete. Diagnose the failure (likely candidates: rotation convention for the bridge camera math, GLFW raw-mode quirk on macOS, asset path typo, missing texture search). Add a follow-up task if the fix is non-trivial.

- [ ] **Step 4: Report manual-verification status**

Summarise to the user what was verified live vs what's deferred. If pose iterations are needed (the BRIDGE_BASE_PITCH_RAD axis-angle convention may be wrong), note them as a follow-up.

---

## Done criteria

- All 13 tests in `tests/host/test_view_mode.py` pass (8 from previous PoC + 5 new).
- All 7 tests in `tests/host/test_bridge_camera.py` pass.
- All 6 tests in `tests/host/test_bridge_bindings.py` pass.
- All 4 new gtest cases in `World.*` pass alongside the existing scenegraph tests.
- The full `tests/host tests/ui tests/unit tests/test_mission_picker.py` regression suite is green.
- Pressing SPACE in the live binary swaps to a rendered DBridge interior with mouse-look; pressing SPACE again or ESC returns to the exterior orbit view exactly as before. Engines keep coasting through the toggle (regression test from previous PoC also passes).
- Spec-listed deferred items (D1–D10) remain deferred and untouched.
