"""Region activation without repeated Outliner selection."""

from __future__ import annotations

import bpy
from bpy.props import StringProperty
from bpy.types import Operator


class DAF_OT_activate_standard_region(Operator):
    bl_idname = "daf.activate_standard_region"
    bl_label = "Activate Damage Region"
    bl_description = "Activate a registered region and its managed target object"
    bl_options = {'REGISTER'}

    region_id: StringProperty()

    def execute(self, context):
        from ... import deformation_authoring

        try:
            registry = deformation_authoring._load_registry()
            region = deformation_authoring._region_record(registry, self.region_id)
            if region is None:
                raise RuntimeError(f"Region {self.region_id!r} is not registered.")
            deformation_authoring._set_active_region(self.region_id, context)
            attached, _detached = deformation_authoring._resolve_region_pair(region)
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            attached.hide_set(False)
            attached.select_set(True)
            context.view_layer.objects.active = attached
            context.scene.daf_settings.deformation_status = f"ACTIVE REGION — {self.region_id}"
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


CLASSES = (DAF_OT_activate_standard_region,)
