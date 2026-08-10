"""Versioned, Blender-independent offensive Action metadata contract."""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from typing import Any, Mapping


OFFENSIVE_ACTION_SCHEMA = "dreadstone.offensive_action.v1"
OFFENSIVE_ACTION_PROPERTY = "dsb_offensive_action_json"

SOCKET_ROLES = frozenset({"MAIN_HAND_R", "MAIN_HAND_L"})
WEAPON_CLASSES = frozenset({
    "ONE_HAND_BLADE",
    "ONE_HAND_BLUNT",
    "TWO_HAND_BLADE",
    "TWO_HAND_BLUNT",
    "POLEARM",
})
ROOT_MOTION_POLICIES = frozenset({"IN_PLACE", "AUTHORED_ROOT_MOTION"})
ATTACK_SOURCE_ROLES = frozenset({"EQUIPPED_MAIN_HAND"})
_STABLE_ID = re.compile(r"^[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?$")
_EPSILON = 1.0e-6


OFFENSIVE_ACTION_VARIANTS = {
    "ATTACK_SLASH_RTL_ONE_HAND": {
        "draftName": "DSB_DRAFT_Attack_Slash_RTL_OneHand",
        "baseName": "DSB_Attack_Slash_RTL_OneHand",
        "combatActionId": "humanoid_one_hand_slash_rtl",
        "attackFamily": "SLASH_RIGHT_TO_LEFT",
        "socketRole": "MAIN_HAND_R",
        "compatibleWeaponClasses": ("ONE_HAND_BLADE", "ONE_HAND_BLUNT"),
        "motion": "SLASH_RTL",
        "windupSeconds": 0.46,
        "activeSeconds": 0.30,
        "recoverySeconds": 0.58,
    },
    "ATTACK_SLASH_LTR_ONE_HAND": {
        "draftName": "DSB_DRAFT_Attack_Slash_LTR_OneHand",
        "baseName": "DSB_Attack_Slash_LTR_OneHand",
        "combatActionId": "humanoid_one_hand_slash_ltr",
        "attackFamily": "SLASH_LEFT_TO_RIGHT",
        "socketRole": "MAIN_HAND_R",
        "compatibleWeaponClasses": ("ONE_HAND_BLADE", "ONE_HAND_BLUNT"),
        "motion": "SLASH_LTR",
        "windupSeconds": 0.48,
        "activeSeconds": 0.30,
        "recoverySeconds": 0.56,
    },
    "ATTACK_OVERHEAD_ONE_HAND": {
        "draftName": "DSB_DRAFT_Attack_Overhead_OneHand",
        "baseName": "DSB_Attack_Overhead_OneHand",
        "combatActionId": "humanoid_one_hand_overhead",
        "attackFamily": "OVERHEAD_STRIKE",
        "socketRole": "MAIN_HAND_R",
        "compatibleWeaponClasses": ("ONE_HAND_BLADE", "ONE_HAND_BLUNT"),
        "motion": "OVERHEAD",
        "windupSeconds": 0.54,
        "activeSeconds": 0.28,
        "recoverySeconds": 0.62,
    },
    "ATTACK_THRUST_ONE_HAND": {
        "draftName": "DSB_DRAFT_Attack_Thrust_OneHand",
        "baseName": "DSB_Attack_Thrust_OneHand",
        "combatActionId": "humanoid_one_hand_thrust",
        "attackFamily": "THRUST",
        "socketRole": "MAIN_HAND_R",
        "compatibleWeaponClasses": ("ONE_HAND_BLADE", "POLEARM"),
        "motion": "THRUST",
        "windupSeconds": 0.42,
        "activeSeconds": 0.26,
        "recoverySeconds": 0.52,
    },
    "ATTACK_HEAVY_ONE_HAND": {
        "draftName": "DSB_DRAFT_Attack_Heavy_OneHand",
        "baseName": "DSB_Attack_Heavy_OneHand",
        "combatActionId": "humanoid_one_hand_heavy",
        "attackFamily": "HEAVY_COMMITTED_STRIKE",
        "socketRole": "MAIN_HAND_R",
        "compatibleWeaponClasses": ("ONE_HAND_BLADE", "ONE_HAND_BLUNT"),
        "motion": "HEAVY",
        "windupSeconds": 0.72,
        "activeSeconds": 0.36,
        "recoverySeconds": 0.78,
    },
    "ATTACK_SLASH_TWO_HAND": {
        "draftName": "DSB_DRAFT_Attack_Slash_TwoHand",
        "baseName": "DSB_Attack_Slash_TwoHand",
        "combatActionId": "humanoid_two_hand_slash",
        "attackFamily": "TWO_HAND_DIAGONAL_STRIKE",
        "socketRole": "MAIN_HAND_R",
        "secondarySocketRole": "MAIN_HAND_L",
        "compatibleWeaponClasses": ("TWO_HAND_BLADE", "TWO_HAND_BLUNT", "POLEARM"),
        "motion": "TWO_HAND_SLASH",
        "windupSeconds": 0.62,
        "activeSeconds": 0.34,
        "recoverySeconds": 0.70,
    },
    "ATTACK_OVERHEAD_TWO_HAND": {
        "draftName": "DSB_DRAFT_Attack_Overhead_TwoHand",
        "baseName": "DSB_Attack_Overhead_TwoHand",
        "combatActionId": "humanoid_two_hand_overhead",
        "attackFamily": "TWO_HAND_OVERHEAD_STRIKE",
        "socketRole": "MAIN_HAND_R",
        "secondarySocketRole": "MAIN_HAND_L",
        "compatibleWeaponClasses": ("TWO_HAND_BLADE", "TWO_HAND_BLUNT", "POLEARM"),
        "motion": "TWO_HAND_OVERHEAD",
        "windupSeconds": 0.68,
        "activeSeconds": 0.34,
        "recoverySeconds": 0.74,
    },
    "ATTACK_THRUST_TWO_HAND": {
        "draftName": "DSB_DRAFT_Attack_Thrust_TwoHand",
        "baseName": "DSB_Attack_Thrust_TwoHand",
        "combatActionId": "humanoid_two_hand_thrust",
        "attackFamily": "TWO_HAND_THRUST",
        "socketRole": "MAIN_HAND_R",
        "secondarySocketRole": "MAIN_HAND_L",
        "compatibleWeaponClasses": ("TWO_HAND_BLADE", "POLEARM"),
        "motion": "TWO_HAND_THRUST",
        "windupSeconds": 0.56,
        "activeSeconds": 0.30,
        "recoverySeconds": 0.64,
    },
}


