bl_info = {
    "name": "Dreadstone Animation Forge",
    "author": "Dreadstone Black",
    "version": (3, 16, 2),
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

ALIASES = {
    "hips": [
        "hips","pelvis","hip","waist","cog","center","rootpelvis",
        "basehip","ccbasehip","bip001pelvis","bip01pelvis","jpelvis"
    ],
    "spine": [
        "spine","spine0","spine1","spine01","lowerback","abdomen",
        "torso","spinebase","ccbasewaist","ccbasespine01"
    ],
    "chest": [
        "chest","upperchest","thorax","ribcage","spine2","spine02",
        "spine3","spine03","ccbasespine02","ccbasespine03"
    ],
    "neck": ["neck","neck1","neck01","ccbasenecktwist01"],
    "head": ["head","ccbasehead"],
    "thigh_l": [
        "leftupleg","leftupperleg","leftthigh","thighl","upperlegl",
        "lthigh","thigh_l","upper_leg_l"
    ],
    "shin_l": [
        "leftleg","leftlowerleg","leftshin","shinl","lowerlegl",
        "calfl","lcalf","shin_l","lower_leg_l"
    ],
    "foot_l": ["leftfoot","footl","lfoot","foot_l"],
    "thigh_r": [
        "rightupleg","rightupperleg","rightthigh","thighr","upperlegr",
        "rthigh","thigh_r","upper_leg_r"
    ],
    "shin_r": [
        "rightleg","rightlowerleg","rightshin","shinr","lowerlegr",
        "calfr","rcalf","shin_r","lower_leg_r"
    ],
    "foot_r": ["rightfoot","footr","rfoot","foot_r"],
    "upper_arm_l": [
        "leftarm","leftupperarm","upperarml","lupperarm",
        "upper_arm_l","arm_l"
    ],
    "lower_arm_l": [
        "leftforearm","leftlowerarm","forearml","lowerarml",
        "lforearm","lower_arm_l","forearm_l"
    ],
    "shoulder_l": ["leftshoulder", "shoulderl", "lshoulder", "shoulder_l", "clavicle_l"],
    "hand_l": ["lefthand", "handl", "lhand", "hand_l", "wrist_l"],
    "upper_arm_r": [
        "rightarm","rightupperarm","upperarmr","rupperarm",
        "upper_arm_r","arm_r"
    ],
    "lower_arm_r": [
        "rightforearm","rightlowerarm","forearmr","lowerarmr",
        "rforearm","lower_arm_r","forearm_r"
    ],
    "shoulder_r": ["rightshoulder", "shoulderr", "rshoulder", "shoulder_r", "clavicle_r"],
    "hand_r": ["righthand", "handr", "rhand", "hand_r", "wrist_r"],
}

ANIMATE_ANYTHING_PROFILE = {
    "root": "root",
    "hips": "body",
    "spine": "body_top0",
    "spine_mid": "body_top1",
    "chest": "body_top2",
    "neck": "neck",
    "head": "head",
    "shoulder_l": "shoulder_left",
    "upper_arm_l": "arm_left_top",
    "lower_arm_l": "arm_left_bot",
    "hand_l": "arm_left_hand",
    "shoulder_r": "shoulder_right",
    "upper_arm_r": "arm_right_top",
    "lower_arm_r": "arm_right_bot",
    "hand_r": "arm_right_hand",
    "thigh_l": "leg_left_top",
    "shin_l": "leg_left_bot",
    "foot_l": "leg_left_foot",
    "thigh_r": "leg_right_top",
    "shin_r": "leg_right_bot",
    "foot_r": "leg_right_foot",
}

def detect_animate_anything_profile(arm):
    required = {
        "body", "body_top0", "body_top1", "body_top2",
        "leg_left_top", "leg_left_bot", "leg_left_foot",
        "leg_right_top", "leg_right_bot", "leg_right_foot",
        "arm_left_top", "arm_left_bot",
        "arm_right_top", "arm_right_bot",
        "neck", "head",
    }
    available = {bone.name for bone in arm.data.bones}
    return required.issubset(available)

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

    # Exact profile derived from the uploaded Animate Anything GLB.
    if detect_animate_anything_profile(arm):
        for role, bone_name in ANIMATE_ANYTHING_PROFILE.items():
            if arm.data.bones.get(bone_name):
                result[role] = bone_name

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

def vectors(settings):
    lookup = {
        "NEG_Y": Vector((0,-1,0)),
        "POS_Y": Vector((0,1,0)),
        "POS_X": Vector((1,0,0)),
        "NEG_X": Vector((-1,0,0)),
    }
    fwd = lookup[settings.facing]
    up = Vector((0,0,1))
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

DRAFT_ACTION_NAMES = {
    "WALK": "DSB_DRAFT_Walk",
    "DEATH": "DSB_DRAFT_Death",
    "HURT_LEFT": "DSB_DRAFT_Hurt_LEFT",
    "HURT_RIGHT": "DSB_DRAFT_Hurt_RIGHT",
    "MACE_GUARD_TWO_ARM": "DSB_DRAFT_Mace_Brace_Head_TwoArm",
    "MACE_GUARD_LEFT_ARM": "DSB_DRAFT_Mace_Brace_Head_LeftArm",
    "MACE_GUARD_RIGHT_ARM": "DSB_DRAFT_Mace_Brace_Head_RightArm",
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
    if kind == "WALK":
        return f"DSB_Walk_{settings.walk_style}"

    if kind == "DEATH":
        style_label = {
            "CHEST_HOLD": "ChestHold",
            "FACEPLANT": "Faceplant",
            "KNEES_FIRST": "KneesFirst",
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

    raise RuntimeError(f"Unknown Action kind: {kind}")


def approve_draft_action(context, kind):
    settings = context.scene.daf_settings
    draft_name = DRAFT_ACTION_NAMES[kind]
    action = bpy.data.actions.get(draft_name)

    if action is None:
        raise RuntimeError(
            f"No {draft_name} exists. Generate the draft first."
        )

    final_base = approval_base_name(settings, kind)
    final_name = next_approved_version_name(final_base)

    action.name = final_name
    action["dsb_draft"] = False
    action["dsb_approved"] = True
    action["dsb_approved_kind"] = kind
    action["dsb_approved_frame_start"] = int(context.scene.frame_start)
    action["dsb_approved_frame_end"] = int(context.scene.frame_end)
    if action.get("dsb_guard_variant"):
        action["dsb_guard_action_id"] = final_name
    action.use_fake_user = True

    try:
        armature = find_armature(context)
        if not armature.animation_data:
            armature.animation_data_create()
        armature.animation_data.action = action
    except Exception:
        pass

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
        module.request_managed_preview(context, "deformation control changed")


def _deformation_metadata_property_updated(self, context):
    module = sys.modules.get(f"{__package__}.deformation_authoring")
    if module is not None:
        module.request_managed_preview(context, "deformation metadata changed")


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
    ui_character_open: BoolProperty(default=True)
    ui_ground_open: BoolProperty(default=False)
    ui_rig_open: BoolProperty(default=False)
    ui_pose_open: BoolProperty(default=True)
    ui_pose_left_open: BoolProperty(default=False)
    ui_pose_right_open: BoolProperty(default=False)
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
    ui_mace_guard_open: BoolProperty(default=False)

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
        default="testman_animpack_v001"
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
    facing: EnumProperty(
        name="Character Faces",
        items=[
            ("NEG_Y", "-Y (Animate Anything)", ""),
            ("POS_Y", "+Y", ""),
            ("POS_X", "+X", ""),
            ("NEG_X", "-X", ""),
        ],
        default="NEG_Y"
    )

    # The inspected Animate Anything rig needs the knee hinge inverted but not
    # the elbow hinge. Keeping these independent fixes the v2 behavior.
    invert_knees: BoolProperty(
        name="Invert Knees",
        description="Reverse only the knee bend direction",
        default=True
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

    # Mace head-guard draft timing. Scene FPS determines actual frames.
    mace_guard_raise_seconds: FloatProperty(
        name="Arm Raise", default=0.34, min=0.25, max=0.40, unit='TIME'
    )
    mace_guard_hold_seconds: FloatProperty(
        name="Guard Hold", default=0.15, min=0.10, max=0.20, unit='TIME'
    )
    mace_guard_recovery_seconds: FloatProperty(
        name="Interruptible Recovery", default=0.18, min=0.05, max=0.50, unit='TIME'
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
        default="testman_damage_v001"
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

    # Trauma Field Authoring v3.16.2.
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
    deformation_key_name: StringProperty(name="New Key Name", default="Head_Dent_Left")
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
        name="Feather Distance", default=0.020, min=0.0, max=0.30, unit='LENGTH',
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
        name="Stamp Strength", default=1.0, min=0.0, max=2.0, precision=2,
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
    deformation_impact_semantic_name: StringProperty(
        name="Impact Name",
        description="Optional semantic name; Forge creates a safe unique name when blank",
        default="",
    )
    deformation_impact_preset: EnumProperty(
        name="Impact Preset",
        items=[
            ('HEAD_LEFT', "Head Left", "Configure left-head defaults without choosing polygons"),
            ('HEAD_RIGHT', "Head Right", "Configure right-head defaults without choosing polygons"),
            ('HEAD_FRONT', "Head Front", "Configure front-head defaults without choosing polygons"),
            ('HEAD_BACK', "Head Back", "Configure rear-head defaults without choosing polygons"),
            ('BODY_FRONT', "Body Front", "Configure front-body defaults without choosing polygons"),
            ('BODY_LEFT', "Body Left", "Configure left-body defaults without choosing polygons"),
            ('BODY_RIGHT', "Body Right", "Configure right-body defaults without choosing polygons"),
            ('BODY_BACK', "Body Back", "Configure rear-body defaults without choosing polygons"),
            ('FOREARM_OUTER', "Forearm Outer", "Configure outer-forearm defaults without choosing polygons"),
            ('CUSTOM', "Custom Impact", "Use the active region and current controls"),
        ],
        default='CUSTOM',
    )
    deformation_impact_intensity: EnumProperty(
        name="Intensity",
        items=[
            ('LIGHT', "Light", "Restrained depth and gore"),
            ('MEDIUM', "Medium", "General-purpose impact"),
            ('HEAVY', "Heavy", "High-intensity displacement and raised gore"),
        ],
        default='MEDIUM',
    )
    diagnostics_output_directory: StringProperty(
        name="Diagnostics Folder",
        description="Folder for privacy-safe Forge JSON and Markdown support reports",
        default="//forge_diagnostics/",
        subtype='DIR_PATH',
    )
    deformation_seed_radius: FloatProperty(
        name="Seed Radius", default=0.075, min=0.005, max=0.30, unit='LENGTH',
        update=_deformation_preview_property_updated,
    )
    deformation_seed_depth: FloatProperty(
        name="Seed Depth", default=0.025, min=0.0, max=0.12, unit='LENGTH',
        update=_deformation_preview_property_updated,
    )
    deformation_seed_falloff: FloatProperty(
        name="Falloff Exponent", default=2.2, min=0.35, max=6.0, precision=2,
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
        name="Seam Protection", default=0.025, min=0.0, max=0.10, unit='LENGTH',
        update=_deformation_preview_property_updated,
    )
    deformation_max_vertex_displacement: FloatProperty(
        name="Maximum Displacement", default=0.065, min=0.001, max=0.15, unit='LENGTH',
        update=_deformation_metadata_property_updated,
    )
    deformation_maximum_influence: FloatProperty(
        name="Maximum Runtime Weight", default=1.0, min=0.05, max=2.0, precision=2,
        update=_deformation_metadata_property_updated,
    )
    deformation_gore_enabled: BoolProperty(
        name="Enable Surface Gore Overlay",
        description="Author a procedural blunt-trauma coating on the linked captured outer surface",
        default=False,
        update=_deformation_preview_property_updated,
    )
    deformation_default_heavy_gore: BoolProperty(
        name="Default New Impacts to High-Intensity Gore",
        description="Link the heavy-clotted recipe when the first valid stamp is added to a new deformation",
        default=True,
    )
    deformation_gore_preset: EnumProperty(
        name="Gore Preset",
        items=[
            ('Gore_Ooze_Wet', "Ooze Wet", "Wet localized ooze with medium organic breakup"),
            ('Gore_Clot_Dark', "Clot Dark", "Darker clotted patches with lower gloss"),
            ('Gore_Smear_Heavy', "Smear Heavy", "Broad heavy smear with soft edges"),
            ('Gore_Speckled_Impact', "Speckled Impact", "Sparse fine impact breakup"),
            ('Gore_Crush_Bloodied', "Crush Bloodied", "Dense dark wet coverage for a crushed surface"),
            ('Gore_Crush_Heavy_Clotted', "Crush Heavy Clotted", "High-intensity raised clots, broken islands, dark recesses, and wet crimson highlights"),
        ],
        default='Gore_Crush_Heavy_Clotted',
    )
    deformation_gore_coverage: FloatProperty(name="Coverage", default=0.72, min=0.0, max=1.0, precision=2, update=_deformation_preview_property_updated)
    deformation_gore_scatter: FloatProperty(name="Scatter / Breakup", default=0.48, min=0.0, max=1.0, precision=2, update=_deformation_preview_property_updated)
    deformation_gore_edge_feather: FloatProperty(name="Edge Feather", default=0.70, min=0.0, max=1.0, precision=2)
    deformation_gore_wetness: FloatProperty(name="Wetness / Gloss", default=0.92, min=0.0, max=1.0, precision=2)
    deformation_gore_darkness: FloatProperty(name="Darkness", default=0.38, min=0.0, max=1.0, precision=2)
    deformation_gore_color_bias: FloatVectorProperty(
        name="Color Bias",
        description="Linear RGB bias for the procedural blood coating",
        size=3,
        default=(0.34, 0.012, 0.008),
        min=0.0,
        max=1.0,
        subtype='COLOR',
    )
    deformation_gore_raised_enabled: BoolProperty(
        name="Enable Raised Gore",
        description="Generate ordinary exportable gore shell meshes above the intact deformed surface",
        default=True,
        update=_deformation_preview_property_updated,
    )
    deformation_gore_clot_coverage: FloatProperty(name="Clot Coverage", default=0.82, min=0.0, max=1.0, precision=2)
    deformation_gore_core_density: FloatProperty(name="Core Density", default=0.94, min=0.0, max=1.0, precision=2)
    deformation_gore_clot_thickness: FloatProperty(
        name="Clot Thickness", default=0.0048, min=0.0001, max=0.05, precision=4, unit='LENGTH',
        update=_deformation_preview_property_updated,
    )
    deformation_gore_thickness_variation: FloatProperty(name="Thickness Variation", default=0.88, min=0.0, max=1.0, precision=2)
    deformation_gore_island_breakup: FloatProperty(name="Island Breakup", default=0.86, min=0.0, max=1.0, precision=2, update=_deformation_preview_property_updated)
    deformation_gore_peripheral_fragments: FloatProperty(name="Peripheral Fragments", default=0.58, min=0.0, max=1.0, precision=2)
    deformation_gore_surface_offset: FloatProperty(
        name="Surface Offset", default=0.00065, min=0.00015, max=0.012, precision=5, unit='LENGTH'
    )
    deformation_gore_geometry_density: FloatProperty(name="Geometry Density", default=0.72, min=0.0, max=1.0, precision=2)
    deformation_gore_wetness_variation: FloatProperty(name="Wetness Variation", default=0.84, min=0.0, max=1.0, precision=2)
    deformation_gore_dark_clot_bias: FloatProperty(name="Dark-Clot Bias", default=0.72, min=0.0, max=1.0, precision=2)
    deformation_gore_rough_edge_bias: FloatProperty(name="Rough-Edge Bias", default=0.56, min=0.0, max=1.0, precision=2)
    deformation_gore_color_intensity: FloatProperty(name="Color Intensity", default=1.0, min=0.0, max=1.0, precision=2)
    deformation_gore_organic_irregularity: FloatProperty(
        name="Organic Irregularity",
        description="Break up straight polygon edges and shift refined gore facets without changing the source mesh",
        default=0.78,
        min=0.0,
        max=1.0,
        precision=2,
    )
    deformation_gore_surface_roundness: FloatProperty(
        name="Surface Roundness",
        description="Round and bulge refined clot surfaces so the source triangulation is less visible",
        default=0.82,
        min=0.0,
        max=1.0,
        precision=2,
    )
    deformation_gore_texture_enabled: BoolProperty(
        name="Use Muscle-Fiber Textures",
        description="Wrap every refined gore face in a master-seed-selected muscle-fiber direction",
        default=True,
    )
    deformation_gore_fiber_texture_strength: FloatProperty(
        name="Muscle Fiber Contribution",
        description="Independent additive contribution from the muscle-fiber texture set",
        default=0.82,
        min=0.0,
        max=1.0,
        precision=2,
    )
    deformation_gore_base_color_strength: FloatProperty(
        name="Gore Color Contribution",
        description="Independent additive contribution from the original procedural gore color",
        default=0.30,
        min=0.0,
        max=1.0,
        precision=2,
    )
    deformation_gore_inner_rim_enabled: BoolProperty(
        name="Compromised Inner Reddening",
        description="Generate a second reddened barrier just inside each deformed gore-island edge",
        default=True,
    )
    deformation_gore_inner_rim_width: FloatProperty(
        name="Inner Reddening Width",
        default=0.0032,
        min=0.0001,
        max=0.03,
        precision=4,
        unit='LENGTH',
    )
    deformation_gore_inner_rim_strength: FloatProperty(
        name="Barrier Compromise",
        description="Control the height and visibility of the breached inner reddening layer",
        default=0.88,
        min=0.0,
        max=1.0,
        precision=2,
    )
    deformation_gore_maximum_triangles: IntProperty(
        name="Maximum Triangles", default=12000, min=128, max=100000
    )
    deformation_gore_user_customized: BoolProperty(
        name="Preserve as User-Customized",
        description="Prevent Apply Heavy Gore to All Deformations from replacing this key's recipe",
        default=False,
    )
    deformation_gore_mask_seed: IntProperty(
        name="Master Gore Seed",
        description="Repeatable seed for overlay breakup, islands, fragments, thickness, organic shape, materials, and fiber directions",
        default=1776,
        min=0,
        max=2147483647,
    )
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


def find_safe_wrapper(context):
    """Find the outer Dreadstone scale wrapper related to the selection."""
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

    raise RuntimeError(
        "Could not find the DSB safe wrapper. Select the character or its armature."
    )


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
    """Collect the imported character without pulling in the preview floor."""
    objects = set()
    objects.add(armature)

    for obj in related(context):
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

    # Include the full ancestry of every character object.
    for obj in list(objects):
        current = obj.parent
        while current:
            if current.name != PREVIEW_FLOOR_NAME:
                objects.add(current)
            current = current.parent

    return {
        obj for obj in objects
        if obj.type in {'EMPTY', 'ARMATURE', 'MESH'}
        and obj.name != PREVIEW_FLOOR_NAME
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
    if any(word in lower for word in ("walk", "idle", "locomotion")):
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
        "Animate Anything / testman exact profile"
        if detect_animate_anything_profile(armature)
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
    "left_forearm_twist",
    "left_wrist_flex",
    "left_wrist_side",
    "left_wrist_roll",
    "right_upper_arm_forward",
    "right_upper_arm_roll",
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

class DAF_OT_analyze(Operator):
    bl_idname="daf.analyze"
    bl_label="Analyze Humanoid Rig"
    bl_options={'REGISTER'}
    def execute(self,context):
        try:
            arm=find_armature(context); mapping=map_bones(arm, context.scene.daf_settings)
            profile = write_rig_mapping_report(arm, mapping)
            needed=["hips","thigh_l","shin_l","foot_l","thigh_r","shin_r","foot_r","upper_arm_l","upper_arm_r"]
            missing=[r for r in needed if r not in mapping]
            if missing:
                self.report({'WARNING'},"Missing: "+", ".join(missing))
            else:
                self.report({'INFO'},f"Exact rig profile detected; mapped {len(mapping)} roles. Ready to animate." if detect_animate_anything_profile(arm) else f"Mapped {len(mapping)} humanoid roles. Ready to animate.")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'},str(e)); return {'CANCELLED'}

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

    For the inspected Animate Anything rig, the character faces -Y. The
    shoulder chain must rotate left-positive and right-negative around the
    forward axis to lower the arms. v3.1 used the opposite signs and tended to
    lift or widen them.
    """
    if degrees <= 0.0:
        return

    left_degrees = degrees * left_scale
    right_degrees = degrees * right_scale

    # Rotate the shoulder parent first so the forearm and hand descend with
    # the complete limb, like lowering the arms during a jumping jack.
    rotate(arm, mapping, "shoulder_l", forward_axis, left_degrees * .82)
    rotate(arm, mapping, "upper_arm_l", forward_axis, left_degrees * .18)

    rotate(arm, mapping, "shoulder_r", forward_axis, -right_degrees * .82)
    rotate(arm, mapping, "upper_arm_r", forward_axis, -right_degrees * .18)


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

class DAF_OT_walk(Operator):
    bl_idname = "daf.walk"
    bl_label = "Generate Polished Walk"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            s = context.scene.daf_settings
            arm = find_armature(context)
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

            fwd, side, up = vectors(s)
            knee_sign = -1.0 if s.invert_knees else 1.0
            elbow_sign = -1.0 if s.invert_elbows else 1.0
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

                left_thigh = values["stride_l"] * lt_r
                right_thigh = values["stride_r"] * rt_r
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
                    s.foot_roll * lf_r - left_knee * knee_sign * .20 - left_thigh * .08
                )
                rotate(
                    arm, m, "foot_r", side,
                    s.foot_roll * rf_r - right_knee * knee_sign * .20 - right_thigh * .08
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

            style_label = {
                "CHEST_HOLD": "ChestHold",
                "FACEPLANT": "Faceplant",
                "KNEES_FIRST": "KneesFirst",
            }[s.collapse_style]
            action = ensure_draft_action(
                arm,
                DRAFT_ACTION_NAMES["DEATH"]
            )

            fps = context.scene.render.fps / max(context.scene.render.fps_base, .001)
            start = 1
            motion_end = start + round(s.collapse_seconds * fps)
            final_end = motion_end + s.death_hold_frames
            context.scene.frame_start = start
            context.scene.frame_end = final_end

            fwd, side, up = vectors(s)
            knee_sign = -1.0 if s.invert_knees else 1.0
            elbow_sign = -1.0 if s.invert_elbows else 1.0

            mn, mx = world_bounds(context, character_meshes(context))
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

            # Ratios: curl, hips pitch, lead knee, trailing knee, drop,
            # forward travel, hold arm, brace arm, head, twist, side fall.
            poses = [
                (0.00, 0,  0,  0,  0, 0.00, 0.00, 0.00, 0.00,  0,  0, 0.00),
                (0.12, 9,  4,  3,  2, 0.03, 0.01, 0.38, 0.05, -2,  3, 0.03),
                (0.28, 23, 12, 25, 12, 0.20, 0.08, 0.78, 0.20,  5,  7, 0.12),
                (0.48, 40, 27, 63, 44, 0.48, 0.25, 1.00, 0.55, 12, 10, 0.35),
                (0.68, 61, 49, 78, 65, 0.76, 0.58, 0.78, 0.88, 24, 13, 0.68),
                (0.84, 77, 70, 72, 58, 0.95, 0.90, 0.55, 1.00, 38, 15, 0.92),
                (0.94, 82, 76, 67, 53, 1.00, 1.00, 0.42, 0.82, 46, 17, 1.00),
                (1.00, 80, 74, 64, 50, 1.00, 1.00, 0.32, 0.68, 49, 16, 1.00),
            ]

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

                wiggle = wiggle_pattern[pose_index] * s.death_wiggle
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

            # Duplicate the exact final pose later so it remains frozen.
            context.scene.frame_set(motion_end)
            key_pose(arm, m, final_end)

            set_bezier(action, cycles=False)
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

    fwd, side, up = vectors(s)
    knee_sign = -1.0 if s.invert_knees else 1.0
    elbow_sign = -1.0 if s.invert_elbows else 1.0
    # Facing -Y means anatomical left is -X and right is +X.
    # v3.0 used the opposite sign, making the body reaction look reversed.
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


def mace_guard_frame_schedule(fps, raise_seconds=0.34, hold_seconds=0.15, recovery_seconds=0.18):
    """Build a scene-FPS-aware, short and interruptible brace schedule."""
    fps = max(float(fps), 0.001)
    start = 1
    guard = start + max(1, round(float(raise_seconds) * fps))
    hold_end = guard + max(1, round(float(hold_seconds) * fps))
    end = hold_end + max(1, round(float(recovery_seconds) * fps))
    recognition = start + max(1, round((guard - start) * 0.22))
    return {
        "Brace_Start": start,
        "Recognition": recognition,
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
    fwd, side, up = vectors(settings)
    elbow_sign = -1.0 if settings.invert_elbows else 1.0
    left_scale = float(variant["leftScale"]) * intensity
    right_scale = float(variant["rightScale"]) * intensity

    # Instinctive compression: chin tuck, slight recoil, raised shoulders, and
    # softened knees. Only rotation/location channels are authored.
    rotate(arm, mapping, "spine", side, -7.0 * intensity)
    rotate(arm, mapping, "chest", side, -10.0 * intensity)
    rotate(arm, mapping, "chest", up, float(variant["torsoTurn"]) * intensity)
    rotate(arm, mapping, "neck", side, 8.0 * intensity)
    rotate(arm, mapping, "head", side, 17.0 * intensity)
    rotate(arm, mapping, "head", up, -float(variant["torsoTurn"]) * 0.30 * intensity)
    rotate(arm, mapping, "thigh_l", side, -5.0 * intensity)
    rotate(arm, mapping, "thigh_r", side, -5.0 * intensity)
    rotate(arm, mapping, "shin_l", side, 11.0 * intensity)
    rotate(arm, mapping, "shin_r", side, 11.0 * intensity)
    offset(arm, mapping, "hips", -up * (0.024 * intensity) - fwd * (0.012 * intensity))

    for suffix, scale, inward_sign, asymmetry in (
        ("l", left_scale, -1.0, 1.0),
        ("r", right_scale, 1.0, 0.94),
    ):
        rotate(arm, mapping, f"shoulder_{suffix}", side, -16.0 * scale)
        rotate(arm, mapping, f"upper_arm_{suffix}", side, -76.0 * scale * asymmetry)
        rotate(arm, mapping, f"upper_arm_{suffix}", fwd, inward_sign * 38.0 * scale)
        rotate(arm, mapping, f"upper_arm_{suffix}", up, -inward_sign * 8.0 * scale)
        rotate(arm, mapping, f"lower_arm_{suffix}", side, 112.0 * scale * elbow_sign)
        rotate(arm, mapping, f"lower_arm_{suffix}", fwd, -inward_sign * 11.0 * scale)
        rotate_local(arm, mapping, f"lower_arm_{suffix}", (0.0, 1.0, 0.0), inward_sign * 18.0 * scale)
        rotate_local(arm, mapping, f"hand_{suffix}", (1.0, 0.0, 0.0), -12.0 * scale)
        rotate_local(arm, mapping, f"hand_{suffix}", (0.0, 0.0, 1.0), inward_sign * 8.0 * scale)


def validate_mace_guard_action(context, action, arm=None, mapping=None):
    errors = []
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
                head_height = (head.head.z + head.tail.z) * 0.5
                minimum_height = head_height - max(float(head.length) * 2.5, 0.35)
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
                    forearm_height = max(float(forearm.head.z), float(forearm.tail.z))
                    if forearm_height < minimum_height:
                        errors.append(f"Mace guard {suffix} forearm remains grossly below head height at Guard_Active.")
        finally:
            context.scene.frame_set(previous_frame)
            arm.animation_data.action = previous_action
    return {
        "status": "FAIL" if errors else "PASS",
        "action": action.name,
        "guardVariant": variant_name,
        "guardActiveFrame": markers.get("Guard_Active"),
        "presentedRegions": presented,
        "errors": errors,
    }


def generate_mace_guard_action(context, kind):
    if kind not in MACE_GUARD_VARIANTS:
        raise RuntimeError(f"Unknown mace guard variant {kind!r}.")
    settings = context.scene.daf_settings
    arm = find_armature(context)
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
        (schedule["Recognition"], 0.24),
        (schedule["Guard_Active"], 1.0),
        (schedule["Guard_Hold_End"], 0.96),
        (schedule["Brace_End"], 0.42),
    )
    side_axis = vectors(settings)[1]
    variant = MACE_GUARD_VARIANTS[kind]
    for frame, intensity in stages:
        context.scene.frame_set(frame)
        reset_pose(arm, mapping)
        _apply_mace_guard_pose(arm, mapping, settings, variant, intensity)
        apply_arm_hand_pose_polish(arm, mapping, settings, side_axis)
        key_pose(arm, mapping, frame)
    for marker_name in ("Brace_Start", "Guard_Active", "Brace_End"):
        _set_action_marker(action, marker_name, schedule[marker_name])
    action["dsb_guard_variant"] = variant["guardVariant"]
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
    loop = kind == "WALK" or "walk" in lower or "idle" in lower
    death = kind == "DEATH" or any(word in lower for word in ("death", "collapse", "faceplant"))
    hurt = kind in {"HURT_LEFT", "HURT_RIGHT"} or "hurt" in lower
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
        "return_to_previous_state": bool(hurt),
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
    return result


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


def select_pack_character(context, wrapper, *, include_hidden=False):
    bpy.ops.object.select_all(action='DESELECT')
    selected = []
    for obj in {wrapper} | descendants(wrapper):
        if obj.name == PREVIEW_FLOOR_NAME or obj.type not in {'EMPTY', 'ARMATURE', 'MESH'}:
            continue
        if obj.hide_get() and not include_hidden:
            continue
        obj.select_set(True)
        selected.append(obj)
    if not selected:
        raise RuntimeError('No character objects were selected for export.')
    context.view_layer.objects.active = wrapper
    return selected


def resolve_pack_source(context):
    """Prefer the preserved original rig/hierarchy in a damage authoring file."""

    try:
        from . import damage_authoring
        state = damage_authoring._load_state()
        armature = bpy.data.objects.get(state.get("source_armature_name", ""))
        if armature is not None and armature.type == 'ARMATURE':
            current = armature
            while current is not None:
                if current.get("dsb_safe_size_wrapper", False):
                    return armature, current
                current = current.parent
    except Exception:
        pass
    return find_armature(context), find_safe_wrapper(context)


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


def export_approved_glb(context, filepath, actions, force_sampling):
    armature, wrapper = resolve_pack_source(context)
    selected_before = list(context.selected_objects)
    active_before = context.view_layer.objects.active
    frame_before = context.scene.frame_current
    start_before = context.scene.frame_start
    end_before = context.scene.frame_end
    floor = bpy.data.objects.get(PREVIEW_FLOOR_NAME)
    export_objects = {
        obj for obj in ({wrapper} | descendants(wrapper))
        if obj.name != PREVIEW_FLOOR_NAME and obj.type in {'EMPTY', 'ARMATURE', 'MESH'}
    }
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
        select_pack_character(context, wrapper, include_hidden=True)
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
            guard_actions = [action for action in actions if action.get("dsb_guard_variant")]
            guard_validation = []
            if guard_actions:
                armature = find_armature(context)
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
            export_approved_glb(context, glb_path, actions, settings.pack_force_sampling)
            validation = validate_pack_file(glb_path, [action.name for action in actions])
            stem = os.path.splitext(glb_path)[0]
            manifest_path = stem + '.json'
            validation_path = stem + '_validation.json'
            wrapper = find_safe_wrapper(context)
            manifest = {
                'schema': 'dreadstone.animation_pack.v1',
                'asset': os.path.basename(glb_path),
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'blender_version': bpy.app.version_string,
                'source_blend': bpy.data.filepath or None,
                'approved_animation_count': len(actions),
                'fps': fps,
                'character': {
                    'wrapper_name': wrapper.name,
                    'wrapper_location': list(wrapper.location),
                    'wrapper_scale': list(wrapper.scale),
                    'target_height_m': wrapper.get('dsb_target_height_m'),
                    'original_height_m': wrapper.get('dsb_original_height_m'),
                },
                'animations': metadata,
                'mace_head_guard_validation': guard_validation,
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
            "Trauma Field Authoring v3.16.2",
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
            box.prop(s, "collapse_seconds")
            box.prop(s, "death_pain_side")
            box.prop(s, "death_lead_knee")
            box.prop(s, "death_brace_side")
            box.prop(s, "death_arm_tuck", slider=True)
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
            box.prop(s, "mace_guard_raise_seconds")
            box.prop(s, "mace_guard_hold_seconds")
            box.prop(s, "mace_guard_recovery_seconds")
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
            box.label(text="Brace markers: Brace_Start / Guard_Active / Brace_End", icon='MARKER_HLT')
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
importlib.invalidate_caches()
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
    DAF_OT_analyze,
    DAF_OT_walk,
    DAF_OT_collapse,
    DAF_OT_hurt_left,
    DAF_OT_hurt_right,
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
    *DEFORMATION_AUTHORING_CLASSES,
    *TASK_UI_CLASSES,
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
    except Exception:
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
