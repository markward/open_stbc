# Mission Picker — In-Process Mission Switching UI

**Status:** design approved, ready for implementation plan
**Date:** 2026-05-11
**Author:** Mark Ward (with Claude)

## 1. Purpose

`open_stbc` boots into a single hard-coded mission (`SHIP_GATE_MISSION =
"Custom.Tutorial.Episode.M1Basic.M1Basic"`) and offers no way to switch
once the renderer is running. To validate Phase 1's "run the SDK
tutorial missions" goal — and to exercise the in-process reload path the
engine will need anyway — we need a developer-facing mission picker:

- A "Load Mission" button at the bottom of the existing top-right Debug
  panel.
- Clicking it opens a centered modal panel listing every discoverable
  mission, grouped two-deep (family → episode → mission).
- Clicking a mission closes the modal and swaps the running mission
  in-process.
- A "Cancel" button (and ESC) closes the modal without changing
  anything.

This consumes the `UiPanel`/`UiButton`/`UiCollapsibleList` primitives
from `docs/superpowers/specs/2026-05-11-ui-components-design.md`, adds
the small UI shell features the picker needs, and introduces a
`MissionSession` boundary in the host loop so a mission swap is a
well-defined operation.

## 2. Scope

In scope:

- Mission discovery across the full `sdk/Build/scripts/` tree.
- A minimal binary-TGL reader sufficient to pull mission and episode
  display names.
- A "center" anchor for `UiPanel` and a single-slot footer button.
- A `MissionPicker` module that builds and owns the modal.
- A `MissionSession` refactor of `host_loop.run()` so swapping a
  mission is one method call.
- Tests for discovery, TGL parsing, name resolution, the new UI shell
  features, and the picker itself.

Out of scope (explicitly deferred — see §11):

- Backdrop / dim overlay / input gating / pause-while-modal.
- Mission preview text, screenshots, difficulty selection.
- Remembering expansion or last-picked state across opens.
- Localization of "Load Mission" / "Cancel" labels.
- QuickBattle as a mission target.

## 3. Decisions captured during brainstorming

| Decision | Choice | Notes |
|---|---|---|
| Mission scope | Scan all of `sdk/Build/scripts/` | Forward-looking; unloadable missions still surface in the picker |
| Reload mechanism | In-process | Renderer + SDK state torn down on each swap; same process |
| Tree shape | Two-level: family → episode → missions | Both family and episode rows are collapsible |
| Modal behavior | Floating panel only | No dim/backdrop, no input gating, no pause |
| Dismiss key | ESC dismisses | Same effect as clicking Cancel |
| Label source | Real TGL strings | With dir-name fallback when TGL parse misses |
| Cold state | All families/episodes collapsed | Compact open |
| Trigger | Debug-panel button only | No global keyboard shortcut |

## 4. Architecture

```
engine/missions/                 (new package)
├── __init__.py                  exports MissionRegistry, FamilyEntry, EpisodeEntry, MissionEntry, discover()
├── discovery.py                 walks sdk/Build/scripts → registry
├── tgl_reader.py                BC binary TGL parser
└── name_resolver.py             per-family adapters: TGL keys (Tutorial, Maelstrom),
                                 module callback (Multiplayer); dir-name fallback

engine/mission_picker.py         MissionPicker class — builds & owns the modal panel,
                                 routes mission/cancel clicks, handles ESC

engine/ui/panel.py               (modified) Anchor literal gains "center";
                                 set_footer_button(label, on_click) added

native/assets/ui/components.rcss (modified) .bc-panel-center, .bc-panel-footer styles

engine/host_loop.py              (modified) scene state extracted into MissionSession;
                                 HostController owns swap_mission() and the pending-swap latch
```

No native C++ changes are anticipated — the centered anchor is a CSS
class switch on the existing `create_panel` binding. The plan stage
validates that the renderer already exposes per-instance teardown
(`destroy_instance` or `clear_instances`); if not, that's a small
binding addition.

### 4.1 Component boundaries

- **`engine/missions/`** has no UI imports. Pure data — discovery,
  parsing, label resolution. Useful from tests, harnesses, and future
  CLI tooling. Single dependency direction: missions → SDK paths +
  TGL binaries.
- **`engine/mission_picker.py`** depends on `engine.missions` (for the
  registry) and `engine.ui` (for the panel). It does **not** know how
  to load a mission — it invokes a callback supplied by the host.
- **`engine/host_loop.py`** owns the renderer, the
  `MissionSession`, and the swap callback. The picker is a passive
  consumer.

### 4.2 Sequence — opening, picking, swapping

