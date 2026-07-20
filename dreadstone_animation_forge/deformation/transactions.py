"""Reusable Blender operation capture, rollback, and scoped cleanup."""

from __future__ import annotations

import copy

import bpy

from . import diagnostics


class OperationTransaction:
    """Capture user/context state and remove only resources created in scope."""

    def __init__(
        self,
        context,
        name,
        *,
        objects=(),
        metadata_keys=(),
        coordinate_key_names=(),
        property_groups=(),
        ownership_predicate=None,
    ):
        self.context = context
        self.name = str(name)
        self.objects = tuple(obj for obj in objects if obj is not None)
        self.metadata_keys = tuple(str(key) for key in metadata_keys)
        self.coordinate_key_names = tuple(str(name) for name in coordinate_key_names)
        self.property_groups = tuple(property_groups)
        self.ownership_predicate = ownership_predicate or (lambda datablock: bool(datablock.get("dsb_generated_role", "")))
        self.stage = "initialize"
        self._committed = False
        self._snapshot = None

    def __enter__(self):
        context = self.context
        active = getattr(context.view_layer.objects, "active", None)
        shape_values = {}
        materials = {}
        metadata = {}
        data_metadata = {}
        visibility = {}
        coordinates = {}
        property_groups = []
        for group, prefix in self.property_groups:
            values = {}
            for prop in getattr(getattr(group, "bl_rna", None), "properties", ()):
                identifier = str(getattr(prop, "identifier", ""))
                if identifier == "rna_type" or not identifier.startswith(str(prefix)):
                    continue
                if bool(getattr(prop, "is_readonly", False)) or str(getattr(prop, "type", "")) in {"COLLECTION", "POINTER"}:
                    continue
                try:
                    value = getattr(group, identifier)
                    values[identifier] = list(value) if hasattr(value, "to_list") else copy.deepcopy(value)
                except Exception:
                    continue
            property_groups.append((group, values))
        for obj in self.objects:
            if obj.type == 'MESH' and obj.data.shape_keys:
                shape_values[obj.name] = {
                    "activeIndex": int(obj.active_shape_key_index),
                    "values": {key.name: float(key.value) for key in obj.data.shape_keys.key_blocks},
                    "names": tuple(key.name for key in obj.data.shape_keys.key_blocks),
                }
                coordinates[obj.name] = {
                    key.name: tuple(tuple(float(component) for component in point.co) for point in key.data)
                    for key in obj.data.shape_keys.key_blocks
                    if key.name in self.coordinate_key_names
                }
            materials[obj.name] = [slot.material.name if slot.material else "" for slot in obj.material_slots]
            metadata[obj.name] = {
                key: copy.deepcopy(obj.get(key)) if key in obj else None for key in self.metadata_keys
            }
            if getattr(obj, "data", None) is not None:
                data_metadata[obj.name] = {
                    key: copy.deepcopy(obj.data.get(key)) if key in obj.data else None for key in self.metadata_keys
                }
            visibility[obj.name] = {
                "hideViewport": bool(obj.hide_viewport),
                "hideRender": bool(obj.hide_render),
                "hideGet": bool(obj.hide_get()),
            }
        self._snapshot = {
            "mode": str(getattr(context, "mode", "OBJECT")),
            "selected": tuple(obj.name for obj in context.selected_objects),
            "active": active.name if active else "",
            "frame": int(context.scene.frame_current),
            "action": (
                active.animation_data.action.name
                if active is not None and active.animation_data and active.animation_data.action else ""
            ),
            "shapeValues": shape_values,
            "coordinates": coordinates,
            "materials": materials,
            "metadata": metadata,
            "dataMetadata": data_metadata,
            "sceneMetadata": {
                key: copy.deepcopy(context.scene.get(key)) if key in context.scene else None
                for key in self.metadata_keys
            },
            "visibility": visibility,
            "propertyGroups": property_groups,
            "objects": {obj.name for obj in bpy.data.objects},
            "meshes": {mesh.name for mesh in bpy.data.meshes},
            "materialsInventory": {material.name for material in bpy.data.materials},
        }
        return self

    def set_stage(self, stage):
        self.stage = str(stage)

    def commit(self):
        self._committed = True

    def __exit__(self, exc_type, exc, _traceback):
        if exc is None and self._committed:
            return False
        if exc is not None:
            diagnostics.record_exception(f"{self.name}: {self.stage}", exc)
        self.rollback()
        return False

    def _remove_created(self, collection, original_names):
        for datablock in tuple(collection):
            if datablock.name in original_names:
                continue
            try:
                if self.ownership_predicate(datablock):
                    collection.remove(datablock, do_unlink=True)
            except TypeError:
                try:
                    collection.remove(datablock)
                except Exception:
                    pass
            except Exception:
                pass

    def rollback(self):
        if not self._snapshot:
            return
        snap = self._snapshot
        try:
            if getattr(self.context, "mode", "OBJECT") != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        self._remove_created(bpy.data.objects, snap["objects"])
        self._remove_created(bpy.data.meshes, snap["meshes"])
        self._remove_created(bpy.data.materials, snap["materialsInventory"])
        for object_name, values in snap["shapeValues"].items():
            obj = bpy.data.objects.get(object_name)
            if obj is None or obj.type != 'MESH' or not obj.data.shape_keys:
                continue
            original_names = set(values.get("names", ()))
            for key in tuple(obj.data.shape_keys.key_blocks):
                if key.name not in original_names and key != obj.data.shape_keys.reference_key:
                    try:
                        obj.shape_key_remove(key)
                    except RuntimeError:
                        pass
            for key_name, value in values["values"].items():
                key = obj.data.shape_keys.key_blocks.get(key_name)
                if key is not None:
                    key.value = float(value)
            obj.active_shape_key_index = min(int(values["activeIndex"]), len(obj.data.shape_keys.key_blocks) - 1)
        for object_name, key_values in snap.get("coordinates", {}).items():
            obj = bpy.data.objects.get(object_name)
            if obj is None or obj.type != 'MESH' or not obj.data.shape_keys:
                continue
            for key_name, values in key_values.items():
                key = obj.data.shape_keys.key_blocks.get(key_name)
                if key is None or len(key.data) != len(values):
                    continue
                flat = [component for point in values for component in point]
                key.data.foreach_set("co", flat)
        for object_name, names in snap["materials"].items():
            obj = bpy.data.objects.get(object_name)
            if obj is None or obj.type != 'MESH':
                continue
            while len(obj.data.materials) > len(names):
                obj.data.materials.pop(index=len(obj.data.materials) - 1)
            while len(obj.data.materials) < len(names):
                obj.data.materials.append(None)
            for index, name in enumerate(names):
                obj.material_slots[index].material = bpy.data.materials.get(name) if name else None
        for object_name, values in snap["metadata"].items():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                continue
            for key, value in values.items():
                if value is None:
                    if key in obj:
                        del obj[key]
                else:
                    obj[key] = value
        for object_name, values in snap.get("dataMetadata", {}).items():
            obj = bpy.data.objects.get(object_name)
            if obj is None or getattr(obj, "data", None) is None:
                continue
            for key, value in values.items():
                if value is None:
                    if key in obj.data:
                        del obj.data[key]
                else:
                    obj.data[key] = value
        for key, value in snap.get("sceneMetadata", {}).items():
            if value is None:
                if key in self.context.scene:
                    del self.context.scene[key]
            else:
                self.context.scene[key] = value
        try:
            from . import preview_service
            update_scope = preview_service.suspend_updates()
        except Exception:
            from contextlib import nullcontext
            update_scope = nullcontext()
        with update_scope:
            for group, values in snap.get("propertyGroups", ()):
                for identifier, value in values.items():
                    try:
                        setattr(group, identifier, value)
                    except Exception:
                        pass
        for object_name, values in snap["visibility"].items():
            obj = bpy.data.objects.get(object_name)
            if obj is not None:
                obj.hide_viewport = values["hideViewport"]
                obj.hide_render = values["hideRender"]
                obj.hide_set(values["hideGet"])
        try:
            bpy.ops.object.select_all(action='DESELECT')
            for name in snap["selected"]:
                obj = bpy.data.objects.get(name)
                if obj is not None:
                    obj.select_set(True)
            self.context.view_layer.objects.active = bpy.data.objects.get(snap["active"])
            self.context.scene.frame_set(snap["frame"])
            active = self.context.view_layer.objects.active
            if active is not None and active.animation_data:
                active.animation_data.action = bpy.data.actions.get(snap["action"]) if snap["action"] else None
            mode = snap["mode"]
            if mode.startswith("EDIT"):
                bpy.ops.object.mode_set(mode='EDIT')
            elif mode == 'SCULPT':
                bpy.ops.object.mode_set(mode='SCULPT')
        except Exception:
            pass
