# Shield render-prop promotion plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote `SkinShielding`, `ShieldGlowColor`, `ShieldGlowDecay` from `TGModelProperty.__getattr__` data-bag shims to real methods on `ShieldProperty`. Update `engine/shields.py` to read via the real getters. Preserve color-consumer tracker behavior.

**Architecture:** Same Task-5 pattern as the shield API plan: add fields + real methods with transition dual-write, migrate the consumer (`engine/shields.py`), rewrite the data-bag pin tests, drop the dual-write.

**Tech Stack:** Python 3, pytest. No native code.

**Spec:** [docs/superpowers/specs/2026-05-12-shield-render-props-design.md](../specs/2026-05-12-shield-render-props-design.md)

---

## File map

| File | Action |
|---|---|
| `engine/appc/properties.py` | Modify `ShieldProperty`: add three fields and six accessors with dual-write |
| `tests/unit/test_shield_property.py` | Extend with defaults / round-trip / real-methods / tracker tests |
| `engine/shields.py` | Modify `_color_tuple` + `register_ship_shield` to read via real getters |
| `tests/unit/test_shield_property_skin.py` | Rewrite four tests to pin the new interface |
| (Task 4) `engine/appc/properties.py` | Drop the three data-bag dual-writes |

---

### Task 1: Promote the three render props to real methods

Add fields and accessors with the Task-5 dual-write pattern. `SetShieldGlowColor` also records to the color-consumer tracker.

**Files:**
- Modify: `engine/appc/properties.py` `ShieldProperty`
- Modify: `tests/unit/test_shield_property.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_shield_property.py`:

```python
import App


def test_skin_shielding_default_zero():
    p = ShieldProperty("Shield Generator")
    assert p.GetSkinShielding() == 0


def test_skin_shielding_round_trip():
    p = ShieldProperty("Shield Generator")
    p.SetSkinShielding(1)
    assert p.GetSkinShielding() == 1
    p.SetSkinShielding(0)
    assert p.GetSkinShielding() == 0


def test_skin_shielding_coerces_to_int():
    p = ShieldProperty("Shield Generator")
    p.SetSkinShielding("1")
    assert p.GetSkinShielding() == 1


def test_shield_glow_decay_default_one():
    p = ShieldProperty("Shield Generator")
    assert p.GetShieldGlowDecay() == 1.0


def test_shield_glow_decay_round_trip():
    p = ShieldProperty("Shield Generator")
    p.SetShieldGlowDecay(2.5)
    assert p.GetShieldGlowDecay() == 2.5


def test_shield_glow_decay_coerces_to_float():
    p = ShieldProperty("Shield Generator")
    p.SetShieldGlowDecay("2.5")
    assert p.GetShieldGlowDecay() == 2.5


def test_shield_glow_color_default_none():
    """None is the 'absent' marker; engine/shields.py treats it as white."""
    p = ShieldProperty("Shield Generator")
    assert p.GetShieldGlowColor() is None


def test_shield_glow_color_round_trip():
    p = ShieldProperty("Shield Generator")
    color = App.TGColorA()
    color.SetRGBA(0.2, 0.4, 0.8, 1.0)
    p.SetShieldGlowColor(color)
    got = p.GetShieldGlowColor()
    assert got is color


def test_new_render_prop_methods_are_real_not_databag_shim():
    """Each new method must live on the class itself, not be synthesized
    by TGModelProperty.__getattr__."""
    for name in (
        "GetSkinShielding", "SetSkinShielding",
        "GetShieldGlowDecay", "SetShieldGlowDecay",
        "GetShieldGlowColor", "SetShieldGlowColor",
    ):
        assert name in vars(ShieldProperty), f"{name} missing from class"
    p = ShieldProperty("X")
    assert p.GetSkinShielding.__self__ is p
    assert p.SetShieldGlowColor.__self__ is p


def test_set_shield_glow_color_records_to_tracker():
    """Tracker hook must survive the promotion from __getattr__ shim
    to real method. Caller file/line and recorded name must match the
    pre-refactor shim's behavior."""
    App._color_consumer_tracker.clear()
    App._color_consumer_tracker.enable()
    App._stub_tracker.clear()
    App._stub_tracker.set_mission("tracker_test")

    try:
        p = ShieldProperty("Shield Generator")
        color = App.TGColorA()
        color.SetRGBA(0.5, 0.5, 0.5, 1.0)
        p.SetShieldGlowColor(color)
    finally:
        App._color_consumer_tracker.disable()
        App._stub_tracker.reset_mission()

    rows = App._color_consumer_tracker.report()
    names = [r[0] for r in rows]
    assert "ShieldProperty.SetShieldGlowColor" in names
```

