// native/src/renderer/pipeline.cc
#include "renderer/pipeline.h"

#include <glad/glad.h>

#include "embedded_opaque_vs.h"
#include "embedded_opaque_fs.h"

namespace renderer {

Pipeline::Pipeline() {
    opaque_ = std::make_unique<Shader>(shader_src::opaque_vs, shader_src::opaque_fs);
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LESS);
    glEnable(GL_CULL_FACE);
    glCullFace(GL_BACK);
    glFrontFace(GL_CCW);
}

}  // namespace renderer
