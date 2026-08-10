import copy
import importlib.util
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


if __name__ == "__main__":
    unittest.main()
