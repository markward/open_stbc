# Star-Sphere Skybox + Backdrop Layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the no-op single-NIF skybox slot with BC's actual procedural multi-layer backdrop system: an ordered list of `StarSphere` (opaque) and `BackdropSphere` (alpha-blended) layers driven by SDK script calls (`App.StarSphere_Create` / `App.BackdropSphere_Create` / `pSet.AddBackdropToSet`), rendered each frame via a new `BackdropPass` with shared procedural UV-sphere meshes and a per-texture cache.

**Architecture:** Pull-each-tick (mirrors lighting). SDK scripts populate `SetClass._backdrops`. Each tick, `engine/host_loop.run` resolves the active set via `_resolve_active_set` (renamed from `_resolve_active_lighting_set`), aggregates backdrops into a flat list of dicts via `engine.appc.backdrops.aggregate_for_renderer`, and pushes through `r.set_backdrops(...)`. The C++ binding stores the list in `g_backdrops`; the new `BackdropPass` (owning a sphere mesh cache + texture cache) renders them before the opaque pass with view-matrix translation stripped, depth-write off, depth-LEQUAL, front-face culling reversed.

**Tech Stack:** Python 3.12 (Phase-1 engine + tests), C++20 (renderer + bindings), pybind11, GLSL 330, GLM, glad/GLFW. Spec: [docs/superpowers/specs/2026-05-10-skybox-backdrops-design.md](../specs/2026-05-10-skybox-backdrops-design.md).

---

## File map

**Created:**
- `engine/appc/backdrops.py` — `Backdrop`, `StarSphere`, `BackdropSphere`, `*_Create` factories, `aggregate_for_renderer`
- `tests/unit/test_appc_backdrops.py`
- `tests/unit/test_aggregate_backdrops.py`
- `tests/host/test_backdrops_bindings.py`
- `tests/host/test_backdrops_integration.py`
- `native/src/renderer/shaders/backdrop.vert`
- `native/src/renderer/shaders/backdrop.frag`
- `native/src/renderer/include/renderer/backdrop_pass.h`
- `native/src/renderer/backdrop_pass.cc`
- `native/src/renderer/sphere_mesh.h` — UV-sphere `MeshCpu` generator
- `native/src/renderer/sphere_mesh.cc`
- `native/tests/renderer/backdrop_pass_test.cc`

**Modified:**
- `engine/appc/sets.py` — `_backdrops` storage + `AddBackdropToSet`
- `App.py` — backdrop exports
- `engine/renderer.py` — drop `set_skybox`, add `set_backdrops`
- `engine/host_loop.py` — rename helper, add `_aggregate_backdrops`, `run()` integration, drop `DEFAULT_SKYBOX_NIF` + boot-time skybox load
- `native/src/renderer/include/renderer/frame.h` — drop `submit_skybox`, add `Backdrop` struct + `BackdropKind`
- `native/src/renderer/frame.cc` — drop `submit_skybox` body
- `native/src/renderer/include/renderer/pipeline.h` — replace `skybox_shader()` with `backdrop_shader()`
- `native/src/renderer/pipeline.cc` — same
- `native/src/renderer/CMakeLists.txt` — replace skybox shader embed with backdrop shader embed; add new `backdrop_pass.cc`, `sphere_mesh.cc`
- `native/src/scenegraph/include/scenegraph/world.h` — drop `skybox_model_` slot + accessors
- `native/src/host/host_bindings.cc` — drop `set_skybox`, add `set_backdrops`; add `g_backdrops` and `g_backdrop_pass`; replace `submit_skybox` call in `frame()` with `g_backdrop_pass.render(...)`
- `tests/host/test_scene_setup.py` — migrate `test_set_skybox_does_not_crash_in_frame` to backdrops
- `tests/host/test_scene_bindings.py` — migrate `test_set_skybox_does_not_raise` to backdrops
- `tests/unit/test_set.py` — `_backdrops` storage tests
- `native/src/host/docs/deferred_work.md` — mark item #1 implemented; add follow-ups
- `docs/superpowers/specs/2026-05-09-renderer-host-design.md` — same
- `docs/architecture/sub_project_status.md` — record completion

**Removed:**
- `native/src/renderer/shaders/skybox.vert`
- `native/src/renderer/shaders/skybox.frag`
- `native/tests/renderer/skybox_test.cc`
- `tools/pick_default_skybox.py`

---

## Task 1: Phase-1 `Backdrop` class hierarchy + factories

**Files:**
- Create: `engine/appc/backdrops.py`
- Test: `tests/unit/test_appc_backdrops.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_appc_backdrops.py`:

```python
"""Phase-1 backdrop shim: StarSphere / BackdropSphere materialisation."""
import pytest


def test_star_sphere_create_returns_star_kind():
    import App
    from engine.appc.backdrops import StarSphere, Backdrop
    s = App.StarSphere_Create()
    assert isinstance(s, StarSphere)
    assert s._kind == Backdrop.KIND_STAR


def test_backdrop_sphere_create_returns_backdrop_kind():
    import App
    from engine.appc.backdrops import BackdropSphere, Backdrop
    b = App.BackdropSphere_Create()
    assert isinstance(b, BackdropSphere)
    assert b._kind == Backdrop.KIND_BACKDROP


def test_backdrop_setters_round_trip():
    import App
    s = App.StarSphere_Create()
    s.SetTextureFileName("data/stars.tga")
    s.SetTargetPolyCount(512)
    s.SetHorizontalSpan(0.75)
    s.SetVerticalSpan(0.5)
    s.SetSphereRadius(420.0)
    s.SetTextureHTile(22.0)
    s.SetTextureVTile(11.0)
    assert s._texture_path == "data/stars.tga"
    assert s._target_poly_count == 512
    assert s._horizontal_span == 0.75
    assert s._vertical_span == 0.5
    assert s._sphere_radius == 420.0
    assert s._texture_h_tile == 22.0
    assert s._texture_v_tile == 11.0


def test_backdrop_defaults_match_bc_stock_pattern():
    import App
    s = App.StarSphere_Create()
    # Stock BC StarSphere defaults before any setter calls — derived from
    # the pattern in Systems/Biranu/Biranu1.LoadBackdrops.
    assert s._target_poly_count == 256
    assert s._horizontal_span == 1.0
    assert s._vertical_span == 1.0
    assert s._sphere_radius == 300.0
    assert s._texture_h_tile == 1.0
    assert s._texture_v_tile == 1.0
    assert s._texture_path == ""


def test_rebuild_is_noop():
    import App
    s = App.StarSphere_Create()
    assert s.Rebuild() is None


def test_backdrop_inherits_object_class_align_to_vectors():
    """Backdrop inherits ObjectClass so AlignToVectors works — required
    for the per-backdrop world rotation honored by the renderer."""
    import App
    from engine.appc.math import TGPoint3
    s = App.StarSphere_Create()
    fwd = TGPoint3(); fwd.SetXYZ(0.0, 1.0, 0.0)
    up  = TGPoint3(); up.SetXYZ(0.0, 0.0, 1.0)
    s.AlignToVectors(fwd, up)
    rot = s.GetWorldRotation()
    # Row 1 = forward axis post-AlignToVectors.
    assert rot.GetRow(1).y == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_appc_backdrops.py -v`
Expected: All 6 FAIL with `ImportError: cannot import name 'StarSphere'` (the module does not exist) or `AttributeError: module 'App' has no attribute 'StarSphere_Create'`.

- [ ] **Step 3: Create `engine/appc/backdrops.py`**

```python
"""Phase-1 backdrop objects: StarSphere + BackdropSphere.

BC scripts call:
    kThis = App.StarSphere_Create()           # opaque starfield
    kThis = App.BackdropSphere_Create()       # alpha-blended overlay

    kThis.SetName(name)
    kThis.SetTranslateXYZ(0, 0, 0)            # always origin; ignored
    kThis.AlignToVectors(forward, up)         # world orientation
    kThis.SetTextureFileName("data/stars.tga")
    kThis.SetTargetPolyCount(256)
    kThis.SetHorizontalSpan(1.0)
    kThis.SetVerticalSpan(1.0)
    kThis.SetSphereRadius(300.0)
    kThis.SetTextureHTile(22.0)
    kThis.SetTextureVTile(11.0)
    kThis.Rebuild()                           # no-op; we evaluate at submit
    pSet.AddBackdropToSet(kThis, name)        # append-order = draw-order
    kThis.Update(0)

The renderer reads stored config via aggregate_for_renderer at the end
of this module and passes a flat list to the C++ side each tick.
"""
from engine.appc.objects import ObjectClass


class Backdrop(ObjectClass):
    """Common storage. Subclasses differ only in their `kind`
    discriminator; the rendering blend mode is selected from kind.

    Inherits ObjectClass so SetTranslateXYZ / AlignToVectors /
    GetWorldRotation come for free, matching how Light / LightPlacement
    inherit from ObjectClass.
    """
    KIND_STAR = "star"
    KIND_BACKDROP = "backdrop"

    def __init__(self, kind):
        super().__init__()
        self._kind = kind
        self._texture_path: str = ""
        self._target_poly_count: int = 256
        self._horizontal_span: float = 1.0
        self._vertical_span: float = 1.0
        self._sphere_radius: float = 300.0
        self._texture_h_tile: float = 1.0
        self._texture_v_tile: float = 1.0

    def SetTextureFileName(self, path):  self._texture_path = str(path)
    def SetTargetPolyCount(self, n):     self._target_poly_count = int(n)
    def SetHorizontalSpan(self, h):      self._horizontal_span = float(h)
    def SetVerticalSpan(self, v):        self._vertical_span = float(v)
    def SetSphereRadius(self, r):        self._sphere_radius = float(r)
    def SetTextureHTile(self, h):        self._texture_h_tile = float(h)
    def SetTextureVTile(self, v):        self._texture_v_tile = float(v)

    def Rebuild(self):
        # In real BC this regenerates the sphere mesh with the configured
        # poly count and UV mapping. We defer all geometry to the
        # renderer (cached & shared per-poly_count across all backdrops),
        # so this is a no-op. Listed explicitly rather than caught by
        # ObjectClass.__getattr__ so the name shows up in code search.
        return None


class StarSphere(Backdrop):
    def __init__(self):
        super().__init__(Backdrop.KIND_STAR)


class BackdropSphere(Backdrop):
    def __init__(self):
        super().__init__(Backdrop.KIND_BACKDROP)


def StarSphere_Create() -> StarSphere:
    return StarSphere()


def BackdropSphere_Create() -> BackdropSphere:
    return BackdropSphere()
```

- [ ] **Step 4: Tests can't fully pass yet — `App.StarSphere_Create` is still a `_NamedStub`. Tasks 2/3 finish the wiring. Run anyway to confirm partial progress:**

