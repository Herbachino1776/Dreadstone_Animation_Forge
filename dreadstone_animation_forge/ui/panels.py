"""Task-oriented panel rendering from small cached state only."""

from __future__ import annotations

from . import properties, workflow_state


def _status_row(box, label, ready, detail=""):
    row = box.row(align=True)
    row.label(text=label, icon='CHECKMARK' if ready else 'RADIOBUT_OFF')
    if detail:
        row.label(text=str(detail)[:72])


def _draw_next_action(layout, state):
    box = layout.box()
    box.alert = workflow_state.next_action(state) not in {"Export"}
    box.label(text="Next: " + workflow_state.next_action(state), icon='TRACKING')


def _draw_start(layout, context, settings, summary):
    box = layout.box()
    box.label(text="Character Processing", icon='OUTLINER_OB_ARMATURE')
    active = context.active_object
    _status_row(box, "Source selected", active is not None, active.name if active else "")
    _status_row(box, "Rig analyzed", bool(settings.manual_hips or settings.manual_spine))
    _status_row(box, "Scale ready", bool(settings.target_height), f"Target {settings.target_height:.2f} m")
    _status_row(
        box,
        "Source Readiness",
        settings.damage_readiness_overall_status in {"READY", "SOURCE READY"},
        settings.damage_readiness_overall_status,
    )
    _status_row(box, "Authoring asset built", settings.damage_authoring_status.startswith("BUILT"), settings.damage_authoring_status)
    regions = summary.get("registry", {}).get("regions", [])
    ids = {region.get("regionId") for region in regions}
    _status_row(box, "Standard regions registered", {"head", "body_core", "forearm_left", "forearm_right"}.issubset(ids), f"{len(ids)} total")
    _status_row(box, "Ready to author impacts", bool(regions) and settings.damage_authoring_status.startswith("BUILT"))
    box.prop(settings, "target_height")
    box.prop(settings, "damage_readiness_output_directory")
    box.operator(
        "daf.prepare_character_for_damage_authoring",
        text="PREPARE CHARACTER FOR DAMAGE AUTHORING",
        icon='MODIFIER_ON',
    )
    box.label(text="Stops on NOT READY; never guesses source repairs", icon='LOCKED')


def _draw_context_card(layout, settings, summary):
    region = summary.get("region", {})
    key = summary.get("key", {})
    stamp = summary.get("stamp", {})
    card = layout.box()
    card.label(text="Active Context", icon='PIVOT_ACTIVE')
    card.label(text=f"Region: {region.get('regionId', '<none>')} / {region.get('regionMode', '<none>')}")
    card.label(text=f"Mesh: {region.get('targetObject', '<none>')}")
    if region.get("detachedObject"):
        card.label(text=f"Detached: {region.get('detachedObject')}")
    card.label(text=f"Deformation: {settings.deformation_active_key or '<none>'}")
    card.label(text=f"Capture: {'READY' if settings.deformation_seed_center_valid else 'NOT CAPTURED'}")
    card.label(text=f"Stamp: {stamp.get('displayName', '<none>')}")
    card.label(text=f"Preview: {settings.deformation_preview_status}")
    card.label(text=f"Gore: {key.get('goreStatus', 'NOT CONFIGURED')} / {int(key.get('goreTriangles', 0)):,} triangles")
    card.label(text=f"Validation: {key.get('validationStatus', settings.last_deformation_validation)}")


