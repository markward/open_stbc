"""PhaserSystem.StartFiring fires ALL eligible banks simultaneously
(not round-robin like torpedo tubes).
"""
from unittest.mock import patch

import App


def _make_target_ahead(player):
    """Build a fake target placed 100 units ahead of the player (+Y)."""
    class _Target:
        def __init__(self, pos):
            self._pos = pos
        def GetWorldLocation(self):  return self._pos
        def IsDead(self):            return 0
    from engine.appc.math import TGPoint3
    p = player.GetWorldLocation()
    return _Target(TGPoint3(p.x, p.y + 100.0, p.z))


def test_target_ahead_fires_all_eligible_banks(galaxy_red):
    """Galaxy at RED + target dead ahead → every PhaserBank in arc fires."""
    ship = galaxy_red
    sys_ = ship.GetPhaserSystem()
    assert sys_ is not None and sys_.GetNumWeapons() > 0
    target = _make_target_ahead(ship)
    # Force every bank fully charged so charge-gate doesn't suppress any.
    for i in range(sys_.GetNumWeapons()):
        bank = sys_.GetWeapon(i)
        bank._charge_level = bank._max_charge

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        sys_.StartFiring(target)

    firing = [sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons())]
    # At least 2 banks should engage a target dead-ahead (Galaxy has
    # forward-facing arcs on multiple dorsal+ventral phasers).
    assert sum(firing) >= 2, f"Expected multiple banks firing, got: {firing}"


def test_target_directly_behind_fires_no_forward_banks(galaxy_red):
    """Target behind the ship → forward-facing banks must NOT fire."""
    ship = galaxy_red
    sys_ = ship.GetPhaserSystem()
    from engine.appc.math import TGPoint3
    class _Behind:
        def GetWorldLocation(self):
            p = ship.GetWorldLocation()
            return TGPoint3(p.x, p.y - 100.0, p.z)
        def IsDead(self): return 0
    for i in range(sys_.GetNumWeapons()):
        bank = sys_.GetWeapon(i)
        bank._charge_level = bank._max_charge

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        sys_.StartFiring(_Behind())

    firing = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    # Galaxy has 8 phasers but the SDK defines their arcs to cover forward
    # hemispheres; a target directly astern should yield 0 firing banks.
    assert firing == 0, f"Expected no forward banks firing on aft target, got {firing}"


def test_uncharged_banks_skipped(galaxy_red):
    """A bank with _charge_level < _min_firing_charge must not fire even
    when alert + arc allow it."""
    ship = galaxy_red
    sys_ = ship.GetPhaserSystem()
    target = _make_target_ahead(ship)
    for i in range(sys_.GetNumWeapons()):
        bank = sys_.GetWeapon(i)
        bank._charge_level = 0.0

    with patch("engine.audio.tg_sound.TGSoundManager.instance"):
        sys_.StartFiring(target)

    firing = sum(sys_.GetWeapon(i).IsFiring() for i in range(sys_.GetNumWeapons()))
    assert firing == 0, f"Drained banks must not fire, got {firing} firing"
