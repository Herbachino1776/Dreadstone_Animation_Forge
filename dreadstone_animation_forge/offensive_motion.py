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
TARGETING_SCHEMA = "dreadstone.offensive_targeting.v1"
TARGETING_PROPERTY = "dsb_offensive_targeting_json"

TARGET_ZONES = frozenset({"HEAD", "UPPER_TORSO", "CENTER_MASS", "LOW_TORSO", "CUSTOM"})
TRAJECTORY_FAMILIES = frozenset({"HORIZONTAL", "DIAGONAL_DOWN", "OVERHEAD_VERTICAL", "THRUST", "CUSTOM"})
PROXY_CLASSES = frozenset({"ONE_HAND_BLADE", "ONE_HAND_BLUNT", "SHORT_BLADE", "TWO_HAND_GENERIC"})
MASTER_STATES = frozenset({"BUILT_IN_STARTER", "PROMOTED_MASTER"})
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

DEFAULT_PROXY = {
    "class": "ONE_HAND_BLUNT",
    "lengthMeters": 0.74,
    "gripToContactMeters": 0.64,
    "strikeSegmentStartMeters": 0.54,
    "strikeSegmentEndMeters": 0.74,
    "headRadiusMeters": 0.075,
}

DEFAULT_STYLE = {
    "anticipation": 1.0,
    "torsoPower": 1.0,
    "stanceCompression": 1.0,
    "followThrough": 1.0,
    "recovery": 1.0,
    "armExtension": 1.0,
    "elbowStyle": 1.0,
    "wristStyle": 1.0,
}

