"""Register an extracted release ZIP in Blender without using repository modules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


def arguments():
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True)
    return parser.parse_args(raw)


def main():
    package_dir = Path(arguments().package_dir).resolve()
    if not (package_dir / "__init__.py").is_file():
        raise RuntimeError(f"Extracted package is incomplete: {package_dir}")
    sys.path.insert(0, str(package_dir.parent))
    import dreadstone_animation_forge as addon
    from dreadstone_animation_forge import deformation_authoring

    imported = Path(addon.__file__).resolve()
    if imported.parent != package_dir:
        raise RuntimeError(f"Smoke test imported {imported}, not extracted release {package_dir}.")
    addon.register()
    if not hasattr(bpy.types.Scene, "daf_settings"):
        raise RuntimeError("Extracted release did not register DAFSettings.")
    if not deformation_authoring.GORE_TEXTURE_ATLAS_PATH.is_file():
        raise RuntimeError("Extracted release is missing its muscle-fiber atlas.")
    report = {
        "status": "PASS",
        "version": list(addon.bl_info["version"]),
        "module": str(imported),
        "textureAtlas": str(deformation_authoring.GORE_TEXTURE_ATLAS_PATH),
    }
    addon.unregister()
    print("RELEASE_ZIP_SMOKE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
