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

    bone_names = sorted(set(addon.ANIMATE_ANYTHING_PROFILE.values()))
    for index, name in enumerate(bone_names):
        bone = armature_data.edit_bones.new(name)
        x = ((index % 5) - 2) * 0.015
        bone.head = (x, 0.0, 0.70)
        bone.tail = (x, 0.0, 0.90)
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
    group = mesh.vertex_groups.new(
        name=addon.ANIMATE_ANYTHING_PROFILE["hips"]
    )
    group.add(list(range(len(vertices))), 1.0, "REPLACE")
    modifier = mesh.modifiers.new("Native_Armature", "ARMATURE")
    modifier.object = armature

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
    settings.ground_sink = 0.005

    collapse_result = bpy.ops.daf.collapse()
    require(
        "FINISHED" in collapse_result,
        f"Death generation failed: {sorted(collapse_result)}",
    )
    death = bpy.data.actions.get(addon.DRAFT_ACTION_NAMES["DEATH"])
    require(death is not None, "Death draft was not created.")
    require(
        bool(death.get("dsb_floor_grounded", False)),
        "Death draft has no baked floor-grounding metadata.",
    )
    start, end = addon.action_frame_bounds(death)
    worst_minimum = float("inf")
    for frame in range(int(start), int(end) + 1):
        bpy.context.scene.frame_set(frame)
        worst_minimum = min(worst_minimum, minimum_z(mesh))
    require(
        worst_minimum >= -settings.ground_sink - 0.0011,
        f"Grounded death penetrated the floor: {worst_minimum:.6f} m.",
    )

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
                "deathMinimumZ": worst_minimum,
                "groundSinkM": settings.ground_sink,
                "wrapperlessPack": True,
                "approvedWalk": walk.name,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