Run: `uv run pytest tests/unit/test_appc_backdrops.py::test_rebuild_is_noop tests/unit/test_appc_backdrops.py::test_backdrop_setters_round_trip -v`
Expected: 2 of 6 pass — these tests would only need the class definition once the App.py export lands. Run after Task 3 to confirm.

Actually, all 6 tests reference `App.StarSphere_Create()` which will return a `_NamedStub` until Task 3. Move on; revisit at end of Task 3.

- [ ] **Step 5: Commit**

```bash
git add engine/appc/backdrops.py tests/unit/test_appc_backdrops.py
git commit -m "feat(appc): Backdrop / StarSphere / BackdropSphere Phase-1 classes"
```

---

## Task 2: SetClass `_backdrops` + `AddBackdropToSet`

**Files:**
- Modify: `engine/appc/sets.py`
- Test: `tests/unit/test_set.py` (extend)

- [ ] **Step 1: Write failing tests in `tests/unit/test_set.py`**

Append to `tests/unit/test_set.py`:

```python
def test_set_backdrops_initially_empty():
    import App
    pSet = App.SetClass_Create()
    assert pSet._backdrops == []


def test_add_backdrop_to_set_appends_in_order():
    import App
    pSet = App.SetClass_Create()
    star = App.StarSphere_Create()
    cloud1 = App.BackdropSphere_Create()
    cloud2 = App.BackdropSphere_Create()
    pSet.AddBackdropToSet(star, "stars")
    pSet.AddBackdropToSet(cloud1, "nebula1")
    pSet.AddBackdropToSet(cloud2, "nebula2")
    assert pSet._backdrops == [star, cloud1, cloud2]


def test_add_backdrop_assigns_name_to_object():
    import App
    pSet = App.SetClass_Create()
    star = App.StarSphere_Create()
    pSet.AddBackdropToSet(star, "Backdrop stars")
    assert star.GetName() == "Backdrop stars"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_set.py::test_set_backdrops_initially_empty tests/unit/test_set.py::test_add_backdrop_to_set_appends_in_order tests/unit/test_set.py::test_add_backdrop_assigns_name_to_object -v`
Expected: all 3 FAIL — `_backdrops` doesn't exist or `AddBackdropToSet` falls through to `_RendererStub` which returns a stub instead of mutating state.

- [ ] **Step 3: Modify `engine/appc/sets.py`**

In `SetClass.__init__`, add the new field next to `_lights`:

```python
        self._lights: 'list["Light"]' = []
        self._lights_by_name: 'dict[str, "Light"]' = {}
        # Backdrops — populated by pSet.AddBackdropToSet(). Ordered list
        # (insertion order = draw order); names aren't indexed because BC
        # scripts only ever pass them positionally to AddBackdropToSet,
        # never look them up later.
        self._backdrops: 'list["Backdrop"]' = []
```

Below the `GetLight` method, add `AddBackdropToSet`:

```python
    # ── Backdrops ──────────────────────────────────────────────────────────
    # SDK signature: pSet.AddBackdropToSet(obj, name).
    # Insertion order is draw order: StarSphere first, nebula overlays
    # alpha-blended on top in registration order.

    def AddBackdropToSet(self, backdrop, name):
        if hasattr(backdrop, "SetName"):
            backdrop.SetName(name)
        self._backdrops.append(backdrop)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_set.py -v`
Expected: All PASS, including the 3 new ones and existing ones (no regression).

- [ ] **Step 5: Commit**

```bash
git add engine/appc/sets.py tests/unit/test_set.py
git commit -m "feat(appc): SetClass owns _backdrops + AddBackdropToSet"
```

---

## Task 3: Export backdrop factories from `App.py`

**Files:**
- Modify: `App.py`

- [ ] **Step 1: Verify pre-task — `App.StarSphere_Create` is still a stub**

Run: `uv run python -c "import App; print(type(App.StarSphere_Create).__name__)"`
Expected: `_NamedStub`

- [ ] **Step 2: Add the import to `App.py`**

In `App.py`, after the existing `from engine.appc.lights import (...)` block:

```python
from engine.appc.backdrops import (
    Backdrop, StarSphere, BackdropSphere,
    StarSphere_Create, BackdropSphere_Create,
)
```

- [ ] **Step 3: Verify the export and re-run Task 1 + Task 2 tests**

Run: `uv run python -c "import App; print(type(App.StarSphere_Create).__name__)"`
Expected: `function`

Run: `uv run pytest tests/unit/test_appc_backdrops.py tests/unit/test_set.py -v`
Expected: all PASS (Task 1's 6 tests now exercise the real factories; Task 2's 3 tests still pass).

- [ ] **Step 4: Commit**

```bash
git add App.py
git commit -m "feat(appc): export Backdrop/StarSphere/BackdropSphere from App.py"
```

---

## Task 4: `aggregate_for_renderer` in backdrops.py + tests

**Files:**
- Modify: `engine/appc/backdrops.py`
- Create: `tests/unit/test_aggregate_backdrops.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_aggregate_backdrops.py`:

```python
"""Tests for engine.appc.backdrops.aggregate_for_renderer."""
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent.parent
GAME_DATA = PROJECT_ROOT / "game" / "data"


def test_aggregate_returns_empty_for_none():
    from engine.appc.backdrops import aggregate_for_renderer
    assert aggregate_for_renderer(None, PROJECT_ROOT) == []


def test_aggregate_returns_empty_for_set_with_no_backdrops():
    import App
    from engine.appc.backdrops import aggregate_for_renderer
    pSet = App.SetClass_Create()
    assert aggregate_for_renderer(pSet, PROJECT_ROOT) == []


def test_aggregate_resolves_texture_path_against_game_dir():
    """data/stars.tga must resolve to project_root/game/data/stars.tga."""
    if not (GAME_DATA / "stars.tga").is_file():
        pytest.skip("BC assets not available")
    import App
    from engine.appc.backdrops import aggregate_for_renderer
    pSet = App.SetClass_Create()
    s = App.StarSphere_Create()
    s.SetTextureFileName("data/stars.tga")
    pSet.AddBackdropToSet(s, "stars")

    result = aggregate_for_renderer(pSet, PROJECT_ROOT)
    assert len(result) == 1
    expected_abs = str((GAME_DATA / "stars.tga").resolve())
    assert result[0]["texture_path"] == expected_abs


def test_aggregate_preserves_draw_order():
    if not (GAME_DATA / "stars.tga").is_file():
        pytest.skip("BC assets not available")
    import App
    from engine.appc.backdrops import aggregate_for_renderer
    pSet = App.SetClass_Create()
    star = App.StarSphere_Create();         star.SetTextureFileName("data/stars.tga")
    cloud1 = App.BackdropSphere_Create();   cloud1.SetTextureFileName("data/stars.tga")
    cloud2 = App.BackdropSphere_Create();   cloud2.SetTextureFileName("data/stars.tga")
    pSet.AddBackdropToSet(star, "stars")
    pSet.AddBackdropToSet(cloud1, "n1")
    pSet.AddBackdropToSet(cloud2, "n2")

    result = aggregate_for_renderer(pSet, PROJECT_ROOT)
    assert [r["kind"] for r in result] == ["star", "backdrop", "backdrop"]


def test_aggregate_extracts_world_rotation_from_align_to_vectors():
    if not (GAME_DATA / "stars.tga").is_file():
        pytest.skip("BC assets not available")
    import App
    from engine.appc.backdrops import aggregate_for_renderer
    from engine.appc.math import TGPoint3

    pSet = App.SetClass_Create()
    s = App.StarSphere_Create()
    s.SetTextureFileName("data/stars.tga")
    fwd = TGPoint3(); fwd.SetXYZ(0.185766, 0.947862, -0.258938)
    up  = TGPoint3(); up.SetXYZ(0.049825, 0.254099, 0.965894)
    s.AlignToVectors(fwd, up)
    pSet.AddBackdropToSet(s, "stars")

    result = aggregate_for_renderer(pSet, PROJECT_ROOT)
    m9 = result[0]["world_rotation"]
    assert len(m9) == 9
    # Row 1 (forward axis) must equal the AlignToVectors-normalized fwd.
    # AlignToVectors normalises; (0.186, 0.948, -0.259) is already
    # near-unit-length so we can compare directly with tolerance.
    assert m9[3] == pytest.approx(0.185766, abs=1e-4)
    assert m9[4] == pytest.approx(0.947862, abs=1e-4)
    assert m9[5] == pytest.approx(-0.258938, abs=1e-4)


def test_aggregate_drops_backdrops_with_unresolvable_texture(capsys):
    import App
    from engine.appc.backdrops import aggregate_for_renderer
    pSet = App.SetClass_Create()
    pSet.SetName("MissingTextureSet")
    s = App.StarSphere_Create()
    s.SetTextureFileName("data/does_not_exist.tga")
    pSet.AddBackdropToSet(s, "stars")

    result = aggregate_for_renderer(pSet, PROJECT_ROOT)
    assert result == []
    out = capsys.readouterr().out
    assert "MissingTextureSet" in out
    assert "data/does_not_exist.tga" in out


def test_aggregate_unresolvable_warning_fires_once_per_set(capsys):
    import App
    from engine.appc.backdrops import aggregate_for_renderer
    pSet = App.SetClass_Create()
    pSet.SetName("RepeatSet")
    s = App.StarSphere_Create()
    s.SetTextureFileName("data/missing.tga")
    pSet.AddBackdropToSet(s, "stars")

    aggregate_for_renderer(pSet, PROJECT_ROOT)
    capsys.readouterr()  # drain first warning
    aggregate_for_renderer(pSet, PROJECT_ROOT)
    assert capsys.readouterr().out == ""


def test_aggregate_drops_empty_texture_path_silently(capsys):
    import App
    from engine.appc.backdrops import aggregate_for_renderer
    pSet = App.SetClass_Create()
    s = App.StarSphere_Create()
    # No SetTextureFileName called.
    pSet.AddBackdropToSet(s, "stars")

    result = aggregate_for_renderer(pSet, PROJECT_ROOT)
    assert result == []
    assert capsys.readouterr().out == ""


def test_aggregate_snaps_target_poly_count_to_minimum():
    if not (GAME_DATA / "stars.tga").is_file():
        pytest.skip("BC assets not available")
    import App
    from engine.appc.backdrops import aggregate_for_renderer
    pSet = App.SetClass_Create()
    s = App.StarSphere_Create()
    s.SetTextureFileName("data/stars.tga")
    s.SetTargetPolyCount(0)
    pSet.AddBackdropToSet(s, "stars")
    result = aggregate_for_renderer(pSet, PROJECT_ROOT)
    assert result[0]["target_poly_count"] == 64


def test_aggregate_passes_through_tile_and_span():
    if not (GAME_DATA / "stars.tga").is_file():
        pytest.skip("BC assets not available")
    import App
    from engine.appc.backdrops import aggregate_for_renderer
    pSet = App.SetClass_Create()
    s = App.StarSphere_Create()
    s.SetTextureFileName("data/stars.tga")
    s.SetTextureHTile(22.0)
    s.SetTextureVTile(11.0)
    s.SetHorizontalSpan(0.3025)
    s.SetVerticalSpan(0.605)
    pSet.AddBackdropToSet(s, "stars")
    result = aggregate_for_renderer(pSet, PROJECT_ROOT)
    assert result[0]["h_tile"] == 22.0
    assert result[0]["v_tile"] == 11.0
    assert result[0]["h_span"] == 0.3025
    assert result[0]["v_span"] == 0.605
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_aggregate_backdrops.py -v`
Expected: All 10 FAIL with `ImportError: cannot import name 'aggregate_for_renderer'`.

