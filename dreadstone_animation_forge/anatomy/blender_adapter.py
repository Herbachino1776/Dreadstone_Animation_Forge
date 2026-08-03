"""Thin Blender-facing adapter for pure Creature Anatomy services."""

from __future__ import annotations

import json
from typing import Callable, Mapping

from .detection import analyze_selected_profile, detect_profile
from .model import BoneRecord, RigSnapshot
from .orientation import FACING_TO_AXIS
from .persistence import clear_override, load_metadata, store_metadata
from .profiles import (
    HUMANOID_PROFILE_ID,
    capability_status,
    registry,
)
from .resolver import mapping_digest
from .skin_and_bones import (
    SBF_CANONICAL_RIG_VERSION,
    contract as skin_and_bones_contract,
    require_canonical_yplus,
)
from .ui_state import summary_from_analysis


def snapshot_armature(armature) -> RigSnapshot:
    records = []
    for bone in armature.data.bones:
        records.append(BoneRecord(
            name=str(bone.name),
            parent=str(bone.parent.name) if bone.parent else "",
            head=tuple(float(value) for value in bone.head_local),
            tail=tuple(float(value) for value in bone.tail_local),
            length=float(bone.length),
            use_deform=bool(getattr(bone, "use_deform", True)),
            valid=True,
        ))
    return RigSnapshot.from_bones(
        records,
        armature_name=str(armature.name),
        scale=tuple(float(value) for value in armature.scale),
    )


def _manual_overrides(settings) -> dict[str, str]:
    return {
        "hips": str(getattr(settings, "manual_hips", "")),
        "spine": str(getattr(settings, "manual_spine", "")),
        "chest": str(getattr(settings, "manual_chest", "")),
    }


def analyze_armature(
    armature,
    settings,
    *,
    legacy_humanoid_mapper: Callable[[object, object], Mapping[str, object]] | None = None,
) -> dict[str, object]:
    snapshot = snapshot_armature(armature)
    override = str(getattr(settings, "anatomy_profile_override", "AUTO") or "AUTO")
    sbf = skin_and_bones_contract(armature)
    if sbf is not None:
        require_canonical_yplus(armature, label="Creature Anatomy analysis")
        profile = registry.require(HUMANOID_PROFILE_ID)
        result = analyze_selected_profile(
            profile,
            snapshot,
            sbf["roleMapping"],
            confidence=1.0,
            override="HUMANOID",
            explicit_forward="+Y",
            rig_profile_id=SBF_CANONICAL_RIG_VERSION,
        )
        result.update({
            "canonicalRigVersion": SBF_CANONICAL_RIG_VERSION,
            "rigContractVersion": int(sbf["rigContractVersion"]),
            "orientationRevision": int(sbf["orientationRevision"]),
            "rootMotionCarrier": str(sbf["rootBone"]),
            "unitScaleMeters": float(sbf["unitScaleMeters"]),
        })
        store_metadata(armature, result)
        update_settings_summary(settings, result)
        return result

    explicit_forward = str(getattr(settings, "facing", "POS_Y"))
    result = detect_profile(
        snapshot,
        override=override,
        manual_overrides=_manual_overrides(settings),
        # AUTO quadrupeds use their own profile convention. Humanoids are
        # explicitly +Y-only in this release.
        explicit_forward=(
            explicit_forward
            if override in {"HUMANOID", HUMANOID_PROFILE_ID}
            else None
        ),
    )
    if result.get("profileId") == HUMANOID_PROFILE_ID and legacy_humanoid_mapper is not None:
        humanoid_mapping = dict(legacy_humanoid_mapper(armature, settings))
        profile = registry.require(HUMANOID_PROFILE_ID)
        rebuilt = analyze_selected_profile(
            profile,
            snapshot,
            humanoid_mapping,
            confidence=float(result.get("detectionConfidence", 0.0)),
            override=override,
            ambiguities=list(result.get("ambiguities", [])),
            explicit_forward=explicit_forward,
            rig_profile_id="GENERIC_HUMANOID_YPLUS",
        )
        rebuilt["profileScores"] = result.get("profileScores", [])
        result = rebuilt
    orientation = result.get("orientation", {})
    if (
        result.get("profileId") == HUMANOID_PROFILE_ID
        and str(orientation.get("forwardAxis", "")) != "+Y"
    ):
        blocker = {
            "code": "UNSUPPORTED_FORWARD_AXIS",
            "message": (
                "Animation Forge requires Blender +Y forward. Convert or rebuild "
                "this character in Skin & Bones; Y- animation authoring is unsupported."
            ),
        }
        result["ready"] = False
        result["readinessStatus"] = "UNSUPPORTED_FORWARD_AXIS"
        result["blockers"] = [blocker] + list(result.get("blockers", []))
        result["worstBlocker"] = blocker["message"]
    store_metadata(armature, result)
    update_settings_summary(settings, result)
    return result


