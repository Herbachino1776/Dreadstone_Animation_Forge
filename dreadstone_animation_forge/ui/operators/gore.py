"""Primary Gore Control Deck orchestration."""

from __future__ import annotations

from bpy.types import Operator

from ...deformation import preview_service


class _GoreOperator(Operator):
    def failed(self, exc):
        self.report({"ERROR"}, str(exc))
        return {"CANCELLED"}


class DAF_OT_generate_gore_preview(_GoreOperator):
    bl_idname = "daf.generate_gore_preview"
    bl_label = "GENERATE / REBUILD GORE PREVIEW"
    bl_description = (
        "Build one managed preview-only result from the current Gore Pedal, "
        "identity, and seed without replacing the saved recipe"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.generate_gore_preview(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_final_gore_preview(_GoreOperator):
    bl_idname = "daf.final_gore_preview"
    bl_label = "FINAL GORE PREVIEW"
    bl_description = "Build complete deterministic preview-only cavity/inlay geometry"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.generate_gore_preview(context, quality="FINAL")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_commit_gore(_GoreOperator):
    bl_idname = "daf.commit_gore"
    bl_label = "COMMIT / SAVE GORE"
    bl_description = (
        "Persist the current Gore Pedal recipe, build stable final geometry, "
        "and run focused validation"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.commit_current_tuning(context)
            preview_service.clear(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_revert_gore(_GoreOperator):
    bl_idname = "daf.revert_gore"
    bl_label = "Revert Gore"
    bl_description = (
        "Restore the previous saved Gore Pedal, master seed, recipe, and valid "
        "generated result"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.revert_current_tuning(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_use_manual_gore_control(_GoreOperator):
    bl_idname = "daf.use_manual_gore_control"
    bl_label = "USE MANUAL GORE CONTROL"
    bl_description = "Keep current physical gore values and mark the recipe CUSTOM"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.enter_manual_gore_control(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_return_to_gore_macro_control(_GoreOperator):
    bl_idname = "daf.return_to_gore_macro_control"
    bl_label = "RETURN TO GORE PEDAL"
    bl_description = "Replace manual gore internals with the current six-macro recipe"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.return_to_gore_macro_control(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


CLASSES = (
    DAF_OT_generate_gore_preview,
    DAF_OT_final_gore_preview,
    DAF_OT_commit_gore,
    DAF_OT_revert_gore,
    DAF_OT_use_manual_gore_control,
    DAF_OT_return_to_gore_macro_control,
)
