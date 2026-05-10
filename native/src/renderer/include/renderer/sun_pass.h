// native/src/renderer/include/renderer/sun_pass.h
#pragma once

#include <renderer/frame.h>
#include <renderer/fbo.h>
#include <assets/mesh.h>
#include <assets/texture.h>

#include <glad/glad.h>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace scenegraph { struct Camera; }

namespace renderer {

class Pipeline;

class SunPass {
public:
    SunPass() = default;
    ~SunPass();
    SunPass(const SunPass&) = delete;
    SunPass& operator=(const SunPass&) = delete;

    void render(const std::vector<SunDescriptor>& suns,
                const scenegraph::Camera& camera,
                Pipeline& pipeline);

private:
    std::unordered_map<int, std::unique_ptr<assets::Mesh>>           sphere_cache_;
    std::unordered_map<std::string, std::unique_ptr<assets::Texture>> texture_cache_;
    Fbo     fbo_[2];        // ping-pong: [0] corona render, [1] H-blur result
    GLuint  quad_vao_ = 0;  // empty VAO for fullscreen triangle draw

    assets::Mesh*    ensure_sphere(int target_tris = 256);
    assets::Texture* ensure_texture(const std::string& path);
    void             ensure_quad_vao();
};

}  // namespace renderer