def phase_metadata(variant: Mapping[str, Any], fps: float) -> tuple[dict[str, Any], dict[str, int]]:
    """Create contiguous phase intervals from the actual rounded frame schedule."""

    fps = max(float(fps), 0.001)
    start = 1
    active_start = start + max(1, round(float(variant["windupSeconds"]) * fps))
    active_end = active_start + max(1, round(float(variant["activeSeconds"]) * fps))
    end = active_end + max(1, round(float(variant["recoverySeconds"]) * fps))
    windup_end = (active_start - start) / fps
    active_end_seconds = (active_end - start) / fps
    duration = (end - start) / fps
    metadata = {
        "schema": OFFENSIVE_ACTION_SCHEMA,
        "combatActionId": str(variant["combatActionId"]),
        "attackFamily": str(variant["attackFamily"]),
        "socketRole": str(variant["socketRole"]),
        "compatibleWeaponClasses": list(variant["compatibleWeaponClasses"]),
        "attackSourceRole": "EQUIPPED_MAIN_HAND",
        "rootMotionPolicy": "IN_PLACE",
        "clipDurationSeconds": round(duration, 6),
        "phases": {
            "windup": {"startSeconds": 0.0, "endSeconds": round(windup_end, 6)},
            "active": {"startSeconds": round(windup_end, 6), "endSeconds": round(active_end_seconds, 6)},
            "recovery": {"startSeconds": round(active_end_seconds, 6), "endSeconds": round(duration, 6)},
        },
        "commitment": {
            "timeSeconds": round(windup_end, 6),
            "lockOrientationThroughActive": True,
        },
    }
    secondary = variant.get("secondarySocketRole")
    if secondary:
        metadata["secondarySocketRole"] = str(secondary)
    schedule = {
        "start": start,
        "anticipation": start + max(1, round((active_start - start) * 0.62)),
        "activeStart": active_start,
        "contact": active_start + max(1, round((active_end - active_start) * 0.55)),
        "activeEnd": active_end,
        "end": end,
    }
    return metadata, schedule


