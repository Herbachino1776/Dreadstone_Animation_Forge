"""Blender authoring adapter for target-constrained Offensive Motion Studio."""

from __future__ import annotations

import json
import math
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone

import bpy
from bpy.app.handlers import persistent
from bpy.props import StringProperty
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import animation_library, attachment_sockets, offensive_actions
from . import offensive_motion as motion
from .anatomy import blender_adapter as anatomy_blender
from .anatomy import skin_and_bones


MOTION_STUDIO_COLLECTION = "DSB_OFFENSIVE_MOTION_STUDIO"
MOTION_STUDIO_STATE_PROPERTY = "dsb_offensive_motion_studio_session_json"
MOTION_STUDIO_HELPER_ROLE = "offensive_motion_studio_helper"
MOTION_BYPASS_PROPERTY = "dsb_offensive_motion_bypass_json"
MOTION_BYPASS_SCHEMA = "dreadstone.offensive_motion_bypass.v1"
PREVIEW_WEAPON_ROLES = frozenset({
    "PROXY_GRIP",
    "WEAPON_PROXY",
    "PROXY_STRIKE_SEGMENT",
    "PROXY_CONTACT_POINT",
    "PROXY_HEAD",
    "PROXY_TIP",
    "PROXY_GUARD",
})
_SETTINGS_GUARD = False


