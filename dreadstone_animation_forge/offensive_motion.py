"""Blender-independent weapon-first offensive motion contracts and geometry.

Motion Studio deliberately keeps target, proxy, trajectory, validation, and
runtime targeting math independent from Blender.  The Blender adapter solves
the canonical body and samples the baked FK Action into this module.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence


MOTION_RECIPE_SCHEMA = "dreadstone.offensive_motion_recipe.v1"
MOTION_RECIPE_PROPERTY = "dsb_offensive_motion_recipe_json"
MOTION_MASTER_SCHEMA = "dreadstone.offensive_motion_master.v1"
MOTION_MASTER_PROPERTY = "dsb_offensive_motion_master_json"
MOTION_MASTER_LIBRARY_SCHEMA = "dreadstone.offensive_motion_master_library.v1"
MOTION_MASTER_LIBRARY_PROPERTY = "dsb_offensive_motion_master_library_json"
MOTION_VALIDATION_SCHEMA = "dreadstone.offensive_motion_validation.v1"
MOTION_VALIDATION_PROPERTY = "dsb_offensive_motion_validation_json"
MOTION_POSE_HEALTH_SCHEMA = "dreadstone.offensive_motion_pose_health.v1"
MOTION_POSE_HEALTH_PROPERTY = "dsb_offensive_motion_pose_health_json"
TARGETING_SCHEMA = "dreadstone.offensive_targeting.v1"
TARGETING_PROPERTY = "dsb_offensive_targeting_json"
BUILTIN_MOTION_REVISION = "5.4.2-simple.1"
DEFAULT_MINIMUM_REACH_RATIO = 0.55

TARGET_ZONES = frozenset({"HEAD", "UPPER_TORSO", "CENTER_MASS", "LOW_TORSO", "CUSTOM"})
TRAJECTORY_FAMILIES = frozenset({"HORIZONTAL", "DIAGONAL_DOWN", "OVERHEAD_VERTICAL", "THRUST", "CUSTOM"})
PROXY_CLASSES = frozenset({"ONE_HAND_BLADE", "ONE_HAND_BLUNT", "SHORT_BLADE", "TWO_HAND_GENERIC"})
MASTER_STATES = frozenset({"BUILT_IN_STARTER", "PROMOTED_MASTER"})
CONTACT_ANCHORS = frozenset({"CENTER", "ENTRY_SURFACE", "TOP_SURFACE", "SIDE_SURFACE"})
MOTION_FEELS = frozenset({"SUBTLE", "NATURAL", "FORCEFUL", "CUSTOM"})
CONTROL_IDS = (
    "START",
    "ANTICIPATION",
    "PRE_CONTACT",
    "CONTACT",
    "POST_CONTACT",
    "FOLLOW_THROUGH",
    "END",
)

_ID = re.compile(r"^[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?$")
_EPSILON = 1.0e-9


DEFAULT_TARGET = {
    "heightMeters": 1.80,
    "distanceMeters": 0.72,
    "lateralOffsetMeters": 0.0,
    "zone": "UPPER_TORSO",
    "torsoRadiusMeters": 0.22,
    "zoneHalfHeightMeters": 0.16,
    "headRadiusMeters": 0.14,
    "customHeightMeters": 1.15,
    "customRadiusMeters": 0.20,
}

PROXY_CLASS_DEFAULTS = {
    "ONE_HAND_BLUNT": {
        "class": "ONE_HAND_BLUNT",
        "lengthMeters": 0.74,
        "gripToContactMeters": 0.64,
        "strikeSegmentStartMeters": 0.54,
        "strikeSegmentEndMeters": 0.74,
        "headRadiusMeters": 0.075,
    },
    "ONE_HAND_BLADE": {
        "class": "ONE_HAND_BLADE",
        "lengthMeters": 0.82,
        "gripToContactMeters": 0.82,
        "strikeSegmentStartMeters": 0.18,
        "strikeSegmentEndMeters": 0.80,
        "headRadiusMeters": 0.025,
    },
    "SHORT_BLADE": {
        "class": "SHORT_BLADE",
        "lengthMeters": 0.46,
        "gripToContactMeters": 0.46,
        "strikeSegmentStartMeters": 0.12,
        "strikeSegmentEndMeters": 0.46,
        "headRadiusMeters": 0.018,
    },
    "TWO_HAND_GENERIC": {
        "class": "TWO_HAND_GENERIC",
        "lengthMeters": 1.10,
        "gripToContactMeters": 0.92,
        "strikeSegmentStartMeters": 0.42,
        "strikeSegmentEndMeters": 1.08,
        "headRadiusMeters": 0.035,
    },
}

DEFAULT_PROXY = deepcopy(PROXY_CLASS_DEFAULTS["ONE_HAND_BLUNT"])

STYLE_PRESETS = {
    "SUBTLE": {
        "anticipation": 0.50,
        "torsoPower": 0.34,
        "stanceCompression": 0.14,
        "followThrough": 0.44,
        "recovery": 0.94,
        "armExtension": 0.82,
        "elbowStyle": 1.14,
        "wristStyle": 0.38,
    },
    "NATURAL": {
        "anticipation": 0.70,
        "torsoPower": 0.54,
        "stanceCompression": 0.26,
        "followThrough": 0.64,
        "recovery": 0.86,
        "armExtension": 0.87,
        "elbowStyle": 1.06,
        "wristStyle": 0.62,
    },
    "FORCEFUL": {
        "anticipation": 1.02,
        "torsoPower": 0.92,
        "stanceCompression": 0.58,
        "followThrough": 1.02,
        "recovery": 0.74,
        "armExtension": 0.92,
        "elbowStyle": 0.94,
        "wristStyle": 0.92,
    },
}

DEFAULT_STYLE = deepcopy(STYLE_PRESETS["NATURAL"])

DEFAULT_SOLVER = {
    "arm": "RIGHT",
    "ikChainLength": 2,
    "poleSideMeters": 0.36,
    "poleBackMeters": 0.08,
    "torsoSupport": 0.72,
    "minimumReachRatio": DEFAULT_MINIMUM_REACH_RATIO,
    "comfortableReachRatio": 0.88,
    "warningReachRatio": 0.92,
    "hardReachRatio": 0.985,
    "maxShoulderSupportDegrees": 4.0,
    "deformTranslationToleranceMeters": 0.0001,
    "solveErrorToleranceMeters": 0.015,
    "bakeStepFrames": 1,
}

DEFAULT_TOLERANCES = {
    "planeErrorMeters": 0.12,
    "contactFrameWindowFrames": 2.0,
    "directionDotMinimum": 0.60,
    "activeSamplingStepFrames": 0.25,
}


def _unit(value):
    components = tuple(float(component) for component in value)
    magnitude = math.sqrt(sum(component * component for component in components))
    if magnitude <= _EPSILON:
        return (0.0, 1.0, 0.0)
    return tuple(component / magnitude for component in components)


def _control(control_id: str, offset, axis) -> dict[str, Any]:
    return {
        "id": control_id,
        "targetOffsetMeters": [float(value) for value in offset],
        "weaponAxisLocal": [float(value) for value in _unit(axis)],
    }


def _master(
    master_id: str,
    label: str,
    action_kind: str,
    target_zone: str,
    family: str,
    direction,
    controls,
    *,
    proxy_class="ONE_HAND_BLUNT",
    target_distance=0.72,
    timing=(0.54, 0.28, 0.62),
    contact_anchor="CENTER",
    axes_by_proxy=None,
) -> dict[str, Any]:
    target = deepcopy(DEFAULT_TARGET)
    target["zone"] = target_zone
    target["distanceMeters"] = float(target_distance)
    proxy = deepcopy(PROXY_CLASS_DEFAULTS[proxy_class])
    profiles = {
        str(class_name): {
            control_id: [float(value) for value in _unit(axis)]
            for control_id, axis in profile.items()
        }
        for class_name, profile in dict(axes_by_proxy or {}).items()
    }
    return {
        "schema": MOTION_MASTER_SCHEMA,
        "version": 1,
        "masterId": master_id,
        "label": label,
        "state": "BUILT_IN_STARTER",
        "artistApproved": False,
        "builtInRevision": BUILTIN_MOTION_REVISION,
        "feel": "NATURAL",
        "actionKind": action_kind,
        "target": target,
        "proxy": proxy,
        "trajectory": {
            "family": family,
            "contactAnchor": str(contact_anchor),
            "expectedDirectionLocal": [float(value) for value in _unit(direction)],
            "controls": [_control(*value) for value in controls],
            "weaponAxesByProxy": profiles,
        },
        "timing": {
            "windupSeconds": float(timing[0]),
            "activeSeconds": float(timing[1]),
            "recoverySeconds": float(timing[2]),
            "contactFractionOfActive": 0.55,
        },
        "style": deepcopy(DEFAULT_STYLE),
        "solver": deepcopy(DEFAULT_SOLVER),
        "tolerances": deepcopy(DEFAULT_TOLERANCES),
    }


def _axes(*values):
    return {control_id: value for control_id, value in zip(CONTROL_IDS, values)}


_SLASH_RTL_BLADE_AXES = _axes(
    (-0.42, 0.80, 0.42), (-0.61, 0.63, 0.31), (-0.68, 0.63, -0.37),
    (-0.68, 0.63, -0.37), (-0.48, 0.73, -0.49), (-0.18, 0.80, -0.57),
    (-0.42, 0.80, 0.42),
)
_SLASH_LTR_BLADE_AXES = _axes(
    (-0.42, 0.80, 0.42), (-0.76, 0.56, 0.33), (-0.72, 0.60, -0.35),
    (-0.72, 0.60, -0.35), (-0.34, 0.78, -0.52), (0.10, 0.82, -0.56),
    (-0.42, 0.80, 0.42),
)
_OVERHEAD_BLADE_AXES = _axes(
    (-0.15, 0.74, 0.66), (-0.10, 0.78, 0.62), (-0.05, 1.00, 0.02),
    (-0.06, 0.89, -0.45), (-0.08, 0.90, -0.42), (-0.15, 0.91, -0.38),
    (-0.15, 0.74, 0.66),
)
_OVERHEAD_BLUNT_AXES = _axes(
    (-0.10, 0.89, 0.45), (-0.10, 0.78, 0.62), (-0.05, 1.00, 0.02),
    (-0.04, 1.00, -0.02), (-0.08, 0.99, -0.10), (-0.14, 0.97, -0.20),
    (-0.10, 0.89, 0.45),
)
_DIAGONAL_BLADE_AXES = _axes(
    (-0.30, 0.75, 0.59), (-0.48, 0.56, 0.68), (-0.58, 0.66, -0.48),
    (-0.58, 0.66, -0.48), (-0.45, 0.76, -0.47), (-0.20, 0.84, -0.51),
    (-0.30, 0.75, 0.59),
)
_DIAGONAL_BLUNT_AXES = _axes(
    (0.18, 0.84, 0.51), (0.24, 0.52, 0.82), (-0.15, 0.94, 0.30),
    (-0.50, 0.72, -0.48), (-0.40, 0.79, -0.46), (-0.16, 0.86, -0.48),
    (0.18, 0.84, 0.51),
)
_THRUST_BLADE_AXES = _axes(
    (0.04, 0.99, 0.08), (0.02, 0.99, 0.10), (0.0, 1.0, 0.02),
    (0.0, 1.0, 0.0), (0.0, 1.0, -0.02), (0.02, 0.99, 0.04),
    (0.04, 0.99, 0.08),
)


# Target-anchor-relative strike-point controls. CONTACT is first impact on a
# meaningful target surface; ACTIVE then crosses through the authored volume.
# Offsets are deliberately compact. Weapon-class profiles keep blades readable
# without changing neutral runtime socket calibration.
BUILTIN_MOTION_MASTERS = {
    "builtin_1h_slash_rtl": _master(
        "builtin_1h_slash_rtl",
        "1H Slash Right to Left",
        "ATTACK_SLASH_RTL_ONE_HAND",
        "UPPER_TORSO",
        "HORIZONTAL",
        (-1.0, 0.0, 0.0),
        (
            ("START", (0.16, -0.20, -0.02), (-0.42, 0.80, 0.42)),
            ("ANTICIPATION", (0.32, -0.18, 0.18), (-0.61, 0.63, 0.31)),
            ("PRE_CONTACT", (0.16, -0.015, 0.015), (-0.68, 0.63, -0.37)),
            ("CONTACT", (0.0, 0.0, 0.0), (-0.68, 0.63, -0.37)),
            ("POST_CONTACT", (-0.48, 0.02, -0.03), (-0.48, 0.73, -0.49)),
            ("FOLLOW_THROUGH", (-0.54, -0.18, -0.15), (-0.18, 0.80, -0.57)),
            ("END", (0.16, -0.20, -0.02), (-0.42, 0.80, 0.42)),
        ),
        proxy_class="ONE_HAND_BLADE",
        target_distance=0.68,
        timing=(0.46, 0.30, 0.58),
        contact_anchor="SIDE_SURFACE",
        axes_by_proxy={"ONE_HAND_BLADE": _SLASH_RTL_BLADE_AXES, "SHORT_BLADE": _SLASH_RTL_BLADE_AXES},
    ),
    "builtin_1h_slash_ltr": _master(
        "builtin_1h_slash_ltr",
        "1H Slash Left to Right",
        "ATTACK_SLASH_LTR_ONE_HAND",
        "UPPER_TORSO",
        "HORIZONTAL",
        (1.0, 0.0, 0.0),
        (
            ("START", (-0.14, -0.20, -0.02), (-0.42, 0.80, 0.42)),
            ("ANTICIPATION", (-0.30, -0.18, 0.16), (-0.76, 0.56, 0.33)),
            ("PRE_CONTACT", (-0.16, -0.015, 0.015), (-0.72, 0.60, -0.35)),
            ("CONTACT", (0.0, 0.0, 0.0), (-0.72, 0.60, -0.35)),
            ("POST_CONTACT", (0.48, 0.02, -0.03), (-0.34, 0.78, -0.52)),
            ("FOLLOW_THROUGH", (0.54, -0.17, -0.15), (0.10, 0.82, -0.56)),
            ("END", (-0.14, -0.20, -0.02), (-0.42, 0.80, 0.42)),
        ),
        proxy_class="ONE_HAND_BLADE",
        target_distance=0.66,
        timing=(0.48, 0.30, 0.56),
        contact_anchor="SIDE_SURFACE",
        axes_by_proxy={"ONE_HAND_BLADE": _SLASH_LTR_BLADE_AXES, "SHORT_BLADE": _SLASH_LTR_BLADE_AXES},
    ),
    "builtin_1h_overhead": _master(
        "builtin_1h_overhead",
        "1H Overhead",
        "ATTACK_OVERHEAD_ONE_HAND",
        "UPPER_TORSO",
        "OVERHEAD_VERTICAL",
        (0.0, 0.0, -1.0),
        (
            ("START", (0.18, -0.29, 0.02), (-0.10, 0.72, 0.69)),
            ("ANTICIPATION", (0.08, -0.20, 0.38), (-0.10, 0.25, 0.96)),
            ("PRE_CONTACT", (0.02, 0.12, 0.16), (-0.05, 1.00, 0.02)),
            ("CONTACT", (0.0, 0.0, 0.0), (-0.04, 0.95, -0.31)),
            ("POST_CONTACT", (-0.05, 0.03, -0.30), (-0.08, 0.93, -0.36)),
            ("FOLLOW_THROUGH", (-0.14, -0.15, -0.42), (-0.14, 0.92, -0.37)),
            ("END", (0.18, -0.29, 0.02), (-0.10, 0.72, 0.69)),
        ),
        proxy_class="ONE_HAND_BLUNT",
        target_distance=0.64,
        timing=(0.58, 0.26, 0.66),
        contact_anchor="TOP_SURFACE",
        axes_by_proxy={
            "ONE_HAND_BLUNT": _OVERHEAD_BLUNT_AXES,
            "ONE_HAND_BLADE": _OVERHEAD_BLADE_AXES,
            "SHORT_BLADE": _OVERHEAD_BLADE_AXES,
        },
    ),
    "builtin_1h_heavy_diagonal": _master(
        "builtin_1h_heavy_diagonal",
        "1H Heavy Diagonal",
        "ATTACK_HEAVY_ONE_HAND",
        "CENTER_MASS",
        "DIAGONAL_DOWN",
        (-0.70, 0.0, -0.70),
        (
            ("START", (0.14, -0.24, 0.14), (-0.30, 0.75, 0.59)),
            ("ANTICIPATION", (0.08, -0.18, 0.38), (-0.48, 0.56, 0.68)),
            ("PRE_CONTACT", (0.16, -0.02, 0.16), (-0.58, 0.66, -0.48)),
            ("CONTACT", (0.0, 0.0, 0.0), (-0.58, 0.66, -0.48)),
            ("POST_CONTACT", (-0.28, 0.02, -0.30), (-0.45, 0.76, -0.47)),
            ("FOLLOW_THROUGH", (-0.32, -0.14, -0.28), (-0.20, 0.84, -0.51)),
            ("END", (0.14, -0.24, 0.14), (-0.30, 0.75, 0.59)),
        ),
        proxy_class="ONE_HAND_BLUNT",
        target_distance=0.68,
        timing=(0.72, 0.34, 0.78),
        contact_anchor="SIDE_SURFACE",
        axes_by_proxy={
            "ONE_HAND_BLUNT": _DIAGONAL_BLUNT_AXES,
            "ONE_HAND_BLADE": _DIAGONAL_BLADE_AXES,
            "SHORT_BLADE": _DIAGONAL_BLADE_AXES,
        },
    ),
    "builtin_1h_thrust": _master(
        "builtin_1h_thrust",
        "1H Thrust",
        "ATTACK_THRUST_ONE_HAND",
        "CENTER_MASS",
        "THRUST",
        (0.0, 1.0, 0.0),
        (
            ("START", (0.10, -0.12, 0.02), (0.04, 0.99, 0.08)),
            ("ANTICIPATION", (0.07, -0.16, 0.04), (0.02, 0.99, 0.10)),
            ("PRE_CONTACT", (0.02, -0.05, 0.01), (0.0, 1.0, 0.02)),
            ("CONTACT", (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            ("POST_CONTACT", (-0.01, 0.15, -0.01), (0.0, 1.0, -0.02)),
            ("FOLLOW_THROUGH", (0.02, 0.04, -0.02), (0.02, 0.99, 0.04)),
            ("END", (0.10, -0.10, 0.02), (0.04, 0.99, 0.08)),
        ),
        proxy_class="ONE_HAND_BLADE",
        target_distance=1.34,
        timing=(0.42, 0.26, 0.52),
        contact_anchor="ENTRY_SURFACE",
        axes_by_proxy={"ONE_HAND_BLADE": _THRUST_BLADE_AXES, "SHORT_BLADE": _THRUST_BLADE_AXES},
    ),
}


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def finite_vector(value, size=3) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == size and all(finite_number(item) for item in value)


def vector(value) -> tuple[float, float, float]:
    if not finite_vector(value):
        raise ValueError("Expected a finite 3-vector.")
    return tuple(float(item) for item in value)


def add(first, second):
    return tuple(float(a) + float(b) for a, b in zip(first, second))


def subtract(first, second):
    return tuple(float(a) - float(b) for a, b in zip(first, second))


def multiply(value, scalar):
    return tuple(float(component) * float(scalar) for component in value)


def dot(first, second) -> float:
    return sum(float(a) * float(b) for a, b in zip(first, second))


def cross(first, second):
    ax, ay, az = vector(first)
    bx, by, bz = vector(second)
    return (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)


def length(value) -> float:
    return math.sqrt(max(0.0, dot(value, value)))


def normalize(value, fallback=(0.0, 1.0, 0.0)):
    magnitude = length(value)
    if magnitude <= _EPSILON:
        return vector(fallback)
    return tuple(float(component) / magnitude for component in value)


def lerp(first, second, factor):
    factor = float(factor)
    return add(multiply(first, 1.0 - factor), multiply(second, factor))


def clamp(value, minimum=0.0, maximum=1.0):
    return max(float(minimum), min(float(maximum), float(value)))


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(*values: Any) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(stable_json(value).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def target_zone_center(target: Mapping[str, Any]) -> tuple[float, float, float]:
    height = float(target["heightMeters"])
    zone = str(target["zone"])
    ratios = {"HEAD": 0.90, "UPPER_TORSO": 0.72, "CENTER_MASS": 0.58, "LOW_TORSO": 0.44}
    z = float(target["customHeightMeters"]) if zone == "CUSTOM" else height * ratios[zone]
    return (float(target["lateralOffsetMeters"]), float(target["distanceMeters"]), z)


def target_zone_volume(target: Mapping[str, Any]) -> dict[str, Any]:
    center = target_zone_center(target)
    zone = str(target["zone"])
    if zone in {"HEAD", "CUSTOM"}:
        radius = float(target["headRadiusMeters"] if zone == "HEAD" else target["customRadiusMeters"])
        return {"type": "SPHERE", "center": list(center), "radiusMeters": radius, "zone": zone}
    half_height = float(target["zoneHalfHeightMeters"])
    return {
        "type": "CAPSULE",
        "start": [center[0], center[1], center[2] - half_height],
        "end": [center[0], center[1], center[2] + half_height],
        "radiusMeters": float(target["torsoRadiusMeters"]),
        "center": list(center),
        "zone": zone,
    }


def proxy_defaults(proxy_class: str) -> dict[str, Any]:
    try:
        return deepcopy(PROXY_CLASS_DEFAULTS[str(proxy_class)])
    except KeyError:
        raise ValueError(f"Unsupported weapon proxy class {proxy_class!r}.") from None


def target_contact_anchor(
    target: Mapping[str, Any],
    anchor: str,
    expected_direction=(0.0, 1.0, 0.0),
    *,
    proxy_radius=0.0,
) -> tuple[float, float, float]:
    """Resolve first-impact anchors from the exact authored target volume."""

    volume = target_zone_volume(target)
    center = vector(volume["center"])
    anchor = str(anchor or "CENTER")
    if anchor == "CENTER":
        return center
    # A 2 mm numerical inset makes the sampled CONTACT unambiguously intersect
    # while still reading as first surface impact at human/weapon scale.
    radius = max(0.0, float(volume["radiusMeters"]) + max(0.0, float(proxy_radius)) - 0.002)
    if anchor == "TOP_SURFACE":
        top = vector(volume["end"]) if volume["type"] == "CAPSULE" else center
        return add(top, (0.0, 0.0, radius))
    direction = normalize(expected_direction)
    if anchor == "SIDE_SURFACE":
        side = -1.0 if float(direction[0]) > 0.0 else 1.0
        return add(center, (side * radius, 0.0, 0.0))
    if anchor == "ENTRY_SURFACE":
        # The entry point is the near surface opposite travel. Canonical thrust
        # therefore meets the front of the target instead of its center.
        radial = (-direction[0] * radius, -direction[1] * radius, 0.0)
        return add(center, radial)
    raise ValueError(f"Unsupported target contact anchor {anchor!r}.")


VIP_MACRO_DEFAULTS = {
    "horizontalAim": 0.0,
    "verticalAim": 0.0,
    "windup": 50.0,
    "strikePower": 50.0,
    "bodyMotion": 50.0,
    "followThrough": 50.0,
    "armRelax": 50.0,
}


def apply_vip_macros(recipe: Mapping[str, Any], macros: Mapping[str, Any]) -> dict[str, Any]:
    """Apply artist-facing aim and feel macros without changing contact law."""

    result = deepcopy(recipe)
    values = dict(VIP_MACRO_DEFAULTS)
    values.update({key: float(value) for key, value in dict(macros or {}).items() if key in values})
    horizontal = clamp(values["horizontalAim"], -100.0, 100.0)
    vertical = clamp(values["verticalAim"], -100.0, 100.0)
    trajectory = result["trajectory"]
    family = str(trajectory["family"])
    # Thrust/overhead families can be redirected substantially. Crossing arcs
    # stay deliberately tighter so a macro cannot swing WINDUP through target.
    aim_scale = 1.0 if family in {"THRUST", "OVERHEAD_VERTICAL"} else (1.0 / 6.0)
    yaw = math.radians(horizontal * 0.30 * aim_scale)
    pitch = math.radians(vertical * 0.18 * aim_scale)

    def rotate(value):
        x, y, z = vector(value)
        cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
        x, y = x * cos_yaw + y * sin_yaw, -x * sin_yaw + y * cos_yaw
        cos_pitch, sin_pitch = math.cos(pitch), math.sin(pitch)
        return (x, y * cos_pitch - z * sin_pitch, y * sin_pitch + z * cos_pitch)

    old_direction = normalize(trajectory["expectedDirectionLocal"])
    new_direction = normalize(rotate(old_direction))
    proxy = result["proxy"]
    proxy_radius = float(proxy["headRadiusMeters"] if proxy["class"] == "ONE_HAND_BLUNT" else 0.015)
    anchor_kind = str(trajectory.get("contactAnchor", "CENTER"))
    old_anchor = target_contact_anchor(result["target"], anchor_kind, old_direction, proxy_radius=proxy_radius)
    new_anchor = target_contact_anchor(result["target"], anchor_kind, new_direction, proxy_radius=proxy_radius)
    trajectory["expectedDirectionLocal"] = [round(value, 7) for value in new_direction]
    for control in trajectory["controls"]:
        offset = subtract(control["contactPointLocal"], old_anchor)
        control["contactPointLocal"] = [round(value, 7) for value in add(new_anchor, rotate(offset))]
        control["weaponAxisLocal"] = [round(value, 7) for value in normalize(rotate(control["weaponAxisLocal"]))]

    def centered(name):
        return (clamp(values[name], 0.0, 100.0) - 50.0) / 50.0

    windup = centered("windup")
    power = centered("strikePower")
    body = centered("bodyMotion")
    follow = centered("followThrough")
    relax = centered("armRelax")
    style = result["style"]
    style["anticipation"] = clamp(float(style["anticipation"]) * (1.0 + 0.25 * windup), 0.0, 2.0)
    style["torsoPower"] = clamp(float(style["torsoPower"]) * (1.0 + 0.35 * body + 0.12 * power), 0.0, 2.0)
    style["stanceCompression"] = clamp(float(style["stanceCompression"]) * (1.0 + 0.35 * body), 0.0, 2.0)
    style["followThrough"] = clamp(float(style["followThrough"]) * (1.0 + 0.30 * follow), 0.0, 2.0)
    style["wristStyle"] = clamp(float(style["wristStyle"]) * (1.0 + 0.20 * power), 0.0, 2.0)
    style["armExtension"] = clamp(float(style["armExtension"]) * (1.0 - 0.09 * relax), 0.0, 2.0)
    style["elbowStyle"] = clamp(float(style["elbowStyle"]) * (1.0 + 0.11 * relax), 0.0, 2.0)
    result["timing"]["windupSeconds"] = clamp(float(result["timing"]["windupSeconds"]) * (1.0 + 0.18 * windup), 0.10, 2.50)
    result["timing"]["activeSeconds"] = clamp(float(result["timing"]["activeSeconds"]) * (1.0 - 0.12 * power), 0.08, 1.00)
    result["solver"]["torsoSupport"] = clamp(float(result["solver"]["torsoSupport"]) * (1.0 + 0.25 * body), 0.0, 2.0)
    result.setdefault("provenance", {})["vipMacros"] = {key: round(value, 3) for key, value in values.items()}
    return result


def arm_reach_model(
    upper_arm_length: float,
    lower_arm_length: float,
    *,
    minimum_ratio=DEFAULT_MINIMUM_REACH_RATIO,
    comfortable_ratio=0.88,
    warning_ratio=0.92,
    hard_ratio=0.985,
) -> dict[str, float]:
    """Return character-specific shoulder-to-wrist reach thresholds."""

    upper = float(upper_arm_length)
    lower = float(lower_arm_length)
    if not math.isfinite(upper) or not math.isfinite(lower) or upper <= 0.0 or lower <= 0.0:
        raise ValueError("Canonical upper- and lower-arm lengths must be finite and positive.")
    comfortable = clamp(float(comfortable_ratio), 0.70, 0.94)
    minimum = clamp(float(minimum_ratio), 0.20, comfortable)
    warning = clamp(float(warning_ratio), comfortable, 0.97)
    hard = clamp(float(hard_ratio), warning, 0.9995)
    maximum = upper + lower
    return {
        "upperArmLengthMeters": upper,
        "lowerArmLengthMeters": lower,
        "maximumGeometricReachMeters": maximum,
        "minimumReachRatio": minimum,
        "minimumReachMeters": maximum * minimum,
        "comfortableReachRatio": comfortable,
        "comfortableReachMeters": maximum * comfortable,
        "warningReachRatio": warning,
        "warningReachMeters": maximum * warning,
        "hardReachRatio": hard,
        "hardReachMeters": maximum * hard,
    }


def reach_requirement(shoulder, wrist, reach_model: Mapping[str, Any]) -> dict[str, Any]:
    distance = length(subtract(wrist, shoulder))
    maximum = max(float(reach_model["maximumGeometricReachMeters"]), _EPSILON)
    ratio = distance / maximum
    status = (
        "FOLDED"
        if ratio < float(reach_model.get("minimumReachRatio", DEFAULT_MINIMUM_REACH_RATIO)) - 1.0e-7
        else "IMPOSSIBLE"
        if ratio > float(reach_model["hardReachRatio"]) + 1.0e-7
        else "WARNING"
        if ratio > float(reach_model["warningReachRatio"]) + 1.0e-7
        else "COMFORTABLE"
    )
    return {"distanceMeters": distance, "extensionRatio": ratio, "status": status}


def elbow_bend_degrees(shoulder, elbow, wrist) -> float:
    first = normalize(subtract(shoulder, elbow))
    second = normalize(subtract(wrist, elbow))
    interior = math.degrees(math.acos(clamp(dot(first, second), -1.0, 1.0)))
    return max(0.0, 180.0 - interior)


def default_contact_distance(proxy: Mapping[str, Any], family: str) -> float:
    if str(family) == "THRUST" or str(proxy["class"]) == "ONE_HAND_BLUNT":
        return float(proxy["gripToContactMeters"])
    return (float(proxy["strikeSegmentStartMeters"]) + float(proxy["strikeSegmentEndMeters"])) * 0.5


def select_strike_contact_distance(
    contact_point,
    weapon_axis,
    shoulder,
    proxy: Mapping[str, Any],
    comfortable_reach_meters: float,
    *,
    preferred_distance=None,
    target_reach_meters=None,
) -> float:
    """Choose a legal blade point while preferring comfortable arm reach."""

    if str(proxy["class"]) == "ONE_HAND_BLUNT":
        return float(proxy["gripToContactMeters"])
    start = float(proxy["strikeSegmentStartMeters"])
    end = float(proxy["strikeSegmentEndMeters"])
    preferred = clamp(
        default_contact_distance(proxy, "CUSTOM") if preferred_distance is None else float(preferred_distance),
        start,
        end,
    )
    delta = subtract(contact_point, shoulder)
    axis = normalize(weapon_axis)
    projection = dot(delta, axis)
    perpendicular_sq = max(0.0, dot(delta, delta) - projection * projection)
    comfortable = max(0.0, float(comfortable_reach_meters))
    target_reach = min(
        comfortable,
        max(0.0, float(target_reach_meters if target_reach_meters is not None else comfortable * 0.90)),
    )
    candidates = {start, end, preferred, clamp(projection, start, end)}
    target_sq = target_reach * target_reach
    if perpendicular_sq <= target_sq:
        along = math.sqrt(max(0.0, target_sq - perpendicular_sq))
        for value in (projection - along, projection + along):
            if start <= value <= end:
                candidates.add(value)

    def score(distance):
        reach = math.sqrt(max(0.0, perpendicular_sq + (projection - distance) ** 2))
        hard_penalty = max(0.0, reach - comfortable) * 20.0
        return abs(reach - target_reach) + abs(distance - preferred) * 0.025 + hard_penalty

    return min(candidates, key=score)


_SUPPORT_PROFILES = {
    "HORIZONTAL": (0.0, -0.24, -0.06, 0.28, 0.35, 0.17, 0.0),
    "OVERHEAD_VERTICAL": (0.0, -0.20, -0.04, 0.27, 0.34, 0.15, 0.0),
    "DIAGONAL_DOWN": (0.0, -0.27, -0.07, 0.31, 0.39, 0.18, 0.0),
    "THRUST": (0.0, -0.15, -0.03, 0.20, 0.24, 0.09, 0.0),
    "CUSTOM": (0.0, -0.18, -0.04, 0.24, 0.30, 0.13, 0.0),
}


def body_support_envelope(recipe: Mapping[str, Any], frame: float, schedule: Mapping[str, int]) -> float:
    """C1-continuous body support through every authored phase boundary."""

    family = str(recipe["trajectory"]["family"])
    values = _SUPPORT_PROFILES.get(family, _SUPPORT_PROFILES["CUSTOM"])
    frames = [float(schedule[control_id]) for control_id in CONTROL_IDS]
    frame = clamp(float(frame), frames[0], frames[-1])
    segment = next((index for index in range(len(frames) - 1) if frame <= frames[index + 1]), len(frames) - 2)
    duration = max(frames[segment + 1] - frames[segment], _EPSILON)
    factor = clamp((frame - frames[segment]) / duration)
    smooth = factor * factor * (3.0 - 2.0 * factor)

    def styled(value, index):
        if value < 0.0:
            return value * float(recipe["style"]["anticipation"])
        result = value * float(recipe["style"]["followThrough"])
        if index >= CONTROL_IDS.index("FOLLOW_THROUGH"):
            result *= float(recipe["style"]["recovery"])
        return result

    return (1.0 - smooth) * styled(values[segment], segment) + smooth * styled(values[segment + 1], segment + 1)


def closest_point_on_segment(point, start, end):
    direction = subtract(end, start)
    denominator = dot(direction, direction)
    if denominator <= _EPSILON:
        return vector(start), 0.0
    factor = clamp(dot(subtract(point, start), direction) / denominator)
    return add(start, multiply(direction, factor)), factor


def point_segment_distance(point, start, end) -> float:
    closest, _factor = closest_point_on_segment(point, start, end)
    return length(subtract(point, closest))


def segment_segment_closest(first_start, first_end, second_start, second_end):
    """Return robust closest points and distance for two finite 3D segments."""

    p1 = vector(first_start)
    q1 = vector(first_end)
    p2 = vector(second_start)
    q2 = vector(second_end)
    d1 = subtract(q1, p1)
    d2 = subtract(q2, p2)
    r = subtract(p1, p2)
    a = dot(d1, d1)
    e = dot(d2, d2)
    f = dot(d2, r)
    if a <= _EPSILON and e <= _EPSILON:
        return p1, p2, length(subtract(p1, p2))
    if a <= _EPSILON:
        first_factor = 0.0
        second_factor = clamp(f / e)
    else:
        c = dot(d1, r)
        if e <= _EPSILON:
            second_factor = 0.0
            first_factor = clamp(-c / a)
        else:
            b = dot(d1, d2)
            denominator = a * e - b * b
            first_factor = clamp((b * f - c * e) / denominator) if abs(denominator) > _EPSILON else 0.0
            second_factor = (b * first_factor + f) / e
            if second_factor < 0.0:
                second_factor = 0.0
                first_factor = clamp(-c / a)
            elif second_factor > 1.0:
                second_factor = 1.0
                first_factor = clamp((b - c) / a)
    first_point = add(p1, multiply(d1, first_factor))
    second_point = add(p2, multiply(d2, second_factor))
    return first_point, second_point, length(subtract(first_point, second_point))


def segment_volume_distance(start, end, volume: Mapping[str, Any]) -> tuple[float, tuple[float, float, float], tuple[float, float, float]]:
    """Signed clearance from a strike segment to a sphere/capsule volume."""

    radius = float(volume["radiusMeters"])
    if volume["type"] == "SPHERE":
        on_segment, _factor = closest_point_on_segment(volume["center"], start, end)
        on_volume_axis = vector(volume["center"])
        distance = length(subtract(on_segment, on_volume_axis))
    elif volume["type"] == "CAPSULE":
        on_segment, on_volume_axis, distance = segment_segment_closest(start, end, volume["start"], volume["end"])
    else:
        raise ValueError(f"Unsupported target volume {volume.get('type')!r}.")
    return distance - radius, on_segment, on_volume_axis


def point_volume_distance(point, volume: Mapping[str, Any]) -> tuple[float, tuple[float, float, float], tuple[float, float, float]]:
    """Signed clearance from a contact point to a sphere/capsule volume."""

    weapon_point = vector(point)
    radius = float(volume["radiusMeters"])
    if volume["type"] == "SPHERE":
        on_volume_axis = vector(volume["center"])
    elif volume["type"] == "CAPSULE":
        on_volume_axis, _factor = closest_point_on_segment(
            weapon_point,
            volume["start"],
            volume["end"],
        )
    else:
        raise ValueError(f"Unsupported target volume {volume.get('type')!r}.")
    return length(subtract(weapon_point, on_volume_axis)) - radius, weapon_point, on_volume_axis


def trajectory_geometry(family: str, target_center, expected_direction) -> dict[str, Any]:
    center = vector(target_center)
    direction = normalize(expected_direction)
    if family == "HORIZONTAL":
        return {"type": "PLANE", "point": list(center), "normal": [0.0, 0.0, 1.0]}
    if family == "OVERHEAD_VERTICAL":
        return {"type": "PLANE", "point": list(center), "normal": [1.0, 0.0, 0.0]}
    if family == "DIAGONAL_DOWN":
        return {"type": "PLANE", "point": list(center), "normal": [0.0, 1.0, 0.0]}
    if family == "THRUST":
        return {"type": "LINE", "point": list(center), "direction": list(direction)}
    return {"type": "CUSTOM", "point": list(center), "direction": list(direction)}


def trajectory_error(point, geometry: Mapping[str, Any]) -> float:
    if geometry["type"] == "PLANE":
        return abs(dot(subtract(point, geometry["point"]), normalize(geometry["normal"])))
    if geometry["type"] == "LINE":
        offset = subtract(point, geometry["point"])
        direction = normalize(geometry["direction"])
        return length(subtract(offset, multiply(direction, dot(offset, direction))))
    return 0.0


def _numeric_errors(record: Mapping[str, Any], fields: Mapping[str, tuple[float, float]], prefix: str) -> list[str]:
    errors = []
    for name, (minimum, maximum) in fields.items():
        value = record.get(name)
        if not finite_number(value):
            errors.append(f"{prefix}.{name} must be finite.")
        elif not minimum <= float(value) <= maximum:
            errors.append(f"{prefix}.{name} must be between {minimum} and {maximum}.")
    return errors


def validate_target(target: Mapping[str, Any]) -> list[str]:
    if not isinstance(target, Mapping):
        return ["target must be an object."]
    errors = []
    if target.get("zone") not in TARGET_ZONES:
        errors.append("target.zone is unsupported.")
    errors.extend(_numeric_errors(target, {
        "heightMeters": (0.6, 4.0),
        "distanceMeters": (0.2, 4.0),
        "lateralOffsetMeters": (-2.0, 2.0),
        "torsoRadiusMeters": (0.05, 0.60),
        "zoneHalfHeightMeters": (0.03, 0.60),
        "headRadiusMeters": (0.04, 0.40),
        "customHeightMeters": (0.1, 4.0),
        "customRadiusMeters": (0.03, 0.60),
    }, "target"))
    return errors


def validate_proxy(proxy: Mapping[str, Any]) -> list[str]:
    if not isinstance(proxy, Mapping):
        return ["proxy must be an object."]
    errors = []
    if proxy.get("class") not in PROXY_CLASSES:
        errors.append("proxy.class is unsupported.")
    errors.extend(_numeric_errors(proxy, {
        "lengthMeters": (0.15, 3.0),
        "gripToContactMeters": (0.05, 3.0),
        "strikeSegmentStartMeters": (0.0, 3.0),
        "strikeSegmentEndMeters": (0.05, 3.0),
        "headRadiusMeters": (0.0, 0.30),
    }, "proxy"))
    if all(finite_number(proxy.get(name)) for name in ("lengthMeters", "gripToContactMeters", "strikeSegmentStartMeters", "strikeSegmentEndMeters")):
        if float(proxy["gripToContactMeters"]) > float(proxy["lengthMeters"]) + 1.0e-6:
            errors.append("proxy.gripToContactMeters cannot exceed proxy.lengthMeters.")
        if float(proxy["strikeSegmentStartMeters"]) >= float(proxy["strikeSegmentEndMeters"]):
            errors.append("proxy strike segment must have positive length.")
        if float(proxy["strikeSegmentEndMeters"]) > float(proxy["lengthMeters"]) + 1.0e-6:
            errors.append("proxy strike segment cannot exceed proxy.lengthMeters.")
    return errors


def _contact_distance_errors(proxy: Mapping[str, Any], trajectory: Mapping[str, Any]) -> list[str]:
    if validate_proxy(proxy) or not isinstance(trajectory, Mapping):
        return []
    errors = []
    family = str(trajectory.get("family", "CUSTOM"))
    proxy_class = str(proxy.get("class", ""))
    for index, control in enumerate(trajectory.get("controls", [])):
        if not isinstance(control, Mapping) or "contactDistanceMeters" not in control:
            continue
        distance = control.get("contactDistanceMeters")
        if not finite_number(distance):
            continue
        distance = float(distance)
        if distance > float(proxy["lengthMeters"]) + 1.0e-6:
            errors.append(f"trajectory.controls[{index}].contactDistanceMeters exceeds proxy length.")
        if family == "THRUST" or proxy_class == "ONE_HAND_BLUNT":
            if abs(distance - float(proxy["gripToContactMeters"])) > 1.0e-5:
                errors.append(f"trajectory.controls[{index}] must use the fixed tip/head contact distance for {family or proxy_class}.")
        elif not float(proxy["strikeSegmentStartMeters"]) - 1.0e-6 <= distance <= float(proxy["strikeSegmentEndMeters"]) + 1.0e-6:
            errors.append(f"trajectory.controls[{index}].contactDistanceMeters lies outside the authored strike segment.")
    return errors


def validate_controls(trajectory: Mapping[str, Any], *, master=False) -> list[str]:
    if not isinstance(trajectory, Mapping):
        return ["trajectory must be an object."]
    errors = []
    if trajectory.get("family") not in TRAJECTORY_FAMILIES:
        errors.append("trajectory.family is unsupported.")
    anchor = trajectory.get("contactAnchor", "CENTER")
    if anchor not in CONTACT_ANCHORS:
        errors.append("trajectory.contactAnchor is unsupported.")
    if not finite_vector(trajectory.get("expectedDirectionLocal")) or length(trajectory.get("expectedDirectionLocal", ())) <= _EPSILON:
        errors.append("trajectory.expectedDirectionLocal must be a nonzero finite vector.")
    controls = trajectory.get("controls")
    if not isinstance(controls, list):
        return errors + ["trajectory.controls must be an array."]
    ids = []
    position_field = "targetOffsetMeters" if master else "contactPointLocal"
    for index, control in enumerate(controls):
        if not isinstance(control, Mapping):
            errors.append(f"trajectory.controls[{index}] must be an object.")
            continue
        control_id = control.get("id")
        ids.append(control_id)
        if control_id not in CONTROL_IDS:
            errors.append(f"trajectory.controls[{index}].id is unsupported.")
        if not finite_vector(control.get(position_field)):
            errors.append(f"trajectory.controls[{index}].{position_field} must be a finite 3-vector.")
        axis = control.get("weaponAxisLocal")
        if not finite_vector(axis) or length(axis or ()) <= _EPSILON:
            errors.append(f"trajectory.controls[{index}].weaponAxisLocal must be a nonzero finite vector.")
        contact_distance = control.get("contactDistanceMeters")
        if contact_distance is not None and (not finite_number(contact_distance) or float(contact_distance) < 0.0):
            errors.append(f"trajectory.controls[{index}].contactDistanceMeters must be finite and nonnegative.")
    if tuple(ids) != CONTROL_IDS:
        errors.append("trajectory controls must contain the ordered START through END control set exactly once.")
    profiles = trajectory.get("weaponAxesByProxy", {}) if master else {}
    if not isinstance(profiles, Mapping):
        errors.append("trajectory.weaponAxesByProxy must be an object when present.")
    else:
        for proxy_class, profile in profiles.items():
            if proxy_class not in PROXY_CLASSES or not isinstance(profile, Mapping):
                errors.append("trajectory.weaponAxesByProxy contains an unsupported proxy profile.")
                continue
            if set(profile) != set(CONTROL_IDS):
                errors.append(f"trajectory.weaponAxesByProxy.{proxy_class} must define every control exactly once.")
                continue
            if any(not finite_vector(axis) or length(axis) <= _EPSILON for axis in profile.values()):
                errors.append(f"trajectory.weaponAxesByProxy.{proxy_class} contains an invalid axis.")
    return errors


def validate_motion_master(master: Mapping[str, Any]) -> list[str]:
    if not isinstance(master, Mapping):
        return ["Motion Master must be an object."]
    errors = []
    if master.get("schema") != MOTION_MASTER_SCHEMA or master.get("version") != 1:
        errors.append(f"Motion Master schema/version must be {MOTION_MASTER_SCHEMA} / 1.")
    if not isinstance(master.get("masterId"), str) or not _ID.fullmatch(master.get("masterId", "")):
        errors.append("Motion Master ID must be stable lowercase text.")
    if master.get("state") not in MASTER_STATES:
        errors.append("Motion Master state is unsupported.")
    if not isinstance(master.get("artistApproved"), bool):
        errors.append("Motion Master artistApproved must be boolean.")
    if master.get("state") == "BUILT_IN_STARTER" and master.get("artistApproved") is not False:
        errors.append("Built-in starter masters cannot claim artist approval.")
    if master.get("state") == "PROMOTED_MASTER" and master.get("artistApproved") is not True:
        errors.append("Promoted masters require deliberate artist approval.")
    if master.get("feel", "CUSTOM") not in MOTION_FEELS:
        errors.append("Motion Master feel is unsupported.")
    if not isinstance(master.get("label"), str) or not master.get("label", "").strip():
        errors.append("Motion Master label must be nonempty text.")
    if not str(master.get("actionKind", "")).startswith("ATTACK_"):
        errors.append("Motion Master actionKind must be an offensive ATTACK_ kind.")
    errors.extend(validate_target(master.get("target", {})))
    errors.extend(validate_proxy(master.get("proxy", {})))
    errors.extend(validate_controls(master.get("trajectory", {}), master=True))
    errors.extend(_contact_distance_errors(master.get("proxy", {}), master.get("trajectory", {})))
    errors.extend(_numeric_errors(master.get("timing", {}), {
        "windupSeconds": (0.10, 2.50),
        "activeSeconds": (0.08, 1.00),
        "recoverySeconds": (0.10, 3.00),
        "contactFractionOfActive": (0.05, 0.95),
    }, "timing"))
    errors.extend(_numeric_errors(master.get("style", {}), {name: (0.0, 2.0) for name in DEFAULT_STYLE}, "style"))
    errors.extend(_numeric_errors(master.get("solver", {}), {
        "ikChainLength": (2, 3),
        "poleSideMeters": (0.05, 2.0),
        "poleBackMeters": (-1.0, 1.0),
        "torsoSupport": (0.0, 2.0),
        "bakeStepFrames": (1, 4),
    }, "solver"))
    for name, bounds in {
        "minimumReachRatio": (0.20, 0.80),
        "comfortableReachRatio": (0.70, 0.94),
        "warningReachRatio": (0.70, 0.97),
        "hardReachRatio": (0.90, 0.9995),
        "maxShoulderSupportDegrees": (0.0, 12.0),
        "deformTranslationToleranceMeters": (0.000001, 0.01),
        "solveErrorToleranceMeters": (0.0001, 0.10),
    }.items():
        if name in master.get("solver", {}):
            errors.extend(_numeric_errors(master["solver"], {name: bounds}, "solver"))
    solver = master.get("solver", {})
    reach_names = ("comfortableReachRatio", "warningReachRatio", "hardReachRatio")
    if "minimumReachRatio" in solver:
        reach_names = ("minimumReachRatio", *reach_names)
    if all(finite_number(solver.get(name)) for name in reach_names):
        reach_values = tuple(float(solver[name]) for name in reach_names)
        if any(first > second for first, second in zip(reach_values, reach_values[1:])):
            errors.append("solver reach ratios must be ordered minimum <= comfortable <= warning <= hard.")
    if master.get("solver", {}).get("arm") not in {"RIGHT", "LEFT"}:
        errors.append("solver.arm must be RIGHT or LEFT.")
    errors.extend(_numeric_errors(master.get("tolerances", {}), {
        "planeErrorMeters": (0.01, 0.30),
        "contactFrameWindowFrames": (0.0, 5.0),
        "directionDotMinimum": (0.2, 0.99),
        "activeSamplingStepFrames": (0.1, 1.0),
    }, "tolerances"))
    return errors


def instantiate_motion_recipe(master: Mapping[str, Any], *, target=None, proxy=None, style=None, solver=None, tolerances=None) -> dict[str, Any]:
    errors = validate_motion_master(master)
    if errors:
        raise ValueError("Invalid Motion Master: " + " ".join(errors))
    resolved_target = deepcopy(master["target"])
    resolved_target.update(dict(target or {}))
    resolved_proxy = deepcopy(master["proxy"])
    resolved_proxy.update(dict(proxy or {}))
    family = str(master["trajectory"]["family"])
    anchor_kind = str(master["trajectory"].get("contactAnchor", "CENTER"))
    proxy_radius = float(resolved_proxy["headRadiusMeters"] if resolved_proxy["class"] == "ONE_HAND_BLUNT" else 0.015)
    anchor = target_contact_anchor(
        resolved_target,
        anchor_kind,
        master["trajectory"]["expectedDirectionLocal"],
        proxy_radius=proxy_radius,
    )
    axes_profile = master["trajectory"].get("weaponAxesByProxy", {}).get(resolved_proxy["class"], {})
    controls = []
    for source in master["trajectory"]["controls"]:
        if "contactDistanceMeters" in source:
            contact_distance = float(source["contactDistanceMeters"])
        elif str(master.get("builtInRevision", "")).startswith(("5.4.1-natural", "5.4.2-simple")):
            contact_distance = default_contact_distance(resolved_proxy, family)
        else:
            # A 5.4.0 saved/promoted master used gripToContactMeters for every
            # proxy class. Preserve that authored relationship unless an
            # explicit 5.4.1+ rebuild/reset records a strike-segment choice.
            contact_distance = float(resolved_proxy["gripToContactMeters"])
        record = {
            "id": source["id"],
            "contactPointLocal": [round(value, 7) for value in add(anchor, source["targetOffsetMeters"])],
            "weaponAxisLocal": [round(value, 7) for value in normalize(axes_profile.get(source["id"], source["weaponAxisLocal"]))],
            "contactDistanceMeters": round(contact_distance, 7),
        }
        controls.append(record)
    resolved_style = deepcopy(DEFAULT_STYLE)
    resolved_style.update(deepcopy(master.get("style", {})))
    resolved_style.update(dict(style or {}))
    resolved_solver = deepcopy(DEFAULT_SOLVER)
    resolved_solver.update(deepcopy(master.get("solver", {})))
    resolved_solver.update(dict(solver or {}))
    resolved_tolerances = deepcopy(DEFAULT_TOLERANCES)
    resolved_tolerances.update(deepcopy(master.get("tolerances", {})))
    resolved_tolerances.update(dict(tolerances or {}))
    return {
        "schema": MOTION_RECIPE_SCHEMA,
        "version": 1,
        "motionMasterId": master["masterId"],
        "motionMasterState": master["state"],
        "feel": str(master.get("feel", "CUSTOM")),
        "actionKind": master["actionKind"],
        "target": resolved_target,
        "proxy": resolved_proxy,
        "trajectory": {
            "family": family,
            "contactAnchor": anchor_kind,
            "expectedDirectionLocal": list(normalize(master["trajectory"]["expectedDirectionLocal"])),
            "controls": controls,
        },
        "timing": deepcopy(master["timing"]),
        "style": resolved_style,
        "solver": resolved_solver,
        "tolerances": resolved_tolerances,
        "contactFrame": 0,
        "provenance": {
            "sourceMasterLabel": master["label"],
            "sourceMasterArtistApproved": bool(master["artistApproved"]),
            "builtInRevision": str(master.get("builtInRevision", "5.4.0-or-promoted")),
        },
    }


def validate_motion_recipe(recipe: Mapping[str, Any]) -> list[str]:
    if not isinstance(recipe, Mapping):
        return ["Motion Studio recipe must be an object."]
    errors = []
    if recipe.get("schema") != MOTION_RECIPE_SCHEMA or recipe.get("version") != 1:
        errors.append(f"Motion Studio recipe schema/version must be {MOTION_RECIPE_SCHEMA} / 1.")
    if not isinstance(recipe.get("motionMasterId"), str) or not _ID.fullmatch(recipe.get("motionMasterId", "")):
        errors.append("Motion Studio recipe motionMasterId must be stable lowercase text.")
    if recipe.get("motionMasterState") not in MASTER_STATES:
        errors.append("Motion Studio recipe motionMasterState is unsupported.")
    if recipe.get("feel", "CUSTOM") not in MOTION_FEELS:
        errors.append("Motion Studio recipe feel is unsupported.")
    if not str(recipe.get("actionKind", "")).startswith("ATTACK_"):
        errors.append("Motion Studio recipe actionKind must use ATTACK_.")
    errors.extend(validate_target(recipe.get("target", {})))
    errors.extend(validate_proxy(recipe.get("proxy", {})))
    errors.extend(validate_controls(recipe.get("trajectory", {}), master=False))
    errors.extend(_contact_distance_errors(recipe.get("proxy", {}), recipe.get("trajectory", {})))
    errors.extend(_numeric_errors(recipe.get("timing", {}), {
        "windupSeconds": (0.10, 2.50),
        "activeSeconds": (0.08, 1.00),
        "recoverySeconds": (0.10, 3.00),
        "contactFractionOfActive": (0.05, 0.95),
    }, "timing"))
    errors.extend(_numeric_errors(recipe.get("style", {}), {name: (0.0, 2.0) for name in DEFAULT_STYLE}, "style"))
    errors.extend(_numeric_errors(recipe.get("solver", {}), {
        "ikChainLength": (2, 3),
        "poleSideMeters": (0.05, 2.0),
        "poleBackMeters": (-1.0, 1.0),
        "torsoSupport": (0.0, 2.0),
        "bakeStepFrames": (1, 4),
    }, "solver"))
    for name, bounds in {
        "minimumReachRatio": (0.20, 0.80),
        "comfortableReachRatio": (0.70, 0.94),
        "warningReachRatio": (0.70, 0.97),
        "hardReachRatio": (0.90, 0.9995),
        "maxShoulderSupportDegrees": (0.0, 12.0),
        "deformTranslationToleranceMeters": (0.000001, 0.01),
        "solveErrorToleranceMeters": (0.0001, 0.10),
    }.items():
        if name in recipe.get("solver", {}):
            errors.extend(_numeric_errors(recipe["solver"], {name: bounds}, "solver"))
    solver = recipe.get("solver", {})
    reach_names = ("comfortableReachRatio", "warningReachRatio", "hardReachRatio")
    if "minimumReachRatio" in solver:
        reach_names = ("minimumReachRatio", *reach_names)
    if all(finite_number(solver.get(name)) for name in reach_names):
        reach_values = tuple(float(solver[name]) for name in reach_names)
        if any(first > second for first, second in zip(reach_values, reach_values[1:])):
            errors.append("solver reach ratios must be ordered minimum <= comfortable <= warning <= hard.")
    if recipe.get("solver", {}).get("arm") not in {"RIGHT", "LEFT"}:
        errors.append("solver.arm must be RIGHT or LEFT.")
    errors.extend(_numeric_errors(recipe.get("tolerances", {}), {
        "planeErrorMeters": (0.01, 0.30),
        "contactFrameWindowFrames": (0.0, 5.0),
        "directionDotMinimum": (0.2, 0.99),
        "activeSamplingStepFrames": (0.1, 1.0),
    }, "tolerances"))
    if not isinstance(recipe.get("contactFrame"), int) or int(recipe.get("contactFrame", 0)) < 0:
        errors.append("contactFrame must be a nonnegative integer.")
    return errors


def stamp_json(owner, property_name: str, value: Mapping[str, Any]):
    owner[property_name] = stable_json(dict(value))
    return owner


def read_json(owner, property_name: str, label: str) -> dict[str, Any] | None:
    raw = owner.get(property_name, "")
    if not raw:
        return None
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError(f"{label} is not valid JSON.") from None
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


def stamp_motion_recipe(action, recipe: Mapping[str, Any]):
    errors = validate_motion_recipe(recipe)
    if errors:
        raise ValueError("Invalid Motion Studio recipe: " + " ".join(errors))
    return stamp_json(action, MOTION_RECIPE_PROPERTY, recipe)


def read_motion_recipe(action) -> dict[str, Any] | None:
    value = read_json(action, MOTION_RECIPE_PROPERTY, "Motion Studio recipe")
    if value is None:
        return None
    errors = validate_motion_recipe(value)
    if errors:
        raise ValueError("Invalid Motion Studio recipe: " + " ".join(errors))
    return deepcopy(value)


def control_frame_schedule(recipe: Mapping[str, Any], fps: float, *, start=1) -> dict[str, int]:
    fps = max(float(fps), 0.001)
    timing = recipe["timing"]
    active_start = int(start) + max(1, round(float(timing["windupSeconds"]) * fps))
    active_end = active_start + max(1, round(float(timing["activeSeconds"]) * fps))
    end = active_end + max(1, round(float(timing["recoverySeconds"]) * fps))
    contact = active_start + max(1, round((active_end - active_start) * float(timing["contactFractionOfActive"])))
    contact = min(contact, active_end - 1 if active_end - active_start > 1 else active_end)
    anticipation = int(start) + max(1, round((active_start - int(start)) * 0.62))
    follow = active_end + max(1, round((end - active_end) * 0.48))
    return {
        "START": int(start),
        "ANTICIPATION": anticipation,
        "PRE_CONTACT": active_start,
        "CONTACT": contact,
        "POST_CONTACT": active_end,
        "FOLLOW_THROUGH": min(follow, end),
        "END": end,
        "activeStart": active_start,
        "activeEnd": active_end,
    }


def _control_tangents(values: Sequence[Sequence[float]], frames: Sequence[float], index: int):
    if index <= 0:
        dt = max(frames[1] - frames[0], _EPSILON)
        return multiply(subtract(values[1], values[0]), 1.0 / dt)
    if index >= len(values) - 1:
        dt = max(frames[-1] - frames[-2], _EPSILON)
        return multiply(subtract(values[-1], values[-2]), 1.0 / dt)
    dt = max(frames[index + 1] - frames[index - 1], _EPSILON)
    return multiply(subtract(values[index + 1], values[index - 1]), 1.0 / dt)


def interpolate_trajectory(recipe: Mapping[str, Any], frame: float, schedule: Mapping[str, int]):
    controls = recipe["trajectory"]["controls"]
    frames = [float(schedule[control_id]) for control_id in CONTROL_IDS]
    points = [vector(control["contactPointLocal"]) for control in controls]
    axes = [normalize(control["weaponAxisLocal"]) for control in controls]
    contact_distances = [
        # Missing means a persisted 5.4.0 recipe, whose contact law was the
        # proxy's single gripToContactMeters point for every weapon class.
        float(control.get("contactDistanceMeters", recipe["proxy"]["gripToContactMeters"]))
        for control in controls
    ]
    frame = clamp(float(frame), frames[0], frames[-1])
    segment = next((index for index in range(len(frames) - 1) if frame <= frames[index + 1]), len(frames) - 2)
    start_frame, end_frame = frames[segment], frames[segment + 1]
    duration = max(end_frame - start_frame, _EPSILON)
    factor = clamp((frame - start_frame) / duration)
    first = points[segment]
    second = points[segment + 1]
    smooth = factor * factor * (3.0 - 2.0 * factor)
    # Segment-bounded smooth interpolation cannot create the large off-path
    # overshoots that previously folded the wrist through the shoulder during
    # recovery. It is C1 at every named control and deliberately eases through
    # reversals instead of snapping across them.
    point = lerp(first, second, smooth)
    axis = normalize(lerp(axes[segment], axes[segment + 1], smooth))
    contact_distance = (1.0 - smooth) * contact_distances[segment] + smooth * contact_distances[segment + 1]
    contact_distance = clamp(
        contact_distance,
        0.0,
        float(recipe["proxy"]["lengthMeters"]),
    )
    return {
        "contactPointLocal": point,
        "weaponAxisLocal": axis,
        "contactDistanceMeters": contact_distance,
    }


def _sample_phase(frame: float, schedule: Mapping[str, int]) -> str:
    if frame < float(schedule["activeStart"]):
        return "WINDUP"
    if frame <= float(schedule["activeEnd"]):
        return "ACTIVE"
    return "RECOVERY"


def ideal_trajectory_samples(recipe: Mapping[str, Any], fps: float = 24.0, step=0.25) -> list[dict[str, Any]]:
    schedule = control_frame_schedule(recipe, fps)
    samples = []
    frame = float(schedule["START"])
    while frame <= float(schedule["END"]) + _EPSILON:
        pose = interpolate_trajectory(recipe, frame, schedule)
        axis = pose["weaponAxisLocal"]
        contact = pose["contactPointLocal"]
        proxy = recipe["proxy"]
        contact_distance = float(pose["contactDistanceMeters"])
        grip = subtract(contact, multiply(axis, contact_distance))
        strike_start = add(grip, multiply(axis, float(proxy["strikeSegmentStartMeters"])))
        strike_end = add(grip, multiply(axis, float(proxy["strikeSegmentEndMeters"])))
        samples.append({
            "frame": frame,
            "timeSeconds": (frame - schedule["START"]) / max(float(fps), 0.001),
            "phase": _sample_phase(frame, schedule),
            "contactPointLocal": list(contact),
            "strikeStartLocal": list(strike_start),
            "strikeEndLocal": list(strike_end),
            "weaponAxisLocal": list(axis),
            "contactDistanceMeters": contact_distance,
        })
        frame += max(float(step), 0.05)
    return samples


def validate_baked_trajectory(recipe: Mapping[str, Any], samples: Sequence[Mapping[str, Any]], *, input_digest="") -> dict[str, Any]:
    recipe_errors = validate_motion_recipe(recipe)
    if recipe_errors:
        return {
            "schema": MOTION_VALIDATION_SCHEMA,
            "status": "FAIL",
            "inputDigest": str(input_digest),
            "errors": recipe_errors,
        }
    if not samples:
        return {
            "schema": MOTION_VALIDATION_SCHEMA,
            "status": "FAIL",
            "inputDigest": str(input_digest),
            "errors": ["The baked Action produced no weapon-path samples."],
        }
    target = recipe["target"]
    proxy = recipe["proxy"]
    volume = target_zone_volume(target)
    target_center = target_zone_center(target)
    family = recipe["trajectory"]["family"]
    expected = normalize(recipe["trajectory"]["expectedDirectionLocal"])
    geometry = trajectory_geometry(family, target_center, expected)
    proxy_radius = float(proxy["headRadiusMeters"] if proxy["class"] == "ONE_HAND_BLUNT" else 0.015)
    evaluations = []
    for sample in samples:
        if family == "THRUST":
            clearance, weapon_point, target_axis_point = point_volume_distance(
                sample["contactPointLocal"], volume
            )
        else:
            clearance, weapon_point, target_axis_point = segment_volume_distance(
                sample["strikeStartLocal"], sample["strikeEndLocal"], volume
            )
        clearance -= proxy_radius
        evaluations.append({
            "sample": sample,
            "clearance": float(clearance),
            "weaponPoint": weapon_point,
            "targetAxisPoint": target_axis_point,
            "planeError": trajectory_error(sample["contactPointLocal"], geometry),
        })
    active = [record for record in evaluations if record["sample"].get("phase") == "ACTIVE"]
    windup = [record for record in evaluations if record["sample"].get("phase") == "WINDUP"]
    recovery = [record for record in evaluations if record["sample"].get("phase") == "RECOVERY"]
    active_closest = min(active, key=lambda record: record["clearance"]) if active else None
    closest = min(evaluations, key=lambda record: record["clearance"])
    contacts = [record for record in evaluations if record["clearance"] <= 0.0]
    active_contacts = [record for record in active if record["clearance"] <= 0.0]
    intended = min(evaluations, key=lambda record: abs(float(record["sample"]["frame"]) - float(recipe["contactFrame"])))
    active_start = active[0]["sample"]["contactPointLocal"] if active else samples[0]["contactPointLocal"]
    active_end = active[-1]["sample"]["contactPointLocal"] if active else samples[-1]["contactPointLocal"]
    actual_direction = normalize(subtract(active_end, active_start), fallback=expected)
    direction_dot = dot(actual_direction, expected)
    active_displacement = subtract(active_end, active_start)
    active_distance = max(length(active_displacement), _EPSILON)
    plane_error = max((record["planeError"] for record in active), default=0.0)
    windup_intersection = any(record["clearance"] <= 0.0 for record in windup)
    recovery_intersections = [record for record in recovery if record["clearance"] <= 0.0]
    recovery_buried = bool(recovery) and len(recovery_intersections) == len(recovery)
    errors = []
    zone = target["zone"]
    miss = max(0.0, float(active_closest["clearance"])) if active_closest else float("inf")
    if not active_contacts:
        errors.append(f"Weapon contact point missed {zone} by {miss:.2f} m during ACTIVE.")
    if intended["clearance"] > 0.0:
        errors.append(
            f"Intended CONTACT frame {int(recipe['contactFrame'])} missed {zone} by {intended['clearance']:.2f} m."
        )
    if plane_error > float(recipe["tolerances"]["planeErrorMeters"]):
        errors.append(
            f"Baked weapon path deviated {plane_error:.2f} m from the intended {family} geometry; "
            f"tolerance is {float(recipe['tolerances']['planeErrorMeters']):.2f} m."
        )
    if direction_dot < float(recipe["tolerances"]["directionDotMinimum"]):
        errors.append(f"Baked trajectory moved in the wrong direction for {family} (dot {direction_dot:.2f}).")
    if windup_intersection:
        errors.append("Weapon intersects the intended target during WINDUP before commitment.")
    if recovery_buried:
        errors.append("Weapon remains buried in the intended target throughout RECOVERY.")
    family_checks = {}
    if family == "OVERHEAD_VERTICAL":
        vertical_ratio = max(0.0, -float(active_displacement[2])) / active_distance
        family_checks["descendingRatio"] = vertical_ratio
        if float(active_displacement[2]) >= -0.08 or vertical_ratio < 0.60:
            errors.append("OVERHEAD ACTIVE motion did not descend primarily through the target.")
    elif family == "THRUST":
        forward_ratio = max(0.0, float(active_displacement[1])) / active_distance
        family_checks["forwardRatio"] = forward_ratio
        if float(active_displacement[1]) <= 0.08 or forward_ratio < 0.72:
            errors.append("THRUST ACTIVE motion did not advance primarily along canonical +Y.")
    elif family == "HORIZONTAL":
        lateral_ratio = abs(float(active_displacement[0])) / active_distance
        family_checks["lateralRatio"] = lateral_ratio
        if lateral_ratio < 0.72:
            errors.append("HORIZONTAL ACTIVE motion did not cross the target primarily laterally.")
    elif family == "DIAGONAL_DOWN":
        diagonal_ratio = (abs(float(active_displacement[0])) + max(0.0, -float(active_displacement[2]))) / (math.sqrt(2.0) * active_distance)
        family_checks["diagonalRatio"] = diagonal_ratio
        if float(active_displacement[2]) >= -0.06 or diagonal_ratio < 0.58:
            errors.append("DIAGONAL_DOWN ACTIVE motion did not cross high-to-low.")
    contact_record = active_contacts[0] if active_contacts else active_closest or closest
    return {
        "schema": MOTION_VALIDATION_SCHEMA,
        "status": "FAIL" if errors else "PASS",
        "inputDigest": str(input_digest),
        "targetZone": zone,
        "trajectoryFamily": family,
        "sampleCount": len(samples),
        "targetContact": bool(contacts),
        "activeContact": bool(active_contacts),
        "intendedContact": intended["clearance"] <= 0.0,
        "contactFrame": float(contact_record["sample"]["frame"]),
        "contactTimeSeconds": round(float(contact_record["sample"]["timeSeconds"]), 6),
        "closestFrame": float(closest["sample"]["frame"]),
        "activeMissDistanceMeters": round(miss, 6),
        "closestClearanceMeters": round(float(closest["clearance"]), 6),
        "closestWeaponPointLocal": [round(float(value), 7) for value in closest["weaponPoint"]],
        "closestTargetAxisPointLocal": [round(float(value), 7) for value in closest["targetAxisPoint"]],
        "planeErrorMeters": round(plane_error, 6),
        "planeToleranceMeters": float(recipe["tolerances"]["planeErrorMeters"]),
        "directionDot": round(direction_dot, 6),
        "expectedDirectionLocal": list(expected),
        "actualDirectionLocal": list(actual_direction),
        "windupIntersected": windup_intersection,
        "recoveryBuried": recovery_buried,
        "familyChecks": family_checks,
        "errors": errors,
    }


def targeting_metadata(recipe: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    if validation.get("status") != "PASS" or not validation.get("activeContact"):
        raise ValueError("Targeting metadata requires a successful ACTIVE baked-path validation.")
    target = recipe["target"]
    center = target_zone_center(target)
    volume = target_zone_volume(target)
    target_radius = float(volume["radiusMeters"])
    record = {
        "schema": TARGETING_SCHEMA,
        "targetZone": target["zone"],
        "preferredTargetOffsetLocal": [round(float(value), 6) for value in center],
        "preferredDistanceMeters": round(float(target["distanceMeters"]), 6),
        "preferredContactHeightMeters": round(float(center[2]), 6),
        "horizontalToleranceMeters": round(target_radius, 6),
        "verticalToleranceMeters": round(
            target_radius if volume["type"] == "SPHERE" else float(target["zoneHalfHeightMeters"]) + target_radius,
            6,
        ),
        "depthToleranceMeters": round(target_radius, 6),
        "trajectoryFamily": recipe["trajectory"]["family"],
        "contactTimeSeconds": round(float(validation["contactTimeSeconds"]), 6),
        "proxyReachMeters": round(float(recipe["proxy"]["gripToContactMeters"]), 6),
    }
    errors = validate_targeting_metadata(record)
    if errors:
        raise ValueError("Invalid targeting metadata: " + " ".join(errors))
    return record


def validate_targeting_metadata(record: Mapping[str, Any]) -> list[str]:
    if not isinstance(record, Mapping):
        return ["Targeting metadata must be an object."]
    errors = []
    if record.get("schema") != TARGETING_SCHEMA:
        errors.append(f"schema must be {TARGETING_SCHEMA}.")
    if record.get("targetZone") not in TARGET_ZONES:
        errors.append("targetZone is unsupported.")
    if record.get("trajectoryFamily") not in TRAJECTORY_FAMILIES:
        errors.append("trajectoryFamily is unsupported.")
    if not finite_vector(record.get("preferredTargetOffsetLocal")):
        errors.append("preferredTargetOffsetLocal must be a finite 3-vector.")
    for name in (
        "preferredDistanceMeters",
        "preferredContactHeightMeters",
        "horizontalToleranceMeters",
        "verticalToleranceMeters",
        "depthToleranceMeters",
        "contactTimeSeconds",
        "proxyReachMeters",
    ):
        if not finite_number(record.get(name)) or float(record.get(name, -1.0)) < 0.0:
            errors.append(f"{name} must be finite and nonnegative.")
    return errors


def promoted_master_from_recipe(recipe: Mapping[str, Any], master_id: str, label: str, *, source_action="", source_clip_id=""):
    errors = validate_motion_recipe(recipe)
    if errors:
        raise ValueError("Invalid Motion Studio recipe: " + " ".join(errors))
    anchor_kind = str(recipe["trajectory"].get("contactAnchor", "CENTER"))
    proxy_radius = float(recipe["proxy"]["headRadiusMeters"] if recipe["proxy"]["class"] == "ONE_HAND_BLUNT" else 0.015)
    anchor = target_contact_anchor(
        recipe["target"],
        anchor_kind,
        recipe["trajectory"]["expectedDirectionLocal"],
        proxy_radius=proxy_radius,
    )
    controls = []
    for control in recipe["trajectory"]["controls"]:
        record = {
            "id": control["id"],
            "targetOffsetMeters": [round(float(value), 7) for value in subtract(control["contactPointLocal"], anchor)],
            "weaponAxisLocal": [round(float(value), 7) for value in normalize(control["weaponAxisLocal"])],
        }
        if "contactDistanceMeters" in control:
            record["contactDistanceMeters"] = round(float(control["contactDistanceMeters"]), 7)
        controls.append(record)
    master = {
        "schema": MOTION_MASTER_SCHEMA,
        "version": 1,
        "masterId": str(master_id),
        "label": str(label),
        "state": "PROMOTED_MASTER",
        "artistApproved": True,
        "feel": str(recipe.get("feel", "CUSTOM")),
        "actionKind": recipe["actionKind"],
        "target": deepcopy(recipe["target"]),
        "proxy": deepcopy(recipe["proxy"]),
        "trajectory": {
            "family": recipe["trajectory"]["family"],
            "contactAnchor": anchor_kind,
            "expectedDirectionLocal": deepcopy(recipe["trajectory"]["expectedDirectionLocal"]),
            "controls": controls,
        },
        "timing": deepcopy(recipe["timing"]),
        "style": deepcopy(recipe["style"]),
        "solver": deepcopy(recipe["solver"]),
        "tolerances": deepcopy(recipe["tolerances"]),
        "source": {"actionName": str(source_action), "clipId": str(source_clip_id)},
    }
    master_errors = validate_motion_master(master)
    if master_errors:
        raise ValueError("Invalid promoted Motion Master: " + " ".join(master_errors))
    return master


def builtin_master(master_id: str) -> dict[str, Any]:
    try:
        return deepcopy(BUILTIN_MOTION_MASTERS[str(master_id)])
    except KeyError:
        raise ValueError(f"Unknown Motion Master {master_id!r}.") from None


for _builtin in BUILTIN_MOTION_MASTERS.values():
    _errors = validate_motion_master(_builtin)
    if _errors:  # Fail at import so a malformed shipped master cannot hide.
        raise RuntimeError("Invalid built-in Motion Master: " + " ".join(_errors))


__all__ = (
    "BUILTIN_MOTION_MASTERS",
    "CONTROL_IDS",
    "CONTACT_ANCHORS",
    "DEFAULT_PROXY",
    "DEFAULT_SOLVER",
    "DEFAULT_STYLE",
    "DEFAULT_TARGET",
    "DEFAULT_TOLERANCES",
    "MOTION_FEELS",
    "MOTION_POSE_HEALTH_PROPERTY",
    "MOTION_POSE_HEALTH_SCHEMA",
    "MASTER_STATES",
    "MOTION_MASTER_LIBRARY_PROPERTY",
    "MOTION_MASTER_LIBRARY_SCHEMA",
    "MOTION_MASTER_PROPERTY",
    "MOTION_MASTER_SCHEMA",
    "MOTION_RECIPE_PROPERTY",
    "MOTION_RECIPE_SCHEMA",
    "MOTION_VALIDATION_PROPERTY",
    "MOTION_VALIDATION_SCHEMA",
    "PROXY_CLASSES",
    "PROXY_CLASS_DEFAULTS",
    "STYLE_PRESETS",
    "TARGETING_PROPERTY",
    "TARGETING_SCHEMA",
    "TARGET_ZONES",
    "TRAJECTORY_FAMILIES",
    "add",
    "arm_reach_model",
    "body_support_envelope",
    "builtin_master",
    "control_frame_schedule",
    "default_contact_distance",
    "elbow_bend_degrees",
    "ideal_trajectory_samples",
    "instantiate_motion_recipe",
    "interpolate_trajectory",
    "normalize",
    "point_volume_distance",
    "point_segment_distance",
    "proxy_defaults",
    "promoted_master_from_recipe",
    "read_json",
    "read_motion_recipe",
    "reach_requirement",
    "segment_segment_closest",
    "segment_volume_distance",
    "stable_digest",
    "stable_json",
    "select_strike_contact_distance",
    "stamp_json",
    "stamp_motion_recipe",
    "subtract",
    "target_zone_center",
    "target_contact_anchor",
    "target_zone_volume",
    "targeting_metadata",
    "trajectory_error",
    "trajectory_geometry",
    "validate_baked_trajectory",
    "validate_motion_master",
    "validate_motion_recipe",
    "validate_proxy",
    "validate_target",
    "validate_targeting_metadata",
    "vector",
)
