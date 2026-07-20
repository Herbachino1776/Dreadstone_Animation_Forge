"""Dreadstone Animation Forge v3.9.1 damage segment, stump, and morph export authoring.

Consumes a READY source-readiness contract, validates original-source identity,
and creates copied, materially cut segment meshes. The imported source mesh and
armature datablocks are never edited beyond stable identity metadata.
"""

import bpy
import hashlib
import json
import math
import os
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree
from bpy.types import Operator

from . import damage_readiness, trauma_field

AUTHORING_SCHEMA = "dreadstone.damage_authoring.v1"
AUTHORING_VERSION = (3, 9, 1)
AUTHORING_BUILD_ID = "2026-07-18.source-contract.1"
READINESS_SCHEMA = "dreadstone.damage_readiness.v1"
READINESS_REVISION_REQUIRED = "virtual_weld_v3.7.4"
STATE_TEXT_NAME = "DSB_DAMAGE_AUTHORING_STATE.json"
ROOT_COLLECTION_NAME = "DSB_DAMAGE_AUTHORING"
PROTECTED_COLLECTION_NAME = "DSB_PROTECTED_SOURCE"
INTACT_COLLECTION_NAME = "DSB_INTACT_SEGMENTS"
DETACHED_COLLECTION_NAME = "DSB_DETACHED_SEGMENTS"
STUMP_COLLECTION_NAME = "DSB_STUMP_CAPS"
HELPER_COLLECTION_NAME = "DSB_DAMAGE_HELPERS"
INTERIOR_MATERIAL_NAME = "DSB_INTERIOR_WOUND_MAT"
AUTHORING_RIG_NAME = "DSB_DAMAGE_RIG"
AUTHORING_SOURCE_MESH_NAME = "DSB_SOURCE_MODEL_PROTECTED"
BODY_CORE_NAME = "DSB_BODY_CORE"
ABDOMEN_SOCKET_NAME = "DSB_SOCKET_ABDOMEN_VISCERA"
CLIP_EPSILON = 1e-9

SEAM_SPECS = {
    "head_neck": {
        "label": "Head–Neck",
        "attached": "DSB_ATTACHED_HEAD",
        "detached": "DSB_SEGMENT_HEAD",
        "proximal_cap": "DSB_STUMP_NECK_TORSO",
        "distal_cap": "DSB_STUMP_NECK_HEAD",
        "proximal_bone": "neck",
        "distal_bone": "head",
        "fatal": True,
        "mass_hint": 4.5,
        "collider_hint": "convex_hull",
    },
    "left_elbow": {
        "label": "Left Elbow",
        "attached": "DSB_ATTACHED_FOREARM_L",
        "detached": "DSB_SEGMENT_FOREARM_L",
        "proximal_cap": "DSB_STUMP_ELBOW_L_UPPER",
        "distal_cap": "DSB_STUMP_ELBOW_L_LOWER",
        "proximal_bone": "arm_left_top",
        "distal_bone": "arm_left_bot",
        "fatal": False,
        "mass_hint": 1.8,
        "collider_hint": "convex_hull",
    },
    "right_elbow": {
        "label": "Right Elbow",
        "attached": "DSB_ATTACHED_FOREARM_R",
        "detached": "DSB_SEGMENT_FOREARM_R",
        "proximal_cap": "DSB_STUMP_ELBOW_R_UPPER",
        "distal_cap": "DSB_STUMP_ELBOW_R_LOWER",
        "proximal_bone": "arm_right_top",
        "distal_bone": "arm_right_bot",
        "fatal": False,
        "mass_hint": 1.8,
        "collider_hint": "convex_hull",
    },
    "lower_spine": {
        "label": "Lower Spine",
        "attached": None,
        "detached": "DSB_SEGMENT_UPPER_BODY",
        "proximal_segment": "DSB_SEGMENT_LOWER_BODY",
        "proximal_cap": "DSB_STUMP_WAIST_LOWER",
        "distal_cap": "DSB_STUMP_WAIST_UPPER",
        "proximal_bone": "body",
        "distal_bone": "body_top0",
        "fatal": True,
        "mass_hint": 28.0,
        "proximal_mass_hint": 32.0,
        "collider_hint": "compound_convex",
    },
}


GENERATED_OBJECT_NAMES = {
    BODY_CORE_NAME,
    ABDOMEN_SOCKET_NAME,
    AUTHORING_RIG_NAME,
    AUTHORING_SOURCE_MESH_NAME,
}
for _spec in SEAM_SPECS.values():
    for _key in ("attached", "detached", "proximal_segment", "proximal_cap", "distal_cap"):
        if _spec.get(_key):
            GENERATED_OBJECT_NAMES.add(_spec[_key])

RESERVED_COLLECTION_NAMES = {
    ROOT_COLLECTION_NAME,
    PROTECTED_COLLECTION_NAME,
    INTACT_COLLECTION_NAME,
    DETACHED_COLLECTION_NAME,
    STUMP_COLLECTION_NAME,
    HELPER_COLLECTION_NAME,
}


def _version_string():
    return ".".join(str(value) for value in AUTHORING_VERSION)


def _utc_timestamp():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha_indices(indices):
    digest = hashlib.sha256()
    for value in sorted(int(index) for index in indices):
        digest.update(f"{value},".encode("ascii"))
    return digest.hexdigest()


def _json_load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _json_write(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _set_hidden(obj, hidden):
    if obj is None:
        return
    try:
        obj.hide_set(bool(hidden))
    except RuntimeError:
        pass
    obj.hide_viewport = bool(hidden)
    obj.hide_render = bool(hidden)


def _damage_import_objects():
    return [
        obj for obj in bpy.data.objects
        if bool(obj.get("dsb_damage_generated", False))
    ]


def _enable_damage_collections(objects):
    collections = set()
    for obj in objects:
        collections.update(obj.users_collection)
    for collection in collections:
        collection.hide_viewport = False
        collection.hide_render = False

    def visit(layer_collection):
        if layer_collection.collection in collections:
            layer_collection.exclude = False
            layer_collection.hide_viewport = False
        for child in layer_collection.children:
            visit(child)

    for view_layer in bpy.context.scene.view_layers:
        visit(view_layer.layer_collection)


def _enable_mesh_visibility_in_viewports(context):
    changed = 0
    manager = getattr(context, "window_manager", None)
    if manager is None:
        return changed
    for window in manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = area.spaces.active
            if hasattr(space, "show_object_viewport_mesh") and not space.show_object_viewport_mesh:
                space.show_object_viewport_mesh = True
                changed += 1
    return changed


def _frame_objects_in_view(context, objects):
    if not objects:
        return False
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        try:
            obj.select_set(True)
        except RuntimeError:
            pass
    body = next((obj for obj in objects if obj.get("dsb_damage_role") == "body_core"), objects[0])
    context.view_layer.objects.active = body

    manager = getattr(context, "window_manager", None)
    if manager is None:
        return False
    for window in manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            region = next((region for region in area.regions if region.type == 'WINDOW'), None)
            if region is None:
                continue
            try:
                with context.temp_override(window=window, screen=screen, area=area, region=region):
                    bpy.ops.view3d.view_selected(use_all_regions=False)
                return True
            except (RuntimeError, TypeError):
                continue
    return False


def _restore_imported_intact_preview(context):
    objects = _damage_import_objects()
    if not objects:
        raise RuntimeError(
            "No imported Dreadstone damage objects were found. "
            "Import the exported Damage GLB first."
        )

    _enable_damage_collections(objects)
    viewport_filters_changed = _enable_mesh_visibility_in_viewports(context)
    visible = []
    hidden = []
    for obj in objects:
        role = obj.get("dsb_damage_role", "")
        default_visible = bool(obj.get("dsb_default_visible", False))
        should_show = default_visible or role in {"body_core", "attached_segment"}
        if obj.type == 'MESH':
            obj.display_type = 'TEXTURED'
        _set_hidden(obj, not should_show)
        (visible if should_show else hidden).append(obj)

    visible_meshes = [obj for obj in visible if obj.type == 'MESH']
    if not visible_meshes:
        raise RuntimeError(
            "Damage objects were found, but no default-visible body meshes were tagged. "
            "The GLB may not be a Forge v3.8+ export."
        )
    framed = _frame_objects_in_view(context, visible_meshes)
    return {
        "object_count": len(objects),
        "visible_mesh_count": len(visible_meshes),
        "hidden_object_count": len(hidden),
        "viewport_filters_changed": viewport_filters_changed,
        "framed": framed,
    }


def _delete_collection_tree(collection):
    for child in list(collection.children):
        _delete_collection_tree(child)
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)


def _clear_existing_authoring():
    root = bpy.data.collections.get(ROOT_COLLECTION_NAME)
    if root:
        if not root.get("dsb_damage_generated_collection", False):
            raise RuntimeError(
                f"Collection name '{ROOT_COLLECTION_NAME}' is reserved by Forge v3.8. "
                "Rename the existing user collection before building."
            )
        _delete_collection_tree(root)
    text = bpy.data.texts.get(STATE_TEXT_NAME)
    if text:
        bpy.data.texts.remove(text)
    # Region/event registries own generated authoring object identities. An
    # explicit authoring rebuild replaces those objects, so retaining the old
    # scene registry would silently bind new meshes to stale topology/weights.
    scene = getattr(bpy.context, "scene", None)
    if scene is not None:
        for key in (
            "dsb_deformation_region_registry_json",
            "dsb_compound_trauma_preview_json",
        ):
            if key in scene:
                del scene[key]

    # Restore original source visibility before checking for collisions.
    for obj in list(bpy.data.objects):
        if obj.get("dsb_hidden_for_damage_authoring", False):
            _set_hidden(obj, False)
            try:
                del obj["dsb_hidden_for_damage_authoring"]
            except KeyError:
                pass

    # Remove tagged generated objects that were manually moved outside the root.
    # Never delete a user-authored object just because its name collides.
    for name in sorted(GENERATED_OBJECT_NAMES):
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        if obj.get("dsb_damage_generated", False):
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            raise RuntimeError(
                f"Object name '{name}' is reserved by Forge v3.8. Rename the existing user object before building."
            )

    for name in sorted(RESERVED_COLLECTION_NAMES):
        collection = bpy.data.collections.get(name)
        if collection is None:
            continue
        if collection.get("dsb_damage_generated_collection", False):
            _delete_collection_tree(collection)
        else:
            raise RuntimeError(
                f"Collection name '{name}' is reserved by Forge v3.8. Rename the existing collection before building."
            )


