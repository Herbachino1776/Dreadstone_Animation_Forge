"""Dreadstone Animation Forge v3.9 deformation shape-key authoring.

The workbench edits only the generated protected Damage Asset. It creates
paired morph targets on DSB_ATTACHED_HEAD and DSB_SEGMENT_HEAD, keeps their
world-space deltas synchronized even when object scales differ, and never edits
the imported source mesh.
"""

import bmesh
import bpy
import hashlib
import json
import math
from mathutils import Vector
from bpy.props import StringProperty
from bpy.types import Operator

DEFORMATION_SCHEMA = "dreadstone.damage_deformation.v1"
DEFORMATION_VERSION = (3, 9, 1)
DEFORMATION_BUILD_ID = "2026-07-16.deformation-workbench.2"
ATTACHED_HEAD_NAME = "DSB_ATTACHED_HEAD"
DETACHED_HEAD_NAME = "DSB_SEGMENT_HEAD"
PREVIEW_KEY_NAME = "__DSB_DEFORMATION_SEED_PREVIEW"
METADATA_PROPERTY = "dsb_deformation_manifest_json"
PAIR_TOLERANCE = 1e-6
SYNC_TOLERANCE = 1e-6

STANDARD_HEAD_KEYS = {
    "Head_Dent_Left": {
        "family": "localized_dent", "side": "left", "mirrorPartner": "Head_Dent_Right",
        "seedRadius": 0.075, "seedDepth": 0.025, "seedFalloff": 1.65,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.045,
    },
    "Head_Dent_Right": {
        "family": "localized_dent", "side": "right", "mirrorPartner": "Head_Dent_Left",
        "seedRadius": 0.075, "seedDepth": 0.025, "seedFalloff": 1.65,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.045,
    },
    "Head_Cave_Front": {
        "family": "broad_cave", "side": "center", "mirrorPartner": "",
        "seedRadius": 0.105, "seedDepth": 0.038, "seedFalloff": 1.35,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.055,
    },
    "Jaw_Displaced": {
        "family": "directional_displacement", "side": "configurable", "mirrorPartner": "",
        "seedRadius": 0.080, "seedDepth": 0.024, "seedFalloff": 1.55,
        "maximumInfluence": 1.0, "maximumDisplacement": 0.050,
    },
}


def _version_string():
    return ".".join(str(value) for value in DEFORMATION_VERSION)


def _object(name):
    return bpy.data.objects.get(name)


def _resolve_pair():
    attached = _object(ATTACHED_HEAD_NAME)
    detached = _object(DETACHED_HEAD_NAME)
    if attached is None or attached.type != 'MESH':
        raise RuntimeError(f"Build or import the Damage Asset first; {ATTACHED_HEAD_NAME} is missing.")
    if detached is None or detached.type != 'MESH':
        raise RuntimeError(f"Build or import the Damage Asset first; {DETACHED_HEAD_NAME} is missing.")
    return attached, detached


def _topology_fingerprint(obj):
    digest = hashlib.sha256()
    digest.update(f"v:{len(obj.data.vertices)}|p:{len(obj.data.polygons)}|".encode("utf8"))
    for polygon in obj.data.polygons:
        digest.update((",".join(str(int(index)) for index in polygon.vertices) + ";").encode("ascii"))
    return digest.hexdigest()


def validate_topology_pair(attached=None, detached=None):
    attached, detached = (attached, detached) if attached and detached else _resolve_pair()
    errors = []
    if len(attached.data.vertices) != len(detached.data.vertices):
        errors.append("Attached and detached head vertex counts differ.")
    if len(attached.data.polygons) != len(detached.data.polygons):
        errors.append("Attached and detached head polygon counts differ.")
    attached_fingerprint = _topology_fingerprint(attached)
    detached_fingerprint = _topology_fingerprint(detached)
    if attached_fingerprint != detached_fingerprint:
        errors.append("Attached and detached head topology fingerprints differ; vertex-index transfer is unsafe.")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "attachedVertexCount": len(attached.data.vertices),
        "detachedVertexCount": len(detached.data.vertices),
        "attachedPolygonCount": len(attached.data.polygons),
        "detachedPolygonCount": len(detached.data.polygons),
        "topologyFingerprint": attached_fingerprint,
    }


def _metadata(obj):
    raw = obj.get(METADATA_PROPERTY, "") or obj.data.get(METADATA_PROPERTY, "")
    if raw:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    payload = {
        "schema": DEFORMATION_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": DEFORMATION_BUILD_ID,
        "region": "head",
        "attachedObject": ATTACHED_HEAD_NAME,
        "detachedObject": DETACHED_HEAD_NAME,
        "keys": {},
    }
    # Clean GLB reimports retain morph names even when a host strips extras.
    # Recover only the exact standard Forge names; never adopt arbitrary keys.
    other = _object(DETACHED_HEAD_NAME if obj.name == ATTACHED_HEAD_NAME else ATTACHED_HEAD_NAME)
    for name, template in STANDARD_HEAD_KEYS.items():
        if _key(obj, name) is not None and other is not None and _key(other, name) is not None:
            payload["keys"][name] = {"name": name, "region": "head", "status": "REIMPORTED", **template}
    return payload


