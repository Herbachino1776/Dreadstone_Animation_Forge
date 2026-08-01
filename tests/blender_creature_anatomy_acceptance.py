"""Blender 5.1.2 acceptance for the Creature Anatomy Profile foundation.

The generated quadruped is an architectural fixture, not a production
canonical skeleton and not evidence of visual animation quality.

Run from the repository root:

    blender --background --factory-startup \
      --python tests/blender_creature_anatomy_acceptance.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "anatomy_acceptance"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import animation_library  # noqa: E402
from dreadstone_animation_forge.anatomy import blender_adapter, persistence  # noqa: E402
from dreadstone_animation_forge.anatomy.orientation import orientation_contract  # noqa: E402
from dreadstone_animation_forge.anatomy.profiles import (  # noqa: E402
    QUADRUPED_PROFILE,
    QUADRUPED_PROFILE_ID,
)
from dreadstone_animation_forge.anatomy.validation import validate_mapping  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def activate(obj):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def add_bone(data, name, parent, head, tail, *, deform=True):
    bone = data.edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    bone.use_deform = deform
    if parent:
        bone.parent = data.edit_bones[parent]
    return bone


def make_quadruped(name, *, sign=1.0, missing=""):
    data = bpy.data.armatures.new(name + "_Data")
    armature = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(armature)
    activate(armature)
    bpy.ops.object.mode_set(mode="EDIT")
    specs = [
        ("ground_root", "", (0, 0, 0), (0, 0, 0.2), False),
        ("body_center", "ground_root", (0, 0, 1.05), (0, 0.1 * sign, 1.15), True),
        ("pelvis", "body_center", (0, -0.45 * sign, 1.05), (0, -0.2 * sign, 1.15), True),
        ("spine_01", "pelvis", (0, -0.2 * sign, 1.15), (0, 0.25 * sign, 1.2), True),
        ("spine_02", "spine_01", (0, 0.25 * sign, 1.2), (0, 0.65 * sign, 1.25), True),
        ("chest", "spine_02", (0, 0.65 * sign, 1.25), (0, 0.9 * sign, 1.3), True),
        ("neck_01", "chest", (0, 0.9 * sign, 1.3), (0, 1.2 * sign, 1.45), True),
        ("neck_02", "neck_01", (0, 1.2 * sign, 1.45), (0, 1.5 * sign, 1.55), True),
        ("head", "neck_02", (0, 1.5 * sign, 1.55), (0, 1.85 * sign, 1.55), True),
        ("jaw", "head", (0, 1.55 * sign, 1.45), (0, 1.8 * sign, 1.4), True),
        ("tail_01", "pelvis", (0, -0.45 * sign, 1.1), (0, -0.8 * sign, 1.05), True),
        ("tail_02", "tail_01", (0, -0.8 * sign, 1.05), (0, -1.15 * sign, 0.95), True),
    ]
    for bone_name, parent, head, tail, deform in specs:
        if bone_name != missing:
            add_bone(data, bone_name, parent if parent != missing else "", head, tail, deform=deform)
    for prefix, root_role, joint_role, x, y, parent in (
        ("front_l", "scapula", "carpus", -0.42, 0.72 * sign, "chest"),
        ("front_r", "scapula", "carpus", 0.42, 0.72 * sign, "chest"),
        ("hind_l", "hip", "hock", -0.38, -0.38 * sign, "pelvis"),
        ("hind_r", "hip", "hock", 0.38, -0.38 * sign, "pelvis"),
    ):
        chain = (
            (f"{prefix}_{root_role}", parent, (x, y, 1.23), (x, y, 1.08)),
            (f"{prefix}_upper", f"{prefix}_{root_role}", (x, y, 1.08), (x, y + 0.08 * sign, 0.72)),
            (f"{prefix}_lower", f"{prefix}_upper", (x, y + 0.08 * sign, 0.72), (x, y - 0.02 * sign, 0.38)),
            (f"{prefix}_{joint_role}", f"{prefix}_lower", (x, y - 0.02 * sign, 0.38), (x, y + 0.10 * sign, 0.17)),
            (f"{prefix}_paw", f"{prefix}_{joint_role}", (x, y + 0.10 * sign, 0.17), (x, y + 0.28 * sign, 0.06)),
        )
        for bone_name, parent_name, head, tail in chain:
            if bone_name == missing:
                continue
            add_bone(
                data,
                bone_name,
                parent_name if parent_name != missing else "",
                head,
                tail,
            )
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def make_animate_anything_humanoid():
    data = bpy.data.armatures.new("DSB_Humanoid_Compatibility_Data")
    armature = bpy.data.objects.new("DSB_Humanoid_Compatibility", data)
    bpy.context.collection.objects.link(armature)
    activate(armature)
    bpy.ops.object.mode_set(mode="EDIT")
    specs = (
        ("root", "", (0, 0, 0), (0, 0, 0.2)),
        ("body", "root", (0, 0, 0.8), (0, 0, 1.0)),
        ("body_top0", "body", (0, 0, 1.0), (0, 0, 1.2)),
        ("body_top1", "body_top0", (0, 0, 1.2), (0, 0, 1.4)),
        ("body_top2", "body_top1", (0, 0, 1.4), (0, 0, 1.6)),
        ("neck", "body_top2", (0, 0, 1.6), (0, 0, 1.75)),
        ("head", "neck", (0, 0, 1.75), (0, -0.05, 2.0)),
    )
    for value in specs:
        add_bone(data, *value)
    for side, x in (("left", -0.3), ("right", 0.3)):
        add_bone(data, f"shoulder_{side}", "body_top2", (x * 0.5, 0, 1.55), (x, 0, 1.52))
        add_bone(data, f"arm_{side}_top", f"shoulder_{side}", (x, 0, 1.52), (x * 1.8, 0, 1.3))
        add_bone(data, f"arm_{side}_bot", f"arm_{side}_top", (x * 1.8, 0, 1.3), (x * 2.4, 0, 1.1))
        add_bone(data, f"arm_{side}_hand", f"arm_{side}_bot", (x * 2.4, 0, 1.1), (x * 2.7, 0, 1.05))
        add_bone(data, f"leg_{side}_top", "body", (x, 0, 0.9), (x, 0, 0.55))
        add_bone(data, f"leg_{side}_bot", f"leg_{side}_top", (x, 0, 0.55), (x, 0, 0.18))
        add_bone(data, f"leg_{side}_foot", f"leg_{side}_bot", (x, 0, 0.18), (x, -0.22, 0.08))
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def add_humanoid_family(data):
    bpy.ops.object.mode_set(mode="EDIT")
    values = (
        ("human_root", "", (3, 0, 0), (3, 0, 0.2)),
        ("hips", "human_root", (3, 0, 0.9), (3, 0, 1.05)),
        ("spine", "hips", (3, 0, 1.05), (3, 0, 1.35)),
        ("chest", "spine", (3, 0, 1.35), (3, 0, 1.55)),
        ("neck", "chest", (3, 0, 1.55), (3, 0, 1.7)),
        ("head", "neck", (3, 0, 1.7), (3, -0.05, 1.95)),
    )
    for value in values:
        add_bone(data, *value)
    for side, x in (("l", 2.7), ("r", 3.3)):
        add_bone(data, f"thigh_{side}", "hips", (x, 0, 0.95), (x, 0, 0.55))
        add_bone(data, f"shin_{side}", f"thigh_{side}", (x, 0, 0.55), (x, 0, 0.15))
        add_bone(data, f"foot_{side}", f"shin_{side}", (x, 0, 0.15), (x, -0.2, 0.08))
        add_bone(data, f"upper_arm_{side}", "chest", (x, 0, 1.48), (x + (-0.25 if side == "l" else 0.25), 0, 1.25))
    bpy.ops.object.mode_set(mode="OBJECT")


def rest_fingerprint(armature):
    return {
        bone.name: {
            "parent": bone.parent.name if bone.parent else "",
            "head": tuple(round(float(v), 7) for v in bone.head_local),
            "tail": tuple(round(float(v), 7) for v in bone.tail_local),
            "matrix": tuple(round(float(v), 7) for row in bone.matrix_local for v in row),
            "deform": bool(bone.use_deform),
        }
        for bone in armature.data.bones
    }


def action_fingerprint():
    return {
        action.name: {
            "curves": [
                (
                    curve.data_path,
                    int(curve.array_index),
                    tuple((round(float(point.co.x), 7), round(float(point.co.y), 7)) for point in curve.keyframe_points),
                )
                for curve in animation_library.iter_action_fcurves(action)
            ],
            "properties": sorted((str(key), str(action[key])) for key in action.keys()),
        }
        for action in bpy.data.actions
    }


def new_probe_action(armature):
    action = bpy.data.actions.new("DSB_Anatomy_Analysis_Probe")
    armature.animation_data_create()
    armature.animation_data.action = action
    armature.pose.bones["ground_root"].location = (0.0, 0.0, 0.0)
    armature.pose.bones["ground_root"].keyframe_insert("location", frame=1, group="ground_root")
    action["untouched_probe"] = "analysis-must-not-mutate"
    return action


def analyze(armature, override="AUTO"):
    activate(armature)
    settings = bpy.context.scene.daf_settings
    settings.anatomy_profile_override = override
    return addon.analyze_creature_anatomy(bpy.context)[1]


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    addon.register()
    settings = bpy.context.scene.daf_settings

    quadruped = make_quadruped("DSB_SYNTHETIC_ARCHITECTURAL_QUADRUPED")
    probe = new_probe_action(quadruped)
    before_rest = rest_fingerprint(quadruped)
    before_scale = tuple(quadruped.scale)
    before_actions = action_fingerprint()
    result = analyze(quadruped)
    require(result["profileId"] == QUADRUPED_PROFILE_ID, result)
    require(result["readinessStatus"] == "QUADRUPED_READY", result)
    require(result["orientation"]["forwardAxis"] == "+Y", result["orientation"])
    require(result["orientation"]["upAxis"] == "+Z", result["orientation"])
    contacts = [result["roleMapping"][role] for role in QUADRUPED_PROFILE.contact_roles]
    require(len(set(contacts)) == 4, contacts)
    require(result["roleMapping"]["front_l_upper"] != result["roleMapping"]["hind_l_upper"], result["roleMapping"])
    require(rest_fingerprint(quadruped) == before_rest, "Analysis modified rest bones, names, deform flags, or hierarchy.")
    require(tuple(quadruped.scale) == before_scale, "Analysis modified armature scale.")
    require(action_fingerprint() == before_actions, "Analysis modified an Action or Action metadata.")

    snapshot = blender_adapter.snapshot_armature(quadruped)
    duplicate_mapping = dict(result["roleMapping"])
    duplicate_mapping["front_r_paw"] = duplicate_mapping["front_l_paw"]
    duplicate_orientation = orientation_contract(QUADRUPED_PROFILE, duplicate_mapping, snapshot)
    duplicate_report = validate_mapping(QUADRUPED_PROFILE, duplicate_mapping, snapshot, duplicate_orientation)
    require(not duplicate_report["ready"], "Duplicate paw ownership incorrectly passed validation.")
    require(duplicate_report["status"] == "PROFILE_INCOMPLETE", duplicate_report)

    humanoid = make_animate_anything_humanoid()
    legacy_mapping = addon.map_bones(humanoid, settings)
    humanoid_result = analyze(humanoid, "AUTO")
    require(humanoid_result["profileId"] == "DSB_HUMANOID_V1", humanoid_result)
    require(humanoid_result["readinessStatus"] == "HUMANOID_READY", humanoid_result)
    require(humanoid_result["roleMapping"] == legacy_mapping, {
        "legacy": legacy_mapping,
        "profile": humanoid_result["roleMapping"],
    })
    require(humanoid_result["orientation"]["forwardAxis"] == "-Y", humanoid_result)
    settings.facing = "POS_Y"
    require(
        persistence.load_metadata(humanoid)["orientation"]["forwardAxis"] == "+Y",
        "Changing the legacy humanoid facing control did not refresh authoritative orientation.",
    )
    settings.facing = "NEG_Y"
    require(persistence.load_metadata(humanoid)["orientation"]["forwardAxis"] == "-Y", humanoid_result)

    missing = make_quadruped("DSB_SYNTHETIC_QUAD_MISSING_LIMB", missing="front_l_lower")
    missing_result = analyze(missing, "QUADRUPED_DIGITIGRADE")
    require(missing_result["readinessStatus"] == "MISSING_LIMB_CHAIN", missing_result)

    reversed_rig = make_quadruped("DSB_SYNTHETIC_QUAD_REVERSED", sign=-1.0)
    reversed_result = analyze(reversed_rig, "QUADRUPED_DIGITIGRADE")
    require(reversed_result["readinessStatus"] == "ORIENTATION_AMBIGUOUS", reversed_result)

    explicit_wrong = analyze(missing, "QUADRUPED_DIGITIGRADE")
    require(not explicit_wrong["ready"], "Explicit override waived missing-limb validation.")

    ambiguous = make_quadruped("DSB_SYNTHETIC_AMBIGUOUS")
    activate(ambiguous)
    # Preserve exact aliases for both families so the two top profile scores
    # deliberately tie. Renaming in object mode preserves all parent links.
    ambiguous.data.bones["head"].name = "skull"
    ambiguous.data.bones["chest"].name = "withers"
    ambiguous.data.bones["pelvis"].name = "croup"
    add_humanoid_family(ambiguous.data)
    ambiguous_result = analyze(ambiguous, "AUTO")
    require(ambiguous_result["readinessStatus"] == "PROFILE_AMBIGUOUS", ambiguous_result)
    require(not ambiguous_result["profileId"], ambiguous_result)

    activate(quadruped)
    persisted = persistence.load_metadata(quadruped)
    require(persisted and persisted["mappingDigest"] == result["mappingDigest"], persisted)
    animation_library.mark_approved(probe, quadruped, settings, "OTHER")
    stamped_anatomy = json.loads(str(probe[animation_library.CLIP_ANATOMY_PROFILE_PROPERTY]))
    require(stamped_anatomy["profileId"] == QUADRUPED_PROFILE_ID, stamped_anatomy)
    package = animation_library.export_action_clip(bpy.context, quadruped, probe, str(OUTPUT))
    manifest = json.loads(Path(package["manifestPath"]).read_text(encoding="utf-8"))
    require(manifest["anatomy"]["profileId"] == QUADRUPED_PROFILE_ID, manifest)
    require(not manifest["anatomy"]["legacy"], manifest)

    blend_path = OUTPUT / "synthetic_architectural_quadruped_roundtrip.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    bpy.ops.wm.open_mainfile(filepath=str(blend_path), load_ui=False)
    quadruped = bpy.data.objects["DSB_SYNTHETIC_ARCHITECTURAL_QUADRUPED"]
    reopened = persistence.load_metadata(quadruped)
    require(reopened and reopened["mappingDigest"] == result["mappingDigest"], reopened)
    require(reopened["orientation"]["forwardAxis"] == "+Y", reopened)

    old_probe = bpy.data.actions.get("DSB_Anatomy_Analysis_Probe")
    if quadruped.animation_data:
        quadruped.animation_data.action = None
    if old_probe:
        bpy.data.actions.remove(old_probe)
    imported = animation_library.import_action_clip(bpy.context, quadruped, package["blendPath"])
    imported_action = bpy.data.actions[imported["actions"][0]]
    imported_anatomy = json.loads(str(imported_action[animation_library.CLIP_ANATOMY_PROFILE_PROPERTY]))
    require(imported_anatomy["profileId"] == QUADRUPED_PROFILE_ID, imported_anatomy)
    require(not bool(imported_action[animation_library.CLIP_ANATOMY_LEGACY_PROPERTY]), imported_anatomy)

    report = {
        "status": "PASS",
        "blenderVersion": bpy.app.version_string,
        "fixture": "DSB_SYNTHETIC_ARCHITECTURAL_QUADRUPED",
        "fixtureAuthority": "ARCHITECTURAL_NON_PRODUCTION",
        "profileId": reopened["profileId"],
        "readiness": reopened["readinessStatus"],
        "mappingDigest": reopened["mappingDigest"],
        "contacts": reopened["orientation"]["contactBones"],
        "orientation": reopened["orientation"],
        "humanoidMappingCompatibility": "EXACT",
        "actionPackage": package,
        "failuresProved": [
            "MISSING_LIMB_CHAIN",
            "DUPLICATE_CONTACT_OWNERSHIP",
            "ORIENTATION_AMBIGUOUS",
            "PROFILE_AMBIGUOUS",
            "EXPLICIT_OVERRIDE_NOT_A_WAIVER",
        ],
    }
    report_path = OUTPUT / "creature_anatomy_acceptance.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    addon.unregister()
    require(not hasattr(bpy.types.Scene, "daf_settings"), "Unregister left Scene.daf_settings behind.")
    for class_name in (
        "DAF_OT_analyze_creature_anatomy",
        "DAF_OT_show_anatomy_role_mapping",
        "DAF_OT_clear_anatomy_profile_override",
    ):
        require(not hasattr(bpy.types, class_name), f"Unregister left {class_name} registered.")
    print("CREATURE_ANATOMY_ACCEPTANCE=" + json.dumps(report, sort_keys=True, default=str))


if __name__ == "__main__":
    run()
