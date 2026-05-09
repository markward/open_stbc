// native/src/assets/include/assets/path_resolver.h
#pragma once

#include <filesystem>
#include <stdexcept>
#include <string>
#include <unordered_map>

namespace assets {

class TextureNotFound : public std::runtime_error {
public:
    TextureNotFound(std::string basename, std::filesystem::path searched_dir);
    const std::string&            basename()     const noexcept { return basename_; }
    const std::filesystem::path&  searched_dir() const noexcept { return searched_dir_; }

private:
    std::string                basename_;
    std::filesystem::path      searched_dir_;
};

/// Case-insensitive basename → on-disk-path lookup against a single directory.
/// Caches a lowercase→actual-name map per searched directory; rebuilds on miss
/// so files dropped at runtime are still found after one cache invalidation.
class PathResolver {
public:
    std::filesystem::path resolve(
        std::string basename,
        const std::filesystem::path& search_dir);

private:
    using LowerToActual = std::unordered_map<std::string, std::string>;
    std::unordered_map<std::string, LowerToActual> cache_;

    LowerToActual&    cache_for(const std::filesystem::path& dir, bool force_rebuild);
    static std::string to_lower(std::string_view s);
    static bool        has_extension(std::string_view basename);
};

}  // namespace assets
