"""Blender-independent next-action guidance from cached workflow state."""

from __future__ import annotations


def next_action(state):
    if not state.get("sourceSelected"):
        return "Select a source character"
    if not state.get("outputFolderReady"):
        return "Choose an output folder"
    if state.get("sourceReadiness") not in {"READY", "SOURCE READY", "VALID"}:
        return "Run Prepare Character"
    if not state.get("authoringBuilt"):
        return "Run Prepare Character"
    if not state.get("activeRegion"):
        return "Select a region"
    if not state.get("captureReady"):
        return "Select a connected face patch"
    if not state.get("activeKey"):
        return "Create Impact From Selection"
    if state.get("previewStatus") in {"DIRTY", "BUILDING", "READY", "FAILED"}:
        return "Adjust and Commit Impact"
    if state.get("damageValidation") != "PASS":
        return "Validate Damage Asset"
    return "Export"


def dashboard_state(context, settings, summary):
    active_object = getattr(context, "active_object", None)
    metadata = summary.get("metadata", {})
    region = summary.get("region", {})
    return {
        "sourceSelected": active_object is not None,
        "outputFolderReady": bool(str(getattr(settings, "damage_readiness_output_directory", ""))),
        "sourceReadiness": str(
            getattr(settings, "source_readiness_contract_status", "")
            or getattr(settings, "damage_readiness_overall_status", "NOT ANALYZED")
        ),
        "authoringBuilt": str(getattr(settings, "damage_authoring_status", "")).startswith("BUILT"),
        "activeRegion": str(region.get("regionId", metadata.get("regionId", ""))),
        "captureReady": bool(getattr(settings, "deformation_seed_center_valid", False)),
        "activeKey": str(getattr(settings, "deformation_active_key", "")),
        "previewStatus": str(getattr(settings, "deformation_preview_status", "CLEAN")),
        "damageValidation": str(getattr(settings, "last_damage_authoring_validation", "NOT VALIDATED")),
    }
