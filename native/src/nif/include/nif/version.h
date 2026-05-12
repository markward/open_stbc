// native/src/nif/include/nif/version.h
#pragma once

#include <cstdint>

namespace nif {

// v3.1 has no user_version concept (introduced post-v10). For BC the only
// version field is the 4-byte version after the multi-line text header.
struct Version {
    std::uint32_t value = 0;
};

// Bridge Commander uses NIF v3.1 for most assets, encoded as 0x03010000.
// A handful of legacy assets (planets, viewscreens, the Kessok head) use the
// older v3.0 format encoded as 0x03000000.
//
// Caveat for SDK reference: the Gamebryo 1.2.2 SDK's loader minimum is
// 3.3.0.11, so its sources describe 3.3+ behavior and cannot load BC NIFs
// directly. For BC v3.1/v3.0 on-disk schemas, niflib's nif.xml and the
// reverse-engineered NifSkope tables remain authoritative on version gates.
inline constexpr std::uint32_t kBcVersionValue   = 0x03010000;
inline constexpr std::uint32_t kBcLegacyVersion  = 0x03000000;

inline bool is_bc(Version v) {
    return v.value == kBcVersionValue || v.value == kBcLegacyVersion;
}

}  // namespace nif
