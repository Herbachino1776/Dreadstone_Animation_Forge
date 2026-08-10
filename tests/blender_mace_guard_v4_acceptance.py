"""Blender 5.1 runtime acceptance for Forge 4.0 mace guards."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import animation_library  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def make_bone(edit_bones, name, head, tail, parent=None):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    bone.parent = parent
    return bone


def make_guard_rig():
    bpy.ops.object.armature_add(enter_editmode=True)
    armature = bpy.context.active_object
    armature.name = "DAF_4_Guard_Acceptance_Rig"
    edit_bones = armature.data.edit_bones
    edit_bones.remove(edit_bones[0])

    root = make_bone(edit_bones, "root", (0, 0, 0.0), (0, 0, 0.8))
    hips = make_bone(edit_bones, "body", (0, 0, 0.8), (0, 0, 1.1), root)
    spine = make_bone(edit_bones, "body_top0", (0, 0, 1.1), (0, 0, 1.55), hips)
    spine_mid = make_bone(
        edit_bones, "body_top1", (0, 0, 1.55), (0, 0, 1.75), spine
    )
    chest = make_bone(edit_bones, "body_top2", (0, 0, 1.75), (0, 0, 1.95), spine_mid)
    neck = make_bone(edit_bones, "neck", (0, 0, 1.95), (0, 0, 2.15), chest)
    make_bone(edit_bones, "head", (0, 0, 2.15), (0, 0, 2.48), neck)

    thigh_l = make_bone(edit_bones, "leg_left_top", (-0.16, 0, 0.88), (-0.16, 0, 0.34), hips)
    shin_l = make_bone(edit_bones, "leg_left_bot", (-0.16, 0, 0.34), (-0.16, 0, -0.22), thigh_l)
    make_bone(edit_bones, "leg_left_foot", (-0.16, 0, -0.22), (-0.16, 0.28, -0.22), shin_l)
    thigh_r = make_bone(edit_bones, "leg_right_top", (0.16, 0, 0.88), (0.16, 0, 0.34), hips)
    shin_r = make_bone(edit_bones, "leg_right_bot", (0.16, 0, 0.34), (0.16, 0, -0.22), thigh_r)
    make_bone(edit_bones, "leg_right_foot", (0.16, 0, -0.22), (0.16, 0.28, -0.22), shin_r)

    shoulder_l = make_bone(
        edit_bones, "shoulder_left", (0, 0, 1.88), (-0.28, 0, 1.88), chest
    )
    upper_l = make_bone(
        edit_bones, "arm_left_top", (-0.28, 0, 1.88), (-0.78, 0, 1.78), shoulder_l
    )
    lower_l = make_bone(
        edit_bones, "arm_left_bot", (-0.78, 0, 1.78), (-1.20, 0, 1.70), upper_l
    )
    make_bone(
        edit_bones, "arm_left_hand", (-1.20, 0, 1.70), (-1.42, 0, 1.67), lower_l
    )

    shoulder_r = make_bone(
        edit_bones, "shoulder_right", (0, 0, 1.88), (0.28, 0, 1.88), chest
    )
    upper_r = make_bone(
        edit_bones, "arm_right_top", (0.28, 0, 1.88), (0.78, 0, 1.78), shoulder_r
    )
    lower_r = make_bone(
        edit_bones, "arm_right_bot", (0.78, 0, 1.78), (1.20, 0, 1.70), upper_r
    )
    make_bone(
        edit_bones, "arm_right_hand", (1.20, 0, 1.70), (1.42, 0, 1.67), lower_r
    )

    bpy.ops.object.mode_set(mode="POSE")
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
    bpy.ops.object.mode_set(mode="OBJECT")
    armature["sbf_canonical_rig_version"] = "SBF_HUMANOID_YPLUS_V1"
    armature["sbf_forward_axis"] = "+Y"
    armature["sbf_up_axis"] = "+Z"
    armature["sbf_root_bone"] = "root"
    armature["sbf_rig_contract_version"] = 1
    armature["sbf_unit_scale_meters"] = 1.0
    armature["sbf_orientation_revision"] = 1
    armature["sbf_orientation_state"] = "CANONICAL_Y_PLUS"
    armature["sbf_bone_mapping"] = json.dumps({
        "root": "root",
        "pelvis": "body",
        "spine_lower": "body_top0",
        "spine_middle": "body_top1",
        "chest": "body_top2",
        "neck": "neck",
        "head": "head",
        "shoulder_left": "shoulder_left",
        "upper_arm_left": "arm_left_top",
        "lower_arm_left": "arm_left_bot",
        "hand_left": "arm_left_hand",
        "shoulder_right": "shoulder_right",
        "upper_arm_right": "arm_right_top",
        "lower_arm_right": "arm_right_bot",
        "hand_right": "arm_right_hand",
        "upper_leg_left": "leg_left_top",
        "lower_leg_left": "leg_left_bot",
        "foot_left": "leg_left_foot",
        "upper_leg_right": "leg_right_top",
        "lower_leg_right": "leg_right_bot",
        "foot_right": "leg_right_foot",
    }, sort_keys=True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    return armature


def main():
    addon.register()
    context = bpy.context
    armature = make_guard_rig()
    settings = context.scene.daf_settings
    settings.mace_guard_style = "COWERING"
    settings.mace_guard_raise_seconds = 0.80
    settings.mace_guard_hold_seconds = 2.25
    settings.mace_guard_recovery_seconds = 0.75
    settings.left_elbow_flex = 7.0
    settings.right_elbow_flex = 11.0

    guards = addon.generate_all_mace_guard_actions(context)
    require(len(guards) == 3, "Forge 4.0 did not generate all three guard variants.")
    validation = addon.validate_all_mace_guard_actions(context)
    require(
        validation["status"] == "PASS",
        "Forge 4.0 guard validation failed: " + "; ".join(validation["errors"]),
    )
    for action in guards:
        marker_names = {marker.name for marker in action.pose_markers}
        require(
            {
                "Brace_Start",
                "Recognition",
                "Covering",
                "Guard_Active",
                "Guard_Hold_End",
                "Brace_End",
            }
            <= marker_names,
            f"{action.name} is missing Forge 4.0 guard timing markers.",
        )
        require(
            str(action.get("dsb_guard_style", "")) == "COWERING",
            f"{action.name} lost its cowering style metadata.",
        )
        snapshot = json.loads(
            str(action[animation_library.CLIP_SETTINGS_PROPERTY])
        )
        for property_name in (
            "left_elbow_flex",
            "right_elbow_flex",
            "mace_guard_style",
            "mace_guard_arm_cover",
            "mace_guard_elbow_flex",
            "mace_guard_arm_wrap",
        ):
            require(
                property_name in snapshot,
                f"{action.name} did not snapshot {property_name}.",
            )

    two_arm = guards[0]
    markers = {marker.name: int(marker.frame) for marker in two_arm.pose_markers}
    fps = context.scene.render.fps / context.scene.render.fps_base
    protected_hold = (
        markers["Guard_Hold_End"] - markers["Guard_Active"]
    ) / fps
    require(
        protected_hold >= 2.20,
        "The requested longer protected hold was shortened.",
    )

    # Spatial head coverage can guide the user, but it may never make an
    # otherwise valid animation fail or block a later pack export.
    record = addon.validate_mace_guard_action(
        context,
        two_arm,
        armature,
        addon.map_bones(armature, settings),
    )
    require(record["status"] == "PASS", "Coverage guidance became a hard failure.")
    require("warnings" in record and "coverage" in record, "Coverage guidance is missing.")

    # The original attack-like generator result remains deliberately
    # selectable after the default changes to a natural cower.
    settings.mace_guard_style = "ZOMBIE_ATTACK"
    zombie = addon.generate_mace_guard_action(context, "MACE_GUARD_TWO_ARM")
    require(
        str(zombie.get("dsb_guard_style", "")) == "ZOMBIE_ATTACK",
        "The Zombie-Insect Attack legacy generator style was not preserved.",
    )

    report = {
        "status": "PASS",
        "forgeVersion": "5.2.0",
        "guardCount": len(guards),
        "protectedHoldSeconds": protected_hold,
        "coverageWarnings": len(record["warnings"]),
        "elbowPolish": [
            settings.left_elbow_flex,
            settings.right_elbow_flex,
        ],
        "legacyGeneratorStyle": str(zombie["dsb_guard_style"]),
    }
    print("MACE_GUARD_V4_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