def _ensure_child_collection(parent, name):
    if bpy.data.collections.get(name) is not None:
        raise RuntimeError(f"Reserved collection '{name}' still exists after cleanup.")
    collection = bpy.data.collections.new(name)
    collection["dsb_damage_generated_collection"] = True
    if parent:
        parent.children.link(collection)
    else:
        bpy.context.scene.collection.children.link(collection)
    return collection


def _create_collection_structure(context):
    if bpy.data.collections.get(ROOT_COLLECTION_NAME) is not None:
        raise RuntimeError(f"Reserved collection '{ROOT_COLLECTION_NAME}' still exists after cleanup.")
    root = bpy.data.collections.new(ROOT_COLLECTION_NAME)
    root["dsb_damage_generated_collection"] = True
    context.scene.collection.children.link(root)
    return {
        "root": root,
        "protected": _ensure_child_collection(root, PROTECTED_COLLECTION_NAME),
        "intact": _ensure_child_collection(root, INTACT_COLLECTION_NAME),
        "detached": _ensure_child_collection(root, DETACHED_COLLECTION_NAME),
        "stumps": _ensure_child_collection(root, STUMP_COLLECTION_NAME),
        "helpers": _ensure_child_collection(root, HELPER_COLLECTION_NAME),
    }


def _resolve_report_path(settings):
    candidate = settings.damage_authoring_report_path.strip() or settings.last_damage_readiness_json_path.strip()
    if not candidate:
        raise RuntimeError("Choose the READY v3.7.4 Damage Readiness JSON report.")
    path = os.path.abspath(bpy.path.abspath(candidate))
    if not os.path.isfile(path):
        raise RuntimeError("The selected Damage Readiness JSON report does not exist.")
    return path


def _validate_report_structure(report):
    if report.get("schema") != READINESS_SCHEMA:
        raise RuntimeError("The selected file is not a Dreadstone Damage Readiness report.")
    if report.get("analyzer_revision") != READINESS_REVISION_REQUIRED:
        raise RuntimeError("Forge v3.8 requires a virtual-weld v3.7.4 readiness report.")
    if not report.get("overall_readiness", {}).get("ready_for_v3_8_segment_authoring", False):
        raise RuntimeError("Source readiness is not READY for authoring.")
    source_contract = report.get("source_contract") or {}
    if source_contract.get("schema") != damage_readiness.SOURCE_CONTRACT_SCHEMA:
        raise RuntimeError(
            "Source readiness contract is missing or predates v3.8.1. "
            "Run Repair Source Readiness Contract before authoring or export."
        )
    generated_inventory = [
        name for name in source_contract.get("analyzedObjectNames", [])
        if trauma_field.is_generated_authoring_role(name)
    ]
    if generated_inventory:
        raise RuntimeError(
            "Source readiness contract incorrectly contains generated authoring meshes: "
            + ", ".join(generated_inventory)
            + ". Run Repair Source Readiness Contract."
        )
    seams = {entry.get("id"): entry for entry in report.get("seam_reports", [])}
    for seam_id, spec in SEAM_SPECS.items():
        seam = seams.get(seam_id)
        if not seam:
            raise RuntimeError(f"The readiness report is missing {spec['label']}.")
        if seam.get("recommendation") != "AUTOMATIC_CANDIDATE":
            raise RuntimeError(f"{spec['label']} is not an AUTOMATIC_CANDIDATE.")
        if not (seam.get("selected_component") or {}).get("closed", False):
            raise RuntimeError(f"{spec['label']} is not one closed contour.")
    return seams


def _source_mesh_from_report(context, report):
    mesh_reports = report.get("mesh_reports", [])
    if not mesh_reports:
        raise RuntimeError("The report contains no mesh fingerprint.")
    _armature, candidates = damage_readiness._resolve_contract_objects(
        report.get("source_contract") or {}
    )
    relevant_groups = sorted(set((report.get("semantic_bone_mapping") or {}).values()))
    checked = []
    for obj in candidates:
        expected = next(
            (entry for entry in mesh_reports if entry.get("object_name") == obj.name),
            None,
        )
        if expected is None:
            continue
        expected_fp = expected.get("fingerprints", {})
        checked.append(obj.name)
        try:
            analyzed, topology = damage_readiness.analyze_mesh_object(obj, relevant_groups)
        except Exception:
            continue
        current = analyzed.get("fingerprints", {})
        if (
            current.get("topology_sha256") == expected_fp.get("topology_sha256")
            and current.get("vertex_group_sha256") == expected_fp.get("vertex_group_sha256")
        ):
            return obj, analyzed, topology
    raise RuntimeError(
        "Source readiness stale: no registered original source mesh matches the topology and weight fingerprints. Checked: "
        + ", ".join(checked or ["none"])
    )


def _source_armature(source_mesh, report):
    contract = report.get("source_contract") or {}
    if contract:
        armature, _meshes = damage_readiness._resolve_contract_objects(contract)
        return armature
    named = bpy.data.objects.get(report.get("armature_name", ""))
    if named and named.type == 'ARMATURE':
        return named
    for modifier in source_mesh.modifiers:
        if modifier.type == 'ARMATURE' and modifier.object:
            return modifier.object
    current = source_mesh.parent
    while current:
        if current.type == 'ARMATURE':
            return current
        current = current.parent
    raise RuntimeError("Could not find the source armature named by the report.")


def _copy_object_to_collection(source, collection, name, copy_data=True):
    world = source.matrix_world.copy()
    obj = source.copy()
    if copy_data and source.data:
        obj.data = source.data.copy()
    obj.name = name
    collection.objects.link(obj)
    for key in (
        damage_readiness.SOURCE_OBJECT_ID_PROPERTY,
        damage_readiness.SOURCE_ROLE_PROPERTY,
    ):
        if key in obj:
            del obj[key]
    if getattr(obj, "data", None) is not None and damage_readiness.SOURCE_DATA_ID_PROPERTY in obj.data:
        del obj.data[damage_readiness.SOURCE_DATA_ID_PROPERTY]
    obj.parent = None
    obj.matrix_world = world
    obj["dsb_damage_generated"] = True
    obj["dsb_authoring_version"] = _version_string()
    return obj


def _retarget_armature_modifiers(obj, armature):
    for modifier in obj.modifiers:
        if modifier.type == 'ARMATURE':
            modifier.object = armature


def _make_protected_copies(source_mesh, source_armature, collections, report_path):
    rig = _copy_object_to_collection(source_armature, collections["protected"], AUTHORING_RIG_NAME, True)
    rig["dsb_damage_role"] = "authoring_rig"
    rig["dsb_source_armature"] = source_armature.name
    rig["dsb_readiness_report"] = report_path

    protected = _copy_object_to_collection(source_mesh, collections["protected"], AUTHORING_SOURCE_MESH_NAME, True)
    protected["dsb_damage_role"] = "protected_source_mesh"
    protected["dsb_source_object"] = source_mesh.name
    protected["dsb_readiness_report"] = report_path
    protected["dsb_authoring_source_mesh"] = True
    _retarget_armature_modifiers(protected, rig)

    source_mesh["dsb_hidden_for_damage_authoring"] = True
    source_armature["dsb_hidden_for_damage_authoring"] = True
    _set_hidden(source_mesh, True)
    _set_hidden(source_armature, True)
    _set_hidden(protected, True)
    return rig, protected


def _bone_descendant_names(armature, bone_name):
    bone = armature.data.bones.get(bone_name)
    if bone is None:
        raise RuntimeError(f"Required bone '{bone_name}' is missing from the authoring rig.")
    result, stack = set(), [bone]
    while stack:
        current = stack.pop()
        if current.name in result:
            continue
        result.add(current.name)
        stack.extend(list(current.children))
    return result


def _face_logical_edges(mesh, raw_to_weld):
    logical_edge_faces = defaultdict(set)
    for polygon in mesh.polygons:
        verts = [int(value) for value in polygon.vertices]
        for index, a in enumerate(verts):
            b = verts[(index + 1) % len(verts)]
            wa, wb = int(raw_to_weld[a]), int(raw_to_weld[b])
            if wa == wb:
                continue
            key = (wa, wb) if wa < wb else (wb, wa)
            logical_edge_faces[key].add(int(polygon.index))
    return logical_edge_faces


