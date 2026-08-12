"""Blender background acceptance for weapon-first Offensive Motion Studio."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import (  # noqa: E402
    animation_library,
    attachment_sockets,
    offensive_motion,
    offensive_motion_studio,
)
from dreadstone_animation_forge.anatomy import skin_and_bones  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def create_bone(edit_bones, name, parent, head, tail):
    bone = edit_bones.new(name)
    bone.parent = parent
    bone.head = head
    bone.tail = tail
    return bone


def canonical_humanoid():
    bpy.ops.object.armature_add(enter_editmode=True)
    armature = bpy.context.active_object
    armature.name = attachment_sockets.RUNTIME_ARMATURE_NAME
    bones = armature.data.edit_bones
    root = bones[0]
    root.name = "root"
    root.head = (0.0, 0.0, 0.0)
    root.tail = (0.0, 0.0, 0.10)
    body = create_bone(bones, "body", root, (0.0, 0.0, 0.88), (0.0, 0.0, 1.04))
    spine0 = create_bone(bones, "body_top0", body, (0.0, 0.0, 1.04), (0.0, 0.0, 1.18))
    spine1 = create_bone(bones, "body_top1", spine0, (0.0, 0.0, 1.18), (0.0, 0.0, 1.34))
    chest = create_bone(bones, "body_top2", spine1, (0.0, 0.0, 1.34), (0.0, 0.0, 1.48))
    neck = create_bone(bones, "neck", chest, (0.0, 0.0, 1.48), (0.0, 0.0, 1.58))
    create_bone(bones, "head", neck, (0.0, 0.0, 1.58), (0.0, 0.0, 1.82))
    for side, sign in (("left", -1.0), ("right", 1.0)):
        shoulder = create_bone(
            bones,
            "shoulder_" + side,
            chest,
            (0.0, 0.0, 1.43),
            (0.24 * sign, 0.0, 1.43),
        )
        upper = create_bone(
            bones,
            "arm_" + side + "_top",
            shoulder,
            (0.24 * sign, 0.0, 1.43),
            (0.64 * sign, 0.02, 1.30),
        )
        lower = create_bone(
            bones,
            "arm_" + side + "_bot",
            upper,
            (0.64 * sign, 0.02, 1.30),
            (0.98 * sign, 0.05, 1.20),
        )
        create_bone(
            bones,
            "arm_" + side + "_hand",
            lower,
            (0.98 * sign, 0.05, 1.20),
            (1.10 * sign, 0.10, 1.18),
        )
        thigh = create_bone(
            bones,
            "leg_" + side + "_top",
            body,
            (0.12 * sign, 0.0, 0.90),
            (0.13 * sign, 0.0, 0.50),
        )
        shin = create_bone(
            bones,
            "leg_" + side + "_bot",
            thigh,
            (0.13 * sign, 0.0, 0.50),
            (0.13 * sign, 0.01, 0.10),
        )
        create_bone(
            bones,
            "leg_" + side + "_foot",
            shin,
            (0.13 * sign, 0.01, 0.10),
            (0.13 * sign, 0.25, 0.05),
        )
    bpy.ops.object.mode_set(mode="OBJECT")
    mapping = {
        sbf_role: skin_and_bones.CANONICAL_HUMANOID_MAPPING[forge_role]
        for sbf_role, forge_role in skin_and_bones.SBF_TO_FORGE_ROLE.items()
    }
    armature[skin_and_bones.SBF_RIG_VERSION_PROPERTY] = skin_and_bones.SBF_CANONICAL_RIG_VERSION
    armature[skin_and_bones.SBF_FORWARD_AXIS_PROPERTY] = "+Y"
    armature[skin_and_bones.SBF_UP_AXIS_PROPERTY] = "+Z"
    armature[skin_and_bones.SBF_ROOT_BONE_PROPERTY] = "root"
    armature[skin_and_bones.SBF_ORIENTATION_REVISION_PROPERTY] = 1
    armature[skin_and_bones.SBF_ORIENTATION_STATE_PROPERTY] = "CANONICAL_Y_PLUS"
    armature[skin_and_bones.SBF_RIG_CONTRACT_VERSION_PROPERTY] = 1
    armature[skin_and_bones.SBF_UNIT_SCALE_METERS_PROPERTY] = 1.0
    armature[skin_and_bones.SBF_BONE_MAPPING_PROPERTY] = json.dumps(mapping)
    return armature


def rest_digest(armature):
    return {
        bone.name: (
            bone.parent.name if bone.parent else "",
            tuple(round(float(value), 8) for row in bone.matrix_local for value in row),
        )
        for bone in armature.data.bones
    }


def no_scale(action):
    return not any(curve.data_path.endswith(".scale") for curve in addon.iter_action_fcurves(action))


def build_master(settings, master_id):
    settings.motion_master_id = master_id
    # This synthetic character has long arms but no modeled body depth; a
    # conservative authoring distance keeps the proof inside exact IK reach.
    settings.motion_target_distance = 0.62 if master_id != "builtin_1h_thrust" else 0.76
    return offensive_motion_studio.build_from_master(bpy.context)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    context = bpy.context
    context.scene.render.fps = 24
    context.scene.render.fps_base = 1.0
    armature = canonical_humanoid()
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    context.view_layer.objects.active = armature
    attachment_sockets.ensure_standard_sockets(armature)
    before = rest_digest(armature)
    settings = context.scene.daf_settings

    overhead = build_master(settings, "builtin_1h_overhead")
    # Every target-critical edit must destroy the old proof before approval.
    original_distance = float(settings.motion_target_distance)
    settings.motion_target_distance = original_distance + 0.01
    require(
        offensive_motion.read_json(overhead["action"], offensive_motion.MOTION_VALIDATION_PROPERTY, "validation") is None,
        "A target edit left stale baked-path validation on the draft.",
    )
    settings.motion_target_distance = original_distance
    overhead = offensive_motion_studio.rebuild_body_solve(context)
    overhead_action = overhead["action"]
    overhead_report = overhead["validation"]
    settings.motion_show_target = False
    settings.motion_show_trail = False
    settings.motion_show_plane = False
    offensive_motion_studio.jump_key_pose(context, "CONTACT")
    require(
        settings.motion_show_target and settings.motion_show_trail and settings.motion_show_plane,
        "CONTACT navigation did not reveal the target, baked trail, and strike geometry.",
    )
    require(overhead_report["status"] == "PASS", overhead_report.get("errors"))
    require(overhead_report["activeContact"], "Overhead did not contact during ACTIVE.")
    require(overhead_report["intendedContact"], "Overhead missed its sacred CONTACT frame.")
    require(overhead_report["familyChecks"]["descendingRatio"] > 0.60, "Overhead did not descend.")
    require(not overhead_report["windupIntersected"], "Overhead starts in the target.")
    require(not overhead_report["recoveryBuried"], "Overhead remains buried in recovery.")
    require(no_scale(overhead_action), "Overhead bake contains scale channels.")
    require(rest_digest(armature) == before and len(armature.data.bones) == 21, "Canonical rest skeleton changed.")
    require(
        not any(constraint for bone in armature.pose.bones for constraint in bone.constraints if constraint.name.startswith("DSB_MS_TEMP_")),
        "Temporary IK constraint survived the FK bake.",
    )
    roles = {str(obj.get("dsb_motion_studio_role", "")) for obj in offensive_motion_studio._owned_objects()}
    for role in ("TARGET_ROOT", "TARGET_CENTER", "WEAPON_PROXY", "PROXY_CONTACT_POINT", "STRIKE_GEOMETRY", "TRAIL_ACTIVE", "TRAIL_MARKER_CONTACT"):
        require(role in roles, f"Missing authoring helper role {role}.")
    require(
        all(bool(obj.get("dsb_preview_only", False)) for obj in offensive_motion_studio._owned_objects()),
        "A Motion Studio helper lacks preview-only export exclusion.",
    )
    require(
        not set(offensive_motion_studio._owned_objects()) & addon.character_objects_for_armature(context, armature),
        "Animation pack membership includes Motion Studio helpers.",
    )

    recipe = offensive_motion.read_motion_recipe(overhead_action)
    samples = offensive_motion_studio.sample_baked_weapon_path(context, armature, overhead_action, recipe)
    schedule = offensive_motion.control_frame_schedule(recipe, context.scene.render.fps)
    target_center = offensive_motion.target_zone_center(recipe["target"])
    anticipation = min(samples, key=lambda sample: abs(sample["frame"] - schedule["ANTICIPATION"]))
    require(
        anticipation["contactPointLocal"][2] > target_center[2] + 0.70
        and anticipation["contactPointLocal"][1] < target_center[1] - 0.25,
        "Overhead windup did not raise and draw the weapon behind the target plane.",
    )
    end_sample = samples[-1]
    end_clearance = offensive_motion.segment_volume_distance(
        end_sample["strikeStartLocal"],
        end_sample["strikeEndLocal"],
        offensive_motion.target_zone_volume(recipe["target"]),
    )[0] - float(recipe["proxy"]["headRadiusMeters"])
    require(end_clearance > 0.0, "Overhead weapon did not leave the target by the end of recovery.")
    maximum_foot_drift = 0.0
    for frame in range(schedule["START"], schedule["END"] + 1):
        context.scene.frame_set(frame)
        context.view_layer.update()
        for name in ("leg_left_foot", "leg_right_foot"):
            foot = armature.pose.bones[name]
            maximum_foot_drift = max(
                maximum_foot_drift,
                (foot.head - foot.bone.head_local).length,
            )
    require(maximum_foot_drift < 0.01, f"Body support introduced {maximum_foot_drift:.3f} m of foot drift.")
    require(
        sum(
            (float(a) - float(b)) ** 2
            for a, b in zip(overhead_report["closestWeaponPointLocal"], overhead_report["closestTargetAxisPointLocal"])
        ) ** 0.5 < 0.05,
        "Overhead closest approach was not near the intended target axis.",
    )

    curve = addon.iter_action_fcurves(overhead_action)[0]
    point = curve.keyframe_points[0]
    original_value = float(point.co[1])
    point.co[1] = original_value + 0.002
    require(
        any("changed after validation" in error for error in offensive_motion_studio.approval_errors(context, overhead_action)),
        "An Action-curve edit did not make baked-path validation stale.",
    )
    point.co[1] = original_value
    overhead_report = offensive_motion_studio.validate_baked_action(
        context, overhead_action, sync_inputs=False, rebuild_visuals=True
    )
    require(overhead_report["status"] == "PASS", overhead_report.get("errors"))

    preview = offensive_motion_studio.preview_motion(context, start_playback=False)
    require(preview["previewCount"] == 1, "Motion Studio preview proof was not recorded.")
    approved_overhead = addon.approve_draft_action(context, "ATTACK_OVERHEAD_ONE_HAND")
    require(bool(approved_overhead.get("dsb_motion_artist_approved", False)), "Approval provenance missing.")
    targeting = offensive_motion_studio.validated_targeting_record(context, approved_overhead)
    require(targeting["schema"] == offensive_motion.TARGETING_SCHEMA, targeting)
    pack_metadata = addon.action_pack_metadata(approved_overhead, context.scene.render.fps)
    require(
        pack_metadata["offensive_targeting"] == targeting,
        "Animation Pack metadata did not carry the current targeting companion record.",
    )
    master = offensive_motion_studio.promote_current_master(context, "Reviewed Synthetic Overhead")
    require(master["state"] == "PROMOTED_MASTER" and master["artistApproved"], master)

    rtl = build_master(settings, "builtin_1h_slash_rtl")
    rtl_direction = rtl["validation"]["actualDirectionLocal"][0]
    ltr = build_master(settings, "builtin_1h_slash_ltr")
    ltr_direction = ltr["validation"]["actualDirectionLocal"][0]
    require(rtl["validation"]["status"] == "PASS", rtl["validation"].get("errors"))
    require(ltr["validation"]["status"] == "PASS", ltr["validation"].get("errors"))
    require(rtl_direction < -0.6 and ltr_direction > 0.6, "Slash directions are not opposite.")

    thrust = build_master(settings, "builtin_1h_thrust")
    require(thrust["validation"]["status"] == "PASS", thrust["validation"].get("errors"))
    require(thrust["validation"]["familyChecks"]["forwardRatio"] > 0.72, "Thrust waved laterally.")

    output = Path(tempfile.mkdtemp(prefix="daf_motion_studio_acceptance_"))
    blend = output / "motion_studio_persistence.blend"
    helper_count = len(offensive_motion_studio._owned_objects())
    canonical_bone_count = len(armature.data.bones)
    offensive_motion_studio.remove_helpers()
    require(not offensive_motion_studio._owned_objects(), "Helper removal left owned objects behind.")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    require(
        len(offensive_motion_studio._owned_objects()) == helper_count,
        "Save/reopen did not reconstruct a required Motion Studio authoring session.",
    )
    reloaded = next(action for action in bpy.data.actions if action.get(offensive_motion.MOTION_RECIPE_PROPERTY))
    require(offensive_motion.read_motion_recipe(reloaded) is not None, "Save/reopen lost Motion Studio recipe.")

    print("OFFENSIVE_MOTION_STUDIO_ACCEPTANCE=" + json.dumps({
        "status": "PASS",
        "blenderVersion": bpy.app.version_string,
        "overheadActiveContact": True,
        "overheadDescendingRatio": overhead_report["familyChecks"]["descendingRatio"],
        "overheadPlaneErrorMeters": overhead_report["planeErrorMeters"],
        "overheadContactTimeSeconds": overhead_report["contactTimeSeconds"],
        "maximumFootDriftMeters": maximum_foot_drift,
        "targetAndCurveInvalidation": True,
        "animationPackTargeting": True,
        "contactNavigationRevealsGeometry": True,
        "slashDirections": [rtl_direction, ltr_direction],
        "thrustForwardRatio": thrust["validation"]["familyChecks"]["forwardRatio"],
        "canonicalBoneCount": canonical_bone_count,
        "noScaleAnimation": True,
        "temporaryConstraintsRemoved": True,
        "helperCount": helper_count,
        "loadPostHelperRecovery": True,
        "promotedMasterId": master["masterId"],
        "blend": str(blend),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