def _id_value(value):
    if hasattr(value, "to_dict"):
        return {str(key): _id_value(item) for key, item in value.to_dict().items()}
    if hasattr(value, "to_list"):
        return [_id_value(item) for item in value.to_list()]
    if isinstance(value, (list, tuple)):
        return [_id_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _owned_objects(role=None):
    values = [obj for obj in bpy.data.objects if bool(obj.get("dsb_motion_studio_owned", False))]
    if role is not None:
        values = [obj for obj in values if str(obj.get("dsb_motion_studio_role", "")) == str(role)]
    return values


def _collection():
    collection = bpy.data.collections.get(MOTION_STUDIO_COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new(MOTION_STUDIO_COLLECTION)
    scene = bpy.context.scene
    if collection.name not in {child.name for child in scene.collection.children}:
        scene.collection.children.link(collection)
    collection.hide_render = True
    return collection


def _stamp_helper(obj, role, action=None):
    obj["dsb_motion_studio_owned"] = True
    obj["dsb_motion_studio_role"] = str(role)
    obj["dsb_motion_studio_action"] = action.name if action is not None else ""
    obj["dsb_preview_only"] = True
    obj["dsb_damage_role"] = MOTION_STUDIO_HELPER_ROLE
    obj.hide_render = True
    obj.show_in_front = True
    return obj


def _remove_object(obj):
    data = getattr(obj, "data", None)
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is None or getattr(data, "users", 1) > 0:
        return
    if isinstance(data, bpy.types.Curve):
        bpy.data.curves.remove(data)
    elif isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)


def remove_helpers(*, roles=None):
    allowed = set(roles or ()) if roles is not None else None
    removed = 0
    for obj in list(_owned_objects()):
        if allowed is not None and str(obj.get("dsb_motion_studio_role", "")) not in allowed:
            continue
        _remove_object(obj)
        removed += 1
    collection = bpy.data.collections.get(MOTION_STUDIO_COLLECTION)
    if collection is not None and not collection.objects and not collection.children:
        bpy.data.collections.remove(collection)
    return removed


def _empty(name, role, *, action=None, display="PLAIN_AXES", size=0.12, color=(1.0, 1.0, 1.0, 1.0)):
    obj = bpy.data.objects.new(name, None)
    _collection().objects.link(obj)
    obj.empty_display_type = display
    obj.empty_display_size = float(size)
    obj.color = color
    obj.show_name = True
    return _stamp_helper(obj, role, action)


def _curve(name, role, splines, *, action=None, bevel=0.006, color=(1.0, 1.0, 1.0, 1.0), cyclic=False):
    data = bpy.data.curves.new(name + "_DATA", "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 1
    data.bevel_depth = float(bevel)
    data.bevel_resolution = 1
    for points in splines:
        spline = data.splines.new("POLY")
        spline.points.add(max(0, len(points) - 1))
        for point, value in zip(spline.points, points):
            point.co = (*[float(component) for component in value], 1.0)
        spline.use_cyclic_u = bool(cyclic)
    obj = bpy.data.objects.new(name, data)
    _collection().objects.link(obj)
    obj.color = color
    return _stamp_helper(obj, role, action)


def _wire_mesh(name, role, vertices, edges, *, action=None, color=(1.0, 1.0, 1.0, 1.0)):
    data = bpy.data.meshes.new(name + "_DATA")
    data.from_pydata([tuple(map(float, value)) for value in vertices], list(edges), [])
    data.update()
    obj = bpy.data.objects.new(name, data)
    _collection().objects.link(obj)
    obj.display_type = "WIRE"
    obj.color = color
    return _stamp_helper(obj, role, action)


def _parent_local(obj, parent, matrix=None):
    obj.parent = parent
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = matrix.copy() if matrix is not None else Matrix.Identity(4)
    return obj


def _basis_from_y(axis):
    y_axis = Vector(axis).normalized()
    # Global X is stable through ordinary overhead arcs, including the moment
    # the weapon axis passes near vertical. The old Z reference switched basis
    # branches there and could inject a one-frame wrist roll.
    reference = Vector((1.0, 0.0, 0.0))
    if abs(y_axis.dot(reference)) > 0.94:
        reference = Vector((0.0, 0.0, 1.0))
    x_axis = y_axis.cross(reference).normalized()
    z_axis = x_axis.cross(y_axis).normalized()
    return Matrix((x_axis, y_axis, z_axis)).transposed()


def _pose_matrix(position, axis):
    matrix = _basis_from_y(axis).to_4x4()
    matrix.translation = Vector(position)
    return matrix


def _circle_points(radius, z, *, segments=24, plane="XY"):
    points = []
    for index in range(segments):
        angle = (2.0 * math.pi * index) / segments
        first = math.cos(angle) * radius
        second = math.sin(angle) * radius
        if plane == "XY":
            points.append((first, second, z))
        elif plane == "XZ":
            points.append((first, z, second))
        else:
            points.append((z, first, second))
    return points


def _capsule_splines(radius, half_height, center_z):
    bottom = center_z - half_height
    top = center_z + half_height
    splines = [
        _circle_points(radius, bottom),
        _circle_points(radius, top),
        _circle_points(radius, bottom, plane="XZ"),
        _circle_points(radius, top, plane="XZ"),
    ]
    for angle in (0.0, math.pi * 0.5, math.pi, math.pi * 1.5):
        x = math.cos(angle) * radius
        y = math.sin(angle) * radius
        splines.append([(x, y, bottom), (x, y, top)])
    # Two orthogonal meridian outlines show the exact rounded capsule caps,
    # matching the segment-plus-radius math used by validation.
    for plane in ("XZ", "YZ"):
        meridian = []
        for index in range(13):
            angle = math.pi + (math.pi * index / 12.0)
            radial = math.cos(angle) * radius
            z = bottom + math.sin(angle) * radius
            meridian.append((radial, 0.0, z) if plane == "XZ" else (0.0, radial, z))
        meridian.extend([
            (radius, 0.0, top) if plane == "XZ" else (0.0, radius, top),
        ])
        for index in range(13):
            angle = math.pi * index / 12.0
            radial = math.cos(angle) * radius
            z = top + math.sin(angle) * radius
            meridian.append((radial, 0.0, z) if plane == "XZ" else (0.0, radial, z))
        meridian.append((-radius, 0.0, bottom) if plane == "XZ" else (0.0, -radius, bottom))
        splines.append(meridian)
    return splines


def _helper_by_role(role):
    values = _owned_objects(role)
    return values[0] if values else None


def _target_root_transform(armature, target):
    return Matrix.Translation((
        float(target["lateralOffsetMeters"]),
        float(target["distanceMeters"]),
        0.0,
    ))


def _build_target_helpers(armature, action, recipe):
    target = recipe["target"]
    root = _empty("DSB_MS_TARGET_ROOT", "TARGET_ROOT", action=action, display="ARROWS", size=0.18, color=(0.95, 0.45, 0.10, 1.0))
    _parent_local(root, armature, _target_root_transform(armature, target))
    root["dsb_motion_target_zone"] = target["zone"]
    height = float(target["heightMeters"])
    ground = _curve(
        "DSB_MS_TARGET_GROUND",
        "TARGET_GROUND",
        [_circle_points(max(0.24, float(target["torsoRadiusMeters"]) * 1.35), 0.0, segments=32)],
        action=action,
        bevel=0.004,
        color=(0.35, 0.35, 0.35, 1.0),
        cyclic=True,
    )
    _parent_local(ground, root)
    body = _curve(
        "DSB_MS_TARGET_BODY_CAPSULE",
        "TARGET_BODY",
        _capsule_splines(float(target["torsoRadiusMeters"]) * 1.08, height * 0.30, height * 0.52),
        action=action,
        bevel=0.003,
        color=(0.30, 0.45, 0.55, 1.0),
        cyclic=True,
    )
    _parent_local(body, root)
    zones = (
        ("HEAD", height * 0.90, "SPHERE"),
        ("UPPER_TORSO", height * 0.72, "CAPSULE"),
        ("CENTER_MASS", height * 0.58, "CAPSULE"),
        ("LOW_TORSO", height * 0.44, "CAPSULE"),
    )
    for zone, center_z, shape in zones:
        selected = zone == target["zone"]
        color = (1.0, 0.18, 0.05, 1.0) if selected else (0.20, 0.65, 0.85, 1.0)
        if shape == "SPHERE":
            helper = _empty(
                "DSB_MS_TARGET_ZONE_" + zone,
                "TARGET_ZONE_" + zone,
                action=action,
                display="SPHERE",
                size=float(target["headRadiusMeters"]),
                color=color,
            )
            _parent_local(helper, root, Matrix.Translation((0.0, 0.0, center_z)))
        else:
            helper = _curve(
                "DSB_MS_TARGET_ZONE_" + zone,
                "TARGET_ZONE_" + zone,
                _capsule_splines(
                    float(target["torsoRadiusMeters"]),
                    float(target["zoneHalfHeightMeters"]),
                    center_z,
                ),
                action=action,
                bevel=0.006 if selected else 0.003,
                color=color,
                cyclic=True,
            )
            _parent_local(helper, root)
    if target["zone"] == "CUSTOM":
        helper = _empty(
            "DSB_MS_TARGET_ZONE_CUSTOM",
            "TARGET_ZONE_CUSTOM",
            action=action,
            display="SPHERE",
            size=float(target["customRadiusMeters"]),
            color=(1.0, 0.18, 0.05, 1.0),
        )
        _parent_local(helper, root, Matrix.Translation((0.0, 0.0, float(target["customHeightMeters"]))))
    center = motion.target_zone_center(target)
    marker = _empty("DSB_MS_TARGET_CENTER", "TARGET_CENTER", action=action, display="SPHERE", size=0.045, color=(1.0, 1.0, 0.0, 1.0))
    _parent_local(marker, armature, Matrix.Translation(center))
    proxy_radius = float(recipe["proxy"]["headRadiusMeters"] if recipe["proxy"]["class"] == "ONE_HAND_BLUNT" else 0.015)
    anchor = motion.target_contact_anchor(
        target,
        recipe["trajectory"].get("contactAnchor", "CENTER"),
        recipe["trajectory"]["expectedDirectionLocal"],
        proxy_radius=proxy_radius,
    )
    contact_marker = _empty(
        "DSB_MS_TARGET_CONTACT_ANCHOR",
        "TARGET_CONTACT_ANCHOR",
        action=action,
        display="CUBE",
        size=0.065,
        color=(1.0, 0.78, 0.02, 1.0),
    )
    _parent_local(contact_marker, armature, Matrix.Translation(anchor))
    contact_marker["dsb_motion_contact_anchor"] = str(recipe["trajectory"].get("contactAnchor", "CENTER"))
    return root


def _build_control_helpers(armature, action, recipe):
    for control in recipe["trajectory"]["controls"]:
        helper = _empty(
            "DSB_MS_CONTROL_" + control["id"],
            "CONTROL_" + control["id"],
            action=action,
            display="ARROWS",
            size=0.16 if control["id"] == "CONTACT" else 0.11,
            color=(1.0, 0.10, 0.02, 1.0) if control["id"] == "CONTACT" else (0.95, 0.55, 0.10, 1.0),
        )
        helper["dsb_motion_control_id"] = control["id"]
        _parent_local(helper, armature, _pose_matrix(control["contactPointLocal"], control["weaponAxisLocal"]))


def _socket_context(armature, role):
    helpers = [
        obj
        for obj in bpy.data.objects
        if bool(obj.get("dsb_attachment_socket_owned", False))
    ]
    socket = next((value for value in helpers if str(value.get("dsb_attachment_socket_role", "")) == str(role)), None)
    if (
        socket is None
        or socket.parent != armature
        or socket.parent_type != "BONE"
        or socket.parent_bone != str(socket.get("dsb_attachment_socket_parent_bone", ""))
    ):
        helpers = attachment_sockets.ensure_standard_sockets(armature)
        socket = next((value for value in helpers if str(value.get("dsb_attachment_socket_role", "")) == str(role)), None)
    if socket is None:
        raise RuntimeError(f"Motion Studio requires runtime socket role {role}.")
    mapping = skin_and_bones.forge_mapping(armature)
    hand_role = "hand_r" if role == "MAIN_HAND_R" else "hand_l"
    hand_name = mapping.get(hand_role, "")
    hand = armature.pose.bones.get(hand_name)
    if hand is None:
        raise RuntimeError(f"Motion Studio cannot resolve canonical {hand_role}.")
    # Bone-parented Blender objects carry an additional bone-tail convention in
    # their object transform.  Computing this from evaluated world matrices made
    # the calibration depend on whichever Action/frame happened to be active;
    # on Cinderbound it inverted the socket by roughly 180 degrees.  The helper
    # transform Blender stores for a bone parent is the stable authored local
    # relationship we need for every solve and every frame.
    socket_local = socket.matrix_basis.copy()
    return socket, hand, socket_local


def _build_proxy_helpers(armature, action, recipe):
    proxy = recipe["proxy"]
    role = "MAIN_HAND_R" if recipe["solver"]["arm"] == "RIGHT" else "MAIN_HAND_L"
    socket, _hand, _local = _socket_context(armature, role)
    grip = _empty("DSB_MS_PROXY_GRIP", "PROXY_GRIP", action=action, display="CIRCLE", size=0.055, color=(0.9, 0.9, 0.9, 1.0))
    _parent_local(grip, socket)
    shaft = _curve(
        "DSB_MS_WEAPON_PROXY",
        "WEAPON_PROXY",
        [[(0.0, 0.0, 0.0), (0.0, float(proxy["lengthMeters"]), 0.0)]],
        action=action,
        bevel=0.018 if proxy["class"] == "ONE_HAND_BLUNT" else 0.012,
        color=(0.85, 0.85, 0.90, 1.0),
    )
    _parent_local(shaft, socket)
    strike = _curve(
        "DSB_MS_PROXY_STRIKE_SEGMENT",
        "PROXY_STRIKE_SEGMENT",
        [[
            (0.0, float(proxy["strikeSegmentStartMeters"]), 0.0),
            (0.0, float(proxy["strikeSegmentEndMeters"]), 0.0),
        ]],
        action=action,
        bevel=0.026,
        color=(1.0, 0.15, 0.02, 1.0),
    )
    _parent_local(strike, socket)
    contact = _empty(
        "DSB_MS_PROXY_CONTACT_POINT",
        "PROXY_CONTACT_POINT",
        action=action,
        display="SPHERE",
        size=max(0.035, float(proxy["headRadiusMeters"])),
        color=(1.0, 0.02, 0.02, 1.0),
    )
    _parent_local(contact, socket, Matrix.Translation((0.0, float(proxy["gripToContactMeters"]), 0.0)))
    if proxy["class"] == "ONE_HAND_BLUNT":
        head = _empty(
            "DSB_MS_PROXY_HEAD",
            "PROXY_HEAD",
            action=action,
            display="SPHERE",
            size=float(proxy["headRadiusMeters"]),
            color=(0.55, 0.58, 0.62, 1.0),
        )
        _parent_local(head, socket, Matrix.Translation((0.0, float(proxy["gripToContactMeters"]), 0.0)))
    else:
        tip = _empty(
            "DSB_MS_PROXY_TIP",
            "PROXY_TIP",
            action=action,
            display="CONE",
            size=0.05,
            color=(1.0, 0.72, 0.05, 1.0),
        )
        _parent_local(tip, socket, Matrix.Translation((0.0, float(proxy["lengthMeters"]), 0.0)))
        guard = _curve(
            "DSB_MS_PROXY_GUARD",
            "PROXY_GUARD",
            [[(-0.09, 0.035, 0.0), (0.09, 0.035, 0.0)]],
            action=action,
            bevel=0.009,
            color=(0.70, 0.55, 0.18, 1.0),
        )
        _parent_local(guard, socket)
    return socket


def build_preview_weapon(armature, action, recipe):
    """Replace the visible hand-held proxy with the recipe's current weapon."""

    remove_helpers(roles=PREVIEW_WEAPON_ROLES)
    _build_proxy_helpers(armature, action, recipe)
    _store_session(
        action,
        recipe,
        helpers_required=True,
        editable_controls_required=False,
        helper_mode="WEAPON_PREVIEW",
    )
    return [
        obj
        for obj in _owned_objects()
        if str(obj.get("dsb_motion_studio_role", "")) in PREVIEW_WEAPON_ROLES
    ]


def _build_trajectory_geometry(armature, action, recipe):
    geometry = motion.trajectory_geometry(
        recipe["trajectory"]["family"],
        motion.target_zone_center(recipe["target"]),
        recipe["trajectory"]["expectedDirectionLocal"],
    )
    center = Vector(geometry["point"])
    if geometry["type"] == "LINE":
        direction = Vector(geometry["direction"]).normalized()
        obj = _curve(
            "DSB_MS_STRIKE_LINE",
            "STRIKE_GEOMETRY",
            [[center - direction * 1.2, center + direction * 1.2]],
            action=action,
            bevel=0.005,
            color=(0.75, 0.20, 1.0, 1.0),
        )
        _parent_local(obj, armature)
        return obj
    if geometry["type"] != "PLANE":
        return None
    normal = Vector(geometry["normal"]).normalized()
    first = Vector((1.0, 0.0, 0.0))
    if abs(normal.dot(first)) > 0.90:
        first = Vector((0.0, 1.0, 0.0))
    first = (first - normal * normal.dot(first)).normalized()
    second = normal.cross(first).normalized()
    extent = 0.95
    vertices = [center + first * sx * extent + second * sy * extent for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    obj = _wire_mesh(
        "DSB_MS_STRIKE_PLANE",
        "STRIKE_GEOMETRY",
        vertices,
        ((0, 1), (1, 2), (2, 3), (3, 0), (0, 2), (1, 3)),
        action=action,
        color=(0.75, 0.20, 1.0, 1.0),
    )
    _parent_local(obj, armature)
    return obj


def _build_trail_helpers(armature, action, samples, validation=None):
    remove_helpers(roles={
        "TRAIL_WINDUP", "TRAIL_ACTIVE", "TRAIL_RECOVERY", "TRAIL_MARKER_ACTIVE_START",
        "TRAIL_MARKER_ACTIVE_END", "TRAIL_MARKER_CONTACT", "TRAIL_MARKER_CLOSEST",
    })
    groups = {
        "WINDUP": ("TRAIL_WINDUP", (0.20, 0.45, 1.0, 1.0)),
        "ACTIVE": ("TRAIL_ACTIVE", (1.0, 0.08, 0.02, 1.0)),
        "RECOVERY": ("TRAIL_RECOVERY", (0.25, 0.85, 0.30, 1.0)),
    }
    for phase, (role, color) in groups.items():
        points = [sample["contactPointLocal"] for sample in samples if sample["phase"] == phase]
        if len(points) < 2:
            continue
        curve = _curve("DSB_MS_" + role, role, [points], action=action, bevel=0.008 if phase == "ACTIVE" else 0.005, color=color)
        _parent_local(curve, armature)
    active = [sample for sample in samples if sample["phase"] == "ACTIVE"]
    for suffix, sample, color in (
        ("ACTIVE_START", active[0] if active else None, (1.0, 0.55, 0.0, 1.0)),
        ("ACTIVE_END", active[-1] if active else None, (1.0, 0.25, 0.0, 1.0)),
    ):
        if sample is None:
            continue
        marker = _empty("DSB_MS_TRAIL_" + suffix, "TRAIL_MARKER_" + suffix, action=action, display="SPHERE", size=0.035, color=color)
        _parent_local(marker, armature, Matrix.Translation(sample["contactPointLocal"]))
    recipe = motion.read_motion_recipe(action)
    if recipe is not None:
        contact = min(samples, key=lambda sample: abs(float(sample["frame"]) - float(recipe["contactFrame"])))
        marker = _empty("DSB_MS_CONTACT_MARKER", "TRAIL_MARKER_CONTACT", action=action, display="SPHERE", size=0.06, color=(1.0, 1.0, 0.0, 1.0))
        _parent_local(marker, armature, Matrix.Translation(contact["contactPointLocal"]))
    if validation and validation.get("closestWeaponPointLocal"):
        marker = _empty("DSB_MS_CLOSEST_APPROACH", "TRAIL_MARKER_CLOSEST", action=action, display="SPHERE", size=0.045, color=(1.0, 0.0, 1.0, 1.0))
        _parent_local(marker, armature, Matrix.Translation(validation["closestWeaponPointLocal"]))


def build_helpers(
    armature,
    action,
    recipe,
    *,
    samples=None,
    validation=None,
    include_controls=True,
):
    """Build optional review geometry, keeping the simple workflow uncluttered.

    The seven orange trajectory controls are useful while deliberately editing
    an expert recipe, but they made every ordinary attack create a small scene
    graph of its own.  Simple builds therefore create no helpers at all; the
    CONTACT review action asks for this reduced target/proxy/trail set on
    demand.  Expert repair continues to request the editable controls.
    """

    remove_helpers()
    _build_target_helpers(armature, action, recipe)
    if include_controls:
        _build_control_helpers(armature, action, recipe)
    _build_proxy_helpers(armature, action, recipe)
    _build_trajectory_geometry(armature, action, recipe)
    if samples:
        _build_trail_helpers(armature, action, samples, validation)
    _store_session(
        action,
        recipe,
        helpers_required=True,
        editable_controls_required=include_controls,
        helper_mode="REVIEW",
    )
    settings = getattr(bpy.context.scene, "daf_settings", None)
    if settings is not None:
        motion_display_updated(settings, bpy.context)
    return _owned_objects()


def _store_session(
    action,
    recipe,
    scene=None,
    *,
    helpers_required=None,
    editable_controls_required=None,
    helper_mode=None,
):
    scene = scene or bpy.context.scene
    if helpers_required is None:
        helpers_required = bool(_owned_objects())
    if editable_controls_required is None:
        editable_controls_required = any(
            str(obj.get("dsb_motion_studio_role", "")).startswith("CONTROL_")
            for obj in _owned_objects()
        )
    payload = {
        "schema": "dreadstone.offensive_motion_studio_session.v1",
        "actionName": action.name,
        "motionMasterId": recipe["motionMasterId"],
        "helpersRequired": bool(helpers_required),
        "editableControlsRequired": bool(editable_controls_required),
        "helperMode": str(helper_mode or "REVIEW"),
    }
    scene[MOTION_STUDIO_STATE_PROPERTY] = motion.stable_json(payload)
    return payload


def _session(scene=None):
    scene = scene or getattr(bpy.context, "scene", None)
    raw = str(scene.get(MOTION_STUDIO_STATE_PROPERTY, "")) if scene is not None else ""
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def current_action(context=None, *, require_recipe=True):
    context = context or bpy.context
    armature = None
    try:
        from . import find_armature

        armature = find_armature(context)
    except Exception:
        armature = bpy.data.objects.get(attachment_sockets.RUNTIME_ARMATURE_NAME)
    candidates = []
    if armature is not None and armature.animation_data is not None and armature.animation_data.action is not None:
        candidates.append(armature.animation_data.action)
    state = _session(context.scene)
    if state and bpy.data.actions.get(str(state.get("actionName", ""))) is not None:
        candidates.append(bpy.data.actions[str(state["actionName"])])
    settings = getattr(context.scene, "daf_settings", None)
    if settings is not None:
        selected = animation_library.selected_action(settings)
        if selected is not None:
            candidates.append(selected)
    for action in dict.fromkeys(candidates):
        if not require_recipe or action.get(motion.MOTION_RECIPE_PROPERTY):
            return action
    if require_recipe:
        raise RuntimeError("Build or select a Motion Studio offensive Action first.")
    return candidates[0] if candidates else None


def _load_master_library(scene=None):
    scene = scene or getattr(bpy.context, "scene", None)
    raw = str(scene.get(motion.MOTION_MASTER_LIBRARY_PROPERTY, "")) if scene is not None else ""
    if not raw:
        return {"schema": motion.MOTION_MASTER_LIBRARY_SCHEMA, "version": 1, "masters": []}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"schema": motion.MOTION_MASTER_LIBRARY_SCHEMA, "version": 1, "masters": []}
    if not isinstance(value, dict) or value.get("schema") != motion.MOTION_MASTER_LIBRARY_SCHEMA:
        return {"schema": motion.MOTION_MASTER_LIBRARY_SCHEMA, "version": 1, "masters": []}
    values = [master for master in value.get("masters", []) if not motion.validate_motion_master(master)]
    return {"schema": motion.MOTION_MASTER_LIBRARY_SCHEMA, "version": 1, "masters": values}


def available_masters(scene=None):
    values = {key: deepcopy(value) for key, value in motion.BUILTIN_MOTION_MASTERS.items()}
    for master in _load_master_library(scene).get("masters", []):
        values[master["masterId"]] = deepcopy(master)
    for action in bpy.data.actions:
        raw = str(action.get(motion.MOTION_MASTER_PROPERTY, ""))
        if not raw:
            continue
        try:
            master = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not motion.validate_motion_master(master):
            values[master["masterId"]] = master
    return values


def motion_master_items(_self=None, context=None):
    masters = available_masters(getattr(context, "scene", None))
    priority = {"builtin_1h_overhead": 0}
    return [
        (
            master_id,
            master["label"],
            "Artist-approved promoted master" if master["state"] == "PROMOTED_MASTER" else "Geometry-valid built-in starter; manual artistic approval still required",
        )
        for master_id, master in sorted(masters.items(), key=lambda item: (priority.get(item[0], 1), item[1]["state"] != "BUILT_IN_STARTER", item[1]["label"]))
    ]


def motion_master_updated(settings, context):
    global _SETTINGS_GUARD
    if _SETTINGS_GUARD:
        return
    master = available_masters(context.scene).get(str(settings.motion_master_id or "builtin_1h_overhead"))
    if master is None:
        return
    _SETTINGS_GUARD = True
    try:
        target = master["target"]
        proxy = master["proxy"]
        settings.motion_target_zone = target["zone"]
        settings.motion_target_height = float(target["heightMeters"])
        settings.motion_target_distance = float(target["distanceMeters"])
        settings.motion_target_lateral = float(target["lateralOffsetMeters"])
        settings.motion_target_radius = float(target["torsoRadiusMeters"])
        settings.motion_target_half_height = float(target["zoneHalfHeightMeters"])
        settings.motion_target_head_radius = float(target["headRadiusMeters"])
        settings.motion_custom_target_height = float(target["customHeightMeters"])
        settings.motion_custom_target_radius = float(target["customRadiusMeters"])
        settings.motion_proxy_class = proxy["class"]
        settings.motion_proxy_length = float(proxy["lengthMeters"])
        settings.motion_proxy_contact = float(proxy["gripToContactMeters"])
        settings.motion_proxy_strike_start = float(proxy["strikeSegmentStartMeters"])
        settings.motion_proxy_strike_end = float(proxy["strikeSegmentEndMeters"])
        settings.motion_proxy_head_radius = float(proxy["headRadiusMeters"])
        settings.motion_feel = str(master.get("feel", "CUSTOM"))
        settings.motion_target_distance_mode = "AUTO" if master["state"] == "BUILT_IN_STARTER" else "MANUAL"
        settings.motion_trajectory_family = master["trajectory"]["family"]
        settings.motion_windup_seconds = float(master["timing"]["windupSeconds"])
        settings.motion_active_seconds = float(master["timing"]["activeSeconds"])
        settings.motion_recovery_seconds = float(master["timing"]["recoverySeconds"])
        for name in motion.DEFAULT_STYLE:
            setattr(settings, "motion_style_" + _style_property_suffix(name), float(master["style"][name]))
        solver = dict(motion.DEFAULT_SOLVER)
        solver.update(master.get("solver", {}))
        settings.motion_solver_pole_side = float(solver["poleSideMeters"])
        settings.motion_solver_pole_back = float(solver["poleBackMeters"])
        settings.motion_solver_torso_support = float(solver["torsoSupport"])
        settings.motion_reach_comfortable_ratio = float(solver["comfortableReachRatio"])
        settings.motion_reach_warning_ratio = float(solver["warningReachRatio"])
        settings.motion_reach_hard_ratio = float(solver["hardReachRatio"])
        settings.motion_shoulder_support_max_degrees = float(solver["maxShoulderSupportDegrees"])
        tolerances = dict(motion.DEFAULT_TOLERANCES)
        tolerances.update(master.get("tolerances", {}))
        settings.motion_tolerance_plane_error = float(tolerances["planeErrorMeters"])
        settings.motion_tolerance_contact_window = float(tolerances["contactFrameWindowFrames"])
        settings.motion_tolerance_direction_dot = float(tolerances["directionDotMinimum"])
        settings.motion_tolerance_sampling_step = float(tolerances["activeSamplingStepFrames"])
    finally:
        _SETTINGS_GUARD = False
    settings.motion_pose_health_status = "POSE HEALTH — STALE; build selected master"
    settings.motion_pose_health_detail = ""
    invalidate_active_session(context, "Motion Master changed")


def _style_property_suffix(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", str(name)).lower()


def motion_setting_updated(_settings, context):
    if not _SETTINGS_GUARD:
        _settings.motion_pose_health_status = "POSE HEALTH — STALE; rebuild body solve"
        _settings.motion_pose_health_detail = ""
        invalidate_active_session(context, "Motion Studio input changed")


def motion_macro_updated(settings, context):
    if not _SETTINGS_GUARD:
        settings.motion_validation_status = "VIP CHANGES READY - click REFRESH ATTACK"
        settings.motion_pose_health_status = "POSE HEALTH - refresh required"
        settings.motion_pose_health_detail = ""
        invalidate_active_session(context, "VIP attack macro changed")


def motion_style_updated(settings, context):
    global _SETTINGS_GUARD
    if _SETTINGS_GUARD:
        return
    _SETTINGS_GUARD = True
    try:
        settings.motion_feel = "CUSTOM"
    finally:
        _SETTINGS_GUARD = False
    settings.motion_pose_health_status = "POSE HEALTH — STALE; rebuild body solve"
    settings.motion_pose_health_detail = ""
    invalidate_active_session(context, "Custom Motion Studio body style changed")


def motion_feel_updated(settings, context):
    global _SETTINGS_GUARD
    if _SETTINGS_GUARD:
        return
    preset = motion.STYLE_PRESETS.get(str(settings.motion_feel))
    if preset is None:
        motion_setting_updated(settings, context)
        return
    _SETTINGS_GUARD = True
    try:
        for name, value in preset.items():
            setattr(settings, "motion_style_" + _style_property_suffix(name), float(value))
    finally:
        _SETTINGS_GUARD = False
    settings.motion_pose_health_status = "POSE HEALTH — STALE; rebuild body solve"
    settings.motion_pose_health_detail = ""
    invalidate_active_session(context, "Motion feel changed")


def motion_proxy_updated(settings, context):
    global _SETTINGS_GUARD
    if _SETTINGS_GUARD:
        return
    proxy = motion.proxy_defaults(str(settings.motion_proxy_class))
    _SETTINGS_GUARD = True
    try:
        settings.motion_proxy_length = float(proxy["lengthMeters"])
        settings.motion_proxy_contact = float(proxy["gripToContactMeters"])
        settings.motion_proxy_strike_start = float(proxy["strikeSegmentStartMeters"])
        settings.motion_proxy_strike_end = float(proxy["strikeSegmentEndMeters"])
        settings.motion_proxy_head_radius = float(proxy["headRadiusMeters"])
    finally:
        _SETTINGS_GUARD = False
    settings.motion_pose_health_status = "POSE HEALTH — STALE; rebuild body solve"
    settings.motion_pose_health_detail = ""
    # Do not leave the previous proxy visible while the new selection is
    # waiting to be generated.
    remove_helpers(roles=PREVIEW_WEAPON_ROLES)
    invalidate_active_session(context, "Weapon proxy class changed")


def motion_display_updated(settings, _context):
    for helper in _owned_objects():
        role = str(helper.get("dsb_motion_studio_role", ""))
        visible = True
        if role.startswith("TARGET_"):
            visible = bool(settings.motion_show_target)
        elif role.startswith("TRAIL_"):
            visible = bool(settings.motion_show_trail)
        elif role == "STRIKE_GEOMETRY":
            visible = bool(settings.motion_show_plane)
        try:
            helper.hide_set(not visible)
            helper.hide_viewport = not visible
        except (ReferenceError, RuntimeError):
            continue


def invalidate_action(action, reason="Motion Studio input changed"):
    if action is None or not bool(action.get("dsb_draft", False)):
        return False
    for name in (
        motion.MOTION_VALIDATION_PROPERTY,
        motion.MOTION_POSE_HEALTH_PROPERTY,
        motion.TARGETING_PROPERTY,
        MOTION_BYPASS_PROPERTY,
        "dsb_motion_preview_digest",
        "dsb_offensive_previewed_before_approval",
        "dsb_motion_bypass_active",
        "dsb_motion_approval_mode",
    ):
        if name in action:
            del action[name]
    action["dsb_motion_validation_status"] = "STALE"
    action["dsb_motion_validation_reason"] = str(reason)
    action["dsb_offensive_previewed"] = False
    action["dsb_offensive_preview_count"] = 0
    return True


def invalidate_active_session(context=None, reason="Motion Studio input changed"):
    context = context or bpy.context
    try:
        action = current_action(context)
    except RuntimeError:
        return False
    return invalidate_action(action, reason)


def _settings_target(settings):
    return {
        "heightMeters": float(settings.motion_target_height),
        "distanceMeters": float(settings.motion_target_distance),
        "lateralOffsetMeters": float(settings.motion_target_lateral),
        "zone": str(settings.motion_target_zone),
        "torsoRadiusMeters": float(settings.motion_target_radius),
        "zoneHalfHeightMeters": float(settings.motion_target_half_height),
        "headRadiusMeters": float(settings.motion_target_head_radius),
        "customHeightMeters": float(settings.motion_custom_target_height),
        "customRadiusMeters": float(settings.motion_custom_target_radius),
    }


def _settings_proxy(settings):
    return {
        "class": str(settings.motion_proxy_class),
        "lengthMeters": float(settings.motion_proxy_length),
        "gripToContactMeters": float(settings.motion_proxy_contact),
        "strikeSegmentStartMeters": float(settings.motion_proxy_strike_start),
        "strikeSegmentEndMeters": float(settings.motion_proxy_strike_end),
        "headRadiusMeters": float(settings.motion_proxy_head_radius),
    }


def _settings_style(settings):
    return {
        name: float(getattr(settings, "motion_style_" + _style_property_suffix(name)))
        for name in motion.DEFAULT_STYLE
    }


def _settings_timing(settings):
    return {
        "windupSeconds": float(settings.motion_windup_seconds),
        "activeSeconds": float(settings.motion_active_seconds),
        "recoverySeconds": float(settings.motion_recovery_seconds),
        "contactFractionOfActive": 0.55,
    }


def _settings_solver(settings):
    return {
        **motion.DEFAULT_SOLVER,
        "poleSideMeters": float(settings.motion_solver_pole_side),
        "poleBackMeters": float(settings.motion_solver_pole_back),
        "torsoSupport": float(settings.motion_solver_torso_support),
        "comfortableReachRatio": float(settings.motion_reach_comfortable_ratio),
        "warningReachRatio": float(settings.motion_reach_warning_ratio),
        "hardReachRatio": float(settings.motion_reach_hard_ratio),
        "maxShoulderSupportDegrees": float(settings.motion_shoulder_support_max_degrees),
    }


def _settings_tolerances(settings):
    return {
        "planeErrorMeters": float(settings.motion_tolerance_plane_error),
        "contactFrameWindowFrames": float(settings.motion_tolerance_contact_window),
        "directionDotMinimum": float(settings.motion_tolerance_direction_dot),
        "activeSamplingStepFrames": float(settings.motion_tolerance_sampling_step),
    }


def _settings_vip_macros(settings):
    return {
        "horizontalAim": float(settings.motion_macro_horizontal_aim),
        "verticalAim": float(settings.motion_macro_vertical_aim),
        "windup": float(settings.motion_macro_windup),
        "strikePower": float(settings.motion_macro_strike_power),
        "bodyMotion": float(settings.motion_macro_body_motion),
        "followThrough": float(settings.motion_macro_follow_through),
        "armRelax": float(settings.motion_macro_arm_relax),
    }


def _recipe_from_master_settings(settings, master):
    recipe = motion.instantiate_motion_recipe(
        master,
        target=_settings_target(settings),
        proxy=_settings_proxy(settings),
        style=_settings_style(settings),
        solver=_settings_solver(settings),
        tolerances=_settings_tolerances(settings),
    )
    recipe["feel"] = str(settings.motion_feel)
    recipe["timing"] = _settings_timing(settings)
    recipe["trajectory"]["family"] = str(settings.motion_trajectory_family)
    return motion.apply_vip_macros(recipe, _settings_vip_macros(settings))


def _simple_recipe_from_selection(settings, master):
    """Create the production recipe from only the three visible choices.

    Older builds hid dozens of expert values but still consumed their stale
    scene state when REFRESH ATTACK was clicked.  A file could therefore look
    simple while silently inheriting an unsafe pole, tolerance, body style, or
    timing edit.  The production path is now deterministic: selected attack,
    weapon class, and target zone are the only inputs.  Built-in masters always
    start from their reviewed Natural defaults; promoted masters retain their
    explicitly stored authored values.
    """

    target = deepcopy(master["target"])
    target["zone"] = str(settings.motion_target_zone)
    proxy = motion.proxy_defaults(str(settings.motion_proxy_class))
    style = deepcopy(master.get("style", motion.DEFAULT_STYLE))
    solver = deepcopy(motion.DEFAULT_SOLVER)
    solver.update(deepcopy(master.get("solver", {})))
    tolerances = deepcopy(motion.DEFAULT_TOLERANCES)
    tolerances.update(deepcopy(master.get("tolerances", {})))
    recipe = motion.instantiate_motion_recipe(
        master,
        target=target,
        proxy=proxy,
        style=style,
        solver=solver,
        tolerances=tolerances,
    )
    recipe["feel"] = str(master.get("feel", "NATURAL"))
    recipe.setdefault("provenance", {})["simpleBuild"] = {
        "mode": "ATTACK_WEAPON_TARGET",
        "ignoredHiddenExpertState": True,
    }
    return recipe


def _update_recipe_from_settings(recipe, settings):
    old_proxy = recipe["proxy"]
    old_radius = float(old_proxy["headRadiusMeters"] if old_proxy["class"] == "ONE_HAND_BLUNT" else 0.015)
    anchor_kind = str(recipe["trajectory"].get("contactAnchor", "CENTER"))
    old_center = motion.target_contact_anchor(
        recipe["target"], anchor_kind, recipe["trajectory"]["expectedDirectionLocal"], proxy_radius=old_radius
    )
    new_target = _settings_target(settings)
    new_proxy = _settings_proxy(settings)
    new_radius = float(new_proxy["headRadiusMeters"] if new_proxy["class"] == "ONE_HAND_BLUNT" else 0.015)
    new_center = motion.target_contact_anchor(
        new_target, anchor_kind, recipe["trajectory"]["expectedDirectionLocal"], proxy_radius=new_radius
    )
    delta = motion.subtract(new_center, old_center)
    recipe["target"] = new_target
    proxy_changed = str(old_proxy["class"]) != str(new_proxy["class"])
    recipe["proxy"] = new_proxy
    recipe["style"] = _settings_style(settings)
    recipe["feel"] = str(settings.motion_feel)
    recipe["solver"] = _settings_solver(settings)
    recipe["tolerances"] = _settings_tolerances(settings)
    recipe["timing"] = _settings_timing(settings)
    recipe["trajectory"]["family"] = str(settings.motion_trajectory_family)
    for control in recipe["trajectory"]["controls"]:
        control["contactPointLocal"] = [round(value, 7) for value in motion.add(control["contactPointLocal"], delta)]
        if proxy_changed:
            control["contactDistanceMeters"] = round(
                motion.default_contact_distance(new_proxy, recipe["trajectory"]["family"]), 7
            )
    if proxy_changed:
        master = motion.BUILTIN_MOTION_MASTERS.get(str(recipe.get("motionMasterId", "")))
        profile = (
            master.get("trajectory", {}).get("weaponAxesByProxy", {}).get(str(new_proxy["class"]), {})
            if master is not None
            else {}
        )
        for control in recipe["trajectory"]["controls"]:
            if control["id"] in profile:
                control["weaponAxisLocal"] = [round(value, 7) for value in motion.normalize(profile[control["id"]])]
    return recipe


def _sync_helpers_to_recipe(armature, recipe):
    global _SETTINGS_GUARD
    changed = False
    target_root = _helper_by_role("TARGET_ROOT")
    if target_root is not None:
        local = armature.matrix_world.inverted_safe() @ target_root.matrix_world
        x, y = float(local.translation.x), float(local.translation.y)
        if abs(x - float(recipe["target"]["lateralOffsetMeters"])) > 1.0e-6 or abs(y - float(recipe["target"]["distanceMeters"])) > 1.0e-6:
            old_center = motion.target_zone_center(recipe["target"])
            recipe["target"]["lateralOffsetMeters"] = x
            recipe["target"]["distanceMeters"] = y
            new_center = motion.target_zone_center(recipe["target"])
            delta = motion.subtract(new_center, old_center)
            for control in recipe["trajectory"]["controls"]:
                control["contactPointLocal"] = [round(value, 7) for value in motion.add(control["contactPointLocal"], delta)]
            settings = getattr(bpy.context.scene, "daf_settings", None)
            if settings is not None:
                _SETTINGS_GUARD = True
                try:
                    settings.motion_target_lateral = x
                    settings.motion_target_distance = y
                finally:
                    _SETTINGS_GUARD = False
            changed = True
    by_id = {control["id"]: control for control in recipe["trajectory"]["controls"]}
    for helper in _owned_objects():
        control_id = str(helper.get("dsb_motion_control_id", ""))
        if control_id not in by_id:
            continue
        local = armature.matrix_world.inverted_safe() @ helper.matrix_world
        position = [round(float(value), 7) for value in local.translation]
        axis = [round(float(value), 7) for value in (local.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()]
        control = by_id[control_id]
        if position != [round(float(value), 7) for value in control["contactPointLocal"]] or axis != [round(float(value), 7) for value in motion.normalize(control["weaponAxisLocal"])]:
            control["contactPointLocal"] = position
            control["weaponAxisLocal"] = axis
            changed = True
    return changed


def _legacy_recipe(recipe):
    style = recipe["style"]
    return {
        "schema": offensive_actions.OFFENSIVE_RECIPE_SCHEMA,
        "windupSeconds": float(recipe["timing"]["windupSeconds"]),
        "activeSeconds": float(recipe["timing"]["activeSeconds"]),
        "recoverySeconds": float(recipe["timing"]["recoverySeconds"]),
        "anticipationStrength": max(0.25, min(1.80, float(style["anticipation"]))),
        "strikeStrength": 1.0,
        "followThrough": max(0.25, min(1.80, float(style["followThrough"]))),
        "torsoPower": max(0.0, min(2.0, float(style["torsoPower"]))),
        "armReach": max(0.50, min(1.50, float(style["armExtension"]))),
        "elbowFlex": max(0.50, min(1.50, float(style["elbowStyle"]))),
        "wristAction": max(0.0, min(2.0, float(style["wristStyle"]))),
        "stanceCompression": max(0.0, min(2.0, float(style["stanceCompression"]))),
    }


def _find_existing_kind(context, kind):
    from . import variant_authoring

    for action in variant_authoring.effective_actions(list(bpy.data.actions), context.scene):
        if bool(action.get("dsb_approved", False)) and str(action.get("dsb_approved_kind", "")) == str(kind):
            return action, variant_authoring.action_status(action, context.scene)
    return None


def _new_or_replace_draft(context, armature, kind):
    from . import DRAFT_ACTION_NAMES, unlink_action_everywhere, variant_authoring

    draft_name = DRAFT_ACTION_NAMES[kind]
    existing = bpy.data.actions.get(draft_name)
    if existing is None:
        protected = _find_existing_kind(context, kind)
        if protected is not None:
            existing_action, status = protected
            if status == "INHERITED":
                instruction = "Use CREATE VARIANT OVERRIDE or confirmed EDIT SHARED"
            elif status == "OVERRIDE":
                instruction = "Select the variant override and use EDIT"
            else:
                instruction = "Select the saved Action and use EDIT before rebuilding it"
            raise RuntimeError(
                f"{existing_action.name} already owns {kind} ({status}). {instruction} before building Motion Studio body motion."
            )
        action = bpy.data.actions.new(draft_name)
    else:
        status = variant_authoring.action_status(existing, context.scene)
        if status == "INHERITED":
            raise RuntimeError("Inherited Actions cannot be rebuilt without CREATE VARIANT OVERRIDE or confirmed EDIT SHARED.")
        unlink_action_everywhere(existing)
        properties = {str(key): _id_value(value) for key, value in existing.items()}
        fake_user = bool(existing.use_fake_user)
        bpy.data.actions.remove(existing, do_unlink=True)
        action = bpy.data.actions.new(draft_name)
        for key, value in properties.items():
            try:
                action[key] = value
            except (TypeError, ValueError):
                continue
        action.use_fake_user = fake_user
    action["dsb_draft"] = True
    action["dsb_approved"] = False
    action["dsb_draft_kind"] = kind
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    return action


def _skeleton_digest(armature):
    return motion.stable_digest([
        {
            "name": bone.name,
            "parent": bone.parent.name if bone.parent else "",
            "matrix": [round(float(value), 8) for row in bone.matrix_local for value in row],
        }
        for bone in armature.data.bones
    ])


def _curve_payload(action):
    from . import iter_action_fcurves

    return sorted(
        [
            {
                "path": str(curve.data_path),
                "index": int(curve.array_index),
                "points": [
                    [round(float(point.co[0]), 6), round(float(point.co[1]), 8)]
                    for point in curve.keyframe_points
                ],
            }
            for curve in iter_action_fcurves(action)
        ],
        key=lambda value: (value["path"], value["index"]),
    )


def _socket_payload(armature, recipe):
    role = "MAIN_HAND_R" if recipe["solver"]["arm"] == "RIGHT" else "MAIN_HAND_L"
    socket, _hand, _local = _socket_context(armature, role)
    record = attachment_sockets.socket_record(socket, armature)

    def matrix_values(value):
        return [
            0.0 if abs(float(component)) < 5.0e-7 else round(float(component), 6)
            for row in value
            for component in row
        ]

    # `socket_record()` verifies the public contract, but its decomposed local
    # matrix is evaluated through the animated parent bone and can accumulate
    # sub-micrometre noise between frames.  The authored relationship is stored
    # by Blender in these frame-invariant object matrices, so digest those.
    return {
        "socketId": record["socketId"],
        "semanticRole": record["semanticRole"],
        "parentRuntimeBone": record["parentRuntimeBone"],
        "calibrationMatrixBasis": matrix_values(socket.matrix_basis),
        "matrixParentInverse": matrix_values(socket.matrix_parent_inverse),
        "enabled": record["enabled"],
        "exportable": record["exportable"],
    }


def validation_input_digest(armature, action, recipe):
    return motion.stable_digest(
        recipe,
        _curve_payload(action),
        _socket_payload(armature, recipe),
        _skeleton_digest(armature),
    )


def _arm_reach_context(armature, mapping, recipe):
    suffix = "r" if recipe["solver"]["arm"] == "RIGHT" else "l"
    upper = armature.pose.bones[mapping["upper_arm_" + suffix]]
    lower = armature.pose.bones[mapping["lower_arm_" + suffix]]
    model = motion.arm_reach_model(
        float(upper.bone.length),
        float(lower.bone.length),
        minimum_ratio=float(recipe["solver"].get("minimumReachRatio", motion.DEFAULT_MINIMUM_REACH_RATIO)),
        comfortable_ratio=float(recipe["solver"].get("comfortableReachRatio", 0.88)),
        warning_ratio=float(recipe["solver"].get("warningReachRatio", 0.92)),
        hard_ratio=float(recipe["solver"].get("hardReachRatio", 0.985)),
    )
    return suffix, upper, lower, model


def _desired_hand_matrix(recipe, pose, socket_local):
    axis = Vector(pose["weaponAxisLocal"]).normalized()
    contact = Vector(pose["contactPointLocal"])
    contact_distance = float(
        pose.get(
            "contactDistanceMeters",
            motion.default_contact_distance(recipe["proxy"], recipe["trajectory"]["family"]),
        )
    )
    grip = contact - axis * contact_distance
    desired_socket = _basis_from_y(axis).to_4x4()
    desired_socket.translation = grip
    return desired_socket @ socket_local.inverted_safe()


def _shift_target_distance(recipe, distance):
    candidate = deepcopy(recipe)
    old_target = candidate["target"]
    old_radius = float(candidate["proxy"]["headRadiusMeters"] if candidate["proxy"]["class"] == "ONE_HAND_BLUNT" else 0.015)
    anchor_kind = str(candidate["trajectory"].get("contactAnchor", "CENTER"))
    old_anchor = motion.target_contact_anchor(
        old_target,
        anchor_kind,
        candidate["trajectory"]["expectedDirectionLocal"],
        proxy_radius=old_radius,
    )
    candidate["target"] = deepcopy(old_target)
    candidate["target"]["distanceMeters"] = float(distance)
    new_anchor = motion.target_contact_anchor(
        candidate["target"],
        anchor_kind,
        candidate["trajectory"]["expectedDirectionLocal"],
        proxy_radius=old_radius,
    )
    delta = motion.subtract(new_anchor, old_anchor)
    for control in candidate["trajectory"]["controls"]:
        control["contactPointLocal"] = [round(value, 7) for value in motion.add(control["contactPointLocal"], delta)]
    return candidate


def _fit_blade_contact_distances(recipe, shoulder, reach_model):
    if recipe["trajectory"]["family"] == "THRUST" or recipe["proxy"]["class"] == "ONE_HAND_BLUNT":
        fixed = float(recipe["proxy"]["gripToContactMeters"])
        for control in recipe["trajectory"]["controls"]:
            control["contactDistanceMeters"] = fixed
        return recipe
    proxy = recipe["proxy"]
    segment_start = float(proxy["strikeSegmentStartMeters"])
    segment_end = float(proxy["strikeSegmentEndMeters"])
    maximum_reach = float(reach_model["maximumGeometricReachMeters"])
    target_ratio = motion.clamp(float(recipe["style"].get("armExtension", 0.87)), 0.78, 0.90)
    warning_ratio = float(reach_model["warningReachRatio"])
    preferred = motion.default_contact_distance(proxy, recipe["trajectory"]["family"])
    best = None
    for index in range(65):
        distance = segment_start + (segment_end - segment_start) * (index / 64.0)
        ratios = [
            (Vector(control["contactPointLocal"]) - Vector(control["weaponAxisLocal"]).normalized() * distance - Vector(shoulder)).length
            / max(maximum_reach, 1.0e-8)
            for control in recipe["trajectory"]["controls"]
        ]
        contact_ratio = ratios[motion.CONTROL_IDS.index("CONTACT")]
        score = abs(contact_ratio - target_ratio) * 3.0
        score += max(0.0, max(ratios) - warning_ratio) * 140.0
        score += max(0.0, 0.36 - min(ratios)) * 8.0
        score += abs(distance - preferred) * 0.01
        record = (score, distance)
        if best is None or record[0] < best[0]:
            best = record
    selected = round(float(best[1]), 7)
    # One legal point on the blade is selected for the attack. Sliding that
    # point independently at every control made the wrist race along the blade
    # during recovery and could flip the elbow branch.
    for control in recipe["trajectory"]["controls"]:
        control["contactDistanceMeters"] = selected
    return recipe


def _desired_reach_samples(recipe, socket_local, shoulder, reach_model, fps):
    schedule = motion.control_frame_schedule(recipe, fps)
    values = []
    frame = float(schedule["START"])
    while frame <= float(schedule["END"]) + 1.0e-6:
        pose = motion.interpolate_trajectory(recipe, frame, schedule)
        desired = _desired_hand_matrix(recipe, pose, socket_local)
        requirement = motion.reach_requirement(shoulder, desired.translation, reach_model)
        values.append({
            "frame": frame,
            "wristPositionLocal": [float(value) for value in desired.translation],
            **requirement,
        })
        frame += 0.5
    return values, schedule


def auto_fit_recipe(armature, mapping, recipe, socket_local, fps, *, strict=True):
    """Fit the complete path inside a comfortable shoulder-to-wrist annulus.

    Maximum reach alone is not a pose-quality guarantee.  The old fitter could
    keep the farthest frame below 92% while allowing another frame to collapse
    the wrist into the shoulder, where a two-bone IK chain can change branch.
    We now search target distance *and* a bounded CONTACT-relative path scale,
    rejecting both over-extension and excessive inward folding.
    """

    _suffix, upper, _lower, reach_model = _arm_reach_context(armature, mapping, recipe)
    shoulder = Vector(upper.bone.head_local)
    source_recipe = deepcopy(recipe)
    arm_scale = float(reach_model["maximumGeometricReachMeters"]) / 0.7767385
    initial_excursion_scale = (
        1.0
        if arm_scale >= 0.98
        else motion.clamp(arm_scale * 0.92, 0.64, 0.96)
    )
    excursion_scales = []
    scale = initial_excursion_scale
    while scale > 0.421:
        excursion_scales.append(scale)
        scale *= 0.90
    if not excursion_scales or excursion_scales[-1] > 0.421:
        excursion_scales.append(0.42)

    family = str(source_recipe["trajectory"]["family"])
    minimum_distance, maximum_distance = ((0.68, 1.80) if family == "THRUST" else (0.50, 1.10))
    minimum_safe_ratio = float(source_recipe["solver"].get("minimumReachRatio", 0.55))
    target_ratio = motion.clamp(
        float(source_recipe["style"].get("armExtension", 0.87)),
        minimum_safe_ratio + 0.08,
        float(reach_model["warningReachRatio"]) - 0.01,
    )
    # Body/shoulder support slightly changes the measured chain after this
    # geometry-only fit. Keep a 2% margin so the finished pose, not merely the
    # pre-solve estimate, stays clear of the near-lock warning.
    warning_target = float(reach_model["warningReachRatio"]) - 0.02
    hard_ratio = float(reach_model["hardReachRatio"])
    best = None
    steps = int(round((maximum_distance - minimum_distance) / 0.01))

    source_contact = Vector(next(
        control["contactPointLocal"]
        for control in source_recipe["trajectory"]["controls"]
        if control["id"] == "CONTACT"
    ))
    for excursion_scale in excursion_scales:
        scaled_recipe = deepcopy(source_recipe)
        for control in scaled_recipe["trajectory"]["controls"]:
            point = Vector(control["contactPointLocal"])
            control["contactPointLocal"] = [
                round(float(value), 7)
                for value in source_contact + (point - source_contact) * excursion_scale
            ]
        for index in range(steps + 1):
            distance = minimum_distance + index * 0.01
            candidate = _shift_target_distance(scaled_recipe, distance)
            _fit_blade_contact_distances(candidate, shoulder, reach_model)
            samples, schedule = _desired_reach_samples(candidate, socket_local, shoulder, reach_model, fps)
            candidate["contactFrame"] = int(schedule["CONTACT"])
            ideal_report = motion.validate_baked_trajectory(
                candidate,
                motion.ideal_trajectory_samples(candidate, fps, 0.5),
            )
            maximum_ratio = max(value["extensionRatio"] for value in samples)
            minimum_ratio = min(value["extensionRatio"] for value in samples)
            contact_sample = min(samples, key=lambda value: abs(value["frame"] - schedule["CONTACT"]))
            contact_ratio = float(contact_sample["extensionRatio"])
            score = abs(contact_ratio - target_ratio) * 4.0
            score += max(0.0, maximum_ratio - warning_target) * 180.0
            score += max(0.0, minimum_safe_ratio - minimum_ratio) * 240.0
            score += max(0.0, minimum_safe_ratio + 0.06 - minimum_ratio) * 10.0
            score += max(0.0, minimum_safe_ratio + 0.08 - contact_ratio) * 12.0
            if maximum_ratio > hard_ratio:
                score += 1000.0 + (maximum_ratio - hard_ratio) * 1000.0
            # Reach fitting must not shrink a slash until its blade sits in the
            # target throughout windup/recovery. Contact timing and family
            # geometry are invariants of the fit, not a later surprise.
            if ideal_report["status"] != "PASS":
                score += 5000.0 + 250.0 * len(ideal_report.get("errors", []))
            # Preserve as much readable arc as the safe annulus permits.
            score += (1.0 - excursion_scale) * 0.08
            record = (
                score,
                candidate,
                maximum_ratio,
                minimum_ratio,
                contact_ratio,
                samples,
                excursion_scale,
                ideal_report,
            )
            if best is None or record[0] < best[0]:
                best = record

    _score, fitted, maximum_ratio, minimum_ratio, contact_ratio, samples, excursion_scale, ideal_report = best
    worst = max(samples, key=lambda value: value["extensionRatio"])
    fit_warnings = []
    if maximum_ratio > float(reach_model["hardReachRatio"]) + 1.0e-6:
        over = max(0.0, float(worst["distanceMeters"]) - float(reach_model["hardReachMeters"]))
        message = (
            f"TARGET REQUIRES {maximum_ratio * 100.0:.0f}% ARM EXTENSION. "
            f"Move target {over:.2f} m closer or use AUTO FIT with a more compact trajectory "
            f"(worst frame {float(worst['frame']):.1f})."
        )
        if strict:
            raise RuntimeError(message)
        fit_warnings.append(message)
    if minimum_ratio < minimum_safe_ratio - 1.0e-6:
        folded = min(samples, key=lambda value: value["extensionRatio"])
        message = (
            f"WRIST FOLDS TO {minimum_ratio * 100.0:.0f}% ARM EXTENSION; "
            f"safe minimum is {minimum_safe_ratio * 100.0:.0f}% "
            f"(frame {float(folded['frame']):.1f}). Choose a shorter weapon or a more compact attack."
        )
        if strict:
            raise RuntimeError(message)
        fit_warnings.append(message)
    if ideal_report["status"] != "PASS":
        message = (
            "AUTO FIT COULD NOT PRESERVE ATTACK TIMING AND TARGET CLEARANCE: "
            + " ".join(str(value) for value in ideal_report.get("errors", []))
        )
        if strict:
            raise RuntimeError(message)
        fit_warnings.append(message)
    fitted.setdefault("provenance", {})["autoFitExcursionScale"] = round(float(excursion_scale), 6)
    fitted.setdefault("provenance", {})["autoFit"] = {
        "mode": "CHARACTER_SAFE_REACH_ANNULUS",
        "targetDistanceMeters": round(float(fitted["target"]["distanceMeters"]), 6),
        "maximumDesiredExtensionRatio": round(float(maximum_ratio), 6),
        "minimumDesiredExtensionRatio": round(float(minimum_ratio), 6),
        "contactExtensionRatio": round(float(contact_ratio), 6),
    }
    if fit_warnings:
        fitted["provenance"]["exploratoryFitWarnings"] = fit_warnings
    return fitted, reach_model


def _apply_body_support(armature, mapping, settings, recipe, frame, schedule):
    from . import rotate, rotate_local

    style = recipe["style"]
    torso = float(style["torsoPower"]) * float(recipe["solver"]["torsoSupport"])
    power = motion.body_support_envelope(recipe, frame, schedule)
    family = recipe["trajectory"]["family"]
    side, up = (Vector((-1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)))
    # Production attacks no longer re-solve the pelvis, both legs, both knees,
    # and both feet for a one-hand strike.  That system produced dozens of
    # near-zero curves and could contort unusual rest orientations.  Spine and
    # chest give the weapon readable support while the authored lower body is
    # left exactly as-is.
    if family == "OVERHEAD_VERTICAL":
        lift = max(0.0, -power)
        descend = max(0.0, power)
        rotate(armature, mapping, "spine", side, (12.0 * lift - 16.0 * descend) * torso)
        rotate(armature, mapping, "chest", side, (18.0 * lift - 24.0 * descend) * torso)
    elif family in {"HORIZONTAL", "DIAGONAL_DOWN"}:
        direction = -1.0 if recipe["trajectory"]["expectedDirectionLocal"][0] < 0 else 1.0
        rotate(armature, mapping, "spine", up, direction * power * 14.0 * torso)
        rotate(armature, mapping, "chest", up, direction * power * 22.0 * torso)
        if family == "DIAGONAL_DOWN":
            rotate(armature, mapping, "chest", side, -abs(power) * 10.0 * torso)
    elif family == "THRUST":
        rotate(armature, mapping, "spine", side, -power * 14.0 * torso)
        rotate(armature, mapping, "chest", side, -power * 22.0 * torso)
    shoulder_role = "shoulder_r" if recipe["solver"]["arm"] == "RIGHT" else "shoulder_l"
    shoulder_limit = float(recipe["solver"].get("maxShoulderSupportDegrees", 4.0))
    shoulder_support = motion.clamp(power * 24.0 * torso, -shoulder_limit, shoulder_limit)
    rotate(armature, mapping, shoulder_role, side if family in {"OVERHEAD_VERTICAL", "THRUST"} else up, shoulder_support)
    wrist = (float(style["wristStyle"]) - 1.0) * 7.0
    rotate_local(armature, mapping, "hand_r" if recipe["solver"]["arm"] == "RIGHT" else "hand_l", (0.0, 1.0, 0.0), wrist)


def _solve_hand_ik(
    context,
    armature,
    mapping,
    recipe,
    pose,
    socket_local,
    solver_target,
    pole_target,
    pole_state=None,
):
    arm_suffix = "r" if recipe["solver"]["arm"] == "RIGHT" else "l"
    upper = armature.pose.bones[mapping["upper_arm_" + arm_suffix]]
    lower = armature.pose.bones[mapping["lower_arm_" + arm_suffix]]
    hand = armature.pose.bones[mapping["hand_" + arm_suffix]]
    contact = Vector(pose["contactPointLocal"])
    desired_hand = _desired_hand_matrix(recipe, pose, socket_local)
    solver_target.matrix_world = armature.matrix_world @ Matrix.Translation(desired_hand.translation)
    shoulder = upper.head.copy()
    base_elbow = lower.head.copy()
    reach = desired_hand.translation - shoulder
    reach_axis = reach.normalized() if reach.length > 1.0e-8 else Vector((0.0, 1.0, 0.0))
    # Seed the elbow plane from this rig's authored/base pose instead of a
    # global left/right formula.  The latter chose the wrong side on rotated
    # production bones and could change IK branch near a folded shoulder.
    pole_direction = base_elbow - shoulder
    pole_direction -= reach_axis * pole_direction.dot(reach_axis)
    previous_direction = (pole_state or {}).get("direction")
    if pole_direction.length <= 1.0e-6 and previous_direction is not None:
        pole_direction = previous_direction.copy()
    if pole_direction.length <= 1.0e-6:
        elbow_side = 1.0 if arm_suffix == "r" else -1.0
        fallback = Vector((elbow_side, -0.20, 0.18))
        pole_direction = fallback - reach_axis * fallback.dot(reach_axis)
    pole_direction.normalize()
    if previous_direction is not None:
        if pole_direction.dot(previous_direction) < 0.0:
            pole_direction.negate()
        blended = previous_direction * 0.82 + pole_direction * 0.18
        if blended.length > 1.0e-6:
            pole_direction = blended.normalized()
    if pole_state is not None:
        pole_state["direction"] = pole_direction.copy()
    midpoint = (shoulder + desired_hand.translation) * 0.5
    arm_length = float(upper.bone.length + lower.bone.length)
    pole_distance = max(
        arm_length * 0.72,
        float(recipe["solver"]["poleSideMeters"]) * max(0.50, float(recipe["style"]["elbowStyle"])),
    )
    pole_position = midpoint + pole_direction * pole_distance
    pole_target.matrix_world = armature.matrix_world @ Matrix.Translation(pole_position)
    constraint = lower.constraints.new("IK")
    constraint.name = "DSB_MS_TEMP_IK"
    constraint.target = solver_target
    constraint.pole_target = pole_target
    constraint.chain_count = int(recipe["solver"]["ikChainLength"])
    constraint.use_stretch = False
    context.view_layer.update()
    upper_matrix = upper.matrix.copy()
    lower_matrix = lower.matrix.copy()
    lower.constraints.remove(constraint)
    upper.matrix = upper_matrix
    context.view_layer.update()
    lower.matrix = lower_matrix
    context.view_layer.update()
    # Position is owned by the solved upper/lower arm. Only copy orientation to
    # the hand; preserving the natural parent endpoint prevents wrist
    # dislocation even when exact socket orientation is imperfect.
    solved_wrist = hand.matrix.translation.copy()
    oriented_hand = desired_hand.copy()
    oriented_hand.translation = solved_wrist
    hand.matrix = oriented_hand
    context.view_layer.update()
    actual_socket = hand.matrix @ socket_local
    actual_contact = actual_socket @ Vector((0.0, float(pose["contactDistanceMeters"]), 0.0))
    error = (actual_contact - contact).length
    return error


def _set_baked_interpolation(action):
    from . import iter_action_fcurves

    for curve in iter_action_fcurves(action):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"


def _maximum_baked_angular_step(context, armature, action, bone_names, schedule):
    """Measure actual Action evaluation after any curve post-processing."""

    armature.animation_data.action = action
    previous = {}
    maximum = {"degrees": 0.0, "bone": "", "frame": 0}
    original = int(context.scene.frame_current)
    try:
        for frame in range(schedule["START"], schedule["END"] + 1):
            context.scene.frame_set(frame)
            context.view_layer.update()
            for bone_name in bone_names:
                pose_bone = armature.pose.bones.get(bone_name)
                if pose_bone is None:
                    continue
                current = pose_bone.matrix.to_quaternion().normalized()
                prior = previous.get(bone_name)
                if prior is not None:
                    current.make_compatible(prior)
                    degrees = math.degrees(abs(float(prior.rotation_difference(current).angle)))
                    if degrees > maximum["degrees"]:
                        maximum = {"degrees": degrees, "bone": bone_name, "frame": int(frame)}
                previous[bone_name] = current.copy()
    finally:
        context.scene.frame_set(original)
    return maximum


def _set_markers(action, schedule):
    from . import _set_action_marker

    for name, key in (
        ("Attack_Start", "START"),
        ("Windup_Anticipation", "ANTICIPATION"),
        ("Active_Start", "activeStart"),
        ("Contact", "CONTACT"),
        ("Active_End", "activeEnd"),
        ("Follow_Through", "FOLLOW_THROUGH"),
        ("Attack_End", "END"),
    ):
        _set_action_marker(action, name, int(schedule[key]))


def _reduce_baked_keys(action, schedule):
    """Remove redundant every-frame samples without changing named poses.

    Rotation-only IK still samples every frame so quality checks see the real
    solve.  Once it passes, a small Ramer-Douglas-Peucker reduction keeps all
    seven authored phase poses and bounds component error between them.  This
    leaves ordinary FK curves instead of thousands of no-op keys.
    """

    from . import iter_action_fcurves

    required_frames = {
        float(schedule[key])
        for key in (*motion.CONTROL_IDS, "activeStart", "activeEnd")
        if key in schedule
    }

    def keep_segment(points, first, last, tolerance, keep):
        if last <= first + 1:
            return
        start_frame, start_value = points[first]
        end_frame, end_value = points[last]
        duration = max(end_frame - start_frame, 1.0e-8)
        worst_index = None
        worst_error = -1.0
        for index in range(first + 1, last):
            frame, value = points[index]
            factor = (frame - start_frame) / duration
            expected = start_value + (end_value - start_value) * factor
            error = abs(value - expected)
            if error > worst_error:
                worst_error = error
                worst_index = index
        if worst_index is not None and worst_error > tolerance:
            keep.add(worst_index)
            keep_segment(points, first, worst_index, tolerance, keep)
            keep_segment(points, worst_index, last, tolerance, keep)

    before = 0
    after = 0
    for curve in iter_action_fcurves(action):
        keyframes = list(curve.keyframe_points)
        before += len(keyframes)
        if len(keyframes) <= 1:
            after += len(keyframes)
            continue
        points = [(float(point.co[0]), float(point.co[1])) for point in keyframes]
        tolerance = 0.00045 if str(curve.data_path).endswith("rotation_quaternion") else 0.00001
        if max(value for _frame, value in points) - min(value for _frame, value in points) <= tolerance:
            keep = {0}
        else:
            anchors = {0, len(points) - 1}
            anchors.update(
                index
                for index, (frame, _value) in enumerate(points)
                if any(abs(frame - required) <= 1.0e-5 for required in required_frames)
            )
            keep = set(anchors)
            ordered = sorted(anchors)
            for first, last in zip(ordered, ordered[1:]):
                keep_segment(points, first, last, tolerance, keep)
        for index in range(len(keyframes) - 1, -1, -1):
            if index not in keep:
                curve.keyframe_points.remove(keyframes[index], fast=True)
        try:
            curve.update()
        except (AttributeError, RuntimeError):
            pass
        after += len(curve.keyframe_points)
    action["dsb_motion_bake_key_count_before_reduction"] = int(before)
    action["dsb_motion_bake_key_count"] = int(after)
    action["dsb_motion_bake_key_reduction_ratio"] = float(0.0 if before <= 0 else 1.0 - after / before)
    return {"before": before, "after": after}


def _bake_body(context, armature, action, recipe, *, allow_unsafe_preview=False):
    from . import apply_animation_base_pose, map_bones, reset_pose

    anatomy_blender.require_generator_capability(armature, "offensive_humanoid", "Offensive Motion Studio")
    skin_and_bones.require_canonical_yplus(armature, label="Offensive Motion Studio")
    mapping = map_bones(armature, context.scene.daf_settings)
    suffix = "r" if recipe["solver"]["arm"] == "RIGHT" else "l"
    required = [
        "root", "hips", "spine", "chest", "shoulder_" + suffix, "upper_arm_" + suffix,
        "lower_arm_" + suffix, "hand_" + suffix,
    ]
    missing = [role for role in required if role not in mapping]
    if missing:
        raise RuntimeError("Motion Studio canonical mapping is incomplete: " + ", ".join(missing) + ".")
    before = _skeleton_digest(armature)
    role = "MAIN_HAND_R" if suffix == "r" else "MAIN_HAND_L"
    _socket, _hand, socket_local = _socket_context(armature, role)
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    schedule = motion.control_frame_schedule(recipe, fps)
    _reach_suffix, reach_upper, _reach_lower, reach_model = _arm_reach_context(armature, mapping, recipe)
    desired_samples, _desired_schedule = _desired_reach_samples(
        recipe,
        socket_local,
        Vector(reach_upper.bone.head_local),
        reach_model,
        fps,
    )
    desired_worst = max(desired_samples, key=lambda value: value["extensionRatio"])
    desired_folded = min(desired_samples, key=lambda value: value["extensionRatio"])
    if (
        not allow_unsafe_preview
        and float(desired_worst["extensionRatio"]) > float(reach_model["hardReachRatio"]) + 1.0e-6
    ):
        over = max(0.0, float(desired_worst["distanceMeters"]) - float(reach_model["hardReachMeters"]))
        raise RuntimeError(
            f"TARGET REQUIRES {float(desired_worst['extensionRatio']) * 100.0:.0f}% ARM EXTENSION. "
            f"Move target {over:.2f} m closer or use AUTO FIT."
        )
    if (
        not allow_unsafe_preview
        and float(desired_folded["extensionRatio"]) < float(reach_model["minimumReachRatio"]) - 1.0e-6
    ):
        raise RuntimeError(
            f"WRIST FOLDS TO {float(desired_folded['extensionRatio']) * 100.0:.0f}% ARM EXTENSION. "
            f"The safe minimum is {float(reach_model['minimumReachRatio']) * 100.0:.0f}%; "
            "use AUTO FIT or a shorter weapon."
        )
    recipe["contactFrame"] = int(schedule["CONTACT"])
    context.scene.frame_start = schedule["START"]
    context.scene.frame_end = schedule["END"]
    armature.animation_data.action = action
    solver_target = _empty("DSB_MS_IK_TARGET", "SOLVER_TEMP", action=action, display="PLAIN_AXES", size=0.08)
    pole_target = _empty("DSB_MS_ELBOW_POLE", "SOLVER_TEMP", action=action, display="PLAIN_AXES", size=0.10)
    _parent_local(solver_target, armature)
    _parent_local(pole_target, armature)
    maximum_error = 0.0
    maximum_foot_error = 0.0
    maximum_foot_rotation_error = 0.0
    maximum_extension_ratio = 0.0
    minimum_extension_ratio = math.inf
    minimum_elbow_bend = 180.0
    maximum_thrust_elbow_ahead = 0.0
    maximum_thrust_elbow_ahead_frame = 0
    minimum_thrust_wrist_advance = math.inf
    minimum_thrust_wrist_advance_frame = 0
    minimum_thrust_forearm_advance = math.inf
    minimum_thrust_forearm_advance_frame = 0
    maximum_shoulder_support = 0.0
    maximum_torso_contribution = 0.0
    maximum_deform_translation = 0.0
    maximum_angular_step = 0.0
    maximum_angular_step_bone = ""
    maximum_angular_step_frame = 0
    maximum_angular_step_extension = 0.0
    maximum_angular_step_points = {}
    previous_quaternions = {}
    previous_world_quaternions = {}
    pole_state = {}
    # Neither deform arm receives local translation curves. The active chain is
    # solved by rotation; the support arm has no reason to carry zero-valued
    # location channels either.
    deform_roles = {
        role_name
        for arm_side in ("l", "r")
        for role_name in (
            "shoulder_" + arm_side,
            "upper_arm_" + arm_side,
            "lower_arm_" + arm_side,
            "hand_" + arm_side,
        )
        if role_name in mapping
    }
    deform_bone_names = {mapping[role] for role in deform_roles}
    dynamic_roles = {
        "spine",
        "chest",
        "shoulder_" + suffix,
        "upper_arm_" + suffix,
        "lower_arm_" + suffix,
        "hand_" + suffix,
    }
    dynamic_bone_names = {mapping[role] for role in dynamic_roles if role in mapping}
    mapped_bone_names = set(mapping.values())
    try:
        for frame in range(schedule["START"], schedule["END"] + 1):
            context.scene.frame_set(frame)
            reset_pose(armature, mapping)
            apply_animation_base_pose(armature, mapping, "IDLE")
            context.view_layer.update()
            _apply_body_support(armature, mapping, context.scene.daf_settings, recipe, frame, schedule)
            context.view_layer.update()
            pose = motion.interpolate_trajectory(recipe, frame, schedule)
            maximum_error = max(
                maximum_error,
                _solve_hand_ik(
                    context,
                    armature,
                    mapping,
                    recipe,
                    pose,
                    socket_local,
                    solver_target,
                    pole_target,
                    pole_state,
                ),
            )
            shoulder_point = Vector(armature.pose.bones[mapping["upper_arm_" + suffix]].head)
            elbow_point = Vector(armature.pose.bones[mapping["lower_arm_" + suffix]].head)
            wrist_point = Vector(armature.pose.bones[mapping["hand_" + suffix]].head)
            requirement = motion.reach_requirement(shoulder_point, wrist_point, reach_model)
            maximum_extension_ratio = max(maximum_extension_ratio, float(requirement["extensionRatio"]))
            minimum_extension_ratio = min(minimum_extension_ratio, float(requirement["extensionRatio"]))
            if (
                str(recipe["trajectory"]["family"]) == "THRUST"
                and schedule["activeStart"] <= frame <= schedule["activeEnd"]
            ):
                thrust_axis = Vector(recipe["trajectory"]["expectedDirectionLocal"])
                if thrust_axis.length > 1.0e-8:
                    thrust_axis.normalize()
                    wrist_advance = float((wrist_point - shoulder_point).dot(thrust_axis))
                    forearm_advance = float((wrist_point - elbow_point).dot(thrust_axis))
                    elbow_ahead = -forearm_advance
                    if wrist_advance < minimum_thrust_wrist_advance:
                        minimum_thrust_wrist_advance = wrist_advance
                        minimum_thrust_wrist_advance_frame = int(frame)
                    if forearm_advance < minimum_thrust_forearm_advance:
                        minimum_thrust_forearm_advance = forearm_advance
                        minimum_thrust_forearm_advance_frame = int(frame)
                    if elbow_ahead > maximum_thrust_elbow_ahead:
                        maximum_thrust_elbow_ahead = elbow_ahead
                        maximum_thrust_elbow_ahead_frame = int(frame)
            minimum_elbow_bend = min(
                minimum_elbow_bend,
                motion.elbow_bend_degrees(shoulder_point, elbow_point, wrist_point),
            )
            shoulder_pose = armature.pose.bones[mapping["shoulder_" + suffix]]
            maximum_shoulder_support = max(
                maximum_shoulder_support,
                math.degrees(abs(float(shoulder_pose.rotation_quaternion.angle))),
            )
            maximum_torso_contribution = max(
                maximum_torso_contribution,
                *[
                    math.degrees(abs(float(armature.pose.bones[mapping[body_role]].rotation_quaternion.angle)))
                    for body_role in ("hips", "spine", "chest")
                ],
            )
            maximum_deform_translation = max(
                maximum_deform_translation,
                *[
                    float(armature.pose.bones[mapping[deform_role]].location.length)
                    for deform_role in deform_roles
                ],
            )
            # Matrix decomposition may choose either quaternion hemisphere for
            # equivalent rotations.  Make every baked pose continuous before
            # key insertion so subframe playback cannot take a 360-degree arc
            # that was never present in the weapon control trajectory.
            for bone_name in mapped_bone_names:
                pose_bone = armature.pose.bones.get(bone_name)
                if pose_bone is None:
                    continue
                previous = previous_quaternions.get(bone_name)
                if previous is not None:
                    pose_bone.rotation_quaternion.make_compatible(previous)
                world_quaternion = pose_bone.matrix.to_quaternion().normalized()
                previous_world = previous_world_quaternions.get(bone_name)
                if previous_world is not None:
                    world_quaternion.make_compatible(previous_world)
                    angular_step = math.degrees(abs(float(previous_world.rotation_difference(world_quaternion).angle)))
                    if angular_step > maximum_angular_step:
                        maximum_angular_step = angular_step
                        maximum_angular_step_bone = bone_name
                        maximum_angular_step_frame = int(frame)
                        maximum_angular_step_extension = float(requirement["extensionRatio"])
                        maximum_angular_step_points = {
                            "shoulder": [round(float(value), 6) for value in shoulder_point],
                            "elbow": [round(float(value), 6) for value in elbow_point],
                            "wrist": [round(float(value), 6) for value in wrist_point],
                        }
                previous_quaternions[bone_name] = pose_bone.rotation_quaternion.copy()
                previous_world_quaternions[bone_name] = world_quaternion.copy()
            # One base-pose key keeps untouched bones deterministic when users
            # switch Actions. Only the six production-support bones are then
            # sampled through the clip; no local-location curves are emitted.
            for bone_name in mapped_bone_names:
                if frame != schedule["START"] and bone_name not in dynamic_bone_names:
                    continue
                pose_bone = armature.pose.bones.get(bone_name)
                if pose_bone is None:
                    continue
                pose_bone.keyframe_insert("rotation_quaternion", frame=frame, group=bone_name)
    finally:
        for bone in armature.pose.bones:
            for constraint in list(bone.constraints):
                if str(constraint.name).startswith("DSB_MS_TEMP_"):
                    bone.constraints.remove(constraint)
        for helper in (solver_target, pole_target):
            if helper is not None and helper.name in bpy.data.objects:
                _remove_object(helper)
    _set_baked_interpolation(action)
    measured_step = _maximum_baked_angular_step(
        context,
        armature,
        action,
        dynamic_bone_names,
        schedule,
    )
    maximum_angular_step = float(measured_step["degrees"])
    maximum_angular_step_bone = str(measured_step["bone"])
    maximum_angular_step_frame = int(measured_step["frame"])
    _set_markers(action, schedule)
    if _skeleton_digest(armature) != before:
        raise RuntimeError("Motion Studio changed canonical bone inventory or rest matrices.")
    from . import iter_action_fcurves

    if any(str(curve.data_path).endswith(".scale") for curve in iter_action_fcurves(action)):
        raise RuntimeError("Motion Studio FK bake created forbidden scale animation.")
    deform_location_curves = [
        curve
        for curve in iter_action_fcurves(action)
        if any(curve.data_path == f'pose.bones["{bone_name}"].location' for bone_name in deform_bone_names)
    ]
    if deform_location_curves:
        maximum_curve_translation = max(
            abs(float(point.co[1]))
            for curve in deform_location_curves
            for point in curve.keyframe_points
        )
        maximum_deform_translation = max(maximum_deform_translation, maximum_curve_translation)
    root_name = mapping["root"]
    root_locations = [
        point.co[1]
        for curve in iter_action_fcurves(action)
        if curve.data_path == f'pose.bones["{root_name}"].location'
        for point in curve.keyframe_points
    ]
    if root_locations and max(root_locations) - min(root_locations) > 1.0e-6:
        raise RuntimeError("Motion Studio starter masters must remain IN_PLACE; root translation changed.")
    action["dsb_motion_solver_max_contact_error_m"] = float(maximum_error)
    action["dsb_motion_solver_max_foot_error_m"] = float(maximum_foot_error)
    action["dsb_motion_solver_max_foot_rotation_error_deg"] = float(maximum_foot_rotation_error)
    action["dsb_motion_canonical_skeleton_digest"] = before
    action["dsb_motion_bake_recipe_digest"] = motion.stable_digest(recipe)
    pose_errors = []
    pose_warnings = []
    translation_tolerance = float(recipe["solver"].get("deformTranslationToleranceMeters", 0.0001))
    solve_tolerance = float(recipe["solver"].get("solveErrorToleranceMeters", 0.015))
    if maximum_extension_ratio > float(reach_model["hardReachRatio"]) + 1.0e-6:
        pose_errors.append(f"ARM REQUIRES {maximum_extension_ratio * 100.0:.0f}% EXTENSION; hard limit is {float(reach_model['hardReachRatio']) * 100.0:.1f}%.")
    elif maximum_extension_ratio > float(reach_model["warningReachRatio"]):
        pose_warnings.append(f"ARM EXTENSION {maximum_extension_ratio * 100.0:.0f}% — near lock.")
    minimum_reach_ratio = float(reach_model["minimumReachRatio"])
    if minimum_extension_ratio < minimum_reach_ratio - 1.0e-6:
        pose_errors.append(
            f"ARM FOLDS TO {minimum_extension_ratio * 100.0:.0f}% EXTENSION; "
            f"safe minimum is {minimum_reach_ratio * 100.0:.0f}%."
        )
    if str(recipe["trajectory"]["family"]) == "THRUST":
        if minimum_thrust_wrist_advance <= 0.05:
            pose_errors.append(
                f"THRUST WRIST DOES NOT ADVANCE IN FRONT OF SHOULDER "
                f"({minimum_thrust_wrist_advance:.3f} m, frame {minimum_thrust_wrist_advance_frame})."
            )
        if minimum_thrust_forearm_advance <= 0.01:
            pose_errors.append(
                f"THRUST WRIST DOES NOT STAY AHEAD OF ELBOW "
                f"({minimum_thrust_forearm_advance:.3f} m, frame {minimum_thrust_forearm_advance_frame})."
            )
    if minimum_elbow_bend < 8.0:
        pose_warnings.append(f"ELBOW BEND {minimum_elbow_bend:.1f}° — near locked arm.")
    if maximum_deform_translation > translation_tolerance:
        pose_errors.append(
            f"DEFORM ARM TRANSLATION {maximum_deform_translation:.6f} m exceeds {translation_tolerance:.6f} m."
        )
    if maximum_error > solve_tolerance:
        pose_errors.append(f"WRIST / CONTACT SOLVE ERROR {maximum_error:.3f} m exceeds {solve_tolerance:.3f} m.")
    if maximum_foot_error > 0.01:
        pose_errors.append(f"PLANTED FOOT DRIFT {maximum_foot_error:.3f} m exceeds 0.010 m.")
    if maximum_foot_rotation_error > 1.0:
        pose_errors.append(
            f"PLANTED FOOT ROTATION DRIFT {maximum_foot_rotation_error:.1f} degrees exceeds 1.0 degree."
        )
    shoulder_limit = float(recipe["solver"].get("maxShoulderSupportDegrees", 4.0))
    if maximum_shoulder_support > shoulder_limit + 0.1:
        pose_errors.append(f"SHOULDER SUPPORT {maximum_shoulder_support:.1f}° exceeds {shoulder_limit:.1f}° cap.")
    elif maximum_shoulder_support > shoulder_limit * 0.80:
        pose_warnings.append(f"SHOULDER SUPPORT HIGH — {maximum_shoulder_support:.1f}°.")
    if maximum_torso_contribution > 18.0:
        pose_warnings.append(f"TORSO ROTATION HIGH — {maximum_torso_contribution:.1f}°.")
    if maximum_angular_step > 25.0:
        pose_errors.append(
            f"FK CHAIN DISCONTINUITY {maximum_angular_step:.1f}° in one frame "
            f"({maximum_angular_step_bone}, frame {maximum_angular_step_frame}, "
            f"arm extension {maximum_angular_step_extension * 100.0:.1f}%)."
        )
    elif maximum_angular_step > 22.0:
        pose_warnings.append(f"FRAME ANGULAR CHANGE HIGH — {maximum_angular_step:.1f}°.")
    pose_health = {
        "schema": motion.MOTION_POSE_HEALTH_SCHEMA,
        "status": "FAIL" if pose_errors else "WARN" if pose_warnings else "PASS",
        "reachModel": {key: round(float(value), 7) for key, value in reach_model.items()},
        "maximumArmExtensionRatio": round(maximum_extension_ratio, 7),
        "minimumArmExtensionRatio": round(minimum_extension_ratio, 7),
        "minimumElbowBendDegrees": round(minimum_elbow_bend, 5),
        "maximumThrustElbowAheadOfWristMeters": round(maximum_thrust_elbow_ahead, 7),
        "maximumThrustElbowAheadOfWristFrame": maximum_thrust_elbow_ahead_frame,
        "minimumActiveThrustWristAdvanceMeters": round(
            0.0 if math.isinf(minimum_thrust_wrist_advance) else minimum_thrust_wrist_advance,
            7,
        ),
        "minimumActiveThrustWristAdvanceFrame": minimum_thrust_wrist_advance_frame,
        "minimumActiveThrustForearmAdvanceMeters": round(
            0.0 if math.isinf(minimum_thrust_forearm_advance) else minimum_thrust_forearm_advance,
            7,
        ),
        "minimumActiveThrustForearmAdvanceFrame": minimum_thrust_forearm_advance_frame,
        "maximumShoulderSupportDegrees": round(maximum_shoulder_support, 5),
        "maximumTorsoContributionDegrees": round(maximum_torso_contribution, 5),
        "maximumDeformTranslationMeters": round(maximum_deform_translation, 8),
        "maximumWristContactSolveErrorMeters": round(maximum_error, 8),
        "maximumFootDriftMeters": round(maximum_foot_error, 8),
        "maximumFootRotationDriftDegrees": round(maximum_foot_rotation_error, 5),
        "maximumFrameAngularChangeDegrees": round(maximum_angular_step, 5),
        "maximumFrameAngularChangeBone": maximum_angular_step_bone,
        "maximumFrameAngularChangeFrame": maximum_angular_step_frame,
        "maximumFrameAngularChangeExtensionRatio": round(maximum_angular_step_extension, 7),
        "maximumFrameAngularChangeChainPoints": maximum_angular_step_points,
        "errors": pose_errors,
        "warnings": pose_warnings,
    }
    motion.stamp_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, pose_health)
    action["dsb_motion_pose_health_status"] = pose_health["status"]
    action["dsb_motion_exploratory_preview"] = bool(allow_unsafe_preview)
    if pose_errors and not allow_unsafe_preview:
        raise RuntimeError("Motion Studio pose safety failed: " + " ".join(pose_errors))
    _reduce_baked_keys(action, schedule)
    return schedule


def sample_baked_weapon_path(context, armature, action, recipe):
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    role = "MAIN_HAND_R" if recipe["solver"]["arm"] == "RIGHT" else "MAIN_HAND_L"
    _socket, hand, socket_local = _socket_context(armature, role)
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    schedule = motion.control_frame_schedule(recipe, fps)
    step = float(recipe["tolerances"]["activeSamplingStepFrames"])
    samples = []
    frame = float(schedule["START"])
    original = float(context.scene.frame_current) + float(getattr(context.scene, "frame_subframe", 0.0))
    try:
        while frame <= float(schedule["END"]) + 1.0e-6:
            integer = math.floor(frame)
            context.scene.frame_set(integer, subframe=frame - integer)
            context.view_layer.update()
            socket_matrix = hand.matrix @ socket_local
            proxy = recipe["proxy"]
            pose = motion.interpolate_trajectory(recipe, frame, schedule)
            contact_distance = float(pose["contactDistanceMeters"])
            grip = socket_matrix.translation
            contact = socket_matrix @ Vector((0.0, contact_distance, 0.0))
            strike_start = socket_matrix @ Vector((0.0, float(proxy["strikeSegmentStartMeters"]), 0.0))
            strike_end = socket_matrix @ Vector((0.0, float(proxy["strikeSegmentEndMeters"]), 0.0))
            axis = (socket_matrix.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
            phase = "WINDUP" if frame < schedule["activeStart"] else "ACTIVE" if frame <= schedule["activeEnd"] else "RECOVERY"
            samples.append({
                "frame": round(frame, 6),
                "timeSeconds": round((frame - schedule["START"]) / fps, 7),
                "phase": phase,
                "contactPointLocal": [float(value) for value in contact],
                "strikeStartLocal": [float(value) for value in strike_start],
                "strikeEndLocal": [float(value) for value in strike_end],
                "weaponAxisLocal": [float(value) for value in axis],
                "contactDistanceMeters": contact_distance,
            })
            frame += step if phase == "ACTIVE" else max(0.5, step)
    finally:
        integer = math.floor(original)
        context.scene.frame_set(integer, subframe=original - integer)
    return samples


def _store_validation(action, report):
    motion.stamp_json(action, motion.MOTION_VALIDATION_PROPERTY, report)
    action["dsb_motion_validation_status"] = report["status"]
    if report["status"] == "PASS":
        targeting = motion.targeting_metadata(motion.read_motion_recipe(action), report)
        motion.stamp_json(action, motion.TARGETING_PROPERTY, targeting)
    elif motion.TARGETING_PROPERTY in action:
        del action[motion.TARGETING_PROPERTY]
    return report


def validate_baked_action(context, action=None, *, sync_inputs=True, rebuild_visuals=True):
    from . import find_armature

    action = action or current_action(context)
    armature = find_armature(context)
    recipe = motion.read_motion_recipe(action)
    if recipe is None:
        raise RuntimeError("The selected Action has no Motion Studio recipe.")
    changed = False
    if sync_inputs:
        changed = _sync_helpers_to_recipe(armature, recipe)
        updated = _update_recipe_from_settings(deepcopy(recipe), context.scene.daf_settings)
        if motion.stable_digest(updated) != motion.stable_digest(recipe):
            recipe = updated
            changed = True
        if changed:
            motion.stamp_motion_recipe(action, recipe)
            invalidate_action(action, "Trajectory-critical Motion Studio input changed")
    if str(action.get("dsb_motion_bake_recipe_digest", "")) != motion.stable_digest(recipe):
        report = {
            "schema": motion.MOTION_VALIDATION_SCHEMA,
            "status": "FAIL",
            "inputDigest": "",
            "targetZone": recipe["target"]["zone"],
            "trajectoryFamily": recipe["trajectory"]["family"],
            "activeContact": False,
            "errors": ["Motion Studio controls/settings changed after the FK bake. Run BUILD / REBUILD BODY SOLVE before validation."],
        }
        return _store_validation(action, report)
    digest = validation_input_digest(armature, action, recipe)
    samples = sample_baked_weapon_path(context, armature, action, recipe)
    report = motion.validate_baked_trajectory(recipe, samples, input_digest=digest)
    pose_health = motion.read_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, "Motion Studio pose health")
    report["poseHealth"] = pose_health
    report["warnings"] = list((pose_health or {}).get("warnings", []))
    if pose_health is None:
        report.setdefault("errors", []).append("Motion Studio pose-health proof is missing; rebuild the body solve.")
        report["status"] = "FAIL"
    elif pose_health.get("status") == "FAIL":
        report.setdefault("errors", []).extend(str(value) for value in pose_health.get("errors", []))
        report["status"] = "FAIL"
    _cache_pose_health(context.scene.daf_settings, pose_health)
    _store_validation(action, report)
    if rebuild_visuals:
        build_helpers(armature, action, recipe, samples=samples, validation=report)
    context.scene.daf_settings.motion_validation_status = (
        "PASS — baked weapon intersects " + recipe["target"]["zone"] + " during ACTIVE"
        if report["status"] == "PASS"
        else "FAIL — " + (report["errors"][0] if report.get("errors") else "unknown trajectory failure")
    )
    return report


def _stamp_action_contract(action, recipe, fps):
    kind = recipe["actionKind"]
    legacy = _legacy_recipe(recipe)
    variant = offensive_actions.offensive_variant_with_recipe(kind, legacy)
    metadata, _legacy_schedule = offensive_actions.phase_metadata(variant, fps)
    offensive_actions.stamp_offensive_metadata(action, metadata)
    offensive_actions.stamp_offensive_recipe(action, legacy)
    motion.stamp_motion_recipe(action, recipe)
    action["dsb_draft_kind"] = kind
    action["dsb_root_motion_policy"] = "IN_PLACE"
    action["dsb_motion_studio"] = True
    action["dsb_offensive_previewed"] = False
    action["dsb_offensive_preview_count"] = 0
    return metadata


def _apply_fit_to_settings(settings, recipe):
    global _SETTINGS_GUARD
    _SETTINGS_GUARD = True
    try:
        settings.motion_target_distance = float(recipe["target"]["distanceMeters"])
        for name, value in recipe["style"].items():
            setattr(settings, "motion_style_" + _style_property_suffix(name), float(value))
    finally:
        _SETTINGS_GUARD = False


def _cache_pose_health(settings, report):
    if not report:
        settings.motion_pose_health_status = "POSE HEALTH — MISSING"
        settings.motion_pose_health_detail = "Rebuild the body solve"
        return
    status = str(report.get("status", "UNKNOWN"))
    settings.motion_pose_health_status = (
        f"POSE {status} · reach {float(report.get('minimumArmExtensionRatio', 0.0)) * 100.0:.1f}–"
        f"{float(report.get('maximumArmExtensionRatio', 0.0)) * 100.0:.1f}% · "
        f"elbow {float(report.get('minimumElbowBendDegrees', 0.0)):.1f}° · "
        f"shoulder {float(report.get('maximumShoulderSupportDegrees', 0.0)):.1f}°"
    )
    settings.motion_pose_health_detail = (
        f"torso {float(report.get('maximumTorsoContributionDegrees', 0.0)):.1f}° · "
        f"deform move {float(report.get('maximumDeformTranslationMeters', 0.0)):.6f} m · "
        f"solve {float(report.get('maximumWristContactSolveErrorMeters', 0.0)):.4f} m · "
        f"frame step {float(report.get('maximumFrameAngularChangeDegrees', 0.0)):.1f}°"
    )


def natural_fit_settings(context):
    from . import find_armature, map_bones

    settings = context.scene.daf_settings
    master = available_masters(context.scene).get(str(settings.motion_master_id or "builtin_1h_overhead"))
    if master is None:
        raise RuntimeError("Choose an available Motion Master.")
    armature = find_armature(context)
    mapping = map_bones(armature, settings)
    recipe = _recipe_from_master_settings(settings, master)
    role = "MAIN_HAND_R" if recipe["solver"]["arm"] == "RIGHT" else "MAIN_HAND_L"
    _socket, _hand, socket_local = _socket_context(armature, role)
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    fitted, reach_model = auto_fit_recipe(armature, mapping, recipe, socket_local, fps)
    _apply_fit_to_settings(settings, fitted)
    settings.motion_target_distance_mode = "AUTO"
    settings.motion_validation_status = (
        f"AUTO FIT — {fitted['target']['distanceMeters']:.2f} m · "
        f"comfortable reach {reach_model['comfortableReachMeters']:.2f} m"
    )
    invalidate_active_session(context, "Natural Auto Fit changed the target relationship")
    settings.motion_pose_health_status = "POSE HEALTH — STALE; build Natural Fit"
    settings.motion_pose_health_detail = ""
    return {"recipe": fitted, "reachModel": reach_model}


def reset_to_natural(context):
    global _SETTINGS_GUARD
    settings = context.scene.daf_settings
    _SETTINGS_GUARD = True
    try:
        settings.motion_feel = "NATURAL"
        settings.motion_target_distance_mode = "AUTO"
        for name, value in motion.STYLE_PRESETS["NATURAL"].items():
            setattr(settings, "motion_style_" + _style_property_suffix(name), float(value))
        settings.motion_solver_torso_support = float(motion.DEFAULT_SOLVER["torsoSupport"])
        settings.motion_reach_comfortable_ratio = float(motion.DEFAULT_SOLVER["comfortableReachRatio"])
        settings.motion_reach_warning_ratio = float(motion.DEFAULT_SOLVER["warningReachRatio"])
        settings.motion_reach_hard_ratio = float(motion.DEFAULT_SOLVER["hardReachRatio"])
        settings.motion_shoulder_support_max_degrees = float(motion.DEFAULT_SOLVER["maxShoulderSupportDegrees"])
        settings.motion_macro_horizontal_aim = float(motion.VIP_MACRO_DEFAULTS["horizontalAim"])
        settings.motion_macro_vertical_aim = float(motion.VIP_MACRO_DEFAULTS["verticalAim"])
        settings.motion_macro_windup = float(motion.VIP_MACRO_DEFAULTS["windup"])
        settings.motion_macro_strike_power = float(motion.VIP_MACRO_DEFAULTS["strikePower"])
        settings.motion_macro_body_motion = float(motion.VIP_MACRO_DEFAULTS["bodyMotion"])
        settings.motion_macro_follow_through = float(motion.VIP_MACRO_DEFAULTS["followThrough"])
        settings.motion_macro_arm_relax = float(motion.VIP_MACRO_DEFAULTS["armRelax"])
    finally:
        _SETTINGS_GUARD = False
    invalidate_active_session(context, "Reset to Natural")
    settings.motion_validation_status = "RESET TO NATURAL — build to apply character reach fit"
    settings.motion_pose_health_status = "POSE HEALTH — STALE; build Natural defaults"
    settings.motion_pose_health_detail = ""
    return motion.STYLE_PRESETS["NATURAL"]


def build_from_master(
    context,
    *,
    simple=False,
    exploratory=False,
    preview_weapon=False,
):
    from . import find_armature, map_bones

    settings = context.scene.daf_settings
    master = available_masters(context.scene).get(str(settings.motion_master_id or "builtin_1h_overhead"))
    if master is None:
        raise RuntimeError("Choose an available Motion Master.")
    armature = find_armature(context)
    recipe = (
        _simple_recipe_from_selection(settings, master)
        if simple
        else _recipe_from_master_settings(settings, master)
    )
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    if simple or str(settings.motion_target_distance_mode) == "AUTO":
        mapping = map_bones(armature, settings)
        role = "MAIN_HAND_R" if recipe["solver"]["arm"] == "RIGHT" else "MAIN_HAND_L"
        _socket, _hand, socket_local = _socket_context(armature, role)
        recipe, _reach_model = auto_fit_recipe(
            armature,
            mapping,
            recipe,
            socket_local,
            fps,
            strict=not exploratory,
        )
        _apply_fit_to_settings(settings, recipe)
    schedule = motion.control_frame_schedule(recipe, fps)
    recipe["contactFrame"] = int(schedule["CONTACT"])
    action = _new_or_replace_draft(context, armature, recipe["actionKind"])
    _stamp_action_contract(action, recipe, fps)
    _bake_body(
        context,
        armature,
        action,
        recipe,
        allow_unsafe_preview=exploratory,
    )
    pose_health = motion.read_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, "Motion Studio pose health")
    motion.stamp_motion_recipe(action, recipe)
    action["dsb_motion_bake_recipe_digest"] = motion.stable_digest(recipe)
    animation_library.mark_draft(action, armature, settings, recipe["actionKind"])
    motion.stamp_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, pose_health)
    action["dsb_motion_pose_health_status"] = pose_health["status"]
    _cache_pose_health(settings, pose_health)
    settings.offensive_preview_kind = recipe["actionKind"]
    if simple or preview_weapon:
        remove_helpers()
    validation = validate_baked_action(
        context,
        action,
        sync_inputs=False,
        rebuild_visuals=not simple and not preview_weapon,
    )
    if preview_weapon:
        build_preview_weapon(armature, action, recipe)
    else:
        _store_session(action, recipe, helpers_required=not simple)
    context.scene.frame_set(recipe["contactFrame"])
    return {"action": action, "recipe": recipe, "validation": validation}


def refresh_vip_attack(context, *, start_playback=True):
    """Bake the live controls and always show the exploratory result."""

    result = build_from_master(
        context,
        exploratory=True,
        preview_weapon=True,
    )
    result["preview"] = preview_motion(
        context,
        start_playback=start_playback,
        build_review_helpers=False,
    )
    return result


def rebuild_body_solve(context, *, exploratory=False):
    from . import find_armature

    settings = context.scene.daf_settings
    armature = find_armature(context)
    source = current_action(context)
    if not bool(source.get("dsb_draft", False)):
        from . import variant_authoring

        variant_authoring.require_regular_action_edit_allowed(source, context.scene)
        raise RuntimeError("Motion Studio rebuilds drafts only. Use EDIT, CREATE VARIANT OVERRIDE, or confirmed EDIT SHARED first.")
    recipe = motion.read_motion_recipe(source)
    _sync_helpers_to_recipe(armature, recipe)
    recipe = _update_recipe_from_settings(recipe, settings)
    errors = motion.validate_motion_recipe(recipe)
    if errors:
        raise RuntimeError("Invalid Motion Studio controls: " + " ".join(errors))
    action = _new_or_replace_draft(context, armature, recipe["actionKind"])
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    schedule = motion.control_frame_schedule(recipe, fps)
    recipe["contactFrame"] = int(schedule["CONTACT"])
    _stamp_action_contract(action, recipe, fps)
    _bake_body(
        context,
        armature,
        action,
        recipe,
        allow_unsafe_preview=exploratory,
    )
    pose_health = motion.read_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, "Motion Studio pose health")
    motion.stamp_motion_recipe(action, recipe)
    action["dsb_motion_bake_recipe_digest"] = motion.stable_digest(recipe)
    animation_library.mark_draft(action, armature, settings, recipe["actionKind"])
    motion.stamp_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, pose_health)
    action["dsb_motion_pose_health_status"] = pose_health["status"]
    _cache_pose_health(settings, pose_health)
    validation = validate_baked_action(context, action, sync_inputs=False, rebuild_visuals=True)
    _store_session(action, recipe)
    context.scene.frame_set(recipe["contactFrame"])
    return {"action": action, "recipe": recipe, "validation": validation}


