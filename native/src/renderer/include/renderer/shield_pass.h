// native/src/renderer/include/renderer/shield_pass.h
#pragma once

#include <memory>

#include <assets/mesh.h>
#include <assets/texture.h>

#include "renderer/shield_state.h"

namespace scenegraph { class World; struct Camera; }
namespace renderer { class Pipeline; }

namespace renderer {

/// Per-frame additive shield-flash pass. Owns the per-instance
/// ShieldRegistry, a shared ellipsoid sphere mesh, and the four
/// shieldhit0N textures. Skin-mesh path lands in Tasks 14-15.
class ShieldPass {
public:
    ShieldPass();
    ~ShieldPass();
    ShieldPass(const ShieldPass&) = delete;
    ShieldPass& operator=(const ShieldPass&) = delete;

    void register_ship(scenegraph::InstanceId id,
                       ShieldMode mode,
                       float decay_seconds,
                       const glm::vec4& default_color,
                       const glm::vec3& aabb_center,
                       const glm::vec3& aabb_half_extents);

    void unregister_ship(scenegraph::InstanceId id);

    /// Push a hit. Color (0,0,0,0) substitutes the ship's default color.
    void shield_hit(scenegraph::InstanceId id,
                    const glm::vec3& point_world,
                    const glm::vec4& rgba,
                    float intensity,
                    double now_seconds);

    /// Draw all ships with active hits. Caller owns blend/depth state.
    /// `now_seconds` advances the decay clock.
    void submit(const scenegraph::World& world,
                const scenegraph::Camera& camera,
                Pipeline& pipeline,
                double now_seconds);

private:
    ShieldRegistry registry_;
    std::unique_ptr<assets::Mesh> sphere_;        // shared ellipsoid mesh
    std::unique_ptr<assets::Texture> tex_[4];     // shieldhit01..04.TGA
    bool tex_loaded_ = false;

    assets::Mesh* ensure_sphere();
    void ensure_textures_loaded();
};

}  // namespace renderer
