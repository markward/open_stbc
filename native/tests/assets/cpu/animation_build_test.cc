#include <gtest/gtest.h>
#include "animation_build.h"

#include <nif/block.h>

namespace {

nif::File build_synthetic_keyframed_file() {
    nif::File f;
    // Block 0: NiNode "Saucer" — controller target
    nif::NiNode node;
    node.av.obj.name = "Saucer";
    node.av.obj.controller_link = 1;
    f.blocks.push_back(node);

    // Block 1: NiKeyframeController, data_link → block 2
    nif::NiKeyframeController kc;
    kc.start_time = 0.0f;
    kc.stop_time  = 2.0f;
    kc.data_link  = 2;
    f.blocks.push_back(kc);

    // Block 2: NiKeyframeData with two translation keys
    nif::NiKeyframeData kd;
    kd.translations.num_keys = 2;
    kd.translations.interpolation = 1;  // linear
    nif::NiKeyframeData::Vec3KeyArray::K k0;
    k0.time = 0.0f;
    k0.value = nif::Vec3{0, 0, 0};
    nif::NiKeyframeData::Vec3KeyArray::K k1;
    k1.time = 2.0f;
    k1.value = nif::Vec3{10, 0, 0};
    kd.translations.keys = {k0, k1};
    f.blocks.push_back(kd);
    return f;
}

}  // namespace

TEST(AnimationBuild, NoControllersProducesEmptyList) {
    nif::File f;
    auto anims = assets::detail::build_animations(f);
    EXPECT_TRUE(anims.empty());
}

TEST(AnimationBuild, KeyframeControllerProducesClip) {
    auto f = build_synthetic_keyframed_file();
    auto anims = assets::detail::build_animations(f);
    ASSERT_EQ(anims.size(), 1u);
    EXPECT_FLOAT_EQ(anims[0].duration_seconds, 2.0f);
    ASSERT_EQ(anims[0].tracks.size(), 1u);
    auto& track = anims[0].tracks[0];
    EXPECT_EQ(track.target_node_name, "Saucer");
    ASSERT_EQ(track.translation.size(), 2u);
    EXPECT_FLOAT_EQ(track.translation[0].time, 0.0f);
    EXPECT_FLOAT_EQ(track.translation[1].value.x, 10.0f);
}

TEST(AnimationBuild, VisControllerProducesVisibilityTrack) {
    nif::File f;
    nif::NiNode node;
    node.av.obj.name = "Hatch";
    node.av.obj.controller_link = 1;
    f.blocks.push_back(node);

    nif::NiVisController vc;
    vc.data_link = 2;
    f.blocks.push_back(vc);

    nif::NiVisData vd;
    vd.num_keys = 2;
    vd.keys = {{0.0f, 1}, {1.5f, 0}};
    f.blocks.push_back(vd);

    auto anims = assets::detail::build_animations(f);
    ASSERT_EQ(anims.size(), 1u);
    ASSERT_EQ(anims[0].tracks.size(), 1u);
    auto& track = anims[0].tracks[0];
    ASSERT_EQ(track.visibility.size(), 2u);
    EXPECT_TRUE(track.visibility[0].value);
    EXPECT_FALSE(track.visibility[1].value);
    EXPECT_FLOAT_EQ(anims[0].duration_seconds, 1.5f);
}
