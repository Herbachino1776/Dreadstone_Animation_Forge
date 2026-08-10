"""Task-oriented panel rendering from small cached state only."""

from __future__ import annotations

import json

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
    _status_row(
        box,
        "Creature anatomy analyzed",
        settings.anatomy_readiness_status in {"HUMANOID_READY", "QUADRUPED_READY"},
        settings.anatomy_readiness_status,
    )
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


def _draw_advanced_impact_internals(layout, settings):
    advanced = layout.box()
    row = advanced.row(align=True)
    opened = bool(settings.ui_advanced_impact_internals_open)
    row.prop(
        settings,
        "ui_advanced_impact_internals_open",
        text="Advanced Impact Internals",
        icon='TRIA_DOWN' if opened else 'TRIA_RIGHT',
        emboss=False,
    )
    if not opened:
        return
    mode = str(settings.deformation_impact_control_mode)
    advanced.label(
        text=f"Mode: {mode}  /  Recipe: {'IMPACT PEDAL' if mode == 'MACRO' else 'CUSTOM'}",
        icon='OPTIONS',
    )
    if mode == 'MACRO':
        advanced.label(text="Derived physical values are read-only while macros are authoritative.", icon='LOCKED')
        advanced.operator("daf.use_manual_impact_control", text="USE MANUAL CONTROL", icon='UNLOCKED')
    else:
        advanced.label(text="Manual values are authoritative; macros will not overwrite them.", icon='EDITMODE_HLT')
        row = advanced.row(align=True)
        row.operator("daf.fit_impact_macros", text="FIT MACROS TO CURRENT VALUES", icon='DRIVER')
        row.operator("daf.return_to_macro_control", text="RETURN TO MACRO CONTROL", icon='LOOP_BACK')

    raw = advanced.column()
    raw.enabled = mode == 'MANUAL'
    stamp = raw.box()
    stamp.label(text="Physical Stamp Recipe", icon='MOD_DISPLACE')
    for name in (
        "deformation_seed_radius", "deformation_seed_depth", "deformation_seed_falloff",
        "deformation_stamp_strength", "deformation_feather_distance",
        "deformation_seed_seam_protection", "deformation_max_vertex_displacement",
        "deformation_maximum_influence", "deformation_impact_gore_patch_scale",
    ):
        stamp.prop(settings, name)
    stamp.prop(settings, "deformation_influence_mode")
    stamp.prop(settings, "deformation_distance_mode")
    stamp.prop(settings, "deformation_seed_custom_direction")



def _draw_advanced_gore_internals(layout, settings):
    advanced = layout.box()
    row = advanced.row(align=True)
    opened = bool(settings.ui_advanced_gore_internals_open)
    row.prop(
        settings,
        "ui_advanced_gore_internals_open",
        text="Advanced Gore Internals",
        icon="TRIA_DOWN" if opened else "TRIA_RIGHT",
        emboss=False,
    )
    if not opened:
        return
    mode = str(settings.deformation_gore_control_mode)
    advanced.label(
        text=f"Mode: {mode}  /  Recipe: {'GORE PEDAL' if mode == 'MACRO' else 'CUSTOM'}",
        icon="OPTIONS",
    )
    if mode == "MACRO":
        advanced.label(
            text="Derived physical values are read-only while the Gore Pedal is authoritative.",
            icon="LOCKED",
        )
        advanced.operator(
            "daf.use_manual_gore_control",
            text="USE MANUAL GORE CONTROL",
            icon="UNLOCKED",
        )
    else:
        advanced.label(
            text="Manual values are authoritative; macro groups will not overwrite them.",
            icon="EDITMODE_HLT",
        )
        advanced.operator(
            "daf.return_to_gore_macro_control",
            text="RETURN TO GORE PEDAL",
            icon="LOOP_BACK",
        )
    raw = advanced.column()
    raw.enabled = mode == "MANUAL"
    identity = raw.box()
    identity.label(text="Recipe Identity & Layers", icon="MATERIAL")
    for name in (
        "deformation_gore_enabled",
        "deformation_gore_geometry_mode",
        "deformation_gore_raised_enabled",
        "deformation_gore_wound_bed_enabled",
        "deformation_gore_clot_layer_enabled",
        "deformation_gore_tissue_layer_enabled",
        "deformation_gore_bone_layer_enabled",
        "deformation_gore_barrier_layer_enabled",
        "deformation_gore_raised_rim_opt_in",
        "deformation_gore_allow_internal_fragments",
    ):
        identity.prop(settings, name)
    geometry = raw.box()
    geometry.label(text="Scale-Relative Cavity Geometry", icon="MOD_DISPLACE")
    for name in (
        "deformation_gore_cavity_depth",
        "deformation_gore_liner_separation",
        "deformation_gore_rim_width",
        "deformation_gore_clot_fill_depth",
        "deformation_gore_proudness_limit",
        "deformation_gore_host_deformation_contribution",
        "deformation_gore_bone_reveal",
        "deformation_gore_tissue_coverage",
        "deformation_gore_geometry_density",
        "deformation_gore_maximum_triangles",
    ):
        geometry.prop(settings, name)
    stain = raw.box()
    stain.label(text="Stain, Material & Legacy Fields", icon="SHADING_RENDERED")
    for name in (
        "deformation_gore_coverage", "deformation_gore_scatter",
        "deformation_gore_edge_feather", "deformation_gore_wetness",
        "deformation_gore_darkness", "deformation_gore_clot_coverage",
        "deformation_gore_core_density",
        "deformation_gore_surface_mass_value",
        "deformation_gore_nucleus_amount",
        "deformation_gore_nucleus_lobes",
        "deformation_gore_clot_thickness",
        "deformation_gore_thickness_variation", "deformation_gore_island_breakup",
        "deformation_gore_peripheral_fragments", "deformation_gore_surface_offset",
        "deformation_gore_wetness_variation", "deformation_gore_dark_clot_bias",
        "deformation_gore_rough_edge_bias", "deformation_gore_color_intensity",
        "deformation_gore_organic_irregularity", "deformation_gore_surface_roundness",
        "deformation_gore_fiber_texture_strength", "deformation_gore_base_color_strength",
        "deformation_gore_inner_rim_width", "deformation_gore_inner_rim_strength",
        "deformation_gore_mask_seed",
    ):
        stain.prop(settings, name)
    stain.prop(settings, "deformation_gore_color_bias")
    stain.prop(settings, "deformation_gore_texture_enabled")
    stain.prop(settings, "deformation_gore_inner_rim_enabled")
    measurements = advanced.box()
    measurements.label(text="Current Validation Measurements", icon="CHECKMARK")
    measurements.label(
        text=f"Maximum proudness: {settings.deformation_gore_max_proudness:.6f} m"
    )
    measurements.label(
        text=f"Median liner depth: {settings.deformation_gore_median_cavity_depth:.6f} m"
    )
    measurements.label(
        text=(
            "Minimum skin-to-liner separation: "
            f"{settings.deformation_gore_minimum_liner_separation:.6f} m"
        )
    )


