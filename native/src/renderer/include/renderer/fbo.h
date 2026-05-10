// native/src/renderer/include/renderer/fbo.h
#pragma once

#include <glad/glad.h>

namespace renderer {

// Color-only offscreen framebuffer. Lazy-allocated: resize() creates/recreates
// the texture attachment; calling bind() before resize() is undefined.
// Caller must ensure the GL context is alive when the destructor runs.
class Fbo {
public:
    Fbo() = default;
    ~Fbo();
    Fbo(const Fbo&) = delete;
    Fbo& operator=(const Fbo&) = delete;

    // Create or resize the color attachment. No-op when dimensions match.
    void resize(int w, int h);

    void bind() const;
    static void unbind();   // binds framebuffer 0

    GLuint color_id() const noexcept { return color_; }

private:
    GLuint fbo_   = 0;
    GLuint color_ = 0;
    int    w_     = 0;
    int    h_     = 0;
};

}  // namespace renderer
