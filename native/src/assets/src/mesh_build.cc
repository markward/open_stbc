#include "mesh_build.h"

#include <algorithm>

namespace assets::detail {

namespace {

inline std::uint8_t to_u8(float f) {
    f = std::clamp(f, 0.0f, 1.0f);
    return static_cast<std::uint8_t>(f * 255.0f + 0.5f);
}

}  // namespace

// NOTE: shape parameter is currently unused, but NiTriShape carries an
// `av` block with a local translation/rotation/scale that, per the NIF
// transform model, composes as parent_world * (T * R * S) on top of the
// parent NiNode's world transform. For every BC ship NIF we've inspected
// so far (Galaxy, Sovereign, etc.) the per-shape transform is identity,
// so ignoring it produces correct results today. If a ship ever renders
// displaced from its parent node, this is the first place to look — bake
// the shape transform into the vertex positions or hand it through to
// the renderer's per-mesh matrix.
MeshCpu build_mesh_cpu(
    const nif::NiTriShape& /*shape*/,
    const nif::NiTriShapeData& data,
    int material_index,
    int node_index)
{
    MeshCpu mesh;
    mesh.material_index = material_index;
    mesh.node_index     = node_index;

    mesh.vertices.resize(data.num_vertices);

    if (data.has_vertices) {
        for (std::size_t i = 0; i < data.vertices.size(); ++i) {
            const auto& v = data.vertices[i];
            mesh.vertices[i].position = {v.x, v.y, v.z};
        }
    }
    if (data.has_normals) {
        for (std::size_t i = 0; i < data.normals.size(); ++i) {
            const auto& n = data.normals[i];
            mesh.vertices[i].normal = {n.x, n.y, n.z};
        }
    }
    if (data.has_uv && !data.uv_sets.empty()) {
        const auto& primary = data.uv_sets[0];
        for (std::size_t i = 0; i < primary.size(); ++i) {
            mesh.vertices[i].uv = {primary[i].u, primary[i].v};
        }
        for (std::size_t set = 1; set < data.uv_sets.size(); ++set) {
            std::vector<glm::vec2> extra;
            extra.reserve(data.uv_sets[set].size());
            for (auto& tc : data.uv_sets[set]) extra.push_back({tc.u, tc.v});
            mesh.extra_uvs.push_back(std::move(extra));
        }
    }
    if (data.has_vertex_colors) {
        for (std::size_t i = 0; i < data.vertex_colors.size(); ++i) {
            const auto& c = data.vertex_colors[i];
            mesh.vertices[i].color = glm::u8vec4(
                to_u8(c.r), to_u8(c.g), to_u8(c.b), to_u8(c.a));
        }
    }

    mesh.indices.reserve(data.triangles.size() * 3);
    for (auto& tri : data.triangles) {
        mesh.indices.push_back(tri[0]);
        mesh.indices.push_back(tri[1]);
        mesh.indices.push_back(tri[2]);
    }
    return mesh;
}

}  // namespace assets::detail
