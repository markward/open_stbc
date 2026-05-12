# BC NIF Conventions — Cheat Sheet

One-page lookup for the math, format, and runtime conventions BC NIFs use.
Derived from clean-room NetImmerse/Gamebryo SDK reading
([answers](cleanroom_netimmerse_answers.md),
[supplementary](cleanroom_netimmerse_supplementary.md)), cross-checked
against our own reverse-engineering of BC v3.1 assets.

> **Use this when** you're touching the NIF parser, renderer math,
> skinning, lighting, or animation evaluation. For the full reasoning
> read the cleanroom docs; this page is the lookup.

---

## Version

| Fact | Value |
|---|---|
| BC's primary NIF version | **3.1** (`0x03010000`) |
| BC's legacy NIF version (planets, viewscreens, Kessok head) | **3.0** (`0x03000000`) |
| Gamebryo 1.2.2 SDK loader minimum | **3.3.0.11** |
| Our SDK reference for v3.1 schema | niflib `nif.xml` + NifSkope tables; **not** the Gamebryo SDK loader |

The Gamebryo SDK source describes 3.3+ behavior and cannot load BC NIFs
directly. When SDK docs and BC reality conflict, BC wins.

---

## Math conventions

| Convention | Value |
|---|---|
| Handedness | **Right-handed** |
| Up axis at engine level | Not fixed; content-pipeline decides (BC content typically Y-up) |
| Matrix storage | **Row-major** flat array (`m[0..8]`, row-major) |
| Matrix math | **Column-vector** (`v' = M * v`); parent-to-world is left-multiplied |
| Rotation matrix | Orthonormal 3×3 |
| Quaternion struct order | `{x, y, z, w}` (named fields) |
| Quaternion **on-disk** order | **WXYZ** (W first) — `Reader::read_quat` swaps to struct order |
| Euler order (`NiEulerRotKey`) | XYZ, **radians** |
| `NiAVObject` transform composition | `parent_world * (T * R * S)` |
| Scale | **Uniform scalar only** — non-uniform must be baked into vertices |
| Light forward axis | Model-space **+X** (rotate the node to aim) |
| Camera forward axis | Local **−Z**; up = +Y, right = +X |

---

## Animation key conventions

| Key family | Interpolation | Notes |
|---|---|---|
| `LIN` | Linear (slerp for quaternions, shortest-arc) | |
| `BEZ` | **Hermite spline** (despite "Bez" name); stores in/out tangents | |
| `TCB` | Kochanek-Bartels (tension/continuity/bias) | Adds 3 floats per key |
| `STEP` | Hold previous value | |
| `EULER` (rotation only) | Three independent float tracks composed XYZ | Each track may use its own family |

Cycle types: `LOOP` (wrap), `REVERSE` (ping-pong), `CLAMP` (hold endpoints).
Animation time = `((appTime - startMoment) * frequency + phase)` mapped into
`[start, stop]`.

Text-key tag strings (`NiTextKeyExtraData`) are **application-defined** —
the SDK reserves no vocabulary. `"start"` and `"end"` appear as community
convention. BC may have its own (e.g., `"sound:..."`); round-2 cleanroom
question targets this.

---

## File format conventions

- Detect file family by the **`"File Format"`** substring in the first
  text line — covers NIF, KF, KFM, and BC custom extensions all routed
  through the same stream loader. (We currently anchor on `"Version "`;
  generalize when KF/KFM ingestion lands.)
- **Two-pass load**: each block writes scalar fields + integer link IDs
  in pass 1 (`LoadBinary`); pointers resolve in pass 2 (`LinkObject`).
  This is what allows cycles and arbitrary block ordering.
- Block-type references are **32-bit integer link IDs** into the file's
  flat block array. `NULL_LINKID` represents null.
- **RTTI table at file head** is the schema directory — every distinct
  class name appears once, each block body carries a `u16` index into
  it. Pre-scan to detect unsupported classes.
- Unknown block types are **fatal** in the stock loader. Our loader
  can be more lenient.
- Triangle indices are 16-bit unsigned. ≥ 65535-vertex geometry must be
  split.

---

## Renderer property conventions

- **Property stack: closer wins.** Only one property of any given type
  is active per subtree. Properties do **not** combine.
- Alpha sort: back-to-front by **bounding-sphere center depth** via
  `NiAlphaAccumulator`. `NiAlphaProperty` `NoSort` flag opts out.
- Texturing stage slots: `Base`, `Dark`, `Detail`, `Gloss`, `Glow`, `Bump`,
  `Decal[0..N]`. Glow is **additive emissive** independent of light
  direction and independent of `NiMaterialProperty::emissive`.
- Environment maps attach via `NiTextureEffect` (a `NiDynamicEffect`,
  alongside lights), **not** via the property stack. Modes:
  `WORLD_PARALLEL`, `WORLD_PERSPECTIVE`, `SPHERE_MAP`, `SPECULAR_CUBE`,
  `DIFFUSE_CUBE`.

---

## Skinning conventions

- Linear-blend skinning.
- Per-bone **skin-to-bone** transform (inverse-bind) stored in
  `NiSkinData::BoneData`.
- Per-vertex weights stored **per-bone** as `(vertex_index, weight)` pairs
  with explicit count. Vertex can have arbitrarily many influences at
  the format level.
- **No runtime renormalization** — exporter does it; weights must sum to
  1 in the data.
- Math: `v_world = Σᵢ wᵢ * (Bᵢ_world * Sᵢ * v_skin)` where `Sᵢ` is the
  inverse-bind for bone i.
- `NiSkinPartition` partitions for hardware skinning, default 4 bones per
  partition (DX8 era; we are free to exceed).

---

## Content-envelope limits (DX8-era; not architectural)

BC's content was authored inside these caps. Our renderer should load
content that respects them but **must not bake them in as hard limits** —
the point of rebuilding on modern GPUs is partly to exceed them.

| Limit | Value | Origin |
|---|---|---|
| Simultaneous lights per object | 8 | DX8 fixed-function T&L |
| UV sets per vertex | 8 | DX8 |
| Bones per skin partition | 4 (default) | DX8 matrix palette |
| Multitexture stages per pass | hardware-dependent | DX8 era |
| Triangle indices | 16-bit unsigned | **Format-structural** (must respect) |

See [feedback_dx8_envelope_not_ceiling.md](../../.claude/projects/-Users-mward-Documents-Projects-open-stbc/memory/feedback_dx8_envelope_not_ceiling.md) — the discrimination
between structural / runtime-architectural / hardware-era limits drives
how we model each.

---

## BC engine extensions (NOT in stock SDK)

These behaviors are BC-specific Python/C++ layered on top of NIF, not
features of the underlying engine:

- **Glow attach by filename substring** (`AddLOD("..._glow", ...)`) — no
  stock SDK equivalent.
- **Sun corona / lens flare** — no `NiCorona` / `NiLensFlare` block class.
  BC builds these from `NiBillboardNode` + additive geometry +
  `App.LensFlare`.
- **Center-of-geometry / pivot offset** — no field on `NiAVObject`. NIF
  origin is the only documented anchor; centroid offsets live in custom
  extra data or are baked at export.
- **Stretched/speed-elongated billboard particles** — not stock.
- **Distance-attenuated emissive** — not in any property.
- **Decal projection at runtime** — `Decal` texture slot is UV-driven, not
  screen/world projected.

When BC behavior doesn't map cleanly to a stock SDK feature, suspect BC
extensions before suspecting an obscure engine knob.
