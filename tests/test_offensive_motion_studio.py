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

    def test_surface_contact_anchors_are_first_impact_not_target_center(self):
        target = copy.deepcopy(MOTION.DEFAULT_TARGET)
        target["zone"] = "HEAD"
        center = MOTION.target_zone_center(target)
        top = MOTION.target_contact_anchor(target, "TOP_SURFACE", (0.0, 0.0, -1.0), proxy_radius=0.015)
        entry = MOTION.target_contact_anchor(target, "ENTRY_SURFACE", (0.0, 1.0, 0.0), proxy_radius=0.015)
        self.assertGreater(top[2], center[2] + target["headRadiusMeters"])
        self.assertLess(entry[1], center[1] - target["headRadiusMeters"])
        self.assertAlmostEqual(center[0], top[0])


class MotionMasterTests(unittest.TestCase):
    def test_five_builtin_starters_are_versioned_and_not_artist_approved(self):
        self.assertEqual(5, len(MOTION.BUILTIN_MOTION_MASTERS))
        kinds = set()
        for master in MOTION.BUILTIN_MOTION_MASTERS.values():
            self.assertEqual([], MOTION.validate_motion_master(master))
            self.assertEqual("BUILT_IN_STARTER", master["state"])
            self.assertFalse(master["artistApproved"])
            self.assertEqual("5.4.2-simple.1", master["builtInRevision"])
            self.assertEqual("NATURAL", master["feel"])
            self.assertEqual(2, master["solver"]["ikChainLength"])
            self.assertEqual(0.55, master["solver"]["minimumReachRatio"])
            kinds.add(master["actionKind"])
        self.assertIn("ATTACK_OVERHEAD_ONE_HAND", kinds)
        self.assertIn("ATTACK_THRUST_ONE_HAND", kinds)

    def test_master_validation_rejects_unbounded_solver_and_false_promotion(self):
        master = copy.deepcopy(MOTION.BUILTIN_MOTION_MASTERS["builtin_1h_overhead"])
        master["state"] = "PROMOTED_MASTER"
        master["solver"]["ikChainLength"] = 9
        master["solver"]["minimumReachRatio"] = 0.95
        errors = MOTION.validate_motion_master(master)
        self.assertTrue(any("artist approval" in error for error in errors))
        self.assertTrue(any("ikChainLength" in error for error in errors))
        self.assertTrue(any("minimumReachRatio" in error or "minimum <= comfortable" in error for error in errors))

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

    def test_natural_starters_are_compact_and_use_surface_contact(self):
        overhead = recipe("builtin_1h_overhead")
        thrust = recipe("builtin_1h_thrust")
        overhead_controls = {value["id"]: value for value in overhead["trajectory"]["controls"]}
        thrust_controls = {value["id"]: value for value in thrust["trajectory"]["controls"]}
        overhead_anchor = MOTION.target_contact_anchor(
            overhead["target"], "TOP_SURFACE", overhead["trajectory"]["expectedDirectionLocal"],
            proxy_radius=overhead["proxy"]["headRadiusMeters"],
        )
        thrust_anchor = MOTION.target_contact_anchor(
            thrust["target"], "ENTRY_SURFACE", thrust["trajectory"]["expectedDirectionLocal"],
            proxy_radius=0.015,
        )
        for expected, actual in zip(overhead_anchor, overhead_controls["CONTACT"]["contactPointLocal"]):
            self.assertAlmostEqual(expected, actual, places=7)
        for expected, actual in zip(thrust_anchor, thrust_controls["CONTACT"]["contactPointLocal"]):
            self.assertAlmostEqual(expected, actual, places=7)
        self.assertLess(overhead_controls["ANTICIPATION"]["contactPointLocal"][2] - overhead_anchor[2], 0.45)
        self.assertLess(
            thrust_anchor[1] - thrust_controls["ANTICIPATION"]["contactPointLocal"][1],
            0.18,
        )
        self.assertGreater(thrust_controls["FOLLOW_THROUGH"]["contactPointLocal"][1], thrust_anchor[1])

    def test_sword_overhead_is_a_chop_not_a_vertical_plunge(self):
        master = MOTION.BUILTIN_MOTION_MASTERS["builtin_1h_overhead"]
        value = MOTION.instantiate_motion_recipe(
            master,
            target={"zone": "HEAD"},
            proxy=MOTION.proxy_defaults("ONE_HAND_BLADE"),
        )
        contact = next(control for control in value["trajectory"]["controls"] if control["id"] == "CONTACT")
        axis = MOTION.normalize(contact["weaponAxisLocal"])
        self.assertGreater(axis[1], 0.75)
        self.assertLess(abs(axis[2]), 0.65)
        self.assertEqual("TOP_SURFACE", value["trajectory"]["contactAnchor"])
        self.assertGreaterEqual(contact["contactDistanceMeters"], value["proxy"]["strikeSegmentStartMeters"])
        self.assertLessEqual(contact["contactDistanceMeters"], value["proxy"]["strikeSegmentEndMeters"])


