# TGL Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a smoke-test harness that walks every `.tgl` file under `game/data/TGL/` and `sdk/Build/Data/TGL/`, parses each via `engine.missions.tgl_reader.read_tgl`, and prints a per-file result + ranked summary of failure modes, in the style of `tools/mission_harness.py`.

**Architecture:** A single Python script `tools/tgl_harness.py` with five module-level functions (`discover_tgl_files`, `classify`, `error_key`, `format_line`, `main`) and module-level constants. No SDK module-loading machinery — the parser is pure bytes-in / dataclass-out. Tests live at `tests/missions/test_tgl_harness.py` and import the functions directly.

**Tech Stack:** Python 3.13, `pathlib`, `collections.Counter`, `pytest`. Reuses `engine.missions.tgl_reader.read_tgl` and `TGLParseError`.

**Spec:** [docs/superpowers/specs/2026-05-18-tgl-harness-design.md](../specs/2026-05-18-tgl-harness-design.md)

---

## File Structure

- Create: `tools/tgl_harness.py` — discovery, classification, summary, `main()`.
- Create: `tests/missions/test_tgl_harness.py` — unit tests for the four pure functions.
- Reuse: `engine/missions/tgl_reader.py` (`read_tgl`, `TGLParseError`) — unchanged.
- Reuse: `tests/missions/conftest.py` — `tutorial_episode_tgl` and `maelstrom_tgl` fixtures already exist; we'll add new fixtures inline in the test file rather than expand conftest.

---

## Task 1: Module scaffold + discovery

**Files:**
- Create: `tools/tgl_harness.py`
- Create: `tests/missions/test_tgl_harness.py`

- [ ] **Step 1: Write the failing discovery test**

Create `tests/missions/test_tgl_harness.py`:

```python
"""Tests for the TGL parser smoke-test harness."""
from pathlib import Path

import pytest

from tools.tgl_harness import discover_tgl_files


def test_discover_walks_temp_dir_case_insensitively(tmp_path, monkeypatch):
    """discover_tgl_files picks up .tgl and .TGL, ignores other suffixes."""
    root = tmp_path / "fake_tgl_root"
    root.mkdir()
    (root / "alpha.tgl").write_bytes(b"")
    (root / "BETA.TGL").write_bytes(b"")
    (root / "nested").mkdir()
    (root / "nested" / "gamma.Tgl").write_bytes(b"")
    (root / "ignore.txt").write_bytes(b"")
    (root / "ignore.tglx").write_bytes(b"")

    import tools.tgl_harness as harness
    monkeypatch.setattr(harness, "ROOTS", [root])

    found = discover_tgl_files()

    assert [p.name for p in found] == sorted(["alpha.tgl", "BETA.TGL", "gamma.Tgl"])


def test_discover_skips_missing_root(tmp_path, monkeypatch):
    """A non-existent root is silently skipped (game/ may not be installed)."""
    missing = tmp_path / "does_not_exist"
    present = tmp_path / "present"
    present.mkdir()
    (present / "x.tgl").write_bytes(b"")

    import tools.tgl_harness as harness
    monkeypatch.setattr(harness, "ROOTS", [missing, present])

    found = discover_tgl_files()
    assert [p.name for p in found] == ["x.tgl"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/missions/test_tgl_harness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.tgl_harness'` (or `ImportError`).

- [ ] **Step 3: Create the harness scaffold + discovery**

Create `tools/tgl_harness.py`:

