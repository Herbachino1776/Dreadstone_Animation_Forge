"""Focused Blender acceptance for mode-aware Damage Key creation.

Run from the repository root:

    blender --background --factory-startup \
      --python tests/blender_damage_selection_acceptance.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import (  # noqa: E402
    animation_library,
    deformation_authoring,
    trauma_field,
)
from dreadstone_animation_forge.deformation import preview_service  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def grid_mesh(name, *, size=7, spacing=0.025):
    vertices = [
        ((x - size // 2) * spacing, (y - size // 2) * spacing, 0.0)
        for y in range(size)
        for x in range(size)
    ]
    faces = [
        (
            y * size + x,
            y * size + x + 1,
            (y + 1) * size + x + 1,
            (y + 1) * size + x,
        )
        for y in range(size - 1)
        for x in range(size - 1)
    ]
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.shape_key_add(name="Basis")
    return obj


def select_elements(obj, *, mode, indices):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (
        mode == "VERT",
        mode == "EDGE",
        mode == "FACE",
    )
    bpy.ops.mesh.select_all(action="DESELECT")
    mesh = bmesh.from_edit_mesh(obj.data)
    mesh.verts.ensure_lookup_table()
    mesh.faces.ensure_lookup_table()
    elements = mesh.faces if mode == "FACE" else mesh.verts
    for index in indices:
        elements[index].select_set(True)
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


def active_capture(attached, settings):
    payload = deformation_authoring._metadata(attached)
    entry = payload["keys"][settings.deformation_active_key]
    stamp = entry["stamps"][0]
    return stamp["capture"]


def main():
    addon.register()
    try:
        context = bpy.context
        settings = context.scene.daf_settings
        settings.deformation_live_preview = False
        settings.deformation_auto_preview = True
        settings.deformation_preview_quality = "FAST"

        attached = grid_mesh("DAMAGE_SELECTION_ATTACHED")
        detached = grid_mesh("DAMAGE_SELECTION_DETACHED")
        registry = deformation_authoring._empty_registry()
        region = deformation_authoring._record_from_pair(
            "head",
            attached,
            detached,
            "",
        )
        require(region["validationStatus"] == "PASS", "Synthetic head pair is invalid.")
        registry["regions"] = [region]
        registry["activeRegionId"] = "head"
        deformation_authoring._store_registry(registry)

        cases = (
            ("single_vertex", "VERT", (24,), "SELECTED_VERTICES", "VERTEX", 1),
            ("vertex_patch", "VERT", (23, 24, 25, 31), "SELECTED_VERTICES", "VERTEX", 4),
            ("single_face", "FACE", (14,), "SINGLE_FACE", "FACE", 1),
            ("face_patch", "FACE", (14, 15, 20, 21), "SELECTED_FACE_PATCH", "FACE", 4),
        )
        created = []
        for semantic_name, select_mode, indices, placement, kind, expected_count in cases:
            deformation_authoring._set_active_region("head", context)
            settings.deformation_impact_semantic_name = semantic_name
            select_elements(attached, mode=select_mode, indices=indices)
            result = bpy.ops.daf.create_impact_from_selection()
            require(result == {"FINISHED"}, f"{semantic_name} creation failed: {result}")
            capture = active_capture(attached, settings)
            require(
                capture["placementMode"] == placement,
                f"{semantic_name} used {capture['placementMode']} instead of {placement}.",
            )
            require(
                capture["selectionKind"] == kind,
                f"{semantic_name} used selection kind {capture['selectionKind']}.",
            )
            count = len(
                capture["faceIndices"] if kind == "FACE" else capture["vertexIndices"]
            )
            require(count == expected_count, f"{semantic_name} captured {count} elements.")
            key_name = settings.deformation_active_key
            require(
                detached.data.shape_keys.key_blocks.get(key_name) is not None,
                f"{semantic_name} did not create its paired detached key.",
            )
            require(
                settings.deformation_preview_status == "READY",
                f"{semantic_name} did not complete its FAST preview.",
            )
            created.append(key_name)

        # Normal authoring invalidation and Blender's file-load callback must
        # keep the lightweight Damage Key/Stamp card inventory available.
        persisted_names = set(deformation_authoring._metadata(attached)["keys"])
        deformation_authoring._invalidate_geodesic_cache()
        invalidated_names = {
            str(entry.get("name", ""))
            for entry in deformation_authoring.cached_ui_summary(settings)
            .get("metadata", {})
            .get("keys", [])
        }
        require(
            invalidated_names == persisted_names,
            "Authoring cache invalidation hid persisted Damage Key cards.",
        )
        deformation_authoring._clear_service_caches("file load")
        reloaded_names = {
            str(entry.get("name", ""))
            for entry in deformation_authoring.cached_ui_summary(settings)
            .get("metadata", {})
            .get("keys", [])
        }
        require(
            reloaded_names == persisted_names,
            "File-load cache clearing hid persisted Damage Key cards.",
        )

        # A cancelled creation must not leave a phantom key or Stamp in the panel cache.
        before_names = set(deformation_authoring._metadata(attached)["keys"])
        select_elements(attached, mode="FACE", indices=())
        try:
            failed = bpy.ops.daf.create_impact_from_selection()
        except RuntimeError:
            failed = {"CANCELLED"}
        require(failed == {"CANCELLED"}, "Empty selection did not cancel creation.")
        after_names = set(deformation_authoring._metadata(attached)["keys"])
        require(after_names == before_names, "Cancelled creation leaked persisted metadata.")
        cached = deformation_authoring.cached_ui_summary(settings)
        cached_names = {
            str(entry.get("name", ""))
            for entry in cached.get("metadata", {}).get("keys", [])
        }
        require(cached_names == after_names, "Cancelled creation left a phantom UI key.")
        require(
            settings.deformation_active_key in after_names,
            "Cancelled creation did not restore the previously active Damage Key.",
        )

        # The default additive recipe must build and retain all four final
        # components for a paired region through presentation and validation.
        payload = deformation_authoring._metadata(attached)
        active_name = settings.deformation_active_key
        entry = payload["keys"][active_name]
        overlay = trauma_field.normalize_gore_overlay(
            entry["surfaceGoreOverlay"]
        )
        require(
            overlay["goreGeometryMode"] == "HYBRID_ADDITIVE",
            "New Damage Key did not keep its additive raised + inlay recipe.",
        )
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        commit_result = deformation_authoring.commit_current_tuning(context)
        final_objects = deformation_authoring.generated_gore_objects(
            "head",
            active_name,
        )
        ownership = {
            (
                str(obj.get("dsb_gore_pair_role", "")).upper(),
                str(obj.get("dsb_gore_component", "")).upper(),
            )
            for obj in final_objects
        }
        require(
            ownership == {
                ("ATTACHED", "RAISED"),
                ("ATTACHED", "INLAY"),
                ("DETACHED", "RAISED"),
                ("DETACHED", "INLAY"),
            },
            f"Paired hybrid component ownership was lost: {sorted(ownership)}.",
        )
        raised_objects = [
            obj
            for obj in final_objects
            if str(obj.get("dsb_gore_component", "")).upper()
            == "RAISED"
        ]
        require(
            len(raised_objects) == 2,
            "The paired recipe did not build both raised surface components.",
        )
        require(
            all(
                int(obj.get("dsb_gore_nucleus_triangle_count", 0)) > 0
                for obj in raised_objects
            ),
            "The default cohesive surface recipe did not build closed nuclei.",
        )
        require(
            all(
                int(obj.get("dsb_gore_nucleus_count", 0)) >= 2
                for obj in raised_objects
            ),
            "The default cohesive surface recipe did not distribute multiple nuclei.",
        )
        require(
            all(
                float(obj.get("dsb_gore_surface_mass", 0.0)) > 0.0
                for obj in raised_objects
            ),
            "Raised gore did not retain its cohesive surface-mass control.",
        )
        require(
            all(
                str(obj.get("dsb_gore_shell_quality", ""))
                == "COHESIVE_SURFACE_MASS_DISTRIBUTED_NUCLEI_V5"
                for obj in raised_objects
            ),
            "Raised gore did not use the distributed-nuclei geometry contract.",
        )
        require(
            all(
                trauma_field.RAISED_GORE_MATERIAL_IDS[-1]
                in {
                    str(slot.get("dsb_gore_material_id", ""))
                    for slot in obj.data.materials
                    if slot
                }
                for obj in raised_objects
            ),
            "Raised gore is missing the solid-tissue nucleus material.",
        )
        raised_nucleus_triangles = sum(
            int(obj["dsb_gore_nucleus_triangle_count"])
            for obj in raised_objects
        )
        raised_nucleus_count = sum(
            int(obj["dsb_gore_nucleus_count"])
            for obj in raised_objects
        )
        validation = commit_result["validation"]
        require(
            validation["status"] == "PASS",
            "Paired hybrid validation failed: "
            + "; ".join(validation.get("errors", [])[:6]),
        )

        # Reproduce the reported stale-boundary condition: an existing Stamp
        # can carry a larger historical cap than the key's current macro cap.
        # The rebuilt key must honor the current key-level world limit.
        payload = deformation_authoring._metadata(attached)
        payload["keys"][active_name]["maximumDisplacement"] = 0.020
        deformation_authoring._store_metadata(
            attached,
            detached,
            payload,
        )
        capped_rebuild = deformation_authoring.rebuild_active_deformation(
            context
        )
        require(
            capped_rebuild["validation"]["status"] == "PASS",
            "A lowered macro displacement cap failed final projection.",
        )
        require(
            capped_rebuild["validation"]["maximumDisplacement"] <= 0.020001,
            "Rebuilt key exceeded the lowered macro displacement cap.",
        )
        final_objects = deformation_authoring.generated_gore_objects(
            "head",
            active_name,
        )

        # The final writer independently enforces the world-space recipe cap,
        # including on transformed production objects.
        basis_world = deformation_authoring._basis_world_positions(attached)
        inverse_world = attached.matrix_world.inverted()
        overshoot = [
            inverse_world
            @ (
                Vector(position)
                + Vector((0.0, 0.0, 0.050))
            )
            for position in basis_world
        ]
        clamped = (
            deformation_authoring._clamp_local_coordinates_to_world_limit(
                attached,
                overshoot,
                0.020,
            )
        )
        clamped_maximum = max(
            (
                attached.matrix_world @ coordinate
                - Vector(basis_position)
            ).length
            for basis_position, coordinate in zip(
                basis_world,
                clamped,
            )
        )
        require(
            clamped_maximum <= 0.020001,
            "Final world-space displacement projection exceeded its cap.",
        )

        # Unsaved macro edits must be visible without pressing Save. FAST uses
        # the current stain mask; BALANCED adds preview-only geometry.
        with preview_service.suspend_updates():
            settings.deformation_gore_exposure = 86.45569610595703
            settings.deformation_gore_inlay_amount = 0.699999988079071
            settings.deformation_gore_clot_fill = 75.20674896240234
            settings.deformation_gore_breakup = 58.0
            settings.deformation_gore_wetness_macro = 68.0
            settings.deformation_gore_raised_amount = 0.8603375554084778
        deformation_authoring.apply_gore_macro_transaction(
            context,
            "reported layer-order regression",
        )
        balanced = preview_service.run_now(context, quality="BALANCED")
        require(
            not balanced.get("failed"),
            f"BALANCED live gore preview failed: {balanced.get('error', '')}",
        )
        require(
            balanced.get("previewGoreObjectCount") == 4,
            "BALANCED did not build four paired hybrid preview objects.",
        )
        require(
            len(deformation_authoring.preview_gore_objects("head", active_name)) == 4,
            "BALANCED preview-only ownership count is incorrect.",
        )
        require(
            all(obj.hide_get() for obj in final_objects),
            "Saved gore remained visible over the current unsaved preview.",
        )

        fast = preview_service.run_now(context, quality="FAST")
        require(
            not fast.get("failed"),
            f"FAST live gore preview failed: {fast.get('error', '')}",
        )
        require(
            fast.get("goreMaskedVertexCount", 0) > 0,
            "FAST did not install the current gore stain mask.",
        )
        require(
            fast.get("previewGoreObjectCount") == 0,
            "FAST unexpectedly retained temporary gore geometry.",
        )
        require(
            not deformation_authoring.preview_gore_objects("head", active_name),
            "FAST left BALANCED preview geometry behind.",
        )

        # The front-facing inline action must rename the complete ownership
        # graph, not only the visible shape-key label. This models the common
        # duplicate-as-starting-point workflow.
        animated_key = attached.data.shape_keys.key_blocks[active_name]
        animated_key.value = 0.4
        animated_key.keyframe_insert(data_path="value", frame=1)
        animated_action = attached.data.shape_keys.animation_data.action
        require(animated_action is not None, "Could not create the rename animation fixture.")
        payload_before_rename = deformation_authoring._metadata(attached)
        entry_before_rename = payload_before_rename["keys"][active_name]
        stable_key_id = str(entry_before_rename.get("damageKeyId", ""))
        stamp_ids = [
            str(stamp.get("stampId", ""))
            for stamp in entry_before_rename.get("stamps", [])
        ]
        require(stable_key_id, "The source Damage Key has no stable ID.")
        renamed_name = "face_patch_followup_origin"
        settings.deformation_key_name = renamed_name
        rename_result = bpy.ops.daf.rename_damage_key(key_name=active_name)
        require(rename_result == {"FINISHED"}, f"Inline rename failed: {rename_result}")
        renamed_payload = deformation_authoring._metadata(attached)
        require(active_name not in renamed_payload["keys"], "Old key metadata survived rename.")
        require(renamed_name in renamed_payload["keys"], "Renamed key metadata is missing.")
        renamed_entry = renamed_payload["keys"][renamed_name]
        require(
            str(renamed_entry.get("damageKeyId", "")) == stable_key_id,
            "Rename changed the stable Damage Key ID.",
        )
        require(
            [str(stamp.get("stampId", "")) for stamp in renamed_entry.get("stamps", [])]
            == stamp_ids,
            "Rename changed child Stamp identities.",
        )
        require(
            attached.data.shape_keys.key_blocks.get(active_name) is None
            and detached.data.shape_keys.key_blocks.get(active_name) is None,
            "Old attached/detached shape-key names survived rename.",
        )
        require(
            attached.data.shape_keys.key_blocks.get(renamed_name) is not None
            and detached.data.shape_keys.key_blocks.get(renamed_name) is not None,
            "Renamed attached/detached shape keys are missing.",
        )
        require(
            settings.deformation_active_key == renamed_name
            and settings.deformation_key_name == renamed_name,
            "Rename did not keep the inline editor focused on the new name.",
        )
        renamed_gore = deformation_authoring.generated_gore_objects(
            "head",
            renamed_name,
        )
        require(
            not deformation_authoring.generated_gore_objects("head", active_name),
            "Old generated-gore ownership survived rename.",
        )
        require(
            len(renamed_gore) == len(final_objects),
            "Rename did not rebuild the complete generated-gore ownership graph.",
        )
        driver_targets = [
            str(target.data_path)
            for curve in detached.data.shape_keys.animation_data.drivers
            for variable in curve.driver.variables
            for target in variable.targets
            if getattr(target, "id", None) == attached.data.shape_keys
        ]
        require(
            any(renamed_name in path for path in driver_targets)
            and all(active_name not in path for path in driver_targets),
            "Detached shape-key driver paths did not follow the rename.",
        )
        animated_paths = [
            str(curve.data_path)
            for curve in animation_library.iter_action_fcurves(animated_action)
        ]
        require(
            any(renamed_name in path for path in animated_paths)
            and all(active_name not in path for path in animated_paths),
            "Blender 5.x Action paths did not follow the Damage Key rename.",
        )
        require(
            bool(renamed_entry.get("previewEnabled", False))
            and attached.data.shape_keys.key_blocks[renamed_name].value > 0.0,
            "Rename did not restore the enabled Damage Key preview.",
        )

        # Invalid/colliding edits are rejected before touching the ownership graph.
        settings.deformation_key_name = created[0]
        try:
            collision_result = bpy.ops.daf.rename_damage_key(key_name=renamed_name)
        except RuntimeError:
            collision_result = {"CANCELLED"}
        require(
            collision_result == {"CANCELLED"},
            "A colliding inline rename was not rejected.",
        )
        require(
            renamed_name in deformation_authoring._metadata(attached)["keys"],
            "A rejected rename mutated the active Damage Key.",
        )
        settings.deformation_key_name = renamed_name
        active_name = renamed_name
        final_objects = renamed_gore

        print(json.dumps({
            "status": "PASS",
            "createdKeys": created,
            "selectionCases": len(cases),
            "rollbackCache": "PASS",
            "pairedHybridComponents": len(final_objects),
            "raisedNucleusTriangles": raised_nucleus_triangles,
            "raisedNucleusCount": raised_nucleus_count,
            "fastMaskedVertices": fast["goreMaskedVertexCount"],
            "balancedPreviewComponents": balanced["previewGoreObjectCount"],
            "renamedKey": renamed_name,
            "renameStableId": stable_key_id,
            "worldDisplacementCap": clamped_maximum,
            "rebuildDisplacementCap": capped_rebuild["validation"][
                "maximumDisplacement"
            ],
            "build": deformation_authoring.DEFORMATION_BUILD_ID,
        }, sort_keys=True))
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        addon.unregister()


if __name__ == "__main__":
    main()
