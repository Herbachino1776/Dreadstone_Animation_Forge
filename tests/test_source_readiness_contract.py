"""Regression tests for the source-readiness/authoring/export boundary."""

from __future__ import annotations

import ast
import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"
TRAUMA_PATH = PACKAGE / "trauma_field.py"
SPEC = importlib.util.spec_from_file_location("dreadstone_source_contract", TRAUMA_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load trauma_field.py for source-contract tests")
trauma_field = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trauma_field)


def source_contract() -> dict[str, object]:
    return {
        "schema": "dreadstone.source_readiness.v1",
        "analyzerRevision": "virtual_weld_v3.7.4",
        "analyzerBuildId": "initial-build",
        "generatedAtUtc": "2026-07-18T00:00:00Z",
        "ready": True,
        "sourceArmature": {
            "objectName": "Armature",
            "objectId": "arm-object-id",
            "dataName": "ArmatureData",
            "dataId": "arm-data-id",
            "armatureSha256": "armature-original",
            "semanticBoneMapping": {"head": "Head", "neck": "Neck"},
        },
        "sourceMeshes": [{
            "objectName": "Testman_Source",
            "objectId": "mesh-object-id",
            "dataName": "TestmanMesh",
            "dataId": "mesh-data-id",
            "topologySha256": "topology-original",
            "weightSha256": "weights-original",
        }],
        "sourceCollections": [{"name": "Imported_Source", "id": "source-collection-id"}],
        "analyzedObjectNames": ["Testman_Source"],
    }


