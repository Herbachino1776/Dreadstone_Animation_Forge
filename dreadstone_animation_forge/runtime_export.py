"""Explicit Complete Damage runtime graph and animation staging.

The authoring .blend intentionally contains an immutable source character and
an independent generated damage rig.  This module is the shipping boundary:
only role-validated runtime objects and approved Actions staged on
``DSB_DAMAGE_RIG`` may reach Blender's glTF exporter.
"""

from __future__ import annotations

import math
from collections import defaultdict

import bpy

from . import animation_library, attachment_sockets, offensive_actions, offensive_motion


RUNTIME_ARMATURE_ROLE = "authoring_rig"
RUNTIME_SKINNED_ROLES = {"body_core", "attached_segment"}
RUNTIME_RIGID_ROLES = {
    "detached_segment",
    "detached_upper_body",
    "detached_lower_body",
}
RUNTIME_AUXILIARY_ROLES = {"stump_cap", "viscera_socket"}
AUTHORING_ONLY_ROLES = {
    "protected_source_mesh",
    "source_readiness_helper",
    "deformation_preview",
    "diagnostic",
    "export_staging",
    "attachment_socket_helper",
    "offensive_motion_studio_helper",
}
RUNTIME_GENERATED_VISUAL_ROLES = {"raised_gore", "surface_stain_export"}
RUNTIME_EXPORT_MARKER = "dsb_runtime_export_staging"
RUNTIME_ARMATURE_PROPERTY = "dsb_runtime_armature"
RUNTIME_SOURCE_ACTION_PROPERTY = "dsb_runtime_source_action"
RUNTIME_SOURCE_OWNER_PROPERTY = "dsb_runtime_source_owner"
RUNTIME_FRAME_TOLERANCE = 1.0e-5


def _armature_modifiers(obj):
    return [modifier for modifier in getattr(obj, "modifiers", ()) if modifier.type == 'ARMATURE']


def _matrix_close(first, second, tolerance=1.0e-6):
    return all(
        abs(float(first[row][column]) - float(second[row][column])) <= tolerance
        for row in range(4)
        for column in range(4)
    )


def validate_independent_runtime_rig(source_rig, runtime_rig):
    """Prove that the generated rig is an independent exact skeleton copy."""

    errors = []
    if source_rig is None or source_rig.type != 'ARMATURE':
        errors.append("The original source armature is missing.")
    if runtime_rig is None or runtime_rig.type != 'ARMATURE':
        errors.append("DSB_DAMAGE_RIG is missing or is not an armature.")
    if errors:
        return errors
    if source_rig == runtime_rig:
        errors.append("The runtime rig resolves to the original source armature.")
        return errors
    if source_rig.data == runtime_rig.data:
        errors.append("DSB_DAMAGE_RIG still shares its Armature datablock with the source rig.")
    source_names = set(source_rig.data.bones.keys())
    runtime_names = set(runtime_rig.data.bones.keys())
    if source_names != runtime_names:
        missing = sorted(source_names - runtime_names)
        unexpected = sorted(runtime_names - source_names)
        if missing:
            errors.append("DSB_DAMAGE_RIG is missing source bones: " + ", ".join(missing) + ".")
        if unexpected:
            errors.append("DSB_DAMAGE_RIG has unexpected bones: " + ", ".join(unexpected) + ".")
    for name in sorted(source_names & runtime_names):
        source_bone = source_rig.data.bones[name]
        runtime_bone = runtime_rig.data.bones[name]
        source_parent = source_bone.parent.name if source_bone.parent else ""
        runtime_parent = runtime_bone.parent.name if runtime_bone.parent else ""
        if source_parent != runtime_parent:
            errors.append(
                f"DSB_DAMAGE_RIG bone {name!r} parent differs "
                f"({source_parent or '<root>'} -> {runtime_parent or '<root>'})."
            )
        if bool(source_bone.use_deform) != bool(runtime_bone.use_deform):
            errors.append(f"DSB_DAMAGE_RIG bone {name!r} changed its deform role.")
        if not _matrix_close(source_bone.matrix_local, runtime_bone.matrix_local):
            errors.append(f"DSB_DAMAGE_RIG bone {name!r} changed its rest transform.")
    # Object transforms may intentionally differ when the source character is
    # under Forge's safe-size wrapper.  Action compatibility is established by
    # the independent Armature datablock, exact bone hierarchy/rest matrices,
    # and per-Action bone paths; source export scale remains sidecar provenance.
    return errors


