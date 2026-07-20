"""Canonical metadata adapters with bounded parse reuse and no RNA storage."""

from __future__ import annotations

import copy
import json

from .registry import BoundedCache


_PARSED = BoundedCache(32, "serialized_payloads")


def decode(raw, default=None, *, mutable=True):
    if not raw:
        value = {} if default is None else default
        return copy.deepcopy(value) if mutable else value
    text = str(raw)
    cached = _PARSED.peek(text)
    if cached is None:
        cached = json.loads(text)
        _PARSED[text] = cached
    return copy.deepcopy(cached) if mutable else cached


def encode(value, *, pretty=False):
    if pretty:
        return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_if_changed(owner, key, value):
    """Write canonical JSON only when its bytes differ from stored metadata."""

    encoded = encode(value)
    if str(owner.get(key, "")) == encoded:
        return False
    owner[key] = encoded
    return True


def clear_cache():
    _PARSED.clear()


def cache_count():
    return len(_PARSED)
