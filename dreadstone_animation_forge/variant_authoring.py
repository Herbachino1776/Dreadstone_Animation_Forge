"""Blender persistence, copy-on-write operations, and export staging for variants."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import struct
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from . import animation_library, offensive_motion
from . import variant_family as model
from .anatomy import skin_and_bones as sbf_handoff
from .deformation import progressive_sites, serialization


FAMILY_STATE_PROPERTY = "dsb_character_variant_family_json"
ACTION_SCOPE_PROPERTY = "dsb_variant_action_scope"
ACTION_FAMILY_PROPERTY = "dsb_variant_family_id"
ACTION_VARIANT_PROPERTY = "dsb_variant_owner_id"
ACTION_SHARED_ID_PROPERTY = "dsb_variant_shared_action_id"
ACTION_OVERRIDE_ID_PROPERTY = "dsb_variant_override_action_id"
OBJECT_VARIANT_PROPERTY = "dsb_appearance_variant_id"
OBJECT_FAMILY_PROPERTY = "dsb_appearance_family_id"
PROVENANCE_PROPERTY = "dsb_character_variant_provenance"
ACTIVE_EXPORT_PROPERTY = "dsb_active_appearance_variant_id"
TEXTURE_OWNER_PROPERTY = "dsb_texture_variant_owned"
TEXTURE_SOURCE_PROPERTY = "dsb_texture_variant_source"
SBF_PROJECTION_VISIBILITY_PROPERTY = "dsb_sbf_projection_visibility_json"
SBF_PROJECTION_VISIBILITY_SCHEMA = "dreadstone.sbf_projection_display.v1"
SBF_PROJECTION_VISIBILITY_SCHEMA_VERSION = 1


def _scene(scene=None):
    return scene or getattr(bpy.context, "scene", None)


def load_state(scene=None, *, required=False):
    scene = _scene(scene)
    raw = str(scene.get(FAMILY_STATE_PROPERTY, "")) if scene is not None else ""
    if not raw:
        if required:
            raise RuntimeError(
                "No Character Variant Family exists. Use an approved Skin & Bones handoff, "
                "or start texture variants from the finished Damage Rig."
            )
        return None
    try:
        return model.normalize_family(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        if required:
            raise RuntimeError(f"Character Variant Family state is unreadable: {exc}") from exc
        return None


def store_state(state, scene=None):
    scene = _scene(scene)
    if scene is None:
        raise RuntimeError("No Blender scene is available for Character Variant Family state.")
    state = model.normalize_family(state)
    encoded = model.stable_json(state)
    scene[FAMILY_STATE_PROPERTY] = encoded
    for name in ("DSB_DAMAGE_RIG",):
        owner = bpy.data.objects.get(name)
        if owner is not None:
            owner[FAMILY_STATE_PROPERTY] = encoded
    settings = getattr(scene, "daf_settings", None)
    if settings is not None:
        settings.variant_family_status = (
            f"ACTIVE — {model.variant_by_id(state)['displayName']}"
        )
    return state


def recover_state(scene=None):
    """Recover scene state from the runtime rig after unusual scene duplication."""

    scene = _scene(scene)
    if scene is None or scene.get(FAMILY_STATE_PROPERTY, ""):
        return load_state(scene)
    for owner in bpy.data.objects:
        raw = str(owner.get(FAMILY_STATE_PROPERTY, ""))
        if not raw:
            continue
        try:
            state = model.normalize_family(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        return store_state(state, scene)
    return None


def _owner_candidates(armature):
    seen = set()
    candidates = [armature, getattr(armature, "data", None)]
    candidates.extend(getattr(armature, "children_recursive", ()) or ())
    candidates.extend(getattr(armature, "children", ()) or ())
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in obj.modifiers
        ):
            candidates.extend((obj, getattr(obj, "data", None)))
    for owner in candidates:
        if owner is None:
            continue
        identity = owner.as_pointer() if hasattr(owner, "as_pointer") else id(owner)
        if identity in seen:
            continue
        seen.add(identity)
        yield owner


def handoff_from_armature(armature, *, require_approved=True):
    """Read and cross-check the shipped Skin & Bones node extras."""

    records = []
    for owner in _owner_candidates(armature):
        raw = owner.get(model.SBF_HANDOFF_PROPERTY, "")
        if not raw:
            continue
        scalars = {
            name: owner.get(name, "")
            for name in (
                model.SBF_FAMILY_ID_PROPERTY,
                model.SBF_VARIANT_ID_PROPERTY,
                model.SBF_BODY_FINGERPRINT_PROPERTY,
            )
        }
        try:
            records.append(
                model.require_handoff(
                    raw,
                    scalars,
                    require_approved=require_approved,
                )
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
    if not records:
        raise RuntimeError(
            "The selected character has no Skin & Bones "
            "skin-and-bones-appearance-family-handoff-v1 metadata. "
            "Export it from Skin & Bones Forge 2.2.0+."
        )
    canonical = model.stable_json(records[0])
    if any(model.stable_json(record) != canonical for record in records[1:]):
        raise RuntimeError(
            "Skin & Bones mesh and armature appearance-family handoffs disagree."
        )
    return records[0]


def _manifest_handoff(filepath):
    path = Path(filepath)
    manifest = Path(str(path) + ".sbf.json")
    if not manifest.is_file():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        return model.require_handoff(payload.get("appearance_family"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Skin & Bones sibling manifest is invalid: {exc}") from exc


def _rig_contract(armature):
    return sbf_handoff.require_canonical_yplus(
        armature,
        label="Character Variant Family ingest",
    )


def _armature_objects(armature, candidates=None):
    candidates = list(candidates) if candidates is not None else list(bpy.context.scene.objects)
    result = {armature}
    for obj in candidates:
        if obj == armature:
            result.add(obj)
            continue
        current = getattr(obj, "parent", None)
        while current is not None:
            if current == armature:
                result.add(obj)
                break
            current = getattr(current, "parent", None)
        if obj.type == "MESH" and any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in obj.modifiers
        ):
            result.add(obj)
    for obj in list(result):
        current = getattr(obj, "parent", None)
        while current is not None:
            result.add(current)
            current = getattr(current, "parent", None)
    return sorted(result, key=lambda value: value.name.lower())


def _material_record(material):
    if material is None:
        return {"material": "", "baseColorImages": []}
    images = []
    node_tree = getattr(material, "node_tree", None)
    if node_tree is not None:
        for node in node_tree.nodes:
            image = getattr(node, "image", None)
            if image is not None and image.name not in images:
                images.append(image.name)
    return {"material": material.name, "baseColorImages": images}


def capture_appearance(armature, objects=None):
    objects = _armature_objects(armature, objects)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    meshes.sort(
        key=lambda obj: (
            -len(obj.data.vertices),
            -len(obj.data.polygons),
            obj.name.lower(),
        )
    )
    palette = []
    if meshes:
        palette = [_material_record(value) for value in meshes[0].data.materials]
    return {
        "armatureName": armature.name,
        "objectNames": [obj.name for obj in objects],
        "meshNames": [obj.name for obj in meshes],
        "materialPalette": palette,
        "meshContracts": [
            {
                "object": obj.name,
                "vertexCount": len(obj.data.vertices),
                "polygonCount": len(obj.data.polygons),
                "materials": [_material_record(value) for value in obj.data.materials],
            }
            for obj in meshes
        ],
    }


def _find_selected_armature(context):
    candidates = set()
    for obj in list(context.selected_objects) + [context.active_object]:
        if obj is None:
            continue
        if obj.type == "ARMATURE":
            candidates.add(obj)
        if obj.type == "MESH":
            for modifier in obj.modifiers:
                if modifier.type == "ARMATURE" and modifier.object is not None:
                    candidates.add(modifier.object)
        current = getattr(obj, "parent", None)
        while current is not None:
            if current.type == "ARMATURE":
                candidates.add(current)
            current = getattr(current, "parent", None)
    if len(candidates) != 1:
        raise RuntimeError(
            "Select exactly one imported Skin & Bones character mesh or armature."
        )
    return next(iter(candidates))


def _stamp_variant_objects(state):
    if state.get("familySource") == model.FAMILY_SOURCE_FORGE_TEXTURE:
        for obj in _appearance_body_objects():
            obj[OBJECT_FAMILY_PROPERTY] = state["familyId"]
            if OBJECT_VARIANT_PROPERTY in obj:
                del obj[OBJECT_VARIANT_PROPERTY]
        return
    for variant in state.get("variants", []):
        for name in variant.get("appearance", {}).get("objectNames", []):
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            obj[OBJECT_FAMILY_PROPERTY] = state["familyId"]
            obj[OBJECT_VARIANT_PROPERTY] = variant["variantId"]


def _appearance_body_objects():
    roles = {
        "body_core",
        "attached_segment",
        "detached_segment",
        "detached_upper_body",
        "detached_lower_body",
    }
    return [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and str(obj.get("dsb_damage_role", "")) in roles
    ]


def _runtime_body_should_show(obj):
    """Return the authored intact-state visibility for one Damage body mesh."""

    role = str(obj.get("dsb_damage_role", ""))
    return bool(obj.get("dsb_default_visible", False)) or role in {
        "body_core",
        "attached_segment",
    }


def _restore_runtime_body_visibility():
    """Show only intact/default meshes; never reveal detached damage pieces."""

    visible = []
    for obj in _appearance_body_objects():
        should_show = _runtime_body_should_show(obj)
        try:
            obj.hide_set(not should_show)
        except RuntimeError:
            pass
        obj.hide_viewport = not should_show
        obj.hide_render = not should_show
        try:
            obj.select_set(should_show)
        except RuntimeError:
            pass
        if should_show:
            visible.append(obj)
    return visible


def _use_material_preview(context):
    screen = getattr(context, "screen", None)
    for area in getattr(screen, "areas", ()) if screen is not None else ():
        if area.type != "VIEW_3D":
            continue
        for space in area.spaces:
            if space.type == "VIEW_3D":
                try:
                    space.shading.type = "MATERIAL"
                except (AttributeError, TypeError):
                    pass


def _apply_material_palette(variant):
    appearance = variant.get("appearance", {})
    if appearance.get("runtimeMaterialSlots"):
        return _apply_runtime_material_slots(appearance)
    palette = appearance.get("materialPalette", [])
    materials = [
        bpy.data.materials.get(str(record.get("material", "")))
        for record in palette
    ]
    if not materials:
        return 0
    changed = 0
    for obj in _appearance_body_objects():
        slots = obj.data.materials
        for index in range(min(len(slots), len(materials))):
            material = materials[index]
            if material is not None and slots[index] != material:
                slots[index] = material
                changed += 1
    return changed


def _has_damage_authoring():
    rig = bpy.data.objects.get("DSB_DAMAGE_RIG")
    return rig is not None and bool(rig.get("dsb_damage_generated", False))


def _finished_damage_rig():
    rig = bpy.data.objects.get("DSB_DAMAGE_RIG")
    if rig is None or rig.type != "ARMATURE":
        raise RuntimeError(
            "Build the finished Complete Damage character first; DSB_DAMAGE_RIG is missing."
        )
    if not bool(rig.get("dsb_damage_generated", False)):
        raise RuntimeError("DSB_DAMAGE_RIG is not a built Complete Damage authoring rig.")
    return rig


def _rounded_matrix(matrix):
    return [round(float(value), 7) for row in matrix for value in row]


def _mesh_technical_digest(obj):
    mesh = obj.data
    digest = hashlib.sha256()
    digest.update(struct.pack("<II", len(mesh.vertices), len(mesh.polygons)))
    groups = sorted(
        (int(group.index), str(group.name)) for group in obj.vertex_groups
    )
    digest.update(struct.pack("<I", len(groups)))
    for index, name in groups:
        encoded = name.encode("utf-8")
        digest.update(struct.pack("<II", index, len(encoded)))
        digest.update(encoded)
    for vertex in mesh.vertices:
        digest.update(struct.pack("<3f", *map(float, vertex.co)))
        groups = sorted((int(item.group), float(item.weight)) for item in vertex.groups)
        digest.update(struct.pack("<I", len(groups)))
        for group, weight in groups:
            digest.update(struct.pack("<If", group, weight))
    for polygon in mesh.polygons:
        indices = tuple(int(value) for value in polygon.vertices)
        digest.update(struct.pack("<I", len(indices)))
        if indices:
            digest.update(struct.pack(f"<{len(indices)}I", *indices))
    for layer in sorted(mesh.uv_layers, key=lambda value: value.name.lower()):
        digest.update(layer.name.encode("utf-8"))
        for loop in layer.data:
            digest.update(struct.pack("<2f", *map(float, loop.uv)))
    return digest.hexdigest()


def finished_damage_body_fingerprint(rig=None):
    """Fingerprint the finished technical body while excluding materials/Damage Keys."""

    rig = rig or _finished_damage_rig()
    contract = _rig_contract(rig)
    bodies = sorted(_appearance_body_objects(), key=lambda value: value.name.lower())
    if not bodies:
        raise RuntimeError("The finished Damage Rig has no runtime appearance body meshes.")
    record = {
        "schema": model.FORGE_TEXTURE_BODY_SCHEMA,
        "rig": model.canonical_rig_signature(contract),
        "bones": [
            {
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else "",
                "matrixLocal": _rounded_matrix(bone.matrix_local),
            }
            for bone in sorted(rig.data.bones, key=lambda value: value.name.lower())
        ],
        "meshes": [
            {
                "object": obj.name,
                "role": str(obj.get("dsb_damage_role", "")),
                "vertices": len(obj.data.vertices),
                "polygons": len(obj.data.polygons),
                "uvLayers": [value.name for value in obj.data.uv_layers],
                "materialSlots": len(obj.data.materials),
                "matrixWorld": _rounded_matrix(obj.matrix_world),
                "topologyDigest": _mesh_technical_digest(obj),
            }
            for obj in bodies
        ],
    }
    return model.canonical_digest(record)


def _variant_datablock_name(kind, family_id, variant_id, source_name):
    stem = model.safe_identifier(f"{family_id}_{variant_id}_{source_name}")[:44]
    return f"DAF_{kind}_{stem}_{uuid.uuid4().hex[:8]}"


def _clone_variant_image(image, family_id, variant_id, cache):
    if image is None:
        return None
    identity = image.as_pointer()
    if identity in cache:
        return cache[identity]
    clone = image.copy()
    clone.name = _variant_datablock_name(
        "IMG", family_id, variant_id, image.name
    )
    clone[TEXTURE_OWNER_PROPERTY] = variant_id
    clone[OBJECT_FAMILY_PROPERTY] = family_id
    clone[TEXTURE_SOURCE_PROPERTY] = image.name
    clone.use_fake_user = True
    if clone.packed_file is None:
        try:
            clone.pack()
        except (RuntimeError, OSError):
            pass
    cache[identity] = clone
    return clone


def _clone_variant_material(material, family_id, variant_id, material_cache, image_cache):
    if material is None:
        return None
    identity = material.as_pointer()
    if identity in material_cache:
        return material_cache[identity]
    clone = material.copy()
    clone.name = _variant_datablock_name(
        "MAT", family_id, variant_id, material.name
    )
    clone[TEXTURE_OWNER_PROPERTY] = variant_id
    clone[OBJECT_FAMILY_PROPERTY] = family_id
    clone[TEXTURE_SOURCE_PROPERTY] = material.name
    clone.use_fake_user = True
    node_tree = getattr(clone, "node_tree", None)
    if node_tree is not None:
        for node in node_tree.nodes:
            image = getattr(node, "image", None)
            if image is not None:
                node.image = _clone_variant_image(
                    image, family_id, variant_id, image_cache
                )
    material_cache[identity] = clone
    return clone


def _runtime_material_appearance(family_id, variant_id):
    """Clone only the current runtime skin palette; never duplicate body geometry."""

    material_cache = {}
    image_cache = {}
    slots = []
    for obj in sorted(_appearance_body_objects(), key=lambda value: value.name.lower()):
        records = []
        for material in obj.data.materials:
            clone = _clone_variant_material(
                material,
                family_id,
                variant_id,
                material_cache,
                image_cache,
            )
            records.append(_material_record(clone))
        slots.append({"object": obj.name, "materials": records})
    if not material_cache:
        raise RuntimeError("The finished character has no runtime skin material to snapshot.")
    return {
        "armatureName": "DSB_DAMAGE_RIG",
        "objectNames": [record["object"] for record in slots],
        "meshNames": [record["object"] for record in slots],
        "runtimeMaterialSlots": slots,
        "materialPalette": (
            copy.deepcopy(slots[0]["materials"]) if slots else []
        ),
        "ownedMaterials": sorted(value.name for value in material_cache.values()),
        "ownedImages": sorted(value.name for value in image_cache.values()),
    }


def _serializable_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return [round(float(item), 7) for item in value]
    except (TypeError, ValueError):
        return str(value)


def _image_content_digest(image, *, quick=False):
    if image is None:
        return ""
    if quick:
        packed = getattr(image, "packed_file", None)
        path = Path(bpy.path.abspath(str(image.filepath))) if str(image.filepath) else None
        external = {}
        if path is not None and path.is_file():
            stat = path.stat()
            external = {"bytes": int(stat.st_size), "modifiedNs": int(stat.st_mtime_ns)}
        return model.canonical_digest(
            {
                "name": image.name,
                "source": str(image.source),
                "size": [int(value) for value in image.size],
                "colorspace": str(image.colorspace_settings.name),
                "dirty": bool(image.is_dirty),
                "packedBytes": len(packed.data) if packed is not None else 0,
                "filepath": str(image.filepath),
                "external": external,
            }
        )
    if bool(image.is_dirty):
        return "DIRTY"
    packed = getattr(image, "packed_file", None)
    if packed is not None:
        try:
            return hashlib.sha256(bytes(packed.data)).hexdigest()
        except (TypeError, ValueError, BufferError):
            pass
    path = Path(bpy.path.abspath(str(image.filepath))) if str(image.filepath) else None
    if path is not None and path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    return model.canonical_digest(
        {
            "source": str(image.source),
            "size": [int(value) for value in image.size],
            "colorspace": str(image.colorspace_settings.name),
            "filepath": str(image.filepath),
        }
    )


def _material_content_record(material, *, quick=False):
    if material is None:
        return {"missing": True}
    nodes = []
    links = []
    tree = getattr(material, "node_tree", None)
    if tree is not None:
        for node in sorted(tree.nodes, key=lambda value: value.name.lower()):
            inputs = {}
            for socket in node.inputs:
                if not hasattr(socket, "default_value"):
                    continue
                inputs[socket.identifier or socket.name] = _serializable_value(
                    socket.default_value
                )
            image = getattr(node, "image", None)
            nodes.append(
                {
                    "name": node.name,
                    "type": node.bl_idname,
                    "mute": bool(node.mute),
                    "inputs": inputs,
                    "imageName": image.name if image else "",
                    "image": _image_content_digest(image, quick=quick) if image else "",
                }
            )
        links = sorted(
            (
                link.from_node.name,
                link.from_socket.identifier or link.from_socket.name,
                link.to_node.name,
                link.to_socket.identifier or link.to_socket.name,
            )
            for link in tree.links
        )
    return {
        "diffuseColor": _serializable_value(material.diffuse_color),
        "metallic": round(float(material.metallic), 7),
        "roughness": round(float(material.roughness), 7),
        "nodes": nodes,
        "links": links,
    }


def texture_appearance_fingerprint(appearance, *, quick=False):
    slots = []
    for binding in appearance.get("runtimeMaterialSlots", []):
        materials = []
        for record in binding.get("materials", []):
            name = str(record.get("material", ""))
            material = bpy.data.materials.get(name)
            materials.append(
                {
                    "slotMaterial": name,
                    "content": _material_content_record(material, quick=quick),
                }
            )
        slots.append({"object": str(binding.get("object", "")), "materials": materials})
    return model.canonical_digest({"runtimeMaterialSlots": slots})


def texture_appearance_errors(state, variant_id=None, *, verify_fingerprint=True):
    state = model.normalize_family(state)
    variant = model.variant_by_id(state, variant_id)
    errors = []
    if state["familySource"] != model.FAMILY_SOURCE_FORGE_TEXTURE:
        return errors
    appearance = variant.get("appearance", {})
    for name in appearance.get("ownedMaterials", []):
        if bpy.data.materials.get(str(name)) is None:
            errors.append(f"Texture snapshot material {name!r} is missing.")
    for name in appearance.get("ownedImages", []):
        image = bpy.data.images.get(str(name))
        if image is None:
            errors.append(f"Texture snapshot image {name!r} is missing.")
        elif bool(image.is_dirty):
            errors.append(
                f"Texture image {name!r} has unsaved pixel changes; approve/update this look again."
            )
    current = (
        texture_appearance_fingerprint(appearance)
        if verify_fingerprint
        else None
    )
    if not model.variant_appearance_approved(state, variant_id, current):
        errors.append("Texture appearance is draft or changed after its last Forge approval.")
    return errors


def appearance_status(state, variant_id=None):
    state = model.normalize_family(state)
    variant = model.variant_by_id(state, variant_id)
    if state["familySource"] == model.FAMILY_SOURCE_SBF:
        return "APPROVED"
    if str(variant.get("appearanceApprovalState", "")) != "APPROVED":
        return "DRAFT"
    if texture_appearance_errors(state, variant_id, verify_fingerprint=False):
        return "STALE"
    expected_quick = str(variant.get("appearanceQuickFingerprint", ""))
    if expected_quick:
        current_quick = texture_appearance_fingerprint(
            variant.get("appearance", {}),
            quick=True,
        )
        if current_quick != expected_quick:
            return "STALE"
    return "APPROVED"


def _apply_runtime_material_slots(appearance):
    changed = 0
    for binding in appearance.get("runtimeMaterialSlots", []):
        obj = bpy.data.objects.get(str(binding.get("object", "")))
        if obj is None or obj.type != "MESH":
            continue
        records = list(binding.get("materials", []))
        for index in range(min(len(obj.data.materials), len(records))):
            material = bpy.data.materials.get(str(records[index].get("material", "")))
            if material is not None and obj.data.materials[index] != material:
                obj.data.materials[index] = material
                changed += 1
    return changed


def _release_owned_appearance(appearance):
    for name in appearance.get("ownedMaterials", []):
        material = bpy.data.materials.get(str(name))
        if material is not None and bool(material.get(TEXTURE_OWNER_PROPERTY, "")):
            material.use_fake_user = False
            if material.users == 0:
                bpy.data.materials.remove(material)
    for name in appearance.get("ownedImages", []):
        image = bpy.data.images.get(str(name))
        if image is not None and bool(image.get(TEXTURE_OWNER_PROPERTY, "")):
            image.use_fake_user = False
            if image.users == 0:
                bpy.data.images.remove(image)


def switch_variant(variant_id, scene=None):
    scene = _scene(scene)
    state = model.set_active_variant(load_state(scene, required=True), variant_id)
    active = model.variant_by_id(state)
    damage_built = _has_damage_authoring()
    for variant in state["variants"]:
        show = variant["variantId"] == active["variantId"] and not damage_built
        for name in variant.get("appearance", {}).get("objectNames", []):
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            try:
                obj.hide_set(not show)
            except RuntimeError:
                pass
            obj.hide_render = not show
    _apply_material_palette(active)
    store_state(state, scene)
    effective_action = _select_effective_action(scene)
    if effective_action is not None:
        rig_names = {
            str(active.get("appearance", {}).get("armatureName", "")),
            "DSB_DAMAGE_RIG" if damage_built else "",
        }
        for rig_name in rig_names:
            rig = bpy.data.objects.get(rig_name)
            if rig is None or rig.type != "ARMATURE":
                continue
            if rig.animation_data is None:
                rig.animation_data_create()
            rig.animation_data.action = effective_action
    settings = getattr(scene, "daf_settings", None)
    if settings is not None:
        settings.variant_shared_damage_edit_enabled = False
        settings.variant_family_status = f"VIEWING — {active['displayName']}"
    return active


def adopt_selected_as_family_base(context):
    if load_state(context.scene) is not None:
        raise RuntimeError(
            "This Blend file already owns a Character Variant Family. Add a compatible appearance instead."
        )
    armature = _find_selected_armature(context)
    handoff = handoff_from_armature(armature)
    contract = _rig_contract(armature)
    appearance = capture_appearance(armature)
    try:
        state = model.new_family(handoff, contract, appearance=appearance)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    action_ids = []
    for action in animation_library.character_actions(armature, include_drafts=False):
        if not bool(action.get("dsb_approved", False)):
            continue
        clip_id = animation_library.ensure_clip_id(action)
        action[ACTION_SCOPE_PROPERTY] = model.ACTION_SCOPE_SHARED
        action[ACTION_FAMILY_PROPERTY] = state["familyId"]
        action[ACTION_SHARED_ID_PROPERTY] = clip_id
        action_ids.append(clip_id)
    state = model.register_shared_actions(state, action_ids)
    _stamp_variant_objects(state)
    store_state(state, context.scene)
    switch_variant(handoff["variant_id"], context.scene)
    return state


def _shared_family_actions(state, rig):
    action_ids = []
    for action in animation_library.character_actions(rig, include_drafts=False):
        if not bool(action.get("dsb_approved", False)):
            continue
        clip_id = animation_library.ensure_clip_id(action)
        action[ACTION_SCOPE_PROPERTY] = model.ACTION_SCOPE_SHARED
        action[ACTION_FAMILY_PROPERTY] = state["familyId"]
        action[ACTION_SHARED_ID_PROPERTY] = clip_id
        action_ids.append(clip_id)
    return model.register_shared_actions(state, action_ids)


def _texture_names(settings, *, base=False):
    file_stem = Path(bpy.data.filepath).stem if bpy.data.filepath else "finished_character"
    configured_export = str(getattr(settings, "damage_authoring_filename", "")).strip()
    family_seed = configured_export or file_stem
    family_display = str(settings.variant_texture_family_name).strip() or (
        family_seed.replace("_", " ").replace("-", " ").strip().title()
    )
    requested_display = str(settings.variant_texture_name).strip()
    if not base and not requested_display:
        raise RuntimeError("Name the next look before making its texture copy.")
    display = requested_display or "Original"
    export_identity = str(settings.variant_texture_export_identity).strip()
    if not export_identity:
        export_identity = (
            model.safe_identifier(configured_export or family_display)
            if base
            else model.safe_identifier(f"{_safe_texture_family_name(family_display)}_{display}")
        )
    return (
        family_display,
        display,
        export_identity,
        model.safe_identifier(export_identity),
    )


def _safe_texture_family_name(value):
    """Keep automatically derived shipping names compact and deterministic."""

    return model.safe_identifier(value, fallback="finished_character")


def adopt_finished_damage_as_texture_family(context):
    """Start appearance multiplication from the already-authored Damage Rig."""

    if load_state(context.scene) is not None:
        raise RuntimeError("This Blend file already owns a Character Variant Family.")
    # Older resized authoring files can retain the correct stored proof while
    # their hidden original source was later reset. Repair that exact proof
    # before locking the finished-body fingerprint so setup and export observe
    # the same validated technical state.
    from . import damage_authoring

    try:
        finished_authoring_state = damage_authoring._load_state()
    except RuntimeError:
        finished_authoring_state = None
    if finished_authoring_state is not None:
        damage_authoring.restore_finished_source_transform_proof(context)
    rig = _finished_damage_rig()
    contract = _rig_contract(rig)
    fingerprint = finished_damage_body_fingerprint(rig)
    settings = context.scene.daf_settings
    family_display, display, export_identity, variant_id = _texture_names(
        settings, base=True
    )
    family_id = model.safe_identifier(family_display, fallback="finished_character")
    appearance = _runtime_material_appearance(family_id, variant_id)
    _apply_runtime_material_slots(appearance)
    appearance_fingerprint = texture_appearance_fingerprint(appearance)
    appearance_quick_fingerprint = texture_appearance_fingerprint(
        appearance,
        quick=True,
    )
    state = model.new_forge_texture_family(
        family_id,
        family_display,
        variant_id,
        display,
        export_identity,
        fingerprint,
        contract,
        appearance=appearance,
        appearance_fingerprint=appearance_fingerprint,
        approved_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    state["variants"][0]["appearanceQuickFingerprint"] = appearance_quick_fingerprint
    state = _shared_family_actions(state, rig)
    _stamp_variant_objects(state)
    store_state(state, context.scene)
    switch_variant(variant_id, context.scene)
    settings.variant_texture_name = ""
    settings.variant_texture_export_identity = ""
    return state


def create_forge_texture_variant(context):
    state = load_state(context.scene, required=True)
    if state["familySource"] != model.FAMILY_SOURCE_FORGE_TEXTURE:
        raise RuntimeError(
            "This family is Skin & Bones-owned. Add an approved compatible Skin & Bones GLB instead."
        )
    rig = _finished_damage_rig()
    contract = _rig_contract(rig)
    fingerprint = finished_damage_body_fingerprint(rig)
    settings = context.scene.daf_settings
    _family_display, display, export_identity, variant_id = _texture_names(settings)
    active = model.variant_by_id(state)
    if appearance_status(state, active["variantId"]) != "APPROVED":
        raise RuntimeError(
            "Save the active look before making another texture copy."
        )
    _apply_material_palette(active)
    appearance = _runtime_material_appearance(state["familyId"], variant_id)
    try:
        state = model.add_forge_texture_variant(
            state,
            variant_id,
            display,
            export_identity,
            fingerprint,
            contract,
            appearance=appearance,
        )
    except Exception:
        _release_owned_appearance(appearance)
        raise
    _stamp_variant_objects(state)
    store_state(state, context.scene)
    switch_variant(variant_id, context.scene)
    settings.variant_texture_name = ""
    settings.variant_texture_export_identity = ""
    settings.variant_family_status = (
        f"DRAFT LOOK — {display}; project/bake this copy, then APPROVE CURRENT LOOK"
    )
    return model.variant_by_id(state, variant_id)


def approve_forge_texture_variant(context):
    state = load_state(context.scene, required=True)
    if state["familySource"] != model.FAMILY_SOURCE_FORGE_TEXTURE:
        raise RuntimeError("Skin & Bones appearances must be approved in Skin & Bones.")
    rig = _finished_damage_rig()
    current_technical = finished_damage_body_fingerprint(rig)
    if current_technical != state["technicalBodyFingerprint"]:
        raise RuntimeError(
            "The finished Damage Rig/body changed after this texture family was started; "
            "texture approval cannot hide a technical-body change."
        )
    active = model.variant_by_id(state)
    old_appearance = copy.deepcopy(active.get("appearance", {}))
    appearance = _runtime_material_appearance(
        state["familyId"], active["variantId"]
    )
    _apply_runtime_material_slots(appearance)
    fingerprint = texture_appearance_fingerprint(appearance)
    quick_fingerprint = texture_appearance_fingerprint(appearance, quick=True)
    state = model.approve_forge_texture_variant(
        state,
        fingerprint,
        datetime.now(timezone.utc).isoformat(),
        appearance=appearance,
    )
    next(
        value for value in state["variants"]
        if value["variantId"] == state["activeVariantId"]
    )["appearanceQuickFingerprint"] = quick_fingerprint
    store_state(state, context.scene)
    _release_owned_appearance(old_appearance)
    context.scene.daf_settings.variant_family_status = (
        f"APPROVED LOOK — {active['displayName']}"
    )
    return model.variant_by_id(state)


def edit_forge_texture_variant(context):
    """Enter an explicit edit/re-approval cycle for the active native look."""

    state = load_state(context.scene, required=True)
    if state["familySource"] != model.FAMILY_SOURCE_FORGE_TEXTURE:
        raise RuntimeError("Imported Skin & Bones looks are edited and approved in Skin & Bones.")
    state = model.begin_forge_texture_variant_edit(state)
    store_state(state, context.scene)
    variant = preview_active_variant(context)
    context.scene.daf_settings.variant_family_status = (
        f"EDITING LOOK — {variant['displayName']}; project/paint, preview, then approve"
    )
    return variant


def _linked_base_color_image_nodes(material):
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return []
    found = []
    visited = set()

    def walk_socket(socket):
        for link in socket.links:
            node = link.from_node
            identity = node.as_pointer()
            if identity in visited:
                continue
            visited.add(identity)
            if node.bl_idname == "ShaderNodeTexImage" and node.image is not None:
                found.append(node)
                continue
            for input_socket in node.inputs:
                if input_socket.is_linked:
                    walk_socket(input_socket)

    for node in tree.nodes:
        if node.bl_idname != "ShaderNodeBsdfPrincipled":
            continue
        socket = node.inputs.get("Base Color")
        if socket is not None and socket.is_linked:
            walk_socket(socket)
    if found:
        return list(dict.fromkeys(found))
    candidates = [
        node
        for node in tree.nodes
        if node.bl_idname == "ShaderNodeTexImage" and node.image is not None
    ]
    named = [
        node
        for node in candidates
        if "base" in f"{node.name} {node.label} {node.image.name}".lower()
        and "color" in f"{node.name} {node.label} {node.image.name}".lower()
    ]
    return named or (candidates if len(candidates) == 1 else [])


def _active_base_color_bindings(context):
    state = load_state(context.scene, required=True)
    if state["familySource"] != model.FAMILY_SOURCE_FORGE_TEXTURE:
        raise RuntimeError(
            "Imported Skin & Bones looks must be projected, approved, and exported from Skin & Bones before Forge ingest."
        )
    active = model.variant_by_id(state)
    _apply_material_palette(active)
    materials = [
        bpy.data.materials.get(str(name))
        for name in active.get("appearance", {}).get("ownedMaterials", [])
    ]
    bindings = [
        (material, node)
        for material in materials
        if material is not None
        for node in _linked_base_color_image_nodes(material)
    ]
    if not bindings:
        raise RuntimeError(
            "The active look has no unambiguous image driving Principled Base Color. "
            "Link its skin image to Base Color, then try again."
        )
    return state, active, bindings


def _finish_active_base_color_install(
    context,
    state,
    active,
    bindings,
    image,
    *,
    status_detail,
):
    for _material, node in bindings:
        node.image = image
    if active.get("appearanceApprovalState") == "APPROVED":
        state = model.begin_forge_texture_variant_edit(state)
    owned = next(
        value for value in state["variants"]
        if value["variantId"] == state["activeVariantId"]
    )
    appearance = owned.setdefault("appearance", {})
    appearance["ownedImages"] = sorted(
        set(appearance.get("ownedImages", [])) | {image.name}
    )
    for binding in appearance.get("runtimeMaterialSlots", []):
        for record in binding.get("materials", []):
            material = bpy.data.materials.get(str(record.get("material", "")))
            if material is not None:
                record.update(_material_record(material))
    if appearance.get("runtimeMaterialSlots"):
        appearance["materialPalette"] = copy.deepcopy(
            appearance["runtimeMaterialSlots"][0].get("materials", [])
        )
    store_state(state, context.scene)
    variant = preview_active_variant(context)
    context.scene.daf_settings.variant_family_status = (
        f"EDITING LOOK — {status_detail} in {variant['displayName']}; save before export"
    )
    return variant, image


def replace_active_base_color_texture(context, filepath=None):
    """Load one final Base Color into the active look without touching authoring."""

    path = Path(
        bpy.path.abspath(
            str(filepath or context.scene.daf_settings.variant_texture_image_path)
        )
    )
    if path.is_dir():
        raise RuntimeError(
            "That is a four-view projection-source folder, not a finished model texture. "
            "Use the Skin & Bones projection steps, bake once, then apply its final Base Color."
        )
    if not path.is_file():
        raise RuntimeError("Choose an existing final Base Color image.")
    state, active, bindings = _active_base_color_bindings(context)
    image = None
    try:
        image = bpy.data.images.load(str(path), check_existing=False)
        image.name = _variant_datablock_name(
            "IMG", state["familyId"], active["variantId"], path.stem
        )
        image[TEXTURE_OWNER_PROPERTY] = active["variantId"]
        image[OBJECT_FAMILY_PROPERTY] = state["familyId"]
        image[TEXTURE_SOURCE_PROPERTY] = str(path)
        original_image = bindings[0][1].image
        if original_image is not None:
            try:
                image.colorspace_settings.name = original_image.colorspace_settings.name
            except (AttributeError, TypeError):
                pass
        image.pack()
        image.filepath_raw = ""
        return _finish_active_base_color_install(
            context,
            state,
            active,
            bindings,
            image,
            status_detail=f"loaded {path.name}",
        )
    except Exception:
        if (
            image is not None
            and bpy.data.images.get(image.name) is not None
            and image.users == 0
        ):
            bpy.data.images.remove(image)
        raise


def _skin_and_bones_projection_target(context):
    settings = getattr(context.scene, "sbf_settings", None)
    if settings is None:
        raise RuntimeError(
            "Skin & Bones is not enabled in this Blender session. Enable Skin & Bones 2.2.0+ first."
        )
    target = getattr(settings, "target_object", None)
    if target is None or getattr(target, "type", "") != "MESH":
        raise RuntimeError(
            "Skin & Bones needs its original full-body mesh as Target Mesh. "
            "DSB_DAMAGE_RIG is an armature and is not a projection target."
        )
    if bool(target.get("dsb_damage_generated", False)):
        raise RuntimeError(
            "Choose the original Skin & Bones full-body mesh as Target Mesh, not a generated Damage segment."
        )
    return settings, target


def _validated_skin_and_bones_projection_armature(rig):
    """Prove a source rig can be switched at Armature-datablock scope."""

    if rig is None or getattr(rig, "type", "") != "ARMATURE":
        raise RuntimeError("Skin & Bones projection recovery cannot resolve its source armature.")
    damage_rigs = [
        obj
        for obj in bpy.data.objects
        if getattr(obj, "type", "") == "ARMATURE"
        and (
            obj.name == "DSB_DAMAGE_RIG"
            or str(obj.get("dsb_damage_role", "")) == "authoring_rig"
        )
    ]
    aliases = [
        obj
        for obj in bpy.data.objects
        if obj is not rig
        and getattr(obj, "type", "") == "ARMATURE"
        and getattr(obj, "data", None) is rig.data
    ]
    if (
        bool(rig.get("dsb_damage_generated", False))
        or any(rig is damage or rig.data is damage.data for damage in damage_rigs)
    ):
        raise RuntimeError(
            "Skin & Bones projection cannot neutralize DSB_DAMAGE_RIG or an "
            "armature sharing its data. Bind the original S&B production rig instead."
        )
    if aliases:
        raise RuntimeError(
            "Skin & Bones projection cannot neutralize an Armature datablock shared "
            "by another object ("
            + ", ".join(sorted(obj.name for obj in aliases))
            + "). Make the intended S&B production rig unambiguous first."
        )
    if not bool(rig.get("sbf_production_rig", False)):
        raise RuntimeError(
            "The armature bound to the Skin & Bones Target Mesh lacks the shipped "
            "sbf_production_rig proof. Forge will not neutralize an unproven rig."
        )
    return rig


def _skin_and_bones_projection_armature(target):
    """Resolve the one armature bound to S&B's projection target, if any."""

    candidates = []
    parent = getattr(target, "parent", None)
    if parent is not None and getattr(parent, "type", "") == "ARMATURE":
        candidates.append(parent)
    for modifier in getattr(target, "modifiers", ()):
        if getattr(modifier, "type", "") != "ARMATURE":
            continue
        rig = getattr(modifier, "object", None)
        if rig is not None and rig not in candidates:
            candidates.append(rig)
    if not candidates:
        return None
    if len(candidates) != 1:
        raise RuntimeError(
            "Skin & Bones Target Mesh is bound to multiple armatures. "
            "Choose its single original production rig before projection."
        )
    return _validated_skin_and_bones_projection_armature(candidates[0])


