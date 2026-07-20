"""Build a non-anatomical technical core/forearm/compound acceptance fixture.

This helper is for structural regression testing only. It uses explicitly
supplied mesh face indices and never represents artist or visual approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--technical-face", type=int, default=0)
    parser.add_argument("--head-only", action="store_true")
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(values)


def select_patch(obj, seed_index, count=13):
    bpy.ops.object.select_all(action='DESELECT')
    obj.hide_viewport = False
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    mesh = bmesh.from_edit_mesh(obj.data)
    mesh.faces.ensure_lookup_table()
    for face in mesh.faces:
        face.select_set(False)
    if seed_index < 0 or seed_index >= len(mesh.faces):
        raise RuntimeError(f"technical face {seed_index} is invalid for {obj.name}")
    queue = [mesh.faces[seed_index]]
    seen = set()
    chosen = []
    cursor = 0
    while cursor < len(queue) and len(chosen) < count:
        face = queue[cursor]
        cursor += 1
        if face.index in seen:
            continue
        seen.add(face.index)
        chosen.append(face)
        queue.extend(sorted(
            {linked for edge in face.edges for linked in edge.link_faces if linked.index not in seen},
            key=lambda item: item.index,
        ))
    for face in chosen:
        face.select_set(True)
    bmesh.update_edit_mesh(obj.data)
    return [face.index for face in chosen]


def main():
    args = arguments()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import dreadstone_animation_forge as addon
    addon.register()
    from dreadstone_animation_forge import damage_authoring, deformation_authoring

    settings = bpy.context.scene.daf_settings
    built = []
    head_specifications = (
        ("head", "Head_Impact_Left"),
        ("head", "Head_Impact_Right"),
        ("head", "Head_Impact_Front"),
        ("head", "Head_Impact_Back"),
    )
    core_specifications = (
        ("body_core", "Body_Impact_Front"),
        ("body_core", "Body_Impact_Left"),
        ("forearm_left", "Forearm_L_Impact_Outer"),
        ("forearm_right", "Forearm_R_Impact_Outer"),
    )
    specifications = head_specifications if args.head_only else head_specifications + core_specifications
    for region_id, semantic_name in specifications:
        deformation_authoring._set_active_region(region_id, bpy.context)
        _registry, _region, target, _detached = deformation_authoring._resolve_active_region(bpy.context)
        face_indices = select_patch(target, args.technical_face)
        settings.deformation_impact_preset = 'CUSTOM'
        settings.deformation_impact_intensity = 'HEAVY'
        settings.deformation_impact_semantic_name = semantic_name
        result = bpy.ops.daf.create_impact_from_selection()
        if 'FINISHED' not in result:
            raise RuntimeError(f"technical one-click impact failed for {region_id}/{semantic_name}")
        result = bpy.ops.daf.commit_impact()
        if 'FINISHED' not in result:
            raise RuntimeError(f"technical impact commit failed for {region_id}/{semantic_name}")
        built.append({
            "regionId": region_id,
            "key": settings.deformation_active_key,
            "technicalFaceIndices": face_indices,
        })

    compound = None
    event_id = "Neck_Shoulder_Crush_Left"
    registry = deformation_authoring._load_registry()
    if not args.head_only and deformation_authoring._compound_event_record(registry, event_id) is None:
        state = damage_authoring._load_state()
        protected = bpy.data.objects.get(state.get("protected_source_mesh", ""))
        seam = state.get("seams", {}).get("head_neck", {})
        if protected is None or not seam:
            raise RuntimeError("technical compound setup cannot resolve the head_neck contract")
        protected_world = damage_authoring._evaluated_hidden_world_matrix(protected)
        center_local = Vector(seam.get("joint_plane", {}).get("center_object", (0.0, 0.0, 0.0)))
        center_world = protected_world @ center_local
        settings.compound_event_id = event_id
        settings.compound_display_name = "Technical Neck Shoulder Crush"
        settings.compound_linked_seam_ids = "head_neck"
        settings.compound_impact_origin = tuple(center_world)
        settings.compound_impact_direction = (0.0, 0.0, -1.0)
        settings.compound_impact_radius = 0.32
        settings.compound_impact_depth = 0.028
        settings.compound_displacement_limit = 0.06
        settings.compound_continuity_mode = 'LOCK_BOUNDARY_TO_SHARED_FIELD'
        deformation_authoring.create_compound_event(bpy.context)

        deformation_authoring._set_active_region("head", bpy.context)
        head_target = deformation_authoring._resolve_active_region(bpy.context)[2]
        head_names = deformation_authoring._managed_names(head_target)
        if not head_names:
            raise RuntimeError("technical compound fixture needs one prepared head key")
        head_key = (
            "Technical_Testman_Impact_v001"
            if "Technical_Testman_Impact_v001" in head_names else head_names[0]
        )
        deformation_authoring._select_key(settings, head_key)
        deformation_authoring.add_active_region_to_compound_event(bpy.context)

        deformation_authoring._set_active_region("body_core", bpy.context)
        deformation_authoring._select_key(settings, "Body_Impact_Front_v001")
        deformation_authoring.add_active_region_to_compound_event(bpy.context)
        registry = deformation_authoring._load_registry()
        event = deformation_authoring._compound_event_record(registry, event_id)
        for participant in event.get("participants", []):
            if participant.get("regionId") in {"head", "body_core"}:
                participant["seamIds"] = ["head_neck"]
        deformation_authoring._store_registry(registry)
        compound = deformation_authoring.rebuild_compound_event(bpy.context)
    elif not args.head_only:
        compound = deformation_authoring.rebuild_compound_event(bpy.context)

    validation = damage_authoring._validate_authoring(damage_authoring._load_state())
    if validation["status"] != "PASS":
        raise RuntimeError("technical fixture validation failed: " + "; ".join(validation["errors"][:6]))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
    report = {
        "status": "PASS",
        "blenderVersion": bpy.app.version_string,
        "forgeVersion": deformation_authoring._version_string(),
        "technicalSurfaceOnly": True,
        "visualApproval": False,
        "builtImpacts": built,
        "compoundEventId": compound["eventId"] if compound is not None else "",
        "compoundParticipantCount": len(compound.get("participants", [])) if compound is not None else 0,
        "validation": validation["status"],
        "savedFixture": str(output),
    }
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("FORGE_TECHNICAL_FIXTURE_RESULT=" + json.dumps(report, sort_keys=True))
    addon.unregister()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
