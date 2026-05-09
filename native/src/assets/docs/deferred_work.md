# Asset Pipeline — Deferred Work

This file mirrors the "Deferred / future work" section of the design spec at
[`docs/superpowers/specs/2026-05-09-asset-pipeline-design.md`](../../../../docs/superpowers/specs/2026-05-09-asset-pipeline-design.md).

The spec is the authoritative source. Update both when items move on or off
the list.

1. **LOD chain population.** `Mesh::lod_chain` reserved field; meshoptimizer-
   driven decimation when wanted.
2. **Async loading.** Sync v1; state-machine handle for v2.
3. **Glow / specular suffix conventions** (item 6 of renderer plan).
4. **Med / Low LOD NIFs.** Pipeline ignores them; App.py shim absorbs.
5. **Material normalization layer (Approach C).** Defer until renderer asks.
6. **Mod / asset-overlay support.** Single search dir today.
7. **CI without BC install.** Same problem as nif loader.
8. **GL context-loss recovery.** `keep_cpu_data` is the seed.
9. **PNG / DDS / BC1-7 textures.** TGA only for v1.
10. **Vertex tangent slot.** Required for normal mapping; layout currently 44 B.
11. **HDR texture format (`RGBA16F`).**
12. **Phase 1 Python bindings.**
13. **Continuous LOD via cluster / mesh shaders.** Off-table given GL 3.3.
14. **Skinned animation playback.** Scene-graph-runtime concern.
15. **Particle effects.** Runtime-procedural per gap_analysis.
16. **`NiBinaryVoxelData` semantics.** Defer to scene-graph or physics.
17. **Save/load.** Phase 1 concern; pipeline rebuilds on load.
18. **Streaming / virtual textures.** Not needed today.
19. ~~**Material → texture stage linking.**~~ FIXED 2026-05-09. The bug was twofold:
    (a) `load_all_textures` keyed `image_to_texture` by NIF block-array index, but `TexDesc::source_link` (and the new `NiTextureProperty::image_link`) is a *link ID* — BC NIFs use 8-digit non-sequential link IDs, so the keys never matched. Fixed by keying the map by link ID (via `f.block_ids[i]`).
    (b) `material_build` had no handler for `NiTextureProperty` (singular, single-texture v3.x property used by Galaxy and other BC ships) — only `NiTexturingProperty` (multi-stage) and `NiMultiTextureProperty`. Added `apply_texture_property` populating `stages[Base]`. `gather_material_inputs` now picks up `NiTextureProperty` blocks too. Smoke test `ModelSmokeTest.LoadsGalaxyEndToEnd` now asserts at least one material resolves a Base-stage texture; renderer-host's headless ship-gate test asserts the rendered pixels are *textured* (not just white-fallback).

## v1 deviations from the original plan

These are things the implementation found that the plan didn't anticipate;
captured here so future contributors don't re-discover them.

- **`LinkResolver` introduced.** Real BC NIFs use 8-digit non-sequential link
  IDs in cross-block references; cannot be used as direct array indices.
  `link_resolver.h` builds a `link_id → block_index` map (with identity
  fallback for synthetic tests). Used by `skeleton_build`, `animation_build`,
  and `model_build`. Materials are gathered through `property_links` in the
  orchestrator and also go through the resolver.

- **`*_lifetime.cc` files.** The plan put Texture/Mesh ctor/move/dtor in
  `texture_upload.cc` / `mesh_upload.cc`. They actually need to land
  alongside the public headers (Task 6) so `Model`'s vector destruction
  links — split into `texture_lifetime.cc` / `mesh_lifetime.cc` (no GL
  *calls*, just symbol resolution; the `if (id_)` guard makes the dtor safe
  in CPU-only tests). The `*_upload.cc` files only host the actual
  `upload_image` / `upload_mesh` functions (Tasks 16/17).

- **`AssetCache` two-arg constructor pattern.** clang refused `AssetCache(Config = {})`
  because nested-type default initializers aren't visible at default-arg
  parse time. Replaced with two overloads: `AssetCache()` delegates to
  `AssetCache(Config{})`.
