"""Reversible Damage Key rename acceptance for an existing authoring blend.

Run Blender with the target .blend already loaded, for example::

    blender --background --factory-startup path/to/asset.blend \
      --python tests/blender_damage_key_rename_fixture.py

The test renames one managed key, verifies its ownership graph, renames it back,
and never saves the file.
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
from dreadstone_animation_forge import deformation_authoring  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def unique_check_name(old_name, existing_names):
    stem = old_name[:49] + "_RenameCheck"
    candidate = stem
    suffix = 1
    while candidate in existing_names:
        suffix += 1
        candidate = f"{stem[:58]}_{suffix:03d}"
    return candidate


def main():
    source_path = str(bpy.data.filepath)
    require(source_path, "Load an authoring .blend before running this acceptance test.")
    addon.register()
    try:
        context = bpy.context
        settings = context.scene.daf_settings
        registry = deformation_authoring._load_registry()
        candidates = []
        for region in registry.get("regions", []):
            try:
                attached, detached = deformation_authoring._resolve_region_pair(region)
            except Exception:
                continue
            payload = deformation_authoring._metadata(attached)
            names = sorted(payload.get("keys", {}))
            if names:
                candidates.append((region, attached, detached, payload, names))
        require(candidates, "The loaded blend has no resolvable managed Damage Keys.")

        preferred_region = str(registry.get("activeRegionId", ""))
        region, attached, detached, payload, names = next(
            (
                candidate
                for candidate in candidates
                if str(candidate[0].get("regionId", "")) == preferred_region
            ),
            candidates[0],
        )
        region_id = str(region.get("regionId", ""))
        deformation_authoring._set_active_region(region_id, context)
        old_name = str(settings.deformation_active_key)
        if old_name not in payload.get("keys", {}):
            old_name = names[0]
        deformation_authoring._select_key(settings, old_name)

        before = deformation_authoring._metadata(attached)["keys"][old_name]
        stable_id = str(before.get("damageKeyId", ""))
        stamp_ids = [
            str(stamp.get("stampId", ""))
            for stamp in before.get("stamps", [])
        ]
        preview_enabled = bool(before.get("previewEnabled", False))
        old_gore_count = len(
            deformation_authoring.generated_gore_objects(region_id, old_name)
        )
        require(stable_id, f"Damage Key {old_name!r} has no stable ID.")

        check_name = unique_check_name(old_name, set(names))
        settings.deformation_key_name = check_name
        result = bpy.ops.daf.rename_damage_key(key_name=old_name)
        require(result == {"FINISHED"}, f"Rename failed: {result}")
        renamed = deformation_authoring._metadata(attached)["keys"].get(check_name)
        require(renamed is not None, "Renamed metadata record is missing.")
        require(
            str(renamed.get("damageKeyId", "")) == stable_id,
            "Stable Damage Key ID changed during rename.",
        )
        require(
            [str(stamp.get("stampId", "")) for stamp in renamed.get("stamps", [])]
            == stamp_ids,
            "Child Stamp IDs changed during rename.",
        )
        require(
            attached.data.shape_keys.key_blocks.get(check_name) is not None,
            "Attached shape key did not follow the rename.",
        )
        if detached is not None:
            require(
                detached.data.shape_keys.key_blocks.get(check_name) is not None,
                "Detached shape key did not follow the rename.",
            )
        require(
            len(deformation_authoring.generated_gore_objects(region_id, check_name))
            == old_gore_count,
            "Generated-gore ownership count changed during rename.",
        )
        require(
            bool(renamed.get("previewEnabled", False)) == preview_enabled,
            "Per-key preview preference changed during rename.",
        )

        settings.deformation_key_name = old_name
        restore_result = bpy.ops.daf.rename_damage_key(key_name=check_name)
        require(restore_result == {"FINISHED"}, f"Rename-back failed: {restore_result}")
        restored_keys = deformation_authoring._metadata(attached)["keys"]
        require(old_name in restored_keys, "Original key name was not restored.")
        require(check_name not in restored_keys, "Temporary test name survived rename-back.")
        require(
            str(restored_keys[old_name].get("damageKeyId", "")) == stable_id,
            "Stable Damage Key ID changed during rename-back.",
        )

        print(
            "DAMAGE_KEY_RENAME_FIXTURE="
            + json.dumps(
                {
                    "status": "PASS",
                    "source": source_path,
                    "region": region_id,
                    "key": old_name,
                    "temporaryName": check_name,
                    "stableId": stable_id,
                    "stampCount": len(stamp_ids),
                    "goreObjectCount": old_gore_count,
                    "previewEnabled": preview_enabled,
                    "saved": False,
                },
                sort_keys=True,
            )
        )
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
