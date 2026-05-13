# Scrollable Target List — Cursor-Routed Mouse Wheel

**Status:** design
**Date:** 2026-05-12

## Problem

The targets panel is fixed-height. With heterogeneous missions (drydocks + stations + shuttles) the list overflows the panel and rows are clipped. The mouse wheel is currently bound to camera zoom — there's no way to scroll the list.

We want mouse-wheel scrolling on the panel **only when the cursor is over scrollable content**. Outside the panel, the wheel keeps zooming the camera.

## Goals

- Mouse-wheel scrolls the panel when the cursor is over the scrollable body.
- Mouse-wheel zooms the camera when the cursor is anywhere else (including over the panel's title bar or over the scene).
- No new C++ window-system gymnastics — leverage RmlUi's existing hit-testing.
- Long target lists become usable; short lists render identically to today (no chrome, no scrollbar shown).

## Non-goals

- Click-to-scroll arrow buttons. The user picked wheel-only; arrows can be revisited if discoverability becomes a problem.
- Horizontal scroll. Panels never grow wider than their fixed width.
- Touch / trackpad-pinch / momentum scrolling. GLFW's scroll callback collapses these to discrete y-deltas; that's the granularity we work at.
- Keyboard scrolling (PgUp/PgDn). Could be added later — out of scope here.

## Architecture

Two layers: native input routing (C++) and panel CSS (RmlUi).

| Unit | Where | Role |
|---|---|---|
| `scroll_cb` *(new)* | `native/src/ui/UiSystem.cc` | GLFW scroll callback. Calls `RmlGLFW::ProcessScrollCallback(ctx, yoffset, mods)` and consults its return value. If RmlUi consumed it (cursor over a scrollable element), stop. Otherwise re-emit into `renderer::Window`'s scroll accumulator. |
| `renderer::Window::add_scroll_y` *(new)* | `native/src/renderer/window.cc` | Public method `void add_scroll_y(double dy)`. Adds `dy` to the existing `scroll_y_accum_` so the Python `consume_scroll_y` path keeps working unchanged. |
| Window scroll callback removal *(edit)* | `native/src/renderer/window.cc:51-68` | Delete the existing `glfwSetScrollCallback` block. UiSystem now owns the callback and re-emits to `Window` via `add_scroll_y`. |
| Panel body CSS *(edit)* | `native/assets/ui/components.rcss` (`.bc-panel-body` rule near line 82) | Add `overflow-y: auto; max-height: <vh value>` to `.bc-panel-body`. Style `scrollbar-vertical`, `slidertrack`, `sliderbar` to match the panel palette. |

### Event flow

```
GLFW scroll event
    │
    ▼
UiSystem::scroll_cb(yoffset)
    │
    ├─ RmlGLFW::ProcessScrollCallback(ctx, yoffset, mods)
    │     │
    │     ├─ cursor over scroll-eligible element?
    │     │     yes → RmlUi scrolls the element, returns true     ─── done
    │     │     no  → returns false
    │     │
    └─ if false:
        Window::add_scroll_y(yoffset)
            │
            ▼
        scroll_y_accum_ += yoffset
            │
            (Python tick reads via consume_scroll_y → camera zoom)
```

RmlUi's hit testing is pixel-accurate against the live DOM tree. The cursor-over-panel determination is automatic; we don't track panel rectangles ourselves.

## Per-unit detail

### `UiSystem` scroll callback

```cpp
// native/src/ui/UiSystem.cc — add to the anonymous namespace alongside existing callbacks

void scroll_cb(GLFWwindow* w, double /*xoffset*/, double yoffset) {
    bool consumed = false;
    if (g_input_ctx) {
        consumed = RmlGLFW::ProcessScrollCallback(
            g_input_ctx, yoffset, /*key_modifier_state=*/0);
    }
    if (!consumed) {
        if (auto* win = static_cast<renderer::Window*>(glfwGetWindowUserPointer(w))) {
            win->add_scroll_y(yoffset);
        }
    }
}
```

Wired in the `UiSystem` ctor right after the other callbacks:

```cpp
glfwSetScrollCallback(window, scroll_cb);
```

Header include for `renderer::Window` added at the top of the .cc. UiSystem.cc already references `renderer::Window` indirectly through the GLFW user pointer, so the dependency is minor.

### `renderer::Window::add_scroll_y`

```cpp
// native/src/renderer/include/renderer/window.h
void add_scroll_y(double dy) noexcept;

// native/src/renderer/window.cc
void Window::add_scroll_y(double dy) noexcept {
    scroll_y_accum_ += dy;
}
```

Existing lambda in the `Window` ctor that wired `glfwSetScrollCallback` is **deleted**. UiSystem replaces it. Any test that creates a `Window` without a `UiSystem` (purely native renderer tests with no UI) loses scroll input — those tests don't use scroll today, so no regression.

### Init ordering

Current `App` init in `native/src/host/`:

1. `renderer::Window` constructed → registers cursor/mouse-button callbacks (kept) and (post-edit) no longer registers scroll callback.
2. `ui::UiSystem` constructed → registers cursor/mouse-button/key/char callbacks AND (new) the scroll callback.

`glfwGetWindowUserPointer(w)` returns the `Window*` because `Window` already calls `glfwSetWindowUserPointer(handle_, this)` in its ctor and both move operations ([window.cc:53,107,128](../../../native/src/renderer/window.cc#L53)). UiSystem's scroll callback reads that pointer to call `add_scroll_y`. The pointer is valid for the lifetime of the `Window`.

### Panel CSS

Edit `native/assets/ui/components.rcss`. The `.bc-panel-body` rule already exists near line 82; extend it:

```css
.bc-panel-body {
    /* existing rules preserved */
    overflow-y: auto;
    max-height: 70vh;        /* tunable — panels above 70% viewport scroll */
}

scrollbar-vertical {
    width: 12dp;
}

slidertrack {
    background-color: rgba(20, 20, 30, 0.6);
}

sliderbar {
    background-color: var(--panel-accent);
    border-radius: 4dp;
    min-height: 24dp;
}

sliderbar:hover {
    background-color: var(--panel-accent-hover);
}
```

`--panel-accent` and `--panel-accent-hover` are already set as CSS custom properties by `UiPanel.set_panel_css_var` based on the affiliation/menu-level theme; the scrollbar inherits panel colour automatically.

Affiliation-coloured strip at the left of each row stays unchanged.

### Python side: nothing

`UiPanel` doesn't need to know it's now scrollable — RmlUi handles overflow rendering inside the panel body div. The `clear() + rebuild` cycle in `TargetListController` continues to work; RmlUi resets scroll position to 0 on full DOM replace, which is acceptable behaviour (see Open Questions).

## Error handling

- `g_input_ctx == nullptr`: scroll falls through to camera (current behaviour). Correct.
- `glfwGetWindowUserPointer` returns null: scroll is dropped (no camera zoom either). Logged at WARN once per session. Should only happen if UiSystem is constructed before Window, which we'll prevent at init.
- Panel body shorter than `max-height`: RmlUi renders no scrollbar; wheel events fall through to camera. Expected, matches goal.

## Testing

| Test | Where | Asserts |
|---|---|---|
| Native scroll routing — cursor over scrollable | new C++ test under `native/tests/ui/` | Set up an RmlUi context with a scrollable document, position the virtual cursor over it, fire `ProcessScrollCallback(ctx, -1.0)`, assert returns `true`. |
| Native scroll routing — cursor not over scrollable | same | Same setup, cursor at (0,0) outside any element, fire callback, assert returns `false`. |
| `Window::add_scroll_y` accumulates | `native/tests/renderer/test_window_scroll.cc` *(or existing equivalent)* | Call `add_scroll_y(1.5)` then `consume_scroll_y()`, expect `1.5`. Repeat call without consume → expect `3.0` accumulator. |
| Panel renders with overflow class when long enough | `tests/host/test_target_panel_scroll.py` *(new)* | Load a mission with >10 target rows, assert the panel-body element gets the scrollable-body class / overflow-y style applied. (May need a new DOM-introspection helper; alternative: a snapshot test of the rendered RCSS-effective styles.) |
| Short lists don't display scrollbar | same | Load a 2-target mission, assert the panel body fits without overflow. (Verifies `max-height` is large enough not to clip short lists prematurely.) |
| Wheel-over-scene zooms camera unchanged | existing `tests/host/test_camera_control.py` extended | Simulate scroll event with virtual cursor in scene area (i.e. no panel hit), assert camera distance changed. Regression coverage for the existing flow. |

Native scroll-routing tests are the most novel — they require an offscreen RmlUi context. If our test infrastructure doesn't already spin one up, that's an implementation-cost line worth flagging in the plan. Existing `UiSystem` tests would be the model.

## Risk and mitigation

| Risk | Mitigation |
|---|---|
| RmlUi consumes scroll over elements that *shouldn't* be scrollable (panel title bar, footer button). | RmlUi only returns `true` when the event hits an element with computed `overflow: scroll/auto` and reachable content. Non-overflowing elements pass through. |
| Init order regression: Window's scroll callback survives because someone reintroduces the lambda. | The deletion of `Window`'s `glfwSetScrollCallback` is mechanical — one block goes away. PR review catches it. |
| Future panels also want scrolling but their body class is different. | The rule lives on `.bc-panel-body` which every `UiPanel` uses. Per-panel opt-out (if a future panel doesn't want overflow) is a one-line override on a panel-specific class. |
| RmlUi scrollbar styling clashes with the BC HUD palette. | All scrollbar colours read from the same `--panel-accent` custom properties already driving border/highlight chrome. If a specific panel needs an override, the existing per-panel CSS-var system already supports it. |

## Open questions

- **Scroll position persistence across rebuilds.** `TargetListController` does `panel.clear() + rebuild` on every `ship_lifecycle` event. RmlUi resets scroll to top on DOM replace. If the user is scrolled mid-list when a ship is destroyed, they jump to the top. *Resolution:* Acceptable for the first cut. If complaints land, the controller can snapshot scroll offset by ship-id-of-topmost-visible-row before clearing and restore after rebuilding. Track as a follow-up.
- **Camera-zoom sensitivity.** Existing zoom uses `ZOOM_FACTOR_PER_NOTCH = 0.9` ([engine/host_loop.py:263](../../../engine/host_loop.py#L263)). Wheel deltas routed to scrolling never reach this code, so sensitivity is unchanged.
- **Scrollbar always visible vs auto.** `overflow-y: auto` shows the bar only when content overflows. `overflow-y: scroll` always shows it. Original BC always shows the scroll arrows even on short lists. *Resolution:* start with `auto` (less chrome on short lists), revisit if the user wants the BC look.

## Out of scope, deferred

- Click-to-scroll arrow buttons matching the original BC HUD. Easy add later via RmlUi's `sliderarrowdec` / `sliderarrowinc` decorators if discoverability becomes a problem.
- Keyboard scrolling (PgUp/PgDn, arrow keys when panel focused).
- Per-panel scroll preferences (e.g. always-show arrows on a per-panel basis).
- Drag-to-scroll on the panel body.
- Horizontal scroll for panels that exceed their width — panels are fixed-width by design.