```python
"""
TGL parser smoke-test harness for open_stbc.

Discovers every .tgl file under game/data/TGL/ and sdk/Build/Data/TGL/,
parses each via engine.missions.tgl_reader.read_tgl, and reports a
ranked summary of failures (parse errors and empty files).

Usage:
    uv run python tools/tgl_harness.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# Ensure project root is on sys.path whether run as script or imported in tests.
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ROOTS: list[Path] = [
    PROJECT_ROOT / "game" / "data" / "TGL",
    PROJECT_ROOT / "sdk" / "Build" / "Data" / "TGL",
]


def discover_tgl_files() -> list[Path]:
    """Return all .tgl files (case-insensitive) under ROOTS, sorted.

    Missing roots are skipped silently — game/ is a developer-supplied
    install and may not be present in every checkout.
    """
    found: list[Path] = []
    for root in ROOTS:
        if not root.is_dir():
            continue
        found.extend(
            sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".tgl")
        )
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/missions/test_tgl_harness.py -v`
Expected: both `test_discover_*` tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/tgl_harness.py tests/missions/test_tgl_harness.py
git commit -m "feat(tools): tgl_harness scaffold + discovery"
```

---

## Task 2: Per-file classification

**Files:**
- Modify: `tools/tgl_harness.py` (add `classify`)
- Modify: `tests/missions/test_tgl_harness.py` (add classification tests)

- [ ] **Step 1: Write the failing classification tests**

Append to `tests/missions/test_tgl_harness.py`:

```python
from engine.missions.tgl_reader import TGLParseError
from tools.tgl_harness import classify

PROJECT_ROOT = Path(__file__).parent.parent.parent
SDK_TGL_ROOT = PROJECT_ROOT / "sdk" / "Build" / "Data" / "TGL"


def test_classify_pass_returns_counts():
    """A real, non-empty TGL classifies as pass with (strings, sounds) counts."""
    sample = SDK_TGL_ROOT / "Tutorial" / "Tutorial.tgl"
    if not sample.is_file():
        pytest.skip(f"{sample} not present")

    status, reason = classify(sample)

    assert status == "pass"
    kind, payload = reason
    assert kind == "counts"
    strings_count, sounds_count = payload
    assert strings_count > 0 or sounds_count > 0


def test_classify_empty_placeholder():
    """The tutorial Episode.tgl is the known empty case."""
    sample = SDK_TGL_ROOT / "Tutorial" / "Episode" / "Episode.tgl"
    if not sample.is_file():
        pytest.skip(f"{sample} not present")

    status, reason = classify(sample)

    assert status == "fail"
    kind, payload = reason
    assert kind == "empty"
    assert payload is None


