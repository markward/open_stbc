// native/src/ui/UiSystem.cc
#include "ui/UiSystem.h"
#include "ui/HudDocument.h"

// glad must be included before any GL headers.
#include <glad/glad.h>

#include <RmlUi_Platform_GLFW.h>
#include <RmlUi_Renderer_GL3.h>
#include <RmlUi/Core.h>
#include <GLFW/glfw3.h>

#include <cstdio>
#include <stdexcept>

namespace ui {

UiSystem::UiSystem(GLFWwindow* window,
                   const std::filesystem::path& assets_root)
    : sys_iface_(std::make_unique<SystemInterface_GLFW>())
    , render_iface_(std::make_unique<RenderInterface_GL3>())
{
    sys_iface_->SetWindow(window);

    Rml::SetSystemInterface(sys_iface_.get());

    if (!Rml::Initialise()) {
        throw std::runtime_error("ui::UiSystem: Rml::Initialise() failed");
    }

    int fb_width = 0, fb_height = 0;
    glfwGetFramebufferSize(window, &fb_width, &fb_height);
    if (fb_width  <= 0) fb_width  = 1280;
    if (fb_height <= 0) fb_height = 720;

    context_ = Rml::CreateContext(
        "main",
        Rml::Vector2i(fb_width, fb_height),
        render_iface_.get()
    );
    if (!context_) {
        Rml::Shutdown();
        throw std::runtime_error("ui::UiSystem: Rml::CreateContext failed");
    }

    auto font_path = (assets_root / "fonts" / "Antonio-Regular.ttf").string();
    if (!Rml::LoadFontFace(font_path)) {
        std::fprintf(stderr,
            "[ui] Warning: failed to load font '%s' - HUD text will not render\n",
            font_path.c_str());
    }

    hud_ = std::make_unique<HudDocument>(context_, assets_root / "hud.rml");
}

UiSystem::~UiSystem() {
    hud_.reset();
    context_ = nullptr;  // owned by RmlUi core; Shutdown destroys it
    Rml::Shutdown();
}

void UiSystem::update_hud(const HudState& state) {
    if (hud_) hud_->update(state);
    if (context_) context_->Update();
}

void UiSystem::render(int fb_width, int fb_height) {
    if (!context_) return;
    render_iface_->SetViewport(fb_width, fb_height);
    render_iface_->BeginFrame();
    context_->Render();
    render_iface_->EndFrame();
}

}  // namespace ui