def resolve_runtime_objects(state, *, stain_objects=()):
    """Return the complete, closed set allowed in the final Damage GLB.

    Membership comes from persisted generated identities plus role properties.
    Names are used only as assertions for the canonical runtime rig and the
    persisted state graph; arbitrary user/source objects are never discovered
    by prefix or visibility.
    """

    runtime_rig_name = str(state.get("authoring_rig", ""))
    runtime_rig = bpy.data.objects.get(runtime_rig_name)
    source_rig = bpy.data.objects.get(str(state.get("source_armature_name", "")))
    protected_name = str(state.get("protected_source_mesh", ""))
    source_name = str(state.get("source_object_name", ""))
    errors = validate_independent_runtime_rig(source_rig, runtime_rig)
    if runtime_rig_name != "DSB_DAMAGE_RIG":
        errors.append(
            f"Runtime armature is {runtime_rig_name or '<missing>'!r}; DSB_DAMAGE_RIG is required."
        )
    if runtime_rig is not None:
        if not bool(runtime_rig.get("dsb_damage_generated", False)):
            errors.append("DSB_DAMAGE_RIG lacks generated Damage Authoring ownership.")
        if str(runtime_rig.get("dsb_damage_role", "")) != RUNTIME_ARMATURE_ROLE:
            errors.append("DSB_DAMAGE_RIG lacks the authoring-rig role contract.")

    result = []
    state_names = {
        str(name) for name in (state.get("objects", {}) or {}).values() if name
    }
    for name in sorted(state_names):
        obj = bpy.data.objects.get(name)
        if obj is None:
            errors.append(f"Persisted runtime object {name!r} is missing.")
            continue
        role = str(obj.get("dsb_damage_role", ""))
        if not bool(obj.get("dsb_damage_generated", False)):
            errors.append(f"Runtime candidate {name!r} lacks generated ownership.")
            continue
        if role in AUTHORING_ONLY_ROLES or name in {protected_name, source_name}:
            errors.append(f"Authoring-only object {name!r} entered the persisted runtime graph.")
            continue
        if role not in RUNTIME_SKINNED_ROLES | RUNTIME_RIGID_ROLES | RUNTIME_AUXILIARY_ROLES:
            errors.append(f"Runtime candidate {name!r} has unsupported role {role or '<missing>'!r}.")
            continue
        result.append(obj)

    for obj in bpy.data.objects:
        if (
            bool(obj.get("dsb_gore_owned", False))
            and str(obj.get("dsb_generated_role", "")) == "raised_gore"
            and not bool(obj.get("dsb_preview_only", True))
        ):
            from . import variant_authoring

            if not variant_authoring.damage_object_is_effective(obj):
                continue
            result.append(obj)
    for obj in stain_objects:
        if obj is None:
            continue
        if str(obj.get("dsb_generated_role", "")) != "surface_stain_export":
            errors.append(f"Surface-stain candidate {obj.name!r} lacks its export role.")
            continue
        if bool(obj.get("dsb_preview_only", True)):
            errors.append(f"Surface-stain candidate {obj.name!r} is preview-only.")
            continue
        result.append(obj)
    if runtime_rig is not None:
        result.append(runtime_rig)

    result = list(dict.fromkeys(result))
    result_set = set(result)
    forbidden_names = {
        value for value in (source_name, str(state.get("source_armature_name", "")), protected_name)
        if value
    }
    for obj in result:
        role = str(obj.get("dsb_damage_role", ""))
        generated_role = str(obj.get("dsb_generated_role", ""))
        if obj.name in forbidden_names or role in AUTHORING_ONLY_ROLES:
            errors.append(f"Authoring-only object {obj.name!r} is not allowed in the runtime GLB.")
        if obj != runtime_rig and obj.type == 'ARMATURE':
            errors.append(f"Unexpected runtime armature {obj.name!r}; only DSB_DAMAGE_RIG is allowed.")
        modifiers = _armature_modifiers(obj)
        if role in RUNTIME_SKINNED_ROLES:
            if len(modifiers) != 1 or modifiers[0].object != runtime_rig:
                errors.append(f"Runtime skinned mesh {obj.name!r} is not driven only by DSB_DAMAGE_RIG.")
        elif role in RUNTIME_RIGID_ROLES:
            if modifiers:
                errors.append(f"Rigid detached piece {obj.name!r} unexpectedly has Armature skinning.")
        elif role == "stump_cap":
            skinned = str(obj.get("dsb_cap_side", "")) == "skinned_proximal"
            if skinned and (len(modifiers) != 1 or modifiers[0].object != runtime_rig):
                errors.append(f"Skinned stump cap {obj.name!r} is not driven by DSB_DAMAGE_RIG.")
            if not skinned and modifiers:
                errors.append(f"Rigid stump cap {obj.name!r} unexpectedly has Armature skinning.")
        elif generated_role in RUNTIME_GENERATED_VISUAL_ROLES:
            if any(modifier.object != runtime_rig for modifier in modifiers):
                errors.append(f"Generated runtime visual {obj.name!r} targets a non-runtime armature.")
        parent = obj.parent
        if parent is not None and parent not in result_set:
            errors.append(
                f"Runtime object {obj.name!r} depends on non-runtime parent {parent.name!r}."
            )
    if errors:
        raise RuntimeError("Runtime export membership failed: " + "; ".join(errors[:8]))
    return sorted(result, key=lambda obj: obj.name.lower())


