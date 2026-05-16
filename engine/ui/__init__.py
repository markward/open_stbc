"""Reusable UI components for the open_stbc renderer.

See docs/project/superpowers/specs/2026-05-11-ui-components-design.md for the design.
"""
from . import bindings, theme
from .bindings import init as _bindings_init
from .button import UiButton
from .collapsible import UiCollapsibleList
from .panel import UiPanel
from .stat_row import UiStatRow

# Global UI scale multiplier. The native side scales `dp` by
# `UI_SCALE * fb_height / 1080` so a value of 1.0 looks identical at 1080p,
# 1440p, and UHD instead of locking text to a fixed pixel size. Bump above
# 1.0 to enlarge everything globally; drop below for denser layouts.
UI_SCALE: float = 1.0


def init() -> None:
    """Bind to the real renderer host and apply UI_SCALE.

    Must be called once after engine.renderer.init().
    """
    _bindings_init()
    bindings.dom().set_ui_scale(UI_SCALE)


__all__ = ["init", "bindings", "theme", "UI_SCALE",
           "UiButton", "UiCollapsibleList", "UiPanel", "UiStatRow"]