- [ ] **Step 3: Add `aggregate_for_renderer` to `engine/appc/backdrops.py`**

Append to `engine/appc/backdrops.py`:

```python
def aggregate_for_renderer(pSet, project_root):
    """Project SetClass._backdrops into a flat list of dicts that the
    C++ side can consume verbatim.

    Each entry has shape:
        {
            "texture_path": str (absolute),
            "kind": "star" | "backdrop",
            "h_tile": float,   "v_tile": float,
            "h_span": float,   "v_span": float,
            "world_rotation": list[9] (column-major flatten of mat3),
            "target_poly_count": int (>= 64),
        }

    Backdrops with empty texture paths are dropped silently (script
    bug we can't fix from here). Backdrops whose texture file does not
    exist under project_root/game/ are dropped with a once-per-set
    warning (pSet._backdrop_warned flag) — same gate pattern as the
    lighting overflow warning.
    """
    if pSet is None or not getattr(pSet, "_backdrops", None):
        return []

    out = []
    missing_paths = []
    for b in pSet._backdrops:
        if not b._texture_path:
            continue  # silent: script-author bug
        abs_path = (project_root / "game" / b._texture_path).resolve()
        if not abs_path.is_file():
            missing_paths.append(b._texture_path)
            continue
        rot = b.GetWorldRotation()
        m9 = [
            rot._m[0][0], rot._m[0][1], rot._m[0][2],
            rot._m[1][0], rot._m[1][1], rot._m[1][2],
            rot._m[2][0], rot._m[2][1], rot._m[2][2],
        ]
        out.append({
            "texture_path": str(abs_path),
            "kind": b._kind,
            "h_tile": b._texture_h_tile,
            "v_tile": b._texture_v_tile,
            "h_span": b._horizontal_span,
            "v_span": b._vertical_span,
            "world_rotation": m9,
            "target_poly_count": max(int(b._target_poly_count), 64),
        })

    if missing_paths and not getattr(pSet, "_backdrop_warned", False):
        print(f"[backdrops] dropped {len(missing_paths)} backdrop(s) "
              f"with unresolvable textures from set "
              f"{pSet.GetName()!r}: {missing_paths!r}", flush=True)
        pSet._backdrop_warned = True

    return out
```

**Note on NaN / zero-rotation guards:** the spec mentions filtering
backdrops whose `GetWorldRotation()` returns a NaN or all-zero matrix.
That case is intentionally not guarded in v1 — it requires a buggy
script (zero-length forward to `AlignToVectors`) and the GL uniform
setter would surface NaN as a visual artifact, not a crash. If this
ever appears in the wild, add the check here and a once-per-set warning;
no test covers it now.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_aggregate_backdrops.py -v`
Expected: All 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/appc/backdrops.py tests/unit/test_aggregate_backdrops.py
git commit -m "feat(appc): aggregate_for_renderer for backdrops"
```

---

## Task 5: `_resolve_active_set` rename + `_aggregate_backdrops` wrapper

**Files:**
- Modify: `engine/host_loop.py`
- Test: `tests/host/test_host_loop_lighting.py` (existing tests must still pass)

- [ ] **Step 1: Write failing tests for the new helper**

Append to `tests/host/test_host_loop_lighting.py`:

```python
def test_resolve_active_set_picks_set_with_only_backdrops():
    """_resolve_active_set considers backdrops alongside lights when
    deciding whether a set is 'live'."""
    import App
    from engine import host_loop
    App.g_kSetManager._rendered_set_name = None
    pSet = App.SetClass_Create()
    star = App.StarSphere_Create()
    star.SetTextureFileName("data/stars.tga")
    pSet.AddBackdropToSet(star, "stars")
    App.g_kSetManager.AddSet(pSet, "BackdropOnlySet")
    class _FakePlayer: pass
    fp = _FakePlayer()
    pSet.AddObjectToSet(fp, "player")
    try:
        active = host_loop._resolve_active_set(player=fp)
        assert active is pSet
    finally:
        App.g_kSetManager.DeleteSet("BackdropOnlySet")


def test_aggregate_backdrops_supplies_project_root_for_path_resolution():
    """The host_loop wrapper passes PROJECT_ROOT so 'data/stars.tga'
    resolves correctly without each call site juggling the root path."""
    from pathlib import Path
    import App
    from engine import host_loop
    PROJECT_ROOT = host_loop.PROJECT_ROOT
    if not (PROJECT_ROOT / "game" / "data" / "stars.tga").is_file():
        import pytest as _pt
        _pt.skip("BC assets not available")
    pSet = App.SetClass_Create()
    s = App.StarSphere_Create()
    s.SetTextureFileName("data/stars.tga")
    pSet.AddBackdropToSet(s, "stars")
    result = host_loop._aggregate_backdrops(pSet)
    assert len(result) == 1
    assert result[0]["kind"] == "star"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/test_host_loop_lighting.py::test_resolve_active_set_picks_set_with_only_backdrops tests/host/test_host_loop_lighting.py::test_aggregate_backdrops_supplies_project_root_for_path_resolution -v`
Expected: FAIL with `AttributeError: module 'engine.host_loop' has no attribute '_resolve_active_set'` and `_aggregate_backdrops`.

- [ ] **Step 3: Add the rename + wrapper to `engine/host_loop.py`**

Replace `_resolve_active_lighting_set` with the renamed `_resolve_active_set` (broadened to consider backdrops) and keep a thin alias for back-compat with existing lighting tests. Find the existing function:

```python
def _resolve_active_lighting_set(player):
    """Return the SetClass whose lights apply to the rendered scene.

    Order:
      1. g_kSetManager.GetRenderedSet() — set explicitly via
         MissionLib.MakeRenderedSet during scene transitions. Used when
         present and has lights.
      2. The set containing the player ship — fallback for when Phase 1
         hasn't wired MakeRenderedSet up. Used when has lights.
      3. None — caller falls through to DEFAULT_AMBIENT / DEFAULT_DIRECTIONALS.
    """
    import App
    rendered = App.g_kSetManager.GetRenderedSet()
    if rendered is not None and getattr(rendered, "_lights", None):
        return rendered
    if player is not None:
        for s in App.g_kSetManager._sets.values():
            if any(o is player for o in getattr(s, "_objects", {}).values()):
                if getattr(s, "_lights", None):
                    return s
    return None
```

Replace it with:

```python
def _resolve_active_set(player):
    """Return the SetClass whose lights & backdrops apply to the rendered
    scene. Order:
      1. g_kSetManager.GetRenderedSet() — set explicitly via
         MissionLib.MakeRenderedSet during scene transitions.
      2. The set containing the player ship — Phase 1 fallback.
      3. None — caller falls through to per-system defaults
         (lighting only; backdrops simply absent).

    Considers both _lights and _backdrops when deciding whether a set
    is 'live' so backdrop-only sets (rare but legal) are picked up.
    """
    import App
    rendered = App.g_kSetManager.GetRenderedSet()
    if rendered is not None and (
        getattr(rendered, "_lights", None) or
        getattr(rendered, "_backdrops", None)
    ):
        return rendered
    if player is not None:
        for s in App.g_kSetManager._sets.values():
            if any(o is player for o in getattr(s, "_objects", {}).values()):
                if (getattr(s, "_lights", None) or
                    getattr(s, "_backdrops", None)):
                    return s
    return None


# Back-compat alias — existing lighting tests reference this name.
_resolve_active_lighting_set = _resolve_active_set
```

After the existing `_aggregate_lights` function, add:

```python
def _aggregate_backdrops(pSet):
    """Thin wrapper over engine.appc.backdrops.aggregate_for_renderer
    that supplies PROJECT_ROOT, mirroring _aggregate_lights's wrapping
    of aggregate_for_renderer in lights.py."""
    from engine.appc.backdrops import aggregate_for_renderer
    return aggregate_for_renderer(pSet, PROJECT_ROOT)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/test_host_loop_lighting.py -v`
Expected: All PASS — the 2 new tests now find the symbols, and the existing 17 lighting tests still pass via the back-compat alias.

- [ ] **Step 5: Commit**

```bash
git add engine/host_loop.py tests/host/test_host_loop_lighting.py
git commit -m "refactor(host): _resolve_active_set considers backdrops too"
```

---

## Task 6: New `backdrop.{vert,frag}` shaders + CMake embedding

**Files:**
- Create: `native/src/renderer/shaders/backdrop.vert`
- Create: `native/src/renderer/shaders/backdrop.frag`
- Modify: `native/src/renderer/CMakeLists.txt`

This task only adds new shader files. Pipeline doesn't reference them yet (that's Task 8). No tests yet; the shader compiles when Pipeline is updated.

- [ ] **Step 1: Create `native/src/renderer/shaders/backdrop.vert`**

```glsl
#version 330 core

layout(location=0) in vec3 a_pos;
layout(location=1) in vec3 a_normal;     // unused; binding compatibility with assets::Mesh VAO layout
layout(location=2) in vec2 a_uv;

uniform mat4 u_view_no_translation;
uniform mat4 u_proj;
uniform mat3 u_world_rotation;

out vec3 v_pos_local;
out vec2 v_uv;

void main() {
    vec3 rotated = u_world_rotation * a_pos;
    v_pos_local = rotated;
    v_uv = a_uv;
    vec4 clip = u_proj * u_view_no_translation * vec4(rotated, 1.0);
    // Skybox-depth idiom: force fragment to the far plane so any
    // subsequently-drawn opaque geometry always wins LEQUAL depth tests.
    clip.z = clip.w;
    gl_Position = clip;
}
```

- [ ] **Step 2: Create `native/src/renderer/shaders/backdrop.frag`**

