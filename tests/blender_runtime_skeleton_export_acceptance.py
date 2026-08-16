"""Blender 5.1.2 Complete Damage runtime-skeleton export regression.

Run from the repository root:

    blender --background --factory-startup \
      --python tests/blender_runtime_skeleton_export_acceptance.py
"""

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
    damage_authoring,
    deformation_authoring,
    offensive_actions,
    offensive_motion,
    offensive_motion_studio,
    runtime_export,
    variant_authoring,
    variant_family,
)
from dreadstone_animation_forge.anatomy import skin_and_bones  # noqa: E402
from dreadstone_animation_forge.anatomy.skin_and_bones import (  # noqa: E402
    CANONICAL_HUMANOID_PARENTS,
)
from dreadstone_animation_forge.deformation import gltf_validation  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def make_armature(name):
    bpy.ops.object.armature_add(enter_editmode=True, location=(0.0, 0.0, 0.0))
    armature = bpy.context.active_object
    armature.name = name
    first = armature.data.edit_bones[0]
    armature.data.edit_bones.remove(first)
    positions = {
        "root": ((0.0, 0.0, 0.0), (0.0, 0.0, 0.15)),
        "body": ((0.0, 0.0, 0.15), (0.0, 0.0, 0.55)),
        "body_top0": ((0.0, 0.0, 0.55), (0.0, 0.0, 0.82)),
        "body_top1": ((0.0, 0.0, 0.82), (0.0, 0.0, 1.08)),
        "body_top2": ((0.0, 0.0, 1.08), (0.0, 0.0, 1.34)),
        "neck": ((0.0, 0.0, 1.34), (0.0, 0.0, 1.50)),
        "head": ((0.0, 0.0, 1.50), (0.0, 0.0, 1.78)),
        "shoulder_left": ((-0.02, 0.0, 1.30), (-0.22, 0.0, 1.30)),
        "arm_left_top": ((-0.22, 0.0, 1.30), (-0.55, 0.0, 1.22)),
        "arm_left_bot": ((-0.55, 0.0, 1.22), (-0.83, 0.0, 1.10)),
        "arm_left_hand": ((-0.83, 0.0, 1.10), (-0.99, 0.0, 1.06)),
        "shoulder_right": ((0.02, 0.0, 1.30), (0.22, 0.0, 1.30)),
        "arm_right_top": ((0.22, 0.0, 1.30), (0.55, 0.0, 1.22)),
        "arm_right_bot": ((0.55, 0.0, 1.22), (0.83, 0.0, 1.10)),
        "arm_right_hand": ((0.83, 0.0, 1.10), (0.99, 0.0, 1.06)),
        "leg_left_top": ((-0.14, 0.0, 0.50), (-0.15, 0.0, 0.08)),
        "leg_left_bot": ((-0.15, 0.0, 0.08), (-0.15, 0.02, -0.36)),
        "leg_left_foot": ((-0.15, 0.02, -0.36), (-0.15, 0.28, -0.40)),
        "leg_right_top": ((0.14, 0.0, 0.50), (0.15, 0.0, 0.08)),
        "leg_right_bot": ((0.15, 0.0, 0.08), (0.15, 0.02, -0.36)),
        "leg_right_foot": ((0.15, 0.02, -0.36), (0.15, 0.28, -0.40)),
    }
    for bone_name, parent_name in CANONICAL_HUMANOID_PARENTS.items():
        bone = armature.data.edit_bones.new(bone_name)
        bone.head, bone.tail = positions[bone_name]
        if parent_name:
            bone.parent = armature.data.edit_bones[parent_name]
    bpy.ops.object.mode_set(mode="OBJECT")
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
    armature["sbf_canonical_rig_version"] = "SBF_HUMANOID_YPLUS_V1"
    armature["sbf_forward_axis"] = "+Y"
    armature["sbf_up_axis"] = "+Z"
    armature["sbf_root_bone"] = "root"
    armature["sbf_orientation_revision"] = 1
    armature["sbf_orientation_state"] = "CANONICAL_Y_PLUS"
    armature["sbf_rig_contract_version"] = 1
    armature["sbf_unit_scale_meters"] = 1.0
    return armature


def copy_runtime_armature(source):
    runtime = source.copy()
    runtime.data = source.data.copy()
    runtime.name = damage_authoring.AUTHORING_RIG_NAME
    bpy.context.collection.objects.link(runtime)
    runtime["dsb_damage_generated"] = True
    runtime["dsb_damage_role"] = "authoring_rig"
    runtime["dsb_source_armature"] = source.name
    return runtime


def material(name):
    value = bpy.data.materials.new(name)
    value.diffuse_color = (0.35, 0.05, 0.04, 1.0)
    value.use_nodes = True
    return value


