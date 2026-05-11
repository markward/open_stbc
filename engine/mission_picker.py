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
from engine.ui import bindings as _ui_bindings

_SKIP_EPISODE_LEVEL = {"Episode", "."}


_DESTROY_DELAY_TICKS = 3  # ticks between hide and actual destruction


class MissionPicker:
    def __init__(self, *,
                 registry: MissionRegistry,
                 on_load: Callable[[str], None],
                 on_cancel: Callable[[], None]):
        self._registry = registry
        self._on_load = on_load
        self._on_cancel = on_cancel
        self._panel: Optional[UiPanel] = None
        self._open: bool = False
        # Click handlers fire from inside RmlUi's event dispatch — tearing
        # the panel down synchronously crashes the renderer. Instead, the
        # callback stashes a deferred action here and drain() does the
        # actual close + on_load/on_cancel at a tick boundary.
        self._pending: Optional[tuple[str, Optional[str]]] = None
        # Two-phase close: drain() hides the panel immediately; after
        # _DESTROY_DELAY_TICKS subsequent drains the panel is destroyed.
        # This avoids RmlUi crashing when a document is torn down too
        # close to its own click event, AND ensures the panel doesn't
        # keep eating clicks (hidden documents still appear in the
        # context's hit-test tree).
        self._destroy_countdown: int = 0

    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        # Cancel any pending destruction so we keep the existing panel.
        self._destroy_countdown = 0
        if self._panel is not None:
            _ui_bindings.set_panel_visible(self._panel.panel_id, True)
            self._open = True
            return
        panel = UiPanel(id="mission-picker", anchor="center",
                        width_vw=42.0, height_vh=72.0,
                        title="Load Mission")
        for family in self._registry.families:
            family_row = panel.collapsible(family.display_name,
                                           menu_level=1, expanded=False)
            for episode in family.episodes:
                skip_episode = (
                    len(family.episodes) == 1
                    and episode.dir_name in _SKIP_EPISODE_LEVEL
                )
                if skip_episode:
                    parent = family_row
                else:
                    parent = family_row.collapsible(
                        episode.display_name,
                        menu_level=2, expanded=False)
                for mission in episode.missions:
                    parent.button(
                        mission.display_name,
                        on_click=self._make_pick_callback(mission),
                    )
        panel.set_footer_button("Cancel", on_click=self._queue_cancel)
        self._panel = panel
        self._open = True

    def close(self) -> None:
        # Phase 1: hide the panel immediately, then start a countdown
        # to phase 2 (actual destruction). The hide drops the panel
        # off-screen so it can't intercept clicks even though RmlUi
        # still has it in the hit-test tree.
        if self._panel is None or not self._open:
            return
        _ui_bindings.set_panel_visible(self._panel.panel_id, False)
        self._open = False
        self._destroy_countdown = _DESTROY_DELAY_TICKS

    def destroy(self) -> None:
        """Tear down the picker entirely. Only called at host shutdown."""
        if self._panel is not None:
            self._panel.destroy()
            self._panel = None
        self._open = False

    def handle_key_esc(self) -> None:
        # ESC is polled from the host loop, not from an RmlUi callback,
        # so it's safe to close synchronously here.
        if self.is_open():
            self.close()
            self._on_cancel()

    def drain(self) -> None:
        """Process any deferred pick/cancel queued by a UI click, and
        run the destroy-countdown if a close is pending.

        Call once per host tick. Closing + invoking callbacks happens
        here, outside the RmlUi event dispatch, so the renderer can
        safely tear the document down.
        """
        if self._pending is not None:
            action, arg = self._pending
            self._pending = None
            self.close()
            if action == "load" and arg is not None:
                self._on_load(arg)
            elif action == "cancel":
                self._on_cancel()

        # Destroy countdown: after enough ticks have elapsed since the
        # click, it's safe to actually tear the panel down. Open() resets
        # the countdown so a re-open within the window cancels destruction.
        if self._destroy_countdown > 0 and self._panel is not None:
            self._destroy_countdown -= 1
            if self._destroy_countdown == 0:
                self._panel.destroy()
                self._panel = None

    def _make_pick_callback(self, mission: MissionEntry):
        def _pick():
            self._pending = ("load", mission.module_name)
        return _pick

    def _queue_cancel(self) -> None:
        self._pending = ("cancel", None)
