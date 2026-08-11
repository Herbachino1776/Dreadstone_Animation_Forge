"""Blender integration for first-class Progressive Damage Sites.

The existing Damage Key, Stamp, macro, gore, preview, validation, and export
services remain authoritative.  This layer stores site relationships and
coordinates those services without deriving any stage's artistic result.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math

import bpy
from mathutils import Vector

from . import trauma_field
from .deformation import preview_service, progressive_sites, transactions


PROGRESSIVE_SITE_SCHEMA = "dreadstone.progressive_damage_sites.v1"
_SETTINGS_SYNC_DEPTH = 0
_PREVIEW_SESSION = {}


def _deformation():
    from . import deformation_authoring

    return deformation_authoring


def _settings(context=None):
    context = context or bpy.context
    return getattr(getattr(context, "scene", None), "daf_settings", None)


def _collection(registry=None):
    deformation = _deformation()
    registry = registry if registry is not None else deformation._load_registry()
    normalized = progressive_sites.normalize_sites(
        registry.get("progressiveDamageSites")
    )
    from . import variant_authoring

    return variant_authoring.effective_progressive_collection(normalized)


def _store_collection(collection, registry=None):
    deformation = _deformation()
    registry = registry if registry is not None else deformation._load_registry()
    normalized = progressive_sites.normalize_sites(collection)
    full = progressive_sites.normalize_sites(
        registry.get("progressiveDamageSites")
    )
    from . import variant_authoring

    merged = variant_authoring.merge_progressive_collection(full, normalized)
    registry["progressiveDamageSites"] = progressive_sites.normalize_sites(merged)
    deformation._store_registry(registry)
    return variant_authoring.effective_progressive_collection(
        registry["progressiveDamageSites"]
    )


def _active_site(collection=None, context=None, required=True):
    normalized = _collection() if collection is None else progressive_sites.normalize_sites(collection)
    settings = _settings(context)
    requested = str(
        getattr(settings, "progression_active_site_guid", "")
        if settings is not None
        else ""
    )
    requested = requested or str(normalized.get("activeSiteGuid", ""))
    site = next(
        (
            value
            for value in normalized.get("sites", [])
            if value.get("siteGuid") == requested
        ),
        None,
    )
    if site is None and normalized.get("sites"):
        site = normalized["sites"][0]
    if site is None and required:
        raise RuntimeError("Create a Progressive Damage Site first.")
    return normalized, site


def _site_index(collection, site_guid):
    for index, site in enumerate(collection.get("sites", [])):
        if site.get("siteGuid") == str(site_guid):
            return index
    raise RuntimeError("The selected Progressive Damage Site no longer exists.")


def _unique_site_id(collection, requested):
    base = progressive_sites.safe_site_id(requested)
    existing = {site["siteId"] for site in collection.get("sites", [])}
    if base not in existing:
        return base
    for index in range(2, 10000):
        candidate = f"{base}_{index}"
        if candidate not in existing:
            return candidate
    raise RuntimeError("Could not allocate a unique Progressive Damage Site ID.")


def sync_settings_from_site(context=None, site=None):
    global _SETTINGS_SYNC_DEPTH
    context = context or bpy.context
    settings = _settings(context)
    if settings is None:
        return
    if site is None:
        _collection_value, site = _active_site(context=context, required=False)
    _SETTINGS_SYNC_DEPTH += 1
    try:
        with preview_service.suspend_updates():
            if site is None:
                settings.progression_active_site_guid = ""
                settings.progression_site_name = "Damage Site"
                settings.progression_site_region = ""
                settings.progression_structural_group = ""
                return
            settings.progression_active_site_guid = str(site["siteGuid"])
            settings.progression_site_name = str(site["displayName"])
            settings.progression_site_region = str(site["regionId"])
            settings.progression_structural_group = str(site["structuralGroup"])
            settings.progression_anchor_local = list(site["anchorLocal"])
            settings.progression_radius = float(site["radius"])
            settings.progression_preferred_direction = list(
                site["preferredDirectionLocal"]
            )
            settings.progression_light_anchor = float(
                site["severityAnchors"]["light"]
            )
            settings.progression_medium_anchor = float(
                site["severityAnchors"]["medium"]
            )
            settings.progression_heavy_anchor = float(
                site["severityAnchors"]["heavy"]
            )
            settings.progression_transition_mode = str(site["transitionMode"])
            settings.progression_transition_curve = str(site["transitionCurve"])
            settings.progression_gore_transition_mode = str(
                site["goreTransitionMode"]
            )
    finally:
        _SETTINGS_SYNC_DEPTH = max(0, _SETTINGS_SYNC_DEPTH - 1)


def update_active_site_from_settings(context=None):
    if _SETTINGS_SYNC_DEPTH:
        return None
    context = context or bpy.context
    settings = _settings(context)
    if settings is None:
        return None
    collection, site = _active_site(context=context, required=False)
    if site is None:
        return None
    candidate = copy.deepcopy(site)
    candidate.update(
        {
            "displayName": str(settings.progression_site_name).strip()
            or site["displayName"],
            "structuralGroup": str(
                settings.progression_structural_group
            ).strip()
            or site["structuralGroup"],
            "anchorLocal": list(settings.progression_anchor_local),
            "radius": float(settings.progression_radius),
            "preferredDirectionLocal": list(
                settings.progression_preferred_direction
            ),
            "severityAnchors": {
                "light": float(settings.progression_light_anchor),
                "medium": float(settings.progression_medium_anchor),
                "heavy": float(settings.progression_heavy_anchor),
            },
            "transitionMode": str(settings.progression_transition_mode),
            "transitionCurve": str(settings.progression_transition_curve),
            "goreTransitionMode": str(
                settings.progression_gore_transition_mode
            ),
            "validationStatus": "NOT_VALIDATED",
            "validationDigest": "",
            "enabledForExport": False,
        }
    )
    try:
        candidate = progressive_sites.normalize_site(candidate)
    except ValueError as exc:
        settings.progression_status = f"SITE SETTINGS INVALID — {exc}"
        return None
    collection["sites"][_site_index(collection, site["siteGuid"])] = candidate
    stored = _store_collection(collection)
    settings.progression_status = "SITE SETTINGS SAVED — VALIDATE AGAIN"
    return progressive_sites.site_by_guid(stored, candidate["siteGuid"])


def create_site(context=None):
    context = context or bpy.context
    deformation = _deformation()
    registry, region, _target, _detached = deformation._resolve_active_region(
        context
    )
    collection = _collection(registry)
    settings = _settings(context)
    display_name = (
        str(getattr(settings, "progression_site_name", "")).strip()
        or str(region.get("regionId", "damage")).replace("_", " ").title()
        + " Damage Site"
    )
    site_id = _unique_site_id(collection, display_name)
    site = progressive_sites.new_site(
        display_name,
        str(region.get("regionId", "")),
        str(getattr(settings, "progression_structural_group", "")).strip()
        or str(region.get("regionId", "")),
        site_id=site_id,
    )
    collection["sites"].append(site)
    collection["activeSiteGuid"] = site["siteGuid"]
    stored = _store_collection(collection, registry)
    site = progressive_sites.site_by_guid(stored, site["siteGuid"])
    sync_settings_from_site(context, site)
    settings.progression_active_stage = "LIGHT"
    settings.ui_progressive_sites_open = True
    settings.progression_status = f"SITE CREATED — {site['displayName']}"
    return site


def select_site(context, site_guid):
    collection = _collection()
    site = progressive_sites.site_by_guid(collection, site_guid)
    collection["activeSiteGuid"] = site["siteGuid"]
    stored = _store_collection(collection)
    site = progressive_sites.site_by_guid(stored, site["siteGuid"])
    sync_settings_from_site(context, site)
    _settings(context).progression_status = (
        f"SITE SELECTED — {site['displayName']}"
    )
    return site


def rename_site(context=None):
    context = context or bpy.context
    result = update_active_site_from_settings(context)
    if result is None:
        raise RuntimeError(
            str(_settings(context).progression_status)
            or "Enter a valid site name."
        )
    return result


def duplicate_site_metadata(context=None):
    context = context or bpy.context
    collection, source = _active_site(context=context)
    duplicate = progressive_sites.new_site(
        f"{source['displayName']} Copy",
        source["regionId"],
        source["structuralGroup"],
        site_id=_unique_site_id(
            collection,
            f"{source['siteId']}_copy",
        ),
    )
    for field in (
        "anchorLocal",
        "radius",
        "preferredDirectionLocal",
        "severityAnchors",
        "transitionMode",
        "transitionCurve",
        "goreTransitionMode",
    ):
        duplicate[field] = copy.deepcopy(source[field])
    duplicate = progressive_sites.normalize_site(duplicate)
    collection["sites"].append(duplicate)
    collection["activeSiteGuid"] = duplicate["siteGuid"]
    stored = _store_collection(collection)
    duplicate = progressive_sites.site_by_guid(
        stored,
        duplicate["siteGuid"],
    )
    sync_settings_from_site(context, duplicate)
    _settings(context).progression_status = (
        "SITE METADATA DUPLICATED — STAGES ARE UNASSIGNED"
    )
    return duplicate


def delete_site_metadata(context=None):
    context = context or bpy.context
    clear_progression_preview(context)
    collection, site = _active_site(context=context)
    collection["sites"] = [
        value
        for value in collection["sites"]
        if value["siteGuid"] != site["siteGuid"]
    ]
    collection["activeSiteGuid"] = (
        collection["sites"][0]["siteGuid"] if collection["sites"] else ""
    )
    stored = _store_collection(collection)
    sync_settings_from_site(context)
    _settings(context).progression_status = (
        f"SITE METADATA DELETED — KEYS PRESERVED — {site['displayName']}"
    )
    return {
        "deletedSiteGuid": site["siteGuid"],
        "preservedDamageKeyIds": [
            stage["damageKeyId"]
            for stage in site["stages"].values()
            if stage["damageKeyId"]
        ],
        "remainingSiteCount": stored["siteCount"],
    }


def _capture_digest(stamp):
    capture = (
        stamp.get("capture", {})
        if isinstance(stamp, dict)
        else {}
    )
    return progressive_sites.canonical_digest(capture)


def _deformation_digest(target, key_name):
    key = _deformation()._key(target, key_name)
    if key is None:
        return ""
    digest = hashlib.sha256()
    digest.update(str(len(key.data)).encode("ascii"))
    for point in key.data:
        for value in point.co:
            digest.update(float(value).hex().encode("ascii"))
            digest.update(b"|")
    return digest.hexdigest()


def _generated_mapping(region_id, key_name):
    deformation = _deformation()
    component_ids = {}
    node_names = {}
    role_triangles = {}
    total_triangles = 0
    ownership = set()
    for obj in deformation.generated_gore_objects(region_id, key_name):
        role = str(obj.get("dsb_gore_pair_role", "")).upper()
        component = str(obj.get("dsb_gore_component", "")).upper() or "SINGLE"
        map_key = f"{role}:{component}"
        component_ids[map_key] = str(obj.get("dsb_gore_mesh_id", ""))
        node_names[map_key] = obj.name
        triangles = int(obj.get("dsb_gore_triangle_count", 0))
        total_triangles += triangles
        role_triangles[role] = role_triangles.get(role, 0) + triangles
        if role:
            ownership.add(role)
    return {
        "generatedComponentIds": component_ids,
        "generatedNodeNames": node_names,
        "ownershipRoles": sorted(ownership),
        "triangleCount": total_triangles,
        "visibleTriangleCount": max(role_triangles.values(), default=0),
    }


def _ensure_damage_key_id(
    attached,
    detached,
    payload,
    key_name,
):
    deformation = _deformation()
    entry = payload.get("keys", {}).get(key_name)
    if not isinstance(entry, dict):
        raise RuntimeError(f"Damage Key {key_name!r} is not registered.")
    key_id = str(entry.get("damageKeyId", "")).strip()
    if not key_id:
        seed = progressive_sites.canonical_digest(
            [
                str(payload.get("regionId", "")),
                str(attached.name),
                str(key_name),
            ]
        )[:32]
        key_id = progressive_sites.opaque_id("damage_key", seed)
        entry["damageKeyId"] = key_id
        deformation._store_metadata(attached, detached, payload)
    return key_id


def _stage_record(context, stage_name, *, validation_status=None):
    deformation = _deformation()
    settings = _settings(context)
    _registry, region, attached, detached = deformation._resolve_active_region(
        context
    )
    key_name = str(settings.deformation_active_key)
    if not key_name:
        raise RuntimeError("Select a Damage Key first.")
    payload = deformation._metadata(attached)
    entry = payload.get("keys", {}).get(key_name)
    if not isinstance(entry, dict):
        raise RuntimeError("The active Damage Key is not registered.")
    key_id = _ensure_damage_key_id(
        attached,
        detached,
        payload,
        key_name,
    )
    stamps = list(entry.get("stamps", []))
    active_stamp = deformation._entry_active_stamp(
        entry,
        str(settings.deformation_active_stamp_id),
    )
    recipe_digest = (
        trauma_field.recipe_digest(stamps) if stamps else ""
    )
    current_saved = (
        str(entry.get("draftStatus", "")) == "COMMITTED"
        and not bool(settings.deformation_impact_dirty)
        and (
            not bool(settings.deformation_gore_enabled)
            or not bool(settings.deformation_gore_dirty)
        )
    )
    mapping = _generated_mapping(str(region.get("regionId", "")), key_name)
    return progressive_sites.normalize_stage(
        {
            "stage": stage_name,
            "stageId": progressive_sites.opaque_id("stage"),
            "damageKeyId": key_id,
            "deformationKeyName": key_name,
            "activeStampId": (
                str(active_stamp.get("stampId", ""))
                if active_stamp is not None
                else ""
            ),
            "regionId": str(region.get("regionId", "")),
            "regionMode": deformation._region_mode(region),
            "targetObject": attached.name,
            "attachedObject": attached.name,
            "detachedObject": detached.name if detached is not None else "",
            "recipeDigest": recipe_digest,
            "deformationDigest": _deformation_digest(attached, key_name),
            "captureDigest": _capture_digest(active_stamp),
            **mapping,
            "saved": current_saved,
            "dirty": not current_saved,
            "validationStatus": (
                validation_status
                if validation_status is not None
                else "NOT_VALIDATED"
            ),
        },
        stage_name,
    )


def assign_active_key_to_stage(context=None, stage=None):
    context = context or bpy.context
    settings = _settings(context)
    collection, site = _active_site(context=context)
    stage_name = str(stage or settings.progression_active_stage).upper()
    assignment = _stage_record(context, stage_name)
    collection = progressive_sites.assign_stage(
        collection,
        site["siteGuid"],
        stage_name,
        assignment,
    )
    stored = _store_collection(collection)
    updated = progressive_sites.site_by_guid(stored, site["siteGuid"])
    settings.progression_active_stage = stage_name
    settings.progression_status = (
        f"{stage_name} ASSIGNED — {assignment['deformationKeyName']}"
    )
    sync_settings_from_site(context, updated)
    return updated["stages"][stage_name]


def unassign_stage(context=None, stage=None):
    context = context or bpy.context
    settings = _settings(context)
    collection, site = _active_site(context=context)
    stage_name = str(stage or settings.progression_active_stage).upper()
    collection = progressive_sites.unassign_stage(
        collection,
        site["siteGuid"],
        stage_name,
    )
    stored = _store_collection(collection)
    settings.progression_active_stage = stage_name
    settings.progression_status = (
        f"{stage_name} UNASSIGNED — DAMAGE KEY PRESERVED"
    )
    return progressive_sites.site_by_guid(stored, site["siteGuid"])[
        "stages"
    ][stage_name]


def focus_stage(context=None, stage=None):
    context = context or bpy.context
    clear_progression_preview(context)
    settings = _settings(context)
    collection, site = _active_site(context=context)
    stage_name = str(stage or settings.progression_active_stage).upper()
    stage_record = site["stages"][stage_name]
    settings.progression_active_stage = stage_name
    if not stage_record["damageKeyId"]:
        settings.progression_status = f"{stage_name} — UNASSIGNED"
        return stage_record
    deformation = _deformation()
    deformation._set_active_region(stage_record["regionId"], context)
    deformation._select_key(
        settings,
        stage_record["deformationKeyName"],
    )
    if stage_record["activeStampId"]:
        deformation.select_damage_key_stamp(
            context,
            stage_record["deformationKeyName"],
            stage_record["activeStampId"],
        )
    else:
        deformation.apply_damage_key_previews(context)
    settings.progression_status = (
        f"WORKING ON {stage_name} — "
        f"{stage_record['deformationKeyName']}"
    )
    return stage_record


def create_key_for_stage(context=None, stage=None):
    context = context or bpy.context
    deformation = _deformation()
    settings = _settings(context)
    _registry, _region, attached, detached = (
        deformation._resolve_active_region(context)
    )
    with transactions.OperationTransaction(
        context,
        "Create Progressive Stage Key",
        objects=tuple(
            value for value in (attached, detached) if value is not None
        ),
        metadata_keys=(
            deformation.METADATA_PROPERTY,
            deformation.REGISTRY_PROPERTY,
            deformation.DAMAGE_PREVIEW_STATE_PROPERTY,
            deformation.GORE_PREVIEW_STATE_PROPERTY,
        ),
        property_groups=(
            (settings, "deformation_"),
            (settings, "progression_"),
        ),
        ownership_predicate=lambda value: bool(
            value.get("dsb_generated_role", "")
            or value.get("dsb_damage_generated", False)
        ),
    ) as transaction:
        transaction.set_stage("create independent Damage Key")
        result = deformation.create_impact_from_current_selection(context)
        transaction.set_stage("assign new key to progression stage")
        assigned = assign_active_key_to_stage(context, stage)
        transaction.commit()
    return {"created": result, "stage": assigned}


def duplicate_active_key_for_stage(context=None, stage=None):
    context = context or bpy.context
    deformation = _deformation()
    settings = _settings(context)
    _registry, _region, attached, detached = (
        deformation._resolve_active_region(context)
    )
    with transactions.OperationTransaction(
        context,
        "Duplicate Progressive Stage Key",
        objects=tuple(
            value for value in (attached, detached) if value is not None
        ),
        metadata_keys=(
            deformation.METADATA_PROPERTY,
            deformation.REGISTRY_PROPERTY,
            deformation.DAMAGE_PREVIEW_STATE_PROPERTY,
            deformation.GORE_PREVIEW_STATE_PROPERTY,
        ),
        property_groups=(
            (settings, "deformation_"),
            (settings, "progression_"),
        ),
        ownership_predicate=lambda value: bool(
            value.get("dsb_generated_role", "")
            or value.get("dsb_damage_generated", False)
        ),
    ) as transaction:
        transaction.set_stage("duplicate independent key and recipe")
        result = _duplicate_active_key_for_stage(context, stage)
        transaction.commit()
    return result


def _duplicate_active_key_for_stage(context=None, stage=None):
    context = context or bpy.context
    deformation = _deformation()
    settings = _settings(context)
    (
        _settings_value,
        _registry,
        region,
        attached,
        detached,
        payload,
        source_name,
        source_entry,
    ) = deformation._active_key_context(context)
    source_key = deformation._key(attached, source_name)
    if source_key is None:
        raise RuntimeError("Select a complete Damage Key to duplicate.")
    requested = str(source_name)[:44] + "_Copy"
    settings.deformation_impact_semantic_name = requested
    new_name = deformation._unique_impact_name(
        attached,
        payload.get("keys", {}),
        settings,
        str(region.get("regionId", "")),
    )
    duplicate_entry = copy.deepcopy(source_entry)
    duplicate_entry["name"] = new_name
    duplicate_entry["damageKeyId"] = progressive_sites.opaque_id("damage_key")
    stamp_id_map = {}
    for stamp in duplicate_entry.get("stamps", []):
        prior = str(stamp.get("stampId", ""))
        replacement = progressive_sites.opaque_id("stamp")
        stamp_id_map[prior] = replacement
        stamp["stampId"] = replacement
        stamp["displayName"] = str(stamp.get("displayName", prior)) + " Copy"
    duplicate_entry["activeStampId"] = stamp_id_map.get(
        str(source_entry.get("activeStampId", "")),
        "",
    )
    if isinstance(duplicate_entry.get("surfaceGoreOverlay"), dict):
        overlay = duplicate_entry["surfaceGoreOverlay"]
        overlay["linkedStampId"] = stamp_id_map.get(
            str(overlay.get("linkedStampId", "")),
            duplicate_entry["activeStampId"],
        )
        duplicate_entry["goreOverlayDigest"] = trauma_field.gore_overlay_digest(
            overlay
        )
    for field in (
        "goreGeneratedMeshIds",
        "goreGeneratedNodeNames",
        "goreGeometryDigests",
        "goreGenerationDigests",
        "goreTriangleCounts",
        "goreMaterialIds",
        "goreMaterialNames",
        "goreValidationMeasurements",
        "validationStatus",
    ):
        duplicate_entry.pop(field, None)
    duplicate_entry["draftStatus"] = "UNCOMMITTED"
    duplicate_entry["status"] = "DUPLICATED_INDEPENDENT_DRAFT"
    duplicate_entry["previewEnabled"] = True
    attached, detached, target, paired = deformation._ensure_key_pair(
        new_name,
        duplicate_entry,
    )
    deformation._set_key_coordinates(
        target,
        [point.co.copy() for point in source_key.data],
    )
    if paired is not None:
        deformation.sync_key_to_detached(
            new_name,
            str(region.get("regionId", "")),
        )
    payload = deformation._metadata(attached)
    payload["keys"][new_name] = duplicate_entry
    deformation._store_metadata(attached, detached, payload)
    deformation._select_key(settings, new_name)
    assigned = assign_active_key_to_stage(context, stage)
    settings.progression_status = (
        f"INDEPENDENT KEY CREATED — {new_name}"
    )
    return {"key": new_name, "stage": assigned}


def set_site_anchor_from_active_stage(context=None):
    context = context or bpy.context
    deformation = _deformation()
    settings = _settings(context)
    collection, site = _active_site(context=context)
    stage = site["stages"][str(settings.progression_active_stage)]
    if not stage["damageKeyId"]:
        raise RuntimeError("Assign the active stage before setting its anchor.")
    deformation._set_active_region(stage["regionId"], context)
    _registry, _region, attached, _detached = deformation._resolve_active_region(
        context
    )
    entry = deformation._metadata(attached).get("keys", {}).get(
        stage["deformationKeyName"],
        {},
    )
    stamp = deformation._entry_active_stamp(entry, stage["activeStampId"])
    if stamp is None:
        raise RuntimeError("The active stage has no captured Stamp.")
    capture = stamp.get("capture", {})
    center = capture.get("centerLocal", stamp.get("center"))
    if not center:
        raise RuntimeError("The active stage has no captured local impact center.")
    candidate = copy.deepcopy(site)
    candidate["anchorLocal"] = list(center)
    candidate["radius"] = max(
        1e-6,
        float(capture.get("estimatedRadius", stamp.get("radius", site["radius"]))),
    )
    direction = stamp.get("directionLocal", stamp.get("direction"))
    if direction:
        candidate["preferredDirectionLocal"] = list(direction)
    candidate["validationStatus"] = "NOT_VALIDATED"
    candidate["enabledForExport"] = False
    candidate = progressive_sites.normalize_site(candidate)
    collection["sites"][_site_index(collection, site["siteGuid"])] = candidate
    stored = _store_collection(collection)
    updated = progressive_sites.site_by_guid(stored, site["siteGuid"])
    sync_settings_from_site(context, updated)
    settings.progression_status = "SITE ANCHOR SET FROM ACTIVE STAGE"
    return updated


def _find_assigned_stage(collection, region_id, key_name, key_id=""):
    for site in collection.get("sites", []):
        for stage_name, stage in site["stages"].items():
            if key_id and stage["damageKeyId"] == key_id:
                return site, stage_name
            if (
                stage["regionId"] == str(region_id)
                and stage["deformationKeyName"] == str(key_name)
            ):
                return site, stage_name
    return None, ""


def mark_active_stage_dirty(context=None):
    context = context or bpy.context
    deformation = _deformation()
    settings = _settings(context)
    collection = _collection()
    region_id = deformation._active_region_id(context)
    site, stage_name = _find_assigned_stage(
        collection,
        region_id,
        settings.deformation_active_key,
    )
    if site is None:
        return None
    stage = site["stages"][stage_name]
    stage["saved"] = False
    stage["dirty"] = True
    stage["validationStatus"] = "NOT_VALIDATED"
    site["validationStatus"] = "NOT_VALIDATED"
    site["validationDigest"] = ""
    site["enabledForExport"] = False
    stored = _store_collection(collection)
    settings.progression_status = (
        f"{stage_name} CHANGED — SAVE THIS DAMAGE KEY"
    )
    return progressive_sites.site_by_guid(stored, site["siteGuid"])


def sync_active_stage_after_save(context=None):
    context = context or bpy.context
    deformation = _deformation()
    settings = _settings(context)
    collection = _collection()
    region_id = deformation._active_region_id(context)
    site, stage_name = _find_assigned_stage(
        collection,
        region_id,
        settings.deformation_active_key,
    )
    if site is None:
        return None
    refreshed = _stage_record(context, stage_name)
    refreshed["stageId"] = site["stages"][stage_name]["stageId"]
    refreshed["saved"] = True
    refreshed["dirty"] = False
    refreshed["validationStatus"] = "NOT_VALIDATED"
    site["stages"][stage_name] = progressive_sites.normalize_stage(
        refreshed,
        stage_name,
    )
    site["validationStatus"] = "NOT_VALIDATED"
    site["validationDigest"] = ""
    site["enabledForExport"] = False
    stored = _store_collection(collection)
    settings.progression_status = (
        f"{stage_name} SAVED — VALIDATE PROGRESSION"
    )
    return progressive_sites.site_by_guid(stored, site["siteGuid"])


def request_progression_preview(context=None, reason="progression severity"):
    context = context or bpy.context
    settings = _settings(context)
    if settings is None or _SETTINGS_SYNC_DEPTH:
        return 0
    if not bool(settings.progression_live_preview):
        settings.progression_preview_requested = False
        settings.progression_status = "PROGRESSION PREVIEW DIRTY — REFRESH"
        return 0
    settings.progression_preview_requested = True
    return preview_service.request_refresh(context, reason)


def _preview_mode_for_site(site):
    deformation = _deformation()
    registry = deformation._load_registry()
    region = deformation._region_record(registry, site["regionId"])
    return "CORE" if region and deformation._region_mode(region) == deformation.CORE_SINGLE else "ATTACHED"


def execute_progression_preview(context, _quality="FAST", _generation=0):
    global _PREVIEW_SESSION
    deformation = _deformation()
    settings = _settings(context)
    collection, site = _active_site(context=context)
    missing = [
        name
        for name, stage in site["stages"].items()
        if not stage["damageKeyId"]
    ]
    if missing:
        raise RuntimeError(
            "Assign all three stages before progression preview: "
            + ", ".join(missing)
        )
    if not _PREVIEW_SESSION:
        _PREVIEW_SESSION = {
            "siteGuid": site["siteGuid"],
            "snapshot": deformation.capture_damage_preview_snapshot(context),
        }
    elif _PREVIEW_SESSION.get("siteGuid") != site["siteGuid"]:
        clear_progression_preview(context)
        _PREVIEW_SESSION = {
            "siteGuid": site["siteGuid"],
            "snapshot": deformation.capture_damage_preview_snapshot(context),
        }
    severity = float(settings.progression_severity) / 100.0
    evaluation = progressive_sites.evaluate_weights(
        severity,
        site["severityAnchors"],
        site["transitionCurve"],
    )
    gore_stage = progressive_sites.detailed_gore_stage(
        severity,
        site["severityAnchors"],
        site["transitionCurve"],
    )
    deformation.clear_surface_gore_preview(all_regions=True)
    assigned_key_names = {
        stage["deformationKeyName"] for stage in site["stages"].values()
    }
    if bool(settings.progression_preview_with_other_damage):
        snapshot = _PREVIEW_SESSION.get("snapshot", {})
        for object_name, values in snapshot.get("shapeValues", {}).items():
            obj = bpy.data.objects.get(object_name)
            if obj is None or obj.data.shape_keys is None:
                continue
            for key_name, value in values.items():
                key = deformation._key(obj, key_name)
                if key is not None:
                    key.value = (
                        0.0 if key_name in assigned_key_names else float(value)
                    )
        entries = [
            copy.deepcopy(entry)
            for entry in snapshot.get("damagePreviewState", {}).get(
                "entries",
                [],
            )
            if str(entry.get("keyName", "")) not in assigned_key_names
        ]
    else:
        deformation._zero_all_damage_preview_weights(include_preview=True)
        entries = []
    mode = _preview_mode_for_site(site)
    for stage_name, weight in evaluation["weights"].items():
        stage = site["stages"][stage_name]
        if weight <= 1e-12:
            continue
        registry = deformation._load_registry()
        region = deformation._region_record(registry, stage["regionId"])
        if region is None:
            raise RuntimeError(
                f"{stage_name} references missing region {stage['regionId']!r}."
            )
        attached, detached = deformation._resolve_region_pair(region)
        key = deformation._key(attached, stage["deformationKeyName"])
        if key is None:
            raise RuntimeError(
                f"{stage_name} Damage Key {stage['deformationKeyName']!r} is missing."
            )
        key.value = float(weight)
        if detached is not None:
            paired = deformation._key(detached, stage["deformationKeyName"])
            if paired is not None:
                paired.value = float(weight)
        entries.append(
            deformation._preview_entry(
                stage["regionId"],
                stage["deformationKeyName"],
                weight,
                mode,
            )
        )
    gore_key_name = (
        site["stages"][gore_stage]["deformationKeyName"]
        if gore_stage is not None
        else ""
    )
    state = {
        "kind": "PROGRESSIVE_SITE",
        "siteGuid": site["siteGuid"],
        "severity": severity,
        "weights": dict(evaluation["weights"]),
        "goreStage": gore_stage or "NONE",
        "goreKeyName": gore_key_name,
        "progressionStageKeyNames": sorted(assigned_key_names),
        "entries": entries,
    }
    deformation._store_damage_preview_state(context, state)
    deformation._enforce_damage_preview_weights(context, state)
    deformation._sync_generated_gore_visibility(context, state)
    if gore_stage is not None:
        stage = site["stages"][gore_stage]
        deformation._install_existing_surface_stain_preview(
            context,
            stage["regionId"],
            stage["deformationKeyName"],
        )
    settings.progression_weight_basis = max(
        0.0,
        1.0 - sum(evaluation["weights"].values()),
    )
    settings.progression_weight_light = evaluation["weights"]["LIGHT"]
    settings.progression_weight_medium = evaluation["weights"]["MEDIUM"]
    settings.progression_weight_heavy = evaluation["weights"]["HEAVY"]
    settings.progression_detailed_gore_stage = gore_stage or "NONE"
    settings.progression_transition_status = (
        f"{evaluation['segment'].replace('_', ' ')} — "
        f"{evaluation['segmentT'] * 100.0:.1f}%"
    )
    settings.progression_preview_active = True
    settings.progression_status = (
        f"PROGRESSION PREVIEW — {settings.progression_severity:.1f}%"
    )
    return {
        "siteGuid": site["siteGuid"],
        "severity": severity,
        "weights": dict(evaluation["weights"]),
        "activeMorphCount": evaluation["activeMorphCount"],
        "totalStructuralWeight": evaluation["totalWeight"],
        "detailedGoreStage": gore_stage or "NONE",
        "message": settings.progression_status,
    }


def refresh_progression_preview(context=None):
    context = context or bpy.context
    settings = _settings(context)
    settings.progression_preview_requested = True
    result = preview_service.run_now(
        context,
        quality=str(settings.deformation_preview_quality),
    )
    if result.get("failed"):
        raise RuntimeError(result.get("error", "Progression preview failed."))
    return result


def clear_progression_preview(context=None):
    global _PREVIEW_SESSION
    context = context or bpy.context
    settings = _settings(context)
    preview_service.cancel_timer()
    snapshot = _PREVIEW_SESSION.get("snapshot")
    _PREVIEW_SESSION = {}
    if snapshot:
        _deformation().restore_damage_preview_snapshot(context, snapshot)
    elif settings is not None and bool(settings.progression_preview_active):
        _deformation().clear_damage_preview(context, update_status=False)
    if settings is not None:
        settings.progression_preview_requested = False
        settings.progression_preview_active = False
        settings.progression_weight_basis = 1.0
        settings.progression_weight_light = 0.0
        settings.progression_weight_medium = 0.0
        settings.progression_weight_heavy = 0.0
        settings.progression_detailed_gore_stage = "NONE"
        settings.progression_transition_status = "BASIS"
        settings.progression_status = "PROGRESSION PREVIEW CLEARED"
    return {"restored": bool(snapshot)}


def preview_session_active():
    return bool(_PREVIEW_SESSION)


def _set_site_weights(site, weights):
    deformation = _deformation()
    registry = deformation._load_registry()
    for stage_name, stage in site["stages"].items():
        region = deformation._region_record(registry, stage["regionId"])
        if region is None:
            continue
        attached, detached = deformation._resolve_region_pair(region)
        value = float(weights.get(stage_name, 0.0))
        key = deformation._key(attached, stage["deformationKeyName"])
        if key is not None:
            key.value = value
        if detached is not None:
            paired = deformation._key(detached, stage["deformationKeyName"])
            if paired is not None:
                paired.value = value
    bpy.context.view_layer.update()


def _evaluated_world_points(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        matrix = evaluated.matrix_world
        return [matrix @ vertex.co for vertex in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()


def _bounds(points):
    if not points:
        return (Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0)))
    lower = Vector(
        tuple(min(point[axis] for point in points) for axis in range(3))
    )
    upper = Vector(
        tuple(max(point[axis] for point in points) for axis in range(3))
    )
    return lower, upper


def _pose_candidates(target):
    armature = next(
        (
            modifier.object
            for modifier in target.modifiers
            if modifier.type == "ARMATURE" and modifier.object is not None
        ),
        None,
    )
    candidates = [("REST_OR_CURRENT", None, int(bpy.context.scene.frame_current))]
    if armature is None:
        return armature, candidates
    tokens = (
        ("WALK", ("walk",)),
        ("HURT", ("hurt", "pain", "hit")),
        ("COLLAPSE_DEATH", ("collapse", "death", "die")),
    )
    for label, names in tokens:
        action = next(
            (
                value
                for value in bpy.data.actions
                if any(token in value.name.lower() for token in names)
            ),
            None,
        )
        if action is not None:
            start, end = action.frame_range
            candidates.append(
                (label, action, int(round((float(start) + float(end)) * 0.5)))
            )
    return armature, candidates


def _validate_stage_preflight(site, base_validation):
    deformation = _deformation()
    registry = deformation._load_registry()
    validation_by_key = {
        (str(record.get("regionId", "")), str(record.get("name", ""))): record
        for record in base_validation.get("keys", [])
    }
    errors = []
    warnings = []
    records = {}
    for stage_name, stage in site["stages"].items():
        stage_errors = []
        region = deformation._region_record(registry, stage["regionId"])
        if region is None:
            stage_errors.append("registered region is missing")
            records[stage_name] = {
                "status": "FAIL",
                "errors": stage_errors,
            }
            errors.extend(f"{stage_name}: {value}" for value in stage_errors)
            continue
        attached, detached = deformation._resolve_region_pair(region)
        payload = deformation._metadata(attached)
        entry = payload.get("keys", {}).get(stage["deformationKeyName"])
        key = deformation._key(attached, stage["deformationKeyName"])
        paired = (
            deformation._key(detached, stage["deformationKeyName"])
            if detached is not None
            else None
        )
        if not isinstance(entry, dict):
            stage_errors.append("Damage Key metadata is missing")
        if key is None:
            stage_errors.append("target shape key is missing")
        elif key.relative_key != attached.data.shape_keys.reference_key:
            stage_errors.append("shape key is not relative to Basis")
        if detached is not None:
            if paired is None:
                stage_errors.append("detached shape key is missing")
            elif paired.relative_key != detached.data.shape_keys.reference_key:
                stage_errors.append("detached shape key is not relative to Basis")
        active_stamp = None
        if isinstance(entry, dict):
            if str(entry.get("damageKeyId", "")) != stage["damageKeyId"]:
                stage_errors.append("stable Damage Key ID is stale")
            current_recipe = (
                trauma_field.recipe_digest(entry.get("stamps", []))
                if entry.get("stamps")
                else ""
            )
            current_deformation = _deformation_digest(
                attached,
                stage["deformationKeyName"],
            )
            active_stamp = deformation._entry_active_stamp(
                entry,
                stage["activeStampId"],
            )
            current_capture = _capture_digest(active_stamp)
            if current_recipe != stage["recipeDigest"]:
                stage_errors.append("recipe digest is stale")
            if current_deformation != stage["deformationDigest"]:
                stage_errors.append(
                    "deformation digest is stale "
                    f"({stage['deformationDigest'][:10]} != "
                    f"{current_deformation[:10]})"
                )
            if current_capture != stage["captureDigest"]:
                stage_errors.append("capture digest is stale")
            if str(entry.get("draftStatus", "")) != "COMMITTED":
                stage_errors.append("Damage Key has not been saved")
        capture = (
            active_stamp.get("capture", {})
            if isinstance(active_stamp, dict)
            else {}
        )
        center_local = capture.get("centerLocal")
        anchor_distance = 0.0
        if (
            isinstance(center_local, (list, tuple))
            and len(center_local) == 3
        ):
            anchor_distance = (
                Vector(center_local) - Vector(site["anchorLocal"])
            ).length
            unusual_distance = max(float(site["radius"]) * 2.0, 0.05)
            if anchor_distance > unusual_distance:
                warnings.append(
                    f"{stage_name}: captured center is "
                    f"{anchor_distance:.4f} local units from the site anchor "
                    f"(informational threshold {unusual_distance:.4f})."
                )
        key_validation = validation_by_key.get(
            (stage["regionId"], stage["deformationKeyName"]),
            {},
        )
        if key_validation.get("exportValidationStatus") != "PASS":
            stage_errors.append(
                "current deformation/gore export validation did not pass"
            )
        mapping = _generated_mapping(
            stage["regionId"],
            stage["deformationKeyName"],
        )
        raw_overlay = entry.get("surfaceGoreOverlay", {}) if isinstance(entry, dict) else {}
        if (
            isinstance(raw_overlay, dict)
            and raw_overlay.get("goreOverlayEnabled", False)
            and str(raw_overlay.get("goreGeometryMode", "STAIN_ONLY"))
            != "STAIN_ONLY"
            and not mapping["generatedNodeNames"]
        ):
            stage_errors.append("required generated gore components are missing")
        expected_roles = (
            {"CORE"}
            if deformation._region_mode(region) == deformation.CORE_SINGLE
            else {"ATTACHED", "DETACHED"}
        )
        if mapping["generatedNodeNames"] and not expected_roles.issubset(
            set(mapping["ownershipRoles"])
        ):
            stage_errors.append("generated gore ownership roles are incomplete")
        records[stage_name] = {
            "status": "FAIL" if stage_errors else "PASS",
            "errors": stage_errors,
            "measuredMaximumDisplacement": float(
                key_validation.get("measuredMaximumDisplacement", 0.0)
            ),
            "captureCenterLocal": list(center_local or []),
            "siteAnchorDistance": float(anchor_distance),
            **mapping,
        }
        errors.extend(f"{stage_name}: {value}" for value in stage_errors)
    return records, errors, warnings


def validate_site(context=None, site_guid=None):
    context = context or bpy.context
    deformation = _deformation()
    settings = _settings(context)
    collection = _collection()
    site = progressive_sites.site_by_guid(
        collection,
        site_guid
        or settings.progression_active_site_guid
        or collection.get("activeSiteGuid", ""),
    )
    missing = [
        name for name, stage in site["stages"].items() if not stage["damageKeyId"]
    ]
    if missing:
        report = {
            "schema": progressive_sites.SITE_SCHEMA,
            "siteGuid": site["siteGuid"],
            "status": "FAIL",
            "errors": ["Missing stages: " + ", ".join(missing)],
            "warnings": [],
            "transitionSamples": [],
            "animationPoseResults": [],
        }
        return _store_validation_report(context, collection, site, report, {})

    snapshot = deformation.capture_damage_preview_snapshot(context)
    errors = []
    warnings = []
    sample_records = []
    pose_records = []
    stage_records = {}
    try:
        deformation.clear_damage_preview(context, update_status=False)
        base_validation = deformation.validate_deformations(require_keys=False)
        (
            stage_records,
            preflight_errors,
            preflight_warnings,
        ) = _validate_stage_preflight(
            site,
            base_validation,
        )
        errors.extend(preflight_errors)
        warnings.extend(preflight_warnings)
        registry = deformation._load_registry()
        region = deformation._region_record(registry, site["regionId"])
        if region is None:
            errors.append(f"Site region {site['regionId']!r} is missing.")
            raise RuntimeError(errors[-1])
        target, detached = deformation._resolve_region_pair(region)
        armature, poses = _pose_candidates(target)
        expected_pose_labels = {"REST_OR_CURRENT", "WALK", "HURT", "COLLAPSE_DEATH"}
        actual_pose_labels = {value[0] for value in poses}
        for missing_pose in sorted(expected_pose_labels - actual_pose_labels):
            warnings.append(
                f"Animation pose {missing_pose} was unavailable in this Blend file."
            )
        target.hide_viewport = False
        target.hide_set(False)
        if detached is not None:
            detached.hide_viewport = False
            detached.hide_set(False)
        depsgraph = context.evaluated_depsgraph_get()
        maximum_allowed = max(
            float(
                deformation._metadata(target)["keys"][
                    site["stages"][stage]["deformationKeyName"]
                ].get("maximumDisplacement", 0.1)
            )
            for stage in progressive_sites.STAGE_ORDER
        )
        for pose_label, action, frame in poses:
            if armature is not None:
                if armature.animation_data is None:
                    armature.animation_data_create()
                if action is not None:
                    armature.animation_data.action = action
            context.scene.frame_set(frame)
            _set_site_weights(
                site,
                {stage: 0.0 for stage in progressive_sites.STAGE_ORDER},
            )
            baseline = _evaluated_world_points(target, depsgraph)
            baseline_lower, baseline_upper = _bounds(baseline)
            baseline_diagonal = (baseline_upper - baseline_lower).length
            pose_samples = []
            for sample in progressive_sites.transition_samples(
                site["severityAnchors"]
            ):
                evaluation = progressive_sites.evaluate_weights(
                    sample["severity"],
                    site["severityAnchors"],
                    site["transitionCurve"],
                )
                gore_stage = progressive_sites.detailed_gore_stage(
                    sample["severity"],
                    site["severityAnchors"],
                    site["transitionCurve"],
                )
                _set_site_weights(site, evaluation["weights"])
                evaluated = _evaluated_world_points(target, depsgraph)
                non_finite = sum(
                    not all(math.isfinite(value) for value in point)
                    for point in evaluated
                )
                max_displacement = (
                    max(
                        (point - basis).length
                        for point, basis in zip(evaluated, baseline)
                    )
                    if len(evaluated) == len(baseline)
                    else math.inf
                )
                lower, upper = _bounds(evaluated)
                bounds_expansion = max(
                    (baseline_lower - lower).length,
                    (upper - baseline_upper).length,
                )
                active_count = evaluation["activeMorphCount"]
                total_weight = evaluation["totalWeight"]
                pair_error = 0.0
                if detached is not None:
                    for stage_name, weight in evaluation["weights"].items():
                        if weight <= 1e-12:
                            continue
                        key_name = site["stages"][stage_name][
                            "deformationKeyName"
                        ]
                        attached_key = deformation._key(target, key_name)
                        detached_key = deformation._key(detached, key_name)
                        attached_basis = target.data.shape_keys.reference_key
                        detached_basis = detached.data.shape_keys.reference_key
                        if attached_key is None or detached_key is None:
                            pair_error = math.inf
                            break
                        for index in range(len(attached_key.data)):
                            attached_delta = deformation._local_delta_to_world(
                                target,
                                attached_key.data[index].co
                                - attached_basis.data[index].co,
                            )
                            detached_delta = deformation._local_delta_to_world(
                                detached,
                                detached_key.data[index].co
                                - detached_basis.data[index].co,
                            )
                            pair_error = max(
                                pair_error,
                                (attached_delta - detached_delta).length
                                * weight,
                            )
                visible_triangles = (
                    stage_records.get(gore_stage, {}).get(
                        "visibleTriangleCount",
                        0,
                    )
                    if gore_stage is not None
                    else 0
                )
                sample_errors = []
                if non_finite:
                    sample_errors.append("evaluated coordinates are non-finite")
                if active_count > 2:
                    sample_errors.append("more than two stage morphs are active")
                if total_weight > 1.0 + 1e-8:
                    sample_errors.append("structural stage weight exceeds 1.0")
                if (
                    evaluation["weights"]["LIGHT"] > 1e-8
                    and evaluation["weights"]["HEAVY"] > 1e-8
                ):
                    sample_errors.append("non-adjacent stages overlap")
                if max_displacement > maximum_allowed + 1e-5:
                    sample_errors.append(
                        "crossfade exceeds the registered displacement limit"
                    )
                if bounds_expansion > max(0.5, baseline_diagonal * 1.5):
                    sample_errors.append(
                        "crossfade causes extreme world-bounds expansion"
                    )
                if pair_error > deformation.SYNC_TOLERANCE:
                    sample_errors.append(
                        "attached/detached pair synchronization is unsafe"
                    )
                record = {
                    **sample,
                    "pose": pose_label,
                    "frame": frame,
                    "weights": dict(evaluation["weights"]),
                    "activeGoreStage": gore_stage or "NONE",
                    "maximumDisplacement": max_displacement,
                    "boundsExpansion": bounds_expansion,
                    "nonFiniteCount": non_finite,
                    "seamError": pair_error,
                    "attachedDetachedPairError": pair_error,
                    "generatedVisibleTriangles": int(visible_triangles),
                    "activeMorphCount": active_count,
                    "totalStructuralWeight": total_weight,
                    "status": "FAIL" if sample_errors else "PASS",
                    "errors": sample_errors,
                }
                pose_samples.append(record)
                if pose_label == "REST_OR_CURRENT":
                    sample_records.append(record)
                errors.extend(
                    f"{pose_label} {sample['transition']} "
                    f"{sample['sample']:.2f}: {value}"
                    for value in sample_errors
                )
            pose_records.append(
                {
                    "pose": pose_label,
                    "action": action.name if action is not None else "",
                    "frame": frame,
                    "status": (
                        "PASS"
                        if all(value["status"] == "PASS" for value in pose_samples)
                        else "FAIL"
                    ),
                    "samples": pose_samples,
                }
            )
    finally:
        deformation.restore_damage_preview_snapshot(context, snapshot)

    report = {
        "schema": progressive_sites.SITE_SCHEMA,
        "version": progressive_sites.SITE_VERSION,
        "siteId": site["siteId"],
        "siteGuid": site["siteGuid"],
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
        "stageValidation": stage_records,
        "transitionSamples": sample_records,
        "animationPoseResults": pose_records,
        "sampleCount": sum(
            len(record.get("samples", [])) for record in pose_records
        ),
        "cost": progressive_sites.cost_summary(site),
        "stateRestored": True,
    }
    report["reportDigest"] = progressive_sites.canonical_digest(report)
    return _store_validation_report(
        context,
        collection,
        site,
        report,
        stage_records,
    )


def _store_validation_report(
    context,
    collection,
    site,
    report,
    stage_records,
):
    settings = _settings(context)
    target = copy.deepcopy(site)
    for stage_name, validation in stage_records.items():
        if stage_name not in target["stages"]:
            continue
        target["stages"][stage_name]["validationStatus"] = str(
            validation.get("status", "FAIL")
        )
        target["stages"][stage_name]["measurements"] = copy.deepcopy(
            validation
        )
        target["stages"][stage_name]["triangleCount"] = int(
            validation.get(
                "triangleCount",
                target["stages"][stage_name]["triangleCount"],
            )
        )
        target["stages"][stage_name]["visibleTriangleCount"] = int(
            validation.get(
                "visibleTriangleCount",
                target["stages"][stage_name]["visibleTriangleCount"],
            )
        )
    target["validationStatus"] = str(report.get("status", "FAIL"))
    target["validationReport"] = copy.deepcopy(report)
    target["validationDigest"] = str(report.get("reportDigest", ""))
    target["cost"] = progressive_sites.cost_summary(target)
    target["enabledForExport"] = False
    target = progressive_sites.normalize_site(target)
    collection["sites"][_site_index(collection, site["siteGuid"])] = target
    stored = _store_collection(collection)
    stored_site = progressive_sites.site_by_guid(
        stored,
        site["siteGuid"],
    )
    if settings is not None:
        settings.progression_status = (
            f"PROGRESSION VALIDATION {report.get('status', 'FAIL')} — "
            f"{len(report.get('errors', []))} ERRORS"
        )
    return {
        **report,
        "siteStatus": stored_site["status"],
        "cost": stored_site["cost"],
    }


def validate_all_sites(context=None):
    context = context or bpy.context
    collection = _collection()
    reports = [
        validate_site(context, site["siteGuid"])
        for site in list(collection.get("sites", []))
    ]
    return {
        "status": (
            "FAIL"
            if any(report.get("status") != "PASS" for report in reports)
            else "PASS"
        ),
        "siteCount": len(reports),
        "reports": reports,
    }


def enable_site_for_export(context=None):
    context = context or bpy.context
    validation = validate_site(context)
    if validation["status"] != "PASS":
        raise RuntimeError(
            "Progressive site validation failed: "
            + "; ".join(validation.get("errors", [])[:4])
        )
    collection, site = _active_site(context=context)
    if site["status"] != "READY_FOR_EXPORT":
        raise RuntimeError(
            f"Site is {site['status']}; all stages must be saved and valid."
        )
    site["enabledForExport"] = True
    stored = _store_collection(collection)
    enabled = progressive_sites.site_by_guid(stored, site["siteGuid"])
    _settings(context).progression_status = (
        f"EXPORT ENABLED — {enabled['displayName']}"
    )
    return enabled


def disable_site_export(context=None):
    context = context or bpy.context
    collection, site = _active_site(context=context)
    site["enabledForExport"] = False
    stored = _store_collection(collection)
    disabled = progressive_sites.site_by_guid(stored, site["siteGuid"])
    _settings(context).progression_status = (
        f"EXPORT DISABLED — {disabled['displayName']}"
    )
    return disabled


def export_validation(context=None):
    context = context or bpy.context
    collection = _collection()
    errors = []
    warnings = []
    for site in collection.get("sites", []):
        if site["enabledForExport"]:
            if (
                site["status"] != "READY_FOR_EXPORT"
                or site["validationStatus"] != "PASS"
            ):
                errors.append(
                    f"Export-enabled site {site['displayName']!r} is "
                    f"{site['status']}."
                )
        else:
            warnings.append(
                f"Draft site {site['displayName']!r} is omitted from export "
                f"({site['status']})."
            )
    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
        "siteCount": collection["siteCount"],
        "exportEnabledSiteCount": sum(
            site["enabledForExport"] for site in collection.get("sites", [])
        ),
    }


def manifest_payload():
    collection = _collection()
    sites = [
        progressive_sites.manifest_site(site)
        for site in collection.get("sites", [])
        if site["enabledForExport"]
        and site["status"] == "READY_FOR_EXPORT"
        and site["validationStatus"] == "PASS"
    ]
    warnings = [
        {
            "siteId": site["siteId"],
            "siteGuid": site["siteGuid"],
            "status": site["status"],
            "message": "Draft site omitted because Include in Export is disabled.",
        }
        for site in collection.get("sites", [])
        if not site["enabledForExport"]
    ]
    resident = sum(
        site["cost"]["residentStageGoreTriangles"] for site in sites
    )
    visible = sum(
        site["cost"]["maximumVisibleStageGoreTriangles"]
        for site in sites
    )
    transition = sum(
        site["cost"]["maximumTransitionGoreTriangles"]
        for site in sites
    )
    return {
        "progressiveDamageSiteSchema": progressive_sites.SITE_SCHEMA,
        "progressiveDamageSites": sites,
        "progressiveDamageSiteWarnings": warnings,
        "progressiveDamageSiteCost": {
            "totalResidentStageGoreTriangles": resident,
            "maximumVisibleStageGoreTriangles": visible,
            "maximumTransitionGoreTriangles": transition,
            "totalManagedStageMorphTargets": sum(
                site["cost"]["managedStageMorphTargets"] for site in sites
            ),
            "maximumSimultaneousStageMorphs": 2 if sites else 0,
            "exportEnabledSiteCount": len(sites),
            "hiddenGeneratedNodeCount": sum(
                site["cost"]["hiddenGeneratedNodeCount"] for site in sites
            ),
        },
    }


def cached_ui_state(context=None):
    context = context or bpy.context
    collection, site = _active_site(context=context, required=False)
    settings = _settings(context)
    stage_name = str(
        getattr(settings, "progression_active_stage", "LIGHT")
    )
    return {
        "collection": collection,
        "site": site or {},
        "stage": (
            site["stages"].get(stage_name, {}) if site is not None else {}
        ),
        "stageName": stage_name,
    }
