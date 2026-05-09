// native/src/renderer/include/renderer/pipeline.h
#pragma once

#include "renderer/shader.h"

#include <memory>

namespace renderer {

class Pipeline {
public:
    Pipeline();

    Shader& opaque_shader() noexcept { return *opaque_; }

private:
    std::unique_ptr<Shader> opaque_;
};

}  // namespace renderer
