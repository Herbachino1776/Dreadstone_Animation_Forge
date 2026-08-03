"""Blender acceptance for grounded death and wrapperless animation-pack export.

Run:
    blender --background --factory-startup \
      --python tests/blender_animation_grounding_pack_acceptance.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import animation_library  # noqa: E402
from dreadstone_animation_forge.anatomy import skin_and_bones  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def make_character():
    armature_data = bpy.data.armatures.new("Native_Rig_Data")
    armature = bpy.data.objects.new("Native_Rig", armature_data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    hierarchy = {
        "root": "", "body": "root", "body_top0": "body",
        "body_top1": "body_top0", "body_top2": "body_top1",
        "neck": "body_top2", "head": "neck",
        "shoulder_left": "body_top2", "arm_left_top": "shoulder_left",
        "arm_left_bot": "arm_left_top", "arm_left_hand": "arm_left_bot",
        "shoulder_right": "body_top2", "arm_right_top": "shoulder_right",
        "arm_right_bot": "arm_right_top", "arm_right_hand": "arm_right_bot",
        "leg_left_top": "body", "leg_left_bot": "leg_left_top",
        "leg_left_foot": "leg_left_bot", "leg_right_top": "body",
        "leg_right_bot": "leg_right_top", "leg_right_foot": "leg_right_bot",
    }
    created = {}
    for index, (name, parent_name) in enumerate(hierarchy.items()):
        bone = armature_data.edit_bones.new(name)
        x = ((index % 5) - 2) * 0.015
        bone.head = (x, 0.0, 0.70)
        bone.tail = (x, 0.0, 0.90)
        bone.parent = created.get(parent_name)
        created[name] = bone
    bpy.ops.object.mode_set(mode="OBJECT")

    vertices = [
        (-0.20, -0.10, 0.00),
        (0.20, -0.10, 0.00),
        (0.20, 0.10, 0.00),
        (-0.20, 0.10, 0.00),
        (-0.20, -0.10, 1.50),
        (0.20, -0.10, 1.50),
        (0.20, 0.10, 1.50),
        (-0.20, 0.10, 1.50),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (4, 0, 3, 7),
    ]
    mesh_data = bpy.data.meshes.new("Native_Character_Mesh")
    mesh_data.from_pydata(vertices, [], faces)
    mesh_data.update()
    mesh = bpy.data.objects.new("Native_Character", mesh_data)
    bpy.context.collection.objects.link(mesh)
    for role in ("hips", "spine", "spine_mid", "chest"):
        group = mesh.vertex_groups.new(
            name=skin_and_bones.CANONICAL_HUMANOID_MAPPING[role]
        )
        group.add(
            list(range(len(vertices))),
            1.0 if role == "hips" else 0.25,
            "REPLACE",
        )
    modifier = mesh.modifiers.new("Native_Armature", "ARMATURE")
    modifier.object = armature

    sbf_mapping = {
        sbf_role: skin_and_bones.CANONICAL_HUMANOID_MAPPING[forge_role]
        for sbf_role, forge_role in skin_and_bones.SBF_TO_FORGE_ROLE.items()
    }
    armature["sbf_canonical_rig_version"] = skin_and_bones.SBF_CANONICAL_RIG_VERSION
    armature["sbf_forward_axis"] = "+Y"
    armature["sbf_up_axis"] = "+Z"
    armature["sbf_root_bone"] = "root"
    armature["sbf_orientation_revision"] = 1
    armature["sbf_orientation_state"] = "CANONICAL_Y_PLUS"
    armature["sbf_rig_contract_version"] = 1
    armature["sbf_unit_scale_meters"] = 1.0
    armature["sbf_bone_mapping"] = json.dumps(sbf_mapping)

    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = armature
    return armature, mesh


def minimum_z(mesh):
    minimum, _maximum = addon.world_bounds(bpy.context, [mesh])
    return float(minimum.z)


def main():
    addon.register()
    armature, mesh = make_character()
    settings = bpy.context.scene.daf_settings
    bpy.ops.daf.analyze()
    settings.ground_sink = 0.005
    settings.death_instant_seconds = 0.72
    death_results = {}
    for style in ("CHEST_HOLD", "FACEPLANT", "KNEES_FIRST", "INSTANT_LIMP"):
        settings.collapse_style = style
        collapse_result = bpy.ops.daf.collapse()
        require(
            "FINISHED" in collapse_result,
            f"{style} death generation failed: {sorted(collapse_result)}",
        )
        death = bpy.data.actions.get(addon.DRAFT_ACTION_NAMES["DEATH"])
        require(death is not None, f"{style} death draft was not created.")
        require(
            bool(death.get("dsb_floor_grounded", False)),
            f"{style} death has no baked floor-grounding metadata.",
        )
        require(
            bool(death.get("dsb_terminal_contact_baked", False)),
            f"{style} death has no terminal body-contact metadata.",
        )
        start, end = addon.action_frame_bounds(death)
        worst_minimum = float("inf")
        for frame in range(int(start), int(end) + 1):
            bpy.context.scene.frame_set(frame)
            worst_minimum = min(worst_minimum, minimum_z(mesh))
        require(
            worst_minimum >= -settings.ground_sink - 0.0011,
            f"{style} death penetrated the floor: {worst_minimum:.6f} m.",
        )
        bpy.context.scene.frame_set(int(end))
        final_minimum, final_maximum = addon.world_bounds(bpy.context, [mesh])
        final_height = float(final_maximum.z - final_minimum.z)
        reference_height = float(death["dsb_terminal_reference_height_m"])
        final_ratio = final_height / reference_height
        maximum_ratio = float(death["dsb_terminal_max_height_ratio"])
        require(
            abs(float(final_minimum.z) + settings.ground_sink) <= 0.0011,
            f"{style} death does not end flush: {float(final_minimum.z):.6f} m.",
        )
        require(
            final_ratio <= maximum_ratio + 0.0001,
            f"{style} death remains upright: {final_ratio:.6f} > {maximum_ratio:.6f}.",
        )
        validation = addon.validate_death_floor_action(
            bpy.context,
            death,
            armature,
            [mesh],
            fallback_ground_sink=settings.ground_sink,
        )
        require(
            validation["status"] == "PASS",
            f"{style} terminal validation failed: {validation['errors']}",
        )
        if style == "INSTANT_LIMP":
            terminal_frame = int(death["dsb_terminal_contact_frame"])
            instant_motion_frames = terminal_frame - int(start)
            require(
                instant_motion_frames <= round(settings.death_instant_seconds * 24) + 1,
                f"Instant collapse is too slow: {instant_motion_frames} frames.",
            )
        death_results[style] = {
            "minimumZ": worst_minimum,
            "terminalHeightRatio": final_ratio,
            "terminalTorsoHeightRatio": validation["terminalTorsoHeightRatio"],
            "groundCarrierBone": validation["groundCarrierBone"],
            "torsoRegions": sorted(validation["terminalTorsoRegions"]),
            "terminalFrame": int(death["dsb_terminal_contact_frame"]),
        }

    walk_result = bpy.ops.daf.walk()
    require(
        "FINISHED" in walk_result,
        f"Walk generation failed: {sorted(walk_result)}",
    )
    walk = bpy.data.actions.get(addon.DRAFT_ACTION_NAMES["WALK"])
    require(walk is not None, "Walk draft was not created.")
    walk.name = "DSB_Walk_Approved_Native_Rig"
    animation_library.mark_approved(
        walk,
        armature,
        settings,
        "WALK",
    )

    # Prove the armature-only selection can discover a sibling skinned mesh and
    # does not create or require a DSB safe-size wrapper.
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    require(
        not any(
            bool(obj.get("dsb_safe_size_wrapper", False))
            for obj in bpy.context.scene.objects
        ),
        "Fixture unexpectedly contains a safe-size wrapper.",
    )

    with tempfile.TemporaryDirectory(
        prefix="daf_wrapperless_pack_"
    ) as output_directory:
        settings.pack_output_directory = output_directory
        settings.pack_filename = "native_rig_animation_pack"
        settings.pack_auto_increment = False
        settings.pack_force_sampling = True
        build_result = bpy.ops.daf.build_approved_pack()
        require(
            "FINISHED" in build_result,
            f"Wrapperless pack build failed: {sorted(build_result)}",
        )
        glb_path = Path(output_directory) / "native_rig_animation_pack.glb"
        manifest_path = glb_path.with_suffix(".json")
        require(glb_path.is_file(), "Wrapperless pack GLB was not written.")
        require(
            manifest_path.is_file(),
            "Wrapperless pack manifest was not written.",
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        character = manifest["character"]
        require(
            character["sizing_mode"] == "NATIVE_RIG",
            f"Unexpected sizing mode: {character['sizing_mode']}",
        )
        require(
            character["wrapper_name"] is None,
            "Native-rig manifest unexpectedly names a wrapper.",
        )
        require(
            character["armature_name"] == armature.name,
            "Native-rig manifest names the wrong armature.",
        )

    print(
        "ANIMATION_GROUNDING_PACK_ACCEPTANCE="
        + json.dumps(
            {
                "status": "PASS",
                "deathStyles": death_results,
                "groundSinkM": settings.ground_sink,
                "wrapperlessPack": True,
                "approvedWalk": walk.name,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
