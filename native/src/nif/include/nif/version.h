// native/src/nif/include/nif/version.h
#pragma once

#include <cstdint>

namespace nif {

// v3.1 has no user_version concept (introduced post-v10). For BC the only
// version field is the 4-byte version after the multi-line text header.
struct Version {
    std::uint32_t value = 0;
};

// Bridge Commander uses NIF v3.1, encoded as 0x03010000.
inline constexpr std::uint32_t kBcVersionValue = 0x03010000;

inline bool is_bc(Version v) {
    return v.value == kBcVersionValue;
}

}  // namespace nif
