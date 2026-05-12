// native/src/renderer/include/renderer/skin_shield.h
#pragma once

#include <span>
#include <vector>
#include <stdexcept>
#include <glm/glm.hpp>

namespace assets { struct Model; struct MeshCpu; }

namespace renderer {

/// Push hull positions outward along their normals by `distance`. Topology
/// (the index buffer) is unchanged — the caller reuses the hull's indices
/// for the resulting "skin" shield mesh. Throws std::invalid_argument if
/// `normals.size() < positions.size()`.
std::vector<glm::vec3> build_skin_shield_positions(
    std::span<const glm::vec3> positions,
    std::span<const glm::vec3> normals,
    float distance);

inline std::vector<glm::vec3> build_skin_shield_positions(
    const std::vector<glm::vec3>& positions,
    const std::vector<glm::vec3>& normals,
    float distance) {
    return build_skin_shield_positions(
        std::span<const glm::vec3>(positions),
        std::span<const glm::vec3>(normals),
        distance);
}

/// Build a single CPU-side mesh that concatenates every node's referenced
/// meshes in `model`, pushing each vertex outward along its (transformed)
/// normal by `inflate_distance`. The node hierarchy is walked the same way
/// the opaque pass walks it (see renderer::draw_model), so vertices land in
/// ship-local coordinates that match the visible silhouette. Index buffers
/// are concatenated with an offset so the resulting mesh draws the union of
/// every triangle. Meshes lacking cpu_data, or not referenced by any node,
/// are skipped silently.
assets::MeshCpu build_skin_shield_meshcpu(const assets::Model& model,
                                          float inflate_distance);

}  // namespace renderer
