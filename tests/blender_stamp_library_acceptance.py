"""Blender runtime acceptance for the portable trauma-stamp library.

Run with a compatible authored .blend already opened and pass the destination
library path after ``--``. The script never saves the opened .blend.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import deformation_authoring  # noqa: E402


def coordinate_digest(key_block) -> str:
    digest = hashlib.sha256()
    for point in key_block.data:
        digest.update(struct.pack("<3d", float(point.co.x), float(point.co.y), float(point.co.z)))
    return digest.hexdigest()


def fail(message: str) -> None:
    print("STAMP_LIBRARY_ACCEPTANCE_FAIL", message)
    raise SystemExit(1)


def main() -> None:
    separator = sys.argv.index("--") if "--" in sys.argv else -1
    if separator < 0 or separator + 1 >= len(sys.argv):
        fail("Pass the output .dsbstamps.json path after --")
    output_path = Path(sys.argv[separator + 1]).resolve()

    addon.register()
    library = deformation_authoring.build_current_stamp_library()
    if int(library["keyCount"]) != 4 or int(library["stampCount"]) != 4:
        fail(f"Expected the authored Testman file to contain 4 keys / 4 stamps, got {library['keyCount']} / {library['stampCount']}")
    saved_path, saved_library = deformation_authoring.save_stamp_library(output_path)
    if saved_library != library:
        fail("In-memory and saved library payloads differ")

    original_stamps = {}
    registry = deformation_authoring._load_registry()
    for library_region in library["regions"]:
        region_id = str(library_region["regionId"])
        region = deformation_authoring._region_record(registry, region_id)
        if region is None:
            fail(f"Region {region_id} was not registered")
        attached, detached = deformation_authoring._resolve_region_pair(region)
        payload = deformation_authoring._metadata(attached)
        for key_record in library_region["keys"]:
            name = str(key_record["name"])
            attached_key = deformation_authoring._key(attached, name)
            detached_key = deformation_authoring._key(detached, name)
            if attached_key is None or detached_key is None:
                fail(f"Original paired key {name} is missing")
            original_stamps[(region_id, name)] = json.dumps(
                key_record["stamps"], sort_keys=True, separators=(",", ":")
            )
            deformation_authoring._remove_key(attached, name)
            deformation_authoring._remove_key(detached, name)
            payload.get("keys", {}).pop(name, None)
        deformation_authoring._store_metadata(attached, detached, payload)

    result = deformation_authoring.load_stamp_library(saved_path, bpy.context)
    if result["importedKeyCount"] != 4 or result["stampCount"] != 4:
        fail(f"Unexpected load result: {result}")
    if result["validation"]["status"] != "PASS":
        fail("Loaded library failed deformation validation: " + "; ".join(result["validation"].get("errors", [])))

    rebuilt_library = deformation_authoring.build_current_stamp_library()
    for library_region in rebuilt_library["regions"]:
        region_id = str(library_region["regionId"])
        region = deformation_authoring._region_record(deformation_authoring._load_registry(), region_id)
        attached, detached = deformation_authoring._resolve_region_pair(region)
        for key_record in library_region["keys"]:
            name = str(key_record["name"])
            rebuilt_geometry = (
                coordinate_digest(deformation_authoring._key(attached, name)),
                coordinate_digest(deformation_authoring._key(detached, name)),
            )
            rebuilt_stamps = json.dumps(key_record["stamps"], sort_keys=True, separators=(",", ":"))
            if rebuilt_stamps != original_stamps[(region_id, name)]:
                fail(f"Portable stamp recipe differs for {region_id}/{name}")
            deformation_authoring._set_active_region(region_id, bpy.context)
            deformation_authoring._select_key(bpy.context.scene.daf_settings, name)
            deformation_authoring.rebuild_active_deformation(bpy.context)
            repeated_geometry = (
                coordinate_digest(deformation_authoring._key(attached, name)),
                coordinate_digest(deformation_authoring._key(detached, name)),
            )
            if repeated_geometry != rebuilt_geometry:
                fail(f"Repeated deterministic rebuild differs for {region_id}/{name}")

    if not hasattr(bpy.ops.daf, "save_trauma_stamp_library") or not hasattr(bpy.ops.daf, "load_trauma_stamp_library"):
        fail("Stamp library operators were not registered")
    print(
        "STAMP_LIBRARY_ACCEPTANCE_PASS",
        json.dumps({
            "blend": bpy.data.filepath,
            "library": str(saved_path),
            "keyCount": result["importedKeyCount"],
            "stampCount": result["stampCount"],
            "validation": result["validation"]["status"],
            "libraryDigest": rebuilt_library["libraryDigest"],
        }, sort_keys=True),
    )


if __name__ == "__main__":
    main()
