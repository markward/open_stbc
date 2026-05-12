#include <gtest/gtest.h>
#include <assets/cache.h>
#include <assets/material.h>
#include <glad/glad.h>

#include "gl_fixture.h"

#include <filesystem>

namespace fs = std::filesystem;

class ModelSmokeTest : public assets_test::GLContext {};

TEST_F(ModelSmokeTest, LoadsGalaxyEndToEnd) {
    fs::path root = OPEN_STBC_PROJECT_ROOT;
    fs::path galaxy   = root / "game/data/Models/Ships/Galaxy/Galaxy.nif";
    fs::path fed_high = root / "game/data/Models/SharedTextures/FedShips/High";
    if (!fs::exists(galaxy) || !fs::exists(fed_high))
        GTEST_SKIP() << "game/ not installed";

    assets::AssetCache cache;  // default config: real GL uploaders
    auto model = cache.load(galaxy, fed_high);

    ASSERT_NE(model, nullptr);
    EXPECT_GT(model->meshes.size(), 0u);
    EXPECT_GT(model->materials.size(), 0u);
    EXPECT_GT(model->textures.size(), 0u);
    EXPECT_FALSE(model->nodes.empty());
    EXPECT_EQ(glGetError(), static_cast<GLenum>(GL_NO_ERROR));

    for (auto& tex : model->textures) {
        EXPECT_NE(tex.id(), 0u);
        EXPECT_TRUE(glIsTexture(tex.id()));
    }
    for (auto& m : model->meshes) {
        EXPECT_NE(m.vao(), 0u);
        EXPECT_TRUE(glIsVertexArray(m.vao()));
    }

    // At least one material's Base stage must reference a real texture.
    // Pre-2026-05-09 a link-ID-vs-block-index mismatch in load_all_textures
    // caused every material to come back with texture_index == -1, so the
    // renderer rendered all BC ships untextured (white-fallback). The
    // earlier assertions above all passed under that bug because they
    // didn't check materials → textures linkage.
    int materials_with_base_texture = 0;
    for (auto& mat : model->materials) {
        const auto& base =
            mat.stages[static_cast<std::size_t>(assets::Material::StageSlot::Base)];
        if (base.texture_index >= 0 &&
            base.texture_index < static_cast<int>(model->textures.size())) {
            ++materials_with_base_texture;
        }
    }
    EXPECT_GT(materials_with_base_texture, 0)
        << "no material on the Galaxy resolves a Base-stage texture; "
           "load_all_textures' map keys are likely out of sync with the NiImage link IDs";
}