```glsl
#version 330 core

in vec3 v_pos_local;
in vec2 v_uv;

uniform sampler2D u_texture;
uniform vec2  u_tile;
uniform vec2  u_span;
uniform int   u_use_alpha;   // 0 = opaque (Star), 1 = blended (Backdrop)

out vec4 frag_color;

void main() {
    if (v_uv.x > u_span.x || v_uv.y > u_span.y) {
        if (u_use_alpha == 1) discard;
    }
    vec2 uv = vec2(v_uv.x * u_tile.x, v_uv.y * u_tile.y);
    vec4 tex = texture(u_texture, uv);
    if (u_use_alpha == 1) {
        frag_color = vec4(tex.rgb, tex.a);
    } else {
        frag_color = vec4(tex.rgb, 1.0);
    }
}
```

- [ ] **Step 3: Add embed lines to `native/src/renderer/CMakeLists.txt`**

After the existing `embed_shader(SHADER_SKYBOX_FS shaders/skybox.frag skybox_fs)` line, add:

```cmake
embed_shader(SHADER_BACKDROP_VS shaders/backdrop.vert backdrop_vs)
embed_shader(SHADER_BACKDROP_FS shaders/backdrop.frag backdrop_fs)
```

Don't remove the skybox embed yet — Task 13 cuts those over.

- [ ] **Step 4: Build to verify the shader files exist and embed**

Run: `cmake --build build --target renderer -j 8`
Expected: `librenderer.a` builds. The new headers `embedded_backdrop_vs.h` / `embedded_backdrop_fs.h` exist under `build/native/src/renderer/`.

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/shaders/backdrop.vert \
        native/src/renderer/shaders/backdrop.frag \
        native/src/renderer/CMakeLists.txt
git commit -m "feat(renderer): backdrop.{vert,frag} shaders + CMake embed"
```

---

## Task 7: UV-sphere `MeshCpu` generator

**Files:**
- Create: `native/src/renderer/sphere_mesh.h`
- Create: `native/src/renderer/sphere_mesh.cc`
- Modify: `native/src/renderer/CMakeLists.txt`

- [ ] **Step 1: Create the header**

`native/src/renderer/sphere_mesh.h`:

```cpp
// native/src/renderer/sphere_mesh.h
#pragma once

#include <assets/mesh.h>

namespace renderer {

/// Build an inside-facing UV sphere with approximately `target_tris`
/// triangles. The sphere's vertices lie on the unit sphere (radius 1);
/// callers scale via the world matrix or simply rely on the skybox-depth
/// idiom in the vertex shader, which makes radius cosmetic.
///
/// Triangulation: lat × lon segments split 1:2 so target_tris=256
/// produces 8 lat × 16 lon segments = 128 quads = 256 tris.
///
/// Winding: clockwise from outside the sphere. Combined with this
/// project's `glFrontFace(GL_CW)` convention and back-face culling, the
/// sphere's *interior* renders front-facing — which is what we want for
/// a skybox seen from inside.
///
/// UV layout: u = lon / (2π) ∈ [0,1], v = (lat + π/2) / π ∈ [0,1].
/// Texture stretching at the poles is acceptable for BC's stars.tga.
assets::MeshCpu build_uv_sphere(int target_tris);

}  // namespace renderer
```

- [ ] **Step 2: No dedicated test for this task**

The sphere generator is a pure function returning `assets::MeshCpu`. Its
correctness is enforced indirectly via Task 9's `BackdropPass::ensure_sphere`
(which feeds the result into `assets::upload_mesh` — failure to compile or
produce valid index data surfaces immediately) and via Task 14's native
test, which exercises the whole pass with the sphere baked in. Skip
dedicated unit testing for this task.

- [ ] **Step 3: Create `native/src/renderer/sphere_mesh.cc`**

```cpp
// native/src/renderer/sphere_mesh.cc
#include "sphere_mesh.h"

#include <cmath>

namespace renderer {

namespace {

constexpr float kPi = 3.14159265358979323846f;
constexpr float kTwoPi = 2.0f * kPi;

}  // namespace

assets::MeshCpu build_uv_sphere(int target_tris) {
    if (target_tris < 64) target_tris = 64;
    // Split target evenly across (lat × lon) quad grid such that
    // lon = 2 × lat (full azimuth × half elevation, matching a UV-sphere).
    // target_tris ≈ 2 × lat × lon = 2 × lat × (2 × lat) = 4 × lat² .
    int lat_segs = static_cast<int>(std::round(std::sqrt(target_tris / 4.0f)));
    if (lat_segs < 4) lat_segs = 4;
    int lon_segs = lat_segs * 2;

    assets::MeshCpu cpu;
    cpu.vertices.reserve((lat_segs + 1) * (lon_segs + 1));
    cpu.indices.reserve(lat_segs * lon_segs * 6);

    for (int i = 0; i <= lat_segs; ++i) {
        // theta: from -π/2 (south pole) to +π/2 (north pole)
        float v = static_cast<float>(i) / static_cast<float>(lat_segs);
        float theta = -kPi * 0.5f + v * kPi;
        float sin_t = std::sin(theta);
        float cos_t = std::cos(theta);
        for (int j = 0; j <= lon_segs; ++j) {
            float u = static_cast<float>(j) / static_cast<float>(lon_segs);
            float phi = u * kTwoPi;
            float sin_p = std::sin(phi);
            float cos_p = std::cos(phi);
            assets::MeshCpu::Vertex vert;
            vert.position = {cos_t * cos_p, cos_t * sin_p, sin_t};
            vert.normal   = vert.position;
            vert.uv       = {u, v};
            cpu.vertices.push_back(vert);
        }
    }

    // Indices: clockwise winding from OUTSIDE the sphere. Combined with
    // glFrontFace(GL_CW) + glCullFace(GL_FRONT) (we cull front faces in
    // BackdropPass), the inside of the sphere is what's drawn.
    for (int i = 0; i < lat_segs; ++i) {
        for (int j = 0; j < lon_segs; ++j) {
            std::uint32_t a = static_cast<std::uint32_t>( i      * (lon_segs + 1) + j     );
            std::uint32_t b = static_cast<std::uint32_t>( i      * (lon_segs + 1) + j + 1 );
            std::uint32_t c = static_cast<std::uint32_t>((i + 1) * (lon_segs + 1) + j     );
            std::uint32_t d = static_cast<std::uint32_t>((i + 1) * (lon_segs + 1) + j + 1 );
            // Quad (a, b, d, c) → two CW triangles from outside.
            cpu.indices.push_back(a); cpu.indices.push_back(b); cpu.indices.push_back(d);
            cpu.indices.push_back(a); cpu.indices.push_back(d); cpu.indices.push_back(c);
        }
    }

    return cpu;
}

}  // namespace renderer
```

- [ ] **Step 4: Add `sphere_mesh.cc` to `renderer` library in CMakeLists**

In `native/src/renderer/CMakeLists.txt`, find:

```cmake
add_library(renderer STATIC
    window.cc
    shader.cc
    pipeline.cc
    frame.cc
)
```

Add `sphere_mesh.cc`:

```cmake
add_library(renderer STATIC
    window.cc
    shader.cc
    pipeline.cc
    frame.cc
    sphere_mesh.cc
)
```

- [ ] **Step 5: Build to verify**

Run: `cmake --build build --target renderer -j 8`
Expected: builds cleanly.

- [ ] **Step 6: Commit**

```bash
git add native/src/renderer/sphere_mesh.h \
        native/src/renderer/sphere_mesh.cc \
        native/src/renderer/CMakeLists.txt
git commit -m "feat(renderer): inside-facing UV-sphere MeshCpu generator"
```

---

## Task 8: `renderer::Backdrop` struct + `Pipeline::backdrop_shader()`

**Files:**
- Modify: `native/src/renderer/include/renderer/frame.h`
- Modify: `native/src/renderer/include/renderer/pipeline.h`
- Modify: `native/src/renderer/pipeline.cc`

This task adds the data type and the pipeline accessor without yet integrating into `frame()`. The legacy `skybox_shader()` stays in place; both coexist until Task 13.

- [ ] **Step 1: Add `BackdropKind` and `Backdrop` to `frame.h`**

In `native/src/renderer/include/renderer/frame.h`, after the existing `Lighting` struct (around line 30) and before the `FrameSubmitter` class:

```cpp
enum class BackdropKind { Star, Backdrop };

struct Backdrop {
    /// Source descriptor; matched against the renderer's per-texture
    /// cache. The renderer uploads on first sight and reuses thereafter.
    std::string texture_path;
    BackdropKind kind = BackdropKind::Star;
    float h_tile = 1.0f;
    float v_tile = 1.0f;
    float h_span = 1.0f;
    float v_span = 1.0f;
    glm::mat3 world_rotation = glm::mat3(1.0f);
    int target_poly_count = 256;
};
```

Add `#include <string>` at the top of frame.h if it isn't already there.

- [ ] **Step 2: Add `backdrop_shader()` accessor to `pipeline.h`**

Modify `native/src/renderer/include/renderer/pipeline.h`:

```cpp
class Pipeline {
public:
    Pipeline();

    Shader& opaque_shader() noexcept { return *opaque_; }
    Shader& skybox_shader() noexcept { return *skybox_; }     // legacy; removed in Task 13
    Shader& backdrop_shader() noexcept { return *backdrop_; }  // new

private:
    std::unique_ptr<Shader> opaque_;
    std::unique_ptr<Shader> skybox_;
    std::unique_ptr<Shader> backdrop_;
};
```

- [ ] **Step 3: Construct the backdrop shader in `pipeline.cc`**

Modify `native/src/renderer/pipeline.cc`:

```cpp
#include "renderer/pipeline.h"

#include <glad/glad.h>

#include "embedded_opaque_vs.h"
#include "embedded_opaque_fs.h"
#include "embedded_skybox_vs.h"
#include "embedded_skybox_fs.h"
#include "embedded_backdrop_vs.h"
#include "embedded_backdrop_fs.h"

namespace renderer {

Pipeline::Pipeline() {
    opaque_ = std::make_unique<Shader>(shader_src::opaque_vs, shader_src::opaque_fs);
    skybox_ = std::make_unique<Shader>(shader_src::skybox_vs, shader_src::skybox_fs);
    backdrop_ = std::make_unique<Shader>(shader_src::backdrop_vs, shader_src::backdrop_fs);
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LESS);
    glEnable(GL_CULL_FACE);
    glCullFace(GL_BACK);
    glFrontFace(GL_CW);
}

}  // namespace renderer
```

- [ ] **Step 4: Build to verify**

Run: `cmake --build build --target renderer -j 8`
Expected: builds cleanly. The `backdrop_shader()` accessor is callable; no consumer yet.