def preview_motion(context, *, start_playback=True, build_review_helpers=True):
    from . import find_armature, validate_offensive_action

    action = current_action(context)
    if not bool(action.get("dsb_draft", False)):
        raise RuntimeError("Preview proof is recorded on the current Motion Studio draft before approval.")
    structural = validate_offensive_action(context, action, require_approved=False, require_motion_validation=False)
    if structural["status"] != "PASS":
        raise RuntimeError("Motion Studio preview is blocked: " + "; ".join(structural["errors"][:4]))
    armature = find_armature(context)
    recipe = motion.read_motion_recipe(action)
    digest = validation_input_digest(armature, action, recipe)
    samples = sample_baked_weapon_path(context, armature, action, recipe)
    validation = motion.read_json(action, motion.MOTION_VALIDATION_PROPERTY, "Motion Studio validation")
    if build_review_helpers:
        build_helpers(
            armature,
            action,
            recipe,
            samples=samples,
            validation=validation,
            include_controls=False,
        )
    result = animation_library.play_action(context, armature, action, start_playback=start_playback)
    action["dsb_offensive_previewed"] = True
    action["dsb_offensive_preview_count"] = int(action.get("dsb_offensive_preview_count", 0)) + 1
    action["dsb_motion_preview_digest"] = digest
    validation_status = str((validation or {}).get("status", "MISSING"))
    pose_health = motion.read_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, "Motion Studio pose health")
    pose_status = str((pose_health or {}).get("status", "MISSING"))
    approval_ready = validation_status == "PASS" and pose_status == "PASS"
    context.scene.daf_settings.motion_validation_status = (
        "PASS · PREVIEWED — ready for approval"
        if approval_ready
        else f"PREVIEW ONLY · path {validation_status} · pose {pose_status} — approval blocked"
    )
    return {
        **result,
        "previewCount": int(action["dsb_offensive_preview_count"]),
        "approvalReady": approval_ready,
        "validationStatus": validation_status,
        "poseStatus": pose_status,
    }


