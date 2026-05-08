# Model Property Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `_NamedStub` fallback for `g_kModelPropertyManager`, the `TGModelProperty` hierarchy, and `TGModelPropertySet` with real implementations so configured property values (shield max, weapon damage, charge rates, etc.) are stored and retrievable.

**Architecture:** New `engine/appc/properties.py` module containing `TGModelProperty` (data-bag base with `__getattr__`-driven Set*/Get*), the property subclass hierarchy (with class-level constants only), `TGModelPropertyManager` (two name-keyed dicts for LOCAL/GLOBAL templates), and `TGModelPropertySet` (list of `(node_name, prop)` tuples with iterator). `App.py` imports the public surface and creates `g_kModelPropertyManager = TGModelPropertyManager()` as an explicit module-level singleton. Renderer-only methods (RegisterFilter, etc.) remain `_NamedStub`.

**Tech Stack:** Python 3.11+, pytest, existing `engine/appc/` module convention, existing `App.py` shim, `tools/gameloop_harness.py`.

---

## File Map

- **Create:** `engine/appc/properties.py` — `TGModelProperty` base, all subclasses, constants, factory functions, `TGModelPropertyManager`, `TGModelPropertySet`, internal iterator.
- **Modify:** `App.py` — add imports from `engine.appc.properties`, add `g_kModelPropertyManager = TGModelPropertyManager()` singleton.
- **Create:** `tests/unit/test_properties.py` — unit tests for the base, hierarchy, factories, manager, and set.

Spec reference: [docs/superpowers/specs/2026-05-08-model-property-manager-design.md](../specs/2026-05-08-model-property-manager-design.md).

---

### Task 1: `TGModelProperty` base — data-bag mechanics

**Files:**
- Create: `engine/appc/properties.py`
- Create: `tests/unit/test_properties.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/unit/test_properties.py`:

```python
import pytest
from engine.appc.properties import TGModelProperty


def test_name_storage():
    p = TGModelProperty("Hull")
    assert p.GetName() == "Hull"
    p.SetName("New Hull")
    assert p.GetName() == "New Hull"


def test_bool_is_true():
    p = TGModelProperty("X")
    assert bool(p) is True


def test_repr_contains_class_and_name():
    p = TGModelProperty("Hull")
    assert "TGModelProperty" in repr(p)
    assert "Hull" in repr(p)


def test_data_bag_single_arg():
    p = TGModelProperty("X")
    p.SetMaxCondition(5000)
    assert p.GetMaxCondition() == 5000


def test_data_bag_multi_arg():
    p = TGModelProperty("X")
    p.SetMaxShields(0, 4500.0)
    p.SetMaxShields(1, 3000.0)
    assert p.GetMaxShields(0) == 4500.0
    assert p.GetMaxShields(1) == 3000.0


def test_data_bag_unknown_returns_none():
    p = TGModelProperty("X")
    assert p.GetMaxCondition() is None
    assert p.GetMaxShields(0) is None


def test_unknown_attribute_raises():
    p = TGModelProperty("X")
    with pytest.raises(AttributeError):
        p.NotASetterOrGetter
```

- [ ] **Step 2: Run tests to verify they fail with import error**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.appc.properties'`

- [ ] **Step 3: Create `engine/appc/properties.py` with the base class**

Create `engine/appc/properties.py`:

