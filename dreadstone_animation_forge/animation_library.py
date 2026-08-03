"""VIP saved-Action lifecycle and portable animation clips."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from pathlib import Path

import bpy

from .anatomy import persistence as anatomy_persistence


ANIMATION_CLIP_SCHEMA = "dreadstone.animation_clip.v1"
ANIMATION_LIBRARY_BUILD_ID = "2026-08-02.death-terminal-grounding-4.1.1"

CLIP_ID_PROPERTY = "dsb_animation_clip_id"
CLIP_SCHEMA_PROPERTY = "dsb_animation_clip_schema"
CLIP_BUILD_PROPERTY = "dsb_animation_library_build"
CLIP_OWNER_PROPERTY = "dsb_animation_owner_rig"
CLIP_REQUIRED_BONES_PROPERTY = "dsb_animation_required_bones_json"
CLIP_RIG_PROFILE_PROPERTY = "dsb_animation_rig_profile_json"
CLIP_ANATOMY_PROFILE_PROPERTY = "dsb_animation_anatomy_json"
CLIP_ANATOMY_LEGACY_PROPERTY = "dsb_animation_anatomy_legacy"
CLIP_SETTINGS_PROPERTY = "dsb_animation_settings_json"
CLIP_EXPORT_NAME_PROPERTY = "dsb_animation_export_name"
CLIP_LEGACY_PROPERTY = "dsb_imported_legacy_clip"
CLIP_SOURCE_SCHEMA_PROPERTY = "dsb_imported_source_schema"
CLIP_SOURCE_BUILD_PROPERTY = "dsb_imported_source_build"

DRAFT_ACTION_NAMES = {
    "WALK": "DSB_DRAFT_Walk",
    "DEATH": "DSB_DRAFT_Death",
    "HURT_LEFT": "DSB_DRAFT_Hurt_LEFT",
    "HURT_RIGHT": "DSB_DRAFT_Hurt_RIGHT",
    "MACE_GUARD_TWO_ARM": "DSB_DRAFT_Mace_Brace_Head_TwoArm",
    "MACE_GUARD_LEFT_ARM": "DSB_DRAFT_Mace_Brace_Head_LeftArm",
    "MACE_GUARD_RIGHT_ARM": "DSB_DRAFT_Mace_Brace_Head_RightArm",
}

_POSE_BONE_PATH = re.compile(
    r'pose\.bones\["((?:[^"\\]|\\.)+)"\]'
)

COMMON_SETTING_FIELDS = (
    "facing",
    "invert_knees",
    "invert_elbows",
    "pose_polish_enabled",
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

KIND_SETTING_FIELDS = {
    "WALK": (
        "walk_style",
        "walk_frames",
        "stride",
        "knee",
        "step_lift",
        "foot_roll",
        "arm_swing",
        "walk_arm_tuck",
        "elbow_bend",
        "hip_bob",
        "hip_sway",
        "pelvis_twist",
        "chest_counter_twist",
        "torso_lean",
        "shoulder_sway",
        "head_stability",
        "walk_asymmetry",
    ),
    "DEATH": (
        "collapse_style",
        "collapse_seconds",
        "death_instant_seconds",
        "death_pain_side",
        "death_lead_knee",
        "death_brace_side",
        "death_arm_tuck",
        "death_wiggle",
        "death_knee_strength",
        "death_curl_strength",
        "death_drop_strength",
        "death_travel_strength",
        "death_twist_strength",
        "death_head_lag",
        "death_fall_bias",
        "death_settle",
        "death_hold_frames",
    ),
    "HURT_LEFT": (
        "hurt_seconds",
        "hurt_severity",
        "hurt_hand_to_flank",
        "hurt_torso_bend",
        "hurt_hand_reach",
        "hurt_twist",
        "hurt_knee_dip",
        "hurt_stagger",
        "hurt_head_recoil",
        "hurt_recovery",
    ),
    "HURT_RIGHT": (
        "hurt_seconds",
        "hurt_severity",
        "hurt_hand_to_flank",
        "hurt_torso_bend",
        "hurt_hand_reach",
        "hurt_twist",
        "hurt_knee_dip",
        "hurt_stagger",
        "hurt_head_recoil",
        "hurt_recovery",
    ),
    "MACE_GUARD_TWO_ARM": (
        "mace_guard_raise_seconds",
        "mace_guard_hold_seconds",
        "mace_guard_recovery_seconds",
        "mace_guard_style",
        "mace_guard_arm_cover",
        "mace_guard_elbow_flex",
        "mace_guard_arm_wrap",
        "mace_guard_shoulder_hunch",
        "mace_guard_torso_curl",
        "mace_guard_head_tuck",
        "mace_guard_crouch",
        "mace_guard_asymmetry",
        "mace_guard_end_release",
    ),
    "MACE_GUARD_LEFT_ARM": (
        "mace_guard_raise_seconds",
        "mace_guard_hold_seconds",
        "mace_guard_recovery_seconds",
        "mace_guard_style",
        "mace_guard_arm_cover",
        "mace_guard_elbow_flex",
        "mace_guard_arm_wrap",
        "mace_guard_shoulder_hunch",
        "mace_guard_torso_curl",
        "mace_guard_head_tuck",
        "mace_guard_crouch",
        "mace_guard_asymmetry",
        "mace_guard_end_release",
    ),
    "MACE_GUARD_RIGHT_ARM": (
        "mace_guard_raise_seconds",
        "mace_guard_hold_seconds",
        "mace_guard_recovery_seconds",
        "mace_guard_style",
        "mace_guard_arm_cover",
        "mace_guard_elbow_flex",
        "mace_guard_arm_wrap",
        "mace_guard_shoulder_hunch",
        "mace_guard_torso_curl",
        "mace_guard_head_tuck",
        "mace_guard_crouch",
        "mace_guard_asymmetry",
        "mace_guard_end_release",
    ),
}


def iter_action_fcurves(action):
    """Return F-Curves from legacy and Blender 4.4+ layered Actions."""

    curves = []
    seen = set()
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        try:
            for curve in legacy:
                pointer = curve.as_pointer()
                if pointer not in seen:
                    seen.add(pointer)
                    curves.append(curve)
        except (AttributeError, RuntimeError, TypeError):
            pass
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for channelbag in getattr(strip, "channelbags", ()):
                for curve in getattr(channelbag, "fcurves", ()):
                    pointer = curve.as_pointer()
                    if pointer not in seen:
                        seen.add(pointer)
                        curves.append(curve)
    return curves


def _pose_bone_name(data_path):
    match = _POSE_BONE_PATH.search(str(data_path))
    if match is None:
        return ""
    return match.group(1).replace(r"\"", '"').replace(r"\\", "\\")


def _curve_bone_usage(curves):
    referenced = set()
    translated = set()
    for curve in curves:
        data_path = str(getattr(curve, "data_path", ""))
        name = _pose_bone_name(data_path)
        if not name:
            continue
        referenced.add(name)
        if data_path.endswith(".location"):
            translated.add(name)
    return sorted(referenced), sorted(translated)


def _curve_frame_metrics(curves):
    minimum = math.inf
    maximum = -math.inf
    keyframe_count = 0
    for curve in curves:
        points = curve.keyframe_points
        keyframe_count += len(points)
        for point in points:
            frame = float(point.co[0])
            if math.isfinite(frame):
                minimum = min(minimum, frame)
                maximum = max(maximum, frame)
    if minimum == math.inf:
        return None, None, keyframe_count
    return minimum, maximum, keyframe_count


def action_frame_bounds(action):
    minimum, maximum, _keyframe_count = _curve_frame_metrics(
        iter_action_fcurves(action)
    )
    if minimum is not None:
        return minimum, maximum
    try:
        return float(action.frame_range[0]), float(action.frame_range[1])
    except Exception:
        return 1.0, 1.0


def referenced_bones(action):
    names, _translated = _curve_bone_usage(iter_action_fcurves(action))
    return names


def infer_action_kind(action):
    declared = str(
        action.get(
            "dsb_approved_kind",
            action.get("dsb_draft_kind", ""),
        )
    )
    if declared:
        return declared
    lower = action.name.lower()
    if "mace" in lower and "twoarm" in lower:
        return "MACE_GUARD_TWO_ARM"
    if "mace" in lower and "leftarm" in lower:
        return "MACE_GUARD_LEFT_ARM"
    if "mace" in lower and "rightarm" in lower:
        return "MACE_GUARD_RIGHT_ARM"
    if "hurt" in lower and "left" in lower:
        return "HURT_LEFT"
    if "hurt" in lower and "right" in lower:
        return "HURT_RIGHT"
    if any(token in lower for token in ("death", "collapse", "faceplant")):
        return "DEATH"
    if any(token in lower for token in ("walk", "locomotion")):
        return "WALK"
    if "crawl" in lower:
        return "CRAWL"
    if any(token in lower for token in ("attack", "strike", "combat")):
        return "ATTACK"
    return "IMPORTED"


def action_category(action):
    kind = infer_action_kind(action)
    if kind in {"WALK", "CRAWL"}:
        return "LOCOMOTION"
    if kind in {"DEATH", "HURT_LEFT", "HURT_RIGHT"}:
        return "REACTIONS"
    if kind.startswith("MACE_GUARD") or kind == "ATTACK":
        return "COMBAT"
    return "OTHER"


def ensure_clip_id(action):
    clip_id = str(action.get(CLIP_ID_PROPERTY, ""))
    if not clip_id:
        clip_id = "clip_" + uuid.uuid4().hex
        action[CLIP_ID_PROPERTY] = clip_id
    return clip_id


def _settings_snapshot(settings, kind):
    fields = tuple(dict.fromkeys(
        COMMON_SETTING_FIELDS + KIND_SETTING_FIELDS.get(kind, ())
    ))
    snapshot = {}
    for identifier in fields:
        if not hasattr(settings, identifier):
            continue
        value = getattr(settings, identifier)
        if isinstance(value, (str, bool, int, float)):
            snapshot[identifier] = value
    return snapshot


def restore_action_settings(settings, action):
    raw = str(action.get(CLIP_SETTINGS_PROPERTY, ""))
    if not raw:
        return 0
    try:
        snapshot = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0
    restored = 0
    for identifier, value in snapshot.items():
        if not hasattr(settings, identifier):
            continue
        try:
            if getattr(settings, identifier) == value:
                restored += 1
                continue
            setattr(settings, identifier, value)
            restored += 1
        except (AttributeError, TypeError, ValueError):
            pass
    return restored


def _canonical_quaternion(bone):
    quaternion = bone.matrix_local.to_quaternion().normalized()
    values = [
        float(quaternion.w),
        float(quaternion.x),
        float(quaternion.y),
        float(quaternion.z),
    ]
    if values[0] < 0.0:
        values = [-value for value in values]
    return [round(value, 7) for value in values]


def armature_profile(armature, bone_names):
    bones = {}
    for name in sorted(set(bone_names)):
        bone = armature.data.bones.get(name)
        if bone is None:
            continue
        bones[name] = {
            "parent": bone.parent.name if bone.parent else "",
            "orientation": _canonical_quaternion(bone),
            "length": round(float(bone.length), 7),
        }
    hierarchy = [
        (name, record["parent"])
        for name, record in sorted(bones.items())
    ]
    digest = hashlib.sha256(
        json.dumps(
            hierarchy,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "armature": armature.name,
        "hierarchyDigest": digest,
        "bones": bones,
    }


def stamp_action_metadata(
    action,
    armature,
    settings,
    kind=None,
    *,
    approved=None,
):
    kind = str(kind or infer_action_kind(action))
    required = referenced_bones(action)
    profile = armature_profile(armature, required)
    action[CLIP_SCHEMA_PROPERTY] = ANIMATION_CLIP_SCHEMA
    action[CLIP_BUILD_PROPERTY] = ANIMATION_LIBRARY_BUILD_ID
    action[CLIP_OWNER_PROPERTY] = armature.name
    action[CLIP_REQUIRED_BONES_PROPERTY] = json.dumps(
        required,
        separators=(",", ":"),
    )
    action[CLIP_RIG_PROFILE_PROPERTY] = json.dumps(
        profile,
        sort_keys=True,
        separators=(",", ":"),
    )
    anatomy = anatomy_persistence.export_metadata(armature, infer_legacy=True)
    action[CLIP_ANATOMY_PROFILE_PROPERTY] = json.dumps(
        anatomy,
        sort_keys=True,
        separators=(",", ":"),
    )
    action[CLIP_ANATOMY_LEGACY_PROPERTY] = bool(anatomy.get("legacy", False))
    action[CLIP_SETTINGS_PROPERTY] = json.dumps(
        _settings_snapshot(settings, kind),
        sort_keys=True,
        separators=(",", ":"),
    )
    action["dsb_approved_kind"] = kind
    ensure_clip_id(action)
    start, end = action_frame_bounds(action)
    action["dsb_approved_frame_start"] = int(math.floor(start))
    action["dsb_approved_frame_end"] = int(math.ceil(end))
    if approved is not None:
        action["dsb_approved"] = bool(approved)
        action["dsb_draft"] = not bool(approved)
    return action


def mark_draft(action, armature, settings, kind):
    stamp_action_metadata(
        action,
        armature,
        settings,
        kind,
        approved=False,
    )
    action["dsb_draft_kind"] = str(kind)
    source_clip_id = str(
        getattr(settings, "animation_library_edit_source_clip_id", "")
    )
    if source_clip_id:
        action["dsb_edit_source_clip_id"] = source_clip_id
    return action


def mark_approved(action, armature, settings, kind=None):
    stamp_action_metadata(
        action,
        armature,
        settings,
        kind,
        approved=True,
    )
    action.use_fake_user = True
    for key in ("dsb_edit_source_clip_id", "dsb_draft_kind"):
        if key in action:
            del action[key]
    return action


def _armature_compatibility_context(armature):
    return {
        "availableBones": set(armature.data.bones.keys()),
        "targetAnatomy": anatomy_persistence.load_metadata(armature),
    }


def compatibility_report(action, armature, *, armature_context=None):
    curves = iter_action_fcurves(action)
    required, location_bones = _curve_bone_usage(curves)
    raw_required = str(action.get(CLIP_REQUIRED_BONES_PROPERTY, ""))
    if raw_required:
        try:
            required = sorted(set(json.loads(raw_required)))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    context = (
        armature_context
        if armature_context is not None
        else _armature_compatibility_context(armature)
    )
    available = context["availableBones"]
    missing = sorted(set(required) - available)
    errors = [
        "Missing required bones: " + ", ".join(missing)
    ] if missing else []
    warnings = []
    source_anatomy = None
    raw_anatomy = str(action.get(CLIP_ANATOMY_PROFILE_PROPERTY, ""))
    if raw_anatomy:
        try:
            source_anatomy = anatomy_persistence.migrate_metadata(
                json.loads(raw_anatomy)
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            warnings.append(
                "The source anatomy metadata is unreadable; legacy rig checks remain authoritative."
            )
    else:
        warnings.append(
            "The clip has no anatomy metadata and is treated as legacy humanoid-compatible."
        )
        source_anatomy = anatomy_persistence.legacy_humanoid_metadata()
    target_anatomy = context["targetAnatomy"]
    if source_anatomy is not None and target_anatomy is not None:
        source_profile_id = str(source_anatomy.get("profileId", ""))
        target_profile_id = str(target_anatomy.get("profileId", ""))
        if (
            source_profile_id
            and target_profile_id
            and source_profile_id != target_profile_id
        ):
            errors.append(
                "Creature Anatomy Profile differs "
                f"({source_profile_id} -> {target_profile_id})."
            )
    source_profile = {}
    raw_profile = str(action.get(CLIP_RIG_PROFILE_PROPERTY, ""))
    if raw_profile:
        try:
            source_profile = json.loads(raw_profile)
        except (TypeError, ValueError, json.JSONDecodeError):
            warnings.append("The source rig profile is unreadable.")
    source_bones = (
        source_profile.get("bones", {})
        if isinstance(source_profile, dict)
        else {}
    )
    for name in required:
        if name in missing:
            continue
        target = armature.data.bones[name]
        source = source_bones.get(name, {})
        source_parent = str(source.get("parent", ""))
        target_parent = target.parent.name if target.parent else ""
        if source and source_parent != target_parent:
            errors.append(
                f"Bone {name!r} parent differs "
                f"({source_parent or '<root>'} -> {target_parent or '<root>'})."
            )
            continue
        orientation = source.get("orientation")
        if isinstance(orientation, list) and len(orientation) == 4:
            target_orientation = _canonical_quaternion(target)
            dot = abs(sum(
                float(first) * float(second)
                for first, second in zip(orientation, target_orientation)
            ))
            if dot < math.cos(math.radians(15.0) * 0.5):
                warnings.append(
                    f"Bone {name!r} has a noticeably different rest orientation."
                )
        source_length = float(source.get("length", 0.0) or 0.0)
        target_length = float(target.length)
        if source_length > 1e-8 and target_length > 1e-8:
            ratio = target_length / source_length
            if ratio < 0.72 or ratio > 1.38:
                warnings.append(
                    f"Bone {name!r} length differs by {abs(1.0 - ratio) * 100.0:.0f}%."
                )
    if location_bones:
        warnings.append(
            "Clip contains pose-bone translation; proportion changes may need adjustment."
        )
    if not required:
        warnings.append(
            "Clip has no pose-bone channels; only object/custom-property animation was found."
        )
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": list(dict.fromkeys(warnings)),
        "requiredBones": required,
        "anatomyLegacy": (
            source_anatomy is None or bool(source_anatomy.get("legacy", False))
        ),
        "sourceAnatomyProfileId": (
            str(source_anatomy.get("profileId", "")) if source_anatomy else ""
        ),
    }


def _explicit_armature_actions(armature):
    explicit = set()
    animation_data = armature.animation_data
    if animation_data is None:
        return explicit
    if animation_data.action is not None:
        explicit.add(animation_data.action)
    for track in animation_data.nla_tracks:
        for strip in track.strips:
            if strip.action is not None:
                explicit.add(strip.action)
    return explicit


def character_actions(armature, *, include_drafts=False):
    explicit = _explicit_armature_actions(armature)
    result = []
    armature_context = None
    for action in bpy.data.actions:
        draft = bool(action.get("dsb_draft", False))
        if draft and not (
            include_drafts and action in explicit
        ):
            continue
        approved = bool(action.get("dsb_approved", False))
        if action not in explicit and not approved:
            continue
        owner = str(action.get(CLIP_OWNER_PROPERTY, ""))
        if action not in explicit and owner and owner != armature.name:
            continue
        if armature_context is None:
            armature_context = _armature_compatibility_context(armature)
        report = compatibility_report(
            action,
            armature,
            armature_context=armature_context,
        )
        if report["errors"]:
            continue
        result.append(action)
    return sorted(
        result,
        key=lambda action: (
            action_category(action),
            action.name.lower(),
        ),
    )


def find_action_by_clip_id(clip_id):
    if not clip_id:
        return None
    return next(
        (
            action
            for action in bpy.data.actions
            if str(action.get(CLIP_ID_PROPERTY, "")) == str(clip_id)
        ),
        None,
    )


def selected_action(
    settings,
    armature=None,
    *,
    include_drafts=True,
    available_actions=None,
):
    action = find_action_by_clip_id(
        str(getattr(settings, "animation_library_active_clip_id", ""))
    )
    if action is None:
        action = bpy.data.actions.get(
            str(getattr(settings, "animation_library_active_action", ""))
        )
    if action is None:
        return None
    if armature is not None:
        candidates = (
            available_actions
            if available_actions is not None
            else character_actions(
                armature,
                include_drafts=include_drafts,
            )
        )
        if action not in candidates:
            return None
    return action


def select_action(settings, action):
    settings.animation_library_active_clip_id = ensure_clip_id(action)
    settings.animation_library_active_action = action.name
    settings.animation_library_status = f"SELECTED — {action.name}"
    return action


def _select_armature_object(context, armature):
    if context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    bpy.ops.object.select_all(action="DESELECT")
    armature.hide_set(False)
    armature.select_set(True)
    context.view_layer.objects.active = armature


def play_action(context, armature, action, *, start_playback=True):
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    start, end = action_frame_bounds(action)
    context.scene.frame_start = int(math.floor(start))
    context.scene.frame_end = int(math.ceil(end))
    context.scene.frame_set(context.scene.frame_start)
    _select_armature_object(context, armature)
    settings = context.scene.daf_settings
    select_action(settings, action)
    settings.animation_library_status = f"PLAYING — {action.name}"
    if (
        start_playback
        and context.screen is not None
        and not bool(getattr(context.screen, "is_animation_playing", False))
    ):
        bpy.ops.screen.animation_play()
    return {
        "action": action.name,
        "frameStart": context.scene.frame_start,
        "frameEnd": context.scene.frame_end,
    }


def _action_has_nla_users(action):
    return any(
        strip.action == action
        for obj in bpy.data.objects
        for animation_data in (getattr(obj, "animation_data", None),)
        if animation_data is not None
        for track in animation_data.nla_tracks
        for strip in track.strips
    )


def _remove_action(action, *, unlink_nla=False):
    for obj in bpy.data.objects:
        animation_data = getattr(obj, "animation_data", None)
        if animation_data is None:
            continue
        if animation_data.action == action:
            animation_data.action = None
        for track in list(animation_data.nla_tracks):
            for strip in list(track.strips):
                if strip.action != action:
                    continue
                if not unlink_nla:
                    raise RuntimeError(
                        f"Action {action.name!r} is used by an NLA strip."
                    )
                track.strips.remove(strip)
    action.use_fake_user = False
    try:
        bpy.data.actions.remove(action, do_unlink=True)
    except TypeError:
        bpy.data.actions.remove(action)


def begin_edit(context, armature, source):
    settings = context.scene.daf_settings
    report = compatibility_report(source, armature)
    if report["errors"]:
        raise RuntimeError(" ".join(report["errors"]))
    kind = infer_action_kind(source)
    draft_name = DRAFT_ACTION_NAMES.get(kind, "DSB_DRAFT_Edit")
    existing = bpy.data.actions.get(draft_name)
    if existing is not None and existing != source:
        if _action_has_nla_users(existing):
            raise RuntimeError(
                f"Existing edit draft {draft_name!r} is used by NLA."
            )
        _remove_action(existing)
    draft = source.copy()
    draft.name = draft_name
    source_clip_id = ensure_clip_id(source)
    draft[CLIP_ID_PROPERTY] = "draft_" + uuid.uuid4().hex
    draft["dsb_edit_source_clip_id"] = source_clip_id
    mark_draft(draft, armature, settings, kind)
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = draft
    start, end = action_frame_bounds(draft)
    context.scene.frame_start = int(math.floor(start))
    context.scene.frame_end = int(math.ceil(end))
    context.scene.frame_set(context.scene.frame_start)
    restored = restore_action_settings(settings, source)
    settings.animation_library_active_clip_id = source_clip_id
    settings.animation_library_active_action = source.name
    settings.animation_library_edit_source_clip_id = source_clip_id
    settings.animation_library_edit_source = source.name
    settings.animation_library_edit_draft = draft.name
    settings.animation_library_status = (
        f"EDITING — {source.name}"
        + (f" · {restored} controls restored" if restored else "")
    )
    _select_armature_object(context, armature)
    try:
        bpy.ops.object.mode_set(mode="POSE")
    except RuntimeError:
        pass
    return {
        "source": source.name,
        "draft": draft.name,
        "kind": kind,
        "restoredSettings": restored,
    }


def edit_existing_draft(context, armature, draft):
    if not bool(draft.get("dsb_draft", False)):
        raise RuntimeError("The selected Action is not a draft.")
    settings = context.scene.daf_settings
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = draft
    start, end = action_frame_bounds(draft)
    context.scene.frame_start = int(math.floor(start))
    context.scene.frame_end = int(math.ceil(end))
    context.scene.frame_set(context.scene.frame_start)
    restored = restore_action_settings(settings, draft)
    select_action(settings, draft)
    settings.animation_library_status = (
        f"EDITING UNSAVED DRAFT — {draft.name}"
    )
    _select_armature_object(context, armature)
    try:
        bpy.ops.object.mode_set(mode="POSE")
    except RuntimeError:
        pass
    return {
        "source": "",
        "draft": draft.name,
        "kind": infer_action_kind(draft),
        "restoredSettings": restored,
        "draftOnly": True,
    }


def _replace_action_users(source, replacement):
    active_users = 0
    nla_users = 0
    for obj in bpy.data.objects:
        animation_data = getattr(obj, "animation_data", None)
        if animation_data is None:
            continue
        if animation_data.action == source:
            animation_data.action = replacement
            active_users += 1
        for track in animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action == source:
                    strip.action = replacement
                    nla_users += 1
    return active_users, nla_users


def save_edit(context, armature):
    settings = context.scene.daf_settings
    source = find_action_by_clip_id(
        str(settings.animation_library_edit_source_clip_id)
    )
    if source is None:
        source = bpy.data.actions.get(str(settings.animation_library_edit_source))
    draft = bpy.data.actions.get(str(settings.animation_library_edit_draft))
    if source is None or draft is None:
        raise RuntimeError(
            "No complete animation edit session exists. Select a saved clip and click Edit."
        )
    if source == draft:
        raise RuntimeError("The saved clip and edit draft unexpectedly reference the same Action.")
    source_name = source.name
    source_clip_id = ensure_clip_id(source)
    kind = infer_action_kind(source)
    temporary_name = "__DSB_REPLACED_" + uuid.uuid4().hex
    source.name = temporary_name
    draft.name = source_name
    draft[CLIP_ID_PROPERTY] = source_clip_id
    mark_approved(draft, armature, settings, kind)
    active_users, nla_users = _replace_action_users(source, draft)
    _remove_action(source, unlink_nla=True)
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = draft
    settings.animation_library_active_clip_id = source_clip_id
    settings.animation_library_active_action = draft.name
    settings.animation_library_edit_source_clip_id = ""
    settings.animation_library_edit_source = ""
    settings.animation_library_edit_draft = ""
    settings.animation_library_status = f"SAVED — {draft.name}"
    return {
        "action": draft.name,
        "activeUsersReconnected": active_users,
        "nlaUsersReconnected": nla_users,
    }


def cancel_edit(context, armature):
    settings = context.scene.daf_settings
    source = find_action_by_clip_id(
        str(settings.animation_library_edit_source_clip_id)
    )
    if source is None:
        source = bpy.data.actions.get(str(settings.animation_library_edit_source))
    draft = bpy.data.actions.get(str(settings.animation_library_edit_draft))
    if source is None:
        raise RuntimeError("The saved source clip for this edit session is missing.")
    if draft is not None and draft != source:
        _remove_action(draft, unlink_nla=True)
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = source
    settings.animation_library_active_clip_id = ensure_clip_id(source)
    settings.animation_library_active_action = source.name
    settings.animation_library_edit_source_clip_id = ""
    settings.animation_library_edit_source = ""
    settings.animation_library_edit_draft = ""
    settings.animation_library_status = f"EDIT CANCELLED — {source.name}"
    return {"action": source.name}


def delete_action(context, armature, action):
    settings = context.scene.daf_settings
    clip_id = str(action.get(CLIP_ID_PROPERTY, ""))
    editing_this = (
        clip_id
        and clip_id == str(settings.animation_library_edit_source_clip_id)
    )
    draft = (
        bpy.data.actions.get(str(settings.animation_library_edit_draft))
        if editing_this
        else None
    )
    name = action.name
    _remove_action(action, unlink_nla=True)
    if (
        draft is not None
        and bpy.data.actions.get(draft.name) == draft
    ):
        _remove_action(draft, unlink_nla=True)
    settings.animation_library_active_clip_id = ""
    settings.animation_library_active_action = ""
    if editing_this:
        settings.animation_library_edit_source_clip_id = ""
        settings.animation_library_edit_source = ""
        settings.animation_library_edit_draft = ""
    settings.animation_library_status = f"DELETED — {name}"
    return {"action": name}


def _safe_filename(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return cleaned or "Dreadstone_Animation_Clip"


def export_action_clip(context, armature, action, directory):
    settings = context.scene.daf_settings
    if bool(action.get("dsb_draft", False)):
        raise RuntimeError(
            "Save the current draft as a finalized animation before exporting it."
        )
    report = compatibility_report(action, armature)
    if report["errors"]:
        raise RuntimeError(" ".join(report["errors"]))
    mark_approved(action, armature, settings, infer_action_kind(action))
    action[CLIP_EXPORT_NAME_PROPERTY] = action.name
    resolved = Path(bpy.path.abspath(str(directory))).resolve()
    if not str(directory).strip():
        raise RuntimeError("Choose an Animation Clip Folder first.")
    resolved.mkdir(parents=True, exist_ok=True)
    blend_path = resolved / (_safe_filename(action.name) + ".blend")
    manifest_path = blend_path.with_suffix(".json")
    bpy.data.libraries.write(
        str(blend_path),
        {action},
        path_remap="NONE",
        fake_user=True,
        compress=True,
    )
    start, end = action_frame_bounds(action)
    curves = iter_action_fcurves(action)
    manifest = {
        "schema": ANIMATION_CLIP_SCHEMA,
        "buildId": ANIMATION_LIBRARY_BUILD_ID,
        "clipId": ensure_clip_id(action),
        "actionName": action.name,
        "kind": infer_action_kind(action),
        "frameStart": start,
        "frameEnd": end,
        "fcurveCount": len(curves),
        "keyframeCount": sum(
            len(curve.keyframe_points)
            for curve in curves
        ),
        "requiredBones": report["requiredBones"],
        "sourceArmature": armature.name,
        "anatomy": anatomy_persistence.export_metadata(
            armature,
            infer_legacy=True,
        ),
        "blendFile": blend_path.name,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    settings.animation_library_status = f"EXPORTED — {blend_path.name}"
    return {
        "blendPath": str(blend_path),
        "manifestPath": str(manifest_path),
        "compatibility": report,
    }


def _unique_action_name(base):
    if bpy.data.actions.get(base) is None:
        return base
    index = 2
    while bpy.data.actions.get(f"{base}_v{index:03d}") is not None:
        index += 1
    return f"{base}_v{index:03d}"


def import_action_clip(context, armature, filepath):
    settings = context.scene.daf_settings
    resolved = Path(bpy.path.abspath(str(filepath))).resolve()
    if not resolved.is_file() or resolved.suffix.lower() != ".blend":
        raise RuntimeError("Choose a valid exported animation clip .blend file.")
    existing_names = set(bpy.data.actions.keys())
    existing_clip_ids = {
        str(action.get(CLIP_ID_PROPERTY, ""))
        for action in bpy.data.actions
        if str(action.get(CLIP_ID_PROPERTY, ""))
    }
    with bpy.data.libraries.load(str(resolved), link=False) as (
        data_from,
        data_to,
    ):
        action_names = list(data_from.actions)
        if not action_names:
            raise RuntimeError("The selected file contains no Actions.")
        data_to.actions = action_names
    loaded = [
        action
        for action in data_to.actions
        if action is not None
    ]
    source_metadata = [
        {
            "schema": str(action.get(CLIP_SCHEMA_PROPERTY, "")),
            "build": str(action.get(CLIP_BUILD_PROPERTY, "")),
            "anatomy": str(action.get(CLIP_ANATOMY_PROFILE_PROPERTY, "")),
        }
        for action in loaded
    ]
    unsupported_schemas = sorted({
        record["schema"]
        for record in source_metadata
        if record["schema"] not in {"", ANIMATION_CLIP_SCHEMA}
    })
    if unsupported_schemas:
        for action in loaded:
            _remove_action(action, unlink_nla=True)
        raise RuntimeError(
            "Animation clip uses an unsupported schema: "
            + ", ".join(unsupported_schemas)
            + "."
        )
    reports = [
        compatibility_report(action, armature)
        for action in loaded
    ]
    failures = [
        error
        for report in reports
        for error in report["errors"]
    ]
    if failures:
        for action in loaded:
            _remove_action(action, unlink_nla=True)
        raise RuntimeError("Animation clip is incompatible: " + "; ".join(failures))
    imported = []
    legacy_count = 0
    for action, report, source in zip(loaded, reports, source_metadata):
        desired = str(
            action.get(CLIP_EXPORT_NAME_PROPERTY, action.name)
        )
        if desired in existing_names:
            desired = _unique_action_name(desired)
        action.name = desired
        is_legacy = (
            source["schema"] != ANIMATION_CLIP_SCHEMA
            or source["build"] != ANIMATION_LIBRARY_BUILD_ID
        )
        if is_legacy:
            legacy_count += 1
        action[CLIP_LEGACY_PROPERTY] = is_legacy
        action[CLIP_SOURCE_SCHEMA_PROPERTY] = source["schema"] or "PRE_SCHEMA"
        action[CLIP_SOURCE_BUILD_PROPERTY] = source["build"] or "PRE_BUILD"
        action[CLIP_OWNER_PROPERTY] = armature.name
        action[CLIP_SCHEMA_PROPERTY] = ANIMATION_CLIP_SCHEMA
        action[CLIP_BUILD_PROPERTY] = ANIMATION_LIBRARY_BUILD_ID
        anatomy_legacy = not bool(source.get("anatomy"))
        if anatomy_legacy:
            action[CLIP_ANATOMY_PROFILE_PROPERTY] = json.dumps(
                anatomy_persistence.legacy_humanoid_metadata(),
                sort_keys=True,
                separators=(",", ":"),
            )
        action[CLIP_ANATOMY_LEGACY_PROPERTY] = anatomy_legacy
        action["dsb_approved"] = True
        action["dsb_draft"] = False
        action.use_fake_user = True
        if str(action.get(CLIP_ID_PROPERTY, "")) in existing_clip_ids:
            action[CLIP_ID_PROPERTY] = "clip_" + uuid.uuid4().hex
        existing_clip_ids.add(ensure_clip_id(action))
        imported.append({
            "action": action,
            "compatibility": report,
            "legacy": is_legacy,
            "sourceSchema": source["schema"],
            "sourceBuild": source["build"],
        })
        existing_names.add(action.name)
    first = imported[0]["action"]
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = first
    select_action(settings, first)
    warning_count = sum(
        len(record["compatibility"]["warnings"])
        for record in imported
    )
    settings.animation_library_status = (
        f"IMPORTED — {len(imported)} clip(s)"
        + (f" · {legacy_count} legacy clip(s) preserved" if legacy_count else "")
        + (f" · {warning_count} compatibility warning(s)" if warning_count else "")
    )
    return {
        "actions": [record["action"].name for record in imported],
        "reports": [
            record["compatibility"]
            for record in imported
        ],
        "legacyImports": [
            {
                "action": record["action"].name,
                "sourceSchema": record["sourceSchema"],
                "sourceBuild": record["sourceBuild"],
            }
            for record in imported
            if record["legacy"]
        ],
    }


def action_summary(action, fps):
    curves = iter_action_fcurves(action)
    start, end, keyframe_count = _curve_frame_metrics(curves)
    if start is None:
        try:
            start = float(action.frame_range[0])
            end = float(action.frame_range[1])
        except Exception:
            start, end = 1.0, 1.0
    duration = max(0.0, end - start) / max(float(fps), 1e-8)
    return {
        "kind": infer_action_kind(action),
        "category": action_category(action),
        "frameStart": int(math.floor(start)),
        "frameEnd": int(math.ceil(end)),
        "durationSeconds": duration,
        "fcurveCount": len(curves),
        "keyframeCount": keyframe_count,
    }


__all__ = (
    "ANIMATION_CLIP_SCHEMA",
    "ANIMATION_LIBRARY_BUILD_ID",
    "CLIP_ANATOMY_LEGACY_PROPERTY",
    "CLIP_ANATOMY_PROFILE_PROPERTY",
    "DRAFT_ACTION_NAMES",
    "action_category",
    "action_frame_bounds",
    "action_summary",
    "begin_edit",
    "cancel_edit",
    "character_actions",
    "compatibility_report",
    "delete_action",
    "edit_existing_draft",
    "ensure_clip_id",
    "export_action_clip",
    "find_action_by_clip_id",
    "import_action_clip",
    "infer_action_kind",
    "mark_approved",
    "mark_draft",
    "play_action",
    "referenced_bones",
    "restore_action_settings",
    "save_edit",
    "select_action",
    "selected_action",
    "stamp_action_metadata",
)
