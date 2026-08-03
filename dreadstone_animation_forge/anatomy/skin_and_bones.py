"""Skin & Bones canonical humanoid handoff parsing.

Animation Forge owns Actions, while Skin & Bones owns the production rest rig.
This module translates the explicit Skin & Bones semantic contract into Forge's
anatomy roles without importing or copying a canonical GLB.
"""

from __future__ import annotations

import json
from typing import Mapping


SBF_CANONICAL_RIG_VERSION = "SBF_HUMANOID_YPLUS_V1"
SBF_ORIENTATION_STATE = "CANONICAL_Y_PLUS"
SBF_FORWARD_AXIS = "+Y"
SBF_UP_AXIS = "+Z"
SBF_ROOT_BONE = "root"

SBF_RIG_VERSION_PROPERTY = "sbf_canonical_rig_version"
SBF_BONE_MAPPING_PROPERTY = "sbf_bone_mapping"
SBF_FORWARD_AXIS_PROPERTY = "sbf_forward_axis"
SBF_UP_AXIS_PROPERTY = "sbf_up_axis"
SBF_ROOT_BONE_PROPERTY = "sbf_root_bone"
SBF_RIG_CONTRACT_VERSION_PROPERTY = "sbf_rig_contract_version"
SBF_UNIT_SCALE_METERS_PROPERTY = "sbf_unit_scale_meters"
SBF_ORIENTATION_REVISION_PROPERTY = "sbf_orientation_revision"
SBF_ORIENTATION_STATE_PROPERTY = "sbf_orientation_state"


CANONICAL_HUMANOID_MAPPING = {
    "root": "root",
    "hips": "body",
    "spine": "body_top0",
    "spine_mid": "body_top1",
    "chest": "body_top2",
    "neck": "neck",
    "head": "head",
    "shoulder_l": "shoulder_left",
    "upper_arm_l": "arm_left_top",
    "lower_arm_l": "arm_left_bot",
    "hand_l": "arm_left_hand",
    "shoulder_r": "shoulder_right",
    "upper_arm_r": "arm_right_top",
    "lower_arm_r": "arm_right_bot",
    "hand_r": "arm_right_hand",
    "thigh_l": "leg_left_top",
    "shin_l": "leg_left_bot",
    "foot_l": "leg_left_foot",
    "thigh_r": "leg_right_top",
    "shin_r": "leg_right_bot",
    "foot_r": "leg_right_foot",
}

CANONICAL_HUMANOID_PARENTS = {
    "root": "",
    "body": "root",
    "body_top0": "body",
    "body_top1": "body_top0",
    "body_top2": "body_top1",
    "neck": "body_top2",
    "head": "neck",
    "shoulder_left": "body_top2",
    "arm_left_top": "shoulder_left",
    "arm_left_bot": "arm_left_top",
    "arm_left_hand": "arm_left_bot",
    "shoulder_right": "body_top2",
    "arm_right_top": "shoulder_right",
    "arm_right_bot": "arm_right_top",
    "arm_right_hand": "arm_right_bot",
    "leg_left_top": "body",
    "leg_left_bot": "leg_left_top",
    "leg_left_foot": "leg_left_bot",
    "leg_right_top": "body",
    "leg_right_bot": "leg_right_top",
    "leg_right_foot": "leg_right_bot",
}


SBF_TO_FORGE_ROLE = {
    "root": "root",
    "pelvis": "hips",
    "spine_lower": "spine",
    "spine_middle": "spine_mid",
    "chest": "chest",
    "neck": "neck",
    "head": "head",
    "shoulder_left": "shoulder_l",
    "upper_arm_left": "upper_arm_l",
    "lower_arm_left": "lower_arm_l",
    "hand_left": "hand_l",
    "shoulder_right": "shoulder_r",
    "upper_arm_right": "upper_arm_r",
    "lower_arm_right": "lower_arm_r",
    "hand_right": "hand_r",
    "upper_leg_left": "thigh_l",
    "lower_leg_left": "shin_l",
    "foot_left": "foot_l",
    "upper_leg_right": "thigh_r",
    "lower_leg_right": "shin_r",
    "foot_right": "foot_r",
}