- [ ] **Step 2: Run, confirm fail**

```bash
uv run pytest tests/unit/test_shield_property.py -v
```

Expected: nine new tests fail (or pass-via-shim on a few; the `vars(...)` and tracker tests definitely fail).

- [ ] **Step 3: Implement**

Edit `engine/appc/properties.py` `ShieldProperty` class. Modify `__init__` to add three new fields after the existing two lists:

```python
    def __init__(self, name: str = ""):
        super().__init__(name)
        self._max_shields = [0.0] * self.NUM_SHIELDS
        self._charge_per_second = [0.0] * self.NUM_SHIELDS
        self._skin_shielding: int = 0
        self._shield_glow_decay: float = 1.0
        self._shield_glow_color = None
```

Append these six accessors after `SetShieldChargePerSecond`:

```python
    def GetSkinShielding(self):
        return self._skin_shielding

    def SetSkinShielding(self, value):
        v = int(value)
        self._skin_shielding = v
        # Transition dual-write: existing data-bag readers keep working
        # until Task 4 removes this line.
        self._data[("SkinShielding", ())] = v

    def GetShieldGlowDecay(self):
        return self._shield_glow_decay

    def SetShieldGlowDecay(self, value):
        v = float(value)
        self._shield_glow_decay = v
        self._data[("ShieldGlowDecay", ())] = v

    def GetShieldGlowColor(self):
        return self._shield_glow_color

    def SetShieldGlowColor(self, color):
        self._shield_glow_color = color
        self._data[("ShieldGlowColor", ())] = color
        # Preserve the color-consumer tracker hook that TGModelProperty's
        # auto-synthesized setter used to provide.  Matches the shim's
        # _getframe(1) caller-attribution behavior in properties.py:32-43.
        import App as _App
        if _App._color_consumer_tracker.is_enabled():
            import sys as _sys
            frame = _sys._getframe(1)
            _App._color_consumer_tracker.record(
                "ShieldProperty.SetShieldGlowColor", color,
                frame.f_code.co_filename, frame.f_lineno,
            )
```

- [ ] **Step 4: Run new tests, confirm pass**

```bash
uv run pytest tests/unit/test_shield_property.py -v
```

- [ ] **Step 5: Run the full unit suite**

```bash
uv run pytest tests/unit -q
```

Expected: prior baseline (790) + 9 new = 799 passed. **No pre-existing tests should change status.** In particular:
- `tests/unit/test_shields.py` (renderer glue) still reads from `prop._data` via `engine/shields.py` — passes because of the dual-write.
- `tests/unit/test_shield_property_skin.py` still asserts the data-bag format — passes because of the dual-write.
- `tests/unit/test_color_consumer_tracker.py` — unchanged; doesn't exercise `ShieldProperty.SetShieldGlowColor` end-to-end on a real property.

- [ ] **Step 6: Commit**

```bash
git add engine/appc/properties.py tests/unit/test_shield_property.py
git commit -m "feat(shields): promote SkinShielding / ShieldGlowColor / ShieldGlowDecay to real methods

Adds six real accessors on ShieldProperty backed by instance fields,
with a transition dual-write to the data-bag. SetShieldGlowColor
preserves the color-consumer tracker hook that TGModelProperty's
auto-synthesized setter previously provided.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Switch engine/shields.py to read via real getters

Now that the property has real getters, the renderer glue can stop poking `prop._data` directly.

**Files:**
- Modify: `engine/shields.py` (`_color_tuple`, `register_ship_shield`)

- [ ] **Step 1: Confirm the renderer-glue tests are pinning the behavior we care about**

```bash
uv run pytest tests/unit/test_shields.py -v
```

Expected: all six tests pass.  These are the contract we must preserve.

- [ ] **Step 2: Modify `engine/shields.py`**

Replace `_color_tuple` and the relevant portion of `register_ship_shield`:

```python
def _color_tuple(prop, default=(1.0, 1.0, 1.0, 1.0)):
    """Read the ship's ShieldGlowColor as an RGBA tuple, default white."""
    val = prop.GetShieldGlowColor()
    if isinstance(val, App.TGColorA):
        return (val.r, val.g, val.b, val.a)
    return default