DEFAULT_SOLVER = {
    "arm": "RIGHT",
    "ikChainLength": 3,
    "poleSideMeters": 0.48,
    "poleBackMeters": 0.12,
    "torsoSupport": 1.0,
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
) -> dict[str, Any]:
    target = deepcopy(DEFAULT_TARGET)
    target["zone"] = target_zone
    target["distanceMeters"] = float(target_distance)
    proxy = deepcopy(DEFAULT_PROXY)
    proxy["class"] = proxy_class
    if proxy_class == "ONE_HAND_BLADE":
        proxy.update({
            "lengthMeters": 0.82,
            "gripToContactMeters": 0.70,
            "strikeSegmentStartMeters": 0.18,
            "strikeSegmentEndMeters": 0.82,
            "headRadiusMeters": 0.025,
        })
    return {
        "schema": MOTION_MASTER_SCHEMA,
        "version": 1,
        "masterId": master_id,
        "label": label,
        "state": "BUILT_IN_STARTER",
        "artistApproved": False,
        "actionKind": action_kind,
        "target": target,
        "proxy": proxy,
        "trajectory": {
            "family": family,
            "expectedDirectionLocal": [float(value) for value in _unit(direction)],
            "controls": [_control(*value) for value in controls],
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


# Target-relative contact-point controls.  CONTACT is exactly the selected
# mathematical target center.  PRE/POST controls define the dangerous ACTIVE
# crossing; START/ANTICIPATION/FOLLOW/END define readability around it.
BUILTIN_MOTION_MASTERS = {
    "builtin_1h_slash_rtl": _master(
        "builtin_1h_slash_rtl",
        "1H Slash Right to Left",
        "ATTACK_SLASH_RTL_ONE_HAND",
        "UPPER_TORSO",
        "HORIZONTAL",
        (-1.0, 0.0, 0.0),
        (
            ("START", (0.42, -0.55, -0.08), (-0.45, 0.08, -0.89)),
            ("ANTICIPATION", (0.76, -0.28, 0.26), (-0.70, 0.08, -0.71)),
            ("PRE_CONTACT", (0.54, -0.01, 0.02), (-0.80, 0.06, -0.60)),
            ("CONTACT", (0.0, 0.0, 0.0), (-0.82, 0.06, -0.57)),
            ("POST_CONTACT", (-0.56, 0.02, -0.02), (-0.70, 0.05, -0.71)),
            ("FOLLOW_THROUGH", (-0.74, -0.24, -0.18), (-0.40, 0.04, -0.92)),
            ("END", (0.38, -0.56, -0.10), (-0.45, 0.08, -0.89)),
        ),
        proxy_class="ONE_HAND_BLADE",
        timing=(0.46, 0.30, 0.58),
    ),
    "builtin_1h_slash_ltr": _master(
        "builtin_1h_slash_ltr",
        "1H Slash Left to Right",
        "ATTACK_SLASH_LTR_ONE_HAND",
        "UPPER_TORSO",
        "HORIZONTAL",
        (1.0, 0.0, 0.0),
        (
            ("START", (0.38, -0.56, -0.10), (0.38, 0.08, -0.92)),
            ("ANTICIPATION", (-0.68, -0.25, 0.22), (0.62, 0.08, -0.78)),
            ("PRE_CONTACT", (-0.52, -0.01, 0.02), (0.72, 0.06, -0.69)),
            ("CONTACT", (0.0, 0.0, 0.0), (0.72, 0.06, -0.69)),
            ("POST_CONTACT", (0.55, 0.02, -0.02), (0.58, 0.05, -0.81)),
            ("FOLLOW_THROUGH", (0.72, -0.20, -0.18), (0.30, 0.04, -0.95)),
            ("END", (0.38, -0.56, -0.10), (0.38, 0.08, -0.92)),
        ),
        proxy_class="ONE_HAND_BLADE",
        timing=(0.48, 0.30, 0.56),
    ),
    "builtin_1h_overhead": _master(
        "builtin_1h_overhead",
        "1H Overhead",
        "ATTACK_OVERHEAD_ONE_HAND",
        "UPPER_TORSO",
        "OVERHEAD_VERTICAL",
        (0.0, 0.0, -1.0),
        (
            ("START", (0.42, -0.58, -0.02), (-0.42, 0.06, -0.90)),
            ("ANTICIPATION", (0.34, -0.42, 0.98), (-0.20, 0.10, -0.97)),
            ("PRE_CONTACT", (0.05, -0.02, 0.58), (-0.20, 0.11, -0.97)),
            ("CONTACT", (0.0, 0.0, 0.0), (-0.22, 0.12, -0.97)),
            ("POST_CONTACT", (-0.03, 0.02, -0.56), (-0.23, 0.10, -0.97)),
            ("FOLLOW_THROUGH", (-0.22, -0.22, -0.62), (-0.30, 0.06, -0.95)),
            ("END", (0.40, -0.56, -0.04), (-0.42, 0.06, -0.90)),
        ),
        proxy_class="ONE_HAND_BLUNT",
        timing=(0.58, 0.26, 0.66),
    ),
    "builtin_1h_heavy_diagonal": _master(
        "builtin_1h_heavy_diagonal",
        "1H Heavy Diagonal",
        "ATTACK_HEAVY_ONE_HAND",
        "CENTER_MASS",
        "DIAGONAL_DOWN",
        (-0.70, 0.0, -0.70),
        (
            ("START", (0.42, -0.55, 0.04), (-0.42, 0.08, -0.90)),
            ("ANTICIPATION", (0.66, -0.30, 0.72), (-0.42, 0.09, -0.90)),
            ("PRE_CONTACT", (0.48, -0.01, 0.48), (-0.48, 0.08, -0.87)),
            ("CONTACT", (0.0, 0.0, 0.0), (-0.50, 0.08, -0.86)),
            ("POST_CONTACT", (-0.47, 0.02, -0.46), (-0.52, 0.07, -0.85)),
            ("FOLLOW_THROUGH", (-0.62, -0.20, -0.62), (-0.35, 0.05, -0.94)),
            ("END", (0.40, -0.54, -0.02), (-0.42, 0.08, -0.90)),
        ),
        proxy_class="ONE_HAND_BLUNT",
        timing=(0.72, 0.34, 0.78),
    ),
    "builtin_1h_thrust": _master(
        "builtin_1h_thrust",
        "1H Thrust",
        "ATTACK_THRUST_ONE_HAND",
        "CENTER_MASS",
        "THRUST",
        (0.0, 1.0, 0.0),
        (
            ("START", (0.30, -0.62, 0.02), (0.05, 0.99, -0.10)),
            ("ANTICIPATION", (0.16, -0.68, 0.06), (0.02, 0.99, -0.08)),
            ("PRE_CONTACT", (0.02, -0.50, 0.02), (0.0, 1.0, 0.0)),
            ("CONTACT", (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            ("POST_CONTACT", (-0.01, 0.30, -0.01), (0.0, 1.0, 0.0)),
            ("FOLLOW_THROUGH", (0.04, -0.26, -0.04), (0.0, 1.0, 0.0)),
            ("END", (0.30, -0.62, 0.02), (0.05, 0.99, -0.10)),
        ),
        proxy_class="ONE_HAND_BLADE",
        target_distance=0.84,
        timing=(0.42, 0.26, 0.52),
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


def validate_controls(trajectory: Mapping[str, Any], *, master=False) -> list[str]:
    if not isinstance(trajectory, Mapping):
        return ["trajectory must be an object."]
    errors = []
    if trajectory.get("family") not in TRAJECTORY_FAMILIES:
        errors.append("trajectory.family is unsupported.")
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
    if tuple(ids) != CONTROL_IDS:
        errors.append("trajectory controls must contain the ordered START through END control set exactly once.")
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
    if not isinstance(master.get("label"), str) or not master.get("label", "").strip():
        errors.append("Motion Master label must be nonempty text.")
    if not str(master.get("actionKind", "")).startswith("ATTACK_"):
        errors.append("Motion Master actionKind must be an offensive ATTACK_ kind.")
    errors.extend(validate_target(master.get("target", {})))
    errors.extend(validate_proxy(master.get("proxy", {})))
    errors.extend(validate_controls(master.get("trajectory", {}), master=True))
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
    center = target_zone_center(resolved_target)
    controls = []
    for source in master["trajectory"]["controls"]:
        controls.append({
            "id": source["id"],
            "contactPointLocal": [round(value, 7) for value in add(center, source["targetOffsetMeters"])],
            "weaponAxisLocal": [round(value, 7) for value in normalize(source["weaponAxisLocal"])],
        })
    resolved_style = deepcopy(master.get("style", DEFAULT_STYLE))
    resolved_style.update(dict(style or {}))
    resolved_solver = deepcopy(master.get("solver", DEFAULT_SOLVER))
    resolved_solver.update(dict(solver or {}))
    resolved_tolerances = deepcopy(master.get("tolerances", DEFAULT_TOLERANCES))
    resolved_tolerances.update(dict(tolerances or {}))
    return {
        "schema": MOTION_RECIPE_SCHEMA,
        "version": 1,
        "motionMasterId": master["masterId"],
        "motionMasterState": master["state"],
        "actionKind": master["actionKind"],
        "target": resolved_target,
        "proxy": resolved_proxy,
        "trajectory": {
            "family": master["trajectory"]["family"],
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
    if not str(recipe.get("actionKind", "")).startswith("ATTACK_"):
        errors.append("Motion Studio recipe actionKind must use ATTACK_.")
    errors.extend(validate_target(recipe.get("target", {})))
    errors.extend(validate_proxy(recipe.get("proxy", {})))
    errors.extend(validate_controls(recipe.get("trajectory", {}), master=False))
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
    frame = clamp(float(frame), frames[0], frames[-1])
    segment = next((index for index in range(len(frames) - 1) if frame <= frames[index + 1]), len(frames) - 2)
    start_frame, end_frame = frames[segment], frames[segment + 1]
    duration = max(end_frame - start_frame, _EPSILON)
    factor = clamp((frame - start_frame) / duration)
    first = points[segment]
    second = points[segment + 1]
    tangent_first = _control_tangents(points, frames, segment)
    tangent_second = _control_tangents(points, frames, segment + 1)
    t2 = factor * factor
    t3 = t2 * factor
    h00 = 2.0 * t3 - 3.0 * t2 + 1.0
    h10 = t3 - 2.0 * t2 + factor
    h01 = -2.0 * t3 + 3.0 * t2
    h11 = t3 - t2
    point = add(
        add(multiply(first, h00), multiply(tangent_first, h10 * duration)),
        add(multiply(second, h01), multiply(tangent_second, h11 * duration)),
    )
    axis = normalize(lerp(axes[segment], axes[segment + 1], factor))
    return {"contactPointLocal": point, "weaponAxisLocal": axis}


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
        grip = subtract(contact, multiply(axis, float(proxy["gripToContactMeters"])))
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
    center = target_zone_center(recipe["target"])
    controls = []
    for control in recipe["trajectory"]["controls"]:
        controls.append({
            "id": control["id"],
            "targetOffsetMeters": [round(float(value), 7) for value in subtract(control["contactPointLocal"], center)],
            "weaponAxisLocal": [round(float(value), 7) for value in normalize(control["weaponAxisLocal"])],
        })
    master = {
        "schema": MOTION_MASTER_SCHEMA,
        "version": 1,
        "masterId": str(master_id),
        "label": str(label),
        "state": "PROMOTED_MASTER",
        "artistApproved": True,
        "actionKind": recipe["actionKind"],
        "target": deepcopy(recipe["target"]),
        "proxy": deepcopy(recipe["proxy"]),
        "trajectory": {
            "family": recipe["trajectory"]["family"],
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
    "DEFAULT_PROXY",
    "DEFAULT_SOLVER",
    "DEFAULT_STYLE",
    "DEFAULT_TARGET",
    "DEFAULT_TOLERANCES",
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
    "TARGETING_PROPERTY",
    "TARGETING_SCHEMA",
    "TARGET_ZONES",
    "TRAJECTORY_FAMILIES",
    "add",
    "builtin_master",
    "control_frame_schedule",
    "ideal_trajectory_samples",
    "instantiate_motion_recipe",
    "interpolate_trajectory",
    "normalize",
    "point_volume_distance",
    "point_segment_distance",
    "promoted_master_from_recipe",
    "read_json",
    "read_motion_recipe",
    "segment_segment_closest",
    "segment_volume_distance",
    "stable_digest",
    "stable_json",
    "stamp_json",
    "stamp_motion_recipe",
    "subtract",
    "target_zone_center",
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
