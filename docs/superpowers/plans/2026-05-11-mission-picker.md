# Mission Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Load Mission" button at the bottom of the existing debug panel that opens a centered modal listing every discoverable SDK mission (family → episode → mission) and swaps the running mission in-process when one is picked.

**Architecture:** Three new Python packages (`engine/missions/` for discovery + TGL + name resolution, `engine/mission_picker.py` for the modal UI consumer, refactored `engine/host_loop.py` with a `MissionSession`/`HostController` boundary), plus small UI shell additions (`anchor="center"` and a footer-button slot on `UiPanel`). All component logic is testable against the existing `FakeDom` and on-disk SDK without launching the renderer.

**Tech Stack:** Python 3.12+, `pytest`, the existing `engine.ui` primitives (`UiPanel`, `UiButton`, `UiCollapsibleList`) and `FakeDom`, RmlUi via `_open_stbc_host` for production rendering. Native C++ touchpoints are minimal: one new anchor branch in `PanelDocument.cc`, one new key constant binding.

**Spec:** [docs/superpowers/specs/2026-05-11-mission-picker-design.md](../specs/2026-05-11-mission-picker-design.md)

---

## File Map

**New files:**

- `engine/missions/__init__.py` — public exports: `MissionRegistry`, `FamilyEntry`, `EpisodeEntry`, `MissionEntry`, `discover()`
- `engine/missions/tgl_reader.py` — binary TGL parser; produces `{key: str}` and `{key: filename}` dicts
- `engine/missions/discovery.py` — walks `sdk/Build/scripts/` to a `MissionRegistry`
- `engine/missions/name_resolver.py` — per-family adapters (TGL keys vs. `MissionNName.py` callback); dir-name fallback
- `engine/mission_picker.py` — `MissionPicker` class — builds + owns the modal panel; ESC routing
- `tests/missions/__init__.py` — empty
- `tests/missions/conftest.py` — shared fixtures (sample-TGL bytes, fake registry)
- `tests/missions/test_tgl_reader.py`
- `tests/missions/test_discovery.py`
- `tests/missions/test_name_resolver.py`
- `tests/missions/test_registry.py`
- `tests/test_mission_picker.py`
- `tests/host/test_mission_session.py`
- `tests/ui/test_panel_center.py`
- `tests/ui/test_panel_footer.py`

**Modified files:**

- `engine/ui/panel.py` — extend `Anchor` literal with `"center"`; add `set_footer_button(label, on_click)`; render footer container when first called
- `native/assets/ui/components.rcss` — add `.bc-panel-center`, `.bc-panel-footer`, `.bc-panel-footer-button` styles
- `native/src/ui/PanelDocument.cc` — add `else if (anchor == "center")` branch
- `native/src/host/host_bindings.cc` — bind `GLFW_KEY_ESCAPE` as `KEY_ESCAPE`
- `engine/host_loop.py` — extract `MissionSession` + `HostController`; add `_drain_pending_swap`, ESC key check, "Load Mission" debug-panel button

**Test layout note.** `tests/missions/` is new; `tests/host/test_mission_session.py` extends the existing `tests/host/` directory.

---

## Task 1: TGL parser — header + entry layout

**Files:**

- Create: `engine/missions/__init__.py` (empty for now)
- Create: `engine/missions/tgl_reader.py`
- Create: `tests/missions/__init__.py` (empty)
- Create: `tests/missions/conftest.py`
- Create: `tests/missions/test_tgl_reader.py`

This task reverse-engineers the binary format from existing `.tgl` samples. The format inspected in `sdk/Build/Data/TGL/Tutorial/Episode/Episode.tgl` shows: a 6-uint32 header, then per-entry records of `(uint32 key_len_bytes, ASCII key + NUL, uint32 value_len_bytes, UTF-16-LE value, uint32 filename_len_bytes, ASCII filename)`. The exact header field meanings don't matter — only the `count_entries` field at offset 4. Strings are length-prefixed by their *byte* length (so a UTF-16 string of N chars has length 2N).

- [ ] **Step 1.1: Create empty package and conftest**

Create `engine/missions/__init__.py` containing exactly one line:

```python
"""Mission discovery, name resolution, and TGL reading."""
```

Create `tests/missions/__init__.py` as an empty file.

Create `tests/missions/conftest.py`:

```python
"""Shared fixtures for engine.missions tests."""
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
SDK_TGL_ROOT = PROJECT_ROOT / "sdk" / "Build" / "Data" / "TGL"
GAME_TGL_ROOT = PROJECT_ROOT / "game" / "data" / "TGL"


@pytest.fixture
def tutorial_episode_tgl() -> Path:
    """One-entry sample shipped with the SDK."""
    return SDK_TGL_ROOT / "Tutorial" / "Episode" / "Episode.tgl"


@pytest.fixture
def maelstrom_tgl() -> Path:
    """Larger production sample with episode and mission keys."""
    return GAME_TGL_ROOT / "Maelstrom" / "Maelstrom.tgl"
```

- [ ] **Step 1.2: Write failing test for the one-entry sample**

Create `tests/missions/test_tgl_reader.py`:

```python
"""TGL binary parser — reads localization strings out of BC's .tgl files."""
import pytest

from engine.missions.tgl_reader import read_tgl, TGLParseError


def test_parse_tutorial_episode_one_entry(tutorial_episode_tgl):
    if not tutorial_episode_tgl.is_file():
        pytest.skip(f"{tutorial_episode_tgl} not present")

    tgl = read_tgl(tutorial_episode_tgl)

    assert "Unused" in tgl.strings
    assert tgl.strings["Unused"].startswith("This string is only here")
    assert tgl.sounds.get("Unused") == "Unused.wav"
    assert tgl.source == str(tutorial_episode_tgl)


def test_parse_raises_on_truncated_file(tmp_path):
    bad = tmp_path / "bad.tgl"
    bad.write_bytes(b"\x01\x17\x00\x00")  # header only — count not present
    with pytest.raises(TGLParseError):
        read_tgl(bad)
```

- [ ] **Step 1.3: Run tests to verify they fail**

Run: `uv run pytest tests/missions/test_tgl_reader.py -v`
Expected: ImportError / ModuleNotFoundError on `engine.missions.tgl_reader`.

- [ ] **Step 1.4: Implement the parser**

Create `engine/missions/tgl_reader.py`:

```python
"""Binary TGL parser.

BC's localization databases are stored as .tgl files: a small fixed
header, an entry count, then per-entry records of:

    uint32 key_len            (byte length of the ASCII key including NUL)
    ascii  key + b"\x00"
    uint32 value_len          (byte length of the UTF-16-LE string)
    utf16  value
    uint32 filename_len       (byte length of the ASCII filename incl. NUL)
    ascii  filename + b"\x00"

The first 6 uint32s of the header are read but only the second
(``entries``) is meaningful for our purpose. The exact semantics of the
other header fields are unknown and don't matter for reading strings.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path


class TGLParseError(ValueError):
    pass


@dataclass
class TGLFile:
    strings: dict[str, str] = field(default_factory=dict)
    sounds:  dict[str, str] = field(default_factory=dict)
    source:  str = ""


_HEADER_FMT = "<6I"          # 6 little-endian uint32s
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)


def read_tgl(path: Path | str) -> TGLFile:
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TGLParseError(f"cannot read {path}: {exc}") from exc
    return _parse(data, source=str(path))


def _parse(data: bytes, *, source: str) -> TGLFile:
    if len(data) < _HEADER_SIZE:
        raise TGLParseError(f"header truncated ({len(data)} < {_HEADER_SIZE})")

    _, count, _, _, _, _ = struct.unpack_from(_HEADER_FMT, data, 0)
    out = TGLFile(source=source)
    off = _HEADER_SIZE
    for i in range(count):
        try:
            off, key = _read_ascii_lp(data, off)
            off, value = _read_utf16_lp(data, off)
            off, filename = _read_ascii_lp(data, off)
        except struct.error as exc:
            raise TGLParseError(
                f"entry {i}: truncated at offset {off}") from exc
        out.strings[key] = value
        if filename:
            out.sounds[key] = filename
    return out


def _read_ascii_lp(data: bytes, off: int) -> tuple[int, str]:
    (n,) = struct.unpack_from("<I", data, off)
    off += 4
    if n == 0:
        return off, ""
    raw = data[off:off + n]
    if len(raw) < n:
        raise struct.error("ascii field truncated")
    off += n
    return off, raw.rstrip(b"\x00").decode("ascii", errors="replace")


def _read_utf16_lp(data: bytes, off: int) -> tuple[int, str]:
    (n,) = struct.unpack_from("<I", data, off)
    off += 4
    if n == 0:
        return off, ""
    raw = data[off:off + n]
    if len(raw) < n:
        raise struct.error("utf16 field truncated")
    off += n
    return off, raw.decode("utf-16-le", errors="replace").rstrip("\x00")
```