def _action_users(action):
    users = set()
    for obj in bpy.data.objects:
        if obj.type != 'ARMATURE' or obj.animation_data is None:
            continue
        data = obj.animation_data
        if data.action == action:
            users.add(obj.name)
        for track in data.nla_tracks:
            if any(strip.action == action for strip in track.strips):
                users.add(obj.name)
    return users


def _action_curve_contract(action, runtime_rig):
    errors = []
    curves = animation_library.iter_action_fcurves(action)
    referenced = set()
    for curve in curves:
        path = str(getattr(curve, "data_path", ""))
        bone_name = animation_library._pose_bone_name(path)
        if not bone_name:
            errors.append(f"Action {action.name!r} has non-bone curve {path or '<empty>'!r}.")
            continue
        referenced.add(bone_name)
        if bone_name not in runtime_rig.data.bones:
            errors.append(
                f"Action {action.name!r} references missing runtime bone {bone_name!r}."
            )
        if path.endswith(".scale"):
            errors.append(f"Action {action.name!r} animates bone scale, which is not runtime-safe.")
    if not curves:
        errors.append(f"Approved Action {action.name!r} contains no animation curves.")
    return curves, referenced, errors


def audit_runtime_actions(state):
    """Resolve approved runtime Actions by owner metadata and semantic kind."""

    runtime_rig = bpy.data.objects.get(str(state.get("authoring_rig", "")))
    source_rig = bpy.data.objects.get(str(state.get("source_armature_name", "")))
    rig_errors = validate_independent_runtime_rig(source_rig, runtime_rig)
    if rig_errors:
        raise RuntimeError("Runtime animation compatibility failed: " + "; ".join(rig_errors[:8]))
    source_name = source_rig.name
    runtime_name = runtime_rig.name
    candidates = []
    errors = []
    ignored = []
    socket_contract = attachment_sockets.runtime_socket_contract(state)
    available_socket_roles = {
        socket["semanticRole"] for socket in socket_contract.get("sockets", [])
    }
    fps = bpy.context.scene.render.fps / max(
        bpy.context.scene.render.fps_base, 0.001
    )
    from . import variant_authoring

    for action in variant_authoring.effective_actions(list(bpy.data.actions)):
        if not bool(action.get("dsb_approved", False)) or bool(action.get("dsb_draft", False)):
            continue
        users = _action_users(action)
        metadata_owner = str(action.get(animation_library.CLIP_OWNER_PROPERTY, ""))
        related = bool({source_name, runtime_name} & users) or metadata_owner in {
            source_name,
            runtime_name,
        }
        if not related:
            ignored.append(action.name)
            continue
        if metadata_owner not in {"", source_name, runtime_name}:
            errors.append(
                f"Approved Action {action.name!r} is used by the damage character but declares owner "
                f"{metadata_owner!r}."
            )
            continue
        if metadata_owner:
            ownership = "RUNTIME" if metadata_owner == runtime_name else "SOURCE"
        elif source_name in users:
            # A copied rig inherits animation-data pointers.  Without explicit
            # runtime owner metadata the original source remains authoritative.
            ownership = "SOURCE"
        elif runtime_name in users:
            ownership = "RUNTIME"
        else:
            ignored.append(action.name)
            continue
        kind = str(action.get("dsb_approved_kind", ""))
        if not kind:
            errors.append(f"Approved Action {action.name!r} has no approved-kind metadata.")
            continue
        curves, bones, curve_errors = _action_curve_contract(action, runtime_rig)
        errors.extend(curve_errors)
        raw_anatomy = str(action.get(animation_library.CLIP_ANATOMY_PROFILE_PROPERTY, ""))
        compatibility = None
        if raw_anatomy:
            compatibility = animation_library.compatibility_report(action, runtime_rig)
            errors.extend(
                f"Action {action.name!r}: {message}"
                for message in compatibility.get("errors", [])
            )
        start, end = animation_library.action_frame_bounds(action)
        if not all(math.isfinite(value) for value in (start, end)) or end < start:
            errors.append(f"Approved Action {action.name!r} has invalid frame bounds.")
        duration_seconds = max(0.0, float(end) - float(start)) / max(fps, 0.001)
        offensive = None
        offensive_targeting = None
        try:
            offensive = offensive_actions.validated_action_metadata(
                action,
                clip_duration_seconds=duration_seconds,
                require_approved=True,
                available_socket_roles=available_socket_roles,
            )
        except ValueError as exc:
            errors.append(f"Action {action.name!r}: {exc}")
        if kind.startswith("ATTACK") and offensive is None:
            errors.append(
                f"Offensive Action {action.name!r} has no valid explicit combat metadata."
            )
        if action.get(offensive_motion.MOTION_RECIPE_PROPERTY):
            try:
                from . import offensive_motion_studio

                offensive_targeting = offensive_motion_studio.validated_targeting_record(
                    bpy.context,
                    action,
                    require_current=True,
                    armature=runtime_rig,
                )
            except (RuntimeError, ValueError) as exc:
                errors.append(f"Action {action.name!r}: {exc}")
        candidates.append(
            {
                "action": action,
                "name": action.name,
                "approvedKind": kind,
                "ownership": ownership,
                "metadataOwner": metadata_owner,
                "activeOwners": sorted(users),
                "clipId": str(action.get(animation_library.CLIP_ID_PROPERTY, "")),
                "frameStart": float(start),
                "frameEnd": float(end),
                "clipDurationSeconds": duration_seconds,
                "curveCount": len(curves),
                "boneCount": len(bones),
                "boneOnly": not curve_errors,
                "compatibility": compatibility,
                "offensiveAction": offensive,
                "offensiveTargeting": offensive_targeting,
            }
        )
    if errors:
        raise RuntimeError("Runtime animation audit failed: " + "; ".join(errors[:8]))

    runtime_kinds = {
        record["approvedKind"] for record in candidates if record["ownership"] == "RUNTIME"
    }
    selected = []
    rejected_source = []
    for record in candidates:
        if record["ownership"] == "SOURCE" and record["approvedKind"] in runtime_kinds:
            rejected_source.append(record)
        else:
            selected.append(record)
    clip_owners = defaultdict(list)
    for record in selected:
        if record["clipId"]:
            clip_owners[record["clipId"]].append(record["name"])
    duplicate_ids = {
        clip_id: names for clip_id, names in clip_owners.items() if len(names) > 1
    }
    if duplicate_ids:
        detail = "; ".join(
            f"{clip_id}: {', '.join(names)}" for clip_id, names in sorted(duplicate_ids.items())
        )
        raise RuntimeError("Runtime animation audit found duplicate clip identities: " + detail)
    combat_id_owners = defaultdict(list)
    for record in selected:
        offensive = record.get("offensiveAction")
        if offensive:
            combat_id_owners[offensive["combatActionId"]].append(record["name"])
    duplicate_combat_ids = {
        action_id: names
        for action_id, names in combat_id_owners.items()
        if len(names) > 1
    }
    if duplicate_combat_ids:
        detail = "; ".join(
            f"{action_id}: {', '.join(names)}"
            for action_id, names in sorted(duplicate_combat_ids.items())
        )
        raise RuntimeError("Runtime animation audit found ambiguous combat Action IDs: " + detail)
    selected.sort(key=lambda record: record["name"].lower())
    rejected_source.sort(key=lambda record: record["name"].lower())
    return {
        "status": "PASS",
        "runtimeArmature": runtime_name,
        "actions": [record["action"] for record in selected],
        "clips": [
            {key: value for key, value in record.items() if key not in {"action", "compatibility"}}
            for record in selected
        ],
        "rejectedSourceActions": [record["name"] for record in rejected_source],
        "rejectedSourceActionCount": len(rejected_source),
        "mirroredSourceActionCount": sum(
            record["ownership"] == "SOURCE" for record in selected
        ),
        "ignoredUnrelatedApprovedActions": sorted(ignored),
        "offensiveActionSchema": offensive_actions.OFFENSIVE_ACTION_SCHEMA,
        "offensiveTargetingSchema": offensive_motion.TARGETING_SCHEMA,
        "offensiveActions": [
            {"actionName": record["name"], **record["offensiveAction"]}
            for record in selected
            if record.get("offensiveAction")
        ],
        "offensiveTargeting": [
            {"actionName": record["name"], **record["offensiveTargeting"]}
            for record in selected
            if record.get("offensiveTargeting")
        ],
    }


