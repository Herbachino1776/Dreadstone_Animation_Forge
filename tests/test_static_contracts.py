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
        identifiers = contracts.executable_identifiers(self.trees["deformation_authoring.py"])
        self.assertFalse(contracts.FORBIDDEN_TRANSFER_IDENTIFIERS & identifiers)


if __name__ == "__main__":
    unittest.main()
