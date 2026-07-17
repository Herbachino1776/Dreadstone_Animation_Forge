"""Dreadstone Animation Forge v3.8 damage-readiness diagnostics.

The analyzer is deliberately non-destructive. It reads source mesh datablocks,
builds shell-aware seam candidates, exports fingerprinted reports, and creates
temporary viewport-only preview helpers. It never edits source geometry, weights,
modifiers, armatures, actions, shape keys, or transforms.
"""

import bpy
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from mathutils import Vector
from bpy.types import Operator

REPORT_SCHEMA = "dreadstone.damage_readiness.v1"
ANALYZER_REVISION = "virtual_weld_v3.7.4"
ANALYZER_BUILD_ID = "2026-07-15.virtual-weld.1"
ADDON_VERSION = (3, 8, 0)
WEIGHT_SUM_TOLERANCE = 0.01
CROSSOVER_WEIGHT_THRESHOLD = 0.15
MIN_COMBINED_SEAM_WEIGHT = 0.20
DEGENERATE_FACE_AREA_EPSILON = 1e-12
PREVIEW_TAG = "dsb_damage_readiness_preview"
PREVIEW_COLLECTION_NAME = "DSB_DAMAGE_READINESS_PREVIEW"

SEAM_DEFINITIONS = {
    "head_neck": {
        "label": "Head–Neck",
        "proximal_role": "neck",
        "distal_role": "head",
        "slab_ratio": 0.18,
    },
    "left_elbow": {
        "label": "Left Elbow",
        "proximal_role": "upper_arm_l",
        "distal_role": "lower_arm_l",
        "slab_ratio": 0.22,
    },
    "right_elbow": {
        "label": "Right Elbow",
        "proximal_role": "upper_arm_r",
        "distal_role": "lower_arm_r",
        "slab_ratio": 0.22,
    },
    "lower_spine": {
        "label": "Lower Spine",
        "proximal_role": "hips",
        "distal_role": "spine",
        "slab_ratio": 0.20,
    },
}

RECOMMENDATION_STATES = {
    "AUTOMATIC_CANDIDATE",
    "MANUAL_REVIEW",
    "MANUAL_REQUIRED",
    "UNAVAILABLE",
}


def _addon_version_string():
    return ".".join(str(value) for value in ADDON_VERSION)


def _utc_timestamp():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "character").strip("._-")
    return cleaned or "character"


def _json_clone(value):
    return json.loads(json.dumps(value))


def _vector_list(vector, precision=8):
    return [round(float(value), precision) for value in vector]


def _capture_context_state(context):
    active = context.view_layer.objects.active
    selected = [obj for obj in context.selected_objects]
    actions = {}
    for obj in context.scene.objects:
        if obj.type == 'ARMATURE' and obj.animation_data:
            actions[obj.name] = obj.animation_data.action
    return {
        "active": active,
        "selected": selected,
        "mode": context.mode,
        "frame": context.scene.frame_current,
        "actions": actions,
    }


def _restore_context_state(context, state):
    context.scene.frame_set(state["frame"])
    for name, action in state["actions"].items():
        obj = bpy.data.objects.get(name)
        if obj and obj.type == 'ARMATURE':
            if obj.animation_data is None and action is not None:
                obj.animation_data_create()
            if obj.animation_data:
                obj.animation_data.action = action
    try:
        bpy.ops.object.select_all(action='DESELECT')
        for obj in state["selected"]:
            if obj and obj.name in context.view_layer.objects:
                obj.select_set(True)
        if state["active"] and state["active"].name in context.view_layer.objects:
            context.view_layer.objects.active = state["active"]
    except (RuntimeError, ReferenceError):
        pass
    if context.mode != state["mode"] and state["mode"] == 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass


def _related_helpers(context):
    from . import character_meshes, detect_animate_anything_profile, find_armature, map_bones
    armature = find_armature(context)
    meshes = character_meshes(context)
    mapping = map_bones(armature, context.scene.daf_settings)
    profile = "animate_anything_testman" if detect_animate_anything_profile(armature) else "generic_humanoid"
    return armature, meshes, mapping, profile


def _edge_key(a, b):
    return (a, b) if a < b else (b, a)



def _virtual_weld_map(mesh):
    """Build a non-destructive positional weld map for imported GLB seams.

    glTF import commonly duplicates otherwise coincident vertices at UV, normal,
    material, or tangent seams. Raw index connectivity therefore makes a single
    visible body appear as dozens of disconnected open shells. Forge never edits
    those vertices; it only treats position-coincident copies as one virtual
    vertex for diagnostic connectivity and contour closure.
    """
    if not mesh.vertices:
        return {
            "tolerance": 1e-7,
            "raw_vertex_to_weld": {},
            "weld_members": {},
            "weld_positions": {},
        }

    min_corner = Vector((1e30, 1e30, 1e30))
    max_corner = Vector((-1e30, -1e30, -1e30))
    for vertex in mesh.vertices:
        co = vertex.co
        min_corner.x = min(min_corner.x, co.x)
        min_corner.y = min(min_corner.y, co.y)
        min_corner.z = min(min_corner.z, co.z)
        max_corner.x = max(max_corner.x, co.x)
        max_corner.y = max(max_corner.y, co.y)
        max_corner.z = max(max_corner.z, co.z)
    diagonal = max((max_corner - min_corner).length, 1.0)
    tolerance = max(1e-7, diagonal * 1e-7)
    inverse = 1.0 / tolerance

    buckets = defaultdict(list)
    seed_positions = []
    weld_members = defaultdict(list)
    raw_vertex_to_weld = {}

    def cell_for(co):
        return (
            int(math.floor(float(co.x) * inverse)),
            int(math.floor(float(co.y) * inverse)),
            int(math.floor(float(co.z) * inverse)),
        )

    for vertex in mesh.vertices:
        co = vertex.co.copy()
        cell = cell_for(co)
        match = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for weld_id in buckets.get((cell[0] + dx, cell[1] + dy, cell[2] + dz), ()): 
                        if (co - seed_positions[weld_id]).length <= tolerance:
                            match = weld_id
                            break
                    if match is not None:
                        break
                if match is not None:
                    break
            if match is not None:
                break
        if match is None:
            match = len(seed_positions)
            seed_positions.append(co)
            buckets[cell].append(match)
        raw_vertex_to_weld[int(vertex.index)] = match
        weld_members[match].append(int(vertex.index))

    weld_positions = {}
    for weld_id, members in weld_members.items():
        point = Vector((0.0, 0.0, 0.0))
        for vertex_index in members:
            point += mesh.vertices[vertex_index].co
        weld_positions[weld_id] = point / max(1, len(members))

    return {
        "tolerance": float(tolerance),
        "raw_vertex_to_weld": raw_vertex_to_weld,
        "weld_members": {key: sorted(value) for key, value in weld_members.items()},
        "weld_positions": weld_positions,
    }