def update_settings_summary(settings, analysis: Mapping[str, object]) -> None:
    summary = summary_from_analysis(analysis)
    assignments = {
        "anatomy_detected_creature_class": summary["creatureClass"],
        "anatomy_selected_profile": summary["profileId"],
        "anatomy_detection_confidence": summary["confidence"],
        "anatomy_orientation_summary": summary["orientation"],
        "anatomy_mapped_role_count": summary["mappedRoleCount"],
        "anatomy_readiness_status": summary["readinessStatus"],
        "anatomy_worst_blocker": summary["worstBlocker"],
        "anatomy_role_mapping_json": json.dumps(
            analysis.get("roleMapping", {}), sort_keys=True, indent=2
        ),
    }
    for name, value in assignments.items():
        if hasattr(settings, name):
            setattr(settings, name, value)


def clear_profile_override(armature, settings) -> None:
    settings.anatomy_profile_override = "AUTO"
    clear_override(armature)


def write_mapping_text(armature, analysis, text_collection):
    text = text_collection.get("DSB_Creature_Anatomy_Mapping.json") or text_collection.new(
        "DSB_Creature_Anatomy_Mapping.json"
    )
    text.clear()
    text.write(json.dumps(dict(analysis), indent=2, sort_keys=True) + "\n")
    return text


def current_analysis(armature, settings=None) -> dict[str, object] | None:
    value = load_metadata(armature)
    if value is not None and settings is not None:
        update_settings_summary(settings, value)
    return value


def authoritative_forward_axis(armature, settings) -> str:
    sbf = skin_and_bones_contract(armature) if armature is not None else None
    if sbf is not None:
        require_canonical_yplus(armature, label="Animation generation")
        return "+Y"
    value = load_metadata(armature) if armature is not None else None
    orientation = value.get("orientation", {}) if value else {}
    axis = str(orientation.get("forwardAxis", ""))
    if axis:
        return axis
    return FACING_TO_AXIS.get(str(getattr(settings, "facing", "POS_Y")), "+Y")


def require_generator_capability(armature, capability: str, label: str) -> None:
    metadata = load_metadata(armature)
    sbf = skin_and_bones_contract(armature)
    if sbf is not None:
        require_canonical_yplus(armature, label=label)
        if (
            metadata is None
            or str(metadata.get("canonicalRigVersion", ""))
            != SBF_CANONICAL_RIG_VERSION
            or str(metadata.get("orientation", {}).get("forwardAxis", ""))
            != "+Y"
        ):
            snapshot = snapshot_armature(armature)
            profile = registry.require(HUMANOID_PROFILE_ID)
            metadata = analyze_selected_profile(
                profile,
                snapshot,
                sbf["roleMapping"],
                confidence=1.0,
                override="HUMANOID",
                explicit_forward="+Y",
                rig_profile_id=SBF_CANONICAL_RIG_VERSION,
            )
            metadata.update({
                "canonicalRigVersion": SBF_CANONICAL_RIG_VERSION,
                "rigContractVersion": int(sbf["rigContractVersion"]),
                "orientationRevision": int(sbf["orientationRevision"]),
                "rootMotionCarrier": str(sbf["rootBone"]),
                "unitScaleMeters": float(sbf["unitScaleMeters"]),
            })
            store_metadata(armature, metadata)
    elif capability in {
        "idle", "walk", "collapse", "hurt", "mace_head_guard",
    }:
        raise RuntimeError(
            f"{label} requires {SBF_CANONICAL_RIG_VERSION}. Rig or re-rig "
            "the character in Skin & Bones Forge 2.1.0+. Y- and unversioned "
            "humanoid rigs are unsupported."
        )
    if metadata is None:
        raise RuntimeError(
            f"{label} requires a Y+ Creature Anatomy analysis. Run ANALYZE "
            "CREATURE ANATOMY, or rig the character in Skin & Bones Forge 2.1.0+."
        )
    forward_axis = str(metadata.get("orientation", {}).get("forwardAxis", ""))
    if forward_axis != "+Y":
        raise RuntimeError(
            f"{label} requires Blender +Y forward. Convert or rebuild the "
            "character in Skin & Bones; Y- rigs are unsupported."
        )
    profile_id = str(metadata.get("profileId", ""))
    profile = registry.get(profile_id)
    if profile is None:
        raise RuntimeError(
            f"{label} requires a resolved Creature Anatomy Profile; run ANALYZE CREATURE ANATOMY."
        )
    status = capability_status(profile, capability, metadata.get("roleMapping", {}))
    if not status["supported"]:
        raise RuntimeError(f"{label} is unsupported by anatomy profile {profile_id}.")
    if not status["productionReady"]:
        missing = status.get("missingRoles", [])
        suffix = " Missing roles: " + ", ".join(missing) + "." if missing else ""
        raise RuntimeError(
            f"{label} is not production-ready for anatomy profile {profile_id}.{suffix}"
        )


def legacy_mapping_digest(mapping: Mapping[str, object]) -> str:
    """Compatibility accessor retained for external tests and scripts."""
    return mapping_digest(mapping)


__all__ = (
    "analyze_armature",
    "authoritative_forward_axis",
    "clear_profile_override",
    "current_analysis",
    "legacy_mapping_digest",
    "require_generator_capability",
    "snapshot_armature",
    "update_settings_summary",
    "write_mapping_text",
)