```python
"""TGModelProperty hierarchy + manager.

See docs/superpowers/specs/2026-05-08-model-property-manager-design.md.
"""


class TGModelProperty:
    def __init__(self, name: str):
        self._name = name
        self._data: dict = {}

    def GetName(self) -> str:
        return self._name

    def SetName(self, value: str) -> None:
        self._name = value

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._name!r}>"

    def __getattr__(self, attr: str):
        if attr.startswith("Set"):
            field = attr[3:]
            data = self._data
            def setter(*args):
                data[(field, args[:-1])] = args[-1]
            return setter
        if attr.startswith("Get"):
            field = attr[3:]
            data = self._data
            def getter(*args):
                return data.get((field, args), None)
            return getter
        raise AttributeError(attr)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/appc/properties.py tests/unit/test_properties.py
git commit -m "$(cat <<'EOF'
feat(properties): add TGModelProperty data-bag base class

Set*/Get* method pairs are dispatched through __getattr__ so the full
SDK surface works without per-method boilerplate. Multi-arg setters
like SetMaxShields(face, value) key on (field, args[:-1]).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Property subclass hierarchy + constants

**Files:**
- Modify: `engine/appc/properties.py`
- Modify: `tests/unit/test_properties.py`

- [ ] **Step 1: Append failing tests for the hierarchy and constants**

Append to `tests/unit/test_properties.py`:

```python
from engine.appc.properties import (
    PositionOrientationProperty, EngineGlowProperty,
    SubsystemProperty, HullProperty, PowerProperty,
    WeaponProperty, EnergyWeaponProperty,
    PhaserProperty, PulseWeaponProperty, TractorBeamProperty,
    TorpedoTubeProperty,
    PoweredSubsystemProperty,
    ShieldProperty, SensorProperty, RepairSubsystemProperty,
    WeaponSystemProperty, TorpedoSystemProperty,
)


def test_subclass_isinstance_chain():
    p = PhaserProperty("X")
    assert isinstance(p, EnergyWeaponProperty)
    assert isinstance(p, WeaponProperty)
    assert isinstance(p, SubsystemProperty)
    assert isinstance(p, TGModelProperty)


def test_shield_property_inherits_powered_subsystem():
    p = ShieldProperty("X")
    assert isinstance(p, PoweredSubsystemProperty)
    assert isinstance(p, SubsystemProperty)


def test_torpedo_system_inherits_weapon_system():
    p = TorpedoSystemProperty("X")
    assert isinstance(p, WeaponSystemProperty)
    assert isinstance(p, PoweredSubsystemProperty)


def test_shield_face_constants():
    assert ShieldProperty.FRONT_SHIELDS == 0
    assert ShieldProperty.REAR_SHIELDS == 1
    assert ShieldProperty.TOP_SHIELDS == 2
    assert ShieldProperty.BOTTOM_SHIELDS == 3
    assert ShieldProperty.LEFT_SHIELDS == 4
    assert ShieldProperty.RIGHT_SHIELDS == 5
    assert ShieldProperty.NUM_SHIELDS == 6


def test_weapon_system_type_constants():
    assert WeaponSystemProperty.WST_UNKNOWN == 0
    assert WeaponSystemProperty.WST_PHASER == 1
    assert WeaponSystemProperty.WST_TORPEDO == 2
    assert WeaponSystemProperty.WST_PULSE == 3
    assert WeaponSystemProperty.WST_TRACTOR == 4


def test_data_bag_works_on_subclasses():
    p = ShieldProperty("Shield Generator")
    p.SetMaxShields(ShieldProperty.FRONT_SHIELDS, 4500.0)
    assert p.GetMaxShields(ShieldProperty.FRONT_SHIELDS) == 4500.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: New tests FAIL with `ImportError`.

- [ ] **Step 3: Append the subclass hierarchy to `engine/appc/properties.py`**

Append to `engine/appc/properties.py`:

