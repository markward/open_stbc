# NetImmerse / Gamebryo — Engine Reference

Consolidated clean-room reference for the NetImmerse / Gamebryo runtime as it
relates to Bridge Commander's NIF content. Distilled from the SDK clean-room
investigation (questionnaire rounds 1 and 2 plus supplementary findings) into
a single reference organised by subsystem.

Confidence tags inline: **[documented]**, **[inferred from source]**,
**[inferred from sample]**, **[not found]**. Limit categories:
**[structural]** (encoded in the file format), **[runtime-architectural]**
(in the engine's runtime design), **[hardware-era]** (DX8 / fixed-function
of the 2002-2006 era — a modern reimplementation is free to relax these).

---

## 0. SDK identity and the BC mapping

The SDK on the contaminated side is **Gamebryo 1.2.2** by NDL, built
2006-06-19. Gamebryo is the post-2003 rebrand of NetImmerse; the runtime
architecture, public class names (`NiNode`, `NiAVObject`, `NiAlphaProperty`,
etc.), and file-format mechanics descend directly from NetImmerse 3.x/4.x.
The header string this SDK writes is `"Gamebryo File Format, Version
1.2.0.0"`. Its loader's minimum NIF version is **3.3.0.11**.

Bridge Commander shipped 2002 against **NetImmerse 3.x/4.x** — its NIFs are
at NIF version ~4.0.x. The architecture is continuous, but expect drift:

- **Animation:** BC uses the legacy `NiKeyframeController` + `NiSequence`
  on disk. Gamebryo 1.x split the model into `NiInterpController` +
  `NiInterpolator` and ships a conversion path so legacy classes load as
  modern ones (see §7). At runtime, BC's `NiKeyframeController` instances
  become `NiTransformController` objects — the legacy name appears only on
  disk.
- **Particles:** BC uses the pre-Gamebryo-1.1 "old particle" system, kept
  in `NiOldParticle`. The modern `NiPSys*` modular emitter system is
  post-BC. For a BC reimplementation, the old surface is what to build.
- **Shaders:** Gamebryo's `NiShader` framework is newer than BC. BC is
  fixed-function multitexture only.
- **NIF schema:** field-level details and flag bits shifted across
  versions; NifSkope's reverse-engineered tables remain authoritative
  for the BC-era schema. This SDK is reliable downstream of 3.3.0.11.

The single universal cutoff in the legacy paths is **NIF 10.1.0.104** —
every legacy controller's body-reader branches on this constant. BC's
files are far below it, so they exercise every legacy code path.

---

## 1. File format and streaming

### 1.1 File family

All of these flow through the same `NiStream` and link-ID model. The
streaming layer doesn't care about file extension — it dispatches on the
substring `"File Format"` in the opening ASCII line.

- **`.NIF`** — scene graph (nodes, geometry, properties, lights, textures).
- **`.KF`** — animation clips: one or more `NiControllerSequence` (modern)
  or `NiSequence` (BC-era) with their interpolators and key data, **no
  scene graph**. Applied at runtime to a separately-loaded NIF whose node
  names match.
- **`.KFM`** — Keyframe Manager / actor state machine. ASCII originally,
  binary in Gamebryo 1.2. Drives `NiActorManager`: names sequences with
  stable IDs and encodes allowed transitions.
- **`.NSF` / `.NSB`** — programmable-shader source/binary. Post-BC.
- **NIF-as-texture** — `NiNIFImageReader` lets a texture be packaged as
  a NIF holding a single `NiPixelData`.

BC almost certainly uses custom file extensions for NIF-stream-compatible
files. A reimplementation should detect by first-line content, not
extension.

### 1.2 On-disk byte layout

```
1. Header line: ASCII C-string "Gamebryo File Format, Version a.b.c.d\n"
   (predecessor NetImmerse builds wrote "NetImmerse File Format, ..."; the
    loader matches on the substring "File Format" alone)
2. NIF version: u32, packed bytes (a<<24)|(b<<16)|(c<<8)|d, little-endian
3. [iff version >= 10.0.1.8] User-defined version: u32
4. Total object count: u32
5. RTTI table:
   - RTTI name count: u16
   - For each name: length-prefixed C-string (name of a class)
   - For each object slot (count from step 4): u16 index into RTTI table
6. [iff post-1.0 NIF] Object groups table:
   - Group count: u32
   - For each group: u32 byte size (used for arena-style allocation)
7. Object bodies, one per slot, in slot order
8. Top-level objects:
   - Count: u32
   - For each top-level: u32 link ID
```

There is no endianness marker — endianness is a build/platform property.
Win32 NIFs are little-endian throughout. PS2 builds existed but used the
same loader code with platform-specific image/texture sub-paths.

There is no embedded checksum, signature, or DRM-style integrity check.
No documented compression at the format level (ZLib ships in the SDK
third-party tree but is not used for whole-file NIF compression at this
version).

### 1.3 Object bodies, link IDs, two-pass load

Each object writes its scalar fields and **link IDs** (32-bit integer
indices into the file-wide object array) for its references. There are
no pointers, no name-based lookups, and no strong/weak distinction at
the format level — ownership is enforced at the C++ level via smart
pointers, which are transparent to the on-disk form.

The load process is breadth-first, not depth-first:

1. `RegisterStreamables(stream)` — save-side; recursively registers every
   referenced object once.
2. `SaveBinary(stream)` — writes the body.
3. `CreateObject()` — static factory, called at load.
4. `LoadBinary(stream)` — reads body fields and link IDs (does not
   dereference yet).
5. `LinkObject(stream)` — second pass: resolves link IDs to pointers.

The split between `LoadBinary` and `LinkObject` is what makes the
breadth-first model work and is why a NIF can be read in any order
without circular-reference problems.

Block ordering inside the body section is **not semantically
constrained** — children may precede or follow parents. The Max/Maya
exporters happen to place the root scene-graph node first by convention.

### 1.4 RTTI table — the schema directory

The RTTI table at file head is the only thing that tells you which
classes are in the file. Each body's class is determined by
`body_index → RTTI table → class name string`. A clean-room loader can:

- Pre-scan the RTTI name list before reading any body and fail
  gracefully if an unsupported class is present (the stock SDK aborts
  with `NO_CREATE_FUNCTION`; a reimpl can skip-and-warn if it knows
  the body size).
- Use the RTTI list as a sanity check (an animation NIF will have
  `NiControllerSequence`, `NiTransformInterpolator`, etc.).
- Detect BC custom blocks immediately: any RTTI name not in the stock
  Gamebryo set is a custom block.

**Unknown block types are fatal in the stock SDK.** The loader looks up
each RTTI name in a global creation-function registry; a miss aborts
the load. There is no skip-unknown mechanism. BC's custom blocks were
almost certainly registered into the same factory at BC runtime
startup, not encoded in a vendor-reserved range.

### 1.5 Strings, nulls, primitives

- **No global string table** in the classic stream. Strings are written
  inline per block via a length-prefixed C-string primitive. Duplicates
  are not deduplicated.
  - The RTTI table is the one exception (each class name appears once,
    bodies reference by `u16` index).
  - Later versions add `NiStringPalette` for controller-target name
    deduplication in animation; this is a content-level optimisation,
    not a global table.
- **Null references** are encoded as the sentinel link ID `NULL_LINKID`,
  distinguishable from any valid slot. "Missing optional" is encoded
  either by omitting the field (version-gated) or by writing the null
  sentinel.
- **Floats** are IEEE-754 single throughout the standard scene graph.
  Half-floats / fixed-point appear in some specialized later-version
  data classes (B-spline compressed transforms) but not in foundational
  geometry / material / animation blocks.
- **Object groups** (post-BC `NiObjectGroup`): post-load memory-locality
  hint. Multiple objects declare themselves grouped; the streaming
  system allocates them into a single contiguous block. Absent in
  BC-era content but the loader must read the group table even if it
  ignores the hint.

### 1.6 Extension hooks

Custom classes register via the RTTI-name-keyed creation-function map:
declare RTTI via `NiDeclareRTTI`, declare streaming via `NiDeclareStream`,
implement the five-function streaming protocol, and call
`NiRegisterStream(ThisClass)` at startup to insert
`(className → CreateObject)` into the loader.

There is no reserved version range for vendor extensions. The
`user-defined version` 32-bit word added at NIF 10.0.1.8+ is a
vendor-coordination field, but BC predates that revision.

A clean-room reimpl doesn't need to mirror this pattern — an equivalent
registry mapping class name → factory function is sufficient. The
five-virtual-function protocol is a useful guide to per-class
responsibilities, not a constraint on implementation.

---

## 2. Scene graph

### 2.1 NiAVObject transform model

Composition on every `NiAVObject`:

```
parent_world · (T · R · S)
```

- **T** is a translation `NiPoint3`.
- **R** is a 3×3 orthonormal rotation `NiMatrix3`.
- **S** is a **single scalar uniform scale**.

Points are transformed `vL = (T R S) · vM`, `vW = parent_world · vL`
(column-vector convention, matrices act on the left).

**There is no per-axis (non-uniform) scale at the transform level.**
Non-uniform scale, shear, and reflection must be baked into geometry
data via `ApplyTransform` and propagated to leaf vertices. This is part
of why normals can reuse the position matrix under skinning (the
inverse-transpose collapses for orthonormal rotation + uniform scale).

### 2.2 Update model — lazy, scene-wide

World transforms are **lazily refreshed via a scene-wide `Update(time)`
call** that must run at or above any object whose local transform
changed since the previous update, before that object (or its
descendants) is rendered or collision-checked. There is no eager
set-propagates-immediately mechanism.

The update walk is two-pass:
1. **Downward pass**: recompute child world transforms; tick each
   controller's `Update` to evaluate animation values and write them
   back to targets.
2. **Upward pass**: refresh ancestors' world bounds.

`UpdateSelected(time)` is a variant that uses per-node "selective
update" flags to skip transform recomputation for static subtrees.
Exporters set these flags on load.

### 2.3 NiAVObject flags

- **App-cull flag** (`SetAppCulled`): when true, the object and its
  subtree are skipped during the rendering walk. Not propagated down
  — setting it on an ancestor will not hide a descendant reachable
  via a different scene path.
- **Display-object flag**: doesn't affect Gamebryo drawing; reserved
  as a hook for third-party occlusion culling.
- **Selective-update flags** (four of them): `SelectiveUpdate`,
  `SelectiveUpdateTransforms`, `SelectiveUpdatePropertyControllers`,
  `SelectiveUpdateRigid`. Performance optimisations, not visibility.
  Misconfigured flags produce silently wrong transforms/bounds, so
  the docs flag this as a hazard.

There is no separate "render culled" bit — render culling is the
dynamic result of frustum culling and isn't stored.

### 2.4 Bounds

Each `NiAVObject` carries a world-space bound; `NiNode` derives its
bound from children. Two modes:
- **Merge**: classical — the node's bound is the merger of all child
  world bounds each frame.
- **Rigid**: faster — node holds a precomputed local bound that just
  gets transformed by the node's world transform. Valid only if
  descendants aren't independently animated. Controlled by the
  `SelectiveUpdateRigid` flag.

The recomputation is triggered by the Update upward pass, so a child's
bound always inflates the parent's after an Update covering both, but
never during unrelated frames.

**Authoritative bound type is the bounding sphere** (`NiBound`, center
+ radius). Frustum culling uses this. Collision detection adds OBB and
AABB hierarchies as separate alternate bounding volumes (`NiOBBNode`,
`NiOBBRoot`, `NiOBBLeaf`, `NiSphereBV`, `NiBoxBV`, `NiCapsuleBV`,
`NiUnionBV`) living alongside the scene graph rather than replacing
the sphere bound. Picking uses the sphere bound, optionally refined
to triangle level.

### 2.5 Switch, LOD, billboard, BSP, sort-adjust nodes

- **`NiSwitchNode`**: selects active child by integer index
  (`SetIndex(int)`, `-1` = none active). Manual by default. Optional
  `UpdateOnlyActiveChild` flag tells Update to skip inactive
  subtrees; active child updated on demand if it changes between
  Update and render.
- **`NiLODNode`** derives from `NiSwitchNode`. Asks its `NiLODData`
  which child to make active given the current camera:
  - **`NiRangeLODData`**: numeric distance bands (each child has a
    near/far range; camera-to-node distance picks the band).
  - **`NiScreenLODData`**: apparent-screen-size metric.
  - Distance is computed from the camera position to the LOD node's
    world-space bound center (not nearest point).
  - `LOD Adjust` factor on `NiCamera` (default 1.0) globally scales
    apparent distance.
  - `GlobalLOD` static override forces all LOD nodes to a specific
    index (debug tool).
