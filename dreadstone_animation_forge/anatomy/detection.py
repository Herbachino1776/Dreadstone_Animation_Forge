"""Deterministic anatomy profile scoring, selection, and diagnostics."""

from __future__ import annotations

from typing import Mapping

from .model import RigSnapshot
from .orientation import orientation_contract
from .profiles import (
    HUMANOID_PROFILE_ID,
    QUADRUPED_PROFILE_ID,
    registry as builtin_registry,
)
from .resolver import mapped_bone_names, mapping_digest, resolve_roles
from .schema import AnatomyProfile, ProfileRegistry
from .validation import validate_mapping


ANALYSIS_SCHEMA = "dreadstone.creature_anatomy_analysis.v1"
ANALYZER_VERSION = "2026-07-31.anatomy-profile-1"
AUTO_MIN_CONFIDENCE = 0.62
AUTO_AMBIGUITY_DELTA = 0.08

OVERRIDE_PROFILE_IDS = {
    "HUMANOID": HUMANOID_PROFILE_ID,
    "QUADRUPED_DIGITIGRADE": QUADRUPED_PROFILE_ID,
    HUMANOID_PROFILE_ID: HUMANOID_PROFILE_ID,
    QUADRUPED_PROFILE_ID: QUADRUPED_PROFILE_ID,
}


def _required_total(profile: AnatomyProfile) -> int:
    return len(profile.required_roles) + sum(
        max(1, spec.min_count) for spec in profile.chains.values() if spec.required
    )


def _required_resolved(profile: AnatomyProfile, mapping: Mapping[str, object]) -> int:
    value = sum(1 for role in profile.required_roles if mapping.get(role))
    for role, spec in profile.chains.items():
        if spec.required:
            value += min(len(mapping.get(role, []) or []), max(1, spec.min_count))
    return value


def _first_name(mapping: Mapping[str, object], role: str) -> str:
    value = mapping.get(role)
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value) if value else ""


def _is_ancestor(ancestor: str, descendant: str, by_name) -> bool:
    current = by_name.get(descendant)
    seen: set[str] = set()
    while current is not None and current.name not in seen:
        if current.parent == ancestor:
            return True
        seen.add(current.name)
        current = by_name.get(current.parent)
    return False


def _connected(parent: str, child: str, by_name) -> bool:
    return bool(
        parent
        and child
        and child in by_name
        and (by_name[child].parent == parent or _is_ancestor(parent, child, by_name))
    )


def score_profile(
    profile: AnatomyProfile,
    snapshot: RigSnapshot,
    resolution: Mapping[str, object] | None = None,
) -> dict[str, object]:
    resolution = resolution or resolve_roles(profile, snapshot)
    mapping = resolution["mapping"]
    total = max(_required_total(profile), 1)
    completeness = _required_resolved(profile, mapping) / total
    distinct = len(set(mapped_bone_names(mapping))) / max(len(mapped_bone_names(mapping)), 1)
    topology = 0.0
    by_name = snapshot.by_name()
    if profile.creature_class == "QUADRUPED":
        contacts = [str(mapping.get(role, "")) for role in profile.contact_roles]
        topology += 0.10 if all(contacts) and len(set(contacts)) == 4 else 0.0
        limb_links = []
        for prefix, parts in (
                ("front_l", ("scapula", "upper", "lower", "carpus", "paw")),
                ("front_r", ("scapula", "upper", "lower", "carpus", "paw")),
                ("hind_l", ("hip", "upper", "lower", "hock", "paw")),
                ("hind_r", ("hip", "upper", "lower", "hock", "paw")),
        ):
            names = [_first_name(mapping, f"{prefix}_{part}") for part in parts]
            limb_links.extend(
                _connected(parent, child, by_name)
                for parent, child in zip(names, names[1:])
            )
        topology += 0.10 * (sum(limb_links) / max(len(limb_links), 1))

        core_checks = []
        ground = _first_name(mapping, "ground_root")
        body = _first_name(mapping, "body_center")
        pelvis = _first_name(mapping, "pelvis")
        chest = _first_name(mapping, "chest")
        head = _first_name(mapping, "head")
        core_checks.extend((
            _connected(ground, body, by_name),
            _connected(body, pelvis, by_name),
        ))
        for role, before, after in (
            ("spine_chain", pelvis, chest),
            ("neck_chain", chest, head),
        ):
            chain = [str(name) for name in (mapping.get(role, []) or [])]
            core_checks.append(bool(chain) and _connected(before, chain[0], by_name))
            core_checks.extend(
                _connected(parent, child, by_name)
                for parent, child in zip(chain, chain[1:])
            )
            core_checks.append(bool(chain) and _connected(chain[-1], after, by_name))
        topology += 0.05 * (sum(core_checks) / max(len(core_checks), 1))
        body = str(mapping.get("body_center", ""))
        head = str(mapping.get("head", ""))
        if body in by_name and head in by_name:
            delta = tuple(a - b for a, b in zip(by_name[head].center, by_name[body].center))
            horizontal = (delta[0] ** 2 + delta[1] ** 2) ** 0.5
            topology += 0.03 if horizontal > abs(delta[2]) else 0.0
    else:
        paired = all(
            mapping.get(role)
            for role in ("thigh_l", "thigh_r", "upper_arm_l", "upper_arm_r")
        )
        topology += 0.16 if paired else 0.0
        hips = str(mapping.get("hips", ""))
        head = str(mapping.get("head", ""))
        if hips in by_name and head in by_name:
            delta = tuple(a - b for a, b in zip(by_name[head].center, by_name[hips].center))
            topology += 0.12 if abs(delta[2]) >= max(abs(delta[0]), abs(delta[1])) else 0.0
    confidence = min(1.0, 0.70 * completeness + 0.02 * distinct + topology)
    return {
        "profileId": profile.profile_id,
        "confidence": round(confidence, 6),
        "requiredCompleteness": round(completeness, 6),
        "resolution": resolution,
    }


