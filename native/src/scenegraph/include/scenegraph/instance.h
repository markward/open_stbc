// native/src/scenegraph/include/scenegraph/instance.h
#pragma once

#include <cstdint>
#include <glm/glm.hpp>

namespace scenegraph {

using ModelHandle = std::uint64_t;  // Opaque key into the asset cache.

struct InstanceId {
    std::uint32_t index = 0;
    std::uint32_t generation = 0;
    bool operator==(const InstanceId&) const = default;
};

/// Which renderer pass an instance is drawn in.
/// - Space: ships, planets, suns, dust, backdrops (default).
/// - Bridge: the bridge interior geometry, drawn after a depth clear.
enum class Pass : std::uint8_t { Space = 0, Bridge = 1 };

struct Instance {
    ModelHandle model_handle = 0;
    glm::mat4 world{1.0f};
    bool visible = true;
    Pass pass = Pass::Space;
};

}  // namespace scenegraph