- [ ] **Step 1.5: Run tests, observe failures, iterate against real samples**

Run: `uv run pytest tests/missions/test_tgl_reader.py -v`

This step is the reverse-engineering step. The header / record layout above is the *current best guess* from the `Episode.tgl` hex dump in the spec. If the test fails:

1. Reproduce the failure with `python -c "from engine.missions.tgl_reader import read_tgl; r = read_tgl('sdk/Build/Data/TGL/Tutorial/Episode/Episode.tgl'); print(r.strings, r.sounds)"`.
2. Dump the sample with `xxd sdk/Build/Data/TGL/Tutorial/Episode/Episode.tgl | head -40` and trace each offset.
3. Common alternates to try: header size is 5 or 7 uint32s (not 6); length prefixes include the NUL or do not; UTF-16 length is in *characters* not bytes (so multiply by 2); the third field is `(uint32 len, ascii filename)` *with* a trailing NUL not in the count.
4. Adjust `_parse` until both `test_parse_tutorial_episode_one_entry` and a manual check on `game/data/TGL/Maelstrom/Maelstrom.tgl` produce sensible keys.

Acceptance: both `test_tgl_reader.py` tests pass *and* this one-liner prints "Ep1Title" through "Ep8Title" among other keys with non-empty values:

```bash
uv run python -c "from engine.missions.tgl_reader import read_tgl; t = read_tgl('game/data/TGL/Maelstrom/Maelstrom.tgl'); print({k: v for k, v in t.strings.items() if 'Ep' in k and 'Title' in k})"
```

- [ ] **Step 1.6: Add Maelstrom sample test**

Append to `tests/missions/test_tgl_reader.py`:

```python
def test_parse_maelstrom_episode_titles(maelstrom_tgl):
    if not maelstrom_tgl.is_file():
        pytest.skip(f"{maelstrom_tgl} not present (game install)")

    tgl = read_tgl(maelstrom_tgl)

    # Every episode of Maelstrom has an EpNTitle key in this database.
    for n in range(1, 9):
        key = f"Ep{n}Title"
        assert key in tgl.strings, f"missing {key}; got: {sorted(tgl.strings)[:20]}"
        assert tgl.strings[key], f"{key} is empty"
```

Run: `uv run pytest tests/missions/test_tgl_reader.py -v`. Both tests pass.

- [ ] **Step 1.7: Commit**

```bash
git add engine/missions/__init__.py engine/missions/tgl_reader.py tests/missions/
git commit -m "feat(missions): binary TGL reader"
```

---

## Task 2: Mission discovery

**Files:**

- Create: `engine/missions/discovery.py`
- Modify: `engine/missions/__init__.py`
- Create: `tests/missions/test_discovery.py`

Walks `sdk/Build/scripts/` looking for leaf directories whose name matches a `.py` file inside them with `def Initialize` at top level. Returns a `MissionRegistry`. Does **not** import the modules (importing causes side effects via the SDK loader).

- [ ] **Step 2.1: Write the data model + a failing test for the SDK layout**

Create `tests/missions/test_discovery.py`:

```python
"""MissionRegistry.discover walks sdk/Build/scripts to a typed tree."""
from pathlib import Path

import pytest

from engine.missions.discovery import (
    discover,
    MissionEntry,
    EpisodeEntry,
    FamilyEntry,
    MissionRegistry,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_ROOT = PROJECT_ROOT / "sdk" / "Build" / "scripts"


def test_discover_returns_registry():
    if not SCRIPTS_ROOT.is_dir():
        pytest.skip("SDK scripts not present")
    reg = discover(SCRIPTS_ROOT)
    assert isinstance(reg, MissionRegistry)
    assert isinstance(reg.families, list)
    assert reg.families  # at least one


def test_discover_finds_tutorial_missions():
    if not SCRIPTS_ROOT.is_dir():
        pytest.skip("SDK scripts not present")
    reg = discover(SCRIPTS_ROOT)
    fams = {f.dir_name: f for f in reg.families}
    assert "Tutorial" in fams

    tutorial = fams["Tutorial"]
    missions = [m.dir_name for ep in tutorial.episodes for m in ep.missions]
    for expected in ("M1Basic", "M2Objects", "M3Gameflow", "M4Complex"):
        assert expected in missions, f"missing {expected}; got {missions}"


def test_discover_finds_maelstrom_episode_grouping():
    if not SCRIPTS_ROOT.is_dir():
        pytest.skip("SDK scripts not present")
    reg = discover(SCRIPTS_ROOT)
    fams = {f.dir_name: f for f in reg.families}
    assert "Maelstrom" in fams
    eps = {ep.dir_name for ep in fams["Maelstrom"].episodes}
    # Maelstrom ships with at least these episode directories.
    for expected in ("Episode1", "Episode2", "Episode3"):
        assert expected in eps, f"missing {expected}; got {eps}"


def test_discover_module_name_format():
    if not SCRIPTS_ROOT.is_dir():
        pytest.skip("SDK scripts not present")
    reg = discover(SCRIPTS_ROOT)
    m1 = next(
        m for f in reg.families if f.dir_name == "Tutorial"
        for ep in f.episodes for m in ep.missions
        if m.dir_name == "M1Basic"
    )
    assert m1.module_name == "Custom.Tutorial.Episode.M1Basic.M1Basic"


def test_discover_synthetic_tree(tmp_path):
    """End-to-end on a tmp_path tree — no SDK assets required."""
    custom = tmp_path / "Custom" / "Tutorial" / "Episode"
    (custom / "MX" ).mkdir(parents=True)
    (custom / "MX" / "MX.py").write_text("def Initialize(mission): pass\n")
    # A dir whose .py has no Initialize — must NOT be discovered.
    (custom / "Skip").mkdir()
    (custom / "Skip" / "Skip.py").write_text("# nothing here\n")
    # A dir whose name doesn't match its .py — must NOT be discovered.
    (custom / "Mismatch").mkdir()
    (custom / "Mismatch" / "Other.py").write_text("def Initialize(m): pass\n")

    reg = discover(tmp_path)
    found = [
        m.dir_name
        for f in reg.families for ep in f.episodes for m in ep.missions
    ]
    assert found == ["MX"]
```

- [ ] **Step 2.2: Run tests, verify they fail with import error**

Run: `uv run pytest tests/missions/test_discovery.py -v`
Expected: ImportError on `engine.missions.discovery`.

- [ ] **Step 2.3: Implement discovery**

Create `engine/missions/discovery.py`:

