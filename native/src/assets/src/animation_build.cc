#include "animation_build.h"
#include "link_resolver.h"

#include <nif/block.h>

#include <algorithm>
#include <unordered_map>

namespace assets::detail {

namespace {

/// Find the NiNode whose controller_link points (via link IDs) at the
/// controller at `controller_block_index`.
const nif::NiNode* find_controller_target(
    const nif::File& f,
    std::uint32_t controller_block_index,
    const LinkResolver& resolver)
{
    for (auto& b : f.blocks) {
        if (auto* node = std::get_if<nif::NiNode>(&b)) {
            auto target_idx = resolver.resolve(node->av.obj.controller_link);
            if (target_idx == controller_block_index) return node;
        }
    }
    return nullptr;
}

template <typename DataBlock>
const DataBlock* data_at(const nif::File& f, std::uint32_t block_index) {
    if (block_index >= f.blocks.size()) return nullptr;
    return std::get_if<DataBlock>(&f.blocks[block_index]);
}

void apply_keyframe_data(AnimationClip::NodeTrack& track,
                         const nif::NiKeyframeData& kd,
                         float& clip_duration) {
    for (auto& k : kd.translations.keys) {
        track.translation.push_back({k.time, glm::vec3(k.value.x, k.value.y, k.value.z)});
        clip_duration = std::max(clip_duration, k.time);
    }
    for (auto& k : kd.quaternion_keys) {
        track.rotation.push_back({k.time, glm::quat(k.value.w, k.value.x, k.value.y, k.value.z)});
        clip_duration = std::max(clip_duration, k.time);
    }
    for (auto& k : kd.scales.keys) {
        track.scale.push_back({k.time, k.value});
        clip_duration = std::max(clip_duration, k.time);
    }
}

void apply_vis_data(AnimationClip::NodeTrack& track,
                    const nif::NiVisData& vd,
                    float& clip_duration) {
    for (auto& k : vd.keys) {
        track.visibility.push_back({k.time, k.visible != 0});
        clip_duration = std::max(clip_duration, k.time);
    }
}

void apply_float_data(AnimationClip::NodeTrack& track,
                      const nif::NiFloatData& fd,
                      float& clip_duration) {
    for (auto& k : fd.keys) {
        track.floats.push_back({k.time, k.value});
        clip_duration = std::max(clip_duration, k.time);
    }
}

}  // namespace

std::vector<AnimationClip> build_animations(const nif::File& f) {
    LinkResolver resolver(f);
    std::unordered_map<std::string, AnimationClip::NodeTrack> tracks_by_target;
    float clip_duration = 0.0f;

    for (std::uint32_t i = 0; i < f.blocks.size(); ++i) {
        if (auto* kc = std::get_if<nif::NiKeyframeController>(&f.blocks[i])) {
            auto* target = find_controller_target(f, i, resolver);
            if (!target) continue;
            auto& track = tracks_by_target[target->av.obj.name];
            track.target_node_name = target->av.obj.name;
            auto data_idx = resolver.resolve(kc->data_link);
            if (auto* kd = data_at<nif::NiKeyframeData>(f, data_idx))
                apply_keyframe_data(track, *kd, clip_duration);
        } else if (auto* vc = std::get_if<nif::NiVisController>(&f.blocks[i])) {
            auto* target = find_controller_target(f, i, resolver);
            if (!target) continue;
            auto& track = tracks_by_target[target->av.obj.name];
            track.target_node_name = target->av.obj.name;
            auto data_idx = resolver.resolve(vc->data_link);
            if (auto* vd = data_at<nif::NiVisData>(f, data_idx))
                apply_vis_data(track, *vd, clip_duration);
        } else if (auto* rc = std::get_if<nif::NiRollController>(&f.blocks[i])) {
            auto* target = find_controller_target(f, i, resolver);
            if (!target) continue;
            auto& track = tracks_by_target[target->av.obj.name];
            track.target_node_name = target->av.obj.name;
            auto data_idx = resolver.resolve(rc->data_link);
            if (auto* fd = data_at<nif::NiFloatData>(f, data_idx))
                apply_float_data(track, *fd, clip_duration);
        }
    }

    if (tracks_by_target.empty()) return {};

    AnimationClip clip;
    clip.name = f.source.stem().string();
    clip.duration_seconds = clip_duration;
    for (auto& [_, track] : tracks_by_target) clip.tracks.push_back(std::move(track));
    return {std::move(clip)};
}

}  // namespace assets::detail
