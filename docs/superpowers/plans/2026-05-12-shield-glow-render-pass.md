# Shield-Glow Render Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add BC's hit-flash shield effect to the renderer — colored hex-pattern bubble that fades over ~1s on weapon impact, with ellipsoid (default) and hull-inflated "skin" (per-hardpoint opt-in) silhouettes.

**Architecture:** New `native/src/renderer/shield_pass.cc` called between opaque-ship and dust passes, additive-blended. Per-ship `ShieldState` holds an 8-slot ring buffer of active hits decaying over `ShieldGlowDecay` seconds. Two new host bindings (`shield_register`, `shield_hit`) push state from Python; renderer queries no Python data each frame. Sovereign opts into skin mode via a project-root hardpoint shim and a new `SetSkinShielding(1)` convention auto-handled by the Phase 1 `ShieldProperty` data-bag.

**Tech Stack:** C++20, OpenGL 3.3 core, glm, GLSL 330, pybind11, GoogleTest, pytest. Existing patterns mirror `sun_pass.cc` / `dust_pass.cc`.

**Spec:** [docs/superpowers/specs/2026-05-12-shield-glow-render-pass-design.md](../specs/2026-05-12-shield-glow-render-pass-design.md)

---

## File map

**New files (C++):**
- `native/src/renderer/include/renderer/aabb.h` — `Aabb` + `compute_aabb()` from a vertex span
- `native/src/renderer/include/renderer/shield_state.h` — `ShieldState`, `Hit`, `ShieldRegistry`
- `native/src/renderer/shield_state.cc` — implementation
- `native/src/renderer/include/renderer/shield_pass.h` — `ShieldPass` class
- `native/src/renderer/shield_pass.cc` — GL draw + uniform setup
- `native/src/renderer/include/renderer/skin_shield.h` — `build_skin_shield_mesh()`
- `native/src/renderer/skin_shield.cc` — implementation
- `native/src/renderer/shaders/shield.vert`
- `native/src/renderer/shaders/shield.frag`
- `native/tests/renderer/aabb_test.cc`
- `native/tests/renderer/shield_state_test.cc`
- `native/tests/renderer/skin_shield_test.cc`

**New files (Python):**
- `engine/shields.py` — Python glue: `register_ship_shield(instance_id, ship_class_name)`, `fire_debug_hit(instance_id)`
- `tests/unit/test_shield_property_skin.py` — `SetSkinShielding` convention tests
- `tests/unit/test_shields.py` — engine glue tests
- `ships/__init__.py` — empty package marker
- `ships/Hardpoints/__init__.py` — empty package marker
- `ships/Hardpoints/sovereign.py` — copy of SDK file with `SetSkinShielding(1)` added

**Modified files:**
- `native/src/renderer/CMakeLists.txt` — add new sources + embed new shaders
- `native/src/renderer/include/renderer/frame.h` — add `ShieldHit` struct for submission
- `native/src/renderer/frame.cc` — call `shield_pass` after opaque, before dust
- `native/src/renderer/pipeline.cc` — instantiate shield shader
- `native/src/renderer/include/renderer/pipeline.h` — expose shield shader getter
- `native/src/host/host_bindings.cc` — `shield_register`, `shield_hit`, expose `ShieldPass` access
- `native/src/host/host_bindings.h` — forward decls
- `native/tests/CMakeLists.txt` — add `add_subdirectory(renderer)` test list if not present, else add new test files
- `engine/host_loop.py` — call `engine.shields.fire_debug_hit` on F9
- `engine/appc/ships.py` — call `engine.shields.register_ship_shield` after hardpoint import

---

## Phase 1 — C++ foundation (no GL)

### Task 1: AABB extraction utility

**Files:**
- Create: `native/src/renderer/include/renderer/aabb.h`
- Create: `native/tests/renderer/aabb_test.cc`
- Modify: `native/tests/CMakeLists.txt` (or `native/tests/renderer/CMakeLists.txt` if it exists)

- [ ] **Step 1: Write the failing test**

`native/tests/renderer/aabb_test.cc`:
```cpp
#include <gtest/gtest.h>
#include <glm/glm.hpp>
#include "renderer/aabb.h"

TEST(Aabb, ComputesCenterAndHalfExtentsFromVertexPositions) {
    std::vector<glm::vec3> verts = {
        {-1.0f, -2.0f, -3.0f},
        { 4.0f,  6.0f,  9.0f},
        { 0.0f,  0.0f,  0.0f},
    };
    renderer::Aabb box = renderer::compute_aabb(verts);
    EXPECT_FLOAT_EQ(box.center.x, 1.5f);
    EXPECT_FLOAT_EQ(box.center.y, 2.0f);
    EXPECT_FLOAT_EQ(box.center.z, 3.0f);
    EXPECT_FLOAT_EQ(box.half_extents.x, 2.5f);
    EXPECT_FLOAT_EQ(box.half_extents.y, 4.0f);
    EXPECT_FLOAT_EQ(box.half_extents.z, 6.0f);
}

TEST(Aabb, EmptyVertexListReturnsZeroBox) {
    std::vector<glm::vec3> verts;
    renderer::Aabb box = renderer::compute_aabb(verts);
    EXPECT_EQ(box.center, glm::vec3(0.0f));
    EXPECT_EQ(box.half_extents, glm::vec3(0.0f));
}
```

Wire it into the build. Check whether `native/tests/CMakeLists.txt` has an `add_subdirectory(renderer)` line; if not, add one and create `native/tests/renderer/CMakeLists.txt`:
```cmake
add_executable(renderer_tests
    aabb_test.cc
)
target_link_libraries(renderer_tests PRIVATE renderer GTest::gtest_main)
target_include_directories(renderer_tests PRIVATE ${CMAKE_SOURCE_DIR}/native/src)
gtest_discover_tests(renderer_tests)
```

If `add_subdirectory(renderer)` already exists, just append `aabb_test.cc` to the existing `add_executable(renderer_tests ...)` source list there.

- [ ] **Step 2: Run test to verify it fails**

```
cmake -B build -S . && cmake --build build -j --target renderer_tests
```
Expected: build error — `renderer/aabb.h` not found.

- [ ] **Step 3: Write minimal implementation**

`native/src/renderer/include/renderer/aabb.h`:
```cpp
#pragma once

#include <span>
#include <vector>
#include <glm/glm.hpp>

namespace renderer {

struct Aabb {
    glm::vec3 center{0.0f};
    glm::vec3 half_extents{0.0f};
};

Aabb compute_aabb(std::span<const glm::vec3> positions);

inline Aabb compute_aabb(const std::vector<glm::vec3>& v) {
    return compute_aabb(std::span<const glm::vec3>(v));
}

}  // namespace renderer
```

Add `aabb.cc` to `native/src/renderer/CMakeLists.txt` source list. Create `native/src/renderer/aabb.cc`:
```cpp
#include "renderer/aabb.h"
#include <limits>

namespace renderer {

Aabb compute_aabb(std::span<const glm::vec3> positions) {
    if (positions.empty()) return {};
    glm::vec3 lo(std::numeric_limits<float>::max());
    glm::vec3 hi(std::numeric_limits<float>::lowest());
    for (const auto& p : positions) {
        lo = glm::min(lo, p);
        hi = glm::max(hi, p);
    }
    return Aabb{
        .center = 0.5f * (lo + hi),
        .half_extents = 0.5f * (hi - lo),
    };
}

}  // namespace renderer
```

- [ ] **Step 4: Run test to verify it passes**

```
cmake --build build -j --target renderer_tests && ctest --test-dir build -R "Aabb\." --output-on-failure
```
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/include/renderer/aabb.h native/src/renderer/aabb.cc native/src/renderer/CMakeLists.txt native/tests/renderer/aabb_test.cc native/tests/CMakeLists.txt native/tests/renderer/CMakeLists.txt
git commit -m "feat(renderer): AABB extraction from vertex spans"
```

---

### Task 2: ShieldState struct + Hit ring buffer

**Files:**
- Create: `native/src/renderer/include/renderer/shield_state.h`
- Create: `native/src/renderer/shield_state.cc`
- Create: `native/tests/renderer/shield_state_test.cc`
- Modify: `native/src/renderer/CMakeLists.txt`
- Modify: `native/tests/renderer/CMakeLists.txt`

- [ ] **Step 1: Write the failing test**

`native/tests/renderer/shield_state_test.cc`:
```cpp
#include <gtest/gtest.h>
#include "renderer/shield_state.h"

using namespace renderer;

namespace {
ShieldState make_state(float decay = 1.0f) {
    ShieldState s;
    s.mode = ShieldMode::Ellipsoid;
    s.decay_seconds = decay;
    s.default_color = glm::vec4(0.2f, 0.4f, 1.0f, 1.0f);
    s.aabb_center = glm::vec3(0.0f);
    s.aabb_half_extents = glm::vec3(10.0f);
    return s;
}
}

TEST(ShieldState, PushHitStoresColorAndPoint) {
    auto s = make_state();
    s.push_hit({1.0f, 2.0f, 3.0f}, {0.5f, 0.6f, 0.7f, 1.0f}, 1.0f, 0.0, 2);
    EXPECT_EQ(s.active_count(), 1);
    EXPECT_EQ(s.slot(0).point_world, glm::vec3(1.0f, 2.0f, 3.0f));
    EXPECT_FLOAT_EQ(s.slot(0).color_rgba.r, 0.5f);
    EXPECT_EQ(s.slot(0).texture_index, 2);
}

