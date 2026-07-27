from __future__ import annotations

import ast
import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"


def load_module(name, path):
    module_spec = importlib.util.spec_from_file_location(name, path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


schema = load_module("test_impact_parameter_schema", PACKAGE / "parameter_schema.py")
trauma = load_module("test_impact_trauma_field", PACKAGE / "trauma_field.py")


def base_stamp():
    return {
        "stampId": "endpoint",
        "displayName": "Endpoint",
        "enabled": True,
        "family": "COMPACT_DENT",
        "placementMode": "SINGLE_FACE",
        "capture": {},
        "center": [0.0, 0.0, 0.0],
        "direction": [0.0, 0.0, -1.0],
        "radius": 0.075,
        "depth": 0.025,
        "falloff": 2.0,
        "influenceMode": "PATCH_FEATHERED",
        "distanceMode": "SURFACE_DISTANCE",
        "featherDistance": 0.02,
        "seamProtection": 0.025,
        "strength": 1.0,
        "maximumDisplacement": 0.065,
        "orderIndex": 0,
    }


def endpoint_values(contract):
    minimum = float(contract.hard_min)
    maximum = float(contract.hard_max)
    midpoint = (minimum + maximum) * 0.5
    if contract.integer:
        return tuple(dict.fromkeys(int(round(value)) for value in (
            minimum, contract.soft_min, contract.default, midpoint,
            contract.soft_max, maximum,
        )))
    return (
        minimum,
        math.nextafter(minimum, maximum),
        float(contract.soft_min),
        float(contract.default),
        midpoint,
        float(contract.soft_max),
        math.nextafter(maximum, minimum),
        maximum,
    )


class ImpactParameterContractTests(unittest.TestCase):
    def test_randomize_seed_operator_participates_in_blender_undo(self):
        tree = ast.parse(
            (PACKAGE / "ui" / "operators" / "impacts.py").read_text(encoding="utf-8")
        )
        operator = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "DAF_OT_randomize_impact_seed"
        )
        source = ast.unparse(operator)
        self.assertIn("UNDO", source)
        self.assertIn("randomize_impact_seed(context)", source)

    def test_every_scalar_contract_accepts_full_endpoint_matrix(self):
        for identifier, contract in schema.PARAMETERS.items():
            with self.subTest(identifier=identifier):
                for value in endpoint_values(contract):
                    self.assertEqual(contract.validate(value), [], value)

    def test_normalized_and_inverse_conversion_round_trip(self):
        for identifier, contract in schema.PARAMETERS.items():
            if contract.integer:
                continue
            for normalized in (0.0, 0.25, 0.5, 0.75, 1.0):
                with self.subTest(identifier=identifier, normalized=normalized):
                    physical = schema.inverse(identifier, normalized)
                    self.assertAlmostEqual(schema.normalize(identifier, physical), normalized, places=11)

    def test_blender_float32_endpoint_storage_is_accepted(self):
        for identifier, contract in schema.PARAMETERS.items():
            if contract.integer:
                continue
            for expected, normalized in ((contract.hard_min, 0.0), (contract.hard_max, 1.0)):
                stored = schema._rna_float32(expected)
                with self.subTest(identifier=identifier, stored=stored):
                    self.assertEqual(contract.validate(stored), [])
                    self.assertAlmostEqual(contract.to_normalized(stored), normalized, places=12)

    def test_every_vector_contract_accepts_full_endpoint_matrix(self):
        for identifier, contract in schema.VECTOR_PARAMETERS.items():
            minimum = float(contract["hardMinimum"])
            maximum = float(contract["hardMaximum"])
            size = int(contract["size"])
            uniform_values = (
                minimum,
                math.nextafter(minimum, maximum),
                float(contract["softMinimum"]),
                (minimum + maximum) * 0.5,
                float(contract["softMaximum"]),
                math.nextafter(maximum, minimum),
                maximum,
                schema._rna_float32(minimum),
                schema._rna_float32(maximum),
            )
            candidates = [tuple([value] * size) for value in uniform_values]
            candidates.append(tuple(contract["default"]))
            for value in candidates:
                with self.subTest(identifier=identifier, value=value):
                    self.assertEqual(schema.validate_vector(identifier, value), [])

    def test_every_stamp_ui_endpoint_normalizes_and_validates(self):
        fields = (
            "radius", "depth", "falloff", "featherDistance",
            "seamProtection", "strength", "maximumDisplacement",
        )
        for field in fields:
            contract = schema.recipe_spec(field)
            self.assertIsNotNone(contract)
            for value in endpoint_values(contract):
                recipe = base_stamp()
                recipe[field] = value
                with self.subTest(field=field, value=value):
                    normalized = trauma.normalize_stamp(recipe)
                    self.assertEqual(trauma.validate_stamp_stack((normalized,)), [])

    def test_every_gore_ui_endpoint_normalizes_and_validates(self):
        overlay = trauma.default_gore_overlay()
        fields = sorted({
            contract.recipe_field
            for identifier, contract in schema.PARAMETERS.items()
            if identifier.startswith("deformation_gore_")
            and contract.recipe_field
            and contract.recipe_field != "goreMaskSeed"
        } | {"gorePatchScale", "goreMaskSeed"})
        for field in fields:
            contract = schema.recipe_spec(field)
            self.assertIsNotNone(contract, field)
            for value in endpoint_values(contract):
                candidate = copy.deepcopy(overlay)
                candidate[field] = value
                with self.subTest(field=field, value=value):
                    self.assertEqual(trauma.validate_gore_overlay(candidate), [])
                    self.assertEqual(trauma.normalize_gore_overlay(candidate)[field], value)

    def test_macro_mapping_is_bounded_and_crush_is_monotonic(self):
        previous_maximum = -1.0
        previous_depth = -1.0
        for level in (0, 25, 50, 75, 100):
            derived = schema.derive_impact_parameters(
                (50, level, 50, 50, 50),
                region_scale=0.075,
                family="COMPACT_DENT",
                seed=1776,
            )
            self.assertGreaterEqual(derived["depth"], previous_depth)
            self.assertGreaterEqual(derived["maximumDisplacement"], previous_maximum)
            previous_depth = derived["depth"]
            previous_maximum = derived["maximumDisplacement"]
        zero = schema.derive_impact_parameters((50, 0, 50, 50, 50))
        self.assertEqual(zero["depth"], 0.0)
        self.assertEqual(zero["strength"], 0.0)

    def test_all_families_and_macro_endpoints_produce_valid_stamps(self):
        for family in trauma.TRAUMA_FAMILIES:
            for position in range(5):
                for level in (0, 25, 50, 75, 100):
                    values = [50.0] * 5
                    values[position] = level
                    derived = schema.derive_impact_parameters(
                        values, region_scale=0.075, family=family, seed=31415
                    )
                    recipe = base_stamp()
                    recipe.update({
                        "family": family,
                        "radius": derived["radius"],
                        "depth": derived["depth"],
                        "falloff": derived["falloff"],
                        "featherDistance": derived["featherDistance"],
                        "seamProtection": derived["seamProtection"],
                        "strength": derived["strength"],
                        "maximumDisplacement": derived["maximumDisplacement"],
                        "impactSeed": derived["impactSeed"],
                        "impactChaos": derived["impactChaos"],
                        "impactProfile": derived["impactProfile"],
                        "profileCenterRimBalance": derived["profileCenterRimBalance"],
                    })
                    with self.subTest(family=family, position=position, level=level):
                        self.assertEqual(trauma.validate_stamp_stack((trauma.normalize_stamp(recipe),)), [])

    def test_seed_is_deterministic_and_changes_geometry(self):
        recipe = base_stamp()
        recipe.update({"impactSeed": 100, "impactChaos": 0.75})
        points = ((0.0, 0.0, 0.0), (0.01, 0.0, 0.0), (0.02, 0.01, 0.0))
        weights = {"endpoint": (1.0, 0.8, 0.4)}
        first = trauma.evaluate_stamp_stack(points, (recipe,), weights)
        second = trauma.evaluate_stamp_stack(points, (recipe,), weights)
        self.assertEqual(first, second)
        recipe["impactSeed"] = 101
        third = trauma.evaluate_stamp_stack(points, (recipe,), weights)
        self.assertNotEqual(first, third)

    def test_legacy_recipe_digest_remains_stable_until_recipe_changes(self):
        recipe = base_stamp()
        expected = "00b6388e7e9f23ea762ca2e93bf868f416f42ea1e9801ade6495bf68d3a3f653"
        # Preserve the exact historical normalized recipe representation.
        recipe["stampId"] = "legacy"
        recipe["displayName"] = "Legacy"
        self.assertEqual(trauma.recipe_digest((recipe,)), expected)
        normalized = trauma.normalize_stamp(recipe)
        self.assertNotIn("impactSeed", normalized)
        self.assertNotIn("impactChaos", normalized)

    def test_impact_metadata_round_trips_additively_in_format_four(self):
        metadata = schema.normalize_impact_control({
            "mode": "MACRO",
            "macros": {
                "size": 62, "crush": 71, "profile": 44,
                "edgeSafety": 80, "chaos": 57,
            },
            "seed": 99173,
        })
        stamp = base_stamp()
        stamp.update({"impactSeed": 99173, "impactChaos": 0.57})
        payload = {
            "schema": trauma.STAMP_LIBRARY_SCHEMA,
            "formatVersion": 4,
            "producer": {"forgeVersion": "3.17.0", "deformationBuildId": "test"},
            "regions": [{
                "regionId": "head",
                "regionMode": "CORE_SINGLE",
                "sourceTargetObject": "Fixture",
                "sourceAttachedObject": "Fixture",
                "sourceDetachedObject": "",
                "topologyFingerprint": "a" * 64,
                "vertexCount": 3,
                "polygonCount": 1,
                "keys": [{
                    "name": "Impact",
                    "maximumInfluence": 1.0,
                    "maximumDisplacement": 0.065,
                    "stamps": [stamp],
                    "impactControl": metadata,
                }],
            }],
        }
        normalized = trauma.normalize_stamp_library(payload)
        restored = trauma.normalize_stamp_library(json.loads(json.dumps(normalized)))
        self.assertEqual(
            restored["regions"][0]["keys"][0]["impactControl"],
            metadata,
        )
        self.assertEqual(restored["libraryDigest"], normalized["libraryDigest"])


if __name__ == "__main__":
    unittest.main()