def _source_mesh_topology(mesh):
    edge_indices_by_key = {}
    edge_vertices_by_index = {}
    raw_vertex_neighbors = defaultdict(set)
    for edge in mesh.edges:
        a, b = int(edge.vertices[0]), int(edge.vertices[1])
        key = _edge_key(a, b)
        edge_indices_by_key[key] = int(edge.index)
        edge_vertices_by_index[int(edge.index)] = key
        raw_vertex_neighbors[a].add(b)
        raw_vertex_neighbors[b].add(a)

    raw_edge_face_counts = Counter()
    raw_edge_polygons = defaultdict(list)
    raw_vertex_polygons = defaultdict(set)
    degenerate_faces = []
    polygon_vertices = []
    polygon_material_indices = []
    for polygon in mesh.polygons:
        vertices = [int(index) for index in polygon.vertices]
        polygon_vertices.append(vertices)
        polygon_material_indices.append(int(getattr(polygon, "material_index", 0)))
        for vertex in vertices:
            raw_vertex_polygons[vertex].add(int(polygon.index))
        if len(set(vertices)) < 3 or float(polygon.area) <= DEGENERATE_FACE_AREA_EPSILON:
            degenerate_faces.append(int(polygon.index))
        if len(vertices) >= 2:
            for index, a in enumerate(vertices):
                b = vertices[(index + 1) % len(vertices)]
                key = _edge_key(a, b)
                raw_edge_face_counts[key] += 1
                raw_edge_polygons[key].append(int(polygon.index))

    raw_boundary_edges = []
    raw_non_manifold_edges = []
    raw_loose_edges = []
    raw_non_manifold_vertices = set()
    for edge in mesh.edges:
        a, b = int(edge.vertices[0]), int(edge.vertices[1])
        count = raw_edge_face_counts.get(_edge_key(a, b), 0)
        if count == 1:
            raw_boundary_edges.append(int(edge.index))
        if count != 2:
            raw_non_manifold_edges.append(int(edge.index))
            raw_non_manifold_vertices.update((a, b))
        if count == 0:
            raw_loose_edges.append(int(edge.index))
    loose_vertices = [int(vertex.index) for vertex in mesh.vertices if not raw_vertex_neighbors.get(int(vertex.index))]

    weld = _virtual_weld_map(mesh)
    raw_to_weld = weld["raw_vertex_to_weld"]
    weld_members = weld["weld_members"]
    virtual_vertex_neighbors = defaultdict(set)
    virtual_vertex_polygons = defaultdict(set)
    virtual_edge_face_counts = Counter()
    virtual_edge_polygons = defaultdict(list)
    virtual_edge_raw_edge_indices = defaultdict(set)
    raw_edge_to_virtual_key = {}

    for polygon_index, vertices in enumerate(polygon_vertices):
        weld_vertices = [raw_to_weld[vertex] for vertex in vertices]
        for weld_id in set(weld_vertices):
            virtual_vertex_polygons[weld_id].add(polygon_index)
        polygon_edges = set()
        for index, a in enumerate(weld_vertices):
            b = weld_vertices[(index + 1) % len(weld_vertices)]
            if a == b:
                continue
            key = _edge_key(a, b)
            polygon_edges.add(key)
            virtual_vertex_neighbors[a].add(b)
            virtual_vertex_neighbors[b].add(a)
        for key in polygon_edges:
            virtual_edge_face_counts[key] += 1
            virtual_edge_polygons[key].append(polygon_index)

    for edge in mesh.edges:
        raw_key = _edge_key(int(edge.vertices[0]), int(edge.vertices[1]))
        virtual_key = _edge_key(raw_to_weld[raw_key[0]], raw_to_weld[raw_key[1]])
        raw_edge_to_virtual_key[raw_key] = virtual_key
        if virtual_key[0] != virtual_key[1]:
            virtual_edge_raw_edge_indices[virtual_key].add(int(edge.index))

    virtual_boundary_edge_keys = sorted(key for key, count in virtual_edge_face_counts.items() if count == 1)
    virtual_non_manifold_edge_keys = sorted(key for key, count in virtual_edge_face_counts.items() if count != 2)
    virtual_non_manifold_weld_vertices = {vertex for key in virtual_non_manifold_edge_keys for vertex in key}
    virtual_non_manifold_raw_vertices = {
        raw
        for weld_id in virtual_non_manifold_weld_vertices
        for raw in weld_members.get(weld_id, ())
    }

    def raw_indices_for_virtual_keys(keys):
        return sorted({
            edge_index
            for key in keys
            for edge_index in virtual_edge_raw_edge_indices.get(key, ())
        })

    return {
        "edge_indices_by_key": edge_indices_by_key,
        "edge_vertices_by_index": edge_vertices_by_index,
        "raw_vertex_neighbors": raw_vertex_neighbors,
        "raw_vertex_polygons": raw_vertex_polygons,
        "raw_edge_face_counts": raw_edge_face_counts,
        "raw_edge_polygons": raw_edge_polygons,
        "raw_boundary_edges": raw_boundary_edges,
        "raw_non_manifold_edges": raw_non_manifold_edges,
        "raw_non_manifold_vertices": raw_non_manifold_vertices,
        "raw_loose_edges": raw_loose_edges,
        "loose_vertices": loose_vertices,
        "degenerate_faces": degenerate_faces,
        "polygon_vertices": polygon_vertices,
        "polygon_material_indices": polygon_material_indices,
        "virtual_weld_tolerance": weld["tolerance"],
        "raw_vertex_to_weld": raw_to_weld,
        "weld_members": weld_members,
        "weld_positions": weld["weld_positions"],
        "virtual_vertex_neighbors": virtual_vertex_neighbors,
        "virtual_vertex_polygons": virtual_vertex_polygons,
        "virtual_edge_face_counts": virtual_edge_face_counts,
        "virtual_edge_polygons": virtual_edge_polygons,
        "virtual_edge_raw_edge_indices": virtual_edge_raw_edge_indices,
        "raw_edge_to_virtual_key": raw_edge_to_virtual_key,
        "virtual_boundary_edge_keys": virtual_boundary_edge_keys,
        "virtual_non_manifold_edge_keys": virtual_non_manifold_edge_keys,
        "virtual_non_manifold_weld_vertices": virtual_non_manifold_weld_vertices,
        "virtual_non_manifold_raw_vertices": virtual_non_manifold_raw_vertices,
        "boundary_edges": raw_indices_for_virtual_keys(virtual_boundary_edge_keys),
        "non_manifold_edges": raw_indices_for_virtual_keys(virtual_non_manifold_edge_keys),
        "non_manifold_vertices": virtual_non_manifold_raw_vertices,
        "loose_edges": raw_loose_edges,
    }


def _geometry_shells(obj, topology, group_name_by_index):
    """Return virtual-weld connected shells without editing source geometry."""
    mesh = obj.data
    remaining = set(topology["weld_members"])
    shells = []
    raw_vertex_shell = {}

    while remaining:
        seed = min(remaining)
        queue = deque([seed])
        weld_vertices = set()
        while queue:
            weld_id = queue.popleft()
            if weld_id in weld_vertices:
                continue
            weld_vertices.add(weld_id)
            remaining.discard(weld_id)
            queue.extend(topology["virtual_vertex_neighbors"].get(weld_id, set()) - weld_vertices)

        raw_vertices = {
            vertex_index
            for weld_id in weld_vertices
            for vertex_index in topology["weld_members"].get(weld_id, ())
        }
        for vertex_index in raw_vertices:
            raw_vertex_shell[vertex_index] = len(shells)

        virtual_edge_keys = [
            key for key in topology["virtual_edge_face_counts"]
            if key[0] in weld_vertices and key[1] in weld_vertices
        ]
        boundary_keys = [key for key in virtual_edge_keys if topology["virtual_edge_face_counts"].get(key, 0) == 1]
        non_manifold_keys = [key for key in virtual_edge_keys if topology["virtual_edge_face_counts"].get(key, 0) != 2]
        edge_indices = sorted({
            edge_index
            for key in virtual_edge_keys
            for edge_index in topology["virtual_edge_raw_edge_indices"].get(key, ())
        })
        boundary_edge_indices = sorted({
            edge_index
            for key in boundary_keys
            for edge_index in topology["virtual_edge_raw_edge_indices"].get(key, ())
        })
        non_manifold_edge_indices = sorted({
            edge_index
            for key in non_manifold_keys
            for edge_index in topology["virtual_edge_raw_edge_indices"].get(key, ())
        })
        polygon_indices = sorted({
            polygon_index
            for weld_id in weld_vertices
            for polygon_index in topology["virtual_vertex_polygons"].get(weld_id, ())
        })

        material_indices = {
            topology["polygon_material_indices"][polygon_index]
            for polygon_index in polygon_indices
        }
        min_corner = Vector((1e30, 1e30, 1e30))
        max_corner = Vector((-1e30, -1e30, -1e30))
        dominant_groups = Counter()
        weighted_vertex_count = 0
        for vertex_index in raw_vertices:
            co = mesh.vertices[vertex_index].co
            min_corner.x = min(min_corner.x, co.x)
            min_corner.y = min(min_corner.y, co.y)
            min_corner.z = min(min_corner.z, co.z)
            max_corner.x = max(max_corner.x, co.x)
            max_corner.y = max(max_corner.y, co.y)
            max_corner.z = max(max_corner.z, co.z)
            memberships = [membership for membership in mesh.vertices[vertex_index].groups if membership.weight > 0]
            if memberships:
                weighted_vertex_count += 1
                dominant = max(memberships, key=lambda membership: membership.weight)
                dominant_groups[group_name_by_index.get(dominant.group, f"group_{dominant.group}")] += 1

        dimensions = max_corner - min_corner if raw_vertices else Vector((0.0, 0.0, 0.0))
        shell = {
            "shell_id": len(shells),
            "vertex_indices": sorted(raw_vertices),
            "weld_vertex_indices": sorted(weld_vertices),
            "vertex_count": len(raw_vertices),
            "virtual_vertex_count": len(weld_vertices),
            "welded_duplicate_vertex_count": len(raw_vertices) - len(weld_vertices),
            "edge_indices": edge_indices,
            "edge_count": len(edge_indices),
            "virtual_edge_count": len(virtual_edge_keys),
            "polygon_indices": polygon_indices,
            "polygon_count": len(polygon_indices),
            "boundary_edge_count": len(boundary_keys),
            "boundary_edge_indices": boundary_edge_indices,
            "non_manifold_edge_count": len(non_manifold_keys),
            "non_manifold_edge_indices": non_manifold_edge_indices,
            "closed_shell": bool(virtual_edge_keys) and not boundary_keys and not non_manifold_keys,
            "weighted_vertex_count": weighted_vertex_count,
            "dominant_bone_vertex_counts": dict(dominant_groups.most_common()),
            "material_indices": sorted(material_indices),
            "bounds_min": _vector_list(min_corner),
            "bounds_max": _vector_list(max_corner),
            "dimensions": _vector_list(dimensions),
        }
        shells.append(shell)

    shells.sort(key=lambda shell: (-shell["vertex_count"], shell["shell_id"]))
    remap = {}
    for new_id, shell in enumerate(shells):
        old_id = shell["shell_id"]
        remap[old_id] = new_id
        shell["shell_id"] = new_id
    raw_vertex_shell = {vertex: remap[shell_id] for vertex, shell_id in raw_vertex_shell.items()}
    return shells, raw_vertex_shell

def _armature_modifiers(obj):
    result = []
    for modifier in obj.modifiers:
        if modifier.type == 'ARMATURE':
            result.append({
                "name": modifier.name,
                "target": modifier.object.name if modifier.object else None,
                "use_vertex_groups": bool(getattr(modifier, "use_vertex_groups", True)),
                "use_bone_envelopes": bool(getattr(modifier, "use_bone_envelopes", False)),
            })
    return result


