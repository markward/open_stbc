// native/src/assets/src/animation_build.h
#pragma once

#include <assets/animation.h>
#include <nif/file.h>

#include <vector>

namespace assets::detail {

/// Walk all NiKeyframeController, NiVisController, NiRollController blocks in
/// the file. Tracks for each target node are merged into a single clip's
/// NodeTrack list. Returns at most one clip in v1 (no clip-name multiplexing
/// — that lives in the future scene-graph runtime).
std::vector<AnimationClip> build_animations(const nif::File& f);

}  // namespace assets::detail