TEST(ShieldState, ZeroRgbaSubstitutesDefaultColor) {
    auto s = make_state();
    s.push_hit({0,0,0}, {0,0,0,0}, 1.0f, 0.0, 0);
    EXPECT_EQ(s.slot(0).color_rgba, s.default_color);
}

TEST(ShieldState, IntensityDecaysExponentiallyWithDecaySeconds) {
    auto s = make_state(/*decay=*/2.0f);
    s.push_hit({0,0,0}, {1,1,1,1}, 1.0f, 0.0, 0);
    s.tick(/*now=*/2.0);  // one decay period
    EXPECT_NEAR(s.slot(0).current_intensity, std::exp(-1.0f), 1e-5);
}

TEST(ShieldState, ExpiredSlotsBecomeEmpty) {
    auto s = make_state(/*decay=*/0.1f);
    s.push_hit({0,0,0}, {1,1,1,1}, 1.0f, 0.0, 0);
    s.tick(/*now=*/10.0);  // far past decay
    EXPECT_EQ(s.active_count(), 0);
}

TEST(ShieldState, FullBufferEvictsDimmestHit) {
    auto s = make_state(/*decay=*/100.0f);
    for (int i = 0; i < 8; ++i) {
        s.push_hit({float(i),0,0}, {1,1,1,1}, 1.0f, double(i) * 0.001, 0);
    }
    // 9th hit should evict the dimmest. Since decay is large, t=0 is dimmest
    // (it's been decaying longest); evict slot 0.
    s.tick(/*now=*/0.01);
    s.push_hit({99,0,0}, {1,1,1,1}, 1.0f, 0.01, 0);
    EXPECT_EQ(s.active_count(), 8);
    // None of the active slots should be at x=0 anymore.
    for (int i = 0; i < 8; ++i) {
        if (s.slot(i).current_intensity > 0.01f) {
            EXPECT_NE(s.slot(i).point_world.x, 0.0f);
        }
    }
}

TEST(ShieldState, TextureIndexStableAcrossTicks) {
    auto s = make_state();
    s.push_hit({0,0,0}, {1,1,1,1}, 1.0f, 0.0, 3);
    int idx_before = s.slot(0).texture_index;
    s.tick(/*now=*/0.5);
    EXPECT_EQ(s.slot(0).texture_index, idx_before);
}
```

Append `shield_state_test.cc` to `renderer_tests` sources in `native/tests/renderer/CMakeLists.txt`.

- [ ] **Step 2: Run test to verify it fails**

```
cmake --build build -j --target renderer_tests
```
Expected: build error — `renderer/shield_state.h` not found.

- [ ] **Step 3: Write minimal implementation**

`native/src/renderer/include/renderer/shield_state.h`:
```cpp
#pragma once

#include <array>
#include <cstdint>
#include <glm/glm.hpp>

namespace renderer {

enum class ShieldMode : std::uint8_t { Ellipsoid, Skin };

struct Hit {
    glm::vec3 point_world{0.0f};
    glm::vec4 color_rgba{0.0f};
    float intensity_at_t0 = 0.0f;
    float current_intensity = 0.0f;
    double t0_seconds = 0.0;
    int texture_index = 0;
};

class ShieldState {
public:
    static constexpr std::size_t MaxHits = 8;

    ShieldMode mode = ShieldMode::Ellipsoid;
    float decay_seconds = 1.0f;
    glm::vec4 default_color{1.0f};
    glm::vec3 aabb_center{0.0f};
    glm::vec3 aabb_half_extents{0.0f};

    void push_hit(const glm::vec3& point_world,
                  const glm::vec4& rgba,
                  float intensity,
                  double now_seconds,
                  int texture_index);

    /// Recompute current_intensity for every slot at `now_seconds`. Expired
    /// slots (intensity < 0.01) become inactive.
    void tick(double now_seconds);

    std::size_t active_count() const noexcept;
    const Hit& slot(std::size_t i) const noexcept { return hits_[i]; }

private:
    std::array<Hit, MaxHits> hits_{};
};

}  // namespace renderer
```

`native/src/renderer/shield_state.cc`:
```cpp
#include "renderer/shield_state.h"
#include <cmath>

namespace renderer {

namespace {
constexpr float kInactive = 0.01f;
}

void ShieldState::push_hit(const glm::vec3& point_world,
                           const glm::vec4& rgba,
                           float intensity,
                           double now_seconds,
                           int texture_index) {
    // Find first empty slot, else dimmest.
    std::size_t target = 0;
    float min_intensity = hits_[0].current_intensity;
    for (std::size_t i = 0; i < MaxHits; ++i) {
        if (hits_[i].current_intensity < kInactive) { target = i; min_intensity = 0.0f; break; }
        if (hits_[i].current_intensity < min_intensity) {
            min_intensity = hits_[i].current_intensity;
            target = i;
        }
    }
    glm::vec4 color = (rgba == glm::vec4(0.0f)) ? default_color : rgba;
    hits_[target] = Hit{
        .point_world = point_world,
        .color_rgba = color,
        .intensity_at_t0 = intensity,
        .current_intensity = intensity,
        .t0_seconds = now_seconds,
        .texture_index = texture_index,
    };
}

void ShieldState::tick(double now_seconds) {
    for (auto& h : hits_) {
        if (h.intensity_at_t0 <= 0.0f) continue;
        float dt = static_cast<float>(now_seconds - h.t0_seconds);
        h.current_intensity = h.intensity_at_t0 * std::exp(-dt / decay_seconds);
        if (h.current_intensity < kInactive) {
            h.current_intensity = 0.0f;
            h.intensity_at_t0 = 0.0f;
        }
    }
}

std::size_t ShieldState::active_count() const noexcept {
    std::size_t n = 0;
    for (const auto& h : hits_) if (h.current_intensity >= kInactive) ++n;
    return n;
}

}  // namespace renderer
```

- [ ] **Step 4: Run test to verify it passes**

```
cmake --build build -j --target renderer_tests && ctest --test-dir build -R "ShieldState\." --output-on-failure
```
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/include/renderer/shield_state.h native/src/renderer/shield_state.cc native/src/renderer/CMakeLists.txt native/tests/renderer/shield_state_test.cc native/tests/renderer/CMakeLists.txt
git commit -m "feat(renderer): ShieldState ring buffer with exp decay"
```

---

### Task 3: ShieldRegistry — per-instance state lookup

**Files:**
- Modify: `native/src/renderer/include/renderer/shield_state.h`
- Modify: `native/src/renderer/shield_state.cc`
- Modify: `native/tests/renderer/shield_state_test.cc`

- [ ] **Step 1: Write the failing test**

Append to `native/tests/renderer/shield_state_test.cc`:
```cpp
#include "scenegraph/instance.h"

TEST(ShieldRegistry, RegisterCreatesStateForInstance) {
    ShieldRegistry reg;
    scenegraph::InstanceId id{42};
    reg.register_instance(id, ShieldMode::Skin, 2.0f,
                          glm::vec4(0.1f, 0.2f, 0.3f, 1.0f),
                          glm::vec3(0.0f), glm::vec3(5.0f));
    auto* s = reg.find(id);
    ASSERT_NE(s, nullptr);
    EXPECT_EQ(s->mode, ShieldMode::Skin);
    EXPECT_FLOAT_EQ(s->decay_seconds, 2.0f);
}

TEST(ShieldRegistry, FindReturnsNullForUnknownInstance) {
    ShieldRegistry reg;
    EXPECT_EQ(reg.find(scenegraph::InstanceId{999}), nullptr);
}

TEST(ShieldRegistry, PushHitDropsSilentlyForUnknownInstance) {
    ShieldRegistry reg;
    // Must not crash, must not throw.
    reg.push_hit(scenegraph::InstanceId{999}, {0,0,0}, {1,1,1,1}, 1.0f, 0.0);
    SUCCEED();
}

TEST(ShieldRegistry, PushHitRoutesToCorrectInstance) {
    ShieldRegistry reg;
    scenegraph::InstanceId a{1}, b{2};
    reg.register_instance(a, ShieldMode::Ellipsoid, 1.0f, glm::vec4(1,0,0,1), {}, glm::vec3(1));
    reg.register_instance(b, ShieldMode::Ellipsoid, 1.0f, glm::vec4(0,1,0,1), {}, glm::vec3(1));
    reg.push_hit(a, {1,1,1}, {0,0,0,0}, 1.0f, 0.0);  // 0-rgba → default for A = red
    EXPECT_EQ(reg.find(a)->slot(0).color_rgba, glm::vec4(1,0,0,1));
    EXPECT_EQ(reg.find(b)->active_count(), 0);
}

TEST(ShieldRegistry, UnregisterRemovesState) {
    ShieldRegistry reg;
    scenegraph::InstanceId id{7};
    reg.register_instance(id, ShieldMode::Ellipsoid, 1.0f, glm::vec4(1), {}, glm::vec3(1));
    reg.unregister_instance(id);
    EXPECT_EQ(reg.find(id), nullptr);
}
```

- [ ] **Step 2: Run test to verify it fails**

```
cmake --build build -j --target renderer_tests
```
Expected: build error — `ShieldRegistry` undefined.

- [ ] **Step 3: Write minimal implementation**