def _mesh_fingerprints(obj, topology, relevant_groups=None):
    mesh = obj.data
    topology_hash = hashlib.sha256()
    topology_hash.update(f"{obj.name}|{mesh.name}|{len(mesh.vertices)}|{len(mesh.edges)}|{len(mesh.polygons)}\n".encode("utf-8"))
    for vertex in mesh.vertices:
        topology_hash.update(("v:%d:%.8f,%.8f,%.8f\n" % (
            vertex.index, vertex.co.x, vertex.co.y, vertex.co.z,
        )).encode("utf-8"))
    for edge in mesh.edges:
        topology_hash.update(f"e:{edge.index}:{int(edge.vertices[0])},{int(edge.vertices[1])}\n".encode("utf-8"))
    for polygon_index, vertices in enumerate(topology["polygon_vertices"]):
        topology_hash.update(f"p:{polygon_index}:{','.join(str(value) for value in vertices)}\n".encode("utf-8"))

    weight_hash = hashlib.sha256()
    group_names = [group.name for group in obj.vertex_groups]
    relevant = set(relevant_groups or group_names)
    group_name_by_index = {group.index: group.name for group in obj.vertex_groups}
    weight_hash.update(("groups:" + "|".join(group_names) + "\n").encode("utf-8"))
    for vertex in mesh.vertices:
        entries = []
        for membership in vertex.groups:
            name = group_name_by_index.get(membership.group)
            if name in relevant and membership.weight > 0:
                entries.append((name, round(float(membership.weight), 8)))
        entries.sort()
        if entries:
            weight_hash.update(f"v:{vertex.index}:{entries}\n".encode("utf-8"))

    return {
        "topology_sha256": topology_hash.hexdigest(),
        "vertex_group_sha256": weight_hash.hexdigest(),
    }


def _mesh_weight_statistics(obj):
    mesh = obj.data
    group_name_by_index = {group.index: group.name for group in obj.vertex_groups}
    dominant_counts = Counter()
    unweighted = []
    more_than_four = []
    weight_sum_deviation = []
    maximum_influence_count = 0

    for vertex in mesh.vertices:
        influences = []
        for membership in vertex.groups:
            if membership.weight > 0:
                name = group_name_by_index.get(membership.group, f"group_{membership.group}")
                influences.append((name, float(membership.weight)))
        count = len(influences)
        maximum_influence_count = max(maximum_influence_count, count)
        if not influences:
            unweighted.append(int(vertex.index))
            continue
        if count > 4:
            more_than_four.append(int(vertex.index))
        total = sum(weight for _name, weight in influences)
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            weight_sum_deviation.append(int(vertex.index))
        dominant_counts[max(influences, key=lambda item: item[1])[0]] += 1

    return {
        "unweighted_vertex_count": len(unweighted),
        "unweighted_vertex_indices": unweighted,
        "vertices_over_four_influences_count": len(more_than_four),
        "vertices_over_four_influences": more_than_four,
        "maximum_influence_count": maximum_influence_count,
        "weight_sum_tolerance": WEIGHT_SUM_TOLERANCE,
        "weight_sum_deviation_count": len(weight_sum_deviation),
        "weight_sum_deviation_vertices": weight_sum_deviation,
        "dominant_bone_vertex_counts": dict(sorted(dominant_counts.items())),
    }



def analyze_mesh_object(obj, relevant_groups=None):
    if obj.type != 'MESH':
        raise TypeError("Damage readiness can only analyze mesh objects.")
    if obj.mode == 'EDIT':
        obj.update_from_editmode()
    mesh = obj.data
    topology = _source_mesh_topology(mesh)
    group_name_by_index = {group.index: group.name for group in obj.vertex_groups}
    shells, vertex_shell = _geometry_shells(obj, topology, group_name_by_index)
    topology["shells"] = shells
    topology["vertex_shell"] = vertex_shell
    armature_modifiers = _armature_modifiers(obj)
    shape_keys = [block.name for block in mesh.shape_keys.key_blocks] if mesh.shape_keys else []
    material_slots = [
        {"slot": index, "name": slot.material.name if slot.material else None}
        for index, slot in enumerate(obj.material_slots)
    ]
    weight_stats = _mesh_weight_statistics(obj)
    fingerprints = _mesh_fingerprints(obj, topology, relevant_groups)
    custom_normals = bool(getattr(mesh, "has_custom_normals", False))

    largest_shell = shells[0] if shells else None
    welded_vertex_count = len(topology["weld_members"])
    result = {
        "object_name": obj.name,
        "mesh_datablock_name": mesh.name,
        "vertex_count": len(mesh.vertices),
        "welded_virtual_vertex_count": welded_vertex_count,
        "welded_duplicate_vertex_count": len(mesh.vertices) - welded_vertex_count,
        "virtual_weld_tolerance": topology["virtual_weld_tolerance"],
        "edge_count": len(mesh.edges),
        "polygon_count": len(mesh.polygons),
        "material_slots": material_slots,
        "material_names": [entry["name"] for entry in material_slots if entry["name"]],
        "shape_key_names": shape_keys,
        "armature_modifiers": armature_modifiers,
        "skinned_mesh_equivalent": bool(armature_modifiers),
        "vertex_group_count": len(obj.vertex_groups),
        "vertex_group_names": [group.name for group in obj.vertex_groups],
        **weight_stats,
        "shell_count": len(shells),
        "largest_shell_vertex_count": largest_shell["vertex_count"] if largest_shell else 0,
        "largest_shell_fraction": (largest_shell["vertex_count"] / len(mesh.vertices)) if largest_shell and mesh.vertices else 0.0,
        "shell_reports": shells,
        "boundary_edge_count": len(topology["virtual_boundary_edge_keys"]),
        "boundary_edge_indices": topology["boundary_edges"],
        "non_manifold_edge_count": len(topology["virtual_non_manifold_edge_keys"]),
        "non_manifold_edge_indices": topology["non_manifold_edges"],
        "raw_boundary_edge_count": len(topology["raw_boundary_edges"]),
        "raw_boundary_edge_indices": topology["raw_boundary_edges"],
        "raw_non_manifold_edge_count": len(topology["raw_non_manifold_edges"]),
        "raw_non_manifold_edge_indices": topology["raw_non_manifold_edges"],
        "loose_edge_count": len(topology["loose_edges"]),
        "loose_edge_indices": topology["loose_edges"],
        "loose_vertex_count": len(topology["loose_vertices"]),
        "loose_vertex_indices": topology["loose_vertices"],
        "degenerate_face_count": len(topology["degenerate_faces"]),
        "degenerate_face_indices": topology["degenerate_faces"],
        "custom_normals": {
            "has_custom_normals": custom_normals,
            "auto_smooth": bool(getattr(mesh, "use_auto_smooth", False)),
        },
        "fingerprints": fingerprints,
    }
    return result, topology

def _weights_for_groups(obj, proximal_group_name, distal_group_name):
    proximal_group = obj.vertex_groups.get(proximal_group_name)
    distal_group = obj.vertex_groups.get(distal_group_name)
    if not proximal_group or not distal_group:
        return None
    proximal_index = proximal_group.index
    distal_index = distal_group.index
    weights = {}
    for vertex in obj.data.vertices:
        proximal = 0.0
        distal = 0.0
        for membership in vertex.groups:
            if membership.group == proximal_index:
                proximal = float(membership.weight)
            elif membership.group == distal_index:
                distal = float(membership.weight)
        weights[int(vertex.index)] = (proximal, distal)
    return weights




def _weights_for_weld_vertices(raw_weights, topology):
    result = {}
    for weld_id, members in topology["weld_members"].items():
        if not members:
            result[weld_id] = (0.0, 0.0)
            continue
        proximal = sum(raw_weights.get(vertex, (0.0, 0.0))[0] for vertex in members) / len(members)
        distal = sum(raw_weights.get(vertex, (0.0, 0.0))[1] for vertex in members) / len(members)
        result[weld_id] = (float(proximal), float(distal))
    return result
def _bone_joint_plane(armature, proximal_bone_name, distal_bone_name, obj):
    proximal = armature.data.bones.get(proximal_bone_name)
    distal = armature.data.bones.get(distal_bone_name)
    if not proximal or not distal:
        return None

    proximal_points = [proximal.head_local.copy(), proximal.tail_local.copy()]
    distal_points = [distal.head_local.copy(), distal.tail_local.copy()]
    pair = min(
        ((a, b) for a in proximal_points for b in distal_points),
        key=lambda item: (item[0] - item[1]).length_squared,
    )
    center_armature = (pair[0] + pair[1]) * 0.5
    axis_armature = distal.head_local - proximal.head_local
    if axis_armature.length_squared <= 1e-12:
        axis_armature = distal.tail_local - proximal.tail_local
    if axis_armature.length_squared <= 1e-12:
        axis_armature = pair[1] - pair[0]
    if axis_armature.length_squared <= 1e-12:
        axis_armature = Vector((0.0, 0.0, 1.0))
    axis_armature.normalize()

    center_world = armature.matrix_world @ center_armature
    axis_world = (armature.matrix_world.to_3x3() @ axis_armature).normalized()
    center_object = obj.matrix_world.inverted() @ center_world
    axis_object = (obj.matrix_world.inverted().to_3x3() @ axis_world).normalized()
    return {
        "center_object": center_object,
        "normal_object": axis_object,
        "center_world": center_world,
        "normal_world": axis_world,
    }


