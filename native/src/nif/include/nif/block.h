// native/src/nif/include/nif/block.h
#pragma once

#include <nif/types.h>

#include <cstdint>
#include <string>
#include <variant>
#include <vector>

namespace nif {

/// Generic node object — the primary scene-graph spine.
/// Field layout per v3.1; verified against Galaxy.nif's root node.
/// References are stored as raw v3.x link IDs (uint32); the resolver maps
/// them to BlockHandle later.
struct NiNode {
    std::string name;
    std::uint32_t extra_data_link = 0;   // 0 = no extra data
    std::uint32_t controller_link = 0;   // 0 = no controller
    std::uint16_t flags = 0;
    Vec3 translation{};
    Mat3x3 rotation{ .m = {1, 0, 0, 0, 1, 0, 0, 0, 1} };  // identity default
    float scale = 1.0f;
    Vec3 velocity{};
    std::vector<std::uint32_t> property_links;
    bool has_bounding_volume = false;
    // bounding_volume struct deferred until a sample file exercises it
    std::vector<std::uint32_t> child_links;
    std::vector<std::uint32_t> effect_links;
};

using Block = std::variant<std::monostate, NiNode>;

struct BlockHandle {
    const Block* ptr = nullptr;
    explicit operator bool() const { return ptr != nullptr; }
    const Block& operator*() const { return *ptr; }
    const Block* operator->() const { return ptr; }
};

}  // namespace nif
