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


def validate_damage_gltf(gltf, manifest):
    """Validate portable stain, base-material, and raised-gore GLB contracts."""

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
        "schema": "dreadstone.final_glb_validation.v1",
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
    "SURFACE_STAIN_BINDING_SCHEMA",
    "load_glb_json",
    "validate_damage_gltf",
    "validate_exported_damage_glb",
)
