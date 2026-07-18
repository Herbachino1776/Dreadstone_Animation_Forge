"""Critical source-level contracts that do not require Blender."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_addon as contracts  # noqa: E402


class StaticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = contracts.read_sources()
        cls.trees = contracts.parse_sources(cls.sources)
        cls.literals = contracts.string_literals(cls.trees.values())
        cls.deformation = cls.sources["deformation_authoring.py"]

    def test_addon_and_deformation_version(self) -> None:
        self.assertEqual(
            contracts.read_bl_info_version(self.trees["__init__.py"]),
            contracts.EXPECTED_VERSION,
        )
        self.assertEqual(
            tuple(contracts.literal_assignment(self.trees["deformation_authoring.py"], "DEFORMATION_VERSION")),
            contracts.EXPECTED_VERSION,
        )

    def test_preserved_component_build_identifiers(self) -> None:
        self.assertEqual(
            contracts.literal_assignment(self.trees["damage_readiness.py"], "ANALYZER_BUILD_ID"),
            contracts.EXPECTED_READINESS_BUILD,
        )
        self.assertEqual(
            contracts.literal_assignment(self.trees["damage_authoring.py"], "AUTHORING_BUILD_ID"),
            contracts.EXPECTED_AUTHORING_BUILD,
        )
        self.assertEqual(
            contracts.literal_assignment(self.trees["deformation_authoring.py"], "DEFORMATION_BUILD_ID"),
            contracts.EXPECTED_DEFORMATION_BUILD,
        )

    def test_required_package_modules_exist(self) -> None:
        self.assertEqual(set(self.sources), set(contracts.MODULE_NAMES))
        self.assertIn("trauma_field.py", self.sources)
        self.assertTrue(contracts.MANIFEST_PATH.is_file())

    def test_blender_extension_manifest_and_zip_root_layout(self) -> None:
        manifest = contracts.MANIFEST_PATH.read_text(encoding="utf-8")
        self.assertIn('schema_version = "1.0.0"', manifest)
        self.assertIn('id = "dreadstone_animation_forge"', manifest)
        self.assertIn('version = "3.10.0"', manifest)
        builder = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        self.assertIn('"blender_manifest.toml",\n    "__init__.py",', builder)
        self.assertNotIn('"dreadstone_animation_forge/__init__.py"', builder)

    def test_manifest_schemas(self) -> None:
        self.assertTrue(contracts.REQUIRED_SCHEMAS <= self.literals)

    def test_generated_dsb_object_names(self) -> None:
        self.assertTrue(contracts.REQUIRED_OBJECT_NAMES <= self.literals)

    def test_required_seams(self) -> None:
        self.assertTrue(contracts.REQUIRED_SEAMS <= self.literals)

    def test_standard_deformation_keys(self) -> None:
        self.assertTrue(contracts.REQUIRED_DEFORMATION_KEYS <= self.literals)

    def test_required_operator_identifiers_and_labels(self) -> None:
        actual = contracts.operator_contracts(self.trees.values())
        for operator_id, label in contracts.REQUIRED_OPERATORS.items():
            with self.subTest(operator_id=operator_id):
                self.assertEqual(actual.get(operator_id), label)

    def test_world_space_seed_radius_and_depth(self) -> None:
        for marker in (
            "center_world = attached.matrix_world @ center_local",
            "basis_world = attached.matrix_world @ basis_local",
            "distance = offset_world.length",
            "result_world = basis_world + displacement_world",
            "coordinates.append(inverse_world @ result_world)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.deformation)

    def test_world_space_paired_delta_comparison(self) -> None:
        self.assertIn(
            "delta_a = _local_delta_to_world(attached, attached_key.data[index].co - attached_basis.data[index].co)",
            self.deformation,
        )
        self.assertIn(
            "delta_d = _local_delta_to_world(detached, detached_key.data[index].co - detached_basis.data[index].co)",
            self.deformation,
        )
        self.assertIn("(delta_a - delta_d).length", self.deformation)

    def test_maximum_displacement_is_measured_in_world_space(self) -> None:
        self.assertIn("def _max_displacement(obj, name):", self.deformation)
        self.assertIn(
            "_local_delta_to_world(obj, key.data[i].co - basis.data[i].co).length",
            self.deformation,
        )

    def test_exact_index_attached_detached_sync(self) -> None:
        self.assertIn("for index in range(len(attached_key.data)):", self.deformation)
        self.assertIn("attached_key.data[index].co", self.deformation)
        self.assertIn("detached_key.data[index].co", self.deformation)
        self.assertIn("delta_world = _local_delta_to_world(attached, delta_attached_local)", self.deformation)
        self.assertIn("delta_detached_local = _world_delta_to_local(detached, delta_world)", self.deformation)

    def test_attached_detached_and_overlay_preview_controls(self) -> None:
        operators = contracts.operator_contracts([self.trees["deformation_authoring.py"]])
        self.assertEqual(operators["daf.show_deformation_attached"], "Show Attached")
        self.assertEqual(operators["daf.show_deformation_detached"], "Show Detached")
        self.assertEqual(operators["daf.show_deformation_overlay"], "Show Both")
        self.assertIn('row.operator("daf.show_deformation_overlay", text="Both"', self.deformation)

    def test_build_active_preset_and_zero_weight_contracts(self) -> None:
        self.assertIn('bl_idname = "daf.build_active_deformation_preset"', self.deformation)
        self.assertIn('text="BUILD ACTIVE PRESET"', self.deformation)
        self.assertIn("attached_key.value = 0.0", self.deformation)
        self.assertIn("_zero_managed_weights(attached)", self.deformation)
        self.assertIn("outward_world * rim", self.deformation)

    def test_optional_sculpt_operators(self) -> None:
        self.assertIn('bl_idname = "daf.begin_deformation_sculpt"', self.deformation)
        self.assertIn('bl_idname = "daf.finish_deformation_sculpt"', self.deformation)
        self.assertIn("Sculpting is optional", self.deformation)

    def test_glb_morph_export_flags(self) -> None:
        pairs = contracts.dict_literal_pairs(self.trees["damage_authoring.py"])
        self.assertIn(("export_morph", True), pairs)
        self.assertIn(("export_morph_normal", True), pairs)

    def test_no_nearest_neighbor_pair_transfer(self) -> None:
        identifiers = (
            contracts.executable_identifiers(self.trees["deformation_authoring.py"])
            | contracts.executable_identifiers(self.trees["trauma_field.py"])
        )
        self.assertFalse(contracts.FORBIDDEN_TRANSFER_IDENTIFIERS & identifiers)

    def test_trauma_field_modes_and_exact_families(self) -> None:
        tree = self.trees["trauma_field.py"]
        self.assertEqual(set(contracts.literal_assignment(tree, "TRAUMA_FAMILIES")), contracts.REQUIRED_TRAUMA_FAMILIES)
        self.assertEqual(set(contracts.literal_assignment(tree, "PLACEMENT_MODES")), contracts.REQUIRED_CAPTURE_MODES)
        self.assertEqual(set(contracts.literal_assignment(tree, "INFLUENCE_MODES")), contracts.REQUIRED_INFLUENCE_MODES)
        self.assertEqual(set(contracts.literal_assignment(tree, "DISTANCE_MODES")), contracts.REQUIRED_DISTANCE_MODES)

    def test_region_registry_and_legacy_head_migration_contracts(self) -> None:
        source = self.deformation
        self.assertIn('REGISTRY_PROPERTY = "dsb_deformation_region_registry_json"', source)
        self.assertIn('record = _record_from_pair("head", attached, detached, "head_neck")', source)
        self.assertIn('"recipeStatus": "LEGACY_MANUAL"', source)
        self.assertIn('"legacy": True', source)
        for key_name in contracts.REQUIRED_DEFORMATION_KEYS:
            self.assertIn(key_name, self.literals)

    def test_capture_and_stamp_stack_operators(self) -> None:
        operators = contracts.operator_contracts([self.trees["deformation_authoring.py"]])
        required = {
            "daf.register_deformation_region",
            "daf.validate_deformation_region",
            "daf.remove_deformation_region",
            "daf.capture_deformation_selected_patch",
            "daf.capture_deformation_selected_vertices",
            "daf.add_trauma_stamp",
            "daf.duplicate_trauma_stamp",
            "daf.remove_trauma_stamp",
            "daf.move_trauma_stamp_up",
            "daf.move_trauma_stamp_down",
            "daf.toggle_trauma_stamp",
            "daf.select_trauma_stamp",
            "daf.preview_active_trauma_stamp",
            "daf.rebuild_active_deformation",
        }
        self.assertTrue(required <= set(operators))

    def test_preview_and_rebuild_are_separate_operations(self) -> None:
        self.assertIn("def preview_active_stamp(context, quiet=False):", self.deformation)
        self.assertIn("def rebuild_active_deformation(context):", self.deformation)
        self.assertIn("_basis_world_positions(attached)", self.deformation)
        self.assertIn("clear_seed_preview()", self.deformation)
        self.assertIn("REBUILT FROM BASIS", self.deformation)

    def test_capture_connectivity_and_geodesic_cache_are_revalidated(self) -> None:
        self.assertIn("def _captured_face_component_count(attached, face_indices):", self.deformation)
        self.assertIn("Captured face patch contains disconnected islands", self.deformation)
        self.assertIn("current_topology != cache_context", self.deformation)
        self.assertIn("_invalidate_geodesic_cache()", self.deformation)

    def test_additive_deformation_manifest_fields(self) -> None:
        for marker in (
            '"registeredRegions"',
            '"activeRegionId"',
            '"authoredRegionIds"',
            '"orderedStamps"',
            '"maximumPairDeltaError"',
            '"validationStatus"',
        ):
            self.assertIn(marker, self.deformation)
        self.assertIn("dreadstone.damage_deformation.v1", self.literals)

    def test_core_active_region_operations_do_not_resolve_head_constants(self) -> None:
        protected_functions = {
            "_resolve_active_region",
            "_stamp_weights",
            "_stamp_local_coordinates",
            "preview_active_stamp",
            "rebuild_active_deformation",
            "sync_key_to_detached",
        }
        for node in self.trees["deformation_authoring.py"].body:
            if isinstance(node, ast.FunctionDef) and node.name in protected_functions:
                identifiers = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
                with self.subTest(function=node.name):
                    self.assertNotIn("ATTACHED_HEAD_NAME", identifiers)
                    self.assertNotIn("DETACHED_HEAD_NAME", identifiers)

    def test_workflows_do_not_hardcode_versioned_dreadstone_zip_names(self) -> None:
        hardcoded_zip = r"Dreadstone_Animation_Forge_v\d+(?:[_.]\d+){2}(?:\.zip)?"
        workflows = (
            ROOT / ".github" / "workflows" / "validate.yml",
            ROOT / ".github" / "workflows" / "release.yml",
        )
        for workflow in workflows:
            with self.subTest(workflow=workflow.name):
                source = workflow.read_text(encoding="utf-8")
                self.assertNotRegex(source, hardcoded_zip)


if __name__ == "__main__":
    unittest.main()