```python
"""Mission discovery — walks sdk/Build/scripts to a MissionRegistry."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_INITIALIZE_RE = re.compile(rb"^def\s+Initialize\s*\(", re.MULTILINE)

# Known family roots: (relative_path_under_scripts, family_dir_name)
# Paths are expressed as POSIX-style strings so the walker can match them
# against rglob results without worrying about OS path separators.
_FAMILY_ROOTS: list[tuple[str, str]] = [
    ("Custom/Tutorial",     "Tutorial"),
    ("Maelstrom",           "Maelstrom"),
    ("Multiplayer",         "Multiplayer"),
]


@dataclass
class MissionEntry:
    module_name: str
    dir_name: str
    display_name: str = ""    # filled by name_resolver later


@dataclass
class EpisodeEntry:
    dir_name: str
    missions: list[MissionEntry] = field(default_factory=list)
    display_name: str = ""


@dataclass
class FamilyEntry:
    dir_name: str
    episodes: list[EpisodeEntry] = field(default_factory=list)
    display_name: str = ""


@dataclass
class MissionRegistry:
    families: list[FamilyEntry] = field(default_factory=list)


def discover(scripts_root: Path | str) -> MissionRegistry:
    scripts_root = Path(scripts_root)
    by_family: dict[str, dict[str, list[MissionEntry]]] = {}

    for family_rel, family_name in _FAMILY_ROOTS:
        family_root = scripts_root / family_rel
        if not family_root.is_dir():
            continue
        for mission_dir in _iter_leaf_dirs(family_root):
            entry = _maybe_mission(mission_dir, scripts_root)
            if entry is None:
                continue
            episode_dir = mission_dir.parent.name
            by_family.setdefault(family_name, {}).setdefault(
                episode_dir, []).append(entry)

    reg = MissionRegistry()
    for family_name, episodes in by_family.items():
        fam = FamilyEntry(dir_name=family_name)
        for episode_dir, missions in episodes.items():
            ep = EpisodeEntry(dir_name=episode_dir, missions=sorted(
                missions, key=lambda m: m.dir_name))
            fam.episodes.append(ep)
        fam.episodes.sort(key=lambda e: e.dir_name)
        reg.families.append(fam)
    reg.families.sort(key=lambda f: f.dir_name)
    return reg


def _iter_leaf_dirs(root: Path):
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        if any(p.startswith("__") for p in path.parts):
            continue
        yield path


def _maybe_mission(mission_dir: Path, scripts_root: Path) -> MissionEntry | None:
    candidate = mission_dir / f"{mission_dir.name}.py"
    if not candidate.is_file():
        # Case-insensitive fallback for filesystems that preserve case
        # but the on-disk name differs.
        for child in mission_dir.iterdir():
            if (child.is_file()
                    and child.suffix == ".py"
                    and child.stem.lower() == mission_dir.name.lower()):
                candidate = child
                break
        else:
            return None
    try:
        body = candidate.read_bytes()
    except OSError:
        return None
    if not _INITIALIZE_RE.search(body):
        return None

    rel = mission_dir.relative_to(scripts_root)
    module_name = ".".join(rel.parts + (mission_dir.name,))
    return MissionEntry(module_name=module_name, dir_name=mission_dir.name)
```

- [ ] **Step 2.4: Re-export from package**

Edit `engine/missions/__init__.py`:

```python
"""Mission discovery, name resolution, and TGL reading."""
from engine.missions.discovery import (
    discover,
    MissionEntry,
    EpisodeEntry,
    FamilyEntry,
    MissionRegistry,
)
from engine.missions.tgl_reader import read_tgl, TGLFile, TGLParseError

__all__ = [
    "discover",
    "MissionEntry", "EpisodeEntry", "FamilyEntry", "MissionRegistry",
    "read_tgl", "TGLFile", "TGLParseError",
]
```

- [ ] **Step 2.5: Run tests and verify**

Run: `uv run pytest tests/missions/test_discovery.py -v`
Expected: all 5 tests pass (test_discover_synthetic_tree must pass on any platform without SDK assets).

- [ ] **Step 2.6: Commit**

```bash
git add engine/missions/discovery.py engine/missions/__init__.py tests/missions/test_discovery.py
git commit -m "feat(missions): registry + SDK script discovery"
```

---

## Task 3: Name resolver

**Files:**

- Create: `engine/missions/name_resolver.py`
- Create: `tests/missions/test_name_resolver.py`

Per-family adapters that produce display names. Wraps every adapter in try/except and falls back to the directory name on any failure so a single broken file can't brick the picker.

- [ ] **Step 3.1: Write the failing test**

Create `tests/missions/test_name_resolver.py`:

```python
"""Per-family name adapters."""
from pathlib import Path
import sys
import types

import pytest

from engine.missions.tgl_reader import TGLFile
from engine.missions.name_resolver import (
    resolve_family,
    resolve_episode,
    resolve_mission,
)


@pytest.fixture
def fake_tgl(monkeypatch):
    """Make read_tgl return a constructed TGLFile per path."""
    store: dict[str, TGLFile] = {}

    def _fake(path):
        key = Path(path).as_posix()
        for k, tgl in store.items():
            if key.endswith(k):
                return tgl
        from engine.missions.tgl_reader import TGLParseError
        raise TGLParseError(f"no fake for {path}")

    monkeypatch.setattr("engine.missions.name_resolver.read_tgl", _fake)
    return store


def test_family_known_names_pretty():
    assert resolve_family("Tutorial") == "Tutorial"
    assert resolve_family("Maelstrom") == "Maelstrom"
    assert resolve_family("Multiplayer") == "Multiplayer"
    # Unknown families fall back to their dir name.
    assert resolve_family("Custom") == "Custom"


def test_maelstrom_episode_lookup(fake_tgl):
    fake_tgl["Maelstrom/Maelstrom.tgl"] = TGLFile(strings={
        "Ep1Title": "The Long Night",
    })
    assert resolve_episode("Maelstrom", "Episode1") == "The Long Night"
    # Missing key → dir-name fallback.
    assert resolve_episode("Maelstrom", "Episode9") == "Episode9"


def test_maelstrom_mission_lookup(fake_tgl):
    fake_tgl["Maelstrom/Maelstrom.tgl"] = TGLFile(strings={
        "E1M1Title": "Shakedown",
    })
    assert resolve_mission(
        "Maelstrom", "Episode1", "E1M1",
        "Maelstrom.Episode1.E1M1.E1M1",
    ) == "Shakedown"
    assert resolve_mission(
        "Maelstrom", "Episode2", "E2M99",
        "Maelstrom.Episode2.E2M99.E2M99",
    ) == "E2M99"


def test_multiplayer_mission_uses_module_callback(monkeypatch):
    mod = types.ModuleType("Multiplayer.Episode.MissionX.MissionXName")
    mod.GetMissionName = lambda: "Test Skirmish"
    monkeypatch.setitem(
        sys.modules,
        "Multiplayer.Episode.MissionX.MissionXName",
        mod,
    )
    assert resolve_mission(
        "Multiplayer", "Episode", "MissionX",
        "Multiplayer.Episode.MissionX.MissionX",
    ) == "Test Skirmish"


def test_multiplayer_falls_back_when_module_raises(monkeypatch):
    mod = types.ModuleType("Multiplayer.Episode.MissionBoom.MissionBoomName")
    def boom():
        raise RuntimeError("nope")
    mod.GetMissionName = boom
    monkeypatch.setitem(
        sys.modules,
        "Multiplayer.Episode.MissionBoom.MissionBoomName",
        mod,
    )
    assert resolve_mission(
        "Multiplayer", "Episode", "MissionBoom",
        "Multiplayer.Episode.MissionBoom.MissionBoom",
    ) == "MissionBoom"


def test_tutorial_mission_lookup(fake_tgl):
    fake_tgl["Tutorial/Tutorial.tgl"] = TGLFile(strings={
        "M1Basic": "Basic Maneuvers",
    })
    assert resolve_mission(
        "Tutorial", "Episode", "M1Basic",
        "Custom.Tutorial.Episode.M1Basic.M1Basic",
    ) == "Basic Maneuvers"
```

- [ ] **Step 3.2: Run tests, verify failure**

Run: `uv run pytest tests/missions/test_name_resolver.py -v`
Expected: ImportError on `engine.missions.name_resolver`.

- [ ] **Step 3.3: Implement the resolver**

Create `engine/missions/name_resolver.py`:

```python
"""Per-family display-name resolution.

Each adapter is wrapped so any exception falls back to the directory
name — a broken TGL or a misnamed module never bricks the picker.
"""
from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Optional

from engine.missions.tgl_reader import read_tgl, TGLFile

PROJECT_ROOT = Path(__file__).parent.parent.parent
TGL_ROOTS: tuple[Path, ...] = (
    PROJECT_ROOT / "sdk" / "Build" / "Data" / "TGL",
    PROJECT_ROOT / "game" / "data" / "TGL",
)


def resolve_family(family_dir: str) -> str:
    # Hardcoded for v1 — the three known families ship with friendly names
    # equal to their directory names. Unknown families also return dir.
    return family_dir


def resolve_episode(family_dir: str, episode_dir: str) -> str:
    if family_dir == "Maelstrom":
        m = _match_episode_number(episode_dir)
        if m is not None:
            return _tgl_string(
                "Maelstrom/Maelstrom.tgl", f"Ep{m}Title", episode_dir)
    return episode_dir


def resolve_mission(family_dir: str, episode_dir: str,
                    mission_dir: str, module_name: str) -> str:
    if family_dir == "Multiplayer":
        name_mod = module_name.rsplit(".", 1)[0] + "." + mission_dir + "Name"
        try:
            mod = importlib.import_module(name_mod)
            s = mod.GetMissionName()
        except Exception:
            return mission_dir
        return str(s) if s else mission_dir

    if family_dir == "Maelstrom":
        return _tgl_string(
            "Maelstrom/Maelstrom.tgl", f"{mission_dir}Title", mission_dir)

    if family_dir == "Tutorial":
        return _tgl_string(
            "Tutorial/Tutorial.tgl", mission_dir, mission_dir)

    return mission_dir


def _match_episode_number(episode_dir: str) -> Optional[str]:
    if episode_dir.startswith("Episode") and episode_dir[7:].isdigit():
        return episode_dir[7:]
    return None


@lru_cache(maxsize=None)
def _load_tgl(relpath: str) -> Optional[TGLFile]:
    for root in TGL_ROOTS:
        path = root / relpath
        if path.is_file():
            try:
                return read_tgl(path)
            except Exception:
                return None
    return None


def _tgl_string(relpath: str, key: str, fallback: str) -> str:
    tgl = _load_tgl(relpath)
    if tgl is None:
        return fallback
    value = tgl.strings.get(key)
    if not value:
        return fallback
    return value
```

