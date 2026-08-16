"""Pure and static regressions for shared-by-default Character Variants."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"
SPEC = importlib.util.spec_from_file_location(
    "daf_variant_family",
    PACKAGE / "variant_family.py",
)
VARIANTS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VARIANTS)


def handoff(variant_id="filthy", *, family_id="family-bandit", fingerprint=None):
    fingerprint = fingerprint or ("a" * 64)
    return {
        "schema": "skin-and-bones-appearance-family-handoff-v1",
        "schema_version": 1,
        "family_schema": "skin-and-bones-appearance-family-v1",
        "family_schema_version": 1,
        "family_id": family_id,
        "family_display_name": "Bandit Humanoid 01",
        "variant_id": variant_id,
        "variant_display_name": variant_id.title(),
        "export_identity": f"bandit_humanoid_01_{variant_id}",
        "technical_body_schema": "skin-and-bones-technical-body-v1",
        "technical_body_schema_version": 1,
        "technical_body_fingerprint": fingerprint,
        "appearance_revision": 7,
        "approval": {
            "state": "APPROVED",
            "approved_revision": 7,
            "appearance_fingerprint": "b" * 64,
            "approved_at_utc": "2026-08-11T20:00:00+00:00",
            "addon_version": "2.2.0",
        },
    }


def rig():
    return {
        "rigVersion": "SBF_HUMANOID_YPLUS_V1",
        "rigContractVersion": 1,
        "forwardAxis": "+Y",
        "upAxis": "+Z",
        "rootBone": "root",
        "orientationState": "CANONICAL_Y_PLUS",
        "orientationRevision": 1,
        "unitScaleMeters": 1.0,
        "canonicalYPlus": True,
    }


def family_with_two():
    state = VARIANTS.new_family(handoff(), rig())
    return VARIANTS.add_variant(state, handoff("sooted"), rig())


class SkinAndBonesContractTests(unittest.TestCase):
    def test_accepts_actual_shipped_handoff_and_scalar_extras(self):
        value = handoff()
        extras = {
            "sbf_appearance_family_id": value["family_id"],
            "sbf_appearance_variant_id": value["variant_id"],
            "sbf_technical_body_fingerprint": value["technical_body_fingerprint"],
        }
        self.assertEqual([], VARIANTS.handoff_errors(json.dumps(value), extras))

    def test_rejects_stale_appearance_approval(self):
        value = handoff()
        value["approval"]["approved_revision"] = 6
        self.assertTrue(
            any("stale" in error.lower() for error in VARIANTS.handoff_errors(value))
        )

    def test_rejects_scalar_and_json_disagreement(self):
        value = handoff()
        errors = VARIANTS.handoff_errors(
            value,
            {
                "sbf_appearance_family_id": "wrong",
                "sbf_appearance_variant_id": value["variant_id"],
                "sbf_technical_body_fingerprint": value["technical_body_fingerprint"],
            },
        )
        self.assertTrue(any("scalar" in error.lower() for error in errors))

    def test_requires_exact_canonical_coordinate_contract(self):
        incompatible = rig()
        incompatible["forwardAxis"] = "-Y"
        with self.assertRaisesRegex(ValueError, "forwardAxis"):
            VARIANTS.new_family(handoff(), incompatible)

    def test_compatible_family_accepts_second_appearance(self):
        state = family_with_two()
        self.assertEqual(2, len(state["variants"]))
        self.assertEqual("sooted", state["activeVariantId"])

    def test_rejects_different_family_or_body_fingerprint(self):
        state = VARIANTS.new_family(handoff(), rig())
        for candidate in (
            handoff("captain", family_id="other-family"),
            handoff("captain", fingerprint="c" * 64),
        ):
            with self.assertRaises(ValueError):
                VARIANTS.add_variant(state, candidate, rig())

    def test_rejects_duplicate_stable_variant_identity(self):
        state = VARIANTS.new_family(handoff(), rig())
        with self.assertRaisesRegex(ValueError, "already belongs"):
            VARIANTS.add_variant(state, handoff(), rig())

    def test_rejects_duplicate_shipping_export_identity(self):
        state = VARIANTS.new_family(handoff(), rig())
        duplicate = handoff("sooted")
        duplicate["export_identity"] = "BANDIT_HUMANOID_01_FILTHY"
        with self.assertRaisesRegex(ValueError, "collide"):
            VARIANTS.add_variant(state, duplicate, rig())

    def test_save_reopen_round_trip_preserves_active_and_overrides(self):
        state = family_with_two()
        state = VARIANTS.register_shared_actions(state, ["idle", "walk"])
        state = VARIANTS.set_action_override(state, "walk", "sooted_walk", "sooted")
        reopened = VARIANTS.normalize_family(json.loads(json.dumps(state)))
        self.assertEqual("sooted", reopened["activeVariantId"])
        self.assertEqual(
            ("sooted_walk", "VARIANT_OVERRIDE"),
            VARIANTS.resolve_action_id(reopened, "walk"),
        )


class FinishedRigTextureFamilyTests(unittest.TestCase):
    def setUp(self):
        self.state = VARIANTS.new_forge_texture_family(
            "cinderbound-warden",
            "Cinderbound Warden",
            "base",
            "Base",
            "cinderbound_warden",
            "d" * 64,
            rig(),
            appearance={"runtimeMaterialSlots": []},
            appearance_fingerprint="e" * 64,
            approved_at_utc="2026-08-15T12:00:00+00:00",
        )

    def test_finished_rig_family_is_not_a_synthetic_sbf_handoff(self):
        self.assertEqual(
            VARIANTS.FAMILY_SOURCE_FORGE_TEXTURE,
            self.state["familySource"],
        )
        base = VARIANTS.variant_by_id(self.state, "base")
        self.assertIsNone(base["handoff"])
        self.assertEqual(
            VARIANTS.FORGE_TEXTURE_APPROVAL_AUTHORITY,
            base["appearanceApprovalAuthority"],
        )
        self.assertTrue(VARIANTS.variant_appearance_approved(self.state, "base"))

    def test_new_texture_look_is_draft_and_inherits_all_shared_authoring(self):
        state = VARIANTS.register_shared_actions(self.state, ["idle", "walk", "death"])
        state = VARIANTS.add_forge_texture_variant(
            state,
            "ash",
            "Ash",
            "cinderbound_warden_ash",
            "d" * 64,
            rig(),
            appearance={"runtimeMaterialSlots": []},
        )
        ash = VARIANTS.variant_by_id(state, "ash")
        self.assertEqual("DRAFT", ash["appearanceApprovalState"])
        self.assertFalse(VARIANTS.variant_appearance_approved(state, "ash"))
        self.assertEqual({}, ash["actionOverrides"])
        self.assertEqual({}, ash["damageKeyOverrides"])
        self.assertEqual({}, ash["progressiveSiteOverrides"])
        for action_id in ("idle", "walk", "death"):
            self.assertEqual(
                (action_id, "INHERITED"),
                VARIANTS.resolve_action_id(state, action_id, "ash"),
            )

    def test_texture_approval_is_forge_owned_and_revisioned(self):
        state = VARIANTS.add_forge_texture_variant(
            self.state,
            "ember",
            "Ember",
            "cinderbound_warden_ember",
            "d" * 64,
            rig(),
        )
        state = VARIANTS.approve_forge_texture_variant(
            state,
            "f" * 64,
            "2026-08-15T13:00:00+00:00",
            variant_id="ember",
        )
        ember = VARIANTS.variant_by_id(state, "ember")
        self.assertEqual("APPROVED", ember["appearanceApprovalState"])
        self.assertEqual(2, ember["appearanceRevision"])
        self.assertTrue(
            VARIANTS.variant_appearance_approved(state, "ember", "f" * 64)
        )
        self.assertFalse(
            VARIANTS.variant_appearance_approved(state, "ember", "0" * 64)
        )

    def test_explicit_texture_edit_blocks_export_until_saved_again(self):
        original_revision = self.state["revision"]
        state = VARIANTS.begin_forge_texture_variant_edit(self.state, "base")
        base = VARIANTS.variant_by_id(state, "base")
        self.assertEqual("DRAFT", base["appearanceApprovalState"])
        self.assertEqual("e" * 64, base["appearanceFingerprint"])
        self.assertFalse(VARIANTS.variant_appearance_approved(state, "base"))
        self.assertGreater(state["revision"], original_revision)

    def test_finished_rig_change_or_sbf_join_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Damage Rig/body changed"):
            VARIANTS.add_forge_texture_variant(
                self.state,
                "wrong",
                "Wrong",
                "wrong",
                "0" * 64,
                rig(),
            )
        with self.assertRaisesRegex(ValueError, "cannot be joined"):
            VARIANTS.add_variant(self.state, handoff("sooted"), rig())

    def test_explicit_rebaseline_rejects_wrong_source_fingerprint_and_rig(self):
        with self.assertRaises(ValueError):
            VARIANTS.rebaseline_forge_texture_family(
                VARIANTS.new_family(handoff(), rig()),
                "a" * 64,
                rig(),
                "2026-08-16T20:00:00+00:00",
            )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            VARIANTS.rebaseline_forge_texture_family(
                self.state,
                "not-a-fingerprint",
                rig(),
                "2026-08-16T20:00:00+00:00",
            )
        incompatible_rig = rig()
        incompatible_rig["forwardAxis"] = "-Y"
        with self.assertRaisesRegex(ValueError, "forwardAxis"):
            VARIANTS.rebaseline_forge_texture_family(
                self.state,
                "a" * 64,
                incompatible_rig,
                "2026-08-16T20:00:00+00:00",
            )

    def test_explicit_rebaseline_invalidates_only_appearance_approval(self):
        state = VARIANTS.register_shared_actions(self.state, ["idle", "walk"])
        state = VARIANTS.add_forge_texture_variant(
            state,
            "ash",
            "Ash",
            "cinderbound_warden_ash",
            "d" * 64,
            rig(),
            appearance={"runtimeMaterialSlots": [{"object": "DSB_BODY_CORE"}]},
        )
        state = VARIANTS.approve_forge_texture_variant(
            state,
            "f" * 64,
            "2026-08-15T13:00:00+00:00",
            variant_id="ash",
        )
        state = VARIANTS.set_action_override(
            state,
            "walk",
            "ash_walk",
            "ash",
        )
        state = VARIANTS.set_damage_key_override(
            state,
            {
                "sharedDamageKeyId": "head_light",
                "overrideDamageKeyId": "head_light_ash",
                "overrideName": "Head_Light__ash",
            },
            "ash",
        )
        state = VARIANTS.set_progressive_site_override(
            state,
            {
                "sharedSiteGuid": "site_head",
                "overrideSiteGuid": "site_head_ash",
                "ownedDamageKeys": [],
            },
            "ash",
        )
        for variant in state["variants"]:
            variant["appearanceQuickFingerprint"] = "1" * 64

        before = copy.deepcopy(state)
        rebased = VARIANTS.rebaseline_forge_texture_family(
            state,
            "a" * 64,
            rig(),
            "2026-08-16T20:00:00+00:00",
        )

        self.assertEqual("d" * 64, state["technicalBodyFingerprint"])
        self.assertEqual("a" * 64, rebased["technicalBodyFingerprint"])
        self.assertEqual(before["revision"] + 1, rebased["revision"])
        self.assertEqual(before["canonicalRig"], rebased["canonicalRig"])
        self.assertEqual(before["shared"], rebased["shared"])
        self.assertEqual(
            [variant["variantId"] for variant in before["variants"]],
            [variant["variantId"] for variant in rebased["variants"]],
        )
        for old, new in zip(before["variants"], rebased["variants"]):
            self.assertEqual(old["appearance"], new["appearance"])
            self.assertEqual(old["actionOverrides"], new["actionOverrides"])
            self.assertEqual(old["damageKeyOverrides"], new["damageKeyOverrides"])
            self.assertEqual(
                old["progressiveSiteOverrides"],
                new["progressiveSiteOverrides"],
            )
            self.assertEqual(old["appearanceRevision"] + 1, new["appearanceRevision"])
            self.assertEqual(old["forgeRevision"] + 1, new["forgeRevision"])
            self.assertEqual("DRAFT", new["appearanceApprovalState"])
            self.assertEqual("", str(new.get("appearanceFingerprint", "")))
            self.assertEqual("", str(new.get("appearanceApprovedAtUtc", "")))
            self.assertEqual("", str(new.get("appearanceQuickFingerprint", "")))

    def test_rebaseline_to_existing_fingerprint_is_a_no_op(self):
        before = copy.deepcopy(self.state)
        result = VARIANTS.rebaseline_forge_texture_family(
            self.state,
            "d" * 64,
            rig(),
            "2026-08-16T20:00:00+00:00",
        )
        self.assertEqual(before, result)
        self.assertEqual(before, self.state)

    def test_texture_provenance_names_its_real_authority(self):
        record = VARIANTS.export_provenance(self.state, "base")
        self.assertEqual(
            VARIANTS.FAMILY_SOURCE_FORGE_TEXTURE,
            record["familySource"],
        )
        self.assertEqual(
            VARIANTS.FORGE_TEXTURE_APPROVAL_AUTHORITY,
            record["appearanceApprovalAuthority"],
        )
        self.assertEqual("e" * 64, record["appearanceFingerprint"])


class AnimationResolutionTests(unittest.TestCase):
    def setUp(self):
        self.state = VARIANTS.register_shared_actions(
            family_with_two(),
            ["idle", "walk", "hurt", "death", "attack"],
        )

    def test_new_variant_inherits_all_shared_actions_without_records(self):
        sooted = VARIANTS.variant_by_id(self.state, "sooted")
        self.assertEqual({}, sooted["actionOverrides"])
        for action_id in self.state["shared"]["actionIds"]:
            self.assertEqual(
                (action_id, "INHERITED"),
                VARIANTS.resolve_action_id(self.state, action_id, "sooted"),
            )

    def test_one_override_forks_only_requested_action(self):
        state = VARIANTS.set_action_override(
            self.state,
            "walk",
            "sooted_walk",
            "sooted",
        )
        self.assertEqual(
            ("sooted_walk", "VARIANT_OVERRIDE"),
            VARIANTS.resolve_action_id(state, "walk", "sooted"),
        )
        self.assertEqual(
            ("death", "INHERITED"),
            VARIANTS.resolve_action_id(state, "death", "sooted"),
        )
        self.assertEqual({}, VARIANTS.variant_by_id(state, "filthy")["actionOverrides"])

    def test_shared_identity_remains_live_for_inheritors(self):
        before = VARIANTS.resolve_action_id(self.state, "hurt", "filthy")
        state = copy.deepcopy(self.state)
        state["shared"]["revision"] += 1
        after = VARIANTS.resolve_action_id(state, "hurt", "filthy")
        self.assertEqual(before, after)

    def test_revert_removes_override_and_restores_shared_resolution(self):
        state = VARIANTS.set_action_override(self.state, "death", "long_death", "sooted")
        state, removed = VARIANTS.remove_action_override(state, "death", "sooted")
        self.assertEqual("long_death", removed["overrideActionId"])
        self.assertEqual(
            ("death", "INHERITED"),
            VARIANTS.resolve_action_id(state, "death", "sooted"),
        )


class DamageResolutionTests(unittest.TestCase):
    def setUp(self):
        self.state = family_with_two()
        self.records = [
            {
                "name": "Head_Light",
                "damageKeyId": "key_light",
                "regionId": "head",
                "ownerVariantId": "",
                "sharedDamageKeyId": "",
            },
            {
                "name": "Head_Medium",
                "damageKeyId": "key_medium",
                "regionId": "head",
                "ownerVariantId": "",
                "sharedDamageKeyId": "",
            },
            {
                "name": "Head_Heavy",
                "damageKeyId": "key_heavy",
                "regionId": "head",
                "ownerVariantId": "",
                "sharedDamageKeyId": "",
            },
        ]
        self.site = {
            "siteGuid": "site_head",
            "siteId": "head",
            "stages": {
                "LIGHT": {"stage": "LIGHT", "damageKeyId": "key_light", "deformationKeyName": "Head_Light"},
                "MEDIUM": {"stage": "MEDIUM", "damageKeyId": "key_medium", "deformationKeyName": "Head_Medium"},
                "HEAVY": {"stage": "HEAVY", "damageKeyId": "key_heavy", "deformationKeyName": "Head_Heavy"},
            },
        }

    def test_no_damage_duplication_by_default(self):
        self.assertEqual(
            ["Head_Light", "Head_Medium", "Head_Heavy"],
            VARIANTS.effective_damage_key_names(
                self.state, "head", self.records, "sooted"
            ),
        )
        self.assertEqual({}, VARIANTS.variant_by_id(self.state, "sooted")["damageKeyOverrides"])

    def test_narrow_key_override_suppresses_only_its_shared_key(self):
        state = VARIANTS.set_damage_key_override(
            self.state,
            {
                "sharedDamageKeyId": "key_medium",
                "overrideDamageKeyId": "key_medium_sooted",
                "sharedName": "Head_Medium",
                "overrideName": "Head_Medium__sooted",
                "regionId": "head",
            },
            "sooted",
        )
        records = self.records + [
            {
                "name": "Head_Medium__sooted",
                "damageKeyId": "key_medium_sooted",
                "regionId": "head",
                "ownerVariantId": "sooted",
                "sharedDamageKeyId": "key_medium",
            }
        ]
        self.assertEqual(
            ["Head_Light", "Head_Medium__sooted", "Head_Heavy"],
            VARIANTS.effective_damage_key_names(state, "head", records, "sooted"),
        )
        self.assertEqual(
            ["Head_Light", "Head_Medium", "Head_Heavy"],
            VARIANTS.effective_damage_key_names(state, "head", records, "filthy"),
        )

    def test_progressive_override_plan_clones_exactly_three_assigned_keys(self):
        plan = VARIANTS.progressive_clone_plan(self.site, self.records)
        self.assertEqual([], plan["errors"])
        self.assertEqual(
            ["key_light", "key_medium", "key_heavy"],
            plan["damageKeyIds"],
        )

    def test_progressive_override_replaces_only_requested_site(self):
        other = copy.deepcopy(self.site)
        other["siteGuid"] = "site_shoulder"
        other["siteId"] = "shoulder"
        override = copy.deepcopy(self.site)
        override["siteGuid"] = "site_head_sooted"
        override["ownerVariantId"] = "sooted"
        state = VARIANTS.set_progressive_site_override(
            self.state,
            {
                "sharedSiteGuid": "site_head",
                "overrideSiteGuid": "site_head_sooted",
                "ownedDamageKeys": [],
            },
            "sooted",
        )
        resolved = VARIANTS.effective_progressive_sites(
            state,
            [self.site, other, override],
            "sooted",
        )
        self.assertEqual(2, len(resolved))
        self.assertEqual(
            {"site_head_sooted", "site_shoulder"},
            {site["siteGuid"] for site in resolved},
        )

    def test_progressive_override_replaces_only_its_assigned_physical_keys(self):
        state = VARIANTS.set_progressive_site_override(
            self.state,
            {
                "sharedSiteGuid": "site_head",
                "overrideSiteGuid": "site_head_sooted",
                "ownedDamageKeys": [
                    {
                        "sharedDamageKeyId": "key_light",
                        "overrideDamageKeyId": "key_light_sooted",
                    },
                    {
                        "sharedDamageKeyId": "key_medium",
                        "overrideDamageKeyId": "key_medium_sooted",
                    },
                    {
                        "sharedDamageKeyId": "key_heavy",
                        "overrideDamageKeyId": "key_heavy_sooted",
                    },
                ],
            },
            "sooted",
        )
        records = copy.deepcopy(self.records)
        records.append(
            {
                "damageKeyId": "key_shoulder",
                "name": "Shoulder",
                "regionId": "head",
                "ownerVariantId": "",
                "sharedDamageKeyId": "",
            }
        )
        records.extend(
            {
                "damageKeyId": f"{value['damageKeyId']}_sooted",
                "name": f"{value['name']}__sooted",
                "regionId": "head",
                "ownerVariantId": "sooted",
                "sharedDamageKeyId": value["damageKeyId"],
            }
            for value in self.records
        )
        self.assertEqual(
            {
                "Head_Light__sooted",
                "Head_Medium__sooted",
                "Head_Heavy__sooted",
                "Shoulder",
            },
            set(VARIANTS.effective_damage_key_names(state, "head", records, "sooted")),
        )

    def test_key_override_retargets_inherited_progressive_stage(self):
        state = VARIANTS.set_damage_key_override(
            self.state,
            {
                "sharedDamageKeyId": "key_light",
                "overrideDamageKeyId": "key_light_sooted",
                "overrideName": "Head_Light__sooted",
            },
            "sooted",
        )
        resolved = VARIANTS.effective_progressive_sites(
            state,
            [self.site],
            "sooted",
        )[0]
        self.assertEqual(
            "key_light_sooted",
            resolved["stages"]["LIGHT"]["damageKeyId"],
        )
        self.assertEqual(
            "key_medium",
            resolved["stages"]["MEDIUM"]["damageKeyId"],
        )

    def test_progressive_revert_restores_shared_site(self):
        state = VARIANTS.set_progressive_site_override(
            self.state,
            {
                "sharedSiteGuid": "site_head",
                "overrideSiteGuid": "site_head_sooted",
                "ownedDamageKeys": [],
            },
            "sooted",
        )
        state, removed = VARIANTS.remove_progressive_site_override(
            state,
            "site_head",
            "sooted",
        )
        self.assertEqual("site_head_sooted", removed["overrideSiteGuid"])
        self.assertEqual(
            ["site_head"],
            [
                site["siteGuid"]
                for site in VARIANTS.effective_progressive_sites(
                    state, [self.site], "sooted"
                )
            ],
        )


class ReadinessAndExportTests(unittest.TestCase):
    def test_inherited_approved_content_needs_no_duplicate_variant_approval(self):
        state = family_with_two()
        readiness = VARIANTS.effective_readiness(
            state,
            appearance_approved=True,
            technical_compatible=True,
            shared_valid=True,
            variant_id="sooted",
        )
        self.assertEqual("READY", readiness["status"])

    def test_only_override_validity_blocks_ready_variant(self):
        state = VARIANTS.register_shared_actions(family_with_two(), ["attack"])
        state = VARIANTS.set_action_override(state, "attack", "captain_attack", "sooted")
        blocked = VARIANTS.effective_readiness(
            state,
            appearance_approved=True,
            technical_compatible=True,
            shared_valid=True,
            action_validity={"captain_attack": False},
            variant_id="sooted",
        )
        self.assertEqual("NOT_READY", blocked["status"])
        ready = VARIANTS.effective_readiness(
            state,
            appearance_approved=True,
            technical_compatible=True,
            shared_valid=True,
            action_validity={"captain_attack": True},
            variant_id="sooted",
        )
        self.assertEqual("READY", ready["status"])

    def test_provenance_is_resolved_and_free_of_blender_object_names(self):
        state = VARIANTS.register_shared_actions(family_with_two(), ["walk"])
        state = VARIANTS.set_action_override(state, "walk", "sooted_walk", "sooted")
        record = VARIANTS.export_provenance(state, "sooted")
        self.assertEqual(
            "dreadstone.character_variant_provenance.v1",
            record["schema"],
        )
        self.assertEqual("family-bandit", record["technicalFamilyId"])
        self.assertEqual("sooted", record["appearanceVariantId"])
        self.assertEqual("sooted_walk", record["actionOverrides"][0]["overrideActionId"])
        self.assertNotIn("object", json.dumps(record).lower())

    def test_two_variants_have_distinct_shipping_identity(self):
        state = family_with_two()
        filthy = VARIANTS.export_provenance(state, "filthy")
        sooted = VARIANTS.export_provenance(state, "sooted")
        self.assertNotEqual(
            filthy["effectiveForgeVariantIdentity"],
            sooted["effectiveForgeVariantIdentity"],
        )
        self.assertNotEqual(
            filthy["appearanceExportIdentity"],
            sooted["appearanceExportIdentity"],
        )


class StaticIntegrationTests(unittest.TestCase):
    def test_blender_integration_has_central_resolvers_and_copy_on_write_controls(self):
        source = (PACKAGE / "variant_authoring.py").read_text(encoding="utf-8")
        for marker in (
            "def handoff_from_armature(",
            "def effective_actions(",
            "def effective_damage_key_names(",
            "def effective_progressive_collection(",
            "def export_context(",
            "def finished_damage_body_fingerprint(",
            "def _validated_finished_damage_body(",
            "def _stable_skin_and_bones_bake_uv(",
            'bl_idname = "daf.start_finished_texture_family"',
            'bl_idname = "daf.create_forge_texture_variant"',
            'bl_idname = "daf.approve_forge_texture_variant"',
            'bl_idname = "daf.rebaseline_finished_texture_family"',
            'bl_idname = "daf.edit_forge_texture_variant"',
            'bl_idname = "daf.replace_forge_texture_image"',
            'bl_idname = "daf.load_sbf_projection_folder"',
            'bl_idname = "daf.build_sbf_projection_preview"',
            'bl_idname = "daf.bake_sbf_projection"',
            'bl_idname = "daf.apply_sbf_final_texture"',
            'bl_idname = "daf.save_export_forge_texture_variant"',
            'bl_idname = "daf.preview_character_variant"',
            'bl_idname = "daf.export_active_character_variant"',
            'bl_idname = "daf.create_variant_action_override"',
            'bl_idname = "daf.revert_variant_action_override"',
            'bl_idname = "daf.create_variant_damage_override"',
            'bl_idname = "daf.revert_variant_damage_override"',
            'bl_idname = "daf.export_ready_character_variants"',
        ):
            self.assertIn(marker, source)

    def test_primary_ui_is_one_ordered_look_flow(self):
        source = (PACKAGE / "ui" / "panels.py").read_text(encoding="utf-8")
        for marker in (
            "LOOK VARIANTS · TEXTURE → EXPORT",
            "SET UP FROM THIS FINISHED CHARACTER",
            "MAKE EDITABLE TEXTURE COPY",
            "LOAD 4-VIEW FOLDER",
            "BUILD / REFRESH PREVIEW",
            "USE FINAL ON THIS LOOK",
            "CHOOSE ONE FINISHED BASE COLOR IMAGE",
            "SAVE CURRENT LOOK",
            "SAVE + EXPORT",
            "VALIDATE + ACCEPT CURRENT BODY",
            "ADVANCED · IMPORT A SKIN & BONES 2.2 LOOK FAMILY",
            "ADVANCED · TECHNICAL PROOF + AUTHORING OVERRIDES",
        ):
            self.assertIn(marker, source)

    def test_projection_bridge_uses_only_the_bound_source_rig_in_rest_pose(self):
        source = (PACKAGE / "variant_authoring.py").read_text(encoding="utf-8")
        for marker in (
            "def _skin_and_bones_projection_armature(",
            "def _validated_skin_and_bones_projection_armature(",
            "def _neutralize_skin_and_bones_projection_pose(",
            "def _prepare_skin_and_bones_projection_snapshot(",
            "SBF_PROJECTION_VISIBILITY_SCHEMA",
            'rig.data.pose_position = "REST"',
            'obj.name == "DSB_DAMAGE_RIG"',
            "rig.data is damage.data",
            "and getattr(obj, \"data\", None) is rig.data",
            'rig.get("sbf_production_rig", False)',
            '"rigPosePosition"',
            '"rigData"',
            '"targetData"',
            "recovery state is corrupt",
            "clone.use_fake_user = True",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("bpy.ops.pose.transforms_clear", source)

    def test_export_keeps_zero_time_staging_and_adds_variant_provenance(self):
        runtime = (PACKAGE / "runtime_export.py").read_text(encoding="utf-8")
        damage = (PACKAGE / "damage_authoring.py").read_text(encoding="utf-8")
        self.assertIn("_normalize_runtime_action", runtime)
        self.assertIn("point.co[0]) - source_start", runtime)
        self.assertIn('"characterVariant": variant_provenance', damage)
        self.assertIn("variant_authoring.export_context", damage)

    def test_sockets_remain_shared_without_override_operator(self):
        source = (PACKAGE / "variant_authoring.py").read_text(encoding="utf-8")
        self.assertIn("FAMILY_SHARED_NO_VARIANT_OVERRIDE", (PACKAGE / "variant_family.py").read_text(encoding="utf-8"))
        self.assertNotIn("socket_override", source.lower())

    def test_finished_source_proof_repair_is_explicit_and_transactional(self):
        source = (PACKAGE / "damage_authoring.py").read_text(encoding="utf-8")
        self.assertIn("def restore_finished_source_transform_proof(", source)
        self.assertIn('bl_idname = "daf.restore_finished_source_transform"', source)
        self.assertIn("source.matrix_world = previous", source)


if __name__ == "__main__":
    unittest.main()