Append to `native/src/renderer/include/renderer/shield_state.h` (before namespace close):
```cpp
}  // namespace renderer

#include <unordered_map>
#include "scenegraph/instance.h"

namespace std {
template<> struct hash<scenegraph::InstanceId> {
    std::size_t operator()(const scenegraph::InstanceId& id) const noexcept {
        return std::hash<std::uint32_t>{}(id.value);
    }
};
}

namespace renderer {

class ShieldRegistry {
public:
    void register_instance(scenegraph::InstanceId id,
                           ShieldMode mode,
                           float decay_seconds,
                           const glm::vec4& default_color,
                           const glm::vec3& aabb_center,
                           const glm::vec3& aabb_half_extents);

    void unregister_instance(scenegraph::InstanceId id);

    /// Returns nullptr if instance is not registered.
    ShieldState* find(scenegraph::InstanceId id);
    const ShieldState* find(scenegraph::InstanceId id) const;

    void push_hit(scenegraph::InstanceId id,
                  const glm::vec3& point_world,
                  const glm::vec4& rgba,
                  float intensity,
                  double now_seconds);

    /// Tick every registered state.
    void tick_all(double now_seconds);

    auto begin() const { return states_.begin(); }
    auto end() const { return states_.end(); }

private:
    std::unordered_map<scenegraph::InstanceId, ShieldState> states_;
};

}  // namespace renderer
```

