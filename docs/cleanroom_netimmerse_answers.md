# NetImmerse / Gamebryo SDK — Clean-Room Answers

## Important framing note (read first)

The SDK on the contaminated side is **not** NetImmerse 3.1. It is **Gamebryo
1.2.2** by Numerical Design Limited (NDL), built **June 19, 2006**. Gamebryo is
the rebrand of NetImmerse that took place around 2003; the runtime
architecture, public class names (`NiNode`, `NiAVObject`, `NiAlphaProperty`,
etc.), and file-format mechanics descend directly and unbroken from
NetImmerse 3.x/4.x. The NIF header string written by this SDK is
`"Gamebryo File Format, Version 1.2.0.0"`, and the loader's minimum supported
NIF version is **3.3.0.11**, with a maximum bounded by the Gamebryo NIF macros
(here `1.2.0.0`). So:

- Where this answer document says **[documented]**, it means I read it in the
  Gamebryo 1.2.2 docs (the "Programmer's Guide" or class reference) and the
  same wording is what an NDL programmer would have seen.
- Where it says **[inferred from source]**, it means I read the implementation
  in the public-facing engine source shipped with this SDK (header + .cpp).
- Where it says **[3.1 era; later-version drift likely]**, it means the
  documented Gamebryo 1.2 behavior may have evolved from what NetImmerse 3.1
  did. The most likely drift areas: the animation system was overhauled around
  Gamebryo 1.x (split into `NiInterpolator` + `NiInterpController`; the old
  `NiKeyframeController` was deprecated), and the particle system was
  rewritten in Gamebryo 1.1 (the old one now lives in a separate "old
  particle" library). For BC (shipped 2002), the **old** model — single
  `NiKeyframeController`, classic particle subsystem — is the relevant one,
  and is still partially documented because the SDK ships a conversion
  library for legacy content.

I have tried to answer every NI-Q. Where I could not find an answer, I say
**[not found]** and move on.

---

## Headline findings

1. **The file format is breadth-first streamed, not depth-first serialized.**
   Each `NiObject` writes its scalar fields and "link IDs" (integer object
   indices) into the stream; references are resolved in a second pass after
   all objects are constructed. There is no MFC-style recursive serialization.
   This is the single most load-bearing fact about NIF loading and explains
   why a NIF can be re-read in any order without circular-reference problems.

2. **The header is a human-readable ASCII line followed by binary version and
   object counts.** The opening line is a newline-terminated string
   `"Gamebryo File Format, Version d.d.d.d\n"` (in this build; predecessor
   strings said "NetImmerse" — the loader matches on the substring
   `"File Format"`). After the line, a single 32-bit version integer is read.
   In recent NIF revisions (≥ 10.0.1.8) a second "user-defined version" word
   follows. Then a 32-bit object count.

3. **Transform composition is parent · (T · R · S), with uniform scale only.**
   The documented composition order on every `NiAVObject` is translation,
   then rotation (3×3 orthonormal), then a single scalar scale; the
   parent-to-world transform is left-multiplied. The coordinate system is
   right-handed, with positive rotations clockwise looking down the axis
   toward the origin. There is **no per-axis (non-uniform) scale** in the
   transform chain; non-uniform scale is baked into vertices when applied.

4. **There is no "active child must precede parent" ordering rule and no
   explicit footer.** The file is: header line → version words → object count
   → RTTI table (count + names + per-object RTTI index) → object bodies →
   group table (in newer NIF) → top-level object list. Top-level objects are
   stored as a small array of link IDs at the *end*, which functions as the
   only "footer" — there is no separate root-node index.

5. **Block-type references are global 32-bit link IDs into the file-wide
   object array.** They are not pointers, not named lookups, and not
   strong/weak distinguished at the format level; ownership is enforced at
   the C++ level via smart pointers (`NiPointer<T>`) that are wholly
   transparent to the on-disk form. The convention is that anything reachable
   from a top-level link is loaded.

6. **Unknown block types are fatal, not skipped.** The loader looks up each
   RTTI name in a global creation-function registry; a miss aborts the load
   with `NO_CREATE_FUNCTION` and a diagnostic. There is no documented "skip
   unknown" mechanism. BC's custom blocks were almost certainly registered
   into the same factory, not encoded in a vendor-reserved range.

7. **Alpha-blended objects are sorted by bounding-sphere center depth, in a
   single accumulator pass after all opaque geometry has already gone
   through.** The default sorter is `NiAlphaAccumulator`: as the cull walk
   visits each leaf, opaque objects draw immediately, alpha-blended objects
   register for deferred back-to-front drawing. The "no-sort" flag on
   `NiAlphaProperty` opts a single object out of registration. There is a
   documented `NiSortAdjustNode` for mid-graph push/pop of the sorter.

8. **Animation keys come in five interpolation families: LINEAR (slerp for
   quaternions), BEZIER/Hermite, TCB (Kochanek-Bartels), STEP, and EULER
   (three separate float-key channels composed as XYZ).** The Euler key is a
   container — not a key per se — and explicitly composes its X, Y, Z float
   tracks in XYZ order. Position and scale use the same key families
   (`NiLinPosKey`, `NiBezPosKey`, `NiTCBPosKey`, `NiStepPosKey`,
   `NiLinFloatKey`, `NiBezFloatKey`, `NiTCBFloatKey`, `NiStepFloatKey`).

9. **Skinning binds are stored as one `NiTransform` per bone mapping
   "skin → bone" (the inverse-bind), plus per-vertex weight lists with an
   explicit count.** The runtime accumulates `Σ wᵢ · (boneᵢ_world · skinToBoneᵢ
   · meshVertex)` — the canonical linear-blend skinning formula. There is no
   documented renormalization of weights; the format encodes them as-stored.
   Hardware acceleration is layered on via `NiSkinPartition` (added later)
   which partitions triangles into bone-palette-bounded subsets, defaulting
   to 4 bones/partition.

10. **The "extra data" extension mechanism is the primary BC-style customization
    hook on objects, and `NiTextKeyExtraData` carries the animation text
    markers — but the tag strings themselves (`"start"`, `"end"`, `"sound:..."`,
    `"loop start"`, etc.) are **application-defined**, not standardized in
    this SDK.** The SDK doesn't reserve any tag names; how text keys are
    interpreted is up to the game.

---

## A. File format and serialization

- **NI-Q1 [documented + inferred from source]** The header is an ASCII
  newline-terminated string of the form
  `"Gamebryo File Format, Version a.b.c.d\n"` written via a line-based stream
  primitive. NetImmerse-era files said `"NetImmerse File Format, ..."`; the
  loader's robust check is for the literal substring `"File Format"` so it
  accepts either. Following the line, the loader reads a single 32-bit
  **little-endian** integer encoding the version as packed bytes
  `(a<<24) | (b<<16) | (c<<8) | d`. For files at NIF version ≥ 10.0.1.8 a
  second 32-bit "user-defined version" word follows. Then a 32-bit
  unsigned **total object count**. There is no endianness marker — endianness
  is a build/platform property (see Q2).

- **NI-Q2 [inferred from source]** Byte order is **always little-endian** for
  Win32 NIFs (and on platforms with the same native order). The streaming
  primitives are byte-wise (`NiStreamLoadBinary` template specializations) and
  do not encode endianness in the file; cross-platform exports go through a
  separate tool path. PS2 builds existed but used the same loader code with
  platform-specific image / texture sub-paths; there is no
  endianness flag in the header.

- **NI-Q3 [documented + inferred from source]** The block list is **count first**,
  followed by the blocks in registration order. Concretely the load sequence
  is: header line → version words → object count → RTTI table → object bodies
  (one per slot in order) → optional object-group table (newer NIFs) →
  top-level link-ID list. Ordering within the body section is **not
  semantically constrained** — a child block may appear before or after its
  parent because all references are resolved via integer link IDs in a
  later linking pass (see Q4). The Max/Maya exporters happen to place the
  root scene graph node as the first top-level object as a convention.

- **NI-Q4 [documented]** Inter-block references on disk are **32-bit integer
  link IDs** that index into the file's flat object array. They are written
  by `SaveLinkID(obj)` (mapping pointer→ID via a registration map) and read
  by `ReadLinkID`; pointer fixups happen in a separate `LinkObject` pass
  after every object has been constructed and its body read. There is **no
  separate "strong" vs "weak" type at the format level** — both look like a
  link ID on disk. Ownership is expressed in the C++ types (`NiPointer<T>`
  smart-pointer fields are owning; raw `T*` fields are not), and only the
  raw pointer vs smart-pointer distinction in the engine code determines
  refcount lifetime. A null reference is encoded as a sentinel link ID
  (`NULL_LINKID`).

- **NI-Q5 [inferred from source]** Yes, the graph can legitimately contain
  reference cycles, and the streaming system has explicit protection for
  this: each object's `RegisterStreamables` checks whether it has already
  been registered and short-circuits if so, breaking save-time recursion;
  load time then uses the link-ID mechanism, which is acyclic by
  construction. The documented cycle case is `NiLookAtController` (two
  objects looking at each other) — the docs note such cycles "are broken
  arbitrarily" by the controller logic. Skin instances also induce
  bone-pointer back-references that, if traversed naively, would cycle.

- **NI-Q6 [inferred from source]** **No global string table** in the
  classic NIF stream. Strings are written inline per block via a
  length-prefixed C-string primitive (`SaveCString` / its load counterpart).
  Duplicates are **not** deduplicated on disk. The one important exception
  is the **RTTI table at the top of the file**: each distinct class name
  appears exactly once in the RTTI list, and each object body is preceded
  only by a 16-bit index into that table, not by its own class-name string.
  *Animation* sequences additionally introduce an `NiStringPalette` object
  (later versions) that does deduplicate strings used for controller-target
  resolution — but this is a content-level optimization, not a global table.

- **NI-Q7 [documented + inferred from source]** **Unknown block types are
  fatal.** When the loader reads an RTTI name that is not in the global
  creation-function registry, it emits a diagnostic to the debug output
  (`"<name>: unable to find loader for class"`) and aborts the load with
  the error code `NO_CREATE_FUNCTION`. There is no "skip unknown" path. To
  load custom blocks, an application must call the macro that registers a
  creation function for each subclass before invoking the loader; this is
  the same mechanism the engine's own `NiMainSDM`-style "system descriptor
  module" uses. BC's custom blocks therefore must be registered by the BC
  runtime — they are not version-tagged in the NIF.

- **NI-Q8 [inferred from source]** There is a **trailing top-level object
  list**, which is the closest thing to a footer. After every object body
  has been written, the stream emits an unsigned count of "top-level"
  objects followed by that many link IDs. These are the objects that were
  originally inserted into the stream via `InsertObject`; they are what
  `GetObjectCount`/`GetObjectAt` will return at load time. There is **no
  named-object index** and no dependency manifest. Newer NIFs (post-Gamebryo
  1.0) interpose an "object group" table just before the top-level list,
  used for grouped allocation; this carries a count plus per-group total
  byte size, not per-object indexing.

- **NI-Q9 [not found]** The Gamebryo 1.2 loader reads a raw, uncompressed
  stream. ZLib ships in the SDK's third-party tree, but there is no
  documented mechanism for whole-file NIF compression at this version. (If
  BC files appear compressed, it is an application wrapper above the NIF
  layer.)

- **NI-Q10 [not found]** No documented checksum, signature, or DRM-style
  integrity check in the NIF format itself.

- **NI-Q11 [documented + inferred from source]** A null reference is written
  as the sentinel link ID `NULL_LINKID`. On load, that sentinel resolves to
  a null pointer, distinguishable from any valid object slot. "Missing
  optional" is encoded by either omitting the link entirely (if the parent
  block's schema is version-gated, the field doesn't appear at older NIF
  versions) or by writing `NULL_LINKID` to signal "present but empty." There
  is no separate "optional" tag bit.

