"""Blender-independent raised-gore recipe, distribution, digest, and budget tests."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "dreadstone_animation_forge" / "trauma_field.py"
SPEC = importlib.util.spec_from_file_location("dreadstone_raised_gore", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load trauma_field.py")
trauma_field = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trauma_field)


def grid_surface(width: int = 7, height: int = 7):
    positions = [(x * 0.01, y * 0.01, 0.0) for y in range(height) for x in range(width)]
    faces = []
    for y in range(height - 1):
        for x in range(width - 1):
            first = y * width + x
            faces.append((first, first + 1, first + width + 1, first + width))
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    weights = []
    for y in range(height):
        for x in range(width):
            distance = abs(x - center_x) + abs(y - center_y)
            weights.append(max(0.0, 1.0 - distance / (width * 0.82)))
    displacement = [weight * 0.026 for weight in weights]
    return positions, faces, weights, displacement


def heavy_overlay(seed: int = 1776, region: str = "torso"):
    return trauma_field.default_gore_overlay(
        "Gore_Crush_Heavy_Clotted",
        enabled=True,
        region_id=region,
        linked_stamp_id="stamp_generic",
        selection_hash="capture_hash",
        topology_fingerprint="a" * 64,
        seed=seed,
    )


def heavy_records(seed: int = 1776):
    positions, faces, weights, displacement = grid_surface()
    overlay = heavy_overlay(seed)
    records = trauma_field.raised_gore_face_records(
        positions, faces, weights, displacement, overlay
    )
    return positions, faces, overlay, records


def stamp_recipe():
    return trauma_field.normalize_stamp({
        "stampId": "stamp_generic",
        "displayName": "Generic Impact",
        "family": "BROAD_CAVE",
        "placementMode": "SELECTED_FACE_PATCH",
        "capture": {"selectionHash": "capture_hash"},
        "center": [0.0, 0.0, 0.0],
        "direction": [0.0, 0.0, -1.0],
        "radius": 0.1,
        "depth": 0.03,
        "falloff": 1.4,
        "influenceMode": "CONNECTED_SURFACE",
        "distanceMode": "SURFACE_DISTANCE",
        "featherDistance": 0.02,
        "seamProtection": 0.01,
        "strength": 1.0,
        "maximumDisplacement": 0.08,
        "orderIndex": 0,
    })


def library_with_overlay(overlay):
    stamp = stamp_recipe()
    return trauma_field.build_stamp_library(
        [{
            "regionId": "torso",
            "sourceAttachedObject": "DSB_ATTACHED_TORSO",
            "sourceDetachedObject": "DSB_SEGMENT_TORSO",
            "topologyFingerprint": "a" * 64,
            "vertexCount": 49,
            "polygonCount": 36,
            "keys": [{
                "name": "Torso_Impact_v001",
                "maximumInfluence": 1.0,
                "maximumDisplacement": 0.08,
                "stamps": [stamp],
                "surfaceGoreOverlay": overlay,
                "goreOverlayDigest": trauma_field.gore_overlay_digest(overlay),
            }],
        }],
        "3.13.0",
        "test-raised-gore",
    )


class RaisedGoreTests(unittest.TestCase):
    def test_heavy_preset_defaults_are_high_intensity(self):
        overlay = heavy_overlay()
        self.assertEqual(overlay["gorePresetId"], "Gore_Crush_Heavy_Clotted")
        self.assertEqual(overlay["goreOverlayMode"], "STAIN_AND_RAISED")
        self.assertEqual(overlay["goreIntensityClass"], "HIGH")
        self.assertTrue(overlay["goreRaisedEnabled"])
        self.assertGreaterEqual(overlay["goreCoreDensity"], 0.9)
        self.assertGreater(overlay["goreClotThickness"], overlay["goreSurfaceOffset"])

    def test_raised_recipe_json_round_trip(self):
        overlay = heavy_overlay(seed=42)
        self.assertEqual(
            trauma_field.normalize_gore_overlay(json.loads(json.dumps(overlay))),
            overlay,
        )

    def test_legacy_312_recipe_migrates_to_stain_only(self):
        legacy = {
            "goreOverlayEnabled": True,
            "gorePresetId": "Gore_Crush_Bloodied",
            **trauma_field.GORE_PRESETS["Gore_Crush_Bloodied"],
            "goreMaskSeed": 88,
            "linkedRegionId": "head",
            "linkedStampId": "head_0",
            "linkedSelectionHash": "capture",
            "linkedCaptureTopologyFingerprint": "b" * 64,
        }
        migrated = trauma_field.normalize_gore_overlay(legacy)
        self.assertEqual(migrated["goreRecipeVersion"], 2)
        self.assertEqual(migrated["goreOverlayMode"], "SURFACE_STAIN")
        self.assertFalse(migrated["goreRaisedEnabled"])

    def test_geometry_face_selection_is_deterministic(self):
        _positions, _faces, _overlay, first = heavy_records(1001)
        _positions, _faces, _overlay, second = heavy_records(1001)
        self.assertEqual(first, second)
        self.assertTrue(first)

    def test_thickness_values_are_deterministic_and_varied(self):
        _positions, _faces, _overlay, records = heavy_records(2002)
        values = [record["thickness"] for record in records]
        self.assertEqual(values, [record["thickness"] for record in heavy_records(2002)[3]])
        self.assertGreater(len(set(values)), 2)

    def test_seed_changes_geometry_breakup(self):
        first = [record["faceIndex"] for record in heavy_records(1)[3]]
        second = [record["faceIndex"] for record in heavy_records(2)[3]]
        self.assertNotEqual(first, second)

    def test_heavy_selection_retains_clean_face_gaps(self):
        _positions, faces, _overlay, records = heavy_records(1776)
        self.assertGreater(len(records), 0)
        self.assertLess(len(records), len(faces))

    def test_material_classification_uses_all_three_families(self):
        material_ids = {record["materialId"] for record in heavy_records(1776)[3]}
        self.assertEqual(material_ids, set(trauma_field.GORE_MATERIAL_IDS))

    def test_generated_object_names_are_stable(self):
        first = trauma_field.gore_generated_object_name("torso", "Impact_v001", "ATTACHED")
        second = trauma_field.gore_generated_object_name("torso", "Impact_v001", "ATTACHED")
        self.assertEqual(first, second)
        self.assertEqual(first, "DSB_GORE_ATTACHED_torso_Impact_v001")

    def test_generated_names_are_safe_and_bounded(self):
        name = trauma_field.gore_generated_object_name("left arm!" * 8, "impact?" * 10, "DETACHED")
        self.assertLessEqual(len(name), 63)
        self.assertTrue(name.startswith("DSB_GORE_DETACHED_"))
        self.assertNotIn("!", name)

    def test_generated_name_rejects_unknown_pair_role(self):
        with self.assertRaisesRegex(ValueError, "ATTACHED, DETACHED, or CORE"):
            trauma_field.gore_generated_object_name("torso", "impact", "PREVIEW")

    def test_generation_digest_is_deterministic(self):
        _positions, _faces, overlay, records = heavy_records()
        arguments = dict(
            source_topology_fingerprint="a" * 64,
            deformation_digest="b" * 64,
            capture_hash="capture_hash",
            pair_role="ATTACHED",
            face_records=records,
        )
        self.assertEqual(
            trauma_field.raised_gore_geometry_digest(overlay, **arguments),
            trauma_field.raised_gore_geometry_digest(overlay, **arguments),
        )

    def test_generation_digest_changes_after_deformation_change(self):
        _positions, _faces, overlay, records = heavy_records()
        first = trauma_field.raised_gore_geometry_digest(
            overlay, source_topology_fingerprint="a" * 64,
            deformation_digest="b" * 64, capture_hash="capture_hash",
            pair_role="ATTACHED", face_records=records,
        )
        second = trauma_field.raised_gore_geometry_digest(
            overlay, source_topology_fingerprint="a" * 64,
            deformation_digest="c" * 64, capture_hash="capture_hash",
            pair_role="ATTACHED", face_records=records,
        )
        self.assertNotEqual(first, second)

    def test_deformation_point_digest_detects_coordinate_change(self):
        basis = [(0, 0, 0), (1, 0, 0)]
        first = trauma_field.deformation_point_digest(basis, [(0, 0, 0), (1, 0, -0.1)])
        second = trauma_field.deformation_point_digest(basis, [(0, 0, 0), (1, 0, -0.2)])
        self.assertNotEqual(first, second)

    def test_stale_detection_reports_deformation_and_capture_changes(self):
        overlay = heavy_overlay()
        generated = {
            "forgeOwned": True, "previewOnly": False, "regionId": "torso",
            "deformationKey": "impact", "sourceTopologyFingerprint": "a" * 64,
            "deformationDigest": "old", "captureHash": "old_capture",
            "pairRole": "ATTACHED", "recipeDigest": trauma_field.gore_overlay_digest(overlay),
            "geometryDigest": "geometry", "materialIds": list(trauma_field.GORE_MATERIAL_IDS),
            "defaultVisible": False,
        }
        reasons = trauma_field.raised_gore_stale_reasons(
            overlay, generated, region_id="torso", deformation_key="impact",
            topology_fingerprint="a" * 64, deformation_digest="new",
            capture_hash="new_capture", pair_role="ATTACHED", geometry_digest="geometry",
        )
        self.assertIn("deformation geometry changed", reasons)
        self.assertIn("linked stamp or capture changed", reasons)

    def test_stale_detection_reports_recipe_material_and_owner_changes(self):
        overlay = heavy_overlay()
        generated = {
            "forgeOwned": False, "previewOnly": False, "regionId": "torso",
            "deformationKey": "impact", "sourceTopologyFingerprint": "a" * 64,
            "deformationDigest": "deform", "captureHash": "capture_hash",
            "pairRole": "ATTACHED", "recipeDigest": "old", "geometryDigest": "geometry",
            "materialIds": ["wrong"], "defaultVisible": False,
        }
        reasons = trauma_field.raised_gore_stale_reasons(
            overlay, generated, region_id="torso", deformation_key="impact",
            topology_fingerprint="a" * 64, deformation_digest="deform",
            capture_hash="capture_hash", pair_role="ATTACHED", geometry_digest="geometry",
        )
        self.assertIn("raised-gore recipe changed", reasons)
        self.assertIn("generated mesh ownership metadata is missing", reasons)
        self.assertIn("generated gore material assignment is missing or changed", reasons)

    def test_mesh_geometry_digest_detects_manual_alteration(self):
        vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        first = trauma_field.mesh_geometry_digest(vertices, [(0, 1, 2)], [0])
        changed = trauma_field.mesh_geometry_digest([(0, 0, 0.1), *vertices[1:]], [(0, 1, 2)], [0])
        self.assertNotEqual(first, changed)

    def test_triangle_budget_reports_per_deformation_excess(self):
        errors = trauma_field.raised_gore_budget_errors([12001])
        self.assertTrue(any("limit is 12000" in error for error in errors))

    def test_triangle_budget_reports_asset_excess(self):
        errors = trauma_field.raised_gore_budget_errors([9000] * 6)
        self.assertTrue(any("asset total" in error for error in errors))

    def test_face_selection_obeys_recipe_triangle_cap(self):
        positions, faces, weights, displacement = grid_surface(12, 12)
        overlay = heavy_overlay()
        overlay["goreMaximumTriangles"] = 128
        overlay = trauma_field.normalize_gore_overlay(overlay)
        records = trauma_field.raised_gore_face_records(positions, faces, weights, displacement, overlay)
        self.assertLessEqual(sum(record["estimatedTriangleCount"] for record in records), 128)

    def test_non_head_region_generalization_has_no_anatomical_dependency(self):
        positions, faces, weights, displacement = grid_surface()
        torso = trauma_field.raised_gore_face_records(
            positions, faces, weights, displacement, heavy_overlay(region="torso")
        )
        leg = trauma_field.raised_gore_face_records(
            positions, faces, weights, displacement, heavy_overlay(region="leg_left")
        )
        self.assertEqual(torso, leg)

    def test_differently_oriented_surface_is_supported(self):
        positions, faces, weights, displacement = grid_surface()
        rotated = [(z, y, -x) for x, y, z in positions]
        records = trauma_field.raised_gore_face_records(
            rotated, faces, weights, displacement, heavy_overlay(seed=33)
        )
        self.assertTrue(records)

    def test_empty_and_invalid_geometry_inputs_fail_safely(self):
        overlay = heavy_overlay()
        self.assertEqual(trauma_field.raised_gore_face_records([], [], [], [], overlay), [])
        with self.assertRaisesRegex(ValueError, "outside the source mesh"):
            trauma_field.raised_gore_face_records([(0, 0, 0)] * 3, [(0, 1, 9)], [1] * 3, [1] * 3, overlay)

    def test_material_contract_is_metal_free_and_non_emissive_data(self):
        self.assertEqual(tuple(trauma_field.GORE_MATERIAL_SPECS), trauma_field.GORE_MATERIAL_IDS)
        for material in trauma_field.GORE_MATERIAL_SPECS.values():
            self.assertEqual(material["metallic"], 0.0)
            self.assertEqual(len(material["baseColor"]), 4)
            self.assertGreater(material["roughness"], 0.0)

    def test_export_metadata_declares_inactive_activation_contract(self):
        exported = trauma_field.gore_overlay_export_metadata(heavy_overlay())
        self.assertFalse(exported["goreDefaultVisible"])
        self.assertEqual(exported["goreOverlayMode"], "STAIN_AND_RAISED")
        self.assertEqual(exported["goreActivationWeight"], 0.01)

    def test_portable_v4_round_trip_preserves_raised_recipe(self):
        library = library_with_overlay(heavy_overlay(seed=9876))
        restored = trauma_field.normalize_stamp_library(json.loads(json.dumps(library)))
        key = restored["regions"][0]["keys"][0]
        self.assertEqual(restored["formatVersion"], 4)
        self.assertTrue(key["surfaceGoreOverlay"]["goreRaisedEnabled"])
        self.assertEqual(key["surfaceGoreOverlay"]["goreMaskSeed"], 9876)
        self.assertNotIn("meshBytes", json.dumps(key))

    def test_portable_v2_legacy_overlay_digest_migrates(self):
        legacy = {
            "goreOverlayEnabled": True,
            "gorePresetId": "Gore_Crush_Bloodied",
            **trauma_field.GORE_PRESETS["Gore_Crush_Bloodied"],
            "goreMaskSeed": 12,
            "linkedRegionId": "torso",
            "linkedStampId": "stamp_generic",
            "linkedSelectionHash": "capture_hash",
            "linkedCaptureTopologyFingerprint": "a" * 64,
        }
        library = library_with_overlay(heavy_overlay())
        library["formatVersion"] = 2
        key = library["regions"][0]["keys"][0]
        key["surfaceGoreOverlay"] = legacy
        key["goreOverlayDigest"] = trauma_field._legacy_gore_overlay_digest(legacy)
        library.pop("libraryDigest", None)
        migrated = trauma_field.normalize_stamp_library(library)
        recipe = migrated["regions"][0]["keys"][0]["surfaceGoreOverlay"]
        self.assertFalse(recipe["goreRaisedEnabled"])
        self.assertEqual(recipe["goreOverlayMode"], "SURFACE_STAIN")

    def test_user_customized_state_survives_portable_round_trip(self):
        overlay = heavy_overlay()
        overlay["goreUserCustomized"] = True
        overlay = trauma_field.normalize_gore_overlay(overlay)
        library = library_with_overlay(overlay)
        restored = trauma_field.normalize_stamp_library(copy.deepcopy(library))
        self.assertTrue(restored["regions"][0]["keys"][0]["surfaceGoreOverlay"]["goreUserCustomized"])

    def test_disabled_legacy_deformation_needs_no_gore_geometry(self):
        overlay = heavy_overlay()
        overlay["goreOverlayEnabled"] = False
        overlay = trauma_field.normalize_gore_overlay(overlay)
        positions, faces, weights, displacement = grid_surface()
        self.assertEqual(
            trauma_field.raised_gore_face_records(positions, faces, weights, displacement, overlay),
            [],
        )


if __name__ == "__main__":
    unittest.main()
