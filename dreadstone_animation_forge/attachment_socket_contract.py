"""Versioned, Blender-independent runtime attachment socket contract."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping


ATTACHMENT_SOCKET_SCHEMA = "dreadstone.attachment_sockets.v1"
ATTACHMENT_SOCKET_COLLECTION = "DSB_RUNTIME_ATTACHMENT_SOCKETS"
ATTACHMENT_SOCKET_HELPER_PREFIX = "DSB_ATTACHMENT_SOCKET_"
RUNTIME_ARMATURE_NAME = "DSB_DAMAGE_RIG"
SOCKET_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?$")

STANDARD_SOCKET_SPECS = (
    {
        "socketId": "hand_right_weapon",
        "semanticRole": "MAIN_HAND_R",
        "parentRuntimeBone": "arm_right_hand",
        "helperName": ATTACHMENT_SOCKET_HELPER_PREFIX + "HAND_RIGHT_WEAPON",
    },
    {
        "socketId": "hand_left_weapon",
        "semanticRole": "MAIN_HAND_L",
        "parentRuntimeBone": "arm_left_hand",
        "helperName": ATTACHMENT_SOCKET_HELPER_PREFIX + "HAND_LEFT_WEAPON",
    },
)


def _finite_vector(value, size):
    return (
        isinstance(value, (list, tuple))
        and len(value) == size
        and all(isinstance(item, (int, float)) and math.isfinite(float(item)) for item in value)
    )


def validate_socket_contract(payload: Mapping[str, Any], runtime_bones) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return ["Attachment socket contract must be an object."]
    if payload.get("schema") != ATTACHMENT_SOCKET_SCHEMA:
        errors.append(f"schema must be {ATTACHMENT_SOCKET_SCHEMA}.")
    if payload.get("runtimeArmature") != RUNTIME_ARMATURE_NAME:
        errors.append(f"runtimeArmature must be {RUNTIME_ARMATURE_NAME}.")
    sockets = payload.get("sockets")
    if not isinstance(sockets, list):
        return errors + ["sockets must be an array."]
    ids: list[str] = []
    roles: list[str] = []
    runtime_bones = set(runtime_bones or ())
    for index, socket in enumerate(sockets):
        path = f"sockets[{index}]"
        if not isinstance(socket, Mapping):
            errors.append(f"{path} must be an object.")
            continue
        socket_id = socket.get("socketId")
        role = socket.get("semanticRole")
        parent = socket.get("parentRuntimeBone")
        if not isinstance(socket_id, str) or not SOCKET_ID_PATTERN.fullmatch(socket_id):
            errors.append(f"{path}.socketId must be a stable lowercase identifier.")
        else:
            ids.append(socket_id)
        if role not in {"MAIN_HAND_R", "MAIN_HAND_L"}:
            errors.append(f"{path}.semanticRole is unsupported.")
        else:
            roles.append(str(role))
        if not isinstance(parent, str) or not parent:
            errors.append(f"{path}.parentRuntimeBone is required.")
        elif parent not in runtime_bones:
            errors.append(f"{path}.parentRuntimeBone {parent!r} is not in {RUNTIME_ARMATURE_NAME}.")
        if not _finite_vector(socket.get("localPosition"), 3):
            errors.append(f"{path}.localPosition must be a finite 3-vector.")
        quaternion = socket.get("localQuaternion")
        if not _finite_vector(quaternion, 4):
            errors.append(f"{path}.localQuaternion must be a finite [x,y,z,w] quaternion.")
        else:
            length = math.sqrt(sum(float(value) ** 2 for value in quaternion))
            if length <= 1.0e-8:
                errors.append(f"{path}.localQuaternion cannot be zero.")
            elif abs(length - 1.0) > 1.0e-4:
                errors.append(f"{path}.localQuaternion must be normalized.")
        if not isinstance(socket.get("enabled"), bool) or not isinstance(socket.get("exportable"), bool):
            errors.append(f"{path}.enabled and exportable must be boolean.")
    duplicate_ids = sorted({value for value in ids if ids.count(value) > 1})
    if duplicate_ids:
        errors.append("Socket IDs are duplicated: " + ", ".join(duplicate_ids) + ".")
    duplicate_roles = sorted({value for value in roles if roles.count(value) > 1})
    if duplicate_roles:
        errors.append("Socket semantic roles are duplicated: " + ", ".join(duplicate_roles) + ".")
    return errors


__all__ = (
    "ATTACHMENT_SOCKET_COLLECTION",
    "ATTACHMENT_SOCKET_HELPER_PREFIX",
    "ATTACHMENT_SOCKET_SCHEMA",
    "RUNTIME_ARMATURE_NAME",
    "STANDARD_SOCKET_SPECS",
    "validate_socket_contract",
)
