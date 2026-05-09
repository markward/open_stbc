// native/src/assets/include/assets/cache.h
//
// Refcounted, NIF-path-keyed asset cache. Single-threaded by design;
// caller must ensure a current GL 3.3 core context is on the calling thread
// at load() time and at AssetCache destruction time (the destructor releases
// GL handles via Texture / Mesh dtors).
#pragma once

#include <assets/asset.h>
#include <assets/mesh.h>
#include <assets/model.h>
#include <assets/texture.h>

#include <filesystem>
#include <functional>
#include <memory>
#include <stdexcept>

namespace assets {

class AssetError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class AssetCache {
public:
    struct Config {
        bool keep_cpu_data = false;
        // Test-only injection points. Production callers leave both empty;
        // the cache substitutes upload_image / upload_mesh.
        std::function<Texture(const Image&, bool)> texture_uploader;
        std::function<Mesh(MeshCpu)>               mesh_uploader;
    };

    AssetCache();                     // equivalent to AssetCache(Config{})
    explicit AssetCache(Config cfg);
    ~AssetCache();
    AssetCache(const AssetCache&) = delete;
    AssetCache& operator=(const AssetCache&) = delete;

    /// Synchronous load. Identical (nif_path, texture_search_path) returns
    /// the same handle. Different texture_search_path with the same nif_path
    /// throws AssetError.
    ModelHandle load(const std::filesystem::path& nif_path,
                     const std::filesystem::path& texture_search_path);

    void evict(const std::filesystem::path& nif_path);
    void evict_unused();

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace assets
