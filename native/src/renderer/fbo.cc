// native/src/renderer/fbo.cc
#include "renderer/fbo.h"

namespace renderer {

Fbo::~Fbo() {
    if (color_) glDeleteTextures(1, &color_);
    if (fbo_)   glDeleteFramebuffers(1, &fbo_);
}

void Fbo::resize(int w, int h) {
    if (w == w_ && h == h_) return;
    w_ = w;
    h_ = h;

    if (!fbo_) glGenFramebuffers(1, &fbo_);
    if (color_) glDeleteTextures(1, &color_);

    glGenTextures(1, &color_);
    glBindTexture(GL_TEXTURE_2D, color_);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glBindTexture(GL_TEXTURE_2D, 0);

    glBindFramebuffer(GL_FRAMEBUFFER, fbo_);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, color_, 0);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
}

void Fbo::bind() const {
    glBindFramebuffer(GL_FRAMEBUFFER, fbo_);
}

void Fbo::unbind() {
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
}

}  // namespace renderer
