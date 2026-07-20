"""Blender 5.1 runtime acceptance for Forge 3.15 core/compound trauma.

This runner intentionally requires a prepared, disposable authoring ``.blend``.
The artist must already have made valid captures/stamps for the body-front,
body-side, left-forearm, right-forearm, and compound child keys; the script does
not fabricate anatomical selections.

    blender prepared.blend --background --python tests/blender_core_compound_guard_acceptance.py -- --output <folder>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import damage_authoring, deformation_authoring  # noqa: E402


ACCEPTANCE_KEYS = {
    "body_core": ("Body_Impact_Front_v001", "Body_Impact_Left_v001"),
    "forearm_left": ("Forearm_L_Impact_Outer_v001",),
    "forearm_right": ("Forearm_R_Impact_Outer_v001",),
}


def arguments():
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--event-id", default="Neck_Shoulder_Crush_Left")
    return parser.parse_args(raw)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def require_prepared_key(registry, region_id, key_name):
    region = deformation_authoring._region_record(registry, region_id)
    require(region is not None, f"Prepared file has no registered {region_id!r} region.")
    target, detached = deformation_authoring._resolve_region_pair(region)
    entry = deformation_authoring._metadata(target).get("keys", {}).get(key_name)
    require(entry is not None, f"Prepared file is missing {region_id}/{key_name}.")
    require(entry.get("stamps"), f"Prepared key {region_id}/{key_name} has no artist-authored stamp/capture.")
    return region, target, detached, entry


def rebuild_prepared_keys(context, registry):
    rebuilt = []
    for region_id, key_names in ACCEPTANCE_KEYS.items():
        for key_name in key_names:
            require_prepared_key(registry, region_id, key_name)
            deformation_authoring._set_active_region(region_id, context)
            deformation_authoring._select_key(context.scene.daf_settings, key_name)
            result = deformation_authoring.rebuild_active_deformation(context)
            rebuilt.append({"regionId": region_id, "key": key_name, "stampCount": result["stampCount"]})
    return rebuilt


def triangle_counts(registry):
    result = {}
    for region_id, key_names in ACCEPTANCE_KEYS.items():
        region = deformation_authoring._region_record(registry, region_id)
        target, _detached = deformation_authoring._resolve_region_pair(region)
        payload = deformation_authoring._metadata(target)
        for key_name in key_names:
            counts = payload["keys"][key_name].get("goreTriangleCounts", {})
            require(counts, f"{region_id}/{key_name} has no raised-gore triangle counts.")
            result[f"{region_id}/{key_name}"] = {str(role): int(value) for role, value in counts.items()}
    return result


def imported_morph_names(obj):
    keys = getattr(getattr(obj, "data", None), "shape_keys", None)
    return {block.name for block in keys.key_blocks} if keys else set()


def main():
    args = arguments()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    context = bpy.context
    settings = context.scene.daf_settings
    require(bpy.data.filepath, "Open a prepared authoring .blend before running acceptance.")
    source_blend = bpy.data.filepath

    registry = deformation_authoring._load_registry()
    body = deformation_authoring._region_record(registry, "body_core")
    require(body is not None, "Register DSB_BODY_CORE explicitly as region 'body_core'.")
    require(body.get("regionMode") == "CORE_SINGLE", "body_core is not explicitly CORE_SINGLE.")
    require(body.get("targetObject") == "DSB_BODY_CORE", "body_core targets the wrong prepared mesh.")
    for region_id in ("head", "forearm_left", "forearm_right"):
        region = deformation_authoring._region_record(registry, region_id)
        require(region is not None and region.get("regionMode") == "PAIRED_SEGMENT", f"{region_id} is not a prepared pair.")

    rebuilt = rebuild_prepared_keys(context, registry)
    deformation_authoring.select_compound_event(context, args.event_id)
    compound = deformation_authoring.rebuild_compound_event(context)
    require(len(compound["participants"]) >= 2, "Compound event has fewer than two participants.")
    require("head" in {item["regionId"] for item in compound["participants"]}, "Compound event does not include head.")
    require("body_core" in {item["regionId"] for item in compound["participants"]}, "Compound event does not include body_core.")

    batch = deformation_authoring.apply_heavy_gore_to_all_deformations(context)
    require(not batch["failed"], "Batch heavy-gore failures: " + "; ".join(batch["failed"]))
    compound = deformation_authoring.rebuild_compound_event(context)
    deformation_validation = deformation_authoring.validate_deformations(require_keys=True)
    require(
        deformation_validation["status"] == "PASS",
        "Core/compound validation failed: " + "; ".join(deformation_validation["errors"][:10]),
    )
    counts = triangle_counts(deformation_authoring._load_registry())

    seam = next((item for item in compound.get("seamContinuity", []) if item.get("seamId") == "head_neck"), None)
    require(seam is not None, "Compound event has no measured head_neck seam-continuity record.")
    require(not seam.get("topologyMutated", True), "Compound seam reports destructive topology mutation.")
    require(
        float(seam["maximumMismatchAfter"]) <= float(seam["tolerance"]),
        "Compound head_neck mismatch exceeds tolerance.",
    )
    preview = deformation_authoring.preview_compound_event(context, 1.0)
    require(preview["participantCount"] >= 2, "Full compound preview did not activate all participants.")
    restored_count = deformation_authoring.clear_compound_preview(context)
    require(restored_count == preview["participantCount"], "Compound preview did not restore every previous value.")

    guards = addon.generate_all_mace_guard_actions(context)
    guard_validation = addon.validate_all_mace_guard_actions(context)
    require(guard_validation["status"] == "PASS", "Mace guard validation failed: " + "; ".join(guard_validation["errors"][:10]))
    guard_markers = {
        action.name: {marker.name: int(marker.frame) for marker in action.pose_markers}
        for action in guards
    }
    approved_guards = [addon.approve_draft_action(context, kind) for kind in addon.MACE_GUARD_VARIANTS]

    settings.pack_output_directory = str(output)
    settings.pack_filename = "core_compound_guard_animations"
    settings.pack_auto_increment = False
    pack_result = bpy.ops.daf.build_approved_pack()
    require('FINISHED' in pack_result, "Approved Animation Pack export failed.")
    pack_glb = Path(bpy.path.abspath(settings.last_pack_path)).resolve()
    pack_manifest = pack_glb.with_suffix(".json")
    pack_validation = pack_glb.with_name(pack_glb.stem + "_validation.json")
    require(pack_glb.is_file() and pack_manifest.is_file(), "Approved Animation Pack files are missing.")
    pack_validation_payload = json.loads(pack_validation.read_text(encoding="utf-8"))
    require(
        pack_validation_payload.get("status") == "PASS",
        "Approved Animation Pack validation failed: "
        + "; ".join(pack_validation_payload.get("missing_animations", [])[:6]),
    )

    settings.damage_authoring_output_directory = str(output)
    settings.damage_authoring_filename = "core_compound_damage"
    state = damage_authoring._load_state()
    damage_glb, damage_manifest_path, damage_validation_path = damage_authoring._export_asset(context, settings, state)
    damage_glb = Path(damage_glb).resolve()
    damage_manifest_path = Path(damage_manifest_path).resolve()
    damage_manifest = json.loads(damage_manifest_path.read_text(encoding="utf-8"))
    deformation_manifest = damage_manifest["deformations"]
    exported_event = next(
        (item for item in deformation_manifest.get("compoundTraumaEvents", []) if item.get("eventId") == args.event_id),
        None,
    )
    require(exported_event is not None, "Damage manifest is missing the compound event.")
    require(len(exported_event["morphTargets"]) >= 3, "Compound manifest is missing head/body mesh-local morph mappings.")
    require(exported_event["goreNodes"], "Compound manifest is missing participant gore nodes.")
    expected_gore = {item["nodeName"] for item in deformation_manifest.get("generatedGoreMeshes", [])}
    expected_morphs = {
        item["mesh"]: item["morphTarget"]
        for item in exported_event["morphTargets"]
    }
    approved_names = {action.name for action in approved_guards}

    bpy.ops.wm.read_factory_settings(use_empty=True)
    require('FINISHED' in bpy.ops.import_scene.gltf(filepath=str(damage_glb)), "Clean damage GLB reimport failed.")
    imported_objects = {obj.name: obj for obj in bpy.data.objects}
    missing_gore = sorted(expected_gore - set(imported_objects))
    require(not missing_gore, "Clean damage reimport is missing gore nodes: " + ", ".join(missing_gore))
    for node_name in expected_gore:
        obj = imported_objects[node_name]
        require(obj.type == 'MESH' and len(obj.data.polygons) > 0, f"Reimported gore node {node_name} is empty.")
    for mesh_name, morph_name in expected_morphs.items():
        require(mesh_name in imported_objects, f"Clean damage reimport is missing participant mesh {mesh_name}.")
        require(morph_name in imported_morph_names(imported_objects[mesh_name]), f"{mesh_name} lost morph {morph_name}.")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    require('FINISHED' in bpy.ops.import_scene.gltf(filepath=str(pack_glb)), "Clean animation-pack GLB reimport failed.")
    imported_actions = {action.name for action in bpy.data.actions}
    require(approved_names <= imported_actions, "Clean animation reimport is missing approved guard Actions.")

    report = {
        "status": "PASS",
        "forgeVersion": "3.15.1",
        "blenderVersion": bpy.app.version_string,
        "sourceBlend": source_blend,
        "rebuiltPreparedKeys": rebuilt,
        "compoundEventId": args.event_id,
        "compoundParticipantCount": len(compound["participants"]),
        "headBodySeamMismatchAtFullWeight": float(seam["maximumMismatchAfter"]),
        "headBodySeamTolerance": float(seam["tolerance"]),
        "seamTopologyMutated": bool(seam["topologyMutated"]),
        "bodyForearmGoreTriangleCounts": counts,
        "batchHeavyGore": batch,
        "guardDraftMarkers": guard_markers,
        "guardValidation": guard_validation,
        "approvedGuardActions": sorted(approved_names),
        "damageGLB": str(damage_glb),
        "damageManifest": str(damage_manifest_path),
        "damageValidation": str(damage_validation_path),
        "animationPackGLB": str(pack_glb),
        "animationPackManifest": str(pack_manifest),
        "animationPackValidation": str(pack_validation),
        "damageCleanReimport": "PASS",
        "animationCleanReimport": "PASS",
        "userVisualApprovalRequired": [
            "front and side torso capture/anatomical deformation quality",
            "left and right forearm capture/deformation quality",
            "body/forearm clot silhouette, clean gaps, wet/dark variation, and triangle budget",
            "head/body seam appearance at full compound weight",
            "two-arm, left-arm, and right-arm Guard_Active poses and intersections",
            "final damage and animation appearance after clean reimport",
        ],
    }
    report_path = output / "core_compound_guard_acceptance.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
