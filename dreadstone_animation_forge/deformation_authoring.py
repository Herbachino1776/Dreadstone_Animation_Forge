"""Dreadstone Animation Forge v3.10 trauma-field authoring.

The workbench edits only registered attached/detached regions on the generated
protected Damage Asset. Paired morph targets remain exact-index synchronized in
world space even when object scales differ. Imported source data is never edited.
"""

import bmesh
import bpy
import hashlib
import json
import math
import re
from mathutils import Vector
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import trauma_field

DEFORMATION_SCHEMA = "dreadstone.damage_deformation.v1"
DEFORMATION_VERSION = (3, 10, 0)
DEFORMATION_BUILD_ID = "2026-07-17.trauma-field.1"
ATTACHED_HEAD_NAME = "DSB_ATTACHED_HEAD"
DETACHED_HEAD_NAME = "DSB_SEGMENT_HEAD"
PREVIEW_KEY_NAME = "__DSB_DEFORMATION_SEED_PREVIEW"
METADATA_PROPERTY = "dsb_deformation_manifest_json"
REGISTRY_PROPERTY = "dsb_deformation_region_registry_json"
PAIR_TOLERANCE = 1e-6
SYNC_TOLERANCE = 1e-6
_GEODESIC_CACHE = {}
_GEODESIC_CACHE_CONTEXT = {}

STANDARD_HEAD_KEYS = {
    "Head_Dent_Left": {
        "family": "localized_dent", "side": "left", "mirrorPartner": "Head_Dent_Right",
        "seedRadius": 0.075, "seedDepth": 0.025, "seedFalloff": 1.65,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.045,
    },
    "Head_Dent_Right": {
        "family": "localized_dent", "side": "right", "mirrorPartner": "Head_Dent_Left",
        "seedRadius": 0.075, "seedDepth": 0.025, "seedFalloff": 1.65,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.045,
    },
    "Head_Cave_Front": {
        "family": "broad_cave", "side": "center", "mirrorPartner": "",
        "seedRadius": 0.105, "seedDepth": 0.038, "seedFalloff": 1.35,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.055,
    },
    "Jaw_Displaced": {
        "family": "directional_displacement", "side": "configurable", "mirrorPartner": "",
        "seedRadius": 0.080, "seedDepth": 0.024, "seedFalloff": 1.55,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.050,
    },
}


def _version_string():
    return ".".join(str(value) for value in DEFORMATION_VERSION)


def _object(name):
    return bpy.data.objects.get(name)


def _topology_fingerprint(obj):
    digest = hashlib.sha256()
    digest.update(f"v:{len(obj.data.vertices)}|p:{len(obj.data.polygons)}|".encode("utf8"))
    for polygon in obj.data.polygons:
        digest.update((",".join(str(int(index)) for index in polygon.vertices) + ";").encode("ascii"))
    return digest.hexdigest()


def validate_topology_pair(attached=None, detached=None):
    attached, detached = (attached, detached) if attached and detached else _resolve_pair()
    errors = []
    if attached is None:
        errors.append("The registered attached object is missing.")
    if detached is None:
        errors.append("The registered detached object is missing.")
    if errors:
        return {
            "status": "FAIL", "errors": errors,
            "attachedVertexCount": 0, "detachedVertexCount": 0,
            "attachedPolygonCount": 0, "detachedPolygonCount": 0,
            "topologyFingerprint": "",
        }
    if attached.name == detached.name:
        errors.append("Attached and detached object names must differ.")
    if attached.type != 'MESH':
        errors.append(f"Registered attached object {attached.name} is not a mesh.")
    if detached.type != 'MESH':
        errors.append(f"Registered detached object {detached.name} is not a mesh.")
    if errors:
        return {
            "status": "FAIL", "errors": errors,
            "attachedVertexCount": len(attached.data.vertices) if attached.type == 'MESH' else 0,
            "detachedVertexCount": len(detached.data.vertices) if detached.type == 'MESH' else 0,
            "attachedPolygonCount": len(attached.data.polygons) if attached.type == 'MESH' else 0,
            "detachedPolygonCount": len(detached.data.polygons) if detached.type == 'MESH' else 0,
            "topologyFingerprint": "",
        }
    if len(attached.data.vertices) != len(detached.data.vertices):
        errors.append(f"{attached.name} and {detached.name} vertex counts differ; exact-index transfer is unsafe.")
    if len(attached.data.polygons) != len(detached.data.polygons):
        errors.append(f"{attached.name} and {detached.name} polygon counts differ; exact-index transfer is unsafe.")
    if len(attached.data.vertices) == 0 or len(detached.data.vertices) == 0:
        errors.append("Registered deformation meshes must contain vertices.")
    if len(attached.data.polygons) == 0 or len(detached.data.polygons) == 0:
        errors.append("Registered deformation meshes must contain polygons.")
    attached_fingerprint = _topology_fingerprint(attached)
    detached_fingerprint = _topology_fingerprint(detached)
    if attached_fingerprint != detached_fingerprint:
        errors.append("Attached and detached topology fingerprints differ; vertex-index transfer is unsafe.")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "attachedVertexCount": len(attached.data.vertices),
        "detachedVertexCount": len(detached.data.vertices),
        "attachedPolygonCount": len(attached.data.polygons),
        "detachedPolygonCount": len(detached.data.polygons),
        "topologyFingerprint": attached_fingerprint,
    }


def _empty_registry():
    return {
        "schema": DEFORMATION_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": DEFORMATION_BUILD_ID,
        "activeRegionId": "",
        "regions": [],
    }


def _registry_raw():
    scene = getattr(bpy.context, "scene", None)
    if scene is not None:
        raw = scene.get(REGISTRY_PROPERTY, "")
        if raw:
            return raw
    for obj in bpy.data.objects:
        raw = obj.get(REGISTRY_PROPERTY, "")
        if raw:
            return raw
    return ""


def _store_registry(payload):
    payload["schema"] = DEFORMATION_SCHEMA
    payload["authoringVersion"] = _version_string()
    payload["authoringBuildId"] = DEFORMATION_BUILD_ID
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    scene = getattr(bpy.context, "scene", None)
    if scene is not None:
        scene[REGISTRY_PROPERTY] = encoded
    for region in payload.get("regions", []):
        for name in (region.get("attachedObject"), region.get("detachedObject")):
            obj = _object(name) if name else None
            if obj is not None:
                obj[REGISTRY_PROPERTY] = encoded
                obj["dsb_deformation_region"] = region.get("regionId", "")


def _region_record(registry, region_id):
    return next((region for region in registry.get("regions", []) if region.get("regionId") == region_id), None)


def _record_from_pair(region_id, attached, detached, related_seam_id=""):
    contract = validate_topology_pair(attached, detached)
    return {
        "regionId": region_id,
        "attachedObject": attached.name,
        "detachedObject": detached.name,
        "topologyFingerprint": contract.get("topologyFingerprint", ""),
        "attachedVertexCount": contract.get("attachedVertexCount", 0),
        "detachedVertexCount": contract.get("detachedVertexCount", 0),
        "polygonCount": contract.get("attachedPolygonCount", 0),
        "relatedSeamId": related_seam_id,
        "managedKeys": [],
        "validationStatus": contract["status"],
    }


def _load_registry(migrate_legacy=True):
    payload = _empty_registry()
    raw = _registry_raw()
    if raw:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict) and isinstance(decoded.get("regions", []), list):
                payload.update(decoded)
        except Exception:
            pass
    payload.setdefault("regions", [])
    if not payload["regions"] and migrate_legacy:
        attached = _object(ATTACHED_HEAD_NAME)
        detached = _object(DETACHED_HEAD_NAME)
        if attached is not None and detached is not None and attached.type == 'MESH' and detached.type == 'MESH':
            record = _record_from_pair("head", attached, detached, "head_neck")
            if record["validationStatus"] == "PASS":
                existing = []
                if attached.data.shape_keys and detached.data.shape_keys:
                    for name in STANDARD_HEAD_KEYS:
                        if _key(attached, name) is not None and _key(detached, name) is not None:
                            existing.append(name)
                record["managedKeys"] = existing
                payload["regions"] = [record]
                payload["activeRegionId"] = "head"
                _store_registry(payload)
    if payload.get("activeRegionId") not in {region.get("regionId") for region in payload["regions"]}:
        payload["activeRegionId"] = payload["regions"][0].get("regionId", "") if payload["regions"] else ""
    return payload


def _active_region_id(context=None):
    registry = _load_registry()
    scene = getattr(context, "scene", None) if context is not None else getattr(bpy.context, "scene", None)
    settings = getattr(scene, "daf_settings", None)
    selected = getattr(settings, "deformation_region", "") if settings else ""
    if selected == "HEAD":
        selected = "head"
    if _region_record(registry, selected) is not None:
        return selected
    return registry.get("activeRegionId", "")


def _set_active_region(region_id, context=None):
    registry = _load_registry()
    if _region_record(registry, region_id) is None:
        raise RuntimeError(f"Deformation region {region_id!r} is not registered.")
    registry["activeRegionId"] = region_id
    _store_registry(registry)
    scene = getattr(context, "scene", None) if context is not None else getattr(bpy.context, "scene", None)
    settings = getattr(scene, "daf_settings", None)
    if settings is not None and settings.deformation_region != region_id:
        settings.deformation_region = region_id
    _invalidate_geodesic_cache()


def _resolve_region_pair(region):
    attached = _object(region.get("attachedObject", ""))
    detached = _object(region.get("detachedObject", ""))
    if attached is None:
        raise RuntimeError(f"Registered attached object {region.get('attachedObject', '')} is missing.")
    if detached is None:
        raise RuntimeError(f"Registered detached object {region.get('detachedObject', '')} is missing.")
    if attached.type != 'MESH' or detached.type != 'MESH':
        raise RuntimeError("Both registered deformation-region objects must be meshes.")
    return attached, detached


def _resolve_active_region(context=None, region_id=None):
    registry = _load_registry()
    resolved_id = region_id or _active_region_id(context)
    region = _region_record(registry, resolved_id)
    if region is None:
        raise RuntimeError("Register an attached/detached deformation region first.")
    attached, detached = _resolve_region_pair(region)
    return registry, region, attached, detached


def _resolve_pair(context=None, region_id=None):
    _registry, _region, attached, detached = _resolve_active_region(context, region_id)
    return attached, detached


def region_enum_items():
    registry = _load_registry()
    items = []
    for index, region in enumerate(registry.get("regions", [])):
        region_id = region.get("regionId", "")
        label = region_id.replace("_", " ").title() or "Unnamed Region"
        description = f"{region.get('attachedObject', '')} ↔ {region.get('detachedObject', '')}"
        items.append((region_id, label, description, index))
    return items or [("NONE", "No Regions", "Register an attached/detached mesh pair", 0)]


def _invalidate_geodesic_cache():
    _GEODESIC_CACHE.clear()
    _GEODESIC_CACHE_CONTEXT.clear()


def _metadata(obj):
    raw = obj.get(METADATA_PROPERTY, "") or obj.data.get(METADATA_PROPERTY, "")
    if raw:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                payload["schema"] = DEFORMATION_SCHEMA
                payload["authoringVersion"] = _version_string()
                payload["authoringBuildId"] = DEFORMATION_BUILD_ID
                for entry in payload.get("keys", {}).values():
                    entry.setdefault("stamps", [])
                    if not entry["stamps"]:
                        entry.setdefault("recipeStatus", "LEGACY_MANUAL")
                        entry.setdefault("legacy", True)
                return payload
        except Exception:
            pass
    registry = _load_registry()
    region = next((record for record in registry.get("regions", []) if obj.name in {
        record.get("attachedObject"), record.get("detachedObject")
    }), None)
    region_id = region.get("regionId", "head") if region else "head"
    attached_name = region.get("attachedObject", ATTACHED_HEAD_NAME) if region else ATTACHED_HEAD_NAME
    detached_name = region.get("detachedObject", DETACHED_HEAD_NAME) if region else DETACHED_HEAD_NAME
    payload = {
        "schema": DEFORMATION_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": DEFORMATION_BUILD_ID,
        "region": region_id,
        "regionId": region_id,
        "attachedObject": attached_name,
        "detachedObject": detached_name,
        "keys": {},
    }
    # Clean GLB reimports retain morph names even when a host strips extras.
    # Recover only the exact standard Forge names; never adopt arbitrary keys.
    other_name = detached_name if obj.name == attached_name else attached_name
    other = _object(other_name)
    if region_id == "head":
        for name, template in STANDARD_HEAD_KEYS.items():
            if _key(obj, name) is not None and other is not None and _key(other, name) is not None:
                payload["keys"][name] = {
                    "name": name,
                    "region": "head",
                    "regionId": "head",
                    "status": "REIMPORTED",
                    "recipeStatus": "LEGACY_MANUAL",
                    "legacy": True,
                    "stamps": [],
                    **template,
                }
    return payload


