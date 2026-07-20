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
            self.report({'INFO'}, f"Impact draft {result['key']} created from {result['faceCount']} selected faces.")
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


CLASSES = (DAF_OT_create_impact_from_selection, DAF_OT_undo_impact_draft)
