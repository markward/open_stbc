// native/src/nif/src/blocks/extra_data.cc
//
// NiStringExtraData parser for NIF v3.1.
//
// Per niflib (BSD), v3.1 NiExtraData reads only a `next_extra_data_link`
// uint32 (the per-extra-data linked-list pointer) — `name` is since
// v10.0.1.0 so absent in v3.1. NiStringExtraData adds bytes_remaining
// (uint32) + stringData (uint32 length + ASCII bytes).
#include "../dispatch.h"
#include "../reader.h"

#include <nif/block.h>

namespace nif {

NIF_REGISTER_BLOCK(NiStringExtraData, [](Reader& r) -> Block {
    NiStringExtraData d;
    d.next_extra_data_link = r.read_uint32();
    d.bytes_remaining = r.read_uint32();
    d.string_data = r.read_string_uint32();
    return d;
});

}  // namespace nif