def _store_metadata(attached, detached, payload):
    registry = _load_registry()
    region = next((record for record in registry.get("regions", []) if record.get("attachedObject") == attached.name
                   and record.get("detachedObject") == detached.name), None)
    region_id = region.get("regionId", payload.get("regionId", payload.get("region", ""))) if region else payload.get("regionId", payload.get("region", ""))
    payload["schema"] = DEFORMATION_SCHEMA
    payload["authoringVersion"] = _version_string()
    payload["authoringBuildId"] = DEFORMATION_BUILD_ID
    payload["region"] = region_id
    payload["regionId"] = region_id
    payload["attachedObject"] = attached.name
    payload["detachedObject"] = detached.name
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    attached.data[METADATA_PROPERTY] = encoded
    detached.data[METADATA_PROPERTY] = encoded
    attached[METADATA_PROPERTY] = encoded
    detached[METADATA_PROPERTY] = encoded
    attached["dsb_deformation_region"] = region_id
    detached["dsb_deformation_region"] = region_id
    if region is not None:
        region["managedKeys"] = sorted(payload.get("keys", {}).keys())
        region["topologyFingerprint"] = _topology_fingerprint(attached)
        region["attachedVertexCount"] = len(attached.data.vertices)
        region["detachedVertexCount"] = len(detached.data.vertices)
        region["polygonCount"] = len(attached.data.polygons)
        _store_registry(registry)


def _ensure_basis(obj):
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    return obj.data.shape_keys.reference_key


def _key(obj, name):
    keys = obj.data.shape_keys
    return keys.key_blocks.get(name) if keys else None


def _managed_names(attached=None):
    attached = attached or _resolve_pair()[0]
    metadata = _metadata(attached)
    names = []
    for name in metadata.get("keys", {}):
        if name == PREVIEW_KEY_NAME:
            continue
        if _key(attached, name):
            names.append(name)
    return names


