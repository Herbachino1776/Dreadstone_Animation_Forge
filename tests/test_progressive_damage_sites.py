import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "test_progressive_sites",
    ROOT
    / "dreadstone_animation_forge"
    / "deformation"
    / "progressive_sites.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load progressive_sites.py")
progressive_sites = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(progressive_sites)


def assigned(stage, key_id, key_name, triangles=100):
    return {
        **progressive_sites.empty_stage(stage, f"stage_{stage.lower()}"),
        "damageKeyId": key_id,
        "deformationKeyName": key_name,
        "activeStampId": f"stamp_{stage.lower()}",
        "regionId": "head",
        "targetObject": "Head",
        "recipeDigest": f"recipe_{stage.lower()}",
        "deformationDigest": f"deform_{stage.lower()}",
        "captureDigest": f"capture_{stage.lower()}",
        "generatedComponentIds": {"ATTACHED:RAISED": f"mesh_{stage.lower()}"},
        "generatedNodeNames": {"ATTACHED:RAISED": f"node_{stage.lower()}"},
        "ownershipRoles": ["ATTACHED", "DETACHED"],
        "saved": True,
        "validationStatus": "PASS",
        "triangleCount": triangles * 2,
        "visibleTriangleCount": triangles,
    }


class ProgressiveDamageSiteTests(unittest.TestCase):
    def site(self):
        site = progressive_sites.new_site(
            "Head Left",
            "head",
            site_id="head_left",
            site_guid="site_fixed",
        )
        for index, stage in enumerate(progressive_sites.STAGE_ORDER, 1):
            site["stages"][stage] = assigned(
                stage,
                f"key_{stage.lower()}",
                f"Artist Key {index}",
                100 * index,
            )
        site["validationStatus"] = "PASS"
        return progressive_sites.normalize_site(site)

    def test_schema_normalization_and_stable_ids(self):
        site = progressive_sites.normalize_site(self.site())
        self.assertEqual(site["schema"], progressive_sites.SITE_SCHEMA)
        self.assertEqual(site["siteGuid"], "site_fixed")
        self.assertEqual(
            progressive_sites.normalize_site(site)["stages"]["LIGHT"]["stageId"],
            site["stages"]["LIGHT"]["stageId"],
        )
        self.assertEqual(site["status"], "READY_FOR_EXPORT")

    def test_additive_empty_migration_does_not_infer_sites(self):
        collection = progressive_sites.normalize_sites()
        self.assertEqual(collection["sites"], [])
        self.assertEqual(collection["siteCount"], 0)

    def test_stage_assignment_and_duplicate_rejection(self):
        first = progressive_sites.new_site(
            "First", "head", site_guid="site_first"
        )
        second = progressive_sites.new_site(
            "Second", "head", site_guid="site_second"
        )
        collection = progressive_sites.normalize_sites({"sites": [first, second]})
        collection = progressive_sites.assign_stage(
            collection,
            "site_first",
            "LIGHT",
            assigned("LIGHT", "key_one", "Artist Key"),
        )
        with self.assertRaisesRegex(ValueError, "already drives"):
            progressive_sites.assign_stage(
                collection,
                "site_second",
                "HEAVY",
                assigned("HEAVY", "key_one", "Artist Key"),
            )

    def test_ordered_severity_anchors(self):
        self.assertEqual(
            progressive_sites.normalize_anchors(),
            {"light": 0.33, "medium": 0.66, "heavy": 1.0},
        )
        with self.assertRaisesRegex(ValueError, "strictly ordered"):
            progressive_sites.normalize_anchors(
                {"light": 0.66, "medium": 0.33, "heavy": 1.0}
            )

    def test_smoothstep_and_severity_clamping(self):
        self.assertAlmostEqual(progressive_sites.smoothstep(0.5), 0.5)
        self.assertEqual(
            progressive_sites.evaluate_weights(-10)["severity"],
            0.0,
        )
        self.assertEqual(
            progressive_sites.evaluate_weights(10)["severity"],
            1.0,
        )

    def test_exact_anchor_weights(self):
        anchors = progressive_sites.DEFAULT_ANCHORS
        expected = (
            (0.0, {"LIGHT": 0.0, "MEDIUM": 0.0, "HEAVY": 0.0}),
            (anchors["light"], {"LIGHT": 1.0, "MEDIUM": 0.0, "HEAVY": 0.0}),
            (anchors["medium"], {"LIGHT": 0.0, "MEDIUM": 1.0, "HEAVY": 0.0}),
            (anchors["heavy"], {"LIGHT": 0.0, "MEDIUM": 0.0, "HEAVY": 1.0}),
        )
        for severity, weights in expected:
            self.assertEqual(
                progressive_sites.evaluate_weights(severity)["weights"],
                weights,
            )

    def test_adjacent_only_and_maximum_total_weight(self):
        for index in range(1001):
            result = progressive_sites.evaluate_weights(index / 1000.0)
            self.assertLessEqual(result["activeMorphCount"], 2)
            self.assertLessEqual(result["totalWeight"], 1.0 + 1e-12)
            self.assertFalse(
                result["weights"]["LIGHT"] > 0
                and result["weights"]["HEAVY"] > 0
            )

    def test_midpoint_gore_replacement(self):
        self.assertIsNone(progressive_sites.detailed_gore_stage(0.0))
        self.assertIsNone(progressive_sites.detailed_gore_stage(0.16))
        self.assertEqual(
            progressive_sites.detailed_gore_stage(0.165),
            "LIGHT",
        )
        self.assertEqual(
            progressive_sites.detailed_gore_stage(0.40),
            "LIGHT",
        )
        self.assertEqual(
            progressive_sites.detailed_gore_stage(0.495),
            "MEDIUM",
        )
        self.assertEqual(
            progressive_sites.detailed_gore_stage(0.83),
            "HEAVY",
        )

    def test_manifest_and_cost_contract(self):
        site = self.site()
        manifest = progressive_sites.manifest_site(site)
        self.assertEqual(
            [stage["stage"] for stage in manifest["stages"]],
            list(progressive_sites.STAGE_ORDER),
        )
        self.assertFalse(
            manifest["activationContract"]["detailedGoreStagesStack"]
        )
        self.assertEqual(
            manifest["cost"]["residentStageGoreTriangles"],
            1200,
        )
        self.assertEqual(
            manifest["cost"]["maximumVisibleStageGoreTriangles"],
            300,
        )
        self.assertEqual(
            manifest["cost"]["maximumTransitionGoreTriangles"],
            300,
        )

    def test_digest_is_deterministic(self):
        site = self.site()
        self.assertEqual(
            progressive_sites.canonical_digest(site),
            progressive_sites.canonical_digest(copy.deepcopy(site)),
        )


if __name__ == "__main__":
    unittest.main()