- [ ] **Step 5: Commit**

```bash
git add native/src/renderer/include/renderer/frame.h \
        native/src/renderer/include/renderer/pipeline.h \
        native/src/renderer/pipeline.cc
git commit -m "feat(renderer): Backdrop struct + Pipeline::backdrop_shader()"
```

---

## Task 9: `BackdropPass` header + implementation

**Files:**
- Create: `native/src/renderer/include/renderer/backdrop_pass.h`
- Create: `native/src/renderer/backdrop_pass.cc`
- Modify: `native/src/renderer/CMakeLists.txt`

- [ ] **Step 1: Create the header**

`native/src/renderer/include/renderer/backdrop_pass.h`:

```cpp
// native/src/renderer/include/renderer/backdrop_pass.h
#pragma once

#include <renderer/frame.h>          // Backdrop, BackdropKind
#include <assets/mesh.h>
#include <assets/texture.h>

#include <filesystem>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace scenegraph { struct Camera; }

namespace renderer {

class Pipeline;

class BackdropPass {
public:
    BackdropPass() = default;
    ~BackdropPass();
    BackdropPass(const BackdropPass&) = delete;
    BackdropPass& operator=(const BackdropPass&) = delete;

    /// Render `backdrops` in order. Caller is responsible for clearing
    /// color + depth before this call. Caller has bound a default
    /// framebuffer.
    void render(const std::vector<Backdrop>& backdrops,
                const scenegraph::Camera& camera,
                Pipeline& pipeline);

private:
    /// Lazy-tessellated UV sphere keyed by target_poly_count. Most BC
    /// systems use 256; cache grows on demand if a script requests
    /// something different.
    std::unordered_map<int, std::unique_ptr<assets::Mesh>> sphere_cache_;

    /// Texture cache keyed by absolute path. Sentinel values (with
    /// id == 0) mark previously-failed loads to suppress per-frame
    /// retries.
    std::unordered_map<std::string, std::unique_ptr<assets::Texture>> texture_cache_;

    assets::Mesh*    ensure_sphere(int target_poly_count);
    assets::Texture* ensure_texture(const std::string& path);
};

}  // namespace renderer
```

- [ ] **Step 2: Create the implementation**

`native/src/renderer/backdrop_pass.cc`:

```cpp
// native/src/renderer/backdrop_pass.cc
#include "renderer/backdrop_pass.h"

#include "renderer/pipeline.h"
#include "sphere_mesh.h"

#include <assets/texture.h>
#include <scenegraph/camera.h>

#include <glad/glad.h>
#include <glm/glm.hpp>

#include <cstdio>
#include <fstream>

// upload_image / decode_tga live in assets::detail. They're not in
// public headers; we re-declare the slim interface we need here.
namespace assets {
    struct Image; // fwd
    Image decode_tga(const std::vector<std::uint8_t>& bytes);
    Texture upload_image(const Image& image, bool generate_mipmaps);
}

namespace renderer {

BackdropPass::~BackdropPass() {
    // assets::Mesh / assets::Texture destructors release GL handles.
    // Caller must ensure GL context is still alive when this dtor runs;
    // host_bindings.cc resets the unique_ptr in shutdown() before
    // destroying the window for exactly that reason.
}

assets::Mesh* BackdropPass::ensure_sphere(int target_poly_count) {
    if (target_poly_count < 64) target_poly_count = 64;
    auto it = sphere_cache_.find(target_poly_count);
    if (it != sphere_cache_.end()) return it->second.get();
    assets::MeshCpu cpu = build_uv_sphere(target_poly_count);
    assets::Mesh m = assets::upload_mesh(cpu);
    auto owned = std::make_unique<assets::Mesh>(std::move(m));
    auto* raw = owned.get();
    sphere_cache_.emplace(target_poly_count, std::move(owned));
    return raw;
}

assets::Texture* BackdropPass::ensure_texture(const std::string& path) {
    auto it = texture_cache_.find(path);
    if (it != texture_cache_.end()) {
        // id() == 0 means a sentinel from a previous failed load.
        return (it->second && it->second->id() != 0) ? it->second.get() : nullptr;
    }
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        std::fprintf(stderr, "[backdrop] failed to open '%s'\n", path.c_str());
        // Insert sentinel so we don't retry on every frame.
        texture_cache_.emplace(path, std::make_unique<assets::Texture>());
        return nullptr;
    }
    in.seekg(0, std::ios::end);
    auto size = static_cast<std::size_t>(in.tellg());
    in.seekg(0, std::ios::beg);
    std::vector<std::uint8_t> bytes(size);
    in.read(reinterpret_cast<char*>(bytes.data()),
            static_cast<std::streamsize>(size));
    try {
        assets::Image img = assets::decode_tga(bytes);
        assets::Texture tex = assets::upload_image(img, /*generate_mipmaps=*/true);
        auto owned = std::make_unique<assets::Texture>(std::move(tex));
        auto* raw = owned.get();
        texture_cache_.emplace(path, std::move(owned));
        return raw;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "[backdrop] failed to decode '%s': %s\n",
                     path.c_str(), e.what());
        texture_cache_.emplace(path, std::make_unique<assets::Texture>());
        return nullptr;
    }
}

void BackdropPass::render(const std::vector<Backdrop>& backdrops,
                          const scenegraph::Camera& camera,
                          Pipeline& pipeline) {
    if (backdrops.empty()) return;

    auto& shader = pipeline.backdrop_shader();
    shader.use();

    // Strip translation from the view matrix: camera-anchored position,
    // world-locked orientation. Standard skybox idiom.
    glm::mat4 view_no_t = glm::mat4(glm::mat3(camera.view_matrix()));
    shader.set_mat4("u_view_no_translation", view_no_t);
    shader.set_mat4("u_proj", camera.proj_matrix());

    glDepthMask(GL_FALSE);
    glDepthFunc(GL_LEQUAL);
    glCullFace(GL_FRONT);  // we render the inside of the sphere

    for (const auto& b : backdrops) {
        assets::Mesh* sphere = ensure_sphere(b.target_poly_count);
        assets::Texture* tex = ensure_texture(b.texture_path);
        if (!sphere || !tex) continue;

        if (b.kind == BackdropKind::Backdrop) {
            glEnable(GL_BLEND);
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
            shader.set_int("u_use_alpha", 1);
        } else {
            glDisable(GL_BLEND);
            shader.set_int("u_use_alpha", 0);
        }

        // Per-backdrop uniforms.
        glm::mat3 rot = b.world_rotation;
        glUniformMatrix3fv(glGetUniformLocation(shader.program(),
                                                "u_world_rotation"),
                           1, GL_FALSE, &rot[0][0]);
        shader.set_vec3("u_tile_dummy", glm::vec3(0));  // touch program loc cache
        glUniform2f(glGetUniformLocation(shader.program(), "u_tile"),
                    b.h_tile, b.v_tile);
        glUniform2f(glGetUniformLocation(shader.program(), "u_span"),
                    b.h_span, b.v_span);

        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, tex->id());
        shader.set_int("u_texture", 0);

        glBindVertexArray(sphere->vao());
        glDrawElements(GL_TRIANGLES,
                       static_cast<GLsizei>(sphere->index_count()),
                       GL_UNSIGNED_INT, nullptr);
    }

    glDisable(GL_BLEND);
    glCullFace(GL_BACK);
    glDepthMask(GL_TRUE);
    glDepthFunc(GL_LESS);
    glBindVertexArray(0);
}

}  // namespace renderer
```

Note: the `shader.set_vec3("u_tile_dummy", ...)` line is a typo — remove it before commit. I left it in the draft as a reminder that the existing `Shader::set_vec3` API takes a string + vec3, but for vec2 we need raw `glUniform2f` since there's no `set_vec2`. (Adding `set_vec2` is a 5-line addition to shader.cc; it's worth doing properly.)

Actually, do that properly:

- [ ] **Step 3: Add `Shader::set_vec2` helper**

In `native/src/renderer/include/renderer/shader.h`, after `set_vec3`:

```cpp
    void set_vec2(const std::string& name, const glm::vec2& v) const;
```

In `native/src/renderer/shader.cc`, after `set_vec3`:

```cpp
void Shader::set_vec2(const std::string& name, const glm::vec2& v) const {
    GLint loc = glGetUniformLocation(program_, name.c_str());
    if (loc >= 0) glUniform2fv(loc, 1, glm::value_ptr(v));
}
```

Also add `set_mat3`:

```cpp
// header
void set_mat3(const std::string& name, const glm::mat3& v) const;

// impl
void Shader::set_mat3(const std::string& name, const glm::mat3& v) const {
    GLint loc = glGetUniformLocation(program_, name.c_str());
    if (loc >= 0) glUniformMatrix3fv(loc, 1, GL_FALSE, glm::value_ptr(v));
}
```

Now back in `backdrop_pass.cc`, replace the raw `glUniform*` calls with the new helpers (and remove the dummy `set_vec3` line):

```cpp
        shader.set_mat3("u_world_rotation", b.world_rotation);
        shader.set_vec2("u_tile", glm::vec2(b.h_tile, b.v_tile));
        shader.set_vec2("u_span", glm::vec2(b.h_span, b.v_span));
```

- [ ] **Step 4: Add `backdrop_pass.cc` to `renderer` CMakeLists**

In `native/src/renderer/CMakeLists.txt`, add to the `renderer` library sources:

```cmake
add_library(renderer STATIC
    window.cc
    shader.cc
    pipeline.cc
    frame.cc
    sphere_mesh.cc
    backdrop_pass.cc
)
```

- [ ] **Step 5: Make `assets::decode_tga` and `assets::upload_image` accessible from renderer**

These are currently in `assets::detail` namespace. Check `native/src/assets/include/assets/texture.h`:

Run: `grep -n "decode_tga\|upload_image" /Users/mward/Documents/Projects/dauntless/native/src/assets/include/assets/texture.h`

If they're not in the public header, they need to be promoted. Look at the existing declaration:

Run: `grep -rn "Texture upload_image\|Image decode_tga" /Users/mward/Documents/Projects/dauntless/native/src/assets/`

Expected output should reveal the namespace and signature. If they're in `assets::detail`, change `backdrop_pass.cc` to use the `assets::detail::` prefix, OR promote the declarations into `assets/texture.h`. Promotion is cleaner — these are already used by `model_build.cc` and the public renderer.

For this task, **promote** the two declarations:

In `native/src/assets/include/assets/texture.h`, add at the bottom of the `assets` namespace:

```cpp
struct Image {
    std::vector<std::uint8_t> pixels;
    int width = 0;
    int height = 0;
    int channels = 0;     // 3 = RGB, 4 = RGBA
};

/// Decode a TGA blob (RGB / RGBA / RLE / paletted variants supported by
/// the BC asset corpus). Throws std::runtime_error on malformed data.
Image decode_tga(const std::vector<std::uint8_t>& bytes);

/// Upload a decoded image as a GL texture; optionally generate mipmaps.
Texture upload_image(const Image& image, bool generate_mipmaps);
```

Add `#include <vector>` and `#include <cstdint>` if not present.

Then in `backdrop_pass.cc`, replace the forward-declarations at the top with:

```cpp
#include <assets/texture.h>  // already included, but clarifies intent
```

(remove the manual `namespace assets { ... }` forward-decl block).

Verify these symbols are still defined where they live in `assets/src/`:

Run: `grep -rn "decode_tga\|upload_image" /Users/mward/Documents/Projects/dauntless/native/src/assets/src/`

If the `.cc` definitions are in an anonymous namespace inside `assets::detail`, move them out into `assets::` to match the new public header. This may be a multi-line edit in `texture_decode.cc` and `texture_upload.cc`.

If the existing public declarations already match the new header, skip the promotion edit and just include the existing header.

- [ ] **Step 6: Build to verify**

Run: `cmake --build build --target renderer -j 8`
Expected: builds cleanly. `librenderer.a` now includes `backdrop_pass.cc`.

- [ ] **Step 7: Commit**

```bash
git add native/src/renderer/include/renderer/backdrop_pass.h \
        native/src/renderer/backdrop_pass.cc \
        native/src/renderer/include/renderer/shader.h \
        native/src/renderer/shader.cc \
        native/src/renderer/CMakeLists.txt \
        native/src/assets/include/assets/texture.h
# Plus any assets/src/ files modified to promote decode_tga / upload_image symbols.
git commit -m "feat(renderer): BackdropPass with sphere + texture caches"
```

---

## Task 10: `set_backdrops` binding + `g_backdrops` + `g_backdrop_pass`

**Files:**
- Modify: `native/src/host/host_bindings.cc`
- Test: `tests/host/test_backdrops_bindings.py` (new)

This task adds the new binding alongside the existing `set_skybox` (still functional). The `frame()` `submit_skybox` call also stays. Cut-over happens in Task 13.

- [ ] **Step 1: Write the failing binding test**

Create `tests/host/test_backdrops_bindings.py`:

```python
"""Tests for the _open_stbc_host.set_backdrops binding."""
import os


def test_set_backdrops_empty_list_does_not_raise():
    import _open_stbc_host
    _open_stbc_host.set_backdrops([])


def test_set_backdrops_single_star_descriptor_does_not_raise():
    import _open_stbc_host
    _open_stbc_host.set_backdrops([{
        "texture_path": "/dev/null",  # no init() yet → texture load deferred
        "kind": "star",
        "h_tile": 22.0, "v_tile": 11.0,
        "h_span": 1.0, "v_span": 1.0,
        "world_rotation": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "target_poly_count": 256,
    }])


def test_set_backdrops_many_descriptors_does_not_raise():
    import _open_stbc_host
    descriptor = {
        "texture_path": "/dev/null",
        "kind": "backdrop",
        "h_tile": 1.0, "v_tile": 1.0,
        "h_span": 1.0, "v_span": 1.0,
        "world_rotation": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "target_poly_count": 256,
    }
    _open_stbc_host.set_backdrops([descriptor] * 10)
```

- [ ] **Step 2: Run to verify failure**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/test_backdrops_bindings.py -v`
Expected: FAIL with `AttributeError: module '_open_stbc_host' has no attribute 'set_backdrops'`.

- [ ] **Step 3: Modify `host_bindings.cc`**

At the top of the anonymous namespace (after `g_lighting`), add:

```cpp
std::vector<renderer::Backdrop> g_backdrops;
std::unique_ptr<renderer::BackdropPass> g_backdrop_pass;
```

Add `#include <renderer/backdrop_pass.h>` to the existing includes block.

In `init()`, after `g_lighting = renderer::Lighting{};`:

```cpp
    g_backdrops.clear();
    g_backdrop_pass = std::make_unique<renderer::BackdropPass>();
```

In `shutdown()`, before `g_window.reset()`:

```cpp
    g_backdrops.clear();
    g_backdrop_pass.reset();
```

In `PYBIND11_MODULE`, after the `m.def("set_lighting", ...)` block, add:

```cpp
    m.def("set_backdrops",
          [](const std::vector<py::dict>& descriptors) {
              g_backdrops.clear();
              g_backdrops.reserve(descriptors.size());
              for (const auto& d : descriptors) {
                  renderer::Backdrop b;
                  b.texture_path      = d["texture_path"].cast<std::string>();
                  std::string kind    = d["kind"].cast<std::string>();
                  b.kind = (kind == "star") ? renderer::BackdropKind::Star
                                            : renderer::BackdropKind::Backdrop;
                  b.h_tile            = d["h_tile"].cast<float>();
                  b.v_tile            = d["v_tile"].cast<float>();
                  b.h_span            = d["h_span"].cast<float>();
                  b.v_span            = d["v_span"].cast<float>();
                  b.target_poly_count = d["target_poly_count"].cast<int>();
                  auto m9 = d["world_rotation"].cast<std::vector<float>>();
                  if (m9.size() == 9) {
                      b.world_rotation = glm::mat3(
                          m9[0], m9[1], m9[2],
                          m9[3], m9[4], m9[5],
                          m9[6], m9[7], m9[8]);
                  }
                  g_backdrops.push_back(std::move(b));
              }
          },
          py::arg("backdrops"),
          "Set the active set's ordered backdrop list, applied each frame().");
```

Don't call `g_backdrop_pass->render(...)` from `frame()` yet — that's Task 13's atomic cut-over. The descriptors are stored but no rendering happens until then.

- [ ] **Step 4: Build everything**

Run: `cmake --build build -j 8`
Expected: full clean build.

- [ ] **Step 5: Run new tests**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/test_backdrops_bindings.py -v`
Expected: All 3 PASS.

- [ ] **Step 6: Run full host suite to verify no regression**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/ -q`
Expected: All existing tests still pass; the legacy `set_skybox` path is unchanged.

- [ ] **Step 7: Commit**

```bash
git add native/src/host/host_bindings.cc tests/host/test_backdrops_bindings.py
git commit -m "feat(host): set_backdrops binding + g_backdrop_pass (legacy still active)"
```

---

## Task 11: `engine.renderer.set_backdrops` Python wrapper

**Files:**
- Modify: `engine/renderer.py`

- [ ] **Step 1: Append a smoke test**

Append to `tests/host/test_backdrops_bindings.py`:

```python
def test_renderer_module_set_backdrops_wrapper_exists():
    from engine import renderer
    assert hasattr(renderer, "set_backdrops")
    renderer.set_backdrops([])
```

- [ ] **Step 2: Run to verify failure**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/test_backdrops_bindings.py::test_renderer_module_set_backdrops_wrapper_exists -v`
Expected: FAIL with `AttributeError: module 'engine.renderer' has no attribute 'set_backdrops'`.

- [ ] **Step 3: Add the wrapper to `engine/renderer.py`**

After the existing `set_lighting` function:

```python
def set_backdrops(backdrops: list) -> None:
    """Configure the renderer's ordered backdrop list. Each entry is a
    dict matching engine.appc.backdrops.aggregate_for_renderer's output:

        {
            "texture_path": str (absolute),
            "kind": "star" | "backdrop",
            "h_tile": float, "v_tile": float,
            "h_span": float, "v_span": float,
            "world_rotation": list[9],
            "target_poly_count": int,
        }
    """
    _h.set_backdrops(backdrops)
```

- [ ] **Step 4: Verify**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/test_backdrops_bindings.py -v`
Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/renderer.py tests/host/test_backdrops_bindings.py
git commit -m "feat(host): engine.renderer.set_backdrops Python wrapper"
```

---

## Task 12: `host_loop.run()` integration — call `r.set_backdrops` per tick

**Files:**
- Modify: `engine/host_loop.py`

- [ ] **Step 1: Insert the per-tick `set_backdrops` call**

In `engine/host_loop.py`, locate the existing block:

```python
            r.set_camera(eye=eye, target=target, up=up_vec,
                         fov_y_rad=1.0472, near=1.0, far=100000.0)

            ambient, directionals = _aggregate_lights(
                _resolve_active_lighting_set(player))
            r.set_lighting(ambient, directionals)

            if verbose and ticks == 0:
                print(f"[host_loop] tick 0 camera eye={eye} target={target}", flush=True)
                print(f"[host_loop] tick 0 lighting ambient={ambient} "
                      f"directionals={directionals}", flush=True)

            r.frame()
```

Replace with:

```python
            r.set_camera(eye=eye, target=target, up=up_vec,
                         fov_y_rad=1.0472, near=1.0, far=100000.0)

            active_set = _resolve_active_set(player)
            ambient, directionals = _aggregate_lights(active_set)
            r.set_lighting(ambient, directionals)

            backdrops = _aggregate_backdrops(active_set)
            r.set_backdrops(backdrops)

            if verbose and ticks == 0:
                print(f"[host_loop] tick 0 camera eye={eye} target={target}", flush=True)
                print(f"[host_loop] tick 0 lighting ambient={ambient} "
                      f"directionals={directionals}", flush=True)
                print(f"[host_loop] tick 0 backdrops: "
                      f"{len(backdrops)} layer(s)", flush=True)

            r.frame()
```

The descriptors are stored in `g_backdrops` but the renderer's `frame()` doesn't draw them yet (Task 13).

- [ ] **Step 2: Run the existing 5-tick smoke**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/test_host_loop_unit.py::test_run_M1_Basic_for_a_few_ticks -v`
Expected: PASS. Backdrops accumulate in `g_backdrops` but the legacy skybox path still drives what's drawn.

- [ ] **Step 3: Verify `_aggregate_backdrops` produces the expected stars layer for M1Basic**

Run: `OPEN_STBC_HOST_HEADLESS=1 OPEN_STBC_HOST_VERBOSE=1 uv run pytest tests/host/test_host_loop_unit.py::test_run_M1_Basic_for_a_few_ticks -v -s 2>&1 | grep "tick 0 backdrops"`
Expected: `[host_loop] tick 0 backdrops: 2 layer(s)` (StarSphere + treknebula BackdropSphere from Biranu1).