```python
# ── Subclass hierarchy ────────────────────────────────────────────────────────
# Subclasses are thin: only class-level constants. All Set*/Get* behaviour is
# inherited from the data-bag base.

class PositionOrientationProperty(TGModelProperty):
    pass


class EngineGlowProperty(TGModelProperty):
    pass


class SubsystemProperty(TGModelProperty):
    pass


class HullProperty(SubsystemProperty):
    pass


class PowerProperty(SubsystemProperty):
    pass


class WeaponProperty(SubsystemProperty):
    pass


class EnergyWeaponProperty(WeaponProperty):
    pass


class PhaserProperty(EnergyWeaponProperty):
    pass


class PulseWeaponProperty(EnergyWeaponProperty):
    pass


class TractorBeamProperty(EnergyWeaponProperty):
    pass


class TorpedoTubeProperty(WeaponProperty):
    pass


class PoweredSubsystemProperty(SubsystemProperty):
    pass


class ShieldProperty(PoweredSubsystemProperty):
    FRONT_SHIELDS  = 0
    REAR_SHIELDS   = 1
    TOP_SHIELDS    = 2
    BOTTOM_SHIELDS = 3
    LEFT_SHIELDS   = 4
    RIGHT_SHIELDS  = 5
    NUM_SHIELDS    = 6


class SensorProperty(PoweredSubsystemProperty):
    pass


class RepairSubsystemProperty(PoweredSubsystemProperty):
    pass


class WeaponSystemProperty(PoweredSubsystemProperty):
    WST_UNKNOWN = 0
    WST_PHASER  = 1
    WST_TORPEDO = 2
    WST_PULSE   = 3
    WST_TRACTOR = 4


class TorpedoSystemProperty(WeaponSystemProperty):
    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: All tests PASS (14 total).

- [ ] **Step 5: Commit**

```bash
git add engine/appc/properties.py tests/unit/test_properties.py
git commit -m "$(cat <<'EOF'
feat(properties): add TGModelProperty subclass hierarchy

Mirrors the SDK's class tree (Phaser → EnergyWeapon → Weapon →
Subsystem → TGModelProperty, etc.) with class-level constants for
shield faces and weapon system types. All Set*/Get* behaviour is
inherited from the data-bag base.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Factory functions

**Files:**
- Modify: `engine/appc/properties.py`
- Modify: `tests/unit/test_properties.py`

- [ ] **Step 1: Append failing tests for the factories**

Append to `tests/unit/test_properties.py`:

```python
from engine.appc.properties import (
    PositionOrientationProperty_Create,
    HullProperty_Create, PowerProperty_Create,
    PhaserProperty_Create, PulseWeaponProperty_Create,
    TractorBeamProperty_Create, TorpedoTubeProperty_Create,
    ShieldProperty_Create, SensorProperty_Create,
    RepairSubsystemProperty_Create, TorpedoSystemProperty_Create,
)


@pytest.mark.parametrize("factory,cls", [
    (PositionOrientationProperty_Create, PositionOrientationProperty),
    (HullProperty_Create, HullProperty),
    (PowerProperty_Create, PowerProperty),
    (PhaserProperty_Create, PhaserProperty),
    (PulseWeaponProperty_Create, PulseWeaponProperty),
    (TractorBeamProperty_Create, TractorBeamProperty),
    (TorpedoTubeProperty_Create, TorpedoTubeProperty),
    (ShieldProperty_Create, ShieldProperty),
    (SensorProperty_Create, SensorProperty),
    (RepairSubsystemProperty_Create, RepairSubsystemProperty),
    (TorpedoSystemProperty_Create, TorpedoSystemProperty),
])
def test_factory_returns_correct_subclass(factory, cls):
    p = factory("Test Name")
    assert isinstance(p, cls)
    assert p.GetName() == "Test Name"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: New parametrized tests FAIL with `ImportError`.

- [ ] **Step 3: Append factory functions to `engine/appc/properties.py`**

Append to `engine/appc/properties.py`:

```python
# ── Factory functions ─────────────────────────────────────────────────────────
# SDK call sites use App.XxxProperty_Create("Name") rather than the
# constructor directly. These mirror the SDK's Appc.new_XxxProperty pattern.