def _partition_faces(source_obj, authoring_rig, seam, topology):
    """Classify complete source polygons on the two sides of an approved seam.

    The analyzer contour is an interpolated zero crossing through polygons. The
    contour polygons themselves are cut exactly later; all other polygons need a
    stable side label. We label them by distal-bone-subtree weight versus the
    proximal seam-bone weight, then retain the connected distal component. This
    avoids treating contour crossing edges as face-graph barriers, which cannot
    divide polygons that the contour passes through.
    """
    mesh = source_obj.data
    all_faces = set(range(len(mesh.polygons)))
    logical_edge_faces = _face_logical_edges(mesh, topology["raw_vertex_to_weld"])
    adjacency = defaultdict(set)
    for faces in logical_edge_faces.values():
        face_list = sorted(faces)
        for index, face_a in enumerate(face_list):
            for face_b in face_list[index + 1:]:
                adjacency[face_a].add(face_b)
                adjacency[face_b].add(face_a)

    distal_names = _bone_descendant_names(authoring_rig, seam["distal_bone"])
    distal_indices = {group.index for group in source_obj.vertex_groups if group.name in distal_names}
    proximal_group = source_obj.vertex_groups.get(seam["proximal_bone"])
    if not distal_indices:
        raise RuntimeError(f"No vertex groups were found for distal region '{seam['distal_bone']}'.")
    if proximal_group is None:
        raise RuntimeError(f"Required proximal group '{seam['proximal_bone']}' is missing.")

    distal_vertex_weight = {}
    proximal_vertex_weight = {}
    for vertex in mesh.vertices:
        distal = 0.0
        proximal = 0.0
        for membership in vertex.groups:
            if membership.group in distal_indices:
                distal += float(membership.weight)
            if membership.group == proximal_group.index:
                proximal += float(membership.weight)
        distal_vertex_weight[int(vertex.index)] = distal
        proximal_vertex_weight[int(vertex.index)] = proximal

    face_distal = {}
    face_proximal = {}
    face_score = {}
    for polygon in mesh.polygons:
        indices = [int(value) for value in polygon.vertices]
        count = max(1, len(indices))
        distal = sum(distal_vertex_weight[index] for index in indices) / count
        proximal = sum(proximal_vertex_weight[index] for index in indices) / count
        face_index = int(polygon.index)
        face_distal[face_index] = distal
        face_proximal[face_index] = proximal
        face_score[face_index] = distal - proximal

    distal_seed = max(all_faces, key=lambda index: (face_score[index], face_distal[index], -index))
    allowed = {index for index in all_faces if face_score[index] > 0.0}
    distal = set()
    queue = deque([distal_seed])
    while queue:
        face = queue.popleft()
        if face in distal or face not in allowed:
            continue
        distal.add(face)
        queue.extend(adjacency.get(face, ()) - distal)
    proximal = all_faces - distal
    if not distal or not proximal:
        raise RuntimeError(f"{seam.get('label')} bone-weight partition did not divide the mesh.")

    # The exact contour polygons are clipped later, but their side labels still
    # participate in deterministic manifest hashes and validation.
    return {
        "distal_faces": sorted(distal),
        "proximal_faces": sorted(proximal),
        "distal_weight_score": float(sum(face_distal[index] for index in distal) / len(distal)),
        "proximal_weight_score": float(sum(face_distal[index] for index in proximal) / len(proximal)),
        "distal_bone_groups": sorted(distal_names),
        "classification": "connected_faces_where_distal_subtree_weight_exceeds_proximal_bone_weight",
    }


def _selected_shell_candidate(seam):
    selected_shell_id = seam.get("selected_shell_id")
    for candidate in seam.get("shell_candidates", []):
        if candidate.get("shell_id") == selected_shell_id:
            return candidate
    return None


def _reconstruct_contour(source_obj, seam, topology):
    raw_weights = damage_readiness._weights_for_groups(source_obj, seam["proximal_bone"], seam["distal_bone"])
    if raw_weights is None:
        raise RuntimeError(f"Missing seam groups for {seam.get('label')}.")
    weld_weights = damage_readiness._weights_for_weld_vertices(raw_weights, topology)
    plane_data = seam.get("joint_plane") or {}
    plane = {
        "center_object": Vector(plane_data.get("center_object", (0.0, 0.0, 0.0))),
        "normal_object": Vector(plane_data.get("normal_object", (0.0, 0.0, 1.0))),
    }
    shell = next((item for item in topology["shells"] if item["shell_id"] == seam.get("selected_shell_id")), None)
    shell_candidate = _selected_shell_candidate(seam)
    if not shell or not shell_candidate:
        raise RuntimeError(f"Could not reconstruct the selected shell for {seam.get('label')}.")
    nodes, components, _ambiguous = damage_readiness._contour_components(
        source_obj,
        shell,
        topology,
        weld_weights,
        plane,
        float(shell_candidate.get("slab_width_object", 0.1)),
    )
    expected_nodes = {tuple(int(value) for value in pair) for pair in (seam.get("selected_component") or {}).get("node_edge_keys", [])}
    component = next(
        (item for item in components if {tuple(pair) for pair in item.get("node_edge_keys", [])} == expected_nodes),
        None,
    )
    if component is None:
        raise RuntimeError(f"The {seam.get('label')} contour no longer matches its READY report.")

    segments = []
    node_set = expected_nodes
    for polygon_index in component.get("polygon_indices", []):
        raw_vertices = topology["polygon_vertices"][polygon_index]
        weld_vertices = [topology["raw_vertex_to_weld"][vertex] for vertex in raw_vertices]
        crossing = []
        for index, a in enumerate(weld_vertices):
            b = weld_vertices[(index + 1) % len(weld_vertices)]
            if a == b:
                continue
            key = (a, b) if a < b else (b, a)
            if key in node_set and key not in crossing:
                crossing.append(key)
        if len(crossing) == 2:
            segments.append((crossing[0], crossing[1], int(polygon_index)))
        elif len(crossing) > 2:
            remaining = set(crossing)
            while len(remaining) >= 2:
                first = min(remaining)
                remaining.remove(first)
                second = min(
                    remaining,
                    key=lambda key: (nodes[first]["point_object"] - nodes[key]["point_object"]).length_squared,
                )
                remaining.remove(second)
                segments.append((first, second, int(polygon_index)))

    adjacency = defaultdict(list)
    for a, b, _polygon in segments:
        adjacency[a].append(b)
        adjacency[b].append(a)
    if set(adjacency) != node_set or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise RuntimeError(f"The {seam.get('label')} contour is not one ordered degree-2 cycle.")
    start = min(node_set)
    order, previous, current = [start], None, start
    for _index in range(len(node_set) + 2):
        neighbors = sorted(adjacency[current])
        following = neighbors[0] if neighbors[0] != previous else neighbors[1]
        if following == start:
            break
        if following in order:
            raise RuntimeError(f"The {seam.get('label')} contour self-intersects.")
        order.append(following)
        previous, current = current, following
    if len(order) != len(node_set):
        raise RuntimeError(f"The {seam.get('label')} contour traversal is incomplete.")

    balance_by_raw = {index: float(distal - proximal) for index, (proximal, distal) in raw_weights.items()}
    return {
        "ordered_node_edge_keys": [list(key) for key in order],
        "points_object": [[float(value) for value in nodes[key]["point_object"]] for key in order],
        "node_t": {f"{key[0]}:{key[1]}": float(nodes[key]["t"]) for key in order},
        "node_combined_weight": {
            f"{key[0]}:{key[1]}": float(nodes[key]["combined_weight"]) for key in order
        },
        "segments": [[list(a), list(b), polygon] for a, b, polygon in segments],
        "contour_polygon_indices": sorted(set(int(item[2]) for item in segments)),
        "balance_by_raw_vertex": balance_by_raw,
    }


def _source_vertex_weights(source_obj):
    group_names = {group.index: group.name for group in source_obj.vertex_groups}
    result = {}
    for vertex in source_obj.data.vertices:
        values = {
            group_names[membership.group]: float(membership.weight)
            for membership in vertex.groups
            if membership.group in group_names and membership.weight > 0.0
        }
        result[int(vertex.index)] = values
    return result


def _lerp_dict(first, second, t):
    keys = set(first) | set(second)
    values = {key: first.get(key, 0.0) * (1.0 - t) + second.get(key, 0.0) * t for key in keys}
    return {key: value for key, value in values.items() if value > 1e-8}


def _clip_vertex_lerp(first, second, t, seam_id):
    raw_a, raw_b = int(first["raw_vertex"]), int(second["raw_vertex"])
    if raw_a <= raw_b:
        canonical_t = t
        edge = (raw_a, raw_b)
    else:
        canonical_t = 1.0 - t
        edge = (raw_b, raw_a)
    normal = first["normal"].lerp(second["normal"], t)
    if normal.length_squared > 1e-12:
        normal.normalize()
    return {
        "key": ("e", seam_id, edge[0], edge[1], round(float(canonical_t), 10)),
        "raw_vertex": raw_a,
        "position": first["position"].lerp(second["position"], t),
        "normal": normal,
        "weights": _lerp_dict(first["weights"], second["weights"], t),
        "uvs": {
            name: first["uvs"][name].lerp(second["uvs"][name], t)
            for name in first["uvs"]
        },
        "scalar": 0.0,
    }


def _clip_polygon(vertices, keep_distal, seam_id):
    if not vertices:
        return []
    output = []
    previous = vertices[-1]
    previous_inside = previous["scalar"] >= -CLIP_EPSILON if keep_distal else previous["scalar"] <= CLIP_EPSILON
    for current in vertices:
        current_inside = current["scalar"] >= -CLIP_EPSILON if keep_distal else current["scalar"] <= CLIP_EPSILON
        if current_inside != previous_inside:
            denominator = previous["scalar"] - current["scalar"]
            t = previous["scalar"] / denominator if abs(denominator) > 1e-12 else 0.5
            t = max(0.0, min(1.0, float(t)))
            output.append(_clip_vertex_lerp(previous, current, t, seam_id))
        if current_inside:
            output.append(current)
        previous, previous_inside = current, current_inside
    cleaned = []
    for item in output:
        if not cleaned or item["key"] != cleaned[-1]["key"]:
            cleaned.append(item)
    if len(cleaned) > 1 and cleaned[0]["key"] == cleaned[-1]["key"]:
        cleaned.pop()
    return cleaned


def _polygon_loop_vertices(source_obj, polygon, source_weights, scalar_values):
    mesh = source_obj.data
    uv_layers = list(mesh.uv_layers)
    result = []
    for loop_index in polygon.loop_indices:
        loop = mesh.loops[loop_index]
        raw_vertex = int(loop.vertex_index)
        try:
            normal = loop.normal.copy()
        except Exception:
            normal = mesh.vertices[raw_vertex].normal.copy()
        uvs = {}
        for layer in uv_layers:
            uvs[layer.name] = layer.data[loop_index].uv.copy()
        result.append({
            "key": ("v", raw_vertex),
            "raw_vertex": raw_vertex,
            "position": mesh.vertices[raw_vertex].co.copy(),
            "normal": normal,
            "weights": source_weights[raw_vertex],
            "uvs": uvs,
            "scalar": float(scalar_values.get(raw_vertex, 0.0)),
        })
    return result


