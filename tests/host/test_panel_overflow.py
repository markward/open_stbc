"""The .bc-panel-body rule in components.rcss declares overflow-y: auto
and a tunable max-height so long target lists scroll.  Scrollbar styling
is intentionally left at RmlUi defaults — a prior attempt at custom
slidertrack/sliderbar rules rendered as a giant blue block (RmlUi
appears to render scrollbar chrome unconstrained when only the bar/track
are styled without their parent scrollbarvertical container).

This test asserts the file's textual content; it doesn't execute RmlUi.
A runtime check would require parsing the compiled DOM, which our test
harness doesn't expose."""
from pathlib import Path


_RCSS = Path(__file__).resolve().parents[2] / "native" / "assets" / "ui" / "components.rcss"


def _rcss_text():
    return _RCSS.read_text(encoding="utf-8")


def test_bc_panel_body_has_overflow_y_auto():
    text = _rcss_text()
    # The .bc-panel-body block must include overflow-y: auto somewhere.
    # Use a substring check rather than parsing CSS — RmlUi's RCSS dialect
    # isn't a perfect CSS subset.
    body_block_start = text.index(".bc-panel-body")
    body_block_end   = text.index("}", body_block_start)
    body_block = text[body_block_start:body_block_end]
    assert "overflow-y" in body_block
    assert "auto" in body_block


def test_bc_panel_body_has_max_height():
    text = _rcss_text()
    body_block_start = text.index(".bc-panel-body")
    body_block_end   = text.index("}", body_block_start)
    body_block = text[body_block_start:body_block_end]
    assert "max-height" in body_block


def test_components_rcss_does_not_style_sliderbar_directly():
    """Regression: a bare `sliderbar { background-color: ... }` rule made
    the scrollbar chrome render as a giant blue block over the panel
    body.  The correct RmlUi pattern wraps slidertrack/sliderbar inside
    a scrollbarvertical container — until we adopt that, no custom
    scrollbar styling at all."""
    text = _rcss_text()
    # Allow the word "sliderbar" inside comments; check for an actual rule.
    # An RCSS rule begins with the selector at column 0 followed by '{'.
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("sliderbar") and "{" in stripped:
            raise AssertionError(
                "components.rcss contains a bare `sliderbar` rule — "
                "this rendered as a giant blue block in the panel body."
            )
