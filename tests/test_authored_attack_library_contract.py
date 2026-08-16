from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"


class AuthoredAttackLibraryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = (PACKAGE / "authored_attack_library.py").read_text(
            encoding="utf-8"
        )
        cls.service_tree = ast.parse(cls.service)
        cls.functions = {
            node.name: node
            for node in cls.service_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        cls.operators = (
            PACKAGE / "ui" / "operators" / "animations.py"
        ).read_text(encoding="utf-8")
        cls.operators_tree = ast.parse(cls.operators)
        cls.panels = (PACKAGE / "ui" / "panels.py").read_text(
            encoding="utf-8"
        )
        cls.addon = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
        cls.ui_package = (PACKAGE / "ui" / "__init__.py").read_text(
            encoding="utf-8"
        )

    @classmethod
    def assignment(cls, name):
        return next(
            node
            for node in cls.service_tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and (
                isinstance(getattr(node, "target", None), ast.Name)
                and node.target.id == name
                or any(
                    isinstance(target, ast.Name) and target.id == name
                    for target in getattr(node, "targets", ())
                )
            )
        )

    @classmethod
    def builtin_headers(cls):
        value = cls.assignment("BUILTIN_CLIPS").value
        return [
            {
                "clip_id": ast.literal_eval(call.args[0]),
                "kind": ast.literal_eval(call.args[1]),
                "title": ast.literal_eval(call.args[2]),
                "mechanics": ast.literal_eval(call.args[3]),
                "families": tuple(ast.literal_eval(call.args[4])),
            }
            for call in value.elts
        ]

    @classmethod
    def function_closure(cls, root_name):
        """Return the root function and its module-local helper call closure."""

        pending = [root_name]
        visited = set()
        result = []
        while pending:
            name = pending.pop()
            if name in visited or name not in cls.functions:
                continue
            visited.add(name)
            function = cls.functions[name]
            result.append(function)
            pending.extend(
                node.func.id
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in cls.functions
            )
        return result

    def test_catalog_has_exactly_the_five_initial_attack_kinds(self):
        records = self.builtin_headers()
        expected = (
            ("authored_slash_rtl_light_blade_v1", "ATTACK_SLASH_RTL_ONE_HAND"),
            ("authored_slash_ltr_light_blade_v1", "ATTACK_SLASH_LTR_ONE_HAND"),
            ("authored_overhead_top_heavy_v1", "ATTACK_OVERHEAD_ONE_HAND"),
            ("authored_heavy_diagonal_top_heavy_v1", "ATTACK_HEAVY_ONE_HAND"),
            ("authored_thrust_point_forward_v1", "ATTACK_THRUST_ONE_HAND"),
        )
        self.assertEqual(
            tuple((record["clip_id"], record["kind"]) for record in records),
            expected,
        )
        self.assertEqual(len({record["clip_id"] for record in records}), 5)
        self.assertEqual(len({record["kind"] for record in records}), 5)

    def test_mechanics_families_preserve_weapon_compatible_bases(self):
        records = {record["kind"]: record for record in self.builtin_headers()}
        for kind in (
            "ATTACK_SLASH_RTL_ONE_HAND",
            "ATTACK_SLASH_LTR_ONE_HAND",
        ):
            with self.subTest(kind=kind):
                self.assertEqual(records[kind]["mechanics"], "LIGHT_ONE_HAND_BLADE")
                self.assertEqual(records[kind]["families"], ("SWORD",))

        for kind in (
            "ATTACK_OVERHEAD_ONE_HAND",
            "ATTACK_HEAVY_ONE_HAND",
        ):
            with self.subTest(kind=kind):
                self.assertEqual(records[kind]["mechanics"], "TOP_HEAVY_ONE_HAND")
                self.assertEqual(set(records[kind]["families"]), {"AXE", "MACE"})

        thrust = records["ATTACK_THRUST_ONE_HAND"]
        self.assertEqual(thrust["mechanics"], "POINT_FORWARD")
        self.assertEqual(set(thrust["families"]), {"SWORD", "POLEARM"})
        self.assertTrue({"AXE", "MACE"}.isdisjoint(thrust["families"]))

        clip_factory = ast.unparse(self.functions["_clip"])
        self.assertIn("compatible = ('ONE_HAND_BLADE',)", clip_factory)
        self.assertIn("compatible = ('ONE_HAND_BLUNT',)", clip_factory)

    def test_required_markers_are_the_six_ordered_combat_markers(self):
        markers = ast.literal_eval(self.assignment("REQUIRED_MARKERS").value)
        self.assertEqual(
            markers,
            (
                "Attack_Start",
                "Windup_Anticipation",
                "Active_Start",
                "Contact",
                "Active_End",
                "Attack_End",
            ),
        )
        marker_writer = ast.unparse(self.functions["_set_markers"])
        for schedule_field in (
            "start",
            "anticipation",
            "activeStart",
            "contact",
            "activeEnd",
            "end",
        ):
            self.assertIn(schedule_field, marker_writer)

    def test_polish_macro_bounds_and_neutral_defaults_are_fixed(self):
        limits = ast.literal_eval(self.assignment("MACRO_LIMITS").value)
        self.assertEqual(
            limits,
            {
                "anticipation": (0.75, 1.25),
                "strike": (0.80, 1.20),
                "follow_through": (0.70, 1.30),
                "torso": (0.70, 1.30),
                "reach": (0.88, 1.10),
                "elbow": (0.80, 1.20),
                "wrist": (0.60, 1.35),
                "stance": (0.75, 1.25),
                "speed": (0.60, 1.60),
            },
        )
        defaults = ast.literal_eval(
            next(
                node.value
                for node in ast.walk(self.functions["default_macros"])
                if isinstance(node, ast.Return)
            )
        )
        for name, (minimum, maximum) in limits.items():
            with self.subTest(macro=name):
                self.assertEqual(defaults[name], 1.0)
                self.assertLessEqual(minimum, defaults[name])
                self.assertGreaterEqual(maximum, defaults[name])

    def test_builtins_and_bake_have_no_solver_target_or_weapon_direction_inputs(self):
        imports = {
            alias.name
            for node in self.service_tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or ""
            for node in self.service_tree.body
            if isinstance(node, ast.ImportFrom)
        )
        self.assertNotIn("offensive_motion_studio", imports)

        catalog_source = ast.get_source_segment(
            self.service,
            self.assignment("BUILTIN_CLIPS"),
        ).lower()
        bake_source = ast.get_source_segment(
            self.service,
            self.functions["bake_builtin_action"],
        ).lower()
        for forbidden in (
            "offensive_motion_studio",
            "motion_recipe",
            "target_distance",
            "target_height",
            "target_lateral",
            "target_object",
            "enemy",
            "hitbox",
            "trajectory",
            "weapon_direction",
            '"weapon_r"',
            '"weapon_l"',
        ):
            with self.subTest(forbidden_bake_vocabulary=forbidden):
                self.assertNotIn(forbidden, catalog_source)
                self.assertNotIn(forbidden, bake_source)

        bake = self.functions["bake_builtin_action"]
        self.assertEqual(
            [argument.arg for argument in bake.args.args],
            ["context", "clip_id"],
        )
        self.assertEqual(
            [argument.arg for argument in bake.args.kwonlyargs],
            ["macros", "action_name"],
        )

    def test_foot_anchors_are_bind_pose_relative_and_fixed_for_the_bake(self):
        bake = self.functions["bake_builtin_action"]
        bake_source = ast.unparse(bake)
        for warden_landmark in (
            "(0.185, -0.105, 0.0975)",
            "(-0.185, 0.095, 0.0975)",
            "(0.185, 0.095, 0.0975)",
            "(-0.185, -0.105, 0.0975)",
        ):
            with self.subTest(fixed_warden_ankle=warden_landmark):
                self.assertNotIn(warden_landmark, bake_source)

        frame_loop = next(
            node
            for node in ast.walk(bake)
            if isinstance(node, ast.For)
            and isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
            and "schedule" in ast.unparse(node.iter)
        )
        leg_calls = [
            node
            for node in ast.walk(frame_loop)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_set_leg"
        ]
        self.assertEqual(len(leg_calls), 2)
        anchor_names = {
            call.args[3].value.id
            for call in leg_calls
            if len(call.args) > 3
            and isinstance(call.args[3], ast.Subscript)
            and isinstance(call.args[3].value, ast.Name)
        }
        self.assertEqual(len(anchor_names), 1)
        anchor_name = next(iter(anchor_names))
        assignments_before_loop = [
            node
            for node in ast.walk(bake)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and node.lineno < frame_loop.lineno
            and any(
                isinstance(target, ast.Name) and target.id == anchor_name
                for target in (
                    [node.target]
                    if isinstance(node, ast.AnnAssign)
                    else node.targets
                )
            )
        ]
        self.assertTrue(assignments_before_loop)
        self.assertFalse(
            any(
                isinstance(node, (ast.Assign, ast.AnnAssign))
                and any(
                    isinstance(target, ast.Name) and target.id == anchor_name
                    for target in (
                        [node.target]
                        if isinstance(node, ast.AnnAssign)
                        else node.targets
                    )
                )
                for node in ast.walk(frame_loop)
            ),
            "Foot anchors must not be recomputed per frame.",
        )

        closure = self.function_closure("bake_builtin_action")
        closure_source = "\n".join(ast.unparse(node) for node in closure)
        closure_attributes = {
            node.attr
            for function in closure
            for node in ast.walk(function)
            if isinstance(node, ast.Attribute)
        }
        self.assertIn("foot_", closure_source)
        self.assertTrue(
            {"head_local", "matrix_local"}.intersection(closure_attributes),
            "Foot anchors must originate from mapped bind/rest bone data.",
        )
        self.assertIn("failed its planted FK landmark", bake_source)
        self.assertIn("foot.head", bake_source)
        self.assertIn("length > 0.004", bake_source)

        if any(
            marker in closure_source.lower()
            for marker in ("stance_offset", "stance_width", "authored_offset")
        ):
            self.assertTrue(
                any(
                    marker in closure_source.lower()
                    for marker in ("leg_length", "thigh.length", "shin.length", "proportion")
                ),
                "Any authored stance offset must scale from target-rig proportions.",
            )

    def test_hidden_production_rig_is_made_evaluable_before_visual_bake(self):
        bake = self.functions["bake_builtin_action"]
        bake_source = ast.unparse(bake)
        self.assertLess(
            bake_source.index("_armature(context)"),
            bake_source.index("anim_utils.bake_action_iter"),
        )
        closure_source = "\n".join(
            ast.unparse(node)
            for node in self.function_closure("bake_builtin_action")
        )
        self.assertIn("hide_viewport = False", closure_source)
        self.assertIn("hide_set(False)", closure_source)
        self.assertIn("context.view_layer.update()", closure_source)

    def test_authored_root_motion_is_preserved_by_bounded_planted_stance_fit(self):
        fit = self.functions["_fit_planted_foot_anchors"]
        fit_source = ast.unparse(fit)
        self.assertIn("for side in ('r', 'l')", fit_source)
        self.assertIn("fit_for_stance(0.0)", fit_source)
        self.assertIn("fit_for_stance(1.0)", fit_source)
        self.assertIn("required_drop = max(required_drop", fit_source)
        self.assertIn("required_drop > maximum_drop", fit_source)
        self.assertIn("stance_fit_scale = low", fit_source)
        self.assertIn(
            "return (fitted, pelvis_drops, stance_fit_scale, maximum_drop)",
            fit_source,
        )
        self.assertNotIn("root_motion_scale", fit_source)
        self.assertNotIn("pose['root_y'] =", fit_source)
        self.assertNotIn("constraints.new", fit_source)
        self.assertNotIn("IK", fit_source)

        bake_source = ast.unparse(self.functions["bake_builtin_action"])
        self.assertIn("root_motion_scale = 1.0", bake_source)
        self.assertIn("'rootMotionScale': root_motion_scale", bake_source)
        self.assertIn("'stanceFitScale': stance_fit_scale", bake_source)
        self.assertIn(
            "'footPlantPelvisDropMax': maximum_plant_drop",
            bake_source,
        )
        self.assertIn(
            "action['dsb_authored_root_motion_scale'] = root_motion_scale",
            bake_source,
        )

    def test_bake_and_validation_stamp_target_free_provenance(self):
        bake = self.functions["bake_builtin_action"]
        authored_assignment = next(
            node
            for node in ast.walk(bake)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "authored"
                for target in node.targets
            )
        )
        authored_fields = {
            ast.literal_eval(key): value
            for key, value in zip(
                authored_assignment.value.keys,
                authored_assignment.value.values,
            )
        }
        self.assertIsInstance(authored_fields["source"], ast.Name)
        bake_source = ast.unparse(bake)
        self.assertIn("BUILTIN_HAND_AUTHORED_BASE", bake_source)
        self.assertIn("AUTHORED_MANIFEST", bake_source)
        self.assertFalse(
            ast.literal_eval(authored_fields["targetOrContactGeometryRequired"])
        )
        for field in (
            "schema",
            "clipId",
            "actionKind",
            "mechanicsFamily",
            "rigProfileId",
            "semanticBoneMapping",
            "rootPolicy",
            "macros",
        ):
            self.assertIn(field, authored_fields)

        self.assertIn("action[AUTHORED_ATTACK_PROPERTY]", bake_source)
        self.assertIn("offensive_actions.stamp_offensive_metadata", bake_source)

        validator = self.functions["validate_action"]
        validator_source = ast.unparse(validator)
        self.assertNotIn("require_approval_ready", validator_source)
        self.assertNotIn("validated_targeting_record", validator_source)
        self.assertNotIn("approval_errors", validator_source)
        validator_return = next(
            node.value
            for node in ast.walk(validator)
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
        )
        validator_fields = {
            ast.literal_eval(key): value
            for key, value in zip(validator_return.keys, validator_return.values)
        }
        self.assertFalse(ast.literal_eval(validator_fields["targetGeometryRequired"]))

    def test_ui_operators_are_registered_and_route_to_the_service(self):
        operator_classes = {
            node.name: node
            for node in self.operators_tree.body
            if isinstance(node, ast.ClassDef)
        }
        expected = {
            "DAF_OT_authored_attack_select": "daf.authored_attack_select",
            "DAF_OT_authored_attack_refresh": "daf.authored_attack_refresh",
            "DAF_OT_authored_attack_preview": "daf.authored_attack_preview",
            "DAF_OT_authored_attack_accept_draft": "daf.authored_attack_accept_draft",
        }
        for class_name, operator_id in expected.items():
            with self.subTest(authored_operator=operator_id):
                node = operator_classes[class_name]
                class_source = ast.get_source_segment(self.operators, node)
                self.assertIn(operator_id, class_source)

        routes = {
            "DAF_OT_authored_attack_refresh": "refresh_library(context)",
            "DAF_OT_authored_attack_preview": "preview_selected(context)",
            "DAF_OT_authored_attack_accept_draft": "accept_preview_as_draft(context)",
        }
        for class_name, route in routes.items():
            self.assertIn(
                route,
                ast.unparse(operator_classes[class_name]),
            )

        classes_assignment = next(
            node
            for node in self.operators_tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "CLASSES"
                for target in node.targets
            )
        )
        registered = {
            element.id
            for element in classes_assignment.value.elts
            if isinstance(element, ast.Name)
        }
        self.assertTrue(set(expected).issubset(registered))
        self.assertIn("*animations.CLASSES", self.ui_package)

        for operator_id in expected.values():
            self.assertIn(operator_id, self.panels)
        for hook in (
            "_authored_attack_preview_weapon_updated",
            "authored_attack_preview_weapon",
            "authored_attack_library.replace_preview_proxy(",
        ):
            self.assertIn(hook, self.addon)

    def test_browser_draft_and_preview_lifecycle_are_persistent_and_clearable(self):
        discover = ast.unparse(self.functions["discover_clips"])
        browser = ast.unparse(self.functions["browser_records"])
        accept = ast.unparse(self.functions["accept_preview_as_draft"])
        adjust = ast.unparse(self.functions["_adjust_pose"])
        self.assertIn("_CLIPS_BY_ID.update(catalog)", discover)
        self.assertIn("previewWeaponFamilies", browser)
        self.assertIn("draft.use_fake_user = True", accept)
        self.assertIn("hand_r'][1] - elbow_delta * 0.06", adjust)
        self.assertNotIn("max(0.0, elbow_delta)", adjust)
        self.assertIn("daf.authored_attack_clear_preview", self.operators)
        self.assertIn("CLEAR TRANSIENT PREVIEW", self.panels)
        self.assertIn("marker.frame", self.panels)


if __name__ == "__main__":
    unittest.main()