def _create_clipped_mesh_object(
    source_obj,
    authoring_rig,
    collection,
    name,
    seam_contracts,
    side_rules,
    role,
    seam_id=None,
    skinned=True,
):
    mesh = source_obj.data
    source_weights = _source_vertex_weights(source_obj)
    contour_polygons = {
        sid: set(contract["contour_polygon_indices"]) for sid, contract in seam_contracts.items()
    }
    distal_faces = {sid: set(contract["partition"]["distal_faces"]) for sid, contract in seam_contracts.items()}
    uv_names = [layer.name for layer in mesh.uv_layers]

    vertices = []
    vertex_weights = []
    key_to_index = {}
    faces = []
    face_uvs = []
    face_normals = []
    face_materials = []
    face_smooth = []
    source_face_indices = []

    def vertex_index(item):
        key = item["key"]
        index = key_to_index.get(key)
        if index is None:
            index = len(vertices)
            key_to_index[key] = index
            vertices.append(tuple(item["position"]))
            vertex_weights.append(dict(item["weights"]))
        return index

    for polygon in mesh.polygons:
        source_index = int(polygon.index)
        contour_hits = [sid for sid in side_rules if source_index in contour_polygons[sid]]
        if len(contour_hits) > 1:
            raise RuntimeError(f"Source polygon {source_index} belongs to multiple authored seam contours.")

        include = True
        for sid, side in side_rules.items():
            if sid in contour_hits:
                continue
            is_distal = source_index in distal_faces[sid]
            if (side == "distal" and not is_distal) or (side == "proximal" and is_distal):
                include = False
                break
        if not include:
            continue

        if contour_hits:
            sid = contour_hits[0]
            scalar_values = seam_contracts[sid]["balance_by_raw_vertex"]
            polygon_vertices = _polygon_loop_vertices(source_obj, polygon, source_weights, scalar_values)
            clipped = _clip_polygon(polygon_vertices, side_rules[sid] == "distal", sid)
        else:
            scalar_values = {}
            clipped = _polygon_loop_vertices(source_obj, polygon, source_weights, scalar_values)

        if len(clipped) < 3:
            continue
        for fan_index in range(1, len(clipped) - 1):
            triangle = [clipped[0], clipped[fan_index], clipped[fan_index + 1]]
            indices = [vertex_index(item) for item in triangle]
            if len(set(indices)) < 3:
                continue
            faces.append(tuple(indices))
            # Keep UV layers separated to avoid flattening layer order.
            face_uvs.append({
                uv_name: [[float(value) for value in item["uvs"][uv_name]] for item in triangle]
                for uv_name in uv_names
            })
            face_normals.append([tuple(item["normal"]) for item in triangle])
            face_materials.append(int(polygon.material_index))
            face_smooth.append(bool(polygon.use_smooth))
            source_face_indices.append(source_index)

    if not faces:
        raise RuntimeError(f"No faces were generated for {name}.")

    new_mesh = bpy.data.meshes.new(name + "_MESH")
    new_mesh.from_pydata(vertices, [], faces)
    for material in mesh.materials:
        new_mesh.materials.append(material)
    for uv_name in uv_names:
        layer = new_mesh.uv_layers.new(name=uv_name)
        for polygon_index, polygon in enumerate(new_mesh.polygons):
            values = face_uvs[polygon_index][uv_name]
            for corner, loop_index in enumerate(polygon.loop_indices):
                layer.data[loop_index].uv = values[corner]
    loop_normals = []
    for polygon_index, polygon in enumerate(new_mesh.polygons):
        polygon.material_index = face_materials[polygon_index]
        polygon.use_smooth = face_smooth[polygon_index]
        loop_normals.extend(face_normals[polygon_index])
    new_mesh.update()
    try:
        new_mesh.normals_split_custom_set(loop_normals)
    except Exception:
        pass

    obj = source_obj.copy()
    obj.data = new_mesh
    obj.name = name
    collection.objects.link(obj)
    obj.parent = None
    obj.matrix_world = source_obj.matrix_world.copy()
    obj["dsb_damage_generated"] = True
    obj["dsb_authoring_version"] = _version_string()
    obj["dsb_damage_role"] = role
    obj["dsb_source_face_count"] = len(set(source_face_indices))
    obj["dsb_source_face_sha256"] = _sha_indices(source_face_indices)
    obj["dsb_generated_polygon_count"] = len(new_mesh.polygons)
    obj["dsb_default_visible"] = bool(role in {"body_core", "attached_segment"})
    if seam_id:
        obj["dsb_seam_id"] = seam_id

    # Object.copy preserves vertex-group definitions, but generated vertex
    # membership must be written explicitly because intersection vertices are new.
    for group in list(obj.vertex_groups):
        obj.vertex_groups.remove(group)
    groups = {}
    for vertex_index_value, weights in enumerate(vertex_weights):
        for group_name, weight in weights.items():
            group = groups.get(group_name)
            if group is None:
                group = obj.vertex_groups.new(name=group_name)
                groups[group_name] = group
            group.add([vertex_index_value], float(weight), 'REPLACE')

    if skinned:
        _retarget_armature_modifiers(obj, authoring_rig)
    else:
        for modifier in list(obj.modifiers):
            if modifier.type == 'ARMATURE':
                obj.modifiers.remove(modifier)
    return obj


def _duplicate_rigid_segment(source_obj, collection, name, seam_id, center_local, role):
    world = source_obj.matrix_world.copy()
    obj = source_obj.copy()
    obj.data = source_obj.data.copy()
    obj.name = name
    collection.objects.link(obj)
    obj.parent = None
    obj.matrix_world = world
    for modifier in list(obj.modifiers):
        if modifier.type == 'ARMATURE':
            obj.modifiers.remove(modifier)
    center_local = Vector(center_local)
    obj.data.transform(Matrix.Translation(-center_local))
    obj.matrix_world = world @ Matrix.Translation(center_local)
    obj["dsb_damage_generated"] = True
    obj["dsb_authoring_version"] = _version_string()
    obj["dsb_damage_role"] = role
    obj["dsb_seam_id"] = seam_id
    obj["dsb_default_visible"] = False
    obj["dsb_rigid_origin_source_local"] = [float(value) for value in center_local]
    return obj


def _newell_normal(points):
    normal = Vector((0.0, 0.0, 0.0))
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        normal.x += (current.y - following.y) * (current.z + following.z)
        normal.y += (current.z - following.z) * (current.x + following.x)
        normal.z += (current.x - following.x) * (current.y + following.y)
    if normal.length_squared <= 1e-12:
        normal = Vector((0.0, 0.0, 1.0))
    return normal.normalized()


def _interior_material():
    material = bpy.data.materials.get(INTERIOR_MATERIAL_NAME)
    if material is None:
        material = bpy.data.materials.new(INTERIOR_MATERIAL_NAME)
    material.diffuse_color = (0.22, 0.006, 0.01, 1.0)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
    if principled:
        if principled.inputs.get("Base Color"):
            principled.inputs["Base Color"].default_value = (0.22, 0.006, 0.01, 1.0)
        if principled.inputs.get("Roughness"):
            principled.inputs["Roughness"].default_value = 0.58
        if principled.inputs.get("Metallic"):
            principled.inputs["Metallic"].default_value = 0.0
    material["dsb_damage_interior_material"] = True
    return material


def _average_weights(source_obj, raw_indices):
    group_names = {group.index: group.name for group in source_obj.vertex_groups}
    totals = defaultdict(float)
    count = 0
    for raw_index in raw_indices:
        for membership in source_obj.data.vertices[int(raw_index)].groups:
            if membership.group in group_names:
                totals[group_names[membership.group]] += float(membership.weight)
        count += 1
    if not count:
        return {}
    values = {name: value / count for name, value in totals.items() if value > 0.0}
    total = sum(values.values())
    return {name: value / total for name, value in values.items()} if total > 1e-12 else values


def _contour_node_weights(source_obj, topology, node_key, t):
    a, b = int(node_key[0]), int(node_key[1])
    first = _average_weights(source_obj, topology["weld_members"][a])
    second = _average_weights(source_obj, topology["weld_members"][b])
    return _lerp_dict(first, second, float(t))


def _create_cap(source_obj, authoring_rig, collection, name, seam_id, seam, contract, topology, desired_normal, skinned):
    order = [tuple(pair) for pair in contract["ordered_node_edge_keys"]]
    points = [Vector(value) for value in contract["points_object"]]
    desired = Vector(desired_normal)
    if desired.length_squared <= 1e-12:
        desired = Vector((0.0, 0.0, 1.0))
    desired.normalize()
    if _newell_normal(points).dot(desired) < 0.0:
        order.reverse()
        points.reverse()
    center = sum(points, Vector((0.0, 0.0, 0.0))) / len(points)
    vertices = [tuple(point) for point in points] + [tuple(center)]
    center_index = len(points)
    faces = [(center_index, index, (index + 1) % len(points)) for index in range(len(points))]
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(_interior_material())
    for polygon in mesh.polygons:
        polygon.material_index = 0
        polygon.use_smooth = False
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.matrix_world = source_obj.matrix_world.copy()
    obj["dsb_damage_generated"] = True
    obj["dsb_authoring_version"] = _version_string()
    obj["dsb_damage_role"] = "stump_cap"
    obj["dsb_seam_id"] = seam_id
    obj["dsb_cap_side"] = "skinned_proximal" if skinned else "rigid_distal"
    obj["dsb_contour_vertex_count"] = len(points)
    obj["dsb_cap_expected_normal_object"] = [float(value) for value in desired]
    obj["dsb_default_visible"] = False

    if skinned:
        weights = []
        for node_key in order:
            t = contract["node_t"][f"{node_key[0]}:{node_key[1]}"]
            weights.append(_contour_node_weights(source_obj, topology, node_key, t))
        center_weights = defaultdict(float)
        for values in weights:
            for group_name, value in values.items():
                center_weights[group_name] += value
        center_weights = {name: value / len(weights) for name, value in center_weights.items()}
        weights.append(center_weights)
        groups = {}
        for vertex_index, values in enumerate(weights):
            for group_name, value in values.items():
                group = groups.get(group_name)
                if group is None:
                    group = obj.vertex_groups.new(name=group_name)
                    groups[group_name] = group
                group.add([vertex_index], float(value), 'REPLACE')
        modifier = obj.modifiers.new(name="Armature", type='ARMATURE')
        modifier.object = authoring_rig
    return obj, center, order, points


