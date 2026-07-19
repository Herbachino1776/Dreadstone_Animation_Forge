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
        try:
            _normalized(stamp.get("direction", ()), "stamp direction")  # type: ignore[arg-type]
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
