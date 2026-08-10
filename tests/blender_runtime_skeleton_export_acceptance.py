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
    damage_authoring,
    deformation_authoring,
    runtime_export,
)
from dreadstone_animation_forge.deformation import gltf_validation  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def make_armature(name):
    bpy.ops.object.armature_add(enter_editmode=True, location=(0.0, 0.0, 0.0))
    armature = bpy.context.active_object
    armature.name = name
    root = armature.data.edit_bones[0]
    root.name = "root"
    root.head = (0.0, 0.0, 0.0)
    root.tail = (0.0, 0.0, 0.25)
    body = armature.data.edit_bones.new("body")
    body.parent = root
    body.use_connect = True
    body.head = root.tail
    body.tail = (0.0, 0.0, 0.75)
    head = armature.data.edit_bones.new("head")
    head.parent = body
    head.use_connect = True
    head.head = body.tail
    head.tail = (0.0, 0.0, 1.05)
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
    body = owner.pose.bones["body"]
    for frame, offset in ((1, 0.0), (7, 0.08), (13, 0.0)):
        body.location = (offset, 0.0, 0.0)
        body.keyframe_insert("location", frame=frame, group="body")
    action["dsb_approved"] = bool(approved)
    action["dsb_draft"] = bool(draft)
    action["dsb_approved_kind"] = kind
    action[animation_library.CLIP_OWNER_PROPERTY] = owner.name
    action[animation_library.CLIP_ID_PROPERTY] = clip_id or ("clip_" + name)
    action["dsb_approved_frame_start"] = 1
    action["dsb_approved_frame_end"] = 13
    action["dsb_root_motion_policy"] = "IN_PLACE"
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
        create_action(source_rig, "DSB_Attack_SourceOnly_v001", "ATTACK", clip_id="source_attack"),
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
    source_rig.animation_data.action = source_actions[0]
    runtime_rig.animation_data.action = runtime_actions[0]

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

    original_validate_current = damage_authoring._validate_current_source
    original_validate_authoring = damage_authoring._validate_authoring
    original_prepare = deformation_authoring.prepare_for_export
    original_build_stains = deformation_authoring.build_surface_stain_export_artifacts
    original_remove_stains = deformation_authoring.remove_surface_stain_export_artifacts
    original_manifest = deformation_authoring.get_deformation_manifest
    original_capture = deformation_authoring.capture_damage_preview_snapshot
    original_restore = deformation_authoring.restore_damage_preview_snapshot
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
    try:
        settings.damage_authoring_output_directory = str(output)
        settings.damage_authoring_filename = "runtime_skeleton_acceptance"
        glb_path, manifest_path, validation_path = damage_authoring._export_asset(
            context,
            settings,
            state,
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

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    validation = json.loads(Path(validation_path).read_text(encoding="utf-8"))
    gltf = gltf_validation.load_glb_json(glb_path)
    node_names = {str(node.get("name", "")) for node in gltf.get("nodes", [])}
    animation_names = [
        str(animation.get("name", "")) for animation in gltf.get("animations", [])
    ]
    expected_animations = {
        "DSB_Idle_Humanoid_v002",
        "DSB_Walk_NORMAL_v002",
        "DSB_Hurt_LEFT_v001",
        "DSB_Death_v001",
        "DSB_Attack_SourceOnly_v001",
    }
    require(validation["status"] == "PASS", "; ".join(validation["errors"]))
    require(validation["runtimeSkeleton"]["status"] == "PASS", "Runtime skeleton validation failed.")
    require(validation["runtimeAnimations"]["status"] == "PASS", "Runtime animation validation failed.")
    require(set(animation_names) == expected_animations, f"Unexpected animation inventory: {animation_names}")
    require("DSB_Idle_Humanoid_v001" not in animation_names, "Source Idle leaked into the GLB.")
    require("DSB_Walk_NORMAL_v001" not in animation_names, "Source Walk leaked into the GLB.")
    require("SBF_ProductionRig" not in node_names, "Source armature leaked into the GLB.")
    require("SBF_CLEAN_CHARACTER" not in node_names, "Source mesh leaked into the GLB.")
    require("DSB_SOURCE_MODEL_PROTECTED" not in node_names, "Protected source leaked into the GLB.")
    require("DSB_DAMAGE_RIG" in node_names, "Runtime rig is missing from the GLB.")
    require(manifest["source"]["armature"] == "SBF_ProductionRig", "Source provenance changed.")
    require(manifest["source"]["object"] == "SBF_CLEAN_CHARACTER", "Source object provenance changed.")
    require(manifest["runtimeAnimations"]["rejectedSourceActionCount"] == 2, "Duplicate source family rejection count is wrong.")
    require(manifest["runtimeAnimations"]["mirroredSourceActionCount"] == 1, "Compatible source-only mirror count is wrong.")

    action_after = {
        action.name: action_snapshot(action)
        for action in source_actions + runtime_actions
    }
    require(action_before == action_after, "Source/runtime Actions changed during export staging.")
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
        "sourceProvenancePreserved": True,
        "sourceActionsPreserved": True,
        "sourceRigPreserved": True,
        "runtimeRigRestPosePreserved": True,
        "temporaryStateCleaned": True,
        "cleanReimportArmatureCount": len(imported_armatures),
        "cleanReimportMorphs": [key.name for key in imported_body.data.shape_keys.key_blocks],
    }
    report_path = output / "runtime_skeleton_acceptance.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RUNTIME_SKELETON_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