def _neutralize_skin_and_bones_projection_pose(context, target):
    """Evaluate source plates on S&B's neutral body without touching Forge's rig."""

    rig = _skin_and_bones_projection_armature(target)
    if rig is None:
        return None, None
    previous = str(rig.data.pose_position)
    rig.data.pose_position = "REST"
    try:
        context.view_layer.update()
    except (AttributeError, RuntimeError):
        pass
    return rig, previous


def _load_skin_and_bones_projection_snapshot(scene):
    raw = str(scene.get(SBF_PROJECTION_VISIBILITY_PROPERTY, ""))
    if not raw:
        return None
    try:
        snapshot = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Skin & Bones projection recovery state is corrupt. "
            "Forge did not change either rig; restore or remove the saved recovery property explicitly."
        ) from exc
    if not isinstance(snapshot, dict) or not str(snapshot.get("target", "")):
        raise RuntimeError(
            "Skin & Bones projection recovery state is incomplete. "
            "Forge did not change either rig."
        )
    schema = str(snapshot.get("schema", ""))
    try:
        schema_version = int(snapshot.get("schemaVersion", 0))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Skin & Bones projection recovery state has an invalid schema version. "
            "Forge did not change either rig."
        ) from exc
    if schema and (
        schema != SBF_PROJECTION_VISIBILITY_SCHEMA
        or schema_version != SBF_PROJECTION_VISIBILITY_SCHEMA_VERSION
    ):
        raise RuntimeError(
            "Skin & Bones projection recovery state uses an unsupported schema. "
            "Forge did not change either rig."
        )
    if not schema and any(
        key in snapshot
        for key in ("schemaVersion", "targetData", "rig", "rigData", "rigPosePosition")
    ):
        raise RuntimeError(
            "Skin & Bones projection recovery state mixes legacy and versioned fields. "
            "Forge did not change either rig."
        )
    if schema:
        rig_name = str(snapshot.get("rig", ""))
        rig_data = str(snapshot.get("rigData", ""))
        pose_position = str(snapshot.get("rigPosePosition", ""))
        if bool(rig_name or rig_data or pose_position) and not (
            rig_name and rig_data and pose_position in {"POSE", "REST"}
        ):
            raise RuntimeError(
                "Skin & Bones projection recovery state has incomplete source-rig identity. "
                "Forge did not change either rig."
            )
    return snapshot


