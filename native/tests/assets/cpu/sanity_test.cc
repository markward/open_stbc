#include <gtest/gtest.h>
#include <assets/asset.h>

TEST(AssetsSanity, ForwardDeclsCompile) {
    assets::ModelHandle h;
    EXPECT_FALSE(static_cast<bool>(h));
}