def bypass_record(action):
    record = motion.read_json(action, MOTION_BYPASS_PROPERTY, "Motion Studio bypass approval")
    if not isinstance(record, dict) or record.get("schema") != MOTION_BYPASS_SCHEMA:
        return None
    return record


def bypass_is_current(context, action, *, armature=None):
    """Return true only while the override still matches the reviewed preview."""

    record = bypass_record(action)
    recipe = motion.read_motion_recipe(action)
    if record is None or recipe is None or not bool(record.get("exportAllowed", False)):
        return False
    try:
        from . import find_armature

        armature = armature or find_armature(context)
        digest = validation_input_digest(armature, action, recipe)
    except Exception:
        return False
    return bool(
        action.get("dsb_motion_bypass_active", False)
        and action.get("dsb_offensive_previewed", False)
        and str(record.get("inputDigest", "")) == digest
        and str(record.get("previewDigest", "")) == digest
        and str(action.get("dsb_motion_preview_digest", "")) == digest
    )


def approval_errors(context, action, *, armature=None):
    errors = []
    recipe = motion.read_motion_recipe(action)
    if recipe is None:
        return errors
    try:
        from . import find_armature, iter_action_fcurves

        armature = armature or find_armature(context)
    except Exception as exc:
        return [str(exc)]
    if bypass_is_current(context, action, armature=armature):
        return []
    if str(action.get("dsb_motion_bake_recipe_digest", "")) != motion.stable_digest(recipe):
        errors.append("Motion Studio body solve is stale; rebuild and validate the FK Action.")
    report = motion.read_json(action, motion.MOTION_VALIDATION_PROPERTY, "Motion Studio validation")
    current_digest = validation_input_digest(armature, action, recipe)
    if report is None or report.get("status") != "PASS":
        detail = report.get("errors", ["Run baked-path validation."])[0] if report else "Run baked-path validation."
        errors.append("APPROVAL BLOCKED: " + str(detail))
    elif str(report.get("inputDigest", "")) != current_digest:
        errors.append("APPROVAL BLOCKED: Action curves, target, proxy, socket, or skeleton changed after validation.")
    else:
        if not bool(report.get("activeContact", False)):
            errors.append("APPROVAL BLOCKED: baked weapon path has no target contact during ACTIVE.")
        if not bool(report.get("intendedContact", False)):
            errors.append("APPROVAL BLOCKED: intended CONTACT frame does not intersect the authored target.")
    if not bool(action.get("dsb_offensive_previewed", False)):
        errors.append("APPROVAL BLOCKED: preview this Motion Studio draft on the character.")
    elif str(action.get("dsb_motion_preview_digest", "")) != current_digest:
        errors.append("APPROVAL BLOCKED: preview proof is stale after a trajectory-critical change.")
    targeting = motion.read_json(action, motion.TARGETING_PROPERTY, "Offensive targeting metadata")
    if targeting is None:
        errors.append("APPROVAL BLOCKED: successful validation has not produced targeting metadata.")
    elif motion.validate_targeting_metadata(targeting):
        errors.append("APPROVAL BLOCKED: targeting metadata is invalid.")
    role = "MAIN_HAND_R" if recipe["solver"]["arm"] == "RIGHT" else "MAIN_HAND_L"
    try:
        _socket_payload(armature, recipe)
    except Exception as exc:
        errors.append(f"APPROVAL BLOCKED: compatible socket role {role} is unavailable: {exc}")
    if _skeleton_digest(armature) != str(action.get("dsb_motion_canonical_skeleton_digest", "")):
        errors.append("APPROVAL BLOCKED: canonical skeleton inventory/rest matrices changed after the FK bake.")
    if any(str(curve.data_path).endswith(".scale") for curve in iter_action_fcurves(action)):
        errors.append("APPROVAL BLOCKED: Motion Studio Action contains scale animation.")
    pose_health = motion.read_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, "Motion Studio pose health")
    if pose_health is None:
        errors.append("APPROVAL BLOCKED: Motion Studio pose-health proof is missing.")
    elif pose_health.get("status") != "PASS":
        detail = (
            (pose_health.get("errors") or pose_health.get("warnings"))
            or ["pose-health validation did not pass."]
        )[0]
        errors.append("APPROVAL BLOCKED: " + str(detail))
    deform_names = {
        mapping_name
        for arm_side in ("l", "r")
        for role_name in (
            "shoulder_" + arm_side,
            "upper_arm_" + arm_side,
            "lower_arm_" + arm_side,
            "hand_" + arm_side,
        )
        for mapping_name in [skin_and_bones.forge_mapping(armature).get(role_name, "")]
        if mapping_name
    }
    if any(curve.data_path in {f'pose.bones["{name}"].location' for name in deform_names} for curve in iter_action_fcurves(action)):
        errors.append("APPROVAL BLOCKED: Motion Studio Action animates local translation on the deform arm chain.")
    return errors