def _make_rigid_origin(obj, center_local):
    center_local = Vector(center_local)
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.data.transform(Matrix.Translation(-center_local))
    obj.matrix_world = world @ Matrix.Translation(center_local)
    obj["dsb_rigid_origin_source_local"] = [float(value) for value in center_local]


def _parent_preserve_world(child, parent):
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def _create_abdomen_socket(collection, source_obj, seam):
    center = Vector(seam["joint_plane"]["center_object"])
    socket = bpy.data.objects.new(ABDOMEN_SOCKET_NAME, None)
    collection.objects.link(socket)
    socket.empty_display_type = 'SPHERE'
    socket.empty_display_size = 0.045
    socket.matrix_world = source_obj.matrix_world @ Matrix.Translation(center)
    socket["dsb_damage_generated"] = True
    socket["dsb_damage_role"] = "viscera_socket"
    socket["dsb_socket_id"] = "abdomen_viscera"
    socket["dsb_default_visible"] = False
    return socket


def _store_state(state):
    text = bpy.data.texts.get(STATE_TEXT_NAME) or bpy.data.texts.new(STATE_TEXT_NAME)
    text.clear()
    text.write(json.dumps(state, indent=2, ensure_ascii=False))


def _load_state():
    text = bpy.data.texts.get(STATE_TEXT_NAME)
    if text is None:
        raise RuntimeError("No v3.8 damage authoring asset exists in this Blend file.")
    try:
        return json.loads(text.as_string())
    except Exception as exc:
        raise RuntimeError("The stored damage-authoring state is invalid.") from exc


def _build_authoring_asset_impl(context, report_path, report, seams, source_mesh, source_analysis):
    collections = _create_collection_structure(context)
    source_armature = _source_armature(source_mesh, report)
    authoring_rig, protected = _make_protected_copies(source_mesh, source_armature, collections, report_path)
    relevant_groups = sorted(set((report.get("semantic_bone_mapping") or {}).values()))
    _protected_analysis, topology = damage_readiness.analyze_mesh_object(protected, relevant_groups)

    contracts = {}
    for seam_id in SEAM_SPECS:
        partition = _partition_faces(protected, authoring_rig, seams[seam_id], topology)
        contour = _reconstruct_contour(protected, seams[seam_id], topology)
        contracts[seam_id] = {**contour, "partition": partition}

    # Contour polygons must be spatially disjoint for the combined intact core.
    contour_sets = {sid: set(contract["contour_polygon_indices"]) for sid, contract in contracts.items()}
    for first, second in (("head_neck", "left_elbow"), ("head_neck", "right_elbow"), ("left_elbow", "right_elbow")):
        if contour_sets[first] & contour_sets[second]:
            raise RuntimeError("Approved head and forearm contour polygons overlap unexpectedly.")

    objects = {}
    core = _create_clipped_mesh_object(
        protected,
        authoring_rig,
        collections["intact"],
        BODY_CORE_NAME,
        contracts,
        {"head_neck": "proximal", "left_elbow": "proximal", "right_elbow": "proximal"},
        "body_core",
        skinned=True,
    )
    objects[core.name] = core

    for seam_id in ("head_neck", "left_elbow", "right_elbow"):
        spec = SEAM_SPECS[seam_id]
        attached = _create_clipped_mesh_object(
            protected,
            authoring_rig,
            collections["intact"],
            spec["attached"],
            contracts,
            {seam_id: "distal"},
            "attached_segment",
            seam_id,
            skinned=True,
        )
        center = Vector(seams[seam_id]["joint_plane"]["center_object"])
        detached = _duplicate_rigid_segment(
            attached,
            collections["detached"],
            spec["detached"],
            seam_id,
            center,
            "detached_segment",
        )
        detached["dsb_mass_hint"] = float(spec["mass_hint"])
        detached["dsb_collider_hint"] = spec["collider_hint"]
        detached["dsb_fatal_detachment"] = bool(spec["fatal"])
        objects[attached.name] = attached
        objects[detached.name] = detached

    waist_spec = SEAM_SPECS["lower_spine"]
    upper = _create_clipped_mesh_object(
        protected,
        authoring_rig,
        collections["detached"],
        waist_spec["detached"],
        contracts,
        {"lower_spine": "distal"},
        "detached_upper_body",
        "lower_spine",
        skinned=False,
    )
    lower = _create_clipped_mesh_object(
        protected,
        authoring_rig,
        collections["detached"],
        waist_spec["proximal_segment"],
        contracts,
        {"lower_spine": "proximal"},
        "detached_lower_body",
        "lower_spine",
        skinned=False,
    )
    waist_center = Vector(seams["lower_spine"]["joint_plane"]["center_object"])
    _make_rigid_origin(upper, waist_center)
    _make_rigid_origin(lower, waist_center)
    upper["dsb_mass_hint"] = float(waist_spec["mass_hint"])
    lower["dsb_mass_hint"] = float(waist_spec["proximal_mass_hint"])
    upper["dsb_collider_hint"] = waist_spec["collider_hint"]
    lower["dsb_collider_hint"] = waist_spec["collider_hint"]
    upper["dsb_fatal_detachment"] = True
    lower["dsb_fatal_detachment"] = True
    objects[upper.name] = upper
    objects[lower.name] = lower

    cap_state = {}
    for seam_id, spec in SEAM_SPECS.items():
        seam, contract = seams[seam_id], contracts[seam_id]
        normal = Vector(seam["joint_plane"]["normal_object"])
        proximal_skinned = seam_id != "lower_spine"
        proximal_cap, center, order, cap_points = _create_cap(
            protected,
            authoring_rig,
            collections["stumps"],
            spec["proximal_cap"],
            seam_id,
            seam,
            contract,
            topology,
            normal,
            proximal_skinned,
        )
        distal_cap, _center2, _order2, _distal_points = _create_cap(
            protected,
            authoring_rig,
            collections["stumps"],
            spec["distal_cap"],
            seam_id,
            seam,
            contract,
            topology,
            -normal,
            False,
        )
        if seam_id == "lower_spine":
            _make_rigid_origin(proximal_cap, center)
            _make_rigid_origin(distal_cap, center)
            _parent_preserve_world(proximal_cap, lower)
            _parent_preserve_world(distal_cap, upper)
        else:
            _parent_preserve_world(distal_cap, objects[spec["detached"]])
        objects[proximal_cap.name] = proximal_cap
        objects[distal_cap.name] = distal_cap
        cap_state[seam_id] = {
            "ordered_node_edge_keys": [list(key) for key in order],
            "points_object": [[float(value) for value in point] for point in cap_points],
            "center_object": [float(value) for value in center],
            "proximal_cap": proximal_cap.name,
            "distal_cap": distal_cap.name,
        }

    socket = _create_abdomen_socket(collections["helpers"], protected, seams["lower_spine"])
    _parent_preserve_world(socket, upper)
    objects[socket.name] = socket

    source_contract = report.get("source_contract") or {}
    source_contract_record = next(
        (
            record for record in source_contract.get("sourceMeshes", [])
            if record.get("objectName") == source_mesh.name
        ),
        {},
    )
    state = {
        "schema": AUTHORING_SCHEMA,
        "authoring_version": _version_string(),
        "authoring_build_id": AUTHORING_BUILD_ID,
        "generated_at_utc": _utc_timestamp(),
        "readiness_report_path": report_path,
        "readiness_analyzer_revision": report.get("analyzer_revision"),
        "readiness_analyzer_build_id": report.get("analyzer_build_id"),
        "source_readiness_contract": source_contract,
        "source_object_name": source_mesh.name,
        "source_mesh_datablock_name": source_mesh.data.name,
        "source_armature_name": source_armature.name,
        "source_object_matrix_world": [list(row) for row in source_mesh.matrix_world],
        "source_object_scale": [float(value) for value in source_mesh.matrix_world.to_scale()],
        "source_fingerprints": source_analysis.get("fingerprints", {}),
        "source_contract_fingerprints": {
            "topology_sha256": source_contract_record.get("topologySha256"),
            "vertex_group_sha256": source_contract_record.get("weightSha256"),
        },
        "relevant_vertex_groups": relevant_groups,
        "virtual_weld_tolerance": float(topology["virtual_weld_tolerance"]),
        "raw_vertex_count": len(protected.data.vertices),
        "virtual_vertex_count": len(topology["weld_members"]),
        "source_polygon_count": len(protected.data.polygons),
        "authoring_rig": authoring_rig.name,
        "protected_source_mesh": protected.name,
        "objects": {name: obj.name for name, obj in objects.items()},
        "seams": {},
        "caps": cap_state,
    }
    for seam_id, contract in contracts.items():
        seam = seams[seam_id]
        node_families = {}
        for pair in contract["ordered_node_edge_keys"]:
            a, b = int(pair[0]), int(pair[1])
            key = f"{a}:{b}"
            node_families[key] = {
                "weldA": a,
                "weldB": b,
                "rawMembersA": list(topology["weld_members"][a]),
                "rawMembersB": list(topology["weld_members"][b]),
                "t": contract["node_t"][key],
            }
        state["seams"][seam_id] = {
            "label": seam.get("label"),
            "proximal_bone": seam.get("proximal_bone"),
            "distal_bone": seam.get("distal_bone"),
            "candidate_confidence": float(seam.get("selected_component_score", 0.0)),
            "source_edge_indices": seam.get("candidate_boundary_edge_indices", []),
            "source_vertex_indices": seam.get("candidate_boundary_vertex_indices", []),
            "ordered_contour_node_edge_keys": contract["ordered_node_edge_keys"],
            "contour_points_object": contract["points_object"],
            "contour_polygon_indices": contract["contour_polygon_indices"],
            "node_virtual_families": node_families,
            "joint_plane": seam.get("joint_plane"),
            "distal_source_faces": contract["partition"]["distal_faces"],
            "proximal_source_faces": contract["partition"]["proximal_faces"],
            "distal_face_sha256": _sha_indices(contract["partition"]["distal_faces"]),
            "proximal_face_sha256": _sha_indices(contract["partition"]["proximal_faces"]),
            "proximal_cap": SEAM_SPECS[seam_id]["proximal_cap"],
            "distal_cap": SEAM_SPECS[seam_id]["distal_cap"],
        }
    _store_state(state)
    _preview_intact(state)
    return state


