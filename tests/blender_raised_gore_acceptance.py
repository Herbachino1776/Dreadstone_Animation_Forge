"""Blender runtime acceptance for Forge 3.13 raised surface gore.

Run from a prepared Damage Authoring file that contains the four v001 head
impact deformation keys and valid linked Trauma Field captures/stamps:

    blender prepared.blend --background --python tests/blender_raised_gore_acceptance.py -- --output <folder>

The script builds all heavy gore, exercises attached/detached preview state,
exports the damage GLB/manifest, resets to a clean scene, reimports the GLB,
and writes ``raised_gore_acceptance.json`` in the output folder.
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


HEAD_KEYS = (
    "Head_Impact_Left_v001",
    "Head_Impact_Right_v001",
    "Head_Impact_Front_v001",
    "Head_Impact_Back_v001",
)


def arguments():
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    return parser.parse_args(raw)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    args = arguments()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    settings = bpy.context.scene.daf_settings
    require(bpy.data.filepath, "Open a prepared authoring .blend before running this acceptance script.")
    source_blend = bpy.data.filepath

    deformation_authoring._set_active_region("head", bpy.context)
    registry = deformation_authoring._load_registry()
    region = deformation_authoring._region_record(registry, "head")
    require(region is not None, "The prepared file has no registered head region.")
    attached, detached = deformation_authoring._resolve_region_pair(region)
    payload = deformation_authoring._metadata(attached)
    missing = [name for name in HEAD_KEYS if name not in payload.get("keys", {})]
    require(not missing, "Prepared file is missing head keys: " + ", ".join(missing))
    source_materials_before = {
        obj.name: [slot.material.name if slot.material else "" for slot in obj.material_slots]
        for obj in (attached, detached)
    }

    batch = deformation_authoring.apply_heavy_gore_to_all_deformations(bpy.context)
    require(not batch["failed"], "Batch heavy-gore failures: " + "; ".join(batch["failed"]))
    counts = {}
    preview_checks = {}
    for key_name in HEAD_KEYS:
        deformation_authoring._select_key(settings, key_name)
        key = deformation_authoring._key(attached, key_name)
        key.value = min(1.0, key.slider_max)
        objects = deformation_authoring.generated_gore_objects("head", key_name)
        require(len(objects) == 2, f"{key_name} did not produce attached/detached gore meshes.")
        counts[key_name] = {
            str(obj["dsb_gore_pair_role"]): int(obj["dsb_gore_triangle_count"])
            for obj in objects
        }
        deformation_authoring._set_authoring_view(attached, detached, 'ATTACHED', bpy.context)
        attached_visible = any(
            obj.get("dsb_gore_pair_role") == "ATTACHED" and not obj.hide_get()
            for obj in objects
        )
        deformation_authoring._set_authoring_view(attached, detached, 'DETACHED', bpy.context)
        detached_visible = any(
            obj.get("dsb_gore_pair_role") == "DETACHED" and not obj.hide_get()
            for obj in objects
        )
        preview_checks[key_name] = {
            "attachedVisible": attached_visible,
            "detachedVisible": detached_visible,
        }
        require(attached_visible and detached_visible, f"{key_name} failed paired preview visibility.")

    validation = deformation_authoring.validate_deformations(require_keys=True)
    require(validation["status"] == "PASS", "Raised gore validation failed: " + "; ".join(validation["errors"][:8]))
    deformation_authoring.prepare_for_export()
    source_materials_after = {
        obj.name: [slot.material.name if slot.material else "" for slot in obj.material_slots]
        for obj in (attached, detached)
    }
    require(source_materials_before == source_materials_after, "Source material slots changed during gore generation/export preparation.")

    settings.damage_authoring_output_directory = str(output)
    settings.damage_authoring_filename = "raised_gore_acceptance"
    state = damage_authoring._load_state()
    glb_path, manifest_path, validation_path = damage_authoring._export_asset(bpy.context, settings, state)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    generated = manifest["deformations"].get("generatedGoreMeshes", [])
    expected_names = {obj.name for obj in deformation_authoring.generated_gore_objects()}
    manifest_names = {record["nodeName"] for record in generated}
    require(expected_names == manifest_names, "Export manifest gore-node mapping differs from generated Blender objects.")
    require(all(not record["defaultVisible"] for record in generated), "A gore manifest node is active by default.")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    result = bpy.ops.import_scene.gltf(filepath=str(glb_path))
    require('FINISHED' in result, "Clean-scene GLB import failed.")
    imported_names = {obj.name for obj in bpy.data.objects}
    missing_imports = sorted(expected_names - imported_names)
    require(not missing_imports, "Clean GLB reimport is missing gore nodes: " + ", ".join(missing_imports))
    for node_name in expected_names:
        obj = bpy.data.objects[node_name]
        require(obj.type == 'MESH' and len(obj.data.polygons) > 0, f"Reimported gore node {node_name} is empty.")
        require(len(obj.data.materials) == 3, f"Reimported gore node {node_name} lost its material family.")

    report = {
        "status": "PASS",
        "forgeVersion": "3.13.0",
        "sourceBlend": source_blend,
        "headTriangleCounts": counts,
        "previewChecks": preview_checks,
        "sourceMaterialsPreserved": source_materials_before == source_materials_after,
        "glb": str(glb_path),
        "manifest": str(manifest_path),
        "validation": str(validation_path),
        "manifestGoreNodeCount": len(generated),
        "cleanReimportNodeCount": len(expected_names),
        "defaultInactiveContract": all(not record["defaultVisible"] for record in generated),
    }
    report_path = output / "raised_gore_acceptance.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
