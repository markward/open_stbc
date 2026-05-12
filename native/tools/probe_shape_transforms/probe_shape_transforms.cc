// native/tools/probe_shape_transforms/probe_shape_transforms.cc
//
// Investigation tool: walks a directory of NIFs and reports every
// NiTriShape whose `av` block carries a non-identity translation,
// rotation, or scale. The goal is to find ships where mesh chunks
// (saucers, pylons, nacelles) carry their offset on the NiTriShape
// rather than on a parent NiNode. Our build_mesh_cpu currently
// ignores NiTriShape.av — non-identity shapes would render at their
// parent NiNode's origin, producing visible misalignment.
//
// Usage:
//   probe_shape_transforms <root-directory>
//
// Output: one line per non-identity NiTriShape, plus a summary.

#include <nif/block.h>
#include <nif/file.h>

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <variant>

namespace fs = std::filesystem;

namespace {

bool is_nif(const fs::path& p) {
    auto ext = p.extension().string();
    for (auto& c : ext) c = static_cast<char>(std::tolower(c));
    return ext == ".nif";
}

bool is_identity_translation(const nif::Vec3& t, float eps = 1e-5f) {
    return std::abs(t.x) < eps && std::abs(t.y) < eps && std::abs(t.z) < eps;
}

bool is_identity_rotation(const nif::Mat3x3& r, float eps = 1e-5f) {
    const float ident[9] = {1, 0, 0, 0, 1, 0, 0, 0, 1};
    for (int i = 0; i < 9; ++i) {
        if (std::abs(r.m[i] - ident[i]) > eps) return false;
    }
    return true;
}

bool is_identity_scale(float s, float eps = 1e-5f) {
    return std::abs(s - 1.0f) < eps;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: %s <root-directory>\n", argv[0]);
        return 2;
    }
    fs::path root = argv[1];
    if (!fs::is_directory(root)) {
        std::fprintf(stderr, "not a directory: %s\n", root.string().c_str());
        return 2;
    }

    std::size_t total_files = 0;
    std::size_t total_shapes = 0;
    std::size_t non_id_trans = 0;
    std::size_t non_id_rot = 0;
    std::size_t non_id_scale = 0;
    std::size_t files_with_non_id = 0;

    for (auto& entry : fs::recursive_directory_iterator(root)) {
        if (!entry.is_regular_file()) continue;
        if (!is_nif(entry.path())) continue;
        ++total_files;
        nif::File f;
        try {
            f = nif::load(entry.path());
        } catch (const std::exception& e) {
            std::printf("ERR %s: %s\n", entry.path().string().c_str(), e.what());
            continue;
        }
        bool printed_header = false;
        for (std::size_t i = 0; i < f.blocks.size(); ++i) {
            auto* shape = std::get_if<nif::NiTriShape>(&f.blocks[i]);
            if (!shape) continue;
            ++total_shapes;
            bool nt = !is_identity_translation(shape->av.translation);
            bool nr = !is_identity_rotation(shape->av.rotation);
            bool ns = !is_identity_scale(shape->av.scale);
            if (!nt && !nr && !ns) continue;
            non_id_trans += nt ? 1 : 0;
            non_id_rot   += nr ? 1 : 0;
            non_id_scale += ns ? 1 : 0;
            if (!printed_header) {
                std::printf("\n%s\n", entry.path().string().c_str());
                printed_header = true;
                ++files_with_non_id;
            }
            const auto& t = shape->av.translation;
            std::printf("  block %zu  name=%-20s  t=[%.2f %.2f %.2f]%s%s\n",
                        i,
                        shape->av.obj.name.c_str(),
                        t.x, t.y, t.z,
                        nr ? "  rot!=I" : "",
                        ns ? "  scale!=1" : "");
        }
    }

    std::printf("\n--- summary ---\n");
    std::printf("files scanned       : %zu\n", total_files);
    std::printf("files with non-id   : %zu\n", files_with_non_id);
    std::printf("NiTriShape total    : %zu\n", total_shapes);
    std::printf("  non-id translation: %zu\n", non_id_trans);
    std::printf("  non-id rotation   : %zu\n", non_id_rot);
    std::printf("  non-id scale      : %zu\n", non_id_scale);
    return 0;
}