def _resolve_damage_templates(profile: AnatomyProfile, mapping: Mapping[str, object]):
    resolved = []
    for template in profile.damage_region_templates:
        roles = [str(role) for role in template.get("roleRefs", [])]
        bones: list[str] = []
        for role in roles:
            value = mapping.get(role)
            if isinstance(value, (list, tuple)):
                bones.extend(str(name) for name in value)
            elif value:
                bones.append(str(value))
        resolved.append({**dict(template), "resolvedBones": bones, "resolved": bool(bones)})
    return resolved


def analyze_selected_profile(
    profile: AnatomyProfile,
    snapshot: RigSnapshot,
    mapping: Mapping[str, object],
    *,
    confidence: float,
    override: str,
    ambiguities: list[object] | None = None,
    explicit_forward: str | None = None,
    rig_profile_id: str = "",
) -> dict[str, object]:
    orientation = orientation_contract(
        profile,
        mapping,
        snapshot,
        explicit_forward=explicit_forward,
    )
    readiness = validate_mapping(profile, mapping, snapshot, orientation)
    unsupported = sorted(
        name
        for name, capability in profile.capabilities.items()
        if not capability.production_ready
    )
    return {
        "schema": ANALYSIS_SCHEMA,
        "anatomySchema": profile.schema,
        "analyzerVersion": ANALYZER_VERSION,
        "profileId": profile.profile_id,
        "creatureClass": profile.creature_class,
        "locomotionClass": profile.locomotion_class,
        "rigProfileId": str(rig_profile_id),
        "detectionConfidence": round(float(confidence), 6),
        "profileOverride": str(override or "AUTO"),
        "roleMapping": dict(mapping),
        "mappingDigest": mapping_digest(mapping),
        "mappedRoleCount": len(mapping),
        "mappedBoneCount": len(mapped_bone_names(mapping)),
        "orientation": orientation,
        "contactRoles": list(profile.contact_roles),
        "capabilities": {
            name: capability.to_dict()
            for name, capability in sorted(profile.capabilities.items())
        },
        "readinessStatus": readiness["status"],
        "ready": readiness["ready"],
        "missingRequirements": readiness["missingRequirements"],
        "ambiguities": list(ambiguities or []),
        "warnings": readiness["warnings"],
        "blockers": readiness["blockers"],
        "worstBlocker": readiness["worstBlocker"],
        "unsupportedFeatures": unsupported,
        "damageRegionTemplates": _resolve_damage_templates(profile, mapping),
        "legacy": False,
    }


