// native/src/renderer/hit_vfx_pass.cc
#include "renderer/hit_vfx_pass.h"

#include "renderer/pipeline.h"

#include <assets/texture.h>
#include <scenegraph/camera.h>

#include <glad/glad.h>
#include <glm/glm.hpp>

#include <algorithm>
#include <cstdio>
#include <fstream>

namespace renderer {

namespace {

constexpr float kPeakSize  = 5.0f;   // world-units half-size at full expansion
constexpr float kSpawnDur  = 0.1f;
constexpr float kFadeDur   = 0.4f;
constexpr const char* kImpactTexturePath = "data/Textures/Tactical/TorpedoFlares.tga";

constexpr float kQuadCorners[] = {
    -1.0f, -1.0f,
    +1.0f, -1.0f,
    +1.0f, +1.0f,
    -1.0f, -1.0f,
    +1.0f, +1.0f,
    -1.0f, +1.0f,
};

}  // namespace

HitVfxPass::HitVfxPass() = default;

HitVfxPass::~HitVfxPass() {
    if (quad_vbo_) glDeleteBuffers(1, &quad_vbo_);
    if (quad_vao_) glDeleteVertexArrays(1, &quad_vao_);
}

void HitVfxPass::ensure_quad_mesh() {
    if (quad_vao_ != 0) return;
    glGenVertexArrays(1, &quad_vao_);
    glBindVertexArray(quad_vao_);
    glGenBuffers(1, &quad_vbo_);
    glBindBuffer(GL_ARRAY_BUFFER, quad_vbo_);
    glBufferData(GL_ARRAY_BUFFER, sizeof(kQuadCorners), kQuadCorners,
                 GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * sizeof(float),
                          reinterpret_cast<void*>(0));
    glBindVertexArray(0);
}

void HitVfxPass::ensure_texture() {
    if (texture_) return;
    std::ifstream in(kImpactTexturePath, std::ios::binary);
    if (!in) {
        std::fprintf(stderr, "[hit_vfx_pass] failed to open '%s'\n",
                     kImpactTexturePath);
        texture_ = std::make_unique<assets::Texture>();
        return;
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
        texture_ = std::make_unique<assets::Texture>(std::move(tex));
    } catch (const std::exception& e) {
        std::fprintf(stderr, "[hit_vfx_pass] failed to decode '%s': %s\n",
                     kImpactTexturePath, e.what());
        texture_ = std::make_unique<assets::Texture>();
    }
}

void HitVfxPass::render(const std::vector<HitVfxDescriptor>& vfx,
                        const scenegraph::Camera& camera,
                        Pipeline& pipeline) {
    if (vfx.empty()) return;
    ensure_quad_mesh();
    ensure_texture();
    if (!texture_ || texture_->id() == 0) return;

    auto& shader = pipeline.hit_vfx_shader();
    shader.use();

    const glm::mat4 vp = camera.proj_matrix() * camera.view_matrix();
    const glm::mat4 view = camera.view_matrix();
    const glm::vec3 cam_right = glm::vec3(view[0][0], view[1][0], view[2][0]);
    const glm::vec3 cam_up    = glm::vec3(view[0][1], view[1][1], view[2][1]);

    shader.set_mat4("u_view_proj",    vp);
    shader.set_vec3("u_camera_right", cam_right);
    shader.set_vec3("u_camera_up",    cam_up);
    shader.set_int ("u_texture",      0);

    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE);
    glEnable(GL_DEPTH_TEST);
    glDepthMask(GL_FALSE);
    glDisable(GL_CULL_FACE);

    glBindVertexArray(quad_vao_);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, texture_->id());

    for (const auto& v : vfx) {
        const float age = std::max(0.0f, v.age);
        const float size_t  = std::min(1.0f, age / kSpawnDur);
        const float fade_t  = std::max(0.0f, std::min(1.0f,
                                  (age - kSpawnDur) / kFadeDur));
        const float size    = kPeakSize * size_t;
        const float alpha   = 1.0f - fade_t;
        shader.set_vec3 ("u_world_position", v.world_pos);
        shader.set_float("u_size",           size);
        shader.set_float("u_alpha",          alpha);
        glDrawArrays(GL_TRIANGLES, 0, 6);
    }

    glBindVertexArray(0);
    glEnable(GL_CULL_FACE);
    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);
}

}  // namespace renderer
