"""Synthetic Blender acceptance for Character Variant Family persistence/COW."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import animation_library, variant_authoring  # noqa: E402
from dreadstone_animation_forge import variant_family as model  # noqa: E402
from dreadstone_animation_forge.anatomy import skin_and_bones  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(str(message))


def appearance_handoff(variant_id, display_name):
    return {
        "schema": model.SBF_HANDOFF_SCHEMA,
        "schema_version": model.SBF_HANDOFF_SCHEMA_VERSION,
        "family_schema": model.SBF_FAMILY_SCHEMA,
        "family_schema_version": model.SBF_FAMILY_SCHEMA_VERSION,
        "family_id": "synthetic-bandit-family",
        "family_display_name": "Synthetic Bandit",
        "variant_id": variant_id,
        "variant_display_name": display_name,
        "export_identity": f"synthetic_bandit_{variant_id}",
        "technical_body_schema": model.SBF_TECHNICAL_BODY_SCHEMA,
        "technical_body_schema_version": model.SBF_TECHNICAL_BODY_SCHEMA_VERSION,
        "technical_body_fingerprint": "a" * 64,
        "appearance_revision": 1,
        "approval": {
            "state": "APPROVED",
            "approved_revision": 1,
            "appearance_fingerprint": ("b" if variant_id == "filthy" else "c") * 64,
            "approved_at_utc": "2026-08-11T20:00:00+00:00",
            "addon_version": "2.2.0",
        },
    }


def stamp_canonical(armature):
    mapping = {
        sbf_role: skin_and_bones.CANONICAL_HUMANOID_MAPPING[forge_role]
        for sbf_role, forge_role in skin_and_bones.SBF_TO_FORGE_ROLE.items()
    }
    armature[skin_and_bones.SBF_RIG_VERSION_PROPERTY] = skin_and_bones.SBF_CANONICAL_RIG_VERSION
    armature[skin_and_bones.SBF_FORWARD_AXIS_PROPERTY] = "+Y"
    armature[skin_and_bones.SBF_UP_AXIS_PROPERTY] = "+Z"
    armature[skin_and_bones.SBF_ROOT_BONE_PROPERTY] = "root"
    armature[skin_and_bones.SBF_ORIENTATION_REVISION_PROPERTY] = 1
    armature[skin_and_bones.SBF_ORIENTATION_STATE_PROPERTY] = "CANONICAL_Y_PLUS"
    armature[skin_and_bones.SBF_RIG_CONTRACT_VERSION_PROPERTY] = 1
    armature[skin_and_bones.SBF_UNIT_SCALE_METERS_PROPERTY] = 1.0
    armature[skin_and_bones.SBF_BONE_MAPPING_PROPERTY] = json.dumps(mapping)


def make_canonical_armature(name):
    bpy.ops.object.armature_add(enter_editmode=True)
    armature = bpy.context.active_object
    armature.name = name
    first = armature.data.edit_bones[0]
    first.name = "root"
    first.head = (0.0, 0.0, 0.0)
    first.tail = (0.0, 0.0, 0.1)
    created = {"root": first}
    for index, (bone_name, parent_name) in enumerate(
        skin_and_bones.CANONICAL_HUMANOID_PARENTS.items()
    ):
        if bone_name == "root":
            continue
        bone = armature.data.edit_bones.new(bone_name)
        bone.parent = created[parent_name]
        side = -0.12 if "left" in bone_name else 0.12 if "right" in bone_name else 0.0
        bone.head = (side, 0.01 * index, 0.10 + 0.07 * index)
        bone.tail = (side, 0.01 * index + 0.02, 0.16 + 0.07 * index)
        created[bone_name] = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    stamp_canonical(armature)
    return armature


def make_mesh(name, armature, material, handoff):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(
        [(-0.3, 0.0, 0.0), (0.3, 0.0, 0.0), (0.0, 0.0, 1.0)],
        [],
        [(0, 1, 2)],
    )
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = armature
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature
    root_group = obj.vertex_groups.new(name="root")
    root_group.add(range(len(mesh.vertices)), 1.0, "REPLACE")
    mesh.materials.append(material)
    encoded = model.stable_json(handoff)
    for owner in (armature, obj):
        owner[model.SBF_HANDOFF_PROPERTY] = encoded
        owner[model.SBF_FAMILY_ID_PROPERTY] = handoff["family_id"]
        owner[model.SBF_VARIANT_ID_PROPERTY] = handoff["variant_id"]
        owner[model.SBF_BODY_FINGERPRINT_PROPERTY] = handoff[
            "technical_body_fingerprint"
        ]
    return obj


def select_character(armature, mesh):
    bpy.ops.object.select_all(action="DESELECT")
    armature.hide_set(False)
    mesh.hide_set(False)
    armature.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = armature


def make_shared_action(armature):
    action = bpy.data.actions.new("DSB_Walk_Synthetic_v001")
    action["dsb_approved"] = True
    action["dsb_draft"] = False
    action["dsb_approved_kind"] = "WALK"
    action[animation_library.CLIP_ID_PROPERTY] = "clip_shared_walk"
    action[animation_library.CLIP_OWNER_PROPERTY] = armature.name
    action[variant_authoring.ACTION_SCOPE_PROPERTY] = model.ACTION_SCOPE_SHARED
    action[variant_authoring.ACTION_FAMILY_PROPERTY] = "synthetic-bandit-family"
    action[variant_authoring.ACTION_SHARED_ID_PROPERTY] = "clip_shared_walk"
    action.use_fake_user = True
    armature.animation_data_create()
    armature.animation_data.action = action
    body = armature.pose.bones["body"]
    for frame, value in ((1, 0.0), (13, 0.08), (25, 0.0)):
        body.location.y = value
        body.keyframe_insert("location", frame=frame, group="body")
    return action


def main():
    addon.register()
    red = bpy.data.materials.new("Filthy_BaseColor")
    red.diffuse_color = (0.5, 0.12, 0.08, 1.0)
    gray = bpy.data.materials.new("Sooted_BaseColor")
    gray.diffuse_color = (0.08, 0.08, 0.08, 1.0)

    base_handoff = appearance_handoff("filthy", "Filthy")
    base_rig = make_canonical_armature("SBF_Filthy_Rig")
    base_mesh = make_mesh("SBF_Filthy_Body", base_rig, red, base_handoff)
    select_character(base_rig, base_mesh)
    parsed = variant_authoring.handoff_from_armature(base_rig)
    require(parsed == base_handoff, parsed)
    state = variant_authoring.adopt_selected_as_family_base(bpy.context)
    require(len(state["variants"]) == 1, state)
    require(state["shared"]["socketPolicy"] == model.SOCKET_POLICY, state)

    shared = make_shared_action(base_rig)
    state = model.register_shared_actions(
        variant_authoring.load_state(required=True),
        ["clip_shared_walk"],
    )
    variant_authoring.store_state(state)

    output = Path(tempfile.mkdtemp(prefix="daf_variant_acceptance_"))
    sooted_handoff = appearance_handoff("sooted", "Sooted")
    sooted_rig = make_canonical_armature("SBF_Sooted_Rig")
    sooted_mesh = make_mesh("SBF_Sooted_Body", sooted_rig, gray, sooted_handoff)
    select_character(sooted_rig, sooted_mesh)
    variant_glb = output / "synthetic_bandit_sooted.glb"
    exported = bpy.ops.export_scene.gltf(
        filepath=str(variant_glb),
        export_format="GLB",
        use_selection=True,
        export_extras=True,
        export_animations=False,
    )
    require("FINISHED" in exported, "Could not create a synthetic Skin & Bones GLB.")
    Path(str(variant_glb) + ".sbf.json").write_text(
        json.dumps({"appearance_family": sooted_handoff}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    sooted_mesh_data = sooted_mesh.data
    sooted_rig_data = sooted_rig.data
    bpy.data.objects.remove(sooted_mesh, do_unlink=True)
    bpy.data.objects.remove(sooted_rig, do_unlink=True)
    bpy.data.meshes.remove(sooted_mesh_data)
    bpy.data.armatures.remove(sooted_rig_data)
    active = variant_authoring.import_appearance_variant(bpy.context, variant_glb)
    state = variant_authoring.load_state(required=True)
    sooted_rig = bpy.data.objects[state["variants"][1]["appearance"]["armatureName"]]
    sooted_mesh = bpy.data.objects[state["variants"][1]["appearance"]["meshNames"][0]]
    require(active["variantId"] == "sooted", active)
    inventory_before_rejected_import = {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "armatures": len(bpy.data.armatures),
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
    }
    try:
        variant_authoring.import_appearance_variant(bpy.context, variant_glb)
    except (RuntimeError, ValueError) as exc:
        require("already belongs" in str(exc), exc)
    else:
        raise RuntimeError("A duplicate Skin & Bones variant identity was accepted.")
    require(
        inventory_before_rejected_import
        == {
            "objects": len(bpy.data.objects),
            "meshes": len(bpy.data.meshes),
            "armatures": len(bpy.data.armatures),
            "materials": len(bpy.data.materials),
            "images": len(bpy.data.images),
        },
        "Rejected variant import left orphaned Blender data.",
    )
    require(base_mesh.hide_get(), "Base appearance stayed visible after switching.")
    require(not sooted_mesh.hide_get(), "Active Sooted appearance is hidden.")
    require(len(bpy.data.actions) == 1, "Adding an appearance duplicated Actions.")
    require(
        variant_authoring.effective_actions([shared]) == [shared],
        "Fresh appearance did not inherit the shared Action.",
    )

    select_character(base_rig, base_mesh)
    animation_library.select_action(bpy.context.scene.daf_settings, shared)
    override = variant_authoring.create_action_override(bpy.context, shared)
    require(len(bpy.data.actions) == 2, "One override did not create exactly one Action.")
    require(variant_authoring.action_status(override) == "OVERRIDE", override)
    state = variant_authoring.load_state(required=True)
    require(
        model.resolve_action_id(state, "clip_shared_walk", "sooted")[0]
        == override[animation_library.CLIP_ID_PROPERTY],
        state,
    )
    override["dsb_approved"] = True
    override["dsb_draft"] = False
    override.name = "DSB_Walk_Sooted_Override_v001"
    variant_authoring.switch_variant("filthy")
    shared_curve = animation_library.iter_action_fcurves(shared)[0]
    override_curve = animation_library.iter_action_fcurves(override)[0]
    override_value_before_shared_edit = float(override_curve.keyframe_points[1].co[1])
    revision_before_shared_edit = variant_authoring.export_provenance()[
        "effectiveForgeRevision"
    ]
    shared_curve.keyframe_points[1].co[1] += 0.035
    revision_after_shared_edit = variant_authoring.export_provenance()[
        "effectiveForgeRevision"
    ]
    require(
        revision_before_shared_edit != revision_after_shared_edit,
        "Shared Action edits did not advance resolved export provenance.",
    )
    require(
        float(override_curve.keyframe_points[1].co[1])
        == override_value_before_shared_edit,
        "Editing the shared Action mutated the variant override.",
    )
    require(
        base_rig.animation_data.action == shared,
        "Base appearance did not receive the resolved shared Action.",
    )
    variant_authoring.switch_variant("sooted")
    require(
        sooted_rig.animation_data is not None
        and sooted_rig.animation_data.action == override,
        "Active appearance did not receive the resolved Action override.",
    )

    blend = output / "character_variant_family.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    reopened = variant_authoring.load_state(required=True)
    require(reopened["activeVariantId"] == "sooted", reopened)
    reopened_override = animation_library.find_action_by_clip_id(
        model.resolve_action_id(reopened, "clip_shared_walk", "sooted")[0]
    )
    require(reopened_override is not None, "Save/reopen lost the variant Action override.")
    require(len(bpy.data.actions) == 2, "Save/reopen silently duplicated Actions.")

    select_character(bpy.data.objects["SBF_Filthy_Rig"], bpy.data.objects["SBF_Filthy_Body"])
    animation_library.select_action(bpy.context.scene.daf_settings, reopened_override)
    restored = variant_authoring.revert_action_override(bpy.context, reopened_override)
    require(
        restored is not None
        and restored.get(animation_library.CLIP_ID_PROPERTY) == "clip_shared_walk",
        "Revert did not restore shared Action.",
    )
    require(len(bpy.data.actions) == 1, "Revert left a physical override Action behind.")
    require(
        model.resolve_action_id(
            variant_authoring.load_state(required=True),
            "clip_shared_walk",
            "sooted",
        )
        == ("clip_shared_walk", "INHERITED"),
        "Revert did not restore live inheritance.",
    )

    report = {
        "status": "PASS",
        "blenderVersion": bpy.app.version_string,
        "familyId": reopened["familyId"],
        "variantCount": len(reopened["variants"]),
        "defaultActionCopies": 0,
        "singleOverrideCopies": 1,
        "saveReopen": True,
        "activeSwitching": True,
        "revert": True,
        "socketPolicy": reopened["shared"]["socketPolicy"],
    }
    (output / "character_variant_family_acceptance.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("CHARACTER_VARIANT_FAMILY_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
