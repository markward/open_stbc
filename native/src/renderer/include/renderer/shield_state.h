// native/src/renderer/include/renderer/shield_state.h
#pragma once

#include <array>
#include <cstdint>
#include <cstddef>
#include <glm/glm.hpp>

namespace renderer {

enum class ShieldMode : std::uint8_t { Ellipsoid = 0, Skin = 1 };

struct Hit {
    glm::vec3 point_world{0.0f};
    glm::vec4 color_rgba{0.0f};
    float intensity_at_t0 = 0.0f;
    float current_intensity = 0.0f;
    double t0_seconds = 0.0;
    int texture_index = 0;
};

class ShieldState {
public:
    static constexpr std::size_t MaxHits = 8;

    ShieldMode mode = ShieldMode::Ellipsoid;
    float decay_seconds = 1.0f;
    glm::vec4 default_color{1.0f};
    glm::vec3 aabb_center{0.0f};
    glm::vec3 aabb_half_extents{0.0f};

    /// Store a new hit. Picks the first empty slot, falling back to the
    /// dimmest slot when full. If `rgba` is all-zero, substitutes
    /// `default_color`. `intensity` is preserved as `intensity_at_t0` and
    /// also seeds `current_intensity` so the slot is immediately active.
    void push_hit(const glm::vec3& point_world,
                  const glm::vec4& rgba,
                  float intensity,
                  double now_seconds,
                  int texture_index);

    /// Recompute current_intensity for every slot at `now_seconds`.
    /// Slots that fall below the inactive threshold (0.01) are zeroed.
    void tick(double now_seconds);

    std::size_t active_count() const noexcept;
    const Hit& slot(std::size_t i) const noexcept { return hits_[i]; }

private:
    std::array<Hit, MaxHits> hits_{};
};

}  // namespace renderer