- [ ] **Step 4: Run full host suite**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/ -q`
Expected: all PASS, no regression.

- [ ] **Step 5: Commit**

```bash
git add engine/host_loop.py
git commit -m "feat(host): per-tick set_backdrops from active set in run()"
```

---

## Task 13: Cut over to `BackdropPass`; remove legacy `set_skybox` path

**Files:**
- Modify: `native/src/host/host_bindings.cc`
- Modify: `native/src/renderer/include/renderer/frame.h`
- Modify: `native/src/renderer/frame.cc`
- Modify: `native/src/renderer/include/renderer/pipeline.h`
- Modify: `native/src/renderer/pipeline.cc`
- Modify: `native/src/renderer/CMakeLists.txt`
- Modify: `native/src/scenegraph/include/scenegraph/world.h`
- Modify: `engine/renderer.py`
- Modify: `engine/host_loop.py`
- Modify: `tests/host/test_scene_setup.py`
- Modify: `tests/host/test_scene_bindings.py`
- Delete: `native/src/renderer/shaders/skybox.vert`
- Delete: `native/src/renderer/shaders/skybox.frag`
- Delete: `native/tests/renderer/skybox_test.cc`
- Delete: `tools/pick_default_skybox.py`

This is the largest task and the only "atomic" cut-over. After it, the legacy skybox path is gone and the new path is the only one.

- [ ] **Step 1: Replace `submit_skybox` call in `frame()` with `g_backdrop_pass->render`**

In `native/src/host/host_bindings.cc`, find:

```cpp
    g_world.propagate();
    g_submitter->submit_skybox(lookup(g_world.skybox_model()), g_camera, *g_pipeline);
    g_submitter->submit_opaque(g_world, g_camera, *g_pipeline, lookup, g_lighting);
```

Replace with:

```cpp
    g_world.propagate();
    g_backdrop_pass->render(g_backdrops, g_camera, *g_pipeline);
    g_submitter->submit_opaque(g_world, g_camera, *g_pipeline, lookup, g_lighting);
```

- [ ] **Step 2: Remove `set_skybox` binding from `host_bindings.cc`**

Delete the `m.def("set_skybox", ...)` block.

- [ ] **Step 3: Remove `submit_skybox` from `FrameSubmitter`**

In `native/src/renderer/include/renderer/frame.h`, delete:

```cpp
    void submit_skybox(const assets::Model* skybox_model,
                       const scenegraph::Camera& camera,
                       Pipeline& pipeline);
```

In `native/src/renderer/frame.cc`, delete the `submit_skybox` function body and the helper `draw_model_skybox` it used.

- [ ] **Step 4: Remove `skybox_shader()` from Pipeline**

In `native/src/renderer/include/renderer/pipeline.h`, delete `skybox_shader()` accessor and `skybox_` member.

In `native/src/renderer/pipeline.cc`, delete the `skybox_` initialization line and the `embedded_skybox_*.h` includes.

- [ ] **Step 5: Delete legacy skybox shader files + CMake embed**

```bash
rm native/src/renderer/shaders/skybox.vert
rm native/src/renderer/shaders/skybox.frag
rm native/tests/renderer/skybox_test.cc
rm tools/pick_default_skybox.py
```

In `native/src/renderer/CMakeLists.txt`, delete:

```cmake
embed_shader(SHADER_SKYBOX_VS shaders/skybox.vert skybox_vs)
embed_shader(SHADER_SKYBOX_FS shaders/skybox.frag skybox_fs)
```

Also check `native/tests/renderer/CMakeLists.txt` and remove `skybox_test.cc` from the `renderer_tests` source list (the file existed in the prior task and was referenced by the test target).

Run: `grep -n "skybox" /Users/mward/Documents/Projects/dauntless/native/tests/renderer/CMakeLists.txt`
Expected if present: a `skybox_test.cc` line. Remove it.

- [ ] **Step 6: Remove `skybox_model_` slot from `scenegraph::World`**

In `native/src/scenegraph/include/scenegraph/world.h`, delete:

```cpp
    void set_skybox(ModelHandle model) noexcept { skybox_model_ = model; }
    ModelHandle skybox_model() const noexcept { return skybox_model_; }
```

and:

```cpp
    ModelHandle skybox_model_ = 0;
```

- [ ] **Step 7: Remove `set_skybox` from `engine/renderer.py`**

Delete the `set_skybox` function.

- [ ] **Step 8: Remove `DEFAULT_SKYBOX_NIF` and the boot-time skybox load from `engine/host_loop.py`**

Delete the `DEFAULT_SKYBOX_NIF` constant declaration. In `run()`, delete:

```python
        if DEFAULT_SKYBOX_NIF:
            sky = r.load_model(DEFAULT_SKYBOX_NIF, DEFAULT_TEXTURE_SEARCH)
            r.set_skybox(sky)
```

- [ ] **Step 9: Migrate `test_set_skybox_*` tests**

In `tests/host/test_scene_setup.py`, find `test_set_skybox_does_not_crash_in_frame` and replace it with:

```python
def test_set_backdrops_does_not_crash_in_frame():
    """Replaces the legacy skybox slot test. Drive the new backdrop API
    end-to-end through frame() to ensure the pass renders without GL
    errors when fed an empty descriptor list."""
    import os
    os.environ["OPEN_STBC_HOST_HEADLESS"] = "1"
    import _open_stbc_host
    _open_stbc_host.init(640, 360, "test_set_backdrops_does_not_crash")
    try:
        _open_stbc_host.set_backdrops([])
        _open_stbc_host.set_camera(
            eye=(0.0, 0.0, 1500.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 1.0, 0.0),
            fov_y_rad=1.0472, near=1.0, far=100000.0,
        )
        _open_stbc_host.frame()  # must not raise
    finally:
        _open_stbc_host.shutdown()
```

In `tests/host/test_scene_bindings.py`, find `test_set_skybox_does_not_raise` and replace with:

```python
def test_set_backdrops_does_not_raise():
    import _open_stbc_host
    _open_stbc_host.set_backdrops([])
```

- [ ] **Step 10: Build everything**

Run: `cmake --build build -j 8`
Expected: full clean build. Linker errors here mean a missed reference; grep for `skybox` in the source tree:

`grep -rn "skybox\|set_skybox\|submit_skybox\|skybox_shader" native/ engine/ App.py | grep -v "\.md\|docs/"` should return nothing.

- [ ] **Step 11: Run all tests**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/ -q && cd build && ctest --output-on-failure 2>&1 | tail -5`
Expected: all PASS. The 5-tick M1Basic smoke now drives `BackdropPass::render` with the 2-layer descriptor list captured from `Biranu1.LoadBackdrops`.

- [ ] **Step 12: Visual smoke (optional but recommended)**

Run (no headless flag):

```bash
unset OPEN_STBC_HOST_HEADLESS
./build/bin/open_stbc_host
```

Expected: starfield visible behind the Galaxy. Press a key / close window to exit. If the starfield doesn't appear, check verbose log: `OPEN_STBC_HOST_VERBOSE=1 ./build/bin/open_stbc_host` should print `tick 0 backdrops: 2 layer(s)`.

- [ ] **Step 13: Commit**

```bash
git add -A  # captures deletions + edits
git commit -m "feat(renderer): cut over to BackdropPass; remove legacy skybox path"
```

---

## Task 14: Native `BackdropPass` test + integration tests

**Files:**
- Create: `native/tests/renderer/backdrop_pass_test.cc`
- Modify: `native/tests/renderer/CMakeLists.txt`
- Create: `tests/host/test_backdrops_integration.py`

- [ ] **Step 1: Create the native gtest**

`native/tests/renderer/backdrop_pass_test.cc`:

```cpp
#include <gtest/gtest.h>

#include <renderer/backdrop_pass.h>
#include <renderer/pipeline.h>
#include <renderer/window.h>
#include <scenegraph/camera.h>

#include <glad/glad.h>

namespace {

class BackdropPassTest : public ::testing::Test {
protected:
    std::unique_ptr<renderer::Window> window;
    std::unique_ptr<renderer::Pipeline> pipeline;

    void SetUp() override {
        window = std::make_unique<renderer::Window>(256, 256, "backdrop_test", false);
        pipeline = std::make_unique<renderer::Pipeline>();
    }
    void TearDown() override {
        pipeline.reset();
        window.reset();
    }
};

TEST_F(BackdropPassTest, EmptyListProducesNoGLError) {
    renderer::BackdropPass pass;
    scenegraph::Camera cam;
    cam.eye = {0, 0, 1500};
    cam.target = {0, 0, 0};
    cam.aspect = 1.0f;
    pass.render({}, cam, *pipeline);
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}

TEST_F(BackdropPassTest, SphereCacheReusesAcrossDescriptors) {
    renderer::BackdropPass pass;
    scenegraph::Camera cam;
    cam.aspect = 1.0f;

    renderer::Backdrop b1;
    b1.texture_path = "/dev/null";  // load fails; sphere still requested
    b1.target_poly_count = 256;
    renderer::Backdrop b2 = b1;  // same poly count

    pass.render({b1, b2}, cam, *pipeline);  // both share one sphere

    // No way to introspect the cache from the public API; smoke-only.
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}

TEST_F(BackdropPassTest, TargetPolyCountSnapsToMinimum) {
    renderer::BackdropPass pass;
    scenegraph::Camera cam;
    cam.aspect = 1.0f;

    renderer::Backdrop b;
    b.target_poly_count = 1;  // below minimum
    b.texture_path = "/dev/null";

    pass.render({b}, cam, *pipeline);
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}

}  // namespace
```

- [ ] **Step 2: Add the test to `native/tests/renderer/CMakeLists.txt`**

Add `backdrop_pass_test.cc` to the `renderer_tests` source list. Run:

```
grep -n "skybox_test\|frame_test" native/tests/renderer/CMakeLists.txt
```

to find the existing test list and append `backdrop_pass_test.cc` next to `frame_test.cc`.

- [ ] **Step 3: Build and run native tests**

Run: `cmake --build build --target renderer_tests -j 8 && cd build && ctest -R BackdropPass --output-on-failure`
Expected: all 3 BackdropPass tests PASS.

- [ ] **Step 4: Write Python integration tests**

Create `tests/host/test_backdrops_integration.py`:

```python
"""End-to-end backdrop rendering tests."""
import os
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent.parent
GAME = PROJECT_ROOT / "game"
GALAXY_NIF = GAME / "data" / "Models" / "Ships" / "Galaxy" / "Galaxy.nif"
STARS_TGA = GAME / "data" / "stars.tga"


def _star_descriptor():
    return {
        "texture_path": str(STARS_TGA),
        "kind": "star",
        "h_tile": 22.0, "v_tile": 11.0,
        "h_span": 1.0, "v_span": 1.0,
        "world_rotation": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "target_poly_count": 256,
    }


def _setup_for_pixel_test():
    if not STARS_TGA.is_file():
        pytest.skip("BC assets not available")
    os.environ["OPEN_STBC_HOST_HEADLESS"] = "1"
    import _open_stbc_host
    _open_stbc_host.init(640, 360, "test_backdrops_integration")
    _open_stbc_host.set_camera(
        eye=(0.0, 0.0, 1500.0),
        target=(0.0, 0.0, 0.0),
        up=(0.0, 1.0, 0.0),
        fov_y_rad=1.0472, near=1.0, far=100000.0,
    )
    return _open_stbc_host


def test_backdrop_renders_into_corner_pixel():
    """Backdrop pixel at corner of viewport (no opaque geometry there)
    must NOT be the clear-color value (~13, 18, 26)."""
    h = _setup_for_pixel_test()
    try:
        h.set_backdrops([_star_descriptor()])
        h.frame()
        r, g, b, a = h.read_pixel(0, 0)
        clear = (13, 18, 26)
        # If the backdrop is rendering, at least one channel should differ
        # from the clear color by more than the noise floor.
        diff = abs(int(r) - clear[0]) + abs(int(g) - clear[1]) + abs(int(b) - clear[2])
        assert diff > 5, (
            f"corner pixel = ({r},{g},{b}) — looks like the clear color; "
            f"backdrop did not render")
    finally:
        h.shutdown()


def test_camera_rotation_changes_pixel_translation_does_not():
    """Rotation reference: rotating the camera 30° about the up axis
    must change the corner pixel. Translation along the camera forward
    must NOT change the same corner pixel (modulo float noise)."""
    h = _setup_for_pixel_test()
    try:
        h.set_backdrops([_star_descriptor()])

        # Baseline.
        h.frame()
        r0, g0, b0, _ = h.read_pixel(0, 0)

        # Translate forward 1000 units.
        h.set_camera(
            eye=(0.0, 0.0, 500.0),
            target=(0.0, 0.0, -1000.0),
            up=(0.0, 1.0, 0.0),
            fov_y_rad=1.0472, near=1.0, far=100000.0,
        )
        h.frame()
        r1, g1, b1, _ = h.read_pixel(0, 0)

        # Rotation: 30° about up axis from baseline.
        import math
        a = math.radians(30)
        new_target = (math.sin(a) * -1000.0, 0.0, math.cos(a) * -1000.0)
        h.set_camera(
            eye=(0.0, 0.0, 1500.0),
            target=new_target,
            up=(0.0, 1.0, 0.0),
            fov_y_rad=1.0472, near=1.0, far=100000.0,
        )
        h.frame()
        r2, g2, b2, _ = h.read_pixel(0, 0)

        # Translation: same corner pixel within tolerance.
        d_trans = abs(int(r0)-int(r1)) + abs(int(g0)-int(g1)) + abs(int(b0)-int(b1))
        assert d_trans <= 5, (
            f"translation should not change corner pixel: "
            f"baseline=({r0},{g0},{b0}), translated=({r1},{g1},{b1})")

        # Rotation: corner pixel must differ from baseline.
        d_rot = abs(int(r0)-int(r2)) + abs(int(g0)-int(g2)) + abs(int(b0)-int(b2))
        assert d_rot > 5, (
            f"rotation should change corner pixel: "
            f"baseline=({r0},{g0},{b0}), rotated=({r2},{g2},{b2})")
    finally:
        h.shutdown()


def test_lighting_still_works_with_backdrops():
    """Regression: opaque pass lighting must not be broken by the new
    backdrop pass. Reuses the existing red-vs-black ambient assertion."""
    if not GALAXY_NIF.is_file():
        pytest.skip("BC assets not available")
    h = _setup_for_pixel_test()
    try:
        h.set_backdrops([_star_descriptor()])
        tex_search = str(GAME / "data" / "Models" / "SharedTextures" /
                         "FedShips" / "High")
        m = h.load_model(str(GALAXY_NIF), tex_search)
        iid = h.create_instance(m)
        h.set_world_transform(iid, [
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            0, 0, 0, 1,
        ])
        fw, fh = h.framebuffer_size()
        cx, cy = fw // 2, fh // 2

        h.set_lighting((1.0, 0.0, 0.0), [])
        h.frame()
        red_r, _, _, _ = h.read_pixel(cx, cy)

        h.set_lighting((0.0, 0.0, 0.0), [])
        h.frame()
        dark_r, _, _, _ = h.read_pixel(cx, cy)

        assert red_r > dark_r + 50, (
            f"lighting regressed after backdrops added: red_r={red_r}, dark_r={dark_r}")

        h.destroy_instance(iid)
    finally:
        h.shutdown()
```

- [ ] **Step 5: Run integration tests**

Run: `OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/host/test_backdrops_integration.py -v`
Expected: all 3 PASS.

- [ ] **Step 6: Run full Python + native suites**

Run:

```bash
OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/ -q
cd build && ctest --output-on-failure | tail -3
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add native/tests/renderer/backdrop_pass_test.cc \
        native/tests/renderer/CMakeLists.txt \
        tests/host/test_backdrops_integration.py
git commit -m "test(backdrops): native gtest + camera-rotation/translation integration"
```

---

## Task 15: Documentation — deferred-work + sub-project status

**Files:**
- Modify: `native/src/host/docs/deferred_work.md`
- Modify: `docs/superpowers/specs/2026-05-09-renderer-host-design.md`
- Modify: `docs/architecture/sub_project_status.md`

- [ ] **Step 1: Mark deferred-work item #1 implemented**

In `native/src/host/docs/deferred_work.md`, find item #1 ("Skybox path lookup from mission/system config"). Replace with:

```
1. **Skybox path lookup from mission/system config.** ✅ Implemented
   2026-05-10 as a multi-layer backdrop system rather than a single-NIF
   skybox slot. See
   [`docs/superpowers/specs/2026-05-10-skybox-backdrops-design.md`](../../../../docs/superpowers/specs/2026-05-10-skybox-backdrops-design.md).

   - Phase-1 shim (`engine/appc/backdrops.py`) materialises BC's
     `App.StarSphere_Create()` / `App.BackdropSphere_Create()` /
     `pSet.AddBackdropToSet(obj, name)` calls into `SetClass._backdrops`
     (insertion order = draw order).
   - `engine/host_loop.run` resolves the active set each tick via
     `_resolve_active_set` (shared with lighting), aggregates backdrops
     into a flat descriptor list, calls `r.set_backdrops(...)`.
   - `BackdropPass` (`native/src/renderer/backdrop_pass.{h,cc}`) draws
     the list with depth-write off, depth-LEQUAL, front-face culling
     reversed; per-backdrop blend mode (opaque for StarSphere,
     `GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA` for BackdropSphere); shared
     procedural UV-sphere mesh cache + per-texture cache.
   - **NIF-skybox parsing was deliberately NOT part of this work** — BC
     ships no skybox NIFs (`tools/pick_default_skybox.py` only matched
     starbase NIFs by name; tool removed by this commit).

   Follow-up backlog:

   - **Lens-flare rendering.** Used by
     `Tactical.LensFlares.YellowLensFlare(pSet, pSun)`; scoped into
     sub-project #3 (sun + planet rendering).
   - **Backdrop animation.** No stock content uses rotating nebulae;
     cosmetic future option.
   - **Cubemap path.** Higher-detail starfields via cubemaps; mod
     territory.
```

- [ ] **Step 2: Mirror in the renderer-host design spec**

In `docs/superpowers/specs/2026-05-09-renderer-host-design.md`, find item #1 in the Deferred / future work list. Replace with:

```
1. **Skybox path lookup from mission/system config** — ✅ Implemented
   2026-05-10. See
   [`2026-05-10-skybox-backdrops-design.md`](2026-05-10-skybox-backdrops-design.md).
   Reframed as a multi-layer backdrop system: ordered StarSphere +
   BackdropSphere registrations from BC's runtime Python-script calls,
   driven through `engine/appc/backdrops` and a new C++ `BackdropPass`.
   NIF-skybox parsing was deliberately scoped out (no skybox NIFs in BC's
   asset corpus).
```

- [ ] **Step 3: Update sub-project status table**

In `docs/architecture/sub_project_status.md`, add a row under the existing renderer sub-projects:

```
| 3-6+ | Star-sphere skybox + backdrop layers | Implemented (2026-05-10; BC's StarSphere + BackdropSphere registrations driven from script through new BackdropPass) | [2026-05-10-skybox-backdrops-design.md](../superpowers/specs/2026-05-10-skybox-backdrops-design.md) | (folded into renderer-host's `deferred_work.md`) |
```

- [ ] **Step 4: Verify cross-references**

Run: `grep -n "2026-05-10-skybox-backdrops-design" docs/superpowers/specs/2026-05-09-renderer-host-design.md native/src/host/docs/deferred_work.md docs/architecture/sub_project_status.md`
Expected: 3 hits, one per file, all pointing to the new spec.

- [ ] **Step 5: Commit**

```bash
git add native/src/host/docs/deferred_work.md \
        docs/superpowers/specs/2026-05-09-renderer-host-design.md \
        docs/architecture/sub_project_status.md
git commit -m "docs: skybox/backdrops sub-project implemented; record follow-ups"
```

---

## Final verification

- [ ] **Build everything:**

```bash
cmake --build build -j 8
```

- [ ] **All Python tests:**

```bash
OPEN_STBC_HOST_HEADLESS=1 uv run pytest tests/ -q
```

Expected: 100% pass; new tests in `tests/unit/test_appc_backdrops.py`,
`tests/unit/test_aggregate_backdrops.py`,
`tests/host/test_backdrops_bindings.py`,
`tests/host/test_backdrops_integration.py`, plus extensions to
`tests/unit/test_set.py` and `tests/host/test_host_loop_lighting.py`
are green; no regressions in existing 47 host-loop tests or the 13
lighting tests.

- [ ] **All native tests:**

```bash
cd build && ctest --output-on-failure | tail -5
```

Expected: 100% pass including the 3 new BackdropPass tests.

- [ ] **Visual smoke:**

```bash
unset OPEN_STBC_HOST_HEADLESS
./build/bin/open_stbc_host
```

Expected: Galaxy ship visible against a starfield (data/stars.tga tiled
22×11 across the sphere). Camera follows the ship; as the player turns
(Q/W/E/A/S/D + 0–9 + R), stars sweep across the view, providing the
rotation reference the user asked for. Translation does NOT shift the
stars (the standard skybox no-parallax behavior — by design).

- [ ] **Verbose smoke:**

```bash
OPEN_STBC_HOST_VERBOSE=1 ./build/bin/open_stbc_host
```

Expected `stderr` includes:

```
[host_loop] tick 0 backdrops: 2 layer(s)
```

(StarSphere + treknebula BackdropSphere from `Biranu1.LoadBackdrops`.)
