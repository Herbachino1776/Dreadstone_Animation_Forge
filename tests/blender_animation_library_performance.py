"""Repeatable Blender benchmark for VIP Animation Library redraw services.

Run from the repository root:

    blender --background --factory-startup \
      --python tests/blender_animation_library_performance.py -- \
      --output build/animation_library_performance.json

The synthetic rig and Actions exercise inventory filtering, compatibility,
selected-clip resolution, and summary metrics without making artistic claims.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import animation_library  # noqa: E402
from dreadstone_animation_forge.anatomy import persistence  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--actions", type=int, default=24)
    parser.add_argument("--bones", type=int, default=20)
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--samples", type=int, default=7)
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(values)


def make_armature(bone_count):
    data = bpy.data.armatures.new("DAF_Performance_Rig_Data")
    armature = bpy.data.objects.new("DAF_Performance_Rig", data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    parent = None
    for index in range(bone_count):
        bone = data.edit_bones.new(f"bone_{index:03d}")
        bone.head = (0.0, 0.0, index * 0.1)
        bone.tail = (0.0, 0.0, (index + 1) * 0.1)
        bone.parent = parent
        bone.use_connect = parent is not None
        parent = bone
    bpy.ops.object.mode_set(mode="POSE")
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.animation_data_create()
    persistence.store_metadata(
        armature,
        persistence.legacy_humanoid_metadata(
            {"hips": "bone_000", "head": f"bone_{bone_count - 1:03d}"}
        ),
    )
    return armature


def make_actions(armature, settings, action_count, frame_count):
    result = []
    for action_index in range(action_count):
        action = bpy.data.actions.new(f"DAF_Performance_Action_{action_index:03d}")
        armature.animation_data.action = action
        for frame_index in range(frame_count):
            frame = 1 + frame_index * 6
            for bone_index, bone in enumerate(armature.pose.bones):
                scale = (action_index + 1) * (bone_index + 1) * 0.0001
                bone.location.x = scale * frame_index
                bone.rotation_euler.z = scale * (frame_index + 1)
                bone.keyframe_insert("location", index=0, frame=frame)
                bone.keyframe_insert("rotation_euler", index=2, frame=frame)
        animation_library.mark_approved(
            action,
            armature,
            settings,
            "WALK" if action_index % 2 == 0 else "ATTACK",
        )
        result.append(action)
    armature.animation_data.action = result[-1]
    animation_library.select_action(settings, result[-1])
    return result


def timed_samples(callback, sample_count):
    callback()
    callback()
    durations = []
    checksum = None
    for _index in range(sample_count):
        started = time.perf_counter()
        checksum = callback()
        durations.append((time.perf_counter() - started) * 1000.0)
    return {
        "durationsMs": [round(value, 6) for value in durations],
        "medianMs": round(statistics.median(durations), 6),
        "minimumMs": round(min(durations), 6),
        "maximumMs": round(max(durations), 6),
        "checksum": checksum,
    }


def main():
    args = parse_args()
    addon.register()
    settings = bpy.context.scene.daf_settings
    armature = make_armature(args.bones)
    actions = make_actions(
        armature,
        settings,
        args.actions,
        args.frames,
    )

    def inventory():
        compatible = animation_library.character_actions(
            armature,
            include_drafts=True,
        )
        return [action.name for action in compatible]

    def panel_services():
        compatible = animation_library.character_actions(
            armature,
            include_drafts=True,
        )
        try:
            selected = animation_library.selected_action(
                settings,
                armature,
                include_drafts=True,
                available_actions=compatible,
            )
        except TypeError:
            selected = animation_library.selected_action(
                settings,
                armature,
                include_drafts=True,
            )
        summary = animation_library.action_summary(selected, 24.0)
        return {
            "compatible": len(compatible),
            "selected": selected.name,
            "curves": summary["fcurveCount"],
            "keys": summary["keyframeCount"],
        }

    report = {
        "blenderVersion": bpy.app.version_string,
        "addonVersion": ".".join(str(value) for value in addon.bl_info["version"]),
        "fixture": {
            "actions": len(actions),
            "bones": len(armature.data.bones),
            "framesPerCurve": args.frames,
            "curvesPerAction": len(animation_library.iter_action_fcurves(actions[0])),
        },
        "inventory": timed_samples(inventory, args.samples),
        "panelServices": timed_samples(panel_services, args.samples),
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("DAF_ANIMATION_LIBRARY_PERFORMANCE=" + json.dumps(report, sort_keys=True))
    addon.unregister()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
