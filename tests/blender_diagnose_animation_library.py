"""Read-only-on-disk VIP animation-library diagnostic for a saved .blend."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import animation_library  # noqa: E402


def arguments():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", default="")
    parser.add_argument("--finalize-draft", action="store_true")
    return parser.parse_args(raw)


def main():
    args = arguments()
    if hasattr(bpy.types.Scene, "daf_settings"):
        addon.unregister()
    addon.register()
    context = bpy.context
    settings = context.scene.daf_settings
    armature = addon.find_armature(context)
    actions = animation_library.character_actions(
        armature,
        include_drafts=True,
    )
    selected = next(
        (
            action
            for action in actions
            if action.name == args.action
        ),
        None,
    )
    if selected is None:
        selected = next(
            (
                action
                for action in actions
                if "walk" in action.name.lower()
            ),
            actions[0] if actions else None,
        )
    lifecycle = {}
    if selected is not None:
        animation_library.select_action(settings, selected)
        lifecycle["play"] = animation_library.play_action(
            context,
            armature,
            selected,
            start_playback=False,
        )
        if bool(selected.get("dsb_draft", False)):
            lifecycle["edit"] = (
                animation_library.edit_existing_draft(
                    context,
                    armature,
                    selected,
                )
            )
            if args.finalize_draft:
                finalized = addon.approve_draft_action(
                    context,
                    animation_library.infer_action_kind(selected),
                )
                animation_library.select_action(
                    settings,
                    finalized,
                )
                lifecycle["finalize"] = {
                    "action": finalized.name,
                    "approved": bool(
                        finalized.get("dsb_approved", False)
                    ),
                    "draft": bool(
                        finalized.get("dsb_draft", True)
                    ),
                }
                selected = finalized
        else:
            lifecycle["edit"] = animation_library.begin_edit(
                context,
                armature,
                selected,
            )
            lifecycle["cancel"] = animation_library.cancel_edit(
                context,
                armature,
            )
    fps = context.scene.render.fps / max(
        context.scene.render.fps_base,
        0.001,
    )
    report = {
        "blend": bpy.data.filepath,
        "armature": armature.name,
        "armatures": [
            {
                "name": obj.name,
                "boneCount": len(obj.data.bones),
                "activeAction": (
                    obj.animation_data.action.name
                    if obj.animation_data
                    and obj.animation_data.action
                    else ""
                ),
            }
            for obj in bpy.data.objects
            if obj.type == "ARMATURE"
        ],
        "allActions": [
            {
                "name": action.name,
                "approved": bool(
                    action.get("dsb_approved", False)
                ),
                "draft": bool(action.get("dsb_draft", False)),
                "owner": str(
                    action.get(
                        animation_library.CLIP_OWNER_PROPERTY,
                        "",
                    )
                ),
                "bones": animation_library.referenced_bones(action),
            }
            for action in bpy.data.actions
        ],
        "selected": selected.name if selected else "",
        "actionCount": len(actions),
        "actions": [
            {
                "name": action.name,
                **animation_library.action_summary(action, fps),
            }
            for action in actions
        ],
        "lifecycle": lifecycle,
        "status": "PASS" if actions else "NO ANIMATIONS",
    }
    print(
        "ANIMATION_LIBRARY_DIAGNOSTIC="
        + json.dumps(report, sort_keys=True)
    )


if __name__ == "__main__":
    main()