```
user clicks "Load Mission"
  → debug_panel button on_click → picker.open()
    → picker builds UiPanel(anchor="center")
    → for each family / episode / mission, builds collapsibles and buttons

user clicks a mission button
  → mission_button on_click → picker._pick(mission)
    → picker.close()                              # panel destroyed
    → host.swap_mission(mission.module_name)
      → host.pending_swap = module_name           # deferred to next tick

next tick of run() loop:
  → if host.pending_swap: host._do_swap()
    → session.teardown()                          # destroy instances, clear SDK globals
    → session = host._load_session(pending_swap)
    → rebind player + camera control
    → pending_swap = None
```

Deferring the swap to the tick boundary keeps the in-flight RmlUi event
dispatch clean and avoids tearing down the renderer's instance table
mid-callback.

## 5. Mission discovery

### 5.1 Data model

```python
@dataclass
class MissionEntry:
    module_name: str         # "Custom.Tutorial.Episode.M1Basic.M1Basic"
    display_name: str        # TGL-resolved or dir fallback
    dir_name: str            # "M1Basic"

@dataclass
class EpisodeEntry:
    display_name: str
    dir_name: str
    missions: list[MissionEntry]

@dataclass
class FamilyEntry:
    display_name: str        # "Tutorial", "Maelstrom", "Multiplayer"
    dir_name: str
    episodes: list[EpisodeEntry]

class MissionRegistry:
    families: list[FamilyEntry]

    @classmethod
    def discover(cls, scripts_root: Path = ...) -> "MissionRegistry": ...
```

### 5.2 Discovery rule

A *mission* is a leaf directory `X/` under `sdk/Build/scripts/` that
contains a same-named Python file `X.py` (case-insensitive match) whose
top level defines `Initialize(mission)`. The `Initialize` check is a
lightweight regex/AST scan — we do **not** import the module during
discovery.

The discovery walker recognises three canonical family layouts:

| SDK layout | Family | Episode dir | Mission dir |
|---|---|---|---|
| `Custom/Tutorial/Episode/<M>/<M>.py` | `Tutorial` | `Episode` (collapsed in UI) | `<M>` |
| `Maelstrom/Episode<N>/<MID>/<MID>.py` | `Maelstrom` | `Episode<N>` | `<MID>` |
| `Multiplayer/Episode/<MID>/<MID>.py` | `Multiplayer` | `Episode` (collapsed in UI) | `<MID>` |

Anything else found that matches the leaf-dir-with-same-named-file
heuristic is grouped under a synthetic `"Other"` family with episode
`"."` so it still surfaces. Discovery never raises on malformed input;
it logs and skips.

### 5.3 Single-episode collapse

When a family has exactly one episode and that episode's `dir_name`
matches a stop-list (`Episode`, `.`), the picker UI skips rendering the
episode row and attaches mission buttons directly to the family
collapsible. The data structure remains family → episode → missions;
only the *rendered* tree elides the redundant level.

### 5.4 QuickBattle

Excluded from v1. `QuickBattle.py` is a game-mode entry point, not a
discrete mission package, and the v1 picker has no place to surface the
"start QuickBattle" affordance.

## 6. TGL reader

### 6.1 What we need

Just enough to read `{key: str}` from BC's binary `.tgl` localization
files. The two registries that supply mission/episode display names
are:

- `sdk/Build/Data/TGL/Tutorial/Tutorial.tgl`
  (and `.../Tutorial/Episode/Episode.tgl`)
- `game/data/TGL/Maelstrom/Maelstrom.tgl` — contains keys like
  `Ep1Title`, `E1M1Title`.

Multiplayer doesn't need the reader at all — its `MissionNName.py`
modules call back into a TGL via the existing
`engine/appc/localization.py` stub. With a working reader behind that
stub, those calls return real strings automatically.

### 6.2 Format

Inspection of `sdk/Build/Data/TGL/Tutorial/Episode/Episode.tgl` (a
deliberately one-entry sample) shows a small fixed header, an entry
count, then per-entry records of:

- length-prefixed ASCII key (null-terminated)
- length-prefixed UTF-16-LE string value
- length-prefixed ASCII sound filename (or empty)

The plan stage finalizes the exact offsets against ≥3 sample files of
different sizes, including one larger file from the Maelstrom set.

### 6.3 API

```python
class TGLFile:
    strings:    dict[str, str]      # key → unicode string
    sounds:     dict[str, str]      # key → sound filename ("" when absent)
    source:     str                 # original filename, for debugging

def read_tgl(path: Path) -> TGLFile: ...
```

The reader raises `TGLParseError` on malformed input — callers in
`name_resolver` swallow this and fall back to dir names, so a single
broken file cannot brick the picker.

### 6.4 Escape hatch

If the binary layout proves harder than expected during plan execution,
the picker still ships: `name_resolver` already falls back per-entry to
the dir name. The TGL reader is therefore the **only** part of this
spec where degrading to "dir names only" is an acceptable outcome.

