# RmlUi HUD Overlay — Design Spec

**Date:** 2026-05-10
**Status:** Approved

## Summary

Introduce [RmlUi](https://github.com/mikke89/RmlUi) as the UI framework for open_stbc. The initial deliverable is a simple debug/status HUD overlay in the top-right corner of the renderer window showing the player ship's position, rotation (yaw/pitch/roll), current system (set name), and current ship name.

This is the **foundation for the game UI**, not a throwaway debug panel. The architecture is designed to be extended.

---

## Architecture

### New library: `native/src/ui/`

A dedicated CMake static library, sibling to `renderer`, `assets`, and `scenegraph`. It owns all RmlUi lifecycle and document management. Neither `renderer` nor `assets` depends on it; only `host_bindings.cc` holds both.

```
native/src/ui/
  CMakeLists.txt
  include/ui/
    UiSystem.h
    HudDocument.h
  UiSystem.cc
  HudDocument.cc
  rmlui_backends/
    RmlUi_Platform_GLFW.h
    RmlUi_Platform_GLFW.cpp
    RmlUi_Renderer_GL3.h
    RmlUi_Renderer_GL3.cpp

native/assets/ui/
  hud.rml
  hud.rcss
  fonts/
    Antonio-Regular.ttf       (OFL licence — committed to repo)
```

### Dependency graph

```
open_stbc_host → renderer, ui, assets, scenegraph, pybind11, Python3
ui             → RmlCore, glad, glfw
renderer       → assets, scenegraph, glad, glfw, glm
```

`ui` and `renderer` are siblings. `host_bindings.cc` is the only place both are included.

---

## Components

### `HudState` (plain struct, `UiSystem.h`)

```cpp
struct HudState {
    float pos_x, pos_y, pos_z;
    float yaw_deg, pitch_deg, roll_deg;
    std::string system_name;
    std::string ship_name;
};
```

Passed by value — no synchronisation needed (single-threaded render loop).

### `UiSystem`

Owns RmlUi init/shutdown, the GLFW system interface, the GL3 render interface, and one `Rml::Context`. Constructed in `init()`, destroyed in `shutdown()` before `g_window`.

```cpp
class UiSystem {
public:
    UiSystem(GLFWwindow* window, const std::filesystem::path& assets_root);
    ~UiSystem();                           // calls Rml::Shutdown()
    void update_hud(const HudState& state);
    void render(int fb_width, int fb_height);
private:
    SystemInterface_GLFW  system_iface_;
    RenderInterface_GL3   render_iface_;
    Rml::Context*         context_ = nullptr;
    HudDocument           hud_;
};
```

### `HudDocument`

Loads `hud.rml` once at construction. Caches four `Rml::Element*` pointers for the text nodes (`#ship-name`, `#system-name`, `#pos`, `#rot`). `update()` calls `SetInnerRML()` on each — cheap per-frame string updates, no document reload.

---

## HUD Document

### Visual layout (top-right corner)

```
┌───────────────────────┐
│ Ship:    Bop           │
│ System:  Biranu1       │
│ Pos:   123.4 -56.7 890 │
│ Rot:  Y45° P-12° R3°  │
└───────────────────────┘
```

Semi-transparent dark panel (`rgba(0,0,0,0.45)`) ensures readability against bright backdrops or suns.

### `hud.rcss` key rules

- Font: Antonio Regular, 14px, colour `#c8d8e8`
- Position: `absolute; right: 10px; top: 10px`
- Text alignment: right
- Background: `rgba(0,0,0,0.45)`, padding 8px, border-radius 4px

### `hud.rml` element IDs

| ID | Content |
|----|---------|
| `#ship-name` | `Ship: <name>` |
| `#system-name` | `System: <name>` |
| `#pos` | `Pos: X Y Z` (1 decimal place) |
| `#rot` | `Rot: Y<n>° P<n>° R<n>°` (0 decimal places) |

---

## Data Flow

### Per-tick Python (`engine/host_loop.py`)

Added after the existing lighting/backdrop calls, before `r.frame()`:

```python
import math

R = player.GetWorldRotation()   # TGMatrix3, row-vector convention
fwd = R.GetRow(1)               # forward = Y axis
up  = R.GetRow(2)               # up = Z axis
rgt = R.GetRow(0)               # right = X axis

yaw_deg   = math.degrees(math.atan2(fwd.x, fwd.y))
pitch_deg = math.degrees(math.asin(max(-1.0, min(1.0, fwd.z))))
roll_deg  = math.degrees(math.atan2(-rgt.z, up.z))

p = player.GetWorldLocation()
import App as _App
active_set_name = next(
    (name for name, s in _App.g_kSetManager._sets.items() if s is active_set),
    ""
) if active_set is not None else ""
raw_script = player.GetScript() or ""
ship_display = raw_script.split(".")[-1] if raw_script else "---"

r.set_hud_state({
    "pos":    (p.x, p.y, p.z),
    "yaw":    yaw_deg,
    "pitch":  pitch_deg,
    "roll":   roll_deg,
    "system": active_set_name or "---",
    "ship":   ship_display or "---",
})
```

`set_hud_state` is a no-op when `player is None`.

### Per-frame C++ (`host_bindings.cc` `frame()`)

After the opaque pass, before `poll_events` / swap:

```cpp
if (g_ui_system) {
    g_ui_system->update_hud(g_hud_state);
    g_ui_system->render(fw, fh);
}
```

### Full `frame()` pass order

1. `glClear`
2. `g_backdrop_pass->render(…)`
3. `g_sun_pass->render(…)`
4. `g_submitter->submit_opaque(…)`
5. `g_ui_system->update_hud(…)` + `render(…)`
6. `g_window->poll_events()`
7. `g_window->swap_buffers()`

---

## Build / CMake

### RmlUi via FetchContent (`native/CMakeLists.txt`)

```cmake
FetchContent_Declare(
    RmlUi
    GIT_REPOSITORY https://github.com/mikke89/RmlUi.git
    GIT_TAG        6.0.1
)
set(RMLUI_BACKEND None CACHE STRING "" FORCE)
set(RMLUI_SAMPLES OFF CACHE BOOL "" FORCE)
set(RMLUI_TESTS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(RmlUi)
```

Added after the pybind11 `FetchContent_MakeAvailable` block, before `add_subdirectory(src/renderer)`.

Also add `add_subdirectory(src/ui)` immediately after `add_subdirectory(src/renderer)` so both sibling libraries are present before `add_subdirectory(src/host)`.

### `native/src/ui/CMakeLists.txt`

```cmake
add_library(ui STATIC
    UiSystem.cc
    HudDocument.cc
    rmlui_backends/RmlUi_Platform_GLFW.cpp
    rmlui_backends/RmlUi_Renderer_GL3.cpp
)
target_include_directories(ui
    PUBLIC  include
    PRIVATE rmlui_backends
)
target_link_libraries(ui PUBLIC RmlCore glad glfw)
target_compile_features(ui PUBLIC cxx_std_20)
```

### `native/src/host/CMakeLists.txt`

Add `ui` to the `open_stbc_host` link set.

---

## Python API additions

### `engine/renderer.py`

```python
def set_hud_state(state: dict) -> None:
    _h.set_hud_state(state)
```

### `_open_stbc_host` binding

```cpp
m.def("set_hud_state", [](const py::dict& d) {
    if (!g_ui_system) return;
    g_hud_state.pos_x       = d["pos"].cast<std::tuple<float,float,float>>() ...
    g_hud_state.yaw_deg     = d["yaw"].cast<float>();
    // etc.
});
```

---

## Testing

### Euler angle extraction (new Python unit test)

File: `tests/test_hud_euler.py`

Construct known `TGMatrix3` values and assert the extracted yaw/pitch/roll match expected degrees:
- Identity matrix → 0°/0°/0°
- Pure 90° yaw around Z → yaw=90°, pitch=0°, roll=0°
- Pure 90° pitch → yaw=0°, pitch=90°, roll=0°
- Compound rotation → matches expected decomposition

### Smoke test (existing)

The existing `OPEN_STBC_HOST_HEADLESS=1` smoke test exercises `init → frame → shutdown`. After this change it also exercises `UiSystem` construction, `hud.rml` load, font load, and `render()`. No new test file needed.

### What is not tested

Pixel-level HUD rendering. macOS headless windows return unreliable pixel data (see project memory). The Euler test + smoke path provides sufficient confidence.

---

## Open questions / deferred

- RmlUi input forwarding (mouse, keyboard) — not wired up in this milestone. `UiSystem` will expose a `handle_glfw_event()` hook as a stub for a future milestone.
- `RmlDebugger` — excluded from this milestone; can be added later behind a compile-time flag.
- Additional HUD panels (weapons status, shields, etc.) — out of scope; this spec covers only the position/rotation overlay.
