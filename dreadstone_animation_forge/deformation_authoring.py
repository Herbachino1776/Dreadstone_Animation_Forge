"""Dreadstone Animation Forge v5.3.0 trauma-field authoring.

The workbench edits explicitly registered paired-segment or core-single regions
on the generated protected Damage Asset. Paired morph targets remain exact-index
synchronized; core meshes own one morph target. Imported source data is never edited.
"""

import bmesh
import bpy
import copy
import hashlib
import json
import math
import re
import secrets
from pathlib import Path
from mathutils import Vector
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import animation_library
from . import parameter_schema
from . import trauma_field
from .deformation import (
    blueprint_service,
    cavity_service,
    compound_service,
    diagnostics,
    gore_service,
    mesh_snapshot,
    preview_service,
    progressive_sites,
    registry as service_registry,
    serialization,
    shape_keys,
    transactions,
    validation_service,
)

DEFORMATION_SCHEMA = "dreadstone.damage_deformation.v1"
DEFORMATION_VERSION = (5, 3, 0)
DEFORMATION_BUILD_ID = "2026-08-11.character-variant-families.1"
IMPACT_CONTROL_SCHEMA = parameter_schema.IMPACT_CONTROL_SCHEMA
ATTACHED_HEAD_NAME = "DSB_ATTACHED_HEAD"
DETACHED_HEAD_NAME = "DSB_SEGMENT_HEAD"
PREVIEW_KEY_NAME = "__DSB_DEFORMATION_SEED_PREVIEW"
METADATA_PROPERTY = "dsb_deformation_manifest_json"
REGISTRY_PROPERTY = "dsb_deformation_region_registry_json"
GORE_PREVIEW_STATE_PROPERTY = "dsb_surface_gore_preview_json"
DAMAGE_PREVIEW_STATE_PROPERTY = "dsb_damage_preview_state_json"
GORE_PREVIEW_ATTRIBUTE = "DSB_Surface_Gore_Mask"
GORE_MATERIAL_PREFIX = "DSB_SURFACE_GORE_PREVIEW_"
GORE_OBJECT_ROLE = "raised_gore"
GORE_MESH_ID_PREFIX = "gore_mesh_"
SURFACE_STAIN_BINDING_SCHEMA = "dreadstone.surface_stain_binding.v1"
SURFACE_STAIN_OBJECT_ROLE = "surface_stain_export"
SURFACE_STAIN_MESH_ID_PREFIX = "stain_mesh_"
SURFACE_STAIN_COLOR_ATTRIBUTE = "DSB_Surface_Stain_RGBA"
GORE_TEXTURE_ATLAS_PATH = (
    Path(__file__).resolve().parent / "assets" / "gore_textures" / "muscle_fibers_macro_atlas.png"
)
GORE_TEXTURE_ATLAS_IMAGE = "DSB_Muscle_Fibers_Macro_Atlas"
PAIRED_SEGMENT = "PAIRED_SEGMENT"
CORE_SINGLE = "CORE_SINGLE"
COMPOUND_PREVIEW_PROPERTY = "dsb_compound_trauma_preview_json"
PAIR_TOLERANCE = 1e-6
SYNC_TOLERANCE = 1e-6
COMPOUND_SEAM_TOLERANCE = 0.0005
_GEODESIC_CACHE = service_registry.register_cache(
    "geodesicDistances", service_registry.BoundedCache(32, "geodesic_distances")
)
_GEODESIC_CACHE_CONTEXT = service_registry.register_cache(
    "geodesicContexts", service_registry.BoundedCache(32, "geodesic_contexts")
)
_ADJACENCY_CACHE = service_registry.register_cache(
    "weightedAdjacency", service_registry.BoundedCache(8, "weighted_adjacency")
)
_SEAM_FACTOR_CACHE = service_registry.register_cache(
    "seamFactors", service_registry.BoundedCache(16, "seam_factors")
)
_UNSET_REGION_OBJECT = object()
_PENDING_REGION_ID = ""
_IMPACT_TRANSACTION_DEPTH = 0
_GORE_TRANSACTION_DEPTH = 0
_PREVIEW_RESTORE_STATE = {}
_BLUEPRINT_LIBRARY_CACHE = {
    "path": "",
    "mtimeNs": -1,
    "library": blueprint_service.normalize_library(),
    "error": "",
}

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

BLUNT_GORE_HEAD_KEYS = {
    "Head_Impact_Left_v001": {
        "family": "broad_cave", "side": "left", "mirrorPartner": "Head_Impact_Right_v001",
        "seedRadius": 0.090, "seedDepth": 0.034, "seedFalloff": 1.45,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.060,
    },
    "Head_Impact_Right_v001": {
        "family": "broad_cave", "side": "right", "mirrorPartner": "Head_Impact_Left_v001",
        "seedRadius": 0.090, "seedDepth": 0.034, "seedFalloff": 1.45,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.060,
    },
    "Head_Impact_Front_v001": {
        "family": "broad_cave", "side": "front", "mirrorPartner": "",
        "seedRadius": 0.095, "seedDepth": 0.036, "seedFalloff": 1.40,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.062,
    },
    "Head_Impact_Back_v001": {
        "family": "broad_cave", "side": "back", "mirrorPartner": "",
        "seedRadius": 0.095, "seedDepth": 0.036, "seedFalloff": 1.40,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.062,
    },
}

BODY_IMPACT_STARTER_KEYS = {
    "Body_Impact_Front_v001": {"side": "front"},
    "Body_Impact_Left_v001": {"side": "left"},
    "Body_Impact_Right_v001": {"side": "right"},
    "Body_Impact_Back_v001": {"side": "back"},
}
for _body_template in BODY_IMPACT_STARTER_KEYS.values():
    _body_template.update({
        "family": "broad_cave", "mirrorPartner": "",
        "seedRadius": 0.115, "seedDepth": 0.032, "seedFalloff": 1.45,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.060,
    })

FOREARM_IMPACT_STARTER_KEYS = {
    "LEFT": "Forearm_L_Impact_Outer_v001",
    "RIGHT": "Forearm_R_Impact_Outer_v001",
}


def _version_string():
    return ".".join(str(value) for value in DEFORMATION_VERSION)


def _object(name):
    return bpy.data.objects.get(name)


def _topology_fingerprint(obj, force=False):
    return mesh_snapshot.topology_fingerprint(obj, force=force)


def _weight_fingerprint(obj, force=False):
    """Fingerprint source skin weights without changing Source Readiness rules."""

    return mesh_snapshot.weight_fingerprint(obj, force=force)


def _region_mode(region):
    mode = str(region.get("regionMode", PAIRED_SEGMENT))
    if mode not in trauma_field.REGION_MODES:
        raise RuntimeError(f"Registered deformation region has unsupported mode {mode!r}.")
    return mode


def validate_core_region(target=None):
    errors = []
    if target is None:
        errors.append("The registered core target mesh is missing.")
    elif target.type != 'MESH':
        errors.append(f"Registered core target {target.name} is not a mesh.")
    elif len(target.data.vertices) == 0 or len(target.data.polygons) == 0:
        errors.append("Registered core target mesh must contain vertices and polygons.")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "targetVertexCount": len(target.data.vertices) if target is not None and target.type == 'MESH' else 0,
        "targetPolygonCount": len(target.data.polygons) if target is not None and target.type == 'MESH' else 0,
        "topologyFingerprint": _topology_fingerprint(target, force=True) if target is not None and target.type == 'MESH' else "",
        "weightFingerprint": _weight_fingerprint(target, force=True) if target is not None and target.type == 'MESH' else "",
    }


def validate_region_contract(region, target=None, detached=None):
    mode = _region_mode(region)
    if mode == CORE_SINGLE:
        contract = validate_core_region(target)
        if detached is not None or str(region.get("detachedObject", "")):
            contract["errors"].append("Core single-mesh regions must not require a detached object.")
            contract["status"] = "FAIL"
        contract.update({
            "regionMode": CORE_SINGLE,
            "attachedVertexCount": contract["targetVertexCount"],
            "detachedVertexCount": 0,
            "attachedPolygonCount": contract["targetPolygonCount"],
            "detachedPolygonCount": 0,
        })
        return contract
    pair = validate_topology_pair(target, detached)
    pair["regionMode"] = PAIRED_SEGMENT
    pair["targetVertexCount"] = pair["attachedVertexCount"]
    pair["targetPolygonCount"] = pair["attachedPolygonCount"]
    pair["weightFingerprint"] = _weight_fingerprint(target, force=True) if target is not None and target.type == 'MESH' else ""
    return pair


def validate_topology_pair(attached=_UNSET_REGION_OBJECT, detached=_UNSET_REGION_OBJECT):
    if attached is _UNSET_REGION_OBJECT and detached is _UNSET_REGION_OBJECT:
        attached, detached = _resolve_pair()
    else:
        attached = None if attached is _UNSET_REGION_OBJECT else attached
        detached = None if detached is _UNSET_REGION_OBJECT else detached
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
    attached_fingerprint = _topology_fingerprint(attached, force=True)
    detached_fingerprint = _topology_fingerprint(detached, force=True)
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
        "activeCompoundEventId": "",
        "regions": [],
        "compoundEvents": [],
        "progressiveDamageSites": progressive_sites.normalize_sites(),
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


def _cache_registry_summary(payload):
    validation_service.store("region_registry", {
        "activeRegionId": str(payload.get("activeRegionId", "")),
        "activeCompoundEventId": str(payload.get("activeCompoundEventId", "")),
        "regions": [
            {
                "regionId": str(region.get("regionId", "")),
                "regionMode": str(region.get("regionMode", PAIRED_SEGMENT)),
                "targetObject": str(region.get("targetObject", region.get("attachedObject", ""))),
                "detachedObject": str(region.get("detachedObject", "")),
                "validationStatus": str(region.get("validationStatus", "NOT VALIDATED")),
                "vertexCount": int(region.get("attachedVertexCount", 0)),
                "polygonCount": int(region.get("polygonCount", 0)),
            }
            for region in payload.get("regions", [])
        ],
        "compoundEvents": [
            {
                "eventId": str(event.get("eventId", "")),
                "displayName": str(event.get("displayName", event.get("eventId", ""))),
                "participantCount": len(event.get("participants", [])),
                "validationStatus": str(event.get("validationStatus", "NOT VALIDATED")),
            }
            for event in payload.get("compoundEvents", [])
        ],
        "progressiveDamageSites": [
            {
                "siteId": str(site.get("siteId", "")),
                "siteGuid": str(site.get("siteGuid", "")),
                "displayName": str(site.get("displayName", "")),
                "regionId": str(site.get("regionId", "")),
                "status": str(site.get("status", "EMPTY")),
                "enabledForExport": bool(site.get("enabledForExport", False)),
                "assignedStageCount": sum(
                    bool(stage.get("damageKeyId"))
                    for stage in site.get("stages", {}).values()
                ),
            }
            for site in payload.get("progressiveDamageSites", {}).get("sites", [])
        ],
    })


def _store_registry(payload):
    payload["schema"] = DEFORMATION_SCHEMA
    payload["authoringVersion"] = _version_string()
    payload["authoringBuildId"] = DEFORMATION_BUILD_ID
    encoded = serialization.encode(payload)
    scene = getattr(bpy.context, "scene", None)
    if scene is not None and str(scene.get(REGISTRY_PROPERTY, "")) != encoded:
        scene[REGISTRY_PROPERTY] = encoded
    for region in payload.get("regions", []):
        for name in (region.get("targetObject", region.get("attachedObject")), region.get("detachedObject")):
            obj = _object(name) if name else None
            if obj is not None:
                if str(obj.get(REGISTRY_PROPERTY, "")) != encoded:
                    obj[REGISTRY_PROPERTY] = encoded
                region_id = region.get("regionId", "")
                if str(obj.get("dsb_deformation_region", "")) != region_id:
                    obj["dsb_deformation_region"] = region_id
    _cache_registry_summary(payload)


def _region_record(registry, region_id):
    return next((region for region in registry.get("regions", []) if region.get("regionId") == region_id), None)


def _record_from_pair(region_id, attached, detached, related_seam_id=""):
    contract = validate_topology_pair(attached, detached)
    return {
        "regionId": region_id,
        "regionMode": PAIRED_SEGMENT,
        "targetObject": attached.name,
        "attachedObject": attached.name,
        "detachedObject": detached.name,
        "topologyFingerprint": contract.get("topologyFingerprint", ""),
        "weightFingerprint": _weight_fingerprint(attached),
        "attachedVertexCount": contract.get("attachedVertexCount", 0),
        "detachedVertexCount": contract.get("detachedVertexCount", 0),
        "polygonCount": contract.get("attachedPolygonCount", 0),
        "relatedSeamId": related_seam_id,
        "managedKeys": [],
        "validationStatus": contract["status"],
    }


def _record_from_core(region_id, target, related_seam_id=""):
    contract = validate_core_region(target)
    return {
        "regionId": region_id,
        "regionMode": CORE_SINGLE,
        "targetObject": target.name,
        "attachedObject": target.name,
        "detachedObject": "",
        "topologyFingerprint": contract.get("topologyFingerprint", ""),
        "weightFingerprint": contract.get("weightFingerprint", ""),
        "attachedVertexCount": contract.get("targetVertexCount", 0),
        "detachedVertexCount": 0,
        "polygonCount": contract.get("targetPolygonCount", 0),
        "relatedSeamId": related_seam_id,
        "managedKeys": [],
        "validationStatus": contract["status"],
    }


def _load_registry(migrate_legacy=True):
    payload = _empty_registry()
    raw = _registry_raw()
    if raw:
        try:
            decoded = serialization.decode(raw)
            if isinstance(decoded, dict) and isinstance(decoded.get("regions", []), list):
                payload.update(decoded)
        except Exception:
            pass
    payload.setdefault("regions", [])
    payload.setdefault("compoundEvents", [])
    payload.setdefault("activeCompoundEventId", "")
    try:
        payload["progressiveDamageSites"] = progressive_sites.normalize_sites(
            payload.get("progressiveDamageSites")
        )
    except (TypeError, ValueError):
        payload["progressiveDamageSites"] = progressive_sites.normalize_sites()
    for region in payload["regions"]:
        region.setdefault("regionMode", PAIRED_SEGMENT)
        region.setdefault("targetObject", region.get("attachedObject", ""))
        region.setdefault("attachedObject", region.get("targetObject", ""))
        region.setdefault("detachedObject", "")
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
                repair_legacy_pair_sync(
                    region_id="head",
                    candidate_names=existing,
                    automatic=True,
                )
                payload = _load_registry(migrate_legacy=False)
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
    previous_region_id = registry.get("activeRegionId", "")
    if previous_region_id and previous_region_id != region_id:
        previous_region = _region_record(registry, previous_region_id)
        if previous_region is not None:
            try:
                previous_attached, previous_detached = _resolve_region_pair(previous_region)
                _clear_gore_preview_pair(previous_attached, previous_detached)
            except Exception:
                pass
    registry["activeRegionId"] = region_id
    _store_registry(registry)
    scene = getattr(context, "scene", None) if context is not None else getattr(bpy.context, "scene", None)
    settings = getattr(scene, "daf_settings", None)
    if settings is not None and settings.deformation_region != region_id:
        auto_preview = settings.deformation_auto_preview
        settings.deformation_auto_preview = False
        try:
            settings.deformation_region = region_id
        finally:
            settings.deformation_auto_preview = auto_preview
    _invalidate_geodesic_cache()


def _resolve_region_pair(region):
    target_name = region.get("targetObject", region.get("attachedObject", ""))
    attached = _object(target_name)
    detached = _object(region.get("detachedObject", "")) if region.get("detachedObject") else None
    if attached is None:
        raise RuntimeError(f"Registered target object {target_name} is missing.")
    if attached.type != 'MESH':
        raise RuntimeError(f"Registered target object {target_name} is not a mesh.")
    if _region_mode(region) == CORE_SINGLE:
        if region.get("detachedObject"):
            raise RuntimeError("Core single-mesh region accidentally stores a detached-object requirement.")
        return attached, None
    if detached is None:
        raise RuntimeError(f"Registered detached object {region.get('detachedObject', '')} is missing.")
    if detached.type != 'MESH':
        raise RuntimeError("Both registered paired-region objects must be meshes.")
    return attached, detached


def _resolve_active_region(context=None, region_id=None):
    registry = _load_registry()
    resolved_id = region_id or _active_region_id(context)
    region = _region_record(registry, resolved_id)
    if region is None:
        raise RuntimeError("Register a paired-segment or core single-mesh deformation region first.")
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
        description = (
            f"Core single mesh: {region.get('targetObject', '')}"
            if _region_mode(region) == CORE_SINGLE
            else f"Paired: {region.get('attachedObject', '')} / {region.get('detachedObject', '')}"
        )
        items.append((region_id, label, description, index))
    return items or [("NONE", "No Regions", "Register a paired segment or core mesh", 0)]


def register_standard_generated_regions(context=None):
    """Register existing generated standard objects without guessing replacements."""

    context = context or bpy.context
    registry = _load_registry()
    specs = (
        ("head", PAIRED_SEGMENT, "DSB_ATTACHED_HEAD", "DSB_SEGMENT_HEAD", "head_neck"),
        ("body_core", CORE_SINGLE, "DSB_BODY_CORE", "", "lower_spine"),
        ("forearm_left", PAIRED_SEGMENT, "DSB_ATTACHED_FOREARM_L", "DSB_SEGMENT_FOREARM_L", "left_elbow"),
        ("forearm_right", PAIRED_SEGMENT, "DSB_ATTACHED_FOREARM_R", "DSB_SEGMENT_FOREARM_R", "right_elbow"),
    )
    registered = []
    existing = []
    skipped = []
    used_names = {
        name for record in registry.get("regions", [])
        for name in (record.get("targetObject", record.get("attachedObject", "")), record.get("detachedObject", ""))
        if name
    }
    for region_id, mode, target_name, detached_name, seam_id in specs:
        prior = _region_record(registry, region_id)
        if prior is not None:
            target, detached = _resolve_region_pair(prior)
            _ensure_basis(target)
            if detached is not None:
                _ensure_basis(detached)
            contract = validate_region_contract(prior, target, detached)
            if contract["status"] != "PASS":
                raise RuntimeError(f"Existing standard region {region_id!r} is invalid: {' '.join(contract['errors'])}")
            prior["validationStatus"] = "PASS"
            existing.append(region_id)
            continue
        target = _object(target_name)
        detached = _object(detached_name) if detached_name else None
        if target is None or (mode == PAIRED_SEGMENT and detached is None):
            skipped.append({"regionId": region_id, "reason": "generated object not present"})
            continue
        _ensure_basis(target)
        if detached is not None:
            _ensure_basis(detached)
        assigned = {target_name, detached_name} - {""}
        if assigned.intersection(used_names):
            raise RuntimeError(f"A standard {region_id!r} object is already owned by another registered region.")
        if mode == CORE_SINGLE:
            contract = validate_core_region(target)
            record = _record_from_core(region_id, target, seam_id)
        else:
            contract = validate_topology_pair(target, detached)
            record = _record_from_pair(region_id, target, detached, seam_id)
        if contract["status"] != "PASS":
            raise RuntimeError(f"Generated standard region {region_id!r} is invalid: {' '.join(contract['errors'])}")
        record["validationStatus"] = "PASS"
        registry.setdefault("regions", []).append(record)
        used_names.update(assigned)
        registered.append(region_id)
    if not registry.get("activeRegionId") and registry.get("regions"):
        registry["activeRegionId"] = "head" if _region_record(registry, "head") else registry["regions"][0]["regionId"]
    _store_registry(registry)
    active_id = registry.get("activeRegionId", "")
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is not None and active_id and settings.deformation_region != active_id:
        auto = settings.deformation_auto_preview
        settings.deformation_auto_preview = False
        try:
            settings.deformation_region = active_id
        finally:
            settings.deformation_auto_preview = auto
    _invalidate_geodesic_cache()
    return {"registered": registered, "existing": existing, "skipped": skipped}


def _invalidate_geodesic_cache():
    _GEODESIC_CACHE.clear()
    _GEODESIC_CACHE_CONTEXT.clear()
    _ADJACENCY_CACHE.clear()
    _SEAM_FACTOR_CACHE.clear()
    mesh_snapshot.clear_cache("authoring invalidation")
    gore_service.clear_cache("authoring invalidation")
    validation_service.clear_cache("authoring invalidation")
    _refresh_authoring_ui_cache_safely()


def cached_diagnostics_summary():
    """Return the last explicitly refreshed diagnostics snapshot for UI draw."""

    return diagnostics.cached_summary()


def _metadata(obj):
    raw = obj.get(METADATA_PROPERTY, "") or obj.data.get(METADATA_PROPERTY, "")
    if raw:
        try:
            payload = serialization.decode(raw)
            if isinstance(payload, dict):
                payload["schema"] = DEFORMATION_SCHEMA
                payload["authoringVersion"] = _version_string()
                payload["authoringBuildId"] = DEFORMATION_BUILD_ID
                for key_name, entry in payload.get("keys", {}).items():
                    entry.setdefault("stamps", [])
                    entry.setdefault("previewEnabled", False)
                    entry.setdefault("activeStampId", "")
                    entry.setdefault("stampMode", "STACK")
                    if not entry["stamps"]:
                        entry.setdefault("recipeStatus", "LEGACY_MANUAL")
                        entry.setdefault("legacy", True)
                    elif not entry["activeStampId"]:
                        entry["activeStampId"] = str(
                            sorted(
                                entry["stamps"],
                                key=lambda stamp: int(stamp.get("orderIndex", 0)),
                            )[0].get("stampId", "")
                        )
                    if not str(entry.get("damageKeyId", "")).strip():
                        entry["damageKeyId"] = progressive_sites.opaque_id(
                            "damage_key",
                            progressive_sites.canonical_digest(
                                [
                                    str(payload.get("regionId", payload.get("region", ""))),
                                    str(obj.name),
                                    str(key_name),
                                ]
                            )[:32],
                        )
                return payload
        except Exception:
            pass
    registry = _load_registry()
    region = next((record for record in registry.get("regions", []) if obj.name in {
        record.get("targetObject", record.get("attachedObject")), record.get("detachedObject")
    }), None)
    region_id = region.get("regionId", "head") if region else "head"
    attached_name = region.get("targetObject", region.get("attachedObject", ATTACHED_HEAD_NAME)) if region else ATTACHED_HEAD_NAME
    detached_name = region.get("detachedObject", DETACHED_HEAD_NAME) if region else DETACHED_HEAD_NAME
    payload = {
        "schema": DEFORMATION_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": DEFORMATION_BUILD_ID,
        "region": region_id,
        "regionId": region_id,
        "regionMode": _region_mode(region) if region else PAIRED_SEGMENT,
        "targetObject": attached_name,
        "attachedObject": attached_name,
        "detachedObject": detached_name,
        "keys": {},
    }
    # Clean GLB reimports retain morph names even when a host strips extras.
    # Recover only the exact standard Forge names; never adopt arbitrary keys.
    other_name = detached_name if obj.name == attached_name else attached_name
    other = _object(other_name)
    if region_id == "head" and detached_name:
        for name, template in STANDARD_HEAD_KEYS.items():
            if _key(obj, name) is not None and other is not None and _key(other, name) is not None:
                payload["keys"][name] = {
                    "name": name,
                    "damageKeyId": progressive_sites.opaque_id(
                        "damage_key",
                        progressive_sites.canonical_digest(
                            [region_id, str(obj.name), str(name)]
                        )[:32],
                    ),
                    "region": "head",
                    "regionId": "head",
                    "status": "REIMPORTED",
                    "recipeStatus": "LEGACY_MANUAL",
                    "legacy": True,
                    "stamps": [],
                    **template,
                }
    return payload


def _cache_metadata_summary(attached, detached, payload, region_id):
    validation_service.store("active_metadata", {
        "regionId": str(region_id),
        "regionMode": str(payload.get("regionMode", PAIRED_SEGMENT)),
        "targetObject": attached.name,
        "detachedObject": detached.name if detached is not None else "",
        "keys": [
            {
                "name": str(name),
                "damageKeyId": str(entry.get("damageKeyId", "")),
                "status": str(entry.get("status", "")),
                "recipeStatus": str(entry.get("recipeStatus", "")),
                "stampCount": len(entry.get("stamps", [])),
                "previewEnabled": bool(entry.get("previewEnabled", False)),
                "activeStampId": str(entry.get("activeStampId", "")),
                "stampMode": str(entry.get("stampMode", "STACK")),
                "stamps": [
                    {
                        "stampId": str(stamp.get("stampId", "")),
                        "displayName": str(stamp.get("displayName", stamp.get("stampId", ""))),
                        "enabled": bool(stamp.get("enabled", True)),
                        "orderIndex": int(stamp.get("orderIndex", 0)),
                    }
                    for stamp in entry.get("stamps", [])
                ],
                "goreStatus": str(entry.get("raisedGoreStatus", "NOT GENERATED")),
                "goreTriangles": sum(int(value) for value in entry.get("goreTriangleCounts", {}).values()),
                "validationStatus": str(entry.get("validationStatus", "NOT VALIDATED")),
            }
            for name, entry in payload.get("keys", {}).items()
        ],
    })


def _refresh_authoring_ui_cache(region_id=""):
    """Rebuild panel summaries from persisted state after a rollback."""

    registry = _load_registry(migrate_legacy=False)
    _cache_registry_summary(registry)
    selected_region_id = str(
        region_id or registry.get("activeRegionId", "")
    )
    region = _region_record(registry, selected_region_id)
    if region is None:
        return
    attached, detached = _resolve_region_pair(region)
    _cache_metadata_summary(
        attached,
        detached,
        _metadata(attached),
        selected_region_id,
    )


def _refresh_authoring_ui_cache_safely(region_id=""):
    """Keep lightweight panel state available after unrelated cache clears."""

    try:
        _refresh_authoring_ui_cache(region_id)
    except Exception:
        # Explicit validation reports invalid or missing regions. Routine cache
        # invalidation must not break otherwise recoverable authoring actions.
        pass


def _store_metadata(attached, detached, payload):
    registry = _load_registry()
    region = next((
        record for record in registry.get("regions", [])
        if record.get("targetObject", record.get("attachedObject")) == attached.name
        and (
            _region_mode(record) == CORE_SINGLE
            or record.get("detachedObject") == getattr(detached, "name", None)
        )
    ), None)
    region_id = region.get("regionId", payload.get("regionId", payload.get("region", ""))) if region else payload.get("regionId", payload.get("region", ""))
    payload["schema"] = DEFORMATION_SCHEMA
    payload["authoringVersion"] = _version_string()
    payload["authoringBuildId"] = DEFORMATION_BUILD_ID
    payload["region"] = region_id
    payload["regionId"] = region_id
    payload["regionMode"] = _region_mode(region) if region else payload.get("regionMode", PAIRED_SEGMENT)
    payload["targetObject"] = attached.name
    payload["attachedObject"] = attached.name
    payload["detachedObject"] = detached.name if detached is not None else ""
    encoded = serialization.encode(payload)
    if str(attached.data.get(METADATA_PROPERTY, "")) != encoded:
        attached.data[METADATA_PROPERTY] = encoded
    if str(attached.get(METADATA_PROPERTY, "")) != encoded:
        attached[METADATA_PROPERTY] = encoded
    if str(attached.get("dsb_deformation_region", "")) != region_id:
        attached["dsb_deformation_region"] = region_id
    if detached is not None:
        if str(detached.data.get(METADATA_PROPERTY, "")) != encoded:
            detached.data[METADATA_PROPERTY] = encoded
        if str(detached.get(METADATA_PROPERTY, "")) != encoded:
            detached[METADATA_PROPERTY] = encoded
        if str(detached.get("dsb_deformation_region", "")) != region_id:
            detached["dsb_deformation_region"] = region_id
    if region is not None:
        region["managedKeys"] = sorted(payload.get("keys", {}).keys())
        region["topologyFingerprint"] = _topology_fingerprint(attached)
        region["weightFingerprint"] = _weight_fingerprint(attached)
        region["attachedVertexCount"] = len(attached.data.vertices)
        region["detachedVertexCount"] = len(detached.data.vertices) if detached is not None else 0
        region["polygonCount"] = len(attached.data.polygons)
        _store_registry(registry)
    _cache_metadata_summary(attached, detached, payload, region_id)


def cached_ui_summary(settings=None):
    registry = validation_service.get("region_registry", {}) or {}
    metadata = validation_service.get("active_metadata", {}) or {}
    active_region_id = str(registry.get("activeRegionId", metadata.get("regionId", "")))
    region = next((item for item in registry.get("regions", []) if item.get("regionId") == active_region_id), {})
    active_key = str(getattr(settings, "deformation_active_key", "")) if settings is not None else ""
    key = next((item for item in metadata.get("keys", []) if item.get("name") == active_key), {})
    active_stamp_id = str(getattr(settings, "deformation_active_stamp_id", "")) if settings is not None else ""
    stamp = next((item for item in key.get("stamps", []) if item.get("stampId") == active_stamp_id), {})
    return {
        "registry": registry,
        "metadata": metadata,
        "region": region,
        "key": key,
        "stamp": stamp,
        "preview": preview_service.state(),
        "blueprints": cached_blueprint_library_summary(),
    }


def _blueprint_library_path(settings):
    raw = str(getattr(settings, "deformation_blueprint_library_path", "") or "").strip()
    if not raw:
        raw = "//dreadstone_damage_blueprints.json"
    resolved = Path(bpy.path.abspath(raw))
    if resolved.suffix.lower() != ".json":
        resolved = Path(str(resolved) + ".json")
    return resolved


def _cache_blueprint_library(path, library=None, error=""):
    global _BLUEPRINT_LIBRARY_CACHE
    resolved = Path(path)
    try:
        mtime_ns = resolved.stat().st_mtime_ns if resolved.exists() else -1
    except OSError:
        mtime_ns = -1
    _BLUEPRINT_LIBRARY_CACHE = {
        "path": str(resolved),
        "mtimeNs": int(mtime_ns),
        "library": blueprint_service.normalize_library(library),
        "error": str(error),
    }
    return _BLUEPRINT_LIBRARY_CACHE["library"]


def refresh_blueprint_library(context=None):
    """Read the portable recipe library explicitly; panel draws stay disk-free."""

    context = context or bpy.context
    settings = context.scene.daf_settings
    path = _blueprint_library_path(settings)
    if not path.exists():
        return _cache_blueprint_library(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        library = blueprint_service.normalize_library(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        _cache_blueprint_library(path, error=str(exc))
        raise RuntimeError(f"Could not read Damage Blueprint library: {exc}") from exc
    return _cache_blueprint_library(path, library)


def cached_blueprint_library_summary():
    library = _BLUEPRINT_LIBRARY_CACHE.get("library", {}) or {}
    return {
        "path": str(_BLUEPRINT_LIBRARY_CACHE.get("path", "")),
        "error": str(_BLUEPRINT_LIBRARY_CACHE.get("error", "")),
        "count": int(library.get("blueprintCount", 0)),
        "entries": [
            {
                "blueprintId": str(record.get("blueprintId", "")),
                "name": str(record.get("name", "")),
                "digest": str(record.get("blueprintDigest", "")),
            }
            for record in library.get("blueprints", [])
        ],
    }


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
    from . import variant_authoring

    return variant_authoring.effective_damage_key_names(
        str(metadata.get("regionId", metadata.get("region", ""))),
        names,
    )


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
    _registry, region, attached, detached = _resolve_active_region()
    if preview:
        if str(region.get("validationStatus", "")) != "PASS":
            raise RuntimeError("Validate the active deformation region before previewing it.")
        if detached is not None and len(attached.data.vertices) != len(detached.data.vertices):
            raise RuntimeError("The registered pair no longer has exact-index compatible point counts.")
    else:
        contract = validate_region_contract(region, attached, detached)
        if contract["status"] != "PASS":
            raise RuntimeError(" ".join(contract["errors"]))
    _ensure_basis(attached)
    if detached is not None:
        _ensure_basis(detached)
    payload = _metadata(attached)
    attached_key = _key(attached, name)
    detached_key = _key(detached, name) if detached is not None else None
    if not preview and name not in payload.get("keys", {}) and (attached_key is not None or detached_key is not None):
        raise RuntimeError(f"A non-Forge shape key named {name} already exists; choose another name.")
    created_attached = attached_key is None
    created_detached = detached is not None and detached_key is None
    attached_key = attached_key or attached.shape_key_add(name=name, from_mix=False)
    if detached is not None:
        detached_key = detached_key or detached.shape_key_add(name=name, from_mix=False)
    attached_key.slider_min = 0.0
    if detached_key is not None:
        detached_key.slider_min = 0.0
    maximum = float((metadata_entry or {}).get("maximumInfluence", 1.0))
    attached_key.slider_max = maximum
    if detached_key is not None:
        detached_key.slider_max = maximum
    if created_attached or created_detached:
        attached_key.value = 0.0
        if detached_key is not None:
            detached_key.value = 0.0
            _link_detached_value(attached, detached, name)
    if not preview:
        region_id = region.get("regionId", "")
        entry = {
            "name": name,
            "region": region_id,
            "regionId": region_id,
            "regionMode": _region_mode(region),
            "targetObject": attached.name,
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
        if "surfaceGoreOverlay" in (metadata_entry or {}):
            entry["surfaceGoreOverlay"] = copy.deepcopy(metadata_entry["surfaceGoreOverlay"])
            entry["goreOverlayDigest"] = (metadata_entry or {}).get("goreOverlayDigest")
        payload.setdefault("keys", {})[name] = {**payload.get("keys", {}).get(name, {}), **entry}
        _store_metadata(attached, detached, payload)
    return attached, detached, attached_key, detached_key


def _rename_shape_key_data_paths(key_data_blocks, old_name, new_name):
    """Retarget animation paths owned by the renamed shape-key datablocks."""

    old_token = f'key_blocks["{_escape_data_path(old_name)}"]'
    new_token = f'key_blocks["{_escape_data_path(new_name)}"]'
    actions = set()
    for key_data in tuple(value for value in key_data_blocks if value is not None):
        animation_data = getattr(key_data, "animation_data", None)
        if animation_data is None:
            continue
        if animation_data.action is not None:
            actions.add(animation_data.action)
        for track in animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action is not None:
                    actions.add(strip.action)
        for curve in animation_data.drivers:
            if old_token in str(curve.data_path):
                curve.data_path = str(curve.data_path).replace(
                    old_token,
                    new_token,
                )
            driver = getattr(curve, "driver", None)
            if driver is None:
                continue
            for variable in driver.variables:
                for target in variable.targets:
                    path = str(getattr(target, "data_path", ""))
                    if old_token in path:
                        target.data_path = path.replace(old_token, new_token)
    for action in actions:
        for curve in animation_library.iter_action_fcurves(action):
            if old_token in str(curve.data_path):
                curve.data_path = str(curve.data_path).replace(
                    old_token,
                    new_token,
                )


def rename_deformation_key(context=None, old_name=None, new_name=None):
    """Rename one managed Damage Key without breaking its stable ownership graph."""

    context = context or bpy.context
    settings = context.scene.daf_settings
    registry, region, attached, detached = _resolve_active_region(context)
    old_name = str(old_name or settings.deformation_active_key).strip()
    new_name = str(new_name or settings.deformation_key_name).strip()
    if not old_name:
        raise RuntimeError("Select a managed Damage Key to rename.")
    if (
        not new_name
        or new_name in {"Basis", PREVIEW_KEY_NAME}
        or len(new_name) > 63
        or re.fullmatch(r"[A-Za-z0-9_]+", new_name) is None
    ):
        raise RuntimeError(
            "Damage Key names must contain only letters, numbers, and "
            "underscores and be at most 63 characters."
        )
    if old_name == new_name:
        return {
            "oldName": old_name,
            "newName": new_name,
            "changed": False,
        }

    payload = _metadata(attached)
    entry = payload.get("keys", {}).get(old_name)
    attached_key = _key(attached, old_name)
    detached_key = _key(detached, old_name) if detached is not None else None
    if not isinstance(entry, dict) or attached_key is None:
        raise RuntimeError(
            f"Managed Damage Key {old_name!r} is incomplete or missing."
        )
    if detached is not None and detached_key is None:
        raise RuntimeError(
            f"Detached ownership is missing Damage Key {old_name!r}."
        )
    if (
        new_name in payload.get("keys", {})
        or _key(attached, new_name) is not None
        or (detached is not None and _key(detached, new_name) is not None)
    ):
        raise RuntimeError(
            f"Damage Key {new_name!r} already exists in this region."
        )

    region_id = str(region.get("regionId", ""))
    key_id = str(entry.get("damageKeyId", "")).strip()
    if not key_id:
        key_id = progressive_sites.opaque_id("damage_key")
        entry["damageKeyId"] = key_id
    registry_before = copy.deepcopy(registry)
    payload_before = copy.deepcopy(payload)
    key_data_blocks = (
        attached.data.shape_keys,
        detached.data.shape_keys if detached is not None else None,
    )
    old_gore = list(generated_gore_objects(region_id, old_name))
    new_gore = []

    clear_damage_preview(context)
    try:
        attached_key.name = new_name
        if detached_key is not None:
            detached_key.name = new_name
        _rename_shape_key_data_paths(
            key_data_blocks,
            old_name,
            new_name,
        )

        renamed_entry = payload["keys"].pop(old_name)
        renamed_entry["name"] = new_name
        renamed_entry["damageKeyId"] = key_id
        if str(renamed_entry.get("mirrorPartner", "")) == old_name:
            renamed_entry["mirrorPartner"] = new_name
        for other_entry in payload.get("keys", {}).values():
            if str(other_entry.get("mirrorPartner", "")) == old_name:
                other_entry["mirrorPartner"] = new_name
        payload["keys"][new_name] = renamed_entry

        if old_gore:
            _clear_generated_entry_fields(renamed_entry)
            new_gore = rebuild_raised_gore_for_key(
                region,
                attached,
                detached,
                new_name,
                renamed_entry,
            )
        else:
            _clear_generated_entry_fields(renamed_entry)

        from . import progressive_authoring

        renamed_stage_count = 0
        sites = registry.get("progressiveDamageSites", {}).get("sites", [])
        for site in sites:
            site_changed = False
            for stage in site.get("stages", {}).values():
                is_stable_match = (
                    key_id
                    and str(stage.get("damageKeyId", "")) == key_id
                )
                is_legacy_match = (
                    str(stage.get("regionId", "")) == region_id
                    and str(stage.get("deformationKeyName", "")) == old_name
                )
                if not (is_stable_match or is_legacy_match):
                    continue
                stage["damageKeyId"] = key_id
                stage["deformationKeyName"] = new_name
                stage["deformationDigest"] = (
                    progressive_authoring._deformation_digest(
                        attached,
                        new_name,
                    )
                )
                stage.update(
                    progressive_authoring._generated_mapping(
                        region_id,
                        new_name,
                    )
                )
                stage["validationStatus"] = "NOT_VALIDATED"
                stage["measurements"] = {}
                renamed_stage_count += 1
                site_changed = True
            if site_changed:
                site["validationStatus"] = "NOT_VALIDATED"
                site["validationDigest"] = ""
                site["validationReport"] = {}
                site["enabledForExport"] = False

        renamed_compound_count = 0
        for event in registry.get("compoundEvents", []):
            event_changed = False
            for participant in event.get("participants", []):
                if (
                    str(participant.get("regionId", "")) == region_id
                    and str(participant.get("childKeyName", "")) == old_name
                ):
                    participant["childKeyName"] = new_name
                    renamed_compound_count += 1
                    event_changed = True
            if event_changed:
                event["validationStatus"] = "NOT_VALIDATED"
                event["validationReport"] = {}

        _store_registry(registry)
        _store_metadata(attached, detached, payload)
        if detached is not None:
            _link_detached_value(attached, detached, new_name)
        _remove_generated_gore_objects(region_id, old_name)
    except Exception:
        _remove_generated_gore_objects(region_id, new_name)
        current_attached_key = _key(attached, new_name)
        if current_attached_key is not None:
            current_attached_key.name = old_name
        current_detached_key = (
            _key(detached, new_name) if detached is not None else None
        )
        if current_detached_key is not None:
            current_detached_key.name = old_name
        _rename_shape_key_data_paths(
            key_data_blocks,
            new_name,
            old_name,
        )
        _store_registry(registry_before)
        _store_metadata(attached, detached, payload_before)
        if detached is not None:
            _link_detached_value(attached, detached, old_name)
        raise

    with preview_service.suspend_updates():
        settings.deformation_active_key = new_name
        if str(settings.deformation_key_name) == old_name:
            settings.deformation_key_name = new_name
    preview_restore_error = ""
    try:
        apply_damage_key_previews(context)
    except Exception as exc:
        preview_restore_error = str(exc)
    settings.deformation_status = f"DAMAGE KEY RENAMED - {old_name} -> {new_name}"
    if preview_restore_error:
        settings.deformation_status += " - PREVIEW REFRESH NEEDED"
    if renamed_stage_count:
        settings.progression_status = (
            "DAMAGE KEY RENAMED - VALIDATE + ENABLE SITE FOR EXPORT"
        )
    _invalidate_geodesic_cache()
    return {
        "oldName": old_name,
        "newName": new_name,
        "damageKeyId": key_id,
        "regionId": region_id,
        "renamedStageCount": renamed_stage_count,
        "renamedCompoundParticipantCount": renamed_compound_count,
        "rebuiltGoreNodeNames": [obj.name for obj in new_gore],
        "previewRestoreError": preview_restore_error,
        "changed": True,
    }


def _remove_key(obj, name):
    if obj is None:
        return
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
        if detached is not None:
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


def _evaluated_world_matrix(obj):
    """Return a correct matrix for a hidden object after file reopen.

    Blender may defer dependency-graph evaluation for disabled viewport objects
    and temporarily expose an identity ``matrix_world``. Explicit Forge work
    briefly evaluates the object and its parents, then restores exact visibility.
    """

    hierarchy = []
    current = obj
    while current is not None:
        hierarchy.append(current)
        current = current.parent
    visibility = [(item, bool(item.hide_viewport), bool(item.hide_get())) for item in hierarchy]
    if not any(viewport or hidden for _item, viewport, hidden in visibility):
        return obj.matrix_world.copy()
    try:
        for item, _viewport, _hidden in visibility:
            item.hide_viewport = False
            item.hide_set(False)
        bpy.context.view_layer.update()
        return obj.matrix_world.copy()
    finally:
        for item, viewport, hidden in reversed(visibility):
            item.hide_viewport = viewport
            item.hide_set(hidden)
        bpy.context.view_layer.update()


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


def _is_dsb_authoring_collection(collection):
    return bool(collection.get("dsb_damage_generated_collection", False)) or collection.name.startswith("DSB_")


def _collection_paths(root, target):
    paths = []

    def visit(collection, path):
        current = path + [collection]
        if collection == target:
            paths.append(current)
        for child in collection.children:
            visit(child, current)

    visit(root, [])
    return paths


def _layer_collection_paths(root, target):
    paths = []

    def visit(layer_collection, path):
        current = path + [layer_collection]
        if layer_collection.collection == target:
            paths.append(current)
        for child in layer_collection.children:
            visit(child, current)

    visit(root, [])
    return paths


def _visibility_blocker(context, obj):
    if obj.hide_viewport:
        return f"Object {obj.name} is blocked by object.hide_viewport."
    try:
        if obj.hide_get(view_layer=context.view_layer):
            return f"Object {obj.name} is blocked by its current-view-layer hide state."
    except TypeError:
        if obj.hide_get():
            return f"Object {obj.name} is blocked by its viewport hide state."
    reasons = []
    for collection in obj.users_collection:
        if collection.hide_viewport:
            reasons.append(f"collection {collection.name} has hide_viewport enabled")
        layer_paths = _layer_collection_paths(context.view_layer.layer_collection, collection)
        if not layer_paths:
            reasons.append(f"collection {collection.name} is absent from view layer {context.view_layer.name}")
        for path in layer_paths:
            for layer_collection in path:
                if layer_collection.exclude:
                    reasons.append(f"layer collection {layer_collection.name} is excluded")
                if layer_collection.hide_viewport:
                    reasons.append(f"layer collection {layer_collection.name} has viewport hiding enabled")
    if reasons:
        return f"Object {obj.name} remains blocked: " + "; ".join(dict.fromkeys(reasons)) + "."
    return f"Object {obj.name} remains blocked by the current viewport or local-view state."


def _object_visible_in_view_layer(obj, view_layer):
    try:
        return bool(obj.visible_get(view_layer=view_layer))
    except TypeError:
        return bool(obj.visible_get())


def _damage_preview_state(context=None):
    scene = getattr(context, "scene", None) if context is not None else getattr(bpy.context, "scene", None)
    raw = scene.get(DAMAGE_PREVIEW_STATE_PROPERTY, "") if scene is not None else ""
    if not raw:
        return {"kind": "NONE", "entries": []}
    try:
        state = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"kind": "BROKEN", "entries": []}
    return state if isinstance(state, dict) else {"kind": "BROKEN", "entries": []}


def _store_damage_preview_state(context, state):
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    entries = list(state.get("entries", [])) if isinstance(state, dict) else []
    if not entries:
        if str((state or {}).get("kind", "NONE")) != "PROGRESSIVE_SITE":
            scene.pop(DAMAGE_PREVIEW_STATE_PROPERTY, None)
            return
    payload = copy.deepcopy(state) if isinstance(state, dict) else {}
    payload["kind"] = str(payload.get("kind", "SINGLE"))
    payload["entries"] = entries
    scene[DAMAGE_PREVIEW_STATE_PROPERTY] = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )


def _preview_entry(region_id, key_name, weight, mode):
    resolved_mode = str(mode).upper()
    if resolved_mode not in {"ATTACHED", "DETACHED", "BOTH", "CORE"}:
        raise RuntimeError(f"Unsupported damage preview inspection mode {resolved_mode!r}.")
    return {
        "regionId": str(region_id),
        "keyName": str(key_name),
        "weight": max(0.0, float(weight)),
        "mode": resolved_mode,
    }


def _zero_all_damage_preview_weights(*, include_preview=True):
    registry = _load_registry()
    for region in registry.get("regions", []):
        attached, detached = _resolve_region_pair(region)
        _zero_managed_weights(attached, include_preview=include_preview)


def _enforce_damage_preview_weights(context, state):
    """Keep one single key, or the declared compound child set, active per region."""

    registry = _load_registry()
    regions = {str(region.get("regionId", "")): region for region in registry.get("regions", [])}
    allowed = {}
    for entry in state.get("entries", []):
        allowed.setdefault(str(entry.get("regionId", "")), set()).add(str(entry.get("keyName", "")))
    active = False
    state_changed = False
    for region_id, region in regions.items():
        attached, detached = _resolve_region_pair(region)
        allowed_names = allowed.get(region_id, set())
        for key_name in (*_managed_names(attached), PREVIEW_KEY_NAME):
            key = _key(attached, key_name)
            if key is not None and key_name not in allowed_names and abs(float(key.value)) > 1e-8:
                key.value = 0.0
            if detached is not None:
                detached_key = _key(detached, key_name)
                if (
                    detached_key is not None
                    and key_name not in allowed_names
                    and abs(float(detached_key.value)) > 1e-8
                ):
                    detached_key.value = 0.0
        for entry in state.get("entries", []):
            if str(entry.get("regionId", "")) != region_id:
                continue
            key = _key(attached, str(entry.get("keyName", "")))
            actual = float(key.value) if key is not None else 0.0
            active = active or actual > 1e-8
            if abs(float(entry.get("weight", 0.0)) - actual) > 1e-8:
                entry["weight"] = actual
                state_changed = True
    if state_changed:
        _store_damage_preview_state(context, state)
    return active


def _hide_all_generated_gore():
    for obj in generated_gore_objects(include_preview=True):
        obj.hide_viewport = False
        obj.hide_set(True)


def _sync_generated_gore_visibility(context=None, state=None):
    """Derive viewport gore visibility from preview state plus live morph weight."""

    context = context or bpy.context
    state = state or _damage_preview_state(context)
    entries = {
        (str(entry.get("regionId", "")), str(entry.get("keyName", ""))): entry
        for entry in state.get("entries", [])
    }
    registry = _load_registry()
    regions = {str(region.get("regionId", "")): region for region in registry.get("regions", [])}
    progression_active = str(state.get("kind", "")) == "PROGRESSIVE_SITE"
    progression_gore_key = (
        str(state.get("goreKeyName", "")) if progression_active else ""
    )
    progression_stage_keys = {
        str(value) for value in state.get("progressionStageKeyNames", [])
    }
    for gore_obj in generated_gore_objects(include_preview=True):
        region_id = str(gore_obj.get("dsb_gore_region_id", ""))
        key_name = str(gore_obj.get("dsb_gore_deformation_key", ""))
        entry = entries.get((region_id, key_name))
        show = False
        if entry is not None and float(entry.get("weight", 0.0)) > 1e-8:
            if (
                progression_active
                and key_name in progression_stage_keys
                and key_name != progression_gore_key
            ):
                entry = None
        if entry is not None and float(entry.get("weight", 0.0)) > 1e-8:
            region = regions.get(region_id)
            if region is not None:
                attached, _detached = _resolve_region_pair(region)
                key = _key(attached, key_name)
                actual_weight = float(key.value) if key is not None else 0.0
                role = str(gore_obj.get("dsb_gore_pair_role", "")).upper()
                mode = str(entry.get("mode", "ATTACHED")).upper()
                role_visible = (
                    (mode == "ATTACHED" and role == "ATTACHED")
                    or (mode == "DETACHED" and role == "DETACHED")
                    or (mode == "BOTH" and role in {"ATTACHED", "DETACHED"})
                    or (mode == "CORE" and role == "CORE")
                )
                show = actual_weight > 1e-8 and role_visible
        if gore_obj.hide_viewport:
            gore_obj.hide_viewport = False
        if bool(gore_obj.hide_get()) != (not show):
            gore_obj.hide_set(not show)


def _set_single_damage_preview_state(context, region_id, key_name, weight, mode):
    state = {"kind": "SINGLE", "entries": [_preview_entry(region_id, key_name, weight, mode)]}
    _store_damage_preview_state(context, state)
    _enforce_damage_preview_weights(context, state)
    _sync_generated_gore_visibility(context, state)
    return state


def _entry_active_stamp(entry, fallback_id=""):
    """Return the one active alternative for a key, with legacy-stack fallback."""

    stamps = list((entry or {}).get("stamps", []))
    requested = str((entry or {}).get("activeStampId", "") or fallback_id)
    active = next(
        (stamp for stamp in stamps if str(stamp.get("stampId", "")) == requested),
        None,
    )
    if active is None and stamps:
        active = sorted(stamps, key=lambda stamp: int(stamp.get("orderIndex", 0)))[0]
    return active


def _entry_preview_stamps(entry, fallback_id=""):
    """New keys use alternatives; migrated stacks retain additive replay."""

    if str((entry or {}).get("stampMode", "STACK")) == "ALTERNATIVES":
        active = _entry_active_stamp(entry, fallback_id)
        return [active] if active is not None and bool(active.get("enabled", True)) else []
    return [
        stamp
        for stamp in trauma_field.reindex_stamps((entry or {}).get("stamps", []))
        if bool(stamp.get("enabled", True))
    ]


def _sync_surface_stain_preview_visibility(context, state):
    """Show a stain only for a key whose per-key Preview toggle is enabled."""

    enabled_by_region = {}
    for state_entry in state.get("entries", []):
        if float(state_entry.get("weight", 0.0)) <= 1e-8:
            continue
        enabled_by_region.setdefault(
            str(state_entry.get("regionId", "")),
            [],
        ).append(str(state_entry.get("keyName", "")))
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    focused_key = (
        str(getattr(settings, "deformation_active_key", ""))
        if settings is not None
        else ""
    )
    registry = _load_registry()
    for region in registry.get("regions", []):
        region_id = str(region.get("regionId", ""))
        attached, detached = _resolve_region_pair(region)
        enabled_names = sorted(set(enabled_by_region.get(region_id, ())))
        desired_key = (
            focused_key
            if focused_key in enabled_names
            else enabled_names[0]
            if enabled_names
            else ""
        )
        current_state = _gore_state(attached)
        current_key = (
            str(current_state.get("keyName", ""))
            if current_state and not current_state.get("broken")
            else ""
        )
        has_mask = (
            attached.data.color_attributes.get(GORE_PREVIEW_ATTRIBUTE)
            is not None
        )
        if not desired_key:
            _clear_gore_preview_pair(attached, detached)
            continue
        if current_key == desired_key and has_mask:
            continue
        _install_existing_surface_stain_preview(
            context,
            region_id,
            desired_key,
        )


def apply_damage_key_previews(context=None):
    """Apply every per-key Preview toggle without changing focus or recipes."""

    context = context or bpy.context
    registry = _load_registry()
    state_entries = []
    enabled_names = []
    for region in registry.get("regions", []):
        region_id = str(region.get("regionId", ""))
        attached, detached = _resolve_region_pair(region)
        payload = _metadata(attached)
        for name, entry in payload.get("keys", {}).items():
            if not bool(entry.get("previewEnabled", False)):
                continue
            key = _key(attached, name)
            if key is None:
                continue
            weight = min(1.0, float(key.slider_max)) if _max_displacement(attached, name) > 1e-7 else 0.0
            key.value = weight
            if detached is not None:
                detached_key = _key(detached, name)
                if detached_key is not None:
                    detached_key.value = weight
            mode = "CORE" if detached is None else "ATTACHED"
            state_entries.append(_preview_entry(region_id, name, weight, mode))
            enabled_names.append(f"{region_id}/{name}")
    state = {
        "kind": "MULTI_KEY" if len(state_entries) > 1 else "SINGLE",
        "entries": state_entries,
    }
    _store_damage_preview_state(context, state)
    _enforce_damage_preview_weights(context, state)
    _sync_generated_gore_visibility(context, state)
    _sync_surface_stain_preview_visibility(context, state)
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is not None:
        settings.deformation_status = (
            f"DAMAGE KEY PREVIEWS — {len(state_entries)} ON"
            if state_entries else "DAMAGE KEY PREVIEWS — ALL OFF"
        )
    return {
        "enabledCount": len(state_entries),
        "enabledKeys": enabled_names,
        "state": state,
    }


def set_damage_key_preview_enabled(context, key_name, enabled=None):
    """Toggle exactly one Damage Key preview and preserve every other key."""

    registry, region, attached, detached = _resolve_active_region(context)
    payload = _metadata(attached)
    entry = payload.get("keys", {}).get(str(key_name))
    if not isinstance(entry, dict):
        raise RuntimeError(f"Damage Key {key_name!r} was not found in the active region.")
    current = bool(entry.get("previewEnabled", False))
    entry["previewEnabled"] = (not current) if enabled is None else bool(enabled)
    _store_metadata(attached, detached, payload)
    result = apply_damage_key_previews(context)
    result.update({"key": str(key_name), "enabled": bool(entry["previewEnabled"])})
    return result


def clear_damage_preview(context=None, *, update_status=True):
    """Clear deformation, stain, and gore presentation without deleting authored data."""

    global _PREVIEW_RESTORE_STATE
    context = context or bpy.context
    preview_service.cancel_timer()
    try:
        clear_seed_preview(all_regions=True)
    finally:
        try:
            clear_surface_gore_preview(all_regions=True)
        finally:
            _remove_preview_gore_objects()
            _zero_all_damage_preview_weights(include_preview=True)
            _hide_all_generated_gore()
            _store_damage_preview_state(context, {"kind": "NONE", "entries": []})
            if COMPOUND_PREVIEW_PROPERTY in context.scene:
                del context.scene[COMPOUND_PREVIEW_PROPERTY]
            _PREVIEW_RESTORE_STATE = {}
    if update_status:
        settings = getattr(context.scene, "daf_settings", None)
        if settings is not None:
            settings.deformation_status = "DAMAGE PREVIEW CLEARED"
    return {"morphWeight": 0.0, "stainCleared": True, "goreHidden": True}


def capture_damage_preview_snapshot(context=None):
    """Capture viewport presentation separately from export ownership metadata."""

    context = context or bpy.context
    registry = _load_registry()
    source_objects = []
    shape_values = {}
    stain_entries = []
    for region in registry.get("regions", []):
        attached, detached = _resolve_region_pair(region)
        for obj in tuple(value for value in (attached, detached) if value is not None):
            source_objects.append(obj)
            if obj.data.shape_keys:
                shape_values[obj.name] = {
                    key.name: float(key.value) for key in obj.data.shape_keys.key_blocks
                }
            gore_state = _gore_state(obj)
            if gore_state and not gore_state.get("broken"):
                record = (str(region.get("regionId", "")), str(gore_state.get("keyName", "")))
                if record[1] and record not in stain_entries:
                    stain_entries.append(record)
    visibility_objects = {obj.name: obj for obj in (*source_objects, *generated_gore_objects())}
    active = getattr(context.view_layer.objects, "active", None)
    settings = getattr(context.scene, "daf_settings", None)
    animation = {}
    for obj in bpy.data.objects:
        data = getattr(obj, "animation_data", None)
        if data is None:
            continue
        animation[obj.name] = {
            "action": data.action.name if data.action is not None else "",
            "tracks": [
                {
                    "name": track.name,
                    "mute": bool(track.mute),
                    "solo": bool(track.is_solo),
                    "strips": [
                        {
                            "name": strip.name,
                            "mute": bool(strip.mute),
                            "influence": float(strip.influence),
                        }
                        for strip in track.strips
                    ],
                }
                for track in data.nla_tracks
            ],
        }
    return {
        "damagePreviewState": copy.deepcopy(_damage_preview_state(context)),
        "compoundPreview": str(context.scene.get(COMPOUND_PREVIEW_PROPERTY, "")),
        "shapeValues": shape_values,
        "visibility": {
            name: {
                "hideViewport": bool(obj.hide_viewport),
                "hideRender": bool(obj.hide_render),
                "hideGet": bool(obj.hide_get()),
            }
            for name, obj in visibility_objects.items()
        },
        "stainEntries": [list(value) for value in stain_entries],
        "activeObject": active.name if active is not None else "",
        "selectedObjects": [obj.name for obj in context.selected_objects],
        "mode": str(getattr(context, "mode", "OBJECT")),
        "frame": int(context.scene.frame_current),
        "activeDamageKey": (
            str(settings.deformation_active_key) if settings is not None else ""
        ),
        "activeDamageStamp": (
            str(settings.deformation_active_stamp_id) if settings is not None else ""
        ),
        "previewGeneration": int(
            getattr(settings, "deformation_preview_generation", 0)
        ) if settings is not None else 0,
        "managedPreviewState": copy.deepcopy(preview_service.state()),
        "animation": animation,
    }


def restore_damage_preview_snapshot(context, snapshot):
    try:
        if getattr(context, "mode", "OBJECT") != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    except RuntimeError:
        pass
    clear_surface_gore_preview(all_regions=True)
    for object_name, values in snapshot.get("shapeValues", {}).items():
        obj = _object(object_name)
        if obj is None or obj.data.shape_keys is None:
            continue
        for key_name, value in values.items():
            key = _key(obj, key_name)
            if key is not None:
                key.value = float(value)
    for object_name, record in snapshot.get("visibility", {}).items():
        obj = _object(object_name)
        if obj is None:
            continue
        obj.hide_viewport = bool(record.get("hideViewport", False))
        obj.hide_render = bool(record.get("hideRender", False))
        obj.hide_set(bool(record.get("hideGet", False)))
    state = copy.deepcopy(snapshot.get("damagePreviewState", {"kind": "NONE", "entries": []}))
    _store_damage_preview_state(context, state)
    raw_compound = str(snapshot.get("compoundPreview", ""))
    if raw_compound:
        context.scene[COMPOUND_PREVIEW_PROPERTY] = raw_compound
    else:
        context.scene.pop(COMPOUND_PREVIEW_PROPERTY, None)
    for region_id, key_name in snapshot.get("stainEntries", []):
        _install_existing_surface_stain_preview(context, str(region_id), str(key_name))
    _store_damage_preview_state(context, state)
    _sync_generated_gore_visibility(context, state)
    for object_name, record in snapshot.get("animation", {}).items():
        obj = _object(object_name)
        data = getattr(obj, "animation_data", None) if obj is not None else None
        if data is None:
            continue
        data.action = bpy.data.actions.get(str(record.get("action", "")))
        tracks = {track.name: track for track in data.nla_tracks}
        for track_record in record.get("tracks", []):
            track = tracks.get(str(track_record.get("name", "")))
            if track is None:
                continue
            track.mute = bool(track_record.get("mute", False))
            track.is_solo = bool(track_record.get("solo", False))
            strips = {strip.name: strip for strip in track.strips}
            for strip_record in track_record.get("strips", []):
                strip = strips.get(str(strip_record.get("name", "")))
                if strip is None:
                    continue
                strip.mute = bool(strip_record.get("mute", False))
                strip.influence = float(strip_record.get("influence", 1.0))
    settings = getattr(context.scene, "daf_settings", None)
    if settings is not None:
        with preview_service.suspend_updates():
            settings.deformation_active_key = str(
                snapshot.get("activeDamageKey", "")
            )
            settings.deformation_active_stamp_id = str(
                snapshot.get("activeDamageStamp", "")
            )
            settings.deformation_preview_generation = int(
                snapshot.get("previewGeneration", 0)
            )
    context.scene.frame_set(int(snapshot.get("frame", context.scene.frame_current)))
    try:
        bpy.ops.object.select_all(action="DESELECT")
        for object_name in snapshot.get("selectedObjects", []):
            obj = _object(object_name)
            if obj is not None and obj.name in context.view_layer.objects:
                obj.select_set(True)
        active = _object(snapshot.get("activeObject", ""))
        if active is not None and active.name in context.view_layer.objects:
            context.view_layer.objects.active = active
        prior_mode = str(snapshot.get("mode", "OBJECT"))
        if prior_mode.startswith("EDIT") and active is not None:
            bpy.ops.object.mode_set(mode="EDIT")
        elif prior_mode == "SCULPT" and active is not None:
            bpy.ops.object.mode_set(mode="SCULPT")
        elif prior_mode == "POSE" and active is not None:
            bpy.ops.object.mode_set(mode="POSE")
    except RuntimeError:
        pass


def _set_authoring_view(attached, detached, mode='ATTACHED', context=None):
    """Normalize viewport-only visibility for one explicit registered region."""

    if detached is None and mode == 'ATTACHED':
        mode = 'CORE'
    if mode not in {'ATTACHED', 'DETACHED', 'BOTH', 'CORE'}:
        raise RuntimeError(f"Unsupported Trauma Field authoring view {mode!r}.")
    context = context or bpy.context
    if getattr(context, "view_layer", None) is None or getattr(context, "scene", None) is None:
        raise RuntimeError("Trauma Field visibility requires an active scene and view layer.")
    if detached is None and mode == 'DETACHED':
        raise RuntimeError("Core single-mesh regions have no detached preview.")
    pair = tuple(obj for obj in (attached, detached) if obj is not None)
    relevant_collections = {
        collection
        for obj in pair
        for collection in obj.users_collection
        if _is_dsb_authoring_collection(collection)
    }

    # Damage Authoring may set object and DSB collection viewport flags. Restore
    # only the active pair and its generated collection paths; render/export
    # visibility and unrelated user collections remain untouched.
    for obj in pair:
        obj.hide_viewport = False
    for collection in relevant_collections:
        collection.hide_viewport = False
        for path in _collection_paths(context.scene.collection, collection):
            for parent in path:
                if _is_dsb_authoring_collection(parent):
                    parent.hide_viewport = False
        for path in _layer_collection_paths(context.view_layer.layer_collection, collection):
            for layer_collection in path:
                if _is_dsb_authoring_collection(layer_collection.collection):
                    layer_collection.exclude = False
                    layer_collection.hide_viewport = False

    for obj in pair:
        if obj.name not in context.view_layer.objects:
            raise RuntimeError(_visibility_blocker(context, obj))

    show_attached = mode in {'ATTACHED', 'BOTH', 'CORE'}
    show_detached = detached is not None and mode in {'DETACHED', 'BOTH'}
    attached.hide_set(not show_attached)
    if detached is not None:
        detached.hide_set(not show_detached)
    for obj, should_show in tuple((obj, show) for obj, show in ((attached, show_attached), (detached, show_detached)) if obj is not None):
        if should_show and not _object_visible_in_view_layer(obj, context.view_layer):
            raise RuntimeError(_visibility_blocker(context, obj))
    region_id = str(attached.get("dsb_deformation_region", ""))
    state = _damage_preview_state(context)
    changed = False
    for entry in state.get("entries", []):
        if str(entry.get("regionId", "")) == region_id:
            entry["mode"] = mode
            changed = True
    if changed:
        _store_damage_preview_state(context, state)
    _sync_generated_gore_visibility(context, state)


def set_damage_preview_inspection_mode(context, mode):
    _registry, region, attached, detached = _resolve_active_region(context)
    settings = context.scene.daf_settings
    key_name = str(settings.deformation_active_key)
    state = _damage_preview_state(context)
    matching = any(
        str(entry.get("regionId", "")) == str(region.get("regionId", ""))
        and str(entry.get("keyName", "")) == key_name
        for entry in state.get("entries", [])
    )
    if not matching and key_name:
        key = _key(attached, key_name)
        weight = float(key.value) if key is not None else 0.0
        if weight > 1e-8:
            _set_single_damage_preview_state(context, region.get("regionId", ""), key_name, weight, mode)
    _set_authoring_view(attached, detached, mode, context)
    return attached, detached


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
    shape_keys.set_coordinates(key_block, coordinates)


def _sync_exact_index_key_pair(attached, detached, name):
    attached_key = _key(attached, name)
    detached_key = _key(detached, name)
    if attached_key is None or detached_key is None:
        raise RuntimeError(f"The paired key {name} is incomplete.")
    attached_basis = attached.data.shape_keys.reference_key
    detached_basis = detached.data.shape_keys.reference_key
    if attached_basis is None or detached_basis is None:
        raise RuntimeError(f"The paired key {name} has no Basis key.")
    if not (
        len(attached_key.data) == len(detached_key.data)
        == len(attached_basis.data) == len(detached_basis.data)
    ):
        raise RuntimeError(f"The paired key {name} has mismatched point counts.")
    _evaluated_world_matrix(attached)
    _evaluated_world_matrix(detached)
    for index in range(len(attached_key.data)):
        delta_attached_local = attached_key.data[index].co - attached_basis.data[index].co
        delta_world = _local_delta_to_world(attached, delta_attached_local)
        delta_detached_local = _world_delta_to_local(detached, delta_world)
        detached_key.data[index].co = detached_basis.data[index].co + delta_detached_local
    _link_detached_value(attached, detached, name)


def sync_key_to_detached(name, region_id=None):
    _registry, region, attached, detached = _resolve_active_region(region_id=region_id)
    contract = validate_region_contract(region, attached, detached)
    if contract["status"] != "PASS":
        raise RuntimeError(" ".join(contract["errors"]))
    if _region_mode(region) == CORE_SINGLE:
        if _key(attached, name) is None:
            raise RuntimeError(f"The core deformation key {name!r} is missing.")
        return
    _sync_exact_index_key_pair(attached, detached, name)


def _pair_delta_error(attached, detached, name):
    attached_key = _key(attached, name)
    detached_key = _key(detached, name)
    attached_basis = attached.data.shape_keys.reference_key if attached.data.shape_keys else None
    detached_basis = detached.data.shape_keys.reference_key if detached.data.shape_keys else None
    if attached_key is None or detached_key is None or attached_basis is None or detached_basis is None:
        return math.inf
    if not (
        len(attached_key.data) == len(detached_key.data)
        == len(attached_basis.data) == len(detached_basis.data)
    ):
        return math.inf
    _evaluated_world_matrix(attached)
    _evaluated_world_matrix(detached)
    maximum = 0.0
    for index in range(len(attached_key.data)):
        delta_a = _local_delta_to_world(attached, attached_key.data[index].co - attached_basis.data[index].co)
        delta_d = _local_delta_to_world(detached, detached_key.data[index].co - detached_basis.data[index].co)
        values = (*attached_key.data[index].co, *detached_key.data[index].co, *delta_a, *delta_d)
        if not all(math.isfinite(value) for value in values):
            return math.inf
        maximum = max(maximum, (delta_a - delta_d).length)
    return maximum


def _attached_key_repair_safety(attached, detached, name, declared_maximum, topology_contract):
    if topology_contract.get("status") != "PASS":
        return False, "Registered topology pair failed: " + " ".join(topology_contract.get("errors", []))
    attached_key = _key(attached, name)
    detached_key = _key(detached, name)
    attached_basis = attached.data.shape_keys.reference_key if attached.data.shape_keys else None
    detached_basis = detached.data.shape_keys.reference_key if detached.data.shape_keys else None
    if attached_key is None or detached_key is None:
        return False, "The exact legacy key is missing from one side."
    if attached_basis is None or detached_basis is None:
        return False, "The exact legacy key has no Basis key."
    if not (
        len(attached_key.data) == len(detached_key.data)
        == len(attached_basis.data) == len(detached_basis.data)
    ):
        return False, "The exact legacy key has unequal point counts."
    try:
        maximum = float(declared_maximum)
    except (TypeError, ValueError):
        maximum = math.nan
    if not math.isfinite(maximum) or maximum <= 0.0:
        return False, "The attached key has no valid declared maximum displacement."
    measured = 0.0
    for index in range(len(attached_key.data)):
        attached_coordinate = attached_key.data[index].co
        attached_basis_coordinate = attached_basis.data[index].co
        delta_world = _local_delta_to_world(attached, attached_coordinate - attached_basis_coordinate)
        if not all(math.isfinite(value) for value in (*attached_coordinate, *attached_basis_coordinate, *delta_world)):
            return False, "The attached key contains non-finite coordinates or deltas."
        measured = max(measured, delta_world.length)
    if measured > maximum + PAIR_TOLERANCE:
        return False, f"The attached key exceeds its declared maximum displacement: {measured:.6f} m > {maximum:.6f} m."
    return True, ""


def _finite_error_or_none(value):
    return float(value) if math.isfinite(value) else None


def repair_legacy_pair_sync(context=None, region_id=None, candidate_names=None, automatic=False):
    """Repair safe Forge-managed legacy pairs from attached to detached by index."""

    registry, region, attached, detached = _resolve_active_region(context, region_id)
    if _region_mode(region) != PAIRED_SEGMENT or detached is None:
        raise RuntimeError("Legacy pair synchronization is available only for paired-segment regions.")
    if automatic and not (
        region.get("regionId") == "head"
        and attached.name == ATTACHED_HEAD_NAME
        and detached.name == DETACHED_HEAD_NAME
    ):
        raise RuntimeError("Automatic legacy repair is restricted to the exact Testman head pair.")
    payload = _metadata(attached)
    metadata_keys = payload.setdefault("keys", {})
    if candidate_names is None:
        names = sorted(metadata_keys)
    else:
        names = sorted({str(name) for name in candidate_names})
    if automatic:
        names = [name for name in names if name in STANDARD_HEAD_KEYS]
        for name in names:
            if not isinstance(metadata_keys.get(name), dict):
                metadata_keys[name] = {
                    "name": name,
                    "region": "head",
                    "regionId": "head",
                    "status": "MIGRATED",
                    "recipeStatus": "LEGACY_MANUAL",
                    "legacy": True,
                    "stamps": [],
                    **STANDARD_HEAD_KEYS[name],
                }

    result = {
        "inspected": 0,
        "healthy": 0,
        "repaired": 0,
        "skipped": 0,
        "unrepairable": 0,
        "details": [],
    }
    topology_contract = validate_topology_pair(attached, detached)
    for name in names:
        result["inspected"] += 1
        entry = metadata_keys.get(name)
        if not isinstance(entry, dict) or name == PREVIEW_KEY_NAME:
            result["skipped"] += 1
            result["details"].append({"name": name, "status": "SKIPPED", "reason": "Not a Forge-managed legacy key."})
            continue
        if entry.get("stamps") or entry.get("recipeStatus") == "PROCEDURAL_STACK":
            result["skipped"] += 1
            result["details"].append({"name": name, "status": "SKIPPED", "reason": "Procedural stamp-stack key."})
            continue
        attached_key = _key(attached, name)
        detached_key = _key(detached, name)
        if attached_key is None or detached_key is None:
            result["skipped"] += 1
            result["details"].append({"name": name, "status": "SKIPPED", "reason": "Missing key left unchanged."})
            continue

        before = _pair_delta_error(attached, detached, name)
        safe, reason = _attached_key_repair_safety(
            attached,
            detached,
            name,
            entry.get("maximumDisplacement"),
            topology_contract,
        )
        entry["legacySyncErrorBefore"] = _finite_error_or_none(before)
        entry["legacySyncRepairApplied"] = False
        if not safe:
            entry["legacySyncStatus"] = "UNREPAIRABLE"
            entry["legacySyncErrorAfter"] = _finite_error_or_none(before)
            entry["legacySyncReason"] = reason
            result["unrepairable"] += 1
            result["details"].append({"name": name, "status": "UNREPAIRABLE", "reason": reason})
            continue
        if before <= SYNC_TOLERANCE:
            try:
                _link_detached_value(attached, detached, name)
            except Exception as exc:
                entry["legacySyncStatus"] = "UNREPAIRABLE"
                entry["legacySyncErrorAfter"] = float(before)
                entry["legacySyncReason"] = "Could not restore the detached value driver: " + str(exc)
                result["unrepairable"] += 1
                result["details"].append({"name": name, "status": "UNREPAIRABLE", "reason": entry["legacySyncReason"]})
                continue
            entry["legacySyncStatus"] = "PASS"
            entry["legacySyncErrorAfter"] = float(before)
            entry.pop("legacySyncReason", None)
            result["healthy"] += 1
            result["details"].append({"name": name, "status": "PASS", "error": float(before)})
            continue

        original_detached = [point.co.copy() for point in detached_key.data]
        try:
            _sync_exact_index_key_pair(attached, detached, name)
            after = _pair_delta_error(attached, detached, name)
            if not math.isfinite(after) or after > SYNC_TOLERANCE:
                raise RuntimeError(f"Exact-index repair still differs by {after:.8f} m.")
        except Exception as exc:
            for point, coordinate in zip(detached_key.data, original_detached):
                point.co = coordinate
            entry["legacySyncStatus"] = "UNREPAIRABLE"
            entry["legacySyncErrorAfter"] = _finite_error_or_none(_pair_delta_error(attached, detached, name))
            entry["legacySyncReason"] = str(exc)
            result["unrepairable"] += 1
            result["details"].append({"name": name, "status": "UNREPAIRABLE", "reason": str(exc)})
            continue
        entry["legacySyncStatus"] = "REPAIRED"
        entry["legacySyncErrorAfter"] = float(after)
        entry["legacySyncRepairApplied"] = True
        entry.pop("legacySyncReason", None)
        result["repaired"] += 1
        result["details"].append({"name": name, "status": "REPAIRED", "before": float(before), "after": float(after)})

    result["summary"] = (
        f"LEGACY PAIR REPAIR — {result['healthy']} healthy / "
        f"{result['repaired']} repaired / {result['unrepairable']} unrepairable"
    )
    payload["legacyPairRepair"] = {
        "regionId": region.get("regionId"),
        "inspected": result["inspected"],
        "healthy": result["healthy"],
        "repaired": result["repaired"],
        "skipped": result["skipped"],
        "unrepairable": result["unrepairable"],
        "summary": result["summary"],
        "automatic": bool(automatic),
    }
    _store_metadata(attached, detached, payload)
    registry = _load_registry(migrate_legacy=False)
    stored_region = _region_record(registry, region.get("regionId"))
    if stored_region is not None:
        stored_region["legacyPairRepair"] = payload["legacyPairRepair"]
        _store_registry(registry)
    return result


def preview_seed(context, quiet=False):
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        raise RuntimeError("Switch to Object Mode before previewing a deformation seed.")
    settings = context.scene.daf_settings
    clear_damage_preview(context, update_status=False)
    _registry, region, _source, _paired = _resolve_active_region(context)
    attached, detached, attached_preview, _detached_preview = _ensure_key_pair(PREVIEW_KEY_NAME, preview=True)
    _zero_managed_weights(attached)
    _set_authoring_view(attached, detached, 'ATTACHED')
    coordinates = _seed_coordinates(settings, attached)
    _set_key_coordinates(attached_preview, coordinates)
    if detached is not None:
        _sync_exact_index_key_pair(attached, detached, PREVIEW_KEY_NAME)
    attached_preview.value = 1.0
    attached_preview.slider_max = 1.0
    inspection = 'CORE' if detached is None else 'ATTACHED'
    _set_single_damage_preview_state(context, region.get("regionId", ""), PREVIEW_KEY_NAME, 1.0, inspection)
    _set_authoring_view(attached, detached, inspection, context)
    settings.deformation_status = "LIVE SEED PREVIEW"
    if not quiet:
        return {"vertexCount": len(coordinates), "key": settings.deformation_active_key}
    return None


def refresh_live_seed_preview(context):
    """Compatibility entry point: schedule managed preview without doing geometry work."""

    return request_managed_preview(context, "legacy live-preview request")


def request_managed_preview(context, reason="property update"):
    return preview_service.request_refresh(context, reason)


def _impact_macro_values(settings):
    return (
        float(settings.deformation_impact_size),
        float(settings.deformation_impact_crush),
        float(settings.deformation_impact_profile),
        float(settings.deformation_impact_edge_safety),
        float(settings.deformation_impact_chaos),
        float(settings.deformation_impact_asymmetry),
    )


def _impact_region_scale(settings):
    try:
        capture = json.loads(str(settings.deformation_capture_json or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        capture = {}
    estimate = float(capture.get("estimatedRadius", settings.deformation_seed_radius))
    return estimate if math.isfinite(estimate) and estimate > 0.0 else 0.075


def impact_control_metadata(settings, *, mode=None):
    return parameter_schema.normalize_impact_control({
        "schema": IMPACT_CONTROL_SCHEMA,
        "version": parameter_schema.IMPACT_CONTROL_VERSION,
        "mode": str(mode or settings.deformation_impact_control_mode),
        "macros": {
            "size": float(settings.deformation_impact_size),
            "crush": float(settings.deformation_impact_crush),
            "profile": float(settings.deformation_impact_profile),
            "edgeSafety": float(settings.deformation_impact_edge_safety),
            "chaos": float(settings.deformation_impact_chaos),
            "asymmetry": float(settings.deformation_impact_asymmetry),
        },
        "seed": int(settings.deformation_impact_seed),
    })


def _assign_impact_derived_values(settings, derived):
    settings.deformation_seed_radius = float(derived["radius"])
    settings.deformation_seed_depth = float(derived["depth"])
    settings.deformation_seed_falloff = float(derived["falloff"])
    settings.deformation_feather_distance = float(derived["featherDistance"])
    settings.deformation_seed_seam_protection = float(derived["seamProtection"])
    settings.deformation_stamp_strength = float(derived["strength"])
    settings.deformation_max_vertex_displacement = float(derived["maximumDisplacement"])
    settings.deformation_impact_gore_patch_scale = float(derived["gorePatchScale"])
    settings.deformation_gore_coverage = float(derived["goreCoverage"])
    settings.deformation_gore_scatter = float(derived["goreScatter"])
    settings.deformation_gore_island_breakup = float(derived["goreIslandBreakup"])
    settings.deformation_gore_organic_irregularity = float(derived["goreOrganicIrregularity"])


def _mark_impact_dirty(settings, metadata):
    settings.deformation_impact_dirty = True
    settings.deformation_impact_identity = str(metadata["identityDigest"])
    settings.deformation_impact_transaction_count = int(settings.deformation_impact_transaction_count) + 1


def request_low_level_property_update(context, reason="deformation control changed"):
    """Route editable raw values without recursively reapplying macros."""

    if _IMPACT_TRANSACTION_DEPTH or preview_service.updates_suspended():
        return int(preview_service.state().get("generation", 0))
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is not None:
        metadata = impact_control_metadata(
            settings,
            mode="MANUAL" if settings.deformation_impact_control_mode == 'MANUAL' else "MACRO",
        )
        settings.deformation_impact_dirty = True
        settings.deformation_impact_identity = str(metadata["identityDigest"])
    return request_managed_preview(context, reason)


# Backward-compatible name for integrations that called the pre-3.17 helper.
handle_low_level_property_update = request_low_level_property_update


def apply_impact_macro_transaction(context, reason="Impact Pedal changed"):
    """Derive and assign the full physical recipe with one dirty/token request."""

    global _IMPACT_TRANSACTION_DEPTH
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is None or _IMPACT_TRANSACTION_DEPTH or preview_service.updates_suspended():
        return {}
    if str(settings.deformation_impact_control_mode) != 'MACRO':
        return {}
    derived = parameter_schema.derive_impact_parameters(
        _impact_macro_values(settings),
        region_scale=_impact_region_scale(settings),
        family=str(settings.deformation_stamp_family),
        seed=int(settings.deformation_impact_seed),
    )
    metadata = impact_control_metadata(settings, mode="MACRO")
    _IMPACT_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            _assign_impact_derived_values(settings, derived)
            _mark_impact_dirty(settings, metadata)
    finally:
        _IMPACT_TRANSACTION_DEPTH = max(0, _IMPACT_TRANSACTION_DEPTH - 1)
    generation = request_managed_preview(context, reason)
    return {"derived": derived, "metadata": metadata, "generation": generation}


def apply_impact_seed_transaction(context, reason="master impact seed changed"):
    """Apply a validated seed identity and schedule at most one managed preview."""

    global _IMPACT_TRANSACTION_DEPTH
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is None or _IMPACT_TRANSACTION_DEPTH or preview_service.updates_suspended():
        return {}
    errors = parameter_schema.validate("deformation_impact_seed", settings.deformation_impact_seed)
    if errors:
        raise ValueError(errors[0])
    metadata = impact_control_metadata(settings)
    _IMPACT_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            _mark_impact_dirty(settings, metadata)
    finally:
        _IMPACT_TRANSACTION_DEPTH = max(0, _IMPACT_TRANSACTION_DEPTH - 1)
    generation = request_managed_preview(context, reason)
    return {"seed": int(settings.deformation_impact_seed), "metadata": metadata, "generation": generation}


def randomize_impact_seed(context):
    """Choose one new valid seed without changing identity semantics or macros."""

    global _IMPACT_TRANSACTION_DEPTH
    settings = context.scene.daf_settings
    previous = int(settings.deformation_impact_seed)
    candidate = previous
    while candidate == previous:
        candidate = secrets.randbelow(parameter_schema.MAX_SEED + 1)
    _IMPACT_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            settings.deformation_impact_seed = candidate
    finally:
        _IMPACT_TRANSACTION_DEPTH = max(0, _IMPACT_TRANSACTION_DEPTH - 1)
    result = apply_impact_seed_transaction(context, "impact seed randomized")
    result["previousSeed"] = previous
    return result


def _gore_macro_values(settings):
    return (
        float(settings.deformation_gore_exposure),
        float(settings.deformation_gore_inlay_amount) * 100.0,
        float(settings.deformation_gore_clot_fill),
        float(settings.deformation_gore_breakup),
        float(settings.deformation_gore_wetness_macro),
        float(settings.deformation_gore_raised_amount) * 100.0,
    )


def _surface_gore_macro_values(settings):
    return (
        float(settings.deformation_gore_surface_mass),
        float(settings.deformation_gore_surface_relief),
        float(settings.deformation_gore_nucleus),
        float(settings.deformation_gore_lobes),
        float(settings.deformation_gore_redness),
    )


def _sample_mean_edge_length(obj, *, maximum_edges=512):
    matrix = obj.matrix_world
    vertices = obj.data.vertices
    samples = []
    for edge in obj.data.edges[:max(0, int(maximum_edges))]:
        first, second = edge.vertices
        distance = (
            matrix @ vertices[int(first)].co
            - matrix @ vertices[int(second)].co
        ).length
        if math.isfinite(distance) and distance > 1e-12:
            samples.append(distance)
    return sum(samples) / len(samples) if samples else None


def _gore_scale_inputs(context, settings):
    region_scale = _impact_region_scale(settings)
    mean_edge_length = region_scale * 0.05
    try:
        _registry, _region, attached, _detached = _resolve_active_region(context)
        sampled_edge_length = _sample_mean_edge_length(attached)
        if sampled_edge_length is not None:
            mean_edge_length = sampled_edge_length
    except Exception:
        pass
    return region_scale, max(1e-6, mean_edge_length)


def gore_control_metadata(settings, *, mode=None):
    identity_id = str(settings.deformation_gore_identity)
    if identity_id not in parameter_schema.GORE_IDENTITIES:
        identity_id = parameter_schema.gore_identity_for_preset(settings.deformation_gore_preset)
    if identity_id not in parameter_schema.GORE_IDENTITIES:
        identity_id = "BLOODY_CRATER"
    return parameter_schema.normalize_gore_control({
        "schema": parameter_schema.GORE_CONTROL_SCHEMA,
        "version": parameter_schema.GORE_CONTROL_VERSION,
        "mode": str(mode or settings.deformation_gore_control_mode),
        "identityId": identity_id,
        "macros": {
            "exposure": float(settings.deformation_gore_exposure),
            "cavity": float(settings.deformation_gore_inlay_amount) * 100.0,
            "clotFill": float(settings.deformation_gore_clot_fill),
            "breakup": float(settings.deformation_gore_breakup),
            "wetness": float(settings.deformation_gore_wetness_macro),
            "variation": float(settings.deformation_gore_raised_amount) * 100.0,
        },
        "seed": int(settings.deformation_gore_mask_seed),
    })


def surface_gore_control_metadata(settings):
    return parameter_schema.normalize_surface_gore_control({
        "schema": parameter_schema.SURFACE_GORE_CONTROL_SCHEMA,
        "version": parameter_schema.SURFACE_GORE_CONTROL_VERSION,
        "macros": {
            "mass": float(settings.deformation_gore_surface_mass),
            "relief": float(
                settings.deformation_gore_surface_relief
            ),
            "nucleus": float(settings.deformation_gore_nucleus),
            "lobes": float(settings.deformation_gore_lobes),
            "redness": float(settings.deformation_gore_redness),
        },
    })


def _combined_gore_identity_digest(settings):
    control = gore_control_metadata(settings)
    surface = surface_gore_control_metadata(settings)
    return hashlib.sha256(
        (
            str(control["identityDigest"])
            + "|"
            + str(surface["identityDigest"])
        ).encode("ascii")
    ).hexdigest()


def _derive_complete_gore_parameters(
    context,
    settings,
    *,
    identity_id,
    stamp_depth,
    region_scale=None,
    mean_edge_length=None,
):
    if region_scale is None or mean_edge_length is None:
        region_scale, mean_edge_length = _gore_scale_inputs(
            context,
            settings,
        )
    derived = parameter_schema.derive_gore_parameters(
        _gore_macro_values(settings),
        identity_id=str(identity_id),
        region_scale=float(region_scale),
        stamp_depth=float(stamp_depth),
        mean_edge_length=float(mean_edge_length),
    )
    derived.update(
        parameter_schema.derive_surface_gore_parameters(
            _surface_gore_macro_values(settings),
            region_scale=float(region_scale),
            mean_edge_length=float(mean_edge_length),
        )
    )
    return derived


def _assign_gore_derived_values(settings, derived):
    scalar_properties = {
        "goreCoverage": "deformation_gore_coverage",
        "goreScatter": "deformation_gore_scatter",
        "goreEdgeFeather": "deformation_gore_edge_feather",
        "goreWetness": "deformation_gore_wetness",
        "goreDarkness": "deformation_gore_darkness",
        "gorePatchScale": "deformation_impact_gore_patch_scale",
        "goreClotCoverage": "deformation_gore_clot_coverage",
        "goreCoreDensity": "deformation_gore_core_density",
        "goreClotThickness": "deformation_gore_clot_thickness",
        "goreThicknessVariation": "deformation_gore_thickness_variation",
        "goreIslandBreakup": "deformation_gore_island_breakup",
        "gorePeripheralFragments": "deformation_gore_peripheral_fragments",
        "goreSurfaceOffset": "deformation_gore_surface_offset",
        "goreGeometryDensity": "deformation_gore_geometry_density",
        "goreWetnessVariation": "deformation_gore_wetness_variation",
        "goreDarkClotBias": "deformation_gore_dark_clot_bias",
        "goreRoughEdgeBias": "deformation_gore_rough_edge_bias",
        "goreColorIntensity": "deformation_gore_color_intensity",
        "goreOrganicIrregularity": "deformation_gore_organic_irregularity",
        "goreSurfaceRoundness": "deformation_gore_surface_roundness",
        "goreFiberTextureStrength": "deformation_gore_fiber_texture_strength",
        "goreBaseColorStrength": "deformation_gore_base_color_strength",
        "goreInnerRimWidth": "deformation_gore_inner_rim_width",
        "goreInnerRimStrength": "deformation_gore_inner_rim_strength",
        "goreCavityDepth": "deformation_gore_cavity_depth",
        "goreLinerSeparation": "deformation_gore_liner_separation",
        "goreRimWidth": "deformation_gore_rim_width",
        "goreClotFillDepth": "deformation_gore_clot_fill_depth",
        "goreProudnessLimit": "deformation_gore_proudness_limit",
        "goreHostDeformationContribution": "deformation_gore_host_deformation_contribution",
        "goreBoneReveal": "deformation_gore_bone_reveal",
        "goreTissueCoverage": "deformation_gore_tissue_coverage",
        "goreInlayAmount": "deformation_gore_inlay_amount",
        "goreRaisedAmount": "deformation_gore_raised_amount",
        "goreSurfaceMass": "deformation_gore_surface_mass_value",
        "goreNucleusAmount": "deformation_gore_nucleus_amount",
        "goreNucleusLobes": "deformation_gore_nucleus_lobes",
    }
    boolean_properties = {
        "goreWoundBedEnabled": "deformation_gore_wound_bed_enabled",
        "goreClotLayerEnabled": "deformation_gore_clot_layer_enabled",
        "goreTissueLayerEnabled": "deformation_gore_tissue_layer_enabled",
        "goreBoneLayerEnabled": "deformation_gore_bone_layer_enabled",
        "goreBarrierLayerEnabled": "deformation_gore_barrier_layer_enabled",
        "goreRaisedRimOptIn": "deformation_gore_raised_rim_opt_in",
        "goreAllowInternalFragments": "deformation_gore_allow_internal_fragments",
    }
    for field, property_name in scalar_properties.items():
        setattr(settings, property_name, float(derived[field]))
    for field, property_name in boolean_properties.items():
        setattr(settings, property_name, bool(derived[field]))
    settings.deformation_gore_geometry_mode = str(derived["goreGeometryMode"])
    settings.deformation_gore_raised_enabled = derived["goreGeometryMode"] != "STAIN_ONLY"
    settings.deformation_gore_inner_rim_enabled = bool(derived["goreBarrierLayerEnabled"])
    settings.deformation_gore_texture_enabled = True
    settings.deformation_gore_maximum_triangles = int(derived["goreMaximumTriangles"])


def _mark_gore_dirty(settings, metadata):
    settings.deformation_gore_dirty = True
    settings.deformation_gore_identity_digest = (
        _combined_gore_identity_digest(settings)
    )
    settings.deformation_gore_transaction_count = int(settings.deformation_gore_transaction_count) + 1
    settings.deformation_gore_validation_status = "DIRTY"


def apply_gore_macro_transaction(context, reason="Gore Pedal changed"):
    """Derive one complete cavity/inlay recipe and request at most one preview."""

    global _GORE_TRANSACTION_DEPTH
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is None or _GORE_TRANSACTION_DEPTH or preview_service.updates_suspended():
        return {}
    if str(settings.deformation_gore_control_mode) != "MACRO":
        return {}
    metadata = gore_control_metadata(settings, mode="MACRO")
    derived = _derive_complete_gore_parameters(
        context,
        settings,
        identity_id=str(metadata["identityId"]),
        stamp_depth=float(settings.deformation_seed_depth),
    )
    _GORE_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            settings.deformation_gore_enabled = True
            settings.deformation_gore_identity = str(metadata["identityId"])
            settings.deformation_gore_preset = "USER_AUTHORED"
            settings.deformation_gore_cavity = (
                float(settings.deformation_gore_inlay_amount) * 100.0
            )
            settings.deformation_gore_variation = (
                float(settings.deformation_gore_raised_amount) * 100.0
            )
            _assign_gore_derived_values(settings, derived)
            _mark_gore_dirty(settings, metadata)
    finally:
        _GORE_TRANSACTION_DEPTH = max(0, _GORE_TRANSACTION_DEPTH - 1)
    generation = request_managed_preview(context, reason)
    return {"derived": derived, "metadata": metadata, "generation": generation}


def apply_gore_identity_transaction(context):
    global _GORE_TRANSACTION_DEPTH
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is None or _GORE_TRANSACTION_DEPTH or preview_service.updates_suspended():
        return {}
    identity_id = str(settings.deformation_gore_identity)
    if identity_id not in parameter_schema.GORE_IDENTITIES:
        raise ValueError(f"Unsupported gore identity {identity_id!r}.")
    _GORE_TRANSACTION_DEPTH += 1
    try:
        settings.deformation_gore_preset = str(
            parameter_schema.GORE_IDENTITIES[identity_id]["presetId"]
        )
    finally:
        _GORE_TRANSACTION_DEPTH = max(0, _GORE_TRANSACTION_DEPTH - 1)
    return apply_gore_preset_to_settings(context)


def apply_gore_seed_transaction(context, reason="master gore seed changed"):
    global _GORE_TRANSACTION_DEPTH
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is None or _GORE_TRANSACTION_DEPTH or preview_service.updates_suspended():
        return {}
    errors = parameter_schema.validate(
        "deformation_gore_mask_seed", settings.deformation_gore_mask_seed
    )
    if errors:
        raise ValueError(errors[0])
    metadata = gore_control_metadata(settings)
    _GORE_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            _mark_gore_dirty(settings, metadata)
    finally:
        _GORE_TRANSACTION_DEPTH = max(0, _GORE_TRANSACTION_DEPTH - 1)
    generation = request_managed_preview(context, reason)
    return {
        "seed": int(settings.deformation_gore_mask_seed),
        "metadata": metadata,
        "generation": generation,
    }


def randomize_gore_seed(context):
    """Change only the complete deterministic inlay identity."""

    global _GORE_TRANSACTION_DEPTH
    settings = context.scene.daf_settings
    previous = int(settings.deformation_gore_mask_seed)
    candidate = previous
    while candidate == previous:
        candidate = secrets.randbelow(parameter_schema.MAX_SEED + 1)
    _GORE_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            settings.deformation_gore_mask_seed = candidate
    finally:
        _GORE_TRANSACTION_DEPTH = max(0, _GORE_TRANSACTION_DEPTH - 1)
    result = apply_gore_seed_transaction(context, "gore seed randomized")
    result["previousSeed"] = previous
    return result


def randomize_damage_recipe(context):
    """Randomize impact and gore together and request exactly one preview."""

    global _IMPACT_TRANSACTION_DEPTH, _GORE_TRANSACTION_DEPTH
    settings = context.scene.daf_settings
    previous = (
        int(settings.deformation_impact_seed),
        int(settings.deformation_gore_mask_seed),
    )
    master_seed = secrets.randbelow(parameter_schema.MAX_SEED + 1)
    impact_seed = blueprint_service.derive_subseed(master_seed, "impact")
    gore_seed = blueprint_service.derive_subseed(master_seed, "gore")
    _IMPACT_TRANSACTION_DEPTH += 1
    _GORE_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            settings.deformation_impact_control_mode = "MACRO"
            settings.deformation_gore_control_mode = "MACRO"
            settings.deformation_impact_seed = impact_seed
            settings.deformation_gore_mask_seed = gore_seed
            impact_derived = parameter_schema.derive_impact_parameters(
                _impact_macro_values(settings),
                region_scale=_impact_region_scale(settings),
                family=str(settings.deformation_stamp_family),
                seed=impact_seed,
            )
            region_scale, mean_edge_length = _gore_scale_inputs(
                context,
                settings,
            )
            gore_derived = _derive_complete_gore_parameters(
                context,
                settings,
                identity_id=str(settings.deformation_gore_identity),
                region_scale=region_scale,
                stamp_depth=float(impact_derived["depth"]),
                mean_edge_length=mean_edge_length,
            )
            _assign_impact_derived_values(settings, impact_derived)
            _assign_gore_derived_values(settings, gore_derived)
            _mark_impact_dirty(
                settings, impact_control_metadata(settings, mode="MACRO")
            )
            _mark_gore_dirty(
                settings, gore_control_metadata(settings, mode="MACRO")
            )
    finally:
        _IMPACT_TRANSACTION_DEPTH = max(0, _IMPACT_TRANSACTION_DEPTH - 1)
        _GORE_TRANSACTION_DEPTH = max(0, _GORE_TRANSACTION_DEPTH - 1)
    generation = request_managed_preview(
        context, "complete damage recipe randomized"
    )
    return {
        "masterSeed": master_seed,
        "impactSeed": impact_seed,
        "goreSeed": gore_seed,
        "previousSeeds": previous,
        "generation": generation,
    }


def enter_manual_gore_control(context):
    settings = context.scene.daf_settings
    settings.deformation_gore_control_mode = "MANUAL"
    metadata = gore_control_metadata(settings, mode="MANUAL")
    _mark_gore_dirty(settings, metadata)
    return request_managed_preview(context, "manual gore control enabled")


def return_to_gore_macro_control(context):
    settings = context.scene.daf_settings
    settings.deformation_gore_control_mode = "MACRO"
    return apply_gore_macro_transaction(context, "returned to Gore Pedal macro control")


def enter_manual_impact_control(context):
    settings = context.scene.daf_settings
    settings.deformation_impact_control_mode = 'MANUAL'
    metadata = impact_control_metadata(settings, mode="MANUAL")
    _mark_impact_dirty(settings, metadata)
    generation = request_managed_preview(context, "manual impact control enabled")
    return {"metadata": metadata, "generation": generation}


def fit_impact_macros_to_current_values(context):
    global _IMPACT_TRANSACTION_DEPTH
    settings = context.scene.daf_settings
    fitted = parameter_schema.fit_macros_to_parameters(
        {
            "radius": float(settings.deformation_seed_radius),
            "depth": float(settings.deformation_seed_depth),
            "falloff": float(settings.deformation_seed_falloff),
            "seamProtection": float(settings.deformation_seed_seam_protection),
            "impactChaos": float(settings.deformation_impact_chaos) / 100.0,
            "impactAsymmetry": float(settings.deformation_impact_asymmetry) / 100.0,
        },
        region_scale=_impact_region_scale(settings),
        family=str(settings.deformation_stamp_family),
    )
    _IMPACT_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            settings.deformation_impact_size = fitted["size"]
            settings.deformation_impact_crush = fitted["crush"]
            settings.deformation_impact_profile = fitted["profile"]
            settings.deformation_impact_edge_safety = fitted["edgeSafety"]
            settings.deformation_impact_chaos = fitted["chaos"]
            settings.deformation_impact_asymmetry = fitted["asymmetry"]
            metadata = impact_control_metadata(settings, mode="MANUAL")
            _mark_impact_dirty(settings, metadata)
    finally:
        _IMPACT_TRANSACTION_DEPTH = max(0, _IMPACT_TRANSACTION_DEPTH - 1)
    return {"macros": fitted, "metadata": metadata}


def return_to_macro_control(context):
    settings = context.scene.daf_settings
    settings.deformation_impact_control_mode = 'MACRO'
    return apply_impact_macro_transaction(context, "returned to Impact Pedal macro control")


def _load_impact_control_into_settings(settings, entry, stamp=None):
    """Load additive v1 metadata; legacy recipes remain unmodified CUSTOM data."""

    global _IMPACT_TRANSACTION_DEPTH
    raw = entry.get("impactControl") if isinstance(entry, dict) else None
    if isinstance(raw, dict):
        try:
            metadata = parameter_schema.normalize_impact_control(raw)
        except (TypeError, ValueError):
            metadata = None
    else:
        metadata = None
    if metadata is None:
        stamp = stamp or {}
        fitted = parameter_schema.fit_macros_to_parameters(
            {
                "radius": float(stamp.get("radius", settings.deformation_seed_radius)),
                "depth": float(stamp.get("depth", settings.deformation_seed_depth)),
                "falloff": float(stamp.get("falloff", settings.deformation_seed_falloff)),
                "seamProtection": float(stamp.get("seamProtection", settings.deformation_seed_seam_protection)),
                "impactChaos": float(stamp.get("impactChaos", 0.0)),
                "impactAsymmetry": float(stamp.get("impactAsymmetry", 0.38)),
            },
            region_scale=_impact_region_scale(settings),
            family=str(stamp.get("family", settings.deformation_stamp_family)),
        )
        metadata = parameter_schema.normalize_impact_control({
            "mode": "MANUAL",
            "macros": fitted,
            "seed": int(stamp.get("impactSeed", parameter_schema.DEFAULT_IMPACT_SEED)),
        })
    macros = metadata["macros"]
    _IMPACT_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            settings.deformation_impact_control_mode = str(metadata["mode"])
            settings.deformation_impact_control_version = int(metadata["version"])
            settings.deformation_impact_size = float(macros["size"])
            settings.deformation_impact_crush = float(macros["crush"])
            settings.deformation_impact_profile = float(macros["profile"])
            settings.deformation_impact_edge_safety = float(macros["edgeSafety"])
            settings.deformation_impact_chaos = float(macros["chaos"])
            settings.deformation_impact_asymmetry = float(macros.get("asymmetry", 38.0))
            settings.deformation_impact_seed = int(metadata["seed"])
            settings.deformation_impact_identity = str(metadata["identityDigest"])
            settings.deformation_impact_dirty = False
    finally:
        _IMPACT_TRANSACTION_DEPTH = max(0, _IMPACT_TRANSACTION_DEPTH - 1)
    return metadata


def request_region_switch(region_id, context=None):
    global _PENDING_REGION_ID
    _PENDING_REGION_ID = str(region_id)
    context = context or bpy.context
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is not None and (
        not bool(settings.deformation_auto_preview)
        or not bool(settings.deformation_live_preview)
        or str(settings.deformation_preview_quality) == 'OFF'
    ):
        _apply_pending_region(context)
    return preview_service.request_refresh(context, "region switch")


def _apply_pending_region(context):
    global _PENDING_REGION_ID
    if not _PENDING_REGION_ID:
        return
    region_id = _PENDING_REGION_ID
    _PENDING_REGION_ID = ""
    clear_damage_preview(context, update_status=False)
    if region_id != _active_region_id(context):
        _set_active_region(region_id, context)
    registry, region, attached, _detached = _resolve_active_region(context, region_id)
    _set_active_object(context, attached)
    validation_service.store("active_context", {
        "regionId": region_id,
        "regionMode": _region_mode(region),
        "activeObject": attached.name,
        "validationStatus": region.get("validationStatus", "NOT VALIDATED"),
        "registeredRegionCount": len(registry.get("regions", [])),
    })


def _capture_preview_restore_state(context, attached, detached):
    global _PREVIEW_RESTORE_STATE
    if _PREVIEW_RESTORE_STATE:
        return
    objects = tuple(value for value in (attached, detached) if value is not None)
    _PREVIEW_RESTORE_STATE = {
        "active": getattr(getattr(context.view_layer, "objects", None), "active", None).name
        if getattr(getattr(context.view_layer, "objects", None), "active", None) else "",
        "selected": tuple(obj.name for obj in context.selected_objects),
        "mode": str(getattr(context, "mode", "OBJECT")),
        "objects": {
            obj.name: {
                "hideViewport": bool(obj.hide_viewport),
                "hideRender": bool(obj.hide_render),
                "hideGet": bool(obj.hide_get()),
                "shapeValues": {
                    key.name: float(key.value) for key in obj.data.shape_keys.key_blocks
                } if obj.type == 'MESH' and obj.data.shape_keys else {},
            }
            for obj in objects
        },
    }


def _restore_preview_state(context):
    global _PREVIEW_RESTORE_STATE
    state = _PREVIEW_RESTORE_STATE
    _PREVIEW_RESTORE_STATE = {}
    if not state:
        return
    for object_name, record in state.get("objects", {}).items():
        obj = _object(object_name)
        if obj is None:
            continue
        obj.hide_viewport = bool(record.get("hideViewport", False))
        obj.hide_render = bool(record.get("hideRender", False))
        obj.hide_set(bool(record.get("hideGet", False)))
        if obj.type == 'MESH' and obj.data.shape_keys:
            for key_name, value in record.get("shapeValues", {}).items():
                key = _key(obj, key_name)
                if key is not None:
                    key.value = float(value)
    try:
        if getattr(context, "mode", "OBJECT") != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        for name in state.get("selected", ()):
            obj = _object(name)
            if obj is not None:
                obj.select_set(True)
        context.view_layer.objects.active = _object(state.get("active", ""))
        if state.get("mode", "") == 'SCULPT':
            bpy.ops.object.mode_set(mode='SCULPT')
        elif str(state.get("mode", "")).startswith("EDIT"):
            bpy.ops.object.mode_set(mode='EDIT')
    except Exception:
        pass


def _preview_stamp_stack(context, quality):
    settings, _registry, region, attached, detached, payload, name, entry = _active_key_context(context)
    stored = _active_stamp(settings, entry)
    order_index = int(stored.get("orderIndex", 0))
    current = _stamp_from_settings(context, stamp_id=str(stored["stampId"]), order_index=order_index)
    alternative_mode = str(entry.get("stampMode", "STACK")) == "ALTERNATIVES"
    if quality == "FAST" or alternative_mode:
        stamps = [current]
    else:
        stamps = [
            current if str(stamp.get("stampId", "")) == str(current["stampId"]) else stamp
            for stamp in trauma_field.reindex_stamps(entry.get("stamps", []))
            if stamp.get("enabled", True)
        ]
    weights, distances = _stamp_weights(attached, region, current)
    coordinates = (
        _stamp_local_coordinates_from_inputs(
            attached,
            stamps,
            {str(current["stampId"]): weights},
            {str(current["stampId"]): distances},
        )
        if quality == "FAST" else _stamp_local_coordinates(attached, stamps, region)
    )
    coordinates = _clamp_local_coordinates_to_world_limit(
        attached,
        coordinates,
        settings.deformation_max_vertex_displacement,
    )
    if alternative_mode:
        target = _key(attached, name)
        if target is None:
            raise RuntimeError(f"Damage Key {name!r} is missing.")
        _set_key_coordinates(target, coordinates)
        if detached is not None:
            _sync_exact_index_key_pair(attached, detached, name)
        apply_damage_key_previews(context)
    else:
        clear_damage_preview(context, update_status=False)
        attached, detached, attached_preview, _detached_preview = _ensure_key_pair(PREVIEW_KEY_NAME, preview=True)
        _zero_managed_weights(attached)
        _set_key_coordinates(attached_preview, coordinates)
        if detached is not None:
            _sync_exact_index_key_pair(attached, detached, PREVIEW_KEY_NAME)
        attached_preview.value = 1.0
        attached_preview.slider_max = 1.0
        inspection = 'CORE' if detached is None else 'ATTACHED'
        _set_single_damage_preview_state(
            context,
            region.get("regionId", ""),
            PREVIEW_KEY_NAME,
            1.0,
            inspection,
        )
        _set_authoring_view(attached, detached, inspection, context)

    # The VIP controls are an exploration surface. Build their gore indication
    # from the current unsaved Stamp and macro values instead of leaving an old
    # committed gore mesh visible until Save is pressed.
    preview_key_name = name if alternative_mode else PREVIEW_KEY_NAME
    temporary_entry = copy.deepcopy(entry)
    temporary_entry["stamps"] = trauma_field.reindex_stamps([
        current
        if str(stamp.get("stampId", "")) == str(current["stampId"])
        else stamp
        for stamp in entry.get("stamps", [])
    ])
    temporary_entry["activeStampId"] = str(current["stampId"])
    preview_objects = []
    mask_values = []
    if bool(settings.deformation_gore_enabled):
        overlay = _gore_overlay_from_settings(context)
        temporary_entry["surfaceGoreOverlay"] = overlay
        temporary_entry["goreOverlayDigest"] = (
            trauma_field.gore_overlay_digest(overlay)
        )
        _overlay, mask_values = _install_surface_stain_preview(
            region,
            attached,
            detached,
            payload,
            preview_key_name,
            temporary_entry,
            persist=False,
        )
        if (
            bool(settings.deformation_gore_raised_enabled)
            and overlay["goreGeometryMode"] != "STAIN_ONLY"
            and quality in {"BALANCED", "FINAL"}
        ):
            preview_objects = _build_preview_gore_for_entry(
                region,
                attached,
                detached,
                preview_key_name,
                temporary_entry,
                quality=quality,
            )
        else:
            _remove_preview_gore_objects(
                str(region.get("regionId", "")),
                preview_key_name,
            )
    else:
        _clear_gore_preview_pair(attached, detached)
        _remove_preview_gore_objects(
            str(region.get("regionId", "")),
            preview_key_name,
        )

    # A final mesh from the saved recipe is deliberately hidden while the
    # active recipe is dirty; otherwise it can be mistaken for the current
    # slider result. Other enabled Damage Keys remain untouched.
    for obj in generated_gore_objects(
        str(region.get("regionId", "")),
        name,
    ):
        obj.hide_viewport = False
        obj.hide_set(True)
    inspection_roles = (
        {"CORE"} if detached is None else {"ATTACHED"}
    )
    for obj in preview_objects:
        role = str(obj.get("dsb_gore_pair_role", "")).upper()
        obj.hide_viewport = False
        obj.hide_set(role not in inspection_roles)
    triangle_count = sum(
        int(obj.get("dsb_gore_triangle_count", 0))
        for obj in preview_objects
    )
    if preview_objects:
        message = (
            f"{quality.title()} live deformation + temporary gore geometry ready"
        )
    elif mask_values:
        message = f"{quality.title()} live deformation + gore stain ready"
    else:
        message = f"{quality.title()} live deformation preview ready"
    return {
        "key": name,
        "stampId": current["stampId"],
        "affectedVertexCount": sum(float(value) > 1e-8 for value in weights),
        "goreMaskedVertexCount": sum(
            float(value) > 1e-8 for value in mask_values
        ),
        "previewGoreObjectCount": len(preview_objects),
        "estimatedGoreTriangleCount": triangle_count,
        "finalGoreTriangleCount": 0,
        "message": message,
    }


def _execute_managed_preview(context, quality, _generation):
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if settings is not None and bool(
        getattr(settings, "progression_preview_requested", False)
    ):
        from . import progressive_authoring

        return progressive_authoring.execute_progression_preview(
            context,
            quality,
            _generation,
        )
    _apply_pending_region(context)
    if settings is None or not settings.deformation_active_key or not settings.deformation_seed_center_valid:
        clear_damage_preview(context, update_status=False)
        return {"message": "Select a region, deformation, stamp, and captured surface"}
    result = _preview_stamp_stack(context, quality)
    if quality == "FINAL":
        result["message"] = "Final-quality deterministic preview ready; recipe remains uncommitted"
    return result


def _clear_managed_preview(context, **_flags):
    try:
        from . import progressive_authoring

        settings = getattr(getattr(context, "scene", None), "daf_settings", None)
        if progressive_authoring.preview_session_active() or (
            settings is not None
            and bool(getattr(settings, "progression_preview_active", False))
        ):
            return progressive_authoring.clear_progression_preview(context)
    except ImportError:
        pass
    return clear_damage_preview(context)


def commit_current_tuning(context):
    settings, _registry, region, attached, detached, payload, name, entry = _active_key_context(context)
    objects = tuple(value for value in (attached, detached) if value is not None)
    with transactions.OperationTransaction(
        context,
        "Commit Impact",
        objects=objects,
        metadata_keys=(METADATA_PROPERTY, REGISTRY_PROPERTY),
        coordinate_key_names=(name,),
        ownership_predicate=lambda value: bool(value.get("dsb_generated_role", "") or value.get("dsb_damage_generated", False)),
    ) as transaction:
        transaction.set_stage("persist recipe")
        stored = _active_stamp(settings, entry)
        current = _stamp_from_settings(
            context,
            stamp_id=str(stored["stampId"]),
            order_index=int(stored.get("orderIndex", 0)),
        )
        entry["stamps"] = trauma_field.reindex_stamps([
            current if str(stamp.get("stampId", "")) == str(current["stampId"]) else stamp
            for stamp in entry.get("stamps", [])
        ])
        entry["maximumInfluence"] = float(settings.deformation_maximum_influence)
        entry["maximumDisplacement"] = float(settings.deformation_max_vertex_displacement)
        entry["draftStatus"] = "COMMITTED"
        impact_metadata = impact_control_metadata(settings)
        entry["impactControl"] = impact_metadata
        entry["impactRecipeClass"] = str(impact_metadata["recipeClass"])
        if settings.deformation_gore_enabled:
            overlay = _gore_overlay_from_settings(context)
            entry["surfaceGoreOverlay"] = overlay
            entry["goreOverlayDigest"] = trauma_field.gore_overlay_digest(overlay)
        _store_metadata(attached, detached, payload)
        transaction.set_stage("rebuild final deformation and gore")
        result = rebuild_active_deformation(context)
        refreshed = _metadata(attached).get("keys", {}).get(name, {})
        triangle_counts = refreshed.get("goreTriangleCounts", {})
        result["finalGoreTriangleCount"] = sum(int(value) for value in triangle_counts.values())
        result["affectedVertexCount"] = len(attached.data.vertices)
        settings.deformation_impact_dirty = False
        settings.deformation_impact_identity = str(impact_metadata["identityDigest"])
        if settings.deformation_gore_enabled:
            gore_metadata = gore_control_metadata(settings)
            settings.deformation_gore_dirty = False
            settings.deformation_gore_identity_digest = (
                _combined_gore_identity_digest(settings)
            )
            settings.deformation_gore_validation_status = str(
                result.get("validation", {}).get("status", "NOT_VALIDATED")
            )
        transaction.commit()
        return result


def revert_current_tuning(context):
    settings, _registry, _region, _attached, _detached, _payload, _name, entry = _active_key_context(context)
    stamp = _active_stamp(settings, entry)
    with preview_service.suspend_updates():
        _load_stamp_into_settings(settings, stamp)
        _load_gore_into_settings(settings, entry.get("surfaceGoreOverlay"))
        _load_impact_control_into_settings(settings, entry, stamp)
    return preview_service.request_refresh(context, "reverted to saved recipe")


def _unique_impact_name(attached, entry_names, settings, region_id):
    requested = settings.deformation_impact_semantic_name.strip()
    if requested:
        base = re.sub(r"[^A-Za-z0-9_]+", "_", requested).strip("_")
        if not base:
            raise RuntimeError("Impact Name must contain at least one letter or digit.")
    else:
        base = region_id.replace("_", " ").title().replace(" ", "_") + "_Damage"
    base = base[:52].rstrip("_")
    for version in range(1, 10000):
        candidate = f"{base}_v{version:03d}"
        if candidate not in entry_names and _key(attached, candidate) is None:
            return candidate
    raise RuntimeError("Could not allocate a unique managed impact name.")


def _configure_impact_defaults(context, settings, capture):
    global _IMPACT_TRANSACTION_DEPTH
    # One neutral starting point replaces every factory preset.  The strong
    # macros plus master seed are the intended authoring path.
    macros = (52.0, 56.0, 46.0, 45.0, 42.0, 38.0)
    estimated = float(capture.get("estimatedRadius", 0.0))
    _IMPACT_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            settings.deformation_impact_control_mode = 'MACRO'
            (
                settings.deformation_impact_size,
                settings.deformation_impact_crush,
                settings.deformation_impact_profile,
                settings.deformation_impact_edge_safety,
                settings.deformation_impact_chaos,
                settings.deformation_impact_asymmetry,
            ) = macros
            settings.deformation_capture_mode = str(
                capture.get("placementMode", "SELECTED_FACE_PATCH")
            )
            settings.deformation_gore_enabled = True
            settings.deformation_gore_raised_enabled = True
            settings.deformation_gore_preset = "USER_AUTHORED"
            settings.deformation_gore_inlay_amount = 0.70
            settings.deformation_gore_raised_amount = 0.70
            settings.deformation_gore_exposure = 70.0
            settings.deformation_gore_clot_fill = 52.0
            settings.deformation_gore_breakup = 58.0
            settings.deformation_gore_wetness_macro = 68.0
            settings.deformation_gore_surface_mass = 82.0
            settings.deformation_gore_surface_relief = 68.0
            settings.deformation_gore_nucleus = 32.0
            settings.deformation_gore_lobes = 72.0
            settings.deformation_gore_redness = 88.0
            derived = parameter_schema.derive_impact_parameters(
                macros,
                region_scale=estimated,
                family=str(settings.deformation_stamp_family),
                seed=int(settings.deformation_impact_seed),
            )
            _assign_impact_derived_values(settings, derived)
            settings.deformation_gore_mask_seed = int(settings.deformation_impact_seed)
            gore_derived = _derive_complete_gore_parameters(
                context,
                settings,
                identity_id="BLOODY_CRATER",
                region_scale=estimated,
                stamp_depth=float(derived["depth"]),
                mean_edge_length=max(1e-6, estimated * 0.05),
            )
            _assign_gore_derived_values(settings, gore_derived)
            _mark_impact_dirty(settings, impact_control_metadata(settings, mode="MACRO"))
    finally:
        _IMPACT_TRANSACTION_DEPTH = max(0, _IMPACT_TRANSACTION_DEPTH - 1)


def _capture_current_mesh_selection(context):
    """Capture the current face or vertex selection using Blender's select mode."""

    _registry, _region, attached, _detached = _resolve_active_region(context)
    if context.active_object != attached or context.mode != 'EDIT_MESH':
        raise RuntimeError(
            f"Make {attached.name} active, enter Edit Mode, and select "
            "one vertex, multiple vertices, one face, or one connected face patch."
        )
    mesh = bmesh.from_edit_mesh(attached.data)
    mesh.verts.ensure_lookup_table()
    mesh.faces.ensure_lookup_table()
    selected_vertices = [vertex for vertex in mesh.verts if vertex.select]
    selected_faces = [face for face in mesh.faces if face.select]
    select_mode = tuple(
        bool(value)
        for value in getattr(
            getattr(context, "tool_settings", None),
            "mesh_select_mode",
            (True, False, False),
        )
    )
    face_mode = len(select_mode) >= 3 and bool(select_mode[2])
    vertex_or_edge_mode = bool(select_mode[0]) or (
        len(select_mode) >= 2 and bool(select_mode[1])
    )
    if face_mode and selected_faces:
        return _capture_face_selection(
            context,
            require_single=len(selected_faces) == 1,
        )
    if vertex_or_edge_mode and selected_vertices:
        return _capture_vertex_selection(context)
    if selected_faces:
        return _capture_face_selection(
            context,
            require_single=len(selected_faces) == 1,
        )
    if selected_vertices:
        return _capture_vertex_selection(context)
    raise RuntimeError(
        "Select one vertex, multiple vertices, one face, or one connected "
        "face patch on the active registered mesh."
    )


def create_impact_from_current_selection(context):
    settings = context.scene.daf_settings
    _registry, region, attached, detached = _resolve_active_region(context)
    previous_settings = {
        name: getattr(settings, name) for name in (
            "deformation_active_key", "deformation_active_stamp_id", "deformation_key_name",
            "deformation_capture_json", "deformation_seed_center_valid", "deformation_status",
        )
    }
    try:
        with transactions.OperationTransaction(
            context,
            "Create Impact From Current Selection",
            objects=tuple(value for value in (attached, detached) if value is not None),
            metadata_keys=(
                METADATA_PROPERTY,
                REGISTRY_PROPERTY,
                DAMAGE_PREVIEW_STATE_PROPERTY,
                GORE_PREVIEW_STATE_PROPERTY,
            ),
            property_groups=((settings, "deformation_"),),
            ownership_predicate=lambda value: bool(value.get("dsb_generated_role", "") or value.get("dsb_damage_generated", False)),
        ) as transaction:
            transaction.set_stage("validate current mesh selection")
            settings.deformation_active_key = ""
            settings.deformation_active_stamp_id = ""
            capture = _capture_current_mesh_selection(context)

            transaction.set_stage("configure impact defaults")
            auto = settings.deformation_auto_preview
            settings.deformation_auto_preview = False
            try:
                _configure_impact_defaults(context, settings, capture)
                impact_metadata = impact_control_metadata(settings, mode="MACRO")
                payload = _metadata(attached)
                name = _unique_impact_name(attached, payload.get("keys", {}), settings, str(region.get("regionId", "")))
                settings.deformation_key_name = name
                settings.deformation_active_key = name
                attached, detached, attached_key, detached_key = _ensure_key_pair(name, metadata_entry={
                    "family": str(settings.deformation_stamp_family).lower(),
                    "status": "IMPACT_DRAFT",
                    "recipeStatus": "PROCEDURAL_STACK",
                    "legacy": False,
                    "maximumInfluence": float(settings.deformation_maximum_influence),
                    "maximumDisplacement": float(settings.deformation_max_vertex_displacement),
                    "impactControl": impact_metadata,
                    "previewEnabled": True,
                    "activeStampId": "",
                    "stampMode": "ALTERNATIVES",
                })
                transaction.set_stage("create default trauma stamp")
                stamp = _stamp_from_settings(context, order_index=0)
                settings.deformation_active_stamp_id = str(stamp["stampId"])
                payload = _metadata(attached)
                entry = payload["keys"][name]
                entry["stamps"] = [stamp]
                entry["activeStampId"] = str(stamp["stampId"])
                entry["previewEnabled"] = True
                entry["stampMode"] = "ALTERNATIVES"
                entry["recipeDigest"] = trauma_field.recipe_digest(entry["stamps"])
                entry["status"] = "IMPACT_DRAFT"
                entry["draftStatus"] = "UNCOMMITTED"
                entry["recipeStatus"] = "PROCEDURAL_STACK"
                entry["legacy"] = False
                entry["impactControl"] = impact_metadata
                _store_metadata(attached, detached, payload)
                if settings.deformation_gore_enabled:
                    payload = _metadata(attached)
                    entry = payload["keys"][name]
                    overlay = _gore_overlay_from_settings(context)
                    entry["surfaceGoreOverlay"] = overlay
                    entry["goreOverlayDigest"] = trauma_field.gore_overlay_digest(overlay)
                    entry["raisedGoreStatus"] = "STALE_REBUILD_REQUIRED" if overlay["goreRaisedEnabled"] else "NOT_GENERATED"
                _store_metadata(attached, detached, payload)
                attached_key.value = 0.0
                if detached_key is not None:
                    detached_key.value = 0.0
            finally:
                settings.deformation_auto_preview = auto

            transaction.set_stage("generate FAST preview")
            result = preview_service.run_now(context, quality="FAST")
            if result.get("failed"):
                raise RuntimeError(result.get("error", "FAST preview failed."))
            settings.deformation_status = f"IMPACT DRAFT — {name}"
            transaction.commit()
            return {
                "key": name,
                "stampId": str(stamp["stampId"]),
                "faceCount": len(capture.get("faceIndices", [])),
                "vertexCount": len(capture.get("vertexIndices", [])),
                "placementMode": str(capture.get("placementMode", "")),
                "selectionKind": str(capture.get("selectionKind", "")),
                "preview": result,
                "workflow": (
                    "key selected", "surface captured", "first stamp created",
                    "Impact Pedal recipe applied", "FAST preview generated",
                ),
            }
    except Exception:
        auto = settings.deformation_auto_preview
        settings.deformation_auto_preview = False
        try:
            for name, value in previous_settings.items():
                setattr(settings, name, value)
        finally:
            settings.deformation_auto_preview = auto
        try:
            _refresh_authoring_ui_cache(str(region.get("regionId", "")))
        except Exception:
            validation_service.clear_cache("impact creation rollback")
        raise


def remove_active_draft(context):
    settings, _registry, region, attached, detached, payload, name, entry = _active_key_context(context)
    if str(entry.get("draftStatus", "")) != "UNCOMMITTED":
        return False
    _remove_generated_gore_objects(str(region.get("regionId", "")), name)
    _remove_key(attached, name)
    if detached is not None:
        _remove_key(detached, name)
    payload.get("keys", {}).pop(name, None)
    _store_metadata(attached, detached, payload)
    settings.deformation_active_key = ""
    settings.deformation_active_stamp_id = ""
    settings.deformation_capture_json = ""
    settings.deformation_seed_center_valid = False
    settings.deformation_status = f"DRAFT REMOVED — {name}"
    return True


def update_active_key_metadata(context):
    """Compatibility entry point; metadata writes happen only on explicit commit."""

    return request_managed_preview(context, "active key metadata changed")


def commit_active_key_metadata(context):
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
        for obj in tuple(value for value in (attached, detached) if value is not None):
            block = _key(obj, settings.deformation_active_key)
            if block:
                block.slider_max = float(settings.deformation_maximum_influence)
        _store_metadata(attached, detached, payload)
    except Exception:
        pass


def _select_key(settings, name):
    attached, _detached = _resolve_pair()
    entry = _metadata(attached).get("keys", {}).get(name, {})
    auto_preview = settings.deformation_auto_preview
    settings.deformation_auto_preview = False
    try:
        with preview_service.suspend_updates():
            settings.deformation_active_key = name
            settings.deformation_key_name = name
            settings.deformation_seed_radius = float(entry.get("seedRadius", settings.deformation_seed_radius))
            settings.deformation_seed_depth = float(entry.get("seedDepth", settings.deformation_seed_depth))
            settings.deformation_seed_falloff = float(entry.get("seedFalloff", settings.deformation_seed_falloff))
            settings.deformation_maximum_influence = float(entry.get("maximumInfluence", 1.0))
            settings.deformation_max_vertex_displacement = float(entry.get("maximumDisplacement", 0.045))
            stamps = entry.get("stamps", [])
            settings.deformation_active_stamp_id = ""
            active_stamp = _entry_active_stamp(entry)
            if active_stamp is not None:
                _load_stamp_into_settings(settings, active_stamp)
            _load_gore_into_settings(settings, entry.get("surfaceGoreOverlay"))
            _load_impact_control_into_settings(settings, entry, active_stamp)
    finally:
        settings.deformation_auto_preview = auto_preview


def select_damage_key_stamp(context, key_name, stamp_id):
    """Focus a key and activate exactly one of its child Stamp alternatives."""

    settings = context.scene.daf_settings
    _select_key(settings, str(key_name))
    _registry, _region, attached, detached = _resolve_active_region(context)
    payload = _metadata(attached)
    entry = payload.get("keys", {}).get(str(key_name), {})
    stamp = next(
        (
            value
            for value in entry.get("stamps", [])
            if str(value.get("stampId", "")) == str(stamp_id)
        ),
        None,
    )
    if stamp is None:
        raise RuntimeError("The selected Stamp alternative no longer exists.")
    _load_stamp_into_settings(settings, stamp)
    entry["activeStampId"] = str(stamp["stampId"])
    entry["stampMode"] = "ALTERNATIVES"
    _store_metadata(attached, detached, payload)
    if bool(entry.get("previewEnabled", False)):
        preview_service.run_now(context, quality="FAST")
    settings.deformation_status = (
        f"ACTIVE STAMP — {stamp.get('displayName', stamp_id)}"
    )
    return {"key": str(key_name), "stamp": stamp}


def _load_gore_into_settings(settings, overlay):
    if overlay:
        try:
            recipe = trauma_field.normalize_gore_overlay(overlay)
        except (TypeError, ValueError):
            recipe = trauma_field.default_gore_overlay()
    else:
        recipe = trauma_field.default_gore_overlay()
    settings.deformation_gore_enabled = bool(recipe["goreOverlayEnabled"])
    settings.deformation_gore_preset = str(
        recipe["gorePresetId"]
        if recipe["gorePresetId"] in parameter_schema.GORE_PRESETS
        else "USER_AUTHORED"
    )
    settings.deformation_gore_identity = str(recipe["goreControl"]["identityId"])
    settings.deformation_gore_geometry_mode = str(recipe["goreGeometryMode"])
    settings.deformation_gore_control_mode = str(recipe["goreControl"]["mode"])
    settings.deformation_gore_exposure = float(recipe["goreControl"]["macros"]["exposure"])
    settings.deformation_gore_cavity = float(recipe["goreControl"]["macros"]["cavity"])
    settings.deformation_gore_clot_fill = float(recipe["goreControl"]["macros"]["clotFill"])
    settings.deformation_gore_breakup = float(recipe["goreControl"]["macros"]["breakup"])
    settings.deformation_gore_wetness_macro = float(recipe["goreControl"]["macros"]["wetness"])
    settings.deformation_gore_variation = float(recipe["goreControl"]["macros"]["variation"])
    surface_macros = recipe["goreSurfaceControl"]["macros"]
    settings.deformation_gore_surface_mass = float(
        surface_macros["mass"]
    )
    settings.deformation_gore_surface_relief = float(
        surface_macros["relief"]
    )
    settings.deformation_gore_nucleus = float(
        surface_macros["nucleus"]
    )
    settings.deformation_gore_lobes = float(
        surface_macros["lobes"]
    )
    settings.deformation_gore_redness = float(
        surface_macros["redness"]
    )
    settings.deformation_gore_inlay_amount = float(recipe.get(
        "goreInlayAmount",
        recipe["goreControl"]["macros"]["cavity"] / 100.0,
    ))
    settings.deformation_gore_raised_amount = float(recipe.get(
        "goreRaisedAmount",
        recipe["goreControl"]["macros"]["variation"] / 100.0,
    ))
    settings.deformation_gore_identity_digest = hashlib.sha256(
        (
            str(recipe["goreControl"]["identityDigest"])
            + "|"
            + str(
                recipe["goreSurfaceControl"]["identityDigest"]
            )
        ).encode("ascii")
    ).hexdigest()
    settings.deformation_gore_coverage = float(recipe["goreCoverage"])
    settings.deformation_gore_scatter = float(recipe["goreScatter"])
    settings.deformation_gore_edge_feather = float(recipe["goreEdgeFeather"])
    settings.deformation_gore_wetness = float(recipe["goreWetness"])
    settings.deformation_gore_darkness = float(recipe["goreDarkness"])
    settings.deformation_gore_color_bias = tuple(recipe["goreColorBias"])
    settings.deformation_impact_gore_patch_scale = float(recipe["gorePatchScale"])
    settings.deformation_gore_raised_enabled = bool(recipe["goreRaisedEnabled"])
    settings.deformation_gore_clot_coverage = float(recipe["goreClotCoverage"])
    settings.deformation_gore_core_density = float(recipe["goreCoreDensity"])
    settings.deformation_gore_surface_mass_value = float(
        recipe["goreSurfaceMass"]
    )
    settings.deformation_gore_nucleus_amount = float(
        recipe["goreNucleusAmount"]
    )
    settings.deformation_gore_nucleus_lobes = float(
        recipe["goreNucleusLobes"]
    )
    settings.deformation_gore_clot_thickness = float(recipe["goreClotThickness"])
    settings.deformation_gore_thickness_variation = float(recipe["goreThicknessVariation"])
    settings.deformation_gore_island_breakup = float(recipe["goreIslandBreakup"])
    settings.deformation_gore_peripheral_fragments = float(recipe["gorePeripheralFragments"])
    settings.deformation_gore_surface_offset = float(recipe["goreSurfaceOffset"])
    settings.deformation_gore_geometry_density = float(recipe["goreGeometryDensity"])
    settings.deformation_gore_wetness_variation = float(recipe["goreWetnessVariation"])
    settings.deformation_gore_dark_clot_bias = float(recipe["goreDarkClotBias"])
    settings.deformation_gore_rough_edge_bias = float(recipe["goreRoughEdgeBias"])
    settings.deformation_gore_color_intensity = float(recipe["goreColorIntensity"])
    settings.deformation_gore_organic_irregularity = float(recipe["goreOrganicIrregularity"])
    settings.deformation_gore_surface_roundness = float(recipe["goreSurfaceRoundness"])
    settings.deformation_gore_texture_enabled = bool(recipe["goreTextureEnabled"])
    settings.deformation_gore_fiber_texture_strength = float(recipe["goreFiberTextureStrength"])
    settings.deformation_gore_base_color_strength = float(recipe["goreBaseColorStrength"])
    settings.deformation_gore_inner_rim_enabled = bool(recipe["goreInnerRimEnabled"])
    settings.deformation_gore_inner_rim_width = float(recipe["goreInnerRimWidth"])
    settings.deformation_gore_inner_rim_strength = float(recipe["goreInnerRimStrength"])
    settings.deformation_gore_maximum_triangles = int(recipe["goreMaximumTriangles"])
    settings.deformation_gore_user_customized = bool(recipe["goreUserCustomized"])
    settings.deformation_gore_cavity_depth = float(recipe["goreCavityDepth"])
    settings.deformation_gore_liner_separation = float(recipe["goreLinerSeparation"])
    settings.deformation_gore_rim_width = float(recipe["goreRimWidth"])
    settings.deformation_gore_clot_fill_depth = float(recipe["goreClotFillDepth"])
    settings.deformation_gore_proudness_limit = float(recipe["goreProudnessLimit"])
    settings.deformation_gore_host_deformation_contribution = float(
        recipe["goreHostDeformationContribution"]
    )
    settings.deformation_gore_bone_reveal = float(recipe["goreBoneReveal"])
    settings.deformation_gore_tissue_coverage = float(recipe["goreTissueCoverage"])
    settings.deformation_gore_wound_bed_enabled = bool(recipe["goreWoundBedEnabled"])
    settings.deformation_gore_clot_layer_enabled = bool(recipe["goreClotLayerEnabled"])
    settings.deformation_gore_tissue_layer_enabled = bool(recipe["goreTissueLayerEnabled"])
    settings.deformation_gore_bone_layer_enabled = bool(recipe["goreBoneLayerEnabled"])
    settings.deformation_gore_barrier_layer_enabled = bool(recipe["goreBarrierLayerEnabled"])
    settings.deformation_gore_raised_rim_opt_in = bool(recipe["goreRaisedRimOptIn"])
    settings.deformation_gore_allow_internal_fragments = bool(recipe["goreAllowInternalFragments"])
    settings.deformation_gore_mask_seed = int(recipe["goreMaskSeed"])


def apply_gore_preset_to_settings(context):
    global _GORE_TRANSACTION_DEPTH
    settings = context.scene.daf_settings
    preset_id = settings.deformation_gore_preset
    preset = trauma_field.GORE_PRESETS.get(preset_id)
    if preset is None:
        raise RuntimeError(f"Unknown surface gore preset {preset_id!r}.")
    identity_id = str(preset.get("goreIdentityId", ""))
    if identity_id in parameter_schema.GORE_IDENTITIES:
        defaults = parameter_schema.gore_identity_defaults(identity_id)
        macros = defaults["macros"]
        _GORE_TRANSACTION_DEPTH += 1
        try:
            with preview_service.suspend_updates():
                settings.deformation_gore_identity = identity_id
                settings.deformation_gore_control_mode = "MACRO"
                settings.deformation_gore_exposure = float(macros["exposure"])
                settings.deformation_gore_cavity = float(macros["cavity"])
                settings.deformation_gore_clot_fill = float(macros["clotFill"])
                settings.deformation_gore_breakup = float(macros["breakup"])
                settings.deformation_gore_wetness_macro = float(macros["wetness"])
                settings.deformation_gore_variation = float(macros["variation"])
        finally:
            _GORE_TRANSACTION_DEPTH = max(0, _GORE_TRANSACTION_DEPTH - 1)
        if preview_service.updates_suspended():
            metadata = gore_control_metadata(settings, mode="MACRO")
            region_scale, mean_edge_length = _gore_scale_inputs(context, settings)
            derived = _derive_complete_gore_parameters(
                context,
                settings,
                identity_id=identity_id,
                region_scale=region_scale,
                stamp_depth=float(settings.deformation_seed_depth),
                mean_edge_length=mean_edge_length,
            )
            _GORE_TRANSACTION_DEPTH += 1
            try:
                _assign_gore_derived_values(settings, derived)
                _mark_gore_dirty(settings, metadata)
            finally:
                _GORE_TRANSACTION_DEPTH = max(0, _GORE_TRANSACTION_DEPTH - 1)
            return {"derived": derived, "metadata": metadata, "generation": None}
        return apply_gore_macro_transaction(context, "gore identity changed")
    settings.deformation_gore_coverage = float(preset["goreCoverage"])
    settings.deformation_gore_scatter = float(preset["goreScatter"])
    settings.deformation_gore_edge_feather = float(preset["goreEdgeFeather"])
    settings.deformation_gore_wetness = float(preset["goreWetness"])
    settings.deformation_gore_darkness = float(preset["goreDarkness"])
    settings.deformation_gore_color_bias = tuple(preset["goreColorBias"])
    settings.deformation_impact_gore_patch_scale = float(preset["gorePatchScale"])
    raised = {**trauma_field.RAISED_GORE_DEFAULTS, **{
        key: value for key, value in preset.items()
        if key in trauma_field.RAISED_GORE_DEFAULTS
    }}
    settings.deformation_gore_raised_enabled = bool(raised["goreRaisedEnabled"])
    settings.deformation_gore_clot_coverage = float(raised["goreClotCoverage"])
    settings.deformation_gore_core_density = float(raised["goreCoreDensity"])
    settings.deformation_gore_surface_mass_value = float(
        raised["goreSurfaceMass"]
    )
    settings.deformation_gore_nucleus_amount = float(
        raised["goreNucleusAmount"]
    )
    settings.deformation_gore_nucleus_lobes = float(
        raised["goreNucleusLobes"]
    )
    settings.deformation_gore_clot_thickness = float(raised["goreClotThickness"])
    settings.deformation_gore_thickness_variation = float(raised["goreThicknessVariation"])
    settings.deformation_gore_island_breakup = float(raised["goreIslandBreakup"])
    settings.deformation_gore_peripheral_fragments = float(raised["gorePeripheralFragments"])
    settings.deformation_gore_surface_offset = float(raised["goreSurfaceOffset"])
    settings.deformation_gore_geometry_density = float(raised["goreGeometryDensity"])
    settings.deformation_gore_wetness_variation = float(raised["goreWetnessVariation"])
    settings.deformation_gore_dark_clot_bias = float(raised["goreDarkClotBias"])
    settings.deformation_gore_rough_edge_bias = float(raised["goreRoughEdgeBias"])
    settings.deformation_gore_color_intensity = float(raised["goreColorIntensity"])
    settings.deformation_gore_organic_irregularity = float(raised["goreOrganicIrregularity"])
    settings.deformation_gore_surface_roundness = float(raised["goreSurfaceRoundness"])
    settings.deformation_gore_texture_enabled = bool(raised["goreTextureEnabled"])
    settings.deformation_gore_fiber_texture_strength = float(raised["goreFiberTextureStrength"])
    settings.deformation_gore_base_color_strength = float(raised["goreBaseColorStrength"])
    settings.deformation_gore_inner_rim_enabled = bool(raised["goreInnerRimEnabled"])
    settings.deformation_gore_inner_rim_width = float(raised["goreInnerRimWidth"])
    settings.deformation_gore_inner_rim_strength = float(raised["goreInnerRimStrength"])
    settings.deformation_gore_maximum_triangles = int(raised["goreMaximumTriangles"])
    settings.deformation_gore_geometry_mode = (
        "LEGACY_RAISED" if raised["goreRaisedEnabled"] else "STAIN_ONLY"
    )
    settings.deformation_gore_identity = "BLOODY_CRATER"
    settings.deformation_gore_control_mode = "MANUAL"
    settings.deformation_gore_user_customized = False


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


def _captured_face_component_count(attached, face_indices, virtual_weld=None):
    selected = sorted({int(index) for index in face_indices})
    if not selected:
        return 0
    if virtual_weld is None:
        _positions, virtual_weld = _virtual_weld_context(attached)
    faces = [tuple(attached.data.polygons[index].vertices) for index in selected]
    components = trauma_field.virtual_face_components(faces, virtual_weld["raw_vertex_to_virtual"])
    return len(components)


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
    invalid_faces = any(not isinstance(index, int) or index < 0 or index >= len(attached.data.polygons) for index in face_indices)
    if invalid_faces:
        errors.append("Captured face indices are invalid for the active attached mesh; recapture them.")
    elif placement in {"SINGLE_FACE", "SELECTED_FACE_PATCH"}:
        _positions, virtual_weld = _virtual_weld_context(attached)
        component_count = _captured_face_component_count(attached, face_indices, virtual_weld)
        if component_count != 1:
            errors.append("Captured face patch contains disconnected islands; select one connected patch and recapture it.")
        stored_digest = capture.get("virtualWeldDigest")
        if stored_digest and stored_digest != virtual_weld["digest"]:
            errors.append("Captured virtual weld state is stale; recapture the surface on the current world-space mesh.")
        stored_tolerance = capture.get("virtualWeldTolerance")
        if stored_tolerance is not None:
            try:
                tolerance_matches = math.isclose(
                    float(stored_tolerance),
                    float(virtual_weld["tolerance"]),
                    rel_tol=1e-12,
                    abs_tol=1e-15,
                )
            except (TypeError, ValueError):
                tolerance_matches = False
            if not tolerance_matches:
                errors.append("Captured virtual weld tolerance is stale or invalid; recapture the surface.")
        stored_components = capture.get("virtualConnectedComponentCount")
        if stored_components is not None:
            try:
                components_match = int(stored_components) == component_count
            except (TypeError, ValueError):
                components_match = False
            if not components_match:
                errors.append("Captured virtual face connectivity is stale; recapture the surface.")
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
                overlay = entry.get("surfaceGoreOverlay", {})
                if overlay.get("linkedStampId") == active_id and overlay.get("goreRaisedEnabled", False):
                    entry["raisedGoreStatus"] = "STALE_REBUILD_REQUIRED"
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
    settings, _registry, region, attached, _detached, _payload, _name, entry = _active_key_context(context)
    capture = _capture_payload(settings)
    errors = _capture_errors(capture, region, attached)
    if errors:
        raise RuntimeError(" ".join(errors))
    direction_local = _direction(settings)
    stamp_payload = {
        "stampId": stamp_id or trauma_field.new_stamp_id(),
        "displayName": settings.deformation_stamp_name.strip() or settings.deformation_stamp_family.replace("_", " ").title(),
        "enabled": True,
        "family": settings.deformation_stamp_family,
        "placementMode": capture.get("placementMode", settings.deformation_capture_mode),
        "capture": capture,
        "center": capture.get("centerWorld", (0.0, 0.0, 0.0)),
        "direction": list(_seed_direction_world(settings, attached)),
        "directionMode": settings.deformation_seed_direction_mode,
        "directionLocal": list(direction_local),
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
    }
    if (
        str(settings.deformation_impact_control_mode) == 'MACRO'
        or isinstance((entry or {}).get("impactControl"), dict)
    ):
        stamp_payload.update({
            "impactSeed": int(settings.deformation_impact_seed),
            "impactChaos": float(settings.deformation_impact_chaos) / 100.0,
            "impactEdgeDamage": float(settings.deformation_impact_edge_safety) / 100.0,
            "impactAsymmetry": float(settings.deformation_impact_asymmetry) / 100.0,
            "impactProfile": float(settings.deformation_impact_profile) / 100.0,
            "profileCenterRimBalance": float(settings.deformation_impact_profile) / 100.0,
        })
    return trauma_field.normalize_stamp(stamp_payload)


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
        direction_mode = str(stamp.get("directionMode", ""))
        if direction_mode in trauma_field.DIRECTION_MODES:
            settings.deformation_seed_direction_mode = direction_mode
            if direction_mode == 'CUSTOM_VECTOR' and stamp.get("directionLocal"):
                settings.deformation_seed_custom_direction = tuple(stamp["directionLocal"])
        capture = stamp.get("capture", {})
        if capture:
            settings.deformation_capture_json = json.dumps(capture, sort_keys=True, separators=(",", ":"))
            settings.deformation_seed_center = tuple(capture.get("centerLocal", (0.0, 0.0, 0.0)))
            settings.deformation_seed_surface_normal = tuple(capture.get("normalLocal", (0.0, 0.0, 1.0)))
            settings.deformation_seed_center_valid = True
    finally:
        settings.deformation_auto_preview = auto_preview


def _basis_world_positions(attached):
    _ensure_basis(attached)
    return mesh_snapshot.basis_world_positions(attached)


def _world_vertex_positions(attached):
    return mesh_snapshot.world_positions(attached)


def _virtual_weld_context(attached):
    return mesh_snapshot.virtual_weld_context(attached, trauma_field.build_virtual_weld_map)


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
        positions = mesh_snapshot.world_positions(attached)
        distances = {
            index: (Vector(position) - center).length
            for index, position in enumerate(positions)
            if (Vector(position) - center).length <= maximum_traversal
        }
    else:
        topology = _topology_fingerprint(attached)
        positions, virtual_weld = _virtual_weld_context(attached)
        cache_key = trauma_field.geodesic_cache_key(
            topology,
            f"{attached.name}:{attached.data.name}",
            capture.get("selectionHash", ""),
            distance_mode,
            maximum_traversal,
            virtual_weld["digest"],
            virtual_weld["tolerance"],
        )
        if cache_key not in _GEODESIC_CACHE:
            adjacency_key = (
                topology, f"{attached.name}:{attached.data.name}",
                virtual_weld["digest"], float(virtual_weld["tolerance"]),
            )
            adjacency = _ADJACENCY_CACHE.peek(adjacency_key)
            if adjacency is None:
                adjacency = trauma_field.build_weighted_adjacency(
                    vertex_count,
                    mesh_snapshot.edges(attached),
                    positions,
                    virtual_members=virtual_weld["virtual_members"],
                )
                _ADJACENCY_CACHE[adjacency_key] = adjacency
            _GEODESIC_CACHE[cache_key] = trauma_field.geodesic_distances(adjacency, selected, maximum_traversal)
            _GEODESIC_CACHE_CONTEXT[cache_key] = {
                "topologyFingerprint": topology,
                "objectIdentity": f"{attached.name}:{attached.data.name}",
                "objectName": attached.name,
                "meshDataName": attached.data.name,
                "selectionHash": capture.get("selectionHash", ""),
                "distanceMode": distance_mode,
                "maximumDistance": maximum_traversal,
                "virtualWeldDigest": virtual_weld["digest"],
                "virtualWeldTolerance": virtual_weld["tolerance"],
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
            seam_digest = hashlib.sha256(
                "|".join(
                    f"{point[0]:.9f},{point[1]:.9f},{point[2]:.9f}" for point in seam_points
                ).encode("ascii")
            ).hexdigest()
            factor_key = (
                f"{attached.name}:{attached.data.name}", _topology_fingerprint(attached),
                seam_digest, round(seam_protection, 12),
            )
            factors = _SEAM_FACTOR_CACHE.peek(factor_key)
            if factors is None:
                factors = tuple(
                    _smoothstep(min((Vector(position) - point).length for point in seam_points) / seam_protection)
                    for position in mesh_snapshot.world_positions(attached)
                )
                _SEAM_FACTOR_CACHE[factor_key] = factors
            weights = [value * factors[index] for index, value in enumerate(weights)]
    return tuple(weights), dict(distances)


def _gore_overlay_from_settings(context):
    settings, _registry, region, _attached, _detached, _payload, _name, entry = _active_key_context(context)
    stamp = _active_stamp(settings, entry, require=bool(settings.deformation_gore_enabled))
    existing = entry.get("surfaceGoreOverlay", {})
    capture = stamp.get("capture", {}) if stamp else {}
    geometry_mode = str(settings.deformation_gore_geometry_mode)
    if not settings.deformation_gore_raised_enabled:
        geometry_mode = "STAIN_ONLY"
    elif geometry_mode not in trauma_field.GORE_GEOMETRY_MODES or geometry_mode == "STAIN_ONLY":
        geometry_mode = "CAVITY_INLAY"
    control = gore_control_metadata(settings)
    surface_control = surface_gore_control_metadata(settings)
    recipe = trauma_field.normalize_gore_overlay({
        "goreRecipeVersion": trauma_field.GORE_RECIPE_VERSION,
        "goreOverlayEnabled": bool(settings.deformation_gore_enabled),
        "gorePresetId": "USER_AUTHORED",
        "goreCoverage": float(settings.deformation_gore_coverage),
        "goreScatter": float(settings.deformation_gore_scatter),
        "goreEdgeFeather": float(settings.deformation_gore_edge_feather),
        "goreWetness": float(settings.deformation_gore_wetness),
        "goreDarkness": float(settings.deformation_gore_darkness),
        "goreColorBias": list(settings.deformation_gore_color_bias),
        "gorePatchScale": float(settings.deformation_impact_gore_patch_scale),
        "goreGeometryMode": geometry_mode,
        "goreInlayAmount": float(settings.deformation_gore_inlay_amount),
        "goreRaisedAmount": float(settings.deformation_gore_raised_amount),
        "goreIdentityId": str(control["identityId"]),
        "goreControl": control,
        "goreSurfaceControl": surface_control,
        "goreOverlayMode": "STAIN_AND_RAISED" if geometry_mode != "STAIN_ONLY" else "SURFACE_STAIN",
        "goreIntensityClass": (
            "HIGH" if geometry_mode in {"CAVITY_INLAY", "HYBRID_ADDITIVE"}
            and not settings.deformation_gore_user_customized else "CUSTOM"
        ),
        "goreRaisedEnabled": bool(settings.deformation_gore_raised_enabled),
        "goreClotCoverage": float(settings.deformation_gore_clot_coverage),
        "goreCoreDensity": float(settings.deformation_gore_core_density),
        "goreClotThickness": float(settings.deformation_gore_clot_thickness),
        "goreThicknessVariation": float(settings.deformation_gore_thickness_variation),
        "goreIslandBreakup": float(settings.deformation_gore_island_breakup),
        "gorePeripheralFragments": float(settings.deformation_gore_peripheral_fragments),
        "goreSurfaceOffset": float(settings.deformation_gore_surface_offset),
        "goreGeometryDensity": float(settings.deformation_gore_geometry_density),
        "goreWetnessVariation": float(settings.deformation_gore_wetness_variation),
        "goreDarkClotBias": float(settings.deformation_gore_dark_clot_bias),
        "goreRoughEdgeBias": float(settings.deformation_gore_rough_edge_bias),
        "goreColorIntensity": float(settings.deformation_gore_color_intensity),
        "goreOrganicIrregularity": float(settings.deformation_gore_organic_irregularity),
        "goreSurfaceRoundness": float(settings.deformation_gore_surface_roundness),
        "goreTextureEnabled": bool(settings.deformation_gore_texture_enabled),
        "goreFiberTextureStrength": float(settings.deformation_gore_fiber_texture_strength),
        "goreBaseColorStrength": float(settings.deformation_gore_base_color_strength),
        "goreInnerRimEnabled": bool(settings.deformation_gore_inner_rim_enabled),
        "goreInnerRimWidth": float(settings.deformation_gore_inner_rim_width),
        "goreInnerRimStrength": float(settings.deformation_gore_inner_rim_strength),
        "goreMaximumTriangles": int(settings.deformation_gore_maximum_triangles),
        "goreDefaultVisible": False,
        "goreActivationWeight": 0.01,
        "goreUserCustomized": bool(settings.deformation_gore_user_customized),
        "goreCavityDepth": float(settings.deformation_gore_cavity_depth),
        "goreLinerSeparation": float(settings.deformation_gore_liner_separation),
        "goreRimWidth": float(settings.deformation_gore_rim_width),
        "goreClotFillDepth": float(settings.deformation_gore_clot_fill_depth),
        "goreProudnessLimit": float(settings.deformation_gore_proudness_limit),
        "goreHostDeformationContribution": float(
            settings.deformation_gore_host_deformation_contribution
        ),
        "goreBoneReveal": float(settings.deformation_gore_bone_reveal),
        "goreTissueCoverage": float(settings.deformation_gore_tissue_coverage),
        "goreWoundBedEnabled": bool(settings.deformation_gore_wound_bed_enabled),
        "goreClotLayerEnabled": bool(settings.deformation_gore_clot_layer_enabled),
        "goreTissueLayerEnabled": bool(settings.deformation_gore_tissue_layer_enabled),
        "goreBoneLayerEnabled": bool(settings.deformation_gore_bone_layer_enabled),
        "goreBarrierLayerEnabled": bool(settings.deformation_gore_barrier_layer_enabled),
        "goreRaisedRimOptIn": bool(settings.deformation_gore_raised_rim_opt_in),
        "goreAllowInternalFragments": bool(settings.deformation_gore_allow_internal_fragments),
        "goreSurfaceMass": float(
            settings.deformation_gore_surface_mass_value
        ),
        "goreNucleusAmount": float(
            settings.deformation_gore_nucleus_amount
        ),
        "goreNucleusLobes": float(
            settings.deformation_gore_nucleus_lobes
        ),
        "goreMaskSeed": int(settings.deformation_gore_mask_seed),
        "linkedRegionId": region.get("regionId", existing.get("linkedRegionId", "")),
        "linkedStampId": stamp.get("stampId", existing.get("linkedStampId", "")) if stamp else existing.get("linkedStampId", ""),
        "linkedSelectionHash": capture.get("selectionHash", existing.get("linkedSelectionHash", "")),
        "linkedCaptureTopologyFingerprint": capture.get(
            "topologyFingerprint", existing.get("linkedCaptureTopologyFingerprint", "")
        ),
        "validationStatus": "NOT_VALIDATED",
    })
    return recipe


def update_surface_gore_overlay(context):
    settings, _registry, _region, attached, detached, payload, name, entry = _active_key_context(context)
    clear_surface_gore_preview()
    overlay = _gore_overlay_from_settings(context)
    entry["surfaceGoreOverlay"] = overlay
    entry["goreOverlayDigest"] = trauma_field.gore_overlay_digest(overlay)
    if overlay["goreRaisedEnabled"]:
        entry["raisedGoreStatus"] = "STALE_REBUILD_REQUIRED"
    _store_metadata(attached, detached, payload)
    settings.deformation_status = (
        f"SURFACE GORE {'ENABLED' if overlay['goreOverlayEnabled'] else 'DISABLED'} — {name}"
    )
    return overlay


def _stamp_local_coordinates(attached, stamps, region=None):
    if region is None:
        _registry, region, _active, _detached = _resolve_active_region()
    weights_by_stamp = {}
    distances_by_stamp = {}
    for stamp in stamps:
        weights, distances = _stamp_weights(attached, region, stamp)
        weights_by_stamp[str(stamp["stampId"])] = weights
        distances_by_stamp[str(stamp["stampId"])] = distances
    return _stamp_local_coordinates_from_inputs(attached, stamps, weights_by_stamp, distances_by_stamp)


def _stamp_local_coordinates_from_inputs(attached, stamps, weights_by_stamp, distances_by_stamp):
    basis_world = _basis_world_positions(attached)
    final_world = trauma_field.evaluate_stamp_stack(basis_world, stamps, weights_by_stamp, distances_by_stamp)
    inverse_world = attached.matrix_world.inverted()
    return [inverse_world @ Vector(position) for position in final_world]


def _clamp_local_coordinates_to_world_limit(
    attached,
    coordinates,
    maximum_displacement,
):
    """Project generated coordinates into the recipe's final world-space cap."""

    coordinates = list(coordinates)
    basis_world = _basis_world_positions(attached)
    if len(coordinates) != len(basis_world):
        raise RuntimeError(
            "Generated coordinate count does not match the active Basis."
        )
    maximum = float(maximum_displacement)
    if not math.isfinite(maximum) or maximum <= 0.0:
        raise RuntimeError(
            "Maximum world displacement must be a finite positive value."
        )
    world = attached.matrix_world
    inverse_world = world.inverted()
    result = []
    for basis_position, coordinate in zip(basis_world, coordinates):
        basis_position = Vector(basis_position)
        generated_world = world @ Vector(coordinate)
        delta = generated_world - basis_position
        if not all(math.isfinite(float(value)) for value in delta):
            raise RuntimeError(
                "Generated deformation contains a non-finite displacement."
            )
        if delta.length > maximum:
            delta.normalize()
            delta *= maximum
            generated_world = basis_position + delta
        result.append(inverse_world @ generated_world)
    return result


def _portable_direction_fields(attached, stamp):
    capture = stamp.get("capture", {})
    mode = str(stamp.get("directionMode", ""))
    local = stamp.get("directionLocal")
    if mode in trauma_field.DIRECTION_MODES and local:
        direction_local = Vector(local)
        if direction_local.length_squared > 1e-12:
            return mode, direction_local.normalized()

    direction_world = Vector(stamp.get("direction", (0.0, 0.0, -1.0)))
    if direction_world.length_squared <= 1e-12:
        raise RuntimeError(f"Stamp {stamp.get('displayName', stamp.get('stampId'))} has no usable direction.")
    direction_world.normalize()
    normal_world = Vector(capture.get("normalWorld", (0.0, 0.0, 0.0)))
    normal_local = Vector(capture.get("normalLocal", (0.0, 0.0, 0.0)))
    if normal_world.length_squared > 1e-12 and normal_local.length_squared > 1e-12:
        normal_world.normalize()
        normal_local.normalize()
        alignment = direction_world.dot(normal_world)
        if alignment >= 1.0 - 1e-5:
            return 'OUTWARD_SURFACE_NORMAL', normal_local
        if alignment <= -1.0 + 1e-5:
            return 'INWARD_SURFACE_NORMAL', -normal_local
    direction_local = _world_delta_to_local(attached, direction_world)
    if direction_local.length_squared <= 1e-12:
        raise RuntimeError(f"Stamp {stamp.get('displayName', stamp.get('stampId'))} has no usable local direction.")
    return 'CUSTOM_VECTOR', direction_local.normalized()


def _portable_stamp(attached, stamp):
    portable = copy.deepcopy(dict(stamp))
    capture = copy.deepcopy(dict(portable.get("capture", {})))
    vertex_indices = sorted({int(index) for index in capture.get("vertexIndices", [])})
    face_indices = sorted({int(index) for index in capture.get("faceIndices", [])})
    if any(index < 0 or index >= len(attached.data.vertices) for index in vertex_indices):
        raise RuntimeError("A trauma stamp contains a vertex outside the current attached mesh.")
    if any(index < 0 or index >= len(attached.data.polygons) for index in face_indices):
        raise RuntimeError("A trauma stamp contains a face outside the current attached mesh.")
    capture["portableVertexAnchorsLocal"] = [
        list(attached.data.vertices[index].co) for index in vertex_indices
    ]
    capture["portableVertexAnchorsWorld"] = [
        list(attached.matrix_world @ attached.data.vertices[index].co) for index in vertex_indices
    ]
    capture["portableFaceAnchorsLocal"] = [
        [list(attached.data.vertices[index].co) for index in attached.data.polygons[face_index].vertices]
        for face_index in face_indices
    ]
    capture["portableFaceAnchorsWorld"] = [
        [list(attached.matrix_world @ attached.data.vertices[index].co) for index in attached.data.polygons[face_index].vertices]
        for face_index in face_indices
    ]
    capture["portableSourceTopologyFingerprint"] = _topology_fingerprint(attached)
    capture["portableSourceVertexCount"] = len(attached.data.vertices)
    capture["portableSourcePolygonCount"] = len(attached.data.polygons)
    portable["capture"] = capture
    mode, direction_local = _portable_direction_fields(attached, portable)
    portable["directionMode"] = mode
    portable["directionLocal"] = list(direction_local)
    return trauma_field.normalize_stamp(portable)


def _map_capture_indices_from_anchors(attached, capture):
    placement = str(capture.get("placementMode", ""))
    anchor_spaces = (
        (
            "LOCAL",
            [tuple(vertex.co) for vertex in attached.data.vertices],
            capture.get("portableVertexAnchorsLocal", []),
            capture.get("portableFaceAnchorsLocal", []),
        ),
        (
            "WORLD",
            [tuple(attached.matrix_world @ vertex.co) for vertex in attached.data.vertices],
            capture.get("portableVertexAnchorsWorld", []),
            capture.get("portableFaceAnchorsWorld", []),
        ),
    )
    attempts = []
    selected_space = None
    target_positions = []
    vertex_anchors = []
    face_anchors = []
    vertex_match = None
    for space, positions, saved_vertices, saved_faces in anchor_spaces:
        if not saved_vertices:
            continue
        tolerance = trauma_field.portable_anchor_tolerance(positions)
        candidate = trauma_field.match_positional_anchors(positions, saved_vertices, tolerance=tolerance)
        attempts.append((space, candidate))
        if not candidate["unmatched_anchor_indices"]:
            selected_space = space
            target_positions = positions
            vertex_anchors = saved_vertices
            face_anchors = saved_faces
            vertex_match = candidate
            break
    if not attempts:
        raise RuntimeError(
            "The saved capture uses different topology and has no analytical positional anchors. "
            "Recapture it on the current attached mesh."
        )
    if vertex_match is None:
        _space, best_match = min(attempts, key=lambda item: len(item[1]["unmatched_anchor_indices"]))
        raise RuntimeError(
            "The saved capture does not analytically match this mesh: "
            f"{len(best_match['unmatched_anchor_indices'])} vertex anchors are outside the conservative "
            f"{float(best_match['tolerance']):.9g} quantization tolerance."
        )

    if placement not in {'SINGLE_FACE', 'SELECTED_FACE_PATCH'}:
        mapped_vertices = sorted({
            int(index)
            for candidates in vertex_match["matches"]
            for index in candidates
        })
        if not mapped_vertices:
            raise RuntimeError("The saved capture has no analytically matching vertices on the current mesh.")
        return [], mapped_vertices, float(vertex_match["tolerance"]), selected_space

    if not face_anchors:
        raise RuntimeError("The saved face capture has no analytical face anchors.")
    mapped_faces = set()
    for saved_face_index, saved_face in enumerate(face_anchors):
        face_match = trauma_field.match_positional_anchors(
            target_positions,
            saved_face,
            tolerance=float(vertex_match["tolerance"]),
        )
        if face_match["unmatched_anchor_indices"]:
            raise RuntimeError(
                f"Saved face anchor {saved_face_index} does not analytically match the current mesh."
            )
        anchor_groups = [set(int(index) for index in candidates) for candidates in face_match["matches"]]
        candidates = []
        for polygon in attached.data.polygons:
            polygon_vertices = set(int(index) for index in polygon.vertices)
            if len(polygon.vertices) != len(anchor_groups):
                continue
            if all(polygon_vertices & group for group in anchor_groups) and all(
                any(vertex_index in group for group in anchor_groups)
                for vertex_index in polygon_vertices
            ):
                candidates.append(int(polygon.index))
        if not candidates:
            raise RuntimeError(
                f"Saved face anchor {saved_face_index} has no exact positional face on the current mesh."
            )
        mapped_faces.update(candidates)
    mapped_vertices = sorted({
        int(index)
        for face_index in mapped_faces
        for index in attached.data.polygons[face_index].vertices
    })
    return sorted(mapped_faces), mapped_vertices, float(vertex_match["tolerance"]), selected_space


def _rebind_library_capture(attached, region, capture):
    rebound = copy.deepcopy(dict(capture))
    placement = str(rebound.get("placementMode", ""))
    selection_kind = "FACE" if placement in {'SINGLE_FACE', 'SELECTED_FACE_PATCH'} else "VERTEX"
    face_indices = sorted({int(index) for index in rebound.get("faceIndices", [])})
    vertex_indices = sorted({int(index) for index in rebound.get("vertexIndices", [])})
    topology = _topology_fingerprint(attached)
    source_topology = str(rebound.get("topologyFingerprint", ""))
    indices_valid = (
        all(0 <= index < len(attached.data.vertices) for index in vertex_indices)
        and all(0 <= index < len(attached.data.polygons) for index in face_indices)
    )
    if source_topology != topology or not indices_valid:
        face_indices, vertex_indices, anchor_tolerance, anchor_space = _map_capture_indices_from_anchors(attached, rebound)
        rebound["portableBindingMode"] = "ANALYTICAL_POSITIONAL_ANCHORS"
        rebound["portableAnchorTolerance"] = anchor_tolerance
        rebound["portableAnchorSpace"] = anchor_space
        rebound["portableSourceTopologyFingerprint"] = source_topology
    else:
        rebound["portableBindingMode"] = "EXACT_TOPOLOGY"
    rebound["regionId"] = region.get("regionId", "")
    rebound["attachedObject"] = attached.name
    rebound["topologyFingerprint"] = topology
    rebound["selectionKind"] = selection_kind
    rebound["faceIndices"] = face_indices
    rebound["vertexIndices"] = vertex_indices
    selected_indices = face_indices if selection_kind == "FACE" else vertex_indices
    rebound["selectionHash"] = trauma_field.selection_hash(selected_indices, topology, selection_kind)

    center_local = Vector(rebound.get("centerLocal", (0.0, 0.0, 0.0)))
    normal_local = Vector(rebound.get("normalLocal", (0.0, 0.0, 1.0)))
    if normal_local.length_squared <= 1e-12:
        raise RuntimeError("A saved stamp capture has no usable local surface normal.")
    normal_local.normalize()
    center_world, bounds_world, estimated_radius = _capture_bounds_and_radius(attached, vertex_indices, center_local)
    rebound["centerLocal"] = list(center_local)
    rebound["centerWorld"] = list(center_world)
    rebound["normalLocal"] = list(normal_local)
    rebound["normalWorld"] = list(_normal_local_to_world(attached, normal_local))
    rebound["boundsWorld"] = bounds_world
    rebound["estimatedRadius"] = estimated_radius

    if placement in {'SINGLE_FACE', 'SELECTED_FACE_PATCH'}:
        _positions, virtual_weld = _virtual_weld_context(attached)
        component_count = _captured_face_component_count(attached, face_indices, virtual_weld)
        rebound["connectedComponentCount"] = component_count
        rebound["virtualWeldTolerance"] = virtual_weld["tolerance"]
        rebound["virtualWeldDigest"] = virtual_weld["digest"]
        rebound["virtualWeldMemberCount"] = sum(
            len(group) for group in virtual_weld["virtual_members"] if len(group) > 1
        )
        rebound["virtualConnectedComponentCount"] = component_count
    else:
        for field in (
            "virtualWeldTolerance", "virtualWeldDigest", "virtualWeldMemberCount",
            "virtualConnectedComponentCount",
        ):
            rebound.pop(field, None)
    return rebound


def _rebind_library_stamp(attached, region, stamp):
    rebound = copy.deepcopy(dict(stamp))
    capture = _rebind_library_capture(attached, region, rebound.get("capture", {}))
    rebound["capture"] = capture
    rebound["placementMode"] = capture.get("placementMode")
    rebound["center"] = list(capture.get("centerWorld", (0.0, 0.0, 0.0)))
    mode, direction_local = _portable_direction_fields(attached, rebound)
    rebound["directionMode"] = mode
    rebound["directionLocal"] = list(direction_local)
    if mode == 'INWARD_SURFACE_NORMAL':
        rebound["direction"] = list(-Vector(capture["normalWorld"]))
        rebound["directionLocal"] = list(-Vector(capture["normalLocal"]))
    elif mode == 'OUTWARD_SURFACE_NORMAL':
        rebound["direction"] = list(Vector(capture["normalWorld"]))
        rebound["directionLocal"] = list(Vector(capture["normalLocal"]))
    else:
        direction_world = _linear_world_matrix(attached) @ direction_local
        if direction_world.length_squared <= 1e-12:
            raise RuntimeError("A saved stamp direction cannot be transformed onto the current attached mesh.")
        rebound["direction"] = list(direction_world.normalized())
    normalized = trauma_field.normalize_stamp(rebound)
    errors = _capture_errors(normalized.get("capture", {}), region, attached)
    if errors:
        raise RuntimeError(" ".join(errors))
    return normalized


def build_current_stamp_library():
    """Collect every procedural stamp stack without requiring the source mesh."""

    registry = _load_registry()
    region_records = []
    for region in registry.get("regions", []):
        attached, detached = _resolve_region_pair(region)
        contract = validate_region_contract(region, attached, detached)
        if contract["status"] != "PASS":
            raise RuntimeError(f"Region {region.get('regionId')}: {' '.join(contract['errors'])}")
        payload = _metadata(attached)
        key_records = []
        for name, entry in sorted(payload.get("keys", {}).items()):
            raw_stamps = entry.get("stamps", [])
            if not raw_stamps:
                continue
            portable_stamps = [
                _rebind_library_stamp(attached, region, _portable_stamp(attached, stamp))
                for stamp in trauma_field.ordered_stamps(raw_stamps)
            ]
            key_records.append({
                "name": name,
                "family": entry.get("family", "manual"),
                "side": entry.get("side", "configurable"),
                "mirrorPartner": entry.get("mirrorPartner", ""),
                "maximumInfluence": entry.get("maximumInfluence", 1.0),
                "maximumDisplacement": entry.get("maximumDisplacement", 0.045),
                "seedRadius": entry.get("seedRadius", 0.055),
                "seedDepth": entry.get("seedDepth", 0.016),
                "seedFalloff": entry.get("seedFalloff", 2.2),
                "recipeDigest": trauma_field.recipe_digest(portable_stamps),
                "stamps": portable_stamps,
            })
            if isinstance(entry.get("impactControl"), dict):
                key_records[-1]["impactControl"] = parameter_schema.normalize_impact_control(
                    entry["impactControl"]
                )
            if "surfaceGoreOverlay" in entry:
                portable_overlay = trauma_field.normalize_gore_overlay(entry["surfaceGoreOverlay"])
                key_records[-1]["surfaceGoreOverlay"] = portable_overlay
                key_records[-1]["goreOverlayDigest"] = trauma_field.gore_overlay_digest(portable_overlay)
        if key_records:
            region_records.append({
                "regionId": region.get("regionId", ""),
                "regionMode": _region_mode(region),
                "sourceTargetObject": attached.name,
                "sourceAttachedObject": attached.name,
                "sourceDetachedObject": detached.name if detached is not None else "",
                "topologyFingerprint": contract["topologyFingerprint"],
                "weightFingerprint": _weight_fingerprint(attached),
                "vertexCount": contract["attachedVertexCount"],
                "polygonCount": contract["attachedPolygonCount"],
                "relatedSeamId": region.get("relatedSeamId", ""),
                "keys": key_records,
            })
    if not region_records:
        raise RuntimeError("No authored trauma stamps were found. Add at least one stamp before saving a library.")
    return trauma_field.build_stamp_library(
        region_records,
        _version_string(),
        DEFORMATION_BUILD_ID,
        compound_events=registry.get("compoundEvents", []),
    )


def save_stamp_library(filepath):
    path = Path(filepath)
    if not str(path).lower().endswith(".dsbstamps.json"):
        path = Path(str(path) + ".dsbstamps.json")
    library = build_current_stamp_library()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(library, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path, library


def _semantic_anchor_for_region(region_id):
    value = str(region_id or "").upper()
    if "HEAD" in value:
        if "LEFT" in value:
            return "HEAD_LEFT"
        if "RIGHT" in value:
            return "HEAD_RIGHT"
        return "HEAD"
    if "FOREARM" in value or "ARM" in value:
        if "LEFT" in value:
            return "FOREARM_LEFT"
        if "RIGHT" in value:
            return "FOREARM_RIGHT"
        return "CUSTOM"
    if any(token in value for token in ("BODY", "TORSO", "CORE")):
        return "BODY"
    return "CUSTOM"


def _current_damage_blueprint(context, name):
    settings, _registry, region, _attached, _detached, _payload, _key_name, entry = (
        _active_key_context(context)
    )
    stored = _active_stamp(settings, entry)
    current = _stamp_from_settings(
        context,
        stamp_id=str(stored["stampId"]),
        order_index=int(stored.get("orderIndex", 0)),
    )
    current = dict(current)
    current["maximumInfluence"] = float(
        settings.deformation_maximum_influence
    )
    return blueprint_service.build_blueprint(
        name,
        impact_macros={
            "area": float(settings.deformation_impact_size),
            "depth": float(settings.deformation_impact_crush),
            "falloff": float(settings.deformation_impact_profile),
            "edgeDamage": float(settings.deformation_impact_edge_safety),
            "distortion": float(settings.deformation_impact_chaos),
            "asymmetry": float(settings.deformation_impact_asymmetry),
        },
        impact_seed=int(settings.deformation_impact_seed),
        gore_macros={
            "coverage": float(settings.deformation_gore_exposure),
            "raised": float(settings.deformation_gore_raised_amount) * 100.0,
            "inlay": float(settings.deformation_gore_inlay_amount) * 100.0,
            "breakup": float(settings.deformation_gore_breakup),
            "fill": float(settings.deformation_gore_clot_fill),
            "wetness": float(settings.deformation_gore_wetness_macro),
        },
        surface_gore_macros={
            "mass": float(settings.deformation_gore_surface_mass),
            "relief": float(
                settings.deformation_gore_surface_relief
            ),
            "nucleus": float(settings.deformation_gore_nucleus),
            "folds": float(settings.deformation_gore_lobes),
            "redness": float(settings.deformation_gore_redness),
        },
        gore_seed=int(settings.deformation_gore_mask_seed),
        stamp=current,
        gore_enabled=bool(settings.deformation_gore_enabled),
        gore_identity_id=str(settings.deformation_gore_identity),
        texture_enabled=bool(settings.deformation_gore_texture_enabled),
        fiber_texture_strength=float(settings.deformation_gore_fiber_texture_strength),
        base_color_strength=float(settings.deformation_gore_base_color_strength),
        semantic_anchor=_semantic_anchor_for_region(region.get("regionId", "")),
    )


def save_active_damage_blueprint(context):
    """Upsert the focused key/stamp/gore intent as a portable adaptive recipe."""

    settings = context.scene.daf_settings
    name = str(settings.deformation_blueprint_name or "").strip()
    if not name:
        name = str(
            settings.deformation_stamp_name or settings.deformation_active_key or ""
        ).strip()
    if not name:
        raise RuntimeError("Name the Damage Blueprint before saving it.")
    blueprint = _current_damage_blueprint(context, name)
    path = _blueprint_library_path(settings)
    library = (
        refresh_blueprint_library(context)
        if path.exists()
        else blueprint_service.normalize_library()
    )
    library = blueprint_service.upsert_blueprint(library, blueprint)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(library, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    _cache_blueprint_library(path, library)
    settings.deformation_blueprint_name = str(blueprint["name"])
    settings.deformation_status = f"DAMAGE BLUEPRINT SAVED — {blueprint['name']}"
    return path, blueprint


def apply_damage_blueprint(context, blueprint_id):
    """Bind portable intent to the focused stamp's fresh destination capture."""

    global _IMPACT_TRANSACTION_DEPTH, _GORE_TRANSACTION_DEPTH
    settings, _registry, region, attached, detached, payload, key_name, entry = (
        _active_key_context(context)
    )
    active = _active_stamp(settings, entry)
    capture = dict(active.get("capture", {}))
    errors = _capture_errors(capture, region, attached)
    if errors:
        raise RuntimeError(
            "A Damage Blueprint needs a fresh valid destination capture. "
            + " ".join(errors)
        )
    library = refresh_blueprint_library(context)
    try:
        blueprint = blueprint_service.blueprint_by_id(library, blueprint_id)
    except KeyError as exc:
        raise RuntimeError(str(exc)) from exc
    impact = blueprint["impact"]
    gore = blueprint["gore"]
    impact_macros = impact["macros"]
    gore_macros = gore["macros"]
    surface_gore_macros = gore["surfaceMacros"]
    destination_scale = float(
        capture.get("estimatedRadius", settings.deformation_seed_radius)
    )
    adaptive = blueprint_service.adaptive_stamp_values(
        blueprint, destination_scale
    )
    _IMPACT_TRANSACTION_DEPTH += 1
    _GORE_TRANSACTION_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            settings.deformation_impact_control_mode = "MACRO"
            settings.deformation_gore_control_mode = "MACRO"
            settings.deformation_impact_size = float(impact_macros["area"])
            settings.deformation_impact_crush = float(impact_macros["depth"])
            settings.deformation_impact_profile = float(impact_macros["falloff"])
            settings.deformation_impact_edge_safety = float(
                impact_macros["edgeDamage"]
            )
            settings.deformation_impact_chaos = float(
                impact_macros["distortion"]
            )
            settings.deformation_impact_asymmetry = float(
                impact_macros["asymmetry"]
            )
            settings.deformation_impact_seed = int(impact["seed"])
            settings.deformation_gore_exposure = float(gore_macros["coverage"])
            settings.deformation_gore_raised_amount = (
                float(gore_macros["raised"]) / 100.0
            )
            settings.deformation_gore_inlay_amount = (
                float(gore_macros["inlay"]) / 100.0
            )
            settings.deformation_gore_breakup = float(gore_macros["breakup"])
            settings.deformation_gore_clot_fill = float(gore_macros["fill"])
            settings.deformation_gore_wetness_macro = float(
                gore_macros["wetness"]
            )
            settings.deformation_gore_surface_mass = float(
                surface_gore_macros["mass"]
            )
            settings.deformation_gore_surface_relief = float(
                surface_gore_macros["relief"]
            )
            settings.deformation_gore_nucleus = float(
                surface_gore_macros["nucleus"]
            )
            settings.deformation_gore_lobes = float(
                surface_gore_macros["folds"]
            )
            settings.deformation_gore_redness = float(
                surface_gore_macros["redness"]
            )
            settings.deformation_gore_mask_seed = int(gore["seed"])
            settings.deformation_gore_enabled = bool(gore["enabled"])
            settings.deformation_gore_identity = str(gore["identityId"])
            settings.deformation_gore_texture_enabled = bool(
                gore["textureEnabled"]
            )
            settings.deformation_gore_fiber_texture_strength = float(
                gore["fiberTextureStrength"]
            )
            settings.deformation_gore_base_color_strength = float(
                gore["baseColorStrength"]
            )
            settings.deformation_seed_direction_mode = str(
                adaptive["directionMode"]
            )
            settings.deformation_seed_custom_direction = tuple(
                adaptive["directionLocal"]
            )
            settings.deformation_influence_mode = str(
                adaptive["influenceMode"]
            )
            settings.deformation_distance_mode = str(adaptive["distanceMode"])
            settings.deformation_stamp_family = str(adaptive["family"])
            settings.deformation_stamp_name = str(blueprint["name"])
            settings.deformation_gore_preset = "USER_AUTHORED"
            impact_derived = parameter_schema.derive_impact_parameters(
                _impact_macro_values(settings),
                region_scale=destination_scale,
                family=str(settings.deformation_stamp_family),
                seed=int(impact["seed"]),
            )
            region_scale, mean_edge_length = _gore_scale_inputs(context, settings)
            gore_derived = _derive_complete_gore_parameters(
                context,
                settings,
                identity_id=str(settings.deformation_gore_identity),
                region_scale=region_scale,
                stamp_depth=float(adaptive["depth"]),
                mean_edge_length=mean_edge_length,
            )
            _assign_impact_derived_values(settings, impact_derived)
            # Portable ratios author the physical size at the new capture.
            settings.deformation_seed_radius = float(adaptive["radius"])
            settings.deformation_seed_depth = float(adaptive["depth"])
            settings.deformation_feather_distance = float(
                adaptive["featherDistance"]
            )
            settings.deformation_stamp_strength = float(adaptive["strength"])
            settings.deformation_seed_falloff = float(adaptive["falloff"])
            settings.deformation_seed_seam_protection = float(
                adaptive["seamProtection"]
            )
            settings.deformation_max_vertex_displacement = float(
                adaptive["maximumDisplacement"]
            )
            settings.deformation_maximum_influence = float(
                adaptive["maximumInfluence"]
            )
            _assign_gore_derived_values(settings, gore_derived)
            _mark_impact_dirty(
                settings, impact_control_metadata(settings, mode="MACRO")
            )
            _mark_gore_dirty(
                settings, gore_control_metadata(settings, mode="MACRO")
            )
    finally:
        _IMPACT_TRANSACTION_DEPTH = max(0, _IMPACT_TRANSACTION_DEPTH - 1)
        _GORE_TRANSACTION_DEPTH = max(0, _GORE_TRANSACTION_DEPTH - 1)

    replacement = _stamp_from_settings(
        context,
        stamp_id=str(active["stampId"]),
        order_index=int(active.get("orderIndex", 0)),
    )
    replacement["displayName"] = str(blueprint["name"])
    entry["stamps"] = trauma_field.reindex_stamps([
        replacement
        if str(stamp.get("stampId", "")) == str(active["stampId"])
        else stamp
        for stamp in entry.get("stamps", [])
    ])
    entry["activeStampId"] = str(replacement["stampId"])
    entry["stampMode"] = "ALTERNATIVES"
    entry["impactControl"] = impact_control_metadata(settings, mode="MACRO")
    entry["surfaceGoreOverlay"] = _gore_overlay_from_settings(context)
    entry["blueprintId"] = str(blueprint["blueprintId"])
    entry["blueprintDigest"] = str(blueprint["blueprintDigest"])
    entry["previewEnabled"] = True
    _store_metadata(attached, detached, payload)
    result = rebuild_active_deformation(context)
    settings.deformation_status = (
        f"DAMAGE BLUEPRINT APPLIED — {blueprint['name']} / "
        f"{region.get('regionId', '')}"
    )
    return {"blueprint": blueprint, "key": key_name, "rebuild": result}


def load_stamp_library(filepath, context):
    """Load by exact topology or conservative positional anchors; never overwrite work."""

    path = Path(filepath)
    try:
        raw_library = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read trauma stamp library: {exc}")
    try:
        library = trauma_field.normalize_stamp_library(raw_library)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(str(exc))

    registry = _load_registry()
    region_by_id = {str(region.get("regionId", "")): region for region in registry.get("regions", [])}
    target_contracts = {}
    for region_id, region in region_by_id.items():
        attached, detached = _resolve_region_pair(region)
        contract = validate_region_contract(region, attached, detached)
        if contract["status"] == "PASS":
            target_contracts[region_id] = {
                "regionMode": _region_mode(region),
                "topologyFingerprint": contract["topologyFingerprint"],
                "vertexCount": contract["attachedVertexCount"],
                "polygonCount": contract["attachedPolygonCount"],
            }
    missing_regions = [
        str(region["regionId"])
        for region in library["regions"]
        if str(region["regionId"]) not in target_contracts
    ]
    if missing_regions:
        raise RuntimeError(
            "These saved deformation regions are not registered with valid region contracts: "
            + ", ".join(missing_regions)
        )
    mode_mismatches = [
        str(library_region["regionId"])
        for library_region in library["regions"]
        if str(library_region.get("regionMode", PAIRED_SEGMENT))
        != str(target_contracts[str(library_region["regionId"])]["regionMode"])
    ]
    if mode_mismatches:
        raise RuntimeError(
            "Saved region modes do not match the explicit current registrations: "
            + ", ".join(mode_mismatches)
        )

    event_plans = []
    event_conflicts = []
    for saved_event in library.get("compoundEvents", []):
        rebound = copy.deepcopy(saved_event)
        rebound.pop("recipeDigest", None)
        for participant in rebound.get("participants", []):
            region = region_by_id.get(str(participant.get("regionId", "")))
            if region is None:
                continue
            target, detached = _resolve_region_pair(region)
            participant["regionMode"] = _region_mode(region)
            participant["targetObject"] = target.name
            participant["detachedObject"] = detached.name if detached is not None else ""
            participant["participantSeed"] = trauma_field.derive_participant_seed(
                int(rebound.get("seed", 0)), str(region.get("regionId", "")), target.name
            )
        rebound = trauma_field.normalize_compound_event(rebound, verify_digest=False)
        existing = _compound_event_record(registry, str(rebound["eventId"]))
        if existing is not None:
            try:
                existing_digest = trauma_field.compound_event_digest(existing)
            except (TypeError, ValueError):
                existing_digest = "INVALID"
            if existing_digest != rebound["recipeDigest"]:
                event_conflicts.append(str(rebound["eventId"]))
            continue
        event_plans.append(rebound)
    if event_conflicts:
        raise RuntimeError(
            "Stamp library was not loaded because these compound events contain different work: "
            + ", ".join(event_conflicts)
        )

    plans = []
    skipped = []
    conflicts = []
    remapped_capture_count = 0
    for library_region in library["regions"]:
        region_id = str(library_region["regionId"])
        region = region_by_id[region_id]
        attached, detached = _resolve_region_pair(region)
        payload = _metadata(attached)
        for key_record in library_region["keys"]:
            key_record = copy.deepcopy(dict(key_record))
            name = str(key_record["name"])
            stamps = [
                _rebind_library_stamp(attached, region, stamp)
                for stamp in key_record["stamps"]
            ]
            if "surfaceGoreOverlay" in key_record:
                overlay = trauma_field.normalize_gore_overlay(key_record["surfaceGoreOverlay"])
                linked_stamp = next(
                    (stamp for stamp in stamps if stamp.get("stampId") == overlay.get("linkedStampId")),
                    None,
                )
                if overlay["goreOverlayEnabled"] and linked_stamp is None:
                    raise RuntimeError(
                        f"Deformation key {name!r} has a surface gore overlay linked to a missing saved stamp."
                    )
                if linked_stamp is not None:
                    capture = linked_stamp.get("capture", {})
                    overlay["linkedRegionId"] = region_id
                    overlay["linkedSelectionHash"] = str(capture.get("selectionHash", ""))
                    overlay["linkedCaptureTopologyFingerprint"] = str(capture.get("topologyFingerprint", ""))
                overlay["validationStatus"] = "NOT_VALIDATED"
                key_record["surfaceGoreOverlay"] = overlay
                key_record["goreOverlayDigest"] = trauma_field.gore_overlay_digest(overlay)
            existing_entry = payload.get("keys", {}).get(name)
            attached_key = _key(attached, name)
            detached_key = _key(detached, name) if detached is not None else None
            imported_digest = trauma_field.recipe_digest(stamps)
            existing_digest = ""
            imported_gore_digest = str(key_record.get("goreOverlayDigest", ""))
            existing_gore_digest = ""
            if existing_entry and existing_entry.get("stamps"):
                try:
                    existing_digest = trauma_field.recipe_digest(existing_entry["stamps"])
                except (TypeError, ValueError):
                    existing_digest = "INVALID"
            if existing_entry and existing_entry.get("surfaceGoreOverlay"):
                try:
                    existing_gore_digest = trauma_field.gore_overlay_digest(existing_entry["surfaceGoreOverlay"])
                except (TypeError, ValueError):
                    existing_gore_digest = "INVALID"
            if existing_entry is not None or attached_key is not None or detached_key is not None:
                if (
                    existing_digest == imported_digest
                    and existing_gore_digest == imported_gore_digest
                    and attached_key is not None
                    and (detached is None or detached_key is not None)
                ):
                    skipped.append(f"{region_id}/{name}")
                    continue
                conflicts.append(f"{region_id}/{name}")
                continue
            remapped_capture_count += sum(
                stamp.get("capture", {}).get("portableBindingMode") == "ANALYTICAL_POSITIONAL_ANCHORS"
                for stamp in stamps
            )
            coordinates = _stamp_local_coordinates(attached, stamps, region)
            plans.append({
                "regionId": region_id,
                "region": region,
                "attached": attached,
                "detached": detached,
                "key": key_record,
                "stamps": stamps,
                "coordinates": coordinates,
            })
    if conflicts:
        raise RuntimeError(
            "Stamp library was not loaded because these deformation keys already contain different work: "
            + ", ".join(conflicts)
            + ". Delete or rename those keys first; Forge never overwrites authored stamp stacks."
        )

    previous_region_id = registry.get("activeRegionId", "")
    affected_region_ids = {plan["regionId"] for plan in plans}
    affected_region_ids.update(
        str(participant.get("regionId", ""))
        for event in event_plans for participant in event.get("participants", [])
    )
    metadata_backups = {
        region_id: copy.deepcopy(_metadata(_resolve_region_pair(region_by_id[region_id])[0]))
        for region_id in affected_region_ids if region_id in region_by_id
    }
    coordinate_backups = []
    for region_id in affected_region_ids:
        region = region_by_id.get(region_id)
        if region is None:
            continue
        target, detached = _resolve_region_pair(region)
        for key_name in metadata_backups.get(region_id, {}).get("keys", {}):
            target_key = _key(target, key_name)
            if target_key is None:
                continue
            coordinate_backups.append({
                "regionId": region_id,
                "target": target,
                "detached": detached,
                "keyName": key_name,
                "coordinates": [point.co.copy() for point in target_key.data],
            })
    registry_backup = copy.deepcopy(registry)
    created = []
    validation = None
    try:
        clear_seed_preview(all_regions=True)
        for plan in plans:
            _set_active_region(plan["regionId"], context)
            key_record = plan["key"]
            metadata_entry = {
                **key_record,
                "stamps": plan["stamps"],
                "status": "TRAUMA_REBUILT",
                "recipeStatus": "PROCEDURAL_STACK",
                "legacy": False,
            }
            attached, detached, attached_key, detached_key = _ensure_key_pair(
                str(key_record["name"]),
                metadata_entry=metadata_entry,
            )
            created.append((attached, detached, str(key_record["name"]), plan["regionId"]))
            _set_key_coordinates(attached_key, plan["coordinates"])
            sync_key_to_detached(str(key_record["name"]), plan["regionId"])
            if detached is not None:
                _link_detached_value(attached, detached, str(key_record["name"]))
            attached_key.value = 0.0
            if detached_key is not None:
                detached_key.value = 0.0
            payload = _metadata(attached)
            entry = payload["keys"][str(key_record["name"])]
            entry.update(metadata_entry)
            entry["region"] = plan["regionId"]
            entry["regionId"] = plan["regionId"]
            entry["recipeDigest"] = trauma_field.recipe_digest(plan["stamps"])
            if entry.get("surfaceGoreOverlay"):
                imported_overlay = trauma_field.normalize_gore_overlay(entry["surfaceGoreOverlay"])
                if imported_overlay["goreOverlayEnabled"] and imported_overlay["goreRaisedEnabled"]:
                    rebuild_raised_gore_for_key(plan["region"], attached, detached, str(key_record["name"]), entry)
            _store_metadata(attached, detached, payload)
        if event_plans:
            current_registry = _load_registry()
            current_registry.setdefault("compoundEvents", []).extend(copy.deepcopy(event_plans))
            _store_registry(current_registry)
            for event in event_plans:
                event_id = str(event["eventId"])
                for participant in event.get("participants", []):
                    region_id = str(participant.get("regionId", ""))
                    region = region_by_id[region_id]
                    target, detached = _resolve_region_pair(region)
                    key_name = str(participant.get("childKeyName", ""))
                    entry_payload = _metadata(target)
                    target_entry = entry_payload.get("keys", {}).get(key_name)
                    if target_entry is None:
                        raise RuntimeError(
                            f"Compound event {event_id!r} references missing imported child key {region_id}/{key_name}."
                        )
                    target_entry["compoundEventIds"] = sorted(
                        set(target_entry.get("compoundEventIds", [])) | {event_id}
                    )
                    target_entry["compoundChildStampId"] = str(participant.get("childStampId", ""))
                    _store_metadata(target, detached, entry_payload)
                select_compound_event(context, event_id)
                rebuild_compound_event(context)
        validation = validate_deformations(require_keys=True)
        if validation["status"] != "PASS":
            raise RuntimeError(
                "Loaded trauma library failed validation: " + "; ".join(validation["errors"][:8])
            )
    except Exception:
        for attached, detached, name, _region_id in reversed(created):
            _remove_generated_gore_objects(_region_id, name)
            _remove_key(attached, name)
            if detached is not None:
                _remove_key(detached, name)
        _store_registry(registry_backup)
        for region_id, backup in metadata_backups.items():
            region = region_by_id.get(region_id)
            if region is None:
                continue
            target, detached = _resolve_region_pair(region)
            if backup is not None:
                _store_metadata(target, detached, backup)
        for backup in coordinate_backups:
            key = _key(backup["target"], backup["keyName"])
            if key is None:
                continue
            _set_key_coordinates(key, backup["coordinates"])
            if backup["detached"] is not None:
                _sync_exact_index_key_pair(
                    backup["target"], backup["detached"], backup["keyName"]
                )
        for region_id, backup in metadata_backups.items():
            region = region_by_id.get(region_id)
            if region is None:
                continue
            target, detached = _resolve_region_pair(region)
            for key_name, entry in backup.get("keys", {}).items():
                _remove_generated_gore_objects(region_id, key_name)
                overlay = entry.get("surfaceGoreOverlay")
                if isinstance(overlay, dict) and overlay.get("goreRaisedEnabled", False):
                    try:
                        rebuild_raised_gore_for_key(region, target, detached, key_name, entry)
                    except Exception:
                        # Preserve the primary import failure. Subsequent
                        # validation will explicitly report a stale gore restore.
                        pass
        if previous_region_id and _region_record(_load_registry(), previous_region_id) is not None:
            _set_active_region(previous_region_id, context)
        raise

    _invalidate_geodesic_cache()
    if plans:
        first = plans[0]
        _set_active_region(first["regionId"], context)
        _select_key(context.scene.daf_settings, str(first["key"]["name"]))
    elif previous_region_id and _region_record(_load_registry(), previous_region_id) is not None:
        _set_active_region(previous_region_id, context)
    if validation is None:
        raise RuntimeError("Trauma library load completed without a validation result.")
    context.scene.daf_settings.last_deformation_validation = validation["status"]
    context.scene.daf_settings.deformation_status = (
        f"STAMP LIBRARY LOADED — {len(plans)} keys / {int(library['stampCount'])} stamps"
    )
    return {
        "path": str(path),
        "importedKeyCount": len(plans),
        "skippedKeyCount": len(skipped),
        "stampCount": int(library["stampCount"]),
        "compoundEventCount": len(event_plans),
        "remappedCaptureCount": remapped_capture_count,
        "validation": validation,
    }


def _gore_state(obj):
    raw = obj.get(GORE_PREVIEW_STATE_PROPERTY, "")
    if not raw:
        return {}
    try:
        state = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"broken": True}
    return state if isinstance(state, dict) else {"broken": True}


def _clear_gore_preview_pair(attached, detached):
    material_names = set()
    previewed_keys = set()
    for obj in tuple(value for value in (attached, detached) if value is not None):
        state = _gore_state(obj)
        if state and not state.get("broken"):
            previewed_keys.add(str(state.get("keyName", "")))
            material_names.update(str(name) for name in state.get("previewMaterialNames", []) if name)
            original_names = state.get("originalMaterialNames", [])
            original_fake_users = state.get("originalMaterialFakeUsers", [])
            original_count = int(state.get("originalMaterialSlotCount", len(original_names)))
            for index in range(min(original_count, len(obj.material_slots))):
                original = str(original_names[index]) if index < len(original_names) and original_names[index] else ""
                original_material = bpy.data.materials.get(original) if original else None
                obj.material_slots[index].material = original_material
                if original_material is not None and index < len(original_fake_users):
                    original_material.use_fake_user = bool(original_fake_users[index])
            while len(obj.data.materials) > original_count:
                obj.data.materials.pop(index=len(obj.data.materials) - 1)
        else:
            fallback_original_count = len(obj.material_slots)
            for slot in obj.material_slots:
                managed = slot.material
                if managed is None or not managed.get("dsb_surface_gore_preview", False):
                    continue
                fallback_original_count = int(managed.get("dsb_surface_gore_original_slot_count", fallback_original_count))
                source_name = str(managed.get("dsb_surface_gore_source_material", ""))
                source = bpy.data.materials.get(source_name) if source_name else None
                slot.material = source
                if source is not None:
                    source.use_fake_user = bool(managed.get("dsb_surface_gore_source_fake_user", False))
            while len(obj.data.materials) > fallback_original_count:
                obj.data.materials.pop(index=len(obj.data.materials) - 1)
        attribute = obj.data.color_attributes.get(GORE_PREVIEW_ATTRIBUTE)
        if attribute is not None:
            obj.data.color_attributes.remove(attribute)
        if GORE_PREVIEW_STATE_PROPERTY in obj:
            del obj[GORE_PREVIEW_STATE_PROPERTY]
    for material_name in sorted(material_names):
        material = bpy.data.materials.get(material_name)
        if material is not None and material.get("dsb_surface_gore_preview", False) and material.users == 0:
            bpy.data.materials.remove(material)
    for material in list(bpy.data.materials):
        if material.get("dsb_surface_gore_preview", False) and material.users == 0:
            bpy.data.materials.remove(material)
    if previewed_keys:
        payload = _metadata(attached)
        changed = False
        for key_name in previewed_keys:
            overlay = payload.get("keys", {}).get(key_name, {}).get("surfaceGoreOverlay")
            if overlay:
                overlay["previewStatus"] = "CLEARED"
                overlay.pop("previewObjectNames", None)
                overlay.pop("previewAttributeName", None)
                changed = True
        if changed:
            _store_metadata(attached, detached, payload)


def clear_surface_gore_preview(all_regions=False):
    registry = _load_registry()
    if all_regions:
        regions = list(registry.get("regions", []))
    else:
        region = _region_record(registry, _active_region_id())
        regions = [region] if region is not None else []
    for region in regions:
        attached, detached = _resolve_region_pair(region)
        _clear_gore_preview_pair(attached, detached)


def generated_gore_objects(region_id=None, key_name=None, pair_role=None, *, include_preview=False):
    """Return only Forge-owned, ordinary exportable raised-gore meshes."""

    result = []
    role = str(pair_role).upper() if pair_role else None
    for obj in bpy.data.objects:
        if not bool(obj.get("dsb_gore_owned", False)):
            continue
        if obj.get("dsb_generated_role") != GORE_OBJECT_ROLE or obj.type != 'MESH':
            continue
        if not include_preview and bool(obj.get("dsb_preview_only", False)):
            continue
        if region_id is not None and str(obj.get("dsb_gore_region_id", "")) != str(region_id):
            continue
        if key_name is not None and str(obj.get("dsb_gore_deformation_key", "")) != str(key_name):
            continue
        if role is not None and str(obj.get("dsb_gore_pair_role", "")).upper() != role:
            continue
        result.append(obj)
    return sorted(result, key=lambda obj: obj.name)


def preview_gore_objects(region_id=None, key_name=None):
    return [
        obj
        for obj in generated_gore_objects(region_id, key_name, include_preview=True)
        if bool(obj.get("dsb_preview_only", False))
    ]


def _remove_preview_gore_objects(region_id=None, key_name=None):
    removed = []
    for obj in list(preview_gore_objects(region_id, key_name)):
        mesh = obj.data
        removed.append(obj.name)
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        if material.get("dsb_gore_material", False) and material.users == 0:
            bpy.data.materials.remove(material)
    for image in list(bpy.data.images):
        if image.get("dsb_gore_composed_texture", False) and image.users == 0:
            bpy.data.images.remove(image)
    return removed


def _remove_generated_gore_objects(region_id=None, key_name=None, pair_role=None):
    removed = []
    for obj in list(generated_gore_objects(region_id, key_name, pair_role)):
        mesh = obj.data
        removed.append(obj.name)
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        if material.get("dsb_gore_material", False) and material.users == 0:
            bpy.data.materials.remove(material)
    for image in list(bpy.data.images):
        if image.get("dsb_gore_composed_texture", False) and image.users == 0:
            bpy.data.images.remove(image)
    return removed


def _clear_generated_entry_fields(entry):
    for field in (
        "raisedGoreStatus", "goreGeneratedMeshIds", "goreGeneratedNodeNames",
        "goreGeometryDigests", "goreGenerationDigests", "goreTriangleCounts",
        "goreMaterialIds", "goreMaterialNames", "goreGeneratedAtBuild",
        "goreGeometryMode", "goreIdentityId", "goreValidationMeasurements",
    ):
        entry.pop(field, None)


def clear_generated_gore(context=None, *, all_regions=False):
    """Delete only Forge-owned raised gore; recipes and source meshes remain."""

    registry = _load_registry()
    active_id = _active_region_id(context)
    active_key = ""
    scene = getattr(context, "scene", None) if context is not None else getattr(bpy.context, "scene", None)
    settings = getattr(scene, "daf_settings", None)
    if settings is not None:
        active_key = str(settings.deformation_active_key)
    regions = registry.get("regions", []) if all_regions else [
        _region_record(registry, active_id)
    ]
    removed = []
    for region in regions:
        if region is None:
            continue
        region_id = str(region.get("regionId", ""))
        attached, detached = _resolve_region_pair(region)
        payload = _metadata(attached)
        names = list(payload.get("keys", {})) if all_regions else [active_key]
        for name in names:
            if not name:
                continue
            removed.extend(_remove_generated_gore_objects(region_id, name))
            entry = payload.get("keys", {}).get(name)
            if entry is not None:
                _clear_generated_entry_fields(entry)
                if entry.get("surfaceGoreOverlay", {}).get("goreRaisedEnabled", False):
                    entry["raisedGoreStatus"] = "NOT_GENERATED"
        _store_metadata(attached, detached, payload)
    return removed


def _gore_material_name(material_id, overlay):
    return f"{material_id}_{trauma_field.gore_overlay_digest(overlay)[:8]}"


def _ensure_gore_texture_atlas():
    """Load the packaged four-direction fiber atlas without touching user images."""

    if not GORE_TEXTURE_ATLAS_PATH.is_file():
        raise RuntimeError(
            f"Packaged muscle-fiber atlas is missing: {GORE_TEXTURE_ATLAS_PATH}"
        )
    resolved = str(GORE_TEXTURE_ATLAS_PATH.resolve())
    image = next(
        (
            candidate for candidate in bpy.data.images
            if bool(candidate.get("dsb_gore_texture_atlas", False))
            and str(Path(bpy.path.abspath(candidate.filepath)).resolve()) == resolved
        ),
        None,
    )
    if image is None:
        image = bpy.data.images.load(resolved, check_existing=True)
    occupied = bpy.data.images.get(GORE_TEXTURE_ATLAS_IMAGE)
    if occupied is not None and occupied is not image and not bool(occupied.get("dsb_gore_texture_atlas", False)):
        raise RuntimeError(f"Image name {GORE_TEXTURE_ATLAS_IMAGE!r} is occupied by user data.")
    image.name = GORE_TEXTURE_ATLAS_IMAGE
    image.filepath = resolved
    image["dsb_gore_texture_atlas"] = True
    image["dsb_generated_role"] = "raised_gore_texture_atlas"
    try:
        image.colorspace_settings.name = 'sRGB'
    except TypeError:
        pass
    return image


def _ensure_gore_composed_texture(material_id, overlay, base_color):
    """Bake independent additive fiber and gore-color contributions for glTF."""

    atlas = _ensure_gore_texture_atlas()
    digest = trauma_field.gore_overlay_digest(overlay)
    name = f"DSB_GORE_COMPOSED_{material_id}_{digest[:10]}"
    image = bpy.data.images.get(name)
    if image is not None and not bool(image.get("dsb_gore_composed_texture", False)):
        raise RuntimeError(f"Image name {name!r} is occupied by non-Forge data.")
    if image is not None:
        return image
    width, height = (int(value) for value in atlas.size)
    if width <= 0 or height <= 0:
        raise RuntimeError("The packaged muscle-fiber atlas has not loaded any pixels.")
    fiber_strength = float(overlay["goreFiberTextureStrength"])
    color_strength = float(overlay["goreBaseColorStrength"])
    source_pixels = list(atlas.pixels[:])
    composed = [0.0] * len(source_pixels)
    cavity_mode = str(overlay.get("goreGeometryMode", "")) == "CAVITY_INLAY"
    for offset in range(0, len(source_pixels), 4):
        if cavity_mode:
            # Cavity materials preserve their role hue.  Treat the atlas as a
            # bounded fiber-value modulation instead of adding its near-white
            # RGB directly, which would wash deep crimson into cream under
            # ordinary point lights.  Legacy raised recipes keep their exact
            # additive v3 composition below.
            fiber_value = (
                float(source_pixels[offset]) * 0.2126
                + float(source_pixels[offset + 1]) * 0.7152
                + float(source_pixels[offset + 2]) * 0.0722
            )
            fiber_modulation = 0.82 + fiber_strength * (0.12 + fiber_value * 0.22)
            color_modulation = 0.78 + color_strength * 0.22
            for channel in range(3):
                composed[offset + channel] = min(
                    1.0,
                    float(base_color[channel]) * fiber_modulation * color_modulation,
                )
        else:
            composed[offset] = min(1.0, source_pixels[offset] * fiber_strength + float(base_color[0]) * color_strength)
            composed[offset + 1] = min(1.0, source_pixels[offset + 1] * fiber_strength + float(base_color[1]) * color_strength)
            composed[offset + 2] = min(1.0, source_pixels[offset + 2] * fiber_strength + float(base_color[2]) * color_strength)
        composed[offset + 3] = source_pixels[offset + 3]
    image = bpy.data.images.new(name=name, width=width, height=height, alpha=True)
    image.pixels[:] = composed
    image["dsb_gore_composed_texture"] = True
    image["dsb_gore_texture_atlas"] = True
    image["dsb_generated_role"] = "raised_gore_composed_texture"
    image["dsb_gore_recipe_digest"] = digest
    image["dsb_gore_material_id"] = material_id
    image["dsb_gore_fiber_texture_strength"] = fiber_strength
    image["dsb_gore_base_color_strength"] = color_strength
    image["dsb_gore_composition_mode"] = (
        "CAVITY_HUE_PRESERVING_V1" if cavity_mode else "LEGACY_ADDITIVE_V3"
    )
    image.pack()
    return image


def _ensure_gore_material(material_id, overlay):
    if material_id not in trauma_field.GORE_MATERIAL_SPECS:
        raise RuntimeError(f"Unsupported raised gore material ID {material_id!r}.")
    name = _gore_material_name(material_id, overlay)
    material = bpy.data.materials.get(name)
    if material is not None and not material.get("dsb_gore_material", False):
        raise RuntimeError(f"Material name {name!r} is occupied by non-Forge data.")
    material = material or bpy.data.materials.new(name=name)
    material.use_nodes = True
    material["dsb_gore_material"] = True
    material["dsb_generated_role"] = "raised_gore_material"
    material["dsb_gore_material_id"] = material_id
    material["dsb_gore_recipe_digest"] = trauma_field.gore_overlay_digest(overlay)
    material["dsb_gore_textured"] = bool(overlay["goreTextureEnabled"])
    material["dsb_gore_fiber_texture_strength"] = float(overlay["goreFiberTextureStrength"])
    material["dsb_gore_base_color_strength"] = float(overlay["goreBaseColorStrength"])
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    output.name = "DSB glTF Material Output"
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.name = "DSB glTF Gore Principled"
    spec = trauma_field.GORE_MATERIAL_SPECS[material_id]
    intensity = float(overlay["goreColorIntensity"])
    darkness = float(overlay["goreDarkness"])
    wet_variation = float(overlay["goreWetnessVariation"])
    base = list(spec["baseColor"])
    if material_id == trauma_field.LEGACY_GORE_MATERIAL_IDS[0]:
        base[:3] = [min(1.0, channel * (0.72 + intensity * 0.48)) for channel in base[:3]]
        roughness = max(0.06, float(spec["roughness"]) * (1.24 - wet_variation * 0.40))
    elif material_id == trauma_field.LEGACY_GORE_MATERIAL_IDS[1]:
        base[:3] = [channel * (1.0 - darkness * 0.30) for channel in base[:3]]
        roughness = float(spec["roughness"])
    elif material_id == "DSB_GORE_DEEP_WOUND_BED":
        base[:3] = [channel * (0.82 + intensity * 0.18) for channel in base[:3]]
        roughness = max(0.30, float(spec["roughness"]) - wet_variation * 0.10)
    elif material_id == "DSB_GORE_CRUSHED_TISSUE":
        base[:3] = [channel * (0.78 + intensity * 0.32) for channel in base[:3]]
        roughness = max(0.34, float(spec["roughness"]) - wet_variation * 0.12)
    elif material_id == "DSB_GORE_EXPOSED_BONE":
        base[:3] = [min(0.72, channel * (0.90 + intensity * 0.10)) for channel in base[:3]]
        roughness = float(spec["roughness"])
    else:
        base[:3] = [channel * (0.88 + intensity * 0.12) for channel in base[:3]]
        roughness = min(0.95, float(spec["roughness"]) + float(overlay["goreRoughEdgeBias"]) * 0.10)
    shader.inputs["Base Color"].default_value = tuple(base)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = 0.0
    emission = shader.inputs.get("Emission Color")
    if emission is None:
        emission = shader.inputs.get("Emission")
    if emission is not None:
        emission.default_value = (0.0, 0.0, 0.0, 1.0)
    emission_strength = shader.inputs.get("Emission Strength")
    if emission_strength is not None:
        emission_strength.default_value = 0.0
    if shader.inputs.get("Coat Weight") is not None:
        coat = (
            0.28 * float(overlay["goreWetness"])
            if material_id in {
                trauma_field.LEGACY_GORE_MATERIAL_IDS[0],
                "DSB_GORE_DEEP_WOUND_BED",
            }
            else 0.0
        )
        shader.inputs["Coat Weight"].default_value = coat
    if bool(overlay["goreTextureEnabled"]):
        texture = nodes.new('ShaderNodeTexImage')
        texture.name = "DSB Additive Fiber + Gore Color Composition"
        texture.label = "Independent fiber and gore-color contributions; direction chosen per face"
        texture.image = _ensure_gore_composed_texture(material_id, overlay, base)
        texture.interpolation = 'Linear'
        texture.extension = 'REPEAT'
        material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
        material["dsb_gore_composed_texture"] = texture.image.name
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material.diffuse_color = tuple(base)
    return material


def _deformation_local_points(obj, key_name):
    key = _key(obj, key_name)
    if key is None:
        raise RuntimeError(f"Raised gore owner {obj.name} has no deformation key {key_name!r}.")
    return [point.co.copy() for point in key.data]


def _deformation_input_digest(obj, key_name):
    _evaluated_world_matrix(obj)
    basis = _ensure_basis(obj)
    basis_world = [tuple(obj.matrix_world @ point.co) for point in basis.data]
    deformed_world = [tuple(obj.matrix_world @ point) for point in _deformation_local_points(obj, key_name)]
    return trauma_field.deformation_point_digest(basis_world, deformed_world)


def _local_vertex_normals(positions, faces):
    normals = [Vector((0.0, 0.0, 0.0)) for _unused in positions]
    for face in faces:
        indices = [int(index) for index in face]
        if len(indices) < 3:
            continue
        origin = positions[indices[0]]
        for offset in range(1, len(indices) - 1):
            normal = (positions[indices[offset]] - origin).cross(positions[indices[offset + 1]] - origin)
            for index in (indices[0], indices[offset], indices[offset + 1]):
                normals[index] += normal
    for index, normal in enumerate(normals):
        if normal.length_squared <= 1e-16:
            normal = Vector((0.0, 0.0, 1.0))
        normals[index] = normal.normalized()
    return normals


def _copy_gore_skinning(source, target, generated_source_blends, *, require_deform=False):
    """Interpolate source skin weights for corners and newly refined surface points."""

    target.parent = source.parent
    target.parent_type = source.parent_type
    target.parent_bone = source.parent_bone
    target.matrix_world = source.matrix_world.copy()
    source_armatures = [
        modifier.object
        for modifier in source.modifiers
        if modifier.type == "ARMATURE" and modifier.object is not None
    ]
    deform_names = {
        bone.name
        for armature in source_armatures
        for bone in getattr(getattr(armature, "data", None), "bones", ())
        if bool(getattr(bone, "use_deform", True))
    }
    permitted_names = deform_names if require_deform and deform_names else {
        group.name for group in source.vertex_groups
    }
    groups = {}
    for source_group in source.vertex_groups:
        if source_group.name in permitted_names:
            groups[source_group.index] = target.vertex_groups.new(name=source_group.name)
    for generated_index, raw_blend in enumerate(generated_source_blends):
        blend = raw_blend if isinstance(raw_blend, dict) else {int(raw_blend): 1.0}
        combined = {}
        total = sum(max(0.0, float(weight)) for weight in blend.values())
        if total <= 1e-12:
            continue
        for source_index, source_factor in blend.items():
            factor = max(0.0, float(source_factor)) / total
            if factor <= 0.0:
                continue
            for membership in source.data.vertices[int(source_index)].groups:
                if membership.group in groups and membership.weight > 0.0:
                    combined[membership.group] = (
                        combined.get(membership.group, 0.0) + factor * float(membership.weight)
                    )
        selected = sorted(
            (
                (group_index, weight)
                for group_index, weight in combined.items()
                if math.isfinite(weight) and weight > 0.0
            ),
            key=lambda item: (-item[1], item[0]),
        )[:4]
        selected_total = sum(weight for _group_index, weight in selected)
        if require_deform and deform_names and selected_total <= 1e-12:
            raise RuntimeError(
                f"Cavity/inlay vertex {generated_index} has no interpolated deform influence."
            )
        for group_index, weight in selected:
            groups[group_index].add(
                [generated_index], weight / selected_total, "REPLACE"
            )
    for source_modifier in source.modifiers:
        if source_modifier.type != 'ARMATURE':
            continue
        modifier = target.modifiers.new(name=source_modifier.name, type='ARMATURE')
        modifier.object = source_modifier.object
        for attribute in ("use_deform_preserve_volume", "use_vertex_groups", "use_bone_envelopes"):
            if hasattr(source_modifier, attribute) and hasattr(modifier, attribute):
                setattr(modifier, attribute, getattr(source_modifier, attribute))


def _mesh_digest(obj):
    return trauma_field.mesh_geometry_digest(
        [tuple(vertex.co) for vertex in obj.data.vertices],
        [tuple(polygon.vertices) for polygon in obj.data.polygons],
        [int(polygon.material_index) for polygon in obj.data.polygons],
    )


def _region_gore_sources(region, attached, detached):
    if _region_mode(region) == CORE_SINGLE:
        return ((attached, "CORE"),)
    return ((attached, "ATTACHED"), (detached, "DETACHED"))


def _smoothed_gore_thickness(face_records):
    """Relax face-level thickness and taper open island rims for cleaner shells."""

    thickness = {}
    adjacency = {}
    edge_uses = {}
    for record in face_records:
        face = [int(index) for index in record["vertices"]]
        value = float(record["thickness"])
        for index in face:
            thickness[index] = max(thickness.get(index, 0.0), value)
            adjacency.setdefault(index, set())
        for offset, first in enumerate(face):
            second = face[(offset + 1) % len(face)]
            adjacency[first].add(second)
            adjacency[second].add(first)
            edge = tuple(sorted((first, second)))
            edge_uses[edge] = edge_uses.get(edge, 0) + 1
    for _pass in range(2):
        relaxed = {}
        for index, value in thickness.items():
            neighbors = adjacency.get(index, ())
            average = sum(thickness.get(neighbor, value) for neighbor in neighbors) / max(1, len(neighbors))
            relaxed[index] = value * 0.55 + average * 0.45
        thickness = relaxed
    boundary = {
        index
        for edge, count in edge_uses.items() if count == 1
        for index in edge
    }
    for index in boundary:
        thickness[index] *= 0.42
    return thickness


def _gore_unit(seed, *values):
    payload = "|".join(str(int(value)) for value in (seed, *values)).encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / float((1 << 64) - 1)


def _normalized_source_blend(blend):
    merged = {}
    for source_index, weight in blend.items():
        value = max(0.0, float(weight))
        if value > 0.0:
            merged[int(source_index)] = merged.get(int(source_index), 0.0) + value
    total = sum(merged.values())
    if total <= 1e-12:
        raise RuntimeError("Organic gore refinement produced an empty source blend.")
    return {source_index: weight / total for source_index, weight in merged.items()}


def _lerp_source_blends(first, second, factor):
    amount = min(1.0, max(0.0, float(factor)))
    combined = {}
    for source_index, weight in first.items():
        combined[int(source_index)] = combined.get(int(source_index), 0.0) + float(weight) * (1.0 - amount)
    for source_index, weight in second.items():
        combined[int(source_index)] = combined.get(int(source_index), 0.0) + float(weight) * amount
    return _normalized_source_blend(combined)


def _gore_atlas_uv(local_uv, variant):
    """Map zero-to-one local UVs into one padded quadrant of the 2x2 atlas."""

    index = int(variant) % len(trauma_field.GORE_TEXTURE_VARIANTS)
    quadrant_x = index % 2
    # Image files are assembled top-to-bottom; Blender UV origin is bottom-left.
    quadrant_y = 1 - (index // 2)
    padding = 0.018
    u = padding + min(1.0, max(0.0, float(local_uv[0]))) * (1.0 - padding * 2.0)
    v = padding + min(1.0, max(0.0, float(local_uv[1]))) * (1.0 - padding * 2.0)
    return ((quadrant_x + u) * 0.5, (quadrant_y + v) * 0.5)


def _build_gore_shell_object(
    source,
    key_name,
    region_id,
    pair_role,
    overlay,
    face_records,
    *,
    preview=False,
    component="",
):
    stable_name = trauma_field.gore_generated_object_name(
        region_id, key_name, pair_role, component
    )
    name = stable_name + "__PREVIEW" if preview else stable_name
    if bpy.data.objects.get(name) is not None:
        raise RuntimeError(f"Raised gore object name {name!r} was not cleared before rebuild.")
    source_world = _evaluated_world_matrix(source)
    positions = _deformation_local_points(source, key_name)
    source_faces = [tuple(int(index) for index in polygon.vertices) for polygon in source.data.polygons]
    normals = _local_vertex_normals(positions, source_faces)
    all_source_indices = sorted({int(index) for record in face_records for index in record["vertices"]})
    if not all_source_indices:
        raise RuntimeError("Raised gore selection contains no usable source vertices.")
    thickness_by_vertex = _smoothed_gore_thickness(face_records)

    record_edges = []
    edge_records = {}
    for record_index, record in enumerate(face_records):
        record_face = [int(index) for index in record["vertices"]]
        edges = {
            tuple(sorted((first, record_face[(index + 1) % len(record_face)])))
            for index, first in enumerate(record_face)
        }
        record_edges.append(edges)
        for edge in edges:
            edge_records.setdefault(edge, []).append(record_index)
    record_adjacency = {index: set() for index in range(len(face_records))}
    for record_indices in edge_records.values():
        for first in record_indices:
            record_adjacency[first].update(index for index in record_indices if index != first)
    surface_islands = []
    remaining = set(range(len(face_records)))
    while remaining:
        seed = min(remaining)
        stack = [seed]
        island_record_indices = []
        remaining.remove(seed)
        while stack:
            current = stack.pop()
            island_record_indices.append(current)
            neighbors = sorted(record_adjacency[current] & remaining, reverse=True)
            for neighbor in neighbors:
                remaining.remove(neighbor)
                stack.append(neighbor)
        surface_islands.append(sorted(island_record_indices))

    inverse = source_world.inverted()
    normal_matrix = source_world.to_3x3().inverted().transposed()
    offset = float(overlay["goreSurfaceOffset"])
    base_thickness = float(overlay["goreClotThickness"])
    organic = float(overlay["goreOrganicIrregularity"])
    roundness = float(overlay["goreSurfaceRoundness"])
    master_seed = int(overlay["goreMaskSeed"])
    textured = bool(overlay["goreTextureEnabled"])
    vertices = []
    generated_source_indices = []
    generated_source_blends = []
    generated_surface_positions = []
    material_lookup = {
        material_id: index
        for index, material_id in enumerate(
            trauma_field.RAISED_GORE_MATERIAL_IDS
        )
    }
    faces = []
    material_indices = []
    face_uvs = []
    face_texture_variants = []
    face_layers = []
    nucleus_candidates = []
    nucleus_triangle_count = 0

    world_points = {index: source_world @ point for index, point in enumerate(positions)}
    world_normals = {}
    for index, normal in enumerate(normals):
        normal_world = normal_matrix @ normal
        if normal_world.length_squared <= 1e-16:
            normal_world = Vector((0.0, 0.0, 1.0))
        world_normals[index] = normal_world.normalized()

    def blended_surface(blend):
        result = Vector((0.0, 0.0, 0.0))
        for source_index, weight in blend.items():
            result += world_points[int(source_index)] * float(weight)
        return result

    def blended_normal(blend):
        result = Vector((0.0, 0.0, 0.0))
        for source_index, weight in blend.items():
            result += world_normals[int(source_index)] * float(weight)
        if result.length_squared <= 1e-16:
            return Vector((0.0, 0.0, 1.0))
        return result.normalized()

    def add_vertex(surface_world, normal_world, height, blend):
        normalized = _normalized_source_blend(blend)
        index = len(vertices)
        vertices.append(tuple(inverse @ (surface_world + normal_world * float(height))))
        generated_surface_positions.append(tuple(inverse @ surface_world))
        generated_source_blends.append(normalized)
        generated_source_indices.append(max(normalized, key=lambda value: (normalized[value], -value)))
        return index

    def choose_variant(face_index, subface_index):
        if not textured:
            return 0
        return trauma_field.gore_texture_variant_index(master_seed, face_index, subface_index)

    def add_face(indices, material_index, local_uvs, variant, layer):
        faces.append(tuple(int(index) for index in indices))
        material_indices.append(int(material_index))
        face_uvs.append(tuple(tuple(float(value) for value in uv) for uv in local_uvs))
        face_texture_variants.append(int(variant))
        face_layers.append(int(layer))

    triangle_uv = ((0.05, 0.05), (0.95, 0.05), (0.50, 0.95))
    quad_uv = ((0.04, 0.04), (0.96, 0.04), (0.96, 0.96), (0.04, 0.96))

    for island_record_indices in surface_islands:
        source_indices = sorted({
            int(index)
            for record_index in island_record_indices
            for index in face_records[record_index]["vertices"]
        })
        component_edges = {}
        face_data = {}
        for record_index in island_record_indices:
            face = [int(index) for index in face_records[record_index]["vertices"]]
            center_blend = {index: 1.0 / len(face) for index in face}
            center_shift = 0.12 * organic * _gore_unit(master_seed, record_index, 901)
            target_index = face[min(len(face) - 1, int(_gore_unit(master_seed, record_index, 907) * len(face)))]
            center_blend = _lerp_source_blends(center_blend, {target_index: 1.0}, center_shift)
            face_data[record_index] = {
                "vertices": face,
                "centerBlend": center_blend,
                "centerWorld": blended_surface(center_blend),
                "normalWorld": blended_normal(center_blend),
            }
            for edge_index, first in enumerate(face):
                second = face[(edge_index + 1) % len(face)]
                component_edges.setdefault(tuple(sorted((first, second))), []).append(
                    (record_index, first, second)
                )

        island_blend = _normalized_source_blend({
            source_index: 1.0 / len(source_indices)
            for source_index in source_indices
        })
        island_surface = blended_surface(island_blend)
        island_normal = blended_normal(island_blend)
        tangent_candidates = []
        for source_index in source_indices:
            tangent = world_points[source_index] - island_surface
            tangent -= island_normal * tangent.dot(island_normal)
            tangent_candidates.append(tangent)
        tangent_u = max(
            tangent_candidates,
            key=lambda value: value.length_squared,
            default=Vector((1.0, 0.0, 0.0)),
        )
        if tangent_u.length_squared <= 1e-16:
            tangent_u = island_normal.cross(Vector((1.0, 0.0, 0.0)))
            if tangent_u.length_squared <= 1e-16:
                tangent_u = island_normal.cross(
                    Vector((0.0, 1.0, 0.0))
                )
        tangent_u.normalize()
        tangent_v = island_normal.cross(tangent_u).normalized()
        extent_u = max(
            (
                abs(
                    (world_points[index] - island_surface).dot(
                        tangent_u
                    )
                )
                for index in source_indices
            ),
            default=base_thickness,
        )
        extent_v = max(
            (
                abs(
                    (world_points[index] - island_surface).dot(
                        tangent_v
                    )
                )
                for index in source_indices
            ),
            default=base_thickness,
        )
        for record_index in island_record_indices:
            record = face_records[record_index]
            data = face_data[record_index]
            response = float(record.get("deformationResponse", 0.0))
            priority = float(record.get("priority", response))
            nucleus_candidates.append({
                "blend": dict(data["centerBlend"]),
                "surface": Vector(data["centerWorld"]),
                "normal": Vector(data["normalWorld"]),
                "tangentU": tangent_u.copy(),
                "tangentV": tangent_v.copy(),
                "extentU": extent_u,
                "extentV": extent_v,
                "priority": response * 0.82 + priority * 0.18,
                "faceIndex": int(record["faceIndex"]),
            })

        corner_bottom = {}
        corner_top = {}
        for source_index in source_indices:
            blend = {source_index: 1.0}
            surface = world_points[source_index]
            normal = world_normals[source_index]
            corner_bottom[source_index] = add_vertex(surface, normal, offset, blend)
            corner_top[source_index] = add_vertex(
                surface, normal, offset + thickness_by_vertex[source_index], blend
            )

        edge_bottom = {}
        edge_top = {}
        edge_blends = {}
        for edge, uses in sorted(component_edges.items()):
            first, second = edge
            ratio = 0.5 + (_gore_unit(master_seed, first, second, 101) - 0.5) * 0.28 * organic
            blend = _normalized_source_blend({first: 1.0 - ratio, second: ratio})
            surface = blended_surface(blend)
            normal = blended_normal(blend)
            edge_length = (world_points[second] - world_points[first]).length
            if len(uses) == 1 and edge_length > 1e-12:
                owner_center = face_data[uses[0][0]]["centerWorld"]
                outward = surface - owner_center
                outward -= normal * outward.dot(normal)
                if outward.length_squared > 1e-16:
                    signed = _gore_unit(master_seed, first, second, 109) * 2.0 - 1.0
                    surface += outward.normalized() * edge_length * 0.16 * organic * signed
            edge_blends[edge] = blend
            edge_thickness = (
                thickness_by_vertex[first] * (1.0 - ratio)
                + thickness_by_vertex[second] * ratio
                + base_thickness * roundness * (0.12 + 0.24 * _gore_unit(master_seed, first, second, 113))
            )
            edge_bottom[edge] = add_vertex(surface, normal, offset, blend)
            edge_top[edge] = add_vertex(surface, normal, offset + edge_thickness, blend)

        center_bottom = {}
        center_top = {}
        for record_index in island_record_indices:
            data = face_data[record_index]
            face = data["vertices"]
            average_thickness = sum(thickness_by_vertex[index] for index in face) / len(face)
            center_thickness = average_thickness + base_thickness * roundness * (
                0.28 + 0.42 * _gore_unit(master_seed, record_index, 127)
            )
            center_bottom[record_index] = add_vertex(
                data["centerWorld"], data["normalWorld"], offset, data["centerBlend"]
            )
            center_top[record_index] = add_vertex(
                data["centerWorld"], data["normalWorld"], offset + center_thickness, data["centerBlend"]
            )

        for record_index in island_record_indices:
            record = face_records[record_index]
            face = face_data[record_index]["vertices"]
            top_material = material_lookup[str(record["materialId"])]
            for edge_index, first in enumerate(face):
                second = face[(edge_index + 1) % len(face)]
                edge = tuple(sorted((first, second)))
                subface = edge_index * 2
                add_face(
                    (corner_top[first], edge_top[edge], center_top[record_index]),
                    top_material,
                    triangle_uv,
                    choose_variant(int(record["faceIndex"]), subface),
                    1,
                )
                add_face(
                    (edge_top[edge], corner_top[second], center_top[record_index]),
                    top_material,
                    triangle_uv,
                    choose_variant(int(record["faceIndex"]), subface + 1),
                    1,
                )
                add_face(
                    (center_bottom[record_index], edge_bottom[edge], corner_bottom[first]),
                    material_lookup[trauma_field.GORE_MATERIAL_IDS[1]],
                    triangle_uv,
                    choose_variant(int(record["faceIndex"]), 1000 + subface),
                    0,
                )
                add_face(
                    (center_bottom[record_index], corner_bottom[second], edge_bottom[edge]),
                    material_lookup[trauma_field.GORE_MATERIAL_IDS[1]],
                    triangle_uv,
                    choose_variant(int(record["faceIndex"]), 1001 + subface),
                    0,
                )

        for edge, uses in sorted(component_edges.items()):
            if len(uses) != 1:
                continue
            record_index, first, second = uses[0]
            face_index = int(face_records[record_index]["faceIndex"])
            add_face(
                (corner_bottom[first], edge_bottom[edge], edge_top[edge], corner_top[first]),
                material_lookup[trauma_field.GORE_MATERIAL_IDS[2]],
                quad_uv,
                choose_variant(face_index, 2000 + first),
                0,
            )
            add_face(
                (edge_bottom[edge], corner_bottom[second], corner_top[second], edge_top[edge]),
                material_lookup[trauma_field.GORE_MATERIAL_IDS[2]],
                quad_uv,
                choose_variant(face_index, 2000 + second),
                0,
            )

        rim_enabled = bool(overlay["goreInnerRimEnabled"]) and float(overlay["goreInnerRimStrength"]) > 1e-8
        if rim_enabled:
            rim_strength = float(overlay["goreInnerRimStrength"])
            requested_width = float(overlay["goreInnerRimWidth"])
            rim_offset = max(0.00008, offset * 0.58)
            for edge, uses in sorted(component_edges.items()):
                if len(uses) != 1:
                    continue
                record_index, first, second = uses[0]
                face_index = int(face_records[record_index]["faceIndex"])
                center_blend = face_data[record_index]["centerBlend"]
                center_world = face_data[record_index]["centerWorld"]
                edge_length = (world_points[second] - world_points[first]).length
                if edge_length <= 1e-10:
                    continue
                width = min(requested_width, edge_length * 0.32)
                first_distance = (center_world - world_points[first]).length
                second_distance = (center_world - world_points[second]).length
                first_amount = min(0.45, width / max(first_distance, 1e-12))
                second_amount = min(0.45, width / max(second_distance, 1e-12))
                outer_first_blend = {first: 1.0}
                outer_second_blend = {second: 1.0}
                inner_first_blend = _lerp_source_blends(outer_first_blend, center_blend, first_amount)
                inner_second_blend = _lerp_source_blends(outer_second_blend, center_blend, second_amount)
                rim_height = min(base_thickness * 0.28, width * 0.38) * (0.35 + 0.65 * rim_strength)
                prism_blends = (
                    outer_first_blend, outer_second_blend, inner_second_blend, inner_first_blend
                )
                lower = []
                upper = []
                for blend in prism_blends:
                    surface = blended_surface(blend)
                    normal = blended_normal(blend)
                    lower.append(add_vertex(surface, normal, rim_offset, blend))
                    upper.append(add_vertex(surface, normal, rim_offset + rim_height, blend))
                rim_faces = (
                    (upper[0], upper[1], upper[2], upper[3]),
                    (lower[3], lower[2], lower[1], lower[0]),
                    (lower[0], lower[1], upper[1], upper[0]),
                    (lower[1], lower[2], upper[2], upper[1]),
                    (lower[2], lower[3], upper[3], upper[2]),
                    (lower[3], lower[0], upper[0], upper[3]),
                )
                for prism_face_index, prism_face in enumerate(rim_faces):
                    add_face(
                        prism_face,
                        material_lookup[trauma_field.GORE_MATERIAL_IDS[2]],
                        quad_uv,
                        choose_variant(face_index, 3000 + prism_face_index + first * 7),
                        2,
                    )

    nucleus_amount = float(overlay["goreNucleusAmount"])
    nucleus_count = 0
    if nucleus_amount > 1e-8 and nucleus_candidates:
        ranked_candidates = sorted(
            nucleus_candidates,
            key=lambda value: (
                -float(value["priority"]),
                int(value["faceIndex"]),
            ),
        )
        deepest_count = max(
            1,
            int(math.ceil(len(ranked_candidates) / 3.0)),
        )
        deepest_candidates = ranked_candidates[:deepest_count]
        requested_nucleus_count = min(
            len(deepest_candidates),
            1 + int(round(7.0 * nucleus_amount ** 0.72)),
        )
        selected_nuclei = [deepest_candidates[0]]
        spread_scale = max(
            float(overlay["gorePatchScale"]),
            base_thickness * 1.5,
            1e-8,
        )
        while len(selected_nuclei) < requested_nucleus_count:
            remaining_candidates = [
                candidate
                for candidate in deepest_candidates
                if candidate not in selected_nuclei
            ]
            if not remaining_candidates:
                break
            candidate = max(
                remaining_candidates,
                key=lambda value: (
                    min(
                        (
                            Vector(value["surface"])
                            - Vector(selected["surface"])
                        ).length
                        for selected in selected_nuclei
                    )
                    / spread_scale
                    + float(value["priority"]) * 0.28
                    + _gore_unit(
                        master_seed,
                        int(value["faceIndex"]),
                        17003,
                    )
                    * 0.04,
                    -int(value["faceIndex"]),
                ),
            )
            selected_nuclei.append(candidate)
        current_triangles = sum(max(1, len(face) - 2) for face in faces)
        available_triangles = max(
            0,
            int(overlay["goreMaximumTriangles"]) - current_triangles,
        )
        lobes = float(overlay["goreNucleusLobes"])
        latitude_segments = 7 + int(round(lobes * 4.0))
        longitude_segments = 10 + int(round(lobes * 6.0))
        while (
            2
            * longitude_segments
            * (latitude_segments - 1)
            * len(selected_nuclei)
            > available_triangles
            and (latitude_segments > 6 or longitude_segments > 8)
        ):
            if longitude_segments > 8:
                longitude_segments -= 1
            elif latitude_segments > 6:
                latitude_segments -= 1
        expected_nucleus_triangles = (
            2 * longitude_segments * (latitude_segments - 1)
        )
        affordable_nucleus_count = min(
            len(selected_nuclei),
            available_triangles // max(1, expected_nucleus_triangles),
        )
        selected_nuclei = selected_nuclei[:affordable_nucleus_count]
        if (
            latitude_segments >= 6
            and longitude_segments >= 8
            and selected_nuclei
        ):
            patch_scale = float(overlay["gorePatchScale"])
            nucleus_material = material_lookup[
                "DSB_GORE_CRUSHED_TISSUE"
            ]
            for nucleus_index, nucleus in enumerate(selected_nuclei):
                anchor = Vector(nucleus["surface"])
                normal = Vector(nucleus["normal"])
                base_tangent_u = Vector(nucleus["tangentU"])
                base_tangent_v = Vector(nucleus["tangentV"])
                blend = dict(nucleus["blend"])
                face_index = int(nucleus["faceIndex"])
                rotation = (
                    _gore_unit(
                        master_seed,
                        face_index,
                        nucleus_index,
                        17007,
                    )
                    * math.tau
                )
                tangent_u = (
                    base_tangent_u * math.cos(rotation)
                    + base_tangent_v * math.sin(rotation)
                )
                tangent_v = normal.cross(tangent_u).normalized()
                size_variation = (
                    0.82
                    + 0.38
                    * _gore_unit(
                        master_seed,
                        face_index,
                        nucleus_index,
                        17009,
                    )
                )
                u_variation = (
                    0.80
                    + 0.42
                    * _gore_unit(
                        master_seed,
                        face_index,
                        nucleus_index,
                        17011,
                    )
                )
                v_variation = (
                    0.78
                    + 0.46
                    * _gore_unit(
                        master_seed,
                        face_index,
                        nucleus_index,
                        17013,
                    )
                )
                vertical_variation = (
                    0.82
                    + 0.36
                    * _gore_unit(
                        master_seed,
                        face_index,
                        nucleus_index,
                        17017,
                    )
                )
                extent_u = float(nucleus["extentU"])
                extent_v = float(nucleus["extentV"])
                radius_u = min(
                    extent_u * (0.46 + 0.12 * nucleus_amount),
                    max(
                        base_thickness
                        * (0.65 + 0.65 * nucleus_amount),
                        patch_scale
                        * (1.20 + 1.35 * nucleus_amount),
                    ),
                ) * size_variation * u_variation
                radius_v = min(
                    extent_v * (0.43 + 0.12 * nucleus_amount),
                    max(
                        base_thickness
                        * (0.58 + 0.60 * nucleus_amount),
                        patch_scale
                        * (1.08 + 1.22 * nucleus_amount),
                    ),
                ) * size_variation * v_variation
                radius_u = max(radius_u, base_thickness * 0.38)
                radius_v = max(radius_v, base_thickness * 0.34)
                vertical_radius = min(
                    max(radius_u, radius_v) * 0.92,
                    max(
                        base_thickness
                        * (0.52 + 0.82 * nucleus_amount),
                        patch_scale
                        * (0.86 + 1.12 * nucleus_amount),
                    ),
                ) * vertical_variation
                nucleus_distance_limit = (
                    offset + base_thickness * 4.0 + 0.002
                )
                vertical_radius = min(
                    vertical_radius,
                    max(
                        base_thickness * 0.35,
                        (nucleus_distance_limit - offset)
                        / (1.18 + lobes * 0.10),
                    ),
                )
                center_height = (
                    offset
                    + vertical_radius * 0.08
                )
                phase = (
                    _gore_unit(
                        master_seed,
                        face_index,
                        nucleus_index,
                        17019,
                    )
                    * math.tau
                )
                primary_folds = (
                    3.0
                    + lobes * 4.0
                    + float(nucleus_index % 3)
                )
                cross_folds = (
                    2.0
                    + lobes * 3.0
                    + float((nucleus_index + 1) % 4) * 0.5
                )

                def nucleus_vertex(phi, theta):
                    latitude_scale = max(0.0, math.cos(phi))
                    fold = (
                        math.sin(theta * primary_folds + phase)
                        * math.sin(
                            (phi + math.pi * 0.5)
                            * (2.5 + float(nucleus_index % 3) * 0.5)
                        )
                    )
                    cross_fold = math.sin(
                        theta * cross_folds
                        - phi
                        * (
                            4.0
                            + lobes * 3.0
                            + float(nucleus_index % 2)
                        )
                        + phase * 0.63
                    )
                    radial = max(
                        0.62,
                        1.0
                        + lobes
                        * (0.15 * fold + 0.08 * cross_fold),
                    )
                    x = (
                        math.cos(theta)
                        * latitude_scale
                        * radius_u
                        * radial
                    )
                    y = (
                        math.sin(theta)
                        * latitude_scale
                        * radius_v
                        * radial
                    )
                    z = (
                        math.sin(phi)
                        * vertical_radius
                        * (1.0 + lobes * 0.10 * cross_fold)
                    )
                    surface = anchor + tangent_u * x + tangent_v * y
                    return add_vertex(
                        surface,
                        normal,
                        center_height + z,
                        blend,
                    )

                bottom = nucleus_vertex(-math.pi * 0.5, 0.0)
                rings = []
                for latitude in range(1, latitude_segments):
                    phi = (
                        -math.pi * 0.5
                        + math.pi * latitude / latitude_segments
                    )
                    rings.append([
                        nucleus_vertex(
                            phi,
                            math.tau * longitude / longitude_segments,
                        )
                        for longitude in range(longitude_segments)
                    ])
                top = nucleus_vertex(math.pi * 0.5, 0.0)
                first_ring = rings[0]
                last_ring = rings[-1]
                texture_offset = nucleus_index * 10000
                for longitude in range(longitude_segments):
                    following = (
                        longitude + 1
                    ) % longitude_segments
                    add_face(
                        (
                            bottom,
                            first_ring[following],
                            first_ring[longitude],
                        ),
                        nucleus_material,
                        triangle_uv,
                        choose_variant(
                            face_index,
                            texture_offset + 4000 + longitude,
                        ),
                        3,
                    )
                    add_face(
                        (
                            top,
                            last_ring[longitude],
                            last_ring[following],
                        ),
                        nucleus_material,
                        triangle_uv,
                        choose_variant(
                            face_index,
                            texture_offset + 5000 + longitude,
                        ),
                        3,
                    )
                for ring_index in range(len(rings) - 1):
                    lower = rings[ring_index]
                    upper = rings[ring_index + 1]
                    v0 = ring_index / max(1, len(rings) - 1)
                    v1 = (ring_index + 1) / max(
                        1, len(rings) - 1
                    )
                    for longitude in range(longitude_segments):
                        following = (
                            longitude + 1
                        ) % longitude_segments
                        u0 = longitude / longitude_segments
                        u1 = (
                            longitude + 1
                        ) / longitude_segments
                        add_face(
                            (
                                lower[longitude],
                                lower[following],
                                upper[following],
                                upper[longitude],
                            ),
                            nucleus_material,
                            (
                                (u0, v0),
                                (u1, v0),
                                (u1, v1),
                                (u0, v1),
                            ),
                            choose_variant(
                                face_index,
                                texture_offset
                                + 6000
                                + ring_index * longitude_segments
                                + longitude,
                            ),
                            3,
                        )
                nucleus_count += 1
                nucleus_triangle_count += expected_nucleus_triangles

    constructed_edge_counts = {}
    for face in faces:
        for index, first in enumerate(face):
            edge = tuple(sorted((int(first), int(face[(index + 1) % len(face)]))))
            constructed_edge_counts[edge] = constructed_edge_counts.get(edge, 0) + 1
    invalid_edges = {edge: count for edge, count in constructed_edge_counts.items() if count != 2}
    if invalid_edges:
        samples = ", ".join(f"{edge}:{count}" for edge, count in sorted(invalid_edges.items())[:6])
        raise RuntimeError(
            f"Raised gore source selection cannot form a closed manifold shell "
            f"({len(invalid_edges)} invalid edges; {samples})."
        )

    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    target_collection = source.users_collection[0] if source.users_collection else bpy.context.scene.collection
    target_collection.objects.link(obj)
    _copy_gore_skinning(source, obj, generated_source_blends)
    material_names = []
    for material_id in trauma_field.RAISED_GORE_MATERIAL_IDS:
        material = _ensure_gore_material(material_id, overlay)
        mesh.materials.append(material)
        material_names.append(material.name)
    for polygon_index, (polygon, material_index) in enumerate(zip(mesh.polygons, material_indices)):
        polygon.material_index = material_index
        polygon.use_smooth = face_layers[polygon_index] in {1, 3}
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon_index, polygon in enumerate(mesh.polygons):
        local_uvs = face_uvs[polygon_index]
        variant = face_texture_variants[polygon_index]
        for loop_index, local_uv in zip(polygon.loop_indices, local_uvs):
            uv_layer.data[loop_index].uv = _gore_atlas_uv(local_uv, variant)
    source_attribute = mesh.attributes.new(name="DSB_Gore_Source_Vertex", type='INT', domain='POINT')
    for index, source_index in enumerate(generated_source_indices):
        source_attribute.data[index].value = int(source_index)
    surface_attribute = mesh.attributes.new(name="DSB_Gore_Source_Position", type='FLOAT_VECTOR', domain='POINT')
    for index, source_position in enumerate(generated_surface_positions):
        surface_attribute.data[index].vector = source_position
    variant_attribute = mesh.attributes.new(name="DSB_Gore_Texture_Variant", type='INT', domain='FACE')
    layer_attribute = mesh.attributes.new(name="DSB_Gore_Layer", type='INT', domain='FACE')
    for index, variant in enumerate(face_texture_variants):
        variant_attribute.data[index].value = int(variant)
        layer_attribute.data[index].value = int(face_layers[index])
    mesh.calc_loop_triangles()
    triangle_count = len(mesh.loop_triangles)
    mesh_id = GORE_MESH_ID_PREFIX + hashlib.sha256(
        f"{region_id}|{key_name}|{pair_role}|{component}".encode("utf-8")
    ).hexdigest()[:20]
    obj["dsb_damage_generated"] = True
    obj["dsb_gore_owned"] = True
    obj["dsb_generated_role"] = GORE_OBJECT_ROLE
    obj["dsb_preview_only"] = bool(preview)
    obj["dsb_gore_mesh_id"] = mesh_id
    obj["dsb_gore_region_id"] = str(region_id)
    obj["dsb_gore_deformation_key"] = str(key_name)
    obj["dsb_gore_pair_role"] = str(pair_role).upper()
    obj["dsb_gore_component"] = str(component or "RAISED").upper()
    obj["dsb_gore_geometry_mode"] = "LEGACY_RAISED"
    obj["dsb_gore_identity_id"] = str(overlay.get("goreIdentityId", overlay["gorePresetId"]))
    obj["dsb_gore_source_object"] = source.name
    obj["dsb_gore_source_topology_fingerprint"] = _topology_fingerprint(source)
    obj["dsb_gore_recipe_digest"] = trauma_field.gore_overlay_digest(overlay)
    obj["dsb_gore_material_ids"] = json.dumps(
        list(trauma_field.RAISED_GORE_MATERIAL_IDS)
    )
    obj["dsb_gore_material_names"] = json.dumps(material_names)
    obj["dsb_gore_texture_enabled"] = textured
    obj["dsb_gore_texture_variants"] = json.dumps(list(trauma_field.GORE_TEXTURE_VARIANTS))
    obj["dsb_gore_inner_rim_enabled"] = bool(overlay["goreInnerRimEnabled"])
    obj["dsb_gore_surface_mass"] = float(
        overlay["goreSurfaceMass"]
    )
    obj["dsb_gore_nucleus_amount"] = nucleus_amount
    obj["dsb_gore_nucleus_lobes"] = float(
        overlay["goreNucleusLobes"]
    )
    obj["dsb_gore_nucleus_triangle_count"] = (
        nucleus_triangle_count
    )
    obj["dsb_gore_nucleus_count"] = nucleus_count
    obj["dsb_gore_nucleus_depth_fraction"] = 1.0 / 3.0
    obj["dsb_gore_default_visible"] = False
    obj["dsb_gore_activation_weight"] = float(overlay["goreActivationWeight"])
    obj["dsb_gore_triangle_count"] = triangle_count
    obj["dsb_gore_shell_quality"] = (
        "COHESIVE_SURFACE_MASS_DISTRIBUTED_NUCLEI_V5"
    )
    obj["dsb_gore_mesh_geometry_digest"] = _mesh_digest(obj)
    obj.hide_render = True
    obj.hide_set(not preview)
    return obj


def _build_cavity_inlay_object(
    source,
    key_name,
    region_id,
    pair_role,
    overlay,
    face_records,
    *,
    preview=False,
    component="",
):
    stable_name = trauma_field.gore_generated_object_name(
        region_id, key_name, pair_role, component
    )
    name = stable_name + "__PREVIEW" if preview else stable_name
    if bpy.data.objects.get(name) is not None:
        raise RuntimeError(f"Cavity/inlay object name {name!r} was not cleared before rebuild.")
    source_world = _evaluated_world_matrix(source)
    inverse_world = source_world.inverted()
    local_positions = _deformation_local_points(source, key_name)
    source_faces = [
        tuple(int(index) for index in polygon.vertices)
        for polygon in source.data.polygons
    ]
    local_normals = _local_vertex_normals(local_positions, source_faces)
    normal_matrix = source_world.to_3x3().inverted().transposed()
    world_positions = [tuple(source_world @ position) for position in local_positions]
    world_normals = []
    for normal in local_normals:
        world_normal = normal_matrix @ normal
        if world_normal.length_squared <= 1e-16:
            world_normal = Vector((0.0, 0.0, 1.0))
        world_normals.append(tuple(world_normal.normalized()))
    material_roles = {
        "WET": "DSB_GORE_WET_CRIMSON",
        "CLOT": "DSB_GORE_DARK_CLOT",
        "EDGE": "DSB_GORE_ROUGH_EDGE",
        "BED": "DSB_GORE_DEEP_WOUND_BED",
        "TISSUE": "DSB_GORE_CRUSHED_TISSUE",
        "BONE": "DSB_GORE_EXPOSED_BONE",
    }
    generated = cavity_service.build_cavity_inlay(
        world_positions,
        world_normals,
        face_records,
        overlay,
        material_roles,
    )
    integrity_errors = cavity_service.edge_use_errors(generated["faces"])
    if integrity_errors:
        raise RuntimeError("; ".join(integrity_errors))
    vertices = [tuple(inverse_world @ Vector(value)) for value in generated["vertices"]]
    local_surface_positions = [
        tuple(inverse_world @ Vector(value)) for value in generated["surfacePositions"]
    ]
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(vertices, [], generated["faces"])
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    target_collection = (
        source.users_collection[0]
        if source.users_collection
        else bpy.context.scene.collection
    )
    target_collection.objects.link(obj)
    _copy_gore_skinning(
        source,
        obj,
        generated["sourceBlends"],
        require_deform=True,
    )
    material_names = []
    for material_id in generated["materialIds"]:
        material = _ensure_gore_material(material_id, overlay)
        mesh.materials.append(material)
        material_names.append(material.name)
    face_layers = list(generated["faceLayers"])
    texture_variants = list(generated["textureVariants"])
    for polygon_index, (polygon, material_index) in enumerate(
        zip(mesh.polygons, generated["materialIndices"])
    ):
        polygon.material_index = int(material_index)
        polygon.use_smooth = int(face_layers[polygon_index]) in {
            cavity_service.LAYER_CLOT,
            cavity_service.LAYER_TISSUE,
            cavity_service.LAYER_LINER,
        }
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon_index, polygon in enumerate(mesh.polygons):
        count = len(polygon.loop_indices)
        variant = int(texture_variants[polygon_index])
        for loop_offset, loop_index in enumerate(polygon.loop_indices):
            angle = (2.0 * math.pi * loop_offset / max(3, count)) - math.pi * 0.5
            local_uv = (0.5 + math.cos(angle) * 0.45, 0.5 + math.sin(angle) * 0.45)
            uv_layer.data[loop_index].uv = _gore_atlas_uv(local_uv, variant)
    source_attribute = mesh.attributes.new(
        name="DSB_Gore_Source_Vertex", type="INT", domain="POINT"
    )
    surface_attribute = mesh.attributes.new(
        name="DSB_Gore_Source_Position", type="FLOAT_VECTOR", domain="POINT"
    )
    normal_attribute = mesh.attributes.new(
        name="DSB_Gore_Source_Normal_World", type="FLOAT_VECTOR", domain="POINT"
    )
    depth_attribute = mesh.attributes.new(
        name="DSB_Gore_Inward_Depth", type="FLOAT", domain="POINT"
    )
    for index, source_index in enumerate(generated["sourceIndices"]):
        source_attribute.data[index].value = int(source_index)
        surface_attribute.data[index].vector = local_surface_positions[index]
        normal_attribute.data[index].vector = generated["sourceNormals"][index]
        depth_attribute.data[index].value = float(generated["vertexDepths"][index])
    variant_attribute = mesh.attributes.new(
        name="DSB_Gore_Texture_Variant", type="INT", domain="FACE"
    )
    layer_attribute = mesh.attributes.new(
        name="DSB_Gore_Layer", type="INT", domain="FACE"
    )
    for index, variant in enumerate(texture_variants):
        variant_attribute.data[index].value = int(variant)
        layer_attribute.data[index].value = int(face_layers[index])
    mesh.calc_loop_triangles()
    triangle_count = len(mesh.loop_triangles)
    if triangle_count != int(generated["metrics"]["triangleCount"]):
        raise RuntimeError(
            "Cavity/inlay triangle accounting changed during Blender mesh construction."
        )
    mesh_id = GORE_MESH_ID_PREFIX + hashlib.sha256(
        f"{region_id}|{key_name}|{pair_role}|{component}".encode("utf-8")
    ).hexdigest()[:20]
    obj["dsb_damage_generated"] = True
    obj["dsb_gore_owned"] = True
    obj["dsb_generated_role"] = GORE_OBJECT_ROLE
    obj["dsb_preview_only"] = bool(preview)
    obj["dsb_gore_mesh_id"] = mesh_id
    obj["dsb_gore_region_id"] = str(region_id)
    obj["dsb_gore_deformation_key"] = str(key_name)
    obj["dsb_gore_pair_role"] = str(pair_role).upper()
    obj["dsb_gore_component"] = str(component or "INLAY").upper()
    obj["dsb_gore_geometry_mode"] = "CAVITY_INLAY"
    obj["dsb_gore_identity_id"] = str(overlay["goreIdentityId"])
    obj["dsb_gore_source_object"] = source.name
    obj["dsb_gore_source_topology_fingerprint"] = _topology_fingerprint(source)
    obj["dsb_gore_recipe_digest"] = trauma_field.gore_overlay_digest(overlay)
    obj["dsb_gore_material_ids"] = json.dumps(list(generated["materialIds"]))
    obj["dsb_gore_material_names"] = json.dumps(material_names)
    obj["dsb_gore_texture_enabled"] = bool(overlay["goreTextureEnabled"])
    obj["dsb_gore_texture_variants"] = json.dumps(
        list(trauma_field.GORE_TEXTURE_VARIANTS)
    )
    obj["dsb_gore_inner_rim_enabled"] = bool(overlay["goreBarrierLayerEnabled"])
    obj["dsb_gore_internal_fragments"] = bool(generated["internalFragments"])
    obj["dsb_gore_default_visible"] = False
    obj["dsb_gore_activation_weight"] = float(overlay["goreActivationWeight"])
    obj["dsb_gore_triangle_count"] = triangle_count
    obj["dsb_gore_shell_quality"] = "CAVITY_INLAY_RECESSED_MANIFOLD_V4"
    obj["dsb_gore_validation_measurements"] = json.dumps(
        generated["metrics"], sort_keys=True, separators=(",", ":")
    )
    obj["dsb_gore_layer_depths"] = json.dumps(
        generated["metrics"]["layerDepths"], sort_keys=True, separators=(",", ":")
    )
    obj["dsb_gore_mesh_geometry_digest"] = _mesh_digest(obj)
    obj.hide_render = True
    obj.hide_set(not preview)
    return obj


def _expected_raised_gore_inputs(region, attached, detached, key_name, entry):
    overlay = trauma_field.normalize_gore_overlay(entry.get("surfaceGoreOverlay", {}))
    stamp = next(
        (stamp for stamp in entry.get("stamps", []) if stamp.get("stampId") == overlay.get("linkedStampId")),
        None,
    )
    if stamp is None:
        raise RuntimeError("The linked trauma stamp no longer exists.")
    capture = stamp.get("capture", {})
    errors = _capture_errors(capture, region, attached)
    if str(capture.get("selectionHash", "")) != str(overlay.get("linkedSelectionHash", "")):
        errors.append("The linked stamp capture changed; apply the gore recipe again before rebuilding.")
    if str(capture.get("topologyFingerprint", "")) != str(overlay.get("linkedCaptureTopologyFingerprint", "")):
        errors.append("The linked stamp topology changed; apply the gore recipe again before rebuilding.")
    if errors:
        raise RuntimeError(" ".join(errors))
    topology = _topology_fingerprint(attached)
    capture_hash = str(capture.get("selectionHash", ""))
    sources = _region_gore_sources(region, attached, detached)
    deformation_digests = {
        role: _deformation_input_digest(source, key_name)
        for source, role in sources
    }
    weights, _distances = _stamp_weights(attached, region, stamp)
    basis = _ensure_basis(attached)
    target = _key(attached, key_name)
    if target is None:
        raise RuntimeError(f"The deformation key {key_name!r} is missing.")
    basis_world = [attached.matrix_world @ point.co for point in basis.data]
    target_world = [attached.matrix_world @ point.co for point in target.data]
    displacement = [
        (deformed - original).length
        for original, deformed in zip(basis_world, target_world)
    ]
    components = trauma_field.gore_component_recipes(overlay)
    component_inputs = []
    generation_digests = {}
    for component, component_overlay in components:
        cache_key = hashlib.sha256(
            (
                trauma_field.gore_overlay_digest(component_overlay)
                + "|"
                + topology
                + "|"
                + deformation_digests.get(
                    "ATTACHED", deformation_digests.get("CORE", "")
                )
                + "|"
                + capture_hash
                + "|"
                + component
            ).encode("utf-8")
        ).hexdigest()

        def evaluate_records(recipe=component_overlay):
            return trauma_field.gore_face_records(
                [tuple(point) for point in target_world],
                mesh_snapshot.faces(attached),
                weights,
                displacement,
                recipe,
            )

        records, _cache_hit = gore_service.face_records(
            cache_key, evaluate_records
        )
        if not records:
            raise RuntimeError(
                f"The linked capture produced no {component.lower()} gore geometry "
                "faces at the current coverage, density, and breakup settings."
            )
        component_inputs.append((component, component_overlay, records))
        multi_component = len(components) > 1
        for _source, role in sources:
            storage_key = f"{role}:{component}" if multi_component else role
            generation_digests[storage_key] = (
                trauma_field.raised_gore_geometry_digest(
                    component_overlay,
                    source_topology_fingerprint=topology,
                    deformation_digest=deformation_digests[role],
                    capture_hash=capture_hash,
                    pair_role=storage_key,
                    face_records=records,
                )
            )
    return (
        overlay,
        stamp,
        component_inputs,
        topology,
        capture_hash,
        deformation_digests,
        generation_digests,
    )


def rebuild_raised_gore_for_key(region, attached, detached, key_name, entry):
    """Regenerate one core shell or matching paired shells from one recipe."""

    overlay, stamp, component_inputs, topology, capture_hash, deformation_digests, generation_digests = (
        _expected_raised_gore_inputs(region, attached, detached, key_name, entry)
    )
    region_id = str(region.get("regionId", ""))
    previous = list(generated_gore_objects(region_id, key_name))
    previous_state = []
    for index, obj in enumerate(previous):
        mesh = obj.data if obj.type == 'MESH' else None
        previous_state.append((obj, obj.name, mesh, mesh.name if mesh is not None else ""))
        obj.name = f"__DSB_GORE_ROLLBACK_{index:03d}"
        if mesh is not None:
            mesh.name = f"__DSB_GORE_MESH_ROLLBACK_{index:03d}"
    built = []
    try:
        multi_component = len(component_inputs) > 1
        for component, component_overlay, records in component_inputs:
            for source, role in _region_gore_sources(
                region, attached, detached
            ):
                builder = (
                    _build_cavity_inlay_object
                    if component_overlay["goreGeometryMode"] == "CAVITY_INLAY"
                    else _build_gore_shell_object
                )
                storage_key = (
                    f"{role}:{component}" if multi_component else role
                )
                obj = builder(
                    source,
                    key_name,
                    region_id,
                    role,
                    component_overlay,
                    records,
                    component=component if multi_component else "",
                )
                obj["dsb_gore_parent_recipe_digest"] = (
                    trauma_field.gore_overlay_digest(overlay)
                )
                obj["dsb_gore_linked_stamp_id"] = str(
                    stamp.get("stampId", "")
                )
                obj["dsb_gore_capture_hash"] = capture_hash
                obj["dsb_gore_deformation_digest"] = deformation_digests[role]
                obj["dsb_gore_generation_digest"] = generation_digests[
                    storage_key
                ]
                built.append(obj)
    except Exception:
        expected_names = set()
        multi_component = len(component_inputs) > 1
        for component, _component_overlay, _records in component_inputs:
            for _source, role in _region_gore_sources(
                region, attached, detached
            ):
                expected_names.add(
                    trauma_field.gore_generated_object_name(
                        region_id,
                        key_name,
                        role,
                        component if multi_component else "",
                    )
                )
        for name in expected_names:
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            mesh = obj.data if obj.type == 'MESH' else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        for obj, object_name, mesh, mesh_name in previous_state:
            obj.name = object_name
            if mesh is not None:
                mesh.name = mesh_name
        raise
    for obj, _object_name, mesh, _mesh_name in previous_state:
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    entry["raisedGoreStatus"] = "READY"
    entry["goreGeometryMode"] = str(overlay["goreGeometryMode"])
    entry["goreIdentityId"] = str(overlay["goreIdentityId"])
    entry["goreGeneratedMeshIds"] = [str(obj["dsb_gore_mesh_id"]) for obj in built]
    entry["goreGeneratedNodeNames"] = [obj.name for obj in built]
    multi_component = len(component_inputs) > 1
    entry["goreGeometryDigests"] = {
        (
            f"{obj['dsb_gore_pair_role']}:{obj['dsb_gore_component']}"
            if multi_component
            else str(obj["dsb_gore_pair_role"])
        ): str(obj["dsb_gore_mesh_geometry_digest"])
        for obj in built
    }
    entry["goreGenerationDigests"] = dict(generation_digests)
    entry["goreTriangleCounts"] = {
        (
            f"{obj['dsb_gore_pair_role']}:{obj['dsb_gore_component']}"
            if multi_component
            else str(obj["dsb_gore_pair_role"])
        ): int(obj["dsb_gore_triangle_count"])
        for obj in built
    }
    entry["goreMaterialIds"] = sorted({
        material_id
        for obj in built
        for material_id in json.loads(str(obj["dsb_gore_material_ids"]))
    })
    entry["goreMaterialNames"] = sorted({
        material_name
        for obj in built
        for material_name in json.loads(str(obj["dsb_gore_material_names"]))
    })
    entry["goreGeneratedAtBuild"] = DEFORMATION_BUILD_ID
    entry["goreValidationMeasurements"] = {
        (
            f"{obj['dsb_gore_pair_role']}:{obj['dsb_gore_component']}"
            if multi_component
            else str(obj["dsb_gore_pair_role"])
        ): json.loads(
            str(obj.get("dsb_gore_validation_measurements", "{}"))
        )
        for obj in built
        if obj.get("dsb_gore_validation_measurements")
    }
    return built


def rebuild_current_raised_gore(context):
    settings, _registry, region, attached, detached, payload, name, entry = _active_key_context(context)
    overlay = trauma_field.normalize_gore_overlay(entry.get("surfaceGoreOverlay", {}))
    if not overlay["goreOverlayEnabled"] or not overlay["goreRaisedEnabled"]:
        raise RuntimeError("Enable raised gore and apply its settings before rebuilding geometry.")
    built = rebuild_raised_gore_for_key(region, attached, detached, name, entry)
    _store_metadata(attached, detached, payload)
    _set_authoring_view(attached, detached, 'ATTACHED', context)
    settings.deformation_status = (
        f"{overlay['goreGeometryMode']} GORE READY - {name} / "
        f"{sum(int(obj['dsb_gore_triangle_count']) for obj in built)} triangles"
    )
    return built


def rebuild_all_generated_gore(context=None):
    registry = _load_registry()
    rebuilt = []
    skipped = []
    failed = []
    for region in registry.get("regions", []):
        try:
            attached, detached = _resolve_region_pair(region)
            contract = validate_region_contract(region, attached, detached)
            if contract["status"] != "PASS":
                raise RuntimeError(" ".join(contract["errors"]))
        except Exception as exc:
            failed.append(f"{region.get('regionId', '<missing>')}: {exc}")
            continue
        payload = _metadata(attached)
        changed = False
        for key_name in _managed_names(attached):
            entry = payload.get("keys", {}).get(key_name, {})
            try:
                overlay = trauma_field.normalize_gore_overlay(entry.get("surfaceGoreOverlay", {}))
            except (TypeError, ValueError):
                failed.append(f"{region.get('regionId')}/{key_name}: broken recipe")
                continue
            if not overlay["goreOverlayEnabled"] or not overlay["goreRaisedEnabled"]:
                skipped.append(f"{region.get('regionId')}/{key_name}")
                continue
            try:
                objects = rebuild_raised_gore_for_key(region, attached, detached, key_name, entry)
                rebuilt.append((str(region.get("regionId", "")), key_name, objects))
                changed = True
            except Exception as exc:
                failed.append(f"{region.get('regionId')}/{key_name}: {exc}")
        if changed:
            _store_metadata(attached, detached, payload)
    return {"rebuilt": rebuilt, "skipped": skipped, "failed": failed}


def apply_heavy_gore_to_all_deformations(context):
    """Apply the heavy preset generically to every valid authored key."""

    registry = _load_registry()
    applied = []
    skipped = []
    failed = []
    for region in registry.get("regions", []):
        region_id = str(region.get("regionId", ""))
        try:
            attached, detached = _resolve_region_pair(region)
            contract = validate_region_contract(region, attached, detached)
            if contract["status"] != "PASS":
                raise RuntimeError(" ".join(contract["errors"]))
        except Exception as exc:
            failed.append(f"{region_id or '<missing>'}: {exc}")
            continue
        payload = _metadata(attached)
        changed = False
        for key_name in _managed_names(attached):
            entry = payload.get("keys", {}).get(key_name, {})
            existing = entry.get("surfaceGoreOverlay")
            try:
                existing_recipe = trauma_field.normalize_gore_overlay(existing) if existing else None
            except (TypeError, ValueError) as exc:
                failed.append(f"{region_id}/{key_name}: broken existing recipe ({exc})")
                continue
            if existing_recipe and existing_recipe.get("goreUserCustomized", False):
                skipped.append(f"{region_id}/{key_name}: user-customized recipe")
                continue
            enabled_stamps = [stamp for stamp in entry.get("stamps", []) if bool(stamp.get("enabled", True))]
            linked_id = str(existing_recipe.get("linkedStampId", "")) if existing_recipe else ""
            stamp = next((item for item in enabled_stamps if str(item.get("stampId", "")) == linked_id), None)
            stamp = stamp or (enabled_stamps[0] if enabled_stamps else None)
            if stamp is None:
                failed.append(f"{region_id}/{key_name}: no enabled trauma stamp")
                continue
            capture = stamp.get("capture", {})
            capture_errors = _capture_errors(capture, region, attached)
            if capture_errors:
                failed.append(f"{region_id}/{key_name}: {' '.join(capture_errors)}")
                continue
            recipe = trauma_field.default_gore_overlay(
                "Gore_Bloody_Crater",
                enabled=True,
                region_id=region_id,
                linked_stamp_id=str(stamp.get("stampId", "")),
                selection_hash=str(capture.get("selectionHash", "")),
                topology_fingerprint=str(capture.get("topologyFingerprint", "")),
                seed=int(existing_recipe.get("goreMaskSeed", 1776)) if existing_recipe else 1776,
            )
            candidate = copy.deepcopy(entry)
            candidate["surfaceGoreOverlay"] = recipe
            candidate["goreOverlayDigest"] = trauma_field.gore_overlay_digest(recipe)
            backup = copy.deepcopy(entry)
            try:
                _expected_raised_gore_inputs(region, attached, detached, key_name, candidate)
                for _source, role in _region_gore_sources(region, attached, detached):
                    node_name = trauma_field.gore_generated_object_name(region_id, key_name, role)
                    occupied = bpy.data.objects.get(node_name)
                    if occupied is not None and not bool(occupied.get("dsb_gore_owned", False)):
                        raise RuntimeError(f"generated node name {node_name!r} is occupied by user data")
                for material_id in trauma_field.gore_material_ids_for_mode(
                    recipe["goreGeometryMode"]
                ):
                    material_name = _gore_material_name(material_id, recipe)
                    occupied = bpy.data.materials.get(material_name)
                    if occupied is not None and not bool(occupied.get("dsb_gore_material", False)):
                        raise RuntimeError(f"generated material name {material_name!r} is occupied by user data")
                entry.update({
                    "surfaceGoreOverlay": recipe,
                    "goreOverlayDigest": trauma_field.gore_overlay_digest(recipe),
                    "raisedGoreStatus": "STALE_REBUILD_REQUIRED",
                })
                rebuild_raised_gore_for_key(region, attached, detached, key_name, entry)
                applied.append(f"{region_id}/{key_name}")
                changed = True
            except Exception as exc:
                entry.clear()
                entry.update(backup)
                failed.append(f"{region_id}/{key_name}: {exc}")
        if changed:
            _store_metadata(attached, detached, payload)
    return {"applied": applied, "skipped": skipped, "failed": failed}


def _gltf_gore_material_errors(material, expected_id, overlay):
    errors = []
    if material is None:
        return [f"Raised gore material {expected_id} is missing."]
    if not material.get("dsb_gore_material", False):
        errors.append(f"Material {material.name} is not Forge-owned raised gore data.")
    if str(material.get("dsb_gore_material_id", "")) != expected_id:
        errors.append(f"Material {material.name} has the wrong semantic gore material ID.")
    if not material.use_nodes or material.node_tree is None:
        errors.append(f"Material {material.name} has no glTF-safe node surface.")
        return errors
    allowed = {'ShaderNodeOutputMaterial', 'ShaderNodeBsdfPrincipled', 'ShaderNodeTexImage'}
    unsupported = sorted({node.bl_idname for node in material.node_tree.nodes if node.bl_idname not in allowed})
    if unsupported:
        errors.append(f"Material {material.name} uses unsupported glTF nodes: {', '.join(unsupported)}.")
    shaders = [node for node in material.node_tree.nodes if node.bl_idname == 'ShaderNodeBsdfPrincipled']
    outputs = [node for node in material.node_tree.nodes if node.bl_idname == 'ShaderNodeOutputMaterial']
    if len(shaders) != 1 or len(outputs) != 1:
        errors.append(f"Material {material.name} must contain one Principled shader and one output.")
    elif not outputs[0].inputs["Surface"].is_linked:
        errors.append(f"Material {material.name} has no linked material output.")
    if shaders:
        shader = shaders[0]
        metallic = float(shader.inputs["Metallic"].default_value)
        if abs(metallic) > 1e-8:
            errors.append(f"Material {material.name} must keep Metallic at zero.")
        emission = shader.inputs.get("Emission Color")
        if emission is None:
            emission = shader.inputs.get("Emission")
        emission_strength = shader.inputs.get("Emission Strength")
        if emission is not None:
            strength = float(emission_strength.default_value) if emission_strength is not None else 1.0
            if (
                emission.is_linked
                or (emission_strength is not None and emission_strength.is_linked)
                or trauma_field.has_effective_emission(emission.default_value, strength)
            ):
                errors.append(f"Material {material.name} must not use emission to fake wetness.")
        texture_nodes = [node for node in material.node_tree.nodes if node.bl_idname == 'ShaderNodeTexImage']
        textured = bool(overlay["goreTextureEnabled"])
        if bool(material.get("dsb_gore_textured", False)) != textured:
            errors.append(f"Material {material.name} has stale textured-gore metadata.")
        for field in ("goreFiberTextureStrength", "goreBaseColorStrength"):
            metadata_field = (
                "dsb_gore_fiber_texture_strength"
                if field == "goreFiberTextureStrength" else "dsb_gore_base_color_strength"
            )
            if abs(float(material.get(metadata_field, -1.0)) - float(overlay[field])) > 1e-8:
                errors.append(f"Material {material.name} has stale {field} composition metadata.")
        if textured:
            if len(texture_nodes) != 1 or texture_nodes[0].image is None:
                errors.append(f"Material {material.name} has no composed fiber/color texture.")
            elif not bool(texture_nodes[0].image.get("dsb_gore_composed_texture", False)):
                errors.append(f"Material {material.name} uses an unowned fiber/color composition.")
            if not shader.inputs["Base Color"].is_linked:
                errors.append(f"Material {material.name} does not feed the fiber atlas into Base Color.")
        elif texture_nodes:
            errors.append(f"Material {material.name} retains texture nodes although texturing is disabled.")
    return errors


def _raised_gore_mesh_errors(obj, source, key_name, overlay, expected_role):
    errors = []
    if obj is None or obj.type != 'MESH':
        return [f"Raised gore {expected_role.lower()} mesh is missing."]
    if not bool(obj.get("dsb_gore_owned", False)) or obj.get("dsb_generated_role") != GORE_OBJECT_ROLE:
        errors.append(f"Raised gore object {obj.name} has missing Forge ownership metadata.")
    if bool(obj.get("dsb_preview_only", True)):
        errors.append(f"Raised gore object {obj.name} is incorrectly marked preview-only.")
    if bool(obj.get("dsb_gore_default_visible", True)) or not obj.hide_render:
        errors.append(f"Raised gore object {obj.name} is visible by default; the export contract requires inactive gore.")
    obj_world = _evaluated_world_matrix(obj)
    source_world = _evaluated_world_matrix(source)
    transform_error = max(
        abs(float(obj_world[row][column] - source_world[row][column]))
        for row in range(4) for column in range(4)
    )
    if transform_error > 1e-8:
        errors.append(f"Raised gore object {obj.name} transform no longer matches its source surface.")
    mesh = obj.data
    geometry_mode = str(overlay.get("goreGeometryMode", "LEGACY_RAISED"))
    expected_material_ids = trauma_field.gore_material_ids_for_mode(geometry_mode)
    if str(obj.get("dsb_gore_geometry_mode", "")) != geometry_mode:
        errors.append(f"Gore object {obj.name} has stale or missing geometry-mode metadata.")
    if len(mesh.vertices) == 0 or len(mesh.polygons) == 0:
        errors.append(f"Raised gore object {obj.name} is empty.")
        return errors
    if len(mesh.materials) != len(expected_material_ids):
        errors.append(
            f"Gore object {obj.name} must use exactly {len(expected_material_ids)} "
            f"{geometry_mode} material slots."
        )
    assigned_ids = []
    for material in mesh.materials:
        assigned_ids.append(str(material.get("dsb_gore_material_id", "")) if material else "")
    if tuple(assigned_ids) != tuple(expected_material_ids):
        errors.append(f"Raised gore object {obj.name} has a missing or reordered material assignment.")
    for index, material_id in enumerate(expected_material_ids):
        material = mesh.materials[index] if index < len(mesh.materials) else None
        errors.extend(_gltf_gore_material_errors(material, material_id, overlay))
    if any(int(polygon.material_index) >= len(mesh.materials) for polygon in mesh.polygons):
        errors.append(f"Raised gore object {obj.name} contains an invalid material index.")
    if bool(overlay["goreTextureEnabled"]):
        if not mesh.uv_layers or mesh.uv_layers.active is None:
            errors.append(f"Raised gore object {obj.name} has no fiber-atlas UV map.")
        variant_attribute = mesh.attributes.get("DSB_Gore_Texture_Variant")
        if variant_attribute is None or len(variant_attribute.data) != len(mesh.polygons):
            errors.append(f"Raised gore object {obj.name} has no per-face fiber direction attribute.")
        elif any(
            int(record.value) < 0 or int(record.value) >= len(trauma_field.GORE_TEXTURE_VARIANTS)
            for record in variant_attribute.data
        ):
            errors.append(f"Raised gore object {obj.name} contains an invalid fiber direction index.")
    layer_attribute = mesh.attributes.get("DSB_Gore_Layer")
    if layer_attribute is None or len(layer_attribute.data) != len(mesh.polygons):
        errors.append(f"Raised gore object {obj.name} has no multilayer gore classification.")
    else:
        layer_values = {int(record.value) for record in layer_attribute.data}
        if geometry_mode == "LEGACY_RAISED" and (
            bool(overlay["goreInnerRimEnabled"])
            and float(overlay["goreInnerRimStrength"]) > 1e-8
            and 2 not in layer_values
        ):
            errors.append(f"Raised gore object {obj.name} has no compromised inner-reddening layer.")
        if geometry_mode == "CAVITY_INLAY":
            required_layers = {cavity_service.LAYER_RIM, cavity_service.LAYER_LINER}
            if bool(overlay["goreClotLayerEnabled"]):
                required_layers.add(cavity_service.LAYER_CLOT)
            if bool(overlay["goreTissueLayerEnabled"]):
                required_layers.add(cavity_service.LAYER_TISSUE)
            if bool(overlay["goreBoneLayerEnabled"]):
                required_layers.add(cavity_service.LAYER_BONE)
            if bool(overlay["goreBarrierLayerEnabled"]):
                required_layers.add(cavity_service.LAYER_BARRIER)
            missing_layers = sorted(required_layers - layer_values)
            if missing_layers:
                errors.append(
                    f"Cavity/inlay object {obj.name} is missing enabled layer codes {missing_layers}."
                )

    duplicate_faces = set()
    seen_faces = set()
    edge_counts = {}
    edge_directions = {}
    for polygon in mesh.polygons:
        if float(polygon.area) <= 1e-14 or len(set(int(value) for value in polygon.vertices)) < 3:
            errors.append(f"Raised gore object {obj.name} contains degenerate geometry.")
            break
        face_key = tuple(sorted(int(value) for value in polygon.vertices))
        if face_key in seen_faces:
            duplicate_faces.add(face_key)
        seen_faces.add(face_key)
        vertices = [int(value) for value in polygon.vertices]
        for edge_index, first in enumerate(vertices):
            second = vertices[(edge_index + 1) % len(vertices)]
            edge = tuple(sorted((first, second)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            edge_directions.setdefault(edge, []).append((first, second))
    if duplicate_faces:
        errors.append(f"Raised gore object {obj.name} contains duplicate faces.")
    non_manifold = sum(count != 2 for count in edge_counts.values())
    if non_manifold:
        errors.append(f"Raised gore object {obj.name} contains {non_manifold} non-manifold boundary edges.")
    inconsistent_winding = sum(
        len(directions) == 2 and directions[0] == directions[1]
        for directions in edge_directions.values()
    )
    if inconsistent_winding:
        errors.append(
            f"Gore object {obj.name} contains {inconsistent_winding} "
            "inconsistently wound shared edges."
        )
    mesh.calc_loop_triangles()
    triangle_count = len(mesh.loop_triangles)
    if triangle_count != int(obj.get("dsb_gore_triangle_count", -1)):
        errors.append(f"Raised gore object {obj.name} triangle metadata is stale.")
    errors.extend(trauma_field.raised_gore_budget_errors(
        [triangle_count], per_deformation_limit=int(overlay["goreMaximumTriangles"]),
        total_limit=trauma_field.GORE_MAX_TRIANGLES_PER_ASSET,
    ))
    actual_digest = _mesh_digest(obj)
    if actual_digest != str(obj.get("dsb_gore_mesh_geometry_digest", "")):
        errors.append(f"Raised gore object {obj.name} geometry digest does not match; the generated mesh was altered.")

    source_armatures = {modifier.object for modifier in source.modifiers if modifier.type == 'ARMATURE'}
    gore_armatures = {modifier.object for modifier in obj.modifiers if modifier.type == 'ARMATURE'}
    if source_armatures != gore_armatures:
        errors.append(f"Raised gore object {obj.name} does not preserve the source armature linkage.")
    attribute = mesh.attributes.get("DSB_Gore_Source_Vertex")
    surface_attribute = mesh.attributes.get("DSB_Gore_Source_Position")
    if attribute is None or len(attribute.data) != len(mesh.vertices):
        errors.append(f"Raised gore object {obj.name} has no valid source-vertex ownership attribute.")
    elif surface_attribute is None or len(surface_attribute.data) != len(mesh.vertices):
        errors.append(f"Raised gore object {obj.name} has no refined source-surface position attribute.")
    else:
        deformed = _deformation_local_points(source, key_name)
        maximum_distance = 0.0
        for vertex, source_record, surface_record in zip(mesh.vertices, attribute.data, surface_attribute.data):
            source_index = int(source_record.value)
            if source_index < 0 or source_index >= len(deformed):
                errors.append(f"Raised gore object {obj.name} references an invalid source vertex.")
                break
            distance = ((obj_world @ vertex.co) - (source_world @ Vector(surface_record.vector))).length
            maximum_distance = max(maximum_distance, distance)
        if geometry_mode == "CAVITY_INLAY":
            normal_attribute = mesh.attributes.get("DSB_Gore_Source_Normal_World")
            depth_attribute = mesh.attributes.get("DSB_Gore_Inward_Depth")
            if normal_attribute is None or len(normal_attribute.data) != len(mesh.vertices):
                errors.append(
                    f"Cavity/inlay object {obj.name} has no stable source-normal attribute."
                )
            if depth_attribute is None or len(depth_attribute.data) != len(mesh.vertices):
                errors.append(
                    f"Cavity/inlay object {obj.name} has no inward-depth measurement attribute."
                )
            if normal_attribute is not None and depth_attribute is not None:
                signed_distances = []
                inward_depths = []
                for vertex, surface_record, normal_record, depth_record in zip(
                    mesh.vertices,
                    surface_attribute.data,
                    normal_attribute.data,
                    depth_attribute.data,
                ):
                    generated_world = obj_world @ vertex.co
                    surface_world = source_world @ Vector(surface_record.vector)
                    stable_normal = Vector(normal_record.vector)
                    if stable_normal.length_squared <= 1e-16:
                        errors.append(
                            f"Cavity/inlay object {obj.name} contains a zero source normal."
                        )
                        break
                    signed = (generated_world - surface_world).dot(stable_normal.normalized())
                    signed_distances.append(float(signed))
                    inward_depths.append(float(depth_record.value))
                    if not math.isfinite(signed) or not math.isfinite(float(depth_record.value)):
                        errors.append(
                            f"Cavity/inlay object {obj.name} contains a non-finite depth measurement."
                        )
                        break
                    if abs((-signed) - float(depth_record.value)) > 2e-5:
                        errors.append(
                            f"Cavity/inlay object {obj.name} has stale source/depth attributes."
                        )
                        break
                proudness = max((max(0.0, value) for value in signed_distances), default=0.0)
                permitted = float(overlay["goreProudnessLimit"])
                above = sum(value > permitted + 1e-7 for value in signed_distances)
                if proudness > permitted + 1e-7 or above:
                    errors.append(
                        f"Cavity/inlay object {obj.name} protrudes {proudness:.6f} m; "
                        f"permitted proudness is {permitted:.6f} m ({above} vertices exceed it)."
                    )
                minimum_separation = min(inward_depths, default=0.0)
                requested_separation = float(overlay["goreLinerSeparation"])
                if minimum_separation < requested_separation * 0.45:
                    errors.append(
                        f"Cavity/inlay object {obj.name} has z-fighting-risk separation "
                        f"{minimum_separation:.6f} m; requested liner separation is "
                        f"{requested_separation:.6f} m."
                    )
                maximum_depth = max(inward_depths, default=0.0)
                permitted_depth = (
                    float(overlay["goreCavityDepth"])
                    + requested_separation
                    + max(float(overlay["goreClotThickness"]), requested_separation) * 3.0
                )
                if maximum_depth > permitted_depth + 1e-6:
                    errors.append(
                        f"Cavity/inlay object {obj.name} exceeds its scale-relative cavity "
                        f"depth ({maximum_depth:.6f} m > {permitted_depth:.6f} m)."
                    )
            try:
                measurements = json.loads(
                    str(obj.get("dsb_gore_validation_measurements", ""))
                )
                layer_depths = json.loads(str(obj.get("dsb_gore_layer_depths", "")))
            except (TypeError, ValueError, json.JSONDecodeError):
                measurements = {}
                layer_depths = {}
            if not isinstance(measurements, dict) or not isinstance(layer_depths, dict):
                errors.append(
                    f"Cavity/inlay object {obj.name} has missing numerical validation metadata."
                )
            else:
                ordered = [
                    layer
                    for layer in ("RIM", "CLOT", "TISSUE", "LINER", "BONE")
                    if layer in layer_depths
                ]
                medians = [float(layer_depths[layer]["median"]) for layer in ordered]
                if any(second + 1e-8 < first for first, second in zip(medians, medians[1:])):
                    errors.append(
                        f"Cavity/inlay object {obj.name} has internal layers in the wrong "
                        f"depth order ({ordered})."
                    )
        else:
            allowed = (
                float(overlay["goreSurfaceOffset"])
                + float(overlay["goreClotThickness"]) * 4.0
                + 0.002
            )
            if maximum_distance > allowed:
                errors.append(
                    f"Raised gore object {obj.name} floats {maximum_distance:.6f} m "
                    f"from the deformed surface; allowed is {allowed:.6f} m."
                )
    if geometry_mode == "CAVITY_INLAY" and source_armatures:
        deform_names = {
            bone.name
            for armature in source_armatures
            for bone in getattr(getattr(armature, "data", None), "bones", ())
            if bool(getattr(bone, "use_deform", True))
        }
        group_names = {
            group.index: group.name
            for group in obj.vertex_groups
        }
        for vertex in mesh.vertices:
            influences = []
            for membership in vertex.groups:
                weight = float(membership.weight)
                name = group_names.get(int(membership.group), "")
                if not math.isfinite(weight) or weight < 0.0:
                    errors.append(
                        f"Cavity/inlay object {obj.name} vertex {vertex.index} has "
                        "a non-finite or negative skin weight."
                    )
                    break
                if name not in deform_names and weight > 1e-8:
                    errors.append(
                        f"Cavity/inlay object {obj.name} vertex {vertex.index} uses "
                        f"non-deform group {name!r}."
                    )
                    break
                if weight > 1e-8:
                    influences.append(weight)
            if len(influences) > 4:
                errors.append(
                    f"Cavity/inlay object {obj.name} vertex {vertex.index} exceeds "
                    "the four-influence export limit."
                )
                break
            total = sum(influences)
            if not influences or abs(total - 1.0) > 1e-4:
                errors.append(
                    f"Cavity/inlay object {obj.name} vertex {vertex.index} has "
                    f"invalid normalized deform-weight sum {total:.6f}."
                )
                break
    return errors


def _raised_gore_errors(region, attached, detached, key_name, entry, overlay):
    """Validate raised geometry separately from stain and deformation state."""

    region_id = str(region.get("regionId", ""))
    objects = generated_gore_objects(region_id, key_name)
    if not overlay["goreOverlayEnabled"] or not overlay["goreRaisedEnabled"]:
        return (["Raised gore helpers exist although the recipe has raised gore disabled."] if objects else []), {
            "status": "DISABLED", "nodeNames": [], "triangleCounts": {}, "errors": []
        }
    errors = []
    try:
        (_recipe, _stamp, component_inputs, topology, capture_hash,
         deformation_digests, generation_digests) = _expected_raised_gore_inputs(
            region, attached, detached, key_name, entry
        )
    except Exception as exc:
        return [str(exc)], {"status": "FAIL", "nodeNames": [obj.name for obj in objects], "triangleCounts": {}, "errors": [str(exc)]}
    sources = _region_gore_sources(region, attached, detached)
    multi_component = len(component_inputs) > 1
    expected_items = []
    for component, component_overlay, _records in component_inputs:
        for source, role in sources:
            storage_key = f"{role}:{component}" if multi_component else role
            expected_items.append({
                "component": component,
                "overlay": component_overlay,
                "source": source,
                "role": role,
                "storageKey": storage_key,
                "name": trauma_field.gore_generated_object_name(
                    region_id,
                    key_name,
                    role,
                    component if multi_component else "",
                ),
            })
    by_component_role = {
        (
            str(obj.get("dsb_gore_pair_role", "")).upper(),
            str(obj.get("dsb_gore_component", "")).upper(),
        ): obj
        for obj in objects
    }
    expected_keys = {
        (item["role"], item["component"]) for item in expected_items
    }
    if len(objects) != len(expected_items) or set(by_component_role) != expected_keys:
        errors.append(
            "Gore component ownership does not match the recipe and region mode: "
            + ", ".join(
                f"{role.lower()} {component.lower()}"
                for role, component in sorted(expected_keys)
            )
            + "."
        )
    triangle_counts = {}
    for item in expected_items:
        source = item["source"]
        role = item["role"]
        component = item["component"]
        component_overlay = item["overlay"]
        storage_key = item["storageKey"]
        obj = by_component_role.get((role, component))
        if obj is None:
            errors.append(
                f"Gore {role.lower()} {component.lower()} mesh is missing."
            )
            continue
        if obj.name != item["name"]:
            errors.append(
                f"Gore {role.lower()} {component.lower()} node name is not deterministic."
            )
        expected_metadata = {
            "dsb_gore_region_id": region_id,
            "dsb_gore_deformation_key": key_name,
            "dsb_gore_pair_role": role,
            "dsb_gore_component": component,
            "dsb_gore_source_object": source.name,
            "dsb_gore_source_topology_fingerprint": topology,
            "dsb_gore_capture_hash": capture_hash,
            "dsb_gore_deformation_digest": deformation_digests[role],
            "dsb_gore_recipe_digest": trauma_field.gore_overlay_digest(
                component_overlay
            ),
            "dsb_gore_parent_recipe_digest": trauma_field.gore_overlay_digest(
                overlay
            ),
            "dsb_gore_generation_digest": generation_digests[storage_key],
            "dsb_gore_geometry_mode": str(
                component_overlay["goreGeometryMode"]
            ),
        }
        for field, expected in expected_metadata.items():
            if str(obj.get(field, "")) != str(expected):
                errors.append(f"Raised gore object {obj.name} has stale or incorrect {field} metadata.")
        mesh_errors = _raised_gore_mesh_errors(
            obj, source, key_name, component_overlay, role
        )
        errors.extend(mesh_errors)
        triangle_counts[storage_key] = int(
            obj.get("dsb_gore_triangle_count", 0)
        )
        stored_geometry = entry.get("goreGeometryDigests", {}).get(
            storage_key, ""
        )
        if str(stored_geometry) != str(obj.get("dsb_gore_mesh_geometry_digest", "")):
            errors.append(f"Raised gore object {obj.name} does not match the deformation manifest geometry digest.")
    errors.extend(
        trauma_field.raised_gore_budget_errors(
            list(triangle_counts.values()),
            per_deformation_limit=int(overlay["goreMaximumTriangles"]),
            total_limit=trauma_field.GORE_MAX_TRIANGLES_PER_ASSET,
        )
    )
    if entry.get("raisedGoreStatus") != "READY":
        errors.append("Raised gore recipe is marked stale or not generated.")
    stored_names = list(entry.get("goreGeneratedNodeNames", []))
    expected_names = [item["name"] for item in expected_items]
    if stored_names != expected_names:
        errors.append("Raised gore manifest node mapping is missing or stale.")
    stored_ids = list(entry.get("goreGeneratedMeshIds", []))
    actual_ids = [
        str(
            by_component_role[(item["role"], item["component"])].get(
                "dsb_gore_mesh_id", ""
            )
        )
        for item in expected_items
        if (item["role"], item["component"]) in by_component_role
    ]
    if stored_ids != actual_ids or len(set(actual_ids)) != len(actual_ids):
        errors.append("Raised gore stable mesh ID mapping is missing, duplicated, or stale.")
    record = {
        "status": "FAIL" if errors else "PASS",
        "geometryMode": str(overlay["goreGeometryMode"]),
        "identityId": str(overlay["goreIdentityId"]),
        "nodeNames": expected_names,
        "meshIds": list(entry.get("goreGeneratedMeshIds", [])),
        "triangleCounts": triangle_counts,
        "materialIds": list(entry.get("goreMaterialIds", [])),
        "measurements": dict(entry.get("goreValidationMeasurements", {})),
        "defaultVisible": False,
        "activationWeight": float(overlay["goreActivationWeight"]),
        "errors": list(errors),
    }
    return errors, record


def _gore_material(source, obj, slot_index, overlay):
    safe_object_name = re.sub(r"[^A-Za-z0-9_]+", "_", obj.name)
    name = f"{GORE_MATERIAL_PREFIX}{safe_object_name}_{slot_index:02d}"
    stale = bpy.data.materials.get(name)
    if stale is not None and stale.users == 0:
        bpy.data.materials.remove(stale)
    material = source.copy() if source is not None else bpy.data.materials.new(name=name)
    material.name = name
    material.use_nodes = True
    material["dsb_surface_gore_preview"] = True
    material["dsb_generated_role"] = "surface_gore_preview_material"
    material["dsb_surface_gore_attribute"] = GORE_PREVIEW_ATTRIBUTE
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = next(
        (node for node in nodes if node.bl_idname == 'ShaderNodeOutputMaterial' and getattr(node, "is_active_output", True)),
        None,
    )
    if output is None:
        output = nodes.new('ShaderNodeOutputMaterial')
    surface = output.inputs.get("Surface")
    original_socket = surface.links[0].from_socket if surface is not None and surface.is_linked else None
    if original_socket is None:
        base = nodes.new('ShaderNodeBsdfPrincipled')
        base.name = "DSB Gore Preview Base Surface"
        original_socket = base.outputs.get("BSDF")
    if surface is None or original_socket is None:
        raise RuntimeError(f"Could not create a managed gore preview surface for material {material.name}.")
    for link in list(surface.links):
        links.remove(link)
    attribute = nodes.new('ShaderNodeAttribute')
    attribute.name = "DSB Surface Gore Mask"
    attribute.attribute_name = GORE_PREVIEW_ATTRIBUTE
    gore = nodes.new('ShaderNodeBsdfPrincipled')
    gore.name = "DSB Surface Gore"
    color = tuple(
        max(0.0, min(1.0, float(channel) * (1.0 - 0.78 * float(overlay["goreDarkness"]))))
        for channel in overlay["goreColorBias"]
    )
    gore.inputs["Base Color"].default_value = (*color, 1.0)
    gore.inputs["Roughness"].default_value = max(0.035, 1.0 - float(overlay["goreWetness"]) * 0.94)
    if gore.inputs.get("Metallic") is not None:
        gore.inputs["Metallic"].default_value = 0.0
    if gore.inputs.get("Coat Weight") is not None:
        gore.inputs["Coat Weight"].default_value = float(overlay["goreWetness"]) * 0.38
    mix = nodes.new('ShaderNodeMixShader')
    mix.name = "DSB Surface Gore Overlay"
    mask_socket = attribute.outputs.get("Fac") or attribute.outputs.get("Color")
    if mask_socket is None:
        raise RuntimeError("Blender's Attribute node exposes no usable surface gore mask output.")
    links.new(mask_socket, mix.inputs[0])
    links.new(original_socket, mix.inputs[1])
    links.new(gore.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs[0], surface)
    material.diffuse_color = (*color, 1.0)
    return material


def _install_gore_preview(obj, mask_values, overlay, key_name, original_fake_user_by_name):
    if len(mask_values) != len(obj.data.vertices):
        raise RuntimeError(f"Surface gore mask point count does not match {obj.name}.")
    existing = obj.data.color_attributes.get(GORE_PREVIEW_ATTRIBUTE)
    if existing is not None:
        obj.data.color_attributes.remove(existing)
    attribute = obj.data.color_attributes.new(name=GORE_PREVIEW_ATTRIBUTE, type='FLOAT_COLOR', domain='POINT')
    for index, value in enumerate(mask_values):
        value = float(value)
        attribute.data[index].color = (value, value, value, 1.0)
    original_names = [slot.material.name if slot.material else "" for slot in obj.material_slots]
    original_fake_users = [
        bool(original_fake_user_by_name.get(slot.material.name, slot.material.use_fake_user)) if slot.material else False
        for slot in obj.material_slots
    ]
    original_count = len(obj.material_slots)
    preview_names = []
    state = {
        "keyName": key_name,
        "attributeName": GORE_PREVIEW_ATTRIBUTE,
        "overlayDigest": trauma_field.gore_overlay_digest(overlay),
        "originalMaterialSlotCount": original_count,
        "originalMaterialNames": original_names,
        "originalMaterialFakeUsers": original_fake_users,
        "previewMaterialNames": preview_names,
    }
    obj[GORE_PREVIEW_STATE_PROPERTY] = json.dumps(state, sort_keys=True, separators=(",", ":"))
    if original_count:
        for index in range(original_count):
            source = obj.material_slots[index].material
            if source is not None:
                source.use_fake_user = True
            managed = _gore_material(source, obj, index, overlay)
            managed["dsb_surface_gore_source_material"] = source.name if source is not None else ""
            managed["dsb_surface_gore_source_fake_user"] = original_fake_users[index]
            managed["dsb_surface_gore_original_slot_count"] = original_count
            preview_names.append(managed.name)
            obj[GORE_PREVIEW_STATE_PROPERTY] = json.dumps(state, sort_keys=True, separators=(",", ":"))
            obj.material_slots[index].material = managed
    else:
        managed = _gore_material(None, obj, 0, overlay)
        managed["dsb_surface_gore_source_material"] = ""
        managed["dsb_surface_gore_source_fake_user"] = False
        managed["dsb_surface_gore_original_slot_count"] = original_count
        preview_names.append(managed.name)
        obj[GORE_PREVIEW_STATE_PROPERTY] = json.dumps(state, sort_keys=True, separators=(",", ":"))
        obj.data.materials.append(managed)


def _gore_preview_errors(attached, detached, key_name, overlay):
    if overlay.get("previewStatus") != "READY":
        return []
    errors = []
    expected_digest = trauma_field.gore_overlay_digest(overlay)
    for obj in tuple(value for value in (attached, detached) if value is not None):
        state = _gore_state(obj)
        if state.get("broken"):
            errors.append(f"Surface gore preview state on {obj.name} is broken.")
            continue
        if not state or state.get("keyName") != key_name or state.get("overlayDigest") != expected_digest:
            errors.append(f"Surface gore preview linkage on {obj.name} is missing or stale.")
            continue
        if obj.data.color_attributes.get(GORE_PREVIEW_ATTRIBUTE) is None:
            errors.append(f"Surface gore preview mask attribute is missing from {obj.name}.")
        for material_name in state.get("previewMaterialNames", []):
            material = bpy.data.materials.get(material_name)
            if material is None or not material.get("dsb_surface_gore_preview", False):
                errors.append(f"Managed surface gore preview material {material_name!r} is missing.")
    return errors


def _surface_gore_preview_data(region, attached, entry):
    overlay = trauma_field.normalize_gore_overlay(entry.get("surfaceGoreOverlay", {}))
    if not overlay["goreOverlayEnabled"]:
        raise RuntimeError("Enable Surface Gore Overlay and apply its settings before previewing it.")
    stamp = next(
        (stamp for stamp in entry.get("stamps", []) if stamp.get("stampId") == overlay.get("linkedStampId")),
        None,
    )
    errors = trauma_field.validate_gore_overlay(
        overlay,
        expected_region_id=str(region.get("regionId", "")),
        available_stamp_ids=[str(stamp.get("stampId", "")) for stamp in entry.get("stamps", [])],
    )
    if stamp is None:
        errors.append("The linked trauma stamp no longer exists.")
    else:
        capture = stamp.get("capture", {})
        if capture.get("selectionHash") != overlay.get("linkedSelectionHash"):
            errors.append("The linked surface capture changed after the gore overlay was authored.")
        if capture.get("topologyFingerprint") != overlay.get("linkedCaptureTopologyFingerprint"):
            errors.append("The linked surface capture topology changed after the gore overlay was authored.")
        errors.extend(_capture_errors(capture, region, attached))
    if errors:
        raise RuntimeError(" ".join(errors))
    weights, _distances = _stamp_weights(attached, region, stamp)
    positions = _basis_world_positions(attached)
    mask_values = trauma_field.gore_mask_values(weights, positions, overlay)
    if max(mask_values, default=0.0) <= 1e-6:
        raise RuntimeError("The linked capture produced no usable surface gore preview mask.")
    return overlay, mask_values


def _install_surface_stain_preview(
    region, attached, detached, payload, key_name, entry, *, persist=True
):
    overlay, mask_values = _surface_gore_preview_data(region, attached, entry)
    _clear_gore_preview_pair(attached, detached)
    try:
        original_fake_user_by_name = {
            slot.material.name: bool(slot.material.use_fake_user)
            for obj in tuple(value for value in (attached, detached) if value is not None)
            for slot in obj.material_slots
            if slot.material is not None
        }
        _install_gore_preview(attached, mask_values, overlay, key_name, original_fake_user_by_name)
        if detached is not None:
            _install_gore_preview(detached, mask_values, overlay, key_name, original_fake_user_by_name)
    except Exception:
        _clear_gore_preview_pair(attached, detached)
        raise
    overlay["previewStatus"] = "READY"
    overlay["previewObjectNames"] = [obj.name for obj in (attached, detached) if obj is not None]
    overlay["previewAttributeName"] = GORE_PREVIEW_ATTRIBUTE
    overlay["validationStatus"] = "NOT_VALIDATED"
    if persist:
        entry["surfaceGoreOverlay"] = overlay
        entry["goreOverlayDigest"] = trauma_field.gore_overlay_digest(overlay)
        _store_metadata(attached, detached, payload)
    return overlay, mask_values


def _install_existing_surface_stain_preview(context, region_id, key_name):
    registry = _load_registry()
    region = _region_record(registry, region_id)
    if region is None:
        return None
    attached, detached = _resolve_region_pair(region)
    payload = _metadata(attached)
    entry = payload.get("keys", {}).get(key_name)
    if not isinstance(entry, dict):
        return None
    raw_overlay = entry.get("surfaceGoreOverlay")
    if not isinstance(raw_overlay, dict) or not raw_overlay.get("goreOverlayEnabled", False):
        return None
    return _install_surface_stain_preview(region, attached, detached, payload, key_name, entry)


def _surface_stain_name(region_id, key_name, pair_role):
    raw = (
        f"DSB_STAIN_{str(pair_role).upper()}_"
        f"{str(region_id)}_{str(key_name)}"
    )
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")
    if len(safe) <= 60:
        return safe
    digest = hashlib.sha256(safe.encode("utf-8")).hexdigest()[:12]
    return safe[:47].rstrip("_") + "_" + digest


def surface_stain_export_objects(region_id=None, key_name=None, pair_role=None):
    role = str(pair_role).upper() if pair_role else None
    result = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        if str(obj.get("dsb_generated_role", "")) != SURFACE_STAIN_OBJECT_ROLE:
            continue
        if not bool(obj.get("dsb_stain_owned", False)):
            continue
        if region_id is not None and str(obj.get("dsb_stain_region_id", "")) != str(region_id):
            continue
        if key_name is not None and str(obj.get("dsb_stain_deformation_key", "")) != str(key_name):
            continue
        if role is not None and str(obj.get("dsb_stain_pair_role", "")).upper() != role:
            continue
        result.append(obj)
    return sorted(result, key=lambda value: value.name)


def remove_surface_stain_export_artifacts():
    removed = []
    material_names = set()
    image_names = set()
    for obj in list(surface_stain_export_objects()):
        mesh = obj.data
        removed.append(obj.name)
        material_names.update(
            material.name
            for material in mesh.materials
            if material is not None
        )
        image_name = str(obj.get("dsb_stain_texture_name", ""))
        if image_name:
            image_names.add(image_name)
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for material_name in sorted(material_names):
        material = bpy.data.materials.get(material_name)
        if (
            material is not None
            and material.users == 0
            and str(material.get("dsb_generated_role", ""))
            == "surface_stain_export_material"
        ):
            bpy.data.materials.remove(material)
    for image_name in sorted(image_names):
        image = bpy.data.images.get(image_name)
        if (
            image is not None
            and image.users == 0
            and str(image.get("dsb_generated_role", ""))
            == "surface_stain_export_texture"
        ):
            bpy.data.images.remove(image)
    return removed


def _create_surface_stain_material(name, overlay, overlay_digest):
    material_name = name + "_MAT"
    occupied = bpy.data.materials.get(material_name)
    if occupied is not None:
        if str(occupied.get("dsb_generated_role", "")) != "surface_stain_export_material":
            raise RuntimeError(
                f"Surface-stain material name {material_name!r} is occupied by user data."
            )
        if occupied.users == 0:
            bpy.data.materials.remove(occupied)
        else:
            raise RuntimeError(
                f"Stale surface-stain material {material_name!r} is still in use."
            )
    material = bpy.data.materials.new(name=material_name)
    material.use_nodes = True
    material["dsb_generated_role"] = "surface_stain_export_material"
    material["dsb_stain_binding_schema"] = SURFACE_STAIN_BINDING_SCHEMA
    material["dsb_stain_overlay_digest"] = overlay_digest
    material["dsb_stain_attribute_semantic"] = "COLOR_0"
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    output.name = "DSB glTF Stain Output"
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.name = "DSB glTF Wet Surface Stain"
    shader.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    shader.inputs["Metallic"].default_value = 0.0
    shader.inputs["Roughness"].default_value = max(
        0.055,
        1.0 - float(overlay["goreWetness"]) * 0.90,
    )
    shader.inputs["Alpha"].default_value = 1.0
    color_attribute = nodes.new('ShaderNodeVertexColor')
    color_attribute.name = "DSB Standard glTF COLOR_0 Stain"
    color_attribute.layer_name = SURFACE_STAIN_COLOR_ATTRIBUTE
    material.node_tree.links.new(
        color_attribute.outputs["Color"],
        shader.inputs["Base Color"],
    )
    material.node_tree.links.new(
        color_attribute.outputs["Alpha"],
        shader.inputs["Alpha"],
    )
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = 'DITHERED'
    elif hasattr(material, "blend_method"):
        material.blend_method = 'BLEND'
    if hasattr(material, "use_transparency_overlap"):
        material.use_transparency_overlap = False
    material.use_backface_culling = True
    material.diffuse_color = (0.25, 0.005, 0.003, 1.0)
    return material


def _build_surface_stain_export_object(
    source,
    key_name,
    region_id,
    pair_role,
    overlay,
    mask_values,
):
    name = _surface_stain_name(region_id, key_name, pair_role)
    occupied = bpy.data.objects.get(name)
    if occupied is not None:
        if str(occupied.get("dsb_generated_role", "")) != SURFACE_STAIN_OBJECT_ROLE:
            raise RuntimeError(
                f"Surface-stain node name {name!r} is occupied by user data."
            )
        mesh = occupied.data
        bpy.data.objects.remove(occupied, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    basis = _ensure_basis(source)
    target = _key(source, key_name)
    if target is None:
        raise RuntimeError(
            f"Surface-stain owner {source.name} has no deformation key {key_name!r}."
        )
    basis_positions = [point.co.copy() for point in basis.data]
    target_positions = [point.co.copy() for point in target.data]
    source_faces = [
        tuple(int(index) for index in polygon.vertices)
        for polygon in source.data.polygons
    ]
    basis_normals = _local_vertex_normals(basis_positions, source_faces)
    target_normals = _local_vertex_normals(target_positions, source_faces)
    selected_faces = []
    used_source_indices = set()
    for polygon in source.data.polygons:
        indices = tuple(int(index) for index in polygon.vertices)
        if max((float(mask_values[index]) for index in indices), default=0.0) <= 1.0e-5:
            continue
        selected_faces.append({
            "sourcePolygonIndex": int(polygon.index),
            "sourceIndices": indices,
        })
        used_source_indices.update(indices)
    if not selected_faces:
        raise RuntimeError(
            f"Surface-stain key {key_name!r} produced no exportable faces."
        )
    source_indices = sorted(used_source_indices)
    local_index = {
        source_index: index
        for index, source_index in enumerate(source_indices)
    }
    faces = [
        tuple(local_index[index] for index in record["sourceIndices"])
        for record in selected_faces
    ]
    offset = max(0.00005, float(overlay.get("goreSurfaceOffset", 0.00035)))
    vertices = [
        tuple(basis_positions[index] + basis_normals[index] * offset)
        for index in source_indices
    ]
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    target_collection = (
        source.users_collection[0]
        if source.users_collection
        else bpy.context.scene.collection
    )
    target_collection.objects.link(obj)
    _copy_gore_skinning(
        source,
        obj,
        source_indices,
        require_deform=True,
    )
    obj.shape_key_add(name="Basis")
    stage_key = obj.shape_key_add(name=key_name)
    stage_key.value = 0.0
    stage_key.slider_min = 0.0
    stage_key.slider_max = max(
        1.0,
        float(getattr(target, "slider_max", 1.0)),
    )
    for local, source_index in enumerate(source_indices):
        stage_key.data[local].co = (
            target_positions[source_index]
            + target_normals[source_index] * offset
        )
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    overlay_digest = trauma_field.gore_overlay_digest(overlay)
    color = tuple(
        max(
            0.0,
            min(
                1.0,
                float(channel)
                * (1.0 - 0.78 * float(overlay["goreDarkness"])),
            ),
        )
        for channel in overlay["goreColorBias"]
    )
    color_layer = mesh.color_attributes.new(
        name=SURFACE_STAIN_COLOR_ATTRIBUTE,
        type='BYTE_COLOR',
        domain='POINT',
    )
    for local, source_index in enumerate(source_indices):
        color_layer.data[local].color = (
            float(color[0]),
            float(color[1]),
            float(color[2]),
            max(0.0, min(1.0, float(mask_values[source_index]))),
        )
    mesh.color_attributes.active_color = color_layer
    mesh.color_attributes.render_color_index = (
        mesh.color_attributes.find(color_layer.name)
    )
    material = _create_surface_stain_material(
        name,
        overlay,
        overlay_digest,
    )
    mesh.materials.append(material)
    mesh.calc_loop_triangles()
    triangle_count = len(mesh.loop_triangles)
    mesh_id = SURFACE_STAIN_MESH_ID_PREFIX + hashlib.sha256(
        f"{region_id}|{key_name}|{str(pair_role).upper()}|{overlay_digest}".encode(
            "utf-8"
        )
    ).hexdigest()[:20]
    obj["dsb_damage_generated"] = True
    obj["dsb_stain_owned"] = True
    obj["dsb_generated_role"] = SURFACE_STAIN_OBJECT_ROLE
    obj["dsb_preview_only"] = False
    obj["dsb_stain_binding_schema"] = SURFACE_STAIN_BINDING_SCHEMA
    obj["dsb_stain_mesh_id"] = mesh_id
    obj["dsb_stain_region_id"] = str(region_id)
    obj["dsb_stain_deformation_key"] = str(key_name)
    obj["dsb_stain_pair_role"] = str(pair_role).upper()
    obj["dsb_stain_source_object"] = source.name
    obj["dsb_stain_source_topology_fingerprint"] = _topology_fingerprint(source)
    obj["dsb_stain_overlay_digest"] = overlay_digest
    obj["dsb_stain_material_name"] = material.name
    obj["dsb_stain_attribute_name"] = SURFACE_STAIN_COLOR_ATTRIBUTE
    obj["dsb_stain_attribute_semantic"] = "COLOR_0"
    obj["dsb_stain_morph_target"] = str(key_name)
    obj["dsb_stain_default_visible"] = False
    obj["dsb_stain_activation_weight"] = float(
        overlay.get("goreActivationWeight", 0.01)
    )
    obj["dsb_stain_triangle_count"] = triangle_count
    obj["dsb_stain_alpha_mode"] = "BLEND"
    obj["dsb_stain_portable_representation"] = "VERTEX_COLOR_RGBA"
    obj["dsb_stain_portable_artifact_included"] = True
    obj.hide_render = True
    obj.hide_set(True)
    return obj


def build_surface_stain_export_artifacts():
    """Build ordinary glTF mesh/material/texture stains for every enabled key."""

    remove_surface_stain_export_artifacts()
    registry = _load_registry()
    built = []
    try:
        for region in registry.get("regions", []):
            attached, detached = _resolve_region_pair(region)
            payload = _metadata(attached)
            for key_name in _managed_names(attached):
                entry = payload.get("keys", {}).get(key_name, {})
                raw_overlay = entry.get("surfaceGoreOverlay")
                if not isinstance(raw_overlay, dict):
                    continue
                overlay = trauma_field.normalize_gore_overlay(raw_overlay)
                if not bool(overlay.get("goreOverlayEnabled", False)):
                    continue
                if str(overlay.get("goreOverlayMode", "")) not in {
                    "SURFACE_STAIN",
                    "STAIN_AND_RAISED",
                }:
                    continue
                _resolved_overlay, mask_values = _surface_gore_preview_data(
                    region,
                    attached,
                    entry,
                )
                for source, role in _region_gore_sources(
                    region,
                    attached,
                    detached,
                ):
                    built.append(
                        _build_surface_stain_export_object(
                            source,
                            key_name,
                            str(region.get("regionId", "")),
                            role,
                            overlay,
                            mask_values,
                        )
                    )
    except Exception:
        remove_surface_stain_export_artifacts()
        raise
    return built


def surface_stain_export_records(region_id=None, key_name=None):
    records = []
    for obj in surface_stain_export_objects(region_id, key_name):
        material_name = str(obj.get("dsb_stain_material_name", ""))
        records.append({
            "schema": SURFACE_STAIN_BINDING_SCHEMA,
            "meshId": str(obj.get("dsb_stain_mesh_id", "")),
            "nodeName": obj.name,
            "materialName": material_name,
            "textureName": "",
            "attributeName": str(
                obj.get(
                    "dsb_stain_attribute_name",
                    SURFACE_STAIN_COLOR_ATTRIBUTE,
                )
            ),
            "attributeSemantic": str(
                obj.get("dsb_stain_attribute_semantic", "COLOR_0")
            ),
            "maskEncoding": "COLOR_0_RGBA_ALPHA",
            "regionId": str(obj.get("dsb_stain_region_id", "")),
            "deformationKey": str(obj.get("dsb_stain_deformation_key", "")),
            "ownershipRole": str(obj.get("dsb_stain_pair_role", "")),
            "sourceObject": str(obj.get("dsb_stain_source_object", "")),
            "sourceTopologyFingerprint": str(
                obj.get("dsb_stain_source_topology_fingerprint", "")
            ),
            "morphTarget": str(obj.get("dsb_stain_morph_target", "")),
            "morphWeightSource": "MATCHING_DEFORMATION_KEY_WEIGHT",
            "defaultVisible": bool(obj.get("dsb_stain_default_visible", False)),
            "activationWeight": float(
                obj.get("dsb_stain_activation_weight", 0.01)
            ),
            "triangleCount": int(obj.get("dsb_stain_triangle_count", 0)),
            "alphaMode": str(obj.get("dsb_stain_alpha_mode", "BLEND")),
            "portableRepresentation": str(
                obj.get(
                    "dsb_stain_portable_representation",
                    "VERTEX_COLOR_RGBA",
                )
            ),
            "depthBehavior": "NORMAL_OFFSET_NO_DEPTH_WRITE_OVERRIDE",
            "portableArtifactIncluded": bool(
                obj.get("dsb_stain_portable_artifact_included", False)
            ),
            "runtimeImplementationIncluded": False,
            "rendererRequirements": {
                "glTFVersion": "2.0",
                "materialModel": "PBR_METALLIC_ROUGHNESS",
                "alphaMode": "BLEND",
                "embeddedTexture": False,
                "vertexColorSemantic": "COLOR_0",
                "requiresNodeVisibilityToggle": True,
                "requiresMorphWeightBinding": True,
                "threeJsLoader": "GLTFLoader",
            },
        })
    return records


def _build_preview_gore_for_entry(
    region, attached, detached, key_name, entry, *, quality
):
    overlay, stamp, component_inputs, _topology, capture_hash, deformation_digests, generation_digests = (
        _expected_raised_gore_inputs(region, attached, detached, key_name, entry)
    )
    region_id = str(region.get("regionId", ""))
    _remove_preview_gore_objects(region_id, key_name)
    built = []
    try:
        multi_component = len(component_inputs) > 1
        for component, component_overlay, full_records in component_inputs:
            records = list(full_records)
            if quality == "BALANCED" and len(records) > 1:
                records = records[::2]
            for source, role in _region_gore_sources(
                region, attached, detached
            ):
                builder = (
                    _build_cavity_inlay_object
                    if component_overlay["goreGeometryMode"] == "CAVITY_INLAY"
                    else _build_gore_shell_object
                )
                storage_key = (
                    f"{role}:{component}" if multi_component else role
                )
                obj = builder(
                    source,
                    key_name,
                    region_id,
                    role,
                    component_overlay,
                    records,
                    preview=True,
                    component=component if multi_component else "",
                )
                obj["dsb_gore_parent_recipe_digest"] = (
                    trauma_field.gore_overlay_digest(overlay)
                )
                obj["dsb_gore_linked_stamp_id"] = str(
                    stamp.get("stampId", "")
                )
                obj["dsb_gore_capture_hash"] = capture_hash
                obj["dsb_gore_deformation_digest"] = deformation_digests[role]
                obj["dsb_gore_generation_digest"] = generation_digests[
                    storage_key
                ]
                built.append(obj)
    except Exception:
        _remove_preview_gore_objects(region_id, key_name)
        raise
    return built


def generate_gore_preview(context, *, quality=None):
    """Build a managed, preview-only gore result without replacing the saved recipe."""

    if getattr(context, "mode", "OBJECT") != "OBJECT":
        raise RuntimeError("Switch to Object Mode before generating a gore preview.")
    settings, _registry, region, attached, detached, payload, name, entry = (
        _active_key_context(context)
    )
    requested = str(quality or settings.deformation_preview_quality)
    if requested not in {"FAST", "BALANCED", "FINAL"}:
        requested = "FAST"
    overlay = _gore_overlay_from_settings(context)
    temporary_entry = copy.deepcopy(entry)
    temporary_entry["surfaceGoreOverlay"] = overlay
    temporary_entry["goreOverlayDigest"] = trauma_field.gore_overlay_digest(overlay)
    clear_damage_preview(context, update_status=False)
    mask_values = []
    if overlay["goreOverlayEnabled"]:
        _overlay, mask_values = _install_surface_stain_preview(
            region,
            attached,
            detached,
            payload,
            name,
            temporary_entry,
            persist=False,
        )
    preview_objects = []
    if (
        overlay["goreGeometryMode"] != "STAIN_ONLY"
        and requested in {"BALANCED", "FINAL"}
    ):
        preview_objects = _build_preview_gore_for_entry(
            region,
            attached,
            detached,
            name,
            temporary_entry,
            quality=requested,
        )
    _zero_managed_weights(attached, include_preview=True)
    key = _key(attached, name)
    if key is None:
        raise RuntimeError(f"Managed deformation key {name!r} is missing.")
    key.value = min(1.0, float(key.slider_max))
    inspection = "CORE" if detached is None else "ATTACHED"
    _set_single_damage_preview_state(
        context,
        region.get("regionId", ""),
        name,
        key.value,
        inspection,
    )
    for obj in preview_objects:
        role = str(obj.get("dsb_gore_pair_role", "")).upper()
        show = role in ({"CORE"} if detached is None else {"ATTACHED"})
        obj.hide_viewport = False
        obj.hide_set(not show)
    triangle_count = sum(
        int(obj.get("dsb_gore_triangle_count", 0)) for obj in preview_objects
    )
    measurements = {}
    measured = next(
        (
            obj
            for obj in preview_objects
            if obj.get("dsb_gore_validation_measurements")
            and str(obj.get("dsb_gore_pair_role", "")).upper() in {"ATTACHED", "CORE"}
        ),
        None,
    )
    if measured is not None:
        measurements = json.loads(
            str(measured["dsb_gore_validation_measurements"])
        )
    settings.deformation_preview_final_gore_triangles = (
        triangle_count if requested == "FINAL" else 0
    )
    settings.deformation_preview_estimated_gore_triangles = triangle_count
    settings.deformation_gore_geometry_status = (
        f"{requested} PREVIEW / {triangle_count} tris"
    )
    settings.deformation_gore_validation_status = (
        "PREVIEW NUMERIC PASS" if measurements else "FAST INDICATION"
    )
    settings.deformation_gore_max_proudness = float(
        measurements.get("maximumProudness", 0.0)
    )
    settings.deformation_gore_median_cavity_depth = float(
        measurements.get("medianLinerDepth", 0.0)
    )
    settings.deformation_gore_minimum_liner_separation = float(
        measurements.get("minimumSkinToLinerSeparation", 0.0)
    )
    settings.deformation_status = (
        f"{requested} GORE PREVIEW READY - {name} / "
        f"{overlay['goreIdentityId']} / {triangle_count} triangles"
    )
    return {
        "key": name,
        "identityId": overlay["goreIdentityId"],
        "geometryMode": overlay["goreGeometryMode"],
        "quality": requested,
        "maskedVertexCount": sum(value > 1e-4 for value in mask_values),
        "triangleCount": triangle_count,
        "measurements": measurements,
    }


def preview_managed_deformation(context, key_name=None, mode=None):
    settings, _registry, region, attached, detached, payload, active_name, entry = _active_key_context(context)
    name = str(key_name or active_name)
    if name != active_name:
        entry = payload.get("keys", {}).get(name)
        if not isinstance(entry, dict):
            raise RuntimeError(f"Managed deformation {name!r} has no recipe metadata.")
    clear_damage_preview(context, update_status=False)
    mask_values = []
    raw_overlay = entry.get("surfaceGoreOverlay")
    if isinstance(raw_overlay, dict) and raw_overlay.get("goreOverlayEnabled", False):
        _overlay, mask_values = _install_surface_stain_preview(
            region, attached, detached, payload, name, entry
        )
    key = _key(attached, name)
    if key is None:
        raise RuntimeError(f"Managed deformation key {name!r} is missing from {attached.name}.")
    key.value = min(1.0, float(key.slider_max)) if _max_displacement(attached, name) > 1e-7 else 0.0
    inspection = mode or ('CORE' if detached is None else 'ATTACHED')
    _set_single_damage_preview_state(context, region.get("regionId", ""), name, key.value, inspection)
    _set_authoring_view(attached, detached, inspection, context)
    return {
        "key": name,
        "weight": float(key.value),
        "maskedVertexCount": sum(value > 1e-4 for value in mask_values),
    }


def preview_surface_gore(context, *, rebuild_raised=True):
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        raise RuntimeError("Switch to Object Mode before previewing surface gore.")
    settings, _registry, region, attached, detached, payload, name, entry = _active_key_context(context)
    clear_damage_preview(context, update_status=False)
    overlay, mask_values = _install_surface_stain_preview(
        region, attached, detached, payload, name, entry
    )
    try:
        raised_objects = (
            rebuild_raised_gore_for_key(region, attached, detached, name, entry)
            if rebuild_raised and overlay["goreRaisedEnabled"]
            else generated_gore_objects(str(region.get("regionId", "")), name)
        )
    except Exception:
        _clear_gore_preview_pair(attached, detached)
        raise
    _zero_managed_weights(attached, include_preview=True)
    key = _key(attached, name)
    if key is not None:
        key.value = min(1.0, key.slider_max)
    inspection = 'CORE' if detached is None else 'ATTACHED'
    _set_single_damage_preview_state(
        context, region.get("regionId", ""), name, key.value if key is not None else 0.0, inspection
    )
    _set_authoring_view(attached, detached, inspection, context)
    screen = getattr(context, "screen", None)
    for area in getattr(screen, "areas", ()):
        if area.type == 'VIEW_3D':
            area.spaces.active.shading.type = 'MATERIAL'
    settings.deformation_status = f"SURFACE GORE PREVIEW READY — {name} / {overlay['gorePresetId']}"
    return {
        "key": name,
        "presetId": overlay["gorePresetId"],
        "maskedVertexCount": sum(value > 1e-4 for value in mask_values),
        "raisedTriangleCount": sum(int(obj.get("dsb_gore_triangle_count", 0)) for obj in raised_objects),
    }


def preview_active_stamp(context, quiet=False):
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        raise RuntimeError("Switch to Object Mode before previewing a trauma stamp.")
    settings, _registry, region, attached, detached, _payload, _name, entry = _active_key_context(context)
    stamp = _active_stamp(settings, entry)
    preview_stamp = dict(stamp)
    preview_stamp["orderIndex"] = 0
    clear_damage_preview(context, update_status=False)
    attached, detached, attached_preview, _detached_preview = _ensure_key_pair(PREVIEW_KEY_NAME, preview=True)
    _zero_managed_weights(attached)
    _set_key_coordinates(attached_preview, _stamp_local_coordinates(attached, [preview_stamp]))
    sync_key_to_detached(PREVIEW_KEY_NAME)
    attached_preview.value = 1.0
    attached_preview.slider_max = 1.0
    inspection = 'CORE' if detached is None else 'ATTACHED'
    _set_single_damage_preview_state(context, region.get("regionId", ""), PREVIEW_KEY_NAME, 1.0, inspection)
    _set_authoring_view(attached, detached, inspection, context)
    settings.deformation_status = f"STAMP PREVIEW — {stamp.get('displayName', stamp.get('stampId'))}"
    if not quiet:
        return {"stampId": stamp.get("stampId"), "vertexCount": len(attached_preview.data)}
    return None


def validate_active_deformation(context, *, include_gore=True):
    settings, _registry, region, attached, detached, _payload, name, entry = _active_key_context(context)
    errors = []
    contract = validate_region_contract(region, attached, detached)
    errors.extend(contract.get("errors", []))
    key = _key(attached, name)
    maximum = 0.0
    if key is None:
        errors.append(f"The active deformation key {name!r} is missing.")
    else:
        maximum = _max_displacement(attached, name)
        allowed = float(entry.get("maximumDisplacement", settings.deformation_max_vertex_displacement))
        if maximum > allowed + 1e-6:
            errors.append(f"{name} exceeds its maximum world displacement ({maximum:.6f} m > {allowed:.6f} m).")
    if detached is not None:
        mismatch = _pair_delta_error(attached, detached, name)
        if mismatch > SYNC_TOLERANCE:
            errors.append(f"{name} attached/detached exact-index delta mismatch is {mismatch:.9f} m.")
    overlay = entry.get("surfaceGoreOverlay")
    if include_gore and isinstance(overlay, dict) and overlay.get("goreOverlayEnabled") and overlay.get("goreRaisedEnabled"):
        expected_roles = {role for _source, role in _region_gore_sources(region, attached, detached)}
        objects = generated_gore_objects(str(region.get("regionId", "")), name)
        actual_roles = {str(obj.get("dsb_gore_pair_role", "")) for obj in objects}
        if actual_roles != expected_roles:
            errors.append(f"{name} final raised-gore roles are incomplete ({sorted(actual_roles)} != {sorted(expected_roles)}).")
        try:
            normalized_overlay = trauma_field.normalize_gore_overlay(overlay)
            gore_errors, _gore_record = _raised_gore_errors(
                region, attached, detached, name, entry, normalized_overlay
            )
            errors.extend(gore_errors)
        except Exception as exc:
            errors.append(f"{name} final raised-gore focused validation failed: {exc}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "regionId": str(region.get("regionId", "")),
        "key": name,
        "maximumDisplacement": maximum,
    }


def rebuild_active_deformation(context):
    settings, _registry, region, attached, detached, payload, name, entry = _active_key_context(context)
    alternative_mode = str(entry.get("stampMode", "STACK")) == "ALTERNATIVES"
    stamps = _entry_preview_stamps(entry, settings.deformation_active_stamp_id)
    stamps = trauma_field.reindex_stamps(stamps)
    if not stamps:
        raise RuntimeError("The active deformation has no trauma stamps; legacy/manual geometry was not overwritten.")
    errors = trauma_field.validate_stamp_stack(stamps)
    if errors:
        raise RuntimeError(" ".join(errors))
    if not alternative_mode:
        clear_damage_preview(context, update_status=False)
    coordinates = _stamp_local_coordinates(attached, stamps)
    coordinates = _clamp_local_coordinates_to_world_limit(
        attached,
        coordinates,
        entry.get(
            "maximumDisplacement",
            settings.deformation_max_vertex_displacement,
        ),
    )
    target = _key(attached, name)
    _set_key_coordinates(target, coordinates)
    sync_key_to_detached(name)
    entry["stamps"] = (
        trauma_field.reindex_stamps(entry.get("stamps", []))
        if alternative_mode
        else stamps
    )
    entry["status"] = "TRAUMA_REBUILT"
    entry["recipeStatus"] = "PROCEDURAL_STACK"
    entry["legacy"] = False
    entry["recipeDigest"] = trauma_field.recipe_digest(entry["stamps"])
    entry["region"] = region.get("regionId")
    entry["regionId"] = region.get("regionId")
    raw_overlay = entry.get("surfaceGoreOverlay")
    if raw_overlay:
        overlay = trauma_field.normalize_gore_overlay(raw_overlay)
        if overlay["goreOverlayEnabled"] and overlay["goreRaisedEnabled"]:
            rebuild_raised_gore_for_key(region, attached, detached, name, entry)
    _store_metadata(attached, detached, payload)
    clear_seed_preview()
    if alternative_mode:
        apply_damage_key_previews(context)
    else:
        _zero_managed_weights(attached)
        target.value = min(1.0, target.slider_max)
    if raw_overlay and raw_overlay.get("goreOverlayEnabled", False):
        _install_existing_surface_stain_preview(context, str(region.get("regionId", "")), name)
    inspection = 'CORE' if detached is None else 'ATTACHED'
    if not alternative_mode:
        _set_single_damage_preview_state(
            context, region.get("regionId", ""), name, target.value, inspection
        )
    _set_authoring_view(attached, detached, inspection, context)
    validation = validate_active_deformation(context)
    if validation["status"] != "PASS":
        raise RuntimeError("Rebuilt deformation failed validation: " + "; ".join(validation["errors"][:4]))
    entry["validationStatus"] = validation["status"]
    entry["focusedValidationErrors"] = list(validation.get("errors", []))
    _store_metadata(attached, detached, payload)
    settings.last_deformation_validation = validation["status"]
    settings.deformation_status = f"REBUILT FROM BASIS — {name} / {len(stamps)} stamps"
    return {"key": name, "stampCount": len(stamps), "validation": validation}


def _compound_event_record(registry, event_id):
    return next(
        (event for event in registry.get("compoundEvents", []) if str(event.get("eventId", "")) == str(event_id)),
        None,
    )


def _active_compound_event(context=None, require=True):
    registry = _load_registry()
    scene = getattr(context, "scene", None) if context is not None else getattr(bpy.context, "scene", None)
    settings = getattr(scene, "daf_settings", None)
    event_id = str(getattr(settings, "compound_active_event_id", "") or registry.get("activeCompoundEventId", ""))
    event = _compound_event_record(registry, event_id)
    if require and event is None:
        raise RuntimeError("Create or select a Compound Trauma Event first.")
    return registry, event


def _compound_world_field_from_settings(context, *, use_active_capture=False):
    settings = context.scene.daf_settings
    origin = Vector(settings.compound_impact_origin)
    direction = Vector(settings.compound_impact_direction)
    if use_active_capture and settings.deformation_seed_center_valid:
        capture = _capture_payload(settings)
        origin = Vector(capture.get("centerWorld", origin))
        direction = Vector(capture.get("normalWorld", direction))
        if settings.deformation_seed_direction_mode == 'INWARD_SURFACE_NORMAL':
            direction.negate()
    elif use_active_capture:
        origin = context.scene.cursor.location.copy()
    if direction.length_squared <= 1e-12:
        raise RuntimeError("Compound impact direction has zero length.")
    return trauma_field.normalize_world_impact_field({
        "origin": list(origin),
        "direction": list(direction.normalized()),
        "normal": list(direction.normalized()),
        "radius": float(settings.compound_impact_radius),
        "depth": float(settings.compound_impact_depth),
        "falloff": float(settings.compound_impact_falloff),
        "strength": float(settings.compound_impact_strength),
        "displacementLimit": float(settings.compound_displacement_limit),
        "seed": int(settings.compound_event_seed),
        "traumaFamily": settings.compound_trauma_family,
        "transformReference": "WORLD",
        "participantIntersections": [],
    })


def create_compound_event(context):
    settings = context.scene.daf_settings
    registry = _load_registry()
    event_id = settings.compound_event_id.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", event_id):
        raise RuntimeError("Compound event ID must start with a letter and use only letters, digits, underscore, period, or hyphen.")
    if _compound_event_record(registry, event_id) is not None:
        raise RuntimeError(f"Compound trauma event {event_id!r} already exists.")
    linked_seams = sorted({
        value.strip() for value in settings.compound_linked_seam_ids.split(",") if value.strip()
    })
    event = {
        "schema": trauma_field.COMPOUND_EVENT_SCHEMA,
        "eventId": event_id,
        "displayName": settings.compound_display_name.strip() or event_id,
        "traumaFamily": settings.compound_trauma_family,
        "impactDirection": settings.compound_semantic_direction.strip() or "UNSPECIFIED",
        "severity": float(settings.compound_severity),
        "worldField": _compound_world_field_from_settings(context),
        "participants": [],
        "linkedSeamIds": linked_seams,
        "continuityMode": settings.compound_continuity_mode,
        "activationWeight": float(settings.compound_activation_weight),
        "activationRule": "SYNCHRONIZED_WEIGHT",
        "goreStyleLinkage": "SHARED_HEAVY_CLOTTED",
        "seed": int(settings.compound_event_seed),
        "validationStatus": "INCOMPLETE",
        "seamContinuity": [],
    }
    registry.setdefault("compoundEvents", []).append(event)
    registry["activeCompoundEventId"] = event_id
    _store_registry(registry)
    settings.compound_active_event_id = event_id
    settings.deformation_status = f"COMPOUND EVENT CREATED — {event_id}"
    return event


def select_compound_event(context, event_id):
    registry = _load_registry()
    event = _compound_event_record(registry, event_id)
    if event is None:
        raise RuntimeError(f"Compound trauma event {event_id!r} is missing.")
    registry["activeCompoundEventId"] = str(event_id)
    _store_registry(registry)
    context.scene.daf_settings.compound_active_event_id = str(event_id)
    return event


def _compound_child_stamp_id(event_id, region_id, key_name):
    digest = hashlib.sha256(f"{event_id}|{region_id}|{key_name}".encode("utf-8")).hexdigest()[:20]
    return "compound_stamp_" + digest


def add_active_region_to_compound_event(context):
    registry, event = _active_compound_event(context)
    settings, _region_registry, region, attached, detached, payload, key_name, entry = _active_key_context(context)
    identity = (str(region.get("regionId", "")), attached.name)
    if any(
        (str(item.get("regionId", "")), str(item.get("targetObject", ""))) == identity
        for item in event.get("participants", [])
    ):
        raise RuntimeError(f"Region {identity[0]!r} is already a participant in this event.")
    participant_seed = trauma_field.derive_participant_seed(
        int(event.get("seed", 0)), identity[0], identity[1]
    )
    related_seam = str(region.get("relatedSeamId", ""))
    linked_event_seams = {str(value) for value in event.get("linkedSeamIds", [])}
    seam_ids = [related_seam] if related_seam and related_seam in linked_event_seams else []
    participant = {
        "regionId": identity[0],
        "regionMode": _region_mode(region),
        "targetObject": attached.name,
        "detachedObject": detached.name if detached is not None else "",
        "childKeyName": key_name,
        "childStampId": _compound_child_stamp_id(event["eventId"], identity[0], key_name),
        "seamIds": seam_ids,
        "participantSeed": participant_seed,
        "intersectionVertexCount": 0,
        "intersectionDigest": "",
        "goreRecipeDigest": "",
        "goreNodeNames": [],
    }
    event.setdefault("participants", []).append(participant)
    entry["compoundEventIds"] = sorted(set(entry.get("compoundEventIds", [])) | {str(event["eventId"])})
    entry["compoundChildStampId"] = participant["childStampId"]
    _store_metadata(attached, detached, payload)
    event["validationStatus"] = "INCOMPLETE" if len(event["participants"]) < 2 else "NOT_VALIDATED"
    registry["activeCompoundEventId"] = str(event["eventId"])
    _store_registry(registry)
    settings.deformation_status = f"COMPOUND PARTICIPANT ADDED — {identity[0]}/{key_name}"
    return participant


def remove_active_region_from_compound_event(context):
    registry, event = _active_compound_event(context)
    _region_registry, region, attached, detached = _resolve_active_region(context)
    region_id = str(region.get("regionId", ""))
    before = len(event.get("participants", []))
    event["participants"] = [
        item for item in event.get("participants", [])
        if str(item.get("regionId", "")) != region_id
    ]
    if len(event["participants"]) == before:
        raise RuntimeError(f"Region {region_id!r} is not a participant in the active event.")
    payload = _metadata(attached)
    for entry in payload.get("keys", {}).values():
        entry["compoundEventIds"] = [
            value for value in entry.get("compoundEventIds", []) if value != event["eventId"]
        ]
    _store_metadata(attached, detached, payload)
    event["validationStatus"] = "INCOMPLETE"
    _store_registry(registry)
    return region_id


def capture_compound_world_field(context):
    registry, event = _active_compound_event(context)
    field = _compound_world_field_from_settings(context, use_active_capture=True)
    event["worldField"] = field
    event["traumaFamily"] = field["traumaFamily"]
    event["seed"] = int(field["seed"])
    event["validationStatus"] = "NOT_VALIDATED"
    _store_registry(registry)
    settings = context.scene.daf_settings
    settings.compound_impact_origin = tuple(field["origin"])
    settings.compound_impact_direction = tuple(field["direction"])
    settings.deformation_status = f"SHARED WORLD FIELD CAPTURED — {event['eventId']}"
    return field


def _compound_capture(target, region, field, affected_indices):
    if not affected_indices:
        raise RuntimeError(f"Shared world field does not intersect {target.name}.")
    topology = _topology_fingerprint(target)
    center_world = Vector(field["origin"])
    center_local = target.matrix_world.inverted() @ center_world
    normal_world = Vector(field["normal"]).normalized()
    normal_local = target.matrix_world.to_3x3().transposed() @ normal_world
    if normal_local.length_squared <= 1e-12:
        raise RuntimeError(f"Shared world field cannot derive a local normal for {target.name}.")
    normal_local.normalize()
    points = [target.matrix_world @ target.data.vertices[index].co for index in affected_indices]
    bounds = [
        [min(point[axis] for point in points) for axis in range(3)],
        [max(point[axis] for point in points) for axis in range(3)],
    ]
    return {
        "placementMode": "SELECTED_VERTICES",
        "selectionKind": "VERTEX",
        "regionId": str(region.get("regionId", "")),
        "attachedObject": target.name,
        "topologyFingerprint": topology,
        "faceIndices": [],
        "vertexIndices": sorted(int(index) for index in affected_indices),
        "selectionHash": trauma_field.selection_hash(affected_indices, topology, "VERTEX"),
        "centerLocal": list(center_local),
        "centerWorld": list(center_world),
        "normalLocal": list(normal_local),
        "normalWorld": list(normal_world),
        "boundsWorld": bounds,
        "estimatedRadius": float(field["radius"]),
        "compoundWorldField": True,
    }


def _compound_stamp(participant, region, target, field, capture):
    direction_world = Vector(field["direction"]).normalized()
    direction_local = _world_delta_to_local(target, direction_world)
    direction_local.normalize()
    return trauma_field.normalize_stamp({
        "stampId": participant["childStampId"],
        "displayName": "Compound " + str(participant["childKeyName"]),
        "enabled": True,
        "family": str(field["traumaFamily"]),
        "placementMode": "SELECTED_VERTICES",
        "capture": capture,
        "center": list(field["origin"]),
        "direction": list(direction_world),
        "directionMode": "CUSTOM_VECTOR",
        "directionLocal": list(direction_local),
        "radius": float(field["radius"]),
        "depth": float(field["depth"]),
        "falloff": float(field["falloff"]),
        "influenceMode": "CONNECTED_SURFACE",
        "distanceMode": "WORLD_DISTANCE",
        "featherDistance": min(float(field["radius"]) * 0.25, 0.30),
        "seamProtection": 0.0,
        "strength": float(field["strength"]),
        "maximumDisplacement": float(field["displacementLimit"]),
        "orderIndex": 0,
    })


def _compound_seam_mapping(first, second, seam_id, tolerance=COMPOUND_SEAM_TOLERANCE):
    from . import damage_authoring

    state = damage_authoring._load_state()
    seam = state.get("seams", {}).get(seam_id)
    protected = _object(state.get("protected_source_mesh", ""))
    if not seam or protected is None:
        raise RuntimeError(f"Linked seam contract {seam_id!r} is missing from Damage Authoring state.")
    protected_world = damage_authoring._evaluated_hidden_world_matrix(protected)
    first_world = damage_authoring._evaluated_hidden_world_matrix(first)
    second_world = damage_authoring._evaluated_hidden_world_matrix(second)
    contour_points = seam.get("contour_points_object", [])
    contour_digest = hashlib.sha256(
        json.dumps(contour_points, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cache_key = (
        str(seam_id),
        first.name,
        _topology_fingerprint(first),
        tuple(round(float(value), 12) for row in first_world for value in row),
        second.name,
        _topology_fingerprint(second),
        tuple(round(float(value), 12) for row in second_world for value in row),
        protected.name,
        tuple(round(float(value), 12) for row in protected_world for value in row),
        contour_digest,
        round(float(tolerance), 9),
    )
    cached = compound_service.seam_mapping(cache_key)
    if cached is not None:
        return list(cached)
    contour_world = [protected_world @ Vector(point) for point in contour_points]
    if len(contour_world) < 3:
        raise RuntimeError(f"Linked seam contract {seam_id!r} has an incomplete contour.")

    def closest_indices(obj):
        matrix = first_world if obj == first else second_world
        world = [matrix @ vertex.co for vertex in obj.data.vertices]
        result = []
        for point in contour_world:
            index, distance = min(
                ((index, (candidate - point).length) for index, candidate in enumerate(world)),
                key=lambda item: item[1],
            )
            if distance > tolerance:
                raise RuntimeError(
                    f"{obj.name} misses seam {seam_id} by {distance:.6f} m; tolerance is {tolerance:.6f} m."
                )
            result.append(index)
        return result

    first_indices = closest_indices(first)
    second_indices = closest_indices(second)
    mappings = []
    used = set()
    for first_index, second_index in zip(first_indices, second_indices):
        pair = (int(first_index), int(second_index))
        if pair in used:
            continue
        used.add(pair)
        mappings.append(pair)
    if len(mappings) < 3:
        raise RuntimeError(f"Linked seam {seam_id!r} produced fewer than three unique mapped boundary points.")
    return list(compound_service.store_seam_mapping(cache_key, mappings))


def _feather_compound_seam_inward(deltas, obj, boundary_indices, rings=2):
    """Blend matched seam motion into adjacent vertices without topology edits."""

    result = [Vector(value) for value in deltas]
    boundary = {int(index) for index in boundary_indices}
    if not boundary:
        return [tuple(value) for value in result], 0
    adjacency = {index: set() for index in range(len(obj.data.vertices))}
    for edge in obj.data.edges:
        first, second = (int(value) for value in edge.vertices)
        adjacency[first].add(second)
        adjacency[second].add(first)
    frontier = set(boundary)
    visited = set(boundary)
    feathered = 0
    for ring in range(1, max(1, int(rings)) + 1):
        next_frontier = {
            neighbor
            for index in frontier
            for neighbor in adjacency.get(index, ())
            if neighbor not in visited
        }
        if not next_frontier:
            break
        strength = 0.42 / float(ring)
        for index in sorted(next_frontier):
            matched_neighbors = adjacency[index] & visited
            if not matched_neighbors:
                continue
            target = sum((result[value] for value in sorted(matched_neighbors)), Vector((0.0, 0.0, 0.0))) / len(matched_neighbors)
            result[index] = result[index].lerp(target, strength)
            feathered += 1
        visited.update(next_frontier)
        frontier = next_frontier
    return [tuple(value) for value in result], feathered


def rebuild_compound_event(context):
    registry, raw_event = _active_compound_event(context)
    region_by_id = {str(region.get("regionId", "")): region for region in registry.get("regions", [])}
    try:
        event = trauma_field.normalize_compound_event(raw_event, verify_digest=False)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(str(exc)) from None
    event_errors = trauma_field.validate_compound_event(event, registered_regions=region_by_id)
    if event_errors:
        raise RuntimeError(" ".join(event_errors))
    field = event["worldField"]
    plans = []
    for participant in event["participants"]:
        region = region_by_id.get(str(participant["regionId"]))
        if region is None:
            raise RuntimeError(f"Compound participant region {participant['regionId']!r} is missing.")
        attached, detached = _resolve_region_pair(region)
        if attached.name != participant["targetObject"]:
            raise RuntimeError(f"Compound participant {participant['regionId']!r} targets a stale mesh identity.")
        key_name = str(participant["childKeyName"])
        key = _key(attached, key_name)
        if key is None:
            raise RuntimeError(f"Compound participant {participant['regionId']!r} is missing child key {key_name!r}.")
        basis = _ensure_basis(attached)
        basis_world = [tuple(attached.matrix_world @ point.co) for point in basis.data]
        evaluation = trauma_field.evaluate_world_impact_field(basis_world, field)
        affected = list(evaluation["affectedVertexIndices"])
        capture = _compound_capture(attached, region, field, affected)
        stamp = _compound_stamp(participant, region, attached, field, capture)
        plans.append({
            "participant": participant,
            "region": region,
            "attached": attached,
            "detached": detached,
            "key": key,
            "basis": basis,
            "deltas": [tuple(value) for value in evaluation["deltas"]],
            "capture": capture,
            "stamp": stamp,
        })

    seam_records = []
    for seam_id in event.get("linkedSeamIds", []):
        candidates = [
            plan for plan in plans
            if seam_id in plan["participant"].get("seamIds", [])
            or str(plan["region"].get("relatedSeamId", "")) == seam_id
        ]
        if len(candidates) != 2:
            raise RuntimeError(f"Linked seam {seam_id!r} requires exactly two participating region boundaries.")
        first, second = candidates
        mappings = _compound_seam_mapping(first["attached"], second["attached"], seam_id)
        resolved = trauma_field.resolve_seam_boundary_displacements(
            first["deltas"], second["deltas"], mappings, str(event["continuityMode"])
        )
        first["deltas"] = list(resolved["firstDeltas"])
        second["deltas"] = list(resolved["secondDeltas"])
        feathered_count = 0
        if event["continuityMode"] == "BLEND_ACROSS_SEAM":
            first["deltas"], first_count = _feather_compound_seam_inward(
                first["deltas"], first["attached"], [pair[0] for pair in mappings]
            )
            second["deltas"], second_count = _feather_compound_seam_inward(
                second["deltas"], second["attached"], [pair[1] for pair in mappings]
            )
            feathered_count = first_count + second_count
        seam_records.append({
            "seamId": seam_id,
            "continuityMode": event["continuityMode"],
            "mappedVertexCount": resolved["mappedVertexCount"],
            "maximumMismatchBefore": resolved["maximumMismatchBefore"],
            "maximumMismatchAfter": resolved["maximumMismatchAfter"],
            "tolerance": COMPOUND_SEAM_TOLERANCE,
            "topologyMutated": False,
            "featheredInteriorVertexCount": feathered_count,
        })

    backups = []
    intersections = []
    try:
        for plan in plans:
            attached, detached = plan["attached"], plan["detached"]
            key_name = str(plan["participant"]["childKeyName"])
            backups.append({
                "attached": attached,
                "detached": detached,
                "keyName": key_name,
                "coordinates": [point.co.copy() for point in plan["key"].data],
                "metadata": copy.deepcopy(_metadata(attached)),
            })
            coordinates = []
            inverse = attached.matrix_world.inverted()
            for basis_point, delta in zip(plan["basis"].data, plan["deltas"]):
                coordinates.append(inverse @ ((attached.matrix_world @ basis_point.co) + Vector(delta)))
            _set_key_coordinates(plan["key"], coordinates)
            sync_key_to_detached(key_name, str(plan["participant"]["regionId"]))
            payload = _metadata(attached)
            entry = payload["keys"][key_name]
            stamps = [
                stamp for stamp in entry.get("stamps", [])
                if str(stamp.get("stampId", "")) != str(plan["stamp"]["stampId"])
            ]
            stamps.append(plan["stamp"])
            entry["stamps"] = trauma_field.reindex_stamps(stamps)
            entry["recipeDigest"] = trauma_field.recipe_digest(entry["stamps"])
            entry["recipeStatus"] = "COMPOUND_WORLD_FIELD"
            entry["status"] = "COMPOUND_REBUILT"
            entry["legacy"] = False
            entry["compoundEventIds"] = sorted(set(entry.get("compoundEventIds", [])) | {str(event["eventId"])})
            entry["compoundChildStampId"] = str(plan["participant"]["childStampId"])
            participant_seed = trauma_field.derive_participant_seed(
                int(event["seed"]), str(plan["participant"]["regionId"]), attached.name
            )
            recipe = trauma_field.default_gore_overlay(
                "Gore_Bloody_Crater",
                enabled=True,
                region_id=str(plan["participant"]["regionId"]),
                linked_stamp_id=str(plan["participant"]["childStampId"]),
                selection_hash=str(plan["capture"]["selectionHash"]),
                topology_fingerprint=str(plan["capture"]["topologyFingerprint"]),
                seed=participant_seed,
            )
            entry["surfaceGoreOverlay"] = recipe
            entry["goreOverlayDigest"] = trauma_field.gore_overlay_digest(recipe)
            objects = rebuild_raised_gore_for_key(
                plan["region"], attached, detached, key_name, entry
            )
            _store_metadata(attached, detached, payload)
            intersection_digest = hashlib.sha256(
                (str(plan["capture"]["selectionHash"]) + trauma_field.compound_event_digest(event)).encode("utf-8")
            ).hexdigest()
            plan["participant"].update({
                "participantSeed": participant_seed,
                "intersectionVertexCount": len(plan["capture"]["vertexIndices"]),
                "intersectionDigest": intersection_digest,
                "goreRecipeDigest": trauma_field.gore_overlay_digest(recipe),
                "goreNodeNames": [obj.name for obj in objects],
            })
            intersections.append({
                "regionId": str(plan["participant"]["regionId"]),
                "targetObject": attached.name,
                "vertexCount": len(plan["capture"]["vertexIndices"]),
                "selectionHash": str(plan["capture"]["selectionHash"]),
                "intersectionDigest": intersection_digest,
            })
    except Exception:
        for backup in reversed(backups):
            key = _key(backup["attached"], backup["keyName"])
            if key is not None:
                _set_key_coordinates(key, backup["coordinates"])
            if backup["detached"] is not None:
                sync_key_to_detached(backup["keyName"], str(backup["metadata"].get("regionId", "")))
            _remove_generated_gore_objects(str(backup["metadata"].get("regionId", "")), backup["keyName"])
            _store_metadata(backup["attached"], backup["detached"], backup["metadata"])
            restored_entry = backup["metadata"].get("keys", {}).get(backup["keyName"], {})
            restored_overlay = restored_entry.get("surfaceGoreOverlay")
            if isinstance(restored_overlay, dict) and restored_overlay.get("goreRaisedEnabled", False):
                try:
                    backup_region = _region_record(
                        _load_registry(), str(backup["metadata"].get("regionId", ""))
                    )
                    if backup_region is not None:
                        rebuild_raised_gore_for_key(
                            backup_region,
                            backup["attached"],
                            backup["detached"],
                            backup["keyName"],
                            restored_entry,
                        )
                except Exception:
                    # Preserve the original rebuild exception. Validation will
                    # explicitly report a stale/missing restored gore node.
                    pass
        raise

    field = copy.deepcopy(field)
    field["participantIntersections"] = intersections
    event["worldField"] = field
    event["seamContinuity"] = seam_records
    event["validationStatus"] = "PASS"
    event = trauma_field.normalize_compound_event(event, verify_digest=False)
    event["validationStatus"] = "PASS"
    registry["compoundEvents"] = [
        event if str(item.get("eventId", "")) == str(event["eventId"]) else item
        for item in registry.get("compoundEvents", [])
    ]
    registry["activeCompoundEventId"] = str(event["eventId"])
    _store_registry(registry)
    context.scene.daf_settings.deformation_status = (
        f"COMPOUND EVENT REBUILT — {event['eventId']} / {len(plans)} participants"
    )
    return event


def preview_compound_event(context, weight=1.0):
    registry, event = _active_compound_event(context)
    clear_damage_preview(context, update_status=False)
    event_digest = trauma_field.compound_event_digest(event)
    recomputed = 0
    entries = []
    source_views = []
    preview_weight = max(0.0, float(weight))
    for participant in event.get("participants", []):
        region = _region_record(registry, str(participant.get("regionId", "")))
        if region is None:
            raise RuntimeError(f"Compound participant region {participant.get('regionId')!r} is missing.")
        attached, detached = _resolve_region_pair(region)
        key_name = str(participant.get("childKeyName", ""))
        key = _key(attached, key_name)
        if key is None:
            raise RuntimeError(f"Compound child key {key_name!r} is missing on {attached.name}.")
        region_id = str(region.get("regionId", ""))
        preview_digest = compound_service.participant_digest(
            region_fingerprint=str(region.get("topologyFingerprint", "")),
            target_topology=_topology_fingerprint(attached),
            child_key_state={"key": key_name, "weight": round(float(weight), 6)},
            shared_field_digest=event_digest,
            seam_mapping_digest=json.dumps(sorted(participant.get("seamIds", []))),
            gore_recipe_digest=str(participant.get("goreRecipeDigest", "")),
        )
        _zero_managed_weights(attached, include_preview=True)
        key.value = min(float(key.slider_max), preview_weight)
        inspection = 'ATTACHED' if detached is not None else 'CORE'
        entries.append(_preview_entry(region_id, key_name, key.value, inspection))
        source_views.append((attached, detached, inspection))
        if key.value > 1e-8:
            payload = _metadata(attached)
            entry = payload.get("keys", {}).get(key_name, {})
            overlay = entry.get("surfaceGoreOverlay") if isinstance(entry, dict) else None
            if isinstance(overlay, dict) and overlay.get("goreOverlayEnabled", False):
                _install_surface_stain_preview(region, attached, detached, payload, key_name, entry)
        compound_service.mark_clean(event.get("eventId", ""), region_id, preview_digest, preview_service.state().get("generation", 0))
        recomputed += 1
    damage_state = {"kind": "COMPOUND", "entries": entries}
    _store_damage_preview_state(context, damage_state)
    for attached, detached, inspection in source_views:
        _set_authoring_view(attached, detached, inspection, context)
    _sync_generated_gore_visibility(context, damage_state)
    context.scene[COMPOUND_PREVIEW_PROPERTY] = json.dumps({
        "eventId": event["eventId"],
        "entries": entries,
    }, sort_keys=True, separators=(",", ":"))
    context.scene.daf_settings.deformation_status = f"COMPOUND PREVIEW {float(weight):.2f} — {event['eventId']}"
    return {
        "eventId": event["eventId"],
        "participantCount": len(entries),
        "recomputedParticipantCount": recomputed,
        "weight": float(weight),
    }


def clear_compound_preview(context):
    raw = context.scene.get(COMPOUND_PREVIEW_PROPERTY, "")
    if not raw:
        clear_damage_preview(context)
        return 0
    try:
        state = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        state = {}
    restored = len(state.get("entries", []))
    clear_damage_preview(context, update_status=False)
    compound_service.clear_cache("compound preview cleared")
    context.scene.daf_settings.deformation_status = "DAMAGE PREVIEW CLEARED"
    return restored


def validate_compound_events():
    registry = _load_registry()
    region_by_id = {str(region.get("regionId", "")): region for region in registry.get("regions", [])}
    records = []
    all_errors = []
    event_ids = [str(event.get("eventId", "")) for event in registry.get("compoundEvents", [])]
    for event_id in sorted({value for value in event_ids if event_ids.count(value) > 1}):
        all_errors.append(f"Duplicate compound event ID {event_id!r}.")
    for raw_event in registry.get("compoundEvents", []):
        event_errors = []
        try:
            event = trauma_field.normalize_compound_event(raw_event, verify_digest=False)
        except (TypeError, ValueError) as exc:
            event = raw_event
            event_errors.append(str(exc))
        event_errors.extend(trauma_field.validate_compound_event(event, registered_regions=region_by_id))
        for participant in event.get("participants", []):
            region_id = str(participant.get("regionId", ""))
            region = region_by_id.get(region_id)
            if region is None:
                continue
            attached, _detached = _resolve_region_pair(region)
            key_name = str(participant.get("childKeyName", ""))
            key = _key(attached, key_name)
            if key is None:
                event_errors.append(f"Participant {region_id!r} is missing child key {key_name!r}.")
                continue
            entry = _metadata(attached).get("keys", {}).get(key_name, {})
            if str(event.get("eventId", "")) not in entry.get("compoundEventIds", []):
                event_errors.append(f"Participant {region_id!r} child key has inconsistent event ownership.")
            if entry.get("recipeStatus") == "COMPOUND_WORLD_FIELD":
                expected_stamp = str(participant.get("childStampId", ""))
                compound_stamp = next(
                    (stamp for stamp in entry.get("stamps", []) if str(stamp.get("stampId", "")) == expected_stamp),
                    None,
                )
                if compound_stamp is None:
                    event_errors.append(f"Participant {region_id!r} is missing its compound child stamp.")
                else:
                    capture = compound_stamp.get("capture", {})
                    expected_intersection_digest = hashlib.sha256(
                        (
                            str(capture.get("selectionHash", ""))
                            + trauma_field.compound_event_digest(event)
                        ).encode("utf-8")
                    ).hexdigest()
                    if str(participant.get("intersectionDigest", "")) != expected_intersection_digest:
                        event_errors.append(f"Participant {region_id!r} has a stale intersection recipe.")
                    if int(participant.get("intersectionVertexCount", -1)) != len(capture.get("vertexIndices", [])):
                        event_errors.append(f"Participant {region_id!r} has a stale intersection vertex count.")
                overlay = entry.get("surfaceGoreOverlay", {})
                if not isinstance(overlay, dict) or not overlay.get("goreRaisedEnabled", False):
                    event_errors.append(f"Participant {region_id!r} is missing enabled raised gore.")
                else:
                    try:
                        current_gore_digest = trauma_field.gore_overlay_digest(overlay)
                    except (TypeError, ValueError):
                        current_gore_digest = "INVALID"
                    if str(participant.get("goreRecipeDigest", "")) != current_gore_digest:
                        event_errors.append(f"Participant {region_id!r} has a stale compound gore recipe.")
                actual_gore_nodes = {
                    obj.name for obj in generated_gore_objects(region_id, key_name)
                }
                if set(participant.get("goreNodeNames", [])) != actual_gore_nodes:
                    event_errors.append(f"Participant {region_id!r} gore ownership/export mapping is stale.")
        if event.get("validationStatus") == "PASS":
            reported_seams = {str(value.get("seamId", "")) for value in event.get("seamContinuity", [])}
            for seam_id in event.get("linkedSeamIds", []):
                if str(seam_id) not in reported_seams:
                    event_errors.append(f"Linked seam {seam_id!r} has no measured continuity report.")
        for seam in event.get("seamContinuity", []):
            mismatch = float(seam.get("maximumMismatchAfter", math.inf))
            tolerance = float(seam.get("tolerance", COMPOUND_SEAM_TOLERANCE))
            if mismatch > tolerance:
                event_errors.append(
                    f"Seam {seam.get('seamId')} mismatch is {mismatch:.6f} m; tolerance is {tolerance:.6f} m."
                )
            if bool(seam.get("topologyMutated", True)):
                event_errors.append(f"Seam {seam.get('seamId')} reports destructive topology mutation.")
        record = {
            "eventId": str(event.get("eventId", "")),
            "status": "FAIL" if event_errors else "PASS",
            "participantCount": len(event.get("participants", [])),
            "errors": event_errors,
        }
        records.append(record)
        all_errors.extend(f"Compound event {record['eventId']}: {message}" for message in event_errors)
    return {
        "status": "FAIL" if all_errors else "PASS",
        "eventCount": len(records),
        "events": records,
        "errors": all_errors,
    }


def _manifest_stamp(stamp):
    capture = stamp.get("capture", {})
    manifest = {
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
            "virtualWeldTolerance": capture.get("virtualWeldTolerance"),
            "virtualWeldDigest": capture.get("virtualWeldDigest"),
            "virtualWeldMemberCount": capture.get("virtualWeldMemberCount"),
            "virtualConnectedComponentCount": capture.get("virtualConnectedComponentCount"),
        },
    }
    for field in ("impactSeed", "impactChaos", "impactProfile", "profileCenterRimBalance"):
        if field in stamp:
            manifest[field] = stamp[field]
    return manifest


def validate_deformations(require_keys=False):
    registry = _load_registry()
    errors = []
    warnings = []
    region_records = []
    key_records = []
    raised_triangle_counts = []
    known_gore_owners = set()
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
        contract = validate_region_contract(region, attached, detached)
        region_errors.extend(contract["errors"])
        if contract["status"] != "PASS":
            errors.extend(f"Region {region_id or '<empty>'}: {message}" for message in contract["errors"])
            region_records.append({"regionId": region_id, "status": "FAIL", "errors": region_errors, "keys": []})
            continue
        if region_id == registry.get("activeRegionId"):
            active_pair = contract
        if region.get("topologyFingerprint") and region.get("topologyFingerprint") != contract.get("topologyFingerprint"):
            region_errors.append("Stored region topology fingerprint is stale; validate or re-register the region.")
        if region.get("weightFingerprint") and region.get("weightFingerprint") != _weight_fingerprint(attached):
            region_errors.append("Stored region source-weight fingerprint is stale.")
        if int(region.get("attachedVertexCount", contract["attachedVertexCount"])) != contract["attachedVertexCount"]:
            region_errors.append("Stored target vertex count is stale.")
        if int(region.get("detachedVertexCount", contract["detachedVertexCount"])) != contract["detachedVertexCount"]:
            region_errors.append("Stored detached vertex count is stale.")
        if int(region.get("polygonCount", contract["attachedPolygonCount"])) != contract["attachedPolygonCount"]:
            region_errors.append("Stored polygon count is stale.")
        payload = _metadata(attached)
        names = _managed_names(attached)
        if attached.data.shape_keys is None or attached.data.shape_keys.reference_key is None:
            region_errors.append("Registered region target mesh is missing its Basis shape key.")
        if detached is not None and (detached.data.shape_keys is None or detached.data.shape_keys.reference_key is None):
            region_errors.append("Registered paired region detached mesh is missing its Basis shape key.")
        total_names += len(names)
        registered_names = set(region.get("managedKeys", []))
        metadata_names = set(payload.get("keys", {}))
        removed_references = sorted(registered_names - metadata_names)
        if removed_references:
            region_errors.append("Region references removed managed keys: " + ", ".join(removed_references) + ".")
        region_key_records = []
        for name in names:
            known_gore_owners.add((region_id, name))
            key_error_start = len(region_errors)
            attached_key = _key(attached, name)
            detached_key = _key(detached, name) if detached is not None else None
            if attached_key is None or (_region_mode(region) == PAIRED_SEGMENT and detached_key is None):
                region_errors.append(f"Managed deformation {name} is missing from its registered region owner.")
                continue
            if detached_key is not None and len(attached_key.data) != len(detached_key.data):
                region_errors.append(f"Managed deformation {name} has mismatched point counts.")
                continue
            attached_basis = attached.data.shape_keys.reference_key
            detached_basis = detached.data.shape_keys.reference_key if detached is not None else None
            max_delta_error = 0.0
            finite = True
            for index in range(len(attached_key.data)):
                delta_a = _local_delta_to_world(attached, attached_key.data[index].co - attached_basis.data[index].co)
                finite = finite and all(math.isfinite(value) for value in attached_key.data[index].co)
                if detached_key is not None and detached_basis is not None:
                    delta_d = _local_delta_to_world(detached, detached_key.data[index].co - detached_basis.data[index].co)
                    max_delta_error = max(max_delta_error, (delta_a - delta_d).length)
                    finite = finite and all(math.isfinite(value) for value in detached_key.data[index].co)
            if not finite:
                region_errors.append(f"Managed deformation {name} contains non-finite coordinates.")
            if _region_mode(region) == PAIRED_SEGMENT and max_delta_error > SYNC_TOLERANCE:
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
            stamp_errors.extend(trauma_field.enabled_stamp_contract_errors(stamps, name))
            region_errors.extend(f"Managed deformation {name}: {message}" for message in stamp_errors)
            for stamp in stamps:
                region_errors.extend(
                    f"Managed deformation {name}, stamp {stamp.get('stampId', '<missing>')}: {message}"
                    for message in _capture_errors(stamp.get("capture", {}), region, attached)
                )
            deformation_status = "PASS" if len(region_errors) == key_error_start else "FAIL"
            gore_status = "NOT_AUTHORED"
            raised_gore_status = "NOT_AUTHORED"
            raised_gore_record = {"status": raised_gore_status, "nodeNames": [], "triangleCounts": {}, "errors": []}
            raw_overlay = entry.get("surfaceGoreOverlay")
            if raw_overlay is not None:
                gore_errors = trauma_field.validate_gore_overlay(
                    raw_overlay if isinstance(raw_overlay, dict) else {},
                    expected_region_id=region_id,
                    available_stamp_ids=[str(stamp.get("stampId", "")) for stamp in stamps],
                )
                normalized_overlay = None
                try:
                    normalized_overlay = trauma_field.normalize_gore_overlay(raw_overlay)
                except (TypeError, ValueError) as exc:
                    gore_errors.append("Broken saved overlay recipe: " + str(exc))
                if normalized_overlay is not None:
                    linked_stamp = next(
                        (stamp for stamp in stamps if stamp.get("stampId") == normalized_overlay.get("linkedStampId")),
                        None,
                    )
                    if normalized_overlay["goreOverlayEnabled"] and linked_stamp is not None:
                        linked_capture = linked_stamp.get("capture", {})
                        if linked_capture.get("selectionHash") != normalized_overlay.get("linkedSelectionHash"):
                            gore_errors.append("Surface gore capture selection linkage is stale.")
                        if linked_capture.get("topologyFingerprint") != normalized_overlay.get("linkedCaptureTopologyFingerprint"):
                            gore_errors.append("Surface gore capture topology linkage is stale.")
                    calculated_digest = trauma_field.gore_overlay_digest(normalized_overlay)
                    if entry.get("goreOverlayDigest") != calculated_digest:
                        gore_errors.append("Surface gore export metadata digest does not match the saved overlay recipe.")
                    preview_recipe = dict(normalized_overlay)
                    if isinstance(raw_overlay, dict):
                        for field in ("previewStatus", "previewObjectNames", "previewAttributeName"):
                            if field in raw_overlay:
                                preview_recipe[field] = copy.deepcopy(raw_overlay[field])
                    gore_errors.extend(_gore_preview_errors(attached, detached, name, preview_recipe))
                    raised_errors, raised_gore_record = _raised_gore_errors(
                        region, attached, detached, name, entry, normalized_overlay
                    )
                    raised_gore_status = raised_gore_record["status"]
                    region_errors.extend(
                        f"Managed deformation {name}, raised gore geometry validation: {message}"
                        for message in raised_errors
                    )
                    raised_triangle_counts.extend(
                        int(value) for value in raised_gore_record.get("triangleCounts", {}).values()
                    )
                    normalized_overlay["validationStatus"] = "FAIL" if gore_errors or raised_errors else "PASS"
                    for field in ("previewStatus", "previewObjectNames", "previewAttributeName"):
                        if isinstance(raw_overlay, dict) and field in raw_overlay:
                            normalized_overlay[field] = copy.deepcopy(raw_overlay[field])
                    entry["surfaceGoreOverlay"] = normalized_overlay
                    entry["goreOverlayDigest"] = calculated_digest
                gore_status = "FAIL" if gore_errors else "PASS"
                region_errors.extend(
                    f"Managed deformation {name}, surface gore overlay validation: {message}"
                    for message in gore_errors
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
                "deformationValidationStatus": deformation_status,
                "goreOverlayValidationStatus": gore_status,
                "raisedGoreValidationStatus": raised_gore_status,
                "raisedGore": raised_gore_record,
                "exportValidationStatus": (
                    "PASS" if deformation_status == "PASS" and gore_status != "FAIL"
                    and raised_gore_status not in {"FAIL"} else "FAIL"
                ),
                "goreOverlayEnabled": bool(
                    isinstance(entry.get("surfaceGoreOverlay"), dict)
                    and entry["surfaceGoreOverlay"].get("goreOverlayEnabled", False)
                ),
            }
            region_key_records.append(record)
            key_records.append(record)
        _store_metadata(attached, detached, payload)
        if _key(attached, PREVIEW_KEY_NAME) or (detached is not None and _key(detached, PREVIEW_KEY_NAME)):
            warnings.append(f"Region {region_id} contains the temporary preview key; export will remove it.")
        errors.extend(f"Region {region_id}: {message}" for message in region_errors)
        region["validationStatus"] = "PASS" if not region_errors else "FAIL"
        region_records.append({
            "regionId": region_id,
            "regionMode": _region_mode(region),
            "targetObject": attached.name,
            "attachedObject": attached.name,
            "detachedObject": detached.name if detached is not None else "",
            "status": region["validationStatus"],
            "topologyPair": contract,
            "keys": region_key_records,
            "errors": region_errors,
        })
    for gore_obj in generated_gore_objects():
        owner = (
            str(gore_obj.get("dsb_gore_region_id", "")),
            str(gore_obj.get("dsb_gore_deformation_key", "")),
        )
        if owner not in known_gore_owners:
            errors.append(
                f"Raised gore geometry validation: {gore_obj.name} belongs to a missing or wrong deformation."
            )
    budget_errors = trauma_field.raised_gore_budget_errors(
        raised_triangle_counts,
        total_limit=trauma_field.GORE_MAX_TRIANGLES_PER_ASSET,
    )
    errors.extend(f"Raised gore geometry validation: {message}" for message in budget_errors)
    for cache_key, cache_context in _GEODESIC_CACHE_CONTEXT.items():
        try:
            expected = trauma_field.geodesic_cache_key(
                cache_context["topologyFingerprint"], cache_context["objectIdentity"],
                cache_context["selectionHash"], cache_context["distanceMode"], cache_context["maximumDistance"],
                cache_context["virtualWeldDigest"], cache_context["virtualWeldTolerance"],
            )
            cached_object = _object(cache_context.get("objectName", ""))
            current_identity = (
                f"{cached_object.name}:{cached_object.data.name}"
                if cached_object is not None and cached_object.type == 'MESH' else ""
            )
            current_topology = _topology_fingerprint(cached_object) if current_identity else ""
            if current_identity:
                _current_positions, current_virtual_weld = _virtual_weld_context(cached_object)
            else:
                current_virtual_weld = {"digest": "", "tolerance": 0.0}
            if (
                expected != cache_key
                or cache_key not in _GEODESIC_CACHE
                or current_identity != cache_context["objectIdentity"]
                or current_topology != cache_context["topologyFingerprint"]
                or current_virtual_weld["digest"] != cache_context["virtualWeldDigest"]
                or not math.isclose(
                    float(current_virtual_weld["tolerance"]),
                    float(cache_context["virtualWeldTolerance"]),
                    rel_tol=1e-12,
                    abs_tol=1e-15,
                )
                or (cached_object is not None and cached_object.data.name != cache_context.get("meshDataName"))
            ):
                errors.append("A stale geodesic cache key was detected; recapture or rebuild the active stamp.")
        except Exception as exc:
            errors.append("A geodesic cache record is invalid: " + str(exc))
    if require_keys and not total_names:
        errors.append("No managed deformation keys exist.")
    compound_validation = validate_compound_events()
    errors.extend(compound_validation.get("errors", []))
    from . import progressive_authoring

    progression_validation = progressive_authoring.export_validation()
    errors.extend(progression_validation.get("errors", []))
    warnings.extend(progression_validation.get("warnings", []))
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
        "raisedGoreTriangleCount": sum(raised_triangle_counts),
        "raisedGoreTriangleLimit": trauma_field.GORE_MAX_TRIANGLES_PER_ASSET,
        "keys": key_records,
        "coreSingleRegionCount": sum(
            record.get("regionMode") == CORE_SINGLE for record in region_records
        ),
        "pairedSegmentRegionCount": sum(
            record.get("regionMode") == PAIRED_SEGMENT for record in region_records
        ),
        "compoundTrauma": compound_validation,
        "progressiveDamageSites": progression_validation,
        "errors": errors,
        "warnings": warnings,
    }


def prepare_for_export():
    clear_damage_preview(bpy.context, update_status=False)
    registry = _load_registry()
    for region in registry.get("regions", []):
        attached, _detached = _resolve_region_pair(region)
        for name in _managed_names(attached):
            sync_key_to_detached(name, region.get("regionId"))
    validation = validate_deformations(require_keys=False)
    if validation["status"] != "PASS":
        raise RuntimeError("Deformation validation failed: " + "; ".join(validation["errors"][:4]))
    from . import progressive_authoring

    progression = progressive_authoring.export_validation()
    if progression["status"] != "PASS":
        raise RuntimeError(
            "Progressive Damage Site validation failed: "
            + "; ".join(progression["errors"][:4])
        )
    return validation


def get_deformation_manifest():
    registry = _load_registry()
    if not registry.get("regions"):
        return {"schema": DEFORMATION_SCHEMA, "authoringVersion": _version_string(), "registeredRegions": [], "keys": []}
    validation = validate_deformations(require_keys=False)
    validation_by_region = {record.get("regionId"): record for record in validation.get("regions", [])}
    manifest_regions = []
    flat_keys = []
    flat_gore_meshes = []
    flat_stain_meshes = []
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
                "damageKeyId": str(source_entry.get("damageKeyId", "")),
                "regionId": region.get("regionId"),
                "regionMode": _region_mode(region),
                "targetObject": attached.name,
                "attachedObject": attached.name,
                "detachedObject": detached.name if detached is not None else "",
                "status": source_entry.get("status", "UNKNOWN"),
                "recipeStatus": source_entry.get("recipeStatus", "LEGACY_MANUAL"),
                "legacy": bool(source_entry.get("legacy", not source_entry.get("stamps"))),
                "maximumInfluence": source_entry.get("maximumInfluence"),
                "maximumDisplacement": source_entry.get("maximumDisplacement"),
                "measuredMaximumDisplacement": key_validation.get("measuredMaximumDisplacement", _max_displacement(attached, name)),
                "maximumPairDeltaError": key_validation.get("maximumPairDeltaError"),
                "validationStatus": validation_record.get("status", "UNKNOWN"),
                "legacySyncStatus": source_entry.get("legacySyncStatus"),
                "legacySyncErrorBefore": source_entry.get("legacySyncErrorBefore"),
                "legacySyncErrorAfter": source_entry.get("legacySyncErrorAfter"),
                "legacySyncRepairApplied": bool(source_entry.get("legacySyncRepairApplied", False)),
                "previewEnabled": bool(source_entry.get("previewEnabled", False)),
                "activeStampId": str(source_entry.get("activeStampId", "")),
                "stampMode": str(source_entry.get("stampMode", "STACK")),
                "orderedStamps": [_manifest_stamp(stamp) for stamp in source_entry.get("stamps", [])],
                "recipeDigest": source_entry.get("recipeDigest"),
            }
            if source_entry.get("blueprintId"):
                entry["blueprintId"] = str(source_entry["blueprintId"])
                entry["blueprintDigest"] = str(
                    source_entry.get("blueprintDigest", "")
                )
            if isinstance(source_entry.get("impactControl"), dict):
                entry["impactControl"] = parameter_schema.normalize_impact_control(
                    source_entry["impactControl"]
                )
            if "surfaceGoreOverlay" in source_entry:
                gore_export = trauma_field.gore_overlay_export_metadata(source_entry["surfaceGoreOverlay"])
                overlay = gore_export["surfaceGoreOverlay"]
                entry.update(gore_export)
                entry["goreOverlayValidationStatus"] = key_validation.get(
                    "goreOverlayValidationStatus", overlay.get("validationStatus", "UNKNOWN")
                )
                entry["exportValidationStatus"] = key_validation.get("exportValidationStatus", "UNKNOWN")
                entry["goreRegionId"] = region.get("regionId")
                entry["goreDeformationKey"] = name
                entry["goreGeometryMode"] = str(overlay.get("goreGeometryMode", "STAIN_ONLY"))
                entry["goreIdentityId"] = str(overlay.get("goreIdentityId", ""))
                entry["goreControl"] = copy.deepcopy(overlay.get("goreControl", {}))
                entry["goreGeneratedMeshIds"] = list(source_entry.get("goreGeneratedMeshIds", []))
                entry["goreGeneratedNodeNames"] = list(source_entry.get("goreGeneratedNodeNames", []))
                entry["goreGeometryDigests"] = dict(source_entry.get("goreGeometryDigests", {}))
                entry["goreGenerationDigests"] = dict(source_entry.get("goreGenerationDigests", {}))
                entry["goreTriangleCounts"] = dict(source_entry.get("goreTriangleCounts", {}))
                entry["goreMaterialIds"] = list(source_entry.get("goreMaterialIds", []))
                entry["goreMaterialNames"] = list(source_entry.get("goreMaterialNames", []))
                entry["goreValidationMeasurements"] = copy.deepcopy(
                    source_entry.get("goreValidationMeasurements", {})
                )
                entry["goreActivationContract"] = {
                    "defaultVisible": False,
                    "activationWeight": float(overlay.get("goreActivationWeight", 0.01)),
                    "activateWithDeformationKey": name,
                    "retainThroughDeathAndCorpsePersistence": True,
                    "runtimeImplementationIncluded": False,
                }
                stain_bindings = surface_stain_export_records(
                    str(region.get("regionId", "")),
                    name,
                )
                entry["surfaceStainBindingSchema"] = (
                    SURFACE_STAIN_BINDING_SCHEMA
                )
                entry["surfaceStainBindings"] = stain_bindings
                entry["surfaceStainActivationContract"] = {
                    "defaultVisible": False,
                    "activateWithDeformationKey": name,
                    "activationWeight": float(
                        overlay.get("goreActivationWeight", 0.01)
                    ),
                    "morphWeightSource": (
                        "MATCHING_DEFORMATION_KEY_WEIGHT"
                    ),
                    "portableArtifactIncluded": bool(stain_bindings),
                    "runtimeImplementationIncluded": False,
                }
                flat_stain_meshes.extend(copy.deepcopy(stain_bindings))
                for gore_obj in generated_gore_objects(str(region.get("regionId", "")), name):
                    mesh_record = {
                        "meshId": str(gore_obj.get("dsb_gore_mesh_id", "")),
                        "nodeName": gore_obj.name,
                        "regionId": str(region.get("regionId", "")),
                        "deformationKey": name,
                        "attachedDetachedRole": str(gore_obj.get("dsb_gore_pair_role", "")),
                        "ownershipRole": str(gore_obj.get("dsb_gore_pair_role", "")),
                        "sourceObject": str(gore_obj.get("dsb_gore_source_object", "")),
                        "defaultVisible": False,
                        "activationWeight": float(gore_obj.get("dsb_gore_activation_weight", 0.01)),
                        "triangleCount": int(gore_obj.get("dsb_gore_triangle_count", 0)),
                        "recipeDigest": str(gore_obj.get("dsb_gore_recipe_digest", "")),
                        "generationDigest": str(gore_obj.get("dsb_gore_generation_digest", "")),
                        "geometryDigest": str(gore_obj.get("dsb_gore_mesh_geometry_digest", "")),
                        "geometryMode": str(gore_obj.get("dsb_gore_geometry_mode", "")),
                        "component": str(gore_obj.get("dsb_gore_component", "")),
                        "parentRecipeDigest": str(
                            gore_obj.get("dsb_gore_parent_recipe_digest", "")
                        ),
                        "identityId": str(gore_obj.get("dsb_gore_identity_id", "")),
                        "materialIds": json.loads(
                            str(gore_obj.get("dsb_gore_material_ids", "[]"))
                        ),
                        "materialNames": json.loads(str(gore_obj.get("dsb_gore_material_names", "[]"))),
                        "validationMeasurements": json.loads(
                            str(gore_obj.get("dsb_gore_validation_measurements", "{}"))
                        ),
                        "previewOnly": False,
                    }
                    flat_gore_meshes.append(mesh_record)
            keys.append(entry)
            flat_keys.append(entry)
        manifest_regions.append({
            "regionId": region.get("regionId"),
            "regionMode": _region_mode(region),
            "targetObject": attached.name,
            "attachedObject": attached.name,
            "detachedObject": detached.name if detached is not None else "",
            "topologyFingerprint": _topology_fingerprint(attached),
            "weightFingerprint": _weight_fingerprint(attached),
            "attachedVertexCount": len(attached.data.vertices),
            "detachedVertexCount": len(detached.data.vertices) if detached is not None else 0,
            "polygonCount": len(attached.data.polygons),
            "relatedSeamId": region.get("relatedSeamId", ""),
            "managedKeyNames": [entry["name"] for entry in keys],
            "validationStatus": validation_record.get("status", "UNKNOWN"),
            "keys": keys,
        })
    compound_events = []
    for raw_event in registry.get("compoundEvents", []):
        try:
            event = trauma_field.normalize_compound_event(raw_event, verify_digest=False)
        except (TypeError, ValueError):
            continue
        morph_targets = []
        gore_nodes = []
        for participant in event.get("participants", []):
            region = _region_record(registry, str(participant.get("regionId", "")))
            if region is None:
                continue
            target, detached = _resolve_region_pair(region)
            key_name = str(participant.get("childKeyName", ""))
            morph_targets.append({
                "regionId": str(participant.get("regionId", "")),
                "mesh": target.name,
                "morphTarget": key_name,
                "attachedDetachedRole": "CORE" if _region_mode(region) == CORE_SINGLE else "ATTACHED",
            })
            if detached is not None:
                morph_targets.append({
                    "regionId": str(participant.get("regionId", "")),
                    "mesh": detached.name,
                    "morphTarget": key_name,
                    "attachedDetachedRole": "DETACHED",
                })
            gore_nodes.extend(str(value) for value in participant.get("goreNodeNames", []))
        compound_events.append({
            "eventId": event["eventId"],
            "displayName": event["displayName"],
            "traumaFamily": event["traumaFamily"],
            "impactDirection": event["impactDirection"],
            "severity": event["severity"],
            "worldField": event["worldField"],
            "participantRegions": [str(value.get("regionId", "")) for value in event["participants"]],
            "participantMeshes": [str(value.get("targetObject", "")) for value in event["participants"]],
            "morphTargets": morph_targets,
            "goreNodes": sorted(set(gore_nodes)),
            "seamIds": list(event["linkedSeamIds"]),
            "seamContinuity": copy.deepcopy(event.get("seamContinuity", [])),
            "activationWeight": float(event["activationWeight"]),
            "activationRule": event["activationRule"],
            "seed": int(event["seed"]),
            "recipeDigest": event["recipeDigest"],
            "defaultState": "INACTIVE",
            "runtimeImplementationIncluded": False,
        })
    brace_actions = []
    for action in sorted(bpy.data.actions, key=lambda value: value.name):
        if not bool(action.get("dsb_approved", False)) or not action.get("dsb_guard_variant"):
            continue
        try:
            presented_regions = json.loads(str(action.get("dsb_presented_regions_json", "[]")))
        except (TypeError, json.JSONDecodeError):
            presented_regions = []
        brace_actions.append({
            "actionName": action.name,
            "guardVariant": str(action.get("dsb_guard_variant", "")),
            "guardActiveFrame": int(action.get("dsb_guard_active_frame", 0)),
            "guardActiveTimeSeconds": float(action.get("dsb_guard_active_time_seconds", 0.0)),
            "presentedRegions": presented_regions,
            "interruptible": bool(action.get("dsb_interruptible", True)),
            "rootMotionPolicy": str(action.get("dsb_root_motion_policy", "IN_PLACE")),
            "validationStatus": str(action.get("dsb_guard_validation_status", "NOT_VALIDATED")),
        })
    result = {
        "schema": DEFORMATION_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": DEFORMATION_BUILD_ID,
        "activeRegionId": registry.get("activeRegionId", ""),
        "authoredRegionIds": [region["regionId"] for region in manifest_regions if region["managedKeyNames"]],
        "registeredRegions": manifest_regions,
        "keys": flat_keys,
        "generatedGoreMeshes": flat_gore_meshes,
        "surfaceStainBindingSchema": SURFACE_STAIN_BINDING_SCHEMA,
        "surfaceStainMeshes": flat_stain_meshes,
        "compoundTraumaEvents": compound_events,
        "compoundActivationContract": {
            "undamagedState": "ALL_CHILD_MORPHS_ZERO_AND_GORE_INACTIVE",
            "activationSource": "semantic compound event synchronized weight",
            "runtimeImplementationIncluded": False,
        },
        "maceHeadGuardActions": brace_actions,
        "goreActivationContract": {
            "undamagedState": "INACTIVE",
            "activationSource": "matching deformation key weight/state",
            "defaultVisible": False,
            "runtimeImplementationIncluded": False,
        },
        "validationStatus": validation.get("status", "UNKNOWN"),
    }
    from . import progressive_authoring

    result.update(progressive_authoring.manifest_payload())
    stain_bindings_by_key = {}
    for binding in flat_stain_meshes:
        key = (
            str(binding.get("regionId", "")),
            str(binding.get("deformationKey", "")),
        )
        stain_bindings_by_key.setdefault(key, []).append(binding)
    for site in result.get("progressiveDamageSites", []):
        site_has_portable_stains = True
        transition_mode = str(
            site.get("goreTransitionMode", "MIDPOINT_REPLACE")
        )
        for stage in site.get("stages", []):
            key = (
                str(stage.get("regionId", "")),
                str(stage.get("deformationKeyName", "")),
            )
            bindings = copy.deepcopy(stain_bindings_by_key.get(key, []))
            stage["surfaceStainBindingSchema"] = (
                SURFACE_STAIN_BINDING_SCHEMA
            )
            stage["surfaceStainBindings"] = bindings
            stage["surfaceStainActivation"] = {
                "defaultVisible": False,
                "activationThreshold": float(
                    bindings[0].get("activationWeight", 0.01)
                )
                if bindings
                else 0.01,
                "deformationKey": stage.get("deformationKeyName", ""),
                "attachedDetachedOwnership": [
                    str(binding.get("ownershipRole", ""))
                    for binding in bindings
                ],
                "transitionBehavior": transition_mode,
                "structuralMorphWeightSource": (
                    "MATCHING_DEFORMATION_KEY_WEIGHT"
                ),
                "portableArtifactIncluded": bool(bindings),
                "runtimeImplementationIncluded": False,
            }
            site_has_portable_stains = (
                site_has_portable_stains and bool(bindings)
            )
        site["surfaceStainContract"] = {
            "schema": SURFACE_STAIN_BINDING_SCHEMA,
            "stageOwned": True,
            "stageMappingSource": "EXPLICIT_PROGRESSIVE_STAGE_ASSIGNMENT",
            "transitionBehavior": transition_mode,
            "basisVisible": False,
            "portableArtifactsIncluded": site_has_portable_stains,
            "runtimeImplementationIncluded": False,
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
    bl_label = "Register Selected Pair"
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
                for name in (region.get("targetObject", region.get("attachedObject")), region.get("detachedObject"))
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


class DAF_OT_register_core_deformation_region(Operator):
    bl_idname = "daf.register_core_deformation_region"
    bl_label = "Register Selected Core Mesh"
    bl_description = "Register one active mesh as an explicit core single-mesh trauma region without a detached partner"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            region_id = settings.deformation_region_id.strip().lower()
            if not re.fullmatch(r"[a-z][a-z0-9_]*", region_id):
                raise RuntimeError("Region ID must start with a lowercase letter and contain only lowercase letters, digits, and underscores.")
            selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
            if len(selected) != 1 or context.active_object != selected[0]:
                raise RuntimeError("Select exactly one mesh object and make it active for core registration.")
            target = selected[0]
            registry = _load_registry()
            if _region_record(registry, region_id) is not None:
                raise RuntimeError(f"Semantic deformation region ID {region_id!r} is already registered.")
            used_names = {
                name for region in registry.get("regions", [])
                for name in (region.get("targetObject", region.get("attachedObject")), region.get("detachedObject"))
                if name
            }
            if target.name in used_names:
                raise RuntimeError("The selected mesh is already assigned to a deformation region; remove that registration explicitly first.")
            contract = validate_core_region(target)
            if contract["status"] != "PASS":
                raise RuntimeError(" ".join(contract["errors"]))
            record = _record_from_core(region_id, target, settings.deformation_related_seam_id.strip())
            registry.setdefault("regions", []).append(record)
            registry["activeRegionId"] = region_id
            _store_registry(registry)
            settings.deformation_region = region_id
            settings.deformation_status = f"CORE REGION REGISTERED — {region_id}"
            _invalidate_geodesic_cache()
            self.report({'INFO'}, f"Registered {target.name} as core region {region_id}.")
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
    bl_label = "Validate Active Region"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            registry, region, attached, detached = _resolve_active_region(context)
            contract = validate_region_contract(region, attached, detached)
            errors = list(contract["errors"])
            if region.get("topologyFingerprint") != contract.get("topologyFingerprint"):
                errors.append("Stored region topology fingerprint is stale; remove and re-register only after reviewing the source change.")
            if region.get("weightFingerprint") != _weight_fingerprint(attached):
                errors.append("Stored region source-weight fingerprint is stale.")
            if int(region.get("attachedVertexCount", -1)) != int(contract.get("attachedVertexCount", 0)):
                errors.append("Stored target vertex count is stale.")
            if int(region.get("detachedVertexCount", -1)) != int(contract.get("detachedVertexCount", 0)):
                errors.append("Stored detached vertex count is stale.")
            if int(region.get("polygonCount", -1)) != int(contract.get("attachedPolygonCount", 0)):
                errors.append("Stored polygon count is stale.")
            region["validationStatus"] = "FAIL" if errors else "PASS"
            _store_registry(registry)
            if errors:
                raise RuntimeError(" ".join(errors))
            context.scene.daf_settings.deformation_status = f"REGION VALID — {region['regionId']}"
            self.report({'INFO'}, f"Validated {_region_mode(region)} region {region['regionId']}.")
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
            preview_attached, preview_detached = _resolve_region_pair(region)
            _clear_gore_preview_pair(preview_attached, preview_detached)
            registered_objects = [
                _object(region.get("targetObject", region.get("attachedObject", ""))),
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
    _positions, virtual_weld = _virtual_weld_context(attached)
    selected_faces = [tuple(vertex.index for vertex in face.verts) for face in selected]
    virtual_components = trauma_field.virtual_face_components(
        selected_faces,
        virtual_weld["raw_vertex_to_virtual"],
    )
    if len(virtual_components) != 1:
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
        "virtualWeldTolerance": virtual_weld["tolerance"],
        "virtualWeldDigest": virtual_weld["digest"],
        "virtualWeldMemberCount": sum(
            len(group) for group in virtual_weld["virtual_members"] if len(group) > 1
        ),
        "virtualConnectedComponentCount": len(virtual_components),
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


class DAF_OT_save_trauma_stamp_library(Operator, ExportHelper):
    bl_idname = "daf.save_trauma_stamp_library"
    bl_label = "Save Trauma Stamp Library"
    bl_description = "Save every procedural trauma stamp stack to a portable, topology-bound JSON library"
    filename_ext = ".dsbstamps.json"
    filter_glob: StringProperty(default="*.dsbstamps.json", options={'HIDDEN'})

    def execute(self, context):
        try:
            path, library = save_stamp_library(self.filepath)
            context.scene.daf_settings.deformation_status = (
                f"STAMP LIBRARY SAVED — {int(library['keyCount'])} keys / {int(library['stampCount'])} stamps"
            )
            self.report(
                {'INFO'},
                f"Saved {int(library['stampCount'])} trauma stamps to {path.name}.",
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_load_trauma_stamp_library(Operator, ImportHelper):
    bl_idname = "daf.load_trauma_stamp_library"
    bl_label = "Load Trauma Stamp Library"
    bl_description = "Create and rebuild saved trauma-stamp keys on matching registered regions without overwriting existing work"
    filename_ext = ".dsbstamps.json"
    filter_glob: StringProperty(default="*.dsbstamps.json;*.json", options={'HIDDEN'})

    def execute(self, context):
        try:
            result = load_stamp_library(self.filepath, context)
            validation = result["validation"]
            message = (
                f"Loaded {result['importedKeyCount']} deformation keys and {result['stampCount']} trauma stamps"
            )
            if result["skippedKeyCount"]:
                message += f"; {result['skippedKeyCount']} identical keys skipped"
            if result["remappedCaptureCount"]:
                message += f"; {result['remappedCaptureCount']} captures rebound by exact positional anchors"
            if validation["status"] == "PASS":
                self.report({'INFO'}, message + ". Validation passed.")
            else:
                self.report(
                    {'WARNING'},
                    message + ". Validation needs review: " + "; ".join(validation.get("errors", [])[:2]),
                )
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
            entry["stampMode"] = "ALTERNATIVES"
            entry["activeStampId"] = str(created["stampId"])
            entry["recipeStatus"] = "PROCEDURAL_STACK"
            entry["legacy"] = False
            _store_metadata(attached, detached, payload)
            _invalidate_geodesic_cache()
            settings.deformation_active_stamp_id = created["stampId"]
            if bool(entry.get("previewEnabled", False)):
                preview_service.run_now(context, quality="FAST")
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
            entry["activeStampId"] = str(stamp["stampId"])
            entry["stampMode"] = "ALTERNATIVES"
            _store_metadata(_attached, _detached, _payload)
            if bool(entry.get("previewEnabled", False)):
                preview_service.run_now(context, quality="FAST")
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
            clear_surface_gore_preview()
            settings, _registry, _region, attached, detached, payload, _name, entry = _active_key_context(context)
            active = _active_stamp(settings, entry)
            replacement = _stamp_from_settings(context, stamp_id=active["stampId"], order_index=active["orderIndex"])
            for index, stamp in enumerate(entry["stamps"]):
                if stamp.get("stampId") == active["stampId"]:
                    replacement["enabled"] = bool(active.get("enabled", True))
                    entry["stamps"][index] = replacement
                    overlay = entry.get("surfaceGoreOverlay", {})
                    if overlay.get("linkedStampId") == active["stampId"] and overlay.get("goreRaisedEnabled", False):
                        entry["raisedGoreStatus"] = "STALE_REBUILD_REQUIRED"
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
            clear_surface_gore_preview()
            settings, _registry, _region, attached, detached, payload, _name, entry = _active_key_context(context)
            active = _active_stamp(settings, entry)
            stamps = [stamp for stamp in entry.get("stamps", []) if stamp.get("stampId") != active["stampId"]]
            entry["stamps"] = trauma_field.reindex_stamps(stamps)
            overlay = entry.get("surfaceGoreOverlay", {})
            if overlay.get("linkedStampId") == active["stampId"] and overlay.get("goreRaisedEnabled", False):
                entry["raisedGoreStatus"] = "STALE_REBUILD_REQUIRED"
            _invalidate_geodesic_cache()
            settings.deformation_active_stamp_id = ""
            if stamps:
                next_stamp = stamps[min(int(active.get("orderIndex", 0)), len(stamps) - 1)]
                entry["activeStampId"] = str(next_stamp.get("stampId", ""))
                _load_stamp_into_settings(settings, next_stamp)
            else:
                entry["activeStampId"] = ""
                entry["previewEnabled"] = False
            _store_metadata(attached, detached, payload)
            apply_damage_key_previews(context)
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


class DAF_OT_randomize_gore_seed(Operator):
    bl_idname = "daf.randomize_gore_seed"
    bl_label = "RANDOMIZE GORE SEED"
    bl_description = (
        "Choose a new master seed for overlay breakup, islands, fragments, thickness, "
        "organic shape, material response, and muscle-fiber directions"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            result = randomize_gore_seed(context)
            self.report(
                {'INFO'},
                f"Gore seed {result['previousSeed']} -> {result['seed']}.",
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_update_surface_gore_overlay(Operator):
    bl_idname = "daf.update_surface_gore_overlay"
    bl_label = "Apply Gore Overlay Settings"
    bl_description = "Save the visible surface gore settings and link them to the selected trauma stamp capture"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            overlay = update_surface_gore_overlay(context)
            self.report(
                {'INFO'},
                f"Surface gore {'enabled' if overlay['goreOverlayEnabled'] else 'disabled'} with {overlay['gorePresetId']}.",
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_preview_surface_gore_overlay(Operator):
    bl_idname = "daf.preview_surface_gore_overlay"
    bl_label = "Preview / Rebuild Current Gore"
    bl_description = "Save settings, refresh the stain, and rebuild ordinary attached/detached raised gore meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            update_surface_gore_overlay(context)
            result = preview_surface_gore(context)
            self.report(
                {'INFO'},
                f"Previewed stain on {result['maskedVertexCount']} vertices and rebuilt {result['raisedTriangleCount']} raised-gore triangles.",
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_clear_surface_gore_overlay_preview(Operator):
    bl_idname = "daf.clear_surface_gore_overlay_preview"
    bl_label = "Clear Stain Preview"
    bl_description = "Restore the original material slots and remove only Forge-managed gore preview data"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            clear_surface_gore_preview()
            context.scene.daf_settings.deformation_status = "SURFACE GORE PREVIEW CLEARED"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_clear_current_generated_gore(Operator):
    bl_idname = "daf.clear_current_generated_gore"
    bl_label = "Clear Current Generated Gore"
    bl_description = "Delete only Forge-owned raised gore meshes for the active deformation; keep its recipe"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            removed = clear_generated_gore(context)
            context.scene.daf_settings.deformation_status = f"CLEARED {len(removed)} RAISED GORE MESHES"
            self.report({'INFO'}, f"Removed {len(removed)} Forge-owned raised gore meshes.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_rebuild_all_generated_gore(Operator):
    bl_idname = "daf.rebuild_all_generated_gore"
    bl_label = "Rebuild All Generated Gore"
    bl_description = "Rebuild every valid enabled raised-gore recipe without touching source meshes or shape keys"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            result = rebuild_all_generated_gore(context)
            summary = (
                f"Raised gore: {len(result['rebuilt'])} rebuilt, "
                f"{len(result['skipped'])} skipped, {len(result['failed'])} failed"
            )
            context.scene.daf_settings.deformation_status = summary.upper()
            if result["failed"]:
                self.report({'WARNING'}, summary + ". " + "; ".join(result["failed"][:2]))
            else:
                self.report({'INFO'}, summary + ".")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_validate_gore_geometry(Operator):
    bl_idname = "daf.validate_gore_geometry"
    bl_label = "Validate Gore Geometry"
    bl_description = "Run separate raised-gore ownership, geometry, material, budget, pairing, and export checks"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            validation = validate_deformations(require_keys=False)
            raised_failures = [
                record for record in validation.get("keys", [])
                if record.get("raisedGoreValidationStatus") == "FAIL"
            ]
            if raised_failures:
                context.scene.daf_settings.deformation_gore_validation_status = "FAIL"
                self.report({'ERROR'}, f"Raised gore validation failed for {len(raised_failures)} deformation keys.")
                return {'CANCELLED'}
            triangles = int(validation.get("raisedGoreTriangleCount", 0))
            settings = context.scene.daf_settings
            settings.deformation_gore_validation_status = "PASS"
            settings.deformation_preview_final_gore_triangles = triangles
            try:
                _settings, _registry, _region, _attached, _detached, _payload, _name, entry = (
                    _active_key_context(context)
                )
                measurements_by_role = entry.get("goreValidationMeasurements", {})
                measurements = (
                    measurements_by_role.get("ATTACHED")
                    or measurements_by_role.get("CORE")
                    or next(iter(measurements_by_role.values()), {})
                )
                settings.deformation_gore_max_proudness = float(
                    measurements.get("maximumProudness", 0.0)
                )
                settings.deformation_gore_median_cavity_depth = float(
                    measurements.get("medianLinerDepth", 0.0)
                )
                settings.deformation_gore_minimum_liner_separation = float(
                    measurements.get("minimumSkinToLinerSeparation", 0.0)
                )
            except Exception:
                pass
            self.report({'INFO'}, f"Raised gore geometry passed; {triangles} generated triangles across the asset.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_new_compound_trauma_event(Operator):
    bl_idname = "daf.new_compound_trauma_event"
    bl_label = "New Compound Trauma Event"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            event = create_compound_event(context)
            self.report({'INFO'}, f"Created compound trauma event {event['eventId']}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_select_compound_trauma_event(Operator):
    bl_idname = "daf.select_compound_trauma_event"
    bl_label = "Select Compound Trauma Event"
    bl_options = {'REGISTER'}
    event_id: StringProperty()

    def execute(self, context):
        try:
            select_compound_event(context, self.event_id)
            context.scene.daf_settings.deformation_status = f"ACTIVE COMPOUND EVENT — {self.event_id}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_add_active_region_to_compound_event(Operator):
    bl_idname = "daf.add_active_region_to_compound_event"
    bl_label = "Add Active Region to Event"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            participant = add_active_region_to_compound_event(context)
            self.report({'INFO'}, f"Added {participant['regionId']}/{participant['childKeyName']}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_remove_active_region_from_compound_event(Operator):
    bl_idname = "daf.remove_active_region_from_compound_event"
    bl_label = "Remove Region from Event"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            region_id = remove_active_region_from_compound_event(context)
            self.report({'INFO'}, f"Removed region {region_id} from the active compound event.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_capture_compound_impact_field(Operator):
    bl_idname = "daf.capture_compound_impact_field"
    bl_label = "Capture Shared Impact Field"
    bl_description = "Use the active surface capture when available, otherwise the 3D cursor, and store one world-space field"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            field = capture_compound_world_field(context)
            self.report({'INFO'}, f"Captured shared field with radius {float(field['radius']):.3f} m.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_rebuild_compound_trauma_event(Operator):
    bl_idname = "daf.rebuild_compound_trauma_event"
    bl_label = "Rebuild Compound Event"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            event = rebuild_compound_event(context)
            self.report({'INFO'}, f"Rebuilt {event['eventId']} across {len(event['participants'])} regions.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_preview_compound_trauma_event(Operator):
    bl_idname = "daf.preview_compound_trauma_event"
    bl_label = "Preview Compound Event"
    bl_options = {'REGISTER'}
    weight: FloatProperty(default=1.0, min=0.0, max=2.0)

    def execute(self, context):
        try:
            preview_compound_event(context, self.weight)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_clear_compound_trauma_preview(Operator):
    bl_idname = "daf.clear_compound_trauma_preview"
    bl_label = "Clear Compound Preview"
    bl_description = "Atomically zero every compound child and hide its stains and gore without deleting authored data"
    bl_options = {'REGISTER'}

    def execute(self, context):
        cleared = clear_compound_preview(context)
        self.report({'INFO'}, f"Cleared damage preview for {cleared} compound participants.")
        return {'FINISHED'}


class DAF_OT_validate_compound_trauma_event(Operator):
    bl_idname = "daf.validate_compound_trauma_event"
    bl_label = "Validate Compound Event"
    bl_options = {'REGISTER'}

    def execute(self, context):
        validation = validate_compound_events()
        context.scene.daf_settings.deformation_status = "COMPOUND VALIDATION " + validation["status"]
        if validation["status"] == "PASS":
            self.report({'INFO'}, f"Validated {validation['eventCount']} compound trauma events.")
            return {'FINISHED'}
        self.report({'ERROR'}, "; ".join(validation["errors"][:4]))
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
    bl_description = "Create four empty compatibility keys for optional artist sculpting"
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


class DAF_OT_create_blunt_gore_head_deformations(Operator):
    bl_idname = "daf.create_blunt_gore_head_deformations"
    bl_label = "Create Blunt Gore Head Set"
    bl_description = "Create the four directional v001 head-impact keys used by blunt surface gore authoring"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _registry, region, attached, detached = _resolve_active_region(context)
            if region.get("regionId") != "head":
                raise RuntimeError("Create Blunt Gore Head Set requires the registered head region.")
            for name, template in BLUNT_GORE_HEAD_KEYS.items():
                _ensure_key_pair(name, template)
            _zero_managed_weights(attached, include_preview=True)
            _set_authoring_view(attached, detached, 'ATTACHED')
            _select_key(context.scene.daf_settings, "Head_Impact_Left_v001")
            context.scene.daf_settings.deformation_status = "BLUNT GORE HEAD SET READY"
            self.report({'INFO'}, "Created four directional paired head-impact deformation keys.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_create_body_impact_starters(Operator):
    bl_idname = "daf.create_body_impact_starters"
    bl_label = "Create Body Impact Starters"
    bl_description = "Create empty semantic body-impact records; the artist must still capture each intended surface and add stamps"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _registry, region, target, detached = _resolve_active_region(context)
            if _region_mode(region) != CORE_SINGLE:
                raise RuntimeError("Body impact starters require an active core single-mesh region.")
            for name, template in BODY_IMPACT_STARTER_KEYS.items():
                _ensure_key_pair(name, template)
            _zero_managed_weights(target, include_preview=True)
            _set_authoring_view(target, detached, 'ATTACHED')
            _select_key(context.scene.daf_settings, "Body_Impact_Front_v001")
            context.scene.daf_settings.deformation_status = "BODY IMPACT STARTERS READY — CAPTURE REQUIRED"
            self.report({'INFO'}, "Created body impact records. Capture the intended surface before adding stamps.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_create_forearm_impact_starter(Operator):
    bl_idname = "daf.create_forearm_impact_starter"
    bl_label = "Create Forearm Impact Starter"
    bl_description = "Create one empty outer-forearm impact record on the active paired forearm region"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _registry, region, attached, detached = _resolve_active_region(context)
            if _region_mode(region) != PAIRED_SEGMENT:
                raise RuntimeError("Forearm impact starters require an active paired-segment region.")
            identity = " ".join((str(region.get("regionId", "")), attached.name, detached.name)).lower()
            if any(token in identity for token in ("left", "_l", "forearm_l")):
                side = "LEFT"
            elif any(token in identity for token in ("right", "_r", "forearm_r")):
                side = "RIGHT"
            else:
                raise RuntimeError("The active pair is not semantically identifiable as a left or right forearm.")
            name = FOREARM_IMPACT_STARTER_KEYS[side]
            _ensure_key_pair(name, {
                "family": "localized_dent", "side": side.lower(), "mirrorPartner": "",
                "seedRadius": 0.060, "seedDepth": 0.020, "seedFalloff": 1.70,
                "maximumInfluence": 1.0, "maximumDisplacement": 0.040,
            })
            _zero_managed_weights(attached, include_preview=True)
            _set_authoring_view(attached, detached, 'ATTACHED')
            _select_key(context.scene.daf_settings, name)
            context.scene.daf_settings.deformation_status = "FOREARM IMPACT STARTER READY — CAPTURE REQUIRED"
            self.report({'INFO'}, f"Created {name}. Capture the outer forearm before adding stamps.")
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
            _select_key(context.scene.daf_settings, self.key_name)
            apply_damage_key_previews(context)
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
            clear_damage_preview(context, update_status=False)
            _select_key(context.scene.daf_settings, self.key_name)
            preview_managed_deformation(context, self.key_name)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_zero_deformations(Operator):
    bl_idname = "daf.zero_deformations"
    bl_label = "Zero All Deformations"
    bl_description = "Atomically clear deformation weights, stain resources, and raised-gore visibility without deleting recipes or meshes"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            clear_damage_preview(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_delete_managed_deformation(Operator):
    bl_idname = "daf.delete_managed_deformation"
    bl_label = "Delete Managed Deformation"
    bl_description = "Delete only the selected Forge-managed deformation key from the active region mesh or registered pair"
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
            clear_surface_gore_preview()
            region_id = str(attached.get("dsb_deformation_region", _active_region_id(context)))
            _remove_generated_gore_objects(region_id, name)
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
    bl_description = "Copy the temporary seed into the active permanent deformation key and synchronize a detached partner when present"
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
            _registry, region, _source, _paired = _resolve_active_region(context)
            raw_overlay = entry.get("surfaceGoreOverlay")
            if isinstance(raw_overlay, dict) and raw_overlay.get("goreOverlayEnabled", False):
                _install_existing_surface_stain_preview(context, str(region.get("regionId", "")), name)
            inspection = 'CORE' if detached is None else 'ATTACHED'
            _set_single_damage_preview_state(context, region.get("regionId", ""), name, target.value, inspection)
            _set_authoring_view(attached, detached, inspection, context)
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
    bl_description = "Leave Sculpt Mode, synchronize a detached partner when present, and validate limits"
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
            target_entry.pop("surfaceGoreOverlay", None)
            target_entry.pop("goreOverlayDigest", None)
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


class DAF_OT_show_deformation_attached(Operator):
    bl_idname = "daf.show_deformation_attached"
    bl_label = "Show Attached"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            attached, detached = set_damage_preview_inspection_mode(context, 'ATTACHED')
            _set_active_object(context, attached)
            context.scene.daf_settings.deformation_status = "VIEWING ATTACHED REGION"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_show_deformation_detached(Operator):
    bl_idname = "daf.show_deformation_detached"
    bl_label = "Show Detached"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            attached, detached = set_damage_preview_inspection_mode(context, 'DETACHED')
            _set_active_object(context, detached)
            context.scene.daf_settings.deformation_status = "VIEWING DETACHED REGION"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_show_deformation_overlay(Operator):
    bl_idname = "daf.show_deformation_overlay"
    bl_label = "Show Both"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            _attached, _detached = set_damage_preview_inspection_mode(context, 'BOTH')
            context.scene.daf_settings.deformation_status = "PAIR OVERLAY ENABLED"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_repair_legacy_pair_sync(Operator):
    bl_idname = "daf.repair_legacy_pair_sync"
    bl_label = "Repair Legacy Pair Sync"
    bl_description = "Safely resynchronize Forge-managed legacy detached keys from their authoritative attached copies"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            result = repair_legacy_pair_sync(context=context)
            validation = validate_deformations(require_keys=True)
            settings = context.scene.daf_settings
            settings.last_deformation_validation = validation["status"]
            settings.deformation_status = result["summary"]
            report = (
                f"{result['summary']} — {result['skipped']} skipped / "
                f"{result['inspected']} inspected; validation {validation['status']}"
            )
            if validation["status"] == "PASS" and not result["unrepairable"]:
                self.report({'INFO'}, report)
            else:
                validation_detail = "; ".join(validation.get("errors", [])[:2])
                self.report({'WARNING'}, report + (": " + validation_detail if validation_detail else ""))
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_validate_deformations(Operator):
    bl_idname = "daf.validate_deformations"
    bl_label = "Validate Deformations"
    bl_description = "Validate core and paired region contracts, morphs, compound events, gore, finite coordinates, and displacement limits"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            validation = validate_deformations(require_keys=True)
            settings = context.scene.daf_settings
            settings.last_deformation_validation = validation["status"]
            settings.deformation_status = "VALIDATION " + validation["status"]
            if validation["status"] == "PASS":
                self.report(
                    {'INFO'},
                    f"Validated {validation['managedKeyCount']} deformation keys across "
                    f"{validation['registeredRegionCount']} regions.",
                )
                return {'FINISHED'}
            self.report({'ERROR'}, "; ".join(validation["errors"][:4]))
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def _legacy_draw_panel_source(box, context, settings):
    regions = box.box()
    regions.label(text="1. Core Single-Mesh / Paired Segment Regions", icon='MESH_DATA')
    regions.prop(settings, "deformation_region")
    row = regions.row(align=True)
    row.operator("daf.select_deformation_region", text="Use Selected Region", icon='RESTRICT_SELECT_OFF')
    row.operator("daf.validate_deformation_region", text="Validate Region", icon='CHECKMARK')
    regions.prop(settings, "deformation_region_id")
    regions.prop(settings, "deformation_related_seam_id")
    row = regions.row(align=True)
    row.operator("daf.register_deformation_region", text="Register Selected Pair", icon='ADD')
    row.operator("daf.register_core_deformation_region", text="Register Selected Core Mesh", icon='MESH_DATA')
    row = regions.row(align=True)
    row.operator("daf.remove_deformation_region", text="Remove Registration", icon='X')
    try:
        registry, region, attached, detached = _resolve_active_region(context)
        contract = validate_region_contract(region, attached, detached)
        icon = 'CHECKMARK' if contract["status"] == "PASS" else 'ERROR'
        if _region_mode(region) == CORE_SINGLE:
            regions.label(text=f"{region['regionId']}: CORE_SINGLE / {attached.name}", icon=icon)
        else:
            regions.label(text=f"{region['regionId']}: PAIRED_SEGMENT / {attached.name} ↔ {detached.name}", icon=icon)
        regions.label(text=f"Topology: {contract['status']} — {contract['attachedVertexCount']} vertices / {contract['attachedPolygonCount']} polygons")
        regions.label(text="Status: " + region.get("validationStatus", "NOT VALIDATED"))
    except Exception as exc:
        regions.label(text=str(exc), icon='ERROR')
        regions.label(text="Select one core mesh or two exact-index paired meshes", icon='INFO')
        return

    status = box.box()
    status.label(text="Status: " + settings.deformation_status, icon='INFO')
    status.label(text="Validation: " + settings.last_deformation_validation)

    library = box.box()
    library.label(text="2. Active Deformation", icon='SHAPEKEY_DATA')
    rename = library.row(align=True)
    rename.prop(settings, "deformation_key_name", text="Rename to")
    rename_button = rename.row(align=True)
    rename_button.enabled = bool(settings.deformation_active_key)
    rename_action = rename_button.operator("daf.rename_damage_key", text="Rename Active")
    rename_action.key_name = settings.deformation_active_key
    row = library.row(align=True)
    row.operator("daf.create_damage_shape_key", text="Create Damage Shape Key", icon='ADD')
    row.operator("daf.create_standard_head_deformations", text="Create Standard Head Set", icon='PRESET')
    library.operator("daf.create_blunt_gore_head_deformations", text="Create Blunt Gore Head Set", icon='PRESET')

    body_arm = library.box()
    body_arm.prop(
        settings, "ui_body_arm_trauma_open", text="Body and Arm Trauma",
        icon='TRIA_DOWN' if settings.ui_body_arm_trauma_open else 'TRIA_RIGHT', emboss=False,
    )
    if settings.ui_body_arm_trauma_open:
        row = body_arm.row(align=True)
        row.operator("daf.create_body_impact_starters", text="Create Body Impact Starters", icon='PRESET')
        row.operator("daf.create_forearm_impact_starter", text="Create Forearm Impact Starter", icon='PRESET')
        body_arm.label(text="Starter records require an explicit artist surface capture", icon='INFO')

    names = _managed_names(attached)
    if names:
        for name in names:
            row = library.row(align=True)
            select = row.operator("daf.select_deformation_key", text=name, depress=settings.deformation_active_key == name)
            select.key_name = name
            solo = row.operator("daf.solo_deformation_key", text="Solo")
            solo.key_name = name
    else:
        library.label(text="No managed deformation keys yet", icon='INFO')

    clear = library.column()
    clear.scale_y = 1.3
    clear.alert = True
    clear.operator("daf.clear_managed_preview", text="CLEAR DAMAGE PREVIEW", icon='X')
    row = library.row(align=True)
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
        if capture.get("virtualConnectedComponentCount") is not None:
            capture_box.label(
                text=f"Virtual seam connectivity: {capture.get('virtualConnectedComponentCount')} component",
                icon='LINKED',
            )
            capture_box.label(text=f"Virtual weld members: {capture.get('virtualWeldMemberCount', 0)}")
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
    row = stamps_box.row(align=True)
    row.operator("daf.save_trauma_stamp_library", text="Save Stamp Library...", icon='EXPORT')
    row.operator("daf.load_trauma_stamp_library", text="Load Stamp Library...", icon='IMPORT')
    stamps_box.label(text="Libraries save every procedural stack across registered regions", icon='INFO')
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

    gore = box.box()
    gore.prop(
        settings,
        "ui_surface_gore_open",
        text="5. Surface Gore Overlay",
        icon='TRIA_DOWN' if settings.ui_surface_gore_open else 'TRIA_RIGHT',
        emboss=False,
    )
    if settings.ui_surface_gore_open:
        gore.label(text="Intact exterior + stain + optional exportable raised shell", icon='INFO')
        gore.prop(settings, "deformation_gore_enabled")
        if settings.deformation_gore_enabled:
            stain = gore.box()
            stain.label(text="Surface Stain")
            stain.prop(settings, "deformation_gore_coverage", text="Stain Coverage", slider=True)
            stain.prop(settings, "deformation_gore_scatter", text="Stain Breakup", slider=True)
            stain.prop(settings, "deformation_gore_edge_feather", slider=True)
            raised = gore.box()
            raised.label(text="Raised Gore")
            raised.prop(settings, "deformation_gore_raised_enabled")
            if settings.deformation_gore_raised_enabled:
                raised.prop(settings, "deformation_gore_clot_coverage", slider=True)
                raised.prop(settings, "deformation_gore_core_density", slider=True)
                raised.prop(settings, "deformation_gore_clot_thickness")
                raised.prop(settings, "deformation_gore_thickness_variation", slider=True)
                raised.prop(settings, "deformation_gore_island_breakup", slider=True)
                raised.prop(settings, "deformation_gore_peripheral_fragments", slider=True)
                raised.prop(settings, "deformation_gore_surface_offset")
                raised.prop(settings, "deformation_gore_geometry_density", slider=True)
                raised.prop(settings, "deformation_gore_maximum_triangles")
                shape = raised.box()
                shape.label(text="Organic Shape Refinement")
                shape.prop(settings, "deformation_gore_organic_irregularity", slider=True)
                shape.prop(settings, "deformation_gore_surface_roundness", slider=True)
                shape.prop(settings, "deformation_gore_texture_enabled")
                if settings.deformation_gore_texture_enabled:
                    composition = shape.box()
                    composition.label(text="Additive Surface Composition")
                    composition.prop(settings, "deformation_gore_fiber_texture_strength", slider=True)
                    composition.prop(settings, "deformation_gore_base_color_strength", slider=True)
                    composition.label(text="Both contributions accumulate; neither replaces the other.", icon='INFO')
                rim = raised.box()
                rim.label(text="Compromised Inner Barrier")
                rim.prop(settings, "deformation_gore_inner_rim_enabled")
                if settings.deformation_gore_inner_rim_enabled:
                    rim.prop(settings, "deformation_gore_inner_rim_width")
                    rim.prop(settings, "deformation_gore_inner_rim_strength", slider=True)
            response = gore.box()
            response.label(text="Material Variation")
            response.prop(settings, "deformation_gore_wetness", slider=True)
            response.prop(settings, "deformation_gore_wetness_variation", slider=True)
            response.prop(settings, "deformation_gore_dark_clot_bias", slider=True)
            response.prop(settings, "deformation_gore_rough_edge_bias", slider=True)
            response.prop(settings, "deformation_gore_color_intensity", slider=True)
            response.prop(settings, "deformation_gore_darkness", slider=True)
            response.prop(settings, "deformation_gore_color_bias")
            variation = gore.box()
            variation.label(text="Variation")
            seed_row = variation.row(align=True)
            seed_row.prop(settings, "deformation_gore_mask_seed")
            seed_row.operator("daf.randomize_gore_seed", text="", icon='FILE_REFRESH')
            variation.label(text="Master seed changes the entire overlay, including fiber directions.", icon='INFO')
            variation.prop(settings, "deformation_gore_user_customized")
        gore.operator("daf.update_surface_gore_overlay", text="Apply Gore Overlay Settings", icon='CHECKMARK')
        actions = gore.box()
        actions.label(text="Actions")
        actions.operator("daf.preview_surface_gore_overlay", text="Preview / Rebuild Current Gore", icon='MATERIAL')
        row = actions.row(align=True)
        row.operator("daf.clear_current_generated_gore", text="Clear Current Generated Gore", icon='TRASH')
        row.operator("daf.clear_surface_gore_overlay_preview", text="Clear Stain Preview", icon='X')
        actions.operator("daf.rebuild_all_generated_gore", text="Rebuild All Generated Gore", icon='FILE_REFRESH')
        actions.operator("daf.validate_gore_geometry", text="Validate Gore Geometry", icon='CHECKMARK')
        if entry.get("surfaceGoreOverlay"):
            overlay = entry["surfaceGoreOverlay"]
            gore.label(
                text=f"Saved: {overlay.get('gorePresetId', '<invalid>')} - {overlay.get('validationStatus', 'NOT_VALIDATED')}",
                icon='CHECKMARK' if overlay.get('validationStatus') == 'PASS' else 'INFO',
            )
            gore.label(text=f"Linked stamp: {overlay.get('linkedStampId', '<none>')}")
            triangle_counts = entry.get("goreTriangleCounts", {})
            if triangle_counts:
                if _region_mode(region) == CORE_SINGLE:
                    gore.label(text=f"Triangles: core {int(triangle_counts.get('CORE', 0)):,}", icon='MESH_DATA')
                else:
                    gore.label(
                        text=(
                            f"Triangles: attached {int(triangle_counts.get('ATTACHED', 0)):,} / "
                            f"detached {int(triangle_counts.get('DETACHED', 0)):,}"
                        ),
                        icon='MESH_DATA',
                    )
            gore.label(text="Export default: inactive; activate with matching deformation", icon='HIDE_ON')

    compound = box.box()
    compound.prop(
        settings, "ui_compound_trauma_open", text="6. Compound Trauma Events",
        icon='TRIA_DOWN' if settings.ui_compound_trauma_open else 'TRIA_RIGHT', emboss=False,
    )
    if settings.ui_compound_trauma_open:
        compound.prop(settings, "compound_event_id")
        compound.prop(settings, "compound_display_name")
        row = compound.row(align=True)
        row.operator("daf.new_compound_trauma_event", text="New Compound Trauma Event", icon='ADD')
        row.operator("daf.add_active_region_to_compound_event", text="Add Active Region to Event", icon='LINKED')
        compound.operator("daf.remove_active_region_from_compound_event", text="Remove Region from Event", icon='UNLINKED')
        for event_value in registry.get("compoundEvents", []):
            event_id = str(event_value.get("eventId", ""))
            select = compound.operator(
                "daf.select_compound_trauma_event",
                text=f"{event_value.get('displayName', event_id)} ({len(event_value.get('participants', []))})",
                depress=event_id == settings.compound_active_event_id,
                icon='CHECKMARK' if event_value.get("validationStatus") == "PASS" else 'INFO',
            )
            select.event_id = event_id
        field_box = compound.box()
        field_box.label(text="Shared World-Space Impact Field")
        field_box.prop(settings, "compound_trauma_family")
        field_box.prop(settings, "compound_semantic_direction")
        field_box.prop(settings, "compound_severity")
        field_box.prop(settings, "compound_impact_origin")
        field_box.prop(settings, "compound_impact_direction")
        row = field_box.row(align=True)
        row.prop(settings, "compound_impact_radius")
        row.prop(settings, "compound_impact_depth")
        row = field_box.row(align=True)
        row.prop(settings, "compound_impact_falloff")
        row.prop(settings, "compound_impact_strength")
        field_box.prop(settings, "compound_displacement_limit")
        field_box.prop(settings, "compound_event_seed")
        field_box.operator("daf.capture_compound_impact_field", text="Capture Shared Impact Field", icon='PIVOT_CURSOR')
        seam_box = compound.box()
        seam_box.label(text="Seam Continuity")
        seam_box.prop(settings, "compound_linked_seam_ids")
        seam_box.prop(settings, "compound_continuity_mode")
        seam_box.prop(settings, "compound_activation_weight")
        compound.operator("daf.rebuild_compound_trauma_event", text="REBUILD COMPOUND EVENT", icon='FILE_REFRESH')
        row = compound.row(align=True)
        preview_zero = row.operator("daf.preview_compound_trauma_event", text="Event Zero", icon='LOOP_BACK')
        preview_zero.weight = 0.0
        preview_full = row.operator("daf.preview_compound_trauma_event", text="Preview Compound Event", icon='PLAY')
        preview_full.weight = 1.0
        row.operator("daf.clear_compound_trauma_preview", text="Clear Event Preview", icon='X')
        compound.operator("daf.validate_compound_trauma_event", text="Validate Compound Event", icon='CHECKMARK')
        compound.label(text="One semantic event; one mesh-local morph per participant", icon='INFO')

    preview = box.box()
    preview.label(text="7. Preview and Rebuild", icon='HIDE_OFF')
    row = preview.row(align=True)
    row.operator("daf.show_deformation_attached", text="Attached", icon='OUTLINER_OB_MESH')
    detached_controls = row.row(align=True)
    detached_controls.enabled = detached is not None
    detached_controls.operator("daf.show_deformation_detached", text="Detached", icon='PHYSICS')
    detached_controls.operator("daf.show_deformation_overlay", text="Both", icon='HIDE_OFF')
    row = preview.row(align=True)
    row.operator("daf.preview_active_trauma_stamp", text="Preview Active Stamp", icon='PLAY')
    clear = preview.column()
    clear.scale_y = 1.3
    clear.alert = True
    clear.operator("daf.clear_managed_preview", text="CLEAR DAMAGE PREVIEW", icon='X')
    preview.operator("daf.rebuild_active_deformation", text="REBUILD ACTIVE DEFORMATION", icon='FILE_REFRESH')
    preview.label(text="Rebuild always replays enabled stamps from Basis", icon='INFO')

    sculpt = box.box()
    sculpt.label(text="8. Sculpt and Sync", icon='SCULPTMODE_HLT')
    row = sculpt.row(align=True)
    row.operator("daf.begin_deformation_sculpt", text="Begin Sculpt", icon='SCULPTMODE_HLT')
    row.operator("daf.finish_deformation_sculpt", text="Finish Sculpt & Sync", icon='FILE_TICK')
    sculpt.label(text="Sculpting is optional; Damage Blueprints remain procedural.", icon='INFO')

    validation_box = box.box()
    validation_box.label(text="9. Validation and Export", icon='CHECKMARK')
    validation_box.operator("daf.validate_deformations", text="Validate Morph Targets", icon='CHECKMARK')
    if _region_mode(region) == PAIRED_SEGMENT:
        validation_box.operator("daf.repair_legacy_pair_sync", text="REPAIR LEGACY PAIR SYNC", icon='FILE_REFRESH')
    repair_summary = payload.get("legacyPairRepair", {}).get("summary")
    if repair_summary:
        validation_box.label(text="Legacy pair repair: " + repair_summary.replace("LEGACY PAIR REPAIR — ", ""), icon='LINKED')
    validation_box.label(text="Export remains in Damage Segment & Stump Authoring", icon='EXPORT')
    validation_box.label(
        text="Core owns one morph; pairs stay exact-index synchronized",
        icon='LINKED',
    )
    validation_box.label(text="Source mesh and rig remain protected", icon='LOCKED')


def _advanced_authoring_foldout(box, settings, property_name, title, icon):
    section = box.box()
    row = section.row(align=True)
    opened = bool(getattr(settings, property_name))
    row.prop(
        settings,
        property_name,
        text=title,
        icon='TRIA_DOWN' if opened else 'TRIA_RIGHT',
        emboss=False,
    )
    if not opened:
        return None
    section.label(text=title, icon=icon)
    return section


def draw_panel(box, context, settings):
    """Draw every expert workflow from deliberately cached, mesh-free state."""

    summary = cached_ui_summary(settings)
    registry = summary.get("registry", {})
    metadata = summary.get("metadata", {})
    region = summary.get("region", {})
    active_key = summary.get("key", {})

    regions = _advanced_authoring_foldout(
        box, settings, "ui_advanced_regions_open", "Manual Region Registration", 'MESH_DATA'
    )
    if regions is not None:
        regions.prop(settings, "deformation_region")
        row = regions.row(align=True)
        row.operator("daf.select_deformation_region", text="Use Selected Region")
        row.operator("daf.validate_deformation_region", text="Validate Region")
        regions.prop(settings, "deformation_region_id")
        regions.prop(settings, "deformation_related_seam_id")
        row = regions.row(align=True)
        row.operator("daf.register_deformation_region", text="Register Selected Pair")
        row.operator("daf.register_core_deformation_region", text="Register Selected Core Mesh")
        regions.operator("daf.remove_deformation_region", text="Remove Registration")
        if region:
            regions.label(text=f"{region.get('regionId')}: {region.get('regionMode')} / {region.get('validationStatus')}")
            regions.label(text=f"Cached inventory: {int(region.get('vertexCount', 0)):,} vertices / {int(region.get('polygonCount', 0)):,} polygons")

    keys = _advanced_authoring_foldout(
        box, settings, "ui_advanced_deformations_open", "Managed Deformations", 'SHAPEKEY_DATA'
    )
    if keys is not None:
        rename = keys.row(align=True)
        rename.prop(settings, "deformation_key_name", text="Rename to")
        rename_button = rename.row(align=True)
        rename_button.enabled = bool(settings.deformation_active_key)
        rename_action = rename_button.operator("daf.rename_damage_key", text="Rename Active")
        rename_action.key_name = settings.deformation_active_key
        row = keys.row(align=True)
        row.operator("daf.create_damage_shape_key", text="Create Damage Shape Key")
        row.operator("daf.create_standard_head_deformations", text="Create Standard Head Set")
        keys.operator("daf.create_blunt_gore_head_deformations", text="Create Blunt Gore Head Set")
        row = keys.row(align=True)
        row.operator("daf.create_body_impact_starters", text="Create Body Impact Starters")
        row.operator("daf.create_forearm_impact_starter", text="Create Forearm Impact Starter")
        for record in metadata.get("keys", []):
            select = keys.operator(
                "daf.select_deformation_key",
                text=record.get("name", "<unnamed>"),
                depress=record.get("name") == settings.deformation_active_key,
            )
            select.key_name = record.get("name", "")
        clear = keys.column()
        clear.scale_y = 1.3
        clear.alert = True
        clear.operator("daf.clear_managed_preview", text="CLEAR DAMAGE PREVIEW", icon='X')
        row = keys.row(align=True)
        row.operator("daf.delete_managed_deformation", text="Delete Active")
        row.operator("daf.create_mirrored_deformation", text="Mirror Active")

    capture = _advanced_authoring_foldout(
        box, settings, "ui_advanced_capture_open", "Exact Placement & Capture", 'FACESEL'
    )
    if capture is not None:
        capture.prop(settings, "deformation_capture_mode")
        raw_capture = capture.column()
        raw_capture.enabled = str(settings.deformation_impact_control_mode) == 'MANUAL'
        raw_capture.prop(settings, "deformation_influence_mode")
        raw_capture.prop(settings, "deformation_distance_mode")
        raw_capture.prop(settings, "deformation_feather_distance")
        row = capture.row(align=True)
        row.operator("daf.capture_deformation_selected_face", text="Capture Single Face")
        row.operator("daf.capture_deformation_selected_patch", text="Capture Connected Face Patch")
        row = capture.row(align=True)
        row.operator("daf.capture_deformation_selected_vertices", text="Capture Selected Vertices")
        row.operator("daf.capture_deformation_cursor", text="Capture 3D Cursor")

    stamps = _advanced_authoring_foldout(
        box, settings, "ui_advanced_stamps_open", "Stamp Stack & Portable Libraries", 'MOD_DISPLACE'
    )
    if stamps is not None:
        for stamp in active_key.get("stamps", []):
            select = stamps.operator(
                "daf.select_trauma_stamp",
                text=f"{int(stamp.get('orderIndex', 0)) + 1}. {stamp.get('displayName', '<stamp>')}",
                depress=stamp.get("stampId") == settings.deformation_active_stamp_id,
            )
            select.stamp_id = stamp.get("stampId", "")
        row = stamps.row(align=True)
        row.operator("daf.add_trauma_stamp", text="Add Stamp")
        row.operator("daf.duplicate_trauma_stamp", text="Duplicate")
        row.operator("daf.remove_trauma_stamp", text="Remove")
        row = stamps.row(align=True)
        row.operator("daf.move_trauma_stamp_up", text="Move Up")
        row.operator("daf.move_trauma_stamp_down", text="Move Down")
        row.operator("daf.toggle_trauma_stamp", text="Enable / Disable")
        stamps.label(
            text="Portable reuse is handled by Damage Blueprints in the VIP workflow.",
            icon='ASSET_MANAGER',
        )
        mode = str(settings.deformation_impact_control_mode)
        stamps.label(
            text=f"Impact Control: {mode} / {'IMPACT PEDAL' if mode == 'MACRO' else 'CUSTOM'}",
            icon='LOCKED' if mode == 'MACRO' else 'UNLOCKED',
        )
        if mode == 'MACRO':
            stamps.operator("daf.use_manual_impact_control", text="USE MANUAL CONTROL")
        else:
            row = stamps.row(align=True)
            row.operator("daf.fit_impact_macros", text="FIT MACROS TO CURRENT VALUES")
            row.operator("daf.return_to_macro_control", text="RETURN TO MACRO CONTROL")
        raw_stamp = stamps.column()
        raw_stamp.enabled = mode == 'MANUAL'
        for prop in (
            "deformation_stamp_name", "deformation_stamp_family", "deformation_seed_radius",
            "deformation_seed_depth", "deformation_seed_falloff", "deformation_stamp_strength",
            "deformation_seed_direction_mode", "deformation_seed_custom_direction",
            "deformation_seed_seam_protection", "deformation_max_vertex_displacement",
            "deformation_maximum_influence",
        ):
            raw_stamp.prop(settings, prop)
        raw_stamp.operator("daf.update_trauma_stamp", text="Update Active Stamp")

    gore = _advanced_authoring_foldout(
        box, settings, "ui_advanced_gore_open", "Detailed Raised Gore", 'MATERIAL'
    )
    if gore is not None:
        mode = str(settings.deformation_impact_control_mode)
        raw_gore = gore.column()
        raw_gore.enabled = mode == 'MANUAL'
        for prop in (
            "deformation_gore_enabled",
            "deformation_gore_coverage", "deformation_gore_scatter", "deformation_gore_edge_feather",
            "deformation_gore_raised_enabled", "deformation_gore_clot_coverage", "deformation_gore_core_density",
            "deformation_gore_clot_thickness", "deformation_gore_thickness_variation",
            "deformation_gore_island_breakup", "deformation_gore_peripheral_fragments",
            "deformation_gore_surface_offset", "deformation_gore_geometry_density",
            "deformation_gore_maximum_triangles", "deformation_gore_wetness",
            "deformation_gore_wetness_variation", "deformation_gore_dark_clot_bias",
            "deformation_gore_rough_edge_bias", "deformation_gore_color_intensity",
            "deformation_gore_organic_irregularity", "deformation_gore_surface_roundness",
            "deformation_gore_texture_enabled", "deformation_gore_fiber_texture_strength",
            "deformation_gore_base_color_strength", "deformation_gore_inner_rim_enabled",
            "deformation_gore_inner_rim_width", "deformation_gore_inner_rim_strength",
            "deformation_gore_darkness", "deformation_gore_color_bias",
            "deformation_gore_user_customized",
        ):
            raw_gore.prop(settings, prop)
        seed_row = raw_gore.row(align=True)
        seed_row.prop(settings, "deformation_gore_mask_seed")
        seed_row.operator("daf.randomize_gore_seed", text="Randomize Seed")
        raw_gore.operator("daf.update_surface_gore_overlay", text="Apply Gore Overlay Settings")
        gore.operator("daf.preview_surface_gore_overlay", text="Preview / Rebuild Current Gore")
        row = gore.row(align=True)
        row.operator("daf.clear_current_generated_gore", text="Clear Current Generated Gore")
        row.operator("daf.clear_surface_gore_overlay_preview", text="Clear Stain Preview")
        gore.operator("daf.rebuild_all_generated_gore", text="Rebuild All Generated Gore")
        gore.operator("daf.validate_gore_geometry", text="Validate Gore Geometry")

    compound = _advanced_authoring_foldout(
        box, settings, "ui_advanced_compound_open", "Compound Participants & Cross-Seam Settings", 'LINKED'
    )
    if compound is not None:
        compound.prop(settings, "compound_event_id")
        compound.prop(settings, "compound_display_name")
        row = compound.row(align=True)
        row.operator("daf.new_compound_trauma_event", text="New Compound Trauma Event")
        row.operator("daf.add_active_region_to_compound_event", text="Add Active Region to Event")
        compound.operator("daf.remove_active_region_from_compound_event", text="Remove Region from Event")
        for event in registry.get("compoundEvents", []):
            select = compound.operator("daf.select_compound_trauma_event", text=event.get("displayName", event.get("eventId", "")))
            select.event_id = event.get("eventId", "")
        for prop in (
            "compound_trauma_family", "compound_semantic_direction", "compound_severity",
            "compound_impact_origin", "compound_impact_direction", "compound_impact_radius",
            "compound_impact_depth", "compound_impact_falloff", "compound_impact_strength",
            "compound_displacement_limit", "compound_event_seed", "compound_linked_seam_ids",
            "compound_continuity_mode", "compound_activation_weight",
        ):
            compound.prop(settings, prop)
        compound.operator("daf.capture_compound_impact_field", text="Capture Shared Impact Field")
        compound.operator("daf.rebuild_compound_trauma_event", text="Rebuild Compound Event")
        row = compound.row(align=True)
        zero = row.operator("daf.preview_compound_trauma_event", text="Event Zero")
        zero.weight = 0.0
        full = row.operator("daf.preview_compound_trauma_event", text="Preview Compound Event")
        full.weight = 1.0
        row.operator("daf.clear_compound_trauma_preview", text="Clear Event Preview")
        compound.operator("daf.validate_compound_trauma_event", text="Validate Compound Event")

    preview = _advanced_authoring_foldout(
        box, settings, "ui_advanced_preview_open", "Views, Preview, Sculpt, Sync & Validation", 'HIDE_OFF'
    )
    if preview is not None:
        row = preview.row(align=True)
        row.operator("daf.show_deformation_attached", text="Attached")
        row.operator("daf.show_deformation_detached", text="Detached")
        row.operator("daf.show_deformation_overlay", text="Both")
        row = preview.row(align=True)
        row.operator("daf.preview_active_trauma_stamp", text="Preview Active Stamp")
        clear = preview.column()
        clear.scale_y = 1.3
        clear.alert = True
        clear.operator("daf.clear_managed_preview", text="CLEAR DAMAGE PREVIEW", icon='X')
        preview.operator("daf.rebuild_active_deformation", text="REBUILD ACTIVE DEFORMATION")
        row = preview.row(align=True)
        row.operator("daf.begin_deformation_sculpt", text="Begin Sculpt")
        row.operator("daf.finish_deformation_sculpt", text="Finish Sculpt & Sync")
        preview.operator("daf.repair_legacy_pair_sync", text="REPAIR LEGACY PAIR SYNC")
        preview.operator("daf.validate_deformations", text="Validate Morph Targets")


def service_cache_counts():
    return {
        "geodesicDistances": len(_GEODESIC_CACHE),
        "geodesicContexts": len(_GEODESIC_CACHE_CONTEXT),
        "weightedAdjacency": len(_ADJACENCY_CACHE),
        "seamFactors": len(_SEAM_FACTOR_CACHE),
        "meshSnapshots": mesh_snapshot.cache_count(),
        "goreFaceRecords": gore_service.cache_count(),
        "validationSummaries": validation_service.cache_count(),
        "serializedPayloads": serialization.cache_count(),
    }


def _clear_service_caches(reason="explicit"):
    _GEODESIC_CACHE.clear()
    _GEODESIC_CACHE_CONTEXT.clear()
    _ADJACENCY_CACHE.clear()
    _SEAM_FACTOR_CACHE.clear()
    mesh_snapshot.clear_cache(reason)
    gore_service.clear_cache(reason)
    validation_service.clear_cache(reason)
    serialization.clear_cache()
    if reason == "file load":
        _refresh_authoring_ui_cache_safely()


def startup_self_check(context=None):
    context = context or bpy.context
    findings = []
    stale_preview_resources = 0
    for obj in bpy.data.objects:
        if bool(obj.get("dsb_gore_owned", False)) and bool(obj.get("dsb_preview_only", False)):
            stale_preview_resources += 1
        if obj.type != 'MESH':
            continue
        if _key(obj, PREVIEW_KEY_NAME) is not None:
            stale_preview_resources += 1
        if obj.data.color_attributes.get(GORE_PREVIEW_ATTRIBUTE) is not None:
            stale_preview_resources += 1
    if stale_preview_resources:
        findings.append(f"cleared {stale_preview_resources} stale preview resources")
        try:
            _clear_managed_preview(context)
        except Exception as exc:
            findings.append("preview cleanup failed: " + str(exc))
    try:
        registry = _load_registry()
        _cache_registry_summary(registry)
        active = _region_record(registry, registry.get("activeRegionId", ""))
        if active is not None:
            attached, detached = _resolve_region_pair(active)
            payload = _metadata(attached)
            _cache_metadata_summary(attached, detached, payload, active.get("regionId", ""))
    except Exception as exc:
        findings.append("state cache unavailable: " + str(exc))
    state = preview_service.state()
    duplicate_handlers = max(0, sum(
        1 for handler in bpy.app.handlers.load_post
        if getattr(handler, "__name__", "") == "_load_post"
        and getattr(handler, "__module__", "").endswith("deformation.preview_service")
    ) - 1)
    if duplicate_handlers:
        findings.append(f"detected {duplicate_handlers} duplicate Forge load handlers")
    result = {
        "status": "PASS" if not findings else "REPAIRED",
        "findings": findings,
        "timerRegistered": state["timerRegistered"],
        "cacheCounts": service_cache_counts(),
    }
    diagnostics.refresh_summary(_version_string(), DEFORMATION_BUILD_ID)
    return result


def _damage_preview_depsgraph_update(_scene, _depsgraph):
    try:
        state = _damage_preview_state(bpy.context)
        if state.get("entries"):
            active = _enforce_damage_preview_weights(bpy.context, state)
            if active:
                _sync_generated_gore_visibility(bpy.context, state)
            else:
                clear_damage_preview(bpy.context, update_status=False)
    except Exception:
        pass


def _install_damage_preview_handler():
    handlers = bpy.app.handlers.depsgraph_update_post
    for handler in tuple(handlers):
        if getattr(handler, "__name__", "") == _damage_preview_depsgraph_update.__name__:
            handlers.remove(handler)
    handlers.append(_damage_preview_depsgraph_update)


def _remove_damage_preview_handler():
    for handler in tuple(bpy.app.handlers.depsgraph_update_post):
        if getattr(handler, "__name__", "") == _damage_preview_depsgraph_update.__name__:
            bpy.app.handlers.depsgraph_update_post.remove(handler)


def initialize_runtime_services():
    preview_service.configure(
        executor=_execute_managed_preview,
        clearer=_clear_managed_preview,
        cache_clearer=_clear_service_caches,
    )
    diagnostics.configure(cache_provider=service_cache_counts, preview_provider=preview_service.state)
    preview_service.install_handlers()
    _install_damage_preview_handler()
    # Blender's extension installer enables packages while bpy.data is a
    # restricted proxy. Defer the datablock scan until normal startup/runtime.
    if not hasattr(bpy.data, "objects"):
        return {
            "status": "DEFERRED",
            "findings": ["startup self-check deferred until Blender runtime"],
            "timerRegistered": False,
            "cacheCounts": service_cache_counts(),
        }
    return startup_self_check()


def shutdown_runtime_services():
    try:
        preview_service.clear(bpy.context)
    except Exception:
        pass
    preview_service.shutdown()
    _remove_damage_preview_handler()
    _clear_service_caches("unregister")


CLASSES = (
    DAF_OT_register_deformation_region,
    DAF_OT_register_core_deformation_region,
    DAF_OT_select_deformation_region,
    DAF_OT_validate_deformation_region,
    DAF_OT_remove_deformation_region,
    DAF_OT_create_damage_shape_key,
    DAF_OT_create_standard_head_deformations,
    DAF_OT_create_blunt_gore_head_deformations,
    DAF_OT_create_body_impact_starters,
    DAF_OT_create_forearm_impact_starter,
    DAF_OT_select_deformation_key,
    DAF_OT_solo_deformation_key,
    DAF_OT_zero_deformations,
    DAF_OT_delete_managed_deformation,
    DAF_OT_capture_deformation_selected_face,
    DAF_OT_capture_deformation_selected_patch,
    DAF_OT_capture_deformation_selected_vertices,
    DAF_OT_capture_deformation_cursor,
    DAF_OT_save_trauma_stamp_library,
    DAF_OT_load_trauma_stamp_library,
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
    DAF_OT_randomize_gore_seed,
    DAF_OT_update_surface_gore_overlay,
    DAF_OT_preview_surface_gore_overlay,
    DAF_OT_clear_surface_gore_overlay_preview,
    DAF_OT_clear_current_generated_gore,
    DAF_OT_rebuild_all_generated_gore,
    DAF_OT_validate_gore_geometry,
    DAF_OT_new_compound_trauma_event,
    DAF_OT_select_compound_trauma_event,
    DAF_OT_add_active_region_to_compound_event,
    DAF_OT_remove_active_region_from_compound_event,
    DAF_OT_capture_compound_impact_field,
    DAF_OT_rebuild_compound_trauma_event,
    DAF_OT_preview_compound_trauma_event,
    DAF_OT_clear_compound_trauma_preview,
    DAF_OT_validate_compound_trauma_event,
    DAF_OT_preview_deformation_seed,
    DAF_OT_commit_deformation_seed,
    DAF_OT_clear_deformation_seed,
    DAF_OT_begin_deformation_sculpt,
    DAF_OT_finish_deformation_sculpt,
    DAF_OT_create_mirrored_deformation,
    DAF_OT_show_deformation_attached,
    DAF_OT_show_deformation_detached,
    DAF_OT_show_deformation_overlay,
    DAF_OT_repair_legacy_pair_sync,
    DAF_OT_validate_deformations,
)
