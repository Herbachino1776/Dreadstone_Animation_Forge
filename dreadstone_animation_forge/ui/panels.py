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


def _draw_impact_control_deck(layout, settings):
    deck = layout.box()
    deck.label(text="IMPACT CONTROL DECK", icon='MOD_DISPLACE')
    pedal = deck.box()
    mode = str(settings.deformation_impact_control_mode)
    identity = str(settings.deformation_impact_identity or "")[:10] or "not-saved"
    pedal.label(
        text=f"IMPACT PEDAL  |  {mode if mode == 'MACRO' else 'CUSTOM'}  |  {settings.deformation_stamp_family.replace('_', ' ').title()}",
        icon='DRIVER',
    )
    macros = pedal.column(align=True)
    macros.enabled = mode == 'MACRO'
    row = macros.row(align=True)
    row.scale_y = 1.22
    row.prop(settings, "deformation_impact_size", text="SIZE", slider=True)
    row.prop(settings, "deformation_impact_crush", text="CRUSH", slider=True)
    row = macros.row(align=True)
    row.scale_y = 1.22
    row.prop(settings, "deformation_impact_profile", text="PROFILE", slider=True)
    row.prop(settings, "deformation_impact_edge_safety", text="EDGE SAFETY", slider=True)
    row = macros.row(align=True)
    row.scale_y = 1.22
    row.prop(settings, "deformation_impact_chaos", text="CHAOS", slider=True)

    seed = pedal.box()
    seed.label(text=f"DETERMINISTIC IDENTITY  {identity}", icon='KEY_HLT')
    seed.prop(settings, "deformation_impact_seed", text="Master Seed")
    randomize = seed.column()
    randomize.scale_y = 1.55
    randomize.operator("daf.randomize_impact_seed", text="RANDOMIZE SEED", icon='FILE_REFRESH')

    pedal.prop(settings, "deformation_preview_quality")
    preview = pedal.column()
    preview.scale_y = 1.55
    preview.operator("daf.refresh_impact_preview", text="GENERATE / REFRESH PREVIEW", icon='PLAY')
    commit = pedal.column()
    commit.scale_y = 1.55
    commit.operator("daf.commit_impact", text="COMMIT / SAVE IMPACT", icon='CHECKMARK')
    recovery = pedal.row(align=True)
    recovery.scale_y = 1.25
    recovery.operator("daf.revert_impact", text="Revert", icon='RECOVER_LAST')
    clear = recovery.row(align=True)
    clear.alert = True
    clear.operator("daf.clear_managed_preview", text="Clear Preview", icon='X')

    state = "DIRTY" if settings.deformation_impact_dirty else "SAVED"
    validity = str(settings.last_deformation_validation or "NOT VALIDATED")
    status = pedal.row(align=True)
    status.label(
        text=(
            f"{state} / {settings.deformation_preview_status} / {validity}  |  "
            f"{settings.deformation_preview_affected_vertices:,} verts / "
            f"{settings.deformation_preview_elapsed_ms:.1f} ms"
        ),
        icon='ERROR' if settings.deformation_preview_status == 'FAILED' else 'INFO',
    )


def _draw_gore_control_deck(layout, settings):
    deck = layout.box()
    deck.label(text="GORE CONTROL DECK", icon="MATERIAL")
    pedal = deck.box()
    mode = str(settings.deformation_gore_control_mode)
    digest = str(settings.deformation_gore_identity_digest or "")[:10] or "not-saved"
    pedal.label(
        text=(
            f"GORE PEDAL  |  {mode if mode == 'MACRO' else 'CUSTOM'}  |  "
            f"{settings.deformation_gore_identity.replace('_', ' ').title()}"
        ),
        icon="DRIVER",
    )
    pedal.prop(settings, "deformation_gore_identity", text="Gore Identity")
    pedal.prop(settings, "deformation_gore_enabled", text="Enabled")
    macros = pedal.column(align=True)
    macros.enabled = mode == "MACRO"
    for first, second in (
        ("deformation_gore_exposure", "deformation_gore_cavity"),
        ("deformation_gore_clot_fill", "deformation_gore_breakup"),
        ("deformation_gore_wetness_macro", "deformation_gore_variation"),
    ):
        row = macros.row(align=True)
        row.scale_y = 1.22
        row.prop(settings, first, slider=True)
        row.prop(settings, second, slider=True)

    seed = pedal.box()
    seed.label(
        text=(
            f"MASTER GORE SEED  {int(settings.deformation_gore_mask_seed)}  |  "
            f"DIGEST {digest}"
        ),
        icon="KEY_HLT",
    )
    randomize = seed.column()
    randomize.scale_y = 1.60
    # Ordinary sidebar operators do not expose stable per-button RGB colors.
    # A normal embossed operator is the robust theme-safe neutral/light-gray treatment.
    randomize.operator(
        "daf.randomize_gore_seed",
        text="RANDOMIZE GORE SEED",
        icon="FILE_REFRESH",
    )

    pedal.prop(settings, "deformation_preview_quality")
    preview = pedal.column()
    preview.scale_y = 1.60
    preview.operator(
        "daf.generate_gore_preview",
        text="GENERATE / REBUILD GORE PREVIEW",
        icon="PLAY",
    )
    commit = pedal.column()
    commit.scale_y = 1.60
    commit.operator(
        "daf.commit_gore",
        text="COMMIT / SAVE GORE",
        icon="CHECKMARK",
    )
    recovery = pedal.row(align=True)
    recovery.scale_y = 1.24
    recovery.operator("daf.revert_gore", text="Revert", icon="RECOVER_LAST")
    clear = recovery.row(align=True)
    clear.alert = True
    clear.operator(
        "daf.clear_managed_preview",
        text="Clear Gore Preview",
        icon="X",
    )

    proof = pedal.row(align=True)
    proof.scale_y = 1.35
    proof.operator(
        "daf.final_gore_preview",
        text="FINAL GORE PREVIEW",
        icon="SHADING_RENDERED",
    )
    proof.operator(
        "daf.validate_gore_geometry",
        text="VALIDATE GORE GEOMETRY",
        icon="CHECKMARK",
    )

    state = "DIRTY" if settings.deformation_gore_dirty else "SAVED"
    triangles = (
        int(settings.deformation_preview_final_gore_triangles)
        or int(settings.deformation_preview_estimated_gore_triangles)
    )
    status = pedal.box()
    status.label(
        text=(
            f"{settings.deformation_gore_geometry_mode}  |  {triangles:,} tris  |  "
            f"{state}  |  {settings.deformation_gore_validation_status}"
        ),
        icon="ERROR" if "FAIL" in settings.deformation_gore_validation_status else "INFO",
    )
    status.label(
        text=(
            f"Proud {settings.deformation_gore_max_proudness:.5f} m  |  "
            f"Median depth {settings.deformation_gore_median_cavity_depth:.5f} m  |  "
            f"Liner gap {settings.deformation_gore_minimum_liner_separation:.5f} m"
        )
    )


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
            text="Manual values are authoritative; the six macros will not overwrite them.",
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
        "deformation_gore_preset",
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
        "deformation_gore_core_density", "deformation_gore_clot_thickness",
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
    create = draft.column()
    create.scale_y = 1.55
    create.operator(
        "daf.create_impact_from_selection",
        text="CREATE IMPACT FROM CURRENT SELECTION",
        icon='ADD',
    )
    draft.label(text="The selected connected surface remains the artist's decision", icon='INFO')

    _draw_impact_control_deck(layout, settings)
    _draw_gore_control_deck(layout, settings)
    _draw_advanced_impact_internals(layout, settings)
    _draw_advanced_gore_internals(layout, settings)

    actions = layout.box()
    actions.prop(settings, "deformation_live_preview")
    final = actions.column()
    final.scale_y = 1.4
    final.operator("daf.final_impact_preview", text="FINAL PREVIEW", icon='SHADING_RENDERED')
    clear = actions.column()
    clear.scale_y = 1.4
    clear.alert = True
    clear.operator("daf.clear_managed_preview", text="CLEAR DAMAGE PREVIEW", icon='X')
    actions.operator("daf.undo_impact_draft", text="Undo Draft", icon='LOOP_BACK')


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


