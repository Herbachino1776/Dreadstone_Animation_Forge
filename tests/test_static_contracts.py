"""Critical source-level contracts that do not require Blender."""

from __future__ import annotations

import ast
import importlib.util
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_addon as contracts  # noqa: E402


class StaticContractTests(unittest.TestCase):
    def test_packaged_gore_texture_set_and_atlas(self) -> None:
        root = ROOT / "dreadstone_animation_forge" / "assets" / "gore_textures"
        names = [
            "muscle_fibers_macro_rot_000.png",
            "muscle_fibers_macro_rot_090.png",
            "muscle_fibers_macro_rot_180.png",
            "muscle_fibers_macro_rot_270.png",
        ]
        for name in names:
            payload = (root / name).read_bytes()
            self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"), name)
        atlas = (root / "muscle_fibers_macro_atlas.png").read_bytes()
        self.assertTrue(atlas.startswith(b"\x89PNG\r\n\x1a\n"))
        source_size = struct.unpack(">II", (root / names[0]).read_bytes()[16:24])
        atlas_size = struct.unpack(">II", atlas[16:24])
        self.assertEqual(atlas_size, (source_size[0] * 2, source_size[1] * 2))

    def test_surface_gore_overlay_authoring_contract(self) -> None:
        for preset in (
            "Gore_Ooze_Wet",
            "Gore_Clot_Dark",
            "Gore_Smear_Heavy",
            "Gore_Speckled_Impact",
            "Gore_Crush_Bloodied",
            "Gore_Crush_Heavy_Clotted",
        ):
            self.assertIn(preset, self.trauma)
        for helper in (
            "def normalize_gore_overlay(",
            "def validate_gore_overlay(",
            "def gore_mask_value(",
            "def preview_surface_gore(",
            "def clear_surface_gore_preview(",
            "def raised_gore_face_records(",
            "def rebuild_raised_gore_for_key(",
            "def _raised_gore_errors(",
        ):
            self.assertIn(helper, self.trauma + self.deformation)
        for operator in (
            "daf.update_surface_gore_overlay",
            "daf.preview_surface_gore_overlay",
            "daf.clear_surface_gore_overlay_preview",
            "daf.create_blunt_gore_head_deformations",
            "daf.apply_heavy_gore_all_deformations",
            "daf.clear_current_generated_gore",
            "daf.rebuild_all_generated_gore",
            "daf.validate_gore_geometry",
            "daf.randomize_gore_seed",
        ):
            self.assertIn(operator, self.deformation)
        for key_name in (
            "Head_Impact_Left_v001",
            "Head_Impact_Right_v001",
            "Head_Impact_Front_v001",
            "Head_Impact_Back_v001",
        ):
            self.assertIn(key_name, self.deformation)
        self.assertIn('entry["surfaceGoreOverlay"] = overlay', self.deformation)
        self.assertIn('entry["goreOverlayDigest"]', self.deformation)
        self.assertIn('GORE_PREVIEW_ATTRIBUTE = "DSB_Surface_Gore_Mask"', self.deformation)
        self.assertIn('material = source.copy()', self.deformation)
        self.assertIn('clear_surface_gore_preview(all_regions=True)', self.deformation)
        self.assertIn('"generatedGoreMeshes"', self.deformation)
        self.assertIn('"goreActivationContract"', self.deformation)
        self.assertIn('obj["dsb_gore_default_visible"] = False', self.deformation)
        self.assertIn('obj["dsb_preview_only"] = False', self.deformation)
        self.assertIn('and obj.get("dsb_generated_role") == "raised_gore"', self.sources["damage_authoring.py"])
        self.assertIn('if not bool(obj.get("dsb_gore_owned", False)):', self.deformation)
        self.assertIn('if existing_recipe and existing_recipe.get("goreUserCustomized", False):', self.deformation)
        self.assertIn('def _region_gore_sources(', self.deformation)
        self.assertIn('return ((attached, "CORE"),)', self.deformation)
        self.assertIn(
            "allowed = {'ShaderNodeOutputMaterial', 'ShaderNodeBsdfPrincipled', 'ShaderNodeTexImage'}",
            self.deformation,
        )
        self.assertIn('GORE_TEXTURE_ATLAS_IMAGE = "DSB_Muscle_Fibers_Macro_Atlas"', self.deformation)
        self.assertIn('name="DSB_Gore_Texture_Variant"', self.deformation)
        self.assertIn('name="DSB_Gore_Layer"', self.deformation)
        self.assertIn('"ORGANIC_REFINED_TEXTURED_RIM_V3"', self.deformation)
        self.assertIn('emission.default_value = (0.0, 0.0, 0.0, 1.0)', self.deformation)
        self.assertIn('emission_strength.default_value = 0.0', self.deformation)
        self.assertIn('trauma_field.has_effective_emission(emission.default_value, strength)', self.deformation)
        self.assertIn('entry["raisedGoreStatus"] = "STALE_REBUILD_REQUIRED"', self.deformation)

    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = contracts.read_sources()
        cls.trees = contracts.parse_sources(cls.sources)
        cls.literals = contracts.string_literals(cls.trees.values())
        cls.deformation = cls.sources["deformation_authoring.py"]
        cls.trauma = cls.sources["trauma_field.py"]

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
        self.assertIn('version = "3.16.2"', manifest)
        builder = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        self.assertIn('ARCHIVE_ENTRIES = ("blender_manifest.toml", *MODULES', builder)
        self.assertNotIn('"dreadstone_animation_forge/__init__.py"', builder)
        spec = importlib.util.spec_from_file_location("forge_release_builder", ROOT / "scripts" / "build_release.py")
        release_builder = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(release_builder)
        expected_modules = tuple(sorted(
            path.relative_to(ROOT / "dreadstone_animation_forge").as_posix()
            for path in (ROOT / "dreadstone_animation_forge").rglob("*.py")
            if "__pycache__" not in path.parts
        ))
        self.assertEqual(release_builder.MODULES, expected_modules)
        self.assertEqual(release_builder.ARCHIVE_ENTRIES[0], "blender_manifest.toml")
        self.assertEqual(release_builder.ARCHIVE_ENTRIES[-2:], ("README.txt", "VALIDATION.txt"))
        self.assertIn("deformation/preview_service.py", release_builder.ARCHIVE_ENTRIES)
        self.assertIn("ui/operators/character.py", release_builder.ARCHIVE_ENTRIES)
        version = contracts.EXPECTED_VERSION
        self.assertEqual(
            f"Dreadstone_Animation_Forge_v{'_'.join(map(str, version))}.zip",
            "Dreadstone_Animation_Forge_v3_16_2.zip",
        )

    def test_authoritative_user_workflow_guide_contract(self) -> None:
        contracts.check_user_workflow_guide()
        guide = contracts.USER_GUIDE_PATH.read_text(encoding="utf-8")
        self.assertIn(contracts.current_version_string(), guide)
        self.assertIn(contracts.current_zip_name(), guide)
        for heading in contracts.REQUIRED_GUIDE_HEADINGS:
            with self.subTest(heading=heading):
                self.assertIn(heading, guide)
        for label in contracts.REQUIRED_GUIDE_UI_LABELS:
            with self.subTest(label=label):
                self.assertIn(label, guide)

    def test_release_readme_contains_install_quick_start_and_guide_reference(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for marker in (
            "3.16.2",
            "Dreadstone_Animation_Forge_v3_16_2.zip",
            "Install from Disk",
            "## Quick start",
            "docs/USER_WORKFLOW_GUIDE.md",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, readme)
        builder = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        self.assertIn('(ROOT / "README.md").read_text', builder)

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
        self.assertIn('detached_controls.operator("daf.show_deformation_overlay", text="Both"', self.deformation)

    def test_visibility_normalization_is_pair_scoped_and_viewport_only(self) -> None:
        tree = self.trees["deformation_authoring.py"]
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_set_authoring_view"
        )
        attributes = {node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)}
        self.assertIn("hide_viewport", attributes)
        self.assertIn("hide_set", attributes)
        self.assertNotIn("hide_render", attributes)
        self.assertIn("layer_collection.exclude = False", self.deformation)
        self.assertIn("def _visibility_blocker(context, obj):", self.deformation)

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

    def test_legacy_pair_repair_operator_and_strict_sync_metadata(self) -> None:
        operators = contracts.operator_contracts([self.trees["deformation_authoring.py"]])
        self.assertEqual(operators.get("daf.repair_legacy_pair_sync"), "Repair Legacy Pair Sync")
        self.assertIn('text="REPAIR LEGACY PAIR SYNC"', self.deformation)
        self.assertIn("def repair_legacy_pair_sync(", self.deformation)
        self.assertIn("_sync_exact_index_key_pair(attached, detached, name)", self.deformation)
        self.assertIn("if before <= SYNC_TOLERANCE:", self.deformation)
        self.assertIn("if _region_mode(region) == PAIRED_SEGMENT and max_delta_error > SYNC_TOLERANCE:", self.deformation)
        for field in (
            "legacySyncStatus",
            "legacySyncErrorBefore",
            "legacySyncErrorAfter",
            "legacySyncRepairApplied",
        ):
            self.assertIn(field, self.deformation)

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
            "daf.save_trauma_stamp_library",
            "daf.load_trauma_stamp_library",
        }
        self.assertTrue(required <= set(operators))

    def test_portable_stamp_library_is_analytically_rebound_and_non_destructive(self) -> None:
        self.assertIn('STAMP_LIBRARY_SCHEMA = "dreadstone.trauma_stamp_library.v1"', self.trauma)
        self.assertIn("def normalize_stamp_library(", self.trauma)
        self.assertIn("def stamp_library_compatibility_errors(", self.trauma)
        self.assertIn("def match_positional_anchors(", self.trauma)
        self.assertIn("def portable_anchor_tolerance(", self.trauma)
        self.assertIn("def build_current_stamp_library():", self.deformation)
        self.assertIn("def save_stamp_library(filepath):", self.deformation)
        self.assertIn("def load_stamp_library(filepath, context):", self.deformation)
        self.assertIn("topology does not match the current attached mesh", self.trauma)
        self.assertIn('"ANALYTICAL_POSITIONAL_ANCHORS"', self.deformation)
        self.assertIn('"portableVertexAnchorsLocal"', self.deformation)
        self.assertIn('"portableFaceAnchorsLocal"', self.deformation)
        self.assertIn("Forge never overwrites authored stamp stacks", self.deformation)
        self.assertIn('text="Save Stamp Library..."', self.deformation)
        self.assertIn('text="Load Stamp Library..."', self.deformation)

    def test_preview_and_rebuild_are_separate_operations(self) -> None:
        self.assertIn("def preview_active_stamp(context, quiet=False):", self.deformation)
        self.assertIn("def rebuild_active_deformation(context):", self.deformation)
        self.assertIn("_basis_world_positions(attached)", self.deformation)
        self.assertIn("clear_seed_preview()", self.deformation)
        self.assertIn("REBUILT FROM BASIS", self.deformation)

    def test_capture_connectivity_and_geodesic_cache_are_revalidated(self) -> None:
        self.assertIn("def _captured_face_component_count(attached, face_indices, virtual_weld=None):", self.deformation)
        self.assertIn("Captured face patch contains disconnected islands", self.deformation)
        self.assertIn("current_topology != cache_context", self.deformation)
        self.assertIn("_invalidate_geodesic_cache()", self.deformation)
        self.assertIn('cache_context["virtualWeldDigest"]', self.deformation)
        self.assertIn('cache_context["virtualWeldTolerance"]', self.deformation)

    def test_virtual_weld_capture_and_geodesic_contracts(self) -> None:
        for marker in (
            "def build_virtual_weld_map(",
            "def virtualize_edges(",
            "def virtual_face_components(",
            "virtual_members: Sequence[Sequence[int]] | None = None",
            '"virtualWeldDigest"',
            '"virtualWeldTolerance"',
        ):
            self.assertIn(marker, self.trauma)
        for marker in (
            "trauma_field.build_virtual_weld_map",
            "trauma_field.virtual_face_components",
            'virtual_members=virtual_weld["virtual_members"]',
            '"virtualWeldTolerance"',
            '"virtualWeldDigest"',
            '"virtualConnectedComponentCount"',
        ):
            self.assertIn(marker, self.deformation)

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

    def test_prior_hotfix_documentation_contracts_remain_preserved(self) -> None:
        documentation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "README.md",
                ROOT / "CHANGELOG.md",
                ROOT / "docs" / "DEVELOPMENT.md",
                ROOT / "docs" / "USER_WORKFLOW_GUIDE.md",
            )
        )
        for marker in (
            "3.10.1",
            "missing legacy keys are not recreated",
            "unrepairable attached keys are not overwritten",
            "analytical only",
            "no Blender mesh merge",
            "does not rewrite render/export visibility",
        ):
            self.assertIn(marker, documentation)


if __name__ == "__main__":
    unittest.main()
