"""Capture-state summaries and stable dependency digests."""

from __future__ import annotations

import hashlib
import json


def capture_digest(capture):
    payload = {
        "regionId": str(capture.get("regionId", "")),
        "object": str(capture.get("attachedObject", "")),
        "topology": str(capture.get("topologyFingerprint", "")),
        "selection": str(capture.get("selectionHash", "")),
        "placement": str(capture.get("placementMode", "")),
        "virtualWeld": str(capture.get("virtualWeldDigest", "")),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def summary(capture):
    return {
        "ready": bool(capture and capture.get("vertexIndices")),
        "faces": len(capture.get("faceIndices", ())) if capture else 0,
        "vertices": len(capture.get("vertexIndices", ())) if capture else 0,
        "placementMode": str(capture.get("placementMode", "")) if capture else "",
        "digest": capture_digest(capture) if capture else "",
    }