(Note: if `InstanceId` doesn't already have a `value` field, check [native/src/scenegraph/include/scenegraph/instance.h](../../native/src/scenegraph/include/scenegraph/instance.h) and adjust the hash to match the actual field name.)

Append to `native/src/renderer/shield_state.cc`:
```cpp
void ShieldRegistry::register_instance(scenegraph::InstanceId id,
                                       ShieldMode mode,
                                       float decay_seconds,
                                       const glm::vec4& default_color,
                                       const glm::vec3& aabb_center,
                                       const glm::vec3& aabb_half_extents) {
    auto& s = states_[id];
    s.mode = mode;
    s.decay_seconds = decay_seconds;
    s.default_color = default_color;
    s.aabb_center = aabb_center;
    s.aabb_half_extents = aabb_half_extents;
}

void ShieldRegistry::unregister_instance(scenegraph::InstanceId id) {
    states_.erase(id);
}

ShieldState* ShieldRegistry::find(scenegraph::InstanceId id) {
    auto it = states_.find(id);
    return it == states_.end() ? nullptr : &it->second;
}
const ShieldState* ShieldRegistry::find(scenegraph::InstanceId id) const {
    auto it = states_.find(id);
    return it == states_.end() ? nullptr : &it->second;
}

void ShieldRegistry::push_hit(scenegraph::InstanceId id,
                               const glm::vec3& point_world,
                               const glm::vec4& rgba,
                               float intensity,
                               double now_seconds) {
    auto* s = find(id);
    if (!s) return;
    // texture_index picked from a thread-local stateless rng to keep ticks deterministic.
    static thread_local std::uint32_t rng = 0x12345678u;
    rng = rng * 1664525u + 1013904223u;
    int tex = static_cast<int>(rng >> 30);  // 0..3
    s->push_hit(point_world, rgba, intensity, now_seconds, tex);
}

void ShieldRegistry::tick_all(double now_seconds) {
    for (auto& [id, s] : states_) s.tick(now_seconds);
}
```

Link the renderer test target against the `scenegraph` library — in `native/tests/renderer/CMakeLists.txt`:
```cmake
target_link_libraries(renderer_tests PRIVATE renderer scenegraph GTest::gtest_main)
```

- [ ] **Step 4: Run test to verify it passes**

```
cmake --build build -j --target renderer_tests && ctest --test-dir build -R "ShieldRegistry\." --output-on-failure
```
Expected: 5 tests pass; 6 prior `ShieldState` tests still pass.

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/include/renderer/shield_state.h native/src/renderer/shield_state.cc native/tests/renderer/shield_state_test.cc native/tests/renderer/CMakeLists.txt
git commit -m "feat(renderer): ShieldRegistry routes hits by InstanceId"
```

---

### Task 4: Skin-mesh inflate utility

**Files:**
- Create: `native/src/renderer/include/renderer/skin_shield.h`
- Create: `native/src/renderer/skin_shield.cc`
- Create: `native/tests/renderer/skin_shield_test.cc`
- Modify: `native/src/renderer/CMakeLists.txt`, `native/tests/renderer/CMakeLists.txt`

- [ ] **Step 1: Write the failing test**

`native/tests/renderer/skin_shield_test.cc`:
```cpp
#include <gtest/gtest.h>
#include <glm/glm.hpp>
#include "renderer/skin_shield.h"

using namespace renderer;

TEST(SkinShield, InflatesPositionsAlongNormalsByDistance) {
    std::vector<glm::vec3> positions = {
        {0, 0, 0},
        {1, 0, 0},
        {0, 1, 0},
    };
    std::vector<glm::vec3> normals = {
        {0, 0, 1},
        {1, 0, 0},
        {0, 1, 0},
    };
    auto inflated = build_skin_shield_positions(positions, normals, /*distance=*/0.5f);
    ASSERT_EQ(inflated.size(), 3u);
    EXPECT_EQ(inflated[0], glm::vec3(0, 0, 0.5f));
    EXPECT_EQ(inflated[1], glm::vec3(1.5f, 0, 0));
    EXPECT_EQ(inflated[2], glm::vec3(0, 1.5f, 0));
}

TEST(SkinShield, NormalsShorterThanPositionsThrows) {
    std::vector<glm::vec3> positions = {{0,0,0}, {1,0,0}};
    std::vector<glm::vec3> normals = {{0,0,1}};
    EXPECT_THROW(build_skin_shield_positions(positions, normals, 0.5f),
                 std::invalid_argument);
}

TEST(SkinShield, ZeroDistanceReturnsPositionsUnchanged) {
    std::vector<glm::vec3> positions = {{1,2,3}, {4,5,6}};
    std::vector<glm::vec3> normals = {{0,0,1}, {1,0,0}};
    auto out = build_skin_shield_positions(positions, normals, 0.0f);
    EXPECT_EQ(out[0], positions[0]);
    EXPECT_EQ(out[1], positions[1]);
}
```

Append `skin_shield_test.cc` to `native/tests/renderer/CMakeLists.txt`.

- [ ] **Step 2: Run test to verify it fails**

```
cmake --build build -j --target renderer_tests
```
Expected: build error — `renderer/skin_shield.h` not found.

- [ ] **Step 3: Write minimal implementation**

`native/src/renderer/include/renderer/skin_shield.h`:
```cpp
#pragma once

#include <span>
#include <vector>
#include <stdexcept>
#include <glm/glm.hpp>

namespace renderer {

/// Returns hull positions pushed outward along their normals by `distance`.
/// Topology (indices) is unchanged — the caller reuses the hull index buffer.
std::vector<glm::vec3> build_skin_shield_positions(
    std::span<const glm::vec3> positions,
    std::span<const glm::vec3> normals,
    float distance);

inline std::vector<glm::vec3> build_skin_shield_positions(
    const std::vector<glm::vec3>& positions,
    const std::vector<glm::vec3>& normals,
    float distance) {
    return build_skin_shield_positions(
        std::span<const glm::vec3>(positions),
        std::span<const glm::vec3>(normals),
        distance);
}

}  // namespace renderer
```

`native/src/renderer/skin_shield.cc`:
```cpp
#include "renderer/skin_shield.h"

namespace renderer {

std::vector<glm::vec3> build_skin_shield_positions(
    std::span<const glm::vec3> positions,
    std::span<const glm::vec3> normals,
    float distance) {
    if (normals.size() < positions.size()) {
        throw std::invalid_argument(
            "build_skin_shield_positions: normals.size() < positions.size()");
    }
    std::vector<glm::vec3> out;
    out.reserve(positions.size());
    for (std::size_t i = 0; i < positions.size(); ++i) {
        out.push_back(positions[i] + normals[i] * distance);
    }
    return out;
}

}  // namespace renderer
```

Add `skin_shield.cc` to `native/src/renderer/CMakeLists.txt`.

- [ ] **Step 4: Run test to verify it passes**

```
cmake --build build -j --target renderer_tests && ctest --test-dir build -R "SkinShield\." --output-on-failure
```
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/include/renderer/skin_shield.h native/src/renderer/skin_shield.cc native/src/renderer/CMakeLists.txt native/tests/renderer/skin_shield_test.cc native/tests/renderer/CMakeLists.txt
git commit -m "feat(renderer): skin-shield mesh inflate along normals"
```

---

## Phase 2 — Ellipsoid render pass + bindings + F9 debug

### Task 5: Shield shaders

**Files:**
- Create: `native/src/renderer/shaders/shield.vert`
- Create: `native/src/renderer/shaders/shield.frag`
- Modify: `native/src/renderer/CMakeLists.txt` — add `embed_shader(... shield_vs)` + `shield_fs`

- [ ] **Step 1: Write `shield.vert`**

`native/src/renderer/shaders/shield.vert`:
```glsl
#version 330 core

layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;

uniform mat4 u_view_proj;
uniform mat4 u_world;       // ship_world transform
uniform mat4 u_ship_local;  // identity for skin path, scale*translate for ellipsoid

out vec3 v_world_pos;
out vec3 v_ship_local_pos;
out vec3 v_ship_local_normal;

void main() {
    vec4 lp = u_ship_local * vec4(a_position, 1.0);
    v_ship_local_pos = lp.xyz;
    v_ship_local_normal = mat3(u_ship_local) * a_normal;
    vec4 wp = u_world * lp;
    v_world_pos = wp.xyz;
    gl_Position = u_view_proj * wp;
}
```

- [ ] **Step 2: Write `shield.frag`**

`native/src/renderer/shaders/shield.frag`:
```glsl
#version 330 core

const int MAX_HITS = 8;

in vec3 v_world_pos;
in vec3 v_ship_local_pos;
in vec3 v_ship_local_normal;

uniform vec4 u_hit_points[MAX_HITS];      // xyz = world pt, w = unused
uniform vec4 u_hit_color_intensity[MAX_HITS]; // rgb = color, a = current_intensity
uniform int u_hit_tex_index[MAX_HITS];    // 0..3
uniform float u_hit_radius;
uniform float u_hex_tile_rate;            // hexes per ship-local unit (= per world meter @ 1:1)

uniform sampler2D u_shieldhit_0;
uniform sampler2D u_shieldhit_1;
uniform sampler2D u_shieldhit_2;
uniform sampler2D u_shieldhit_3;

out vec4 frag_color;

vec4 sample_tex(int idx, vec2 uv) {
    if      (idx == 0) return texture(u_shieldhit_0, uv);
    else if (idx == 1) return texture(u_shieldhit_1, uv);
    else if (idx == 2) return texture(u_shieldhit_2, uv);
    else               return texture(u_shieldhit_3, uv);
}

vec2 triplanar_uv(vec3 p, vec3 n) {
    vec3 w = abs(normalize(n));
    vec2 uv_x = p.yz;
    vec2 uv_y = p.xz;
    vec2 uv_z = p.xy;
    // blend the three by axis weights; pick max-axis projection for simplicity.
    if (w.x >= w.y && w.x >= w.z) return uv_x;
    if (w.y >= w.z)               return uv_y;
    return uv_z;
}

void main() {
    vec3 color = vec3(0.0);
    float alpha = 0.0;
    vec2 uv = triplanar_uv(v_ship_local_pos * u_hex_tile_rate, v_ship_local_normal);
    for (int i = 0; i < MAX_HITS; ++i) {
        float inten = u_hit_color_intensity[i].a;
        if (inten < 0.01) continue;
        float d = distance(v_world_pos, u_hit_points[i].xyz);
        float falloff = 1.0 - smoothstep(0.0, u_hit_radius, d);
        if (falloff <= 0.0) continue;
        vec4 hex = sample_tex(u_hit_tex_index[i], uv);
        color += u_hit_color_intensity[i].rgb * inten * falloff * hex.rgb;
        alpha += hex.a * inten * falloff;
    }
    if (alpha < 0.001) discard;
    frag_color = vec4(color, alpha);
}
```

- [ ] **Step 3: Embed shaders**

In `native/src/renderer/CMakeLists.txt`, add next to the existing embed lines:
```cmake
embed_shader(SHADER_SHIELD_VS shaders/shield.vert shield_vs)
embed_shader(SHADER_SHIELD_FS shaders/shield.frag shield_fs)
```

- [ ] **Step 4: Build to verify shaders embed cleanly**

```
cmake --build build -j --target dauntless
```
Expected: build succeeds. (The headers `embedded_shield_vs.h` / `embedded_shield_fs.h` are generated; they aren't yet referenced by any .cc, so they need no consumer at this step.)

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/shaders/shield.vert native/src/renderer/shaders/shield.frag native/src/renderer/CMakeLists.txt
git commit -m "feat(renderer): shield-hit shader (vert + frag, embedded)"
```

---

### Task 6: ShieldPass class + pipeline integration

**Files:**
- Create: `native/src/renderer/include/renderer/shield_pass.h`
- Create: `native/src/renderer/shield_pass.cc`
- Modify: `native/src/renderer/include/renderer/pipeline.h` — add `shield()` accessor
- Modify: `native/src/renderer/pipeline.cc` — create the shader
- Modify: `native/src/renderer/CMakeLists.txt` — add `shield_pass.cc`

- [ ] **Step 1: Declare `ShieldPass`**

`native/src/renderer/include/renderer/shield_pass.h`:
```cpp
#pragma once

#include <memory>
#include <glm/glm.hpp>

#include "renderer/shield_state.h"

namespace assets { struct Model; }
namespace scenegraph { class World; struct Camera; }

namespace renderer {

class Shader;
class Texture;
class SphereMesh;

class ShieldPass {
public:
    ShieldPass();
    ~ShieldPass();

    /// Push a hit. Resolves color, picks ring-buffer slot.
    void shield_hit(scenegraph::InstanceId id,
                    const glm::vec3& point_world,
                    const glm::vec4& rgba,
                    float intensity);

    void register_ship(scenegraph::InstanceId id,
                       ShieldMode mode,
                       float decay_seconds,
                       const glm::vec4& default_color,
                       const glm::vec3& aabb_center,
                       const glm::vec3& aabb_half_extents);

    void unregister_ship(scenegraph::InstanceId id);

    /// Draw all active flashes. Caller sets up viewport + camera state.
    void submit(const scenegraph::World& world,
                const scenegraph::Camera& camera,
                Shader& shield_shader,
                double now_seconds);

private:
    ShieldRegistry registry_;
    std::unique_ptr<SphereMesh> sphere_;
    // Shieldhit textures shieldhit01..04.TGA loaded on first use.
    std::unique_ptr<Texture> tex_[4];
    bool tex_loaded_ = false;

    void ensure_textures_loaded();
};

}  // namespace renderer
```

- [ ] **Step 2: Implement (no draw yet — just bookkeeping)**

`native/src/renderer/shield_pass.cc`:
```cpp
#include "renderer/shield_pass.h"

#include <glad/glad.h>

#include "renderer/shader.cc"  // ensure correct include for Shader
#include "renderer/sphere_mesh.h"
#include "scenegraph/world.h"

namespace renderer {

ShieldPass::ShieldPass()
    : sphere_(std::make_unique<SphereMesh>(/*segments=*/24, /*rings=*/12)) {}

ShieldPass::~ShieldPass() = default;

void ShieldPass::shield_hit(scenegraph::InstanceId id,
                            const glm::vec3& point_world,
                            const glm::vec4& rgba,
                            float intensity) {
    // Get a monotonic now from world (or pass it in). For now, use 0.0 — the
    // host loop will provide a proper clock via submit's now_seconds and the
    // ring buffer's intensity_at_t0 carries forward correctly.
    registry_.push_hit(id, point_world, rgba, intensity, /*now=*/0.0);
}

void ShieldPass::register_ship(scenegraph::InstanceId id,
                                ShieldMode mode,
                                float decay_seconds,
                                const glm::vec4& default_color,
                                const glm::vec3& aabb_center,
                                const glm::vec3& aabb_half_extents) {
    registry_.register_instance(id, mode, decay_seconds, default_color,
                                aabb_center, aabb_half_extents);
}

void ShieldPass::unregister_ship(scenegraph::InstanceId id) {
    registry_.unregister_instance(id);
}

void ShieldPass::submit(const scenegraph::World&,
                        const scenegraph::Camera&,
                        Shader&,
                        double now_seconds) {
    registry_.tick_all(now_seconds);
    // Draw path lands in Task 8.
}

void ShieldPass::ensure_textures_loaded() {
    if (tex_loaded_) return;
    // Texture loading lands in Task 8.
    tex_loaded_ = true;
}

}  // namespace renderer
```

(Note: review whether the `include "renderer/shader.cc"` line is needed — the existing pattern in `sun_pass.cc` will show the right header to include. Use `renderer/shader.h` if that exists; otherwise mirror sun_pass's include.)

- [ ] **Step 3: Wire pipeline**

Modify `native/src/renderer/pipeline.cc`:
```cpp
#include "embedded_shield_vs.h"
#include "embedded_shield_fs.h"
// ...
Pipeline::Pipeline() {
    opaque_ = std::make_unique<Shader>(shader_src::opaque_vs, shader_src::opaque_fs);
    backdrop_ = std::make_unique<Shader>(shader_src::backdrop_vs, shader_src::backdrop_fs);
    sun_ = std::make_unique<Shader>(shader_src::sun_vs, shader_src::sun_fs);
    dust_ = std::make_unique<Shader>(shader_src::dust_vs, shader_src::dust_fs);
    shield_ = std::make_unique<Shader>(shader_src::shield_vs, shader_src::shield_fs);
    glEnable(GL_DEPTH_TEST);
    // ... (existing body)
}
```

Add `shield_` field + `shield()` accessor in `pipeline.h` matching the existing pattern for `sun()` / `dust()`.

- [ ] **Step 4: Build**

```
cmake --build build -j --target dauntless
```
Expected: build succeeds, no test breakage. (Renderer test suite hasn't changed.)

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/include/renderer/shield_pass.h native/src/renderer/shield_pass.cc native/src/renderer/pipeline.cc native/src/renderer/include/renderer/pipeline.h native/src/renderer/CMakeLists.txt
git commit -m "feat(renderer): ShieldPass skeleton + pipeline shader slot"
```

---

### Task 7: Wire `submit_shield` into the frame call order

**Files:**
- Modify: `native/src/renderer/include/renderer/frame.h` — add `submit_shield`
- Modify: `native/src/renderer/frame.cc` — implement, call after opaque, before dust

- [ ] **Step 1: Read existing frame call sequence**

Inspect `native/src/renderer/frame.cc` to identify the line ordering: opaque → dust → backdrop → sun. Shield must run after opaque, before dust (additive on top of ships; dust + backdrop composite over shields). Find the host-loop call site (`host_loop.py` calls `host.frame(...)`) and note which `FrameSubmitter` method orchestrates the pass order.

- [ ] **Step 2: Add `submit_shield` to FrameSubmitter**

In `native/src/renderer/include/renderer/frame.h`, add a method on `FrameSubmitter`:
```cpp
void submit_shield(const scenegraph::World& world,
                   const scenegraph::Camera& camera,
                   Pipeline& pipeline,
                   ShieldPass& shield,
                   double now_seconds);
```

Forward-declare `ShieldPass` at top of `frame.h`:
```cpp
namespace renderer { class ShieldPass; }
```

- [ ] **Step 3: Implement `submit_shield` in frame.cc**

```cpp
void FrameSubmitter::submit_shield(const scenegraph::World& world,
                                   const scenegraph::Camera& camera,
                                   Pipeline& pipeline,
                                   ShieldPass& shield,
                                   double now_seconds) {
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE);  // alpha-weighted additive
    glDepthMask(GL_FALSE);
    shield.submit(world, camera, pipeline.shield(), now_seconds);
    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);
}
```

Locate the host frame orchestrator (likely `host_bindings.cc` near `m.def("frame", ...)`) and insert the call between the opaque pass and the dust pass.

- [ ] **Step 4: Build**

```
cmake --build build -j --target dauntless
```
Expected: build succeeds. Running `./build/dauntless` should still render normally — shield pass does nothing visible yet because `ShieldPass::submit` only ticks.

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/include/renderer/frame.h native/src/renderer/frame.cc native/src/host/host_bindings.cc
git commit -m "feat(renderer): wire shield pass into frame after opaque"
```

---

### Task 8: Ellipsoid draw path + texture loading

**Files:**
- Modify: `native/src/renderer/shield_pass.cc` — implement draw
- Verify: textures `game/data/Textures/Tactical/shieldhit01.TGA` ... `04.TGA` exist

- [ ] **Step 1: Confirm texture files**

```
ls game/data/Textures/Tactical/shieldhit0*.TGA
```
Expected: `shieldhit01.TGA shieldhit02.TGA shieldhit03.TGA shieldhit04.TGA`.

- [ ] **Step 2: Implement texture loading**

Find how existing passes load textures (mirror `sun_pass.cc` or `dust_pass.cc` Texture-loading pattern). In `shield_pass.cc`:
```cpp
void ShieldPass::ensure_textures_loaded() {
    if (tex_loaded_) return;
    for (int i = 0; i < 4; ++i) {
        char path[256];
        std::snprintf(path, sizeof(path),
                      "game/data/Textures/Tactical/shieldhit0%d.TGA", i + 1);
        tex_[i] = std::make_unique<Texture>(path);
    }
    tex_loaded_ = true;
}
```

(Adjust to match the actual Texture ctor signature in the codebase.)

- [ ] **Step 3: Implement draw in `submit`**

Replace the body of `ShieldPass::submit`:
```cpp
void ShieldPass::submit(const scenegraph::World& world,
                        const scenegraph::Camera& camera,
                        Shader& shield_shader,
                        double now_seconds) {
    registry_.tick_all(now_seconds);
    ensure_textures_loaded();

    shield_shader.use();
    shield_shader.set_mat4("u_view_proj", camera.view_proj());

    glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, tex_[0]->id());
    glActiveTexture(GL_TEXTURE1); glBindTexture(GL_TEXTURE_2D, tex_[1]->id());
    glActiveTexture(GL_TEXTURE2); glBindTexture(GL_TEXTURE_2D, tex_[2]->id());
    glActiveTexture(GL_TEXTURE3); glBindTexture(GL_TEXTURE_2D, tex_[3]->id());
    shield_shader.set_int("u_shieldhit_0", 0);
    shield_shader.set_int("u_shieldhit_1", 1);
    shield_shader.set_int("u_shieldhit_2", 2);
    shield_shader.set_int("u_shieldhit_3", 3);
    shield_shader.set_float("u_hex_tile_rate", 1.0f / 5.0f);

    for (auto& [id, state] : registry_) {
        if (state.active_count() == 0) continue;
        if (state.mode != ShieldMode::Ellipsoid) continue;  // skin path in Phase 4

        const auto* instance = world.get(id);
        if (!instance) continue;
        glm::mat4 ship_world = instance->world_transform;  // adjust per real field name

        glm::mat4 ship_local = glm::translate(glm::mat4(1.0f), state.aabb_center)
                              * glm::scale(glm::mat4(1.0f), state.aabb_half_extents * 1.1f);
        shield_shader.set_mat4("u_world", ship_world);
        shield_shader.set_mat4("u_ship_local", ship_local);

        // Pack hit uniforms.
        glm::vec4 pts[ShieldState::MaxHits];
        glm::vec4 col[ShieldState::MaxHits];
        int       tex[ShieldState::MaxHits];
        for (std::size_t i = 0; i < ShieldState::MaxHits; ++i) {
            const auto& h = state.slot(i);
            pts[i] = glm::vec4(h.point_world, 0.0f);
            col[i] = glm::vec4(glm::vec3(h.color_rgba), h.current_intensity);
            tex[i] = h.texture_index;
        }
        shield_shader.set_vec4_array("u_hit_points", pts, ShieldState::MaxHits);
        shield_shader.set_vec4_array("u_hit_color_intensity", col, ShieldState::MaxHits);
        shield_shader.set_int_array("u_hit_tex_index", tex, ShieldState::MaxHits);

        float hit_radius = std::max({state.aabb_half_extents.x,
                                     state.aabb_half_extents.y,
                                     state.aabb_half_extents.z}) * 0.25f;
        shield_shader.set_float("u_hit_radius", hit_radius);

        sphere_->draw();
    }
}
```

If `Shader` doesn't have `set_vec4_array` / `set_int_array` helpers, add them (mirror existing `set_mat4` / `set_int`). Add to `shader.h` + `shader.cc`:
```cpp
void set_vec4_array(const char* name, const glm::vec4* values, std::size_t count) {
    glUniform4fv(glGetUniformLocation(id_, name),
                 static_cast<GLsizei>(count),
                 reinterpret_cast<const GLfloat*>(values));
}
void set_int_array(const char* name, const int* values, std::size_t count) {
    glUniform1iv(glGetUniformLocation(id_, name),
                 static_cast<GLsizei>(count), values);
}
```

- [ ] **Step 4: Build, launch, verify (manual)**

```
cmake --build build -j --target dauntless
./build/dauntless
```
Expected: scene renders unchanged because no hits have been pushed yet. No crashes. No new console warnings. We will exercise the visual path via F9 in Task 10.

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/shield_pass.cc native/src/renderer/include/renderer/shader.h native/src/renderer/shader.cc
git commit -m "feat(renderer): ellipsoid shield draw + texture loading"
```

---

### Task 9: Host bindings for shield_register and shield_hit

**Files:**
- Modify: `native/src/host/host_bindings.cc` — expose `ShieldPass` access; add `shield_register`, `shield_hit`
- Modify: `native/src/host/host_main.cc` — ensure `ShieldPass` instance lives on host state

- [ ] **Step 1: Add ShieldPass to host state**

Find where existing render state lives (probably `host_main.cc` or a host context struct). Add a `std::unique_ptr<renderer::ShieldPass> shield_pass_;` member alongside the existing pipeline / submitter. Construct it during init.

- [ ] **Step 2: Wire `submit_shield` into the frame call**

Locate the frame function (`m.def("frame", &frame, ...)` in `host_bindings.cc` → `frame` defined in `host_main.cc`). Between the opaque-pass call and the dust-pass call, add:
```cpp
double now_seconds = glfwGetTime();  // or whichever monotonic source the host uses
submitter_.submit_shield(world_, camera_, *pipeline_, *shield_pass_, now_seconds);
```

- [ ] **Step 3: Add `shield_register` binding**

In `host_bindings.cc`, in the `PYBIND11_MODULE` block, near the existing `set_lighting` / `set_camera` definitions:
```cpp
m.def("shield_register",
      [](int instance_id_raw, int mode_int, float decay,
         py::tuple default_color, py::tuple aabb_center, py::tuple aabb_half_extents) {
          auto id = scenegraph::InstanceId{static_cast<std::uint32_t>(instance_id_raw)};
          auto mode = static_cast<renderer::ShieldMode>(mode_int);
          glm::vec4 dc(default_color[0].cast<float>(), default_color[1].cast<float>(),
                       default_color[2].cast<float>(), default_color[3].cast<float>());
          glm::vec3 ac(aabb_center[0].cast<float>(), aabb_center[1].cast<float>(),
                       aabb_center[2].cast<float>());
          glm::vec3 ah(aabb_half_extents[0].cast<float>(), aabb_half_extents[1].cast<float>(),
                       aabb_half_extents[2].cast<float>());
          shield_pass_->register_ship(id, mode, decay, dc, ac, ah);
      },
      py::arg("instance_id"), py::arg("mode"), py::arg("decay_seconds"),
      py::arg("default_color"), py::arg("aabb_center"), py::arg("aabb_half_extents"));
```

- [ ] **Step 4: Add `shield_hit` binding**

```cpp
m.def("shield_hit",
      [](int instance_id_raw, py::tuple point, py::tuple rgba, float intensity) {
          auto id = scenegraph::InstanceId{static_cast<std::uint32_t>(instance_id_raw)};
          glm::vec3 p(point[0].cast<float>(), point[1].cast<float>(), point[2].cast<float>());
          glm::vec4 c(rgba[0].cast<float>(), rgba[1].cast<float>(),
                      rgba[2].cast<float>(), rgba[3].cast<float>());
          shield_pass_->shield_hit(id, p, c, intensity);
      },
      py::arg("instance_id"), py::arg("point"), py::arg("rgba"),
      py::arg("intensity") = 1.0f);
```

- [ ] **Step 5: Build**

```
cmake --build build -j
```
Expected: build succeeds, all existing tests still pass:
```
ctest --test-dir build --output-on-failure
```

- [ ] **Step 6: Commit**

```bash
git add native/src/host/host_bindings.cc native/src/host/host_main.cc
git commit -m "feat(host): expose shield_register and shield_hit bindings"
```

---

### Task 10: F9 debug binding + Python glue stub

**Files:**
- Create: `engine/shields.py`
- Create: `tests/unit/test_shields.py`
- Modify: `engine/host_loop.py` — call shields module on F9

- [ ] **Step 1: Write failing Python tests**

`tests/unit/test_shields.py`:
```python
"""Engine glue for shield-hit pushes.

The renderer-side state lives in C++. This module owns the small bit of Python
state needed to compose host.shield_register / host.shield_hit calls when
Python doesn't have a real connection to the renderer (unit tests, harness).
"""
from unittest.mock import MagicMock


def test_fire_debug_hit_sends_to_host():
    import engine.shields as s
    host = MagicMock()
    host.shield_hit = MagicMock()
    s.fire_debug_hit(host, instance_id=42, world_point=(1.0, 2.0, 3.0))
    host.shield_hit.assert_called_once()
    args, kwargs = host.shield_hit.call_args
    # Accept either positional or kw; just verify the four required fields land.
    call_args = dict(zip(("instance_id", "point", "rgba", "intensity"), args))
    call_args.update(kwargs)
    assert call_args["instance_id"] == 42
    assert tuple(call_args["point"]) == (1.0, 2.0, 3.0)
    assert tuple(call_args["rgba"]) == (0.0, 0.0, 0.0, 0.0)  # 0 = use ship default
    assert call_args["intensity"] == 1.0


def test_register_ship_shield_skips_if_no_shield_property():
    import engine.shields as s
    host = MagicMock()
    host.shield_register = MagicMock()
    # A ship instance with no ShieldProperty in its subsystems
    class FakeShip:
        subsystems = []
    s.register_ship_shield(host, instance_id=1, ship=FakeShip(),
                           aabb_center=(0,0,0), aabb_half_extents=(1,1,1))
    host.shield_register.assert_not_called()


def test_register_ship_shield_reads_skin_flag_and_color():
    import engine.shields as s
    from engine.appc.properties import ShieldProperty
    host = MagicMock()
    host.shield_register = MagicMock()

    shield_prop = ShieldProperty("Shield Generator")
    shield_prop.SetShieldGlowColor(_color(0.2, 0.4, 1.0, 1.0))
    shield_prop.SetShieldGlowDecay(2.0)
    shield_prop.SetSkinShielding(1)

    class FakeShip:
        subsystems = [shield_prop]

    s.register_ship_shield(host, instance_id=7, ship=FakeShip(),
                           aabb_center=(0,1,0), aabb_half_extents=(10,5,30))
    host.shield_register.assert_called_once()
    call = host.shield_register.call_args
    kwargs = call.kwargs
    if not kwargs:
        # Was called positionally; extract by argname order
        positional = call.args
        kwargs = dict(zip(
            ["instance_id","mode","decay_seconds","default_color","aabb_center","aabb_half_extents"],
            positional))
    assert kwargs["instance_id"] == 7
    assert kwargs["mode"] == 1  # SKIN
    assert kwargs["decay_seconds"] == 2.0
    assert tuple(kwargs["default_color"]) == (0.2, 0.4, 1.0, 1.0)
    assert tuple(kwargs["aabb_center"]) == (0,1,0)
    assert tuple(kwargs["aabb_half_extents"]) == (10,5,30)


def _color(r, g, b, a):
    import App
    c = App.TGColorA(); c.SetRGBA(r, g, b, a); return c
```

- [ ] **Step 2: Run tests, expect failure**

```
uv run pytest tests/unit/test_shields.py -v
```
Expected: ImportError on `engine.shields`.

- [ ] **Step 3: Implement `engine/shields.py`**

```python
"""Glue between Python ship state and C++ shield renderer.

The renderer holds the per-instance ShieldState; we just translate property
shim values into host.shield_register / host.shield_hit calls."""
import App
from engine.appc.properties import ShieldProperty

SHIELD_MODE_ELLIPSOID = 0
SHIELD_MODE_SKIN = 1


def _find_shield_property(ship):
    for sub in getattr(ship, "subsystems", []):
        if isinstance(sub, ShieldProperty):
            return sub
    return None


def _color_tuple(prop, key, default=(1.0, 1.0, 1.0, 1.0)):
    val = prop._data.get((key, ()))
    if val is None:
        return default
    if isinstance(val, App.TGColorA):
        return (val.r, val.g, val.b, val.a)
    return default


def register_ship_shield(host, instance_id, ship,
                         aabb_center, aabb_half_extents):
    prop = _find_shield_property(ship)
    if prop is None:
        return
    skin = prop._data.get(("SkinShielding", ()), 0)
    mode = SHIELD_MODE_SKIN if skin else SHIELD_MODE_ELLIPSOID
    decay = prop._data.get(("ShieldGlowDecay", ()), 1.0)
    color = _color_tuple(prop, "ShieldGlowColor")
    host.shield_register(
        instance_id=instance_id, mode=mode, decay_seconds=float(decay),
        default_color=color,
        aabb_center=tuple(aabb_center),
        aabb_half_extents=tuple(aabb_half_extents),
    )


def fire_debug_hit(host, instance_id, world_point):
    """Push a synthetic hit at world_point. Color (0,0,0,0) signals the
    renderer to use the ship's default ShieldGlowColor."""
    host.shield_hit(
        instance_id=instance_id,
        point=tuple(world_point),
        rgba=(0.0, 0.0, 0.0, 0.0),
        intensity=1.0,
    )
```

- [ ] **Step 4: Run tests, expect pass**

```
uv run pytest tests/unit/test_shields.py -v
```
Expected: 3 tests pass.

- [ ] **Step 5: Wire F9 into host_loop.py**

In `engine/host_loop.py`, find the existing F-key polling near line 165 (`if h.key_pressed(h.keys.KEY_R):`). Add an F9 branch that pushes a debug hit at the player ship's world position:
```python
if h.key_pressed(h.keys.KEY_F9):
    from engine.shields import fire_debug_hit
    # Use the player's instance id (where the harness stores it depends on
    # the existing code path; check how the player ship's instance id is
    # currently tracked in host_loop.py).
    pid = self.player_instance_id  # adjust to actual field
    ppos = self.player_world_pos    # adjust to actual field
    if pid is not None and ppos is not None:
        fire_debug_hit(h, instance_id=pid, world_point=ppos)
```

(Adjust field names to whatever the existing host_loop uses — likely there's a `current_player_ship` or similar; check the existing F-key handlers like the one at line 165 for reference.)

- [ ] **Step 6: Run full suite**

```
uv run pytest tests/unit/ tests/integration/ -q
```
Expected: all green.

- [ ] **Step 7: Manual visual check**

```
./build/dauntless
```
Expected: scene renders; press F9 a few times → ellipsoid hex flash appears around the player ship, fading over ~1 s. Rapid presses → brighter, overlapping flashes. (Won't yet honor `ShieldGlowColor` for any specific ship until the registration glue is wired into ship creation, which is Task 13. For now the hit uses default white.)

- [ ] **Step 8: Commit**

```bash
git add engine/shields.py tests/unit/test_shields.py engine/host_loop.py
git commit -m "feat(shields): F9 debug-hit + engine.shields glue module"
```

---

## Phase 3 — Sovereign shim + SetSkinShielding

### Task 11: `SetSkinShielding` Python tests

**Files:**
- Create: `tests/unit/test_shield_property_skin.py`

- [ ] **Step 1: Write the failing test**

```python
"""Convention: ShieldProperty.SetSkinShielding(1) opts a ship into hull-
inflated shield rendering. Auto-handled by the Phase 1 data-bag at
engine/appc/properties.py:24-46 — no new code needed in the shim."""
from engine.appc.properties import ShieldProperty


def test_set_skin_shielding_stores_value_in_databag():
    shield = ShieldProperty("Shield Generator")
    shield.SetSkinShielding(1)
    assert shield._data[("SkinShielding", ())] == 1


def test_default_no_skin_shielding_key():
    shield = ShieldProperty("Shield Generator")
    assert shield._data.get(("SkinShielding", ())) is None


def test_set_skin_shielding_zero_stores_zero():
    shield = ShieldProperty("Shield Generator")
    shield.SetSkinShielding(0)
    assert shield._data[("SkinShielding", ())] == 0
```

- [ ] **Step 2: Run test**

```
uv run pytest tests/unit/test_shield_property_skin.py -v
```
Expected: 3 tests pass immediately (the data-bag handles `Set*` automatically — this test pins the convention).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_shield_property_skin.py
git commit -m "test(shields): pin SetSkinShielding databag convention"
```

---

### Task 12: Sovereign hardpoint shim

**Files:**
- Create: `ships/__init__.py` (empty)
- Create: `ships/Hardpoints/__init__.py` (empty)
- Create: `ships/Hardpoints/sovereign.py` (copy of SDK, modified)

- [ ] **Step 1: Verify sovereign exists in SDK**

```
ls sdk/Build/scripts/ships/Hardpoints/sovereign.py
```
Expected: file exists.

- [ ] **Step 2: Create package markers**

```bash
mkdir -p ships/Hardpoints
: > ships/__init__.py
: > ships/Hardpoints/__init__.py
```

- [ ] **Step 3: Copy SDK file and add SetSkinShielding(1)**

```bash
cp sdk/Build/scripts/ships/Hardpoints/sovereign.py ships/Hardpoints/sovereign.py
```

Then open `ships/Hardpoints/sovereign.py`, find the `ShieldGenerator.SetShieldGlowColor(...)` line, and immediately below it add:
```python
ShieldGenerator.SetSkinShielding(1)
```

- [ ] **Step 4: Write a verification test**

`tests/unit/test_shield_property_skin.py` — append:
```python
def test_sovereign_hardpoint_opts_into_skin_shielding(monkeypatch):
    """Importing the sovereign hardpoint should result in SkinShielding=1 on
    its ShieldGenerator. This indirectly verifies that the project-root
    ships/Hardpoints/sovereign.py shadows the SDK copy via _SDKFinder."""
    import sys, importlib
    # Force fresh import
    for k in list(sys.modules):
        if k.startswith("ships.Hardpoints.sovereign") or k == "ships.Hardpoints":
            del sys.modules[k]
    mod = importlib.import_module("ships.Hardpoints.sovereign")
    # The hardpoint module sets globals; locate ShieldGenerator
    sg = getattr(mod, "ShieldGenerator")
    assert sg._data.get(("SkinShielding", ())) == 1
```

- [ ] **Step 5: Run tests**

```
uv run pytest tests/unit/test_shield_property_skin.py -v
```
Expected: all 4 tests pass. If the sovereign test fails with `ModuleNotFoundError`, ensure `tests/conftest.py`'s `_SDKFinder` (or equivalent) is on the meta_path before pytest collects — this matches the existing pattern for `LoadBridge.py`.

- [ ] **Step 6: Commit**

```bash
git add ships/__init__.py ships/Hardpoints/__init__.py ships/Hardpoints/sovereign.py tests/unit/test_shield_property_skin.py
git commit -m "feat(ships): sovereign opts into skin-shielding via root-shim hardpoint"
```

---

### Task 13: Wire `register_ship_shield` into ship creation

**Files:**
- Modify: `engine/appc/ships.py` — after hardpoint import completes, call `register_ship_shield`

- [ ] **Step 1: Survey the existing creation path**

Run these and note the file:line of the create-instance call site and AABB plumbing:
```
grep -rn "create_instance" engine/ native/src/host/ | grep -v __pycache__
grep -rn "aabb\|AABB" native/src/host/ native/src/scenegraph/
```
Identify (a) the Python function that imports the hardpoint module + calls `host.create_instance` (likely `engine/appc/ships.py::_load_ship_via_loadspacehelper` or wherever `loadspacehelper.CreateShip` lands), and (b) whether the AABB is already exposed Python-side. Note both findings in scratch.

- [ ] **Step 2: Add `host.model_aabb` binding if AABB isn't exposed**

If AABB isn't already on the Python side, add it. In `native/src/host/host_bindings.cc`:
```cpp
m.def("model_aabb",
      [](int model_handle_raw) -> py::tuple {
          auto handle = assets::ModelHandle{static_cast<std::uint32_t>(model_handle_raw)};
          const auto* model = model_registry_.get(handle);  // adjust to actual registry name
          if (!model) return py::make_tuple(py::make_tuple(0,0,0), py::make_tuple(0,0,0));
          std::vector<glm::vec3> pts;
          pts.reserve(model->hull_mesh.vertices.size());
          for (const auto& v : model->hull_mesh.vertices) pts.push_back(v.position);
          auto box = renderer::compute_aabb(pts);
          return py::make_tuple(
              py::make_tuple(box.center.x, box.center.y, box.center.z),
              py::make_tuple(box.half_extents.x, box.half_extents.y, box.half_extents.z));
      },
      py::arg("model_handle"));
```

(Adjust `model_registry_` and field names to the real host state.)

- [ ] **Step 3: Write the failing test**

`tests/unit/test_shields.py` — append:
```python
def test_register_ship_shield_called_after_create_instance(monkeypatch):
    """When engine.appc.ships creates a ship instance, it must call
    register_ship_shield with the host's AABB for that ship."""
    import engine.shields as shields
    import engine.appc.ships as ships_module

    register_calls = []
    monkeypatch.setattr(
        shields, "register_ship_shield",
        lambda *args, **kwargs: register_calls.append((args, kwargs))
    )

    # Use a fake host that returns a predictable model handle + AABB.
    fake_host = MagicMock()
    fake_host.create_instance.return_value = 100  # instance_id
    fake_host.model_aabb.return_value = ((0.0, 1.0, 0.0), (10.0, 5.0, 30.0))

    # Pick the simplest non-shielded ship the test infrastructure can build.
    # Look at tests/unit/test_ships.py for the canonical ship construction
    # pattern in headless tests; mirror it here. The key assertion is just
    # that register_ship_shield ran with the AABB the host returned.
    ship = ships_module.ShipClass_Create("Akira", host=fake_host)

    assert len(register_calls) == 1
    args, kwargs = register_calls[0]
    call = {**dict(zip(("host","instance_id","ship","aabb_center","aabb_half_extents"), args)), **kwargs}
    assert call["instance_id"] == 100
    assert tuple(call["aabb_center"]) == (0.0, 1.0, 0.0)
    assert tuple(call["aabb_half_extents"]) == (10.0, 5.0, 30.0)
```

If `ShipClass_Create` doesn't accept a `host` parameter today, the test will fail at the call site — that's expected; either thread the host through, or use whatever creation entry point already has access to the host.

- [ ] **Step 4: Run test, expect failure**

```
uv run pytest tests/unit/test_shields.py::test_register_ship_shield_called_after_create_instance -v
```
Expected: fail — `register_ship_shield` is not called from ship creation yet, or the host parameter is missing.

- [ ] **Step 5: Implement the wiring**

In `engine/appc/ships.py`, find the function that calls `host.create_instance` (identified in Step 1). After it succeeds, before returning the ship object, add:
```python
from engine.shields import register_ship_shield
center, half_extents = host.model_aabb(model_handle)
register_ship_shield(host=host, instance_id=instance_id, ship=ship,
                     aabb_center=center, aabb_half_extents=half_extents)
```

- [ ] **Step 6: Run all tests**

```
uv run pytest tests/unit/ tests/integration/ -q
```
Expected: all green.

- [ ] **Step 7: Manual check**

```
./build/dauntless
```
F9 → flash now uses the player ship's ShieldGlowColor (Federation blue for Galaxy, etc.).

- [ ] **Step 8: Commit**

```bash
git add engine/appc/ships.py tests/unit/test_shields.py native/src/host/host_bindings.cc
git commit -m "feat(shields): register every loaded ship with the shield pass"
```

---

## Phase 4 — Skin-mesh path

### Task 14: NIF skin-mesh cache

**Files:**
- Create: `native/src/renderer/include/renderer/skin_mesh_cache.h`
- Create: `native/src/renderer/skin_mesh_cache.cc`
- Modify: `native/src/renderer/shield_pass.cc` — own a cache, use it in draw
- Create: `native/tests/renderer/skin_mesh_cache_test.cc`

- [ ] **Step 1: Read the assets::Mesh + ModelHandle shape**

Before writing the test, inspect:
- [native/src/assets/include/assets/mesh.h](../../native/src/assets/include/assets/mesh.h) — note the exact `Vertex` field names (likely `position`, `normal`, but verify).
- The `ModelHandle` type used by `FrameSubmitter::ModelLookup` (search `grep -rn ModelHandle native/src/`). Verify whether it's a `struct { uint32_t value; }` or a typedef.

Adjust the test fixture below to use the real names if they differ.

- [ ] **Step 2: Write failing test**

`native/tests/renderer/skin_mesh_cache_test.cc`:
```cpp
#include <gtest/gtest.h>
#include "renderer/skin_mesh_cache.h"
#include "assets/mesh.h"

namespace {
assets::Mesh make_triangle_hull() {
    assets::Mesh m;
    m.vertices.push_back({.position = {0.0f, 0.0f, 0.0f}, .normal = {0.0f, 0.0f, 1.0f}});
    m.vertices.push_back({.position = {1.0f, 0.0f, 0.0f}, .normal = {0.0f, 0.0f, 1.0f}});
    m.vertices.push_back({.position = {0.0f, 1.0f, 0.0f}, .normal = {0.0f, 0.0f, 1.0f}});
    m.indices = {0, 1, 2};
    return m;
}
}

TEST(SkinMeshCache, BuildsOncePerModelHandle) {
    renderer::SkinMeshCache cache;
    auto hull = make_triangle_hull();
    assets::ModelHandle handle{42};
    int build_calls = 0;
    auto* first  = cache.get_or_build(handle, hull, /*inflate=*/0.5f, [&]{ ++build_calls; });
    auto* second = cache.get_or_build(handle, hull, /*inflate=*/0.5f, [&]{ ++build_calls; });
    EXPECT_EQ(first, second);
    EXPECT_EQ(build_calls, 1);
}

TEST(SkinMeshCache, InflatesPositionsOnBuild) {
    renderer::SkinMeshCache cache;
    auto hull = make_triangle_hull();
    auto* m = cache.get_or_build(assets::ModelHandle{1}, hull, 0.5f);
    ASSERT_EQ(m->positions.size(), 3u);
    EXPECT_EQ(m->positions[0], glm::vec3(0.0f, 0.0f, 0.5f));  // pushed along +Z
    EXPECT_EQ(m->indices, std::vector<std::uint32_t>({0, 1, 2}));
}
```

If `Vertex` uses different field names, swap `.position`/`.normal` accordingly. If `ModelHandle` is a plain integer alias, replace `assets::ModelHandle{42}` with the equivalent.

- [ ] **Step 3: Run, expect failure**

```
cmake --build build -j --target renderer_tests
```
Expected: build error.

- [ ] **Step 4: Implement cache**

`native/src/renderer/include/renderer/skin_mesh_cache.h`:
```cpp
#pragma once

#include <unordered_map>
#include <vector>
#include <functional>
#include <glm/glm.hpp>
#include "assets/model_handle.h"  // adjust to real include for ModelHandle

namespace assets { struct Mesh; }

namespace renderer {

struct SkinMesh {
    std::vector<glm::vec3> positions;
    std::vector<glm::vec3> normals;
    std::vector<std::uint32_t> indices;
    // GL handles created on first use, owned here:
    unsigned int vao = 0;
    unsigned int vbo_pos = 0;
    unsigned int vbo_nrm = 0;
    unsigned int ibo = 0;
};

class SkinMeshCache {
public:
    SkinMesh* get_or_build(assets::ModelHandle handle,
                           const assets::Mesh& hull,
                           float inflate_distance,
                           std::function<void()> on_build = {});
private:
    std::unordered_map<std::uint64_t, SkinMesh> by_handle_;
};

}  // namespace renderer
```

`native/src/renderer/skin_mesh_cache.cc`:
```cpp
#include "renderer/skin_mesh_cache.h"
#include "renderer/skin_shield.h"
#include "assets/mesh.h"

namespace renderer {

SkinMesh* SkinMeshCache::get_or_build(assets::ModelHandle handle,
                                       const assets::Mesh& hull,
                                       float inflate_distance,
                                       std::function<void()> on_build) {
    auto it = by_handle_.find(handle.value);
    if (it != by_handle_.end()) return &it->second;
    SkinMesh m;
    // Extract hull positions + normals from hull.vertices (adjust to real
    // Vertex field names; existing pattern lives in assets/mesh.h).
    std::vector<glm::vec3> pos, nrm;
    pos.reserve(hull.vertices.size());
    nrm.reserve(hull.vertices.size());
    for (const auto& v : hull.vertices) {
        pos.push_back(v.position);
        nrm.push_back(v.normal);
    }
    m.positions = build_skin_shield_positions(pos, nrm, inflate_distance);
    m.normals = std::move(nrm);
    m.indices = hull.indices;  // share topology
    if (on_build) on_build();
    return &by_handle_.emplace(handle.value, std::move(m)).first->second;
}

}  // namespace renderer
```

GL upload happens lazily in `shield_pass.cc` when the skin mesh is first drawn (or do it eagerly here — pick one and document). Add the GL upload in shield_pass right before drawing.

- [ ] **Step 5: Run test**

```
cmake --build build -j --target renderer_tests && ctest --test-dir build -R "SkinMeshCache" --output-on-failure
```
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add native/src/renderer/include/renderer/skin_mesh_cache.h native/src/renderer/skin_mesh_cache.cc native/tests/renderer/skin_mesh_cache_test.cc native/src/renderer/CMakeLists.txt native/tests/renderer/CMakeLists.txt
git commit -m "feat(renderer): skin-mesh cache keyed by ModelHandle"
```

---

### Task 15: Mode dispatch in shield_pass

**Files:**
- Modify: `native/src/renderer/shield_pass.cc` — branch on `state.mode`
- Modify: `native/src/renderer/shield_pass.h` — own a `SkinMeshCache`, accept `assets::Model` lookup
- Modify: host wiring (`host_main.cc` / `host_bindings.cc`) — pass model lookup into submit

- [ ] **Step 1: Add model lookup to submit signature**

```cpp
void submit(const scenegraph::World& world,
            const scenegraph::Camera& camera,
            Shader& shield_shader,
            double now_seconds,
            const std::function<const assets::Model*(scenegraph::InstanceId)>& model_for_instance);
```

- [ ] **Step 2: Branch on mode**

In `shield_pass.cc` submit:
```cpp
for (auto& [id, state] : registry_) {
    if (state.active_count() == 0) continue;
    glm::mat4 ship_world = /* ... as before */;
    glm::mat4 ship_local;
    GLsizei index_count = 0;
    unsigned int vao = 0;

    if (state.mode == ShieldMode::Ellipsoid) {
        ship_local = glm::translate(glm::mat4(1.0f), state.aabb_center)
                   * glm::scale(glm::mat4(1.0f), state.aabb_half_extents * 1.1f);
        vao = sphere_->vao();
        index_count = sphere_->index_count();
    } else {  // Skin
        const auto* model = model_for_instance(id);
        if (!model) continue;
        float inflate = std::max({state.aabb_half_extents.x,
                                  state.aabb_half_extents.y,
                                  state.aabb_half_extents.z}) * 0.05f;
        auto* skin = skin_cache_.get_or_build(model->handle, model->hull_mesh, inflate);
        ensure_skin_uploaded(*skin);
        vao = skin->vao;
        index_count = static_cast<GLsizei>(skin->indices.size());
        ship_local = glm::mat4(1.0f);  // already in ship-local space
    }

    shield_shader.set_mat4("u_world", ship_world);
    shield_shader.set_mat4("u_ship_local", ship_local);
    // ... hit uniforms as before ...
    glBindVertexArray(vao);
    glDrawElements(GL_TRIANGLES, index_count, GL_UNSIGNED_INT, nullptr);
}
```

Add `ensure_skin_uploaded(SkinMesh&)` helper that, on first draw of a skin mesh, creates VAO/VBO/IBO and uploads positions/normals/indices.

- [ ] **Step 3: Update host site**

The host passes a model lookup. Reuse the existing `ModelLookup` pattern from `FrameSubmitter::submit_opaque` (see [frame.h:55](../../native/src/renderer/include/renderer/frame.h#L55)).

- [ ] **Step 4: Build**

```
cmake --build build -j
```

- [ ] **Step 5: Manual check**

```
./build/dauntless
```
Load a mission where sovereign is the player ship (or spawn one). F9 → hex flash now silhouettes the hull. F9 on a non-sovereign ship still shows ellipsoid.

If the sovereign isn't reachable from default mission boot, temporarily set the harness to load sovereign as the player ship, capture a screenshot, then revert. Note in the commit message that visual verification was done via that ad-hoc harness change.

- [ ] **Step 6: Commit**

```bash
git add native/src/renderer/shield_pass.cc native/src/renderer/include/renderer/shield_pass.h native/src/host/host_main.cc native/src/host/host_bindings.cc
git commit -m "feat(renderer): skin-mesh dispatch — sovereign shields hug the hull"
```

---

### Task 16: Cleanup + final regression sweep

**Files:**
- Modify: anywhere TODO/FIXME comments accumulated during phases
- Run: full test suite, full harness, manual visual check

- [ ] **Step 1: Sweep for placeholder TODOs**

```
git diff main -- native/ engine/ tests/ | grep -i "TODO\|FIXME\|XXX"
```
Expected: empty. Resolve any lingering items.

- [ ] **Step 2: Full Python test suite**

```
uv run pytest tests/unit/ tests/integration/ -q
```
Expected: all green.

- [ ] **Step 3: Full C++ test suite**

```
ctest --test-dir build --output-on-failure
```
Expected: all green.

- [ ] **Step 4: Gameloop harness regression**

```
uv run python tools/gameloop_harness.py --ticks 120 --profile
```
Expected: same pass count as the baseline before this work. The `ShieldProperty.SetShieldGlowColor` line in the consumer report is no longer "consumed only at the Phase 1 data-bag" — it's now also driving `host.shield_register`.

- [ ] **Step 5: Manual visual checklist**

`./build/dauntless`:
- [ ] Galaxy (player default): F9 → ellipsoid bubble flash sized roughly to ship AABB, fades over ~1 s, color = Federation blue from hardpoint.
- [ ] Sovereign (load via ad-hoc test setup): F9 → hull-conforming flash silhouette, color from sovereign hardpoint.
- [ ] Rapid F9 (5 presses in 1 s): overlapping flashes brighten additively, each fades independently.
- [ ] Two ships visible: each shows its own flash on its own bubble; no cross-bleed.
- [ ] No console errors, no fps regression vs baseline.

- [ ] **Step 6: Final commit**

```bash
git commit --allow-empty -m "chore(shields): end-of-feature regression sweep"
```

Or, if cleanups happened in step 1: include them in this final commit.

---

## Out of scope (do not implement)

These are intentionally deferred per the spec:
- Damage-system integration (real impact points from weapon hits) — F9 is the only ingress until the damage system lands.
- Persistent low-shield warning bubble.
- Shield depletion fade (alpha modulated by shield strength).
- Tactical-view shield outline.
- Per-quadrant shields. `SetMaxShields(direction, value)` is stored but unused by the render pass.
- Beam render pass (phaser, tractor) — separate spec/plan, next round.

## Open questions

None blocking. Tunables (`hex_tile_rate`, `hit_radius` multiplier, `inflate_distance` multiplier, decay default) are settled by feel during phase 2 visual verification.
