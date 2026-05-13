# NetImmerse / Gamebryo SDK — Supplementary Findings for a Modern Reimplementation

Things the questionnaire didn't ask about but that turn out to matter once you
sit down to actually rebuild a NIF renderer. Organized by "thing that
surprised me" rather than by subsystem.

Same clean-room rules as the answer doc: behavior in prose, public class
names only, no source paste, confidence tagged.

---

## 1. File formats beyond .NIF you'll meet in BC-era content

The questionnaire treats the format as just "NIF", but the SDK distinguishes
**at least five sibling file formats**, all routed through the same
`NiStream` and built on the same link-ID streaming model:

- **`.NIF`** — Scene graph (nodes, geometry, properties, lights, textures).
  The main format.
- **`.KF`** — Keyframe / animation clips. A KF file contains one or more
  `NiControllerSequence` (modern) or `NiSequence` (BC-era) objects with their
  interpolators and animation key data, **without** the scene graph itself.
  Designed to be applied to a separately-loaded NIF whose node names match.
- **`.KFM`** — Keyframe Manager / actor state machine. Originally ASCII text;
  became binary in Gamebryo 1.2. Drives `NiActorManager`: lists the NIF
  file + KF files for an actor, names each sequence with a stable ID, and
  encodes the allowed transitions between sequences (a state machine the
  engine walks).
- **`.NSF` / `.NSB`** — NiShader source / binary shader-library files. The
  programmable-shader system uses these as out-of-NIF assets. (Post-BC
  feature; included for completeness.)
- **NIF-as-texture** — `NiNIFImageReader` registers itself as an image
  reader, meaning a texture *can* be packaged as a NIF blob holding a
  single `NiPixelData`. Useful to know if you encounter a NIF where a
  `NiSourceTexture::Create` filename ends in `.nif`.

Additionally, BC almost certainly uses **custom file extensions** for the
same on-disk format. The streaming layer doesn't care about the extension;
it just looks for the `"File Format"` substring in the first line. So any
file whose first 80 bytes contain that substring is a NIF-stream-compatible
file regardless of extension.

**Implication for reimplementation:** your loader needs to be a streaming
loader, not a NIF-specific parser. The same loader handles KF and any other
custom NIF-like format. Detect by first-line content, not extension.

---

## 2. The on-disk structure has a precise, generic shape

Pulling everything together from the source, the actual byte layout of a
file from this SDK is:

```
1. Header line: ASCII C-string "Gamebryo File Format, Version a.b.c.d\n"
   (predecessor NetImmerse builds wrote "NetImmerse File Format, ..."; the
    loader's substring check is on "File Format" alone)
2. NIF version: u32, packed bytes (a<<24)|(b<<16)|(c<<8)|d
3. [iff version >= 10.0.1.8] User-defined version: u32
4. Total object count: u32
5. RTTI table:
   - RTTI name count: u16
   - For each name: length-prefixed C-string (name of a class)
   - For each object slot (in order, count from step 4):
     a u16 index into the RTTI name table
6. [iff newer NIF] Object groups table:
   - Group count: u32
   - For each group: u32 byte size
7. Object bodies, one per slot, in slot order:
   - Each body is whatever the class's stream-save routine writes,
     using fixed-size primitives + link IDs to other slots
8. Top-level objects:
   - Count: u32
   - For each top-level: u32 link ID
```

**Section 7 is the variable part**; every class defines its own body layout
in its stream-save routine. Sections 1–6 are uniform across all files
from this SDK.

[inferred from source]

---

## 3. The RTTI table at the top is the schema directory

This is worth restating because it's how a clean-room loader actually scales:

The RTTI table at file head is the **only thing that tells you which classes
are in the file**. Each object body's class is determined by `body_index →
RTTI table → class name string`. So you can:

- Pre-scan the RTTI name list before reading any body, decide which classes
  you support, and **fail gracefully early** if an unsupported class is
  present (the stock SDK aborts; a clean-room reimpl can do better, e.g.
  skip-and-warn if it knows the body size).
- Use the RTTI name list as a sanity check that the file is what you think
  it is (a character animation NIF will have `NiControllerSequence`,
  `NiTransformInterpolator`, etc., near the top of the RTTI list).
- Detect BC custom blocks immediately: any RTTI name not in the stock
  Gamebryo set is a custom block.

**Practical advice:** keep an enum of "known RTTI names" in your loader,
and dispatch body-reading by that enum. New custom blocks become a one-line
addition.

[inferred from source]

---

## 4. The "controller chain" data model is more subtle than a list

The questionnaire treats controllers as a linked list, which is true, but
there's more architecture in the SDK:

- **One controller targets one object**, via `NiTimeController::m_pkTarget`.
  Targets are reached via the controller's `Prev`/`Next` siblings only —
  the target itself holds the head pointer.
- **`NiMultiTargetTransformController` is a single controller that drives
  many targets simultaneously.** Documented as a performance optimization
  for character skeletons: rather than one controller per bone (N controllers
  × N target writes per frame), one controller writes to N bones from one
  iteration. `NiControllerSequence` automatically inserts one of these into
  the scene graph if it doesn't find one already.
- **`NiBoneLODController` automatically disables / re-enables groups of
  bones based on LOD level.** Distance-based skeletal-LOD without touching
  the skin instance.
- **Interpolators and controllers are decoupled.** A modern controller
  (`NiSingleInterpController` family) holds one interpolator; the
  interpolator computes the value, the controller writes it to the target.
  The legacy controllers (`NiKeyframeController`, `NiAlphaController`, etc.)
  combine the two. For BC-era content, expect monolithic legacy controllers.

[documented]

---

## 5. Animation sequences resolve by (node name, controller type), not by pointer

This is mentioned obliquely in the answer doc but matters a lot for content
sharing.

`NiControllerSequence` stores, for each of its sub-interpolators:
- The **target node name** (e.g., `"Bip01 L UpperArm"`)
- The **controller type RTTI name** (e.g., `"NiTransformController"`)
- The **interpolator** itself (without a target)

At sequence activation, the manager walks the scene graph from its root,
calls `GetObjectByName(nodeName)`, finds the controller of the right type
on that node, and binds the interpolator to it. This is why one KF clip
can drive any character whose skeleton uses the same bone names.

**For BC-era `NiSequence`:** the analogous resolution was simpler but
similar — by name + class — and is what got converted to the modern
sequence model at load time by `NiOldAnimationConverter`. Looking at the
old `NiSequence` class would tell you BC's exact lookup keying; I haven't
gone that deep.

**Implication for reimplementation:** name uniqueness matters. Two nodes
with the same name in the same skeleton creates ambiguous sequence
binding. The exporters enforce this.

[documented]

---

## 6. Object groups: a load-time memory-layout trick worth knowing about

`NiObjectGroup` (introduced post-BC) is a feature where multiple objects
declare themselves as belonging to a "group" and the streaming system
allocates them into a single contiguous block at load time. The on-disk
form encodes: group count + total bytes per group + per-object membership.

**Why it's there:** post-load memory locality. All the geometry-data
objects for a single skinned character end up in one allocation, which
helps cache behavior during draw and dramatically reduces malloc traffic
on consoles.

**For BC-era content this section is absent.** But if you reimplement and
want to handle newer Gamebryo files too, this is one of the post-NetImmerse
additions to plan around. The loader needs to read the group table even if
it ignores the layout hint.

[inferred from source]

---

## 7. `NiTextureEffect` is where dynamic env-maps / projected textures live

The questionnaire asked about cube/env maps under properties, but the
actual mechanism is via the **dynamic-effect** system (alongside
lights), not the property stack.

- `NiTextureEffect` is a `NiDynamicEffect` (like `NiLight`).
- It attaches to a `NiNode` via `AttachEffect`, affecting the subtree.
- It carries a texture, a clip plane, and a texture-coordinate generation
  mode (`WORLD_PARALLEL`, `WORLD_PERSPECTIVE`, `SPHERE_MAP`, `SPECULAR_CUBE`,
  `DIFFUSE_CUBE`).
- The renderer inserts an additional texture stage in the affected
  subtree's draw with these generated coords.

This is **the** documented mechanism for things like environment-mapped
reflections, projected spotlights (texture-as-light cookie), and
sphere/cube mapping on fixed-function hardware. BC's reflective ship hulls,
if any, would use this. The clipped-projected-textures variant counts as
"2 textures" against the multitexture stage budget.

[documented]

---

## 8. Sorting has more knobs than just the alpha accumulator

Beyond `NiAlphaAccumulator` (default) and the no-sort flag, the SDK has:

- **`NiSortAdjustNode`** (`NiNode` subclass): mid-scene-graph sorter
  push/pop. Modes: `SORTING_INHERIT`, `SORTING_OFF` (subtree draws in
  traversal order, regardless of alpha), `SORTING_SUBSORT` (uses a
  locally-attached sorter for the subtree, then pops). Use cases:
  skybox drawn first regardless of position, HUD drawn last, in-engine
  sub-scenes.
- **`NiBSPNode`**: an `NiNode` whose left/right children are split by a
  plane. Documented use is "gross-scale" sort separation, not per-poly
  BSP. The renderer picks the side the camera is on first.
- **`NiAccumulator` is subclassable.** Applications can install their own
  sorters (front-to-back opaque, material-sort, etc.).

**Implication for reimplementation:** the sort architecture is layered.
A naive reimpl can do "opaque traversal order + alpha back-to-front by
sphere center" and handle 95% of content. The remaining 5% (BC's HUD,
sky, etc.) needs `NiSortAdjustNode` semantics or equivalent.

[documented]

---

## 9. Renderer constraints that constrained content

Reading the DX8 renderer notes pins down what artists could and couldn't
do at this era, which determines what shapes of content you have to
support:

- **Maximum 8 simultaneous lights** per object (DX8 fixed-function T&L
  limit). Gamebryo drops lights beyond this — and crucially **without
  any documented distance/influence priority**, so artists were expected
  to scope lights to small subtrees.
- **Maximum 8 texture coordinate sets per vertex.**
- **Hardware skinning requires at least 4 bones per matrix slot** and a
  properly-partitioned `NiSkinPartition`. Otherwise software skinning
  runs (still optimized, but slower).
- **Multitexture stages auto-detected** from the GPU; combinations that
  exceed single-pass limits split into multiple passes via alpha
  blending. The renderer's per-stage state inference is documented as
  "not currently checking compatibility" — meaning artists used
  conservative combinations to avoid driver bugs.
- **The renderer expects geometry as `NiGeometry`-derived with a
  per-class vertex buffer cache.** Geometry marked as changed
  (`MarkAsChanged`) repacks its VB next frame. Morphed and skinned
  geometry are repacked every frame and are flagged as the slow path.

[documented]

---

## 10. The `NiGeometryGroup` family is the documented batching strategy

Not in the questionnaire but worth understanding: in newer Gamebryo the
renderer uses **geometry groups** — explicit application-side hints that
group static geometry into shared vertex buffers for fewer state changes.
`NiGeometryGroupManager` handles registration; groups can be marked
static or dynamic. The DX8/DX9 renderers consult the group manager when
packing VBs.

**BC-era engines didn't have this**, but if you reimplement to a modern
GPU you'll want the equivalent batching. The documented advice in the
SDK is: "place geometry into an appropriate `NiGeometryGroup`" for both
performance and memory.

[documented]

---

## 11. Portals: BC may use this for ship interiors

The `NiPortal` library is a fully documented portal-visibility system:

- **`NiRoom`** — convex volume defined by `NiRoom::Wall` planes
  (one-sided oriented planes).
- **`NiPortal`** — one-way "from-through-to" visibility connection
  between a room and an adjoining piece of scene graph (the "adjoiner").
  Portals carry a convex polygon for the through-shape.
- **`NiRoomGroup`** — a top-level grouping of mutually-visible rooms;
  effectively "a level".
- **Fixtures** — non-special geometry attached as children of a room.
- Portals are one-way. Bidirectional connectivity needs two portals.
- Portal-adjoiner is **not** a parent-child scene-graph relationship.

BC's ship-interior tour mode (walking around the bridge) is a plausible
use case for `NiPortal`. If BC's ship-interior NIFs contain
`NiRoom`/`NiPortal` blocks, this is the system; otherwise BC built its
own occlusion.

[documented]

---

## 12. The cloning system distinguishes shallow / deep / by-streaming

Three documented copy modes for `NiObject`:

- **`Clone()`** — Smart clone: structural copy of the scene graph,
  geometry-data and other "shareable" objects (`NiGeometryData`,
  `NiSkinData`, `NiSourceTexture`, `NiMorphData`) are **shared by
  smart pointer**, not duplicated. Use this for instancing a character
  or model.
- **`CreateDeepCopy()`** — Stream the object to a memory buffer, then
  stream it back as new objects. Everything is duplicated, no
  sharing. Use when you genuinely need an independent copy
  (e.g., to mutate one instance's vertex data without affecting
  others).
- **Default name-copy policy** is `COPY_UNIQUE` — clones append a
  single character to their name to keep `GetObjectByName` working.
  `COPY_EXACT` keeps names identical (needed for animation sequences
  to bind to clones). `COPY_NONE` clears names. This is a global
  static; the `NiControllerManager` docs specifically warn to set
  `COPY_EXACT` before cloning anything that animation sequences will
  retarget to.

**Implication:** when you instance ships in BC, you almost certainly
want shallow `Clone()` with `COPY_EXACT` so animations keep working.

[documented]

---

## 13. Lifecycle rules: `NiInit` / `NiShutdown`, no statics

Hard rule from the SDK: **do not create static or stack-allocated
`NiRefObject`-derived objects.** Reasons:
- Refcount lifetime expects heap allocation.
- The engine has explicit `NiInit()` / `NiShutdown()` boundaries; static
  objects could be destroyed after shutdown.
- The runtime is designed to detect leaks post-`NiShutdown` and would
  flag any pre-main allocations.

A clean-room reimpl can ignore this rule (use RAII / heap exclusively /
ARC-style refcount as preferred), but if you read sample code and
wonder why everything is `new NiXxx`, this is why.

[documented]

---

## 14. The math library has more than just basic types

Things you'll need but the questionnaire didn't ask about:

- **`NiTransform`** — combined translation (`NiPoint3`) + rotation
  (`NiMatrix3`) + scalar uniform scale. Most controllers operate on
  this struct as a whole.
- **`NiQuatTransform`** — same conceptually but with a `NiQuaternion`
  in place of `NiMatrix3`. Used by modern animation
  (`NiTransformInterpolator` outputs this).
- **`NiBound`** — bounding sphere with stale-flag.
- **`NiFrustum`** — L, R, T, B, N, F, ortho-bool.
- **`NiPlane`**, **`NiSegment`**, **`NiTrigon`**, **`NiBox`**,
  **`NiSphere`**, **`NiCapsule`**, **`NiParallelogram`** —
  collision primitives.
- **`NiSqrDistance`** — utility class with squared-distance functions
  between every primitive pair.
- **`NiMath`** — static-method math utilities (line-plane intersection,
  closest-point queries, etc.).

The `NiPoint3` layout is just three contiguous floats `x, y, z` — no
SIMD padding by default on platforms where it's not needed; there's a
data-alignment macro (`NI_DATA_ALIGMENT`) used in places like
`NiQuaternion` (aligned to 16 bytes) for SIMD on platforms that benefit.

[inferred from source]

---

## 15. The animation key universe is larger than five families

Beyond the five families (Lin / Bez / TCB / Step / Euler), there's a
parallel **B-spline compressed** track family for offline-compressed
animations:

- `NiBSplineInterpolator` (abstract).
- `NiBSplineColorInterpolator`, `NiBSplineFloatInterpolator`,
  `NiBSplinePoint3Interpolator`, `NiBSplineTransformInterpolator`.
- Compressed variants (`NiBSplineCompXxxInterpolator`) that quantize
  control points further.
- `NiBSplineBasis`, `NiBSplineBasisData`, `NiBSplineFit` — the math
  side.

**Post-BC.** Bridge Commander predates this entirely. Listing it because
if you reimplement to handle Skyrim-era or Oblivion-era NIFs (same
engine family), you'll need these. For BC-only, ignore.

[documented]

---

## 16. The "old particle" world: what BC actually uses

The questionnaire's particle answers covered the modern (Gamebryo 1.1+)
system. The **old particle** system that BC uses has different classes,
all preserved in this SDK under the `NiOldParticle` library:

- **`NiParticleSystemController`** — the orchestrator (a `NiTimeController`).
- **`NiAutoNormalParticles`** / **`NiRotatingParticles`** — particle-set
  scene-graph leaves (the "renderer" side).
- **`NiPerParticleData`** — per-particle SOA-style state.
- **Modifiers** (chained on the controller):
  - **`NiParticleModifier`** (base).
  - **`NiEmitterModifier`** — generates particles.
  - **`NiGravity`** — gravity / wind / point gravity.
  - **`NiParticleBomb`** — explosive impulse.
  - **`NiParticleCollider`** (base) / **`NiPlanarCollider`** /
    **`NiSphericalCollider`** — collision response.
  - **`NiParticleColorModifier`** — color over lifetime.
  - **`NiParticleGrowFade`** — size over lifetime.
  - **`NiParticleMeshModifier`** — mesh particles.
  - **`NiParticleRotation`** — rotation over lifetime.

The conversion library (`NiOldParticleConversion`) maps these to modern
`NiPSys*` modifiers at load time. **For a BC reimplementation, this is
the actual surface to implement**, not the modern `NiPSys*` zoo.

Architectural shape: a single controller walks a linked list of
modifiers each frame, applying each in order. Emitters add particles;
modifiers update them; the particle-set node renders them. Far simpler
than the modular emitter-pipeline of the modern system.

[inferred from source]

---

## 17. The audio system is decoupled from the scene graph

Important framing: `NiAudioSystem` / `NiAudioSource` / `NiAudioListener`
are **not NIF block types** — they don't appear in NIF files. They're
runtime APIs the application uses directly. The only NIF-level audio
hook is text keys (`NiTextKeyExtraData`), and even those are just
strings — the app reads them and fires audio events itself.

The Miles backend (`NiMilesAudio*`) is the only stock implementation;
others would require writing an `NiAudioSystem` subclass.

**Implication:** for BC, audio integration is at the application layer.
Don't expect NIF files to contain audio data.

[documented]

---

## 18. Class registration is one macro per class

The RTTI + streaming registration uses three macros that need to fire
in concert:

- In the header: `NiDeclareRTTI` + `NiDeclareStream`
  (or `NiDeclareAbstractStream` for abstract bases).
- In the source: `NiImplementRTTI(ThisClass, BaseClass)` plus
  implementations of `RegisterStreamables`, `SaveBinary`,
  `LoadBinary`, `LinkObject`, `IsEqual`, `CreateObject`.
- At application init: `NiRegisterStream(ThisClass)` to insert the
  creation function into the global loader map.

**For a clean-room reimpl:** you don't need to mirror this pattern.
You need an equivalent registry mapping class name → factory function,
and that's it. The five-virtual-function streaming protocol is a useful
guide for the responsibilities of each class but not a constraint on
your implementation.

The streaming protocol's five functions in particular:
1. **`RegisterStreamables(stream)`** — called save-side, recursively
   registers this object and everything it references with the stream.
2. **`SaveBinary(stream)`** — writes this object's body.
3. **`CreateObject()`** (static) — factory, used at load.
4. **`LoadBinary(stream)`** — reads this object's body (with link IDs
   for references; doesn't dereference them yet).
5. **`LinkObject(stream)`** — second pass: resolve link IDs to
   pointers.

The split between `LoadBinary` and `LinkObject` is what makes the
breadth-first link-ID streaming model work.

[documented]

---

## 19. Diagnostic affordances you can build out of the box

Worth knowing about for debugging your reimpl against the SDK:

- **`SceneViewer`** — a Win32 GUI that opens NIFs and shows the scene
  graph, properties, controllers, bounds. Use it as a reference for
  "what should I see in this file."
- **`AnimationTool`** — KF/KFM editor, with a state-machine view of
  actor sequences.
- **`NiProfile`** — instrumented profile builds with per-object timing
  (update-down time, update-up time, render time, frames culled).
  Columns documented in the NiProfile reference.
- **Per-`NiAVObject` profiling counters** are read-accessible in Profile
  builds (`GetUpdateDownTime`, `GetFramesRendered`, etc.) — these
  feed `NiProfile` but can be queried directly.
- **`NiOutputDebugString`** — platform-abstracted debug print used
  everywhere in the engine for error paths.

[documented]

---

## 20. NIF version history (for understanding BC content vs newer)

The version field encodes major releases. Relevant historical points:

- **3.0 / 3.1** — NetImmerse 3.x era (~2001-2002). **BC ships here.**
  Single-controller animation (`NiKeyframeController`), old particle
  system, no skin partitions yet.
- **3.3.0.11** — the **minimum version this SDK's loader accepts**. So
  the Gamebryo 1.2.2 loader still understands 3.3.0.11 content. If
  BC's content is older than that, this loader cannot read it directly,
  but the format details are very close.
- **4.0** — NetImmerse 4 (~2002-2003). Last NetImmerse-branded release.
- **10.x** — Gamebryo 1.x (the rename). Skin partitions, `NiPSys*`
  particles, `NiInterpolator` split.
- **10.0.1.8+** — Adds the second "user-defined version" word in the
  header.
- **1.2.0.0** (this SDK) — Note the version reset: Gamebryo started
  using its own version numbering distinct from the NIF version macro.

**Practical advice:** assume BC content is at NIF version 4.0.0.2 or
similar; lots of field-presence is gated by `version >= X`. A robust
clean-room loader has to encode those gates. The reverse-engineered
NifSkope tables you already use are authoritative on those gates;
this SDK won't help directly with anything older than 3.3.0.11.

[inferred from source]

---

## 21. Things to look at next if you go deeper

Files in this repo that I sampled but didn't fully analyze, and that
would reward more attention:

- **`Samples/Games/MadLab/`** and **`Samples/Games/Eturnum/`** — Full
  game-tier sample applications. Eturnum includes a perspective
  mirror, sound manager, camera manager. These are Rosetta-stone
  references for "how a real game integrates this engine." For BC
  patterns specifically, look at any custom controller / property
  patterns these use.
- **`CoreLibs/NiAnimation/NiOldAnimationConverter.h/.cpp`** — The
  one-place spec of how `NiKeyframeController` + `NiSequence` map
  to modern `NiTransformController` + `NiControllerSequence`. This
  is the **single most useful file in this SDK for understanding
  BC-era animation**, because it has to know every detail of the
  old data to convert it.
- **`CoreLibs/NiOldParticle/`** entire directory — same logic for
  particles. The conversion library `NiOldParticleConversion` does
  the same map for the particle system.
- **`ToolLibs/NiStripify/`** — the stripification algorithm used at
  export. Useful if you need to re-stripify content.
- **`ToolLibs/NiAnimationCompression/`** — B-spline fitting, key
  reduction. Mostly post-BC but informative.
- **`Samples/Tutorials/06 - Time Controllers/`** — the canonical
  programmatic-animation example. Shows in code form what an
  animation NIF reduces to at runtime.
- **`SDK/Win32/Include/`** and **`SDK/PS2/Include/`** — the
  "installed SDK" headers (vs the development tree). Slightly cleaner
  view of the public API surface.

---

## 22. The headline take for a modern reimpl

If I were rebuilding the BC NIF path from scratch with this SDK in
front of me, here's what I would actually use it for:

1. **`NiOldAnimationConverter.cpp` is your animation spec.** It reads
   BC-era animation data and writes modern data; in doing so it
   touches every field. It's the single most informative file for
   BC-era NIF animation. (Without crossing the clean-room boundary
   you can't paste from it, but you can describe it in prose, which
   is enough to write your own.)
2. **`NiOldParticle/*` is your particle spec** in the same way.
3. **`Samples/Tutorials/03 - NIF Files/`** is the canonical loop —
   30 lines of mainline + a recursive `FindCamera` helper. Match
   its shape and you'll match the engine's lifecycle.
4. **`NiStream.cpp` is the loader skeleton.** The byte layout above
   came from reading it; reading it once is enough to build a
   modern loader.
5. **`NiAVObject.cpp` (in particular its `Update` / `UpdateSelected`
   structure) is the per-frame scene-graph spec.** Worth reading
   for the documented two-pass (downward transforms + upward bounds)
   pattern that every NIF renderer needs.
6. **The DX8 renderer's "Features and Limitations" docs** define
   the content envelope BC's artists worked inside: 8 lights, 8 UV
   sets, 4 bones/partition fixed-function, env-map-as-2-stages.
   Anything beyond that envelope is BC application-level, not stock
   engine.

Everything else is either covered in the answer doc, or is a later
Gamebryo addition that BC doesn't use.
