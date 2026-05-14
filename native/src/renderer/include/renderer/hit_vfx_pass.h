// native/src/renderer/include/renderer/hit_vfx_pass.h
#pragma once

#include <renderer/frame.h>
#include <assets/texture.h>

#include <memory>
#include <vector>

namespace scenegraph { struct Camera; }

namespace renderer {

class Pipeline;

class HitVfxPass {
public:
    HitVfxPass();
    ~HitVfxPass();
    HitVfxPass(const HitVfxPass&)            = delete;
    HitVfxPass& operator=(const HitVfxPass&) = delete;

    /// Render every active hit VFX as an additive billboard at its world
    /// position.  Size eases 0→1 over first 100ms; alpha fades 1→0 over
    /// next 400ms based on `age` (engine prunes after 500ms).
    void render(const std::vector<HitVfxDescriptor>& vfx,
                const scenegraph::Camera& camera,
                Pipeline& pipeline);

private:
    unsigned int quad_vao_ = 0;
    unsigned int quad_vbo_ = 0;
    std::unique_ptr<assets::Texture> texture_;

    void ensure_quad_mesh();
    void ensure_texture();
};

}  // namespace renderer
