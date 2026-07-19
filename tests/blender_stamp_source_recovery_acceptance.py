"""Blender 5.1 runtime acceptance for old-GLB to fresh-source stamp recovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import damage_authoring, deformation_authoring  # noqa: E402


def fail(message: str) -> None:
    print("STAMP_SOURCE_RECOVERY_FAIL", message)
    raise SystemExit(1)


def require_finished(result, label: str) -> None:
    if 'FINISHED' not in result:
        fail(f"{label} returned {result}")


def portable_recipe_signature(stamps):
    fields = (
        "stampId", "displayName", "enabled", "family", "placementMode",
        "radius", "depth", "falloff", "influenceMode", "distanceMode",
        "featherDistance", "seamProtection", "strength",
        "maximumDisplacement", "orderIndex", "directionMode", "directionLocal",
    )
    return [
        {
            **{field: stamp.get(field) for field in fields},
            "captureCenterLocal": stamp.get("capture", {}).get("centerLocal"),
            "captureNormalLocal": stamp.get("capture", {}).get("normalLocal"),
        }
        for stamp in stamps
    ]


def main() -> None:
    separator = sys.argv.index("--") if "--" in sys.argv else -1
    arguments = sys.argv[separator + 1:] if separator >= 0 else []
    if len(arguments) != 3:
        fail("Pass source GLB, library path, and report output folder after --")
    source_glb = Path(arguments[0]).resolve()
    library_path = Path(arguments[1]).resolve()
    report_folder = Path(arguments[2]).resolve()
    report_folder.mkdir(parents=True, exist_ok=True)

    addon.register()
    _path, saved_library = deformation_authoring.save_stamp_library(library_path)
    expected_recipes = {
        (str(region["regionId"]), str(key["name"])): portable_recipe_signature(key["stamps"])
        for region in saved_library["regions"]
        for key in region["keys"]
    }

    before_import = set(bpy.data.objects)
    require_finished(bpy.ops.import_scene.gltf(filepath=str(source_glb)), "Source GLB import")
    imported = [obj for obj in bpy.data.objects if obj not in before_import]
    imported_meshes = [obj for obj in imported if obj.type == 'MESH']
    if not imported_meshes:
        fail("The original source GLB imported no mesh")
    bpy.ops.object.select_all(action='DESELECT')
    for obj in imported:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = max(imported_meshes, key=lambda obj: len(obj.data.vertices))

    settings = bpy.context.scene.daf_settings
    settings.damage_readiness_output_directory = str(report_folder)
    require_finished(bpy.ops.daf.analyze_damage_readiness(), "Analyze Source Damage Readiness")
    if settings.source_readiness_contract_status != "VALID":
        fail(f"Source readiness contract is {settings.source_readiness_contract_status}")
    if settings.damage_readiness_overall_status != "SOURCE READY":
        fail(f"Source readiness is {settings.damage_readiness_overall_status}")

    settings.damage_authoring_report_path = settings.last_damage_readiness_json_path
    require_finished(bpy.ops.daf.load_damage_readiness_handoff(), "Load READY Handoff")
    require_finished(bpy.ops.daf.build_damage_authoring_asset(), "Build Authoring Asset")
    state = damage_authoring._load_state()
    if not state or "head_neck" not in state.get("seams", {}):
        fail("Fresh Damage Authoring state or head-neck seam is missing")

    registry = deformation_authoring._load_registry()
    if deformation_authoring._region_record(registry, "head") is None:
        fail("Fresh exact-topology head pair was not registered")
    deformation_authoring._set_active_region("head", bpy.context)
    first_key_name = str(saved_library["regions"][0]["keys"][0]["name"])
    attached, detached, _attached_key, _detached_key = deformation_authoring._ensure_key_pair(first_key_name)
    try:
        deformation_authoring.load_stamp_library(library_path, bpy.context)
    except RuntimeError as exc:
        if "never overwrites authored stamp stacks" not in str(exc):
            fail(f"Unexpected conflict error: {exc}")
    else:
        fail("A conflicting existing key was overwritten")
    for key_record in saved_library["regions"][0]["keys"]:
        name = str(key_record["name"])
        if name != first_key_name and deformation_authoring._key(attached, name) is not None:
            fail("Conflict preflight partially created another saved key")
    deformation_authoring._remove_key(attached, first_key_name)
    deformation_authoring._remove_key(detached, first_key_name)
    payload = deformation_authoring._metadata(attached)
    payload.get("keys", {}).pop(first_key_name, None)
    deformation_authoring._store_metadata(attached, detached, payload)

    result = deformation_authoring.load_stamp_library(library_path, bpy.context)
    if result["importedKeyCount"] != 4 or result["stampCount"] != 4:
        fail(f"Unexpected load result: {result}")
    if result["remappedCaptureCount"] != 4:
        fail(f"Expected 4 analytical capture rebindings, got {result['remappedCaptureCount']}")
    if result["validation"]["status"] != "PASS":
        fail("Loaded stamps failed validation: " + "; ".join(result["validation"].get("errors", [])))

    rebuilt_library = deformation_authoring.build_current_stamp_library()
    actual_recipes = {
        (str(region["regionId"]), str(key["name"])): portable_recipe_signature(key["stamps"])
        for region in rebuilt_library["regions"]
        for key in region["keys"]
    }
    if actual_recipes != expected_recipes:
        fail("Fresh-source load changed one or more saved stamp recipes")
    repeated = deformation_authoring.load_stamp_library(library_path, bpy.context)
    if repeated["importedKeyCount"] != 0 or repeated["skippedKeyCount"] != 4:
        fail(f"Repeated load was not an idempotent skip: {repeated}")
    print(
        "STAMP_SOURCE_RECOVERY_PASS",
        json.dumps({
            "source": str(source_glb),
            "library": str(library_path),
            "report": settings.last_damage_readiness_json_path,
            "keyCount": result["importedKeyCount"],
            "stampCount": result["stampCount"],
            "remappedCaptureCount": result["remappedCaptureCount"],
            "repeatedLoadSkippedKeyCount": repeated["skippedKeyCount"],
            "sourceReadiness": settings.source_readiness_contract_status,
            "authoringValidation": result["validation"]["status"],
            "libraryDigest": rebuilt_library["libraryDigest"],
        }, sort_keys=True),
    )


if __name__ == "__main__":
    main()