def _build_authoring_asset(context, report_path, report, seams, source_mesh, source_analysis):
    _clear_existing_authoring()
    try:
        return _build_authoring_asset_impl(
            context, report_path, report, seams, source_mesh, source_analysis
        )
    except Exception:
        # A failed build must not leave Testman hidden or partial generated data.
        try:
            _clear_existing_authoring()
        except Exception:
            pass
        raise


def _object(name):
    return bpy.data.objects.get(name) if name else None


def _all_generated_objects(state):
    names = set(state.get("objects", {}).values())
    names.add(state.get("authoring_rig"))
    names.update(
        obj.name for obj in bpy.data.objects
        if bool(obj.get("dsb_gore_owned", False))
        and obj.get("dsb_generated_role") == "raised_gore"
        and not bool(obj.get("dsb_preview_only", True))
    )
    return [obj for name in names if name and (obj := bpy.data.objects.get(name))]


def _preview_intact(state):
    for obj in _all_generated_objects(state):
        _set_hidden(obj, True)
    for name in (
        BODY_CORE_NAME,
        SEAM_SPECS["head_neck"]["attached"],
        SEAM_SPECS["left_elbow"]["attached"],
        SEAM_SPECS["right_elbow"]["attached"],
    ):
        _set_hidden(_object(name), False)
    _set_hidden(_object(state.get("protected_source_mesh")), True)


def _preview_detached(state, seam_id):
    if seam_id not in SEAM_SPECS:
        raise RuntimeError("Choose a valid authored seam.")
    for obj in _all_generated_objects(state):
        _set_hidden(obj, True)
    spec = SEAM_SPECS[seam_id]
    if seam_id == "lower_spine":
        for name in (spec["detached"], spec["proximal_segment"], spec["proximal_cap"], spec["distal_cap"], ABDOMEN_SOCKET_NAME):
            _set_hidden(_object(name), False)
        return
    _set_hidden(_object(BODY_CORE_NAME), False)
    for other_id in ("head_neck", "left_elbow", "right_elbow"):
        other = SEAM_SPECS[other_id]
        if other_id == seam_id:
            for name in (other["detached"], other["proximal_cap"], other["distal_cap"]):
                _set_hidden(_object(name), False)
        else:
            _set_hidden(_object(other["attached"]), False)


def _validate_current_source(state):
    contract = state.get("source_readiness_contract")
    validation = damage_readiness.validate_source_readiness_contract(contract, bpy.context)
    if validation["status"] != "PASS":
        label = "Source readiness stale" if validation["status"] == "STALE" else "Source readiness invalid"
        raise RuntimeError(label + ": " + "; ".join(validation["reasons"][:4]))
    source = next(
        (
            bpy.data.objects.get(name) for name in validation["sourceObjects"]
            if bpy.data.objects.get(name) is not None and bpy.data.objects.get(name).type == 'MESH'
        ),
        None,
    )
    if source is None:
        raise RuntimeError(
            f"Source readiness stale: original source mesh {state.get('source_object_name', '<unknown>')} is missing or replaced."
        )
    return source


def _evaluated_hidden_world_matrix(obj):
    """Evaluate a hidden source hierarchy without changing its saved visibility.

    Blender can leave parented objects with ``hide_viewport`` disabled out of the
    dependency graph after reopening a file.  Their unevaluated ``matrix_world``
    then reads as identity even though the saved local transform and parent chain
    are intact.  Explicit validation may briefly make the chain evaluable, but it
    must restore the exact visibility contract before returning.
    """

    hierarchy = []
    current = obj
    while current is not None:
        hierarchy.append(current)
        current = current.parent
    visibility = [(item, bool(item.hide_viewport), bool(item.hide_get())) for item in hierarchy]
    try:
        for item, _viewport, _hidden in visibility:
            item.hide_viewport = False
            item.hide_set(False)
        bpy.context.view_layer.update()
        return obj.matrix_world.copy()
    finally:
        for item, viewport, hidden in reversed(visibility):
            item.hide_viewport = viewport
            item.hide_set(hidden)
        bpy.context.view_layer.update()


def _mesh_edge_face_counts(mesh):
    counts = defaultdict(int)
    for polygon in mesh.polygons:
        vertices = [int(value) for value in polygon.vertices]
        for index, a in enumerate(vertices):
            b = vertices[(index + 1) % len(vertices)]
            key = (a, b) if a < b else (b, a)
            counts[key] += 1
    return counts


def _world_kdtree(obj):
    world = _evaluated_hidden_world_matrix(obj)
    tree = KDTree(len(obj.data.vertices))
    for index, vertex in enumerate(obj.data.vertices):
        tree.insert(world @ vertex.co, index)
    tree.balance()
    return tree


def _maximum_world_point_error(obj, expected_world_points):
    if obj is None or obj.type != 'MESH' or not obj.data.vertices:
        return float("inf")
    tree = _world_kdtree(obj)
    maximum = 0.0
    for point in expected_world_points:
        _co, _index, distance = tree.find(point)
        maximum = max(maximum, float(distance))
    return maximum


def _cap_world_normal_in_source_space(cap, source):
    source_inverse = _evaluated_hidden_world_matrix(source).inverted_safe()
    cap_world = _evaluated_hidden_world_matrix(cap)
    normal = Vector((0.0, 0.0, 0.0))
    for polygon in cap.data.polygons:
        if len(polygon.vertices) < 3:
            continue
        a = source_inverse @ (cap_world @ cap.data.vertices[polygon.vertices[0]].co)
        b = source_inverse @ (cap_world @ cap.data.vertices[polygon.vertices[1]].co)
        c = source_inverse @ (cap_world @ cap.data.vertices[polygon.vertices[2]].co)
        normal += (b - a).cross(c - a)
    return normal.normalized() if normal.length_squared > 1e-12 else normal


def _validate_cap_mesh(cap, seam_label, expected_count, expected_normal, source, errors):
    if cap is None or cap.type != 'MESH':
        return
    mesh = cap.data
    if len(mesh.vertices) != expected_count + 1:
        errors.append(f"{cap.name} has {len(mesh.vertices)} vertices; expected {expected_count + 1}.")
    if len(mesh.polygons) != expected_count:
        errors.append(f"{cap.name} has {len(mesh.polygons)} faces; expected {expected_count}.")
    edge_counts = _mesh_edge_face_counts(mesh)
    boundary_count = sum(count == 1 for count in edge_counts.values())
    non_manifold_count = sum(count > 2 for count in edge_counts.values())
    if boundary_count != expected_count:
        errors.append(f"{cap.name} has {boundary_count} boundary edges; expected {expected_count}.")
    if non_manifold_count:
        errors.append(f"{cap.name} contains {non_manifold_count} non-manifold edges.")
    if INTERIOR_MATERIAL_NAME not in {material.name for material in mesh.materials if material}:
        errors.append(f"{cap.name} does not use {INTERIOR_MATERIAL_NAME}.")
    desired = Vector(expected_normal)
    actual = _cap_world_normal_in_source_space(cap, source)
    if desired.length_squared > 1e-12:
        desired.normalize()
        if actual.length_squared <= 1e-12 or actual.dot(desired) < 0.90:
            errors.append(f"{seam_label}: {cap.name} normals face the wrong direction.")


