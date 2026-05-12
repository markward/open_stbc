// native/src/renderer/shield_pass.cc
#include "renderer/shield_pass.h"

#include "renderer/pipeline.h"
#include "sphere_mesh.h"

#include <assets/texture.h>
#include <scenegraph/camera.h>

#include <glad/glad.h>
#include <glm/gtc/matrix_transform.hpp>

#include <cstdio>
#include <fstream>

namespace renderer {

ShieldPass::ShieldPass() = default;
ShieldPass::~ShieldPass() = default;

void ShieldPass::register_ship(scenegraph::InstanceId id,
                                ShieldMode mode,
                                float decay_seconds,
                                const glm::vec4& default_color,
                                const glm::vec3& aabb_center,
                                const glm::vec3& aabb_half_extents) {
    registry_.register_instance(id, mode, decay_seconds, default_color,
                                aabb_center, aabb_half_extents);
}

void ShieldPass::unregister_ship(scenegraph::InstanceId id) {
    registry_.unregister_instance(id);
}

void ShieldPass::shield_hit(scenegraph::InstanceId id,
                             const glm::vec3& point_world,
                             const glm::vec4& rgba,
                             float intensity,
                             double now_seconds) {
    registry_.push_hit(id, point_world, rgba, intensity, now_seconds);
}

assets::Mesh* ShieldPass::ensure_sphere() {
    if (sphere_) return sphere_.get();
    assets::MeshCpu cpu = build_uv_sphere(256);
    sphere_ = std::make_unique<assets::Mesh>(assets::upload_mesh(cpu));
    return sphere_.get();
}

void ShieldPass::ensure_textures_loaded() {
    if (tex_loaded_) return;
    for (int i = 0; i < 4; ++i) {
        char path[256];
        std::snprintf(path, sizeof(path),
                      "game/data/Textures/Tactical/shieldhit0%d.TGA", i + 1);
        std::ifstream in(path, std::ios::binary);
        if (!in) {
            std::fprintf(stderr, "[shield] failed to open '%s'\n", path);
            tex_[i] = std::make_unique<assets::Texture>();
            continue;
        }
        in.seekg(0, std::ios::end);
        auto size = static_cast<std::size_t>(in.tellg());
        in.seekg(0, std::ios::beg);
        std::vector<std::uint8_t> bytes(size);
        in.read(reinterpret_cast<char*>(bytes.data()),
                static_cast<std::streamsize>(size));
        try {
            assets::Image img = assets::decode_tga(bytes);
            assets::Texture tex = assets::upload_image(img, /*generate_mipmaps=*/true);
            tex_[i] = std::make_unique<assets::Texture>(std::move(tex));
        } catch (const std::exception& e) {
            std::fprintf(stderr, "[shield] failed to decode '%s': %s\n", path, e.what());
            tex_[i] = std::make_unique<assets::Texture>();
        }
    }
    tex_loaded_ = true;
}

void ShieldPass::submit(const scenegraph::World& /*world*/,
                         const scenegraph::Camera& /*camera*/,
                         Pipeline& /*pipeline*/,
                         double now_seconds) {
    // Decay every registered shield. Draw is Task 8.
    registry_.tick_all(now_seconds);
}

}  // namespace renderer
