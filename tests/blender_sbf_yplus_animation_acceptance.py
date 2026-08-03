"""Live acceptance for the Skin & Bones Y+ humanoid handoff.

Run with::

    blender --background --factory-startup --python \
      tests/blender_sbf_yplus_animation_acceptance.py -- \
      --source-glb <skin-and-bones.glb> --output <report.json>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge.anatomy import persistence  # noqa: E402
from dreadstone_animation_forge.anatomy import skin_and_bones  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(str(message))


def arguments():
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(values)


def select_character(armature):
    bpy.ops.object.select_all(action='DESELECT')
    armature.select_set(True)
    for child in armature.children_recursive:
        child.select_set(True)
    bpy.context.view_layer.objects.active = armature


def pose_point(armature, bone_name, endpoint="head"):
    bone = armature.pose.bones[bone_name]
    value = bone.head if endpoint == "head" else bone.tail
    return armature.matrix_world @ value


def pose_snapshot(armature, mapping):
    return {
        role: [
            round(float(value), 7)
            for row in armature.pose.bones[name].matrix
            for value in row
        ]
        for role, name in mapping.items()
    }


def maximum_snapshot_gap(first, second):
    return max(
        abs(a - b)
        for role in first
        for a, b in zip(first[role], second[role])
    )


def quaternion_gap(first, second):
    return float(
        Quaternion(first).normalized().rotation_difference(
            Quaternion(second).normalized()
        ).angle
    )


def main():
    args = arguments()
    bpy.ops.import_scene.gltf(filepath=str(Path(args.source_glb).resolve()))
    addon.register()
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE']
    require(armatures, "The GLB imported no armature.")
    armature = max(armatures, key=lambda obj: len(obj.data.bones))
    select_character(armature)

    contract = skin_and_bones.require_canonical_yplus(
        armature,
        label="Y+ acceptance",
    )
    settings = bpy.context.scene.daf_settings
    settings.anatomy_profile_override = "AUTO"
    analyze_result = bpy.ops.daf.analyze()
    require("FINISHED" in analyze_result, analyze_result)
    anatomy = persistence.load_metadata(armature)
    require(anatomy is not None, "Analysis metadata was not persisted.")
    require(anatomy["orientation"]["forwardAxis"] == "+Y", anatomy)
    require(
        anatomy.get("canonicalRigVersion")
        == skin_and_bones.SBF_CANONICAL_RIG_VERSION,
        anatomy,
    )
    mapping = anatomy["roleMapping"]

    # Capture a deliberately relaxed left arm as an animation-only base pose.
    # The first Idle sample must reproduce it, while later breathing samples
    # retain that pose and add procedural motion on top.
    settings.pose_polish_enabled = False
    settings.idle_breathing = 1.0
    settings.idle_weight_shift = 1.0
    settings.idle_arm_tuck = 0.0
    edit_base_result = bpy.ops.daf.edit_animation_base_pose(kind="IDLE")
    require("FINISHED" in edit_base_result, edit_base_result)
    require(bpy.context.mode == 'POSE', bpy.context.mode)
    addon.rotate(
        armature,
        mapping,
        "upper_arm_l",
        Vector((0.0, 1.0, 0.0)),
        -14.0,
    )
    captured_left_arm = tuple(
        armature.pose.bones[mapping["upper_arm_l"]].rotation_quaternion
    )
    capture_base_result = bpy.ops.daf.capture_animation_base_pose(kind="IDLE")
    require("FINISHED" in capture_base_result, capture_base_result)
    require(bpy.context.mode == 'OBJECT', bpy.context.mode)
    base_library = json.loads(
        str(armature[addon.ANIMATION_BASE_POSES_PROPERTY])
    )
    base_payload = base_library["poses"]["IDLE"]
    require("root" not in base_payload["bones"], base_payload)

    idle = bpy.data.actions.get(addon.DRAFT_ACTION_NAMES["IDLE"])
    require(idle is not None, "Capturing the base pose generated no Idle Action.")
    require(
        str(idle.get("dsb_animation_base_pose_kind", "")) == "IDLE",
        dict(idle.items()),
    )
    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    first_left_arm = tuple(
        armature.pose.bones[mapping["upper_arm_l"]].rotation_quaternion
    )
    base_pose_first_gap = quaternion_gap(captured_left_arm, first_left_arm)
    require(
        base_pose_first_gap <= 1.0e-5,
        f"Idle did not begin from captured base pose: {base_pose_first_gap}",
    )
    quarter_frame = int(round(
        bpy.context.scene.frame_start
        + (bpy.context.scene.frame_end - bpy.context.scene.frame_start) * 0.25
    ))
    bpy.context.scene.frame_set(quarter_frame)
    quarter_left_arm = tuple(
        armature.pose.bones[mapping["upper_arm_l"]].rotation_quaternion
    )
    base_pose_motion_gap = quaternion_gap(captured_left_arm, quarter_left_arm)
    require(
        base_pose_motion_gap > math.radians(0.1),
        f"Idle motion was not layered over the base pose: {base_pose_motion_gap}",
    )

    # The quick Arm Drop control must lower both hands from the canonical
    # A-pose. This guards the +Y left/right rotation signs.
    clear_base_result = bpy.ops.daf.clear_animation_base_pose(kind="IDLE")
    require("FINISHED" in clear_base_result, clear_base_result)
    settings.idle_breathing = 0.0
    settings.idle_weight_shift = 0.0
    settings.idle_arm_tuck = 0.0
    idle_result = bpy.ops.daf.idle()
    require("FINISHED" in idle_result, idle_result)
    idle = bpy.data.actions.get(addon.DRAFT_ACTION_NAMES["IDLE"])
    require(idle is not None, "Idle Action was not generated.")
    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    hand_rest_z = {
        side: float(pose_point(armature, mapping[f"hand_{side}"], "tail").z)
        for side in ("l", "r")
    }
    settings.idle_arm_tuck = 30.0
    tucked_result = bpy.ops.daf.idle()
    require("FINISHED" in tucked_result, tucked_result)
    idle = bpy.data.actions.get(addon.DRAFT_ACTION_NAMES["IDLE"])
    require(idle is not None, "Arm Drop preview generated no Idle Action.")
    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    hand_tucked_z = {
        side: float(pose_point(armature, mapping[f"hand_{side}"], "tail").z)
        for side in ("l", "r")
    }
    for side in ("l", "r"):
        require(
            hand_tucked_z[side] < hand_rest_z[side] - 0.01,
            f"Arm Drop raised {side} hand: {hand_rest_z} -> {hand_tucked_z}",
        )
    first = pose_snapshot(armature, mapping)
    bpy.context.scene.frame_set(bpy.context.scene.frame_end)
    last = pose_snapshot(armature, mapping)
    idle_gap = maximum_snapshot_gap(first, last)
    require(idle_gap <= 1.0e-5, f"Idle loop endpoint gap: {idle_gap}")
    root = armature.pose.bones[mapping["root"]]
    idle_root_drift = float(root.location.length)
    require(idle_root_drift <= 1.0e-7, f"Idle root drift: {root.location[:]}.")
    settings.pose_polish_enabled = True

    walk_result = bpy.ops.daf.walk()
    require("FINISHED" in walk_result, walk_result)
    walk = bpy.data.actions.get(addon.DRAFT_ACTION_NAMES["WALK"])
    require(walk is not None, "Walk Action was not generated.")
    walk_start, walk_end = addon.action_frame_bounds(walk)
    passing_frame = int(round(walk_start + (walk_end - walk_start) * 0.25))
    bpy.context.scene.frame_set(passing_frame)
    hip = pose_point(armature, mapping["thigh_r"], "head")
    knee = pose_point(armature, mapping["shin_r"], "head")
    ankle = pose_point(armature, mapping["foot_r"], "head")
    knee_forward_offset = float(knee.y - ((hip.y + ankle.y) * 0.5))
    shoulder = pose_point(armature, mapping["upper_arm_r"], "head")
    elbow = pose_point(armature, mapping["lower_arm_r"], "head")
    wrist = pose_point(armature, mapping["hand_r"], "head")
    elbow_backward_offset = float(((shoulder.y + wrist.y) * 0.5) - elbow.y)

    hurt_result = bpy.ops.daf.hurt_left()
    require("FINISHED" in hurt_result, hurt_result)

    deaths = {}
    death_failures = []
    for style in ("CHEST_HOLD", "FACEPLANT", "KNEES_FIRST", "INSTANT_LIMP"):
        settings.collapse_style = style
        result = bpy.ops.daf.collapse()
        if "FINISHED" not in result:
            death_failures.append(f"{style}: operator returned {sorted(result)}")
        action = bpy.data.actions.get(addon.DRAFT_ACTION_NAMES["DEATH"])
        require(action is not None, f"{style} produced no death Action.")
        meshes = [
            obj for obj in armature.children_recursive if obj.type == 'MESH'
        ]
        validation = addon.validate_death_floor_action(
            bpy.context,
            action,
            armature,
            meshes,
            fallback_ground_sink=float(settings.ground_sink),
        )
        if validation["status"] != "PASS":
            death_failures.extend(
                f"{style}: {message}" for message in validation["errors"]
            )
        deaths[style] = {
            "result": sorted(result),
            "groundCarrierBone": str(action.get("dsb_ground_carrier_bone", "")),
            "terminalTorsoHeightRatio": float(
                action.get("dsb_terminal_torso_height_ratio", math.inf)
            ),
            "terminalTorsoRegions": json.loads(
                str(action.get("dsb_torso_contact_regions_json", "{}"))
            ),
            "minimumZ": float(action.get("dsb_ground_minimum_z", math.inf)),
            "validation": validation,
        }

    report = {
        "status": "PASS",
        "blenderVersion": bpy.app.version_string,
        "addonVersion": ".".join(str(value) for value in addon.bl_info["version"]),
        "rigVersion": contract["rigVersion"],
        "forwardAxis": anatomy["orientation"]["forwardAxis"],
        "upAxis": anatomy["orientation"]["upAxis"],
        "rootBone": mapping["root"],
        "mapping": mapping,
        "idle": {
            "action": idle.name,
            "endpointGap": idle_gap,
            "rootDriftM": idle_root_drift,
            "rootMotionPolicy": str(idle.get("dsb_root_motion_policy", "")),
            "basePoseFirstGapRadians": base_pose_first_gap,
            "basePoseMotionGapRadians": base_pose_motion_gap,
            "basePoseBones": len(base_payload["bones"]),
            "armDropHandRestZ": hand_rest_z,
            "armDropHandTuckedZ": hand_tucked_z,
        },
        "walk": {
            "action": walk.name,
            "rightKneeForwardOffsetAtPassingM": knee_forward_offset,
            "rightElbowBackwardOffsetAtPassingM": elbow_backward_offset,
            "rightArmY": {
                "shoulder": float(shoulder.y),
                "elbow": float(elbow.y),
                "wrist": float(wrist.y),
            },
        },
        "hurt": {"result": sorted(hurt_result)},
        "deaths": deaths,
        "deathFailures": death_failures,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SBF_YPLUS_ANIMATION_ACCEPTANCE=" + json.dumps(report, sort_keys=True))
    require(knee_forward_offset > 0.02, report["walk"])
    require(elbow_backward_offset > 0.005, report["walk"])
    require(not death_failures, death_failures)
    for record in deaths.values():
        require(record["groundCarrierBone"] == mapping["root"], record)


if __name__ == "__main__":
    main()
