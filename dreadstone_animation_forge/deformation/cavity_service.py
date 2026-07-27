"""Blender-free cavity/inlay mesh construction and numerical measurements.

The service only consumes evaluated source-surface data and normalized recipe
values.  It never edits source topology.  Blender object ownership, material
datablocks, attributes, skinning, and transactions remain in the facade.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence


LAYER_RIM = 0
LAYER_CLOT = 1
LAYER_TISSUE = 2
LAYER_LINER = 3
LAYER_BONE = 4
LAYER_BARRIER = 5

LAYER_NAMES = {
    LAYER_RIM: "RIM",
    LAYER_CLOT: "CLOT",
    LAYER_TISSUE: "TISSUE",
    LAYER_LINER: "LINER",
    LAYER_BONE: "BONE",
    LAYER_BARRIER: "BARRIER",
}


def _vec3(value, label):
    try:
        result = tuple(float(channel) for channel in value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must contain three finite values") from None
    if len(result) != 3 or any(not math.isfinite(channel) for channel in result):
        raise ValueError(f"{label} must contain three finite values")
    return result


def _add(first, second):
    return tuple(a + b for a, b in zip(first, second))


def _sub(first, second):
    return tuple(a - b for a, b in zip(first, second))


def _mul(value, factor):
    return tuple(channel * float(factor) for channel in value)


def _dot(first, second):
    return sum(a * b for a, b in zip(first, second))


def _length(value):
    return math.sqrt(max(0.0, _dot(value, value)))


def _normal(value):
    length = _length(value)
    if length <= 1e-15:
        return (0.0, 0.0, 1.0)
    return tuple(channel / length for channel in value)


def _blend_values(values, blend):
    result = (0.0, 0.0, 0.0)
    for index, weight in blend.items():
        result = _add(result, _mul(values[int(index)], float(weight)))
    return result


def _normalize_blend(blend):
    merged = {}
    for raw_index, raw_weight in blend.items():
        index = int(raw_index)
        weight = max(0.0, float(raw_weight))
        if weight > 0.0:
            merged[index] = merged.get(index, 0.0) + weight
    total = sum(merged.values())
    if total <= 1e-15:
        raise ValueError("cavity source interpolation produced no usable weight")
    return {index: value / total for index, value in merged.items()}


def _lerp_blend(first, second, factor):
    amount = min(1.0, max(0.0, float(factor)))
    result = {}
    for index, weight in first.items():
        result[int(index)] = result.get(int(index), 0.0) + float(weight) * (1.0 - amount)
    for index, weight in second.items():
        result[int(index)] = result.get(int(index), 0.0) + float(weight) * amount
    return _normalize_blend(result)


def _unit(seed, *values):
    payload = "|".join(str(int(value)) for value in (seed, *values)).encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / float((1 << 64) - 1)


def _median(values):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) * 0.5


def _triangle_count(face):
    return max(0, len(tuple(face)) - 2)


def _components(face_records):
    edge_records = {}
    for record_index, record in enumerate(face_records):
        face = [int(index) for index in record["vertices"]]
        for offset, first in enumerate(face):
            edge = tuple(sorted((first, face[(offset + 1) % len(face)])))
            edge_records.setdefault(edge, []).append(record_index)
    adjacency = {index: set() for index in range(len(face_records))}
    for record_indices in edge_records.values():
        for first in record_indices:
            adjacency[first].update(value for value in record_indices if value != first)
    result = []
    remaining = set(range(len(face_records)))
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        stack = [seed]
        component = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current] & remaining, reverse=True):
                remaining.remove(neighbor)
                stack.append(neighbor)
        result.append(sorted(component))
    return result


def build_cavity_inlay(
    positions: Sequence[Sequence[float]],
    normals: Sequence[Sequence[float]],
    face_records: Sequence[Mapping[str, object]],
    recipe: Mapping[str, object],
    material_roles: Mapping[str, str],
) -> dict[str, object]:
    """Build closed, manifold Forge-owned geometry below an evaluated surface.

    The principal liner is one closed solid per selected face component.  Its
    boundary vertices remain close to the host while edge midpoints and face
    centers step inward, producing a controlled rim-to-bed transition without
    cutting, deleting, welding, or reordering the source mesh.  Optional clot,
    tissue, barrier, and bone plates are explicitly recipe-owned internal
    fragments with deterministic source interpolation.
    """

    source_positions = tuple(_vec3(value, "cavity source position") for value in positions)
    source_normals = tuple(_normal(_vec3(value, "cavity source normal")) for value in normals)
    if len(source_positions) != len(source_normals):
        raise ValueError("cavity source positions and normals must have the same length")
    records = [dict(record) for record in face_records]
    if not records:
        raise ValueError("cavity inlay requires at least one selected source face")
    if any(
        int(index) < 0 or int(index) >= len(source_positions)
        for record in records for index in record.get("vertices", ())
    ):
        raise ValueError("cavity inlay face references a source vertex outside the mesh")

    cavity_depth = max(0.0, float(recipe.get("goreCavityDepth", 0.0)))
    separation = max(0.00002, float(recipe.get("goreLinerSeparation", 0.00035)))
    clot_depth = max(separation, float(recipe.get("goreClotFillDepth", separation * 2.0)))
    clot_coverage = min(1.0, max(0.0, float(recipe.get("goreClotCoverage", 0.0))))
    tissue_coverage = min(1.0, max(0.0, float(recipe.get("goreTissueCoverage", 0.0))))
    bone_reveal = min(1.0, max(0.0, float(recipe.get("goreBoneReveal", 0.0))))
    breakup = min(1.0, max(0.0, float(recipe.get("goreIslandBreakup", 0.0))))
    variation = min(1.0, max(0.0, float(recipe.get("goreThicknessVariation", 0.0))))
    seed = int(recipe.get("goreMaskSeed", 1776))
    maximum_triangles = max(128, int(recipe.get("goreMaximumTriangles", 12000)))
    wall_thickness = max(separation * 0.72, cavity_depth * 0.035, 0.00002)

    material_ids = []
    for role in ("WET", "CLOT", "EDGE", "BED", "TISSUE", "BONE"):
        material_id = str(material_roles[role])
        if material_id not in material_ids:
            material_ids.append(material_id)
    material_lookup = {material_id: index for index, material_id in enumerate(material_ids)}

    vertices = []
    surface_positions = []
    source_normals_out = []
    source_blends = []
    source_indices = []
    vertex_depths = []
    vertex_layers = []
    faces = []
    material_indices = []
    face_layers = []
    texture_variants = []

    def surface_and_normal(raw_blend):
        blend = _normalize_blend(raw_blend)
        surface = _blend_values(source_positions, blend)
        normal = _normal(_blend_values(source_normals, blend))
        return blend, surface, normal

    def add_vertex(raw_blend, depth, layer):
        blend, surface, normal = surface_and_normal(raw_blend)
        inward_depth = max(0.0, float(depth))
        generated = _sub(surface, _mul(normal, inward_depth))
        index = len(vertices)
        vertices.append(generated)
        surface_positions.append(surface)
        source_normals_out.append(normal)
        source_blends.append(blend)
        source_indices.append(max(blend, key=lambda value: (blend[value], -value)))
        vertex_depths.append(inward_depth)
        vertex_layers.append(int(layer))
        return index

    def add_face(indices, material_id, layer, variant_value):
        face = tuple(int(index) for index in indices)
        if len(face) < 3 or len(set(face)) != len(face):
            raise ValueError("cavity builder produced a degenerate face")
        faces.append(face)
        material_indices.append(material_lookup[str(material_id)])
        face_layers.append(int(layer))
        texture_variants.append(int(variant_value) % 4)

    estimated = 0
    for record in records:
        count = len(tuple(record["vertices"]))
        estimated += count * 6
    enabled_plate_count = sum(bool(recipe.get(field, False)) for field in (
        "goreClotLayerEnabled",
        "goreTissueLayerEnabled",
        "goreBoneLayerEnabled",
        "goreBarrierLayerEnabled",
    ))
    estimated += sum(max(0, len(tuple(record["vertices"])) * 4 - 4) for record in records) * enabled_plate_count
    if estimated > maximum_triangles:
        limit = max(1, int(len(records) * maximum_triangles / max(estimated, 1)))
        records = sorted(
            records,
            key=lambda record: (-float(record.get("priority", 0.0)), int(record["faceIndex"])),
        )[:limit]
        records.sort(key=lambda record: int(record["faceIndex"]))

    for component in _components(records):
        component_edges = {}
        face_data = {}
        component_sources = set()
        for record_index in component:
            record = records[record_index]
            face = [int(index) for index in record["vertices"]]
            component_sources.update(face)
            center_blend = {index: 1.0 / len(face) for index in face}
            face_data[record_index] = {"face": face, "centerBlend": center_blend}
            for offset, first in enumerate(face):
                second = face[(offset + 1) % len(face)]
                component_edges.setdefault(tuple(sorted((first, second))), []).append(
                    (record_index, first, second)
                )

        boundary_vertices = {
            index
            for edge, uses in component_edges.items() if len(uses) == 1
            for index in edge
        }
        corner_top = {}
        corner_bottom = {}
        for source_index in sorted(component_sources):
            boundary = source_index in boundary_vertices
            irregular = (_unit(seed, source_index, 3101) * 2.0 - 1.0) * variation
            usable_depth = max(0.0, cavity_depth - separation)
            depth = separation + usable_depth * (
                (0.055 if boundary else 0.22)
                + (0.028 if boundary else 0.07) * irregular
            )
            depth = min(max(separation, depth), max(separation, cavity_depth))
            blend = {source_index: 1.0}
            corner_layer = LAYER_RIM if boundary else LAYER_LINER
            corner_top[source_index] = add_vertex(blend, depth, corner_layer)
            corner_bottom[source_index] = add_vertex(
                blend, depth + wall_thickness, corner_layer
            )

        edge_top = {}
        edge_bottom = {}
        edge_blends = {}
        for edge, uses in sorted(component_edges.items()):
            first, second = edge
            ratio = 0.5 + (_unit(seed, first, second, 3203) - 0.5) * 0.22 * variation
            blend = _normalize_blend({first: 1.0 - ratio, second: ratio})
            boundary = len(uses) == 1
            irregular = (_unit(seed, first, second, 3209) * 2.0 - 1.0) * variation
            usable_depth = max(0.0, cavity_depth - separation)
            depth = separation + usable_depth * (
                (0.22 if boundary else 0.46)
                + (0.06 if boundary else 0.10) * irregular
            )
            depth = min(max(separation, depth), max(separation, cavity_depth))
            edge_blends[edge] = blend
            edge_top[edge] = add_vertex(blend, depth, LAYER_RIM if boundary else LAYER_LINER)
            edge_bottom[edge] = add_vertex(
                blend, depth + wall_thickness, LAYER_RIM if boundary else LAYER_LINER
            )

        center_top = {}
        center_bottom = {}
        for record_index in component:
            record = records[record_index]
            face_index = int(record["faceIndex"])
            irregular = (_unit(seed, face_index, 3301) * 2.0 - 1.0) * variation
            usable_depth = max(0.0, cavity_depth - separation)
            depth = separation + usable_depth * (0.80 + 0.15 * irregular)
            depth = min(max(separation, depth), max(separation, cavity_depth))
            center_blend = face_data[record_index]["centerBlend"]
            center_top[record_index] = add_vertex(center_blend, depth, LAYER_LINER)
            center_bottom[record_index] = add_vertex(
                center_blend, depth + wall_thickness, LAYER_LINER
            )

        for record_index in component:
            record = records[record_index]
            face = face_data[record_index]["face"]
            face_index = int(record["faceIndex"])
            for edge_index, first in enumerate(face):
                second = face[(edge_index + 1) % len(face)]
                edge = tuple(sorted((first, second)))
                boundary = len(component_edges[edge]) == 1
                layer = LAYER_RIM if boundary else LAYER_LINER
                material = material_roles["EDGE"] if boundary else material_roles["BED"]
                variant = int(_unit(seed, face_index, edge_index, 3407) * 4.0)
                add_face(
                    (corner_top[first], edge_top[edge], center_top[record_index]),
                    material, layer, variant,
                )
                add_face(
                    (edge_top[edge], corner_top[second], center_top[record_index]),
                    material, layer, variant,
                )
                add_face(
                    (center_bottom[record_index], edge_bottom[edge], corner_bottom[first]),
                    material_roles["BED"], LAYER_LINER, variant,
                )
                add_face(
                    (center_bottom[record_index], corner_bottom[second], edge_bottom[edge]),
                    material_roles["BED"], LAYER_LINER, variant,
                )

        for edge, uses in sorted(component_edges.items()):
            if len(uses) != 1:
                continue
            record_index, first, second = uses[0]
            variant = int(_unit(seed, first, second, 3501) * 4.0)
            add_face(
                (corner_top[first], corner_bottom[first], edge_bottom[edge], edge_top[edge]),
                material_roles["EDGE"], LAYER_RIM, variant,
            )
            add_face(
                (edge_top[edge], edge_bottom[edge], corner_bottom[second], corner_top[second]),
                material_roles["EDGE"], LAYER_RIM, variant,
            )

    def add_plate(record, *, layer, depth, thickness, inset, material_id, salt):
        face = [int(index) for index in record["vertices"]]
        center_blend = {index: 1.0 / len(face) for index in face}
        top = []
        bottom = []
        for offset, source_index in enumerate(face):
            jitter = (_unit(seed, int(record["faceIndex"]), offset, salt) - 0.5) * 0.12 * variation
            corner_blend = _lerp_blend(
                {source_index: 1.0},
                center_blend,
                min(0.72, max(0.08, inset + jitter)),
            )
            top.append(add_vertex(corner_blend, depth, layer))
            bottom.append(add_vertex(corner_blend, depth + thickness, layer))
        variant = int(_unit(seed, int(record["faceIndex"]), salt, 3701) * 4.0)
        add_face(tuple(top), material_id, layer, variant)
        add_face(tuple(reversed(bottom)), material_id, layer, variant)
        for offset, first in enumerate(top):
            following = (offset + 1) % len(top)
            add_face(
                (first, bottom[offset], bottom[following], top[following]),
                material_id, layer, variant,
            )

    plate_specs = []
    if bool(recipe.get("goreClotLayerEnabled", False)) and clot_coverage > 1e-8:
        plate_specs.append((
            LAYER_CLOT,
            min(max(separation * 1.5, clot_depth), max(separation * 1.5, cavity_depth * 0.72)),
            clot_coverage,
            material_roles["CLOT"] if float(recipe.get("goreDarkClotBias", 0.0)) >= 0.45 else material_roles["WET"],
            4101,
        ))
    if bool(recipe.get("goreTissueLayerEnabled", False)) and tissue_coverage > 1e-8:
        plate_specs.append((
            LAYER_TISSUE,
            max(separation * 1.8, cavity_depth * 0.42),
            tissue_coverage,
            material_roles["TISSUE"],
            4201,
        ))
    if bool(recipe.get("goreBarrierLayerEnabled", False)):
        plate_specs.append((
            LAYER_BARRIER,
            max(separation * 2.0, cavity_depth * 0.58),
            min(1.0, 0.38 + breakup * 0.42),
            material_roles["EDGE"],
            4301,
        ))
    if bool(recipe.get("goreBoneLayerEnabled", False)) and bone_reveal > 1e-8:
        plate_specs.append((
            LAYER_BONE,
            max(separation * 2.2, cavity_depth + wall_thickness * 1.35),
            bone_reveal,
            material_roles["BONE"],
            4401,
        ))

    for layer, depth, coverage, material_id, salt in plate_specs:
        eligible = [
            record
            for record in records
            if _unit(seed, int(record["faceIndex"]), salt) <= coverage
        ]
        if not eligible and records:
            eligible = [max(records, key=lambda record: float(record.get("priority", 0.0)))]
        for record in eligible:
            if sum(_triangle_count(face) for face in faces) >= maximum_triangles:
                break
            thickness = max(separation * 0.45, wall_thickness * (0.34 if layer != LAYER_BONE else 0.50))
            inset = 0.24 + 0.36 * breakup
            add_plate(
                record,
                layer=layer,
                depth=depth,
                thickness=thickness,
                inset=inset,
                material_id=material_id,
                salt=salt,
            )

    triangle_count = sum(_triangle_count(face) for face in faces)
    if triangle_count > maximum_triangles:
        raise ValueError(
            f"cavity inlay produced {triangle_count} triangles; recipe budget is {maximum_triangles}"
        )

    layer_depth_values = {}
    for depth, layer in zip(vertex_depths, vertex_layers):
        layer_depth_values.setdefault(LAYER_NAMES[layer], []).append(float(depth))
    layer_depths = {
        layer: {
            "minimum": min(values),
            "median": _median(values),
            "maximum": max(values),
        }
        for layer, values in sorted(layer_depth_values.items())
    }
    liner_depths = layer_depth_values.get("LINER", [])
    metrics = {
        "maximumProudness": 0.0,
        "percentVerticesAboveLimit": 0.0,
        "maximumCavityDepth": max(liner_depths, default=0.0),
        "maximumGeneratedDepth": max(vertex_depths, default=0.0),
        "medianLinerDepth": _median(liner_depths),
        "minimumSkinToLinerSeparation": min(liner_depths, default=0.0),
        "triangleCount": triangle_count,
        "generatedVertexCount": len(vertices),
        "layerDepths": layer_depths,
    }
    return {
        "vertices": vertices,
        "faces": faces,
        "materialIds": material_ids,
        "materialIndices": material_indices,
        "sourceBlends": source_blends,
        "sourceIndices": source_indices,
        "surfacePositions": surface_positions,
        "sourceNormals": source_normals_out,
        "vertexDepths": vertex_depths,
        "faceLayers": face_layers,
        "textureVariants": texture_variants,
        "metrics": metrics,
        "internalFragments": bool(plate_specs),
    }


def edge_use_errors(faces: Sequence[Sequence[int]]) -> list[str]:
    """Return deterministic manifold diagnostics for a generated cavity mesh."""

    edge_counts = {}
    edge_directions = {}
    duplicate_faces = set()
    seen_faces = set()
    for raw_face in faces:
        face = tuple(int(value) for value in raw_face)
        if len(face) < 3 or len(set(face)) != len(face):
            return ["generated cavity contains a degenerate face"]
        key = tuple(sorted(face))
        if key in seen_faces:
            duplicate_faces.add(key)
        seen_faces.add(key)
        for offset, first in enumerate(face):
            second = face[(offset + 1) % len(face)]
            edge = tuple(sorted((first, second)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            edge_directions.setdefault(edge, []).append((first, second))
    errors = []
    if duplicate_faces:
        errors.append(f"generated cavity contains {len(duplicate_faces)} duplicate faces")
    invalid = {edge: count for edge, count in edge_counts.items() if count != 2}
    if invalid:
        errors.append(f"generated cavity contains {len(invalid)} non-manifold edges")
    inconsistent = [
        edge
        for edge, directions in edge_directions.items()
        if len(directions) == 2 and directions[0] == directions[1]
    ]
    if inconsistent:
        errors.append(
            f"generated cavity contains {len(inconsistent)} inconsistently wound edges"
        )
    return errors
