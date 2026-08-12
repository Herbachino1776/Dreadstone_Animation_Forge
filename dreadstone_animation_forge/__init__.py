bl_info = {
    "name": "Dreadstone Animation Forge",
    "author": "Dreadstone Black",
    "version": (5, 4, 1),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar > Dreadstone",
    "description": "Animation authoring, protected damage assets, and registered-region trauma-field shape-key authoring.",
    "category": "Animation",
}

import bpy, math, re, json, os, struct, sys, importlib
from datetime import datetime, timezone
from mathutils import Vector, Quaternion
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from . import animation_library
from . import offensive_actions
from . import offensive_motion
from . import parameter_schema
from .anatomy import blender_adapter as anatomy_blender
from .anatomy import persistence as anatomy_persistence
from .anatomy.profiles import CANONICAL_HUMANOID_MAPPING, HUMANOID_ALIASES
from .anatomy.schema import axis_vector as anatomy_axis_vector
from .anatomy import skin_and_bones as sbf_handoff

# Public compatibility aliases. Their authority moved into DSB_HUMANOID_V1;
# existing scripts importing these names continue to receive the same values.
ALIASES = {role: list(aliases) for role, aliases in HUMANOID_ALIASES.items()}

def detect_canonical_humanoid_profile(arm):
    required = set(CANONICAL_HUMANOID_MAPPING.values())
    available = {bone.name for bone in arm.data.bones}
    contract = sbf_handoff.contract(arm)
    return bool(
        contract
        and contract.get("canonicalYPlus", False)
        and available == required
    )

def norm(name):
    s = name.lower().replace("mixamorig","")
    return re.sub(r"[^a-z0-9]","",s)

def descendants(obj):
    out, stack = set(), list(obj.children)
    while stack:
        child = stack.pop()
        if child in out:
            continue
        out.add(child)
        stack.extend(child.children)
    return out

def has_ancestor(obj, ancestor):
    """Blender 3.6-compatible parent-chain test.

    Some supported Blender builds do not expose a recursive-parent convenience
    property, so adoption walks ``Object.parent`` directly. The
    visited set also makes the helper safe against malformed cyclic imports.
    """
    current = getattr(obj, "parent", None)
    visited = set()
    while current is not None and current not in visited:
        if current == ancestor:
            return True
        visited.add(current)
        current = getattr(current, "parent", None)
    return False

def related(context):
    seeds = set(context.selected_objects)
    if not seeds and context.active_object:
        seeds.add(context.active_object)
    if not seeds:
        raise RuntimeError("Select the imported character, or press A in an otherwise empty scene.")
    out = set(seeds)
    for obj in list(seeds):
        out.update(descendants(obj))
        p = obj.parent
        while p:
            out.add(p)
            p = p.parent
    return out

def find_armature(context):
    objects = related(context)
    candidates = [o for o in objects if o.type == 'ARMATURE']
    for obj in objects:
        if obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'ARMATURE' and mod.object:
                    candidates.append(mod.object)
    if not candidates:
        raise RuntimeError("No armature found in the selected character.")
    return max(set(candidates), key=lambda a: len(a.data.bones))

