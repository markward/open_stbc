# Shield render-prop promotion — design

**Date:** 2026-05-12
**Status:** Approved, ready for plan
**Related:** [2026-05-12-shield-api-implementation-design.md](2026-05-12-shield-api-implementation-design.md) (Task 5 pattern this extends)

## Problem

The renderer side of `ShieldProperty` still reads three props through the data-bag in [engine/shields.py:64-67](../../../engine/shields.py#L64-L67):

```python
skin  = prop._data.get(("SkinShielding", ()), 0)
decay = prop._data.get(("ShieldGlowDecay", ()), 1.0)
color = _color_tuple(prop, "ShieldGlowColor")
```

The data-bag access works because `TGModelProperty.__getattr__` auto-synthesizes setters that store in `self._data`. Hardpoint scripts (`sovereign.py`, `sunbuster.py`, every shielded ship) call `Set{SkinShielding,ShieldGlowColor,ShieldGlowDecay}` and the storage flows through that shim.

The previous plan's final review flagged this as the follow-up: promote these three to real methods on `ShieldProperty`, mirroring the Task 5 pattern that promoted `MaxShields` / `ShieldChargePerSecond`. The renderer should read via real getters, not poke `prop._data`.

## Goal

After this work:
- `ShieldProperty.SetSkinShielding`, `GetSkinShielding`, `SetShieldGlowColor`, `GetShieldGlowColor`, `SetShieldGlowDecay`, `GetShieldGlowDecay` are real methods on the class.
- `engine/shields.py` reads via the real getters, not `prop._data`.
- The data-bag tripwire tests at `tests/unit/test_shield_property_skin.py` are rewritten to pin the new interface (preserving coverage, dropping the data-bag-specific assertions that exist purely to detect a future refactor — which this *is*).
- The color consumer tracker continues to record `SetShieldGlowColor` calls when enabled.

## Out of scope

- Promoting other `ShieldProperty` accessors not currently read by the renderer.
- Touching renderer-side data structures or the C++ `shield_pass`.
- Other property classes (e.g. `SensorProperty`, `PhaserProperty`) — they have their own data-bag readers, addressed when those subsystems become hot.

## Surface to add

### `engine/appc/properties.py` — `ShieldProperty`

Extend the class added in the previous spec with three more scalar fields and matching accessors. After this work the class init is:

```python
def __init__(self, name: str = ""):
    super().__init__(name)
    self._max_shields = [0.0] * self.NUM_SHIELDS
    self._charge_per_second = [0.0] * self.NUM_SHIELDS
    self._skin_shielding: int = 0
    self._shield_glow_decay: float = 1.0
    self._shield_glow_color = None      # TGColorA, set on demand
```

Accessors:

- `GetSkinShielding() -> int` — returns `self._skin_shielding`.
- `SetSkinShielding(value: int) -> None` — stores `int(value)`.
- `GetShieldGlowDecay() -> float` — returns `self._shield_glow_decay`.
- `SetShieldGlowDecay(value: float) -> None` — stores `float(value)`.
- `GetShieldGlowColor()` — returns the stored `TGColorA` or `None` if unset. Renderer treats `None` as "default white (1,1,1,1)".
- `SetShieldGlowColor(color: TGColorA) -> None` — stores the color *and* records it to the color-consumer tracker when enabled (preserves the tracker hook that `TGModelProperty.__getattr__` used to provide).

**Defaults justification:**

- `_skin_shielding = 0` matches the existing fallback (`prop._data.get(..., 0)`).
- `_shield_glow_decay = 1.0` matches the existing fallback.
- `_shield_glow_color = None` is the "absent" marker. `engine/shields.py` already handles a non-`TGColorA` value as "use default white"; switching to `is None` is the same semantics with clearer intent. The existing test `test_register_ship_shield_defaults_when_keys_absent` pins this behavior and must keep passing.

### Color tracker preservation

The existing setter shim in [properties.py:24-44](../../../engine/appc/properties.py#L24-L44) records colors to `_color_consumer_tracker` when enabled. The new real `SetShieldGlowColor` must do the same — same recorded name (`"ShieldProperty.SetShieldGlowColor"`), same caller-frame lookup. Inline the existing logic at the bottom of the new method:

```python
def SetShieldGlowColor(self, color):
    self._shield_glow_color = color
    self._data[("ShieldGlowColor", ())] = color    # transition dual-write
    import App as _App
    if _App._color_consumer_tracker.is_enabled():
        import sys as _sys
        frame = _sys._getframe(1)
        _App._color_consumer_tracker.record(
            "ShieldProperty.SetShieldGlowColor", color,
            frame.f_code.co_filename, frame.f_lineno,
        )
```

`_sys._getframe(1)` walks to the direct caller — matches the existing shim's `_getframe(1)` exactly.

### `engine/shields.py` — switch to real getters

After the property side is in place, replace the data-bag reads in `register_ship_shield`:

```python
# before
skin  = prop._data.get(("SkinShielding", ()), 0)
decay = prop._data.get(("ShieldGlowDecay", ()), 1.0)
color = _color_tuple(prop, "ShieldGlowColor")

# after
skin  = prop.GetSkinShielding()
decay = prop.GetShieldGlowDecay()
color = _color_tuple(prop)
```

And update `_color_tuple` to read from `prop.GetShieldGlowColor()` instead of `prop._data.get(("ShieldGlowColor", ()))`:

```python
def _color_tuple(prop, default=(1.0, 1.0, 1.0, 1.0)):
    val = prop.GetShieldGlowColor()
    if isinstance(val, App.TGColorA):
        return (val.r, val.g, val.b, val.a)
    return default
```

The signature loses the `key` parameter — there's only one color attribute, so the indirection bought us nothing.

### Transition dual-write

Mirror Task 5: setters store via the new attribute *and* the data-bag (`self._data[("SkinShielding", ())] = value` etc.). After the renderer is converted and tests rewritten, a final cleanup task drops the dual-write.

## Tests

1. **Defaults.** `GetSkinShielding() == 0`, `GetShieldGlowDecay() == 1.0`, `GetShieldGlowColor() is None` on a freshly-constructed property.
2. **Round-trip.** `Set*/Get*` pairs preserve values.
3. **Type coercion.** `SetSkinShielding("1")` stores `1`, `SetShieldGlowDecay("2.5")` stores `2.5` — matches the `int()/float()` pattern used in the per-face accessors.
4. **Methods are real, not shims.** `"GetSkinShielding" in vars(ShieldProperty)`, `p.GetSkinShielding.__self__ is p`. Same form as the test_shield_property tripwire.
5. **Color tracker preservation.** Enable the tracker, call `SetShieldGlowColor(color)`, verify `_color_consumer_tracker.report()` contains a row with name `"ShieldProperty.SetShieldGlowColor"`.
6. **Renderer integration.** Existing `test_register_ship_shield_reads_skin_flag_and_color` and `test_register_ship_shield_defaults_when_keys_absent` keep passing — these assert end-to-end semantics through the renderer glue.
7. **Sovereign hardpoint.** Existing `test_sovereign_hardpoint_opts_into_skin_shielding` rewritten to assert `sg.GetSkinShielding() == 1`.

## Risks and mitigations

- **`test_shield_property_skin.py` rewrites.** Three of its four tests assert the data-bag storage format directly. They were written as deliberate tripwires for "a future refactor of the data-bag" — this refactor is exactly that case. Rewrite them to test the new interface; coverage is preserved.
- **Color tracker silently breaking.** If the inline tracker hook in `SetShieldGlowColor` drops below the `getattr` shim's frame depth, the tracker records the wrong call site. Mitigation: test 5 asserts a specific caller file/line.
- **Dual-write removal regression.** Same as Task 11: grep for any remaining data-bag reader before removing the dual-write. If a reader exists (e.g. test, renderer, harness), keep the dual-write and document it.
