"""Blender-facing deformation services used by the compatibility facade."""

from . import (
    compound_service,
    diagnostics,
    gore_service,
    mesh_snapshot,
    preview_service,
    registry,
    serialization,
    validation_service,
)


def clear_all_caches(reason="explicit"):
    """Clear every name/data-only cache without retaining Blender RNA."""

    mesh_snapshot.clear_cache(reason)
    gore_service.clear_cache(reason)
    compound_service.clear_cache(reason)
    serialization.clear_cache()
    validation_service.clear_cache(reason)
    registry.clear_registered_caches()


def cache_counts():
    return {
        "meshSnapshots": mesh_snapshot.cache_count(),
        "goreRecords": gore_service.cache_count(),
        "compoundParticipants": compound_service.cache_count(),
        "serializedPayloads": serialization.cache_count(),
        "validationSummaries": validation_service.cache_count(),
        **registry.registered_cache_counts(),
    }
