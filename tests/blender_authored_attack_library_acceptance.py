"""Blender acceptance for the target-free Authored Attack Library.

Run this only against a unique copy of the production Blend::

    blender <working-copy.blend> --background \
      --python tests/blender_authored_attack_library_acceptance.py -- \
      --working-copy <working-copy.blend> \
      --original <never-overwrite-reference.blend>

The active file must exactly match ``--working-copy`` and must not match the
reference file.  This script never saves either Blend.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import (  # noqa: E402
    animation_library,
    authored_attack_library,
    damage_authoring,
    offensive_actions,
    runtime_export,
)
from dreadstone_animation_forge.anatomy import skin_and_bones  # noqa: E402


DEFAULT_REFERENCE = Path(
    r"D:\AI aRt\Skin and Bones Projection packs\Cinderbound_Warden_V1_PRODUCTION"
    r"\Cinderbound_Warden_SIMPLE_ATTACK_FIXED.blend"
)
KNOWN_REFERENCES = (
    DEFAULT_REFERENCE,
    Path(
        r"D:\AI aRt\Skin and Bones Projection packs\Cinderbound_Warden_V1_PRODUCTION"
        r"\Cinderbound_Warden.blend"
    ),
)
EXPECTED_MARKERS = (
    "Attack_Start",
    "Windup_Anticipation",
    "Active_Start",
    "Contact",
    "Active_End",
    "Attack_End",
)
EXPECTED_CLIPS = {
    "authored_slash_rtl_light_blade_v1": {
        "kind": "ATTACK_SLASH_RTL_ONE_HAND",
        "mechanics": "LIGHT_ONE_HAND_BLADE",
        "families": ("SWORD",),
        "classes": ("ONE_HAND_BLADE",),
    },
    "authored_slash_ltr_light_blade_v1": {
        "kind": "ATTACK_SLASH_LTR_ONE_HAND",
        "mechanics": "LIGHT_ONE_HAND_BLADE",
        "families": ("SWORD",),
        "classes": ("ONE_HAND_BLADE",),
    },
    "authored_overhead_top_heavy_v1": {
        "kind": "ATTACK_OVERHEAD_ONE_HAND",
        "mechanics": "TOP_HEAVY_ONE_HAND",
        "families": ("AXE", "MACE"),
        "classes": ("ONE_HAND_BLUNT",),
    },
    "authored_heavy_diagonal_top_heavy_v1": {
        "kind": "ATTACK_HEAVY_ONE_HAND",
        "mechanics": "TOP_HEAVY_ONE_HAND",
        "families": ("AXE", "MACE"),
        "classes": ("ONE_HAND_BLUNT",),
    },
    "authored_thrust_point_forward_v1": {
        "kind": "ATTACK_THRUST_ONE_HAND",
        "mechanics": "POINT_FORWARD",
        "families": ("SWORD", "POLEARM"),
        "classes": ("ONE_HAND_BLADE", "POLEARM"),
    },
}
FORBIDDEN_ACTION_PROPERTIES = (
    "dsb_offensive_recipe_json",
    "dsb_offensive_motion_recipe_json",
    "dsb_offensive_targeting_json",
    "dsb_offensive_motion_bypass_json",
    "dsb_offensive_motion_validation_json",
    "dsb_offensive_motion_pose_health_json",
    "dsb_motion_bypass_active",
    "dsb_motion_approval_mode",
    "dsb_motion_checks_bypassed",
)


def arguments():
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--working-copy", required=True, type=Path)
    parser.add_argument("--original", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--report", type=Path)
    return parser.parse_args(values)


def require(condition, message):
    if not condition:
        raise RuntimeError(str(message))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def guard_working_copy(options):
    require(bpy.data.filepath, "Open the guarded working-copy Blend first.")
    active = Path(bpy.data.filepath).resolve()
    working_copy = options.working_copy.expanduser().resolve()
    original = options.original.expanduser().resolve()
    require(working_copy.is_file(), f"Working copy is missing: {working_copy}")
    require(original.is_file(), f"Reference Blend is missing: {original}")
    require(
        active == working_copy,
        f"Active Blend {active} does not match --working-copy {working_copy}.",
    )
    require(
        active != original,
        "Refusing to run Authored Attack acceptance on the reference Blend.",
    )
    for reference in KNOWN_REFERENCES:
        require(
            active != reference.resolve(),
            f"Refusing to run on a known never-overwrite reference: {reference}",
        )
    return active, original, sha256(original)


def armature_inventory():
    return tuple(
        sorted(
            (obj.name, obj.data.name)
            for obj in bpy.data.objects
            if obj.type == 'ARMATURE'
        )
    )


def rest_inventory(armature):
    return {
        bone.name: tuple(float(value) for row in bone.matrix_local for value in row)
        for bone in armature.data.bones
    }


def constraint_inventory(armature):
    return tuple(
        sorted(
            (bone.name, constraint.name, constraint.type)
            for bone in armature.pose.bones
            for constraint in bone.constraints
        )
    )


def owned_helpers():
    return [
        obj
        for obj in bpy.data.objects
        if bool(obj.get(authored_attack_library.OWNED_HELPER_PROPERTY, False))
    ]


def owned_proxies():
    result = []
    for obj in bpy.data.objects:
        legacy_proxy = (
            bool(obj.get("dsb_motion_studio_owned", False))
            and str(obj.get("dsb_motion_studio_role", "")).startswith("PROXY_")
        )
        if (
            bool(obj.get(authored_attack_library.PREVIEW_PROXY_PROPERTY, False))
            or legacy_proxy
            or obj.name == "DSB_MS_WEAPON_PROXY"
        ):
            result.append(obj)
    return result


def action_fingerprint(action):
    return tuple(
        sorted(
            (
                curve.data_path,
                int(curve.array_index),
                tuple(
                    (
                        round(float(point.co[0]), 7),
                        round(float(point.co[1]), 7),
                        str(point.interpolation),
                    )
                    for point in curve.keyframe_points
                ),
            )
            for curve in animation_library.iter_action_fcurves(action)
        )
    )


def marker_contract(action):
    markers = sorted(
        action.pose_markers,
        key=lambda marker: (int(marker.frame), marker.name),
    )
    names = tuple(marker.name for marker in markers)
    frames = tuple(int(marker.frame) for marker in markers)
    require(names == EXPECTED_MARKERS, f"{action.name} marker order is {names}.")
    require(
        all(second > first for first, second in zip(frames, frames[1:])),
        f"{action.name} marker frames are not strictly ordered: {frames}.",
    )
    return frames


def target_free_contract(context, armature, action, *, require_approved):
    for key in FORBIDDEN_ACTION_PROPERTIES:
        require(key not in action, f"{action.name} contains forbidden metadata {key}.")
    payload = json.loads(str(action[authored_attack_library.AUTHORED_ATTACK_PROPERTY]))
    require(
        payload.get("source") == "BUILTIN_HAND_AUTHORED_BASE",
        f"{action.name} lost built-in authored provenance.",
    )
    require(
        payload.get("targetOrContactGeometryRequired") is False,
        f"{action.name} unexpectedly requires target/contact geometry.",
    )
    require(
        payload.get("semanticBoneMapping"),
        f"{action.name} lost its explicit semantic bone mapping.",
    )
    report = authored_attack_library.validate_action(
        context,
        armature,
        action,
        require_approved=require_approved,
    )
    require(
        report["status"] == "PASS",
        f"{action.name} technical validation failed: " + "; ".join(report["errors"]),
    )
    require(
        report["targetGeometryRequired"] is False,
        f"{action.name} technical validation became target-dependent.",
    )
    require(
        report["motionStudioRecipePresent"] is False,
        f"{action.name} unexpectedly contains a Motion Studio recipe.",
    )
    curves = animation_library.iter_action_fcurves(action)
    require(curves, f"{action.name} contains no ordinary FK curves.")
    require(
        all(
            curve.data_path.startswith('pose.bones["')
            and (
                curve.data_path.endswith(".location")
                or curve.data_path.endswith(".rotation_quaternion")
            )
            for curve in curves
        ),
        f"{action.name} contains a non-FK or non-exportable channel.",
    )
    marker_contract(action)
    return payload, report


def require_no_bake_transients(
    armature,
    *,
    expected_armatures,
    expected_rest,
    expected_constraints,
):
    require(
        armature_inventory() == expected_armatures,
        "Authored bake added or removed an armature/source rig.",
    )
    require(
        rest_inventory(armature) == expected_rest,
        "Authored bake changed the runtime damage-rig rest pose.",
    )
    require(
        constraint_inventory(armature) == expected_constraints,
        "Authored bake added, removed, or changed rig constraints.",
    )
    require(not owned_helpers(), "Authored bake left temporary helper objects.")


def ensure_preview_sockets(armature, mapping):
    created = []
    for name, bone_name in (
        ("DSB_ATTACHMENT_SOCKET_HAND_RIGHT_WEAPON", mapping["hand_r"]),
        ("DSB_ATTACHMENT_SOCKET_HAND_LEFT_WEAPON", mapping["hand_l"]),
    ):
        socket = bpy.data.objects.get(name)
        if socket is not None:
            continue
        socket = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(socket)
        socket.parent = armature
        socket.parent_type = 'BONE'
        socket.parent_bone = bone_name
        socket["dsb_authored_acceptance_fixture"] = True
        created.append(socket)
    return created


def validate_catalog_and_filters(context):
    records = list(authored_attack_library.BUILTIN_CLIPS)
    require(len(records) == 5, f"Expected five built-ins, found {len(records)}.")
    by_id = {str(record["clipId"]): record for record in records}
    require(set(by_id) == set(EXPECTED_CLIPS), "Built-in authored clip IDs drifted.")
    require(
        len({str(record["actionKind"]) for record in records}) == 5,
        "The built-ins do not provide five distinct action kinds.",
    )
    for clip_id, expected in EXPECTED_CLIPS.items():
        record = by_id[clip_id]
        require(record["actionKind"] == expected["kind"], f"{clip_id} kind drifted.")
        require(
            record["mechanicsFamily"] == expected["mechanics"],
            f"{clip_id} mechanics family drifted.",
        )
        require(
            tuple(record["previewWeaponFamilies"]) == expected["families"],
            f"{clip_id} preview families are incompatible.",
        )
        require(
            tuple(record["compatibleWeaponClasses"]) == expected["classes"],
            f"{clip_id} runtime weapon classes are incompatible.",
        )
        require(
            not authored_attack_library.validate_clip_record(record),
            f"Built-in {clip_id} failed its source record contract.",
        )

    thrust = deepcopy(by_id["authored_thrust_point_forward_v1"])
    thrust["previewWeaponFamilies"] = ("SWORD", "AXE", "MACE")
    thrust_errors = authored_attack_library.validate_clip_record(thrust)
    require(
        any("Thrust cannot use axe or mace mechanics" in error for error in thrust_errors),
        "A thrust record incorrectly accepted AXE/MACE mechanics.",
    )

    settings = context.scene.daf_settings
    settings.authored_attack_library_root = ""
    settings.authored_attack_filter_kind = "ATTACK_THRUST_ONE_HAND"
    for incompatible in ("AXE", "MACE"):
        settings.authored_attack_filter_weapon = incompatible
        filtered = authored_attack_library.refresh_library(context)
        require(
            not filtered,
            f"Thrust appeared in the incompatible {incompatible} browser filter.",
        )
    settings.authored_attack_filter_weapon = "SWORD"
    filtered = authored_attack_library.refresh_library(context)
    require(
        [record["clipId"] for record in filtered]
        == ["authored_thrust_point_forward_v1"],
        "The blade-compatible thrust disappeared from the SWORD filter.",
    )
    settings.authored_attack_filter_kind = "ALL"
    settings.authored_attack_filter_weapon = "ALL"
    return by_id


def exercise_proxy_replacement(context, action, families):
    before = action_fingerprint(action)
    first_owned = owned_proxies()
    require(len(first_owned) == 1, "Preview did not create exactly one owned proxy.")
    stale_token = "authored_acceptance_previous_proxy"
    first_owned[0][stale_token] = True
    replacement_family = families[-1]
    replacement = authored_attack_library.replace_preview_proxy(
        context,
        replacement_family,
    )
    current = owned_proxies()
    require(len(current) == 1, "Proxy replacement left zero or multiple owned proxies.")
    require(current[0] == replacement, "Proxy replacement returned the wrong object.")
    require(
        not current[0].get(stale_token, False),
        "Proxy replacement retained the previous owned proxy.",
    )
    require(
        bool(current[0].get(authored_attack_library.PREVIEW_PROXY_PROPERTY, False)),
        "The replacement proxy is not marked as authored-preview-owned.",
    )
    require(
        action_fingerprint(action) == before,
        "Changing the preview proxy modified authored body curves.",
    )


def portable_round_trip(context, armature, actions):
    results = []
    with tempfile.TemporaryDirectory(prefix="daf_authored_attack_clip_") as folder:
        for action in actions:
            fingerprint = action_fingerprint(action)
            frames = marker_contract(action)
            exported = animation_library.export_action_clip(
                context,
                armature,
                action,
                folder,
            )
            blend_path = Path(exported["blendPath"])
            manifest_path = Path(exported["manifestPath"])
            require(
                blend_path.is_file() and manifest_path.is_file(),
                f"Portable export for {action.name} did not create both files.",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload = json.loads(
                str(action[authored_attack_library.AUTHORED_ATTACK_PROPERTY])
            )
            require(
                manifest["kind"] == payload["actionKind"],
                f"Portable manifest kind drifted for {action.name}.",
            )
            imported_result = animation_library.import_action_clip(
                context,
                armature,
                str(blend_path),
            )
            require(
                len(imported_result["actions"]) == 1,
                f"Portable reload for {action.name} did not load exactly one Action.",
            )
            imported = bpy.data.actions.get(imported_result["actions"][0])
            require(imported is not None, f"Reloaded Action for {action.name} is missing.")
            target_free_contract(
                context,
                armature,
                imported,
                require_approved=True,
            )
            require(
                action_fingerprint(imported) == fingerprint,
                f"Portable reload changed FK curves for {action.name}.",
            )
            require(
                marker_contract(imported) == frames,
                f"Portable reload changed markers for {action.name}.",
            )
            results.append(
                {
                    "kind": payload["actionKind"],
                    "blend": blend_path.name,
                    "fcurveCount": len(animation_library.iter_action_fcurves(imported)),
                }
            )
            if armature.animation_data and armature.animation_data.action == imported:
                armature.animation_data.action = action
            bpy.data.actions.remove(imported, do_unlink=True)
    return results


def main():
    options = arguments()
    active, original, original_hash = guard_working_copy(options)
    created_sockets = []
    try:
        # Force the checkout's PropertyGroup/operator registration even when
        # another installed Forge build was enabled in Blender preferences.
        addon.register()
        context = bpy.context
        settings = context.scene.daf_settings
        require(
            tuple(authored_attack_library.REQUIRED_MARKERS) == EXPECTED_MARKERS,
            "Authored marker constant order drifted.",
        )
        armature = bpy.data.objects.get("DSB_DAMAGE_RIG")
        require(
            armature is not None and armature.type == 'ARMATURE',
            "The working copy has no game-ready DSB_DAMAGE_RIG armature.",
        )
        source_armature = bpy.data.objects.get("SBF_ProductionRig")
        source_action_before = (
            source_armature.animation_data.action
            if source_armature is not None and source_armature.animation_data is not None
            else None
        )
        source_rest_before = (
            rest_inventory(source_armature) if source_armature is not None else None
        )
        rig_contract = skin_and_bones.require_canonical_yplus(
            armature,
            label="Authored Attack acceptance",
        )
        mapping = dict(rig_contract["roleMapping"])
        bpy.ops.object.select_all(action='DESELECT')
        armature.select_set(True)
        context.view_layer.objects.active = armature
        context.scene.render.fps = 24
        context.scene.render.fps_base = 1.0

        authored_attack_library.cleanup_transients(context)
        require(not owned_proxies(), "Stale owned proxies survived initial cleanup.")
        require(not owned_helpers(), "Stale authored helpers survived initial cleanup.")
        created_sockets = ensure_preview_sockets(armature, mapping)

        expected_armatures = armature_inventory()
        expected_rest = rest_inventory(armature)
        expected_constraints = constraint_inventory(armature)
        by_id = validate_catalog_and_filters(context)
        previous_action = armature.animation_data.action if armature.animation_data else None
        previous_frame_state = (
            context.scene.frame_current,
            context.scene.frame_start,
            context.scene.frame_end,
        )
        settings.authored_attack_active_clip_id = next(iter(EXPECTED_CLIPS))
        authored_attack_library.preview_selected(context)
        authored_attack_library.clear_preview(context)
        require(
            armature.animation_data is not None
            and armature.animation_data.action == previous_action,
            "Clearing authored preview did not restore the runtime rig's prior Action.",
        )
        require(
            (
                context.scene.frame_current,
                context.scene.frame_start,
                context.scene.frame_end,
            )
            == previous_frame_state,
            "Clearing authored preview did not restore the prior frame range.",
        )
        require(
            source_armature is None or source_armature.hide_viewport or source_armature.hide_get(),
            "Clearing authored preview left SBF_ProductionRig visible.",
        )
        root_motion_probes = []
        for mirror in (False, True):
            settings.authored_attack_active_clip_id = "authored_thrust_point_forward_v1"
            settings.authored_attack_root_policy = "AUTHORED_ROOT_MOTION"
            settings.authored_attack_mirror = mirror
            root_preview = authored_attack_library.preview_selected(context)
            root_payload, _root_report = target_free_contract(
                context,
                armature,
                root_preview,
                require_approved=False,
            )
            root_scale = float(root_payload.get("rootMotionScale", 0.0))
            require(
                root_scale == 1.0,
                "Authored thrust changed the authored root-motion magnitude.",
            )
            require(
                float(root_preview.get("dsb_authored_root_motion_scale", 0.0)) == 1.0,
                "Authored thrust Action changed the authored root-motion magnitude.",
            )
            stance_fit_scale = float(root_payload.get("stanceFitScale", -1.0))
            pelvis_drop_max = float(root_payload.get("footPlantPelvisDropMax", -1.0))
            pelvis_drop_limit = float(root_payload.get("footPlantPelvisDropLimit", -1.0))
            require(
                0.0 < stance_fit_scale <= 1.0,
                "Authored thrust recorded an invalid stance-fit scale.",
            )
            require(
                0.0 <= pelvis_drop_max <= pelvis_drop_limit,
                "Authored thrust exceeded its bounded pelvis-drop limit.",
            )
            require(
                float(root_preview.get("dsb_authored_stance_fit_scale", -1.0))
                == stance_fit_scale,
                "Authored thrust Action lost its stance-fit scale.",
            )
            require(
                float(root_preview.get("dsb_authored_foot_plant_drop_max", -1.0))
                == pelvis_drop_max,
                "Authored thrust Action lost its maximum pelvis drop.",
            )
            root_motion_probes.append(
                {
                    "mirror": mirror,
                    "rootMotionScale": root_scale,
                    "stanceFitScale": stance_fit_scale,
                    "footPlantPelvisDropMax": pelvis_drop_max,
                    "footPlantPelvisDropLimit": pelvis_drop_limit,
                }
            )
            authored_attack_library.clear_preview(context)
            require(
                armature.animation_data is not None
                and armature.animation_data.action == previous_action,
                "Root-motion thrust preview did not restore the prior runtime Action.",
            )
        approved = []
        lifecycle = []

        for clip_id, expected in EXPECTED_CLIPS.items():
            record = by_id[clip_id]
            settings.authored_attack_active_clip_id = clip_id
            settings.authored_attack_preview_weapon = expected["families"][0]
            settings.authored_attack_mirror = False
            settings.authored_attack_speed = 1.0
            settings.authored_attack_root_policy = "IN_PLACE"

            preview = authored_attack_library.preview_selected(context)
            require(
                armature.animation_data.action == preview,
                f"{clip_id} preview was not assigned to DSB_DAMAGE_RIG.",
            )
            require(
                source_armature is None
                or source_armature.animation_data is None
                or source_armature.animation_data.action == source_action_before,
                f"{clip_id} changed the source production rig Action.",
            )
            require(
                bool(preview.get(authored_attack_library.AUTHORED_PREVIEW_PROPERTY, False)),
                f"{clip_id} was not marked as an authored preview.",
            )
            preview_payload, preview_report = target_free_contract(
                context,
                armature,
                preview,
                require_approved=False,
            )
            require(
                tuple(preview_payload["previewWeaponFamilies"])
                == tuple(record["previewWeaponFamilies"]),
                f"{clip_id} preview provenance changed weapon-family compatibility.",
            )
            exercise_proxy_replacement(
                context,
                preview,
                tuple(expected["families"]),
            )
            require_no_bake_transients(
                armature,
                expected_armatures=expected_armatures,
                expected_rest=expected_rest,
                expected_constraints=expected_constraints,
            )

            draft = authored_attack_library.accept_preview_as_draft(context)
            require(
                bool(draft.get("dsb_draft", False))
                and not bool(draft.get("dsb_approved", False)),
                f"{clip_id} was not accepted as an editable draft.",
            )
            require(
                str(draft.get(animation_library.CLIP_OWNER_PROPERTY, ""))
                == "DSB_DAMAGE_RIG",
                f"{clip_id} draft is not owned by DSB_DAMAGE_RIG.",
            )
            require(
                not bool(draft.get(authored_attack_library.AUTHORED_PREVIEW_PROPERTY, True)),
                f"{clip_id} draft retained preview-only identity.",
            )
            target_free_contract(
                context,
                armature,
                draft,
                require_approved=False,
            )
            require(not owned_proxies(), f"{clip_id} draft acceptance left a proxy.")

            final = authored_attack_library.finalize_draft(
                context,
                armature,
                draft,
            )
            require(
                bool(final.get("dsb_approved", False))
                and not bool(final.get("dsb_draft", True)),
                f"{clip_id} did not finalize as an approved library Action.",
            )
            require(
                str(final.get(animation_library.CLIP_OWNER_PROPERTY, ""))
                == "DSB_DAMAGE_RIG",
                f"{clip_id} final Action is not owned by DSB_DAMAGE_RIG.",
            )
            final_payload, final_report = target_free_contract(
                context,
                armature,
                final,
                require_approved=True,
            )
            require(
                offensive_actions.read_offensive_metadata(final) is not None,
                f"{clip_id} lost dreadstone.offensive_action.v1 metadata.",
            )
            require_no_bake_transients(
                armature,
                expected_armatures=expected_armatures,
                expected_rest=expected_rest,
                expected_constraints=expected_constraints,
            )
            require(
                not any(
                    bool(action.get(authored_attack_library.AUTHORED_PREVIEW_PROPERTY, False))
                    for action in bpy.data.actions
                ),
                f"{clip_id} finalization left a preview Action.",
            )
            approved.append(final)
            lifecycle.append(
                {
                    "clipId": clip_id,
                    "kind": final_payload["actionKind"],
                    "fcurveCount": final_report["fcurveCount"],
                    "markers": final_report["markers"],
                }
            )
            settings.authored_attack_preview_weapon = "NONE"

        require(len(approved) == 5, "Acceptance did not finalize all five Actions.")
        require(
            len({action.name for action in approved}) == 5,
            "Approved authored Action names are not unique.",
        )
        portable = portable_round_trip(context, armature, approved)
        require(len(portable) == 5, "Portable round-trip did not cover all five Actions.")
        runtime_audit = runtime_export.audit_runtime_actions(
            damage_authoring._load_state()
        )
        runtime_action_names = {
            action.name for action in runtime_audit["actions"]
        }
        require(
            {action.name for action in approved}.issubset(runtime_action_names),
            "Complete Damage export did not select every approved authored attack.",
        )
        require(
            "DSB_Attack_Overhead_OneHand_v001" not in runtime_action_names,
            "Legacy overhead was not superseded by its approved authored replacement.",
        )
        require_no_bake_transients(
            armature,
            expected_armatures=expected_armatures,
            expected_rest=expected_rest,
            expected_constraints=expected_constraints,
        )
        require(not owned_proxies(), "Portable round-trip left an owned proxy.")
        require(
            source_armature is None or source_armature.hide_viewport or source_armature.hide_get(),
            "Authored preview left SBF_ProductionRig visible beside the runtime rig.",
        )
        require(
            source_armature is None or rest_inventory(source_armature) == source_rest_before,
            "Authored preview changed the source production-rig rest pose.",
        )
    finally:
        authored_attack_library.remove_owned_preview_proxies()
        for socket in created_sockets:
            current = bpy.data.objects.get(socket.name)
            if current is socket:
                bpy.data.objects.remove(current, do_unlink=True)
        require(
            sha256(original) == original_hash,
            "The never-overwrite reference Blend changed during acceptance.",
        )

    report = {
        "status": "PASS",
        "workingCopy": str(active),
        "animationArmature": "DSB_DAMAGE_RIG",
        "sourceArmatureAnimated": False,
        "runtimeAuditActions": sorted(runtime_action_names),
        "rootMotionThrustProbes": root_motion_probes,
        "reference": str(original),
        "referenceSha256Before": original_hash,
        "referenceSha256After": sha256(original),
        "clipCount": len(lifecycle),
        "lifecycle": lifecycle,
        "portableRoundTrip": portable,
        "targetGeometryRequired": False,
        "motionStudioMetadataPresent": False,
        "staleOwnedProxyCount": len(owned_proxies()),
    }
    if options.report is not None:
        report_path = options.report.expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print("AUTHORED_ATTACK_LIBRARY_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