def _draw_progressive_damage_sites(layout, context, settings):
    from .. import progressive_authoring

    state = progressive_authoring.cached_ui_state(context)
    collection = state["collection"]
    site = state["site"]
    stage = state["stage"]
    stage_name = state["stageName"]
    box = layout.box()
    header = box.row(align=True)
    opened = bool(settings.ui_progressive_sites_open)
    header.scale_y = 1.28
    header.prop(
        settings,
        "ui_progressive_sites_open",
        text="PROGRESSIVE DAMAGE SITES",
        icon="TRIA_DOWN" if opened else "TRIA_RIGHT",
        emboss=False,
    )
    if not opened:
        return

    if not site:
        box.label(
            text="Organize three fully custom Damage Keys into one runtime site.",
            icon="INFO",
        )
        create = box.column()
        create.scale_y = 1.45
        create.operator(
            "daf.new_progressive_site",
            text="NEW DAMAGE SITE",
            icon="ADD",
        )
        return

    completion = sum(
        bool(value.get("damageKeyId"))
        for value in site.get("stages", {}).values()
    )
    card = box.box()
    title = card.row(align=True)
    title.label(text=str(site["displayName"]), icon="PINNED")
    title.label(
        text=f"{completion} / 3 · {site['status'].replace('_', ' ')}",
        icon=(
            "CHECKMARK"
            if site["status"] == "READY_FOR_EXPORT"
            else "ERROR"
            if site["status"] == "FAILED"
            else "INFO"
        ),
    )
    card.label(
        text=(
            f"Region {site['regionId']} · Group {site['structuralGroup']} · "
            f"Export {'ON' if site['enabledForExport'] else 'OFF'}"
        )
    )

    sites = list(collection.get("sites", []))
    if len(sites) > 1:
        selector = card.box()
        selector.label(text="SELECT SITE", icon="RESTRICT_SELECT_OFF")
        for candidate in sites:
            op = selector.operator(
                "daf.select_progressive_site",
                text=str(candidate["displayName"]),
                icon=(
                    "RADIOBUT_ON"
                    if candidate["siteGuid"] == site["siteGuid"]
                    else "RADIOBUT_OFF"
                ),
                depress=candidate["siteGuid"] == site["siteGuid"],
            )
            op.site_guid = str(candidate["siteGuid"])
    actions = card.row(align=True)
    actions.operator(
        "daf.new_progressive_site",
        text="NEW DAMAGE SITE",
        icon="ADD",
    )
    actions.operator(
        "daf.duplicate_progressive_site_metadata",
        text="DUPLICATE SITE METADATA",
        icon="DUPLICATE",
    )
    name = card.row(align=True)
    name.prop(settings, "progression_site_name", text="")
    name.operator(
        "daf.rename_progressive_site",
        text="RENAME SITE",
        icon="GREASEPENCIL",
    )
    remove = card.row()
    remove.alert = True
    remove.operator(
        "daf.delete_progressive_site_metadata",
        text="DELETE SITE METADATA",
        icon="TRASH",
    )

    tabs = box.box()
    tabs.label(text="STAGES · COMPLETE RESULTS RELATIVE TO BASIS")
    row = tabs.row(align=True)
    row.scale_y = 1.65
    for name in ("LIGHT", "MEDIUM", "HEAVY"):
        record = site["stages"][name]
        assigned = bool(record.get("damageKeyId"))
        invalid = str(record.get("validationStatus", "")) in {"FAIL", "FAILED"}
        dirty = bool(record.get("dirty", False)) or (
            assigned and not bool(record.get("saved", False))
        )
        icon = (
            "ERROR"
            if invalid
            else "GREASEPENCIL"
            if dirty
            else "CHECKMARK"
            if assigned and record.get("validationStatus") == "PASS"
            else "LAYER_ACTIVE"
            if assigned
            else "RADIOBUT_OFF"
        )
        stage_row = row.row(align=True)
        stage_row.alert = invalid
        op = stage_row.operator(
            "daf.focus_progressive_stage",
            text=name,
            icon=icon,
            depress=name == stage_name,
        )
        op.stage = name
    tabs.label(
        text="Neutral / amber / caution intent uses Blender-native icons and state emphasis."
    )

    active = box.box()
    active.label(text=f"ACTIVE STAGE · {stage_name}", icon="EDITMODE_HLT")
    if not stage.get("damageKeyId"):
        active.label(text="Unassigned · choose or create an independent Damage Key")
    else:
        active.label(
            text=f"Damage Key · {stage.get('deformationKeyName', '')}",
            icon="SHAPEKEY_DATA",
        )
        active.label(
            text=(
                f"Stamp · {stage.get('activeStampId', '') or '<none>'} · "
                f"{'DIRTY' if stage.get('dirty') else 'SAVED' if stage.get('saved') else 'UNSAVED'}"
            )
        )
        active.label(
            text=(
                f"Validation · {stage.get('validationStatus', 'EMPTY')} · "
                f"Gore {len(stage.get('generatedNodeNames', {}))} nodes · "
                f"{int(stage.get('triangleCount', 0)):,} tris"
            )
        )
        active.label(
            text="Ownership · "
            + (", ".join(stage.get("ownershipRoles", [])) or "not generated")
        )
    action = active.column()
    action.scale_y = 1.25
    assign = action.operator(
        "daf.assign_progressive_stage",
        text="ASSIGN ACTIVE DAMAGE KEY",
        icon="LINKED",
    )
    assign.stage = stage_name
    create = action.operator(
        "daf.create_progressive_stage_key",
        text="CREATE NEW KEY FOR THIS STAGE",
        icon="ADD",
    )
    create.stage = stage_name
    duplicate = action.operator(
        "daf.duplicate_progressive_stage_key",
        text="DUPLICATE ACTIVE KEY AS STARTING POINT",
        icon="DUPLICATE",
    )
    duplicate.stage = stage_name
    if stage.get("damageKeyId"):
        go = active.operator(
            "daf.focus_progressive_stage",
            text="GO TO ASSIGNED KEY",
            icon="RESTRICT_SELECT_OFF",
        )
        go.stage = stage_name
        unassign = active.row()
        unassign.alert = True
        op = unassign.operator(
            "daf.unassign_progressive_stage",
            text="UNASSIGN STAGE · PRESERVE KEY",
            icon="UNLINKED",
        )
        op.stage = stage_name
    active.operator(
        "daf.set_progressive_site_anchor",
        text="SET SITE ANCHOR FROM ACTIVE STAGE",
        icon="PIVOT_CURSOR",
    )
    active.label(
        text="Stage focus loads the existing Impact/Gore macros directly below.",
        icon="INFO",
    )

    deck = box.box()
    deck.label(text="PROGRESSION CONTROL DECK", icon="DRIVER")
    severity = deck.column()
    severity.scale_y = 1.35
    severity.prop(settings, "progression_severity", slider=True)
    deck.prop(settings, "progression_live_preview")
    preview = deck.column()
    preview.scale_y = 1.45
    op = preview.operator(
        "daf.refresh_progression_preview",
        text="PREVIEW SITE IN ISOLATION",
        icon="SHADING_RENDERED",
    )
    op.with_other_damage = False
    refresh = deck.column()
    refresh.scale_y = 1.40
    op = refresh.operator(
        "daf.refresh_progression_preview",
        text="REFRESH PROGRESSION PREVIEW",
        icon="FILE_REFRESH",
    )
    op.with_other_damage = bool(
        settings.progression_preview_with_other_damage
    )
    other = deck.operator(
        "daf.refresh_progression_preview",
        text="PREVIEW WITH OTHER DAMAGE",
        icon="HIDE_OFF",
    )
    other.with_other_damage = True
    clear = deck.column()
    clear.alert = bool(settings.progression_preview_active)
    clear.scale_y = 1.20
    clear.operator(
        "daf.clear_progression_preview",
        text="CLEAR PROGRESSION PREVIEW",
        icon="X",
    )
    deck.label(
        text=(
            f"Basis {settings.progression_weight_basis:.3f} · "
            f"Light {settings.progression_weight_light:.3f} · "
            f"Medium {settings.progression_weight_medium:.3f} · "
            f"Heavy {settings.progression_weight_heavy:.3f}"
        )
    )
    deck.label(
        text=(
            f"Detailed gore · {settings.progression_detailed_gore_stage} · "
            f"{settings.progression_transition_status}"
        )
    )
    validate = deck.column()
    validate.scale_y = 1.45
    validate.operator(
        "daf.validate_progressive_site",
        text="VALIDATE ALL CROSSFADE STATES",
        icon="CHECKMARK",
    )
    enable = deck.column()
    enable.scale_y = 1.55
    if site["enabledForExport"]:
        enable.operator(
            "daf.disable_progressive_site_export",
            text="DISABLE SITE EXPORT",
            icon="CANCEL",
        )
    else:
        enable.operator(
            "daf.enable_progressive_site_export",
            text="VALIDATE + ENABLE SITE FOR EXPORT",
            icon="EXPORT",
        )
    if settings.progression_status:
        deck.label(text=str(settings.progression_status)[:110], icon="INFO")

    advanced = box.box()
    advanced.prop(
        settings,
        "ui_progressive_advanced_open",
        text="Advanced Progressive Site Settings",
        icon=(
            "TRIA_DOWN"
            if settings.ui_progressive_advanced_open
            else "TRIA_RIGHT"
        ),
        emboss=False,
    )
    if settings.ui_progressive_advanced_open:
        advanced.label(text=f"Site ID · {site['siteId']}")
        advanced.label(text=f"Site GUID · {site['siteGuid']}")
        advanced.prop(settings, "progression_site_name")
        advanced.label(text=f"Registered Region · {site['regionId']}")
        advanced.prop(settings, "progression_structural_group")
        advanced.prop(settings, "progression_anchor_local")
        advanced.prop(settings, "progression_radius")
        advanced.prop(settings, "progression_preferred_direction")
        advanced.prop(settings, "progression_light_anchor")
        advanced.prop(settings, "progression_medium_anchor")
        advanced.prop(settings, "progression_heavy_anchor")
        advanced.prop(settings, "progression_transition_mode")
        advanced.prop(settings, "progression_transition_curve")
        advanced.prop(settings, "progression_gore_transition_mode")
        advanced.label(
            text=f"Include in Export · {'YES' if site['enabledForExport'] else 'NO'}"
        )
        cost = site.get("cost", {})
        advanced.label(
            text=(
                f"Cost · resident {int(cost.get('residentStageGoreTriangles', 0)):,} · "
                f"visible {int(cost.get('maximumVisibleStageGoreTriangles', 0)):,} · "
                f"transition {int(cost.get('maximumTransitionGoreTriangles', 0)):,}"
            )
        )
        for name in ("LIGHT", "MEDIUM", "HEAVY"):
            record = site["stages"][name]
            advanced.label(
                text=(
                    f"{name} · {record.get('stageId', '')} · "
                    f"{record.get('damageKeyId', '') or '<unassigned>'}"
                )
            )
            if record.get("damageKeyId"):
                advanced.label(
                    text=(
                        "Digests · "
                        f"{record.get('recipeDigest', '')[:10]} / "
                        f"{record.get('deformationDigest', '')[:10]} / "
                        f"{record.get('captureDigest', '')[:10]}"
                    )
                )


