"""Blender 5.1 regression for the unified deformation + gore preview lifecycle.

Run from the repository root:

    blender --background --factory-startup --python tests/blender_atomic_damage_preview_acceptance.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import deformation_authoring, trauma_field  # noqa: E402


REGION_ID = "atomic_fixture"
KEYS = ("Fixture_Impact_A", "Fixture_Impact_B")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def grid_surface(width=6, height=6):
    vertices = [(x * 0.012, y * 0.012, 0.0) for y in range(height) for x in range(width)]
    faces = []
    for y in range(height - 1):
        for x in range(width - 1):
            first = y * width + x
            faces.append((first, first + 1, first + width + 1, first + width))
    weights = []
    center = (width - 1) * 0.5
    for y in range(height):
        for x in range(width):
            distance = ((x - center) ** 2 + (y - center) ** 2) ** 0.5
            weights.append(max(0.08, 1.0 - distance / (width * 0.62)))
    return vertices, faces, weights


def make_stamp(source, region, stamp_id, selection_hash, topology):
    vertex_indices = list(range(len(source.data.vertices)))
    capture = {
        "placementMode": "SELECTED_VERTICES",
        "selectionKind": "VERTEX",
        "regionId": REGION_ID,
        "attachedObject": source.name,
        "topologyFingerprint": topology,
        "faceIndices": [],
        "vertexIndices": vertex_indices,
        "selectionHash": selection_hash,
        "centerLocal": [0.03, 0.03, 0.0],
        "centerWorld": [0.03, 0.03, 0.0],
        "normalLocal": [0.0, 0.0, 1.0],
        "normalWorld": [0.0, 0.0, 1.0],
        "boundsWorld": [[0.0, 0.0, 0.0], [0.06, 0.06, 0.0]],
        "estimatedRadius": 0.08,
    }
    require(not deformation_authoring._capture_errors(capture, region, source), "Fixture capture is invalid.")
    return trauma_field.normalize_stamp({
        "stampId": stamp_id,
        "displayName": stamp_id,
        "enabled": True,
        "family": "COMPACT_DENT",
        "placementMode": "SELECTED_VERTICES",
        "capture": capture,
        "center": capture["centerWorld"],
        "direction": [0.0, 0.0, -1.0],
        "directionMode": "INWARD_SURFACE_NORMAL",
        "directionLocal": [0.0, 0.0, -1.0],
        "radius": 0.08,
        "depth": 0.01,
        "falloff": 1.5,
        "strength": 1.0,
        "influenceMode": "PATCH_ONLY",
        "distanceMode": "WORLD_DISTANCE",
        "featherDistance": 0.02,
        "seamProtection": 0.0,
        "orderIndex": 0,
    })


def activate(context, source, region, key_name):
    deformation_authoring.clear_damage_preview(context, update_status=False)
    deformation_authoring._install_existing_surface_stain_preview(context, REGION_ID, key_name)
    key = deformation_authoring._key(source, key_name)
    key.value = 1.0
    deformation_authoring._set_single_damage_preview_state(context, REGION_ID, key_name, 1.0, "CORE")
    deformation_authoring._set_authoring_view(source, None, "CORE", context)


def assert_active(source, key_name):
    key = deformation_authoring._key(source, key_name)
    require(abs(float(key.value) - 1.0) < 1e-8, f"{key_name} morph did not activate.")
    require(
        source.data.color_attributes.get(deformation_authoring.GORE_PREVIEW_ATTRIBUTE) is not None,
        f"{key_name} stain mask did not activate.",
    )
    objects = deformation_authoring.generated_gore_objects(REGION_ID, key_name)
    require(objects and all(not obj.hide_get() for obj in objects), f"{key_name} raised gore is not visible.")


def assert_cleared(source, recipes_before, object_names_before):
    for key_name in KEYS:
        require(abs(float(deformation_authoring._key(source, key_name).value)) < 1e-8, f"{key_name} was not zeroed.")
    require(
        source.data.color_attributes.get(deformation_authoring.GORE_PREVIEW_ATTRIBUTE) is None,
        "Surface stain attribute leaked after clear.",
    )
    require(not source.get(deformation_authoring.GORE_PREVIEW_STATE_PROPERTY, ""), "Surface stain state leaked after clear.")
    objects = deformation_authoring.generated_gore_objects()
    require(objects and all(obj.hide_get() for obj in objects), "Inactive raised gore remained visible.")
    require({obj.name for obj in objects} == object_names_before, "Clear deleted or replaced raised-gore geometry.")
    payload = deformation_authoring._metadata(source)
    require(
        {name: payload["keys"][name]["recipeMarker"] for name in KEYS} == recipes_before,
        "Clear deleted or changed a stored gore recipe.",
    )


def main():
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    context = bpy.context
    vertices, faces, weights = grid_surface()
    mesh = bpy.data.meshes.new("DSB_ATOMIC_PREVIEW_FIXTURE_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    source = bpy.data.objects.new("DSB_ATOMIC_PREVIEW_FIXTURE", mesh)
    context.scene.collection.objects.link(source)
    material = bpy.data.materials.new("Atomic Fixture Skin")
    material.diffuse_color = (0.22, 0.08, 0.055, 1.0)
    source.data.materials.append(material)
    source.shape_key_add(name="Basis")
    for key_index, key_name in enumerate(KEYS):
        key = source.shape_key_add(name=key_name)
        for index, point in enumerate(key.data):
            point.co.z -= weights[index] * (0.007 + 0.002 * key_index)

    registry = deformation_authoring._empty_registry()
    region = deformation_authoring._record_from_core(REGION_ID, source)
    region["managedKeys"] = list(KEYS)
    registry["regions"] = [region]
    registry["activeRegionId"] = REGION_ID
    deformation_authoring._store_registry(registry)
    topology = deformation_authoring._topology_fingerprint(source)
    payload = deformation_authoring._metadata(source)
    payload["keys"] = {}
    for key_index, key_name in enumerate(KEYS):
        stamp_id = f"fixture_stamp_{key_index}"
        vertex_indices = list(range(len(source.data.vertices)))
        selection_hash = trauma_field.selection_hash(vertex_indices, topology, "VERTEX")
        stamp = make_stamp(source, region, stamp_id, selection_hash, topology)
        overlay = trauma_field.default_gore_overlay(
            "Gore_Crush_Heavy_Clotted",
            enabled=True,
            region_id=REGION_ID,
            linked_stamp_id=stamp_id,
            selection_hash=selection_hash,
            topology_fingerprint=topology,
            seed=7000 + key_index,
        )
        payload["keys"][key_name] = {
            "name": key_name,
            "regionId": REGION_ID,
            "recipeStatus": "PROCEDURAL_STACK",
            "legacy": False,
            "stamps": [stamp],
            "surfaceGoreOverlay": overlay,
            "recipeMarker": f"keep-{key_index}",
        }
        deformed = [tuple(point.co) for point in deformation_authoring._key(source, key_name).data]
        displacement = [abs(deformed[index][2] - vertices[index][2]) for index in range(len(vertices))]
        records = trauma_field.raised_gore_face_records(deformed, faces, weights, displacement, overlay)
        require(records, f"{key_name} fixture generated no gore records.")
        deformation_authoring._build_gore_shell_object(
            source, key_name, REGION_ID, "CORE", overlay, records
        )
    deformation_authoring._store_metadata(source, None, payload)
    recipes_before = {name: payload["keys"][name]["recipeMarker"] for name in KEYS}
    object_names_before = {obj.name for obj in deformation_authoring.generated_gore_objects()}

    activate(context, source, region, KEYS[0])
    assert_active(source, KEYS[0])
    deformation_authoring.clear_damage_preview(context)
    assert_cleared(source, recipes_before, object_names_before)

    activate(context, source, region, KEYS[0])
    assert_active(source, KEYS[0])
    activate(context, source, region, KEYS[1])
    assert_active(source, KEYS[1])
    require(
        all(obj.hide_get() for obj in deformation_authoring.generated_gore_objects(REGION_ID, KEYS[0])),
        "Old deformation gore remained visible after switching keys.",
    )

    for cycle in range(50):
        active_name = KEYS[cycle % len(KEYS)]
        activate(context, source, region, active_name)
        assert_active(source, active_name)
        deformation_authoring.clear_damage_preview(context, update_status=False)
        assert_cleared(source, recipes_before, object_names_before)
        leaked_materials = [
            item.name for item in bpy.data.materials
            if item.get("dsb_surface_gore_preview", False) and item.users == 0
        ]
        require(not leaked_materials, "Unused preview materials leaked: " + ", ".join(leaked_materials))

    activate(context, source, region, KEYS[0])
    snapshot = deformation_authoring.capture_damage_preview_snapshot(context)
    deformation_authoring.clear_damage_preview(context, update_status=False)
    deformation_authoring.restore_damage_preview_snapshot(context, snapshot)
    assert_active(source, KEYS[0])

    report = {
        "status": "PASS",
        "cycles": 50,
        "keys": list(KEYS),
        "goreObjects": sorted(object_names_before),
        "previewState": json.loads(context.scene[deformation_authoring.DAMAGE_PREVIEW_STATE_PROPERTY]),
    }
    print("ATOMIC_DAMAGE_PREVIEW_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
