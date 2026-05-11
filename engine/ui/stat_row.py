"""Read-only label/value row used by debug/status panels.

Layout: a `.bc-stat-row` div wrapping `.bc-stat-label` (left) and
`.bc-stat-value` (right). No click handler, no selection state — value
mutates via `set_value()`.
"""
from __future__ import annotations

from . import bindings


class UiStatRow:
    def __init__(self, *, parent_element: int, label: str, value: str = ""):
        self._label = label
        self._value = value
        self._destroyed = False

        self.element_id = bindings.append_div(parent_element, "bc-stat-row")
        self._label_element_id = bindings.append_div(self.element_id, "bc-stat-label")
        self._value_element_id = bindings.append_div(self.element_id, "bc-stat-value")
        bindings.set_text(self._label_element_id, label)
        bindings.set_text(self._value_element_id, value)

    @property
    def label(self) -> str: return self._label
    @property
    def value(self) -> str: return self._value

    def set_value(self, value: str) -> None:
        if self._value == value:
            return
        self._value = value
        bindings.set_text(self._value_element_id, value)

    def set_label(self, label: str) -> None:
        self._label = label
        bindings.set_text(self._label_element_id, label)

    def destroy(self) -> None:
        if self._destroyed:
            return
        bindings.remove_element(self.element_id)
        self._destroyed = True