def _projection_snapshot_object(snapshot, name_key, data_key, object_type, label):
    name = str(snapshot.get(name_key, ""))
    data_name = str(snapshot.get(data_key, ""))
    value = bpy.data.objects.get(name) if name else None
    if (
        value is not None
        and getattr(value, "type", "") == object_type
        and (not data_name or getattr(getattr(value, "data", None), "name", "") == data_name)
    ):
        return value
    if data_name:
        matches = [
            obj
            for obj in bpy.data.objects
            if getattr(obj, "type", "") == object_type
            and getattr(getattr(obj, "data", None), "name", "") == data_name
        ]
        if len(matches) == 1:
            return matches[0]
    raise RuntimeError(
        f"Skin & Bones projection recovery cannot safely resolve its saved {label}. "
        "The recovery state was retained; restore the original object/data identity and try again."
    )


def _projection_snapshot_matches(snapshot, target, rig):
    target_name = str(snapshot.get("target", ""))
    target_data = str(snapshot.get("targetData", ""))
    target_matches = target_name == target.name
    if not target_matches and target_data == target.data.name:
        matches = [
            obj
            for obj in bpy.data.objects
            if getattr(obj, "type", "") == "MESH"
            and getattr(getattr(obj, "data", None), "name", "") == target_data
        ]
        target_matches = len(matches) == 1 and matches[0] is target
    if not target_matches:
        return False
    if not str(snapshot.get("schema", "")):
        return True
    saved_rig = str(snapshot.get("rig", ""))
    saved_data = str(snapshot.get("rigData", ""))
    if rig is None:
        return not saved_rig and not saved_data
    return (
        (saved_rig == rig.name or saved_data == rig.data.name)
        and saved_data == rig.data.name
    )


