// Internal-header include path is added via target_include_directories
// pointing at native/src/assets/src.
#include <gtest/gtest.h>
#include "mesh_build.h"

TEST(MeshBuild, MinimalTriangle) {
    nif::NiTriShape shape;
    nif::NiTriShapeData data;
    data.num_vertices = 3;
    data.has_vertices = true;
    data.vertices = {{0.0f, 0.0f, 0.0f}, {1.0f, 0.0f, 0.0f}, {0.0f, 1.0f, 0.0f}};
    data.has_normals = true;
    data.normals = {{0, 0, 1}, {0, 0, 1}, {0, 0, 1}};
    data.has_uv = true;
    data.uv_sets.push_back({{0.0f, 0.0f}, {1.0f, 0.0f}, {0.0f, 1.0f}});
    data.num_triangles = 1;
    data.num_triangle_points = 3;
    data.triangles.push_back({0, 1, 2});

    auto mesh = assets::detail::build_mesh_cpu(shape, data, /*mat=*/0, /*node=*/2);
    EXPECT_EQ(mesh.vertices.size(), 3u);
    EXPECT_EQ(mesh.indices.size(), 3u);
    EXPECT_EQ(mesh.indices[0], 0u);
    EXPECT_EQ(mesh.indices[1], 1u);
    EXPECT_EQ(mesh.indices[2], 2u);
    EXPECT_EQ(mesh.material_index, 0);
    EXPECT_EQ(mesh.node_index, 2);
    EXPECT_FLOAT_EQ(mesh.vertices[1].position.x, 1.0f);
    EXPECT_EQ(mesh.vertices[0].color, glm::u8vec4(255, 255, 255, 255));
}

TEST(MeshBuild, VertexColorsAreCopied) {
    nif::NiTriShape shape;
    nif::NiTriShapeData data;
    data.num_vertices = 1;
    data.has_vertices = true;
    data.vertices = {{0, 0, 0}};
    data.has_vertex_colors = true;
    data.vertex_colors = {{0.5f, 0.25f, 1.0f, 0.75f}};
    data.has_uv = true;
    data.uv_sets.push_back({{0.0f, 0.0f}});

    auto mesh = assets::detail::build_mesh_cpu(shape, data, -1, -1);
    EXPECT_EQ(mesh.vertices[0].color.r, static_cast<std::uint8_t>(0.5f * 255 + 0.5f));
    EXPECT_EQ(mesh.vertices[0].color.a, static_cast<std::uint8_t>(0.75f * 255 + 0.5f));
}

TEST(MeshBuild, ExtraUvSetsArePreserved) {
    nif::NiTriShape shape;
    nif::NiTriShapeData data;
    data.num_vertices = 1;
    data.has_vertices = true;
    data.vertices = {{0, 0, 0}};
    data.has_uv = true;
    data.uv_sets.push_back({{0.1f, 0.2f}});  // primary
    data.uv_sets.push_back({{0.3f, 0.4f}});  // extra (detail map)

    auto mesh = assets::detail::build_mesh_cpu(shape, data, -1, -1);
    EXPECT_FLOAT_EQ(mesh.vertices[0].uv.x, 0.1f);
    ASSERT_EQ(mesh.extra_uvs.size(), 1u);
    EXPECT_FLOAT_EQ(mesh.extra_uvs[0][0].x, 0.3f);
}

TEST(MeshBuild, NoUvWhenAbsent) {
    nif::NiTriShape shape;
    nif::NiTriShapeData data;
    data.num_vertices = 2;
    data.has_vertices = true;
    data.vertices = {{0, 0, 0}, {1, 0, 0}};
    data.has_uv = false;

    auto mesh = assets::detail::build_mesh_cpu(shape, data, -1, -1);
    EXPECT_FLOAT_EQ(mesh.vertices[0].uv.x, 0.0f);
    EXPECT_FLOAT_EQ(mesh.vertices[0].uv.y, 0.0f);
    EXPECT_TRUE(mesh.extra_uvs.empty());
}
