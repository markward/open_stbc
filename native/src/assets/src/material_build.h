// native/src/assets/src/material_build.h
#pragma once

#include <assets/material.h>
#include <nif/block.h>

#include <unordered_map>

namespace assets::detail {

/// Inputs for building a Material — the property blocks linked from a
/// NiTriShape, plus an image-link → texture-index map produced by the
/// orchestrator.
struct MaterialInputs {
    const nif::NiMaterialProperty*     material      = nullptr;
    const nif::NiTexturingProperty*    texturing     = nullptr;
    const nif::NiMultiTextureProperty* multi_texture = nullptr;
    const nif::NiAlphaProperty*        alpha         = nullptr;
    const nif::NiZBufferProperty*      zbuffer       = nullptr;
    const nif::NiVertexColorProperty*  vertex_color  = nullptr;
    /// Maps NIF block index of a NiImage → assets::Model::textures index.
    const std::unordered_map<std::uint32_t, int>* image_to_texture = nullptr;
};

Material build_material(const MaterialInputs&);

}  // namespace assets::detail
