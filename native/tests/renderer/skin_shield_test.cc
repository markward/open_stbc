#include <gtest/gtest.h>
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
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

// ── build_skin_shield_meshcpu: concatenate model meshes + inflate ──

#include <assets/model.h>

namespace {
// Synthesize a minimal Model with two triangle meshes. Mesh::set_cpu_data
// stashes the MeshCpu without touching GL, so this works in a pure-CPU
// test without a render context.
assets::Model make_two_tri_model() {
    assets::Model model;
    model.nodes.push_back(assets::Node{
        .name = "root", .parent_index = -1,
        .local_transform = glm::mat4(1.0f),
        .children = {}, .meshes = {0, 1},
    });

    auto make_tri = [](glm::vec3 origin, glm::vec3 normal) {
        assets::MeshCpu cpu;
        cpu.vertices.push_back({.position = origin,                .normal = normal});
        cpu.vertices.push_back({.position = origin + glm::vec3(1, 0, 0), .normal = normal});
        cpu.vertices.push_back({.position = origin + glm::vec3(0, 1, 0), .normal = normal});
        cpu.indices = {0, 1, 2};
        return cpu;
    };

    assets::Mesh m1, m2;
    m1.set_cpu_data(make_tri({0, 0, 0}, {0, 0, 1}));
    m2.set_cpu_data(make_tri({10, 0, 0}, {1, 0, 0}));
    model.meshes.push_back(std::move(m1));
    model.meshes.push_back(std::move(m2));
    return model;
}
}  // namespace

TEST(SkinShieldMeshCpu, ConcatenatesAllMeshesWithIndexOffset) {
    auto model = make_two_tri_model();
    auto cpu = renderer::build_skin_shield_meshcpu(model, /*inflate=*/0.0f);
    EXPECT_EQ(cpu.vertices.size(), 6u);    // 3 + 3
    EXPECT_EQ(cpu.indices.size(), 6u);     // 3 + 3
    // Second mesh's indices must be offset by 3 (first mesh's vertex count).
    EXPECT_EQ(cpu.indices[0], 0u);
    EXPECT_EQ(cpu.indices[1], 1u);
    EXPECT_EQ(cpu.indices[2], 2u);
    EXPECT_EQ(cpu.indices[3], 3u);
    EXPECT_EQ(cpu.indices[4], 4u);
    EXPECT_EQ(cpu.indices[5], 5u);
}

TEST(SkinShieldMeshCpu, InflatesPositionsAlongNormals) {
    auto model = make_two_tri_model();
    auto cpu = renderer::build_skin_shield_meshcpu(model, /*inflate=*/0.5f);
    // Mesh 0: normal (0,0,1) → z += 0.5.
    EXPECT_FLOAT_EQ(cpu.vertices[0].position.z, 0.5f);
    // Mesh 1: normal (1,0,0) → x += 0.5, origin x=10 → x=10.5.
    EXPECT_FLOAT_EQ(cpu.vertices[3].position.x, 10.5f);
}

TEST(SkinShieldMeshCpu, AppliesNodeHierarchyTransformsToPositionAndNormal) {
    // Mirror the opaque-pass behaviour (frame.cc draw_model): each mesh is
    // drawn at world_per_node[i] = chained local_transform from root. Skin
    // shield must match — otherwise the shell drifts off the hull on any
    // ship whose submeshes live under translated/rotated child nodes.
    assets::Model model;
    model.nodes.push_back(assets::Node{
        .name = "root", .parent_index = -1,
        .local_transform = glm::mat4(1.0f),
        .children = {1}, .meshes = {},
    });
    glm::mat4 child_xform = glm::translate(glm::mat4(1.0f), glm::vec3(10, 0, 0));
    model.nodes.push_back(assets::Node{
        .name = "child", .parent_index = 0,
        .local_transform = child_xform,
        .children = {}, .meshes = {0},
    });

    assets::MeshCpu cpu;
    // Single vertex at local origin with normal +X. After the child node's
    // translation it should sit at (10, 0, 0); with inflate 0.5 along the
    // (still +X) normal it should land at (10.5, 0, 0).
    cpu.vertices.push_back({.position = {0, 0, 0}, .normal = {1, 0, 0}});
    cpu.indices = {0, 0, 0};
    assets::Mesh m;
    m.set_cpu_data(std::move(cpu));
    model.meshes.push_back(std::move(m));

    auto out = renderer::build_skin_shield_meshcpu(model, /*inflate=*/0.5f);
    ASSERT_EQ(out.vertices.size(), 1u);
    EXPECT_FLOAT_EQ(out.vertices[0].position.x, 10.5f);
    EXPECT_FLOAT_EQ(out.vertices[0].position.y, 0.0f);
    EXPECT_FLOAT_EQ(out.vertices[0].position.z, 0.0f);
    EXPECT_FLOAT_EQ(out.vertices[0].normal.x, 1.0f);
    EXPECT_FLOAT_EQ(out.vertices[0].normal.y, 0.0f);
    EXPECT_FLOAT_EQ(out.vertices[0].normal.z, 0.0f);
}

TEST(SkinShieldMeshCpu, SkipsMeshesWithoutCpuData) {
    assets::Model model;
    model.nodes.push_back(assets::Node{
        .name = "root", .parent_index = -1, .meshes = {0},
    });
    model.meshes.emplace_back();  // GL-only mesh: cpu_data is nullopt
    auto cpu = renderer::build_skin_shield_meshcpu(model, 0.0f);
    EXPECT_EQ(cpu.vertices.size(), 0u);
    EXPECT_EQ(cpu.indices.size(), 0u);
}