def _projection_snapshot_payload(target, rig, *, visibility=None):
    visibility = visibility or {}
    return {
        "schema": SBF_PROJECTION_VISIBILITY_SCHEMA,
        "schemaVersion": SBF_PROJECTION_VISIBILITY_SCHEMA_VERSION,
        "target": target.name,
        "targetData": target.data.name,
        "hideViewport": bool(visibility.get("hideViewport", target.hide_viewport)),
        "hideRender": bool(visibility.get("hideRender", target.hide_render)),
        "hidden": bool(visibility.get("hidden", target.hide_get())),
        "rig": getattr(rig, "name", ""),
        "rigData": getattr(getattr(rig, "data", None), "name", ""),
        "rigPosePosition": str(rig.data.pose_position) if rig is not None else "",
    }


def _prepare_skin_and_bones_projection_snapshot(scene, target, rig):
    snapshot = _load_skin_and_bones_projection_snapshot(scene)
    if snapshot is not None and not _projection_snapshot_matches(snapshot, target, rig):
        _restore_skin_and_bones_projection_visibility(scene)
        snapshot = None
    if snapshot is None:
        snapshot = _projection_snapshot_payload(target, rig)
        scene[SBF_PROJECTION_VISIBILITY_PROPERTY] = model.stable_json(snapshot)
        return snapshot
    if not str(snapshot.get("schema", "")):
        # Migrate the visibility-only state shipped before 6.0.0 without
        # overwriting its original hidden/display values.
        snapshot = _projection_snapshot_payload(target, rig, visibility=snapshot)
        scene[SBF_PROJECTION_VISIBILITY_PROPERTY] = model.stable_json(snapshot)
    return snapshot


def _restore_skin_and_bones_projection_visibility(scene):
    snapshot = _load_skin_and_bones_projection_snapshot(scene)
    if snapshot is None:
        return None
    target = _projection_snapshot_object(
        snapshot,
        "target",
        "targetData",
        "MESH",
        "projection target",
    )
    if str(snapshot.get("schema", "")) and str(snapshot.get("rig", "")):
        rig = _projection_snapshot_object(
            snapshot,
            "rig",
            "rigData",
            "ARMATURE",
            "source armature",
        )
        _validated_skin_and_bones_projection_armature(rig)
        pose_position = str(snapshot.get("rigPosePosition", ""))
        if pose_position not in {"POSE", "REST"}:
            raise RuntimeError(
                "Skin & Bones projection recovery has no valid saved pose mode. "
                "The recovery state was retained."
            )
        rig.data.pose_position = pose_position
        try:
            bpy.context.view_layer.update()
        except (AttributeError, RuntimeError):
            pass
    target.hide_viewport = bool(snapshot.get("hideViewport", True))
    target.hide_render = bool(snapshot.get("hideRender", True))
    try:
        target.hide_set(bool(snapshot.get("hidden", True)))
    except RuntimeError:
        pass
    del scene[SBF_PROJECTION_VISIBILITY_PROPERTY]
    return target


def enter_skin_and_bones_projection(context):
    """Show S&B's source body and hide only Forge runtime appearance meshes."""

    state = load_state(context.scene, required=True)
    if state["familySource"] != model.FAMILY_SOURCE_FORGE_TEXTURE:
        raise RuntimeError(
            "This bridge is for a finished Forge texture look. Imported S&B family looks stay S&B-owned."
        )
    if appearance_status(state) == "APPROVED":
        raise RuntimeError("Click EDIT / TWEAK THIS LOOK before projecting a replacement texture.")
    _settings, target = _skin_and_bones_projection_target(context)
    scene = context.scene
    rig = _skin_and_bones_projection_armature(target)
    _prepare_skin_and_bones_projection_snapshot(scene, target, rig)
    try:
        neutral_rig, _previous_pose = _neutralize_skin_and_bones_projection_pose(context, target)
        for obj in list(getattr(context, "selected_objects", ())):
            try:
                obj.select_set(False)
            except RuntimeError:
                pass
        for body in _appearance_body_objects():
            try:
                body.hide_set(True)
                body.select_set(False)
            except RuntimeError:
                pass
            body.hide_viewport = True
            body.hide_render = True
        target.hide_viewport = False
        target.hide_render = False
        try:
            target.hide_set(False)
            target.select_set(True)
            context.view_layer.objects.active = target
        except (AttributeError, RuntimeError):
            pass
        _use_material_preview(context)
    except Exception as exc:
        _restore_runtime_body_visibility()
        try:
            _restore_skin_and_bones_projection_visibility(scene)
        except Exception as recovery_exc:
            raise RuntimeError(
                "Skin & Bones projection entry failed and automatic recovery could not "
                f"finish: {recovery_exc}"
            ) from exc
        raise
    context.scene.daf_settings.variant_family_status = (
        f"SKIN & BONES PROJECTION BODY — {target.name}"
        + (
            f" on neutral {neutral_rig.name}; load sources or rebuild preview"
            if neutral_rig is not None
            else "; load sources or rebuild preview"
        )
    )
    return target


def _call_skin_and_bones_operator(context, name, label):
    enter_skin_and_bones_projection(context)
    try:
        operation = getattr(bpy.ops.sbf, name)
        result = operation()
    except (AttributeError, RuntimeError) as exc:
        raise RuntimeError(
            f"Skin & Bones cannot run {label}. Enable the current Skin & Bones add-on and try again."
        ) from exc
    if "FINISHED" not in result:
        settings = getattr(context.scene, "sbf_settings", None)
        detail = str(getattr(settings, "status_message", "")).strip()
        raise RuntimeError(detail or f"Skin & Bones did not finish {label}.")
    return getattr(context.scene, "sbf_settings", None)


def build_skin_and_bones_projection_preview(context):
    settings = _call_skin_and_bones_operator(context, "best_preview", "projection preview")
    context.scene.daf_settings.variant_family_status = (
        "SKIN & BONES PREVIEW READY — inspect the visible projection body, then bake"
    )
    return settings


def bake_skin_and_bones_projection(context):
    settings = _call_skin_and_bones_operator(context, "bake_final", "final texture bake")
    context.scene.daf_settings.variant_family_status = (
        "SKIN & BONES BAKE READY — repair there if needed, then apply the final texture to this look"
    )
    return settings


def _skin_and_bones_final_image(settings):
    variants = getattr(settings, "appearance_variants", ())
    try:
        index = int(getattr(settings, "active_variant_index", 0))
        if 0 <= index < len(variants):
            image = getattr(variants[index], "final_image", None)
            if image is not None:
                return image
    except (IndexError, TypeError, ValueError):
        pass
    for name in ("repair_final_image", "last_baked_image"):
        value = getattr(settings, name, None)
        if value is None:
            continue
        if hasattr(value, "pixels"):
            return value
        image = bpy.data.images.get(str(value))
        if image is not None:
            return image
    return None


def apply_skin_and_bones_final_texture(context):
    """Copy S&B's latest final pixels into only the active finished Forge look."""

    settings, _target = _skin_and_bones_projection_target(context)
    source = _skin_and_bones_final_image(settings)
    if source is None:
        raise RuntimeError(
            "Skin & Bones has no final Base Color yet. Build the preview and click BAKE FINAL TEXTURE first."
        )
    state, active, bindings = _active_base_color_bindings(context)
    image = None
    try:
        image = _clone_variant_image(
            source,
            state["familyId"],
            active["variantId"],
            {},
        )
        image[TEXTURE_SOURCE_PROPERTY] = f"Skin & Bones final: {source.name}"
        try:
            if image.packed_file is None:
                image.pack()
            image.filepath_raw = ""
        except (AttributeError, OSError, RuntimeError):
            pass
        return _finish_active_base_color_install(
            context,
            state,
            active,
            bindings,
            image,
            status_detail=f"captured Skin & Bones final {source.name}",
        )
    except Exception:
        if (
            image is not None
            and bpy.data.images.get(image.name) is not None
            and image.users == 0
        ):
            bpy.data.images.remove(image)
        raise


def preview_active_variant(context):
    _restore_skin_and_bones_projection_visibility(context.scene)
    state = load_state(context.scene, required=True)
    variant = switch_variant(state["activeVariantId"], context.scene)
    for obj in list(getattr(context, "selected_objects", ())):
        try:
            obj.select_set(False)
        except RuntimeError:
            pass
    bodies = _restore_runtime_body_visibility()
    if bodies:
        try:
            context.view_layer.objects.active = bodies[0]
        except (AttributeError, RuntimeError):
            pass
    _use_material_preview(context)
    context.scene.daf_settings.variant_family_status = (
        f"PREVIEWING LOOK — {variant['displayName']}"
    )
    return variant


def _remove_imported_objects(objects):
    for obj in reversed(list(objects)):
        if obj is None or obj.name not in bpy.data.objects:
            continue
        object_type = str(obj.type)
        data = getattr(obj, "data", None)
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0:
            collection = (
                bpy.data.meshes
                if object_type == "MESH"
                else bpy.data.armatures
                if object_type == "ARMATURE"
                else None
            )
            if collection is not None:
                try:
                    collection.remove(data)
                except (ReferenceError, RuntimeError):
                    pass


def _rollback_variant_import(imported, before_data, original_state, scene):
    _remove_imported_objects(imported)
    for collection, existing in before_data:
        for datablock in list(set(collection) - existing):
            if getattr(datablock, "users", 1) != 0:
                continue
            try:
                collection.remove(datablock)
            except (ReferenceError, RuntimeError):
                pass
    store_state(original_state, scene)
    switch_variant(original_state["activeVariantId"], scene)


