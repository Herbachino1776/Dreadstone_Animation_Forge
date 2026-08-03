"""Pure acceptance for the Creature Anatomy Profile foundation."""

from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"
ANATOMY = PACKAGE / "anatomy"

# Import the Blender-independent subpackage without executing the add-on's
# bpy-dependent root __init__.py.
root_package = sys.modules.setdefault(
    "dreadstone_animation_forge",
    types.ModuleType("dreadstone_animation_forge"),
)
root_package.__path__ = [str(PACKAGE)]
anatomy_package = sys.modules.setdefault(
    "dreadstone_animation_forge.anatomy",
    types.ModuleType("dreadstone_animation_forge.anatomy"),
)
anatomy_package.__path__ = [str(ANATOMY)]

schema = importlib.import_module("dreadstone_animation_forge.anatomy.schema")
model = importlib.import_module("dreadstone_animation_forge.anatomy.model")
profiles = importlib.import_module("dreadstone_animation_forge.anatomy.profiles")
resolver = importlib.import_module("dreadstone_animation_forge.anatomy.resolver")
orientation = importlib.import_module("dreadstone_animation_forge.anatomy.orientation")
validation = importlib.import_module("dreadstone_animation_forge.anatomy.validation")
detection = importlib.import_module("dreadstone_animation_forge.anatomy.detection")
persistence = importlib.import_module("dreadstone_animation_forge.anatomy.persistence")
skin_and_bones = importlib.import_module("dreadstone_animation_forge.anatomy.skin_and_bones")


Bone = model.BoneRecord
Snapshot = model.RigSnapshot


def bone(name, parent, head, tail, *, deform=True):
    return Bone(
        name=name,
        parent=parent,
        head=tuple(head),
        tail=tuple(tail),
        length=sum((a - b) ** 2 for a, b in zip(head, tail)) ** 0.5,
        use_deform=deform,
    )


def synthetic_quadruped(*, missing="", reversed_orientation=False):
    forward = -1.0 if reversed_orientation else 1.0
    values = [
        bone("ground_root", "", (0, 0, 0), (0, 0, 0.2)),
        bone("body_center", "ground_root", (0, 0, 1.05), (0, 0.1 * forward, 1.15)),
        bone("pelvis", "body_center", (0, -0.45 * forward, 1.05), (0, -0.2 * forward, 1.15)),
        bone("spine_01", "pelvis", (0, -0.2 * forward, 1.15), (0, 0.25 * forward, 1.2)),
        bone("spine_02", "spine_01", (0, 0.25 * forward, 1.2), (0, 0.65 * forward, 1.25)),
        bone("chest", "spine_02", (0, 0.65 * forward, 1.25), (0, 0.9 * forward, 1.3)),
        bone("neck_01", "chest", (0, 0.9 * forward, 1.3), (0, 1.2 * forward, 1.45)),
        bone("neck_02", "neck_01", (0, 1.2 * forward, 1.45), (0, 1.5 * forward, 1.55)),
        bone("head", "neck_02", (0, 1.5 * forward, 1.55), (0, 1.85 * forward, 1.55)),
        bone("jaw", "head", (0, 1.55 * forward, 1.45), (0, 1.8 * forward, 1.4)),
        bone("tail_01", "pelvis", (0, -0.45 * forward, 1.1), (0, -0.8 * forward, 1.05)),
        bone("tail_02", "tail_01", (0, -0.8 * forward, 1.05), (0, -1.15 * forward, 0.95)),
    ]
    limb_specs = (
        ("front_l", "scapula", "carpus", -0.42, 0.72 * forward, "chest"),
        ("front_r", "scapula", "carpus", 0.42, 0.72 * forward, "chest"),
        ("hind_l", "hip", "hock", -0.38, -0.38 * forward, "pelvis"),
        ("hind_r", "hip", "hock", 0.38, -0.38 * forward, "pelvis"),
    )
    for prefix, root_role, joint_role, x, y, parent in limb_specs:
        root_name = f"{prefix}_{root_role}"
        upper = f"{prefix}_upper"
        lower = f"{prefix}_lower"
        joint = f"{prefix}_{joint_role}"
        paw = f"{prefix}_paw"
        values.extend((
            bone(root_name, parent, (x, y, 1.23), (x, y, 1.08)),
            bone(upper, root_name, (x, y, 1.08), (x, y + 0.08 * forward, 0.72)),
            bone(lower, upper, (x, y + 0.08 * forward, 0.72), (x, y - 0.02 * forward, 0.38)),
            bone(joint, lower, (x, y - 0.02 * forward, 0.38), (x, y + 0.10 * forward, 0.17)),
            bone(paw, joint, (x, y + 0.10 * forward, 0.17), (x, y + 0.28 * forward, 0.06)),
        ))
    values = [value for value in values if value.name != missing]
    return Snapshot.from_bones(values, armature_name="DSB_SYNTHETIC_ARCHITECTURAL_QUADRUPED")


