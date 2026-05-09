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

}  // namespace

NIF_REGISTER_BLOCK(NiKeyframeController, [](Reader& r) -> Block {
    return parse_NiKeyframeController_body(r);
});

}  // namespace nif
