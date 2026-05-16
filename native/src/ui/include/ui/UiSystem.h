// native/src/ui/include/ui/UiSystem.h
#pragma once

#include <filesystem>
#include <memory>
#include <string>
#include <unordered_map>

struct GLFWwindow;
namespace Rml { class Context; }
class SystemInterface_GLFW;
class RenderInterface_GL3;

namespace ui {

class HudDocument;
class PanelDocument;

struct HudState {
    float pos_x = 0.f, pos_y = 0.f, pos_z = 0.f;
    float yaw_deg = 0.f, pitch_deg = 0.f, roll_deg = 0.f;
    std::string system_name;
    std::string ship_name;
};

class UiSystem {
public:
    /// Initialise RmlUi, load the font and HUD document from assets_root.
    /// Throws std::runtime_error if Rml::Initialise() or context creation fails.
    UiSystem(GLFWwindow* window, const std::filesystem::path& assets_root);
    ~UiSystem();

    UiSystem(const UiSystem&) = delete;
    UiSystem& operator=(const UiSystem&) = delete;

    /// Update HUD element text. Call once per frame before render().
    void update_hud(const HudState& state);

    /// Render the UI context at the given framebuffer size.
    void render(int fb_width, int fb_height);

    /// Create a new PanelDocument from panel.rml. Returns an integer handle
    /// the bindings use to reference it later. Ownership stays with this
    /// UiSystem.
    int create_panel(const std::string& anchor, float width_vw, float height_vh);
    void destroy_panel(int panel_id);
    PanelDocument* get_panel(int panel_id);

    /// Iterator access for the binding layer — used to resolve which panel
    /// owns a given element id when callers pass element ids directly.
    auto& panels_for_bindings() { return panels_; }

    /// Set the base UI scale multiplier. The actual `dp-ratio` applied to
    /// the RmlUi context is `scale * fb_height / reference_height` and is
    /// recomputed on every render() when the framebuffer height changes.
    /// This keeps UI elements at the same screen-relative size across
    /// 1080p / 1440p / UHD instead of locking them to absolute pixels.
    /// A multiplier of 1.0 matches the reference height (1080p) at native
    /// dp; 1.25 makes everything 25% larger at all resolutions.
    void set_ui_scale(float scale);

    /// Toggle the RmlUi debugger overlay. Shows the live element tree,
    /// computed styles, layout boxes — exactly what we need to see when
    /// "the panel only renders at top and bottom" without theorising.
    void toggle_debugger();

    /// Toggle whole-UI visibility (every panel + HUD doc).
    void toggle_visibility();

private:
    std::unique_ptr<SystemInterface_GLFW> sys_iface_;
    std::unique_ptr<RenderInterface_GL3>  render_iface_;
    Rml::Context*                         context_ = nullptr;
    std::unique_ptr<HudDocument>          hud_;

    std::filesystem::path                 assets_root_;
    std::unordered_map<int, std::unique_ptr<PanelDocument>> panels_;
    int                                   next_panel_id_ = 1;
    bool                                  rendering_enabled_ = true;

    // Resolution-proportional dp scaling. base_scale_ is the user-facing
    // multiplier passed to set_ui_scale(); applied_scale_ is the value most
    // recently pushed to the RmlUi context. last_fb_height_ caches the
    // framebuffer height that produced applied_scale_ so render() can skip
    // the recompute when the window hasn't resized.
    float                                 base_scale_ = 1.0f;
    int                                   last_fb_width_ = 0;
    int                                   last_fb_height_ = 0;
    static constexpr float                kReferenceHeight = 1080.0f;

    void apply_scale_for_height_(int fb_height);
};

}  // namespace ui