- [ ] **Step 3.4: Run tests, expect pass**

Run: `uv run pytest tests/missions/test_name_resolver.py -v`
Expected: all six tests pass.

- [ ] **Step 3.5: Commit**

```bash
git add engine/missions/name_resolver.py tests/missions/test_name_resolver.py
git commit -m "feat(missions): per-family display-name resolver"
```

---

## Task 4: Wire name resolution into discovery

**Files:**

- Modify: `engine/missions/discovery.py`
- Create: `tests/missions/test_registry.py`

The current `discover()` leaves `display_name=""` on every entry. Now we backfill those by calling the resolver.

- [ ] **Step 4.1: Write failing test for populated display names**

Create `tests/missions/test_registry.py`:

```python
"""End-to-end: discover() returns entries with display_name filled."""
from pathlib import Path

import pytest

from engine.missions import discover

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_ROOT = PROJECT_ROOT / "sdk" / "Build" / "scripts"


def test_display_names_are_non_empty():
    if not SCRIPTS_ROOT.is_dir():
        pytest.skip("SDK scripts not present")
    reg = discover(SCRIPTS_ROOT)
    for fam in reg.families:
        assert fam.display_name, f"family {fam.dir_name!r} has empty display_name"
        for ep in fam.episodes:
            assert ep.display_name, (
                f"episode {fam.dir_name}/{ep.dir_name!r} has empty display_name")
            for m in ep.missions:
                assert m.display_name, (
                    f"mission {fam.dir_name}/{ep.dir_name}/{m.dir_name!r}"
                    " has empty display_name")


def test_display_name_falls_back_to_dir_when_unknown():
    """A family root that doesn't exist in TGL still produces dir-name labels."""
    if not SCRIPTS_ROOT.is_dir():
        pytest.skip("SDK scripts not present")
    reg = discover(SCRIPTS_ROOT)
    tutorial = next(f for f in reg.families if f.dir_name == "Tutorial")
    m1 = next(
        m for ep in tutorial.episodes for m in ep.missions
        if m.dir_name == "M1Basic"
    )
    # We don't assert the *value* (depends on TGL availability) — only that
    # it's a non-empty string, populated by resolve_mission.
    assert isinstance(m1.display_name, str) and m1.display_name
```

- [ ] **Step 4.2: Run, verify it fails**

Run: `uv run pytest tests/missions/test_registry.py -v`
Expected: `AssertionError: family 'Tutorial' has empty display_name`.

- [ ] **Step 4.3: Modify discovery to call the resolver**

Edit `engine/missions/discovery.py` — at the bottom of `discover()`, before returning `reg`:

```python
    # Backfill display names. Imported lazily because name_resolver imports
    # tgl_reader which doesn't need to be paid-for in tests that only care
    # about tree shape.
    from engine.missions import name_resolver as nr
    for fam in reg.families:
        fam.display_name = nr.resolve_family(fam.dir_name)
        for ep in fam.episodes:
            ep.display_name = nr.resolve_episode(fam.dir_name, ep.dir_name)
            for m in ep.missions:
                m.display_name = nr.resolve_mission(
                    fam.dir_name, ep.dir_name, m.dir_name, m.module_name)
    return reg
```

(Remove the previous `return reg` if duplicated.)

- [ ] **Step 4.4: Run all missions tests**

Run: `uv run pytest tests/missions/ -v`
Expected: every test passes.

- [ ] **Step 4.5: Commit**

```bash
git add engine/missions/discovery.py tests/missions/test_registry.py
git commit -m "feat(missions): populate display_name during discover()"
```

---

## Task 5: UiPanel center anchor — Python + RCSS

**Files:**

- Modify: `engine/ui/panel.py`
- Modify: `native/assets/ui/components.rcss`
- Create: `tests/ui/test_panel_center.py`

The Python side just needs the `Anchor` literal to accept `"center"`. The native side change is Task 6.

- [ ] **Step 5.1: Failing test**

Create `tests/ui/test_panel_center.py`:

```python
"""UiPanel supports anchor='center'."""
import pytest

from engine.ui import UiPanel


def test_center_anchor_is_accepted(fake_dom):
    panel = UiPanel(id="c", anchor="center", width_vw=40, height_vh=70)
    panels = list(fake_dom._panels.values())
    assert len(panels) == 1
    assert panels[0].anchor == "center"
    panel.destroy()


def test_default_anchor_unchanged(fake_dom):
    """Regression: the default is still top-right after adding 'center'."""
    panel = UiPanel(id="d", width_vw=20, height_vh=20)
    assert list(fake_dom._panels.values())[0].anchor == "top-right"
    panel.destroy()
```

- [ ] **Step 5.2: Run, observe failure**

Run: `uv run pytest tests/ui/test_panel_center.py -v`
Expected: a type/Literal error from the `anchor="center"` argument when running with strict typing, or no test failure on plain Python (Literal is a hint, not enforced). If both pass on plain Python, proceed — the test still pins the runtime behaviour.

In practice expect: tests pass on plain Python. The functional change is in Task 6.

- [ ] **Step 5.3: Update the Anchor literal**

Edit `engine/ui/panel.py:17`:

```python
Anchor = Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]
```

(Add `"center"` at the end.)

- [ ] **Step 5.4: Add CSS for centered panels**

Append to `native/assets/ui/components.rcss` (use the existing indentation style and `dp` units already in the file):

```rcss
/* Centered modal panels — anchor="center" via PanelDocument.cc. */
/* The actual positioning is applied as inline style by PanelDocument; */
/* this class is reserved for any per-modal styling we add later.       */
.bc-panel-center {
}
```

The actual positioning happens via inline `left/top/transform` properties set in `PanelDocument.cc` (Task 6) so the class itself can stay empty for now. Keeping the selector lets us hang styles off it without re-doing the binding.

- [ ] **Step 5.5: Run UI tests**

Run: `uv run pytest tests/ui/ -v`
Expected: all UI tests pass including the new ones.

- [ ] **Step 5.6: Commit**

```bash
git add engine/ui/panel.py native/assets/ui/components.rcss tests/ui/test_panel_center.py
git commit -m "feat(ui): UiPanel anchor='center'"
```

---

## Task 6: PanelDocument C++ — center branch

**Files:**

- Modify: `native/src/ui/PanelDocument.cc:58-61`

This is the only native code change in the plan. It adds one branch and rebuilds.

- [ ] **Step 6.1: Add the center branch**

Edit `native/src/ui/PanelDocument.cc` — extend the anchor cascade so it reads:

```cpp
    if      (anchor == "top-left")     { doc_->SetProperty("left",  "10dp"); doc_->SetProperty("top",    "10dp"); }
    else if (anchor == "top-right")    { doc_->SetProperty("right", "10dp"); doc_->SetProperty("top",    "10dp"); }
    else if (anchor == "bottom-left")  { doc_->SetProperty("left",  "10dp"); doc_->SetProperty("bottom", "10dp"); }
    else if (anchor == "bottom-right") { doc_->SetProperty("right", "10dp"); doc_->SetProperty("bottom", "10dp"); }
    else if (anchor == "center") {
        doc_->SetProperty("left",      "50%");
        doc_->SetProperty("top",       "50%");
        doc_->SetProperty("transform", "translate(-50%, -50%)");
    }
```

- [ ] **Step 6.2: Rebuild**

Run: `cmake --build build -j`
Expected: builds cleanly. If a stale binary lives at `native/build/...` or `build/bin/...`, delete it — the CLAUDE.md hard rule is one tree at `build/`.

