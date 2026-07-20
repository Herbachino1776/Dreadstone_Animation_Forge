"""Blender 5.1 structural workflow acceptance for Forge 3.15.

The runner uses an explicitly supplied technical seed face only. It does not
claim anatomy or visual quality and must not be used as an artist approval.

Example:
  blender prepared.blend --factory-startup --background --python \
    tests/blender_healing_workflow_acceptance.py -- \
    --output healing_workflow.json --save benchmark.blend --technical-face 0
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import traceback
from pathlib import Path

import bmesh
import bpy


ROOT = Path(__file__).resolve().parents[1]


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--save", default="")
    parser.add_argument("--technical-face", type=int, required=True)
    parser.add_argument("--patch-faces", type=int, default=13)
    parser.add_argument("--preview-iterations", type=int, default=25)
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(values)


def select_connected_patch(obj, seed_index, count):
    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')
    mesh = bmesh.from_edit_mesh(obj.data)
    mesh.faces.ensure_lookup_table()
    if seed_index < 0 or seed_index >= len(mesh.faces):
        raise RuntimeError(f"technical face {seed_index} is outside the mesh")
    for face in mesh.faces:
        face.select_set(False)
    queue = [mesh.faces[seed_index]]
    chosen = []
    visited = set()
    cursor = 0
    while cursor < len(queue) and len(chosen) < count:
        face = queue[cursor]
        cursor += 1
        if face.index in visited:
            continue
        visited.add(face.index)
        chosen.append(face)
        neighbors = sorted(
            {linked for edge in face.edges for linked in edge.link_faces if linked.index not in visited},
            key=lambda item: item.index,
        )
        queue.extend(neighbors)
    for face in chosen:
        face.select_set(True)
    bmesh.update_edit_mesh(obj.data)
    return [face.index for face in chosen]


def main():
    args = arguments()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "dreadstone.forge_healing_workflow_acceptance.v1",
        "blenderVersion": bpy.app.version_string,
        "fixture": bpy.data.filepath,
        "technicalSurfaceOnly": True,
        "visualApproval": False,
        "failures": [],
    }
    addon = None
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import dreadstone_animation_forge as addon
        addon.register()
        from dreadstone_animation_forge import damage_authoring, deformation_authoring

        report["forgeVersion"] = deformation_authoring._version_string()
        report["forgeBuild"] = deformation_authoring.DEFORMATION_BUILD_ID
        settings = bpy.context.scene.daf_settings
        deformation_authoring._set_active_region("head", bpy.context)
        _registry, region, attached, detached = deformation_authoring._resolve_active_region(bpy.context)
        bpy.ops.object.select_all(action='DESELECT')
        attached.hide_viewport = False
        attached.hide_set(False)
        attached.select_set(True)
        bpy.context.view_layer.objects.active = attached
        bpy.ops.object.mode_set(mode='EDIT')

        before_keys = set(deformation_authoring._metadata(attached).get("keys", {}))
        select_connected_patch(attached, args.technical_face, 0)
        invalid_cancelled = False
        try:
            result = bpy.ops.daf.create_impact_from_selection()
            invalid_cancelled = 'CANCELLED' in result
        except RuntimeError:
            invalid_cancelled = True
        after_keys = set(deformation_authoring._metadata(attached).get("keys", {}))
        report["invalidSelectionRollback"] = {
            "cancelled": invalid_cancelled,
            "keyInventoryStable": before_keys == after_keys,
        }
        if not invalid_cancelled or before_keys != after_keys:
            raise RuntimeError("invalid-selection one-click draft did not roll back cleanly")

        patch = select_connected_patch(attached, args.technical_face, max(1, args.patch_faces))
        settings.deformation_impact_preset = 'HEAD_LEFT'
        settings.deformation_impact_intensity = 'HEAVY'
        settings.deformation_impact_semantic_name = "Technical_Testman_Impact"
        started = time.perf_counter()
        created = bpy.ops.daf.create_impact_from_selection()
        create_seconds = time.perf_counter() - started
        if 'FINISHED' not in created:
            raise RuntimeError("one-click impact creation did not finish")

        base_radius = float(settings.deformation_seed_radius)
        samples = []
        for index in range(max(1, args.preview_iterations)):
            settings.deformation_seed_radius = max(0.005, base_radius + ((index % 5) - 2) * 0.001)
            started = time.perf_counter()
            result = deformation_authoring.preview_service.run_now(bpy.context, quality="FAST")
            samples.append((time.perf_counter() - started) * 1000.0)
            if result.get("failed"):
                raise RuntimeError(result.get("error", "FAST preview failed"))

        started = time.perf_counter()
        committed = bpy.ops.daf.commit_impact()
        commit_seconds = time.perf_counter() - started
        if 'FINISHED' not in committed:
            raise RuntimeError("impact commit did not finish")
        complete = damage_authoring._validate_authoring(damage_authoring._load_state())
        if complete["status"] != "PASS":
            raise RuntimeError("complete validation failed: " + "; ".join(complete.get("errors", [])[:4]))
        entry = deformation_authoring._metadata(attached).get("keys", {}).get(settings.deformation_active_key, {})
        report["impact"] = {
            "region": region.get("regionId"),
            "paired": detached is not None,
            "key": settings.deformation_active_key,
            "technicalFaceIndices": patch,
            "createSeconds": create_seconds,
            "fastPreviewIterations": len(samples),
            "fastPreviewMedianMs": statistics.median(samples),
            "fastPreviewMinMs": min(samples),
            "fastPreviewMaxMs": max(samples),
            "commitSeconds": commit_seconds,
            "draftStatus": entry.get("draftStatus"),
            "focusedValidation": entry.get("validationStatus"),
            "goreTriangleCounts": entry.get("goreTriangleCounts", {}),
            "completeValidation": complete["status"],
        }
        if args.save:
            save_path = Path(args.save).resolve()
            save_path.parent.mkdir(parents=True, exist_ok=True)
            result = bpy.ops.wm.save_as_mainfile(filepath=str(save_path), check_existing=False)
            if 'FINISHED' not in result:
                raise RuntimeError("acceptance fixture save did not finish")
            report["savedFixture"] = str(save_path)
        report["status"] = "PASS"
    except Exception as exc:
        report["status"] = "FAIL"
        report["failures"].append({
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc()[-8000:],
        })
    finally:
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("FORGE_HEALING_WORKFLOW_RESULT=" + json.dumps({
            "output": str(output), "status": report.get("status"), "failures": len(report["failures"])
        }, sort_keys=True))
        if addon is not None:
            try:
                addon.unregister()
            except Exception:
                pass
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
