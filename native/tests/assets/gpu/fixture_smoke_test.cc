#include <gtest/gtest.h>
#include <glad/glad.h>

#include "gl_fixture.h"

class GlFixtureSmoke : public assets_test::GLContext {};

TEST_F(GlFixtureSmoke, GlGetStringReturnsRenderer) {
    auto* renderer = reinterpret_cast<const char*>(glGetString(GL_RENDERER));
    ASSERT_NE(renderer, nullptr);
    SUCCEED() << "GL_RENDERER = " << renderer;
}

TEST_F(GlFixtureSmoke, NoErrorAtStartup) {
    EXPECT_EQ(glGetError(), GL_NO_ERROR);
}
