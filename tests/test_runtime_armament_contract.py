"""Blender-independent M6 socket and offensive metadata regression."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"
FIXTURE = ROOT / "tests" / "fixtures" / "m6_runtime_capability.json"


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sockets = load_module("attachment_socket_contract")
offense = load_module("offensive_actions")


class RuntimeArmamentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.bones = cls.fixture["runtimeSkeleton"]["requiredBones"]

    def test_shared_fixture_is_valid_and_canonical(self):
        socket_contract = self.fixture["runtimeAttachmentSockets"]
        self.assertEqual([], sockets.validate_socket_contract(socket_contract, self.bones))
        self.assertEqual(21, socket_contract["runtimeBoneCount"])
        self.assertEqual(
            {"arm_left_hand", "arm_right_hand"},
            {record["parentRuntimeBone"] for record in socket_contract["sockets"]},
        )
        action = self.fixture["runtimeAnimations"]["offensiveActions"][0]
        self.assertEqual(
            [],
            offense.validate_offensive_metadata(
                action,
                clip_duration_seconds=action["clipDurationSeconds"],
                approved=True,
                draft=False,
                available_socket_roles={"MAIN_HAND_R", "MAIN_HAND_L"},
            ),
        )

    def test_all_eight_variants_have_unique_stable_identities_and_valid_phases(self):
        identities = set()
        for variant in offense.OFFENSIVE_ACTION_VARIANTS.values():
            metadata, schedule = offense.phase_metadata(variant, 24.0)
            self.assertNotIn(metadata["combatActionId"], identities)
            identities.add(metadata["combatActionId"])
            self.assertLess(schedule["start"], schedule["activeStart"])
            self.assertLess(schedule["activeStart"], schedule["activeEnd"])
            self.assertLess(schedule["activeEnd"], schedule["end"])
            self.assertEqual(
                [],
                offense.validate_offensive_metadata(
                    metadata,
                    clip_duration_seconds=metadata["clipDurationSeconds"],
                    approved=True,
                    draft=False,
                    available_socket_roles={"MAIN_HAND_R", "MAIN_HAND_L"},
                ),
            )
        self.assertEqual(8, len(identities))

    def test_socket_contract_rejects_duplicates_parent_and_nonfinite_transform(self):
        payload = copy.deepcopy(self.fixture["runtimeAttachmentSockets"])
        payload["sockets"][1]["socketId"] = payload["sockets"][0]["socketId"]
        payload["sockets"][1]["semanticRole"] = payload["sockets"][0]["semanticRole"]
        payload["sockets"][1]["parentRuntimeBone"] = "missing_hand"
        payload["sockets"][1]["localPosition"][0] = float("nan")
        errors = sockets.validate_socket_contract(payload, self.bones)
        self.assertTrue(any("duplicated" in message for message in errors))
        self.assertTrue(any("missing_hand" in message for message in errors))
        self.assertTrue(any("finite 3-vector" in message for message in errors))

    def test_offensive_contract_rejects_draft_overlap_zero_active_and_duration_drift(self):
        metadata = copy.deepcopy(
            self.fixture["runtimeAnimations"]["offensiveActions"][0]
        )
        metadata["phases"]["active"]["endSeconds"] = metadata["phases"]["active"]["startSeconds"]
        metadata["phases"]["recovery"]["startSeconds"] = 0.4
        errors = offense.validate_offensive_metadata(
            metadata,
            clip_duration_seconds=2.0,
            approved=False,
            draft=True,
            available_socket_roles={"MAIN_HAND_L"},
        )
        for marker in (
            "explicitly approved",
            "clipDurationSeconds does not match",
            "ACTIVE interval must have positive duration",
            "contiguous",
            "not authored",
        ):
            self.assertTrue(any(marker in message for message in errors), marker)

    def test_fixture_clip_and_offensive_lists_are_exactly_linked(self):
        runtime = self.fixture["runtimeAnimations"]
        by_name = {record["actionName"]: record for record in runtime["offensiveActions"]}
        self.assertEqual(len(by_name), len(runtime["offensiveActions"]))
        for clip in runtime["clips"]:
            self.assertEqual(clip["offensiveAction"], {
                key: value for key, value in by_name[clip["name"]].items()
                if key != "actionName"
            })


if __name__ == "__main__":
    unittest.main()