def mesh_object(name, role, *, runtime_rig=None, cap_side="", shape_keys=False):
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(
        [(-0.1, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.0, 0.2)],
        [],
        [(0, 1, 2)],
    )
    mesh.materials.append(material(name + "_MAT"))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj["dsb_damage_generated"] = True
    obj["dsb_damage_role"] = role
    obj["dsb_default_visible"] = role in {"body_core", "attached_segment"}
    if cap_side:
        obj["dsb_cap_side"] = cap_side
    if runtime_rig is not None:
        group = obj.vertex_groups.new(name="root")
        group.add([0, 1, 2], 1.0, 'REPLACE')
        modifier = obj.modifiers.new(name="Armature", type='ARMATURE')
        modifier.object = runtime_rig
    if shape_keys:
        obj.shape_key_add(name="Basis")
        for index, key_name in enumerate(("Light", "Medium", "Heavy"), start=1):
            key = obj.shape_key_add(name=key_name)
            key.data[2].co.z += 0.01 * index
            key.value = 0.0
    return obj


def empty_object(name, role):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj["dsb_damage_generated"] = True
    obj["dsb_damage_role"] = role
    return obj


def create_action(owner, name, kind, *, approved=True, draft=False, clip_id=""):
    if owner.animation_data is None:
        owner.animation_data_create()
    action = bpy.data.actions.new(name)
    owner.animation_data.action = action
    offensive_metadata = None
    frames = (1, 7, 13)
    if kind in offensive_actions.OFFENSIVE_ACTION_VARIANTS:
        offensive_metadata, schedule = offensive_actions.phase_metadata(
            offensive_actions.OFFENSIVE_ACTION_VARIANTS[kind],
            bpy.context.scene.render.fps / max(bpy.context.scene.render.fps_base, 0.001),
        )
        frames = (schedule["start"], schedule["activeStart"], schedule["end"])
    body = owner.pose.bones["body"]
    for frame, offset in zip(frames, (0.0, 0.08, 0.0)):
        body.location = (offset, 0.0, 0.0)
        body.keyframe_insert("location", frame=frame, group="body")
    action["dsb_approved"] = bool(approved)
    action["dsb_draft"] = bool(draft)
    action["dsb_approved_kind"] = kind
    action[animation_library.CLIP_OWNER_PROPERTY] = owner.name
    action[animation_library.CLIP_ID_PROPERTY] = clip_id or ("clip_" + name)
    action["dsb_approved_frame_start"] = frames[0]
    action["dsb_approved_frame_end"] = frames[-1]
    action["dsb_root_motion_policy"] = "IN_PLACE"
    if offensive_metadata is not None:
        offensive_actions.stamp_offensive_metadata(action, offensive_metadata)
    track = owner.animation_data.nla_tracks.new()
    track.name = "OWNER_" + name
    track.strips.new(name, 1, action)
    return action


def action_snapshot(action):
    return {
        "name": action.name,
        "properties": {
            key: action[key]
            for key in sorted(action.keys())
        },
        "curves": [
            {
                "path": curve.data_path,
                "index": int(curve.array_index),
                "points": [
                    (
                        round(float(point.co[0]), 7),
                        round(float(point.co[1]), 7),
                        str(point.interpolation),
                    )
                    for point in curve.keyframe_points
                ],
            }
            for curve in animation_library.iter_action_fcurves(action)
        ],
    }


def rig_snapshot(rig):
    return {
        "matrix": [list(row) for row in rig.matrix_world],
        "data": rig.data.as_pointer(),
        "bones": {
            bone.name: {
                "parent": bone.parent.name if bone.parent else "",
                "matrix": [list(row) for row in bone.matrix_local],
            }
            for bone in rig.data.bones
        },
    }


def animation_owner_snapshot(rig):
    data = rig.animation_data
    return {
        "active": data.action.name if data and data.action else "",
        "tracks": [
            {
                "name": track.name,
                "mute": bool(track.mute),
                "solo": bool(getattr(track, "is_solo", False)),
                "actions": [strip.action.name if strip.action else "" for strip in track.strips],
            }
            for track in data.nla_tracks
        ] if data else [],
    }


def socket_helper_snapshot(helpers):
    return {
        helper.name: {
            "parent": helper.parent.name if helper.parent else "",
            "parentType": str(helper.parent_type),
            "parentBone": str(helper.parent_bone),
            "matrixBasis": [list(row) for row in helper.matrix_basis],
            "matrixParentInverse": [list(row) for row in helper.matrix_parent_inverse],
            "properties": {key: helper[key] for key in sorted(helper.keys())},
        }
        for helper in helpers
    }


def dummy_seam(label):
    return {
        "label": label,
        "candidate_confidence": 1.0,
        "source_edge_indices": [],
        "source_vertex_indices": [],
        "contour_polygon_indices": [],
        "ordered_contour_node_edge_keys": [],
        "contour_points_object": [],
        "node_virtual_families": {},
        "joint_plane": {
            "center_object": [0.0, 0.0, 0.0],
            "normal_object": [0.0, 0.0, 1.0],
        },
        "distal_face_sha256": "fixture-distal",
        "proximal_face_sha256": "fixture-proximal",
    }