def import_appearance_variant(context, filepath):
    path = Path(bpy.path.abspath(str(filepath)))
    if not path.is_file() or path.suffix.lower() not in {".glb", ".gltf"}:
        raise RuntimeError("Choose a Skin & Bones .glb or .gltf appearance export.")
    original_state = load_state(context.scene, required=True)
    state = original_state
    before = set(bpy.data.objects)
    before_data = [
        (bpy.data.meshes, set(bpy.data.meshes)),
        (bpy.data.armatures, set(bpy.data.armatures)),
        (bpy.data.materials, set(bpy.data.materials)),
        (bpy.data.images, set(bpy.data.images)),
    ]
    try:
        result = bpy.ops.import_scene.gltf(filepath=str(path))
    except Exception:
        imported = sorted(
            set(bpy.data.objects) - before,
            key=lambda obj: obj.name.lower(),
        )
        _rollback_variant_import(
            imported,
            before_data,
            original_state,
            context.scene,
        )
        raise
    if "FINISHED" not in result:
        imported = sorted(
            set(bpy.data.objects) - before,
            key=lambda obj: obj.name.lower(),
        )
        _rollback_variant_import(
            imported,
            before_data,
            original_state,
            context.scene,
        )
        raise RuntimeError("Blender did not finish importing the appearance variant.")
    imported = sorted(set(bpy.data.objects) - before, key=lambda obj: obj.name.lower())
    try:
        armatures = [obj for obj in imported if obj.type == "ARMATURE"]
        if len(armatures) != 1:
            raise RuntimeError(
                "A variant appearance export must contain exactly one Skin & Bones armature."
            )
        armature = armatures[0]
        handoff = handoff_from_armature(armature)
        manifest_handoff = _manifest_handoff(path)
        if (
            manifest_handoff is not None
            and model.stable_json(manifest_handoff) != model.stable_json(handoff)
        ):
            raise RuntimeError(
                "Skin & Bones GLB extras disagree with the sibling .glb.sbf.json appearance_family record."
            )
        contract = _rig_contract(armature)
        appearance = capture_appearance(armature, imported)
        state = model.add_variant(
            state,
            handoff,
            contract,
            appearance=appearance,
        )
        _stamp_variant_objects(state)
        store_state(state, context.scene)
        switch_variant(handoff["variant_id"], context.scene)
        return model.variant_by_id(state, handoff["variant_id"])
    except Exception as exc:
        _rollback_variant_import(
            imported,
            before_data,
            original_state,
            context.scene,
        )
        if isinstance(exc, ValueError):
            raise RuntimeError(str(exc)) from exc
        raise


def mark_action_for_family(action, armature=None, scene=None):
    """New approved content joins the shared layer unless already an override."""

    scene = _scene(scene)
    state = load_state(scene)
    if state is None or bool(action.get("dsb_draft", False)):
        return action
    scope = str(action.get(ACTION_SCOPE_PROPERTY, ""))
    if scope == model.ACTION_SCOPE_OVERRIDE:
        action[ACTION_FAMILY_PROPERTY] = state["familyId"]
        return action
    clip_id = animation_library.ensure_clip_id(action)
    action[ACTION_SCOPE_PROPERTY] = model.ACTION_SCOPE_SHARED
    action[ACTION_FAMILY_PROPERTY] = state["familyId"]
    action[ACTION_SHARED_ID_PROPERTY] = clip_id
    state = model.register_shared_actions(
        state,
        list(state["shared"].get("actionIds", [])) + [clip_id],
    )
    store_state(state, scene)
    return action


def action_status(action, scene=None):
    state = load_state(scene)
    if state is None or action is None:
        return "STANDALONE"
    scope = str(action.get(ACTION_SCOPE_PROPERTY, ""))
    if scope == model.ACTION_SCOPE_OVERRIDE:
        return "OVERRIDE"
    shared_id = str(
        action.get(ACTION_SHARED_ID_PROPERTY, "")
        or action.get(animation_library.CLIP_ID_PROPERTY, "")
    )
    if shared_id in set(state["shared"].get("actionIds", [])):
        return (
            "SHARED"
            if state["activeVariantId"] == state["baseVariantId"]
            else "INHERITED"
        )
    return "STANDALONE"


def effective_actions(actions, scene=None):
    state = load_state(scene)
    if state is None:
        return list(actions)
    variant = model.variant_by_id(state)
    overrides = variant.get("actionOverrides", {})
    by_id = {
        str(action.get(animation_library.CLIP_ID_PROPERTY, "")): action
        for action in bpy.data.actions
        if str(action.get(animation_library.CLIP_ID_PROPERTY, ""))
    }
    result = []
    for action in actions:
        scope = str(action.get(ACTION_SCOPE_PROPERTY, ""))
        owner_variant = str(action.get(ACTION_VARIANT_PROPERTY, ""))
        if scope == model.ACTION_SCOPE_OVERRIDE:
            if owner_variant == variant["variantId"]:
                result.append(action)
            continue
        shared_id = str(
            action.get(ACTION_SHARED_ID_PROPERTY, "")
            or action.get(animation_library.CLIP_ID_PROPERTY, "")
        )
        replacement = overrides.get(shared_id)
        if replacement:
            override = by_id.get(str(replacement.get("overrideActionId", "")))
            if override is not None and override not in result:
                result.append(override)
            continue
        result.append(action)
    return list(dict.fromkeys(result))


def _shared_action(action, state):
    if str(action.get(ACTION_SCOPE_PROPERTY, "")) == model.ACTION_SCOPE_OVERRIDE:
        shared_id = str(action.get(ACTION_SHARED_ID_PROPERTY, ""))
    else:
        shared_id = str(
            action.get(ACTION_SHARED_ID_PROPERTY, "")
            or action.get(animation_library.CLIP_ID_PROPERTY, "")
        )
    source = animation_library.find_action_by_clip_id(shared_id)
    if source is None:
        raise RuntimeError("The shared family Action for this logical clip is missing.")
    if shared_id not in set(state["shared"].get("actionIds", [])):
        raise RuntimeError("The selected Action is not registered in the shared family layer.")
    return source, shared_id


def create_action_override(context, action):
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    source, shared_id = _shared_action(action, state)
    if shared_id in variant.get("actionOverrides", {}):
        raise RuntimeError("This appearance variant already overrides the selected Action.")
    if context.scene.daf_settings.animation_library_edit_source_clip_id:
        raise RuntimeError("Finish or cancel the current animation edit first.")
    from . import DRAFT_ACTION_NAMES

    kind = animation_library.infer_action_kind(source)
    draft_name = DRAFT_ACTION_NAMES.get(kind, "DSB_DRAFT_Variant_Edit")
    if bpy.data.actions.get(draft_name) is not None:
        raise RuntimeError(
            f"Finish or delete the existing draft {draft_name!r} before creating an override."
        )
    override = source.copy()
    override.name = draft_name
    override_id = "clip_" + uuid.uuid4().hex
    override[animation_library.CLIP_ID_PROPERTY] = override_id
    override[ACTION_SCOPE_PROPERTY] = model.ACTION_SCOPE_OVERRIDE
    override[ACTION_FAMILY_PROPERTY] = state["familyId"]
    override[ACTION_VARIANT_PROPERTY] = variant["variantId"]
    override[ACTION_SHARED_ID_PROPERTY] = shared_id
    override[ACTION_OVERRIDE_ID_PROPERTY] = override_id
    override["dsb_draft"] = True
    override["dsb_approved"] = False
    override["dsb_draft_kind"] = kind
    if override.get("dsb_offensive_action_json"):
        override["dsb_offensive_previewed"] = False
        override["dsb_offensive_preview_count"] = 0
        for name in (
            "dsb_offensive_previewed_before_approval",
            "dsb_offensive_character_recipe",
            offensive_motion.MOTION_VALIDATION_PROPERTY,
            offensive_motion.MOTION_POSE_HEALTH_PROPERTY,
            offensive_motion.TARGETING_PROPERTY,
            "dsb_offensive_motion_bypass_json",
            "dsb_motion_preview_digest",
            "dsb_motion_bypass_active",
            "dsb_motion_approval_mode",
        ):
            if name in override:
                del override[name]
        if override.get(offensive_motion.MOTION_RECIPE_PROPERTY):
            override["dsb_motion_validation_status"] = "STALE"
            override["dsb_motion_validation_reason"] = (
                "Character Variant override requires a new baked-path validation"
            )
    override.use_fake_user = True
    if context.active_object is not None:
        try:
            armature = _find_selected_armature(context)
        except RuntimeError:
            armature = bpy.data.objects.get("DSB_DAMAGE_RIG")
    else:
        armature = bpy.data.objects.get("DSB_DAMAGE_RIG")
    if armature is None or armature.type != "ARMATURE":
        raise RuntimeError("Select the active family armature before creating an override.")
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = override
    state = model.set_action_override(
        state,
        shared_id,
        override_id,
        variant["variantId"],
    )
    store_state(state, context.scene)
    animation_library.select_action(context.scene.daf_settings, override)
    context.scene.daf_settings.animation_library_status = (
        f"VARIANT OVERRIDE DRAFT — {variant['displayName']} / {source.name}"
    )
    return override


def revert_action_override(context, action):
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    _source, shared_id = _shared_action(action, state)
    record = variant.get("actionOverrides", {}).get(shared_id)
    if not record:
        raise RuntimeError("The selected Action is inherited; there is no override to revert.")
    override = animation_library.find_action_by_clip_id(record["overrideActionId"])
    state, _removed = model.remove_action_override(
        state,
        shared_id,
        variant["variantId"],
    )
    if override is not None:
        animation_library._remove_action(override, unlink_nla=True)
    store_state(state, context.scene)
    source = animation_library.find_action_by_clip_id(shared_id)
    if source is not None:
        animation_library.select_action(context.scene.daf_settings, source)
    return source


def _select_effective_action(scene):
    settings = getattr(scene, "daf_settings", None)
    state = load_state(scene)
    if settings is None or state is None:
        return None
    selected = animation_library.find_action_by_clip_id(
        str(settings.animation_library_active_clip_id)
    )
    if selected is None:
        return None
    shared_id = str(
        selected.get(ACTION_SHARED_ID_PROPERTY, "")
        or selected.get(animation_library.CLIP_ID_PROPERTY, "")
    )
    effective_id, _status = model.resolve_action_id(state, shared_id)
    effective = animation_library.find_action_by_clip_id(effective_id)
    if effective is not None:
        animation_library.select_action(settings, effective)
    return effective


def require_regular_action_edit_allowed(action, scene=None):
    state = load_state(scene)
    if state is None or action_status(action, scene) != "INHERITED":
        return
    raise RuntimeError(
        "This is an INHERITED family Action. Use CREATE VARIANT OVERRIDE, or use "
        "EDIT SHARED FAMILY ACTION and confirm the family-wide edit."
    )


def _deformation():
    from . import deformation_authoring

    return deformation_authoring


def _physical_damage_records(region_id=None):
    deformation = _deformation()
    registry = deformation._load_registry(migrate_legacy=False)
    records = []
    for region in registry.get("regions", []):
        if region_id is not None and str(region.get("regionId", "")) != str(region_id):
            continue
        attached, _detached = deformation._resolve_region_pair(region)
        payload = deformation._metadata(attached)
        for name, entry in payload.get("keys", {}).items():
            if deformation._key(attached, name) is None:
                continue
            records.append(
                {
                    "name": name,
                    "damageKeyId": str(entry.get("damageKeyId", "")),
                    "regionId": str(region.get("regionId", "")),
                    "ownerVariantId": str(entry.get("ownerVariantId", "")),
                    "sharedDamageKeyId": str(entry.get("sharedDamageKeyId", "")),
                    "entry": entry,
                }
            )
    return records


def effective_damage_key_names(region_id, names):
    state = load_state()
    if state is None:
        return list(names)
    by_name = {record["name"]: record for record in _physical_damage_records(region_id)}
    records = [by_name[name] for name in names if name in by_name]
    return model.effective_damage_key_names(state, region_id, records)


def effective_progressive_collection(collection):
    state = load_state()
    if state is None:
        return copy.deepcopy(collection)
    result = copy.deepcopy(collection)
    result["sites"] = model.effective_progressive_sites(
        state,
        result.get("sites", []),
    )
    active = str(result.get("activeSiteGuid", ""))
    visible = {str(site.get("siteGuid", "")) for site in result["sites"]}
    if active not in visible:
        result["activeSiteGuid"] = next(iter(visible), "")
    result["siteCount"] = len(result["sites"])
    return result


def merge_progressive_collection(full_collection, effective_collection):
    """Persist edits to visible records without deleting hidden variant records."""

    state = load_state()
    if state is None:
        return copy.deepcopy(effective_collection)
    result = copy.deepcopy(full_collection)
    original_effective = model.effective_progressive_sites(
        state,
        full_collection.get("sites", []),
    )
    before_visible = {
        str(site.get("siteGuid", "")): site for site in original_effective
    }
    after_visible = {
        str(site.get("siteGuid", "")): site
        for site in effective_collection.get("sites", [])
    }
    settings = getattr(bpy.context.scene, "daf_settings", None)
    shared_edit_enabled = bool(
        getattr(settings, "variant_shared_damage_edit_enabled", False)
    )
    active_variant = model.variant_by_id(state)["variantId"]
    for guid in sorted(set(before_visible) | set(after_visible)):
        before = before_visible.get(guid)
        after = after_visible.get(guid)
        if before is not None and after is not None:
            if model.stable_json(before) == model.stable_json(after):
                continue
            owner = str(before.get("ownerVariantId", ""))
            if owner == active_variant or shared_edit_enabled:
                continue
            raise RuntimeError(
                "This Progressive Site is INHERITED. Create a variant override "
                "or explicitly unlock shared family Damage editing."
            )
        if before is None and after is not None:
            owner = str(after.get("ownerVariantId", ""))
            if owner == active_variant or shared_edit_enabled:
                continue
            raise RuntimeError(
                "Creating a shared Progressive Site requires explicit shared "
                "family Damage editing."
            )
        owner = str(before.get("ownerVariantId", ""))
        if owner == active_variant:
            raise RuntimeError(
                "Use REVERT TO SHARED to remove a variant Progressive Site override."
            )
        if not shared_edit_enabled:
            raise RuntimeError(
                "Deleting a shared Progressive Site requires explicit shared "
                "family Damage editing."
            )
    by_guid = {
        str(site.get("siteGuid", "")): copy.deepcopy(site)
        for site in result.get("sites", [])
    }
    visible_before = set(before_visible)
    visible_after = {
        str(site.get("siteGuid", ""))
        for site in effective_collection.get("sites", [])
    }
    for deleted_guid in visible_before - visible_after:
        by_guid.pop(deleted_guid, None)
    for site in effective_collection.get("sites", []):
        by_guid[str(site.get("siteGuid", ""))] = copy.deepcopy(site)
    result.update(
        {
            key: copy.deepcopy(value)
            for key, value in effective_collection.items()
            if key not in {"sites", "siteCount"}
        }
    )
    result["sites"] = list(by_guid.values())
    result["siteCount"] = len(result["sites"])
    return result


