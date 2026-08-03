"""Source contracts for grounded death clips and wrapper-optional packs."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "dreadstone_animation_forge" / "__init__.py"


class AnimationGroundingPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = ADDON_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def function(self, name: str) -> ast.FunctionDef:
        return next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )

    def operator_execute(self, class_name: str) -> ast.FunctionDef:
        operator = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        return next(
            node
            for node in operator.body
            if isinstance(node, ast.FunctionDef) and node.name == "execute"
        )

    def test_pack_source_does_not_require_safe_resize_wrapper(self) -> None:
        resolver = ast.unparse(self.function("resolve_pack_source"))
        self.assertIn("character_objects_for_armature", resolver)
        self.assertIn("'wrapper': wrapper", resolver)
        self.assertNotIn("find_safe_wrapper", resolver)

        builder = ast.unparse(
            self.operator_execute("DAF_OT_build_approved_pack")
        )
        self.assertIn("resolve_pack_source", builder)
        self.assertIn("pack_character_metadata", builder)
        self.assertNotIn("find_safe_wrapper", builder)

    def test_native_rig_manifest_mode_is_explicit(self) -> None:
        metadata = ast.unparse(self.function("pack_character_metadata"))
        self.assertIn("'NATIVE_RIG'", metadata)
        self.assertIn("'SAFE_WRAPPER'", metadata)
        self.assertIn("'visible_height_m'", metadata)

    def test_death_generation_bakes_floor_correction(self) -> None:
        collapse = ast.unparse(self.operator_execute("DAF_OT_collapse"))
        self.assertIn("bake_grounded_death_motion", collapse)
        self.assertIn("action['dsb_floor_grounded'] = True", collapse)
        self.assertIn("apply_terminal_death_pose", collapse)
        self.assertIn("action['dsb_terminal_contact_baked'] = True", collapse)

        bake = ast.unparse(self.function("bake_grounded_death_motion"))
        self.assertIn("hips.keyframe_insert('location'", bake)
        self.assertIn("set_bone_location_linear", bake)
        self.assertIn("terminal_height_ratio", bake)
        self.assertIn("maximum_terminal_height_ratio", bake)

        ground = ast.unparse(self.function("ground_current_pose"))
        self.assertIn("float(target_lowest_z) - float(minimum.z)", ground)
        self.assertNotIn("max(0.0", ground)

    def test_instant_lifeless_death_style_is_first_class(self) -> None:
        source = self.source
        self.assertIn('"INSTANT_LIMP",', source)
        self.assertIn('"Instant Unconscious"', source)
        self.assertIn("death_instant_seconds", source)
        terminal = ast.unparse(self.function("apply_terminal_death_pose"))
        self.assertIn("INSTANT_LIMP", terminal)
        self.assertIn("reset_pose", terminal)
        self.assertIn("key_pose", terminal)

    def test_pack_blocks_floor_penetrating_death_actions(self) -> None:
        builder = ast.unparse(
            self.operator_execute("DAF_OT_build_approved_pack")
        )
        self.assertIn("validate_death_floor_action", builder)
        self.assertIn("Death floor validation failed", builder)
        self.assertIn("'death_floor_validation'", builder)
        validator = ast.unparse(self.function("validate_death_floor_action"))
        self.assertIn("dsb_terminal_contact_baked", validator)
        self.assertIn("terminal body height ratio", validator)


if __name__ == "__main__":
    unittest.main()
