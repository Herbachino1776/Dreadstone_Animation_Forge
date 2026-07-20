"""Direct, context-free shape-key reads and writes."""

from __future__ import annotations


def coordinates(key_block):
    flat = [0.0] * (len(key_block.data) * 3)
    key_block.data.foreach_get("co", flat)
    return tuple(tuple(flat[index:index + 3]) for index in range(0, len(flat), 3))


def set_coordinates(key_block, values):
    values = tuple(values)
    if len(values) != len(key_block.data):
        raise RuntimeError("Shape-key coordinate count does not match the target mesh.")
    flat = [float(component) for point in values for component in point]
    key_block.data.foreach_set("co", flat)


def copy_exact(source_key, target_key):
    if len(source_key.data) != len(target_key.data):
        raise RuntimeError("Exact-index shape-key synchronization requires matching point counts.")
    flat = [0.0] * (len(source_key.data) * 3)
    source_key.data.foreach_get("co", flat)
    target_key.data.foreach_set("co", flat)