def _copy_shape_key(source, target):
    if len(source.data) != len(target.data):
        raise RuntimeError("Damage Key copy-on-write point counts differ.")
    for source_point, target_point in zip(source.data, target.data):
        target_point.co = source_point.co
    target.slider_min = source.slider_min
    target.slider_max = source.slider_max
    target.value = 0.0
    target.mute = False


def _unique_override_key_name(source_name, export_identity, suffix=""):
    token = model.safe_identifier(export_identity).replace("-", "_")
    tail = f"__{token}{suffix}"
    return (str(source_name)[: max(1, 63 - len(tail))] + tail)[:63]


def _clone_damage_key(context, shared_id, *, owner_role="DAMAGE_KEY", suffix=""):
    deformation = _deformation()
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    record = next(
        (
            value
            for value in _physical_damage_records()
            if value["damageKeyId"] == str(shared_id)
            and not value["ownerVariantId"]
        ),
        None,
    )
    if record is None:
        raise RuntimeError(f"Shared Damage Key {shared_id!r} is missing.")
    registry = deformation._load_registry(migrate_legacy=False)
    region = next(
        value
        for value in registry.get("regions", [])
        if str(value.get("regionId", "")) == record["regionId"]
    )
    attached, detached = deformation._resolve_region_pair(region)
    source_attached = deformation._key(attached, record["name"])
    source_detached = deformation._key(detached, record["name"]) if detached else None
    previous_region = registry.get("activeRegionId", "")
    deformation._set_active_region(record["regionId"], context)
    name = _unique_override_key_name(
        record["name"],
        variant["exportIdentity"],
        suffix,
    )
    if deformation._key(attached, name) is not None:
        raise RuntimeError(f"Variant Damage Key {name!r} already exists.")
    entry = copy.deepcopy(record["entry"])
    override_id = progressive_sites.opaque_id("damage_key")
    entry.update(
        {
            "name": name,
            "damageKeyId": override_id,
            "ownerVariantId": variant["variantId"],
            "sharedDamageKeyId": record["damageKeyId"],
            "variantOwnerRole": owner_role,
            "status": "VARIANT_OVERRIDE_DRAFT",
            "validationStatus": "NOT_VALIDATED",
            "previewEnabled": False,
        }
    )
    for field in (
        "goreGeneratedMeshIds",
        "goreGeneratedNodeNames",
        "goreGeometryDigests",
        "goreGenerationDigests",
        "goreTriangleCounts",
        "goreValidationMeasurements",
    ):
        entry.pop(field, None)
    try:
        _attached, _detached, target_attached, target_detached = deformation._ensure_key_pair(
            name,
            metadata_entry=entry,
        )
        _copy_shape_key(source_attached, target_attached)
        if detached is not None:
            _copy_shape_key(source_detached, target_detached)
            deformation._link_detached_value(attached, detached, name)
        payload = deformation._metadata(attached)
        payload["keys"][name] = entry
        overlay = entry.get("surfaceGoreOverlay")
        if isinstance(overlay, dict):
            try:
                normalized = deformation.trauma_field.normalize_gore_overlay(overlay)
                if normalized.get("goreOverlayEnabled") and normalized.get("goreRaisedEnabled"):
                    deformation.rebuild_raised_gore_for_key(
                        region,
                        attached,
                        detached,
                        name,
                        entry,
                    )
            except (TypeError, ValueError):
                pass
        deformation._store_metadata(attached, detached, payload)
    except Exception:
        deformation._remove_generated_gore_objects(record["regionId"], name)
        deformation._remove_key(attached, name)
        if detached is not None:
            deformation._remove_key(detached, name)
        raise
    finally:
        if previous_region and previous_region != record["regionId"]:
            deformation._set_active_region(previous_region, context)
    return {
        "sharedDamageKeyId": record["damageKeyId"],
        "sharedName": record["name"],
        "overrideDamageKeyId": override_id,
        "overrideName": name,
        "regionId": record["regionId"],
        "ownerVariantId": variant["variantId"],
        "ownerRole": owner_role,
    }


def create_damage_key_override(context):
    settings = context.scene.daf_settings
    deformation = _deformation()
    _registry, region, attached, _detached = deformation._resolve_active_region(context)
    name = str(settings.deformation_active_key)
    entry = deformation._metadata(attached).get("keys", {}).get(name)
    if not entry:
        raise RuntimeError("Select an inherited Damage Key first.")
    if entry.get("ownerVariantId"):
        raise RuntimeError("The selected Damage Key is already a variant override.")
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    shared_id = str(entry.get("damageKeyId", ""))
    if shared_id in variant.get("damageKeyOverrides", {}):
        raise RuntimeError("This appearance already overrides the selected Damage Key.")
    record = _clone_damage_key(context, shared_id)
    state = model.set_damage_key_override(state, record, variant["variantId"])
    store_state(state, context.scene)
    deformation._set_active_region(record["regionId"], context)
    deformation._select_key(settings, record["overrideName"])
    settings.variant_family_status = f"DAMAGE OVERRIDE — {record['overrideName']}"
    return record


def _delete_variant_damage_key(record):
    deformation = _deformation()
    registry = deformation._load_registry(migrate_legacy=False)
    region = next(
        (
            value
            for value in registry.get("regions", [])
            if str(value.get("regionId", "")) == str(record.get("regionId", ""))
        ),
        None,
    )
    if region is None:
        return
    attached, detached = deformation._resolve_region_pair(region)
    name = str(record.get("overrideName", ""))
    deformation._remove_generated_gore_objects(record.get("regionId"), name)
    deformation._remove_key(attached, name)
    if detached is not None:
        deformation._remove_key(detached, name)
    payload = deformation._metadata(attached)
    payload.get("keys", {}).pop(name, None)
    deformation._store_metadata(attached, detached, payload)


def revert_damage_key_override(context):
    settings = context.scene.daf_settings
    deformation = _deformation()
    _registry, _region, attached, _detached = deformation._resolve_active_region(context)
    entry = deformation._metadata(attached).get("keys", {}).get(
        str(settings.deformation_active_key), {}
    )
    shared_id = str(entry.get("sharedDamageKeyId", ""))
    if not shared_id:
        raise RuntimeError("The selected Damage Key is inherited; there is no override to revert.")
    state = load_state(context.scene, required=True)
    state, record = model.remove_damage_key_override(state, shared_id)
    if not record:
        raise RuntimeError("The selected Damage Key is not an independent override record.")
    _delete_variant_damage_key(record)
    store_state(state, context.scene)
    deformation._set_active_region(record["regionId"], context)
    deformation._select_key(settings, record["sharedName"])
    return record


def _full_progressive_collection():
    deformation = _deformation()
    registry = deformation._load_registry(migrate_legacy=False)
    return registry, progressive_sites.normalize_sites(
        registry.get("progressiveDamageSites")
    )


def create_progressive_site_override(context):
    settings = context.scene.daf_settings
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    registry, collection = _full_progressive_collection()
    shared_guid = str(settings.progression_active_site_guid)
    site = progressive_sites.site_by_guid(collection, shared_guid)
    if site.get("ownerVariantId"):
        raise RuntimeError("The selected Progressive Site is already a variant override.")
    if shared_guid in variant.get("progressiveSiteOverrides", {}):
        raise RuntimeError("This appearance already overrides the selected Progressive Site.")
    plan = model.progressive_clone_plan(site, _physical_damage_records())
    if plan["errors"]:
        raise RuntimeError(" ".join(plan["errors"]))
    owned = []
    try:
        for index, key_id in enumerate(plan["damageKeyIds"]):
            owned.append(
                _clone_damage_key(
                    context,
                    key_id,
                    owner_role="PROGRESSIVE_SITE",
                    suffix=f"_s{index + 1}",
                )
            )
        mapping = {value["sharedDamageKeyId"]: value for value in owned}
        override = copy.deepcopy(site)
        override_guid = progressive_sites.opaque_id("site")
        override["siteGuid"] = override_guid
        override["siteId"] = progressive_sites.safe_site_id(
            f"{site['siteId']}_{variant['exportIdentity']}"
        )
        override["displayName"] = f"{site['displayName']} — {variant['displayName']}"
        override["ownerVariantId"] = variant["variantId"]
        override["sharedSiteGuid"] = shared_guid
        override["validationStatus"] = "NOT_VALIDATED"
        override["validationDigest"] = ""
        override["enabledForExport"] = False
        for stage_name, stage in override.get("stages", {}).items():
            replacement = mapping.get(str(stage.get("damageKeyId", "")))
            if replacement is None:
                continue
            stage["sharedDamageKeyId"] = str(stage.get("damageKeyId", ""))
            stage["damageKeyId"] = replacement["overrideDamageKeyId"]
            stage["deformationKeyName"] = replacement["overrideName"]
            stage["stageId"] = progressive_sites.opaque_id("stage")
            stage["validationStatus"] = "NOT_VALIDATED"
            stage["ownerVariantId"] = variant["variantId"]
        override = progressive_sites.normalize_site(override)
        collection["sites"].append(override)
        collection["activeSiteGuid"] = override_guid
        collection = progressive_sites.normalize_sites(collection)
        registry["progressiveDamageSites"] = collection
        _deformation()._store_registry(registry)
        record = {
            "sharedSiteGuid": shared_guid,
            "overrideSiteGuid": override_guid,
            "ownerVariantId": variant["variantId"],
            "ownedDamageKeys": owned,
        }
        state = model.set_progressive_site_override(
            state,
            record,
            variant["variantId"],
        )
        store_state(state, context.scene)
        settings.progression_active_site_guid = override_guid
        from . import progressive_authoring

        progressive_authoring.sync_settings_from_site(context, override)
        return record
    except Exception:
        for record in reversed(owned):
            _delete_variant_damage_key(record)
        raise


def revert_progressive_site_override(context):
    settings = context.scene.daf_settings
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    active_guid = str(settings.progression_active_site_guid)
    shared_guid = next(
        (
            shared
            for shared, record in variant.get("progressiveSiteOverrides", {}).items()
            if str(record.get("overrideSiteGuid", "")) == active_guid
        ),
        "",
    )
    if not shared_guid:
        raise RuntimeError("The selected Progressive Site is inherited; there is no override to revert.")
    state, record = model.remove_progressive_site_override(state, shared_guid)
    registry, collection = _full_progressive_collection()
    collection["sites"] = [
        site
        for site in collection.get("sites", [])
        if str(site.get("siteGuid", "")) != str(record["overrideSiteGuid"])
    ]
    collection["activeSiteGuid"] = shared_guid
    registry["progressiveDamageSites"] = progressive_sites.normalize_sites(collection)
    _deformation()._store_registry(registry)
    for key_record in reversed(record.get("ownedDamageKeys", [])):
        _delete_variant_damage_key(key_record)
    store_state(state, context.scene)
    settings.progression_active_site_guid = shared_guid
    from . import progressive_authoring

    progressive_authoring.sync_settings_from_site(context)
    return record


def damage_status(context):
    state = load_state(context.scene)
    if state is None:
        return {"status": "STANDALONE", "kind": ""}
    settings = context.scene.daf_settings
    variant = model.variant_by_id(state)
    if str(settings.variant_damage_override_unit) == "PROGRESSIVE_SITE":
        active = str(settings.progression_active_site_guid)
        for shared, record in variant.get("progressiveSiteOverrides", {}).items():
            if active == str(record.get("overrideSiteGuid", "")):
                return {"status": "OVERRIDE", "kind": model.PROGRESSIVE_SITE_KIND, "sharedId": shared}
        return {"status": "INHERITED", "kind": model.PROGRESSIVE_SITE_KIND, "sharedId": active}
    deformation = _deformation()
    try:
        _registry, region, attached, _detached = deformation._resolve_active_region(context)
        name = str(settings.deformation_active_key)
        entry = deformation._metadata(attached).get("keys", {}).get(name, {})
    except Exception:
        return {"status": "NONE", "kind": model.DAMAGE_KEY_KIND}
    if str(entry.get("ownerVariantId", "")) == variant["variantId"]:
        return {
            "status": "OVERRIDE",
            "kind": model.DAMAGE_KEY_KIND,
            "sharedId": str(entry.get("sharedDamageKeyId", "")),
            "name": name,
        }
    return {
        "status": "INHERITED",
        "kind": model.DAMAGE_KEY_KIND,
        "sharedId": str(entry.get("damageKeyId", "")),
        "name": name,
        "regionId": str(region.get("regionId", "")),
    }


