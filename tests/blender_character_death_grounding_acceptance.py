"""Validate every generated death style on a real character .blend.

Run:
    blender --background --factory-startup character.blend \
      --python tests/blender_character_death_grounding_acceptance.py \
      -- DSB_DAMAGE_RIG output.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402


STYLES = ("CHEST_HOLD", "FACEPLANT", "KNEES_FIRST", "INSTANT_LIMP")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    armature_name = args[0] if args else "DSB_DAMAGE_RIG"
    output_path = Path(args[1]) if len(args) > 1 else None

    if not hasattr(bpy.types.Scene, "daf_settings"):
        addon.register()

    armature = bpy.data.objects.get(armature_name)
    require(armature is not None, f"Armature not found: {armature_name}")
    require(armature.type == "ARMATURE", f"Not an armature: {armature_name}")

    bpy.ops.object.select_all(action="DESELECT")
    armature.hide_viewport = False
    armature.hide_set(False)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature

    candidates = [
        obj for obj in addon.character_objects_for_armature(bpy.context, armature)
        if obj.type == "MESH"
        and obj.name != addon.PREVIEW_FLOOR_NAME
        and not bool(obj.get("dsb_preview_only", False))
    ]
    displayed = [
        obj for obj in candidates
        if not obj.hide_render and not obj.hide_viewport and not obj.hide_get()
    ]
    meshes = displayed or candidates
    require(meshes, "No character meshes found for grounding acceptance.")

    settings = bpy.context.scene.daf_settings
    settings.death_instant_seconds = 0.72
    results = {}
    for style in STYLES:
        settings.collapse_style = style
        operator_result = bpy.ops.daf.collapse()
        require(
            "FINISHED" in operator_result,
            f"{style} generation failed: {sorted(operator_result)}",
        )
        action = bpy.data.actions.get(addon.DRAFT_ACTION_NAMES["DEATH"])
        require(action is not None, f"{style} did not create a death Action.")
        start, end = addon.action_frame_bounds(action)
        worst_minimum = float("inf")
        for frame in range(int(math.floor(start)), int(math.ceil(end)) + 1):
            bpy.context.scene.frame_set(frame)
            minimum, _maximum = addon.world_bounds(bpy.context, meshes)
            worst_minimum = min(worst_minimum, float(minimum.z))

        bpy.context.scene.frame_set(int(math.ceil(end)))
        minimum, maximum = addon.world_bounds(bpy.context, meshes)
        final_height = float(maximum.z - minimum.z)
        reference_height = float(action["dsb_terminal_reference_height_m"])
        final_ratio = final_height / reference_height
        maximum_ratio = float(action["dsb_terminal_max_height_ratio"])
        validation = addon.validate_death_floor_action(
            bpy.context,
            action,
            armature,
            meshes,
            fallback_ground_sink=settings.ground_sink,
        )
        require(
            validation["status"] == "PASS",
            f"{style} validation failed: {validation['errors']}",
        )
        require(
            final_ratio <= maximum_ratio + 0.0001,
            f"{style} final height ratio {final_ratio:.4f} exceeds {maximum_ratio:.4f}.",
        )
        results[style] = {
            "frameStart": start,
            "frameEnd": end,
            "terminalContactFrame": int(action["dsb_terminal_contact_frame"]),
            "worstMinimumZ": worst_minimum,
            "terminalMinimumZ": float(minimum.z),
            "terminalMaximumZ": float(maximum.z),
            "terminalHeightM": final_height,
            "referenceHeightM": reference_height,
            "terminalHeightRatio": final_ratio,
            "maximumTerminalHeightRatio": maximum_ratio,
            "validation": validation,
        }

    report = {
        "status": "PASS",
        "file": bpy.data.filepath,
        "armature": armature.name,
        "meshes": sorted(obj.name for obj in meshes),
        "styles": results,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("CHARACTER_DEATH_GROUNDING_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
