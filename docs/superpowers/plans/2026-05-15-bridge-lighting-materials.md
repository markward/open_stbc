# Bridge Lighting & Materials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the BC bridge interior render with correct base textures, baked lightmap multiply, and bridge-set ambient lighting, without regressing ship rendering.

**Architecture:** Two-pronged. (A) Fix `gather_material_inputs` to walk inherited NiNode property links so bridge shapes actually get materials, and tag materials whose Base texture is a `* lm.tga` lightmap. (B) Replace the current shared-shader bridge draw with a dedicated `BridgePass` that runs two sub-passes — a `bridge.{vert,frag}` opaque base draw, then a `lightmap.{vert,frag}` multiply-blend draw — both driven by a separate `g_bridge_lighting` aggregated from the bridge `SetClass`.

**Tech Stack:** C++20, GLSL 330 core, OpenGL 3.3 core, GoogleTest (native), pytest (Python), pybind11. Build via top-level `cmake -B build -S .`.

**Precondition (worktree):** Implementation happens on an experimental branch in a git worktree, per the spec's risk-management approach. The worktree is created by `superpowers:using-git-worktrees` before execution begins; this plan assumes the working directory is the worktree.

**Spec:** [docs/superpowers/specs/2026-05-15-bridge-lighting-materials-design.md](../specs/2026-05-15-bridge-lighting-materials-design.md)

---

## File map

**New files**
- `native/src/renderer/shaders/bridge.vert` — bridge sub-pass A vertex shader.
- `native/src/renderer/shaders/bridge.frag` — bridge sub-pass A fragment shader (base × ambient, alpha-test).
- `native/src/renderer/shaders/lightmap.vert` — bridge sub-pass B vertex shader.
- `native/src/renderer/shaders/lightmap.frag` — bridge sub-pass B fragment shader (pure texture sample).
- `native/src/renderer/include/renderer/bridge_pass.h` — `BridgePass` interface.
- `native/src/renderer/bridge_pass.cc` — `BridgePass` implementation (two sub-passes).
- `native/tests/renderer/bridge_pass_test.cc` — CPU-side partitioning test (stubbed GL).

**Modified — asset pipeline (C++)**
- `native/src/assets/include/assets/material.h` — add `bool lightmap_pass = false;`.
- `native/src/assets/src/material_build.h` — add `image_filename_for_link` accessor to `MaterialInputs`.
- `native/src/assets/src/material_build.cc` — set `lightmap_pass` via filename predicate on Base stage.
- `native/src/assets/src/model_build.cc` — build child→parent map; thread inheritance walk into `gather_material_inputs`; pass image-filename map to `MaterialInputs`.
- `native/tests/assets/cpu/material_build_test.cc` — predicate tests.
- `native/tests/assets/cpu/model_build_test.cc` — inheritance walk tests + Galaxy regression fixture.

**Modified — renderer (C++)**
- `native/src/renderer/CMakeLists.txt` — embed new shaders; add `bridge_pass.cc` to the renderer library.
- `native/src/renderer/include/renderer/pipeline.h` — add `bridge_shader()` and `lightmap_shader()` accessors.
- `native/src/renderer/pipeline.cc` — compile bridge and lightmap programs.
- `native/src/renderer/include/renderer/frame.h` — drop `submit_opaque_in_pass` declaration.
- `native/src/renderer/frame.cc` — drop `submit_opaque_in_pass` definition.
- `native/tests/renderer/CMakeLists.txt` — add `bridge_pass_test.cc`.

**Modified — host bindings (C++)**
- `native/src/host/host_bindings.cc` — add `g_bridge_lighting` global, `set_bridge_lighting` binding, `g_bridge_pass`; replace inline `submit_opaque_in_pass` with `g_bridge_pass->render(...)`.

**Modified — engine (Python)**
- `engine/appc/lights.py` — `_resolve_bridge_set`, `aggregate_bridge_for_renderer`.
- `engine/renderer.py` — `set_bridge_lighting` wrapper.
- `engine/host_loop.py` — call `aggregate_bridge_for_renderer` + `r.set_bridge_lighting` per tick.
- `tests/unit/test_appc_lights.py` — bridge-set resolution + aggregation tests.
- `tests/host/test_host_loop_lighting.py` — bridge ambient is independent of space ambient.

**Modified — investigation tooling**
- `native/tools/probe_texture_stages/probe_texture_stages.cc` — report direct vs inherited per property.

**Modified — docs**
- `native/src/host/docs/deferred_work.md` — add new entries from spec section "Deferred work".

---

## Task 1: Extend probe to show provenance + sweep ship NIFs

**Why:** Before changing inheritance semantics in `gather_material_inputs`, we need to know whether any ship NIF already relies on inherited properties. If they don't, the change is a pure addition. If some do, we need to know which ones for the regression fixture.

**Files:**
- Modify: `native/tools/probe_texture_stages/probe_texture_stages.cc`

- [ ] **Step 1: Extend probe to label each property as direct vs inherited**

Open `native/tools/probe_texture_stages/probe_texture_stages.cc`. Replace the existing `inherited_property_links` helper with one that returns each link tagged with its provenance (`direct` if from the shape itself, `inherited(<depth>)` if from an ancestor), and replace the printed-property line to include the tag. Concrete change:

```cpp
struct TaggedLink {
    std::uint32_t link;
    int depth;  // 0 = direct on shape, 1 = on parent NiNode, 2 = grandparent...
};

auto inherited_property_links_tagged =
    [&](std::size_t shape_block_index) -> std::vector<TaggedLink> {
    std::vector<TaggedLink> out;
    const auto* shape = std::get_if<nif::NiTriShape>(&f.blocks[shape_block_index]);
    if (shape) {
        for (auto l : shape->av.property_links) out.push_back({l, 0});
    }
    std::uint32_t cur_id = f.block_ids[shape_block_index];
    int depth = 1;
    while (true) {
        auto it = child_id_to_parent_index.find(cur_id);
        if (it == child_id_to_parent_index.end()) break;
        const auto* n = std::get_if<nif::NiNode>(&f.blocks[it->second]);
        if (!n) break;
        for (auto l : n->av.property_links) out.push_back({l, depth});
        cur_id = f.block_ids[it->second];
        ++depth;
    }
    return out;
};
```

And at the per-shape print site, change the local `prop_links` loop body so each matched property prints its `depth`. Replace the inner `for (std::uint32_t link : prop_links)` block with the tagged form, and append `[direct]` or `[inherited@<depth>]` to the existing classification print. Add summary counters `multi_direct`, `multi_inherited`, `single_direct`, `single_inherited` and print them in the summary block.

- [ ] **Step 2: Build the probe**

```bash
cmake -B build -S . && cmake --build build --target probe_texture_stages -j
```

Expected: build succeeds.

- [ ] **Step 3: Run on DBridge.NIF — verify provenance reporting works**

```bash
./build/native/tools/probe_texture_stages/probe_texture_stages \
  game/data/Models/Sets/DBridge/Dbridge.NIF | grep -E "(\\[direct\\]|\\[inherited)" | head -5
./build/native/tools/probe_texture_stages/probe_texture_stages \
  game/data/Models/Sets/DBridge/Dbridge.NIF | tail -20
```

Expected: every shape's property is labelled `[inherited@1]` or deeper. Summary shows `multi_inherited` = 17, `single_inherited` = 128, `multi_direct` = 0, `single_direct` = 0.

- [ ] **Step 4: Sweep ship NIFs**

```bash
for nif in game/data/Models/Ships/*/Galaxy.nif \
          game/data/Models/Ships/*/Vorcha.NIF \
          game/data/Models/Ships/*/Akira.nif \
          game/data/Models/Ships/*/Sovereign.nif; do
  if [ -f "$nif" ]; then
    echo "=== $nif ==="
    ./build/native/tools/probe_texture_stages/probe_texture_stages "$nif" | tail -8
  fi
done
```

Expected: results that show whether ship NIFs rely on inherited properties. **Record the findings** — copy the output into the task's commit message so future agents have the evidence. If any ship has non-zero `*_inherited` counters, that ship needs explicit fixture coverage in Task 3.

- [ ] **Step 5: Commit**

```bash
git add native/tools/probe_texture_stages/probe_texture_stages.cc
git commit -m "tools(probe): label texture-property provenance (direct vs inherited)

Extends probe_texture_stages so each shape's property line says whether
the property block came from the shape itself or from an ancestor NiNode,
and adds per-provenance counters to the summary.

Ship NIF sweep results (paste counts here)."
```

---

## Task 2: Galaxy regression fixture (baseline before changing inheritance)

**Why:** Pin current observable Material values for a representative ship so Task 3 cannot silently regress them. Test must pass on `main` before any inheritance-walk change.

**Files:**
- Modify: `native/tests/assets/cpu/model_build_test.cc`

- [ ] **Step 1: Find a representative ship NIF**

```bash
ls -la game/data/Models/Ships/Galaxy/Galaxy.nif \
       game/data/Models/SharedTextures/FedShips/High
```

Expected: both exist. (Frame test uses these same paths; pattern is already proven.)

- [ ] **Step 2: Add a regression fixture test**

Append this to the bottom of `native/tests/assets/cpu/model_build_test.cc`:

```cpp
#include <filesystem>
#include <assets/cache.h>

namespace {
const std::filesystem::path kProjectRoot =
    std::filesystem::path(OPEN_STBC_PROJECT_ROOT);
const std::filesystem::path kGalaxyNif =
    kProjectRoot / "game" / "data" / "Models" / "Ships" / "Galaxy" / "Galaxy.nif";
const std::filesystem::path kGalaxyTex =
    kProjectRoot / "game" / "data" / "Models" / "SharedTextures" / "FedShips" / "High";
}  // namespace

// Regression fixture: pin Galaxy's observable material count and per-
// material Base-stage texture-index identity. The point is to detect
// silent regressions when the property-link inheritance walk lands. If
// this test starts failing, the inheritance walk has changed Galaxy's
// rendering — investigate before allowing the change.
TEST(GalaxyRegression, MaterialCountAndBaseTextureIdentity) {
    if (!std::filesystem::is_regular_file(kGalaxyNif)) {
        GTEST_SKIP() << "BC asset not available at " << kGalaxyNif;
    }
    if (!std::filesystem::is_directory(kGalaxyTex)) {
        GTEST_SKIP() << "BC texture dir not available at " << kGalaxyTex;
    }
    assets::AssetCache cache;
    auto model_h = cache.load(kGalaxyNif, kGalaxyTex);
    ASSERT_TRUE(model_h);
    const assets::Model& m = *model_h;

    // Capture invariants — fail the test on first run, then paste the
    // observed values back as concrete expectations.
    const std::size_t mat_count = m.materials.size();
    std::vector<int> base_indices;
    for (const auto& mat : m.materials) {
        base_indices.push_back(
            mat.stages[static_cast<std::size_t>(
                assets::Material::StageSlot::Base)].texture_index);
    }

    // Print invariants on every run so the values are visible in CI logs.
    std::fprintf(stderr, "Galaxy materials=%zu base_indices=[",
                 mat_count);
    for (std::size_t i = 0; i < base_indices.size(); ++i) {
        std::fprintf(stderr, "%s%d", i ? "," : "", base_indices[i]);
    }
    std::fprintf(stderr, "]\n");

    // FILL IN concrete expectations after first run. See Step 4.
    EXPECT_GT(mat_count, 0u);
}
```

Note the use of `OPEN_STBC_PROJECT_ROOT` — already defined as a compile definition for `assets_tests` in `native/tests/assets/CMakeLists.txt`.

- [ ] **Step 3: Run the test to discover the current values**

```bash
cmake --build build --target assets_tests -j && \
  ctest --test-dir build/native/tests/assets --output-on-failure \
        -R GalaxyRegression
```

Expected: PASS, with `stderr` containing a line like `Galaxy materials=N base_indices=[...]`. Copy the numbers from the output.

- [ ] **Step 4: Replace `EXPECT_GT` with concrete pinned values**

Edit the same test to encode the discovered values, e.g.:

```cpp
EXPECT_EQ(mat_count, /*paste observed count*/);
const std::vector<int> expected_bases = { /*paste observed indices*/ };
EXPECT_EQ(base_indices, expected_bases);
```

- [ ] **Step 5: Re-run; expect green**

```bash
ctest --test-dir build/native/tests/assets --output-on-failure -R GalaxyRegression
```

Expected: PASS with the pinned values now enforced.

- [ ] **Step 6: Commit**

```bash
git add native/tests/assets/cpu/model_build_test.cc
git commit -m "test(assets): pin Galaxy material count + base-texture identity

Regression fixture to be enforced before the property-link inheritance
walk lands. Locks the current observable Material output for the Galaxy
ship NIF so a silent regression in gather_material_inputs is caught at
unit-test time rather than via 'why does the ship look wrong'."
```

---

## Task 3: Property-link inheritance walk in `gather_material_inputs`

**Why:** Bridge shapes have empty direct `property_links`; without this fix every bridge mesh gets an empty Material and renders untextured. The change is generic and benefits any v3.x NIF that sets properties on parent NiNodes.

**Files:**
- Modify: `native/src/assets/src/model_build.cc`
- Modify: `native/tests/assets/cpu/model_build_test.cc`

- [ ] **Step 1: Add a synthetic-NIF inheritance test (failing)**

In `native/tests/assets/cpu/model_build_test.cc`, add a new method to the `ModelBuildTest` fixture below `trivial_file_with_one_trishape`:

```cpp
nif::File file_with_property_on_parent_node() {
    // Block 0: root NiNode with NO properties
    nif::NiNode root;
    root.av.obj.name = "Root";
    root.child_links = {10};  // -> mid node, id 10
    nif::File f;
    f.blocks.push_back(root);
    f.block_ids.push_back(0);

    // Block 1: mid NiNode that carries a NiMaterialProperty link.
    // child_link -> NiTriShape (id 20).
    nif::NiNode mid;
    mid.av.obj.name = "Mid";
    mid.child_links = {20};
    mid.av.property_links = {30};  // -> NiMaterialProperty
    f.blocks.push_back(mid);
    f.block_ids.push_back(10);

    // Block 2: NiTriShape (id 20) with EMPTY property_links —
    // must inherit from Mid.
    nif::NiTriShape tri;
    tri.av.obj.name = "ChildShape";
    tri.data_link = 40;
    f.blocks.push_back(tri);
    f.block_ids.push_back(20);

    // Block 3: NiMaterialProperty (id 30) with distinguishable colors.
    nif::NiMaterialProperty mp;
    mp.diffuse = {0.25f, 0.5f, 0.75f};
    f.blocks.push_back(mp);
    f.block_ids.push_back(30);

    // Block 4: NiTriShapeData (id 40)
    nif::NiTriShapeData d;
    d.num_vertices = 3;
    d.has_vertices = true;
    d.vertices = {{0, 0, 0}, {1, 0, 0}, {0, 1, 0}};
    d.has_uv = true;
    d.uv_sets.push_back({{0, 0}, {1, 0}, {0, 1}});
    d.num_triangles = 1;
    d.triangles.push_back({0, 1, 2});
    f.blocks.push_back(d);
    f.block_ids.push_back(40);

    return f;
}
```

Add the test itself:

```cpp
TEST_F(ModelBuildTest, ChildShapeInheritsParentNodeProperty) {
    auto f = file_with_property_on_parent_node();
    auto model = assets::detail::build_model(f, make_ctx());
    ASSERT_EQ(model.materials.size(), 1u);
    EXPECT_FLOAT_EQ(model.materials[0].diffuse.x, 0.25f);
    EXPECT_FLOAT_EQ(model.materials[0].diffuse.y, 0.5f);
    EXPECT_FLOAT_EQ(model.materials[0].diffuse.z, 0.75f);
}
```

- [ ] **Step 2: Run; expect FAIL**

```bash
cmake --build build --target assets_tests -j && \
  ctest --test-dir build/native/tests/assets --output-on-failure \
        -R ChildShapeInheritsParentNodeProperty
```

