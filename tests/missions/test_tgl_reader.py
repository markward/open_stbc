"""TGL binary parser — reads localization strings out of BC's .tgl files."""
import pytest

from engine.missions.tgl_reader import read_tgl, TGLParseError


def test_parse_tutorial_episode_one_entry(tutorial_episode_tgl):
    """Episode.tgl ships with exactly one entry that documents itself —
    the developer note explaining the file's existence is its value."""
    if not tutorial_episode_tgl.is_file():
        pytest.skip(f"{tutorial_episode_tgl} not present")

    tgl = read_tgl(tutorial_episode_tgl)

    assert "Unused" in tgl.strings
    assert tgl.strings["Unused"].startswith("This string is only here")
    assert tgl.sounds.get("Unused") == "Unused.wav"
    assert tgl.source == str(tutorial_episode_tgl)


def test_parse_maelstrom_episode_titles(maelstrom_tgl):
    """Maelstrom.tgl is the real-world test — eight episode titles plus
    star-system names, all with matching .mp3 sound files."""
    if not maelstrom_tgl.is_file():
        pytest.skip(f"{maelstrom_tgl} not present (game install)")

    tgl = read_tgl(maelstrom_tgl)

    for n in range(1, 9):
        key = f"Ep{n}Title"
        assert key in tgl.strings, f"missing {key}; got: {sorted(tgl.strings)[:20]}"
        v = tgl.strings[key]
        assert v.startswith(f"Episode {n}"), (
            f"{key}={v!r} did not start with 'Episode {n}'")
        assert tgl.sounds.get(key) == f"{key}.mp3"


def test_parse_raises_on_truncated_file(tmp_path):
    bad = tmp_path / "bad.tgl"
    bad.write_bytes(b"\x01\x17\x00\x00")  # header truncated
    with pytest.raises(TGLParseError):
        read_tgl(bad)