def _shell_relevance(shell, weights):
    meaningful = 0
    combined_sum = 0.0
    both_sum = 0.0
    for vertex_index in shell["vertex_indices"]:
        proximal, distal = weights.get(vertex_index, (0.0, 0.0))
        combined = proximal + distal
        if combined >= MIN_COMBINED_SEAM_WEIGHT:
            meaningful += 1
            combined_sum += combined
            both_sum += min(proximal, distal)
    vertex_count = max(1, shell["vertex_count"])
    return {
        "meaningful_vertex_count": meaningful,
        "meaningful_fraction": meaningful / vertex_count,
        "combined_weight_sum": combined_sum,
        "shared_weight_sum": both_sum,
    }


def _candidate_slab_width(obj, shell, plane, definition):
    dimensions = Vector(shell.get("dimensions", (0.0, 0.0, 0.0)))
    shell_scale = max(dimensions.length, 0.05)
    normal = plane["normal_object"]
    projected_extent = (
        abs(normal.x) * dimensions.x
        + abs(normal.y) * dimensions.y
        + abs(normal.z) * dimensions.z
    )
    base = max(projected_extent, shell_scale * 0.2)
    return max(0.015, min(base * float(definition.get("slab_ratio", 0.2)), shell_scale * 0.28))



def _edge_crossing_node(topology, edge_key, weights, plane, slab_width):
    a, b = edge_key
    pa, da = weights[a]
    pb, db = weights[b]
    balance_a = pa - da
    balance_b = pb - db
    combined_a = pa + da
    combined_b = pb + db
    if max(combined_a, combined_b) < MIN_COMBINED_SEAM_WEIGHT:
        return None
    if balance_a == 0.0 and balance_b == 0.0:
        t = 0.5
    elif balance_a * balance_b > 0.0:
        return None
    else:
        denominator = abs(balance_a) + abs(balance_b)
        t = abs(balance_a) / denominator if denominator > 1e-12 else 0.5
    co_a = topology["weld_positions"][a]
    co_b = topology["weld_positions"][b]
    point = co_a.lerp(co_b, t)
    plane_distance = abs((point - plane["center_object"]).dot(plane["normal_object"]))
    if plane_distance > slab_width:
        return None
    combined = combined_a * (1.0 - t) + combined_b * t
    if combined < MIN_COMBINED_SEAM_WEIGHT:
        return None
    return {
        "edge_key": edge_key,
        "source_edge_indices": sorted(topology["virtual_edge_raw_edge_indices"].get(edge_key, ())),
        "point_object": point,
        "t": t,
        "plane_distance": plane_distance,
        "combined_weight": combined,
        "balance_abs": abs(balance_a * (1.0 - t) + balance_b * t),
    }


def _contour_components(obj, shell, topology, weights, plane, slab_width):
    shell_weld_vertices = set(shell["weld_vertex_indices"])
    nodes = {}
    segments = []
    ambiguous_polygons = []

    for polygon_index in shell["polygon_indices"]:
        raw_vertices = topology["polygon_vertices"][polygon_index]
        weld_vertices = [topology["raw_vertex_to_weld"][vertex] for vertex in raw_vertices]
        crossing_keys = []
        for index, a in enumerate(weld_vertices):
            b = weld_vertices[(index + 1) % len(weld_vertices)]
            if a == b or a not in shell_weld_vertices or b not in shell_weld_vertices:
                continue
            key = _edge_key(a, b)
            node = nodes.get(key)
            if node is None:
                node = _edge_crossing_node(topology, key, weights, plane, slab_width)
                if node is not None:
                    nodes[key] = node
            if node is not None:
                crossing_keys.append(key)

        unique = []
        seen = set()
        for key in crossing_keys:
            if key not in seen:
                seen.add(key)
                unique.append(key)
        if len(unique) == 2:
            segments.append((unique[0], unique[1], polygon_index))
        elif len(unique) > 2:
            ambiguous_polygons.append(int(polygon_index))
            remaining = set(unique)
            while len(remaining) >= 2:
                first = min(remaining)
                remaining.remove(first)
                second = min(
                    remaining,
                    key=lambda key: (nodes[first]["point_object"] - nodes[key]["point_object"]).length_squared,
                )
                remaining.remove(second)
                segments.append((first, second, polygon_index))

    adjacency = defaultdict(set)
    for a, b, _polygon_index in segments:
        adjacency[a].add(b)
        adjacency[b].add(a)

    components = []
    remaining = set(adjacency)
    while remaining:
        seed = min(remaining)
        queue = deque([seed])
        component_nodes = set()
        while queue:
            node_key = queue.popleft()
            if node_key in component_nodes:
                continue
            component_nodes.add(node_key)
            remaining.discard(node_key)
            queue.extend(adjacency[node_key] - component_nodes)

        component_segments = []
        polygon_indices = set()
        for a, b, polygon_index in segments:
            if a in component_nodes and b in component_nodes:
                component_segments.append((a, b))
                polygon_indices.add(polygon_index)
        degrees = {key: len(adjacency[key]) for key in component_nodes}
        source_edge_indices = sorted({
            edge_index
            for key in component_nodes
            for edge_index in nodes[key].get("source_edge_indices", ())
        })
        weld_vertex_ids = sorted({vertex for key in component_nodes for vertex in key})
        source_vertices = sorted({
            raw_vertex
            for weld_id in weld_vertex_ids
            for raw_vertex in topology["weld_members"].get(weld_id, ())
        })
        points = [nodes[key]["point_object"] for key in component_nodes]
        length = sum((nodes[a]["point_object"] - nodes[b]["point_object"]).length for a, b in component_segments)
        mean_plane_distance = (
            sum(nodes[key]["plane_distance"] for key in component_nodes) / len(component_nodes)
            if component_nodes else 0.0
        )
        mean_combined_weight = (
            sum(nodes[key]["combined_weight"] for key in component_nodes) / len(component_nodes)
            if component_nodes else 0.0
        )
        components.append({
            "component_id": len(components),
            "node_edge_keys": [list(key) for key in sorted(component_nodes)],
            "weld_vertex_ids": weld_vertex_ids,
            "source_edge_indices": source_edge_indices,
            "source_vertex_indices": source_vertices,
            "polygon_indices": sorted(polygon_indices),
            "node_count": len(component_nodes),
            "segment_count": len(component_segments),
            "closed": bool(component_nodes) and all(degree == 2 for degree in degrees.values()),
            "open_endpoint_edge_keys": [list(key) for key, degree in sorted(degrees.items()) if degree == 1],
            "branch_edge_keys": [list(key) for key, degree in sorted(degrees.items()) if degree > 2],
            "length_object": float(length),
            "mean_plane_distance": float(mean_plane_distance),
            "mean_combined_weight": float(mean_combined_weight),
            "centroid_object": _vector_list(sum(points, Vector((0.0, 0.0, 0.0))) / len(points)) if points else [0.0, 0.0, 0.0],
        })

    return nodes, components, ambiguous_polygons


def _component_local_defects(component, shell, topology):
    weld_vertices = set(component.get("weld_vertex_ids", ()))
    neighborhood = set(weld_vertices)
    for weld_id in list(weld_vertices):
        neighborhood.update(topology["virtual_vertex_neighbors"].get(weld_id, set()))
    shell_weld_vertices = set(shell["weld_vertex_indices"])
    neighborhood.intersection_update(shell_weld_vertices)
    non_manifold_welds = sorted(neighborhood.intersection(topology["virtual_non_manifold_weld_vertices"]))
    non_manifold_raw = sorted({
        raw_vertex
        for weld_id in non_manifold_welds
        for raw_vertex in topology["weld_members"].get(weld_id, ())
    })
    degenerate_faces = []
    for polygon_index in topology["degenerate_faces"]:
        polygon_welds = {
            topology["raw_vertex_to_weld"][raw_vertex]
            for raw_vertex in topology["polygon_vertices"][polygon_index]
        }
        if polygon_welds.intersection(neighborhood):
            degenerate_faces.append(int(polygon_index))
    return non_manifold_raw, degenerate_faces

def _score_component(component, shell, slab_width, ambiguous_polygon_count):
    score = 0.0
    if component["closed"]:
        score += 0.42
    if not component["open_endpoint_edge_keys"]:
        score += 0.10
    if not component["branch_edge_keys"]:
        score += 0.10
    plane_score = 1.0 - min(1.0, component["mean_plane_distance"] / max(slab_width, 1e-9))
    score += plane_score * 0.18
    score += min(1.0, component["mean_combined_weight"]) * 0.10
    shell_diagonal = max(Vector(shell["dimensions"]).length, 1e-6)
    normalized_length = component["length_object"] / shell_diagonal
    if 0.08 <= normalized_length <= 2.0:
        score += 0.10
    elif normalized_length < 0.03:
        score -= 0.10
    if ambiguous_polygon_count:
        score -= min(0.12, ambiguous_polygon_count * 0.015)
    return max(0.0, min(1.0, score))