def PositionOrientationProperty_Create(name): return PositionOrientationProperty(name)
def HullProperty_Create(name):                return HullProperty(name)
def PowerProperty_Create(name):               return PowerProperty(name)
def PhaserProperty_Create(name):              return PhaserProperty(name)
def PulseWeaponProperty_Create(name):         return PulseWeaponProperty(name)
def TractorBeamProperty_Create(name):         return TractorBeamProperty(name)
def TorpedoTubeProperty_Create(name):         return TorpedoTubeProperty(name)
def ShieldProperty_Create(name):              return ShieldProperty(name)
def SensorProperty_Create(name):              return SensorProperty(name)
def RepairSubsystemProperty_Create(name):     return RepairSubsystemProperty(name)
def TorpedoSystemProperty_Create(name):       return TorpedoSystemProperty(name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: All tests PASS (25 total — 14 prior + 11 parametrized).

- [ ] **Step 5: Commit**

```bash
git add engine/appc/properties.py tests/unit/test_properties.py
git commit -m "$(cat <<'EOF'
feat(properties): add XxxProperty_Create factory functions

Mirror the SDK's Appc.new_XxxProperty pattern. Hardpoint scripts call
App.ShieldProperty_Create("Shield Generator"), etc., so each subclass
gets a matching factory.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `TGModelPropertyManager`

**Files:**
- Modify: `engine/appc/properties.py`
- Modify: `tests/unit/test_properties.py`

- [ ] **Step 1: Append failing tests for the manager**

Append to `tests/unit/test_properties.py`:

```python
from engine.appc.properties import TGModelPropertyManager


@pytest.fixture
def mgr():
    return TGModelPropertyManager()


def test_scope_constants():
    assert TGModelPropertyManager.LOCAL_TEMPLATES == 0
    assert TGModelPropertyManager.GLOBAL_TEMPLATES == 1


def test_register_local_then_find(mgr):
    p = HullProperty("Hull")
    mgr.RegisterLocalTemplate(p)
    assert mgr.FindByName("Hull", TGModelPropertyManager.LOCAL_TEMPLATES) is p


def test_register_global_then_find(mgr):
    p = HullProperty("Hull")
    mgr.RegisterGlobalTemplate(p)
    assert mgr.FindByName("Hull", TGModelPropertyManager.GLOBAL_TEMPLATES) is p


def test_find_by_name_unknown_returns_none(mgr):
    assert mgr.FindByName("Missing", TGModelPropertyManager.LOCAL_TEMPLATES) is None
    assert mgr.FindByName("Missing", TGModelPropertyManager.GLOBAL_TEMPLATES) is None


def test_local_and_global_scopes_are_independent(mgr):
    local_hull = HullProperty("Hull")
    global_hull = HullProperty("Hull")
    mgr.RegisterLocalTemplate(local_hull)
    mgr.RegisterGlobalTemplate(global_hull)
    assert mgr.FindByName("Hull", TGModelPropertyManager.LOCAL_TEMPLATES) is local_hull
    assert mgr.FindByName("Hull", TGModelPropertyManager.GLOBAL_TEMPLATES) is global_hull


def test_clear_local_does_not_affect_global(mgr):
    mgr.RegisterLocalTemplate(HullProperty("L"))
    mgr.RegisterGlobalTemplate(HullProperty("G"))
    mgr.ClearLocalTemplates()
    assert mgr.FindByName("L", TGModelPropertyManager.LOCAL_TEMPLATES) is None
    assert mgr.FindByName("G", TGModelPropertyManager.GLOBAL_TEMPLATES) is not None


def test_clear_global_does_not_affect_local(mgr):
    mgr.RegisterLocalTemplate(HullProperty("L"))
    mgr.RegisterGlobalTemplate(HullProperty("G"))
    mgr.ClearGlobalTemplates()
    assert mgr.FindByName("L", TGModelPropertyManager.LOCAL_TEMPLATES) is not None
    assert mgr.FindByName("G", TGModelPropertyManager.GLOBAL_TEMPLATES) is None


def test_find_by_name_and_type_match(mgr):
    p = ShieldProperty("Shields")
    mgr.RegisterLocalTemplate(p)
    found = mgr.FindByNameAndType("Shields", ShieldProperty, TGModelPropertyManager.LOCAL_TEMPLATES)
    assert found is p


def test_find_by_name_and_type_mismatch(mgr):
    p = ShieldProperty("Shields")
    mgr.RegisterLocalTemplate(p)
    found = mgr.FindByNameAndType("Shields", HullProperty, TGModelPropertyManager.LOCAL_TEMPLATES)
    assert found is None


def test_is_local_and_is_global(mgr):
    local_p = HullProperty("L")
    global_p = HullProperty("G")
    mgr.RegisterLocalTemplate(local_p)
    mgr.RegisterGlobalTemplate(global_p)
    assert mgr.IsLocalTemplate(local_p) is True
    assert mgr.IsLocalTemplate(global_p) is False
    assert mgr.IsGlobalTemplate(global_p) is True
    assert mgr.IsGlobalTemplate(local_p) is False


def test_remove_template(mgr):
    p = HullProperty("Hull")
    mgr.RegisterLocalTemplate(p)
    mgr.RemoveTemplate(p)
    assert mgr.FindByName("Hull", TGModelPropertyManager.LOCAL_TEMPLATES) is None
    assert mgr.IsLocalTemplate(p) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: New tests FAIL with `ImportError: cannot import name 'TGModelPropertyManager'`.

- [ ] **Step 3: Append the manager to `engine/appc/properties.py`**

Append to `engine/appc/properties.py`:

```python
# ── TGModelPropertyManager ────────────────────────────────────────────────────
# loadspacehelper.py:90 calls ClearLocalTemplates() between ship loads, so the
# manager is genuinely stateful across hardpoint imports. App.py's singleton
# lives for the whole session.
#
# Renderer-only methods (RegisterFilter, AddFilter, ApplyFilters, etc.) are
# Phase 2 concerns; they fall through to App.py's _NamedStub via __getattr__.

class TGModelPropertyManager:
    LOCAL_TEMPLATES  = 0
    GLOBAL_TEMPLATES = 1

    def __init__(self):
        self._local: dict = {}
        self._global: dict = {}

    def _store(self, scope):
        return self._local if scope == self.LOCAL_TEMPLATES else self._global

    def RegisterLocalTemplate(self, prop):
        self._local[prop.GetName()] = prop

    def RegisterGlobalTemplate(self, prop):
        self._global[prop.GetName()] = prop

    def ClearLocalTemplates(self):
        self._local.clear()

    def ClearGlobalTemplates(self):
        self._global.clear()

    def FindByName(self, name, scope):
        return self._store(scope).get(name)

    def FindByNameAndType(self, name, type_cls, scope):
        prop = self._store(scope).get(name)
        return prop if isinstance(prop, type_cls) else None

    def IsLocalTemplate(self, prop):
        return prop in self._local.values()

    def IsGlobalTemplate(self, prop):
        return prop in self._global.values()

    def RemoveTemplate(self, prop):
        self._local  = {k: v for k, v in self._local.items()  if v is not prop}
        self._global = {k: v for k, v in self._global.items() if v is not prop}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: All tests PASS (36 total).

- [ ] **Step 5: Commit**

```bash
git add engine/appc/properties.py tests/unit/test_properties.py
git commit -m "$(cat <<'EOF'
feat(properties): add TGModelPropertyManager

Two name-keyed dicts for LOCAL/GLOBAL templates with
register/find/clear/remove. Renderer-only filter methods are
deliberately omitted -- they remain _NamedStub fallbacks.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `TGModelPropertySet` + iterator

**Files:**
- Modify: `engine/appc/properties.py`
- Modify: `tests/unit/test_properties.py`

- [ ] **Step 1: Append failing tests for the set**

Append to `tests/unit/test_properties.py`:

```python
from engine.appc.properties import TGModelPropertySet


def test_property_set_starts_empty():
    s = TGModelPropertySet()
    items = list(s.GetPropertyList())
    assert items == []


def test_property_set_add_to_set_appends():
    s = TGModelPropertySet()
    hull = HullProperty("Hull")
    shield = ShieldProperty("Shield Generator")
    s.AddToSet("Scene Root", hull)
    s.AddToSet("Scene Root", shield)
    items = list(s.GetPropertyList())
    assert items == [hull, shield]


def test_property_set_get_properties_by_type():
    s = TGModelPropertySet()
    hull = HullProperty("Hull")
    shield = ShieldProperty("Shield Generator")
    phaser = PhaserProperty("Forward Phaser")
    s.AddToSet("Scene Root", hull)
    s.AddToSet("Scene Root", shield)
    s.AddToSet("Scene Root", phaser)
    weapons = list(s.GetPropertiesByType(WeaponProperty))
    assert weapons == [phaser]
    subsystems = list(s.GetPropertiesByType(SubsystemProperty))
    assert subsystems == [hull, shield, phaser]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: New tests FAIL with `ImportError`.

- [ ] **Step 3: Append the set + iterator to `engine/appc/properties.py`**

Append to `engine/appc/properties.py`:

```python
# ── TGModelPropertySet ────────────────────────────────────────────────────────
# Holds (node_name, prop) pairs. node_name (e.g. "Scene Root") is a renderer
# concept stored but unused in Phase 1.

class TGModelPropertySet:
    def __init__(self):
        self._entries: list = []

    def AddToSet(self, node_name, prop):
        self._entries.append((node_name, prop))

    def GetPropertyList(self):
        return iter([prop for _node, prop in self._entries])

    def GetPropertiesByType(self, type_cls):
        return iter([prop for _node, prop in self._entries if isinstance(prop, type_cls)])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_properties.py -v`
Expected: All tests PASS (39 total).

- [ ] **Step 5: Commit**

```bash
git add engine/appc/properties.py tests/unit/test_properties.py
git commit -m "$(cat <<'EOF'
feat(properties): add TGModelPropertySet

Holds (node_name, prop) tuples. GetPropertyList iterates all props;
GetPropertiesByType filters by isinstance.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Wire up App.py — imports and singleton

**Files:**
- Modify: `App.py` (add imports near the top, add singleton near the other singletons around line 44)
- Create: `tests/unit/test_app_properties.py` (new file to verify App.py exposure)

- [ ] **Step 1: Write a failing test for the App-level surface**

Create `tests/unit/test_app_properties.py`:

```python
import App
from engine.appc.properties import (
    TGModelPropertyManager, ShieldProperty, HullProperty,
)


def test_app_exposes_real_manager():
    assert isinstance(App.g_kModelPropertyManager, TGModelPropertyManager)


def test_app_exposes_factories():
    p = App.ShieldProperty_Create("Shield Generator")
    assert isinstance(p, ShieldProperty)
    assert p.GetName() == "Shield Generator"


def test_app_exposes_class_constants():
    assert App.TGModelPropertyManager.LOCAL_TEMPLATES == 0
    assert App.ShieldProperty.FRONT_SHIELDS == 0
    assert App.WeaponSystemProperty.WST_TORPEDO == 2


def test_round_trip_through_app_namespace():
    App.g_kModelPropertyManager.ClearLocalTemplates()
    hull = App.HullProperty_Create("Hull")
    hull.SetMaxCondition(7000.0)
    App.g_kModelPropertyManager.RegisterLocalTemplate(hull)
    found = App.g_kModelPropertyManager.FindByName(
        "Hull", App.TGModelPropertyManager.LOCAL_TEMPLATES
    )
    assert found is hull
    assert found.GetMaxCondition() == 7000.0
    App.g_kModelPropertyManager.ClearLocalTemplates()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_app_properties.py -v`
Expected: FAIL — `App.g_kModelPropertyManager` is currently a `_NamedStub`, not a `TGModelPropertyManager`.

- [ ] **Step 3: Add imports + singleton to `App.py`**

In [App.py](App.py), insert after the existing `from engine.core.game import ...` line (around line 31) and before `# ── Numeric constants ──`:

```python
from engine.appc.properties import (
    TGModelProperty,
    TGModelPropertyManager, TGModelPropertySet,
    PositionOrientationProperty,
    EngineGlowProperty,
    SubsystemProperty,
    HullProperty, PowerProperty,
    WeaponProperty, EnergyWeaponProperty,
    PhaserProperty, PulseWeaponProperty, TractorBeamProperty,
    TorpedoTubeProperty,
    PoweredSubsystemProperty,
    ShieldProperty, SensorProperty, RepairSubsystemProperty,
    WeaponSystemProperty, TorpedoSystemProperty,
    PositionOrientationProperty_Create,
    HullProperty_Create, PowerProperty_Create,
    PhaserProperty_Create, PulseWeaponProperty_Create,
    TractorBeamProperty_Create, TorpedoTubeProperty_Create,
    ShieldProperty_Create, SensorProperty_Create,
    RepairSubsystemProperty_Create, TorpedoSystemProperty_Create,
)
```

Then in the `# ── Singletons ──` block (currently lines 40-44), append after `g_kTGActionManager = TGActionManager()`:

```python
g_kModelPropertyManager = TGModelPropertyManager()
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `uv run pytest tests/unit/test_app_properties.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Run the full unit suite to confirm no regressions**

Run: `uv run pytest tests/unit -v`
Expected: All tests PASS (existing + new properties + new app_properties).

- [ ] **Step 6: Commit**

```bash
git add App.py tests/unit/test_app_properties.py
git commit -m "$(cat <<'EOF'
feat(App): wire up real g_kModelPropertyManager singleton

Replace the _NamedStub fallback for g_kModelPropertyManager with a
real TGModelPropertyManager. Import the full property class hierarchy
and factory functions so SDK call sites resolve to real
implementations instead of stubs.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Integration verification — harness still passes

**Files:**
- (No file changes — verification only.)

- [ ] **Step 1: Run the gameloop harness to confirm 35/35 still passes**

Run: `uv run python tools/gameloop_harness.py --ticks 60`
Expected: `PASS: 35`, `INIT FAIL: 0`, `LOOP FAIL: 0`.

- [ ] **Step 2: Run the harness with `--profile` to confirm property cluster moved out of stub list**

Run: `uv run python tools/gameloop_harness.py --profile --ticks 60`
Expected:
- `PASS: 35` still.
- `g_kModelPropertyManager.FindByName` no longer appears in the profile (it's now a real method).
- `g_kModelPropertyManager.RegisterLocalTemplate` no longer appears.
- `TGModelPropertySet().AddToSet` no longer appears.
- `PhaserProperty_Create` and similar `XxxProperty_Create` calls no longer appear.
- The next tier of stubs (e.g. `pObj.AddToSet` on ship objects, `LensFlare_Create`) becomes the new top of the list.

- [ ] **Step 3: Run the full test suite as a final check**

Run: `uv run pytest`
Expected: All tests PASS (unit + integration).

- [ ] **Step 4: No commit needed** — verification step only.

---

## Self-Review Notes

**Spec coverage check:**
- Goal #1 (RegisterLocalTemplate persists by name) → Task 4
- Goal #2 (FindByName retrieves) → Task 4
- Goal #3 (Set*/Get* store/return correctly) → Task 1
- Goal #4 (ClearLocalTemplates between ship loads) → Task 4
- Goal #5 (harness still passes 35/35) → Task 7

**Hierarchy coverage:** All 16 named subclasses from the spec tree appear in Task 2.

**Constants coverage:** Shield faces (Task 2), WeaponSystemProperty types (Task 2).

**Factory coverage:** 11 factories listed in Task 3 — matches all `_Create` calls observed in hardpoints.

**Test coverage:** 39 unit tests for `engine.appc.properties` + 4 for App.py wire-up.
