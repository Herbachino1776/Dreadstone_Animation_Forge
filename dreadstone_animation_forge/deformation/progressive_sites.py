"""Pure Progressive Damage Site schema, evaluation, and export helpers.

Every stage is an independently authored, complete Damage Key relative to
Basis.  This module owns organization and transition math only; it never
derives, scales, or otherwise edits an artist's stage recipe.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import uuid
from collections.abc import Mapping, Sequence


SITE_SCHEMA = "dreadstone.progressive_damage_sites.v1"
SITE_VERSION = 1
STAGE_ORDER = ("LIGHT", "MEDIUM", "HEAVY")
SITE_STATUSES = (
    "EMPTY",
    "DRAFT",
    "READY_FOR_PREVIEW",
    "READY_FOR_EXPORT",
    "NEEDS_STAGE_SAVE",
    "NEEDS_VALIDATION",
    "FAILED",
)
TRANSITION_MODES = ("ADJACENT_CROSSFADE",)
TRANSITION_CURVES = ("SMOOTHSTEP", "LINEAR")
GORE_TRANSITION_MODES = ("MIDPOINT_REPLACE",)
DEFAULT_ANCHORS = {"light": 0.33, "medium": 0.66, "heavy": 1.0}


def canonical_digest(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def opaque_id(prefix, value=None):
    token = str(value or uuid.uuid4().hex).strip().lower()
    token = re.sub(r"[^a-z0-9]+", "", token)
    if not token:
        raise ValueError("Stable ID token must contain a letter or digit")
    return f"{str(prefix).strip().lower()}_{token[:48]}"


def safe_site_id(value):
    cleaned = re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "site_" + cleaned
    return cleaned[:64].rstrip("_")


def _finite(value, label, *, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a finite number") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    if minimum is not None and number < float(minimum):
        raise ValueError(f"{label} must be at least {float(minimum):g}")
    if maximum is not None and number > float(maximum):
        raise ValueError(f"{label} must be at most {float(maximum):g}")
    return number


def _vector3(value, label, default, *, normalize=False):
    raw = default if value is None else value
    if (
        not isinstance(raw, Sequence)
        or isinstance(raw, (str, bytes))
        or len(raw) != 3
    ):
        raise ValueError(f"{label} must contain three finite numbers")
    result = [_finite(component, label) for component in raw]
    if normalize:
        length = math.sqrt(sum(component * component for component in result))
        if length <= 1e-12:
            result = [float(component) for component in default]
            length = math.sqrt(sum(component * component for component in result))
        result = [component / length for component in result]
    return result


def normalize_anchors(value=None):
    raw = value if isinstance(value, Mapping) else {}
    anchors = {
        stage: _finite(
            raw.get(stage, default),
            f"{stage.title()} severity anchor",
            minimum=0.0,
            maximum=1.0,
        )
        for stage, default in DEFAULT_ANCHORS.items()
    }
    if not (0.0 < anchors["light"] < anchors["medium"] < anchors["heavy"]):
        raise ValueError(
            "Severity anchors must be strictly ordered: "
            "0 < Light < Medium < Heavy <= 1"
        )
    return anchors


def empty_stage(stage, stage_id=None):
    stage_name = str(stage).upper()
    if stage_name not in STAGE_ORDER:
        raise ValueError(f"Unsupported progression stage {stage_name!r}")
    return {
        "stage": stage_name,
        "stageId": str(stage_id or opaque_id("stage")),
        "damageKeyId": "",
        "deformationKeyName": "",
        "activeStampId": "",
        "regionId": "",
        "regionMode": "",
        "targetObject": "",
        "attachedObject": "",
        "detachedObject": "",
        "recipeDigest": "",
        "deformationDigest": "",
        "captureDigest": "",
        "generatedComponentIds": {},
        "generatedNodeNames": {},
        "ownershipRoles": [],
        "saved": False,
        "dirty": False,
        "validationStatus": "EMPTY",
        "triangleCount": 0,
        "visibleTriangleCount": 0,
        "measurements": {},
    }


def normalize_stage(value, stage, *, stage_id=None):
    stage_name = str(stage).upper()
    if stage_name not in STAGE_ORDER:
        raise ValueError(f"Unsupported progression stage {stage_name!r}")
    raw = value if isinstance(value, Mapping) else {}
    normalized = empty_stage(
        stage_name,
        raw.get("stageId") or stage_id or opaque_id("stage"),
    )
    normalized.update(
        {
            "damageKeyId": str(raw.get("damageKeyId", "")).strip(),
            "deformationKeyName": str(
                raw.get("deformationKeyName", raw.get("damageKeyName", ""))
            ),
            "activeStampId": str(raw.get("activeStampId", "")),
            "regionId": str(raw.get("regionId", "")),
            "regionMode": str(raw.get("regionMode", "")),
            "targetObject": str(raw.get("targetObject", "")),
            "attachedObject": str(
                raw.get("attachedObject", raw.get("targetObject", ""))
            ),
            "detachedObject": str(raw.get("detachedObject", "")),
            "recipeDigest": str(raw.get("recipeDigest", "")),
            "deformationDigest": str(raw.get("deformationDigest", "")),
            "captureDigest": str(raw.get("captureDigest", "")),
            "generatedComponentIds": copy.deepcopy(
                raw.get("generatedComponentIds", {})
                if isinstance(raw.get("generatedComponentIds", {}), Mapping)
                else {}
            ),
            "generatedNodeNames": copy.deepcopy(
                raw.get("generatedNodeNames", {})
                if isinstance(raw.get("generatedNodeNames", {}), Mapping)
                else {}
            ),
            "ownershipRoles": sorted(
                {
                    str(role).upper()
                    for role in raw.get("ownershipRoles", [])
                    if str(role).upper() in {"ATTACHED", "DETACHED", "CORE"}
                }
            ),
            "saved": bool(raw.get("saved", False)),
            "dirty": bool(raw.get("dirty", False)),
            "validationStatus": str(
                raw.get(
                    "validationStatus",
                    "NOT_VALIDATED" if raw.get("damageKeyId") else "EMPTY",
                )
            ).upper(),
            "triangleCount": max(0, int(raw.get("triangleCount", 0))),
            "visibleTriangleCount": max(
                0,
                int(raw.get("visibleTriangleCount", raw.get("triangleCount", 0))),
            ),
            "measurements": copy.deepcopy(
                raw.get("measurements", {})
                if isinstance(raw.get("measurements", {}), Mapping)
                else {}
            ),
        }
    )
    if bool(normalized["damageKeyId"]) != bool(normalized["deformationKeyName"]):
        raise ValueError(
            f"{stage_name} must store both a stable Damage Key ID and its artist name"
        )
    if not normalized["damageKeyId"]:
        normalized.update(
            {
                "activeStampId": "",
                "regionId": "",
                "regionMode": "",
                "targetObject": "",
                "attachedObject": "",
                "detachedObject": "",
                "recipeDigest": "",
                "deformationDigest": "",
                "captureDigest": "",
                "generatedComponentIds": {},
                "generatedNodeNames": {},
                "ownershipRoles": [],
                "saved": False,
                "dirty": False,
                "validationStatus": "EMPTY",
                "triangleCount": 0,
                "visibleTriangleCount": 0,
                "measurements": {},
            }
        )
    return normalized


def site_status(site):
    stages = [
        normalize_stage(
            (site.get("stages", {}) if isinstance(site, Mapping) else {}).get(stage),
            stage,
        )
        for stage in STAGE_ORDER
    ]
    assigned = [stage for stage in stages if stage["damageKeyId"]]
    if not assigned:
        return "EMPTY"
    if len(assigned) < len(STAGE_ORDER):
        return "DRAFT"
    if any(not stage["saved"] or stage["dirty"] for stage in assigned):
        return "NEEDS_STAGE_SAVE"
    statuses = {stage["validationStatus"] for stage in assigned}
    if "FAIL" in statuses or "FAILED" in statuses:
        return "FAILED"
    site_validation = str(
        site.get("validationStatus", "NOT_VALIDATED")
        if isinstance(site, Mapping)
        else "NOT_VALIDATED"
    ).upper()
    if site_validation == "PASS" and statuses <= {"PASS"}:
        return "READY_FOR_EXPORT"
    if statuses <= {"PASS"}:
        return "READY_FOR_PREVIEW"
    return "NEEDS_VALIDATION"


def normalize_site(value):
    if not isinstance(value, Mapping):
        raise ValueError("Progressive Damage Site must be an object")
    schema = str(value.get("schema", SITE_SCHEMA))
    version = int(value.get("version", SITE_VERSION))
    if schema != SITE_SCHEMA or version != SITE_VERSION:
        raise ValueError(
            f"Unsupported Progressive Damage Site schema/version {schema!r}/{version!r}"
        )
    site_id = safe_site_id(
        value.get("siteId", value.get("displayName", "damage_site"))
    )
    site_guid = str(value.get("siteGuid", "")).strip()
    if not site_guid:
        site_guid = opaque_id("site")
    display_name = str(value.get("displayName", site_id.replace("_", " ").title()))
    stages_raw = value.get("stages", {})
    if not isinstance(stages_raw, Mapping):
        raise ValueError("Progressive Damage Site stages must be an object")
    stages = {
        stage: normalize_stage(
            stages_raw.get(stage, stages_raw.get(stage.lower())),
            stage,
        )
        for stage in STAGE_ORDER
    }
    assigned_ids = [
        stage["damageKeyId"] for stage in stages.values() if stage["damageKeyId"]
    ]
    if len(assigned_ids) != len(set(assigned_ids)):
        raise ValueError("One Damage Key cannot drive two stages in the same site")
    transition_mode = str(
        value.get("transitionMode", TRANSITION_MODES[0])
    ).upper()
    transition_curve = str(
        value.get("transitionCurve", TRANSITION_CURVES[0])
    ).upper()
    gore_mode = str(
        value.get("goreTransitionMode", GORE_TRANSITION_MODES[0])
    ).upper()
    if transition_mode not in TRANSITION_MODES:
        raise ValueError(f"Unsupported transition mode {transition_mode!r}")
    if transition_curve not in TRANSITION_CURVES:
        raise ValueError(f"Unsupported transition curve {transition_curve!r}")
    if gore_mode not in GORE_TRANSITION_MODES:
        raise ValueError(f"Unsupported gore transition mode {gore_mode!r}")
    normalized = {
        "schema": SITE_SCHEMA,
        "version": SITE_VERSION,
        "siteId": site_id,
        "siteGuid": site_guid,
        "displayName": display_name[:96],
        "regionId": str(value.get("regionId", "")),
        "structuralGroup": str(
            value.get("structuralGroup", value.get("regionId", ""))
        ),
        "enabledForExport": bool(value.get("enabledForExport", False)),
        "anchorLocal": _vector3(
            value.get("anchorLocal"),
            "Site anchor",
            (0.0, 0.0, 0.0),
        ),
        "radius": _finite(
            value.get("radius", 0.10),
            "Site influence radius",
            minimum=1e-6,
            maximum=100.0,
        ),
        "preferredDirectionLocal": _vector3(
            value.get("preferredDirectionLocal"),
            "Preferred incoming direction",
            (1.0, 0.0, 0.0),
            normalize=True,
        ),
        "transitionMode": transition_mode,
        "transitionCurve": transition_curve,
        "goreTransitionMode": gore_mode,
        "severityAnchors": normalize_anchors(value.get("severityAnchors")),
        "stages": stages,
        "validationStatus": str(
            value.get("validationStatus", "NOT_VALIDATED")
        ).upper(),
        "validationDigest": str(value.get("validationDigest", "")),
        "validationReport": copy.deepcopy(
            value.get("validationReport", {})
            if isinstance(value.get("validationReport", {}), Mapping)
            else {}
        ),
        "cost": copy.deepcopy(
            value.get("cost", {})
            if isinstance(value.get("cost", {}), Mapping)
            else {}
        ),
    }
    normalized["status"] = site_status(normalized)
    if normalized["enabledForExport"] and normalized["status"] != "READY_FOR_EXPORT":
        normalized["enabledForExport"] = False
    return normalized


def new_site(
    display_name,
    region_id,
    structural_group=None,
    *,
    site_id=None,
    site_guid=None,
):
    name = str(display_name).strip() or "Damage Site"
    guid = str(site_guid or opaque_id("site"))
    stages = {
        stage: empty_stage(
            stage,
            opaque_id("stage", canonical_digest([guid, stage])[:32]),
        )
        for stage in STAGE_ORDER
    }
    return normalize_site(
        {
            "schema": SITE_SCHEMA,
            "version": SITE_VERSION,
            "siteId": site_id or safe_site_id(name),
            "siteGuid": guid,
            "displayName": name,
            "regionId": str(region_id),
            "structuralGroup": str(structural_group or region_id),
            "stages": stages,
        }
    )


def normalize_sites(payload=None):
    if payload is None:
        raw = {}
    elif isinstance(payload, Mapping):
        raw = payload
    else:
        raise ValueError("Progressive Damage Site collection must be an object")
    if raw and str(raw.get("schema", SITE_SCHEMA)) != SITE_SCHEMA:
        raise ValueError(
            f"Unsupported Progressive Damage Site collection {raw.get('schema')!r}"
        )
    if raw and int(raw.get("version", SITE_VERSION)) != SITE_VERSION:
        raise ValueError(
            f"Unsupported Progressive Damage Site collection version "
            f"{raw.get('version')!r}"
        )
    values = raw.get("sites", [])
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError("Progressive Damage Site records must be an array")
    sites = [normalize_site(site) for site in values]
    guids = [site["siteGuid"] for site in sites]
    ids = [site["siteId"] for site in sites]
    if len(guids) != len(set(guids)):
        raise ValueError("Progressive Damage Site GUIDs must be unique")
    if len(ids) != len(set(ids)):
        raise ValueError("Progressive Damage Site IDs must be unique")
    assigned = {}
    for site in sites:
        for stage_name, stage in site["stages"].items():
            key_id = stage["damageKeyId"]
            if not key_id:
                continue
            prior = assigned.get(key_id)
            if prior is not None:
                raise ValueError(
                    f"Damage Key {key_id!r} is already assigned to "
                    f"{prior[0]}/{prior[1]}"
                )
            assigned[key_id] = (site["siteId"], stage_name)
    sites.sort(key=lambda site: (site["displayName"].casefold(), site["siteGuid"]))
    normalized = {
        "schema": SITE_SCHEMA,
        "version": SITE_VERSION,
        "activeSiteGuid": str(raw.get("activeSiteGuid", "")),
        "sites": sites,
    }
    if normalized["activeSiteGuid"] not in set(guids):
        normalized["activeSiteGuid"] = guids[0] if guids else ""
    normalized["siteCount"] = len(sites)
    normalized["digest"] = canonical_digest(
        {key: value for key, value in normalized.items() if key != "digest"}
    )
    return normalized


def site_by_guid(collection, site_guid):
    normalized = normalize_sites(collection)
    for site in normalized["sites"]:
        if site["siteGuid"] == str(site_guid):
            return site
    raise KeyError(f"Progressive Damage Site {site_guid!r} was not found")


def assign_stage(collection, site_guid, stage, assignment):
    normalized = normalize_sites(collection)
    stage_name = str(stage).upper()
    if stage_name not in STAGE_ORDER:
        raise ValueError(f"Unsupported progression stage {stage_name!r}")
    candidate = normalize_stage(assignment, stage_name)
    if not candidate["damageKeyId"]:
        raise ValueError("Assigning a stage requires a stable Damage Key ID")
    for site in normalized["sites"]:
        for other_name, other in site["stages"].items():
            if (
                other["damageKeyId"] == candidate["damageKeyId"]
                and not (
                    site["siteGuid"] == str(site_guid)
                    and other_name == stage_name
                )
            ):
                raise ValueError(
                    "This Damage Key already drives "
                    f"{site['displayName']} / {other_name}"
                )
    target = next(
        (
            site
            for site in normalized["sites"]
            if site["siteGuid"] == str(site_guid)
        ),
        None,
    )
    if target is None:
        raise KeyError(f"Progressive Damage Site {site_guid!r} was not found")
    if target["regionId"] and candidate["regionId"] != target["regionId"]:
        raise ValueError(
            f"{stage_name} belongs to region {candidate['regionId']!r}; "
            f"the site owns {target['regionId']!r}"
        )
    candidate["stageId"] = target["stages"][stage_name]["stageId"]
    target["stages"][stage_name] = candidate
    target["validationStatus"] = "NOT_VALIDATED"
    target["validationDigest"] = ""
    target["enabledForExport"] = False
    target["status"] = site_status(target)
    return normalize_sites(normalized)


def unassign_stage(collection, site_guid, stage):
    normalized = normalize_sites(collection)
    stage_name = str(stage).upper()
    target = next(
        (
            site
            for site in normalized["sites"]
            if site["siteGuid"] == str(site_guid)
        ),
        None,
    )
    if target is None:
        raise KeyError(f"Progressive Damage Site {site_guid!r} was not found")
    prior_id = target["stages"][stage_name]["stageId"]
    target["stages"][stage_name] = empty_stage(stage_name, prior_id)
    target["validationStatus"] = "NOT_VALIDATED"
    target["validationDigest"] = ""
    target["enabledForExport"] = False
    target["status"] = site_status(target)
    return normalize_sites(normalized)


def smoothstep(value):
    t = min(1.0, max(0.0, _finite(value, "Interpolation parameter")))
    return t * t * (3.0 - 2.0 * t)


def evaluate_weights(severity, anchors=None, curve="SMOOTHSTEP"):
    position = min(
        1.0,
        max(0.0, _finite(severity, "Progression severity")),
    )
    resolved = normalize_anchors(anchors)
    curve_name = str(curve).upper()
    if curve_name not in TRANSITION_CURVES:
        raise ValueError(f"Unsupported transition curve {curve_name!r}")

    if position <= resolved["light"]:
        lower, higher = "BASIS", "LIGHT"
        raw_t = position / resolved["light"]
    elif position <= resolved["medium"]:
        lower, higher = "LIGHT", "MEDIUM"
        raw_t = (
            (position - resolved["light"])
            / (resolved["medium"] - resolved["light"])
        )
    else:
        lower, higher = "MEDIUM", "HEAVY"
        raw_t = (
            (position - resolved["medium"])
            / (resolved["heavy"] - resolved["medium"])
        )
    raw_t = min(1.0, max(0.0, raw_t))
    t = smoothstep(raw_t) if curve_name == "SMOOTHSTEP" else raw_t
    weights = {stage: 0.0 for stage in STAGE_ORDER}
    if lower != "BASIS":
        weights[lower] = 1.0 - t
    weights[higher] = t
    if position <= 0.0:
        weights = {stage: 0.0 for stage in STAGE_ORDER}
    active = [stage for stage, weight in weights.items() if weight > 1e-12]
    return {
        "severity": position,
        "segment": f"{lower}_TO_{higher}",
        "lowerStage": lower,
        "higherStage": higher,
        "segmentT": raw_t,
        "interpolatedT": t,
        "curve": curve_name,
        "weights": weights,
        "activeStages": active,
        "activeMorphCount": len(active),
        "totalWeight": sum(weights.values()),
    }


def detailed_gore_stage(severity, anchors=None, curve="SMOOTHSTEP"):
    evaluation = evaluate_weights(severity, anchors, curve)
    if evaluation["severity"] <= 0.0:
        return None
    if evaluation["segmentT"] < 0.5 - 1e-12:
        lower = evaluation["lowerStage"]
        return None if lower == "BASIS" else lower
    return evaluation["higherStage"]


def transition_samples(anchors=None):
    resolved = normalize_anchors(anchors)
    boundaries = (
        ("BASIS_TO_LIGHT", 0.0, resolved["light"]),
        ("LIGHT_TO_MEDIUM", resolved["light"], resolved["medium"]),
        ("MEDIUM_TO_HEAVY", resolved["medium"], resolved["heavy"]),
    )
    return [
        {
            "transition": name,
            "sample": fraction,
            "severity": start + (end - start) * fraction,
        }
        for name, start, end in boundaries
        for fraction in (0.0, 0.25, 0.50, 0.75, 1.0)
    ]


def cost_summary(site):
    normalized = normalize_site(site)
    stages = normalized["stages"]
    resident = sum(stage["triangleCount"] for stage in stages.values())
    visible_by_stage = {
        name: stage["visibleTriangleCount"] for name, stage in stages.items()
    }
    adjacent = (
        ("LIGHT",),
        ("LIGHT", "MEDIUM"),
        ("MEDIUM", "HEAVY"),
    )
    transition_max = max(
        (
            max(visible_by_stage[name] for name in pair)
            for pair in adjacent
        ),
        default=0,
    )
    return {
        "residentStageGoreTriangles": resident,
        "maximumVisibleStageGoreTriangles": max(
            visible_by_stage.values(),
            default=0,
        ),
        "maximumTransitionGoreTriangles": transition_max,
        "managedStageMorphTargets": sum(
            bool(stage["damageKeyId"]) for stage in stages.values()
        ),
        "maximumSimultaneousStageMorphs": 2,
        "hiddenGeneratedNodeCount": sum(
            len(stage["generatedNodeNames"]) for stage in stages.values()
        ),
        "perStageVisibleTriangles": visible_by_stage,
    }


def manifest_site(site):
    normalized = normalize_site(site)
    cost = cost_summary(normalized)
    stage_records = []
    for stage_name in STAGE_ORDER:
        stage = normalized["stages"][stage_name]
        stage_records.append(
            {
                "stage": stage_name,
                "stageId": stage["stageId"],
                "damageKeyId": stage["damageKeyId"],
                "deformationKeyName": stage["deformationKeyName"],
                "activeStampId": stage["activeStampId"],
                "regionId": stage["regionId"],
                "regionMode": stage["regionMode"],
                "targetObject": stage["targetObject"],
                "attachedObject": stage["attachedObject"],
                "detachedObject": stage["detachedObject"],
                "recipeDigest": stage["recipeDigest"],
                "deformationDigest": stage["deformationDigest"],
                "captureDigest": stage["captureDigest"],
                "generatedComponentIds": copy.deepcopy(
                    stage["generatedComponentIds"]
                ),
                "generatedNodeNames": copy.deepcopy(
                    stage["generatedNodeNames"]
                ),
                "ownershipRoles": list(stage["ownershipRoles"]),
                "saved": stage["saved"],
                "validationStatus": stage["validationStatus"],
                "triangleCount": stage["triangleCount"],
                "visibleTriangleCount": stage["visibleTriangleCount"],
                "recommendedSeverity": normalized["severityAnchors"][
                    stage_name.lower()
                ],
                "measurements": copy.deepcopy(stage["measurements"]),
            }
        )
    return {
        "schema": SITE_SCHEMA,
        "version": SITE_VERSION,
        "siteId": normalized["siteId"],
        "siteGuid": normalized["siteGuid"],
        "displayName": normalized["displayName"],
        "regionId": normalized["regionId"],
        "structuralGroup": normalized["structuralGroup"],
        "anchorLocal": list(normalized["anchorLocal"]),
        "radius": normalized["radius"],
        "preferredDirectionLocal": list(
            normalized["preferredDirectionLocal"]
        ),
        "severityAnchors": dict(normalized["severityAnchors"]),
        "transitionMode": normalized["transitionMode"],
        "transitionCurve": normalized["transitionCurve"],
        "goreTransitionMode": normalized["goreTransitionMode"],
        "stageOrder": list(STAGE_ORDER),
        "stages": stage_records,
        "attachedDetachedMapping": {
            stage["stage"]: {
                "regionMode": stage["regionMode"],
                "targetObject": stage["targetObject"],
                "attachedObject": stage["attachedObject"],
                "detachedObject": stage["detachedObject"],
                "ownershipRoles": list(stage["ownershipRoles"]),
            }
            for stage in stage_records
        },
        "status": normalized["status"],
        "validationStatus": normalized["validationStatus"],
        "validationDigest": normalized["validationDigest"],
        "cost": cost,
        "runtimeImplementationIncluded": False,
        "activationContract": {
            "stageResults": "ABSOLUTE_RELATIVE_TO_BASIS",
            "structuralTransition": "ADJACENT_SMOOTHSTEP_CROSSFADE",
            "maximumSimultaneousStageMorphs": 2,
            "maximumStructuralWeight": 1.0,
            "detailedGoreTransition": "MIDPOINT_REPLACE",
            "detailedGoreStagesStack": False,
            "defaultState": "ALL_SITE_GEOMETRY_INACTIVE",
            "gameplayThresholdsOwnedByRuntime": True,
            "impactEnergyAccumulationOwnedByRuntime": True,
            "runtimeImplementationIncluded": False,
        },
    }
