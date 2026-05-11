# UI Components — Reusable Button & Collapsible List

**Status:** design approved, ready for implementation plan
**Date:** 2026-05-11
**Author:** Mark Ward (with Claude)

## 1. Purpose

Bridge Commander's HUD is dense with stackable, hierarchical menus: targets, target subsystems, system map, navigation, mission orders, options. The current `open_stbc` build has a static hardcoded HUD (ship/system/pos/rot stats only). To get parity with the original — and to ship the mission-picker that's the immediate motivator — we need two reusable UI primitives:

- **`UiButton`** — a clickable row with radio-style selection within its parent.
- **`UiCollapsibleList`** — a header (itself a button) plus an expand/collapse arrow plus a list of child rows. Children can be `UiButton`s or further `UiCollapsibleList`s, nested to arbitrary depth.

Both primitives stack vertically inside a `UiPanel`. The panel is sized as a percentage of the viewport (vh/vw) and scrolls when content overflows.

This spec covers Phase 1 of the UI work — the two primitives plus the panel scaffolding they sit in. The mission-picker is a downstream consumer and is **out of scope** for this spec; it gets its own once the primitives land.

## 2. Architecture

### 2.1 Layered stack

```
engine/ui/                       (Python — component library, state, callbacks)
└── thin DOM bindings ──────────►
                                 native/src/ui/    (C++ — RmlUi element mutations)
                                 native/assets/ui/ (RML/RCSS — styling)
                                                  ──────────►  RmlUi  ──────►  OpenGL renderer
```

All component logic (selection, expansion, label resolution, radio-group semantics) lives in Python. The C++ binding layer is intentionally thin — it exposes element-tree primitives that Python composes into components. This is **Approach A** from brainstorming.

### 2.2 File layout

**New files:**

```
engine/ui/                       (new package)
├── __init__.py                   exports UiPanel, UiButton, UiCollapsibleList, theme
├── panel.py                      UiPanel — root container; owns an RmlUi document handle
├── button.py                     UiButton — radio-group child; click + selection state
├── collapsible.py                UiCollapsibleList — header (button + arrow) + child list
├── theme.py                      Affiliation + menu-level registries; mutable at runtime
├── bindings.py                   Thin façade over the new _open_stbc_host UI primitives
└── _dom.py                       Private fake-DOM shim used by unit tests

native/assets/ui/
├── components.rcss               (new) shared styles for Button / CollapsibleList
└── panel.rml                     (new) empty document shell that Python populates

native/src/ui/
├── PanelDocument.cc              (new) wraps a mutable RmlUi document for Python use
└── UiSystem.cc                   (existing) extended to register the panel document

native/src/host_bindings.cc       (existing) extended with create_panel / append_div /
                                            set_class / set_text / on_click / etc.
native/include/host_bindings.h    (existing) signatures added

tests/ui/                         (new directory)
├── test_theme.py                 registry behavior; mutation; default values
├── test_button.py                radio-group semantics; click → callback
├── test_collapsible.py           expand/collapse; nested children; header-vs-arrow click
├── test_panel.py                 viewport sizing; overflow scroll; mount/unmount
└── conftest.py                   fake-DOM fixture
```

**Files touched (not created):**

- `engine/renderer.py` — re-export the new bindings so consumer code keeps importing from `engine.renderer`.
- `.gitignore` — already covers `.superpowers/` (added during brainstorming).

### 2.3 Migration path

The Python component class boundary (`UiButton`, `UiCollapsibleList`, `UiPanel`) is the public surface. Consumer code never touches the C++ primitives directly. This insulates us from the underlying binding strategy:

- **A → B (declarative tree):** rewrite the component internals to batch element-tree dicts and ship them in one C++ call; selection/expansion state already lives Python-side, so it survives rebuild. Internal change only.
- **A → C (RmlUi data binding):** rewrite component internals as thin wrappers over an RmlUi `DataModel`. Bigger C++ glue, no consumer changes.

We default to A because it's cheapest to iterate, and the migration tax is internal to the component classes.

**Pre-migration escape hatches** if we hit performance issues before considering B/C:

1. Batched primitive calls via a `with panel.batched():` context that defers and flushes in one round-trip.
2. Lazy DOM materialization — collapsed subtrees are Python stubs that emit primitives only when expanded.

## 3. Visual theme

Style direction: **minimal modern** (locked during brainstorming). Dark panel, neutral child-row backgrounds, color used as accent on borders and (selectively) on tinted backgrounds and text. Sized for fixed-height rows that scale to viewport.

### 3.1 Fixed sizing

- Each row (button or collapsible header) has a fixed height in `vh` units: `--row-height: 4.5vh` (tunable; current best estimate).
- Panel width is the consumer's choice in `vw` (e.g., `width_vw=20`).
- When rows exceed the panel's `height_vh`, the inner list scrolls; row height never compresses.

