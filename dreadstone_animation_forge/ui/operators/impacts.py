"""Atomic impact-draft operator."""

from __future__ import annotations

from bpy.types import Operator

from ...deformation import diagnostics, preview_service


class DAF_OT_create_impact_from_selection(Operator):
    bl_idname = "daf.create_impact_from_selection"
    bl_label = "Create Impact From Current Selection"
    bl_description = "Transactionally create a unique key, capture one connected face patch, add a blunt stamp and optional heavy gore, then generate FAST preview"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            result = deformation_authoring.create_impact_from_current_selection(context)
            stages = " / ".join(result.get("workflow", ()))
            self.report(
                {'INFO'},
                f"{result['key']}: {stages} ({result['faceCount']} selected faces).",
            )
            return {'FINISHED'}
        except Exception as exc:
            diagnostics.record_exception("Create Impact From Current Selection", exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_undo_impact_draft(Operator):
    bl_idname = "daf.undo_impact_draft"
    bl_label = "Undo Draft"
    bl_description = "Delete only the active uncommitted Forge impact draft"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            if not deformation_authoring.remove_active_draft(context):
                raise RuntimeError("The active deformation is committed or is not a one-click draft.")
            preview_service.clear(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_randomize_impact_seed(Operator):
    bl_idname = "daf.randomize_impact_seed"
    bl_label = "RANDOMIZE SEED"
    bl_description = "Choose one new deterministic master impact seed and request one managed preview"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            result = deformation_authoring.randomize_impact_seed(context)
            self.report({'INFO'}, f"Impact seed {result['previousSeed']} -> {result['seed']}.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_use_manual_impact_control(Operator):
    bl_idname = "daf.use_manual_impact_control"
    bl_label = "USE MANUAL CONTROL"
    bl_description = "Keep current physical values and mark the recipe CUSTOM"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ... import deformation_authoring

        deformation_authoring.enter_manual_impact_control(context)
        return {'FINISHED'}


class DAF_OT_fit_impact_macros(Operator):
    bl_idname = "daf.fit_impact_macros"
    bl_label = "FIT MACROS TO CURRENT VALUES"
    bl_description = "Estimate the nearest Impact Pedal state without changing the manual physical recipe"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.fit_impact_macros_to_current_values(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_return_to_macro_control(Operator):
    bl_idname = "daf.return_to_macro_control"
    bl_label = "RETURN TO MACRO CONTROL"
    bl_description = "Replace manual physical values with the currently fitted Impact Pedal recipe"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.return_to_macro_control(context)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


CLASSES = (
    DAF_OT_create_impact_from_selection,
    DAF_OT_undo_impact_draft,
    DAF_OT_randomize_impact_seed,
    DAF_OT_use_manual_impact_control,
    DAF_OT_fit_impact_macros,
    DAF_OT_return_to_macro_control,
)
