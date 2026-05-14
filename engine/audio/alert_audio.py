"""Alert audio listener: plays Red/Yellow/Green alert SFX on transitions.

The alert state is a plain field on ShipClass (no signal). host_loop calls
.tick(player) each frame; the listener remembers the previous level and fires
the matching one-shot when the level changes.
"""
from __future__ import annotations

from typing import Optional

from engine.audio.tg_sound import TGSoundManager


# Mirror ShipClass alert constants from engine/appc/ships.py:10-12 to avoid
# importing ShipClass (keeps this module testable with fake ships).
GREEN_ALERT = 0
YELLOW_ALERT = 1
RED_ALERT = 2

_SOUND_BY_LEVEL = {
    RED_ALERT:    "RedAlertSound",
    YELLOW_ALERT: "YellowAlertSound",
    GREEN_ALERT:  "GreenAlertSound",
}


class AlertAudioListener:
    def __init__(self) -> None:
        self._last_level: Optional[int] = None

    def tick(self, player) -> None:
        if player is None:
            return
        getter = getattr(player, "GetAlertLevel", None)
        if getter is None:
            return
        level = int(getter())
        if self._last_level is None:
            self._last_level = level
            return
        if level == self._last_level:
            return
        self._last_level = level
        name = _SOUND_BY_LEVEL.get(level)
        if name:
            TGSoundManager.instance().PlaySound(name)

    def reset(self) -> None:
        self._last_level = None