def character_meshes(context):
    meshes = [o for o in related(context) if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("No character mesh found.")
    return meshes

def world_bounds(context, meshes):
    deps = context.evaluated_depsgraph_get()
    mn = Vector((1e30,1e30,1e30))
    mx = Vector((-1e30,-1e30,-1e30))
    count = 0
    for obj in meshes:
        e = obj.evaluated_get(deps)
        mesh = None
        try:
            mesh = e.to_mesh()
            if not mesh:
                continue
            for v in mesh.vertices:
                p = e.matrix_world @ v.co
                mn.x, mn.y, mn.z = min(mn.x,p.x), min(mn.y,p.y), min(mn.z,p.z)
                mx.x, mx.y, mx.z = max(mx.x,p.x), max(mx.y,p.y), max(mx.z,p.z)
                count += 1
        finally:
            if mesh:
                e.to_mesh_clear()
    if not count:
        raise RuntimeError("Could not measure the selected mesh.")
    return mn, mx


def world_bounds_for_bone_groups(
    context,
    meshes,
    bone_names,
    *,
    minimum_weight=0.20,
):
    """Measure evaluated vertices influenced by selected deform bones."""

    requested = {str(name) for name in bone_names if name}
    if not requested:
        raise RuntimeError("No deform groups were supplied for weighted bounds.")
    deps = context.evaluated_depsgraph_get()
    minimum = Vector((1.0e30, 1.0e30, 1.0e30))
    maximum = Vector((-1.0e30, -1.0e30, -1.0e30))
    count = 0
    for obj in meshes:
        group_indices = {
            group.index
            for group in obj.vertex_groups
            if group.name in requested
        }
        if not group_indices:
            continue
        evaluated = obj.evaluated_get(deps)
        mesh = None
        try:
            mesh = evaluated.to_mesh()
            if mesh is None:
                continue
            for vertex in mesh.vertices:
                influence = sum(
                    float(group.weight)
                    for group in vertex.groups
                    if group.group in group_indices
                )
                if influence < float(minimum_weight):
                    continue
                point = evaluated.matrix_world @ vertex.co
                minimum.x = min(minimum.x, point.x)
                minimum.y = min(minimum.y, point.y)
                minimum.z = min(minimum.z, point.z)
                maximum.x = max(maximum.x, point.x)
                maximum.y = max(maximum.y, point.y)
                maximum.z = max(maximum.z, point.z)
                count += 1
        finally:
            if mesh is not None:
                evaluated.to_mesh_clear()
    if not count:
        raise RuntimeError(
            "Could not measure mesh vertices weighted to: "
            + ", ".join(sorted(requested))
            + "."
        )
    return minimum, maximum, count


def torso_contact_bounds(context, meshes, mapping):
    """Measure the body core without allowing arms/hands to define contact."""

    role_names = {
        role: mapping.get(role, "")
        for role in ("hips", "spine", "spine_mid", "chest")
        if mapping.get(role)
    }
    minimum, maximum, count = world_bounds_for_bone_groups(
        context,
        meshes,
        role_names.values(),
    )
    regions = {}
    for role, bone_name in role_names.items():
        try:
            region_minimum, region_maximum, region_count = (
                world_bounds_for_bone_groups(
                    context,
                    meshes,
                    (bone_name,),
                    minimum_weight=0.25,
                )
            )
        except RuntimeError:
            continue
        regions[role] = {
            "minimum_z": float(region_minimum.z),
            "maximum_z": float(region_maximum.z),
            "vertex_count": int(region_count),
        }
    return {
        "minimum": minimum,
        "maximum": maximum,
        "vertex_count": int(count),
        "regions": regions,
        "required_roles": sorted(role_names),
        "missing_regions": sorted(set(role_names) - set(regions)),
    }

def bone_ancestors(bone):
    out = []
    current = bone
    while current:
        out.append(current)
        current = current.parent
    return out

def nearest_common_ancestor(a, b):
    if not a or not b:
        return None
    b_dist = {bone.name: index for index, bone in enumerate(bone_ancestors(b))}
    best = None
    for a_index, bone in enumerate(bone_ancestors(a)):
        if bone.name in b_dist:
            score = a_index + b_dist[bone.name]
            if best is None or score < best[0]:
                best = (score, bone)
    return best[1] if best else None

def child_on_path(ancestor, descendant):
    if not ancestor or not descendant:
        return None
    current = descendant
    previous = descendant
    while current and current != ancestor:
        previous = current
        current = current.parent
    return previous if current == ancestor and previous != ancestor else None

def bone_center(bone):
    return (bone.head_local + bone.tail_local) * 0.5

def best_upward_child(parent, excluded_names=None):
    excluded_names = excluded_names or set()
    parent_center = bone_center(parent)
    candidates = []
    for child in parent.children:
        if child.name in excluded_names:
            continue
        center = bone_center(child)
        rise = center.z - parent_center.z
        direction = child.tail_local - child.head_local
        verticality = abs(direction.normalized().z) if direction.length else 0.0
        horizontal = abs(center.x - parent_center.x) + abs(center.y - parent_center.y)
        score = rise * 20.0 + verticality * 3.0 - horizontal
        if rise > -0.001:
            candidates.append((score, child))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None

def apply_manual_mapping(arm, settings, result):
    if not settings:
        return
    manual = {
        "hips": settings.manual_hips,
        "spine": settings.manual_spine,
        "chest": settings.manual_chest,
    }
    for role, bone_name in manual.items():
        if bone_name and arm.data.bones.get(bone_name):
            result[role] = bone_name

def map_bones(arm, settings=None):
    bones = list(arm.data.bones)
    result = {}

    # Skin & Bones owns this exact semantic map. Its explicit metadata is the
    # only humanoid animation authority; bone-name resemblance is not enough.
    sbf = sbf_handoff.contract(arm)
    if sbf is not None:
        sbf_handoff.require_canonical_yplus(arm, label="Rig mapping")
        return dict(sbf["roleMapping"])
    # First pass: familiar bone names. Exact profile entries are preserved.
    for role, aliases in ALIASES.items():
        best = None
        for bone in bones:
            n = norm(bone.name)
            score = 0
            for alias in aliases:
                a = norm(alias)
                if n == a:
                    score = max(score, 100)
                elif n.startswith(a) or n.endswith(a):
                    score = max(score, 80)
                elif a in n:
                    score = max(score, 60)

            if role.endswith("_l"):
                if "left" in n or n.endswith("l"):
                    score += 10
                if "right" in n or n.endswith("r"):
                    score -= 40
            if role.endswith("_r"):
                if "right" in n or n.endswith("r"):
                    score += 10
                if "left" in n or n.endswith("l"):
                    score -= 40

            if score > 0 and (best is None or score > best[0]):
                best = (score, bone.name)
        if best and role not in result:
            result[role] = best[1]

    # Pelvis fallback: the closest shared ancestor of the two upper legs.
    left_thigh = arm.data.bones.get(result.get("thigh_l", ""))
    right_thigh = arm.data.bones.get(result.get("thigh_r", ""))
    if "hips" not in result and left_thigh and right_thigh:
        common = nearest_common_ancestor(left_thigh, right_thigh)
        if common:
            result["hips"] = common.name

    # Chest fallback: the closest shared ancestor of the two upper arms.
    left_arm = arm.data.bones.get(result.get("upper_arm_l", ""))
    right_arm = arm.data.bones.get(result.get("upper_arm_r", ""))
    if "chest" not in result and left_arm and right_arm:
        common = nearest_common_ancestor(left_arm, right_arm)
        if common:
            result["chest"] = common.name

    hips = arm.data.bones.get(result.get("hips", ""))
    chest = arm.data.bones.get(result.get("chest", ""))

    # Spine fallback: use the lowest center-chain bone between pelvis and chest.
    if "spine" not in result and hips and chest:
        path_child = child_on_path(hips, chest)
        if path_child:
            result["spine"] = path_child.name

    # If no chest mapping exists, rise through the center chain from the pelvis.
    if hips and "spine" not in result:
        excluded = {
            name for name in (
                result.get("thigh_l"),
                result.get("thigh_r"),
            ) if name
        }
        spine = best_upward_child(hips, excluded)
        if spine:
            result["spine"] = spine.name

    spine = arm.data.bones.get(result.get("spine", ""))
    if spine and "chest" not in result:
        chain = []
        current = spine
        excluded = {
            name for name in (
                result.get("upper_arm_l"),
                result.get("upper_arm_r"),
            ) if name
        }
        for _ in range(3):
            child = best_upward_child(current, excluded)
            if not child:
                break
            chain.append(child)
            current = child
        if chain:
            result["chest"] = chain[-1].name

    # Explicit user choices always win.
    apply_manual_mapping(arm, settings, result)
    return result

def unique_action(base):
    if base not in bpy.data.actions:
        return base
    i = 2
    while f"{base}_v{i:03d}" in bpy.data.actions:
        i += 1
    return f"{base}_v{i:03d}"

def vectors(settings, armature=None):
    """Compatibility accessor backed by the authoritative orientation service."""
    if str(getattr(settings, "facing", "POS_Y")) != "POS_Y":
        settings.facing = "POS_Y"
        settings.invert_knees = False
        settings.invert_elbows = False
    forward_axis = anatomy_blender.authoritative_forward_axis(armature, settings)
    if forward_axis != "+Y":
        raise RuntimeError(
            "Animation Forge is Y+ only. Convert or rebuild this character in "
            "Skin & Bones before generating animation."
        )
    fwd = Vector(anatomy_axis_vector(forward_axis))
    up = Vector(anatomy_axis_vector("+Z"))
    side = up.cross(fwd).normalized()
    return fwd, side, up

def reset_pose(arm, mapping):
    for name in set(mapping.values()):
        pb = arm.pose.bones.get(name)
        if pb:
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = Quaternion((1,0,0,0))
            pb.location = (0,0,0)
            pb.scale = (1,1,1)

def local_axis(pb, axis):
    a = pb.bone.matrix_local.to_3x3().inverted() @ axis
    return a.normalized() if a.length else Vector((1,0,0))

def rotate(arm, mapping, role, axis, degrees):
    name = mapping.get(role)
    pb = arm.pose.bones.get(name) if name else None
    if pb and abs(degrees) > 1e-6:
        pb.rotation_quaternion = Quaternion(local_axis(pb,axis), math.radians(degrees)) @ pb.rotation_quaternion

def rotate_local(arm, mapping, role, local_axis_vector, degrees):
    """Rotate a pose bone around one of its own local axes.

    Blender bones use local Y along the length of the bone. This is ideal for
    safe upper-arm, forearm, and wrist roll/twist controls because it does not
    translate or scale the rig.
    """
    name = mapping.get(role)
    pose_bone = arm.pose.bones.get(name) if name else None
    if pose_bone is None or abs(degrees) <= 1.0e-6:
        return

    axis = Vector(local_axis_vector)
    if axis.length <= 1.0e-8:
        return

    pose_bone.rotation_quaternion = (
        Quaternion(axis.normalized(), math.radians(degrees))
        @ pose_bone.rotation_quaternion
    )


def rotate_for_disabled_inheritance(arm, mapping, roles, axis, degrees):
    """Carry a parent rotation into bones that explicitly ignore it.

    Some production rigs disable ``use_inherit_rotation`` throughout their
    deform chains. Rotating only the pelvis on those rigs moves child heads but
    leaves every child pointing upright. A terminal fall therefore needs the
    same gross pitch on each inheritance break before its local limp offsets
    are applied.
    """

    for role in roles:
        bone_name = mapping.get(role)
        data_bone = arm.data.bones.get(bone_name) if bone_name else None
        if data_bone is not None and not bool(data_bone.use_inherit_rotation):
            rotate(arm, mapping, role, axis, degrees)


def rotation_inheritance_disabled(arm, mapping, role):
    """Return whether a mapped bone ignores its parent's pose rotation."""

    bone_name = mapping.get(role)
    data_bone = arm.data.bones.get(bone_name) if bone_name else None
    return bool(data_bone is not None and not data_bone.use_inherit_rotation)


def apply_arm_hand_pose_polish(arm, mapping, settings, side_axis):
    """Overlay safe rotation-only arm and hand adjustments."""
    if not settings.pose_polish_enabled:
        return

    # Upper-arm forward/back uses the character's left-right axis.
    rotate(
        arm,
        mapping,
        "upper_arm_l",
        side_axis,
        settings.left_upper_arm_forward
    )
    rotate(
        arm,
        mapping,
        "upper_arm_r",
        side_axis,
        settings.right_upper_arm_forward
    )

    # Bone-local Y follows the limb and creates clean roll/twist.
    rotate_local(
        arm,
        mapping,
        "upper_arm_l",
        (0.0, 1.0, 0.0),
        settings.left_upper_arm_roll
    )
    rotate_local(
        arm,
        mapping,
        "upper_arm_r",
        (0.0, 1.0, 0.0),
        settings.right_upper_arm_roll
    )

    # Independent elbow flex is applied around the same character-space axis
    # used by generated limb bends. This keeps the control useful on rigs whose
    # local forearm axes differ while still respecting Invert Elbows.
    elbow_sign = 1.0 if settings.invert_elbows else -1.0
    rotate(
        arm,
        mapping,
        "lower_arm_l",
        side_axis,
        settings.left_elbow_flex * elbow_sign
    )
    rotate(
        arm,
        mapping,
        "lower_arm_r",
        side_axis,
        settings.right_elbow_flex * elbow_sign
    )
    rotate_local(
        arm,
        mapping,
        "lower_arm_l",
        (0.0, 1.0, 0.0),
        settings.left_forearm_twist
    )
    rotate_local(
        arm,
        mapping,
        "lower_arm_r",
        (0.0, 1.0, 0.0),
        settings.right_forearm_twist
    )

    # Wrist rotations are entirely local to the hand bone:
    # X = flex/extend, Z = side bend, Y = roll.
    rotate_local(
        arm,
        mapping,
        "hand_l",
        (1.0, 0.0, 0.0),
        settings.left_wrist_flex
    )
    rotate_local(
        arm,
        mapping,
        "hand_r",
        (1.0, 0.0, 0.0),
        settings.right_wrist_flex
    )
    rotate_local(
        arm,
        mapping,
        "hand_l",
        (0.0, 0.0, 1.0),
        settings.left_wrist_side
    )
    rotate_local(
        arm,
        mapping,
        "hand_r",
        (0.0, 0.0, 1.0),
        settings.right_wrist_side
    )
    rotate_local(
        arm,
        mapping,
        "hand_l",
        (0.0, 1.0, 0.0),
        settings.left_wrist_roll
    )
    rotate_local(
        arm,
        mapping,
        "hand_r",
        (0.0, 1.0, 0.0),
        settings.right_wrist_roll
    )


def offset(arm, mapping, role, world_vec):
    name = mapping.get(role)
    pb = arm.pose.bones.get(name) if name else None
    if not pb:
        return
    arm_vec = arm.matrix_world.to_3x3().inverted() @ world_vec
    pb.location += pb.bone.matrix_local.to_3x3().inverted() @ arm_vec

def key_pose(arm, mapping, frame):
    for name in set(mapping.values()):
        pb = arm.pose.bones.get(name)
        if pb:
            pb.keyframe_insert("rotation_quaternion", frame=frame, group=name)
            pb.keyframe_insert("location", frame=frame, group=name)


DEATH_TERMINAL_MAX_HEIGHT_RATIO = 0.50
DEATH_TERMINAL_MAX_TORSO_HEIGHT_RATIO = 0.30
DEATH_TORSO_CONTACT_TOLERANCE_RATIO = 0.031


def ground_current_pose(
    context,
    arm,
    mapping,
    meshes,
    *,
    target_lowest_z,
    torso_contact=False,
):
    """Align the character through root motion using whole-body or torso contact."""
    context.view_layer.update()
    torso = torso_contact_bounds(context, meshes, mapping) if torso_contact else None
    if torso is None:
        minimum, _maximum = world_bounds(context, meshes)
    else:
        minimum = torso["minimum"]
    correction = float(target_lowest_z) - float(minimum.z)
    carrier_role = (
        "root"
        if mapping.get("root") and arm.pose.bones.get(mapping.get("root"))
        else "hips"
    )
    if abs(correction) > 1.0e-7:
        offset(
            arm,
            mapping,
            carrier_role,
            Vector((0.0, 0.0, correction)),
        )
        context.view_layer.update()
    grounded_minimum, _grounded_maximum = world_bounds(context, meshes)
    safety_lift = 0.0
    if torso_contact and float(grounded_minimum.z) < float(target_lowest_z):
        # Torso contact is authoritative, but a head or limb may not visibly
        # penetrate the preview floor. Lift only enough to clear the complete
        # mesh, then let the per-region torso tolerance reject a body that was
        # actually being supported far above the floor by that secondary part.
        safety_lift = float(target_lowest_z) - float(grounded_minimum.z)
        offset(
            arm,
            mapping,
            carrier_role,
            Vector((0.0, 0.0, safety_lift)),
        )
        correction += safety_lift
        context.view_layer.update()
        grounded_minimum, _grounded_maximum = world_bounds(context, meshes)
    grounded_torso = (
        torso_contact_bounds(context, meshes, mapping)
        if torso_contact
        else None
    )
    return {
        "correction": correction,
        "minimum_before": float(minimum.z),
        "minimum_after": float(grounded_minimum.z),
        "contact_minimum_after": float(
            grounded_torso["minimum"].z
            if grounded_torso is not None
            else grounded_minimum.z
        ),
        "carrier_role": carrier_role,
        "carrier_bone": str(mapping.get(carrier_role, "")),
        "torso_safety_lift": safety_lift,
        "torso": grounded_torso,
    }


def set_bone_location_linear(action, pose_bone):
    """Keep baked root/hips samples from overshooting between floor contacts."""
    location_path = pose_bone.path_from_id("location")
    for curve in iter_action_fcurves(action):
        if str(getattr(curve, "data_path", "")) != location_path:
            continue
        for keyframe in curve.keyframe_points:
            keyframe.interpolation = 'LINEAR'


def bake_grounded_death_motion(
    context,
    action,
    arm,
    mapping,
    meshes,
    frame_start,
    frame_end,
    *,
    ground_sink,
    terminal_frame,
    reference_height,
    maximum_terminal_height_ratio=DEATH_TERMINAL_MAX_HEIGHT_RATIO,
):
    """Bake signed floor alignment and require a low terminal body-contact pose."""
    carrier_role = "root" if mapping.get("root") else "hips"
    carrier = arm.pose.bones.get(mapping.get(carrier_role, ""))
    if carrier is None:
        raise RuntimeError("Death grounding requires the mapped top-level root bone.")

    target_lowest_z = -float(ground_sink)
    maximum_correction = 0.0
    maximum_upward_correction = 0.0
    maximum_downward_correction = 0.0
    worst_minimum = float("inf")
    grounded_frames = 0
    maximum_torso_safety_lift = 0.0
    frames = range(int(math.floor(frame_start)), int(math.ceil(frame_end)) + 1)
    for frame in frames:
        context.scene.frame_set(frame)
        terminal_contact = frame >= int(terminal_frame)
        result = ground_current_pose(
            context,
            arm,
            mapping,
            meshes,
            target_lowest_z=target_lowest_z,
            torso_contact=terminal_contact,
        )
        if abs(result["correction"]) > 1.0e-7:
            grounded_frames += 1
        maximum_correction = max(maximum_correction, abs(result["correction"]))
        maximum_upward_correction = max(
            maximum_upward_correction,
            result["correction"],
        )
        maximum_downward_correction = min(
            maximum_downward_correction,
            result["correction"],
        )
        worst_minimum = min(worst_minimum, result["minimum_after"])
        maximum_torso_safety_lift = max(
            maximum_torso_safety_lift,
            float(result["torso_safety_lift"]),
        )

        # Key every sampled root location. This is the actual runtime floor
        # correction and remains valid even when glTF force sampling is off.
        carrier.keyframe_insert("location", frame=frame, group=carrier.name)

    set_bone_location_linear(action, carrier)
    tolerance = 0.001
    if worst_minimum < target_lowest_z - tolerance:
        raise RuntimeError(
            "Death grounding could not keep the visible mesh above the preview "
            f"floor (lowest {worst_minimum:.4f} m, allowed "
            f"{target_lowest_z:.4f} m). Check root mapping and skin weights."
        )
    context.scene.frame_set(int(terminal_frame))
    context.view_layer.update()
    terminal_minimum, terminal_maximum = world_bounds(context, meshes)
    terminal_torso = torso_contact_bounds(context, meshes, mapping)
    terminal_height = float(terminal_maximum.z - terminal_minimum.z)
    terminal_torso_height = float(
        terminal_torso["maximum"].z - terminal_torso["minimum"].z
    )
    safe_reference_height = max(float(reference_height), 1.0e-6)
    terminal_height_ratio = terminal_height / safe_reference_height
    terminal_torso_height_ratio = terminal_torso_height / safe_reference_height
    if terminal_torso["missing_regions"]:
        raise RuntimeError(
            "Death grounding cannot verify the full torso because these "
            "canonical deform groups have no measurable weights: "
            + ", ".join(terminal_torso["missing_regions"])
            + "."
        )
    if terminal_height_ratio > float(maximum_terminal_height_ratio) + 1.0e-4:
        raise RuntimeError(
            "Death terminal pose is not flat enough for ground contact "
            f"({terminal_height:.4f} m / {safe_reference_height:.4f} m = "
            f"{terminal_height_ratio:.3f}; maximum "
            f"{float(maximum_terminal_height_ratio):.3f})."
        )
    if abs(float(terminal_minimum.z) - target_lowest_z) > tolerance:
        raise RuntimeError(
            "Death terminal pose did not finish flush on the preview floor "
            f"(lowest {float(terminal_minimum.z):.4f} m; target "
            f"{target_lowest_z:.4f} m)."
        )
    if terminal_torso_height_ratio > DEATH_TERMINAL_MAX_TORSO_HEIGHT_RATIO + 1.0e-4:
        raise RuntimeError(
            "Death terminal torso is not flat enough for full body-core contact "
            f"({terminal_torso_height_ratio:.3f}; maximum "
            f"{DEATH_TERMINAL_MAX_TORSO_HEIGHT_RATIO:.3f})."
        )
    contact_tolerance = max(
        0.02,
        min(0.08, safe_reference_height * DEATH_TORSO_CONTACT_TOLERANCE_RATIO),
    )
    floating_regions = {
        role: record["minimum_z"] - target_lowest_z
        for role, record in terminal_torso["regions"].items()
        if record["minimum_z"] - target_lowest_z > contact_tolerance
    }
    if floating_regions:
        detail = ", ".join(
            f"{role} {gap:.3f} m"
            for role, gap in sorted(floating_regions.items())
        )
        raise RuntimeError(
            "Death terminal torso is still floating above the floor: " + detail + "."
        )
    return {
        "floor_z": 0.0,
        "ground_sink_m": float(ground_sink),
        "target_lowest_z": target_lowest_z,
        "sample_count": int(math.ceil(frame_end)) - int(math.floor(frame_start)) + 1,
        "grounded_frame_count": grounded_frames,
        "maximum_correction_m": maximum_correction,
        "maximum_upward_correction_m": maximum_upward_correction,
        "maximum_downward_correction_m": maximum_downward_correction,
        "minimum_z": worst_minimum,
        "terminal_contact_frame": int(terminal_frame),
        "reference_height_m": safe_reference_height,
        "terminal_height_m": terminal_height,
        "terminal_height_ratio": terminal_height_ratio,
        "maximum_terminal_height_ratio": float(maximum_terminal_height_ratio),
        "carrier_role": carrier_role,
        "carrier_bone": str(mapping.get(carrier_role, "")),
        "terminal_torso_minimum_z": float(terminal_torso["minimum"].z),
        "terminal_torso_height_m": terminal_torso_height,
        "terminal_torso_height_ratio": terminal_torso_height_ratio,
        "maximum_terminal_torso_height_ratio": DEATH_TERMINAL_MAX_TORSO_HEIGHT_RATIO,
        "torso_contact_tolerance_m": contact_tolerance,
        "torso_regions": terminal_torso["regions"],
        "maximum_torso_safety_lift_m": maximum_torso_safety_lift,
    }


DRAFT_ACTION_NAMES = {
    "IDLE": "DSB_DRAFT_Idle",
    "WALK": "DSB_DRAFT_Walk",
    "DEATH": "DSB_DRAFT_Death",
    "HURT_LEFT": "DSB_DRAFT_Hurt_LEFT",
    "HURT_RIGHT": "DSB_DRAFT_Hurt_RIGHT",
    "MACE_GUARD_TWO_ARM": "DSB_DRAFT_Mace_Brace_Head_TwoArm",
    "MACE_GUARD_LEFT_ARM": "DSB_DRAFT_Mace_Brace_Head_LeftArm",
    "MACE_GUARD_RIGHT_ARM": "DSB_DRAFT_Mace_Brace_Head_RightArm",
    **{
        kind: record["draftName"]
        for kind, record in offensive_actions.OFFENSIVE_ACTION_VARIANTS.items()
    },
}


def unlink_action_everywhere(action):
    """Unlink an Action from active slots before replacing a disposable draft."""
    # Preflight all NLA users before changing any active Action slot. A refusal
    # must be non-destructive even when the NLA owner appears late in the scene.
    for obj in bpy.data.objects:
        animation_data = getattr(obj, "animation_data", None)
        if animation_data is None:
            continue
        for track in animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action == action:
                    raise RuntimeError(
                        f"Draft Action '{action.name}' is used by an NLA strip. "
                        "Remove it from NLA before regenerating."
                    )

    for obj in bpy.data.objects:
        animation_data = getattr(obj, "animation_data", None)
        if animation_data is None:
            continue

        if animation_data.action == action:
            animation_data.action = None


def ensure_draft_action(arm, draft_name):
    """Replace one disposable draft instead of accumulating tweak versions."""
    if not arm.animation_data:
        arm.animation_data_create()

    existing = bpy.data.actions.get(draft_name)
    if existing is not None:
        unlink_action_everywhere(existing)
        existing.use_fake_user = False
        try:
            bpy.data.actions.remove(existing, do_unlink=True)
        except TypeError:
            bpy.data.actions.remove(existing)

    action = bpy.data.actions.new(draft_name)
    action["dsb_draft"] = True
    action["dsb_approved"] = False
    arm.animation_data.action = action
    return action


def next_approved_version_name(base_name):
    pattern = re.compile(r"^" + re.escape(base_name) + r"_v(\d+)$")
    highest = 0

    for action in bpy.data.actions:
        match = pattern.match(action.name)
        if match:
            highest = max(highest, int(match.group(1)))

    return f"{base_name}_v{highest + 1:03d}"


def approval_base_name(settings, kind):
    if kind == "IDLE":
        return "DSB_Idle_Humanoid"

    if kind == "WALK":
        return f"DSB_Walk_{settings.walk_style}"

    if kind == "DEATH":
        style_label = {
            "CHEST_HOLD": "ChestHold",
            "FACEPLANT": "Faceplant",
            "KNEES_FIRST": "KneesFirst",
            "INSTANT_LIMP": "InstantUnconscious",
        }[settings.collapse_style]
        return f"DSB_Death_{style_label}_{settings.death_pain_side}"

    if kind == "HURT_LEFT":
        return "DSB_Hurt_LEFT_Flank"

    if kind == "HURT_RIGHT":
        return "DSB_Hurt_RIGHT_Flank"

    if kind == "MACE_GUARD_TWO_ARM":
        return "DSB_Mace_Brace_Head_TwoArm"

    if kind == "MACE_GUARD_LEFT_ARM":
        return "DSB_Mace_Brace_Head_LeftArm"

    if kind == "MACE_GUARD_RIGHT_ARM":
        return "DSB_Mace_Brace_Head_RightArm"

    if kind in offensive_actions.OFFENSIVE_ACTION_VARIANTS:
        return offensive_actions.OFFENSIVE_ACTION_VARIANTS[kind]["baseName"]

    raise RuntimeError(f"Unknown Action kind: {kind}")


def approve_draft_action(context, kind):
    settings = context.scene.daf_settings
    if settings.animation_library_edit_source_clip_id:
        raise RuntimeError(
            "A VIP animation edit is active. Use SAVE / OVERWRITE in the "
            "VIP Animation Library, or cancel that edit before approving a "
            "new version."
        )
    draft_name = DRAFT_ACTION_NAMES[kind]
    action = bpy.data.actions.get(draft_name)

    if action is None:
        raise RuntimeError(
            f"No {draft_name} exists. Generate the draft first."
        )

    if action.get(offensive_actions.OFFENSIVE_ACTION_PROPERTY):
        start, end = action_frame_bounds(action)
        fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
        recipe = offensive_actions.read_offensive_recipe(action)
        if recipe is None:
            raise RuntimeError(
                "This offensive draft has no saved slider recipe. Refresh the selected draft first."
            )
        if not bool(action.get("dsb_offensive_previewed", False)):
            raise RuntimeError(
                "Preview this offensive draft on the character before approving it."
            )
        if action.get(offensive_motion.MOTION_RECIPE_PROPERTY):
            offensive_motion_studio.require_approval_ready(context, action)
        offensive_actions.validated_action_metadata(
            action,
            clip_duration_seconds=max(0.0, end - start) / max(fps, 0.001),
            require_approved=False,
        )

    final_base = approval_base_name(settings, kind)
    final_name = next_approved_version_name(final_base)

    action.name = final_name
    action["dsb_draft"] = False
    action["dsb_approved"] = True
    action["dsb_approved_kind"] = kind
    approved_start, approved_end = action_frame_bounds(action)
    action["dsb_approved_frame_start"] = int(approved_start)
    action["dsb_approved_frame_end"] = int(approved_end)
    if action.get("dsb_guard_variant"):
        action["dsb_guard_action_id"] = final_name
    action.use_fake_user = True

    armature = find_armature(context)
    if not armature.animation_data:
        armature.animation_data_create()
    armature.animation_data.action = action
    animation_library.mark_approved(
        action,
        armature,
        settings,
        kind,
    )
    if action.get(offensive_actions.OFFENSIVE_ACTION_PROPERTY):
        offensive_actions.validated_action_metadata(
            action,
            clip_duration_seconds=max(0.0, action_frame_bounds(action)[1] - action_frame_bounds(action)[0]) / max(fps, 0.001),
            require_approved=True,
        )
        action["dsb_offensive_previewed_before_approval"] = True
        action["dsb_offensive_character_recipe"] = True
        if action.get(offensive_motion.MOTION_RECIPE_PROPERTY):
            offensive_motion_studio.on_action_approved(action)

    return action

def iter_action_fcurves(action):
    """Return F-Curves from both legacy and modern slotted Blender Actions."""
    curves = []
    seen = set()

    # Blender 3.x and legacy Actions through Blender 4.x.
    legacy_fcurves = getattr(action, "fcurves", None)
    if legacy_fcurves is not None:
        try:
            for fcurve in legacy_fcurves:
                pointer = fcurve.as_pointer()
                if pointer not in seen:
                    seen.add(pointer)
                    curves.append(fcurve)
        except (AttributeError, TypeError, RuntimeError):
            pass

    # Blender 4.4+ layered/slotted Actions; mandatory in Blender 5.x.
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                for fcurve in getattr(channelbag, "fcurves", []):
                    pointer = fcurve.as_pointer()
                    if pointer not in seen:
                        seen.add(pointer)
                        curves.append(fcurve)

    return curves


def set_bezier(action, cycles=False):
    curves = iter_action_fcurves(action)
    if not curves:
        print(
            "[Dreadstone] Warning: no F-Curves were found for interpolation cleanup. "
            "The generated keyframes remain valid."
        )
        return

    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'

        if cycles:
            try:
                has_cycles = any(mod.type == 'CYCLES' for mod in fc.modifiers)
                if not has_cycles:
                    fc.modifiers.new(type='CYCLES')
            except (AttributeError, RuntimeError):
                # The loop already closes with matching first/last poses, so a
                # missing Cycles modifier is non-fatal.
                pass



def _deformation_preview_property_updated(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is not None:
        module.request_low_level_property_update(context, "deformation control changed")


def _deformation_metadata_property_updated(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is not None:
        module.request_low_level_property_update(context, "deformation metadata changed")


def _impact_macro_property_updated(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is not None:
        module.apply_impact_macro_transaction(context, "Impact Pedal changed")


def _impact_seed_property_updated(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is not None:
        module.apply_impact_seed_transaction(context, "master impact seed changed")


def _gore_macro_property_updated(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is not None:
        module.apply_gore_macro_transaction(context, "Gore Pedal changed")


def _gore_seed_property_updated(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is not None:
        module.apply_gore_seed_transaction(context, "master gore seed changed")


def _gore_identity_property_updated(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is not None:
        module.apply_gore_identity_transaction(context)


def _anatomy_facing_updated(self, context):
    """Keep analyzed humanoid orientation synchronized with the Y+ contract."""

    try:
        armature = find_armature(context)
    except RuntimeError:
        return
    metadata = anatomy_persistence.load_metadata(armature)
    if metadata is None or metadata.get("profileId") != "DSB_HUMANOID_V1":
        return
    anatomy_blender.analyze_armature(
        armature,
        self,
        legacy_humanoid_mapper=map_bones,
    )


def _deformation_region_items(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is None:
        return [("NONE", "No Regions", "Register an attached/detached mesh pair")]
    try:
        return module.region_enum_items()
    except Exception:
        return [("NONE", "No Regions", "Register an attached/detached mesh pair")]


def _deformation_region_updated(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is not None and self.deformation_region not in {"", "NONE"}:
        try:
            module.request_region_switch(self.deformation_region, context)
        except Exception:
            pass


def _progression_authoring_module():
    module = sys.modules.get(f"{__package__}.progressive_authoring")
    if module is None:
        try:
            module = importlib.import_module(
                ".progressive_authoring",
                __package__,
            )
        except ImportError:
            return None
    return module


def _progression_severity_updated(self, context):
    module = _progression_authoring_module()
    if module is not None:
        module.request_progression_preview(context, "progression severity changed")


def _progression_site_property_updated(self, context):
    module = _progression_authoring_module()
    if module is not None:
        module.update_active_site_from_settings(context)


_OFFENSIVE_RECIPE_SETTING_FIELDS = {
    "windupSeconds": "offensive_windup_seconds",
    "activeSeconds": "offensive_active_seconds",
    "recoverySeconds": "offensive_recovery_seconds",
    "anticipationStrength": "offensive_anticipation_strength",
    "strikeStrength": "offensive_strike_strength",
    "followThrough": "offensive_follow_through",
    "torsoPower": "offensive_torso_power",
    "armReach": "offensive_arm_reach",
    "elbowFlex": "offensive_elbow_flex",
    "wristAction": "offensive_wrist_action",
    "stanceCompression": "offensive_stance_compression",
}


def offensive_recipe_from_settings(settings, kind):
    variant = offensive_actions.OFFENSIVE_ACTION_VARIANTS.get(str(kind))
    if variant is None:
        raise RuntimeError(f"Unknown offensive Action kind {kind!r}.")
    recipe = offensive_actions.default_offensive_recipe(variant)
    for field, setting_name in _OFFENSIVE_RECIPE_SETTING_FIELDS.items():
        recipe[field] = float(getattr(settings, setting_name))
    errors = offensive_actions.validate_offensive_recipe(recipe)
    if errors:
        raise RuntimeError("Invalid offensive slider recipe: " + " ".join(errors))
    return recipe


def apply_offensive_recipe_to_settings(settings, recipe):
    errors = offensive_actions.validate_offensive_recipe(recipe)
    if errors:
        raise RuntimeError("Invalid saved offensive recipe: " + " ".join(errors))
    for field, setting_name in _OFFENSIVE_RECIPE_SETTING_FIELDS.items():
        setattr(settings, setting_name, float(recipe[field]))
    return recipe


def _latest_offensive_recipe(kind):
    variant = offensive_actions.OFFENSIVE_ACTION_VARIANTS[str(kind)]
    draft = bpy.data.actions.get(variant["draftName"])
    candidates = [draft] if draft is not None else []
    candidates.extend(sorted(
        (
            action for action in bpy.data.actions
            if str(action.get("dsb_approved_kind", "")) == str(kind)
            and bool(action.get("dsb_approved", False))
        ),
        key=lambda action: action.name,
        reverse=True,
    ))
    for action in candidates:
        try:
            recipe = offensive_actions.read_offensive_recipe(action)
        except ValueError:
            continue
        if recipe is not None:
            return recipe
    return offensive_actions.default_offensive_recipe(variant)


def _offensive_preview_kind_updated(self, _context):
    try:
        apply_offensive_recipe_to_settings(
            self,
            _latest_offensive_recipe(str(self.offensive_preview_kind)),
        )
    except (KeyError, RuntimeError, TypeError, ValueError):
        return


def _motion_master_items(self, context):
    module = sys.modules.get(f"{__package__}.offensive_motion_studio")
    if module is None:
        return [
            (master_id, master["label"], "Built-in target-constrained Motion Master")
            for master_id, master in offensive_motion.BUILTIN_MOTION_MASTERS.items()
        ]
    return module.motion_master_items(self, context)


def _motion_master_updated(self, context):
    module = sys.modules.get(f"{__package__}.offensive_motion_studio")
    if module is not None:
        module.motion_master_updated(self, context)


def _motion_setting_updated(self, context):
    module = sys.modules.get(f"{__package__}.offensive_motion_studio")
    if module is not None:
        module.motion_setting_updated(self, context)


def _motion_style_updated(self, context):
    module = sys.modules.get(f"{__package__}.offensive_motion_studio")
    if module is not None:
        module.motion_style_updated(self, context)


def _motion_feel_updated(self, context):
    module = sys.modules.get(f"{__package__}.offensive_motion_studio")
    if module is not None:
        module.motion_feel_updated(self, context)


def _motion_proxy_updated(self, context):
    module = sys.modules.get(f"{__package__}.offensive_motion_studio")
    if module is not None:
        module.motion_proxy_updated(self, context)


def _motion_display_updated(self, context):
    module = sys.modules.get(f"{__package__}.offensive_motion_studio")
    if module is not None:
        module.motion_display_updated(self, context)


class DAFSettings(PropertyGroup):
    # Compact interface state. These values are stored in the Blender scene.
    ui_workspace: EnumProperty(
        name="Workspace",
        items=[
            ('START', "Start / Character", "Prepare a protected character for damage authoring"),
            ('DAMAGE', "Damage Authoring", "Create, tune, preview, and commit impacts"),
            ('ANIMATION', "Animation", "Draft, preview, approve, and package Actions"),
            ('EXPORT', "Validate & Export", "Run focused/full validation and export"),
            ('ADVANCED', "Advanced", "All manual and legacy Forge controls"),
        ],
        default='START',
    )
    ui_advanced_character_open: BoolProperty(default=True)
    ui_advanced_trauma_open: BoolProperty(default=False)
    ui_advanced_diagnostics_open: BoolProperty(default=False)
    ui_advanced_regions_open: BoolProperty(default=True)
    ui_advanced_deformations_open: BoolProperty(default=False)
    ui_advanced_capture_open: BoolProperty(default=False)
    ui_advanced_stamps_open: BoolProperty(default=False)
    ui_advanced_gore_open: BoolProperty(default=False)
    ui_advanced_compound_open: BoolProperty(default=False)
    ui_advanced_preview_open: BoolProperty(default=False)
    ui_advanced_legacy_open: BoolProperty(default=False)
    ui_advanced_impact_internals_open: BoolProperty(default=False)
    ui_advanced_gore_internals_open: BoolProperty(default=False)
    ui_vip_damage_open: BoolProperty(default=True)
    ui_progressive_sites_open: BoolProperty(default=True)
    ui_progressive_advanced_open: BoolProperty(default=False)
    ui_vip_animation_open: BoolProperty(default=True)
    ui_character_open: BoolProperty(default=True)
    ui_ground_open: BoolProperty(default=False)
    ui_rig_open: BoolProperty(default=False)
    ui_pose_open: BoolProperty(default=True)
    ui_pose_left_open: BoolProperty(default=False)
    ui_pose_right_open: BoolProperty(default=False)
    ui_idle_open: BoolProperty(default=True)
    ui_walk_open: BoolProperty(default=True)
    ui_walk_advanced_open: BoolProperty(default=False)
    ui_death_open: BoolProperty(default=False)
    ui_death_advanced_open: BoolProperty(default=False)
    ui_hurt_open: BoolProperty(default=False)
    ui_hurt_advanced_open: BoolProperty(default=False)
    ui_pack_open: BoolProperty(default=False)
    ui_workflow_open: BoolProperty(default=False)
    ui_deformation_authoring_open: BoolProperty(default=True)
    ui_surface_gore_open: BoolProperty(default=True)
    ui_body_arm_trauma_open: BoolProperty(default=False)
    ui_compound_trauma_open: BoolProperty(default=False)
    ui_offensive_open: BoolProperty(default=True)
    ui_motion_target_details_open: BoolProperty(default=False)
    ui_motion_weapon_geometry_open: BoolProperty(default=False)
    ui_motion_trajectory_open: BoolProperty(default=False)
    ui_motion_style_open: BoolProperty(default=False)
    ui_motion_solver_open: BoolProperty(default=False)
    ui_motion_validation_open: BoolProperty(default=False)
    ui_legacy_offensive_open: BoolProperty(default=False)
    ui_offensive_custom_open: BoolProperty(default=True)
    ui_mace_guard_open: BoolProperty(default=False)
    ui_variant_family_open: BoolProperty(default=True)

    variant_import_path: StringProperty(
        name="Skin & Bones Variant GLB",
        description="Approved Skin & Bones 2.2.0+ appearance export to add to the active technical family",
        default="",
        subtype='FILE_PATH',
    )
    variant_family_status: StringProperty(
        name="Character Variant Family Status",
        default="NO FAMILY — ADOPT AN APPROVED SKIN & BONES APPEARANCE",
        options={'HIDDEN'},
    )
    variant_shared_damage_edit_enabled: BoolProperty(
        name="Shared Family Damage Editing",
        description="Explicit family-wide edit gate for inherited Damage authoring",
        default=False,
        options={'HIDDEN'},
    )
    variant_damage_override_unit: EnumProperty(
        name="Damage Override Unit",
        description="Choose the narrow coherent Damage unit to inherit or override",
        items=[
            (
                'DAMAGE_KEY',
                "Active Damage Key",
                "Override only the active Damage Key, its Stamps, Gore, and generated bindings",
            ),
            (
                'PROGRESSIVE_SITE',
                "Active Progressive Site",
                "Override the site plus independent copies of its assigned Light/Medium/Heavy Damage Keys",
            ),
        ],
        default='DAMAGE_KEY',
    )

    target_height: FloatProperty(
        name="Target Height",
        default=1.50,
        min=.1,
        max=20,
        unit='LENGTH'
    )
    preview_floor_size: FloatProperty(
        name="Preview Floor Size",
        description="Width and depth of the square preview floor",
        default=8.0,
        min=1.0,
        max=100.0,
        unit='LENGTH'
    )
    ground_sink: FloatProperty(
        name="Ground Sink",
        description="How far the lowest visible mesh point sits below the floor",
        default=0.005,
        min=-0.05,
        max=0.10,
        precision=4,
        unit='LENGTH'
    )
    pack_output_directory: StringProperty(
        name="Pack Output Folder",
        description="Folder for the GLB, manifest, and validation report",
        default="//exports/",
        subtype='DIR_PATH'
    )
    pack_filename: StringProperty(
        name="Pack Filename",
        description="Filename without the .glb extension",
        default="humanoid_yplus_animpack_v001"
    )
    pack_auto_increment: BoolProperty(
        name="Auto-Increment Existing Filename",
        description="Create the next version instead of overwriting",
        default=True
    )
    pack_force_sampling: BoolProperty(
        name="Bake / Force Sampling",
        description="Bake sampling during glTF export for robust playback",
        default=True
    )
    last_pack_path: StringProperty(
        name="Last Pack Path",
        default="",
        options={'HIDDEN'}
    )
    animation_library_active_clip_id: StringProperty(
        name="Selected Animation Clip ID",
        default="",
        options={'HIDDEN'},
    )
    animation_library_active_action: StringProperty(
        name="Selected Animation",
        default="",
        options={'HIDDEN'},
    )
    animation_library_edit_source_clip_id: StringProperty(
        name="Animation Edit Source Clip ID",
        default="",
        options={'HIDDEN'},
    )
    animation_library_edit_source: StringProperty(
        name="Animation Edit Source",
        default="",
        options={'HIDDEN'},
    )
    animation_library_edit_draft: StringProperty(
        name="Animation Edit Draft",
        default="",
        options={'HIDDEN'},
    )
    animation_library_status: StringProperty(
        name="Animation Library Status",
        default="READY",
        options={'HIDDEN'},
    )
    animation_clip_directory: StringProperty(
        name="Clip Export Folder",
        description="Folder for portable .blend animation clips and their JSON manifests",
        default="//animation_clips/",
        subtype='DIR_PATH',
    )
    animation_clip_import_path: StringProperty(
        name="Clip to Import",
        description="Portable Forge animation-clip .blend file",
        default="",
        subtype='FILE_PATH',
    )
    ui_anatomy_advanced_open: BoolProperty(default=False)
    anatomy_profile_override: EnumProperty(
        name="Profile Override",
        description="Select a validator explicitly; required topology validation still applies",
        items=[
            ("AUTO", "Auto Detect", "Select only when profile confidence is decisive"),
            ("HUMANOID", "Humanoid", "Validate with the built-in humanoid anatomy profile"),
            (
                "QUADRUPED_DIGITIGRADE",
                "Quadruped Digitigrade",
                "Validate wolf-, dog-, hyena-, big-cat-, or demon-hound-like anatomy",
            ),
            (
                "CUSTOM_UNRESOLVED",
                "Custom / Unresolved",
                "Do not claim support until a matching profile exists",
            ),
        ],
        default="AUTO",
    )
    anatomy_detected_creature_class: StringProperty(default="NOT ANALYZED", options={'HIDDEN'})
    anatomy_selected_profile: StringProperty(default="AUTO / UNRESOLVED", options={'HIDDEN'})
    anatomy_detection_confidence: FloatProperty(default=0.0, min=0.0, max=1.0, options={'HIDDEN'})
    anatomy_orientation_summary: StringProperty(default="? forward / ? up", options={'HIDDEN'})
    anatomy_mapped_role_count: IntProperty(default=0, min=0, options={'HIDDEN'})
    anatomy_readiness_status: StringProperty(default="NOT_ANALYZED", options={'HIDDEN'})
    anatomy_worst_blocker: StringProperty(default="", options={'HIDDEN'})
    anatomy_role_mapping_json: StringProperty(default="", options={'HIDDEN'})
    facing: EnumProperty(
        name="Character Faces",
        items=[
            ("POS_Y", "+Y (Skin & Bones Canonical)", "Blender +Y forward; glTF -Z"),
        ],
        default="POS_Y",
        update=_anatomy_facing_updated,
    )

    # Y+ is the only production basis. Independent switches remain available
    # as artistic overrides, but the canonical knee/elbow defaults are direct.
    invert_knees: BoolProperty(
        name="Invert Knees",
        description="Reverse only the knee bend direction",
        default=False
    )
    invert_elbows: BoolProperty(
        name="Invert Elbows",
        description="Reverse only the elbow bend direction",
        default=False
    )

    manual_hips: StringProperty(
        name="Pelvis / Hips Bone",
        description="Optional manual override",
        default=""
    )
    manual_spine: StringProperty(
        name="Lowest Spine Bone",
        description="Optional manual override",
        default=""
    )
    manual_chest: StringProperty(
        name="Upper Spine / Chest Bone",
        description="Optional manual override",
        default=""
    )

    # Seamless humanoid idle controls.
    idle_seconds: FloatProperty(
        name="Loop Duration",
        default=3.2,
        min=1.5,
        max=8.0,
        unit='TIME',
    )
    idle_breathing: FloatProperty(
        name="Breathing",
        default=1.0,
        min=0.0,
        max=2.0,
    )
    idle_weight_shift: FloatProperty(
        name="Weight Shift",
        default=1.0,
        min=0.0,
        max=2.0,
    )
    idle_arm_tuck: FloatProperty(
        name="Arm Drop to Sides",
        description="Additively lower both complete arm chains from the current Draft Base Pose toward the torso",
        default=18.0,
        min=0.0,
        max=75.0,
    )
    animation_base_pose_status: StringProperty(
        name="Draft Base Pose Status",
        default="No Idle Draft Base Pose captured",
        options={'HIDDEN'},
    )

    # Walk controls.
    walk_style: EnumProperty(
        name="Walk Style",
        items=[
            ("NORMAL", "Normal", "Balanced everyday walk"),
            ("HEAVY", "Heavy", "Weighty, grounded movement"),
            ("CAUTIOUS", "Cautious", "Shorter guarded steps"),
            ("INJURED_LEFT", "Injured Left Leg", "Protect the left leg"),
            ("INJURED_RIGHT", "Injured Right Leg", "Protect the right leg"),
        ],
        default="NORMAL"
    )
    walk_frames: IntProperty(name="Cycle Frames", default=28, min=16, max=72)
    stride: FloatProperty(name="Stride", default=24, min=3, max=60)
    knee: FloatProperty(name="Knee Bend", default=38, min=5, max=100)
    step_lift: FloatProperty(name="Swing Foot Lift", default=12, min=0, max=40)
    foot_roll: FloatProperty(name="Heel / Toe Roll", default=10, min=0, max=30)
    arm_swing: FloatProperty(name="Arm Swing", default=20, min=0, max=60)
    walk_arm_tuck: FloatProperty(
        name="Arm Drop to Sides",
        description="Rotate the complete shoulder-and-arm chain downward like the closing half of a jumping jack",
        default=18.0,
        min=0.0,
        max=75.0
    )
    elbow_bend: FloatProperty(name="Elbow Bend", default=10, min=0, max=50)
    hip_bob: FloatProperty(
        name="Hip Bob",
        default=.035,
        min=0,
        max=.15,
        unit='LENGTH'
    )
    hip_sway: FloatProperty(
        name="Hip Sway",
        default=.022,
        min=0,
        max=.12,
        unit='LENGTH'
    )
    pelvis_twist: FloatProperty(name="Pelvis Twist", default=3.0, min=0, max=12)
    chest_counter_twist: FloatProperty(
        name="Chest Counter-Twist",
        default=4.0,
        min=0,
        max=15
    )
    torso_lean: FloatProperty(name="Forward Lean", default=2.0, min=-8, max=18)
    shoulder_sway: FloatProperty(name="Shoulder Sway", default=2.0, min=0, max=12)
    head_stability: FloatProperty(
        name="Head Stability",
        description="How strongly the head counters torso motion",
        default=.75,
        min=0,
        max=1
    )
    walk_asymmetry: FloatProperty(
        name="Step Asymmetry",
        default=0.0,
        min=0,
        max=.45
    )

    # Rotation-only arm and hand pose polish.
    pose_polish_enabled: BoolProperty(
        name="Use Arm & Hand Pose Polish",
        description="Apply the rotation-only offsets below to newly generated drafts",
        default=True
    )

    left_upper_arm_forward: FloatProperty(
        name="Left Arm Forward / Back",
        default=0.0,
        min=-60.0,
        max=60.0
    )
    left_upper_arm_roll: FloatProperty(
        name="Left Upper-Arm Roll",
        default=0.0,
        min=-90.0,
        max=90.0
    )
    left_elbow_flex: FloatProperty(
        name="Left Elbow Flex",
        description="Add or remove left elbow bend after the generated pose",
        default=0.0,
        min=-90.0,
        max=140.0
    )
    left_forearm_twist: FloatProperty(
        name="Left Forearm Twist",
        default=0.0,
        min=-120.0,
        max=120.0
    )
    left_wrist_flex: FloatProperty(
        name="Left Wrist Flex",
        default=0.0,
        min=-75.0,
        max=75.0
    )
    left_wrist_side: FloatProperty(
        name="Left Wrist Side Bend",
        default=0.0,
        min=-60.0,
        max=60.0
    )
    left_wrist_roll: FloatProperty(
        name="Left Wrist Roll",
        default=0.0,
        min=-120.0,
        max=120.0
    )

    right_upper_arm_forward: FloatProperty(
        name="Right Arm Forward / Back",
        default=0.0,
        min=-60.0,
        max=60.0
    )
    right_upper_arm_roll: FloatProperty(
        name="Right Upper-Arm Roll",
        default=0.0,
        min=-90.0,
        max=90.0
    )
    right_elbow_flex: FloatProperty(
        name="Right Elbow Flex",
        description="Add or remove right elbow bend after the generated pose",
        default=0.0,
        min=-90.0,
        max=140.0
    )
    right_forearm_twist: FloatProperty(
        name="Right Forearm Twist",
        default=0.0,
        min=-120.0,
        max=120.0
    )
    right_wrist_flex: FloatProperty(
        name="Right Wrist Flex",
        default=0.0,
        min=-75.0,
        max=75.0
    )
    right_wrist_side: FloatProperty(
        name="Right Wrist Side Bend",
        default=0.0,
        min=-60.0,
        max=60.0
    )
    right_wrist_roll: FloatProperty(
        name="Right Wrist Roll",
        default=0.0,
        min=-120.0,
        max=120.0
    )

    # Collapse controls.
    collapse_style: EnumProperty(
        name="Collapse Style",
        items=[
            ("CHEST_HOLD", "Chest-Hold Forward", "Hold the flank/chest and weaken"),
            ("FACEPLANT", "Uncontrolled Faceplant", "Less bracing, stronger forward fall"),
            ("KNEES_FIRST", "Knees First", "Longer knee-buckle phase"),
            (
                "INSTANT_LIMP",
                "Instant Unconscious",
                "Immediate loss of consciousness with completely lifeless limb collapse",
            ),
        ],
        default="CHEST_HOLD"
    )
    collapse_seconds: FloatProperty(
        name="Duration",
        default=3.8,
        min=2,
        max=8,
        unit='TIME'
    )
    death_instant_seconds: FloatProperty(
        name="Instant Collapse Duration",
        description="Time from consciousness loss to full-body ground contact",
        default=0.72,
        min=0.35,
        max=1.5,
        unit='TIME'
    )
    death_pain_side: EnumProperty(
        name="Pain / Hold Side",
        items=[("LEFT", "Left", ""), ("RIGHT", "Right", "")],
        default="LEFT"
    )
    death_lead_knee: EnumProperty(
        name="First Knee to Fail",
        items=[("LEFT", "Left", ""), ("RIGHT", "Right", "")],
        default="LEFT"
    )
    death_brace_side: EnumProperty(
        name="Bracing Arm",
        items=[
            ("AUTO", "Opposite Pain Side", ""),
            ("LEFT", "Left", ""),
            ("RIGHT", "Right", ""),
            ("NONE", "No Effective Brace", ""),
        ],
        default="AUTO"
    )
    death_knee_strength: FloatProperty(
        name="Knee Buckle",
        default=1.0,
        min=.35,
        max=1.5
    )
    death_curl_strength: FloatProperty(
        name="Torso Curl",
        default=1.0,
        min=.35,
        max=1.5
    )
    death_drop_strength: FloatProperty(
        name="Body Drop",
        default=1.0,
        min=.5,
        max=1.4
    )
    death_travel_strength: FloatProperty(
        name="Forward Travel",
        default=1.0,
        min=.3,
        max=1.6
    )
    death_twist_strength: FloatProperty(
        name="Body Twist",
        default=1.0,
        min=0,
        max=1.6
    )
    death_head_lag: FloatProperty(
        name="Head Heaviness",
        default=1.0,
        min=.25,
        max=1.6
    )
    death_fall_bias: FloatProperty(
        name="Fall Left / Right",
        description="Negative falls left; positive falls right",
        default=0.12,
        min=-1,
        max=1
    )
    death_arm_tuck: FloatProperty(
        name="Arm Drop to Body",
        description="Rotate the complete shoulder-and-arm chains downward toward the ribs during collapse",
        default=18.0,
        min=0.0,
        max=75.0
    )
    death_wiggle: FloatProperty(
        name="Death Wiggle / Thrash",
        description="Adds a restrained alternating torso and pelvis thrash before final settling",
        default=0.22,
        min=0.0,
        max=1.5
    )
    death_settle: FloatProperty(
        name="Final Settle",
        default=1.0,
        min=0,
        max=1.6
    )
    death_hold_frames: IntProperty(
        name="Final Pose Hold",
        default=12,
        min=1,
        max=120
    )

    # Hurt reaction controls.
    hurt_seconds: FloatProperty(
        name="Reaction Duration",
        default=1.35,
        min=.45,
        max=4,
        unit='TIME'
    )
    hurt_severity: FloatProperty(name="Severity", default=1.0, min=.25, max=1.6)
    hurt_hand_reach: FloatProperty(name="Hand-to-Flank Reach", default=1.0, min=.2, max=1.5)
    hurt_hand_to_flank: FloatProperty(
        name="Hand Down to Hip / Flank",
        description="Moves the wounded-side hand lower, like gripping the side of the waist or hip",
        default=0.85,
        min=0.0,
        max=1.5
    )
    hurt_torso_bend: FloatProperty(name="Torso Bend", default=1.0, min=.2, max=1.6)
    hurt_twist: FloatProperty(name="Torso Twist", default=1.0, min=0, max=1.6)
    hurt_knee_dip: FloatProperty(name="Knee Dip", default=1.0, min=0, max=1.6)
    hurt_stagger: FloatProperty(
        name="Stagger Distance",
        default=.055,
        min=0,
        max=.20,
        unit='LENGTH'
    )
    hurt_head_recoil: FloatProperty(name="Head Recoil", default=1.0, min=0, max=1.6)
    hurt_recovery: FloatProperty(
        name="Recovery by Final Frame",
        description="1 returns to neutral; 0 remains fully hurt",
        default=.72,
        min=0,
        max=1
    )

    # Weapon-first Offensive Motion Studio.  These are scene UI values; the
    # authoritative versioned recipe is persisted on the Action.
    motion_master_id: EnumProperty(
        name="Motion Master",
        description="Built-in starter or deliberately promoted target/trajectory master",
        items=_motion_master_items,
        update=_motion_master_updated,
    )
    motion_feel: EnumProperty(
        name="Feel",
        description="High-level secondary motion style; target geometry and combat identity do not change",
        items=[
            ("SUBTLE", "Subtle", "Very restrained body support and comfortable elbow bend"),
            ("NATURAL", "Natural", "Production default: compact, connected, and human"),
            ("FORCEFUL", "Forceful", "More committed secondary motion within the same hard reach law"),
            ("CUSTOM", "Custom", "Use the advanced body-style values directly"),
        ],
        default="NATURAL",
        update=_motion_feel_updated,
    )
    motion_target_distance_mode: EnumProperty(
        name="Target Distance",
        description="Use measured character arm reach or keep the entered distance",
        items=[
            ("AUTO", "Auto (Natural Fit)", "Adapt target distance and blade contact point to this character"),
            ("MANUAL", "Manual", "Keep the explicit target distance and enforce hard reach limits"),
        ],
        default="AUTO",
        update=_motion_setting_updated,
    )
    motion_target_zone: EnumProperty(
        name="Target Zone",
        items=[
            ("HEAD", "Head", "Spherical head target"),
            ("UPPER_TORSO", "Upper Torso", "Upper torso capsule"),
            ("CENTER_MASS", "Center Mass", "Center torso capsule"),
            ("LOW_TORSO", "Low Torso", "Lower torso capsule"),
            ("CUSTOM", "Custom", "Editable spherical target"),
        ],
        default="UPPER_TORSO",
        update=_motion_setting_updated,
    )
    motion_target_height: FloatProperty(name="Target Height", default=1.80, min=0.60, max=4.0, unit='LENGTH', update=_motion_setting_updated)
    motion_target_distance: FloatProperty(name="Target Distance", default=0.72, min=0.20, max=4.0, unit='LENGTH', update=_motion_setting_updated)
    motion_target_lateral: FloatProperty(name="Lateral Offset", default=0.0, min=-2.0, max=2.0, unit='LENGTH', update=_motion_setting_updated)
    motion_target_radius: FloatProperty(name="Torso Radius", default=0.22, min=0.05, max=0.60, unit='LENGTH', update=_motion_setting_updated)
    motion_target_half_height: FloatProperty(name="Zone Half Height", default=0.16, min=0.03, max=0.60, unit='LENGTH', update=_motion_setting_updated)
    motion_target_head_radius: FloatProperty(name="Head Radius", default=0.14, min=0.04, max=0.40, unit='LENGTH', update=_motion_setting_updated)
    motion_custom_target_height: FloatProperty(name="Custom Contact Height", default=1.15, min=0.10, max=4.0, unit='LENGTH', update=_motion_setting_updated)
    motion_custom_target_radius: FloatProperty(name="Custom Target Radius", default=0.20, min=0.03, max=0.60, unit='LENGTH', update=_motion_setting_updated)
    motion_proxy_class: EnumProperty(
        name="Weapon Proxy",
        items=[
            ("ONE_HAND_BLUNT", "1H Blunt / Mace", "Grip, shaft, and head contact geometry"),
            ("ONE_HAND_BLADE", "1H Blade", "Grip, blade strike segment, and tip"),
            ("SHORT_BLADE", "Dagger / Short Blade", "Short blade proxy architecture"),
            ("TWO_HAND_GENERIC", "2H Generic (Architecture)", "Two-hand proxy representation; polished two-hand solve is future work"),
        ],
        default="ONE_HAND_BLUNT",
        update=_motion_proxy_updated,
    )
    motion_proxy_length: FloatProperty(name="Proxy Length", default=0.74, min=0.15, max=3.0, unit='LENGTH', update=_motion_setting_updated)
    motion_proxy_contact: FloatProperty(name="Grip to Contact", default=0.64, min=0.05, max=3.0, unit='LENGTH', update=_motion_setting_updated)
    motion_proxy_strike_start: FloatProperty(name="Strike Segment Start", default=0.54, min=0.0, max=3.0, unit='LENGTH', update=_motion_setting_updated)
    motion_proxy_strike_end: FloatProperty(name="Strike Segment End", default=0.74, min=0.05, max=3.0, unit='LENGTH', update=_motion_setting_updated)
    motion_proxy_head_radius: FloatProperty(name="Head / Contact Radius", default=0.075, min=0.0, max=0.30, unit='LENGTH', update=_motion_setting_updated)
    motion_trajectory_family: EnumProperty(
        name="Trajectory Family",
        items=[
            ("HORIZONTAL", "Horizontal", "Lateral target crossing on a horizontal plane"),
            ("DIAGONAL_DOWN", "Diagonal Down", "High-to-low diagonal target crossing"),
            ("OVERHEAD_VERTICAL", "Overhead Vertical", "Descending sagittal strike plane"),
            ("THRUST", "Thrust", "Forward line through the target"),
            ("CUSTOM", "Custom", "Artist-defined trajectory controls"),
        ],
        default="OVERHEAD_VERTICAL",
        update=_motion_setting_updated,
    )
    motion_windup_seconds: FloatProperty(name="WINDUP Seconds", default=0.58, min=0.10, max=2.50, unit='TIME', update=_motion_setting_updated)
    motion_active_seconds: FloatProperty(name="ACTIVE Seconds", default=0.26, min=0.08, max=1.00, unit='TIME', update=_motion_setting_updated)
    motion_recovery_seconds: FloatProperty(name="RECOVERY Seconds", default=0.66, min=0.10, max=3.00, unit='TIME', update=_motion_setting_updated)
    motion_style_anticipation: FloatProperty(name="Anticipation", default=0.70, min=0.0, max=2.0, update=_motion_style_updated)
    motion_style_torso_power: FloatProperty(name="Torso Power", default=0.54, min=0.0, max=2.0, update=_motion_style_updated)
    motion_style_stance_compression: FloatProperty(name="Stance Compression", default=0.26, min=0.0, max=2.0, update=_motion_style_updated)
    motion_style_follow_through: FloatProperty(name="Follow Through", default=0.64, min=0.0, max=2.0, update=_motion_style_updated)
    motion_style_recovery: FloatProperty(name="Recovery", default=0.86, min=0.0, max=2.0, update=_motion_style_updated)
    motion_style_arm_extension: FloatProperty(name="Arm Extension", default=0.87, min=0.0, max=2.0, update=_motion_style_updated)
    motion_style_elbow_style: FloatProperty(name="Elbow Style", default=1.06, min=0.0, max=2.0, update=_motion_style_updated)
    motion_style_wrist_style: FloatProperty(name="Wrist Style", default=0.62, min=0.0, max=2.0, update=_motion_style_updated)
    motion_solver_pole_side: FloatProperty(name="Elbow Pole Side", default=0.36, min=0.05, max=2.0, unit='LENGTH', update=_motion_setting_updated)
    motion_solver_pole_back: FloatProperty(name="Elbow Pole Back", default=0.08, min=-1.0, max=1.0, unit='LENGTH', update=_motion_setting_updated)
    motion_solver_torso_support: FloatProperty(name="Torso Support", default=0.72, min=0.0, max=2.0, update=_motion_setting_updated)
    motion_reach_comfortable_ratio: FloatProperty(name="Comfortable Reach", default=0.88, min=0.70, max=0.94, subtype='FACTOR', update=_motion_setting_updated)
    motion_reach_warning_ratio: FloatProperty(name="Near-Lock Warning", default=0.92, min=0.70, max=0.97, subtype='FACTOR', update=_motion_setting_updated)
    motion_reach_hard_ratio: FloatProperty(name="Hard Reach Limit", default=0.985, min=0.90, max=0.9995, subtype='FACTOR', update=_motion_setting_updated)
    motion_shoulder_support_max_degrees: FloatProperty(name="Shoulder Support Cap (Degrees)", default=4.0, min=0.0, max=12.0, update=_motion_setting_updated)
    motion_tolerance_plane_error: FloatProperty(name="Plane / Line Error", default=0.12, min=0.01, max=0.30, unit='LENGTH', update=_motion_setting_updated)
    motion_tolerance_contact_window: FloatProperty(name="Contact Frame Window", default=2.0, min=0.0, max=5.0, update=_motion_setting_updated)
    motion_tolerance_direction_dot: FloatProperty(name="Direction Dot Minimum", default=0.60, min=0.20, max=0.99, update=_motion_setting_updated)
    motion_tolerance_sampling_step: FloatProperty(name="ACTIVE Sampling Step", default=0.25, min=0.10, max=1.0, update=_motion_setting_updated)
    motion_show_target: BoolProperty(name="Show Target", default=True, update=_motion_display_updated)
    motion_show_trail: BoolProperty(name="Show Weapon Trail", default=True, update=_motion_display_updated)
    motion_show_plane: BoolProperty(name="Show Strike Plane / Line", default=True, update=_motion_display_updated)
    motion_validation_status: StringProperty(name="Motion Studio Status", default="NO MOTION STUDIO ACTION", options={'HIDDEN'})
    motion_pose_health_status: StringProperty(name="Pose Health", default="POSE HEALTH — NOT BUILT", options={'HIDDEN'})
    motion_pose_health_detail: StringProperty(name="Pose Health Detail", default="", options={'HIDDEN'})

    # Backward-compatible body-first recipe. Values are persisted into every
    # legacy generated/approved Action rather than changing global defaults.
    offensive_preview_kind: EnumProperty(
        name="Attack to Customize",
        description="Choose the character-specific offensive draft controlled by the sliders below",
        items=[
            ("ATTACK_SLASH_RTL_ONE_HAND", "1H Slash Right to Left", "One-hand horizontal slash"),
            ("ATTACK_SLASH_LTR_ONE_HAND", "1H Slash Left to Right", "One-hand reverse slash"),
            ("ATTACK_OVERHEAD_ONE_HAND", "1H Overhead", "One-hand overhead strike"),
            ("ATTACK_THRUST_ONE_HAND", "1H Thrust", "One-hand forward thrust"),
            ("ATTACK_HEAVY_ONE_HAND", "1H Heavy", "Committed one-hand heavy strike"),
            ("ATTACK_SLASH_TWO_HAND", "2H Slash", "Two-hand diagonal strike"),
            ("ATTACK_OVERHEAD_TWO_HAND", "2H Overhead", "Two-hand overhead strike"),
            ("ATTACK_THRUST_TWO_HAND", "2H Thrust", "Two-hand forward thrust"),
        ],
        default="ATTACK_SLASH_RTL_ONE_HAND",
        update=_offensive_preview_kind_updated,
    )
    offensive_windup_seconds: FloatProperty(
        name="WINDUP Seconds", default=0.46, min=0.10, max=2.50, unit='TIME'
    )
    offensive_active_seconds: FloatProperty(
        name="ACTIVE Seconds", default=0.30, min=0.08, max=1.00, unit='TIME'
    )
    offensive_recovery_seconds: FloatProperty(
        name="RECOVERY Seconds", default=0.58, min=0.10, max=3.00, unit='TIME'
    )
    offensive_anticipation_strength: FloatProperty(
        name="Anticipation", default=1.0, min=0.25, max=1.80
    )
    offensive_strike_strength: FloatProperty(
        name="Strike Strength", default=1.0, min=0.25, max=1.80
    )
    offensive_follow_through: FloatProperty(
        name="Follow Through", default=1.0, min=0.25, max=1.80
    )
    offensive_torso_power: FloatProperty(
        name="Torso Power", default=1.0, min=0.0, max=2.0
    )
    offensive_arm_reach: FloatProperty(
        name="Arm Reach", default=1.0, min=0.50, max=1.50
    )
    offensive_elbow_flex: FloatProperty(
        name="Elbow Flex", default=1.0, min=0.50, max=1.50
    )
    offensive_wrist_action: FloatProperty(
        name="Wrist Action", default=1.0, min=0.0, max=2.0
    )
    offensive_stance_compression: FloatProperty(
        name="Stance / Compression", default=1.0, min=0.0, max=2.0
    )

    # Mace head-guard draft timing and pose shaping. Scene FPS determines the
    # actual frames. The wide timing ranges support a readable fear/cower hold
    # as well as the original short, deformed zombie-attack motion.
    mace_guard_raise_seconds: FloatProperty(
        name="Recognition + Arm Raise",
        description="Time spent recognizing the threat and bringing the arms over the head",
        default=0.65,
        min=0.15,
        max=2.50,
        unit='TIME'
    )
    mace_guard_hold_seconds: FloatProperty(
        name="Protected Hold",
        description="How long the forearms remain around the head",
        default=1.20,
        min=0.10,
        max=6.00,
        unit='TIME'
    )
    mace_guard_recovery_seconds: FloatProperty(
        name="Interruptible Recovery",
        default=0.60,
        min=0.05,
        max=3.00,
        unit='TIME'
    )
    mace_guard_style: EnumProperty(
        name="Motion Style",
        description="Choose a natural protective cower, a compact guard, or the original twisted attack-like pose",
        items=[
            (
                'COWERING',
                "Cowering in Fear",
                "Longer protective arc, compressed torso, tucked head, and forearms wrapped around the crown",
            ),
            (
                'DEFENSIVE',
                "Defensive Head Guard",
                "Balanced upright guard with readable head coverage",
            ),
            (
                'ZOMBIE_ATTACK',
                "Zombie-Insect Attack (Legacy Shape)",
                "Preserve the original deformed, attack-like pose as a reusable generator style",
            ),
        ],
        default='COWERING',
    )
    mace_guard_arm_cover: FloatProperty(
        name="Arm Cover Height",
        description="How high the upper arms lift to place the forearms around the head",
        default=1.0,
        min=0.35,
        max=1.65
    )
    mace_guard_elbow_flex: FloatProperty(
        name="Guard Elbow Flex",
        description="Elbow bend used to form the protective forearm arc",
        default=124.0,
        min=55.0,
        max=155.0
    )
    mace_guard_arm_wrap: FloatProperty(
        name="Forearm Wrap",
        description="How strongly the arms fold inward across the temples and crown",
        default=1.0,
        min=0.0,
        max=1.80
    )
    mace_guard_shoulder_hunch: FloatProperty(
        name="Shoulder Hunch",
        default=1.0,
        min=0.0,
        max=2.00
    )
    mace_guard_torso_curl: FloatProperty(
        name="Torso Curl",
        default=1.0,
        min=0.0,
        max=2.00
    )
    mace_guard_head_tuck: FloatProperty(
        name="Head Tuck",
        default=1.0,
        min=0.0,
        max=2.00
    )
    mace_guard_crouch: FloatProperty(
        name="Crouch / Compression",
        default=1.0,
        min=0.0,
        max=2.00
    )
    mace_guard_asymmetry: FloatProperty(
        name="Fear Asymmetry",
        description="Offsets the right side for a less mirrored, more natural defensive pose",
        default=0.10,
        min=0.0,
        max=0.65
    )
    mace_guard_end_release: FloatProperty(
        name="Release by Final Frame",
        description="1 returns fully toward neutral; 0 remains fully covered",
        default=0.45,
        min=0.0,
        max=1.0
    )
    mace_guard_preview_variant: EnumProperty(
        name="Preview Variant",
        items=[
            ('MACE_GUARD_TWO_ARM', "Two-Arm Head Guard", "Both forearms form an imperfect shield"),
            ('MACE_GUARD_LEFT_ARM', "Left-Arm Emergency Guard", "Left forearm protects the head"),
            ('MACE_GUARD_RIGHT_ARM', "Right-Arm Emergency Guard", "Right forearm protects the head"),
        ],
        default='MACE_GUARD_TWO_ARM',
    )

    # Source Damage Readiness v3.8.1. The analyzer writes report/UI state and
    # stable identity metadata, but never edits source geometry or weights.
    ui_damage_readiness_open: BoolProperty(default=False)
    damage_readiness_output_directory: StringProperty(
        name="Report Output Folder",
        description="Explicit project folder for readiness reports; blank values, unsaved // paths, and drive roots are rejected",
        default="",
        subtype='DIR_PATH'
    )
    damage_readiness_preview_seam: EnumProperty(
        name="Preview Seam",
        items=[
            ("head_neck", "Head–Neck", "Preview the neck/head candidate boundary"),
            ("left_elbow", "Left Elbow", "Preview the left upper/lower arm candidate boundary"),
            ("right_elbow", "Right Elbow", "Preview the right upper/lower arm candidate boundary"),
            ("lower_spine", "Lower Spine", "Preview the pelvis/lower-spine candidate boundary"),
        ],
        default="head_neck"
    )
    last_damage_readiness_json_path: StringProperty(default="", options={'HIDDEN'})
    last_damage_readiness_markdown_path: StringProperty(default="", options={'HIDDEN'})
    damage_readiness_overall_status: StringProperty(default="NOT ANALYZED", options={'HIDDEN'})
    source_readiness_contract_status: StringProperty(default="NOT ANALYZED", options={'HIDDEN'})
    damage_readiness_head_neck_status: StringProperty(default="NOT ANALYZED", options={'HIDDEN'})
    damage_readiness_left_elbow_status: StringProperty(default="NOT ANALYZED", options={'HIDDEN'})
    damage_readiness_right_elbow_status: StringProperty(default="NOT ANALYZED", options={'HIDDEN'})
    damage_readiness_lower_spine_status: StringProperty(default="NOT ANALYZED", options={'HIDDEN'})

    # Forge v3.8 protected segment and stump authoring.
    ui_damage_authoring_open: BoolProperty(default=True)
    damage_authoring_report_path: StringProperty(
        name="READY Report JSON",
        description="Fingerprint-validated virtual-weld v3.7.4 readiness JSON",
        default="",
        subtype='FILE_PATH'
    )
    damage_authoring_output_directory: StringProperty(
        name="Damage Export Folder",
        description="Project folder for the Damage GLB, manifest, and validation report; unsaved files require an explicit folder",
        default="",
        subtype='DIR_PATH'
    )
    damage_authoring_filename: StringProperty(
        name="Damage Asset Filename",
        description="Filename without extension",
        default="humanoid_damage_v001"
    )
    damage_authoring_seam: EnumProperty(
        name="Detached Preview Seam",
        items=[
            ("head_neck", "Head–Neck", "Preview decapitation authoring assets"),
            ("left_elbow", "Left Elbow", "Preview left forearm authoring assets"),
            ("right_elbow", "Right Elbow", "Preview right forearm authoring assets"),
            ("lower_spine", "Lower Spine", "Preview upper/lower body split assets"),
        ],
        default="head_neck"
    )
    damage_authoring_gap_tolerance: FloatProperty(
        name="Intact Seam Tolerance",
        description="Maximum accepted virtual seam-family position error",
        default=0.0005,
        min=0.00001,
        max=0.01,
        precision=6,
        unit='LENGTH'
    )
    damage_authoring_status: StringProperty(default="NOT BUILT", options={'HIDDEN'})
    last_damage_authoring_validation: StringProperty(default="NOT VALIDATED", options={'HIDDEN'})
    last_damage_export_validation: StringProperty(default="NOT VALIDATED", options={'HIDDEN'})
    last_damage_glb_path: StringProperty(default="", options={'HIDDEN'})
    last_damage_manifest_path: StringProperty(default="", options={'HIDDEN'})
    last_damage_validation_path: StringProperty(default="", options={'HIDDEN'})

    # Trauma Field Authoring v5.4.1.
    deformation_region: EnumProperty(
        name="Active Region",
        items=_deformation_region_items,
        update=_deformation_region_updated,
    )
    deformation_region_id: StringProperty(
        name="New Region ID",
        description="Unique semantic ID for the selected attached/detached pair",
        default="head",
    )
    deformation_related_seam_id: StringProperty(
        name="Related Seam ID",
        description="Optional Damage Authoring seam ID used for protection weighting",
        default="head_neck",
    )
    deformation_key_name: StringProperty(
        name="Damage Key Name",
        description=(
            "Editable name for the focused Damage Key; use the Rename action to "
            "apply it without changing the key's stable identity"
        ),
        default="Head_Dent_Left",
    )
    deformation_active_key: StringProperty(name="Active Deformation", default="", options={'HIDDEN'})
    deformation_capture_mode: EnumProperty(
        name="Placement Mode",
        items=[
            ('SINGLE_FACE', "Single Face", "Capture exactly one selected face"),
            ('SELECTED_FACE_PATCH', "Selected Face Patch", "Capture one connected component of selected faces"),
            ('SELECTED_VERTICES', "Selected Vertices", "Capture one or more selected vertices"),
            ('CURSOR', "3D Cursor", "Capture the cursor and one surface seed vertex"),
        ],
        default='SINGLE_FACE',
    )
    deformation_influence_mode: EnumProperty(
        name="Influence Mask",
        items=[
            ('PATCH_ONLY', "Patch Only", "Only captured vertices are eligible"),
            ('PATCH_FEATHERED', "Patch Feathered", "Keep captured vertices full and feather across connected edges"),
            ('CONNECTED_SURFACE', "Connected Surface", "Spread over the connected surface within the radius"),
        ],
        default='PATCH_FEATHERED',
    )
    deformation_distance_mode: EnumProperty(
        name="Distance Mode",
        items=[
            ('SURFACE_DISTANCE', "Surface Distance", "Use world-length weighted edge-graph geodesic distance"),
            ('WORLD_DISTANCE', "World Distance", "Use direct world-space distance for compatibility and diagnosis"),
        ],
        default='SURFACE_DISTANCE',
    )
    deformation_feather_distance: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_feather_distance"),
        update=_deformation_preview_property_updated,
    )
    deformation_stamp_family: EnumProperty(
        name="Trauma Family",
        items=[
            ('COMPACT_DENT', "Compact Dent", "Localized inward depression"),
            ('BROAD_CAVE', "Broad Cave", "Wide soft inward collapse"),
            ('FLAT_COMPRESSION', "Flat Compression", "Compress vertices toward an impact plane"),
            ('DIRECTIONAL_SHEAR', "Directional Shear", "Controlled lateral displacement"),
            ('RAISED_IMPACT_RIM', "Raised Impact Rim", "Restrained raised lip around an impact"),
            ('RIDGE_COLLAPSE', "Ridge Collapse", "Push a protruding ridge inward"),
        ],
        default='COMPACT_DENT',
    )
    deformation_stamp_name: StringProperty(name="Stamp Name", default="Impact Stamp")
    deformation_stamp_strength: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_stamp_strength"),
        update=_deformation_preview_property_updated,
    )
    deformation_active_stamp_id: StringProperty(default="", options={'HIDDEN'})
    deformation_capture_json: StringProperty(default="", options={'HIDDEN'})
    deformation_auto_preview: BoolProperty(
        name="Live Seed Preview",
        description="Refresh the temporary seed morph while sliders change",
        default=True,
        update=_deformation_preview_property_updated,
    )
    deformation_live_preview: BoolProperty(
        name="Live Preview",
        description="Debounce authoring changes through one managed main-thread preview session",
        default=True,
        update=_deformation_preview_property_updated,
    )
    deformation_preview_quality: EnumProperty(
        name="Preview Quality",
        items=[
            ('OFF', "Off", "Disable managed live preview"),
            ('FAST', "Fast", "Affected deformation vertices; no final raised-gore shells"),
            ('BALANCED', "Balanced", "Complete non-destructive deformation with lightweight gore feedback"),
            ('FINAL', "Final", "Use explicit Final Preview or Commit for deterministic final output"),
        ],
        default='FAST',
        update=_deformation_preview_property_updated,
    )
    deformation_preview_status: StringProperty(default="CLEAN", options={'HIDDEN'})
    deformation_preview_message: StringProperty(default="", options={'HIDDEN'})
    deformation_preview_generation: IntProperty(default=0, min=0, options={'HIDDEN'})
    deformation_preview_elapsed_ms: FloatProperty(default=0.0, min=0.0, options={'HIDDEN'})
    deformation_preview_affected_vertices: IntProperty(default=0, min=0, options={'HIDDEN'})
    deformation_preview_estimated_gore_triangles: IntProperty(default=0, min=0, options={'HIDDEN'})
    deformation_preview_final_gore_triangles: IntProperty(default=0, min=0, options={'HIDDEN'})
    progression_active_site_guid: StringProperty(
        name="Active Progressive Site GUID",
        default="",
        options={'HIDDEN'},
    )
    progression_active_stage: EnumProperty(
        name="Active Progression Stage",
        items=[
            ("LIGHT", "LIGHT", "Artist-authored Light Damage Key"),
            ("MEDIUM", "MEDIUM", "Artist-authored Medium Damage Key"),
            ("HEAVY", "HEAVY", "Artist-authored Heavy Damage Key"),
        ],
        default="LIGHT",
    )
    progression_site_name: StringProperty(
        name="Site Name",
        default="Damage Site",
        update=_progression_site_property_updated,
    )
    progression_site_region: StringProperty(
        name="Registered Region",
        default="",
        options={'HIDDEN'},
    )
    progression_structural_group: StringProperty(
        name="Structural Group",
        default="",
        update=_progression_site_property_updated,
    )
    progression_anchor_local: FloatVectorProperty(
        name="Local Anchor",
        size=3,
        subtype='XYZ',
        default=(0.0, 0.0, 0.0),
        update=_progression_site_property_updated,
    )
    progression_radius: FloatProperty(
        name="Influence Radius",
        default=0.10,
        min=0.000001,
        max=100.0,
        precision=4,
        unit='LENGTH',
        update=_progression_site_property_updated,
    )
    progression_preferred_direction: FloatVectorProperty(
        name="Preferred Direction",
        size=3,
        subtype='DIRECTION',
        default=(1.0, 0.0, 0.0),
        update=_progression_site_property_updated,
    )
    progression_light_anchor: FloatProperty(
        name="Light Severity",
        default=0.33,
        min=0.01,
        max=0.98,
        precision=3,
        update=_progression_site_property_updated,
    )
    progression_medium_anchor: FloatProperty(
        name="Medium Severity",
        default=0.66,
        min=0.02,
        max=0.99,
        precision=3,
        update=_progression_site_property_updated,
    )
    progression_heavy_anchor: FloatProperty(
        name="Heavy Severity",
        default=1.0,
        min=0.03,
        max=1.0,
        precision=3,
        update=_progression_site_property_updated,
    )
    progression_transition_mode: EnumProperty(
        name="Transition Mode",
        items=[
            (
                "ADJACENT_CROSSFADE",
                "Adjacent Crossfade",
                "Crossfade only Basis/Light, Light/Medium, or Medium/Heavy",
            ),
        ],
        default="ADJACENT_CROSSFADE",
        update=_progression_site_property_updated,
    )
    progression_transition_curve: EnumProperty(
        name="Transition Curve",
        items=[
            ("SMOOTHSTEP", "Smoothstep", "Smooth cubic adjacent transition"),
            ("LINEAR", "Linear", "Linear adjacent transition"),
        ],
        default="SMOOTHSTEP",
        update=_progression_site_property_updated,
    )
    progression_gore_transition_mode: EnumProperty(
        name="Detailed Gore Transition",
        items=[
            (
                "MIDPOINT_REPLACE",
                "Midpoint Replace",
                "Show exactly one complete stage gore assembly",
            ),
        ],
        default="MIDPOINT_REPLACE",
        update=_progression_site_property_updated,
    )
    progression_severity: FloatProperty(
        name="Progression Severity",
        description="Normalized Progressive Damage Site preview severity",
        default=0.0,
        min=0.0,
        max=100.0,
        precision=1,
        subtype='PERCENTAGE',
        update=_progression_severity_updated,
    )
    progression_live_preview: BoolProperty(
        name="Live Progression Preview",
        default=True,
        update=_progression_severity_updated,
    )
    progression_preview_with_other_damage: BoolProperty(
        name="Preview with Other Damage",
        default=False,
    )
    progression_preview_requested: BoolProperty(
        default=False,
        options={'HIDDEN'},
    )
    progression_preview_active: BoolProperty(
        default=False,
        options={'HIDDEN'},
    )
    progression_weight_basis: FloatProperty(
        default=1.0,
        min=0.0,
        max=1.0,
        options={'HIDDEN'},
    )
    progression_weight_light: FloatProperty(
        default=0.0,
        min=0.0,
        max=1.0,
        options={'HIDDEN'},
    )
    progression_weight_medium: FloatProperty(
        default=0.0,
        min=0.0,
        max=1.0,
        options={'HIDDEN'},
    )
    progression_weight_heavy: FloatProperty(
        default=0.0,
        min=0.0,
        max=1.0,
        options={'HIDDEN'},
    )
    progression_detailed_gore_stage: StringProperty(
        default="NONE",
        options={'HIDDEN'},
    )
    progression_transition_status: StringProperty(
        default="BASIS",
        options={'HIDDEN'},
    )
    progression_status: StringProperty(
        default="NO PROGRESSIVE SITE",
        options={'HIDDEN'},
    )
    deformation_impact_semantic_name: StringProperty(
        name="Damage Key Name",
        description="Optional universal damage-key name; Forge creates a safe unique name when blank",
        default="",
    )
    deformation_blueprint_name: StringProperty(
        name="Library Name",
        description="Name used when saving the focused Damage Key, Stamp, and Gore recipe",
        default="My Damage",
    )
    deformation_blueprint_library_path: StringProperty(
        name="Damage Blueprint Library",
        description="Project or absolute JSON path for reusable topology-independent Damage Blueprints",
        default="//dreadstone_damage_blueprints.json",
        subtype='FILE_PATH',
    )
    deformation_impact_control_mode: EnumProperty(
        name="Impact Control Mode",
        description="MACRO derives the physical recipe from the Impact Pedal; MANUAL preserves editable raw values as CUSTOM",
        items=[
            ('MACRO', "MACRO", "Impact Pedal macros are authoritative"),
            ('MANUAL', "MANUAL", "Raw physical controls are authoritative and the recipe is CUSTOM"),
        ],
        default='MACRO',
    )
    deformation_impact_control_version: IntProperty(
        name="Impact Control Version",
        default=parameter_schema.IMPACT_CONTROL_VERSION,
        options={'HIDDEN'},
    )
    deformation_impact_size: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_impact_size"),
        update=_impact_macro_property_updated,
    )
    deformation_impact_crush: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_impact_crush"),
        update=_impact_macro_property_updated,
    )
    deformation_impact_profile: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_impact_profile"),
        update=_impact_macro_property_updated,
    )
    deformation_impact_edge_safety: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_impact_edge_safety"),
        update=_impact_macro_property_updated,
    )
    deformation_impact_chaos: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_impact_chaos"),
        update=_impact_macro_property_updated,
    )
    deformation_impact_asymmetry: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_impact_asymmetry"),
        update=_impact_macro_property_updated,
    )
    deformation_impact_seed: IntProperty(
        **parameter_schema.blender_kwargs("deformation_impact_seed"),
        update=_impact_seed_property_updated,
    )
    deformation_impact_gore_patch_scale: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_impact_gore_patch_scale"),
        update=_deformation_preview_property_updated,
    )
    deformation_impact_dirty: BoolProperty(default=False, options={'HIDDEN'})
    deformation_impact_identity: StringProperty(default="", options={'HIDDEN'})
    deformation_impact_transaction_count: IntProperty(default=0, min=0, options={'HIDDEN'})
    diagnostics_output_directory: StringProperty(
        name="Diagnostics Folder",
        description="Folder for privacy-safe Forge JSON and Markdown support reports",
        default="//forge_diagnostics/",
        subtype='DIR_PATH',
    )
    deformation_seed_radius: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_seed_radius"),
        update=_deformation_preview_property_updated,
    )
    deformation_seed_depth: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_seed_depth"),
        update=_deformation_preview_property_updated,
    )
    deformation_seed_falloff: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_seed_falloff"),
        update=_deformation_preview_property_updated,
    )
    deformation_seed_direction_mode: EnumProperty(
        name="Damage Axis",
        items=[
            ('INWARD_SURFACE_NORMAL', "Inward Surface Normal", "Push into the captured surface"),
            ('OUTWARD_SURFACE_NORMAL', "Outward Surface Normal", "Pull away from the captured surface"),
            ('LOCAL_X', "+X", "Local positive X"), ('LOCAL_NEG_X', "-X", "Local negative X"),
            ('LOCAL_Y', "+Y", "Local positive Y"), ('LOCAL_NEG_Y', "-Y", "Local negative Y"),
            ('LOCAL_Z', "+Z", "Local positive Z"), ('LOCAL_NEG_Z', "-Z", "Local negative Z"),
            ('CUSTOM_VECTOR', "Custom Vector", "Use the normalized custom vector"),
        ],
        default='INWARD_SURFACE_NORMAL',
        update=_deformation_preview_property_updated,
    )
    deformation_seed_custom_direction: FloatVectorProperty(
        name="Custom Direction", size=3, default=(0.0, 0.0, -1.0), subtype='DIRECTION',
        update=_deformation_preview_property_updated,
    )
    deformation_seed_center: FloatVectorProperty(name="Seed Center", size=3, default=(0.0, 0.0, 0.0), subtype='XYZ')
    deformation_seed_surface_normal: FloatVectorProperty(name="Surface Normal", size=3, default=(0.0, 0.0, 1.0), subtype='DIRECTION')
    deformation_seed_center_valid: BoolProperty(default=False, options={'HIDDEN'})
    deformation_seed_seam_protection: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_seed_seam_protection"),
        update=_deformation_preview_property_updated,
    )
    deformation_max_vertex_displacement: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_max_vertex_displacement"),
        update=_deformation_metadata_property_updated,
    )
    deformation_maximum_influence: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_maximum_influence"),
        update=_deformation_metadata_property_updated,
    )
    deformation_gore_enabled: BoolProperty(
        name="Enable Surface Gore Overlay",
        description="Author a procedural blunt-trauma coating on the linked captured outer surface",
        default=False,
        update=_deformation_preview_property_updated,
    )
    deformation_gore_identity: EnumProperty(
        name="Gore Identity",
        description="Choose one strongly differentiated Cavity/Inlay Gore identity",
        items=[
            ("BRUISED_DENT", "Bruised Dent", "Shallow crushed depression with stain-led damage"),
            ("BLOODY_CRATER", "Bloody Crater", "Wet recessed bed with restrained clot fill"),
            ("DARK_CLOT_CAVITY", "Dark Clot Cavity", "Deep recess partially occupied by dark clot"),
            ("CRUSHED_TISSUE", "Crushed Tissue", "Broad compressed wound with fiber and tissue breakup"),
            ("EXPOSED_CRANIUM", "Exposed Cranium", "Deep low-fill cavity with an exposed pale plate"),
            ("RAGGED_IMPACT", "Ragged Impact", "Irregular cavity with bounded peripheral fragments"),
        ],
        default="BLOODY_CRATER",
        update=_gore_identity_property_updated,
    )
    deformation_gore_geometry_mode: EnumProperty(
        name="Geometry Mode",
        items=[
            ("STAIN_ONLY", "Stain Only", "Surface stain without generated geometry"),
            ("CAVITY_INLAY", "Cavity / Inlay", "Recessed liner and optional internal layers"),
            ("LEGACY_RAISED", "Legacy Raised", "Compatibility mode for existing raised-shell recipes"),
            (
                "HYBRID_ADDITIVE",
                "Raised + Inlay",
                "Independent full-strength raised and recessed geometry channels",
            ),
        ],
        default="HYBRID_ADDITIVE",
    )
    deformation_gore_control_mode: EnumProperty(
        name="Gore Control Mode",
        items=[
            (
                "MACRO",
                "MACRO",
                "The additive inlay/raised and cohesive Surface Gore macros "
                "are authoritative",
            ),
            ("MANUAL", "MANUAL", "Advanced physical gore values are authoritative"),
        ],
        default="MACRO",
    )
    deformation_gore_exposure: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_exposure"),
        update=_gore_macro_property_updated,
    )
    deformation_gore_cavity: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_cavity"),
        update=_gore_macro_property_updated,
    )
    deformation_gore_clot_fill: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_clot_fill"),
        update=_gore_macro_property_updated,
    )
    deformation_gore_breakup: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_breakup"),
        update=_gore_macro_property_updated,
    )
    deformation_gore_wetness_macro: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_wetness_macro"),
        update=_gore_macro_property_updated,
    )
    deformation_gore_variation: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_variation"),
        update=_gore_macro_property_updated,
    )
    deformation_gore_surface_mass: FloatProperty(
        **parameter_schema.blender_kwargs(
            "deformation_gore_surface_mass"
        ),
        update=_gore_macro_property_updated,
    )
    deformation_gore_surface_relief: FloatProperty(
        **parameter_schema.blender_kwargs(
            "deformation_gore_surface_relief"
        ),
        update=_gore_macro_property_updated,
    )
    deformation_gore_nucleus: FloatProperty(
        **parameter_schema.blender_kwargs(
            "deformation_gore_nucleus"
        ),
        update=_gore_macro_property_updated,
    )
    deformation_gore_lobes: FloatProperty(
        **parameter_schema.blender_kwargs(
            "deformation_gore_lobes"
        ),
        update=_gore_macro_property_updated,
    )
    deformation_gore_redness: FloatProperty(
        **parameter_schema.blender_kwargs(
            "deformation_gore_redness"
        ),
        update=_gore_macro_property_updated,
    )
    deformation_gore_inlay_amount: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_inlay_amount"),
        update=_gore_macro_property_updated,
    )
    deformation_gore_raised_amount: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_raised_amount"),
        update=_gore_macro_property_updated,
    )
    deformation_gore_dirty: BoolProperty(default=False, options={"HIDDEN"})
    deformation_gore_identity_digest: StringProperty(default="", options={"HIDDEN"})
    deformation_gore_transaction_count: IntProperty(default=0, min=0, options={"HIDDEN"})
    deformation_gore_preset: StringProperty(
        name="Legacy Recipe Migration",
        description="Internal compatibility ID for older authored gore records",
        default="USER_AUTHORED",
        options={'HIDDEN'},
    )
    deformation_gore_coverage: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_coverage"), update=_deformation_preview_property_updated)
    deformation_gore_scatter: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_scatter"), update=_deformation_preview_property_updated)
    deformation_gore_edge_feather: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_edge_feather"))
    deformation_gore_wetness: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_wetness"))
    deformation_gore_darkness: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_darkness"))
    deformation_gore_color_bias: FloatVectorProperty(
        description="Linear RGB bias for the procedural blood coating",
        **parameter_schema.blender_vector_kwargs("deformation_gore_color_bias"),
        subtype='COLOR',
    )
    deformation_gore_raised_enabled: BoolProperty(
        name="Enable Generated Gore",
        description="Generate exportable cavity/inlay geometry or an explicit legacy raised shell",
        default=True,
        update=_deformation_preview_property_updated,
    )
    deformation_gore_clot_coverage: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_clot_coverage"))
    deformation_gore_core_density: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_core_density"))
    deformation_gore_surface_mass_value: FloatProperty(
        **parameter_schema.blender_kwargs(
            "deformation_gore_surface_mass_value"
        )
    )
    deformation_gore_nucleus_amount: FloatProperty(
        **parameter_schema.blender_kwargs(
            "deformation_gore_nucleus_amount"
        )
    )
    deformation_gore_nucleus_lobes: FloatProperty(
        **parameter_schema.blender_kwargs(
            "deformation_gore_nucleus_lobes"
        )
    )
    deformation_gore_clot_thickness: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_clot_thickness"),
        update=_deformation_preview_property_updated,
    )
    deformation_gore_thickness_variation: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_thickness_variation"))
    deformation_gore_island_breakup: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_island_breakup"), update=_deformation_preview_property_updated)
    deformation_gore_peripheral_fragments: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_peripheral_fragments"))
    deformation_gore_surface_offset: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_surface_offset")
    )
    deformation_gore_geometry_density: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_geometry_density"))
    deformation_gore_wetness_variation: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_wetness_variation"))
    deformation_gore_dark_clot_bias: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_dark_clot_bias"))
    deformation_gore_rough_edge_bias: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_rough_edge_bias"))
    deformation_gore_color_intensity: FloatProperty(**parameter_schema.blender_kwargs("deformation_gore_color_intensity"))
    deformation_gore_organic_irregularity: FloatProperty(
        description="Break up straight polygon edges and shift refined gore facets without changing the source mesh",
        **parameter_schema.blender_kwargs("deformation_gore_organic_irregularity"),
    )
    deformation_gore_surface_roundness: FloatProperty(
        description="Round and bulge refined clot surfaces so the source triangulation is less visible",
        **parameter_schema.blender_kwargs("deformation_gore_surface_roundness"),
    )
    deformation_gore_texture_enabled: BoolProperty(
        name="Use Muscle-Fiber Textures",
        description="Wrap every refined gore face in a master-seed-selected muscle-fiber direction",
        default=True,
    )
    deformation_gore_fiber_texture_strength: FloatProperty(
        description="Independent additive contribution from the muscle-fiber texture set",
        **parameter_schema.blender_kwargs("deformation_gore_fiber_texture_strength"),
    )
    deformation_gore_base_color_strength: FloatProperty(
        description="Independent additive contribution from the original procedural gore color",
        **parameter_schema.blender_kwargs("deformation_gore_base_color_strength"),
    )
    deformation_gore_inner_rim_enabled: BoolProperty(
        name="Compromised Inner Reddening",
        description="Generate a second reddened barrier just inside each deformed gore-island edge",
        default=True,
    )
    deformation_gore_inner_rim_width: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_inner_rim_width"),
    )
    deformation_gore_inner_rim_strength: FloatProperty(
        description="Control the height and visibility of the breached inner reddening layer",
        **parameter_schema.blender_kwargs("deformation_gore_inner_rim_strength"),
    )
    deformation_gore_maximum_triangles: IntProperty(
        **parameter_schema.blender_kwargs("deformation_gore_maximum_triangles")
    )
    deformation_gore_user_customized: BoolProperty(
        name="Preserve as User-Customized",
        description="Prevent Apply Heavy Gore to All Deformations from replacing this key's recipe",
        default=False,
    )
    deformation_gore_cavity_depth: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_cavity_depth"),
    )
    deformation_gore_liner_separation: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_liner_separation"),
    )
    deformation_gore_rim_width: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_rim_width"),
    )
    deformation_gore_clot_fill_depth: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_clot_fill_depth"),
    )
    deformation_gore_proudness_limit: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_proudness_limit"),
    )
    deformation_gore_host_deformation_contribution: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_host_deformation_contribution"),
    )
    deformation_gore_bone_reveal: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_bone_reveal"),
    )
    deformation_gore_tissue_coverage: FloatProperty(
        **parameter_schema.blender_kwargs("deformation_gore_tissue_coverage"),
    )
    deformation_gore_wound_bed_enabled: BoolProperty(name="Wound Bed", default=True)
    deformation_gore_clot_layer_enabled: BoolProperty(name="Clot Layer", default=True)
    deformation_gore_tissue_layer_enabled: BoolProperty(name="Tissue / Fiber Layer", default=False)
    deformation_gore_bone_layer_enabled: BoolProperty(name="Exposed Bone Plate", default=False)
    deformation_gore_barrier_layer_enabled: BoolProperty(name="Compromised Barrier", default=True)
    deformation_gore_raised_rim_opt_in: BoolProperty(
        name="Explicit Raised Rim",
        description="Allow only the identity's capped rim proudness",
        default=False,
    )
    deformation_gore_allow_internal_fragments: BoolProperty(
        name="Internal Fragments",
        description="Permit deterministic small internal fragments inside the cavity",
        default=False,
    )
    deformation_gore_mask_seed: IntProperty(
        description="Repeatable seed for overlay breakup, islands, fragments, thickness, organic shape, materials, and fiber directions",
        **parameter_schema.blender_kwargs("deformation_gore_mask_seed"),
        update=_gore_seed_property_updated,
    )
    deformation_gore_geometry_status: StringProperty(default="NOT GENERATED", options={"HIDDEN"})
    deformation_gore_validation_status: StringProperty(default="NOT VALIDATED", options={"HIDDEN"})
    deformation_gore_max_proudness: FloatProperty(default=0.0, min=0.0, options={"HIDDEN"})
    deformation_gore_median_cavity_depth: FloatProperty(default=0.0, min=0.0, options={"HIDDEN"})
    deformation_gore_minimum_liner_separation: FloatProperty(default=0.0, min=0.0, options={"HIDDEN"})
    deformation_status: StringProperty(default="NOT INITIALIZED", options={'HIDDEN'})
    last_deformation_validation: StringProperty(default="NOT VALIDATED", options={'HIDDEN'})

    # Core/compound trauma authoring.
    compound_event_id: StringProperty(name="New Event ID", default="Neck_Shoulder_Crush_Left")
    compound_display_name: StringProperty(name="Display Name", default="Neck Shoulder Crush Left")
    compound_active_event_id: StringProperty(name="Active Compound Event", default="", options={'HIDDEN'})
    compound_trauma_family: EnumProperty(
        name="Trauma Family",
        items=[
            ('COMPACT_DENT', "Compact Dent", "Localized inward depression"),
            ('BROAD_CAVE', "Broad Cave", "Wide soft inward collapse"),
            ('FLAT_COMPRESSION', "Flat Compression", "Compress toward an impact plane"),
            ('DIRECTIONAL_SHEAR', "Directional Shear", "Controlled lateral displacement"),
            ('RAISED_IMPACT_RIM', "Raised Impact Rim", "Restrained raised impact lip"),
            ('RIDGE_COLLAPSE', "Ridge Collapse", "Push a ridge inward"),
        ],
        default='BROAD_CAVE',
    )
    compound_semantic_direction: StringProperty(name="Semantic Impact Direction", default="LEFT_TO_RIGHT")
    compound_severity: FloatProperty(name="Severity", default=1.0, min=0.0, max=10.0)
    compound_impact_origin: FloatVectorProperty(
        name="World Impact Origin", size=3, default=(0.0, 0.0, 1.4), subtype='XYZ', unit='LENGTH'
    )
    compound_impact_direction: FloatVectorProperty(
        name="World Impact Direction", size=3, default=(1.0, 0.0, -0.15), subtype='DIRECTION'
    )
    compound_impact_radius: FloatProperty(name="Radius", default=0.16, min=0.005, max=1.0, unit='LENGTH')
    compound_impact_depth: FloatProperty(name="Depth", default=0.035, min=0.0, max=0.25, unit='LENGTH')
    compound_impact_falloff: FloatProperty(name="Falloff", default=1.45, min=0.1, max=8.0)
    compound_impact_strength: FloatProperty(name="Strength", default=1.0, min=0.0, max=2.0)
    compound_displacement_limit: FloatProperty(
        name="Displacement Limit", default=0.065, min=0.001, max=0.25, unit='LENGTH'
    )
    compound_event_seed: IntProperty(name="Event Seed", default=1776, min=0, max=2147483647)
    compound_linked_seam_ids: StringProperty(
        name="Linked Seam IDs", description="Comma-separated Damage Authoring seam contracts", default="head_neck"
    )
    compound_continuity_mode: EnumProperty(
        name="Continuity Mode",
        items=[
            ('LOCK_BOUNDARY_TO_SHARED_FIELD', "Lock Boundary to Shared Field", "Use one compatible mapped boundary displacement"),
            ('BLEND_ACROSS_SEAM', "Blend Across Seam", "Match the boundary and feather inward per participant"),
            ('PROTECT_SEAM', "Protect Seam", "Keep linked seam boundary vertices undisplaced"),
        ],
        default='LOCK_BOUNDARY_TO_SHARED_FIELD',
    )
    compound_activation_weight: FloatProperty(name="Activation Weight", default=0.01, min=0.0, max=2.0)