def _draw_vip_damage_workflow(layout, context, settings, summary):
    vip = layout.box()
    header = vip.row(align=True)
    opened = bool(settings.ui_vip_damage_open)
    header.scale_y = 1.28
    header.prop(
        settings,
        "ui_vip_damage_open",
        text="VIP DAMAGE WORKFLOW",
        icon="TRIA_DOWN" if opened else "TRIA_RIGHT",
        emboss=False,
    )
    if not opened:
        return

    vip.label(
        text="DAMAGE KEYS + STAMPS + MACROS",
        icon="MOD_DISPLACE",
    )
    registry_summary = summary.get("registry", {})
    metadata_summary = summary.get("metadata", {})
    active_region_id = str(
        registry_summary.get(
            "activeRegionId",
            metadata_summary.get("regionId", ""),
        )
    )
    region = vip.box()
    region.label(text="1 · PLACE", icon="RESTRICT_SELECT_OFF")
    rows = (
        properties.STANDARD_REGION_BUTTONS[:2],
        properties.STANDARD_REGION_BUTTONS[2:],
    )
    for region_buttons in rows:
        row = region.row(align=True)
        for region_id, label in region_buttons:
            op = row.operator(
                "daf.activate_standard_region",
                text=label,
                depress=region_id == active_region_id,
            )
            op.region_id = region_id
    region.prop(settings, "deformation_seed_direction_mode", text="Direction")
    region.prop(settings, "deformation_impact_semantic_name", text="Damage Key Name")
    create = region.column()
    create.scale_y = 1.55
    create.operator(
        "daf.create_impact_from_selection",
        text="CREATE DAMAGE KEY FROM SELECTION",
        icon="ADD",
    )
    region.label(
        text="Select vertex/vertices, one face, or one connected face patch.",
        icon="INFO",
    )

    keys = list(metadata_summary.get("keys", []))
    requested_key_name = str(settings.deformation_active_key)
    current_key_names = {str(key.get("name", "")) for key in keys}
    active_key_name = (
        requested_key_name
        if requested_key_name in current_key_names
        else ""
    )
    enabled_count = sum(bool(key.get("previewEnabled", False)) for key in keys)
    rack = vip.box()
    rack.label(
        text=f"2 · DAMAGE KEYS  ·  {enabled_count} PREVIEWING",
        icon="SHAPEKEY_DATA",
    )
    if not keys:
        region_label = next(
            (
                label
                for region_id, label in properties.STANDARD_REGION_BUTTONS
                if region_id == active_region_id
            ),
            active_region_id or "selected region",
        )
        rack.label(
            text=f"No Damage Keys in {region_label} yet.",
            icon="INFO",
        )
    for key in keys:
        key_name = str(key.get("name", ""))
        focused = key_name == active_key_name
        preview_enabled = bool(key.get("previewEnabled", False))
        card = rack.box()
        title = card.row(align=True)
        title.alert = focused
        select = title.operator(
            "daf.select_deformation_key",
            text=(
                f"WORKING ON · {key_name.upper()}"
                if focused else key_name
            ),
            icon="RADIOBUT_ON" if focused else "RADIOBUT_OFF",
            depress=focused,
        )
        select.key_name = key_name
        toggle = title.operator(
            "daf.toggle_damage_key_preview",
            text="PREVIEW ON" if preview_enabled else "PREVIEW OFF",
            icon="HIDE_OFF" if preview_enabled else "HIDE_ON",
            depress=preview_enabled,
        )
        toggle.key_name = key_name
        if focused:
            rename = card.row(align=True)
            rename.prop(settings, "deformation_key_name", text="Rename to")
            rename_action = rename.operator(
                "daf.rename_damage_key",
                text="RENAME",
                icon="CHECKMARK",
            )
            rename_action.key_name = key_name
            card.label(
                text="Use letters, numbers, and underscores.",
                icon="INFO",
            )
        for stamp in key.get("stamps", []):
            stamp_id = str(stamp.get("stampId", ""))
            stamp_active = stamp_id == str(key.get("activeStampId", ""))
            child = card.row(align=True)
            child.separator(factor=0.6)
            stamp_op = child.operator(
                "daf.select_damage_stamp",
                text=(
                    f"STAMP · {stamp.get('displayName', stamp_id)}"
                    + (" · ACTIVE" if focused and stamp_active else "")
                ),
                icon="LAYER_ACTIVE" if stamp_active else "LAYER_USED",
                depress=focused and stamp_active,
            )
            stamp_op.key_name = key_name
            stamp_op.stamp_id = stamp_id
        if focused:
            stamp_actions = card.row(align=True)
            stamp_actions.operator(
                "daf.add_trauma_stamp",
                text="ADD STAMP ALTERNATIVE",
                icon="ADD",
            )
            remove = stamp_actions.row(align=True)
            remove.alert = True
            remove.operator(
                "daf.remove_trauma_stamp",
                text="REMOVE ACTIVE",
                icon="TRASH",
            )

    _draw_progressive_damage_sites(vip, context, settings)

    controls = vip.box()
    controls.enabled = bool(active_key_name)
    controls.label(text="3 · SHAPE THE ACTIVE STAMP", icon="DRIVER")
    impact = controls.box()
    impact.label(text="IMPACT MACROS", icon="MOD_DISPLACE")
    for first, second in (
        ("deformation_impact_size", "deformation_impact_crush"),
        ("deformation_impact_profile", "deformation_impact_edge_safety"),
        ("deformation_impact_chaos", "deformation_impact_asymmetry"),
    ):
        row = impact.row(align=True)
        row.scale_y = 1.22
        row.prop(settings, first, slider=True)
        row.prop(settings, second, slider=True)

    gore = controls.box()
    gore.label(text="ADDITIVE GORE MACROS", icon="MATERIAL")
    gore.prop(settings, "deformation_gore_enabled", text="Gore Enabled")
    row = gore.row(align=True)
    row.scale_y = 1.28
    row.prop(settings, "deformation_gore_raised_amount", slider=True)
    row.prop(settings, "deformation_gore_inlay_amount", slider=True)
    for first, second in (
        ("deformation_gore_exposure", "deformation_gore_breakup"),
        ("deformation_gore_clot_fill", "deformation_gore_wetness_macro"),
    ):
        row = gore.row(align=True)
        row.scale_y = 1.22
        row.prop(settings, first, slider=True)
        row.prop(settings, second, slider=True)
    surface = gore.box()
    surface.label(
        text="COHESIVE LEGACY SURFACE GORE",
        icon="META_BALL",
    )
    for first, second in (
        (
            "deformation_gore_surface_mass",
            "deformation_gore_surface_relief",
        ),
        (
            "deformation_gore_nucleus",
            "deformation_gore_lobes",
        ),
    ):
        row = surface.row(align=True)
        row.scale_y = 1.24
        row.prop(settings, first, slider=True)
        row.prop(settings, second, slider=True)
    row = surface.row()
    row.scale_y = 1.24
    row.prop(settings, "deformation_gore_redness", slider=True)
    surface.label(
        text="Mass joins the shell; Nucleus fills the deepest zone with varied tissue masses.",
        icon="INFO",
    )
    gore.label(
        text=(
            f"{settings.deformation_gore_geometry_mode.replace('_', ' ')}  ·  "
            "Raised and Inlay each reach full strength."
        ),
        icon="CHECKMARK",
    )
    gore.prop(settings, "deformation_preview_quality", text="Preview Quality")
    refresh = gore.column()
    refresh.scale_y = 1.35
    refresh.operator(
        "daf.refresh_impact_preview",
        text="UPDATE GORE PREVIEW",
        icon="SHADING_RENDERED",
    )
    gore.label(
        text="FAST = live stain. BALANCED = live temporary gore geometry.",
        icon="INFO",
    )
    gore.label(
        text="Save commits the approved look; it is not required to preview.",
        icon="CHECKMARK",
    )

    action = controls.column()
    action.scale_y = 1.65
    action.operator(
        "daf.randomize_damage_recipe",
        text="RANDOMIZE DAMAGE",
        icon="FILE_REFRESH",
    )
    save = controls.column()
    save.scale_y = 1.65
    save.operator(
        "daf.save_vip_damage",
        text="SAVE DAMAGE KEY + STAMP + GORE",
        icon="CHECKMARK",
    )

    library = vip.box()
    library.enabled = bool(active_key_name)
    library.label(text="4 · ADAPTIVE BLUEPRINT LIBRARY", icon="ASSET_MANAGER")
    library.label(
        text="Recipes reuse intent and scale—not source vertex IDs.",
        icon="WORLD",
    )
    library.prop(settings, "deformation_blueprint_name", text="Blueprint Name")
    library.prop(
        settings,
        "deformation_blueprint_library_path",
        text="Library File",
    )
    row = library.row(align=True)
    row.operator(
        "daf.save_damage_blueprint",
        text="ADD CURRENT RECIPE",
        icon="BOOKMARKS",
    )
    row.operator(
        "daf.refresh_damage_blueprints",
        text="REFRESH",
        icon="FILE_REFRESH",
    )
    blueprint_summary = summary.get("blueprints", {})
    error = str(blueprint_summary.get("error", ""))
    if error:
        warning = library.row()
        warning.alert = True
        warning.label(text=error[:96], icon="ERROR")
    entries = list(blueprint_summary.get("entries", []))
    if not entries:
        library.label(text="No saved Damage Blueprints loaded.", icon="INFO")
    for entry in entries:
        apply = library.operator(
            "daf.apply_damage_blueprint",
            text=f"APPLY · {entry.get('name', entry.get('blueprintId', ''))}",
            icon="IMPORT",
        )
        apply.blueprint_id = str(entry.get("blueprintId", ""))


