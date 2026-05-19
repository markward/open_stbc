# Space Dust Particles — Design

**Status:** Draft, pre-implementation.
**Sub-project:** Renderer atmosphere/motion-cue effects — adds a dust
particle pass to the renderer host so the player can sense ship motion
through otherwise empty space.

## Why this scope

The original Star Trek: Bridge Commander rendered small white particles
("space dust") around the camera. When the ship was stationary they
were tiny dots; when it moved they smeared into short streaks oriented
along the camera's velocity. The effect gave the player a continuous
parallax-driven sense of motion in otherwise featureless space.

The original engine exposes the effect only as a global on/off toggle:

- `App.SpaceCamera_SetSpaceDustInGame(bool)` /
  `App.SpaceCamera_IsSpaceDustEnabledInGame()`
- `SpaceCamera.SetSpaceDustForCamera(bool)` /
  `SpaceCamera.IsSpaceDustEnabled()`

No Python script in the SDK calls these; density, volume sizing, smear
length, fade, and recycling all live inside `Appc.dll`. The shipped
texture `data/Textures/spacedust.tga` (16×16 RGBA, soft radial dot) is
the only asset. `starstreak.tga` is reserved for the warp-travel
system and is **not** used by this pass.

This sub-project adds the equivalent effect to the new C++ renderer
host, going by feel since the original tuning constants are not
recoverable from Python.

## Goals

1. Render ~2,000 dust particles in a bounded volume around the camera,
   visible as 1–2 px white dots when stationary.
2. Smear particles along the camera's negative velocity vector when the
   camera is moving, producing short streaks proportional to speed.
3. Recycle particles as the camera moves so density stays roughly
   constant in the visible volume.
4. Integrate as a new `DustPass` alongside `BackdropPass` / `SunPass`,
   mirroring those passes' shape (header, impl, two shaders, owned by
   host bindings).
5. Provide a runtime on/off toggle (debug key `F7`) and a stub for
   future per-system density modulation.

## Non-goals (Phase 1)

- Per-system dynamic density (proximity to planets, nebulae, dust
  clouds) — deferred.
- Color tinting per environment — deferred.
- High-speed/warp-transit dust behaviour — deferred to Phase 2.
- Replacing the original engine's `SpaceCamera_SetSpaceDustInGame`
  surface wholesale; for Phase 1 the toggle is a host-side debug key,
  not a Python-driven engine call. A Python hook is listed as deferred
  work below.

## Architecture

A new render pass mirroring `BackdropPass`.

**New files:**

- `native/src/renderer/include/renderer/dust_pass.h`
- `native/src/renderer/dust_pass.cc`
- `native/src/renderer/shaders/dust.vert`
- `native/src/renderer/shaders/dust.frag`

**Modified files:**

- `native/src/renderer/pipeline.cc` — add `dust_shader_` member,
  loaded the same way as `backdrop_shader_`.
- `native/src/renderer/frame.cc` — call `DustPass::render()` after
  backdrop and opaque scene, before sun corona and UI.
- `native/src/host/host_bindings.cc` — own a `DustPass` unique_ptr;
  expose `dust_set_enabled(bool)` and `dust_set_density(int)` to
  Python.
- `engine/host_loop.py` — bind `F7` to toggle the dust pass.
- `native/src/renderer/CMakeLists.txt` — add new sources and shader
  embed targets.

**Pass placement in `frame.cc`:**

```
clear → backdrop → opaque scene → DUST → sun corona → UI
```

Dust is depth-tested against the scene depth buffer so ships and
planets occlude particles behind them, but does not write depth so it
neither self-occludes nor breaks later passes.

## Particle model

Particles are world-space points stored in a fixed-size GPU buffer,
generated once at construction and never rewritten during normal play.
"Recycling" happens entirely in the vertex shader via toroidal
wrapping around the camera.

### Storage

- **Particle count:** 4096 seeded; ~2150 visible after the fragment
  shader's sphere clip. Sparse by design.
- **Volume radius:** `R = 40.0` BC units around the camera. Particles
  outside this radius are discarded by the fragment shader.
