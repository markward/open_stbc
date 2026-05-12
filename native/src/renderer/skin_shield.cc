// native/src/renderer/skin_shield.cc
#include "renderer/skin_shield.h"

#include <stdexcept>

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

}  // namespace renderer