def damage_object_is_effective(obj):
    state = load_state()
    if state is None:
        return True
    key_name = str(
        obj.get("dsb_gore_deformation_key", "")
        or obj.get("dsb_stain_deformation_key", "")
    )
    region_id = str(
        obj.get("dsb_gore_region_id", "")
        or obj.get("dsb_stain_region_id", "")
    )
    if not key_name:
        return True
    effective = set(
        effective_damage_key_names(
            region_id,
            [record["name"] for record in _physical_damage_records(region_id)],
        )
    )
    return key_name in effective


def _resolved_action_revision():
    records = []
    for action in effective_actions(list(bpy.data.actions)):
        if bool(action.get("dsb_draft", False)) or not bool(
            action.get("dsb_approved", False)
        ):
            continue
        curves = []
        for curve in animation_library.iter_action_fcurves(action):
            curves.append(
                {
                    "dataPath": str(curve.data_path),
                    "arrayIndex": int(curve.array_index),
                    "points": [
                        {
                            "co": [float(point.co[0]), float(point.co[1])],
                            "handleLeft": [
                                float(point.handle_left[0]),
                                float(point.handle_left[1]),
                            ],
                            "handleRight": [
                                float(point.handle_right[0]),
                                float(point.handle_right[1]),
                            ],
                            "interpolation": str(point.interpolation),
                        }
                        for point in curve.keyframe_points
                    ],
                }
            )
        records.append(
            {
                "clipId": str(
                    action.get(animation_library.CLIP_ID_PROPERTY, "")
                ),
                "name": action.name,
                "kind": str(action.get("dsb_approved_kind", "")),
                "offensive": str(action.get("dsb_offensive_action_json", "")),
                "recipe": str(action.get("dsb_offensive_character_recipe", "")),
                "motionRecipe": str(action.get(offensive_motion.MOTION_RECIPE_PROPERTY, "")),
                "motionValidation": str(action.get(offensive_motion.MOTION_VALIDATION_PROPERTY, "")),
                "offensiveTargeting": str(action.get(offensive_motion.TARGETING_PROPERTY, "")),
                "curves": sorted(
                    curves,
                    key=lambda value: (value["dataPath"], value["arrayIndex"]),
                ),
            }
        )
    return model.canonical_digest(
        sorted(records, key=lambda value: value["clipId"])
    )


def _resolved_damage_revision():
    physical = _physical_damage_records()
    names_by_region = {}
    for record in physical:
        names_by_region.setdefault(record["regionId"], []).append(record["name"])
    effective_by_region = {
        region_id: set(effective_damage_key_names(region_id, names))
        for region_id, names in names_by_region.items()
    }
    records = [
        {
            "regionId": record["regionId"],
            "damageKeyId": record["damageKeyId"],
            "name": record["name"],
            "entry": copy.deepcopy(record["entry"]),
        }
        for record in physical
        if record["name"] in effective_by_region.get(record["regionId"], set())
    ]
    try:
        _registry, collection = _full_progressive_collection()
        sites = effective_progressive_collection(collection).get("sites", [])
    except (KeyError, RuntimeError, TypeError, ValueError):
        sites = []
    return model.canonical_digest(
        {
            "keys": sorted(
                records,
                key=lambda value: (value["regionId"], value["damageKeyId"]),
            ),
            "progressiveSites": sites,
        }
    )


def export_provenance(scene=None):
    state = load_state(scene)
    if state is None:
        return None
    provenance = model.export_provenance(state)
    resolved_content_revision = model.canonical_digest(
        {
            "actions": _resolved_action_revision(),
            "damage": _resolved_damage_revision(),
        }
    )[:20]
    effective_revision = model.canonical_digest(
        {
            "structuralRevision": provenance["effectiveForgeRevision"],
            "resolvedContentRevision": resolved_content_revision,
        }
    )[:20]
    provenance["resolvedContentRevision"] = resolved_content_revision
    provenance["effectiveForgeRevision"] = effective_revision
    provenance["effectiveForgeVariantIdentity"] = (
        f"{provenance['technicalFamilyId']}:"
        f"{provenance['appearanceVariantId']}:"
        f"{effective_revision}"
    )
    return provenance


@contextmanager
def export_context(context, settings, state):
    """Stage only the active variant's appearance, morphs, and provenance."""

    family = load_state(context.scene)
    if family is None:
        yield None
        return
    variant = model.variant_by_id(family)
    if family["familySource"] == model.FAMILY_SOURCE_SBF:
        handoff = model.require_handoff(variant["handoff"])
        expected_fields = {
            "family_id": family["familyId"],
            "technical_body_schema": family["technicalBodySchema"],
            "technical_body_schema_version": family["technicalBodySchemaVersion"],
            "technical_body_fingerprint": family["technicalBodyFingerprint"],
        }
        mismatched = [
            field
            for field, expected in expected_fields.items()
            if handoff.get(field) != expected
        ]
        if mismatched:
            raise RuntimeError(
                "Active variant appearance provenance no longer matches its family: "
                + ", ".join(mismatched)
                + "."
            )
        appearance_armature_name = str(
            variant.get("appearance", {}).get("armatureName", "")
        )
        if appearance_armature_name:
            appearance_armature = bpy.data.objects.get(appearance_armature_name)
            if appearance_armature is None or appearance_armature.type != "ARMATURE":
                raise RuntimeError("The active Skin & Bones appearance armature is missing.")
            current_handoff = handoff_from_armature(appearance_armature)
            if model.stable_json(current_handoff) != model.stable_json(handoff):
                raise RuntimeError(
                    "The active Skin & Bones appearance handoff changed after family ingest."
                )
            if model.canonical_rig_signature(_rig_contract(appearance_armature)) != model.canonical_rig_signature(
                family["canonicalRig"]
            ):
                raise RuntimeError(
                    "The active appearance canonical rig/coordinate contract changed after family ingest."
                )
    else:
        rig = _finished_damage_rig()
        if finished_damage_body_fingerprint(rig) != family["technicalBodyFingerprint"]:
            raise RuntimeError(
                "The finished Damage Rig/body changed after the texture family was started."
            )
        if model.canonical_rig_signature(_rig_contract(rig)) != model.canonical_rig_signature(
            family["canonicalRig"]
        ):
            raise RuntimeError(
                "The finished Damage Rig canonical rig/coordinate contract changed."
            )
        errors = texture_appearance_errors(family, variant["variantId"])
        if errors:
            raise RuntimeError(" ".join(errors))
    for shared_id, override_record in variant.get("actionOverrides", {}).items():
        override_id = str(override_record.get("overrideActionId", ""))
        override = animation_library.find_action_by_clip_id(override_id)
        if override is None:
            raise RuntimeError(
                f"Variant Action override for {shared_id!r} is missing its Blender Action."
            )
        if bool(override.get("dsb_draft", False)) or not bool(
            override.get("dsb_approved", False)
        ):
            raise RuntimeError(
                f"Variant Action override {override.name!r} must be saved and approved before export."
            )
    switch_variant(variant["variantId"], context.scene)
    provenance = export_provenance(context.scene)
    encoded = model.stable_json(provenance)
    previous_filename = str(settings.damage_authoring_filename)
    previous_properties = []
    previous_mutes = []
    active_names_by_region = {}
    for record in _physical_damage_records():
        active_names_by_region.setdefault(record["regionId"], []).append(record["name"])
    effective_by_region = {
        region_id: set(effective_damage_key_names(region_id, names))
        for region_id, names in active_names_by_region.items()
    }
    appearance_bodies = set(_appearance_body_objects())
    runtime_rig = bpy.data.objects.get(str(state.get("authoring_rig", "")))
    try:
        settings.damage_authoring_filename = variant["exportIdentity"]
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                region_id = str(obj.get("dsb_deformation_region", ""))
                keys = getattr(obj.data, "shape_keys", None)
                if keys is not None and region_id in effective_by_region:
                    for key in keys.key_blocks:
                        if key == keys.reference_key:
                            continue
                        previous_mutes.append((key, bool(key.mute)))
                        key.mute = key.name not in effective_by_region[region_id]
            if obj == runtime_rig or obj in appearance_bodies:
                metadata_names = [
                    PROVENANCE_PROPERTY,
                    ACTIVE_EXPORT_PROPERTY,
                    model.SBF_FAMILY_ID_PROPERTY,
                    model.SBF_VARIANT_ID_PROPERTY,
                    model.SBF_BODY_FINGERPRINT_PROPERTY,
                ]
                before = {
                    name: (name in obj, obj.get(name))
                    for name in metadata_names
                }
                previous_properties.append((obj, before))
                obj[PROVENANCE_PROPERTY] = encoded
                obj[ACTIVE_EXPORT_PROPERTY] = variant["variantId"]
                if family["familySource"] == model.FAMILY_SOURCE_SBF:
                    obj[model.SBF_FAMILY_ID_PROPERTY] = family["familyId"]
                    obj[model.SBF_VARIANT_ID_PROPERTY] = variant["variantId"]
                    obj[model.SBF_BODY_FINGERPRINT_PROPERTY] = family[
                        "technicalBodyFingerprint"
                    ]
                else:
                    for name in (
                        model.SBF_FAMILY_ID_PROPERTY,
                        model.SBF_VARIANT_ID_PROPERTY,
                        model.SBF_BODY_FINGERPRINT_PROPERTY,
                    ):
                        if name in obj:
                            del obj[name]
        yield provenance
    finally:
        settings.damage_authoring_filename = previous_filename
        for key, muted in previous_mutes:
            try:
                key.mute = muted
            except ReferenceError:
                pass
        for obj, values in previous_properties:
            if obj is None or obj.name not in bpy.data.objects:
                continue
            for name, (existed, value) in values.items():
                if existed:
                    obj[name] = value
                elif name in obj:
                    del obj[name]


def _repair_resized_socket_scale_for_export(attachment_sockets, authoring_state):
    """Leave valid authored sockets byte-for-byte alone; repair resized scale only."""

    runtime_rig = bpy.data.objects.get(str(authoring_state.get("authoring_rig", "")))
    try:
        return attachment_sockets.runtime_socket_contract(
            authoring_state,
            runtime_rig=runtime_rig,
        )
    except RuntimeError as exc:
        # Complete Damage never supports socket scale. Some older files acquired
        # it as a side effect of resizing the whole character after socket
        # placement. The repair preserves the artist's local position and
        # quaternion; every other socket failure remains an ordinary hard gate.
        if "unsupported local scale" not in str(exc):
            raise
    attachment_sockets.ensure_standard_sockets(runtime_rig)
    return attachment_sockets.runtime_socket_contract(
        authoring_state,
        runtime_rig=runtime_rig,
    )


def batch_export_ready_variants(context):
    from . import attachment_sockets, damage_authoring

    family = load_state(context.scene, required=True)
    settings = context.scene.daf_settings
    original_variant = family["activeVariantId"]
    original_filename = str(settings.damage_authoring_filename)
    authoring_state = damage_authoring._load_state()
    if authoring_state is None:
        raise RuntimeError("Build the Complete Damage authoring asset before batch export.")
    if family["familySource"] == model.FAMILY_SOURCE_FORGE_TEXTURE:
        damage_authoring.restore_finished_source_transform_proof(context)
    _repair_resized_socket_scale_for_export(attachment_sockets, authoring_state)
    exported = []
    skipped = []
    try:
        for variant in family["variants"]:
            switch_variant(variant["variantId"], context.scene)
            try:
                paths = damage_authoring._export_asset(
                    context,
                    settings,
                    authoring_state,
                )
            except Exception as exc:
                skipped.append(
                    {"variantId": variant["variantId"], "reason": str(exc)}
                )
                continue
            exported.append(
                {
                    "variantId": variant["variantId"],
                    "exportIdentity": variant["exportIdentity"],
                    "paths": list(paths),
                }
            )
    finally:
        settings.damage_authoring_filename = original_filename
        switch_variant(original_variant, context.scene)
    return {"exported": exported, "skipped": skipped}


def export_active_variant(context):
    from . import attachment_sockets, damage_authoring

    family = load_state(context.scene, required=True)
    variant = model.variant_by_id(family)
    authoring_state = damage_authoring._load_state()
    if authoring_state is None:
        raise RuntimeError("Build the Complete Damage authoring asset before export.")
    if family["familySource"] == model.FAMILY_SOURCE_FORGE_TEXTURE:
        damage_authoring.restore_finished_source_transform_proof(context)
    _repair_resized_socket_scale_for_export(attachment_sockets, authoring_state)
    paths = damage_authoring._export_asset(
        context,
        context.scene.daf_settings,
        authoring_state,
    )
    return variant, paths


class _VariantOperator(Operator):
    def failed(self, context, exc):
        settings = getattr(context.scene, "daf_settings", None)
        if settings is not None:
            settings.variant_family_status = f"ERROR — {exc}"
        self.report({"ERROR"}, str(exc))
        return {"CANCELLED"}