## 7. Name resolution

```python
def resolve_family(family_dir: str) -> str: ...
def resolve_episode(family_dir: str, episode_dir: str) -> str: ...
def resolve_mission(family_dir: str, episode_dir: str, mission_dir: str,
                    module_path: str) -> str: ...
```

Per-family rules:

| Family | Episode label source | Mission label source |
|---|---|---|
| `Tutorial` | `Tutorial.tgl` key `Episode` (fallback: `"Tutorial"`) | `Tutorial.tgl` key matching `mission_dir` |
| `Maelstrom` | `Maelstrom.tgl` key `Ep<N>Title` | `Maelstrom.tgl` key `<MissionID>Title` then `<MissionID>` |
| `Multiplayer` | hard-coded `"Multiplayer"` | `import Multiplayer.Episode.<MID>.<MID>Name; GetMissionName()` |
| Other / fallback | `episode_dir` | `mission_dir` |

Every adapter is wrapped in `try / except Exception` and falls back to
the directory name on failure. No exception leaves `resolve_*` —
`MissionRegistry` always returns a complete tree of strings.

A small cache keyed by TGL filename avoids re-parsing the same file
once per row.

## 8. UI shell changes

### 8.1 Centered anchor

`engine/ui/panel.py`:

```python
Anchor = Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]
```

`engine/ui/bindings.py` (or wherever the anchor string reaches the
binding layer) maps `"center"` to the CSS class `bc-panel-center`. No
C++ change is needed if the anchor is already a class-string switch in
`create_panel`; the plan verifies this in the existing
`native/src/host_bindings.cc`.

`native/assets/ui/components.rcss`:

```rcss
.bc-panel-center {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
}
```

### 8.2 Footer button

```python
class UiPanel:
    def set_footer_button(self, label: str,
                          on_click: Optional[Callable[[], None]] = None) -> UiButton: ...
```

First call creates a `bc-panel-footer` div appended after
`bc-panel-body` and a single `UiButton` inside it, right-aligned via
CSS. Subsequent calls re-label / re-bind the same button. `destroy()`
removes it. There is intentionally exactly one footer button per panel
for v1 — Cancel is the only consumer.

```rcss
.bc-panel-footer {
    display: flex;
    justify-content: flex-end;
    padding: 8dp;
}
```

### 8.3 Debug-panel hook

In `host_loop.run()` after the existing stat rows:

```python
picker = MissionPicker(registry=MissionRegistry.discover(),
                       on_load=host.swap_mission,
                       on_cancel=lambda: None)
debug_panel.button("Load Mission", on_click=picker.open)
```

This uses the existing `UiPanel.button()` API; the button slots in at
the end of the debug panel because rows are appended in order.

## 9. Mission picker

```python
class MissionPicker:
    def __init__(self, *,
                 registry: MissionRegistry,
                 on_load: Callable[[str], None],
                 on_cancel: Callable[[], None]):
        self._registry = registry
        self._on_load = on_load
        self._on_cancel = on_cancel
        self._panel: Optional[UiPanel] = None

    def open(self) -> None: ...
    def close(self) -> None: ...        # idempotent — destroys panel if open
    def is_open(self) -> bool: ...
    def handle_key_esc(self) -> None:   # called from host's per-tick key poll
        if self.is_open(): self._cancel()
```

`open()` builds:

```
UiPanel(id="mission-picker", anchor="center",
        width_vw=42, height_vh=72, title="Load Mission", collapsible=False)

  for family in registry.families:
      family_row = panel.collapsible(family.display_name, menu_level=1, expanded=False)
      for episode in family.episodes:
          if len(family.episodes) == 1 and episode.dir_name in {"Episode", "."}:
              parent = family_row                          # skip redundant episode row
          else:
              parent = family_row.collapsible(episode.display_name,
                                              menu_level=2, expanded=False)
          for mission in episode.missions:
              parent.button(mission.display_name,
                            on_click=lambda m=mission: self._pick(m))

  panel.set_footer_button("Cancel", on_click=self._cancel)
```

`_pick(mission)`: closes the panel, then calls `on_load(mission.module_name)`.
`_cancel`: closes the panel, then calls `on_cancel()`.

The picker holds the registry passed at construction time; rescanning
is a future enhancement. (Restarting the host re-scans.)

## 10. In-process mission swap

### 10.1 `MissionSession`

```python
@dataclass
class MissionSession:
    mission_name: str
    ship_instances:   dict[object, int]        # ship → renderer instance id
    planet_instances: dict[object, int]
    player: Optional[object]
```

The `nif_to_handle` cache is **not** part of the session — it lives on
the `HostController` and is reused across swaps so the same NIF doesn't
re-load when the next mission also uses it.

### 10.2 `HostController`

