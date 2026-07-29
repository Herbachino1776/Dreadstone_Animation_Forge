"""Progressive Damage Site orchestration operators."""

from __future__ import annotations

from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from ...deformation import diagnostics


class _ProgressiveOperator(Operator):
    def failed(self, operation, exc):
        diagnostics.record_exception(operation, exc)
        self.report({"ERROR"}, str(exc))
        return {"CANCELLED"}


class DAF_OT_new_progressive_site(_ProgressiveOperator):
    bl_idname = "daf.new_progressive_site"
    bl_label = "New Progressive Damage Site"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import progressive_authoring

        try:
            site = progressive_authoring.create_site(context)
            self.report({"INFO"}, f"Created {site['displayName']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("New Progressive Damage Site", exc)


class DAF_OT_select_progressive_site(_ProgressiveOperator):
    bl_idname = "daf.select_progressive_site"
    bl_label = "Select Progressive Damage Site"
    bl_options = {"REGISTER"}

    site_guid: StringProperty()

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.select_site(context, self.site_guid)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Select Progressive Damage Site", exc)


class DAF_OT_rename_progressive_site(_ProgressiveOperator):
    bl_idname = "daf.rename_progressive_site"
    bl_label = "Rename Progressive Damage Site"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.rename_site(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Rename Progressive Damage Site", exc)


class DAF_OT_duplicate_progressive_site_metadata(_ProgressiveOperator):
    bl_idname = "daf.duplicate_progressive_site_metadata"
    bl_label = "Duplicate Progressive Site Metadata"
    bl_description = (
        "Duplicate spatial/transition metadata with empty stages; Damage Keys "
        "remain exclusively assigned to the original site"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.duplicate_site_metadata(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Duplicate Progressive Site Metadata", exc)


class DAF_OT_delete_progressive_site_metadata(_ProgressiveOperator):
    bl_idname = "daf.delete_progressive_site_metadata"
    bl_label = "Delete Progressive Site Metadata"
    bl_description = (
        "Delete only the site relationship; preserve every assigned Damage "
        "Key, Stamp, shape key, and gore object"
    )
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from ... import progressive_authoring

        try:
            result = progressive_authoring.delete_site_metadata(context)
            self.report(
                {"INFO"},
                f"Site metadata deleted; {len(result['preservedDamageKeyIds'])} keys preserved.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Delete Progressive Site Metadata", exc)


class DAF_OT_focus_progressive_stage(_ProgressiveOperator):
    bl_idname = "daf.focus_progressive_stage"
    bl_label = "Focus Progressive Stage"
    bl_options = {"REGISTER"}

    stage: StringProperty()

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.focus_stage(context, self.stage)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Focus Progressive Stage", exc)


class DAF_OT_assign_progressive_stage(_ProgressiveOperator):
    bl_idname = "daf.assign_progressive_stage"
    bl_label = "Assign Active Damage Key"
    bl_options = {"REGISTER", "UNDO"}

    stage: StringProperty()

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.assign_active_key_to_stage(
                context,
                self.stage,
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Assign Progressive Stage", exc)


class DAF_OT_unassign_progressive_stage(_ProgressiveOperator):
    bl_idname = "daf.unassign_progressive_stage"
    bl_label = "Unassign Progressive Stage"
    bl_description = "Remove only the stage relationship and preserve artist data"
    bl_options = {"REGISTER", "UNDO"}

    stage: StringProperty()

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.unassign_stage(context, self.stage)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Unassign Progressive Stage", exc)


class DAF_OT_create_progressive_stage_key(_ProgressiveOperator):
    bl_idname = "daf.create_progressive_stage_key"
    bl_label = "Create New Key for Progressive Stage"
    bl_description = (
        "Delegate to the current atomic Damage Key creation workflow, then "
        "assign the new independent key to this stage"
    )
    bl_options = {"REGISTER", "UNDO"}

    stage: StringProperty()

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.create_key_for_stage(context, self.stage)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Create Progressive Stage Key", exc)


class DAF_OT_duplicate_progressive_stage_key(_ProgressiveOperator):
    bl_idname = "daf.duplicate_progressive_stage_key"
    bl_label = "Duplicate Active Key as Independent Starting Point"
    bl_options = {"REGISTER", "UNDO"}

    stage: StringProperty()

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.duplicate_active_key_for_stage(
                context,
                self.stage,
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Duplicate Progressive Stage Key", exc)


class DAF_OT_set_progressive_site_anchor(_ProgressiveOperator):
    bl_idname = "daf.set_progressive_site_anchor"
    bl_label = "Set Site Anchor from Active Stage"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.set_site_anchor_from_active_stage(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Set Progressive Site Anchor", exc)


class DAF_OT_refresh_progression_preview(_ProgressiveOperator):
    bl_idname = "daf.refresh_progression_preview"
    bl_label = "Refresh Progression Preview"
    bl_options = {"REGISTER"}

    with_other_damage: BoolProperty(default=False)

    def execute(self, context):
        from ... import progressive_authoring

        try:
            context.scene.daf_settings.progression_preview_with_other_damage = (
                bool(self.with_other_damage)
            )
            progressive_authoring.refresh_progression_preview(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Refresh Progression Preview", exc)


class DAF_OT_clear_progression_preview(_ProgressiveOperator):
    bl_idname = "daf.clear_progression_preview"
    bl_label = "Clear Progression Preview"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.clear_progression_preview(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Clear Progression Preview", exc)


class DAF_OT_validate_progressive_site(_ProgressiveOperator):
    bl_idname = "daf.validate_progressive_site"
    bl_label = "Validate Progressive Damage Site"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ... import progressive_authoring

        try:
            report = progressive_authoring.validate_site(context)
            if report["status"] != "PASS":
                raise RuntimeError("; ".join(report["errors"][:4]))
            self.report(
                {"INFO"},
                f"Progression validation passed ({report['sampleCount']} samples).",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Validate Progressive Damage Site", exc)


class DAF_OT_validate_all_progressive_sites(_ProgressiveOperator):
    bl_idname = "daf.validate_all_progressive_sites"
    bl_label = "Validate All Progressive Damage Sites"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ... import progressive_authoring

        try:
            report = progressive_authoring.validate_all_sites(context)
            if report["status"] != "PASS":
                raise RuntimeError("One or more Progressive Damage Sites failed.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Validate All Progressive Damage Sites", exc)


class DAF_OT_enable_progressive_site_export(_ProgressiveOperator):
    bl_idname = "daf.enable_progressive_site_export"
    bl_label = "Validate and Enable Site for Export"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.enable_site_for_export(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Enable Progressive Site Export", exc)


class DAF_OT_disable_progressive_site_export(_ProgressiveOperator):
    bl_idname = "daf.disable_progressive_site_export"
    bl_label = "Disable Progressive Site Export"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import progressive_authoring

        try:
            progressive_authoring.disable_site_export(context)
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Disable Progressive Site Export", exc)


CLASSES = (
    DAF_OT_new_progressive_site,
    DAF_OT_select_progressive_site,
    DAF_OT_rename_progressive_site,
    DAF_OT_duplicate_progressive_site_metadata,
    DAF_OT_delete_progressive_site_metadata,
    DAF_OT_focus_progressive_stage,
    DAF_OT_assign_progressive_stage,
    DAF_OT_unassign_progressive_stage,
    DAF_OT_create_progressive_stage_key,
    DAF_OT_duplicate_progressive_stage_key,
    DAF_OT_set_progressive_site_anchor,
    DAF_OT_refresh_progression_preview,
    DAF_OT_clear_progression_preview,
    DAF_OT_validate_progressive_site,
    DAF_OT_validate_all_progressive_sites,
    DAF_OT_enable_progressive_site_export,
    DAF_OT_disable_progressive_site_export,
)
