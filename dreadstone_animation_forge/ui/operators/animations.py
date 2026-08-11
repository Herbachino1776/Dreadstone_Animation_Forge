"""VIP saved-animation library operators."""

from __future__ import annotations

from bpy.props import StringProperty
from bpy.types import Operator


def _armature(context):
    from ... import find_armature

    return find_armature(context)


class _AnimationLibraryOperator(Operator):
    def failed(self, exc):
        context = getattr(self, "_context", None)
        scene = getattr(context, "scene", None)
        settings = getattr(scene, "daf_settings", None)
        if settings is not None:
            settings.animation_library_status = f"ERROR — {exc}"
        self.report({"ERROR"}, str(exc))
        return {"CANCELLED"}


class DAF_OT_animation_library_select(_AnimationLibraryOperator):
    bl_idname = "daf.animation_library_select"
    bl_label = "Select Saved Animation"
    bl_description = "Select this saved Action in the VIP animation library"
    bl_options = {"REGISTER"}

    action_name: StringProperty()

    def execute(self, context):
        from ... import animation_library

        self._context = context
        try:
            action = context.blend_data.actions.get(self.action_name)
            if action is None:
                raise RuntimeError("The selected animation no longer exists.")
            animation_library.select_action(
                context.scene.daf_settings,
                action,
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_animation_library_play(_AnimationLibraryOperator):
    bl_idname = "daf.animation_library_play"
    bl_label = "Play Saved Animation"
    bl_description = "Assign the selected saved Action, set its exact frame range, and start playback"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ... import animation_library

        self._context = context
        try:
            armature = _armature(context)
            settings = context.scene.daf_settings
            source = animation_library.selected_action(settings, armature)
            if source is None:
                raise RuntimeError("Select a saved animation first.")
            action = source
            if (
                str(source.get(animation_library.CLIP_ID_PROPERTY, ""))
                == str(settings.animation_library_edit_source_clip_id)
            ):
                action = (
                    context.blend_data.actions.get(
                        settings.animation_library_edit_draft
                    )
                    or source
                )
            result = animation_library.play_action(
                context,
                armature,
                action,
                start_playback=True,
            )
            animation_library.select_action(settings, source)
            settings.animation_library_status = (
                f"PLAYING {'DRAFT' if action != source else 'SAVED'} — "
                f"{source.name}"
            )
            self.report(
                {"INFO"},
                f"Playing {source.name}: "
                f"{result['frameStart']}–{result['frameEnd']}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_animation_library_edit(_AnimationLibraryOperator):
    bl_idname = "daf.animation_library_edit"
    bl_label = "Edit Saved Animation"
    bl_description = "Open a safe draft copy, restore its saved custom controls when available, and enter Pose Mode"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import animation_library

        self._context = context
        try:
            armature = _armature(context)
            source = animation_library.selected_action(
                context.scene.daf_settings,
                armature,
            )
            if source is None:
                raise RuntimeError("Select a saved animation first.")
            if not bool(source.get("dsb_draft", False)):
                from ... import variant_authoring

                variant_authoring.require_regular_action_edit_allowed(
                    source,
                    context.scene,
                )
            result = (
                animation_library.edit_existing_draft(
                    context,
                    armature,
                    source,
                )
                if bool(source.get("dsb_draft", False))
                else animation_library.begin_edit(
                    context,
                    armature,
                    source,
                )
            )
            self.report(
                {"INFO"},
                (
                    f"Editing unsaved draft {result['draft']}."
                    if result.get("draftOnly")
                    else
                    f"Editing {result['source']} in {result['draft']}."
                ),
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_animation_library_finalize_draft(
    _AnimationLibraryOperator
):
    bl_idname = "daf.animation_library_finalize_draft"
    bl_label = "Save Draft as Animation"
    bl_description = "Finalize the selected current draft as a protected saved animation"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import animation_library, approve_draft_action

        self._context = context
        try:
            armature = _armature(context)
            settings = context.scene.daf_settings
            draft = animation_library.selected_action(
                settings,
                armature,
            )
            if draft is None or not bool(
                draft.get("dsb_draft", False)
            ):
                raise RuntimeError("Select a current animation draft first.")
            kind = animation_library.infer_action_kind(draft)
            action = approve_draft_action(context, kind)
            animation_library.select_action(settings, action)
            settings.animation_library_status = (
                f"SAVED NEW — {action.name}"
            )
            self.report(
                {"INFO"},
                f"Saved finalized animation: {action.name}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_animation_library_save(_AnimationLibraryOperator):
    bl_idname = "daf.animation_library_save"
    bl_label = "Save / Overwrite Animation"
    bl_description = "Overwrite the selected saved Action with the current edit draft and reconnect Action/NLA users"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from ... import animation_library

        self._context = context
        try:
            result = animation_library.save_edit(
                context,
                _armature(context),
            )
            self.report(
                {"INFO"},
                f"Overwrote saved animation: {result['action']}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_animation_library_cancel_edit(_AnimationLibraryOperator):
    bl_idname = "daf.animation_library_cancel_edit"
    bl_label = "Cancel Animation Edit"
    bl_description = "Discard the edit draft and restore the untouched saved Action"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import animation_library

        self._context = context
        try:
            result = animation_library.cancel_edit(
                context,
                _armature(context),
            )
            self.report(
                {"INFO"},
                f"Discarded draft; restored {result['action']}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_animation_library_delete(_AnimationLibraryOperator):
    bl_idname = "daf.animation_library_delete"
    bl_label = "Delete Saved Animation"
    bl_description = "Remove the selected saved Action from the character, including its NLA strip references"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from ... import animation_library

        self._context = context
        try:
            armature = _armature(context)
            action = animation_library.selected_action(
                context.scene.daf_settings,
                armature,
            )
            if action is None:
                raise RuntimeError("Select a saved animation first.")
            from ... import variant_authoring

            status = variant_authoring.action_status(action, context.scene)
            if status in {"SHARED", "INHERITED"}:
                raise RuntimeError(
                    "Shared family Actions cannot be deleted from a variant. "
                    "Create an override or leave family authoring before deleting shared content."
                )
            result = animation_library.delete_action(
                context,
                armature,
                action,
            )
            self.report(
                {"INFO"},
                f"Deleted animation: {result['action']}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_animation_library_export(_AnimationLibraryOperator):
    bl_idname = "daf.animation_library_export"
    bl_label = "Export Selected Clip"
    bl_description = "Export the selected saved Action as a native .blend clip plus a readable compatibility manifest"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ... import animation_library

        self._context = context
        try:
            settings = context.scene.daf_settings
            armature = _armature(context)
            action = animation_library.selected_action(
                settings,
                armature,
            )
            if action is None:
                raise RuntimeError("Select a saved animation first.")
            result = animation_library.export_action_clip(
                context,
                armature,
                action,
                settings.animation_clip_directory,
            )
            self.report(
                {"INFO"},
                f"Exported clip: {result['blendPath']}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


class DAF_OT_animation_library_import(_AnimationLibraryOperator):
    bl_idname = "daf.animation_library_import"
    bl_label = "Import Animation Clip"
    bl_description = "Import a native Forge animation clip after bone, hierarchy, and rest-pose compatibility checks"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from ... import animation_library

        self._context = context
        try:
            settings = context.scene.daf_settings
            result = animation_library.import_action_clip(
                context,
                _armature(context),
                settings.animation_clip_import_path,
            )
            warning_count = sum(
                len(report["warnings"])
                for report in result["reports"]
            )
            message = (
                f"Imported {len(result['actions'])} animation clip(s)"
                + (
                    f" with {warning_count} compatibility warning(s)."
                    if warning_count
                    else "."
                )
            )
            self.report(
                {"WARNING"} if warning_count else {"INFO"},
                message,
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(exc)


CLASSES = (
    DAF_OT_animation_library_select,
    DAF_OT_animation_library_play,
    DAF_OT_animation_library_edit,
    DAF_OT_animation_library_finalize_draft,
    DAF_OT_animation_library_save,
    DAF_OT_animation_library_cancel_edit,
    DAF_OT_animation_library_delete,
    DAF_OT_animation_library_export,
    DAF_OT_animation_library_import,
)