```python
class HostController:
    nif_to_handle: dict[str, int]
    session: Optional[MissionSession]
    pending_swap: Optional[str]

    def swap_mission(self, module_name: str) -> None:
        self.pending_swap = module_name

    def _drain_pending_swap(self) -> None: ...   # called at top of each tick
```

`_drain_pending_swap()`:

1. If `pending_swap is None`, return.
2. `self._teardown_session()` — destroy renderer instances for every
   ship/planet, reset SDK globals (timers, set manager, event manager,
   broadcast handlers, waypoint registry, `_next_event_type_id`).
3. `self.session = self._load_session(pending_swap)` — runs the
   existing `_init_mission` body sans the prelude that step 2 already
   did; then iterates ships and planets to build instances; resolves
   the player.
4. Rebind player to `player_control`; reset `cam_control`.
5. `self.pending_swap = None`.

The SDK-globals clear that `_init_mission` does today is extracted into
`MissionSession.reset_sdk_globals()` so both code paths share it.

### 10.3 Renderer teardown support

The plan verifies the renderer exposes a per-instance destroy
(`r.destroy_instance(iid)`) or a bulk `r.clear_instances()`. If neither
exists, the plan adds a thin native binding — this is the only
plausible C++ change in the spec and it's small.

### 10.4 Error policy

If `_load_session(name)` raises, the host logs the failure and leaves
itself in a "no current mission" state: renderer alive, no instances,
debug panel still visible, the picker re-openable. The user can pick
another mission. We do not attempt to revert to the previous mission —
state-machine complexity for a developer tool is not worth the cost.

### 10.5 ESC routing

Per-tick, after the existing `key_pressed(KEY_F8)` / `KEY_F9` checks:

```python
if _h is not None and _h.key_pressed(_h.keys.KEY_ESCAPE):
    picker.handle_key_esc()
```

ESC is silently ignored when the picker is closed.

## 11. Out of scope (deferred)

- **Backdrop / dim / input-gate / pause.** Brainstorming explicitly
  ruled these out. Re-add later when the game has a real pause mode.
- **Mission preview / description / screenshots / difficulty.** Phase
  2 — needs more data plumbing.
- **Remembering expand/collapse / last picked across opens.** Easy add
  later; not worth state plumbing now.
- **Localizing the picker's own UI labels** ("Load Mission", "Cancel",
  "Mission Picker" title). English only for v1.
- **QuickBattle.** Not a mission package.
- **Mission rescan.** Picker uses the registry captured at host start.

## 12. Testing

Pure-Python tests, no native build required, run via `uv run pytest`.

| File | Coverage |
|---|---|
| `tests/missions/test_discovery.py` | Golden tree against the real `sdk/Build/scripts/`; family grouping; Other-family fallback; malformed dirs are skipped |
| `tests/missions/test_tgl_reader.py` | Parses ≥2 real sample TGLs to expected `(strings, sounds)` dicts; raises `TGLParseError` on truncated input |
| `tests/missions/test_name_resolver.py` | Each family adapter with a stub TGL + stub Multiplayer module; dir-name fallback when the source is missing or raises |
| `tests/ui/test_panel_center.py` | `anchor="center"` produces the `bc-panel-center` class; no other layout side-effects |
| `tests/ui/test_panel_footer.py` | `set_footer_button` creates a single footer container with a right-aligned button; repeat calls re-use it; `destroy()` removes it |
| `tests/test_mission_picker.py` | `open()` builds the expected nested tree (family/episode/mission counts match a stub registry); single-episode collapse fires for `Episode`/`.`; mission click closes panel + calls `on_load(module_name)`; cancel closes + calls `on_cancel`; ESC routes to cancel when open and is a no-op when closed |
| `tests/host_loop/test_mission_session.py` | `_teardown_session()` clears renderer instances and the five SDK globals; `_load_session()` rebuilds instances; two consecutive swaps leave a clean state; failure in `_load_session` is logged and leaves the host in the "no-mission" state |

Integration smoke (manual, eyeball): launch the host, open the picker,
expand a family + episode, pick the tutorial → the tutorial mission
reloads in place.

## 13. Plan-stage open items

Decide during the implementation plan, not during this design:

- Exact byte layout of the TGL header (validate against ≥3 sample files).
- Whether the renderer already exposes a per-instance teardown.
- The exact width/height of the modal in `vw`/`vh` — start at 42/72 and
  tune against a busy tree (Maelstrom has the largest list).
- Whether `panel.collapsible(...)` on a `UiCollapsibleList` returns a
  `UiCollapsibleList` we can re-target (it should, per the components
  spec §5.3, but confirm before the picker leans on it).
- Whether to make the family / episode collapsibles `menu_level=1` /
  `menu_level=2` as listed in §9 — confirm visual contrast against the
  components-spec palettes once the picker is rendering.
