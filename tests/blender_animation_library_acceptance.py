"""Blender 5.1 acceptance for the VIP saved-animation library.

Run from the repository root:

    blender --background --factory-startup \
      --python tests/blender_animation_library_acceptance.py
"""

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
from dreadstone_animation_forge import animation_library  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def action_fingerprint(action):
    return [
        (
            curve.data_path,
            int(curve.array_index),
            [
                (
                    round(float(point.co[0]), 7),
                    round(float(point.co[1]), 7),
                    str(point.interpolation),
                )
                for point in curve.keyframe_points
            ],
        )
        for curve in animation_library.iter_action_fcurves(action)
    ]


def make_armature(name, *, include_spine=True, length_scale=1.0):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.armature_add(
        enter_editmode=True,
        location=(0.0, 0.0, 0.0),
    )
    armature = bpy.context.active_object
    armature.name = name
    hips = armature.data.edit_bones[0]
    hips.name = "hips"
    hips.head = (0.0, 0.0, 0.0)
    hips.tail = (0.0, 0.0, 0.4 * length_scale)
    if include_spine:
        spine = armature.data.edit_bones.new("spine")
        spine.head = hips.tail
        spine.tail = (0.0, 0.0, 1.0 * length_scale)
        spine.parent = hips
        spine.use_connect = True
    bpy.ops.object.mode_set(mode="POSE")
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def make_saved_walk(context, armature):
    settings = context.scene.daf_settings
    if armature.animation_data is None:
        armature.animation_data_create()
    action = bpy.data.actions.new(
        animation_library.DRAFT_ACTION_NAMES["WALK"]
    )
    armature.animation_data.action = action
    for frame, shift, turn in (
        (1, 0.0, 1.0),
        (13, 0.12, 0.985),
        (25, 0.0, 1.0),
    ):
        context.scene.frame_set(frame)
        hips = armature.pose.bones["hips"]
        hips.location = (shift, 0.0, 0.0)
        hips.rotation_quaternion = (turn, 0.0, 0.0, 0.0)
        hips.keyframe_insert("location", frame=frame, group="hips")
        hips.keyframe_insert(
            "rotation_quaternion",
            frame=frame,
            group="hips",
        )
        spine = armature.pose.bones["spine"]
        spine.rotation_quaternion = (turn, 0.0, 0.0, 0.0)
        spine.keyframe_insert(
            "rotation_quaternion",
            frame=frame,
            group="spine",
        )
    context.scene.frame_start = 1
    context.scene.frame_end = 25
    settings.stride = 31.0
    settings.walk_asymmetry = 8.0
    animation_library.mark_draft(
        action,
        armature,
        settings,
        "WALK",
    )
    saved = addon.approve_draft_action(context, "WALK")
    animation_library.select_action(settings, saved)
    return saved