def _unique_temporary_action_name(index):
    base = f"__DSB_RUNTIME_EXPORT_SOURCE_{index:03d}"
    name = base
    suffix = 1
    while bpy.data.actions.get(name) is not None:
        name = f"{base}_{suffix:03d}"
        suffix += 1
    return name


def _slot_identifier(slot):
    return str(getattr(slot, "identifier", "")) if slot is not None else ""


def _normalize_runtime_action(action, source_start, source_end):
    """Move only a temporary export clone onto a zero-based timeline."""

    source_start = float(source_start)
    source_end = float(source_end)
    duration_frames = source_end - source_start
    if (
        not math.isfinite(source_start)
        or not math.isfinite(source_end)
        or duration_frames < 0.0
    ):
        raise RuntimeError(f"Runtime Action {action.name!r} has invalid source bounds.")

    shifted_points = 0
    for curve in animation_library.iter_action_fcurves(action):
        for point in curve.keyframe_points:
            point.co[0] = float(point.co[0]) - source_start
            point.handle_left[0] = float(point.handle_left[0]) - source_start
            point.handle_right[0] = float(point.handle_right[0]) - source_start
            shifted_points += 1
        for point in getattr(curve, "sampled_points", ()):
            try:
                point.co[0] = float(point.co[0]) - source_start
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"Runtime Action {action.name!r} contains an unshiftable sampled point."
                ) from exc
            shifted_points += 1
        curve.update()
    if not shifted_points:
        raise RuntimeError(f"Runtime Action {action.name!r} contains no timeline samples.")

    try:
        action.use_frame_range = True
        action.frame_start = 0.0
        action.frame_end = duration_frames
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass

    normalized_start, normalized_end = animation_library.action_frame_bounds(action)
    if (
        abs(float(normalized_start)) > RUNTIME_FRAME_TOLERANCE
        or abs(float(normalized_end) - duration_frames) > RUNTIME_FRAME_TOLERANCE
    ):
        raise RuntimeError(
            f"Runtime Action {action.name!r} did not normalize to "
            f"0..{duration_frames:g} frames."
        )
    return 0.0, duration_frames


