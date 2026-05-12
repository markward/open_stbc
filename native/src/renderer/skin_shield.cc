// native/src/renderer/skin_shield.cc
#include "renderer/skin_shield.h"

#include <stdexcept>

#include <glm/gtc/matrix_transform.hpp>

#include <assets/mesh.h>
#include <assets/model.h>

namespace renderer {

std::vector<glm::vec3> build_skin_shield_positions(
    std::span<const glm::vec3> positions,
    std::span<const glm::vec3> normals,
    float distance) {
    if (normals.size() < positions.size()) {
        throw std::invalid_argument(
            "build_skin_shield_positions: normals.size() < positions.size()");
    }
    std::vector<glm::vec3> out;
    out.reserve(positions.size());
    for (std::size_t i = 0; i < positions.size(); ++i) {
        out.push_back(positions[i] + normals[i] * distance);
    }
    return out;
}

assets::MeshCpu build_skin_shield_meshcpu(const assets::Model& model,
                                          float inflate_distance) {
    assets::MeshCpu out;
    if (model.nodes.empty()) return out;

    // Chain local_transform from root down — same walk as
    // renderer::compute_model_aabb and renderer::draw_model. The asset
    // pipeline orders nodes parent-before-child, so a single linear pass
    // produces correct world-per-node matrices.
    std::vector<glm::mat4> node_world(model.nodes.size(), glm::mat4(1.0f));
    node_world[model.root_node] = model.nodes[model.root_node].local_transform;
    for (std::size_t i = 0; i < model.nodes.size(); ++i) {
        const auto& node = model.nodes[i];
        if (node.parent_index >= 0) {
            node_world[i] = node_world[node.parent_index] * node.local_transform;
        }
    }

    std::uint32_t index_offset = 0;
    for (std::size_t i = 0; i < model.nodes.size(); ++i) {
        const auto& node = model.nodes[i];
        const glm::mat4& xform = node_world[i];
        const glm::mat3 normal_basis(xform);  // BC NIFs use uniform scale.
        for (int mesh_idx : node.meshes) {
            if (mesh_idx < 0 ||
                mesh_idx >= static_cast<int>(model.meshes.size())) continue;
            const auto& cpu = model.meshes[mesh_idx].cpu_data();
            if (!cpu) continue;
            out.vertices.reserve(out.vertices.size() + cpu->vertices.size());
            for (const auto& v : cpu->vertices) {
                assets::MeshCpu::Vertex transformed = v;
                const glm::vec3 pos_ws =
                    glm::vec3(xform * glm::vec4(v.position, 1.0f));
                const glm::vec3 n_ws = glm::normalize(normal_basis * v.normal);
                transformed.position = pos_ws + n_ws * inflate_distance;
                transformed.normal = n_ws;
                out.vertices.push_back(transformed);
            }
            out.indices.reserve(out.indices.size() + cpu->indices.size());
            for (auto idx : cpu->indices) {
                out.indices.push_back(idx + index_offset);
            }
            index_offset += static_cast<std::uint32_t>(cpu->vertices.size());
        }
    }
    return out;
}

}  // namespace renderer
