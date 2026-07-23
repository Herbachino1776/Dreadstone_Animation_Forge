"""Blender 5.1 acceptance for organic textured multilayer gore generation.

Run from the repository root:

    blender --background --factory-startup --python tests/blender_gore_v3_acceptance.py
"""

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
from dreadstone_animation_forge import deformation_authoring, trauma_field  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def arguments():
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", default="")
    return parser.parse_args(raw)


def aim_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def grid_surface(width=8, height=8):
    vertices = [(x * 0.01, y * 0.01, 0.0) for y in range(height) for x in range(width)]
    faces = []
    for y in range(height - 1):
        for x in range(width - 1):
            first = y * width + x
            faces.append((first, first + 1, first + width + 1, first + width))
    center_x = (width - 1) * 0.5
    center_y = (height - 1) * 0.5
    weights = []
    for y in range(height):
        for x in range(width):
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            weights.append(max(0.0, 1.0 - distance / (width * 0.58)))
    return vertices, faces, weights


def main():
    args = arguments()
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    vertices, faces, weights = grid_surface()
    mesh = bpy.data.meshes.new("DSB_GORE_V3_FIXTURE_SOURCE_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    source = bpy.data.objects.new("DSB_GORE_V3_FIXTURE_SOURCE", mesh)
    bpy.context.scene.collection.objects.link(source)
    source.shape_key_add(name="Basis")
    key_name = "Fixture_Impact"
    key = source.shape_key_add(name=key_name)
    for index, point in enumerate(key.data):
        point.co.z -= weights[index] * 0.008

    overlay = trauma_field.default_gore_overlay(
        "Gore_Crush_Heavy_Clotted",
        enabled=True,
        region_id="fixture",
        linked_stamp_id="fixture_stamp",
        selection_hash="fixture_capture",
        topology_fingerprint="f" * 64,
        seed=734921,
    )
    deformed = [tuple(point.co) for point in key.data]
    displacement = [abs(deformed[index][2] - vertices[index][2]) for index in range(len(vertices))]
    records = trauma_field.raised_gore_face_records(
        deformed,
        faces,
        weights,
        displacement,
        overlay,
    )
    require(records, "Fixture produced no raised-gore face records.")
    gore = deformation_authoring._build_gore_shell_object(
        source,
        key_name,
        "fixture",
        "CORE",
        overlay,
        records,
    )
    errors = deformation_authoring._raised_gore_mesh_errors(
        gore, source, key_name, overlay, "CORE"
    )
    require(not errors, "Runtime gore validation failed: " + "; ".join(errors))
    gore.data.calc_loop_triangles()
    triangle_count = len(gore.data.loop_triangles)
    require(triangle_count <= int(overlay["goreMaximumTriangles"]), "Triangle budget was exceeded.")
    require(gore.data.uv_layers.active is not None, "Fiber atlas UV map is missing.")
    variants = gore.data.attributes["DSB_Gore_Texture_Variant"]
    variant_values = {int(record.value) for record in variants.data}
    require(len(variant_values) >= 3, "Master seed did not distribute multiple fiber directions.")
    layers = gore.data.attributes["DSB_Gore_Layer"]
    layer_values = {int(record.value) for record in layers.data}
    require(2 in layer_values, "Compromised inner-reddening layer is missing.")
    for material in gore.data.materials:
        textures = [
            node for node in material.node_tree.nodes
            if node.bl_idname == 'ShaderNodeTexImage' and node.image is not None
        ]
        require(len(textures) == 1, f"{material.name} does not use exactly one composed gore texture.")
        image = textures[0].image
        require(image.get("dsb_gore_composed_texture", False), "Additive composed texture metadata is missing.")
        require(image.packed_file is not None, "Composed gore texture is not packed for export.")
        require(
            abs(float(image.get("dsb_gore_fiber_texture_strength", -1.0)) - float(overlay["goreFiberTextureStrength"])) < 1e-8,
            "Fiber contribution metadata is stale.",
        )
        require(
            abs(float(image.get("dsb_gore_base_color_strength", -1.0)) - float(overlay["goreBaseColorStrength"])) < 1e-8,
            "Gore-color contribution metadata is stale.",
        )

    report = {
        "status": "PASS",
        "recordCount": len(records),
        "triangleCount": triangle_count,
        "materialCount": len(gore.data.materials),
        "fiberDirectionsUsed": sorted(variant_values),
        "layersUsed": sorted(layer_values),
        "shellQuality": gore["dsb_gore_shell_quality"],
        "textureAtlas": str(deformation_authoring.GORE_TEXTURE_ATLAS_PATH),
    }
    if args.render:
        render_path = Path(args.render).resolve()
        render_path.parent.mkdir(parents=True, exist_ok=True)
        key.value = 1.0
        gore.hide_render = False
        gore.hide_set(False)
        source.hide_render = False
        source.hide_set(False)
        skin = bpy.data.materials.new("Fixture Skin")
        skin.diffuse_color = (0.20, 0.055, 0.032, 1.0)
        skin.use_nodes = True
        skin.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = skin.diffuse_color
        skin.node_tree.nodes.get("Principled BSDF").inputs["Roughness"].default_value = 0.78
        source.data.materials.append(skin)
        camera_data = bpy.data.cameras.new("Gore Acceptance Camera")
        camera = bpy.data.objects.new("Gore Acceptance Camera", camera_data)
        bpy.context.scene.collection.objects.link(camera)
        camera.location = (0.035, -0.105, 0.092)
        camera_data.lens = 58
        aim_at(camera, (0.035, 0.035, -0.002))
        bpy.context.scene.camera = camera
        for name, location, energy, size in (
            ("Key", (-0.04, -0.03, 0.13), 2.4, 0.09),
            ("Fill", (0.12, 0.04, 0.08), 0.8, 0.07),
        ):
            light_data = bpy.data.lights.new(name, 'AREA')
            light_data.energy = energy
            light_data.shape = 'DISK'
            light_data.size = size
            light = bpy.data.objects.new(name, light_data)
            bpy.context.scene.collection.objects.link(light)
            light.location = location
            aim_at(light, (0.035, 0.035, 0.0))
        scene = bpy.context.scene
        scene.render.engine = 'BLENDER_EEVEE'
        scene.render.resolution_x = 720
        scene.render.resolution_y = 720
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = str(render_path)
        scene.world.use_nodes = True
        background = scene.world.node_tree.nodes.get("Background")
        background.inputs["Color"].default_value = (0.004, 0.004, 0.004, 1.0)
        background.inputs["Strength"].default_value = 0.08
        scene.view_settings.look = 'AgX - Medium High Contrast'
        scene.view_settings.exposure = -1.0
        bpy.ops.render.render(write_still=True)
        report["render"] = str(render_path)
    print("GORE_V3_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