class NaturalismMathTests(unittest.TestCase):
    def test_vip_aim_macro_redirects_thrust_around_exact_contact(self):
        base = recipe("builtin_1h_thrust")
        tuned = MOTION.apply_vip_macros(base, {"horizontalAim": 60.0, "verticalAim": 20.0})
        expected = tuned["trajectory"]["expectedDirectionLocal"]
        self.assertGreater(expected[0], 0.25)
        self.assertGreater(expected[1], 0.85)
        contact = next(control for control in tuned["trajectory"]["controls"] if control["id"] == "CONTACT")
        anchor = MOTION.target_contact_anchor(tuned["target"], "ENTRY_SURFACE", expected, proxy_radius=0.015)
        for actual, wanted in zip(contact["contactPointLocal"], anchor):
            self.assertAlmostEqual(actual, wanted, places=6)
        report = MOTION.validate_baked_trajectory(tuned, MOTION.ideal_trajectory_samples(tuned))
        self.assertEqual("PASS", report["status"], report["errors"])

    def test_neutral_vip_macros_preserve_natural_motion_and_relaxation_is_bounded(self):
        base = recipe("builtin_1h_overhead")
        neutral = MOTION.apply_vip_macros(base, MOTION.VIP_MACRO_DEFAULTS)
        self.assertEqual(base["trajectory"], neutral["trajectory"])
        self.assertEqual(base["style"], neutral["style"])
        relaxed = MOTION.apply_vip_macros(base, {"armRelax": 100.0, "bodyMotion": 0.0})
        self.assertLess(relaxed["style"]["armExtension"], base["style"]["armExtension"])
        self.assertGreater(relaxed["style"]["elbowStyle"], base["style"]["elbowStyle"])
        self.assertLess(relaxed["solver"]["torsoSupport"], base["solver"]["torsoSupport"])

    def test_vip_aim_extremes_keep_every_builtin_geometry_valid(self):
        for master_id in MOTION.BUILTIN_MOTION_MASTERS:
            for horizontal, vertical in ((-100.0, -100.0), (100.0, 100.0)):
                tuned = MOTION.apply_vip_macros(
                    recipe(master_id), {"horizontalAim": horizontal, "verticalAim": vertical}
                )
                report = MOTION.validate_baked_trajectory(tuned, MOTION.ideal_trajectory_samples(tuned))
                # At extreme aim the family moves along the redirected authored
                # axis, not necessarily canonical +Y. Geometry/contact and the
                # general direction-dot gate must still pass.
                remaining = [
                    error
                    for error in report["errors"]
                    if error != "THRUST ACTIVE motion did not advance primarily along canonical +Y."
                ]
                self.assertEqual([], remaining, (master_id, report["errors"]))

    def test_feel_presets_change_style_not_combat_or_target_law(self):
        master = MOTION.BUILTIN_MOTION_MASTERS["builtin_1h_overhead"]
        natural = MOTION.instantiate_motion_recipe(master)
        forceful = MOTION.instantiate_motion_recipe(master, style=MOTION.STYLE_PRESETS["FORCEFUL"])
        self.assertEqual(natural["actionKind"], forceful["actionKind"])
        self.assertEqual(natural["target"], forceful["target"])
        self.assertEqual(natural["trajectory"], forceful["trajectory"])
        self.assertNotEqual(natural["style"], forceful["style"])

    def test_character_arm_reach_model_keeps_a_soft_and_hard_boundary(self):
        model = MOTION.arm_reach_model(0.42, 0.36)
        self.assertAlmostEqual(0.78, model["maximumGeometricReachMeters"])
        self.assertAlmostEqual(0.55, model["minimumReachRatio"])
        self.assertAlmostEqual(0.429, model["minimumReachMeters"])
        self.assertAlmostEqual(0.88, model["comfortableReachRatio"])
        self.assertAlmostEqual(0.92, model["warningReachRatio"])
        self.assertAlmostEqual(0.985, model["hardReachRatio"])
        self.assertEqual("FOLDED", MOTION.reach_requirement((0, 0, 0), (0, 0.40, 0), model)["status"])
        self.assertEqual("COMFORTABLE", MOTION.reach_requirement((0, 0, 0), (0, 0.60, 0), model)["status"])
        self.assertEqual("WARNING", MOTION.reach_requirement((0, 0, 0), (0, 0.73, 0), model)["status"])
        self.assertEqual("IMPOSSIBLE", MOTION.reach_requirement((0, 0, 0), (0, 0.78, 0), model)["status"])

    def test_compact_thrust_stays_outside_folded_reach_on_short_arm_fit(self):
        value = recipe("builtin_1h_thrust")
        old_anchor = MOTION.target_contact_anchor(
            value["target"], "ENTRY_SURFACE", value["trajectory"]["expectedDirectionLocal"], proxy_radius=0.015
        )
        value["target"]["distanceMeters"] = 1.29
        new_anchor = MOTION.target_contact_anchor(
            value["target"], "ENTRY_SURFACE", value["trajectory"]["expectedDirectionLocal"], proxy_radius=0.015
        )
        target_shift = MOTION.subtract(new_anchor, old_anchor)
        for control in value["trajectory"]["controls"]:
            control["contactPointLocal"] = list(MOTION.add(control["contactPointLocal"], target_shift))
        value = MOTION.apply_vip_macros(value, {"verticalAim": -41.667})
        contact = next(
            control["contactPointLocal"]
            for control in value["trajectory"]["controls"]
            if control["id"] == "CONTACT"
        )
        for control in value["trajectory"]["controls"]:
            excursion = MOTION.subtract(control["contactPointLocal"], contact)
            control["contactPointLocal"] = list(MOTION.add(contact, MOTION.multiply(excursion, 0.42)))

        model = MOTION.arm_reach_model(0.2867687, 0.2263346)
        shoulder = (0.187323, -0.027309, 1.212151)
        requirements = []
        for sample in MOTION.ideal_trajectory_samples(value, 24.0, 0.25):
            grip = MOTION.subtract(
                sample["contactPointLocal"],
                MOTION.multiply(sample["weaponAxisLocal"], sample["contactDistanceMeters"]),
            )
            requirements.append(MOTION.reach_requirement(shoulder, grip, model))
        self.assertGreaterEqual(
            min(requirement["extensionRatio"] for requirement in requirements),
            model["minimumReachRatio"],
        )
        self.assertNotIn("FOLDED", {requirement["status"] for requirement in requirements})

    def test_minimum_reach_ratio_is_validated_but_optional_for_saved_541_recipe(self):
        value = recipe("builtin_1h_overhead")
        value["solver"]["minimumReachRatio"] = 0.90
        errors = MOTION.validate_motion_recipe(value)
        self.assertTrue(any("minimumReachRatio" in error or "minimum <= comfortable" in error for error in errors))

        saved_541 = recipe("builtin_1h_overhead")
        saved_541["provenance"]["builtInRevision"] = "5.4.1-natural.1"
        saved_541["solver"].pop("minimumReachRatio")
        self.assertEqual([], MOTION.validate_motion_recipe(saved_541))

    def test_blade_contact_selection_never_leaves_authored_segment(self):
        proxy = MOTION.proxy_defaults("ONE_HAND_BLADE")
        selected = MOTION.select_strike_contact_distance(
            (0.0, 0.72, 1.62),
            (0.0, 0.89, -0.45),
            (0.24, 0.0, 1.43),
            proxy,
            0.68,
            target_reach_meters=0.66,
        )
        self.assertGreaterEqual(selected, proxy["strikeSegmentStartMeters"])
        self.assertLessEqual(selected, proxy["strikeSegmentEndMeters"])

    def test_support_envelope_is_continuous_around_every_phase_key(self):
        value = recipe("builtin_1h_overhead")
        schedule = MOTION.control_frame_schedule(value, 24.0)
        for key in MOTION.CONTROL_IDS[1:-1]:
            frame = float(schedule[key])
            left = MOTION.body_support_envelope(value, frame - 1.0e-4, schedule)
            exact = MOTION.body_support_envelope(value, frame, schedule)
            right = MOTION.body_support_envelope(value, frame + 1.0e-4, schedule)
            self.assertLess(abs(left - exact), 1.0e-5, key)
            self.assertLess(abs(right - exact), 1.0e-5, key)
        contact = float(schedule["CONTACT"])
        values = [MOTION.body_support_envelope(value, contact + offset, schedule) for offset in (-1.0, 0.0, 1.0)]
        self.assertLess(max(abs(values[index + 1] - values[index]) for index in range(2)), 0.16)

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
    def test_541_master_keeps_natural_strike_segment_contact_semantics(self):
        saved_541 = copy.deepcopy(MOTION.BUILTIN_MOTION_MASTERS["builtin_1h_overhead"])
        saved_541["builtInRevision"] = "5.4.1-natural.1"
        saved_541["proxy"] = MOTION.proxy_defaults("ONE_HAND_BLADE")
        value = MOTION.instantiate_motion_recipe(saved_541)
        expected = MOTION.default_contact_distance(value["proxy"], value["trajectory"]["family"])
        self.assertTrue(
            all(abs(control["contactDistanceMeters"] - expected) < 1.0e-8 for control in value["trajectory"]["controls"])
        )

    def test_540_master_and_recipe_keep_fixed_grip_contact_semantics(self):
        legacy_master = copy.deepcopy(MOTION.BUILTIN_MOTION_MASTERS["builtin_1h_overhead"])
        legacy_master.pop("builtInRevision", None)
        legacy_master["state"] = "PROMOTED_MASTER"
        legacy_master["artistApproved"] = True
        legacy_master["proxy"] = MOTION.proxy_defaults("ONE_HAND_BLADE")
        legacy_master["proxy"]["gripToContactMeters"] = 0.70
        legacy_master["trajectory"].pop("weaponAxesByProxy", None)
        value = MOTION.instantiate_motion_recipe(legacy_master)
        self.assertTrue(all(control["contactDistanceMeters"] == 0.70 for control in value["trajectory"]["controls"]))
        for control in value["trajectory"]["controls"]:
            control.pop("contactDistanceMeters")
        schedule = MOTION.control_frame_schedule(value, 24.0)
        pose = MOTION.interpolate_trajectory(value, schedule["CONTACT"], schedule)
        self.assertEqual(0.70, pose["contactDistanceMeters"])

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
        value = MOTION.instantiate_motion_recipe(
            MOTION.BUILTIN_MOTION_MASTERS["builtin_1h_thrust"],
            target={"zone": "CUSTOM", "customRadiusMeters": 0.11},
        )
        value["contactFrame"] = MOTION.control_frame_schedule(value, 24.0)["CONTACT"]
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
