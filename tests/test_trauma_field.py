"""Standard-library tests for Blender-independent trauma-field algorithms."""

from __future__ import annotations

import ast
import importlib.util
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "dreadstone_animation_forge" / "trauma_field.py"
SPEC = importlib.util.spec_from_file_location("dreadstone_trauma_field", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load trauma_field.py for static tests")
trauma_field = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trauma_field)


def stamp(stamp_id: str, order: int, family: str = "COMPACT_DENT") -> dict[str, object]:
    return trauma_field.normalize_stamp({
        "stampId": stamp_id,
        "displayName": stamp_id,
        "family": family,
        "placementMode": "SELECTED_FACE_PATCH",
        "capture": {"selectionHash": "abc"},
        "center": [0.0, 0.0, 0.0],
        "direction": [0.0, 0.0, -1.0],
        "radius": 2.0,
        "depth": 0.25,
        "falloff": 1.0,
        "influenceMode": "CONNECTED_SURFACE",
        "distanceMode": "SURFACE_DISTANCE",
        "featherDistance": 0.5,
        "seamProtection": 0.0,
        "strength": 1.0,
        "maximumDisplacement": 1.0,
        "orderIndex": order,
    })


class TraumaFieldTests(unittest.TestCase):
    def test_adjacency_construction_uses_world_edge_lengths(self) -> None:
        adjacency = trauma_field.build_weighted_adjacency(
            3,
            ((0, 1), (1, 2)),
            ((0, 0, 0), (3, 0, 0), (3, 4, 0)),
        )
        self.assertEqual(adjacency[0], ((1, 3.0),))
        self.assertEqual(adjacency[1], ((0, 3.0), (2, 4.0)))

    def test_zero_length_mesh_edges_remain_traversable(self) -> None:
        adjacency = trauma_field.build_weighted_adjacency(
            2,
            ((0, 1),),
            ((0, 0, 0), (0, 0, 0)),
        )
        self.assertEqual(trauma_field.geodesic_distances(adjacency, (0,)), {0: 0.0, 1: 0.0})

    def test_geodesic_distances_follow_edge_connectivity(self) -> None:
        # Vertex 3 is Euclidean-close to vertex 0 but has no connecting edge.
        adjacency = trauma_field.build_weighted_adjacency(
            4,
            ((0, 1), (1, 2)),
            ((0, 0, 0), (2, 0, 0), (4, 0, 0), (0.01, 0, 0)),
        )
        distances = trauma_field.geodesic_distances(adjacency, (0,))
        self.assertEqual(distances, {0: 0.0, 1: 2.0, 2: 4.0})
        self.assertNotIn(3, distances)

    def test_disconnected_graph_behavior(self) -> None:
        adjacency = trauma_field.build_weighted_adjacency(4, ((0, 1, 1.0), (2, 3, 1.0)))
        self.assertEqual(set(trauma_field.geodesic_distances(adjacency, (0,))), {0, 1})

    def test_radius_limited_geodesic_traversal(self) -> None:
        adjacency = trauma_field.build_weighted_adjacency(4, ((0, 1, 1.0), (1, 2, 1.0), (2, 3, 1.0)))
        distances = trauma_field.geodesic_distances(adjacency, (0,), maximum_distance=1.5)
        self.assertEqual(distances, {0: 0.0, 1: 1.0})

    def test_selection_hash_is_order_and_duplicate_independent(self) -> None:
        first = trauma_field.selection_hash((4, 2, 4, 1), "topology", "FACE")
        second = trauma_field.selection_hash((1, 2, 4), "topology", "FACE")
        self.assertEqual(first, second)
        self.assertNotEqual(first, trauma_field.selection_hash((1, 2, 3), "topology", "FACE"))

    def test_cache_keys_are_deterministic_and_context_sensitive(self) -> None:
        args = ("topology", "Object:Mesh", "selection", "SURFACE_DISTANCE", 0.25)
        self.assertEqual(trauma_field.geodesic_cache_key(*args), trauma_field.geodesic_cache_key(*args))
        self.assertNotEqual(
            trauma_field.geodesic_cache_key(*args),
            trauma_field.geodesic_cache_key("topology", "Other:Mesh", "selection", "SURFACE_DISTANCE", 0.25),
        )

    def test_patch_only_weights_move_only_captured_vertices(self) -> None:
        weights = trauma_field.surface_mask_weights(5, (1, 3), {}, "PATCH_ONLY", 2.0, 0.5)
        self.assertEqual(weights, (0.0, 1.0, 0.0, 1.0, 0.0))

    def test_feathered_patch_weights_keep_patch_full_and_fade_neighbors(self) -> None:
        weights = trauma_field.surface_mask_weights(
            4, (0,), {0: 0.0, 1: 0.25, 2: 0.5, 3: 0.75}, "PATCH_FEATHERED", 2.0, 0.5
        )
        self.assertEqual(weights[0], 1.0)
        self.assertAlmostEqual(weights[1], 0.5)
        self.assertEqual(weights[2], 0.0)
        self.assertEqual(weights[3], 0.0)

    def test_connected_surface_weights_use_configured_radius(self) -> None:
        weights = trauma_field.surface_mask_weights(
            4, (0,), {0: 0.0, 1: 0.5, 2: 1.0}, "CONNECTED_SURFACE", 1.0, 0.0
        )
        self.assertEqual(weights, (1.0, 0.5, 0.0, 0.0))

    def test_stamp_ordering_is_explicit_and_deterministic(self) -> None:
        ordered = trauma_field.ordered_stamps((stamp("second", 1), stamp("first", 0)))
        self.assertEqual([value["stampId"] for value in ordered], ["first", "second"])

    def test_stamp_id_is_stable_during_reordering(self) -> None:
        original = (stamp("alpha", 0), stamp("beta", 1))
        reordered = trauma_field.reindex_stamps((original[1], original[0]))
        self.assertEqual([value["stampId"] for value in reordered], ["beta", "alpha"])

    def test_duplicate_stamp_receives_a_new_id(self) -> None:
        original = stamp("original", 0)
        duplicate = trauma_field.duplicate_stamp(original, stamp_id="duplicate")
        self.assertEqual(original["stampId"], "original")
        self.assertEqual(duplicate["stampId"], "duplicate")

    def test_duplicate_stamp_ids_are_rejected(self) -> None:
        errors = trauma_field.validate_stamp_stack((stamp("same", 0), stamp("same", 1)))
        self.assertTrue(any("Duplicate stamp ID" in error for error in errors))

    def test_invalid_direction_and_negative_values_are_rejected(self) -> None:
        invalid = stamp("invalid", 0)
        invalid["direction"] = [0.0, 0.0, 0.0]
        invalid["strength"] = -0.5
        invalid["featherDistance"] = -0.1
        errors = trauma_field.validate_stamp_stack((invalid,))
        self.assertTrue(any("zero length" in error for error in errors))
        self.assertTrue(any("negative strength" in error for error in errors))
        self.assertTrue(any("negative featherDistance" in error for error in errors))

    def test_rebuild_recipe_is_deterministic_and_starts_from_basis(self) -> None:
        basis = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        recipe = (stamp("dent", 0), stamp("shear", 1, "DIRECTIONAL_SHEAR"))
        weights = {"dent": (1.0, 0.5), "shear": (0.25, 0.0)}
        distances = {"dent": {0: 0.0, 1: 1.0}, "shear": {0: 0.0, 1: 1.0}}
        first = trauma_field.evaluate_stamp_stack(basis, recipe, weights, distances)
        second = trauma_field.evaluate_stamp_stack(basis, recipe, weights, distances)
        self.assertEqual(first, second)
        self.assertEqual(first, trauma_field.evaluate_stamp_stack(basis, recipe, weights, distances))

    def test_flat_compression_moves_points_toward_an_impact_plane(self) -> None:
        recipe = stamp("flat", 0, "FLAT_COMPRESSION")
        recipe["direction"] = [0.0, 0.0, -1.0]
        recipe["depth"] = 0.25
        result = trauma_field.evaluate_stamp_stack(
            ((0.0, 0.0, 0.2), (0.0, 0.0, -0.1)),
            (recipe,),
            {"flat": (1.0, 1.0)},
        )
        self.assertAlmostEqual(result[0][2], -0.25)
        self.assertAlmostEqual(result[1][2], -0.25)

    def test_exact_supported_family_names(self) -> None:
        self.assertEqual(
            trauma_field.TRAUMA_FAMILIES,
            (
                "COMPACT_DENT",
                "BROAD_CAVE",
                "FLAT_COMPRESSION",
                "DIRECTIONAL_SHEAR",
                "RAISED_IMPACT_RIM",
                "RIDGE_COLLAPSE",
            ),
        )

    def test_no_nearest_neighbor_transfer_implementation(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        identifiers = {
            node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        self.assertFalse({"kdtree", "find_nearest", "nearest_neighbor"} & identifiers)


if __name__ == "__main__":
    unittest.main()