def _draw_damage(layout, context, settings, summary):
    _draw_vip_damage_workflow(layout, context, settings, summary)
    _draw_advanced_impact_internals(layout, settings)
    _draw_advanced_gore_internals(layout, settings)


def _animation_foldout(layout, settings, property_name, title, icon='ACTION'):
    box = layout.box()
    row = box.row(align=True)
    opened = bool(getattr(settings, property_name))
    row.prop(
        settings,
        property_name,
        text=title,
        icon='TRIA_DOWN' if opened else 'TRIA_RIGHT',
        emboss=False,
    )
    if opened:
        box.use_property_split = True
        box.use_property_decorate = False
        box.label(text=title, icon=icon)
        return box
    return None


def _draw_vip_animation_library(layout, context, settings):
    from .. import animation_library, find_armature

    library = layout.box()
    header = library.row(align=True)
    header.prop(
        settings,
        "ui_vip_animation_open",
        text="VIP ANIMATION LIBRARY",
        icon=(
            'TRIA_DOWN'
            if settings.ui_vip_animation_open
            else 'TRIA_RIGHT'
        ),
        emboss=False,
    )
    if not settings.ui_vip_animation_open:
        return
    try:
        armature = find_armature(context)
        actions = animation_library.character_actions(
            armature,
            include_drafts=True,
        )
    except Exception as exc:
        library.label(
            text="Select a mesh or armature from the character.",
            icon='INFO',
        )
        library.label(text=str(exc)[:90])
        return

    title = library.row(align=True)
    saved_count = sum(
        not bool(action.get("dsb_draft", False))
        for action in actions
    )
    draft_count = len(actions) - saved_count
    title.label(
        text=(
            f"{armature.name} · {saved_count} SAVED"
            + (f" · {draft_count} DRAFT" if draft_count else "")
        ),
        icon='ARMATURE_DATA',
    )
    title.label(text="Names are editable")
    active_clip_id = str(settings.animation_library_active_clip_id)
    active_name = str(settings.animation_library_active_action)
    for category, label in (
        ("DRAFTS", "CURRENT DRAFTS"),
        ("LOCOMOTION", "LOCOMOTION"),
        ("REACTIONS", "REACTIONS"),
        ("COMBAT", "COMBAT"),
        ("OTHER", "OTHER"),
    ):
        category_actions = [
            action
            for action in actions
            if (
                (
                    category == "DRAFTS"
                    and bool(action.get("dsb_draft", False))
                )
                or (
                    category != "DRAFTS"
                    and not bool(action.get("dsb_draft", False))
                    and animation_library.action_category(action)
                    == category
                )
            )
        ]
        if not category_actions:
            continue
        section = library.box()
        section.label(
            text=f"{label} · {len(category_actions)}",
            icon='ACTION',
        )
        for action in category_actions:
            clip_id = str(
                action.get(
                    animation_library.CLIP_ID_PROPERTY,
                    "",
                )
            )
            selected = (
                (clip_id and clip_id == active_clip_id)
                or (not active_clip_id and action.name == active_name)
            )
            row = section.row(align=True)
            choose = row.operator(
                "daf.animation_library_select",
                text="",
                icon='RADIOBUT_ON' if selected else 'RADIOBUT_OFF',
                depress=selected,
            )
            choose.action_name = action.name
            row.prop(action, "name", text="")
            row.label(
                text=animation_library.infer_action_kind(action)
                .replace("_", " ")
                .title()
            )

    selected_action = animation_library.selected_action(
        settings,
        armature,
        available_actions=actions,
    )
    editing = bool(settings.animation_library_edit_source_clip_id)
    selected_is_draft = bool(
        selected_action
        and selected_action.get("dsb_draft", False)
    )
    selected_is_edit_source = bool(
        selected_action
        and str(
            selected_action.get(
                animation_library.CLIP_ID_PROPERTY,
                "",
            )
        )
        == str(settings.animation_library_edit_source_clip_id)
    )
    if selected_action is not None:
        fps = (
            context.scene.render.fps
            / max(context.scene.render.fps_base, 0.001)
        )
        summary = animation_library.action_summary(
            selected_action,
            fps,
        )
        info = library.row(align=True)
        info.label(
            text=(
                f"{summary['frameStart']}–{summary['frameEnd']} · "
                f"{summary['durationSeconds']:.2f}s"
            ),
            icon='TIME',
        )
        info.label(
            text=(
                f"{summary['fcurveCount']} curves · "
                f"{summary['keyframeCount']} keys"
            )
        )
    elif not actions:
        library.label(
            text="No saved Actions yet. Generate a draft and approve it.",
            icon='INFO',
        )
    else:
        library.label(
            text="Select an animation to play, edit, export, or delete.",
            icon='INFO',
        )

    controls = library.row(align=True)
    play = controls.row(align=True)
    play.enabled = selected_action is not None
    play.operator(
        "daf.animation_library_play",
        text="PLAY",
        icon='PLAY',
    )
    edit = controls.row(align=True)
    edit.enabled = (
        selected_action is not None
        and (selected_is_draft or not editing)
    )
    edit.operator(
        "daf.animation_library_edit",
        text="EDIT",
        icon='GREASEPENCIL',
    )
    save = controls.row(align=True)
    save.enabled = (
        selected_is_draft
        or (editing and selected_is_edit_source)
    )
    save.operator(
        (
            "daf.animation_library_finalize_draft"
            if selected_is_draft
            else "daf.animation_library_save"
        ),
        text="SAVE",
        icon='FILE_TICK',
    )
    delete = controls.row(align=True)
    delete.enabled = selected_action is not None
    delete.operator(
        "daf.animation_library_delete",
        text="DELETE",
        icon='TRASH',
    )

    if editing:
        edit_row = library.row(align=True)
        edit_row.alert = True
        edit_row.label(
            text=(
                "EDIT DRAFT · "
                + str(settings.animation_library_edit_source)
            ),
            icon='GREASEPENCIL',
        )
        edit_row.operator(
            "daf.animation_library_cancel_edit",
            text="CANCEL",
            icon='LOOP_BACK',
        )
        library.label(
            text="All draft sliders below remain available; SAVE overwrites the original.",
            icon='INFO',
        )
    elif selected_is_draft:
        library.label(
            text="CURRENT DRAFT · EDIT keeps sliders live; SAVE creates the finalized animation.",
            icon='GREASEPENCIL',
        )

    transfer = library.box()
    transfer.label(text="PORTABLE ANIMATION CLIPS", icon='PACKAGE')
    transfer.prop(settings, "animation_clip_directory")
    export_row = transfer.row(align=True)
    export_row.enabled = (
        selected_action is not None
        and not selected_is_draft
    )
    export_row.operator(
        "daf.animation_library_export",
        text="EXPORT SELECTED",
        icon='EXPORT',
    )
    transfer.prop(settings, "animation_clip_import_path")
    transfer.operator(
        "daf.animation_library_import",
        text="IMPORT TO CHARACTER",
        icon='IMPORT',
    )
    transfer.label(
        text="Missing bones/parents block import; rest/proportion differences warn.",
        icon='INFO',
    )
    if settings.animation_library_status:
        library.label(
            text=str(settings.animation_library_status)[:100],
            icon='INFO',
        )


