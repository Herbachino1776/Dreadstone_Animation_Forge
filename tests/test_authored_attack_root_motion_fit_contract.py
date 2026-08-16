import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "dreadstone_animation_forge" / "authored_attack_library.py"


class AuthoredAttackRootMotionFitContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SERVICE_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, ast.FunctionDef)
        }

    def function_source(self, name):
        return ast.unparse(self.functions[name])

    def assignment_value(self, name):
        assignment = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
        )
        return ast.literal_eval(assignment.value)

    def thrust_stage_root_y(self, stage):
        builtins = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "BUILTIN_CLIPS"
                for target in node.targets
            )
        )
        thrust = next(
            call
            for call in builtins.value.elts
            if isinstance(call, ast.Call)
            and ast.literal_eval(call.args[0])
            == "authored_thrust_point_forward_v1"
        )
        stages = thrust.args[5]
        stage_call = next(
            value
            for key, value in zip(stages.keys, stages.values)
            if ast.literal_eval(key) == stage
        )
        return ast.literal_eval(
            next(
                keyword.value
                for keyword in stage_call.keywords
                if keyword.arg == "root_y"
            )
        )

    def test_authored_root_samples_are_preserved_from_the_base(self):
        self.assertAlmostEqual(self.thrust_stage_root_y("contact"), 0.095)
        self.assertAlmostEqual(self.thrust_stage_root_y("follow"), 0.125)

        adjust = self.function_source("_adjust_pose")
        self.assertIn("if key == 'root_y':\n                continue", adjust)
        self.assertIn(
            "if macros['root_policy'] != 'AUTHORED_ROOT_MOTION'",
            adjust,
        )
        self.assertIn("result['root_y'] = 0.0", adjust)

        mirror = self.function_source("_mirror_pose")
        self.assertNotIn("result['root_y']", mirror)
        self.assertNotIn("pose['root_y']", mirror)

    def test_fit_samples_full_root_hips_and_never_mutates_root_travel(self):
        fit_node = self.functions["_fit_planted_foot_anchors"]
        fit = ast.unparse(fit_node)
        self.assertIn("pose = _pose_at_frame(stages, schedule, frame)", fit)
        self.assertIn("_apply_body_pose(armature, mapping, pose)", fit)
        self.assertNotIn("base_pose", fit)
        self.assertNotIn("root_offsets", fit)
        self.assertNotIn("root_motion_scale", fit)

        root_writes = [
            node
            for node in ast.walk(fit_node)
            if isinstance(node, (ast.Assign, ast.AugAssign))
            and any(
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "pose"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "root_y"
                for target in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
            )
        ]
        self.assertEqual(root_writes, [])

    def test_stance_fit_uses_knee_reserve_and_bounded_pelvis_drop(self):
        knee_bend = float(
            self.assignment_value("MIN_PLANTED_KNEE_BEND_DEGREES")
        )
        drop_ratio = float(
            self.assignment_value("MAX_FOOT_PLANT_PELVIS_DROP_RATIO")
        )
        self.assertGreaterEqual(knee_bend, 8.0)
        self.assertLessEqual(knee_bend, 25.0)
        self.assertGreater(drop_ratio, 0.0)
        self.assertLessEqual(drop_ratio, 0.10)

        fit = self.function_source("_fit_planted_foot_anchors")
        self.assertIn(
            "math.cos(math.radians(MIN_PLANTED_KNEE_BEND_DEGREES))",
            fit,
        )
        self.assertNotIn("thigh_length + shin_length - 0.001", fit)
        self.assertIn(
            "maximum_drop = shortest_chain * MAX_FOOT_PLANT_PELVIS_DROP_RATIO",
            fit,
        )
        self.assertIn(
            "side: bind[side].lerp(anchors[side], factor)",
            fit,
        )
        self.assertIn("required_drop = max(required_drop", fit)
        self.assertIn("if required_drop > maximum_drop", fit)
        self.assertIn("fit_for_stance(0.0)", fit)
        self.assertIn("fit_for_stance(1.0)", fit)
        self.assertIn(
            "range(STANCE_FIT_SCAN_STEPS - 1, -1, -1)",
            fit,
        )
        self.assertIn(
            "range(STANCE_FIT_REFINEMENT_STEPS)",
            fit,
        )
        self.assertIn("stance_fit_scale = low", fit)
        self.assertIn("needs an explicit foot release/step", fit)

    def test_bake_applies_only_vertical_body_compensation_per_frame(self):
        bake = self.function_source("bake_builtin_action")
        self.assertIn("ankles = foot_fit[0]", bake)
        self.assertIn(
            "pelvis_drops = tuple((float(value) for value in foot_fit[1]))",
            bake,
        )
        self.assertIn("stance_fit_scale = float(foot_fit[2])", bake)
        self.assertIn("root_motion_scale = 1.0", bake)
        self.assertIn(
            "pelvis_drop = pelvis_drops[frame - schedule['start']]",
            bake,
        )
        self.assertIn(
            "pose['body'] = (body[0], body[1], body[2] - pelvis_drop)",
            bake,
        )
        self.assertNotIn("pose['root_y'] =", bake)

        fit_index = bake.index("ankles = foot_fit[0]")
        frame_loop_index = bake.index(
            "for frame in range(schedule['start'], schedule['end'] + 1)"
        )
        self.assertLess(fit_index, frame_loop_index)
        self.assertIn("_set_leg(armature, mapping, 'r', ankles['r']", bake)
        self.assertIn("_set_leg(armature, mapping, 'l', ankles['l']", bake)
        self.assertIn("failed its planted FK landmark", bake)
        self.assertIn("_assert_baked_plant_invariants", bake)

        post_bake = self.function_source("_assert_baked_plant_invariants")
        self.assertIn("_slot_action(armature, action)", post_bake)
        self.assertIn("expected_root_y", post_bake)
        self.assertIn("foot drifted after FK bake", post_bake)
        self.assertIn("MIN_PLANTED_KNEE_BEND_DEGREES", post_bake)
        self.assertIn("knee lost its planted bend", post_bake)

    def test_fit_is_target_free_fk_and_records_reviewable_provenance(self):
        fit = self.function_source("_fit_planted_foot_anchors")
        for forbidden in (
            "enemy",
            "target_geometry",
            "constraints.new",
            "inverse_kinematics",
            "ik_solver",
        ):
            self.assertNotIn(forbidden, fit.lower())

        bake = self.function_source("bake_builtin_action")
        for field in (
            "'rootMotionScale': root_motion_scale",
            "'stanceFitScale': stance_fit_scale",
            "'footPlantPelvisDropMax': maximum_plant_drop",
            "'footPlantPelvisDropLimit': foot_plant_drop_limit",
        ):
            self.assertIn(field, bake)
        self.assertIn(
            "action['dsb_authored_root_motion_scale'] = root_motion_scale",
            bake,
        )
        self.assertIn(
            "action['dsb_authored_stance_fit_scale'] = stance_fit_scale",
            bake,
        )
        self.assertIn(
            "action['dsb_authored_foot_plant_drop_max'] = maximum_plant_drop",
            bake,
        )


if __name__ == "__main__":
    unittest.main()
