"""Pure and source-level contracts for core and compound trauma authoring."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "trauma_field_core_compound",
    ROOT / "dreadstone_animation_forge" / "trauma_field.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load trauma_field.py")
trauma_field = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trauma_field)


def stamp(stamp_id: str, region_id: str) -> dict[str, object]:
    return trauma_field.normalize_stamp({
        "stampId": stamp_id,
        "displayName": "Compound blunt impact",
        "family": "BROAD_CAVE",
        "placementMode": "SELECTED_VERTICES",
        "capture": {
            "selectionHash": f"selection-{region_id}",
            "topologyFingerprint": "a" * 64,
            "vertexIndices": [0, 1],
        },
        "center": [0.0, 0.0, 0.0],
        "direction": [0.0, 0.0, -1.0],
        "directionMode": "CUSTOM_VECTOR",
        "directionLocal": [0.0, 0.0, -1.0],
        "radius": 0.2,
        "depth": 0.04,
        "falloff": 1.5,
        "influenceMode": "CONNECTED_SURFACE",
        "distanceMode": "WORLD_DISTANCE",
        "featherDistance": 0.03,
        "seamProtection": 0.0,
        "strength": 1.0,
        "maximumDisplacement": 0.06,
        "orderIndex": 0,
    })


def region(
    region_id: str,
    target: str,
    mode: str,
    *,
    detached: str = "",
    fingerprint: str = "a" * 64,
) -> dict[str, object]:
    child_stamp = stamp(f"compound-{region_id}", region_id)
    return {
        "regionId": region_id,
        "regionMode": mode,
        "sourceTargetObject": target,
        "sourceAttachedObject": target,
        "sourceDetachedObject": detached,
        "topologyFingerprint": fingerprint,
        "weightFingerprint": f"weights-{region_id}",
        "vertexCount": 4,
        "polygonCount": 2,
        "relatedSeamId": "head_neck" if region_id in {"head", "body_core"} else "",
        "keys": [{
            "name": f"Impact_{region_id}_v001",
            "family": "broad_cave",
            "side": "configurable",
            "mirrorPartner": "",
            "maximumInfluence": 1.0,
            "maximumDisplacement": 0.06,
            "stamps": [child_stamp],
            "recipeDigest": trauma_field.recipe_digest([child_stamp]),
        }],
    }


def world_field() -> dict[str, object]:
    return trauma_field.normalize_world_impact_field({
        "origin": [0.0, 0.0, 0.0],
        "direction": [0.0, 0.0, -2.0],
        "normal": [0.0, 0.0, 1.0],
        "radius": 0.2,
        "depth": 0.04,
        "falloff": 2.0,
        "strength": 1.5,
        "displacementLimit": 0.05,
        "seed": 1776,
        "traumaFamily": "BROAD_CAVE",
        "transformReference": "WORLD",
        "participantIntersections": [],
    })


def participant(region_id: str, target: str, mode: str, event_seed: int = 1776) -> dict[str, object]:
    return {
        "regionId": region_id,
        "regionMode": mode,
        "targetObject": target,
        "detachedObject": "DSB_SEGMENT_HEAD" if region_id == "head" else "",
        "childKeyName": f"Impact_{region_id}_v001",
        "childStampId": f"compound-{region_id}",
        "seamIds": ["head_neck"] if region_id in {"head", "body_core"} else [],
        "participantSeed": trauma_field.derive_participant_seed(event_seed, region_id, target),
        "intersectionVertexCount": 2,
        "intersectionDigest": f"intersection-{region_id}",
        "goreRecipeDigest": f"gore-{region_id}",
        "goreNodeNames": [f"DSB_GORE_{region_id}"],
    }


def compound_event(*, linked_seams: tuple[str, ...] = ("head_neck",)) -> dict[str, object]:
    event = {
        "schema": trauma_field.COMPOUND_EVENT_SCHEMA,
        "eventId": "Neck_Shoulder_Crush_Left",
        "displayName": "Neck Shoulder Crush Left",
        "traumaFamily": "BROAD_CAVE",
        "impactDirection": "LEFT_TO_RIGHT",
        "severity": 1.0,
        "worldField": world_field(),
        "participants": [
            participant("head", "DSB_ATTACHED_HEAD", "PAIRED_SEGMENT"),
            participant("body_core", "DSB_BODY_CORE", "CORE_SINGLE"),
        ],
        "linkedSeamIds": list(linked_seams),
        "continuityMode": "LOCK_BOUNDARY_TO_SHARED_FIELD",
        "seamContinuity": [],
        "activationWeight": 0.01,
        "activationRule": "SYNCHRONIZED_WEIGHT",
        "goreStyleLinkage": "SHARED_HEAVY_CLOTTED",
        "seed": 1776,
        "validationStatus": "PASS",
    }
    return trauma_field.normalize_compound_event(event, verify_digest=False)


def library(events=()) -> dict[str, object]:
    return trauma_field.build_stamp_library(
        [
            region("head", "DSB_ATTACHED_HEAD", "PAIRED_SEGMENT", detached="DSB_SEGMENT_HEAD"),
            region("body_core", "DSB_BODY_CORE", "CORE_SINGLE"),
        ],
        "3.14.0",
        "2026-07-19.core-compound.1",
        list(events),
    )


class CoreRegionTests(unittest.TestCase):
    def test_region_modes_are_explicit(self):
        self.assertEqual(trauma_field.REGION_MODES, ("PAIRED_SEGMENT", "CORE_SINGLE"))

    def test_core_library_region_needs_no_detached_partner(self):
        body = library()["regions"][0]
        self.assertEqual(body["regionMode"], "CORE_SINGLE")
        self.assertEqual(body["sourceTargetObject"], "DSB_BODY_CORE")
        self.assertEqual(body["sourceDetachedObject"], "")

    def test_core_region_rejects_accidental_detached_requirement(self):
        bad = region("body", "DSB_BODY_CORE", "CORE_SINGLE", detached="FAKE")
        with self.assertRaisesRegex(ValueError, "must not require a detached mesh"):
            trauma_field.build_stamp_library([bad], "3.14.0", "test")

    def test_paired_region_still_requires_detached_partner(self):
        bad = region("head", "DSB_ATTACHED_HEAD", "PAIRED_SEGMENT")
        with self.assertRaisesRegex(ValueError, "has no detached mesh identity"):
            trauma_field.build_stamp_library([bad], "3.14.0", "test")

    def test_core_weight_fingerprint_round_trip(self):
        restored = trauma_field.normalize_stamp_library(json.loads(json.dumps(library())))
        body = restored["regions"][0]
        self.assertEqual(body["weightFingerprint"], "weights-body_core")

    def test_compatibility_rejects_region_mode_mismatch(self):
        payload = library()
        targets = {
            item["regionId"]: {
                "regionMode": "PAIRED_SEGMENT",
                "topologyFingerprint": item["topologyFingerprint"],
                "vertexCount": item["vertexCount"],
                "polygonCount": item["polygonCount"],
            }
            for item in payload["regions"]
        }
        errors = trauma_field.stamp_library_compatibility_errors(payload, targets)
        self.assertTrue(any("mode does not match" in error for error in errors))

    def test_core_gore_uses_explicit_core_ownership_role(self):
        self.assertEqual(
            trauma_field.gore_generated_object_name("body_core", "Impact", "CORE"),
            "DSB_GORE_CORE_body_core_Impact",
        )

    def test_portable_core_recipe_contains_no_generated_mesh_bytes(self):
        self.assertNotIn("meshBytes", json.dumps(library()))

    def test_legacy_v3_pair_library_remains_loadable(self):
        payload = library()
        payload["formatVersion"] = 3
        payload.pop("compoundEvents", None)
        payload.pop("compoundEventCount", None)
        payload.pop("libraryDigest", None)
        restored = trauma_field.normalize_stamp_library(payload)
        self.assertEqual(restored["formatVersion"], 3)
        self.assertEqual(restored["compoundEvents"], [])

    def test_current_portable_format_is_four(self):
        self.assertEqual(library()["formatVersion"], 4)


class CompoundFieldTests(unittest.TestCase):
    def test_world_field_is_normalized_to_world_space(self):
        field = world_field()
        self.assertEqual(field["coordinateSpace"], "WORLD")
        self.assertEqual(field["direction"], [0.0, 0.0, -1.0])

    def test_world_field_rejects_zero_direction(self):
        bad = world_field()
        bad["direction"] = [0.0, 0.0, 0.0]
        with self.assertRaisesRegex(ValueError, "zero length"):
            trauma_field.normalize_world_impact_field(bad)

    def test_world_field_rejects_non_positive_radius(self):
        bad = world_field()
        bad["radius"] = 0.0
        with self.assertRaisesRegex(ValueError, "radius must be positive"):
            trauma_field.normalize_world_impact_field(bad)

    def test_world_weight_is_full_at_origin(self):
        self.assertEqual(trauma_field.world_impact_weight((0, 0, 0), world_field()), 1.0)

    def test_world_weight_is_zero_at_radius(self):
        self.assertEqual(trauma_field.world_impact_weight((0.2, 0, 0), world_field()), 0.0)

    def test_one_world_field_evaluates_against_two_mesh_fixtures(self):
        field = world_field()
        first = trauma_field.evaluate_world_impact_field([(0, 0, 0), (0.3, 0, 0)], field)
        second = trauma_field.evaluate_world_impact_field([(0.1, 0, 0), (0.4, 0, 0)], field)
        self.assertEqual(first["affectedVertexIndices"], (0,))
        self.assertEqual(second["affectedVertexIndices"], (0,))
        self.assertNotEqual(first["deltas"], second["deltas"])

    def test_world_field_honors_participant_mask(self):
        result = trauma_field.evaluate_world_impact_field([(0, 0, 0), (0.05, 0, 0)], world_field(), [0.0, 1.0])
        self.assertEqual(result["affectedVertexIndices"], (1,))

    def test_world_field_enforces_displacement_limit(self):
        result = trauma_field.evaluate_world_impact_field([(0, 0, 0)], world_field())
        self.assertAlmostEqual(result["maximumDisplacement"], 0.05)

    def test_participant_seed_is_deterministic(self):
        first = trauma_field.derive_participant_seed(1776, "head", "DSB_ATTACHED_HEAD")
        second = trauma_field.derive_participant_seed(1776, "head", "DSB_ATTACHED_HEAD")
        self.assertEqual(first, second)

    def test_participant_seed_differs_by_mesh(self):
        first = trauma_field.derive_participant_seed(1776, "head", "DSB_ATTACHED_HEAD")
        second = trauma_field.derive_participant_seed(1776, "body", "DSB_BODY_CORE")
        self.assertNotEqual(first, second)

    def test_compound_event_canonicalizes_participant_order(self):
        raw = compound_event()
        raw["participants"].reverse()
        raw.pop("recipeDigest", None)
        normalized = trauma_field.normalize_compound_event(raw, verify_digest=False)
        self.assertEqual([item["regionId"] for item in normalized["participants"]], ["body_core", "head"])

    def test_compound_digest_is_deterministic(self):
        event = compound_event()
        self.assertEqual(
            trauma_field.compound_event_digest(event),
            trauma_field.compound_event_digest(copy.deepcopy(event)),
        )

    def test_compound_recipe_digest_excludes_rebuild_outputs(self):
        event = compound_event()
        first = trauma_field.compound_event_digest(event)
        event["participants"][0]["intersectionDigest"] = "rebuilt-again"
        event["participants"][0]["goreNodeNames"] = ["new-generated-node"]
        event["worldField"]["participantIntersections"] = [{"regionId": "head", "vertexCount": 99}]
        event["seamContinuity"] = [{"seamId": "head_neck", "maximumMismatchAfter": 0.0}]
        self.assertEqual(first, trauma_field.compound_event_digest(event))

    def test_compound_digest_tampering_is_detected(self):
        event = compound_event()
        event["severity"] = 2.0
        with self.assertRaisesRegex(ValueError, "recipe digest"):
            trauma_field.normalize_compound_event(event)

    def test_compound_requires_two_participants(self):
        event = compound_event()
        event["participants"] = event["participants"][:1]
        errors = trauma_field.validate_compound_event(event)
        self.assertTrue(any("at least two participants" in error for error in errors))

    def test_compound_rejects_duplicate_participant(self):
        event = compound_event()
        event["participants"][1] = copy.deepcopy(event["participants"][0])
        errors = trauma_field.validate_compound_event(event)
        self.assertTrue(any("duplicate participant" in error for error in errors))

    def test_compound_reports_missing_registered_region(self):
        errors = trauma_field.validate_compound_event(compound_event(), registered_regions={})
        self.assertTrue(any("is not registered" in error for error in errors))

    def test_compound_reports_wrong_mesh_identity(self):
        event = compound_event()
        regions = {
            "head": {"targetObject": "WRONG"},
            "body_core": {"targetObject": "DSB_BODY_CORE"},
        }
        errors = trauma_field.validate_compound_event(event, registered_regions=regions)
        self.assertTrue(any("wrong mesh identity" in error for error in errors))

    def test_compound_reports_stale_region_mode_binding(self):
        event = compound_event()
        event["participants"][0]["regionMode"] = "PAIRED_SEGMENT"
        event["participants"][0]["detachedObject"] = "FAKE"
        regions = {
            "head": {"regionMode": "PAIRED_SEGMENT", "targetObject": "DSB_ATTACHED_HEAD", "detachedObject": "DSB_SEGMENT_HEAD"},
            "body_core": {"regionMode": "CORE_SINGLE", "targetObject": "DSB_BODY_CORE", "detachedObject": ""},
        }
        errors = trauma_field.validate_compound_event(event, registered_regions=regions)
        self.assertTrue(any("stale region-mode binding" in error for error in errors))

    def test_compound_core_participant_rejects_detached_requirement(self):
        event = compound_event()
        event["participants"][0]["detachedObject"] = "FAKE"
        errors = trauma_field.validate_compound_event(event)
        self.assertTrue(any("must not require a detached mesh" in error for error in errors))

    def test_compound_reports_stale_participant_seed(self):
        event = compound_event()
        event["participants"][0]["participantSeed"] += 1
        errors = trauma_field.validate_compound_event(event)
        self.assertTrue(any("stale deterministic seed" in error for error in errors))

    def test_compound_reports_missing_child_key_name(self):
        event = compound_event()
        event["participants"][0]["childKeyName"] = ""
        errors = trauma_field.validate_compound_event(event)
        self.assertTrue(any("no child deformation key" in error for error in errors))

    def test_compound_reports_missing_child_stamp_id(self):
        event = compound_event()
        event["participants"][0]["childStampId"] = ""
        errors = trauma_field.validate_compound_event(event)
        self.assertTrue(any("no child stamp ID" in error for error in errors))

    def test_disjoint_compound_event_may_have_no_linked_seam(self):
        event = compound_event(linked_seams=())
        self.assertEqual(trauma_field.validate_compound_event(event), [])

    def test_compound_rejects_invalid_continuity_mode(self):
        event = compound_event()
        event["continuityMode"] = "WELD"
        errors = trauma_field.validate_compound_event(event)
        self.assertTrue(any("invalid seam-continuity mode" in error for error in errors))

    def test_compound_rejects_invalid_activation_weight(self):
        event = compound_event()
        event["activationWeight"] = math.inf
        errors = trauma_field.validate_compound_event(event)
        self.assertTrue(any("activation weight" in error for error in errors))

    def test_compound_portable_round_trip(self):
        restored = trauma_field.normalize_stamp_library(json.loads(json.dumps(library([compound_event()]))))
        self.assertEqual(restored["compoundEventCount"], 1)
        self.assertEqual(restored["compoundEvents"][0]["eventId"], "Neck_Shoulder_Crush_Left")

    def test_compound_portable_digest_detects_tampering(self):
        payload = library([compound_event()])
        payload["compoundEvents"][0]["severity"] = 5.0
        with self.assertRaisesRegex(ValueError, "recipe digest"):
            trauma_field.normalize_stamp_library(payload)


class SeamContinuityTests(unittest.TestCase):
    def setUp(self):
        self.first = [(0.1, 0, 0), (0, 0.2, 0), (0, 0, 0.3), (9, 9, 9)]
        self.second = [(0.0, 0, 0), (0, 0.0, 0), (0, 0, 0.1), (-9, -9, -9)]
        self.mapping = [(0, 0), (1, 1), (2, 2)]

    def test_lock_boundary_produces_zero_mismatch(self):
        result = trauma_field.resolve_seam_boundary_displacements(self.first, self.second, self.mapping, "LOCK_BOUNDARY_TO_SHARED_FIELD")
        self.assertEqual(result["maximumMismatchAfter"], 0.0)

    def test_blend_boundary_produces_zero_mismatch(self):
        result = trauma_field.resolve_seam_boundary_displacements(self.first, self.second, self.mapping, "BLEND_ACROSS_SEAM")
        self.assertEqual(result["maximumMismatchAfter"], 0.0)

    def test_protect_boundary_keeps_all_boundary_deltas_zero(self):
        result = trauma_field.resolve_seam_boundary_displacements(self.first, self.second, self.mapping, "PROTECT_SEAM")
        self.assertTrue(all(result["firstDeltas"][index] == (0.0, 0.0, 0.0) for index in range(3)))

    def test_seam_reports_pre_resolution_mismatch(self):
        result = trauma_field.resolve_seam_boundary_displacements(self.first, self.second, self.mapping, "LOCK_BOUNDARY_TO_SHARED_FIELD")
        self.assertGreater(result["maximumMismatchBefore"], 0.0)

    def test_seam_resolution_does_not_mutate_inputs_or_topology(self):
        first = copy.deepcopy(self.first)
        second = copy.deepcopy(self.second)
        result = trauma_field.resolve_seam_boundary_displacements(first, second, self.mapping, "LOCK_BOUNDARY_TO_SHARED_FIELD")
        self.assertEqual(first, self.first)
        self.assertEqual(second, self.second)
        self.assertFalse(result["topologyMutated"])

    def test_seam_mapping_must_be_one_to_one(self):
        with self.assertRaisesRegex(ValueError, "one-to-one"):
            trauma_field.resolve_seam_boundary_displacements(self.first, self.second, [(0, 0), (0, 1)], "PROTECT_SEAM")

    def test_seam_mapping_rejects_out_of_range_vertex(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            trauma_field.resolve_seam_boundary_displacements(self.first, self.second, [(99, 0)], "PROTECT_SEAM")


class BlenderIntegrationSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deformation = (ROOT / "dreadstone_animation_forge" / "deformation_authoring.py").read_text(encoding="utf-8")
        cls.addon = (ROOT / "dreadstone_animation_forge" / "__init__.py").read_text(encoding="utf-8")

    def test_core_registration_is_explicit_not_missing_pair_inference(self):
        self.assertIn('regionMode": CORE_SINGLE', self.deformation)
        self.assertIn('bl_idname = "daf.register_core_deformation_region"', self.deformation)

    def test_body_impact_starter_names_are_present(self):
        for name in ("Body_Impact_Front_v001", "Body_Impact_Left_v001", "Body_Impact_Right_v001", "Body_Impact_Back_v001"):
            self.assertIn(name, self.deformation)

    def test_forearm_impact_starter_names_are_present(self):
        self.assertIn("Forearm_L_Impact_Outer_v001", self.deformation)
        self.assertIn("Forearm_R_Impact_Outer_v001", self.deformation)

    def test_gore_sources_support_core_and_pair_roles(self):
        self.assertIn('return ((attached, "CORE"),)', self.deformation)
        self.assertIn('(attached, "ATTACHED")', self.deformation)
        self.assertIn('(detached, "DETACHED")', self.deformation)

    def test_compound_gore_uses_derived_participant_seed(self):
        self.assertIn("participant_seed = trauma_field.derive_participant_seed", self.deformation)
        self.assertIn('"Gore_Crush_Heavy_Clotted"', self.deformation)

    def test_batch_heavy_gore_records_failures(self):
        self.assertIn('failed.append(f"{region_id}/{key_name}: {exc}")', self.deformation)
        self.assertIn('return {"applied": applied, "skipped": skipped, "failed": failed}', self.deformation)

    def test_compound_preview_uses_one_atomic_damage_state(self):
        self.assertIn('clear_damage_preview(context, update_status=False)', self.deformation)
        self.assertIn('damage_state = {"kind": "COMPOUND", "entries": entries}', self.deformation)
        self.assertIn('_store_damage_preview_state(context, damage_state)', self.deformation)

    def test_compound_blend_feathers_inward_without_weld(self):
        self.assertIn("def _feather_compound_seam_inward", self.deformation)
        self.assertIn('"topologyMutated": False', self.deformation)

    def test_compound_manifest_maps_individual_mesh_morph_targets(self):
        self.assertIn('"morphTargets": morph_targets', self.deformation)
        self.assertIn('"attachedDetachedRole": "CORE"', self.deformation)
        self.assertIn('"attachedDetachedRole": "DETACHED"', self.deformation)

    def test_compound_manifest_defaults_inactive(self):
        self.assertIn('"defaultState": "INACTIVE"', self.deformation)
        self.assertIn('"undamagedState": "ALL_CHILD_MORPHS_ZERO_AND_GORE_INACTIVE"', self.deformation)

    def test_three_guard_draft_actions_have_stable_names(self):
        for name in (
            "DSB_DRAFT_Mace_Brace_Head_TwoArm",
            "DSB_DRAFT_Mace_Brace_Head_LeftArm",
            "DSB_DRAFT_Mace_Brace_Head_RightArm",
        ):
            self.assertIn(name, self.addon)

    def test_guard_variants_present_expected_damage_regions(self):
        self.assertIn('("forearm_left", "forearm_right", "head")', self.addon)
        self.assertIn('("forearm_left", "head")', self.addon)
        self.assertIn('("forearm_right", "head")', self.addon)

    def test_guard_schedule_is_scene_fps_aware(self):
        self.assertIn("def mace_guard_frame_schedule(fps", self.addon)
        self.assertIn("context.scene.render.fps_base", self.addon)

    def test_guard_actions_have_required_markers(self):
        self.assertIn('for marker_name in ("Brace_Start", "Guard_Active", "Brace_End")', self.addon)

    def test_guard_keying_avoids_bone_scale_channels(self):
        key_pose = self.addon[self.addon.index("def key_pose("):self.addon.index("DRAFT_ACTION_NAMES =")]
        self.assertIn('keyframe_insert("rotation_quaternion"', key_pose)
        self.assertIn('keyframe_insert("location"', key_pose)
        self.assertNotIn("scale", key_pose)

    def test_guard_generation_checks_required_mapped_bones_before_replacement(self):
        missing = self.addon.index('raise RuntimeError("Missing mapped bones for mace head guard: "')
        replace = self.addon.index('action = ensure_draft_action(arm, DRAFT_ACTION_NAMES[kind])', missing)
        self.assertLess(missing, replace)

    def test_three_guard_regeneration_is_transactional(self):
        self.assertIn("def generate_all_mace_guard_actions(context):", self.addon)
        self.assertIn('backup.name = "__DSB_GUARD_BACKUP_" + draft_name', self.addon)
        self.assertIn("actions = generate_all_mace_guard_actions(context)", self.addon)

    def test_guard_validation_checks_forearm_height(self):
        self.assertIn("remains grossly below head height at Guard_Active", self.addon)

    def test_guard_approval_metadata_is_exported(self):
        self.assertIn('"maceHeadGuardActions": brace_actions', self.deformation)
        self.assertIn('"rootMotionPolicy": str(action.get("dsb_root_motion_policy", "IN_PLACE"))', self.deformation)

    def test_guard_preview_does_not_key_shape_values(self):
        start = self.addon.index("class DAF_OT_preview_mace_guard_active")
        end = self.addon.index("class DAF_OT_validate_mace_head_guards", start)
        preview = self.addon[start:end]
        self.assertNotIn("shape_key", preview)
        self.assertIn("Guard_Active", preview)

    def test_guard_validation_handles_malformed_region_metadata(self):
        self.assertIn("Mace guard action has malformed presented-region metadata.", self.addon)

    def test_export_contract_declares_runtime_not_included(self):
        self.assertIn('"runtimeImplementationIncluded": False', self.deformation)


if __name__ == "__main__":
    unittest.main()