def analyze_seam_on_mesh(obj, seam_id, definition, armature, proximal_group_name, distal_group_name, mesh_report, topology):
    raw_weights = _weights_for_groups(obj, proximal_group_name, distal_group_name)
    if raw_weights is None:
        missing = []
        if obj.vertex_groups.get(proximal_group_name) is None:
            missing.append(proximal_group_name)
        if obj.vertex_groups.get(distal_group_name) is None:
            missing.append(distal_group_name)
        return {
            "mesh_object_name": obj.name,
            "available": False,
            "missing_vertex_groups": missing,
            "candidate_boundary_edge_count": 0,
        }

    plane = _bone_joint_plane(armature, proximal_group_name, distal_group_name, obj)
    if plane is None:
        return {
            "mesh_object_name": obj.name,
            "available": False,
            "missing_vertex_groups": [],
            "candidate_boundary_edge_count": 0,
            "analysis_error": "Could not derive the seam joint plane.",
        }

    shell_candidates = []
    for shell in topology["shells"]:
        relevance = _shell_relevance(shell, raw_weights)
        if relevance["meaningful_vertex_count"] < 3:
            continue
        slab_width = _candidate_slab_width(obj, shell, plane, definition)
        nodes, components, ambiguous_polygons = _contour_components(
            obj, shell, topology, _weights_for_weld_vertices(raw_weights, topology), plane, slab_width,
        )
        for component in components:
            nearby_non_manifold, nearby_degenerate = _component_local_defects(component, shell, topology)
            component["nearby_non_manifold_vertex_indices"] = nearby_non_manifold
            component["nearby_degenerate_face_indices"] = nearby_degenerate
            component["score"] = _score_component(component, shell, slab_width, len(ambiguous_polygons))
        components.sort(key=lambda component: (-component["score"], -int(component["closed"]), -component["segment_count"], component["component_id"]))
        for index, component in enumerate(components):
            component["rank"] = index + 1
        shell_candidates.append({
            "shell_id": shell["shell_id"],
            "shell_vertex_count": shell["vertex_count"],
            "shell_polygon_count": shell["polygon_count"],
            "shell_closed": shell["closed_shell"],
            "shell_boundary_edge_count": shell["boundary_edge_count"],
            "shell_non_manifold_edge_count": shell["non_manifold_edge_count"],
            "relevance": relevance,
            "slab_width_object": float(slab_width),
            "ambiguous_polygon_indices": sorted(ambiguous_polygons),
            "components": components,
        })

    all_ranked = []
    for shell_candidate in shell_candidates:
        for component in shell_candidate["components"]:
            all_ranked.append((component["score"], shell_candidate, component))
    all_ranked.sort(key=lambda item: (-item[0], -int(item[2]["closed"]), -item[2]["segment_count"]))
    selected_shell = all_ranked[0][1] if all_ranked else None
    selected = all_ranked[0][2] if all_ranked else None

    proximal_dominant = set()
    distal_dominant = set()
    crossover = set()
    for vertex_index, (proximal, distal) in raw_weights.items():
        if proximal > distal:
            proximal_dominant.add(vertex_index)
        elif distal > proximal:
            distal_dominant.add(vertex_index)
        if proximal >= CROSSOVER_WEIGHT_THRESHOLD and distal >= CROSSOVER_WEIGHT_THRESHOLD:
            crossover.add(vertex_index)

    rejected = []
    for score, shell_candidate, component in all_ranked[1:6]:
        rejected.append({
            "shell_id": shell_candidate["shell_id"],
            "component_id": component["component_id"],
            "score": score,
            "closed": component["closed"],
            "source_edge_indices": component["source_edge_indices"],
            "source_vertex_indices": component["source_vertex_indices"],
            "open_endpoint_edge_keys": component["open_endpoint_edge_keys"],
            "branch_edge_keys": component["branch_edge_keys"],
        })

    selected_edges = selected["source_edge_indices"] if selected else []
    selected_vertices = selected["source_vertex_indices"] if selected else []
    def representative_raw_vertices(node_keys):
        representatives = []
        for key in node_keys:
            raw_edges = sorted(topology["virtual_edge_raw_edge_indices"].get(tuple(key), ()))
            if raw_edges:
                raw_key = topology["edge_vertices_by_index"].get(raw_edges[0])
                if raw_key:
                    representatives.append(raw_key[0])
                    continue
            weld_id = key[0] if key else None
            members = topology["weld_members"].get(weld_id, ()) if weld_id is not None else ()
            if members:
                representatives.append(members[0])
        return sorted(set(representatives))

    endpoint_node_keys = selected["open_endpoint_edge_keys"] if selected else []
    branch_node_keys = selected["branch_edge_keys"] if selected else []
    open_endpoint_vertices = representative_raw_vertices(endpoint_node_keys)
    branch_vertices = representative_raw_vertices(branch_node_keys)
    nearby_non_manifold = selected.get("nearby_non_manifold_vertex_indices", []) if selected else []
    nearby_degenerate = selected.get("nearby_degenerate_face_indices", []) if selected else []

    return {
        "mesh_object_name": obj.name,
        "mesh_datablock_name": obj.data.name,
        "available": True,
        "proximal_dominant_vertex_count": len(proximal_dominant),
        "distal_dominant_vertex_count": len(distal_dominant),
        "crossover_vertex_count": len(crossover),
        "crossover_vertex_indices": sorted(crossover),
        "joint_plane": {
            "center_object": _vector_list(plane["center_object"]),
            "normal_object": _vector_list(plane["normal_object"]),
            "center_world": _vector_list(plane["center_world"]),
            "normal_world": _vector_list(plane["normal_world"]),
        },
        "shell_candidate_count": len(shell_candidates),
        "selected_shell_id": selected_shell["shell_id"] if selected_shell else None,
        "selected_component_id": selected["component_id"] if selected else None,
        "selected_component_score": selected["score"] if selected else 0.0,
        "candidate_boundary_vertex_count": len(selected_vertices),
        "candidate_boundary_edge_count": len(selected_edges),
        "candidate_boundary_vertex_indices": selected_vertices,
        "candidate_boundary_edge_indices": selected_edges,
        "connected_component_count": len(all_ranked),
        "closed_component_count": sum(1 for _score, _shell, component in all_ranked if component["closed"]),
        "open_endpoint_count": len(endpoint_node_keys),
        "branch_vertex_count": len(branch_node_keys),
        "open_endpoint_vertex_indices": open_endpoint_vertices,
        "branch_vertex_indices": branch_vertices,
        "non_manifold_vertices_within_one_edge_step_count": len(nearby_non_manifold),
        "degenerate_faces_within_one_edge_step_count": len(nearby_degenerate),
        "nearby_non_manifold_vertex_indices": nearby_non_manifold,
        "nearby_degenerate_face_indices": nearby_degenerate,
        "selected_component": _json_clone(selected) if selected else None,
        "rejected_components": rejected,
        "shell_candidates": shell_candidates,
        "mesh_fingerprints": _json_clone(mesh_report["fingerprints"]),
    }


def _recommend_seam(selected):
    if not selected or not selected.get("available"):
        missing = selected.get("missing_vertex_groups", []) if selected else []
        reason = "Required mesh, joint plane, or vertex groups are unavailable."
        if missing:
            reason = "Missing vertex groups: " + ", ".join(missing)
        if selected and selected.get("analysis_error"):
            reason = selected["analysis_error"]
        return "UNAVAILABLE", [reason]
    if selected.get("candidate_boundary_edge_count", 0) == 0:
        return "MANUAL_REQUIRED", ["No usable shell-aware weight contour exists inside the joint-plane slab."]

    component = selected.get("selected_component") or {}
    failures = []
    if not component.get("closed"):
        failures.append("The best shell-aware contour is open rather than one closed loop.")
    if selected.get("open_endpoint_count", 0):
        failures.append(f"Found {selected['open_endpoint_count']} open contour endpoints on the selected shell.")
    if selected.get("branch_vertex_count", 0):
        failures.append(f"Found {selected['branch_vertex_count']} branch vertices on the selected contour.")
    if selected.get("non_manifold_vertices_within_one_edge_step_count", 0):
        failures.append(
            f"Found {selected['non_manifold_vertices_within_one_edge_step_count']} same-shell non-manifold vertices beside the selected contour."
        )
    if selected.get("degenerate_faces_within_one_edge_step_count", 0):
        failures.append(
            f"Found {selected['degenerate_faces_within_one_edge_step_count']} same-shell degenerate faces beside the selected contour."
        )
    if selected.get("selected_component_score", 0.0) < 0.62:
        failures.append(f"Best contour confidence is {selected.get('selected_component_score', 0.0):.2f}; required automatic threshold is 0.62.")
    if not failures:
        return "AUTOMATIC_CANDIDATE", [
            "One high-confidence closed contour passed joint-plane, shell, weight, and local-topology checks."
        ]
    return "MANUAL_REVIEW", failures


