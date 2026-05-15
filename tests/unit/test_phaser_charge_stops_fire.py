"""Continuous fire drains charge; bank auto-stops when it dips below
its MinFiringCharge threshold."""
import sys
import importlib
from unittest.mock import patch

import pytest

import App
from engine.appc.ships import ShipClass, ShipClass_Create


@pytest.fixture
def galaxy_red():
    ship = ShipClass_Create("Galaxy")
    App.g_kModelPropertyManager.ClearLocalTemplates()
    mod_name = "ships.Hardpoints.galaxy"
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
    else:
        importlib.import_module(mod_name)
    mod = sys.modules[mod_name]
    mod.LoadPropertySet(ship.GetPropertySet())
    ship.SetupProperties()
    ship.SetAlertLevel(ShipClass.RED_ALERT)
    yield ship
    App.g_kModelPropertyManager.ClearLocalTemplates()
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]


def test_firing_stops_when_charge_drops_below_min(galaxy_red):
    """Galaxy phaser: MaxCharge=5, Min=3, Discharge=1/s.  Starting at
    charge=3.5, sustained fire for 1s drains to 2.5, which is below
    Min — bank should auto-stop."""
    ship = galaxy_red
    bank = ship.GetPhaserSystem().GetWeapon(0)
    bank._charge_level = 3.5
    bank._firing = True

    bank.UpdateCharge(1.0)  # drains 1.0/s × 1.0s = 1.0 → 2.5

    assert bank._charge_level == pytest.approx(2.5)
    assert bank.IsFiring() == 0, "Bank should auto-stop below MinFiringCharge"


def test_firing_continues_above_min(galaxy_red):
    """Same bank firing for 0.4s drops 0.4 → still above Min=3."""
    ship = galaxy_red
    bank = ship.GetPhaserSystem().GetWeapon(0)
    bank._charge_level = 5.0
    bank._firing = True

    bank.UpdateCharge(0.4)  # 5.0 → 4.6

    assert bank._charge_level == pytest.approx(4.6)
    assert bank.IsFiring() == 1, "Bank above MinFiringCharge keeps firing"


def test_idle_recharges_only_when_alert_powers_system(galaxy_red):
    """Recharge requires parent.IsOn() (alert-driven power)."""
    ship = galaxy_red
    bank = ship.GetPhaserSystem().GetWeapon(0)
    bank._charge_level = 1.0
    bank._firing = False
    bank.UpdateCharge(1.0)  # parent on (RED alert) → +0.08/s
    assert bank._charge_level == pytest.approx(1.08)

    ship.SetAlertLevel(ShipClass.GREEN_ALERT)
    bank._charge_level = 1.0
    bank.UpdateCharge(1.0)  # parent off → no recharge
    assert bank._charge_level == pytest.approx(1.0)
