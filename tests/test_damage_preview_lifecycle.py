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
        for role in ("ATTACHED", "DETACHED", "CORE"):
            self.assertIn(role, source)

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

    def test_primary_ui_has_one_prominent_atomic_clear(self):
        panels = (PACKAGE / "ui" / "panels.py").read_text(encoding="utf-8")
        operators = (PACKAGE / "ui" / "operators" / "previews.py").read_text(encoding="utf-8")
        self.assertIn("CLEAR DAMAGE PREVIEW", panels)
        self.assertIn('bl_label = "CLEAR DAMAGE PREVIEW"', operators)
        self.assertIn("clear.alert = True", panels)

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


if __name__ == "__main__":
    unittest.main()
