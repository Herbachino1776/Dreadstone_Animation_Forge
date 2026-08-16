"""Register an extracted release ZIP in Blender without using repository modules."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

import bpy
from _bpy_restrict_state import RestrictBlend


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
    # Blender enables add-ons while bpy.data/context are deliberately
    # restricted.  Registration must not inspect scene objects or Actions.
    with RestrictBlend():
        addon.register()
    if not hasattr(bpy.types.Scene, "daf_settings"):
        raise RuntimeError("Extracted release did not register DAFSettings.")
    if not deformation_authoring.GORE_TEXTURE_ATLAS_PATH.is_file():
        raise RuntimeError("Extracted release is missing its muscle-fiber atlas.")
    panel_source = (package_dir / "ui" / "panels.py").read_text(encoding="utf-8")
    panel_tree = ast.parse(panel_source)
    requested_icons = {
        keyword.value.value
        for node in ast.walk(panel_tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "icon"
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    }
    valid_icons = set(
        bpy.types.UILayout.bl_rna.functions["operator"]
        .parameters["icon"]
        .enum_items.keys()
    )
    invalid_icons = sorted(requested_icons - valid_icons)
    if invalid_icons:
        raise RuntimeError(
            "Extracted release contains invalid Blender UI icons: "
            + ", ".join(invalid_icons)
        )
    report = {
        "status": "PASS",
        "version": list(addon.bl_info["version"]),
        "module": str(imported),
        "textureAtlas": str(deformation_authoring.GORE_TEXTURE_ATLAS_PATH),
        "panelIconsValidated": len(requested_icons),
    }
    addon.unregister()
    print("RELEASE_ZIP_SMOKE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
