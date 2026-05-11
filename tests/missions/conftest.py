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