def require_approval_ready(context, action, *, armature=None):
    errors = approval_errors(context, action, armature=armature)
    if errors:
        raise RuntimeError(" ".join(errors))
    return motion.read_json(action, motion.MOTION_VALIDATION_PROPERTY, "Motion Studio validation")


def _intended_targeting_for_bypass(context, action, recipe, digest):
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    schedule = motion.control_frame_schedule(recipe, fps)
    accepted_validation = {
        "status": "PASS",
        "activeContact": True,
        "contactTimeSeconds": max(
            0.0,
            (float(schedule["CONTACT"]) - float(schedule["START"])) / max(fps, 0.001),
        ),
    }
    targeting = motion.targeting_metadata(recipe, accepted_validation)
    targeting["technicalChecksBypassed"] = True
    targeting["bypassInputDigest"] = digest
    motion.stamp_json(action, motion.TARGETING_PROPERTY, targeting)
    return targeting


def bypass_failed_checks_and_save(context):
    """Explicitly approve the exact current preview while preserving failures."""

    from . import approve_draft_action, find_armature

    action = current_action(context)
    if not bool(action.get("dsb_draft", False)):
        raise RuntimeError("BYPASS saves the current Motion Studio draft only.")
    recipe = motion.read_motion_recipe(action)
    if recipe is None:
        raise RuntimeError("The current draft has no Motion Studio recipe.")
    armature = find_armature(context)
    digest = validation_input_digest(armature, action, recipe)
    if not bool(action.get("dsb_offensive_previewed", False)):
        raise RuntimeError("Preview this exact animation before bypassing its failed checks.")
    if str(action.get("dsb_motion_preview_digest", "")) != digest:
        raise RuntimeError("The preview is stale. Replay this exact animation before bypassing its failed checks.")
    errors = approval_errors(context, action, armature=armature)
    if not errors:
        raise RuntimeError("This animation passes the normal checks; use APPROVE instead of BYPASS.")

    validation = motion.read_json(action, motion.MOTION_VALIDATION_PROPERTY, "Motion Studio validation") or {}
    pose_health = motion.read_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, "Motion Studio pose health") or {}
    record = {
        "schema": MOTION_BYPASS_SCHEMA,
        "acceptedAtUtc": datetime.now(timezone.utc).isoformat(),
        "decision": "USER_EXPLICIT_BYPASS",
        "exportAllowed": True,
        "inputDigest": digest,
        "previewDigest": digest,
        "recipeDigest": motion.stable_digest(recipe),
        "validationStatus": str(validation.get("status", "MISSING")),
        "poseHealthStatus": str(pose_health.get("status", "MISSING")),
        "bypassedErrors": [str(value) for value in errors],
        "validationErrors": [str(value) for value in validation.get("errors", [])],
        "validationWarnings": [str(value) for value in validation.get("warnings", [])],
        "poseErrors": [str(value) for value in pose_health.get("errors", [])],
        "poseWarnings": [str(value) for value in pose_health.get("warnings", [])],
    }
    motion.stamp_json(action, MOTION_BYPASS_PROPERTY, record)
    action["dsb_motion_bypass_active"] = True
    action["dsb_motion_approval_mode"] = "USER_EXPLICIT_BYPASS"

    # A failed path does not normally produce runtime targeting metadata. The
    # user's override accepts the authored target/contact timing, so stamp that
    # intended launch relationship explicitly for game export.
    targeting = motion.read_json(action, motion.TARGETING_PROPERTY, "Offensive targeting metadata")
    if targeting is None or motion.validate_targeting_metadata(targeting):
        targeting = _intended_targeting_for_bypass(context, action, recipe, digest)

    approved = approve_draft_action(
        context,
        recipe["actionKind"],
        bypass_motion_checks=True,
    )
    record["approvedAction"] = approved.name
    motion.stamp_json(approved, MOTION_BYPASS_PROPERTY, record)
    approved["dsb_motion_bypass_active"] = True
    approved["dsb_motion_approval_mode"] = "USER_EXPLICIT_BYPASS"
    on_action_approved(approved)
    return approved, record


