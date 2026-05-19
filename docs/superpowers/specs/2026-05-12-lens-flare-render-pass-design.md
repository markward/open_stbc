# Lens-flare render pass — design

**Date:** 2026-05-12
**Status:** Design approved; implementation pending
**Related work:** Sun corona pass ([`native/src/renderer/sun_pass.cc`](../../../../native/src/renderer/sun_pass.cc)), space-dust pass ([`native/src/renderer/dust_pass.cc`](../../../../native/src/renderer/dust_pass.cc)).

## Goal

Render BC's sun lens-flare overlay: a chain of textured polygonal disks strung along the screen-space line from a light source (the system sun) through screen center to the opposite side. The flare disappears entirely when the source is occluded by geometry or off-screen.

## Background

`App.LensFlare_Create(pSet).AddFlare(...)` is the hottest stub in the gameloop-harness profile: **873 calls across 30 missions** (rank 1), driven by 86 system scripts in [`sdk/Build/scripts/Systems/`](../../../../sdk/Build/scripts/Systems/) that call `Tactical.LensFlares.{Red,Yellow,Blue,}LensFlare(pSet, pSun)` once per scene. Each call expands via `MakeLensFlare` at [`sdk/Build/scripts/Tactical/LensFlares.py:106-124`](../../../../sdk/Build/scripts/Tactical/LensFlares.py#L106-L124) into 1 `LensFlare_Create` + 1 `SetSource` + 9 `AddFlare` + 1 `Build` calls. All output is currently swallowed by `_NamedStub` and nothing renders. This spec implements the consumer.

## Architecture

Three layers, each in its own file, following the same pattern as the existing sun pass:

```
SDK script    ─▶  App.LensFlare_Create(pSet)
                       │
                       ▼
Python class  ─▶  engine.appc.lens_flare.LensFlare   (stores elements list)
                       │
                       ▼   (per frame, in engine.host_loop)
aggregator    ─▶  aggregate_lens_flares_for_renderer()
                       │  list[dict]
                       ▼
host binding  ─▶  set_lens_flares(...)
                       │
                       ▼
C++ pass      ─▶  renderer::LensFlarePass::render()
```

The pass runs **after the dust pass** in `frame()`, so flares draw on top of dust specks. No runtime toggle key (per design choice).

## Python side

### `LensFlare` class

New file `engine/appc/lens_flare.py`:

```python
class LensFlare:
    def __init__(self, pSet):
        self._set = pSet
        self._source = None
        self._direction_mode = 1   # SDK: 1=backdrop, 6=object
        self._elements: list[dict] = []
        self._built = False

    def SetSource(self, obj, direction_mode):
        self._source = obj
        self._direction_mode = int(direction_mode)

    def AddFlare(self, wedges, texture, position, size, freq=0.0, amp=0.0):
        self._elements.append({
            "wedges":   int(wedges),
            "texture":  str(texture),
            "position": float(position),
            "size":     float(size),
            "freq":     float(freq),
            "amp":      float(amp),
        })

    def Build(self):
        self._built = True


def LensFlare_Create(pSet) -> LensFlare:
    """SDK signature: ``LensFlare_Create(pSet) -> LensFlare``."""
    flare = LensFlare(pSet)
    if pSet is not None and hasattr(pSet, "_lens_flares"):
        pSet._lens_flares.append(flare)
    return flare
```

### SetClass attribute

`engine/appc/sets.py` `SetClass.__init__` gains `self._lens_flares: list = []` (alongside the existing `_lights` and `_backdrops`). No method needed — `LensFlare_Create` mutates the list directly.

### Aggregator

```python
def aggregate_lens_flares_for_renderer(project_root, pSets) -> list:
    """Return list[dict] for all built LensFlares across pSets, resolving
    texture paths against project_root / "game". Drops flares whose
    source object has no world location, whose Build() was never called,
    whose textures don't resolve, or which have no elements."""
```

Each output entry:
```python
{
    "source_world_pos": (x, y, z),
    "source_radius":    float,     # used as a depth-test epsilon
    "elements": [
        {
            "wedges":       int,    # clamped to [3, 64]
            "texture_path": str,    # absolute
            "position":     float,
            "size":         float,
            "freq":         float,
            "amp":          float,
        }, ...
    ],
}
```

### App.py wiring

`App.py` replaces the `_NamedStub` fall-through for `LensFlare_Create` with:

```python
from engine.appc.lens_flare import LensFlare_Create  # real factory
```

This pattern matches `Sun_Create`, `Planet_Create`, etc. — the stub tracker only catches calls that go through `_NamedStub`, so once `LensFlare_Create` is a real function, the row drops out of the profile.

### host_loop integration

`engine/host_loop.py` gains `_aggregate_lens_flares()` mirroring `_aggregate_suns`, and the per-frame block adds:

```python
flares = _aggregate_lens_flares()
r.set_lens_flares(flares)
```

`engine/renderer.py` adds a typed `set_lens_flares(flares: list)` wrapper.

## C++ side

### New pass — `LensFlarePass`

New files `native/src/renderer/lens_flare_pass.{cc,h}`. State:

```cpp
class LensFlarePass {
public:
    void render(const std::vector<LensFlareDescriptor>& flares,
                const scenegraph::Camera& camera,
                Pipeline& pipeline,
                int viewport_w, int viewport_h,
                double now_seconds);
private:
    struct WedgeMesh { GLuint vao, vbo, ebo; int index_count; };
    std::unordered_map<int, WedgeMesh> wedge_meshes_;
    std::unordered_map<std::string, std::unique_ptr<assets::Texture>> texture_cache_;

    WedgeMesh& ensure_wedge_mesh(int n);
    assets::Texture* ensure_texture(const std::string& path);
};

struct LensFlareDescriptor {
    glm::vec3 source_world_pos;
    float     source_radius;
    std::vector<LensFlareElement> elements;
};

struct LensFlareElement {
    int         wedges;
    std::string texture_path;
    float       position;
    float       size;
    float       freq;
    float       amp;
};
```

### Wedge mesh (N-gon disk with per-wedge UV tiling)

For each unique wedge count `N`, cache a mesh built once:

- **Vertices**: 1 center + N outer = N+1 total. Center at (0, 0) in local "disk space"; outer k at `(cos(2πk/N), sin(2πk/N))` for `k ∈ [0, N)`.
- **UVs**: per-wedge, not shared across wedges. Each wedge k draws as one triangle with three distinct vertex indices:
  - center vertex of wedge k:    `uv = (0.5, 1.0)`
  - outer vertex k (left edge):  `uv = (0.0, 0.0)`
  - outer vertex k+1 (right):    `uv = (1.0, 0.0)`
- **Element buffer**: N triangles, 3N indices.

This tiling makes the texture's vertical axis run center→edge of the disk, and the horizontal axis sweep one side of a wedge to the other. With `rays.tga` (a vertical column of bright spikes) × 8 wedges, the result is the classic 8-spike sun-star.

Storage: `vec4 position_xy_uv = (x, y, u, v)` per vertex; one VAO/VBO/EBO triple per `N`. Because the UVs differ per wedge, vertices cannot be reused across wedges; final vertex count is `3N`, index count `3N`.

### Shader pair

`native/src/renderer/shaders/lens_flare.vert`:

```glsl
#version 330 core
layout(location = 0) in vec2 a_corner;   // unit-disk-local position
layout(location = 1) in vec2 a_uv;

uniform vec2  u_screen_center;            // NDC
uniform float u_scale;                    // size in NDC-Y units
uniform float u_aspect;                   // viewport_w / viewport_h

out vec2 v_uv;

void main() {
    vec2 ndc = u_screen_center
             + vec2(a_corner.x / u_aspect, a_corner.y) * u_scale;
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_uv = a_uv;
}
```

`native/src/renderer/shaders/lens_flare.frag`:

```glsl
#version 330 core
in  vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform float     u_brightness;   // global fade

void main() {
    vec4 t = texture(u_texture, v_uv);
    frag_color = vec4(t.rgb, t.a) * u_brightness;
}
```

Additive blend; no depth test; no depth write. Aspect-correcting on X keeps the disk circular regardless of window aspect.

### Per-frame render

For each flare descriptor:

1. **Project source to NDC**:
   ```cpp
   vec4 clip = camera.proj_matrix() * camera.view_matrix()
             * vec4(source_world_pos, 1.0);
   if (clip.w <= 0) continue;                       // behind camera
   vec3 ndc = clip.xyz / clip.w;
   if (abs(ndc.x) > 1.2 || abs(ndc.y) > 1.2) continue; // off-screen (with margin)
   if (ndc.z < -1.0 || ndc.z > 1.0) continue;          // outside near/far
   ```

2. **Depth-buffer occlusion test**:
   ```cpp
   int px = int((ndc.x * 0.5 + 0.5) * viewport_w);
   int py = int((ndc.y * 0.5 + 0.5) * viewport_h);
   float depth = 0.0;
   glReadPixels(px, py, 1, 1, GL_DEPTH_COMPONENT, GL_FLOAT, &depth);
   float source_depth_01 = ndc.z * 0.5 + 0.5;
   const float eps = 1e-4;
   if (depth + eps < source_depth_01) continue;     // occluded
   ```
   One synchronous readback per visible flare per frame; with 1–3 suns/scene the stall is microseconds.

3. **Set GL state once** (shared across all elements of all flares):
   ```cpp
   glDisable(GL_DEPTH_TEST);
   glDepthMask(GL_FALSE);
   glEnable(GL_BLEND);
   glBlendFunc(GL_SRC_ALPHA, GL_ONE);   // additive
   ```

4. **For each element**:
   - Resolve screen center: `center = mix(ndc.xy, vec2(0,0), element.position)`.
   - Compute time-wobbled scale: `scale = element.size * (1 + element.amp * sin(2π * element.freq * now_seconds))`.
   - Bind the wedge mesh for `element.wedges` (build on demand if missing).
   - Bind the texture (load on demand if missing; skip element if load fails).
   - Set uniforms; draw `3 * element.wedges` indices.

5. **Restore GL state**:
   ```cpp
   glDisable(GL_BLEND);
   glDepthMask(GL_TRUE);
   glEnable(GL_DEPTH_TEST);
   ```

### Pipeline + bindings

- `native/src/renderer/pipeline.{cc,h}`: load lens-flare shader; expose `lens_flare_shader()` accessor.
- `native/src/host/host_bindings.cc`: new `g_lens_flare_pass` and `g_lens_flares` globals; `set_lens_flares(...)` binding parses dict list → `LensFlareDescriptor` vector; `frame()` calls `g_lens_flare_pass->render(...)` after `g_dust_pass->render(...)` and before bridge.
- `native/src/renderer/CMakeLists.txt`: add `lens_flare_pass.cc`.

## Testing

| Test | Location | What it verifies |
|---|---|---|
| `test_lens_flare_class` | `tests/unit/test_lens_flare.py` | `LensFlare_Create` registers on the set; `AddFlare` accumulates elements; `Build()` marks built |
| `test_aggregate_lens_flares` | `tests/unit/test_lens_flare.py` | Aggregator returns descriptors with absolute texture paths; skips unbuilt flares, flares with no source, flares whose textures don't resolve |
| `test_lens_flare_stub_regression` | `tests/unit/test_lens_flare_stub_regression.py` | Run `gameloop_harness(profile=True)`; assert no row starting with `LensFlare_Create` in `_stub_tracker.report()` |
| `test_wedge_mesh_build` | `native/tests/test_lens_flare_pass.cc` (GoogleTest) | For N ∈ {3, 6, 8, 30}: vertex count = 3N, index count = 3N; outer-edge UVs are `(0,0)` and `(1,0)`; center UVs are `(0.5, 1.0)` |
| Visual smoke | manual | `./build/dauntless`, fly Tau Ceti (E1M1) and Cebalrai (red-orange sun); confirm flares appear, disappear when sun is behind ship/planet, animate (amp=0.1 freq=0.5 wobble on rays element) |

## Risks and notes

- **`glReadPixels` stall**: one synchronous read per flare per frame. Acceptable for ≤5 flares; if scenes ever push higher (modded systems), upgrade to asynchronous `glBeginQuery(GL_SAMPLES_PASSED, ...)` occlusion queries.
- **First-frame load hitch**: textures and wedge meshes are lazy-cached on first use. Across all stock systems that's ≤17 textures + 3 mesh builds, all sub-millisecond. No precaching needed.
- **Sun's own sphere occlusion**: the depth-test `eps = 1e-4` prevents the sun sphere from occluding its own flare. Verify in visual smoke.
- **Texture sharing with future passes**: the per-pass `texture_cache_` may end up redundant if other passes (planet, ship) share these TGAs. Not worth solving now — promote to an asset cache later if it matters.
- **Out-of-frustum source with on-screen flare elements**: if the sun is just off-screen, late elements (position ≈ 2) are still visible on the opposite side. The current off-screen cull uses a 1.2 margin so flares fade as the sun moves out; if that looks abrupt in practice, switch to a smooth fade based on `max(abs(ndc.x), abs(ndc.y))`.

## Out of scope

- Custom lens flares on non-sun light sources (weapon flashes, explosions). The SDK supports it via `App.LensFlare_Create(pSet).SetSource(obj, 6)`; the API surface above handles it, but no current stock script does this, so it's untested in V1.
- Per-pixel "smooth fade" as the sun approaches occlusion edge. V1 is binary visible/hidden.
- Adaptive LOD (lower wedge count when small on screen). All wedge counts honor the SDK request as-is.