def analyze_seam(seam_id, definition, armature, mapping, mesh_objects, mesh_reports_by_name, topology_by_name):
    proximal_bone = mapping.get(definition["proximal_role"])
    distal_bone = mapping.get(definition["distal_role"])
    base = {
        "id": seam_id,
        "label": definition["label"],
        "proximal_role": definition["proximal_role"],
        "distal_role": definition["distal_role"],
        "proximal_bone": proximal_bone,
        "distal_bone": distal_bone,
        "crossover_weight_threshold": CROSSOVER_WEIGHT_THRESHOLD,
        "minimum_combined_seam_weight": MIN_COMBINED_SEAM_WEIGHT,
    }
    missing_bones = []
    if not proximal_bone or armature.data.bones.get(proximal_bone) is None:
        missing_bones.append(definition["proximal_role"])
    if not distal_bone or armature.data.bones.get(distal_bone) is None:
        missing_bones.append(definition["distal_role"])
    if missing_bones:
        return {
            **base,
            "recommendation": "UNAVAILABLE",
            "reasons": ["Missing required mapped bones: " + ", ".join(missing_bones)],
            "mesh_candidates": [],
            "selected_mesh_object_name": None,
        }

    candidates = []
    for obj in mesh_objects:
        result = analyze_seam_on_mesh(
            obj,
            seam_id,
            definition,
            armature,
            proximal_bone,
            distal_bone,
            mesh_reports_by_name[obj.name],
            topology_by_name[obj.name],
        )
        candidates.append(result)

    available_candidates = [candidate for candidate in candidates if candidate.get("available")]
    selected = None
    if available_candidates:
        selected = max(
            available_candidates,
            key=lambda candidate: (
                candidate.get("selected_component_score", 0.0),
                int(bool((candidate.get("selected_component") or {}).get("closed"))),
                candidate.get("candidate_boundary_edge_count", 0),
            ),
        )
    elif candidates:
        selected = candidates[0]

    recommendation, reasons = _recommend_seam(selected)
    selected_payload = _json_clone(selected) if selected else {}
    return {
        **base,
        **selected_payload,
        "recommendation": recommendation,
        "reasons": reasons,
        "selected_mesh_object_name": selected.get("mesh_object_name") if selected else None,
        "mesh_candidates": candidates,
    }


def _overall_summary(mesh_reports, seam_reports):
    skinned = [report for report in mesh_reports if report["skinned_mesh_equivalent"]]
    usable_skinning = bool(skinned) and any(report["vertex_count"] > report["unweighted_vertex_count"] for report in skinned)
    weight_cleanup = any(
        report["unweighted_vertex_count"]
        or report["vertices_over_four_influences_count"]
        or report["weight_sum_deviation_count"]
        for report in mesh_reports
    )
    seam_local_topology_repairs = [
        report["id"] for report in seam_reports
        if report.get("non_manifold_vertices_within_one_edge_step_count", 0)
        or report.get("degenerate_faces_within_one_edge_step_count", 0)
    ]
    global_hard_topology_errors = any(
        report["loose_edge_count"]
        or report["loose_vertex_count"]
        or report["degenerate_face_count"]
        for report in mesh_reports
    )
    topology_repair = bool(seam_local_topology_repairs) or global_hard_topology_errors
    open_shell_review = any(report.get("shell_count", 0) > 1 or report.get("boundary_edge_count", 0) for report in mesh_reports)
    shape_keys_exist = any(report["shape_key_names"] for report in mesh_reports)
    automatic = [report["id"] for report in seam_reports if report["recommendation"] == "AUTOMATIC_CANDIDATE"]
    manual_review = [report["id"] for report in seam_reports if report["recommendation"] == "MANUAL_REVIEW"]
    manual_required = [report["id"] for report in seam_reports if report["recommendation"] == "MANUAL_REQUIRED"]
    unavailable = [report["id"] for report in seam_reports if report["recommendation"] == "UNAVAILABLE"]
    ready = usable_skinning and not weight_cleanup and not topology_repair and len(automatic) == len(SEAM_DEFINITIONS)
    if unavailable or manual_required:
        readiness_statement = "Not ready for v3.8: required seam data or a usable joint contour is missing."
    elif manual_review:
        readiness_statement = "Not yet ready for automatic v3.8 authoring: localized seam review is required."
    elif ready:
        readiness_statement = "Ready for v3.8 segment and stump authoring."
    else:
        readiness_statement = "Seams are viable, but localized mesh or weight cleanup remains."
    return {
        "usable_skinning": usable_skinning,
        "weight_cleanup_required": weight_cleanup,
        "topology_repair_required": topology_repair,
        "topology_repair_basis": "selected_seam_local_defects_or_hard_mesh_errors",
        "open_shell_review_required": open_shell_review,
        "automatic_seam_extraction_unresolved": bool(manual_review or manual_required or unavailable),
        "shape_keys_exist": shape_keys_exist,
        "automatic_candidate_seams": automatic,
        "manual_review_seams": manual_review,
        "manual_required_seams": manual_required,
        "unavailable_seams": unavailable,
        "seams_with_confirmed_local_topology_defects": seam_local_topology_repairs,
        "ready_for_v3_8_segment_authoring": ready,
        "readiness_statement": readiness_statement,
    }


def build_damage_readiness_report(context):
    armature, meshes, mapping, profile = _related_helpers(context)
    relevant_groups = [name for name in mapping.values() if name]
    mesh_reports = []
    mesh_reports_by_name = {}
    topology_by_name = {}
    warnings = []
    errors = []

    for obj in sorted(meshes, key=lambda item: item.name.lower()):
        try:
            report, topology = analyze_mesh_object(obj, relevant_groups)
            mesh_reports.append(report)
            mesh_reports_by_name[obj.name] = report
            topology_by_name[obj.name] = topology
        except Exception as exc:
            errors.append(f"Mesh {obj.name}: {exc}")

    seam_reports = []
    if not errors or mesh_reports:
        for seam_id, definition in SEAM_DEFINITIONS.items():
            try:
                seam_reports.append(analyze_seam(
                    seam_id,
                    definition,
                    armature,
                    mapping,
                    [obj for obj in meshes if obj.name in mesh_reports_by_name],
                    mesh_reports_by_name,
                    topology_by_name,
                ))
            except Exception as exc:
                seam_reports.append({
                    "id": seam_id,
                    "label": definition["label"],
                    "recommendation": "UNAVAILABLE",
                    "reasons": [f"Analysis error: {exc}"],
                    "selected_mesh_object_name": None,
                    "mesh_candidates": [],
                })
                errors.append(f"Seam {seam_id}: {exc}")

    for report in mesh_reports:
        if report["unweighted_vertex_count"]:
            warnings.append(f"{report['object_name']}: {report['unweighted_vertex_count']} unweighted vertices.")
        if report["vertices_over_four_influences_count"]:
            warnings.append(f"{report['object_name']}: {report['vertices_over_four_influences_count']} vertices exceed four influences.")
        if report["shell_count"] > 1:
            warnings.append(f"{report['object_name']}: {report['shell_count']} weld-aware geometry shells after collapsing coincident GLB seam vertices.")
        if report["boundary_edge_count"]:
            warnings.append(
                f"{report['object_name']}: {report['boundary_edge_count']} weld-aware boundary edges remain after collapsing coincident GLB seam vertices."
            )
        if report["degenerate_face_count"]:
            warnings.append(f"{report['object_name']}: {report['degenerate_face_count']} degenerate faces.")

    summary = _overall_summary(mesh_reports, seam_reports)
    source_path = bpy.data.filepath or ""
    return {
        "schema": REPORT_SCHEMA,
        "analyzer_revision": ANALYZER_REVISION,
        "analyzer_build_id": ANALYZER_BUILD_ID,
        "analyzer_module_path": os.path.abspath(__file__),
        "addon_package_path": os.path.abspath(os.path.dirname(__file__)),
        "generated_at_utc": _utc_timestamp(),
        "blender_version": bpy.app.version_string,
        "addon_version": _addon_version_string(),
        "source_blend_path": source_path,
        "armature_name": armature.name,
        "detected_rig_profile": profile,
        "semantic_bone_mapping": dict(sorted(mapping.items())),
        "analyzed_object_names": [report["object_name"] for report in mesh_reports],
        "mesh_count": len(mesh_reports),
        "skinned_mesh_equivalent_count": sum(1 for report in mesh_reports if report["skinned_mesh_equivalent"]),
        "mesh_reports": mesh_reports,
        "seam_reports": seam_reports,
        "overall_readiness": summary,
        "warnings": warnings,
        "errors": errors,
    }


