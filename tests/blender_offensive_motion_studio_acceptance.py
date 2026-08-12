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


def build_master(settings, master_id, *, weapon=None, zone=None):
    settings.motion_master_id = master_id
    if weapon is not None:
        settings.motion_proxy_class = weapon
    if zone is not None:
        settings.motion_target_zone = zone
    settings.motion_feel = "NATURAL"
    settings.motion_target_distance_mode = "AUTO"
    return offensive_motion_studio.build_from_master(bpy.context)


def pose_health(action):
    return offensive_motion.read_json(
        action,
        offensive_motion.MOTION_POSE_HEALTH_PROPERTY,
        "Motion Studio pose health",
    )


def no_deform_arm_location_curves(action):
    names = {
        "shoulder_left", "arm_left_top", "arm_left_bot", "arm_left_hand",
        "shoulder_right", "arm_right_top", "arm_right_bot", "arm_right_hand",
    }
    return not any(
        curve.data_path in {f'pose.bones["{name}"].location' for name in names}
        for curve in addon.iter_action_fcurves(action)
    )


def require_natural_pose(report, label):
    require(report["status"] in {"PASS", "WARN"}, f"{label}: {report.get('errors')}")
    require(report["maximumArmExtensionRatio"] < 0.92, f"{label} arm extension: {report}")
    require(report["maximumShoulderSupportDegrees"] <= 4.1, f"{label} shoulder support: {report}")
    require(report["maximumTorsoContributionDegrees"] < 8.0, f"{label} torso contribution: {report}")
    require(report["maximumDeformTranslationMeters"] <= 0.0001, f"{label} deform translation: {report}")
    require(report["maximumFrameAngularChangeDegrees"] < 45.0, f"{label} angular step: {report}")


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

    overhead = build_master(
        settings,
        "builtin_1h_overhead",
        weapon="ONE_HAND_BLADE",
        zone="HEAD",
    )
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
    overhead_pose = pose_health(overhead_action)
    require_natural_pose(overhead_pose, "Sword Overhead / Head")
    require(
        settings.motion_pose_health_status.startswith("POSE ")
        and "arm " in settings.motion_pose_health_status
        and "solve " in settings.motion_pose_health_detail,
        "Quick workflow did not expose the current pose-health summary.",
    )
    require(
        overhead_pose["maximumArmExtensionRatio"] < 0.92,
        f"Natural sword overhead extended the arm to {overhead_pose['maximumArmExtensionRatio']:.1%}.",
    )
    require(overhead_pose["minimumElbowBendDegrees"] > 15.0, "Natural sword overhead locked the elbow.")
    require(
        overhead_pose["maximumDeformTranslationMeters"] <= 0.0001,
        "Natural sword overhead translated/dislocated the deform arm chain.",
    )
    require(no_deform_arm_location_curves(overhead_action), "Natural sword overhead keyed deform-arm translation.")
    require(rest_digest(armature) == before and len(armature.data.bones) == 21, "Canonical rest skeleton changed.")
    require(
        not any(constraint for bone in armature.pose.bones for constraint in bone.constraints if constraint.name.startswith("DSB_MS_TEMP_")),
        "Temporary IK constraint survived the FK bake.",
    )
    roles = {str(obj.get("dsb_motion_studio_role", "")) for obj in offensive_motion_studio._owned_objects()}
    for role in (
        "TARGET_ROOT",
        "TARGET_CENTER",
        "TARGET_CONTACT_ANCHOR",
        "WEAPON_PROXY",
        "PROXY_CONTACT_POINT",
        "PROXY_TIP",
        "PROXY_GUARD",
        "STRIKE_GEOMETRY",
        "TRAIL_ACTIVE",
        "TRAIL_MARKER_CONTACT",
    ):
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
    contact_anchor = offensive_motion.target_contact_anchor(
        recipe["target"],
        recipe["trajectory"]["contactAnchor"],
        recipe["trajectory"].get("expectedDirectionLocal", (0.0, 1.0, 0.0)),
        proxy_radius=(
            float(recipe["proxy"]["headRadiusMeters"])
            if recipe["proxy"]["class"] == "ONE_HAND_BLUNT"
            else 0.015
        ),
    )
    anticipation = min(samples, key=lambda sample: abs(sample["frame"] - schedule["ANTICIPATION"]))
    require(
        contact_anchor[2] + 0.24 < anticipation["contactPointLocal"][2] < contact_anchor[2] + 0.48
        and anticipation["contactPointLocal"][1] < contact_anchor[1] - 0.08,
        "Natural overhead does not use a compact raised/back anticipation.",
    )
    contact_control = next(control for control in recipe["trajectory"]["controls"] if control["id"] == "CONTACT")
    require(
        max(abs(float(a) - float(b)) for a, b in zip(contact_control["contactPointLocal"], contact_anchor)) < 1.0e-5,
        f"Overhead CONTACT did not use the head impact surface anchor: "
        f"control={contact_control['contactPointLocal']!r}, anchor={contact_anchor!r}.",
    )
    require(
        float(contact_control["weaponAxisLocal"][1]) > 0.75
        and abs(float(contact_control["weaponAxisLocal"][2])) < 0.65,
        "Sword overhead CONTACT reverted to a vertical tip-down/plunging orientation.",
    )
    require(
        float(recipe["proxy"]["strikeSegmentStartMeters"])
        <= float(contact_control["contactDistanceMeters"])
        <= float(recipe["proxy"]["strikeSegmentEndMeters"]),
        "Sword overhead contact slid outside the authored blade strike segment.",
    )
    require(int(recipe["solver"]["ikChainLength"]) == 2, "Natural arm IK is not limited to upper/lower arm ownership.")
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
    support_values = [
        offensive_motion.body_support_envelope(recipe, schedule["CONTACT"] + offset, schedule)
        for offset in (-1, 0, 1)
    ]
    require(
        max(abs(support_values[index + 1] - support_values[index]) for index in range(2)) < 0.20,
        f"Body support snapped around CONTACT: {support_values!r}.",
    )
    chest_quaternions = []
    for frame in (schedule["CONTACT"] - 1, schedule["CONTACT"], schedule["CONTACT"] + 1):
        context.scene.frame_set(frame)
        context.view_layer.update()
        chest_quaternions.append(armature.pose.bones["body_top2"].matrix.to_quaternion().normalized())
    chest_steps = [
        chest_quaternions[index].rotation_difference(chest_quaternions[index + 1]).angle
        for index in range(2)
    ]
    require(max(chest_steps) < 0.18, f"Baked torso snapped around CONTACT: {chest_steps!r}.")
    require(
        sum(
            (float(a) - float(b)) ** 2
            for a, b in zip(overhead_report["closestWeaponPointLocal"], overhead_report["closestTargetAxisPointLocal"])
        ) ** 0.5 < 0.05,
        "Overhead closest approach was not near the intended target axis.",
    )

    sword_torso = build_master(
        settings,
        "builtin_1h_overhead",
        weapon="ONE_HAND_BLADE",
        zone="UPPER_TORSO",
    )
    sword_torso_pose = pose_health(sword_torso["action"])
    require_natural_pose(sword_torso_pose, "Sword Overhead / Upper Torso")
    require(sword_torso["validation"]["status"] == "PASS", sword_torso["validation"].get("errors"))
    require(sword_torso_pose["maximumArmExtensionRatio"] < 0.92, sword_torso_pose)
    require(no_deform_arm_location_curves(sword_torso["action"]), "Torso sword overhead translated the arm.")

    mace_torso = build_master(
        settings,
        "builtin_1h_overhead",
        weapon="ONE_HAND_BLUNT",
        zone="UPPER_TORSO",
    )
    mace_recipe = offensive_motion.read_motion_recipe(mace_torso["action"])
    mace_contact = next(control for control in mace_recipe["trajectory"]["controls"] if control["id"] == "CONTACT")
    mace_pose = pose_health(mace_torso["action"])
    require_natural_pose(mace_pose, "Mace Overhead / Upper Torso")
    require(mace_torso["validation"]["status"] == "PASS", mace_torso["validation"].get("errors"))
    require(mace_pose["maximumArmExtensionRatio"] < 0.92, mace_pose)
    require(
        abs(float(mace_contact["contactDistanceMeters"]) - float(mace_recipe["proxy"]["gripToContactMeters"])) < 1.0e-6,
        "Mace overhead did not lead with its fixed head/contact region.",
    )
    require(
        "PROXY_HEAD" in {str(obj.get("dsb_motion_studio_role", "")) for obj in offensive_motion_studio._owned_objects()},
        "Blunt proxy did not expose a readable head/contact region.",
    )

    settings.motion_master_id = "builtin_1h_overhead"
    settings.motion_proxy_class = "ONE_HAND_BLADE"
    settings.motion_target_zone = "HEAD"
    settings.motion_target_distance_mode = "MANUAL"
    settings.motion_target_distance = 2.50
    unreachable_error = ""
    try:
        offensive_motion_studio.build_from_master(context)
    except RuntimeError as exc:
        unreachable_error = str(exc)
    require(
        "TARGET REQUIRES" in unreachable_error and "AUTO FIT" in unreachable_error,
        f"Impossible manual reach did not fail actionably: {unreachable_error!r}.",
    )
    settings.motion_target_distance_mode = "AUTO"

    # Restore the primary Sword / Head case before stale-proof, preview, and approval checks.
    overhead = build_master(
        settings,
        "builtin_1h_overhead",
        weapon="ONE_HAND_BLADE",
        zone="HEAD",
    )
    overhead_action = overhead["action"]
    overhead_report = overhead["validation"]
    recipe = offensive_motion.read_motion_recipe(overhead_action)

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

    hand = armature.pose.bones["arm_right_hand"]
    hand.location.x = 0.02
    hand.keyframe_insert("location", frame=schedule["CONTACT"], group=hand.name)
    require(
        any("deform arm chain" in error for error in offensive_motion_studio.approval_errors(context, overhead_action)),
        "Approval did not reject an injected deform-hand translation channel.",
    )
    armature.animation_data.action = None
    rebuilt = build_master(
        settings,
        "builtin_1h_overhead",
        weapon="ONE_HAND_BLADE",
        zone="HEAD",
    )
    overhead_action = rebuilt["action"]
    overhead_report = rebuilt["validation"]
    recipe = offensive_motion.read_motion_recipe(overhead_action)
    schedule = offensive_motion.control_frame_schedule(recipe, context.scene.render.fps)

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

    rtl = build_master(
        settings,
        "builtin_1h_slash_rtl",
        weapon="ONE_HAND_BLADE",
        zone="UPPER_TORSO",
    )
    rtl_direction = rtl["validation"]["actualDirectionLocal"][0]
    rtl_pose = pose_health(rtl["action"])
    require_natural_pose(rtl_pose, "RTL Slash")
    ltr = build_master(
        settings,
        "builtin_1h_slash_ltr",
        weapon="ONE_HAND_BLADE",
        zone="UPPER_TORSO",
    )
    ltr_direction = ltr["validation"]["actualDirectionLocal"][0]
    ltr_pose = pose_health(ltr["action"])
    require_natural_pose(ltr_pose, "LTR Slash")
    require(rtl["validation"]["status"] == "PASS", rtl["validation"].get("errors"))
    require(ltr["validation"]["status"] == "PASS", ltr["validation"].get("errors"))
    require(rtl_direction < -0.6 and ltr_direction > 0.6, "Slash directions are not opposite.")
    require(rtl_pose["maximumArmExtensionRatio"] < 0.92, rtl_pose)
    require(ltr_pose["maximumArmExtensionRatio"] < 0.92, ltr_pose)
    require(no_deform_arm_location_curves(ltr["action"]), "Natural slash keyed deform-arm translation.")

    thrust = build_master(
        settings,
        "builtin_1h_thrust",
        weapon="ONE_HAND_BLADE",
        zone="CENTER_MASS",
    )
    require(thrust["validation"]["status"] == "PASS", thrust["validation"].get("errors"))
    require(thrust["validation"]["familyChecks"]["forwardRatio"] > 0.72, "Thrust waved laterally.")
    thrust_action = thrust["action"]
    thrust_recipe = offensive_motion.read_motion_recipe(thrust_action)
    thrust_pose = pose_health(thrust_action)
    require_natural_pose(thrust_pose, "Sword Thrust")
    thrust_schedule = offensive_motion.control_frame_schedule(thrust_recipe, context.scene.render.fps)
    thrust_anchor = offensive_motion.target_contact_anchor(
        thrust_recipe["target"],
        thrust_recipe["trajectory"]["contactAnchor"],
        thrust_recipe["trajectory"].get("expectedDirectionLocal", (0.0, 1.0, 0.0)),
        proxy_radius=(
            float(thrust_recipe["proxy"]["headRadiusMeters"])
            if thrust_recipe["proxy"]["class"] == "ONE_HAND_BLUNT"
            else 0.015
        ),
    )
    require(thrust_recipe["trajectory"]["contactAnchor"] == "ENTRY_SURFACE", thrust_recipe["trajectory"])
    require(
        min(float(control["contactPointLocal"][1]) for control in thrust_recipe["trajectory"]["controls"])
        > float(thrust_anchor[1]) - 0.34,
        "Natural thrust retained an excessive backward chamber.",
    )
    require(thrust_pose["maximumArmExtensionRatio"] < 0.92, thrust_pose)
    require(no_deform_arm_location_curves(thrust_action), "Natural thrust keyed deform-arm translation.")
    wrist_y = []
    for frame in range(thrust_schedule["START"], thrust_schedule["END"] + 1):
        context.scene.frame_set(frame)
        context.view_layer.update()
        wrist_y.append(float(armature.pose.bones["arm_right_hand"].head[1]))
    require(min(wrist_y) > -0.10, f"Natural thrust yanked the wrist behind the body: {min(wrist_y):.3f} m.")

    heavy = build_master(
        settings,
        "builtin_1h_heavy_diagonal",
        weapon="ONE_HAND_BLUNT",
        zone="CENTER_MASS",
    )
    heavy_pose = pose_health(heavy["action"])
    require_natural_pose(heavy_pose, "Heavy Diagonal")
    require(heavy["validation"]["status"] == "PASS", heavy["validation"].get("errors"))
    require(heavy_pose["maximumArmExtensionRatio"] < 0.92, heavy_pose)
    require(no_deform_arm_location_curves(heavy["action"]), "Natural heavy attack keyed deform-arm translation.")

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
        "naturalSwordHeadMaxExtension": overhead_pose["maximumArmExtensionRatio"],
        "naturalSwordHeadMaxAngularChange": overhead_pose["maximumFrameAngularChangeDegrees"],
        "naturalSwordHeadMaxAngularBone": overhead_pose["maximumFrameAngularChangeBone"],
        "naturalSwordHeadMaxAngularFrame": overhead_pose["maximumFrameAngularChangeFrame"],
        "naturalSwordTorsoMaxExtension": sword_torso_pose["maximumArmExtensionRatio"],
        "naturalMaceTorsoMaxExtension": mace_pose["maximumArmExtensionRatio"],
        "naturalSlashMaxExtension": max(rtl_pose["maximumArmExtensionRatio"], ltr_pose["maximumArmExtensionRatio"]),
        "naturalThrustMaxExtension": thrust_pose["maximumArmExtensionRatio"],
        "naturalHeavyMaxExtension": heavy_pose["maximumArmExtensionRatio"],
        "naturalThrustMinimumWristY": min(wrist_y),
        "surfaceContactAnchors": True,
        "bladeSegmentContact": True,
        "impossibleReachBlocked": True,
        "noDeformArmTranslation": True,
        "continuousContactSupport": True,
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