def register_ship_shield(host, instance_id, ship,
                         aabb_center, aabb_half_extents):
    """Push a ship's shield render state to the C++ pass.

    Reads the ship's ShieldProperty for:
    - ShieldGlowColor → default flash color
    - ShieldGlowDecay → exponential decay constant (seconds)
    - SkinShielding   → 1 = hull-conforming, 0/absent = ellipsoid (default)

    Silently does nothing if the ship has no ShieldProperty subsystem
    (asteroids, debris, etc.). Hardpoints that want a shielded ship must
    instantiate App.ShieldProperty_Create(...) and register it on the ship."""
    prop = _find_shield_property(ship)
    if prop is None:
        return
    skin = prop.GetSkinShielding()
    mode = SHIELD_MODE_SKIN if skin else SHIELD_MODE_ELLIPSOID
    decay = prop.GetShieldGlowDecay()
    color = _color_tuple(prop)
    host.shield_register(
        instance_id=instance_id,
        mode=mode,
        decay_seconds=float(decay),
        default_color=color,
        aabb_center=tuple(aabb_center),
        aabb_half_extents=tuple(aabb_half_extents),
    )
```

The `key` parameter to `_color_tuple` is gone — there's only one color attribute, so the indirection bought us nothing.

- [ ] **Step 3: Run the renderer-glue tests**

```bash
uv run pytest tests/unit/test_shields.py -v
```

Expected: all six tests still pass. The dual-write on the property side means the data-bag still has the values, so even if a stale code path read from `_data` it would still get the right values — but `engine/shields.py` no longer does that.

- [ ] **Step 4: Run the full suite**

```bash
uv run pytest tests/unit -q
```

Expected: 799 still pass.

- [ ] **Step 5: Commit**

```bash
git add engine/shields.py
git commit -m "refactor(shields): renderer glue reads via ShieldProperty getters

Drops the prop._data.get(...) reads for SkinShielding / ShieldGlowColor /
ShieldGlowDecay. _color_tuple loses the key parameter (only one color
attribute exists).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Rewrite the data-bag pin tests

`tests/unit/test_shield_property_skin.py` was deliberately written as a tripwire for "a future refactor of the data-bag" — this work *is* that refactor. The tests pin the wrong layer now (the storage detail rather than the contract). Rewrite to pin the new interface.

**Files:**
- Modify: `tests/unit/test_shield_property_skin.py`

- [ ] **Step 1: Replace the file**

Replace the entire contents of `tests/unit/test_shield_property_skin.py` with:

```python
"""Pin the SetSkinShielding interface contract.

Originally this file pinned the TGModelProperty data-bag storage format
because SkinShielding had no explicit accessor on ShieldProperty.  After
the render-prop promotion (docs/superpowers/specs/2026-05-12-shield-render-props-design.md)
SkinShielding is a real attribute, and these tests pin the new interface:
that hardpoint scripts opting in via App.ShieldProperty_Create(...).SetSkinShielding(1)
end up with GetSkinShielding() == 1 on the property the renderer sees.
"""
from engine.appc.properties import ShieldProperty


def test_set_skin_shielding_stores_value():
    shield = ShieldProperty("Shield Generator")
    shield.SetSkinShielding(1)
    assert shield.GetSkinShielding() == 1


def test_default_skin_shielding_zero():
    shield = ShieldProperty("Shield Generator")
    assert shield.GetSkinShielding() == 0


def test_set_skin_shielding_zero_stores_zero():
    shield = ShieldProperty("Shield Generator")
    shield.SetSkinShielding(1)
    shield.SetSkinShielding(0)
    assert shield.GetSkinShielding() == 0


def test_sovereign_hardpoint_opts_into_skin_shielding():
    """Importing the project-root sovereign hardpoint should result in
    SkinShielding=1 on its ShieldGenerator. Indirectly verifies that
    ships/Hardpoints/sovereign.py shadows the SDK copy via _SDKFinder."""
    import sys
    import importlib
    for k in list(sys.modules):
        if k == "ships" or k.startswith("ships."):
            del sys.modules[k]
    mod = importlib.import_module("ships.Hardpoints.sovereign")
    sg = getattr(mod, "ShieldGenerator")
    assert sg.GetSkinShielding() == 1
```