- **NI-Q12 [inferred from source]** Float fields are IEEE-754 single
  precision throughout the standard scene graph (positions, normals,
  matrices, quaternions, key values, attenuation factors, etc.). Half-floats
  and fixed-point storage appear in some specialized later-version data
  classes (e.g., B-spline compressed transforms) but not in the foundational
  geometry/material/animation blocks.

- **NI-Q13 [inferred from source]** The documented extension hook is the
  creation-function registry (Q7) plus the RTTI-name table — i.e., new
  classes are registered by name. There is **no reserved version-number
  range for vendor extensions** in the format; vendors would simply add
  classes with new names that the application registers. The "user-defined
  version" 32-bit word added at NIF 10.0.1.8+ is a vendor-coordination
  field, but BC predates that revision.

## B. Scene graph semantics

- **NI-Q14 [documented]** Transform composition on every `NiAVObject` is
  **parent_world · (T · R · S)**, where T is a translation vector, R is a
  3×3 orthonormal rotation matrix, and S is a **single scalar uniform scale**.
  Points are transformed `vL = (T R S) · vM`, `vW = parent_world · vL` (i.e.
  column-vector convention; matrices act on the left). Scale is **uniform
  only** at the transform level; non-uniform scale, shear, and reflection
  must be baked into the geometry data via `ApplyTransform` and propagated
  to leaf vertices.

- **NI-Q15 [documented]** World transforms are **lazily refreshed via a
  scene-wide `Update(time)` call** that must be made at or above any object
  whose local transform changed since the previous update, before that
  object (or its descendants) is rendered or collision-checked. There is no
  eager "set propagates immediately" mechanism. The Update walk does a
  downward pass that recomputes child world transforms and a subsequent
  upward pass that refreshes ancestors' world bounds. There is also a
  `UpdateSelected(time)` variant that uses per-node "selective update" flags
  to skip transform recomputation for static subtrees; the exporters set
  these flags on load.

- **NI-Q16 [documented + inferred from source]** The principal flags on
  `NiAVObject` are:
  - **App-cull flag** (`GetAppCulled` / `SetAppCulled`). When true, the
    object and its subtree are skipped during the rendering walk. This is
    *not* propagated down the hierarchy — setting it on an ancestor will
    *not* hide a descendant if that descendant is reached via a different
    scene path.
  - **Display-object flag** (`SetDisplayObject`). Doesn't affect Gamebryo
    drawing; reserved as a hook for third-party occlusion culling.
  - **Selective-update flags** (four of them): `SelectiveUpdate`,
    `SelectiveUpdateTransforms`, `SelectiveUpdatePropertyControllers`,
    `SelectiveUpdateRigid`. These control which parts of the `UpdateSelected`
    walk execute for this node; default initializations bias toward the
    fast/cheap path. They are a performance optimization, not a visibility
    flag.

  There is no separate "render culled" bit distinct from "app culled" at the
  `NiAVObject` level; "render culling" is the dynamic result of frustum
  culling during the rendering walk and is not stored.

- **NI-Q17 [documented]** Bounding volumes are computed bottom-up during
  Update: each `NiAVObject` carries a world-space bound, and an `NiNode`
  derives its bound from its children. There are two modes: **Merge** (the
  classical mode — the node's bound is the merger of all child world bounds
  each frame) and **Rigid** (faster — the node holds a precomputed local
  bound that just gets transformed by the node's world transform, valid only
  if descendants are not independently animated). Which mode is used per
  node is controlled by the `SelectiveUpdateRigid` flag. The recomputation
  is triggered by the Update upward pass, so a child's bound always inflates
  the parent's *after* an Update call covering both, but never during
  unrelated frames.

- **NI-Q18 [documented]** The authoritative bound type is the **bounding
  sphere** (`NiBound`, holding a center + radius; the documentation notes
  the internal representation "may be any type of bounding volume" but only
  sphere accessors are exposed). Frustum culling uses this sphere.
  Collision detection adds OBBs and AABBs as separate "alternate bounding
  volume" hierarchies (`NiOBBNode`, `NiOBBRoot`, `NiOBBLeaf`,
  `NiSphereBV`, `NiBoxBV`, `NiCapsuleBV`, `NiUnionBV` — see Section I)
  living alongside the scene graph rather than replacing the sphere bound.
  Picking uses the same sphere bound as culling, optionally refined to
  triangle level.

- **NI-Q19 [documented]** `NiSwitchNode` selects the active child by an
  **integer index** (`SetIndex(int)`); index `-1` means "no child active",
  any non-negative value picks a slot of the child array. The selection is
  **manual** by default — it does not change per frame on its own. A
  controller (e.g., a flipbook animator) can be attached to drive the
  index over time, but the SDK's flipbook animation is a specific subclass
  on top, not a feature of the base switch. A configurable optimization
  flag, `UpdateOnlyActiveChild`, tells `Update` to skip inactive subtrees;
  the active child is updated on demand if it changes between Update and
  render.

- **NI-Q20 [documented]** `NiLODNode` derives from `NiSwitchNode` and asks
  its attached `NiLODData` object which child to make active given the
  current camera. There are two data subclasses: **`NiRangeLODData`**, which
  defines numeric distance bands (each child is associated with a
  near/far range, and the camera-to-node distance picks the band), and
  **`NiScreenLODData`**, which evaluates an apparent-screen-size metric
  instead. The distance is computed from the camera position to the
  LOD node's world-space bound center (not to the nearest point on the
  bound). A `LOD Adjust` factor on `NiCamera` (default 1.0) globally
  scales the apparent distance for tuning. There is also a `GlobalLOD`
  static override for forcing all LOD nodes to a specific child index
  (debug tool).

- **NI-Q21 [documented]** `NiBillboardNode` has five rotation modes:
  - `ALWAYS_FACE_CAMERA` — model-space +Z aligns to camera view-plane
    normal, recomputed each frame.
  - `ROTATE_ABOUT_UP` (default) — model-space +Z faces camera as closely as
    possible while only rotation about model-space [0,1,0] is allowed.
  - `RIGID_FACE_CAMERA` — billboard normal stays parallel to camera
    direction, and billboard frame rigidly rotates with camera frame.
  - `ALWAYS_FACE_CENTER` — z-axis points at camera origin (as opposed to
    view-plane).
  - `RIGID_FACE_CENTER` — z-axis points at camera origin, with rigid
    rotational coupling to camera frame.

  Importantly, the "up" vector for `ROTATE_ABOUT_UP` is the **model-space
  up of the billboard node itself** ([0,1,0] in the node's local frame),
  not a global world-up — so a billboard's effective axis is determined by
  its parent transform chain. Orientation update happens **during the
  render-pass cull walk**, not during the Update pass, so a billboard's
  apparent orientation is always consistent with the current camera state.

- **NI-Q22 [documented]** No — every `NiAVObject` child of an `NiNode`
  participates in the transform hierarchy, and "rendered or not" is
  determined by the leaf object's drawability (a `NiCamera` or `NiLight`
  isn't drawn but is positioned by its parent; an `NiGeometry` leaf is).
  Lights and effects attach to nodes via a separate "dynamic effect list"
  (`AttachEffect`/`DetachEffect`), distinct from the child array — that's
  the closest thing to a "non-rendered, transform-affecting" child, but
  effects don't have their own subtree.

- **NI-Q23 [documented]** Documented per-frame order is:
  1. Application calls `Update(time)` (or `UpdateSelected`) on the scene
     root — this propagates world transforms downward, calls each
     controller's `Update` to evaluate animation values and write them
     back to their targets, then propagates world bounds upward.
  2. Application calls `UpdateProperties()` and `UpdateEffects()` if the
     property/effect stacks changed (these are *not* run inside `Update`).
  3. Application calls `NiCamera::Click()`. Internally `Click` does a
     `CullShow` traversal: depth-first walk, world-bound frustum reject at
     each node, alpha-accumulator registration at each leaf, immediate
     draw for opaque leaves. After the walk, the accumulator's deferred
     queue is drawn back-to-front.
  4. `SwapBuffers`.

  Animation evaluation thus happens *inside* `Update`, before cull/render.
  Geometry that responds to animation (skinning, morphing) finishes its
  vertex computations either in `Update` or in a pre-display callback
  (`OnPreDisplay` on `NiGeomMorpherController`).

- **NI-Q24 [documented]** Yes — the four `SelectiveUpdate*` flags on
  `NiAVObject` (see Q16). They are set automatically by the exporters and
  on legacy NIF load to optimal values for a content-static viewer, and
  can be recomputed by `SetSelectiveUpdateFlags` on a subtree.
  `SelectiveUpdate=false` skips that object entirely;
  `SelectiveUpdateTransforms=false` skips the world-transform
  recomputation; `SelectiveUpdateRigid=true` says "use precomputed local
  bound rather than merging children each frame." Misconfigured flags
  produce silently wrong transforms or bounds, so the docs flag this as a
  hazard.

- **NI-Q25 [documented]** There is no distinct "scene root" class — any
  `NiNode` can be a scene root; `NiCamera::SetScene(NiNode*)` accepts any
  node. A scene typically *contains* an `NiCamera`, `NiLight`s, and an
  ambient light at top level, but they are children/siblings rather than
  members of a distinguished root type.

## C. Geometry

- **NI-Q26 [documented]** Vertex attributes storable on
  `NiTriShapeData`/`NiTriStripsData` (via the common base `NiGeometryData`):
  positions (`NiPoint3` array, always present for non-empty geometry);
  optional normals (`NiPoint3`); optional vertex colors (`NiColorA` —
  RGBA float, *not* packed bytes at this engine level); optional texture
  coordinates as an array of `NiPoint2` with an explicit "number of
  texture sets" count, so multiple UV sets are stored as concatenated
  blocks; optional binormals and tangents, stored interleaved-by-block
  with normals (all normals, then all binormals, then all tangents) when
  enabled by an "NBT method" enum (`NBT_METHOD_NONE` or one of the
  computed methods). Presence is flagged by null vs non-null pointers in
  the data object (and by the NBT method enum for binormals/tangents).

- **NI-Q27 [documented]** Normals are **per-vertex** when present, in
  **model space** (the same space as the vertex positions). Per-face
  normals are not a stored option in `NiGeometryData`; a "smooth = false"
  effect is achieved at runtime via `NiShadeProperty::SetSmooth(false)`,
  not by per-face normals.

- **NI-Q28 [documented]** `NiTriStripsData` stores **multiple independent
  triangle strips per object**, not a single restart-encoded super-strip.
  The data carries a strip count, a per-strip vertex-count array, and a
  flat index list concatenating all strips. No restart index or degenerate
  triangles are used at the format level. Strip orientation (which vertex
  starts the alternation) is encoded in the strip itself; the renderer
  uses each strip's natural orientation and does not flip culling between
  strips.

- **NI-Q29 [documented]** UV sets are arbitrarily many in principle; the
  count is stored on the geometry data. A texture stage selects its UV set
  via the `Map`'s "texture index" property (an integer texture-coordinate
  set index), which can be set per-stage on the `NiTexturingProperty`.
  Most BC-era content uses one or two sets in practice.

