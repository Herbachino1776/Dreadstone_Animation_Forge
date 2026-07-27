"""Blender 5.1.2 acceptance for the Impact Pedal and compact control deck.

Run from the repository root:

    blender --background --factory-startup --python tests/blender_impact_pedal_acceptance.py
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bmesh
import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import deformation_authoring, parameter_schema, trauma_field  # noqa: E402
from dreadstone_animation_forge.deformation import preview_service  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def grid_mesh(name, *, width=11, height=11, spacing=0.012, x_offset=0.0):
    vertices = [
        (x_offset + x * spacing, y * spacing, 0.0)
        for y in range(height)
        for x in range(width)
    ]
    faces = []
    for y in range(height - 1):
        for x in range(width - 1):
            first = y * width + x
            faces.append((first, first + 1, first + width + 1, first + width))
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.shape_key_add(name="Basis")
    return obj


def pair_mesh(name, x_offset):
    attached = grid_mesh(name + "_ATTACHED", x_offset=x_offset)
    detached = bpy.data.objects.new(name + "_DETACHED", attached.data.copy())
    bpy.context.scene.collection.objects.link(detached)
    detached.shape_key_add(name="Basis")
    return attached, detached


def activate_and_select(region_id, obj, *, select=True):
    deformation_authoring._set_active_region(region_id, bpy.context)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    mesh = bmesh.from_edit_mesh(obj.data)
    mesh.faces.ensure_lookup_table()
    for face in mesh.faces:
        face.select = False
    if select:
        center = len(mesh.faces) // 2
        for index in (center, center + 1, center + 10, center + 11):
            if 0 <= index < len(mesh.faces):
                mesh.faces[index].select = True
    bmesh.update_edit_mesh(obj.data)


def coordinate_digest(key):
    digest = hashlib.sha256()
    for point in key.data:
        digest.update(struct.pack("<3d", float(point.co.x), float(point.co.y), float(point.co.z)))
    return digest.hexdigest()


def endpoint_values(contract):
    if contract.integer:
        return tuple(dict.fromkeys(int(round(value)) for value in (
            contract.hard_min, contract.soft_min, contract.default,
            (float(contract.hard_min) + float(contract.hard_max)) * 0.5,
            contract.soft_max, contract.hard_max,
        )))
    minimum = float(contract.hard_min)
    maximum = float(contract.hard_max)
    return (
        minimum, math.nextafter(minimum, maximum), float(contract.soft_min),
        float(contract.default), (minimum + maximum) * 0.5,
        float(contract.soft_max), math.nextafter(maximum, minimum), maximum,
    )


def main():
    addon.register()
    context = bpy.context
    settings = context.scene.daf_settings
    settings.deformation_live_preview = False
    settings.deformation_auto_preview = True
    settings.deformation_preview_quality = 'FAST'
    settings.deformation_default_heavy_gore = False

    head, head_detached = pair_mesh("PEDAL_HEAD", 0.0)
    body = grid_mesh("PEDAL_BODY", x_offset=0.4)
    forearm, forearm_detached = pair_mesh("PEDAL_FOREARM", 0.8)
    registry = deformation_authoring._empty_registry()
    regions = [
        deformation_authoring._record_from_pair("head", head, head_detached, ""),
        deformation_authoring._record_from_core("body_core", body, ""),
        deformation_authoring._record_from_pair("forearm_left", forearm, forearm_detached, ""),
    ]
    require(all(region["validationStatus"] == "PASS" for region in regions), "Synthetic region contract failed.")
    registry["regions"] = regions
    registry["activeRegionId"] = "head"
    deformation_authoring._store_registry(registry)

    targets = {
        "head": head,
        "body_core": body,
        "forearm_left": forearm,
    }
    families = tuple(trauma_field.TRAUMA_FAMILIES)
    created = []
    for index, family in enumerate(families):
        region_id = ("head", "body_core", "forearm_left")[index % 3]
        target = targets[region_id]
        settings.deformation_stamp_family = family
        settings.deformation_impact_intensity = ('LIGHT', 'MEDIUM', 'HEAVY')[index % 3]
        settings.deformation_impact_semantic_name = f"{region_id}_{family}"
        activate_and_select(region_id, target)
        result = bpy.ops.daf.create_impact_from_selection()
        require(result == {'FINISHED'}, f"Create Impact failed for {region_id}/{family}: {result}")
        created.append((region_id, settings.deformation_active_key, settings.deformation_active_stamp_id))
        require(settings.deformation_impact_control_mode == 'MACRO', "New impact was not in MACRO mode.")
        require(settings.deformation_preview_status == 'READY', "Create Impact did not generate FAST preview.")
        require(settings.deformation_preview_affected_vertices > 0, "Create Impact preview affected no vertices.")

    # A forced invalid empty selection must roll back without adding a key.
    region_id, _, _ = created[-1]
    target = targets[region_id]
    before_names = set(deformation_authoring._metadata(target).get("keys", {}))
    activate_and_select(region_id, target, select=False)
    try:
        failed = bpy.ops.daf.create_impact_from_selection()
    except RuntimeError:
        failed = {'CANCELLED'}
    require(failed == {'CANCELLED'}, "Empty selection did not cancel atomic Create Impact.")
    after_names = set(deformation_authoring._metadata(target).get("keys", {}))
    require(before_names == after_names, "Forced Create Impact failure leaked a key.")
    bpy.ops.object.mode_set(mode='OBJECT')

    # Repeated key/stamp switching must restore each recipe mode and active stamp.
    for region_id, key_name, stamp_id in created * 2:
        deformation_authoring._set_active_region(region_id, context)
        deformation_authoring._select_key(settings, key_name)
        require(settings.deformation_active_stamp_id == stamp_id, f"Stamp switch failed for {key_name}.")
        result = bpy.ops.daf.select_trauma_stamp(stamp_id=stamp_id)
        require(result == {'FINISHED'}, f"Stamp operator failed for {key_name}.")

    # Macro endpoint changes issue one generation request per property assignment.
    settings.deformation_live_preview = False
    generation_checks = 0
    for identifier in parameter_schema.MACRO_IDENTIFIERS:
        for level in (0.0, 25.0, 50.0, 75.0, 100.0):
            before = int(preview_service.state()["generation"])
            setattr(settings, identifier, level)
            after = int(preview_service.state()["generation"])
            require(after == before + 1, f"{identifier} scheduled {after - before} preview requests.")
            generation_checks += 1
    require(settings.deformation_seed_depth > 0.0, "CRUSH 100 did not produce physical depth.")

    # Twenty primary seed randomizations remain valid, distinct, and leak-free.
    seeds = []
    for _index in range(20):
        before = int(preview_service.state()["generation"])
        result = bpy.ops.daf.randomize_impact_seed()
        after = int(preview_service.state()["generation"])
        require(result == {'FINISHED'}, "Top-deck Randomize Seed failed.")
        require(after == before + 1, "Randomize Seed did not issue exactly one preview request.")
        seeds.append(int(settings.deformation_impact_seed))
        require(not preview_service.state()["timerRegistered"], "Seed randomization leaked a preview timer.")
    require(len(set(seeds)) == 20, "Randomize Seed repeated a seed in the 20-seed acceptance sweep.")

    # Explicit top-deck preview works even with live preview disabled and is deterministic.
    settings.deformation_impact_chaos = 65.0
    settings.deformation_impact_crush = 60.0
    preview_result = bpy.ops.daf.refresh_impact_preview()
    require(preview_result == {'FINISHED'}, "Top-deck Generate / Refresh Preview failed.")
    target = targets[deformation_authoring._active_region_id(context)]
    first_digest = coordinate_digest(deformation_authoring._key(target, deformation_authoring.PREVIEW_KEY_NAME))
    preview_result = bpy.ops.daf.refresh_impact_preview()
    second_digest = coordinate_digest(deformation_authoring._key(target, deformation_authoring.PREVIEW_KEY_NAME))
    require(first_digest == second_digest, "Same seed/macros produced a different preview.")

    # Commit stores additive metadata; Randomize + Revert restores the committed seed/result.
    committed_seed = int(settings.deformation_impact_seed)
    commit_result = bpy.ops.daf.commit_impact()
    require(commit_result == {'FINISHED'}, "Top-deck Commit / Save Impact failed.")
    require(not settings.deformation_impact_dirty, "Commit left the Impact Pedal dirty.")
    active_entry = deformation_authoring._metadata(target)["keys"][settings.deformation_active_key]
    require(active_entry["impactControl"]["seed"] == committed_seed, "Commit did not store the master impact seed.")
    require(active_entry["impactControl"]["schema"] == parameter_schema.IMPACT_CONTROL_SCHEMA, "Impact metadata schema is missing.")
    bpy.ops.daf.randomize_impact_seed()
    require(settings.deformation_impact_seed != committed_seed, "Randomize Seed did not change the committed seed.")
    revert_result = bpy.ops.daf.revert_impact()
    require(revert_result == {'FINISHED'}, "Revert failed.")
    require(settings.deformation_impact_seed == committed_seed, "Revert did not restore the committed seed.")

    # The adjacent top Gore Control Deck completes the same no-scroll loop.
    settings.deformation_live_preview = False
    settings.deformation_auto_preview = True
    settings.deformation_preview_quality = "BALANCED"
    with preview_service.suspend_updates():
        settings.deformation_gore_enabled = True
        settings.deformation_gore_identity = "BLOODY_CRATER"
        settings.deformation_gore_preset = "Gore_Bloody_Crater"
    deformation_authoring.apply_gore_preset_to_settings(context)
    require(
        bpy.ops.daf.update_surface_gore_overlay() == {'FINISHED'},
        "Gore deck could not link its recipe to the active capture.",
    )
    gore_macros = tuple(
        float(getattr(settings, name))
        for name in parameter_schema.GORE_MACRO_IDENTIFIERS
    )
    gore_seeds = []
    for _index in range(20):
        transaction_before = int(settings.deformation_gore_transaction_count)
        generation_before = int(preview_service.state()["generation"])
        require(
            bpy.ops.daf.randomize_gore_seed() == {'FINISHED'},
            "Top-deck Randomize Gore Seed failed.",
        )
        require(
            int(settings.deformation_gore_transaction_count) == transaction_before + 1,
            "Randomize Gore Seed did not make exactly one dirty transition.",
        )
        require(
            int(preview_service.state()["generation"]) == generation_before + 1,
            "Randomize Gore Seed did not request exactly one managed preview.",
        )
        require(
            tuple(float(getattr(settings, name)) for name in parameter_schema.GORE_MACRO_IDENTIFIERS)
            == gore_macros,
            "Randomize Gore Seed changed a Gore Pedal macro.",
        )
        gore_seeds.append(int(settings.deformation_gore_mask_seed))
    require(len(set(gore_seeds)) == 20, "Gore seed sweep repeated a seed.")
    require(
        bpy.ops.daf.generate_gore_preview() == {'FINISHED'},
        "Top-deck Generate / Rebuild Gore Preview failed.",
    )
    require(
        deformation_authoring.preview_gore_objects(),
        "BALANCED Gore preview did not create preview-only feedback.",
    )
    require(
        bpy.ops.daf.final_gore_preview() == {'FINISHED'},
        "Top-deck Final Gore Preview failed.",
    )
    require(
        bpy.ops.daf.commit_gore() == {'FINISHED'},
        "Top-deck Commit / Save Gore failed.",
    )
    require(
        not deformation_authoring.preview_gore_objects(),
        "Gore commit leaked preview-only nodes.",
    )
    require(
        deformation_authoring.generated_gore_objects(
            deformation_authoring._active_region_id(context),
            settings.deformation_active_key,
        ),
        "Gore commit did not create stable final nodes.",
    )
    require(not settings.deformation_gore_dirty, "Gore commit left the recipe dirty.")
    # Later endpoint coverage intentionally assigns every raw field extreme;
    # keep that independent from the new-draft rollback check below.
    settings.deformation_gore_enabled = False

    # FINAL PREVIEW is non-committing; Clear Preview removes temporary resources.
    settings.deformation_impact_size = 72.0
    require(settings.deformation_impact_dirty, "Macro edit did not mark the recipe dirty.")
    final_result = bpy.ops.daf.final_impact_preview()
    require(final_result == {'FINISHED'}, "FINAL PREVIEW failed.")
    require(settings.deformation_impact_dirty, "FINAL PREVIEW silently committed the recipe.")
    clear_result = bpy.ops.daf.clear_managed_preview()
    require(clear_result == {'FINISHED'}, "CLEAR DAMAGE PREVIEW failed.")
    for obj in (head, head_detached, body, forearm, forearm_detached):
        require(
            deformation_authoring._key(obj, deformation_authoring.PREVIEW_KEY_NAME) is None,
            f"Temporary preview key leaked on {obj.name}.",
        )

    # RNA limits exactly mirror the authority and accept every endpoint matrix value.
    with preview_service.suspend_updates():
        for identifier, contract in parameter_schema.PARAMETERS.items():
            if not hasattr(settings, identifier):
                continue
            rna = settings.bl_rna.properties[identifier]
            require(math.isclose(float(rna.hard_min), float(contract.hard_min), rel_tol=1e-6, abs_tol=1e-7), f"{identifier} RNA minimum drifted.")
            require(math.isclose(float(rna.hard_max), float(contract.hard_max), rel_tol=1e-6, abs_tol=1e-7), f"{identifier} RNA maximum drifted.")
            require(math.isclose(float(rna.soft_min), float(contract.soft_min), rel_tol=1e-6, abs_tol=1e-7), f"{identifier} RNA soft minimum drifted.")
            require(math.isclose(float(rna.soft_max), float(contract.soft_max), rel_tol=1e-6, abs_tol=1e-7), f"{identifier} RNA soft maximum drifted.")
            for value in endpoint_values(contract):
                setattr(settings, identifier, value)
                actual = getattr(settings, identifier)
                tolerance = 0.0 if contract.integer else max(1e-7, abs(float(value)) * 1e-6)
                require(
                    abs(float(actual) - float(value)) <= tolerance,
                    f"{identifier} rejected/clamped legal endpoint {value} -> {actual}.",
                )

    # MANUAL/CUSTOM does not fight raw values; fit is non-destructive; return is explicit.
    deformation_authoring.enter_manual_impact_control(context)
    manual_depth = 0.037123
    settings.deformation_seed_depth = manual_depth
    deformation_authoring.fit_impact_macros_to_current_values(context)
    require(abs(settings.deformation_seed_depth - manual_depth) < 1e-8, "Fit Macros changed a manual value.")
    deformation_authoring.return_to_macro_control(context)
    require(settings.deformation_impact_control_mode == 'MACRO', "Return to Macro Control failed.")

    # Undo Draft deletes only one uncommitted impact.
    settings.deformation_impact_semantic_name = "Undo_Draft_Acceptance"
    activate_and_select("body_core", body)
    before_count = len(deformation_authoring._metadata(body).get("keys", {}))
    require(bpy.ops.daf.create_impact_from_selection() == {'FINISHED'}, "Undo Draft setup failed.")
    require(bpy.ops.daf.undo_impact_draft() == {'FINISHED'}, "Undo Draft operator failed.")
    after_count = len(deformation_authoring._metadata(body).get("keys", {}))
    require(after_count == before_count, "Undo Draft leaked or removed the wrong key.")

    state = preview_service.state()
    handler_count = sum(
        getattr(handler, "__name__", "") == "_load_post"
        and getattr(handler, "__module__", "").endswith("deformation.preview_service")
        for handler in bpy.app.handlers.load_post
    )
    require(not state["timerRegistered"], "A managed preview timer leaked.")
    require(handler_count == 1, f"Expected one preview load handler, found {handler_count}.")
    report = {
        "status": "PASS",
        "blenderVersion": bpy.app.version_string,
        "regions": [region["regionId"] for region in regions],
        "regionModes": [region["regionMode"] for region in regions],
        "families": list(families),
        "createdImpactCount": len(created),
        "macroGenerationChecks": generation_checks,
        "randomizedSeedCount": len(seeds),
        "distinctRandomizedSeeds": len(set(seeds)),
        "goreRandomizedSeedCount": len(gore_seeds),
        "distinctGoreRandomizedSeeds": len(set(gore_seeds)),
        "goreTopDeckPreviewCommit": True,
        "deterministicPreviewDigest": first_digest,
        "timerRegistered": state["timerRegistered"],
        "previewHandlerCount": handler_count,
    }
    print("IMPACT_PEDAL_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
