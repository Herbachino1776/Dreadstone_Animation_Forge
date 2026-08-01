"""Safe JSON persistence, export serialization, and legacy migration."""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from .detection import ANALYSIS_SCHEMA, ANALYZER_VERSION
from .profiles import HUMANOID_PROFILE, HUMANOID_PROFILE_ID
from .resolver import canonical_mapping, mapping_digest


ANATOMY_PROPERTY = "dsb_creature_anatomy_json"
PROFILE_ID_PROPERTY = "dsb_anatomy_profile_id"
MAPPING_DIGEST_PROPERTY = "dsb_anatomy_mapping_digest"
OVERRIDE_PROPERTY = "dsb_anatomy_profile_override"


def legacy_humanoid_metadata(
    mapping: Mapping[str, object] | None = None,
    *,
    forward_axis: str = "-Y",
) -> dict[str, Any]:
    canonical = canonical_mapping(mapping or {})
    return {
        "schema": ANALYSIS_SCHEMA,
        "anatomySchema": HUMANOID_PROFILE.schema,
        "analyzerVersion": "LEGACY_PRE_ANATOMY_PROFILE",
        "profileId": HUMANOID_PROFILE_ID,
        "creatureClass": HUMANOID_PROFILE.creature_class,
        "locomotionClass": HUMANOID_PROFILE.locomotion_class,
        "rigProfileId": "",
        "detectionConfidence": 0.0,
        "profileOverride": "AUTO",
        "roleMapping": canonical,
        "mappingDigest": mapping_digest(canonical),
        "mappedRoleCount": len(canonical),
        "orientation": {
            "forwardAxis": forward_axis,
            "upAxis": "+Z",
            "leftAxis": "+X" if forward_axis == "-Y" else "-X",
            "contactRoles": list(HUMANOID_PROFILE.contact_roles),
        },
        "contactRoles": list(HUMANOID_PROFILE.contact_roles),
        "capabilities": {
            name: spec.to_dict() for name, spec in HUMANOID_PROFILE.capabilities.items()
        },
        "readinessStatus": "HUMANOID_READY",
        "ready": True,
        "missingRequirements": [],
        "ambiguities": [],
        "warnings": ["Anatomy metadata was absent; legacy humanoid compatibility is in use."],
        "blockers": [],
        "worstBlocker": "",
        "unsupportedFeatures": [],
        "damageRegionTemplates": [],
        "legacy": True,
    }


def migrate_metadata(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return legacy_humanoid_metadata()
    value = copy.deepcopy(dict(payload))
    schema = str(value.get("schema", ""))
    if schema == ANALYSIS_SCHEMA:
        value.setdefault("legacy", False)
        value.setdefault("analyzerVersion", ANALYZER_VERSION)
        value.setdefault("rigProfileId", "")
        value.setdefault("roleMapping", {})
        value["roleMapping"] = canonical_mapping(value["roleMapping"])
        value["mappingDigest"] = mapping_digest(value["roleMapping"])
        return value
    if schema in {"", "dreadstone.rig_analysis.v0"}:
        mapping = value.get("mapping", value.get("roleMapping", {}))
        migrated = legacy_humanoid_metadata(mapping)
        facing = str(value.get("forwardAxis", value.get("facing", "-Y")))
        if facing in {"NEG_Y", "-Y"}:
            migrated["orientation"]["forwardAxis"] = "-Y"
        elif facing in {"POS_Y", "+Y"}:
            migrated["orientation"]["forwardAxis"] = "+Y"
        migrated["legacySource"] = schema or "PRE_SCHEMA"
        return migrated
    raise ValueError(f"Unsupported anatomy analysis schema {schema!r}.")


def store_metadata(owner, analysis: Mapping[str, Any]) -> dict[str, Any]:
    value = migrate_metadata(analysis)
    owner[ANATOMY_PROPERTY] = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    owner[PROFILE_ID_PROPERTY] = str(value.get("profileId", ""))
    owner[MAPPING_DIGEST_PROPERTY] = str(value.get("mappingDigest", ""))
    owner[OVERRIDE_PROPERTY] = str(value.get("profileOverride", "AUTO"))
    return value


def load_metadata(owner, *, infer_legacy: bool = False) -> dict[str, Any] | None:
    raw = owner.get(ANATOMY_PROPERTY, "") if owner is not None else ""
    if not raw:
        return legacy_humanoid_metadata() if infer_legacy else None
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("Stored Creature Anatomy metadata is unreadable.") from None
    return migrate_metadata(payload)


def clear_override(owner) -> None:
    if owner is not None:
        owner[OVERRIDE_PROPERTY] = "AUTO"


def export_metadata(owner_or_metadata, *, infer_legacy: bool = False) -> dict[str, Any] | None:
    if isinstance(owner_or_metadata, Mapping) and "profileId" in owner_or_metadata:
        value = migrate_metadata(owner_or_metadata)
    else:
        value = load_metadata(owner_or_metadata, infer_legacy=infer_legacy)
    if value is None:
        return None
    fields = (
        "schema", "anatomySchema", "profileId", "creatureClass", "locomotionClass",
        "rigProfileId", "roleMapping", "mappingDigest", "orientation",
        "contactRoles", "capabilities", "readinessStatus", "analyzerVersion", "legacy",
    )
    return {field: copy.deepcopy(value.get(field)) for field in fields}


__all__ = (
    "ANATOMY_PROPERTY",
    "MAPPING_DIGEST_PROPERTY",
    "OVERRIDE_PROPERTY",
    "PROFILE_ID_PROPERTY",
    "clear_override",
    "export_metadata",
    "legacy_humanoid_metadata",
    "load_metadata",
    "migrate_metadata",
    "store_metadata",
)
