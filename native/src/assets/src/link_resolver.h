// native/src/assets/src/link_resolver.h
//
// Maps NIF cross-block link IDs (the uint32 values stored in
// `child_links`, `data_link`, `property_links`, `controller_link`, etc.)
// to indices into `nif::File::blocks`. Real BC files use arbitrary 8-digit
// values rather than sequential array positions, so we can't index directly.
//
// Falls back to identity when `f.block_ids` is empty (the case for synthetic
// tests that build a `nif::File` programmatically without populating link IDs).
#pragma once

#include <nif/file.h>

#include <cstdint>
#include <unordered_map>

namespace assets::detail {

class LinkResolver {
public:
    static constexpr std::uint32_t kInvalidIndex = ~0u;

    explicit LinkResolver(const nif::File& f) {
        if (f.block_ids.empty()) {
            fallback_identity_ = true;
            block_count_ = f.blocks.size();
            return;
        }
        link_to_index_.reserve(f.block_ids.size());
        for (std::uint32_t i = 0; i < f.block_ids.size(); ++i) {
            link_to_index_.emplace(f.block_ids[i], i);
        }
        block_count_ = f.blocks.size();
    }

    /// Block array index for `link_id`, or `kInvalidIndex` if not found.
    std::uint32_t resolve(std::uint32_t link_id) const noexcept {
        if (fallback_identity_) {
            return (link_id < block_count_) ? link_id : kInvalidIndex;
        }
        auto it = link_to_index_.find(link_id);
        return (it != link_to_index_.end()) ? it->second : kInvalidIndex;
    }

private:
    bool fallback_identity_ = false;
    std::unordered_map<std::uint32_t, std::uint32_t> link_to_index_;
    std::size_t block_count_ = 0;
};

}  // namespace assets::detail
