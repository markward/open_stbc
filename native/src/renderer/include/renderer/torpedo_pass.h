// native/src/renderer/include/renderer/torpedo_pass.h
#pragma once

#include <renderer/frame.h>
#include <assets/texture.h>

#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace scenegraph { struct Camera; }

namespace renderer {

class Pipeline;

class TorpedoPass {
public:
    TorpedoPass();
    ~TorpedoPass();
    TorpedoPass(const TorpedoPass&)            = delete;
    TorpedoPass& operator=(const TorpedoPass&) = delete;

    /// Render every torpedo as three additive billboards (glow, flares,
    /// core) at its world position.  Caller pushes the descriptor list
    /// via host's set_torpedoes binding before each frame.
    void render(const std::vector<TorpedoDescriptor>& torpedoes,
                const scenegraph::Camera& camera,
                Pipeline& pipeline);

private:
    // Unit-quad VAO/VBO — single shared mesh, repeated per torpedo per
    // layer with per-draw uniforms (position / size / color / texture).
    unsigned int quad_vao_ = 0;
    unsigned int quad_vbo_ = 0;
    std::unordered_map<std::string, std::unique_ptr<assets::Texture>> texture_cache_;

    void             ensure_quad_mesh();
    assets::Texture* ensure_texture(const std::string& path);
};

}  // namespace renderer