def _markdown_report(report):
    overall = report["overall_readiness"]
    lines = [
        "# Dreadstone Damage Readiness Report",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Analyzer revision: `{report.get('analyzer_revision', 'legacy')}`",
        f"- Analyzer build: `{report.get('analyzer_build_id', 'unknown')}`",
        f"- Analyzer module: `{report.get('analyzer_module_path', 'unknown')}`",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Blender: `{report['blender_version']}`",
        f"- Add-on: `{report['addon_version']}`",
        f"- Source: `{report['source_blend_path'] or '(unsaved blend)'}`",
        f"- Armature: `{report['armature_name']}`",
        f"- Rig profile: `{report['detected_rig_profile']}`",
        "",
        "## Overall Readiness",
        "",
        overall["readiness_statement"],
        "",
        f"- Usable skinning: **{'YES' if overall['usable_skinning'] else 'NO'}**",
        f"- Weight cleanup required: **{'YES' if overall['weight_cleanup_required'] else 'NO'}**",
        f"- Confirmed topology repair required: **{'YES' if overall['topology_repair_required'] else 'NO'}**",
        f"- Open-shell review required: **{'YES' if overall.get('open_shell_review_required') else 'NO'}**",
        f"- Automatic seam extraction unresolved: **{'YES' if overall.get('automatic_seam_extraction_unresolved') else 'NO'}**",
        f"- Existing shape keys: **{'YES' if overall['shape_keys_exist'] else 'NO'}**",
        f"- Ready for v3.8: **{'YES' if overall['ready_for_v3_8_segment_authoring'] else 'NO'}**",
        "",
        "Raw GLB seam splits do not count as holes. v3.7.4 uses non-destructive virtual positional welding and only marks topology repair for defects that remain after virtual welding.",
        "",
        "## Seam Verdicts",
        "",
    ]

    for seam in report["seam_reports"]:
        component = seam.get("selected_component") or {}
        lines.extend([
            f"### {seam.get('label', seam['id'])}: {seam['recommendation']}",
            "",
            f"- Proximal bone: `{seam.get('proximal_bone') or 'unavailable'}`",
            f"- Distal bone: `{seam.get('distal_bone') or 'unavailable'}`",
            f"- Mesh: `{seam.get('selected_mesh_object_name') or 'unavailable'}`",
            f"- Selected shell: `{seam.get('selected_shell_id', 'unavailable')}`",
            f"- Candidate confidence: `{seam.get('selected_component_score', 0.0):.3f}`",
            f"- Candidate source edges: `{seam.get('candidate_boundary_edge_count', 0)}`",
            f"- Contour segments: `{component.get('segment_count', 0)}`",
            f"- Closed contour: `{'yes' if component.get('closed') else 'no'}`",
            f"- Open endpoints: `{seam.get('open_endpoint_count', 0)}`",
            f"- Branch vertices: `{seam.get('branch_vertex_count', 0)}`",
            f"- Same-shell nearby non-manifold vertices: `{seam.get('non_manifold_vertices_within_one_edge_step_count', 0)}`",
            "",
            "Reasons:",
        ])
        for reason in seam.get("reasons", []):
            lines.append(f"- {reason}")
        rejected = seam.get("rejected_components", [])
        if rejected:
            lines.extend(["", "Rejected alternatives:"])
            for candidate in rejected:
                lines.append(
                    f"- shell {candidate['shell_id']}, component {candidate['component_id']}: score {candidate['score']:.3f}, closed={'yes' if candidate['closed'] else 'no'}"
                )
        if seam["recommendation"] == "MANUAL_REVIEW":
            lines.extend([
                "",
                "Suggested action:",
                "- Preview the selected contour and rejected alternatives in Forge.",
                "- Repair only the localized selected-shell defect or adjust seam weights.",
                "- Rerun the analyzer and generate a new fingerprinted report.",
            ])
        elif seam["recommendation"] == "MANUAL_REQUIRED":
            lines.extend([
                "",
                "Suggested action:",
                "- Inspect the expected joint plane and relevant shell.",
                "- Establish a clear proximal/distal weight transition or author a manual loop.",
            ])
        lines.append("")

    lines.extend(["## Mesh and Shell Health", ""])
    for mesh in report["mesh_reports"]:
        lines.extend([
            f"### {mesh['object_name']}",
            "",
            f"- Vertices / Edges / Polygons: `{mesh['vertex_count']} / {mesh['edge_count']} / {mesh['polygon_count']}`",
            f"- Weld-aware geometry shells: `{mesh.get('shell_count', 0)}`",
            f"- Largest shell fraction: `{mesh.get('largest_shell_fraction', 0.0):.3f}`",
            f"- Skinned mesh equivalent: `{'yes' if mesh['skinned_mesh_equivalent'] else 'no'}`",
            f"- Unweighted vertices: `{mesh['unweighted_vertex_count']}`",
            f"- Vertices over four influences: `{mesh['vertices_over_four_influences_count']}`",
            f"- Weight-sum deviations: `{mesh['weight_sum_deviation_count']}`",
            f"- Weld-aware boundary edges: `{mesh['boundary_edge_count']}`",
            f"- Weld-aware non-manifold edges: `{mesh['non_manifold_edge_count']}`",
            f"- Raw imported boundary edges: `{mesh.get('raw_boundary_edge_count', 0)}`",
            f"- Raw imported non-manifold edges: `{mesh.get('raw_non_manifold_edge_count', 0)}`",
            f"- Virtual welded vertices: `{mesh.get('welded_virtual_vertex_count', mesh['vertex_count'])}`",
            f"- Coincident GLB split vertices: `{mesh.get('welded_duplicate_vertex_count', 0)}`",
            f"- Loose edges / vertices: `{mesh['loose_edge_count']} / {mesh['loose_vertex_count']}`",
            f"- Degenerate faces: `{mesh['degenerate_face_count']}`",
            f"- Topology fingerprint: `{mesh['fingerprints']['topology_sha256']}`",
            f"- Weight fingerprint: `{mesh['fingerprints']['vertex_group_sha256']}`",
            "",
            "Largest shell summaries:",
        ])
        for shell in mesh.get("shell_reports", [])[:12]:
            lines.append(
                f"- shell {shell['shell_id']}: {shell['vertex_count']} vertices, {shell['polygon_count']} polygons, {shell['boundary_edge_count']} boundary edges, closed={'yes' if shell['closed_shell'] else 'no'}"
            )
        lines.append("")

    if report["warnings"]:
        lines.extend(["## Warnings", ""] + [f"- {warning}" for warning in report["warnings"]] + [""])
    if report["errors"]:
        lines.extend(["## Errors", ""] + [f"- {error}" for error in report["errors"]] + [""])
    lines.extend([
        "## Handoff Contract",
        "",
        "The JSON report is the validated input contract for Forge v3.8. v3.8 must reject a report when the target mesh topology or relevant vertex-group fingerprint no longer matches.",
        "",
        "Forge v3.7.4 performed no destructive edits.",
        "",
    ])
    return "\n".join(lines)


def _is_drive_root(path):
    normalized = os.path.abspath(path)
    drive, tail = os.path.splitdrive(normalized)
    stripped = tail.strip("/\\")
    return bool(drive) and not stripped


def resolve_damage_readiness_output_directory(settings):
    raw = (settings.damage_readiness_output_directory or "").strip()
    if not raw:
        raise RuntimeError(
            "Choose a Damage Readiness Report Output Folder. Forge intentionally has no C-drive fallback."
        )
    if raw.startswith("//") and not bpy.data.filepath:
        raise RuntimeError(
            "This .blend is unsaved. Choose an explicit Report Output Folder first; Forge will not resolve // to the current drive."
        )
    expanded = os.path.expandvars(os.path.expanduser(raw))
    output_directory = bpy.path.abspath(expanded)
    if not output_directory:
        raise RuntimeError("Choose a valid Damage Readiness Report Output Folder.")
    if _is_drive_root(output_directory):
        raise RuntimeError("The report folder cannot be a drive root. Choose a project folder or save the .blend first.")
    return os.path.normpath(output_directory)


def write_damage_readiness_reports(context, report):
    settings = context.scene.daf_settings
    output_directory = resolve_damage_readiness_output_directory(settings)
    os.makedirs(output_directory, exist_ok=True)
    character_name = _safe_name(report.get("armature_name") or "character")
    json_path = os.path.join(output_directory, f"{character_name}_damage_readiness.json")
    markdown_path = os.path.join(output_directory, f"{character_name}_damage_readiness.md")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=False)
    with open(markdown_path, "w", encoding="utf-8") as handle:
        handle.write(_markdown_report(report))
    return json_path, markdown_path


def _set_last_results(settings, report, json_path, markdown_path):
    settings.last_damage_readiness_json_path = json_path
    settings.last_damage_readiness_markdown_path = markdown_path
    settings.damage_readiness_overall_status = "READY" if report["overall_readiness"]["ready_for_v3_8_segment_authoring"] else "REVIEW"
    by_id = {entry["id"]: entry["recommendation"] for entry in report["seam_reports"]}
    settings.damage_readiness_head_neck_status = by_id.get("head_neck", "UNAVAILABLE")
    settings.damage_readiness_left_elbow_status = by_id.get("left_elbow", "UNAVAILABLE")
    settings.damage_readiness_right_elbow_status = by_id.get("right_elbow", "UNAVAILABLE")
    settings.damage_readiness_lower_spine_status = by_id.get("lower_spine", "UNAVAILABLE")


def _load_last_report(settings):
    path = bpy.path.abspath(settings.last_damage_readiness_json_path)
    if not path or not os.path.isfile(path):
        raise RuntimeError("Run Analyze Damage Readiness first; the last JSON report is unavailable.")
    with open(path, "r", encoding="utf-8") as handle:
        report = json.load(handle)
    if report.get("schema") != REPORT_SCHEMA:
        raise RuntimeError("The selected report does not use the v3.7 damage-readiness schema.")
    return report


def clear_damage_readiness_preview():
    removed = 0
    for obj in list(bpy.data.objects):
        if obj.get(PREVIEW_TAG, False):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
            if data and data.users == 0 and isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)
    collection = bpy.data.collections.get(PREVIEW_COLLECTION_NAME)
    if collection and not collection.objects:
        try:
            bpy.data.collections.remove(collection)
        except RuntimeError:
            pass
    return removed