class RuntimeAnimationStaging:
    """Temporarily expose approved runtime-owned Action clones on one rig."""

    def __init__(self, state):
        self.state = state
        self.audit = None
        self.runtime_rig = None
        self.created_animation_data = False
        self.previous_action = None
        self.previous_slot_identifier = ""
        self.previous_use_nla = True
        self.previous_use_tweak_mode = False
        self.track_states = []
        self.temporary_tracks = []
        self.original_names = []
        self.clones = []

    def __enter__(self):
        self.audit = audit_runtime_actions(self.state)
        self.runtime_rig = bpy.data.objects[self.audit["runtimeArmature"]]
        self.created_animation_data = self.runtime_rig.animation_data is None
        if self.created_animation_data:
            self.runtime_rig.animation_data_create()
        data = self.runtime_rig.animation_data
        self.previous_action = data.action
        self.previous_slot_identifier = _slot_identifier(getattr(data, "action_slot", None))
        self.previous_use_nla = bool(data.use_nla)
        self.previous_use_tweak_mode = bool(data.use_tweak_mode)
        for track in data.nla_tracks:
            self.track_states.append(
                (track, bool(track.mute), bool(getattr(track, "is_solo", False)))
            )
            track.mute = True
            try:
                track.is_solo = False
            except (AttributeError, RuntimeError):
                pass
        data.use_tweak_mode = False
        data.use_nla = True
        data.action = None
        try:
            for index, (action, clip) in enumerate(zip(self.audit["actions"], self.audit["clips"])):
                export_name = action.name
                temporary_name = _unique_temporary_action_name(index)
                self.original_names.append((action, export_name))
                action.name = temporary_name
                clone = action.copy()
                self.clones.append(clone)
                clone.name = export_name
                clone.use_fake_user = False
                clone[animation_library.CLIP_OWNER_PROPERTY] = self.runtime_rig.name
                clone["dsb_approved"] = True
                clone["dsb_draft"] = False
                clone[RUNTIME_EXPORT_MARKER] = True
                clone[RUNTIME_ARMATURE_PROPERTY] = self.runtime_rig.name
                clone[RUNTIME_SOURCE_ACTION_PROPERTY] = export_name
                clone[RUNTIME_SOURCE_OWNER_PROPERTY] = str(
                    clip.get("metadataOwner") or clip.get("ownership", "")
                )
                start, end = _normalize_runtime_action(
                    clone,
                    clip["frameStart"],
                    clip["frameEnd"],
                )
                track = data.nla_tracks.new()
                self.temporary_tracks.append(track)
                track.name = f"__DSB_RUNTIME_EXPORT__{export_name}"
                strip = track.strips.new(export_name, 0, clone)
                strip.name = export_name
                try:
                    strip.action_frame_start = start
                    strip.action_frame_end = end
                    strip.frame_start = start
                    strip.frame_end = end
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    @property
    def actions(self):
        return list(self.clones)

    def __exit__(self, _exc_type, _exc, _traceback):
        data = self.runtime_rig.animation_data if self.runtime_rig is not None else None
        if data is not None:
            data.use_tweak_mode = False
            data.action = None
            for track in list(self.temporary_tracks):
                try:
                    data.nla_tracks.remove(track)
                except (ReferenceError, RuntimeError):
                    pass
            for track, mute, solo in self.track_states:
                try:
                    track.mute = mute
                    track.is_solo = solo
                except (ReferenceError, RuntimeError, AttributeError):
                    pass
        for clone in list(self.clones):
            if clone and clone.name in bpy.data.actions:
                bpy.data.actions.remove(clone)
        for action, original_name in self.original_names:
            if action and action.name in bpy.data.actions:
                action.name = original_name
        if data is not None:
            try:
                data.action = self.previous_action
                if self.previous_action is not None and self.previous_slot_identifier:
                    slot = next(
                        (
                            value for value in self.previous_action.slots
                            if _slot_identifier(value) == self.previous_slot_identifier
                        ),
                        None,
                    )
                    if slot is not None:
                        data.action_slot = slot
            except (ReferenceError, RuntimeError, AttributeError, TypeError):
                pass
            data.use_nla = self.previous_use_nla
            try:
                data.use_tweak_mode = self.previous_use_tweak_mode
            except RuntimeError:
                pass
        if self.created_animation_data and self.runtime_rig.animation_data is not None:
            self.runtime_rig.animation_data_clear()
        return False


def configure_action_filter(actions):
    """Install Blender 5.1's exact Action allow-list transaction."""

    try:
        from io_scene_gltf2 import GLTF2_filter_action
    except Exception as exc:
        raise RuntimeError(
            "Blender 5.1's glTF Action filter is unavailable; runtime animation isolation cannot be proven."
        ) from exc
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

    return cleanup


__all__ = (
    "RuntimeAnimationStaging",
    "audit_runtime_actions",
    "configure_action_filter",
    "resolve_runtime_objects",
    "validate_independent_runtime_rig",
)