PREVIEW_FLOOR_NAME = "DSB_PREVIEW_FLOOR"


def find_safe_wrapper(context, *, required=True):
    """Find an optional outer Dreadstone scale wrapper related to the selection."""
    for obj in related(context):
        current = obj
        while current:
            if current.get("dsb_safe_size_wrapper", False):
                return current
            current = current.parent

    # Fallback: useful when the armature is active but selection is unusual.
    candidates = [
        obj for obj in context.scene.objects
        if obj.get("dsb_safe_size_wrapper", False)
    ]
    if len(candidates) == 1:
        return candidates[0]

    if required:
        raise RuntimeError(
            "Could not find the DSB safe wrapper. Select the character or its armature."
        )
    return None


def create_or_update_preview_floor(context, settings):
    floor = bpy.data.objects.get(PREVIEW_FLOOR_NAME)

    if floor is None:
        mesh = bpy.data.meshes.new(PREVIEW_FLOOR_NAME + "_MESH")
        half = settings.preview_floor_size * 0.5
        mesh.from_pydata(
            [
                (-half, -half, 0.0),
                ( half, -half, 0.0),
                ( half,  half, 0.0),
                (-half,  half, 0.0),
            ],
            [],
            [(0, 1, 2, 3)],
        )
        mesh.update()

        floor = bpy.data.objects.new(PREVIEW_FLOOR_NAME, mesh)
        context.collection.objects.link(floor)
    else:
        half = settings.preview_floor_size * 0.5
        if floor.type == 'MESH' and len(floor.data.vertices) >= 4:
            coordinates = [
                (-half, -half, 0.0),
                ( half, -half, 0.0),
                ( half,  half, 0.0),
                (-half,  half, 0.0),
            ]
            for vertex, coordinate in zip(floor.data.vertices[:4], coordinates):
                vertex.co = coordinate
            floor.data.update()

    floor.location = (0.0, 0.0, 0.0)
    floor.rotation_euler = (0.0, 0.0, 0.0)
    floor.scale = (1.0, 1.0, 1.0)
    floor["dsb_preview_only"] = True

    material = bpy.data.materials.get("DSB_PREVIEW_FLOOR_MATERIAL")
    if material is None:
        material = bpy.data.materials.new("DSB_PREVIEW_FLOOR_MATERIAL")
        material.use_nodes = True
        material.diffuse_color = (0.12, 0.14, 0.16, 1.0)

        principled = None
        if material.node_tree:
            principled = material.node_tree.nodes.get("Principled BSDF")
        if principled:
            base_color = principled.inputs.get("Base Color")
            roughness = principled.inputs.get("Roughness")
            metallic = principled.inputs.get("Metallic")
            if base_color:
                base_color.default_value = (0.12, 0.14, 0.16, 1.0)
            if roughness:
                roughness.default_value = 0.88
            if metallic:
                metallic.default_value = 0.0

    if floor.type == 'MESH':
        if not floor.data.materials:
            floor.data.materials.append(material)
        else:
            floor.data.materials[0] = material

    return floor