Expected: FAIL (diffuse stays at default `(1, 1, 1)` because `gather_material_inputs` only reads the shape's own `property_links`).

- [ ] **Step 3: Add child→parent map + inheritance walk to model_build.cc**

In `native/src/assets/src/model_build.cc`, replace the existing `gather_material_inputs` and its caller. First, just above `gather_material_inputs`, add the helper:

```cpp
/// child_link → parent NiNode block index. Built once per build_model
/// invocation and reused for every shape's inheritance walk. Keys are
/// NIF link IDs (the values stored in cross-block references), not block
/// array indices, to match every other cross-ref site in this file.
using ChildToParentMap = std::unordered_map<std::uint32_t, std::size_t>;

ChildToParentMap build_child_to_parent_map(const nif::File& f) {
    ChildToParentMap out;
    out.reserve(f.blocks.size());
    for (std::size_t i = 0; i < f.blocks.size(); ++i) {
        const auto* n = std::get_if<nif::NiNode>(&f.blocks[i]);
        if (!n) continue;
        for (std::uint32_t c : n->child_links) {
            out[c] = i;
        }
    }
    return out;
}
```

Now replace `gather_material_inputs`'s body to walk inherited links. The full replacement:

```cpp
MaterialInputs gather_material_inputs(
    const nif::File& f,
    std::uint32_t shape_block_index,
    const nif::NiTriShape& shape,
    const ChildToParentMap& child_to_parent,
    const std::unordered_map<std::uint32_t, int>& image_to_texture,
    const std::unordered_set<std::uint32_t>& glow_image_links,
    const std::unordered_set<std::uint32_t>& specular_image_links,
    const std::unordered_map<std::uint32_t, int>& sibling_specular_for_image,
    const LinkResolver& resolver)
{
    MaterialInputs in;
    in.image_to_texture = &image_to_texture;
    in.glow_image_links = &glow_image_links;
    in.specular_image_links = &specular_image_links;
    in.sibling_specular_for_image = &sibling_specular_for_image;

    auto consider = [&](std::uint32_t link) {
        auto idx = resolver.resolve(link);
        if (idx == LinkResolver::kInvalidIndex) return;
        if (idx >= f.blocks.size()) return;
        const auto& b = f.blocks[idx];
        // Child overrides parent: only set each per-type slot if it's
        // empty. The walk visits the shape's own links first (depth 0),
        // then walks up the parent chain.
        if (auto* p = std::get_if<nif::NiMaterialProperty>(&b)) {
            if (!in.material) in.material = p;
        } else if (auto* p = std::get_if<nif::NiTextureProperty>(&b)) {
            if (!in.texture) in.texture = p;
        } else if (auto* p = std::get_if<nif::NiMultiTextureProperty>(&b)) {
            if (!in.multi_texture) in.multi_texture = p;
        } else if (auto* p = std::get_if<nif::NiAlphaProperty>(&b)) {
            if (!in.alpha) in.alpha = p;
        } else if (auto* p = std::get_if<nif::NiZBufferProperty>(&b)) {
            if (!in.zbuffer) in.zbuffer = p;
        } else if (auto* p = std::get_if<nif::NiVertexColorProperty>(&b)) {
            if (!in.vertex_color) in.vertex_color = p;
        }
    };

    // 1. Shape's own property_links (highest priority).
    for (auto link : shape.av.property_links) consider(link);

    // 2. Walk up the parent NiNode chain. `cur_id` is the link ID we're
    // looking up as a child in `child_to_parent`. Starts as the shape's
    // own link ID and updates to each ancestor's as we walk up.
    if (shape_block_index >= f.block_ids.size()) return in;
    std::uint32_t cur_id = f.block_ids[shape_block_index];
    while (true) {
        auto it = child_to_parent.find(cur_id);
        if (it == child_to_parent.end()) break;
        const std::size_t parent_idx = it->second;
        const auto* parent = std::get_if<nif::NiNode>(&f.blocks[parent_idx]);
        if (!parent) break;
        for (auto link : parent->av.property_links) consider(link);
        cur_id = f.block_ids[parent_idx];
    }

    return in;
}
```

Update the single call site in `build_model`:

```cpp
auto child_to_parent = build_child_to_parent_map(f);
// ... existing code, then inside the trishape loop:
auto mat_inputs = gather_material_inputs(
    f, /*shape_block_index=*/i, *shape, child_to_parent,
    tex_result.image_to_texture, tex_result.glow_image_links,
    tex_result.specular_image_links,
    tex_result.sibling_specular_for_image, resolver);
```

- [ ] **Step 4: Run the new test; expect PASS**

```bash
cmake --build build --target assets_tests -j && \
  ctest --test-dir build/native/tests/assets --output-on-failure \
        -R ChildShapeInheritsParentNodeProperty
```

Expected: PASS.

- [ ] **Step 5: Run the Galaxy regression test; expect PASS (no change)**

```bash
ctest --test-dir build/native/tests/assets --output-on-failure -R GalaxyRegression
```

Expected: PASS. If FAIL: investigate via the probe sweep from Task 1 — the inheritance walk has changed Galaxy's materials, and we need to understand why before continuing.

- [ ] **Step 6: Run the full assets and renderer test suites; expect PASS**

```bash
ctest --test-dir build/native/tests/assets --output-on-failure && \
  ctest --test-dir build/native/tests/renderer --output-on-failure
```

Expected: all PASS. Frame test (`OpaquePassRunsWithoutGLError`) still draws the Galaxy lit — no visual regression.

- [ ] **Step 7: Commit**

```bash
git add native/src/assets/src/model_build.cc native/tests/assets/cpu/model_build_test.cc
git commit -m "fix(assets): walk parent NiNode property_links during material build

v3.x BC NIFs commonly set NiMaterialProperty / NiTextureProperty etc. on
a parent NiNode and inherit them down to child NiTriShapes. The old
gather_material_inputs only read the shape's own property_links, so any
shape with empty links got a default-constructed Material. DBridge.NIF
has 145 shapes that all rely on inheritance — every one rendered
untextured.

Walk: shape's own links first (highest priority), then each ancestor
NiNode in turn; first match per property type wins. Galaxy regression
fixture confirms ships are unaffected."
```

---

## Task 4: Lightmap-pass tagging on `Material`

**Why:** The bridge pass needs to partition meshes into base vs lightmap sub-passes. Tag is set at material-build time when the Base-stage texture filename matches BC's `_lm.tga` / ` lm.tga` authoring convention.

**Files:**
- Modify: `native/src/assets/include/assets/material.h`
- Modify: `native/src/assets/src/material_build.h`
- Modify: `native/src/assets/src/material_build.cc`
- Modify: `native/src/assets/src/model_build.cc`
- Modify: `native/tests/assets/cpu/material_build_test.cc`

- [ ] **Step 1: Add `lightmap_pass` field to `Material`**

Edit `native/src/assets/include/assets/material.h`. After the existing `stages` array field and before `// From NiAlphaProperty`, add:

```cpp
    /// True when the Base-stage source texture's filename matches BC's
    /// baked-lightmap authoring convention (` lm.tga` or `_lm.tga`,
    /// case-insensitive). Bridge geometry has duplicate meshes whose
    /// only material is a lightmap texture; those meshes need a
    /// multiply-blend draw over the regular base-textured geometry.
    /// Renderer's BridgePass reads this to partition bridge sub-passes.
    bool lightmap_pass = false;
```

- [ ] **Step 2: Add filename-accessor to `MaterialInputs`**

Edit `native/src/assets/src/material_build.h`. After the existing `sibling_specular_for_image` field in `MaterialInputs`, add:

```cpp
    /// Maps NIF link ID of a NiImage → its source filename
    /// (NiImage::file_name). Used by build_material to apply BC's
    /// `_lm.tga` lightmap-pass filename predicate without having to
    /// chase the NiImage block through nif::File from the predicate
    /// site. Populated by load_all_textures for `use_external != 0`
    /// images; embedded images (NiRawImageData) leave no entry.
    const std::unordered_map<std::uint32_t, std::string>* image_filename_for_link = nullptr;
```

Add `#include <string>` at the top.

- [ ] **Step 3: Add the filename predicate and wire it (failing test first)**

Add a positive and negative test to `native/tests/assets/cpu/material_build_test.cc` before the closing brace:

```cpp
TEST(MaterialBuild, LightmapPassFlagSetForLmFilename) {
    nif::NiTextureProperty tex;
    tex.image_link = 7;
    std::unordered_map<std::uint32_t, int> image_to_texture = {{7, 0}};
    std::unordered_map<std::uint32_t, std::string> filenames = {
        {7, "DBridge/door 04a lm.tga"}};

    assets::detail::MaterialInputs in;
    in.texture = &tex;
    in.image_to_texture = &image_to_texture;
    in.image_filename_for_link = &filenames;
    auto m = assets::detail::build_material(in);
    EXPECT_TRUE(m.lightmap_pass);
}

TEST(MaterialBuild, LightmapPassFlagFalseForRegularBase) {
    nif::NiTextureProperty tex;
    tex.image_link = 5;
    std::unordered_map<std::uint32_t, int> image_to_texture = {{5, 0}};
    std::unordered_map<std::uint32_t, std::string> filenames = {
        {5, "Map 19.tga"}};

    assets::detail::MaterialInputs in;
    in.texture = &tex;
    in.image_to_texture = &image_to_texture;
    in.image_filename_for_link = &filenames;
    auto m = assets::detail::build_material(in);
    EXPECT_FALSE(m.lightmap_pass);
}

TEST(MaterialBuild, LightmapPassFlagSetForUnderscoreLmFilename) {
    nif::NiTextureProperty tex;
    tex.image_link = 8;
    std::unordered_map<std::uint32_t, int> image_to_texture = {{8, 0}};
    std::unordered_map<std::uint32_t, std::string> filenames = {
        {8, "modder_panel_lm.tga"}};

    assets::detail::MaterialInputs in;
    in.texture = &tex;
    in.image_to_texture = &image_to_texture;
    in.image_filename_for_link = &filenames;
    auto m = assets::detail::build_material(in);
    EXPECT_TRUE(m.lightmap_pass);
}
```

- [ ] **Step 4: Run; expect FAIL**

```bash
cmake --build build --target assets_tests -j && \
  ctest --test-dir build/native/tests/assets --output-on-failure -R LightmapPassFlag
```

Expected: FAIL on `LightmapPassFlagSetForLmFilename` (and the underscore variant) — `lightmap_pass` stays false.

- [ ] **Step 5: Implement the predicate in material_build.cc**

In `native/src/assets/src/material_build.cc`, add a helper near the top of the anonymous namespace (below `apply_vertex_color_property`):

```cpp
/// True when `fname`'s basename (case-insensitive) ends in either
/// " lm.tga" (space-separated, as in stock BC content like
/// "door 04a lm.tga") or "_lm.tga" (underscore-separated, as a future
/// authoring-tool convention). Matches BC's baked-lightmap filename
/// rule for bridge geometry.
bool filename_is_lightmap(std::string_view fname) {
    auto lower_ends_with = [](std::string_view s, std::string_view suffix) {
        if (s.size() < suffix.size()) return false;
        for (std::size_t i = 0; i < suffix.size(); ++i) {
            char c = s[s.size() - suffix.size() + i];
            c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            if (c != suffix[i]) return false;
        }
        return true;
    };
    return lower_ends_with(fname, " lm.tga") ||
           lower_ends_with(fname, "_lm.tga");
}
```

Add `#include <string_view>` and `#include <cctype>` to the top of the file if not already present.

Now wire it into `build_material`. Replace the function body so that after the Base stage is populated, the lightmap_pass flag is set when applicable. Specifically, append at the end of `build_material` (just before `return m;`):

```cpp
// Apply BC's lightmap filename convention. Reads the source filename
// for whichever NiImage ended up bound to the Base stage. Only checks
// the Base slot: stock BC bridges use NiMultiTextureProperty with ONLY
// the Base stage populated (containing the *_lm.tga path); single-
// stage NiTextureProperty bridges work the same way. If a non-lm
// image is bound to Base, the flag stays false even when other stages
// reference lightmap-suffixed files.
if (in.image_filename_for_link) {
    std::uint32_t base_image_link = 0;
    bool have_base_link = false;
    if (in.texture && !(in.specular_image_links &&
        in.specular_image_links->find(in.texture->image_link) !=
        in.specular_image_links->end())) {
        base_image_link = in.texture->image_link;
        have_base_link = true;
    } else if (in.multi_texture && in.multi_texture->elements[0].has_image) {
        base_image_link = in.multi_texture->elements[0].image_link;
        have_base_link = true;
    }
    if (have_base_link) {
        auto it = in.image_filename_for_link->find(base_image_link);
        if (it != in.image_filename_for_link->end()) {
            if (filename_is_lightmap(it->second)) {
                m.lightmap_pass = true;
            }
        }
    }
}
```

- [ ] **Step 6: Run; expect PASS**

```bash
cmake --build build --target assets_tests -j && \
  ctest --test-dir build/native/tests/assets --output-on-failure -R LightmapPassFlag
```

Expected: all three new tests PASS.

- [ ] **Step 7: Wire the filename map through model_build.cc**

In `native/src/assets/src/model_build.cc`, extend `TextureLoadResult`:

```cpp
struct TextureLoadResult {
    std::unordered_map<std::uint32_t, int> image_to_texture;
    std::unordered_set<std::uint32_t>      glow_image_links;
    std::unordered_set<std::uint32_t>      specular_image_links;
    std::unordered_map<std::uint32_t, int> sibling_specular_for_image;
    /// NIF link ID -> source filename (NiImage::file_name) for external
    /// images. Used by material_build's lightmap-pass predicate.
    std::unordered_map<std::uint32_t, std::string> image_filename_for_link;
};
```

In `load_all_textures`, after the line `out.image_to_texture[link_id] = ...;`, add:

```cpp
if (img->use_external != 0) {
    out.image_filename_for_link[link_id] = img->file_name;
}
```

In `build_model`, where `gather_material_inputs` is called, pass it through. After populating `mat_inputs`, set:

```cpp
mat_inputs.image_filename_for_link = &tex_result.image_filename_for_link;
```

(Add this line immediately after the existing `gather_material_inputs` assignment block.)

- [ ] **Step 8: Add an integration test — DBridge.NIF has the expected lightmap_pass distribution**

Append to `native/tests/assets/cpu/model_build_test.cc`:

```cpp
TEST(DBridgeIntegration, MaterialLightmapPassDistribution) {
    const std::filesystem::path nif =
        std::filesystem::path(OPEN_STBC_PROJECT_ROOT) /
        "game/data/Models/Sets/DBridge/Dbridge.NIF";
    const std::filesystem::path tex =
        std::filesystem::path(OPEN_STBC_PROJECT_ROOT) /
        "game/data/Models/Sets/DBridge/High";
    if (!std::filesystem::is_regular_file(nif)) {
        GTEST_SKIP() << "BC asset not available at " << nif;
    }
    if (!std::filesystem::is_directory(tex)) {
        GTEST_SKIP() << "BC texture dir not available at " << tex;
    }
    assets::AssetCache cache;
    auto model_h = cache.load(nif, tex);
    ASSERT_TRUE(model_h);

    int lm = 0, base_only = 0;
    for (const auto& m : model_h->materials) {
        if (m.lightmap_pass) ++lm;
        else                 ++base_only;
    }
    std::fprintf(stderr,
                 "DBridge: %d lightmap_pass materials, %d base-only\n",
                 lm, base_only);
    EXPECT_EQ(model_h->materials.size(), 145u);
    EXPECT_EQ(lm, 17);
    EXPECT_EQ(base_only, 128);
}
```

- [ ] **Step 9: Run integration test; expect PASS**

```bash
cmake --build build --target assets_tests -j && \
  ctest --test-dir build/native/tests/assets --output-on-failure -R DBridgeIntegration
```

Expected: PASS, `stderr` contains `DBridge: 17 lightmap_pass materials, 128 base-only`.

- [ ] **Step 10: Run full test suite; expect PASS**

```bash
ctest --test-dir build/native/tests/assets --output-on-failure && \
  ctest --test-dir build/native/tests/renderer --output-on-failure
```

Expected: PASS. Galaxy regression untouched.

- [ ] **Step 11: Commit**

```bash
git add native/src/assets/include/assets/material.h \
        native/src/assets/src/material_build.h \
        native/src/assets/src/material_build.cc \
        native/src/assets/src/model_build.cc \
        native/tests/assets/cpu/material_build_test.cc \
        native/tests/assets/cpu/model_build_test.cc
git commit -m "feat(assets): tag lightmap-pass materials by filename suffix

Materials whose Base-stage source texture filename ends in ' lm.tga' or
'_lm.tga' (case-insensitive) are now flagged Material::lightmap_pass.
Matches BC's bridge-authoring convention where lightmap meshes are
authored as separate geometry with a single _lm.tga base texture, to be
drawn over the regular base-textured geometry with multiply blend.

DBridge.NIF: 145 materials, 17 lightmap_pass, 128 base-only — matches
the prior probe_texture_stages survey."
```

---

## Task 5: Bridge and lightmap shaders

**Why:** Two dedicated shader programs for the two bridge sub-passes — keeps the bridge pipeline self-contained and decoupled from the ship opaque path.

**Files:**
- Create: `native/src/renderer/shaders/bridge.vert`
- Create: `native/src/renderer/shaders/bridge.frag`
- Create: `native/src/renderer/shaders/lightmap.vert`
- Create: `native/src/renderer/shaders/lightmap.frag`
- Modify: `native/src/renderer/CMakeLists.txt`
- Modify: `native/src/renderer/include/renderer/pipeline.h`
- Modify: `native/src/renderer/pipeline.cc`
- Modify: `native/tests/renderer/pipeline_test.cc`

- [ ] **Step 1: Write `bridge.vert`**

Create `native/src/renderer/shaders/bridge.vert`:

```glsl
#version 330 core

layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec2 a_uv;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;

out vec2 v_uv;

void main() {
    v_uv = a_uv;
    gl_Position = u_proj * u_view * u_model * vec4(a_position, 1.0);
}
```

- [ ] **Step 2: Write `bridge.frag`**

Create `native/src/renderer/shaders/bridge.frag`:

```glsl
#version 330 core

in vec2 v_uv;

uniform sampler2D u_base_color;
uniform vec3 u_ambient;
uniform float u_alpha_test_threshold;

out vec4 FragColor;

void main() {
    vec4 base = texture(u_base_color, v_uv);
    if (base.a < u_alpha_test_threshold) discard;
    FragColor = vec4(base.rgb * u_ambient, 1.0);
}
```

- [ ] **Step 3: Write `lightmap.vert`**

Create `native/src/renderer/shaders/lightmap.vert`:

```glsl
#version 330 core

layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec2 a_uv;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;

out vec2 v_uv;

void main() {
    v_uv = a_uv;
    gl_Position = u_proj * u_view * u_model * vec4(a_position, 1.0);
}
```

- [ ] **Step 4: Write `lightmap.frag`**

Create `native/src/renderer/shaders/lightmap.frag`:

```glsl
#version 330 core

in vec2 v_uv;

uniform sampler2D u_lightmap;

out vec4 FragColor;

void main() {
    FragColor = texture(u_lightmap, v_uv);
}
```

- [ ] **Step 5: Embed shaders in CMakeLists**

Edit `native/src/renderer/CMakeLists.txt`. After the existing `embed_shader(SHADER_PHASER_FS ...)` line and before `add_library(renderer STATIC`, add:

```cmake
embed_shader(SHADER_BRIDGE_VS shaders/bridge.vert bridge_vs)
embed_shader(SHADER_BRIDGE_FS shaders/bridge.frag bridge_fs)
embed_shader(SHADER_LIGHTMAP_VS shaders/lightmap.vert lightmap_vs)
embed_shader(SHADER_LIGHTMAP_FS shaders/lightmap.frag lightmap_fs)
```

- [ ] **Step 6: Add `bridge_shader()` and `lightmap_shader()` to Pipeline**

Edit `native/src/renderer/include/renderer/pipeline.h`. Add two accessors and two unique_ptr members:

```cpp
    Shader& bridge_shader() noexcept   { return *bridge_; }
    Shader& lightmap_shader() noexcept { return *lightmap_; }
```

and in the private section:

```cpp
    std::unique_ptr<Shader> bridge_;
    std::unique_ptr<Shader> lightmap_;
```

Edit `native/src/renderer/pipeline.cc`. After the existing `#include "embedded_phaser_fs.h"` add:

```cpp
#include "embedded_bridge_vs.h"
#include "embedded_bridge_fs.h"
#include "embedded_lightmap_vs.h"
#include "embedded_lightmap_fs.h"
```

In `Pipeline::Pipeline()`, after the existing `phaser_ = ...` line, add:

```cpp
    bridge_   = std::make_unique<Shader>(shader_src::bridge_vs,   shader_src::bridge_fs);
    lightmap_ = std::make_unique<Shader>(shader_src::lightmap_vs, shader_src::lightmap_fs);
```

- [ ] **Step 7: Add a pipeline test that the new shaders compile and link**

Open `native/tests/renderer/pipeline_test.cc`. Append a test that constructs a `Pipeline` and calls each new accessor:

```cpp
TEST_F(PipelineTest, BridgeAndLightmapShadersAvailable) {
    renderer::Pipeline p;
    EXPECT_NE(p.bridge_shader().program(), 0u);
    EXPECT_NE(p.lightmap_shader().program(), 0u);
}
```

If the existing fixture name is different from `PipelineTest`, match it. Confirm by:

```bash
grep -E "^TEST(_F)?\(" native/tests/renderer/pipeline_test.cc
```

If the fixture name differs, copy the form used by surrounding tests.

- [ ] **Step 8: Reconfigure and build (shader embedding runs at configure time)**

```bash
cmake -B build -S . && cmake --build build --target renderer_tests -j
```

Expected: success.

- [ ] **Step 9: Run pipeline test; expect PASS**

```bash
ctest --test-dir build/native/tests/renderer --output-on-failure \
      -R BridgeAndLightmapShadersAvailable
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add native/src/renderer/shaders/bridge.vert \
        native/src/renderer/shaders/bridge.frag \
        native/src/renderer/shaders/lightmap.vert \
        native/src/renderer/shaders/lightmap.frag \
        native/src/renderer/CMakeLists.txt \
        native/src/renderer/include/renderer/pipeline.h \
        native/src/renderer/pipeline.cc \
        native/tests/renderer/pipeline_test.cc
git commit -m "feat(renderer): bridge and lightmap shader programs

Two dedicated shader pairs for the bridge pipeline:
  bridge.{vert,frag}   — base * ambient with alpha-test for LCARS panels
  lightmap.{vert,frag} — pure texture sample for the multiply-blend pass

Registered on Pipeline alongside the existing opaque/sun/dust/etc.
programs. BridgePass (next commit) consumes them."
```

---

## Task 6: `BridgePass` class — skeleton, base sub-pass (A)

**Why:** Centralise the bridge-pass GL state machine in its own class, mirroring SunPass/DustPass/PhaserPass. First commit covers the partitioning + base sub-pass; lightmap sub-pass lands in Task 7.

**Files:**
- Create: `native/src/renderer/include/renderer/bridge_pass.h`
- Create: `native/src/renderer/bridge_pass.cc`
- Create: `native/tests/renderer/bridge_pass_test.cc`
- Modify: `native/src/renderer/CMakeLists.txt`
- Modify: `native/tests/renderer/CMakeLists.txt`

- [ ] **Step 1: Write `bridge_pass.h`**

Create `native/src/renderer/include/renderer/bridge_pass.h`:

```cpp
// native/src/renderer/include/renderer/bridge_pass.h
#pragma once

#include <renderer/frame.h>

#include <functional>

namespace scenegraph { class World; struct Camera; }

namespace renderer {

class Pipeline;

/// Renders the bridge interior in two sub-passes:
///   A. Base geometry — opaque, alpha-test, base * ambient via bridge.frag.
///   B. Lightmap geometry — multiply blend over the framebuffer via
///      lightmap.frag, depth-write off + polygon offset.
///
/// Caller is responsible for clearing color + depth before calling
/// render() (the bridge interior overlays the space scene; see
/// host_bindings.cc::frame). Renders nothing if the world has no
/// scenegraph::Pass::Bridge-tagged instances.
class BridgePass {
public:
    using ModelLookup = std::function<const assets::Model*(unsigned long long)>;

    BridgePass() = default;
    ~BridgePass();
    BridgePass(const BridgePass&) = delete;
    BridgePass& operator=(const BridgePass&) = delete;

    void render(const scenegraph::World& world,
                const scenegraph::Camera& camera,
                Pipeline& pipeline,
                const ModelLookup& lookup,
                const Lighting& lighting);

private:
    /// Lazily-allocated 1x1 white texture, used as a fallback for any
    /// bridge mesh whose Base-stage texture failed to load. Same role
    /// as FrameSubmitter::white_texture_ but owned by this pass so the
    /// GL handle lifetime tracks BridgePass.
    std::uint32_t white_texture_ = 0;
    std::uint32_t ensure_white_texture();
};

}  // namespace renderer
```

- [ ] **Step 2: Write `bridge_pass.cc` — skeleton + sub-pass A**

Create `native/src/renderer/bridge_pass.cc`:

```cpp
// native/src/renderer/bridge_pass.cc
#include "renderer/bridge_pass.h"
#include "renderer/pipeline.h"

#include <glad/glad.h>

#include <scenegraph/world.h>
#include <scenegraph/camera.h>
#include <scenegraph/instance.h>

#include <assets/model.h>
#include <assets/mesh.h>
#include <assets/texture.h>
#include <assets/material.h>

#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>

namespace renderer {

BridgePass::~BridgePass() {
    if (white_texture_ != 0) {
        GLuint t = white_texture_;
        glDeleteTextures(1, &t);
        white_texture_ = 0;
    }
}

std::uint32_t BridgePass::ensure_white_texture() {
    if (white_texture_ != 0) return white_texture_;
    GLuint t = 0;
    glGenTextures(1, &t);
    glBindTexture(GL_TEXTURE_2D, t);
    const std::uint8_t white[4] = {255, 255, 255, 255};
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 1, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, white);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glBindTexture(GL_TEXTURE_2D, 0);
    white_texture_ = t;
    return white_texture_;
}

namespace {

/// Walk every visible bridge-tagged instance's meshes; for each mesh
/// whose Material::lightmap_pass == `want_lightmap_pass`, compute its
/// world-space transform and issue a draw via `draw_one`.
template <typename DrawOne>
void walk_bridge_meshes(const scenegraph::World& world,
                        const BridgePass::ModelLookup& lookup,
                        bool want_lightmap_pass,
                        const DrawOne& draw_one) {
    world.for_each_visible_in_pass(scenegraph::Pass::Bridge,
        [&](const scenegraph::Instance& inst) {
            const assets::Model* m = lookup(inst.model_handle);
            if (!m) return;
            std::vector<glm::mat4> world_per_node(m->nodes.size(), glm::mat4(1.0f));
            if (!m->nodes.empty()) {
                world_per_node[m->root_node] =
                    inst.world * m->nodes[m->root_node].local_transform;
            }
            for (std::size_t i = 0; i < m->nodes.size(); ++i) {
                const auto& node = m->nodes[i];
                if (node.parent_index >= 0) {
                    world_per_node[i] =
                        world_per_node[node.parent_index] * node.local_transform;
                }
                for (int mesh_idx : node.meshes) {
                    const auto& mesh = m->meshes[mesh_idx];
                    const auto& mat = (mesh.material_index() >= 0
                        ? m->materials[mesh.material_index()]
                        : assets::Material{});
                    if (mat.lightmap_pass != want_lightmap_pass) continue;
                    draw_one(*m, mesh, mat, world_per_node[i]);
                }
            }
        });
}

void draw_mesh(const assets::Model& model,
               const assets::Mesh& mesh,
               const assets::Material& mat,
               Shader& shader,
               const glm::mat4& world,
               GLuint white_fallback) {
    shader.set_mat4("u_model", world);
    const int base_tex = mat.stages[
        static_cast<std::size_t>(assets::Material::StageSlot::Base)
    ].texture_index;
    glActiveTexture(GL_TEXTURE0);
    if (base_tex >= 0) {
        glBindTexture(GL_TEXTURE_2D, model.textures[base_tex].id());
    } else {
        glBindTexture(GL_TEXTURE_2D, white_fallback);
    }
    glBindVertexArray(mesh.vao());
    glDrawElements(GL_TRIANGLES, mesh.index_count(), GL_UNSIGNED_INT, nullptr);
}

}  // namespace

void BridgePass::render(const scenegraph::World& world,
                        const scenegraph::Camera& camera,
                        Pipeline& pipeline,
                        const ModelLookup& lookup,
                        const Lighting& lighting) {
    // ── Sub-pass A: base geometry, opaque, base × ambient, alpha-test ──
    auto& base_shader = pipeline.bridge_shader();
    base_shader.use();
    base_shader.set_mat4("u_view", camera.view_matrix());
    base_shader.set_mat4("u_proj", camera.proj_matrix());
    base_shader.set_vec3("u_ambient", lighting.ambient);
    base_shader.set_int("u_base_color", 0);
    base_shader.set_float("u_alpha_test_threshold", 0.5f);

    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LESS);
    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);

    const GLuint white = ensure_white_texture();
    walk_bridge_meshes(world, lookup, /*want_lightmap_pass=*/false,
        [&](const assets::Model& m, const assets::Mesh& mesh,
            const assets::Material& mat, const glm::mat4& w) {
            draw_mesh(m, mesh, mat, base_shader, w, white);
        });

    // Sub-pass B (lightmap multiply) lands in Task 7.
    (void)lighting;  // intentional: lightmap pass doesn't read it.
    glBindVertexArray(0);
}

}  // namespace renderer
```

- [ ] **Step 3: Add to CMakeLists**

Edit `native/src/renderer/CMakeLists.txt`. In `add_library(renderer STATIC` block, after `phaser_pass.cc`, add:

```cmake
    bridge_pass.cc
```

- [ ] **Step 4: Write the partitioning test (CPU-side, no GL context needed)**

Note: this test only verifies behaviour observable without a GL context — we walk bridge instances via `for_each_visible_in_pass`, partition by `Material::lightmap_pass`, count expected calls. The actual `render()` is harder to test without a GL context; we test the partitioning logic by exposing a helper or by simulating.

Create `native/tests/renderer/bridge_pass_test.cc`:

```cpp
// native/tests/renderer/bridge_pass_test.cc
//
// CPU-side test that BridgePass partitions bridge-tagged meshes by
// Material::lightmap_pass. We cannot invoke BridgePass::render() here
// (it issues real GL calls), so we verify partitioning by counting
// matching meshes in a fake Model+World; the BridgePass implementation
// uses the same predicate (mat.lightmap_pass == want_lightmap_pass).
#include <gtest/gtest.h>

#include <assets/material.h>
#include <assets/mesh.h>
#include <assets/model.h>

#include <scenegraph/world.h>
#include <scenegraph/instance.h>

namespace {

assets::Mesh make_stub_mesh(int material_index) {
    return assets::Mesh(/*vao=*/0, /*vbo=*/0, /*ebo=*/0,
                        /*index_count=*/3, material_index, /*node_index=*/0);
}

}  // namespace

TEST(BridgePassPartitioning, CountsBaseAndLightmapMeshesSeparately) {
    assets::Model model;
    model.materials.push_back(assets::Material{});                 // 0 base
    model.materials.push_back(assets::Material{});                 // 1 base
    {
        assets::Material lm;
        lm.lightmap_pass = true;
        model.materials.push_back(std::move(lm));                  // 2 lm
    }
    model.meshes.push_back(make_stub_mesh(0));
    model.meshes.push_back(make_stub_mesh(1));
    model.meshes.push_back(make_stub_mesh(2));
    assets::Node root;
    root.meshes = {0, 1, 2};
    model.nodes.push_back(std::move(root));
    model.root_node = 0;

    scenegraph::World world;
    auto h = reinterpret_cast<scenegraph::ModelHandle>(&model);
    auto iid = world.create_instance(h);
    world.set_pass(iid, scenegraph::Pass::Bridge);

    int base_count = 0, lm_count = 0;
    world.for_each_visible_in_pass(scenegraph::Pass::Bridge,
        [&](const scenegraph::Instance& inst) {
            const auto* m = reinterpret_cast<const assets::Model*>(inst.model_handle);
            for (const auto& mesh : m->meshes) {
                const auto& mat = m->materials[mesh.material_index()];
                if (mat.lightmap_pass) ++lm_count;
                else                    ++base_count;
            }
        });

    EXPECT_EQ(base_count, 2);
    EXPECT_EQ(lm_count, 1);
}

TEST(BridgePassPartitioning, SkipsNonBridgePassInstances) {
    assets::Model model;
    model.materials.push_back(assets::Material{});
    model.meshes.push_back(make_stub_mesh(0));
    assets::Node root;
    root.meshes = {0};
    model.nodes.push_back(std::move(root));
    model.root_node = 0;

    scenegraph::World world;
    auto h = reinterpret_cast<scenegraph::ModelHandle>(&model);
    auto iid_space = world.create_instance(h);   // default Pass::Space
    auto iid_bridge = world.create_instance(h);
    world.set_pass(iid_bridge, scenegraph::Pass::Bridge);
    (void)iid_space;

    int count = 0;
    world.for_each_visible_in_pass(scenegraph::Pass::Bridge,
        [&](const scenegraph::Instance&) { ++count; });
    EXPECT_EQ(count, 1);  // only the bridge-tagged instance
}
```

Add to `native/tests/renderer/CMakeLists.txt` — inside the `add_executable(renderer_tests` list, after `lens_flare_pass_test.cc`, append `bridge_pass_test.cc`.

- [ ] **Step 5: Build and run**

```bash
cmake -B build -S . && cmake --build build --target renderer_tests -j && \
  ctest --test-dir build/native/tests/renderer --output-on-failure \
        -R BridgePassPartitioning
```

Expected: both new tests PASS.

- [ ] **Step 6: Commit**

```bash
git add native/src/renderer/include/renderer/bridge_pass.h \
        native/src/renderer/bridge_pass.cc \
        native/src/renderer/CMakeLists.txt \
        native/tests/renderer/bridge_pass_test.cc \
        native/tests/renderer/CMakeLists.txt
git commit -m "feat(renderer): BridgePass skeleton + base sub-pass

Adds a dedicated BridgePass class encapsulating the bridge interior's
GL state machine. This commit implements sub-pass A only: opaque draw
of non-lightmap bridge meshes via bridge.{vert,frag}, base * ambient,
alpha-test enabled at 0.5.

Sub-pass B (lightmap multiply blend) follows in the next commit.

Not yet wired into host_bindings — that swap-over lands once both
sub-passes are in."
```

---

## Task 7: `BridgePass` sub-pass B — lightmap multiply

**Why:** Add the second sub-pass that draws lightmap-tagged meshes over the base geometry with multiply blend, completing the visual model.

**Files:**
- Modify: `native/src/renderer/bridge_pass.cc`

- [ ] **Step 1: Replace the sub-pass B placeholder with the real implementation**

In `native/src/renderer/bridge_pass.cc`, find this block:

```cpp
    // Sub-pass B (lightmap multiply) lands in Task 7.
    (void)lighting;  // intentional: lightmap pass doesn't read it.
    glBindVertexArray(0);
```

Replace it with:

```cpp
    // ── Sub-pass B: lightmap geometry, multiply blend over framebuffer ──
    // GL state for fixed-function-style multiply lightmaps:
    //   LEQUAL  — lightmap mesh is coplanar with the base mesh under it
    //             in most stock content; LESS would reject every fragment
    //             on exact-coplanar duplicates.
    //   depth-write OFF — sub-pass B does not contribute to the depth
    //             buffer; only A's opaque pass owns depth.
    //   blend DST_COLOR/ZERO — `framebuffer *= lightmap`, the canonical
    //             multiply-blend lightmap composite.
    //   polygon offset (-1, -1) — handles floating-point drift between
    //             the base and lightmap copies even when nominally
    //             coplanar; cheap and standard for this pattern.
    auto& lm_shader = pipeline.lightmap_shader();
    lm_shader.use();
    lm_shader.set_mat4("u_view", camera.view_matrix());
    lm_shader.set_mat4("u_proj", camera.proj_matrix());
    lm_shader.set_int("u_lightmap", 0);

    glDepthFunc(GL_LEQUAL);
    glDepthMask(GL_FALSE);
    glEnable(GL_BLEND);
    glBlendFunc(GL_DST_COLOR, GL_ZERO);
    glEnable(GL_POLYGON_OFFSET_FILL);
    glPolygonOffset(-1.0f, -1.0f);

    walk_bridge_meshes(world, lookup, /*want_lightmap_pass=*/true,
        [&](const assets::Model& m, const assets::Mesh& mesh,
            const assets::Material& mat, const glm::mat4& w) {
            draw_mesh(m, mesh, mat, lm_shader, w, white);
        });

    // Restore GL state so subsequent passes don't inherit our changes.
    glDisable(GL_POLYGON_OFFSET_FILL);
    glPolygonOffset(0.0f, 0.0f);
    glDisable(GL_BLEND);
    glDepthMask(GL_TRUE);
    glDepthFunc(GL_LESS);

    (void)lighting;
    glBindVertexArray(0);
```

- [ ] **Step 2: Build; expect success**

```bash
cmake --build build --target renderer_tests -j
```

Expected: clean build.

- [ ] **Step 3: Run all renderer tests; expect PASS**

```bash
ctest --test-dir build/native/tests/renderer --output-on-failure
```

Expected: all PASS. (The partitioning tests don't invoke `render()`, but compile-time correctness is verified by the build.)

- [ ] **Step 4: Commit**

```bash
git add native/src/renderer/bridge_pass.cc
git commit -m "feat(renderer): BridgePass sub-pass B — lightmap multiply

Second bridge sub-pass: lightmap-tagged meshes drawn over the base
geometry with multiply blend (GL_DST_COLOR, GL_ZERO), depth-write off,
GL_LEQUAL depth test, polygon-offset (-1,-1) to defeat z-fighting on
coplanar lightmap copies of the base geometry. Restores GL state at
the end so downstream passes aren't affected.

Visual result not yet observable: host_bindings still calls the legacy
submit_opaque_in_pass; switchover happens in the next commit."
```

---

## Task 8: Wire BridgePass into host_bindings; drop `submit_opaque_in_pass`

**Why:** Replace the legacy inline bridge draw with the new pass class. This is the visible-result commit.

**Files:**
- Modify: `native/src/host/host_bindings.cc`
- Modify: `native/src/renderer/include/renderer/frame.h`
- Modify: `native/src/renderer/frame.cc`

- [ ] **Step 1: Add `g_bridge_pass` and use it in `frame()`**

Edit `native/src/host/host_bindings.cc`. Add `#include <renderer/bridge_pass.h>` next to the other renderer includes.

Add a global next to the other pass unique_ptrs (just after `g_phaser_pass`):

```cpp
std::unique_ptr<renderer::BridgePass> g_bridge_pass;
```

In `init()`, after `g_phaser_pass  = std::make_unique<renderer::PhaserPass>();`, add:

```cpp
    g_bridge_pass = std::make_unique<renderer::BridgePass>();
```

In `shutdown()`, after `g_phaser_pass.reset();`, add:

```cpp
    g_bridge_pass.reset();
```

In `frame()`, replace the existing bridge-pass block:

```cpp
    if (g_bridge_pass_enabled) {
        glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        if (fh > 0) g_bridge_camera.aspect = static_cast<float>(fw) / static_cast<float>(fh);
        g_submitter->submit_opaque_in_pass(
            g_world, g_bridge_camera, *g_pipeline, lookup, g_lighting,
            scenegraph::Pass::Bridge);
    }
```

with:

```cpp
    if (g_bridge_pass_enabled && g_bridge_pass) {
        glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        if (fh > 0) g_bridge_camera.aspect = static_cast<float>(fw) / static_cast<float>(fh);
        g_bridge_pass->render(g_world, g_bridge_camera, *g_pipeline,
                              lookup, g_lighting);
    }
```

(Still passes `g_lighting`; the dedicated bridge-lighting plumbing arrives in Task 10.)

- [ ] **Step 2: Drop `submit_opaque_in_pass`**

Edit `native/src/renderer/include/renderer/frame.h`. Remove the `submit_opaque_in_pass` declaration block (the entire method including its doc comment).

Edit `native/src/renderer/frame.cc`. Remove the `FrameSubmitter::submit_opaque_in_pass` definition (the entire function body).

- [ ] **Step 3: Build and confirm no references remain**

```bash
cmake --build build -j 2>&1 | grep -E "(error|undefined|submit_opaque_in_pass)" | head -10
```

Expected: no errors and no stray references. If there are other references (e.g. in tests), grep for them:

```bash
grep -rn "submit_opaque_in_pass" native/ 2>/dev/null
```

Expected: zero matches.

- [ ] **Step 4: Run renderer + assets + host tests**

```bash
cmake --build build -j && \
  ctest --test-dir build/native/tests --output-on-failure
```

Expected: all PASS.

- [ ] **Step 5: Visual smoke test (manual)**

```bash
./build/open_stbc
```

Then in the running binary:
1. Press F (or whatever your bridge toggle is — confirm via `engine/host_loop.py` if unclear) to enter bridge mode.
2. Verify the bridge interior is visible with base textures (Map N.tga) showing.
3. Look at floor / wall insets / doors — those are the 17 lightmap-tagged regions. They should appear *darker* than full-bright (multiply blend with the lightmap reduces brightness).
4. Press ESC to exit bridge mode; verify space rendering is unchanged.

Expected: bridge renders with visible textures. Ambient is still the space-scene ambient (0.1) — likely too dark; Task 10 fixes this with the bridge-set ambient.

If the bridge renders all black or has glaring z-fighting between base and lightmap geometry: **stop, investigate, and revisit the design risks 2/4 before continuing.** The polygon offset or LEQUAL choice may need tuning.

- [ ] **Step 6: Commit**

```bash
git add native/src/host/host_bindings.cc \
        native/src/renderer/include/renderer/frame.h \
        native/src/renderer/frame.cc
git commit -m "feat(host): switch bridge rendering to BridgePass; drop submit_opaque_in_pass

Bridge pass now uses the new BridgePass class (two sub-passes: opaque
base, then lightmap multiply). The legacy FrameSubmitter::submit_opaque_in_pass
had only one caller (the bridge); removed entirely.

Visual confirmation: bridge interior textures are now visible. Lightmap
regions (floor, doors, wall insets) appear darkened by the multiply
blend against the lightmap texture, matching BC's baked-shading model.

Lighting still feeds from g_lighting (space scene); bridge-set ambient
plumbing follows in the next commits."
```

---

## Task 9: Bridge-set lighting aggregator (Python)

**Why:** Bridge ambient is authored on the bridge `SetClass`, not the space set. Without this, the bridge renders at the space scene's typical 0.1 ambient (very dark).

**Files:**
- Modify: `engine/appc/lights.py`
- Modify: `tests/unit/test_appc_lights.py`

- [ ] **Step 1: Add the resolver test (failing)**

Append to `tests/unit/test_appc_lights.py`:

```python
def test_resolve_bridge_set_returns_set_named_bridge():
    """Locate the bridge SetClass by the conventional name 'bridge'."""
    import App
    from engine.appc.lights import _resolve_bridge_set
    pSet = App.SetClass_Create()
    App.g_kSetManager.AddSet(pSet, "bridge")
    try:
        assert _resolve_bridge_set() is pSet
    finally:
        App.g_kSetManager.DeleteSet("bridge")


def test_resolve_bridge_set_returns_none_when_no_bridge():
    """No 'bridge' set registered → resolver returns None."""
    import App
    from engine.appc.lights import _resolve_bridge_set
    # Ensure no leftover "bridge" set from a prior test.
    if App.g_kSetManager.GetSet("bridge") is not None:
        App.g_kSetManager.DeleteSet("bridge")
    assert _resolve_bridge_set() is None


def test_aggregate_bridge_for_renderer_uses_bridge_set_ambient():
    """aggregate_bridge_for_renderer reads the bridge set's
    CreateAmbientLight, NOT the space scene's lighting."""
    import App
    from engine.appc.lights import aggregate_bridge_for_renderer
    pSet = App.SetClass_Create()
    App.g_kSetManager.AddSet(pSet, "bridge")
    try:
        pSet.CreateAmbientLight(1.0, 0.5, 0.25, 0.8, "ambientlight1")
        default_ambient = (0.01, 0.01, 0.01)
        ambient, directionals = aggregate_bridge_for_renderer(
            default_ambient, [])
        # Bridge ambient takes precedence; uses the same dimmer multiply
        # as the existing space aggregator.
        assert ambient == pytest.approx((0.8, 0.4, 0.2))
        assert directionals == []
    finally:
        App.g_kSetManager.DeleteSet("bridge")


def test_aggregate_bridge_for_renderer_returns_defaults_when_no_bridge():
    """No 'bridge' set → defaults flow through."""
    import App
    from engine.appc.lights import aggregate_bridge_for_renderer
    if App.g_kSetManager.GetSet("bridge") is not None:
        App.g_kSetManager.DeleteSet("bridge")
    default_ambient = (0.7, 0.7, 0.7)
    default_directionals = []
    ambient, directionals = aggregate_bridge_for_renderer(
        default_ambient, default_directionals)
    assert ambient == default_ambient
    assert directionals == default_directionals
```

- [ ] **Step 2: Run; expect FAIL**

```bash
uv run pytest tests/unit/test_appc_lights.py -k "bridge" -v
```

Expected: FAIL on import (`_resolve_bridge_set` / `aggregate_bridge_for_renderer` don't exist yet).

- [ ] **Step 3: Implement the resolver and aggregator**

Append to `engine/appc/lights.py` (after `aggregate_for_renderer`):

```python
def _resolve_bridge_set():
    """Return the bridge SetClass, or None.

    BC's convention (sdk/Build/scripts/LoadBridge.py:64): the bridge set
    is registered under the literal name "bridge" via
    g_kSetManager.AddSet(pBridgeSet, "bridge"). LoadBridge.py is the
    only producer; LoadBridge_Phase1 shim mirrors this. There is no
    per-ship-class disambiguation at this layer — bridge variants
    (DBridge, FBridge, ...) are selected upstream when LoadBridge runs.
    """
    import App
    return App.g_kSetManager.GetSet("bridge")


def aggregate_bridge_for_renderer(default_ambient, default_directionals):
    """Bridge-pass counterpart of aggregate_for_renderer.

    Pulls lighting from the bridge SetClass (resolved by name) so the
    bridge interior renders against its own authored ambient, not the
    space scene's. Returns (ambient, directionals) in the same shape as
    aggregate_for_renderer, so the binding signature is identical.

    Stock BC bridges author only CreateAmbientLight (no directionals);
    aggregate_for_renderer's directional handling is mechanically
    correct for the bridge case too, so we reuse it without modification.
    """
    pSet = _resolve_bridge_set()
    return aggregate_for_renderer(pSet, default_ambient, default_directionals)
```

- [ ] **Step 4: Run the new tests; expect PASS**

```bash
uv run pytest tests/unit/test_appc_lights.py -k "bridge" -v
```

Expected: all four new tests PASS.

- [ ] **Step 5: Run the full appc-lights suite; expect PASS**

```bash
uv run pytest tests/unit/test_appc_lights.py -v
```

Expected: all PASS (nothing regressed).

- [ ] **Step 6: Commit**

```bash
git add engine/appc/lights.py tests/unit/test_appc_lights.py
git commit -m "feat(lights): aggregate bridge-set lighting separately from space

New helpers in engine/appc/lights.py:
  _resolve_bridge_set()             — finds SetClass named 'bridge'
  aggregate_bridge_for_renderer(...) — collapses its _lights to (ambient,
                                       directionals), same shape as the
                                       existing space-set aggregator

Stock BC bridges author only CreateAmbientLight, but the directional
path is wired in so future content with directionals works mechanically."
```

---

## Task 10: `set_bridge_lighting` binding + BridgePass consumes it

**Why:** Plumb the Python-side aggregator's result through to the C++ bridge pass via a dedicated `g_bridge_lighting` global, leaving `g_lighting` for the space scene.

**Files:**
- Modify: `native/src/host/host_bindings.cc`
- Modify: `native/src/renderer/bridge_pass.cc` (only signature dependency — already takes a `Lighting&`)
- Modify: `engine/renderer.py`

- [ ] **Step 1: Add `g_bridge_lighting` global and binding**

Edit `native/src/host/host_bindings.cc`. Next to the existing `renderer::Lighting g_lighting;`, add:

```cpp
// Separate lighting state for the bridge pass. Populated by the Python
// host loop via set_bridge_lighting() each tick, mirroring the space
// pass's set_lighting() flow. Decoupled because the bridge interior's
// ambient is authored on its own SetClass and is typically much
// brighter than the space scene's.
renderer::Lighting g_bridge_lighting;
```

In `init()`, after `g_lighting = renderer::Lighting{};`, add:

```cpp
    g_bridge_lighting = renderer::Lighting{};
```

In `shutdown()`, mirror the same reset.

In the PYBIND11_MODULE block, add the binding right after `set_lighting`'s `m.def(...)` block:

```cpp
    m.def("set_bridge_lighting",
          [](std::tuple<float,float,float> ambient,
             const std::vector<std::tuple<
                 std::tuple<float,float,float>,
                 std::tuple<float,float,float>>>& directionals) {
              g_bridge_lighting.ambient = {std::get<0>(ambient),
                                           std::get<1>(ambient),
                                           std::get<2>(ambient)};
              int n = std::min(static_cast<int>(directionals.size()),
                               renderer::Lighting::MaxDirectionals);
              g_bridge_lighting.directional_count = n;
              for (int i = 0; i < n; ++i) {
                  const auto& [dir, col] = directionals[i];
                  glm::vec3 d{std::get<0>(dir), std::get<1>(dir), std::get<2>(dir)};
                  float len = glm::length(d);
                  g_bridge_lighting.directional_dir_ws[i] =
                      (len > 1e-6f) ? d / len : glm::vec3(0.0f, 1.0f, 0.0f);
                  g_bridge_lighting.directional_color[i] = {
                      std::get<0>(col), std::get<1>(col), std::get<2>(col)};
              }
          },
          py::arg("ambient"), py::arg("directionals"),
          "Set the bridge pass's lighting state, applied each frame() when "
          "the bridge pass is enabled. Separate from set_lighting (which "
          "feeds the space scene).");
```

Change the bridge-pass invocation in `frame()` to consume `g_bridge_lighting`:

```cpp
    if (g_bridge_pass_enabled && g_bridge_pass) {
        glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        if (fh > 0) g_bridge_camera.aspect = static_cast<float>(fw) / static_cast<float>(fh);
        g_bridge_pass->render(g_world, g_bridge_camera, *g_pipeline,
                              lookup, g_bridge_lighting);
    }
```

- [ ] **Step 2: Add the Python wrapper**

Edit `engine/renderer.py`. After the existing `set_lighting` wrapper, add:

```python
def set_bridge_lighting(ambient: Tuple[float, float, float],
                        directionals: list) -> None:
    """Configure the bridge pass's lighting for subsequent frame()s.

    Same shape as set_lighting, but feeds the bridge pass exclusively.
    Stock BC bridges author only ambient (directionals empty).
    """
    _h.set_bridge_lighting(ambient, directionals)
```

- [ ] **Step 3: Build and verify the module exports the new binding**

```bash
cmake --build build -j
uv run python -c "import _open_stbc_host as h; print(hasattr(h, 'set_bridge_lighting'))"
```

Expected: build success + `True`.

- [ ] **Step 4: Commit**

```bash
git add native/src/host/host_bindings.cc engine/renderer.py
git commit -m "feat(host): set_bridge_lighting binding + g_bridge_lighting global

Adds a parallel lighting global feeding BridgePass exclusively, plus
the Python binding wrapper. BridgePass now consumes g_bridge_lighting
instead of g_lighting (the space-scene lighting). Default-constructed
ambient (0.1) holds until host_loop wires the per-tick push from
aggregate_bridge_for_renderer."
```

---

## Task 11: host_loop tick wire-up + visual decision on 4th-arg

**Why:** Push the bridge-set ambient to the renderer every tick alongside the existing space-set push, and decide visually how to interpret `CreateAmbientLight`'s 4th argument (currently `dimmer × color`, with bridge values reaching 19.0 producing blown-out output).

**Files:**
- Modify: `engine/host_loop.py`
- Modify: `engine/appc/sets.py` (only if 4th-arg interpretation needs changing)
- Modify: `tests/host/test_host_loop_lighting.py`

- [ ] **Step 1: Add the tick-loop push test (failing)**

Append to `tests/host/test_host_loop_lighting.py`. First check the existing patterns:

```bash
grep -n "def test_\|set_lighting\|set_bridge_lighting" tests/host/test_host_loop_lighting.py | head -20
```

Then add a test that, when a bridge SetClass with `CreateAmbientLight` exists, the host_loop pushes a distinct bridge lighting (not the space ambient):

```python
def test_host_loop_pushes_bridge_lighting_each_tick():
    """When a 'bridge' SetClass exists with CreateAmbientLight, the host
    loop's per-tick lighting push targets set_bridge_lighting in addition
    to set_lighting. The bridge ambient is independent of the space
    scene's ambient."""
    import App
    from engine.host_loop import _aggregate_bridge_lights
    # Make sure no leftover from earlier tests.
    if App.g_kSetManager.GetSet("bridge") is not None:
        App.g_kSetManager.DeleteSet("bridge")
    pSet = App.SetClass_Create()
    App.g_kSetManager.AddSet(pSet, "bridge")
    try:
        pSet.CreateAmbientLight(1.0, 1.0, 1.0, 0.7, "ambientlight1")
        ambient, directionals = _aggregate_bridge_lights()
        # 4th arg (dimmer) currently 0.7; expect 0.7-scaled white.
        assert ambient == pytest.approx((0.7, 0.7, 0.7))
        assert directionals == []
    finally:
        App.g_kSetManager.DeleteSet("bridge")
```

- [ ] **Step 2: Run; expect FAIL**

```bash
uv run pytest tests/host/test_host_loop_lighting.py::test_host_loop_pushes_bridge_lighting_each_tick -v
```

Expected: FAIL (`_aggregate_bridge_lights` doesn't exist).

- [ ] **Step 3: Add `_aggregate_bridge_lights` and the per-tick push**

Edit `engine/host_loop.py`. After the existing `_aggregate_lights` wrapper, add a parallel wrapper:

```python
def _aggregate_bridge_lights():
    """Wrapper over aggregate_bridge_for_renderer plugging in this
    module's DEFAULT_AMBIENT / DEFAULT_DIRECTIONALS as the no-bridge-set
    fallback. Mirrors _aggregate_lights's relationship with the space
    aggregator."""
    from engine.appc.lights import aggregate_bridge_for_renderer
    return aggregate_bridge_for_renderer(DEFAULT_AMBIENT, DEFAULT_DIRECTIONALS)
```

In the tick loop, find the existing line `r.set_lighting(ambient, directionals)` and add immediately below it:

```python
            bridge_ambient, bridge_directionals = _aggregate_bridge_lights()
            r.set_bridge_lighting(bridge_ambient, bridge_directionals)
```

- [ ] **Step 4: Run the new test and adjacent tests; expect PASS**

```bash
uv run pytest tests/host/test_host_loop_lighting.py -v
```

Expected: all PASS.

- [ ] **Step 5: Visual smoke test + 4th-arg decision**

```bash
./build/open_stbc
```

Enter bridge mode. Two scenarios are possible:

1. **Bridge ambient looks reasonable** (clean-lit, but not blown out). The `dimmer × color` interpretation works — leave `engine/appc/sets.py:CreateAmbientLight` as is. Document the choice with a comment.

2. **Bridge looks blown out** (everything near white, lightmap regions still visible but baseline is over-bright). The 4th arg (19.0 for MissionLib-bridge, 0.7 for LoadBridge) isn't pure dimmer. Two reasonable workarounds:
   - **Clamp**: change `engine/appc/sets.py:CreateAmbientLight` to `min(dimmer, 1.0)`.
   - **Ignore**: pass `dimmer=1.0` regardless of input.

Decide visually and apply the chosen change. If you change `CreateAmbientLight`, also update the docstring's current text:

```python
def CreateAmbientLight(self, r, g, b, dimmer, name):
    """SDK signature: pSet.CreateAmbientLight(r, g, b, range_or_dimmer, name).

    Stock bridge content passes 19.0 (MissionLib) or 0.7 (LoadBridge).
    Visual investigation (2026-05-15 bridge-lighting work): a literal
    `dimmer × color` interpretation makes 19.0 blow out the bridge
    interior; <DESCRIBE CHOSEN WORKAROUND HERE — clamp / ignore / etc.>.
    See docs/superpowers/specs/2026-05-15-bridge-lighting-materials-design.md.
    """
```

If clamping: replace `light = Light(... dimmer)` with `light = Light(... min(float(dimmer), 1.0))`.

If ignoring: replace with `light = Light(... 1.0)` and document why the arg is dropped.

If the test from Step 1 is now inconsistent with the new interpretation, update its expected ambient value to match. Re-run:

```bash
uv run pytest tests/host/test_host_loop_lighting.py -v
```

Expected: PASS.

- [ ] **Step 6: Run all engine/host tests; expect PASS**

```bash
uv run pytest tests/unit/test_appc_lights.py tests/host/test_host_loop_lighting.py -v
```

Expected: PASS.

- [ ] **Step 7: Visual confirmation — full bridge render**

```bash
./build/open_stbc
```

Verify:
1. Space view renders normally.
2. Entering bridge view shows a recognisably-lit bridge interior — base textures visible, lightmap regions distinguishable, no blown-out white, no all-black.
3. Exiting bridge view returns to a normal space view.

- [ ] **Step 8: Commit**

```bash
git add engine/host_loop.py engine/appc/sets.py tests/host/test_host_loop_lighting.py
git commit -m "feat(host_loop): push bridge-set lighting each tick

Adds _aggregate_bridge_lights() and a per-tick r.set_bridge_lighting()
call alongside the existing space-set lighting push. The bridge pass
now sees the bridge SetClass's authored ambient (CreateAmbientLight in
LoadBridge.py / MissionLib.py), not the space scene's defaults.

CreateAmbientLight 4th-arg interpretation: <PASTE CHOICE: kept as
dimmer / clamped at 1.0 / ignored>. <ONE-LINE RATIONALE FROM VISUAL
INSPECTION>."
```

---

## Task 12: Deferred-work doc updates

**Why:** Anchor the spec's deferred-work list in the runbook so future agents know what was intentionally left out.

**Files:**
- Modify: `native/src/host/docs/deferred_work.md`

- [ ] **Step 1: Append the new items**

Open `native/src/host/docs/deferred_work.md` and find the existing "Bridge & cinematic light rendering" follow-up under item 2. Update it in-place to mark it resolved (cross-reference the new spec and the chosen 4th-arg interpretation):

```markdown
   - **Bridge & cinematic light rendering.** ✅ Resolved 2026-05-15 by the
     [bridge-lighting-materials work](../../../../docs/superpowers/specs/2026-05-15-bridge-lighting-materials-design.md).
     BridgePass + bridge.{vert,frag} / lightmap.{vert,frag} ship the
     visual; `engine/appc/lights.py:aggregate_bridge_for_renderer`
     plumbs bridge-set ambient through `r.set_bridge_lighting`. The
     `CreateAmbientLight` 4th-arg semantics (range vs dimmer) were
     decided visually — see commit / `engine/appc/sets.py` for the
     chosen interpretation.
```

Add a new top-level item to the deferred list:

```markdown
N. **Strip the space pass when bridge view is active.** The space
   render path currently runs every frame even when the bridge pass is
   the only thing the user sees (see `host_bindings.cc::frame`, comment
   at lines 263-271). Deferred until the viewscreen-as-RTT work lands
   — that work needs the space pass running so it can target the
   viewscreen surface; stripping it now would force adding a "render
   space here" path that doesn't otherwise exist.
N+1. **Viewscreen-as-render-target.** Render the space scene into the
     `DbridgeViewScreen.NIF` surface so the bridge's main screen shows
     a live view of the outside world. Pulls in framebuffer / render-
     target plumbing.
N+2. **Animated bridge state.** Red-alert tint, viewscreen flicker,
     station-screen content.
N+3. **Per-ship-class bridge variants.** DBridge is hardcoded in
     `host_loop.py:502`; other classes have their own bridge NIFs.
N+4. **Bridge characters / skinned animation.** Crew at stations.
N+5. **Specular / glow on bridge geometry.** Not authored in stock
     content; relevant if mods add it.
N+6. **Per-LCARS-panel alpha-test threshold tuning.** Currently 0.5
     hardcoded in `bridge.frag`. Surface as a per-material override if
     specific panels need tuning.
N+7. **NIF `Dark`-stage lightmap support.** Modern authoring tools can
     put a lightmap in stage 1 (`Dark`) of `NiMultiTextureProperty`;
     stock BC content doesn't use this path, but adding a second
     predicate would extend `lightmap_pass` tagging to non-stock
     bridges.
N+8. **`CreateAmbientLight` 4th-arg true semantics.** The chosen
     interpretation matches visual expectations for stock content; the
     ground truth (range vs dimmer vs something else) is still
     unconfirmed and may matter for non-stock content.
```

Replace `N` with the next sequential number from the existing list. Check `native/src/host/docs/deferred_work.md` for the current highest number first.

- [ ] **Step 2: Commit**

```bash
git add native/src/host/docs/deferred_work.md
git commit -m "docs(deferred): bridge lighting & materials follow-ups

Marks the longstanding 'Bridge & cinematic light rendering' item
resolved. Adds eight new entries from the bridge-lighting design's
deferred-work section — most notably the viewscreen-as-RTT path that
will reclaim the space-pass-in-bridge-mode overdraw."
```

---

## Self-review checklist

After execution, the operator should confirm:

1. **Spec coverage.** Six in-scope items from the spec all land in tasks above:
   - Property-link inheritance → Task 3.
   - Lightmap tagging → Task 4.
   - Bridge-set lighting aggregation → Task 9 + 11.
   - `CreateAmbientLight` 4th-arg interpretation → Task 11 Step 5.
   - Bridge + lightmap shaders → Task 5.
   - `BridgePass` two sub-passes → Tasks 6, 7, 8.
2. **All five risks have a concrete mitigation step:**
   - Ship regression → Task 2 fixture + Task 3 Step 5.
   - Z-fighting → Task 7 GL state choice + Task 8 Step 5 visual smoke.
   - 4th-arg interpretation → Task 11 Step 5 visual decision.
   - Texture-path resolution → covered by Task 4 Step 9 DBridge integration test (passes only if path resolution actually works).
   - LCARS alpha channel → covered by Task 8 Step 5 visual smoke (operator can drop alpha-test from `bridge.frag` if LCARS panels render with wrong cutouts).
3. **No placeholder text** in any task's code blocks; concrete file paths and full code throughout.
