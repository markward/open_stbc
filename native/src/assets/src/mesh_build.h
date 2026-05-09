// native/src/assets/src/mesh_build.h
#pragma once

#include <assets/mesh.h>
#include <nif/block.h>

namespace assets::detail {

/// Build a MeshCpu from a NiTriShape and its referenced NiTriShapeData.
/// `material_index` and `node_index` are stamped into the output.
MeshCpu build_mesh_cpu(
    const nif::NiTriShape& shape,
    const nif::NiTriShapeData& data,
    int material_index,
    int node_index);

}  // namespace assets::detail
