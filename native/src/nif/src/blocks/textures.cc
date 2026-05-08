// native/src/nif/src/blocks/textures.cc
//
// Texture-related parsers for NIF v3.1 (legacy pre-10.1 family):
//   - NiTextureModeProperty: NiObjectNET + flags(u16) + ps2_l(i16) + ps2_k(i16)
//   - NiImage: use_external(u8) + (file_name | image_data_link) + unknown_int + unknown_float
//   - NiTextureProperty: NiObjectNET + flags(u16) + image_link(u32)
//
// NiMultiTextureProperty inherits from NiTexturingProperty which has a much
// larger conditional body (texture descriptors per slot). Deferred until a
// later task — Galaxy.nif uses NiTextureProperty/NiImage which suffice for
// the walker's first pass through ship blocks.

#include "../dispatch.h"
#include "../reader.h"
#include "av_object_base.h"

#include <nif/block.h>

#include <cstdint>

namespace nif {

namespace {

NiTextureModeProperty parse_NiTextureModeProperty_body(Reader& r) {
    NiTextureModeProperty p;
    p.obj = parse_object_net_base(r);
    p.flags = r.read_uint16();
    // PS2 L / PS2 K are signed shorts (since 3.1, until 10.2.0.0).
    p.ps2_l = static_cast<std::int16_t>(r.read_uint16());
    p.ps2_k = static_cast<std::int16_t>(r.read_uint16());
    return p;
}

NiImage parse_NiImage_body(Reader& r) {
    NiImage img;
    img.use_external = r.read_uint8();
    if (img.use_external != 0) {
        img.file_name = r.read_string_uint32();
    } else {
        img.image_data_link = r.read_uint32();
    }
    img.unknown_int = r.read_uint32();
    img.unknown_float = r.read_float();  // since 3.1, present in v3.1
    return img;
}

NiTextureProperty parse_NiTextureProperty_body(Reader& r) {
    NiTextureProperty p;
    p.obj = parse_object_net_base(r);
    p.flags = r.read_uint16();
    p.image_link = r.read_uint32();
    return p;
}

}  // namespace

NIF_REGISTER_BLOCK(NiTextureModeProperty, [](Reader& r) -> Block {
    return parse_NiTextureModeProperty_body(r);
});

NIF_REGISTER_BLOCK(NiImage, [](Reader& r) -> Block {
    return parse_NiImage_body(r);
});

NIF_REGISTER_BLOCK(NiTextureProperty, [](Reader& r) -> Block {
    return parse_NiTextureProperty_body(r);
});

}  // namespace nif
