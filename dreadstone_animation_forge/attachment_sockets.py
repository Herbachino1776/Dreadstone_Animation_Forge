"""Managed Blender Empty authoring and export for runtime attachment sockets."""

from __future__ import annotations

from copy import deepcopy

import bpy
from bpy.types import Operator
from mathutils import Matrix, Quaternion, Vector

from .attachment_socket_contract import (
    ATTACHMENT_SOCKET_COLLECTION,
    ATTACHMENT_SOCKET_HELPER_PREFIX,
    ATTACHMENT_SOCKET_SCHEMA,
    RUNTIME_ARMATURE_NAME,
    STANDARD_SOCKET_SPECS,
    validate_socket_contract,
)


def _collection():
    collection = bpy.data.collections.get(ATTACHMENT_SOCKET_COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new(ATTACHMENT_SOCKET_COLLECTION)
    if not any(collection == child for scene in bpy.data.scenes for child in scene.collection.children):
        bpy.context.scene.collection.children.link(collection)
    return collection


def _owned_helpers():
    return [obj for obj in bpy.data.objects if bool(obj.get("dsb_attachment_socket_owned", False))]


def _helper_for_socket(socket_id):
    matches = [obj for obj in _owned_helpers() if str(obj.get("dsb_attachment_socket_id", "")) == socket_id]
    if len(matches) > 1:
        raise RuntimeError(f"Attachment socket {socket_id!r} has duplicate managed helpers.")
    return matches[0] if matches else None


def _pose_bone_world(runtime_rig, bone_name):
    pose_bone = runtime_rig.pose.bones.get(bone_name)
    if pose_bone is None:
        raise RuntimeError(f"{RUNTIME_ARMATURE_NAME} is missing required socket parent bone {bone_name!r}.")
    return runtime_rig.matrix_world @ pose_bone.matrix


def _initial_helper_world(runtime_rig, bone_name):
    pose_bone = runtime_rig.pose.bones[bone_name]
    local = Matrix.Translation((0.0, max(float(pose_bone.length) * 0.52, 0.015), 0.0))
    return _pose_bone_world(runtime_rig, bone_name) @ local


def _stamp_helper(helper, spec):
    helper["dsb_attachment_socket_owned"] = True
    helper["dsb_attachment_socket_schema"] = ATTACHMENT_SOCKET_SCHEMA
    helper["dsb_attachment_socket_id"] = spec["socketId"]
    helper["dsb_attachment_socket_role"] = spec["semanticRole"]
    helper["dsb_attachment_socket_parent_bone"] = spec["parentRuntimeBone"]
    helper["dsb_attachment_socket_enabled"] = True
    helper["dsb_attachment_socket_exportable"] = True
    helper["dsb_damage_role"] = "attachment_socket_helper"
    helper.empty_display_type = 'ARROWS'
    helper.empty_display_size = 0.12
    helper.show_name = True
    helper.show_in_front = True


def ensure_standard_sockets(runtime_rig=None):
    """Create or repair the standard helpers without altering an authored transform."""

    runtime_rig = runtime_rig or bpy.data.objects.get(RUNTIME_ARMATURE_NAME)
    if runtime_rig is None or runtime_rig.type != 'ARMATURE':
        raise RuntimeError(f"{RUNTIME_ARMATURE_NAME} must exist before ensuring attachment sockets.")
    missing = [spec["parentRuntimeBone"] for spec in STANDARD_SOCKET_SPECS if runtime_rig.data.bones.get(spec["parentRuntimeBone"]) is None]
    if missing:
        raise RuntimeError("Required attachment socket parent bone(s) are missing: " + ", ".join(missing) + ".")
    bone_names_before = tuple(runtime_rig.data.bones.keys())
    rest_before = {bone.name: tuple(value for row in bone.matrix_local for value in row) for bone in runtime_rig.data.bones}
    action_count_before = len(bpy.data.actions)
    collection = _collection()
    helpers = []
    for spec in STANDARD_SOCKET_SPECS:
        helper = _helper_for_socket(spec["socketId"])
        authored_world = helper.matrix_world.copy() if helper is not None else _initial_helper_world(runtime_rig, spec["parentRuntimeBone"])
        if helper is None:
            helper = bpy.data.objects.new(spec["helperName"], None)
            collection.objects.link(helper)
        elif collection.objects.get(helper.name) is None:
            collection.objects.link(helper)
        _stamp_helper(helper, spec)
        if helper.parent != runtime_rig or helper.parent_type != 'BONE' or helper.parent_bone != spec["parentRuntimeBone"]:
            helper.parent = runtime_rig
            helper.parent_type = 'BONE'
            helper.parent_bone = spec["parentRuntimeBone"]
        helper.matrix_world = authored_world
        helpers.append(helper)
    if tuple(runtime_rig.data.bones.keys()) != bone_names_before:
        raise RuntimeError("Attachment socket authoring changed the runtime skeleton inventory.")
    for bone in runtime_rig.data.bones:
        current = tuple(value for row in bone.matrix_local for value in row)
        if current != rest_before[bone.name]:
            raise RuntimeError(f"Attachment socket authoring changed rest transform for bone {bone.name!r}.")
    if len(bpy.data.actions) != action_count_before:
        raise RuntimeError("Attachment socket authoring changed the Action inventory.")
    return helpers


def socket_record(helper, runtime_rig):
    socket_id = str(helper.get("dsb_attachment_socket_id", ""))
    parent_bone = str(helper.get("dsb_attachment_socket_parent_bone", ""))
    if helper.parent != runtime_rig or helper.parent_type != 'BONE' or helper.parent_bone != parent_bone:
        raise RuntimeError(f"Attachment socket {socket_id or helper.name!r} is not parented to its declared runtime bone.")
    parent_world = _pose_bone_world(runtime_rig, parent_bone)
    local = parent_world.inverted_safe() @ helper.matrix_world
    position, quaternion, scale = local.decompose()
    if any(abs(float(value) - 1.0) > 1.0e-5 for value in scale):
        raise RuntimeError(f"Attachment socket {socket_id!r} uses unsupported local scale; apply scale to the helper.")
    quaternion = Quaternion(quaternion).normalized()
    return {
        "socketId": socket_id,
        "semanticRole": str(helper.get("dsb_attachment_socket_role", "")),
        "parentRuntimeBone": parent_bone,
        "localPosition": [round(float(value), 7) for value in Vector(position)],
        "localQuaternion": [
            round(float(quaternion.x), 7),
            round(float(quaternion.y), 7),
            round(float(quaternion.z), 7),
            round(float(quaternion.w), 7),
        ],
        "enabled": bool(helper.get("dsb_attachment_socket_enabled", True)),
        "exportable": bool(helper.get("dsb_attachment_socket_exportable", True)),
    }


def runtime_socket_contract(state=None, *, runtime_rig=None):
    runtime_name = str((state or {}).get("authoring_rig", RUNTIME_ARMATURE_NAME))
    runtime_rig = runtime_rig or bpy.data.objects.get(runtime_name)
    if runtime_rig is None or runtime_rig.type != 'ARMATURE':
        raise RuntimeError(f"Runtime attachment sockets require {RUNTIME_ARMATURE_NAME}.")
    helpers = _owned_helpers()
    records = [socket_record(helper, runtime_rig) for helper in helpers]
    records = [record for record in records if record["enabled"] and record["exportable"]]
    records.sort(key=lambda record: record["socketId"])
    payload = {
        "schema": ATTACHMENT_SOCKET_SCHEMA,
        "runtimeArmature": RUNTIME_ARMATURE_NAME,
        "runtimeBoneCount": len(runtime_rig.data.bones),
        "socketCount": len(records),
        "sockets": records,
    }
    errors = validate_socket_contract(payload, runtime_rig.data.bones.keys())
    if errors:
        raise RuntimeError("Attachment socket validation failed: " + " ".join(errors))
    return deepcopy(payload)


class DAF_OT_ensure_runtime_attachment_sockets(Operator):
    bl_idname = "daf.ensure_runtime_attachment_sockets"
    bl_label = "Create / Repair Runtime Hand Sockets"
    bl_description = "Create or repair Forge-owned hand socket Empty frames on DSB_DAMAGE_RIG without adding bones"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, _context):
        try:
            helpers = ensure_standard_sockets()
            bpy.ops.object.select_all(action='DESELECT')
            for helper in helpers:
                helper.select_set(True)
            if helpers:
                bpy.context.view_layer.objects.active = helpers[0]
            self.report({'INFO'}, f"Ensured {len(helpers)} runtime attachment socket helpers; no bones were added.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


CLASSES = (DAF_OT_ensure_runtime_attachment_sockets,)


__all__ = (
    "ATTACHMENT_SOCKET_COLLECTION",
    "ATTACHMENT_SOCKET_HELPER_PREFIX",
    "ATTACHMENT_SOCKET_SCHEMA",
    "CLASSES",
    "RUNTIME_ARMATURE_NAME",
    "STANDARD_SOCKET_SPECS",
    "ensure_standard_sockets",
    "runtime_socket_contract",
    "socket_record",
    "validate_socket_contract",
)