def function_node(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


class SourceReadinessContractTests(unittest.TestCase):
    def test_initial_source_readiness_contract_is_valid(self) -> None:
        contract = source_contract()
        self.assertEqual(trauma_field.source_readiness_stale_reasons(contract, copy.deepcopy(contract)), [])

    def test_generated_assets_are_recognized_as_authoring_roles(self) -> None:
        for name in (
            "DSB_BODY_CORE",
            "DSB_ATTACHED_HEAD",
            "DSB_DETACHED_HEAD",
            "DSB_SEGMENT_HEAD",
            "DSB_STUMP_NECK_HEAD",
            "DSB_DAMAGE_RIG",
            "DSB_SOCKET_ABDOMEN_VISCERA",
            "DSB_SOURCE_MODEL_PROTECTED",
        ):
            with self.subTest(name=name):
                self.assertTrue(trauma_field.is_generated_authoring_role(name))
        self.assertFalse(trauma_field.is_generated_authoring_role("Testman_Source"))

    def test_explicit_generated_role_marker_is_excluded(self) -> None:
        self.assertTrue(trauma_field.is_generated_authoring_role("renamed", generated=True))
        self.assertTrue(trauma_field.is_generated_authoring_role("renamed", damage_role="body_core"))

    def test_intentional_generated_open_boundaries_do_not_stale_source(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["generatedOpenBoundaryCount"] = 128
        current["generatedContourStatus"] = "INTENTIONAL_OPEN_CUT"
        self.assertEqual(trauma_field.source_readiness_stale_reasons(expected, current), [])

    def test_generated_inventory_does_not_replace_source_inventory(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["generatedAnalyzedObjectNames"] = [
            "DSB_BODY_CORE", "DSB_ATTACHED_HEAD", "DSB_ATTACHED_FOREARM_L", "DSB_ATTACHED_FOREARM_R"
        ]
        self.assertEqual(trauma_field.source_readiness_stale_reasons(expected, current), [])
        self.assertEqual(current["analyzedObjectNames"], ["Testman_Source"])

    def test_generated_shape_keys_do_not_stale_source(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["generatedShapeKeys"] = ["left", "right", "front", "back"]
        self.assertEqual(trauma_field.source_readiness_stale_reasons(expected, current), [])

    def test_generated_trauma_stamps_do_not_stale_source(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["traumaStamps"] = [{"stampId": "left-impact", "enabled": True}]
        self.assertEqual(trauma_field.source_readiness_stale_reasons(expected, current), [])

    def test_generated_topology_does_not_stale_source(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["generatedTopologySha256"] = "cut-topology"
        self.assertEqual(trauma_field.source_readiness_stale_reasons(expected, current), [])

    def test_preview_actions_and_export_metadata_do_not_stale_source(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current.update({"previewState": "DETACHED", "actions": ["Walk"], "exportMetadata": {"glb": "x.glb"}})
        self.assertEqual(trauma_field.source_readiness_stale_reasons(expected, current), [])

    def test_source_topology_change_stales_with_exact_fingerprint(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["sourceMeshes"][0]["topologySha256"] = "topology-edited"  # type: ignore[index]
        reasons = trauma_field.source_readiness_stale_reasons(expected, current)
        self.assertEqual(len(reasons), 1)
        self.assertIn("Testman_Source topology fingerprint changed", reasons[0])
        self.assertIn("topology-original", reasons[0])
        self.assertIn("topology-edited", reasons[0])

    def test_source_relevant_weight_change_stales_with_exact_fingerprint(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["sourceMeshes"][0]["weightSha256"] = "weights-edited"  # type: ignore[index]
        reasons = trauma_field.source_readiness_stale_reasons(expected, current)
        self.assertEqual(len(reasons), 1)
        self.assertIn("relevant-weight fingerprint changed", reasons[0])
        self.assertIn("weights-original", reasons[0])
        self.assertIn("weights-edited", reasons[0])

    def test_source_armature_mapping_change_stales(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["sourceArmature"]["semanticBoneMapping"]["head"] = "Head.001"  # type: ignore[index]
        self.assertIn(
            "source armature semantic bone mapping changed",
            trauma_field.source_readiness_stale_reasons(expected, current),
        )

    def test_source_armature_edit_stales(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["sourceArmature"]["armatureSha256"] = "armature-edited"  # type: ignore[index]
        self.assertIn(
            "source armature fingerprint changed",
            trauma_field.source_readiness_stale_reasons(expected, current),
        )

    def test_analyzer_revision_change_stales_but_build_change_does_not(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["analyzerBuildId"] = "new-compatible-build"
        self.assertEqual(trauma_field.source_readiness_stale_reasons(expected, current), [])
        current["analyzerRevision"] = "virtual_weld_v4"
        self.assertTrue(trauma_field.source_readiness_stale_reasons(expected, current))

    def test_source_object_or_datablock_identity_loss_stales(self) -> None:
        expected = source_contract()
        missing = copy.deepcopy(expected)
        missing["sourceMeshes"] = []
        self.assertIn("identity was lost or replaced", " ".join(trauma_field.source_readiness_stale_reasons(expected, missing)))
        replaced = copy.deepcopy(expected)
        replaced["sourceMeshes"][0]["dataId"] = "replacement-data"  # type: ignore[index]
        self.assertIn("datablock identity was lost or replaced", " ".join(trauma_field.source_readiness_stale_reasons(expected, replaced)))

    def test_source_collection_identity_change_stales(self) -> None:
        expected = source_contract()
        current = copy.deepcopy(expected)
        current["sourceCollections"] = [{"name": "Other", "id": "other-id"}]
        self.assertIn("source collection identity changed", trauma_field.source_readiness_stale_reasons(expected, current))

    def test_four_head_keys_with_one_enabled_stamp_each_pass_stamp_contract(self) -> None:
        for key_name in ("left", "right", "front", "back"):
            with self.subTest(key_name=key_name):
                self.assertEqual(
                    trauma_field.enabled_stamp_contract_errors([{"stampId": key_name, "enabled": True}], key_name),
                    [],
                )

    def test_disabled_procedural_stack_is_a_genuine_authoring_error(self) -> None:
        self.assertEqual(
            trauma_field.enabled_stamp_contract_errors([{"stampId": "left", "enabled": False}], "left"),
            ["deformation key left has no enabled trauma stamp"],
        )
        self.assertEqual(trauma_field.enabled_stamp_contract_errors([], "legacy-manual"), [])

    def test_export_never_runs_or_writes_source_readiness(self) -> None:
        function = function_node(PACKAGE / "damage_authoring.py", "_export_asset")
        call_names = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        self.assertNotIn("build_damage_readiness_report", call_names)
        self.assertNotIn("write_damage_readiness_reports", call_names)
        self.assertNotIn("persist_source_readiness_contract", call_names)
        self.assertIn("_validate_authoring", call_names)

    def test_explicit_rerun_prefers_stored_contract_before_selection(self) -> None:
        source = (PACKAGE / "damage_readiness.py").read_text(encoding="utf-8")
        function = ast.get_source_segment(source, function_node(PACKAGE / "damage_readiness.py", "resolve_source_readiness_inputs")) or ""
        self.assertLess(function.index("load_source_readiness_contract()"), function.index("related(context)"))
        self.assertIn("return _resolve_authoring_state_objects(context, authoring_state)", function)

    def test_missing_original_source_blocks_without_generated_fallback(self) -> None:
        source = (PACKAGE / "damage_readiness.py").read_text(encoding="utf-8")
        self.assertIn("Restore the original source object; Forge will not fall back to generated authoring meshes.", source)
        self.assertIn("generated DSB_* meshes cannot replace it", source)

    def test_repair_operator_does_not_clear_or_mutate_authoring_work(self) -> None:
        function = function_node(PACKAGE / "damage_readiness.py", "persist_source_readiness_contract")
        repair = next(
            node for node in ast.parse((PACKAGE / "damage_readiness.py").read_text(encoding="utf-8")).body
            if isinstance(node, ast.ClassDef) and node.name == "DAF_OT_repair_source_readiness_contract"
        )
        text = ast.dump(repair) + ast.dump(function)
        self.assertIn("validate_source_readiness_contract", text)
        for forbidden in ("clear_damage_authoring", "deformation_authoring", "bpy.data.objects.remove"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
