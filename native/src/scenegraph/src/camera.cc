// native/src/scenegraph/src/camera.cc
#include "scenegraph/camera.h"

#include <glm/gtc/matrix_transform.hpp>

namespace scenegraph {

glm::mat4 Camera::view_matrix() const noexcept {
    return glm::lookAt(eye, target, up);
}

glm::mat4 Camera::proj_matrix() const noexcept {
    return glm::perspective(fov_y_rad, aspect, near, far);
}

}  // namespace scenegraph
