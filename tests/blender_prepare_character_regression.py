"""End-to-end regression for Prepare Character on a supplied saved scene.

The runner loads the checkout instead of the installed extension and never
saves the source blend.  Invoke with Blender's ``--background file.blend``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]


def require_finished(result, label):
    if "FINISHED" not in result:
        raise RuntimeError(f"{label} returned {sorted(result)}")


def load_checkout():
    for module in addon_utils.modules(refresh=False):
        if getattr(module, "bl_info", {}).get("name") != "Dreadstone Animation Forge":
            continue
        if addon_utils.check(module.__name__)[1]:
            addon_utils.disable(module.__name__, default_set=False)
    for name in tuple(sys.modules):
        if name == "dreadstone_animation_forge" or name.startswith("dreadstone_animation_forge."):
            del sys.modules[name]
    sys.path.insert(0, str(ROOT))
    import dreadstone_animation_forge

    dreadstone_animation_forge.register()
    return dreadstone_animation_forge


def main():
    load_checkout()
    settings = bpy.context.scene.daf_settings
    output = Path(tempfile.gettempdir()) / "daf_prepare_character_regression"
    output.mkdir(parents=True, exist_ok=True)
    settings.damage_readiness_output_directory = str(output)

    result = bpy.ops.daf.prepare_character_for_damage_authoring()
    require_finished(result, "Prepare Character for Damage Authoring")
    require_finished(bpy.ops.daf.validate_damage_authoring_asset(), "Validate Damage Authoring Asset")

    summary = json.loads(bpy.context.scene.get("dsb_prepare_character_summary_json", "[]"))
    payload = {
        "sourceBlend": bpy.data.filepath,
        "summary": summary,
        "readiness": settings.damage_readiness_overall_status,
        "authoringValidation": settings.last_damage_authoring_validation,
        "report": settings.last_damage_readiness_json_path,
    }
    if payload["readiness"] not in {"READY", "SOURCE READY"}:
        raise RuntimeError(f"Unexpected readiness: {payload['readiness']}")
    if "PASS" not in payload["authoringValidation"]:
        raise RuntimeError(f"Unexpected authoring validation: {payload['authoringValidation']}")
    print("DAF_PREPARE_REGRESSION=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