def _store_metadata(attached, detached, payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    attached.data[METADATA_PROPERTY] = encoded
    detached.data[METADATA_PROPERTY] = encoded
    attached[METADATA_PROPERTY] = encoded
    detached[METADATA_PROPERTY] = encoded
    attached["dsb_deformation_region"] = "head"
    detached["dsb_deformation_region"] = "head"


def _ensure_basis(obj):
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    return obj.data.shape_keys.reference_key


def _key(obj, name):
    keys = obj.data.shape_keys
    return keys.key_blocks.get(name) if keys else None


def _managed_names(attached=None):
    attached = attached or _resolve_pair()[0]
    metadata = _metadata(attached)
    names = []
    for name in metadata.get("keys", {}):
        if name == PREVIEW_KEY_NAME:
            continue
        if _key(attached, name):
            names.append(name)
    return names


def _escape_data_path(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _link_detached_value(attached, detached, name):
    detached_key = _key(detached, name)
    if detached_key is None:
        return
    try:
        detached_key.driver_remove("value")
    except (TypeError, RuntimeError):
        pass
    fcurve = detached_key.driver_add("value")
    driver = fcurve.driver
    driver.type = 'AVERAGE'
    variable = driver.variables.new()
    variable.name = "attached_weight"
    variable.type = 'SINGLE_PROP'
    target = variable.targets[0]
    target.id_type = 'KEY'
    target.id = attached.data.shape_keys
    target.data_path = f'key_blocks["{_escape_data_path(name)}"].value'


def _ensure_key_pair(name, metadata_entry=None, preview=False):
    if not name or name == "Basis":
        raise RuntimeError("Choose a valid deformation key name.")
    attached, detached = _resolve_pair()
    contract = validate_topology_pair(attached, detached)
    if contract["status"] != "PASS":
        raise RuntimeError(" ".join(contract["errors"]))
    _ensure_basis(attached)
    _ensure_basis(detached)
    payload = _metadata(attached)
    attached_key = _key(attached, name)
    detached_key = _key(detached, name)
    if not preview and name not in payload.get("keys", {}) and (attached_key is not None or detached_key is not None):
        raise RuntimeError(f"A non-Forge shape key named {name} already exists; choose another name.")
    created_attached = attached_key is None
    created_detached = detached_key is None
    attached_key = attached_key or attached.shape_key_add(name=name, from_mix=False)
    detached_key = detached_key or detached.shape_key_add(name=name, from_mix=False)
    attached_key.slider_min = 0.0
    detached_key.slider_min = 0.0
    maximum = float((metadata_entry or {}).get("maximumInfluence", 1.0))
    attached_key.slider_max = maximum
    detached_key.slider_max = maximum
    if created_attached or created_detached:
        attached_key.value = 0.0
        detached_key.value = 0.0
        _link_detached_value(attached, detached, name)
    if not preview:
        entry = {
            "name": name,
            "region": "head",
            "family": (metadata_entry or {}).get("family", "manual"),
            "side": (metadata_entry or {}).get("side", "configurable"),
            "mirrorPartner": (metadata_entry or {}).get("mirrorPartner", ""),
            "maximumInfluence": maximum,
            "maximumDisplacement": float((metadata_entry or {}).get("maximumDisplacement", 0.045)),
            "status": (metadata_entry or {}).get("status", "EMPTY"),
            "seedRadius": float((metadata_entry or {}).get("seedRadius", 0.055)),
            "seedDepth": float((metadata_entry or {}).get("seedDepth", 0.016)),
            "seedFalloff": float((metadata_entry or {}).get("seedFalloff", 2.2)),
        }
        payload.setdefault("keys", {})[name] = {**payload.get("keys", {}).get(name, {}), **entry}
        _store_metadata(attached, detached, payload)
    return attached, detached, attached_key, detached_key


def _remove_key(obj, name):
    key_block = _key(obj, name)
    if key_block is not None and key_block != obj.data.shape_keys.reference_key:
        try:
            key_block.driver_remove("value")
        except (TypeError, RuntimeError):
            pass
        obj.shape_key_remove(key_block)


def clear_seed_preview():
    try:
        attached, detached = _resolve_pair()
    except RuntimeError:
        return
    _remove_key(attached, PREVIEW_KEY_NAME)
    _remove_key(detached, PREVIEW_KEY_NAME)


def _head_seam_points():
    try:
        from . import damage_authoring
        state = damage_authoring._load_state()
        points = state.get("seams", {}).get("head_neck", {}).get("contour_points_object", [])
        return [Vector(point) for point in points]
    except Exception:
        return []


def _direction(settings):
    mode = settings.deformation_seed_direction_mode
    if mode == 'INWARD_SURFACE_NORMAL':
        vector = -Vector(settings.deformation_seed_surface_normal)
    elif mode == 'OUTWARD_SURFACE_NORMAL':
        vector = Vector(settings.deformation_seed_surface_normal)
    else:
        vectors = {
            'LOCAL_X': Vector((1, 0, 0)), 'LOCAL_NEG_X': Vector((-1, 0, 0)),
            'LOCAL_Y': Vector((0, 1, 0)), 'LOCAL_NEG_Y': Vector((0, -1, 0)),
            'LOCAL_Z': Vector((0, 0, 1)), 'LOCAL_NEG_Z': Vector((0, 0, -1)),
            'CUSTOM_VECTOR': Vector(settings.deformation_seed_custom_direction),
        }
        vector = vectors.get(mode, Vector((0, 0, -1)))
    if vector.length_squared <= 1e-12:
        raise RuntimeError("The deformation direction vector has zero length.")
    return vector.normalized()


def _smoothstep(value):
    t = max(0.0, min(1.0, float(value)))
    return t * t * (3.0 - 2.0 * t)


def _linear_world_matrix(obj):
    return obj.matrix_world.to_3x3()


def _local_delta_to_world(obj, delta):
    return _linear_world_matrix(obj) @ Vector(delta)


def _world_delta_to_local(obj, delta):
    matrix = _linear_world_matrix(obj)
    try:
        return matrix.inverted() @ Vector(delta)
    except ValueError:
        raise RuntimeError(f"{obj.name} has a singular object transform; apply or repair scale before deformation authoring.")


def _normal_local_to_world(obj, normal):
    matrix = _linear_world_matrix(obj)
    try:
        result = matrix.inverted().transposed() @ Vector(normal)
    except ValueError:
        raise RuntimeError(f"{obj.name} has a singular object transform; cannot transform the captured surface normal.")
    if result.length_squared <= 1e-12:
        raise RuntimeError("The transformed deformation direction has zero length.")
    return result.normalized()


def _seed_direction_world(settings, obj):
    mode = settings.deformation_seed_direction_mode
    local = _direction(settings)
    if mode in {'INWARD_SURFACE_NORMAL', 'OUTWARD_SURFACE_NORMAL'}:
        return _normal_local_to_world(obj, local)
    result = _linear_world_matrix(obj) @ local
    if result.length_squared <= 1e-12:
        raise RuntimeError("The transformed deformation axis has zero length.")
    return result.normalized()


def _set_authoring_view(attached, detached, mode='ATTACHED'):
    # hide_set is viewport-only and does not alter export visibility. It prevents
    # the intact detached segment from sitting directly on top of the skinned head
    # and masking the seed preview.
    if mode == 'ATTACHED':
        attached.hide_set(False)
        detached.hide_set(True)
    elif mode == 'DETACHED':
        attached.hide_set(True)
        detached.hide_set(False)
    else:
        attached.hide_set(False)
        detached.hide_set(False)


def _zero_managed_weights(attached, include_preview=False):
    for name in _managed_names(attached):
        key = _key(attached, name)
        if key:
            key.value = 0.0
    if include_preview:
        preview = _key(attached, PREVIEW_KEY_NAME)
        if preview:
            preview.value = 0.0


def _seed_coordinates(settings, attached):
    if not settings.deformation_seed_center_valid:
        raise RuntimeError("Capture a surface center before previewing the seed.")
    center_local = Vector(settings.deformation_seed_center)
    center_world = attached.matrix_world @ center_local
    direction_world = _seed_direction_world(settings, attached)
    radius = max(1e-6, float(settings.deformation_seed_radius))
    depth = max(0.0, float(settings.deformation_seed_depth))
    falloff = max(0.01, float(settings.deformation_seed_falloff))
    max_displacement = max(1e-6, float(settings.deformation_max_vertex_displacement))
    seam_protection = max(0.0, float(settings.deformation_seed_seam_protection))
    seam_points_world = [attached.matrix_world @ point for point in _head_seam_points()]
    payload = _metadata(attached)
    entry = payload.get("keys", {}).get(settings.deformation_active_key, {})
    family = entry.get("family", "manual")
    outward_world = -direction_world
    coordinates = []
    inverse_world = attached.matrix_world.inverted()
    basis_block = attached.data.shape_keys.reference_key if attached.data.shape_keys else None
    affected = 0
    maximum_world_displacement = 0.0
    for index, vertex in enumerate(attached.data.vertices):
        basis_local = (basis_block.data[index].co if basis_block else vertex.co).copy()
        basis_world = attached.matrix_world @ basis_local
        offset_world = basis_world - center_world
        # Surface dents are selected by radial world-space distance. The slider
        # values therefore remain real meters regardless of object scale.
        distance = offset_world.length
        normalized = max(0.0, 1.0 - distance / radius)
        core = normalized ** falloff
        seam_factor = 1.0
        if seam_points_world and seam_protection > 0.0:
            seam_distance = min((basis_world - point).length for point in seam_points_world)
            seam_factor = _smoothstep(seam_distance / seam_protection)
        displacement_world = Vector((0.0, 0.0, 0.0))
        if core > 0.0:
            if family == "localized_dent":
                # A shallow raised lip makes the preset read as a dent instead of
                # a rubbery uniform translation. The lip is deliberately subtle.
                radial_fraction = min(1.0, distance / radius)
                rim = math.exp(-((radial_fraction - 0.78) / 0.14) ** 2) * depth * 0.13
                inward = depth * core
                displacement_world = direction_world * inward + outward_world * rim
            elif family == "broad_cave":
                inward = depth * (normalized ** max(0.55, falloff * 0.72))
                displacement_world = direction_world * inward
            elif family == "directional_displacement":
                plateau = _smoothstep(min(1.0, normalized * 1.35))
                displacement_world = direction_world * (depth * plateau)
            else:
                displacement_world = direction_world * (depth * core)
            displacement_world *= seam_factor
            if displacement_world.length > max_displacement:
                displacement_world.normalize()
                displacement_world *= max_displacement
            if displacement_world.length > 1e-8:
                affected += 1
                maximum_world_displacement = max(maximum_world_displacement, displacement_world.length)
        result_world = basis_world + displacement_world
        coordinates.append(inverse_world @ result_world)
    if affected == 0:
        raise RuntimeError(
            "The seed radius reached no vertices in world space. This usually means the captured center belongs to the other head object; show the attached head, capture again, and retry."
        )
    settings.deformation_status = f"LIVE SEED — {affected} vertices / {maximum_world_displacement:.3f} m"
    return coordinates


def _set_key_coordinates(key_block, coordinates):
    if len(key_block.data) != len(coordinates):
        raise RuntimeError("Shape-key coordinate count does not match the mesh.")
    for point, coordinate in zip(key_block.data, coordinates):
        point.co = coordinate


def sync_key_to_detached(name):
    attached, detached = _resolve_pair()
    contract = validate_topology_pair(attached, detached)
    if contract["status"] != "PASS":
        raise RuntimeError(" ".join(contract["errors"]))
    attached_key = _key(attached, name)
    detached_key = _key(detached, name)
    if attached_key is None or detached_key is None:
        raise RuntimeError(f"The paired key {name} is incomplete.")
    attached_basis = attached.data.shape_keys.reference_key
    detached_basis = detached.data.shape_keys.reference_key
    for index in range(len(attached_key.data)):
        delta_attached_local = attached_key.data[index].co - attached_basis.data[index].co
        delta_world = _local_delta_to_world(attached, delta_attached_local)
        delta_detached_local = _world_delta_to_local(detached, delta_world)
        detached_key.data[index].co = detached_basis.data[index].co + delta_detached_local
    _link_detached_value(attached, detached, name)


def preview_seed(context, quiet=False):
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        raise RuntimeError("Switch to Object Mode before previewing a deformation seed.")
    settings = context.scene.daf_settings
    attached, detached, attached_preview, _detached_preview = _ensure_key_pair(PREVIEW_KEY_NAME, preview=True)
    _zero_managed_weights(attached)
    _set_authoring_view(attached, detached, 'ATTACHED')
    coordinates = _seed_coordinates(settings, attached)
    _set_key_coordinates(attached_preview, coordinates)
    sync_key_to_detached(PREVIEW_KEY_NAME)
    attached_preview.value = 1.0
    attached_preview.slider_max = 1.0
    settings.deformation_status = "LIVE SEED PREVIEW"
    if not quiet:
        return {"vertexCount": len(coordinates), "key": settings.deformation_active_key}
    return None


def refresh_live_seed_preview(context):
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if not settings or not settings.deformation_auto_preview:
        return
    try:
        if settings.deformation_seed_center_valid and settings.deformation_active_key:
            preview_seed(context, quiet=True)
    except Exception as exc:
        settings.deformation_status = "SEED PREVIEW ERROR: " + str(exc)[:120]


def update_active_key_metadata(context):
    settings = getattr(getattr(context, "scene", None), "daf_settings", None)
    if not settings or not settings.deformation_active_key:
        return
    try:
        attached, detached = _resolve_pair()
        payload = _metadata(attached)
        entry = payload.get("keys", {}).get(settings.deformation_active_key)
        if not entry:
            return
        entry["maximumInfluence"] = float(settings.deformation_maximum_influence)
        entry["maximumDisplacement"] = float(settings.deformation_max_vertex_displacement)
        for obj in (attached, detached):
            block = _key(obj, settings.deformation_active_key)
            if block:
                block.slider_max = float(settings.deformation_maximum_influence)
        _store_metadata(attached, detached, payload)
    except Exception:
        pass


def _select_key(settings, name):
    attached, _detached = _resolve_pair()
    entry = _metadata(attached).get("keys", {}).get(name, {})
    settings.deformation_active_key = name
    settings.deformation_key_name = name
    settings.deformation_seed_radius = float(entry.get("seedRadius", settings.deformation_seed_radius))
    settings.deformation_seed_depth = float(entry.get("seedDepth", settings.deformation_seed_depth))
    settings.deformation_seed_falloff = float(entry.get("seedFalloff", settings.deformation_seed_falloff))
    settings.deformation_maximum_influence = float(entry.get("maximumInfluence", 1.0))
    settings.deformation_max_vertex_displacement = float(entry.get("maximumDisplacement", 0.045))


def _set_active_object(context, obj):
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _max_displacement(obj, name):
    key = _key(obj, name)
    if not key:
        return 0.0
    basis = obj.data.shape_keys.reference_key
    return max((_local_delta_to_world(obj, key.data[i].co - basis.data[i].co).length for i in range(len(key.data))), default=0.0)


def validate_deformations(require_keys=False):
    attached, detached = _resolve_pair()
    pair = validate_topology_pair(attached, detached)
    errors = list(pair["errors"])
    warnings = []
    payload = _metadata(attached)
    names = _managed_names(attached)
    if require_keys and not names:
        errors.append("No managed deformation keys exist.")
    records = []
    for name in names:
        attached_key = _key(attached, name)
        detached_key = _key(detached, name)
        if attached_key is None or detached_key is None:
            errors.append(f"Managed deformation {name} is missing from one side of the pair.")
            continue
        if len(attached_key.data) != len(detached_key.data):
            errors.append(f"Managed deformation {name} has mismatched point counts.")
            continue
        attached_basis = attached.data.shape_keys.reference_key
        detached_basis = detached.data.shape_keys.reference_key
        max_delta_error = 0.0
        finite = True
        for index in range(len(attached_key.data)):
            delta_a = _local_delta_to_world(attached, attached_key.data[index].co - attached_basis.data[index].co)
            delta_d = _local_delta_to_world(detached, detached_key.data[index].co - detached_basis.data[index].co)
            max_delta_error = max(max_delta_error, (delta_a - delta_d).length)
            finite = finite and all(math.isfinite(value) for value in (*attached_key.data[index].co, *detached_key.data[index].co))
        if not finite:
            errors.append(f"Managed deformation {name} contains non-finite coordinates.")
        if max_delta_error > SYNC_TOLERANCE:
            errors.append(f"Managed deformation {name} detached delta mismatch is {max_delta_error:.8f} m.")
        entry = payload.get("keys", {}).get(name, {})
        maximum = float(entry.get("maximumDisplacement", 0.1))
        measured = _max_displacement(attached, name)
        if measured > maximum + PAIR_TOLERANCE:
            errors.append(f"Managed deformation {name} exceeds its maximum displacement: {measured:.6f} m > {maximum:.6f} m.")
        records.append({
            "name": name,
            "maximumInfluence": float(entry.get("maximumInfluence", attached_key.slider_max)),
            "maximumDisplacement": maximum,
            "measuredMaximumDisplacement": measured,
            "maximumPairDeltaError": max_delta_error,
            "status": entry.get("status", "UNKNOWN"),
        })
    if _key(attached, PREVIEW_KEY_NAME) or _key(detached, PREVIEW_KEY_NAME):
        warnings.append("The temporary seed-preview key is present and will be removed before export.")
    return {
        "status": "PASS" if not errors else "FAIL",
        "schema": DEFORMATION_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": DEFORMATION_BUILD_ID,
        "topologyPair": pair,
        "managedKeyCount": len(names),
        "keys": records,
        "errors": errors,
        "warnings": warnings,
    }


def prepare_for_export():
    clear_seed_preview()
    attached, _detached = _resolve_pair()
    for name in _managed_names(attached):
        sync_key_to_detached(name)
    validation = validate_deformations(require_keys=False)
    if validation["status"] != "PASS":
        raise RuntimeError("Deformation validation failed: " + "; ".join(validation["errors"][:4]))
    return validation


def get_deformation_manifest():
    try:
        attached, detached = _resolve_pair()
    except RuntimeError:
        return {"schema": DEFORMATION_SCHEMA, "authoringVersion": _version_string(), "keys": []}
    payload = _metadata(attached)
    validation = validate_deformations(require_keys=False)
    keys = []
    for name in _managed_names(attached):
        entry = dict(payload.get("keys", {}).get(name, {}))
        entry.update({
            "name": name,
            "attachedObject": attached.name,
            "detachedObject": detached.name,
            "measuredMaximumDisplacement": _max_displacement(attached, name),
        })
        keys.append(entry)
    return {
        "schema": DEFORMATION_SCHEMA,
        "authoringVersion": _version_string(),
        "authoringBuildId": DEFORMATION_BUILD_ID,
        "region": "head",
        "attachedObject": attached.name,
        "detachedObject": detached.name,
        "topologyFingerprint": validation["topologyPair"].get("topologyFingerprint"),
        "keys": keys,
    }


class DAF_OT_create_damage_shape_key(Operator):
    bl_idname = "daf.create_damage_shape_key"
    bl_label = "Create Damage Shape Key"
    bl_description = "Create a protected paired head deformation key on attached and detached meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            name = settings.deformation_key_name.strip()
            template = STANDARD_HEAD_KEYS.get(name, {
                "family": "manual", "side": "configurable", "mirrorPartner": "",
                "seedRadius": settings.deformation_seed_radius,
                "seedDepth": settings.deformation_seed_depth,
                "seedFalloff": settings.deformation_seed_falloff,
                "maximumInfluence": settings.deformation_maximum_influence,
                "maximumDisplacement": settings.deformation_max_vertex_displacement,
            })
            _ensure_key_pair(name, template)
            _select_key(settings, name)
            settings.deformation_status = f"CREATED — {name}"
            self.report({'INFO'}, f"Created paired deformation key {name}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_create_standard_head_deformations(Operator):
    bl_idname = "daf.create_standard_head_deformations"
    bl_label = "Create Standard Head Set"
    bl_description = "Create the four standard head deformation keys for one-click presets or optional artist sculpting"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            attached, detached = _resolve_pair()
            for name, template in STANDARD_HEAD_KEYS.items():
                _ensure_key_pair(name, template)
            _zero_managed_weights(attached, include_preview=True)
            _set_authoring_view(attached, detached, 'ATTACHED')
            _select_key(context.scene.daf_settings, "Head_Dent_Left")
            context.scene.daf_settings.deformation_status = "STANDARD HEAD SET READY"
            self.report({'INFO'}, "Created the four paired standard head deformation keys.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_select_deformation_key(Operator):
    bl_idname = "daf.select_deformation_key"
    bl_label = "Select Deformation Key"
    bl_options = {'REGISTER'}
    key_name: StringProperty()

    def execute(self, context):
        try:
            attached, detached = _resolve_pair()
            _zero_managed_weights(attached, include_preview=True)
            _set_authoring_view(attached, detached, 'ATTACHED')
            _select_key(context.scene.daf_settings, self.key_name)
            key = _key(attached, self.key_name)
            if key and _max_displacement(attached, self.key_name) > 1e-7:
                key.value = min(1.0, key.slider_max)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_solo_deformation_key(Operator):
    bl_idname = "daf.solo_deformation_key"
    bl_label = "Solo Deformation Key"
    bl_options = {'REGISTER'}
    key_name: StringProperty()

    def execute(self, context):
        try:
            attached, _detached = _resolve_pair()
            for name in _managed_names(attached):
                _key(attached, name).value = 1.0 if name == self.key_name else 0.0
            preview = _key(attached, PREVIEW_KEY_NAME)
            if preview:
                preview.value = 0.0
            _select_key(context.scene.daf_settings, self.key_name)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_zero_deformations(Operator):
    bl_idname = "daf.zero_deformations"
    bl_label = "Zero All Deformations"
    bl_description = "Set every managed deformation preview weight to zero"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            attached, _detached = _resolve_pair()
            if attached.data.shape_keys:
                for key in attached.data.shape_keys.key_blocks:
                    if key.name != "Basis":
                        key.value = 0.0
            context.scene.daf_settings.deformation_status = "ALL WEIGHTS ZERO"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_delete_managed_deformation(Operator):
    bl_idname = "daf.delete_managed_deformation"
    bl_label = "Delete Managed Deformation"
    bl_description = "Delete only the selected Forge-managed deformation key from both head objects"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            name = settings.deformation_active_key
            attached, detached = _resolve_pair()
            if name not in _managed_names(attached):
                raise RuntimeError("Select a managed deformation key first.")
            _remove_key(attached, name)
            _remove_key(detached, name)
            payload = _metadata(attached)
            payload.get("keys", {}).pop(name, None)
            _store_metadata(attached, detached, payload)
            settings.deformation_active_key = ""
            settings.deformation_status = f"DELETED — {name}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_capture_deformation_selected_face(Operator):
    bl_idname = "daf.capture_deformation_selected_face"
    bl_label = "Capture Center from Selected Face"
    bl_description = "Capture the center and outward normal of one selected face on DSB_ATTACHED_HEAD"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            attached, _detached = _resolve_pair()
            if context.active_object != attached or context.mode != 'EDIT_MESH':
                raise RuntimeError(f"Select {ATTACHED_HEAD_NAME}, enter Edit Mode, and select one face.")
            mesh = bmesh.from_edit_mesh(attached.data)
            selected = [face for face in mesh.faces if face.select]
            if len(selected) != 1:
                raise RuntimeError("Select exactly one head face.")
            face = selected[0]
            center = face.calc_center_median().copy()
            normal = face.normal.normalized().copy()
            bpy.ops.object.mode_set(mode='OBJECT')
            settings = context.scene.daf_settings
            settings.deformation_seed_center = tuple(center)
            settings.deformation_seed_surface_normal = tuple(normal)
            settings.deformation_seed_center_valid = True
            settings.deformation_status = "SURFACE CENTER CAPTURED"
            refresh_live_seed_preview(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_capture_deformation_cursor(Operator):
    bl_idname = "daf.capture_deformation_cursor"
    bl_label = "Capture Center from 3D Cursor"
    bl_description = "Capture the 3D Cursor in attached-head local coordinates and derive a radial surface direction"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            attached, _detached = _resolve_pair()
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            center = attached.matrix_world.inverted() @ context.scene.cursor.location
            bounds_center = sum((Vector(corner) for corner in attached.bound_box), Vector((0.0, 0.0, 0.0))) / 8.0
            normal = center - bounds_center
            if normal.length_squared <= 1e-12:
                normal = Vector((0, 0, 1))
            settings = context.scene.daf_settings
            settings.deformation_seed_center = tuple(center)
            settings.deformation_seed_surface_normal = tuple(normal.normalized())
            settings.deformation_seed_center_valid = True
            settings.deformation_status = "CURSOR CENTER CAPTURED"
            refresh_live_seed_preview(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_preview_deformation_seed(Operator):
    bl_idname = "daf.preview_deformation_seed"
    bl_label = "Preview Procedural Seed"
    bl_description = "Generate or refresh the temporary live seed key without editing the active deformation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            result = preview_seed(context)
            self.report({'INFO'}, f"Previewed the seed on {result['vertexCount']} head vertices.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_commit_deformation_seed(Operator):
    bl_idname = "daf.commit_deformation_seed"
    bl_label = "Commit Seed to Active Key"
    bl_description = "Copy the temporary seed into the active permanent paired deformation key"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            name = settings.deformation_active_key
            if not name:
                raise RuntimeError("Select or create a permanent deformation key first.")
            attached, detached = _resolve_pair()
            if _key(attached, PREVIEW_KEY_NAME) is None:
                preview_seed(context)
            preview = _key(attached, PREVIEW_KEY_NAME)
            target = _key(attached, name)
            if target is None:
                raise RuntimeError(f"The active deformation key {name} does not exist.")
            _set_key_coordinates(target, [point.co.copy() for point in preview.data])
            sync_key_to_detached(name)
            payload = _metadata(attached)
            entry = payload["keys"][name]
            entry.update({
                "status": "SEEDED",
                "seedRadius": float(settings.deformation_seed_radius),
                "seedDepth": float(settings.deformation_seed_depth),
                "seedFalloff": float(settings.deformation_seed_falloff),
                "seedDirectionMode": settings.deformation_seed_direction_mode,
                "seedCenter": [float(value) for value in settings.deformation_seed_center],
                "seedSurfaceNormal": [float(value) for value in settings.deformation_seed_surface_normal],
                "seamProtection": float(settings.deformation_seed_seam_protection),
                "maximumInfluence": float(settings.deformation_maximum_influence),
                "maximumDisplacement": float(settings.deformation_max_vertex_displacement),
            })
            _store_metadata(attached, detached, payload)
            clear_seed_preview()
            _zero_managed_weights(attached)
            target.value = min(1.0, target.slider_max)
            _set_authoring_view(attached, detached, 'ATTACHED')
            settings.deformation_status = f"PRESET COMMITTED — {name} / {_max_displacement(attached, name):.3f} m"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_clear_deformation_seed(Operator):
    bl_idname = "daf.clear_deformation_seed"
    bl_label = "Clear Uncommitted Seed"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clear_seed_preview()
        context.scene.daf_settings.deformation_status = "SEED PREVIEW CLEARED"
        return {'FINISHED'}


class DAF_OT_begin_deformation_sculpt(Operator):
    bl_idname = "daf.begin_deformation_sculpt"
    bl_label = "Begin Sculpt"
    bl_description = "Solo the active permanent key and enter Sculpt Mode on the attached head"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            name = settings.deformation_active_key
            attached, _detached = _resolve_pair()
            if name not in _managed_names(attached):
                raise RuntimeError("Select a managed deformation key first.")
            clear_seed_preview()
            _set_active_object(context, attached)
            keys = attached.data.shape_keys.key_blocks
            attached.active_shape_key_index = keys.find(name)
            for managed in _managed_names(attached):
                _key(attached, managed).value = 1.0 if managed == name else 0.0
            attached.show_only_shape_key = True
            bpy.ops.object.mode_set(mode='SCULPT')
            settings.deformation_status = f"SCULPTING — {name}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_finish_deformation_sculpt(Operator):
    bl_idname = "daf.finish_deformation_sculpt"
    bl_label = "Finish Sculpt & Sync"
    bl_description = "Leave Sculpt Mode, copy exact vertex-index deltas to the detached head, and validate limits"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            name = settings.deformation_active_key
            attached, detached = _resolve_pair()
            attached.show_only_shape_key = False
            sync_key_to_detached(name)
            payload = _metadata(attached)
            payload["keys"][name]["status"] = "SCULPTED"
            payload["keys"][name]["maximumInfluence"] = float(settings.deformation_maximum_influence)
            payload["keys"][name]["maximumDisplacement"] = float(settings.deformation_max_vertex_displacement)
            _store_metadata(attached, detached, payload)
            validation = validate_deformations(require_keys=True)
            settings.last_deformation_validation = validation["status"]
            if validation["status"] != "PASS":
                raise RuntimeError("; ".join(validation["errors"][:4]))
            settings.deformation_status = f"SCULPT SYNCED — {name}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_create_mirrored_deformation(Operator):
    bl_idname = "daf.create_mirrored_deformation"
    bl_label = "Create Mirrored Shape Key"
    bl_description = "Mirror the active deformation across local X using Blender topology mirror, then synchronize the detached head"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            source_name = settings.deformation_active_key
            attached, detached = _resolve_pair()
            source = _key(attached, source_name)
            if source is None or source_name not in _managed_names(attached):
                raise RuntimeError("Select a managed source deformation first.")
            source_entry = _metadata(attached)["keys"].get(source_name, {})
            target_name = source_entry.get("mirrorPartner") or (source_name + "_Mirrored")
            target_entry = dict(source_entry)
            target_entry["name"] = target_name
            target_entry["side"] = "right" if source_entry.get("side") == "left" else "left" if source_entry.get("side") == "right" else "mirrored"
            target_entry["mirrorPartner"] = source_name
            _ensure_key_pair(target_name, target_entry)
            target = _key(attached, target_name)
            _set_key_coordinates(target, [point.co.copy() for point in source.data])
            _set_active_object(context, attached)
            attached.active_shape_key_index = attached.data.shape_keys.key_blocks.find(target_name)
            result = bpy.ops.object.shape_key_mirror(use_topology=True)
            if 'FINISHED' not in result:
                raise RuntimeError("Blender topology mirror did not finish.")
            sync_key_to_detached(target_name)
            payload = _metadata(attached)
            payload["keys"][target_name].update(target_entry)
            payload["keys"][target_name]["status"] = "MIRRORED"
            _store_metadata(attached, detached, payload)
            _select_key(settings, target_name)
            settings.deformation_status = f"MIRRORED — {source_name} → {target_name}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_build_active_preset(Operator):
    bl_idname = "daf.build_active_deformation_preset"
    bl_label = "Build Active Preset"
    bl_description = "Generate, commit, solo, and display a finished procedural starting deformation in one click"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            if not settings.deformation_active_key:
                raise RuntimeError("Select a managed deformation key first.")
            preview_seed(context)
            result = bpy.ops.daf.commit_deformation_seed()
            if 'FINISHED' not in result:
                raise RuntimeError("The procedural preset could not be committed.")
            settings.deformation_status = f"OUT-OF-BOX PRESET READY — {settings.deformation_active_key}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_show_deformation_attached(Operator):
    bl_idname = "daf.show_deformation_attached"
    bl_label = "Show Attached"
    bl_options = {'REGISTER'}

    def execute(self, context):
        attached, detached = _resolve_pair()
        _set_authoring_view(attached, detached, 'ATTACHED')
        _set_active_object(context, attached)
        context.scene.daf_settings.deformation_status = "VIEWING ATTACHED HEAD"
        return {'FINISHED'}


class DAF_OT_show_deformation_detached(Operator):
    bl_idname = "daf.show_deformation_detached"
    bl_label = "Show Detached"
    bl_options = {'REGISTER'}

    def execute(self, context):
        attached, detached = _resolve_pair()
        _set_authoring_view(attached, detached, 'DETACHED')
        _set_active_object(context, detached)
        context.scene.daf_settings.deformation_status = "VIEWING DETACHED HEAD"
        return {'FINISHED'}


class DAF_OT_show_deformation_overlay(Operator):
    bl_idname = "daf.show_deformation_overlay"
    bl_label = "Show Both"
    bl_options = {'REGISTER'}

    def execute(self, context):
        attached, detached = _resolve_pair()
        _set_authoring_view(attached, detached, 'BOTH')
        context.scene.daf_settings.deformation_status = "PAIR OVERLAY ENABLED"
        return {'FINISHED'}


class DAF_OT_validate_deformations(Operator):
    bl_idname = "daf.validate_deformations"
    bl_label = "Validate Deformations"
    bl_description = "Validate topology correspondence, paired deltas, finite coordinates, and displacement limits"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            validation = validate_deformations(require_keys=True)
            settings = context.scene.daf_settings
            settings.last_deformation_validation = validation["status"]
            settings.deformation_status = "VALIDATION " + validation["status"]
            if validation["status"] == "PASS":
                self.report({'INFO'}, f"Validated {validation['managedKeyCount']} paired deformation keys.")
                return {'FINISHED'}
            self.report({'ERROR'}, "; ".join(validation["errors"][:4]))
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def draw_panel(box, context, settings):
    try:
        attached, detached = _resolve_pair()
        contract = validate_topology_pair(attached, detached)
        icon = 'CHECKMARK' if contract["status"] == "PASS" else 'ERROR'
        box.label(text=f"Pair: {attached.name} ↔ {detached.name}", icon=icon)
        box.label(text=f"Topology Pair: {contract['status']} — {contract['attachedVertexCount']} vertices")
    except Exception as exc:
        box.label(text=str(exc), icon='ERROR')
        box.label(text="Build the protected v3.8 Damage Asset first", icon='LOCKED')
        return

    status = box.box()
    status.label(text="Status: " + settings.deformation_status, icon='INFO')
    status.label(text="Validation: " + settings.last_deformation_validation)

    library = box.box()
    library.label(text="Deformation Library", icon='SHAPEKEY_DATA')
    library.prop(settings, "deformation_region")
    library.prop(settings, "deformation_key_name")
    row = library.row(align=True)
    row.operator("daf.create_damage_shape_key", text="Create Damage Shape Key", icon='ADD')
    row.operator("daf.create_standard_head_deformations", text="Create Standard Head Set", icon='PRESET')

    names = _managed_names(attached)
    if names:
        for name in names:
            key = _key(attached, name)
            row = library.row(align=True)
            select = row.operator("daf.select_deformation_key", text=name, depress=settings.deformation_active_key == name)
            select.key_name = name
            row.prop(key, "value", text="", slider=True)
            solo = row.operator("daf.solo_deformation_key", text="Solo")
            solo.key_name = name
    else:
        library.label(text="No managed deformation keys yet", icon='INFO')

    row = library.row(align=True)
    row.operator("daf.zero_deformations", text="Zero All", icon='LOOP_BACK')
    row.operator("daf.delete_managed_deformation", text="Delete Active", icon='TRASH')
    row.operator("daf.create_mirrored_deformation", text="Mirror Active", icon='MOD_MIRROR')

    active = box.box()
    active.label(text="Active Key: " + (settings.deformation_active_key or "NONE"), icon='KEY_HLT')
    row = active.row(align=True)
    row.operator("daf.show_deformation_attached", text="Attached", icon='OUTLINER_OB_MESH')
    row.operator("daf.show_deformation_detached", text="Detached", icon='PHYSICS')
    row.operator("daf.show_deformation_overlay", text="Both", icon='HIDE_OFF')
    active.prop(settings, "deformation_maximum_influence")
    active.prop(settings, "deformation_max_vertex_displacement")

    seed = box.box()
    seed.label(text="Procedural Seed — Starting Point Only", icon='MOD_DISPLACE')
    seed.prop(settings, "deformation_auto_preview")
    seed.prop(settings, "deformation_seed_radius")
    seed.prop(settings, "deformation_seed_depth")
    seed.prop(settings, "deformation_seed_falloff")
    seed.prop(settings, "deformation_seed_direction_mode")
    if settings.deformation_seed_direction_mode == 'CUSTOM_VECTOR':
        seed.prop(settings, "deformation_seed_custom_direction")
    seed.prop(settings, "deformation_seed_seam_protection")
    row = seed.row(align=True)
    row.operator("daf.capture_deformation_selected_face", text="Capture Selected Face", icon='FACESEL')
    row.operator("daf.capture_deformation_cursor", text="Capture 3D Cursor", icon='PIVOT_CURSOR')
    if settings.deformation_seed_center_valid:
        seed.label(text="Center captured", icon='CHECKMARK')
    else:
        seed.label(text="Capture a surface center", icon='ERROR')
    seed.operator("daf.build_active_deformation_preset", text="BUILD ACTIVE PRESET", icon='MOD_DISPLACE')
    row = seed.row(align=True)
    row.operator("daf.preview_deformation_seed", text="Preview Seed", icon='HIDE_OFF')
    row.operator("daf.commit_deformation_seed", text="Commit Seed", icon='CHECKMARK')
    row.operator("daf.clear_deformation_seed", text="Clear Seed", icon='X')
    seed.label(text="Seed sizes are measured in world meters, independent of object scale", icon='WORLD')

    sculpt = box.box()
    sculpt.label(text="Manual Sculpt Finish", icon='SCULPTMODE_HLT')
    row = sculpt.row(align=True)
    row.operator("daf.begin_deformation_sculpt", text="Begin Sculpt", icon='SCULPTMODE_HLT')
    row.operator("daf.finish_deformation_sculpt", text="Finish Sculpt & Sync", icon='FILE_TICK')
    sculpt.label(text="Sculpting is optional; presets are now intended to read clearly out of the box", icon='INFO')

    box.operator("daf.validate_deformations", text="Validate Morph Targets", icon='CHECKMARK')
    box.label(text="Attached and detached head deltas stay vertex-index synchronized", icon='LINKED')
    box.label(text="Source mesh and rig remain protected", icon='LOCKED')


CLASSES = (
    DAF_OT_create_damage_shape_key,
    DAF_OT_create_standard_head_deformations,
    DAF_OT_select_deformation_key,
    DAF_OT_solo_deformation_key,
    DAF_OT_zero_deformations,
    DAF_OT_delete_managed_deformation,
    DAF_OT_capture_deformation_selected_face,
    DAF_OT_capture_deformation_cursor,
    DAF_OT_preview_deformation_seed,
    DAF_OT_commit_deformation_seed,
    DAF_OT_clear_deformation_seed,
    DAF_OT_begin_deformation_sculpt,
    DAF_OT_finish_deformation_sculpt,
    DAF_OT_create_mirrored_deformation,
    DAF_OT_build_active_preset,
    DAF_OT_show_deformation_attached,
    DAF_OT_show_deformation_detached,
    DAF_OT_show_deformation_overlay,
    DAF_OT_validate_deformations,
)