def _validate_authoring(state, gap_tolerance=0.0005):
    source = _validate_current_source(state)
    source_world = _evaluated_hidden_world_matrix(source)
    errors, warnings = [], []
    required = [
        BODY_CORE_NAME,
        SEAM_SPECS["head_neck"]["attached"],
        SEAM_SPECS["left_elbow"]["attached"],
        SEAM_SPECS["right_elbow"]["attached"],
        SEAM_SPECS["head_neck"]["detached"],
        SEAM_SPECS["left_elbow"]["detached"],
        SEAM_SPECS["right_elbow"]["detached"],
        SEAM_SPECS["lower_spine"]["detached"],
        SEAM_SPECS["lower_spine"]["proximal_segment"],
        ABDOMEN_SOCKET_NAME,
    ]
    for spec in SEAM_SPECS.values():
        required.extend([spec["proximal_cap"], spec["distal_cap"]])
    for name in required:
        obj = bpy.data.objects.get(name)
        if obj is None:
            errors.append(f"Missing generated object: {name}")
        elif obj.type == 'MESH' and len(obj.data.polygons) == 0:
            errors.append(f"Generated mesh has no polygons: {name}")

    rig = bpy.data.objects.get(state.get("authoring_rig", ""))
    if rig is None or rig.type != 'ARMATURE':
        errors.append("The generated DSB_DAMAGE_RIG is missing.")
    for name in (
        BODY_CORE_NAME,
        SEAM_SPECS["head_neck"]["attached"],
        SEAM_SPECS["left_elbow"]["attached"],
        SEAM_SPECS["right_elbow"]["attached"],
    ):
        obj = bpy.data.objects.get(name)
        if obj:
            targets = [modifier.object for modifier in obj.modifiers if modifier.type == 'ARMATURE']
            if rig not in targets:
                errors.append(f"{name} is not skinned to the authoring rig.")
    for name in (
        SEAM_SPECS["head_neck"]["detached"],
        SEAM_SPECS["left_elbow"]["detached"],
        SEAM_SPECS["right_elbow"]["detached"],
        SEAM_SPECS["lower_spine"]["detached"],
        SEAM_SPECS["lower_spine"]["proximal_segment"],
    ):
        obj = bpy.data.objects.get(name)
        if obj and any(modifier.type == 'ARMATURE' for modifier in obj.modifiers):
            errors.append(f"{name} must be a rigid prop without an Armature modifier.")

    protected = bpy.data.objects.get(state.get("protected_source_mesh", ""))
    if protected is None or protected.type != 'MESH':
        errors.append("Protected authoring source mesh is missing.")
    else:
        protected_world = _evaluated_hidden_world_matrix(protected)
        source_matrix = Matrix(state.get("source_object_matrix_world", source_world))
        matrix_error = max(
            abs(float(source_world[row][column] - source_matrix[row][column]))
            for row in range(4) for column in range(4)
        )
        if matrix_error > 1e-6:
            errors.append("The original source transform changed after v3.8 authoring.")

        piece_pairs = {
            "head_neck": (BODY_CORE_NAME, SEAM_SPECS["head_neck"]["attached"]),
            "left_elbow": (BODY_CORE_NAME, SEAM_SPECS["left_elbow"]["attached"]),
            "right_elbow": (BODY_CORE_NAME, SEAM_SPECS["right_elbow"]["attached"]),
            "lower_spine": (SEAM_SPECS["lower_spine"]["proximal_segment"], SEAM_SPECS["lower_spine"]["detached"]),
        }
        for seam_id, seam_state in state.get("seams", {}).items():
            label = SEAM_SPECS[seam_id]["label"]
            expected_local = [Vector(point) for point in seam_state.get("contour_points_object", [])]
            expected_world = [protected_world @ point for point in expected_local]
            if len(expected_world) < 3:
                errors.append(f"{label} has an incomplete stored contour.")
                continue
            proximal_name, distal_name = piece_pairs[seam_id]
            for piece_name in (proximal_name, distal_name):
                error = _maximum_world_point_error(bpy.data.objects.get(piece_name), expected_world)
                if error > gap_tolerance:
                    errors.append(
                        f"{label}: {piece_name} cut boundary misses the approved contour by {error:.6f} m."
                    )

            normal = Vector(seam_state.get("joint_plane", {}).get("normal_object", (0.0, 0.0, 1.0)))
            proximal_cap = bpy.data.objects.get(seam_state.get("proximal_cap", ""))
            distal_cap = bpy.data.objects.get(seam_state.get("distal_cap", ""))
            _validate_cap_mesh(proximal_cap, label, len(expected_world), normal, protected, errors)
            _validate_cap_mesh(distal_cap, label, len(expected_world), -normal, protected, errors)
            for cap in (proximal_cap, distal_cap):
                error = _maximum_world_point_error(cap, expected_world)
                if error > gap_tolerance:
                    errors.append(
                        f"{label}: {cap.name if cap else 'missing cap'} misses the approved contour by {error:.6f} m."
                    )

            distal = set(int(value) for value in seam_state.get("distal_source_faces", []))
            proximal = set(int(value) for value in seam_state.get("proximal_source_faces", []))
            if distal & proximal:
                errors.append(f"{label} source-side partitions overlap.")
            if len(distal | proximal) != int(state.get("source_polygon_count", 0)):
                errors.append(f"{label} source-side partitions do not cover every source polygon.")

    if state.get("source_polygon_count", 0) != len(source.data.polygons):
        errors.append("Stored source polygon count no longer matches the source mesh.")
    if source.data.shape_keys:
        warnings.append("The protected imported source contains shape keys; generated Damage Asset morphs remain independently authored.")

    deformation_validation = None
    try:
        from . import deformation_authoring
        deformation_validation = deformation_authoring.validate_deformations(require_keys=False)
        errors.extend(deformation_validation.get("errors", []))
        warnings.extend(deformation_validation.get("warnings", []))
    except RuntimeError:
        # A freshly built asset may not yet have deformation keys; missing pair
        # errors are already covered by the generated-object validation above.
        deformation_validation = {"status": "UNAVAILABLE", "managedKeyCount": 0, "errors": [], "warnings": []}

    return {
        "status": "PASS" if not errors else "FAIL",
        "validated_at_utc": _utc_timestamp(),
        "authoring_version": _version_string(),
        "authoring_build_id": AUTHORING_BUILD_ID,
        "source_topology_sha256": state.get("source_fingerprints", {}).get("topology_sha256"),
        "source_weight_sha256": state.get("source_fingerprints", {}).get("vertex_group_sha256"),
        "gap_tolerance_m": float(gap_tolerance),
        "errors": errors,
        "warnings": warnings,
        "generated_object_count": len(_all_generated_objects(state)),
        "source_readiness": {
            "status": "PASS",
            "contract_schema": (state.get("source_readiness_contract") or {}).get("schema"),
            "source_objects": (state.get("source_readiness_contract") or {}).get("analyzedObjectNames", []),
        },
        "deformation": deformation_validation,
    }


def _resolve_export_directory(settings):
    raw = settings.damage_authoring_output_directory.strip()
    if not raw:
        if not bpy.data.filepath:
            raise RuntimeError("Save the Blend file or choose an explicit Damage Export folder.")
        raw = "//damage_exports/"
    if raw.startswith("//") and not bpy.data.filepath:
        raise RuntimeError("An unsaved Blend file cannot use a // relative export folder.")
    path = os.path.abspath(bpy.path.abspath(raw))
    drive, tail = os.path.splitdrive(path)
    if drive and tail in ("\\", "/", ""):
        raise RuntimeError("Choose a project subfolder, not a drive root.")
    os.makedirs(path, exist_ok=True)
    return path


def _exporter_property_names():
    try:
        rna = bpy.ops.export_scene.gltf.get_rna_type()
    except Exception as exc:
        raise RuntimeError("Blender's built-in glTF 2.0 exporter is unavailable.") from exc
    return {prop.identifier for prop in rna.properties if prop.identifier != 'rna_type'}


def _manifest(state, validation, glb_filename):
    segments = []
    for seam_id, spec in SEAM_SPECS.items():
        seam = state["seams"][seam_id]
        segments.append({
            "segmentId": seam_id,
            "label": spec["label"],
            "attachedObject": spec.get("attached"),
            "detachedObject": spec.get("detached"),
            "proximalSegmentObject": spec.get("proximal_segment"),
            "parentRegion": spec["proximal_bone"],
            "bone": spec["distal_bone"],
            "connectingJoint": seam_id,
            "proximalStump": spec["proximal_cap"],
            "distalStump": spec["distal_cap"],
            "fatal": bool(spec["fatal"]),
            "detachedMassHint": float(spec["mass_hint"]),
            "proximalMassHint": float(spec.get("proximal_mass_hint", 0.0)),
            "colliderHint": spec["collider_hint"],
            "candidateConfidence": seam["candidate_confidence"],
            "sourceEdgeIndices": seam["source_edge_indices"],
            "sourceVertexIndices": seam["source_vertex_indices"],
            "contourSourcePolygonIndices": seam["contour_polygon_indices"],
            "orderedContourNodeEdges": seam["ordered_contour_node_edge_keys"],
            "contourPointsObject": seam["contour_points_object"],
            "nodeVirtualFamilies": seam["node_virtual_families"],
            "jointPlane": seam["joint_plane"],
            "distalSourceFaceSha256": seam["distal_face_sha256"],
            "proximalSourceFaceSha256": seam["proximal_face_sha256"],
        })
    return {
        "schema": AUTHORING_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": AUTHORING_BUILD_ID,
        "generatedAtUtc": _utc_timestamp(),
        "glb": glb_filename,
        "source": {
            "object": state["source_object_name"],
            "armature": state["source_armature_name"],
            "readinessContractSchema": (state.get("source_readiness_contract") or {}).get("schema"),
            "objectId": next(
                (
                    record.get("objectId")
                    for record in (state.get("source_readiness_contract") or {}).get("sourceMeshes", [])
                    if record.get("objectName") == state["source_object_name"]
                ),
                None,
            ),
            "meshDataId": next(
                (
                    record.get("dataId")
                    for record in (state.get("source_readiness_contract") or {}).get("sourceMeshes", [])
                    if record.get("objectName") == state["source_object_name"]
                ),
                None,
            ),
            "armatureObjectId": ((state.get("source_readiness_contract") or {}).get("sourceArmature") or {}).get("objectId"),
            "armatureDataId": ((state.get("source_readiness_contract") or {}).get("sourceArmature") or {}).get("dataId"),
            "topologyFingerprint": state["source_fingerprints"]["topology_sha256"],
            "weightFingerprint": state["source_fingerprints"]["vertex_group_sha256"],
            "readinessAnalyzerRevision": state["readiness_analyzer_revision"],
            "readinessAnalyzerBuildId": state["readiness_analyzer_build_id"],
            "virtualWeldTolerance": state["virtual_weld_tolerance"],
            "rawVertexCount": state["raw_vertex_count"],
            "virtualVertexCount": state["virtual_vertex_count"],
            "objectMatrixWorld": state.get("source_object_matrix_world"),
            "exportScale": state.get("source_object_scale"),
        },
        "intact": {
            "bodyCore": BODY_CORE_NAME,
            "attachedSegments": [
                SEAM_SPECS["head_neck"]["attached"],
                SEAM_SPECS["left_elbow"]["attached"],
                SEAM_SPECS["right_elbow"]["attached"],
            ],
        },
        "interiorMaterial": INTERIOR_MATERIAL_NAME,
        "sockets": [{"id": "abdomen_viscera", "object": ABDOMEN_SOCKET_NAME}],
        "segments": segments,
        "deformations": __import__(f"{__package__}.deformation_authoring", fromlist=["get_deformation_manifest"]).get_deformation_manifest(),
        "validation": validation,
    }