- **Per-instance data:** `vec4(x, y, z, jitter)`.
  - `x, y, z` are world coordinates at init (uniformly distributed in
    the **cube** `[-R, R]^3`, deterministically seeded). Cube — not
    sphere — because the vertex shader's toroidal wrap operates on
    each axis independently in a 2R cube; seeding in a sphere
    produces visible density variations as the camera moves more than
    a fraction of `R`. The fragment shader's `length(local) > R →
    discard` keeps the visible region spherical.
  - `jitter` is a single `float ∈ [0, 1)` seeded at init. The vertex
    shader derives brightness and size from it:
    ```
    brightness = mix(kBrightnessMin, kBrightnessMax, jitter);
    size       = mix(kSizeMin,       kSizeMax,       fract(jitter * 7.0));
    ```
    A single jitter value drives both — cheap, deterministic, and
    decorrelates the two via the multiplier.

### Recycling math

Each frame the host passes the current camera world position as a
uniform `vec3 u_camera_pos`. The vertex shader computes a per-particle
local offset:

```
local = particle_pos - u_camera_pos
local = mod(local + R, 2.0 * R) - R    // wrap each axis into [-R, R]
world_pos = u_camera_pos + local
```

This wraps particles inside a cube of side `2R`. The cube's corners
that fall outside the inscribed sphere are culled by `length(local) > R
→ discard` in the fragment shader. No CPU bookkeeping, no per-frame
buffer updates.

A soft alpha fade near the sphere boundary prevents recycling pops:

```
alpha_fade = 1.0 - smoothstep(R * 0.85, R, length(local))
```

## Smear

### Camera velocity sourcing

`DustPass` holds a `glm::vec3 prev_eye_` member, updated each frame
after rendering. Velocity is `(camera.eye - prev_eye_) / dt`, where
`dt` is the frame delta time (already plumbed through to existing
passes).

Two guards on first/abnormal frames:

- First frame after construction: velocity = 0 (no streaks).
- If `dt > 0.1 s`: velocity = 0 (pause/hitch suppression).

### Smear uniform

The shader receives `vec3 u_smear = -camera_velocity * smear_seconds`,
where `smear_seconds = 1.0 / 30.0` initially. This is the world-space
streak length. A 100 BC/s ship velocity produces a ~3.3 BC streak;
perspective shortens it for distant particles automatically.

### Quad expansion in the vertex shader

Base mesh is a single quad: 4 vertices, 6 indices, static VBO. Drawn
with instanced rendering: per-instance attribute (divisor=1) is the
particle `vec4`. Per corner the shader:

1. Computes `local` via the wrapping math above.
2. Reads the billboard basis from the view matrix's right/up vectors:
   ```
   right = vec3(u_view[0][0], u_view[1][0], u_view[2][0]);
   up    = vec3(u_view[0][1], u_view[1][1], u_view[2][1]);
   ```
3. Builds the base corner offset:
   `offset = corner.x * size * right + corner.y * size * up`.
4. Stretches along smear: corners with `corner.y > 0` get
   `+0.5 * u_smear`, corners with `corner.y < 0` get
   `-0.5 * u_smear`. (The "leading" and "trailing" edges of the quad
   each get pulled half the streak length along the smear axis.)
5. Emits clip-space position:
   `gl_Position = u_proj * u_view * vec4(world_pos + offset, 1.0)`.
6. Passes `vec2 v_uv`, `float v_brightness`, `vec3 v_local` to the
   fragment shader.

## Fragment shader

```glsl
#version 330 core
in vec2 v_uv;
in float v_brightness;
in vec3 v_local;
uniform sampler2D u_dust_tex;
uniform float u_radius;
out vec4 out_color;

