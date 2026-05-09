// native/tests/renderer/skybox_test.cc
#include <gtest/gtest.h>

#include <renderer/pipeline.h>
#include <renderer/frame.h>
#include <renderer/window.h>

#include <scenegraph/camera.h>

#include <glad/glad.h>

namespace {

class SkyboxTest : public ::testing::Test {
protected:
    std::unique_ptr<renderer::Window> w;
    std::unique_ptr<renderer::Pipeline> p;
    void SetUp() override {
        try {
            w = std::make_unique<renderer::Window>(64, 64, "skybox-test", false);
        } catch (const std::runtime_error& e) {
            GTEST_SKIP() << "no GL: " << e.what();
        }
        p = std::make_unique<renderer::Pipeline>();
    }
};

TEST_F(SkyboxTest, NullModelIsNoOp) {
    scenegraph::Camera cam;
    renderer::FrameSubmitter s;
    s.submit_skybox(nullptr, cam, *p);
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}

TEST_F(SkyboxTest, SkyboxShaderCompiles) {
    EXPECT_NE(p->skybox_shader().program(), 0u);
}

}  // namespace