def validated_targeting_record(context, action, *, require_current=True, armature=None):
    recipe = motion.read_motion_recipe(action)
    if recipe is None:
        return None
    if require_current:
        require_approval_ready(context, action, armature=armature)
    record = motion.read_json(action, motion.TARGETING_PROPERTY, "Offensive targeting metadata")
    errors = motion.validate_targeting_metadata(record or {})
    if errors and bypass_is_current(context, action, armature=armature):
        from . import find_armature

        armature = armature or find_armature(context)
        digest = validation_input_digest(armature, action, recipe)
        record = _intended_targeting_for_bypass(context, action, recipe, digest)
        errors = motion.validate_targeting_metadata(record)
    if errors:
        raise ValueError("Invalid offensive targeting metadata: " + " ".join(errors))
    return deepcopy(record)


def on_action_approved(action):
    recipe = motion.read_motion_recipe(action)
    if recipe is None:
        return action
    _store_session(action, recipe)
    for helper in _owned_objects():
        helper["dsb_motion_studio_action"] = action.name
    validation = motion.read_json(action, motion.MOTION_VALIDATION_PROPERTY, "Motion Studio validation") or {}
    action["dsb_motion_geometry_valid"] = str(validation.get("status", "")) == "PASS"
    action["dsb_motion_artist_approved"] = True
    action["dsb_motion_checks_bypassed"] = bool(bypass_record(action))
    return action


