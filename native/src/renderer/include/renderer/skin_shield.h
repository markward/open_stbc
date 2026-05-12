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

/// Build a single CPU-side mesh that concatenates all CPU-data meshes in
/// `model`, pushing each vertex outward along its normal by `inflate_distance`.
/// Index buffers are concatenated with an offset so the resulting mesh draws
/// the union of every triangle. Meshes lacking cpu_data are skipped silently.
///
/// Node transforms are NOT applied — BC ship NIFs have flat-enough hierarchies
/// that the union of NiTriShape-local positions tracks the visible silhouette
/// closely. Refine if a multi-armed ship surfaces visible misalignment.
assets::MeshCpu build_skin_shield_meshcpu(const assets::Model& model,
                                          float inflate_distance);

}  // namespace renderer