- **NI-Q30 [documented]** Vertex color routing is controlled by
  `NiVertexColorProperty::SourceVertexMode`: `SOURCE_IGNORE` (vertex
  colors are not consulted; all of emissive, ambient, diffuse come from
  the material), `SOURCE_EMISSIVE` (vertex color replaces emissive only),
  and `SOURCE_AMB_DIFF` (vertex color replaces ambient+diffuse, but
  emissive still from material). Independently, the
  `NiTexturingProperty` "apply mode" can be `APPLY_REPLACE`,
  `APPLY_MODULATE`, `APPLY_DECAL`, or `APPLY_HILIGHT` — and `MODULATE` is
  what makes vertex/material colors visible at all when a base texture is
  present.

- **NI-Q31 [documented]** Tangents and binormals are stored only when an
  application or exporter enables them (NBT method). When stored, they
  are *full* `NiPoint3` per vertex (no compression) and are laid out
  contiguously after the normals: normals[0..n-1], binormals[0..n-1],
  tangents[0..n-1] in one allocation. When absent, the renderer computes
  them on demand if a property needs them (e.g., for bump mapping with
  classic fixed-function dot-product setup).

- **NI-Q32 [documented]** Skinning attaches to an ordinary `NiGeometry` via
  an `NiSkinInstance` pointer on that geometry. There is no separate
  "skinned geometry" subclass; the same `NiTriShape` / `NiTriStrips` can
  be skinned or not depending on whether it has an `NiSkinInstance`.

- **NI-Q33 [inferred from source]** Triangle indices are **16-bit unsigned**
  in the standard `NiTriShapeData` / `NiTriStripsData` (the C++ signature
  takes `unsigned short*` for tri lists). 32-bit indices are not native to
  these classes at this version. Geometry exceeding 65535 indices would
  need to be split.

- **NI-Q34 [not found]** No documented vertex-cache optimization hint at
  the format level (e.g., no "pre-transform cache order" flag). The
  stripification tool ships separately under `NiStripify` and produces
  cache-friendly strips at export time, but the runtime does not record or
  consult an optimization indicator.

## D. Materials and rendering properties

- **NI-Q35 [documented]** `NiMaterialProperty` channels and defaults:
  - **Ambient color** (default [0.5, 0.5, 0.5]) — modulated by each light's
    ambient component plus the global ambient light.
  - **Diffuse color** (default [0.5, 0.5, 0.5]) — modulated by each light's
    diffuse component, scaled by N·L.
  - **Specular color** (default [0.0, 0.0, 0.0]) — modulated by each light's
    specular contribution if specular is gated on (see Q36); implementation
    is described as renderer-dependent in the docs.
  - **Emissive color** (default [0.0, 0.0, 0.0]) — added unconditionally;
    this is the only channel that contributes when no light is hitting the
    surface.
  - **Alpha** (default 1.0, range 0..1) — the material's translucency.
  - **Shineness / glossiness** (default 4.0, non-negative) — the specular
    exponent ("shine").

  When no light contributes (or `NiVertexColorProperty::LIGHTING_E` mode is
  selected), only **emissive** is taken. The full equation, paraphrased
  from the SDK's "Diffuse Lighting Equation" topic:

  `V_final = V_E + Σ_lights L_I · (L_A·V_A + A·S·L_D·V_D·R_D)`

  where V_E, V_A, V_D are emissive/ambient/diffuse vertex colors (chosen
  from material or vertex color per `NiVertexColorProperty::SourceMode`),
  L_I is the dimmer, A and S are the distance and spot attenuations, and
  R_D is the diffuse-reflection scalar (clamped N·L). Specular is added
  on top in a renderer-dependent way and is not formally part of this
  equation.

- **NI-Q36 [inferred from source]** Specular is **gated by a separate
  `NiSpecularProperty`** (a stock property in the hierarchy: a single
  boolean flag for "specular enabled"). The `NiMaterialProperty` stores
  the specular color and shine but does not turn specular on/off by itself.
  Some renderers also respect a per-`NiMaterialProperty` "specular ignore"
  optimization, but the documented opt-out path is `NiSpecularProperty`.

- **NI-Q37 [documented]** `NiAlphaProperty` exposes named fields, not
  raw bit positions, but here is what each field means:
  - **Alpha-blend enable** (boolean) — turn alpha blending on/off for the
    subtree.
  - **Source blend mode** (enum) — selects the multiplier applied to the
    incoming pixel before write. Choices include ONE, ZERO, SRCCOLOR,
    INVSRCCOLOR, DESTCOLOR, INVDESTCOLOR, SRCALPHA, INVSRCALPHA, DESTALPHA,
    INVDESTALPHA, SRCALPHASAT.
  - **Destination blend mode** (enum) — same enumeration, applied to the
    existing framebuffer pixel.
  - **Alpha-test enable** (boolean) — turn alpha testing on/off.
  - **Alpha-test function** (enum) — ALWAYS, LESS, EQUAL, LESSEQUAL,
    GREATER, NOTEQUAL, GREATEREQUAL, NEVER.
  - **Alpha-test reference** (unsigned char, 0..255) — the reference value
    compared against source alpha.
  - **No-sort flag** (boolean) — when true, an alpha-blended object is
    **not** registered with the `NiAlphaAccumulator` for back-to-front
    sorting; it draws immediately at its traversal-order position.
    Useful for hand-ordered transparent geometry.

  Defaults are: blending off, alpha-test off, src=SRCALPHA, dst=INVSRCALPHA,
  test=ALWAYS, ref=0.

- **NI-Q38 [documented]** Documented policy: alpha-blended objects sort
  **back-to-front by world-space depth of the bounding-sphere center**
  (single-point per object), via `NiAlphaAccumulator`. Triangles within an
  object are not sorted relative to each other; objects with overlapping
  centers in depth produce ordering tied to traversal order. The `NoSorter`
  flag opts an object out and is the documented mechanism for "I will
  handle ordering myself."

- **NI-Q39 [documented]** `NiZBufferProperty` carries three independent
  fields: a depth-test enable boolean, a depth-write enable boolean, and
  a depth-test comparison function. Supported functions: ALWAYS, LESS,
  EQUAL, LESSEQUAL (default), GREATER, NOTEQUAL, GREATEREQUAL, NEVER.
  The default constructor enables both test and write with LESSEQUAL —
  classic full Z-buffering. All four (test, write) × (true, false)
  combinations are individually meaningful and documented.

- **NI-Q40 [documented]** `NiStencilProperty` exposes:
  - **Enable** (boolean).
  - **Function** (same TEST_* enumeration as Q39).
  - **Reference** (unsigned int).
  - **Mask** (unsigned int, default 0xFFFFFFFF).
  - **Pass action** — what to do on stencil pass + Z pass.
  - **Pass-but-Z-fail action**.
  - **Fail action**.
    Actions: KEEP, ZERO, REPLACE, INCREMENT, DECREMENT, INVERT.
    Default: pass=INCREMENT, others=KEEP.
  - **Draw mode** — independent culling override that lives on stencil
    property because stencil effects often need two-sided draw:
    DRAW_CCW_OR_BOTH (default, equivalent to fixed-function front-CCW),
    DRAW_CCW, DRAW_CW, DRAW_BOTH (no culling).

- **NI-Q41 [documented]** `NiTexturingProperty` slot vocabulary:
  - **Base map** — primary diffuse texture. Combined with vertex/material
    color per the property's apply mode.
  - **Dark map** — multiplicative light map (white = fully lit, black =
    unlit); modulated against the result so far.
  - **Detail map** — high-frequency surface texture, combined with base
    via `2 × baseColor × detailColor` (the classic "modulate2x") to add
    bump-like detail across distance.
  - **Gloss map** — modulates specular contribution per texel (white =
    mirror, black = matte, tinted = colored metallic).
  - **Glow map** — adds an additive emissive contribution that does **not**
    depend on light direction; renders as a separate additive stage atop
    the lit color. Independent of the material's emissive color.
  - **Bump map** — gradient-encoded normal/height map. The stage carries a
    2×2 bump matrix and (when paired with an environment map) generates
    perturbed env-map coordinates.
  - **Decal 0..N** — additional decal stages indexed by integer. Each
    decal is an RGBA texture; alpha gates the decal against the surface.
  - **Shader map** — used by the higher-level shader system to attach
    arbitrary additional sampler bindings; covered by `NiShader` library.

  Each `Map` (and `BumpMap`) records its image (`NiTexture*`), the clamp
  mode, the filter mode, and the texture-coordinate set index. The
  combiner formula is documented per stage type rather than per `Map`.

- **NI-Q42 [documented]** Filter modes (enum on each `Map`): NEAREST,
  BILERP, NEAREST_MIPNEAREST, NEAREST_MIPLERP, BILERP_MIPNEAREST,
  BILERP_MIPLERP (trilinear), and ANISOTROPIC. Clamp modes: CLAMP_S_CLAMP_T,
  CLAMP_S_WRAP_T, WRAP_S_CLAMP_T, WRAP_S_WRAP_T (the four corners), plus
  mirror variants in newer Gamebryo. There is no separate "clamp-to-edge"
  vs "clamp-to-border" distinction at this API level.

- **NI-Q43 [documented]** Yes — the **glow map** is the documented
  additive emissive stage. It contributes additively to the framebuffer,
  is independent of lighting, and is independent of the material's
  emissive color. It is one of the named slots on `NiTexturingProperty`
  (see Q41) and ships with stock combiner support across all renderers.

- **NI-Q44 [documented]** `NiSourceTexture` carries either a filename
  reference or an in-memory `NiPixelData` object. `NiPixelData` stores
  the pixel format via a `NiPixelFormat` descriptor (which encodes
  channel count, bit depths, component meaning — including palettized
  modes via an `NiPalette` reference). Mipmaps are governed by a global
  `SetUseMipmapping(bool)` toggle (default true) plus per-texture
  preferences ("format prefs") attached to the source; if mipmapping is
  on and the source data is non-mipmapped, the engine generates the
  pyramid. Mipmaps can also be pre-stored in the `NiPixelData` (full
  pyramid) and loaded directly. The `LoadDirectToRendererHint` flag
  short-circuits the app-side `NiPixelData` step for textures that come
  straight from a file format the renderer can ingest natively (e.g.,
  DDS via `NiDDSReader`).

- **NI-Q45 [documented]** UV transform controllers were originally
  `NiUVController`; in Gamebryo 1.x it is deprecated in favor of
  `NiTextureTransformController`. The latter targets a single
  `NiTexturingProperty` *map slot* and a single UV channel (translate,
  rotate, or scale) at a time, driven by an `NiFloatInterpolator`. The
  transform stages compose in the documented order T·R·S (same as
  geometry transforms). The UV set being transformed is the one bound
  to the targeted texture stage (per `Map::SetTextureIndex`).