def _export_asset(context, settings, state):
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        raise RuntimeError("Switch Blender to Object Mode before exporting the Damage GLB.")
    from . import deformation_authoring
    try:
        _validate_current_source(state)
        deformation_authoring.prepare_for_export()
        validation = _validate_authoring(state, settings.damage_authoring_gap_tolerance)
    except Exception as exc:
        raise RuntimeError(f"Export validation failed: {exc}") from exc
    if validation["status"] != "PASS":
        raise RuntimeError(
            "Export validation failed: Authoring validation failed: "
            + "; ".join(validation["errors"][:4])
        )
    output_dir = _resolve_export_directory(settings)
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", settings.damage_authoring_filename.strip() or "testman_damage_v001")
    glb_path = os.path.join(output_dir, base + ".glb")
    manifest_path = os.path.join(output_dir, base + ".json")
    validation_path = os.path.join(output_dir, base + "_validation.json")

    selected_before = list(context.selected_objects)
    active_before = context.view_layer.objects.active
    export_objects = [obj for obj in _all_generated_objects(state) if obj.name != state.get("protected_source_mesh")]
    visibility = {}
    try:
        bpy.ops.object.select_all(action='DESELECT')
        for obj in export_objects:
            visibility[obj.name] = (obj.hide_viewport, obj.hide_render, obj.hide_get())
            _set_hidden(obj, False)
            obj.select_set(True)
        context.view_layer.objects.active = bpy.data.objects.get(state.get("authoring_rig", "")) or export_objects[0]
        supported = _exporter_property_names()
        kwargs = {"filepath": glb_path}
        selection_property = (
            "use_selection" if "use_selection" in supported
            else "export_selected" if "export_selected" in supported
            else None
        )
        if selection_property is None:
            raise RuntimeError("The installed glTF exporter exposes no selected-object export option.")
        kwargs[selection_property] = True
        for key, value in {
            "export_format": "GLB",
            "export_animations": True,
            "export_force_sampling": True,
            "export_extras": True,
            "export_apply": False,
            "export_morph": True,
            "export_morph_normal": True,
            "export_morph_tangent": False,
        }.items():
            if key in supported:
                kwargs[key] = value
        result = bpy.ops.export_scene.gltf(**kwargs)
        if 'FINISHED' not in result:
            raise RuntimeError("Blender did not finish exporting the Damage GLB.")
    finally:
        for obj in export_objects:
            if obj.name in visibility:
                viewport, render, hidden = visibility[obj.name]
                obj.hide_viewport, obj.hide_render = viewport, render
                try:
                    obj.hide_set(hidden)
                except RuntimeError:
                    pass
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_before:
            if obj and obj.name in context.view_layer.objects:
                obj.select_set(True)
        if active_before and active_before.name in context.view_layer.objects:
            context.view_layer.objects.active = active_before

    _json_write(manifest_path, _manifest(state, validation, os.path.basename(glb_path)))
    _json_write(validation_path, validation)
    return glb_path, manifest_path, validation_path


class DAF_OT_load_damage_readiness_handoff(Operator):
    bl_idname = "daf.load_damage_readiness_handoff"
    bl_label = "Load READY Handoff"
    bl_description = "Validate the selected virtual-weld v3.7.4 readiness JSON"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            path = _resolve_report_path(settings)
            report = _json_load(path)
            _validate_report_structure(report)
            source, _analysis, _topology = _source_mesh_from_report(context, report)
            settings.damage_authoring_report_path = path
            settings.damage_authoring_status = "READY HANDOFF LOADED"
            settings.source_readiness_contract_status = "VALID"
            settings.last_damage_authoring_validation = "NOT VALIDATED"
            settings.last_damage_export_validation = "NOT VALIDATED"
            self.report({'INFO'}, f"Source readiness valid for {source.name}; READY handoff loaded.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_build_damage_authoring_asset(Operator):
    bl_idname = "daf.build_damage_authoring_asset"
    bl_label = "Build Damage Authoring Asset"
    bl_description = "Create protected copies, materially cut segments, detached props, stump caps, and the abdomen socket"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            if getattr(context, "mode", "OBJECT") != 'OBJECT':
                raise RuntimeError("Switch Blender to Object Mode before building the Damage Authoring Asset.")
            settings = context.scene.daf_settings
            path = _resolve_report_path(settings)
            report = _json_load(path)
            seams = _validate_report_structure(report)
            source, analysis, _topology = _source_mesh_from_report(context, report)
            state = _build_authoring_asset(context, path, report, seams, source, analysis)
            settings.damage_authoring_report_path = path
            settings.damage_authoring_status = "BUILT — INTACT PREVIEW"
            settings.source_readiness_contract_status = "VALID"
            settings.last_damage_authoring_validation = "NOT VALIDATED"
            settings.last_damage_export_validation = "NOT VALIDATED"
            self.report({'INFO'}, f"Forge v3.9 built {len(_all_generated_objects(state))} authoring objects.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_clear_damage_authoring_asset(Operator):
    bl_idname = "daf.clear_damage_authoring_asset"
    bl_label = "Clear Damage Authoring Asset"
    bl_description = "Remove only Forge-generated damage objects and restore the original source visibility"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _clear_existing_authoring()
            settings = context.scene.daf_settings
            settings.damage_authoring_status = "NOT BUILT"
            settings.last_damage_authoring_validation = "NOT VALIDATED"
            settings.last_damage_export_validation = "NOT VALIDATED"
            self.report({'INFO'}, "Removed the generated damage authoring asset and restored the source.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_preview_damage_intact(Operator):
    bl_idname = "daf.preview_damage_intact"
    bl_label = "Preview Intact State"
    bl_description = "Show the body core and attached head and forearms with every stump hidden"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            state = _load_state()
            _preview_intact(state)
            context.scene.daf_settings.damage_authoring_status = "INTACT PREVIEW"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_preview_damage_detached(Operator):
    bl_idname = "daf.preview_damage_detached"
    bl_label = "Preview Detached State"
    bl_description = "Show the detached prop and both stump sides for the chosen seam"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            state = _load_state()
            _preview_detached(state, settings.damage_authoring_seam)
            settings.damage_authoring_status = "DETACHED PREVIEW — " + SEAM_SPECS[settings.damage_authoring_seam]["label"]
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_restore_imported_damage_intact_preview(Operator):
    bl_idname = "daf.restore_imported_damage_intact_preview"
    bl_label = "Restore Imported GLB Intact Preview"
    bl_description = (
        "After reimporting a Damage GLB, show the intact body meshes, hide detached "
        "pieces/caps/socket, enable mesh viewport visibility, and frame the character"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            result = _restore_imported_intact_preview(context)
            settings = getattr(context.scene, "daf_settings", None)
            if settings is not None:
                settings.damage_authoring_status = "IMPORTED GLB — INTACT PREVIEW"
            self.report(
                {'INFO'},
                "Restored imported intact preview: "
                f"{result['visible_mesh_count']} visible body meshes, "
                f"{result['hidden_object_count']} helpers/detached objects hidden."
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_validate_damage_authoring_asset(Operator):
    bl_idname = "daf.validate_damage_authoring_asset"
    bl_label = "Validate Complete Damage Asset"
    bl_description = "Verify fingerprints, generated pieces, caps, skinning, and contour gap tolerance"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            result = _validate_authoring(_load_state(), settings.damage_authoring_gap_tolerance)
            settings.last_damage_authoring_validation = result["status"]
            settings.last_damage_export_validation = "NOT VALIDATED"
            settings.source_readiness_contract_status = result["source_readiness"]["status"]
            settings.damage_authoring_status = "AUTHORING VALIDATION " + result["status"]
            if result["status"] == "PASS":
                self.report({'INFO'}, "Authoring validation passed.")
                return {'FINISHED'}
            self.report({'ERROR'}, "Authoring validation failed: " + "; ".join(result["errors"][:4]))
            return {'CANCELLED'}
        except Exception as exc:
            settings = context.scene.daf_settings
            settings.last_damage_authoring_validation = "FAIL"
            settings.last_damage_export_validation = "NOT VALIDATED"
            if "Source readiness stale" in str(exc):
                settings.source_readiness_contract_status = "STALE"
            elif "Source readiness invalid" in str(exc):
                settings.source_readiness_contract_status = "INVALID"
            self.report({'ERROR'}, "Authoring validation failed: " + str(exc))
            return {'CANCELLED'}


class DAF_OT_export_damage_asset(Operator):
    bl_idname = "daf.export_damage_asset"
    bl_label = "Export Damage GLB + Manifest"
    bl_description = "Validate and export the damage hierarchy, manifest, and validation report"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            glb_path, manifest_path, validation_path = _export_asset(context, settings, _load_state())
            settings.last_damage_glb_path = glb_path
            settings.last_damage_manifest_path = manifest_path
            settings.last_damage_validation_path = validation_path
            settings.damage_authoring_status = "EXPORTED"
            settings.last_damage_authoring_validation = "PASS"
            settings.last_damage_export_validation = "PASS"
            settings.source_readiness_contract_status = "VALID"
            self.report({'INFO'}, f"Exported {os.path.basename(glb_path)} and validated manifest.")
            return {'FINISHED'}
        except Exception as exc:
            settings = context.scene.daf_settings
            settings.last_damage_export_validation = "FAIL"
            if "Source readiness stale" in str(exc):
                settings.source_readiness_contract_status = "STALE"
            elif "Source readiness invalid" in str(exc):
                settings.source_readiness_contract_status = "INVALID"
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_open_damage_export_folder(Operator):
    bl_idname = "daf.open_damage_export_folder"
    bl_label = "Open Damage Export Folder"
    bl_description = "Open the folder containing the last Damage GLB and manifest"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.daf_settings
        path = settings.last_damage_glb_path or settings.last_damage_manifest_path
        if path:
            folder = os.path.dirname(bpy.path.abspath(path))
        else:
            try:
                folder = _resolve_export_directory(settings)
            except Exception as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
        if not os.path.isdir(folder):
            self.report({'ERROR'}, "The Damage Export folder does not exist.")
            return {'CANCELLED'}
        bpy.ops.wm.path_open(filepath=folder)
        return {'FINISHED'}


CLASSES = (
    DAF_OT_load_damage_readiness_handoff,
    DAF_OT_build_damage_authoring_asset,
    DAF_OT_clear_damage_authoring_asset,
    DAF_OT_preview_damage_intact,
    DAF_OT_preview_damage_detached,
    DAF_OT_restore_imported_damage_intact_preview,
    DAF_OT_validate_damage_authoring_asset,
    DAF_OT_export_damage_asset,
    DAF_OT_open_damage_export_folder,
)
