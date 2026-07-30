"""Read-only diagnostic for a prepared surface-stain authoring Blend."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import deformation_authoring  # noqa: E402
from dreadstone_animation_forge import progressive_authoring  # noqa: E402


def main():
    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()
    registry = deformation_authoring._load_registry()
    sites = progressive_authoring._collection().get("sites", [])
    regions = []
    for region in registry.get("regions", []):
        attached, detached = deformation_authoring._resolve_region_pair(region)
        payload = deformation_authoring._metadata(attached)
        keys = []
        for key_name in deformation_authoring._managed_names(attached):
            entry = payload.get("keys", {}).get(key_name, {})
            overlay = entry.get("surfaceGoreOverlay", {})
            keys.append({
                "name": key_name,
                "damageKeyId": str(entry.get("damageKeyId", "")),
                "goreOverlayEnabled": bool(
                    overlay.get("goreOverlayEnabled", False)
                ),
                "goreOverlayMode": str(
                    overlay.get("goreOverlayMode", "")
                ),
                "goreGeometryMode": str(
                    overlay.get("goreGeometryMode", "")
                ),
                "previewStatus": str(
                    overlay.get("previewStatus", "")
                ),
                "generatedGoreNodes": list(
                    entry.get("goreGeneratedNodeNames", [])
                ),
            })
        regions.append({
            "regionId": region.get("regionId", ""),
            "attachedObject": attached.name,
            "detachedObject": detached.name if detached else "",
            "attachedMaterials": [
                slot.material.name if slot.material else ""
                for slot in attached.material_slots
            ],
            "detachedMaterials": [
                slot.material.name if slot.material else ""
                for slot in detached.material_slots
            ]
            if detached
            else [],
            "attachedHasPreviewMask": (
                attached.data.color_attributes.get(
                    deformation_authoring.GORE_PREVIEW_ATTRIBUTE
                )
                is not None
            ),
            "detachedHasPreviewMask": (
                detached is not None
                and detached.data.color_attributes.get(
                    deformation_authoring.GORE_PREVIEW_ATTRIBUTE
                )
                is not None
            ),
            "keys": keys,
        })
    report = {
        "blend": bpy.data.filepath,
        "regions": regions,
        "progressiveSites": [
            {
                "siteId": site.get("siteId", ""),
                "displayName": site.get("displayName", ""),
                "status": site.get("status", ""),
                "validationStatus": site.get(
                    "validationStatus", ""
                ),
                "enabledForExport": bool(
                    site.get("enabledForExport", False)
                ),
                "stages": {
                    stage_name: {
                        "damageKeyId": stage.get("damageKeyId", ""),
                        "deformationKeyName": stage.get(
                            "deformationKeyName", ""
                        ),
                        "regionId": stage.get("regionId", ""),
                        "saved": bool(stage.get("saved", False)),
                        "validationStatus": stage.get(
                            "validationStatus", ""
                        ),
                    }
                    for stage_name, stage in site.get(
                        "stages", {}
                    ).items()
                },
            }
            for site in sites
        ],
    }
    print(
        "SURFACE_STAIN_SOURCE_DIAGNOSTIC="
        + json.dumps(report, sort_keys=True)
    )


if __name__ == "__main__":
    main()