def promote_current_master(context, label=""):
    action = current_action(context)
    if not bool(action.get("dsb_approved", False)) or bool(action.get("dsb_draft", False)):
        raise RuntimeError("Approve the reviewed Motion Studio Action before promotion.")
    require_approval_ready(context, action)
    recipe = motion.read_motion_recipe(action)
    safe = re.sub(r"[^a-z0-9]+", "_", (label or action.name).lower()).strip("_")[:40] or "reviewed_attack"
    master_id = "user_" + safe + "_" + motion.stable_digest(recipe)[:8]
    master = motion.promoted_master_from_recipe(
        recipe,
        master_id,
        label or action.name,
        source_action=action.name,
        source_clip_id=str(action.get(animation_library.CLIP_ID_PROPERTY, "")),
    )
    library = _load_master_library(context.scene)
    library["masters"] = [value for value in library["masters"] if value["masterId"] != master_id] + [master]
    context.scene[motion.MOTION_MASTER_LIBRARY_PROPERTY] = motion.stable_json(library)
    runtime_rig = bpy.data.objects.get(attachment_sockets.RUNTIME_ARMATURE_NAME)
    if runtime_rig is not None:
        runtime_rig[motion.MOTION_MASTER_LIBRARY_PROPERTY] = motion.stable_json(library)
    action[motion.MOTION_MASTER_PROPERTY] = motion.stable_json(master)
    action["dsb_motion_promoted_master_id"] = master_id
    context.scene.daf_settings.motion_validation_status = "PROMOTED MASTER — " + master["label"]
    return master


