# Renderer Host — Deferred Work

This file mirrors the "Deferred / future work" section of the design spec at
[`docs/superpowers/specs/2026-05-09-renderer-host-design.md`](../../../../docs/superpowers/specs/2026-05-09-renderer-host-design.md).

The spec is the authoritative source. Update both when items move on or off
the list.

## Spec items

1. **Skybox path lookup from mission/system config.** Replaces the v1
   hard-coded default skybox. Note: BC ships no actual skybox NIFs in
   `game/data` (the `tools/pick_default_skybox.py` scan only finds
   starbases that match "star"). Skybox is procedural in BC. v1 leaves
   `DEFAULT_SKYBOX_NIF = None` in `engine/host_loop.py` and the renderer's
   skybox pass is a no-op.
2. **BC light data interpretation.** ✅ Implemented 2026-05-10.
   See [`docs/superpowers/specs/2026-05-10-bc-light-data-design.md`](../../../../docs/superpowers/specs/2026-05-10-bc-light-data-design.md).

   - Phase-1 shim (`engine/appc/lights.py`) materialises BC's
     `LightPlacement` / `Config*Light` / `pSet.Create*Light` calls into
     `SetClass._lights`.
   - `engine/host_loop.run` resolves the active set
     (`g_kSetManager.GetRenderedSet()` → player's set → None) each tick,
     aggregates 1 ambient + up to 4 directionals, calls
     `r.set_lighting(...)`.
   - `opaque.frag` consumes the ambient + directional array.

   **NIF-block light parsing is intentionally not part of this work** — a
   binary survey of all 93 NIFs in the repo (`game/data/` + `sdk/Art/`)
   found zero `NiAmbient*` / `NiDirectional*` blocks. Stock BC stores no
   lighting in scene NIFs.

   Follow-up backlog:

   - **Bridge & cinematic light rendering.** When bridge rendering
     arrives, revisit `SetClass.CreateAmbientLight`'s 4th-arg semantics
     (range vs dimmer) — bridges call it with values up to 19.0, treated
     as dimmer today.
   - **`AddIlluminatedObject` per-object filtering.** Phase 1 ignores
     it; lights affect every object in the set. Becomes relevant when
     characters render.
   - **Save/load coverage of `Light` and `SetClass._lights`.** Tracked
     under "Save/load coverage of render state" (existing item #15).
   - **Point/spot light support.** No stock content uses them. The NIF
     parser already understands `NiPointLight` / `NiSpotLight` block
     types for forward compatibility.
   - **Per-set lighting persistence across set transitions.** The
     pull-each-tick model re-aggregates every frame; cache by `_lights`
     identity if profiling later shows it matters.
3. **Animation playback.** Evaluate `AnimationClip` data already present
   in `Model` (asset pipeline produces it; renderer ignores it).
4. **Skinned-mesh rendering.** Bone palette uniform, vertex skinning in
   the vertex shader, evaluation against `Skeleton` data already in
   `Model`. The opaque shader currently has the bone_indices /
   bone_weights vertex inputs but ignores them.
5. **LOD selection.** Depends on asset pipeline populating
   `Mesh::lod_chain` first (asset pipeline deferred-work item #1). v1 uses
   `FilenameHigh` for every ship.
6. **Frustum culling.** Sphere-in-frustum test once scene-instance count
   grows beyond a few dozen. Requires the asset pipeline to produce
   per-`Model` bounding volumes; cross-cutting work into the asset
   pipeline. The `Camera::view_matrix` / `proj_matrix` infrastructure in
   v1 is already sufficient to derive frustum planes when needed.
7. **Decoupled render thread / interpolation.** Off-table for v1,
   available if profiling later shows headroom problems.
8. **Render targets / framebuffers / post-processing.** Required for
   bloom, motion blur, etc.; none of these are v1 surface.
9. **Debug fly-around camera** (mouse + WASD). Needs an input-binding
   layer.
10. **In-game camera modes** (tactical, bridge, external orbit,
    cinematic). Each needs its own camera-state machine and BC-config
    interpretation.
11. **HUD and UI.** Separate sub-project entirely; not part of any item
    in the renderer breakdown.
12. **Procedural FX** (explosions, weapon fire, warp trails). Gap analysis
    confirms runtime-procedural; will need its own renderer pass and
    particle system.
13. **Hardpoint-marker / damage-node interpretation.** The rest of item 6
    in the renderer breakdown.
14. **Mod / asset-overlay support.** Depends on asset pipeline gaining
    the same (asset pipeline deferred-work item #6).
15. **Save/load coverage of render state.** Phase 1 concern; render state
    is rebuilt at load from Python ship state, but the seam needs to be
    formalized once Phase 1 save/load lands.
16. **BC input system integration.** Keyboard/mouse/joystick mapping
    matching BC's input scheme, distinct from the v1 fixed third-person
    camera.
17. **Read turn rate / max impulse from BC config.** `_PlayerControl`'s
    `TURN_RATE_RAD_PER_S` (1.5) and `IMPULSE_UNIT` (50.0) are tuned by
    feel; they should come from the ship's `ImpulseEngineSubsystem`
    properties or `GlobalPropertyTemplates.py` once Phase 1 wires those
    up. Same for `REVERSE_LEVEL`.
18. **Switch to physics integration.** When `engine/physics/simulation.py`
    gets a real PyBullet integrator, `_PlayerControl.apply` should set
    target velocity / target angular velocity on the ship's impulse
    subsystem instead of writing the transform directly.
19. **BC config-file keybindings.** Read user-customized bindings from
    `data/scripts/Custom/Bridge/Keymap.py` (or wherever BC stores them)
    so players who remap keys see those bindings honored.
20. **Mouse input.** Stock BC supports yaw/pitch via mouse-look; v1 is
    keyboard-only.
21. **Acceleration / deceleration curves.** v1 sets impulse level
    instantaneously; BC ramps. Adding ramps depends on item 18 above.
22. **Auto-damping toggle.** Some space sims auto-damp angular velocity
    when no input is held; v1 doesn't (release = stop turning, but no
    re-centering).

## v1 deviations from the original plan

These are things the implementation found that the plan didn't anticipate;
captured here so future contributors don't re-discover them.

- **`-force_load,$<TARGET_FILE:nif>` required on host targets.** The NIF
  block parsers self-register via static initializers. Without
  force-loading the nif archive into both the `_open_stbc_host` module
  and the `open_stbc_host` executable, the linker drops the unreferenced
  object files and the registrations never run; `model_build` then
  throws "no NiNode root in NIF file" on every load. The same pattern
  was already used by `nif_tests` and `assets_tests`. See
  `native/src/host/CMakeLists.txt`.

- **`<pybind11/stl.h>` required for STL conversions.** pybind11's
  `std::vector<float>` / `std::tuple<float,float,float>` automatic
  conversions need this header at the binding-module's translation unit.
  Missing it produces a runtime `TypeError: incompatible function
  arguments` on first call, not a compile error. See
  `native/src/host/host_bindings.cc`.

- **`Development.Embed` (granular form) required.** CMake's legacy
  `find_package(Python3 ... COMPONENTS Development Embed)` (two separate
  components) fails on macOS Python.framework. The granular
  `Development.Embed` works because it lets CMake match the framework
  bundle. See `native/CMakeLists.txt`.

- **Top-level `cmake -S . -B build`.** The README's `-S native -B build`
  example skips the project's top-level `CMakeLists.txt` (which wraps
  `native/`). The docs and the plan have been corrected. Asset tests
  reference `${CMAKE_SOURCE_DIR}/native/src/assets/src` which only
  resolves correctly when `CMAKE_SOURCE_DIR` is the project root.

- **White-fallback texture in `FrameSubmitter`.** Originally added because
  Galaxy.nif's materials returned `stages[Base].texture_index = -1` from
  the asset pipeline. That asset-pipeline gap was fixed 2026-05-09 (see
  `native/src/assets/docs/deferred_work.md` item #19) and the Galaxy now
  renders with real BC textures. The white-fallback is kept as
  defensive logic for materials that legitimately have no Base-stage
  texture (procedural surfaces, etc.) — without it, GL's zero-texture
  produces black pixels and the lighting math is wiped out.

- **`SetClass.GetNextObject` wraps around.** The Phase 1 set iterator
  returns the first object after the last (mirroring BC's iteration
  semantics). A naive `while obj is not None` loop infinite-loops on a
  populated set. `engine/host_loop.py:_iter_set_objects` detects the
  wrap-around by comparing object IDs against the first object's ID.

- **No skybox NIF in BC assets.** `tools/pick_default_skybox.py` returns
  starbase NIFs (matching "star" in the path) because BC's skybox is
  procedural, not a NIF. v1 leaves `DEFAULT_SKYBOX_NIF = None` and the
  skybox pass is a no-op. Real skybox lookup → procedural starfield is
  spec deferred-work item #1.
