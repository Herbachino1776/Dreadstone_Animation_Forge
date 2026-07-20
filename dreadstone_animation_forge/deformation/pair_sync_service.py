"""Exact-index direct shape-key synchronization helpers."""

from __future__ import annotations

from . import shape_keys


def synchronize(source_key, target_key):
    """Copy coordinates exactly; nearest-neighbor transfer is never permitted."""

    shape_keys.copy_exact(source_key, target_key)
    target_key.value = float(source_key.value)
    target_key.slider_min = float(source_key.slider_min)
    target_key.slider_max = float(source_key.slider_max)


def maximum_coordinate_error(first_key, second_key):
    if len(first_key.data) != len(second_key.data):
        return float("inf")
    return max(
        ((first_key.data[index].co - second_key.data[index].co).length for index in range(len(first_key.data))),
        default=0.0,
    )