def jump_key_pose(context, pose):
    from . import find_armature

    action = current_action(context)
    recipe = motion.read_motion_recipe(action)
    schedule = motion.control_frame_schedule(
        recipe,
        context.scene.render.fps / max(context.scene.render.fps_base, 0.001),
    )
    key = {"ANTICIPATION": "ANTICIPATION", "CONTACT": "CONTACT", "FOLLOW_THROUGH": "FOLLOW_THROUGH"}.get(str(pose))
    if key is None:
        raise RuntimeError(f"Unknown Motion Studio key pose {pose!r}.")
    if key == "CONTACT":
        settings = context.scene.daf_settings
        settings.motion_show_target = True
        settings.motion_show_trail = True
        settings.motion_show_plane = True
        review_roles = {
            "TARGET_ROOT",
            "STRIKE_GEOMETRY",
            "TRAIL_ACTIVE",
            "TRAIL_MARKER_CONTACT",
        }
        if not any(
            str(obj.get("dsb_motion_studio_role", "")) in review_roles
            for obj in _owned_objects()
        ):
            armature = find_armature(context)
            samples = sample_baked_weapon_path(context, armature, action, recipe)
            validation = motion.read_json(action, motion.MOTION_VALIDATION_PROPERTY, "Motion Studio validation")
            build_helpers(
                armature,
                action,
                recipe,
                samples=samples,
                validation=validation,
                include_controls=False,
            )
        motion_display_updated(settings, context)
    context.scene.frame_set(int(schedule[key]))
    return int(schedule[key])


def recover_sessions():
    state = _session()
    if not state or not bool(state.get("helpersRequired", False)):
        return None
    action = bpy.data.actions.get(str(state.get("actionName", "")))
    if action is None:
        return None
    recipe = motion.read_motion_recipe(action)
    if recipe is None:
        return None
    armature = bpy.data.objects.get(attachment_sockets.RUNTIME_ARMATURE_NAME)
    if armature is None:
        return None
    if not _owned_objects():
        if str(state.get("helperMode", "REVIEW")) == "WEAPON_PREVIEW":
            build_preview_weapon(armature, action, recipe)
        else:
            samples = sample_baked_weapon_path(bpy.context, armature, action, recipe)
            validation = motion.read_json(action, motion.MOTION_VALIDATION_PROPERTY, "Motion Studio validation")
            build_helpers(
                armature,
                action,
                recipe,
                samples=samples,
                validation=validation,
                include_controls=bool(state.get("editableControlsRequired", True)),
            )
    settings = getattr(bpy.context.scene, "daf_settings", None)
    if settings is not None:
        _cache_pose_health(
            settings,
            motion.read_json(action, motion.MOTION_POSE_HEALTH_PROPERTY, "Motion Studio pose health"),
        )
    return state


@persistent
def _load_post_recover_sessions(_filepath):
    try:
        recover_sessions()
    except (RuntimeError, ValueError) as exc:
        settings = getattr(getattr(bpy.context, "scene", None), "daf_settings", None)
        if settings is not None:
            settings.motion_validation_status = "HELPER RECOVERY FAILED — " + str(exc)


def register_handlers():
    unregister_handlers()
    bpy.app.handlers.load_post.append(_load_post_recover_sessions)


def unregister_handlers():
    for handler in list(bpy.app.handlers.load_post):
        if (
            getattr(handler, "__name__", "") == "_load_post_recover_sessions"
            and getattr(handler, "__module__", "") == __name__
        ):
            bpy.app.handlers.load_post.remove(handler)


class _MotionOperator(Operator):
    def failed(self, exc):
        self.report({"ERROR"}, str(exc))
        settings = getattr(bpy.context.scene, "daf_settings", None)
        if settings is not None:
            settings.motion_validation_status = "ERROR — " + str(exc)
        return {"CANCELLED"}


class DAF_OT_motion_studio_natural_fit(_MotionOperator):
    bl_idname = "daf.motion_studio_natural_fit"
    bl_label = "Natural Auto Fit"
    bl_description = "Measure the canonical arm and choose a comfortable target distance and legal blade contact point"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            result = natural_fit_settings(context)
            self.report(
                {"INFO"},
                f"Natural fit: target {result['recipe']['target']['distanceMeters']:.2f} m; "
                f"comfortable arm reach {result['reachModel']['comfortableReachMeters']:.2f} m.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_reset_natural(_MotionOperator):
    bl_idname = "daf.motion_studio_reset_natural"
    bl_label = "Reset to Natural"
    bl_description = "Restore restrained Natural body style and character-adaptive target fitting"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            reset_to_natural(context)
            self.report({"INFO"}, "Motion Studio style reset to Natural; build to apply Auto Fit.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_build_from_master(_MotionOperator):
    bl_idname = "daf.motion_studio_build_from_master"
    bl_label = "Build From Motion Master"
    bl_description = "Create target and weapon controls, solve the canonical body around the weapon path, and bake ordinary FK curves"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            result = build_from_master(context, exploratory=True)
            report = result["validation"]
            self.report(
                {"INFO" if report["status"] == "PASS" else "WARNING"},
                f"Built {result['action'].name}; baked-path {report['status']}. Preview remains available.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_refresh_vip(_MotionOperator):
    bl_idname = "daf.motion_studio_refresh_vip"
    bl_label = "Generate and Preview Attack"
    bl_description = "Bake every live slider and meter, replace the visible weapon proxy, and preview even when approval checks fail"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            result = refresh_vip_attack(context, start_playback=True)
            report = result["validation"]
            level = "INFO" if report["status"] == "PASS" else "WARNING"
            self.report(
                {level},
                f"Previewing {result['action'].name}; path {report['status']}, "
                f"pose {result['preview']['poseStatus']}"
                + (" — ready to approve." if result["preview"]["approvalReady"] else " — preview only; approval blocked."),
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_rebuild_body_solve(_MotionOperator):
    bl_idname = "daf.motion_studio_rebuild_body_solve"
    bl_label = "Rebuild Body Solve"
    bl_description = "Read edited target/trajectory controls, solve IK, bake canonical FK, remove constraints, and resample the real weapon path"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            result = rebuild_body_solve(context, exploratory=True)
            self.report({"INFO" if result["validation"]["status"] == "PASS" else "WARNING"}, f"Rebuilt {result['action'].name}; baked-path {result['validation']['status']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_jump_key_pose(_MotionOperator):
    bl_idname = "daf.motion_studio_jump_key_pose"
    bl_label = "Jump to Motion Key Pose"
    bl_options = {"REGISTER"}

    pose: StringProperty()

    def execute(self, context):
        try:
            frame = jump_key_pose(context, self.pose)
            self.report({"INFO"}, f"{self.pose.replace('_', ' ').title()} · frame {frame}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_validate_baked_path(_MotionOperator):
    bl_idname = "daf.motion_studio_validate_baked_path"
    bl_label = "Validate Baked Weapon Path"
    bl_description = "Sample the actual canonical FK hand/socket/proxy path and test target contact, ACTIVE timing, plane error, and direction"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            report = validate_baked_action(context)
            if report["status"] != "PASS":
                self.report({"ERROR"}, "; ".join(report.get("errors", [])[:3]))
                return {"CANCELLED"}
            self.report({"INFO"}, f"PASS · {report['trajectoryFamily']} contacted {report['targetZone']} during ACTIVE at {report['contactTimeSeconds']:.3f}s.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_preview(_MotionOperator):
    bl_idname = "daf.motion_studio_preview"
    bl_label = "Preview Motion Studio Attack"
    bl_description = "Play the baked FK attack; CONTACT can reveal optional target and trail review geometry"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            result = preview_motion(
                context,
                start_playback=True,
                build_review_helpers=False,
            )
            self.report({"INFO"}, f"Previewing {result['action']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_approve(_MotionOperator):
    bl_idname = "daf.motion_studio_approve"
    bl_label = "Approve Target-Constrained Attack"
    bl_description = "Approve only after current preview proof and successful baked FK target-path validation"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            from . import approve_draft_action

            action = current_action(context)
            recipe = motion.read_motion_recipe(action)
            require_approval_ready(context, action)
            approved = approve_draft_action(context, recipe["actionKind"])
            on_action_approved(approved)
            self.report({"INFO"}, f"Approved {approved.name}; target path remains authored and non-homing.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_bypass_and_save(_MotionOperator):
    bl_idname = "daf.motion_studio_bypass_and_save"
    bl_label = "Bypass Failed Checks and Save"
    bl_description = (
        "Explicitly accept the exact current preview despite failed Motion Studio checks, "
        "record the bypassed failures, and allow game export"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            approved, record = bypass_failed_checks_and_save(context)
            self.report(
                {"WARNING"},
                f"Saved {approved.name} with explicit bypass of "
                f"{len(record['bypassedErrors'])} failed check(s).",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_promote_master(_MotionOperator):
    bl_idname = "daf.motion_studio_promote_master"
    bl_label = "Promote to Motion Master"
    bl_description = "Deliberately promote an approved reviewed target/trajectory recipe for reuse through the weapon-first solver"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            master = promote_current_master(context)
            self.report({"INFO"}, f"Promoted reusable Motion Master {master['label']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_repair_helpers(_MotionOperator):
    bl_idname = "daf.motion_studio_repair_helpers"
    bl_label = "Repair Motion Studio Helpers"
    bl_description = "Reconstruct the owned authoring-only target, proxy, controls, plane, and baked trail from saved Action state"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            from . import find_armature

            armature = find_armature(context)
            action = current_action(context)
            recipe = motion.read_motion_recipe(action)
            samples = sample_baked_weapon_path(context, armature, action, recipe)
            validation = motion.read_json(action, motion.MOTION_VALIDATION_PROPERTY, "Motion Studio validation")
            helpers = build_helpers(armature, action, recipe, samples=samples, validation=validation)
            self.report({"INFO"}, f"Repaired {len(helpers)} authoring-only Motion Studio helpers.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_motion_studio_remove_helpers(_MotionOperator):
    bl_idname = "daf.motion_studio_remove_helpers"
    bl_label = "Hide / Remove Motion Studio Helpers"
    bl_description = "Remove only Forge-owned Motion Studio viewport helpers; saved Action recipes remain intact"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = remove_helpers()
        self.report({"INFO"}, f"Removed {removed} Motion Studio helper object(s); no Action or socket changed.")
        return {"FINISHED"}


CLASSES = (
    DAF_OT_motion_studio_natural_fit,
    DAF_OT_motion_studio_reset_natural,
    DAF_OT_motion_studio_build_from_master,
    DAF_OT_motion_studio_refresh_vip,
    DAF_OT_motion_studio_rebuild_body_solve,
    DAF_OT_motion_studio_jump_key_pose,
    DAF_OT_motion_studio_validate_baked_path,
    DAF_OT_motion_studio_preview,
    DAF_OT_motion_studio_approve,
    DAF_OT_motion_studio_bypass_and_save,
    DAF_OT_motion_studio_promote_master,
    DAF_OT_motion_studio_repair_helpers,
    DAF_OT_motion_studio_remove_helpers,
)


__all__ = (
    "CLASSES",
    "MOTION_STUDIO_COLLECTION",
    "MOTION_STUDIO_HELPER_ROLE",
    "approval_errors",
    "bypass_failed_checks_and_save",
    "bypass_is_current",
    "bypass_record",
    "auto_fit_recipe",
    "available_masters",
    "build_from_master",
    "build_helpers",
    "current_action",
    "invalidate_action",
    "invalidate_active_session",
    "motion_master_items",
    "motion_master_updated",
    "motion_macro_updated",
    "motion_feel_updated",
    "motion_proxy_updated",
    "motion_style_updated",
    "motion_display_updated",
    "motion_setting_updated",
    "on_action_approved",
    "natural_fit_settings",
    "preview_motion",
    "promote_current_master",
    "rebuild_body_solve",
    "refresh_vip_attack",
    "recover_sessions",
    "register_handlers",
    "remove_helpers",
    "reset_to_natural",
    "require_approval_ready",
    "sample_baked_weapon_path",
    "validate_baked_action",
    "validated_targeting_record",
    "validation_input_digest",
    "unregister_handlers",
)
