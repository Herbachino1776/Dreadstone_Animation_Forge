"""Source contracts for the VIP animation library."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"


class AnimationLibraryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = (
            PACKAGE / "animation_library.py"
        ).read_text(encoding="utf-8")
        cls.operators = (
            PACKAGE / "ui" / "operators" / "animations.py"
        ).read_text(encoding="utf-8")
        cls.panels = (
            PACKAGE / "ui" / "panels.py"
        ).read_text(encoding="utf-8")
        cls.addon = (
            PACKAGE / "__init__.py"
        ).read_text(encoding="utf-8")

    def test_clip_contract_is_native_and_rig_checked(self):
        for marker in (
            'ANIMATION_CLIP_SCHEMA = "dreadstone.animation_clip.v1"',
            "bpy.data.libraries.write(",
            "bpy.data.libraries.load(",
            "def compatibility_report(",
            "Missing required bones:",
            "rest orientation",
            "parent differs",
        ):
            self.assertIn(marker, self.service)

    def test_edit_save_delete_lifecycle_is_explicit(self):
        tree = ast.parse(self.service)
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        for function in (
            "character_actions",
            "play_action",
            "begin_edit",
            "save_edit",
            "cancel_edit",
            "delete_action",
            "export_action_clip",
            "import_action_clip",
        ):
            self.assertIn(function, functions)
        save = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "save_edit"
        )
        source = ast.unparse(save)
        self.assertIn("_replace_action_users", source)
        self.assertIn("mark_approved", source)

    def test_vip_panel_keeps_draft_controls_below_library(self):
        for marker in (
            "VIP ANIMATION LIBRARY",
            "PORTABLE ANIMATION CLIPS",
            '"daf.animation_library_play"',
            '"daf.animation_library_edit"',
            '"daf.animation_library_finalize_draft"',
            '"daf.animation_library_save"',
            '"daf.animation_library_delete"',
            '"daf.animation_library_export"',
            '"daf.animation_library_import"',
            "_draw_walk_animation",
            "_draw_idle_animation",
            "_draw_death_animation",
            "_draw_hurt_animation",
        ):
            self.assertIn(marker, self.panels)
        draw = next(
            node
            for node in ast.parse(self.panels).body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_draw_animation"
        )
        calls = [
            node.func.id
            for node in ast.walk(draw)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        ]
        self.assertEqual(calls[0], "_draw_vip_animation_library")
        self.assertIn("_draw_walk_animation", calls)
        self.assertIn("_draw_idle_animation", calls)

    def test_authored_attack_browser_is_primary_and_preserves_legacy_tools(self):
        tree = ast.parse(self.panels)
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertNotIn("_draw_offensive_animation_540_reference", functions)
        authored = ast.get_source_segment(
            self.panels,
            functions["_draw_authored_attack_browser"],
        )
        self.assertIsNotNone(authored)
        for marker in (
            "AUTHORED ATTACK BROWSER",
            "ATTACK LIBRARY",
            "AUTHORED BASES",
            "NON-SOLVING MACROS",
            "TIMING MARKERS",
            "PREVIEW ON CHARACTER",
            "ACCEPT AS DRAFT",
            '"daf.authored_attack_refresh"',
            '"daf.authored_attack_select"',
            '"daf.authored_attack_preview"',
            '"daf.authored_attack_accept_draft"',
            "authored_attack_mirror",
            "authored_attack_speed",
            "authored_attack_anticipation",
            "authored_attack_strike",
            "authored_attack_follow_through",
            "authored_attack_torso",
            "authored_attack_reach",
            "authored_attack_elbow",
            "authored_attack_wrist",
            "authored_attack_stance",
            "authored_attack_root_policy",
            "authored_attack_preview_weapon",
            "Attack_Start",
            "Windup_Anticipation",
            "Active_Start",
            "Contact",
            "Active_End",
            "Attack_End",
        ):
            self.assertIn(marker, authored)
        self.assertNotIn("motion_studio", authored)
        self.assertNotIn("target_distance", authored)

        legacy = ast.get_source_segment(
            self.panels,
            functions["_draw_offensive_animation"],
        )
        self.assertIsNotNone(legacy)
        for marker in (
            "LEGACY PROCEDURAL ATTACKS",
            "OFFENSIVE MOTION STUDIO",
            "ADVANCED - TRAJECTORY, BODY & SOLVER",
            "SANDBOX CONTROLS",
            '"daf.motion_studio_build_from_master"',
            '"daf.motion_studio_rebuild_body_solve"',
            '"daf.motion_studio_validate_baked_path"',
            '"daf.motion_studio_promote_master"',
            "LEGACY / PROCEDURAL DRAFTING",
            '"offensive_windup_seconds"',
            '"offensive_active_seconds"',
            '"offensive_recovery_seconds"',
            '"offensive_anticipation_strength"',
            '"offensive_strike_strength"',
            '"offensive_follow_through"',
            '"offensive_torso_power"',
            '"offensive_arm_reach"',
            '"offensive_elbow_flex"',
            '"offensive_wrist_action"',
            '"offensive_stance_compression"',
            '"daf.generate_selected_offensive_draft"',
            '"daf.preview_offensive_draft"',
            "Backward-compatible body-first rough drafts",
        ):
            self.assertIn(marker, legacy)

        draw = functions["_draw_animation"]
        calls = [
            node.func.id
            for node in ast.walk(draw)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        ]
        self.assertLess(
            calls.index("_draw_authored_attack_browser"),
            calls.index("_draw_offensive_animation"),
        )

    def test_authored_attack_macro_properties_match_service_limits(self):
        settings = next(
            node
            for node in ast.parse(self.addon).body
            if isinstance(node, ast.ClassDef)
            and node.name == "DAFSettings"
        )
        properties = {
            node.target.id: node.annotation
            for node in settings.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
        }
        expected = {
            "authored_attack_speed": (0.60, 1.60),
            "authored_attack_anticipation": (0.75, 1.25),
            "authored_attack_strike": (0.80, 1.20),
            "authored_attack_follow_through": (0.70, 1.30),
            "authored_attack_torso": (0.70, 1.30),
            "authored_attack_reach": (0.88, 1.10),
            "authored_attack_elbow": (0.80, 1.20),
            "authored_attack_wrist": (0.60, 1.35),
            "authored_attack_stance": (0.75, 1.25),
        }
        for property_name, (minimum, maximum) in expected.items():
            with self.subTest(authored_macro=property_name):
                call = properties[property_name]
                self.assertIsInstance(call, ast.Call)
                keywords = {
                    keyword.arg: ast.literal_eval(keyword.value)
                    for keyword in call.keywords
                }
                self.assertEqual(keywords["default"], 1.0)
                self.assertEqual(keywords["min"], minimum)
                self.assertEqual(keywords["max"], maximum)

    def test_humanoid_idle_is_a_first_class_yplus_loop(self):
        for marker in (
            '"IDLE": "DSB_DRAFT_Idle"',
            'class DAF_OT_idle(Operator):',
            'bl_idname = "daf.idle"',
            'action["dsb_root_motion_policy"] = "IN_PLACE"',
            'action["dsb_forward_axis"] = "+Y"',
        ):
            self.assertIn(marker, self.addon)
        self.assertIn('"IDLE": (', self.service)
        self.assertIn('if "idle" in lower:', self.service)
        self.assertIn('"daf.idle"', self.panels)

    def test_idle_supports_a_reusable_additive_draft_base_pose(self):
        for marker in (
            'ANIMATION_BASE_POSE_SCHEMA = "dreadstone.animation_base_pose.v1"',
            "def store_animation_base_pose(",
            "def apply_animation_base_pose(",
            "def clear_animation_base_pose(",
            'bl_idname = "daf.edit_animation_base_pose"',
            'bl_idname = "daf.capture_animation_base_pose"',
            'bl_idname = "daf.cancel_animation_base_pose"',
            'bl_idname = "daf.clear_animation_base_pose"',
            'apply_animation_base_pose(armature, mapping, "IDLE")',
            'apply_animation_base_pose(arm, m, "HURT")',
            'apply_animation_base_pose(arm, mapping, "MACE_GUARD")',
            'stamp_action_base_pose(action, armature, "IDLE")',
            'stamp_action_base_pose(action, arm, "HURT")',
            'stamp_action_base_pose(action, arm, "MACE_GUARD")',
            '"HURT": ("hurt_left", "hurt_right")',
            '"MACE_GUARD": ("generate_mace_head_guards",)',
        ):
            self.assertIn(marker, self.addon)
        for marker in (
            "Draft Base Pose",
            '"daf.edit_animation_base_pose"',
            '"daf.capture_animation_base_pose"',
            '"daf.cancel_animation_base_pose"',
            '"daf.clear_animation_base_pose"',
            "Capture Base + Preview Idle",
            '"HURT"',
            '"MACE_GUARD"',
            "Capture + Preview Both",
            "Capture + Preview Guards",
        ):
            self.assertIn(marker, self.panels)
        self.assertIn("icon='POSE_HLT'", self.panels)
        self.assertNotIn("icon='POSE_DATA'", self.panels)

        store = next(
            node
            for node in ast.parse(self.addon).body
            if isinstance(node, ast.FunctionDef)
            and node.name == "store_animation_base_pose"
        )
        self.assertIn("role == 'root'", ast.unparse(store))

    def test_yplus_walk_moves_forward_and_positive_elbow_bend_flexes(self):
        for marker in (
            '-values["stride_l"] * lt_r',
            '-values["stride_r"] * rt_r',
            '-s.foot_roll * lf_r',
            '-s.foot_roll * rf_r',
            "elbow_sign = 1.0 if s.invert_elbows else -1.0",
        ):
            self.assertIn(marker, self.addon)

    def test_vip_panel_reuses_one_compatibility_inventory(self):
        self.assertIn("available_actions=actions", self.panels)
        tree = ast.parse(self.service)
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        compatibility = functions["compatibility_report"]
        compatibility_calls = [
            node.func.id
            for node in ast.walk(compatibility)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        ]
        self.assertEqual(
            compatibility_calls.count("iter_action_fcurves"),
            1,
        )
        self.assertNotIn("referenced_bones", compatibility_calls)

        summary_calls = [
            node.func.id
            for node in ast.walk(functions["action_summary"])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        ]
        self.assertEqual(summary_calls.count("iter_action_fcurves"), 1)
        self.assertNotIn("action_frame_bounds", summary_calls)

    def test_scene_state_and_operator_registration_are_present(self):
        for marker in (
            "ui_vip_animation_open",
            "ui_authored_attack_open",
            "animation_library_active_clip_id",
            "animation_library_edit_source_clip_id",
            "animation_clip_directory",
            "animation_clip_import_path",
            "authored_attack_library_root",
            "authored_attack_filter_kind",
            "authored_attack_filter_weapon",
            "authored_attack_active_clip_id",
            "authored_attack_mirror",
            "authored_attack_speed",
            "authored_attack_anticipation",
            "authored_attack_strike",
            "authored_attack_follow_through",
            "authored_attack_torso",
            "authored_attack_reach",
            "authored_attack_elbow",
            "authored_attack_wrist",
            "authored_attack_stance",
            "authored_attack_root_policy",
            "authored_attack_preview_weapon",
        ):
            self.assertIn(marker, self.addon)
        for identifier in (
            "daf.animation_library_select",
            "daf.animation_library_play",
            "daf.animation_library_edit",
            "daf.animation_library_finalize_draft",
            "daf.animation_library_save",
            "daf.animation_library_cancel_edit",
            "daf.animation_library_delete",
            "daf.animation_library_export",
            "daf.animation_library_import",
            "daf.authored_attack_select",
            "daf.authored_attack_refresh",
            "daf.authored_attack_preview",
            "daf.authored_attack_accept_draft",
        ):
            self.assertIn(identifier, self.operators)
        for integration in (
            "authored.finalize_draft(",
            "_require_authored_attack_valid(",
            "module.validate_action(context, armature, action)",
        ):
            self.assertIn(integration, self.operators)
        self.assertIn(
            "authored_attack_library.replace_preview_proxy(",
            self.addon,
        )


if __name__ == "__main__":
    unittest.main()
