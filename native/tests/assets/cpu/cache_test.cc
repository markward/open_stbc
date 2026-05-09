#include <gtest/gtest.h>
#include <assets/cache.h>
#include <nif/file.h>

#include <filesystem>

namespace fs = std::filesystem;

namespace {

bool game_data_present() {
    fs::path p1 = fs::path(OPEN_STBC_PROJECT_ROOT)
        / "game/data/Models/Ships/Galaxy/Galaxy.nif";
    if (fs::exists(p1)) return true;
    return fs::exists("/Users/mward/Documents/Projects/open_stbc/game/data/Models/Ships/Galaxy/Galaxy.nif");
}

fs::path galaxy_path() {
    fs::path p = fs::path(OPEN_STBC_PROJECT_ROOT)
        / "game/data/Models/Ships/Galaxy/Galaxy.nif";
    if (fs::exists(p)) return p;
    return "/Users/mward/Documents/Projects/open_stbc/game/data/Models/Ships/Galaxy/Galaxy.nif";
}

fs::path fed_high_path() {
    fs::path p = fs::path(OPEN_STBC_PROJECT_ROOT)
        / "game/data/Models/SharedTextures/FedShips/High";
    if (fs::exists(p)) return p;
    return "/Users/mward/Documents/Projects/open_stbc/game/data/Models/SharedTextures/FedShips/High";
}

fs::path fed_medium_path() {
    fs::path p = fs::path(OPEN_STBC_PROJECT_ROOT)
        / "game/data/Models/SharedTextures/FedShips/Medium";
    if (fs::exists(p)) return p;
    return "/Users/mward/Documents/Projects/open_stbc/game/data/Models/SharedTextures/FedShips/Medium";
}

assets::AssetCache::Config stub_config() {
    assets::AssetCache::Config cfg;
    cfg.texture_uploader = [](const assets::Image&, bool) {
        return assets::Texture(/*id=*/0, 1, 1, false);
    };
    cfg.mesh_uploader = [](assets::MeshCpu cpu) {
        return assets::Mesh(0, 0, 0,
            static_cast<std::uint32_t>(cpu.indices.size()),
            cpu.material_index, cpu.node_index);
    };
    return cfg;
}

}  // namespace

TEST(AssetCacheTest, LoadSamePathReturnsSameHandle) {
    if (!game_data_present()) GTEST_SKIP() << "game/ not installed";

    assets::AssetCache cache(stub_config());
    auto a = cache.load(galaxy_path(), fed_high_path());
    auto b = cache.load(galaxy_path(), fed_high_path());
    EXPECT_EQ(a.get(), b.get());
}

TEST(AssetCacheTest, DifferentSearchPathThrows) {
    if (!game_data_present()) GTEST_SKIP() << "game/ not installed";

    assets::AssetCache cache(stub_config());
    cache.load(galaxy_path(), fed_high_path());
    EXPECT_THROW(
        cache.load(galaxy_path(), fed_medium_path()),
        assets::AssetError);
}

TEST(AssetCacheTest, EvictDropsCachePin) {
    if (!game_data_present()) GTEST_SKIP() << "game/ not installed";

    assets::AssetCache cache(stub_config());
    auto handle = cache.load(galaxy_path(), fed_high_path());
    cache.evict(galaxy_path());
    // Outstanding handle still keeps the model alive.
    EXPECT_TRUE(handle != nullptr);
}