def synthetic_humanoid():
    values = [
        bone("root", "", (0, 0, 0), (0, 0, 0.2)),
        bone("hips", "root", (0, 0, 0.9), (0, 0, 1.05)),
        bone("spine", "hips", (0, 0, 1.05), (0, 0, 1.35)),
        bone("chest", "spine", (0, 0, 1.35), (0, 0, 1.55)),
        bone("neck", "chest", (0, 0, 1.55), (0, 0, 1.7)),
        bone("head", "neck", (0, 0, 1.7), (0, -0.05, 1.95)),
    ]
    for side, x in (("l", -0.3), ("r", 0.3)):
        values.extend((
            bone(f"thigh_{side}", "hips", (x, 0, 0.95), (x, 0, 0.55)),
            bone(f"shin_{side}", f"thigh_{side}", (x, 0, 0.55), (x, 0, 0.15)),
            bone(f"foot_{side}", f"shin_{side}", (x, 0, 0.15), (x, -0.2, 0.08)),
            bone(f"upper_arm_{side}", "chest", (x, 0, 1.48), (x * 1.8, 0, 1.25)),
            bone(f"lower_arm_{side}", f"upper_arm_{side}", (x * 1.8, 0, 1.25), (x * 2.4, 0, 1.05)),
        ))
    return Snapshot.from_bones(values, armature_name="SyntheticHumanoid")


class ProfileSchemaTests(unittest.TestCase):
    def test_builtin_profiles_are_versioned_and_valid(self):
        self.assertEqual(
            {value.profile_id for value in profiles.registry.all()},
            {profiles.HUMANOID_PROFILE_ID, profiles.QUADRUPED_PROFILE_ID},
        )
        for profile in profiles.registry.all():
            self.assertEqual(profile.schema, schema.PROFILE_SCHEMA)
            self.assertEqual(schema.validate_profile(profile), [])
        self.assertEqual(profiles.HUMANOID_PROFILE.forward_axis, "+Y")
        self.assertTrue(profiles.HUMANOID_PROFILE.capabilities["idle"].production_ready)

    def test_required_optional_variable_chains_symmetry_contacts_and_aliases(self):
        profile = profiles.QUADRUPED_PROFILE
        self.assertIn("head", profile.required_roles)
        self.assertIn("jaw", profile.optional_roles)
        self.assertTrue(profile.chains["spine_chain"].required)
        self.assertIsNone(profile.chains["tail_chain"].max_count)
        self.assertIn(("front_l_paw", "front_r_paw"), profile.symmetry_pairs)
        self.assertEqual(len(profile.contact_roles), 4)
        self.assertIn("forepaw_l", profile.aliases["front_l_paw"])

    def test_profile_migration_and_revalidation(self):
        old = profiles.HUMANOID_PROFILE.to_dict()
        old["schema"] = "dreadstone.creature_profile.v0"
        old["id"] = old.pop("profileId")
        migrated = schema.profile_from_dict(old)
        self.assertEqual(migrated.profile_id, profiles.HUMANOID_PROFILE_ID)

    def test_invalid_axes_and_duplicate_registration_fail(self):
        invalid = replace(profiles.HUMANOID_PROFILE, up_axis="-Y")
        self.assertTrue(any("orthogonal" in value for value in schema.validate_profile(invalid)))
        registry = schema.ProfileRegistry()
        registry.register(profiles.HUMANOID_PROFILE)
        with self.assertRaises(ValueError):
            registry.register(replace(profiles.HUMANOID_PROFILE, creature_class="OTHER"))


