"""Blender-free contracts for the 3.15 healing architecture."""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"


def load_standalone(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BASELINE_OPERATOR_IDS = set("""
daf.add_active_region_to_compound_event daf.add_trauma_stamp daf.adopt_imported_pack
daf.align_feet_to_floor daf.analyze daf.analyze_damage_readiness
daf.apply_heavy_gore_all_deformations daf.apply_surface_gore_preset
daf.approve_active_legacy daf.approve_draft daf.begin_deformation_sculpt
daf.build_active_deformation_preset daf.build_damage_authoring_asset
daf.capture_compound_impact_field daf.capture_deformation_cursor
daf.capture_deformation_selected_face daf.capture_deformation_selected_patch
daf.capture_deformation_selected_vertices daf.clear_compound_trauma_preview
daf.clear_current_generated_gore daf.clear_damage_authoring_asset
daf.clear_damage_seam_preview daf.clear_deformation_seed
daf.clear_surface_gore_overlay_preview daf.collapse daf.commit_deformation_seed
daf.create_blunt_gore_head_deformations daf.create_body_impact_starters
daf.create_damage_shape_key daf.create_forearm_impact_starter
daf.create_mirrored_deformation daf.create_preview_floor
daf.create_standard_head_deformations daf.delete_managed_deformation
daf.duplicate_trauma_stamp daf.export_damage_asset daf.finish_deformation_sculpt
daf.generate_mace_head_guards daf.hurt_left daf.hurt_right
daf.load_damage_readiness_handoff daf.load_trauma_stamp_library
daf.move_trauma_stamp_down daf.move_trauma_stamp_up daf.new_compound_trauma_event
daf.open_damage_export_folder daf.open_damage_markdown_report
daf.open_damage_report_folder daf.preview_active_trauma_stamp
daf.preview_compound_trauma_event daf.preview_damage_detached
daf.preview_damage_intact daf.preview_damage_seam daf.preview_deformation_seed
daf.preview_mace_guard_active daf.preview_surface_gore_overlay
daf.purge_unapproved_attempts daf.rebuild_active_deformation
daf.rebuild_all_generated_gore daf.rebuild_compound_trauma_event
daf.register_core_deformation_region daf.register_deformation_region
daf.remove_active_region_from_compound_event daf.remove_deformation_region
daf.remove_trauma_stamp daf.repair_legacy_pair_sync
daf.repair_source_readiness_contract daf.reset_pose_polish
daf.restore_imported_damage_intact_preview daf.safe_resize
daf.save_trauma_stamp_library daf.select_compound_trauma_event
daf.select_deformation_key daf.select_deformation_region daf.select_trauma_stamp
daf.show_deformation_attached daf.show_deformation_detached
daf.show_deformation_overlay daf.solo_deformation_key daf.toggle_trauma_stamp
daf.update_surface_gore_overlay daf.update_trauma_stamp
daf.validate_compound_trauma_event daf.validate_damage_authoring_asset
daf.validate_deformation_region daf.validate_deformations daf.validate_gore_geometry
daf.validate_mace_head_guards daf.walk daf.zero_deformations
""".split())


class HealingArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.performance = load_standalone(
            "forge_performance_contract", PACKAGE / "deformation" / "performance.py"
        )
        cls.registry = load_standalone(
            "forge_registry_contract", PACKAGE / "deformation" / "registry.py"
        )
        cls.workflow = load_standalone(
            "forge_workflow_contract", PACKAGE / "ui" / "workflow_state.py"
        )

    def test_baseline_operator_inventory_is_preserved_additively(self):
        actual = set()
        for path in PACKAGE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for item in node.body:
                    if isinstance(item, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "bl_idname"
                        for target in item.targets
                    ):
                        try:
                            value = ast.literal_eval(item.value)
                        except Exception:
                            continue
                        if isinstance(value, str) and value.startswith("daf."):
                            actual.add(value)
        self.assertEqual(len(BASELINE_OPERATOR_IDS), 90)
        self.assertTrue(BASELINE_OPERATOR_IDS <= actual, sorted(BASELINE_OPERATOR_IDS - actual))
        self.assertTrue({
            "daf.prepare_character_for_damage_authoring",
            "daf.create_impact_from_selection",
            "daf.commit_impact",
            "daf.revert_impact",
            "daf.write_forge_diagnostic_report",
        } <= actual)

    def test_scene_property_contract_is_additive(self):
        tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
        settings = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DAFSettings")
        names = {
            node.target.id for node in settings.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        baseline_critical = {
            "damage_readiness_output_directory", "damage_authoring_report_path",
            "damage_authoring_output_directory", "deformation_region",
            "deformation_active_key", "deformation_active_stamp_id",
            "deformation_capture_json", "deformation_seed_radius",
            "deformation_seed_depth", "deformation_seed_falloff",
            "deformation_gore_enabled", "deformation_gore_raised_enabled",
            "compound_active_event_id", "compound_event_seed",
            "source_readiness_contract_status", "last_damage_export_validation",
        }
        self.assertTrue(baseline_critical <= names)
        self.assertGreaterEqual(len(names), 186)

    def test_bounded_cache_evicts_and_invalidates(self):
        cache = self.registry.BoundedCache(2, "test")
        cache["a"] = 1
        cache["b"] = 2
        self.assertEqual(cache["a"], 1)
        cache["c"] = 3
        self.assertNotIn("b", cache)
        self.assertEqual(set(cache), {"a", "c"})
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_performance_report_and_relative_gates(self):
        report = {
            "schema": self.performance.SCHEMA,
            "blenderVersion": "5.1.2", "addonVersion": "3.15.0", "commit": "abc",
            "sourceAsset": {}, "resourceCounts": {}, "operations": [], "failures": [],
        }
        self.assertEqual(self.performance.validate_report(report), [])
        self.assertTrue(self.performance.relative_preview_gate(80.0, 20.0)["pass"])
        self.assertFalse(self.performance.relative_preview_gate(80.0, 50.0)["pass"])
        self.assertTrue(self.performance.no_regression_gate(100.0, 109.0)["pass"])
        self.assertFalse(self.performance.no_regression_gate(100.0, 111.0)["pass"])
        growth = self.performance.numeric_growth({"objects": 4}, {"objects": 4})
        self.assertTrue(self.performance.stable_growth(growth)["pass"])

    def test_property_callbacks_only_schedule_preview(self):
        tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
        for name in (
            "_deformation_preview_property_updated",
            "_deformation_metadata_property_updated",
            "_deformation_region_updated",
        ):
            node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
            source = ast.unparse(node)
            self.assertNotIn("rebuild_", source)
            self.assertNotIn("validate_", source)
            self.assertNotIn("preview_active_stamp", source)
            self.assertIn("request_", source)

    def test_task_panel_draw_has_no_geometry_or_metadata_writes(self):
        tree = ast.parse((PACKAGE / "ui" / "panels.py").read_text(encoding="utf-8"))
        source = ast.unparse(tree)
        called = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        for forbidden in (
            "topology_fingerprint", "rebuild_active_deformation", "validate_deformations",
            "json.loads", "json.dumps", "shape_key_add", "bpy.data", "bpy.ops",
        ):
            self.assertNotIn(forbidden, called)
        self.assertIn("cached_ui_summary", source)

    def test_preview_service_has_one_debounced_timer_and_stale_guard(self):
        source = (PACKAGE / "deformation" / "preview_service.py").read_text(encoding="utf-8")
        self.assertIn("QUIET_INTERVAL_SECONDS = 0.2", source)
        self.assertIn("if not _TIMER_REGISTERED:", source)
        self.assertIn("if token != _GENERATION:", source)
        self.assertIn("bpy.app.timers.unregister(_timer_callback)", source)
        self.assertIn("def _load_post", source)

    def test_diagnostics_are_cached_and_include_authoring_context(self):
        source = (PACKAGE / "deformation" / "diagnostics.py").read_text(encoding="utf-8")
        for contract in (
            '"activeContext"', '"validationStates"', '"captureStatus"',
            '"sourceReadiness"', '"authoring"', '"export"',
            "def cached_summary", "def refresh_summary",
        ):
            self.assertIn(contract, source)
        panels = (PACKAGE / "ui" / "panels.py").read_text(encoding="utf-8")
        self.assertIn("cached_diagnostics_summary", panels)

    def test_extension_install_defers_datablock_self_check(self):
        source = (PACKAGE / "deformation_authoring.py").read_text(encoding="utf-8")
        self.assertIn('if not hasattr(bpy.data, "objects"):', source)
        self.assertIn('"status": "DEFERRED"', source)

    def test_workflow_recommendations_derive_from_state(self):
        self.assertEqual(self.workflow.next_action({}), "Select a source character")
        state = {"sourceSelected": True}
        self.assertEqual(self.workflow.next_action(state), "Choose an output folder")
        state.update(outputFolderReady=True, sourceReadiness="SOURCE READY", authoringBuilt=True)
        self.assertEqual(self.workflow.next_action(state), "Select a region")
        state.update(activeRegion="head", captureReady=True)
        self.assertEqual(self.workflow.next_action(state), "Create Impact From Selection")
        state.update(activeKey="Head_Impact_v001", previewStatus="READY")
        self.assertEqual(self.workflow.next_action(state), "Adjust and Commit Impact")


if __name__ == "__main__":
    unittest.main()
