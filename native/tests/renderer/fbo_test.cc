// native/tests/renderer/fbo_test.cc
#include <gtest/gtest.h>

#include <renderer/fbo.h>
#include <renderer/window.h>

#include <glad/glad.h>

namespace {

class FboTest : public ::testing::Test {
protected:
    std::unique_ptr<renderer::Window> window;
    void SetUp() override {
        try {
            window = std::make_unique<renderer::Window>(64, 64, "fbo_test", false);
        } catch (const std::runtime_error& e) {
            GTEST_SKIP() << "no GL context: " << e.what();
        }
    }
};

TEST_F(FboTest, ResizeCreatesColorAttachment) {
    renderer::Fbo fbo;
    fbo.resize(64, 64);
    EXPECT_NE(fbo.color_id(), 0u);
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}

TEST_F(FboTest, ResizeIsNoOpWhenDimensionsMatch) {
    renderer::Fbo fbo;
    fbo.resize(64, 64);
    GLuint first_id = fbo.color_id();
    fbo.resize(64, 64);
    EXPECT_EQ(fbo.color_id(), first_id);
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}

TEST_F(FboTest, ResizeRecreatesTextureOnSizeChange) {
    renderer::Fbo fbo;
    fbo.resize(64, 64);
    fbo.resize(128, 128);
    EXPECT_NE(fbo.color_id(), 0u);
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}

TEST_F(FboTest, BindAndUnbindProduceNoGLError) {
    renderer::Fbo fbo;
    fbo.resize(64, 64);
    fbo.bind();
    renderer::Fbo::unbind();
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}

TEST_F(FboTest, ClearAfterBindProducesNoGLError) {
    renderer::Fbo fbo;
    fbo.resize(64, 64);
    fbo.bind();
    glClearColor(0, 0, 0, 0);
    glClear(GL_COLOR_BUFFER_BIT);
    renderer::Fbo::unbind();
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}

}  // namespace
