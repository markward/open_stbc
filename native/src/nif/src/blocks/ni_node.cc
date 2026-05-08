// native/src/nif/src/blocks/ni_node.cc
//
// NiNode parser for NIF v3.1 (BC). Field layout derived from nifxml schema
// (NiObjectNET → NiAVObject → NiNode), filtered by since/until/vercond for
// v3.1, and verified against Galaxy.nif's root NiNode body (offset 0xA2,
// 102 bytes total).
//
// v3.1 NiNode body layout:
//   NiObjectNET:
//     name             (uint32 length + ASCII bytes)
//     extra_data_link  (uint32 link ID, 0 = none)
//     controller_link  (uint32 link ID, 0 = none)
//   NiAVObject:
//     flags            (uint16)
//     translation      (Vec3 = 3 floats)
//     rotation         (Mat3x3 = 9 floats)
//     scale            (float)
//     velocity         (Vec3)
//     num_properties   (uint32)
//     property_links   (uint32 × num_properties)
//     has_bounding_volume (uint32 bool — 0 or 1)
//     bounding_volume  (only if has_bv == 1; not yet implemented)
//   NiNode:
//     num_children     (uint32)
//     child_links      (uint32 × num_children)
//     num_effects      (uint32)
//     effect_links     (uint32 × num_effects)

#include "../dispatch.h"
#include "../reader.h"

#include <nif/block.h>
#include <nif/error.h>

namespace nif {

namespace {

NiNode parse_NiNode_body(Reader& r) {
    NiNode n;
    n.name = r.read_string_uint32();
    n.extra_data_link = r.read_uint32();
    n.controller_link = r.read_uint32();
    n.flags = r.read_uint16();
    n.translation = r.read_vec3();
    n.rotation = r.read_mat3x3();
    n.scale = r.read_float();
    n.velocity = r.read_vec3();

    auto num_properties = r.read_uint32();
    n.property_links.reserve(num_properties);
    for (std::uint32_t i = 0; i < num_properties; ++i) {
        n.property_links.push_back(r.read_uint32());
    }

    auto has_bv = r.read_uint32();
    if (has_bv != 0 && has_bv != 1) {
        ParseError e("NiNode has_bounding_volume not 0 or 1: " + std::to_string(has_bv));
        e.file = r.source();
        e.byte_offset = r.offset();
        e.block_type = "NiNode";
        throw e;
    }
    n.has_bounding_volume = (has_bv == 1);
    if (n.has_bounding_volume) {
        ParseError e("NiNode with bounding_volume==1 not yet implemented; "
                     "no sample file required this path");
        e.file = r.source();
        e.byte_offset = r.offset();
        e.block_type = "NiNode";
        throw e;
    }

    auto num_children = r.read_uint32();
    n.child_links.reserve(num_children);
    for (std::uint32_t i = 0; i < num_children; ++i) {
        n.child_links.push_back(r.read_uint32());
    }

    auto num_effects = r.read_uint32();
    n.effect_links.reserve(num_effects);
    for (std::uint32_t i = 0; i < num_effects; ++i) {
        n.effect_links.push_back(r.read_uint32());
    }

    return n;
}

}  // namespace

NIF_REGISTER_BLOCK(NiNode, [](Reader& r) -> Block {
    return parse_NiNode_body(r);
});

}  // namespace nif
