// native/src/nif/src/blocks/animation.cc
//
// NiKeyframeController parser for NIF v3.1.
//
// Per niflib (BSD): NiKeyframeController inherits NiSingleInterpController
// → NiInterpController → NiTimeController. For v3.1 only NiTimeController
// fields are present, plus the v3.1-conditional unknown_integer, plus the
// NiKeyframeController-specific data_link.
//
// v3.1 NiKeyframeController body (per niflib's auto-gen Read):
//   next_controller_link (uint32)   // NiTimeController
//   flags                (uint16)
//   frequency            (float)
//   phase                (float)
//   start_time           (float)
//   stop_time            (float)
//   // skin instance ref since 3.3.0.13 — absent in v3.1
//   unknown_integer      (uint32)   // version <= 3.1
//   data_link            (uint32)   // version <= 10.1.0.0

#include "../dispatch.h"
#include "../reader.h"

#include <nif/block.h>

namespace nif {

namespace {

NiKeyframeController parse_NiKeyframeController_body(Reader& r) {
    NiKeyframeController k;
    k.next_controller_link = r.read_uint32();
    k.flags = r.read_uint16();
    k.frequency = r.read_float();
    k.phase = r.read_float();
    k.start_time = r.read_float();
    k.stop_time = r.read_float();
    k.unknown_integer = r.read_uint32();
    k.data_link = r.read_uint32();
    return k;
}

// NiTriShapeSkinController v3.1: NiTimeController fields, then per-bone
// vertex counts, bone links, and (bone, vertex) weight tuples.
//
// Per niflib's auto-gen Read:
//   NiTimeController fields
//   numBones (uint32)
//   vertexCounts (uint32 × numBones)
//   bones (uint32 × numBones)  -- block links
//   boneData (per bone, per vertex_count[bone]):
//     vertexWeight (float)
//     vertexIndex (uint16)
//     unknownVector (Vec3)
NiTriShapeSkinController parse_NiTriShapeSkinController_body(Reader& r) {
    NiTriShapeSkinController c;
    c.next_controller_link = r.read_uint32();
    c.flags = r.read_uint16();
    c.frequency = r.read_float();
    c.phase = r.read_float();
    c.start_time = r.read_float();
    c.stop_time = r.read_float();
    c.unknown_integer = r.read_uint32();

    c.num_bones = r.read_uint32();
    c.vertex_counts_per_bone.reserve(c.num_bones);
    for (std::uint32_t i = 0; i < c.num_bones; ++i) {
        c.vertex_counts_per_bone.push_back(r.read_uint32());
    }
    c.bone_links.reserve(c.num_bones);
    for (std::uint32_t i = 0; i < c.num_bones; ++i) {
        c.bone_links.push_back(r.read_uint32());
    }
    c.bone_weights.resize(c.num_bones);
    for (std::uint32_t i = 0; i < c.num_bones; ++i) {
        auto count = c.vertex_counts_per_bone[i];
        c.bone_weights[i].reserve(count);
        for (std::uint32_t j = 0; j < count; ++j) {
            OldSkinWeight w;
            w.weight = r.read_float();
            w.vertex_index = r.read_uint16();
            w.unknown_vector = r.read_vec3();
            c.bone_weights[i].push_back(w);
        }
    }
    return c;
}

}  // namespace

NIF_REGISTER_BLOCK(NiKeyframeController, [](Reader& r) -> Block {
    return parse_NiKeyframeController_body(r);
});

NIF_REGISTER_BLOCK(NiTriShapeSkinController, [](Reader& r) -> Block {
    return parse_NiTriShapeSkinController_body(r);
});

}  // namespace nif