- [ ] **Step 6.3: Manual smoke (host running)**

Run: `./build/open_stbc` (headed). The host still boots without errors. (The picker isn't wired yet; this just confirms the existing anchors still work.)

- [ ] **Step 6.4: Commit**

```bash
git add native/src/ui/PanelDocument.cc
git commit -m "feat(ui): center anchor in PanelDocument"
```

---

## Task 7: UiPanel footer button

**Files:**

- Modify: `engine/ui/panel.py`
- Modify: `native/assets/ui/components.rcss`
- Create: `tests/ui/test_panel_footer.py`

Adds a single-slot footer button row at the bottom of a panel. First call creates the container; subsequent calls re-label / re-bind the existing button. `destroy()` removes it.

- [ ] **Step 7.1: Failing tests**

Create `tests/ui/test_panel_footer.py`:

```python
"""UiPanel.set_footer_button creates one right-aligned button at the bottom."""
import pytest

from engine.ui import UiPanel


def test_footer_creates_one_container_and_button(fake_dom):
    panel = UiPanel(id="f", width_vw=30, height_vh=30, title="T")
    btn = panel.set_footer_button("Cancel")
    # The panel root should now contain exactly: header, body, footer.
    root = fake_dom.panel_root(panel.panel_id)
    classes = [
        " ".join(fake_dom.element(c).classes)
        for c in fake_dom.children(root)
    ]
    assert classes == ["bc-panel-header", "bc-panel-body", "bc-panel-footer"]
    footer_id = fake_dom.children(root)[-1]
    footer_kids = fake_dom.children(footer_id)
    assert len(footer_kids) == 1
    assert "bc-button" in fake_dom.element(footer_kids[0]).classes
    assert fake_dom.element(footer_kids[0]).text == "Cancel"
    assert btn is not None


def test_footer_click_fires_callback(fake_dom):
    panel = UiPanel(id="f", width_vw=30, height_vh=30, title="T")
    seen = []
    panel.set_footer_button("Cancel", on_click=lambda: seen.append("clicked"))
    root = fake_dom.panel_root(panel.panel_id)
    footer_id = [
        c for c in fake_dom.children(root)
        if "bc-panel-footer" in fake_dom.element(c).classes
    ][0]
    btn_id = fake_dom.children(footer_id)[0]
    fake_dom.fire_click(btn_id)
    assert seen == ["clicked"]


def test_footer_relabel_reuses_container(fake_dom):
    panel = UiPanel(id="f", width_vw=30, height_vh=30, title="T")
    panel.set_footer_button("Cancel")
    panel.set_footer_button("Close", on_click=lambda: None)
    root = fake_dom.panel_root(panel.panel_id)
    footers = [
        c for c in fake_dom.children(root)
        if "bc-panel-footer" in fake_dom.element(c).classes
    ]
    assert len(footers) == 1
    btn_id = fake_dom.children(footers[0])[0]
    assert fake_dom.element(btn_id).text == "Close"


def test_no_footer_when_set_footer_button_never_called(fake_dom):
    panel = UiPanel(id="f", width_vw=30, height_vh=30, title="T")
    root = fake_dom.panel_root(panel.panel_id)
    classes = [
        " ".join(fake_dom.element(c).classes)
        for c in fake_dom.children(root)
    ]
    assert "bc-panel-footer" not in " ".join(classes)
```

- [ ] **Step 7.2: Run, observe failures**

Run: `uv run pytest tests/ui/test_panel_footer.py -v`
Expected: AttributeError — no `set_footer_button` on `UiPanel`.

- [ ] **Step 7.3: Implement `set_footer_button`**

Edit `engine/ui/panel.py` — add these instance attributes to `__init__` (alongside the existing `self._title_element_id`, etc.):

```python
        self._footer_element_id: Optional[int] = None
        self._footer_button: Optional[UiButton] = None
```

Add the method (placement: alongside `set_title`, before `_handle_toggle_click`):

```python
    def set_footer_button(self, label: str,
                          on_click: Optional[Callable[[], None]] = None,
    ) -> UiButton:
        """Create or re-bind the panel's single footer button.

        The footer is created lazily on first call. Subsequent calls
        update the label and on_click on the same button without
        re-creating the container.
        """
        if self._footer_element_id is None:
            self._footer_element_id = bindings.append_div(
                bindings.panel_root(self.panel_id), "bc-panel-footer")
            self._footer_button = UiButton(
                parent_element=self._footer_element_id,
                label=label, menu_level=3, selected=False,
                on_click=on_click,
            )
        else:
            assert self._footer_button is not None
            self._footer_button.set_label(label)
            self._footer_button.on_click = on_click
        return self._footer_button
```

- [ ] **Step 7.4: CSS for footer + right-aligned button**

Append to `native/assets/ui/components.rcss`:

```rcss
.bc-panel-footer {
    display: flex;
    justify-content: flex-end;
    padding: 8dp;
}
```

- [ ] **Step 7.5: Run, verify**

Run: `uv run pytest tests/ui/test_panel_footer.py -v`
Expected: all four tests pass.

Run: `uv run pytest tests/ui/ -v`
Expected: full UI suite still green.

- [ ] **Step 7.6: Commit**

```bash
git add engine/ui/panel.py native/assets/ui/components.rcss tests/ui/test_panel_footer.py
git commit -m "feat(ui): single-slot footer button on UiPanel"
```

---

## Task 8: KEY_ESCAPE binding

**Files:**

- Modify: `native/src/host/host_bindings.cc:389`

Adds `KEY_ESCAPE` next to the existing `KEY_F7`/`KEY_F8`/`KEY_F9` constants so the host loop can poll it.

- [ ] **Step 8.1: Add the binding**

Edit `native/src/host/host_bindings.cc` — after `keys.attr("KEY_F9") = GLFW_KEY_F9;` add:

```cpp
    keys.attr("KEY_ESCAPE") = GLFW_KEY_ESCAPE;
```

- [ ] **Step 8.2: Rebuild**

Run: `cmake --build build -j`

- [ ] **Step 8.3: Smoke test the binding**

Run:
```bash
uv run python -c "import _open_stbc_host as h; print(h.keys.KEY_ESCAPE)"
```
Expected: prints `256` (GLFW_KEY_ESCAPE).

- [ ] **Step 8.4: Commit**

```bash
git add native/src/host/host_bindings.cc
git commit -m "feat(input): expose KEY_ESCAPE"
```

---

## Task 9: MissionPicker

**Files:**

- Create: `engine/mission_picker.py`
- Create: `tests/test_mission_picker.py`

The picker is a pure consumer of `engine.ui` and `engine.missions`. Build-on-open, destroy-on-close.

- [ ] **Step 9.1: Failing tests**

Create `tests/test_mission_picker.py`:

```python
"""MissionPicker — opens a centered modal, closes on pick / cancel / ESC."""
import pytest

from engine.missions.discovery import (
    MissionRegistry, FamilyEntry, EpisodeEntry, MissionEntry,
)
from engine.mission_picker import MissionPicker


@pytest.fixture
def fake_dom(monkeypatch):
    from engine.ui import bindings as bindings_module
    from engine.ui._dom import FakeDom
    dom = FakeDom()
    monkeypatch.setattr(bindings_module, "_active_dom", dom)
    return dom


@pytest.fixture
def two_family_registry():
    return MissionRegistry(families=[
        FamilyEntry(
            dir_name="Tutorial", display_name="Tutorial",
            episodes=[EpisodeEntry(
                dir_name="Episode", display_name="Episode",
                missions=[
                    MissionEntry(
                        module_name="Custom.Tutorial.Episode.M1.M1",
                        dir_name="M1", display_name="Basic Maneuvers"),
                    MissionEntry(
                        module_name="Custom.Tutorial.Episode.M2.M2",
                        dir_name="M2", display_name="Objects"),
                ],
            )],
        ),
        FamilyEntry(
            dir_name="Maelstrom", display_name="Maelstrom",
            episodes=[
                EpisodeEntry(
                    dir_name="Episode1", display_name="The Long Night",
                    missions=[MissionEntry(
                        module_name="Maelstrom.Episode1.E1M1.E1M1",
                        dir_name="E1M1", display_name="Shakedown")],
                ),
                EpisodeEntry(
                    dir_name="Episode2", display_name="The Second Wave",
                    missions=[MissionEntry(
                        module_name="Maelstrom.Episode2.E2M0.E2M0",
                        dir_name="E2M0", display_name="Prologue")],
                ),
            ],
        ),
    ])


def test_open_creates_centered_panel(fake_dom, two_family_registry):
    picker = MissionPicker(
        registry=two_family_registry,
        on_load=lambda name: None,
        on_cancel=lambda: None,
    )
    picker.open()
    assert picker.is_open()
    panels = list(fake_dom._panels.values())
    assert len(panels) == 1
    assert panels[0].anchor == "center"


def test_open_builds_family_and_episode_collapsibles(fake_dom, two_family_registry):
    picker = MissionPicker(
        registry=two_family_registry,
        on_load=lambda name: None,
        on_cancel=lambda: None,
    )
    picker.open()
    # Walk the DOM for all elements whose first class is bc-collapsible-header.
    header_texts = [
        fake_dom.element(eid).text
        for eid, el in fake_dom._elements.items()
        if "bc-collapsible-header-title" in el.classes
    ]
    # Tutorial has one episode named "Episode" → collapse one level: should
    # not produce an episode collapsible row labelled "Episode".
    assert "Tutorial" in header_texts
    assert "Maelstrom" in header_texts
    assert "The Long Night" in header_texts
    assert "The Second Wave" in header_texts
    # The redundant single-episode "Episode" row must not appear under Tutorial.
    assert header_texts.count("Episode") == 0


def test_picking_a_mission_closes_panel_and_invokes_callback(
        fake_dom, two_family_registry):
    chosen: list[str] = []
    picker = MissionPicker(
        registry=two_family_registry,
        on_load=lambda name: chosen.append(name),
        on_cancel=lambda: None,
    )
    picker.open()
    # Locate the "Basic Maneuvers" button.
    btn = next(
        eid for eid, el in fake_dom._elements.items()
        if el.text == "Basic Maneuvers" and "bc-button" in el.classes
    )
    fake_dom.fire_click(btn)
    assert chosen == ["Custom.Tutorial.Episode.M1.M1"]
    assert not picker.is_open()
    assert not fake_dom._panels   # panel destroyed


def test_cancel_button_closes_and_invokes_on_cancel(
        fake_dom, two_family_registry):
    cancelled: list[int] = []
    picker = MissionPicker(
        registry=two_family_registry,
        on_load=lambda name: None,
        on_cancel=lambda: cancelled.append(1),
    )
    picker.open()
    cancel = next(
        eid for eid, el in fake_dom._elements.items()
        if el.text == "Cancel" and "bc-button" in el.classes
    )
    fake_dom.fire_click(cancel)
    assert cancelled == [1]
    assert not picker.is_open()


def test_handle_key_esc_cancels_when_open(fake_dom, two_family_registry):
    cancelled: list[int] = []
    picker = MissionPicker(
        registry=two_family_registry,
        on_load=lambda name: None,
        on_cancel=lambda: cancelled.append(1),
    )
    picker.open()
    picker.handle_key_esc()
    assert cancelled == [1]
    assert not picker.is_open()


def test_handle_key_esc_noop_when_closed(fake_dom, two_family_registry):
    picker = MissionPicker(
        registry=two_family_registry,
        on_load=lambda name: None,
        on_cancel=lambda: pytest.fail("on_cancel must not fire"),
    )
    picker.handle_key_esc()
    assert not picker.is_open()


def test_close_is_idempotent(fake_dom, two_family_registry):
    picker = MissionPicker(
        registry=two_family_registry,
        on_load=lambda name: None,
        on_cancel=lambda: None,
    )
    picker.open()
    picker.close()
    picker.close()       # second call must not raise
    assert not picker.is_open()
```

- [ ] **Step 9.2: Run, verify import failure**

Run: `uv run pytest tests/test_mission_picker.py -v`
Expected: ImportError on `engine.mission_picker`.

- [ ] **Step 9.3: Implement MissionPicker**

Create `engine/mission_picker.py`:

```python
"""MissionPicker — centered modal that lists every discoverable mission
and routes a click to a swap-mission callback.

This module is a pure consumer of engine.ui and engine.missions and has
no knowledge of how a mission actually loads — the host wires up the
on_load callback.
"""
from __future__ import annotations

from typing import Callable, Optional

from engine.missions import MissionEntry, MissionRegistry
from engine.ui import UiPanel

_SKIP_EPISODE_LEVEL = {"Episode", "."}


class MissionPicker:
    def __init__(self, *,
                 registry: MissionRegistry,
                 on_load: Callable[[str], None],
                 on_cancel: Callable[[], None]):
        self._registry = registry
        self._on_load = on_load
        self._on_cancel = on_cancel
        self._panel: Optional[UiPanel] = None

    def is_open(self) -> bool:
        return self._panel is not None

    def open(self) -> None:
        if self._panel is not None:
            return
        panel = UiPanel(id="mission-picker", anchor="center",
                        width_vw=42.0, height_vh=72.0,
                        title="Load Mission")
        for family in self._registry.families:
            f_row = panel.collapsible(family.display_name,
                                      menu_level=1, expanded=False)
            for episode in family.episodes:
                skip_episode = (
                    len(family.episodes) == 1
                    and episode.dir_name in _SKIP_EPISODE_LEVEL
                )
                parent = (f_row if skip_episode
                          else f_row.collapsible(episode.display_name,
                                                 menu_level=2, expanded=False))
                for mission in episode.missions:
                    parent.button(
                        mission.display_name,
                        on_click=self._make_pick_callback(mission),
                    )
        panel.set_footer_button("Cancel", on_click=self._cancel)
        self._panel = panel

    def close(self) -> None:
        if self._panel is None:
            return
        self._panel.destroy()
        self._panel = None

    def handle_key_esc(self) -> None:
        if self.is_open():
            self._cancel()

    def _make_pick_callback(self, mission: MissionEntry):
        def _pick():
            self.close()
            self._on_load(mission.module_name)
        return _pick

    def _cancel(self) -> None:
        self.close()
        self._on_cancel()
```

- [ ] **Step 9.4: Tweak collapsible header class assumption if needed**

The picker test asserts headers carry the class `bc-collapsible-header-title`. Verify this against the existing `engine/ui/collapsible.py`:

```bash
grep "bc-collapsible-header" engine/ui/collapsible.py
```

If the title element uses a different class, adjust the test accordingly to match what the collapsible component actually emits. (Either way, the *correct* assertion is "the visible title text appears as a header somewhere in the DOM". Walking by class is the simplest way to express that.)

- [ ] **Step 9.5: Run tests, verify pass**

Run: `uv run pytest tests/test_mission_picker.py -v`
Expected: all seven tests pass.

- [ ] **Step 9.6: Commit**

```bash
git add engine/mission_picker.py tests/test_mission_picker.py
git commit -m "feat(picker): MissionPicker modal with cancel + ESC"
```

---

## Task 10: Extract `reset_sdk_globals` from `_init_mission`

**Files:**

- Modify: `engine/host_loop.py:337-374`
- Create: `tests/host/test_mission_session.py` (just the reset test for now)

Before introducing `MissionSession`, factor out the SDK-reset prelude so both the existing `_init_mission` path and the future swap path share it.

- [ ] **Step 10.1: Failing test for `reset_sdk_globals`**

Create `tests/host/test_mission_session.py`:

```python
"""MissionSession + reset_sdk_globals — backend for in-process mission swaps."""
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_reset_sdk_globals_clears_state():
    """After reset, the five SDK globals listed in the spec are empty."""
    # Import sequence mirrors _setup_sdk's order.
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from tools import mission_harness
    mission_harness.setup_sdk()

    import App
    from engine.appc.placement import _waypoint_registry
    from engine.host_loop import reset_sdk_globals

    App.g_kTimerManager._timers["x"] = object()
    App.g_kRealtimeTimerManager._timers["y"] = object()
    App.g_kEventManager._broadcast_handlers["t"] = [object()]
    App.g_kSetManager._sets["s"] = object()
    _waypoint_registry["w"] = object()
    App._next_event_type_id = 999

    reset_sdk_globals()

    assert App.g_kTimerManager._time == 0.0
    assert App.g_kTimerManager._timers == {}
    assert App.g_kRealtimeTimerManager._time == 0.0
    assert App.g_kRealtimeTimerManager._timers == {}
    assert App.g_kEventManager._broadcast_handlers == {}
    assert App.g_kSetManager._sets == {}
    assert _waypoint_registry == {}
    assert App._next_event_type_id == 200
```

- [ ] **Step 10.2: Run, verify failure**

Run: `uv run pytest tests/host/test_mission_session.py -v`
Expected: `ImportError: cannot import name 'reset_sdk_globals' from 'engine.host_loop'`.

- [ ] **Step 10.3: Extract the helper**

Edit `engine/host_loop.py`. Add this function above `_init_mission`:

```python
def reset_sdk_globals() -> None:
    """Clear the SDK globals that a mission populates.

    Called once at start-of-mission and again on every in-process swap.
    Keep this list in lockstep with what the SDK actually mutates.
    """
    import App
    from engine.appc.placement import _waypoint_registry

    App.g_kTimerManager._time = 0.0
    App.g_kTimerManager._timers.clear()
    App.g_kRealtimeTimerManager._time = 0.0
    App.g_kRealtimeTimerManager._timers.clear()
    App.g_kEventManager._broadcast_handlers.clear()
    App.g_kSetManager._sets.clear()
    _waypoint_registry.clear()
    App._next_event_type_id = 200
```

Replace the corresponding lines inside `_init_mission`:

```python
    # Reset state per session (mirror tools/gameloop_harness.py).
    App.g_kTimerManager._time = 0.0
    App.g_kTimerManager._timers.clear()
    App.g_kRealtimeTimerManager._time = 0.0
    App.g_kRealtimeTimerManager._timers.clear()
    App.g_kEventManager._broadcast_handlers.clear()
    App.g_kSetManager._sets.clear()
    _waypoint_registry.clear()
    App._next_event_type_id = 200
```

with:

```python
    reset_sdk_globals()
```

The two `import App` / `from engine.appc.placement import _waypoint_registry` lines inside `_init_mission` can stay; remove them if and only if no other code in `_init_mission` needs them after the replacement (it doesn't, since the only remaining `App` references are below this block — verify with a quick re-read).

- [ ] **Step 10.4: Verify**

Run: `uv run pytest tests/host/test_mission_session.py -v tests/host/test_host_loop_unit.py -v`
Expected: new test passes; existing `_init_mission` tests still pass.

- [ ] **Step 10.5: Commit**

```bash
git add engine/host_loop.py tests/host/test_mission_session.py
git commit -m "refactor(host): extract reset_sdk_globals helper"
```

---

## Task 11: MissionSession + HostController + pending swap

**Files:**

- Modify: `engine/host_loop.py`
- Modify: `tests/host/test_mission_session.py`

Encapsulates per-mission render state in `MissionSession` and adds a `HostController` whose `swap_mission()` queues a swap that drains at the start of the next tick. The actual `run()` integration happens in Task 12.

- [ ] **Step 11.1: Add tests for session lifecycle**

Append to `tests/host/test_mission_session.py`:

```python
def test_mission_session_teardown_drops_instances():
    """teardown destroys every renderer instance the session created."""
    from engine.host_loop import MissionSession

    destroyed: list[int] = []

    class FakeRenderer:
        def destroy_instance(self, iid):
            destroyed.append(iid)

    sess = MissionSession(mission_name="x",
                          ship_instances={"shipA": 11, "shipB": 12},
                          planet_instances={"planetA": 21},
                          player=None)
    sess.teardown(FakeRenderer())
    assert sorted(destroyed) == [11, 12, 21]
    assert sess.ship_instances == {}
    assert sess.planet_instances == {}


def test_host_controller_swap_is_deferred():
    """swap_mission() must NOT load synchronously — it sets pending_swap."""
    from engine.host_loop import HostController

    h = HostController()
    h.swap_mission("Some.Mission.Name")
    assert h.pending_swap == "Some.Mission.Name"


def test_host_controller_drain_clears_pending():
    """_drain_pending_swap loads then clears the latch."""
    from engine.host_loop import HostController, MissionSession

    loaded: list[str] = []

    class StubLoader:
        def load(self, name):
            loaded.append(name)
            return MissionSession(mission_name=name,
                                  ship_instances={}, planet_instances={},
                                  player=None)

    class FakeRenderer:
        def destroy_instance(self, iid): pass

    h = HostController()
    h.renderer = FakeRenderer()
    h.loader = StubLoader()
    h.session = MissionSession(mission_name="prev",
                               ship_instances={}, planet_instances={},
                               player=None)
    h.swap_mission("Next.Mission")
    h._drain_pending_swap()
    assert loaded == ["Next.Mission"]
    assert h.pending_swap is None
    assert h.session.mission_name == "Next.Mission"
```

- [ ] **Step 11.2: Run, verify failure**

Run: `uv run pytest tests/host/test_mission_session.py -v`
Expected: ImportError on `MissionSession` / `HostController`.

- [ ] **Step 11.3: Implement `MissionSession`**

Add to `engine/host_loop.py` (above `run()`):

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MissionSession:
    """Per-mission scene state owned by HostController.

    Instances of the renderer are tracked here so a swap can destroy them
    without re-deriving them from the SDK's set manager (which is itself
    about to be cleared).
    """
    mission_name: str
    ship_instances:   dict[Any, int] = field(default_factory=dict)
    planet_instances: dict[Any, int] = field(default_factory=dict)
    player: Optional[Any] = None

    def teardown(self, renderer) -> None:
        for iid in list(self.ship_instances.values()):
            renderer.destroy_instance(iid)
        for iid in list(self.planet_instances.values()):
            renderer.destroy_instance(iid)
        self.ship_instances.clear()
        self.planet_instances.clear()
        self.player = None
```

- [ ] **Step 11.4: Implement `HostController`**

Add to `engine/host_loop.py` (above `run()`, after `MissionSession`):

```python
class _LoaderProtocol:
    def load(self, mission_name: str) -> MissionSession: ...


class HostController:
    """Per-process state for the running renderer + a single mission.

    The nif_to_handle cache is intentionally a controller-level field so
    the same NIF doesn't re-upload when the next mission re-uses it.
    """
    def __init__(self) -> None:
        self.renderer: Any = None          # set by run() to the engine.renderer module
        self.loader: Optional[_LoaderProtocol] = None
        self.nif_to_handle: dict[str, int] = {}
        self.session: Optional[MissionSession] = None
        self.pending_swap: Optional[str] = None

    def swap_mission(self, mission_name: str) -> None:
        self.pending_swap = mission_name

    def _drain_pending_swap(self) -> None:
        if self.pending_swap is None:
            return
        name = self.pending_swap
        self.pending_swap = None
        if self.session is not None:
            self.session.teardown(self.renderer)
        reset_sdk_globals()
        assert self.loader is not None, "HostController.loader must be set"
        try:
            self.session = self.loader.load(name)
        except Exception as e:
            # Log and leave the controller in a no-mission state; the user
            # can pick another. Avoid bringing the loop down for a swap fail.
            import traceback
            print(f"[host] mission swap to {name!r} failed: "
                  f"{type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
            self.session = None
```

- [ ] **Step 11.5: Run tests**

Run: `uv run pytest tests/host/test_mission_session.py -v`
Expected: all four tests pass.

- [ ] **Step 11.6: Commit**

```bash
git add engine/host_loop.py tests/host/test_mission_session.py
git commit -m "feat(host): MissionSession + HostController.swap_mission"
```

---

## Task 12: Wire MissionSession + Picker into `run()`

**Files:**

- Modify: `engine/host_loop.py:596-830` (the `run()` body)

This is the integration step. The existing `run()` builds the scene, then loops. We turn the body that builds the scene into a `_MissionLoader.load(name)` method that returns a `MissionSession`; `run()` constructs a `HostController`, sets it up, calls `loader.load(initial_mission)` once, and drains pending swaps each tick. The picker is built from a `MissionRegistry.discover()` call after the renderer is up.

The diff is large enough that this task does the integration in three sub-steps, each committed independently.

- [ ] **Step 12.1: Add `_MissionLoader` adapter**

Add to `engine/host_loop.py`, between `_iter_planets` and `def run`:

```python
class _MissionLoader:
    """Bundles _init_mission + render-instance construction so HostController
    can call a single .load(name) method.

    Kept inside this module so it can use the existing _iter_ships /
    _iter_planets / _ship_nif_path / _planet_nif_path helpers without
    re-exporting them.
    """
    def __init__(self, controller: "HostController", verbose: bool):
        self._c = controller
        self._verbose = verbose

    def load(self, mission_name: str) -> MissionSession:
        import App
        from engine.core.loop import GameLoop  # noqa: F401  (used elsewhere)
        _init_mission(mission_name)
        sess = MissionSession(mission_name=mission_name)
        r_ = self._c.renderer

        tex_search = str(PROJECT_ROOT / "game" / DEFAULT_TEXTURE_SEARCH)
        for ship in _iter_ships(verbose=self._verbose):
            nif_path = _ship_nif_path(ship, verbose=self._verbose)
            if nif_path is None:
                continue
            handle = self._c.nif_to_handle.get(nif_path)
            if handle is None:
                try:
                    handle = r_.load_model(nif_path, tex_search)
                except Exception:
                    continue
                self._c.nif_to_handle[nif_path] = handle
            iid = r_.create_instance(handle)
            r_.set_world_transform(iid, _ship_world_matrix(ship))
            sess.ship_instances[ship] = iid

        planet_tex_search = str(PROJECT_ROOT / "game" / DEFAULT_PLANET_TEXTURE_SEARCH)
        for planet in _iter_planets(verbose=self._verbose):
            nif_path = _planet_nif_path(planet, verbose=self._verbose)
            if nif_path is None:
                continue
            handle = self._c.nif_to_handle.get(nif_path)
            if handle is None:
                try:
                    handle = r_.load_model(nif_path, planet_tex_search)
                except Exception:
                    continue
                self._c.nif_to_handle[nif_path] = handle
            iid = r_.create_instance(handle)
            r_.set_world_transform(iid, _astro_world_matrix(planet))
            sess.planet_instances[planet] = iid

        player_set = App.g_kSetManager.GetSet(DEFAULT_PLAYER_SET)
        player = player_set.GetObject("player") if player_set is not None else None
        if player is None and sess.ship_instances:
            player = next(iter(sess.ship_instances.keys()))
        sess.player = player
        return sess
```

Run: `uv run pytest tests/host/test_host_loop_unit.py -v`
Expected: still green — `_MissionLoader` is unused so far.

Commit:
```bash
git add engine/host_loop.py
git commit -m "refactor(host): extract _MissionLoader.load"
```

- [ ] **Step 12.2: Replace `run()`'s inline scene-build with the loader**

Edit `engine/host_loop.py:run()` — replace the block from `# Per-NIF cache so the same mesh isn't reloaded once per ship.` through the `# Per-tick player input → ship-transform integrator.` line with the controller-based version:

```python
        controller = HostController()
        controller.renderer = r
        controller.loader = _MissionLoader(controller, verbose=verbose)
        controller.session = controller.loader.load(mission_name)

        if verbose:
            ss = controller.session
            print(f"[host_loop] mission={mission_name}", flush=True)
            total = len(ss.ship_instances) + len(ss.planet_instances)
            print(f"[host_loop] {total} render instance(s) created "
                  f"({len(ss.ship_instances)} ships, "
                  f"{len(ss.planet_instances)} planets)", flush=True)

        # The initial _init_mission(mission_name) at run() top already
        # populated the SDK globals; controller.loader.load just rebuilt
        # render instances against them. From this point on, any swap
        # goes through controller.swap_mission(name).

        # Per-tick player input → ship-transform integrator.
        player_control = _PlayerControl()
```

Important: leave the `_init_mission(mission_name)` call at the top of `run()` in place — `_MissionLoader.load` also calls it, so for the first load the SDK is double-initialised. Fix this by removing the original early `_init_mission(mission_name)` call near the start of `run()`. Re-read `run()` to confirm only one call to `_init_mission` remains, inside `_MissionLoader.load`.

In the per-tick loop, change references from `ship_instances`, `planet_instances`, `player` to `controller.session.ship_instances`, `controller.session.planet_instances`, `controller.session.player` (find the four to six call sites in `run()`).

At the top of the per-tick loop body, before any other work, add:

```python
            controller._drain_pending_swap()
            if controller.session is None:
                # Mission swap failed; skip per-tick scene work this frame.
                # User can still interact with the UI to pick another mission.
                r.frame()
                continue
```

(The exact placement of `r.frame()` may differ — adapt to whatever the existing frame call is in `run()`. The goal is: when there's no session, still pump the renderer + UI so the picker stays interactive.)

Run: `uv run pytest tests/host/test_host_loop_unit.py -v`
Expected: all `test_run_M1_Basic_*` integration tests still pass (they require BC assets — skips are acceptable in their own right but a failure is not).

Commit:
```bash
git add engine/host_loop.py
git commit -m "refactor(host): run() now uses HostController + session"
```

- [ ] **Step 12.3: Wire the picker + ESC key**

Edit `engine/host_loop.py` — after the debug panel is built, before the controller-based scene load, add:

```python
        from engine.missions import discover as discover_missions
        from engine.mission_picker import MissionPicker

        registry = discover_missions(PROJECT_ROOT / "sdk" / "Build" / "scripts")
        picker = MissionPicker(
            registry=registry,
            on_load=controller.swap_mission,
            on_cancel=lambda: None,
        )
        debug_panel.button("Load Mission", on_click=picker.open)
```

Note: this references `controller` — make sure this block appears **after** `controller = HostController()` but before the controller's loader is set (the picker only needs the swap method; the loader can be wired later). If the construction order makes that awkward, move the picker-build below the controller-wired block and ensure `picker.open` doesn't fire before then (it can't — it's user-triggered).

In the per-tick loop, alongside the existing F8/F9 checks (around line 768-771):

```python
            if _h is not None and _h.key_pressed(_h.keys.KEY_ESCAPE):
                picker.handle_key_esc()
```

Run: `uv run pytest -v` (everything).
Expected: every Python test passes.

Commit:
```bash
git add engine/host_loop.py
git commit -m "feat(host): wire MissionPicker into run()"
```

---

## Task 13: Manual smoke test

**Files:** none — manual verification only.

- [ ] **Step 13.1: Build native**

Run: `cmake --build build -j`

- [ ] **Step 13.2: Launch the host**

Run: `./build/open_stbc`

Expected behaviours:

1. Window opens; M1Basic loads as before.
2. Top-right Debug panel shows the existing stat rows plus a new "Load Mission" button at the bottom.
3. Clicking "Load Mission" opens a centered modal titled "Load Mission". Bottom-right of the panel is a "Cancel" button.
4. The modal lists collapsibles labelled (or dir-name-fallback for) "Tutorial", "Maelstrom", "Multiplayer". Maelstrom expands to its episode collapsibles. Tutorial / Multiplayer skip the redundant single-episode level and show mission buttons directly.
5. Clicking a mission button:
   - The modal closes.
   - Within one tick, the running scene reloads to the picked mission.
   - The camera reattaches to the new player ship.
6. Cancel closes the modal without changing anything.
7. ESC also closes the modal (same effect as Cancel).
8. F9 still toggles the entire UI (modal + debug panel both vanish).
9. Picking a mission that fails to load logs the failure and leaves the scene empty — the user can re-open the picker and try another.

- [ ] **Step 13.3: Final commit (if any local-only changes from troubleshooting)**

If steps 12.x left any forgotten loose-ends, commit them now. Otherwise this step is a no-op.

---

## Self-Review

**Spec coverage:** every numbered section of the spec maps to at least one task:

- §4 Architecture → tasks 1–12 distributed.
- §5 Discovery → task 2.
- §6 TGL reader → task 1.
- §7 Name resolution → tasks 3, 4.
- §8.1 Center anchor → tasks 5, 6.
- §8.2 Footer button → task 7.
- §8.3 Debug-panel hook → task 12.3.
- §9 MissionPicker → task 9.
- §10 MissionSession + HostController + ESC → tasks 8, 10, 11, 12.
- §11 Out of scope → none of these tasks add deferred features.
- §12 Testing strategy → every test file listed in §12 has a corresponding `Create:` in a task.

**Placeholder scan:** no "TBD" / "fill in" / "handle edge cases" left. Step 1.5 contains an explicit *reverse-engineering* sub-procedure (not a placeholder — actual fallback alternates listed).

**Type consistency:** `MissionEntry`/`EpisodeEntry`/`FamilyEntry`/`MissionRegistry` fields are consistent across tasks 2, 3, 4, 9. `MissionSession`'s field names (`ship_instances`, `planet_instances`, `player`, `mission_name`) match between definition (task 11) and consumer (task 12). `HostController` methods (`swap_mission`, `_drain_pending_swap`) consistent task 11 → task 12. `MissionPicker` `open`/`close`/`is_open`/`handle_key_esc` consistent task 9 → task 12.3.
