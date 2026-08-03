"""Render visual proof frames for the Skin & Bones Y+ humanoid contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402


def arguments():
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-glb", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(values)


def require(condition, message):
    if not condition:
        raise RuntimeError(str(message))


def aim(camera, location, target):
    camera.location = Vector(location)
    camera.rotation_euler = (
        Vector(target) - camera.location
    ).to_track_quat("-Z", "Y").to_euler()


def material(name, color):
    value = bpy.data.materials.new(name)
    value.diffuse_color = (*color, 1.0)
    value.use_nodes = True
    node = value.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1.0)
    node.inputs["Roughness"].default_value = 0.88
    return value


def setup_stage(character_height):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 720
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = 'RGBA'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.world.color = (0.025, 0.03, 0.04)

    bpy.ops.mesh.primitive_plane_add(
        size=max(5.0, character_height * 5.0),
        location=(0.0, 0.0, -0.005),
    )
    floor = bpy.context.active_object
    floor.name = "SBF_YPlus_Proof_Floor"
    floor.data.materials.append(material("SBF Proof Floor", (0.075, 0.085, 0.095)))

    camera_data = bpy.data.cameras.new("SBF_YPlus_Proof_Camera_Data")
    camera = bpy.data.objects.new("SBF_YPlus_Proof_Camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.lens = 58

    for name, energy, size, location, color in (
        ("Key", 1100.0, 3.0, (2.8, -2.4, 4.0), (1.0, 0.82, 0.68)),
        ("Fill", 850.0, 2.5, (-2.5, 1.8, 2.7), (0.48, 0.68, 1.0)),
        ("Rim", 700.0, 2.0, (0.0, 3.4, 3.1), (0.75, 0.88, 1.0)),
    ):
        light_data = bpy.data.lights.new("SBF Proof " + name, 'AREA')
        light_data.energy = energy
        light_data.shape = 'DISK'
        light_data.size = size
        light_data.color = color
        light = bpy.data.objects.new(light_data.name, light_data)
        light.location = location
        scene.collection.objects.link(light)
    return camera


def render(scene, camera, meshes, output_dir, name, character_height, *, prone=False):
    minimum, maximum = addon.world_bounds(bpy.context, meshes)
    center = (minimum + maximum) * 0.5
    extent = max(
        float(maximum.x - minimum.x),
        float(maximum.y - minimum.y),
        float(maximum.z - minimum.z),
        character_height * 0.45,
    )
    if prone:
        aim(
            camera,
            center + Vector((extent * 1.6, -extent * 1.6, extent * 1.05)),
            center,
        )
        camera.data.lens = 58
    else:
        aim(
            camera,
            center + Vector((extent * 1.8, -extent * 1.7, extent * 0.68)),
            center,
        )
        camera.data.lens = 58
    path = output_dir / f"sbf_yplus_{name}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return str(path)


def main():
    args = arguments()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.source_glb).resolve()))
    addon.register()
    armature = max(
        (obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE'),
        key=lambda obj: len(obj.data.bones),
    )
    bpy.ops.object.select_all(action='DESELECT')
    armature.select_set(True)
    for child in armature.children_recursive:
        child.select_set(True)
    bpy.context.view_layer.objects.active = armature
    require("FINISHED" in bpy.ops.daf.analyze(), "Canonical analysis failed.")
    meshes = [obj for obj in armature.children_recursive if obj.type == 'MESH']
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj not in meshes:
            obj.hide_render = True
    minimum, maximum = addon.world_bounds(bpy.context, meshes)
    height = float(maximum.z - minimum.z)
    camera = setup_stage(height)
    scene = bpy.context.scene
    results = {}
    bpy.ops.object.select_all(action='DESELECT')
    armature.select_set(True)
    for child in armature.children_recursive:
        child.select_set(True)
    bpy.context.view_layer.objects.active = armature

    require("FINISHED" in bpy.ops.daf.idle(), "Idle generation failed.")
    scene.frame_set(scene.frame_start + round((scene.frame_end - scene.frame_start) * 0.25))
    results["idle"] = render(scene, camera, meshes, output_dir, "idle_breathe", height)

    require("FINISHED" in bpy.ops.daf.walk(), "Walk generation failed.")
    scene.frame_set(scene.frame_start + round((scene.frame_end - scene.frame_start) * 0.25))
    results["walk"] = render(scene, camera, meshes, output_dir, "walk_passing", height)

    scene.daf_settings.collapse_style = "FACEPLANT"
    require("FINISHED" in bpy.ops.daf.collapse(), "Death generation failed.")
    scene.frame_set(scene.frame_end)
    results["death"] = render(
        scene,
        camera,
        meshes,
        output_dir,
        "death_terminal",
        height,
        prone=True,
    )
    report_path = output_dir / "sbf_yplus_visual_proof.json"
    report_path.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("SBF_YPLUS_VISUAL_PROOF=" + json.dumps(results, sort_keys=True))


if __name__ == "__main__":
    main()
