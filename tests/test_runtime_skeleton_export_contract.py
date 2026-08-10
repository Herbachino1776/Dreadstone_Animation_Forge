import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "dreadstone_animation_forge" / "deformation" / "gltf_validation.py"
SPEC = importlib.util.spec_from_file_location("runtime_gltf_validation", MODULE_PATH)
GLTF_VALIDATION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GLTF_VALIDATION)


def fixture():
    gltf = {
        "asset": {"version": "2.0"},
        "nodes": [
            {
                "name": "DSB_DAMAGE_RIG",
                "children": [1],
                "extras": {"dsb_damage_role": "authoring_rig"},
            },
            {"name": "root", "children": [2]},
            {"name": "body"},
            {"name": "DSB_BODY_CORE", "mesh": 0, "skin": 0},
            {"name": "DSB_SEGMENT_HEAD", "mesh": 1},
        ],
        "meshes": [
            {"primitives": [{"attributes": {"POSITION": 0}}]},
            {"primitives": [{"attributes": {"POSITION": 0}}]},
        ],
        "skins": [
            {"name": "DSB_DAMAGE_RIG", "joints": [1, 2]},
        ],
        "accessors": [
            {"type": "VEC3"},
            {"type": "SCALAR", "min": [0.0], "max": [1.0]},
            {"type": "VEC4"},
        ],
        "animations": [
            {
                "name": "DSB_Idle_Humanoid_v002",
                "extras": {
                    "dsb_approved": True,
                    "dsb_draft": False,
                    "dsb_approved_kind": "IDLE",
                    "dsb_runtime_armature": "DSB_DAMAGE_RIG",
                },
                "samplers": [{"input": 1, "output": 2}],
                "channels": [
                    {
                        "sampler": 0,
                        "target": {"node": 2, "path": "rotation"},
                    }
                ],
            }
        ],
    }
    manifest = {
        "source": {
            "object": "SBF_CLEAN_CHARACTER",
            "armature": "SBF_ProductionRig",
        },
        "runtimeSkeleton": {
            "armature": "DSB_DAMAGE_RIG",
            "protectedSourceObject": "DSB_SOURCE_MODEL_PROTECTED",
            "requiredBones": ["root", "body"],
        },
        "runtimeAnimations": {
            "clips": [
                {
                    "name": "DSB_Idle_Humanoid_v002",
                    "approvedKind": "IDLE",
                    "clipDurationSeconds": 1.0,
                }
            ],
            "rejectedSourceActionCount": 1,
            "rejectedSourceActions": ["DSB_Idle_Humanoid_v001"],
        },
        "intact": {"bodyCore": "DSB_BODY_CORE", "attachedSegments": []},
        "segments": [{"detachedObject": "DSB_SEGMENT_HEAD"}],
        "deformations": {},
    }
    return gltf, manifest


