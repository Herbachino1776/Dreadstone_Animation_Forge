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

    approved = [
        addon.approve_draft_action(context, kind)
        for kind in offensive_actions.OFFENSIVE_ACTION_VARIANTS
    ]
    require(len({action.name for action in approved}) == 8, "Approved Action names are not unique.")
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
        "blend": str(blend_path),
    }
    print("OFFENSIVE_ANIMATION_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
