"""Raised-gore source evaluation cache separated from generated Blender data."""

from __future__ import annotations

import copy

from .registry import BoundedCache


_RECORDS = BoundedCache(16, "gore_face_records")
_LAST_CLEAR_REASON = "startup"


def face_records(cache_key, evaluator):
    cached = _RECORDS.peek(str(cache_key))
    if cached is not None:
        return copy.deepcopy(cached), True
    records = list(evaluator())
    _RECORDS[str(cache_key)] = copy.deepcopy(records)
    return records, False


def balanced_overlay(overlay):
    """Keep raised gore but reduce only temporary preview density/budget."""

    value = copy.deepcopy(dict(overlay))
    value["goreGeometryDensity"] = min(float(value.get("goreGeometryDensity", 1.0)), 0.35)
    value["goreMaximumTriangles"] = min(int(value.get("goreMaximumTriangles", 12000)), 2500)
    return value


def clear_cache(reason="explicit"):
    global _LAST_CLEAR_REASON
    _RECORDS.clear()
    _LAST_CLEAR_REASON = str(reason)


def cache_count():
    return len(_RECORDS)
