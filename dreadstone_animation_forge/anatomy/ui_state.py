"""Compact summary state for the Blender anatomy card."""

from __future__ import annotations

from typing import Mapping


def summary_from_analysis(value: Mapping[str, object] | None) -> dict[str, object]:
    value = value or {}
    orientation = value.get("orientation", {})
    if not isinstance(orientation, Mapping):
        orientation = {}
    return {
        "creatureClass": str(value.get("creatureClass", "NOT ANALYZED")),
        "profileId": str(value.get("profileId", "AUTO / UNRESOLVED")),
        "confidence": float(value.get("detectionConfidence", 0.0) or 0.0),
        "orientation": (
            f"{orientation.get('forwardAxis', '?')} forward / "
            f"{orientation.get('upAxis', '?')} up"
        ),
        "mappedRoleCount": int(value.get("mappedRoleCount", 0) or 0),
        "readinessStatus": str(value.get("readinessStatus", "NOT_ANALYZED")),
        "worstBlocker": str(value.get("worstBlocker", "")),
        "ready": bool(value.get("ready", False)),
    }


__all__ = ("summary_from_analysis",)
