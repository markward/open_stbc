// native/src/renderer/skin_shield.cc
#include "renderer/skin_shield.h"

#include <stdexcept>

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
    std::uint32_t index_offset = 0;
    for (const auto& mesh : model.meshes) {
        const auto& cpu = mesh.cpu_data();
        if (!cpu) continue;
        out.vertices.reserve(out.vertices.size() + cpu->vertices.size());
        for (const auto& v : cpu->vertices) {
            assets::MeshCpu::Vertex inflated = v;
            inflated.position = v.position + v.normal * inflate_distance;
            out.vertices.push_back(inflated);
        }
        out.indices.reserve(out.indices.size() + cpu->indices.size());
        for (auto idx : cpu->indices) {
            out.indices.push_back(idx + index_offset);
        }
        index_offset += static_cast<std::uint32_t>(cpu->vertices.size());
    }
    return out;
}

}  // namespace renderer
