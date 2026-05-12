#include <gtest/gtest.h>
#include <glm/glm.hpp>
#include "renderer/skin_shield.h"

using namespace renderer;

TEST(SkinShield, InflatesPositionsAlongNormalsByDistance) {
    std::vector<glm::vec3> positions = {
        {0, 0, 0},
        {1, 0, 0},
        {0, 1, 0},
    };
    std::vector<glm::vec3> normals = {
        {0, 0, 1},
        {1, 0, 0},
        {0, 1, 0},
    };
    auto inflated = build_skin_shield_positions(positions, normals, /*distance=*/0.5f);
    ASSERT_EQ(inflated.size(), 3u);
    EXPECT_EQ(inflated[0], glm::vec3(0,    0,    0.5f));
    EXPECT_EQ(inflated[1], glm::vec3(1.5f, 0,    0));
    EXPECT_EQ(inflated[2], glm::vec3(0,    1.5f, 0));
}

TEST(SkinShield, NormalsShorterThanPositionsThrows) {
    std::vector<glm::vec3> positions = {{0, 0, 0}, {1, 0, 0}};
    std::vector<glm::vec3> normals   = {{0, 0, 1}};
    EXPECT_THROW(build_skin_shield_positions(positions, normals, 0.5f),
                 std::invalid_argument);
}

TEST(SkinShield, ZeroDistanceReturnsPositionsUnchanged) {
    std::vector<glm::vec3> positions = {{1, 2, 3}, {4, 5, 6}};
    std::vector<glm::vec3> normals   = {{0, 0, 1}, {1, 0, 0}};
    auto out = build_skin_shield_positions(positions, normals, 0.0f);
    EXPECT_EQ(out[0], positions[0]);
    EXPECT_EQ(out[1], positions[1]);
}