def detect_profile(
    snapshot: RigSnapshot,
    *,
    profile_registry: ProfileRegistry | None = None,
    override: str = "AUTO",
    manual_overrides: Mapping[str, str] | None = None,
    explicit_forward: str | None = None,
) -> dict[str, object]:
    profile_registry = profile_registry or builtin_registry
    override = str(override or "AUTO")
    if override == "CUSTOM_UNRESOLVED":
        return {
            "schema": ANALYSIS_SCHEMA,
            "analyzerVersion": ANALYZER_VERSION,
            "profileId": "",
            "creatureClass": "CUSTOM_UNRESOLVED",
            "locomotionClass": "UNRESOLVED",
            "detectionConfidence": 0.0,
            "profileOverride": override,
            "roleMapping": {},
            "mappingDigest": mapping_digest({}),
            "mappedRoleCount": 0,
            "mappedBoneCount": 0,
            "orientation": {},
            "contactRoles": [],
            "capabilities": {},
            "readinessStatus": "UNSUPPORTED_ANATOMY",
            "ready": False,
            "missingRequirements": [],
            "ambiguities": [],
            "warnings": [],
            "blockers": [{"code": "UNSUPPORTED_ANATOMY", "message": "Custom anatomy has no resolved profile."}],
            "worstBlocker": "Custom anatomy has no resolved profile.",
            "unsupportedFeatures": [],
            "damageRegionTemplates": [],
            "legacy": False,
            "profileScores": [],
        }

    scored = []
    for profile in profile_registry.all():
        resolution = resolve_roles(profile, snapshot, manual_overrides=manual_overrides)
        scored.append(score_profile(profile, snapshot, resolution))
    scored.sort(key=lambda value: (-float(value["confidence"]), str(value["profileId"])))

    selected = None
    if override != "AUTO":
        profile_id = OVERRIDE_PROFILE_IDS.get(override, override)
        selected = next((value for value in scored if value["profileId"] == profile_id), None)
        if selected is None:
            raise ValueError(f"Unknown anatomy profile override {override!r}.")
    elif scored:
        best = scored[0]
        second = scored[1] if len(scored) > 1 else None
        ambiguous = (
            second is not None
            and float(best["confidence"]) - float(second["confidence"]) < AUTO_AMBIGUITY_DELTA
        )
        if float(best["confidence"]) < AUTO_MIN_CONFIDENCE:
            return _unselected_result("UNSUPPORTED_ANATOMY", scored, "No supported profile met the confidence threshold.")
        if ambiguous:
            return _unselected_result("PROFILE_AMBIGUOUS", scored, "Multiple anatomy profiles have similar confidence; choose an explicit override.")
        selected = best

    if selected is None:
        return _unselected_result("UNSUPPORTED_ANATOMY", scored, "No Creature Anatomy Profiles are registered.")
    profile = profile_registry.require(str(selected["profileId"]))
    resolution = selected["resolution"]
    result = analyze_selected_profile(
        profile,
        snapshot,
        resolution["mapping"],
        confidence=float(selected["confidence"]),
        override=override,
        ambiguities=list(resolution["ambiguities"]),
        explicit_forward=explicit_forward,
    )
    result["profileScores"] = [
        {
            "profileId": value["profileId"],
            "confidence": value["confidence"],
            "requiredCompleteness": value["requiredCompleteness"],
        }
        for value in scored
    ]
    return result


def _unselected_result(status: str, scores, message: str) -> dict[str, object]:
    return {
        "schema": ANALYSIS_SCHEMA,
        "analyzerVersion": ANALYZER_VERSION,
        "profileId": "",
        "creatureClass": "UNRESOLVED",
        "locomotionClass": "UNRESOLVED",
        "detectionConfidence": float(scores[0]["confidence"]) if scores else 0.0,
        "profileOverride": "AUTO",
        "roleMapping": {},
        "mappingDigest": mapping_digest({}),
        "mappedRoleCount": 0,
        "mappedBoneCount": 0,
        "orientation": {},
        "contactRoles": [],
        "capabilities": {},
        "readinessStatus": status,
        "ready": False,
        "missingRequirements": [],
        "ambiguities": [
            {"profileId": value["profileId"], "confidence": value["confidence"]}
            for value in scores[:2]
        ],
        "warnings": [],
        "blockers": [{"code": status, "message": message}],
        "worstBlocker": message,
        "unsupportedFeatures": [],
        "damageRegionTemplates": [],
        "legacy": False,
        "profileScores": [
            {
                "profileId": value["profileId"],
                "confidence": value["confidence"],
                "requiredCompleteness": value["requiredCompleteness"],
            }
            for value in scores
        ],
    }


__all__ = (
    "ANALYSIS_SCHEMA",
    "ANALYZER_VERSION",
    "AUTO_AMBIGUITY_DELTA",
    "AUTO_MIN_CONFIDENCE",
    "analyze_selected_profile",
    "detect_profile",
    "score_profile",
)
