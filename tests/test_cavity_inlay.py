"""Blender-free Cavity/Inlay Gore recipe, geometry, and seed-matrix tests."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schema = load_module("dreadstone_cavity_parameter_schema", "dreadstone_animation_forge/parameter_schema.py")
trauma = load_module("dreadstone_cavity_trauma_field", "dreadstone_animation_forge/trauma_field.py")
cavity = load_module(
    "dreadstone_cavity_service",
    "dreadstone_animation_forge/deformation/cavity_service.py",
)


MATERIAL_ROLES = {
    "WET": "DSB_GORE_WET_CRIMSON",
    "CLOT": "DSB_GORE_DARK_CLOT",
    "EDGE": "DSB_GORE_ROUGH_EDGE",
    "BED": "DSB_GORE_DEEP_WOUND_BED",
    "TISSUE": "DSB_GORE_CRUSHED_TISSUE",
    "BONE": "DSB_GORE_EXPOSED_BONE",
}


def grid_surface(scale=1.0, width=7, height=7):
    step = 0.01 * float(scale)
    positions = [
        (x * step, y * step, 0.0)
        for y in range(height)
        for x in range(width)
    ]
    faces = []
    for y in range(height - 1):
        for x in range(width - 1):
            first = y * width + x
            faces.append((first, first + 1, first + width + 1, first + width))
    center_x = (width - 1) * 0.5
    center_y = (height - 1) * 0.5
    weights = []
    for y in range(height):
        for x in range(width):
            distance = abs(x - center_x) + abs(y - center_y)
            weights.append(max(0.0, 1.0 - distance / (width * 0.82)))
    normals = [(0.0, 0.0, 1.0)] * len(positions)
    return positions, faces, weights, normals


def cavity_overlay(identity_id, macros, seed, scale=1.0):
    identity = schema.gore_identity_defaults(identity_id)
    stamp_depth = 0.035 * float(scale)
    derived = schema.derive_gore_parameters(
        macros,
        identity_id=identity_id,
        region_scale=0.09 * float(scale),
        stamp_depth=stamp_depth,
        mean_edge_length=0.01 * float(scale),
    )
    overlay = trauma.default_gore_overlay(
        identity["presetId"],
        enabled=True,
        region_id="fixture",
        linked_stamp_id="stamp",
        selection_hash="capture",
        topology_fingerprint="a" * 64,
        seed=seed,
    )
    overlay.update(derived)
    overlay["goreMaskSeed"] = int(seed)
    overlay["goreControl"] = schema.normalize_gore_control({
        "identityId": identity_id,
        "mode": "MACRO",
        "macros": {
            label: value
            for label, value in zip(
                ("exposure", "cavity", "clotFill", "breakup", "wetness", "variation"),
                macros,
            )
        },
        "seed": int(seed),
    })
    return trauma.normalize_gore_overlay(overlay)


def build(identity_id, macros, seed, scale=1.0):
    positions, faces, weights, normals = grid_surface(scale)
    overlay = cavity_overlay(identity_id, macros, seed, scale)
    displacement = [weight * 0.035 * scale for weight in weights]
    records = trauma.gore_face_records(
        positions, faces, weights, displacement, overlay
    )
    generated = cavity.build_cavity_inlay(
        positions, normals, records, overlay, MATERIAL_ROLES
    )
    digest = trauma.mesh_geometry_digest(
        generated["vertices"],
        generated["faces"],
        generated["materialIndices"],
    )
    variant_digest = hashlib.sha256(json.dumps({
        "materials": generated["materialIndices"],
        "variants": generated["textureVariants"],
        "layers": generated["faceLayers"],
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return overlay, records, generated, digest, variant_digest


class CavityInlayTests(unittest.TestCase):
    def test_legacy_recipes_never_silently_become_cavities(self):
        legacy_raised = trauma.normalize_gore_overlay({
            "goreRecipeVersion": 3,
            "goreOverlayEnabled": True,
            "gorePresetId": "Gore_Crush_Heavy_Clotted",
            **trauma.GORE_PRESETS["Gore_Crush_Heavy_Clotted"],
            "goreMaskSeed": 19,
            "linkedRegionId": "head",
            "linkedStampId": "stamp",
            "linkedSelectionHash": "capture",
            "linkedCaptureTopologyFingerprint": "a" * 64,
        })
        self.assertEqual(legacy_raised["goreGeometryMode"], "LEGACY_RAISED")
        self.assertEqual(legacy_raised["goreDigestVersion"], 3)
        legacy_stain = trauma.normalize_gore_overlay({
            "goreRecipeVersion": 2,
            "goreOverlayEnabled": True,
            "gorePresetId": "Gore_Crush_Bloodied",
            **trauma.GORE_PRESETS["Gore_Crush_Bloodied"],
            "goreMaskSeed": 19,
            "linkedRegionId": "head",
            "linkedStampId": "stamp",
            "linkedSelectionHash": "capture",
            "linkedCaptureTopologyFingerprint": "a" * 64,
        })
        self.assertEqual(legacy_stain["goreGeometryMode"], "STAIN_ONLY")
        self.assertFalse(legacy_stain["goreRaisedEnabled"])

    def test_all_identities_have_macro_defaults_layers_and_budgets(self):
        self.assertEqual(
            set(schema.GORE_IDENTITIES),
            {
                "BRUISED_DENT",
                "BLOODY_CRATER",
                "DARK_CLOT_CAVITY",
                "CRUSHED_TISSUE",
                "EXPOSED_CRANIUM",
                "RAGGED_IMPACT",
            },
        )
        for identity_id in schema.GORE_IDENTITIES:
            identity = schema.gore_identity_defaults(identity_id)
            self.assertEqual(len(identity["macros"]), 6)
            self.assertTrue(identity["purpose"])
            self.assertIn("WOUND_BED", identity["layers"])
            self.assertGreaterEqual(identity["triangleBudget"], 128)

    def test_each_macro_accepts_required_0_25_50_75_100_matrix(self):
        for identity_id in schema.GORE_IDENTITIES:
            defaults = list(schema.GORE_IDENTITIES[identity_id]["macros"])
            for macro_index in range(6):
                previous_depth = -1.0
                for level in (0, 25, 50, 75, 100):
                    values = list(defaults)
                    values[macro_index] = level
                    derived = schema.derive_gore_parameters(
                        values,
                        identity_id=identity_id,
                        region_scale=0.09,
                        stamp_depth=0.035,
                        mean_edge_length=0.01,
                    )
                    self.assertEqual(
                        trauma.validate_gore_overlay(cavity_overlay(identity_id, values, 1776)),
                        [],
                    )
                    if macro_index == 1:
                        self.assertGreaterEqual(derived["goreCavityDepth"], previous_depth)
                        previous_depth = derived["goreCavityDepth"]

    def test_twenty_seeds_per_identity_are_valid_deterministic_and_varied(self):
        for identity_id, identity in schema.GORE_IDENTITIES.items():
            geometry_digests = set()
            variant_digests = set()
            depths = []
            proudness = []
            triangles = []
            for seed in range(20):
                first = build(identity_id, identity["macros"], seed)
                repeated = build(identity_id, identity["macros"], seed)
                overlay, records, generated, digest, variant_digest = first
                self.assertEqual(digest, repeated[3])
                self.assertEqual(variant_digest, repeated[4])
                self.assertTrue(records)
                self.assertEqual(cavity.edge_use_errors(generated["faces"]), [])
                self.assertLessEqual(
                    generated["metrics"]["triangleCount"],
                    overlay["goreMaximumTriangles"],
                )
                self.assertLessEqual(
                    generated["metrics"]["maximumProudness"],
                    overlay["goreProudnessLimit"] + 1e-12,
                )
                self.assertGreater(
                    generated["metrics"]["minimumSkinToLinerSeparation"],
                    0.0,
                )
                geometry_digests.add(digest)
                variant_digests.add(variant_digest)
                depths.append(generated["metrics"]["maximumCavityDepth"])
                proudness.append(generated["metrics"]["maximumProudness"])
                triangles.append(generated["metrics"]["triangleCount"])
            self.assertGreaterEqual(len(geometry_digests), 15, identity_id)
            self.assertGreaterEqual(len(variant_digests), 15, identity_id)
            self.assertGreater(max(depths), min(depths), identity_id)
            self.assertEqual(max(proudness), 0.0)
            self.assertGreaterEqual(min(triangles), 1)

    def test_scale_relative_generation_behaves_consistently(self):
        identity = schema.GORE_IDENTITIES["BLOODY_CRATER"]
        small = build("BLOODY_CRATER", identity["macros"], 77, scale=0.75)[2]["metrics"]
        large = build("BLOODY_CRATER", identity["macros"], 77, scale=1.50)[2]["metrics"]
        ratio = large["maximumCavityDepth"] / small["maximumCavityDepth"]
        self.assertGreater(ratio, 1.8)
        self.assertLess(ratio, 2.2)
        self.assertEqual(large["triangleCount"], small["triangleCount"])

    def test_layer_order_is_skin_rim_clot_tissue_liner_bone(self):
        identity = schema.GORE_IDENTITIES["CRUSHED_TISSUE"]
        overlay, _records, generated, _digest, _variant = build(
            "CRUSHED_TISSUE", identity["macros"], 1776
        )
        depths = generated["metrics"]["layerDepths"]
        ordered = [
            layer
            for layer in ("RIM", "CLOT", "TISSUE", "LINER", "BONE")
            if layer in depths
        ]
        medians = [depths[layer]["median"] for layer in ordered]
        self.assertTrue(all(first <= second for first, second in zip(medians, medians[1:])))
        self.assertEqual(overlay["goreGeometryMode"], "CAVITY_INLAY")

    def test_winding_tamper_is_detected(self):
        identity = schema.GORE_IDENTITIES["BLOODY_CRATER"]
        generated = build("BLOODY_CRATER", identity["macros"], 1776)[2]
        faces = [tuple(face) for face in generated["faces"]]
        self.assertEqual(cavity.edge_use_errors(faces), [])
        faces[0] = tuple(reversed(faces[0]))
        self.assertTrue(
            any("wound" in error for error in cavity.edge_use_errors(faces))
        )

    def test_cavity_generation_digest_uses_cavity_record_contract(self):
        identity = schema.GORE_IDENTITIES["BLOODY_CRATER"]
        overlay, records, _generated, _digest, _variant = build(
            "BLOODY_CRATER", identity["macros"], 1776
        )
        first = trauma.raised_gore_geometry_digest(
            overlay,
            source_topology_fingerprint="topology",
            deformation_digest="deformation",
            capture_hash="capture",
            pair_role="CORE",
            face_records=records,
        )
        repeated = trauma.raised_gore_geometry_digest(
            overlay,
            source_topology_fingerprint="topology",
            deformation_digest="deformation",
            capture_hash="capture",
            pair_role="CORE",
            face_records=records,
        )
        self.assertEqual(first, repeated)

    def test_seed_changes_do_not_change_macros_or_placement_links(self):
        identity = schema.GORE_IDENTITIES["BLOODY_CRATER"]
        first = cavity_overlay("BLOODY_CRATER", identity["macros"], 1)
        second = cavity_overlay("BLOODY_CRATER", identity["macros"], 2)
        self.assertEqual(first["goreControl"]["macros"], second["goreControl"]["macros"])
        for field in (
            "linkedRegionId",
            "linkedStampId",
            "linkedSelectionHash",
            "linkedCaptureTopologyFingerprint",
        ):
            self.assertEqual(first[field], second[field])
        self.assertNotEqual(
            trauma.gore_overlay_digest(first),
            trauma.gore_overlay_digest(second),
        )

    def test_invalid_seed_is_rejected_by_the_normalizer(self):
        identity = schema.GORE_IDENTITIES["BLOODY_CRATER"]
        overlay = cavity_overlay("BLOODY_CRATER", identity["macros"], 1)
        overlay["goreMaskSeed"] = schema.MAX_SEED + 1
        overlay["goreControl"] = copy.deepcopy(overlay["goreControl"])
        overlay["goreControl"]["seed"] = schema.MAX_SEED + 1
        with self.assertRaisesRegex(ValueError, "Master Gore Seed"):
            trauma.normalize_gore_overlay(overlay)


if __name__ == "__main__":
    unittest.main()
