"""populated_subsystems iterates the canonical getters and skips None slots."""
from engine.ui.target_list import populated_subsystems


class _Sub:
    def __init__(self, name): self._name = name
    def GetName(self): return self._name


class _ShipAllPopulated:
    def GetHull(self):                  return _Sub("Custom Hull")
    def GetSensorSubsystem(self):       return _Sub("Sensor Subsystem")
    def GetImpulseEngineSubsystem(self):return _Sub("Impulse Engines")
    def GetWarpEngineSubsystem(self):   return _Sub("Warp Engines")
    def GetPhaserSystem(self):          return _Sub("Phaser System")
    def GetPulseWeaponSystem(self):     return _Sub("Pulse Weapon System")
    def GetTorpedoSystem(self):         return _Sub("Torpedo System")
    def GetTractorBeamSystem(self):     return _Sub("Tractor Beam System")


class _ShipSparse:
    def GetHull(self):                  return None
    def GetSensorSubsystem(self):       return _Sub("Sensors")
    def GetImpulseEngineSubsystem(self):return None
    def GetWarpEngineSubsystem(self):   return None
    def GetPhaserSystem(self):          return None
    def GetPulseWeaponSystem(self):     return None
    def GetTorpedoSystem(self):         return None
    def GetTractorBeamSystem(self):     return None


class _ShipNameless:
    class _NamelessSub: pass
    def GetHull(self):                  return self._NamelessSub()
    def GetSensorSubsystem(self):       return None
    def GetImpulseEngineSubsystem(self):return None
    def GetWarpEngineSubsystem(self):   return None
    def GetPhaserSystem(self):          return None
    def GetPulseWeaponSystem(self):     return None
    def GetTorpedoSystem(self):         return None
    def GetTractorBeamSystem(self):     return None


class _ShipNoSubsystemGetters:
    pass


def test_all_populated_returns_eight_in_canonical_order():
    rows = populated_subsystems(_ShipAllPopulated())
    labels = [label for label, _ in rows]
    assert labels == [
        "Custom Hull", "Sensor Subsystem", "Impulse Engines",
        "Warp Engines", "Phaser System", "Pulse Weapon System",
        "Torpedo System", "Tractor Beam System",
    ]


def test_sparse_ship_returns_only_populated():
    rows = populated_subsystems(_ShipSparse())
    assert [label for label, _ in rows] == ["Sensors"]


def test_nameless_subsystem_falls_back_to_canonical_label():
    rows = populated_subsystems(_ShipNameless())
    assert [label for label, _ in rows] == ["Hull"]


def test_missing_getters_do_not_raise():
    assert populated_subsystems(_ShipNoSubsystemGetters()) == []


def test_returns_subsystem_instance_alongside_label():
    rows = populated_subsystems(_ShipSparse())
    label, sub = rows[0]
    assert label == "Sensors"
    assert sub.GetName() == "Sensors"
