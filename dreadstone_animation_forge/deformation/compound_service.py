"""Per-participant dirty tracking for compound trauma events."""

from __future__ import annotations

import hashlib
import json

from .registry import BoundedCache


_PARTICIPANTS = BoundedCache(64, "compound_participants")
_SEAM_MAPPINGS = BoundedCache(32, "compound_seam_mappings")


def participant_digest(*, region_fingerprint, target_topology, child_key_state, shared_field_digest, seam_mapping_digest, gore_recipe_digest):
    payload = {
        "regionFingerprint": str(region_fingerprint),
        "targetTopology": str(target_topology),
        "childKeyState": child_key_state,
        "sharedFieldDigest": str(shared_field_digest),
        "seamMappingDigest": str(seam_mapping_digest),
        "goreRecipeDigest": str(gore_recipe_digest),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def is_dirty(event_id, region_id, digest):
    record = _PARTICIPANTS.peek((str(event_id), str(region_id)))
    return not isinstance(record, dict) or str(record.get("digest", "")) != str(digest)


def mark_clean(event_id, region_id, digest, generation):
    _PARTICIPANTS[(str(event_id), str(region_id))] = {
        "digest": str(digest), "generation": int(generation),
    }


def cached_record(event_id, region_id):
    return _PARTICIPANTS.peek((str(event_id), str(region_id)))


def seam_mapping(cache_key):
    value = _SEAM_MAPPINGS.peek(cache_key)
    return tuple(value) if value is not None else None


def store_seam_mapping(cache_key, mappings):
    normalized = tuple((int(first), int(second)) for first, second in mappings)
    _SEAM_MAPPINGS[cache_key] = normalized
    return normalized


def clear_cache(_reason="explicit"):
    _PARTICIPANTS.clear()
    _SEAM_MAPPINGS.clear()


def cache_count():
    return len(_PARTICIPANTS) + len(_SEAM_MAPPINGS)


def cache_counts():
    return {"participants": len(_PARTICIPANTS), "seamMappings": len(_SEAM_MAPPINGS)}
