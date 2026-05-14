"""WeaponSystem.GetNumWeapons / GetWeapon(i) — SDK-faithful aliases over
GetNumChildSubsystems / GetChildSubsystem.  TacticalInterfaceHandlers.
FireWeapons in PR 2 calls these.
"""
from engine.appc.subsystems import PhaserSystem, PhaserBank


def test_get_num_weapons_empty():
    ps = PhaserSystem("Phasers")
    assert ps.GetNumWeapons() == 0


def test_get_num_weapons_counts_child_emitters():
    ps = PhaserSystem("Phasers")
    ps.AddChildSubsystem(PhaserBank("Dorsal Phaser 1"))
    ps.AddChildSubsystem(PhaserBank("Dorsal Phaser 2"))
    assert ps.GetNumWeapons() == 2


def test_get_weapon_returns_child_at_index():
    ps = PhaserSystem("Phasers")
    b1 = PhaserBank("Dorsal Phaser 1")
    b2 = PhaserBank("Dorsal Phaser 2")
    ps.AddChildSubsystem(b1)
    ps.AddChildSubsystem(b2)
    assert ps.GetWeapon(0) is b1
    assert ps.GetWeapon(1) is b2


def test_get_weapon_out_of_range_returns_none():
    ps = PhaserSystem("Phasers")
    assert ps.GetWeapon(0) is None
    ps.AddChildSubsystem(PhaserBank("Dorsal Phaser 1"))
    assert ps.GetWeapon(5) is None
