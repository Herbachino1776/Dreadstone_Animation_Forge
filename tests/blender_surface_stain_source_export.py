"""Guarded v002 migration/export for the supplied Dreadguard authoring Blend."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import damage_authoring  # noqa: E402
from dreadstone_animation_forge import deformation_authoring  # noqa: E402
from dreadstone_animation_forge import progressive_authoring  # noqa: E402


SOURCE = Path(r"D:\Blender\Blends\Untitled2.blend")
BACKUP = Path(
    r"D:\Blender\Blends\Untitled2_pre_portable_stain_v002.blend"
)
OUTPUT = Path(r"D:\AI aRt\Models\damage testing")
OLD_LIGHT = "Left_Head_Impact_v002_Copy_v001"
EXPECTED_STAGE_KEYS = {
    "LIGHT": "Left_Head_Impact_v003",
    "MEDIUM": "Left_Head_Impact_v002",
    "HEAVY": "Left_Head_Impact_v001",
}
V001_NAMES = (
    "dreadguard_damage_v001.glb",
    "dreadguard_damage_v001.json",
    "dreadguard_damage_v001_validation.json",
)
V002_NAMES = (
    "dreadguard_damage_v002.glb",
    "dreadguard_damage_v002.json",
    "dreadguard_damage_v002_validation.json",
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    refresh_v002 = "--refresh-v002" in sys.argv
    require(
        Path(bpy.data.filepath).resolve() == SOURCE.resolve(),
        f"Open the supplied source Blend: {SOURCE}",
    )
    existing_v002 = [
        name for name in V002_NAMES if (OUTPUT / name).exists()
    ]
    v001_before = {}
    for name in V001_NAMES:
        path = OUTPUT / name
        require(path.is_file(), f"Existing v001 artifact is missing: {path}")
        v001_before[name] = sha256(path)

    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    context = bpy.context
    settings = context.scene.daf_settings
    deformation_authoring._set_active_region("head", context)
    collection, site = progressive_authoring._active_site(context=context)
    saved_light = site["stages"]["LIGHT"]["deformationKeyName"]
    require(
        saved_light in {OLD_LIGHT, EXPECTED_STAGE_KEYS["LIGHT"]},
        "Saved Light assignment is neither the authorized duplicate nor "
        "the already-migrated v003 key.",
    )
    if saved_light == OLD_LIGHT:
        require(
            not BACKUP.exists(),
            f"Backup target already exists before migration: {BACKUP}",
        )
        require(
            not existing_v002,
            "Refusing to overwrite an existing v002 during first migration: "
            + ", ".join(existing_v002),
        )
    else:
        require(
            refresh_v002,
            "Source is already migrated; pass --refresh-v002 to replace only "
            "the previously generated v002 bundle.",
        )
        require(
            BACKUP.is_file(),
            "The pre-migration backup is missing.",
        )
    for stage_name in ("MEDIUM", "HEAVY"):
        require(
            site["stages"][stage_name]["deformationKeyName"]
            == EXPECTED_STAGE_KEYS[stage_name],
            f"Saved {stage_name} assignment does not match the required mapping.",
        )
    light_id = site["stages"]["LIGHT"]["damageKeyId"]

    if saved_light == OLD_LIGHT:
        copy_result = bpy.ops.wm.save_as_mainfile(
            filepath=str(BACKUP),
            copy=True,
            compress=True,
        )
        require(
            "FINISHED" in copy_result and BACKUP.is_file(),
            "Could not create the pre-migration Blend backup.",
        )
        require(
            Path(bpy.data.filepath).resolve() == SOURCE.resolve(),
            "Backup operation unexpectedly changed the active Blend path.",
        )
        deformation_authoring._select_key(settings, OLD_LIGHT)
        rename = deformation_authoring.rename_deformation_key(
            context,
            OLD_LIGHT,
            EXPECTED_STAGE_KEYS["LIGHT"],
        )
    else:
        deformation_authoring._select_key(
            settings,
            EXPECTED_STAGE_KEYS["LIGHT"],
        )
        rename = {
            "changed": False,
            "damageKeyId": light_id,
            "newName": EXPECTED_STAGE_KEYS["LIGHT"],
            "oldName": EXPECTED_STAGE_KEYS["LIGHT"],
            "regionId": "head",
            "renamedStageCount": 0,
            "renamedCompoundParticipantCount": 0,
            "rebuiltGoreNodeNames": [],
        }
    require(
        rename["damageKeyId"] == light_id,
        "The Light rename changed its stable Damage Key identity.",
    )
    site = progressive_authoring._active_site(context=context)[1]
    actual_mapping = {
        name: site["stages"][name]["deformationKeyName"]
        for name in ("LIGHT", "MEDIUM", "HEAVY")
    }
    require(
        actual_mapping == EXPECTED_STAGE_KEYS,
        f"Post-rename stage mapping is wrong: {actual_mapping}",
    )
    if rename["changed"]:
        require(
            not site["enabledForExport"],
            "Rename did not invalidate the export safety latch.",
        )

    validation = progressive_authoring.validate_site(
        context,
        site["siteGuid"],
    )
    require(
        validation["status"] == "PASS",
        "Progressive validation failed: "
        + "; ".join(validation.get("errors", [])[:8]),
    )
    enabled = progressive_authoring.enable_site_for_export(context)
    require(
        enabled["enabledForExport"],
        "The valid progressive site could not be enabled for export.",
    )

    settings.damage_authoring_output_directory = str(OUTPUT)
    settings.damage_authoring_filename = "dreadguard_damage_v002"
    state = damage_authoring._load_state()
    glb_path, manifest_path, validation_path = damage_authoring._export_asset(
        context,
        settings,
        state,
    )
    output_paths = tuple(
        Path(value).resolve()
        for value in (glb_path, manifest_path, validation_path)
    )
    require(
        tuple(path.name for path in output_paths) == V002_NAMES,
        f"Exporter wrote unexpected filenames: {output_paths}",
    )

    manifest = json.loads(output_paths[1].read_text(encoding="utf-8"))
    report = json.loads(output_paths[2].read_text(encoding="utf-8"))
    sites = manifest["deformations"]["progressiveDamageSites"]
    require(len(sites) == 1, "v002 manifest does not contain exactly one site.")
    exported_mapping = {
        stage["stage"]: stage["deformationKeyName"]
        for stage in sites[0]["stages"]
    }
    require(
        exported_mapping == EXPECTED_STAGE_KEYS,
        f"Exported stage mapping is wrong: {exported_mapping}",
    )
    for stage in sites[0]["stages"]:
        roles = {
            binding["ownershipRole"]
            for binding in stage["surfaceStainBindings"]
        }
        require(
            roles == {"ATTACHED", "DETACHED"},
            f"{stage['stage']} stain ownership is incomplete: {roles}",
        )
        require(
            all(
                binding["deformationKey"]
                == stage["deformationKeyName"]
                for binding in stage["surfaceStainBindings"]
            ),
            f"{stage['stage']} stain binding targets the wrong Damage Key.",
        )
    require(
        report["status"] == "PASS"
        and report["finalGlb"]["status"] == "PASS"
        and report["surfaceStains"]["status"] == "PASS"
        and report["raisedGoreGeometry"]["status"] == "PASS",
        "v002 completed-GLB validation did not pass.",
    )
    require(
        all(
            sha256(OUTPUT / name) == digest
            for name, digest in v001_before.items()
        ),
        "The existing v001 bundle changed during v002 export.",
    )

    save_result = bpy.ops.wm.save_mainfile()
    require(
        "FINISHED" in save_result,
        "The corrected source Blend could not be saved.",
    )

    stain_names = {
        binding["nodeName"]
        for stage in sites[0]["stages"]
        for binding in stage["surfaceStainBindings"]
    }
    gore_names = {
        record["nodeName"]
        for record in manifest["deformations"]["generatedGoreMeshes"]
    }
    bpy.ops.wm.read_factory_settings(use_empty=True)
    imported = bpy.ops.import_scene.gltf(filepath=str(output_paths[0]))
    require("FINISHED" in imported, "Clean v002 GLB reimport failed.")
    imported_names = {obj.name for obj in bpy.data.objects}
    require(
        stain_names <= imported_names,
        "Clean reimport is missing stain nodes: "
        + ", ".join(sorted(stain_names - imported_names)),
    )
    require(
        gore_names <= imported_names,
        "Clean reimport is missing raised/inlay nodes: "
        + ", ".join(sorted(gore_names - imported_names)),
    )
    for node_name in stain_names:
        obj = bpy.data.objects[node_name]
        require(
            obj.type == "MESH"
            and len(obj.data.polygons) > 0
            and len(obj.data.materials) == 1,
            f"Reimported stain node is incomplete: {node_name}",
        )

    result = {
        "status": "PASS",
        "sourceBlend": str(SOURCE),
        "backupBlend": str(BACKUP),
        "rename": rename,
        "stageMapping": exported_mapping,
        "progressiveValidation": validation["status"],
        "exportEnabled": True,
        "glb": str(output_paths[0]),
        "manifest": str(output_paths[1]),
        "validation": str(output_paths[2]),
        "glbSha256": sha256(output_paths[0]),
        "surfaceStainNodeCount": len(stain_names),
        "raisedGoreNodeCount": len(gore_names),
        "cleanReimport": "PASS",
        "v001Preserved": True,
    }
    print(
        "DREADGUARD_SURFACE_STAIN_V002="
        + json.dumps(result, sort_keys=True)
    )


if __name__ == "__main__":
    main()
