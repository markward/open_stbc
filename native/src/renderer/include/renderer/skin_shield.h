// native/src/renderer/include/renderer/skin_shield.h
#pragma once

#include <span>
#include <vector>
#include <stdexcept>
#include <glm/glm.hpp>

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

}  // namespace renderer
