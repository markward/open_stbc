"""Virtual scrolling on TargetListController.

`_scroll_offset` is the number of ships to skip from the top of the
visible list.  `scroll(delta)` bumps the offset by delta (positive =
scroll down through the list, showing later ships) and rebuilds.
Clamped to [0, max(0, len(non-player ships) - 1)] so at least one ship
is always visible (or zero if there are none).
"""
import pytest

from engine.appc import ship_lifecycle
from engine.ui import UiPanel, bindings as bindings_module
from engine.ui._dom import FakeDom
from engine.ui.target_list import TargetListController


@pytest.fixture
def fake_dom(monkeypatch) -> FakeDom:
    dom = FakeDom()
    monkeypatch.setattr(bindings_module, "_active_dom", dom)
    return dom


@pytest.fixture(autouse=True)
def _reset_hub():
    ship_lifecycle._subscribers.clear()
    ship_lifecycle._live.clear()
    yield
    ship_lifecycle._subscribers.clear()
    ship_lifecycle._live.clear()


class _Ship:
    def __init__(self, name): self._name = name
    def GetName(self): return self._name
    # Minimal subsystem getters so _add_row + populated_subsystems don't crash.
    def GetHull(self): return None
    def GetShieldSubsystem(self): return None
    def GetSensorSubsystem(self): return None
    def GetPowerSubsystem(self): return None
    def GetRepairSubsystem(self): return None
    def GetImpulseEngineSubsystem(self): return None
    def GetWarpEngineSubsystem(self): return None
    def GetPhaserSystem(self): return None
    def GetPulseWeaponSystem(self): return None
    def GetTorpedoSystem(self): return None
    def GetTractorBeamSystem(self): return None


def _ship_titles(fake_dom, panel) -> list[str]:
    """Return the visible ship-row titles in order."""
    root = fake_dom.panel_root(panel.panel_id)
    body_id = fake_dom.children(root)[-1]
    wrappers = fake_dom.children(body_id)
    titles = []
    for w in wrappers:
        header = fake_dom.children(w)[0]
        title_id = fake_dom.children(header)[1]
        titles.append(fake_dom.element(title_id).text)
    return titles


def test_initial_offset_is_zero(fake_dom):
    panel = UiPanel(id="t", title="T")
    ctrl = TargetListController(panel, player_provider=lambda: None)
    assert ctrl._scroll_offset == 0


def test_scroll_down_advances_offset(fake_dom):
    for n in ("A", "B", "C", "D"):
        ship_lifecycle.publish_added(_Ship(n))
    panel = UiPanel(id="t", title="T")
    ctrl = TargetListController(panel, player_provider=lambda: None)
    assert _ship_titles(fake_dom, panel) == ["A", "B", "C", "D"]

    ctrl.scroll(1)
    assert _ship_titles(fake_dom, panel) == ["B", "C", "D"]
    assert ctrl._scroll_offset == 1

    ctrl.scroll(1)
    assert _ship_titles(fake_dom, panel) == ["C", "D"]


def test_scroll_up_clamps_at_zero(fake_dom):
    for n in ("A", "B"):
        ship_lifecycle.publish_added(_Ship(n))
    panel = UiPanel(id="t", title="T")
    ctrl = TargetListController(panel, player_provider=lambda: None)

    ctrl.scroll(-5)
    assert ctrl._scroll_offset == 0
    assert _ship_titles(fake_dom, panel) == ["A", "B"]


def test_scroll_down_clamps_so_one_ship_always_visible(fake_dom):
    for n in ("A", "B", "C"):
        ship_lifecycle.publish_added(_Ship(n))
    panel = UiPanel(id="t", title="T")
    ctrl = TargetListController(panel, player_provider=lambda: None)

    ctrl.scroll(99)
    assert ctrl._scroll_offset == 2  # len-1
    assert _ship_titles(fake_dom, panel) == ["C"]


def test_scroll_with_no_ships_is_noop(fake_dom):
    panel = UiPanel(id="t", title="T")
    ctrl = TargetListController(panel, player_provider=lambda: None)
    ctrl.scroll(3)  # must not raise
    assert ctrl._scroll_offset == 0


def test_player_skipped_then_offset_applies_to_non_player_ships(fake_dom):
    player = _Ship("Player")
    others = [_Ship(n) for n in ("A", "B", "C")]
    ship_lifecycle.publish_added(player)
    for s in others:
        ship_lifecycle.publish_added(s)
    panel = UiPanel(id="t", title="T")
    ctrl = TargetListController(panel, player_provider=lambda: player)
    assert _ship_titles(fake_dom, panel) == ["A", "B", "C"]

    ctrl.scroll(1)
    assert _ship_titles(fake_dom, panel) == ["B", "C"]


def test_ship_added_event_preserves_scroll_offset(fake_dom):
    """A new ship arriving must not reset scroll_offset; the controller
    just re-renders with the same offset applied to the new snapshot."""
    for n in ("A", "B", "C"):
        ship_lifecycle.publish_added(_Ship(n))
    panel = UiPanel(id="t", title="T")
    ctrl = TargetListController(panel, player_provider=lambda: None)
    ctrl.scroll(1)  # offset = 1, visible: B, C

    ship_lifecycle.publish_added(_Ship("D"))  # triggers rebuild
    assert ctrl._scroll_offset == 1
    assert _ship_titles(fake_dom, panel) == ["B", "C", "D"]


def test_ship_removed_event_clamps_offset_if_needed(fake_dom):
    """If destroying ships drops the snapshot below the offset, clamp
    so the user still sees something."""
    ships = [_Ship(n) for n in ("A", "B", "C", "D")]
    for s in ships:
        ship_lifecycle.publish_added(s)
    panel = UiPanel(id="t", title="T")
    ctrl = TargetListController(panel, player_provider=lambda: None)
    ctrl.scroll(2)  # offset = 2, visible: C, D
    assert _ship_titles(fake_dom, panel) == ["C", "D"]

    # Drop C and D from the hub, then trigger a rebuild.
    ship_lifecycle._live.clear()
    ship_lifecycle._live.update({ships[0], ships[1]})
    ctrl.rebuild_from_snapshot()

    # Offset was 2, but only 2 ships remain (A, B).  Clamp to 1 so B is shown.
    assert ctrl._scroll_offset == 1
    assert _ship_titles(fake_dom, panel) == ["B"]