- **`NiBillboardNode`** modes:
  - `ALWAYS_FACE_CAMERA` — model-space +Z aligns to camera view-plane
    normal, recomputed each frame.
  - `ROTATE_ABOUT_UP` (default) — +Z faces camera as closely as
    possible while only rotation about model-space [0,1,0] is allowed.
  - `RIGID_FACE_CAMERA` — billboard normal stays parallel to camera
    direction; frame rigidly rotates with camera frame.
  - `ALWAYS_FACE_CENTER` — +Z points at camera origin (vs view-plane).
  - `RIGID_FACE_CENTER` — +Z at camera origin, rigid rotational
    coupling.
  - The "up" vector for `ROTATE_ABOUT_UP` is **model-space up of the
    billboard node itself** ([0,1,0] in the node's local frame), not
    world-up — so a billboard's effective axis is determined by its
    parent transform chain.
  - Orientation update happens **during the render-pass cull walk**,
    not during Update, so the billboard's apparent orientation is
    always consistent with the current camera state.
- **`NiSortAdjustNode`** (NiNode subclass): mid-scene-graph sorter
  push/pop. Modes: `SORTING_INHERIT`, `SORTING_OFF` (subtree draws in
  traversal order regardless of alpha), `SORTING_SUBSORT` (uses a
  locally-attached sorter for the subtree, then pops). Use cases:
  skybox drawn first, HUD drawn last, in-engine sub-scenes.
- **`NiBSPNode`**: NiNode whose left/right children are split by a
  plane. Documented use is gross-scale sort separation, not per-poly
  BSP. The renderer picks the side the camera is on first.

There is no distinct "scene root" class — any `NiNode` can be a
scene root; `NiCamera::SetScene(NiNode*)` accepts any node.

### 2.6 Children vs effects

Every `NiAVObject` child of an `NiNode` participates in the transform
hierarchy. Drawability is determined by the leaf type: a `NiCamera`
or `NiLight` isn't drawn but is positioned by its parent; an
`NiGeometry` leaf is.

Lights and effects attach via a separate **dynamic effect list**
(`AttachEffect` / `DetachEffect`) distinct from the child array. This
is the closest thing to a non-rendered, transform-affecting child,
but effects don't have their own subtree.

---

## 3. Geometry

### 3.1 Vertex attributes

`NiGeometryData` (base of `NiTriShapeData`, `NiTriStripsData`, etc.)
stores:
- **Positions**: `NiPoint3` array, always present for non-empty geometry.
- **Normals**: optional `NiPoint3`, **per-vertex**, in **model space**.
  Per-face normals are not stored; flat shading uses
  `NiShadeProperty::SetSmooth(false)`.
- **Vertex colors**: optional `NiColorA` — RGBA float (not packed bytes
  at this engine level).
- **Texture coordinates**: optional array of `NiPoint2` with explicit
  "number of texture sets" count. Multiple UV sets are concatenated.
- **Binormals + tangents**: optional, stored interleaved-by-block with
  normals (all normals, then all binormals, then all tangents) when
  enabled by an NBT method enum. Full `NiPoint3` per vertex, no
  compression. When absent, the renderer computes on demand.

Presence is flagged by null vs non-null pointers (plus the NBT method
enum for binormals/tangents).

### 3.2 Triangle and strip data

- **`NiTriShapeData`**: triangle list with `unsigned short*` indices.
  **Indices are 16-bit unsigned** in this SDK; 32-bit indices are not
  native, so geometry exceeding 65535 indices must be split.
- **`NiTriStripsData`**: **multiple independent triangle strips per
  object**, not a single restart-encoded super-strip. Stores a strip
  count, a per-strip vertex-count array, and a flat index list
  concatenating all strips. No restart index or degenerate triangles
  at the format level. Strip orientation is encoded per-strip; the
  renderer uses each strip's natural orientation and does not flip
  culling between strips.

No vertex-cache-optimization hint at the format level. The
stripification tool (`NiStripify`) produces cache-friendly strips at
export time; the runtime doesn't record or consult an indicator.

### 3.3 Skinning attachment, instancing

Skinning attaches to an ordinary `NiGeometry` via an `NiSkinInstance`
pointer on that geometry — there is no separate "skinned geometry"
subclass.

Mesh sharing follows the `NiGeometry`/`NiGeometryData` split: when a
scene graph is cloned, the `NiGeometry` is duplicated but the
`NiGeometryData` is shared by smart pointer. Two `NiTriShape`s
pointing at the same `NiTriShapeData` is the engine's notion of
instancing — no separate instance-node type.

---

## 4. Materials and rendering properties

### 4.1 Property stack rule

**Closer wins; only one property of a given type is active on any
given subtree.** Properties are pushed downward during the cull walk.
When a deeper `NiAVObject` carries a property of the same type as an
ancestor, the deeper one fully replaces the ancestor's for that
subtree. Properties do **not** combine. If no property of a given
type is on the ancestor chain, the engine's default-constructed
property of that type is used.

### 4.2 NiMaterialProperty

Channels and defaults:
- **Ambient** (default [0.5, 0.5, 0.5]) — modulated by each light's
  ambient component plus the global ambient light.
- **Diffuse** (default [0.5, 0.5, 0.5]) — modulated by each light's
  diffuse component, scaled by N·L.
- **Specular** (default [0, 0, 0]) — modulated by each light's specular
  contribution if specular is gated on; renderer-dependent in detail.
- **Emissive** (default [0, 0, 0]) — added unconditionally. The only
  channel that contributes when no light is hitting the surface.
- **Alpha** (default 1.0, range 0..1) — translucency.
- **Shineness / glossiness** (default 4.0, non-negative) — specular
  exponent.

When no light contributes (or `NiVertexColorProperty::LIGHTING_E` is
selected), only emissive is taken. Documented lighting equation
(paraphrased):

```
V_final = V_E + Σ_lights L_I · (L_A·V_A + A·S·L_D·V_D·R_D)
```

where V_E/V_A/V_D are emissive/ambient/diffuse vertex colors (chosen
from material or vertex color per the vertex-color property's source
mode), L_I is the dimmer, A and S are distance and spot attenuations,
R_D is the diffuse-reflection scalar (clamped N·L). Specular is added
in a renderer-dependent way and is not formally part of this equation.

### 4.3 NiSpecularProperty

Specular is **gated by a separate `NiSpecularProperty`** — a single
boolean flag. `NiMaterialProperty` stores specular color/shine but
doesn't toggle specular on/off by itself. Some renderers respect a
per-`NiMaterialProperty` "specular ignore" optimisation, but the
documented opt-out path is `NiSpecularProperty`.

### 4.4 NiAlphaProperty

Named fields:
- **Alpha-blend enable** (bool).
- **Source blend mode** / **Destination blend mode** (enum): ONE, ZERO,
  SRCCOLOR, INVSRCCOLOR, DESTCOLOR, INVDESTCOLOR, SRCALPHA, INVSRCALPHA,
  DESTALPHA, INVDESTALPHA, SRCALPHASAT.
- **Alpha-test enable** (bool).
- **Alpha-test function** (enum): ALWAYS, LESS, EQUAL, LESSEQUAL,
  GREATER, NOTEQUAL, GREATEREQUAL, NEVER.
- **Alpha-test reference** (u8, 0..255).
- **No-sort flag** (bool): when true, an alpha-blended object is not
  registered with `NiAlphaAccumulator` and draws immediately at its
  traversal-order position. Useful for hand-ordered transparent
  geometry.

Defaults: blending off, alpha-test off, src=SRCALPHA, dst=INVSRCALPHA,
test=ALWAYS, ref=0.

### 4.5 NiZBufferProperty

Three independent fields: depth-test enable (bool), depth-write enable
(bool), depth-test function (enum: ALWAYS, LESS, EQUAL, LESSEQUAL
(default), GREATER, NOTEQUAL, GREATEREQUAL, NEVER). Default enables
both with LESSEQUAL. All four (test, write) × (true, false)
combinations are individually meaningful.

### 4.6 NiStencilProperty

- **Enable** (bool).
- **Function** (same TEST_* enum).
- **Reference** (u32). **Mask** (u32, default 0xFFFFFFFF).
- **Pass action** (stencil pass + Z pass).
- **Pass-but-Z-fail action**.
- **Fail action**.
  Actions: KEEP, ZERO, REPLACE, INCREMENT, DECREMENT, INVERT.
  Defaults: pass=INCREMENT, others=KEEP.
- **Draw mode** — independent culling override (stencil effects often
  need two-sided draw): DRAW_CCW_OR_BOTH (default), DRAW_CCW, DRAW_CW,
  DRAW_BOTH.

### 4.7 NiTexturingProperty — slots and combiners

Named stage slots:
- **Base map** — primary diffuse texture. Combined with vertex/material
  color per the property's apply mode.
- **Dark map** — multiplicative light map (white = fully lit); modulated
  against result so far.
- **Detail map** — high-frequency surface texture, combined with base
  via `2 × baseColor × detailColor` (modulate2x).
- **Gloss map** — modulates specular contribution per texel.
- **Glow map** — additive emissive contribution that does **not** depend
  on light direction. Independent of the material's emissive color.
- **Bump map** — gradient-encoded normal/height map. Stage carries a
  2×2 bump matrix and, paired with an env-map, generates perturbed
  env-map coordinates.
- **Decal 0..N** — additional decal stages indexed by integer. Each
  decal is RGBA; alpha gates the decal against the surface.
- **Shader map** — used by the higher-level `NiShader` system for
  arbitrary additional sampler bindings (post-BC).

Each `Map` (and `BumpMap`) records image (`NiTexture*`), clamp mode,
filter mode, and texture-coordinate set index. Combiner formula is
documented per stage type, not per `Map`.

**Apply modes**: `APPLY_REPLACE`, `APPLY_MODULATE`, `APPLY_DECAL`,
`APPLY_HILIGHT`. `MODULATE` is what makes vertex/material colors
visible at all when a base texture is present.

### 4.8 Filter and clamp modes

- **Filter** (per-Map enum): NEAREST, BILERP, NEAREST_MIPNEAREST,
  NEAREST_MIPLERP, BILERP_MIPNEAREST, BILERP_MIPLERP (trilinear),
  ANISOTROPIC.
- **Clamp**: CLAMP_S_CLAMP_T, CLAMP_S_WRAP_T, WRAP_S_CLAMP_T,
  WRAP_S_WRAP_T (the four corners), plus mirror variants in newer
  Gamebryo. No separate "clamp-to-edge" vs "clamp-to-border"
  distinction at this API level.

### 4.9 NiSourceTexture and pixel data

Carries either a filename reference or an in-memory `NiPixelData`.
`NiPixelData` stores pixel format via `NiPixelFormat` (channel count,
bit depths, component meaning, palettized modes via `NiPalette`).

Mipmaps: global `SetUseMipmapping(bool)` toggle (default true) plus
per-texture preferences. If mipmapping is on and source data is
non-mipmapped, the engine generates the pyramid. Mipmaps can also be
pre-stored in `NiPixelData`. The `LoadDirectToRendererHint` flag
short-circuits the app-side `NiPixelData` step for renderer-native
formats (DDS via `NiDDSReader`).

`NiSourceTexture` does **not** automatically deduplicate by filename
— each `Create` call returns a new instance. Renderer-side textures
*are* shared via the global preloading mechanism
(`SetUsePreloading(true)`), so the GPU resource is shared, but the
engine-side object is not. Applications that want app-side sharing
do their own filename → object cache.

### 4.10 NiTextureEffect — env-maps and projected textures

`NiTextureEffect` is a `NiDynamicEffect` (like `NiLight`) — env-maps
live in the dynamic-effect system, not the property stack.

- Attaches to an `NiNode` via `AttachEffect`, affecting the subtree.
- Carries a texture, a clip plane, and a texture-coordinate generation
  mode: `WORLD_PARALLEL`, `WORLD_PERSPECTIVE`, `SPHERE_MAP`,
  `SPECULAR_CUBE`, `DIFFUSE_CUBE`.
- The renderer inserts an additional texture stage in the affected
  subtree's draw with these generated coords.

This is the documented mechanism for environment-mapped reflections,
projected spotlights (texture-as-light-cookie), and sphere/cube
mapping on fixed-function hardware. Clipped-projected-textures count
as 2 textures against the multitexture stage budget.

### 4.11 NiVertexColorProperty

Two independent enums:
- **Source vertex mode**:
  - `SOURCE_IGNORE` — use only material colors.
  - `SOURCE_EMISSIVE` — vertex color overrides emissive only.
  - `SOURCE_AMB_DIFF` — vertex color overrides ambient + diffuse.
- **Lighting mode**:
  - `LIGHTING_E` — only emissive contributes (pre-lit / unlit).
  - `LIGHTING_E_A_D` — emissive + ambient + diffuse contribute.

Independent: one can ask for vertex-overridden ambient+diffuse while
only outputting emissive (classic static pre-lighting). Defaults:
`SOURCE_IGNORE` + `LIGHTING_E_A_D`.

### 4.12 NiShadeProperty / NiDitherProperty / NiWireframeProperty / NiFogProperty

- **`NiShadeProperty`**: single boolean `SetSmooth(bool)` — Gouraud
  (default) or flat. Phong-style would require `NiShader`.
- **`NiDitherProperty`**: single boolean (dither at framebuffer level;
  affects 16-bit display modes).
- **`NiWireframeProperty`**: single boolean (draw triangles as
  wireframe).
- **`NiFogProperty`**: enable flag, fog function enum
  (FOG_Z_LINEAR — cheap vertex/raster, distance from far plane;
  FOG_RANGE_SQ — eye-distance squared, fewer artifacts; older
  FOG_VERTEX_ALPHA no longer supported), fog color (independent of
  background), depth in normalized [0..1]. Per-pixel vs per-vertex is
  renderer-dependent.

No documented multi-pass fallback specifier in the format. Multi-pass
behaviour is handled internally by the renderer when a property
configuration exceeds single-pass hardware capability — the
application doesn't specify and there is no NIF-level encoding.

---

## 5. Lighting

### 5.1 Light classes

All four derive from `NiLight` (which derives from `NiDynamicEffect`)
and share:
- **Dimmer** (intensity scalar, default 1.0)
- **Ambient color** (default [1, 1, 1])
- **Diffuse color** (default [1, 1, 1])
- **Specular color** (default [1, 1, 1])

Subclass-specific:
- **`NiAmbientLight`**: nothing more — no location, direction, or
  attenuation.
- **`NiDirectionalLight`**: direction derived from the node's
  transform — light projects **down model-space +X axis**, defaults
  to [1,0,0] world-space. Rotating the parent node aims the light.
- **`NiPointLight`**: world location (from node transform), plus three
  attenuation factors (constant C, linear L, quadratic Q; defaults
  C=0, L=1, Q=0).
- **`NiSpotLight`** (extends `NiPointLight`): direction (also +X),
  cone angle (degrees, default 0), spot exponent (default 1.0).

Lights attach to the scene graph as children of ordinary `NiNode`s
and inherit transform. **The light's forward / shine axis is
model-space +X**, not -Z.

### 5.2 Attenuation

```
attenuation = 1 / (C + L·d + Q·d²)
```

where d is world-space distance from light to vertex. To disable
attenuation entirely, set C=1, L=0, Q=0. Ambient and directional
lights do not attenuate. Spot cone attenuation is linear from spot
direction to edge of cone when the spot exponent is 1.0; other
exponent values are renderer-dependent.

### 5.3 Light count and selection

No documented hard limit at the scene-graph level — `AttachEffect`
accepts arbitrary numbers. The actual cap is **8 simultaneous
hardware lights per object** (DX8/DX9 fixed-function T&L limit) —
**[hardware-era]**. Gamebryo drops lights beyond this with **no
documented distance/influence/priority selection algorithm**; artists
were expected to scope lights to small subtrees via the dynamic-effect
attachment mechanism.

Specular uses the light's **specular color** (a separate `NiColor`
from diffuse). Whether it contributes depends on `NiSpecularProperty`.
No per-material "ignore specular" flag.