- [ ] **Step 2: Run**

```bash
uv run pytest tests/unit/test_shield_property_skin.py -v
```

Expected: all four pass.

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest tests/unit -q
```

Expected: 799 still.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_shield_property_skin.py
git commit -m "test(shields): pin SkinShielding via real accessor, not data-bag

Rewrites the four tests that previously asserted shield._data[...]
storage to assert GetSkinShielding() / SetSkinShielding() round-trip.
Same coverage, contract-level rather than implementation-level.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Drop the data-bag dual-write

Now that `engine/shields.py` and the rewritten skin-test read via real getters, no consumer needs the data-bag entries. Mirror Task 11 of the previous plan.

**Files:**
- Modify: `engine/appc/properties.py` (`SetSkinShielding`, `SetShieldGlowDecay`, `SetShieldGlowColor`)

- [ ] **Step 1: Search for remaining data-bag readers**

```bash
grep -rn '"SkinShielding"\|"ShieldGlowColor"\|"ShieldGlowDecay"\|_data\[.*SkinShielding\|_data\[.*ShieldGlowColor\|_data\[.*ShieldGlowDecay' \
  /Users/mward/Documents/Projects/open_stbc/engine \
  /Users/mward/Documents/Projects/open_stbc/native \
  /Users/mward/Documents/Projects/open_stbc/tests
```

Expected: only the three writes inside `engine/appc/properties.py` `SetSkinShielding` / `SetShieldGlowDecay` / `SetShieldGlowColor`. No readers.

If you find any external reader, STOP. Report **DONE_WITH_CONCERNS**, do not commit, name the reader's file and line. Suggest retaining the dual-write and migrating that reader in a follow-up.

- [ ] **Step 2: Remove the three `self._data[...]` writes**

In each of the three setters, delete the `self._data[...] = ...` line and the transition comment above `SetSkinShielding` ("Transition dual-write: ...").

For `SetShieldGlowColor`, only the `self._data[...]` line goes — the tracker hook stays. After:

```python
    def SetSkinShielding(self, value):
        self._skin_shielding = int(value)

    def SetShieldGlowDecay(self, value):
        self._shield_glow_decay = float(value)

    def SetShieldGlowColor(self, color):
        self._shield_glow_color = color
        import App as _App
        if _App._color_consumer_tracker.is_enabled():
            import sys as _sys
            frame = _sys._getframe(1)
            _App._color_consumer_tracker.record(
                "ShieldProperty.SetShieldGlowColor", color,
                frame.f_code.co_filename, frame.f_lineno,
            )
```

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest tests/unit -q
```

Expected: 799 passed, no regressions. The renderer-glue tests, the rewritten skin tests, and the new property tests all run independently of the data-bag for these three props.

- [ ] **Step 4: Commit**

```bash
git add engine/appc/properties.py
git commit -m "refactor(shields): drop data-bag dual-write for render props

Verified no remaining readers of self._data[(\"SkinShielding\", ())] /
self._data[(\"ShieldGlowColor\", ())] / self._data[(\"ShieldGlowDecay\", ())]
across engine/, native/, tests/. SetShieldGlowColor still records to the
color-consumer tracker.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Verification — final state

```bash
uv run pytest tests/unit -v
```

799 passed. `engine/shields.py` reads via `prop.GetSkinShielding()`, `prop.GetShieldGlowColor()`, `prop.GetShieldGlowDecay()` — no `prop._data` access in renderer-glue code. Color tracker continues to record `SetShieldGlowColor` calls.
