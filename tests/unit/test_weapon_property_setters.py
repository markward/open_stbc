"""The catch-all TGModelProperty.__getattr__ accepts any SetX/GetX but
stores into _data with None defaults.  These tests pin down the typed
accessors that Pass 4 reads — explicit fields with real defaults so
the runtime emitters get correct values.
"""
from engine.appc.properties import (
    EnergyWeaponProperty, PhaserProperty, PulseWeaponProperty,
    TractorBeamProperty, TorpedoTubeProperty,
)


def test_energy_weapon_charge_fields_default_zero():
    p = EnergyWeaponProperty("Test")
    assert p.GetMaxCharge() == 0.0
    assert p.GetMinFiringCharge() == 0.0
    assert p.GetNormalDischargeRate() == 0.0
    assert p.GetRechargeRate() == 0.0


def test_energy_weapon_charge_fields_roundtrip():
    p = EnergyWeaponProperty("Test")
    p.SetMaxCharge(5.0)
    p.SetMinFiringCharge(3.0)
    p.SetNormalDischargeRate(1.0)
    p.SetRechargeRate(0.08)
    assert p.GetMaxCharge() == 5.0
    assert p.GetMinFiringCharge() == 3.0
    assert p.GetNormalDischargeRate() == 1.0
    assert p.GetRechargeRate() == 0.08


def test_energy_weapon_charge_setters_coerce_to_float():
    p = EnergyWeaponProperty("Test")
    p.SetMaxCharge(5)  # int input
    assert isinstance(p.GetMaxCharge(), float)
    assert p.GetMaxCharge() == 5.0


def test_phaser_inherits_energy_weapon_charge_surface():
    p = PhaserProperty("Galaxy Dorsal 1")
    p.SetMaxCharge(5.0)
    assert p.GetMaxCharge() == 5.0


def test_tractor_inherits_energy_weapon_charge_surface():
    p = TractorBeamProperty("Forward Tractor 1")
    p.SetRechargeRate(0.3)
    assert p.GetRechargeRate() == 0.3


def test_pulse_weapon_inherits_charge_surface():
    p = PulseWeaponProperty("Forward Pulse")
    p.SetMaxCharge(2.0)
    assert p.GetMaxCharge() == 2.0


def test_pulse_weapon_cooldown_default_zero():
    p = PulseWeaponProperty("Forward Pulse")
    assert p.GetCooldownTime() == 0.0


def test_pulse_weapon_cooldown_roundtrip():
    p = PulseWeaponProperty("Forward Pulse")
    p.SetCooldownTime(0.3)
    assert p.GetCooldownTime() == 0.3


def test_torpedo_tube_reload_fields_default_zero():
    t = TorpedoTubeProperty("Forward Torpedo 1")
    assert t.GetImmediateDelay() == 0.0
    assert t.GetReloadDelay() == 0.0
    assert t.GetMaxReady() == 0


def test_torpedo_tube_reload_fields_roundtrip():
    t = TorpedoTubeProperty("Forward Torpedo 1")
    t.SetImmediateDelay(0.25)
    t.SetReloadDelay(40.0)
    t.SetMaxReady(1)
    assert t.GetImmediateDelay() == 0.25
    assert t.GetReloadDelay() == 40.0
    assert t.GetMaxReady() == 1


def test_torpedo_tube_max_ready_coerces_to_int():
    t = TorpedoTubeProperty("Forward Torpedo 1")
    t.SetMaxReady(1.0)  # hardpoint files have inconsistent typing
    assert isinstance(t.GetMaxReady(), int)
    assert t.GetMaxReady() == 1


def test_energy_weapon_fire_sound_default_empty():
    p = EnergyWeaponProperty("Test")
    assert p.GetFireSound() == ""


def test_energy_weapon_fire_sound_roundtrip():
    p = EnergyWeaponProperty("Test")
    p.SetFireSound("Galaxy Phaser")
    assert p.GetFireSound() == "Galaxy Phaser"


def test_phaser_inherits_fire_sound():
    p = PhaserProperty("Dorsal Phaser 1")
    p.SetFireSound("Galaxy Phaser")
    assert p.GetFireSound() == "Galaxy Phaser"
