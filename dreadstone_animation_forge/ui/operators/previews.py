"""Explicit preview/commit/revert lifecycle actions."""

from __future__ import annotations

from bpy.types import Operator

from ...deformation import preview_service


class _PreviewOperator(Operator):
    def failed(self, exc):
        self.report({'ERROR'}, str(exc))
        return {'CANCELLED'}


class DAF_OT_final_impact_preview(_PreviewOperator):
    bl_idname = "daf.final_impact_preview"
    bl_label = "Final Preview"
    bl_description = "Deliberately build deterministic final deformation and raised gore"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        result = preview_service.run_now(context, quality="FINAL")
        if result.get("failed"):
            return self.failed(RuntimeError(result.get("error", "Final preview failed.")))
        return {'FINISHED'}


class DAF_OT_commit_impact(_PreviewOperator):
    bl_idname = "daf.commit_impact"
    bl_label = "Commit Impact"
    bl_description = "Persist current controls, rebuild deterministic final geometry, and run focused validation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.commit_current_tuning(context)
            preview_service.clear(context)
            return {'FINISHED'}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_revert_impact(_PreviewOperator):
    bl_idname = "daf.revert_impact"
    bl_label = "Revert to Saved Recipe"
    bl_description = "Discard uncommitted control changes and reload the stored recipe"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.revert_current_tuning(context)
            return {'FINISHED'}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_clear_managed_preview(_PreviewOperator):
    bl_idname = "daf.clear_managed_preview"
    bl_label = "CLEAR DAMAGE PREVIEW"
    bl_description = "Atomically zero managed damage morphs, remove stain preview resources, and hide raised gore without deleting recipes or export geometry"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            preview_service.clear(context)
            return {'FINISHED'}
        except Exception as exc:
            return self.failed(exc)


CLASSES = (
    DAF_OT_final_impact_preview,
    DAF_OT_commit_impact,
    DAF_OT_revert_impact,
    DAF_OT_clear_managed_preview,
)
