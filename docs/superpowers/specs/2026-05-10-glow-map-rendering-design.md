# Emissive/Glow-Map Rendering — Design Spec

Date: 2026-05-10

## Problem

BC ship scripts call `pLODModel.AddLOD(nif, ..., "_glow", ...)`. The NIF loader
already places the resulting texture into `NiTexturingProperty.glow`, and
`material_build.cc` already populates `Material::stages[StageSlot::Glow]` and
`Material::emissive` from `NiMaterialProperty`. The renderer ignores both.
Ship windows, engine lights, and other self-illuminated surfaces appear unlit.

## Goal

Extend the opaque pass to add the emissive/glow contribution in the same draw
call. No new render pass. No bloom post-process.

## Final color formula

```
lit  = (ambient + Σ dir_lights) × diffuse_color × base_tex.rgb
glow = glow_tex.rgb × glow_tex.a          (α = 1.0 for RGB-only textures)
out  = lit + emissive_color + glow
```

`emissive_color` and `glow` are additive over `lit`; they are NOT modulated by
lighting. `NiMaterialProperty.emissive` is often `(0,0,0)` on ships; the glow
map is the meaningful contributor.

## Files changed

### `native/src/renderer/shaders/opaque.frag`

Add two uniforms:

```glsl
uniform sampler2D u_glow_map;    // tex unit 1
uniform vec3 u_emissive_color;
```

Sample the glow map and add both emissive terms to the output:

```glsl
vec4 glow = texture(u_glow_map, v_uv);
frag_color = vec4(lit + u_emissive_color + glow.rgb * glow.a, 1.0);
```

### `native/src/renderer/include/renderer/frame.h`

Add a black 1×1 fallback texture symmetric with the existing white one:

```cpp
std::uint32_t black_texture_ = 0;
std::uint32_t ensure_black_texture();
```

Destructor releases both.

### `native/src/renderer/frame.cc`

`ensure_black_texture()`: same pattern as `ensure_white_texture()` but uploads
`{0, 0, 0, 255}`.

`draw_model()` gains a `black_fallback` parameter. Per mesh:
- `shader.set_vec3("u_emissive_color", mat.emissive)`
- Look up `StageSlot::Glow` texture index; bind to `GL_TEXTURE1`
  (or `black_fallback` if index < 0)
- `shader.set_int("u_glow_map", 1)`

`submit_opaque()` calls `ensure_black_texture()` and passes it to
`draw_model()`.

## Tests

### Python — `tests/host/test_glow_pass.py`

Pattern: `OPEN_STBC_HOST_HEADLESS=1` + `_open_stbc_host`, matching
`test_host_loop_lighting.py`.

- Skip when Galaxy NIF / texture dir absent (missing prerequisite, not platform).
- Set `lighting = (0.0, 0.0, 0.0), []` — zero ambient, no directionals.
  With this lighting, the only illumination is from the glow map.
- Scan a 7×7 grid (±60 px horizontal, ±40 px vertical from viewport centre)
  to avoid false failures from non-glowing hull geometry at the exact centre.
- Assert `max(r+g+b across sampled pixels) > 57` — above the clear-color
  background level `(0.05, 0.07, 0.10) × 255 ≈ 57 total`, proving glow
  contributed to at least one mesh pixel.

### C++ — `native/tests/renderer/frame_test.cc`

New `TEST_F(FrameTest, GlowContributesWithZeroAmbient)`.
- Zero-out `Lighting` (ambient = 0, directional_count = 0).
- Call `submit_opaque`, then `glReadPixels` from `GL_BACK` (before swap).
- Assert center-pixel total `> 0`.

The C++ test reads `GL_BACK` pre-swap, which is reliable on macOS headless.
The Python test reads `GL_FRONT` post-swap, which inherits the known macOS
headless limitation shared by the rest of `tests/host/`; no platform skip is
added.

## What is NOT done

- `AddLOD` search-string texture discovery — `material_build.cc` already handles it.
- Specular (`_specular`, args 9–10).
- Post-process bloom.
