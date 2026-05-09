#include <gtest/gtest.h>
#include <assets/texture.h>
#include <glad/glad.h>

#include "gl_fixture.h"

class TextureUploadTest : public assets_test::GLContext {};

TEST_F(TextureUploadTest, UploadsRgba8WithMipmaps) {
    assets::Image img;
    img.width = 8;
    img.height = 8;
    img.format = assets::Image::Format::RGBA8;
    img.pixels.assign(8 * 8 * 4, 0xCC);

    auto tex = assets::upload_image(img, /*generate_mipmaps=*/true);
    EXPECT_NE(tex.id(), 0u);
    EXPECT_TRUE(glIsTexture(tex.id()));
    EXPECT_EQ(tex.width(), 8u);
    EXPECT_EQ(tex.height(), 8u);
    EXPECT_TRUE(tex.has_mipmaps());

    GLint w = 0;
    glBindTexture(GL_TEXTURE_2D, tex.id());
    glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_WIDTH, &w);
    EXPECT_EQ(w, 8);
    glBindTexture(GL_TEXTURE_2D, 0);
}

TEST_F(TextureUploadTest, MovedFromTextureIsZero) {
    assets::Image img;
    img.width = 4;
    img.height = 4;
    img.format = assets::Image::Format::RGBA8;
    img.pixels.assign(64, 0);

    auto a = assets::upload_image(img, false);
    auto b = std::move(a);
    EXPECT_EQ(a.id(), 0u);
    EXPECT_NE(b.id(), 0u);
    EXPECT_TRUE(glIsTexture(b.id()));
}

TEST_F(TextureUploadTest, Rgb8Uploads) {
    assets::Image img;
    img.width = 2;
    img.height = 2;
    img.format = assets::Image::Format::RGB8;
    img.pixels.assign(2 * 2 * 3, 0x80);

    auto tex = assets::upload_image(img, false);
    EXPECT_TRUE(glIsTexture(tex.id()));
    EXPECT_FALSE(tex.has_mipmaps());  // dimensions <= 4
}
