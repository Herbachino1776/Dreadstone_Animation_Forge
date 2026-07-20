"""Support-report and startup self-check operators."""

from __future__ import annotations

from bpy.types import Operator

from ...deformation import diagnostics


class DAF_OT_write_diagnostic_report(Operator):
    bl_idname = "daf.write_forge_diagnostic_report"
    bl_label = "Write Forge Diagnostic Report"
    bl_description = "Write privacy-safe JSON and Markdown diagnostics without proprietary mesh payloads"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            result = diagnostics.write_reports(
                context.scene.daf_settings.diagnostics_output_directory,
                deformation_authoring._version_string(),
                deformation_authoring.DEFORMATION_BUILD_ID,
            )
            self.report({'INFO'}, f"Wrote {result['json']}")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class DAF_OT_startup_self_check(Operator):
    bl_idname = "daf.forge_startup_self_check"
    bl_label = "Run Startup Self-Check"
    bl_description = "Detect or repair duplicate lifecycle hooks, stale previews, and invalid caches"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from ... import deformation_authoring

        result = deformation_authoring.startup_self_check(context)
        level = {'INFO'} if result["status"] == "PASS" else {'WARNING'}
        self.report(level, f"Forge self-check {result['status']}: {len(result['findings'])} finding(s).")
        return {'FINISHED'}


CLASSES = (DAF_OT_write_diagnostic_report, DAF_OT_startup_self_check)