class ResolutionAndDetectionTests(unittest.TestCase):
    def test_profile_scoring_prefers_matching_anatomy_and_is_repeatable(self):
        snapshot = synthetic_quadruped()
        quad_first = detection.score_profile(profiles.QUADRUPED_PROFILE, snapshot)
        quad_second = detection.score_profile(profiles.QUADRUPED_PROFILE, snapshot)
        human = detection.score_profile(profiles.HUMANOID_PROFILE, snapshot)
        self.assertEqual(quad_first["confidence"], quad_second["confidence"])
        self.assertGreater(quad_first["confidence"], human["confidence"])

    def test_valid_digitigrade_resolves_four_distinct_limb_families(self):
        result = detection.detect_profile(synthetic_quadruped())
        self.assertEqual(result["profileId"], profiles.QUADRUPED_PROFILE_ID)
        self.assertEqual(result["readinessStatus"], "QUADRUPED_READY", result)
        mapping = result["roleMapping"]
        contacts = [mapping[role] for role in profiles.QUADRUPED_PROFILE.contact_roles]
        self.assertEqual(len(set(contacts)), 4)
        self.assertNotEqual(mapping["front_l_upper"], mapping["hind_l_upper"])
        self.assertEqual(mapping["spine_chain"], ["spine_01", "spine_02"])
        self.assertEqual(mapping["tail_chain"], ["tail_01", "tail_02"])

    def test_alias_normalization_and_mapping_digest_are_deterministic(self):
        self.assertEqual(resolver.normalize_name("mixamorig:Upper_Leg.L"), "upperlegl")
        first = {"head": "Head", "spine_chain": ["Spine1", "Spine2"]}
        second = {"spine_chain": ["Spine1", "Spine2"], "head": "Head"}
        self.assertEqual(resolver.mapping_digest(first), resolver.mapping_digest(second))

    def test_orientation_axes_are_orthogonal_and_head_forward(self):
        result = detection.detect_profile(synthetic_quadruped())
        contract = result["orientation"]
        self.assertEqual(contract["forwardAxis"], "+Y")
        self.assertEqual(contract["upAxis"], "+Z")
        self.assertEqual(contract["leftAxis"], "-X")
        self.assertGreater(contract["headForwardAlignment"], 0.9)

    def test_missing_limb_blocks_readiness(self):
        result = detection.detect_profile(
            synthetic_quadruped(missing="front_l_lower"),
            override="QUADRUPED_DIGITIGRADE",
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["readinessStatus"], "MISSING_LIMB_CHAIN")

    def test_duplicate_contact_ownership_blocks_readiness(self):
        snapshot = synthetic_quadruped()
        resolution = resolver.resolve_roles(profiles.QUADRUPED_PROFILE, snapshot)
        mapping = dict(resolution["mapping"])
        mapping["front_r_paw"] = mapping["front_l_paw"]
        contract = orientation.orientation_contract(profiles.QUADRUPED_PROFILE, mapping, snapshot)
        report = validation.validate_mapping(profiles.QUADRUPED_PROFILE, mapping, snapshot, contract)
        self.assertFalse(report["ready"])
        self.assertTrue(any("unique" in value["message"] or "Duplicate" in value["message"] for value in report["blockers"]))

    def test_reversed_head_tail_orientation_is_detected(self):
        result = detection.detect_profile(
            synthetic_quadruped(reversed_orientation=True),
            override="QUADRUPED_DIGITIGRADE",
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["readinessStatus"], "ORIENTATION_AMBIGUOUS")

    def test_ambiguous_auto_detection_does_not_silently_succeed(self):
        combined = Snapshot.from_bones(
            synthetic_quadruped().bones + synthetic_humanoid().bones,
            armature_name="DeliberatelyAmbiguous",
        )
        result = detection.detect_profile(combined)
        self.assertEqual(result["readinessStatus"], "PROFILE_AMBIGUOUS")
        self.assertFalse(result["profileId"])

    def test_explicit_override_selects_validator_but_not_readiness_waiver(self):
        result = detection.detect_profile(
            synthetic_humanoid(),
            override="QUADRUPED_DIGITIGRADE",
        )
        self.assertEqual(result["profileId"], profiles.QUADRUPED_PROFILE_ID)
        self.assertFalse(result["ready"])
        self.assertTrue(result["missingRequirements"])

    def test_capability_lookup_distinguishes_support_from_production(self):
        quad = profiles.capability_status(profiles.QUADRUPED_PROFILE, "walk", {})
        human = profiles.capability_status(
            profiles.HUMANOID_PROFILE,
            "walk",
            {role: role for role in profiles.HUMANOID_PROFILE.required_roles},
        )
        self.assertTrue(quad["supported"])
        self.assertFalse(quad["productionReady"])
        self.assertTrue(human["productionReady"])