def _property(owner, name: str, default=""):
    if owner is None:
        return default
    try:
        return owner.get(name, default)
    except (AttributeError, TypeError):
        return default


def _owners(armature):
    """Yield likely Blender owners for object/data/GLB-extra metadata."""

    seen = set()
    candidates = [armature, getattr(armature, "data", None)]
    candidates.extend(getattr(armature, "children_recursive", ()) or ())
    candidates.extend(getattr(armature, "children", ()) or ())
    for owner in candidates:
        if owner is None:
            continue
        identity = id(owner)
        if identity in seen:
            continue
        seen.add(identity)
        yield owner


def _first_property(armature, name: str, default=""):
    for owner in _owners(armature):
        value = _property(owner, name, None)
        if value is not None and value != "":
            return value
    return default


def _mapping_payload(raw) -> dict[str, str]:
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    if not isinstance(raw, Mapping):
        try:
            raw = dict(raw)
        except (TypeError, ValueError):
            return {}
    return {
        str(role): str(name)
        for role, name in raw.items()
        if str(role) and str(name)
    }


def forge_mapping(armature) -> dict[str, str]:
    """Return the Skin & Bones semantic map expressed as Forge roles."""

    source = _mapping_payload(
        _first_property(armature, SBF_BONE_MAPPING_PROPERTY, "")
    )
    if source:
        translated = {
            forge_role: source[sbf_role]
            for sbf_role, forge_role in SBF_TO_FORGE_ROLE.items()
            if source.get(sbf_role)
        }
    else:
        translated = dict(CANONICAL_HUMANOID_MAPPING)
    available = set(getattr(getattr(armature, "data", None), "bones", {}).keys())
    if available:
        translated = {
            role: name for role, name in translated.items() if name in available
        }
    return translated


def contract(armature) -> dict[str, object] | None:
    """Read the explicit Skin & Bones rig contract from a Blender armature."""

    rig_version = str(
        _first_property(armature, SBF_RIG_VERSION_PROPERTY, "")
    )
    if not rig_version:
        return None
    forward_axis = str(
        _first_property(armature, SBF_FORWARD_AXIS_PROPERTY, "")
    )
    up_axis = str(_first_property(armature, SBF_UP_AXIS_PROPERTY, ""))
    root_bone = str(
        _first_property(armature, SBF_ROOT_BONE_PROPERTY, SBF_ROOT_BONE)
    )
    orientation_state = str(
        _first_property(armature, SBF_ORIENTATION_STATE_PROPERTY, "")
    )
    try:
        orientation_revision = int(
            _first_property(armature, SBF_ORIENTATION_REVISION_PROPERTY, 0)
        )
    except (TypeError, ValueError):
        orientation_revision = 0
    try:
        rig_contract_version = int(
            _first_property(armature, SBF_RIG_CONTRACT_VERSION_PROPERTY, 0)
        )
    except (TypeError, ValueError):
        rig_contract_version = 0
    try:
        unit_scale_meters = float(
            _first_property(armature, SBF_UNIT_SCALE_METERS_PROPERTY, 0.0)
        )
    except (TypeError, ValueError):
        unit_scale_meters = 0.0
    mapping = forge_mapping(armature)
    return {
        "rigVersion": rig_version,
        "supported": rig_version == SBF_CANONICAL_RIG_VERSION,
        "forwardAxis": forward_axis,
        "upAxis": up_axis,
        "rootBone": root_bone,
        "orientationState": orientation_state,
        "orientationRevision": orientation_revision,
        "rigContractVersion": rig_contract_version,
        "unitScaleMeters": unit_scale_meters,
        "roleMapping": mapping,
        "canonicalYPlus": bool(
            rig_version == SBF_CANONICAL_RIG_VERSION
            and forward_axis == SBF_FORWARD_AXIS
            and up_axis == SBF_UP_AXIS
            and root_bone == SBF_ROOT_BONE
            and orientation_state == SBF_ORIENTATION_STATE
            and orientation_revision == 1
            and rig_contract_version == 1
            and abs(unit_scale_meters - 1.0) <= 1.0e-6
        ),
    }


