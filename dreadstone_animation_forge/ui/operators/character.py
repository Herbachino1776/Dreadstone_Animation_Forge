"""Transactional character-preparation orchestration."""

from __future__ import annotations

import json

import bpy
from bpy.types import Operator

from ...deformation import diagnostics
from ...deformation.transactions import OperationTransaction


class DAF_OT_prepare_character_for_damage_authoring(Operator):
    bl_idname = "daf.prepare_character_for_damage_authoring"
    bl_label = "Prepare Character for Damage Authoring"
    bl_description = "Analyze rig and source readiness, stop on NOT READY, build the protected asset, and register available standard regions"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ... import deformation_authoring, related, world_bounds

        settings = context.scene.daf_settings
        summary = []
        try:
            output = str(settings.damage_readiness_output_directory).strip()
            if not output:
                raise RuntimeError("Choose an explicit Source Readiness output folder first.")
            if output.startswith("//") and not bpy.data.filepath:
                raise RuntimeError("An unsaved .blend requires an explicit non-relative Source Readiness output folder.")
            selected = tuple(context.selected_objects)
            active = context.active_object
            if active is None:
                raise RuntimeError("Select the imported character hierarchy before preparing it.")
            candidates = tuple({*selected, active})
            with OperationTransaction(
                context,
                "Prepare Character",
                objects=candidates,
                metadata_keys=(deformation_authoring.REGISTRY_PROPERTY, deformation_authoring.METADATA_PROPERTY),
                ownership_predicate=lambda value: bool(
                    value.get("dsb_damage_generated", False)
                    or value.get("dsb_generated_role", "")
                    or value.get("dsb_safe_size_wrapper", False)
                ),
            ) as transaction:
                transaction.set_stage("analyze rig")
                result = bpy.ops.daf.analyze()
                if 'FINISHED' not in result:
                    raise RuntimeError("Rig analysis did not finish.")
                summary.append({"step": "Rig analyzed", "status": "PASS"})

                transaction.set_stage("evaluate scale")
                meshes = [
                    obj for obj in related(context)
                    if obj.type == 'MESH' and obj.name != "DSB_PREVIEW_FLOOR"
                ]
                if not meshes:
                    raise RuntimeError("Rig analysis found no character mesh to measure.")
                minimum, maximum = world_bounds(context, meshes)
                measured_height = float(maximum.z - minimum.z)
                target_height = float(settings.target_height)
                resize_required = abs(measured_height - target_height) > 0.0005
                if resize_required:
                    result = bpy.ops.daf.safe_resize()
                    if 'FINISHED' not in result:
                        raise RuntimeError("Safe Resize did not finish.")
                summary.append({
                    "step": "Scale evaluated",
                    "status": "PASS",
                    "measuredHeightBefore": measured_height,
                    "targetHeight": target_height,
                    "resizeNecessary": resize_required,
                    "resizeApplied": resize_required,
                })

                transaction.set_stage("source damage readiness")
                result = bpy.ops.daf.analyze_damage_readiness()
                if 'FINISHED' not in result:
                    raise RuntimeError("Source Damage Readiness did not finish.")
                readiness = str(settings.damage_readiness_overall_status)
                summary.append({"step": "Source Damage Readiness", "status": readiness})
                if readiness not in {"READY", "SOURCE READY"}:
                    raise RuntimeError(f"Source Damage Readiness is {readiness}; Forge stopped without guessing repairs.")

                transaction.set_stage("load READY handoff")
                settings.damage_authoring_report_path = settings.last_damage_readiness_json_path
                result = bpy.ops.daf.load_damage_readiness_handoff()
                if 'FINISHED' not in result:
                    raise RuntimeError("READY handoff validation failed.")
                summary.append({"step": "READY handoff loaded", "status": "PASS"})

                transaction.set_stage("build authoring asset")
                result = bpy.ops.daf.build_damage_authoring_asset()
                if 'FINISHED' not in result:
                    raise RuntimeError("Damage Authoring Asset build failed.")
                summary.append({"step": "Authoring asset built", "status": "PASS"})

                transaction.set_stage("register standard regions")
                region_result = deformation_authoring.register_standard_generated_regions(context)
                summary.append({"step": "Standard regions registered", "status": "PASS", **region_result})
                transaction.commit()

            settings.ui_workspace = 'DAMAGE'
            settings.deformation_status = "CHARACTER PREPARED — SELECT A REGION"
            context.scene["dsb_prepare_character_summary_json"] = json.dumps(summary, sort_keys=True, separators=(",", ":"))
            self.report({'INFO'}, f"Prepared character; {len(region_result['registered'])} new and {len(region_result['existing'])} existing regions ready.")
            return {'FINISHED'}
        except Exception as exc:
            summary.append({"step": "Stopped", "status": "FAIL", "error": str(exc)})
            context.scene["dsb_prepare_character_summary_json"] = json.dumps(summary, sort_keys=True, separators=(",", ":"))
            diagnostics.record_exception("Prepare Character", exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


CLASSES = (DAF_OT_prepare_character_for_damage_authoring,)