- **NI-Q46 [documented]** Cube-map and environment-map support is
  present at this engine version via two paths: (a) `NiTextureEffect`,
  a dynamic effect attached to a node that injects a sphere-, cube-, or
  projected-texture stage into the texturing pipeline for the affected
  subtree (the classic env-map mechanism); (b) the `NiShader` framework
  (Gamebryo 1.x addition) for programmable cube-map sampling. For BC
  (NetImmerse 3.x era), only the dynamic-effect path was available.

- **NI-Q47 [documented]** `NiVertexColorProperty` has two enums:
  **Source vertex mode** — `SOURCE_IGNORE` (use only `NiMaterialProperty`
  colors), `SOURCE_EMISSIVE` (vertex color overrides emissive only),
  `SOURCE_AMB_DIFF` (vertex color overrides ambient + diffuse).
  **Lighting mode** — `LIGHTING_E` (only emissive contributes — used for
  pre-lit / unlit geometry), `LIGHTING_E_A_D` (emissive + ambient +
  diffuse contribute — full lighting). The two enums are independent;
  e.g., one can ask for vertex-overridden ambient+diffuse while only
  outputting the emissive term, which is the classic "static
  pre-lighting" mode. Defaults: `SOURCE_IGNORE` + `LIGHTING_E_A_D`.

- **NI-Q48 [documented]** `NiShadeProperty` supports exactly two modes,
  via a single boolean `SetSmooth(bool)`: **Gouraud** (smooth, default)
  and **flat**. Phong is not a stock fixed-function option; Phong-style
  shading would be achieved by the `NiShader` framework.

- **NI-Q49 [documented]** `NiDitherProperty` is a single boolean
  (dither-on/off at the framebuffer level; affects 16-bit display modes).
  `NiWireframeProperty` is similarly a single boolean (draw triangles as
  wireframe lines); useful for debug visualization.

- **NI-Q50 [documented]** `NiFogProperty` carries an enable flag, a fog
  function enum, a fog color (independent of background color in current
  Gamebryo), and a depth value in normalized [0..1] range. Functions
  available: **FOG_Z_LINEAR** (cheap, vertex/raster, distance from far
  plane), **FOG_RANGE_SQ** (eye-distance squared, fewer artifacts).
  Older `FOG_VERTEX_ALPHA` (vertex-alpha-driven custom fog) is documented
  as no longer supported in this version. Per-pixel vs per-vertex
  distinction is renderer-dependent; the property does not select.

- **NI-Q51 [documented]** The property stack rule: **closer wins, and
  only one property of a given type is active on any given subtree**.
  Properties are pushed downward during the cull walk; when a deeper
  `NiAVObject` carries a property of the same type as an ancestor, the
  deeper one fully replaces the ancestor's for that subtree. Properties
  do *not* combine. If no property of a given type is anywhere on the
  ancestor chain, the engine's default-constructed property of that type
  is used.

