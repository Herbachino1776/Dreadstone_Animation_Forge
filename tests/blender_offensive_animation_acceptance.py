"""Blender 5.1 offensive Action and persistent socket authoring acceptance."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import (  # noqa: E402
    animation_library,
    attachment_sockets,
    offensive_actions,
)
from dreadstone_animation_forge.anatomy import skin_and_bones  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def make_canonical_armature():
    bpy.ops.object.armature_add(enter_editmode=True)
    armature = bpy.context.active_object
    armature.name = attachment_sockets.RUNTIME_ARMATURE_NAME
    hierarchy = skin_and_bones.CANONICAL_HUMANOID_PARENTS
    first = armature.data.edit_bones[0]
    first.name = "root"
    first.head = (0.0, 0.0, 0.0)
    first.tail = (0.0, 0.0, 0.1)
    created = {"root": first}
    for index, (bone_name, parent_name) in enumerate(hierarchy.items()):
        if bone_name == "root":
            continue
        bone = armature.data.edit_bones.new(bone_name)
        bone.parent = created[parent_name]
        side = -0.12 if "left" in bone_name else 0.12 if "right" in bone_name else 0.0
        bone.head = (side, 0.01 * index, 0.10 + 0.08 * index)
        bone.tail = (side, 0.01 * index + 0.025, 0.18 + 0.08 * index)
        created[bone_name] = bone
    bpy.ops.object.mode_set(mode="POSE")
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
    bpy.ops.object.mode_set(mode="OBJECT")
    sbf_mapping = {
        sbf_role: skin_and_bones.CANONICAL_HUMANOID_MAPPING[forge_role]
        for sbf_role, forge_role in skin_and_bones.SBF_TO_FORGE_ROLE.items()
    }
    armature[skin_and_bones.SBF_RIG_VERSION_PROPERTY] = skin_and_bones.SBF_CANONICAL_RIG_VERSION
    armature[skin_and_bones.SBF_FORWARD_AXIS_PROPERTY] = "+Y"
    armature[skin_and_bones.SBF_UP_AXIS_PROPERTY] = "+Z"
    armature[skin_and_bones.SBF_ROOT_BONE_PROPERTY] = "root"
    armature[skin_and_bones.SBF_ORIENTATION_REVISION_PROPERTY] = 1
    armature[skin_and_bones.SBF_ORIENTATION_STATE_PROPERTY] = "CANONICAL_Y_PLUS"
    armature[skin_and_bones.SBF_RIG_CONTRACT_VERSION_PROPERTY] = 1
    armature[skin_and_bones.SBF_UNIT_SCALE_METERS_PROPERTY] = 1.0
    armature[skin_and_bones.SBF_BONE_MAPPING_PROPERTY] = json.dumps(sbf_mapping)
    return armature


def rest_snapshot(armature):
    return {
        bone.name: (
            bone.parent.name if bone.parent else "",
            tuple(value for row in bone.matrix_local for value in row),
        )
        for bone in armature.data.bones
    }


def matrix_values(matrix):
    return tuple(round(float(value), 7) for row in matrix for value in row)


def transform_values(obj):
    return {
        "location": tuple(round(float(value), 7) for value in obj.location),
        "rotationMode": obj.rotation_mode,
        "rotationQuaternion": tuple(round(float(value), 7) for value in obj.rotation_quaternion),
        "rotationEuler": tuple(round(float(value), 7) for value in obj.rotation_euler),
        "scale": tuple(round(float(value), 7) for value in obj.scale),
        "parentInverse": matrix_values(obj.matrix_parent_inverse),
    }


def curve_signature(action):
    return tuple(
        round(float(point.co.y), 6)
        for curve in addon.iter_action_fcurves(action)
        for point in curve.keyframe_points
    )


def main():
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    context = bpy.context
    armature = make_canonical_armature()
    bpy.ops.object.select_all(action='DESELECT')
    armature.select_set(True)
    context.view_layer.objects.active = armature
    context.scene.render.fps = 24
    context.scene.render.fps_base = 1.0

    bones_before = rest_snapshot(armature)
    action_count_before = len(bpy.data.actions)
    helpers = attachment_sockets.ensure_standard_sockets(armature)
    require(len(helpers) == 2, "The two standard hand sockets were not created.")
    right = next(helper for helper in helpers if helper["dsb_attachment_socket_role"] == "MAIN_HAND_R")
    authored = right.matrix_world.copy()
    authored.translation.y += 0.043
    right.matrix_world = authored
    right_name = right.name
    authored_values = matrix_values(right.matrix_world)
    attachment_sockets.ensure_standard_sockets(armature)
    require(matrix_values(right.matrix_world) == authored_values, "Idempotent ensure reset the grip transform.")
    persisted_transform = transform_values(right)
    require(rest_snapshot(armature) == bones_before, "Socket authoring changed canonical rest bones.")
    require(len(bpy.data.actions) == action_count_before, "Socket authoring changed the Action inventory.")

    drafts = addon.generate_humanoid_offensive_suite(context)
    require(len(drafts) == 8, "The offensive generator did not create eight drafts.")
    draft_validation = addon.validate_all_offensive_actions(
        context,
        require_approved=False,
        available_socket_roles={"MAIN_HAND_R", "MAIN_HAND_L"},
    )
    require(draft_validation["status"] == "PASS", "; ".join(draft_validation["errors"]))
    require(
        not any(curve.data_path.endswith(".scale") for action in drafts for curve in addon.iter_action_fcurves(action)),
        "An offensive generator animated bone scale.",
    )

    selected_kind = "ATTACK_SLASH_RTL_ONE_HAND"
    settings = context.scene.daf_settings
    settings.offensive_preview_kind = selected_kind
    baseline_signature = curve_signature(bpy.data.actions[offensive_actions.OFFENSIVE_ACTION_VARIANTS[selected_kind]["draftName"]])
    settings.offensive_windup_seconds = 0.80
    settings.offensive_active_seconds = 0.22
    settings.offensive_recovery_seconds = 0.90
    settings.offensive_anticipation_strength = 1.35
    settings.offensive_strike_strength = 1.40
    settings.offensive_follow_through = 1.25
    settings.offensive_torso_power = 1.50
    settings.offensive_arm_reach = 1.18
    settings.offensive_elbow_flex = 0.82
    settings.offensive_wrist_action = 1.30
    settings.offensive_stance_compression = 1.20
    customized = addon.generate_selected_offensive_action(context)
    custom_recipe = offensive_actions.read_offensive_recipe(customized)
    customized_signature = curve_signature(customized)
    require(custom_recipe is not None, "The custom slider recipe was not stored on the draft.")
    require(abs(custom_recipe["windupSeconds"] - 0.80) < 1.0e-6, "The WINDUP slider did not reach the draft recipe.")
    require(customized_signature != baseline_signature, "Motion sliders did not change generated keyframes.")
    custom_metadata = offensive_actions.read_offensive_metadata(customized)
    require(custom_metadata["phases"]["windup"]["endSeconds"] == 0.791667, "Custom timing did not drive phase frames.")

    regenerated = addon.generate_humanoid_offensive_suite(context)
    regenerated_custom = bpy.data.actions[offensive_actions.OFFENSIVE_ACTION_VARIANTS[selected_kind]["draftName"]]
    require(offensive_actions.read_offensive_recipe(regenerated_custom) == custom_recipe, "Suite refresh lost a character recipe.")
    require(curve_signature(regenerated_custom) == customized_signature, "Suite refresh changed the saved custom motion.")
    drafts = regenerated

    try:
        addon.approve_draft_action(context, selected_kind)
    except RuntimeError as exc:
        require("Preview this offensive draft" in str(exc), "Approval failed for the wrong pre-preview reason.")
    else:
        raise RuntimeError("An unpreviewed offensive draft was approved.")

    approved = []
    preview_results = []
    for kind in offensive_actions.OFFENSIVE_ACTION_VARIANTS:
        settings.offensive_preview_kind = kind
        preview_results.append(addon.preview_offensive_action(context, kind, start_playback=False))
        approved.append(addon.approve_draft_action(context, kind))
    require(len({action.name for action in approved}) == 8, "Approved Action names are not unique.")
    require(all(result["previewCount"] == 1 for result in preview_results), "A draft preview was not recorded exactly once.")
    approved_validation = addon.validate_all_offensive_actions(
        context,
        require_approved=True,
        available_socket_roles={"MAIN_HAND_R", "MAIN_HAND_L"},
    )
    require(approved_validation["status"] == "PASS", "; ".join(approved_validation["errors"]))
    identities = {
        offensive_actions.read_offensive_metadata(action)["combatActionId"]
        for action in approved
    }
    require(len(identities) == 8, "Approved combat Action IDs are not unique.")
    for action in approved:
        metadata = offensive_actions.read_offensive_metadata(action)
        start, end = animation_library.action_frame_bounds(action)
        expected_duration = (end - start) / 24.0
        require(abs(metadata["clipDurationSeconds"] - expected_duration) < 1.0e-5, "Phase duration drifted from Action frames.")
        require(action["dsb_approved_frame_start"] == int(start), "Approved start frame is wrong.")
        require(action["dsb_approved_frame_end"] == int(end), "Approved end frame is wrong.")
        require(bool(action["dsb_offensive_previewed_before_approval"]), "Approved Action lost preview proof.")
        require(offensive_actions.read_offensive_recipe(action) is not None, "Approved Action lost its character recipe.")

    socket_contract = attachment_sockets.runtime_socket_contract(runtime_rig=armature)
    require(socket_contract["socketCount"] == 2, "The sidecar socket inventory is incomplete.")
    require(socket_contract["runtimeBoneCount"] == 21, "Socket authoring changed the canonical bone count.")

    output = Path(tempfile.mkdtemp(prefix="daf_offensive_acceptance_"))
    blend_path = output / "offensive_socket_persistence.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    reloaded_rig = bpy.data.objects[attachment_sockets.RUNTIME_ARMATURE_NAME]
    reloaded_right = bpy.data.objects[right_name]
    require(transform_values(reloaded_right) == persisted_transform, "Reload changed the authored grip transform.")
    require(rest_snapshot(reloaded_rig) == bones_before, "Reload changed canonical rest bones.")
    require(
        len([action for action in bpy.data.actions if action.get(offensive_actions.OFFENSIVE_ACTION_PROPERTY)]) == 8,
        "Reload lost offensive Action metadata.",
    )
    reloaded_custom = next(
        action for action in bpy.data.actions
        if action.get("dsb_approved_kind") == selected_kind
    )
    require(offensive_actions.read_offensive_recipe(reloaded_custom) == custom_recipe, "Reload lost the custom slider recipe.")

    report = {
        "status": "PASS",
        "blenderVersion": bpy.app.version_string,
        "forgeVersion": ".".join(str(value) for value in addon.bl_info["version"]),
        "draftCount": len(drafts),
        "approvedCount": len(approved),
        "combatActionIds": sorted(identities),
        "socketCount": socket_contract["socketCount"],
        "runtimeBoneCount": socket_contract["runtimeBoneCount"],
        "noScaleAnimation": True,
        "restSkeletonPreserved": True,
        "socketTransformPersisted": True,
        "customSliderRecipePersisted": True,
        "previewRequiredBeforeApproval": True,
        "blend": str(blend_path),
    }
    print("OFFENSIVE_ANIMATION_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