def _draw_damage(layout, context, settings, summary):
    _draw_context_card(layout, settings, summary)
    regions = layout.box()
    regions.label(text="Choose Region", icon='MESH_DATA')
    row = regions.row(align=True)
    for region_id, label in properties.STANDARD_REGION_BUTTONS[:2]:
        op = row.operator("daf.activate_standard_region", text=label)
        op.region_id = region_id
    row = regions.row(align=True)
    for region_id, label in properties.STANDARD_REGION_BUTTONS[2:]:
        op = row.operator("daf.activate_standard_region", text=label)
        op.region_id = region_id
    row = regions.row(align=True)
    row.operator("daf.new_compound_trauma_event", text="Compound Event", icon='LINKED')
    custom = row.operator("daf.select_deformation_region", text="Custom Region", icon='RESTRICT_SELECT_OFF')

    draft = layout.box()
    draft.label(text="Create Impact Draft", icon='MOD_DISPLACE')
    draft.prop(settings, "deformation_impact_preset")
    draft.prop(settings, "deformation_stamp_family", text="Impact Family")
    draft.prop(settings, "deformation_impact_intensity")
    draft.prop(settings, "deformation_seed_direction_mode", text="Impact Direction")
    draft.prop(settings, "deformation_impact_semantic_name")
    draft.operator(
        "daf.create_impact_from_selection",
        text="CREATE IMPACT FROM CURRENT SELECTION",
        icon='ADD',
    )
    draft.label(text="The selected connected surface remains the artist's decision", icon='INFO')

    tune = layout.box()
    tune.label(text="Impact Tuning", icon='DRIVER_DISTANCE')
    tune.prop(settings, "deformation_seed_radius", text="Radius")
    tune.prop(settings, "deformation_seed_depth", text="Depth")
    tune.prop(settings, "deformation_seed_falloff", text="Falloff")
    tune.prop(settings, "deformation_seed_direction_mode", text="Impact Direction")
    tune.prop(settings, "deformation_stamp_family", text="Shape")
    tune.prop(settings, "deformation_seed_seam_protection", text="Seam Safety")
    tune.prop(settings, "deformation_gore_coverage", text="Gore Amount", slider=True)
    tune.prop(settings, "deformation_gore_clot_thickness", text="Gore Thickness")
    tune.prop(settings, "deformation_gore_island_breakup", text="Gore Breakup", slider=True)
    tune.prop(settings, "deformation_live_preview")
    tune.prop(settings, "deformation_preview_quality")
    status = tune.box()
    status.label(text=f"{settings.deformation_preview_status}: {settings.deformation_preview_message}")
    status.label(text=f"{settings.deformation_preview_elapsed_ms:.1f} ms / {settings.deformation_preview_affected_vertices:,} vertices")
    status.label(text=f"Gore estimate/final: {settings.deformation_preview_estimated_gore_triangles:,} / {settings.deformation_preview_final_gore_triangles:,} triangles")
    row = tune.row(align=True)
    row.operator("daf.commit_impact", text="Commit", icon='CHECKMARK')
    row.operator("daf.revert_impact", text="Revert", icon='RECOVER_LAST')
    row.operator("daf.clear_managed_preview", text="Clear Preview", icon='X')
    row = tune.row(align=True)
    row.operator("daf.final_impact_preview", text="Final Preview", icon='SHADING_RENDERED')
    row.operator("daf.undo_impact_draft", text="Undo Draft", icon='LOOP_BACK')


def _draw_animation(layout, settings):
    setup = layout.box()
    setup.label(text="Animation Setup", icon='ARMATURE_DATA')
    row = setup.row(align=True)
    row.operator("daf.analyze", text="Analyze Rig")
    row.operator("daf.safe_resize", text="Safe Resize")
    setup.operator("daf.adopt_imported_pack", text="Adopt Imported Animation Pack")
    draft = layout.box()
    draft.label(text="Draft Actions", icon='ACTION')
    draft.operator("daf.walk", text="Generate Walk Draft")
    row = draft.row(align=True)
    row.operator("daf.hurt_left", text="Left Hurt")
    row.operator("daf.hurt_right", text="Right Hurt")
    draft.operator("daf.collapse", text="Generate Death / Collapse Draft")
    draft.operator("daf.generate_mace_head_guards", text="Generate Three Mace Head-Guard Drafts")
    pack = layout.box()
    pack.label(text="Approved Animation Pack", icon='PACKAGE')
    pack.prop(settings, "pack_output_directory")
    pack.prop(settings, "pack_filename")
    row = pack.row(align=True)
    row.operator("daf.build_approved_pack", text="Build Approved Pack")
    row.operator("daf.validate_last_pack", text="Validate Last Pack")


def _draw_export(layout, settings):
    validation = layout.box()
    validation.label(text="Focused Validation", icon='CHECKMARK')
    row = validation.row(align=True)
    row.operator("daf.validate_deformations", text="Validate Morph Targets")
    row.operator("daf.validate_gore_geometry", text="Validate Gore Geometry")
    validation.operator("daf.validate_compound_trauma_event", text="Validate Compound Event")
    validation.operator("daf.validate_mace_head_guards", text="Validate Mace Head-Guard Drafts")
    validation.operator("daf.validate_damage_authoring_asset", text="Validate Complete Damage Asset")
    export = layout.box()
    export.label(text="Damage Export", icon='EXPORT')
    export.prop(settings, "damage_authoring_output_directory")
    export.prop(settings, "damage_authoring_filename")
    export.operator("daf.export_damage_asset", text="Export Damage GLB + Manifest")
    export.operator("daf.restore_imported_damage_intact_preview", text="Restore Reimported GLB Intact Preview")


