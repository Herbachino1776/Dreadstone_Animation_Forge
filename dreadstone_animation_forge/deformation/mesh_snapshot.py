"""Bulk mesh/topology snapshots shared by hot authoring paths."""

from __future__ import annotations

import hashlib
import json

from mathutils import Vector

from .registry import BoundedCache


_CACHE = BoundedCache(24, "mesh_snapshots")
_LAST_CLEAR_REASON = "startup"


def _matrix_key(obj):
    return tuple(round(float(value), 12) for row in obj.matrix_world for value in row)


def _identity(obj, kind):
    return (
        str(kind), str(obj.name), str(obj.data.name),
        len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons),
        _matrix_key(obj),
    )


def _local_vertex_tuples(vertices):
    flat = [0.0] * (len(vertices) * 3)
    vertices.foreach_get("co", flat)
    return tuple(tuple(flat[index:index + 3]) for index in range(0, len(flat), 3))


def local_positions(obj, *, force=False):
    key = _identity(obj, "local")
    if not force:
        cached = _CACHE.peek(key)
        if cached is not None:
            return cached
    value = _local_vertex_tuples(obj.data.vertices)
    _CACHE[key] = value
    return value


def world_positions(obj, *, force=False):
    key = _identity(obj, "world")
    if not force:
        cached = _CACHE.peek(key)
        if cached is not None:
            return cached
    matrix = obj.matrix_world
    value = tuple(tuple(matrix @ Vector(point)) for point in local_positions(obj, force=force))
    _CACHE[key] = value
    return value


def basis_world_positions(obj, *, force=False):
    shape_keys = getattr(obj.data, "shape_keys", None)
    basis = getattr(shape_keys, "reference_key", None)
    if basis is None:
        return world_positions(obj, force=force)
    key = _identity(obj, "basis_world") + (str(basis.name), len(basis.data))
    if not force:
        cached = _CACHE.peek(key)
        if cached is not None:
            return cached
    flat = [0.0] * (len(basis.data) * 3)
    basis.data.foreach_get("co", flat)
    matrix = obj.matrix_world
    value = tuple(
        tuple(matrix @ Vector(flat[index:index + 3]))
        for index in range(0, len(flat), 3)
    )
    _CACHE[key] = value
    return value


def edges(obj, *, force=False):
    key = _identity(obj, "edges")
    if not force:
        cached = _CACHE.peek(key)
        if cached is not None:
            return cached
    flat = [0] * (len(obj.data.edges) * 2)
    obj.data.edges.foreach_get("vertices", flat)
    value = tuple(tuple(flat[index:index + 2]) for index in range(0, len(flat), 2))
    _CACHE[key] = value
    return value


def faces(obj, *, force=False):
    key = _identity(obj, "faces")
    if not force:
        cached = _CACHE.peek(key)
        if cached is not None:
            return cached
    value = tuple(tuple(int(index) for index in polygon.vertices) for polygon in obj.data.polygons)
    _CACHE[key] = value
    return value


def topology_fingerprint(obj, *, force=False):
    key = _identity(obj, "topology_fingerprint")
    if not force:
        cached = _CACHE.peek(key)
        if cached is not None:
            return cached
    digest = hashlib.sha256()
    digest.update(f"v:{len(obj.data.vertices)}|p:{len(obj.data.polygons)}|".encode("utf8"))
    for face in faces(obj, force=force):
        digest.update((",".join(str(index) for index in face) + ";").encode("ascii"))
    value = digest.hexdigest()
    _CACHE[key] = value
    return value


def weight_fingerprint(obj, *, force=False):
    key = _identity(obj, "weight_fingerprint") + (len(obj.vertex_groups),)
    if not force:
        cached = _CACHE.peek(key)
        if cached is not None:
            return cached
    digest = hashlib.sha256()
    groups = {int(group.index): str(group.name) for group in obj.vertex_groups}
    digest.update(json.dumps(groups, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    for vertex in obj.data.vertices:
        values = sorted(
            (groups.get(int(item.group), str(int(item.group))), round(float(item.weight), 9))
            for item in vertex.groups if float(item.weight) > 0.0
        )
        digest.update(json.dumps(values, separators=(",", ":")).encode("utf-8"))
    value = digest.hexdigest()
    _CACHE[key] = value
    return value


def virtual_weld_context(obj, builder, *, force=False):
    key = _identity(obj, "virtual_weld")
    if not force:
        cached = _CACHE.peek(key)
        if cached is not None:
            return cached
    positions = world_positions(obj, force=force)
    value = (positions, builder(positions))
    _CACHE[key] = value
    return value


def invalidate_object(obj_or_name):
    name = str(getattr(obj_or_name, "name", obj_or_name))
    for key in tuple(_CACHE):
        if len(key) > 1 and key[1] == name:
            del _CACHE[key]


def clear_cache(reason="explicit"):
    global _LAST_CLEAR_REASON
    _CACHE.clear()
    _LAST_CLEAR_REASON = str(reason)


def cache_count():
    return len(_CACHE)


def last_clear_reason():
    return _LAST_CLEAR_REASON