def validate_offensive_metadata(
    metadata: Mapping[str, Any],
    *,
    clip_duration_seconds: float | None = None,
    approved: bool = True,
    draft: bool = False,
    available_socket_roles: set[str] | frozenset[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(metadata, Mapping):
        return ["Offensive Action metadata must be an object."]
    if metadata.get("schema") != OFFENSIVE_ACTION_SCHEMA:
        errors.append(f"schema must be {OFFENSIVE_ACTION_SCHEMA}.")
    action_id = metadata.get("combatActionId")
    if not isinstance(action_id, str) or not _STABLE_ID.fullmatch(action_id):
        errors.append("combatActionId must be a stable lowercase identifier.")
    if not isinstance(metadata.get("attackFamily"), str) or not metadata.get("attackFamily"):
        errors.append("attackFamily is required.")
    socket_roles = [metadata.get("socketRole")]
    if metadata.get("secondarySocketRole") is not None:
        socket_roles.append(metadata.get("secondarySocketRole"))
    for role in socket_roles:
        if role not in SOCKET_ROLES:
            errors.append(f"Unsupported socket role {role!r}.")
        elif available_socket_roles is not None and role not in available_socket_roles:
            errors.append(f"Required socket role {role!r} is not authored for the runtime body.")
    classes = metadata.get("compatibleWeaponClasses")
    if not isinstance(classes, list) or not classes or any(value not in WEAPON_CLASSES for value in classes):
        errors.append("compatibleWeaponClasses must contain supported unique weapon classes.")
    elif len(set(classes)) != len(classes):
        errors.append("compatibleWeaponClasses contains duplicates.")
    if metadata.get("attackSourceRole") not in ATTACK_SOURCE_ROLES:
        errors.append("attackSourceRole is unsupported.")
    if metadata.get("rootMotionPolicy") not in ROOT_MOTION_POLICIES:
        errors.append("rootMotionPolicy is unsupported.")
    if not approved or draft:
        errors.append("Offensive Action must be explicitly approved and non-draft.")

    declared_duration = metadata.get("clipDurationSeconds")
    if not isinstance(declared_duration, (int, float)) or not math.isfinite(float(declared_duration)) or float(declared_duration) <= 0:
        errors.append("clipDurationSeconds must be finite and positive.")
        declared_duration = None
    duration = float(clip_duration_seconds) if clip_duration_seconds is not None else declared_duration
    if duration is not None and (not math.isfinite(float(duration)) or float(duration) <= 0):
        errors.append("The runtime clip duration is invalid.")
        duration = None
    if declared_duration is not None and duration is not None and abs(float(declared_duration) - float(duration)) > 1.0e-4:
        errors.append("clipDurationSeconds does not match the Action range.")

    phases = metadata.get("phases")
    bounds: dict[str, tuple[float, float]] = {}
    if not isinstance(phases, Mapping):
        errors.append("phases must contain WINDUP, ACTIVE, and RECOVERY intervals.")
    else:
        for name in ("windup", "active", "recovery"):
            phase = phases.get(name)
            if not isinstance(phase, Mapping):
                errors.append(f"{name.upper()} interval is missing.")
                continue
            start = phase.get("startSeconds")
            end = phase.get("endSeconds")
            if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in (start, end)):
                errors.append(f"{name.upper()} interval must use finite seconds.")
                continue
            bounds[name] = (float(start), float(end))
        if len(bounds) == 3:
            windup, active, recovery = bounds["windup"], bounds["active"], bounds["recovery"]
            if windup[0] < 0 or windup[1] < windup[0]:
                errors.append("WINDUP interval is negative or reversed.")
            if active[1] <= active[0]:
                errors.append("ACTIVE interval must have positive duration.")
            if recovery[1] < recovery[0]:
                errors.append("RECOVERY interval is reversed.")
            if abs(windup[0]) > _EPSILON:
                errors.append("WINDUP must begin at clip time zero.")
            if abs(windup[1] - active[0]) > _EPSILON or abs(active[1] - recovery[0]) > _EPSILON:
                errors.append("WINDUP, ACTIVE, and RECOVERY must be contiguous and non-overlapping.")
            if duration is not None and abs(recovery[1] - float(duration)) > 1.0e-4:
                errors.append("RECOVERY must end at the clip duration.")
            if duration is not None and any(value < -_EPSILON or value > float(duration) + _EPSILON for pair in bounds.values() for value in pair):
                errors.append("An offensive phase lies outside the clip.")

    commitment = metadata.get("commitment")
    if commitment is not None:
        time_value = commitment.get("timeSeconds") if isinstance(commitment, Mapping) else None
        if not isinstance(time_value, (int, float)) or not math.isfinite(float(time_value)):
            errors.append("commitment.timeSeconds must be finite.")
        elif duration is not None and not 0 <= float(time_value) <= float(duration):
            errors.append("commitment.timeSeconds lies outside the clip.")
        if not isinstance(commitment, Mapping) or not isinstance(commitment.get("lockOrientationThroughActive"), bool):
            errors.append("commitment.lockOrientationThroughActive must be boolean.")
    return errors


def stamp_offensive_metadata(action, metadata: Mapping[str, Any]):
    action[OFFENSIVE_ACTION_PROPERTY] = json.dumps(
        dict(metadata), sort_keys=True, separators=(",", ":")
    )
    action["dsb_root_motion_policy"] = str(metadata.get("rootMotionPolicy", "IN_PLACE"))
    return action


def read_offensive_metadata(action) -> dict[str, Any] | None:
    raw = action.get(OFFENSIVE_ACTION_PROPERTY, "")
    if not raw:
        return None
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("Offensive Action metadata is not valid JSON.") from None
    if not isinstance(value, dict):
        raise ValueError("Offensive Action metadata must be a JSON object.")
    return value


def validated_action_metadata(
    action,
    *,
    clip_duration_seconds: float | None = None,
    require_approved: bool = True,
    available_socket_roles: set[str] | frozenset[str] | None = None,
) -> dict[str, Any] | None:
    metadata = read_offensive_metadata(action)
    if metadata is None:
        return None
    errors = validate_offensive_metadata(
        metadata,
        clip_duration_seconds=clip_duration_seconds,
        approved=bool(action.get("dsb_approved", False)) if require_approved else True,
        draft=bool(action.get("dsb_draft", False)) if require_approved else False,
        available_socket_roles=available_socket_roles,
    )
    if errors:
        raise ValueError("Invalid offensive Action metadata: " + " ".join(errors))
    return deepcopy(metadata)


__all__ = (
    "ATTACK_SOURCE_ROLES",
    "OFFENSIVE_ACTION_PROPERTY",
    "OFFENSIVE_ACTION_SCHEMA",
    "OFFENSIVE_ACTION_VARIANTS",
    "ROOT_MOTION_POLICIES",
    "SOCKET_ROLES",
    "WEAPON_CLASSES",
    "phase_metadata",
    "read_offensive_metadata",
    "stamp_offensive_metadata",
    "validate_offensive_metadata",
    "validated_action_metadata",
)