class PersistenceTests(unittest.TestCase):
    def test_round_trip_serialization_and_mapping_digest(self):
        owner = {}
        analysis = detection.detect_profile(synthetic_quadruped())
        stored = persistence.store_metadata(owner, analysis)
        loaded = persistence.load_metadata(owner)
        self.assertEqual(loaded["profileId"], profiles.QUADRUPED_PROFILE_ID)
        self.assertEqual(loaded["mappingDigest"], stored["mappingDigest"])
        self.assertEqual(json.loads(owner[persistence.ANATOMY_PROPERTY])["mappingDigest"], stored["mappingDigest"])
        exported = persistence.export_metadata(owner)
        remigrated = persistence.migrate_metadata(exported)
        self.assertEqual(remigrated["profileId"], profiles.QUADRUPED_PROFILE_ID)
        self.assertFalse(remigrated["legacy"])

    def test_missing_metadata_uses_labeled_legacy_humanoid_path(self):
        legacy = persistence.load_metadata({}, infer_legacy=True)
        self.assertEqual(legacy["profileId"], profiles.HUMANOID_PROFILE_ID)
        self.assertTrue(legacy["legacy"])
        self.assertEqual(legacy["analyzerVersion"], "LEGACY_PRE_ANATOMY_PROFILE")
        self.assertEqual(legacy["orientation"]["forwardAxis"], "+Y")

    def test_v0_rig_analysis_migrates_without_losing_mapping(self):
        migrated = persistence.migrate_metadata({
            "schema": "dreadstone.rig_analysis.v0",
            "mapping": {"hips": "Pelvis"},
            "facing": "NEG_Y",
        })
        self.assertEqual(migrated["roleMapping"], {"hips": "Pelvis"})
        self.assertTrue(migrated["legacy"])
        self.assertEqual(migrated["orientation"]["forwardAxis"], "-Y")


class SkinAndBonesHandoffTests(unittest.TestCase):
    class Bones(dict):
        pass

    class Data:
        def __init__(self, names):
            self.bones = SkinAndBonesHandoffTests.Bones(
                (name, object()) for name in names
            )

    class Armature(dict):
        def __init__(self, properties):
            super().__init__(properties)
            self.data = SkinAndBonesHandoffTests.Data(
                skin_and_bones.CANONICAL_HUMANOID_MAPPING.values()
            )
            self.children = []
            self.children_recursive = []

    def canonical_armature(self, *, forward="+Y"):
        mapping = {
            sbf_role: skin_and_bones.CANONICAL_HUMANOID_MAPPING[forge_role]
            for sbf_role, forge_role in skin_and_bones.SBF_TO_FORGE_ROLE.items()
        }
        return self.Armature({
            "sbf_canonical_rig_version": skin_and_bones.SBF_CANONICAL_RIG_VERSION,
            "sbf_forward_axis": forward,
            "sbf_up_axis": "+Z",
            "sbf_root_bone": "root",
            "sbf_orientation_revision": 1,
            "sbf_orientation_state": "CANONICAL_Y_PLUS",
            "sbf_rig_contract_version": 1,
            "sbf_unit_scale_meters": 1.0,
            "sbf_bone_mapping": json.dumps(mapping),
        })

    def test_exact_contract_translates_all_twenty_one_roles(self):
        armature = self.canonical_armature()
        contract = skin_and_bones.require_canonical_yplus(armature)
        self.assertTrue(contract["canonicalYPlus"])
        self.assertEqual(contract["roleMapping"], skin_and_bones.CANONICAL_HUMANOID_MAPPING)
        self.assertEqual(len(contract["roleMapping"]), 21)

    def test_y_minus_contract_is_rejected_without_migration(self):
        armature = self.canonical_armature(forward="-Y")
        with self.assertRaisesRegex(RuntimeError, "no longer supports Y- rigs"):
            skin_and_bones.require_canonical_yplus(armature)


if __name__ == "__main__":
    unittest.main()