### 3.2 Collapsible header (top-level or nested)

The header is affiliation-themed when its `affiliation` arg is set (top-level targets), otherwise menu-level-themed (nested system maps, options screens, etc.).

| Property | Affiliation-themed | Menu-level-themed |
|---|---|---|
| background | `affiliation NormalBase` @ 0.2 alpha | `menu_level NormalBase` @ 0.2 alpha |
| border-left | 3px solid `affiliation NormalBase` | 3px solid `menu_level NormalBase` |
| arrow color | `affiliation NormalBase` | `menu_level NormalBase` |
| text color | `#e8e8d0` (cream) | `#e8e8d0` |
| font | Antonio Regular | Antonio Regular |
| text-transform | `uppercase` | `uppercase` |
| letter-spacing | 2px | 2px |
| font-size | 14px | 14px |

Arrow glyph: `◀` when expanded, rotated `-90deg` (`▶`) when collapsed. Rotation is animated by the same 180ms ease used for row state changes (see 3.4).

### 3.3 Child button (unselected vs selected)

| Property | Unselected | Selected |
|---|---|---|
| background | `#3a3a3a` (neutral grey) | `menu_level Selected` variant @ 0.55-0.70 alpha (level-specific) |
| border-left | 6px solid `menu_level NormalBase` | 9px solid `menu_level HighlightedBase` |
| padding-left | 31px | 28px |
| text color | `#e0e0d8` (cream) | `#ffffff` |
| font | Antonio Regular | Antonio Regular |
| font-size | 14px | 14px |

The 6px border + 31px padding sums to 37px; the 9px border + 28px padding also sums to 37px. The content x-position is identical between states; only the colored bar grows.

### 3.4 Transitions

```
transition: border-left-width 0.18s ease,
            padding-left      0.18s ease,
            background        0.18s ease,
            color             0.18s ease,
            border-left-color 0.18s ease;
```

Click → previously selected sibling de-selects; the clicked row's bar grows from 6px to 9px while content stays put. Reversible.

## 4. Theme registries

Two registries live in `engine/ui/theme.py`. Both initialize from the same RGB values used in [`sdk/Build/scripts/LoadInterface.py`](../../sdk/Build/scripts/LoadInterface.py), and both are mutable at runtime — mirroring BC's `g_kRadar*Color` globals and the `ResetAffiliationColors()` API.

### 4.1 Affiliation palette

```python
# engine/ui/theme.py
AFFILIATION_DEFAULTS: dict[str, RGB] = {
    "friendly": ( 80, 112, 230),
    "enemy":    (216,  43,  43),
    "neutral":  (255, 255, 175),
    "unknown":  (127, 127, 127),
}
```

Used by `UiCollapsibleList` when constructed with `affiliation="<name>"`.

The 0.2-alpha background tint is derived at render time, not stored — keeping the registry simple.

### 4.2 Menu-level palette

```python
@dataclass
class MenuPalette:
    normal:      RGB    # g_kSTMenu{N}NormalBase
    highlighted: RGB    # g_kSTMenu{N}HighlightedBase
    selected:    RGB    # g_kSTMenu{N}Selected

MENU_LEVEL_DEFAULTS: dict[int, MenuPalette] = {
    1: MenuPalette(normal=(216,  94,  86), highlighted=(254, 120,  86), selected=(127, 60,  43)),
    2: MenuPalette(normal=(147, 103, 255), highlighted=(173, 132, 255), selected=( 86, 66, 127)),
    3: MenuPalette(normal=(207,  96, 159), highlighted=(246, 147, 204), selected=(103, 48,  79)),
    4: MenuPalette(normal=(144, 103, 144), highlighted=(175, 144, 175), selected=( 72, 51,  72)),
}
```

Used by `UiButton` and by `UiCollapsibleList` (when no `affiliation` is supplied) via a `menu_level: int = 3` argument.

### 4.3 Public API

```python
def get_affiliation(name: str) -> RGB
def set_affiliation(name: str, rgb: RGB) -> None
def reset_affiliations() -> None                 # mirrors BC's ResetAffiliationColors

def get_menu_palette(level: int) -> MenuPalette
def set_menu_palette(level: int, palette: MenuPalette) -> None
def reset_menu_palettes() -> None
```

Mutations push updated CSS custom properties (`--aff-*-color`, `--menu-N-normal`, etc.) to the panel document on the next frame — components re-color without re-rendering.

## 5. Component API

All labels are plain `str`. Localization (where needed) is the caller's responsibility — resolve via `App.g_kLocalizer.GetString(...)` before passing in.

