import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"


def function_node(path, name):
    module = ast.parse(path.read_text(encoding="utf-8"))
    return next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name)


def call_names(node):
    return {
        call.func.attr if isinstance(call.func, ast.Attribute) else call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, (ast.Attribute, ast.Name))
    }


class DamagePreviewLifecycleTests(unittest.TestCase):
    def test_clear_is_atomic_and_non_destructive(self):
        path = PACKAGE / "deformation_authoring.py"
        function = function_node(path, "clear_damage_preview")
        calls = call_names(function)
        self.assertIn("clear_seed_preview", calls)
        self.assertIn("clear_surface_gore_preview", calls)
        self.assertIn("_zero_all_damage_preview_weights", calls)
        self.assertIn("_hide_all_generated_gore", calls)
        source = ast.get_source_segment(path.read_text(encoding="utf-8"), function) or ""
        self.assertNotIn("_remove_generated_gore_objects", source)
        self.assertNotIn("bpy.data.objects.remove", source)

    def test_gore_visibility_requires_matching_nonzero_morph(self):
        path = PACKAGE / "deformation_authoring.py"
        function = function_node(path, "_sync_generated_gore_visibility")
        source = ast.get_source_segment(path.read_text(encoding="utf-8"), function) or ""
        self.assertIn("actual_weight > 1e-8 and role_visible", source)
        self.assertIn("include_preview=True", source)
        for role in ("ATTACHED", "DETACHED", "CORE"):
            self.assertIn(role, source)

    def test_clear_hides_final_and_preview_only_gore(self):
        path = PACKAGE / "deformation_authoring.py"
        function = function_node(path, "_hide_all_generated_gore")
        source = ast.get_source_segment(path.read_text(encoding="utf-8"), function) or ""
        self.assertIn("include_preview=True", source)

    def test_per_key_toggle_synchronizes_stain_visibility(self):
        path = PACKAGE / "deformation_authoring.py"
        function = function_node(path, "apply_damage_key_previews")
        self.assertIn(
            "_sync_surface_stain_preview_visibility",
            call_names(function),
        )

    def test_export_snapshot_restores_in_finally(self):
        path = PACKAGE / "damage_authoring.py"
        function = function_node(path, "_export_asset")
        self.assertIn("capture_damage_preview_snapshot", call_names(function))
        try_nodes = [node for node in ast.walk(function) if isinstance(node, ast.Try)]
        self.assertTrue(try_nodes)
        self.assertTrue(any(
            "restore_damage_preview_snapshot" in call_names(statement)
            for node in try_nodes for statement in node.finalbody
        ))

    def test_primary_ui_has_per_key_preview_controls(self):
        panels = (PACKAGE / "ui" / "panels.py").read_text(encoding="utf-8")
        operators = (PACKAGE / "ui" / "operators" / "vip.py").read_text(encoding="utf-8")
        authoring = (PACKAGE / "deformation_authoring.py").read_text(encoding="utf-8")
        self.assertIn("VIP DAMAGE WORKFLOW", panels)
        self.assertIn("PREVIEW ON", panels)
        self.assertIn("PREVIEW OFF", panels)
        self.assertIn("depress=region_id == active_region_id", panels)
        self.assertIn("requested_key_name in current_key_names", panels)
        self.assertIn('bl_idname = "daf.toggle_damage_key_preview"', operators)
        self.assertIn("def apply_damage_key_previews(", authoring)

    def test_authoring_cache_invalidations_restore_damage_key_cards(self):
        path = PACKAGE / "deformation_authoring.py"
        invalidation = function_node(path, "_invalidate_geodesic_cache")
        file_load_clear = function_node(path, "_clear_service_caches")
        self.assertIn(
            "_refresh_authoring_ui_cache_safely",
            call_names(invalidation),
        )
        self.assertIn(
            "_refresh_authoring_ui_cache_safely",
            call_names(file_load_clear),
        )
        file_load_source = (
            ast.get_source_segment(
                path.read_text(encoding="utf-8"),
                file_load_clear,
            )
            or ""
        )
        self.assertIn('reason == "file load"', file_load_source)

    def test_create_damage_key_dispatches_face_or_vertex_selection(self):
        path = PACKAGE / "deformation_authoring.py"
        dispatcher = function_node(path, "_capture_current_mesh_selection")
        calls = call_names(dispatcher)
        self.assertIn("_capture_face_selection", calls)
        self.assertIn("_capture_vertex_selection", calls)
        dispatcher_source = (
            ast.get_source_segment(
                path.read_text(encoding="utf-8"), dispatcher
            )
            or ""
        )
        self.assertIn("mesh_select_mode", dispatcher_source)

        create = function_node(path, "create_impact_from_current_selection")
        create_calls = call_names(create)
        self.assertIn("_capture_current_mesh_selection", create_calls)
        self.assertIn("_refresh_authoring_ui_cache", create_calls)

    def test_multi_key_preview_resolves_paired_detached_mesh(self):
        path = PACKAGE / "deformation_authoring.py"
        function = function_node(path, "_enforce_damage_preview_weights")
        source = (
            ast.get_source_segment(
                path.read_text(encoding="utf-8"), function
            )
            or ""
        )
        self.assertIn(
            "attached, detached = _resolve_region_pair(region)",
            source,
        )
        self.assertNotIn("attached, _detached =", source)

    def test_additive_gore_composition_is_persisted_and_exposed(self):
        trauma = (PACKAGE / "trauma_field.py").read_text(encoding="utf-8")
        authoring = (PACKAGE / "deformation_authoring.py").read_text(encoding="utf-8")
        panels = (PACKAGE / "ui" / "panels.py").read_text(encoding="utf-8")
        for field in ("goreFiberTextureStrength", "goreBaseColorStrength"):
            self.assertIn(field, trauma)
            self.assertIn(field, authoring)
        self.assertIn("source_pixels[offset] * fiber_strength + float(base_color[0]) * color_strength", authoring)
        self.assertIn("deformation_gore_fiber_texture_strength", panels)
        self.assertIn("deformation_gore_base_color_strength", panels)

    def test_raised_builder_preserves_component_ownership_argument(self):
        path = PACKAGE / "deformation_authoring.py"
        function = function_node(path, "_build_gore_shell_object")
        self.assertIn("component", {argument.arg for argument in function.args.args + function.args.kwonlyargs})
        reassigned = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Name)
            and node.id == "component"
            and isinstance(node.ctx, ast.Store)
        ]
        self.assertFalse(
            reassigned,
            "The RAISED ownership argument must not be reused for local face islands.",
        )
        source = ast.get_source_segment(path.read_text(encoding="utf-8"), function) or ""
        self.assertIn(
            'obj["dsb_gore_component"] = str(component or "RAISED").upper()',
            source,
        )

    def test_vip_macro_preview_builds_current_stain_and_balanced_geometry(self):
        path = PACKAGE / "deformation_authoring.py"
        function = function_node(path, "_preview_stamp_stack")
        calls = call_names(function)
        self.assertIn("_install_surface_stain_preview", calls)
        self.assertIn("_build_preview_gore_for_entry", calls)
        source = (
            ast.get_source_segment(
                path.read_text(encoding="utf-8"), function
            )
            or ""
        )
        self.assertIn('quality in {"BALANCED", "FINAL"}', source)
        self.assertIn('"previewGoreObjectCount"', source)

        panels = (PACKAGE / "ui" / "panels.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("UPDATE GORE PREVIEW", panels)
        self.assertIn('"daf.refresh_impact_preview"', panels)
        self.assertIn(
            "FAST = live stain. BALANCED = live temporary gore geometry.",
            panels,
        )
        self.assertIn(
            "Save commits the approved look; it is not required to preview.",
            panels,
        )

    def test_preview_and_rebuild_enforce_final_world_displacement_cap(self):
        path = PACKAGE / "deformation_authoring.py"
        preview = function_node(path, "_preview_stamp_stack")
        rebuild = function_node(path, "rebuild_active_deformation")
        self.assertIn(
            "_clamp_local_coordinates_to_world_limit",
            call_names(preview),
        )
        self.assertIn(
            "_clamp_local_coordinates_to_world_limit",
            call_names(rebuild),
        )


if __name__ == "__main__":
    unittest.main()