No documented projected light textures or built-in shadow primitives
at this SDK era. `ShadowMap` and `StencilShadow` sample apps exist as
application-level implementations on top of the engine, not as
light-class features.

---

## 6. Animation

> **Historical note for BC:** BC ships against the
> **`NiKeyframeController`** model (single controller, multi-channel
> data block per node) — the **deprecated** path in this Gamebryo
> 1.2 SDK. Gamebryo 1.x split that model into `NiTimeController`-derived
> "interp controllers" each on one property of one target, holding
> `NiInterpolator` objects each one channel. Conversion is automatic
> at load (see §6.7).

### 6.1 NiTimeController base

Per-controller fields (every `NiTimeController` carries):
- **Start time** / **stop time** (floats; the time range over which
  keys are valid). Start/stop are inclusive endpoints.
- **Frequency** (float, default 1.0; multiplicative time scale).
- **Phase** (float, default 0.0; additive time offset).
- **Cycle type** (enum): LOOP, REVERSE (ping-pong), CLAMP (hold).
- **Animation type** (enum): APP_TIME (absolute application time),
  APP_INIT (subtract per-controller start moment so the animation
  re-bases when `Start` is called).
- **Active** (bool, default true; inactive controllers don't update).
- **Play-backwards** (bit). Added in 10.0.1.1 — older files need a
  flag-bit shift on load; files exactly at 10.0.1.1 encode it as a
  separate boolean after the standard fields.
- **Manager-controlled** (bit). Repurposed at 10.1.0.109 — files
  below have the bit force-cleared.

Effective evaluation time:
`((appTime - startMoment) · frequency + phase)`, mapped through
cycle type into [start, stop]:
- **CLAMP**: time is clipped to endpoint (holds first/last key).
- **LOOP**: time wraps modulo (stop − start).
- **REVERSE**: time reflects at endpoints (ping-pong).

Application time is passed in as a `float`. The engine does not clamp
or scale it itself; the application can pass real wall-clock, fixed-
step, or scaled time. No documented per-frame max step.

### 6.2 Attachment

A controller chain attaches to its target `NiObjectNET` via the
target's `controllers` linked-list field (`PrependController` /
`SetControllers` / `GetControllers`). On the controller,
`SetTarget(NiObjectNET*)` automatically inserts/removes itself in the
target's list.

`NiTimeController::SetTarget` is the only correct way to attach a
controller — don't call `PrependController` directly (documented
gotcha).

For multi-target performance: **`NiMultiTargetTransformController`**
is a single controller driving many targets simultaneously
(`NiControllerSequence` automatically inserts one if it doesn't find
one already). **`NiBoneLODController`** disables/re-enables groups of
bones based on LOD level — distance-based skeletal-LOD without
touching the skin instance.

When two controllers target the same property on the same object,
**whichever runs last wins** — its writes overwrite the first's.
There is no documented priority on raw time controllers; the
priority/blend system lives in `NiBlendInterpolator` one layer up.

### 6.3 Key families

Five key interpolation families:

**Rotation keys** (subclasses of `NiRotKey`):
- **`NiLinRotKey`** — time + quaternion. Slerp interpolation.
- **`NiBezRotKey`** — time + quaternion, **Hermite spline** despite
  the name. Each key stores an in-tangent and out-tangent (quaternion
  deltas), in the same space as the key values.
- **`NiTCBRotKey`** — time + quaternion + three TCB parameters
  (tension, continuity, bias, each in [-1, 1]). Kochanek-Bartels
  formulation: tangents at each key are a weighted combination of
  incoming/outgoing chord vectors weighted by (1−T)(1+C)(1+B) /
  (1−T)(1−C)(1−B) (incoming) and analogous outgoing. Boundary keys
  reflect the present chord for natural behaviour. Interpolation is
  cubic Hermite using those tangents.
- **`NiStepRotKey`** — time + quaternion, no interpolation; value
  holds until next key.
- **`NiEulerRotKey`** — *container*, not a single key. Holds three
  independent `NiFloatKey` arrays (X, Y, Z) each with its own
  interpolation type. Composed in **XYZ** order (extrinsic, fixed
  axes). Units are **radians**.

Position keys (`NiLinPosKey`, `NiBezPosKey`, `NiTCBPosKey`,
`NiStepPosKey`) and scale keys (`NiLinFloatKey`, `NiBezFloatKey`,
`NiTCBFloatKey`, `NiStepFloatKey`) mirror this taxonomy with the
family-appropriate math.

Quaternion slerp uses the shortest-arc selection (negate one
quaternion if dot product is negative). A fast-path Lerp +
counter-warp approximates slerp for small angular separation. No
runtime squad path — squad is in the offline animation-compression
tool (B-spline fit).

A separate **B-spline compressed** family exists for offline-compressed
animations (`NiBSplineInterpolator` and friends). Post-BC.

### 6.4 NiTransformData (formerly NiKeyframeData)

Three independent channels stored sequentially on disk:

```
1. Rotation channel:    u32 numRotKeys.   If non-zero:
                        rotation key type enum (LIN/BEZ/TCB/EULER/STEP)
                        then numRotKeys keys.
2. Position channel:    u32 numPosKeys.   If non-zero:
                        position key type enum (LIN/BEZ/TCB/STEP)
                        then keys.
3. Scale channel:       u32 numScaleKeys. If non-zero:
                        float key type enum (LIN/BEZ/TCB/STEP)
                        then keys.
```

Channels are fully independent — rotation can be LINEAR while
position is BEZIER and scale is TCB in the same block. Each channel
is one contiguous array (no interleaving). A channel with **zero
keys** means "no animation for this channel" — the interpolator
reports "value invalid" each frame and the runtime skips writing
that field, preserving the target's bind-pose value for that channel.

The Euler container is special: when the rotation channel uses EULER,
`numRotKeys` is required to be **exactly 1** (runtime assertion at
save time and equality testing). That single key body contains three
separate float-key arrays (X, Y, Z), each with its own count, type,
and keys. Each axis float-array **can be absent independently** —
zero keys for an axis means that axis isn't animated; runtime
defaults that axis to zero rotation contribution.

`NiKeyframeController` itself carried no fields beyond the base
`NiTimeController` — its body was a single link to `NiKeyframeData`.
Modern loading wraps that link via `NiTransformInterpolator(legacyData)`
into the controller's interpolator slot.

### 6.5 Sequences and the keyframe manager

**`NiSequence`** (BC-era) fields:
- **Name** — heap-allocated C string identifying the sequence.
- **Object-name array** — parallel array of C strings, one per
  sub-controller, naming the target scene-graph node. Resolution at
  activation time is by `GetObjectByName`.
- **Controller array** — same length, smart pointers to
  `NiTransformController` objects (transform-only in the legacy
  sequence model).
- **Text-key reference index** (u32) — names which controller's
  timing the text keys are anchored to.
- **Text-key smart-pointer** — to an `NiTextKeyExtraData`.

**Targets resolve by name string at activation time**, not by
pointer at load. The same sequence can drive any character with
matching node names.

Timing is **per-controller**, not per-sequence. Each sub-controller
carries its own start/stop/frequency/phase/cycle-type fields. The
sequence has no global timing — only the text-key-reference index
anchors text keys to a chosen sub-controller's timing. This differs
from modern `NiControllerSequence`, which centralizes timing.

**`NiKeyframeManager`** is a `NiTimeController` subclass attached at
the scene root. It owns a name-keyed map of sequences (zero or more,
plus external KF file references). Active vs inactive selection is a
runtime API, not a NIF field. `NiSequence` is **not a top-level
scene-graph object** — it's a child resource of the keyframe manager.

**Version gates** in this layer:
- **NIF < 4.1.0.3** — KF files encode sequences as a transient
  `NiSequenceStreamHelper` container carrying a controller chain
  with parallel string-extra-data entries; on load, the converter
  walks both lists pairwise and constructs an `NiSequence` on the
  fly. The keyframe manager also reads an elaborate per-sequence
  layout (saved-URL flag, per-sequence text-key state, per-key object
  name + controller link). **BC's files fall here.**
- **NIF ≥ 4.1.0.3** — sequences saved natively; manager layout is
  just a list of sequence link IDs.

### 6.6 Modern sequences, manager, blending

**`NiControllerSequence`** (modern) represents a named animation clip
— a set of interpolators with their targets and channel selectors,
plus optional text keys. Differences from raw controller chains:
- Loaded as a unit (typically from a KF rather than a NIF).
- Interpolators are attached to **blend interpolators** the sequence
  inserts at activation time, not directly to controllers in the
  scene graph.
- Targets resolve by **(node name + interpolator-target type RTTI
  name)** at activation, looking up `(nodeName, ctrlTypeName)` within
  the scene graph rooted at the manager's target.

**`NiControllerManager`** itself is a `NiTimeController` attached at
the subtree root it manages. Owns a list of sequences and currently-
active sequences. On `Update(time)`:
1. Ticks each active sequence, which evaluates its interpolators into
   the per-sequence side of blend interpolators.
2. Each blend interpolator computes a single result per controller
   target.

Blending model: **weighted average, with priority groups, with
cross-fade between the highest and next-highest priority groups via
an "ease spinner"**. Only sequences at the top-priority level
contribute fully; lower-priority sequences contribute via the ease
spinner. Activation supports fade-in/fade-out time, looping,
frequency, and ease curves at the sequence level.

**`NiBlendInterpolator`** algorithm:
1. Find highest priority among active sub-interpolators.
2. Compute weighted average of all sub-interpolators sharing that
   priority (using their weights).
3. If a lower-priority group is also active, compute its weighted
   average then cross-fade between the two by the summed ease spinner
   of the highest priority.
4. Sub-interpolators with weight below an internal threshold are
   dropped.
5. Weights are **not** renormalized — used as given. If they don't
   sum to 1, the result scales accordingly.
6. Optimization flag `OnlyUseHighestWeight` short-circuits to a
   single dominant interpolator when set.

**Name uniqueness matters** — two nodes with the same name in the
same skeleton creates ambiguous sequence binding. The exporters
enforce uniqueness.

### 6.7 Legacy animation conversion — three mechanisms

There is no single converter file. Legacy animation loading is split:

**(a) RTTI-name aliasing** at body-construction time. Exactly three
class names are aliased:
- `"NiKeyframeController"` → modern `NiTransformController`
- `"NiKeyframeData"` → modern `NiTransformData`
- `"NiVisData"` → modern `NiBoolData`

Other legacy controllers (`NiAlphaController`, `NiVisController`,
`NiUVController`, `NiFlipController`, `NiMaterialColorController`,
`NiLightColorController`) **kept their original class names** — they
are still first-class classes in this SDK, but their *body layouts*
changed at NIF 10.1.0.104 and their `LoadBinary` paths branch on
file version.

**(b) Version-gated branches** in each modern class's body-reader.
**NIF 10.1.0.104** is the universal cutoff:
- Below: read the legacy data-link layout and construct the modern
  interpolator from the legacy data block.
- At/above: read the interpolator-based modern layout directly.

The wrap is non-destructive — the legacy `NiKeyframeData` object
still exists as a `NiTransformData` (its modern alias) inside the
new interpolator. Conversion is a wrapper, not a data copy. The
interpolator's `Collapse()` is then called to trim unused channels.

**(c) A small post-process function** runs at the end of the load
pipeline (after bodies read, link IDs resolved, before top-level
objects return to caller). Registered via `NiStream`'s post-process
hooks. Handles **only three** controllers that need graph-topology
fixup:
- **`NiLookAtController`** → wraps its target reference and axis
  into a new `NiLookAtInterpolator` driven by a fresh or existing
  `NiTransformController` on the same target. If a transform
  controller already exists with a transform interpolator, position
  and scale tracks are migrated as side interpolators on the
  look-at interp (so a node can both look-at and translate).
