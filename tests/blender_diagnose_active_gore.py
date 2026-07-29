"""Read-only-on-disk diagnostic for one saved Blender Damage Key gore recipe.

The loaded blend is mutated only in memory to exercise regeneration; this
script never saves the file.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import deformation_authoring, trauma_field  # noqa: E402


def arguments():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default="")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--max-nuclei", action="store_true")
    parser.add_argument("--toggle-lifecycle", action="store_true")
    return parser.parse_args(raw)


def object_record(obj):
    layer_depths = {}
    raw_depths = str(obj.get("dsb_gore_layer_depths", "") or "")
    if raw_depths:
        try:
            layer_depths = json.loads(raw_depths)
        except (TypeError, ValueError, json.JSONDecodeError):
            layer_depths = {"broken": raw_depths}
    return {
        "name": obj.name,
        "role": str(obj.get("dsb_gore_pair_role", "")),
        "component": str(obj.get("dsb_gore_component", "")),
        "geometryMode": str(obj.get("dsb_gore_geometry_mode", "")),
        "surfaceMass": float(obj.get("dsb_gore_surface_mass", 0.0)),
        "nucleusAmount": float(
            obj.get("dsb_gore_nucleus_amount", 0.0)
        ),
        "nucleusTriangles": int(
            obj.get("dsb_gore_nucleus_triangle_count", 0)
        ),
        "nucleusCount": int(
            obj.get("dsb_gore_nucleus_count", 0)
        ),
        "nucleusDepthFraction": float(
            obj.get("dsb_gore_nucleus_depth_fraction", 0.0)
        ),
        "layerDepths": layer_depths,
    }


def main():
    args = arguments()
    # A saved file may auto-enable an older installed Forge before this source
    # checkout is imported. Re-register in memory so the diagnostic never mixes
    # old RNA definitions with the current implementation.
    if hasattr(bpy.types.Scene, "daf_settings"):
        addon.unregister()
    addon.register()
    registered_here = True
    try:
        context = bpy.context
        settings = context.scene.daf_settings
        registry = deformation_authoring._load_registry()
        key_name = str(args.key or settings.deformation_active_key)
        candidates = []
        selected = None
        for region in registry.get("regions", []):
            attached, detached = deformation_authoring._resolve_region_pair(region)
            payload = deformation_authoring._metadata(attached)
            candidates.extend(
                f"{region.get('regionId', '')}/{name}"
                for name in payload.get("keys", {})
            )
            if key_name in payload.get("keys", {}):
                selected = (region, attached, detached, payload, payload["keys"][key_name])
                break
        if selected is None:
            raise RuntimeError(
                f"Damage Key {key_name!r} was not found. Available: {candidates}"
            )
        region, attached, detached, payload, entry = selected
        region_id = str(region.get("regionId", ""))
        deformation_authoring._set_active_region(region_id, context)
        deformation_authoring._select_key(settings, key_name)
        if args.toggle_lifecycle:
            deformation_authoring.set_damage_key_preview_enabled(
                context,
                key_name,
                True,
            )
            toggle_on = {
                "maskVisible": (
                    attached.data.color_attributes.get(
                        deformation_authoring.GORE_PREVIEW_ATTRIBUTE
                    )
                    is not None
                ),
                "visibleGoreCount": sum(
                    not obj.hide_get()
                    for obj in deformation_authoring.generated_gore_objects(
                        region_id,
                        key_name,
                        include_preview=True,
                    )
                ),
            }
            deformation_authoring.set_damage_key_preview_enabled(
                context,
                key_name,
                False,
            )
            toggle_off = {
                "maskVisible": (
                    attached.data.color_attributes.get(
                        deformation_authoring.GORE_PREVIEW_ATTRIBUTE
                    )
                    is not None
                ),
                "visibleGoreCount": sum(
                    not obj.hide_get()
                    for obj in deformation_authoring.generated_gore_objects(
                        region_id,
                        key_name,
                        include_preview=True,
                    )
                ),
            }
        else:
            toggle_on = {}
            toggle_off = {}
        if args.max_nuclei:
            with deformation_authoring.preview_service.suspend_updates():
                settings.deformation_gore_nucleus = 100.0
                settings.deformation_gore_lobes = 100.0
            deformation_authoring.apply_gore_macro_transaction(
                context,
                "active-file maximum nuclei diagnostic",
            )
        overlay = trauma_field.normalize_gore_overlay(
            entry.get("surfaceGoreOverlay", {})
        )
        current_overlay = deformation_authoring._gore_overlay_from_settings(
            context
        )
        before = [
            object_record(obj)
            for obj in deformation_authoring.generated_gore_objects(
                region_id,
                key_name,
            )
        ]
        report = {
            "blend": bpy.data.filepath,
            "regionId": region_id,
            "key": key_name,
            "deformation": {
                "stampMode": str(entry.get("stampMode", "STACK")),
                "activeStampId": str(entry.get("activeStampId", "")),
                "entryMaximumDisplacement": float(
                    entry.get("maximumDisplacement", 0.0)
                ),
                "measuredMaximumDisplacement": float(
                    deformation_authoring._max_displacement(
                        attached, key_name
                    )
                ),
                "stamps": [
                    {
                        "stampId": str(stamp.get("stampId", "")),
                        "enabled": bool(stamp.get("enabled", True)),
                        "orderIndex": int(stamp.get("orderIndex", 0)),
                        "maximumDisplacement": float(
                            stamp.get("maximumDisplacement", 0.0)
                        ),
                    }
                    for stamp in entry.get("stamps", [])
                ],
                "settingsMaximumDisplacement": float(
                    settings.deformation_max_vertex_displacement
                ),
                "impactMacros": {
                    "area": float(settings.deformation_impact_size),
                    "depth": float(settings.deformation_impact_crush),
                    "falloff": float(
                        settings.deformation_impact_profile
                    ),
                    "edgeDamage": float(
                        settings.deformation_impact_edge_safety
                    ),
                    "distortion": float(
                        settings.deformation_impact_chaos
                    ),
                    "asymmetry": float(
                        settings.deformation_impact_asymmetry
                    ),
                },
                "objectScale": [
                    float(value)
                    for value in attached.matrix_world.to_scale()
                ],
            },
            "settings": {
                identifier: getattr(settings, identifier)
                for identifier in (
                    "deformation_gore_exposure",
                    "deformation_gore_cavity",
                    "deformation_gore_clot_fill",
                    "deformation_gore_breakup",
                    "deformation_gore_wetness_macro",
                    "deformation_gore_variation",
                    "deformation_gore_inlay_amount",
                    "deformation_gore_raised_amount",
                    "deformation_gore_surface_mass",
                    "deformation_gore_surface_relief",
                    "deformation_gore_nucleus",
                    "deformation_gore_lobes",
                    "deformation_gore_redness",
                    "deformation_preview_quality",
                    "deformation_auto_preview",
                    "deformation_live_preview",
                )
            },
            "recipe": {
                field: overlay[field]
                for field in (
                    "goreGeometryMode",
                    "goreIdentityId",
                    "goreInlayAmount",
                    "goreRaisedAmount",
                    "goreCavityDepth",
                    "goreLinerSeparation",
                    "goreClotFillDepth",
                    "goreClotCoverage",
                    "goreTissueCoverage",
                    "goreIslandBreakup",
                    "goreThicknessVariation",
                    "goreSurfaceMass",
                    "goreNucleusAmount",
                    "goreNucleusLobes",
                    "goreMaskSeed",
                )
            },
            "currentRecipe": {
                field: current_overlay[field]
                for field in (
                    "goreGeometryMode",
                    "goreIdentityId",
                    "goreInlayAmount",
                    "goreRaisedAmount",
                    "goreCavityDepth",
                    "goreLinerSeparation",
                    "goreClotFillDepth",
                    "goreClotCoverage",
                    "goreTissueCoverage",
                    "goreIslandBreakup",
                    "goreThicknessVariation",
                    "goreSurfaceMass",
                    "goreNucleusAmount",
                    "goreNucleusLobes",
                    "goreMaskSeed",
                )
            },
            "before": before,
            "toggleLifecycle": {
                "on": toggle_on,
                "off": toggle_off,
            },
        }
        try:
            candidate_entry = copy.deepcopy(entry)
            candidate_entry["surfaceGoreOverlay"] = current_overlay
            deformation_authoring.rebuild_raised_gore_for_key(
                region,
                attached,
                detached,
                key_name,
                candidate_entry,
            )
            errors, validation = deformation_authoring._raised_gore_errors(
                region,
                attached,
                detached,
                key_name,
                candidate_entry,
                current_overlay,
            )
            report["rebuild"] = {
                "status": "PASS" if not errors else "FAIL",
                "errors": errors,
                "validation": validation,
                "objects": [
                    object_record(obj)
                    for obj in deformation_authoring.generated_gore_objects(
                        region_id,
                        key_name,
                    )
                ],
            }
            if args.commit:
                commit = deformation_authoring.commit_current_tuning(
                    context
                )
                report["vipSave"] = {
                    "status": str(
                        commit.get("validation", {}).get(
                            "status",
                            "UNKNOWN",
                        )
                    ),
                    "errors": list(
                        commit.get("validation", {}).get("errors", [])
                    ),
                    "finalGoreTriangleCount": int(
                        commit.get("finalGoreTriangleCount", 0)
                    ),
                }
        except Exception as exc:
            report["rebuild"] = {
                "status": "EXCEPTION",
                "error": f"{type(exc).__name__}: {exc}",
            }
        print("ACTIVE_GORE_DIAGNOSTIC=" + json.dumps(report, sort_keys=True))
    finally:
        if registered_here:
            addon.unregister()


if __name__ == "__main__":
    main()
