// native/src/assets/include/assets/asset.h
#pragma once

#include <memory>

namespace assets {

// Forward declarations of public domain types defined in later headers.
struct Image;
class  Texture;
struct MeshCpu;
class  Mesh;
struct Material;
struct Bone;
struct Skeleton;
struct AnimationClip;
struct Node;
struct Model;

using ModelHandle = std::shared_ptr<const Model>;

}  // namespace assets
