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
