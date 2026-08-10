"""Completed-GLB validation for portable damage visuals.

This module intentionally has no Blender dependency. It validates the JSON
chunk that a standards-based glTF loader receives, rather than treating
Blender preview state as proof that a runtime representation exists.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Mapping


GLB_MAGIC = 0x46546C67
GLB_JSON_CHUNK = 0x4E4F534A
SURFACE_STAIN_BINDING_SCHEMA = "dreadstone.surface_stain_binding.v1"
STAIN_MODES = {"SURFACE_STAIN", "STAIN_AND_RAISED"}
FINAL_GLB_VALIDATION_SCHEMA = "dreadstone.final_glb_validation.v2"
ATTACHMENT_SOCKET_SCHEMA = "dreadstone.attachment_sockets.v1"
OFFENSIVE_ACTION_SCHEMA = "dreadstone.offensive_action.v1"


def load_glb_json(filepath):
    path = Path(filepath)
    payload = path.read_bytes()
    if len(payload) < 20:
        raise ValueError(f"GLB is too small: {path}")
    magic, version, declared_length = struct.unpack_from("<III", payload, 0)
    if magic != GLB_MAGIC or version != 2:
        raise ValueError(f"Not a glTF 2.0 GLB: {path}")
    if declared_length != len(payload):
        raise ValueError(
            f"GLB length header is {declared_length}, actual size is {len(payload)}."
        )
    offset = 12
    while offset + 8 <= len(payload):
        chunk_length, chunk_type = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunk_end = offset + chunk_length
        if chunk_end > len(payload):
            raise ValueError("GLB chunk exceeds the declared file length.")
        if chunk_type == GLB_JSON_CHUNK:
            raw = payload[offset:chunk_end].rstrip(b"\x00 \t\r\n")
            return json.loads(raw.decode("utf-8"))
        offset = chunk_end
    raise ValueError("GLB contains no JSON chunk.")


def _unique_by_name(records):
    result = {}
    duplicates = set()
    for index, record in enumerate(records or []):
        name = str(record.get("name", ""))
        if not name:
            continue
        if name in result:
            duplicates.add(name)
        else:
            result[name] = (index, record)
    return result, duplicates


def _mesh_material_indices(gltf, node):
    mesh_index = node.get("mesh")
    meshes = gltf.get("meshes", [])
    if not isinstance(mesh_index, int) or not 0 <= mesh_index < len(meshes):
        return None, []
    mesh = meshes[mesh_index]
    material_indices = [
        primitive.get("material")
        for primitive in mesh.get("primitives", [])
        if isinstance(primitive.get("material"), int)
    ]
    return mesh, material_indices


def _material_texture_image(gltf, material):
    pbr = material.get("pbrMetallicRoughness", {})
    texture_info = pbr.get("baseColorTexture")
    if not isinstance(texture_info, Mapping):
        return None, None
    texture_index = texture_info.get("index")
    textures = gltf.get("textures", [])
    if not isinstance(texture_index, int) or not 0 <= texture_index < len(textures):
        return None, None
    texture = textures[texture_index]
    source_index = texture.get("source")
    images = gltf.get("images", [])
    if not isinstance(source_index, int) or not 0 <= source_index < len(images):
        return texture, None
    return texture, images[source_index]


def _enabled_stain_keys(deformations):
    result = []
    for key in deformations.get("keys", []):
        if not bool(key.get("goreOverlayEnabled", False)):
            continue
        if str(key.get("goreOverlayMode", "")) not in STAIN_MODES:
            continue
        result.append(key)
    return result


def _node_descendants(nodes, root_index):
    descendants = set()
    stack = [root_index]
    while stack:
        index = stack.pop()
        if index in descendants or not isinstance(index, int) or not 0 <= index < len(nodes):
            continue
        descendants.add(index)
        stack.extend(nodes[index].get("children", []))
    return descendants


def _accessor_time_bounds(gltf, animation):
    accessors = gltf.get("accessors", [])
    bounds = []
    errors = []
    for sampler_index, sampler in enumerate(animation.get("samplers", [])):
        accessor_index = sampler.get("input")
        if not isinstance(accessor_index, int) or not 0 <= accessor_index < len(accessors):
            errors.append(f"sampler {sampler_index} has no valid time accessor")
            continue
        accessor = accessors[accessor_index]
        minimum = accessor.get("min", [])
        maximum = accessor.get("max", [])
        if not minimum or not maximum:
            errors.append(f"sampler {sampler_index} time accessor has no min/max bounds")
            continue
        try:
            start = float(minimum[0])
            end = float(maximum[0])
        except (TypeError, ValueError, IndexError):
            errors.append(f"sampler {sampler_index} time bounds are unreadable")
            continue
        if not math.isfinite(start) or not math.isfinite(end) or end < start:
            errors.append(f"sampler {sampler_index} has invalid time bounds")
            continue
        bounds.append((start, end))
    if not bounds:
        return None, None, errors
    return min(value[0] for value in bounds), max(value[1] for value in bounds), errors


def _runtime_contract_validation(gltf, manifest, nodes_by_name):
    nodes = gltf.get("nodes", [])
    skins = gltf.get("skins", [])
    animations = gltf.get("animations", [])
    skeleton_contract = manifest.get("runtimeSkeleton", {})
    animation_contract = manifest.get("runtimeAnimations", {})
    runtime_name = str(skeleton_contract.get("armature", "DSB_DAMAGE_RIG"))
    source_name = str((manifest.get("source", {}) or {}).get("object", ""))
    source_armature = str((manifest.get("source", {}) or {}).get("armature", ""))
    protected_name = str(
        skeleton_contract.get("protectedSourceObject", "DSB_SOURCE_MODEL_PROTECTED")
    )
    blocked_names = {
        value
        for value in {
            "SBF_CLEAN_CHARACTER",
            "SBF_ProductionRig",
            "DSB_SOURCE_MODEL_PROTECTED",
            source_name,
            source_armature,
            protected_name,
        }
        if value and value != runtime_name
    }
    skeleton_errors = []
    animation_errors = []
    present_blocked = sorted(name for name in blocked_names if name in nodes_by_name)
    for name in present_blocked:
        skeleton_errors.append(f"Authoring-only node {name!r} is present in the runtime GLB.")

    runtime_record = nodes_by_name.get(runtime_name)
    runtime_index = runtime_record[0] if runtime_record is not None else None
    runtime_hierarchy = (
        _node_descendants(nodes, runtime_index)
        if runtime_index is not None
        else set()
    )
    if runtime_index is None:
        skeleton_errors.append(f"Required runtime armature node {runtime_name!r} is missing.")

    armature_role_nodes = [
        (index, str(node.get("name", "")))
        for index, node in enumerate(nodes)
        if str(node.get("extras", {}).get("dsb_damage_role", "")) == "authoring_rig"
    ]
    unexpected_armatures = [
        name for index, name in armature_role_nodes if index != runtime_index
    ]
    if unexpected_armatures:
        skeleton_errors.append(
            "Unexpected generated armature hierarchy: "
            + ", ".join(sorted(unexpected_armatures))
            + "."
        )

    referenced_joint_sets = []
    for skin_index, skin in enumerate(skins):
        joints = list(skin.get("joints", []))
        if not joints:
            skeleton_errors.append(f"Skin {skin_index} contains no joints.")
            continue
        invalid = [
            joint for joint in joints
            if not isinstance(joint, int) or not 0 <= joint < len(nodes)
        ]
        if invalid:
            skeleton_errors.append(f"Skin {skin_index} references invalid joint indices.")
            continue
        outside = sorted(set(joints) - runtime_hierarchy)
        if outside:
            names = [str(nodes[index].get("name", index)) for index in outside]
            skeleton_errors.append(
                f"Skin {skin_index} references joints outside {runtime_name}: "
                + ", ".join(names)
                + "."
            )
        skeleton_index = skin.get("skeleton")
        if skeleton_index is not None and skeleton_index not in runtime_hierarchy:
            skeleton_errors.append(
                f"Skin {skin_index} declares a skeleton root outside {runtime_name}."
            )
        referenced_joint_sets.append(set(joints))

    required_bones = {
        str(name) for name in skeleton_contract.get("requiredBones", []) if name
    }
    runtime_node_names = {
        str(nodes[index].get("name", "")) for index in runtime_hierarchy
    }
    missing_bones = sorted(required_bones - runtime_node_names)
    if missing_bones:
        skeleton_errors.append(
            f"{runtime_name} is missing required bones: " + ", ".join(missing_bones) + "."
        )

    intact = manifest.get("intact", {})
    required_skinned_names = {
        str(intact.get("bodyCore", "")),
        *(str(value) for value in intact.get("attachedSegments", [])),
    }
    required_skinned_names.discard("")
    for name in sorted(required_skinned_names):
        record = nodes_by_name.get(name)
        if record is None:
            skeleton_errors.append(f"Required intact runtime mesh {name!r} is missing.")
            continue
        _index, node = record
        skin_index = node.get("skin")
        if not isinstance(skin_index, int) or not 0 <= skin_index < len(skins):
            skeleton_errors.append(
                f"Intact runtime mesh {name!r} is not skinned to {runtime_name}."
            )

    rigid_names = set()
    for segment in manifest.get("segments", []):
        for key in ("detachedObject", "proximalSegmentObject"):
            value = segment.get(key)
            if value:
                rigid_names.add(str(value))
    for name in sorted(rigid_names):
        record = nodes_by_name.get(name)
        if record is None:
            skeleton_errors.append(f"Required rigid detached piece {name!r} is missing.")
            continue
        if "skin" in record[1]:
            skeleton_errors.append(
                f"Rigid detached piece {name!r} unexpectedly carries a glTF skin."
            )

    expected_clips = {
        str(clip.get("name", "")): clip
        for clip in animation_contract.get("clips", [])
        if str(clip.get("name", ""))
    }
    expected_offensive_ids = [
        str((clip.get("offensiveAction") or {}).get("combatActionId", ""))
        for clip in expected_clips.values()
        if clip.get("offensiveAction") is not None
    ]
    duplicate_offensive_ids = sorted({
        value for value in expected_offensive_ids
        if value and expected_offensive_ids.count(value) > 1
    })
    if duplicate_offensive_ids:
        animation_errors.append(
            "Runtime animation contract contains ambiguous combat Action IDs: "
            + ", ".join(duplicate_offensive_ids)
            + "."
        )
    actual_names = [str(animation.get("name", "")) for animation in animations]
    duplicate_animation_names = sorted(
        {name for name in actual_names if name and actual_names.count(name) > 1}
    )
    if any(not name for name in actual_names):
        animation_errors.append("Final GLB contains an animation with an empty name.")
    if duplicate_animation_names:
        animation_errors.append(
            "Final GLB contains duplicate animation names: "
            + ", ".join(duplicate_animation_names)
            + "."
        )
    missing_clips = sorted(set(expected_clips) - set(actual_names))
    unexpected_clips = sorted(set(actual_names) - set(expected_clips))
    if missing_clips:
        animation_errors.append("Approved runtime animations are missing: " + ", ".join(missing_clips) + ".")
    if unexpected_clips:
        animation_errors.append("Unexpected or source-owned animations were exported: " + ", ".join(unexpected_clips) + ".")

    clip_diagnostics = []
    allowed_targets = runtime_hierarchy
    for animation_index, animation in enumerate(animations):
        name = str(animation.get("name", ""))
        expected = expected_clips.get(name, {})
        channels = list(animation.get("channels", []))
        extras = animation.get("extras", {})
        clip_errors = []
        if not channels:
            clip_errors.append("contains no channels")
        kind = str(extras.get("dsb_approved_kind", ""))
        expected_kind = str(expected.get("approvedKind", ""))
        if expected_kind and kind != expected_kind:
            clip_errors.append(
                f"approved kind is {kind or '<missing>'!r}, expected {expected_kind!r}"
            )
        if not bool(extras.get("dsb_approved", False)) or bool(extras.get("dsb_draft", False)):
            clip_errors.append("does not retain approved/non-draft metadata")
        if str(extras.get("dsb_runtime_armature", "")) != runtime_name:
            clip_errors.append(f"does not declare runtime owner {runtime_name!r}")
        expected_offensive = expected.get("offensiveAction")
        raw_offensive = extras.get("dsb_offensive_action_json")
        embedded_offensive = None
        if raw_offensive:
            try:
                embedded_offensive = json.loads(str(raw_offensive))
            except (TypeError, ValueError, json.JSONDecodeError):
                clip_errors.append("contains malformed offensive Action metadata")
        if expected_offensive is not None:
            if embedded_offensive != expected_offensive:
                clip_errors.append("embedded offensive Action metadata does not match the technical sidecar")
            if str((expected_offensive or {}).get("schema", "")) != OFFENSIVE_ACTION_SCHEMA:
                clip_errors.append("technical sidecar uses an unsupported offensive Action schema")
        elif embedded_offensive is not None:
            clip_errors.append("contains offensive metadata absent from the approved technical sidecar")
        target_indices = []
        for channel_index, channel in enumerate(channels):
            target_index = (channel.get("target", {}) or {}).get("node")
            if not isinstance(target_index, int) or not 0 <= target_index < len(nodes):
                clip_errors.append(f"channel {channel_index} has no valid target node")
                continue
            target_indices.append(target_index)
            if target_index not in allowed_targets:
                target_name = str(nodes[target_index].get("name", target_index))
                clip_errors.append(
                    f"channel {channel_index} targets non-runtime node {target_name!r}"
                )
            if str(nodes[target_index].get("name", "")) in blocked_names:
                clip_errors.append(f"channel {channel_index} targets an authoring-only node")
        time_start, time_end, time_errors = _accessor_time_bounds(gltf, animation)
        clip_errors.extend(time_errors)
        expected_duration = expected.get("clipDurationSeconds")
        if (
            expected_duration is not None
            and time_start is not None
            and time_end is not None
            and abs((time_end - time_start) - float(expected_duration)) > 1.0e-4
        ):
            clip_errors.append("exported duration does not match authored offensive timing")
        if clip_errors:
            animation_errors.append(
                f"Runtime animation {name or animation_index!r}: " + "; ".join(clip_errors) + "."
            )
        clip_diagnostics.append(
            {
                "name": name,
                "approvedKind": kind or None,
                "runtimeArmature": runtime_name,
                "channelCount": len(channels),
                "targetNodeCount": len(set(target_indices)),
                "timeStartSeconds": time_start,
                "timeEndSeconds": time_end,
                "durationSeconds": (
                    time_end - time_start
                    if time_start is not None and time_end is not None
                    else None
                ),
                "combatActionId": (
                    (expected_offensive or {}).get("combatActionId")
                    if expected_offensive is not None
                    else None
                ),
                "status": "PASS" if not clip_errors else "FAIL",
            }
        )

    skeleton_count = 1 if runtime_index is not None and not any(
        "outside" in error or "Unexpected generated armature" in error
        for error in skeleton_errors
    ) else 0
    runtime_skeleton = {
        "status": "PASS" if not skeleton_errors else "FAIL",
        "armature": runtime_name,
        "sourceArmaturePresentInGlb": bool(source_armature and source_armature in nodes_by_name),
        "protectedSourcePresentInGlb": bool(protected_name and protected_name in nodes_by_name),
        "sourceObjectPresentInGlb": bool(source_name and source_name in nodes_by_name),
        "skeletonCount": skeleton_count,
        "skinCount": len(skins),
        "requiredBoneCount": len(required_bones),
        "missingBones": missing_bones,
        "errors": skeleton_errors,
    }
    runtime_animations = {
        "status": "PASS" if not animation_errors else "FAIL",
        "exportedCount": len(animations),
        "expectedCount": len(expected_clips),
        "clips": clip_diagnostics,
        "rejectedSourceActionCount": int(
            animation_contract.get("rejectedSourceActionCount", 0)
        ),
        "rejectedSourceActions": list(
            animation_contract.get("rejectedSourceActions", [])
        ),
        "missingAnimations": missing_clips,
        "unexpectedAnimations": unexpected_clips,
        "errors": animation_errors,
    }
    return runtime_skeleton, runtime_animations, skeleton_errors + animation_errors


def _attachment_socket_validation(gltf, manifest, nodes_by_name):
    if "runtimeAttachmentSockets" not in manifest:
        return {
            "status": "PASS",
            "schema": ATTACHMENT_SOCKET_SCHEMA,
            "available": False,
            "runtimeArmature": "DSB_DAMAGE_RIG",
            "socketCount": 0,
            "runtimeBoneCount": len((manifest.get("runtimeSkeleton", {}) or {}).get("requiredBones", [])),
            "skinJointCount": 0,
            "helperNodeLeakCount": 0,
            "socketJointLeakCount": 0,
            "sockets": [],
            "errors": [],
        }
    contract = manifest.get("runtimeAttachmentSockets", {})
    errors = []
    nodes = gltf.get("nodes", [])
    runtime_name = str(contract.get("runtimeArmature", "DSB_DAMAGE_RIG"))
    runtime_record = nodes_by_name.get(runtime_name)
    runtime_hierarchy = (
        _node_descendants(nodes, runtime_record[0])
        if runtime_record is not None
        else set()
    )
    runtime_names = {
        str(nodes[index].get("name", "")) for index in runtime_hierarchy
    }
    if contract.get("schema") != ATTACHMENT_SOCKET_SCHEMA:
        errors.append(f"Attachment socket schema must be {ATTACHMENT_SOCKET_SCHEMA}.")
    if runtime_name != "DSB_DAMAGE_RIG":
        errors.append("Attachment sockets must target DSB_DAMAGE_RIG.")
    sockets = contract.get("sockets")
    if not isinstance(sockets, list):
        sockets = []
        errors.append("Attachment socket contract has no sockets array.")
    ids = []
    roles = []
    for index, socket in enumerate(sockets):
        if not isinstance(socket, Mapping):
            errors.append(f"Attachment socket {index} is not an object.")
            continue
        socket_id = str(socket.get("socketId", ""))
        ids.append(socket_id)
        role = str(socket.get("semanticRole", ""))
        roles.append(role)
        parent = str(socket.get("parentRuntimeBone", ""))
        if not socket_id:
            errors.append(f"Attachment socket {index} has no stable ID.")
        if parent not in runtime_names:
            errors.append(f"Attachment socket {socket_id!r} parent {parent!r} is outside DSB_DAMAGE_RIG.")
        position = socket.get("localPosition")
        quaternion = socket.get("localQuaternion")
        if not isinstance(position, list) or len(position) != 3 or not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in position):
            errors.append(f"Attachment socket {socket_id!r} has a non-finite local position.")
        if not isinstance(quaternion, list) or len(quaternion) != 4 or not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in quaternion):
            errors.append(f"Attachment socket {socket_id!r} has an invalid local quaternion.")
        elif abs(math.sqrt(sum(float(value) ** 2 for value in quaternion)) - 1.0) > 1.0e-4:
            errors.append(f"Attachment socket {socket_id!r} quaternion is not normalized.")
    duplicates = sorted({value for value in ids if value and ids.count(value) > 1})
    if duplicates:
        errors.append("Attachment socket IDs are duplicated: " + ", ".join(duplicates) + ".")
    duplicate_roles = sorted({value for value in roles if value and roles.count(value) > 1})
    if duplicate_roles:
        errors.append("Attachment socket semantic roles are duplicated: " + ", ".join(duplicate_roles) + ".")
    if contract.get("socketCount") != len(sockets):
        errors.append("Attachment socketCount does not match the socket inventory.")
    helper_nodes = [
        str(node.get("name", ""))
        for node in nodes
        if str(node.get("name", "")).startswith("DSB_ATTACHMENT_SOCKET_")
        or bool((node.get("extras", {}) or {}).get("dsb_attachment_socket_owned", False))
    ]
    if helper_nodes:
        errors.append("Authoring socket helpers leaked into the runtime GLB: " + ", ".join(sorted(helper_nodes)) + ".")
    joint_names = {
        str(nodes[joint].get("name", ""))
        for skin in gltf.get("skins", [])
        for joint in skin.get("joints", [])
        if isinstance(joint, int) and 0 <= joint < len(nodes)
    }
    socket_joint_leaks = sorted(set(helper_nodes) & joint_names)
    if socket_joint_leaks:
        errors.append("Attachment socket helpers became skin joints: " + ", ".join(socket_joint_leaks) + ".")
    required_bones = set((manifest.get("runtimeSkeleton", {}) or {}).get("requiredBones", []))
    declared_bone_count = contract.get("runtimeBoneCount")
    if declared_bone_count != len(required_bones):
        errors.append("Attachment socket authoring changed the declared runtime bone count.")
    if len(joint_names) != declared_bone_count:
        errors.append("Completed GLB skin-joint count differs from the declared runtime bone count.")
    return {
        "status": "PASS" if not errors else "FAIL",
        "schema": ATTACHMENT_SOCKET_SCHEMA,
        "available": bool(sockets),
        "runtimeArmature": runtime_name,
        "socketCount": len(sockets),
        "runtimeBoneCount": len(required_bones),
        "skinJointCount": len(joint_names),
        "helperNodeLeakCount": len(helper_nodes),
        "socketJointLeakCount": len(socket_joint_leaks),
        "sockets": [
            {
                "socketId": socket.get("socketId"),
                "semanticRole": socket.get("semanticRole"),
                "parentRuntimeBone": socket.get("parentRuntimeBone"),
            }
            for socket in sockets
            if isinstance(socket, Mapping)
        ],
        "errors": errors,
    }


def validate_damage_gltf(gltf, manifest):
    """Validate runtime skeleton, animation, and portable damage contracts."""

    errors = []
    nodes_by_name, duplicate_nodes = _unique_by_name(gltf.get("nodes", []))
    materials_by_name, duplicate_materials = _unique_by_name(
        gltf.get("materials", [])
    )
    images_by_name, duplicate_images = _unique_by_name(gltf.get("images", []))
    deformations = manifest.get("deformations", {})
    enabled_keys = _enabled_stain_keys(deformations)
    stain_errors = []
    base_errors = []
    raised_errors = []
    binding_count = 0
    stage_count = 0

    for duplicate in sorted(duplicate_nodes):
        errors.append(f"Final GLB contains duplicate node name {duplicate!r}.")
    for duplicate in sorted(duplicate_materials):
        errors.append(f"Final GLB contains duplicate material name {duplicate!r}.")
    for duplicate in sorted(duplicate_images):
        errors.append(f"Final GLB contains duplicate image name {duplicate!r}.")

    runtime_skeleton, runtime_animations, runtime_errors = (
        _runtime_contract_validation(gltf, manifest, nodes_by_name)
    )
    errors.extend(runtime_errors)
    runtime_attachment_sockets = _attachment_socket_validation(
        gltf, manifest, nodes_by_name
    )
    errors.extend(runtime_attachment_sockets["errors"])

    required_by_key = {}
    for key in enabled_keys:
        key_name = str(key.get("name", ""))
        region_id = str(key.get("regionId", ""))
        region_mode = str(key.get("regionMode", ""))
        required_roles = (
            {"CORE"} if region_mode == "CORE_SINGLE" else {"ATTACHED", "DETACHED"}
        )
        bindings = list(key.get("surfaceStainBindings", []))
        required_by_key[(region_id, key_name)] = bindings
        if not bindings:
            stain_errors.append(
                f"Enabled surface-stain key {key_name!r} has no exported binding."
            )
            continue
        roles = {
            str(binding.get("ownershipRole", "")).upper()
            for binding in bindings
        }
        missing_roles = sorted(required_roles - roles)
        if missing_roles:
            stain_errors.append(
                f"Surface-stain key {key_name!r} is missing "
                + ", ".join(missing_roles)
                + " ownership."
            )
        for binding in bindings:
            binding_count += 1
            node_name = str(binding.get("nodeName", ""))
            material_name = str(binding.get("materialName", ""))
            image_name = str(binding.get("textureName", ""))
            if str(binding.get("schema", "")) != SURFACE_STAIN_BINDING_SCHEMA:
                stain_errors.append(
                    f"Surface-stain node {node_name!r} has no supported binding schema."
                )
            if str(binding.get("deformationKey", "")) != key_name:
                stain_errors.append(
                    f"Surface-stain node {node_name!r} targets the wrong deformation key."
                )
            if bool(binding.get("defaultVisible", True)):
                stain_errors.append(
                    f"Surface-stain node {node_name!r} is visible at Basis/rest."
                )
            activation = binding.get("activationWeight")
            if (
                not isinstance(activation, (int, float))
                or not math.isfinite(float(activation))
                or float(activation) <= 0.0
            ):
                stain_errors.append(
                    f"Surface-stain node {node_name!r} has no usable activation weight."
                )
            if not bool(binding.get("portableArtifactIncluded", False)):
                stain_errors.append(
                    f"Surface-stain node {node_name!r} does not declare a portable artifact."
                )
            node_record = nodes_by_name.get(node_name)
            if node_record is None:
                stain_errors.append(
                    f"Referenced surface-stain GLB node {node_name!r} is missing."
                )
                continue
            _node_index, node = node_record
            extras = node.get("extras", {})
            if str(extras.get("dsb_generated_role", "")) != "surface_stain_export":
                stain_errors.append(
                    f"GLB node {node_name!r} is not an exported surface-stain artifact."
                )
            if bool(extras.get("dsb_stain_default_visible", True)):
                stain_errors.append(
                    f"GLB node {node_name!r} does not retain its hidden-at-Basis contract."
                )
            if bool(extras.get("dsb_preview_only", True)):
                stain_errors.append(
                    f"GLB node {node_name!r} is incorrectly marked preview-only."
                )
            mesh, material_indices = _mesh_material_indices(gltf, node)
            if mesh is None:
                stain_errors.append(
                    f"GLB node {node_name!r} has no mesh."
                )
                continue
            targets = [
                target
                for primitive in mesh.get("primitives", [])
                for target in primitive.get("targets", [])
            ]
            target_names = list(mesh.get("extras", {}).get("targetNames", []))
            if not targets:
                stain_errors.append(
                    f"GLB stain mesh {node_name!r} has no stage deformation morph."
                )
            elif target_names and key_name not in target_names:
                stain_errors.append(
                    f"GLB stain mesh {node_name!r} does not expose morph {key_name!r}."
                )
            default_weights = list(node.get("weights", mesh.get("weights", [])))
            if any(
                isinstance(weight, (int, float))
                and math.isfinite(float(weight))
                and abs(float(weight)) > 1.0e-8
                for weight in default_weights
            ):
                stain_errors.append(
                    f"GLB stain mesh {node_name!r} has a nonzero Basis/rest morph weight."
                )
            material_record = materials_by_name.get(material_name)
            if material_record is None:
                stain_errors.append(
                    f"Referenced stain material {material_name!r} is missing."
                )
                continue
            material_index, material = material_record
            if material_index not in material_indices:
                stain_errors.append(
                    f"Stain node {node_name!r} is not bound to material {material_name!r}."
                )
            if material_name.startswith("DSB_SURFACE_GORE_PREVIEW_"):
                stain_errors.append(
                    f"Preview-only Blender material {material_name!r} was treated as runtime proof."
                )
            if str(material.get("alphaMode", "OPAQUE")) not in {"BLEND", "MASK"}:
                stain_errors.append(
                    f"Stain material {material_name!r} lacks portable alpha blending."
                )
            representation = str(
                binding.get("portableRepresentation", "")
            )
            attribute_semantic = str(
                binding.get("attributeSemantic", "")
            )
            uses_vertex_color = (
                representation == "VERTEX_COLOR_RGBA"
                or attribute_semantic == "COLOR_0"
            )
            if uses_vertex_color:
                if attribute_semantic != "COLOR_0":
                    stain_errors.append(
                        f"Stain node {node_name!r} does not declare COLOR_0."
                    )
                accessors = gltf.get("accessors", [])
                for primitive in mesh.get("primitives", []):
                    color_index = primitive.get("attributes", {}).get(
                        "COLOR_0"
                    )
                    if (
                        not isinstance(color_index, int)
                        or not 0 <= color_index < len(accessors)
                    ):
                        stain_errors.append(
                            f"Stain node {node_name!r} has no portable COLOR_0 attribute."
                        )
                        continue
                    accessor = accessors[color_index]
                    if str(accessor.get("type", "")) != "VEC4":
                        stain_errors.append(
                            f"Stain node {node_name!r} COLOR_0 has no alpha channel."
                        )
            else:
                texture, image = _material_texture_image(gltf, material)
                if texture is None or image is None:
                    stain_errors.append(
                        f"Stain material {material_name!r} has no portable "
                        "COLOR_0 or embedded base-color/mask texture."
                    )
                elif image_name and str(image.get("name", "")) != image_name:
                    stain_errors.append(
                        f"Stain material {material_name!r} references image "
                        f"{image.get('name', '')!r}, expected {image_name!r}."
                    )
                elif image_name and image_name not in images_by_name:
                    stain_errors.append(
                        f"Referenced stain image {image_name!r} is missing."
                    )

            source_name = str(binding.get("sourceObject", ""))
            source_record = nodes_by_name.get(source_name)
            if source_record is None:
                base_errors.append(
                    f"Surface-stain owner node {source_name!r} is missing from the GLB."
                )
            else:
                _source_index, source_node = source_record
                source_mesh, source_materials = _mesh_material_indices(
                    gltf, source_node
                )
                if source_mesh is None or not source_materials:
                    base_errors.append(
                        f"Base owner {source_name!r} lost its original material."
                    )

    for site in deformations.get("progressiveDamageSites", []):
        for stage in site.get("stages", []):
            stage_count += 1
            key_name = str(stage.get("deformationKeyName", ""))
            stage_region_id = str(stage.get("regionId", ""))
            expected = required_by_key.get(
                (stage_region_id, key_name),
                [],
            )
            stage_bindings = list(stage.get("surfaceStainBindings", []))
            if expected and not stage_bindings:
                stain_errors.append(
                    f"Progressive stage {stage.get('stage', '')!r} / "
                    f"{key_name!r} has no stage-owned stain binding."
                )
            if any(
                str(binding.get("deformationKey", "")) != key_name
                for binding in stage_bindings
            ):
                stain_errors.append(
                    f"Progressive stage {stage.get('stage', '')!r} stain binding "
                    "does not match its explicitly assigned deformation key."
                )
            if expected:
                expected_nodes = {
                    str(binding.get("nodeName", "")) for binding in expected
                }
                stage_nodes = {
                    str(binding.get("nodeName", "")) for binding in stage_bindings
                }
                if stage_nodes != expected_nodes:
                    stain_errors.append(
                        f"Progressive stage {stage.get('stage', '')!r} does not "
                        "own the exact exported stain pair for its Damage Key."
                    )

    for record in deformations.get("generatedGoreMeshes", []):
        node_name = str(record.get("nodeName", ""))
        if node_name and node_name not in nodes_by_name:
            raised_errors.append(
                f"Referenced INLAY/RAISED GLB node {node_name!r} is missing."
            )

    surface_status = "PASS" if not stain_errors else "FAIL"
    base_status = "PASS" if not base_errors else "FAIL"
    raised_status = "PASS" if not raised_errors else "FAIL"
    errors.extend(stain_errors)
    errors.extend(base_errors)
    errors.extend(raised_errors)
    return {
        "status": "PASS" if not errors else "FAIL",
        "schema": FINAL_GLB_VALIDATION_SCHEMA,
        "runtimeSkeleton": runtime_skeleton,
        "runtimeAnimations": runtime_animations,
        "runtimeAttachmentSockets": runtime_attachment_sockets,
        "surfaceStains": {
            "status": surface_status,
            "schema": SURFACE_STAIN_BINDING_SCHEMA,
            "enabledKeyCount": len(enabled_keys),
            "progressiveStageCount": stage_count,
            "bindingCount": binding_count,
            "errors": stain_errors,
        },
        "baseMaterials": {
            "status": base_status,
            "errors": base_errors,
        },
        "raisedGoreGeometry": {
            "status": raised_status,
            "nodeCount": len(deformations.get("generatedGoreMeshes", [])),
            "errors": raised_errors,
        },
        "errors": errors,
    }


def validate_exported_damage_glb(filepath, manifest):
    return validate_damage_gltf(load_glb_json(filepath), manifest)


__all__ = (
    "FINAL_GLB_VALIDATION_SCHEMA",
    "SURFACE_STAIN_BINDING_SCHEMA",
    "load_glb_json",
    "validate_damage_gltf",
    "validate_exported_damage_glb",
)