def align_character_to_floor(context, settings):
    """Move only the safe outer wrapper so the current pose meets Z=0."""
    wrapper = find_safe_wrapper(context)
    meshes = character_meshes(context)
    minimum, _maximum = world_bounds(context, meshes)

    target_lowest_z = -settings.ground_sink
    delta_z = target_lowest_z - minimum.z

    world_matrix = wrapper.matrix_world.copy()
    world_matrix.translation.z += delta_z
    wrapper.matrix_world = world_matrix
    context.view_layer.update()

    return wrapper, minimum.z, target_lowest_z, delta_z


class DAF_OT_create_preview_floor(Operator):
    bl_idname = "daf.create_preview_floor"
    bl_label = "Create / Update Preview Floor"
    bl_description = "Create a solid preview-only floor at world Z zero"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            floor = create_or_update_preview_floor(context, settings)
            self.report(
                {'INFO'},
                f"Preview floor ready at Z=0: {floor.name}"
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_align_feet_to_floor(Operator):
    bl_idname = "daf.align_feet_to_floor"
    bl_label = "Align Current Pose to Floor"
    bl_description = "Move the safe wrapper so the current visible pose touches the floor with the selected sink"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            create_or_update_preview_floor(context, settings)
            wrapper, old_z, target_z, delta_z = align_character_to_floor(
                context,
                settings,
            )
            self.report(
                {'INFO'},
                f"Grounded {wrapper.name}: lowest point {old_z:.4f} m → "
                f"{target_z:.4f} m; moved wrapper {delta_z:+.4f} m."
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

def character_objects_for_armature(context, armature):
    """Collect one rig hierarchy without requiring an outer resize wrapper."""
    scene_objects = set(context.scene.objects)
    objects = {armature}
    objects.update(descendants(armature))

    # A normally rigged character often keeps its meshes beside the armature
    # instead of parenting them below it.  The Armature modifier is the
    # authoritative relationship in that layout, so scan the scene rather than
    # limiting export discovery to the current selection.
    for obj in scene_objects:
        if obj.name == PREVIEW_FLOOR_NAME:
            continue

        if obj.type == 'MESH':
            uses_armature = any(
                modifier.type == 'ARMATURE'
                and modifier.object == armature
                for modifier in obj.modifiers
            )
            if uses_armature or has_ancestor(obj, armature):
                objects.add(obj)

        if obj == armature or has_ancestor(obj, armature):
            objects.add(obj)

    # Include character-owned attachments below the discovered rig and meshes.
    for obj in list(objects):
        objects.update(descendants(obj))

    # Include the full ancestry of every character object.
    for obj in list(objects):
        current = obj.parent
        while current:
            if current.name != PREVIEW_FLOOR_NAME:
                objects.add(current)
            current = current.parent

    return {
        obj for obj in objects
        if obj in scene_objects
        if obj.type in {'EMPTY', 'ARMATURE', 'MESH'}
        and obj.name != PREVIEW_FLOOR_NAME
        and not bool(obj.get("dsb_preview_only", False))
    }


def top_level_objects(objects):
    return [
        obj for obj in objects
        if obj.parent not in objects
    ]


def adopt_or_create_wrapper(context, armature, objects):
    """Reuse an imported root when possible; otherwise add a neutral wrapper."""
    armature_top = armature
    while armature_top.parent and armature_top.parent in objects:
        armature_top = armature_top.parent

    candidates = top_level_objects(objects)

    # Preferred case: the pack retained the Forge root.
    if (
        armature_top.type == 'EMPTY'
        and (
            armature_top.name.startswith("DSB_SIZE_ROOT")
            or len(candidates) == 1
        )
    ):
        return armature_top, False

    # A single imported EMPTY is still the safest existing common root.
    if len(candidates) == 1 and candidates[0].type == 'EMPTY':
        return candidates[0], False

    # Some exporters flatten the neutral parent. Add a scale-1 wrapper only;
    # this does not resize or alter any world-space transforms.
    wrapper = bpy.data.objects.new("DSB_SIZE_ROOT_ADOPTED", None)
    wrapper.empty_display_type = 'CIRCLE'
    wrapper.location = (0.0, 0.0, 0.0)
    wrapper.rotation_euler = (0.0, 0.0, 0.0)
    wrapper.scale = (1.0, 1.0, 1.0)
    context.collection.objects.link(wrapper)

    for obj in candidates:
        world = obj.matrix_world.copy()
        obj.parent = wrapper
        obj.matrix_parent_inverse = wrapper.matrix_world.inverted()
        obj.matrix_world = world

    return wrapper, True


def infer_approved_kind(action_name):
    lower = action_name.lower()

    if "mace" in lower and "brace" in lower and "twoarm" in lower:
        return "MACE_GUARD_TWO_ARM"
    if "mace" in lower and "brace" in lower and "leftarm" in lower:
        return "MACE_GUARD_LEFT_ARM"
    if "mace" in lower and "brace" in lower and "rightarm" in lower:
        return "MACE_GUARD_RIGHT_ARM"

    if "hurt" in lower and "left" in lower:
        return "HURT_LEFT"
    if "hurt" in lower and "right" in lower:
        return "HURT_RIGHT"
    if any(word in lower for word in ("death", "collapse", "faceplant")):
        return "DEATH"
    if "idle" in lower:
        return "IDLE"
    if any(word in lower for word in ("walk", "locomotion")):
        return "WALK"

    return "IMPORTED"


def action_mentions_armature(action, armature):
    """Avoid adopting unrelated DSB Actions when a busy .blend is used."""
    bone_names = set(armature.data.bones.keys())
    mentioned = set()

    for fcurve in iter_action_fcurves(action):
        path = getattr(fcurve, "data_path", "")
        match = re.search(r'pose\.bones\["([^"]+)"\]', path)
        if match:
            mentioned.add(match.group(1))

    # Object-level animation may not mention bones. DSB Actions in a fresh
    # imported pack are still safe to recover.
    return not mentioned or bool(mentioned & bone_names)


def recover_imported_approved_actions(armature):
    recovered = []

    for action in bpy.data.actions:
        if not action.name.startswith("DSB_"):
            continue
        if action.name.startswith("DSB_DRAFT"):
            continue
        if not action_mentions_armature(action, armature):
            continue

        action["dsb_draft"] = False
        action["dsb_approved"] = True
        action["dsb_approved_kind"] = infer_approved_kind(action.name)
        action.use_fake_user = True
        recovered.append(action)

    return sorted(recovered, key=lambda action: action.name.lower())


def write_rig_mapping_report(armature, mapping):
    text = (
        bpy.data.texts.get("DSB_Rig_Mapping.txt")
        or bpy.data.texts.new("DSB_Rig_Mapping.txt")
    )
    text.clear()

    profile = (
        "Skin & Bones canonical humanoid Y+ profile"
        if sbf_handoff.contract(armature) is not None
        else "Generic structural profile"
    )

    text.write("Profile: " + profile + "\n\n")
    text.write(
        "\n".join(
            f"{role}: {name}"
            for role, name in sorted(mapping.items())
        )
    )
    return profile


def select_character_hierarchy(context, wrapper):
    bpy.ops.object.select_all(action='DESELECT')
    wrapper.select_set(True)

    for obj in descendants(wrapper):
        if obj.name != PREVIEW_FLOOR_NAME:
            obj.select_set(True)

    context.view_layer.objects.active = wrapper


class DAF_OT_adopt_imported_pack(Operator):
    bl_idname = "daf.adopt_imported_pack"
    bl_label = "Adopt Imported Animation Pack"
    bl_description = (
        "Recognize an imported Forge GLB without resizing it, recover its "
        "approved Actions, rebuild the rig report, and prepare the floor tools"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            armature = find_armature(context)
            objects = character_objects_for_armature(context, armature)

            meshes = [
                obj for obj in objects
                if obj.type == 'MESH'
            ]
            if not meshes:
                raise RuntimeError(
                    "No skinned character mesh was found beside the armature."
                )

            minimum, maximum = world_bounds(context, meshes)
            visible_height = maximum.z - minimum.z
            if visible_height <= 1.0e-6:
                raise RuntimeError("The imported character height is invalid.")

            wrapper, created_wrapper = adopt_or_create_wrapper(
                context,
                armature,
                objects,
            )

            wrapper["dsb_safe_size_wrapper"] = True
            wrapper["dsb_adopted_imported_pack"] = True
            wrapper["dsb_current_visible_height_m"] = float(visible_height)

            wrapper_scale = wrapper.matrix_world.to_scale()
            uniform_scale = (
                abs(wrapper_scale.x)
                + abs(wrapper_scale.y)
                + abs(wrapper_scale.z)
            ) / 3.0

            inferred_original_height = (
                visible_height / uniform_scale
                if uniform_scale > 1.0e-8
                else visible_height
            )
            wrapper["dsb_original_height_m"] = float(
                inferred_original_height
            )

            # Adoption is recognition-only, but Safe Resize must always aim at
            # the canonical Testman height rather than silently copying a tall
            # imported pack's current height into the target field.
            settings.target_height = 1.50
            wrapper["dsb_target_height_m"] = float(settings.target_height)

            mapping = map_bones(armature, settings)
            profile = write_rig_mapping_report(armature, mapping)
            recovered = recover_imported_approved_actions(armature)

            create_or_update_preview_floor(context, settings)
            select_character_hierarchy(context, wrapper)

            needed = {
                "hips",
                "thigh_l",
                "shin_l",
                "foot_l",
                "thigh_r",
                "shin_r",
                "foot_r",
                "upper_arm_l",
                "upper_arm_r",
                "hand_l",
                "hand_r",
            }
            missing = sorted(needed - set(mapping))

            wrapper_message = (
                "added a neutral scale-1 wrapper"
                if created_wrapper
                else "reused the imported root"
            )

            if missing:
                self.report(
                    {'WARNING'},
                    f"Adopted pack and {wrapper_message}; recovered "
                    f"{len(recovered)} approved Action(s), but mapping is "
                    f"missing: {', '.join(missing)}"
                )
            else:
                self.report(
                    {'INFO'},
                    f"Adopted {visible_height:.3f} m pack without resizing; "
                    f"Safe Resize target reset to {settings.target_height:.3f} m; "
                    f"{wrapper_message}; {profile}; recovered "
                    f"{len(recovered)} approved Action(s)."
                )

            return {'FINISHED'}

        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


POSE_POLISH_PROPERTIES = (
    "left_upper_arm_forward",
    "left_upper_arm_roll",
    "left_elbow_flex",
    "left_forearm_twist",
    "left_wrist_flex",
    "left_wrist_side",
    "left_wrist_roll",
    "right_upper_arm_forward",
    "right_upper_arm_roll",
    "right_elbow_flex",
    "right_forearm_twist",
    "right_wrist_flex",
    "right_wrist_side",
    "right_wrist_roll",
)


class DAF_OT_reset_pose_polish(Operator):
    bl_idname = "daf.reset_pose_polish"
    bl_label = "Zero Arm & Hand Polish"
    bl_description = "Return every arm and wrist pose-polish slider to zero"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.daf_settings
        for property_name in POSE_POLISH_PROPERTIES:
            setattr(settings, property_name, 0.0)

        self.report({'INFO'}, "Arm and hand pose-polish sliders reset.")
        return {'FINISHED'}

class DAF_OT_resize(Operator):
    bl_idname = "daf.safe_resize"
    bl_label = "Safely Resize Character"
    bl_description = "Resize through the outer wrapper, including an existing adopted wrapper, and report the measured result"
    bl_options = {'REGISTER','UNDO'}

    @staticmethod
    def _translate_world(obj, world_delta):
        if obj.parent:
            local_delta = obj.parent.matrix_world.inverted().to_3x3() @ world_delta
            obj.location += local_delta
        else:
            obj.location += world_delta

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            target_height = float(settings.target_height)
            if not math.isfinite(target_height) or target_height <= 1.0e-6:
                raise RuntimeError("Target Height must be greater than zero.")

            objects = related(context)
            meshes = [obj for obj in objects if obj.type == 'MESH' and obj.name != PREVIEW_FLOOR_NAME]
            if not meshes:
                raise RuntimeError("No character mesh found. Select the character or its armature.")

            minimum, maximum = world_bounds(context, meshes)
            current_height = float(maximum.z - minimum.z)
            if current_height <= 1.0e-6:
                raise RuntimeError("The selected character height is invalid.")

            relevant = {obj for obj in objects if obj.type in {'EMPTY','ARMATURE','MESH'} and obj.name != PREVIEW_FLOOR_NAME}
            wrapper = None
            for obj in relevant:
                current = obj
                visited = set()
                while current is not None and current not in visited:
                    if current.get("dsb_safe_size_wrapper", False):
                        wrapper = current
                        break
                    visited.add(current)
                    current = current.parent
                if wrapper:
                    break

            created_wrapper = False
            if wrapper is None:
                tops = [obj for obj in relevant if obj.parent not in relevant]
                if not tops:
                    raise RuntimeError("Could not find a safe top-level character hierarchy to resize.")
                wrapper = bpy.data.objects.new(f"DSB_SIZE_ROOT_{target_height:.2f}m", None)
                wrapper.empty_display_type = 'CIRCLE'
                wrapper.location = (
                    (minimum.x + maximum.x) * 0.5,
                    (minimum.y + maximum.y) * 0.5,
                    minimum.z,
                )
                wrapper.rotation_euler = (0.0, 0.0, 0.0)
                wrapper.scale = (1.0, 1.0, 1.0)
                context.collection.objects.link(wrapper)
                for obj in tops:
                    world = obj.matrix_world.copy()
                    obj.parent = wrapper
                    obj.matrix_parent_inverse = wrapper.matrix_world.inverted()
                    obj.matrix_world = world
                created_wrapper = True

            if abs(current_height - target_height) <= 0.0005:
                wrapper["dsb_safe_size_wrapper"] = True
                wrapper["dsb_target_height_m"] = target_height
                wrapper["dsb_current_visible_height_m"] = current_height
                select_character_hierarchy(context, wrapper)
                self.report({'INFO'}, f"Character already measures {current_height:.3f} m; target is {target_height:.3f} m. No scale change required.")
                return {'FINISHED'}

            old_center = Vector(((minimum.x + maximum.x) * 0.5, (minimum.y + maximum.y) * 0.5, minimum.z))
            factor = target_height / current_height
            wrapper.scale = tuple(float(value) * factor for value in wrapper.scale)
            context.view_layer.update()

            scaled_minimum, scaled_maximum = world_bounds(context, meshes)
            scaled_center = Vector(((scaled_minimum.x + scaled_maximum.x) * 0.5, (scaled_minimum.y + scaled_maximum.y) * 0.5, scaled_minimum.z))
            self._translate_world(wrapper, old_center - scaled_center)
            context.view_layer.update()

            final_minimum, final_maximum = world_bounds(context, meshes)
            final_height = float(final_maximum.z - final_minimum.z)
            if abs(final_height - target_height) > max(0.002, target_height * 0.002):
                correction = target_height / max(final_height, 1.0e-8)
                wrapper.scale = tuple(float(value) * correction for value in wrapper.scale)
                context.view_layer.update()
                corrected_minimum, corrected_maximum = world_bounds(context, meshes)
                corrected_center = Vector(((corrected_minimum.x + corrected_maximum.x) * 0.5, (corrected_minimum.y + corrected_maximum.y) * 0.5, corrected_minimum.z))
                self._translate_world(wrapper, old_center - corrected_center)
                context.view_layer.update()
                final_minimum, final_maximum = world_bounds(context, meshes)
                final_height = float(final_maximum.z - final_minimum.z)

            wrapper["dsb_safe_size_wrapper"] = True
            wrapper["dsb_original_height_m"] = float(wrapper.get("dsb_original_height_m", current_height))
            wrapper["dsb_previous_visible_height_m"] = current_height
            wrapper["dsb_target_height_m"] = target_height
            wrapper["dsb_current_visible_height_m"] = final_height
            wrapper["dsb_last_scale_factor"] = factor
            select_character_hierarchy(context, wrapper)

            action = "Created wrapper and resized" if created_wrapper else "Updated existing safe wrapper"
            self.report(
                {'INFO'},
                f"{action}: {current_height:.3f} m -> {final_height:.3f} m "
                f"(target {target_height:.3f} m, factor {factor:.5f}). Do not apply wrapper scale."
            )
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Safe Resize failed: {e}")
            return {'CANCELLED'}

def analyze_creature_anatomy(context):
    armature = find_armature(context)
    settings = context.scene.daf_settings
    analysis = anatomy_blender.analyze_armature(
        armature,
        settings,
        legacy_humanoid_mapper=map_bones,
    )
    if analysis.get("profileId") == "DSB_HUMANOID_V1":
        write_rig_mapping_report(armature, analysis.get("roleMapping", {}))
    anatomy_blender.write_mapping_text(armature, analysis, bpy.data.texts)
    return armature, analysis


class DAF_OT_analyze_creature_anatomy(Operator):
    bl_idname = "daf.analyze_creature_anatomy"
    bl_label = "Analyze Creature Anatomy"
    bl_description = "Detect, resolve, validate, and persist the selected Creature Anatomy Profile"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            _armature, analysis = analyze_creature_anatomy(context)
            status = str(analysis.get("readinessStatus", "PROFILE_INCOMPLETE"))
            message = (
                f"{status}: {analysis.get('profileId') or 'unresolved'}; "
                f"mapped {analysis.get('mappedRoleCount', 0)} roles at "
                f"{float(analysis.get('detectionConfidence', 0.0)):.0%} confidence."
            )
            if analysis.get("ready"):
                self.report({'INFO'}, message)
            else:
                blocker = str(analysis.get("worstBlocker", ""))
                self.report({'WARNING'}, message + (" " + blocker if blocker else ""))
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_analyze(Operator):
    """Compatibility operator retained for saved workspaces and external tests."""

    bl_idname = "daf.analyze"
    bl_label = "Analyze Creature Anatomy"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            _armature, analysis = analyze_creature_anatomy(context)
            if analysis.get("ready"):
                self.report(
                    {'INFO'},
                    f"{analysis['readinessStatus']}; mapped {analysis['mappedRoleCount']} roles.",
                )
            else:
                self.report({'WARNING'}, str(analysis.get("worstBlocker", analysis.get("readinessStatus"))))
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_show_anatomy_role_mapping(Operator):
    bl_idname = "daf.show_anatomy_role_mapping"
    bl_label = "Show Role Mapping"
    bl_description = "Write the complete anatomy mapping and diagnostics to a Blender Text datablock"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            armature = find_armature(context)
            analysis = anatomy_blender.current_analysis(armature, context.scene.daf_settings)
            if analysis is None:
                raise RuntimeError("Run ANALYZE CREATURE ANATOMY first.")
            text = anatomy_blender.write_mapping_text(armature, analysis, bpy.data.texts)
            self.report({'INFO'}, f"Role mapping written to {text.name}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_clear_anatomy_profile_override(Operator):
    bl_idname = "daf.clear_anatomy_profile_override"
    bl_label = "Clear Profile Override"
    bl_description = "Return to deterministic auto detection and re-analyze the selected rig"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            armature = find_armature(context)
            settings = context.scene.daf_settings
            anatomy_blender.clear_profile_override(armature, settings)
            _armature, analysis = analyze_creature_anatomy(context)
            self.report({'INFO'}, f"Profile override cleared: {analysis['readinessStatus']}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

def style_walk_values(settings):
    values = {
        "stride_l": settings.stride,
        "stride_r": settings.stride,
        "knee_l": settings.knee,
        "knee_r": settings.knee,
        "bob": settings.hip_bob,
        "sway": settings.hip_sway,
        "arms": settings.arm_swing,
        "elbows": settings.elbow_bend,
        "lean": settings.torso_lean,
        "lift": settings.step_lift,
    }

    if settings.walk_style == "HEAVY":
        values["stride_l"] *= .88
        values["stride_r"] *= .88
        values["knee_l"] *= 1.08
        values["knee_r"] *= 1.08
        values["bob"] *= 1.28
        values["sway"] *= 1.22
        values["arms"] *= .78
        values["elbows"] *= 1.25
        values["lean"] += 3.5
    elif settings.walk_style == "CAUTIOUS":
        values["stride_l"] *= .66
        values["stride_r"] *= .66
        values["knee_l"] *= 1.14
        values["knee_r"] *= 1.14
        values["bob"] *= .68
        values["sway"] *= .78
        values["arms"] *= .55
        values["lean"] += 4.0
        values["lift"] *= 1.12
    elif settings.walk_style == "INJURED_LEFT":
        values["stride_l"] *= .55
        values["knee_l"] *= .62
        values["stride_r"] *= .90
        values["bob"] *= 1.12
        values["sway"] *= 1.30
        values["lean"] += 2.5
    elif settings.walk_style == "INJURED_RIGHT":
        values["stride_r"] *= .55
        values["knee_r"] *= .62
        values["stride_l"] *= .90
        values["bob"] *= 1.12
        values["sway"] *= 1.30
        values["lean"] += 2.5

    asymmetry = settings.walk_asymmetry
    values["stride_l"] *= 1.0 - asymmetry
    values["stride_r"] *= 1.0 + asymmetry * .45
    return values



def apply_arm_tuck(arm, mapping, forward_axis, degrees, left_scale=1.0, right_scale=1.0):
    """Adduct both complete arm chains toward the ribs.

    The Skin & Bones rest basis faces +Y. Looking from above, the left chain
    rotates negative and the right chain positive around +Y so both complete
    arm chains descend toward the ribs.
    """
    if degrees <= 0.0:
        return

    left_degrees = degrees * left_scale
    right_degrees = degrees * right_scale

    # Rotate the shoulder parent first so the forearm and hand descend with
    # the complete limb, like lowering the arms during a jumping jack.
    rotate(arm, mapping, "shoulder_l", forward_axis, -left_degrees * .82)
    rotate(arm, mapping, "upper_arm_l", forward_axis, -left_degrees * .18)

    rotate(arm, mapping, "shoulder_r", forward_axis, right_degrees * .82)
    rotate(arm, mapping, "upper_arm_r", forward_axis, right_degrees * .18)


def resolve_brace_side(settings):
    if settings.death_brace_side == "NONE":
        return None
    if settings.death_brace_side in {"LEFT", "RIGHT"}:
        return settings.death_brace_side
    return "RIGHT" if settings.death_pain_side == "LEFT" else "LEFT"


def pain_arm_pose(arm, mapping, side_name, side_axis, forward_axis,
                  upper_degrees, elbow_degrees, inward_degrees, elbow_sign):
    suffix = "l" if side_name == "LEFT" else "r"
    inward_sign = -1.0 if side_name == "LEFT" else 1.0
    rotate(arm, mapping, f"upper_arm_{suffix}", side_axis, upper_degrees)
    rotate(arm, mapping, f"lower_arm_{suffix}", side_axis, elbow_degrees * elbow_sign)
    rotate(
        arm,
        mapping,
        f"upper_arm_{suffix}",
        forward_axis,
        inward_degrees * inward_sign
    )


def brace_arm_pose(arm, mapping, side_name, side_axis, forward_axis,
                   extension_degrees, elbow_degrees, elbow_sign):
    if not side_name:
        return
    suffix = "l" if side_name == "LEFT" else "r"
    outward_sign = 1.0 if side_name == "LEFT" else -1.0
    rotate(arm, mapping, f"upper_arm_{suffix}", side_axis, extension_degrees)
    rotate(arm, mapping, f"lower_arm_{suffix}", side_axis, elbow_degrees * elbow_sign)
    rotate(
        arm,
        mapping,
        f"upper_arm_{suffix}",
        forward_axis,
        18.0 * outward_sign
    )

def apply_terminal_death_pose(
    arm,
    mapping,
    settings,
    forward_axis,
    side_axis,
    up_axis,
    height,
    frame,
    *,
    strength=1.0,
):
    """Author a low, limp terminal pose that puts the whole body on the floor."""

    profile = {
        "CHEST_HOLD": {
            "pitch": 90.0,
            "roll": 4.0,
            "travel": 0.34,
            "curl": 18.0,
            "lead_knee": 72.0,
            "trail_knee": 54.0,
        },
        "FACEPLANT": {
            "pitch": 94.0,
            "roll": 2.0,
            "travel": 0.42,
            "curl": 5.0,
            "lead_knee": 58.0,
            "trail_knee": 42.0,
        },
        "KNEES_FIRST": {
            "pitch": 91.0,
            "roll": 4.0,
            "travel": 0.30,
            "curl": 13.0,
            "lead_knee": 92.0,
            "trail_knee": 76.0,
        },
        "INSTANT_LIMP": {
            "pitch": 94.0,
            "roll": 5.0,
            "travel": 0.36,
            "curl": 5.0,
            "lead_knee": 66.0,
            "trail_knee": 48.0,
        },
    }[settings.collapse_style]
    amount = max(0.0, min(1.0, float(strength)))
    fall_sign = -1.0 if settings.death_pain_side == "LEFT" else 1.0
    knee_sign = -1.0 if settings.invert_knees else 1.0
    elbow_sign = -1.0 if settings.invert_elbows else 1.0

    reset_pose(arm, mapping)
    terminal_pitch = profile["pitch"] * amount
    rotate(arm, mapping, "hips", side_axis, terminal_pitch)
    rotate_for_disabled_inheritance(
        arm,
        mapping,
        (
            "spine", "spine_mid", "chest", "neck", "head",
            "shoulder_l", "upper_arm_l", "lower_arm_l", "hand_l",
            "shoulder_r", "upper_arm_r", "lower_arm_r", "hand_r",
            "thigh_l", "shin_l", "foot_l",
            "thigh_r", "shin_r", "foot_r",
        ),
        side_axis,
        terminal_pitch,
    )
    rotate(
        arm,
        mapping,
        "hips",
        forward_axis,
        profile["roll"] * fall_sign * amount,
    )
    rotate(arm, mapping, "hips", up_axis, 7.0 * fall_sign * amount)

    # Keep the center chain almost horizontal. A restrained curl reads as
    # compression without lifting the head and shoulders back off the floor.
    curl = profile["curl"] * amount
    rotate(arm, mapping, "spine", side_axis, curl * .45)
    rotate(arm, mapping, "spine_mid", side_axis, curl * .20)
    rotate(arm, mapping, "chest", side_axis, curl * .35)
    rotate(arm, mapping, "chest", forward_axis, 4.0 * fall_sign * amount)
    # Finish with the head turned and heavy, but do not let the snout become a
    # single low pivot that suspends the chest above the floor.
    rotate(arm, mapping, "neck", side_axis, -32.0 * amount)
    rotate(arm, mapping, "head", side_axis, -78.0 * amount)
    rotate(arm, mapping, "neck", forward_axis, 24.0 * fall_sign * amount)
    rotate(arm, mapping, "head", forward_axis, 52.0 * fall_sign * amount)

    if settings.death_lead_knee == "LEFT":
        left_knee = profile["lead_knee"]
        right_knee = profile["trail_knee"]
    else:
        right_knee = profile["lead_knee"]
        left_knee = profile["trail_knee"]
    rotate(arm, mapping, "thigh_l", side_axis, -left_knee * .24 * amount)
    rotate(arm, mapping, "thigh_r", side_axis, -right_knee * .21 * amount)
    left_shin_scale = .30 if rotation_inheritance_disabled(arm, mapping, "shin_l") else 1.0
    right_shin_scale = .30 if rotation_inheritance_disabled(arm, mapping, "shin_r") else 1.0
    left_foot_scale = .45 if rotation_inheritance_disabled(arm, mapping, "foot_l") else 1.0
    right_foot_scale = .45 if rotation_inheritance_disabled(arm, mapping, "foot_r") else 1.0
    rotate(
        arm, mapping, "shin_l", side_axis,
        left_knee * knee_sign * left_shin_scale * amount,
    )
    rotate(
        arm, mapping, "shin_r", side_axis,
        right_knee * knee_sign * right_shin_scale * amount,
    )
    rotate(
        arm, mapping, "foot_l", side_axis,
        -left_knee * knee_sign * .32 * left_foot_scale * amount,
    )
    rotate(
        arm, mapping, "foot_r", side_axis,
        -right_knee * knee_sign * .28 * right_foot_scale * amount,
    )

    # No protective brace survives the terminal pose. Unequal limb bends and
    # relaxed wrists make the body read as unconscious rather than supported.
    terminal_tuck = min(18.0, float(settings.death_arm_tuck) * .25)
    apply_arm_tuck(
        arm,
        mapping,
        forward_axis,
        terminal_tuck * amount,
        left_scale=.86,
        right_scale=1.0,
    )
    rotate(arm, mapping, "upper_arm_l", side_axis, 8.0 * amount)
    rotate(arm, mapping, "upper_arm_r", side_axis, -5.0 * amount)
    left_elbow_scale = .50 if rotation_inheritance_disabled(arm, mapping, "lower_arm_l") else 1.0
    right_elbow_scale = .50 if rotation_inheritance_disabled(arm, mapping, "lower_arm_r") else 1.0
    rotate(
        arm, mapping, "lower_arm_l", side_axis,
        28.0 * elbow_sign * left_elbow_scale * amount,
    )
    rotate(
        arm, mapping, "lower_arm_r", side_axis,
        38.0 * elbow_sign * right_elbow_scale * amount,
    )
    rotate_local(arm, mapping, "hand_l", (1.0, 0.0, 0.0), -18.0 * amount)
    rotate_local(arm, mapping, "hand_r", (1.0, 0.0, 0.0), 13.0 * amount)

    offset(
        arm,
        mapping,
        "hips",
        -up_axis * (height * .58 * amount)
        + forward_axis * (height * profile["travel"] * amount)
        + side_axis * (height * .08 * fall_sign * amount),
    )
    key_pose(arm, mapping, frame)


ANIMATION_BASE_POSE_SCHEMA = "dreadstone.animation_base_pose.v1"
ANIMATION_BASE_POSES_PROPERTY = "dsb_animation_base_poses_json"
ANIMATION_BASE_POSE_SESSION_PROPERTY = "dsb_animation_base_pose_session_json"


def animation_base_pose_library(armature):
    raw = str(armature.get(ANIMATION_BASE_POSES_PROPERTY, ""))
    if not raw:
        return {"schema": ANIMATION_BASE_POSE_SCHEMA, "poses": {}}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"schema": ANIMATION_BASE_POSE_SCHEMA, "poses": {}}
    if not isinstance(value, dict) or not isinstance(value.get("poses"), dict):
        return {"schema": ANIMATION_BASE_POSE_SCHEMA, "poses": {}}
    value["schema"] = ANIMATION_BASE_POSE_SCHEMA
    return value


def animation_base_pose(armature, kind):
    return animation_base_pose_library(armature)["poses"].get(str(kind), {})


def store_animation_base_pose(armature, mapping, kind):
    """Capture a reusable additive pose recipe without changing the rest rig."""

    bones = {}
    for role, bone_name in sorted(mapping.items()):
        if role == "root":
            continue
        pose_bone = armature.pose.bones.get(bone_name)
        if pose_bone is None:
            continue
        pose_bone.rotation_mode = 'QUATERNION'
        rotation = pose_bone.rotation_quaternion.normalized()
        bones[role] = {
            "bone": bone_name,
            "rotation": [float(value) for value in rotation],
            "location": [float(value) for value in pose_bone.location],
        }
    library = animation_base_pose_library(armature)
    library["poses"][str(kind)] = {
        "schema": ANIMATION_BASE_POSE_SCHEMA,
        "kind": str(kind),
        "canonicalRigVersion": sbf_handoff.SBF_CANONICAL_RIG_VERSION,
        "bones": bones,
    }
    armature[ANIMATION_BASE_POSES_PROPERTY] = json.dumps(
        library,
        sort_keys=True,
        separators=(",", ":"),
    )
    return library["poses"][str(kind)]


def apply_animation_base_pose(armature, mapping, kind):
    """Apply a captured pose before a generator adds its motion layer."""

    payload = animation_base_pose(armature, kind)
    if not payload:
        return 0
    if (
        str(payload.get("canonicalRigVersion", ""))
        != sbf_handoff.SBF_CANONICAL_RIG_VERSION
    ):
        raise RuntimeError(
            f"{kind} Base Pose was captured for a different canonical rig."
        )
    applied = 0
    for role, record in payload.get("bones", {}).items():
        bone_name = mapping.get(str(role), "")
        pose_bone = armature.pose.bones.get(bone_name) if bone_name else None
        if pose_bone is None or not isinstance(record, dict):
            continue
        rotation = record.get("rotation", ())
        location = record.get("location", ())
        if len(rotation) != 4 or len(location) != 3:
            continue
        values = [float(value) for value in (*rotation, *location)]
        if not all(math.isfinite(value) for value in values):
            continue
        pose_bone.rotation_mode = 'QUATERNION'
        pose_bone.rotation_quaternion = Quaternion(rotation).normalized()
        pose_bone.location = Vector(location)
        applied += 1
    return applied


def clear_animation_base_pose(armature, kind):
    library = animation_base_pose_library(armature)
    removed = library["poses"].pop(str(kind), None) is not None
    if library["poses"]:
        armature[ANIMATION_BASE_POSES_PROPERTY] = json.dumps(
            library,
            sort_keys=True,
            separators=(",", ":"),
        )
    elif ANIMATION_BASE_POSES_PROPERTY in armature:
        del armature[ANIMATION_BASE_POSES_PROPERTY]
    return removed


def stamp_action_base_pose(action, armature, kind):
    payload = animation_base_pose(armature, kind)
    if payload:
        action["dsb_animation_base_pose_kind"] = str(kind)
        action["dsb_animation_base_pose_json"] = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
    else:
        for key in (
            "dsb_animation_base_pose_kind",
            "dsb_animation_base_pose_json",
        ):
            if key in action:
                del action[key]


def regenerate_animation_base_pose_preview(kind):
    """Refresh every draft that consumes the selected shared base pose."""

    operations = {
        "IDLE": ("idle",),
        "HURT": ("hurt_left", "hurt_right"),
        "MACE_GUARD": ("generate_mace_head_guards",),
    }.get(str(kind))
    if operations is None:
        raise RuntimeError(f"Unsupported Draft Base Pose kind: {kind}.")
    for identifier in operations:
        result = getattr(bpy.ops.daf, identifier)()
        if 'FINISHED' not in result:
            raise RuntimeError(
                f"{kind} preview regeneration failed at daf.{identifier}."
            )


def _begin_animation_base_pose_session(context, armature, mapping, kind):
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    armature.animation_data_create()
    animation_data = armature.animation_data
    session = {
        "kind": str(kind),
        "action": animation_data.action.name if animation_data.action else "",
        "tracks": [
            {"name": track.name, "mute": bool(track.mute)}
            for track in animation_data.nla_tracks
        ],
    }
    armature[ANIMATION_BASE_POSE_SESSION_PROPERTY] = json.dumps(
        session,
        sort_keys=True,
        separators=(",", ":"),
    )
    animation_data.action = None
    for track in animation_data.nla_tracks:
        track.mute = True
    reset_pose(armature, mapping)
    apply_animation_base_pose(armature, mapping, kind)
    bpy.ops.object.select_all(action='DESELECT')
    armature.hide_set(False)
    armature.hide_viewport = False
    armature.select_set(True)
    armature.show_in_front = True
    context.view_layer.objects.active = armature
    context.view_layer.update()
    bpy.ops.object.mode_set(mode='POSE')
    return session


def _restore_animation_base_pose_session(armature, *, restore_action):
    raw = str(armature.get(ANIMATION_BASE_POSE_SESSION_PROPERTY, ""))
    try:
        session = json.loads(raw) if raw else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        session = {}
    if armature.animation_data is not None:
        tracks = {
            str(record.get("name", "")): bool(record.get("mute", False))
            for record in session.get("tracks", [])
            if isinstance(record, dict)
        }
        for track in armature.animation_data.nla_tracks:
            if track.name in tracks:
                track.mute = tracks[track.name]
        if restore_action:
            armature.animation_data.action = bpy.data.actions.get(
                str(session.get("action", ""))
            )
    if ANIMATION_BASE_POSE_SESSION_PROPERTY in armature:
        del armature[ANIMATION_BASE_POSE_SESSION_PROPERTY]
    return session


class DAF_OT_edit_animation_base_pose(Operator):
    bl_idname = "daf.edit_animation_base_pose"
    bl_label = "Edit Draft Base Pose"
    bl_description = "Detach animation playback and enter Pose Mode on the reusable additive base pose"
    bl_options = {'REGISTER', 'UNDO'}

    kind: StringProperty(default="IDLE")

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            armature = find_armature(context)
            sbf_handoff.require_canonical_yplus(
                armature,
                label=f"{self.kind} Base Pose editing",
            )
            mapping = map_bones(armature, settings)
            _begin_animation_base_pose_session(
                context,
                armature,
                mapping,
                self.kind,
            )
            if self.kind == "IDLE":
                settings.idle_arm_tuck = 0.0
            settings.animation_base_pose_status = (
                f"EDITING {self.kind} BASE - pose bones, then Capture + Preview"
            )
            self.report(
                {'INFO'},
                f"Editing {self.kind} Base Pose. Pose the body, then Capture + Preview.",
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_capture_animation_base_pose(Operator):
    bl_idname = "daf.capture_animation_base_pose"
    bl_label = "Capture Base Pose and Preview"
    bl_description = "Capture the current manual pose and regenerate the draft with motion layered on top"
    bl_options = {'REGISTER', 'UNDO'}

    kind: StringProperty(default="IDLE")

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            armature = find_armature(context)
            session_raw = str(
                armature.get(ANIMATION_BASE_POSE_SESSION_PROPERTY, "")
            )
            session = json.loads(session_raw) if session_raw else {}
            if str(session.get("kind", "")) != self.kind:
                raise RuntimeError(
                    f"Click Edit {self.kind.title()} Base Pose before capturing."
                )
            mapping = map_bones(armature, settings)
            payload = store_animation_base_pose(
                armature,
                mapping,
                self.kind,
            )
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            _restore_animation_base_pose_session(
                armature,
                restore_action=False,
            )
            bpy.ops.object.select_all(action='DESELECT')
            armature.select_set(True)
            context.view_layer.objects.active = armature
            regenerate_animation_base_pose_preview(self.kind)
            settings.animation_base_pose_status = (
                f"{self.kind} BASE CAPTURED - {len(payload['bones'])} bones"
            )
            self.report(
                {'INFO'},
                f"Captured {self.kind} Base Pose and refreshed its draft preview.",
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_cancel_animation_base_pose(Operator):
    bl_idname = "daf.cancel_animation_base_pose"
    bl_label = "Cancel Base Pose Edit"
    bl_description = "Discard uncaptured pose changes and restore the prior animation state"
    bl_options = {'REGISTER', 'UNDO'}

    kind: StringProperty(default="IDLE")

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            armature = find_armature(context)
            mapping = map_bones(armature, settings)
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            reset_pose(armature, mapping)
            _restore_animation_base_pose_session(
                armature,
                restore_action=True,
            )
            context.view_layer.update()
            settings.animation_base_pose_status = (
                f"{self.kind} Base Pose edit cancelled"
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_clear_animation_base_pose(Operator):
    bl_idname = "daf.clear_animation_base_pose"
    bl_label = "Clear Draft Base Pose"
    bl_description = "Remove the captured base pose and regenerate from the canonical rest pose"
    bl_options = {'REGISTER', 'UNDO'}

    kind: StringProperty(default="IDLE")

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            armature = find_armature(context)
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            _restore_animation_base_pose_session(
                armature,
                restore_action=False,
            )
            clear_animation_base_pose(armature, self.kind)
            bpy.ops.object.select_all(action='DESELECT')
            armature.select_set(True)
            context.view_layer.objects.active = armature
            regenerate_animation_base_pose_preview(self.kind)
            settings.animation_base_pose_status = (
                f"{self.kind} Base Pose cleared"
            )
            self.report({'INFO'}, f"Cleared {self.kind} Base Pose.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_idle(Operator):
    bl_idname = "daf.idle"
    bl_label = "Generate Humanoid Idle"
    bl_description = "Generate a seamless Y+ in-place breathing and weight-shift loop"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            settings = context.scene.daf_settings
            armature = find_armature(context)
            anatomy_blender.require_generator_capability(
                armature,
                "idle",
                "Humanoid Idle generator",
            )
            mapping = map_bones(armature, settings)
            needed = ["root", "hips", "spine", "chest", "head"]
            missing = [role for role in needed if role not in mapping]
            if missing:
                raise RuntimeError("Missing mapped bones: " + ", ".join(missing))

            action = ensure_draft_action(
                armature,
                DRAFT_ACTION_NAMES["IDLE"],
            )
            fps = context.scene.render.fps / max(
                context.scene.render.fps_base,
                0.001,
            )
            start = 1
            loop_frames = max(24, round(float(settings.idle_seconds) * fps))
            end = start + loop_frames
            context.scene.frame_start = start
            context.scene.frame_end = end
            forward, side, up = vectors(settings, armature)

            # The first and last samples are identical. Breathing and the
            # lateral weight shift are quarter-cycle offset so the result does
            # not pulse like a mechanical two-pose loop.
            phases = (
                (0.00, 0.0, -1.0),
                (0.25, 1.0, 0.0),
                (0.50, 0.0, 1.0),
                (0.75, -1.0, 0.0),
                (1.00, 0.0, -1.0),
            )
            for ratio, breath_phase, shift_phase in phases:
                frame = start + round(loop_frames * ratio)
                context.scene.frame_set(frame)
                reset_pose(armature, mapping)
                apply_animation_base_pose(armature, mapping, "IDLE")
                breathing = float(settings.idle_breathing) * breath_phase
                shift = float(settings.idle_weight_shift) * shift_phase

                apply_arm_tuck(
                    armature,
                    mapping,
                    forward,
                    float(settings.idle_arm_tuck),
                )
                rotate(armature, mapping, "hips", forward, 0.75 * shift)
                rotate(armature, mapping, "hips", up, 0.45 * shift)
                rotate(armature, mapping, "spine", side, -0.55 * breathing)
                rotate(armature, mapping, "spine", forward, -0.30 * shift)
                rotate(armature, mapping, "chest", side, 1.15 * breathing)
                rotate(armature, mapping, "chest", forward, 0.50 * shift)
                rotate(armature, mapping, "chest", up, -0.35 * shift)
                rotate(armature, mapping, "head", side, -0.35 * breathing)
                rotate(armature, mapping, "head", forward, -0.30 * shift)
                rotate(armature, mapping, "upper_arm_l", side, 0.35 * breathing)
                rotate(armature, mapping, "upper_arm_r", side, 0.35 * breathing)
                offset(
                    armature,
                    mapping,
                    "hips",
                    up * (0.004 * max(0.0, breathing)),
                )
                apply_arm_hand_pose_polish(
                    armature,
                    mapping,
                    settings,
                    side,
                )
                key_pose(armature, mapping, frame)

            set_bezier(action, cycles=True)
            action["dsb_loop"] = True
            action["dsb_root_motion_policy"] = "IN_PLACE"
            action["dsb_forward_axis"] = "+Y"
            action["dsb_up_axis"] = "+Z"
            animation_library.mark_draft(
                action,
                armature,
                settings,
                "IDLE",
            )
            stamp_action_base_pose(action, armature, "IDLE")
            context.scene.frame_set(start)
            self.report(
                {'INFO'},
                f"Refreshed {action.name}. The first and last poses match for a seamless loop.",
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_walk(Operator):
    bl_idname = "daf.walk"
    bl_label = "Generate Polished Walk"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            s = context.scene.daf_settings
            arm = find_armature(context)
            anatomy_blender.require_generator_capability(arm, "walk", "Humanoid Walk generator")
            m = map_bones(arm, s)
            needed = [
                "hips", "thigh_l", "shin_l", "foot_l",
                "thigh_r", "shin_r", "foot_r",
                "upper_arm_l", "upper_arm_r"
            ]
            missing = [role for role in needed if role not in m]
            if missing:
                raise RuntimeError(
                    "Missing mapped bones: " + ", ".join(missing)
                    + ". Use the Rig Mapping fields."
                )

            action = ensure_draft_action(arm, DRAFT_ACTION_NAMES["WALK"])
            start = 1
            end = start + s.walk_frames
            context.scene.frame_start = start
            context.scene.frame_end = end

            fwd, side, up = vectors(s, arm)
            knee_sign = -1.0 if s.invert_knees else 1.0
            elbow_sign = 1.0 if s.invert_elbows else -1.0
            values = style_walk_values(s)

            # Contact, down, passing, up, opposite contact, then close the loop.
            phases = [
                (0.000,  1.00, -1.00, .12, .36, -.35,  1.00,  1.00, -.70),
                (0.125,  .72,  -.72, .34, .58, -1.00,   .84,  .55, -.92),
                (0.250, -.10,   .10, .22, 1.00,  .62,   .18, -.10,  .22),
                (0.375, -.68,   .68, .46, .76,  1.00,  -.55, -.62,  .55),
                (0.500, -1.00,  1.00, .36, .12, -.35, -1.00, -.70,  1.00),
                (0.625, -.72,   .72, .58, .34, -1.00,  -.84, -.92,  .55),
                (0.750,  .10,  -.10, 1.00, .22,  .62,  -.18,  .22, -.10),
                (0.875,  .68,  -.68, .76, .46,  1.00,   .55,  .55, -.62),
                (1.000,  1.00, -1.00, .12, .36, -.35,  1.00,  1.00, -.70),
            ]

            for phase, lt_r, rt_r, lk_r, rk_r, bob_r, sway_r, lf_r, rf_r in phases:
                frame = start + round(s.walk_frames * phase)
                context.scene.frame_set(frame)
                reset_pose(arm, m)

                # Skin & Bones faces +Y. The canonical thigh basis needs the
                # opposite swing sign from the retired Y- generator so the
                # airborne foot travels from rear to front instead of front
                # to rear.
                left_thigh = -values["stride_l"] * lt_r
                right_thigh = -values["stride_r"] * rt_r
                left_knee = values["knee_l"] * lk_r
                right_knee = values["knee_r"] * rk_r

                # Extra swing-foot clearance during passing.
                if phase in {0.250, 0.750}:
                    if phase == 0.250:
                        right_knee += values["lift"]
                    else:
                        left_knee += values["lift"]

                rotate(arm, m, "thigh_l", side, left_thigh)
                rotate(arm, m, "thigh_r", side, right_thigh)
                rotate(arm, m, "shin_l", side, left_knee * knee_sign)
                rotate(arm, m, "shin_r", side, right_knee * knee_sign)

                rotate(
                    arm, m, "foot_l", side,
                    -s.foot_roll * lf_r - left_knee * knee_sign * .20 - left_thigh * .08
                )
                rotate(
                    arm, m, "foot_r", side,
                    -s.foot_roll * rf_r - right_knee * knee_sign * .20 - right_thigh * .08
                )

                arm_left = -(left_thigh / max(abs(values["stride_l"]), 1.0)) * values["arms"]
                arm_right = -(right_thigh / max(abs(values["stride_r"]), 1.0)) * values["arms"]
                rotate(arm, m, "upper_arm_l", side, arm_left)
                rotate(arm, m, "upper_arm_r", side, arm_right)
                apply_arm_tuck(arm, m, fwd, s.walk_arm_tuck)
                rotate(arm, m, "lower_arm_l", side, values["elbows"] * elbow_sign)
                rotate(arm, m, "lower_arm_r", side, values["elbows"] * elbow_sign)

                sway_direction = 1.0 if sway_r >= 0 else -1.0
                rotate(arm, m, "hips", up, s.pelvis_twist * sway_direction)
                rotate(arm, m, "chest", up, -s.chest_counter_twist * sway_direction)
                rotate(arm, m, "spine", side, values["lean"])
                rotate(
                    arm, m, "chest", fwd,
                    s.shoulder_sway * sway_direction
                )
                rotate(
                    arm, m, "head", side,
                    -values["lean"] * s.head_stability
                )
                rotate(
                    arm, m, "head", fwd,
                    -s.shoulder_sway * sway_direction * s.head_stability
                )

                offset(
                    arm,
                    m,
                    "hips",
                    up * (values["bob"] * bob_r)
                    + side * (values["sway"] * sway_r)
                )
                apply_arm_hand_pose_polish(arm, m, s, side)
                key_pose(arm, m, frame)

            set_bezier(action, cycles=True)
            action["dsb_loop"] = True
            action["dsb_root_motion_policy"] = "IN_PLACE"
            action["dsb_forward_axis"] = "+Y"
            action["dsb_up_axis"] = "+Z"
            animation_library.mark_draft(
                action,
                arm,
                s,
                "WALK",
            )
            context.scene.frame_set(start)
            self.report(
                {'INFO'},
                f"Refreshed {action.name}. Tweak freely; approve it only when finished."
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

class DAF_OT_collapse(Operator):
    bl_idname = "daf.collapse"
    bl_label = "Generate Authored Collapse"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            s = context.scene.daf_settings
            arm = find_armature(context)
            anatomy_blender.require_generator_capability(arm, "collapse", "Humanoid Collapse generator")
            m = map_bones(arm, s)
            needed = [
                "hips", "spine", "head",
                "thigh_l", "shin_l", "thigh_r", "shin_r",
                "upper_arm_l", "lower_arm_l",
                "upper_arm_r", "lower_arm_r"
            ]
            missing = [role for role in needed if role not in m]
            if missing:
                raise RuntimeError("Missing mapped bones: " + ", ".join(missing))

            candidate_meshes = [
                obj for obj in character_objects_for_armature(context, arm)
                if obj.type == 'MESH'
                and obj.name != PREVIEW_FLOOR_NAME
                and not bool(obj.get("dsb_preview_only", False))
            ]
            displayed_meshes = [
                obj for obj in candidate_meshes
                if not obj.hide_render
                and not obj.hide_viewport
                and not obj.hide_get()
            ]
            meshes = displayed_meshes or candidate_meshes
            if not meshes:
                raise RuntimeError(
                    "No skinned character mesh was found for death grounding."
                )

            style_label = {
                "CHEST_HOLD": "ChestHold",
                "FACEPLANT": "Faceplant",
                "KNEES_FIRST": "KneesFirst",
                "INSTANT_LIMP": "InstantUnconscious",
            }[s.collapse_style]
            action = ensure_draft_action(
                arm,
                DRAFT_ACTION_NAMES["DEATH"]
            )

            fps = context.scene.render.fps / max(context.scene.render.fps_base, .001)
            start = 1
            motion_seconds = (
                s.death_instant_seconds
                if s.collapse_style == "INSTANT_LIMP"
                else s.collapse_seconds
            )
            motion_end = start + max(2, round(motion_seconds * fps))
            final_end = motion_end + s.death_hold_frames
            context.scene.frame_start = start
            context.scene.frame_end = final_end

            fwd, side, up = vectors(s, arm)
            knee_sign = -1.0 if s.invert_knees else 1.0
            elbow_sign = -1.0 if s.invert_elbows else 1.0

            context.scene.frame_set(start)
            reset_pose(arm, m)
            context.view_layer.update()
            mn, mx = world_bounds(context, meshes)
            height = max(mx.z - mn.z, .5)
            base_drop = min(max(height * .42, .55), 1.15) * s.death_drop_strength
            base_travel = min(max(height * .22, .28), .60) * s.death_travel_strength
            side_travel = height * .10 * s.death_fall_bias

            style = {
                "hold": 1.0,
                "brace": 1.0,
                "curl": 1.0,
                "travel": 1.0,
                "drop": 1.0,
                "knees": 1.0,
                "head": 1.0,
            }
            if s.collapse_style == "FACEPLANT":
                style.update(
                    hold=.30, brace=.28, curl=1.08,
                    travel=1.25, drop=1.08, knees=.88, head=1.18
                )
            elif s.collapse_style == "KNEES_FIRST":
                style.update(
                    hold=.72, brace=.82, curl=.90,
                    travel=.68, drop=.96, knees=1.18, head=.92
                )
            elif s.collapse_style == "INSTANT_LIMP":
                style.update(
                    hold=0.0, brace=0.0, curl=.62,
                    travel=1.18, drop=1.16, knees=1.0, head=1.32
                )

            # Ratios: curl, hips pitch, lead knee, trailing knee, drop,
            # forward travel, hold arm, brace arm, head, twist, side fall.
            if s.collapse_style == "INSTANT_LIMP":
                poses = [
                    (0.00, 0,  0,  0,  0, 0.00, 0.00, 0.00, 0.00,  0,  0, 0.00),
                    (0.12, 3,  2,  1,  1, 0.02, 0.04, 0.00, 0.00, 12,  0, 0.08),
                    (0.30, 10, 10, 14, 10, 0.18, 0.24, 0.00, 0.00, 32,  2, 0.24),
                    (0.50, 24, 29, 46, 34, 0.48, 0.55, 0.00, 0.00, 55,  5, 0.52),
                    (0.66, 35, 46, 70, 52, 0.76, 0.82, 0.00, 0.00, 68,  7, 0.78),
                ]
                contact_ratio = .74
            else:
                poses = [
                    (0.00, 0,  0,  0,  0, 0.00, 0.00, 0.00, 0.00,  0,  0, 0.00),
                    (0.12, 9,  4,  3,  2, 0.03, 0.01, 0.38, 0.05, -2,  3, 0.03),
                    (0.28, 23, 12, 25, 12, 0.20, 0.08, 0.78, 0.20,  5,  7, 0.12),
                    (0.48, 40, 27, 63, 44, 0.48, 0.25, 1.00, 0.55, 12, 10, 0.35),
                    (0.68, 61, 49, 78, 65, 0.76, 0.58, 0.78, 0.88, 24, 13, 0.68),
                    (0.84, 77, 70, 72, 58, 0.95, 0.90, 0.55, 1.00, 38, 15, 0.92),
                ]
                contact_ratio = .90

            # Alternating, damped body motion: visible but deliberately restrained.
            wiggle_pattern = [0.0, .65, -.85, .90, -.62, .38, -.14, 0.0]

            pain_side = s.death_pain_side
            brace_side = resolve_brace_side(s)
            if brace_side == pain_side:
                brace_side = "RIGHT" if pain_side == "LEFT" else "LEFT"

            for pose_index, pose in enumerate(poses):
                (
                    time_ratio, curl, hip_pitch, lead_knee, trail_knee,
                    drop_r, travel_r, hold_r, brace_r,
                    head_r, twist_r, side_r
                ) = pose
                frame = start + round((motion_end - start) * time_ratio)
                context.scene.frame_set(frame)
                reset_pose(arm, m)
                apply_arm_tuck(arm, m, fwd, s.death_arm_tuck)

                if s.death_lead_knee == "LEFT":
                    left_knee = lead_knee
                    right_knee = trail_knee
                else:
                    right_knee = lead_knee
                    left_knee = trail_knee

                left_knee *= s.death_knee_strength * style["knees"]
                right_knee *= s.death_knee_strength * style["knees"]
                curl *= s.death_curl_strength * style["curl"]
                head_r *= s.death_head_lag * style["head"]
                twist_r *= s.death_twist_strength

                rotate(arm, m, "hips", side, hip_pitch * style["curl"])
                rotate(arm, m, "hips", up, twist_r)
                rotate(arm, m, "spine", side, curl * .55)
                rotate(arm, m, "spine_mid", side, curl * .15)
                rotate(arm, m, "chest", side, curl * .30)
                rotate(arm, m, "chest", up, -twist_r * .55)
                rotate(
                    arm, m, "spine", fwd,
                    s.death_fall_bias * 16.0 * side_r
                )
                rotate(
                    arm, m, "chest", fwd,
                    s.death_fall_bias * 11.0 * side_r
                )
                rotate(arm, m, "neck", side, head_r * .35)
                rotate(arm, m, "head", side, head_r)

                wiggle = (
                    0.0
                    if s.collapse_style == "INSTANT_LIMP"
                    else wiggle_pattern[pose_index] * s.death_wiggle
                )
                rotate(arm, m, "hips", up, wiggle * 4.0)
                rotate(arm, m, "spine", fwd, wiggle * 6.5)
                rotate(arm, m, "chest", fwd, -wiggle * 8.0)
                rotate(arm, m, "head", fwd, wiggle * 4.5)

                rotate(arm, m, "thigh_l", side, -left_knee * .28)
                rotate(arm, m, "thigh_r", side, -right_knee * .25)
                rotate(arm, m, "shin_l", side, left_knee * knee_sign)
                rotate(arm, m, "shin_r", side, right_knee * knee_sign)
                rotate(arm, m, "foot_l", side, -left_knee * knee_sign * .25)
                rotate(arm, m, "foot_r", side, -right_knee * knee_sign * .25)

                pain_arm_pose(
                    arm, m, pain_side, side, fwd,
                    50.0 * hold_r * style["hold"],
                    76.0 * hold_r * style["hold"],
                    24.0 * hold_r * style["hold"],
                    elbow_sign
                )
                brace_arm_pose(
                    arm, m, brace_side, side, fwd,
                    -68.0 * brace_r * style["brace"],
                    18.0 * brace_r * style["brace"],
                    elbow_sign
                )

                # Final relaxation after the main impact.
                if pose_index == len(poses) - 1:
                    settle = s.death_settle
                    rotate(arm, m, "head", fwd, 5.0 * settle)
                    rotate(arm, m, "lower_arm_l", fwd, -5.0 * settle)
                    rotate(arm, m, "lower_arm_r", fwd, 4.0 * settle)
                    rotate(arm, m, "foot_l", up, -4.0 * settle)
                    rotate(arm, m, "foot_r", up, 3.0 * settle)

                offset(
                    arm,
                    m,
                    "hips",
                    -up * (base_drop * drop_r * style["drop"])
                    + fwd * (base_travel * travel_r * style["travel"])
                    + side * (side_travel * side_r)
                    + side * (height * .010 * wiggle)
                )
                apply_arm_hand_pose_polish(arm, m, s, side)
                key_pose(arm, m, frame)

            contact_start = start + round((motion_end - start) * contact_ratio)
            apply_terminal_death_pose(
                arm,
                m,
                s,
                fwd,
                side,
                up,
                height,
                contact_start,
                strength=.84,
            )
            apply_terminal_death_pose(
                arm,
                m,
                s,
                fwd,
                side,
                up,
                height,
                motion_end,
                strength=1.0,
            )

            # Duplicate the exact grounded terminal pose so runtime playback
            # freezes in a fully settled body-contact state.
            context.scene.frame_set(motion_end)
            key_pose(arm, m, final_end)

            set_bezier(action, cycles=False)
            grounding = bake_grounded_death_motion(
                context,
                action,
                arm,
                m,
                meshes,
                start,
                final_end,
                ground_sink=s.ground_sink,
                terminal_frame=motion_end,
                reference_height=height,
            )
            action["dsb_floor_grounded"] = True
            action["dsb_ground_floor_z"] = grounding["floor_z"]
            action["dsb_ground_sink_m"] = grounding["ground_sink_m"]
            action["dsb_ground_sample_count"] = grounding["sample_count"]
            action["dsb_grounded_frame_count"] = grounding["grounded_frame_count"]
            action["dsb_ground_max_correction_m"] = grounding["maximum_correction_m"]
            action["dsb_ground_minimum_z"] = grounding["minimum_z"]
            action["dsb_ground_max_upward_correction_m"] = grounding[
                "maximum_upward_correction_m"
            ]
            action["dsb_ground_max_downward_correction_m"] = grounding[
                "maximum_downward_correction_m"
            ]
            action["dsb_terminal_contact_baked"] = True
            action["dsb_terminal_contact_frame"] = grounding[
                "terminal_contact_frame"
            ]
            action["dsb_terminal_reference_height_m"] = grounding[
                "reference_height_m"
            ]
            action["dsb_terminal_height_m"] = grounding["terminal_height_m"]
            action["dsb_terminal_height_ratio"] = grounding[
                "terminal_height_ratio"
            ]
            action["dsb_terminal_max_height_ratio"] = grounding[
                "maximum_terminal_height_ratio"
            ]
            action["dsb_ground_carrier_role"] = grounding["carrier_role"]
            action["dsb_ground_carrier_bone"] = grounding["carrier_bone"]
            action["dsb_terminal_torso_minimum_z"] = grounding[
                "terminal_torso_minimum_z"
            ]
            action["dsb_terminal_torso_height_m"] = grounding[
                "terminal_torso_height_m"
            ]
            action["dsb_terminal_torso_height_ratio"] = grounding[
                "terminal_torso_height_ratio"
            ]
            action["dsb_terminal_max_torso_height_ratio"] = grounding[
                "maximum_terminal_torso_height_ratio"
            ]
            action["dsb_torso_contact_tolerance_m"] = grounding[
                "torso_contact_tolerance_m"
            ]
            action["dsb_torso_contact_regions_json"] = json.dumps(
                grounding["torso_regions"],
                sort_keys=True,
                separators=(",", ":"),
            )
            action["dsb_ground_max_torso_safety_lift_m"] = grounding[
                "maximum_torso_safety_lift_m"
            ]
            action["dsb_forward_axis"] = "+Y"
            action["dsb_up_axis"] = "+Z"
            action["dsb_root_motion_bone"] = grounding["carrier_bone"]
            animation_library.mark_draft(
                action,
                arm,
                s,
                "DEATH",
            )
            context.scene.frame_set(start)
            self.report(
                {'INFO'},
                f"Refreshed {action.name}. Tweak freely; approve it only when finished."
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

def generate_flank_hurt(context, operator, pain_side):
    s = context.scene.daf_settings
    arm = find_armature(context)
    anatomy_blender.require_generator_capability(arm, "hurt", "Humanoid Hurt generator")
    m = map_bones(arm, s)
    needed = [
        "hips", "spine", "chest", "head",
        "upper_arm_l", "lower_arm_l",
        "upper_arm_r", "lower_arm_r",
        "thigh_l", "shin_l", "thigh_r", "shin_r"
    ]
    missing = [role for role in needed if role not in m]
    if missing:
        raise RuntimeError("Missing mapped bones: " + ", ".join(missing))

    action = ensure_draft_action(
        arm,
        DRAFT_ACTION_NAMES[
            "HURT_LEFT" if pain_side == "LEFT" else "HURT_RIGHT"
        ]
    )
    fps = context.scene.render.fps / max(context.scene.render.fps_base, .001)
    start = 1
    end = start + round(s.hurt_seconds * fps)
    context.scene.frame_start = start
    context.scene.frame_end = end

    fwd, side, up = vectors(s, arm)
    knee_sign = -1.0 if s.invert_knees else 1.0
    elbow_sign = -1.0 if s.invert_elbows else 1.0
    # With canonical +Y forward, anatomical left is -X and right is +X.
    pain_sign = -1.0 if pain_side == "LEFT" else 1.0
    opposite_side = "RIGHT" if pain_side == "LEFT" else "LEFT"

    # Impact, maximum contraction, brief hold, then partial recovery.
    stages = [
        (0.00, 0.00),
        (0.10, 0.55),
        (0.28, 1.00),
        (0.52, 0.92),
        (0.76, 0.52),
        (1.00, 1.0 - s.hurt_recovery),
    ]

    for time_ratio, intensity in stages:
        frame = start + round((end - start) * time_ratio)
        context.scene.frame_set(frame)
        reset_pose(arm, m)
        apply_animation_base_pose(arm, m, "HURT")

        severity = s.hurt_severity * intensity
        torso = s.hurt_torso_bend * severity
        twist = s.hurt_twist * severity
        knee = 18.0 * s.hurt_knee_dip * severity
        hand = s.hurt_hand_reach * severity
        head = s.hurt_head_recoil * severity

        rotate(arm, m, "hips", fwd, 5.0 * pain_sign * torso)
        rotate(arm, m, "spine", fwd, 15.0 * pain_sign * torso)
        rotate(arm, m, "spine_mid", fwd, 7.0 * pain_sign * torso)
        rotate(arm, m, "chest", fwd, 8.0 * pain_sign * torso)
        rotate(arm, m, "chest", up, 15.0 * pain_sign * twist)
        rotate(arm, m, "head", fwd, -9.0 * pain_sign * head)
        rotate(arm, m, "head", side, -6.0 * head)

        flank = s.hurt_hand_to_flank * severity
        upper_angle = max(8.0, 46.0 * hand - 24.0 * flank)
        elbow_angle = 72.0 * hand + 18.0 * flank
        inward_angle = 30.0 * hand + 10.0 * flank

        pain_arm_pose(
            arm, m, pain_side, side, fwd,
            upper_angle,
            elbow_angle,
            inward_angle,
            elbow_sign
        )

        pain_suffix = "l" if pain_side == "LEFT" else "r"
        rotate(
            arm,
            m,
            f"upper_arm_{pain_suffix}",
            up,
            pain_sign * 16.0 * flank
        )
        rotate(
            arm,
            m,
            f"lower_arm_{pain_suffix}",
            fwd,
            -pain_sign * 8.0 * flank
        )
        rotate(
            arm,
            m,
            f"hand_{pain_suffix}",
            side,
            -12.0 * flank * elbow_sign
        )
        brace_arm_pose(
            arm, m, opposite_side, side, fwd,
            -12.0 * severity,
            12.0 * severity,
            elbow_sign
        )

        rotate(arm, m, "thigh_l", side, -knee * .12)
        rotate(arm, m, "thigh_r", side, -knee * .12)
        rotate(arm, m, "shin_l", side, knee * knee_sign)
        rotate(arm, m, "shin_r", side, knee * knee_sign)

        offset(
            arm,
            m,
            "hips",
            -up * (.035 * severity)
            - side * (pain_sign * s.hurt_stagger * intensity)
            - fwd * (s.hurt_stagger * .35 * intensity)
        )
        apply_arm_hand_pose_polish(arm, m, s, side)
        key_pose(arm, m, frame)

    set_bezier(action, cycles=False)
    animation_library.mark_draft(
        action,
        arm,
        s,
        "HURT_LEFT" if pain_side == "LEFT" else "HURT_RIGHT",
    )
    stamp_action_base_pose(action, arm, "HURT")
    context.scene.frame_set(start)
    operator.report({'INFO'}, f"Refreshed {action.name}. Approve it only when finished.")
    return {'FINISHED'}


class DAF_OT_hurt_left(Operator):
    bl_idname = "daf.hurt_left"
    bl_label = "Generate Left-Flank Hurt"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            return generate_flank_hurt(context, self, "LEFT")
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_hurt_right(Operator):
    bl_idname = "daf.hurt_right"
    bl_label = "Generate Right-Flank Hurt"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            return generate_flank_hurt(context, self, "RIGHT")
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


MACE_GUARD_VARIANTS = {
    "MACE_GUARD_TWO_ARM": {
        "guardVariant": "TWO_ARM_HEAD_GUARD",
        "presentedRegions": ("forearm_left", "forearm_right", "head"),
        "leftScale": 1.0,
        "rightScale": 0.92,
        "torsoTurn": 2.0,
    },
    "MACE_GUARD_LEFT_ARM": {
        "guardVariant": "LEFT_ARM_EMERGENCY_HEAD_GUARD",
        "presentedRegions": ("forearm_left", "head"),
        "leftScale": 1.0,
        "rightScale": 0.24,
        "torsoTurn": -8.0,
    },
    "MACE_GUARD_RIGHT_ARM": {
        "guardVariant": "RIGHT_ARM_EMERGENCY_HEAD_GUARD",
        "presentedRegions": ("forearm_right", "head"),
        "leftScale": 0.24,
        "rightScale": 1.0,
        "torsoTurn": 8.0,
    },
}

MACE_GUARD_STYLE_PROFILES = {
    # The default 4.0 cower is informed by protective-motion reference:
    # recognize, compress, lift the elbows, then wrap the forearms around the
    # crown/temples for a readable hold.
    "COWERING": {
        "torsoCurl": 1.55,
        "headTuck": 1.45,
        "crouch": 1.35,
        "shoulderHunch": 1.35,
        "armCover": 1.18,
        "armWrap": 1.18,
        "elbowScale": 1.0,
        "asymmetryScale": 1.0,
        "releaseBias": 0.0,
    },
    "DEFENSIVE": {
        "torsoCurl": 1.10,
        "headTuck": 1.10,
        "crouch": 0.85,
        "shoulderHunch": 1.10,
        "armCover": 1.08,
        "armWrap": 1.05,
        "elbowScale": 0.95,
        "asymmetryScale": 0.75,
        "releaseBias": 0.08,
    },
    # With untouched sliders this profile reproduces the 3.20.1 generator's
    # twisted attack-like pose, including its 112-degree elbow and .42 end pose.
    "ZOMBIE_ATTACK": {
        "torsoCurl": 1.0,
        "headTuck": 1.0,
        "crouch": 1.0,
        "shoulderHunch": 1.0,
        "armCover": 1.0,
        "armWrap": 1.0,
        "elbowScale": 112.0 / 124.0,
        "asymmetryScale": 0.60,
        "releaseBias": 0.13,
    },
}


def mace_guard_frame_schedule(fps, raise_seconds=0.65, hold_seconds=1.20, recovery_seconds=0.60):
    """Build a scene-FPS-aware brace with recognition, cover, hold, and release."""
    fps = max(float(fps), 0.001)
    start = 1
    guard = start + max(1, round(float(raise_seconds) * fps))
    hold_end = guard + max(1, round(float(hold_seconds) * fps))
    end = hold_end + max(1, round(float(recovery_seconds) * fps))
    recognition = start + max(1, round((guard - start) * 0.22))
    covering = start + max(1, round((guard - start) * 0.64))
    return {
        "Brace_Start": start,
        "Recognition": recognition,
        "Covering": covering,
        "Guard_Active": guard,
        "Guard_Hold_End": hold_end,
        "Brace_End": end,
    }


def _set_action_marker(action, name, frame):
    marker = action.pose_markers.get(name)
    if marker is None:
        marker = action.pose_markers.new(name)
    marker.frame = int(frame)
    return marker


def _apply_mace_guard_pose(arm, mapping, settings, variant, intensity):
    fwd, side, up = vectors(settings, arm)
    elbow_sign = -1.0 if settings.invert_elbows else 1.0
    profile = MACE_GUARD_STYLE_PROFILES.get(
        settings.mace_guard_style,
        MACE_GUARD_STYLE_PROFILES["COWERING"],
    )
    left_scale = float(variant["leftScale"]) * intensity
    right_scale = float(variant["rightScale"]) * intensity
    torso_curl = float(settings.mace_guard_torso_curl) * profile["torsoCurl"]
    head_tuck = float(settings.mace_guard_head_tuck) * profile["headTuck"]
    crouch = float(settings.mace_guard_crouch) * profile["crouch"]
    shoulder_hunch = (
        float(settings.mace_guard_shoulder_hunch) * profile["shoulderHunch"]
    )
    arm_cover = float(settings.mace_guard_arm_cover) * profile["armCover"]
    arm_wrap = float(settings.mace_guard_arm_wrap) * profile["armWrap"]
    elbow_flex = float(settings.mace_guard_elbow_flex) * profile["elbowScale"]
    right_asymmetry = max(
        0.25,
        1.0
        - float(settings.mace_guard_asymmetry) * profile["asymmetryScale"],
    )

    # Instinctive compression: chin tuck, slight recoil, raised shoulders, and
    # softened knees. Only rotation/location channels are authored.
    rotate(arm, mapping, "spine", side, -7.0 * torso_curl * intensity)
    rotate(arm, mapping, "chest", side, -10.0 * torso_curl * intensity)
    rotate(arm, mapping, "chest", up, float(variant["torsoTurn"]) * intensity)
    rotate(arm, mapping, "neck", side, 8.0 * head_tuck * intensity)
    rotate(arm, mapping, "head", side, 17.0 * head_tuck * intensity)
    rotate(arm, mapping, "head", up, -float(variant["torsoTurn"]) * 0.30 * intensity)
    rotate(arm, mapping, "thigh_l", side, -5.0 * crouch * intensity)
    rotate(arm, mapping, "thigh_r", side, -5.0 * crouch * intensity)
    rotate(arm, mapping, "shin_l", side, 11.0 * crouch * intensity)
    rotate(arm, mapping, "shin_r", side, 11.0 * crouch * intensity)
    offset(
        arm,
        mapping,
        "hips",
        -up * (0.024 * crouch * intensity)
        - fwd * (0.012 * torso_curl * intensity),
    )

    for suffix, scale, inward_sign, asymmetry in (
        ("l", left_scale, -1.0, 1.0),
        ("r", right_scale, 1.0, right_asymmetry),
    ):
        rotate(
            arm,
            mapping,
            f"shoulder_{suffix}",
            side,
            -16.0 * shoulder_hunch * scale,
        )
        rotate(
            arm,
            mapping,
            f"upper_arm_{suffix}",
            side,
            -76.0 * arm_cover * scale * asymmetry,
        )
        rotate(
            arm,
            mapping,
            f"upper_arm_{suffix}",
            fwd,
            inward_sign * 38.0 * arm_wrap * scale,
        )
        rotate(
            arm,
            mapping,
            f"upper_arm_{suffix}",
            up,
            -inward_sign * 8.0 * arm_wrap * scale,
        )
        rotate(
            arm,
            mapping,
            f"lower_arm_{suffix}",
            side,
            elbow_flex * scale * elbow_sign,
        )
        rotate(
            arm,
            mapping,
            f"lower_arm_{suffix}",
            fwd,
            -inward_sign * 11.0 * arm_wrap * scale,
        )
        rotate_local(
            arm,
            mapping,
            f"lower_arm_{suffix}",
            (0.0, 1.0, 0.0),
            inward_sign * 18.0 * arm_wrap * scale,
        )
        rotate_local(
            arm,
            mapping,
            f"hand_{suffix}",
            (1.0, 0.0, 0.0),
            -12.0 * arm_wrap * scale,
        )
        rotate_local(
            arm,
            mapping,
            f"hand_{suffix}",
            (0.0, 0.0, 1.0),
            inward_sign * 8.0 * arm_wrap * scale,
        )


def _point_segment_distance(point, start, end):
    segment = end - start
    length_squared = segment.length_squared
    if length_squared <= 1.0e-12:
        return float((point - start).length)
    factor = max(0.0, min(1.0, float((point - start).dot(segment) / length_squared)))
    return float((point - (start + segment * factor)).length)


def validate_mace_guard_action(context, action, arm=None, mapping=None):
    errors = []
    warnings = []
    coverage = []
    variant_name = str(action.get("dsb_guard_variant", ""))
    if variant_name not in {value["guardVariant"] for value in MACE_GUARD_VARIANTS.values()}:
        errors.append("Mace guard action has invalid or missing guard-variant metadata.")
    curves = iter_action_fcurves(action)
    if any("scale" in str(getattr(curve, "data_path", "")) for curve in curves):
        errors.append("Mace guard action contains forbidden bone-scale animation.")
    allowed_channels = ("rotation_quaternion", "location")
    forbidden = sorted({
        str(getattr(curve, "data_path", ""))
        for curve in curves
        if not any(str(getattr(curve, "data_path", "")).endswith(channel) for channel in allowed_channels)
    })
    if forbidden:
        errors.append("Mace guard action contains forbidden channels: " + ", ".join(forbidden[:4]) + ".")
    start, end = action_frame_bounds(action)
    if not math.isfinite(start) or not math.isfinite(end) or end <= start:
        errors.append("Mace guard action range is invalid.")
    markers = {marker.name: int(marker.frame) for marker in action.pose_markers}
    for required in ("Brace_Start", "Guard_Active", "Brace_End"):
        if required not in markers:
            errors.append(f"Mace guard action is missing {required} marker.")
    if "Guard_Active" in markers and not start <= markers["Guard_Active"] <= end:
        errors.append("Mace guard Guard_Active marker lies outside the action range.")
    try:
        presented = json.loads(str(action.get("dsb_presented_regions_json", "[]")))
    except (TypeError, json.JSONDecodeError):
        presented = []
        errors.append("Mace guard action has malformed presented-region metadata.")
    if not isinstance(presented, list) or not all(isinstance(value, str) for value in presented):
        presented = []
        errors.append("Mace guard action presented-region metadata must be an array of strings.")
    if not presented or "head" not in presented:
        errors.append("Mace guard action has no presented-region metadata for the head.")

    if not errors and context is not None:
        arm = arm or find_armature(context)
        mapping = mapping or map_bones(arm, context.scene.daf_settings)
        previous_action = arm.animation_data.action if arm.animation_data else None
        previous_frame = context.scene.frame_current
        try:
            if not arm.animation_data:
                arm.animation_data_create()
            arm.animation_data.action = action
            context.scene.frame_set(markers["Guard_Active"])
            head = arm.pose.bones.get(mapping.get("head", ""))
            if head is None:
                errors.append("Mace guard validation is missing the mapped head bone.")
            else:
                world = arm.matrix_world
                head_start = world @ head.head
                head_end = world @ head.tail
                head_center = (head_start + head_end) * 0.5
                head_length = max(float((head_end - head_start).length), 1.0e-6)
                sides = []
                if "forearm_left" in presented:
                    sides.append("l")
                if "forearm_right" in presented:
                    sides.append("r")
                for suffix in sides:
                    forearm = arm.pose.bones.get(mapping.get(f"lower_arm_{suffix}", ""))
                    if forearm is None:
                        errors.append(f"Mace guard validation is missing the mapped {suffix} forearm bone.")
                        continue
                    forearm_start = world @ forearm.head
                    forearm_end = world @ forearm.tail
                    forearm_length = max(
                        float((forearm_end - forearm_start).length),
                        1.0e-6,
                    )
                    distance = _point_segment_distance(
                        head_center,
                        forearm_start,
                        forearm_end,
                    )
                    coverage_limit = max(
                        head_length * 4.0,
                        forearm_length * 1.75,
                    )
                    coverage.append({
                        "side": suffix,
                        "distanceToHead": distance,
                        "coverageLimit": coverage_limit,
                    })
                    if distance > coverage_limit:
                        warnings.append(
                            f"Mace guard {suffix} forearm may not visually cover the head at Guard_Active; "
                            "adjust Arm Cover Height, Guard Elbow Flex, or Forearm Wrap if desired."
                        )
        finally:
            context.scene.frame_set(previous_frame)
            arm.animation_data.action = previous_action
    return {
        "status": "FAIL" if errors else "PASS",
        "action": action.name,
        "guardVariant": variant_name,
        "guardActiveFrame": markers.get("Guard_Active"),
        "presentedRegions": presented,
        "coverage": coverage,
        "warnings": warnings,
        "errors": errors,
    }


def generate_mace_guard_action(context, kind):
    if kind not in MACE_GUARD_VARIANTS:
        raise RuntimeError(f"Unknown mace guard variant {kind!r}.")
    settings = context.scene.daf_settings
    arm = find_armature(context)
    anatomy_blender.require_generator_capability(arm, "mace_head_guard", "Mace Head-Guard generator")
    mapping = map_bones(arm, settings)
    required = [
        "hips", "spine", "chest", "neck", "head",
        "upper_arm_l", "lower_arm_l", "hand_l",
        "upper_arm_r", "lower_arm_r", "hand_r",
        "thigh_l", "shin_l", "thigh_r", "shin_r",
    ]
    missing = [role for role in required if role not in mapping]
    if missing:
        raise RuntimeError("Missing mapped bones for mace head guard: " + ", ".join(missing) + ".")
    action = ensure_draft_action(arm, DRAFT_ACTION_NAMES[kind])
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    schedule = mace_guard_frame_schedule(
        fps,
        settings.mace_guard_raise_seconds,
        settings.mace_guard_hold_seconds,
        settings.mace_guard_recovery_seconds,
    )
    context.scene.frame_start = schedule["Brace_Start"]
    context.scene.frame_end = schedule["Brace_End"]
    stages = (
        (schedule["Brace_Start"], 0.0),
        (schedule["Recognition"], 0.12),
        (schedule["Covering"], 0.68),
        (schedule["Guard_Active"], 1.0),
        (schedule["Guard_Hold_End"], 0.98),
        (
            schedule["Brace_End"],
            max(
                0.0,
                1.0
                - min(
                    1.0,
                    float(settings.mace_guard_end_release)
                    + MACE_GUARD_STYLE_PROFILES.get(
                        settings.mace_guard_style,
                        MACE_GUARD_STYLE_PROFILES["COWERING"],
                    )["releaseBias"],
                ),
            ),
        ),
    )
    side_axis = vectors(settings, arm)[1]
    variant = MACE_GUARD_VARIANTS[kind]
    for frame, intensity in stages:
        context.scene.frame_set(frame)
        reset_pose(arm, mapping)
        apply_animation_base_pose(arm, mapping, "MACE_GUARD")
        _apply_mace_guard_pose(arm, mapping, settings, variant, intensity)
        apply_arm_hand_pose_polish(arm, mapping, settings, side_axis)
        key_pose(arm, mapping, frame)
    for marker_name in (
        "Brace_Start",
        "Recognition",
        "Covering",
        "Guard_Active",
        "Guard_Hold_End",
        "Brace_End",
    ):
        _set_action_marker(action, marker_name, schedule[marker_name])
    action["dsb_guard_variant"] = variant["guardVariant"]
    action["dsb_guard_style"] = settings.mace_guard_style
    action["dsb_guard_active_frame"] = int(schedule["Guard_Active"])
    action["dsb_guard_active_time_seconds"] = float(
        (schedule["Guard_Active"] - schedule["Brace_Start"]) / max(fps, 0.001)
    )
    action["dsb_presented_regions_json"] = json.dumps(list(variant["presentedRegions"]))
    action["dsb_interruptible"] = True
    action["dsb_root_motion_policy"] = "IN_PLACE"
    action["dsb_draft_kind"] = kind
    action["dsb_guard_action_id"] = action.name
    set_bezier(action, cycles=False)
    animation_library.mark_draft(
        action,
        arm,
        settings,
        kind,
    )
    stamp_action_base_pose(action, arm, "MACE_GUARD")
    validation = validate_mace_guard_action(context, action, arm, mapping)
    action["dsb_guard_validation_status"] = validation["status"]
    action["dsb_guard_validation_json"] = json.dumps(validation, sort_keys=True)
    if validation["status"] != "PASS":
        raise RuntimeError("Generated mace guard failed validation: " + "; ".join(validation["errors"][:4]))
    context.scene.frame_set(schedule["Guard_Active"])
    return action


def generate_all_mace_guard_actions(context):
    """Regenerate the three disposable guard drafts as one safe transaction."""

    arm = find_armature(context)
    if not arm.animation_data:
        arm.animation_data_create()
    original_action = arm.animation_data.action
    original_action_name = original_action.name if original_action is not None else ""
    draft_names = [DRAFT_ACTION_NAMES[kind] for kind in MACE_GUARD_VARIANTS]
    active_users = {draft_name: [] for draft_name in draft_names}

    # Refuse all three before copying/removing anything when a draft became an
    # NLA dependency. ``unlink_action_everywhere`` performs the same preflight
    # for individual generation.
    for draft_name in draft_names:
        existing = bpy.data.actions.get(draft_name)
        if existing is None:
            continue
        for obj in bpy.data.objects:
            animation_data = getattr(obj, "animation_data", None)
            if animation_data is None:
                continue
            if animation_data.action == existing:
                active_users[draft_name].append(obj)
            if any(strip.action == existing for track in animation_data.nla_tracks for strip in track.strips):
                raise RuntimeError(
                    f"Draft Action '{draft_name}' is used by an NLA strip. Remove it from NLA before regenerating."
                )

    backups = {}
    for draft_name in draft_names:
        existing = bpy.data.actions.get(draft_name)
        if existing is None:
            continue
        backup = existing.copy()
        backup.name = "__DSB_GUARD_BACKUP_" + draft_name
        backup.use_fake_user = True
        backups[draft_name] = (backup, bool(existing.use_fake_user))

    try:
        actions = [generate_mace_guard_action(context, kind) for kind in MACE_GUARD_VARIANTS]
    except Exception:
        for draft_name in draft_names:
            current = bpy.data.actions.get(draft_name)
            if current is not None:
                unlink_action_everywhere(current)
                try:
                    bpy.data.actions.remove(current, do_unlink=True)
                except TypeError:
                    bpy.data.actions.remove(current)
            backup_record = backups.get(draft_name)
            if backup_record is not None:
                backup, original_fake_user = backup_record
                backup.name = draft_name
                backup.use_fake_user = original_fake_user
                for obj in active_users[draft_name]:
                    if not obj.animation_data:
                        obj.animation_data_create()
                    obj.animation_data.action = backup
        if original_action_name in backups:
            arm.animation_data.action = bpy.data.actions.get(original_action_name)
        else:
            try:
                arm.animation_data.action = original_action
            except ReferenceError:
                arm.animation_data.action = None
        raise
    for backup, _original_fake_user in backups.values():
        try:
            bpy.data.actions.remove(backup, do_unlink=True)
        except TypeError:
            bpy.data.actions.remove(backup)
    return actions


def validate_all_mace_guard_actions(context):
    arm = find_armature(context)
    mapping = map_bones(arm, context.scene.daf_settings)
    records = []
    ownership = {}
    for action in bpy.data.actions:
        if not action.get("dsb_guard_variant"):
            continue
        record = validate_mace_guard_action(context, action, arm, mapping)
        records.append(record)
        action_id = str(action.get("dsb_guard_action_id", ""))
        ownership.setdefault(action_id, []).append(action.name)
    errors = [
        f"Duplicate mace guard action ownership {action_id!r}: {', '.join(names)}."
        for action_id, names in ownership.items() if not action_id or len(names) > 1
    ]
    errors.extend(
        f"{record['action']}: {message}"
        for record in records for message in record["errors"]
    )
    return {"status": "FAIL" if errors else "PASS", "actions": records, "errors": errors}


class DAF_OT_generate_mace_head_guards(Operator):
    bl_idname = "daf.generate_mace_head_guards"
    bl_label = "Generate Three Mace Head-Guard Drafts"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            actions = generate_all_mace_guard_actions(context)
            self.report({'INFO'}, "Generated: " + ", ".join(action.name for action in actions) + ".")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_preview_mace_guard_active(Operator):
    bl_idname = "daf.preview_mace_guard_active"
    bl_label = "Preview Guard_Active"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            kind = context.scene.daf_settings.mace_guard_preview_variant
            action = bpy.data.actions.get(DRAFT_ACTION_NAMES[kind])
            if action is None:
                approved = [
                    value for value in bpy.data.actions
                    if value.get("dsb_approved_kind") == kind
                ]
                action = sorted(approved, key=lambda value: value.name)[-1] if approved else None
            if action is None:
                raise RuntimeError("Generate or approve the selected mace guard variant first.")
            arm = find_armature(context)
            if not arm.animation_data:
                arm.animation_data_create()
            arm.animation_data.action = action
            frame = int(action.get("dsb_guard_active_frame", 1))
            context.scene.frame_set(frame)
            presented = json.loads(str(action.get("dsb_presented_regions_json", "[]")))
            object_names = {"head": "DSB_ATTACHED_HEAD", "forearm_left": "DSB_ATTACHED_FOREARM_L", "forearm_right": "DSB_ATTACHED_FOREARM_R"}
            bpy.ops.object.select_all(action='DESELECT')
            selected = []
            for region_id in presented:
                obj = bpy.data.objects.get(object_names.get(region_id, ""))
                if obj is not None:
                    obj.select_set(True)
                    selected.append(obj)
            if selected:
                context.view_layer.objects.active = selected[0]
            self.report({'INFO'}, f"{action.name} at Guard_Active frame {frame}; presented regions selected.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_validate_mace_head_guards(Operator):
    bl_idname = "daf.validate_mace_head_guards"
    bl_label = "Validate Mace Head-Guard Drafts"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            validation = validate_all_mace_guard_actions(context)
            if validation["status"] != "PASS":
                self.report({'ERROR'}, "; ".join(validation["errors"][:4]))
                return {'CANCELLED'}
            self.report({'INFO'}, f"Validated {len(validation['actions'])} mace head-guard actions.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def _apply_offensive_pose(arm, mapping, settings, variant, swing):
    """Apply one readable rotation-only attack pose across torso and arms."""

    fwd, side, up = vectors(settings, arm)
    motion = variant["motion"]
    two_hand = bool(variant.get("secondarySocketRole"))
    elbow_sign = -1.0 if settings.invert_elbows else 1.0
    torso_power = float(variant.get("torsoPower", 1.0))
    arm_reach = float(variant.get("armReach", 1.0))
    elbow_flex = float(variant.get("elbowFlex", 1.0))
    wrist_action = float(variant.get("wristAction", 1.0))
    stance = float(variant.get("stanceCompression", 1.0))

    if motion in {"SLASH_RTL", "SLASH_LTR", "TWO_HAND_SLASH", "HEAVY"}:
        direction = -1.0 if motion == "SLASH_LTR" else 1.0
        weight = 1.28 if motion == "HEAVY" else 1.12 if two_hand else 1.0
        rotate(arm, mapping, "hips", up, direction * swing * 8.0 * weight * torso_power)
        rotate(arm, mapping, "spine", up, direction * swing * 14.0 * weight * torso_power)
        rotate(arm, mapping, "chest", up, direction * swing * 25.0 * weight * torso_power)
        rotate(arm, mapping, "chest", side, -abs(swing) * 5.0 * weight * torso_power)
        rotate(arm, mapping, "shoulder_r", side, -14.0 * abs(swing) * arm_reach)
        rotate(arm, mapping, "upper_arm_r", up, direction * swing * 68.0 * arm_reach)
        rotate(arm, mapping, "upper_arm_r", side, (-42.0 - abs(swing) * 22.0) * arm_reach)
        rotate(arm, mapping, "lower_arm_r", side, (58.0 - swing * 24.0) * elbow_sign * elbow_flex)
        rotate_local(arm, mapping, "lower_arm_r", (0.0, 1.0, 0.0), direction * swing * 34.0 * wrist_action)
        rotate_local(arm, mapping, "hand_r", (0.0, 0.0, 1.0), -direction * swing * 18.0 * wrist_action)
        if two_hand:
            rotate(arm, mapping, "shoulder_l", side, -12.0 * abs(swing) * arm_reach)
            rotate(arm, mapping, "upper_arm_l", up, direction * swing * 52.0 * arm_reach)
            rotate(arm, mapping, "upper_arm_l", side, (-36.0 - abs(swing) * 18.0) * arm_reach)
            rotate(arm, mapping, "lower_arm_l", side, (76.0 - swing * 18.0) * elbow_sign * elbow_flex)
            rotate_local(arm, mapping, "hand_l", (0.0, 0.0, 1.0), direction * swing * 14.0 * wrist_action)
    elif motion in {"OVERHEAD", "TWO_HAND_OVERHEAD"}:
        weight = 1.12 if two_hand else 1.0
        lift = max(0.0, -swing)
        descend = max(0.0, swing)
        rotate(arm, mapping, "hips", side, (lift * 5.0 - descend * 8.0) * weight * torso_power)
        rotate(arm, mapping, "spine", side, (lift * 9.0 - descend * 15.0) * weight * torso_power)
        rotate(arm, mapping, "chest", side, (lift * 16.0 - descend * 28.0) * weight * torso_power)
        for suffix, lateral in (("r", 1.0), ("l", -1.0)):
            if suffix == "l" and not two_hand:
                continue
            rotate(arm, mapping, f"shoulder_{suffix}", side, -18.0 * lift * arm_reach)
            rotate(arm, mapping, f"upper_arm_{suffix}", side, (-72.0 * lift + 58.0 * descend) * arm_reach)
            rotate(arm, mapping, f"upper_arm_{suffix}", fwd, lateral * (18.0 if two_hand else 7.0) * arm_reach)
            rotate(arm, mapping, f"lower_arm_{suffix}", side, (54.0 + lift * 38.0 - descend * 28.0) * elbow_sign * elbow_flex)
            rotate_local(arm, mapping, f"hand_{suffix}", (1.0, 0.0, 0.0), -swing * 16.0 * wrist_action)
    elif motion in {"THRUST", "TWO_HAND_THRUST"}:
        extension = max(-1.0, min(1.0, swing))
        rotate(arm, mapping, "hips", up, -extension * 5.0 * torso_power)
        rotate(arm, mapping, "spine", side, -extension * 7.0 * torso_power)
        rotate(arm, mapping, "chest", side, -extension * 13.0 * torso_power)
        rotate(arm, mapping, "chest", up, -extension * 8.0 * torso_power)
        for suffix, lateral in (("r", 1.0), ("l", -1.0)):
            if suffix == "l" and not two_hand:
                continue
            rotate(arm, mapping, f"shoulder_{suffix}", side, -10.0 * abs(extension) * arm_reach)
            rotate(arm, mapping, f"upper_arm_{suffix}", side, (-54.0 - extension * 24.0) * arm_reach)
            rotate(arm, mapping, f"upper_arm_{suffix}", fwd, lateral * (16.0 if two_hand else 6.0) * arm_reach)
            elbow = 92.0 - (extension + 1.0) * 36.0
            rotate(arm, mapping, f"lower_arm_{suffix}", side, elbow * elbow_sign * elbow_flex)
            rotate_local(arm, mapping, f"hand_{suffix}", (1.0, 0.0, 0.0), extension * 9.0 * wrist_action)
        offset(arm, mapping, "hips", fwd * (0.026 * max(0.0, extension) * stance))

    rotate(arm, mapping, "thigh_l", side, -4.0 * abs(swing) * stance)
    rotate(arm, mapping, "thigh_r", side, -4.0 * abs(swing) * stance)
    rotate(arm, mapping, "shin_l", side, 7.0 * abs(swing) * stance)
    rotate(arm, mapping, "shin_r", side, 7.0 * abs(swing) * stance)


def validate_offensive_action(
    context,
    action,
    *,
    require_approved=None,
    available_socket_roles=None,
    require_motion_validation=True,
):
    start, end = action_frame_bounds(action)
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    require_approved = bool(action.get("dsb_approved", False)) if require_approved is None else bool(require_approved)
    errors = []
    try:
        metadata = offensive_actions.validated_action_metadata(
            action,
            clip_duration_seconds=max(0.0, end - start) / max(fps, 0.001),
            require_approved=require_approved,
            available_socket_roles=available_socket_roles,
        )
    except ValueError as exc:
        metadata = None
        errors.append(str(exc))
    if metadata is None:
        errors.append("Action has no offensive metadata.")
    curves = iter_action_fcurves(action)
    if not curves:
        errors.append("Offensive Action contains no animation curves.")
    if any(str(getattr(curve, "data_path", "")).endswith(".scale") for curve in curves):
        errors.append("Offensive Action contains forbidden bone-scale animation.")
    kind = str(action.get("dsb_approved_kind", action.get("dsb_draft_kind", "")))
    if not kind.startswith("ATTACK_"):
        errors.append("Offensive Action kind must use the ATTACK_ namespace.")
    if action.get(offensive_motion.MOTION_RECIPE_PROPERTY) and require_motion_validation:
        try:
            recipe = offensive_motion.read_motion_recipe(action)
            report = offensive_motion.read_json(
                action,
                offensive_motion.MOTION_VALIDATION_PROPERTY,
                "Motion Studio validation",
            )
            armature = find_armature(context)
            current_digest = offensive_motion_studio.validation_input_digest(
                armature,
                action,
                recipe,
            )
            if report is None:
                errors.append("Motion Studio baked weapon path has not been validated.")
            elif report.get("status") != "PASS":
                errors.extend(
                    "Motion Studio: " + message
                    for message in report.get("errors", ["Baked weapon-path validation failed."])
                )
            elif str(report.get("inputDigest", "")) != current_digest:
                errors.append("Motion Studio baked-path validation is stale after a trajectory-critical change.")
            elif not bool(report.get("activeContact", False)):
                errors.append("Motion Studio baked weapon path does not contact its target during ACTIVE.")
            if require_approved:
                errors.extend(offensive_motion_studio.approval_errors(context, action))
        except (RuntimeError, ValueError) as exc:
            errors.append(str(exc))
    markers = {marker.name: int(marker.frame) for marker in action.pose_markers}
    for name in ("Attack_Start", "Active_Start", "Active_End", "Attack_End"):
        if name not in markers:
            errors.append(f"Offensive Action is missing {name} marker.")
    return {
        "status": "FAIL" if errors else "PASS",
        "action": action.name,
        "combatActionId": metadata.get("combatActionId") if metadata else None,
        "metadata": metadata,
        "markers": markers,
        "errors": errors,
    }


def generate_offensive_action(context, kind, *, recipe=None):
    base_variant = offensive_actions.OFFENSIVE_ACTION_VARIANTS.get(kind)
    if base_variant is None:
        raise RuntimeError(f"Unknown offensive Action kind {kind!r}.")
    recipe = recipe or offensive_actions.default_offensive_recipe(base_variant)
    try:
        variant = offensive_actions.offensive_variant_with_recipe(kind, recipe)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from None
    settings = context.scene.daf_settings
    arm = find_armature(context)
    anatomy_blender.require_generator_capability(arm, "offensive_humanoid", "Humanoid offensive generator")
    mapping = map_bones(arm, settings)
    required = [
        "hips", "spine", "chest", "shoulder_r", "upper_arm_r", "lower_arm_r", "hand_r",
        "thigh_l", "shin_l", "thigh_r", "shin_r",
    ]
    if variant.get("secondarySocketRole"):
        required.extend(("shoulder_l", "upper_arm_l", "lower_arm_l", "hand_l"))
    missing = [role for role in required if role not in mapping]
    if missing:
        raise RuntimeError("Missing mapped bones for humanoid offense: " + ", ".join(missing) + ".")
    action = ensure_draft_action(arm, variant["draftName"])
    fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
    metadata, schedule = offensive_actions.phase_metadata(variant, fps)
    context.scene.frame_start = schedule["start"]
    context.scene.frame_end = schedule["end"]
    stages = (
        (schedule["start"], 0.0),
        (schedule["anticipation"], -1.0 * variant["anticipationStrength"]),
        (schedule["activeStart"], -0.64 * variant["anticipationStrength"]),
        (schedule["contact"], 0.56 * variant["strikeStrength"]),
        (schedule["activeEnd"], 1.0 * variant["followThrough"]),
        (schedule["end"], 0.0),
    )
    for frame, swing in stages:
        context.scene.frame_set(frame)
        reset_pose(arm, mapping)
        apply_animation_base_pose(arm, mapping, "IDLE")
        _apply_offensive_pose(arm, mapping, settings, variant, swing)
        key_pose(arm, mapping, frame)
    for marker_name, frame in (
        ("Attack_Start", schedule["start"]),
        ("Windup_Anticipation", schedule["anticipation"]),
        ("Active_Start", schedule["activeStart"]),
        ("Contact", schedule["contact"]),
        ("Active_End", schedule["activeEnd"]),
        ("Attack_End", schedule["end"]),
    ):
        _set_action_marker(action, marker_name, frame)
    action["dsb_draft_kind"] = kind
    action["dsb_root_motion_policy"] = "IN_PLACE"
    offensive_actions.stamp_offensive_metadata(action, metadata)
    offensive_actions.stamp_offensive_recipe(action, recipe)
    action["dsb_offensive_previewed"] = False
    action["dsb_offensive_preview_count"] = 0
    set_bezier(action, cycles=False)
    animation_library.mark_draft(action, arm, settings, kind)
    validation = validate_offensive_action(context, action, require_approved=False)
    action["dsb_offensive_validation_status"] = validation["status"]
    action["dsb_offensive_validation_json"] = json.dumps(validation, sort_keys=True)
    if validation["status"] != "PASS":
        raise RuntimeError("Generated offensive Action failed validation: " + "; ".join(validation["errors"][:4]))
    context.scene.frame_set(schedule["activeStart"])
    return action


def generate_humanoid_offensive_suite(context):
    """Regenerate the compact eight-Action suite with rollback on failure."""

    arm = find_armature(context)
    if not arm.animation_data:
        arm.animation_data_create()
    original_action = arm.animation_data.action
    backups = {}
    recipes = {}
    for kind, variant in offensive_actions.OFFENSIVE_ACTION_VARIANTS.items():
        recipes[kind] = _latest_offensive_recipe(kind)
        draft_name = variant["draftName"]
        existing = bpy.data.actions.get(draft_name)
        if existing is None:
            continue
        unlink_action_everywhere(existing)
        backup = existing.copy()
        backup.name = "__DSB_OFFENSE_BACKUP_" + draft_name
        backup.use_fake_user = True
        backups[draft_name] = (backup, bool(existing.use_fake_user))
    try:
        actions = [
            generate_offensive_action(context, kind, recipe=recipes[kind])
            for kind in offensive_actions.OFFENSIVE_ACTION_VARIANTS
        ]
    except Exception:
        for variant in offensive_actions.OFFENSIVE_ACTION_VARIANTS.values():
            draft_name = variant["draftName"]
            current = bpy.data.actions.get(draft_name)
            if current is not None:
                unlink_action_everywhere(current)
                bpy.data.actions.remove(current, do_unlink=True)
            if draft_name in backups:
                backup, fake_user = backups[draft_name]
                backup.name = draft_name
                backup.use_fake_user = fake_user
        arm.animation_data.action = original_action if original_action and original_action.name in bpy.data.actions else None
        raise
    for backup, _fake_user in backups.values():
        bpy.data.actions.remove(backup, do_unlink=True)
    return actions


def generate_selected_offensive_action(context):
    settings = context.scene.daf_settings
    kind = str(settings.offensive_preview_kind)
    recipe = offensive_recipe_from_settings(settings, kind)
    return generate_offensive_action(context, kind, recipe=recipe)


def preview_offensive_action(context, kind=None, *, start_playback=True):
    settings = context.scene.daf_settings
    kind = str(kind or settings.offensive_preview_kind)
    variant = offensive_actions.OFFENSIVE_ACTION_VARIANTS.get(kind)
    if variant is None:
        raise RuntimeError(f"Unknown offensive Action kind {kind!r}.")
    action = bpy.data.actions.get(variant["draftName"])
    if action is None or not bool(action.get("dsb_draft", False)):
        raise RuntimeError("Refresh the selected offensive draft before previewing it.")
    if action.get(offensive_motion.MOTION_RECIPE_PROPERTY):
        return {
            **offensive_motion_studio.preview_motion(
                context,
                start_playback=start_playback,
            ),
            "kind": kind,
        }
    validation = validate_offensive_action(context, action, require_approved=False)
    if validation["status"] != "PASS":
        raise RuntimeError("Draft preview validation failed: " + "; ".join(validation["errors"][:4]))
    arm = find_armature(context)
    playback = animation_library.play_action(
        context,
        arm,
        action,
        start_playback=start_playback,
    )
    action["dsb_offensive_previewed"] = True
    action["dsb_offensive_preview_count"] = int(action.get("dsb_offensive_preview_count", 0)) + 1
    settings.animation_library_status = f"PREVIEWED — {action.name}"
    return {**playback, "kind": kind, "previewCount": int(action["dsb_offensive_preview_count"])}


def validate_all_offensive_actions(context, *, require_approved=None, available_socket_roles=None):
    records = []
    identities = {}
    for action in bpy.data.actions:
        if not action.get(offensive_actions.OFFENSIVE_ACTION_PROPERTY):
            continue
        record = validate_offensive_action(
            context,
            action,
            require_approved=require_approved,
            available_socket_roles=available_socket_roles,
        )
        records.append(record)
        identities.setdefault(record.get("combatActionId"), []).append(action.name)
    errors = [f"{record['action']}: {message}" for record in records for message in record["errors"]]
    errors.extend(
        f"Ambiguous combatActionId {action_id!r}: {', '.join(names)}."
        for action_id, names in identities.items()
        if not action_id or len(names) > 1
    )
    return {"status": "FAIL" if errors else "PASS", "actions": records, "errors": errors}


class DAF_OT_generate_humanoid_offensive_suite(Operator):
    bl_idname = "daf.generate_humanoid_offensive_suite"
    bl_label = "Generate Humanoid Offensive Suite"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            actions = generate_humanoid_offensive_suite(context)
            self.report({'INFO'}, f"Generated {len(actions)} customizable offensive drafts.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_generate_selected_offensive_draft(Operator):
    bl_idname = "daf.generate_selected_offensive_draft"
    bl_label = "Refresh Selected Offensive Draft"
    bl_description = "Apply the visible timing and motion sliders to the selected character-specific draft"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            action = generate_selected_offensive_action(context)
            self.report({'INFO'}, f"Refreshed {action.name}. Preview it before approval.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_preview_offensive_draft(Operator):
    bl_idname = "daf.preview_offensive_draft"
    bl_label = "Preview Selected Offensive Draft"
    bl_description = "Play the selected draft on this character across its exact authored attack range"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            result = preview_offensive_action(context, start_playback=True)
            self.report(
                {'INFO'},
                f"Previewing {result['action']} ({result['frameStart']}–{result['frameEnd']}).",
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_reset_offensive_sliders(Operator):
    bl_idname = "daf.reset_offensive_sliders"
    bl_label = "Reset Offensive Sliders"
    bl_description = "Restore the selected attack's built-in humanoid starting values without changing any saved Action"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.daf_settings
        kind = str(settings.offensive_preview_kind)
        try:
            recipe = offensive_actions.default_offensive_recipe(
                offensive_actions.OFFENSIVE_ACTION_VARIANTS[kind]
            )
            apply_offensive_recipe_to_settings(settings, recipe)
            settings.animation_library_status = "OFFENSIVE SLIDERS RESET — refresh draft to apply"
            self.report({'INFO'}, "Restored the selected attack's starting slider values.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_validate_humanoid_offensive_suite(Operator):
    bl_idname = "daf.validate_humanoid_offensive_suite"
    bl_label = "Validate Humanoid Offensive Suite"
    bl_options = {'REGISTER'}

    def execute(self, context):
        validation = validate_all_offensive_actions(context, require_approved=None)
        if validation["status"] != "PASS":
            self.report({'ERROR'}, "; ".join(validation["errors"][:4]))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Validated {len(validation['actions'])} offensive Actions.")
        return {'FINISHED'}


class DAF_OT_approve_draft(Operator):
    bl_idname = "daf.approve_draft"
    bl_label = "Version / Approve Draft"
    bl_description = "Rename the disposable draft into the next permanent version and protect it"
    bl_options = {'REGISTER', 'UNDO'}

    kind: StringProperty()

    def execute(self, context):
        try:
            action = approve_draft_action(context, self.kind)
            self.report(
                {'INFO'},
                f"Approved and protected: {action.name}. "
                "The next generation will create a fresh draft."
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_approve_active_legacy(Operator):
    bl_idname = "daf.approve_active_legacy"
    bl_label = "Protect Active Legacy Action"
    bl_description = "Mark the currently active older DSB Action as approved so cleanup will preserve it"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            armature = find_armature(context)
            animation_data = armature.animation_data
            action = animation_data.action if animation_data else None

            if action is None:
                raise RuntimeError("The selected armature has no active Action.")
            if not action.name.startswith("DSB_"):
                raise RuntimeError("The active Action is not a DSB-generated Action.")

            action["dsb_approved"] = True
            action["dsb_draft"] = False
            action.use_fake_user = True
            animation_library.mark_approved(
                action,
                armature,
                context.scene.daf_settings,
                infer_approved_kind(action.name),
            )

            self.report(
                {'INFO'},
                f"Protected legacy Action: {action.name}"
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_purge_unapproved_attempts(Operator):
    bl_idname = "daf.purge_unapproved_attempts"
    bl_label = "Delete Unapproved DSB Attempts"
    bl_description = "Delete old generated DSB Actions except the active Action, approved Actions, and current drafts"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            active_action = None
            try:
                armature = find_armature(context)
                if armature.animation_data:
                    active_action = armature.animation_data.action
            except Exception:
                pass

            draft_names = set(DRAFT_ACTION_NAMES.values())
            removed = []

            for action in list(bpy.data.actions):
                if not action.name.startswith("DSB_"):
                    continue
                if action == active_action:
                    continue
                if action.name in draft_names:
                    continue
                if bool(action.get("dsb_approved", False)):
                    continue

                # Do not destroy Actions used by NLA.
                nla_used = False
                for obj in bpy.data.objects:
                    animation_data = getattr(obj, "animation_data", None)
                    if not animation_data:
                        continue
                    for track in animation_data.nla_tracks:
                        for strip in track.strips:
                            if strip.action == action:
                                nla_used = True
                                break
                        if nla_used:
                            break
                    if nla_used:
                        break

                if nla_used:
                    continue

                name = action.name
                try:
                    bpy.data.actions.remove(action, do_unlink=True)
                except TypeError:
                    bpy.data.actions.remove(action)
                removed.append(name)

            self.report(
                {'INFO'},
                f"Deleted {len(removed)} unapproved DSB attempt(s)."
            )
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

def approved_actions():
    return sorted(
        [
            action for action in bpy.data.actions
            if bool(action.get("dsb_approved", False))
            and not bool(action.get("dsb_draft", False))
        ],
        key=lambda action: action.name.lower(),
    )


def action_frame_bounds(action):
    frames = []
    for fcurve in iter_action_fcurves(action):
        for point in fcurve.keyframe_points:
            frame = float(point.co[0])
            if math.isfinite(frame):
                frames.append(frame)
    if frames:
        return min(frames), max(frames)
    try:
        return float(action.frame_range[0]), float(action.frame_range[1])
    except Exception:
        return 1.0, 1.0


def action_pack_metadata(action, fps):
    start, end = action_frame_bounds(action)
    curves = iter_action_fcurves(action)
    keyframe_count = sum(len(curve.keyframe_points) for curve in curves)
    has_scale_curves = any(
        ".scale" in getattr(curve, "data_path", "")
        or getattr(curve, "data_path", "").endswith("scale")
        for curve in curves
    )
    non_finite = 0
    for curve in curves:
        for point in curve.keyframe_points:
            try:
                if not (
                    math.isfinite(float(point.co[0]))
                    and math.isfinite(float(point.co[1]))
                ):
                    non_finite += 1
            except Exception:
                non_finite += 1

    lower = action.name.lower()
    kind = str(action.get("dsb_approved_kind", ""))
    loop = kind in {"IDLE", "WALK"} or "walk" in lower or "idle" in lower
    death = kind == "DEATH" or any(word in lower for word in ("death", "collapse", "faceplant"))
    hurt = kind in {"HURT_LEFT", "HURT_RIGHT"} or "hurt" in lower
    offensive = action.get(offensive_actions.OFFENSIVE_ACTION_PROPERTY)
    try:
        torso_contact_regions = json.loads(
            str(action.get("dsb_torso_contact_regions_json", "{}"))
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        torso_contact_regions = {}
    result = {
        "name": action.name,
        "approved_kind": kind or None,
        "frame_start": round(start, 4),
        "frame_end": round(end, 4),
        "frame_count": round(max(0.0, end - start), 4),
        "duration_seconds": round(max(0.0, end - start) / max(fps, 0.001), 6),
        "fcurve_count": len(curves),
        "keyframe_count": keyframe_count,
        "contains_scale_curves": has_scale_curves,
        "non_finite_keyframes": non_finite,
        "loop": bool(loop),
        "play_once": bool(not loop),
        "hold_final_pose": bool(death),
        "return_to_previous_state": bool(hurt or offensive),
    }
    if death:
        result["floor_grounding"] = {
            "baked": bool(action.get("dsb_floor_grounded", False)),
            "floor_z": float(action.get("dsb_ground_floor_z", 0.0)),
            "ground_sink_m": float(action.get("dsb_ground_sink_m", 0.0)),
            "sample_count": int(action.get("dsb_ground_sample_count", 0)),
            "grounded_frame_count": int(
                action.get("dsb_grounded_frame_count", 0)
            ),
            "maximum_correction_m": float(
                action.get("dsb_ground_max_correction_m", 0.0)
            ),
            "minimum_z": float(action.get("dsb_ground_minimum_z", 0.0)),
            "signed_alignment": True,
            "maximum_upward_correction_m": float(
                action.get("dsb_ground_max_upward_correction_m", 0.0)
            ),
            "maximum_downward_correction_m": float(
                action.get("dsb_ground_max_downward_correction_m", 0.0)
            ),
            "terminal_contact_baked": bool(
                action.get("dsb_terminal_contact_baked", False)
            ),
            "terminal_contact_frame": int(
                action.get("dsb_terminal_contact_frame", 0)
            ),
            "terminal_reference_height_m": float(
                action.get("dsb_terminal_reference_height_m", 0.0)
            ),
            "terminal_height_m": float(
                action.get("dsb_terminal_height_m", 0.0)
            ),
            "terminal_height_ratio": float(
                action.get("dsb_terminal_height_ratio", 1.0)
            ),
            "maximum_terminal_height_ratio": float(
                action.get(
                    "dsb_terminal_max_height_ratio",
                    DEATH_TERMINAL_MAX_HEIGHT_RATIO,
                )
            ),
            "ground_carrier_role": str(
                action.get("dsb_ground_carrier_role", "")
            ),
            "ground_carrier_bone": str(
                action.get("dsb_ground_carrier_bone", "")
            ),
            "terminal_torso_minimum_z": float(
                action.get("dsb_terminal_torso_minimum_z", 0.0)
            ),
            "terminal_torso_height_m": float(
                action.get("dsb_terminal_torso_height_m", 0.0)
            ),
            "terminal_torso_height_ratio": float(
                action.get("dsb_terminal_torso_height_ratio", 1.0)
            ),
            "maximum_terminal_torso_height_ratio": float(
                action.get(
                    "dsb_terminal_max_torso_height_ratio",
                    DEATH_TERMINAL_MAX_TORSO_HEIGHT_RATIO,
                )
            ),
            "torso_contact_tolerance_m": float(
                action.get("dsb_torso_contact_tolerance_m", 0.0)
            ),
            "torso_contact_regions": torso_contact_regions,
            "maximum_torso_safety_lift_m": float(
                action.get("dsb_ground_max_torso_safety_lift_m", 0.0)
            ),
        }
    guard_variant = str(action.get("dsb_guard_variant", ""))
    if guard_variant:
        try:
            presented_regions = json.loads(str(action.get("dsb_presented_regions_json", "[]")))
        except (TypeError, json.JSONDecodeError):
            presented_regions = []
        markers = {marker.name: int(marker.frame) for marker in action.pose_markers}
        guard_frame = markers.get("Guard_Active", action.get("dsb_guard_active_frame"))
        result.update({
            "guard_variant": guard_variant,
            "guard_active_frame": int(guard_frame) if guard_frame is not None else None,
            "guard_active_time_seconds": (
                round((float(guard_frame) - start) / max(fps, 0.001), 6)
                if guard_frame is not None else None
            ),
            "markers": markers,
            "presented_regions": presented_regions,
            "interruptible": bool(action.get("dsb_interruptible", True)),
            "root_motion_policy": str(action.get("dsb_root_motion_policy", "IN_PLACE")),
            "guard_validation_status": str(action.get("dsb_guard_validation_status", "NOT_VALIDATED")),
        })
    if offensive:
        result["offensive_action"] = offensive_actions.validated_action_metadata(
            action,
            clip_duration_seconds=result["duration_seconds"],
            require_approved=True,
        )
        if action.get(offensive_motion.MOTION_RECIPE_PROPERTY):
            result["offensive_targeting"] = (
                offensive_motion_studio.validated_targeting_record(
                    bpy.context,
                    action,
                    require_current=True,
                )
            )
    return result


def validate_death_floor_action(
    context,
    action,
    armature,
    meshes,
    *,
    fallback_ground_sink,
):
    """Sample an approved death Action against the same Z=0 preview floor."""
    sink = float(action.get("dsb_ground_sink_m", fallback_ground_sink))
    floor_z = float(action.get("dsb_ground_floor_z", 0.0))
    allowed_minimum = floor_z - sink
    tolerance = 0.001
    errors = []
    worst_minimum = float("inf")
    worst_frame = None
    start_height = None
    final_minimum = None
    final_height = None
    final_torso = None
    start, end = action_frame_bounds(action)
    start_frame = int(math.floor(start))
    final_frame = int(math.ceil(end))

    if armature.animation_data is None:
        armature.animation_data_create()
    animation_data = armature.animation_data
    previous_action = animation_data.action
    previous_frame = context.scene.frame_current
    track_states = [
        (
            track,
            bool(track.mute),
            bool(getattr(track, "is_solo", False)),
        )
        for track in animation_data.nla_tracks
    ]
    try:
        mapping = map_bones(armature, context.scene.daf_settings)
        for track, _mute, _solo in track_states:
            track.mute = True
            try:
                track.is_solo = False
            except (AttributeError, RuntimeError):
                pass
        animation_data.action = action
        for frame in range(start_frame, final_frame + 1):
            context.scene.frame_set(frame)
            context.view_layer.update()
            minimum, maximum = world_bounds(context, meshes)
            if float(minimum.z) < worst_minimum:
                worst_minimum = float(minimum.z)
                worst_frame = frame
            if frame == start_frame:
                start_height = float(maximum.z - minimum.z)
            if frame == final_frame:
                final_minimum = float(minimum.z)
                final_height = float(maximum.z - minimum.z)
                final_torso = torso_contact_bounds(context, meshes, mapping)
    finally:
        animation_data.action = previous_action
        for track, mute, solo in track_states:
            track.mute = mute
            try:
                track.is_solo = solo
            except (AttributeError, RuntimeError):
                pass
        context.scene.frame_set(previous_frame)

    if worst_minimum < allowed_minimum - tolerance:
        errors.append(
            f"{action.name} reaches {worst_minimum:.4f} m at frame "
            f"{worst_frame}; floor policy allows {allowed_minimum:.4f} m."
        )
    if not bool(action.get("dsb_terminal_contact_baked", False)):
        errors.append(
            f"{action.name} has no baked terminal full-body ground-contact pass."
        )
    if str(action.get("dsb_ground_carrier_bone", "")) != str(
        mapping.get("root", "")
    ):
        errors.append(
            f"{action.name} is not grounded through the canonical root bone."
        )
    if final_minimum is None or final_height is None:
        errors.append(f"{action.name} has no measurable terminal pose.")
        final_height_ratio = float("inf")
    else:
        reference_height = float(
            action.get(
                "dsb_terminal_reference_height_m",
                start_height if start_height is not None else 0.0,
            )
        )
        reference_height = max(reference_height, 1.0e-6)
        final_height_ratio = final_height / reference_height
        maximum_ratio = float(
            action.get(
                "dsb_terminal_max_height_ratio",
                DEATH_TERMINAL_MAX_HEIGHT_RATIO,
            )
        )
        if abs(final_minimum - allowed_minimum) > tolerance:
            errors.append(
                f"{action.name} ends at {final_minimum:.4f} m instead of "
                f"finishing flush at {allowed_minimum:.4f} m."
            )
        if final_height_ratio > maximum_ratio + 1.0e-4:
            errors.append(
                f"{action.name} terminal body height ratio is "
                f"{final_height_ratio:.3f}; maximum is {maximum_ratio:.3f}."
            )
    torso_regions = {}
    final_torso_height = None
    final_torso_height_ratio = float("inf")
    if final_torso is None:
        errors.append(f"{action.name} has no measurable terminal torso contact.")
    else:
        if final_torso["missing_regions"]:
            errors.append(
                f"{action.name} cannot verify full torso contact; missing "
                + ", ".join(final_torso["missing_regions"])
                + " weighted regions."
            )
        final_torso_height = float(
            final_torso["maximum"].z - final_torso["minimum"].z
        )
        reference_height = max(
            float(
                action.get(
                    "dsb_terminal_reference_height_m",
                    start_height if start_height is not None else 0.0,
                )
            ),
            1.0e-6,
        )
        final_torso_height_ratio = final_torso_height / reference_height
        maximum_torso_ratio = float(
            action.get(
                "dsb_terminal_max_torso_height_ratio",
                DEATH_TERMINAL_MAX_TORSO_HEIGHT_RATIO,
            )
        )
        if final_torso_height_ratio > maximum_torso_ratio + 1.0e-4:
            errors.append(
                f"{action.name} terminal torso height ratio is "
                f"{final_torso_height_ratio:.3f}; maximum is "
                f"{maximum_torso_ratio:.3f}."
            )
        contact_tolerance = float(
            action.get(
                "dsb_torso_contact_tolerance_m",
                max(
                    0.02,
                    min(
                        0.08,
                        reference_height * DEATH_TORSO_CONTACT_TOLERANCE_RATIO,
                    ),
                ),
            )
        )
        torso_regions = final_torso["regions"]
        for role, record in sorted(torso_regions.items()):
            gap = float(record["minimum_z"]) - allowed_minimum
            if gap > contact_tolerance:
                errors.append(
                    f"{action.name} terminal {role} remains {gap:.4f} m "
                    "above the floor."
                )
    return {
        "status": "FAIL" if errors else "PASS",
        "action": action.name,
        "floorZ": floor_z,
        "groundSinkM": sink,
        "allowedMinimumZ": allowed_minimum,
        "minimumZ": worst_minimum,
        "worstFrame": worst_frame,
        "terminalContactBaked": bool(
            action.get("dsb_terminal_contact_baked", False)
        ),
        "terminalMinimumZ": final_minimum,
        "terminalHeightM": final_height,
        "terminalHeightRatio": final_height_ratio,
        "maximumTerminalHeightRatio": float(
            action.get(
                "dsb_terminal_max_height_ratio",
                DEATH_TERMINAL_MAX_HEIGHT_RATIO,
            )
        ),
        "groundCarrierBone": str(action.get("dsb_ground_carrier_bone", "")),
        "terminalTorsoHeightM": final_torso_height,
        "terminalTorsoHeightRatio": final_torso_height_ratio,
        "maximumTerminalTorsoHeightRatio": float(
            action.get(
                "dsb_terminal_max_torso_height_ratio",
                DEATH_TERMINAL_MAX_TORSO_HEIGHT_RATIO,
            )
        ),
        "terminalTorsoRegions": torso_regions,
        "sampleCount": int(math.ceil(end)) - int(math.floor(start)) + 1,
        "errors": errors,
    }


def sanitize_pack_filename(value):
    value = os.path.basename(value.strip())
    if value.lower().endswith('.glb'):
        value = value[:-4]
    value = re.sub(r'[^A-Za-z0-9._-]+', '_', value).strip('._-')
    return value or 'dreadstone_animpack_v001'


def incremented_pack_path(directory, filename, auto_increment):
    filename = sanitize_pack_filename(filename)
    candidate = os.path.join(directory, filename + '.glb')
    if not auto_increment or not os.path.exists(candidate):
        return candidate
    match = re.match(r'^(.*)_v(\d+)$', filename, re.IGNORECASE)
    if match:
        prefix, version = match.group(1), int(match.group(2)) + 1
    else:
        prefix, version = filename, 2
    while True:
        candidate = os.path.join(directory, f'{prefix}_v{version:03d}.glb')
        if not os.path.exists(candidate):
            return candidate
        version += 1


def glb_json(filepath):
    with open(filepath, 'rb') as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise RuntimeError('The exported GLB header is incomplete.')
        magic, version, total_length = struct.unpack('<4sII', header)
        if magic != b'glTF':
            raise RuntimeError('The exported file is not a GLB.')
        if version != 2:
            raise RuntimeError(f'Unsupported GLB version: {version}')
        document = None
        while handle.tell() < total_length:
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                break
            chunk_length, chunk_type = struct.unpack('<II', chunk_header)
            chunk = handle.read(chunk_length)
            if chunk_type == 0x4E4F534A:
                document = json.loads(chunk.decode('utf-8').rstrip('\x00 \t\r\n'))
                break
    if document is None:
        raise RuntimeError('No JSON chunk was found inside the GLB.')
    return document


def write_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write('\n')


def validate_pack_file(glb_path, expected_names):
    document = glb_json(glb_path)
    animation_names = [a.get('name', '') for a in document.get('animations', [])]
    node_names = [n.get('name', '') for n in document.get('nodes', [])]
    expected_set, actual_set = set(expected_names), set(animation_names)
    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    duplicates = sorted({name for name in animation_names if animation_names.count(name) > 1})
    preview_floor_found = PREVIEW_FLOOR_NAME in node_names
    meshes = len(document.get('meshes', []))
    skins = len(document.get('skins', []))
    file_size = os.path.getsize(glb_path)
    passed = (
        file_size > 0 and meshes >= 1 and skins >= 1
        and not preview_floor_found and not missing and not unexpected
        and not duplicates and len(animation_names) == len(expected_names)
    )
    return {
        'status': 'PASS' if passed else 'FAIL',
        'glb_path': glb_path,
        'file_size_bytes': file_size,
        'mesh_count': meshes,
        'skin_count': skins,
        'animation_count': len(animation_names),
        'expected_animation_names': list(expected_names),
        'exported_animation_names': animation_names,
        'missing_animations': missing,
        'unexpected_animations': unexpected,
        'duplicate_animation_names': duplicates,
        'preview_floor_exported': preview_floor_found,
        'node_count': len(node_names),
        'generator': document.get('asset', {}).get('generator'),
    }


def exporter_property_names():
    try:
        rna = bpy.ops.export_scene.gltf.get_rna_type()
    except Exception as exc:
        raise RuntimeError("Blender's built-in glTF 2.0 exporter is unavailable.") from exc
    return {prop.identifier for prop in rna.properties if prop.identifier != 'rna_type'}


def exporter_enum_supports(property_name, value):
    try:
        prop = bpy.ops.export_scene.gltf.get_rna_type().properties[property_name]
        return value in {item.identifier for item in prop.enum_items}
    except Exception:
        return False


def select_pack_character(
    context,
    source_root,
    *,
    objects=None,
    include_hidden=False,
):
    bpy.ops.object.select_all(action='DESELECT')
    selected = []
    candidates = (
        set(objects)
        if objects is not None
        else {source_root} | descendants(source_root)
    )
    for obj in candidates:
        if obj.name == PREVIEW_FLOOR_NAME or obj.type not in {'EMPTY', 'ARMATURE', 'MESH'}:
            continue
        if obj.hide_get() and not include_hidden:
            continue
        obj.select_set(True)
        selected.append(obj)
    if not selected:
        raise RuntimeError('No character objects were selected for export.')
    context.view_layer.objects.active = (
        source_root if source_root in selected else selected[0]
    )
    return selected


def resolve_pack_source(context):
    """Resolve a selected character without requiring a resize wrapper."""

    armature = None
    try:
        from . import damage_authoring
        state = damage_authoring._load_state()
        armature = bpy.data.objects.get(state.get("source_armature_name", ""))
    except Exception:
        armature = None

    if armature is None or armature.type != 'ARMATURE':
        armature = find_armature(context)

    wrapper = None
    current = armature
    while current is not None:
        if current.get("dsb_safe_size_wrapper", False):
            wrapper = current
            break
        current = current.parent

    if wrapper is not None:
        export_objects = {
            obj for obj in ({wrapper} | descendants(wrapper))
            if obj.name != PREVIEW_FLOOR_NAME
            and obj.type in {'EMPTY', 'ARMATURE', 'MESH'}
        }
        source_root = wrapper
    else:
        export_objects = character_objects_for_armature(context, armature)
        source_root = armature

    if armature not in export_objects:
        export_objects.add(armature)
    if not any(obj.type == 'MESH' for obj in export_objects):
        raise RuntimeError(
            "Could not find a skinned character mesh for the selected armature."
        )

    return {
        "armature": armature,
        "source_root": source_root,
        "wrapper": wrapper,
        "objects": export_objects,
    }


def pack_character_metadata(context, source):
    wrapper = source["wrapper"]
    armature = source["armature"]
    meshes = [obj for obj in source["objects"] if obj.type == 'MESH']
    visible_height = None
    if meshes:
        minimum, maximum = world_bounds(context, meshes)
        visible_height = float(maximum.z - minimum.z)
    return {
        "sizing_mode": "SAFE_WRAPPER" if wrapper is not None else "NATIVE_RIG",
        "source_root_name": source["source_root"].name,
        "armature_name": armature.name,
        "wrapper_name": wrapper.name if wrapper is not None else None,
        "wrapper_location": list(wrapper.location) if wrapper is not None else None,
        "wrapper_scale": list(wrapper.scale) if wrapper is not None else None,
        "target_height_m": (
            wrapper.get('dsb_target_height_m') if wrapper is not None else None
        ),
        "original_height_m": (
            wrapper.get('dsb_original_height_m') if wrapper is not None else None
        ),
        "visible_height_m": visible_height,
    }


def build_temporary_export_tracks(armature, actions):
    if armature.animation_data is None:
        armature.animation_data_create()
    data = armature.animation_data
    previous_action = data.action
    previous_states = []
    for track in data.nla_tracks:
        previous_states.append((track, bool(track.mute), bool(getattr(track, 'is_solo', False))))
        track.mute = True
        try:
            track.is_solo = False
        except Exception:
            pass
    data.action = None
    temporary = []
    for action in actions:
        start, end = action_frame_bounds(action)
        track = data.nla_tracks.new()
        track.name = action.name
        track.mute = False
        strip = track.strips.new(action.name, int(math.floor(start)), action)
        strip.name = action.name
        try:
            strip.action_frame_start = start
            strip.action_frame_end = end
            strip.frame_start = start
            strip.frame_end = end
        except Exception:
            pass
        temporary.append(track)
    return previous_action, previous_states, temporary


def restore_export_tracks(armature, previous_action, previous_states, temporary):
    data = armature.animation_data
    if data is None:
        return
    for track in list(temporary):
        try:
            data.nla_tracks.remove(track)
        except Exception:
            pass
    for track, mute, solo in previous_states:
        try:
            track.mute = mute
            track.is_solo = solo
        except Exception:
            pass
    try:
        data.action = previous_action
    except Exception:
        pass


def configure_gltf_action_filter(actions):
    """Install a scoped exporter action allow-list and return a cleanup callback."""

    try:
        from io_scene_gltf2 import GLTF2_filter_action
    except Exception:
        return None
    scene = bpy.data.scenes[0]
    existed = hasattr(scene, "gltf_action_filter")
    previous = []
    previous_active = 0
    if existed:
        previous = [(item.action, bool(item.keep)) for item in scene.gltf_action_filter]
        previous_active = int(getattr(scene, "gltf_action_filter_active", 0))
        scene.gltf_action_filter.clear()
    else:
        bpy.types.Scene.gltf_action_filter = bpy.props.CollectionProperty(type=GLTF2_filter_action)
        bpy.types.Scene.gltf_action_filter_active = bpy.props.IntProperty()
    allowed = set(actions)
    for action in bpy.data.actions:
        item = scene.gltf_action_filter.add()
        item.action = action
        item.keep = action in allowed

    def cleanup():
        try:
            scene.gltf_action_filter.clear()
            if existed:
                for action, keep in previous:
                    if action is None or action.name not in bpy.data.actions:
                        continue
                    item = scene.gltf_action_filter.add()
                    item.action = action
                    item.keep = keep
                scene.gltf_action_filter_active = previous_active
            else:
                del bpy.types.Scene.gltf_action_filter
                del bpy.types.Scene.gltf_action_filter_active
        except Exception:
            pass

    return cleanup


def export_approved_glb(
    context,
    filepath,
    actions,
    force_sampling,
    *,
    source=None,
):
    source = source or resolve_pack_source(context)
    armature = source["armature"]
    source_root = source["source_root"]
    export_objects = set(source["objects"])
    selected_before = list(context.selected_objects)
    active_before = context.view_layer.objects.active
    frame_before = context.scene.frame_current
    start_before = context.scene.frame_start
    end_before = context.scene.frame_end
    floor = bpy.data.objects.get(PREVIEW_FLOOR_NAME)
    visibility_before = {
        obj: (bool(obj.hide_viewport), bool(obj.hide_render), bool(obj.hide_get()))
        for obj in export_objects
    }
    floor_state = None
    if floor is not None:
        floor_state = (bool(floor.hide_viewport), bool(floor.hide_render), bool(floor.hide_get()))
        floor.hide_viewport = True
        floor.hide_render = True
        floor.hide_set(True)
        floor.select_set(False)
    previous_action, previous_states, temporary = None, [], []
    action_filter_cleanup = None
    try:
        for obj in export_objects:
            obj.hide_viewport = False
            obj.hide_render = False
            obj.hide_set(False)
        context.view_layer.update()
        select_pack_character(
            context,
            source_root,
            objects=export_objects,
            include_hidden=True,
        )
        previous_action, previous_states, temporary = build_temporary_export_tracks(armature, actions)
        action_filter_cleanup = configure_gltf_action_filter(actions)
        context.scene.frame_start = int(math.floor(min(action_frame_bounds(a)[0] for a in actions)))
        context.scene.frame_end = int(math.ceil(max(action_frame_bounds(a)[1] for a in actions)))
        supported = exporter_property_names()
        kwargs = {'filepath': filepath}
        optional = {
            'export_format': 'GLB',
            'use_selection': True,
            'export_animations': True,
            'export_force_sampling': bool(force_sampling),
            'export_current_frame': False,
        }
        for key, value in optional.items():
            if key in supported:
                kwargs[key] = value
        if (
            action_filter_cleanup is not None
            and 'export_animation_mode' in supported
            and exporter_enum_supports('export_animation_mode', 'ACTIONS')
        ):
            kwargs['export_animation_mode'] = 'ACTIONS'
            if 'export_action_filter' in supported:
                kwargs['export_action_filter'] = True
        elif 'export_animation_mode' in supported and exporter_enum_supports('export_animation_mode', 'NLA_TRACKS'):
            kwargs['export_animation_mode'] = 'NLA_TRACKS'
        elif 'export_nla_strips' in supported:
            kwargs['export_nla_strips'] = True
        else:
            raise RuntimeError('The glTF exporter does not expose NLA-track animation export.')
        result = bpy.ops.export_scene.gltf(**kwargs)
        if 'FINISHED' not in result:
            raise RuntimeError('The glTF exporter did not finish successfully.')
    finally:
        if action_filter_cleanup is not None:
            action_filter_cleanup()
        restore_export_tracks(armature, previous_action, previous_states, temporary)
        for obj, (hide_viewport, hide_render, hidden) in visibility_before.items():
            if obj.name not in bpy.data.objects:
                continue
            obj.hide_viewport = hide_viewport
            obj.hide_render = hide_render
            obj.hide_set(hidden)
        if floor is not None and floor_state is not None:
            floor.hide_viewport, floor.hide_render = floor_state[0], floor_state[1]
            floor.hide_set(floor_state[2])
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_before:
            if obj and obj.name in context.scene.objects:
                try:
                    obj.select_set(True)
                except Exception:
                    pass
        if active_before and active_before.name in context.scene.objects:
            context.view_layer.objects.active = active_before
        context.scene.frame_start, context.scene.frame_end = start_before, end_before
        context.scene.frame_set(frame_before)


class DAF_OT_build_approved_pack(Operator):
    bl_idname = 'daf.build_approved_pack'
    bl_label = 'Build Approved Animation Pack'
    bl_description = 'Export only approved Actions to one GLB and write manifest/validation files'
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.daf_settings
        try:
            actions = approved_actions()
            if not actions:
                raise RuntimeError('No approved Actions found. Approve at least one Draft first.')
            source = resolve_pack_source(context)
            armature = source["armature"]
            rig_contract = sbf_handoff.require_canonical_yplus(
                armature,
                label="Animation pack export",
            )
            # Approved Actions can predate the Skin & Bones Y+ metadata
            # contract even when their curves were authored and visually
            # verified on this exact canonical rig. Refresh provenance from
            # the selected rig before compatibility validation. This mutates
            # Action metadata only; keyframes, timing, and poses are untouched.
            for action in actions:
                kind = str(action.get("dsb_approved_kind", "")) or infer_approved_kind(
                    action.name
                )
                animation_library.mark_approved(
                    action,
                    armature,
                    settings,
                    kind,
                )
            compatibility = [
                animation_library.compatibility_report(action, armature)
                for action in actions
            ]
            compatibility_errors = [
                error
                for report in compatibility
                for error in report["errors"]
            ]
            if compatibility_errors:
                raise RuntimeError(
                    "Animation pack contains a noncanonical clip: "
                    + "; ".join(compatibility_errors[:4])
                )
            output_dir = bpy.path.abspath(settings.pack_output_directory)
            if not output_dir:
                raise RuntimeError('Choose a Pack Output Folder.')
            os.makedirs(output_dir, exist_ok=True)
            glb_path = incremented_pack_path(output_dir, settings.pack_filename, settings.pack_auto_increment)
            fps = context.scene.render.fps / max(context.scene.render.fps_base, 0.001)
            metadata = [action_pack_metadata(action, fps) for action in actions]
            invalid = [item['name'] for item in metadata if item['non_finite_keyframes'] > 0]
            if invalid:
                raise RuntimeError('Non-finite keyframes found in: ' + ', '.join(invalid))
            offensive_metadata = [
                item for item in metadata if item.get("offensive_action") is not None
            ]
            offensive_ids = [
                item["offensive_action"]["combatActionId"]
                for item in offensive_metadata
            ]
            duplicate_offensive_ids = sorted({
                value for value in offensive_ids if offensive_ids.count(value) > 1
            })
            if duplicate_offensive_ids:
                raise RuntimeError(
                    "Animation pack contains ambiguous combat Action IDs: "
                    + ", ".join(duplicate_offensive_ids)
                    + "."
                )
            guard_actions = [action for action in actions if action.get("dsb_guard_variant")]
            guard_validation = []
            if guard_actions:
                mapping = map_bones(armature, settings)
                guard_validation = [
                    validate_mace_guard_action(context, action, armature, mapping)
                    for action in guard_actions
                ]
                invalid_guards = [record for record in guard_validation if record["status"] != "PASS"]
                if invalid_guards:
                    raise RuntimeError(
                        "Mace head-guard validation failed: "
                        + "; ".join(
                            message for record in invalid_guards for message in record["errors"][:2]
                        )
                    )
            death_actions = [
                action for action in actions
                if str(action.get("dsb_approved_kind", "")) == "DEATH"
                or any(
                    token in action.name.lower()
                    for token in ("death", "collapse", "faceplant")
                )
            ]
            death_floor_validation = []
            if death_actions:
                ground_meshes = [
                    obj for obj in source["objects"]
                    if obj.type == 'MESH'
                    and not bool(obj.get("dsb_preview_only", False))
                ]
                if not ground_meshes:
                    raise RuntimeError(
                        "Death floor validation found no character meshes."
                    )
                death_floor_validation = [
                    validate_death_floor_action(
                        context,
                        action,
                        armature,
                        ground_meshes,
                        fallback_ground_sink=settings.ground_sink,
                    )
                    for action in death_actions
                ]
                invalid_deaths = [
                    record for record in death_floor_validation
                    if record["status"] != "PASS"
                ]
                if invalid_deaths:
                    raise RuntimeError(
                        "Death floor validation failed: "
                        + "; ".join(
                            message
                            for record in invalid_deaths
                            for message in record["errors"][:1]
                        )
                        + " Regenerate the Death Draft or correct its root/torso "
                        "contact before approval."
                    )
            export_approved_glb(
                context,
                glb_path,
                actions,
                settings.pack_force_sampling,
                source=source,
            )
            validation = validate_pack_file(glb_path, [action.name for action in actions])
            stem = os.path.splitext(glb_path)[0]
            manifest_path = stem + '.json'
            validation_path = stem + '_validation.json'
            manifest = {
                'schema': 'dreadstone.animation_pack.v1',
                'asset': os.path.basename(glb_path),
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'blender_version': bpy.app.version_string,
                'source_blend': bpy.data.filepath or None,
                'approved_animation_count': len(actions),
                'fps': fps,
                'character': pack_character_metadata(context, source),
                'canonical_rig': {
                    'rig_version': rig_contract['rigVersion'],
                    'forward_axis': '+Y',
                    'up_axis': '+Z',
                    'root_motion_bone': rig_contract['rootBone'],
                    'orientation_revision': rig_contract['orientationRevision'],
                    'rig_contract_version': rig_contract['rigContractVersion'],
                    'unit_scale_meters': rig_contract['unitScaleMeters'],
                },
                'anatomy': anatomy_persistence.export_metadata(
                    armature,
                    infer_legacy=False,
                ),
                'animations': metadata,
                'offensive_action_schema': offensive_actions.OFFENSIVE_ACTION_SCHEMA,
                'offensive_targeting_schema': offensive_motion.TARGETING_SCHEMA,
                'approved_offensive_action_count': len(offensive_metadata),
                'offensive_targeting': [
                    {
                        'actionName': item['name'],
                        **item['offensive_targeting'],
                    }
                    for item in offensive_metadata
                    if item.get('offensive_targeting') is not None
                ],
                'mace_head_guard_validation': guard_validation,
                'death_floor_validation': death_floor_validation,
                'validation_report': os.path.basename(validation_path),
            }
            write_json(manifest_path, manifest)
            write_json(validation_path, validation)
            settings.last_pack_path = glb_path
            if validation['status'] == 'PASS':
                self.report({'INFO'}, f"Pack built and validated: {os.path.basename(glb_path)} ({len(actions)} animations).")
            else:
                self.report({'WARNING'}, f"Pack exported but validation failed. Read {os.path.basename(validation_path)}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_validate_last_pack(Operator):
    bl_idname = 'daf.validate_last_pack'
    bl_label = 'Validate Last Built Pack'
    bl_description = 'Re-read the last GLB and compare it with the adjacent manifest'
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.daf_settings
        try:
            glb_path = bpy.path.abspath(settings.last_pack_path)
            if not glb_path or not os.path.isfile(glb_path):
                raise RuntimeError('No valid Last Pack Path exists. Build a pack first.')
            manifest_path = os.path.splitext(glb_path)[0] + '.json'
            if os.path.isfile(manifest_path):
                with open(manifest_path, 'r', encoding='utf-8') as handle:
                    manifest = json.load(handle)
                expected = [item['name'] for item in manifest.get('animations', [])]
            else:
                expected = [action.name for action in approved_actions()]
            validation = validate_pack_file(glb_path, expected)
            validation_path = os.path.splitext(glb_path)[0] + '_validation.json'
            write_json(validation_path, validation)
            if validation['status'] == 'PASS':
                self.report({'INFO'}, f"Validation passed: {len(expected)} animations, {validation['mesh_count']} mesh(es), {validation['skin_count']} skin(s).")
            else:
                self.report({'WARNING'}, 'Validation failed. Open the validation JSON.')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

def draw_foldout(layout, settings, property_name, title):
    box = layout.box()
    row = box.row(align=True)
    is_open = bool(getattr(settings, property_name))
    row.prop(
        settings,
        property_name,
        text=title,
        icon='TRIA_DOWN' if is_open else 'TRIA_RIGHT',
        emboss=False,
    )
    return box, is_open


def draw_subfoldout(layout, settings, property_name, title):
    row = layout.row(align=True)
    is_open = bool(getattr(settings, property_name))
    row.prop(
        settings,
        property_name,
        text=title,
        icon='TRIA_DOWN' if is_open else 'TRIA_RIGHT',
        emboss=False,
    )
    return is_open


def configure_property_box(box):
    box.use_property_split = True
    box.use_property_decorate = False


class DAF_PT_legacy_panel(Panel):
    bl_label = "Dreadstone Animation Forge"
    bl_idname = "DAF_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Dreadstone"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s = context.scene.daf_settings

        # Character setup ---------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_character_open",
            "Character Setup",
        )
        if opened:
            configure_property_box(box)

            adopt = box.operator(
                "daf.adopt_imported_pack",
                text="Adopt Imported Animation Pack",
                icon='IMPORT',
            )
            box.label(
                text="Use this after importing an existing Forge GLB",
                icon='INFO',
            )

            box.prop(s, "target_height")
            box.label(text="Adopt keeps current size; Safe Resize targets this value", icon='INFO')

            row = box.row(align=True)
            row.operator(
                "daf.safe_resize",
                text="Safe Resize",
                icon='EMPTY_AXIS',
            )
            row.operator(
                "daf.analyze",
                text="Analyze Rig",
                icon='ARMATURE_DATA',
            )

        # Ground preview ----------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_ground_open",
            "Ground Preview",
        )
        if opened:
            configure_property_box(box)
            box.prop(s, "preview_floor_size")
            box.prop(s, "ground_sink")

            row = box.row(align=True)
            row.operator(
                "daf.create_preview_floor",
                text="Create Floor",
                icon='MESH_PLANE',
            )
            row.operator(
                "daf.align_feet_to_floor",
                text="Align Pose",
                icon='SNAP_ON',
            )
            box.label(
                text="Alignment uses the displayed frame",
                icon='INFO',
            )

        # Rig mapping -------------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_rig_open",
            "Rig Mapping & Direction",
        )
        if opened:
            configure_property_box(box)
            try:
                arm = find_armature(context)
                box.prop_search(
                    s,
                    "manual_hips",
                    arm.data,
                    "bones",
                    text="Pelvis / Hips",
                )
                box.prop_search(
                    s,
                    "manual_spine",
                    arm.data,
                    "bones",
                    text="Lowest Spine",
                )
                box.prop_search(
                    s,
                    "manual_chest",
                    arm.data,
                    "bones",
                    text="Upper Spine / Chest",
                )
            except Exception:
                box.label(
                    text="Select the character for bone pickers",
                    icon='INFO',
                )

            box.prop(s, "facing")
            row = box.row(align=True)
            row.prop(s, "invert_knees")
            row.prop(s, "invert_elbows")

        # Damage readiness -------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_damage_readiness_open",
            "Source Damage Readiness",
        )
        if opened:
            configure_property_box(box)
            box.prop(s, "damage_readiness_output_directory")
            if not s.damage_readiness_output_directory:
                box.label(text="Choose a project folder; no C-drive fallback", icon='ERROR')
            elif not bpy.data.filepath and s.damage_readiness_output_directory.startswith("//"):
                box.label(text="Unsaved .blend: choose an explicit folder", icon='ERROR')
            box.operator(
                "daf.analyze_damage_readiness",
                text="Analyze Source Damage Readiness",
                icon='VIEWZOOM',
            )
            box.operator(
                "daf.repair_source_readiness_contract",
                text="Repair Source Readiness Contract",
                icon='FILE_REFRESH',
            )

            results = box.box()
            results.label(text="Source Readiness Results", icon='INFO')
            results.label(text="Contract: " + s.source_readiness_contract_status)
            results.label(text="Overall: " + s.damage_readiness_overall_status)
            results.label(text="Head–Neck: " + s.damage_readiness_head_neck_status)
            results.label(text="Left Elbow: " + s.damage_readiness_left_elbow_status)
            results.label(text="Right Elbow: " + s.damage_readiness_right_elbow_status)
            results.label(text="Lower Spine: " + s.damage_readiness_lower_spine_status)

            box.prop(s, "damage_readiness_preview_seam")
            row = box.row(align=True)
            row.operator(
                "daf.preview_damage_seam",
                text="Preview Candidate Seam",
                icon='HIDE_OFF',
            )
            row.operator(
                "daf.clear_damage_seam_preview",
                text="Clear Preview",
                icon='X',
            )

            row = box.row(align=True)
            row.operator(
                "daf.open_damage_report_folder",
                text="Open Report Folder",
                icon='FILE_FOLDER',
            )
            row.operator(
                "daf.open_damage_markdown_report",
                text="Open Markdown",
                icon='TEXT',
            )
            if s.last_damage_readiness_json_path:
                box.label(
                    text="JSON: " + os.path.basename(s.last_damage_readiness_json_path),
                    icon='FILE_TICK',
                )
            box.label(text="Source geometry and weights are never edited", icon='LOCKED')
            box.label(text="Stable source identity metadata is stored", icon='CHECKMARK')
            box.label(text="Reports are fingerprinted for the v3.8 handoff", icon='CHECKMARK')

        # Damage segment and stump authoring -------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_damage_authoring_open",
            "Damage Segment & Stump Authoring v3.9",
        )
        if opened:
            configure_property_box(box)
            box.prop(s, "damage_authoring_report_path")
            row = box.row(align=True)
            row.operator(
                "daf.load_damage_readiness_handoff",
                text="Load READY Handoff",
                icon='IMPORT',
            )
            row.operator(
                "daf.build_damage_authoring_asset",
                text="Build Authoring Asset",
                icon='MOD_BOOLEAN',
            )
            box.operator(
                "daf.clear_damage_authoring_asset",
                text="Clear Generated Asset / Restore Source",
                icon='TRASH',
            )

            status = box.box()
            status.label(text="Status: " + s.damage_authoring_status, icon='INFO')
            status.label(text="Source Readiness: " + s.source_readiness_contract_status)
            status.label(text="Authoring Validation: " + s.last_damage_authoring_validation)
            status.label(text="Export Validation: " + s.last_damage_export_validation)

            box.prop(s, "damage_authoring_seam")
            row = box.row(align=True)
            row.operator(
                "daf.preview_damage_intact",
                text="Preview Intact",
                icon='HIDE_OFF',
            )
            row.operator(
                "daf.preview_damage_detached",
                text="Preview Detached",
                icon='UNLINKED',
            )
            box.operator(
                "daf.restore_imported_damage_intact_preview",
                text="Restore Reimported GLB Intact Preview",
                icon='HIDE_OFF',
            )
            box.label(text="Use after importing the exported GLB into a clean scene", icon='INFO')
            box.prop(s, "damage_authoring_gap_tolerance")
            box.operator(
                "daf.validate_damage_authoring_asset",
                text="Validate Complete Damage Asset",
                icon='CHECKMARK',
            )

            export = box.box()
            export.label(text="Damage Export", icon='EXPORT')
            export.prop(s, "damage_authoring_output_directory")
            if not s.damage_authoring_output_directory and not bpy.data.filepath:
                export.label(text="Save the .blend or choose an explicit project folder", icon='ERROR')
            export.prop(s, "damage_authoring_filename")
            export.operator(
                "daf.export_damage_asset",
                text="Export Damage GLB + Manifest",
                icon='EXPORT',
            )
            export.operator(
                "daf.open_damage_export_folder",
                text="Open Damage Export Folder",
                icon='FILE_FOLDER',
            )
            if s.last_damage_glb_path:
                export.label(text="GLB: " + os.path.basename(s.last_damage_glb_path), icon='FILE_TICK')
            if s.last_damage_manifest_path:
                export.label(text="Manifest: " + os.path.basename(s.last_damage_manifest_path), icon='TEXT')

            box.label(text="Source geometry and weights are never edited", icon='LOCKED')
            box.label(text="Virtual GLB seam splits remain non-destructive", icon='CHECKMARK')

        # Damage deformation authoring ------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_deformation_authoring_open",
            "Trauma Field Authoring v5.4.1",
        )
        if opened:
            configure_property_box(box)
            deformation_authoring.draw_panel(box, context, s)

        # Arm and hand polish ----------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_pose_open",
            "Arm & Hand Pose Polish",
        )
        if opened:
            configure_property_box(box)
            box.prop(s, "pose_polish_enabled")

            if draw_subfoldout(
                box,
                s,
                "ui_pose_left_open",
                "Left Arm / Hand",
            ):
                left = box.column(align=True)
                left.prop(s, "left_upper_arm_forward", slider=True)
                left.prop(s, "left_upper_arm_roll", slider=True)
                left.prop(s, "left_elbow_flex", slider=True)
                left.prop(s, "left_forearm_twist", slider=True)
                left.prop(s, "left_wrist_flex", slider=True)
                left.prop(s, "left_wrist_side", slider=True)
                left.prop(s, "left_wrist_roll", slider=True)

            if draw_subfoldout(
                box,
                s,
                "ui_pose_right_open",
                "Right Arm / Hand",
            ):
                right = box.column(align=True)
                right.prop(s, "right_upper_arm_forward", slider=True)
                right.prop(s, "right_upper_arm_roll", slider=True)
                right.prop(s, "right_elbow_flex", slider=True)
                right.prop(s, "right_forearm_twist", slider=True)
                right.prop(s, "right_wrist_flex", slider=True)
                right.prop(s, "right_wrist_side", slider=True)
                right.prop(s, "right_wrist_roll", slider=True)

            box.operator(
                "daf.reset_pose_polish",
                text="Zero Arm & Hand Polish",
                icon='LOOP_BACK',
            )
            box.label(
                text="Rotation only — location and scale stay untouched",
                icon='INFO',
            )

        # Walk --------------------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_walk_open",
            "Walk Draft",
        )
        if opened:
            configure_property_box(box)
            box.prop(s, "walk_style")
            box.prop(s, "walk_frames")
            box.prop(s, "stride", slider=True)
            box.prop(s, "knee", slider=True)
            box.prop(s, "step_lift", slider=True)
            box.prop(s, "arm_swing", slider=True)
            box.prop(s, "walk_arm_tuck", slider=True)

            if draw_subfoldout(
                box,
                s,
                "ui_walk_advanced_open",
                "Advanced Walk Controls",
            ):
                advanced = box.column(align=True)
                advanced.prop(s, "foot_roll", slider=True)
                advanced.prop(s, "elbow_bend", slider=True)
                advanced.prop(s, "hip_bob", slider=True)
                advanced.prop(s, "hip_sway", slider=True)
                advanced.prop(s, "pelvis_twist", slider=True)
                advanced.prop(s, "chest_counter_twist", slider=True)
                advanced.prop(s, "torso_lean", slider=True)
                advanced.prop(s, "shoulder_sway", slider=True)
                advanced.prop(s, "head_stability", slider=True)
                advanced.prop(s, "walk_asymmetry", slider=True)

            box.operator(
                "daf.walk",
                text="Generate / Refresh Walk Draft",
                icon='ACTION',
            )
            approve = box.operator(
                "daf.approve_draft",
                text="Version / Approve Walk Draft",
                icon='FAKE_USER_ON',
            )
            approve.kind = "WALK"

        # Death -------------------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_death_open",
            "Death / Collapse Draft",
        )
        if opened:
            configure_property_box(box)
            box.prop(s, "collapse_style")
            box.prop(
                s,
                "death_instant_seconds"
                if s.collapse_style == "INSTANT_LIMP"
                else "collapse_seconds",
            )
            box.prop(s, "death_pain_side")
            box.prop(s, "death_lead_knee")
            if s.collapse_style != "INSTANT_LIMP":
                box.prop(s, "death_brace_side")
            box.prop(s, "death_arm_tuck", slider=True)
            if s.collapse_style != "INSTANT_LIMP":
                box.prop(s, "death_wiggle", slider=True)

            if draw_subfoldout(
                box,
                s,
                "ui_death_advanced_open",
                "Advanced Collapse Controls",
            ):
                advanced = box.column(align=True)
                advanced.prop(s, "death_knee_strength", slider=True)
                advanced.prop(s, "death_curl_strength", slider=True)
                advanced.prop(s, "death_drop_strength", slider=True)
                advanced.prop(s, "death_travel_strength", slider=True)
                advanced.prop(s, "death_twist_strength", slider=True)
                advanced.prop(s, "death_head_lag", slider=True)
                advanced.prop(s, "death_fall_bias", slider=True)
                advanced.prop(s, "death_settle", slider=True)
                advanced.prop(s, "death_hold_frames")

            box.operator(
                "daf.collapse",
                text="Generate / Refresh Death Draft",
                icon='POSE_HLT',
            )
            approve = box.operator(
                "daf.approve_draft",
                text="Version / Approve Death Draft",
                icon='FAKE_USER_ON',
            )
            approve.kind = "DEATH"

        # Hurt --------------------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_hurt_open",
            "Flank Hurt Drafts",
        )
        if opened:
            configure_property_box(box)
            box.prop(s, "hurt_seconds")
            box.prop(s, "hurt_severity", slider=True)
            box.prop(s, "hurt_hand_to_flank", slider=True)
            box.prop(s, "hurt_torso_bend", slider=True)

            if draw_subfoldout(
                box,
                s,
                "ui_hurt_advanced_open",
                "Advanced Hurt Controls",
            ):
                advanced = box.column(align=True)
                advanced.prop(s, "hurt_hand_reach", slider=True)
                advanced.prop(s, "hurt_twist", slider=True)
                advanced.prop(s, "hurt_knee_dip", slider=True)
                advanced.prop(s, "hurt_stagger", slider=True)
                advanced.prop(s, "hurt_head_recoil", slider=True)
                advanced.prop(s, "hurt_recovery", slider=True)

            row = box.row(align=True)
            row.operator(
                "daf.hurt_left",
                text="Refresh Left",
                icon='ACTION',
            )
            row.operator(
                "daf.hurt_right",
                text="Refresh Right",
                icon='ACTION',
            )

            row = box.row(align=True)
            approve_left = row.operator(
                "daf.approve_draft",
                text="Approve Left",
                icon='FAKE_USER_ON',
            )
            approve_left.kind = "HURT_LEFT"

            approve_right = row.operator(
                "daf.approve_draft",
                text="Approve Right",
                icon='FAKE_USER_ON',
            )
            approve_right.kind = "HURT_RIGHT"

        # Pack builder ------------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_mace_guard_open",
            "Mace Head-Guard Drafts",
        )
        if opened:
            configure_property_box(box)
            box.prop(s, "mace_guard_style")
            timing = box.box()
            timing.label(text="Timing", icon='TIME')
            timing.prop(s, "mace_guard_raise_seconds")
            timing.prop(s, "mace_guard_hold_seconds")
            timing.prop(s, "mace_guard_recovery_seconds")
            pose = box.box()
            pose.label(text="Head Coverage & Cower", icon='POSE_HLT')
            for property_name in (
                "mace_guard_arm_cover",
                "mace_guard_elbow_flex",
                "mace_guard_arm_wrap",
                "mace_guard_shoulder_hunch",
                "mace_guard_torso_curl",
                "mace_guard_head_tuck",
                "mace_guard_crouch",
                "mace_guard_asymmetry",
                "mace_guard_end_release",
            ):
                pose.prop(s, property_name, slider=True)
            box.operator(
                "daf.generate_mace_head_guards",
                text="Generate Three Mace Head-Guard Drafts",
                icon='ACTION',
            )
            box.prop(s, "mace_guard_preview_variant")
            row = box.row(align=True)
            row.operator("daf.preview_mace_guard_active", text="Preview Guard_Active", icon='PLAY')
            row.operator("daf.validate_mace_head_guards", text="Validate Mace Head-Guard Drafts", icon='CHECKMARK')
            for kind, label in (
                ("MACE_GUARD_TWO_ARM", "Approve Two-Arm"),
                ("MACE_GUARD_LEFT_ARM", "Approve Left-Arm"),
                ("MACE_GUARD_RIGHT_ARM", "Approve Right-Arm"),
            ):
                approve = box.operator("daf.approve_draft", text=label, icon='FAKE_USER_ON')
                approve.kind = kind
            box.label(text="Markers: Recognition / Covering / Guard_Active / Hold", icon='MARKER_HLT')
            box.label(text="Forearm coverage is guidance, never an export blocker", icon='INFO')
            box.label(text="Shape-key damage remains a separate preview", icon='INFO')

        # Pack builder ------------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_pack_open",
            "Approved Animation Pack",
        )
        if opened:
            configure_property_box(box)
            box.prop(s, "pack_output_directory")
            box.prop(s, "pack_filename")
            box.prop(s, "pack_auto_increment")
            box.prop(s, "pack_force_sampling")
            box.operator(
                "daf.build_approved_pack",
                text="Build Approved Animation Pack",
                icon='EXPORT',
            )
            box.operator(
                "daf.validate_last_pack",
                text="Validate Last Built Pack",
                icon='CHECKMARK',
            )
            if s.last_pack_path:
                box.label(
                    text="Last: " + os.path.basename(s.last_pack_path),
                    icon='FILE_TICK',
                )
            box.label(
                text="Approved Actions only; preview floor excluded",
                icon='INFO',
            )
            box.label(
                text="Saved Actions stay editable here; no reimport is required",
                icon='INFO',
            )
            box.label(
                text="Force Sampling bakes only the exported delivery GLB",
                icon='INFO',
            )

        # Workflow ----------------------------------------------------------
        box, opened = draw_foldout(
            layout,
            s,
            "ui_workflow_open",
            "Action Cleanup & Safety",
        )
        if opened:
            box.operator(
                "daf.approve_active_legacy",
                icon='FAKE_USER_ON',
            )
            box.operator(
                "daf.purge_unapproved_attempts",
                icon='TRASH',
            )
            warning = box.box()
            warning.alert = True
            warning.label(text="Never apply the wrapper scale")
            warning.label(text="Approved Actions are protected")
            warning.label(text="No animated bone scale")

# Always import the analyzer from this exact installed package. Blender can keep
# a stale package submodule alive across in-place add-on upgrades, which allowed
# a 3.7.2 UI to execute the legacy 3.7.0 analyzer. Removing the submodule before
# importing guarantees that the report engine and the visible add-on build match.
_DAMAGE_READINESS_MODULE_NAME = f"{__package__}.damage_readiness"
sys.modules.pop(_DAMAGE_READINESS_MODULE_NAME, None)
importlib.invalidate_caches()
damage_readiness = importlib.import_module(".damage_readiness", __package__)
DAMAGE_READINESS_CLASSES = damage_readiness.CLASSES

_DAMAGE_AUTHORING_MODULE_NAME = f"{__package__}.damage_authoring"
sys.modules.pop(_DAMAGE_AUTHORING_MODULE_NAME, None)
_ATTACHMENT_SOCKETS_MODULE_NAME = f"{__package__}.attachment_sockets"
sys.modules.pop(_ATTACHMENT_SOCKETS_MODULE_NAME, None)
importlib.invalidate_caches()
attachment_sockets = importlib.import_module(".attachment_sockets", __package__)
ATTACHMENT_SOCKET_CLASSES = attachment_sockets.CLASSES
_OFFENSIVE_MOTION_STUDIO_MODULE_NAME = f"{__package__}.offensive_motion_studio"
sys.modules.pop(_OFFENSIVE_MOTION_STUDIO_MODULE_NAME, None)
importlib.invalidate_caches()
offensive_motion_studio = importlib.import_module(".offensive_motion_studio", __package__)
OFFENSIVE_MOTION_STUDIO_CLASSES = offensive_motion_studio.CLASSES
damage_authoring = importlib.import_module(".damage_authoring", __package__)
DAMAGE_AUTHORING_CLASSES = damage_authoring.CLASSES

_TRAUMA_FIELD_MODULE_NAME = f"{__package__}.trauma_field"
sys.modules.pop(_TRAUMA_FIELD_MODULE_NAME, None)
importlib.invalidate_caches()

_DEFORMATION_AUTHORING_MODULE_NAME = f"{__package__}.deformation_authoring"
sys.modules.pop(_DEFORMATION_AUTHORING_MODULE_NAME, None)
importlib.invalidate_caches()
deformation_authoring = importlib.import_module(".deformation_authoring", __package__)
DEFORMATION_AUTHORING_CLASSES = deformation_authoring.CLASSES

_TASK_UI_MODULE_NAME = f"{__package__}.ui"
task_ui = importlib.import_module(".ui", __package__)
TASK_UI_CLASSES = task_ui.CLASSES

_VARIANT_AUTHORING_MODULE_NAME = f"{__package__}.variant_authoring"
sys.modules.pop(_VARIANT_AUTHORING_MODULE_NAME, None)
importlib.invalidate_caches()
variant_authoring = importlib.import_module(".variant_authoring", __package__)
VARIANT_AUTHORING_CLASSES = variant_authoring.CLASSES


class DAF_PT_panel(Panel):
    bl_label = "Dreadstone Animation Forge"
    bl_idname = "DAF_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Dreadstone"

    def draw(self, context):
        task_ui.panels.draw_main_panel(
            self.layout,
            context,
            context.scene.daf_settings,
            deformation_authoring.draw_panel,
        )

CLASSES = (
    DAFSettings,
    DAF_OT_create_preview_floor,
    DAF_OT_align_feet_to_floor,
    DAF_OT_adopt_imported_pack,
    DAF_OT_reset_pose_polish,
    DAF_OT_resize,
    DAF_OT_analyze_creature_anatomy,
    DAF_OT_analyze,
    DAF_OT_show_anatomy_role_mapping,
    DAF_OT_clear_anatomy_profile_override,
    DAF_OT_edit_animation_base_pose,
    DAF_OT_capture_animation_base_pose,
    DAF_OT_cancel_animation_base_pose,
    DAF_OT_clear_animation_base_pose,
    DAF_OT_idle,
    DAF_OT_walk,
    DAF_OT_collapse,
    DAF_OT_hurt_left,
    DAF_OT_hurt_right,
    DAF_OT_generate_humanoid_offensive_suite,
    DAF_OT_generate_selected_offensive_draft,
    DAF_OT_preview_offensive_draft,
    DAF_OT_reset_offensive_sliders,
    DAF_OT_validate_humanoid_offensive_suite,
    DAF_OT_generate_mace_head_guards,
    DAF_OT_preview_mace_guard_active,
    DAF_OT_validate_mace_head_guards,
    DAF_OT_approve_draft,
    DAF_OT_approve_active_legacy,
    DAF_OT_purge_unapproved_attempts,
    DAF_OT_build_approved_pack,
    DAF_OT_validate_last_pack,
    *DAMAGE_READINESS_CLASSES,
    *DAMAGE_AUTHORING_CLASSES,
    *ATTACHMENT_SOCKET_CLASSES,
    *OFFENSIVE_MOTION_STUDIO_CLASSES,
    *DEFORMATION_AUTHORING_CLASSES,
    *TASK_UI_CLASSES,
    *VARIANT_AUTHORING_CLASSES,
    DAF_PT_panel,
)

_REGISTERED_CLASS_NAMES = []


def _registered_class_named(cls):
    if bool(getattr(cls, "is_registered", False)):
        return cls
    existing = getattr(bpy.types, cls.__name__, None)
    if existing is not None and bool(getattr(existing, "is_registered", True)):
        return existing
    for base in cls.__mro__[1:]:
        try:
            candidates = base.__subclasses__()
        except (AttributeError, TypeError):
            continue
        for candidate in candidates:
            if candidate.__name__ == cls.__name__ and bool(getattr(candidate, "is_registered", False)):
                return candidate
    return None


def register():
    global _REGISTERED_CLASS_NAMES
    if hasattr(bpy.types.Scene, "daf_settings"):
        del bpy.types.Scene.daf_settings
    registered = []
    try:
        for cls in CLASSES:
            existing = _registered_class_named(cls)
            if existing is not None and existing is not cls:
                try:
                    bpy.utils.unregister_class(existing)
                except (RuntimeError, ValueError):
                    pass
            if not bool(getattr(cls, "is_registered", False)):
                bpy.utils.register_class(cls)
            registered.append(cls.__name__)
        bpy.types.Scene.daf_settings = PointerProperty(type=DAFSettings)
        _REGISTERED_CLASS_NAMES = registered
        deformation_authoring.initialize_runtime_services()
        variant_authoring.recover_state()
        offensive_motion_studio.register_handlers()
        offensive_motion_studio.recover_sessions()
    except Exception:
        offensive_motion_studio.unregister_handlers()
        if hasattr(bpy.types.Scene, "daf_settings"):
            del bpy.types.Scene.daf_settings
        for cls in reversed(CLASSES[:len(registered)]):
            existing = _registered_class_named(cls)
            if existing is not None:
                try:
                    bpy.utils.unregister_class(existing)
                except (RuntimeError, ValueError):
                    pass
        _REGISTERED_CLASS_NAMES = []
        raise


def unregister():
    global _REGISTERED_CLASS_NAMES
    try:
        offensive_motion_studio.unregister_handlers()
        deformation_authoring.shutdown_runtime_services()
    finally:
        if hasattr(bpy.types.Scene, "daf_settings"):
            del bpy.types.Scene.daf_settings
        for cls in reversed(CLASSES):
            existing = _registered_class_named(cls)
            if existing is None:
                continue
            try:
                bpy.utils.unregister_class(existing)
            except (RuntimeError, ValueError):
                pass
        _REGISTERED_CLASS_NAMES = []
if __name__=="__main__": register()
