"""Recipe dirty-state and preview dependency helpers."""

from __future__ import annotations

import hashlib
import json


def recipe_state_digest(region_id, key_name, stamp, capture_digest="", transform_state=()):
    payload = {
        "regionId": str(region_id),
        "keyName": str(key_name),
        "stamp": stamp,
        "captureDigest": str(capture_digest),
        "transformState": tuple(transform_state),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def affected_vertex_count(weights, threshold=1e-8):
    return sum(float(value) > float(threshold) for value in weights)
