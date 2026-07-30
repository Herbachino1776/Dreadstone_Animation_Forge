"""Blender 5.1 Progressive Damage Site mechanical/runtime acceptance.

The geometry is deliberately synthetic.  It verifies schema, independently
authored keys, focus/delegation, adjacent preview, midpoint gore replacement,
validation at four animation contexts, leak-free cleanup, manifest output, and
clean GLB reimport; it makes no visual-realism claim.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import bmesh
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon
from dreadstone_animation_forge import deformation_authoring
from dreadstone_animation_forge import progressive_authoring
from dreadstone_animation_forge.deformation import gltf_validation
from dreadstone_animation_forge.deformation import preview_service
from dreadstone_animation_forge.deformation import progressive_sites


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def grid_mesh(name, size=7):
    vertices = []
    faces = []
    for y in range(size):
        for x in range(size):
            vertices.append(
                (
                    (x - (size - 1) * 0.5) * 0.08,
                    (y - (size - 1) * 0.5) * 0.08,
                    0.0,
                )
            )
    for y in range(size - 1):
        for x in range(size - 1):
            a = y * size + x
            faces.append((a, a + 1, a + size + 1, a + size))
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    material = bpy.data.materials.new(name + "_BASE_MATERIAL")
    material.diffuse_color = (0.32, 0.28, 0.24, 1.0)
    mesh.materials.append(material)
    return obj


def select_patch(obj, offset):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    mesh = bmesh.from_edit_mesh(obj.data)
    mesh.faces.ensure_lookup_table()
    for face in mesh.faces:
        face.select = False
    for index in (offset, offset + 1, offset + 6, offset + 7):
        if 0 <= index < len(mesh.faces):
            mesh.faces[index].select = True
    bmesh.update_edit_mesh(obj.data)


def dummy_gore(region_id, key_name, stage_name, triangles):
    mesh = bpy.data.meshes.new(f"GORE_{stage_name}_MESH")
    vertices = []
    faces = []
    for index in range(triangles):
        base = len(vertices)
        x = index * 0.0001
        vertices.extend(
            (
                (x, 0.0, 0.02),
                (x + 0.00005, 0.0, 0.02),
                (x, 0.00005, 0.02),
            )
        )
        faces.append((base, base + 1, base + 2))
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"GORE_{stage_name}", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj["dsb_gore_owned"] = True
    obj["dsb_generated_role"] = deformation_authoring.GORE_OBJECT_ROLE
    obj["dsb_preview_only"] = False
    obj["dsb_gore_region_id"] = region_id
    obj["dsb_gore_deformation_key"] = key_name
    obj["dsb_gore_pair_role"] = "CORE"
    obj["dsb_gore_component"] = "RAISED"
    obj["dsb_gore_mesh_id"] = f"mesh_{stage_name.lower()}"
    obj["dsb_gore_triangle_count"] = triangles
    obj.hide_render = True
    obj.hide_set(True)
    return obj


def inventory():
    state = preview_service.state()
    return {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "previewKeys": sum(
            bool(
                obj.type == "MESH"
                and obj.data.shape_keys
                and obj.data.shape_keys.key_blocks.get(
                    deformation_authoring.PREVIEW_KEY_NAME
                )
            )
            for obj in bpy.data.objects
        ),
        "handlers": sum(
            getattr(handler, "__module__", "").startswith(
                "dreadstone_animation_forge"
            )
            for handler in bpy.app.handlers.depsgraph_update_post
        ),
        "timers": int(state["timerRegistered"]),
        "gore": len(
            deformation_authoring.generated_gore_objects(include_preview=True)
        ),
        "cachedPreviewRecords": int(bool(state["lastResult"])),
    }


def action(name):
    value = bpy.data.actions.new(name)
    value["dsb_test_pose"] = True
    return value


def export_and_reimport(
    target,
    armature,
    gore,
    stains,
    deformation_manifest,
    stage_names,
):
    output = Path(tempfile.mkdtemp(prefix="daf_progression_"))
    glb_path = output / "progressive_site.glb"
    manifest_path = output / "progressive_site.json"
    manifest = {
        "schema": "dreadstone.damage_authoring.v1",
        "glb": glb_path.name,
        "deformations": deformation_manifest,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    target_name = target.name
    gore_names = {obj.name for obj in gore}
    stain_names = {obj.name for obj in stains}
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.mode != "OBJECT" else None
    bpy.ops.object.select_all(action="DESELECT")
    for obj in (target, armature, *gore, *stains):
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = target
    result = bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_extras=True,
        export_morph=True,
        export_animations=True,
    )
    require("FINISHED" in result, "Progressive mechanical GLB export failed.")
    final_glb = gltf_validation.validate_exported_damage_glb(
        glb_path,
        manifest,
    )
    require(
        final_glb["status"] == "PASS",
        "Completed synthetic GLB validation failed: "
        + "; ".join(final_glb["errors"]),
    )
    require(
        final_glb["surfaceStains"]["bindingCount"] == 3,
        "Synthetic GLB does not contain three core-owned stage stains.",
    )
    damaged_json = gltf_validation.load_glb_json(glb_path)
    removed_stain = sorted(stain_names)[0]
    damaged_json["nodes"] = [
        node
        for node in damaged_json.get("nodes", [])
        if str(node.get("name", "")) != removed_stain
    ]
    missing_stain_report = gltf_validation.validate_damage_gltf(
        damaged_json,
        manifest,
    )
    require(
        missing_stain_report["status"] == "FAIL"
        and missing_stain_report["surfaceStains"]["status"] == "FAIL",
        "Completed-GLB validation accepted a deliberately removed stain node.",
    )
    digest = hashlib.sha256(glb_path.read_bytes()).hexdigest()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    imported = bpy.ops.import_scene.gltf(filepath=str(glb_path))
    require("FINISHED" in imported, "Progressive mechanical GLB reimport failed.")
    imported_target = bpy.data.objects.get(target_name)
    require(imported_target is not None, "Clean reimport is missing the target.")
    imported_keys = (
        {key.name for key in imported_target.data.shape_keys.key_blocks}
        if imported_target.data.shape_keys
        else set()
    )
    require(
        set(stage_names) <= imported_keys,
        "Clean reimport is missing Progressive Damage Site morphs.",
    )
    imported_nodes = {obj.name for obj in bpy.data.objects}
    require(
        gore_names <= imported_nodes,
        "Clean reimport is missing detailed-gore stage nodes.",
    )
    require(
        stain_names <= imported_nodes,
        "Clean reimport is missing portable surface-stain stage nodes.",
    )
    imported_stains = {
        name: bpy.data.objects[name]
        for name in stain_names
    }
    for obj in imported_stains.values():
        obj.hide_set(True)
    require(
        not any(not obj.hide_get() for obj in imported_stains.values()),
        "Basis/rest unexpectedly shows a surface stain.",
    )
    site = deformation_manifest["progressiveDamageSites"][0]
    activation_checks = {}
    for stage in site["stages"]:
        for obj in imported_stains.values():
            obj.hide_set(True)
        active_names = {
            binding["nodeName"]
            for binding in stage["surfaceStainBindings"]
        }
        for name in active_names:
            obj = imported_stains[name]
            obj.hide_set(False)
            if obj.data.shape_keys:
                target_key = obj.data.shape_keys.key_blocks.get(
                    stage["deformationKeyName"]
                )
                require(
                    target_key is not None,
                    f"{name} lost its stage morph target.",
                )
                target_key.value = 1.0
        visible = {
            name
            for name, obj in imported_stains.items()
            if not obj.hide_get()
        }
        require(
            visible == active_names,
            f"{stage['stage']} activated the wrong surface stain.",
        )
        activation_checks[stage["stage"]] = sorted(visible)
    return {
        "glb": str(glb_path),
        "manifest": str(manifest_path),
        "sha256": digest,
        "finalGlbValidation": final_glb,
        "missingStainRejected": True,
        "basisHidden": True,
        "stageActivation": activation_checks,
    }


def main():
    addon.register()
    context = bpy.context
    settings = context.scene.daf_settings
    settings.deformation_live_preview = False
    settings.deformation_auto_preview = True
    settings.deformation_preview_quality = "FAST"
    settings.progression_live_preview = False

    target = grid_mesh("PROGRESSION_TARGET")
    registry = deformation_authoring._empty_registry()
    region = deformation_authoring._record_from_core("head", target, "")
    require(region["validationStatus"] == "PASS", "Synthetic core region failed.")
    registry["regions"] = [region]
    registry["activeRegionId"] = "head"
    deformation_authoring._store_registry(registry)
    deformation_authoring._set_active_region("head", context)

    settings.progression_site_name = "Head Left"
    require(
        bpy.ops.daf.new_progressive_site() == {"FINISHED"},
        "Site creation failed.",
    )
    collection, site = progressive_authoring._active_site(context=context)
    original_site_guid = site["siteGuid"]

    authored = {}
    stage_specs = (
        ("LIGHT", "ScratchAlpha", 7, 0.010),
        ("MEDIUM", "BrokenCrescent", 14, 0.020),
        ("HEAVY", "CraterOmega", 21, 0.032),
    )
    for stage_name, artist_name, face_offset, z_delta in stage_specs:
        select_patch(target, face_offset)
        settings.deformation_impact_semantic_name = artist_name
        require(
            bpy.ops.daf.create_impact_from_selection() == {"FINISHED"},
            f"{stage_name} independent key creation failed.",
        )
        settings.deformation_gore_raised_amount = 0.0
        settings.deformation_gore_inlay_amount = 0.0
        settings.deformation_gore_enabled = True
        require(
            bpy.ops.daf.save_vip_damage() == {"FINISHED"},
            f"{stage_name} Save failed.",
        )
        key_name = str(settings.deformation_active_key)
        key = deformation_authoring._key(target, key_name)
        for index, point in enumerate(key.data):
            if index % (4 if stage_name == "LIGHT" else 3 if stage_name == "MEDIUM" else 2) == 0:
                point.co.z -= z_delta
        deformation_authoring.sync_key_to_detached(key_name, "head")
        payload = deformation_authoring._metadata(target)
        entry = payload["keys"][key_name]
        entry["deformationDigestMechanicalEdit"] = True
        deformation_authoring._store_metadata(target, None, payload)
        settings.deformation_impact_dirty = False
        settings.deformation_gore_dirty = False
        require(
            bpy.ops.daf.assign_progressive_stage(stage=stage_name)
            == {"FINISHED"},
            f"{stage_name} assignment failed.",
        )
        authored[stage_name] = {
            "key": key_name,
            "stamp": str(settings.deformation_active_stamp_id),
        }

    original_light_name = authored["LIGHT"]["key"]
    original_light_id = (
        progressive_authoring._active_site(context=context)[1]["stages"][
            "LIGHT"
        ]["damageKeyId"]
    )
    deformation_authoring._select_key(settings, original_light_name)
    rename_result = deformation_authoring.rename_deformation_key(
        context,
        original_light_name,
        "RenamedScratch_v003",
    )
    authored["LIGHT"]["key"] = rename_result["newName"]
    renamed_site = progressive_authoring._active_site(context=context)[1]
    require(
        rename_result["damageKeyId"] == original_light_id
        and renamed_site["stages"]["LIGHT"]["damageKeyId"]
        == original_light_id,
        "Damage Key rename changed the stage's stable identity.",
    )
    require(
        renamed_site["stages"]["LIGHT"]["deformationKeyName"]
        == authored["LIGHT"]["key"],
        "Damage Key rename did not retarget the explicit Light assignment.",
    )
    require(
        deformation_authoring._key(target, original_light_name) is None
        and deformation_authoring._key(
            target,
            authored["LIGHT"]["key"],
        )
        is not None,
        "Damage Key rename did not move the actual shape key.",
    )
    require(
        not renamed_site["enabledForExport"],
        "Damage Key rename did not invalidate the export safety latch.",
    )

    collection, site = progressive_authoring._active_site(context=context)
    require(
        len(
            {
                site["stages"][name]["damageKeyId"]
                for name in progressive_sites.STAGE_ORDER
            }
        )
        == 3,
        "Stages do not own three stable independent Damage Key IDs.",
    )
    require(
        not any(
            token in authored[stage]["key"].upper()
            for stage, token in (
                ("LIGHT", "LIGHT"),
                ("MEDIUM", "MEDIUM"),
                ("HEAVY", "HEAVY"),
            )
        ),
        "Acceptance accidentally relied on stage names.",
    )
    before_failed_assignment = progressive_sites.canonical_digest(
        progressive_authoring._collection()
    )
    deformation_authoring._select_key(settings, authored["LIGHT"]["key"])
    try:
        failed_assignment = bpy.ops.daf.assign_progressive_stage(
            stage="MEDIUM"
        )
    except RuntimeError:
        failed_assignment = {"CANCELLED"}
    require(
        failed_assignment == {"CANCELLED"},
        "Duplicate stage assignment did not fail.",
    )
    require(
        progressive_sites.canonical_digest(
            progressive_authoring._collection()
        )
        == before_failed_assignment,
        "Failed stage assignment changed site metadata.",
    )

    for stage_name in progressive_sites.STAGE_ORDER:
        require(
            bpy.ops.daf.focus_progressive_stage(stage=stage_name)
            == {"FINISHED"},
            f"{stage_name} focus failed.",
        )
        require(
            settings.deformation_active_key == authored[stage_name]["key"],
            f"{stage_name} did not focus its Damage Key.",
        )
        require(
            settings.deformation_active_stamp_id == authored[stage_name]["stamp"],
            f"{stage_name} did not focus its active Stamp.",
        )

    require(
        bpy.ops.daf.focus_progressive_stage(stage="LIGHT") == {"FINISHED"},
        "Could not focus Light for Randomize isolation.",
    )
    before = copy_site = json.loads(
        json.dumps(
            progressive_authoring._active_site(context=context)[1],
            sort_keys=True,
        )
    )
    require(
        bpy.ops.daf.randomize_damage_recipe() == {"FINISHED"},
        "Randomize Damage failed.",
    )
    randomized = progressive_authoring._active_site(context=context)[1]
    require(
        randomized["stages"]["LIGHT"]["dirty"],
        "Randomize did not mark only the active stage dirty.",
    )
    for other in ("MEDIUM", "HEAVY"):
        require(
            randomized["stages"][other] == before["stages"][other],
            f"Randomize modified {other}.",
        )
    require(
        bpy.ops.daf.save_vip_damage() == {"FINISHED"},
        "Saving randomized Light failed.",
    )
    saved = progressive_authoring._active_site(context=context)[1]
    require(saved["stages"]["LIGHT"]["saved"], "Save did not refresh Light.")
    for other in ("MEDIUM", "HEAVY"):
        require(
            saved["stages"][other] == before["stages"][other],
            f"Save overwrote {other}.",
        )

    gore = [
        dummy_gore("head", authored[stage]["key"], stage, triangles)
        for stage, triangles in (("LIGHT", 8), ("MEDIUM", 13), ("HEAVY", 21))
    ]

    settings.progression_severity = 0.0
    require(
        bpy.ops.daf.refresh_progression_preview(with_other_damage=False)
        == {"FINISHED"},
        "Basis progression preview failed.",
    )
    require(
        settings.progression_weight_light == 0.0
        and settings.progression_weight_medium == 0.0
        and settings.progression_weight_heavy == 0.0,
        "Severity zero did not produce Basis.",
    )
    require(not any(not obj.hide_get() for obj in gore), "Basis showed stage gore.")
    bpy.ops.daf.clear_progression_preview()

    for sample in progressive_sites.transition_samples():
        settings.progression_severity = sample["severity"] * 100.0
        require(
            bpy.ops.daf.refresh_progression_preview(with_other_damage=False)
            == {"FINISHED"},
            f"Preview failed at {sample}.",
        )
        weights = (
            settings.progression_weight_light,
            settings.progression_weight_medium,
            settings.progression_weight_heavy,
        )
        require(
            sum(value > 1e-8 for value in weights) <= 2,
            "Three stage morphs became active.",
        )
        require(sum(weights) <= 1.0 + 1e-8, "Stage weights exceeded 1.0.")
        visible_gore = [obj for obj in gore if not obj.hide_get()]
        expected_gore = progressive_sites.detailed_gore_stage(
            sample["severity"]
        )
        require(
            len(visible_gore) == (0 if expected_gore is None else 1),
            (
                "Detailed stage gore stacked during a transition: "
                f"sample={sample}, expected={expected_gore}, "
                f"visible={[obj.name for obj in visible_gore]}, "
                f"state={deformation_authoring._damage_preview_state(context)}"
            ),
        )
        if expected_gore is not None:
            require(
                visible_gore[0].name == f"GORE_{expected_gore}",
                "Midpoint replacement selected the wrong detailed gore stage.",
            )
        bpy.ops.daf.clear_progression_preview()

    stable_inventory = inventory()
    for index in range(50):
        settings.progression_severity = (index % 11) * 10.0
        progressive_authoring.refresh_progression_preview(context)
        progressive_authoring.clear_progression_preview(context)
    require(
        inventory() == stable_inventory,
        f"50 preview/clear cycles leaked resources: {stable_inventory} -> {inventory()}",
    )

    armature_data = bpy.data.armatures.new("PROGRESSION_RIG_DATA")
    armature = bpy.data.objects.new("PROGRESSION_RIG", armature_data)
    context.scene.collection.objects.link(armature)
    modifier = target.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature
    armature.animation_data_create()
    pose_actions = [
        action("Forge_Walk_Test"),
        action("Forge_Hurt_Test"),
        action("Forge_Collapse_Death_Test"),
    ]
    armature.animation_data.action = pose_actions[0]
    context.scene.frame_set(17)
    for stage_name in progressive_sites.STAGE_ORDER:
        progressive_authoring.focus_stage(context, stage_name)
        progressive_authoring.sync_active_stage_after_save(context)

    report = progressive_authoring.validate_site(context, original_site_guid)
    require(
        report["status"] == "PASS",
        "Full site validation failed: " + "; ".join(report["errors"][:6]),
    )
    require(report["sampleCount"] == 60, "Validation did not test 15 samples at 4 poses.")
    require(
        {record["pose"] for record in report["animationPoseResults"]}
        == {"REST_OR_CURRENT", "WALK", "HURT", "COLLAPSE_DEATH"},
        "Animation pose coverage is incomplete.",
    )
    require(context.scene.frame_current == 17, "Validation did not restore the frame.")
    require(
        armature.animation_data.action == pose_actions[0],
        "Validation did not restore the active Action.",
    )
    require(
        bpy.ops.daf.enable_progressive_site_export() == {"FINISHED"},
        "Validate + Enable Site for Export failed.",
    )
    site = progressive_authoring._active_site(context=context)[1]
    require(site["enabledForExport"], "Site was not export enabled.")

    manifest = deformation_authoring.get_deformation_manifest()
    require(
        len(manifest["progressiveDamageSites"]) == 1,
        "Manifest omitted the valid export-enabled site.",
    )
    site_manifest = manifest["progressiveDamageSites"][0]
    require(
        site_manifest["stageOrder"] == ["LIGHT", "MEDIUM", "HEAVY"],
        "Manifest stage order is not explicit.",
    )
    require(
        not site_manifest["activationContract"]["detailedGoreStagesStack"],
        "Manifest permits detailed stage gore stacking.",
    )
    cost = site_manifest["cost"]
    require(cost["residentStageGoreTriangles"] == 42, "Resident cost is wrong.")
    require(cost["maximumVisibleStageGoreTriangles"] == 21, "Visible cost is wrong.")
    require(cost["maximumTransitionGoreTriangles"] == 21, "Transition cost sums gore.")

    require(
        bpy.ops.daf.unassign_progressive_stage(stage="MEDIUM")
        == {"FINISHED"},
        "Stage unassignment failed.",
    )
    require(
        deformation_authoring._key(target, authored["MEDIUM"]["key"]) is not None,
        "Stage unassignment deleted the Damage Key.",
    )
    deformation_authoring._select_key(settings, authored["MEDIUM"]["key"])
    require(
        bpy.ops.daf.assign_progressive_stage(stage="MEDIUM") == {"FINISHED"},
        "Stage reassignment failed.",
    )
    settings.deformation_impact_dirty = False
    settings.deformation_gore_dirty = False
    progressive_authoring.sync_active_stage_after_save(context)
    progressive_authoring.validate_site(context, original_site_guid)
    progressive_authoring.enable_site_for_export(context)

    require(
        bpy.ops.daf.duplicate_progressive_site_metadata() == {"FINISHED"},
        "Metadata duplication failed.",
    )
    draft = progressive_authoring._active_site(context=context)[1]
    require(
        not any(
            value["damageKeyId"] for value in draft["stages"].values()
        ),
        "Metadata duplication reused assigned Damage Keys.",
    )
    draft_manifest = deformation_authoring.get_deformation_manifest()
    require(
        len(draft_manifest["progressiveDamageSites"]) == 1,
        "Incomplete draft site changed the runtime manifest: "
        + json.dumps(
            {
                "exported": [
                    value["siteGuid"]
                    for value in draft_manifest["progressiveDamageSites"]
                ],
                "warnings": draft_manifest[
                    "progressiveDamageSiteWarnings"
                ],
            },
            sort_keys=True,
        ),
    )
    require(
        any(
            warning["siteGuid"] == draft["siteGuid"]
            for warning in draft_manifest[
                "progressiveDamageSiteWarnings"
            ]
        ),
        "Omitted incomplete draft site did not produce a clear warning.",
    )
    require(
        bpy.ops.daf.delete_progressive_site_metadata() == {"FINISHED"},
        "Site metadata deletion failed.",
    )
    for value in authored.values():
        require(
            deformation_authoring._key(target, value["key"]) is not None,
            "Site deletion deleted artist-owned Damage Keys.",
        )
    progressive_authoring.select_site(context, original_site_guid)

    stains = deformation_authoring.build_surface_stain_export_artifacts()
    final_manifest = deformation_authoring.get_deformation_manifest()
    final_site = final_manifest["progressiveDamageSites"][0]
    require(
        [
            stage["deformationKeyName"]
            for stage in final_site["stages"]
        ]
        == [
            authored[stage]["key"]
            for stage in progressive_sites.STAGE_ORDER
        ],
        "Portable stain mapping inferred stage order instead of preserving assignments.",
    )
    require(
        all(
            stage["surfaceStainBindings"]
            for stage in final_site["stages"]
        ),
        "A progressive stage has no stage-owned surface-stain binding.",
    )
    export = export_and_reimport(
        target,
        armature,
        gore,
        stains,
        final_manifest,
        [value["key"] for value in authored.values()],
    )
    print(
        "PROGRESSIVE_DAMAGE_SITE_ACCEPTANCE="
        + json.dumps(
            {
                "status": "PASS",
                "siteGuid": original_site_guid,
                "stageKeys": authored,
                "previewSamples": 15,
                "animationSamples": report["sampleCount"],
                "previewCycles": 50,
                "cost": cost,
                "export": export,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