class DAF_OT_adopt_character_variant_family(_VariantOperator):
    bl_idname = "daf.adopt_character_variant_family"
    bl_label = "Adopt as Shared Family Base"
    bl_description = "Adopt the selected approved Skin & Bones appearance and existing Forge authoring as the shared family layer"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            state = adopt_selected_as_family_base(context)
            self.report(
                {"INFO"},
                f"Adopted {state['displayName']} with {len(state['shared']['actionIds'])} shared Action(s).",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_start_finished_texture_family(_VariantOperator):
    bl_idname = "daf.start_finished_texture_family"
    bl_label = "Start Texture Variants from Finished Character"
    bl_description = "Snapshot the current finished Damage Rig look as the approved base; Actions, Damage, sockets, and geometry remain shared"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            state = adopt_finished_damage_as_texture_family(context)
            variant = model.variant_by_id(state)
            self.report(
                {"INFO"},
                f"Started texture family {state['displayName']} with approved base {variant['displayName']}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_create_forge_texture_variant(_VariantOperator):
    bl_idname = "daf.create_forge_texture_variant"
    bl_label = "Duplicate Active Look for New Texture"
    bl_description = "Create one editable material/image copy for a new skin while inheriting every Action, Damage Site, and socket"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            variant = create_forge_texture_variant(context)
            preview_active_variant(context)
            context.scene.daf_settings.variant_family_status = (
                f"DRAFT LOOK — {variant['displayName']}; edit/replace/paint its texture, then approve"
            )
            self.report(
                {"INFO"},
                f"Created draft texture look {variant['displayName']}; project or bake onto it, then approve the current look.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_approve_forge_texture_variant(_VariantOperator):
    bl_idname = "daf.approve_forge_texture_variant"
    bl_label = "Approve Current Texture Look"
    bl_description = "Snapshot and approve the active runtime material/image palette against the unchanged finished Damage Rig"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            variant = approve_forge_texture_variant(context)
            self.report({"INFO"}, f"Approved texture look {variant['displayName']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_edit_forge_texture_variant(_VariantOperator):
    bl_idname = "daf.edit_forge_texture_variant"
    bl_label = "Edit or Tweak This Look"
    bl_description = "Mark only the active texture look as a draft, keep all shared authoring intact, and require appearance approval after editing"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            variant = edit_forge_texture_variant(context)
            self.report(
                {"INFO"},
                f"Editing {variant['displayName']}; texture approval is now required before export.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_replace_forge_texture_image(_VariantOperator):
    bl_idname = "daf.replace_forge_texture_image"
    bl_label = "Choose One Finished Base Color Image"
    bl_description = "Choose one finished UV Base Color image (not a four-view source folder), load it into only this look, and mark the look unsaved"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(name="Final Base Color", subtype='FILE_PATH')
    filter_glob: StringProperty(
        default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr",
        options={'HIDDEN'},
    )

    def invoke(self, context, _event):
        self.filepath = str(context.scene.daf_settings.variant_texture_image_path)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            context.scene.daf_settings.variant_texture_image_path = str(self.filepath)
            variant, image = replace_active_base_color_texture(context, self.filepath)
            self.report(
                {"INFO"},
                f"Loaded {image.name} into {variant['displayName']}; save the look before export.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_load_sbf_projection_folder(_VariantOperator):
    bl_idname = "daf.load_sbf_projection_folder"
    bl_label = "Load Four-View Projection Folder"
    bl_description = "Show Skin & Bones' full-body target on its verified neutral production rig, hide Forge's derived Damage pieces, and choose front/back/left/right source images"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            target = enter_skin_and_bones_projection(context)
            try:
                operation = getattr(bpy.ops.sbf, "load_perspective_folder")
                result = operation('INVOKE_DEFAULT')
            except (AttributeError, RuntimeError) as exc:
                raise RuntimeError(
                    "Skin & Bones cannot open its perspective-folder browser. Enable Skin & Bones 2.2.0+ first."
                ) from exc
            if not ({"RUNNING_MODAL", "FINISHED"} & set(result)):
                raise RuntimeError("Skin & Bones did not open the perspective-folder browser.")
            self.report(
                {"INFO"},
                f"Projection body {target.name} is visible; choose the folder containing front/back/left/right images.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_build_sbf_projection_preview(_VariantOperator):
    bl_idname = "daf.build_sbf_projection_preview"
    bl_label = "Build or Refresh Projection Preview"
    bl_description = "Reassert the verified Skin & Bones rig's neutral pose, then run One-Click Best Preview on its visible full-body source mesh"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            build_skin_and_bones_projection_preview(context)
            self.report({"INFO"}, "Skin & Bones projection preview is visible.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_bake_sbf_projection(_VariantOperator):
    bl_idname = "daf.bake_sbf_projection"
    bl_label = "Bake Final Texture in Skin & Bones"
    bl_description = "Bake the current Skin & Bones preview to its final UV Base Color without changing shared Forge authoring"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            bake_skin_and_bones_projection(context)
            self.report(
                {"INFO"},
                "Skin & Bones final texture baked; repair there if needed, then apply it to this Forge look.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_apply_sbf_final_texture(_VariantOperator):
    bl_idname = "daf.apply_sbf_final_texture"
    bl_label = "Use Latest Skin & Bones Final on This Look"
    bl_description = "Copy Skin & Bones' active final Base Color into only this Forge look, restore the intact finished body, and leave Actions, Damage, and sockets shared"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            variant, image = apply_skin_and_bones_final_texture(context)
            self.report(
                {"INFO"},
                f"Applied {image.name} to {variant['displayName']}; save or export this look next.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_save_export_forge_texture_variant(_VariantOperator):
    bl_idname = "daf.save_export_forge_texture_variant"
    bl_label = "Save and Export Current Look"
    bl_description = "Snapshot the active Forge-owned texture look, run full Complete Damage validation, and export its independent GLB"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            approve_forge_texture_variant(context)
            variant, paths = export_active_variant(context)
            self.report(
                {"INFO"},
                f"Saved and exported {variant['displayName']} as {Path(paths[0]).name if paths else variant['exportIdentity']}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_preview_character_variant(_VariantOperator):
    bl_idname = "daf.preview_character_variant"
    bl_label = "Preview Active Look"
    bl_description = "Apply the active variant material palette to the finished shared character and use Material Preview"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            variant = preview_active_variant(context)
            self.report({"INFO"}, f"Previewing {variant['displayName']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_export_active_character_variant(_VariantOperator):
    bl_idname = "daf.export_active_character_variant"
    bl_label = "Export This Variant"
    bl_description = "Export the selected appearance with the shared finished character and only its explicit overrides"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            variant, paths = export_active_variant(context)
            self.report(
                {"INFO"},
                f"Exported {variant['displayName']} as {Path(paths[0]).name if paths else variant['exportIdentity']}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_import_character_variant(_VariantOperator):
    bl_idname = "daf.import_character_variant"
    bl_label = "Add Skin & Bones Variant"
    bl_description = "Import one approved Skin & Bones appearance, prove exact family/body compatibility, and inherit shared Forge authoring"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            variant = import_appearance_variant(
                context,
                context.scene.daf_settings.variant_import_path,
            )
            self.report(
                {"INFO"},
                f"Added {variant['displayName']}; all Forge authoring is inherited by default.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_switch_character_variant(_VariantOperator):
    bl_idname = "daf.switch_character_variant"
    bl_label = "Switch Appearance Variant"
    bl_description = "Show this appearance while preserving resolved Actions, Damage, sockets, and rig state"
    bl_options = {"REGISTER", "UNDO"}

    variant_id: StringProperty()

    def execute(self, context):
        try:
            switch_variant(self.variant_id, context.scene)
            variant = preview_active_variant(context)
            self.report({"INFO"}, f"Active appearance: {variant['displayName']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_create_variant_action_override(_VariantOperator):
    bl_idname = "daf.create_variant_action_override"
    bl_label = "Create Variant Override"
    bl_description = "Create one variant-owned editable Action copy; every other Action remains inherited"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            action = animation_library.selected_action(context.scene.daf_settings)
            if action is None:
                raise RuntimeError("Select an inherited Action first.")
            override = create_action_override(context, action)
            self.report({"INFO"}, f"Created variant override draft {override.name}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_revert_variant_action_override(_VariantOperator):
    bl_idname = "daf.revert_variant_action_override"
    bl_label = "Revert Action to Shared"
    bl_description = "Discard this variant-owned Action and immediately resolve the shared family Action"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            action = animation_library.selected_action(context.scene.daf_settings)
            if action is None:
                raise RuntimeError("Select a variant Action override first.")
            shared = revert_action_override(context, action)
            self.report({"INFO"}, f"Reverted to shared Action {shared.name if shared else ''}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_edit_shared_family_action(_VariantOperator):
    bl_idname = "daf.edit_shared_family_action"
    bl_label = "Edit Shared Family Action"
    bl_description = "Intentionally edit the shared family Action; every inheriting appearance receives the saved change"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            action = animation_library.selected_action(context.scene.daf_settings)
            if action is None:
                raise RuntimeError("Select a shared or inherited Action first.")
            state = load_state(context.scene, required=True)
            shared, _shared_id = _shared_action(action, state)
            from . import find_armature

            result = animation_library.begin_edit(context, find_armature(context), shared)
            self.report({"WARNING"}, f"Editing shared family Action {result['source']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_create_variant_damage_override(_VariantOperator):
    bl_idname = "daf.create_variant_damage_override"
    bl_label = "Create Damage Override"
    bl_description = "Clone only the selected Damage Key or coherent Progressive Site unit for this appearance"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            if context.scene.daf_settings.variant_damage_override_unit == "PROGRESSIVE_SITE":
                record = create_progressive_site_override(context)
                label = record["overrideSiteGuid"]
            else:
                record = create_damage_key_override(context)
                label = record["overrideName"]
            self.report({"INFO"}, f"Created variant Damage override {label}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_revert_variant_damage_override(_VariantOperator):
    bl_idname = "daf.revert_variant_damage_override"
    bl_label = "Revert Damage to Shared"
    bl_description = "Discard variant-only Damage edits, remove owned data, and restore live shared resolution"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            if context.scene.daf_settings.variant_damage_override_unit == "PROGRESSIVE_SITE":
                revert_progressive_site_override(context)
            else:
                revert_damage_key_override(context)
            self.report({"INFO"}, "Variant Damage override discarded; shared content restored.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_toggle_shared_family_damage_edit(_VariantOperator):
    bl_idname = "daf.toggle_shared_family_damage_edit"
    bl_label = "Edit Shared Family Damage"
    bl_description = "Deliberately unlock family-wide Damage editing for every inheriting appearance"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        settings = context.scene.daf_settings
        if settings.variant_shared_damage_edit_enabled:
            return self.execute(context)
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            load_state(context.scene, required=True)
            settings = context.scene.daf_settings
            settings.variant_shared_damage_edit_enabled = not bool(
                settings.variant_shared_damage_edit_enabled
            )
            state = "UNLOCKED" if settings.variant_shared_damage_edit_enabled else "LOCKED"
            settings.variant_family_status = f"SHARED FAMILY DAMAGE EDITING {state}"
            self.report(
                {"WARNING" if settings.variant_shared_damage_edit_enabled else "INFO"},
                settings.variant_family_status,
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_export_ready_character_variants(_VariantOperator):
    bl_idname = "daf.export_ready_character_variants"
    bl_label = "Export All Ready Variants"
    bl_description = "Export each Forge-ready appearance as its own resolved Complete Damage GLB and sidecars"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            result = batch_export_ready_variants(context)
            if not result["exported"]:
                detail = result["skipped"][0]["reason"] if result["skipped"] else "No variants exist."
                raise RuntimeError("No ready variants exported. " + detail)
            self.report(
                {"WARNING"} if result["skipped"] else {"INFO"},
                f"Exported {len(result['exported'])} variant(s); skipped {len(result['skipped'])}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


CLASSES = (
    DAF_OT_adopt_character_variant_family,
    DAF_OT_start_finished_texture_family,
    DAF_OT_create_forge_texture_variant,
    DAF_OT_approve_forge_texture_variant,
    DAF_OT_edit_forge_texture_variant,
    DAF_OT_replace_forge_texture_image,
    DAF_OT_load_sbf_projection_folder,
    DAF_OT_build_sbf_projection_preview,
    DAF_OT_bake_sbf_projection,
    DAF_OT_apply_sbf_final_texture,
    DAF_OT_save_export_forge_texture_variant,
    DAF_OT_preview_character_variant,
    DAF_OT_export_active_character_variant,
    DAF_OT_import_character_variant,
    DAF_OT_switch_character_variant,
    DAF_OT_create_variant_action_override,
    DAF_OT_revert_variant_action_override,
    DAF_OT_edit_shared_family_action,
    DAF_OT_create_variant_damage_override,
    DAF_OT_revert_variant_damage_override,
    DAF_OT_toggle_shared_family_damage_edit,
    DAF_OT_export_ready_character_variants,
)


__all__ = (
    "CLASSES",
    "FAMILY_STATE_PROPERTY",
    "ACTION_SCOPE_PROPERTY",
    "action_status",
    "adopt_finished_damage_as_texture_family",
    "adopt_selected_as_family_base",
    "appearance_status",
    "apply_skin_and_bones_final_texture",
    "batch_export_ready_variants",
    "bake_skin_and_bones_projection",
    "build_skin_and_bones_projection_preview",
    "damage_object_is_effective",
    "damage_status",
    "effective_actions",
    "effective_damage_key_names",
    "effective_progressive_collection",
    "edit_forge_texture_variant",
    "enter_skin_and_bones_projection",
    "export_active_variant",
    "export_context",
    "export_provenance",
    "handoff_from_armature",
    "import_appearance_variant",
    "load_state",
    "mark_action_for_family",
    "merge_progressive_collection",
    "recover_state",
    "replace_active_base_color_texture",
    "require_regular_action_edit_allowed",
    "store_state",
    "switch_variant",
    "texture_appearance_errors",
    "texture_appearance_fingerprint",
)