void main() {
    float r = length(v_local);
    if (r > u_radius) discard;
    vec4 tex = texture(u_dust_tex, v_uv);
    float fade = 1.0 - smoothstep(u_radius * 0.85, u_radius, r);
    out_color = vec4(tex.rgb * v_brightness, tex.a * fade);
}
```

## Render state

- `glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE);` — additive.
  Dust never darkens what's behind it.
- `glDepthFunc(GL_LEQUAL); glDepthMask(GL_FALSE);` — depth-tested,
  no depth writes.
- `glDisable(GL_CULL_FACE);` while drawing the dust (quads are
  billboarded so back-face direction is meaningless).
- Restore all default state on exit (matches `BackdropPass` convention).

## Texture loading

`DustPass::ensure_texture()` mirrors `BackdropPass::ensure_texture`:

- Reads `data/Textures/spacedust.tga` once on first render.
- Decodes via `assets::decode_tga`.
- Uploads via `assets::upload_image(img, generate_mipmaps=true)`.
- Caches in a `std::unique_ptr<assets::Texture>`.
- On failure logs `[dust] failed to open '...'` and the pass renders
  nothing without crashing.

## Host-side API

Exposed via `host_bindings.cc` (pybind11):

| Python call | Effect |
|---|---|
| `_open_stbc_host.dust_set_enabled(bool)` | Toggle the pass at runtime. Default `True`. |
| `_open_stbc_host.dust_set_density(int n)` | Reseed the GPU buffer with `n` particles (clamped to `[0, 50000]`). For the deferred dynamic-density work. |

A facade in `engine/renderer.py` mirrors the existing `set_camera`
style:

```python
def set_dust_enabled(enabled: bool) -> None: ...
def set_dust_density(count: int) -> None: ...
```

In [engine/host_loop.py](engine/host_loop.py), `F7` is wired to
toggle the enabled state. `F8` is taken by the RmlUi debugger; `F9`
toggles UI visibility; `F7` is the next free function key. This also
requires adding `KEY_F7 = GLFW_KEY_F7` to the `keys` submodule in
`host_bindings.cc`.

## Tunable constants

Documented in `dust_pass.h` as the dials for visual tuning:

| Constant | Initial value | Notes |
|---|---|---|
| `kParticleCount` | 2048 | Sparse baseline. |
| `kVolumeRadius` | 40.0 BC | Recycling sphere; particles outside are discarded. |
| `kSmearSeconds` | 1.0 / 30.0 | World-space streak length per (BC/s) of velocity. |
| `kSizeMin` | 0.8 BC | Per-particle quad half-extent lower bound. |
| `kSizeMax` | 1.4 BC | Upper bound. |
| `kBrightnessMin` | 0.5 | Per-particle brightness lower bound. |
| `kBrightnessMax` | 1.0 | Upper bound. |
| `kVelocityClampSeconds` | 0.1 | Max `dt` before velocity is forced to 0 (pause/hitch guard). |

## Testing

### Unit tests (no GL context required)

`native/tests/renderer/dust_pass_test.cc`:

1. **Wrapping math regression.** Re-implement the wrap formula in
   plain C++ alongside the shader copy. Verify for a set of
   `(particle_pos, camera_pos, R)` triples that the wrapped local
   stays in `[-R, R]` on each axis.
2. **Deterministic seeding.** Constructing two `DustPass` instances
   with the same seed produces byte-identical particle buffers.
3. **Density resize.** `set_density(n)` produces a buffer of exactly
   `n * sizeof(vec4)` bytes with positions inside the sphere.

If the C++ wrap formula and the GLSL wrap formula ever drift, visual
tuning will catch it before tests do — this is acceptable because the
shader source is the source of truth and the C++ copy is a regression
guard, not a duplicate implementation.

### Visual verification

No headless pixel test: on macOS, GLFW hidden windows don't reliably
present BACK→FRONT swaps and `glReadPixels` on a headless context
returns garbage. Verification is by eye in `./build/dauntless`:

- Dust visible when stationary as faint static dots.
- Dust elongates into streaks proportional to ship velocity.
- Streaks aligned with camera motion direction.
- `F7` toggles the pass cleanly with no flicker.
- No popping at the sphere boundary (alpha fade is doing its job).
- Ships and planets correctly occlude particles behind them.
- Sun corona still draws correctly (dust does not contaminate later
  passes' state).

## Deferred work

1. **Dynamic density per system.** System and mission scripts should
   be able to modulate particle count, density, and tinting based on
   context (proximity to planets, presence of nebulae, dust clouds,
   stellar environment). Implementation hook: pipe
   `App.SpaceCamera_SetSpaceDustInGame` and a new
   `App.SpaceCamera_SetSpaceDustDensity` through to the C++ pass.
2. **Color tinting.** Add a `vec3 u_tint` uniform and per-system
   tint values. Defaults to white.
3. **High-speed safety.** If camera speed exceeds a threshold (e.g.
   2R per frame), wrap math degenerates. Mitigation: skip the dust
   pass above a max speed, or scale particles to zero opacity.
   Becomes relevant once warp / sector transit is implemented.
4. **Per-system particle bias.** Distribute particles non-uniformly
   when inside a nebula or asteroid field (e.g. cluster around a
   dust-cloud centre). Out of scope for Phase 1.
5. **Persisted user preference.** Eventually the on/off toggle should
   survive process restart via the same config plumbing as other
   graphics options. Phase 1 keeps it ephemeral (default-on each
   launch).
6. **Particles deflected by ship hulls.** When Bullet physics arrives,
   promote dust particles to lightweight physics bodies (or use Bullet
   collision queries) so they bounce off ship geometry rather than
   passing through. Gives the "shoving aside" effect at close range
   without needing a separate shader-side push uniform. Deferred until
   Bullet integration lands.
