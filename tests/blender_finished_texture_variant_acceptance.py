"""Blender acceptance for texture-multiplying an already finished character."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import bpy
from bpy.props import PointerProperty
from bpy.types import Operator, PropertyGroup


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

import dreadstone_animation_forge as addon  # noqa: E402
from dreadstone_animation_forge import attachment_sockets  # noqa: E402
from dreadstone_animation_forge import variant_authoring  # noqa: E402
from dreadstone_animation_forge import variant_family as model  # noqa: E402
from blender_character_variant_family_acceptance import (  # noqa: E402
    make_canonical_armature,
    make_shared_action,
)


def require(condition, message):
    if not condition:
        raise RuntimeError(str(message))


def make_runtime_body(rig, material):
    mesh = bpy.data.meshes.new("FinishedBodyMesh")
    mesh.from_pydata(
        [(-0.3, 0.0, 0.0), (0.3, 0.0, 0.0), (0.3, 0.0, 1.0), (-0.3, 0.0, 1.0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.uv_layers.new(name="UVMap")
    body = bpy.data.objects.new("DSB_BODY_CORE", mesh)
    bpy.context.collection.objects.link(body)
    body["dsb_damage_role"] = "body_core"
    body["dsb_damage_generated"] = True
    body["dsb_default_visible"] = True
    mesh.materials.append(material)
    modifier = body.modifiers.new("RuntimeArmature", "ARMATURE")
    modifier.object = rig
    group = body.vertex_groups.new(name="root")
    group.add(range(len(mesh.vertices)), 1.0, "REPLACE")
    return body


class BridgeTestSBFSettings(PropertyGroup):
    target_object: PointerProperty(type=bpy.types.Object)
    repair_final_image: PointerProperty(type=bpy.types.Image)


class BridgeTestBestPreview(Operator):
    bl_idname = "sbf.best_preview"
    bl_label = "Bridge Test Best Preview"

    def execute(self, context):
        target = context.scene.sbf_settings.target_object
        rig = variant_authoring._skin_and_bones_projection_armature(target)
        context.scene["bridge_test_preview_pose_position"] = (
            rig.data.pose_position if rig is not None else "UNRIGGED"
        )
        return {"FINISHED"}


class BridgeTestBakeFinal(Operator):
    bl_idname = "sbf.bake_final"
    bl_label = "Bridge Test Bake Final"

    def execute(self, context):
        target = context.scene.sbf_settings.target_object
        rig = variant_authoring._skin_and_bones_projection_armature(target)
        context.scene["bridge_test_bake_pose_position"] = (
            rig.data.pose_position if rig is not None else "UNRIGGED"
        )
        return {"FINISHED"}


def matrix_snapshot(values):
    return {
        name: tuple(tuple(float(value) for value in row) for row in matrix)
        for name, matrix in values.items()
    }


def matrix_snapshots_close(left, right, tolerance=1.0e-7):
    return set(left) == set(right) and all(
        abs(left[name][row][column] - right[name][row][column]) <= tolerance
        for name in left
        for row in range(4)
        for column in range(4)
    )


def evaluated_world_vertices(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return tuple(
            tuple(float(value) for value in evaluated.matrix_world @ vertex.co)
            for vertex in mesh.vertices
        )
    finally:
        evaluated.to_mesh_clear()


def maximum_vertex_delta(left, right):
    require(len(left) == len(right) and left, "Evaluated projection geometry is empty or mismatched.")
    return max(
        sum((a - b) ** 2 for a, b in zip(left_vertex, right_vertex)) ** 0.5
        for left_vertex, right_vertex in zip(left, right)
    )


def make_skin_material():
    image = bpy.data.images.new("Finished_BaseColor", width=8, height=8)
    image.generated_color = (0.35, 0.12, 0.05, 1.0)
    image.pack()
    material = bpy.data.materials.new("Finished_Skin")
    material.use_nodes = True
    tree = material.node_tree
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.name = "VariantBaseColor"
    texture.image = image
    principled = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    return material


def main():
    addon.register()
    bpy.utils.register_class(BridgeTestSBFSettings)
    bpy.utils.register_class(BridgeTestBestPreview)
    bpy.utils.register_class(BridgeTestBakeFinal)
    bpy.types.Scene.sbf_settings = PointerProperty(type=BridgeTestSBFSettings)
    rig = make_canonical_armature("DSB_DAMAGE_RIG")
    rig["dsb_damage_generated"] = True
    rig["dsb_damage_role"] = "runtime_rig"
    material = make_skin_material()
    body = make_runtime_body(rig, material)
    detached_mesh = body.data.copy()
    detached = bpy.data.objects.new("DSB_SEGMENT_HEAD", detached_mesh)
    bpy.context.collection.objects.link(detached)
    detached["dsb_damage_role"] = "detached_segment"
    detached["dsb_damage_generated"] = True
    detached["dsb_default_visible"] = False
    detached.hide_set(True)
    detached.hide_viewport = True
    detached.hide_render = True
    projection_target = bpy.data.objects.new(
        "SBF_CLEAN_CHARACTER",
        body.data.copy(),
    )
    bpy.context.collection.objects.link(projection_target)
    projection_group = projection_target.vertex_groups.new(name="body")
    projection_group.add(
        range(len(projection_target.data.vertices)),
        1.0,
        "REPLACE",
    )
    projection_rig = make_canonical_armature("SBF_ProductionRig")
    projection_rig["sbf_production_rig"] = True
    projection_rig["sbf_rig_stage"] = "PRODUCTION"
    projection_target.parent = projection_rig
    projection_modifier = projection_target.modifiers.new("SBF_ProductionArmature", "ARMATURE")
    projection_modifier.object = projection_rig
    projection_rig.data.pose_position = "POSE"
    projection_rig.pose.bones["body"].rotation_mode = "XYZ"
    projection_rig.pose.bones["body"].rotation_euler = (0.41, -0.27, 0.19)
    projection_rig.animation_data_create()
    source_action = bpy.data.actions.new("SBF_Source_DisplayPose")
    source_action.use_fake_user = True
    projection_rig.animation_data.action = source_action
    bpy.context.view_layer.update()
    posed_projection_vertices = evaluated_world_vertices(projection_target)
    projection_rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    neutral_projection_vertices = evaluated_world_vertices(projection_target)
    require(
        maximum_vertex_delta(posed_projection_vertices, neutral_projection_vertices) > 0.01,
        "The acceptance fixture did not reproduce a visibly bent projection target.",
    )
    projection_rig.data.pose_position = "POSE"
    bpy.context.view_layer.update()
    unsafe_rig = bpy.data.objects.new("Unsafe_Shared_Projection_Rig", rig.data)
    bpy.context.collection.objects.link(unsafe_rig)
    unsafe_target_mesh = projection_target.data.copy()
    unsafe_target = bpy.data.objects.new("Unsafe_Shared_Projection_Target", unsafe_target_mesh)
    bpy.context.collection.objects.link(unsafe_target)
    unsafe_target.parent = unsafe_rig
    try:
        variant_authoring._skin_and_bones_projection_armature(unsafe_target)
    except RuntimeError as exc:
        require("sharing its data" in str(exc), exc)
    else:
        raise RuntimeError("Projection accepted an armature sharing DSB_DAMAGE_RIG data.")
    bpy.data.objects.remove(unsafe_target, do_unlink=True)
    bpy.data.objects.remove(unsafe_rig, do_unlink=True)
    bpy.data.meshes.remove(unsafe_target_mesh)
    source_alias = bpy.data.objects.new("Unsafe_SBF_Data_Alias", projection_rig.data)
    bpy.context.collection.objects.link(source_alias)
    try:
        variant_authoring._skin_and_bones_projection_armature(projection_target)
    except RuntimeError as exc:
        require("shared by another object" in str(exc), exc)
    else:
        raise RuntimeError("Projection accepted a generic alias of the S&B Armature datablock.")
    bpy.data.objects.remove(source_alias, do_unlink=True)
    projection_target.hide_set(True)
    projection_target.hide_viewport = True
    projection_target.hide_render = True
    sbf_final = bpy.data.images.new("SBF_Test_BaseColor_Final", width=8, height=8)
    sbf_final.generated_color = (0.82, 0.76, 0.64, 1.0)
    sbf_final.pack()
    bpy.context.scene.sbf_settings.target_object = projection_target
    bpy.context.scene.sbf_settings.repair_final_image = sbf_final
    shared = make_shared_action(rig)
    helpers = attachment_sockets.ensure_standard_sockets(rig)
    socket = helpers[0]
    socket.location.x += 0.073
    socket.location.z -= 0.021
    socket.rotation_euler.rotate_axis("Y", 0.31)
    bpy.context.view_layer.update()
    parent_world = rig.matrix_world @ rig.pose.bones[socket.parent_bone].matrix
    before_position, before_rotation, _before_scale = (
        parent_world.inverted_safe() @ socket.matrix_world
    ).decompose()
    before_rotation.normalize()
    helpers[0].scale = (1.25, 1.25, 1.25)
    bpy.context.view_layer.update()
    try:
        attachment_sockets.runtime_socket_contract(runtime_rig=rig)
    except RuntimeError as exc:
        require("unsupported local scale" in str(exc), exc)
    else:
        raise RuntimeError("The acceptance fixture did not reproduce resized socket scale.")
    attachment_sockets.ensure_standard_sockets(rig)
    socket_contract = attachment_sockets.runtime_socket_contract(runtime_rig=rig)
    require(socket_contract["socketCount"] == 2, socket_contract)
    parent_world = rig.matrix_world @ rig.pose.bones[socket.parent_bone].matrix
    after_position, after_rotation, _after_scale = (
        parent_world.inverted_safe() @ socket.matrix_world
    ).decompose()
    after_rotation.normalize()
    require((after_position - before_position).length <= 1.0e-6, "Socket position moved during scale repair.")
    require(abs(after_rotation.dot(before_rotation)) >= 1.0 - 1.0e-6, "Socket rotation changed during scale repair.")
    actions_before = len(bpy.data.actions)
    objects_before = len(bpy.data.objects)
    meshes_before = len(bpy.data.meshes)

    settings = bpy.context.scene.daf_settings
    settings.damage_authoring_filename = "finished_warden"
    settings.variant_texture_family_name = ""
    settings.variant_texture_name = ""
    settings.variant_texture_export_identity = ""
    state = variant_authoring.adopt_finished_damage_as_texture_family(bpy.context)
    require(state["familySource"] == model.FAMILY_SOURCE_FORGE_TEXTURE, state)
    require(model.variant_by_id(state)["handoff"] is None, state)
    variant_authoring.mark_action_for_family(shared, rig)
    state = variant_authoring.load_state(required=True)
    require(len(state["shared"]["actionIds"]) == 1, state)
    require(len(bpy.data.actions) == actions_before, "Base snapshot duplicated an Action.")
    require(len(bpy.data.objects) == objects_before, "Base snapshot duplicated body objects.")
    require(len(bpy.data.meshes) == meshes_before, "Base snapshot duplicated body meshes.")
    base = model.variant_by_id(state)
    require(base["displayName"] == "Original", base)
    require(base["exportIdentity"] == "finished_warden", base)
    base_material = base["appearance"]["ownedMaterials"][0]

    settings.variant_texture_name = "Ashen"
    settings.variant_texture_export_identity = "finished_warden_ashen"
    draft = variant_authoring.create_forge_texture_variant(bpy.context)
    require(variant_authoring.appearance_status(variant_authoring.load_state()) == "DRAFT", draft)
    require(len(bpy.data.actions) == actions_before, "New look duplicated an Action.")
    require(len(bpy.data.objects) == objects_before, "New look duplicated body objects.")
    require(len(bpy.data.meshes) == meshes_before, "New look duplicated body meshes.")
    require(draft["actionOverrides"] == {}, draft)
    require(draft["damageKeyOverrides"] == {}, draft)
    require(draft["progressiveSiteOverrides"] == {}, draft)
    settings.variant_texture_name = "Premature Third Look"
    try:
        variant_authoring.create_forge_texture_variant(bpy.context)
    except RuntimeError as exc:
        require("Save the active look" in str(exc), exc)
    else:
        raise RuntimeError("A second unsaved draft was allowed.")
    settings.variant_texture_name = ""

    bpy.context.scene.frame_set(13)
    socket_world_before_bridge = socket.matrix_world.copy()
    runtime_action_before_bridge = rig.animation_data.action
    runtime_pose_before_bridge = matrix_snapshot(
        {bone.name: bone.matrix.copy() for bone in rig.pose.bones}
    )
    require(len(runtime_pose_before_bridge) == 21, "Runtime fixture no longer has the 21-bone contract.")
    runtime_rig_world_before_bridge = matrix_snapshot({rig.name: rig.matrix_world.copy()})
    socket_worlds_before_bridge = matrix_snapshot(
        {helper.name: helper.matrix_world.copy() for helper in helpers}
    )
    helper_names_before_bridge = tuple(helper.name for helper in helpers)
    socket_name_before_bridge = socket.name
    socket_contract_before_bridge = attachment_sockets.runtime_socket_contract(runtime_rig=rig)
    source_basis_before_bridge = matrix_snapshot(
        {bone.name: bone.matrix_basis.copy() for bone in projection_rig.pose.bones}
    )
    source_action_before_bridge = getattr(projection_rig.animation_data, "action", None)
    source_action_name_before_bridge = source_action_before_bridge.name
    runtime_action_name_before_bridge = runtime_action_before_bridge.name
    shared_action_name = shared.name
    bpy.context.scene[variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY] = "{corrupt"
    try:
        variant_authoring.enter_skin_and_bones_projection(bpy.context)
    except RuntimeError as exc:
        require("recovery state is corrupt" in str(exc), exc)
    else:
        raise RuntimeError("A corrupt projection recovery snapshot did not block entry.")
    require(projection_rig.data.pose_position == "POSE", "Corrupt recovery state changed the source rig.")
    require(rig.data.pose_position == "POSE", "Corrupt recovery state changed DSB_DAMAGE_RIG.")
    require(
        bpy.context.scene[variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY] == "{corrupt",
        "Forge discarded corrupt recovery state without an explicit recovery.",
    )
    del bpy.context.scene[variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY]
    bpy.context.scene[variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY] = model.stable_json(
        {
            "target": projection_target.name,
            "hideViewport": True,
            "hideRender": True,
            "hidden": True,
        }
    )
    shown_target = variant_authoring.enter_skin_and_bones_projection(bpy.context)
    require(shown_target == projection_target, shown_target)
    require(not projection_target.hide_get(), "The S&B projection body stayed hidden.")
    require(not projection_target.hide_viewport, "The S&B projection body stayed viewport-disabled.")
    require(body.hide_get() and body.hide_viewport, "The Forge body still obscured the S&B preview.")
    require(detached.hide_get() and detached.hide_viewport, "A detached piece appeared in projection mode.")
    require(
        projection_rig.data.pose_position == "REST",
        "The S&B projection rig did not enter its neutral rest pose.",
    )
    snapshot = json.loads(
        bpy.context.scene[variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY]
    )
    require(snapshot["rig"] == projection_rig.name, snapshot)
    require(snapshot["rigData"] == projection_rig.data.name, snapshot)
    require(snapshot["rigPosePosition"] == "POSE", snapshot)
    require(
        snapshot["schema"] == variant_authoring.SBF_PROJECTION_VISIBILITY_SCHEMA,
        "The 5.4.5 visibility-only snapshot was not migrated safely.",
    )
    require(
        maximum_vertex_delta(
            evaluated_world_vertices(projection_target),
            neutral_projection_vertices,
        )
        <= 1.0e-7,
        "Projection mode did not return the evaluated source body to neutral geometry.",
    )
    require(bpy.context.scene.frame_current == 13, "Projection changed the current frame.")
    require(rig.data.pose_position == "POSE", "Projection neutralized DSB_DAMAGE_RIG.")
    require(rig.animation_data.action is runtime_action_before_bridge, "Projection changed the shared Action.")
    require(
        matrix_snapshots_close(
            matrix_snapshot({bone.name: bone.matrix.copy() for bone in rig.pose.bones}),
            runtime_pose_before_bridge,
        ),
        "Projection changed a DSB_DAMAGE_RIG pose matrix.",
    )
    require(
        matrix_snapshots_close(
            matrix_snapshot({rig.name: rig.matrix_world.copy()}),
            runtime_rig_world_before_bridge,
        ),
        "Projection changed the DSB_DAMAGE_RIG transform.",
    )
    require(
        matrix_snapshots_close(
            matrix_snapshot({helper.name: helper.matrix_world.copy() for helper in helpers}),
            socket_worlds_before_bridge,
        ),
        "Projection changed an authored socket matrix.",
    )
    require(
        attachment_sockets.runtime_socket_contract(runtime_rig=rig)
        == socket_contract_before_bridge,
        "Projection changed the managed socket contract.",
    )
    require(
        matrix_snapshots_close(
            matrix_snapshot(
                {bone.name: bone.matrix_basis.copy() for bone in projection_rig.pose.bones}
            ),
            source_basis_before_bridge,
        ),
        "Neutral preview cleared the S&B rig's stored pose transforms.",
    )
    require(
        getattr(projection_rig.animation_data, "action", None) is source_action_before_bridge,
        "Neutral preview changed the S&B rig Action.",
    )
    late_alias = bpy.data.objects.new("Late_SBF_Data_Alias", projection_rig.data)
    bpy.context.collection.objects.link(late_alias)
    try:
        variant_authoring._restore_skin_and_bones_projection_visibility(bpy.context.scene)
    except RuntimeError as exc:
        require("shared by another object" in str(exc), exc)
    else:
        raise RuntimeError("Unsafe projection recovery restored a shared Armature datablock.")
    require(
        variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY in bpy.context.scene,
        "Failed recovery discarded the only saved source-pose record.",
    )
    require(
        projection_rig.data.pose_position == "REST",
        "Failed recovery mutated the shared S&B Armature datablock.",
    )
    bpy.data.objects.remove(late_alias, do_unlink=True)
    projection_target.parent = None
    projection_modifier.object = None
    restored_target = variant_authoring._restore_skin_and_bones_projection_visibility(
        bpy.context.scene
    )
    require(restored_target is projection_target, "Recovery lost the saved projection target.")
    require(
        projection_rig.data.pose_position == "POSE",
        "Relationship drift stranded the saved S&B source rig in REST.",
    )
    require(
        variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY not in bpy.context.scene,
        "Successful recovery retained stale projection state.",
    )
    projection_target.parent = projection_rig
    projection_modifier.object = projection_rig
    variant_authoring.enter_skin_and_bones_projection(bpy.context)
    require(
        projection_rig.data.pose_position == "REST",
        "Projection did not re-enter neutral mode after safe relationship recovery.",
    )
    projection_rig.data.pose_position = "POSE"
    variant_authoring.build_skin_and_bones_projection_preview(bpy.context)
    require(
        bpy.context.scene["bridge_test_preview_pose_position"] == "REST",
        "Preview did not reassert the neutral S&B pose after modal-folder drift.",
    )
    require(
        json.loads(bpy.context.scene[variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY])[
            "rigPosePosition"
        ]
        == "POSE",
        "Projection re-entry overwrote the original pose snapshot.",
    )
    projection_rig.data.pose_position = "POSE"
    variant_authoring.bake_skin_and_bones_projection(bpy.context)
    require(
        bpy.context.scene["bridge_test_bake_pose_position"] == "REST",
        "Final bake did not reassert the neutral S&B pose.",
    )
    require(
        json.loads(bpy.context.scene[variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY])[
            "rigPosePosition"
        ]
        == "POSE",
        "Final bake overwrote the original pose snapshot.",
    )
    recovery_output = Path(tempfile.mkdtemp(prefix="daf_projection_recovery_"))
    recovery_blend = recovery_output / "active_projection_recovery.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(recovery_blend))
    bpy.ops.wm.open_mainfile(filepath=str(recovery_blend))
    rig = bpy.data.objects["DSB_DAMAGE_RIG"]
    body = bpy.data.objects["DSB_BODY_CORE"]
    detached = bpy.data.objects["DSB_SEGMENT_HEAD"]
    projection_target = bpy.data.objects["SBF_CLEAN_CHARACTER"]
    projection_rig = bpy.data.objects["SBF_ProductionRig"]
    helpers = [bpy.data.objects[name] for name in helper_names_before_bridge]
    socket = bpy.data.objects[socket_name_before_bridge]
    settings = bpy.context.scene.daf_settings
    shared = bpy.data.actions[shared_action_name]
    runtime_action_before_bridge = bpy.data.actions[runtime_action_name_before_bridge]
    source_action_before_bridge = bpy.data.actions[source_action_name_before_bridge]
    require(
        projection_rig.data.pose_position == "REST",
        "Save/reopen lost the active projection's neutral source pose.",
    )
    require(
        variant_authoring.SBF_PROJECTION_VISIBILITY_PROPERTY in bpy.context.scene,
        "Save/reopen lost the active projection recovery snapshot.",
    )
    require(bpy.context.scene.frame_current == 13, "Save/reopen changed the projection frame.")
    require(rig.animation_data.action is runtime_action_before_bridge, "Save/reopen changed the runtime Action.")
    require(
        matrix_snapshots_close(
            matrix_snapshot({bone.name: bone.matrix.copy() for bone in rig.pose.bones}),
            runtime_pose_before_bridge,
        ),
        "Save/reopen changed a DSB_DAMAGE_RIG pose matrix during projection.",
    )
    require(
        matrix_snapshots_close(
            matrix_snapshot({rig.name: rig.matrix_world.copy()}),
            runtime_rig_world_before_bridge,
        ),
        "Save/reopen changed the DSB_DAMAGE_RIG transform during projection.",
    )
    require(
        matrix_snapshots_close(
            matrix_snapshot({helper.name: helper.matrix_world.copy() for helper in helpers}),
            socket_worlds_before_bridge,
            tolerance=2.0e-6,
        ),
        "Save/reopen changed an authored socket matrix during projection.",
    )
    require(
        matrix_snapshots_close(
            matrix_snapshot(
                {bone.name: bone.matrix_basis.copy() for bone in projection_rig.pose.bones}
            ),
            source_basis_before_bridge,
        ),
        "Save/reopen changed the S&B source pose bases.",
    )
    require(
        projection_rig.animation_data.action is source_action_before_bridge,
        "Save/reopen changed the S&B source Action.",
    )
    bridged_variant, bridged_image = variant_authoring.apply_skin_and_bones_final_texture(
        bpy.context
    )
    require(
        bridged_image.packed_file is not None or bridged_image.source == 'GENERATED',
        "The S&B final was neither packed nor stored as an internal generated image.",
    )
    require(bridged_image.name in bridged_variant["appearance"]["ownedImages"], bridged_variant)
    require(projection_target.hide_get(), "The S&B source body did not return to its hidden state.")
    require(projection_target.hide_viewport, "The S&B source body remained viewport-enabled.")
    require(not body.hide_get() and not body.hide_viewport, "The intact Forge body did not return.")
    require(detached.hide_get() and detached.hide_viewport, "Look preview revealed DSB_SEGMENT_HEAD.")
    require(
        projection_rig.data.pose_position == "POSE",
        "Leaving projection mode did not restore the S&B rig pose mode.",
    )
    require(
        matrix_snapshots_close(
            matrix_snapshot(
                {bone.name: bone.matrix_basis.copy() for bone in projection_rig.pose.bones}
            ),
            source_basis_before_bridge,
        ),
        "Leaving projection mode changed stored S&B pose transforms.",
    )
    require(bpy.context.scene.frame_current == 13, "Leaving projection changed the current frame.")
    require(rig.data.pose_position == "POSE", "Leaving projection changed DSB_DAMAGE_RIG pose mode.")
    require(rig.animation_data.action is runtime_action_before_bridge, "Leaving projection changed the shared Action.")
    require(
        matrix_snapshots_close(
            matrix_snapshot({bone.name: bone.matrix.copy() for bone in rig.pose.bones}),
            runtime_pose_before_bridge,
        ),
        "Leaving projection changed a DSB_DAMAGE_RIG pose matrix.",
    )
    require(
        matrix_snapshots_close(
            matrix_snapshot({helper.name: helper.matrix_world.copy() for helper in helpers}),
            socket_worlds_before_bridge,
        ),
        "Leaving projection changed an authored socket matrix.",
    )
    require(
        max(
            abs(
                float(socket_world_before_bridge[row][column])
                - float(socket.matrix_world[row][column])
            )
            for row in range(4)
            for column in range(4)
        ) <= 1.0e-7,
        "Projection bridging changed an authored hand socket transform.",
    )

    draft_material = bpy.data.materials[draft["appearance"]["ownedMaterials"][0]]
    draft_material.diffuse_color = (0.08, 0.16, 0.24, 1.0)
    draft_image = bridged_image
    pixels = list(draft_image.pixels[0:4])
    pixels[0] = 0.77
    draft_image.pixels[0:4] = pixels
    draft_image.update()
    require(draft_image.is_dirty, "The projected texture edit was not represented as dirty pixels.")

    approved = variant_authoring.approve_forge_texture_variant(bpy.context)
    state = variant_authoring.load_state(required=True)
    require(variant_authoring.appearance_status(state) == "APPROVED", state)
    require(not variant_authoring.texture_appearance_errors(state), state)
    require(
        base_material != approved["appearance"]["ownedMaterials"][0],
        "The new look reused the base material datablock.",
    )
    approved_material = bpy.data.materials[approved["appearance"]["ownedMaterials"][0]]
    approved_material.roughness = min(float(approved_material.roughness) + 0.125, 1.0)
    require(
        variant_authoring.appearance_status(variant_authoring.load_state()) == "STALE",
        "A direct material tweak still displayed as ready to export.",
    )
    variant_authoring.edit_forge_texture_variant(bpy.context)
    require(
        variant_authoring.appearance_status(variant_authoring.load_state()) == "DRAFT",
        "Explicit texture editing did not block export.",
    )
    try:
        variant_authoring.replace_active_base_color_texture(bpy.context, ROOT)
    except RuntimeError as exc:
        require("four-view projection-source folder" in str(exc), exc)
    else:
        raise RuntimeError("A projection-source folder was accepted as one final model texture.")
    replacement = (
        ROOT
        / "dreadstone_animation_forge"
        / "assets"
        / "gore_textures"
        / "muscle_fibers_macro_atlas.png"
    )
    replaced_variant, replaced_image = variant_authoring.replace_active_base_color_texture(
        bpy.context,
        replacement,
    )
    require(replaced_image.packed_file is not None, "Replacement Base Color was not packed.")
    require(replaced_image.name in replaced_variant["appearance"]["ownedImages"], replaced_variant)
    require(len(bpy.data.actions) == actions_before, "Texture replacement duplicated an Action.")
    require(len(bpy.data.objects) == objects_before, "Texture replacement duplicated an object.")
    require(len(bpy.data.meshes) == meshes_before, "Texture replacement duplicated a mesh.")
    approved = variant_authoring.approve_forge_texture_variant(bpy.context)
    variant_authoring.switch_variant(base["variantId"])
    require(body.data.materials[0].name == base_material, "Base material did not restore.")
    variant_authoring.switch_variant(approved["variantId"])
    variant_authoring.preview_active_variant(bpy.context)
    require(
        body.data.materials[0].name == approved["appearance"]["ownedMaterials"][0],
        "Approved new material did not apply.",
    )
    require(rig.animation_data.action == shared, "Variant switching replaced shared animation.")
    require(detached.hide_get() and detached.hide_viewport, "Look switching revealed DSB_SEGMENT_HEAD.")

    previous_filename = settings.damage_authoring_filename
    body[model.SBF_FAMILY_ID_PROPERTY] = "legacy-scalar-only"
    with variant_authoring.export_context(
        bpy.context,
        settings,
        {"authoring_rig": "DSB_DAMAGE_RIG"},
    ) as provenance:
        require(provenance["familySource"] == model.FAMILY_SOURCE_FORGE_TEXTURE, provenance)
        require(
            provenance["appearanceApprovalAuthority"]
            == model.FORGE_TEXTURE_APPROVAL_AUTHORITY,
            provenance,
        )
        require(model.SBF_FAMILY_ID_PROPERTY not in body, "Native export invented SBF family metadata.")
        require(settings.damage_authoring_filename == "finished_warden_ashen", settings.damage_authoring_filename)
    require(body[model.SBF_FAMILY_ID_PROPERTY] == "legacy-scalar-only", "Export staging did not restore source extras.")
    require(settings.damage_authoring_filename == previous_filename, settings.damage_authoring_filename)

    output = Path(tempfile.mkdtemp(prefix="daf_finished_texture_variant_"))
    blend = output / "finished_texture_variants.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    reopened = variant_authoring.load_state(required=True)
    require(reopened["activeVariantId"] == approved["variantId"], reopened)
    require(variant_authoring.appearance_status(reopened) == "APPROVED", reopened)
    reopened_sockets = attachment_sockets.runtime_socket_contract(
        runtime_rig=bpy.data.objects["DSB_DAMAGE_RIG"]
    )
    require(reopened_sockets["socketCount"] == socket_contract["socketCount"], reopened_sockets)
    for before_socket, after_socket in zip(socket_contract["sockets"], reopened_sockets["sockets"]):
        require(before_socket["socketId"] == after_socket["socketId"], (before_socket, after_socket))
        require(
            max(
                abs(float(left) - float(right))
                for left, right in zip(before_socket["localPosition"], after_socket["localPosition"])
            ) <= 2.0e-6,
            f"Authored socket position changed: before={before_socket!r} after={after_socket!r}",
        )
        quaternion_dot = abs(
            sum(
                float(left) * float(right)
                for left, right in zip(before_socket["localQuaternion"], after_socket["localQuaternion"])
            )
        )
        require(
            quaternion_dot >= 1.0 - 2.0e-6,
            f"Authored socket rotation changed: before={before_socket!r} after={after_socket!r}",
        )
    require(len(bpy.data.actions) == actions_before, "Save/reopen duplicated Actions.")
    require(len(bpy.data.meshes) == meshes_before, "Save/reopen duplicated body meshes.")
    require(
        bpy.data.materials.get(base_material) is not None,
        "Save/reopen discarded the inactive base-look material.",
    )
    reopened_body = bpy.data.objects["DSB_BODY_CORE"]
    variant_authoring.switch_variant(base["variantId"])
    require(
        reopened_body.data.materials[0].name == base_material,
        "The inactive base look could not be restored after save/reopen.",
    )
    variant_authoring.switch_variant(approved["variantId"])
    variant_authoring.preview_active_variant(bpy.context)

    report = {
        "status": "PASS",
        "blenderVersion": bpy.app.version_string,
        "familySource": reopened["familySource"],
        "appearanceAuthority": model.FORGE_TEXTURE_APPROVAL_AUTHORITY,
        "variantCount": len(reopened["variants"]),
        "actionCopies": len(bpy.data.actions) - actions_before,
        "bodyObjectCopies": len(bpy.data.objects) - objects_before,
        "bodyMeshCopies": len(bpy.data.meshes) - meshes_before,
        "dirtyPixelCaptureApproved": True,
        "directMaterialTweakShowsStale": True,
        "draftCascadeRejected": True,
        "explicitEditSaveCycle": True,
        "oneClickDefaultSetup": True,
        "replacementBaseColorPacked": True,
        "projectionFolderRejectedAsFinalImage": True,
        "skinAndBonesProjectionBridge": True,
        "projectionRigForcedRest": True,
        "projectionReentryForcedRest": True,
        "projectionBakeForcedRest": True,
        "projectionRigPoseRestored": True,
        "neutralProjectionGeometryVerified": True,
        "legacyProjectionRecoveryMigrated": True,
        "corruptProjectionRecoveryRejected": True,
        "failedProjectionRecoveryRetained": True,
        "projectionRecoverySurvivesSaveReopen": True,
        "genericArmatureDataAliasRejected": True,
        "inactiveLookDatablocksPersist": True,
        "runtimeRigPoseAndActionPreserved": True,
        "sharedDamageArmatureDataRejected": True,
        "detachedDamagePiecesStayHidden": True,
        "saveReopen": True,
        "nativeExportHasNoSyntheticSbfHandoff": True,
        "managedSocketScaleRepair": True,
        "authoredSocketPositionRotationPreserved": True,
    }
    print("FINISHED_TEXTURE_VARIANT_ACCEPTANCE=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
