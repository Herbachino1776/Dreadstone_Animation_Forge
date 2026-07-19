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
STAMP_LIBRARY_FORMAT_VERSION = 2
SUPPORTED_STAMP_LIBRARY_FORMAT_VERSIONS = (1, 2)

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
}
DEFAULT_GORE_PRESET_ID = "Gore_Ooze_Wet"

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
    """Create a complete, serialization-safe blunt-trauma overlay recipe."""

    if preset_id not in GORE_PRESETS:
        raise ValueError(f"unsupported surface gore preset {preset_id!r}")
    return normalize_gore_overlay({
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
    """Canonicalize the optional surface-gore recipe without preview-only state."""

    if not isinstance(overlay, Mapping):
        raise ValueError("Surface gore overlay recipe must be an object.")
    preset_id = str(overlay.get("gorePresetId", ""))
    if preset_id not in GORE_PRESETS:
        raise ValueError(f"unsupported surface gore preset {preset_id!r}")
    defaults = GORE_PRESETS[preset_id]
    color = overlay.get("goreColorBias", defaults["goreColorBias"])
    try:
        normalized_color = [float(value) for value in color]  # type: ignore[union-attr]
    except (TypeError, ValueError):
        raise ValueError("surface gore color bias must contain three finite channels") from None
    if len(normalized_color) != 3 or any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in normalized_color):
        raise ValueError("surface gore color bias channels must be finite values from zero to one")
    try:
        normalized = {
            "goreOverlayEnabled": bool(overlay.get("goreOverlayEnabled", False)),
            "gorePresetId": preset_id,
            "goreCoverage": float(overlay.get("goreCoverage", defaults["goreCoverage"])),
            "goreScatter": float(overlay.get("goreScatter", defaults["goreScatter"])),
            "goreEdgeFeather": float(overlay.get("goreEdgeFeather", defaults["goreEdgeFeather"])),
            "goreWetness": float(overlay.get("goreWetness", defaults["goreWetness"])),
            "goreDarkness": float(overlay.get("goreDarkness", defaults["goreDarkness"])),
            "goreColorBias": normalized_color,
            "gorePatchScale": float(overlay.get("gorePatchScale", defaults["gorePatchScale"])),
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
    for field in ("goreCoverage", "goreScatter", "goreEdgeFeather", "goreWetness", "goreDarkness"):
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


def gore_overlay_export_metadata(overlay: Mapping[str, object]) -> dict[str, object]:
    """Build the additive runtime-facing manifest fragment for one deformation."""

    normalized = normalize_gore_overlay(overlay)
    return {
        "surfaceGoreOverlay": normalized,
        "goreOverlayDigest": gore_overlay_digest(normalized),
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
    """Return a stable organic mask constrained by the captured stamp influence."""

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
    noise = coarse * 0.72 + fine * 0.28
    coverage = float(recipe["goreCoverage"])
    softness = 0.12
    threshold = 1.0 - coverage
    patch = min(1.0, max(0.0, (noise - threshold + softness) / (2.0 * softness)))
    patch = patch * patch * (3.0 - 2.0 * patch)
    scatter = float(recipe["goreScatter"])
    breakup = (1.0 - scatter) + scatter * patch
    return min(1.0, max(0.0, edge * breakup))


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
                if stored_gore_digest and str(stored_gore_digest) != calculated_gore_digest:
                    raise ValueError(f"Deformation key {key_name!r} has a mismatched surface gore overlay digest.")
                key_record["surfaceGoreOverlay"] = gore_overlay
                key_record["goreOverlayDigest"] = calculated_gore_digest
            keys.append(key_record)
            total_stamps += len(stamps)
        keys.sort(key=lambda value: str(value["name"]))
        total_keys += len(keys)
        regions.append({
            "regionId": region_id,
            "sourceAttachedObject": str(raw_region.get("sourceAttachedObject", "")),
            "sourceDetachedObject": str(raw_region.get("sourceDetachedObject", "")),
            "topologyFingerprint": topology,
            "vertexCount": vertex_count,
            "polygonCount": polygon_count,
            "relatedSeamId": str(raw_region.get("relatedSeamId", "")),
            "keys": keys,
        })
    regions.sort(key=lambda value: str(value["regionId"]))
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
        "regions": regions,
    }
    calculated_library_digest = _stamp_library_digest(normalized)
    stored_library_digest = payload.get("libraryDigest")
    if stored_library_digest and str(stored_library_digest) != calculated_library_digest:
        raise ValueError("Trauma stamp library digest does not match its contents.")
    normalized["libraryDigest"] = calculated_library_digest
    return normalized


def build_stamp_library(
    regions: Sequence[Mapping[str, object]],
    producer_version: str,
    producer_build_id: str,
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
