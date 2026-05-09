"""Find a small standalone skybox NIF in game/data.

Heuristic: any *.nif with 'sky' or 'star' in the path, ranked by file size
ascending. Prints the smallest match.

Usage:
    uv run python tools/pick_default_skybox.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
GAME_DATA = PROJECT_ROOT / "game" / "data"


def main():
    if not GAME_DATA.is_dir():
        print(f"no game/data at {GAME_DATA}", file=sys.stderr)
        return 1
    candidates = []
    for nif in GAME_DATA.rglob("*.nif"):
        name = str(nif).lower()
        if "sky" in name or "star" in name:
            candidates.append((nif.stat().st_size, nif))
    if not candidates:
        print("no skybox candidates found", file=sys.stderr)
        return 1
    candidates.sort()
    print("ranked by size:")
    for size, p in candidates[:10]:
        print(f"  {size:>10d}  {p.relative_to(PROJECT_ROOT)}")
    print(f"winner: {candidates[0][1].relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