### 5.1 `UiPanel`

```python
class UiPanel:
    def __init__(
        self,
        id: str,
        anchor: Literal["top-left", "top-right", "bottom-left", "bottom-right"] = "top-right",
        width_vw:  float = 20.0,
        height_vh: float = 60.0,
    ): ...

    def collapsible(self, label: str, *,
                    affiliation: Optional[str] = None,
                    menu_level: int = 3,
                    expanded: bool = True,
                    on_click: Optional[Callable[[], None]] = None,
    ) -> "UiCollapsibleList": ...

    def button(self, label: str, *,
               menu_level: int = 3,
               selected: bool = False,
               on_click: Optional[Callable[[], None]] = None,
    ) -> "UiButton": ...

    def clear(self) -> None: ...
    def destroy(self) -> None: ...
```

### 5.2 `UiButton`

```python
class UiButton:
    label:      str
    menu_level: int
    selected:   bool
    on_click:   Optional[Callable[[], None]]

    def set_selected(self, selected: bool) -> None: ...
    def set_label(self, label: str) -> None: ...
    def set_menu_level(self, level: int) -> None: ...
    def destroy(self) -> None: ...
```

### 5.3 `UiCollapsibleList`

```python
class UiCollapsibleList:
    label:       str
    affiliation: Optional[str]   # None means menu-level-themed
    menu_level:  int
    expanded:    bool
    selected:    bool

    # Children: same as UiPanel's API. Re-exposed here so nesting works:
    def collapsible(self, label, **kw) -> "UiCollapsibleList": ...
    def button(self,      label, **kw) -> "UiButton": ...

    def set_expanded(self,    expanded: bool) -> None: ...
    def set_affiliation(self, name: Optional[str]) -> None: ...
    def set_menu_level(self,  level: int) -> None: ...
    def set_selected(self,    selected: bool) -> None: ...   # selects the header itself
    def clear(self) -> None: ...                             # remove all children
    def destroy(self) -> None: ...
```

### 5.4 Usage example

```python
from engine.ui import UiPanel

panel = UiPanel(id="targets", anchor="top-right",
                width_vw=20, height_vh=60)

bop = panel.collapsible(
    label="Bird of Prey-1",
    affiliation="enemy",
    expanded=True,
    on_click=lambda: target_ship(bop_ref),         # click on the title region
)
bop.button("Shield Generator", on_click=lambda: target_subsystem("shields"))
warp = bop.button("Warp Core",  on_click=lambda: target_subsystem("warp_core"),
                  selected=True)
bop.collapsible("Disruptor Cannons", expanded=False,
                on_click=lambda: target_subsystem("disruptors"))

panel.collapsible(label="USS Yamato", affiliation="friendly", expanded=False,
                  on_click=lambda: target_ship(yamato_ref))
```

## 6. Behavior contract

### 6.1 Radio-group selection

- Within the **direct children** of a single parent (`UiPanel` or `UiCollapsibleList`), at most one button can be `selected=True` at any time.
- Clicking an unselected button: previously-selected sibling's `selected` flips to `False`, its `on_click` is **not** fired; the clicked button's `selected` flips to `True`, its `on_click` is fired.
- Clicking the already-selected button: no state change, `on_click` is **not** re-fired.
- Selection is per-parent, not panel-global. Two sibling collapsibles can each have one selected child independently.
- `set_selected()` programmatic calls follow the same exclusivity rule (other siblings get unselected automatically).

### 6.2 Collapsible header

- The header has two click regions: the **title** (everything except the arrow) and the **arrow** (a small left-side region).
- Title click → fires the header's `on_click`; also acts as a radio button (selects the header itself within its parent).
- Arrow click → toggles `expanded`. Does **not** fire `on_click`. Does **not** change selection state.
- When `expanded=False`, the immediate children's container has `display: none` — the parent's height collapses; subsequent rows shift up. Nested state (expansion of grandchildren, selection of great-grandchildren, etc.) is preserved and re-shows on next expand.

### 6.3 Affiliation vs. menu-level

A `UiCollapsibleList` chooses its theme by argument:

- `affiliation` set (and `menu_level` ignored if supplied) → affiliation palette drives header colors. Typical for top-level target rows.
- `affiliation=None` and `menu_level` set → menu-level palette drives. Typical for nested system maps, options screens, etc.

`UiButton` always uses the menu-level palette.

### 6.4 Mutation semantics

All `set_*` methods update Python state, then push a minimal set of class/text changes through the bindings. No full rebuild on state change. Theme registry changes propagate by pushing updated CSS custom properties at the panel level on the next frame.

## 7. C++ binding primitives

Added to `native/src/host_bindings.cc` (and `native/include/host_bindings.h`):