def main():
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    context = bpy.context
    settings = context.scene.daf_settings
    output = Path(tempfile.mkdtemp(prefix="daf_runtime_skeleton_"))

    source_rig = make_armature("SBF_ProductionRig")
    runtime_rig = copy_runtime_armature(source_rig)
    source_mesh = mesh_object("SBF_CLEAN_CHARACTER", "source_character", runtime_rig=source_rig)
    protected = mesh_object(
        damage_authoring.AUTHORING_SOURCE_MESH_NAME,
        "protected_source_mesh",
        runtime_rig=runtime_rig,
    )
    protected.hide_set(True)

    objects = {}
    for name, role, skinned, keys in (
        (damage_authoring.BODY_CORE_NAME, "body_core", True, True),
        ("DSB_ATTACHED_HEAD", "attached_segment", True, False),
        ("DSB_ATTACHED_FOREARM_L", "attached_segment", True, False),
        ("DSB_ATTACHED_FOREARM_R", "attached_segment", True, False),
        ("DSB_SEGMENT_HEAD", "detached_segment", False, False),
        ("DSB_SEGMENT_FOREARM_L", "detached_segment", False, False),
        ("DSB_SEGMENT_FOREARM_R", "detached_segment", False, False),
        ("DSB_SEGMENT_UPPER_BODY", "detached_upper_body", False, False),
        ("DSB_SEGMENT_LOWER_BODY", "detached_lower_body", False, False),
    ):
        obj = mesh_object(
            name,
            role,
            runtime_rig=runtime_rig if skinned else None,
            shape_keys=keys,
        )
        objects[name] = obj
    for name, skinned in (
        ("DSB_STUMP_NECK_TORSO", True),
        ("DSB_STUMP_NECK_HEAD", False),
        ("DSB_STUMP_ELBOW_L_UPPER", True),
        ("DSB_STUMP_ELBOW_L_LOWER", False),
        ("DSB_STUMP_ELBOW_R_UPPER", True),
        ("DSB_STUMP_ELBOW_R_LOWER", False),
        ("DSB_STUMP_WAIST_LOWER", False),
        ("DSB_STUMP_WAIST_UPPER", False),
    ):
        obj = mesh_object(
            name,
            "stump_cap",
            runtime_rig=runtime_rig if skinned else None,
            cap_side="skinned_proximal" if skinned else "rigid_distal",
        )
        objects[name] = obj
    socket = empty_object(damage_authoring.ABDOMEN_SOCKET_NAME, "viscera_socket")
    objects[socket.name] = socket

    gore = mesh_object("DSB_GORE_CORE_fixture", "", runtime_rig=runtime_rig)
    gore["dsb_gore_owned"] = True
    gore["dsb_generated_role"] = "raised_gore"
    gore["dsb_preview_only"] = False
    gore["dsb_gore_pair_role"] = "CORE"
    stain = mesh_object("DSB_STAIN_CORE_fixture", "", runtime_rig=runtime_rig)
    stain["dsb_generated_role"] = "surface_stain_export"
    stain["dsb_preview_only"] = False

    source_actions = [
        create_action(source_rig, "DSB_Idle_Humanoid_v001", "IDLE", clip_id="source_idle"),
        create_action(source_rig, "DSB_Walk_NORMAL_v001", "WALK", clip_id="source_walk"),
        create_action(
            source_rig,
            "DSB_Attack_SourceOnly_v001",
            "ATTACK_SLASH_RTL_ONE_HAND",
            clip_id="source_attack",
        ),
        create_action(
            source_rig,
            "DSB_DRAFT_Unapproved",
            "ATTACK",
            approved=False,
            draft=True,
            clip_id="draft_attack",
        ),
    ]
    runtime_actions = [
        create_action(runtime_rig, "DSB_Idle_Humanoid_v002", "IDLE", clip_id="runtime_idle"),
        create_action(runtime_rig, "DSB_Walk_NORMAL_v002", "WALK", clip_id="runtime_walk"),
        create_action(runtime_rig, "DSB_Hurt_LEFT_v001", "HURT_LEFT", clip_id="runtime_hurt"),
        create_action(runtime_rig, "DSB_Death_v001", "DEATH", clip_id="runtime_death"),
    ]
    sooted_walk_override = runtime_actions[1].copy()
    sooted_walk_override.name = "DSB_Walk_Sooted_Override_v001"
    sooted_walk_override[animation_library.CLIP_ID_PROPERTY] = "runtime_walk_sooted"
    sooted_walk_override[variant_authoring.ACTION_SCOPE_PROPERTY] = (
        variant_family.ACTION_SCOPE_OVERRIDE
    )
    sooted_walk_override[variant_authoring.ACTION_FAMILY_PROPERTY] = (
        "runtime-bandit-family"
    )
    sooted_walk_override[variant_authoring.ACTION_VARIANT_PROPERTY] = "sooted"
    sooted_walk_override[variant_authoring.ACTION_SHARED_ID_PROPERTY] = "runtime_walk"
    sooted_walk_override[variant_authoring.ACTION_OVERRIDE_ID_PROPERTY] = (
        "runtime_walk_sooted"
    )
    runtime_actions.append(sooted_walk_override)
    source_rig.animation_data.action = source_actions[0]
    runtime_rig.animation_data.action = runtime_actions[0]

    bone_count_before_sockets = len(runtime_rig.data.bones)
    rest_before_sockets = rig_snapshot(runtime_rig)["bones"]
    action_count_before_sockets = len(bpy.data.actions)
    helpers = attachment_sockets.ensure_standard_sockets(runtime_rig)
    right_helper = next(
        helper for helper in helpers
        if helper["dsb_attachment_socket_role"] == "MAIN_HAND_R"
    )
    authored_world = right_helper.matrix_world.copy()
    authored_world.translation.x += 0.031
    right_helper.matrix_world = authored_world
    preserved_world = right_helper.matrix_world.copy()
    helpers_after = attachment_sockets.ensure_standard_sockets(runtime_rig)
    require(len(helpers_after) == 2, "Socket ensure is not idempotent.")
    require(
        max(abs(a - b) for row_a, row_b in zip(right_helper.matrix_world, preserved_world) for a, b in zip(row_a, row_b)) < 1.0e-7,
        "Socket repair reset the artist-authored helper transform.",
    )
    require(len(runtime_rig.data.bones) == bone_count_before_sockets, "Socket ensure added a bone.")
    require(rig_snapshot(runtime_rig)["bones"] == rest_before_sockets, "Socket ensure changed rest matrices.")
    require(len(bpy.data.actions) == action_count_before_sockets, "Socket ensure changed Actions.")
    bpy.ops.object.select_all(action="DESELECT")
    runtime_rig.select_set(True)
    context.view_layer.objects.active = runtime_rig
    settings.motion_master_id = "builtin_1h_thrust"
    settings.motion_proxy_class = "ONE_HAND_BLADE"
    settings.motion_target_zone = "CENTER_MASS"
    settings.motion_target_distance = 0.62
    motion_result = offensive_motion_studio.build_from_master(context, simple=True)
    require(motion_result["validation"]["status"] == "PASS", motion_result["validation"].get("errors"))
    motion_pose_health = offensive_motion.read_json(
        motion_result["action"],
        offensive_motion.MOTION_POSE_HEALTH_PROPERTY,
        "Motion Studio pose health",
    )
    require(motion_pose_health["status"] == "PASS", motion_pose_health.get("errors"))
    require(
        motion_pose_health["minimumArmExtensionRatio"] >= 0.55,
        "Complete Damage fixture Motion Studio attack folded below the safe reach annulus.",
    )
    require(
        motion_pose_health["maximumArmExtensionRatio"] < 0.92,
        f"Complete Damage fixture Natural overhead reached {motion_pose_health['maximumArmExtensionRatio']:.1%}.",
    )
    require(
        motion_pose_health["maximumDeformTranslationMeters"] <= 0.0001,
        "Complete Damage fixture Motion Studio attack translated the deform arm.",
    )
    offensive_motion_studio.preview_motion(context, start_playback=False)
    motion_action = addon.approve_draft_action(context, "ATTACK_THRUST_ONE_HAND")
    runtime_actions.append(motion_action)
    motion_helpers = list(offensive_motion_studio._owned_objects())
    require(motion_helpers, "Motion Studio did not create export-exclusion helpers.")

    state = {
        "schema": damage_authoring.AUTHORING_SCHEMA,
        "authoring_version": damage_authoring._version_string(),
        "authoring_build_id": damage_authoring.AUTHORING_BUILD_ID,
        "source_object_name": source_mesh.name,
        "source_armature_name": source_rig.name,
        "source_object_matrix_world": [list(row) for row in source_mesh.matrix_world],
        "source_object_scale": [1.0, 1.0, 1.0],
        "source_fingerprints": {
            "topology_sha256": "fixture-topology",
            "vertex_group_sha256": "fixture-weights",
        },
        "source_readiness_contract": {
            "schema": damage_authoring.damage_readiness.SOURCE_CONTRACT_SCHEMA,
            "sourceArmature": {
                "objectId": "source-rig-object-id",
                "dataId": "source-rig-data-id",
            },
            "sourceMeshes": [
                {
                    "objectName": source_mesh.name,
                    "objectId": "source-mesh-object-id",
                    "dataId": "source-mesh-data-id",
                }
            ],
        },
        "readiness_analyzer_revision": "fixture-runtime-export",
        "readiness_analyzer_build_id": "fixture-runtime-export",
        "virtual_weld_tolerance": 1.0e-7,
        "raw_vertex_count": 3,
        "virtual_vertex_count": 3,
        "source_polygon_count": 1,
        "authoring_rig": runtime_rig.name,
        "protected_source_mesh": protected.name,
        "objects": {name: obj.name for name, obj in objects.items()},
        "seams": {
            seam_id: dummy_seam(spec["label"])
            for seam_id, spec in damage_authoring.SEAM_SPECS.items()
        },
    }

    approved_actions = [
        action
        for action in source_actions + runtime_actions
        if bool(action.get("dsb_approved", False)) and not bool(action.get("dsb_draft", False))
    ]
    authored_frame_bounds = {
        action.name: tuple(float(value) for value in animation_library.action_frame_bounds(action))
        for action in approved_actions
    }
    require(
        all(abs(bounds[0] - 1.0) < 1.0e-7 for bounds in authored_frame_bounds.values()),
        f"The zero-time regression requires frame-1 authored Actions: {authored_frame_bounds}",
    )
    offensive_metadata_before = offensive_actions.read_offensive_metadata(source_actions[2])
    socket_helpers_before = socket_helper_snapshot(helpers_after)
    action_before = {
        action.name: action_snapshot(action)
        for action in source_actions + runtime_actions
    }
    source_rig_before = rig_snapshot(source_rig)
    runtime_rig_before = rig_snapshot(runtime_rig)
    source_owners_before = animation_owner_snapshot(source_rig)
    runtime_owners_before = animation_owner_snapshot(runtime_rig)
    selected_before = {obj.name for obj in context.selected_objects}
    active_before = context.view_layer.objects.active.name if context.view_layer.objects.active else ""

    base_material = bpy.data.materials.new("Bandit_Filthy_BaseColor")
    base_material.diffuse_color = (0.42, 0.09, 0.04, 1.0)
    sooted_material = bpy.data.materials.new("Bandit_Sooted_BaseColor")
    sooted_material.diffuse_color = (0.035, 0.035, 0.035, 1.0)
    for obj in objects.values():
        if obj.type == "MESH":
            obj.data.materials.append(base_material)

    def family_handoff(variant_id, display_name, export_identity, fingerprint):
        return {
            "schema": variant_family.SBF_HANDOFF_SCHEMA,
            "schema_version": variant_family.SBF_HANDOFF_SCHEMA_VERSION,
            "family_schema": variant_family.SBF_FAMILY_SCHEMA,
            "family_schema_version": variant_family.SBF_FAMILY_SCHEMA_VERSION,
            "family_id": "runtime-bandit-family",
            "family_display_name": "Runtime Bandit Family",
            "variant_id": variant_id,
            "variant_display_name": display_name,
            "export_identity": export_identity,
            "technical_body_schema": variant_family.SBF_TECHNICAL_BODY_SCHEMA,
            "technical_body_schema_version": variant_family.SBF_TECHNICAL_BODY_SCHEMA_VERSION,
            "technical_body_fingerprint": "a" * 64,
            "appearance_revision": 1,
            "approval": {
                "state": "APPROVED",
                "approved_revision": 1,
                "appearance_fingerprint": fingerprint,
                "approved_at_utc": "2026-08-11T12:00:00Z",
                "addon_version": "2.2.0",
            },
        }

    rig_contract = skin_and_bones.require_canonical_yplus(source_rig)
    family_state = variant_family.new_family(
        family_handoff("filthy", "Filthy", "bandit_filthy", "b" * 64),
        rig_contract,
        appearance={
            "objectNames": [],
            "materialPalette": [{"material": base_material.name, "baseColorImages": []}],
        },
    )
    family_state = variant_family.add_variant(
        family_state,
        family_handoff("sooted", "Sooted", "bandit_sooted", "c" * 64),
        rig_contract,
        appearance={
            "objectNames": [],
            "materialPalette": [{"material": sooted_material.name, "baseColorImages": []}],
        },
    )
    family_state = variant_family.register_shared_actions(
        family_state,
        [
            action[animation_library.CLIP_ID_PROPERTY]
            for action in approved_actions
            if action != sooted_walk_override
        ],
    )
    family_state = variant_family.set_action_override(
        family_state,
        "runtime_walk",
        "runtime_walk_sooted",
        "sooted",
    )
    variant_authoring.store_state(family_state)
    variant_authoring.switch_variant("sooted")

    original_validate_current = damage_authoring._validate_current_source
    original_validate_authoring = damage_authoring._validate_authoring
    original_prepare = deformation_authoring.prepare_for_export
    original_build_stains = deformation_authoring.build_surface_stain_export_artifacts
    original_remove_stains = deformation_authoring.remove_surface_stain_export_artifacts
    original_manifest = deformation_authoring.get_deformation_manifest
    original_capture = deformation_authoring.capture_damage_preview_snapshot
    original_restore = deformation_authoring.restore_damage_preview_snapshot
    original_load_authoring_state = damage_authoring._load_state
    damage_authoring._validate_current_source = lambda _state: None
    damage_authoring._validate_authoring = lambda _state, _gap: {
        "status": "PASS",
        "errors": [],
        "warnings": [],
        "source_readiness": {"status": "PASS"},
    }
    deformation_authoring.prepare_for_export = lambda: None
    deformation_authoring.build_surface_stain_export_artifacts = lambda: [stain]
    deformation_authoring.remove_surface_stain_export_artifacts = lambda: None
    deformation_authoring.get_deformation_manifest = lambda: {
        "schema": deformation_authoring.DEFORMATION_SCHEMA,
        "keys": [],
        "generatedGoreMeshes": [],
        "progressiveDamageSites": [],
    }
    deformation_authoring.capture_damage_preview_snapshot = lambda _context: {"fixture": True}
    deformation_authoring.restore_damage_preview_snapshot = lambda _context, _snapshot: None
    damage_authoring._load_state = lambda: state
    try:
        settings.damage_authoring_output_directory = str(output)
        del context.scene[variant_authoring.FAMILY_STATE_PROPERTY]
        if variant_authoring.FAMILY_STATE_PROPERTY in runtime_rig:
            del runtime_rig[variant_authoring.FAMILY_STATE_PROPERTY]
        sooted_walk_override["dsb_approved"] = False
        settings.damage_authoring_filename = "standalone_runtime_skeleton"
        standalone_paths = damage_authoring._export_asset(
            context,
            settings,
            state,
        )
        standalone_manifest = json.loads(
            Path(standalone_paths[1]).read_text(encoding="utf-8")
        )
        require(
            "characterVariant" not in standalone_manifest,
            "Standalone Complete Damage export gained a family requirement.",
        )
        sooted_walk_override["dsb_approved"] = True
        variant_authoring.store_state(family_state)
        variant_authoring.switch_variant("sooted")
        settings.damage_authoring_filename = "runtime_skeleton_acceptance"
        batch = variant_authoring.batch_export_ready_variants(context)
        require(not batch["skipped"], f"Variant batch export skipped entries: {batch}")
        require(len(batch["exported"]) == 2, f"Variant batch export did not write two assets: {batch}")
        exported_by_id = {record["variantId"]: record for record in batch["exported"]}
        glb_path, manifest_path, validation_path = exported_by_id["sooted"]["paths"]
        filthy_glb, filthy_manifest, _filthy_validation = exported_by_id["filthy"]["paths"]
        require(Path(filthy_glb).name == "bandit_filthy.glb", filthy_glb)
        require(Path(glb_path).name == "bandit_sooted.glb", glb_path)
        require(Path(filthy_glb).is_file() and Path(glb_path).is_file(), "Variant GLBs are missing.")
        filthy_materials = {
            str(record.get("name", ""))
            for record in gltf_validation.load_glb_json(filthy_glb).get("materials", [])
        }
        sooted_materials = {
            str(record.get("name", ""))
            for record in gltf_validation.load_glb_json(glb_path).get("materials", [])
        }
        require(base_material.name in filthy_materials, filthy_materials)
        require(sooted_material.name in sooted_materials, sooted_materials)
        filthy_animations = {
            str(record.get("name", ""))
            for record in gltf_validation.load_glb_json(filthy_glb).get("animations", [])
        }
        sooted_animations = {
            str(record.get("name", ""))
            for record in gltf_validation.load_glb_json(glb_path).get("animations", [])
        }
        require(
            "DSB_Walk_NORMAL_v002" in filthy_animations
            and "DSB_Walk_Sooted_Override_v001" not in filthy_animations,
            filthy_animations,
        )
        require(
            "DSB_Walk_Sooted_Override_v001" in sooted_animations
            and "DSB_Walk_NORMAL_v002" not in sooted_animations,
            sooted_animations,
        )
        filthy_payload = json.loads(Path(filthy_manifest).read_text(encoding="utf-8"))
        sooted_payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        require(
            filthy_payload["characterVariant"]["appearanceVariantId"] == "filthy"
            and sooted_payload["characterVariant"]["appearanceVariantId"] == "sooted",
            "Variant manifests do not carry distinct resolved provenance.",
        )
    finally:
        damage_authoring._validate_current_source = original_validate_current
        damage_authoring._validate_authoring = original_validate_authoring
        deformation_authoring.prepare_for_export = original_prepare
        deformation_authoring.build_surface_stain_export_artifacts = original_build_stains
        deformation_authoring.remove_surface_stain_export_artifacts = original_remove_stains
        deformation_authoring.get_deformation_manifest = original_manifest
        deformation_authoring.capture_damage_preview_snapshot = original_capture
        deformation_authoring.restore_damage_preview_snapshot = original_restore
        damage_authoring._load_state = original_load_authoring_state

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    validation = json.loads(Path(validation_path).read_text(encoding="utf-8"))
    gltf = gltf_validation.load_glb_json(glb_path)
    runtime_node = next(
        node for node in gltf.get("nodes", [])
        if str(node.get("name", "")) == damage_authoring.AUTHORING_RIG_NAME
    )
    runtime_extras = runtime_node.get("extras", {})
    runtime_variant = json.loads(runtime_extras[variant_authoring.PROVENANCE_PROPERTY])
    require(
        runtime_variant["appearanceVariantId"] == "sooted"
        and runtime_extras[variant_family.SBF_FAMILY_ID_PROPERTY]
        == "runtime-bandit-family"
        and runtime_extras[variant_family.SBF_VARIANT_ID_PROPERTY] == "sooted",
        "Runtime GLB node extras lost Character Variant provenance.",
    )
    node_names = {str(node.get("name", "")) for node in gltf.get("nodes", [])}
    require(
        not ({helper.name for helper in motion_helpers} & node_names),
        "Motion Studio authoring helpers leaked into the Complete Damage GLB.",
    )
    animation_names = [
        str(animation.get("name", "")) for animation in gltf.get("animations", [])
    ]
    expected_animations = {
        "DSB_Idle_Humanoid_v002",
        "DSB_Walk_Sooted_Override_v001",
        "DSB_Hurt_LEFT_v001",
        "DSB_Death_v001",
        "DSB_Attack_SourceOnly_v001",
        motion_action.name,
    }
    require(validation["status"] == "PASS", "; ".join(validation["errors"]))
    require(validation["runtimeSkeleton"]["status"] == "PASS", "Runtime skeleton validation failed.")
    require(validation["runtimeAnimations"]["status"] == "PASS", "Runtime animation validation failed.")
    require(validation["runtimeAttachmentSockets"]["status"] == "PASS", "Runtime socket validation failed.")
    require(set(animation_names) == expected_animations, f"Unexpected animation inventory: {animation_names}")
    manifest_clips = {
        clip["name"]: clip for clip in manifest["runtimeAnimations"]["clips"]
    }
    timing_clips = {
        clip["name"]: clip for clip in validation["runtimeAnimations"]["clips"]
    }
    require(set(manifest_clips) == expected_animations, "Runtime sidecar clip inventory differs.")
    require(set(timing_clips) == expected_animations, "Runtime timing diagnostic inventory differs.")
    for name in sorted(expected_animations):
        declared = float(manifest_clips[name]["clipDurationSeconds"])
        timing = timing_clips[name]
        require(abs(float(timing["timeStartSeconds"])) < 1.0e-7, f"{name} did not export at time zero.")
        require(
            abs(float(timing["timeEndSeconds"]) - declared) < 1.0e-6,
            f"{name} runtime end does not match its declared duration.",
        )
        require(
            abs(float(timing["durationSeconds"]) - declared) < 1.0e-6,
            f"{name} runtime span does not match its declared duration.",
        )
    require(
        len({round(float(clip["clipDurationSeconds"]), 6) for clip in manifest_clips.values()}) >= 2,
        "The multi-Action timing regression did not exercise independent durations.",
    )
    require("DSB_Idle_Humanoid_v001" not in animation_names, "Source Idle leaked into the GLB.")
    require("DSB_Walk_NORMAL_v001" not in animation_names, "Source Walk leaked into the GLB.")
    require("SBF_ProductionRig" not in node_names, "Source armature leaked into the GLB.")
    require("SBF_CLEAN_CHARACTER" not in node_names, "Source mesh leaked into the GLB.")
    require("DSB_SOURCE_MODEL_PROTECTED" not in node_names, "Protected source leaked into the GLB.")
    require("DSB_DAMAGE_RIG" in node_names, "Runtime rig is missing from the GLB.")
    require(
        not any(name.startswith(attachment_sockets.ATTACHMENT_SOCKET_HELPER_PREFIX) for name in node_names),
        "An authoring socket helper leaked into the GLB.",
    )
    require(manifest["source"]["armature"] == "SBF_ProductionRig", "Source provenance changed.")
    require(manifest["source"]["object"] == "SBF_CLEAN_CHARACTER", "Source object provenance changed.")
    require(manifest["runtimeAnimations"]["rejectedSourceActionCount"] == 2, "Duplicate source family rejection count is wrong.")
    require(manifest["runtimeAnimations"]["mirroredSourceActionCount"] == 1, "Compatible source-only mirror count is wrong.")
    require(manifest["runtimeAttachmentSockets"]["socketCount"] == 2, "Runtime socket count is wrong.")
    require(
        {socket["parentRuntimeBone"] for socket in manifest["runtimeAttachmentSockets"]["sockets"]}
        == {"arm_left_hand", "arm_right_hand"},
        "Runtime socket parents are not canonical hand bones.",
    )
    offensive_records = manifest["runtimeAnimations"]["offensiveActions"]
    require(len(offensive_records) == 2, "Exactly two offensive capabilities should export.")
    require(
        {record["combatActionId"] for record in offensive_records}
        == {"humanoid_one_hand_slash_rtl", "humanoid_one_hand_thrust"},
        "Offensive combat Action identities changed.",
    )
    targeting_records = manifest["runtimeAnimations"]["offensiveTargeting"]
    require(
        len(targeting_records) == 1
        and targeting_records[0]["schema"] == offensive_motion.TARGETING_SCHEMA
        and targeting_records[0]["trajectoryFamily"] == "THRUST",
        "Complete Damage did not emit the validated optional Motion Studio targeting handoff.",
    )
    require(
        manifest_clips[motion_action.name]["offensiveTargeting"]
        == {key: value for key, value in targeting_records[0].items() if key != "actionName"},
        "Per-clip Motion Studio targeting differs from the manifest capability record.",
    )
    exported_offensive = manifest_clips["DSB_Attack_SourceOnly_v001"]["offensiveAction"]
    require(exported_offensive == offensive_metadata_before, "Offensive metadata changed during normalization.")
    phases = exported_offensive["phases"]
    declared_attack_duration = manifest_clips["DSB_Attack_SourceOnly_v001"]["clipDurationSeconds"]
    require(abs(phases["windup"]["startSeconds"]) < 1.0e-7, "WINDUP no longer starts at clip zero.")
    require(
        abs(phases["windup"]["endSeconds"] - phases["active"]["startSeconds"]) < 1.0e-7,
        "WINDUP and ACTIVE are no longer contiguous.",
    )
    require(
        abs(phases["active"]["endSeconds"] - phases["recovery"]["startSeconds"]) < 1.0e-7,
        "ACTIVE and RECOVERY are no longer contiguous.",
    )
    require(
        abs(phases["recovery"]["endSeconds"] - declared_attack_duration) < 1.0e-6,
        "RECOVERY no longer ends at the normalized runtime clip end.",
    )
    require(
        exported_offensive["commitment"] == offensive_metadata_before["commitment"],
        "Commitment timing changed during runtime normalization.",
    )

    action_after = {
        action.name: action_snapshot(action)
        for action in source_actions + runtime_actions
    }
    require(action_before == action_after, "Source/runtime Actions changed during export staging.")
    require(
        socket_helpers_before == socket_helper_snapshot(helpers_after),
        "Complete Damage export changed an authored hand socket helper.",
    )
    require(source_rig_before == rig_snapshot(source_rig), "Source rig changed during export.")
    require(runtime_rig_before == rig_snapshot(runtime_rig), "Damage rig rest state changed during export.")
    require(source_owners_before == animation_owner_snapshot(source_rig), "Source animation ownership changed.")
    require(runtime_owners_before == animation_owner_snapshot(runtime_rig), "Runtime animation ownership was not restored.")
    require(
        not any(bool(action.get(runtime_export.RUNTIME_EXPORT_MARKER, False)) for action in bpy.data.actions),
        "Temporary runtime Action clone survived cleanup.",
    )
    require(
        not any(track.name.startswith("__DSB_RUNTIME_EXPORT__") for track in runtime_rig.animation_data.nla_tracks),
        "Temporary runtime NLA track survived cleanup.",
    )
    require({obj.name for obj in context.selected_objects} == selected_before, "Selection was not restored.")
    require(
        (context.view_layer.objects.active.name if context.view_layer.objects.active else "") == active_before,
        "Active object was not restored.",
    )

    bpy.ops.wm.read_factory_settings(use_empty=True)
    result = bpy.ops.import_scene.gltf(filepath=str(glb_path))
    require("FINISHED" in result, "Clean-scene GLB import failed.")
    imported_names = set(bpy.data.objects.keys())
    require("DSB_DAMAGE_RIG" in imported_names, "Clean import lost DSB_DAMAGE_RIG.")
    require("SBF_ProductionRig" not in imported_names, "Clean import recreated the source rig.")
    require("SBF_CLEAN_CHARACTER" not in imported_names, "Clean import recreated the source mesh.")
    require("DSB_SOURCE_MODEL_PROTECTED" not in imported_names, "Clean import recreated protected source.")
    require(
        not any(name.startswith(attachment_sockets.ATTACHMENT_SOCKET_HELPER_PREFIX) for name in imported_names),
        "Clean import recreated an authoring socket helper.",
    )
    imported_armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
    require(len(imported_armatures) == 1, "Clean import contains more than one armature hierarchy.")
    imported_body = bpy.data.objects[damage_authoring.BODY_CORE_NAME]
    body_modifiers = [modifier for modifier in imported_body.modifiers if modifier.type == 'ARMATURE']
    require(len(body_modifiers) == 1 and body_modifiers[0].object.name == "DSB_DAMAGE_RIG", "Clean body skin is not bound to DSB_DAMAGE_RIG.")
    imported_rigid = bpy.data.objects["DSB_SEGMENT_HEAD"]
    require(not any(modifier.type == 'ARMATURE' for modifier in imported_rigid.modifiers), "Rigid segment became skinned.")
    require(imported_body.data.shape_keys is not None, "Clean body lost morph targets.")
    require(
        {"Light", "Medium", "Heavy"}.issubset(imported_body.data.shape_keys.key_blocks.keys()),
        "Clean body lost progressive morph stages.",
    )
    require("DSB_GORE_CORE_fixture" in imported_names, "Clean import lost raised gore.")
    require("DSB_STAIN_CORE_fixture" in imported_names, "Clean import lost portable stain.")
    require(expected_animations == set(bpy.data.actions.keys()), "Clean import animation inventory differs.")

    report = {
        "status": "PASS",
        "blenderVersion": bpy.app.version_string,
        "forgeVersion": ".".join(str(value) for value in addon.bl_info["version"]),
        "glb": str(glb_path),
        "manifest": str(manifest_path),
        "validation": str(validation_path),
        "beforeAnimations": sorted(action_before),
        "exportedAnimations": sorted(animation_names),
        "rejectedSourceAnimations": manifest["runtimeAnimations"]["rejectedSourceActions"],
        "runtimeSkeleton": validation["runtimeSkeleton"],
        "runtimeAnimations": validation["runtimeAnimations"],
        "runtimeAttachmentSockets": validation["runtimeAttachmentSockets"],
        "authoredFrameBounds": authored_frame_bounds,
        "exportedRuntimeTiming": timing_clips,
        "offensivePhaseContractPreserved": True,
        "offensiveTargetingExported": True,
        "motionStudioHelperCountExcluded": len(motion_helpers),
        "motionStudioNaturalMaxArmExtension": motion_pose_health["maximumArmExtensionRatio"],
        "motionStudioDeformTranslationMeters": motion_pose_health["maximumDeformTranslationMeters"],
        "runtimeSocketContractPreserved": True,
        "sourceProvenancePreserved": True,
        "sourceActionsPreserved": True,
        "sourceRigPreserved": True,
        "runtimeRigRestPosePreserved": True,
        "temporaryStateCleaned": True,
        "cleanReimportArmatureCount": len(imported_armatures),
        "cleanReimportMorphs": [key.name for key in imported_body.data.shape_keys.key_blocks],
        "variantBatchExportCount": 2,
        "variantOutputs": ["bandit_filthy.glb", "bandit_sooted.glb"],
        "variantProvenance": manifest["characterVariant"],
        "standaloneCompleteDamageExport": Path(standalone_paths[0]).name,
    }
    report_path = output / "runtime_skeleton_acceptance.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RUNTIME_SKELETON_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
