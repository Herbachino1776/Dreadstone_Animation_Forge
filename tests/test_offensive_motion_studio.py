"""Blender-independent weapon-first Motion Studio regressions."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "dreadstone_animation_forge" / "offensive_motion.py"
SPEC = importlib.util.spec_from_file_location("daf_offensive_motion", MODULE_PATH)
MOTION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOTION)


def recipe(master_id):
    value = MOTION.instantiate_motion_recipe(MOTION.BUILTIN_MOTION_MASTERS[master_id])
    value["contactFrame"] = MOTION.control_frame_schedule(value, 24.0)["CONTACT"]
    return value


class TargetVolumeTests(unittest.TestCase):
    def test_target_centers_use_canonical_y_forward_z_up(self):
        target = copy.deepcopy(MOTION.DEFAULT_TARGET)
        target.update({"distanceMeters": 1.10, "lateralOffsetMeters": -0.18, "zone": "UPPER_TORSO"})
        center = MOTION.target_zone_center(target)
        self.assertEqual((-0.18, 1.10), center[:2])
        self.assertAlmostEqual(1.296, center[2])
        volume = MOTION.target_zone_volume(target)
        self.assertEqual("CAPSULE", volume["type"])
        self.assertAlmostEqual(target["torsoRadiusMeters"], volume["radiusMeters"])
        self.assertAlmostEqual(center[2] - target["zoneHalfHeightMeters"], volume["start"][2])

    def test_segment_capsule_intersection_and_clearance_are_exact(self):
        target = copy.deepcopy(MOTION.DEFAULT_TARGET)
        volume = MOTION.target_zone_volume(target)
        center = MOTION.target_zone_center(target)
        clearance, weapon, axis = MOTION.segment_volume_distance(
            (center[0] - 0.5, center[1], center[2]),
            (center[0] + 0.5, center[1], center[2]),
            volume,
        )
        self.assertLessEqual(clearance, 0.0)
        self.assertAlmostEqual(0.0, MOTION.point_segment_distance(axis, volume["start"], volume["end"]), places=7)
        missed, _weapon, _axis = MOTION.segment_volume_distance(
            (center[0] - 0.5, center[1], center[2] + 0.75),
            (center[0] + 0.5, center[1], center[2] + 0.75),
            volume,
        )
        self.assertGreater(missed, 0.30)

    def test_point_volume_distance_distinguishes_thrust_tip_from_shaft(self):
        target = copy.deepcopy(MOTION.DEFAULT_TARGET)
        volume = MOTION.target_zone_volume(target)
        center = MOTION.target_zone_center(target)
        inside, point, axis = MOTION.point_volume_distance(center, volume)
        outside, _point, _axis = MOTION.point_volume_distance(
            (center[0], center[1] - 0.50, center[2]), volume
        )
        self.assertLessEqual(inside, 0.0)
        self.assertGreater(outside, 0.0)
        self.assertEqual(tuple(center), point)
        self.assertAlmostEqual(0.0, MOTION.point_segment_distance(axis, volume["start"], volume["end"]), places=7)

    def test_head_and_custom_targets_are_real_spheres(self):
        for zone in ("HEAD", "CUSTOM"):
            target = copy.deepcopy(MOTION.DEFAULT_TARGET)
            target["zone"] = zone
            volume = MOTION.target_zone_volume(target)
            self.assertEqual("SPHERE", volume["type"])
            self.assertGreater(volume["radiusMeters"], 0.0)


class MotionMasterTests(unittest.TestCase):
    def test_five_builtin_starters_are_versioned_and_not_artist_approved(self):
        self.assertEqual(5, len(MOTION.BUILTIN_MOTION_MASTERS))
        kinds = set()
        for master in MOTION.BUILTIN_MOTION_MASTERS.values():
            self.assertEqual([], MOTION.validate_motion_master(master))
            self.assertEqual("BUILT_IN_STARTER", master["state"])
            self.assertFalse(master["artistApproved"])
            kinds.add(master["actionKind"])
        self.assertIn("ATTACK_OVERHEAD_ONE_HAND", kinds)
        self.assertIn("ATTACK_THRUST_ONE_HAND", kinds)

    def test_master_validation_rejects_unbounded_solver_and_false_promotion(self):
        master = copy.deepcopy(MOTION.BUILTIN_MOTION_MASTERS["builtin_1h_overhead"])
        master["state"] = "PROMOTED_MASTER"
        master["solver"]["ikChainLength"] = 9
        errors = MOTION.validate_motion_master(master)
        self.assertTrue(any("artist approval" in error for error in errors))
        self.assertTrue(any("ikChainLength" in error for error in errors))

    def test_every_starter_control_path_intersects_during_active(self):
        for master_id in MOTION.BUILTIN_MOTION_MASTERS:
            value = recipe(master_id)
            report = MOTION.validate_baked_trajectory(
                value,
                MOTION.ideal_trajectory_samples(value, 24.0, 0.25),
                input_digest="ideal",
            )
            self.assertEqual("PASS", report["status"], (master_id, report["errors"]))
            self.assertTrue(report["activeContact"])
            self.assertTrue(report["intendedContact"])
            self.assertFalse(report["windupIntersected"])
            self.assertFalse(report["recoveryBuried"])

    def test_horizontal_masters_cross_in_opposite_directions(self):
        rtl = recipe("builtin_1h_slash_rtl")
        ltr = recipe("builtin_1h_slash_ltr")
        rtl_report = MOTION.validate_baked_trajectory(rtl, MOTION.ideal_trajectory_samples(rtl))
        ltr_report = MOTION.validate_baked_trajectory(ltr, MOTION.ideal_trajectory_samples(ltr))
        self.assertLess(rtl_report["actualDirectionLocal"][0], -0.9)
        self.assertGreater(ltr_report["actualDirectionLocal"][0], 0.9)
        self.assertLess(
            sum(a * b for a, b in zip(rtl_report["actualDirectionLocal"], ltr_report["actualDirectionLocal"])),
            -0.95,
        )

    def test_overhead_descends_and_thrust_advances(self):
        overhead = recipe("builtin_1h_overhead")
        thrust = recipe("builtin_1h_thrust")
        overhead_report = MOTION.validate_baked_trajectory(overhead, MOTION.ideal_trajectory_samples(overhead))
        thrust_report = MOTION.validate_baked_trajectory(thrust, MOTION.ideal_trajectory_samples(thrust))
        self.assertGreater(overhead_report["familyChecks"]["descendingRatio"], 0.95)
        self.assertGreater(thrust_report["familyChecks"]["forwardRatio"], 0.95)
        samples = MOTION.ideal_trajectory_samples(thrust)
        volume = MOTION.target_zone_volume(thrust["target"])
        proxy_radius = 0.015
        self.assertGreater(MOTION.point_volume_distance(samples[0]["contactPointLocal"], volume)[0] - proxy_radius, 0.0)
        self.assertGreater(MOTION.point_volume_distance(samples[-1]["contactPointLocal"], volume)[0] - proxy_radius, 0.0)
        self.assertTrue(thrust_report["activeContact"])

    def test_miss_is_reported_in_meters_for_selected_zone(self):
        value = recipe("builtin_1h_overhead")
        samples = MOTION.ideal_trajectory_samples(value)
        for sample in samples:
            for field in ("contactPointLocal", "strikeStartLocal", "strikeEndLocal"):
                sample[field][0] += 0.80
        report = MOTION.validate_baked_trajectory(value, samples)
        self.assertEqual("FAIL", report["status"])
        self.assertFalse(report["activeContact"])
        self.assertRegex(report["errors"][0], r"missed UPPER_TORSO by 0\.\d+ m during ACTIVE")


class PersistenceAndTargetingTests(unittest.TestCase):
    def test_recipe_schema_round_trip_and_critical_digest_invalidation(self):
        value = recipe("builtin_1h_overhead")
        self.assertEqual([], MOTION.validate_motion_recipe(value))
        before = MOTION.stable_digest(value, {"curves": [1, 2]}, {"socket": [0, 0, 0]})
        changed = copy.deepcopy(value)
        changed["target"]["distanceMeters"] += 0.01
        after = MOTION.stable_digest(changed, {"curves": [1, 2]}, {"socket": [0, 0, 0]})
        curve_after = MOTION.stable_digest(value, {"curves": [1, 3]}, {"socket": [0, 0, 0]})
        socket_after = MOTION.stable_digest(value, {"curves": [1, 2]}, {"socket": [0.01, 0, 0]})
        self.assertEqual(4, len({before, after, curve_after, socket_after}))

    def test_targeting_handoff_is_small_valid_and_non_homing(self):
        value = recipe("builtin_1h_thrust")
        report = MOTION.validate_baked_trajectory(value, MOTION.ideal_trajectory_samples(value))
        targeting = MOTION.targeting_metadata(value, report)
        self.assertEqual([], MOTION.validate_targeting_metadata(targeting))
        self.assertEqual(MOTION.TARGETING_SCHEMA, targeting["schema"])
        self.assertEqual("THRUST", targeting["trajectoryFamily"])
        self.assertNotIn("ik", str(targeting).lower())
        self.assertNotIn("tracking", str(targeting).lower())
        self.assertNotIn("guarantee", str(targeting).lower())

    def test_custom_targeting_tolerances_follow_the_validated_sphere(self):
        value = recipe("builtin_1h_thrust")
        value["target"].update({"zone": "CUSTOM", "customRadiusMeters": 0.11})
        center = MOTION.target_zone_center(value["target"])
        for control in value["trajectory"]["controls"]:
            control["contactPointLocal"][2] = center[2] + (
                0.0 if control["id"] == "CONTACT" else control["contactPointLocal"][2] - 1.044
            )
        report = MOTION.validate_baked_trajectory(value, MOTION.ideal_trajectory_samples(value))
        targeting = MOTION.targeting_metadata(value, report)
        self.assertEqual(0.11, targeting["horizontalToleranceMeters"])
        self.assertEqual(0.11, targeting["verticalToleranceMeters"])
        self.assertEqual(0.11, targeting["depthToleranceMeters"])

    def test_reviewed_recipe_promotes_deliberately_without_mutating_builtin(self):
        value = recipe("builtin_1h_overhead")
        master = MOTION.promoted_master_from_recipe(
            value,
            "user_reviewed_overhead_001",
            "Reviewed Ram God Overhead",
            source_action="DSB_Attack_Overhead_OneHand_v001",
            source_clip_id="clip_123",
        )
        self.assertEqual([], MOTION.validate_motion_master(master))
        self.assertEqual("PROMOTED_MASTER", master["state"])
        self.assertTrue(master["artistApproved"])
        self.assertFalse(MOTION.BUILTIN_MOTION_MASTERS["builtin_1h_overhead"]["artistApproved"])


if __name__ == "__main__":
    unittest.main()