class RuntimeSkeletonExportContractTests(unittest.TestCase):
    def test_one_runtime_skeleton_and_approved_animation_pass(self):
        gltf, manifest = fixture()
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["status"], "PASS", result["errors"])
        self.assertEqual(result["schema"], "dreadstone.final_glb_validation.v2")
        self.assertEqual(result["runtimeSkeleton"]["skeletonCount"], 1)
        self.assertEqual(result["runtimeAnimations"]["exportedCount"], 1)
        self.assertEqual(result["runtimeAnimations"]["rejectedSourceActionCount"], 1)

    def test_source_authoring_nodes_are_rejected(self):
        gltf, manifest = fixture()
        gltf["nodes"].append({"name": "SBF_ProductionRig"})
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["runtimeSkeleton"]["status"], "FAIL")
        self.assertTrue(result["runtimeSkeleton"]["sourceArmaturePresentInGlb"])

    def test_skin_joint_outside_runtime_hierarchy_is_rejected(self):
        gltf, manifest = fixture()
        outside = len(gltf["nodes"])
        gltf["nodes"].append({"name": "source_root"})
        gltf["skins"][0]["joints"].append(outside)
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["runtimeSkeleton"]["status"], "FAIL")
        self.assertTrue(any("outside" in error for error in result["runtimeSkeleton"]["errors"]))

    def test_intact_mesh_requires_runtime_skin(self):
        gltf, manifest = fixture()
        gltf["nodes"][3].pop("skin")
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertTrue(any("not skinned" in error for error in result["runtimeSkeleton"]["errors"]))

    def test_rigid_detached_piece_must_remain_rigid(self):
        gltf, manifest = fixture()
        gltf["nodes"][4]["skin"] = 0
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertTrue(any("Rigid detached" in error for error in result["runtimeSkeleton"]["errors"]))

    def test_animation_channel_cannot_target_source_node(self):
        gltf, manifest = fixture()
        source_index = len(gltf["nodes"])
        gltf["nodes"].append({"name": "SBF_ProductionRig"})
        gltf["animations"][0]["channels"][0]["target"]["node"] = source_index
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["runtimeAnimations"]["status"], "FAIL")
        self.assertTrue(any("non-runtime" in error for error in result["runtimeAnimations"]["errors"]))

    def test_source_only_accidental_clip_is_rejected(self):
        gltf, manifest = fixture()
        accidental = copy.deepcopy(gltf["animations"][0])
        accidental["name"] = "DSB_Idle_Humanoid_v001"
        gltf["animations"].append(accidental)
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertIn(
            "DSB_Idle_Humanoid_v001",
            result["runtimeAnimations"]["unexpectedAnimations"],
        )

    def test_required_runtime_bones_are_enforced(self):
        gltf, manifest = fixture()
        gltf["nodes"][2]["name"] = "renamed_body"
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(result["runtimeSkeleton"]["missingBones"], ["body"])

    def test_frame_one_runtime_timeline_is_rejected_even_when_span_matches(self):
        gltf, manifest = fixture()
        gltf["accessors"][1]["min"] = [1.0 / 24.0]
        gltf["accessors"][1]["max"] = [2.0]
        manifest["runtimeAnimations"]["clips"][0]["clipDurationSeconds"] = 47.0 / 24.0
        result = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        errors = " ".join(result["runtimeAnimations"]["errors"])
        self.assertEqual(result["runtimeAnimations"]["status"], "FAIL")
        self.assertIn("minimum time is not normalized to zero", errors)
        self.assertIn("maximum time does not match", errors)
        self.assertNotIn("exported duration does not match", errors)

    def test_runtime_timeline_requires_declared_duration_end_and_span(self):
        gltf, manifest = fixture()
        manifest["runtimeAnimations"]["clips"][0].pop("clipDurationSeconds")
        missing = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertTrue(any(
            "no valid declared clip duration" in error
            for error in missing["runtimeAnimations"]["errors"]
        ))

        gltf, manifest = fixture()
        gltf["accessors"][1]["max"] = [1.125]
        drifted = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        errors = " ".join(drifted["runtimeAnimations"]["errors"])
        self.assertIn("maximum time does not match", errors)
        self.assertIn("exported duration does not match", errors)

    def test_offensive_phases_must_fit_the_normalized_exported_clip(self):
        gltf, manifest = fixture()
        metadata = {
            "schema": "dreadstone.offensive_action.v1",
            "combatActionId": "fixture_attack",
            "clipDurationSeconds": 1.0,
            "phases": {
                "windup": {"startSeconds": 0.0, "endSeconds": 0.4},
                "active": {"startSeconds": 0.4, "endSeconds": 0.6},
                "recovery": {"startSeconds": 0.6, "endSeconds": 1.0},
            },
            "commitment": {"timeSeconds": 0.4},
        }
        clip = manifest["runtimeAnimations"]["clips"][0]
        clip["approvedKind"] = "ATTACK_FIXTURE"
        clip["offensiveAction"] = copy.deepcopy(metadata)
        extras = gltf["animations"][0]["extras"]
        extras["dsb_approved_kind"] = "ATTACK_FIXTURE"
        extras["dsb_offensive_action_json"] = json.dumps(metadata)
        passing = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertEqual(passing["runtimeAnimations"]["status"], "PASS", passing["errors"])

        metadata["phases"]["recovery"]["endSeconds"] = 0.9
        clip["offensiveAction"] = copy.deepcopy(metadata)
        extras["dsb_offensive_action_json"] = json.dumps(metadata)
        failing = GLTF_VALIDATION.validate_damage_gltf(gltf, manifest)
        self.assertTrue(any(
            "RECOVERY does not end at the exported clip end" in error
            for error in failing["runtimeAnimations"]["errors"]
        ))


if __name__ == "__main__":
    unittest.main()
