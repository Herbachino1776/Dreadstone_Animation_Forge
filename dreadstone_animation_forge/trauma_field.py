"""Pure trauma-field and source-contract algorithms for Dreadstone Animation Forge.

This module deliberately has no Blender imports. Mesh extraction, world/local
coordinate conversion, shape-key writes, operators, properties, and UI remain in
``deformation_authoring.py``; the reusable graph and recipe logic lives here so
it can be tested in ordinary Python.
"""

from __future__ import annotations

import copy
import hashlib
import heapq
import json
import math
import uuid
from itertools import product
from collections.abc import Iterable, Mapping, Sequence


TRAUMA_FAMILIES = (
    "COMPACT_DENT",
    "BROAD_CAVE",
    "FLAT_COMPRESSION",
    "DIRECTIONAL_SHEAR",
    "RAISED_IMPACT_RIM",
    "RIDGE_COLLAPSE",
)

PLACEMENT_MODES = (
    "SINGLE_FACE",
    "SELECTED_FACE_PATCH",
    "SELECTED_VERTICES",
    "CURSOR",
)

INFLUENCE_MODES = (
    "PATCH_ONLY",
    "PATCH_FEATHERED",
    "CONNECTED_SURFACE",
)

DISTANCE_MODES = (
    "SURFACE_DISTANCE",
    "WORLD_DISTANCE",
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

STAMP_LIBRARY_SCHEMA = "dreadstone.trauma_stamp_library.v1"
STAMP_LIBRARY_FORMAT_VERSION = 4
SUPPORTED_STAMP_LIBRARY_FORMAT_VERSIONS = (1, 2, 3, 4)

REGION_MODES = (
    "PAIRED_SEGMENT",
    "CORE_SINGLE",
)

COMPOUND_EVENT_SCHEMA = "dreadstone.compound_trauma_event.v1"
COMPOUND_CONTINUITY_MODES = (
    "LOCK_BOUNDARY_TO_SHARED_FIELD",
    "BLEND_ACROSS_SEAM",
    "PROTECT_SEAM",
)

GORE_RECIPE_VERSION = 2
GORE_OVERLAY_MODES = ("SURFACE_STAIN", "STAIN_AND_RAISED")
GORE_MATERIAL_IDS = (
    "DSB_GORE_WET_CRIMSON",
    "DSB_GORE_DARK_CLOT",
    "DSB_GORE_ROUGH_EDGE",
)
GORE_MATERIAL_SPECS = {
    "DSB_GORE_WET_CRIMSON": {
        "baseColor": (0.30, 0.006, 0.004, 1.0),
        "roughness": 0.16,
        "metallic": 0.0,
    },
    "DSB_GORE_DARK_CLOT": {
        "baseColor": (0.075, 0.0015, 0.0012, 1.0),
        "roughness": 0.43,
        "metallic": 0.0,
    },
    "DSB_GORE_ROUGH_EDGE": {
        "baseColor": (0.14, 0.004, 0.003, 1.0),
        "roughness": 0.78,
        "metallic": 0.0,
    },
}


def has_effective_emission(color, strength, epsilon=1e-8):
    """Return whether an RGB emission color and strength produce visible output."""

    emission_strength = float(strength)
    return any(
        abs(float(channel) * emission_strength) > float(epsilon)
        for channel in tuple(color)[:3]
    )


GORE_MAX_TRIANGLES_PER_DEFORMATION = 12000
GORE_MAX_TRIANGLES_PER_ASSET = 48000
GORE_MAX_SURFACE_OFFSET = 0.012
GORE_MIN_SURFACE_OFFSET = 0.00015

RAISED_GORE_DEFAULTS = {
    "goreOverlayMode": "SURFACE_STAIN",
    "goreIntensityClass": "LIGHT",
    "goreRaisedEnabled": False,
    "goreClotCoverage": 0.0,
    "goreCoreDensity": 0.0,
    "goreClotThickness": 0.0015,
    "goreThicknessVariation": 0.0,
    "goreIslandBreakup": 0.0,
    "gorePeripheralFragments": 0.0,
    "goreSurfaceOffset": 0.00035,
    "goreGeometryDensity": 0.35,
    "goreWetnessVariation": 0.0,
    "goreDarkClotBias": 0.0,
    "goreRoughEdgeBias": 0.0,
    "goreColorIntensity": 1.0,
    "goreMaximumTriangles": GORE_MAX_TRIANGLES_PER_DEFORMATION,
    "goreDefaultVisible": False,
    "goreActivationWeight": 0.01,
    "goreUserCustomized": False,
}

GORE_PRESETS = {
    "Gore_Ooze_Wet": {
        "goreCoverage": 0.72,
        "goreScatter": 0.48,
        "goreEdgeFeather": 0.70,
        "goreWetness": 0.92,
        "goreDarkness": 0.38,
        "goreColorBias": (0.34, 0.012, 0.008),
        "gorePatchScale": 0.018,
    },
    "Gore_Clot_Dark": {
        "goreCoverage": 0.64,
        "goreScatter": 0.62,
        "goreEdgeFeather": 0.54,
        "goreWetness": 0.58,
        "goreDarkness": 0.72,
        "goreColorBias": (0.24, 0.008, 0.006),
        "gorePatchScale": 0.012,
    },
    "Gore_Smear_Heavy": {
        "goreCoverage": 0.86,
        "goreScatter": 0.30,
        "goreEdgeFeather": 0.82,
        "goreWetness": 0.80,
        "goreDarkness": 0.48,
        "goreColorBias": (0.38, 0.014, 0.009),
        "gorePatchScale": 0.028,
    },
    "Gore_Speckled_Impact": {
        "goreCoverage": 0.46,
        "goreScatter": 0.90,
        "goreEdgeFeather": 0.62,
        "goreWetness": 0.74,
        "goreDarkness": 0.42,
        "goreColorBias": (0.42, 0.016, 0.010),
        "gorePatchScale": 0.008,
    },
    "Gore_Crush_Bloodied": {
        "goreCoverage": 0.78,
        "goreScatter": 0.68,
        "goreEdgeFeather": 0.66,
        "goreWetness": 0.86,
        "goreDarkness": 0.56,
        "goreColorBias": (0.30, 0.010, 0.007),
        "gorePatchScale": 0.015,
    },
    "Gore_Crush_Heavy_Clotted": {
        "goreCoverage": 0.76,
        "goreScatter": 0.92,
        "goreEdgeFeather": 0.42,
        "goreWetness": 0.82,
        "goreDarkness": 0.68,
        "goreColorBias": (0.31, 0.006, 0.004),
        "gorePatchScale": 0.010,
        "goreOverlayMode": "STAIN_AND_RAISED",
        "goreIntensityClass": "HIGH",
        "goreRaisedEnabled": True,
        "goreClotCoverage": 0.82,
        "goreCoreDensity": 0.94,
        "goreClotThickness": 0.0048,
        "goreThicknessVariation": 0.88,
        "goreIslandBreakup": 0.86,
        "gorePeripheralFragments": 0.58,
        "goreSurfaceOffset": 0.00065,
        "goreGeometryDensity": 0.72,
        "goreWetnessVariation": 0.84,
        "goreDarkClotBias": 0.72,
        "goreRoughEdgeBias": 0.56,
        "goreColorIntensity": 1.0,
        "goreMaximumTriangles": 12000,
        "goreDefaultVisible": False,
        "goreActivationWeight": 0.01,
        "goreUserCustomized": False,
    },
}
DEFAULT_GORE_PRESET_ID = "Gore_Crush_Heavy_Clotted"

GENERATED_AUTHORING_PREFIXES = (
    "DSB_BODY_CORE",
    "DSB_ATTACHED_",
    "DSB_SEGMENT_",
    "DSB_DETACHED_",
    "DSB_STUMP_",
    "DSB_DAMAGE_",
    "DSB_SOCKET_",
    "DSB_SOURCE_MODEL_PROTECTED",
)


def is_generated_authoring_role(
    name: str,
    *,
    generated: bool = False,
    damage_role: str = "",
) -> bool:
    """Return whether an object is authored output rather than a source mesh."""

    normalized_name = str(name or "")
    normalized_role = str(damage_role or "").strip().lower()
    return bool(generated) or bool(normalized_role) or normalized_name.startswith(
        GENERATED_AUTHORING_PREFIXES
    )


def source_readiness_stale_reasons(
    expected: Mapping[str, object],
    current: Mapping[str, object],
) -> list[str]:
    """Compare only fields that define the source-readiness contract.

    Generated topology, shape keys, trauma stamps, preview state, Actions, and
    export metadata are intentionally ignored because they are authoring state.
    """

    reasons: list[str] = []
    expected_revision = str(expected.get("analyzerRevision", ""))
    current_revision = str(current.get("analyzerRevision", ""))
    if expected_revision != current_revision:
        reasons.append(
            "analyzer contract revision changed "
            f"({expected_revision or '<missing>'} -> {current_revision or '<missing>'})"
        )

    expected_armature = dict(expected.get("sourceArmature") or {})  # type: ignore[arg-type]
    current_armature = dict(current.get("sourceArmature") or {})  # type: ignore[arg-type]
    for field, label in (
        ("objectId", "source armature object identity"),
        ("dataId", "source armature datablock identity"),
    ):
        expected_value = str(expected_armature.get(field, ""))
        current_value = str(current_armature.get(field, ""))
        if expected_value and expected_value != current_value:
            reasons.append(f"{label} was lost or replaced")
    if expected_armature.get("armatureSha256") != current_armature.get("armatureSha256"):
        reasons.append("source armature fingerprint changed")
    if expected_armature.get("semanticBoneMapping") != current_armature.get("semanticBoneMapping"):
        reasons.append("source armature semantic bone mapping changed")

    expected_collections = {
        str(record.get("id")) for record in (expected.get("sourceCollections") or [])  # type: ignore[union-attr]
    }
    current_collections = {
        str(record.get("id")) for record in (current.get("sourceCollections") or [])  # type: ignore[union-attr]
    }
    if expected_collections != current_collections:
        reasons.append("source collection identity changed")

    expected_meshes = {
        str(record.get("objectId") or record.get("objectName")): dict(record)
        for record in (expected.get("sourceMeshes") or [])  # type: ignore[union-attr]
    }
    current_meshes = {
        str(record.get("objectId") or record.get("objectName")): dict(record)
        for record in (current.get("sourceMeshes") or [])  # type: ignore[union-attr]
    }
    for identity, expected_mesh in expected_meshes.items():
        label = str(expected_mesh.get("objectName") or identity or "<unknown source mesh>")
        current_mesh = current_meshes.get(identity)
        if current_mesh is None:
            reasons.append(f"source mesh {label} identity was lost or replaced")
            continue
        expected_data_id = str(expected_mesh.get("dataId", ""))
        if expected_data_id and expected_data_id != str(current_mesh.get("dataId", "")):
            reasons.append(f"source mesh {label} datablock identity was lost or replaced")
        if expected_mesh.get("topologySha256") != current_mesh.get("topologySha256"):
            reasons.append(
                f"source mesh {label} topology fingerprint changed "
                f"(expected {expected_mesh.get('topologySha256')}, current {current_mesh.get('topologySha256')})"
            )
        if expected_mesh.get("weightSha256") != current_mesh.get("weightSha256"):
            reasons.append(
                f"source mesh {label} relevant-weight fingerprint changed "
                f"(expected {expected_mesh.get('weightSha256')}, current {current_mesh.get('weightSha256')})"
            )
    unexpected = sorted(set(current_meshes) - set(expected_meshes))
    if unexpected:
        reasons.append("source mesh inventory changed")
    return reasons


def enabled_stamp_contract_errors(
    stamps: Sequence[Mapping[str, object]],
    key_name: str,
) -> list[str]:
    """Require an enabled stamp only for keys that have a procedural stack."""

    if stamps and not any(bool(stamp.get("enabled", True)) for stamp in stamps):
        return [f"deformation key {key_name} has no enabled trauma stamp"]
    return []


def _vector3(value: Sequence[float], label: str) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError(f"{label} must contain three values")
    result = tuple(float(component) for component in value)
    if not all(math.isfinite(component) for component in result):
        raise ValueError(f"{label} contains non-finite values")
    return result  # type: ignore[return-value]


def _add(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _subtract(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(value: Sequence[float], factor: float) -> tuple[float, float, float]:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(value: Sequence[float]) -> float:
    return math.sqrt(_dot(value, value))


def _normalized(value: Sequence[float], label: str = "direction") -> tuple[float, float, float]:
    vector = _vector3(value, label)
    length = _length(vector)
    if length <= 1e-12:
        raise ValueError(f"{label} has zero length")
    if math.isclose(length, 1.0, rel_tol=1e-12, abs_tol=1e-15):
        return vector
    return _scale(vector, 1.0 / length)


def _clamp_vector(value: Sequence[float], maximum: float) -> tuple[float, float, float]:
    if maximum <= 0.0:
        raise ValueError("maximum displacement must be positive")
    length = _length(value)
    if length <= maximum or length <= 1e-15:
        return _vector3(value, "displacement")
    return _scale(value, maximum / length)


def build_virtual_weld_map(
    positions: Sequence[Sequence[float]],
    tolerance: float | None = None,
) -> dict[str, object]:
    """Build a deterministic, non-destructive positional weld description.

    ``positions`` are world-space coordinates. Virtual IDs are assigned in raw
    vertex-index order, and a spatial hash examines only the 27 neighboring
    tolerance cells. No input mesh or coordinate is modified.
    """

    world_positions = tuple(_vector3(position, "position") for position in positions)
    if tolerance is None:
        if world_positions:
            minimum = tuple(min(point[axis] for point in world_positions) for axis in range(3))
            maximum = tuple(max(point[axis] for point in world_positions) for axis in range(3))
            bounds_diagonal = _length(_subtract(maximum, minimum))
        else:
            bounds_diagonal = 0.0
        resolved_tolerance = max(1e-7, bounds_diagonal * 1e-7)
    else:
        resolved_tolerance = float(tolerance)
        if not math.isfinite(resolved_tolerance) or resolved_tolerance <= 0.0:
            raise ValueError("virtual weld tolerance must be finite and positive")

    inverse_tolerance = 1.0 / resolved_tolerance
    tolerance_squared = resolved_tolerance * resolved_tolerance
    buckets: dict[tuple[int, int, int], list[int]] = {}
    seed_positions: list[tuple[float, float, float]] = []
    members: list[list[int]] = []
    raw_to_virtual: list[int] = []

    def cell_for(point: Sequence[float]) -> tuple[int, int, int]:
        return tuple(math.floor(point[axis] * inverse_tolerance) for axis in range(3))  # type: ignore[return-value]

    for raw_index, point in enumerate(world_positions):
        cell = cell_for(point)
        candidates: list[tuple[float, int]] = []
        for offset in product((-1, 0, 1), repeat=3):
            neighbor_cell = (cell[0] + offset[0], cell[1] + offset[1], cell[2] + offset[2])
            for virtual_id in buckets.get(neighbor_cell, ()):
                difference = _subtract(point, seed_positions[virtual_id])
                distance_squared = _dot(difference, difference)
                if distance_squared <= tolerance_squared:
                    candidates.append((distance_squared, virtual_id))
        if candidates:
            virtual_id = min(candidates)[1]
        else:
            virtual_id = len(seed_positions)
            seed_positions.append(point)
            members.append([])
            buckets.setdefault(cell, []).append(virtual_id)
        raw_to_virtual.append(virtual_id)
        members[virtual_id].append(raw_index)

    normalized_members = tuple(tuple(sorted(group)) for group in members)
    digest = hashlib.sha256()
    digest.update(f"tolerance:{resolved_tolerance:.17g}\n".encode("ascii"))
    for raw_index, (point, virtual_id) in enumerate(zip(world_positions, raw_to_virtual)):
        digest.update(
            (
                f"raw:{raw_index}|virtual:{virtual_id}|"
                f"position:{point[0]:.17g},{point[1]:.17g},{point[2]:.17g}\n"
            ).encode("ascii")
        )
    for virtual_id, group in enumerate(normalized_members):
        digest.update(f"members:{virtual_id}:{','.join(map(str, group))}\n".encode("ascii"))
    return {
        "raw_vertex_to_virtual": tuple(raw_to_virtual),
        "virtual_members": normalized_members,
        "tolerance": float(resolved_tolerance),
        "digest": digest.hexdigest(),
    }


def match_positional_anchors(
    target_positions: Sequence[Sequence[float]],
    anchors: Sequence[Sequence[float]],
    tolerance: float | None = None,
) -> dict[str, object]:
    """Match anchors only to analytically coincident target positions.

    This deliberately has no closest-point fallback. It supports index/split
    changes where the authored surface coordinates remain equal within the
    conservative virtual-weld tolerance, and reports every unmatched anchor.
    """

    targets = tuple(_vector3(position, "target position") for position in target_positions)
    normalized_anchors = tuple(_vector3(anchor, "positional anchor") for anchor in anchors)
    combined = targets + normalized_anchors
    weld = build_virtual_weld_map(combined, tolerance=tolerance)
    raw_to_virtual = weld["raw_vertex_to_virtual"]
    members = weld["virtual_members"]
    target_count = len(targets)
    matches = []
    unmatched = []
    for anchor_index in range(len(normalized_anchors)):
        virtual_id = int(raw_to_virtual[target_count + anchor_index])
        candidates = tuple(index for index in members[virtual_id] if index < target_count)
        matches.append(candidates)
        if not candidates:
            unmatched.append(anchor_index)
    return {
        "matches": tuple(matches),
        "unmatched_anchor_indices": tuple(unmatched),
        "tolerance": weld["tolerance"],
        "digest": weld["digest"],
    }


def portable_anchor_tolerance(positions: Sequence[Sequence[float]]) -> float:
    """Allow only small coordinate quantization drift during stamp migration."""

    normalized = tuple(_vector3(position, "target position") for position in positions)
    if not normalized:
        return 1e-6
    minimum = tuple(min(point[axis] for point in normalized) for axis in range(3))
    maximum = tuple(max(point[axis] for point in normalized) for axis in range(3))
    bounds_diagonal = _length(_subtract(maximum, minimum))
    return max(1e-6, bounds_diagonal * 2e-6)


def virtualize_edges(
    edges: Iterable[Sequence[int]],
    raw_vertex_to_virtual: Sequence[int],
) -> tuple[tuple[int, int], ...]:
    """Return sorted unique virtual edges, discarding collapsed raw edges."""

    vertex_count = len(raw_vertex_to_virtual)
    result: set[tuple[int, int]] = set()
    for edge in edges:
        if len(edge) != 2:
            raise ValueError("each virtualized edge must contain two vertex indices")
        left, right = int(edge[0]), int(edge[1])
        if not (0 <= left < vertex_count and 0 <= right < vertex_count):
            raise ValueError(f"edge ({left}, {right}) is outside the vertex range")
        virtual_left = int(raw_vertex_to_virtual[left])
        virtual_right = int(raw_vertex_to_virtual[right])
        if virtual_left == virtual_right:
            continue
        result.add(tuple(sorted((virtual_left, virtual_right))))
    return tuple(sorted(result))


def virtual_face_components(
    faces: Sequence[Sequence[int]],
    raw_vertex_to_virtual: Sequence[int],
) -> tuple[tuple[int, ...], ...]:
    """Group faces that share a complete virtualized edge.

    Sharing only one virtual vertex is deliberately insufficient, so faces that
    merely touch at a corner remain separate components.
    """

    edge_faces: dict[tuple[int, int], list[int]] = {}
    for face_index, face in enumerate(faces):
        raw_vertices = tuple(int(index) for index in face)
        if len(raw_vertices) < 3:
            raise ValueError("each face must contain at least three vertex indices")
        raw_edges = tuple(
            (raw_vertices[index], raw_vertices[(index + 1) % len(raw_vertices)])
            for index in range(len(raw_vertices))
        )
        for edge in virtualize_edges(raw_edges, raw_vertex_to_virtual):
            edge_faces.setdefault(edge, []).append(face_index)

    neighbors = [set() for _ in faces]
    for linked_faces in edge_faces.values():
        for left in linked_faces:
            neighbors[left].update(right for right in linked_faces if right != left)
    remaining = set(range(len(faces)))
    components: list[tuple[int, ...]] = []
    while remaining:
        stack = [min(remaining)]
        component: set[int] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            remaining.discard(current)
            stack.extend(sorted(neighbors[current] - component, reverse=True))
        components.append(tuple(sorted(component)))
    return tuple(components)


def build_weighted_adjacency(
    vertex_count: int,
    edges: Iterable[Sequence[float]],
    positions: Sequence[Sequence[float]] | None = None,
    virtual_members: Sequence[Sequence[int]] | None = None,
) -> tuple[tuple[tuple[int, float], ...], ...]:
    """Build a deterministic undirected weighted vertex adjacency graph.

    Edges may be ``(a, b)`` pairs when world-space positions are supplied, or
    explicit ``(a, b, weight)`` triples. Duplicate edges retain the shortest
    valid weight.
    """

    if vertex_count < 0:
        raise ValueError("vertex_count cannot be negative")
    if positions is not None and len(positions) != vertex_count:
        raise ValueError("positions must match vertex_count")
    world_positions = tuple(_vector3(position, "position") for position in positions) if positions is not None else None
    neighbors: list[dict[int, float]] = [dict() for _ in range(vertex_count)]
    for edge in edges:
        if len(edge) not in {2, 3}:
            raise ValueError("each edge must contain two indices and optional weight")
        left, right = int(edge[0]), int(edge[1])
        if left == right:
            continue
        if not (0 <= left < vertex_count and 0 <= right < vertex_count):
            raise ValueError(f"edge ({left}, {right}) is outside the vertex range")
        if len(edge) == 3:
            weight = float(edge[2])
        elif world_positions is not None:
            weight = _length(_subtract(world_positions[left], world_positions[right]))
        else:
            weight = 1.0
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError(f"edge ({left}, {right}) has invalid weight {weight!r}")
        previous = neighbors[left].get(right)
        if previous is None or weight < previous:
            neighbors[left][right] = weight
            neighbors[right][left] = weight
    if virtual_members is not None:
        claimed: set[int] = set()
        for raw_group in virtual_members:
            group = tuple(sorted({int(index) for index in raw_group}))
            if any(index < 0 or index >= vertex_count for index in group):
                raise ValueError("a virtual weld member is outside the vertex range")
            if claimed.intersection(group):
                raise ValueError("a raw vertex belongs to multiple virtual weld groups")
            claimed.update(group)
            if len(group) < 2:
                continue
            anchor = group[0]
            for member in group[1:]:
                previous = neighbors[anchor].get(member)
                if previous is None or previous > 0.0:
                    neighbors[anchor][member] = 0.0
                    neighbors[member][anchor] = 0.0
    return tuple(tuple(sorted(row.items())) for row in neighbors)


def geodesic_distances(
    adjacency: Sequence[Sequence[tuple[int, float]]],
    seeds: Iterable[int],
    maximum_distance: float | None = None,
) -> dict[int, float]:
    """Return shortest edge-graph distances using radius-limited Dijkstra."""

    if maximum_distance is not None and (not math.isfinite(maximum_distance) or maximum_distance < 0.0):
        raise ValueError("maximum_distance must be finite and non-negative")
    seed_set = sorted({int(seed) for seed in seeds})
    if not seed_set:
        raise ValueError("at least one geodesic seed is required")
    count = len(adjacency)
    if any(seed < 0 or seed >= count for seed in seed_set):
        raise ValueError("a geodesic seed is outside the vertex range")
    distances = {seed: 0.0 for seed in seed_set}
    queue = [(0.0, seed) for seed in seed_set]
    heapq.heapify(queue)
    while queue:
        distance, vertex = heapq.heappop(queue)
        if distance != distances.get(vertex):
            continue
        if maximum_distance is not None and distance > maximum_distance:
            continue
        for neighbor, weight in adjacency[vertex]:
            if neighbor < 0 or neighbor >= count or not math.isfinite(weight) or weight < 0.0:
                raise ValueError("adjacency contains an invalid weighted edge")
            candidate = distance + weight
            if maximum_distance is not None and candidate > maximum_distance:
                continue
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return distances


def selection_hash(
    indices: Iterable[int],
    topology_fingerprint: str = "",
    selection_kind: str = "VERTEX",
) -> str:
    """Hash a selection independently of input ordering or duplicates."""

    normalized = sorted({int(index) for index in indices})
    if any(index < 0 for index in normalized):
        raise ValueError("selection indices cannot be negative")
    payload = {
        "indices": normalized,
        "kind": str(selection_kind).upper(),
        "topologyFingerprint": str(topology_fingerprint),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def geodesic_cache_key(
    topology_fingerprint: str,
    object_identity: str,
    captured_selection_hash: str,
    distance_mode: str,
    maximum_distance: float,
    virtual_weld_digest: str = "",
    virtual_weld_tolerance: float = 0.0,
) -> str:
    """Build a deterministic cache key that cannot cross region/selection state."""

    if distance_mode not in DISTANCE_MODES:
        raise ValueError(f"unsupported distance mode {distance_mode!r}")
    if not math.isfinite(maximum_distance) or maximum_distance < 0.0:
        raise ValueError("maximum_distance must be finite and non-negative")
    if not math.isfinite(virtual_weld_tolerance) or virtual_weld_tolerance < 0.0:
        raise ValueError("virtual_weld_tolerance must be finite and non-negative")
    payload = {
        "topologyFingerprint": str(topology_fingerprint),
        "objectIdentity": str(object_identity),
        "selectionHash": str(captured_selection_hash),
        "distanceMode": distance_mode,
        "maximumDistance": format(float(maximum_distance), ".12g"),
        "virtualWeldDigest": str(virtual_weld_digest),
        "virtualWeldTolerance": format(float(virtual_weld_tolerance), ".17g"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def falloff_weight(distance: float, radius: float, exponent: float = 1.0) -> float:
    if not all(math.isfinite(value) for value in (distance, radius, exponent)):
        raise ValueError("falloff values must be finite")
    if radius <= 0.0:
        raise ValueError("falloff radius must be positive")
    if exponent <= 0.0:
        raise ValueError("falloff exponent must be positive")
    normalized = max(0.0, min(1.0, 1.0 - max(0.0, distance) / radius))
    return normalized**exponent


def surface_mask_weights(
    vertex_count: int,
    selected_indices: Iterable[int],
    distances: Mapping[int, float],
    influence_mode: str,
    radius: float,
    feather_distance: float,
    exponent: float = 1.0,
) -> tuple[float, ...]:
    """Calculate PATCH_ONLY, PATCH_FEATHERED, or CONNECTED_SURFACE weights."""

    if influence_mode not in INFLUENCE_MODES:
        raise ValueError(f"unsupported influence mode {influence_mode!r}")
    if vertex_count < 0:
        raise ValueError("vertex_count cannot be negative")
    selected = {int(index) for index in selected_indices}
    if any(index < 0 or index >= vertex_count for index in selected):
        raise ValueError("a selected vertex is outside the vertex range")
    if not selected:
        raise ValueError("surface masks require at least one selected vertex")
    if feather_distance < 0.0 or not math.isfinite(feather_distance):
        raise ValueError("feather distance must be finite and non-negative")
    weights = [0.0] * vertex_count
    if influence_mode == "PATCH_ONLY":
        for index in selected:
            weights[index] = 1.0
        return tuple(weights)
    if influence_mode == "PATCH_FEATHERED":
        for index in range(vertex_count):
            if index in selected:
                weights[index] = 1.0
            elif feather_distance > 0.0 and index in distances:
                weights[index] = falloff_weight(float(distances[index]), feather_distance, exponent)
        return tuple(weights)
    for index, distance in distances.items():
        if index < 0 or index >= vertex_count:
            raise ValueError("a distance vertex is outside the vertex range")
        weights[index] = falloff_weight(float(distance), radius, exponent)
    return tuple(weights)


def new_stamp_id() -> str:
    """Create an opaque stable ID; duplication always requests a fresh value."""

    return "stamp_" + uuid.uuid4().hex


def new_compound_event_id() -> str:
    """Create an opaque stable semantic event ID."""

    return "compound_" + uuid.uuid4().hex


def derive_participant_seed(event_seed: int, region_id: str, mesh_identity: str) -> int:
    """Derive coordinated but non-identical deterministic participant variation."""

    try:
        seed = int(event_seed)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("compound event seed must be an integer") from None
    if seed < 0 or seed > 2147483647:
        raise ValueError("compound event seed must be from 0 to 2147483647")
    if not str(region_id).strip() or not str(mesh_identity).strip():
        raise ValueError("participant seed derivation requires a region and mesh identity")
    digest = hashlib.sha256(
        f"{seed}|{str(region_id).strip()}|{str(mesh_identity).strip()}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def normalize_world_impact_field(field: Mapping[str, object]) -> dict[str, object]:
    """Canonicalize a shared world-space field used by every event participant."""

    if not isinstance(field, Mapping):
        raise ValueError("compound world-space impact field must be an object")
    try:
        origin = list(_vector3(field.get("origin", ()), "compound field origin"))  # type: ignore[arg-type]
        direction = list(_normalized(field.get("direction", ()), "compound field direction"))  # type: ignore[arg-type]
        normal = list(_normalized(field.get("normal", direction), "compound field normal"))  # type: ignore[arg-type]
        radius = float(field.get("radius", math.nan))
        depth = float(field.get("depth", math.nan))
        falloff = float(field.get("falloff", math.nan))
        strength = float(field.get("strength", math.nan))
        displacement_limit = float(field.get("displacementLimit", math.nan))
        seed = int(field.get("seed", 0))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"compound world-space impact field contains an invalid value: {exc}") from None
    if not all(math.isfinite(value) for value in origin + direction + normal):
        raise ValueError("compound world-space impact vectors must be finite")
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError("compound world-space impact radius must be positive and finite")
    if not math.isfinite(depth) or depth < 0.0:
        raise ValueError("compound world-space impact depth must be finite and non-negative")
    if not math.isfinite(falloff) or falloff <= 0.0:
        raise ValueError("compound world-space impact falloff must be positive and finite")
    if not math.isfinite(strength) or strength < 0.0:
        raise ValueError("compound world-space impact strength must be finite and non-negative")
    if not math.isfinite(displacement_limit) or displacement_limit <= 0.0:
        raise ValueError("compound world-space displacement limit must be positive and finite")
    if seed < 0 or seed > 2147483647:
        raise ValueError("compound world-space field seed must be from 0 to 2147483647")
    family = str(field.get("traumaFamily", "BROAD_CAVE"))
    if family not in TRAUMA_FAMILIES:
        raise ValueError(f"unsupported compound trauma family {family!r}")
    intersections = field.get("participantIntersections", [])
    if not isinstance(intersections, Sequence) or isinstance(intersections, (str, bytes)):
        raise ValueError("compound participant intersections must be an array")
    return {
        "coordinateSpace": "WORLD",
        "origin": origin,
        "direction": direction,
        "normal": normal,
        "radius": radius,
        "depth": depth,
        "falloff": falloff,
        "strength": strength,
        "displacementLimit": displacement_limit,
        "seed": seed,
        "traumaFamily": family,
        "transformReference": str(field.get("transformReference", "WORLD")) or "WORLD",
        "participantIntersections": copy.deepcopy(list(intersections)),
    }


def world_impact_weight(position: Sequence[float], field: Mapping[str, object]) -> float:
    """Evaluate the common radial field at one world-space point."""

    normalized = normalize_world_impact_field(field)
    point = _vector3(position, "world-space field point")
    delta = _subtract(point, normalized["origin"])  # type: ignore[arg-type]
    distance = _length(delta)
    radius = float(normalized["radius"])
    if distance >= radius:
        return 0.0
    normalized_distance = max(0.0, 1.0 - distance / radius)
    return normalized_distance ** float(normalized["falloff"])


def evaluate_world_impact_field(
    positions: Sequence[Sequence[float]],
    field: Mapping[str, object],
    participant_mask: Sequence[float] | None = None,
) -> dict[str, object]:
    """Return per-point world deltas and explicit intersection metadata."""

    normalized = normalize_world_impact_field(field)
    if participant_mask is not None and len(participant_mask) != len(positions):
        raise ValueError("compound participant mask length does not match the mesh")
    direction = normalized["direction"]  # type: ignore[assignment]
    magnitude = min(
        float(normalized["depth"]) * float(normalized["strength"]),
        float(normalized["displacementLimit"]),
    )
    deltas: list[tuple[float, float, float]] = []
    weights: list[float] = []
    affected: list[int] = []
    for index, position in enumerate(positions):
        weight = world_impact_weight(position, normalized)
        if participant_mask is not None:
            mask_value = float(participant_mask[index])
            if not math.isfinite(mask_value) or mask_value < 0.0:
                raise ValueError("compound participant mask values must be finite and non-negative")
            weight *= min(1.0, mask_value)
        delta = _scale(direction, magnitude * weight)
        deltas.append(delta)
        weights.append(weight)
        if weight > 1e-8:
            affected.append(index)
    return {
        "deltas": tuple(deltas),
        "weights": tuple(weights),
        "affectedVertexIndices": tuple(affected),
        "maximumDisplacement": max((_length(delta) for delta in deltas), default=0.0),
    }


def resolve_seam_boundary_displacements(
    first_deltas: Sequence[Sequence[float]],
    second_deltas: Sequence[Sequence[float]],
    mapped_indices: Sequence[Sequence[int]],
    mode: str,
) -> dict[str, object]:
    """Resolve mapped seam deltas without changing either participant topology."""

    if mode not in COMPOUND_CONTINUITY_MODES:
        raise ValueError(f"unsupported compound seam continuity mode {mode!r}")
    first = [list(_vector3(value, "first seam displacement")) for value in first_deltas]
    second = [list(_vector3(value, "second seam displacement")) for value in second_deltas]
    seen_first: set[int] = set()
    seen_second: set[int] = set()
    before = 0.0
    for pair in mapped_indices:
        if len(pair) != 2:
            raise ValueError("each seam mapping must contain two vertex indices")
        first_index, second_index = int(pair[0]), int(pair[1])
        if not 0 <= first_index < len(first) or not 0 <= second_index < len(second):
            raise ValueError("a seam mapping references a vertex outside its participant mesh")
        if first_index in seen_first or second_index in seen_second:
            raise ValueError("compound seam mappings must be one-to-one")
        seen_first.add(first_index)
        seen_second.add(second_index)
        before = max(before, _length(_subtract(first[first_index], second[second_index])))
        if mode == "PROTECT_SEAM":
            resolved = (0.0, 0.0, 0.0)
        else:
            # Both LOCK and BLEND use the compatible mapped-boundary value.
            # BLEND's inward feathering is applied by the Blender integration.
            resolved = _scale(_add(first[first_index], second[second_index]), 0.5)
        first[first_index] = list(resolved)
        second[second_index] = list(resolved)
    after = max(
        (
            _length(_subtract(first[int(pair[0])], second[int(pair[1])]))
            for pair in mapped_indices
        ),
        default=0.0,
    )
    return {
        "firstDeltas": tuple(tuple(value) for value in first),
        "secondDeltas": tuple(tuple(value) for value in second),
        "mappedVertexCount": len(mapped_indices),
        "maximumMismatchBefore": before,
        "maximumMismatchAfter": after,
        "topologyMutated": False,
    }


def _compound_event_digest_payload(event: Mapping[str, object]) -> dict[str, object]:
    payload = copy.deepcopy(dict(event))
    payload.pop("recipeDigest", None)
    payload.pop("validationStatus", None)
    # Intersection counts/digests, generated gore node names, and measured seam
    # reports are deterministic rebuild outputs, not authoring inputs. Keeping
    # them outside the recipe digest prevents identical rebuilds from changing
    # their own seed material while the full library digest still protects the
    # serialized output records from tampering.
    world_field = payload.get("worldField")
    if isinstance(world_field, dict):
        world_field.pop("participantIntersections", None)
    for participant in payload.get("participants", []):
        if not isinstance(participant, dict):
            continue
        for field in (
            "intersectionVertexCount",
            "intersectionDigest",
            "goreRecipeDigest",
            "goreNodeNames",
        ):
            participant.pop(field, None)
    payload.pop("seamContinuity", None)
    return payload


def compound_event_digest(event: Mapping[str, object]) -> str:
    normalized = normalize_compound_event(event, verify_digest=False)
    encoded = json.dumps(
        _compound_event_digest_payload(normalized),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_compound_event(
    event: Mapping[str, object],
    *,
    verify_digest: bool = True,
) -> dict[str, object]:
    """Canonicalize one synchronized multi-region semantic trauma event."""

    if not isinstance(event, Mapping):
        raise ValueError("compound trauma event must be an object")
    event_id = str(event.get("eventId", "")).strip()
    if not event_id:
        raise ValueError("compound trauma event has no stable event ID")
    raw_participants = event.get("participants", [])
    if not isinstance(raw_participants, Sequence) or isinstance(raw_participants, (str, bytes)):
        raise ValueError("compound trauma event participants must be an array")
    participants: list[dict[str, object]] = []
    for raw in raw_participants:
        if not isinstance(raw, Mapping):
            raise ValueError("compound trauma participant must be an object")
        seam_ids = raw.get("seamIds", [])
        gore_nodes = raw.get("goreNodeNames", [])
        if not isinstance(seam_ids, Sequence) or isinstance(seam_ids, (str, bytes)):
            raise ValueError("compound participant seam IDs must be an array")
        if not isinstance(gore_nodes, Sequence) or isinstance(gore_nodes, (str, bytes)):
            raise ValueError("compound participant gore nodes must be an array")
        region_mode = str(raw.get("regionMode", "PAIRED_SEGMENT"))
        if region_mode not in REGION_MODES:
            raise ValueError(f"unsupported compound participant region mode {region_mode!r}")
        participant = {
            "regionId": str(raw.get("regionId", "")).strip(),
            "regionMode": region_mode,
            "targetObject": str(raw.get("targetObject", raw.get("attachedObject", ""))).strip(),
            "detachedObject": str(raw.get("detachedObject", "")).strip(),
            "childKeyName": str(raw.get("childKeyName", "")).strip(),
            "childStampId": str(raw.get("childStampId", "")).strip(),
            "seamIds": sorted({str(value).strip() for value in seam_ids if str(value).strip()}),
            "participantSeed": int(raw.get("participantSeed", 0)),
            "intersectionVertexCount": int(raw.get("intersectionVertexCount", 0)),
            "intersectionDigest": str(raw.get("intersectionDigest", "")),
            "goreRecipeDigest": str(raw.get("goreRecipeDigest", "")),
            "goreNodeNames": sorted({str(value) for value in gore_nodes if str(value)}),
        }
        participants.append(participant)
    try:
        seed = int(event.get("seed", 0))
        activation_weight = float(event.get("activationWeight", 0.01))
        severity_raw = event.get("severity")
        severity = None if severity_raw in (None, "") else float(severity_raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"compound trauma event contains an invalid scalar: {exc}") from None
    linked_seams = event.get("linkedSeamIds", [])
    seam_continuity = event.get("seamContinuity", [])
    if not isinstance(linked_seams, Sequence) or isinstance(linked_seams, (str, bytes)):
        raise ValueError("compound linked seam IDs must be an array")
    if not isinstance(seam_continuity, Sequence) or isinstance(seam_continuity, (str, bytes)):
        raise ValueError("compound seam-continuity records must be an array")
    normalized = {
        "schema": COMPOUND_EVENT_SCHEMA,
        "eventId": event_id,
        "displayName": str(event.get("displayName", event_id)).strip() or event_id,
        "traumaFamily": str(event.get("traumaFamily", "BROAD_CAVE")),
        "impactDirection": str(event.get("impactDirection", "UNSPECIFIED")),
        "severity": severity,
        "worldField": normalize_world_impact_field(event.get("worldField", {})),  # type: ignore[arg-type]
        "participants": sorted(participants, key=lambda value: (str(value["regionId"]), str(value["targetObject"]))),
        "linkedSeamIds": sorted({str(value).strip() for value in linked_seams if str(value).strip()}),
        "continuityMode": str(event.get("continuityMode", "PROTECT_SEAM")),
        "seamContinuity": copy.deepcopy(list(seam_continuity)),
        "activationWeight": activation_weight,
        "activationRule": str(event.get("activationRule", "SYNCHRONIZED_WEIGHT")),
        "goreStyleLinkage": str(event.get("goreStyleLinkage", "SHARED_RECIPE_FAMILY")),
        "seed": seed,
        "validationStatus": str(event.get("validationStatus", "NOT_VALIDATED")),
    }
    errors = validate_compound_event(normalized)
    if errors:
        raise ValueError("; ".join(errors))
    digest = hashlib.sha256(
        json.dumps(
            _compound_event_digest_payload(normalized),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    stored = str(event.get("recipeDigest", ""))
    if verify_digest and stored and stored != digest:
        raise ValueError("compound trauma event recipe digest does not match its contents")
    normalized["recipeDigest"] = digest
    return normalized


def validate_compound_event(
    event: Mapping[str, object],
    *,
    registered_regions: Mapping[str, Mapping[str, object]] | None = None,
) -> list[str]:
    """Validate semantic ownership without requiring Blender mesh data."""

    errors: list[str] = []
    if str(event.get("schema", COMPOUND_EVENT_SCHEMA)) != COMPOUND_EVENT_SCHEMA:
        errors.append("Compound trauma event schema is unsupported.")
    if not str(event.get("eventId", "")).strip():
        errors.append("Compound trauma event has no stable event ID.")
    family = str(event.get("traumaFamily", ""))
    if family not in TRAUMA_FAMILIES:
        errors.append(f"Compound trauma event uses unsupported trauma family {family!r}.")
    continuity = str(event.get("continuityMode", ""))
    if continuity not in COMPOUND_CONTINUITY_MODES:
        errors.append("Compound trauma event has an invalid seam-continuity mode.")
    participants = event.get("participants", [])
    if not isinstance(participants, Sequence) or isinstance(participants, (str, bytes)):
        return errors + ["Compound trauma event participants must be an array."]
    if len(participants) < 2:
        errors.append("Compound trauma event requires at least two participants.")
    try:
        event_seed = int(event.get("seed", -1))
    except (TypeError, ValueError, OverflowError):
        event_seed = -1
    identities: list[tuple[str, str]] = []
    for participant in participants:
        if not isinstance(participant, Mapping):
            errors.append("Compound trauma event contains an invalid participant.")
            continue
        region_id = str(participant.get("regionId", "")).strip()
        target = str(participant.get("targetObject", "")).strip()
        region_mode = str(participant.get("regionMode", ""))
        detached = str(participant.get("detachedObject", "")).strip()
        identities.append((region_id, target))
        if not region_id or not target:
            errors.append("Compound trauma participant requires a region and target mesh identity.")
        if region_mode not in REGION_MODES:
            errors.append(f"Compound participant {region_id or '<missing>'} has an invalid region mode.")
        elif region_mode == "PAIRED_SEGMENT" and not detached:
            errors.append(f"Compound paired participant {region_id or '<missing>'} has no detached mesh identity.")
        elif region_mode == "CORE_SINGLE" and detached:
            errors.append(f"Compound core participant {region_id or '<missing>'} must not require a detached mesh.")
        if not str(participant.get("childKeyName", "")).strip():
            errors.append(f"Compound participant {region_id or '<missing>'} has no child deformation key.")
        if not str(participant.get("childStampId", "")).strip():
            errors.append(f"Compound participant {region_id or '<missing>'} has no child stamp ID.")
        try:
            participant_seed = int(participant.get("participantSeed", -1))
            expected_seed = derive_participant_seed(event_seed, region_id, target)
        except (TypeError, ValueError, OverflowError):
            participant_seed = expected_seed = -1
        if participant_seed != expected_seed:
            errors.append(f"Compound participant {region_id or '<missing>'} has a stale deterministic seed.")
        if registered_regions is not None:
            registered = registered_regions.get(region_id)
            if registered is None:
                errors.append(f"Compound participant region {region_id!r} is not registered.")
            else:
                registered_targets = {
                    str(registered.get(
                        "targetObject",
                        registered.get("sourceTargetObject", registered.get("attachedObject", "")),
                    )),
                    str(registered.get("attachedObject", registered.get("sourceAttachedObject", ""))),
                    str(registered.get("sourceTargetObject", "")),
                    str(registered.get("sourceAttachedObject", "")),
                }
                if target not in registered_targets:
                    errors.append(f"Compound participant {region_id!r} targets the wrong mesh identity.")
                registered_mode = str(registered.get("regionMode", "PAIRED_SEGMENT"))
                if region_mode != registered_mode:
                    errors.append(f"Compound participant {region_id!r} has a stale region-mode binding.")
                registered_detached = str(
                    registered.get("detachedObject", registered.get("sourceDetachedObject", ""))
                )
                if detached != registered_detached:
                    errors.append(f"Compound participant {region_id!r} has a stale detached-mesh binding.")
    duplicates = sorted({identity for identity in identities if identities.count(identity) > 1})
    if duplicates:
        errors.append("Compound trauma event contains a duplicate participant.")
    linked_seams = event.get("linkedSeamIds", [])
    try:
        normalize_world_impact_field(event.get("worldField", {}))  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        errors.append("Compound world-space impact field is invalid: " + str(exc))
    try:
        activation = float(event.get("activationWeight", math.nan))
    except (TypeError, ValueError):
        activation = math.nan
    if not math.isfinite(activation) or not 0.0 <= activation <= 2.0:
        errors.append("Compound activation weight must be finite from zero to two.")
    if not 0 <= event_seed <= 2147483647:
        errors.append("Compound event seed must be from 0 to 2147483647.")
    return errors


def default_gore_overlay(
    preset_id: str = DEFAULT_GORE_PRESET_ID,
    *,
    enabled: bool = False,
    region_id: str = "",
    linked_stamp_id: str = "",
    selection_hash: str = "",
    topology_fingerprint: str = "",
    seed: int = 1776,
) -> dict[str, object]:
    """Create a complete, serialization-safe surface stain / raised-gore recipe."""

    if preset_id not in GORE_PRESETS:
        raise ValueError(f"unsupported surface gore preset {preset_id!r}")
    return normalize_gore_overlay({
        "goreRecipeVersion": GORE_RECIPE_VERSION,
        "goreOverlayEnabled": bool(enabled),
        "gorePresetId": preset_id,
        **GORE_PRESETS[preset_id],
        "goreMaskSeed": int(seed),
        "linkedRegionId": str(region_id),
        "linkedStampId": str(linked_stamp_id),
        "linkedSelectionHash": str(selection_hash),
        "linkedCaptureTopologyFingerprint": str(topology_fingerprint),
        "validationStatus": "NOT_VALIDATED",
    })


def normalize_gore_overlay(overlay: Mapping[str, object]) -> dict[str, object]:
    """Canonicalize a recipe while deterministically migrating Forge 3.12 data.

    Forge 3.12 recipes did not contain raised-gore fields. They intentionally
    migrate to ``SURFACE_STAIN`` so opening an older library never creates new
    geometry until the artist selects a raised preset or explicitly enables it.
    """

    if not isinstance(overlay, Mapping):
        raise ValueError("Surface gore overlay recipe must be an object.")
    preset_id = str(overlay.get("gorePresetId", ""))
    if preset_id not in GORE_PRESETS:
        raise ValueError(f"unsupported surface gore preset {preset_id!r}")
    defaults = GORE_PRESETS[preset_id]
    raised_fields_present = any(
        field in overlay
        for field in (
            "goreRaisedEnabled", "goreClotCoverage", "goreCoreDensity",
            "goreClotThickness", "goreGeometryDensity", "goreOverlayMode",
        )
    )
    raised_defaults = dict(RAISED_GORE_DEFAULTS)
    if raised_fields_present:
        raised_defaults.update({
            key: value for key, value in defaults.items()
            if key in RAISED_GORE_DEFAULTS
        })
    color = overlay.get("goreColorBias", defaults["goreColorBias"])
    try:
        normalized_color = [float(value) for value in color]  # type: ignore[union-attr]
    except (TypeError, ValueError):
        raise ValueError("surface gore color bias must contain three finite channels") from None
    if len(normalized_color) != 3 or any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in normalized_color):
        raise ValueError("surface gore color bias channels must be finite values from zero to one")
    try:
        normalized = {
            "goreRecipeVersion": GORE_RECIPE_VERSION,
            "goreOverlayEnabled": bool(overlay.get("goreOverlayEnabled", False)),
            "gorePresetId": preset_id,
            "goreCoverage": float(overlay.get("goreCoverage", defaults["goreCoverage"])),
            "goreScatter": float(overlay.get("goreScatter", defaults["goreScatter"])),
            "goreEdgeFeather": float(overlay.get("goreEdgeFeather", defaults["goreEdgeFeather"])),
            "goreWetness": float(overlay.get("goreWetness", defaults["goreWetness"])),
            "goreDarkness": float(overlay.get("goreDarkness", defaults["goreDarkness"])),
            "goreColorBias": normalized_color,
            "gorePatchScale": float(overlay.get("gorePatchScale", defaults["gorePatchScale"])),
            "goreOverlayMode": str(overlay.get("goreOverlayMode", raised_defaults["goreOverlayMode"])),
            "goreIntensityClass": str(overlay.get("goreIntensityClass", raised_defaults["goreIntensityClass"])),
            "goreRaisedEnabled": bool(overlay.get("goreRaisedEnabled", raised_defaults["goreRaisedEnabled"])),
            "goreClotCoverage": float(overlay.get("goreClotCoverage", raised_defaults["goreClotCoverage"])),
            "goreCoreDensity": float(overlay.get("goreCoreDensity", raised_defaults["goreCoreDensity"])),
            "goreClotThickness": float(overlay.get("goreClotThickness", raised_defaults["goreClotThickness"])),
            "goreThicknessVariation": float(overlay.get("goreThicknessVariation", raised_defaults["goreThicknessVariation"])),
            "goreIslandBreakup": float(overlay.get("goreIslandBreakup", raised_defaults["goreIslandBreakup"])),
            "gorePeripheralFragments": float(overlay.get("gorePeripheralFragments", raised_defaults["gorePeripheralFragments"])),
            "goreSurfaceOffset": float(overlay.get("goreSurfaceOffset", raised_defaults["goreSurfaceOffset"])),
            "goreGeometryDensity": float(overlay.get("goreGeometryDensity", raised_defaults["goreGeometryDensity"])),
            "goreWetnessVariation": float(overlay.get("goreWetnessVariation", raised_defaults["goreWetnessVariation"])),
            "goreDarkClotBias": float(overlay.get("goreDarkClotBias", raised_defaults["goreDarkClotBias"])),
            "goreRoughEdgeBias": float(overlay.get("goreRoughEdgeBias", raised_defaults["goreRoughEdgeBias"])),
            "goreColorIntensity": float(overlay.get("goreColorIntensity", raised_defaults["goreColorIntensity"])),
            "goreMaximumTriangles": int(overlay.get("goreMaximumTriangles", raised_defaults["goreMaximumTriangles"])),
            "goreDefaultVisible": bool(overlay.get("goreDefaultVisible", raised_defaults["goreDefaultVisible"])),
            "goreActivationWeight": float(overlay.get("goreActivationWeight", raised_defaults["goreActivationWeight"])),
            "goreUserCustomized": bool(overlay.get("goreUserCustomized", raised_defaults["goreUserCustomized"])),
            "goreMaskSeed": int(overlay.get("goreMaskSeed", 1776)),
            "linkedRegionId": str(overlay.get("linkedRegionId", "")),
            "linkedStampId": str(overlay.get("linkedStampId", "")),
            "linkedSelectionHash": str(overlay.get("linkedSelectionHash", "")),
            "linkedCaptureTopologyFingerprint": str(overlay.get("linkedCaptureTopologyFingerprint", "")),
            "validationStatus": str(overlay.get("validationStatus", "NOT_VALIDATED")),
        }
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"surface gore overlay contains an invalid number: {exc}") from None
    errors = validate_gore_overlay(normalized)
    if errors:
        raise ValueError("; ".join(errors))
    return normalized


def validate_gore_overlay(
    overlay: Mapping[str, object],
    *,
    expected_region_id: str | None = None,
    available_stamp_ids: Sequence[str] | None = None,
) -> list[str]:
    """Validate semantic gore data separately from Blender preview resources."""

    errors: list[str] = []
    preset_id = str(overlay.get("gorePresetId", ""))
    if preset_id not in GORE_PRESETS:
        errors.append(f"Surface gore overlay uses unsupported preset {preset_id!r}.")
    if str(overlay.get("goreOverlayMode", "")) not in GORE_OVERLAY_MODES:
        errors.append("Surface gore overlay mode must be SURFACE_STAIN or STAIN_AND_RAISED.")
    if str(overlay.get("goreIntensityClass", "")) not in {"LIGHT", "MEDIUM", "HIGH", "CUSTOM"}:
        errors.append("Surface gore intensity class is invalid.")
    for field in (
        "goreCoverage", "goreScatter", "goreEdgeFeather", "goreWetness", "goreDarkness",
        "goreClotCoverage", "goreCoreDensity", "goreThicknessVariation", "goreIslandBreakup",
        "gorePeripheralFragments", "goreGeometryDensity", "goreWetnessVariation",
        "goreDarkClotBias", "goreRoughEdgeBias", "goreColorIntensity",
    ):
        try:
            value = float(overlay.get(field, math.nan))
        except (TypeError, ValueError):
            value = math.nan
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            errors.append(f"Surface gore overlay {field} must be a finite value from zero to one.")
    try:
        patch_scale = float(overlay.get("gorePatchScale", math.nan))
    except (TypeError, ValueError):
        patch_scale = math.nan
    if not math.isfinite(patch_scale) or patch_scale <= 0.0:
        errors.append("Surface gore overlay gorePatchScale must be positive and finite.")
    for field, minimum, maximum in (
        ("goreClotThickness", 0.0001, 0.05),
        ("goreSurfaceOffset", GORE_MIN_SURFACE_OFFSET, GORE_MAX_SURFACE_OFFSET),
        ("goreActivationWeight", 0.0, 2.0),
    ):
        try:
            value = float(overlay.get(field, math.nan))
        except (TypeError, ValueError):
            value = math.nan
        if not math.isfinite(value) or not minimum <= value <= maximum:
            errors.append(f"Surface gore overlay {field} must be finite from {minimum} to {maximum}.")
    try:
        maximum_triangles = int(overlay.get("goreMaximumTriangles", -1))
    except (TypeError, ValueError, OverflowError):
        maximum_triangles = -1
    if not 128 <= maximum_triangles <= 100000:
        errors.append("Surface gore maximum triangles must be from 128 to 100000.")
    raised_enabled = bool(overlay.get("goreRaisedEnabled", False))
    if raised_enabled and str(overlay.get("goreOverlayMode", "")) != "STAIN_AND_RAISED":
        errors.append("Raised gore requires STAIN_AND_RAISED overlay mode.")
    if raised_enabled and bool(overlay.get("goreDefaultVisible", True)):
        errors.append("Raised gore must be inactive by default in the export contract.")
    color = overlay.get("goreColorBias", ())
    try:
        channels = tuple(float(value) for value in color)  # type: ignore[union-attr]
    except (TypeError, ValueError):
        channels = ()
    if len(channels) != 3 or any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in channels):
        errors.append("Surface gore overlay color bias must contain three finite channels from zero to one.")
    try:
        seed = int(overlay.get("goreMaskSeed", -1))
    except (TypeError, ValueError, OverflowError):
        seed = -1
    if seed < 0 or seed > 2147483647:
        errors.append("Surface gore overlay variation seed must be from 0 to 2147483647.")
    if bool(overlay.get("goreOverlayEnabled", False)):
        linked_region = str(overlay.get("linkedRegionId", ""))
        linked_stamp = str(overlay.get("linkedStampId", ""))
        if not linked_region:
            errors.append("Enabled surface gore overlay has no linked deformation region.")
        elif expected_region_id is not None and linked_region != expected_region_id:
            errors.append("Enabled surface gore overlay links to a stale or incorrect deformation region.")
        if not linked_stamp:
            errors.append("Enabled surface gore overlay has no linked trauma stamp.")
        elif available_stamp_ids is not None and linked_stamp not in set(available_stamp_ids):
            errors.append("Enabled surface gore overlay links to a removed trauma stamp.")
        if not str(overlay.get("linkedSelectionHash", "")):
            errors.append("Enabled surface gore overlay has no usable linked capture selection.")
        if not str(overlay.get("linkedCaptureTopologyFingerprint", "")):
            errors.append("Enabled surface gore overlay has no linked capture topology fingerprint.")
    return errors


def gore_overlay_digest(overlay: Mapping[str, object]) -> str:
    normalized = normalize_gore_overlay(overlay)
    normalized.pop("validationStatus", None)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _legacy_gore_overlay_digest(overlay: Mapping[str, object]) -> str:
    """Reproduce the Forge 3.12 digest for portable-library migration only."""

    preset_id = str(overlay.get("gorePresetId", ""))
    if preset_id not in GORE_PRESETS:
        return ""
    defaults = GORE_PRESETS[preset_id]
    color = [float(value) for value in overlay.get("goreColorBias", defaults["goreColorBias"])]  # type: ignore[union-attr]
    legacy = {
        "goreOverlayEnabled": bool(overlay.get("goreOverlayEnabled", False)),
        "gorePresetId": preset_id,
        "goreCoverage": float(overlay.get("goreCoverage", defaults["goreCoverage"])),
        "goreScatter": float(overlay.get("goreScatter", defaults["goreScatter"])),
        "goreEdgeFeather": float(overlay.get("goreEdgeFeather", defaults["goreEdgeFeather"])),
        "goreWetness": float(overlay.get("goreWetness", defaults["goreWetness"])),
        "goreDarkness": float(overlay.get("goreDarkness", defaults["goreDarkness"])),
        "goreColorBias": color,
        "gorePatchScale": float(overlay.get("gorePatchScale", defaults["gorePatchScale"])),
        "goreMaskSeed": int(overlay.get("goreMaskSeed", 1776)),
        "linkedRegionId": str(overlay.get("linkedRegionId", "")),
        "linkedStampId": str(overlay.get("linkedStampId", "")),
        "linkedSelectionHash": str(overlay.get("linkedSelectionHash", "")),
        "linkedCaptureTopologyFingerprint": str(overlay.get("linkedCaptureTopologyFingerprint", "")),
    }
    encoded = json.dumps(legacy, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def gore_overlay_export_metadata(overlay: Mapping[str, object]) -> dict[str, object]:
    """Build the additive runtime-facing manifest fragment for one deformation."""

    normalized = normalize_gore_overlay(overlay)
    return {
        "surfaceGoreOverlay": normalized,
        "goreOverlayDigest": gore_overlay_digest(normalized),
        "goreOverlayEnabled": bool(normalized["goreOverlayEnabled"]),
        "goreOverlayMode": normalized["goreOverlayMode"],
        "gorePresetId": normalized["gorePresetId"],
        "goreIntensityClass": normalized["goreIntensityClass"],
        "goreDefaultVisible": bool(normalized["goreDefaultVisible"]),
        "goreActivationWeight": float(normalized["goreActivationWeight"]),
    }


def _gore_hash(x: int, y: int, z: int, seed: int) -> float:
    value = (x * 374761393 + y * 668265263 + z * 2147483647 + seed * 1274126177) & 0xFFFFFFFF
    value = ((value ^ (value >> 13)) * 1274126177) & 0xFFFFFFFF
    value ^= value >> 16
    return value / 4294967295.0


def _gore_noise(position: Sequence[float], scale: float, seed: int) -> float:
    coordinates = [float(value) / scale for value in _vector3(position, "gore mask position")]
    lower = [math.floor(value) for value in coordinates]
    fractions = [value - floor for value, floor in zip(coordinates, lower)]
    smooth = [value * value * (3.0 - 2.0 * value) for value in fractions]
    total = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                wx = smooth[0] if dx else 1.0 - smooth[0]
                wy = smooth[1] if dy else 1.0 - smooth[1]
                wz = smooth[2] if dz else 1.0 - smooth[2]
                total += _gore_hash(lower[0] + dx, lower[1] + dy, lower[2] + dz, seed) * wx * wy * wz
    return total


def gore_mask_value(base_weight: float, position: Sequence[float], overlay: Mapping[str, object]) -> float:
    """Return a stable broken stain mask constrained by stamp influence.

    Three frequency bands and a deterministic erosion gate keep the stain from
    becoming one broad circular red gradient. The raised shell uses the same
    seed family, so stain and clots remain visually related without matching
    edge-for-edge.
    """

    recipe = normalize_gore_overlay(overlay)
    weight = min(1.0, max(0.0, float(base_weight)))
    if not recipe["goreOverlayEnabled"] or weight <= 0.0:
        return 0.0
    edge_exponent = 1.0 + 4.0 * (1.0 - float(recipe["goreEdgeFeather"]))
    edge = weight ** edge_exponent
    scale = float(recipe["gorePatchScale"])
    seed = int(recipe["goreMaskSeed"])
    coarse = _gore_noise(position, scale, seed)
    fine = _gore_noise(position, scale * 0.43, seed + 7919)
    fragments = _gore_noise(position, scale * 0.19, seed + 15485863)
    ridges = 1.0 - abs(2.0 * fine - 1.0)
    noise = coarse * 0.48 + fine * 0.24 + ridges * 0.18 + fragments * 0.10
    coverage = float(recipe["goreCoverage"])
    softness = 0.12
    threshold = 1.0 - coverage
    patch = min(1.0, max(0.0, (noise - threshold + softness) / (2.0 * softness)))
    patch = patch * patch * (3.0 - 2.0 * patch)
    scatter = float(recipe["goreScatter"])
    breakup = (1.0 - scatter) + scatter * patch
    erosion = min(1.0, max(0.0, (fragments - (0.22 + scatter * 0.25)) / 0.32))
    clean_gap = (1.0 - scatter * 0.82) + scatter * erosion
    core_stain = edge * ((1.0 - scatter * 0.30) + scatter * 0.30 * coarse)
    return min(1.0, max(0.0, core_stain * breakup * clean_gap))


def gore_generated_object_name(region_id: str, deformation_key: str, pair_role: str) -> str:
    """Return a stable Blender/glTF node name for one generated gore shell."""

    role = str(pair_role).upper()
    if role not in {"ATTACHED", "DETACHED", "CORE"}:
        raise ValueError("raised gore ownership role must be ATTACHED, DETACHED, or CORE")

    def safe(value: str) -> str:
        cleaned = "_".join(filter(None, "".join(
            character if character.isascii() and character.isalnum() else " " for character in str(value)
        ).split()))
        return cleaned or "UNNAMED"

    region = safe(region_id)
    key = safe(deformation_key)
    base = f"DSB_GORE_{role}_{region}_{key}"
    if len(base) <= 63:
        return base
    suffix = hashlib.sha256(base.encode("utf-8")).hexdigest()[:10]
    return base[:52] + "_" + suffix


def deformation_point_digest(
    basis_positions: Sequence[Sequence[float]],
    deformed_positions: Sequence[Sequence[float]],
) -> str:
    """Fingerprint the fully deformed target without coupling to Blender."""

    if len(basis_positions) != len(deformed_positions):
        raise ValueError("basis and deformed point counts differ")
    digest = hashlib.sha256()
    digest.update(f"points:{len(basis_positions)}|".encode("ascii"))
    for basis, deformed in zip(basis_positions, deformed_positions):
        b = _vector3(basis, "basis position")
        d = _vector3(deformed, "deformed position")
        digest.update(
            (",".join(f"{value:.9f}" for value in (*b, *d)) + ";").encode("ascii")
        )
    return digest.hexdigest()


def _face_centroid(
    positions: Sequence[Sequence[float]],
    face: Sequence[int],
) -> tuple[float, float, float]:
    if len(face) < 3:
        raise ValueError("raised gore source faces require at least three vertices")
    points = [_vector3(positions[int(index)], "raised gore position") for index in face]
    inverse = 1.0 / len(points)
    return tuple(sum(point[axis] for point in points) * inverse for axis in range(3))  # type: ignore[return-value]


def raised_gore_face_records(
    positions: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    influence_weights: Sequence[float],
    displacement_magnitudes: Sequence[float],
    overlay: Mapping[str, object],
    *,
    concavity_weights: Sequence[float] | None = None,
) -> list[dict[str, object]]:
    """Select and classify deterministic, region-independent gore shell faces.

    Distribution combines linked stamp influence, actual deformation magnitude,
    optional local concavity, and multi-frequency breakup. No region name, UV,
    material, or anatomical assumption participates in the result.
    """

    recipe = normalize_gore_overlay(overlay)
    if not recipe["goreOverlayEnabled"] or not recipe["goreRaisedEnabled"]:
        return []
    if len(influence_weights) != len(positions) or len(displacement_magnitudes) != len(positions):
        raise ValueError("raised gore weights must match the source point count")
    if concavity_weights is not None and len(concavity_weights) != len(positions):
        raise ValueError("raised gore concavity weights must match the source point count")
    if any(int(index) < 0 or int(index) >= len(positions) for face in faces for index in face):
        raise ValueError("raised gore face references a point outside the source mesh")

    maximum_displacement = max((max(0.0, float(value)) for value in displacement_magnitudes), default=0.0)
    scale = float(recipe["gorePatchScale"])
    seed = int(recipe["goreMaskSeed"])
    coverage = float(recipe["goreClotCoverage"])
    core_density = float(recipe["goreCoreDensity"])
    breakup = float(recipe["goreIslandBreakup"])
    peripheral = float(recipe["gorePeripheralFragments"])
    geometry_density = float(recipe["goreGeometryDensity"])
    base_thickness = float(recipe["goreClotThickness"])
    thickness_variation = float(recipe["goreThicknessVariation"])
    dark_bias = float(recipe["goreDarkClotBias"])
    rough_bias = float(recipe["goreRoughEdgeBias"])
    maximum_triangles = int(recipe["goreMaximumTriangles"])
    candidates: list[dict[str, object]] = []

    for face_index, raw_face in enumerate(faces):
        face = tuple(int(index) for index in raw_face)
        if len(face) < 3 or len(set(face)) < 3:
            continue
        influence = sum(min(1.0, max(0.0, float(influence_weights[index]))) for index in face) / len(face)
        if influence <= 1e-8:
            continue
        displacement = (
            sum(max(0.0, float(displacement_magnitudes[index])) for index in face) / len(face)
            / maximum_displacement
            if maximum_displacement > 1e-12 else 0.0
        )
        concavity = (
            sum(min(1.0, max(0.0, float(concavity_weights[index]))) for index in face) / len(face)
            if concavity_weights is not None else 0.0
        )
        centroid = _face_centroid(positions, face)
        island_noise = _gore_noise(centroid, scale * 0.82, seed + 104729)
        ridge_noise = 1.0 - abs(2.0 * _gore_noise(centroid, scale * 0.31, seed + 130363) - 1.0)
        fragment_noise = _gore_noise(centroid, scale * 0.14, seed + face_index * 17 + 32452843)
        deformation_response = min(1.0, influence * 0.50 + displacement * 0.38 + concavity * 0.12)
        organic = island_noise * 0.52 + ridge_noise * 0.30 + fragment_noise * 0.18

        core_gate = deformation_response >= 0.58 and organic >= 0.16 + (1.0 - core_density) * 0.44
        rim_gate = deformation_response >= 0.24 and organic >= 0.58 - coverage * 0.36 + breakup * 0.08
        outer_gate = (
            deformation_response >= 0.07
            and fragment_noise >= 0.88 - peripheral * 0.34
            and island_noise >= 0.34
        )
        if not (core_gate or rim_gate or outer_gate):
            continue
        # Even high coverage retains narrow clean gaps between clotted islands;
        # only the deepest response may override this deterministic erosion.
        gap_threshold = 0.14 + breakup * 0.24
        if deformation_response < 0.84 and fragment_noise < gap_threshold:
            continue

        density_gate = _gore_hash(face_index, len(face), int(deformation_response * 10000), seed + 49999)
        keep_probability = min(1.0, 0.38 + geometry_density * 0.62 + deformation_response * 0.22)
        if not core_gate and density_gate > keep_probability:
            continue

        thickness_noise = _gore_noise(centroid, scale * 0.23, seed + 86028121)
        fold = 0.52 + 0.70 * ridge_noise + 0.48 * displacement + 0.20 * concavity
        variation = 1.0 + (thickness_noise * 2.0 - 1.0) * thickness_variation * 0.72
        thickness = max(base_thickness * 0.18, base_thickness * deformation_response * fold * variation)
        if outer_gate and not core_gate and not rim_gate:
            thickness *= 0.42

        edge_likelihood = (1.0 - influence) * 0.62 + fragment_noise * 0.38
        dark_likelihood = displacement * 0.48 + thickness_noise * 0.32 + concavity * 0.20
        if edge_likelihood > 0.80 - rough_bias * 0.32:
            material_id = GORE_MATERIAL_IDS[2]
        elif dark_likelihood > 0.78 - dark_bias * 0.38:
            material_id = GORE_MATERIAL_IDS[1]
        else:
            material_id = GORE_MATERIAL_IDS[0]
        triangle_count = 4 * len(face) - 4
        candidates.append({
            "faceIndex": face_index,
            "vertices": list(face),
            "influence": round(influence, 9),
            "deformationResponse": round(deformation_response, 9),
            "thickness": round(thickness, 9),
            "materialId": material_id,
            "zone": "CORE" if core_gate else "RIM" if rim_gate else "PERIPHERAL",
            "priority": round(deformation_response * 0.68 + organic * 0.32, 9),
            "estimatedTriangleCount": triangle_count,
        })

    candidates.sort(key=lambda record: (-float(record["priority"]), int(record["faceIndex"])))
    selected: list[dict[str, object]] = []
    triangles = 0
    for record in candidates:
        count = int(record["estimatedTriangleCount"])
        if triangles + count > maximum_triangles:
            continue
        selected.append(record)
        triangles += count
    selected.sort(key=lambda record: int(record["faceIndex"]))
    return selected


def raised_gore_geometry_digest(
    overlay: Mapping[str, object],
    *,
    source_topology_fingerprint: str,
    deformation_digest: str,
    capture_hash: str,
    pair_role: str,
    face_records: Sequence[Mapping[str, object]],
) -> str:
    """Fingerprint all recipe/input decisions that produce one gore shell."""

    payload = {
        "version": 1,
        "recipeDigest": gore_overlay_digest(overlay),
        "sourceTopologyFingerprint": str(source_topology_fingerprint),
        "deformationDigest": str(deformation_digest),
        "captureHash": str(capture_hash),
        "pairRole": str(pair_role).upper(),
        "faces": [
            {
                "faceIndex": int(record["faceIndex"]),
                "vertices": [int(value) for value in record["vertices"]],
                "thickness": round(float(record["thickness"]), 9),
                "materialId": str(record["materialId"]),
                "zone": str(record["zone"]),
            }
            for record in face_records
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def mesh_geometry_digest(
    vertices: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    material_indices: Sequence[int],
) -> str:
    """Fingerprint an ordinary generated mesh to detect manual alteration."""

    if len(faces) != len(material_indices):
        raise ValueError("generated face/material counts differ")
    digest = hashlib.sha256()
    digest.update(f"v:{len(vertices)}|f:{len(faces)}|".encode("ascii"))
    for vertex in vertices:
        point = _vector3(vertex, "generated gore vertex")
        digest.update((",".join(f"{value:.9f}" for value in point) + ";").encode("ascii"))
    for face, material_index in zip(faces, material_indices):
        digest.update(
            ((",".join(str(int(value)) for value in face)) + f"@{int(material_index)};").encode("ascii")
        )
    return digest.hexdigest()


def raised_gore_stale_reasons(
    overlay: Mapping[str, object],
    generated: Mapping[str, object],
    *,
    region_id: str,
    deformation_key: str,
    topology_fingerprint: str,
    deformation_digest: str,
    capture_hash: str,
    pair_role: str,
    geometry_digest: str,
    material_ids: Sequence[str] = GORE_MATERIAL_IDS,
) -> list[str]:
    """Compare generated ownership/digest metadata with current authoring inputs."""

    recipe = normalize_gore_overlay(overlay)
    reasons: list[str] = []
    expected = {
        "regionId": str(region_id),
        "deformationKey": str(deformation_key),
        "sourceTopologyFingerprint": str(topology_fingerprint),
        "deformationDigest": str(deformation_digest),
        "captureHash": str(capture_hash),
        "pairRole": str(pair_role).upper(),
        "recipeDigest": gore_overlay_digest(recipe),
        "geometryDigest": str(geometry_digest),
    }
    labels = {
        "regionId": "deformation region ownership changed",
        "deformationKey": "deformation key ownership changed",
        "sourceTopologyFingerprint": "region topology changed",
        "deformationDigest": "deformation geometry changed",
        "captureHash": "linked stamp or capture changed",
        "pairRole": "attached/detached pairing changed",
        "recipeDigest": "raised-gore recipe changed",
        "geometryDigest": "generated mesh was manually altered",
    }
    for field, expected_value in expected.items():
        if str(generated.get(field, "")) != expected_value:
            reasons.append(labels[field])
    if not bool(generated.get("forgeOwned", False)):
        reasons.append("generated mesh ownership metadata is missing")
    if bool(generated.get("previewOnly", True)):
        reasons.append("generated gore mesh is incorrectly marked preview-only")
    assigned = tuple(str(value) for value in generated.get("materialIds", ()))
    if assigned != tuple(str(value) for value in material_ids):
        reasons.append("generated gore material assignment is missing or changed")
    if bool(generated.get("defaultVisible", True)) != bool(recipe["goreDefaultVisible"]):
        reasons.append("generated gore inactive-state contract changed")
    return reasons


def raised_gore_budget_errors(
    triangle_counts: Sequence[int],
    *,
    per_deformation_limit: int = GORE_MAX_TRIANGLES_PER_DEFORMATION,
    total_limit: int = GORE_MAX_TRIANGLES_PER_ASSET,
) -> list[str]:
    errors: list[str] = []
    for index, raw_count in enumerate(triangle_counts):
        count = int(raw_count)
        if count < 0:
            errors.append(f"Raised gore mesh {index} has an invalid negative triangle count.")
        elif count > int(per_deformation_limit):
            errors.append(
                f"Raised gore mesh {index} has {count} triangles; limit is {int(per_deformation_limit)}."
            )
    total = sum(max(0, int(value)) for value in triangle_counts)
    if total > int(total_limit):
        errors.append(f"Raised gore asset total is {total} triangles; limit is {int(total_limit)}.")
    return errors


def normalize_stamp(stamp: Mapping[str, object]) -> dict[str, object]:
    """Return a validated, serialization-safe trauma stamp recipe."""

    family = str(stamp.get("family", "COMPACT_DENT"))
    placement_mode = str(stamp.get("placementMode", "SINGLE_FACE"))
    influence_mode = str(stamp.get("influenceMode", "PATCH_FEATHERED"))
    distance_mode = str(stamp.get("distanceMode", "SURFACE_DISTANCE"))
    if family not in TRAUMA_FAMILIES:
        raise ValueError(f"unsupported trauma family {family!r}")
    if placement_mode not in PLACEMENT_MODES:
        raise ValueError(f"unsupported placement mode {placement_mode!r}")
    if influence_mode not in INFLUENCE_MODES:
        raise ValueError(f"unsupported influence mode {influence_mode!r}")
    if distance_mode not in DISTANCE_MODES:
        raise ValueError(f"unsupported distance mode {distance_mode!r}")
    normalized = {
        "stampId": str(stamp.get("stampId") or new_stamp_id()),
        "displayName": str(stamp.get("displayName") or family.replace("_", " ").title()),
        "enabled": bool(stamp.get("enabled", True)),
        "family": family,
        "placementMode": placement_mode,
        "capture": copy.deepcopy(stamp.get("capture") or {}),
        "center": list(_vector3(stamp.get("center", (0.0, 0.0, 0.0)), "stamp center")),  # type: ignore[arg-type]
        "direction": list(_normalized(stamp.get("direction", (0.0, 0.0, -1.0)), "stamp direction")),  # type: ignore[arg-type]
        "radius": float(stamp.get("radius", 0.075)),
        "depth": float(stamp.get("depth", 0.025)),
        "falloff": float(stamp.get("falloff", 2.0)),
        "influenceMode": influence_mode,
        "distanceMode": distance_mode,
        "featherDistance": float(stamp.get("featherDistance", 0.02)),
        "seamProtection": float(stamp.get("seamProtection", 0.025)),
        "strength": float(stamp.get("strength", 1.0)),
        "maximumDisplacement": float(stamp.get("maximumDisplacement", 0.065)),
        "orderIndex": int(stamp.get("orderIndex", 0)),
    }
    direction_mode = stamp.get("directionMode")
    if direction_mode is not None:
        direction_mode = str(direction_mode)
        if direction_mode not in DIRECTION_MODES:
            raise ValueError(f"unsupported damage direction mode {direction_mode!r}")
        normalized["directionMode"] = direction_mode
    direction_local = stamp.get("directionLocal")
    if direction_local is not None:
        normalized["directionLocal"] = list(_normalized(direction_local, "local stamp direction"))  # type: ignore[arg-type]
    errors = validate_stamp_stack([normalized], require_contiguous_order=False)
    if errors:
        raise ValueError("; ".join(errors))
    return normalized


def validate_stamp_stack(
    stamps: Sequence[Mapping[str, object]],
    *,
    require_contiguous_order: bool = True,
) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    orders: list[int] = []
    for position, stamp in enumerate(stamps):
        stamp_id = str(stamp.get("stampId", ""))
        prefix = f"Stamp {stamp_id or position}"
        if not stamp_id:
            errors.append(f"{prefix} has no stable stamp ID.")
        elif stamp_id in seen_ids:
            errors.append(f"Duplicate stamp ID {stamp_id}.")
        seen_ids.add(stamp_id)
        family = str(stamp.get("family", ""))
        if family not in TRAUMA_FAMILIES:
            errors.append(f"{prefix} uses unsupported trauma family {family!r}.")
        if str(stamp.get("placementMode", "")) not in PLACEMENT_MODES:
            errors.append(f"{prefix} has an invalid placement mode.")
        if str(stamp.get("influenceMode", "")) not in INFLUENCE_MODES:
            errors.append(f"{prefix} has an invalid influence mode.")
        if str(stamp.get("distanceMode", "")) not in DISTANCE_MODES:
            errors.append(f"{prefix} has an invalid distance mode.")
        if "directionMode" in stamp and str(stamp.get("directionMode", "")) not in DIRECTION_MODES:
            errors.append(f"{prefix} has an invalid damage direction mode.")
        try:
            _normalized(stamp.get("direction", ()), "stamp direction")  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            errors.append(f"{prefix}: {exc}.")
        if "directionLocal" in stamp:
            try:
                _normalized(stamp.get("directionLocal", ()), "local stamp direction")  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                errors.append(f"{prefix}: {exc}.")
        numeric_rules = (
            ("radius", True, False),
            ("depth", False, False),
            ("falloff", True, False),
            ("featherDistance", False, False),
            ("seamProtection", False, False),
            ("strength", False, False),
            ("maximumDisplacement", True, False),
        )
        for field, must_be_positive, may_be_negative in numeric_rules:
            try:
                value = float(stamp.get(field, math.nan))
            except (TypeError, ValueError):
                value = math.nan
            if not math.isfinite(value):
                errors.append(f"{prefix} has non-finite {field}.")
            elif must_be_positive and value <= 0.0:
                errors.append(f"{prefix} requires positive {field}.")
            elif not may_be_negative and value < 0.0:
                errors.append(f"{prefix} cannot use negative {field}.")
        try:
            order = int(stamp.get("orderIndex", -1))
            orders.append(order)
            if order < 0:
                errors.append(f"{prefix} has an invalid negative order index.")
        except (TypeError, ValueError):
            errors.append(f"{prefix} has an invalid order index.")
    if len(orders) != len(set(orders)):
        errors.append("Trauma stamp order indices must be unique.")
    if require_contiguous_order and orders and sorted(orders) != list(range(len(stamps))):
        errors.append("Trauma stamp order indices must be contiguous from zero.")
    return errors


def ordered_stamps(stamps: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    errors = validate_stamp_stack(stamps)
    if errors:
        raise ValueError("; ".join(errors))
    return [copy.deepcopy(dict(stamp)) for stamp in sorted(stamps, key=lambda value: int(value["orderIndex"]))]


def reindex_stamps(stamps: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    result = [copy.deepcopy(dict(stamp)) for stamp in stamps]
    for index, stamp in enumerate(result):
        stamp["orderIndex"] = index
    return result


def duplicate_stamp(stamp: Mapping[str, object], stamp_id: str | None = None) -> dict[str, object]:
    duplicate = copy.deepcopy(dict(stamp))
    duplicate["stampId"] = stamp_id or new_stamp_id()
    duplicate["displayName"] = str(stamp.get("displayName") or "Trauma Stamp") + " Copy"
    return normalize_stamp(duplicate)


def _stamp_library_digest(payload: Mapping[str, object]) -> str:
    digest_payload = copy.deepcopy(dict(payload))
    digest_payload.pop("libraryDigest", None)
    encoded = json.dumps(
        digest_payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_stamp_library(payload: Mapping[str, object]) -> dict[str, object]:
    """Validate and canonicalize a portable, topology-bound stamp library."""

    if not isinstance(payload, Mapping):
        raise ValueError("Trauma stamp library root must be a JSON object.")
    if payload.get("schema") != STAMP_LIBRARY_SCHEMA:
        raise ValueError(f"Unsupported trauma stamp library schema {payload.get('schema')!r}.")
    try:
        format_version = int(payload.get("formatVersion", -1))
    except (TypeError, ValueError):
        format_version = -1
    if format_version not in SUPPORTED_STAMP_LIBRARY_FORMAT_VERSIONS:
        raise ValueError(f"Unsupported trauma stamp library format version {format_version}.")
    stored_input_digest = payload.get("libraryDigest")
    input_digest_mismatch = bool(
        stored_input_digest and str(stored_input_digest) != _stamp_library_digest(payload)
    )
    producer = payload.get("producer", {})
    if not isinstance(producer, Mapping):
        raise ValueError("Trauma stamp library producer metadata must be an object.")
    raw_regions = payload.get("regions", [])
    if not isinstance(raw_regions, Sequence) or isinstance(raw_regions, (str, bytes)) or not raw_regions:
        raise ValueError("Trauma stamp library must contain at least one authored region.")

    regions: list[dict[str, object]] = []
    seen_regions: set[str] = set()
    total_keys = 0
    total_stamps = 0
    for raw_region in raw_regions:
        if not isinstance(raw_region, Mapping):
            raise ValueError("Every trauma stamp library region must be an object.")
        region_id = str(raw_region.get("regionId", "")).strip()
        if not region_id:
            raise ValueError("A trauma stamp library region has no region ID.")
        if region_id in seen_regions:
            raise ValueError(f"Duplicate trauma stamp library region {region_id!r}.")
        seen_regions.add(region_id)
        region_mode = str(raw_region.get("regionMode", "PAIRED_SEGMENT"))
        if region_mode not in REGION_MODES:
            raise ValueError(f"Region {region_id!r} has unsupported region mode {region_mode!r}.")
        target_object = str(
            raw_region.get("sourceTargetObject", raw_region.get("sourceAttachedObject", ""))
        )
        detached_object = str(raw_region.get("sourceDetachedObject", ""))
        if not target_object:
            raise ValueError(f"Region {region_id!r} has no source target mesh identity.")
        if region_mode == "PAIRED_SEGMENT" and not detached_object:
            raise ValueError(f"Paired region {region_id!r} has no detached mesh identity.")
        if region_mode == "CORE_SINGLE" and detached_object:
            raise ValueError(f"Core single region {region_id!r} must not require a detached mesh.")
        topology = str(raw_region.get("topologyFingerprint", ""))
        if len(topology) != 64 or any(character not in "0123456789abcdef" for character in topology.lower()):
            raise ValueError(f"Region {region_id!r} has an invalid topology fingerprint.")
        try:
            vertex_count = int(raw_region.get("vertexCount", -1))
            polygon_count = int(raw_region.get("polygonCount", -1))
        except (TypeError, ValueError):
            vertex_count = polygon_count = -1
        if vertex_count <= 0 or polygon_count <= 0:
            raise ValueError(f"Region {region_id!r} requires positive vertex and polygon counts.")
        raw_keys = raw_region.get("keys", [])
        if not isinstance(raw_keys, Sequence) or isinstance(raw_keys, (str, bytes)) or not raw_keys:
            raise ValueError(f"Region {region_id!r} contains no trauma-stamp keys.")
        keys: list[dict[str, object]] = []
        seen_keys: set[str] = set()
        for raw_key in raw_keys:
            if not isinstance(raw_key, Mapping):
                raise ValueError(f"Region {region_id!r} contains a non-object key record.")
            key_name = str(raw_key.get("name", "")).strip()
            if not key_name or key_name == "Basis":
                raise ValueError(f"Region {region_id!r} contains an invalid deformation key name.")
            if key_name in seen_keys:
                raise ValueError(f"Region {region_id!r} contains duplicate key {key_name!r}.")
            seen_keys.add(key_name)
            raw_stamps = raw_key.get("stamps", [])
            if not isinstance(raw_stamps, Sequence) or isinstance(raw_stamps, (str, bytes)) or not raw_stamps:
                raise ValueError(f"Deformation key {key_name!r} contains no trauma stamps.")
            stamps = [normalize_stamp(stamp) for stamp in raw_stamps if isinstance(stamp, Mapping)]
            if len(stamps) != len(raw_stamps):
                raise ValueError(f"Deformation key {key_name!r} contains a non-object trauma stamp.")
            stamp_errors = validate_stamp_stack(stamps)
            if stamp_errors:
                raise ValueError(f"Deformation key {key_name!r}: {' '.join(stamp_errors)}")
            calculated_recipe_digest = recipe_digest(stamps)
            stored_recipe_digest = raw_key.get("recipeDigest")
            if stored_recipe_digest and str(stored_recipe_digest) != calculated_recipe_digest:
                raise ValueError(f"Deformation key {key_name!r} has a mismatched recipe digest.")
            try:
                maximum_influence = float(raw_key.get("maximumInfluence", 1.0))
                maximum_displacement = float(raw_key.get("maximumDisplacement", 0.045))
            except (TypeError, ValueError):
                maximum_influence = maximum_displacement = math.nan
            if not math.isfinite(maximum_influence) or maximum_influence <= 0.0:
                raise ValueError(f"Deformation key {key_name!r} requires positive maximum influence.")
            if not math.isfinite(maximum_displacement) or maximum_displacement <= 0.0:
                raise ValueError(f"Deformation key {key_name!r} requires positive maximum displacement.")
            key_record = {
                "name": key_name,
                "family": str(raw_key.get("family", "manual")),
                "side": str(raw_key.get("side", "configurable")),
                "mirrorPartner": str(raw_key.get("mirrorPartner", "")),
                "maximumInfluence": maximum_influence,
                "maximumDisplacement": maximum_displacement,
                "seedRadius": float(raw_key.get("seedRadius", 0.055)),
                "seedDepth": float(raw_key.get("seedDepth", 0.016)),
                "seedFalloff": float(raw_key.get("seedFalloff", 2.2)),
                "recipeDigest": calculated_recipe_digest,
                "stamps": stamps,
            }
            if "surfaceGoreOverlay" in raw_key:
                try:
                    gore_overlay = normalize_gore_overlay(raw_key["surfaceGoreOverlay"])  # type: ignore[arg-type]
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Deformation key {key_name!r} has a broken surface gore overlay recipe: {exc}") from None
                calculated_gore_digest = gore_overlay_digest(gore_overlay)
                stored_gore_digest = raw_key.get("goreOverlayDigest")
                legacy_digest = _legacy_gore_overlay_digest(raw_key["surfaceGoreOverlay"])  # type: ignore[arg-type]
                if (
                    stored_gore_digest
                    and str(stored_gore_digest) != calculated_gore_digest
                    and not (format_version <= 2 and str(stored_gore_digest) == legacy_digest)
                ):
                    raise ValueError(f"Deformation key {key_name!r} has a mismatched surface gore overlay digest.")
                key_record["surfaceGoreOverlay"] = gore_overlay
                key_record["goreOverlayDigest"] = calculated_gore_digest
            keys.append(key_record)
            total_stamps += len(stamps)
        keys.sort(key=lambda value: str(value["name"]))
        total_keys += len(keys)
        regions.append({
            "regionId": region_id,
            "regionMode": region_mode,
            "sourceTargetObject": target_object,
            "sourceAttachedObject": target_object,
            "sourceDetachedObject": detached_object,
            "topologyFingerprint": topology,
            "weightFingerprint": str(raw_region.get("weightFingerprint", "")),
            "vertexCount": vertex_count,
            "polygonCount": polygon_count,
            "relatedSeamId": str(raw_region.get("relatedSeamId", "")),
            "keys": keys,
        })
    regions.sort(key=lambda value: str(value["regionId"]))
    raw_compound_events = payload.get("compoundEvents", [])
    if not isinstance(raw_compound_events, Sequence) or isinstance(raw_compound_events, (str, bytes)):
        raise ValueError("Trauma stamp library compound events must be an array.")
    compound_events = [
        normalize_compound_event(event)
        for event in raw_compound_events
        if isinstance(event, Mapping)
    ]
    if len(compound_events) != len(raw_compound_events):
        raise ValueError("Trauma stamp library contains a non-object compound event.")
    compound_events.sort(key=lambda value: str(value["eventId"]))
    event_ids = [str(event["eventId"]) for event in compound_events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("Trauma stamp library contains duplicate compound event IDs.")
    known_regions = {str(region["regionId"]): region for region in regions}
    for event in compound_events:
        event_errors = validate_compound_event(event, registered_regions=known_regions)
        if event_errors:
            raise ValueError(
                f"Compound event {event['eventId']!r}: " + "; ".join(event_errors)
            )
    normalized: dict[str, object] = {
        "schema": STAMP_LIBRARY_SCHEMA,
        "formatVersion": format_version,
        "producer": {
            "forgeVersion": str(producer.get("forgeVersion", "")),
            "deformationBuildId": str(producer.get("deformationBuildId", "")),
        },
        "regionCount": len(regions),
        "keyCount": total_keys,
        "stampCount": total_stamps,
        "compoundEventCount": len(compound_events),
        "regions": regions,
        "compoundEvents": compound_events,
    }
    calculated_library_digest = _stamp_library_digest(normalized)
    if input_digest_mismatch:
        raise ValueError("Trauma stamp library digest does not match its contents.")
    normalized["libraryDigest"] = calculated_library_digest
    return normalized


def build_stamp_library(
    regions: Sequence[Mapping[str, object]],
    producer_version: str,
    producer_build_id: str,
    compound_events: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Build a deterministic, versioned library from authored region records."""

    return normalize_stamp_library({
        "schema": STAMP_LIBRARY_SCHEMA,
        "formatVersion": STAMP_LIBRARY_FORMAT_VERSION,
        "producer": {
            "forgeVersion": str(producer_version),
            "deformationBuildId": str(producer_build_id),
        },
        "regions": list(regions),
        "compoundEvents": list(compound_events),
    })


def stamp_library_compatibility_errors(
    library: Mapping[str, object],
    target_regions: Mapping[str, Mapping[str, object]],
) -> list[str]:
    """Require exact topology/count compatibility before applying captures."""

    normalized = normalize_stamp_library(library)
    errors: list[str] = []
    for region in normalized["regions"]:  # type: ignore[assignment]
        region_id = str(region["regionId"])
        target = target_regions.get(region_id)
        if target is None:
            errors.append(f"Stamp library region {region_id!r} is not registered in this scene.")
            continue
        if str(target.get("regionMode", region["regionMode"])) != str(region["regionMode"]):
            errors.append(f"Stamp library region {region_id!r} mode does not match the explicit current registration.")
        if str(target.get("topologyFingerprint", "")) != region["topologyFingerprint"]:
            errors.append(f"Stamp library region {region_id!r} topology does not match the current attached mesh.")
        try:
            vertex_matches = int(target.get("vertexCount", -1)) == int(region["vertexCount"])
            polygon_matches = int(target.get("polygonCount", -1)) == int(region["polygonCount"])
        except (TypeError, ValueError):
            vertex_matches = polygon_matches = False
        if not vertex_matches:
            errors.append(f"Stamp library region {region_id!r} vertex count does not match.")
        if not polygon_matches:
            errors.append(f"Stamp library region {region_id!r} polygon count does not match.")
    return errors


def stamp_displacement(
    position: Sequence[float],
    stamp: Mapping[str, object],
    influence: float,
    distance: float | None = None,
) -> tuple[float, float, float]:
    """Evaluate one family in world space for one vertex."""

    recipe = normalize_stamp(stamp)
    return _normalized_stamp_displacement(position, recipe, influence, distance)


def _normalized_stamp_displacement(
    position: Sequence[float],
    recipe: Mapping[str, object],
    influence: float,
    distance: float | None = None,
) -> tuple[float, float, float]:
    weight = max(0.0, min(1.0, float(influence)))
    if weight <= 0.0 or not recipe["enabled"]:
        return (0.0, 0.0, 0.0)
    point = _vector3(position, "position")
    center = _vector3(recipe["center"], "stamp center")  # type: ignore[arg-type]
    direction = _normalized(recipe["direction"], "stamp direction")  # type: ignore[arg-type]
    depth = float(recipe["depth"])
    radius = float(recipe["radius"])
    strength = float(recipe["strength"])
    family = str(recipe["family"])
    if distance is None:
        distance = _length(_subtract(point, center))
    radial_fraction = max(0.0, min(1.5, float(distance) / radius))
    if family == "COMPACT_DENT":
        displacement = _scale(direction, depth * strength * weight**1.25)
    elif family == "BROAD_CAVE":
        displacement = _scale(direction, depth * strength * weight**0.72)
    elif family == "FLAT_COMPRESSION":
        plane_point = _add(center, _scale(direction, depth))
        signed_to_plane = _dot(_subtract(plane_point, point), direction)
        displacement = _scale(direction, signed_to_plane * min(1.0, strength * weight))
    elif family == "DIRECTIONAL_SHEAR":
        displacement = _scale(direction, depth * strength * weight)
    elif family == "RAISED_IMPACT_RIM":
        ring = math.exp(-((radial_fraction - 0.78) / 0.14) ** 2)
        displacement = _scale(direction, -depth * 0.25 * strength * ring * max(weight, 0.2))
    else:  # RIDGE_COLLAPSE
        protrusion = min(1.0, abs(_dot(_subtract(point, center), direction)) / radius)
        displacement = _scale(direction, depth * strength * weight**1.35 * (0.55 + 0.45 * protrusion))
    return _clamp_vector(displacement, float(recipe["maximumDisplacement"]))


def evaluate_stamp_stack(
    basis_positions: Sequence[Sequence[float]],
    stamps: Sequence[Mapping[str, object]],
    weights_by_stamp: Mapping[str, Sequence[float]],
    distances_by_stamp: Mapping[str, Mapping[int, float]] | None = None,
) -> tuple[tuple[float, float, float], ...]:
    """Replay enabled stamps from Basis in explicit order without drift."""

    basis = tuple(_vector3(position, "basis position") for position in basis_positions)
    result = list(basis)
    distances_by_stamp = distances_by_stamp or {}
    for raw_stamp in ordered_stamps(stamps):
        stamp = normalize_stamp(raw_stamp)
        if not bool(stamp.get("enabled", True)):
            continue
        stamp_id = str(stamp["stampId"])
        weights = weights_by_stamp.get(stamp_id)
        if weights is None or len(weights) != len(result):
            raise ValueError(f"Stamp {stamp_id} has no complete influence weights")
        distances = distances_by_stamp.get(stamp_id, {})
        maximum = float(stamp["maximumDisplacement"])
        for index, current in enumerate(result):
            displacement = _normalized_stamp_displacement(current, stamp, float(weights[index]), distances.get(index))
            candidate = _add(current, displacement)
            total_delta = _clamp_vector(_subtract(candidate, basis[index]), maximum)
            result[index] = _add(basis[index], total_delta)
    return tuple(result)


def recipe_digest(stamps: Sequence[Mapping[str, object]]) -> str:
    """Hash normalized explicit order for deterministic rebuild metadata."""

    normalized = [normalize_stamp(stamp) for stamp in ordered_stamps(stamps)]
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