def require_canonical_yplus(armature, *, label="Animation authoring"):
    """Reject noncanonical or Y- rigs; conversion belongs to Skin & Bones."""

    value = contract(armature)
    if value is None:
        raise RuntimeError(
            f"{label} requires a Skin & Bones {SBF_CANONICAL_RIG_VERSION} "
            "character. Rig or re-rig the model in Skin & Bones Forge 2.1.0+."
        )
    if not value["supported"]:
        raise RuntimeError(
            f"{label} does not support Skin & Bones rig version "
            f"{value['rigVersion']!r}; expected {SBF_CANONICAL_RIG_VERSION}."
        )
    if not value["canonicalYPlus"]:
        raise RuntimeError(
            f"{label} requires canonical Blender +Y forward / +Z up with root "
            "motion on 'root'. Convert or rebuild the character in Skin & Bones; "
            "Animation Forge no longer supports Y- rigs."
        )
    missing = sorted(
        role for role in CANONICAL_HUMANOID_MAPPING if not value["roleMapping"].get(role)
    )
    if missing:
        raise RuntimeError(
            f"{label} received an incomplete Skin & Bones mapping: "
            + ", ".join(missing)
            + "."
        )
    mismatched = sorted(
        role
        for role, expected in CANONICAL_HUMANOID_MAPPING.items()
        if value["roleMapping"].get(role) != expected
    )
    if mismatched:
        raise RuntimeError(
            f"{label} received a renamed or noncanonical Skin & Bones mapping: "
            + ", ".join(mismatched)
            + ". Re-rig the character with the current canonical template."
        )
    available = set(getattr(getattr(armature, "data", None), "bones", {}).keys())
    expected = set(CANONICAL_HUMANOID_MAPPING.values())
    if available and available != expected:
        missing_bones = sorted(expected - available)
        extra_bones = sorted(available - expected)
        details = []
        if missing_bones:
            details.append("missing " + ", ".join(missing_bones))
        if extra_bones:
            details.append("unexpected " + ", ".join(extra_bones))
        raise RuntimeError(
            f"{label} requires the exact 21-bone canonical hierarchy ("
            + "; ".join(details)
            + "). Re-rig the character in Skin & Bones."
        )
    bones = getattr(getattr(armature, "data", None), "bones", {})
    hierarchy_errors = []
    for bone_name, expected_parent in CANONICAL_HUMANOID_PARENTS.items():
        bone = bones.get(bone_name) if hasattr(bones, "get") else None
        if bone is None or not hasattr(bone, "parent"):
            continue
        parent = getattr(bone, "parent", None)
        actual_parent = str(getattr(parent, "name", "")) if parent else ""
        if actual_parent != expected_parent:
            hierarchy_errors.append(
                f"{bone_name}->{actual_parent or '<root>'} "
                f"(expected {expected_parent or '<root>'})"
            )
    if hierarchy_errors:
        raise RuntimeError(
            f"{label} received a noncanonical hierarchy: "
            + "; ".join(hierarchy_errors)
            + ". Re-rig the character in Skin & Bones."
        )
    return value


__all__ = (
    "CANONICAL_HUMANOID_MAPPING",
    "CANONICAL_HUMANOID_PARENTS",
    "SBF_CANONICAL_RIG_VERSION",
    "SBF_FORWARD_AXIS",
    "SBF_ORIENTATION_STATE",
    "SBF_RIG_CONTRACT_VERSION_PROPERTY",
    "SBF_ROOT_BONE",
    "SBF_TO_FORGE_ROLE",
    "SBF_UP_AXIS",
    "SBF_UNIT_SCALE_METERS_PROPERTY",
    "contract",
    "forge_mapping",
    "require_canonical_yplus",
)
