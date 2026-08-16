"""Authored humanoid attack bases, preview, and target-free FK validation.

The built-in records in this module are animation assets expressed as semantic
key poses.  They deliberately do not refer to an enemy, a weapon mesh, a hit
point, or Motion Studio.  Preview bakes the records to ordinary pose-bone FK
curves on the canonical Skin & Bones +Y humanoid.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

import bpy
from bpy_extras import anim_utils
from mathutils import Matrix, Quaternion, Vector

from . import animation_library, offensive_actions
from .anatomy import skin_and_bones


AUTHORED_ATTACK_SCHEMA = "dreadstone.authored_attack.v1"
AUTHORED_ATTACK_PROPERTY = "dsb_authored_attack_json"
AUTHORED_PREVIEW_PROPERTY = "dsb_authored_attack_preview"
PREVIEW_PROXY_PROPERTY = "dsb_authored_attack_preview_proxy"
PREVIEW_ACTION_PREFIX = "DSB_AUTHORED_PREVIEW_"
OWNED_CONSTRAINT_PREFIX = "DSB_AUTHORED_ATTACK_"
OWNED_HELPER_PROPERTY = "dsb_authored_attack_helper"
RUNTIME_ARMATURE_NAME = "DSB_DAMAGE_RIG"
SOURCE_ARMATURE_NAME = "SBF_ProductionRig"
_PREVIEW_SESSIONS = {}
REQUIRED_MARKERS = (
    "Attack_Start",
    "Windup_Anticipation",
    "Active_Start",
    "Contact",
    "Active_End",
    "Attack_End",
)

# These limits intentionally stay narrower than the legacy recipe limits.  The
# controls are polish macros around an approved base, not a new motion solver.
MACRO_LIMITS = {
    "anticipation": (0.75, 1.25),
    "strike": (0.80, 1.20),
    "follow_through": (0.70, 1.30),
    "torso": (0.70, 1.30),
    "reach": (0.88, 1.10),
    "elbow": (0.80, 1.20),
    "wrist": (0.60, 1.35),
    "stance": (0.75, 1.25),
    "speed": (0.60, 1.60),
}


def _pose(
    *,
    body=(0.0, 0.0, -0.055),
    pelvis=(0.0, 0.0, 0.0),
    spine=(0.0, 0.0, 0.0),
    spine_mid=(0.0, 0.0, 0.0),
    chest=(0.0, 0.0, 0.0),
    neck=(0.0, 0.0, 0.0),
    head=(0.0, 0.0, 0.0),
    shoulder_r=(0.0, 0.0, 0.0),
    shoulder_l=(0.0, 0.0, 0.0),
    hand_r=(0.24, 0.20, 1.03),
    hand_l=(-0.23, 0.20, 1.02),
    pole_r=(0.58, 0.03, 0.92),
    pole_l=(-0.42, 0.08, 0.82),
    wrist_r=(0.0, 0.0, 0.0),
    wrist_l=(0.0, 0.0, 0.0),
    root_y=0.0,
):
    return {
        "body": tuple(body),
        "pelvis": tuple(pelvis),
        "spine": tuple(spine),
        "spine_mid": tuple(spine_mid),
        "chest": tuple(chest),
        "neck": tuple(neck),
        "head": tuple(head),
        "shoulder_r": tuple(shoulder_r),
        "shoulder_l": tuple(shoulder_l),
        "hand_r": tuple(hand_r),
        "hand_l": tuple(hand_l),
        "pole_r": tuple(pole_r),
        "pole_l": tuple(pole_l),
        "wrist_r": tuple(wrist_r),
        "wrist_l": tuple(wrist_l),
        "root_y": float(root_y),
    }


READY = _pose(
    body=(0.0, 0.0, -0.060),
    pelvis=(-3.0, 0.0, 0.0),
    spine=(-2.0, 0.0, 0.0),
    chest=(2.0, 0.0, 0.0),
    hand_r=(0.24, 0.20, 1.03),
    hand_l=(-0.23, 0.20, 1.02),
)


def _clip(
    clip_id: str,
    kind: str,
    title: str,
    mechanics: str,
    preview_families: Iterable[str],
    stages: Mapping[str, Mapping[str, Any]],
):
    variant = offensive_actions.OFFENSIVE_ACTION_VARIANTS[kind]
    if mechanics == "LIGHT_ONE_HAND_BLADE":
        compatible = ("ONE_HAND_BLADE",)
    elif mechanics == "TOP_HEAVY_ONE_HAND":
        compatible = ("ONE_HAND_BLUNT",)
    else:
        compatible = tuple(variant["compatibleWeaponClasses"])
    return {
        "schema": AUTHORED_ATTACK_SCHEMA,
        "clipId": clip_id,
        "actionKind": kind,
        "title": title,
        "displayName": title,
        "mechanicsFamily": mechanics,
        "mechanicsFamilies": tuple(preview_families),
        "previewWeaponFamilies": tuple(preview_families),
        "compatibleWeaponClasses": compatible,
        "rigProfileId": skin_and_bones.SBF_CANONICAL_RIG_VERSION,
        "forwardAxis": "+Y",
        "upAxis": "+Z",
        "stages": {name: deepcopy(dict(pose)) for name, pose in stages.items()},
    }


BUILTIN_CLIPS = (
    _clip(
        "authored_slash_rtl_light_blade_v1",
        "ATTACK_SLASH_RTL_ONE_HAND",
        "Slash Right to Left",
        "LIGHT_ONE_HAND_BLADE",
        ("SWORD",),
        {
            "start": READY,
            "anticipation": _pose(
                body=(0.015, -0.025, -0.082),
                pelvis=(-2.0, -18.0, 3.0),
                spine=(2.0, -12.0, 2.0),
                spine_mid=(2.0, -9.0, 1.0),
                chest=(3.0, -10.0, 2.0),
                neck=(0.0, 9.0, -1.0),
                head=(0.0, 9.0, -1.0),
                shoulder_r=(1.0, -7.0, 5.0),
                shoulder_l=(0.0, 4.0, -2.0),
                hand_r=(0.36, -0.05, 1.25),
                hand_l=(-0.30, 0.23, 1.07),
                pole_r=(0.61, -0.02, 1.04),
                pole_l=(-0.44, 0.12, 0.82),
                wrist_r=(-3.0, 7.0, 2.0),
            ),
            "active_start": _pose(
                body=(0.005, -0.010, -0.075),
                pelvis=(-4.0, -12.0, 1.0),
                spine=(-1.0, -7.0, 0.0),
                spine_mid=(0.0, -5.0, 0.0),
                chest=(2.0, -4.0, 1.0),
                neck=(0.0, 5.0, 0.0),
                head=(0.0, 5.0, 0.0),
                shoulder_r=(0.0, -5.0, 4.0),
                hand_r=(0.33, 0.06, 1.23),
                hand_l=(-0.33, 0.21, 1.03),
                pole_r=(0.62, 0.10, 0.99),
                pole_l=(-0.45, 0.12, 0.82),
                wrist_r=(-2.0, 5.0, 1.0),
            ),
            "contact": _pose(
                body=(-0.012, 0.025, -0.060),
                pelvis=(-7.0, 10.0, -2.0),
                spine=(-4.0, 9.0, -1.0),
                spine_mid=(-3.0, 8.0, -1.0),
                chest=(1.0, 11.0, -2.0),
                neck=(0.0, -7.0, 1.0),
                head=(0.0, -7.0, 1.0),
                shoulder_r=(-1.0, 8.0, -3.0),
                shoulder_l=(0.0, -3.0, 2.0),
                hand_r=(-0.12, 0.43, 1.09),
                hand_l=(-0.32, 0.18, 1.00),
                pole_r=(0.55, 0.02, 1.12),
                pole_l=(-0.46, 0.12, 0.80),
                wrist_r=(1.0, -2.0, -1.0),
                root_y=0.025,
            ),
            "follow": _pose(
                body=(-0.025, 0.030, -0.067),
                pelvis=(-8.0, 22.0, -4.0),
                spine=(-5.0, 14.0, -2.0),
                spine_mid=(-4.0, 12.0, -2.0),
                chest=(-1.0, 14.0, -3.0),
                neck=(1.0, -11.0, 1.0),
                head=(1.0, -10.0, 1.0),
                shoulder_r=(-2.0, 11.0, -5.0),
                shoulder_l=(0.0, -2.0, 2.0),
                hand_r=(-0.30, 0.34, 0.96),
                hand_l=(-0.31, 0.12, 0.96),
                pole_r=(0.34, 0.02, 1.08),
                pole_l=(-0.44, 0.08, 0.74),
                wrist_r=(2.0, -6.0, -2.0),
                root_y=0.045,
            ),
            "end": READY,
        },
    ),
    _clip(
        "authored_slash_ltr_light_blade_v1",
        "ATTACK_SLASH_LTR_ONE_HAND",
        "Slash Left to Right",
        "LIGHT_ONE_HAND_BLADE",
        ("SWORD",),
        {
            "start": READY,
            "anticipation": _pose(
                body=(-0.018, -0.012, -0.080),
                pelvis=(-5.0, 18.0, -3.0),
                spine=(-2.0, 11.0, -2.0),
                spine_mid=(0.0, 9.0, -1.0),
                chest=(3.0, 10.0, -2.0),
                neck=(0.0, -8.0, 1.0),
                head=(0.0, -8.0, 1.0),
                shoulder_r=(-1.0, 8.0, -4.0),
                shoulder_l=(0.0, -3.0, 2.0),
                hand_r=(-0.06, 0.12, 0.94),
                hand_l=(-0.30, 0.18, 0.98),
                pole_r=(0.27, 0.20, 0.75),
                pole_l=(-0.44, 0.10, 0.80),
                wrist_r=(2.0, -6.0, -2.0),
            ),
            "active_start": _pose(
                body=(-0.010, 0.0, -0.073),
                pelvis=(-6.0, 12.0, -2.0),
                spine=(-3.0, 7.0, -1.0),
                spine_mid=(-1.0, 5.0, 0.0),
                chest=(2.0, 5.0, -1.0),
                neck=(0.0, -4.0, 0.0),
                head=(0.0, -4.0, 0.0),
                shoulder_r=(-1.0, 5.0, -2.0),
                hand_r=(-0.02, 0.22, 0.99),
                hand_l=(-0.31, 0.18, 0.99),
                pole_r=(0.30, 0.27, 0.78),
                pole_l=(-0.45, 0.11, 0.82),
                wrist_r=(1.0, -4.0, -1.0),
            ),
            "contact": _pose(
                body=(0.008, 0.024, -0.058),
                pelvis=(-7.0, -8.0, 2.0),
                spine=(-5.0, -8.0, 1.0),
                spine_mid=(-3.0, -7.0, 1.0),
                chest=(1.0, -9.0, 2.0),
                neck=(0.0, 6.0, -1.0),
                head=(0.0, 6.0, -1.0),
                shoulder_r=(-1.0, -7.0, 3.0),
                shoulder_l=(0.0, 3.0, -2.0),
                hand_r=(0.15, 0.43, 1.09),
                hand_l=(-0.34, 0.24, 1.02),
                pole_r=(0.54, 0.04, 1.10),
                pole_l=(-0.47, 0.14, 0.82),
                wrist_r=(-1.0, 2.0, 1.0),
                root_y=0.025,
            ),
            "follow": _pose(
                body=(0.024, 0.028, -0.065),
                pelvis=(-6.0, -22.0, 4.0),
                spine=(-4.0, -14.0, 2.0),
                spine_mid=(-3.0, -12.0, 2.0),
                chest=(-1.0, -14.0, 3.0),
                neck=(1.0, 10.0, -1.0),
                head=(1.0, 9.0, -1.0),
                shoulder_r=(-2.0, -11.0, 5.0),
                shoulder_l=(0.0, 5.0, -3.0),
                hand_r=(0.38, 0.32, 1.18),
                hand_l=(-0.32, 0.08, 0.92),
                pole_r=(0.58, 0.02, 1.16),
                pole_l=(-0.46, 0.08, 0.76),
                wrist_r=(-2.0, 6.0, 2.0),
                root_y=0.045,
            ),
            "end": READY,
        },
    ),
    _clip(
        "authored_overhead_top_heavy_v1",
        "ATTACK_OVERHEAD_ONE_HAND",
        "Overhead Top-Heavy Strike",
        "TOP_HEAVY_ONE_HAND",
        ("AXE", "MACE"),
        {
            "start": READY,
            "anticipation": _pose(
                body=(0.012, -0.035, -0.100),
                pelvis=(5.0, -10.0, 2.0),
                spine=(5.0, -6.0, 1.0),
                spine_mid=(4.0, -5.0, 1.0),
                chest=(5.0, -5.0, 1.0),
                neck=(-2.0, 5.0, -1.0),
                head=(-2.0, 5.0, -1.0),
                shoulder_r=(0.0, -4.0, 9.0),
                shoulder_l=(0.0, 3.0, -3.0),
                hand_r=(0.20, -0.03, 1.42),
                hand_l=(-0.31, 0.24, 1.07),
                pole_r=(0.55, -0.02, 1.28),
                pole_l=(-0.46, 0.13, 0.84),
                wrist_r=(-5.0, 8.0, 2.0),
            ),
            "active_start": _pose(
                body=(0.010, -0.020, -0.094),
                pelvis=(2.0, -7.0, 1.0),
                spine=(2.0, -4.0, 0.0),
                spine_mid=(2.0, -3.0, 0.0),
                chest=(3.0, -3.0, 1.0),
                neck=(-1.0, 3.0, 0.0),
                head=(-1.0, 3.0, 0.0),
                shoulder_r=(0.0, -3.0, 8.0),
                hand_r=(0.18, 0.06, 1.40),
                hand_l=(-0.32, 0.22, 1.04),
                pole_r=(0.56, 0.05, 1.25),
                pole_l=(-0.47, 0.13, 0.84),
                wrist_r=(-4.0, 6.0, 2.0),
            ),
            "contact": _pose(
                body=(-0.005, 0.035, -0.072),
                pelvis=(-10.0, 3.0, -1.0),
                spine=(-8.0, 3.0, -1.0),
                spine_mid=(-6.0, 2.0, -1.0),
                chest=(-5.0, 2.0, -1.0),
                neck=(5.0, -2.0, 1.0),
                head=(5.0, -2.0, 1.0),
                shoulder_r=(-4.0, 2.0, -5.0),
                shoulder_l=(1.0, -1.0, 3.0),
                hand_r=(0.09, 0.67, 1.16),
                hand_l=(-0.44, 0.25, 0.96),
                pole_r=(0.42, 0.36, 1.18),
                pole_l=(-0.52, 0.16, 0.80),
                wrist_r=(1.0, -3.0, -1.0),
                root_y=0.035,
            ),
            "follow": _pose(
                body=(-0.016, 0.044, -0.090),
                pelvis=(-13.0, 9.0, -3.0),
                spine=(-10.0, 7.0, -2.0),
                spine_mid=(-8.0, 6.0, -2.0),
                chest=(-7.0, 6.0, -2.0),
                neck=(6.0, -4.0, 1.0),
                head=(6.0, -4.0, 1.0),
                shoulder_r=(-5.0, 5.0, -7.0),
                shoulder_l=(1.0, 0.0, 2.0),
                hand_r=(0.02, 0.63, 0.90),
                hand_l=(-0.46, 0.18, 0.86),
                pole_r=(0.32, 0.40, 1.00),
                pole_l=(-0.52, 0.12, 0.72),
                wrist_r=(3.0, -7.0, -2.0),
                root_y=0.060,
            ),
            "end": READY,
        },
    ),
    _clip(
        "authored_heavy_diagonal_top_heavy_v1",
        "ATTACK_HEAVY_ONE_HAND",
        "Heavy Diagonal Top-Heavy Strike",
        "TOP_HEAVY_ONE_HAND",
        ("AXE", "MACE"),
        {
            "start": READY,
            "anticipation": _pose(
                body=(0.025, -0.045, -0.115),
                pelvis=(5.0, -25.0, 5.0),
                spine=(5.0, -15.0, 3.0),
                spine_mid=(4.0, -13.0, 2.0),
                chest=(5.0, -14.0, 3.0),
                neck=(-2.0, 10.0, -1.0),
                head=(-2.0, 10.0, -1.0),
                shoulder_r=(1.0, -9.0, 9.0),
                shoulder_l=(0.0, 5.0, -4.0),
                hand_r=(0.33, -0.06, 1.33),
                hand_l=(-0.32, 0.25, 1.08),
                pole_r=(0.64, -0.01, 1.13),
                pole_l=(-0.47, 0.14, 0.84),
                wrist_r=(-5.0, 9.0, 3.0),
            ),
            "active_start": _pose(
                body=(0.018, -0.025, -0.108),
                pelvis=(1.0, -18.0, 3.0),
                spine=(1.0, -11.0, 2.0),
                spine_mid=(1.0, -9.0, 1.0),
                chest=(3.0, -9.0, 2.0),
                neck=(-1.0, 7.0, -1.0),
                head=(-1.0, 7.0, -1.0),
                shoulder_r=(0.0, -7.0, 8.0),
                hand_r=(0.31, 0.05, 1.32),
                hand_l=(-0.33, 0.22, 1.04),
                pole_r=(0.64, 0.08, 1.09),
                pole_l=(-0.48, 0.13, 0.82),
                wrist_r=(-4.0, 7.0, 2.0),
            ),
            "contact": _pose(
                body=(-0.010, 0.045, -0.078),
                pelvis=(-12.0, 10.0, -3.0),
                spine=(-9.0, 9.0, -2.0),
                spine_mid=(-7.0, 8.0, -2.0),
                chest=(-5.0, 9.0, -3.0),
                neck=(5.0, -6.0, 1.0),
                head=(5.0, -6.0, 1.0),
                shoulder_r=(-4.0, 7.0, -6.0),
                shoulder_l=(1.0, -3.0, 4.0),
                hand_r=(0.04, 0.72, 1.02),
                hand_l=(-0.42, 0.25, 0.95),
                pole_r=(0.38, 0.34, 1.20),
                pole_l=(-0.52, 0.16, 0.78),
                wrist_r=(2.0, -4.0, -2.0),
                root_y=0.055,
            ),
            "follow": _pose(
                body=(-0.030, 0.052, -0.108),
                pelvis=(-15.0, 27.0, -6.0),
                spine=(-12.0, 17.0, -4.0),
                spine_mid=(-9.0, 15.0, -3.0),
                chest=(-8.0, 16.0, -4.0),
                neck=(7.0, -10.0, 2.0),
                head=(7.0, -9.0, 2.0),
                shoulder_r=(-4.0, 9.0, -6.0),
                shoulder_l=(1.0, 0.0, 2.0),
                hand_r=(-0.04, 0.32, 0.84),
                hand_l=(-0.46, 0.15, 0.82),
                pole_r=(0.18, 0.20, 1.00),
                pole_l=(-0.53, 0.10, 0.68),
                wrist_r=(4.0, -9.0, -3.0),
                root_y=0.085,
            ),
            "end": READY,
        },
    ),
    _clip(
        "authored_thrust_point_forward_v1",
        "ATTACK_THRUST_ONE_HAND",
        "One-Hand Point-Forward Thrust",
        "POINT_FORWARD",
        ("SWORD", "POLEARM"),
        {
            "start": READY,
            "anticipation": _pose(
                body=(0.006, -0.045, -0.088),
                pelvis=(-3.0, -13.0, 2.0),
                spine=(1.0, -7.0, 1.0),
                spine_mid=(2.0, -6.0, 1.0),
                chest=(3.0, -7.0, 1.0),
                neck=(-1.0, 5.0, -1.0),
                head=(-1.0, 5.0, -1.0),
                shoulder_r=(0.0, -6.0, 3.0),
                shoulder_l=(0.0, 3.0, -2.0),
                hand_r=(0.20, 0.08, 1.08),
                hand_l=(-0.30, 0.24, 1.12),
                pole_r=(0.55, 0.01, 0.94),
                pole_l=(-0.45, 0.15, 0.84),
                wrist_r=(-2.0, 4.0, 1.0),
            ),
            "active_start": _pose(
                body=(0.004, -0.018, -0.082),
                pelvis=(-5.0, -8.0, 1.0),
                spine=(-2.0, -4.0, 0.0),
                spine_mid=(-1.0, -3.0, 0.0),
                chest=(2.0, -3.0, 1.0),
                neck=(0.0, 2.0, 0.0),
                head=(0.0, 2.0, 0.0),
                shoulder_r=(-1.0, -3.0, 2.0),
                hand_r=(0.20, 0.22, 1.11),
                hand_l=(-0.31, 0.25, 1.11),
                pole_r=(0.56, 0.13, 0.95),
                pole_l=(-0.46, 0.16, 0.82),
                wrist_r=(-1.0, 2.0, 1.0),
            ),
            "contact": _pose(
                body=(0.0, 0.060, -0.062),
                pelvis=(-10.0, 5.0, -1.0),
                spine=(-7.0, 4.0, -1.0),
                spine_mid=(-5.0, 3.0, -1.0),
                chest=(-3.0, 4.0, -1.0),
                neck=(3.0, -3.0, 1.0),
                head=(3.0, -3.0, 1.0),
                shoulder_r=(-2.0, 5.0, -2.0),
                shoulder_l=(1.0, -2.0, 2.0),
                hand_r=(0.18, 0.735, 1.17),
                hand_l=(-0.43, 0.29, 1.02),
                pole_r=(0.38, 0.40, 1.10),
                pole_l=(-0.52, 0.18, 0.78),
                wrist_r=(0.0, -1.0, 0.0),
                root_y=0.095,
            ),
            "follow": _pose(
                body=(0.0, 0.078, -0.068),
                pelvis=(-11.0, 7.0, -2.0),
                spine=(-8.0, 6.0, -1.0),
                spine_mid=(-6.0, 5.0, -1.0),
                chest=(-4.0, 5.0, -1.0),
                neck=(4.0, -4.0, 1.0),
                head=(4.0, -4.0, 1.0),
                shoulder_r=(-3.0, 6.0, -3.0),
                shoulder_l=(1.0, -2.0, 2.0),
                hand_r=(0.18, 0.80, 1.16),
                hand_l=(-0.44, 0.25, 0.98),
                pole_r=(0.40, 0.50, 1.08),
                pole_l=(-0.53, 0.16, 0.74),
                wrist_r=(0.0, -2.0, 0.0),
                root_y=0.125,
            ),
            "end": READY,
        },
    ),
)

_CLIPS_BY_ID = {record["clipId"]: record for record in BUILTIN_CLIPS}


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def validate_clip_record(record: Mapping[str, Any]) -> list[str]:
    errors = []
    if record.get("schema") != AUTHORED_ATTACK_SCHEMA:
        errors.append(f"schema must be {AUTHORED_ATTACK_SCHEMA}.")
    clip_id = str(record.get("clipId", ""))
    if not clip_id:
        errors.append("clipId is required.")
    kind = str(record.get("actionKind", ""))
    if kind not in offensive_actions.OFFENSIVE_ACTION_VARIANTS:
        errors.append(f"Unknown actionKind {kind!r}.")
    if record.get("rigProfileId") != skin_and_bones.SBF_CANONICAL_RIG_VERSION:
        errors.append("rigProfileId must use the canonical Y+ humanoid.")
    if record.get("forwardAxis") != "+Y" or record.get("upAxis") != "+Z":
        errors.append("Authored clips must be +Y forward and +Z up.")
    stages = record.get("stages")
    if not isinstance(stages, Mapping):
        errors.append("stages must be an object.")
        return errors
    for name in ("start", "anticipation", "active_start", "contact", "follow", "end"):
        pose = stages.get(name)
        if not isinstance(pose, Mapping):
            errors.append(f"Missing {name} pose.")
            continue
        deprecated = sorted({"weapon_r", "weapon_l"}.intersection(pose))
        if deprecated:
            errors.append(
                f"{name} contains deprecated weapon-direction data: "
                + ", ".join(deprecated)
                + ". Body animation must be socket-independent."
            )
        for field, value in pose.items():
            values = value if isinstance(value, (tuple, list)) else (value,)
            if any(not _finite(component) for component in values):
                errors.append(f"{name}.{field} contains a non-finite value.")
        for field in ("wrist_r", "wrist_l"):
            value = pose.get(field)
            if not isinstance(value, (tuple, list)) or len(value) != 3:
                errors.append(f"{name}.{field} must contain three bounded angles.")
            elif any(abs(float(component)) > 15.0 for component in value):
                errors.append(f"{name}.{field} exceeds the 15-degree authored wrist limit.")
    if kind == "ATTACK_THRUST_ONE_HAND":
        families = set(record.get("previewWeaponFamilies", ()))
        if "AXE" in families or "MACE" in families:
            errors.append("Thrust cannot use axe or mace mechanics.")
    return errors


def discover_clips(root="", attack_filter="ALL", mechanics_filter="ALL"):
    """Return built-ins plus valid JSON manifests from an optional library root."""

    catalog = {
        str(record["clipId"]): deepcopy(record)
        for record in BUILTIN_CLIPS
    }
    root_text = str(root or "").strip()
    if root_text:
        path = Path(bpy.path.abspath(root_text)).expanduser()
        if path.is_dir():
            for manifest in sorted(path.glob("*.authored_attack.json")):
                try:
                    value = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if not validate_clip_record(value):
                    record = deepcopy(value)
                    record["manifestPath"] = str(manifest)
                    clip_id = str(record["clipId"])
                    # A local manifest may add a new authored base, but it may
                    # not silently replace one of the shipped reviewed bases.
                    if clip_id not in catalog:
                        catalog[clip_id] = record
    _CLIPS_BY_ID.clear()
    _CLIPS_BY_ID.update(catalog)
    result = []
    for record in catalog.values():
        if attack_filter != "ALL" and record.get("actionKind") != attack_filter:
            continue
        if mechanics_filter != "ALL" and record.get("mechanicsFamily") != mechanics_filter:
            continue
        result.append(record)
    return result


def browser_records(context):
    """Return the currently filtered, previewable authored-base catalog."""

    settings = context.scene.daf_settings
    records = discover_clips(
        getattr(settings, "authored_attack_library_root", ""),
        getattr(settings, "authored_attack_filter_kind", "ALL"),
        "ALL",
    )
    weapon_filter = str(getattr(settings, "authored_attack_filter_weapon", "ALL"))
    if weapon_filter != "ALL":
        records = [
            record
            for record in records
            if weapon_filter in set(record.get("previewWeaponFamilies", ()))
        ]
    return records


def resolve_runtime_armature(context, *, prepare=False):
    value = context.scene.objects.get(RUNTIME_ARMATURE_NAME)
    if value is None or value.type != 'ARMATURE':
        candidates = [obj.name for obj in context.scene.objects if obj.type == 'ARMATURE']
        raise RuntimeError(
            f"Authored attacks require game-ready armature '{RUNTIME_ARMATURE_NAME}'; found "
            + (", ".join(candidates) if candidates else "none")
            + "."
        )
    skin_and_bones.require_canonical_yplus(value, label="Authored attack preview")
    if prepare:
        source = context.scene.objects.get(SOURCE_ARMATURE_NAME)
        if source is not None and source is not value:
            source.hide_viewport = True
            try:
                source.hide_set(True)
            except RuntimeError:
                pass
        value.hide_viewport = False
        value.hide_set(False)
        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                pass
        bpy.ops.object.select_all(action='DESELECT')
        value.select_set(True)
        context.view_layer.objects.active = value
        context.view_layer.update()
    return value


def _armature(context):
    return resolve_runtime_armature(context, prepare=True)


def _slot_action(armature, action):
    animation_data = armature.animation_data_create()
    animation_data.action = action
    slots = list(getattr(action, "slots", ()))
    if slots and hasattr(animation_data, "action_slot"):
        suitable = next((slot for slot in slots if slot.target_id_type == armature.id_type), slots[0])
        animation_data.action_slot = suitable


def _new_action(armature, name):
    action = bpy.data.actions.new(name=name)
    slots = getattr(action, "slots", None)
    if slots is not None and hasattr(slots, "new"):
        try:
            slots.new(armature.id_type, armature.name)
        except (RuntimeError, TypeError, ValueError):
            pass
    _slot_action(armature, action)
    return action


def _preview_session_key(context):
    return int(context.scene.as_pointer())


def _begin_preview_session(context, armature):
    key = _preview_session_key(context)
    if key in _PREVIEW_SESSIONS:
        return
    animation_data = armature.animation_data
    previous = animation_data.action if animation_data is not None else None
    if previous is not None and bool(previous.get(AUTHORED_PREVIEW_PROPERTY, False)):
        previous = None
    _PREVIEW_SESSIONS[key] = {
        "armature": armature.name,
        "action": previous.name if previous is not None else "",
        "frame": int(context.scene.frame_current),
        "frameStart": int(context.scene.frame_start),
        "frameEnd": int(context.scene.frame_end),
    }


def _discard_preview_session(context):
    _PREVIEW_SESSIONS.pop(_preview_session_key(context), None)


def _restore_preview_session(context):
    session = _PREVIEW_SESSIONS.pop(_preview_session_key(context), None)
    if not session:
        return
    armature = context.scene.objects.get(str(session["armature"]))
    if armature is not None and armature.type == 'ARMATURE':
        action = bpy.data.actions.get(str(session["action"]))
        if action is None:
            armature.animation_data_create().action = None
        else:
            _slot_action(armature, action)
    context.scene.frame_start = int(session["frameStart"])
    context.scene.frame_end = int(session["frameEnd"])
    context.scene.frame_set(int(session["frame"]))
    context.view_layer.update()


def _reset_pose(armature):
    for bone in armature.pose.bones:
        bone.rotation_mode = 'QUATERNION'
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)


def _world_offset(pose_bone, value):
    delta = Vector(value)
    pose_bone.location = pose_bone.bone.matrix_local.to_3x3().inverted() @ delta


def _rotate_world(pose_bone, axis, degrees):
    if abs(float(degrees)) <= 1.0e-7:
        return
    local = pose_bone.bone.matrix_local.to_3x3().inverted() @ Vector(axis)
    pose_bone.rotation_quaternion = (
        Quaternion(local.normalized(), math.radians(float(degrees)))
        @ pose_bone.rotation_quaternion
    )


def _apply_rotation(pose_bone, value):
    pitch, yaw, roll = (float(component) for component in value)
    _rotate_world(pose_bone, (1.0, 0.0, 0.0), pitch)
    _rotate_world(pose_bone, (0.0, 0.0, 1.0), yaw)
    _rotate_world(pose_bone, (0.0, 1.0, 0.0), roll)


def _two_bone_joint(root, target, first_length, second_length, pole):
    root = Vector(root)
    target = Vector(target)
    pole = Vector(pole)
    delta = target - root
    distance = delta.length
    maximum = max(1.0e-6, float(first_length) + float(second_length) - 1.0e-4)
    minimum = abs(float(first_length) - float(second_length)) + 1.0e-4
    if distance <= 1.0e-8:
        delta = Vector((0.0, 1.0, 0.0))
        distance = minimum
    axis = delta.normalized()
    distance = min(max(distance, minimum), maximum)
    target = root + axis * distance
    along = (
        float(first_length) ** 2 - float(second_length) ** 2 + distance ** 2
    ) / (2.0 * distance)
    height = math.sqrt(max(0.0, float(first_length) ** 2 - along ** 2))
    pole_direction = pole - root
    perpendicular = pole_direction - axis * pole_direction.dot(axis)
    if perpendicular.length <= 1.0e-8:
        perpendicular = axis.cross(Vector((0.0, 0.0, 1.0)))
    if perpendicular.length <= 1.0e-8:
        perpendicular = axis.cross(Vector((1.0, 0.0, 0.0)))
    joint = root + axis * along + perpendicular.normalized() * height
    return joint, target


def _rotation_for_direction(pose_bone, direction):
    direction = Vector(direction).normalized()
    rest = pose_bone.bone.matrix_local.to_3x3().normalized()
    rest_y = rest.col[1].normalized()
    swing = rest_y.rotation_difference(direction)
    return (swing.to_matrix() @ rest).normalized()


def _set_segment(pose_bone, head, tail):
    matrix = _rotation_for_direction(pose_bone, Vector(tail) - Vector(head)).to_4x4()
    matrix.translation = Vector(head)
    pose_bone.matrix = matrix
    return matrix.to_3x3().normalized()


def _set_limb(
    armature,
    mapping,
    side,
    target,
    pole,
    wrist_rotation,
):
    upper = armature.pose.bones[mapping[f"upper_arm_{side}"]]
    lower = armature.pose.bones[mapping[f"lower_arm_{side}"]]
    hand = armature.pose.bones[mapping[f"hand_{side}"]]
    shoulder = Vector(upper.head)
    elbow, wrist = _two_bone_joint(
        shoulder,
        target,
        upper.length,
        lower.length,
        pole,
    )
    _set_segment(upper, shoulder, elbow)
    bpy.context.view_layer.update()
    lower_rotation = _set_segment(lower, elbow, wrist)
    bpy.context.view_layer.update()
    relative_hand = (
        lower.bone.matrix_local.to_3x3().inverted()
        @ hand.bone.matrix_local.to_3x3()
    )
    hand_rotation = (lower_rotation @ relative_hand).normalized()
    for axis, degrees in zip(((1, 0, 0), (0, 1, 0), (0, 0, 1)), wrist_rotation):
        if abs(float(degrees)) > 1.0e-7:
            hand_rotation = (
                hand_rotation
                @ Quaternion(Vector(axis), math.radians(float(degrees))).to_matrix()
            ).normalized()
    matrix = hand_rotation.to_4x4()
    matrix.translation = wrist
    hand.matrix = matrix
    bpy.context.view_layer.update()


def _set_leg(armature, mapping, side, ankle, pole):
    thigh = armature.pose.bones[mapping[f"thigh_{side}"]]
    shin = armature.pose.bones[mapping[f"shin_{side}"]]
    foot = armature.pose.bones[mapping[f"foot_{side}"]]
    hip = Vector(thigh.head)
    knee, ankle = _two_bone_joint(hip, ankle, thigh.length, shin.length, pole)
    _set_segment(thigh, hip, knee)
    bpy.context.view_layer.update()
    _set_segment(shin, knee, ankle)
    bpy.context.view_layer.update()
    matrix = foot.bone.matrix_local.to_3x3().normalized().to_4x4()
    matrix.translation = ankle
    foot.matrix = matrix
    bpy.context.view_layer.update()


# Offsets are dimensionless fractions of each leg's own bind-chain length.
# They preserve the authored lead-foot silhouette while adapting it to the
# target character's rest footprint and proportions.
_STANCE_OFFSET_RATIOS = {
    False: {
        "r": (0.046684, -0.109673),
        "l": (-0.058163, 0.200226),
    },
    True: {
        "r": (0.046684, 0.200967),
        "l": (-0.058163, -0.112111),
    },
}
MIN_PLANTED_KNEE_BEND_DEGREES = 12.0
MAX_FOOT_PLANT_PELVIS_DROP_RATIO = 0.05
STANCE_FIT_SCAN_STEPS = 128
STANCE_FIT_REFINEMENT_STEPS = 24


def _planted_foot_anchors(armature, mapping, mirror=False):
    """Return fixed, rig-relative FK foot landmarks for one authored bake."""

    ratios = _STANCE_OFFSET_RATIOS[bool(mirror)]
    anchors = {}
    for side in ("r", "l"):
        foot = armature.data.bones[mapping[f"foot_{side}"]]
        thigh = armature.data.bones[mapping[f"thigh_{side}"]]
        shin = armature.data.bones[mapping[f"shin_{side}"]]
        chain_length = float(thigh.length) + float(shin.length)
        lateral, forward = ratios[side]
        anchor = Vector(foot.head_local)
        anchor.x += lateral * chain_length
        anchor.y += forward * chain_length
        anchors[side] = anchor
    return anchors


def _apply_body_pose(armature, mapping, pose):
    root = armature.pose.bones[mapping["root"]]
    body = armature.pose.bones[mapping["hips"]]
    _world_offset(root, (0.0, pose["root_y"], 0.0))
    _world_offset(body, pose["body"])
    for role in (
        "hips", "spine", "spine_mid", "chest", "neck", "head",
        "shoulder_r", "shoulder_l",
    ):
        pose_role = role if role != "hips" else "pelvis"
        _apply_rotation(armature.pose.bones[mapping[role]], pose[pose_role])
    bpy.context.view_layer.update()


def _fit_planted_foot_anchors(context, armature, mapping, stages, schedule, anchors):
    """Fit a planted stance with bounded baked pelvis compensation."""

    bind = {
        side: Vector(armature.data.bones[mapping[f"foot_{side}"]].head_local)
        for side in ("r", "l")
    }
    limits = {}
    for side in ("r", "l"):
        thigh = armature.data.bones[mapping[f"thigh_{side}"]]
        shin = armature.data.bones[mapping[f"shin_{side}"]]
        thigh_length = float(thigh.length)
        shin_length = float(shin.length)
        maximum = math.sqrt(
            thigh_length * thigh_length
            + shin_length * shin_length
            + 2.0
            * thigh_length
            * shin_length
            * math.cos(math.radians(MIN_PLANTED_KNEE_BEND_DEGREES))
        )
        limits[side] = (
            abs(thigh_length - shin_length) + 0.001,
            maximum,
        )

    hip_samples = {"r": [], "l": []}
    for frame in range(schedule["start"], schedule["end"] + 1):
        context.scene.frame_set(frame)
        _reset_pose(armature)
        pose = _pose_at_frame(stages, schedule, frame)
        _apply_body_pose(armature, mapping, pose)
        for side in ("r", "l"):
            thigh = armature.pose.bones[mapping[f"thigh_{side}"]]
            hip_samples[side].append(Vector(thigh.head))

    shortest_chain = min(
        float(armature.data.bones[mapping[f"thigh_{side}"]].length)
        + float(armature.data.bones[mapping[f"shin_{side}"]].length)
        for side in ("r", "l")
    )
    maximum_drop = shortest_chain * MAX_FOOT_PLANT_PELVIS_DROP_RATIO

    def fit_for_stance(factor):
        fitted = {
            side: bind[side].lerp(anchors[side], factor)
            for side in ("r", "l")
        }
        drops = []
        for index in range(len(hip_samples["r"])):
            required_drop = 0.0
            for side in ("r", "l"):
                hip = hip_samples[side][index]
                ankle = fitted[side]
                horizontal_squared = (
                    (float(hip.x) - float(ankle.x)) ** 2
                    + (float(hip.y) - float(ankle.y)) ** 2
                )
                minimum, maximum = limits[side]
                if horizontal_squared >= maximum * maximum:
                    return None
                vertical_limit = math.sqrt(maximum * maximum - horizontal_squared)
                required_drop = max(
                    required_drop,
                    max(0.0, float(hip.z) - float(ankle.z) - vertical_limit),
                )
            if required_drop > maximum_drop:
                return None
            for side in ("r", "l"):
                hip = hip_samples[side][index] - Vector((0.0, 0.0, required_drop))
                distance = (hip - fitted[side]).length
                minimum, maximum = limits[side]
                if not minimum <= distance <= maximum + 1.0e-6:
                    return None
            drops.append(required_drop)
        return fitted, drops

    bind_fit = fit_for_stance(0.0)
    if bind_fit is None:
        raise RuntimeError(
            "Authored body motion needs an explicit foot release/step for this rig; "
            "bounded planted-foot compensation is insufficient."
        )
    full_fit = fit_for_stance(1.0)
    if full_fit is not None:
        fitted, pelvis_drops = full_fit
        stance_fit_scale = 1.0
    else:
        # Feasibility is normally monotone as the authored stance expands, but
        # the minimum reach of a very uneven thigh/shin pair can create a small
        # non-monotone interval. Scan from the authored stance toward bind first
        # so unusual humanoid proportions do not get an unnecessarily narrow
        # stance, then refine only the highest feasible interval found.
        low = 0.0
        high = 1.0
        best = bind_fit
        for scan_index in range(STANCE_FIT_SCAN_STEPS - 1, -1, -1):
            factor = scan_index / STANCE_FIT_SCAN_STEPS
            candidate = fit_for_stance(factor)
            if candidate is not None:
                low = factor
                high = min(1.0, factor + 1.0 / STANCE_FIT_SCAN_STEPS)
                best = candidate
                break
        for _index in range(STANCE_FIT_REFINEMENT_STEPS):
            factor = (low + high) * 0.5
            candidate = fit_for_stance(factor)
            if candidate is None:
                high = factor
            else:
                low = factor
                best = candidate
        fitted, pelvis_drops = best
        stance_fit_scale = low

    _reset_pose(armature)
    context.view_layer.update()
    return fitted, pelvis_drops, stance_fit_scale, maximum_drop


def _smooth(value):
    value = min(1.0, max(0.0, float(value)))
    return value * value * (3.0 - 2.0 * value)


def _lerp_value(first, second, value):
    factor = _smooth(value)
    if isinstance(first, (tuple, list)):
        return tuple(
            float(a) + (float(b) - float(a)) * factor
            for a, b in zip(first, second)
        )
    return float(first) + (float(second) - float(first)) * factor


def _lerp_pose(first, second, value):
    return {key: _lerp_value(first[key], second[key], value) for key in first}


def _mirror_pose(pose):
    result = deepcopy(dict(pose))
    result["body"] = (-pose["body"][0], pose["body"][1], pose["body"][2])
    for role in ("pelvis", "spine", "spine_mid", "chest", "neck", "head"):
        pitch, yaw, roll = pose[role]
        result[role] = (pitch, -yaw, -roll)
    for target in ("hand", "pole"):
        right = pose[f"{target}_r"]
        left = pose[f"{target}_l"]
        result[f"{target}_r"] = (-left[0], left[1], left[2])
        result[f"{target}_l"] = (-right[0], right[1], right[2])
    for role in ("shoulder", "wrist"):
        right = pose[f"{role}_r"]
        left = pose[f"{role}_l"]
        result[f"{role}_r"] = (left[0], -left[1], -left[2])
        result[f"{role}_l"] = (right[0], -right[1], -right[2])
    return result


def _clamp_macro(name, value):
    minimum, maximum = MACRO_LIMITS[name]
    return min(maximum, max(minimum, float(value)))


def default_macros():
    return {
        "anticipation": 1.0,
        "strike": 1.0,
        "follow_through": 1.0,
        "torso": 1.0,
        "reach": 1.0,
        "elbow": 1.0,
        "wrist": 1.0,
        "stance": 1.0,
        "speed": 1.0,
        "mirror": False,
        "root_policy": "IN_PLACE",
    }


def _adjust_pose(pose, stage, macros):
    result = deepcopy(dict(pose))
    strength_name = {
        "anticipation": "anticipation",
        "active_start": "anticipation",
        "contact": "strike",
        "follow": "follow_through",
    }.get(stage)
    if strength_name:
        strength = macros[strength_name]
        for key in result:
            if key == "root_y":
                continue
            elif isinstance(result[key], tuple):
                base = READY[key]
                result[key] = tuple(
                    float(a) + (float(b) - float(a)) * strength
                    for a, b in zip(base, result[key])
                )
    for role in ("pelvis", "spine", "spine_mid", "chest", "neck", "head"):
        result[role] = tuple(float(v) * macros["torso"] for v in result[role])
    body = result["body"]
    result["body"] = (body[0], body[1], body[2] * macros["stance"])
    for side in ("r", "l"):
        wrist = result[f"wrist_{side}"]
        result[f"wrist_{side}"] = tuple(float(v) * macros["wrist"] for v in wrist)
    hand = result["hand_r"]
    ready = READY["hand_r"]
    result["hand_r"] = (
        ready[0] + (hand[0] - ready[0]) * macros["reach"],
        ready[1] + (hand[1] - ready[1]) * macros["reach"],
        ready[2] + (hand[2] - ready[2]) * macros["reach"],
    )
    elbow_delta = macros["elbow"] - 1.0
    result["hand_r"] = (
        result["hand_r"][0],
        result["hand_r"][1] - elbow_delta * 0.06,
        result["hand_r"][2],
    )
    if macros["root_policy"] != "AUTHORED_ROOT_MOTION":
        result["root_y"] = 0.0
    if macros["mirror"]:
        result = _mirror_pose(result)
    return result


def _schedule(record, fps, speed):
    variant = deepcopy(offensive_actions.OFFENSIVE_ACTION_VARIANTS[record["actionKind"]])
    for field in ("windupSeconds", "activeSeconds", "recoverySeconds"):
        variant[field] = float(variant[field]) / speed
    metadata, schedule = offensive_actions.phase_metadata(variant, fps)
    schedule["anticipation"] = max(schedule["start"] + 1, schedule["activeStart"] - 1)
    schedule["contact"] = min(
        schedule["activeEnd"] - 1,
        schedule["activeStart"]
        + max(1, round((schedule["activeEnd"] - schedule["activeStart"]) * 0.55)),
    )
    metadata["rootMotionPolicy"] = "IN_PLACE"
    return metadata, schedule


def _stage_frames(schedule):
    return (
        (schedule["start"], "start"),
        (schedule["anticipation"], "anticipation"),
        (schedule["activeStart"], "active_start"),
        (schedule["contact"], "contact"),
        (schedule["activeEnd"], "follow"),
        (schedule["end"], "end"),
    )


def _pose_at_frame(stages, schedule, frame):
    keys = _stage_frames(schedule)
    if frame <= keys[0][0]:
        return stages[keys[0][1]]
    for (first_frame, first_name), (second_frame, second_name) in zip(keys, keys[1:]):
        if frame <= second_frame:
            span = max(1, second_frame - first_frame)
            return _lerp_pose(
                stages[first_name],
                stages[second_name],
                (frame - first_frame) / span,
            )
    return stages[keys[-1][1]]


def _key_fk_pose(armature, mapping, frame, previous):
    for name in dict.fromkeys(mapping.values()):
        bone = armature.pose.bones.get(name)
        if bone is None:
            continue
        quaternion = bone.rotation_quaternion.normalized()
        old = previous.get(name)
        if old is not None:
            quaternion.make_compatible(old)
            bone.rotation_quaternion = quaternion
        previous[name] = quaternion.copy()
        bone.keyframe_insert("rotation_quaternion", frame=frame, group=name)
        # The production deform hierarchy is intentionally non-connected in a
        # few chains.  Assigning an evaluated FK matrix can therefore produce
        # a small parent-space offset as well as a rotation.  Bake that offset
        # instead of silently losing the authored wrist/ankle landmark.
        bone.keyframe_insert("location", frame=frame, group=name)


def _set_markers(action, schedule):
    for marker in tuple(action.pose_markers):
        action.pose_markers.remove(marker)
    for name, field in zip(
        REQUIRED_MARKERS,
        ("start", "anticipation", "activeStart", "contact", "activeEnd", "end"),
    ):
        marker = action.pose_markers.new(name)
        marker.frame = int(schedule[field])


def _set_linear_dense_curves(action):
    for curve in animation_library.iter_action_fcurves(action):
        for point in curve.keyframe_points:
            point.interpolation = 'BEZIER'
            point.handle_left_type = 'AUTO_CLAMPED'
            point.handle_right_type = 'AUTO_CLAMPED'


def _assert_baked_plant_invariants(
    context,
    armature,
    mapping,
    action,
    stages,
    schedule,
    ankles,
):
    """Re-evaluate the completed FK Action before exposing the preview."""

    _slot_action(armature, action)
    root = armature.pose.bones[mapping["root"]]
    root_bind_head = Vector(root.bone.head_local)
    knee_tolerance = 0.25
    for frame in range(schedule["start"], schedule["end"] + 1):
        context.scene.frame_set(frame)
        context.view_layer.update()
        expected_root_y = float(_pose_at_frame(stages, schedule, frame)["root_y"])
        root_offset = Vector(root.head) - root_bind_head
        if (
            abs(float(root_offset.x)) > 0.0005
            or abs(float(root_offset.y) - expected_root_y) > 0.0005
            or abs(float(root_offset.z)) > 0.0005
        ):
            raise RuntimeError(
                f"Authored root travel changed during FK bake at frame {frame}."
            )
        for side in ("r", "l"):
            thigh = armature.pose.bones[mapping[f"thigh_{side}"]]
            shin = armature.pose.bones[mapping[f"shin_{side}"]]
            foot = armature.pose.bones[mapping[f"foot_{side}"]]
            if (Vector(foot.head) - Vector(ankles[side])).length > 0.004:
                raise RuntimeError(
                    f"Authored {side} foot drifted after FK bake at frame {frame}."
                )
            upper = (Vector(thigh.head) - Vector(shin.head)).normalized()
            lower = (Vector(foot.head) - Vector(shin.head)).normalized()
            internal = math.degrees(upper.angle(lower))
            bend = 180.0 - internal
            if bend + knee_tolerance < MIN_PLANTED_KNEE_BEND_DEGREES:
                raise RuntimeError(
                    f"Authored {side} knee lost its planted bend after FK bake "
                    f"at frame {frame}."
                )


def bake_builtin_action(context, clip_id, *, macros=None, action_name=""):
    record = _CLIPS_BY_ID.get(str(clip_id))
    if record is None:
        raise RuntimeError(f"Unknown authored attack clip {clip_id!r}.")
    errors = validate_clip_record(record)
    if errors:
        raise RuntimeError("Invalid authored attack base: " + " ".join(errors))
    values = default_macros()
    values.update(dict(macros or {}))
    for name in MACRO_LIMITS:
        values[name] = _clamp_macro(name, values[name])
    values["mirror"] = bool(values.get("mirror", False))
    values["root_policy"] = str(values.get("root_policy", "IN_PLACE"))
    if values["root_policy"] not in offensive_actions.ROOT_MOTION_POLICIES:
        raise RuntimeError("root_policy must be IN_PLACE or AUTHORED_ROOT_MOTION.")

    armature = resolve_runtime_armature(context, prepare=False)
    _begin_preview_session(context, armature)
    armature = _armature(context)
    mapping = skin_and_bones.require_canonical_yplus(
        armature, label="Authored attack bake"
    )["roleMapping"]
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    metadata, schedule = _schedule(record, fps, values["speed"])
    metadata["compatibleWeaponClasses"] = list(record["compatibleWeaponClasses"])
    metadata["rootMotionPolicy"] = values["root_policy"]
    if values["mirror"]:
        metadata["socketRole"] = "MAIN_HAND_L"
        if metadata["attackFamily"] == "SLASH_RIGHT_TO_LEFT":
            metadata["attackFamily"] = "SLASH_LEFT_TO_RIGHT"
        elif metadata["attackFamily"] == "SLASH_LEFT_TO_RIGHT":
            metadata["attackFamily"] = "SLASH_RIGHT_TO_LEFT"

    remove_preview_action()
    name = action_name or PREVIEW_ACTION_PREFIX + record["actionKind"]
    action = _new_action(armature, name)
    action[AUTHORED_PREVIEW_PROPERTY] = True
    context.scene.frame_start = schedule["start"]
    context.scene.frame_end = schedule["end"]
    stages = {
        name: _adjust_pose(pose, name, values)
        for name, pose in record["stages"].items()
    }
    _reset_pose(armature)
    context.view_layer.update()
    foot_fit = _fit_planted_foot_anchors(
        context,
        armature,
        mapping,
        stages,
        schedule,
        _planted_foot_anchors(armature, mapping, values["mirror"]),
    )
    ankles = foot_fit[0]
    pelvis_drops = tuple(float(value) for value in foot_fit[1])
    stance_fit_scale = float(foot_fit[2])
    foot_plant_drop_limit = float(foot_fit[3])
    maximum_plant_drop = max(pelvis_drops, default=0.0)
    root_motion_scale = 1.0
    context.scene.frame_set(schedule["start"])
    _reset_pose(armature)
    context.view_layer.update()
    bake_options = anim_utils.BakeOptions(
        only_selected=False,
        do_pose=True,
        do_object=False,
        do_visual_keying=True,
        do_constraint_clear=False,
        do_parents_clear=False,
        do_clean=False,
        do_location=True,
        do_rotation=True,
        do_scale=False,
        do_bbone=False,
        do_custom_props=False,
    )
    bake_iterator = anim_utils.bake_action_iter(
        armature,
        action=action,
        bake_options=bake_options,
    )
    bake_iterator.send(None)
    for frame in range(schedule["start"], schedule["end"] + 1):
        context.scene.frame_set(frame)
        _reset_pose(armature)
        pose = _pose_at_frame(stages, schedule, frame)
        pelvis_drop = pelvis_drops[frame - schedule["start"]]
        if pelvis_drop > 0.0:
            pose = dict(pose)
            body = pose["body"]
            pose["body"] = (body[0], body[1], body[2] - pelvis_drop)
        _apply_body_pose(armature, mapping, pose)
        _set_leg(
            armature,
            mapping,
            "r",
            ankles["r"],
            (0.34, 0.48 + pose["root_y"], 0.42),
        )
        _set_leg(
            armature,
            mapping,
            "l",
            ankles["l"],
            (-0.34, 0.48 + pose["root_y"], 0.42),
        )
        for side in ("r", "l"):
            _set_limb(
                armature,
                mapping,
                side,
                pose[f"hand_{side}"],
                pose[f"pole_{side}"],
                pose[f"wrist_{side}"],
            )
        context.view_layer.update()
        for side, ankle in ankles.items():
            foot = armature.pose.bones[mapping[f"foot_{side}"]]
            if (Vector(foot.head) - Vector(ankle)).length > 0.004:
                raise RuntimeError(
                    f"Authored {side} foot failed its planted FK landmark at frame {frame}."
                )
        bake_iterator.send(frame)

    baked = bake_iterator.send(None)
    if baked != action:
        raise RuntimeError("Blender visual FK bake returned an unexpected Action.")

    _assert_baked_plant_invariants(
        context,
        armature,
        mapping,
        action,
        stages,
        schedule,
        ankles,
    )

    _set_markers(action, schedule)
    _set_linear_dense_curves(action)
    source_label = (
        "AUTHORED_MANIFEST"
        if record.get("manifestPath")
        else "BUILTIN_HAND_AUTHORED_BASE"
    )
    authored = {
        "schema": AUTHORED_ATTACK_SCHEMA,
        "clipId": record["clipId"],
        "title": record["title"],
        "actionKind": record["actionKind"],
        "mechanicsFamily": record["mechanicsFamily"],
        "previewWeaponFamilies": list(record["previewWeaponFamilies"]),
        "rigProfileId": record["rigProfileId"],
        "semanticBoneMapping": dict(mapping),
        "mirror": values["mirror"],
        "speed": values["speed"],
        "rootPolicy": values["root_policy"],
        "rootMotionScale": root_motion_scale,
        "stanceFitScale": stance_fit_scale,
        "footPlantPelvisDropMax": maximum_plant_drop,
        "footPlantPelvisDropLimit": foot_plant_drop_limit,
        "macros": {name: values[name] for name in MACRO_LIMITS if name != "speed"},
        "source": source_label,
        "targetOrContactGeometryRequired": False,
    }
    if record.get("manifestPath"):
        authored["sourceManifest"] = str(record["manifestPath"])
    action[AUTHORED_ATTACK_PROPERTY] = json.dumps(authored, sort_keys=True, separators=(",", ":"))
    action["dsb_draft_kind"] = record["actionKind"]
    action["dsb_root_motion_policy"] = values["root_policy"]
    action["dsb_authored_root_motion_scale"] = root_motion_scale
    action["dsb_authored_stance_fit_scale"] = stance_fit_scale
    action["dsb_authored_foot_plant_drop_max"] = maximum_plant_drop
    offensive_actions.stamp_offensive_metadata(action, metadata)
    action["dsb_offensive_previewed"] = True
    action["dsb_offensive_preview_count"] = 1
    _slot_action(armature, action)
    context.scene.frame_set(schedule["anticipation"])
    report = validate_action(context, armature, action, require_approved=False)
    action["dsb_authored_attack_validation_status"] = report["status"]
    action["dsb_authored_attack_validation_json"] = json.dumps(report, sort_keys=True)
    if report["status"] != "PASS":
        raise RuntimeError("Authored attack bake failed: " + "; ".join(report["errors"]))
    return action


def remove_preview_action():
    for action in tuple(bpy.data.actions):
        if bool(action.get(AUTHORED_PREVIEW_PROPERTY, False)):
            for armature in (obj for obj in bpy.data.objects if obj.type == 'ARMATURE'):
                animation_data = armature.animation_data
                if animation_data and animation_data.action == action:
                    animation_data.action = None
            bpy.data.actions.remove(action)


def _settings_macros(settings):
    return {
        "anticipation": getattr(settings, "authored_attack_anticipation", 1.0),
        "strike": getattr(settings, "authored_attack_strike", 1.0),
        "follow_through": getattr(settings, "authored_attack_follow_through", 1.0),
        "torso": getattr(settings, "authored_attack_torso", 1.0),
        "reach": getattr(settings, "authored_attack_reach", 1.0),
        "elbow": getattr(settings, "authored_attack_elbow", 1.0),
        "wrist": getattr(settings, "authored_attack_wrist", 1.0),
        "stance": getattr(settings, "authored_attack_stance", 1.0),
        "speed": getattr(settings, "authored_attack_speed", 1.0),
        "mirror": getattr(settings, "authored_attack_mirror", False),
        "root_policy": getattr(settings, "authored_attack_root_policy", "IN_PLACE"),
    }


def refresh_library(context):
    settings = context.scene.daf_settings
    records = browser_records(context)
    selected = str(getattr(settings, "authored_attack_active_clip_id", ""))
    if not any(record["clipId"] == selected for record in records):
        selected = records[0]["clipId"] if records else ""
        if hasattr(settings, "authored_attack_active_clip_id"):
            settings.authored_attack_active_clip_id = selected
    if hasattr(settings, "authored_attack_status"):
        settings.authored_attack_status = (
            f"{len(records)} authored base{'s' if len(records) != 1 else ''} available"
        )
    return records


def preview_clip(context, clip_id, mirror=False, speed=1.0, root_policy="IN_PLACE", **macros):
    if str(clip_id) not in _CLIPS_BY_ID:
        settings = context.scene.daf_settings
        discover_clips(getattr(settings, "authored_attack_library_root", ""))
    values = default_macros()
    values.update(macros)
    values.update({"mirror": mirror, "speed": speed, "root_policy": root_policy})
    return bake_builtin_action(context, clip_id, macros=values)


def preview_selected(context):
    settings = context.scene.daf_settings
    discover_clips(getattr(settings, "authored_attack_library_root", ""))
    clip_id = str(getattr(settings, "authored_attack_active_clip_id", ""))
    if not clip_id:
        records = refresh_library(context)
        if not records:
            raise RuntimeError("No authored attack bases are available.")
        clip_id = records[0]["clipId"]
    try:
        action = bake_builtin_action(context, clip_id, macros=_settings_macros(settings))
        weapon = str(getattr(settings, "authored_attack_preview_weapon", "NONE"))
        payload = json.loads(str(action[AUTHORED_ATTACK_PROPERTY]))
        compatible = tuple(str(value) for value in payload["previewWeaponFamilies"])
        if weapon != "NONE" and weapon not in compatible:
            weapon = compatible[0]
            if hasattr(settings, "authored_attack_preview_weapon"):
                settings.authored_attack_preview_weapon = weapon
        replace_preview_proxy(context, weapon)
        return action
    except Exception:
        clear_preview(context)
        raise


def accept_preview_as_draft(context):
    armature = _armature(context)
    preview = armature.animation_data.action if armature.animation_data else None
    if preview is None or not bool(preview.get(AUTHORED_PREVIEW_PROPERTY, False)):
        raise RuntimeError("Preview an authored attack before accepting it as a draft.")
    payload = json.loads(str(preview[AUTHORED_ATTACK_PROPERTY]))
    kind = str(payload["actionKind"])
    variant = offensive_actions.OFFENSIVE_ACTION_VARIANTS[kind]
    draft = preview.copy()
    draft.name = "DSB_DRAFT_Authored_" + variant["baseName"].removeprefix("DSB_")
    draft[AUTHORED_PREVIEW_PROPERTY] = False
    draft["dsb_draft_kind"] = kind
    draft.use_fake_user = True
    _slot_action(armature, draft)
    animation_library.mark_draft(draft, armature, context.scene.daf_settings, kind)
    report = validate_action(context, armature, draft, require_approved=False)
    if report["status"] != "PASS":
        raise RuntimeError("Authored draft is not exportable: " + "; ".join(report["errors"]))
    cleanup_transients(context, keep_action=draft)
    _discard_preview_session(context)
    return draft


def clear_preview(context):
    """Remove every owned preview Action/proxy/helper without touching drafts."""

    remove_owned_preview_proxies()
    remove_preview_action()
    cleanup_transients(context)
    _restore_preview_session(context)
    settings = getattr(context.scene, "daf_settings", None)
    if settings is not None and hasattr(settings, "authored_attack_status"):
        settings.authored_attack_status = "AUTHORED PREVIEW CLEARED"


def finalize_draft(context, armature, action):
    runtime_armature = resolve_runtime_armature(context, prepare=False)
    if armature is not runtime_armature:
        raise RuntimeError("Authored attacks may only be finalized on DSB_DAMAGE_RIG.")
    report = validate_action(context, armature, action, require_approved=False)
    if report["status"] != "PASS":
        raise RuntimeError("Authored draft is not exportable: " + "; ".join(report["errors"]))
    from . import approval_base_name, next_approved_version_name

    kind = str(action.get("dsb_draft_kind", action.get("dsb_approved_kind", "ATTACK")))
    action.name = next_approved_version_name(
        approval_base_name(context.scene.daf_settings, kind)
    )
    result = animation_library.mark_approved(
        action,
        armature,
        context.scene.daf_settings,
        kind,
    )
    result["dsb_offensive_previewed_before_approval"] = True
    approved_report = validate_action(
        context,
        armature,
        result,
        require_approved=True,
    )
    if approved_report["status"] != "PASS":
        raise RuntimeError(
            "Authored animation approval produced a non-exportable Action: "
            + "; ".join(approved_report["errors"])
        )
    cleanup_transients(context, keep_action=result)
    _discard_preview_session(context)
    return result


def validate_action(context, armature, action, require_approved=False):
    errors = []
    try:
        runtime_armature = resolve_runtime_armature(context, prepare=False)
        if armature is not runtime_armature:
            errors.append("Authored Action target must be DSB_DAMAGE_RIG.")
    except RuntimeError as exc:
        errors.append(str(exc))
    if not action.get(AUTHORED_ATTACK_PROPERTY):
        errors.append("Action has no authored-attack provenance.")
    try:
        skin_and_bones.require_canonical_yplus(armature, label="Authored attack validation")
    except RuntimeError as exc:
        errors.append(str(exc))
    curves = animation_library.iter_action_fcurves(action)
    if not curves:
        errors.append("Action contains no FK curves.")
    slots = getattr(action, "slots", None)
    if slots is not None and len(slots) != 1:
        errors.append("Authored Action must contain exactly one armature Action slot.")
    forbidden_records = {
        "dsb_offensive_recipe_json": "legacy procedural recipe",
        "dsb_offensive_motion_recipe_json": "Motion Studio recipe",
        "dsb_offensive_targeting_json": "targeting record",
        "dsb_offensive_motion_bypass_json": "technical bypass record",
    }
    for key, label in forbidden_records.items():
        if action.get(key):
            errors.append(f"Authored Action contains a forbidden {label}.")
    valid_prefix = 'pose.bones["'
    nonfinite = 0
    for curve in curves:
        path = str(getattr(curve, "data_path", ""))
        if not path.startswith(valid_prefix):
            errors.append(f"Non-bone animation channel is not exportable: {path}.")
        else:
            close = path.find('"]', len(valid_prefix))
            bone_name = path[len(valid_prefix):close] if close >= 0 else ""
            if not bone_name or armature.pose.bones.get(bone_name) is None:
                errors.append(f"FK channel references missing bone {bone_name or path!r}.")
        if path.endswith(".scale"):
            errors.append("Bone-scale animation is forbidden.")
        if not (path.endswith(".rotation_quaternion") or path.endswith(".location")):
            errors.append(f"Unsupported FK channel: {path}.")
        for point in curve.keyframe_points:
            if not all(math.isfinite(float(value)) for value in point.co):
                nonfinite += 1
    if nonfinite:
        errors.append(f"Action contains {nonfinite} non-finite keyframes.")
    markers = {marker.name: int(marker.frame) for marker in action.pose_markers}
    missing = [name for name in REQUIRED_MARKERS if name not in markers]
    if missing:
        errors.append("Missing markers: " + ", ".join(missing) + ".")
    else:
        ordered_frames = [markers[name] for name in REQUIRED_MARKERS]
        if any(second <= first for first, second in zip(ordered_frames, ordered_frames[1:])):
            errors.append("Attack markers must be strictly ordered.")
    start, end = animation_library.action_frame_bounds(action)
    if not math.isfinite(start) or not math.isfinite(end) or end <= start:
        errors.append("Action frame bounds are corrupt.")
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    try:
        offensive_actions.validated_action_metadata(
            action,
            clip_duration_seconds=max(0.0, end - start) / max(fps, 0.001),
            require_approved=require_approved,
        )
    except ValueError as exc:
        errors.append(str(exc))
    for bone in armature.pose.bones:
        if any(constraint.name.startswith(OWNED_CONSTRAINT_PREFIX) for constraint in bone.constraints):
            errors.append(f"Temporary authored constraint remains on {bone.name}.")
    helpers = [obj.name for obj in bpy.data.objects if bool(obj.get(OWNED_HELPER_PROPERTY, False))]
    if helpers:
        errors.append("Temporary authored helpers remain: " + ", ".join(helpers) + ".")
    return {
        "status": "FAIL" if errors else "PASS",
        "action": action.name,
        "errors": list(dict.fromkeys(errors)),
        "markers": markers,
        "fcurveCount": len(curves),
        "targetGeometryRequired": False,
        "motionStudioRecipePresent": bool(action.get("dsb_offensive_motion_recipe_json")),
    }


def remove_owned_preview_proxies():
    for obj in tuple(bpy.data.objects):
        legacy_owned_proxy = (
            bool(obj.get("dsb_motion_studio_owned", False))
            and str(obj.get("dsb_motion_studio_role", "")).startswith("PROXY_")
        )
        if bool(obj.get(PREVIEW_PROXY_PROPERTY, False)) or legacy_owned_proxy or obj.name == "DSB_MS_WEAPON_PROXY":
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and getattr(data, "users", 0) == 0:
                collection = getattr(bpy.data, data.bl_rna.identifier.lower() + "s", None)
                if collection is not None:
                    try:
                        collection.remove(data)
                    except (RuntimeError, TypeError):
                        pass


def _proxy_mesh(name, weapon):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    if weapon == "MACE":
        vertices = [
            (-0.025, 0.0, -0.025), (0.025, 0.0, -0.025),
            (-0.025, 0.52, -0.025), (0.025, 0.52, -0.025),
            (-0.070, 0.52, -0.070), (0.070, 0.52, -0.070),
            (-0.070, 0.66, -0.070), (0.070, 0.66, -0.070),
        ]
        edges = [(0, 2), (1, 3), (2, 3), (4, 5), (5, 7), (7, 6), (6, 4), (2, 6), (3, 7)]
    elif weapon == "AXE":
        vertices = [
            (-0.018, 0.0, 0.0), (0.018, 0.0, 0.0),
            (-0.018, 0.62, 0.0), (0.018, 0.62, 0.0),
            (-0.02, 0.52, 0.0), (0.17, 0.58, 0.0), (0.16, 0.73, 0.0), (-0.02, 0.68, 0.0),
        ]
        edges = [(0, 2), (1, 3), (2, 3), (4, 5), (5, 6), (6, 7), (7, 4)]
    else:
        vertices = [
            (-0.025, -0.10, 0.0), (0.025, -0.10, 0.0),
            (-0.018, 0.68, 0.0), (0.018, 0.68, 0.0),
            (-0.10, 0.04, 0.0), (0.10, 0.04, 0.0),
        ]
        edges = [(0, 2), (1, 3), (4, 5)]
    mesh.from_pydata(vertices, edges, [])
    mesh.update()
    return mesh


def replace_preview_proxy(context, weapon):
    remove_owned_preview_proxies()
    weapon = str(weapon or "NONE").upper()
    if weapon == "NONE":
        return None
    if weapon not in {"SWORD", "AXE", "MACE", "POLEARM"}:
        raise RuntimeError(f"Unknown preview weapon {weapon!r}.")
    armature = _armature(context)
    action = armature.animation_data.action if armature.animation_data else None
    payload = {}
    if action and action.get(AUTHORED_ATTACK_PROPERTY):
        payload = json.loads(str(action[AUTHORED_ATTACK_PROPERTY]))
    compatible = tuple(str(value) for value in payload.get("previewWeaponFamilies", ()))
    if compatible and weapon not in compatible:
        settings = getattr(context.scene, "daf_settings", None)
        if settings is not None and hasattr(settings, "authored_attack_status"):
            settings.authored_attack_status = (
                f"NO PROXY — {weapon} is not compatible with "
                + "/".join(compatible)
                + " mechanics"
            )
        return None
    side = "LEFT" if bool(payload.get("mirror", False)) else "RIGHT"
    socket = bpy.data.objects.get(f"DSB_ATTACHMENT_SOCKET_HAND_{side}_WEAPON")
    if socket is None:
        raise RuntimeError(f"Preview socket for {side.lower()} hand is missing.")
    mesh = _proxy_mesh("DSB_AUTHORED_" + weapon, weapon)
    proxy = bpy.data.objects.new("DSB_AUTHORED_ATTACK_PREVIEW_" + weapon, mesh)
    context.scene.collection.objects.link(proxy)
    proxy.parent = socket
    proxy.matrix_parent_inverse = Matrix.Identity(4)
    proxy.location = (0.0, 0.0, 0.0)
    # Preview geometry is authored along socket-local +Y.  Body curves never
    # read this transient proxy or its orientation.
    proxy.rotation_euler = (0.0, 0.0, 0.0)
    proxy[PREVIEW_PROXY_PROPERTY] = True
    proxy["dsb_preview_only"] = True
    proxy.display_type = 'WIRE'
    proxy.show_in_front = True
    return proxy


def cleanup_transients(context, *, keep_action=None):
    remove_owned_preview_proxies()
    for obj in tuple(bpy.data.objects):
        if bool(obj.get(OWNED_HELPER_PROPERTY, False)):
            bpy.data.objects.remove(obj, do_unlink=True)
    for armature in (obj for obj in bpy.data.objects if obj.type == 'ARMATURE'):
        for bone in armature.pose.bones:
            for constraint in tuple(bone.constraints):
                if constraint.name.startswith(OWNED_CONSTRAINT_PREFIX):
                    bone.constraints.remove(constraint)
    for action in tuple(bpy.data.actions):
        if action != keep_action and bool(action.get(AUTHORED_PREVIEW_PROPERTY, False)):
            if action.users == 0:
                bpy.data.actions.remove(action)


def rest_pose_corrected_delta(source_rest, source_pose, target_rest):
    """Map an explicit semantic source rotation delta onto a target rest pose."""

    source_rest = Matrix(source_rest).to_3x3().normalized()
    source_pose = Matrix(source_pose).to_3x3().normalized()
    target_rest = Matrix(target_rest).to_3x3().normalized()
    delta = source_rest.inverted() @ source_pose
    return (target_rest @ delta).normalized()


__all__ = (
    "AUTHORED_ATTACK_PROPERTY",
    "AUTHORED_ATTACK_SCHEMA",
    "BUILTIN_CLIPS",
    "MACRO_LIMITS",
    "PREVIEW_PROXY_PROPERTY",
    "REQUIRED_MARKERS",
    "accept_preview_as_draft",
    "bake_builtin_action",
    "browser_records",
    "clear_preview",
    "cleanup_transients",
    "default_macros",
    "discover_clips",
    "finalize_draft",
    "preview_clip",
    "preview_selected",
    "refresh_library",
    "remove_owned_preview_proxies",
    "replace_preview_proxy",
    "rest_pose_corrected_delta",
    "validate_action",
    "validate_clip_record",
)