def test_classify_parse_error_on_truncated_file(tmp_path):
    """A four-byte file trips TGLParseError and surfaces as a parse failure."""
    bad = tmp_path / "bad.tgl"
    bad.write_bytes(b"\x01\x17\x00\x00")

    status, reason = classify(bad)

    assert status == "fail"
    kind, payload = reason
    assert kind == "parse"
    assert isinstance(payload, TGLParseError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/missions/test_tgl_harness.py -v`
Expected: three new `test_classify_*` tests FAIL with `ImportError: cannot import name 'classify'`.

- [ ] **Step 3: Add `classify` to the harness**

Append to `tools/tgl_harness.py`:

```python
from engine.missions.tgl_reader import read_tgl


def classify(path: Path) -> tuple[str, tuple]:
    """Parse path and classify the result.

    Returns:
        ("pass", ("counts", (strings_n, sounds_n))) on successful, non-empty parse.
        ("fail", ("empty", None)) on successful parse with zero strings AND zero sounds.
        ("fail", ("parse", exc))  on any exception from read_tgl.
    """
    try:
        tgl = read_tgl(path)
    except Exception as exc:
        return ("fail", ("parse", exc))
    if len(tgl.strings) == 0 and len(tgl.sounds) == 0:
        return ("fail", ("empty", None))
    return ("pass", ("counts", (len(tgl.strings), len(tgl.sounds))))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/missions/test_tgl_harness.py -v`
Expected: all five tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/tgl_harness.py tests/missions/test_tgl_harness.py
git commit -m "feat(tools): tgl_harness per-file classification (pass/empty/parse)"
```

---

## Task 3: Error-key generation for the summary Counter

**Files:**
- Modify: `tools/tgl_harness.py` (add `error_key`)
- Modify: `tests/missions/test_tgl_harness.py` (add error_key tests)

- [ ] **Step 1: Write the failing error_key tests**

Append to `tests/missions/test_tgl_harness.py`:

```python
from tools.tgl_harness import error_key


def test_error_key_for_parse_exception():
    """Parse failures key on '<ExcType>: <first-line-of-message[:80]>'."""
    exc = TGLParseError("keys section truncated")
    key = error_key("fail", ("parse", exc))
    assert key == "TGLParseError: keys section truncated"


def test_error_key_truncates_long_messages():
    """Messages longer than 80 chars are truncated."""
    long_msg = "x" * 200
    exc = TGLParseError(long_msg)
    key = error_key("fail", ("parse", exc))
    # "TGLParseError: " (15 chars) + first 80 chars of message
    assert key == "TGLParseError: " + "x" * 80


def test_error_key_takes_first_line_only():
    """Multi-line exception messages get truncated to the first line."""
    exc = TGLParseError("first line\nsecond line\nthird line")
    key = error_key("fail", ("parse", exc))
    assert key == "TGLParseError: first line"


def test_error_key_for_empty_failure():
    """Empty TGLs share a single literal grouping key."""
    key = error_key("fail", ("empty", None))
    assert key == "empty TGL (0 strings, 0 sounds)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/missions/test_tgl_harness.py -v`
Expected: four new `test_error_key_*` tests FAIL with `ImportError: cannot import name 'error_key'`.

- [ ] **Step 3: Add `error_key` to the harness**

Append to `tools/tgl_harness.py`:

```python
def error_key(status: str, reason: tuple) -> str:
    """Build the Counter grouping key for a failure.

    Only called on failures (status == "fail").
    """
    kind, payload = reason
    if kind == "empty":
        return "empty TGL (0 strings, 0 sounds)"
    # kind == "parse"
    exc = payload
    msg = (str(exc).splitlines() or [""])[0]
    return f"{type(exc).__name__}: {msg[:80]}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/missions/test_tgl_harness.py -v`
Expected: all nine tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/tgl_harness.py tests/missions/test_tgl_harness.py
git commit -m "feat(tools): tgl_harness error_key for ranked failure summary"
```

---

## Task 4: Per-file line formatting

**Files:**
- Modify: `tools/tgl_harness.py` (add `format_line`)
- Modify: `tests/missions/test_tgl_harness.py` (add formatting tests)

- [ ] **Step 1: Write the failing format_line tests**

Append to `tests/missions/test_tgl_harness.py`:

```python
from tools.tgl_harness import format_line


def test_format_line_pass_single_line():
    """Pass renders as one line with (strings=N sounds=M) suffix."""
    path = PROJECT_ROOT / "game" / "data" / "TGL" / "Foo.tgl"
    out = format_line(path, "pass", ("counts", (42, 17)))
    assert out == "  PASS  game/data/TGL/Foo.tgl  (strings=42 sounds=17)"


def test_format_line_empty_single_line():
    """Empty failure renders as one line with 'empty: ...' suffix."""
    path = PROJECT_ROOT / "sdk" / "Build" / "Data" / "TGL" / "Tutorial" / "Episode" / "Episode.tgl"
    out = format_line(path, "fail", ("empty", None))
    assert out == (
        "  FAIL  sdk/Build/Data/TGL/Tutorial/Episode/Episode.tgl"
        "  empty: 0 strings, 0 sounds"
    )


def test_format_line_parse_two_lines():
    """Parse failure renders as two lines: path, then indented exception."""
    path = PROJECT_ROOT / "game" / "data" / "TGL" / "Bad.tgl"
    exc = TGLParseError("keys section truncated")
    out = format_line(path, "fail", ("parse", exc))
    assert out == (
        "  FAIL  game/data/TGL/Bad.tgl\n"
        "         TGLParseError: keys section truncated"
    )


def test_format_line_handles_path_outside_project_root(tmp_path):
    """Paths outside PROJECT_ROOT fall back to the absolute path."""
    path = tmp_path / "x.tgl"
    out = format_line(path, "pass", ("counts", (1, 1)))
    assert str(path) in out
    assert out.startswith("  PASS  ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/missions/test_tgl_harness.py -v`
Expected: four new `test_format_line_*` tests FAIL with `ImportError: cannot import name 'format_line'`.

- [ ] **Step 3: Add `format_line` to the harness**

Append to `tools/tgl_harness.py`:

```python
def format_line(path: Path, status: str, reason: tuple) -> str:
    """Render one per-file result line (or two lines for parse errors).

    Paths inside PROJECT_ROOT render relative; paths outside render absolute
    (e.g. tmp_path in tests).
    """
    try:
        rel = path.relative_to(PROJECT_ROOT)
        display = str(rel)
    except ValueError:
        display = str(path)

    marker = "PASS" if status == "pass" else "FAIL"
    kind, payload = reason
    if kind == "counts":
        strings_n, sounds_n = payload
        return f"  {marker}  {display}  (strings={strings_n} sounds={sounds_n})"
    if kind == "empty":
        return f"  {marker}  {display}  empty: 0 strings, 0 sounds"
    # kind == "parse"
    exc = payload
    exc_msg = (str(exc).splitlines() or [""])[0]
    return f"  {marker}  {display}\n         {type(exc).__name__}: {exc_msg}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/missions/test_tgl_harness.py -v`
Expected: all thirteen tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/tgl_harness.py tests/missions/test_tgl_harness.py
git commit -m "feat(tools): tgl_harness per-file line formatting"
```

---

## Task 5: `main()` orchestration + summary

**Files:**
- Modify: `tools/tgl_harness.py` (add `main`, `__main__` guard)

- [ ] **Step 1: Add `main()` to the harness**

Append to `tools/tgl_harness.py`:

```python
def main() -> None:
    files = discover_tgl_files()

    print("open_stbc TGL harness")
    print("=" * 50)
    print(f"Found {len(files)} TGL files\n")
    print("Parsing...\n")

    results: list[tuple[Path, str, tuple]] = []
    for path in files:
        status, reason = classify(path)
        results.append((path, status, reason))
        print(format_line(path, status, reason))

    passed = sum(1 for _, s, _ in results if s == "pass")
    failed = len(results) - passed
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed of {len(results)} total")

    if failed:
        errors: Counter[str] = Counter()
        for _, status, reason in results:
            if status == "fail":
                errors[error_key(status, reason)] += 1
        print(f"\nTop errors ({len(errors)} distinct):")
        for msg, count in errors.most_common(15):
            print(f"  [{count:2d}]  {msg}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-run the harness end-to-end**

Run: `uv run python tools/tgl_harness.py`

Expected:
- Header line `open_stbc TGL harness` followed by `Found N TGL files` (~60 if `game/` is present, 3 if only the SDK).
- Per-file PASS/FAIL lines.
- At minimum one FAIL line for `sdk/Build/Data/TGL/Tutorial/Episode/Episode.tgl` (empty).
- Summary block with `Results: ... passed, ... failed of N total`.
- `Top errors` block listing at least `[ 1]  empty TGL (0 strings, 0 sounds)`.

If unexpected parse failures appear, do NOT fix them in this plan — they indicate parser bugs or undiscovered file format variants and are out of scope. Report them so the user can decide whether to file follow-up work.

- [ ] **Step 3: Run the full harness test file once more**

Run: `uv run pytest tests/missions/test_tgl_harness.py -v`
Expected: all thirteen tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add tools/tgl_harness.py
git commit -m "feat(tools): tgl_harness main() orchestration + ranked summary"
```

---

## Self-Review

**Spec coverage:**
- Discovery (game/ + sdk/, case-insensitive, missing-root tolerance) → Task 1.
- Three-way classification (pass / fail-empty / fail-parse) → Task 2.
- Error-key generation matching the format in the spec → Task 3.
- Per-file line format including the two-line layout for parse failures → Task 4.
- `main()` orchestration, header, summary, Counter-based ranked errors → Task 5.
- Tests: discovery (case-insensitive + missing root), pass/empty/parse classification, error_key for both modes, format_line for all three result shapes → Tasks 1–4 (13 unit tests).
- Spec test (5) "error-key generation for both failure modes" → covered by Tasks 3.
- Spec smoke-criterion "uv run python tools/tgl_harness.py runs to completion" → Task 5 step 2.

**Placeholder scan:** No TBDs, every code step shows complete code, every command shows expected output.

**Type consistency:** `classify` returns `tuple[str, tuple]` where the inner tuple is `(kind, payload)` with `kind ∈ {"counts", "empty", "parse"}`. `error_key` and `format_line` both destructure this same shape consistently across Tasks 3 and 4. `PROJECT_ROOT` and `ROOTS` are module-level in `tools/tgl_harness.py` and referenced via `monkeypatch.setattr(harness, "ROOTS", ...)` in tests — no shadowing.
