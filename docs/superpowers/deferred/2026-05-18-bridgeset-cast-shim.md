# Deferred: bridge view POC cluster (BridgeSet, ModelManager, camera, image, animation)

**Status:** deferred 2026-05-18. Decision: do not shim the bridge-asset cluster right now. The harness profile will continue to record `BridgeSet_Cast`, `g_kModelManager.LoadModel`, `CameraObjectClass_CreateFromNiCamera`, `g_kImageManager.GetImageDetail`, and `g_kAnimationManager.LoadAnimation` as un-implemented engine surface until the bridge view POC lands. These five entries are one transactional unit — same 26-mission set, same call path through bridge config init, same renderer-side blocker. Resolution work is owned by [`docs/superpowers/specs/2026-05-11-bridge-view-poc-design.md`](../specs/2026-05-11-bridge-view-poc-design.md) and [`docs/superpowers/specs/2026-05-11-bridge-interior-render-design.md`](../specs/2026-05-11-bridge-interior-render-design.md).

## Cluster scope

The harness profile groups together because they all fire during the same `LoadBridge.Load(...)` → `<config>.CreateBridgeModel(pBridgeSet)` path. Representative call sequence ([Bridge/SovereignBridge.py:29-67](../../../sdk/Build/scripts/Bridge/SovereignBridge.py#L29-L67)):

| Profile entry | Missions × calls | Role in the bridge init transaction |
|---|---:|---|
| `BridgeSet_Cast` (+ subtree) | 26 × 121 | Downcast generic `SetClass` to bridge subclass; reach viewscreen |
| `g_kImageManager.GetImageDetail` | 26 × 84 | Pick Low/Medium/High NIF env path |
| `g_kModelManager.LoadModel` | 26 × 168 | Preload bridge interior NIF + crew character NIFs |
| `g_kModelManager.CloneCamera` | 26 × 78 | Pull a fresh `NiCamera` from a cached NIF |
| `CameraObjectClass_CreateFromNiCamera` (+ frustum subtree) | 26 × 78 | Wrap `NiCamera` in a `CameraObjectClass`, copy frustum |
| `g_kAnimationManager.LoadAnimation` | 9 × 15 | Crew Talk/Idle animations (after bodies loaded) |

The 96 SDK `g_kModelManager.LoadModel` callsites are almost entirely in [`sdk/Build/scripts/Bridge/`](../../../sdk/Build/scripts/Bridge/) — ~90 for crew body+head preload (e.g. [Bridge/Characters/Graff.py:38-39](../../../sdk/Build/scripts/Bridge/Characters/Graff.py#L38-L39)), ~6 for bridge interior + viewscreen NIFs (e.g. [Bridge/SovereignBridge.py:35-36](../../../sdk/Build/scripts/Bridge/SovereignBridge.py#L35-L36)).

## Context

The cluster lead is `BridgeSet_Cast`. 26 of 35 missions cast `g_kSetManager.GetSet("bridge")` to a `BridgeSet`; the call site is identical everywhere ([MissionLib.py:1050](../../../sdk/Build/scripts/MissionLib.py#L1050) is the canonical form):

```python
pSet = App.BridgeSet_Cast(App.g_kSetManager.GetSet("bridge"))
```

The cast is a downcast from generic `SetClass*` to the `BridgeSet` subclass so callers can reach bridge-specific methods on the returned object — primarily `GetViewScreen()`, `SetViewScreen()`, `SetConfig()`, `GetConfig()`, `IsSameConfig()` ([sdk App.py:4871-4888](../../../sdk/Build/scripts/App.py#L4871-L4888)). The viewscreen object itself ([sdk App.py:4821-4858](../../../sdk/Build/scripts/App.py#L4821-L4858)) carries the bulk of the runtime methods (`SetIsOn`, `SetRemoteCam`, `SetStaticIsOn`, `SetMenu`, etc.), which is why the harness shows a whole `BridgeSet_Cast().GetViewScreen().*` subtree under the root cast.

`g_kModelManager` is the renderer's per-NIF model cache — a refcounted registry that loads, clones, and frees individual `.nif` files. Surface defined at [sdk App.py:627-671](../../../sdk/Build/scripts/App.py#L627-L671); SDK scripts call four methods (`LoadModel`, `CloneCamera`, `CloneModel`, `GetModel`). Distinct from `g_kLODModelManager` ([engine/appc/lod_models.py:93](../../../engine/appc/lod_models.py#L93)) which lives one layer up and tracks ship-class LOD registrations indexed by class name.

## Why we are not shimming this

Unlike `GridClass`, this cluster is **not** dead code. Mission scripts actively drive the viewscreen during warp-in/out, comm channel toggles, and cutscenes, and several callers (e.g. [WarpSequence.py:384](../../../sdk/Build/scripts/WarpSequence.py#L384)) do not guard `GetViewScreen()` against `None`. A minimum-effort `Cast → None` shim would crash those paths.

A "real `BridgeSet` subclass with a stub `ViewScreenObject`" shim is feasible (~50 lines in [`engine/appc/sets.py`](../../../engine/appc/sets.py) + [`engine/appc/objects.py`](../../../engine/appc/objects.py)) and was the obvious next step, but the bridge POC work is already specced and the shim's state model (`is_on`, `remote_cam_target`, `static_on`, `menu`) will be re-derived by that spec. Doing both means writing the same state machine twice and migrating callers when the renderer lands. Cleaner to wait and have the bridge POC own the data model from day one.

The same argument applies to the rest of the cluster. A record-only `g_kModelManager.LoadModel` shim (track loaded paths, return `None`) would clear that row but leave the downstream `CameraObjectClass_CreateFromNiCamera` / `ViewScreenObject_Create` / `BridgeObjectClass_Create` wrappers stubbed because they still need a real cached `NiNode`. Net profile reduction is modest, and the model-name registry would be rewritten by the POC. Same trade-off for `g_kImageManager.GetImageDetail` (returns a detail-level index that only matters when there's a renderer to honor it) and `g_kAnimationManager.LoadAnimation` (the loaded animation has no consumer without a skeletal animation pipeline).

Cost of deferral: the harness profile keeps the bridge cluster rows. We can filter the report when other surfaces are under investigation.

## Resolution path

The bridge view POC ([`2026-05-11-bridge-view-poc-design.md`](../specs/2026-05-11-bridge-view-poc-design.md)) is the work that retires this entry. When that lands it should:

- Provide a real `BridgeSet(SetClass)` subclass in [`engine/appc/sets.py`](../../../engine/appc/sets.py) with `GetViewScreen`, `SetViewScreen`, `SetConfig`, `GetConfig`, `IsSameConfig`.
- Expose `BridgeSet_Cast` from [`App.py`](../../../App.py) returning the `BridgeSet` when the named set exists, `None` otherwise (matching the SWIG semantics).
- Replace the [LoadBridge.py shim](../../../LoadBridge.py) registration so `g_kSetManager.GetSet("bridge")` returns a `BridgeSet`, not a generic `SetClass`.
- Implement a `ViewScreenObject(ObjectClass)` with at minimum `SetIsOn`, `IsOn`, `SetRemoteCam`, `SetStaticIsOn`, `IsStaticOn`, `SetMenu`, `ClearMenu`, `AddPythonFuncHandlerForInstance`. Backed by the actual viewscreen render target produced by the bridge interior pass.
- Expose `g_kModelManager` from [`App.py`](../../../App.py) as a Python-side `TGModelManager` that delegates to the C++ NIF loader in `native/src/`. Required methods: `LoadModel(path, root_node, env_path=None)`, `LoadModelIncremental`, `IsModelLoaded`, `GetModel`, `CloneModel`, `CloneCamera`, `FreeModel`, `FreeAllModels`, `Refer`, `Unrefer`. This is the prerequisite for `BridgeObjectClass_Create` / `ViewScreenObject_Create` / `ZoomCameraObjectClass_Create` to return something the renderer can draw.
- Expose `g_kImageManager` with at minimum `GetImageDetail()` returning the current detail-level index (0/1/2 → Low/Medium/High NIF env paths).
- Expose `CameraObjectClass_CreateFromNiCamera(pNiCamera, name)` that wraps a `NiCamera` (returned by `g_kModelManager.CloneCamera`) in a `CameraObjectClass` and supports the `GetNiFrustum` / `SetNiFrustum` frustum-transfer transaction visible in the profile.
- Expose `g_kAnimationManager` with `LoadAnimation(path)` — needed once crew character skeletons are loadable.

Acceptance check after that work: running `uv run python tools/gameloop_harness.py --profile` shows all five cluster rows (BridgeSet, ModelManager, Camera, Image, Animation) gone from the report, and the viewscreen-rendering smoke test in the POC spec passes.

## Revisit trigger

Re-evaluate if the bridge POC slips materially (e.g. blocked on interior-render dependencies for more than a sprint). In that case implement the stub-state shim (`BridgeSet` + `ViewScreenObject` recording on/off, remote-cam target, static state, menu) as an interim — same pattern as `GridClass` but with state instead of no-ops. The shim becomes a useful contract for the POC to consume rather than throwaway work. Do NOT pre-emptively implement `g_kModelManager` / camera / image-manager shims at the same time; the renderer-side NIF loader has to be exposed back to Python for them to be load-bearing, and that's POC-grade work, not shim-grade.

## Files in scope (for the resolving work, not now)

| File | Relevance |
|---|---|
| [`engine/appc/sets.py`](../../../engine/appc/sets.py) | Add `BridgeSet(SetClass)` with bridge-specific methods |
| [`engine/appc/objects.py`](../../../engine/appc/objects.py) | Add `ViewScreenObject(ObjectClass)`, `BridgeObjectClass`, `CameraObjectClass` |
| `engine/appc/model_manager.py` (new) | Python-side `TGModelManager` delegating to the native NIF loader |
| `engine/appc/image_manager.py` (new) | `g_kImageManager` with `GetImageDetail` and friends |
| `engine/appc/animation_manager.py` (new) | `g_kAnimationManager` with `LoadAnimation` |
| [`App.py`](../../../App.py) | Export `BridgeSet`, `ViewScreenObject`, `BridgeSet_Cast`, `g_kModelManager`, `g_kImageManager`, `g_kAnimationManager`, `CameraObjectClass_CreateFromNiCamera` |
| [`LoadBridge.py`](../../../LoadBridge.py) | Register a `BridgeSet` instead of generic `SetClass` |
| `native/src/host/` | Expose the existing C++ NIF loader through the host extension so Python `TGModelManager` can delegate |
| [`docs/superpowers/specs/2026-05-11-bridge-view-poc-design.md`](../specs/2026-05-11-bridge-view-poc-design.md) | Owns the resolution |
| [`docs/superpowers/specs/2026-05-11-bridge-interior-render-design.md`](../specs/2026-05-11-bridge-interior-render-design.md) | Renderer-side dependency |
