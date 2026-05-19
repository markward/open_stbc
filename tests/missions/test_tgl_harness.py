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