def _draw_anatomy_card(layout, settings):
    card = layout.box()
    status = str(settings.anatomy_readiness_status)
    card.alert = status not in {
        "NOT_ANALYZED", "HUMANOID_READY", "QUADRUPED_READY",
    }
    card.label(text="Creature Anatomy", icon='ARMATURE_DATA')
    card.label(text=f"Creature Class · {settings.anatomy_detected_creature_class}")
    card.label(text=f"Profile · {settings.anatomy_selected_profile}")
    row = card.row(align=True)
    row.label(text=f"Confidence · {settings.anatomy_detection_confidence:.0%}")
    row.label(text=f"Roles · {settings.anatomy_mapped_role_count}")
    card.label(text=f"Orientation · {settings.anatomy_orientation_summary}")
    card.label(
        text=f"Readiness · {status}",
        icon='CHECKMARK' if status in {"HUMANOID_READY", "QUADRUPED_READY"} else 'ERROR' if card.alert else 'INFO',
    )
    if settings.anatomy_worst_blocker:
        blocker = card.box()
        blocker.alert = True
        blocker.label(text=str(settings.anatomy_worst_blocker)[:100], icon='ERROR')
    action = card.row()
    action.scale_y = 1.25
    action.operator(
        "daf.analyze_creature_anatomy",
        text="ANALYZE CREATURE ANATOMY",
        icon='VIEWZOOM',
    )
    card.prop(settings, "anatomy_profile_override")
    row = card.row(align=True)
    row.operator("daf.show_anatomy_role_mapping", text="SHOW ROLE MAPPING", icon='TEXT')
    row.operator("daf.clear_anatomy_profile_override", text="CLEAR PROFILE OVERRIDE", icon='LOOP_BACK')

    card.prop(
        settings,
        "ui_anatomy_advanced_open",
        text="Advanced Anatomy Mapping",
        icon='TRIA_DOWN' if settings.ui_anatomy_advanced_open else 'TRIA_RIGHT',
        emboss=False,
    )
    if settings.ui_anatomy_advanced_open:
        advanced = card.box()
        try:
            mapping = json.loads(str(settings.anatomy_role_mapping_json or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            mapping = {}
        if not mapping:
            advanced.label(text="No persisted role mapping. Run analysis.", icon='INFO')
        else:
            for role, value in sorted(mapping.items()):
                display = " > ".join(value) if isinstance(value, list) else str(value)
                advanced.label(text=f"{role} · {display}"[:110], icon='BONE_DATA')
        advanced.label(text="Detailed diagnostics are stored in DSB_Creature_Anatomy_Mapping.json", icon='TEXT')


def _draw_animation_setup(layout, context, settings):
    setup = layout.box()
    setup.label(text="Animation Setup", icon='ARMATURE_DATA')
    _draw_anatomy_card(setup, settings)
    setup.operator("daf.safe_resize", text="Safe Resize")
    setup.operator("daf.adopt_imported_pack", text="Adopt Imported Animation Pack")
    setup.label(text="Select any mesh or armature belonging to the target character", icon='INFO')
    setup.label(text="Animation tools remain available throughout damage authoring", icon='LINKED')

    ground = _animation_foldout(
        layout, settings, "ui_ground_open", "Ground Preview", icon='MESH_PLANE'
    )
    if ground is not None:
        ground.prop(settings, "preview_floor_size")
        ground.prop(settings, "ground_sink")
        row = ground.row(align=True)
        row.operator("daf.create_preview_floor", text="Create Floor", icon='MESH_PLANE')
        row.operator("daf.align_feet_to_floor", text="Align Pose", icon='SNAP_ON')
        ground.label(text="Alignment uses the displayed frame", icon='INFO')

    rig = _animation_foldout(
        layout, settings, "ui_rig_open", "Rig Mapping & Direction", icon='BONE_DATA'
    )
    if rig is not None:
        try:
            from .. import find_armature
            from ..anatomy import skin_and_bones

            armature = find_armature(context)
            if skin_and_bones.contract(armature) is not None:
                rig.label(text="Skin & Bones mapping is authoritative", icon='LOCKED')
                rig.label(text="body → body_top0 → body_top1 → body_top2")
            else:
                rig.prop_search(settings, "manual_hips", armature.data, "bones", text="Pelvis / Hips")
                rig.prop_search(settings, "manual_spine", armature.data, "bones", text="Lowest Spine")
                rig.prop_search(settings, "manual_chest", armature.data, "bones", text="Upper Spine / Chest")
        except Exception:
            rig.label(text="Select the target character for bone pickers", icon='INFO')
        rig.label(text="Canonical forward: Blender +Y / glTF -Z", icon='ORIENTATION_GLOBAL')
        rig.label(text="Y- rigs are rejected; convert them in Skin & Bones", icon='INFO')
        row = rig.row(align=True)
        row.prop(settings, "invert_knees")
        row.prop(settings, "invert_elbows")


def _draw_pose_polish(layout, settings):
    pose = _animation_foldout(
        layout, settings, "ui_pose_open", "Arm & Hand Pose Polish", icon='POSE_HLT'
    )
    if pose is None:
        return
    pose.prop(settings, "pose_polish_enabled")
    left = pose.box()
    left.prop(
        settings,
        "ui_pose_left_open",
        text="Left Arm / Hand",
        icon='TRIA_DOWN' if settings.ui_pose_left_open else 'TRIA_RIGHT',
        emboss=False,
    )
    if settings.ui_pose_left_open:
        for name in (
            "left_upper_arm_forward", "left_upper_arm_roll", "left_elbow_flex",
            "left_forearm_twist", "left_wrist_flex", "left_wrist_side",
            "left_wrist_roll",
        ):
            left.prop(settings, name, slider=True)
    right = pose.box()
    right.prop(
        settings,
        "ui_pose_right_open",
        text="Right Arm / Hand",
        icon='TRIA_DOWN' if settings.ui_pose_right_open else 'TRIA_RIGHT',
        emboss=False,
    )
    if settings.ui_pose_right_open:
        for name in (
            "right_upper_arm_forward", "right_upper_arm_roll", "right_elbow_flex",
            "right_forearm_twist", "right_wrist_flex", "right_wrist_side",
            "right_wrist_roll",
        ):
            right.prop(settings, name, slider=True)
    pose.operator("daf.reset_pose_polish", text="Zero Arm & Hand Polish", icon='LOOP_BACK')
    pose.label(text="Rotation only; location and scale stay untouched", icon='INFO')


def _draw_walk_animation(layout, settings):
    walk = _animation_foldout(layout, settings, "ui_walk_open", "Walk Draft", icon='ACTION')
    if walk is None:
        return
    for name in ("walk_style", "walk_frames", "stride", "knee", "step_lift", "arm_swing", "walk_arm_tuck"):
        walk.prop(settings, name, slider=name not in {"walk_style", "walk_frames"})
    advanced = walk.box()
    advanced.prop(
        settings,
        "ui_walk_advanced_open",
        text="Advanced Walk Controls",
        icon='TRIA_DOWN' if settings.ui_walk_advanced_open else 'TRIA_RIGHT',
        emboss=False,
    )
    if settings.ui_walk_advanced_open:
        for name in (
            "foot_roll", "elbow_bend", "hip_bob", "hip_sway", "pelvis_twist",
            "chest_counter_twist", "torso_lean", "shoulder_sway", "head_stability",
            "walk_asymmetry",
        ):
            advanced.prop(settings, name, slider=True)
    walk.operator("daf.walk", text="Generate / Refresh Walk Draft", icon='ACTION')
    approve = walk.operator(
        "daf.approve_draft", text="Version / Approve Walk Draft", icon='FAKE_USER_ON'
    )
    approve.kind = "WALK"


def _draw_animation_base_pose(layout, settings, kind, label, preview_label):
    base_pose = layout.box()
    base_pose.label(text="Draft Base Pose", icon='POSE_HLT')
    base_pose.label(text=f"{label}: manual pose first; motion is added on top.")
    row = base_pose.row(align=True)
    edit = row.operator(
        "daf.edit_animation_base_pose",
        text=f"Edit {label} Base",
        icon='POSE_HLT',
    )
    edit.kind = kind
    capture = row.operator(
        "daf.capture_animation_base_pose",
        text=preview_label,
        icon='REC',
    )
    capture.kind = kind
    row = base_pose.row(align=True)
    cancel = row.operator(
        "daf.cancel_animation_base_pose",
        text="Cancel Edit",
        icon='X',
    )
    cancel.kind = kind
    clear = row.operator(
        "daf.clear_animation_base_pose",
        text="Clear Base",
        icon='TRASH',
    )
    clear.kind = kind
    base_pose.label(text=settings.animation_base_pose_status, icon='INFO')
    base_pose.label(text="Root excluded; rest rig and skinning stay unchanged.")


def _draw_idle_animation(layout, settings):
    idle = _animation_foldout(
        layout,
        settings,
        "ui_idle_open",
        "Humanoid Idle Draft",
        icon='ACTION',
    )
    if idle is None:
        return
    idle.prop(settings, "idle_seconds")
    idle.prop(settings, "idle_breathing", slider=True)
    idle.prop(settings, "idle_weight_shift", slider=True)
    idle.prop(settings, "idle_arm_tuck", slider=True)
    _draw_animation_base_pose(
        idle,
        settings,
        "IDLE",
        "Idle",
        "Capture Base + Preview Idle",
    )
    idle.operator("daf.idle", text="Generate / Refresh Idle Draft", icon='ACTION')
    approve = idle.operator(
        "daf.approve_draft",
        text="Version / Approve Idle Draft",
        icon='FAKE_USER_ON',
    )
    approve.kind = "IDLE"
    idle.label(text="Seamless, in-place, Y+ loop with no root drift", icon='INFO')


def _draw_death_animation(layout, settings):
    death = _animation_foldout(
        layout, settings, "ui_death_open", "Death / Collapse Draft", icon='POSE_HLT'
    )
    if death is None:
        return
    death.prop(settings, "collapse_style")
    death.prop(
        settings,
        "death_instant_seconds"
        if settings.collapse_style == "INSTANT_LIMP"
        else "collapse_seconds",
    )
    common_names = [
        "death_pain_side", "death_lead_knee", "death_arm_tuck",
    ]
    if settings.collapse_style != "INSTANT_LIMP":
        common_names.extend(("death_brace_side", "death_wiggle"))
    for name in common_names:
        death.prop(settings, name, slider=name in {"death_arm_tuck", "death_wiggle"})
    advanced = death.box()
    advanced.prop(
        settings,
        "ui_death_advanced_open",
        text="Advanced Collapse Controls",
        icon='TRIA_DOWN' if settings.ui_death_advanced_open else 'TRIA_RIGHT',
        emboss=False,
    )
    if settings.ui_death_advanced_open:
        for name in (
            "death_knee_strength", "death_curl_strength", "death_drop_strength",
            "death_travel_strength", "death_twist_strength", "death_head_lag",
            "death_fall_bias", "death_settle", "death_hold_frames",
        ):
            advanced.prop(settings, name, slider=name != "death_hold_frames")
    death.operator("daf.collapse", text="Generate / Refresh Death Draft", icon='POSE_HLT')
    approve = death.operator(
        "daf.approve_draft", text="Version / Approve Death Draft", icon='FAKE_USER_ON'
    )
    approve.kind = "DEATH"


def _draw_hurt_animation(layout, settings):
    hurt = _animation_foldout(
        layout, settings, "ui_hurt_open", "Flank Hurt Drafts", icon='ACTION'
    )
    if hurt is None:
        return
    for name in ("hurt_seconds", "hurt_severity", "hurt_hand_to_flank", "hurt_torso_bend"):
        hurt.prop(settings, name, slider=name != "hurt_seconds")
    advanced = hurt.box()
    advanced.prop(
        settings,
        "ui_hurt_advanced_open",
        text="Advanced Hurt Controls",
        icon='TRIA_DOWN' if settings.ui_hurt_advanced_open else 'TRIA_RIGHT',
        emboss=False,
    )
    if settings.ui_hurt_advanced_open:
        for name in (
            "hurt_hand_reach", "hurt_twist", "hurt_knee_dip", "hurt_stagger",
            "hurt_head_recoil", "hurt_recovery",
        ):
            advanced.prop(settings, name, slider=True)
    _draw_animation_base_pose(
        hurt,
        settings,
        "HURT",
        "Flank Hurt",
        "Capture + Preview Both",
    )
    row = hurt.row(align=True)
    row.operator("daf.hurt_left", text="Generate / Refresh Left", icon='ACTION')
    row.operator("daf.hurt_right", text="Generate / Refresh Right", icon='ACTION')
    row = hurt.row(align=True)
    approve = row.operator("daf.approve_draft", text="Approve Left", icon='FAKE_USER_ON')
    approve.kind = "HURT_LEFT"
    approve = row.operator("daf.approve_draft", text="Approve Right", icon='FAKE_USER_ON')
    approve.kind = "HURT_RIGHT"


def _draw_mace_guard_animation(layout, settings):
    guard = _animation_foldout(
        layout, settings, "ui_mace_guard_open", "Mace Head-Guard Drafts", icon='ACTION'
    )
    if guard is None:
        return
    guard.prop(settings, "mace_guard_style")
    timing = guard.box()
    timing.label(text="Timing", icon='TIME')
    timing.prop(settings, "mace_guard_raise_seconds")
    timing.prop(settings, "mace_guard_hold_seconds")
    timing.prop(settings, "mace_guard_recovery_seconds")
    pose = guard.box()
    pose.label(text="Head Coverage & Cower", icon='POSE_HLT')
    for name in (
        "mace_guard_arm_cover",
        "mace_guard_elbow_flex",
        "mace_guard_arm_wrap",
        "mace_guard_shoulder_hunch",
        "mace_guard_torso_curl",
        "mace_guard_head_tuck",
        "mace_guard_crouch",
        "mace_guard_asymmetry",
        "mace_guard_end_release",
    ):
        pose.prop(settings, name, slider=True)
    _draw_animation_base_pose(
        guard,
        settings,
        "MACE_GUARD",
        "Mace Guard",
        "Capture + Preview Guards",
    )
    guard.operator(
        "daf.generate_mace_head_guards",
        text="Generate / Refresh Three Mace Head-Guard Drafts",
        icon='ACTION',
    )
    guard.prop(settings, "mace_guard_preview_variant")
    row = guard.row(align=True)
    row.operator("daf.preview_mace_guard_active", text="Preview Guard_Active", icon='PLAY')
    row.operator("daf.validate_mace_head_guards", text="Validate Drafts", icon='CHECKMARK')
    for kind, label in (
        ("MACE_GUARD_TWO_ARM", "Approve Two-Arm"),
        ("MACE_GUARD_LEFT_ARM", "Approve Left-Arm"),
        ("MACE_GUARD_RIGHT_ARM", "Approve Right-Arm"),
    ):
        approve = guard.operator("daf.approve_draft", text=label, icon='FAKE_USER_ON')
        approve.kind = kind
    guard.label(text="Recognition / Covering / Guard_Active / Hold markers are preserved", icon='MARKER_HLT')
    guard.label(text="Forearm coverage is guidance, never an export blocker", icon='INFO')
    guard.label(text="Shape-key damage preview remains independent", icon='INFO')


def _draw_offensive_animation(layout, settings):
    offense = _animation_foldout(
        layout, settings, "ui_offensive_open", "Humanoid Offensive Actions", icon='ACTION'
    )
    if offense is None:
        return
    offense.label(text="Eight reviewed one-hand and two-hand attack drafts", icon='INFO')
    offense.label(text="Timing exports as WINDUP / ACTIVE / RECOVERY seconds", icon='TIME')
    row = offense.row(align=True)
    row.operator(
        "daf.generate_humanoid_offensive_suite",
        text="Generate / Refresh Offensive Suite",
        icon='ACTION',
    )
    row.operator(
        "daf.validate_humanoid_offensive_suite",
        text="Validate Suite",
        icon='CHECKMARK',
    )
    for kind, label in (
        ("ATTACK_SLASH_RTL_ONE_HAND", "Approve 1H Slash R-L"),
        ("ATTACK_SLASH_LTR_ONE_HAND", "Approve 1H Slash L-R"),
        ("ATTACK_OVERHEAD_ONE_HAND", "Approve 1H Overhead"),
        ("ATTACK_THRUST_ONE_HAND", "Approve 1H Thrust"),
        ("ATTACK_HEAVY_ONE_HAND", "Approve 1H Heavy"),
        ("ATTACK_SLASH_TWO_HAND", "Approve 2H Slash"),
        ("ATTACK_OVERHEAD_TWO_HAND", "Approve 2H Overhead"),
        ("ATTACK_THRUST_TWO_HAND", "Approve 2H Thrust"),
    ):
        approve = offense.operator("daf.approve_draft", text=label, icon='FAKE_USER_ON')
        approve.kind = kind
    offense.operator(
        "daf.ensure_runtime_attachment_sockets",
        text="Create / Repair Runtime Hand Sockets",
        icon='CONSTRAINT_BONE',
    )
    offense.label(text="Socket helper offsets remain artist-adjustable and idempotent", icon='ORIENTATION_LOCAL')


def _draw_animation_pack(layout, settings):
    pack = _animation_foldout(
        layout, settings, "ui_pack_open", "Approved Animation Pack", icon='PACKAGE'
    )
    if pack is not None:
        pack.prop(settings, "pack_output_directory")
        pack.prop(settings, "pack_filename")
        pack.prop(settings, "pack_auto_increment")
        pack.prop(settings, "pack_force_sampling")
        row = pack.row(align=True)
        row.operator("daf.build_approved_pack", text="Build Approved Pack", icon='EXPORT')
        row.operator("daf.validate_last_pack", text="Validate Last Pack", icon='CHECKMARK')
        pack.label(text="Only explicitly approved Actions are packaged", icon='INFO')
        pack.label(text="Saved Actions stay editable here; no reimport is required", icon='INFO')
        pack.label(text="Force Sampling bakes only the exported delivery GLB", icon='INFO')

    safety = _animation_foldout(
        layout, settings, "ui_workflow_open", "Action Approval & Safety", icon='LOCKED'
    )
    if safety is not None:
        safety.operator("daf.approve_active_legacy", text="Protect Active DSB Action", icon='FAKE_USER_ON')
        safety.operator("daf.purge_unapproved_attempts", text="Delete Unapproved DSB Attempts", icon='TRASH')
        safety.label(text="Approved Actions and Actions used by NLA are protected", icon='LOCKED')
        safety.label(text="Generated Actions never animate bone scale", icon='CHECKMARK')


def _draw_animation(layout, context, settings):
    _draw_vip_animation_library(layout, context, settings)
    _draw_animation_setup(layout, context, settings)
    if settings.anatomy_selected_profile == "DSB_QUADRUPED_MAMMAL_DIGITIGRADE_V1":
        notice = layout.box()
        notice.label(text="Quadruped generation is not production-ready in this milestone", icon='INFO')
        notice.label(text="Use analysis, role diagnostics, imported references, and validation only")
        _draw_animation_pack(layout, settings)
        return
    if settings.anatomy_readiness_status in {
        "PROFILE_AMBIGUOUS", "PROFILE_INCOMPLETE", "ORIENTATION_AMBIGUOUS",
        "MISSING_LIMB_CHAIN", "MISSING_CONTACT_ROLE", "UNSUPPORTED_ANATOMY",
        "UNSUPPORTED_FORWARD_AXIS",
    }:
        warning = layout.box()
        warning.alert = True
        warning.label(text="Resolve the anatomy blocker before generating humanoid motion", icon='ERROR')
        _draw_animation_pack(layout, settings)
        return
    _draw_pose_polish(layout, settings)
    _draw_idle_animation(layout, settings)
    _draw_walk_animation(layout, settings)
    _draw_death_animation(layout, settings)
    _draw_hurt_animation(layout, settings)
    _draw_offensive_animation(layout, settings)
    _draw_mace_guard_animation(layout, settings)
    _draw_animation_pack(layout, settings)


def _draw_export(layout, settings):
    validation = layout.box()
    validation.label(text="Focused Validation", icon='CHECKMARK')
    row = validation.row(align=True)
    row.operator("daf.validate_deformations", text="Validate Morph Targets")
    row.operator("daf.validate_gore_geometry", text="Validate Gore Geometry")
    validation.operator("daf.validate_compound_trauma_event", text="Validate Compound Event")
    validation.operator("daf.validate_mace_head_guards", text="Validate Mace Head-Guard Drafts")
    validation.operator("daf.validate_humanoid_offensive_suite", text="Validate Humanoid Offensive Suite")
    validation.operator("daf.validate_damage_authoring_asset", text="Validate Complete Damage Asset")
    export = layout.box()
    export.label(text="Damage Export", icon='EXPORT')
    export.prop(settings, "damage_authoring_output_directory")
    export.prop(settings, "damage_authoring_filename")
    export.operator("daf.ensure_runtime_attachment_sockets", text="Create / Repair Runtime Hand Sockets")
    export.operator("daf.export_damage_asset", text="Export Damage GLB + Manifest")
    export.label(text="Approved offensive metadata and runtime sockets are emitted in the sidecar", icon='INFO')
    export.operator("daf.restore_imported_damage_intact_preview", text="Restore Reimported GLB Intact Preview")


def _advanced_foldout(layout, settings, property_name, title, icon):
    box = layout.box()
    row = box.row(align=True)
    opened = bool(getattr(settings, property_name))
    row.prop(
        settings,
        property_name,
        text=title,
        icon='TRIA_DOWN' if opened else 'TRIA_RIGHT',
        emboss=False,
    )
    if not opened:
        return None
    box.label(text=title, icon=icon)
    return box


def _draw_advanced(layout, context, settings, deformation_draw, deformation_authoring):
    manual = _advanced_foldout(
        layout, settings, "ui_advanced_character_open", "Character & Source Workflows", 'TOOL_SETTINGS'
    )
    if manual is not None:
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

    trauma = _advanced_foldout(
        layout, settings, "ui_advanced_trauma_open", "Trauma, Gore, Compound & Legacy Tools", 'MODIFIER'
    )
    if trauma is not None:
        deformation_draw(trauma, context, settings)

    diagnostics = _advanced_foldout(
        layout, settings, "ui_advanced_diagnostics_open", "Diagnostics & Crash Support", 'INFO'
    )
    if diagnostics is not None:
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
        _draw_animation(layout, context, settings)
    elif settings.ui_workspace == 'EXPORT':
        _draw_export(layout, settings)
    else:
        _draw_advanced(layout, context, settings, deformation_draw, deformation_authoring)