def _draw_advanced(layout, context, settings, deformation_draw):
    manual = layout.box()
    manual.label(text="Manual Character and Source Workflows", icon='TOOL_SETTINGS')
    manual.prop(settings, "target_height")
    row = manual.row(align=True)
    row.operator("daf.analyze", text="Analyze Rig")
    row.operator("daf.safe_resize", text="Safe Resize")
    manual.prop(settings, "damage_readiness_output_directory")
    row = manual.row(align=True)
    row.operator("daf.analyze_damage_readiness", text="Analyze Source Damage Readiness")
    row.operator("daf.repair_source_readiness_contract", text="Repair Source Readiness Contract")
    manual.prop(settings, "damage_authoring_report_path")
    row = manual.row(align=True)
    row.operator("daf.load_damage_readiness_handoff", text="Load READY Handoff")
    row.operator("daf.build_damage_authoring_asset", text="Build Authoring Asset")
    manual.operator("daf.clear_damage_authoring_asset", text="Clear Generated Asset / Restore Source")

    trauma = layout.box()
    trauma.label(text="Advanced Trauma, Gore, Compound, and Legacy Tools", icon='MODIFIER')
    deformation_draw(trauma, context, settings)

    diagnostics = layout.box()
    diagnostics.label(text="Diagnostics and Crash Support", icon='INFO')
    diagnostic_state = deformation_authoring.cached_diagnostics_summary()
    if diagnostic_state:
        handlers = diagnostic_state.get("handlers", {})
        timers = diagnostic_state.get("timers", {})
        caches = diagnostic_state.get("caches", {})
        gore = diagnostic_state.get("generatedGore", {})
        datablocks = diagnostic_state.get("datablocks", {})
        active = diagnostic_state.get("activeContext", {})
        validations = diagnostic_state.get("validationStates", {})
        diagnostics.label(text=f"Forge {diagnostic_state.get('forgeVersion', '')} / Blender {diagnostic_state.get('blenderVersion', '')}")
        diagnostics.label(text=f"Handlers: load {handlers.get('load_post', 0)} / Preview timer: {'ON' if timers.get('forgePreviewRegistered') else 'OFF'}")
        diagnostics.label(text=f"Caches: {sum(int(value) for value in caches.values())} / Gore: {gore.get('objects', 0)} objects, {gore.get('triangles', 0)} tris")
        diagnostics.label(text=f"Data: {datablocks.get('objects', 0)} objects / {datablocks.get('meshes', 0)} meshes / {datablocks.get('materials', 0)} materials")
        diagnostics.label(text=f"Active: {active.get('region', '-') or '-'} / {active.get('key', '-') or '-'} / {active.get('captureStatus', 'EMPTY')}")
        diagnostics.label(text=f"Validation: source {validations.get('sourceReadiness', '-')} / authoring {validations.get('authoring', '-')} / export {validations.get('export', '-')}")
        operations = diagnostic_state.get("lastOperations", [])
        if operations:
            last = operations[-1]
            diagnostics.label(text=f"Last: {last.get('name', '')} / {last.get('elapsedMs', 0)} ms / {last.get('status', '')}")
        exception = diagnostic_state.get("lastException", {})
        if exception:
            diagnostics.label(text=f"Exception: {exception.get('type', '')} / {exception.get('stage', '')}", icon='ERROR')
    else:
        diagnostics.label(text="Run Startup Self-Check to refresh the cached summary.")
    diagnostics.prop(settings, "diagnostics_output_directory")
    row = diagnostics.row(align=True)
    row.operator("daf.write_forge_diagnostic_report", text="WRITE FORGE DIAGNOSTIC REPORT")
    row.operator("daf.forge_startup_self_check", text="Startup Self-Check")


def draw_main_panel(layout, context, settings, deformation_draw):
    from .. import deformation_authoring

    summary = deformation_authoring.cached_ui_summary(settings)
    state = workflow_state.dashboard_state(context, settings, summary)
    layout.prop(settings, "ui_workspace", expand=True)
    _draw_next_action(layout, state)
    if settings.ui_workspace == 'START':
        _draw_start(layout, context, settings, summary)
    elif settings.ui_workspace == 'DAMAGE':
        _draw_damage(layout, context, settings, summary)
    elif settings.ui_workspace == 'ANIMATION':
        _draw_animation(layout, settings)
    elif settings.ui_workspace == 'EXPORT':
        _draw_export(layout, settings)
    else:
        _draw_advanced(layout, context, settings, deformation_draw)
