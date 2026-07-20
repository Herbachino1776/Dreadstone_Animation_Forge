"""Cached lightweight UI summaries separated from explicit full validation."""

from __future__ import annotations

from .registry import BoundedCache


_SUMMARIES = BoundedCache(32, "validation_summaries")


def get(key, default=None):
    return _SUMMARIES.peek(key, default)


def store(key, value):
    _SUMMARIES[key] = dict(value)
    return value


def invalidate(key=None):
    if key is None:
        _SUMMARIES.clear()
    elif key in _SUMMARIES:
        del _SUMMARIES[key]


def clear_cache(_reason="explicit"):
    _SUMMARIES.clear()


def cache_count():
    return len(_SUMMARIES)