def main():
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    context = bpy.context
    settings = context.scene.daf_settings
    source_armature = make_armature("VIP_Source_Rig")
    saved = make_saved_walk(context, source_armature)
    original_name = saved.name
    original_clip_id = str(
        saved[animation_library.CLIP_ID_PROPERTY]
    )
    require(
        saved in animation_library.character_actions(source_armature),
        "Approved walk was not listed for its character.",
    )
    available_actions = animation_library.character_actions(
        source_armature,
        include_drafts=True,
    )
    require(
        animation_library.selected_action(
            settings,
            source_armature,
            available_actions=available_actions,
        )
        == saved,
        "Selected-action lookup did not reuse the compatible inventory.",
    )
    require(
        animation_library.selected_action(
            settings,
            source_armature,
            available_actions=[],
        )
        is None,
        "Selected-action lookup escaped an explicitly empty inventory.",
    )
    nla_track = source_armature.animation_data.nla_tracks.new()
    nla_track.name = "VIP Saved Clips"
    nla_strip = nla_track.strips.new(saved.name, 1, saved)

    edit = animation_library.begin_edit(
        context,
        source_armature,
        saved,
    )
    draft = bpy.data.actions.get(edit["draft"])
    require(draft is not None, "Edit did not create a working draft.")
    curves = animation_library.iter_action_fcurves(draft)
    require(curves, "Edit draft contains no F-Curves.")
    edited_curve = curves[0]
    old_value = float(edited_curve.keyframe_points[0].co[1])
    edited_curve.keyframe_points[0].co[1] = old_value + 0.25
    settings.stride = 37.0
    saved_result = animation_library.save_edit(
        context,
        source_armature,
    )
    overwritten = bpy.data.actions.get(original_name)
    require(overwritten is not None, "Save did not preserve the Action name.")
    require(
        str(overwritten[animation_library.CLIP_ID_PROPERTY])
        == original_clip_id,
        "Save did not preserve the stable clip identity.",
    )
    require(
        bool(overwritten.get("dsb_approved", False))
        and not bool(overwritten.get("dsb_draft", True)),
        "Saved edit is not a protected final Action.",
    )
    new_value = float(
        animation_library.iter_action_fcurves(
            overwritten
        )[0].keyframe_points[0].co[1]
    )
    require(
        abs(new_value - (old_value + 0.25)) < 1e-6,
        "Save did not overwrite the source with edited keyframes.",
    )
    require(
        nla_strip.action == overwritten
        and saved_result["nlaUsersReconnected"] == 1,
        "Save did not reconnect the NLA strip to the overwritten Action.",
    )
    playback = animation_library.play_action(
        context,
        source_armature,
        overwritten,
        start_playback=False,
    )
    require(
        playback["frameStart"] == 1
        and playback["frameEnd"] == 25,
        "Play did not apply the exact Action frame range.",
    )

    with tempfile.TemporaryDirectory(
        prefix="daf_animation_clip_"
    ) as temp_directory:
        exported = animation_library.export_action_clip(
            context,
            source_armature,
            overwritten,
            temp_directory,
        )
        require(
            Path(exported["blendPath"]).is_file()
            and Path(exported["manifestPath"]).is_file(),
            "Portable clip export did not create both files.",
        )
        target_armature = make_armature(
            "VIP_Target_Rig",
            length_scale=1.18,
        )
        imported = animation_library.import_action_clip(
            context,
            target_armature,
            exported["blendPath"],
        )
        require(
            len(imported["actions"]) == 1,
            "Compatible target did not import exactly one clip.",
        )
        imported_action = bpy.data.actions.get(
            imported["actions"][0]
        )
        require(
            imported_action is not None
            and target_armature.animation_data.action
            == imported_action,
            "Imported clip was not assigned to the target character.",
        )
        require(
            imported_action
            in animation_library.character_actions(target_armature),
            "Imported clip was not listed for the target character.",
        )

        # A 3.20.1-style animation clip uses the same v1 clip schema but lacks
        # all 4.0 pose-shaping settings. Import must preserve its Action curves
        # and settings payload exactly; the new defaults apply only if a user
        # deliberately regenerates a draft.
        legacy_action = overwritten.copy()
        legacy_action.name = "Zombie_Attack_3_20_1"
        legacy_action[animation_library.CLIP_EXPORT_NAME_PROPERTY] = legacy_action.name
        legacy_action[animation_library.CLIP_SCHEMA_PROPERTY] = (
            animation_library.ANIMATION_CLIP_SCHEMA
        )
        legacy_action[animation_library.CLIP_BUILD_PROPERTY] = (
            "2026-07-28.vip-animation-library.1"
        )
        for anatomy_key in (
            animation_library.CLIP_ANATOMY_PROFILE_PROPERTY,
            animation_library.CLIP_ANATOMY_LEGACY_PROPERTY,
        ):
            if anatomy_key in legacy_action:
                del legacy_action[anatomy_key]
        legacy_settings = json.dumps({
            "facing": "POS_Y",
            "mace_guard_hold_seconds": 0.15,
            "mace_guard_raise_seconds": 0.34,
            "mace_guard_recovery_seconds": 0.18,
        }, sort_keys=True)
        legacy_action[animation_library.CLIP_SETTINGS_PROPERTY] = legacy_settings
        legacy_fingerprint = action_fingerprint(legacy_action)
        legacy_path = Path(temp_directory) / "Zombie_Attack_3_20_1.blend"
        bpy.data.libraries.write(
            str(legacy_path),
            {legacy_action},
            path_remap="NONE",
            fake_user=True,
            compress=True,
        )
        bpy.data.actions.remove(legacy_action)
        legacy_import = animation_library.import_action_clip(
            context,
            target_armature,
            str(legacy_path),
        )
        require(
            len(legacy_import["legacyImports"]) == 1,
            "The 3.20.1 zombie attack was not identified as a legacy clip.",
        )
        imported_legacy_action = bpy.data.actions.get(
            legacy_import["actions"][0]
        )
        require(
            imported_legacy_action is not None,
            "The legacy zombie attack Action was not imported.",
        )
        require(
            action_fingerprint(imported_legacy_action) == legacy_fingerprint,
            "Legacy import changed zombie attack keyframes or curve identity.",
        )
        require(
            str(imported_legacy_action[animation_library.CLIP_SETTINGS_PROPERTY])
            == legacy_settings,
            "Legacy import changed the original 3.20.1 settings payload.",
        )
        require(
            bool(imported_legacy_action[animation_library.CLIP_LEGACY_PROPERTY])
            and bool(imported_legacy_action[animation_library.CLIP_ANATOMY_LEGACY_PROPERTY])
            and str(
                imported_legacy_action[
                    animation_library.CLIP_SOURCE_BUILD_PROPERTY
                ]
            )
            == "2026-07-28.vip-animation-library.1",
            "Legacy import did not retain its 3.20.1 source-build provenance.",
        )
        require(
            "mace_guard_style" not in legacy_settings
            and "left_elbow_flex" not in legacy_settings,
            "Legacy fixture unexpectedly contains 4.0-only settings.",
        )

        incompatible_armature = make_armature(
            "VIP_Incompatible_Rig",
            include_spine=False,
        )
        action_count = len(bpy.data.actions)
        try:
            animation_library.import_action_clip(
                context,
                incompatible_armature,
                exported["blendPath"],
            )
        except RuntimeError as exc:
            require(
                "Missing required bones" in str(exc),
                "Incompatible import failed for the wrong reason.",
            )
        else:
            raise RuntimeError(
                "A target missing the spine bone accepted the clip."
            )
        require(
            len(bpy.data.actions) == action_count,
            "Rejected import leaked an Action datablock.",
        )
        deleted = animation_library.delete_action(
            context,
            target_armature,
            imported_action,
        )
        require(
            bpy.data.actions.get(deleted["action"]) is None,
            "Delete did not remove the imported animation.",
        )
        animation_library.delete_action(
            context,
            target_armature,
            imported_legacy_action,
        )

    for operator_id in (
        "animation_library_select",
        "animation_library_play",
        "animation_library_edit",
        "animation_library_save",
        "animation_library_delete",
        "animation_library_export",
        "animation_library_import",
    ):
        require(
            hasattr(bpy.ops.daf, operator_id),
            f"VIP operator daf.{operator_id} is not registered.",
        )
    report = {
        "status": "PASS",
        "sourceAction": original_name,
        "clipIdPreserved": original_clip_id,
        "editedValueDelta": new_value - old_value,
        "frameRange": [
            playback["frameStart"],
            playback["frameEnd"],
        ],
        "compatibleImportWarnings": sum(
            len(record["warnings"])
            for record in imported["reports"]
        ),
        "legacyZombieAttackPreserved": True,
        "missingBoneRejected": True,
        "saveResult": saved_result,
    }
    print(
        "ANIMATION_LIBRARY_ACCEPTANCE="
        + json.dumps(report, sort_keys=True)
    )


if __name__ == "__main__":
    main()
