"""Single authoritative forward/up/left and root-motion contract."""

from __future__ import annotations

from math import sqrt
from typing import Mapping

from .model import RigSnapshot
from .schema import AnatomyProfile, axis_vector, axes_orthogonal


FACING_TO_AXIS = {
    "NEG_Y": "-Y",
    "POS_Y": "+Y",
    "POS_X": "+X",
    "NEG_X": "-X",
    "+Y": "+Y",
    "-Y": "-Y",
    "+X": "+X",
    "-X": "-X",
}


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _subtract(a, b):
    return tuple(float(x) - float(y) for x, y in zip(a, b))


def _normalize(value):
    length = sqrt(sum(float(part) ** 2 for part in value))
    if length <= 1.0e-8:
        return (0.0, 0.0, 0.0)
    return tuple(float(part) / length for part in value)


def _dot(a, b):
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _first_bone(mapping: Mapping[str, object], *roles: str) -> str:
    for role in roles:
        value = mapping.get(role)
        if isinstance(value, (list, tuple)) and value:
            return str(value[0])
        if value:
            return str(value)
    return ""


def orientation_contract(
    profile: AnatomyProfile,
    mapping: Mapping[str, object],
    snapshot: RigSnapshot,
    *,
    explicit_forward: str | None = None,
) -> dict[str, object]:
    forward_axis = FACING_TO_AXIS.get(str(explicit_forward), profile.forward_axis)
    up_axis = profile.up_axis
    forward = axis_vector(forward_axis)
    up = axis_vector(up_axis)
    left = _normalize(_cross(up, forward))
    left_axis = ""
    for candidate in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
        if _dot(left, axis_vector(candidate)) > 0.999:
            left_axis = candidate
            break

    by_name = snapshot.by_name()
    body_name = _first_bone(mapping, "body_center", "hips", "pelvis", "spine")
    head_name = _first_bone(mapping, "head")
    head_direction = (0.0, 0.0, 0.0)
    forward_alignment = None
    if body_name in by_name and head_name in by_name:
        raw = _subtract(by_name[head_name].center, by_name[body_name].center)
        horizontal = tuple(
            0.0 if abs(component) > 0.5 else value
            for component, value in zip(up, raw)
        )
        head_direction = _normalize(horizontal)
        if head_direction != (0.0, 0.0, 0.0):
            forward_alignment = _dot(head_direction, forward)

    ground_root = _first_bone(mapping, "ground_root", "root", "hips", "pelvis")
    body_center = _first_bone(mapping, "body_center", "hips", "pelvis")
    root_motion = ground_root or body_center
    contacts = [
        str(mapping[role])
        for role in profile.contact_roles
        if isinstance(mapping.get(role), str) and mapping.get(role)
    ]
    warnings: list[str] = []
    if not axes_orthogonal(forward_axis, up_axis) or not left_axis:
        warnings.append("ORIENTATION_AMBIGUOUS")
    if profile.creature_class == "QUADRUPED":
        if forward_alignment is None or abs(float(forward_alignment)) < 0.35:
            warnings.append("ORIENTATION_AMBIGUOUS")
        elif float(forward_alignment) < 0.0:
            warnings.append("HEAD_TAIL_DIRECTION_REVERSED")

    return {
        "forwardAxis": forward_axis,
        "upAxis": up_axis,
        "leftAxis": left_axis,
        "headFacingDirection": [round(float(value), 7) for value in head_direction],
        "headForwardAlignment": (
            None if forward_alignment is None else round(float(forward_alignment), 7)
        ),
        "groundRootRole": "ground_root" if mapping.get("ground_root") else "root" if mapping.get("root") else "hips" if mapping.get("hips") else "pelvis",
        "groundRootBone": ground_root,
        "bodyCenterRole": "body_center" if mapping.get("body_center") else "hips" if mapping.get("hips") else "pelvis",
        "bodyCenterBone": body_center,
        "rootMotionCarrier": root_motion,
        "contactRoles": list(profile.contact_roles),
        "contactBones": contacts,
        "warnings": list(dict.fromkeys(warnings)),
    }


__all__ = ("FACING_TO_AXIS", "orientation_contract")