def _escape_data_path(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _link_detached_value(attached, detached, name):
    detached_key = _key(detached, name)
    if detached_key is None:
        return
    try:
        detached_key.driver_remove("value")
    except (TypeError, RuntimeError):
        pass
    fcurve = detached_key.driver_add("value")
    driver = fcurve.driver
    driver.type = 'AVERAGE'
    variable = driver.variables.new()
    variable.name = "attached_weight"
    variable.type = 'SINGLE_PROP'
    target = variable.targets[0]
    target.id_type = 'KEY'
    target.id = attached.data.shape_keys
    target.data_path = f'key_blocks["{_escape_data_path(name)}"].value'


def _ensure_key_pair(name, metadata_entry=None, preview=False):
    if not name or name == "Basis":
        raise RuntimeError("Choose a valid deformation key name.")
    attached, detached = _resolve_pair()
    contract = validate_topology_pair(attached, detached)
    if contract["status"] != "PASS":
        raise RuntimeError(" ".join(contract["errors"]))
    _ensure_basis(attached)
    _ensure_basis(detached)
    payload = _metadata(attached)
    attached_key = _key(attached, name)
    detached_key = _key(detached, name)
    if not preview and name not in payload.get("keys", {}) and (attached_key is not None or detached_key is not None):
        raise RuntimeError(f"A non-Forge shape key named {name} already exists; choose another name.")
    created_attached = attached_key is None
    created_detached = detached_key is None
    attached_key = attached_key or attached.shape_key_add(name=name, from_mix=False)
    detached_key = detached_key or detached.shape_key_add(name=name, from_mix=False)
    attached_key.slider_min = 0.0
    detached_key.slider_min = 0.0
    maximum = float((metadata_entry or {}).get("maximumInfluence", 1.0))
    attached_key.slider_max = maximum
    detached_key.slider_max = maximum
    if created_attached or created_detached:
        attached_key.value = 0.0
        detached_key.value = 0.0
        _link_detached_value(attached, detached, name)
    if not preview:
        registry, region, _attached, _detached = _resolve_active_region()
        region_id = region.get("regionId", "")
        entry = {
            "name": name,
            "region": region_id,
            "regionId": region_id,
            "family": (metadata_entry or {}).get("family", "manual"),
            "side": (metadata_entry or {}).get("side", "configurable"),
            "mirrorPartner": (metadata_entry or {}).get("mirrorPartner", ""),
            "maximumInfluence": maximum,
            "maximumDisplacement": float((metadata_entry or {}).get("maximumDisplacement", 0.045)),
            "status": (metadata_entry or {}).get("status", "EMPTY"),
            "seedRadius": float((metadata_entry or {}).get("seedRadius", 0.055)),
            "seedDepth": float((metadata_entry or {}).get("seedDepth", 0.016)),
            "seedFalloff": float((metadata_entry or {}).get("seedFalloff", 2.2)),
            "stamps": list((metadata_entry or {}).get("stamps", [])),
            "recipeStatus": (metadata_entry or {}).get("recipeStatus", "LEGACY_MANUAL"),
            "legacy": bool((metadata_entry or {}).get("legacy", False)),
        }
        payload.setdefault("keys", {})[name] = {**payload.get("keys", {}).get(name, {}), **entry}
        _store_metadata(attached, detached, payload)
    return attached, detached, attached_key, detached_key


def _remove_key(obj, name):
    key_block = _key(obj, name)
    if key_block is not None and key_block != obj.data.shape_keys.reference_key:
        try:
            key_block.driver_remove("value")
        except (TypeError, RuntimeError):
            pass
        obj.shape_key_remove(key_block)


def clear_seed_preview(all_regions=False):
    registry = _load_registry()
    regions = registry.get("regions", []) if all_regions else [_region_record(registry, _active_region_id())]
    for region in regions:
        if not region:
            continue
        try:
            attached, detached = _resolve_region_pair(region)
        except RuntimeError:
            continue
        _remove_key(attached, PREVIEW_KEY_NAME)
        _remove_key(detached, PREVIEW_KEY_NAME)


def _region_seam_points(region=None):
    try:
        from . import damage_authoring
        if region is None:
            _registry, region, _attached, _detached = _resolve_active_region()
        seam_id = region.get("relatedSeamId", "")
        if not seam_id:
            return []
        state = damage_authoring._load_state()
        points = state.get("seams", {}).get(seam_id, {}).get("contour_points_object", [])
        return [Vector(point) for point in points]
    except Exception:
        return []


def _direction(settings):
    mode = settings.deformation_seed_direction_mode
    if mode == 'INWARD_SURFACE_NORMAL':
        vector = -Vector(settings.deformation_seed_surface_normal)
    elif mode == 'OUTWARD_SURFACE_NORMAL':
        vector = Vector(settings.deformation_seed_surface_normal)
    else:
        vectors = {
            'LOCAL_X': Vector((1, 0, 0)), 'LOCAL_NEG_X': Vector((-1, 0, 0)),
            'LOCAL_Y': Vector((0, 1, 0)), 'LOCAL_NEG_Y': Vector((0, -1, 0)),
            'LOCAL_Z': Vector((0, 0, 1)), 'LOCAL_NEG_Z': Vector((0, 0, -1)),
            'CUSTOM_VECTOR': Vector(settings.deformation_seed_custom_direction),
        }
        vector = vectors.get(mode, Vector((0, 0, -1)))
    if vector.length_squared <= 1e-12:
        raise RuntimeError("The deformation direction vector has zero length.")
    return vector.normalized()


def _smoothstep(value):
    t = max(0.0, min(1.0, float(value)))
    return t * t * (3.0 - 2.0 * t)


def _linear_world_matrix(obj):
    return obj.matrix_world.to_3x3()


def _local_delta_to_world(obj, delta):
    return _linear_world_matrix(obj) @ Vector(delta)


def _world_delta_to_local(obj, delta):
    matrix = _linear_world_matrix(obj)
    try:
        return matrix.inverted() @ Vector(delta)
    except ValueError:
        raise RuntimeError(f"{obj.name} has a singular object transform; apply or repair scale before deformation authoring.")


def _normal_local_to_world(obj, normal):
    matrix = _linear_world_matrix(obj)
    try:
        result = matrix.inverted().transposed() @ Vector(normal)
    except ValueError:
        raise RuntimeError(f"{obj.name} has a singular object transform; cannot transform the captured surface normal.")
    if result.length_squared <= 1e-12:
        raise RuntimeError("The transformed deformation direction has zero length.")
    return result.normalized()


def _seed_direction_world(settings, obj):
    mode = settings.deformation_seed_direction_mode
    local = _direction(settings)
    if mode in {'INWARD_SURFACE_NORMAL', 'OUTWARD_SURFACE_NORMAL'}:
        return _normal_local_to_world(obj, local)
    result = _linear_world_matrix(obj) @ local
    if result.length_squared <= 1e-12:
        raise RuntimeError("The transformed deformation axis has zero length.")
    return result.normalized()


def _set_authoring_view(attached, detached, mode='ATTACHED'):
    # hide_set is viewport-only and does not alter export visibility. It prevents
    # the intact detached segment from sitting directly on top of the skinned head
    # and masking the seed preview.
    if mode == 'ATTACHED':
        attached.hide_set(False)
        detached.hide_set(True)
    elif mode == 'DETACHED':
        attached.hide_set(True)
        detached.hide_set(False)
    else:
        attached.hide_set(False)
        detached.hide_set(False)


def _zero_managed_weights(attached, include_preview=False):
    for name in _managed_names(attached):
        key = _key(attached, name)
        if key:
            key.value = 0.0
    if include_preview:
        preview = _key(attached, PREVIEW_KEY_NAME)
        if preview:
            preview.value = 0.0


def _seed_coordinates(settings, attached):
    if not settings.deformation_seed_center_valid:
        raise RuntimeError("Capture a surface center before previewing the seed.")
    center_local = Vector(settings.deformation_seed_center)
    center_world = attached.matrix_world @ center_local
    direction_world = _seed_direction_world(settings, attached)
    radius = max(1e-6, float(settings.deformation_seed_radius))
    depth = max(0.0, float(settings.deformation_seed_depth))
    falloff = max(0.01, float(settings.deformation_seed_falloff))
    max_displacement = max(1e-6, float(settings.deformation_max_vertex_displacement))
    seam_protection = max(0.0, float(settings.deformation_seed_seam_protection))
    _registry, region, _active_attached, _detached = _resolve_active_region()
    seam_points_world = [attached.matrix_world @ point for point in _region_seam_points(region)]
    payload = _metadata(attached)
    entry = payload.get("keys", {}).get(settings.deformation_active_key, {})
    family = entry.get("family", "manual")
    outward_world = -direction_world
    coordinates = []
    inverse_world = attached.matrix_world.inverted()
    basis_block = attached.data.shape_keys.reference_key if attached.data.shape_keys else None
    affected = 0
    maximum_world_displacement = 0.0
    for index, vertex in enumerate(attached.data.vertices):
        basis_local = (basis_block.data[index].co if basis_block else vertex.co).copy()
        basis_world = attached.matrix_world @ basis_local
        offset_world = basis_world - center_world
        # Surface dents are selected by radial world-space distance. The slider
        # values therefore remain real meters regardless of object scale.
        distance = offset_world.length
        normalized = max(0.0, 1.0 - distance / radius)
        core = normalized ** falloff
        seam_factor = 1.0
        if seam_points_world and seam_protection > 0.0:
            seam_distance = min((basis_world - point).length for point in seam_points_world)
            seam_factor = _smoothstep(seam_distance / seam_protection)
        displacement_world = Vector((0.0, 0.0, 0.0))
        if core > 0.0:
            if family == "localized_dent":
                # A shallow raised lip makes the preset read as a dent instead of
                # a rubbery uniform translation. The lip is deliberately subtle.
                radial_fraction = min(1.0, distance / radius)
                rim = math.exp(-((radial_fraction - 0.78) / 0.14) ** 2) * depth * 0.13
                inward = depth * core
                displacement_world = direction_world * inward + outward_world * rim
            elif family == "broad_cave":
                inward = depth * (normalized ** max(0.55, falloff * 0.72))
                displacement_world = direction_world * inward
            elif family == "directional_displacement":
                plateau = _smoothstep(min(1.0, normalized * 1.35))
                displacement_world = direction_world * (depth * plateau)
            else:
                displacement_world = direction_world * (depth * core)
            displacement_world *= seam_factor
            if displacement_world.length > max_displacement:
                displacement_world.normalize()
                displacement_world *= max_displacement
            if displacement_world.length > 1e-8:
                affected += 1
                maximum_world_displacement = max(maximum_world_displacement, displacement_world.length)
        result_world = basis_world + displacement_world
        coordinates.append(inverse_world @ result_world)
    if affected == 0:
        raise RuntimeError(
            "The seed radius reached no vertices in world space. Confirm the active region, show its attached mesh, recapture, and retry."
        )
    settings.deformation_status = f"LIVE SEED — {affected} vertices / {maximum_world_displacement:.3f} m"
    return coordinates


def _set_key_coordinates(key_block, coordinates):
    if len(key_block.data) != len(coordinates):
        raise RuntimeError("Shape-key coordinate count does not match the mesh.")
    for point, coordinate in zip(key_block.data, coordinates):
        point.co = coordinate


def sync_key_to_detached(name, region_id=None):
    attached, detached = _resolve_pair(region_id=region_id)
    contract = validate_topology_pair(attached, detached)
    if contract["status"] != "PASS":
        raise RuntimeError(" ".join(contract["errors"]))
    attached_key = _key(attached, name)
    detached_key = _key(detached, name)
    if attached_key is None or detached_key is None:
        raise RuntimeError(f"The paired key {name} is incomplete.")
    attached_basis = attached.data.shape_keys.reference_key
    detached_basis = detached.data.shape_keys.reference_key
    for index in range(len(attached_key.data)):
        delta_attached_local = attached_key.data[index].co - attached_basis.data[index].co
        delta_world = _local_delta_to_world(attached, delta_attached_local)
        delta_detached_local = _world_delta_to_local(detached, delta_world)
        detached_key.data[index].co = detached_basis.data[index].co + delta_detached_local
    _link_detached_value(attached, detached, name)


def preview_seed(context, quiet=False):
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        raise RuntimeError("Switch to Object Mode before previewing a deformation seed.")
    settings = context.scene.daf_settings
    attached, detached, attached_preview, _detached_preview = _ensure_key_pair(PREVIEW_KEY_NAME, preview=True)
    _zero_managed_weights(attached)
    _set_authoring_view(attached, detached, 'ATTACHED')
    coordinates = _seed_coordinates(settings, attached)
    _set_key_coordinates(attached_preview, coordinates)
    sync_key_to_detached(PREVIEW_KEY_NAME)
    attached_preview.value = 1.0
    attached_preview.slider_max = 1.0
    settings.deformation_status = "LIVE SEED PREVIEW"
    if not quiet:
        return {"vertexCount": len(coordinates), "key": settings.deformation_active_key}
    return None


def refresh_live_seed_preview(context):
    # Settings callbacks may change traversal radius or feathering. Clearing is
    # cheap compared with risking reuse of a graph result for superseded inputs.
    _invalidate_geodesic_cache()
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if not settings or not settings.deformation_auto_preview:
        return
    try:
        if settings.deformation_seed_center_valid and settings.deformation_active_key:
            attached, _detached = _resolve_pair(context)
            entry = _metadata(attached).get("keys", {}).get(settings.deformation_active_key, {})
            if entry.get("stamps") and settings.deformation_active_stamp_id:
                preview_active_stamp(context, quiet=True)
            else:
                preview_seed(context, quiet=True)
    except Exception as exc:
        settings.deformation_status = "SEED PREVIEW ERROR: " + str(exc)[:120]


def update_active_key_metadata(context):
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if not settings or not settings.deformation_active_key:
        return
    try:
        attached, detached = _resolve_pair()
        payload = _metadata(attached)
        entry = payload.get("keys", {}).get(settings.deformation_active_key)
        if not entry:
            return
        entry["maximumInfluence"] = float(settings.deformation_maximum_influence)
        entry["maximumDisplacement"] = float(settings.deformation_max_vertex_displacement)
        for obj in (attached, detached):
            block = _key(obj, settings.deformation_active_key)
            if block:
                block.slider_max = float(settings.deformation_maximum_influence)
        _store_metadata(attached, detached, payload)
    except Exception:
        pass


def _select_key(settings, name):
    attached, _detached = _resolve_pair()
    entry = _metadata(attached).get("keys", {}).get(name, {})
    settings.deformation_active_key = name
    settings.deformation_key_name = name
    settings.deformation_seed_radius = float(entry.get("seedRadius", settings.deformation_seed_radius))
    settings.deformation_seed_depth = float(entry.get("seedDepth", settings.deformation_seed_depth))
    settings.deformation_seed_falloff = float(entry.get("seedFalloff", settings.deformation_seed_falloff))
    settings.deformation_maximum_influence = float(entry.get("maximumInfluence", 1.0))
    settings.deformation_max_vertex_displacement = float(entry.get("maximumDisplacement", 0.045))
    stamps = entry.get("stamps", [])
    settings.deformation_active_stamp_id = ""
    if stamps:
        _load_stamp_into_settings(settings, sorted(stamps, key=lambda stamp: int(stamp.get("orderIndex", 0)))[0])


def _set_active_object(context, obj):
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _max_displacement(obj, name):
    key = _key(obj, name)
    if not key:
        return 0.0
    basis = obj.data.shape_keys.reference_key
    return max((_local_delta_to_world(obj, key.data[i].co - basis.data[i].co).length for i in range(len(key.data))), default=0.0)


def _capture_payload(settings):
    raw = getattr(settings, "deformation_capture_json", "")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _captured_face_component_count(attached, face_indices):
    selected = {int(index) for index in face_indices}
    if not selected:
        return 0
    edge_faces = {}
    for index in selected:
        for edge_key in attached.data.polygons[index].edge_keys:
            edge_faces.setdefault(tuple(sorted(edge_key)), []).append(index)
    neighbors = {index: set() for index in selected}
    for linked_faces in edge_faces.values():
        for left in linked_faces:
            neighbors[left].update(right for right in linked_faces if right != left)
    components = 0
    remaining = set(selected)
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            current = stack.pop()
            linked = neighbors[current] & remaining
            remaining.difference_update(linked)
            stack.extend(linked)
    return components


def _capture_errors(capture, region, attached):
    errors = []
    if not isinstance(capture, dict) or not capture:
        return ["Capture a surface face, connected face patch, selected vertices, or cursor before authoring a stamp."]
    placement = capture.get("placementMode")
    if placement not in trauma_field.PLACEMENT_MODES:
        errors.append("Captured placement mode is invalid.")
    if capture.get("regionId") != region.get("regionId"):
        errors.append("Captured surface belongs to a different deformation region; recapture it.")
    if capture.get("attachedObject") != attached.name:
        errors.append("Captured surface belongs to a different attached object; recapture it.")
    current_fingerprint = _topology_fingerprint(attached)
    if capture.get("topologyFingerprint") != current_fingerprint:
        errors.append("Captured surface topology is stale; recapture it on the current mesh.")
    vertex_indices = capture.get("vertexIndices", [])
    face_indices = capture.get("faceIndices", [])
    if placement in {"SINGLE_FACE", "SELECTED_FACE_PATCH"} and not face_indices:
        errors.append("Captured face patch is empty.")
    if placement == "SELECTED_VERTICES" and not vertex_indices:
        errors.append("Captured vertex selection is empty.")
    if not vertex_indices:
        errors.append("Captured surface has no geodesic seed vertices.")
    if any(not isinstance(index, int) or index < 0 or index >= len(attached.data.vertices) for index in vertex_indices):
        errors.append("Captured vertex indices are invalid for the active attached mesh; recapture them.")
    if any(not isinstance(index, int) or index < 0 or index >= len(attached.data.polygons) for index in face_indices):
        errors.append("Captured face indices are invalid for the active attached mesh; recapture them.")
    elif placement in {"SINGLE_FACE", "SELECTED_FACE_PATCH"} and _captured_face_component_count(attached, face_indices) != 1:
        errors.append("Captured face patch contains disconnected islands; select one connected patch and recapture it.")
    selection_kind = capture.get("selectionKind", "VERTEX")
    hash_indices = face_indices if selection_kind == "FACE" else vertex_indices
    if hash_indices:
        expected_hash = trauma_field.selection_hash(hash_indices, current_fingerprint, selection_kind)
        if capture.get("selectionHash") != expected_hash:
            errors.append("Captured selection hash is stale or corrupt; recapture the surface.")
    return errors


def _store_capture(context, capture):
    settings = context.scene.daf_settings
    settings.deformation_capture_json = json.dumps(capture, sort_keys=True, separators=(",", ":"))
    settings.deformation_seed_center = tuple(capture.get("centerLocal", (0.0, 0.0, 0.0)))
    settings.deformation_seed_surface_normal = tuple(capture.get("normalLocal", (0.0, 0.0, 1.0)))
    settings.deformation_seed_center_valid = True
    _invalidate_geodesic_cache()
    try:
        attached, detached = _resolve_pair(context)
        payload = _metadata(attached)
        entry = payload.get("keys", {}).get(settings.deformation_active_key, {})
        active_id = settings.deformation_active_stamp_id
        for stamp in entry.get("stamps", []):
            if stamp.get("stampId") == active_id:
                stamp["capture"] = capture
                stamp["placementMode"] = capture.get("placementMode")
                stamp["center"] = list(capture.get("centerWorld", (0.0, 0.0, 0.0)))
                stamp["direction"] = list(_seed_direction_world(settings, attached))
                _store_metadata(attached, detached, payload)
                break
    except Exception:
        pass


def _active_key_context(context, require=True):
    settings = context.scene.daf_settings
    registry, region, attached, detached = _resolve_active_region(context)
    name = settings.deformation_active_key
    payload = _metadata(attached)
    entry = payload.get("keys", {}).get(name)
    if require and (not name or entry is None or _key(attached, name) is None):
        raise RuntimeError("Select or create a managed deformation key in the active region first.")
    return settings, registry, region, attached, detached, payload, name, entry


def _active_stamp(settings, entry, require=True):
    active_id = settings.deformation_active_stamp_id
    stamp = next((value for value in (entry or {}).get("stamps", []) if value.get("stampId") == active_id), None)
    if require and stamp is None:
        raise RuntimeError("Select an active trauma stamp first.")
    return stamp


def _stamp_from_settings(context, stamp_id=None, order_index=0):
    settings, _registry, region, attached, _detached, _payload, _name, _entry = _active_key_context(context)
    capture = _capture_payload(settings)
    errors = _capture_errors(capture, region, attached)
    if errors:
        raise RuntimeError(" ".join(errors))
    return trauma_field.normalize_stamp({
        "stampId": stamp_id or trauma_field.new_stamp_id(),
        "displayName": settings.deformation_stamp_name.strip() or settings.deformation_stamp_family.replace("_", " ").title(),
        "enabled": True,
        "family": settings.deformation_stamp_family,
        "placementMode": capture.get("placementMode", settings.deformation_capture_mode),
        "capture": capture,
        "center": capture.get("centerWorld", (0.0, 0.0, 0.0)),
        "direction": list(_seed_direction_world(settings, attached)),
        "radius": float(settings.deformation_seed_radius),
        "depth": float(settings.deformation_seed_depth),
        "falloff": float(settings.deformation_seed_falloff),
        "influenceMode": settings.deformation_influence_mode,
        "distanceMode": settings.deformation_distance_mode,
        "featherDistance": float(settings.deformation_feather_distance),
        "seamProtection": float(settings.deformation_seed_seam_protection),
        "strength": float(settings.deformation_stamp_strength),
        "maximumDisplacement": float(settings.deformation_max_vertex_displacement),
        "orderIndex": int(order_index),
    })


def _load_stamp_into_settings(settings, stamp):
    auto_preview = settings.deformation_auto_preview
    settings.deformation_auto_preview = False
    try:
        settings.deformation_active_stamp_id = str(stamp.get("stampId", ""))
        settings.deformation_stamp_name = str(stamp.get("displayName", "Trauma Stamp"))
        settings.deformation_stamp_family = str(stamp.get("family", "COMPACT_DENT"))
        settings.deformation_capture_mode = str(stamp.get("placementMode", "SINGLE_FACE"))
        settings.deformation_influence_mode = str(stamp.get("influenceMode", "PATCH_FEATHERED"))
        settings.deformation_distance_mode = str(stamp.get("distanceMode", "SURFACE_DISTANCE"))
        settings.deformation_feather_distance = float(stamp.get("featherDistance", 0.02))
        settings.deformation_seed_radius = float(stamp.get("radius", 0.075))
        settings.deformation_seed_depth = float(stamp.get("depth", 0.025))
        settings.deformation_seed_falloff = float(stamp.get("falloff", 2.0))
        settings.deformation_seed_seam_protection = float(stamp.get("seamProtection", 0.025))
        settings.deformation_stamp_strength = float(stamp.get("strength", 1.0))
        capture = stamp.get("capture", {})
        if capture:
            settings.deformation_capture_json = json.dumps(capture, sort_keys=True, separators=(",", ":"))
            settings.deformation_seed_center = tuple(capture.get("centerLocal", (0.0, 0.0, 0.0)))
            settings.deformation_seed_surface_normal = tuple(capture.get("normalLocal", (0.0, 0.0, 1.0)))
            settings.deformation_seed_center_valid = True
    finally:
        settings.deformation_auto_preview = auto_preview


def _basis_world_positions(attached):
    basis = _ensure_basis(attached)
    return [tuple(attached.matrix_world @ point.co) for point in basis.data]


def _stamp_weights(attached, region, stamp):
    capture = stamp.get("capture", {})
    errors = _capture_errors(capture, region, attached)
    if errors:
        raise RuntimeError(" ".join(errors))
    vertex_count = len(attached.data.vertices)
    selected = [int(index) for index in capture.get("vertexIndices", [])]
    influence_mode = stamp.get("influenceMode", "PATCH_FEATHERED")
    distance_mode = stamp.get("distanceMode", "SURFACE_DISTANCE")
    radius = float(stamp.get("radius", 0.075))
    feather = float(stamp.get("featherDistance", 0.02))
    maximum_traversal = feather if influence_mode == "PATCH_FEATHERED" else radius
    if influence_mode == "PATCH_ONLY":
        distances = {index: 0.0 for index in selected}
    elif distance_mode == "WORLD_DISTANCE":
        center = Vector(stamp.get("center", (0.0, 0.0, 0.0)))
        distances = {
            index: (attached.matrix_world @ vertex.co - center).length
            for index, vertex in enumerate(attached.data.vertices)
            if (attached.matrix_world @ vertex.co - center).length <= maximum_traversal
        }
    else:
        topology = _topology_fingerprint(attached)
        cache_key = trauma_field.geodesic_cache_key(
            topology,
            f"{attached.name}:{attached.data.name}",
            capture.get("selectionHash", ""),
            distance_mode,
            maximum_traversal,
        )
        if cache_key not in _GEODESIC_CACHE:
            positions = [tuple(attached.matrix_world @ vertex.co) for vertex in attached.data.vertices]
            edges = [tuple(edge.vertices) for edge in attached.data.edges]
            adjacency = trauma_field.build_weighted_adjacency(vertex_count, edges, positions)
            _GEODESIC_CACHE[cache_key] = trauma_field.geodesic_distances(adjacency, selected, maximum_traversal)
            _GEODESIC_CACHE_CONTEXT[cache_key] = {
                "topologyFingerprint": topology,
                "objectIdentity": f"{attached.name}:{attached.data.name}",
                "objectName": attached.name,
                "meshDataName": attached.data.name,
                "selectionHash": capture.get("selectionHash", ""),
                "distanceMode": distance_mode,
                "maximumDistance": maximum_traversal,
            }
        distances = _GEODESIC_CACHE[cache_key]
    weights = list(trauma_field.surface_mask_weights(
        vertex_count,
        selected,
        distances,
        influence_mode,
        radius,
        feather,
        float(stamp.get("falloff", 2.0)),
    ))
    seam_protection = float(stamp.get("seamProtection", 0.0))
    if seam_protection > 0.0:
        seam_points = [attached.matrix_world @ point for point in _region_seam_points(region)]
        if seam_points:
            for index, vertex in enumerate(attached.data.vertices):
                point_world = attached.matrix_world @ vertex.co
                seam_distance = min((point_world - point).length for point in seam_points)
                weights[index] *= _smoothstep(seam_distance / seam_protection)
    return tuple(weights), dict(distances)


def _stamp_local_coordinates(attached, stamps):
    basis_world = _basis_world_positions(attached)
    _registry, region, _active, _detached = _resolve_active_region()
    weights_by_stamp = {}
    distances_by_stamp = {}
    for stamp in stamps:
        weights, distances = _stamp_weights(attached, region, stamp)
        weights_by_stamp[str(stamp["stampId"])] = weights
        distances_by_stamp[str(stamp["stampId"])] = distances
    final_world = trauma_field.evaluate_stamp_stack(basis_world, stamps, weights_by_stamp, distances_by_stamp)
    inverse_world = attached.matrix_world.inverted()
    return [inverse_world @ Vector(position) for position in final_world]


def preview_active_stamp(context, quiet=False):
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        raise RuntimeError("Switch to Object Mode before previewing a trauma stamp.")
    settings, _registry, _region, attached, detached, _payload, _name, entry = _active_key_context(context)
    stamp = _active_stamp(settings, entry)
    preview_stamp = dict(stamp)
    preview_stamp["orderIndex"] = 0
    attached, detached, attached_preview, _detached_preview = _ensure_key_pair(PREVIEW_KEY_NAME, preview=True)
    _zero_managed_weights(attached)
    _set_key_coordinates(attached_preview, _stamp_local_coordinates(attached, [preview_stamp]))
    sync_key_to_detached(PREVIEW_KEY_NAME)
    attached_preview.value = 1.0
    attached_preview.slider_max = 1.0
    _set_authoring_view(attached, detached, 'ATTACHED')
    settings.deformation_status = f"STAMP PREVIEW — {stamp.get('displayName', stamp.get('stampId'))}"
    if not quiet:
        return {"stampId": stamp.get("stampId"), "vertexCount": len(attached_preview.data)}
    return None


def rebuild_active_deformation(context):
    settings, _registry, region, attached, detached, payload, name, entry = _active_key_context(context)
    stamps = trauma_field.reindex_stamps(entry.get("stamps", []))
    if not stamps:
        raise RuntimeError("The active deformation has no trauma stamps; legacy/manual geometry was not overwritten.")
    errors = trauma_field.validate_stamp_stack(stamps)
    if errors:
        raise RuntimeError(" ".join(errors))
    coordinates = _stamp_local_coordinates(attached, stamps)
    target = _key(attached, name)
    _set_key_coordinates(target, coordinates)
    sync_key_to_detached(name)
    entry["stamps"] = stamps
    entry["status"] = "TRAUMA_REBUILT"
    entry["recipeStatus"] = "PROCEDURAL_STACK"
    entry["legacy"] = False
    entry["recipeDigest"] = trauma_field.recipe_digest(stamps)
    entry["region"] = region.get("regionId")
    entry["regionId"] = region.get("regionId")
    _store_metadata(attached, detached, payload)
    clear_seed_preview()
    _zero_managed_weights(attached)
    target.value = min(1.0, target.slider_max)
    _set_authoring_view(attached, detached, 'ATTACHED')
    validation = validate_deformations(require_keys=True)
    if validation["status"] != "PASS":
        raise RuntimeError("Rebuilt deformation failed validation: " + "; ".join(validation["errors"][:4]))
    settings.last_deformation_validation = validation["status"]
    settings.deformation_status = f"REBUILT FROM BASIS — {name} / {len(stamps)} stamps"
    return {"key": name, "stampCount": len(stamps), "validation": validation}


def _manifest_stamp(stamp):
    capture = stamp.get("capture", {})
    return {
        "stampId": stamp.get("stampId"),
        "displayName": stamp.get("displayName"),
        "enabled": bool(stamp.get("enabled", True)),
        "family": stamp.get("family"),
        "placementMode": stamp.get("placementMode"),
        "center": stamp.get("center"),
        "direction": stamp.get("direction"),
        "radius": stamp.get("radius"),
        "depth": stamp.get("depth"),
        "falloff": stamp.get("falloff"),
        "influenceMode": stamp.get("influenceMode"),
        "distanceMode": stamp.get("distanceMode"),
        "featherDistance": stamp.get("featherDistance"),
        "seamProtection": stamp.get("seamProtection"),
        "strength": stamp.get("strength"),
        "maximumDisplacement": stamp.get("maximumDisplacement"),
        "orderIndex": stamp.get("orderIndex"),
        "capture": {
            "selectionHash": capture.get("selectionHash"),
            "topologyFingerprint": capture.get("topologyFingerprint"),
            "faceCount": len(capture.get("faceIndices", [])),
            "vertexCount": len(capture.get("vertexIndices", [])),
            "boundsWorld": capture.get("boundsWorld"),
            "estimatedRadius": capture.get("estimatedRadius"),
        },
    }


def validate_deformations(require_keys=False):
    registry = _load_registry()
    errors = []
    warnings = []
    region_records = []
    key_records = []
    total_names = 0
    region_ids = [str(region.get("regionId", "")) for region in registry.get("regions", [])]
    if not region_ids:
        errors.append("No deformation regions are registered.")
    duplicates = sorted({region_id for region_id in region_ids if region_ids.count(region_id) > 1})
    if duplicates:
        errors.append("Duplicate semantic deformation region IDs: " + ", ".join(duplicates) + ".")
    if registry.get("activeRegionId") not in set(region_ids):
        errors.append("The active deformation region references a removed or missing registration.")
    active_pair = None
    settings = getattr(getattr(bpy.context, "scene", None), "daf_settings", None)
    for region in registry.get("regions", []):
        region_id = str(region.get("regionId", ""))
        region_errors = []
        if not region_id:
            region_errors.append("A deformation region has an empty semantic ID.")
        attached = _object(region.get("attachedObject", ""))
        detached = _object(region.get("detachedObject", ""))
        pair = validate_topology_pair(attached, detached)
        region_errors.extend(pair["errors"])
        if pair["status"] != "PASS":
            errors.extend(f"Region {region_id or '<empty>'}: {message}" for message in pair["errors"])
            region_records.append({"regionId": region_id, "status": "FAIL", "errors": region_errors, "keys": []})
            continue
        if region_id == registry.get("activeRegionId"):
            active_pair = pair
        if region.get("topologyFingerprint") and region.get("topologyFingerprint") != pair.get("topologyFingerprint"):
            region_errors.append("Stored region topology fingerprint is stale; validate or re-register the pair.")
        if int(region.get("attachedVertexCount", pair["attachedVertexCount"])) != pair["attachedVertexCount"]:
            region_errors.append("Stored attached vertex count is stale.")
        if int(region.get("detachedVertexCount", pair["detachedVertexCount"])) != pair["detachedVertexCount"]:
            region_errors.append("Stored detached vertex count is stale.")
        if int(region.get("polygonCount", pair["attachedPolygonCount"])) != pair["attachedPolygonCount"]:
            region_errors.append("Stored polygon count is stale.")
        payload = _metadata(attached)
        names = _managed_names(attached)
        total_names += len(names)
        registered_names = set(region.get("managedKeys", []))
        metadata_names = set(payload.get("keys", {}))
        removed_references = sorted(registered_names - metadata_names)
        if removed_references:
            region_errors.append("Region references removed managed keys: " + ", ".join(removed_references) + ".")
        region_key_records = []
        for name in names:
            attached_key = _key(attached, name)
            detached_key = _key(detached, name)
            if attached_key is None or detached_key is None:
                region_errors.append(f"Managed deformation {name} is missing from one side of region {region_id}.")
                continue
            if len(attached_key.data) != len(detached_key.data):
                region_errors.append(f"Managed deformation {name} has mismatched point counts.")
                continue
            attached_basis = attached.data.shape_keys.reference_key
            detached_basis = detached.data.shape_keys.reference_key
            max_delta_error = 0.0
            finite = True
            for index in range(len(attached_key.data)):
                delta_a = _local_delta_to_world(attached, attached_key.data[index].co - attached_basis.data[index].co)
                delta_d = _local_delta_to_world(detached, detached_key.data[index].co - detached_basis.data[index].co)
                max_delta_error = max(max_delta_error, (delta_a - delta_d).length)
                finite = finite and all(math.isfinite(value) for value in (*attached_key.data[index].co, *detached_key.data[index].co))
            if not finite:
                region_errors.append(f"Managed deformation {name} contains non-finite coordinates.")
            if max_delta_error > SYNC_TOLERANCE:
                region_errors.append(f"Managed deformation {name} detached delta mismatch is {max_delta_error:.8f} m.")
            entry = payload.get("keys", {}).get(name, {})
            if entry.get("regionId", entry.get("region", region_id)) != region_id:
                region_errors.append(f"Managed deformation {name} references removed or incorrect region {entry.get('regionId')}.")
            maximum = float(entry.get("maximumDisplacement", 0.1))
            measured = _max_displacement(attached, name)
            if not math.isfinite(maximum) or maximum <= 0.0:
                region_errors.append(f"Managed deformation {name} has an invalid maximum displacement.")
            elif measured > maximum + PAIR_TOLERANCE:
                region_errors.append(f"Managed deformation {name} exceeds its maximum displacement: {measured:.6f} m > {maximum:.6f} m.")
            stamps = entry.get("stamps", [])
            stamp_errors = trauma_field.validate_stamp_stack(stamps) if stamps else []
            region_errors.extend(f"Managed deformation {name}: {message}" for message in stamp_errors)
            for stamp in stamps:
                region_errors.extend(
                    f"Managed deformation {name}, stamp {stamp.get('stampId', '<missing>')}: {message}"
                    for message in _capture_errors(stamp.get("capture", {}), region, attached)
                )
            if settings and region_id == _active_region_id() and name == settings.deformation_active_key and stamps:
                active_stamp_id = settings.deformation_active_stamp_id
                if active_stamp_id and not any(stamp.get("stampId") == active_stamp_id for stamp in stamps):
                    region_errors.append("The active trauma stamp references a removed stamp.")
            record = {
                "name": name,
                "regionId": region_id,
                "maximumInfluence": float(entry.get("maximumInfluence", attached_key.slider_max)),
                "maximumDisplacement": maximum,
                "measuredMaximumDisplacement": measured,
                "maximumPairDeltaError": max_delta_error,
                "status": entry.get("status", "UNKNOWN"),
                "recipeStatus": entry.get("recipeStatus", "LEGACY_MANUAL"),
                "stampCount": len(stamps),
            }
            region_key_records.append(record)
            key_records.append(record)
        if _key(attached, PREVIEW_KEY_NAME) or _key(detached, PREVIEW_KEY_NAME):
            warnings.append(f"Region {region_id} contains the temporary preview key; export will remove it.")
        errors.extend(f"Region {region_id}: {message}" for message in region_errors)
        region["validationStatus"] = "PASS" if not region_errors else "FAIL"
        region_records.append({
            "regionId": region_id,
            "attachedObject": attached.name,
            "detachedObject": detached.name,
            "status": region["validationStatus"],
            "topologyPair": pair,
            "keys": region_key_records,
            "errors": region_errors,
        })
    for cache_key, cache_context in _GEODESIC_CACHE_CONTEXT.items():
        try:
            expected = trauma_field.geodesic_cache_key(
                cache_context["topologyFingerprint"], cache_context["objectIdentity"],
                cache_context["selectionHash"], cache_context["distanceMode"], cache_context["maximumDistance"],
            )
            cached_object = _object(cache_context.get("objectName", ""))
            current_identity = (
                f"{cached_object.name}:{cached_object.data.name}"
                if cached_object is not None and cached_object.type == 'MESH' else ""
            )
            current_topology = _topology_fingerprint(cached_object) if current_identity else ""
            if (
                expected != cache_key
                or cache_key not in _GEODESIC_CACHE
                or current_identity != cache_context["objectIdentity"]
                or current_topology != cache_context["topologyFingerprint"]
                or (cached_object is not None and cached_object.data.name != cache_context.get("meshDataName"))
            ):
                errors.append("A stale geodesic cache key was detected; recapture or rebuild the active stamp.")
        except Exception as exc:
            errors.append("A geodesic cache record is invalid: " + str(exc))
    if require_keys and not total_names:
        errors.append("No managed deformation keys exist.")
    _store_registry(registry)
    return {
        "status": "PASS" if not errors else "FAIL",
        "schema": DEFORMATION_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": DEFORMATION_BUILD_ID,
        "topologyPair": active_pair or {},
        "registeredRegionCount": len(region_records),
        "activeRegionId": registry.get("activeRegionId", ""),
        "regions": region_records,
        "managedKeyCount": total_names,
        "keys": key_records,
        "errors": errors,
        "warnings": warnings,
    }


def prepare_for_export():
    clear_seed_preview(all_regions=True)
    registry = _load_registry()
    for region in registry.get("regions", []):
        attached, _detached = _resolve_region_pair(region)
        for name in _managed_names(attached):
            sync_key_to_detached(name, region.get("regionId"))
    validation = validate_deformations(require_keys=False)
    if validation["status"] != "PASS":
        raise RuntimeError("Deformation validation failed: " + "; ".join(validation["errors"][:4]))
    return validation


def get_deformation_manifest():
    registry = _load_registry()
    if not registry.get("regions"):
        return {"schema": DEFORMATION_SCHEMA, "authoringVersion": _version_string(), "registeredRegions": [], "keys": []}
    validation = validate_deformations(require_keys=False)
    validation_by_region = {record.get("regionId"): record for record in validation.get("regions", [])}
    manifest_regions = []
    flat_keys = []
    for region in registry.get("regions", []):
        attached, detached = _resolve_region_pair(region)
        payload = _metadata(attached)
        keys = []
        validation_record = validation_by_region.get(region.get("regionId"), {})
        validation_keys = {record.get("name"): record for record in validation_record.get("keys", [])}
        for name in _managed_names(attached):
            source_entry = payload.get("keys", {}).get(name, {})
            key_validation = validation_keys.get(name, {})
            entry = {
                "name": name,
                "regionId": region.get("regionId"),
                "attachedObject": attached.name,
                "detachedObject": detached.name,
                "status": source_entry.get("status", "UNKNOWN"),
                "recipeStatus": source_entry.get("recipeStatus", "LEGACY_MANUAL"),
                "legacy": bool(source_entry.get("legacy", not source_entry.get("stamps"))),
                "maximumInfluence": source_entry.get("maximumInfluence"),
                "maximumDisplacement": source_entry.get("maximumDisplacement"),
                "measuredMaximumDisplacement": key_validation.get("measuredMaximumDisplacement", _max_displacement(attached, name)),
                "maximumPairDeltaError": key_validation.get("maximumPairDeltaError"),
                "validationStatus": validation_record.get("status", "UNKNOWN"),
                "orderedStamps": [_manifest_stamp(stamp) for stamp in source_entry.get("stamps", [])],
                "recipeDigest": source_entry.get("recipeDigest"),
            }
            keys.append(entry)
            flat_keys.append(entry)
        manifest_regions.append({
            "regionId": region.get("regionId"),
            "attachedObject": attached.name,
            "detachedObject": detached.name,
            "topologyFingerprint": _topology_fingerprint(attached),
            "attachedVertexCount": len(attached.data.vertices),
            "detachedVertexCount": len(detached.data.vertices),
            "polygonCount": len(attached.data.polygons),
            "relatedSeamId": region.get("relatedSeamId", ""),
            "managedKeyNames": [entry["name"] for entry in keys],
            "validationStatus": validation_record.get("status", "UNKNOWN"),
            "keys": keys,
        })
    result = {
        "schema": DEFORMATION_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": DEFORMATION_BUILD_ID,
        "activeRegionId": registry.get("activeRegionId", ""),
        "authoredRegionIds": [region["regionId"] for region in manifest_regions if region["managedKeyNames"]],
        "registeredRegions": manifest_regions,
        "keys": flat_keys,
        "validationStatus": validation.get("status", "UNKNOWN"),
    }
    legacy_head = next((region for region in manifest_regions if region.get("regionId") == "head"), None)
    if legacy_head:
        result.update({
            "region": "head",
            "attachedObject": legacy_head["attachedObject"],
            "detachedObject": legacy_head["detachedObject"],
            "topologyFingerprint": legacy_head["topologyFingerprint"],
        })
    return result


class DAF_OT_register_deformation_region(Operator):
    bl_idname = "daf.register_deformation_region"
    bl_label = "Register Selected Region Pair"
    bl_description = "Register the active selected mesh as attached and the other selected mesh as its exact-index detached pair"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            region_id = settings.deformation_region_id.strip().lower()
            if not re.fullmatch(r"[a-z][a-z0-9_]*", region_id):
                raise RuntimeError("Region ID must start with a lowercase letter and contain only lowercase letters, digits, and underscores.")
            selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
            if len(selected) != 2 or context.active_object not in selected:
                raise RuntimeError("Select exactly two mesh objects and make the intended attached object active.")
            attached = context.active_object
            detached = next(obj for obj in selected if obj != attached)
            if attached.name == detached.name:
                raise RuntimeError("Attached and detached object names must differ.")
            registry = _load_registry()
            if _region_record(registry, region_id) is not None:
                raise RuntimeError(f"Semantic deformation region ID {region_id!r} is already registered.")
            used_names = {
                name for region in registry.get("regions", [])
                for name in (region.get("attachedObject"), region.get("detachedObject"))
            }
            if attached.name in used_names or detached.name in used_names:
                raise RuntimeError("One of the selected objects is already assigned to a deformation region; remove that registration explicitly first.")
            contract = validate_topology_pair(attached, detached)
            if contract["status"] != "PASS":
                raise RuntimeError(" ".join(contract["errors"]))
            record = _record_from_pair(region_id, attached, detached, settings.deformation_related_seam_id.strip())
            registry.setdefault("regions", []).append(record)
            registry["activeRegionId"] = region_id
            _store_registry(registry)
            settings.deformation_region = region_id
            settings.deformation_status = f"REGION REGISTERED — {region_id}"
            _invalidate_geodesic_cache()
            self.report({'INFO'}, f"Registered {attached.name} ↔ {detached.name} as {region_id}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_select_deformation_region(Operator):
    bl_idname = "daf.select_deformation_region"
    bl_label = "Select Active Region"
    bl_options = {'REGISTER'}
    region_id: StringProperty()

    def execute(self, context):
        try:
            _set_active_region(self.region_id or context.scene.daf_settings.deformation_region, context)
            context.scene.daf_settings.deformation_active_key = ""
            context.scene.daf_settings.deformation_active_stamp_id = ""
            context.scene.daf_settings.deformation_capture_json = ""
            context.scene.daf_settings.deformation_seed_center_valid = False
            context.scene.daf_settings.deformation_status = f"ACTIVE REGION — {_active_region_id(context)}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_validate_deformation_region(Operator):
    bl_idname = "daf.validate_deformation_region"
    bl_label = "Validate Registered Pair"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            registry, region, attached, detached = _resolve_active_region(context)
            contract = validate_topology_pair(attached, detached)
            region.update({
                "topologyFingerprint": contract.get("topologyFingerprint", ""),
                "attachedVertexCount": contract.get("attachedVertexCount", 0),
                "detachedVertexCount": contract.get("detachedVertexCount", 0),
                "polygonCount": contract.get("attachedPolygonCount", 0),
                "validationStatus": contract["status"],
            })
            _store_registry(registry)
            if contract["status"] != "PASS":
                raise RuntimeError(" ".join(contract["errors"]))
            context.scene.daf_settings.deformation_status = f"REGION VALID — {region['regionId']}"
            self.report({'INFO'}, f"Validated exact-index region {region['regionId']}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_remove_deformation_region(Operator):
    bl_idname = "daf.remove_deformation_region"
    bl_label = "Remove Region Registration"
    bl_description = "Remove only the region registration; existing shape keys and mesh data are not deleted"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            registry = _load_registry()
            region_id = _active_region_id(context)
            region = _region_record(registry, region_id)
            if region is None:
                raise RuntimeError("No active deformation region is registered.")
            registered_objects = [
                _object(region.get("attachedObject", "")),
                _object(region.get("detachedObject", "")),
            ]
            registry["regions"] = [value for value in registry.get("regions", []) if value.get("regionId") != region_id]
            registry["activeRegionId"] = registry["regions"][0].get("regionId", "") if registry["regions"] else ""
            _store_registry(registry)
            for obj in registered_objects:
                if obj is not None and REGISTRY_PROPERTY in obj:
                    del obj[REGISTRY_PROPERTY]
                if obj is not None and "dsb_deformation_region" in obj:
                    del obj["dsb_deformation_region"]
            context.scene.daf_settings.deformation_active_key = ""
            context.scene.daf_settings.deformation_active_stamp_id = ""
            context.scene.daf_settings.deformation_capture_json = ""
            context.scene.daf_settings.deformation_seed_center_valid = False
            context.scene.daf_settings.deformation_status = f"REGION REGISTRATION REMOVED — {region_id}"
            _invalidate_geodesic_cache()
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def _capture_bounds_and_radius(attached, vertex_indices, center_local):
    points = [attached.matrix_world @ attached.data.vertices[index].co for index in vertex_indices]
    center_world = attached.matrix_world @ center_local
    minimum = [min(point[axis] for point in points) for axis in range(3)]
    maximum = [max(point[axis] for point in points) for axis in range(3)]
    radius = max(((point - center_world).length for point in points), default=0.0)
    return center_world, [minimum, maximum], max(radius, 1e-6)


def _capture_face_selection(context, require_single=False):
    registry, region, attached, _detached = _resolve_active_region(context)
    if context.active_object != attached or context.mode != 'EDIT_MESH':
        raise RuntimeError(f"Make {attached.name} active, enter Edit Mode, and select one connected face patch.")
    mesh = bmesh.from_edit_mesh(attached.data)
    mesh.faces.ensure_lookup_table()
    mesh.verts.ensure_lookup_table()
    selected = [face for face in mesh.faces if face.select]
    if require_single and len(selected) != 1:
        raise RuntimeError("Select exactly one face for SINGLE_FACE capture.")
    if not selected:
        raise RuntimeError("Select at least one face on the active attached mesh.")
    selected_set = set(selected)
    visited = {selected[0]}
    stack = [selected[0]]
    while stack:
        face = stack.pop()
        for edge in face.edges:
            for linked in edge.link_faces:
                if linked in selected_set and linked not in visited:
                    visited.add(linked)
                    stack.append(linked)
    if len(visited) != len(selected_set):
        raise RuntimeError("The selected faces contain disconnected islands. Select exactly one connected face patch.")
    areas = [max(face.calc_area(), 1e-12) for face in selected]
    total_area = sum(areas)
    center = sum((face.calc_center_median() * area for face, area in zip(selected, areas)), Vector()) / total_area
    normal = sum((face.normal * area for face, area in zip(selected, areas)), Vector())
    if normal.length_squared <= 1e-12:
        raise RuntimeError("The selected face patch has no usable area-weighted surface normal.")
    normal.normalize()
    face_indices = sorted(face.index for face in selected)
    vertex_indices = sorted({vertex.index for face in selected for vertex in face.verts})
    topology = _topology_fingerprint(attached)
    center_world, bounds, radius = _capture_bounds_and_radius(attached, vertex_indices, center)
    placement = "SINGLE_FACE" if require_single else "SELECTED_FACE_PATCH"
    capture = {
        "placementMode": placement,
        "selectionKind": "FACE",
        "regionId": region.get("regionId"),
        "attachedObject": attached.name,
        "topologyFingerprint": topology,
        "faceIndices": face_indices,
        "vertexIndices": vertex_indices,
        "selectionHash": trauma_field.selection_hash(face_indices, topology, "FACE"),
        "centerLocal": list(center),
        "centerWorld": list(center_world),
        "normalLocal": list(normal),
        "normalWorld": list(_normal_local_to_world(attached, normal)),
        "boundsWorld": bounds,
        "estimatedRadius": radius,
        "connectedComponentCount": 1,
    }
    bpy.ops.object.mode_set(mode='OBJECT')
    _store_capture(context, capture)
    return capture


def _capture_vertex_selection(context):
    _registry, region, attached, _detached = _resolve_active_region(context)
    if context.active_object != attached or context.mode != 'EDIT_MESH':
        raise RuntimeError(f"Make {attached.name} active, enter Edit Mode, and select one or more vertices.")
    mesh = bmesh.from_edit_mesh(attached.data)
    mesh.verts.ensure_lookup_table()
    selected = [vertex for vertex in mesh.verts if vertex.select]
    if not selected:
        raise RuntimeError("Select at least one vertex on the active attached mesh.")
    center = sum((vertex.co for vertex in selected), Vector()) / len(selected)
    normal = Vector()
    for vertex in selected:
        for face in vertex.link_faces:
            normal += face.normal * max(face.calc_area(), 1e-12)
    if normal.length_squared <= 1e-12:
        raise RuntimeError("The selected vertices have no adjacent-face surface normal.")
    normal.normalize()
    vertex_indices = sorted(vertex.index for vertex in selected)
    topology = _topology_fingerprint(attached)
    center_world, bounds, radius = _capture_bounds_and_radius(attached, vertex_indices, center)
    capture = {
        "placementMode": "SELECTED_VERTICES",
        "selectionKind": "VERTEX",
        "regionId": region.get("regionId"),
        "attachedObject": attached.name,
        "topologyFingerprint": topology,
        "faceIndices": [],
        "vertexIndices": vertex_indices,
        "selectionHash": trauma_field.selection_hash(vertex_indices, topology, "VERTEX"),
        "centerLocal": list(center),
        "centerWorld": list(center_world),
        "normalLocal": list(normal),
        "normalWorld": list(_normal_local_to_world(attached, normal)),
        "boundsWorld": bounds,
        "estimatedRadius": radius,
    }
    bpy.ops.object.mode_set(mode='OBJECT')
    _store_capture(context, capture)
    return capture


class DAF_OT_capture_deformation_selected_patch(Operator):
    bl_idname = "daf.capture_deformation_selected_patch"
    bl_label = "Capture Connected Face Patch"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            capture = _capture_face_selection(context, require_single=False)
            context.scene.daf_settings.deformation_status = f"FACE PATCH CAPTURED — {len(capture['faceIndices'])} faces"
            refresh_live_seed_preview(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_capture_deformation_selected_vertices(Operator):
    bl_idname = "daf.capture_deformation_selected_vertices"
    bl_label = "Capture Selected Vertices"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            capture = _capture_vertex_selection(context)
            context.scene.daf_settings.deformation_status = f"VERTICES CAPTURED — {len(capture['vertexIndices'])} vertices"
            refresh_live_seed_preview(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_add_trauma_stamp(Operator):
    bl_idname = "daf.add_trauma_stamp"
    bl_label = "Add Stamp"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings, _registry, _region, attached, detached, payload, name, entry = _active_key_context(context)
            stamps = list(entry.setdefault("stamps", []))
            created = _stamp_from_settings(context, order_index=len(stamps))
            stamps.append(created)
            entry["stamps"] = trauma_field.reindex_stamps(stamps)
            entry["recipeStatus"] = "PROCEDURAL_STACK"
            entry["legacy"] = False
            _store_metadata(attached, detached, payload)
            _invalidate_geodesic_cache()
            settings.deformation_active_stamp_id = created["stampId"]
            settings.deformation_status = f"STAMP ADDED — {created['displayName']}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_select_trauma_stamp(Operator):
    bl_idname = "daf.select_trauma_stamp"
    bl_label = "Select Active Stamp"
    bl_options = {'REGISTER'}
    stamp_id: StringProperty()

    def execute(self, context):
        try:
            settings, _registry, _region, _attached, _detached, _payload, _name, entry = _active_key_context(context)
            stamp = next((value for value in entry.get("stamps", []) if value.get("stampId") == self.stamp_id), None)
            if stamp is None:
                raise RuntimeError("The selected trauma stamp no longer exists.")
            _load_stamp_into_settings(settings, stamp)
            settings.deformation_status = f"ACTIVE STAMP — {stamp.get('displayName', self.stamp_id)}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_update_trauma_stamp(Operator):
    bl_idname = "daf.update_trauma_stamp"
    bl_label = "Update Active Stamp"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings, _registry, _region, attached, detached, payload, _name, entry = _active_key_context(context)
            active = _active_stamp(settings, entry)
            replacement = _stamp_from_settings(context, stamp_id=active["stampId"], order_index=active["orderIndex"])
            for index, stamp in enumerate(entry["stamps"]):
                if stamp.get("stampId") == active["stampId"]:
                    replacement["enabled"] = bool(active.get("enabled", True))
                    entry["stamps"][index] = replacement
                    break
            _store_metadata(attached, detached, payload)
            _invalidate_geodesic_cache()
            settings.deformation_status = f"STAMP UPDATED — {replacement['displayName']}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_duplicate_trauma_stamp(Operator):
    bl_idname = "daf.duplicate_trauma_stamp"
    bl_label = "Duplicate Stamp"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings, _registry, _region, attached, detached, payload, _name, entry = _active_key_context(context)
            active = _active_stamp(settings, entry)
            stamps = list(entry.get("stamps", []))
            source_index = next(index for index, stamp in enumerate(stamps) if stamp.get("stampId") == active["stampId"])
            duplicate = trauma_field.duplicate_stamp(active)
            stamps.insert(source_index + 1, duplicate)
            entry["stamps"] = trauma_field.reindex_stamps(stamps)
            _store_metadata(attached, detached, payload)
            _invalidate_geodesic_cache()
            _load_stamp_into_settings(settings, duplicate)
            settings.deformation_status = f"STAMP DUPLICATED — {duplicate['displayName']}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_remove_trauma_stamp(Operator):
    bl_idname = "daf.remove_trauma_stamp"
    bl_label = "Remove Stamp"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings, _registry, _region, attached, detached, payload, _name, entry = _active_key_context(context)
            active = _active_stamp(settings, entry)
            stamps = [stamp for stamp in entry.get("stamps", []) if stamp.get("stampId") != active["stampId"]]
            entry["stamps"] = trauma_field.reindex_stamps(stamps)
            _store_metadata(attached, detached, payload)
            _invalidate_geodesic_cache()
            settings.deformation_active_stamp_id = ""
            if stamps:
                _load_stamp_into_settings(settings, stamps[min(int(active.get("orderIndex", 0)), len(stamps) - 1)])
            settings.deformation_status = f"STAMP REMOVED — {active.get('displayName', active['stampId'])}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def _move_active_stamp(context, offset):
    settings, _registry, _region, attached, detached, payload, _name, entry = _active_key_context(context)
    active = _active_stamp(settings, entry)
    stamps = list(entry.get("stamps", []))
    index = next(position for position, stamp in enumerate(stamps) if stamp.get("stampId") == active["stampId"])
    target = max(0, min(len(stamps) - 1, index + offset))
    if target != index:
        stamps[index], stamps[target] = stamps[target], stamps[index]
    entry["stamps"] = trauma_field.reindex_stamps(stamps)
    _store_metadata(attached, detached, payload)
    _invalidate_geodesic_cache()


class DAF_OT_move_trauma_stamp_up(Operator):
    bl_idname = "daf.move_trauma_stamp_up"
    bl_label = "Move Stamp Up"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _move_active_stamp(context, -1)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_move_trauma_stamp_down(Operator):
    bl_idname = "daf.move_trauma_stamp_down"
    bl_label = "Move Stamp Down"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _move_active_stamp(context, 1)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_toggle_trauma_stamp(Operator):
    bl_idname = "daf.toggle_trauma_stamp"
    bl_label = "Enable / Disable Stamp"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings, _registry, _region, attached, detached, payload, _name, entry = _active_key_context(context)
            active = _active_stamp(settings, entry)
            active["enabled"] = not bool(active.get("enabled", True))
            _store_metadata(attached, detached, payload)
            _invalidate_geodesic_cache()
            settings.deformation_status = ("STAMP ENABLED — " if active["enabled"] else "STAMP DISABLED — ") + str(active.get("displayName"))
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_preview_active_trauma_stamp(Operator):
    bl_idname = "daf.preview_active_trauma_stamp"
    bl_label = "Preview Active Stamp"
    bl_description = "Preview only the selected stamp on the temporary key without changing the permanent deformation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            preview_active_stamp(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_rebuild_active_deformation(Operator):
    bl_idname = "daf.rebuild_active_deformation"
    bl_label = "Rebuild Active Deformation"
    bl_description = "Replay the complete enabled trauma stamp stack from Basis in explicit order"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            result = rebuild_active_deformation(context)
            self.report({'INFO'}, f"Rebuilt {result['key']} from {result['stampCount']} trauma stamps.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_create_damage_shape_key(Operator):
    bl_idname = "daf.create_damage_shape_key"
    bl_label = "Create Damage Shape Key"
    bl_description = "Create a protected paired deformation key on the active registered region"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            name = settings.deformation_key_name.strip()
            template = STANDARD_HEAD_KEYS.get(name, {
                "family": "manual", "side": "configurable", "mirrorPartner": "",
                "seedRadius": settings.deformation_seed_radius,
                "seedDepth": settings.deformation_seed_depth,
                "seedFalloff": settings.deformation_seed_falloff,
                "maximumInfluence": settings.deformation_maximum_influence,
                "maximumDisplacement": settings.deformation_max_vertex_displacement,
            })
            _ensure_key_pair(name, template)
            _select_key(settings, name)
            settings.deformation_status = f"CREATED — {name}"
            self.report({'INFO'}, f"Created paired deformation key {name}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_create_standard_head_deformations(Operator):
    bl_idname = "daf.create_standard_head_deformations"
    bl_label = "Create Standard Head Set"
    bl_description = "Create the four standard head deformation keys for one-click presets or optional artist sculpting"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _registry, region, attached, detached = _resolve_active_region(context)
            if region.get("regionId") != "head":
                raise RuntimeError("Create Standard Head Set is available only when the legacy Testman head region is active.")
            for name, template in STANDARD_HEAD_KEYS.items():
                _ensure_key_pair(name, template)
            _zero_managed_weights(attached, include_preview=True)
            _set_authoring_view(attached, detached, 'ATTACHED')
            _select_key(context.scene.daf_settings, "Head_Dent_Left")
            context.scene.daf_settings.deformation_status = "STANDARD HEAD SET READY"
            self.report({'INFO'}, "Created the four paired standard head deformation keys.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_select_deformation_key(Operator):
    bl_idname = "daf.select_deformation_key"
    bl_label = "Select Deformation Key"
    bl_options = {'REGISTER'}
    key_name: StringProperty()

    def execute(self, context):
        try:
            attached, detached = _resolve_pair()
            _zero_managed_weights(attached, include_preview=True)
            _set_authoring_view(attached, detached, 'ATTACHED')
            _select_key(context.scene.daf_settings, self.key_name)
            key = _key(attached, self.key_name)
            if key and _max_displacement(attached, self.key_name) > 1e-7:
                key.value = min(1.0, key.slider_max)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_solo_deformation_key(Operator):
    bl_idname = "daf.solo_deformation_key"
    bl_label = "Solo Deformation Key"
    bl_options = {'REGISTER'}
    key_name: StringProperty()

    def execute(self, context):
        try:
            attached, _detached = _resolve_pair()
            for name in _managed_names(attached):
                _key(attached, name).value = 1.0 if name == self.key_name else 0.0
            preview = _key(attached, PREVIEW_KEY_NAME)
            if preview:
                preview.value = 0.0
            _select_key(context.scene.daf_settings, self.key_name)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_zero_deformations(Operator):
    bl_idname = "daf.zero_deformations"
    bl_label = "Zero All Deformations"
    bl_description = "Set every managed deformation preview weight to zero"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            attached, _detached = _resolve_pair()
            if attached.data.shape_keys:
                for key in attached.data.shape_keys.key_blocks:
                    if key.name != "Basis":
                        key.value = 0.0
            context.scene.daf_settings.deformation_status = "ALL WEIGHTS ZERO"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_delete_managed_deformation(Operator):
    bl_idname = "daf.delete_managed_deformation"
    bl_label = "Delete Managed Deformation"
    bl_description = "Delete only the selected Forge-managed deformation key from both objects in the active region"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            name = settings.deformation_active_key
            attached, detached = _resolve_pair()
            if name not in _managed_names(attached):
                raise RuntimeError("Select a managed deformation key first.")
            _remove_key(attached, name)
            _remove_key(detached, name)
            payload = _metadata(attached)
            payload.get("keys", {}).pop(name, None)
            _store_metadata(attached, detached, payload)
            settings.deformation_active_key = ""
            settings.deformation_status = f"DELETED — {name}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_capture_deformation_selected_face(Operator):
    bl_idname = "daf.capture_deformation_selected_face"
    bl_label = "Capture Center from Selected Face"
    bl_description = "Capture the center and outward normal of exactly one face on the active attached region mesh"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            _capture_face_selection(context, require_single=True)
            settings = context.scene.daf_settings
            settings.deformation_status = "SURFACE CENTER CAPTURED"
            refresh_live_seed_preview(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_capture_deformation_cursor(Operator):
    bl_idname = "daf.capture_deformation_cursor"
    bl_label = "Capture Center from 3D Cursor"
    bl_description = "Capture the 3D Cursor for the active region and derive a radial surface direction"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            _registry, region, attached, _detached = _resolve_active_region(context)
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            center = attached.matrix_world.inverted() @ context.scene.cursor.location
            bounds_center = sum((Vector(corner) for corner in attached.bound_box), Vector((0.0, 0.0, 0.0))) / 8.0
            normal = center - bounds_center
            if normal.length_squared <= 1e-12:
                normal = Vector((0, 0, 1))
            center_world = attached.matrix_world @ center
            seed_index = min(
                range(len(attached.data.vertices)),
                key=lambda index: (attached.matrix_world @ attached.data.vertices[index].co - center_world).length_squared,
            )
            topology = _topology_fingerprint(attached)
            capture = {
                "placementMode": "CURSOR",
                "selectionKind": "VERTEX",
                "regionId": region.get("regionId"),
                "attachedObject": attached.name,
                "topologyFingerprint": topology,
                "faceIndices": [],
                "vertexIndices": [seed_index],
                "selectionHash": trauma_field.selection_hash([seed_index], topology, "VERTEX"),
                "centerLocal": list(center),
                "centerWorld": list(center_world),
                "normalLocal": list(normal.normalized()),
                "normalWorld": list(_normal_local_to_world(attached, normal.normalized())),
                "boundsWorld": [list(center_world), list(center_world)],
                "estimatedRadius": float(context.scene.daf_settings.deformation_seed_radius),
            }
            settings = context.scene.daf_settings
            _store_capture(context, capture)
            settings.deformation_status = "CURSOR CENTER CAPTURED"
            refresh_live_seed_preview(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_preview_deformation_seed(Operator):
    bl_idname = "daf.preview_deformation_seed"
    bl_label = "Preview Procedural Seed"
    bl_description = "Generate or refresh the temporary live seed key without editing the active deformation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            result = preview_seed(context)
            self.report({'INFO'}, f"Previewed the seed on {result['vertexCount']} head vertices.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_commit_deformation_seed(Operator):
    bl_idname = "daf.commit_deformation_seed"
    bl_label = "Commit Seed to Active Key"
    bl_description = "Copy the temporary seed into the active permanent paired deformation key"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            name = settings.deformation_active_key
            if not name:
                raise RuntimeError("Select or create a permanent deformation key first.")
            attached, detached = _resolve_pair()
            if _key(attached, PREVIEW_KEY_NAME) is None:
                preview_seed(context)
            preview = _key(attached, PREVIEW_KEY_NAME)
            target = _key(attached, name)
            if target is None:
                raise RuntimeError(f"The active deformation key {name} does not exist.")
            _set_key_coordinates(target, [point.co.copy() for point in preview.data])
            sync_key_to_detached(name)
            payload = _metadata(attached)
            entry = payload["keys"][name]
            entry.update({
                "status": "SEEDED",
                "recipeStatus": "LEGACY_SEEDED",
                "legacy": True,
                "seedRadius": float(settings.deformation_seed_radius),
                "seedDepth": float(settings.deformation_seed_depth),
                "seedFalloff": float(settings.deformation_seed_falloff),
                "seedDirectionMode": settings.deformation_seed_direction_mode,
                "seedCenter": [float(value) for value in settings.deformation_seed_center],
                "seedSurfaceNormal": [float(value) for value in settings.deformation_seed_surface_normal],
                "seamProtection": float(settings.deformation_seed_seam_protection),
                "maximumInfluence": float(settings.deformation_maximum_influence),
                "maximumDisplacement": float(settings.deformation_max_vertex_displacement),
            })
            _store_metadata(attached, detached, payload)
            clear_seed_preview()
            _zero_managed_weights(attached)
            target.value = min(1.0, target.slider_max)
            _set_authoring_view(attached, detached, 'ATTACHED')
            settings.deformation_status = f"PRESET COMMITTED — {name} / {_max_displacement(attached, name):.3f} m"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_clear_deformation_seed(Operator):
    bl_idname = "daf.clear_deformation_seed"
    bl_label = "Clear Uncommitted Seed"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clear_seed_preview()
        context.scene.daf_settings.deformation_status = "SEED PREVIEW CLEARED"
        return {'FINISHED'}


class DAF_OT_begin_deformation_sculpt(Operator):
    bl_idname = "daf.begin_deformation_sculpt"
    bl_label = "Begin Sculpt"
    bl_description = "Solo the active permanent key and enter Sculpt Mode on the active region's attached mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            name = settings.deformation_active_key
            attached, _detached = _resolve_pair()
            if name not in _managed_names(attached):
                raise RuntimeError("Select a managed deformation key first.")
            clear_seed_preview()
            _set_active_object(context, attached)
            keys = attached.data.shape_keys.key_blocks
            attached.active_shape_key_index = keys.find(name)
            for managed in _managed_names(attached):
                _key(attached, managed).value = 1.0 if managed == name else 0.0
            attached.show_only_shape_key = True
            bpy.ops.object.mode_set(mode='SCULPT')
            settings.deformation_status = f"SCULPTING — {name}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_finish_deformation_sculpt(Operator):
    bl_idname = "daf.finish_deformation_sculpt"
    bl_label = "Finish Sculpt & Sync"
    bl_description = "Leave Sculpt Mode, copy exact vertex-index world-space deltas to the active region's detached mesh, and validate limits"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            name = settings.deformation_active_key
            attached, detached = _resolve_pair()
            attached.show_only_shape_key = False
            sync_key_to_detached(name)
            payload = _metadata(attached)
            payload["keys"][name]["status"] = "SCULPTED"
            payload["keys"][name]["recipeStatus"] = "EXTERNALLY_SCULPTED"
            payload["keys"][name]["maximumInfluence"] = float(settings.deformation_maximum_influence)
            payload["keys"][name]["maximumDisplacement"] = float(settings.deformation_max_vertex_displacement)
            _store_metadata(attached, detached, payload)
            validation = validate_deformations(require_keys=True)
            settings.last_deformation_validation = validation["status"]
            if validation["status"] != "PASS":
                raise RuntimeError("; ".join(validation["errors"][:4]))
            settings.deformation_status = f"SCULPT SYNCED — {name}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_create_mirrored_deformation(Operator):
    bl_idname = "daf.create_mirrored_deformation"
    bl_label = "Create Mirrored Shape Key"
    bl_description = "Mirror the active deformation across local X using Blender topology mirror, then synchronize the active detached pair"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            source_name = settings.deformation_active_key
            attached, detached = _resolve_pair()
            source = _key(attached, source_name)
            if source is None or source_name not in _managed_names(attached):
                raise RuntimeError("Select a managed source deformation first.")
            source_entry = _metadata(attached)["keys"].get(source_name, {})
            target_name = source_entry.get("mirrorPartner") or (source_name + "_Mirrored")
            target_entry = dict(source_entry)
            target_entry["name"] = target_name
            target_entry["side"] = "right" if source_entry.get("side") == "left" else "left" if source_entry.get("side") == "right" else "mirrored"
            target_entry["mirrorPartner"] = source_name
            target_entry["stamps"] = []
            target_entry["recipeStatus"] = "LEGACY_MANUAL"
            target_entry["legacy"] = True
            _ensure_key_pair(target_name, target_entry)
            target = _key(attached, target_name)
            _set_key_coordinates(target, [point.co.copy() for point in source.data])
            _set_active_object(context, attached)
            attached.active_shape_key_index = attached.data.shape_keys.key_blocks.find(target_name)
            result = bpy.ops.object.shape_key_mirror(use_topology=True)
            if 'FINISHED' not in result:
                raise RuntimeError("Blender topology mirror did not finish.")
            sync_key_to_detached(target_name)
            payload = _metadata(attached)
            payload["keys"][target_name].update(target_entry)
            payload["keys"][target_name]["status"] = "MIRRORED"
            _store_metadata(attached, detached, payload)
            _select_key(settings, target_name)
            settings.deformation_status = f"MIRRORED — {source_name} → {target_name}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_build_active_preset(Operator):
    bl_idname = "daf.build_active_deformation_preset"
    bl_label = "Build Active Preset"
    bl_description = "Generate, commit, solo, and display a finished procedural starting deformation in one click"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            if not settings.deformation_active_key:
                raise RuntimeError("Select a managed deformation key first.")
            preview_seed(context)
            result = bpy.ops.daf.commit_deformation_seed()
            if 'FINISHED' not in result:
                raise RuntimeError("The procedural preset could not be committed.")
            settings.deformation_status = f"OUT-OF-BOX PRESET READY — {settings.deformation_active_key}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_show_deformation_attached(Operator):
    bl_idname = "daf.show_deformation_attached"
    bl_label = "Show Attached"
    bl_options = {'REGISTER'}

    def execute(self, context):
        attached, detached = _resolve_pair()
        _set_authoring_view(attached, detached, 'ATTACHED')
        _set_active_object(context, attached)
        context.scene.daf_settings.deformation_status = "VIEWING ATTACHED REGION"
        return {'FINISHED'}


class DAF_OT_show_deformation_detached(Operator):
    bl_idname = "daf.show_deformation_detached"
    bl_label = "Show Detached"
    bl_options = {'REGISTER'}

    def execute(self, context):
        attached, detached = _resolve_pair()
        _set_authoring_view(attached, detached, 'DETACHED')
        _set_active_object(context, detached)
        context.scene.daf_settings.deformation_status = "VIEWING DETACHED REGION"
        return {'FINISHED'}


class DAF_OT_show_deformation_overlay(Operator):
    bl_idname = "daf.show_deformation_overlay"
    bl_label = "Show Both"
    bl_options = {'REGISTER'}

    def execute(self, context):
        attached, detached = _resolve_pair()
        _set_authoring_view(attached, detached, 'BOTH')
        context.scene.daf_settings.deformation_status = "PAIR OVERLAY ENABLED"
        return {'FINISHED'}


class DAF_OT_validate_deformations(Operator):
    bl_idname = "daf.validate_deformations"
    bl_label = "Validate Deformations"
    bl_description = "Validate topology correspondence, paired deltas, finite coordinates, and displacement limits"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            validation = validate_deformations(require_keys=True)
            settings = context.scene.daf_settings
            settings.last_deformation_validation = validation["status"]
            settings.deformation_status = "VALIDATION " + validation["status"]
            if validation["status"] == "PASS":
                self.report({'INFO'}, f"Validated {validation['managedKeyCount']} paired deformation keys.")
                return {'FINISHED'}
            self.report({'ERROR'}, "; ".join(validation["errors"][:4]))
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def draw_panel(box, context, settings):
    regions = box.box()
    regions.label(text="1. Deformation Regions", icon='MESH_DATA')
    regions.prop(settings, "deformation_region")
    row = regions.row(align=True)
    row.operator("daf.select_deformation_region", text="Use Selected Region", icon='RESTRICT_SELECT_OFF')
    row.operator("daf.validate_deformation_region", text="Validate Pair", icon='CHECKMARK')
    regions.prop(settings, "deformation_region_id")
    regions.prop(settings, "deformation_related_seam_id")
    row = regions.row(align=True)
    row.operator("daf.register_deformation_region", text="Register Selected Pair", icon='ADD')
    row.operator("daf.remove_deformation_region", text="Remove Registration", icon='X')
    try:
        registry, region, attached, detached = _resolve_active_region(context)
        contract = validate_topology_pair(attached, detached)
        icon = 'CHECKMARK' if contract["status"] == "PASS" else 'ERROR'
        regions.label(text=f"{region['regionId']}: {attached.name} ↔ {detached.name}", icon=icon)
        regions.label(text=f"Topology: {contract['status']} — {contract['attachedVertexCount']} vertices / {contract['attachedPolygonCount']} polygons")
        regions.label(text="Status: " + region.get("validationStatus", "NOT VALIDATED"))
    except Exception as exc:
        regions.label(text=str(exc), icon='ERROR')
        regions.label(text="Select exactly two matching meshes to register a region", icon='INFO')
        return

    status = box.box()
    status.label(text="Status: " + settings.deformation_status, icon='INFO')
    status.label(text="Validation: " + settings.last_deformation_validation)

    library = box.box()
    library.label(text="2. Active Deformation", icon='SHAPEKEY_DATA')
    library.prop(settings, "deformation_key_name")
    row = library.row(align=True)
    row.operator("daf.create_damage_shape_key", text="Create Damage Shape Key", icon='ADD')
    row.operator("daf.create_standard_head_deformations", text="Create Standard Head Set", icon='PRESET')

    names = _managed_names(attached)
    if names:
        for name in names:
            key = _key(attached, name)
            row = library.row(align=True)
            select = row.operator("daf.select_deformation_key", text=name, depress=settings.deformation_active_key == name)
            select.key_name = name
            row.prop(key, "value", text="", slider=True)
            solo = row.operator("daf.solo_deformation_key", text="Solo")
            solo.key_name = name
    else:
        library.label(text="No managed deformation keys yet", icon='INFO')

    row = library.row(align=True)
    row.operator("daf.zero_deformations", text="Zero All", icon='LOOP_BACK')
    row.operator("daf.delete_managed_deformation", text="Delete Active", icon='TRASH')
    row.operator("daf.create_mirrored_deformation", text="Mirror Active", icon='MOD_MIRROR')

    capture_box = box.box()
    capture_box.label(text="3. Surface Capture", icon='FACESEL')
    capture_box.prop(settings, "deformation_capture_mode")
    capture_box.prop(settings, "deformation_influence_mode")
    capture_box.prop(settings, "deformation_distance_mode")
    if settings.deformation_influence_mode == 'PATCH_FEATHERED':
        capture_box.prop(settings, "deformation_feather_distance")
    if settings.deformation_capture_mode == 'SINGLE_FACE':
        capture_box.operator("daf.capture_deformation_selected_face", text="Capture Single Face", icon='FACESEL')
    elif settings.deformation_capture_mode == 'SELECTED_FACE_PATCH':
        capture_box.operator("daf.capture_deformation_selected_patch", text="Capture Connected Face Patch", icon='FACESEL')
    elif settings.deformation_capture_mode == 'SELECTED_VERTICES':
        capture_box.operator("daf.capture_deformation_selected_vertices", text="Capture Selected Vertices", icon='VERTEXSEL')
    else:
        capture_box.operator("daf.capture_deformation_cursor", text="Capture 3D Cursor", icon='PIVOT_CURSOR')
    if settings.deformation_seed_center_valid:
        capture = _capture_payload(settings)
        capture_box.label(text=f"Captured {len(capture.get('faceIndices', []))} faces / {len(capture.get('vertexIndices', []))} vertices", icon='CHECKMARK')
    else:
        capture_box.label(text="Capture a valid surface selection", icon='ERROR')

    stamps_box = box.box()
    stamps_box.label(text="4. Trauma Stamp Stack", icon='MOD_DISPLACE')
    payload = _metadata(attached)
    entry = payload.get("keys", {}).get(settings.deformation_active_key, {})
    stamps = sorted(entry.get("stamps", []), key=lambda stamp: int(stamp.get("orderIndex", 0)))
    for stamp in stamps:
        row = stamps_box.row(align=True)
        select = row.operator(
            "daf.select_trauma_stamp",
            text=f"{int(stamp.get('orderIndex', 0)) + 1}. {stamp.get('displayName', stamp.get('stampId'))}",
            depress=settings.deformation_active_stamp_id == stamp.get("stampId"),
            icon='CHECKBOX_HLT' if stamp.get("enabled", True) else 'CHECKBOX_DEHLT',
        )
        select.stamp_id = stamp.get("stampId", "")
    row = stamps_box.row(align=True)
    row.operator("daf.add_trauma_stamp", text="Add Stamp", icon='ADD')
    row.operator("daf.duplicate_trauma_stamp", text="Duplicate", icon='DUPLICATE')
    row.operator("daf.remove_trauma_stamp", text="Remove", icon='TRASH')
    row = stamps_box.row(align=True)
    row.operator("daf.move_trauma_stamp_up", text="Move Up", icon='TRIA_UP')
    row.operator("daf.move_trauma_stamp_down", text="Move Down", icon='TRIA_DOWN')
    row.operator("daf.toggle_trauma_stamp", text="Enable / Disable")
    stamps_box.prop(settings, "deformation_stamp_name")
    stamps_box.prop(settings, "deformation_stamp_family")
    stamps_box.prop(settings, "deformation_seed_radius")
    stamps_box.prop(settings, "deformation_seed_depth")
    stamps_box.prop(settings, "deformation_seed_falloff")
    stamps_box.prop(settings, "deformation_stamp_strength")
    stamps_box.prop(settings, "deformation_seed_direction_mode")
    if settings.deformation_seed_direction_mode == 'CUSTOM_VECTOR':
        stamps_box.prop(settings, "deformation_seed_custom_direction")
    stamps_box.prop(settings, "deformation_seed_seam_protection")
    stamps_box.prop(settings, "deformation_max_vertex_displacement")
    stamps_box.operator("daf.update_trauma_stamp", text="Update Active Stamp", icon='FILE_REFRESH')

    preview = box.box()
    preview.label(text="5. Preview and Rebuild", icon='HIDE_OFF')
    row = preview.row(align=True)
    row.operator("daf.show_deformation_attached", text="Attached", icon='OUTLINER_OB_MESH')
    row.operator("daf.show_deformation_detached", text="Detached", icon='PHYSICS')
    row.operator("daf.show_deformation_overlay", text="Both", icon='HIDE_OFF')
    row = preview.row(align=True)
    row.operator("daf.preview_active_trauma_stamp", text="Preview Active Stamp", icon='PLAY')
    row.operator("daf.clear_deformation_seed", text="Clear Temporary Preview", icon='X')
    preview.operator("daf.rebuild_active_deformation", text="REBUILD ACTIVE DEFORMATION", icon='FILE_REFRESH')
    preview.label(text="Rebuild always replays enabled stamps from Basis", icon='INFO')
    if not stamps:
        legacy = preview.box()
        legacy.label(text="Legacy v3.9.1 / Testman Preset", icon='RECOVER_LAST')
        legacy.operator("daf.build_active_deformation_preset", text="BUILD ACTIVE PRESET", icon='MOD_DISPLACE')
        row = legacy.row(align=True)
        row.operator("daf.preview_deformation_seed", text="Preview Legacy Seed", icon='HIDE_OFF')
        row.operator("daf.commit_deformation_seed", text="Commit Legacy Seed", icon='CHECKMARK')

    sculpt = box.box()
    sculpt.label(text="6. Sculpt and Sync", icon='SCULPTMODE_HLT')
    row = sculpt.row(align=True)
    row.operator("daf.begin_deformation_sculpt", text="Begin Sculpt", icon='SCULPTMODE_HLT')
    row.operator("daf.finish_deformation_sculpt", text="Finish Sculpt & Sync", icon='FILE_TICK')
    sculpt.label(text="Sculpting is optional; presets are now intended to read clearly out of the box", icon='INFO')

    validation_box = box.box()
    validation_box.label(text="7. Validation and Export", icon='CHECKMARK')
    validation_box.operator("daf.validate_deformations", text="Validate Morph Targets", icon='CHECKMARK')
    validation_box.label(text="Export remains in Damage Segment & Stump Authoring", icon='EXPORT')
    validation_box.label(text="Attached/detached deltas stay exact-index synchronized", icon='LINKED')
    validation_box.label(text="Source mesh and rig remain protected", icon='LOCKED')


CLASSES = (
    DAF_OT_register_deformation_region,
    DAF_OT_select_deformation_region,
    DAF_OT_validate_deformation_region,
    DAF_OT_remove_deformation_region,
    DAF_OT_create_damage_shape_key,
    DAF_OT_create_standard_head_deformations,
    DAF_OT_select_deformation_key,
    DAF_OT_solo_deformation_key,
    DAF_OT_zero_deformations,
    DAF_OT_delete_managed_deformation,
    DAF_OT_capture_deformation_selected_face,
    DAF_OT_capture_deformation_selected_patch,
    DAF_OT_capture_deformation_selected_vertices,
    DAF_OT_capture_deformation_cursor,
    DAF_OT_add_trauma_stamp,
    DAF_OT_select_trauma_stamp,
    DAF_OT_update_trauma_stamp,
    DAF_OT_duplicate_trauma_stamp,
    DAF_OT_remove_trauma_stamp,
    DAF_OT_move_trauma_stamp_up,
    DAF_OT_move_trauma_stamp_down,
    DAF_OT_toggle_trauma_stamp,
    DAF_OT_preview_active_trauma_stamp,
    DAF_OT_rebuild_active_deformation,
    DAF_OT_preview_deformation_seed,
    DAF_OT_commit_deformation_seed,
    DAF_OT_clear_deformation_seed,
    DAF_OT_begin_deformation_sculpt,
    DAF_OT_finish_deformation_sculpt,
    DAF_OT_create_mirrored_deformation,
    DAF_OT_build_active_preset,
    DAF_OT_show_deformation_attached,
    DAF_OT_show_deformation_detached,
    DAF_OT_show_deformation_overlay,
    DAF_OT_validate_deformations,
)
