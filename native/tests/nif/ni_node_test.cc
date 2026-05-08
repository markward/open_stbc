// native/tests/nif/ni_node_test.cc — exercises the NiNode parser against
// the real BC sample files.
#include <gtest/gtest.h>

#include <nif/block.h>
#include <nif/file.h>

#include <filesystem>
#include <variant>

namespace {

const nif::NiNode* find_first_ninode(const nif::File& f) {
    for (const auto& b : f.blocks) {
        if (auto* n = std::get_if<nif::NiNode>(&b)) return n;
    }
    return nullptr;
}

}  // namespace

TEST(NiNodeParser, GalaxyRootNiNodeParses) {
    auto path = std::filesystem::path(OPEN_STBC_PROJECT_ROOT)
                / "game/data/Models/Ships/Galaxy/Galaxy.nif";
    if (!std::filesystem::exists(path)) GTEST_SKIP() << path;
    auto f = nif::load(path);
    ASSERT_FALSE(f.blocks.empty()) << "Walker stopped before parsing any blocks";
    auto* root = find_first_ninode(f);
    ASSERT_NE(root, nullptr) << "First block should be a NiNode";

    // Galaxy's root is a default-transform node with identity rotation.
    EXPECT_FLOAT_EQ(root->translation.x, 0.0f);
    EXPECT_FLOAT_EQ(root->translation.y, 0.0f);
    EXPECT_FLOAT_EQ(root->translation.z, 0.0f);
    EXPECT_FLOAT_EQ(root->scale, 1.0f);
    EXPECT_FLOAT_EQ(root->rotation.m[0], 1.0f);
    EXPECT_FLOAT_EQ(root->rotation.m[4], 1.0f);
    EXPECT_FLOAT_EQ(root->rotation.m[8], 1.0f);
    EXPECT_FALSE(root->has_bounding_volume);

    // Root has at least one property and one child (ZBufferProperty + child NiNode).
    EXPECT_GE(root->property_links.size(), 1u);
    EXPECT_GE(root->child_links.size(), 1u);
}

TEST(NiNodeParser, GalaxyParsesAtLeastOneBlock) {
    auto path = std::filesystem::path(OPEN_STBC_PROJECT_ROOT)
                / "game/data/Models/Ships/Galaxy/Galaxy.nif";
    if (!std::filesystem::exists(path)) GTEST_SKIP() << path;
    auto f = nif::load(path);
    EXPECT_GE(f.blocks.size(), 1u);
    // Walker should have stopped on the first non-NiNode type
    // (NiZBufferProperty per inventory). We don't know yet which blocks
    // beyond NiNode parse; eof_reached should still be false.
    EXPECT_FALSE(f.eof_reached);
}
