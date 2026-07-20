"""Bounded caches and explicit invalidation for Blender-facing services."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import MutableMapping


class BoundedCache(MutableMapping):
    """Small LRU mapping compatible with the legacy dictionary call sites."""

    def __init__(self, capacity=32, name="cache"):
        if int(capacity) <= 0:
            raise ValueError("cache capacity must be positive")
        self.capacity = int(capacity)
        self.name = str(name)
        self._values = OrderedDict()

    def __getitem__(self, key):
        value = self._values.pop(key)
        self._values[key] = value
        return value

    def __setitem__(self, key, value):
        self._values.pop(key, None)
        self._values[key] = value
        while len(self._values) > self.capacity:
            self._values.popitem(last=False)

    def __delitem__(self, key):
        del self._values[key]

    def __iter__(self):
        return iter(tuple(self._values))

    def __len__(self):
        return len(self._values)

    def clear(self):
        self._values.clear()

    def peek(self, key, default=None):
        return self._values.get(key, default)


_REGISTERED_CACHES = {}


def register_cache(name, cache):
    _REGISTERED_CACHES[str(name)] = cache
    return cache


def unregister_cache(name):
    _REGISTERED_CACHES.pop(str(name), None)


def clear_registered_caches():
    for cache in tuple(_REGISTERED_CACHES.values()):
        try:
            cache.clear()
        except Exception:
            pass


def registered_cache_counts():
    result = {}
    for name, cache in _REGISTERED_CACHES.items():
        try:
            result[str(name)] = len(cache)
        except Exception:
            result[str(name)] = -1
    return result
