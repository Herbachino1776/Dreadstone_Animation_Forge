import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"


def _source(path):
    return path.read_text(encoding="utf-8")


def _function(tree, name):
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _assignment_literal(tree, name):
    node = next(
        node
        for node in tree.body
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
    return ast.literal_eval(node.value)


class AuthoredAttackRuntimeRigContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service_source = _source(PACKAGE / "authored_attack_library.py")
        cls.service_tree = ast.parse(cls.service_source)
        cls.operator_source = _source(PACKAGE / "ui" / "operators" / "animations.py")
        cls.operator_tree = ast.parse(cls.operator_source)
        cls.library_source = _source(PACKAGE / "animation_library.py")
        cls.library_tree = ast.parse(cls.library_source)
        cls.socket_contract_source = _source(PACKAGE / "attachment_socket_contract.py")
        cls.socket_contract_tree = ast.parse(cls.socket_contract_source)
        cls.runtime_export_source = _source(PACKAGE / "runtime_export.py")
        cls.damage_source = _source(PACKAGE / "damage_authoring.py")

    def test_authored_and_socket_contracts_name_the_same_runtime_rig(self):
        runtime_name = _assignment_literal(
            self.service_tree,
            "RUNTIME_ARMATURE_NAME",
        )
        socket_runtime_name = _assignment_literal(
            self.socket_contract_tree,
            "RUNTIME_ARMATURE_NAME",
        )
        self.assertEqual(runtime_name, "DSB_DAMAGE_RIG")
        self.assertEqual(runtime_name, socket_runtime_name)
        self.assertEqual(
            _assignment_literal(self.service_tree, "SOURCE_ARMATURE_NAME"),
            "SBF_ProductionRig",
        )

    def test_authored_resolver_is_strict_runtime_and_makes_it_evaluable(self):
        resolver = ast.unparse(
            _function(self.service_tree, "resolve_runtime_armature")
        )
        self.assertIn(
            "context.scene.objects.get(RUNTIME_ARMATURE_NAME)",
            resolver,
        )
        self.assertNotIn("find_armature", resolver)
        self.assertIn("value.type != 'ARMATURE'", resolver)
        self.assertIn("source.hide_viewport = True", resolver)
        self.assertIn("source.hide_set(True)", resolver)
        self.assertIn("value.hide_viewport = False", resolver)
        self.assertIn("value.hide_set(False)", resolver)
        self.assertIn("context.view_layer.objects.active = value", resolver)
        self.assertIn("require_canonical_yplus(value", resolver)
        wrapper = ast.unparse(_function(self.service_tree, "_armature"))
        self.assertIn(
            "resolve_runtime_armature(context, prepare=True)",
            wrapper,
        )

    def test_preview_accept_and_proxy_all_resolve_the_runtime_rig(self):
        for function_name in (
            "bake_builtin_action",
            "accept_preview_as_draft",
            "replace_preview_proxy",
        ):
            with self.subTest(function=function_name):
                body = ast.unparse(_function(self.service_tree, function_name))
                self.assertIn("_armature(context)", body)

        accept = ast.unparse(
            _function(self.service_tree, "accept_preview_as_draft")
        )
        self.assertIn(
            "animation_library.mark_draft(draft, armature",
            accept,
        )
        bake = ast.unparse(_function(self.service_tree, "bake_builtin_action"))
        self.assertIn("_new_action(armature", bake)
        self.assertIn("validate_action(context, armature, action", bake)

    def test_vip_resolver_prefers_runtime_before_selection_fallback(self):
        resolver = ast.unparse(_function(self.operator_tree, "_armature"))
        runtime_lookup = "context.scene.objects.get('DSB_DAMAGE_RIG')"
        self.assertIn(runtime_lookup, resolver)
        self.assertIn("return runtime", resolver)
        self.assertIn("return find_armature(context)", resolver)
        self.assertLess(
            resolver.index("return runtime"),
            resolver.index("return find_armature(context)"),
        )

    def test_vip_finalize_save_and_export_route_authored_actions_on_runtime(self):
        classes = {
            node.name: node
            for node in self.operator_tree.body
            if isinstance(node, ast.ClassDef)
        }
        finalize = ast.unparse(
            classes["DAF_OT_animation_library_finalize_draft"]
        )
        self.assertIn("armature = _armature(context)", finalize)
        self.assertIn("selected_action(settings, armature)", finalize)
        self.assertIn(
            "authored.finalize_draft(context, armature, draft)",
            finalize,
        )

        save = ast.unparse(classes["DAF_OT_animation_library_save"])
        self.assertIn("armature = _armature(context)", save)
        self.assertIn("_require_authored_attack_valid", save)
        self.assertIn("animation_library.save_edit(context, armature)", save)

        export = ast.unparse(classes["DAF_OT_animation_library_export"])
        self.assertIn("armature = _armature(context)", export)
        self.assertIn("selected_action(settings, armature)", export)
        self.assertIn("_require_authored_attack_valid", export)
        self.assertIn(
            "animation_library.export_action_clip(context, armature, action",
            export,
        )

    def test_draft_approval_and_portable_export_stamp_resolved_owner(self):
        stamp = ast.unparse(
            _function(self.library_tree, "stamp_action_metadata")
        )
        self.assertIn("action[CLIP_OWNER_PROPERTY] = armature.name", stamp)

        finalize = ast.unparse(
            _function(self.service_tree, "finalize_draft")
        )
        self.assertIn(
            "runtime_armature = resolve_runtime_armature(context, prepare=False)",
            finalize,
        )
        self.assertIn("armature is not runtime_armature", finalize)
        self.assertIn(
            "animation_library.mark_approved(action, armature",
            finalize,
        )

        validate = ast.unparse(
            _function(self.service_tree, "validate_action")
        )
        self.assertIn(
            "runtime_armature = resolve_runtime_armature(context, prepare=False)",
            validate,
        )
        self.assertIn("armature is not runtime_armature", validate)
        self.assertIn("Action target must be DSB_DAMAGE_RIG", validate)

        portable = ast.unparse(
            _function(self.library_tree, "export_action_clip")
        )
        self.assertIn("'sourceArmature': armature.name", portable)
        self.assertIn("mark_approved(action, armature", portable)

        self.assertIn(
            'runtime_name = runtime_rig.name',
            self.runtime_export_source,
        )
        self.assertIn(
            'metadata_owner == runtime_name',
            self.runtime_export_source,
        )
        self.assertIn(
            'clone[animation_library.CLIP_OWNER_PROPERTY] = self.runtime_rig.name',
            self.runtime_export_source,
        )

    def test_damage_rig_is_an_independent_exact_runtime_skeleton_copy(self):
        self.assertIn(
            'AUTHORING_RIG_NAME = "DSB_DAMAGE_RIG"',
            self.damage_source,
        )
        self.assertIn(
            'rig["dsb_damage_role"] = "authoring_rig"',
            self.damage_source,
        )
        self.assertIn("obj = source.copy()", self.damage_source)
        self.assertIn("obj.data = source.data.copy()", self.damage_source)
        for required in (
            "still shares its Armature datablock with the source rig",
            "changed its rest transform",
            "only DSB_DAMAGE_RIG is allowed",
        ):
            self.assertIn(required, self.runtime_export_source)

    def test_authored_runtime_attack_supersedes_matching_legacy_export_only(self):
        audit = ast.unparse(
            _function(ast.parse(self.runtime_export_source), "audit_runtime_actions")
        )
        self.assertIn("authored_combat_ids", audit)
        self.assertIn("record['authoredAttack']", audit)
        self.assertIn("combat_id in authored_combat_ids", audit)
        self.assertIn("rejected_legacy.append(record)", audit)
        self.assertIn("'rejectedLegacyActions'", audit)

    def test_clear_preview_restores_the_runtime_action_and_frame_range(self):
        bake = ast.unparse(_function(self.service_tree, "bake_builtin_action"))
        clear = ast.unparse(_function(self.service_tree, "clear_preview"))
        accept = ast.unparse(
            _function(self.service_tree, "accept_preview_as_draft")
        )
        self.assertIn("_begin_preview_session(context, armature)", bake)
        self.assertIn("_restore_preview_session(context)", clear)
        self.assertIn("_discard_preview_session(context)", accept)
        restore = ast.unparse(
            _function(self.service_tree, "_restore_preview_session")
        )
        self.assertIn("_slot_action(armature, action)", restore)
        self.assertIn("context.scene.frame_start", restore)
        self.assertIn("context.scene.frame_end", restore)
        self.assertIn("context.scene.frame_set", restore)


if __name__ == "__main__":
    unittest.main()