```cpp
// Panel lifecycle
int create_panel(const char* id, const char* anchor,
                 float width_vw, float height_vh);
void destroy_panel(int panel_id);
void clear_panel(int panel_id);

// Element mutation (each returns an opaque element id)
int append_div(int parent_id, const char* class_names);
void remove_element(int element_id);
void set_class(int element_id, const char* class_names);
void set_text(int element_id, const char* text);
void set_visible(int element_id, bool visible);

// Theme variables (panel-level CSS custom properties)
void set_panel_css_var(int panel_id, const char* var_name, const char* value);

// Input
void on_click(int element_id, PyObject* callable);   // owns a reference to callable
```

Total surface: ~10 functions. Each maps to a few lines of RmlUi calls in `PanelDocument.cc`. Click dispatch routes through a per-panel event listener that looks up the registered callable by element id.

## 8. RML / RCSS

### 8.1 `panel.rml`

Static shell — Python populates the body dynamically:

```xml
<rml>
<head>
    <title>Panel</title>
    <link type="text/rcss" href="components.rcss"/>
</head>
<body>
    <div id="root"></div>
</body>
</rml>
```

### 8.2 `components.rcss`

Declares the classes used by Python-generated markup. Color values are CSS custom properties that the binding layer sets per panel from the theme registry. Sketch:

```rcss
:root {
    --aff-color:           rgb(127, 127, 127);   /* default: unknown */
    --aff-bg:              rgba(127, 127, 127, 0.20);
    --menu-normal:         rgb(207,  96, 159);   /* default: level 3 */
    --menu-highlighted:    rgb(246, 147, 204);
    --menu-selected-bg:    rgba(103, 48, 79, 0.65);
    --row-height:          4.5vh;
}

.bc-panel {
    background-color: #2c2c2c;
    padding: 8dp;
    border-radius: 4dp;
}

.bc-collapsible-header {
    height: var(--row-height);
    background-color: var(--aff-bg);
    border-left: 3dp solid var(--aff-color);
    color: #e8e8d0;
    text-transform: uppercase;
    letter-spacing: 2dp;
    font-size: 14dp;
    font-weight: 600;
}

.bc-button {
    height: var(--row-height);
    background-color: #3a3a3a;
    border-left: 6dp solid var(--menu-normal);
    padding-left: 31dp;
    color: #e0e0d8;
    font-size: 14dp;
    /* transition: ... see 3.4 */
}

.bc-button.selected {
    background-color: var(--menu-selected-bg);
    border-left-color: var(--menu-highlighted);
    border-left-width: 9dp;
    padding-left: 28dp;
    color: #ffffff;
}
```

(Note: RmlUi's RCSS supports `transition` and CSS custom properties. The full file lives in `native/assets/ui/components.rcss`.)

## 9. Testing strategy

Unit tests live in `tests/ui/` and run in pure Python against a fake DOM (`engine/ui/_dom.py`) — no RmlUi or native build required. The fake DOM records `append_div / set_class / set_text / on_click` calls; tests assert on the recorded sequence and on Python-side state.

**Coverage targets:**

- `test_theme.py`: defaults match `LoadInterface.py` values; mutation works; `reset_*` restores defaults.
- `test_button.py`: click fires callback; selection is exclusive within parent; programmatic `set_selected` deselects siblings; theme registry changes propagate.
- `test_collapsible.py`: expand/collapse toggles child visibility; title click vs arrow click route correctly; nested collapsibles work; affiliation vs menu-level theme switching works.
- `test_panel.py`: panel creation/destruction; `clear()` removes all children; overflow scroll class applied when expected.

Integration with the live renderer is verified manually (host loop driven, eyeball check).

## 10. Out of scope

- Mission picker (consumer of these components; gets its own spec).
- Hover / focus / disabled visual states (the BC palette has these but the immediate use case doesn't need them; add when the first consumer asks).
- Drag-to-reorder, multi-select, keyboard navigation (none in BC's panel; not a Phase 1 need).
- Live localization (callable labels) — option 3 from the label-API discussion; deferred.
- Replacing the existing HUD doc (`hud.rml`) — it stays as-is; panels are a parallel document.

## 11. Open items (decide during plan-writing)

- Exact `--row-height` value. 4.5vh is a current best guess; may want to validate against a busy panel (e.g., 8 child rows + nested collapsible on a 1080p screen).
- Whether the collapsible's "arrow region" is fixed-width (e.g., 28dp) or proportional to the header height. Fixed-width is simpler and visually consistent; flag for the plan stage.
- Whether `set_menu_palette` mutations apply *retroactively* to elements already rendered (preferred) or only to newly created ones. Preferred answer is retroactively; confirm with the binding shape.

These don't block the plan; they're details the implementation will surface.