- **NI-Q52 [not found]** No documented multi-pass fallback specifier in
  the format (e.g., no "render this once with pass A, then once with
  pass B" tag). Multi-pass behavior is handled internally by the
  renderer when a texturing-property configuration exceeds the
  hardware's single-pass capability — the application doesn't specify it
  and there is no NIF-level encoding.

## E. Lighting

- **NI-Q53 [documented]** All four light classes derive from `NiLight`
  (which derives from `NiDynamicEffect`) and share:
  - **Dimmer** (intensity scalar, default 1.0)
  - **Ambient color** (default [1,1,1])
  - **Diffuse color** (default [1,1,1])
  - **Specular color** (default [1,1,1])

  Subclass-specific parameters:
  - `NiAmbientLight`: nothing more (no location, no direction, no
    attenuation).
  - `NiDirectionalLight`: light direction in world space, derived from the
    node's transform — light projects **down the model-space +X axis**
    (so rotating the parent node aims the light). Defaults to [1,0,0]
    world-space.
  - `NiPointLight`: world location (from node transform), plus three
    attenuation factors (constant C, linear L, quadratic Q; defaults
    C=0, L=1, Q=0).
  - `NiSpotLight` (extends `NiPointLight`): direction (also model-space
    +X axis), spot cone angle (degrees, default 0), spot exponent (default
    1.0).

- **NI-Q54 [documented]** Lights live in the scene graph as children of
  ordinary `NiNode`s. They inherit the parent transform, so animating
  the parent moves/rotates the light. **The light's "forward" / shine
  axis is model-space +X**, not -Z. To aim a directional or spot light,
  rotate the node so its +X axis points where you want the light to go.

- **NI-Q55 [documented]** Distance attenuation for point and spot lights:
  `attenuation = 1 / (C + L·d + Q·d²)`, where d is the world-space
  distance from light to vertex, and C/L/Q are the constant/linear/
  quadratic factors. To disable attenuation entirely, set C=1, L=0, Q=0.
  Ambient and directional lights do not attenuate. Spot cone attenuation
  is documented as **linear from spot direction to edge of cone** when
  the spot exponent is 1.0; for other exponent values the behavior is
  renderer-dependent.

- **NI-Q56 [inferred from source]** No documented hard limit at the
  scene-graph level; the runtime accepts an arbitrary number of lights
  attached to a node via `AttachEffect`. The actual cap is set by the
  renderer (e.g., DX8/DX9 fixed-function pipelines have 8 simultaneous
  hardware lights). The documented optimization advice is to scope
  lights via the dynamic-effect attachment to the smallest subtree they
  actually affect; there is no built-in "nearest-N selection" algorithm
  described.

- **NI-Q57 [documented]** Specular uses the light's **specular color**
  (a separate `NiColor` from diffuse). Whether it contributes depends on
  the presence of `NiSpecularProperty` (see Q36); there is no per-material
  "ignore specular" flag at the property layer.

- **NI-Q58 [not found]** No documented projected light textures or
  built-in shadow primitives at this SDK era. Shadow maps and stencil
  shadows ship as sample applications (`ShadowMap`, `StencilShadow`),
  but as application-level implementations on top of the engine, not
  as light-class features.

## F. Animation

> Important historical note for BC: BC ships against the
> **NiKeyframeController** model (single controller, multi-channel data
> block per node), which is the **deprecated** path in this Gamebryo
> 1.2 SDK. Gamebryo 1.x split that model into `NiTimeController`-derived
> "interp controllers" (each on one property of one target) holding
> `NiInterpolator` objects (each one channel). The semantics below are
> documented for both paths where they differ; the SDK provides a
> conversion library that maps the old `NiSequence` to the new
> `NiControllerSequence` on load.

- **NI-Q59 [documented]** A controller chain attaches to its target
  `NiObjectNET` via the target's `controllers` linked-list field
  (`PrependController` / `SetControllers` / `GetControllers`). On the
  controller, `SetTarget(NiObjectNET*)` automatically inserts/removes
  itself in the target's list. At **load time, the target reference is
  a raw pointer fixed up by link-ID resolution** (in the modern
  `NiControllerSequence` path, an additional name-based lookup runs:
  the sequence carries a node name + controller-type RTTI name and
  re-resolves the target node by name within the scene graph rooted at
  the controller manager's target — this is what enables sharing an
  animation file across multiple character instances). For BC-era
  (`NiSequence`/`NiKeyframeController`) the link-ID model alone is in
  play; there is no name-based reattach.

- **NI-Q60 [documented]** Per-controller fields on every `NiTimeController`:
  - **Start time** and **stop time** (floats; the time range over which
    keys are valid). Start/stop are inclusive endpoints.
  - **Frequency** (float, default 1.0; multiplicative time scale).
  - **Phase** (float, default 0.0; additive time offset).
  - **Cycle type** (enum): LOOP, REVERSE (ping-pong), CLAMP (hold
    endpoints).
  - **Animation type** (enum): APP_TIME (use the absolute application
    time passed in), APP_INIT (subtract a per-controller start moment
    so the animation re-bases when `Start` is called).
  - **Active** (boolean, default true; inactive controllers don't update).

  The effective evaluation time is `((appTime - startMoment) ·
  frequency + phase)`, mapped through cycle type into [start, stop].

- **NI-Q61 [documented]** Cycle type behavior outside [start, stop]:
  - **CLAMP**: time is clipped to the endpoint (animation holds the
    first or last key value).
  - **LOOP**: time wraps modulo (stop − start), so animation repeats
    end-to-start.
  - **REVERSE** (ping-pong): time reflects at endpoints, alternating
    forward and backward traversals of the range.

- **NI-Q62 [documented]** Rotation key subclasses of `NiRotKey`:
  - **`NiLinRotKey`** — time + quaternion. Interpolation is **slerp**
    (the docs note "spherical correlation to linear interpolation,
    namely Slerp").
  - **`NiBezRotKey`** — time + quaternion, with implicit Hermite-style
    interpolation between adjacent keys. Despite the "Bez" name, the
    docs explicitly note these are Hermite-spline-interpolated (see Q66).
  - **`NiTCBRotKey`** — time + quaternion + three TCB parameters
    (tension, continuity, bias). Interpolation per Kochanek-Bartels
    (see Q65).
  - **`NiStepRotKey`** — time + quaternion, no interpolation; value
    holds until the next key.
  - **`NiEulerRotKey`** — *not* a single key but a container: it holds
    three independent `NiFloatKey` arrays (X, Y, Z float tracks) each
    with their own interpolation type. Composed in **XYZ** order (see
    Q64).

  Position keys mirror this taxonomy (`NiLinPosKey`, `NiBezPosKey`,
  `NiTCBPosKey`, `NiStepPosKey`); scale keys use `NiFloatKey` variants
  (`NiLinFloatKey`, `NiBezFloatKey`, `NiTCBFloatKey`, `NiStepFloatKey`).

- **NI-Q63 [documented + inferred from source]** Quaternion
  interpolation for linear rotation keys is **slerp**, with the
  shortest-arc selection (negate one quaternion if their dot product
  is negative) handled inside `NiQuaternion::Slerp`. The class also
  provides a fast-path "Lerp + counter-warp" that approximates slerp
  for small angular separation. There is no published "squad" path
  for the runtime; squad is used inside the offline animation
  compression tool path (B-spline fit), not at playback.

- **NI-Q64 [documented]** `NiEulerRotKey` composes its three float
  tracks as **rotations about model-space X, then Y, then Z** in that
  fixed order ("the rotation is specified in the following ordering,
  XYZ"). The units are **radians**. Each axis track can itself use any
  of the float-key interpolation types (linear, Bezier, TCB, step), so
  smoothness on each axis is independent.

- **NI-Q65 [documented + inferred from source]** TCB keys use the
  Kochanek-Bartels formulation: each key carries tension (T),
  continuity (C), and bias (B) parameters in [-1, 1]. Tangents are
  computed at each key as a weighted combination of the incoming and
  outgoing chord vectors, weighted by (1−T)(1+C)(1+B) / (1−T)(1−C)(1−B)
  (incoming) and the analogous formula for outgoing. At the first and
  last keys (boundary keys), the missing-side tangent is computed by
  reflecting the present chord, producing a "natural" boundary
  behavior. The interpolation between adjacent keys is a cubic Hermite
  spline using those tangents.

- **NI-Q66 [documented]** `NiBezRotKey` and `NiBezPosKey` are **Hermite
  spline** keys — the documentation literally says "in spite of their
  name, are used to represent a 3-D Hermite spline." Each Bez key
  stores an **in-tangent** and **out-tangent** vector (for position
  keys, two `NiPoint3`; for rotation keys, the tangents are stored as
  quaternion deltas). The tangents are in the same space as the key
  values (model-space position for positions; quaternion deltas for
  rotations).

- **NI-Q67 [documented]** Position keys mirror rotation keys: same
  five families (Lin, Bez/Hermite, TCB, Step, plus none for "Euler"
  since position doesn't decompose that way), same per-family
  semantics. Scale keys use the float-key family. The interpolation
  math is the family-appropriate one (lerp for linear, Hermite for
  Bez, K-B for TCB, hold for step).

- **NI-Q68 [documented]** `NiKeyframeController` is the **deprecated
  classic** single-controller-per-node design: one controller object
  holds a single `NiKeyframeData` block carrying combined rotation +
  translation + scale tracks targeting the node's local transform.
  `NiTransformController` (its replacement in Gamebryo 1.x) is a
  `NiSingleInterpController` that uses an `NiInterpolator` (typically
  `NiTransformInterpolator`) producing an `NiQuatTransform` to drive
  the same target transform. The two are functionally equivalent on
  playback. In 3.1 (BC era), `NiKeyframeController` was the canonical
  type; in current Gamebryo, `NiTransformController` is preferred.

- **NI-Q69 [documented]** `NiControllerSequence` represents a named
  **animation clip** — a set of interpolators with their targets and
  channel selectors, plus optional text keys, intended to be applied
  as a single group. It differs from a raw controller chain in three
  ways: (a) it is loaded as a unit (typically from a KF file rather
  than a NIF); (b) its interpolators are not attached directly to
  controllers in the scene graph but to **blend interpolators** that
  the sequence inserts at activation time (see Q70/Q71); (c) targets
  are resolved by **node name + interpolator-target type name** at
  activation time — looking up `(nodeName, ctrlTypeName)` within the
  scene graph rooted at the manager's target. This name-based binding
  is what lets one KF file animate any character with matching node
  names. The predecessor `NiSequence` class used direct pointer/link
  attachment and is now converted on load.

- **NI-Q70 [documented]** `NiControllerManager` is itself a
  `NiTimeController` attached at the subtree root it manages. It owns
  a list of sequences and a list of currently-active sequences. On
  `Update(time)`, it ticks each active sequence, which in turn evaluates
  its interpolators into the per-sequence side of the blend
  interpolators. The blend interpolator then computes a single result
  per controller target. Documented blending model: **weighted average,
  with priority groups, with cross-fade between the highest and
  next-highest priority groups via an "ease spinner"**. Only sequences
  at the top-priority level contribute fully; lower-priority sequences
  contribute via the ease spinner. Activation/deactivation supports
  fade-in/fade-out time, looping, frequency, and ease curves at the
  sequence level.

- **NI-Q71 [documented]** `NiBlendInterpolator` aggregates multiple
  sub-interpolators and produces a single output value. Each
  sub-interpolator has a weight, a priority, and an ease-spinner
  contribution. Algorithm:
  1. Find the highest priority among active sub-interpolators.
  2. Compute a weighted average of all sub-interpolators sharing that
     priority (using their weights).
  3. If a lower-priority group is also active, compute a weighted
     average for it, then cross-fade between the two results by the
     summed ease spinner of the highest priority.
  4. Sub-interpolators with weight below an internal threshold are
     dropped.
  5. Weights are *not* renormalized — they are used as given. If
     weights don't sum to 1, the result is scaled accordingly.
  An optimization flag `OnlyUseHighestWeight` short-circuits to the
  single dominant interpolator (no blending) when set.

- **NI-Q72 [documented]** Insertion-order semantics: the docs note
  that if two `NiTransformController`s are attached to the same target,
  **whichever runs last wins** — its writes overwrite the first's.
  There is no documented priority field on raw time controllers; the
  priority/blend system lives one layer up in `NiBlendInterpolator`.
  In the legacy `NiKeyframeController` model, only one transform
  controller per node was the documented usage pattern.

- **NI-Q73 [documented]** Application time is passed into the
  controller update as a `float` (`fTime`), supplied by the
  application or computed by `NiTimeController::StartAnimations`. The
  engine does not clamp or scale this time itself; the application can
  pass real wall-clock time, fixed-step time, or scaled time. There is
  no documented per-frame max step. The `APP_TIME` vs `APP_INIT`
  enum on the controller determines whether the controller treats the
  passed time as absolute or rebased to its own start.

- **NI-Q74 [documented]** `NiTextKeyExtraData` stores an array of
  `NiTextKey` (time + string). It is the documented mechanism for
  attaching named markers to an animation timeline. **The interpretation
  of the strings is entirely application-defined** — the SDK does not
  specify a standard vocabulary like "start", "end", "soundN", "loopN".
  The Gamebryo conversion code does specifically look for "start" and
  "end" markers when converting legacy `NiSequence` to
  `NiControllerSequence`, suggesting those two tags were a community
  convention rather than a contractual SDK feature. Anything else (e.g.,
  BC's `"sound:soundname"` or `"event:fire"`) is up to the game runtime.

- **NI-Q75 [documented]** `NiUVController` (deprecated) animates UV
  transform parameters on an `NiTexturingProperty` stage. Replaced by
  `NiTextureTransformController` which targets a specific (property,
  stage, parameter) tuple with an `NiFloatInterpolator`. Parameters:
  translation U/V, rotation (about texture origin), scale U/V.

- **NI-Q76 [documented]** Boolean visibility is animated via
  `NiBoolInterpController` (modern) holding a `NiBoolInterpolator`
  that interpolates boolean keys (typically step-keyed — a value flips
  at each key). The legacy `NiVisController` carries an array of
  visibility keys directly. Either drives `NiAVObject` app-cull state
  on its target.

- **NI-Q77 [documented]** Color/alpha/material animation:
  `NiColorController` (deprecated) → `NiPoint3InterpController` with
  `NiColorInterpolator`. `NiAlphaController` (deprecated) → float
  interp targeting `NiMaterialProperty::SetAlpha`. `NiMaterialColorController`
  targets a specific channel of `NiMaterialProperty` selected by an
  enum (ambient / diffuse / specular / emissive).

- **NI-Q78 [documented]** `NiGeomMorpherController` blends a set of
  morph targets (each is a per-vertex `NiPoint3` array) by per-target
  weights coming from per-target `NiInterpolator`s.
  `NiMorphData::GetRelativeTargets()` controls interpretation: when
  false, each target is an independent absolute vertex set, and the
  blended result is `Σ wᵢ · targetᵢ`; when true, target[0] is the
  base mesh and the others are offsets, giving `target[0] + Σ_{i≥1}
  wᵢ · targetᵢ`. There is no documented weight renormalization — the
  application is responsible for keeping weights sensible.

- **NI-Q79 [documented]** `NiPathController` (deprecated) →
  `NiTransformController` driven by an `NiPathInterpolator`. A path is
  a position curve + an orientation rule ("look along tangent" or
  similar). Banking is supported via a separate float track that rolls
  about the tangent. The replacement interpolator carries its own
  curve representation; the legacy `NiPathController` was a single
  monolithic class.

- **NI-Q80 [documented]** `NiLookAtController` (deprecated) →
  `NiTransformController` driven by `NiLookAtInterpolator`. The look
  target is resolved by a pointer/name reference; an up-vector axis is
  configured; orientation aligns the controlled object's local axis
  (typically +X for a light or camera) to point at the target. Cycles
  are broken arbitrarily by traversal order.

- **NI-Q81 [inferred from source]** Animation curves are **evaluated at
  original key density at runtime**; there is no documented load-time
  resample to a fixed rate. The offline animation-compression tool
  (`NiAnimationCompression` library) can fit B-spline or reduce keys
  before NIF export; at runtime the data is whatever the exporter
  produced.

- **NI-Q82 [not found]** No documented inverse-kinematics in Gamebryo
  1.2 core; IK appears in later Gamebryo versions / 3rd-party plugins.
  Not present here.

## G. Skinning

- **NI-Q83 [documented]** `NiSkinInstance` fields (instance-dependent):
  - Pointer to a shared `NiSkinData`.
  - Root-parent reference (the `NiAVObject` parent of the bone hierarchy
    root — the bind-pose reference frame).
  - Array of `NiAVObject*` bones (one per skin influence; raw pointers,
    not smart pointers).
  - Optional `NiSkinPartition` pointer for hardware skinning.

  `NiSkinInstance` is attached to an `NiGeometry` object (via the
  geometry's `NiSkinInstance` field). Manual skinning APIs exist for
  apps that want to compute deformed positions on the CPU explicitly.

- **NI-Q84 [documented]** `NiSkinData` carries:
  - Number of bones.
  - A `BoneData` array, one entry per bone, each containing:
    - `m_kSkinToBone` (an `NiTransform`) — the **skin-to-bone** bind-pose
      transform (i.e., the inverse-bind matrix for that bone).
    - `m_kBound` — a per-bone bounding sphere computed from the vertices
      that bone influences (used for culling skinned geometry without
      fully evaluating skinning).
    - The per-bone vertex weight list (`BoneVertData[]`): each entry
      is a (vertex-index, weight) pair.
  - `m_kRootParentToSkin` — an `NiTransform` from the root-parent space
    into the skinned mesh's space at bind time.

  The transform direction is **skin-to-bone** at the bone-data level
  (so applying it brings a mesh-space vertex into bone-local space at
  bind time). Combined with bone's current world transform, this gives
  the canonical inverse-bind composition.

- **NI-Q85 [documented]** Vertex weights are stored **per-bone**: each
  bone's `BoneVertData` array carries explicit (vertex-index, weight)
  pairs. There is **no fixed cap** on influences per vertex at the
  format level — a vertex can appear in arbitrarily many bones'
  weight lists. The list is terminated by an explicit count (each bone
  carries the count of vertices it influences). At the hardware-skinning
  layer (`NiSkinPartition`) the cap is **`bonesPerPartition`**, which
  defaults to 4 in the export tools but is configurable up to the
  hardware's matrix-palette limit (or arbitrary via custom vertex
  shaders).

- **NI-Q86 [documented]** The runtime **does not renormalize**
  weights; the format stores them as-exported. Exporters do normalize
  before writing. If weights don't sum to 1, the deformed vertex will
  scale anomalously — the engine assumes the input data is consistent.
  The optional "skin threshold" used at export drops below-threshold
  influences and re-normalizes the survivors before writing.

- **NI-Q87 [documented]** Bind-pose space: each bone's
  `m_kSkinToBone` is in the **bone's local space** (not skeleton root,
  not world). Combined with `m_kRootParentToSkin` (which positions the
  whole skin in the root-parent's frame at bind time), the bind pose
  is fully reconstructed.

- **NI-Q88 [documented]** Linear-blend skinning math:
  `v_world = Σᵢ wᵢ · (B_iᵀ · S_i · v_skin)`,
  where `v_skin` is the bind-pose mesh-space vertex, `S_i` is bone i's
  skin-to-bone transform (the inverse-bind), and `B_iᵀ` is bone i's
  current world transform. Equivalently, each per-bone matrix
  composes "skin-space-to-current-world" via `B_iᵀ · S_i`. The
  `RootParentToSkin` factor adjusts for the root parent's transform
  in mesh local space, applied once. Normals use the same matrix chain
  but with inverse-transpose (see Q91).

- **NI-Q89 [documented]** `NiSkinPartition` is an internal-only
  optimization class (the docs explicitly say it has no supported
  constructors or member functions for application use). It partitions
  the triangle list into subsets such that all triangles in a subset
  reference at most `bonesPerPartition` distinct bones. Each partition
  has its own bone-palette and own (possibly reindexed) vertex/triangle
  data. The renderer iterates partitions, sets the bone-palette
  uniforms, and draws each.

- **NI-Q90 [documented]** `bonesPerPartition` is a **build-time choice**
  passed to `MakePartitions`. The export tools default to **4** (the
  fixed-function pipeline limit on Win32/Xbox). Higher values are
  supported when a custom palette-skinning vertex shader is in use,
  per the `MatrixPaletteSkinning` sample. There is no fixed limit at
  the engine level beyond what the renderer's shader bindings can
  handle.

- **NI-Q91 [inferred from source]** Normals under skinning are
  recomputed at vertex transform time using the same per-bone matrices
  used for positions. For pure rotation+uniform-scale bones (the
  Gamebryo transform model), the inverse-transpose collapses to the
  forward transform (rotations are orthonormal; uniform scale cancels
  in inverse-transpose up to sign), so the engine reuses the position
  matrix. With non-uniform scale (which Gamebryo doesn't support at
  the transform level), this would not hold — and that's part of why
  the transform model restricts scale to uniform.

- **NI-Q92 [not found]** Dual-quaternion skinning is not in Gamebryo
  1.2. Linear-blend only.

## H. Particles and effects

> Major caveat: Gamebryo 1.1 introduced the "new" NiParticle library.
> BC predates that and used the "old particle" system, which now
> lives in a separate `NiOldParticle` library with conversion tools.
> The answers below describe the modern system; for BC, the old
> system applies. The old-particle system had `NiAutoNormalParticles`,
> `NiRotatingParticles`, `NiBSParticleNode`, and a few stock
> modifiers (gravity, planar collision) — far simpler than the modern
> emitter/modifier model.

- **NI-Q93 [documented]** `NiParticleSystem` (modern) is composed of:
  an emitter (`NiPSysEmitter` subclasses), one or more modifiers
  (force, age, collision, color, size, mesh-update, bound-update),
  and a renderer behavior. The `NiPSysData` block holds per-particle
  state arrays. Particle controllers (`NiPSysEmitterCtlr`,
  `NiPSysUpdateCtlr`, modifier-active controllers, etc.) drive
  parameters over time.

- **NI-Q94 [documented]** Emitter shapes in modern NiParticle:
  `NiPSysSphereEmitter`, `NiPSysBoxEmitter`, `NiPSysCylinderEmitter`,
  `NiPSysMeshEmitter`. Each carries per-shape geometry plus shared
  emitter params: speed (mean + variation), declination angle (mean +
  variation), planar angle (mean + variation), color, size, lifespan
  (mean + variation), birth rate, initial rotation.

- **NI-Q95 [documented]** Per-particle state is tracked in `NiPSysData`
  parallel arrays: position, velocity, age, lifespan, color (when
  the color modifier is active), size, rotation, rotation speed,
  rotation axis, and which "subtexture index" if used. Not all
  arrays are present unless the corresponding modifier is in the
  modifier chain.

- **NI-Q96 [documented]** Aging is per-frame: each particle's age is
  incremented by elapsed time; a particle expires when `age >=
  lifespan`. Expired slots are reused on the next emit. The `Update`
  modifier (`NiPSysUpdateCtlr`) drives the age/death pass.

- **NI-Q97 [documented]** Built-in force modifiers:
  `NiPSysGravityModifier` (gravity, with adjustable strength
  controller), `NiPSysDragModifier` (drag), `NiPSysAirFieldModifier`
  (wind), `NiPSysTurbulenceFieldModifier` (turbulence), 
  `NiPSysVortexFieldModifier` (vortex). Each can have its own
  strength controller.

- **NI-Q98 [documented]** Collision: `NiPSysPlanarCollider` and
  `NiPSysSphericalCollider` (and a few related modifiers). Arbitrary
  mesh collision is **not** a stock feature for particles in this
  version.

- **NI-Q99 [documented]** Particle rendering modes: default is
  camera-facing billboards; `NiPSysMeshUpdateModifier` allows
  instanced mesh particles. Axis-locked billboards (rotating about a
  fixed direction, useful for engine trails or magic effects) are
  supported via the rotation modifier with appropriate parameters.

- **NI-Q100 [not found]** No documented stock "ribbon" or "trail"
  primitive distinct from the mesh-particle path in Gamebryo 1.2.

- **NI-Q101 [not found]** No `NiLensFlare` or `NiCorona` block class
  in the SDK. (See section Q for BC-specific speculation.)

## I. Collision

- **NI-Q102 [documented]** Native (pre-Havok) collision lives in the
  `NiCollision` library. Two parallel systems:
  - **Alternate Bounding Volumes** (`NiSphereBV`, `NiBoxBV`, `NiCapsuleBV`,
    `NiUnionBV`, `NiOBBNode`, `NiOBBRoot`, `NiOBBLeaf`) attached to
    scene graph nodes via `NiCollisionObject`.
  - **Triangle-level intersection** primitives (`NiTriIntersect`,
    `NiTrigon`, `NiSegment`) used directly or via collision groups.
  - **Picking** (`NiPick`) for ray queries against the scene graph,
    returning `NiPick::Record` entries.

- **NI-Q103 [documented]** Primitive shapes: sphere (`NiSphere`,
  `NiSphereBV`), box / OBB (`NiBox`, `NiBoxBV`, `NiOBBLeaf`), capsule
  (`NiCapsule`, `NiCapsuleBV`), and triangle (`NiTrigon`). AABB is
  used implicitly via bounding-sphere conversion but is not a
  first-class collision primitive class.

- **NI-Q104 [documented]** Mesh collision uses **OBB tree
  acceleration**: `NiOBBRoot` builds a tree of OBBs over a triangle
  mesh; the root holds the tree and `NiOBBLeaf` holds per-triangle
  data. Triangle-to-triangle queries traverse the OBB hierarchy.
  Per-triangle linear scan is also available via `NiTriIntersect` for
  small meshes.

- **NI-Q105 [documented]** Supported queries:
  - **Ray** (`NiPick::PickObjects` or `NiPick::PickAll`).
  - **Static intersect** (`NiCollisionGroup::TestCollisions` — boolean
    overlap check, current configuration).
  - **Dynamic intersect** (`NiCollisionGroup::FindCollisions` — sweep
    over a time interval, with point/normal of collision).
  - Bound-to-bound (`NiBound::TestIntersect` / `FindIntersect`).

- **NI-Q106 [not found]** No explicit "trigger / sensor" concept
  distinct from solid collision in the core API; an application would
  use a callback on a normal collision query and ignore the response.

- **NI-Q107 [documented]** Dynamic collision *is* the
  "continuous-collision-detection" path for `NiBound` and
  `NiCollisionGroup::FindCollisions` — predictive collision over a
  time interval is exactly what they do. So in that sense, CCD exists
  at the bounding-volume level. Full continuous mesh CCD is not
  documented.

## J. Math and coordinate conventions

- **NI-Q108 [documented]** **Right-handed.**

- **NI-Q109 [documented + inferred]** No fixed engine-level up axis —
  the docs explicitly say Gamebryo makes no requirements about
  world-space "up". The billboard up-axis is model-space [0,1,0]
  *for the billboard itself*. In practice, exported content is
  typically Y-up (3ds max default) or Z-up (Maya default) — content
  pipeline determines this.

- **NI-Q110 [documented]** Forward axis is **+X** for both
  directional lights and spotlights (light shines down model-space
  +X). The camera looks down **-Z in its local frame** (Gamebryo's
  view convention), with camera Up = local +Y and Right = local +X;
  the `NiCamera::Click` path explicitly stores `m_kWorldDir`
  (forward), `m_kWorldUp`, `m_kWorldRight` from the camera's world
  transform.

- **NI-Q111 [inferred from source]** Matrices (`NiMatrix3`) are stored
  as `m_pEntry[3][3]` in row-major C array layout. Math is documented
  as **column-vector**: vectors transform as `v' = M · v`, parent ·
  local is left-multiplication (`OM→W = PM→W · (T·R·S)`). So a
  matrix's columns are the basis vectors of the transformed frame.

- **NI-Q112 [inferred from source]** `NiQuaternion` member layout is
  `m_fW`, `m_fX`, `m_fY`, `m_fZ` — **W first**. On disk, quaternions
  are streamed in this same order. (Note that some downstream tools
  reorder to XYZW; the engine itself is W-first.)

- **NI-Q113 [inferred from source]** Quaternion-to-matrix follows the
  standard formula for a right-handed, column-vector system, applied
  to a unit quaternion `(w, x, y, z)`. A positive rotation about an
  axis is "clockwise looking down the axis toward the origin" per
  the docs — equivalent to the standard right-hand rule with the
  caveat about viewing direction.

- **NI-Q114 [documented]** Euler ordering in `NiEulerRotKey` is
  **XYZ** (rotate X, then Y, then Z, composed left-to-right in the
  column-vector sense). Units are **radians**. The `NiAVObject`
  rotation accessors that take axis-angle also use radians.

- **NI-Q115 [not specified]** Units are **application-defined**. The
  engine has no documented unit convention; scenes are commonly
  "1 unit = 1 meter" (Max default for exporters) or game-specific.

- **NI-Q116 [documented]** `NiCamera` frustum is specified as
  **L, R, T, B, N, F + ortho flag** (asymmetric frustum permitted in
  perspective; in orthographic mode, top/bottom and left/right must
  be symmetric per a runtime assertion). Default L,R,T,B,N,F =
  (-0.5, 0.5, 0.5, -0.5, 1.0, 2.0), ortho=false. Viewport
  ("port") is L,R,T,B in normalized [0..1] screen coordinates,
  default (0, 1, 1, 0). Near and far are positive values; the engine
  enforces a minimum near plane (default 0.1).

- **NI-Q117 [not found]** No documented "center of geometry" or
  "pivot offset" field on `NiAVObject` distinct from the node origin.
  The application would store this externally (e.g., as
  `NiVectorExtraData` on the node).

- **NI-Q118 [documented]** Some swept-volume support exists at the
  `NiBound` level (`TestIntersect`/`FindIntersect` integrate
  velocity over time). Ellipsoid casts are not a stock primitive.

## K. Resource management and lifetime

- **NI-Q119 [documented]** Reference counting is via **`NiPointer<T>`
  smart pointers** wrapping `NiRefObject`-derived classes. Smart
  pointers auto-increment on assignment and auto-decrement on
  destruction; when refcount hits zero the object self-deletes. Raw
  pointer fields are non-owning. By convention each ref-counted class
  has a `T*Ptr` typedef. Cross-block references in NIFs follow this
  model in memory: a child `NiAVObject*` stored in `NiNode` is held
  via smart pointer (so the node owns its children); a target
  `NiAVObject*` stored in a `NiTimeController` is raw (so the
  controller does not retain its target). On-disk these distinctions
  vanish — they're both just link IDs.

- **NI-Q120 [documented + inferred from source]** `NiSourceTexture`
  does **not** automatically deduplicate by filename — each `Create`
  call returns a new `NiSourceTexture` even if the file is the same.
  Renderer-side textures *are* shared via the global preloading
  mechanism (`SetUsePreloading(true)`), so the GPU resource is shared,
  but the engine-side `NiSourceTexture` object is not. Applications
  that want app-side sharing do their own filename→object cache.

- **NI-Q121 [documented]** Mesh sharing follows the
  `NiGeometry`/`NiGeometryData` split: when a scene graph is cloned,
  the `NiGeometry` is duplicated but the `NiGeometryData` is shared
  by smart pointer. Two `NiTriShape`s pointing at the same
  `NiTriShapeData` are the engine's notion of instancing. There is no
  separate "instance node" type at the format level beyond what
  cloning produces.

- **NI-Q122 [documented]** Cleanup is **refcount-driven**: when the
  application releases its last smart pointer to a subtree root, the
  destructor cascades: the root's child smart pointers go out of
  scope → each child's refcount drops → if no other references, child
  destructs → recursive. Order is leaf-first by consequence. There is
  no manual ordering required.

- **NI-Q123 [inferred from source]** Custom allocator hooks exist via
  `NiTAbstractPoolAllocator`, `NiTDefaultAllocator`,
  `NiTPointerAllocator`, `NiTPool` template family — but these are
  per-container allocators, not a global new/delete override. A
  global allocator replacement would happen at platform level.

- **NI-Q124 [documented]** Asynchronous / streaming load **is**
  supported via `NiStream::BackgroundLoadBegin` and progress polling
  via `BackgroundLoadEstimateProgress`. The implementation is
  cooperative — a background loading state machine that processes a
  bounded amount of work per tick. The `BackgroundLoad` sample
  demonstrates it.

## L. Runtime pipeline

- **NI-Q125 [documented + inferred from source]** Documented per-frame
  order in the framework:
  1. Update input.
  2. Process input.
  3. `scene->Update(time)` — refresh transforms + tick controllers +
     refresh bounds.
  4. `camera->Clear(BACK | Z)`.
  5. `camera->Click()` — which internally calls `BeginPaint`,
     starts the sorter, runs `CullShow` (depth-first cull and emit),
     finishes the sorter (draws deferred alpha objects back-to-front),
     and calls `EndPaint`.
  6. Optional second screen-space camera click for HUD.
  7. `camera->SwapBuffers()`.

  Pre-render callbacks exist on individual classes:
  `NiGeomMorpherController::OnPreDisplay` is the documented hook for
  "do work just before draw, after cull decision is made."

- **NI-Q126 [documented]** Culling is **hierarchical bounding-sphere
  vs frustum**. Each node's world-bound sphere is tested against the
  six camera frustum planes; if rejected, the entire subtree is
  skipped. If the bound is fully inside (all planes pass with
  margin), the subtree skips its own plane tests internally — the
  six "active plane flags" track which planes still need testing as
  we descend.

- **NI-Q127 [documented]** Portal culling **is** documented via the
  `NiPortal` library (`NiPortalNode` and friends). PVS is not in the
  core API. Occlusion culling per se is not a built-in feature;
  occlusion volumes attach via `SetDisplayObject` as a hook for
  third-party occlusion.

- **NI-Q128 [documented]** Default sorter (`NiAlphaAccumulator`)
  emits **opaque objects in traversal order** (front-to-back-ish
  only by virtue of how scenes are typically structured;
  Z-buffer is doing the real visible-surface determination), then
  **alpha-blended objects sorted back-to-front by bounding-sphere
  center depth**. The sort key is pure depth, not material-aware.
  A custom `NiAccumulator` subclass can implement state-sorted
  opaque drawing.

- **NI-Q129 [not formally documented as a sort guarantee]** The
  default accumulator does not state-sort opaque batches. The
  renderer libraries do internal state-change minimization at the
  device level. State-sorted accumulators are described as
  application-customizable.

- **NI-Q130 [documented]** Multi-viewport support is via multiple
  `NiCamera` objects with different `Port` rectangles set on the
  same renderer; the framework's screen-space camera idiom is one
  example.

## M. Extension surface (relevant to BC's custom blocks)

- **NI-Q131 [documented]** The registration mechanism is the
  **RTTI-name-keyed creation-function map**. A class declares its
  RTTI via the `NiDeclareRTTI` macro and its streaming via
  `NiDeclareStream`; the application invokes a registration call at
  startup that inserts `(className → CreateObject)` into the global
  stream-loader map. There is no reserved version range for vendor
  classes; the format simply uses the class name as the key. BC's
  custom blocks (`*Source`, `*EngineFlare`, etc., per its content
  files) are registered this same way by BC's runtime.

- **NI-Q132 [documented]** Custom properties subclass `NiProperty`,
  declare RTTI + streaming, and override `Update` / `IsEqualFast`
  as needed. To participate in the render pipeline they must also
  implement the renderer-side hooks (the renderer queries
  `NiProperty::GetType()` and looks up its handling); in practice
  custom *renderable* properties require renderer-specific changes,
  while custom *data-carrying* properties (no GPU state effect) are
  easy.

- **NI-Q133 [documented]** Custom controllers subclass
  `NiTimeController` (or one of the typed `NiInterpController`s),
  declare RTTI + streaming, implement `Update(float)` (and target
  attachment hooks via `SetTarget`). Same pattern as custom
  properties.

- **NI-Q134 [documented]** `NiExtraData` is **the** canonical
  extension hook for attaching app-specific data to any
  `NiObjectNET`. Stock subclasses include:
  - `NiBinaryExtraData` (raw byte blob),
  - `NiBooleanExtraData`, `NiIntegerExtraData`, `NiFloatExtraData`,
    `NiColorExtraData`, `NiVectorExtraData`, `NiStringExtraData`,
  - `NiIntegersExtraData`, `NiFloatsExtraData` (arrays of those),
  - `NiSwitchStringExtraData`,
  - `NiTextKeyExtraData` (animation markers — see Q74).

  Applications routinely add their own subclasses for engine-specific
  per-node data (e.g., BC's hit-point markers, weapon-mount points,
  etc., likely live as custom extra data).

- **NI-Q135 [inferred]** Plugin/DLL hot-load is not documented as a
  stock feature. Custom-block registration must run at application
  startup; once registered, the loader can handle those blocks. No
  documented "load this DLL and let it register new block types"
  mechanism — but the registration API itself is callable from
  anywhere, so apps that build their own DLL system can do it.

- **NI-Q136 [not found in this form]** There is no documented
  filename-substring-match LOD attach API on `NiNode` or `NiLODNode`.
  `NiLODNode` accepts children at fixed integer slots determined by
  its `NiLODData`. The closest documented mechanism is
  `NiAVObject::GetObjectByName` for runtime tree search — an
  application could write its own "find every node whose texture
  ends in `_glow` and add a sibling node" routine on top, which is
  consistent with BC's `AddLOD` pattern being **a BC engine
  extension on top of standard NIF, not a stock SDK function**.

- **NI-Q137 [documented]** Geometry swap while preserving transform
  and skinning binding: yes, in two ways. (a) Replace the
  `NiGeometryData` on an existing `NiGeometry` (the geometry's
  position/topology changes; its transform/property stack/skinning
  binding does not). (b) Detach/attach `NiGeometry` children of a
  shared `NiNode` parent. For skinned geometry, replacing the
  geometry data while keeping the same `NiSkinInstance` works as long
  as vertex counts match the skin data's expectations.

## N. Audio (long-shot)

- **NI-Q138 [documented]** The SDK includes an audio library
  (`NiAudio`) with these stock classes: `NiAudioSystem`,
  `NiAudioSource`, `NiAudioListener`. Plus a Miles-Sound-System
  backend implementation (`NiMilesAudio`: `NiMilesAudioSystem`,
  `NiMilesSource`, `NiMilesListener`). The audio classes are
  **runtime objects, not NIF block types** — they are not loaded
  from NIF files. `NiAudio` is documented as added with Gamebryo;
  whether NetImmerse 3.1 (BC era) shipped an equivalent is unclear.

- **NI-Q139 [documented]** `NiAudioSource` data model: a file or
  buffer reference (format auto-detected per platform/provider),
  loop flag, volume, pitch, 3D positional parameters (position,
  velocity, min/max distance, cone angles for directional sources).
  Position is in world space (the listener pose drives spatialization).

- **NI-Q140 [inferred]** `NiTextKeyExtraData` carries arbitrary
  strings; the audio system has no built-in "play this sound on
  this text key" wiring. The application reads the text-key list
  during animation playback and fires audio events itself — this is
  the standard pattern.

## O. Tools, samples, and test data

- **NI-Q141 [inferred from source]** The canonical "load and render a
  NIF" sample is `Samples/Tutorials/03 - NIF Files`. Its top-level
  flow:
  1. Create renderer (DX8 or DX9 select).
  2. Create an `NiAlphaAccumulator` and set it as the renderer's sorter.
  3. Create an `NiStream`. Call `Load("WORLD.NIF")`.
  4. Take the first top-level object (`GetObjectAt(0)`), cast to
     `NiNode` — that is the scene root.
  5. Recursively walk the scene graph looking for an `NiCamera`; bind
     it to the renderer.
  6. Bind the scene root to the camera as its scene.
  7. Call `scene->Update(0)`, `scene->UpdateProperties()`,
     `scene->UpdateEffects()`, `camera->Update(0)` — initial state.
  8. Enter the application's `OnIdle` loop, which each frame:
     `Clear`, `Click` (the camera, which does cull + draw), optional
     screen-space pass, `SwapBuffers`.

  The application framework (`NiApplication`) wraps the OS message
  loop and calls `OnIdle` once per available time slice.

- **NI-Q142 [documented]** Notable samples shipped with the SDK
  (under `Samples/Demos/` and `Samples/Tutorials/`):
  - Tutorials: `01-Basic`, `02-Renderers`, `03-NIF Files`,
    `04-Scene Attachment`, `05-Transforms`, `06-Time Controllers`,
    `07-User Input`, `08-Screen Texture`, `09-Rendered Texture`.
    Each progressively builds on the previous.
  - Demos: `CharacterAnimationDemo`, `CharacterPerformanceDemo`
    (skinned animation + blending), `MatrixPaletteSkinning`
    (hardware skinning), `VertexMorphing` (`NiGeomMorpherController`),
    `CollisionTestStatic`, `CollisionTestDynamic` (`NiCollisionGroup`),
    `MousePicking`, `ObjectPick` (`NiPick`), `BackgroundLoad`
    (async loading), `ShadowMap`, `StencilShadow`,
    `VertexLightingPipeline`, `CubeMap`, `AdvancedMultitexture`,
    `DynamicTexture`, `ShaderSample`, `ProfileSample`.

- **NI-Q143 [not found]** No conformance / regression suite with
  reference NIFs and expected outputs is documented in the SDK
  Documentation tree.

- **NI-Q144 [documented]** SDK tools include:
  - **3ds max plugin** (export and tool palettes) and **Maya
    plugin** (analogous), both with NIF export, KF export,
    animation manager, switch-node / LOD setup tools, bone-LOD,
    optimization options.
  - **SceneViewer** (a NIF browser GUI: loads NIF, displays scene
    graph as a tree, properties inspector, animation playback).
  - **AnimationTool** (KF authoring/editing).
  - **NiPluginToolkit** + **ArtPlugins** (extension framework for
    third-party tooling).
  - Command-line tools under `Tools/DeveloperTools` for
    optimization, stripification, image quantization, animation
    compression.

- **NI-Q145 [not found]** No documented "minimal scenes for
  debugging" set.

## P. Documentation structure

- **NI-Q146 [documented]** Top-level documentation tree (the
  `Gamebryo.chm` table of contents):
  - **Welcome to Gamebryo** (overview).
  - **Getting Started with Gamebryo** (platform-specific
    bring-up).
  - **Learning Gamebryo** (tutorial-style walkthroughs).
  - **Programmer's Guide** — covers Programming Basics, Object
    Systems (general + internal), Scene Graph, Scene Rendering,
    Texturing, Special Effects (lighting, dynamic effects),
    Skinned Objects, Content Import/Export, NiShader, NiProfile,
    UpdateSelected/performance, threading, optional features
    (collision, portals, audio).
  - **Reference** — class-by-class reference grouped by library
    (`NiMain`, `NiAnimation`, `NiCollision`, `NiAudio`, `NiPortal`,
    `NiParticle`, `NiOldParticle`, `NiSystem`, `NiShader`,
    renderer libs, tool libs, app frameworks).
  - **Tool Manuals** (3ds max plugin, Maya plugin, Scene Viewer,
    Animation Tool, etc.).
  - **What's New in Gamebryo** (per-version changelogs and
    conversion guides — 1.0 → 1.1, 1.1 → 1.2, plus per-platform
    release notes).
  - **Artist's Guides** (3ds max and Maya plugin user manuals).

- **NI-Q147 [documented]** Diagrams in the docs include: a
  partial-hierarchy diagram of `NiObject`-derived classes (in the
  RTTI topic), a texture-pipeline data-flow diagram (showing each
  multitexture stage as a box and inter-stage flow as arrows), and
  several sorting / hierarchical-sort illustrations showing how
  `NiSortAdjustNode` partitions the cull walk. There are also
  step-by-step diagrams of the streaming process (object
  registration → save → linkID resolution → load).

- **NI-Q148 [documented]** Gotcha topics covered:
  - `Update` correctness vs efficiency tradeoff (batching).
  - `SelectiveUpdate` flag misconfiguration ("results may not be
    correct").
  - Never `delete` a smart pointer.
  - Property stack: one property per type per object.
  - `NiAlphaAccumulator` interactions with mid-graph `NiSortAdjustNode`
    can produce surprising draw order.
  - `NiSkinPartition` partition count drives skinning performance more
    than vertex count.
  - Default texture filter / clamp choices per map type (see Q41).
  - `APP_TIME` vs `APP_INIT` semantics for controller timing.
  - `NiTimeController::SetTarget` is the only way to attach a controller
    correctly (don't call `PrependController` directly).
  - Static-vs-dynamic `NiSourceTexture` flag must be set for textures
    that will be modified after creation.

- **NI-Q149 [documented]** Version conversion notes between Gamebryo
  versions exist as dedicated topics:
  - Gamebryo 1.0 → 1.1: input handling overhaul; particle system
    rewrite (with conversion library).
  - Gamebryo 1.1 → 1.2: animation conversion notes (old
    `NiKeyframeController` deprecated in favor of
    `NiTransformController` / `NiInterpolator` split).
  - Per-platform release notes (DX8, DX9, PS2).

  **No release notes covering NetImmerse 3.x → 4.x → Gamebryo 1.0
  transitions** appear in this SDK's docs — those would be in the
  pre-Gamebryo NetImmerse documentation, which isn't here.

## Q. BC-specific cross-references

- **NI-Q150 [not found — strong negative evidence]** The SDK's
  `NiLODNode` is **distance-band-driven via `NiLODData`** (see Q20).
  There is no API on `NiNode`, `NiLODNode`, or any global manager
  that "adds an alternate LOD level after load by texture-name
  pattern" or that registers a runtime override of a node's content
  by filename substring. The BC `AddLOD("..._glow", ...)` pattern
  has no equivalent in the stock SDK and is almost certainly a
  **BC-specific engine extension**, layered on top of NIF via BC's
  Python-callable scripting layer. Implementation-wise the most
  likely shape: BC walks the loaded scene graph, finds geometry
  whose base texture name matches a pattern, and either creates a
  sibling `NiTriShape` with an additive glow texture (drawn after
  via `NiAlphaProperty` with `ALPHA_ONE` / `ALPHA_ONE` blending and
  the no-sort flag) or attaches it as a custom extra-data marker
  resolved at render time.

- **NI-Q151 [not found — strong negative evidence]** No `NiCorona`,
  `NiLensFlare`, or `NiSunCorona` block class in this SDK. Sun /
  corona / lens-flare effects appear to be **BC application-level**
  primitives, likely built from `NiBillboardNode` + additive-blend
  geometry + custom controllers, possibly using stock
  `NiTextureEffect` for cube/sphere mapping.

- **NI-Q152 [not found]** No documented "center of geometry" or
  "pivot offset" field on `NiAVObject`. The NIF origin is the only
  documented model-space anchor; deviation from the visual centroid
  is a content/artist decision. BC ships rotating around the NIF
  origin is consistent with this; the workaround is to store the
  centroid offset in custom extra data or to translate the geometry
  data at export.

- **NI-Q153 [not found in this exact form]** No stock "stretched
  billboard" / "speed-elongated" particle primitive. Closest path
  in the modern particle library is a custom modifier that updates
  per-particle scale and rotation from velocity; in the old
  particle system, this would have been a custom particle subclass
  or a property animator on a billboard quad. BC's engine trails
  were likely custom rendering, not a stock SDK feature.

- **NI-Q154 [not found]** No "emissive-only at distance" or
  "self-illumination distance" knob in `NiMaterialProperty`,
  `NiTexturingProperty`, or `NiVertexColorProperty`. Distance-faded
  running lights would be built application-side, probably by a
  custom controller that animates emissive color based on
  camera-distance.

- **NI-Q155 [not found]** No documented decal-projection API at
  this SDK version. Decals at the texturing-stage level
  (`Decal 0..N` on `NiTexturingProperty`) are *texture-coordinate
  driven*, not screen/world-projected at runtime. Dynamic hit
  decals would be application-implemented atop `NiTriShape`.

## R. Engineering hygiene observations

- **NI-Q156 [documented]** Threading model is documented as **the
  scene graph is not thread-safe; render-thread only touches the
  scene graph, with caveats**. Specific protected operations:
  property updates have a static critical section
  (`LockPropertyUpdate`/`UnlockPropertyUpdate`). Background NIF
  loading runs on a worker thread but synchronizes at the
  application-visible API boundary. Textures have a separate
  threading discussion (uploads can be deferred). General rule:
  prepare data on worker threads, mutate scene graph only on the
  render thread.

- **NI-Q157 [inferred]** Diagnostics: `NiOutputDebugString` for log
  output (platform-specific implementation, hooks into Windows
  `OutputDebugString` or PS2 equivalent). Per-class profiling
  counters on `NiAVObject` (update time, draw time, frames culled,
  etc., available only in Profile builds). Full `NiProfile` library
  for hierarchical profiling instrumentation.

- **NI-Q158 [inferred]** Error-handling style: a mix of:
  - Return-bool / return-pointer-or-NULL for "soft" failures (file
    not found, can't create a texture).
  - `assert` for invariant violations (debug builds only).
  - Per-class `m_uiLastError` + `m_acLastErrorMessage` on `NiStream`
    for diagnostic-quality reporting.
  - No C++ exceptions are thrown by stock engine code.

- **NI-Q159 [documented]** Yes — `SceneViewer` is a documented
  diagnostic GUI for "load this NIF and inspect what's in it,"
  showing scene-graph tree, per-node properties, controller list,
  bounding volumes, and skin-partition counts. There is also a
  `Dump` / `Print` family on some classes used by sample debug
  output.

---

## Not-found list

The following questions could not be answered from this SDK and
documentation set:

- **NI-Q9** — Compressed NIF variants.
- **NI-Q10** — Checksums / signatures.
- **NI-Q34** — Vertex-cache-order hints in the format.
- **NI-Q52** — Multi-pass fallback spec at the format level.
- **NI-Q58** — Projected light textures / shadow primitives at the light
  class.
- **NI-Q82** — IK support.
- **NI-Q92** — Dual-quaternion skinning.
- **NI-Q100** — Stock ribbon/trail particles.
- **NI-Q101** — `NiLensFlare` / `NiCorona` block classes.
- **NI-Q106** — Trigger/sensor concept distinct from collision.
- **NI-Q115** — Default linear units.
- **NI-Q117** — "Center of geometry" / pivot offset field on `NiAVObject`.
- **NI-Q123** — Memory-allocator hook (custom global new/delete).
- **NI-Q129** — State-sorted opaque batches as a default sort guarantee.
- **NI-Q143** — Conformance / regression NIF test suite.
- **NI-Q145** — Canonical minimal debug NIFs.
- **NI-Q150** — `AddLOD` / glow-by-filename API.
- **NI-Q151** — `NiCorona` / `NiLensFlare` / `NiSunCorona`.
- **NI-Q152** — Pivot offset field.
- **NI-Q153** — Stretched/speed-elongated particle mode.
- **NI-Q154** — Distance-attenuated emissive knob.
- **NI-Q155** — Decal-projection API.

Eight of these are "negative space" confirmations for BC-specific
speculation (Q150-Q155) — and the *absence* of those features in the
stock SDK is itself the load-bearing finding: those BC features must be
application-level extensions, not undocumented engine capabilities.

---

## Cross-version disclaimer

This SDK is Gamebryo 1.2.2 (June 2006). Bridge Commander shipped in 2002
against NetImmerse 3.x/4.x. While the architecture is continuous, expect
the following drift:

- **Animation:** BC uses `NiKeyframeController` + `NiSequence` (legacy).
  This SDK documents both legacy and modern (`NiTransformController` /
  `NiControllerSequence` / `NiInterpolator`) paths and ships a
  conversion library. The on-disk key formats (Lin/Bez/TCB/Step/Euler)
  are unchanged.
- **Particles:** BC uses the "old particle" system, now in
  `NiOldParticle` with conversion. Old-particle internals are not deeply
  documented in the current docs; behavior must be inferred from the
  conversion library.
- **Shader system:** Gamebryo's `NiShader` framework is newer than BC;
  BC's rendering is fixed-function multitexture, no programmable
  shaders.
- **NIF format minor versions:** The 3.1-era NIF format differs in
  field-level details (some properties added/removed, some flag bits
  repurposed) from the format documented here. The loader in this SDK
  still understands 3.3.0.11 upward, so its handling of those legacy
  fields is a fair guide, but version-gated branches in the readers are
  what really define the on-disk schema for any specific version. A
  per-version field-by-field treatment would need the actual NIF reader
  source per block class, which I have not enumerated here.