- **`NiRollController`** → its float-data wraps into a new
  `NiFloatInterpolator` and attaches as the **roll sub-interpolator**
  of an existing look-at interpolator on the same target. **If no
  look-at is present, the roll is silently dropped** — roll is
  asymmetrically coupled.
- **`NiPathController`** → all path-shape settings plus path-data
  and percentage-data fold into a new `NiPathInterpolator`, which
  becomes the interpolator of a `NiTransformController` on the
  target.

Unrecognized controllers are **silently passed through** — no
warning, no logging. The converter retains no state about what it
did.

**At runtime, after load, no `NiKeyframeController` objects exist** —
they have all become `NiTransformController` objects with
`NiTransformInterpolator`s wrapping legacy `NiTransformData` blocks.
The class name in the NIF's RTTI table is `"NiKeyframeController"`,
but the constructor invoked is `NiTransformController::CreateObject`.

**Property-attached legacy controllers** are not visited by the
post-process walk (a chunk of property-list iteration is commented
out as "if we ever need to convert property time controllers, this
code should be uncommented"). Property-attached legacy controllers
rely on the per-class load-time path only.

### 6.8 Modern equivalents of legacy controllers

`NiVisController`:
- Targets any `NiAVObject`, animates `AppCulled` (logically inverted
  — `true` value means visible/not culled).
- Reads at load (file < 10.1.0.104): link to legacy `NiVisData`
  (now aliased `NiBoolData`), wrapped in `NiBoolInterpolator`.
- Legacy on-disk visibility key: `u32 numKeys; <time(f32),
  bool(byte)>` (implicit step keys). At 10.1.0.104+, a key-type enum
  is read first, allowing future key shapes.

`NiAlphaController`:
- Targets `NiMaterialProperty`, animates alpha via `SetAlpha(float)`.
- Legacy data is `NiFloatData`, wrapped in `NiFloatInterpolator`.

`NiMaterialColorController`:
- Targets `NiMaterialProperty`. Animates one of four color channels
  via a 3-bit field selector: AMBIENT (0), DIFFUSE (1), SPECULAR (2),
  SELF_ILLUM/EMISSIVE (3).
- In legacy files (< NIF 10.0.1.2) the selector was packed in higher
  bits of the base `NiTimeController` flag word; the loader shifts
  them down into the controller's own flag word and masks. From
  10.0.1.2+ the selector is a dedicated u16 after the base fields.
- Legacy data is `NiPosData` (color-as-Point3) wrapped in
  `NiPoint3Interpolator`. Output is clamped to [0,1] per channel.

`NiLightColorController`:
- Animates a light's ambient or diffuse color (boolean selector flag
  in the flags word). Legacy `NiPoint3Interpolator` wrapping.

`NiUVController` + `NiUVData`:
- Targets `NiGeometry` directly (not its `NiTexturingProperty`).
  Carries a `u16 textureSet` index naming the UV set to modify.
- Data class holds four independent float-key arrays: U-offset,
  V-offset, U-tiling, V-tiling (in that on-disk order).
- Computes per-frame: four scalars applied to every vertex's UV.
  Stateful delta accumulation — `NiUVData` remembers last-computed
  offset/tiling values to compute next-frame delta.
- "To match Max behaviour, tiling is centered about 0.5, U offset is
  subtracted, V offset is added." Composition order is `T·S` per axis,
  applied around UV-space center (0.5, 0.5).
- **Mutates the vertex buffer in place.** Modern equivalent
  `NiTextureTransformController` sets a per-stage transform matrix
  the renderer applies on the GPU. A reimplementation will want the
  matrix model — but BC content was authored against mutation.
- Tiling values of 0.0 trigger a debug assertion.

`NiFlipController`:
- Targets an `NiTexturingProperty`, animates the texture pointer on
  one map slot. Shader-map slots via offset-encoded index:
  `affectedMap < 1024` selects standard map slots; `≥ 1024` selects
  shader maps at index `affectedMap - 1024`.
- Holds an array of smart pointers to `NiTexture` (one per frame).
- Legacy timing (< 10.1.0.104): two floats — `startTime` (frame 0)
  and `secondsPerFrame` (uniform). Loader synthesizes step-keyed
  float keys: one per frame plus a duplicate final key for endpoint
  stability.
- Modern timing: explicit `NiFloatInterpolator` with user keys.
- Pinning: index is `clamp(interp + 0.01f, 0, count - 1)` — the
  0.01 fudge rounds down correctly. Out-of-range sticks to last
  frame.

`NiPathController` + `NiPathData`:
- Path: `NiPosData` (position keys forming the path shape, typically
  TCB or BEZIER) plus a separate `NiFloatData` (percentage-traversed
  curve). Two key arrays drive one animation: path geometry and
  parameterization.
- Orientation fields: `AllowFlip`, `Follow` (orient to tangent),
  `FollowAxis` (i16, signed X/Y/Z), `Flip`, `ConstVelocity`
  (reparameterize for constant speed via arc-length lookup),
  `Smoothing` (float scalar), `CurveTypeOpen` (open vs closed loop).
- Banking: `Bank` (bool), `BankDir` (enum NEGATIVE/POSITIVE),
  `MaxBankAngle` (radians).
- Modern equivalent: `NiPathInterpolator` driving a
  `NiTransformController`. Post-process function does the rebinding.

`NiLookAtController`:
- Targets any `NiAVObject`; orients to face a separate `NiAVObject`
  "look-at target" stored as a raw pointer.
- Axis selector enum: X, Y, Z.
- Flip boolean inverts orientation.
- Up-vector not stored — implementation uses world up implicitly (or
  the controlled object's own up axis depending on config; the
  look-at code lives in the interpolator, not the controller).
- Cycles broken arbitrarily by traversal order.

`NiColorController` does not appear as a discrete class in this SDK
— functionality is in `NiPoint3InterpController` subclasses, mainly
`NiMaterialColorController` and `NiLightColorController`.

`NiGeomMorpherController` + `NiMorphData`:
- Blends a set of morph targets (each is a per-vertex `NiPoint3`
  array) by per-target weights coming from per-target
  `NiInterpolator`s.
- `NiMorphData::GetRelativeTargets()`: when false, each target is an
  absolute vertex set and the result is `Σ wᵢ · targetᵢ`. When true,
  target[0] is the base mesh and others are offsets: `target[0] +
  Σ_{i≥1} wᵢ · targetᵢ`.
- No documented weight renormalization — application is responsible.

### 6.9 Old-to-modern mapping summary

| Legacy class | Modern class(es) | Cardinality | Where converted |
| --- | --- | --- | --- |
| `NiKeyframeController` | `NiTransformController` + `NiTransformInterpolator` | 1:1 | RTTI alias + LoadBinary version branch |
| `NiKeyframeData` | `NiTransformData` | 1:1 (rename) | RTTI alias |
| `NiVisData` | `NiBoolData` | 1:1 (rename) | RTTI alias |
| `NiVisController` | `NiVisController` + `NiBoolInterpolator` | 1:1 (wrap) | LinkObject version branch |
| `NiAlphaController` | `NiAlphaController` + `NiFloatInterpolator` | 1:1 (wrap) | LinkObject version branch |
| `NiMaterialColorController` | + `NiPoint3Interpolator` | 1:1 (wrap + flag-bit reshuffle) | LoadBinary version branch |
| `NiLightColorController` | + `NiPoint3Interpolator` | 1:1 (wrap) | LoadBinary version branch |
| `NiFlipController` | + synthesized `NiFloatInterpolator` (step keys from start+rate) | 1:N (synthesizes keys) | LoadBinary version branch |
| `NiUVController` | `NiUVController` (deprecated, kept) / `NiTextureTransformController` for new content | 1:1 (no conversion) | none |
| `NiLookAtController` | `NiTransformController` + `NiLookAtInterpolator` (+ optional pos/scale side interps) | N:1 (combines with existing transform ctlr) | post-process function |
| `NiRollController` | Roll sub-interpolator on `NiLookAtInterpolator` | N:1 (folded; dropped if no look-at) | post-process function |
| `NiPathController` | `NiTransformController` + `NiPathInterpolator` | 1:1 (field copy) | post-process function |
| `NiSequence` (helper-container) | `NiSequence` (native) | 1:1 (helper assembly) | KF load |
| `NiKeyframeManager` (old layout) | `NiKeyframeManager` (link-ID layout) | 1:1 | LoadBinary/LinkObject version branch |

**Irreversible losses:**
- `NiRollController` without a sibling `NiLookAtController` is dropped
  silently.
- `NiFlipController` step-key synthesis discards `startTime` /
  `secondsPerFrame` — cannot round-trip.
- Pre-10.1.0.109: "manager-controlled" bit is forcibly cleared.

### 6.10 Recommended reimplementation strategy

- Implement only the modern data classes (`NiTransformData`,
  `NiBoolData`, etc.).
- In the loader, register class-name aliases:
  `"NiKeyframeController"` → `NiTransformController` factory,
  `"NiKeyframeData"` → `NiTransformData` factory,
  `"NiVisData"` → `NiBoolData` factory.
- In each modern class's body reader, version-gate on ≥ 10.1.0.104
  to decide modern vs legacy field layout.
- Implement the small post-process function for the three controllers
  needing topology fixup.
- Don't implement `NiKeyframeController` or `NiKeyframeData` as
  distinct classes — they don't exist as classes in the modern SDK
  either.

### 6.11 Text keys

**`NiTextKeyExtraData`** stores an array of `NiTextKey` (time + string).
Documented mechanism for attaching named markers to an animation
timeline.

