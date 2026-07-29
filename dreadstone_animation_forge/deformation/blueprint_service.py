"""Portable, topology-independent Damage Blueprint contracts.

A blueprint stores authored intent only.  Destination object names, vertex and
face indices, shape-key coordinates, generated gore meshes, and Blender IDs are
deliberately excluded.  Applying a blueprint always binds it to a fresh target
capture and regenerates destination-specific data.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence


BLUEPRINT_SCHEMA = "dreadstone.damage_blueprint.v1"
BLUEPRINT_VERSION = 1
LIBRARY_SCHEMA = "dreadstone.damage_blueprint_library.v1"
LIBRARY_VERSION = 1
SCALE_POLICIES = ("CAPTURE_RELATIVE", "ABSOLUTE")
SEMANTIC_ANCHORS = (
    "",
    "HEAD",
    "HEAD_LEFT",
    "HEAD_RIGHT",
    "HEAD_FRONT",
    "HEAD_BACK",
    "BODY",
    "BODY_FRONT",
    "BODY_BACK",
    "FOREARM_LEFT",
    "FOREARM_RIGHT",
    "CUSTOM",
)

IMPACT_MACRO_FIELDS = (
    "area",
    "depth",
    "falloff",
    "edgeDamage",
    "distortion",
    "asymmetry",
)
GORE_MACRO_FIELDS = (
    "coverage",
    "raised",
    "inlay",
    "breakup",
    "fill",
    "wetness",
)
SURFACE_GORE_MACRO_FIELDS = (
    "mass",
    "relief",
    "nucleus",
    "folds",
    "redness",
)
SURFACE_GORE_MACRO_DEFAULTS = {
    "mass": 0.0,
    "relief": 58.0,
    "nucleus": 0.0,
    "folds": 55.0,
    "redness": 78.0,
}
STAMP_FAMILIES = (
    "COMPACT_DENT",
    "BROAD_CAVE",
    "FLAT_COMPRESSION",
    "DIRECTIONAL_SHEAR",
    "RAISED_IMPACT_RIM",
    "RIDGE_COLLAPSE",
)
DIRECTION_MODES = (
    "INWARD_SURFACE_NORMAL",
    "OUTWARD_SURFACE_NORMAL",
    "LOCAL_X",
    "LOCAL_NEG_X",
    "LOCAL_Y",
    "LOCAL_NEG_Y",
    "LOCAL_Z",
    "LOCAL_NEG_Z",
    "CUSTOM_VECTOR",
)
INFLUENCE_MODES = ("PATCH_ONLY", "PATCH_FEATHERED", "CONNECTED_SURFACE")
DISTANCE_MODES = ("SURFACE_DISTANCE", "WORLD_DISTANCE")
GORE_IDENTITIES = (
    "BRUISED_DENT",
    "BLOODY_CRATER",
    "DARK_CLOT_CAVITY",
    "CRUSHED_TISSUE",
    "EXPOSED_CRANIUM",
    "RAGGED_IMPACT",
)


def _finite(value, label, *, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a finite number") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    if minimum is not None and number < float(minimum):
        raise ValueError(f"{label} must be at least {float(minimum):g}")
    if maximum is not None and number > float(maximum):
        raise ValueError(f"{label} must be at most {float(maximum):g}")
    return number


def _macro_block(raw, fields, label):
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} macros must be an object")
    return {
        field: _finite(raw.get(field, 50.0), f"{label} {field}", minimum=0.0, maximum=100.0)
        for field in fields
    }


def _choice(value, choices, label):
    selected = str(value).upper()
    if selected not in choices:
        raise ValueError(f"Unsupported {label} {selected!r}")
    return selected


def _vector3(raw, label, default):
    values = default if raw is None else raw
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or len(values) != 3:
        raise ValueError(f"{label} must contain three numbers")
    result = tuple(_finite(value, label) for value in values)
    length = math.sqrt(sum(value * value for value in result))
    if length <= 1e-12:
        return tuple(float(value) for value in default)
    return tuple(value / length for value in result)


def safe_blueprint_id(name):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name).strip()).strip("_.-")
    if not cleaned:
        raise ValueError("Blueprint name must contain at least one letter or digit")
    return cleaned[:64]


def derive_subseed(master_seed, channel):
    """Derive a stable independent seed channel from one artist-facing seed."""

    seed = int(master_seed)
    if seed < 0 or seed > 2147483647:
        raise ValueError("Master seed must be from 0 to 2147483647")
    digest = hashlib.sha256(f"{seed}|{str(channel)}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little") & 0x7FFFFFFF


def _digest(payload, omitted=()):
    value = copy.deepcopy(dict(payload))
    for field in omitted:
        value.pop(field, None)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _legacy_blueprint_digest_without_surface_macros(normalized):
    """Return the v1 digest used before cohesive surface macros were persisted."""

    legacy = copy.deepcopy(dict(normalized))
    gore = legacy.get("gore")
    if isinstance(gore, dict):
        gore.pop("surfaceMacros", None)
    return _digest(legacy, omitted=("blueprintDigest",))


def _legacy_library_digest_without_surface_macros(normalized, blueprint_ids):
    """Recreate the canonical library digest for pre-surface-macro records."""

    legacy = copy.deepcopy(dict(normalized))
    migrated_ids = set(blueprint_ids)
    for record in legacy.get("blueprints", ()):
        if record.get("blueprintId") not in migrated_ids:
            continue
        gore = record.get("gore")
        if isinstance(gore, dict):
            gore.pop("surfaceMacros", None)
        record["blueprintDigest"] = _digest(
            record,
            omitted=("blueprintDigest",),
        )
    return _digest(legacy, omitted=("libraryDigest",))


def normalize_blueprint(payload):
    if not isinstance(payload, Mapping):
        raise ValueError("Damage Blueprint must be an object")
    if str(payload.get("schema", BLUEPRINT_SCHEMA)) != BLUEPRINT_SCHEMA:
        raise ValueError(f"Unsupported Damage Blueprint schema {payload.get('schema')!r}")
    if int(payload.get("version", BLUEPRINT_VERSION)) != BLUEPRINT_VERSION:
        raise ValueError(f"Unsupported Damage Blueprint version {payload.get('version')!r}")
    name = str(payload.get("name", "")).strip()
    blueprint_id = safe_blueprint_id(payload.get("blueprintId", name))
    if not name:
        name = blueprint_id.replace("_", " ")
    impact = payload.get("impact", {})
    gore = payload.get("gore", {})
    stamp = payload.get("stamp", {})
    placement = payload.get("placement", {})
    if not all(isinstance(value, Mapping) for value in (impact, gore, stamp, placement)):
        raise ValueError("Blueprint impact, gore, stamp, and placement records must be objects")
    scale_policy = str(stamp.get("scalePolicy", "CAPTURE_RELATIVE")).upper()
    if scale_policy not in SCALE_POLICIES:
        raise ValueError(f"Unsupported blueprint scale policy {scale_policy!r}")
    semantic_anchor = str(placement.get("semanticAnchor", "")).upper()
    if semantic_anchor not in SEMANTIC_ANCHORS:
        semantic_anchor = "CUSTOM"
    normalized = {
        "schema": BLUEPRINT_SCHEMA,
        "version": BLUEPRINT_VERSION,
        "blueprintId": blueprint_id,
        "name": name[:96],
        "impact": {
            "macros": _macro_block(impact.get("macros", {}), IMPACT_MACRO_FIELDS, "Impact"),
            "seed": int(impact.get("seed", 1776)),
        },
        "gore": {
            "enabled": bool(gore.get("enabled", True)),
            "identityId": _choice(
                gore.get("identityId", "BLOODY_CRATER"),
                GORE_IDENTITIES,
                "gore identity",
            ),
            "macros": _macro_block(gore.get("macros", {}), GORE_MACRO_FIELDS, "Gore"),
            "surfaceMacros": {
                field: _finite(
                    (
                        gore.get("surfaceMacros", {})
                        if isinstance(
                            gore.get("surfaceMacros", {}),
                            Mapping,
                        )
                        else {}
                    ).get(
                        field,
                        SURFACE_GORE_MACRO_DEFAULTS[field],
                    ),
                    f"Surface Gore {field}",
                    minimum=0.0,
                    maximum=100.0,
                )
                for field in SURFACE_GORE_MACRO_FIELDS
            },
            "seed": int(gore.get("seed", 1776)),
            "textureEnabled": bool(gore.get("textureEnabled", True)),
            "fiberTextureStrength": _finite(
                gore.get("fiberTextureStrength", 0.75),
                "Fiber texture strength",
                minimum=0.0,
                maximum=1.0,
            ),
            "baseColorStrength": _finite(
                gore.get("baseColorStrength", 0.75),
                "Base color strength",
                minimum=0.0,
                maximum=1.0,
            ),
        },
        "stamp": {
            "scalePolicy": scale_policy,
            "family": _choice(
                stamp.get("family", "COMPACT_DENT"),
                STAMP_FAMILIES,
                "stamp family",
            ),
            "referenceScale": _finite(
                stamp.get("referenceScale", 0.075),
                "Blueprint reference scale",
                minimum=1e-6,
                maximum=10.0,
            ),
            "radiusRatio": _finite(
                stamp.get("radiusRatio", 1.0),
                "Blueprint radius ratio",
                minimum=0.01,
                maximum=20.0,
            ),
            "depthRatio": _finite(
                stamp.get("depthRatio", 0.25),
                "Blueprint depth ratio",
                minimum=0.0,
                maximum=10.0,
            ),
            "featherRatio": _finite(
                stamp.get("featherRatio", 0.25),
                "Blueprint feather ratio",
                minimum=0.0,
                maximum=10.0,
            ),
            "strength": _finite(
                stamp.get("strength", 1.0),
                "Blueprint strength",
                minimum=0.0,
                maximum=4.0,
            ),
            "falloff": _finite(
                stamp.get("falloff", 2.0),
                "Blueprint falloff",
                minimum=0.0,
                maximum=20.0,
            ),
            "seamProtectionRatio": _finite(
                stamp.get("seamProtectionRatio", 0.25),
                "Blueprint seam-protection ratio",
                minimum=0.0,
                maximum=20.0,
            ),
            "maximumDisplacementRatio": _finite(
                stamp.get("maximumDisplacementRatio", 0.75),
                "Blueprint maximum-displacement ratio",
                minimum=0.0,
                maximum=20.0,
            ),
            "maximumInfluence": _finite(
                stamp.get("maximumInfluence", 1.0),
                "Blueprint maximum influence",
                minimum=0.0,
                maximum=4.0,
            ),
            "directionMode": _choice(
                stamp.get("directionMode", "INWARD_SURFACE_NORMAL"),
                DIRECTION_MODES,
                "direction mode",
            ),
            "directionLocal": list(_vector3(
                stamp.get("directionLocal"),
                "Blueprint direction",
                (0.0, 0.0, -1.0),
            )),
            "influenceMode": _choice(
                stamp.get("influenceMode", "PATCH_FEATHERED"),
                INFLUENCE_MODES,
                "influence mode",
            ),
            "distanceMode": _choice(
                stamp.get("distanceMode", "SURFACE_DISTANCE"),
                DISTANCE_MODES,
                "distance mode",
            ),
        },
        "placement": {
            "semanticAnchor": semantic_anchor,
            "orientationTurns": _finite(
                placement.get("orientationTurns", 0.0),
                "Blueprint orientation",
                minimum=-1.0,
                maximum=1.0,
            ),
        },
    }
    for label, seed in (
        ("Impact seed", normalized["impact"]["seed"]),
        ("Gore seed", normalized["gore"]["seed"]),
    ):
        if seed < 0 or seed > 2147483647:
            raise ValueError(f"{label} must be from 0 to 2147483647")
    calculated = _digest(normalized, omitted=("blueprintDigest",))
    stored = str(payload.get("blueprintDigest", ""))
    is_legacy_surface_record = "surfaceMacros" not in gore
    legacy_calculated = (
        _legacy_blueprint_digest_without_surface_macros(normalized)
        if is_legacy_surface_record
        else ""
    )
    if stored and stored not in (calculated, legacy_calculated):
        raise ValueError("Damage Blueprint digest does not match its contents")
    normalized["blueprintDigest"] = calculated
    return normalized


def build_blueprint(
    name,
    *,
    impact_macros,
    impact_seed,
    gore_macros,
    surface_gore_macros=None,
    gore_seed,
    stamp,
    gore_enabled=True,
    gore_identity_id="BLOODY_CRATER",
    texture_enabled=True,
    fiber_texture_strength=0.75,
    base_color_strength=0.75,
    semantic_anchor="",
):
    """Build one source-independent blueprint from an authored active stamp."""

    if not isinstance(stamp, Mapping):
        raise ValueError("Active stamp recipe must be an object")
    capture = stamp.get("capture", {})
    capture_scale = (
        float(capture.get("estimatedRadius", 0.0))
        if isinstance(capture, Mapping)
        else 0.0
    )
    radius = _finite(stamp.get("radius", 0.075), "Stamp radius", minimum=1e-6)
    reference_scale = capture_scale if math.isfinite(capture_scale) and capture_scale > 1e-6 else radius
    depth = _finite(stamp.get("depth", 0.0), "Stamp depth", minimum=0.0)
    feather = _finite(stamp.get("featherDistance", 0.0), "Stamp feather", minimum=0.0)
    return normalize_blueprint({
        "schema": BLUEPRINT_SCHEMA,
        "version": BLUEPRINT_VERSION,
        "blueprintId": safe_blueprint_id(name),
        "name": str(name),
        "impact": {"macros": dict(impact_macros), "seed": int(impact_seed)},
        "gore": {
            "enabled": bool(gore_enabled),
            "identityId": str(gore_identity_id),
            "macros": dict(gore_macros),
            "surfaceMacros": dict(
                SURFACE_GORE_MACRO_DEFAULTS
                if surface_gore_macros is None
                else surface_gore_macros
            ),
            "seed": int(gore_seed),
            "textureEnabled": bool(texture_enabled),
            "fiberTextureStrength": float(fiber_texture_strength),
            "baseColorStrength": float(base_color_strength),
        },
        "stamp": {
            "scalePolicy": "CAPTURE_RELATIVE",
            "family": str(stamp.get("family", "COMPACT_DENT")),
            "referenceScale": reference_scale,
            "radiusRatio": radius / reference_scale,
            "depthRatio": depth / reference_scale,
            "featherRatio": feather / reference_scale,
            "strength": float(stamp.get("strength", 1.0)),
            "falloff": float(stamp.get("falloff", 2.0)),
            "seamProtectionRatio": (
                float(stamp.get("seamProtection", 0.0)) / reference_scale
            ),
            "maximumDisplacementRatio": (
                float(stamp.get("maximumDisplacement", 0.0)) / reference_scale
            ),
            "maximumInfluence": float(stamp.get("maximumInfluence", 1.0)),
            "directionMode": str(stamp.get("directionMode", "INWARD_SURFACE_NORMAL")),
            "directionLocal": stamp.get("directionLocal", (0.0, 0.0, -1.0)),
            "influenceMode": str(stamp.get("influenceMode", "PATCH_FEATHERED")),
            "distanceMode": str(stamp.get("distanceMode", "SURFACE_DISTANCE")),
        },
        "placement": {
            "semanticAnchor": str(semantic_anchor),
            "orientationTurns": 0.0,
        },
    })


def adaptive_stamp_values(blueprint, destination_capture_scale):
    """Return destination-scaled physical hints without any topology dependency."""

    normalized = normalize_blueprint(blueprint)
    stamp = normalized["stamp"]
    destination = _finite(
        destination_capture_scale,
        "Destination capture scale",
        minimum=1e-6,
        maximum=10.0,
    )
    scale = destination if stamp["scalePolicy"] == "CAPTURE_RELATIVE" else stamp["referenceScale"]
    return {
        "family": str(stamp["family"]),
        "radius": scale * float(stamp["radiusRatio"]),
        "depth": scale * float(stamp["depthRatio"]),
        "featherDistance": scale * float(stamp["featherRatio"]),
        "strength": float(stamp["strength"]),
        "falloff": float(stamp["falloff"]),
        "seamProtection": scale * float(stamp["seamProtectionRatio"]),
        "maximumDisplacement": scale
        * float(stamp["maximumDisplacementRatio"]),
        "maximumInfluence": float(stamp["maximumInfluence"]),
        "directionMode": str(stamp["directionMode"]),
        "directionLocal": list(stamp["directionLocal"]),
        "influenceMode": str(stamp["influenceMode"]),
        "distanceMode": str(stamp["distanceMode"]),
    }


def normalize_library(payload=None):
    raw = {} if payload is None else payload
    if not isinstance(raw, Mapping):
        raise ValueError("Damage Blueprint library must be an object")
    if raw and str(raw.get("schema", LIBRARY_SCHEMA)) != LIBRARY_SCHEMA:
        raise ValueError(f"Unsupported Damage Blueprint library schema {raw.get('schema')!r}")
    if raw and int(raw.get("version", LIBRARY_VERSION)) != LIBRARY_VERSION:
        raise ValueError(f"Unsupported Damage Blueprint library version {raw.get('version')!r}")
    records = raw.get("blueprints", [])
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("Damage Blueprint library entries must be an array")
    blueprints = [normalize_blueprint(record) for record in records]
    legacy_surface_ids = {
        blueprint["blueprintId"]
        for record, blueprint in zip(records, blueprints)
        if isinstance(record, Mapping)
        and isinstance(record.get("gore"), Mapping)
        and "surfaceMacros" not in record["gore"]
    }
    ids = [record["blueprintId"] for record in blueprints]
    if len(ids) != len(set(ids)):
        raise ValueError("Damage Blueprint library contains duplicate IDs")
    blueprints.sort(key=lambda record: (str(record["name"]).casefold(), str(record["blueprintId"])))
    normalized = {
        "schema": LIBRARY_SCHEMA,
        "version": LIBRARY_VERSION,
        "blueprintCount": len(blueprints),
        "blueprints": blueprints,
    }
    calculated = _digest(normalized, omitted=("libraryDigest",))
    stored = str(raw.get("libraryDigest", ""))
    legacy_calculated = (
        _legacy_library_digest_without_surface_macros(
            normalized,
            legacy_surface_ids,
        )
        if legacy_surface_ids
        else ""
    )
    if stored and stored not in (calculated, legacy_calculated):
        raise ValueError("Damage Blueprint library digest does not match its contents")
    normalized["libraryDigest"] = calculated
    return normalized


def upsert_blueprint(library, blueprint):
    normalized_library = normalize_library(library)
    normalized_blueprint = normalize_blueprint(blueprint)
    records = [
        record
        for record in normalized_library["blueprints"]
        if record["blueprintId"] != normalized_blueprint["blueprintId"]
    ]
    records.append(normalized_blueprint)
    return normalize_library({"blueprints": records})


def blueprint_by_id(library, blueprint_id):
    normalized = normalize_library(library)
    requested = str(blueprint_id)
    for record in normalized["blueprints"]:
        if record["blueprintId"] == requested:
            return record
    raise KeyError(f"Damage Blueprint {requested!r} was not found")
