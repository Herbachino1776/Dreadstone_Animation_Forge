"""Front-facing Damage Key, Stamp, macro, and Blueprint actions."""

from __future__ import annotations

from bpy.props import StringProperty
from bpy.types import Operator

from ...deformation import diagnostics


class _VipOperator(Operator):
    def failed(self, operation, exc):
        diagnostics.record_exception(operation, exc)
        self.report({"ERROR"}, str(exc))
        return {"CANCELLED"}


class DAF_OT_toggle_damage_key_preview(_VipOperator):
    bl_idname = "daf.toggle_damage_key_preview"
    bl_label = "Toggle Damage Key Preview"
    bl_description = (
        "Show or hide this Damage Key while preserving every other enabled key preview"
    )
    bl_options = {"REGISTER", "UNDO"}

    key_name: StringProperty()

    def execute(self, context):
        from ... import deformation_authoring

        try:
            result = deformation_authoring.set_damage_key_preview_enabled(
                context, self.key_name
            )
            state = "ON" if result["enabled"] else "OFF"
            self.report({"INFO"}, f"{self.key_name} preview {state}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Toggle Damage Key Preview", exc)


class DAF_OT_rename_damage_key(_VipOperator):
    bl_idname = "daf.rename_damage_key"
    bl_label = "Rename Damage Key"
    bl_description = (
        "Rename this Damage Key while preserving its stable ID, Stamps, gore, "
        "animation paths, and progressive-site assignments"
    )
    bl_options = {"REGISTER", "UNDO"}

    key_name: StringProperty()

    def execute(self, context):
        from ... import deformation_authoring

        try:
            settings = context.scene.daf_settings
            result = deformation_authoring.rename_deformation_key(
                context,
                old_name=self.key_name or settings.deformation_active_key,
                new_name=settings.deformation_key_name,
            )
            if result.get("changed", False):
                self.report(
                    {"INFO"},
                    f"Renamed {result['oldName']} to {result['newName']}.",
                )
            else:
                self.report({"INFO"}, f"Damage Key is already named {result['newName']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Rename Damage Key", exc)


class DAF_OT_select_damage_stamp(_VipOperator):
    bl_idname = "daf.select_damage_stamp"
    bl_label = "Select Damage Stamp"
    bl_description = (
        "Focus this Damage Key and show this one child Stamp alternative"
    )
    bl_options = {"REGISTER", "UNDO"}

    key_name: StringProperty()
    stamp_id: StringProperty()

    def execute(self, context):
        from ... import deformation_authoring

        try:
            deformation_authoring.select_damage_key_stamp(
                context, self.key_name, self.stamp_id
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Select Damage Stamp", exc)


class DAF_OT_randomize_damage_recipe(_VipOperator):
    bl_idname = "daf.randomize_damage_recipe"
    bl_label = "RANDOMIZE DAMAGE"
    bl_description = (
        "Generate one master seed, derive independent impact and gore seeds, "
        "and request one preview"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            result = deformation_authoring.randomize_damage_recipe(context)
            from ... import progressive_authoring

            progressive_authoring.mark_active_stage_dirty(context)
            self.report(
                {"INFO"},
                (
                    f"Damage seed {result['masterSeed']} "
                    f"(impact {result['impactSeed']} / gore {result['goreSeed']})."
                ),
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Randomize Damage", exc)


class DAF_OT_save_vip_damage(_VipOperator):
    bl_idname = "daf.save_vip_damage"
    bl_label = "SAVE DAMAGE KEY"
    bl_description = (
        "Commit the focused Damage Key, active Stamp alternative, and additive gore recipe"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            result = deformation_authoring.commit_current_tuning(context)
            from ... import progressive_authoring

            progressive_authoring.sync_active_stage_after_save(context)
            deformation_authoring.apply_damage_key_previews(context)
            self.report(
                {"INFO"},
                f"{result.get('key', context.scene.daf_settings.deformation_active_key)} saved.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Save Damage Key", exc)


class DAF_OT_save_damage_blueprint(_VipOperator):
    bl_idname = "daf.save_damage_blueprint"
    bl_label = "ADD TO BLUEPRINT LIBRARY"
    bl_description = (
        "Save the focused Damage Key, active Stamp, macros, seeds, and gore as "
        "a topology-independent adaptive recipe"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            path, blueprint = deformation_authoring.save_active_damage_blueprint(
                context
            )
            self.report(
                {"INFO"},
                f"Saved {blueprint['name']} to {path.name}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Save Damage Blueprint", exc)


class DAF_OT_refresh_damage_blueprints(_VipOperator):
    bl_idname = "daf.refresh_damage_blueprints"
    bl_label = "Refresh Damage Blueprints"
    bl_description = "Reload the configured Damage Blueprint library from disk"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ... import deformation_authoring

        try:
            library = deformation_authoring.refresh_blueprint_library(context)
            self.report(
                {"INFO"},
                f"{int(library.get('blueprintCount', 0))} Damage Blueprints loaded.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Refresh Damage Blueprints", exc)


class DAF_OT_apply_damage_blueprint(_VipOperator):
    bl_idname = "daf.apply_damage_blueprint"
    bl_label = "Apply Damage Blueprint"
    bl_description = (
        "Adapt this portable recipe to the focused Stamp's fresh destination capture"
    )
    bl_options = {"REGISTER", "UNDO"}

    blueprint_id: StringProperty()

    def execute(self, context):
        from ... import deformation_authoring

        try:
            result = deformation_authoring.apply_damage_blueprint(
                context, self.blueprint_id
            )
            self.report(
                {"INFO"},
                f"{result['blueprint']['name']} adapted to {result['key']}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed("Apply Damage Blueprint", exc)


CLASSES = (
    DAF_OT_toggle_damage_key_preview,
    DAF_OT_rename_damage_key,
    DAF_OT_select_damage_stamp,
    DAF_OT_randomize_damage_recipe,
    DAF_OT_save_vip_damage,
    DAF_OT_save_damage_blueprint,
    DAF_OT_refresh_damage_blueprints,
    DAF_OT_apply_damage_blueprint,
)
