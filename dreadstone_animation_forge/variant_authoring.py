"""Blender persistence, copy-on-write operations, and export staging for variants."""

from __future__ import annotations

import copy
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from . import animation_library
from . import variant_family as model
from .anatomy import skin_and_bones as sbf_handoff
from .deformation import progressive_sites, serialization


FAMILY_STATE_PROPERTY = "dsb_character_variant_family_json"
ACTION_SCOPE_PROPERTY = "dsb_variant_action_scope"
ACTION_FAMILY_PROPERTY = "dsb_variant_family_id"
ACTION_VARIANT_PROPERTY = "dsb_variant_owner_id"
ACTION_SHARED_ID_PROPERTY = "dsb_variant_shared_action_id"
ACTION_OVERRIDE_ID_PROPERTY = "dsb_variant_override_action_id"
OBJECT_VARIANT_PROPERTY = "dsb_appearance_variant_id"
OBJECT_FAMILY_PROPERTY = "dsb_appearance_family_id"
PROVENANCE_PROPERTY = "dsb_character_variant_provenance"
ACTIVE_EXPORT_PROPERTY = "dsb_active_appearance_variant_id"


def _scene(scene=None):
    return scene or getattr(bpy.context, "scene", None)


def load_state(scene=None, *, required=False):
    scene = _scene(scene)
    raw = str(scene.get(FAMILY_STATE_PROPERTY, "")) if scene is not None else ""
    if not raw:
        if required:
            raise RuntimeError(
                "No Character Variant Family exists. Adopt an approved Skin & Bones appearance first."
            )
        return None
    try:
        return model.normalize_family(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        if required:
            raise RuntimeError(f"Character Variant Family state is unreadable: {exc}") from exc
        return None


def store_state(state, scene=None):
    scene = _scene(scene)
    if scene is None:
        raise RuntimeError("No Blender scene is available for Character Variant Family state.")
    state = model.normalize_family(state)
    encoded = model.stable_json(state)
    scene[FAMILY_STATE_PROPERTY] = encoded
    for name in ("DSB_DAMAGE_RIG",):
        owner = bpy.data.objects.get(name)
        if owner is not None:
            owner[FAMILY_STATE_PROPERTY] = encoded
    settings = getattr(scene, "daf_settings", None)
    if settings is not None:
        settings.variant_family_status = (
            f"ACTIVE — {model.variant_by_id(state)['displayName']}"
        )
    return state


def recover_state(scene=None):
    """Recover scene state from the runtime rig after unusual scene duplication."""

    scene = _scene(scene)
    if scene is None or scene.get(FAMILY_STATE_PROPERTY, ""):
        return load_state(scene)
    for owner in bpy.data.objects:
        raw = str(owner.get(FAMILY_STATE_PROPERTY, ""))
        if not raw:
            continue
        try:
            state = model.normalize_family(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        return store_state(state, scene)
    return None


def _owner_candidates(armature):
    seen = set()
    candidates = [armature, getattr(armature, "data", None)]
    candidates.extend(getattr(armature, "children_recursive", ()) or ())
    candidates.extend(getattr(armature, "children", ()) or ())
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in obj.modifiers
        ):
            candidates.extend((obj, getattr(obj, "data", None)))
    for owner in candidates:
        if owner is None:
            continue
        identity = owner.as_pointer() if hasattr(owner, "as_pointer") else id(owner)
        if identity in seen:
            continue
        seen.add(identity)
        yield owner


def handoff_from_armature(armature, *, require_approved=True):
    """Read and cross-check the shipped Skin & Bones node extras."""

    records = []
    for owner in _owner_candidates(armature):
        raw = owner.get(model.SBF_HANDOFF_PROPERTY, "")
        if not raw:
            continue
        scalars = {
            name: owner.get(name, "")
            for name in (
                model.SBF_FAMILY_ID_PROPERTY,
                model.SBF_VARIANT_ID_PROPERTY,
                model.SBF_BODY_FINGERPRINT_PROPERTY,
            )
        }
        try:
            records.append(
                model.require_handoff(
                    raw,
                    scalars,
                    require_approved=require_approved,
                )
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
    if not records:
        raise RuntimeError(
            "The selected character has no Skin & Bones "
            "skin-and-bones-appearance-family-handoff-v1 metadata. "
            "Export it from Skin & Bones Forge 2.2.0+."
        )
    canonical = model.stable_json(records[0])
    if any(model.stable_json(record) != canonical for record in records[1:]):
        raise RuntimeError(
            "Skin & Bones mesh and armature appearance-family handoffs disagree."
        )
    return records[0]


def _manifest_handoff(filepath):
    path = Path(filepath)
    manifest = Path(str(path) + ".sbf.json")
    if not manifest.is_file():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        return model.require_handoff(payload.get("appearance_family"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Skin & Bones sibling manifest is invalid: {exc}") from exc


def _rig_contract(armature):
    return sbf_handoff.require_canonical_yplus(
        armature,
        label="Character Variant Family ingest",
    )


def _armature_objects(armature, candidates=None):
    candidates = list(candidates) if candidates is not None else list(bpy.context.scene.objects)
    result = {armature}
    for obj in candidates:
        if obj == armature:
            result.add(obj)
            continue
        current = getattr(obj, "parent", None)
        while current is not None:
            if current == armature:
                result.add(obj)
                break
            current = getattr(current, "parent", None)
        if obj.type == "MESH" and any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in obj.modifiers
        ):
            result.add(obj)
    for obj in list(result):
        current = getattr(obj, "parent", None)
        while current is not None:
            result.add(current)
            current = getattr(current, "parent", None)
    return sorted(result, key=lambda value: value.name.lower())


def _material_record(material):
    if material is None:
        return {"material": "", "baseColorImages": []}
    images = []
    node_tree = getattr(material, "node_tree", None)
    if node_tree is not None:
        for node in node_tree.nodes:
            image = getattr(node, "image", None)
            if image is not None and image.name not in images:
                images.append(image.name)
    return {"material": material.name, "baseColorImages": images}


def capture_appearance(armature, objects=None):
    objects = _armature_objects(armature, objects)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    meshes.sort(
        key=lambda obj: (
            -len(obj.data.vertices),
            -len(obj.data.polygons),
            obj.name.lower(),
        )
    )
    palette = []
    if meshes:
        palette = [_material_record(value) for value in meshes[0].data.materials]
    return {
        "armatureName": armature.name,
        "objectNames": [obj.name for obj in objects],
        "meshNames": [obj.name for obj in meshes],
        "materialPalette": palette,
        "meshContracts": [
            {
                "object": obj.name,
                "vertexCount": len(obj.data.vertices),
                "polygonCount": len(obj.data.polygons),
                "materials": [_material_record(value) for value in obj.data.materials],
            }
            for obj in meshes
        ],
    }


def _find_selected_armature(context):
    candidates = set()
    for obj in list(context.selected_objects) + [context.active_object]:
        if obj is None:
            continue
        if obj.type == "ARMATURE":
            candidates.add(obj)
        if obj.type == "MESH":
            for modifier in obj.modifiers:
                if modifier.type == "ARMATURE" and modifier.object is not None:
                    candidates.add(modifier.object)
        current = getattr(obj, "parent", None)
        while current is not None:
            if current.type == "ARMATURE":
                candidates.add(current)
            current = getattr(current, "parent", None)
    if len(candidates) != 1:
        raise RuntimeError(
            "Select exactly one imported Skin & Bones character mesh or armature."
        )
    return next(iter(candidates))


def _stamp_variant_objects(state):
    for variant in state.get("variants", []):
        for name in variant.get("appearance", {}).get("objectNames", []):
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            obj[OBJECT_FAMILY_PROPERTY] = state["familyId"]
            obj[OBJECT_VARIANT_PROPERTY] = variant["variantId"]


def _appearance_body_objects():
    roles = {
        "body_core",
        "attached_segment",
        "detached_segment",
        "detached_upper_body",
        "detached_lower_body",
    }
    return [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and str(obj.get("dsb_damage_role", "")) in roles
    ]


def _apply_material_palette(variant):
    palette = variant.get("appearance", {}).get("materialPalette", [])
    materials = [
        bpy.data.materials.get(str(record.get("material", "")))
        for record in palette
    ]
    if not materials:
        return 0
    changed = 0
    for obj in _appearance_body_objects():
        slots = obj.data.materials
        for index in range(min(len(slots), len(materials))):
            material = materials[index]
            if material is not None and slots[index] != material:
                slots[index] = material
                changed += 1
    return changed


def _has_damage_authoring():
    rig = bpy.data.objects.get("DSB_DAMAGE_RIG")
    return rig is not None and bool(rig.get("dsb_damage_generated", False))


def switch_variant(variant_id, scene=None):
    scene = _scene(scene)
    state = model.set_active_variant(load_state(scene, required=True), variant_id)
    active = model.variant_by_id(state)
    damage_built = _has_damage_authoring()
    for variant in state["variants"]:
        show = variant["variantId"] == active["variantId"] and not damage_built
        for name in variant.get("appearance", {}).get("objectNames", []):
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            try:
                obj.hide_set(not show)
            except RuntimeError:
                pass
            obj.hide_render = not show
    _apply_material_palette(active)
    store_state(state, scene)
    effective_action = _select_effective_action(scene)
    if effective_action is not None:
        rig_names = {
            str(active.get("appearance", {}).get("armatureName", "")),
            "DSB_DAMAGE_RIG" if damage_built else "",
        }
        for rig_name in rig_names:
            rig = bpy.data.objects.get(rig_name)
            if rig is None or rig.type != "ARMATURE":
                continue
            if rig.animation_data is None:
                rig.animation_data_create()
            rig.animation_data.action = effective_action
    settings = getattr(scene, "daf_settings", None)
    if settings is not None:
        settings.variant_shared_damage_edit_enabled = False
        settings.variant_family_status = f"VIEWING — {active['displayName']}"
    return active


def adopt_selected_as_family_base(context):
    if load_state(context.scene) is not None:
        raise RuntimeError(
            "This Blend file already owns a Character Variant Family. Add a compatible appearance instead."
        )
    armature = _find_selected_armature(context)
    handoff = handoff_from_armature(armature)
    contract = _rig_contract(armature)
    appearance = capture_appearance(armature)
    try:
        state = model.new_family(handoff, contract, appearance=appearance)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    action_ids = []
    for action in animation_library.character_actions(armature, include_drafts=False):
        if not bool(action.get("dsb_approved", False)):
            continue
        clip_id = animation_library.ensure_clip_id(action)
        action[ACTION_SCOPE_PROPERTY] = model.ACTION_SCOPE_SHARED
        action[ACTION_FAMILY_PROPERTY] = state["familyId"]
        action[ACTION_SHARED_ID_PROPERTY] = clip_id
        action_ids.append(clip_id)
    state = model.register_shared_actions(state, action_ids)
    _stamp_variant_objects(state)
    store_state(state, context.scene)
    switch_variant(handoff["variant_id"], context.scene)
    return state


def _remove_imported_objects(objects):
    for obj in reversed(list(objects)):
        if obj is None or obj.name not in bpy.data.objects:
            continue
        object_type = str(obj.type)
        data = getattr(obj, "data", None)
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0:
            collection = (
                bpy.data.meshes
                if object_type == "MESH"
                else bpy.data.armatures
                if object_type == "ARMATURE"
                else None
            )
            if collection is not None:
                try:
                    collection.remove(data)
                except (ReferenceError, RuntimeError):
                    pass


def _rollback_variant_import(imported, before_data, original_state, scene):
    _remove_imported_objects(imported)
    for collection, existing in before_data:
        for datablock in list(set(collection) - existing):
            if getattr(datablock, "users", 1) != 0:
                continue
            try:
                collection.remove(datablock)
            except (ReferenceError, RuntimeError):
                pass
    store_state(original_state, scene)
    switch_variant(original_state["activeVariantId"], scene)


def import_appearance_variant(context, filepath):
    path = Path(bpy.path.abspath(str(filepath)))
    if not path.is_file() or path.suffix.lower() not in {".glb", ".gltf"}:
        raise RuntimeError("Choose a Skin & Bones .glb or .gltf appearance export.")
    original_state = load_state(context.scene, required=True)
    state = original_state
    before = set(bpy.data.objects)
    before_data = [
        (bpy.data.meshes, set(bpy.data.meshes)),
        (bpy.data.armatures, set(bpy.data.armatures)),
        (bpy.data.materials, set(bpy.data.materials)),
        (bpy.data.images, set(bpy.data.images)),
    ]
    try:
        result = bpy.ops.import_scene.gltf(filepath=str(path))
    except Exception:
        imported = sorted(
            set(bpy.data.objects) - before,
            key=lambda obj: obj.name.lower(),
        )
        _rollback_variant_import(
            imported,
            before_data,
            original_state,
            context.scene,
        )
        raise
    if "FINISHED" not in result:
        imported = sorted(
            set(bpy.data.objects) - before,
            key=lambda obj: obj.name.lower(),
        )
        _rollback_variant_import(
            imported,
            before_data,
            original_state,
            context.scene,
        )
        raise RuntimeError("Blender did not finish importing the appearance variant.")
    imported = sorted(set(bpy.data.objects) - before, key=lambda obj: obj.name.lower())
    try:
        armatures = [obj for obj in imported if obj.type == "ARMATURE"]
        if len(armatures) != 1:
            raise RuntimeError(
                "A variant appearance export must contain exactly one Skin & Bones armature."
            )
        armature = armatures[0]
        handoff = handoff_from_armature(armature)
        manifest_handoff = _manifest_handoff(path)
        if (
            manifest_handoff is not None
            and model.stable_json(manifest_handoff) != model.stable_json(handoff)
        ):
            raise RuntimeError(
                "Skin & Bones GLB extras disagree with the sibling .glb.sbf.json appearance_family record."
            )
        contract = _rig_contract(armature)
        appearance = capture_appearance(armature, imported)
        state = model.add_variant(
            state,
            handoff,
            contract,
            appearance=appearance,
        )
        _stamp_variant_objects(state)
        store_state(state, context.scene)
        switch_variant(handoff["variant_id"], context.scene)
        return model.variant_by_id(state, handoff["variant_id"])
    except Exception as exc:
        _rollback_variant_import(
            imported,
            before_data,
            original_state,
            context.scene,
        )
        if isinstance(exc, ValueError):
            raise RuntimeError(str(exc)) from exc
        raise


def mark_action_for_family(action, armature=None, scene=None):
    """New approved content joins the shared layer unless already an override."""

    scene = _scene(scene)
    state = load_state(scene)
    if state is None or bool(action.get("dsb_draft", False)):
        return action
    scope = str(action.get(ACTION_SCOPE_PROPERTY, ""))
    if scope == model.ACTION_SCOPE_OVERRIDE:
        action[ACTION_FAMILY_PROPERTY] = state["familyId"]
        return action
    clip_id = animation_library.ensure_clip_id(action)
    action[ACTION_SCOPE_PROPERTY] = model.ACTION_SCOPE_SHARED
    action[ACTION_FAMILY_PROPERTY] = state["familyId"]
    action[ACTION_SHARED_ID_PROPERTY] = clip_id
    state = model.register_shared_actions(
        state,
        list(state["shared"].get("actionIds", [])) + [clip_id],
    )
    store_state(state, scene)
    return action


def action_status(action, scene=None):
    state = load_state(scene)
    if state is None or action is None:
        return "STANDALONE"
    scope = str(action.get(ACTION_SCOPE_PROPERTY, ""))
    if scope == model.ACTION_SCOPE_OVERRIDE:
        return "OVERRIDE"
    shared_id = str(
        action.get(ACTION_SHARED_ID_PROPERTY, "")
        or action.get(animation_library.CLIP_ID_PROPERTY, "")
    )
    if shared_id in set(state["shared"].get("actionIds", [])):
        return (
            "SHARED"
            if state["activeVariantId"] == state["baseVariantId"]
            else "INHERITED"
        )
    return "STANDALONE"


def effective_actions(actions, scene=None):
    state = load_state(scene)
    if state is None:
        return list(actions)
    variant = model.variant_by_id(state)
    overrides = variant.get("actionOverrides", {})
    by_id = {
        str(action.get(animation_library.CLIP_ID_PROPERTY, "")): action
        for action in bpy.data.actions
        if str(action.get(animation_library.CLIP_ID_PROPERTY, ""))
    }
    result = []
    for action in actions:
        scope = str(action.get(ACTION_SCOPE_PROPERTY, ""))
        owner_variant = str(action.get(ACTION_VARIANT_PROPERTY, ""))
        if scope == model.ACTION_SCOPE_OVERRIDE:
            if owner_variant == variant["variantId"]:
                result.append(action)
            continue
        shared_id = str(
            action.get(ACTION_SHARED_ID_PROPERTY, "")
            or action.get(animation_library.CLIP_ID_PROPERTY, "")
        )
        replacement = overrides.get(shared_id)
        if replacement:
            override = by_id.get(str(replacement.get("overrideActionId", "")))
            if override is not None and override not in result:
                result.append(override)
            continue
        result.append(action)
    return list(dict.fromkeys(result))


def _shared_action(action, state):
    if str(action.get(ACTION_SCOPE_PROPERTY, "")) == model.ACTION_SCOPE_OVERRIDE:
        shared_id = str(action.get(ACTION_SHARED_ID_PROPERTY, ""))
    else:
        shared_id = str(
            action.get(ACTION_SHARED_ID_PROPERTY, "")
            or action.get(animation_library.CLIP_ID_PROPERTY, "")
        )
    source = animation_library.find_action_by_clip_id(shared_id)
    if source is None:
        raise RuntimeError("The shared family Action for this logical clip is missing.")
    if shared_id not in set(state["shared"].get("actionIds", [])):
        raise RuntimeError("The selected Action is not registered in the shared family layer.")
    return source, shared_id


def create_action_override(context, action):
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    source, shared_id = _shared_action(action, state)
    if shared_id in variant.get("actionOverrides", {}):
        raise RuntimeError("This appearance variant already overrides the selected Action.")
    if context.scene.daf_settings.animation_library_edit_source_clip_id:
        raise RuntimeError("Finish or cancel the current animation edit first.")
    from . import DRAFT_ACTION_NAMES

    kind = animation_library.infer_action_kind(source)
    draft_name = DRAFT_ACTION_NAMES.get(kind, "DSB_DRAFT_Variant_Edit")
    if bpy.data.actions.get(draft_name) is not None:
        raise RuntimeError(
            f"Finish or delete the existing draft {draft_name!r} before creating an override."
        )
    override = source.copy()
    override.name = draft_name
    override_id = "clip_" + uuid.uuid4().hex
    override[animation_library.CLIP_ID_PROPERTY] = override_id
    override[ACTION_SCOPE_PROPERTY] = model.ACTION_SCOPE_OVERRIDE
    override[ACTION_FAMILY_PROPERTY] = state["familyId"]
    override[ACTION_VARIANT_PROPERTY] = variant["variantId"]
    override[ACTION_SHARED_ID_PROPERTY] = shared_id
    override[ACTION_OVERRIDE_ID_PROPERTY] = override_id
    override["dsb_draft"] = True
    override["dsb_approved"] = False
    override["dsb_draft_kind"] = kind
    if override.get("dsb_offensive_action_json"):
        override["dsb_offensive_previewed"] = False
        override["dsb_offensive_preview_count"] = 0
        for name in (
            "dsb_offensive_previewed_before_approval",
            "dsb_offensive_character_recipe",
        ):
            if name in override:
                del override[name]
    override.use_fake_user = True
    if context.active_object is not None:
        try:
            armature = _find_selected_armature(context)
        except RuntimeError:
            armature = bpy.data.objects.get("DSB_DAMAGE_RIG")
    else:
        armature = bpy.data.objects.get("DSB_DAMAGE_RIG")
    if armature is None or armature.type != "ARMATURE":
        raise RuntimeError("Select the active family armature before creating an override.")
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = override
    state = model.set_action_override(
        state,
        shared_id,
        override_id,
        variant["variantId"],
    )
    store_state(state, context.scene)
    animation_library.select_action(context.scene.daf_settings, override)
    context.scene.daf_settings.animation_library_status = (
        f"VARIANT OVERRIDE DRAFT — {variant['displayName']} / {source.name}"
    )
    return override


def revert_action_override(context, action):
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    _source, shared_id = _shared_action(action, state)
    record = variant.get("actionOverrides", {}).get(shared_id)
    if not record:
        raise RuntimeError("The selected Action is inherited; there is no override to revert.")
    override = animation_library.find_action_by_clip_id(record["overrideActionId"])
    state, _removed = model.remove_action_override(
        state,
        shared_id,
        variant["variantId"],
    )
    if override is not None:
        animation_library._remove_action(override, unlink_nla=True)
    store_state(state, context.scene)
    source = animation_library.find_action_by_clip_id(shared_id)
    if source is not None:
        animation_library.select_action(context.scene.daf_settings, source)
    return source


def _select_effective_action(scene):
    settings = getattr(scene, "daf_settings", None)
    state = load_state(scene)
    if settings is None or state is None:
        return None
    selected = animation_library.find_action_by_clip_id(
        str(settings.animation_library_active_clip_id)
    )
    if selected is None:
        return None
    shared_id = str(
        selected.get(ACTION_SHARED_ID_PROPERTY, "")
        or selected.get(animation_library.CLIP_ID_PROPERTY, "")
    )
    effective_id, _status = model.resolve_action_id(state, shared_id)
    effective = animation_library.find_action_by_clip_id(effective_id)
    if effective is not None:
        animation_library.select_action(settings, effective)
    return effective


def require_regular_action_edit_allowed(action, scene=None):
    state = load_state(scene)
    if state is None or action_status(action, scene) != "INHERITED":
        return
    raise RuntimeError(
        "This is an INHERITED family Action. Use CREATE VARIANT OVERRIDE, or use "
        "EDIT SHARED FAMILY ACTION and confirm the family-wide edit."
    )


def _deformation():
    from . import deformation_authoring

    return deformation_authoring


def _physical_damage_records(region_id=None):
    deformation = _deformation()
    registry = deformation._load_registry(migrate_legacy=False)
    records = []
    for region in registry.get("regions", []):
        if region_id is not None and str(region.get("regionId", "")) != str(region_id):
            continue
        attached, _detached = deformation._resolve_region_pair(region)
        payload = deformation._metadata(attached)
        for name, entry in payload.get("keys", {}).items():
            if deformation._key(attached, name) is None:
                continue
            records.append(
                {
                    "name": name,
                    "damageKeyId": str(entry.get("damageKeyId", "")),
                    "regionId": str(region.get("regionId", "")),
                    "ownerVariantId": str(entry.get("ownerVariantId", "")),
                    "sharedDamageKeyId": str(entry.get("sharedDamageKeyId", "")),
                    "entry": entry,
                }
            )
    return records


def effective_damage_key_names(region_id, names):
    state = load_state()
    if state is None:
        return list(names)
    by_name = {record["name"]: record for record in _physical_damage_records(region_id)}
    records = [by_name[name] for name in names if name in by_name]
    return model.effective_damage_key_names(state, region_id, records)


def effective_progressive_collection(collection):
    state = load_state()
    if state is None:
        return copy.deepcopy(collection)
    result = copy.deepcopy(collection)
    result["sites"] = model.effective_progressive_sites(
        state,
        result.get("sites", []),
    )
    active = str(result.get("activeSiteGuid", ""))
    visible = {str(site.get("siteGuid", "")) for site in result["sites"]}
    if active not in visible:
        result["activeSiteGuid"] = next(iter(visible), "")
    result["siteCount"] = len(result["sites"])
    return result


def merge_progressive_collection(full_collection, effective_collection):
    """Persist edits to visible records without deleting hidden variant records."""

    state = load_state()
    if state is None:
        return copy.deepcopy(effective_collection)
    result = copy.deepcopy(full_collection)
    original_effective = model.effective_progressive_sites(
        state,
        full_collection.get("sites", []),
    )
    before_visible = {
        str(site.get("siteGuid", "")): site for site in original_effective
    }
    after_visible = {
        str(site.get("siteGuid", "")): site
        for site in effective_collection.get("sites", [])
    }
    settings = getattr(bpy.context.scene, "daf_settings", None)
    shared_edit_enabled = bool(
        getattr(settings, "variant_shared_damage_edit_enabled", False)
    )
    active_variant = model.variant_by_id(state)["variantId"]
    for guid in sorted(set(before_visible) | set(after_visible)):
        before = before_visible.get(guid)
        after = after_visible.get(guid)
        if before is not None and after is not None:
            if model.stable_json(before) == model.stable_json(after):
                continue
            owner = str(before.get("ownerVariantId", ""))
            if owner == active_variant or shared_edit_enabled:
                continue
            raise RuntimeError(
                "This Progressive Site is INHERITED. Create a variant override "
                "or explicitly unlock shared family Damage editing."
            )
        if before is None and after is not None:
            owner = str(after.get("ownerVariantId", ""))
            if owner == active_variant or shared_edit_enabled:
                continue
            raise RuntimeError(
                "Creating a shared Progressive Site requires explicit shared "
                "family Damage editing."
            )
        owner = str(before.get("ownerVariantId", ""))
        if owner == active_variant:
            raise RuntimeError(
                "Use REVERT TO SHARED to remove a variant Progressive Site override."
            )
        if not shared_edit_enabled:
            raise RuntimeError(
                "Deleting a shared Progressive Site requires explicit shared "
                "family Damage editing."
            )
    by_guid = {
        str(site.get("siteGuid", "")): copy.deepcopy(site)
        for site in result.get("sites", [])
    }
    visible_before = set(before_visible)
    visible_after = {
        str(site.get("siteGuid", ""))
        for site in effective_collection.get("sites", [])
    }
    for deleted_guid in visible_before - visible_after:
        by_guid.pop(deleted_guid, None)
    for site in effective_collection.get("sites", []):
        by_guid[str(site.get("siteGuid", ""))] = copy.deepcopy(site)
    result.update(
        {
            key: copy.deepcopy(value)
            for key, value in effective_collection.items()
            if key not in {"sites", "siteCount"}
        }
    )
    result["sites"] = list(by_guid.values())
    result["siteCount"] = len(result["sites"])
    return result


def _copy_shape_key(source, target):
    if len(source.data) != len(target.data):
        raise RuntimeError("Damage Key copy-on-write point counts differ.")
    for source_point, target_point in zip(source.data, target.data):
        target_point.co = source_point.co
    target.slider_min = source.slider_min
    target.slider_max = source.slider_max
    target.value = 0.0
    target.mute = False


def _unique_override_key_name(source_name, export_identity, suffix=""):
    token = model.safe_identifier(export_identity).replace("-", "_")
    tail = f"__{token}{suffix}"
    return (str(source_name)[: max(1, 63 - len(tail))] + tail)[:63]


def _clone_damage_key(context, shared_id, *, owner_role="DAMAGE_KEY", suffix=""):
    deformation = _deformation()
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    record = next(
        (
            value
            for value in _physical_damage_records()
            if value["damageKeyId"] == str(shared_id)
            and not value["ownerVariantId"]
        ),
        None,
    )
    if record is None:
        raise RuntimeError(f"Shared Damage Key {shared_id!r} is missing.")
    registry = deformation._load_registry(migrate_legacy=False)
    region = next(
        value
        for value in registry.get("regions", [])
        if str(value.get("regionId", "")) == record["regionId"]
    )
    attached, detached = deformation._resolve_region_pair(region)
    source_attached = deformation._key(attached, record["name"])
    source_detached = deformation._key(detached, record["name"]) if detached else None
    previous_region = registry.get("activeRegionId", "")
    deformation._set_active_region(record["regionId"], context)
    name = _unique_override_key_name(
        record["name"],
        variant["exportIdentity"],
        suffix,
    )
    if deformation._key(attached, name) is not None:
        raise RuntimeError(f"Variant Damage Key {name!r} already exists.")
    entry = copy.deepcopy(record["entry"])
    override_id = progressive_sites.opaque_id("damage_key")
    entry.update(
        {
            "name": name,
            "damageKeyId": override_id,
            "ownerVariantId": variant["variantId"],
            "sharedDamageKeyId": record["damageKeyId"],
            "variantOwnerRole": owner_role,
            "status": "VARIANT_OVERRIDE_DRAFT",
            "validationStatus": "NOT_VALIDATED",
            "previewEnabled": False,
        }
    )
    for field in (
        "goreGeneratedMeshIds",
        "goreGeneratedNodeNames",
        "goreGeometryDigests",
        "goreGenerationDigests",
        "goreTriangleCounts",
        "goreValidationMeasurements",
    ):
        entry.pop(field, None)
    try:
        _attached, _detached, target_attached, target_detached = deformation._ensure_key_pair(
            name,
            metadata_entry=entry,
        )
        _copy_shape_key(source_attached, target_attached)
        if detached is not None:
            _copy_shape_key(source_detached, target_detached)
            deformation._link_detached_value(attached, detached, name)
        payload = deformation._metadata(attached)
        payload["keys"][name] = entry
        overlay = entry.get("surfaceGoreOverlay")
        if isinstance(overlay, dict):
            try:
                normalized = deformation.trauma_field.normalize_gore_overlay(overlay)
                if normalized.get("goreOverlayEnabled") and normalized.get("goreRaisedEnabled"):
                    deformation.rebuild_raised_gore_for_key(
                        region,
                        attached,
                        detached,
                        name,
                        entry,
                    )
            except (TypeError, ValueError):
                pass
        deformation._store_metadata(attached, detached, payload)
    except Exception:
        deformation._remove_generated_gore_objects(record["regionId"], name)
        deformation._remove_key(attached, name)
        if detached is not None:
            deformation._remove_key(detached, name)
        raise
    finally:
        if previous_region and previous_region != record["regionId"]:
            deformation._set_active_region(previous_region, context)
    return {
        "sharedDamageKeyId": record["damageKeyId"],
        "sharedName": record["name"],
        "overrideDamageKeyId": override_id,
        "overrideName": name,
        "regionId": record["regionId"],
        "ownerVariantId": variant["variantId"],
        "ownerRole": owner_role,
    }


def create_damage_key_override(context):
    settings = context.scene.daf_settings
    deformation = _deformation()
    _registry, region, attached, _detached = deformation._resolve_active_region(context)
    name = str(settings.deformation_active_key)
    entry = deformation._metadata(attached).get("keys", {}).get(name)
    if not entry:
        raise RuntimeError("Select an inherited Damage Key first.")
    if entry.get("ownerVariantId"):
        raise RuntimeError("The selected Damage Key is already a variant override.")
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    shared_id = str(entry.get("damageKeyId", ""))
    if shared_id in variant.get("damageKeyOverrides", {}):
        raise RuntimeError("This appearance already overrides the selected Damage Key.")
    record = _clone_damage_key(context, shared_id)
    state = model.set_damage_key_override(state, record, variant["variantId"])
    store_state(state, context.scene)
    deformation._set_active_region(record["regionId"], context)
    deformation._select_key(settings, record["overrideName"])
    settings.variant_family_status = f"DAMAGE OVERRIDE — {record['overrideName']}"
    return record


def _delete_variant_damage_key(record):
    deformation = _deformation()
    registry = deformation._load_registry(migrate_legacy=False)
    region = next(
        (
            value
            for value in registry.get("regions", [])
            if str(value.get("regionId", "")) == str(record.get("regionId", ""))
        ),
        None,
    )
    if region is None:
        return
    attached, detached = deformation._resolve_region_pair(region)
    name = str(record.get("overrideName", ""))
    deformation._remove_generated_gore_objects(record.get("regionId"), name)
    deformation._remove_key(attached, name)
    if detached is not None:
        deformation._remove_key(detached, name)
    payload = deformation._metadata(attached)
    payload.get("keys", {}).pop(name, None)
    deformation._store_metadata(attached, detached, payload)


def revert_damage_key_override(context):
    settings = context.scene.daf_settings
    deformation = _deformation()
    _registry, _region, attached, _detached = deformation._resolve_active_region(context)
    entry = deformation._metadata(attached).get("keys", {}).get(
        str(settings.deformation_active_key), {}
    )
    shared_id = str(entry.get("sharedDamageKeyId", ""))
    if not shared_id:
        raise RuntimeError("The selected Damage Key is inherited; there is no override to revert.")
    state = load_state(context.scene, required=True)
    state, record = model.remove_damage_key_override(state, shared_id)
    if not record:
        raise RuntimeError("The selected Damage Key is not an independent override record.")
    _delete_variant_damage_key(record)
    store_state(state, context.scene)
    deformation._set_active_region(record["regionId"], context)
    deformation._select_key(settings, record["sharedName"])
    return record


def _full_progressive_collection():
    deformation = _deformation()
    registry = deformation._load_registry(migrate_legacy=False)
    return registry, progressive_sites.normalize_sites(
        registry.get("progressiveDamageSites")
    )


def create_progressive_site_override(context):
    settings = context.scene.daf_settings
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    registry, collection = _full_progressive_collection()
    shared_guid = str(settings.progression_active_site_guid)
    site = progressive_sites.site_by_guid(collection, shared_guid)
    if site.get("ownerVariantId"):
        raise RuntimeError("The selected Progressive Site is already a variant override.")
    if shared_guid in variant.get("progressiveSiteOverrides", {}):
        raise RuntimeError("This appearance already overrides the selected Progressive Site.")
    plan = model.progressive_clone_plan(site, _physical_damage_records())
    if plan["errors"]:
        raise RuntimeError(" ".join(plan["errors"]))
    owned = []
    try:
        for index, key_id in enumerate(plan["damageKeyIds"]):
            owned.append(
                _clone_damage_key(
                    context,
                    key_id,
                    owner_role="PROGRESSIVE_SITE",
                    suffix=f"_s{index + 1}",
                )
            )
        mapping = {value["sharedDamageKeyId"]: value for value in owned}
        override = copy.deepcopy(site)
        override_guid = progressive_sites.opaque_id("site")
        override["siteGuid"] = override_guid
        override["siteId"] = progressive_sites.safe_site_id(
            f"{site['siteId']}_{variant['exportIdentity']}"
        )
        override["displayName"] = f"{site['displayName']} — {variant['displayName']}"
        override["ownerVariantId"] = variant["variantId"]
        override["sharedSiteGuid"] = shared_guid
        override["validationStatus"] = "NOT_VALIDATED"
        override["validationDigest"] = ""
        override["enabledForExport"] = False
        for stage_name, stage in override.get("stages", {}).items():
            replacement = mapping.get(str(stage.get("damageKeyId", "")))
            if replacement is None:
                continue
            stage["sharedDamageKeyId"] = str(stage.get("damageKeyId", ""))
            stage["damageKeyId"] = replacement["overrideDamageKeyId"]
            stage["deformationKeyName"] = replacement["overrideName"]
            stage["stageId"] = progressive_sites.opaque_id("stage")
            stage["validationStatus"] = "NOT_VALIDATED"
            stage["ownerVariantId"] = variant["variantId"]
        override = progressive_sites.normalize_site(override)
        collection["sites"].append(override)
        collection["activeSiteGuid"] = override_guid
        collection = progressive_sites.normalize_sites(collection)
        registry["progressiveDamageSites"] = collection
        _deformation()._store_registry(registry)
        record = {
            "sharedSiteGuid": shared_guid,
            "overrideSiteGuid": override_guid,
            "ownerVariantId": variant["variantId"],
            "ownedDamageKeys": owned,
        }
        state = model.set_progressive_site_override(
            state,
            record,
            variant["variantId"],
        )
        store_state(state, context.scene)
        settings.progression_active_site_guid = override_guid
        from . import progressive_authoring

        progressive_authoring.sync_settings_from_site(context, override)
        return record
    except Exception:
        for record in reversed(owned):
            _delete_variant_damage_key(record)
        raise


def revert_progressive_site_override(context):
    settings = context.scene.daf_settings
    state = load_state(context.scene, required=True)
    variant = model.variant_by_id(state)
    active_guid = str(settings.progression_active_site_guid)
    shared_guid = next(
        (
            shared
            for shared, record in variant.get("progressiveSiteOverrides", {}).items()
            if str(record.get("overrideSiteGuid", "")) == active_guid
        ),
        "",
    )
    if not shared_guid:
        raise RuntimeError("The selected Progressive Site is inherited; there is no override to revert.")
    state, record = model.remove_progressive_site_override(state, shared_guid)
    registry, collection = _full_progressive_collection()
    collection["sites"] = [
        site
        for site in collection.get("sites", [])
        if str(site.get("siteGuid", "")) != str(record["overrideSiteGuid"])
    ]
    collection["activeSiteGuid"] = shared_guid
    registry["progressiveDamageSites"] = progressive_sites.normalize_sites(collection)
    _deformation()._store_registry(registry)
    for key_record in reversed(record.get("ownedDamageKeys", [])):
        _delete_variant_damage_key(key_record)
    store_state(state, context.scene)
    settings.progression_active_site_guid = shared_guid
    from . import progressive_authoring

    progressive_authoring.sync_settings_from_site(context)
    return record


def damage_status(context):
    state = load_state(context.scene)
    if state is None:
        return {"status": "STANDALONE", "kind": ""}
    settings = context.scene.daf_settings
    variant = model.variant_by_id(state)
    if str(settings.variant_damage_override_unit) == "PROGRESSIVE_SITE":
        active = str(settings.progression_active_site_guid)
        for shared, record in variant.get("progressiveSiteOverrides", {}).items():
            if active == str(record.get("overrideSiteGuid", "")):
                return {"status": "OVERRIDE", "kind": model.PROGRESSIVE_SITE_KIND, "sharedId": shared}
        return {"status": "INHERITED", "kind": model.PROGRESSIVE_SITE_KIND, "sharedId": active}
    deformation = _deformation()
    try:
        _registry, region, attached, _detached = deformation._resolve_active_region(context)
        name = str(settings.deformation_active_key)
        entry = deformation._metadata(attached).get("keys", {}).get(name, {})
    except Exception:
        return {"status": "NONE", "kind": model.DAMAGE_KEY_KIND}
    if str(entry.get("ownerVariantId", "")) == variant["variantId"]:
        return {
            "status": "OVERRIDE",
            "kind": model.DAMAGE_KEY_KIND,
            "sharedId": str(entry.get("sharedDamageKeyId", "")),
            "name": name,
        }
    return {
        "status": "INHERITED",
        "kind": model.DAMAGE_KEY_KIND,
        "sharedId": str(entry.get("damageKeyId", "")),
        "name": name,
        "regionId": str(region.get("regionId", "")),
    }


def damage_object_is_effective(obj):
    state = load_state()
    if state is None:
        return True
    key_name = str(
        obj.get("dsb_gore_deformation_key", "")
        or obj.get("dsb_stain_deformation_key", "")
    )
    region_id = str(
        obj.get("dsb_gore_region_id", "")
        or obj.get("dsb_stain_region_id", "")
    )
    if not key_name:
        return True
    effective = set(
        effective_damage_key_names(
            region_id,
            [record["name"] for record in _physical_damage_records(region_id)],
        )
    )
    return key_name in effective


def _resolved_action_revision():
    records = []
    for action in effective_actions(list(bpy.data.actions)):
        if bool(action.get("dsb_draft", False)) or not bool(
            action.get("dsb_approved", False)
        ):
            continue
        curves = []
        for curve in animation_library.iter_action_fcurves(action):
            curves.append(
                {
                    "dataPath": str(curve.data_path),
                    "arrayIndex": int(curve.array_index),
                    "points": [
                        {
                            "co": [float(point.co[0]), float(point.co[1])],
                            "handleLeft": [
                                float(point.handle_left[0]),
                                float(point.handle_left[1]),
                            ],
                            "handleRight": [
                                float(point.handle_right[0]),
                                float(point.handle_right[1]),
                            ],
                            "interpolation": str(point.interpolation),
                        }
                        for point in curve.keyframe_points
                    ],
                }
            )
        records.append(
            {
                "clipId": str(
                    action.get(animation_library.CLIP_ID_PROPERTY, "")
                ),
                "name": action.name,
                "kind": str(action.get("dsb_approved_kind", "")),
                "offensive": str(action.get("dsb_offensive_action_json", "")),
                "recipe": str(action.get("dsb_offensive_character_recipe", "")),
                "curves": sorted(
                    curves,
                    key=lambda value: (value["dataPath"], value["arrayIndex"]),
                ),
            }
        )
    return model.canonical_digest(
        sorted(records, key=lambda value: value["clipId"])
    )


def _resolved_damage_revision():
    physical = _physical_damage_records()
    names_by_region = {}
    for record in physical:
        names_by_region.setdefault(record["regionId"], []).append(record["name"])
    effective_by_region = {
        region_id: set(effective_damage_key_names(region_id, names))
        for region_id, names in names_by_region.items()
    }
    records = [
        {
            "regionId": record["regionId"],
            "damageKeyId": record["damageKeyId"],
            "name": record["name"],
            "entry": copy.deepcopy(record["entry"]),
        }
        for record in physical
        if record["name"] in effective_by_region.get(record["regionId"], set())
    ]
    try:
        _registry, collection = _full_progressive_collection()
        sites = effective_progressive_collection(collection).get("sites", [])
    except (KeyError, RuntimeError, TypeError, ValueError):
        sites = []
    return model.canonical_digest(
        {
            "keys": sorted(
                records,
                key=lambda value: (value["regionId"], value["damageKeyId"]),
            ),
            "progressiveSites": sites,
        }
    )


def export_provenance(scene=None):
    state = load_state(scene)
    if state is None:
        return None
    provenance = model.export_provenance(state)
    resolved_content_revision = model.canonical_digest(
        {
            "actions": _resolved_action_revision(),
            "damage": _resolved_damage_revision(),
        }
    )[:20]
    effective_revision = model.canonical_digest(
        {
            "structuralRevision": provenance["effectiveForgeRevision"],
            "resolvedContentRevision": resolved_content_revision,
        }
    )[:20]
    provenance["resolvedContentRevision"] = resolved_content_revision
    provenance["effectiveForgeRevision"] = effective_revision
    provenance["effectiveForgeVariantIdentity"] = (
        f"{provenance['technicalFamilyId']}:"
        f"{provenance['appearanceVariantId']}:"
        f"{effective_revision}"
    )
    return provenance


@contextmanager
def export_context(context, settings, state):
    """Stage only the active variant's appearance, morphs, and provenance."""

    family = load_state(context.scene)
    if family is None:
        yield None
        return
    variant = model.variant_by_id(family)
    handoff = model.require_handoff(variant["handoff"])
    expected_fields = {
        "family_id": family["familyId"],
        "technical_body_schema": family["technicalBodySchema"],
        "technical_body_schema_version": family["technicalBodySchemaVersion"],
        "technical_body_fingerprint": family["technicalBodyFingerprint"],
    }
    mismatched = [
        field
        for field, expected in expected_fields.items()
        if handoff.get(field) != expected
    ]
    if mismatched:
        raise RuntimeError(
            "Active variant appearance provenance no longer matches its family: "
            + ", ".join(mismatched)
            + "."
        )
    appearance_armature_name = str(
        variant.get("appearance", {}).get("armatureName", "")
    )
    if appearance_armature_name:
        appearance_armature = bpy.data.objects.get(appearance_armature_name)
        if appearance_armature is None or appearance_armature.type != "ARMATURE":
            raise RuntimeError("The active Skin & Bones appearance armature is missing.")
        current_handoff = handoff_from_armature(appearance_armature)
        if model.stable_json(current_handoff) != model.stable_json(handoff):
            raise RuntimeError(
                "The active Skin & Bones appearance handoff changed after family ingest."
            )
        if model.canonical_rig_signature(_rig_contract(appearance_armature)) != model.canonical_rig_signature(
            family["canonicalRig"]
        ):
            raise RuntimeError(
                "The active appearance canonical rig/coordinate contract changed after family ingest."
            )
    for shared_id, override_record in variant.get("actionOverrides", {}).items():
        override_id = str(override_record.get("overrideActionId", ""))
        override = animation_library.find_action_by_clip_id(override_id)
        if override is None:
            raise RuntimeError(
                f"Variant Action override for {shared_id!r} is missing its Blender Action."
            )
        if bool(override.get("dsb_draft", False)) or not bool(
            override.get("dsb_approved", False)
        ):
            raise RuntimeError(
                f"Variant Action override {override.name!r} must be saved and approved before export."
            )
    switch_variant(variant["variantId"], context.scene)
    provenance = export_provenance(context.scene)
    encoded = model.stable_json(provenance)
    previous_filename = str(settings.damage_authoring_filename)
    previous_properties = []
    previous_mutes = []
    active_names_by_region = {}
    for record in _physical_damage_records():
        active_names_by_region.setdefault(record["regionId"], []).append(record["name"])
    effective_by_region = {
        region_id: set(effective_damage_key_names(region_id, names))
        for region_id, names in active_names_by_region.items()
    }
    appearance_bodies = set(_appearance_body_objects())
    runtime_rig = bpy.data.objects.get(str(state.get("authoring_rig", "")))
    try:
        settings.damage_authoring_filename = variant["exportIdentity"]
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                region_id = str(obj.get("dsb_deformation_region", ""))
                keys = getattr(obj.data, "shape_keys", None)
                if keys is not None and region_id in effective_by_region:
                    for key in keys.key_blocks:
                        if key == keys.reference_key:
                            continue
                        previous_mutes.append((key, bool(key.mute)))
                        key.mute = key.name not in effective_by_region[region_id]
            if obj == runtime_rig or obj in appearance_bodies:
                before = {
                    name: (name in obj, obj.get(name))
                    for name in (
                        PROVENANCE_PROPERTY,
                        ACTIVE_EXPORT_PROPERTY,
                        model.SBF_FAMILY_ID_PROPERTY,
                        model.SBF_VARIANT_ID_PROPERTY,
                        model.SBF_BODY_FINGERPRINT_PROPERTY,
                    )
                }
                previous_properties.append((obj, before))
                obj[PROVENANCE_PROPERTY] = encoded
                obj[ACTIVE_EXPORT_PROPERTY] = variant["variantId"]
                obj[model.SBF_FAMILY_ID_PROPERTY] = family["familyId"]
                obj[model.SBF_VARIANT_ID_PROPERTY] = variant["variantId"]
                obj[model.SBF_BODY_FINGERPRINT_PROPERTY] = family[
                    "technicalBodyFingerprint"
                ]
        yield provenance
    finally:
        settings.damage_authoring_filename = previous_filename
        for key, muted in previous_mutes:
            try:
                key.mute = muted
            except ReferenceError:
                pass
        for obj, values in previous_properties:
            if obj is None or obj.name not in bpy.data.objects:
                continue
            for name, (existed, value) in values.items():
                if existed:
                    obj[name] = value
                elif name in obj:
                    del obj[name]


def batch_export_ready_variants(context):
    from . import damage_authoring

    family = load_state(context.scene, required=True)
    settings = context.scene.daf_settings
    original_variant = family["activeVariantId"]
    original_filename = str(settings.damage_authoring_filename)
    authoring_state = damage_authoring._load_state()
    if authoring_state is None:
        raise RuntimeError("Build the Complete Damage authoring asset before batch export.")
    exported = []
    skipped = []
    try:
        for variant in family["variants"]:
            switch_variant(variant["variantId"], context.scene)
            try:
                paths = damage_authoring._export_asset(
                    context,
                    settings,
                    authoring_state,
                )
            except Exception as exc:
                skipped.append(
                    {"variantId": variant["variantId"], "reason": str(exc)}
                )
                continue
            exported.append(
                {
                    "variantId": variant["variantId"],
                    "exportIdentity": variant["exportIdentity"],
                    "paths": list(paths),
                }
            )
    finally:
        settings.damage_authoring_filename = original_filename
        switch_variant(original_variant, context.scene)
    return {"exported": exported, "skipped": skipped}


class _VariantOperator(Operator):
    def failed(self, context, exc):
        settings = getattr(context.scene, "daf_settings", None)
        if settings is not None:
            settings.variant_family_status = f"ERROR — {exc}"
        self.report({"ERROR"}, str(exc))
        return {"CANCELLED"}


class DAF_OT_adopt_character_variant_family(_VariantOperator):
    bl_idname = "daf.adopt_character_variant_family"
    bl_label = "Adopt as Shared Family Base"
    bl_description = "Adopt the selected approved Skin & Bones appearance and existing Forge authoring as the shared family layer"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            state = adopt_selected_as_family_base(context)
            self.report(
                {"INFO"},
                f"Adopted {state['displayName']} with {len(state['shared']['actionIds'])} shared Action(s).",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_import_character_variant(_VariantOperator):
    bl_idname = "daf.import_character_variant"
    bl_label = "Add Skin & Bones Variant"
    bl_description = "Import one approved Skin & Bones appearance, prove exact family/body compatibility, and inherit shared Forge authoring"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            variant = import_appearance_variant(
                context,
                context.scene.daf_settings.variant_import_path,
            )
            self.report(
                {"INFO"},
                f"Added {variant['displayName']}; all Forge authoring is inherited by default.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_switch_character_variant(_VariantOperator):
    bl_idname = "daf.switch_character_variant"
    bl_label = "Switch Appearance Variant"
    bl_description = "Show this appearance while preserving resolved Actions, Damage, sockets, and rig state"
    bl_options = {"REGISTER", "UNDO"}

    variant_id: StringProperty()

    def execute(self, context):
        try:
            variant = switch_variant(self.variant_id, context.scene)
            self.report({"INFO"}, f"Active appearance: {variant['displayName']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_create_variant_action_override(_VariantOperator):
    bl_idname = "daf.create_variant_action_override"
    bl_label = "Create Variant Override"
    bl_description = "Create one variant-owned editable Action copy; every other Action remains inherited"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            action = animation_library.selected_action(context.scene.daf_settings)
            if action is None:
                raise RuntimeError("Select an inherited Action first.")
            override = create_action_override(context, action)
            self.report({"INFO"}, f"Created variant override draft {override.name}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_revert_variant_action_override(_VariantOperator):
    bl_idname = "daf.revert_variant_action_override"
    bl_label = "Revert Action to Shared"
    bl_description = "Discard this variant-owned Action and immediately resolve the shared family Action"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            action = animation_library.selected_action(context.scene.daf_settings)
            if action is None:
                raise RuntimeError("Select a variant Action override first.")
            shared = revert_action_override(context, action)
            self.report({"INFO"}, f"Reverted to shared Action {shared.name if shared else ''}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_edit_shared_family_action(_VariantOperator):
    bl_idname = "daf.edit_shared_family_action"
    bl_label = "Edit Shared Family Action"
    bl_description = "Intentionally edit the shared family Action; every inheriting appearance receives the saved change"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            action = animation_library.selected_action(context.scene.daf_settings)
            if action is None:
                raise RuntimeError("Select a shared or inherited Action first.")
            state = load_state(context.scene, required=True)
            shared, _shared_id = _shared_action(action, state)
            from . import find_armature

            result = animation_library.begin_edit(context, find_armature(context), shared)
            self.report({"WARNING"}, f"Editing shared family Action {result['source']}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_create_variant_damage_override(_VariantOperator):
    bl_idname = "daf.create_variant_damage_override"
    bl_label = "Create Damage Override"
    bl_description = "Clone only the selected Damage Key or coherent Progressive Site unit for this appearance"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            if context.scene.daf_settings.variant_damage_override_unit == "PROGRESSIVE_SITE":
                record = create_progressive_site_override(context)
                label = record["overrideSiteGuid"]
            else:
                record = create_damage_key_override(context)
                label = record["overrideName"]
            self.report({"INFO"}, f"Created variant Damage override {label}.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_revert_variant_damage_override(_VariantOperator):
    bl_idname = "daf.revert_variant_damage_override"
    bl_label = "Revert Damage to Shared"
    bl_description = "Discard variant-only Damage edits, remove owned data, and restore live shared resolution"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            if context.scene.daf_settings.variant_damage_override_unit == "PROGRESSIVE_SITE":
                revert_progressive_site_override(context)
            else:
                revert_damage_key_override(context)
            self.report({"INFO"}, "Variant Damage override discarded; shared content restored.")
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_toggle_shared_family_damage_edit(_VariantOperator):
    bl_idname = "daf.toggle_shared_family_damage_edit"
    bl_label = "Edit Shared Family Damage"
    bl_description = "Deliberately unlock family-wide Damage editing for every inheriting appearance"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        settings = context.scene.daf_settings
        if settings.variant_shared_damage_edit_enabled:
            return self.execute(context)
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            load_state(context.scene, required=True)
            settings = context.scene.daf_settings
            settings.variant_shared_damage_edit_enabled = not bool(
                settings.variant_shared_damage_edit_enabled
            )
            state = "UNLOCKED" if settings.variant_shared_damage_edit_enabled else "LOCKED"
            settings.variant_family_status = f"SHARED FAMILY DAMAGE EDITING {state}"
            self.report(
                {"WARNING" if settings.variant_shared_damage_edit_enabled else "INFO"},
                settings.variant_family_status,
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


class DAF_OT_export_ready_character_variants(_VariantOperator):
    bl_idname = "daf.export_ready_character_variants"
    bl_label = "Export All Ready Variants"
    bl_description = "Export each Forge-ready appearance as its own resolved Complete Damage GLB and sidecars"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            result = batch_export_ready_variants(context)
            if not result["exported"]:
                detail = result["skipped"][0]["reason"] if result["skipped"] else "No variants exist."
                raise RuntimeError("No ready variants exported. " + detail)
            self.report(
                {"WARNING"} if result["skipped"] else {"INFO"},
                f"Exported {len(result['exported'])} variant(s); skipped {len(result['skipped'])}.",
            )
            return {"FINISHED"}
        except Exception as exc:
            return self.failed(context, exc)


CLASSES = (
    DAF_OT_adopt_character_variant_family,
    DAF_OT_import_character_variant,
    DAF_OT_switch_character_variant,
    DAF_OT_create_variant_action_override,
    DAF_OT_revert_variant_action_override,
    DAF_OT_edit_shared_family_action,
    DAF_OT_create_variant_damage_override,
    DAF_OT_revert_variant_damage_override,
    DAF_OT_toggle_shared_family_damage_edit,
    DAF_OT_export_ready_character_variants,
)


__all__ = (
    "CLASSES",
    "FAMILY_STATE_PROPERTY",
    "ACTION_SCOPE_PROPERTY",
    "action_status",
    "adopt_selected_as_family_base",
    "batch_export_ready_variants",
    "damage_object_is_effective",
    "damage_status",
    "effective_actions",
    "effective_damage_key_names",
    "effective_progressive_collection",
    "export_context",
    "export_provenance",
    "handoff_from_armature",
    "import_appearance_variant",
    "load_state",
    "mark_action_for_family",
    "merge_progressive_collection",
    "recover_state",
    "require_regular_action_edit_allowed",
    "store_state",
    "switch_variant",
)
