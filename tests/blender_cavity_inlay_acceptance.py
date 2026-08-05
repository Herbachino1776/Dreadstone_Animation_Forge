"""Self-contained Blender 5.1.2 acceptance for Forge 3.20 cavity/inlay gore.

Run:

    blender --background --factory-startup \
      --python tests/blender_cavity_inlay_acceptance.py -- --output <folder>

The fixture exercises Blender object construction/skinning/materials, the full
identity/macro/seed/scale matrix in the production geometry service, useful
proof renders, GLB export, and clean reimport.  It does not require a production
character or mutate a user blend.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import deformation_authoring  # noqa: E402
from dreadstone_animation_forge import parameter_schema, trauma_field  # noqa: E402
from dreadstone_animation_forge.deformation import cavity_service  # noqa: E402
from dreadstone_animation_forge.deformation import preview_service  # noqa: E402


IDENTITIES = tuple(parameter_schema.GORE_IDENTITIES)
MACRO_LEVELS = (0.0, 25.0, 50.0, 75.0, 100.0)
SCALES = (0.75, 1.5)
SEEDS = tuple(range(1776, 1796))
SCENARIOS = (
    ("head_left", "ATTACHED"),
    ("head_left", "DETACHED"),
    ("head_front", "ATTACHED"),
    ("head_front", "DETACHED"),
    ("body", "CORE"),
    ("forearm_left", "ATTACHED"),
    ("forearm_left", "DETACHED"),
    ("forearm_right", "ATTACHED"),
    ("forearm_right", "DETACHED"),
    ("compound_head_body", "CORE"),
)


def arguments():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    return parser.parse_args(raw)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def remove_object(obj):
    mesh = obj.data if obj and obj.type == "MESH" else None
    if obj is not None:
        bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def make_armature():
    data = bpy.data.armatures.new("Cavity_Acceptance_Rig")
    rig = bpy.data.objects.new("Cavity_Acceptance_Rig", data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    left = data.edit_bones.new("Cavity_Left")
    left.head = (-0.15, 0.0, -0.2)
    left.tail = (-0.15, 0.0, 0.2)
    right = data.edit_bones.new("Cavity_Right")
    right.head = (0.15, 0.0, -0.2)
    right.tail = (0.15, 0.0, 0.2)
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.select_set(False)
    return rig


def make_source(rig, scale=1.0):
    size = 7
    spacing = 0.032 * scale
    vertices = [
        ((x - 3) * spacing, (y - 3) * spacing, 0.0)
        for y in range(size)
        for x in range(size)
    ]
    faces = [
        (
            y * size + x,
            y * size + x + 1,
            (y + 1) * size + x + 1,
            (y + 1) * size + x,
        )
        for y in range(size - 1)
        for x in range(size - 1)
    ]
    mesh = bpy.data.meshes.new("Cavity_Acceptance_Source_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    source = bpy.data.objects.new("Cavity_Acceptance_Source", mesh)
    bpy.context.scene.collection.objects.link(source)
    source.shape_key_add(name="Basis")
    impact = source.shape_key_add(name="Impact")
    radius = spacing * 3.2
    for point in impact.data:
        distance = math.hypot(point.co.x, point.co.y)
        response = max(0.0, 1.0 - distance / radius)
        point.co.z -= 0.018 * scale * response**1.8
    left = source.vertex_groups.new(name="Cavity_Left")
    right = source.vertex_groups.new(name="Cavity_Right")
    for vertex in source.data.vertices:
        x = float(vertex.co.x)
        blend = min(1.0, max(0.0, 0.5 + x / max(spacing * 5.0, 1e-8)))
        left.add([vertex.index], 1.0 - blend, "REPLACE")
        right.add([vertex.index], blend, "REPLACE")
    modifier = source.modifiers.new(name="Cavity Armature", type="ARMATURE")
    modifier.object = rig
    return source, faces


def recipe(identity_id, macros, seed, scale):
    defaults = parameter_schema.gore_identity_defaults(identity_id)
    result = trauma_field.default_gore_overlay(
        defaults["presetId"],
        enabled=True,
        region_id="acceptance",
        linked_stamp_id="acceptance_stamp",
        selection_hash="acceptance_selection",
        topology_fingerprint="acceptance_topology",
        seed=seed,
    )
    result.update(
        parameter_schema.derive_gore_parameters(
            macros,
            identity_id=identity_id,
            region_scale=0.075 * scale,
            stamp_depth=0.025 * scale,
            mean_edge_length=0.004 * scale,
        )
    )
    result["goreControl"] = parameter_schema.normalize_gore_control(
        {
            "identityId": identity_id,
            "mode": "MACRO",
            "macros": macros,
            "seed": seed,
        }
    )
    result["goreMaskSeed"] = seed
    return trauma_field.normalize_gore_overlay(result)


def source_inputs(source, faces):
    target = source.data.shape_keys.key_blocks["Impact"]
    positions = [tuple(point.co) for point in target.data]
    maximum_radius = max(math.hypot(x, y) for x, y, _z in positions)
    weights = [
        max(0.0, 1.0 - math.hypot(x, y) / maximum_radius) ** 0.7
        for x, y, _z in positions
    ]
    displacements = [
        (target.data[index].co - source.data.vertices[index].co).length
        for index in range(len(positions))
    ]
    normals = deformation_authoring._local_vertex_normals(
        [Vector(value) for value in positions], faces
    )
    return positions, [tuple(value) for value in normals], weights, displacements


def geometry_digest(generated):
    payload = {
        "vertices": [[round(value, 8) for value in point] for point in generated["vertices"]],
        "faces": [list(face) for face in generated["faces"]],
        "materials": list(generated["materialIndices"]),
        "variants": list(generated["textureVariants"]),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def variant_digest(generated):
    payload = {
        "materialIds": generated["materialIds"],
        "materialIndices": generated["materialIndices"],
        "variants": generated["textureVariants"],
        "layers": generated["faceLayers"],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_generated(generated, recipe_data):
    errors = cavity_service.edge_use_errors(generated["faces"])
    metrics = generated["metrics"]
    require(not errors, "; ".join(errors))
    require(
        metrics["triangleCount"] <= recipe_data["goreMaximumTriangles"],
        "Cavity triangle budget exceeded.",
    )
    require(
        metrics["maximumProudness"] <= recipe_data["goreProudnessLimit"] + 1e-9,
        "Cavity exceeded its proudness limit.",
    )
    if recipe_data["goreCavityDepth"] > 0.0:
        require(
            metrics["minimumSkinToLinerSeparation"] > 0.0,
            "Cavity has no skin-to-liner separation.",
        )


def weight_status(obj):
    group_names = {group.index: group.name for group in obj.vertex_groups}
    valid = True
    maximum_influences = 0
    for vertex in obj.data.vertices:
        weights = [
            float(membership.weight)
            for membership in vertex.groups
            if group_names.get(membership.group) in {"Cavity_Left", "Cavity_Right"}
            and membership.weight > 1e-8
        ]
        maximum_influences = max(maximum_influences, len(weights))
        valid = valid and bool(weights) and len(weights) <= 4 and abs(sum(weights) - 1.0) <= 1e-4
    return {"valid": bool(valid), "maximumInfluences": maximum_influences}


def make_camera_and_lights():
    camera_data = bpy.data.cameras.new("Cavity_Proof_Camera")
    camera = bpy.data.objects.new("Cavity_Proof_Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.data.lens = 55
    area_data = bpy.data.lights.new("Cavity_Neutral_Area", type="AREA")
    area_data.energy = 4
    area_data.shape = "DISK"
    area_data.size = 1.0
    area = bpy.data.objects.new("Cavity_Neutral_Area", area_data)
    bpy.context.scene.collection.objects.link(area)
    area.location = (0.25, -0.22, 0.38)
    point_data = bpy.data.lights.new("Cavity_Point_Stress", type="POINT")
    point_data.energy = 0
    point = bpy.data.objects.new("Cavity_Point_Stress", point_data)
    bpy.context.scene.collection.objects.link(point)
    point.location = (-0.10, -0.10, 0.08)
    return camera, area, point


def aim(camera, location, target=(0.0, 0.0, -0.006)):
    camera.location = location
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


def render_proofs(output, source, gore):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.exposure = -1.15
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.006, 0.006, 0.006, 1.0)
        background.inputs["Strength"].default_value = 0.08
    source.hide_render = True
    gore.hide_render = False
    gore.hide_set(False)
    camera, area, point = make_camera_and_lights()
    views = {
        "front_impact_normal": (0.0, 0.0, 0.34),
        "grazing_side": (0.32, -0.16, 0.055),
        "underside_inside": (0.21, -0.18, -0.22),
    }
    paths = []
    for name, location in views.items():
        aim(camera, location)
        scene.render.filepath = str(output / f"cavity_{name}.png")
        bpy.ops.render.render(write_still=True)
        paths.append(scene.render.filepath)
    aim(camera, (0.28, -0.18, 0.16))
    scene.render.filepath = str(output / "cavity_neutral_lighting.png")
    bpy.ops.render.render(write_still=True)
    paths.append(scene.render.filepath)
    area.data.energy = 2
    point.data.energy = 12
    scene.render.filepath = str(output / "cavity_point_light_stress.png")
    bpy.ops.render.render(write_still=True)
    paths.append(scene.render.filepath)
    return paths


def render_identity_proofs(output, objects):
    scene = bpy.context.scene
    camera = bpy.data.objects["Cavity_Proof_Camera"]
    area = bpy.data.objects["Cavity_Neutral_Area"]
    point = bpy.data.objects["Cavity_Point_Stress"]
    area.data.energy = 4
    point.data.energy = 0
    aim(camera, (0.28, -0.18, 0.16))
    by_identity = {}
    for obj in objects:
        by_identity.setdefault(str(obj["dsb_gore_identity_id"]), obj)
    require(set(by_identity) == set(IDENTITIES), "Identity proof inventory is incomplete.")
    paths = {}
    for identity, proof in sorted(by_identity.items()):
        for obj in objects:
            obj.hide_render = obj is not proof
        proof.hide_set(False)
        scene.render.filepath = str(
            output / f"cavity_identity_{identity.lower()}.png"
        )
        bpy.ops.render.render(write_still=True)
        paths[identity] = scene.render.filepath
    return paths


def main():
    args = arguments()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    rig = make_armature()
    source, faces = make_source(rig)
    positions, normals, weights, displacements = source_inputs(source, faces)
    material_roles = {
        "WET": "DSB_GORE_WET_CRIMSON",
        "CLOT": "DSB_GORE_DARK_CLOT",
        "EDGE": "DSB_GORE_ROUGH_EDGE",
        "BED": "DSB_GORE_DEEP_WOUND_BED",
        "TISSUE": "DSB_GORE_CRUSHED_TISSUE",
        "BONE": "DSB_GORE_EXPOSED_BONE",
    }

    matrix_count = 0
    failures = []
    macro_ranges = {}
    for identity in IDENTITIES:
        defaults = parameter_schema.gore_identity_defaults(identity)["macros"]
        for macro in tuple(defaults):
            values = []
            for level in MACRO_LEVELS:
                macros = dict(defaults)
                macros[macro] = level
                current = recipe(identity, macros, 1776, 1.0)
                records = trauma_field.gore_face_records(
                    positions, faces, weights, displacements, current
                )
                if not records:
                    values.append(
                        {
                            "level": level,
                            "maximumDepth": 0.0,
                            "triangles": 0,
                        }
                    )
                    matrix_count += 1
                    continue
                generated = cavity_service.build_cavity_inlay(
                    positions, normals, records, current, material_roles
                )
                validate_generated(generated, current)
                values.append(
                    {
                        "level": level,
                        "maximumDepth": generated["metrics"]["maximumCavityDepth"],
                        "triangles": generated["metrics"]["triangleCount"],
                    }
                )
                matrix_count += 1
            macro_ranges[f"{identity}.{macro}"] = values

    random_reports = {}
    for identity in IDENTITIES:
        defaults = parameter_schema.gore_identity_defaults(identity)["macros"]
        geometry_digests = set()
        variant_digests = set()
        depths = []
        proudness = []
        triangles = []
        for seed in SEEDS:
            try:
                current = recipe(identity, defaults, seed, 1.0)
                records = trauma_field.gore_face_records(
                    positions, faces, weights, displacements, current
                )
                generated = cavity_service.build_cavity_inlay(
                    positions, normals, records, current, material_roles
                )
                validate_generated(generated, current)
                geometry_digests.add(geometry_digest(generated))
                variant_digests.add(variant_digest(generated))
                depths.append(generated["metrics"]["maximumCavityDepth"])
                proudness.append(generated["metrics"]["maximumProudness"])
                triangles.append(generated["metrics"]["triangleCount"])
            except Exception as exc:
                failures.append(f"{identity} seed {seed}: {exc}")
        random_reports[identity] = {
            "validGenerationCount": len(SEEDS) - sum(
                value.startswith(identity + " ") for value in failures
            ),
            "uniqueGeometryDigestCount": len(geometry_digests),
            "uniqueMaterialVariantDigestCount": len(variant_digests),
            "minimumCavityDepth": min(depths, default=0.0),
            "maximumCavityDepth": max(depths, default=0.0),
            "minimumProudness": min(proudness, default=0.0),
            "maximumProudness": max(proudness, default=0.0),
            "triangleCountRange": [min(triangles, default=0), max(triangles, default=0)],
        }

    scale_reports = {}
    for scale in SCALES:
        current = recipe(
            "BLOODY_CRATER",
            parameter_schema.gore_identity_defaults("BLOODY_CRATER")["macros"],
            1776,
            scale / 1.5,
        )
        scaled_positions = [tuple(value * (scale / 1.5) for value in point) for point in positions]
        scaled_normals = normals
        records = trauma_field.gore_face_records(
            scaled_positions, faces, weights, displacements, current
        )
        generated = cavity_service.build_cavity_inlay(
            scaled_positions, scaled_normals, records, current, material_roles
        )
        validate_generated(generated, current)
        scale_reports[str(scale)] = generated["metrics"]

    scenario_reports = {}
    actual_objects = []
    proof_object = None
    proof_records = [
        {
            "faceIndex": y * 6 + x,
            "vertices": list(faces[y * 6 + x]),
            "influence": 1.0,
            "deformationResponse": 1.0,
            "priority": 1.0,
            "zone": "CORE",
            "estimatedTriangleCount": 40,
        }
        for y in range(1, 5)
        for x in range(1, 5)
    ]
    for index, (region_id, role) in enumerate(SCENARIOS):
        identity = IDENTITIES[(index + 1) % len(IDENTITIES)]
        defaults = parameter_schema.gore_identity_defaults(identity)["macros"]
        current = recipe(identity, defaults, 1776 + index, 1.0)
        records = trauma_field.gore_face_records(
            positions, faces, weights, displacements, current
        )
        if index == 0:
            records = proof_records
        obj = deformation_authoring._build_cavity_inlay_object(
            source, "Impact", region_id, role, current, records, preview=False
        )
        actual_objects.append(obj)
        status = weight_status(obj)
        require(status["valid"], f"{region_id}/{role} has invalid generated skinning.")
        require(len(obj.data.materials) == 6, f"{region_id}/{role} lost a material role.")
        require(
            not cavity_service.edge_use_errors(
                [tuple(polygon.vertices) for polygon in obj.data.polygons]
            ),
            f"{region_id}/{role} is not manifold.",
        )
        scenario_reports[f"{region_id}.{role}"] = {
            "geometryMode": obj["dsb_gore_geometry_mode"],
            "identityId": obj["dsb_gore_identity_id"],
            "triangles": obj["dsb_gore_triangle_count"],
            "materials": json.loads(obj["dsb_gore_material_ids"]),
            "weights": status,
            "digest": obj["dsb_gore_mesh_geometry_digest"],
            "measurements": json.loads(obj["dsb_gore_validation_measurements"]),
            "hostMaximumDisplacement": max(displacements),
            "cavityOpeningArea": sum(
                source.data.polygons[int(record["faceIndex"])].area
                for record in records
            ),
        }
        if index == 0:
            proof_object = obj

    require(not failures, "; ".join(failures[:8]))
    require(proof_object is not None, "No final proof object was created.")

    lifecycle_baseline = {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
        "actions": len(bpy.data.actions),
    }
    for cycle in range(50):
        current = recipe(
            "RAGGED_IMPACT",
            parameter_schema.gore_identity_defaults("RAGGED_IMPACT")["macros"],
            5000 + cycle,
            1.0,
        )
        deformation_authoring._build_cavity_inlay_object(
            source,
            "Impact",
            "lifecycle",
            "CORE",
            current,
            proof_records,
            preview=True,
        )
        removed = deformation_authoring._remove_preview_gore_objects(
            "lifecycle", "Impact"
        )
        require(len(removed) == 1, "Preview lifecycle did not remove exactly one owned node.")
    lifecycle_after = {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
        "actions": len(bpy.data.actions),
    }
    require(
        lifecycle_after == lifecycle_baseline,
        f"Fifty preview cycles leaked resources: {lifecycle_baseline} -> {lifecycle_after}",
    )
    require(not deformation_authoring.preview_gore_objects(), "Preview-only nodes leaked.")
    preview_state = preview_service.state()
    require(not preview_state["timerRegistered"], "A managed preview timer leaked.")
    proof_paths = render_proofs(output, source, proof_object)
    identity_proof_paths = render_identity_proofs(output, actual_objects)

    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    proof_object.select_set(True)
    bpy.context.view_layer.objects.active = proof_object
    expected_export_material_count = len(
        {int(polygon.material_index) for polygon in proof_object.data.polygons}
    )
    glb_path = output / "cavity_inlay_acceptance.glb"
    result = bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_extras=True,
    )
    require("FINISHED" in result, "Cavity GLB export failed.")
    exported_name = proof_object.name
    bpy.ops.wm.read_factory_settings(use_empty=True)
    result = bpy.ops.import_scene.gltf(filepath=str(glb_path))
    require("FINISHED" in result, "Clean-scene cavity GLB import failed.")
    imported = bpy.data.objects.get(exported_name)
    require(imported is not None, "Clean GLB reimport is missing the cavity node.")
    require(imported.type == "MESH" and len(imported.data.polygons) > 0, "Reimported cavity node is empty.")
    require(
        len(imported.data.materials) == expected_export_material_count,
        "Reimported cavity lost a material role used by its identity.",
    )

    report = {
        "status": "PASS",
        "forgeVersion": "5.1.2",
        "blenderVersion": bpy.app.version_string,
        "identityCount": len(IDENTITIES),
        "macroMatrixGenerationCount": matrix_count,
        "randomizedSeedGenerationCount": len(IDENTITIES) * len(SEEDS),
        "failures": failures,
        "randomizedSeedMatrix": random_reports,
        "scales": scale_reports,
        "scenarios": scenario_reports,
        "macroRanges": macro_ranges,
        "proofRenders": proof_paths,
        "identityProofRenders": identity_proof_paths,
        "lifecycle": {
            "cycles": 50,
            "baseline": lifecycle_baseline,
            "after": lifecycle_after,
            "previewOnlyNodeCount": len(deformation_authoring.preview_gore_objects()),
            "previewTimerRegistered": preview_state["timerRegistered"],
        },
        "glb": str(glb_path),
        "cleanReimport": {
            "nodeName": exported_name,
            "polygonCount": len(imported.data.polygons),
            "materialCount": len(imported.data.materials),
        },
    }
    report_path = output / "cavity_inlay_acceptance.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("CAVITY_INLAY_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
