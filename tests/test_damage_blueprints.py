"""Blender-free Damage Blueprint portability and additive-gore contracts."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


blueprints = load_module(
    "test_damage_blueprint_service",
    PACKAGE / "deformation" / "blueprint_service.py",
)
schema = load_module(
    "test_damage_blueprint_parameter_schema",
    PACKAGE / "parameter_schema.py",
)
trauma = load_module(
    "test_damage_blueprint_trauma_field",
    PACKAGE / "trauma_field.py",
)


def sample_stamp():
    return {
        "capture": {
            "estimatedRadius": 0.08,
            "vertexIndices": [7, 9, 11],
            "faceIndices": [3, 4],
            "topologyFingerprint": "source-specific",
        },
        "radius": 0.096,
        "depth": 0.024,
        "featherDistance": 0.016,
        "family": "DIRECTIONAL_SHEAR",
        "falloff": 3.25,
        "seamProtection": 0.012,
        "maximumDisplacement": 0.06,
        "maximumInfluence": 1.35,
        "strength": 1.1,
        "directionMode": "INWARD_SURFACE_NORMAL",
        "directionLocal": [0.0, 0.0, -1.0],
        "influenceMode": "PATCH_FEATHERED",
        "distanceMode": "SURFACE_DISTANCE",
    }


def sample_blueprint(name="Crater One"):
    return blueprints.build_blueprint(
        name,
        impact_macros={
            "area": 68,
            "depth": 76,
            "falloff": 35,
            "edgeDamage": 72,
            "distortion": 64,
            "asymmetry": 58,
        },
        impact_seed=127,
        gore_macros={
            "coverage": 80,
            "raised": 100,
            "inlay": 100,
            "breakup": 75,
            "fill": 52,
            "wetness": 88,
        },
        surface_gore_macros={
            "mass": 91,
            "relief": 84,
            "nucleus": 72,
            "folds": 63,
            "redness": 96,
        },
        gore_seed=921,
        stamp=sample_stamp(),
        gore_identity_id="RAGGED_IMPACT",
        semantic_anchor="HEAD_LEFT",
    )


class DamageBlueprintTests(unittest.TestCase):
    def test_blueprint_excludes_source_topology_and_indices(self):
        record = sample_blueprint()
        encoded = json.dumps(record, sort_keys=True)
        for forbidden in (
            "vertexIndices",
            "faceIndices",
            "topologyFingerprint",
            "attachedObject",
            "generatedGore",
        ):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(
            record["schema"], "dreadstone.damage_blueprint.v1"
        )

    def test_capture_relative_recipe_adapts_to_any_destination_scale(self):
        record = sample_blueprint()
        small = blueprints.adaptive_stamp_values(record, 0.05)
        large = blueprints.adaptive_stamp_values(record, 0.20)
        self.assertAlmostEqual(large["radius"], small["radius"] * 4.0)
        self.assertAlmostEqual(large["depth"], small["depth"] * 4.0)
        self.assertAlmostEqual(
            large["featherDistance"], small["featherDistance"] * 4.0
        )
        self.assertEqual(large["directionMode"], small["directionMode"])
        self.assertEqual(large["family"], "DIRECTIONAL_SHEAR")
        self.assertEqual(large["falloff"], 3.25)
        self.assertAlmostEqual(
            large["seamProtection"], small["seamProtection"] * 4.0
        )
        self.assertAlmostEqual(
            large["maximumDisplacement"],
            small["maximumDisplacement"] * 4.0,
        )
        self.assertEqual(large["maximumInfluence"], 1.35)
        self.assertEqual(record["gore"]["identityId"], "RAGGED_IMPACT")
        self.assertEqual(
            record["gore"]["surfaceMacros"],
            {
                "mass": 91.0,
                "relief": 84.0,
                "nucleus": 72.0,
                "folds": 63.0,
                "redness": 96.0,
            },
        )

    def test_legacy_blueprint_without_surface_macros_migrates_safely(self):
        record = sample_blueprint()
        record.pop("blueprintDigest")
        record["gore"] = dict(record["gore"])
        record["gore"].pop("surfaceMacros")
        migrated = blueprints.normalize_blueprint(record)
        self.assertEqual(
            migrated["gore"]["surfaceMacros"],
            blueprints.SURFACE_GORE_MACRO_DEFAULTS,
        )

    def test_library_upsert_is_deterministic_and_replaces_by_id(self):
        first = sample_blueprint("A Crater")
        second = sample_blueprint("B Crater")
        library = blueprints.upsert_blueprint(None, second)
        library = blueprints.upsert_blueprint(library, first)
        self.assertEqual(
            [item["name"] for item in library["blueprints"]],
            ["A Crater", "B Crater"],
        )
        replaced = dict(first)
        replaced["impact"] = dict(first["impact"])
        replaced["impact"]["seed"] = 999
        replaced.pop("blueprintDigest")
        library = blueprints.upsert_blueprint(library, replaced)
        self.assertEqual(library["blueprintCount"], 2)
        self.assertEqual(
            blueprints.blueprint_by_id(
                library, first["blueprintId"]
            )["impact"]["seed"],
            999,
        )

    def test_invalid_portable_choices_are_rejected_before_blender_apply(self):
        record = sample_blueprint()
        record.pop("blueprintDigest")
        record["stamp"] = dict(record["stamp"])
        record["stamp"]["family"] = "NOT_A_STAMP_FAMILY"
        with self.assertRaisesRegex(ValueError, "stamp family"):
            blueprints.normalize_blueprint(record)

    def test_master_seed_derives_stable_independent_channels(self):
        impact = blueprints.derive_subseed(1776, "impact")
        gore = blueprints.derive_subseed(1776, "gore")
        self.assertEqual(
            impact, blueprints.derive_subseed(1776, "impact")
        )
        self.assertNotEqual(impact, gore)

    def test_one_plus_one_gore_expands_to_two_full_components(self):
        derived = schema.derive_gore_parameters(
            (82, 100, 55, 74, 88, 100),
            region_scale=0.08,
            stamp_depth=0.03,
            mean_edge_length=0.004,
        )
        overlay = trauma.default_gore_overlay(
            enabled=True,
            region_id="head",
            linked_stamp_id="stamp",
            selection_hash="selection",
            topology_fingerprint="topology",
        )
        overlay.update(derived)
        overlay["goreGeometryMode"] = "HYBRID_ADDITIVE"
        overlay["goreRaisedEnabled"] = True
        overlay["goreOverlayMode"] = "STAIN_AND_RAISED"
        normalized = trauma.normalize_gore_overlay(overlay)
        components = trauma.gore_component_recipes(normalized)
        self.assertEqual(
            [component for component, _recipe in components],
            ["RAISED", "INLAY"],
        )
        raised = components[0][1]
        inlay = components[1][1]
        self.assertEqual(raised["goreGeometryMode"], "LEGACY_RAISED")
        self.assertEqual(inlay["goreGeometryMode"], "CAVITY_INLAY")
        self.assertAlmostEqual(
            raised["goreClotThickness"],
            normalized["goreClotThickness"],
        )
        self.assertAlmostEqual(
            inlay["goreCavityDepth"],
            normalized["goreCavityDepth"],
        )

    def test_hybrid_component_names_are_unique_and_stable(self):
        raised = trauma.gore_generated_object_name(
            "head", "Impact", "ATTACHED", "RAISED"
        )
        inlay = trauma.gore_generated_object_name(
            "head", "Impact", "ATTACHED", "INLAY"
        )
        self.assertNotEqual(raised, inlay)
        self.assertTrue(raised.endswith("_RAISED"))
        self.assertTrue(inlay.endswith("_INLAY"))


if __name__ == "__main__":
    unittest.main()
