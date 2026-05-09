// native/tests/scenegraph/camera_test.cc
#include <gtest/gtest.h>

#include <scenegraph/camera.h>

#include <glm/gtc/matrix_transform.hpp>

namespace {

constexpr float kEpsilon = 1e-5f;

bool nearly_equal(const glm::mat4& a, const glm::mat4& b) {
    for (int c = 0; c < 4; ++c)
        for (int r = 0; r < 4; ++r)
            if (std::fabs(a[c][r] - b[c][r]) > kEpsilon) return false;
    return true;
}

TEST(Camera, ViewMatrixMatchesGlmLookAt) {
    scenegraph::Camera cam;
    cam.eye = glm::vec3(0.0f, 0.0f, 5.0f);
    cam.target = glm::vec3(0.0f, 0.0f, 0.0f);
    cam.up = glm::vec3(0.0f, 1.0f, 0.0f);

    auto expected = glm::lookAt(cam.eye, cam.target, cam.up);
    EXPECT_TRUE(nearly_equal(cam.view_matrix(), expected));
}

TEST(Camera, ProjMatrixMatchesGlmPerspective) {
    scenegraph::Camera cam;
    cam.fov_y_rad = glm::radians(45.0f);
    cam.aspect = 16.0f / 9.0f;
    cam.near = 0.1f;
    cam.far = 1000.0f;

    auto expected = glm::perspective(cam.fov_y_rad, cam.aspect, cam.near, cam.far);
    EXPECT_TRUE(nearly_equal(cam.proj_matrix(), expected));
}

}  // namespace
