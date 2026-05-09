// native/src/scenegraph/include/scenegraph/camera.h
#pragma once

#include <glm/glm.hpp>

namespace scenegraph {

struct Camera {
    glm::vec3 eye{0.0f, 0.0f, 5.0f};
    glm::vec3 target{0.0f, 0.0f, 0.0f};
    glm::vec3 up{0.0f, 1.0f, 0.0f};
    float fov_y_rad = 1.0472f;  // 60 degrees
    float aspect = 16.0f / 9.0f;
    float near = 0.1f;
    float far = 100000.0f;  // BC scenes can be tens of km

    glm::mat4 view_matrix() const noexcept;
    glm::mat4 proj_matrix() const noexcept;
};

}  // namespace scenegraph