def _draw_animation_setup(layout, context, settings):
    setup = layout.box()
    setup.label(text="Animation Setup", icon='ARMATURE_DATA')
    row = setup.row(align=True)
    row.operator("daf.analyze", text="Analyze Rig")
    row.operator("daf.safe_resize", text="Safe Resize")
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

            armature = find_armature(context)
            rig.prop_search(settings, "manual_hips", armature.data, "bones", text="Pelvis / Hips")
            rig.prop_search(settings, "manual_spine", armature.data, "bones", text="Lowest Spine")
            rig.prop_search(settings, "manual_chest", armature.data, "bones", text="Upper Spine / Chest")
        except Exception:
            rig.label(text="Select the target character for bone pickers", icon='INFO')
        rig.prop(settings, "facing")
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
            "left_upper_arm_forward", "left_upper_arm_roll", "left_forearm_twist",
            "left_wrist_flex", "left_wrist_side", "left_wrist_roll",
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
            "right_upper_arm_forward", "right_upper_arm_roll", "right_forearm_twist",
            "right_wrist_flex", "right_wrist_side", "right_wrist_roll",
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


def _draw_death_animation(layout, settings):
    death = _animation_foldout(
        layout, settings, "ui_death_open", "Death / Collapse Draft", icon='POSE_HLT'
    )
    if death is None:
        return
    for name in (
        "collapse_style", "collapse_seconds", "death_pain_side", "death_lead_knee",
        "death_brace_side", "death_arm_tuck", "death_wiggle",
    ):
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
    guard.prop(settings, "mace_guard_raise_seconds")
    guard.prop(settings, "mace_guard_hold_seconds")
    guard.prop(settings, "mace_guard_recovery_seconds")
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
    guard.label(text="Brace_Start / Guard_Active / Brace_End markers are preserved", icon='MARKER_HLT')
    guard.label(text="Shape-key damage preview remains independent", icon='INFO')


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

    safety = _animation_foldout(
        layout, settings, "ui_workflow_open", "Action Approval & Safety", icon='LOCKED'
    )
    if safety is not None:
        safety.operator("daf.approve_active_legacy", text="Protect Active DSB Action", icon='FAKE_USER_ON')
        safety.operator("daf.purge_unapproved_attempts", text="Delete Unapproved DSB Attempts", icon='TRASH')
        safety.label(text="Approved Actions and Actions used by NLA are protected", icon='LOCKED')
        safety.label(text="Generated Actions never animate bone scale", icon='CHECKMARK')


def _draw_animation(layout, context, settings):
    _draw_animation_setup(layout, context, settings)
    _draw_pose_polish(layout, settings)
    _draw_walk_animation(layout, settings)
    _draw_death_animation(layout, settings)
    _draw_hurt_animation(layout, settings)
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
    validation.operator("daf.validate_damage_authoring_asset", text="Validate Complete Damage Asset")
    export = layout.box()
    export.label(text="Damage Export", icon='EXPORT')
    export.prop(settings, "damage_authoring_output_directory")
    export.prop(settings, "damage_authoring_filename")
    export.operator("daf.export_damage_asset", text="Export Damage GLB + Manifest")
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