def _preview_collection(context):
    collection = bpy.data.collections.get(PREVIEW_COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(PREVIEW_COLLECTION_NAME)
        context.scene.collection.children.link(collection)
    return collection


def _material(name, color):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        material.diffuse_color = (*color, 1.0)
        material.use_nodes = True
        principled = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
        if principled:
            base = principled.inputs.get("Base Color")
            if base:
                base.default_value = (*color, 1.0)
            emission = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")
            if emission:
                emission.default_value = (*color, 1.0)
            strength = principled.inputs.get("Emission Strength")
            if strength:
                strength.default_value = 1.5
    return material


def _evaluated_world_positions(context, obj):
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = None
    try:
        mesh = evaluated.to_mesh()
        if mesh and len(mesh.vertices) == len(obj.data.vertices):
            return [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
    finally:
        if mesh:
            evaluated.to_mesh_clear()
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


def _create_edge_preview(context, obj, vertex_positions, edge_indices, seam_id, category="selected", color=(0.1, 0.85, 1.0), bevel=0.004):
    curve = bpy.data.curves.new(f"DSB_{seam_id}_{category}_curve", type='CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 1
    curve.bevel_depth = bevel
    curve.bevel_resolution = 1
    for edge_index in edge_indices:
        if edge_index < 0 or edge_index >= len(obj.data.edges):
            continue
        edge = obj.data.edges[edge_index]
        spline = curve.splines.new('POLY')
        spline.points.add(1)
        a = vertex_positions[int(edge.vertices[0])]
        b = vertex_positions[int(edge.vertices[1])]
        spline.points[0].co = (*a, 1.0)
        spline.points[1].co = (*b, 1.0)
    preview = bpy.data.objects.new(f"DSB_{seam_id}_{category}_edges", curve)
    preview[PREVIEW_TAG] = True
    preview["dsb_preview_only"] = True
    preview.hide_render = True
    curve.materials.append(_material(f"DSB_DAMAGE_PREVIEW_{category.upper()}", color))
    _preview_collection(context).objects.link(preview)
    return preview


def _create_markers(context, vertex_positions, indices, seam_id, category, size, color):
    collection = _preview_collection(context)
    for vertex_index in indices:
        if vertex_index < 0 or vertex_index >= len(vertex_positions):
            continue
        marker = bpy.data.objects.new(f"DSB_{seam_id}_{category}_{vertex_index}", None)
        marker.empty_display_type = 'SPHERE'
        marker.empty_display_size = size
        marker.location = vertex_positions[vertex_index]
        marker.color = (*color, 1.0)
        marker[PREVIEW_TAG] = True
        marker["dsb_preview_only"] = True
        marker.hide_render = True
        collection.objects.link(marker)


def _create_joint_plane_preview(context, seam):
    plane = seam.get("joint_plane") or {}
    center = Vector(plane.get("center_world", (0.0, 0.0, 0.0)))
    normal = Vector(plane.get("normal_world", (0.0, 0.0, 1.0)))
    if normal.length_squared <= 1e-12:
        return None
    normal.normalize()
    tangent = normal.cross(Vector((0.0, 0.0, 1.0)))
    if tangent.length_squared <= 1e-8:
        tangent = normal.cross(Vector((0.0, 1.0, 0.0)))
    tangent.normalize()
    bitangent = normal.cross(tangent).normalized()
    size = 0.18
    corners = [
        center + tangent * size + bitangent * size,
        center - tangent * size + bitangent * size,
        center - tangent * size - bitangent * size,
        center + tangent * size - bitangent * size,
    ]
    curve = bpy.data.curves.new(f"DSB_{seam['id']}_joint_plane_curve", type='CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = 0.002
    spline = curve.splines.new('POLY')
    spline.points.add(4)
    for index, point in enumerate(corners + [corners[0]]):
        spline.points[index].co = (*point, 1.0)
    preview = bpy.data.objects.new(f"DSB_{seam['id']}_joint_plane", curve)
    preview[PREVIEW_TAG] = True
    preview["dsb_preview_only"] = True
    preview.hide_render = True
    curve.materials.append(_material("DSB_DAMAGE_PREVIEW_JOINT_PLANE", (0.7, 0.45, 1.0)))
    _preview_collection(context).objects.link(preview)
    return preview


def create_seam_preview(context, report, seam_id):
    clear_damage_readiness_preview()
    seam = next((entry for entry in report.get("seam_reports", []) if entry.get("id") == seam_id), None)
    if not seam:
        raise RuntimeError(f"The report does not contain seam {seam_id}.")
    object_name = seam.get("selected_mesh_object_name")
    obj = bpy.data.objects.get(object_name) if object_name else None
    if not obj or obj.type != 'MESH':
        raise RuntimeError("The seam's analyzed mesh is not available in the current scene.")
    expected_fingerprints = seam.get("mesh_fingerprints", {})
    relevant_groups = [name for name in report.get("semantic_bone_mapping", {}).values() if name]
    current_report, _topology = analyze_mesh_object(obj, relevant_groups)
    current_fingerprints = current_report["fingerprints"]
    if expected_fingerprints.get("topology_sha256") and expected_fingerprints["topology_sha256"] != current_fingerprints["topology_sha256"]:
        raise RuntimeError("Mesh topology changed after analysis. Rerun Damage Readiness before previewing this seam.")
    if expected_fingerprints.get("vertex_group_sha256") and expected_fingerprints["vertex_group_sha256"] != current_fingerprints["vertex_group_sha256"]:
        raise RuntimeError("Relevant seam weights changed after analysis. Rerun Damage Readiness before previewing this seam.")
    positions = _evaluated_world_positions(context, obj)
    selected_edges = seam.get("candidate_boundary_edge_indices", [])
    _create_edge_preview(context, obj, positions, selected_edges, seam_id, "selected", (0.1, 0.85, 1.0), 0.005)
    rejected_edge_count = 0
    for index, rejected in enumerate(seam.get("rejected_components", [])[:4]):
        edges = rejected.get("source_edge_indices", [])
        rejected_edge_count += len(edges)
        _create_edge_preview(context, obj, positions, edges, seam_id, f"rejected_{index + 1}", (0.9, 0.35, 0.08), 0.0025)
    _create_markers(context, positions, seam.get("open_endpoint_vertex_indices", []), seam_id, "endpoint", 0.025, (1.0, 0.2, 0.1))
    _create_markers(context, positions, seam.get("branch_vertex_indices", []), seam_id, "branch", 0.03, (1.0, 0.05, 0.8))
    _create_markers(context, positions, seam.get("nearby_non_manifold_vertex_indices", []), seam_id, "nonmanifold", 0.022, (1.0, 0.7, 0.05))
    _create_markers(context, positions, seam.get("crossover_vertex_indices", []), seam_id, "crossover", 0.007, (0.25, 1.0, 0.25))
    _create_joint_plane_preview(context, seam)
    return len(selected_edges), rejected_edge_count


class DAF_OT_analyze_damage_readiness(Operator):
    bl_idname = "daf.analyze_damage_readiness"
    bl_label = "Analyze Damage Readiness"
    bl_description = "Generate shell-aware, non-destructive mesh, weight, topology, and seam-readiness reports"
    bl_options = {'REGISTER'}

    def execute(self, context):
        state = _capture_context_state(context)
        try:
            report = build_damage_readiness_report(context)
            json_path, markdown_path = write_damage_readiness_reports(context, report)
            _set_last_results(context.scene.daf_settings, report, json_path, markdown_path)
            status = report["overall_readiness"]["readiness_statement"]
            self.report({'INFO'}, f"Damage readiness complete. {status}")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            _restore_context_state(context, state)


class DAF_OT_preview_damage_seam(Operator):
    bl_idname = "daf.preview_damage_seam"
    bl_label = "Preview Candidate Seam"
    bl_description = "Display the selected contour, rejected alternatives, and joint plane as temporary viewport helpers"
    bl_options = {'REGISTER'}

    def execute(self, context):
        state = _capture_context_state(context)
        try:
            settings = context.scene.daf_settings
            report = _load_last_report(settings)
            selected_count, rejected_count = create_seam_preview(context, report, settings.damage_readiness_preview_seam)
            self.report({'INFO'}, f"Previewed {selected_count} selected and {rejected_count} rejected candidate edges.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            _restore_context_state(context, state)


class DAF_OT_clear_damage_seam_preview(Operator):
    bl_idname = "daf.clear_damage_seam_preview"
    bl_label = "Clear Seam Preview"
    bl_description = "Remove all temporary Damage Readiness preview helpers"
    bl_options = {'REGISTER'}

    def execute(self, context):
        removed = clear_damage_readiness_preview()
        self.report({'INFO'}, f"Removed {removed} preview objects.")
        return {'FINISHED'}


class DAF_OT_open_damage_report_folder(Operator):
    bl_idname = "daf.open_damage_report_folder"
    bl_label = "Open Report Folder"
    bl_description = "Open the folder containing the last Damage Readiness reports"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.daf_settings
        path = bpy.path.abspath(settings.last_damage_readiness_json_path)
        if path:
            folder = os.path.dirname(path)
        else:
            try:
                folder = resolve_damage_readiness_output_directory(settings)
            except RuntimeError as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
        if not folder or not os.path.isdir(folder):
            self.report({'ERROR'}, "The Damage Readiness report folder does not exist.")
            return {'CANCELLED'}
        bpy.ops.wm.path_open(filepath=folder)
        return {'FINISHED'}


class DAF_OT_open_damage_markdown_report(Operator):
    bl_idname = "daf.open_damage_markdown_report"
    bl_label = "Open Markdown Report"
    bl_description = "Open the last human-readable Damage Readiness report"
    bl_options = {'REGISTER'}

    def execute(self, context):
        path = bpy.path.abspath(context.scene.daf_settings.last_damage_readiness_markdown_path)
        if not path or not os.path.isfile(path):
            self.report({'ERROR'}, "The last Damage Readiness Markdown report is unavailable.")
            return {'CANCELLED'}
        bpy.ops.wm.path_open(filepath=path)
        return {'FINISHED'}


CLASSES = (
    DAF_OT_analyze_damage_readiness,
    DAF_OT_preview_damage_seam,
    DAF_OT_clear_damage_seam_preview,
    DAF_OT_open_damage_report_folder,
    DAF_OT_open_damage_markdown_report,
)