**Tag string interpretation is entirely application-defined.** The
converter looks for **zero** literal text-key strings. The SDK does
not specify a standard vocabulary like "start", "end", "soundN",
"loopN". Anything else (BC's `"sound:..."` or `"event:fire"`) is up
to the game runtime.

The closest thing to a "documented convention" is the controller-
identifier strings used by `NiMaterialColorController` (`"AMB"`,
`"DIFF"`, `"SPEC"`, `"SELF_ILLUM"`) and `NiFlipController` (a
decimal-encoded map index) via `GetCtlrID()` — used at sequence
rebinding time to disambiguate "which of the four material-color
controllers on this node is this sequence interpolator for". These
are controller metadata, not text keys.

### 6.12 Resampling and compression

Animation curves are **evaluated at original key density at runtime**
— no documented load-time resample to a fixed rate. The offline
animation-compression tool (`NiAnimationCompression` library) can fit
B-spline or reduce keys before NIF export; at runtime the data is
whatever the exporter produced.

No documented inverse-kinematics in Gamebryo 1.2 core; IK appears in
later Gamebryo versions / third-party plugins.

---

## 7. Skinning

### 7.1 NiSkinInstance

Instance-dependent, attached to an `NiGeometry`. Fields:
- Pointer to a shared `NiSkinData`.
- Root-parent reference (the `NiAVObject` parent of the bone hierarchy
  root — the bind-pose reference frame).
- Array of `NiAVObject*` bones, one per skin influence — **raw
  pointers, not smart pointers**.
- Optional `NiSkinPartition` pointer for hardware skinning.

Manual skinning APIs exist for apps that want to compute deformed
positions on the CPU explicitly.

### 7.2 NiSkinData

- Number of bones.
- `BoneData` array, one per bone, each containing:
  - `m_kSkinToBone` — `NiTransform`. **Skin-to-bone** bind-pose
    transform (the inverse-bind matrix). Applying it brings a
    mesh-space vertex into the bone's local space at bind time. The
    transform direction is bone-local space (not skeleton-root, not
    world).
  - `m_kBound` — per-bone bounding sphere from vertices that bone
    influences. Used for culling skinned geometry without fully
    evaluating skinning.
  - `BoneVertData[]` — explicit (vertex-index, weight) pairs.
- `m_kRootParentToSkin` — `NiTransform` from root-parent space into
  the skinned mesh's space at bind time.

### 7.3 Vertex weights

Stored **per-bone**: each bone's `BoneVertData` array carries explicit
(vertex-index, weight) pairs. **No fixed cap on influences per vertex
at the format level** — a vertex can appear in arbitrarily many
bones' weight lists. The list is terminated by an explicit count
(each bone carries the count of vertices it influences).

**Runtime does not renormalize weights** — the format stores them
as-exported. Exporters normalize before writing. If weights don't sum
to 1, the deformed vertex scales anomalously. The optional "skin
threshold" used at export drops below-threshold influences and
re-normalizes survivors before writing.

### 7.4 Skinning math

Linear-blend skinning:
```
v_world = Σᵢ wᵢ · (B_iᵀ · S_i · v_skin)
```

where `v_skin` is the bind-pose mesh-space vertex, `S_i` is bone i's
skin-to-bone (inverse-bind), `B_iᵀ` is bone i's current world
transform. Per-bone matrix `B_iᵀ · S_i` composes
skin-space-to-current-world. The `RootParentToSkin` factor adjusts
for the root parent's transform in mesh-local space, applied once.

**Normals** under skinning are recomputed using the same per-bone
matrices used for positions. For pure rotation + uniform-scale bones
(the Gamebryo transform model), the inverse-transpose collapses to
the forward transform — so the engine reuses the position matrix.
Non-uniform scale would break this, which is part of why the
transform model restricts scale to uniform.

Dual-quaternion skinning is not in Gamebryo 1.2 — linear-blend only.

### 7.5 NiSkinPartition (hardware skinning)

Internal-only optimization class (no supported constructors or member
functions for app use). Partitions the triangle list into subsets
such that all triangles in a subset reference at most
`bonesPerPartition` distinct bones. Each partition has its own
bone-palette and (possibly reindexed) vertex/triangle data. The
renderer iterates partitions, sets the bone-palette uniforms, and
draws each.

`bonesPerPartition` is a **build-time** choice passed to
`MakePartitions`. Export tools default to **4** (DX8/Xbox
fixed-function matrix-palette limit) — **[hardware-era]**. Higher
values supported with a custom palette-skinning vertex shader, up to
~20+. **[hardware-era]** for the default; **[runtime-architectural]**
for the partitioning scheme itself (`NiSkinPartition` is required for
hardware skinning regardless of bone count).

---

## 8. Particles

### 8.1 Two systems — which BC uses

- **Old particle** (pre-Gamebryo 1.1, kept in `NiOldParticle`): what
  BC uses. Single `NiParticleSystemController` doing everything,
  three parallel linked lists of modifiers.
- **Modern `NiPSys*`** (Gamebryo 1.1+): modular emitter/modifier
  pipeline. The forward-conversion tool (`NiOldParticleConversion`)
  is in a **separate tool library**, not the engine core — an
  application that doesn't link it leaves old particles as old and
  runs them via `NiOldParticle`. BC almost certainly never converted.

### 8.2 Old-particle architecture

The system is a single class with three parallel linked lists:
- `m_spEmitterModifiers` — emitter-state modifiers (frame-level, not
  per-particle).
- `m_spParticleModifiers` — per-particle modifiers (color, grow/fade,
  gravity, bomb, rotation).
- `m_spParticleColliders` — collision response.

Each chain is singly-linked. **Modifier ordering is significant** and
is **chain-insertion-order**. There is no priority and no
category-grouping within a chain (but chains themselves are inherently
category-grouped). Modifiers are *prepended* on attach (`SetTarget`
calls `AddToTarget` which prepends), so iteration order is
**reverse-of-attach** — BC's content effectively encodes "later-
attached modifier runs first."

Per-particle state is **hybrid SoA + AoS split across two objects**:
- **The controller** owns an AoS array of `NiPerParticleData`
  (7 fields, see below), sized at capacity.
- **The target `NiParticlesData`** (geometry-data subclass) owns
  parallel SoA arrays: positions, normals, colors, radii, sizes, and
  (for mesh particles) rotation quaternions. Sized at capacity too.
- A particle's `m_usIndex` bridges: the vertex-array slot it owns.

This split is why rendering is cheap — the renderer reads
`NiParticlesData`'s vertex array directly without touching the
controller.

### 8.3 NiPerParticleData

Exactly seven fields:
- `m_kVelocity` — `NiPoint3`. Linear velocity vector.
- `m_kRotationAxis` — `NiPoint3`. Used only by `NiParticleRotation`
  for mesh particles.
- `m_fAge` — float. Time since spawn.
- `m_fLifeSpan` — float. Death threshold.
- `m_fLastUpdate` — float. Scaled time of previous update; used to
  compute delta-time for velocity-dependent forces.
- `m_usGeneration` — u16. How many spawn cascades deep.
- `m_usIndex` — u16. Slot in `NiParticlesData`.

Fields **not** stored here (live in `NiParticlesData`): position,
color, normal, radius, size, rotation quaternion.

All per-particle state is in the **target `NiParticles` object's
model-local space** — the same space as the target's `NiAVObject`
transform. Moving the target node moves all its particles.

**Alive-vs-dead is implicit via the active count.**
`m_usNumActiveParticles` names how many slots at the front of the
array are alive; everything from that index up to capacity is stale.
No explicit alive flag, no sentinel age. On death, the dying
particle's slot is overwritten with the last active particle's data
and active count decrements (swap-and-pop). The killed particle's
`NiParticlesData` vertex slot is reused for the swapped-in particle.

### 8.4 Memory and capacity

**Fixed pool with reuse.** Capacity is
`NiParticles::GetVertexCount()` — i.e., the number of vertex slots
in the underlying particle geometry. Sized once at `SetTarget` time.

Cap: **[structural]** — capacity is encoded into the NIF as the
vertex count of the particle geometry. Runtime cannot grow it.

Each `NiParticleSystemController` is self-contained — no global
old-particle manager. Only the global stream-loader registry is
shared.

### 8.5 NiParticleSystemController fields

Beyond base `NiTimeController`:
- **Velocity defaults**: mean speed + variance; mean declination +
  variance; mean planar angle + variance (radians).
- **Initial visual state**: normal direction (`NiPoint3`), color
  (`NiColorA`), size scalar.
- **Emit gating**: emit-start time, emit-stop time, reset flag.
- **Birth/death**: birth rate (used if `useBirthRate=true`), lifespan
  mean + variance, `useBirthRate` bool, `spawnOnDeath` bool.
- **Emitter volume**: width, height, depth (box in emitter local
  space — emitters are **always boxes** in the old system).
- **Emitter reference**: raw pointer to an `NiAVObject` whose
  transform defines emitter location/orientation in world.
- **Spawn-cascade params**: generation cap (u16), spawn percentage
  (chance per death), spawn multiplier (count per spawn event),
  speed chaos, direction chaos.
- **State**: total capacity, active count, current iteration cursor,
  pointer to per-particle state array.
- **Modifier chain heads**: smart pointers to first of each chain.
- **Bounding**: static-bound flag + cached static model bound.
- **Bookkeeping**: scaled last-time, last-emit time, first-time flag.

Birth rate gating: if `useBirthRate=true`, use the explicit field
(particles/sec). Otherwise compute implicitly as
`capacity / (emitStop - emitStart)` if `lifespan ≥ animation cycle
length`, or `capacity / lifespan` otherwise.

Per-particle lifespan: `lifespan + lifeSpanVar · (uniformRandom - 0.5)`
— uniform in [-0.5, 0.5] scaled by variance. So variance is "total
spread" not stddev.

Initial velocity at spawn:
- Speed: `speed + speedVar · (uniformRandom - 0.5)`.
- Direction: spherical from `(dec ± decVar, planar ± planarVar)` with
  symmetric [-1, +1] random.
- Result: `velocity = speed · sphericalToCartesian(dec, planar)`.
- In **target-local space** by default; if emitter object set,
  rotated through emitter→target transform.

Initial color and size are single fields on the controller (no
per-channel variance, no random distribution). Color/size evolve
over lifetime via the color and grow/fade modifiers.

Random numbers come from **global engine helpers** (`NiUnitRandom`,
`NiSymmetricRandom`). The controller carries no seed — BC's particle
systems are **not reproducible frame-to-frame across sessions** (a
save/load with active particles will diverge in spawn random rolls).
**[runtime-architectural]** — a clean-room reimpl can make this
per-system.

### 8.6 Per-frame data flow

`NiParticleSystemController::Update(time)`:
1. Standard `NiTimeController` time-scaling produces `scaledTime`.
2. If `scaledTime < lastFrame's scaledTime` and reset flag is set,
   clear (active → 0, first-time flag re-set).
3. **Emitter modifier chain** updated first.
4. On first call ever, a **run-up loop** pre-simulates the system at
   **30 fps** (0.0333…) from emit-start to current time so the
   system isn't empty when first shown.
5. `UpdateParticles(scaledTime)`:
   - Computes wrap-around time modifier if `scaledTime` looped
     backward.
   - For each active particle:
     - Advance age.
     - If `age ≥ lifespan`: optional spawn-on-death cascade, then
       remove (swap with last, decrement count).
     - Else: apply **particle modifier chain** (each modifier mutates
       per-particle state and/or vertex slot, then forwards).
     - **Collider chain** finds earliest collision in frame; if hit,
       collider's `Update` resolves response (may kill).
     - Integrate position: `pos += velocity · (frameEnd -
       collisionTime)` — so position update happens **after**
       collision response.
   - **Emit new particles**: birth budget from rate (or implicit),
     `AddNewParticle` loop up to capacity.
   - Recompute model bound (live or static-precomputed).
6. Mark target's vertex/normal/color arrays as changed so the
   renderer repacks.

### 8.7 Spawn detail

`AddNewParticle`:
1. Locate next slot at `m_usNumActiveParticles`.
2. Assign vertex-data index = current active count; increment.
3. **First-generation** (no parent):
   - Random age in `[0, frameDelta]` — small head-start so spawns
     don't visibly emerge in lockstep.
   - Speed: `speed + speedVar · (uniform - 0.5)`.
   - Direction: spherical from declination/planar.
   - Position: random within box `[-w/2,w/2] × [-h/2,h/2] × [-d/2,d/2]`.
   - If emitter object set, rotate direction and offset position by
     emitter→target transform.
   - Lifespan: as above.
   - Generation: 0.
   - Rotation axis: (1, 0, 0) default.
   - Vertex/normal/color/radius/size in `NiParticlesData`: controller
     defaults.
4. **Death-cascade** (parent particle):
   - Age from spawn-time delta (not random).
   - Speed perturbed by `speedChaos` factor from parent.
   - Direction perturbed by `dirChaos` cone from parent.
   - Lifespan: same formula.
   - Generation: parent + 1.
   - Rotation axis: copied from parent.
   - Vertex/normal/color/radius/size: copied from parent.
5. `m_fLastUpdate` set to `currentTime - age`.
6. Walk modifier chain's `Initialize` on the new particle.

### 8.8 Per-frame particle update

`ParticleUpdate`:
1. Advance age by `frameEnd - lastTimeStep`.
2. If `age > lifespan`: optional cascade, then `RemoveParticle`,
   return.
3. Walk **particle-modifier chain** — each modifier runs `Update`,
   mutating state.
4. Walk **collider chain** via `Resolve` for earliest collision. If
   hit, collider's `Update` reflects velocity; if returns false
   (die-on-collide), bail out.
5. **Integrate position**: `pos[m_usIndex] += velocity · (frameEnd -
   collisionTime)` (full step if no collision; post-collision sub-step
   otherwise — pre-collision motion was done in `Resolve`).
6. Update `m_fLastUpdate`.

Death triggers: age threshold, collision (collider returns false), or
system reset (time wrapped backward + reset flag). Slot reuse is
**immediate** — swap-and-pop; the iteration cursor is decremented
so the swapped-in particle gets visited this frame. No deferred
death list, no two-phase mark-then-sweep. Slot state is
**overwritten, not zeroed** on reuse.

### 8.9 Modifier classes — field-by-field

**`NiParticleModifier`** (base):
- Fields: smart pointer to next (`m_spNext`), raw pointer to owning
  controller (`m_pkTarget`).
- Virtual: `Update(time, particle) → bool` (true = stays alive, false
  = killed); `Initialize(particle)` runs once on spawn.
- Subclass contract: override `Update` for per-frame per-particle
  mutation, chain to base to forward.

**`NiEmitterModifier`** (base):
- **NOT a shape source.** The basic emitter shape is **fixed as a
  box** in the controller. `NiEmitterModifier::Update` runs once per
  frame, not per particle. Subclasses animate emitter parameters
  over time (changing emit rate, dimensions, etc.).
- The old SDK ships **zero concrete `NiEmitterModifier` subclasses**
  — BC almost certainly uses custom emitter modifiers for engine
  washes, weapon-impact bursts, etc.
- Initial particle state setup is handled entirely by the controller
  in `AddNewParticle`, not delegated.
- Birth rate, spawn budget on the controller, not on emitter
  modifiers.
- No stock "burst" mode — achievable by attaching a modifier that
  adjusts birth rate over a short interval.

Cap: emitter is hardcoded box-shaped. **[structural]** — sphere/mesh
emitter shapes in old-particle BC content would require a custom
emitter modifier that reshapes particles after spawn, or BC custom
logic on top.

**`NiGravity`**:
- Mode enum: `FORCE_PLANAR` (uniform directional, optionally
  distance-attenuated through a plane), `FORCE_SPHERICAL` (radial
  from/towards a point).
- Fields: decay (exponential decay rate; 0 = no decay), strength
  (units/sec²), mode enum, position vector, direction vector.
- Planar update: `velocity += direction · exp(-decay · projDist) ·
  strength · 1.6 · deltaT` where projDist is particle distance from
  position projected along direction.
- Spherical update: `velocity += (position - particlePos)norm ·
  exp(-decay · dist) · strength · 1.6 · deltaT`. Negative strength
  pushes.
- **The 1.6 factor** is a magic units-conversion constant.

**`NiParticleBomb`**:
- Trigger: time window (`m_fStart`, `m_fDuration`).
- DecayType enum: NONE, LINEAR, EXPONENTIAL.
- SymmType enum: SPHERICAL, CYLINDRICAL, PLANAR.
- Fields: decay, delta-V magnitude (kick applied at bomb), duration,
  start time, decay type, symmetry type, position, direction.
- Mutates per-particle velocity (additive impulse).
- Conversion to modern: encodes active-time window as boolean
  step-key sequence on `NiPSysModifierActiveCtlr` — mirrors as
  `(true at start, false at start+duration)`.

**`NiParticleCollider`** (base):
- Fields: bounce scalar (restitution), spawn-on-collide bool,
  die-on-collide bool, cached collision point, cached collision
  time.
- Virtual contract: `Resolve(initialTime, &collisionTime, particle)`
  scans collider geometry for trajectory intersection within the
  time interval, returns pointer to self if hit. `Update(time,
  particle)` applies response: reflects velocity with bounce,
  optionally spawns cascade, optionally kills.
- **No separate friction parameter** — bounce is the only response
  coefficient. Velocity along surface preserved; into-surface
  velocity reflected and scaled by bounce.
- Colliders live on their own chain. **Only the first collider
  returning a hit is acted on per frame per particle** (code comment
  notes "Potential for multiple collisions?" as a known limitation).

**`NiPlanarCollider`**:
- Plane representation: `NiPlane` (normal + signed distance) plus
  position, X-axis vector, Y-axis vector — defining a finite
  **rectangular patch**.
- Bounds: width, height (extents along X/Y from position).
- **One-sided**: responds to particles approaching from positive-
  normal side; particles passing from behind are not stopped.

**`NiSphericalCollider`**:
- Sphere: position + radius (and cached squared radius for fast
  tests).
- Treated as solid boundary — particles outside that try to enter
  get bounced/stopped. Inside-only mode is not an explicit switch.

**`NiParticleColorModifier`**:
- Color-over-lifetime: smart pointer to `NiColorData` block carrying
  `NiColorKey` array (any of LIN/BEZ/TCB/STEP).
- Key count: no fixed limit (`u32`).
- Time normalization: clamps particle age to `[m_fLoKeyTime,
  m_fHiKeyTime]` (data block's actual timestamp range) before
  interpolating. Key times are **absolute scaled-time-style values**,
  not auto-mapped to [0, 1].
- Writes interpolated color into particle's color slot, clamped to
  [0, 1] per channel.

**`NiParticleGrowFade`**:
- Fields: `growFor` (seconds at start for size 0→1) and `fadeFor`
  (seconds at end for size 1→0).
- Grow ramp applies **only to first-generation particles**.
- Fade ramp applies **only to last-generation particles** (where
  generation equals controller's `m_usNumGenerations`).
- Mid-generation particles stay at size 1.0.
- Final scale: `min(grow, fade)`, clamped to at least epsilon.
- No key array — just two scalars.

**`NiParticleMeshModifier`**:
- Meshes: array of smart pointers to `NiAVObject` (typically
  `NiTriShape`).
- Per-particle mesh assignment: each particle uses mesh at index
  `m_usIndex % meshCount` (round-robin).
- On spawn: assigns mesh to particle's slot in
  `NiParticleMeshesData`.
- Scale evolution: standard per-particle size from `NiParticlesData`;
  renderer multiplies mesh by that scale.
- Mesh count bounded by `NiTArray` size (32-bit). **[structural —
  generous]**.

**`NiParticleRotation`**:
- Per-particle: rotation axis (in `NiPerParticleData`).
- Modifier fields: random-initial-axis flag, initial axis vector
  (used when random is off), rotation speed (rad/sec).
- On spawn: if `m_bRandomInitialAxis`, uniform random unit vector;
  else stored initial axis.
- Each update: writes fresh quaternion `quat(axis = particle.axis,
  angle = age · speed)` into particle's rotation slot.
- **Caveat**: for non-mesh particles, this modifier is **silently
  stripped at load time** (a `REMOVE_UNUSED_ROTATIONS` block in
  `PostLinkObject`, code-dated "Ni4.0 final release, 4/30/2001",
  removes them because the renderer never honored rotation for
  billboard particles). BC's billboard particles never rotate via
  this modifier — visible rotation must come from animated textures
  (`NiFlipController`) or BC-custom logic.

The complete old-particle modifier set: `NiGravity`,
`NiParticleBomb`, `NiParticleCollider` (base) + `NiPlanarCollider` +
`NiSphericalCollider`, `NiParticleColorModifier`,
`NiParticleGrowFade`, `NiParticleMeshModifier`,
`NiParticleRotation`. Eight concrete classes, three abstract bases.

### 8.10 NiAutoNormalParticles, NiRotatingParticles

Not present by name in this SDK's main library — the modern
`NiParticles` / `NiParticleMeshes` / `NiParticleMeshesData` /
`NiParticlesData` have absorbed the older renderable particle types.
When a NIF contains `"NiAutoNormalParticles"` or
`"NiRotatingParticles"`, they load as the modern equivalents via
RTTI aliasing. Distinguishing original semantics:
- **`NiAutoNormalParticles`**: each particle's normal is automatically
  recomputed each frame to face camera (lit billboard particles —
  sparks, glow points).
- **`NiRotatingParticles`**: each particle has its own rotation state
  (axis + angle, evolved by `NiParticleRotation`) — spinning sparks,
  flame puffs.

Both derive from `NiParticles` → `NiTriBasedGeom` (they ARE
triangle-based geometry, rendered differently — the choice is in the
particle-specific draw path).

### 8.11 Rendering

For non-mesh particles, billboard orientation is implicit in the
renderer: each particle position is the center of a screen-aligned
quad sized by the particle's `radius` (from `NiParticlesData`'s
radii array). Corners are generated in view-space so the quad is
always camera-facing. The per-particle normal (for lit billboards)
is recomputed in `NiAutoNormalParticles` semantics as
`normal = normalize(cameraPos - particlePos)`.

The renderer iterates `NiParticlesData`'s vertex array directly
through `GetActiveVertexCount()` — it does not touch the controller's
per-particle state. Marking vertex/normal/color arrays as changed
each frame is sufficient — the renderer regenerates per-quad
vertices.

**No documented sort within a particle set.** Particles render in
slot order (insertion-order, with swap-on-death scrambling). If the
particle set's enclosing `NiAVObject` has alpha blending on, the
whole set is back-to-front-sorted by its bounding-sphere center
against other alpha objects — but per-particle sorting is not done.
Dense alpha particle systems show visible draw-order artifacts
inside the cloud.

Particle nodes are normal `NiTriBasedGeom` descendants carrying the
full property stack — `NiAlphaProperty`, `NiTexturingProperty`,
`NiMaterialProperty`, `NiZBufferProperty`. Renderer honors them
identically to ordinary geometry. Typical BC particle config:
alpha-blend on with `ALPHA_SRCALPHA`/`ALPHA_ONE` (additive) for
emissive effects, Z-test on with Z-write off.

**Mesh particles render with one draw call per particle** — no
instancing in the fixed-function pipeline of the era. The renderer
iterates particles and emits a draw call against the assigned mesh
per particle. Expensive for dense mesh-particle systems — one of the
reasons the modern particle system was introduced.

### 8.12 Modern particle system (post-BC)

For reference: `NiParticleSystem` is composed of an emitter
(`NiPSysEmitter` subclasses: `NiPSysSphereEmitter`,
`NiPSysBoxEmitter`, `NiPSysCylinderEmitter`, `NiPSysMeshEmitter`),
modifiers (force, age, collision, color, size, mesh-update,
bound-update), and a renderer behaviour. `NiPSysData` holds
per-particle state arrays. Particle controllers
(`NiPSysEmitterCtlr`, `NiPSysUpdateCtlr`, modifier-active
controllers) drive parameters over time.

Force modifiers: `NiPSysGravityModifier`, `NiPSysDragModifier`,
`NiPSysAirFieldModifier`, `NiPSysTurbulenceFieldModifier`,
`NiPSysVortexFieldModifier`. Each can have its own strength
controller.

Colliders: `NiPSysPlanarCollider`, `NiPSysSphericalCollider`.
Arbitrary mesh collision is not stock.

No stock ribbon/trail primitive in Gamebryo 1.2 distinct from the
mesh-particle path.

---

## 9. Collision

Native (pre-Havok) collision is in the `NiCollision` library. Two
parallel systems:

- **Alternate Bounding Volumes** (`NiSphereBV`, `NiBoxBV`,
  `NiCapsuleBV`, `NiUnionBV`, `NiOBBNode`, `NiOBBRoot`, `NiOBBLeaf`)
  attached to scene graph nodes via `NiCollisionObject`.
- **Triangle-level intersection** primitives (`NiTriIntersect`,
  `NiTrigon`, `NiSegment`) used directly or via collision groups.
- **Picking** (`NiPick`) for ray queries against the scene graph,
  returning `NiPick::Record` entries.

Primitive shapes: sphere (`NiSphere`, `NiSphereBV`), box/OBB
(`NiBox`, `NiBoxBV`, `NiOBBLeaf`), capsule (`NiCapsule`,
`NiCapsuleBV`), triangle (`NiTrigon`). AABB is used implicitly via
bounding-sphere conversion, not a first-class primitive.

Mesh collision uses **OBB tree acceleration**: `NiOBBRoot` builds a
tree of OBBs; `NiOBBLeaf` holds per-triangle data. Triangle-to-
triangle queries traverse the hierarchy. Per-triangle linear scan is
available via `NiTriIntersect` for small meshes.

Supported queries:
- **Ray** (`NiPick::PickObjects` / `PickAll`).
- **Static intersect** (`NiCollisionGroup::TestCollisions` — boolean
  overlap, current configuration).
- **Dynamic intersect** (`NiCollisionGroup::FindCollisions` — sweep
  over time interval, with point/normal of collision).
- **Bound-to-bound** (`NiBound::TestIntersect` / `FindIntersect`).

No explicit "trigger / sensor" concept distinct from solid collision
in the core API. An application uses a callback on a normal query
and ignores the response.

Dynamic collision is the CCD path for `NiBound` and
`NiCollisionGroup::FindCollisions` — predictive collision over a
time interval. Full continuous mesh CCD is not documented.

---

## 10. Math and coordinate conventions

- **Coordinate system**: right-handed.
- **Up axis**: no fixed engine-level up. The docs explicitly say
  Gamebryo makes no requirements about world-space up. The billboard
  up-axis is model-space [0,1,0] *for the billboard itself*. In
  practice, exported content is typically Y-up (3ds max default) or
  Z-up (Maya default).
- **Forward axis**: **+X** for both directional lights and spotlights
  (light shines down model-space +X). The camera looks down **-Z in
  its local frame** with camera Up = local +Y and Right = local +X.
  `NiCamera::Click` stores `m_kWorldDir` (forward), `m_kWorldUp`,
  `m_kWorldRight` from the camera's world transform.
- **Matrices** (`NiMatrix3`) stored as `m_pEntry[3][3]` row-major C
  array layout. Math is **column-vector**: `v' = M · v`, parent ·
  local is left-multiplication. So a matrix's columns are the basis
  vectors of the transformed frame.
- **Quaternion** (`NiQuaternion`) member layout: `m_fW`, `m_fX`,
  `m_fY`, `m_fZ` — **W first**. Streamed in this same order. (Some
  downstream tools reorder to XYZW; the engine itself is W-first.)
- **Quaternion-to-matrix**: standard formula for a right-handed,
  column-vector system on a unit quaternion. A positive rotation
  about an axis is "clockwise looking down the axis toward the
  origin" per the docs — equivalent to the standard right-hand rule
  with the viewing-direction caveat.
- **Euler ordering** in `NiEulerRotKey`: **XYZ** (rotate X, then Y,
  then Z, composed left-to-right in column-vector sense). Units
  **radians**.
- **Units**: **application-defined**. The engine has no documented
  unit convention; commonly "1 unit = 1 meter" (Max default) or
  game-specific.

`NiCamera` frustum specified as **L, R, T, B, N, F + ortho flag**
(asymmetric perspective frustum permitted; orthographic requires
symmetric top/bottom and left/right per a runtime assertion).
Defaults: (-0.5, 0.5, 0.5, -0.5, 1.0, 2.0), ortho=false. Viewport
("port") is L,R,T,B in normalized [0..1] screen coordinates, default
(0, 1, 1, 0). Near/far are positive; engine enforces a minimum near
plane (default 0.1).

No documented "center of geometry" or "pivot offset" field on
`NiAVObject` distinct from the node origin. The application stores
this externally (e.g., as `NiVectorExtraData`).

Math library types worth knowing about:
- `NiTransform` — combined T + R + scalar S. Most controllers
  operate on this struct.
- `NiQuatTransform` — same with `NiQuaternion` in place of
  `NiMatrix3`. Used by modern animation (`NiTransformInterpolator`
  outputs this).
- `NiBound` — bounding sphere with stale-flag.
- `NiFrustum` — L, R, T, B, N, F, ortho-bool.
- `NiPlane`, `NiSegment`, `NiTrigon`, `NiBox`, `NiSphere`,
  `NiCapsule`, `NiParallelogram` — collision primitives.
- `NiSqrDistance` — squared-distance functions between every
  primitive pair.
- `NiMath` — static math utilities (line-plane intersection,
  closest-point queries).

`NiPoint3` is three contiguous floats `x, y, z` with no SIMD padding
by default; a data-alignment macro is used in places like
`NiQuaternion` (16-byte aligned) where SIMD benefits.

---

## 11. Resource management and lifetime

### 11.1 Reference counting

Via **`NiPointer<T>` smart pointers** wrapping `NiRefObject`-derived
classes. Auto-increment on assignment, auto-decrement on
destruction; refcount=0 → self-delete. Raw pointer fields are
non-owning. Convention: each ref-counted class has a `T*Ptr` typedef.

Cross-block references follow this in memory: a child
`NiAVObject*` stored in `NiNode` is held via smart pointer (so the
node owns its children); a target `NiAVObject*` stored in a
`NiTimeController` is raw (so the controller doesn't retain its
target). On-disk these distinctions vanish — both are just link IDs.

**Cleanup is refcount-driven**: when the application releases its
last smart pointer to a subtree root, the destructor cascades. Leaf-
first by consequence; no manual ordering required.

### 11.2 Cloning

Three documented copy modes for `NiObject`:
- **`Clone()`** — smart clone: structural copy of scene graph,
  "shareable" objects (`NiGeometryData`, `NiSkinData`,
  `NiSourceTexture`, `NiMorphData`) shared by smart pointer, not
  duplicated. Use for instancing a character or model.
- **`CreateDeepCopy()`** — stream the object to a memory buffer,
  then stream it back as new objects. Everything duplicated, no
  sharing. Use when you need an independent copy (e.g., to mutate
  one instance's vertex data without affecting others).
- **Name-copy policy** (global static):
  - `COPY_UNIQUE` (default) — appends a single character to keep
    `GetObjectByName` working.
  - `COPY_EXACT` — keeps names identical (needed for animation
    sequences to bind to clones).
  - `COPY_NONE` — clears names.
  - `NiControllerManager` docs specifically warn to set `COPY_EXACT`
    before cloning anything that animation sequences will retarget
    to.

For BC ship instancing: use shallow `Clone()` with `COPY_EXACT` so
animations keep working.

### 11.3 Lifecycle rules

**Do not create static or stack-allocated `NiRefObject`-derived
objects.** Reasons:
- Refcount lifetime expects heap allocation.
- Engine has explicit `NiInit()` / `NiShutdown()` boundaries; statics
  could be destroyed after shutdown.
- Runtime is designed to detect leaks post-`NiShutdown` and would
  flag pre-main allocations.

A clean-room reimpl can ignore this rule (use RAII / heap
exclusively / ARC-style refcount as preferred).

### 11.4 Custom allocators, streaming load

Custom allocator hooks exist via `NiTAbstractPoolAllocator`,
`NiTDefaultAllocator`, `NiTPointerAllocator`, `NiTPool` template
family — per-container allocators, not a global new/delete override.
Global allocator replacement happens at platform level.

Asynchronous / streaming load **is** supported via
`NiStream::BackgroundLoadBegin` with progress polling via
`BackgroundLoadEstimateProgress`. Cooperative — a background loading
state machine processes a bounded amount of work per tick. The
`BackgroundLoad` sample demonstrates.

---

## 12. Runtime pipeline

### 12.1 Per-frame order

Documented framework order:
1. Update input.
2. Process input.
3. `scene->Update(time)` — refresh transforms, tick controllers,
   refresh bounds.
4. `camera->Clear(BACK | Z)`.
5. `camera->Click()` — internally:
   - `BeginPaint`.
   - Start the sorter.
   - `CullShow` (depth-first cull and emit).
   - Finish the sorter (draws deferred alpha objects back-to-front).
   - `EndPaint`.
6. Optional second screen-space camera click for HUD.
7. `camera->SwapBuffers()`.

Pre-render callbacks exist on individual classes:
`NiGeomMorpherController::OnPreDisplay` is the documented hook for
"do work just before draw, after cull decision is made."

Animation evaluation happens **inside** `Update`, before
cull/render. Geometry that responds to animation (skinning, morphing)
finishes vertex computations either in `Update` or in a pre-display
callback.

`UpdateProperties()` and `UpdateEffects()` must be called if the
property/effect stacks changed — they are not run inside `Update`.

### 12.2 Culling

**Hierarchical bounding-sphere vs frustum.** Each node's world-bound
sphere is tested against the six frustum planes; if rejected, the
entire subtree is skipped. If fully inside (all planes pass with
margin), the subtree skips its own plane tests internally — six
"active plane flags" track which planes still need testing.

Portal culling **is** documented via the `NiPortal` library
(`NiPortalNode` and friends). PVS is not in core. Occlusion culling
per se is not a built-in feature; occlusion volumes attach via
`SetDisplayObject` as a hook for third-party occlusion.

### 12.3 Sorting

Default sorter is **`NiAlphaAccumulator`**: as the cull walk visits
each leaf, opaque objects draw immediately at traversal order,
alpha-blended objects register for deferred back-to-front drawing.

- **Opaque** emitted in **traversal order** (front-to-back-ish only by
  virtue of how scenes are typically structured; Z-buffer is doing the
  real visible-surface determination).
- **Alpha-blended** sorted **back-to-front by bounding-sphere center
  depth** (single point per object). Sort key is pure depth, not
  material-aware.
- The **no-sort flag** on `NiAlphaProperty` opts a single object out
  of registration.

Triangles within an object are not sorted relative to each other;
objects with overlapping centers in depth produce ordering tied to
traversal order.

State-change minimization happens internally at the device level —
the default accumulator does not state-sort opaque batches. Custom
`NiAccumulator` subclasses can implement state-sorted opaque
drawing.

`NiSortAdjustNode` allows mid-graph push/pop of the sorter (§2.5).

### 12.4 Multi-viewport

Multiple `NiCamera` objects with different `Port` rectangles set on
the same renderer. The framework's screen-space camera idiom is one
example.

### 12.5 Renderer constraints (BC-era envelope)

- Max **8 simultaneous lights** per object (DX8 fixed-function T&L).
  Renderer drops beyond this with no documented priority.
- Max **8 texture coordinate sets per vertex**.
- Hardware skinning requires `NiSkinPartition` with `bonesPerPartition`
  ≤ 4 by default. Otherwise software skinning (still optimized,
  slower).
- Multitexture stages auto-detected from GPU; combinations exceeding
  single-pass limits split into multiple passes via alpha blending.
  Per-stage state inference is "not currently checking
  compatibility" — artists used conservative combinations to avoid
  driver bugs.
- Renderer expects `NiGeometry`-derived geometry with a per-class
  vertex-buffer cache. `MarkAsChanged` triggers VB repack next frame.
  Morphed and skinned geometry are repacked every frame (slow path).

`NiGeometryGroup` family is the documented batching strategy in
newer Gamebryo (post-BC): explicit application-side hints group
static geometry into shared VBs for fewer state changes.
`NiGeometryGroupManager` handles registration. The DX8/DX9 renderers
consult the group manager when packing VBs.

---

## 13. Extension surface

### 13.1 Registration

The mechanism is the RTTI-name-keyed creation-function map (§1.6).
There is no reserved version range for vendor classes — the format
uses the class name as the key.

### 13.2 Custom properties and controllers

- **Custom properties** subclass `NiProperty`, declare RTTI +
  streaming, override `Update` / `IsEqualFast` as needed. To
  participate in the render pipeline they must also implement
  renderer-side hooks (the renderer queries `NiProperty::GetType()`
  and looks up its handling); custom *renderable* properties require
  renderer-specific changes, while custom *data-carrying* properties
  (no GPU state effect) are easy.
- **Custom controllers** subclass `NiTimeController` (or a typed
  `NiInterpController`), declare RTTI + streaming, implement
  `Update(float)` and `SetTarget` hooks. Same pattern.

### 13.3 NiExtraData

**The canonical extension hook** for attaching app-specific data to
any `NiObjectNET`. Stock subclasses:
- `NiBinaryExtraData` (raw byte blob)
- `NiBooleanExtraData`, `NiIntegerExtraData`, `NiFloatExtraData`,
  `NiColorExtraData`, `NiVectorExtraData`, `NiStringExtraData`
- `NiIntegersExtraData`, `NiFloatsExtraData` (arrays)
- `NiSwitchStringExtraData`
- `NiTextKeyExtraData` (animation markers)

Applications routinely add their own subclasses for engine-specific
per-node data (BC's hit-point markers, weapon-mount points etc.
likely live as custom extra data).

### 13.4 Plugin loading, geometry swap

Plugin/DLL hot-load is not a documented stock feature. Custom-block
registration must run at application startup. The registration API
itself is callable from anywhere — apps that build their own DLL
system can do it.

**Geometry swap** while preserving transform and skinning binding:
1. Replace the `NiGeometryData` on an existing `NiGeometry`
   (position/topology changes; transform/property stack/skinning
   binding does not).
2. Detach/attach `NiGeometry` children of a shared `NiNode` parent.
For skinned geometry, replacing geometry data while keeping the same
`NiSkinInstance` works as long as vertex counts match skin data
expectations.

---

## 14. Audio

The SDK includes `NiAudio` with: `NiAudioSystem`, `NiAudioSource`,
`NiAudioListener`. Plus a Miles Sound System backend (`NiMilesAudio`:
`NiMilesAudioSystem`, `NiMilesSource`, `NiMilesListener`).

**These are runtime objects, not NIF block types.** They do not
appear in NIF files. `NiAudio` is documented as added with Gamebryo;
whether NetImmerse 3.1 (BC era) shipped an equivalent is unclear.

`NiAudioSource` data model: file or buffer reference (format
auto-detected per platform/provider), loop flag, volume, pitch, 3D
positional parameters (position, velocity, min/max distance, cone
angles for directional sources). Position in world space; listener
pose drives spatialization.

`NiTextKeyExtraData` carries arbitrary strings; the audio system has
**no built-in "play this sound on this text key" wiring**. The
application reads the text-key list during animation playback and
fires audio events itself — standard pattern.

**For BC, audio integration is at the application layer.** Don't
expect NIF files to contain audio data.

---

## 15. Tools, samples, diagnostics

### 15.1 Canonical samples

The canonical "load and render a NIF" sample is `Samples/Tutorials/
03 - NIF Files`. Top-level flow:
1. Create renderer (DX8 or DX9 select).
2. Create `NiAlphaAccumulator`; set as renderer's sorter.
3. Create `NiStream`. `Load("WORLD.NIF")`.
4. First top-level object (`GetObjectAt(0)`) cast to `NiNode` — the
   scene root.
5. Recursively walk for an `NiCamera`; bind to renderer.
6. Bind scene root to camera as its scene.
7. `scene->Update(0)`, `scene->UpdateProperties()`,
   `scene->UpdateEffects()`, `camera->Update(0)`.
8. `OnIdle` loop each frame: `Clear`, `Click`, optional screen-space
   pass, `SwapBuffers`.

`NiApplication` wraps the OS message loop and calls `OnIdle` once
per available time slice.

Notable samples:
- **Tutorials**: 01-Basic, 02-Renderers, 03-NIF Files, 04-Scene
  Attachment, 05-Transforms, 06-Time Controllers, 07-User Input,
  08-Screen Texture, 09-Rendered Texture.
- **Demos**: CharacterAnimationDemo, CharacterPerformanceDemo,
  MatrixPaletteSkinning, VertexMorphing, CollisionTestStatic,
  CollisionTestDynamic, MousePicking, ObjectPick, BackgroundLoad,
  ShadowMap, StencilShadow, VertexLightingPipeline, CubeMap,
  AdvancedMultitexture, DynamicTexture, ShaderSample, ProfileSample.
- **Games**: `Samples/Games/MadLab/` and `Samples/Games/Eturnum/` —
  full game-tier sample applications.

### 15.2 SDK tools

- **3ds max plugin** and **Maya plugin** — NIF export, KF export,
  animation manager, switch-node/LOD setup, bone-LOD, optimization.
- **SceneViewer** — NIF browser GUI: scene-graph tree, properties
  inspector, animation playback, controller list, bounds, skin-
  partition counts.
- **AnimationTool** — KF/KFM editor with state-machine view of actor
  sequences.
- **NiPluginToolkit + ArtPlugins** — extension framework for
  third-party tooling.
- Command-line tools under `Tools/DeveloperTools` — optimization,
  stripification, image quantization, animation compression.

No conformance/regression suite with reference NIFs and expected
outputs is documented.

### 15.3 Diagnostics

- **`NiOutputDebugString`** — platform-abstracted debug print used
  throughout for error paths.
- **`NiProfile`** — instrumented profile builds with per-object
  timing (update-down, update-up, render time, frames culled).
- Per-`NiAVObject` profiling counters readable in Profile builds
  (`GetUpdateDownTime`, `GetFramesRendered`, etc.).

Error-handling style mixes return-bool/return-pointer-or-NULL for
soft failures; `assert` for invariant violations (debug only);
per-class `m_uiLastError` + `m_acLastErrorMessage` on `NiStream` for
diagnostic-quality reporting. **No C++ exceptions thrown by stock
engine code.**

Threading model: **the scene graph is not thread-safe; render thread
only touches the scene graph, with caveats.** Property updates have
a static critical section (`LockPropertyUpdate` /
`UnlockPropertyUpdate`). Background NIF loading runs on a worker
thread but synchronizes at the application-visible API boundary.
Textures have a separate threading discussion (uploads can be
deferred). General rule: prepare data on worker threads, mutate
scene graph only on the render thread.

---

## 16. Documentation hooks and NIF version landscape

Top-level docs (`Gamebryo.chm`):
- Welcome to Gamebryo (overview).
- Getting Started (platform bring-up).
- Learning Gamebryo (tutorial walkthroughs).
- **Programmer's Guide** — Programming Basics, Object Systems, Scene
  Graph, Scene Rendering, Texturing, Special Effects, Skinned
  Objects, Content Import/Export, NiShader, NiProfile,
  UpdateSelected/performance, threading, optional features
  (collision, portals, audio).
- **Reference** — class-by-class by library (`NiMain`, `NiAnimation`,
  `NiCollision`, `NiAudio`, `NiPortal`, `NiParticle`, `NiOldParticle`,
  `NiSystem`, `NiShader`, renderer libs, tool libs, app frameworks).
- Tool Manuals.
- What's New in Gamebryo (per-version changelogs and conversion
  guides — 1.0 → 1.1, 1.1 → 1.2).
- Artist's Guides (3ds max and Maya plugin manuals).

Diagrams: partial `NiObject`-derived class hierarchy (RTTI topic);
texture-pipeline data-flow (multitexture stages as boxes,
inter-stage flow as arrows); sorting / hierarchical-sort
illustrations showing `NiSortAdjustNode` partitioning; step-by-step
streaming process (registration → save → linkID resolution → load).

Documented "gotcha" topics: `Update` correctness vs efficiency
tradeoff; `SelectiveUpdate` flag misconfiguration; never `delete` a
smart pointer; one property per type per object; `NiAlphaAccumulator`
+ `NiSortAdjustNode` surprising draw orders; `NiSkinPartition`
partition count drives skinning performance more than vertex count;
default texture filter/clamp per map type; `APP_TIME` vs `APP_INIT`
controller timing semantics; `NiTimeController::SetTarget` is the
only correct attach; static-vs-dynamic `NiSourceTexture` flag must
be set for textures modified after creation.

Version conversion notes (in `What's New`): 1.0 → 1.1 (input
overhaul, particle rewrite with conversion library); 1.1 → 1.2
(animation conversion notes). **No release notes covering
NetImmerse 3.x → 4.x → Gamebryo 1.0 transitions** appear in this
SDK's docs — those would be in pre-Gamebryo NetImmerse docs, which
aren't here.

NIF version history:
- **3.0 / 3.1** — NetImmerse 3.x era (~2001-2002). **BC ships here.**
  Single-controller animation, old particle system, no skin
  partitions.
- **3.3.0.11** — minimum version this SDK's loader accepts.
- **4.0** — NetImmerse 4 (~2002-2003). Last NetImmerse-branded.
- **10.x** — Gamebryo 1.x (the rename). Skin partitions, `NiPSys*`,
  `NiInterpolator` split.
- **10.0.1.8+** — adds second "user-defined version" word in header.
- **1.2.0.0** (this SDK) — Gamebryo started using its own version
  numbering distinct from the NIF version macro.

Assume BC content is at NIF version ~4.0.x; field-presence is gated
by `version >= X`. NifSkope's reverse-engineered tables are
authoritative on those gates.

Version gates encountered during converter reading:
- **10.1.0.104** — universal "old vs new" cutoff for every legacy
  data class body. BC files are below.
- **10.1.0.109** — "manager-controlled" flag bit repurposed.
- **10.0.1.2** — `NiMaterialColorController` field selector moved
  from base-flag-bits into its own flag word.
- **10.0.1.1** — `NiTimeController` "play-backwards" bit added.
  Files below: flag-bit shift to insert the new bit. Files exactly
  at 10.0.1.1: a separate boolean appears in the body after standard
  fields.
- **10.0.1.16** — `IsVertexController()` controllers (`NiUVController`,
  `NiGeomMorpherController`) started marking target geometry as
  `VOLATILE` for renderer dynamic-VB management. Older files
  retroactively set this at link time.
- **4.1.0.3** — `NiSequence` stopped using `NiSequenceStreamHelper`
  in KF files. Below the threshold → helper conversion path.
- **3.3.0.15** — particle controller static-bound flag added.

---

## 17. BC-specific cross-references

These are areas where BC has specific behaviour and the SDK either
provides or does not provide a direct hook. "Not found" is itself
a load-bearing finding — those features must be application-level.

- **AddLOD / glow attachment**: BC uses a Python-callable
  `AddLOD("..._glow", ...)` to attach glow textures at runtime by
  filename substring match. **Not found in stock SDK.** `NiLODNode`
  is distance-band-driven via `NiLODData` and accepts children at
  fixed integer slots. The closest documented mechanism is
  `NiAVObject::GetObjectByName` for runtime tree search. BC's
  pattern is almost certainly a **BC engine extension**, likely:
  walks the loaded scene graph, finds geometry whose base texture
  name matches a pattern, and either creates a sibling `NiTriShape`
  with an additive glow texture (drawn after via `NiAlphaProperty`
  with `ALPHA_ONE`/`ALPHA_ONE` and the no-sort flag) or attaches it
  as a custom extra-data marker resolved at render time.
- **Corona / lens flare**: BC renders the sun as procedural sphere
  + additive corona shell + lens-flare overlay. **No `NiCorona`,
  `NiLensFlare`, or `NiSunCorona` block class in this SDK.** BC's
  sun/corona/lens-flare are application-level primitives, likely
  built from `NiBillboardNode` + additive-blend geometry + custom
  controllers, possibly using stock `NiTextureEffect` for
  cube/sphere mapping.
- **Center-of-geometry vs origin**: BC ships rotate around the NIF
  origin, which is not the visual centroid. **No documented "center
  of geometry" or "pivot offset" field on `NiAVObject`.** The NIF
  origin is the only documented model-space anchor; deviation from
  the visual centroid is a content/artist decision. Workaround: store
  the centroid offset in custom extra data or translate geometry
  data at export.
- **Engine-wash / impulse trails**: **No stock "stretched billboard"
  or speed-elongated particle primitive.** Closest in modern
  particle library is a custom modifier updating per-particle scale
  and rotation from velocity; in the old particle system, this would
  have been a custom particle subclass or a property animator on a
  billboard quad. BC's engine trails were likely custom rendering.
- **Distance-attenuated emissive (running lights)**: **No "emissive-
  only at distance" or "self-illumination distance" knob** in
  `NiMaterialProperty`, `NiTexturingProperty`, or
  `NiVertexColorProperty`. Distance-faded running lights would be
  application-side, probably a custom controller animating emissive
  color based on camera distance.
- **Damage decals**: **No documented decal-projection API at this
  SDK version.** Decals at the texturing-stage level (`Decal 0..N`
  on `NiTexturingProperty`) are *texture-coordinate driven*, not
  screen/world-projected at runtime. Dynamic hit decals are
  application-implemented atop `NiTriShape`.
- **Ship interiors**: BC's ship-interior tour mode is a plausible
  use case for `NiPortal`. If BC's ship-interior NIFs contain
  `NiRoom`/`NiPortal` blocks, that system applies; otherwise BC
  built its own occlusion.

### 17.1 The NiPortal library (if BC uses it)

- **`NiRoom`** — convex volume defined by `NiRoom::Wall` planes
  (one-sided oriented).
- **`NiPortal`** — one-way "from-through-to" visibility connection
  between a room and adjoining scene graph (the "adjoiner"). Carries
  a convex polygon for the through-shape.
- **`NiRoomGroup`** — top-level grouping of mutually-visible rooms;
  effectively "a level".
- **Fixtures** — non-special geometry attached as children of a room.
- Portals are **one-way**; bidirectional connectivity needs two.
- Portal-adjoiner is **not** a parent-child scene-graph relationship.

### 17.2 No BC-flavored class names in the SDK

The legacy converter and old-particle code contain zero BC-flavored
or Trek-flavored class names. Every class is stock `Ni*`. There are
no hardcoded named-node checks (no `"Bip01"`), no fallback paths
keyed on class-name patterns. BC's customisation lives entirely in
BC's own block registrations and custom controllers (which the
converter silently passes through).

---

## 18. Magic numbers, hardcoded constants

Worth knowing about when matching BC behaviour:

- **`0.01f`** — fudge added to `NiFlipController`'s interpolated
  index before integer truncation, to round-down correctly.
- **`0.0001f`** — epsilon in `NiParticleSystemController` and
  `NiParticleGrowFade` for size-clamping and time-comparison.
- **`0.0333333333f`** — 30 fps run-up sampling for particle
  initialization on first update.
- **`0.10f`** — sampling step for computing the static bound of a
  particle system.
- **`1.05f`** — over-size factor for the computed static bound.
- **`1.6f`** — strength multiplier in `NiGravity` Update. A units-
  conversion fudge factor (likely tied to a historical "what is 1
  unit" interpretation).
- **`12`** — default array initial size and growBy for `NiSequence`
  and `NiKeyframeManager` sequence storage.
- **`1024`** — `SHADER_MAP_OFFSET` in `NiFlipController` to
  distinguish standard map indices from shader map indices.
- **`SHRT_MAX`** — particle counts stored as `u16`.

Code-comment hints of compromise:
- Property-attached legacy controllers are not visited by the
  post-process walk (commented-out block: "If we ever need to
  convert property time controllers, this code should be
  uncommented").
- "Old system reversed direction of gravity" comment next to a
  multiplication by 1.0 — hint of a past sign flip preserved as a
  placeholder. Worth knowing if BC's gravity directions look
  inverted.
- `REMOVE_UNUSED_ROTATIONS` block strips `NiParticleRotation` from
  non-mesh particle systems because the renderer never honored
  rotation for billboard particles (dated "Ni4.0 final release,
  4/30/2001").

---

## 19. Limit summary

| Limit | Value | Where enforced | Category |
| --- | --- | --- | --- |
| Particles per system | u16 count, capped at geometry vertex count | `NiParticles::GetVertexCount()` at SetTarget | **structural** |
| Spawn-cascade generations | u16 | `m_usNumGenerations` | **structural** |
| Kids per spawn event | u16 | `m_usMultiplier` | **structural** |
| Particle modifier list | unbounded | linked list | runtime |
| Particle collider list | unbounded | linked list | runtime |
| Emitter shape | box only | `NiParticleSystemController` direct fields | **structural** |
| Per-particle attributes stored on controller | 7 fields | `NiPerParticleData` layout | **structural** |
| Color keys per color modifier | u32 | `NiColorData::m_uiNumKeys` | **structural — generous** |
| Animation key type | one of 5 (LIN/BEZ/TCB/STEP/EULER) | enum | **structural** |
| Euler key count per channel | exactly 1 | runtime assertion in `NiTransformData` | **runtime-architectural** |
| Animation channels per `NiTransformData` | 3 (rotation, position, scale) | direct fields | **structural** |
| Lights per object | 8 simultaneous | renderer | **hardware-era** |
| Bones per skin partition | 4 default, ≤20 with custom shader | `NiSkinPartition` builder + renderer | **hardware-era** |
| UV sets per vertex | 8 (renderer); structural max u16 | renderer | **hardware-era** |
| Texture stages per pass | GPU-reported | renderer | **hardware-era** |
| Triangle indices | 16-bit unsigned | `NiTriShapeData`/`NiTriStripsData` | **structural** |
| `NiFlipController` shader-map magic offset | 1024 | direct constant | **runtime-architectural** |
| `NiTimeController` flag bits used | 6 (animType, cycleType×2, active, direction, manager-controlled) | bit masks | **runtime-architectural** |
| Sequence initial array growth | 12 entries | `NiSequence` constructor | runtime — soft |
| Static-bound sampling rate | 0.10 s | hardcoded | runtime — soft |
| Particle run-up rate | 30 fps (0.0333…) | hardcoded | runtime — soft |
| Gravity unit conversion factor | 1.6 | hardcoded | runtime — magic |
| Bound over-size factor | 1.05 | hardcoded | runtime — soft |
| Tiling-zero assertion | epsilon | `NiUVController::OnPreDisplay` | runtime — debug only |
| Mesh-particle mesh count | u32 | `NiTArray` | **structural — generous** |

---

## 20. Reimplementation cheat-sheet

If rebuilding the BC NIF path from scratch:

1. **`NiOldAnimationConverter` is the animation spec** — though the
   architecture has three pieces (RTTI aliasing, version-gated
   body-readers, post-process function), and the post-process
   function itself only covers three controllers. The
   per-controller-class `LoadBinary`/`LinkObject` paths
   (`NiTransformController.cpp`, `NiVisController.cpp`,
   `NiUVController.cpp` especially) encode the actual legacy field
   layouts.
2. **`NiOldParticle/*` is the particle spec** in the same way.
3. **`Samples/Tutorials/03 - NIF Files`** is the canonical loop — 30
   lines of mainline + recursive `FindCamera` helper. Match its
   shape and you'll match the engine's lifecycle.
4. **`NiStream.cpp` is the loader skeleton** — the §1.2 byte layout
   came from reading it.
5. **`NiAVObject.cpp`'s `Update`/`UpdateSelected`** is the per-frame
   scene-graph spec: two-pass (downward transforms + upward bounds).
6. **DX8 renderer "Features and Limitations" docs** define the
   content envelope BC's artists worked inside: 8 lights, 8 UV sets,
   4 bones/partition fixed-function, env-map-as-2-stages. Anything
   beyond that envelope is BC application-level, not stock engine.

Practical guidance for the modern animation path:
- Implement only modern data classes (`NiTransformData`,
  `NiBoolData`, etc.).
- Register class-name aliases: `"NiKeyframeController"` →
  `NiTransformController` factory, `"NiKeyframeData"` →
  `NiTransformData` factory, `"NiVisData"` → `NiBoolData` factory.
- In each modern class body reader, version-gate on ≥ 10.1.0.104.
- Implement the small post-process function for the three
  controllers needing topology fixup (`NiLookAtController`,
  `NiRollController`, `NiPathController`).
- Don't implement `NiKeyframeController` or `NiKeyframeData` as
  distinct classes — they don't exist as classes in the modern SDK
  either.

Files to look at next for going deeper:
- `Samples/Games/MadLab/` and `Samples/Games/Eturnum/` — full
  game-tier sample applications.
- `CoreLibs/NiAnimation/NiOldAnimationConverter.h/.cpp` — the
  post-process function source.
- `CoreLibs/NiOldParticle/` and `NiOldParticleConversion` — old
  particle system + forward-port tool.
- `ToolLibs/NiStripify/` — stripification algorithm.
- `ToolLibs/NiAnimationCompression/` — B-spline fitting, key
  reduction. Post-BC but informative.
- `Samples/Tutorials/06 - Time Controllers/` — canonical
  programmatic-animation example.
- `SDK/Win32/Include/` and `SDK/PS2/Include/` — installed SDK headers
  vs the development tree, slightly cleaner public-API view.
