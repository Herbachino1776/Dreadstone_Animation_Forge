"""Pure Character Variant Family contract and effective-content resolver.

Skin & Bones owns appearance identity and proves technical-body compatibility.
Animation Forge owns the shared authoring layer and explicit copy-on-write
overrides.  This module deliberately has no Blender dependency so every
ownership and resolution rule can be regression-tested outside Blender.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping


SBF_HANDOFF_SCHEMA = "skin-and-bones-appearance-family-handoff-v1"
SBF_HANDOFF_SCHEMA_VERSION = 1
SBF_FAMILY_SCHEMA = "skin-and-bones-appearance-family-v1"
SBF_FAMILY_SCHEMA_VERSION = 1
SBF_TECHNICAL_BODY_SCHEMA = "skin-and-bones-technical-body-v1"
SBF_TECHNICAL_BODY_SCHEMA_VERSION = 1

FORGE_FAMILY_SCHEMA = "dreadstone.character_variant_family.v1"
FORGE_FAMILY_SCHEMA_VERSION = 1
FORGE_PROVENANCE_SCHEMA = "dreadstone.character_variant_provenance.v1"
FORGE_PROVENANCE_SCHEMA_VERSION = 1
FAMILY_SOURCE_SBF = "SKIN_AND_BONES_HANDOFF"
FAMILY_SOURCE_FORGE_TEXTURE = "FORGE_FINISHED_TEXTURE_CAPTURE"
FORGE_TEXTURE_BODY_SCHEMA = "dreadstone-finished-damage-body-v1"
FORGE_TEXTURE_BODY_SCHEMA_VERSION = 1
FORGE_TEXTURE_APPROVAL_AUTHORITY = "ANIMATION_FORGE_TEXTURE_CAPTURE"

SBF_HANDOFF_PROPERTY = "sbf_appearance_family_handoff"
SBF_FAMILY_ID_PROPERTY = "sbf_appearance_family_id"
SBF_VARIANT_ID_PROPERTY = "sbf_appearance_variant_id"
SBF_BODY_FINGERPRINT_PROPERTY = "sbf_technical_body_fingerprint"

ACTION_SCOPE_SHARED = "SHARED"
ACTION_SCOPE_OVERRIDE = "VARIANT_OVERRIDE"
SOCKET_POLICY = "FAMILY_SHARED_NO_VARIANT_OVERRIDE"
DAMAGE_KEY_KIND = "DAMAGE_KEY"
PROGRESSIVE_SITE_KIND = "PROGRESSIVE_SITE"

_HEX_64 = re.compile(r"^[0-9a-fA-F]{64}$")


def stable_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def canonical_digest(value) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def safe_identifier(value, fallback="variant") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    cleaned = cleaned.strip("._-").lower()
    return cleaned or fallback


def _integer(value, label, errors, *, minimum=None):
    if isinstance(value, bool):
        errors.append(f"{label} must be an integer.")
        return 0
    try:
        result = int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be an integer.")
        return 0
    if minimum is not None and result < minimum:
        errors.append(f"{label} must be at least {minimum}.")
    return result


def decode_handoff(raw):
    """Decode the exact compact Skin & Bones v1 handoff JSON."""

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Skin & Bones appearance-family handoff is not valid JSON.") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("Skin & Bones appearance-family handoff must be an object.")
    return copy.deepcopy(dict(raw))


def handoff_errors(raw, scalar_extras=None, *, require_approved=True):
    """Validate only fields actually shipped by Skin & Bones Forge 2.2.0."""

    try:
        handoff = decode_handoff(raw)
    except ValueError as exc:
        return [str(exc)]
    errors = []
    exact = (
        ("schema", SBF_HANDOFF_SCHEMA),
        ("schema_version", SBF_HANDOFF_SCHEMA_VERSION),
        ("family_schema", SBF_FAMILY_SCHEMA),
        ("family_schema_version", SBF_FAMILY_SCHEMA_VERSION),
        ("technical_body_schema", SBF_TECHNICAL_BODY_SCHEMA),
        ("technical_body_schema_version", SBF_TECHNICAL_BODY_SCHEMA_VERSION),
    )
    for field, expected in exact:
        if handoff.get(field) != expected:
            errors.append(
                f"Skin & Bones {field} is {handoff.get(field)!r}; expected {expected!r}."
            )
    for field in (
        "family_id",
        "family_display_name",
        "variant_id",
        "variant_display_name",
        "export_identity",
        "technical_body_fingerprint",
    ):
        if not str(handoff.get(field, "")).strip():
            errors.append(f"Skin & Bones handoff is missing {field}.")
    fingerprint = str(handoff.get("technical_body_fingerprint", ""))
    if fingerprint and not _HEX_64.fullmatch(fingerprint):
        errors.append("Skin & Bones technical_body_fingerprint must be a SHA-256 hex value.")
    appearance_revision = _integer(
        handoff.get("appearance_revision"),
        "Skin & Bones appearance_revision",
        errors,
        minimum=0,
    )
    approval = handoff.get("approval")
    if not isinstance(approval, Mapping):
        errors.append("Skin & Bones handoff is missing its approval object.")
        approval = {}
    if require_approved:
        if approval.get("state") != "APPROVED":
            errors.append("Skin & Bones appearance is not approved.")
        approved_revision = _integer(
            approval.get("approved_revision"),
            "Skin & Bones approved_revision",
            errors,
            minimum=0,
        )
        if approved_revision != appearance_revision:
            errors.append(
                "Skin & Bones approval is stale: approved_revision does not equal appearance_revision."
            )
        if not str(approval.get("appearance_fingerprint", "")).strip():
            errors.append("Skin & Bones approval has no appearance_fingerprint.")
        if not str(approval.get("approved_at_utc", "")).strip():
            errors.append("Skin & Bones approval has no approved_at_utc timestamp.")
        if not str(approval.get("addon_version", "")).strip():
            errors.append("Skin & Bones approval has no addon_version.")
    if scalar_extras is not None:
        scalar_extras = dict(scalar_extras)
        comparisons = (
            (SBF_FAMILY_ID_PROPERTY, "family_id"),
            (SBF_VARIANT_ID_PROPERTY, "variant_id"),
            (SBF_BODY_FINGERPRINT_PROPERTY, "technical_body_fingerprint"),
        )
        for scalar, field in comparisons:
            actual = str(scalar_extras.get(scalar, ""))
            expected = str(handoff.get(field, ""))
            if actual != expected:
                errors.append(
                    f"Skin & Bones scalar {scalar} does not match handoff {field}."
                )
    return errors


def require_handoff(raw, scalar_extras=None, *, require_approved=True):
    handoff = decode_handoff(raw)
    errors = handoff_errors(
        handoff,
        scalar_extras,
        require_approved=require_approved,
    )
    if errors:
        raise ValueError(" ".join(errors))
    return handoff


def canonical_rig_signature(contract):
    """Keep the current Forge/Skin & Bones canonical coordinate gate explicit."""

    contract = dict(contract or {})
    return {
        "rigVersion": str(contract.get("rigVersion", "")),
        "rigContractVersion": int(contract.get("rigContractVersion", 0) or 0),
        "forwardAxis": str(contract.get("forwardAxis", "")),
        "upAxis": str(contract.get("upAxis", "")),
        "rootBone": str(contract.get("rootBone", "")),
        "orientationState": str(contract.get("orientationState", "")),
        "orientationRevision": int(contract.get("orientationRevision", 0) or 0),
        "unitScaleMeters": float(contract.get("unitScaleMeters", 0.0) or 0.0),
        "canonicalYPlus": bool(contract.get("canonicalYPlus", False)),
    }


def rig_signature_errors(signature):
    signature = canonical_rig_signature(signature)
    expected = {
        "rigVersion": "SBF_HUMANOID_YPLUS_V1",
        "rigContractVersion": 1,
        "forwardAxis": "+Y",
        "upAxis": "+Z",
        "rootBone": "root",
        "orientationState": "CANONICAL_Y_PLUS",
        "orientationRevision": 1,
        "unitScaleMeters": 1.0,
        "canonicalYPlus": True,
    }
    errors = []
    for field, value in expected.items():
        actual = signature.get(field)
        if field == "unitScaleMeters":
            if abs(float(actual) - float(value)) > 1.0e-6:
                errors.append(
                    f"Canonical rig {field} is {actual!r}; expected {value!r}."
                )
        elif actual != value:
            errors.append(
                f"Canonical rig {field} is {actual!r}; expected {value!r}."
            )
    return errors


def _variant_from_handoff(handoff, *, appearance=None):
    approval = dict(handoff.get("approval", {}))
    return {
        "variantId": str(handoff["variant_id"]),
        "displayName": str(handoff["variant_display_name"]),
        "exportIdentity": str(handoff["export_identity"]).strip(),
        "appearanceRevision": int(handoff["appearance_revision"]),
        "appearanceFingerprint": str(approval.get("appearance_fingerprint", "")),
        "appearanceApprovedAtUtc": str(approval.get("approved_at_utc", "")),
        "skinAndBonesVersion": str(approval.get("addon_version", "")),
        "appearanceSource": FAMILY_SOURCE_SBF,
        "appearanceApprovalAuthority": "SKIN_AND_BONES",
        "appearanceApprovalState": "APPROVED",
        "handoff": copy.deepcopy(handoff),
        "appearance": copy.deepcopy(appearance or {}),
        "forgeRevision": 1,
        "actionOverrides": {},
        "damageKeyOverrides": {},
        "progressiveSiteOverrides": {},
    }


def new_family(handoff, rig_contract, *, appearance=None):
    handoff = require_handoff(handoff)
    rig = canonical_rig_signature(rig_contract)
    errors = rig_signature_errors(rig)
    if errors:
        raise ValueError(" ".join(errors))
    variant = _variant_from_handoff(handoff, appearance=appearance)
    return {
        "schema": FORGE_FAMILY_SCHEMA,
        "schemaVersion": FORGE_FAMILY_SCHEMA_VERSION,
        "familySource": FAMILY_SOURCE_SBF,
        "familyId": str(handoff["family_id"]),
        "displayName": str(handoff["family_display_name"]),
        "technicalBodySchema": str(handoff["technical_body_schema"]),
        "technicalBodySchemaVersion": int(handoff["technical_body_schema_version"]),
        "technicalBodyFingerprint": str(handoff["technical_body_fingerprint"]),
        "canonicalRig": rig,
        "baseVariantId": variant["variantId"],
        "activeVariantId": variant["variantId"],
        "revision": 1,
        "shared": {
            "revision": 1,
            "actionIds": [],
            "damageRevision": 1,
            "socketPolicy": SOCKET_POLICY,
        },
        "variants": [variant],
    }


def _forge_texture_variant(
    variant_id,
    display_name,
    export_identity,
    *,
    appearance=None,
    appearance_fingerprint="",
    approved_at_utc="",
    approved=False,
):
    variant_id = str(variant_id).strip()
    display_name = str(display_name).strip()
    export_identity = str(export_identity).strip()
    if not variant_id or not display_name or not export_identity:
        raise ValueError(
            "Forge texture variants require a variant ID, display name, and export identity."
        )
    fingerprint = str(appearance_fingerprint).strip()
    if approved and not _HEX_64.fullmatch(fingerprint):
        raise ValueError(
            "An approved Forge texture variant requires a SHA-256 appearance fingerprint."
        )
    return {
        "variantId": variant_id,
        "displayName": display_name,
        "exportIdentity": export_identity,
        "appearanceRevision": 1,
        "appearanceFingerprint": fingerprint,
        "appearanceApprovedAtUtc": str(approved_at_utc) if approved else "",
        "skinAndBonesVersion": "",
        "appearanceSource": FAMILY_SOURCE_FORGE_TEXTURE,
        "appearanceApprovalAuthority": FORGE_TEXTURE_APPROVAL_AUTHORITY,
        "appearanceApprovalState": "APPROVED" if approved else "DRAFT",
        "handoff": None,
        "appearance": copy.deepcopy(appearance or {}),
        "forgeRevision": 1,
        "actionOverrides": {},
        "damageKeyOverrides": {},
        "progressiveSiteOverrides": {},
    }


def new_forge_texture_family(
    family_id,
    display_name,
    variant_id,
    variant_display_name,
    export_identity,
    technical_body_fingerprint,
    rig_contract,
    *,
    appearance=None,
    appearance_fingerprint="",
    approved_at_utc="",
):
    """Create a family by snapshotting materials on a finished Forge Damage Rig.

    This is deliberately not a synthetic Skin & Bones handoff.  It never joins
    separately imported geometry; the stored technical fingerprint locks every
    texture iteration to the already-authored runtime body.
    """

    family_id = str(family_id).strip()
    display_name = str(display_name).strip()
    fingerprint = str(technical_body_fingerprint).strip()
    if not family_id or not display_name:
        raise ValueError("Forge texture families require a family ID and display name.")
    if not _HEX_64.fullmatch(fingerprint):
        raise ValueError(
            "Finished Damage Rig technical-body fingerprint must be a SHA-256 hex value."
        )
    rig = canonical_rig_signature(rig_contract)
    errors = rig_signature_errors(rig)
    if errors:
        raise ValueError(" ".join(errors))
    variant = _forge_texture_variant(
        variant_id,
        variant_display_name,
        export_identity,
        appearance=appearance,
        appearance_fingerprint=appearance_fingerprint,
        approved_at_utc=approved_at_utc,
        approved=True,
    )
    return {
        "schema": FORGE_FAMILY_SCHEMA,
        "schemaVersion": FORGE_FAMILY_SCHEMA_VERSION,
        "familySource": FAMILY_SOURCE_FORGE_TEXTURE,
        "familyId": family_id,
        "displayName": display_name,
        "technicalBodySchema": FORGE_TEXTURE_BODY_SCHEMA,
        "technicalBodySchemaVersion": FORGE_TEXTURE_BODY_SCHEMA_VERSION,
        "technicalBodyFingerprint": fingerprint,
        "canonicalRig": rig,
        "baseVariantId": variant["variantId"],
        "activeVariantId": variant["variantId"],
        "revision": 1,
        "shared": {
            "revision": 1,
            "actionIds": [],
            "damageRevision": 1,
            "socketPolicy": SOCKET_POLICY,
        },
        "variants": [variant],
    }


def normalize_family(value):
    if not isinstance(value, Mapping):
        raise ValueError("Character Variant Family state must be an object.")
    state = copy.deepcopy(dict(value))
    if state.get("schema") != FORGE_FAMILY_SCHEMA:
        raise ValueError("Character Variant Family state uses an unsupported schema.")
    if int(state.get("schemaVersion", 0)) != FORGE_FAMILY_SCHEMA_VERSION:
        raise ValueError("Character Variant Family state uses an unsupported schema version.")
    state.setdefault("familySource", FAMILY_SOURCE_SBF)
    if state["familySource"] not in {
        FAMILY_SOURCE_SBF,
        FAMILY_SOURCE_FORGE_TEXTURE,
    }:
        raise ValueError("Character Variant Family has an unsupported family source.")
    state.setdefault("revision", 1)
    state.setdefault("baseVariantId", "")
    state.setdefault("activeVariantId", state.get("baseVariantId", ""))
    state.setdefault("variants", [])
    shared = state.setdefault("shared", {})
    shared.setdefault("revision", 1)
    shared.setdefault("actionIds", [])
    shared.setdefault("damageRevision", 1)
    shared["socketPolicy"] = SOCKET_POLICY
    seen = set()
    for variant in state["variants"]:
        variant_id = str(variant.get("variantId", ""))
        if not variant_id or variant_id in seen:
            raise ValueError("Character Variant Family contains a missing or duplicate variant ID.")
        seen.add(variant_id)
        variant.setdefault("forgeRevision", 1)
        variant.setdefault("appearance", {})
        variant.setdefault("appearanceSource", state["familySource"])
        variant.setdefault(
            "appearanceApprovalAuthority",
            "SKIN_AND_BONES"
            if state["familySource"] == FAMILY_SOURCE_SBF
            else FORGE_TEXTURE_APPROVAL_AUTHORITY,
        )
        variant.setdefault(
            "appearanceApprovalState",
            "APPROVED"
            if str(variant.get("appearanceFingerprint", ""))
            else "DRAFT",
        )
        variant.setdefault("actionOverrides", {})
        variant.setdefault("damageKeyOverrides", {})
        variant.setdefault("progressiveSiteOverrides", {})
    if state["activeVariantId"] not in seen:
        raise ValueError("Character Variant Family active variant is missing.")
    if state["baseVariantId"] not in seen:
        raise ValueError("Character Variant Family base variant is missing.")
    return state


def variant_by_id(state, variant_id=None):
    state = normalize_family(state)
    requested = str(variant_id or state["activeVariantId"])
    for variant in state["variants"]:
        if variant["variantId"] == requested:
            return variant
    raise KeyError(f"Appearance variant {requested!r} is not in this family.")


def _variant_reference(state, variant_id=None):
    requested = str(variant_id or state["activeVariantId"])
    for variant in state["variants"]:
        if variant["variantId"] == requested:
            return variant
    raise KeyError(f"Appearance variant {requested!r} is not in this family.")


def compatibility_errors(state, handoff, rig_contract):
    state = normalize_family(state)
    errors = handoff_errors(handoff)
    if errors:
        return errors
    handoff = decode_handoff(handoff)
    comparisons = (
        ("family_id", "familyId", "technical family ID"),
        (
            "technical_body_schema",
            "technicalBodySchema",
            "technical-body fingerprint schema",
        ),
        (
            "technical_body_schema_version",
            "technicalBodySchemaVersion",
            "technical-body fingerprint schema version",
        ),
        (
            "technical_body_fingerprint",
            "technicalBodyFingerprint",
            "technical-body fingerprint",
        ),
    )
    for incoming, stored, label in comparisons:
        if handoff.get(incoming) != state.get(stored):
            errors.append(
                f"Incompatible {label}: incoming {handoff.get(incoming)!r}, "
                f"family {state.get(stored)!r}."
            )
    signature = canonical_rig_signature(rig_contract)
    errors.extend(rig_signature_errors(signature))
    if signature != canonical_rig_signature(state.get("canonicalRig", {})):
        errors.append("Canonical rig/coordinate contract differs from the family base.")
    if any(
        variant.get("variantId") == handoff.get("variant_id")
        for variant in state["variants"]
    ):
        errors.append(
            f"Appearance variant {handoff.get('variant_id')!r} already belongs to this family."
        )
    incoming_export = safe_identifier(handoff.get("export_identity", ""))
    if any(
        safe_identifier(variant.get("exportIdentity", "")) == incoming_export
        for variant in state["variants"]
    ):
        errors.append(
            f"Appearance export identity {handoff.get('export_identity')!r} "
            "would collide with an existing family output."
        )
    return errors


def add_variant(state, handoff, rig_contract, *, appearance=None):
    state = normalize_family(state)
    if state["familySource"] != FAMILY_SOURCE_SBF:
        raise ValueError(
            "Skin & Bones GLB variants cannot be joined to a finished-rig texture family."
        )
    handoff = decode_handoff(handoff)
    errors = compatibility_errors(state, handoff, rig_contract)
    if errors:
        raise ValueError(" ".join(errors))
    state["variants"].append(_variant_from_handoff(handoff, appearance=appearance))
    state["activeVariantId"] = str(handoff["variant_id"])
    state["revision"] = int(state.get("revision", 1)) + 1
    return state


def forge_texture_variant_errors(
    state,
    variant_id,
    export_identity,
    technical_body_fingerprint,
    rig_contract,
):
    state = normalize_family(state)
    errors = []
    if state["familySource"] != FAMILY_SOURCE_FORGE_TEXTURE:
        errors.append(
            "Forge texture snapshots can only be added to a finished-rig texture family."
        )
    fingerprint = str(technical_body_fingerprint)
    if fingerprint != str(state.get("technicalBodyFingerprint", "")):
        errors.append(
            "The finished Damage Rig/body changed after the texture family was started."
        )
    signature = canonical_rig_signature(rig_contract)
    errors.extend(rig_signature_errors(signature))
    if signature != canonical_rig_signature(state.get("canonicalRig", {})):
        errors.append("Canonical Damage Rig/coordinate contract differs from the family base.")
    variant_id = str(variant_id).strip()
    if not variant_id:
        errors.append("Texture variant ID is empty.")
    elif any(value.get("variantId") == variant_id for value in state["variants"]):
        errors.append(f"Appearance variant {variant_id!r} already belongs to this family.")
    export_identity = str(export_identity).strip()
    normalized_export = safe_identifier(export_identity)
    if not export_identity:
        errors.append("Texture variant export identity is empty.")
    elif any(
        safe_identifier(value.get("exportIdentity", "")) == normalized_export
        for value in state["variants"]
    ):
        errors.append(
            f"Appearance export identity {export_identity!r} would collide with an existing family output."
        )
    return errors


def add_forge_texture_variant(
    state,
    variant_id,
    display_name,
    export_identity,
    technical_body_fingerprint,
    rig_contract,
    *,
    appearance=None,
):
    state = normalize_family(state)
    errors = forge_texture_variant_errors(
        state,
        variant_id,
        export_identity,
        technical_body_fingerprint,
        rig_contract,
    )
    if errors:
        raise ValueError(" ".join(errors))
    variant = _forge_texture_variant(
        variant_id,
        display_name,
        export_identity,
        appearance=appearance,
        approved=False,
    )
    state["variants"].append(variant)
    state["activeVariantId"] = variant["variantId"]
    state["revision"] = int(state.get("revision", 1)) + 1
    return state


def approve_forge_texture_variant(
    state,
    appearance_fingerprint,
    approved_at_utc,
    *,
    appearance=None,
    variant_id=None,
):
    state = normalize_family(state)
    if state["familySource"] != FAMILY_SOURCE_FORGE_TEXTURE:
        raise ValueError("Skin & Bones appearances remain approved by Skin & Bones.")
    fingerprint = str(appearance_fingerprint).strip()
    if not _HEX_64.fullmatch(fingerprint):
        raise ValueError("Texture approval requires a SHA-256 appearance fingerprint.")
    variant = _variant_reference(state, variant_id)
    if appearance is not None:
        variant["appearance"] = copy.deepcopy(appearance)
    variant["appearanceRevision"] = int(variant.get("appearanceRevision", 0)) + 1
    variant["appearanceFingerprint"] = fingerprint
    variant["appearanceApprovedAtUtc"] = str(approved_at_utc)
    variant["appearanceApprovalState"] = "APPROVED"
    variant["forgeRevision"] = int(variant.get("forgeRevision", 1)) + 1
    state["revision"] = int(state.get("revision", 1)) + 1
    return state


def begin_forge_texture_variant_edit(state, variant_id=None):
    """Make one approved native look deliberately editable again.

    The last fingerprint remains available for diagnostics, but export is
    blocked until the artist approves the newly reviewed appearance.
    """

    state = normalize_family(state)
    if state["familySource"] != FAMILY_SOURCE_FORGE_TEXTURE:
        raise ValueError("Skin & Bones appearance pixels remain owned by Skin & Bones.")
    variant = _variant_reference(state, variant_id)
    variant["appearanceApprovalState"] = "DRAFT"
    variant["forgeRevision"] = int(variant.get("forgeRevision", 1)) + 1
    state["revision"] = int(state.get("revision", 1)) + 1
    return state


def variant_appearance_approved(state, variant_id=None, current_fingerprint=None):
    variant = variant_by_id(state, variant_id)
    approved = (
        str(variant.get("appearanceApprovalState", "")) == "APPROVED"
        and bool(str(variant.get("appearanceFingerprint", "")))
    )
    if current_fingerprint is not None:
        approved = approved and (
            str(current_fingerprint) == str(variant.get("appearanceFingerprint", ""))
        )
    return bool(approved)


def set_active_variant(state, variant_id):
    state = normalize_family(state)
    variant_by_id(state, variant_id)
    state["activeVariantId"] = str(variant_id)
    return state


def register_shared_actions(state, action_ids):
    state = normalize_family(state)
    values = sorted({str(value) for value in action_ids if str(value)})
    if values != list(state["shared"].get("actionIds", [])):
        state["shared"]["actionIds"] = values
        state["shared"]["revision"] = int(state["shared"].get("revision", 1)) + 1
        state["revision"] = int(state.get("revision", 1)) + 1
    return state


def resolve_action_id(state, shared_action_id, variant_id=None):
    variant = variant_by_id(state, variant_id)
    override = variant.get("actionOverrides", {}).get(str(shared_action_id))
    if override:
        return str(override.get("overrideActionId", "")), ACTION_SCOPE_OVERRIDE
    return str(shared_action_id), "INHERITED"


def set_action_override(state, shared_action_id, override_action_id, variant_id=None):
    state = normalize_family(state)
    variant = _variant_reference(state, variant_id)
    shared_action_id = str(shared_action_id)
    if shared_action_id not in set(state["shared"].get("actionIds", [])):
        raise ValueError("Only a registered shared family Action can be overridden.")
    variant["actionOverrides"][shared_action_id] = {
        "kind": "ACTION",
        "sharedActionId": shared_action_id,
        "overrideActionId": str(override_action_id),
    }
    variant["forgeRevision"] = int(variant.get("forgeRevision", 1)) + 1
    state["revision"] = int(state.get("revision", 1)) + 1
    return state


def remove_action_override(state, shared_action_id, variant_id=None):
    state = normalize_family(state)
    variant = _variant_reference(state, variant_id)
    removed = variant["actionOverrides"].pop(str(shared_action_id), None)
    if removed:
        variant["forgeRevision"] = int(variant.get("forgeRevision", 1)) + 1
        state["revision"] = int(state.get("revision", 1)) + 1
    return state, removed


def set_damage_key_override(state, record, variant_id=None):
    state = normalize_family(state)
    variant = _variant_reference(state, variant_id)
    record = copy.deepcopy(dict(record))
    shared_id = str(record.get("sharedDamageKeyId", ""))
    override_id = str(record.get("overrideDamageKeyId", ""))
    if not shared_id or not override_id:
        raise ValueError("Damage Key override requires shared and override Damage Key IDs.")
    record["kind"] = DAMAGE_KEY_KIND
    variant["damageKeyOverrides"][shared_id] = record
    variant["forgeRevision"] = int(variant.get("forgeRevision", 1)) + 1
    state["revision"] = int(state.get("revision", 1)) + 1
    return state


def remove_damage_key_override(state, shared_damage_key_id, variant_id=None):
    state = normalize_family(state)
    variant = _variant_reference(state, variant_id)
    removed = variant["damageKeyOverrides"].pop(str(shared_damage_key_id), None)
    if removed:
        variant["forgeRevision"] = int(variant.get("forgeRevision", 1)) + 1
        state["revision"] = int(state.get("revision", 1)) + 1
    return state, removed


def set_progressive_site_override(state, record, variant_id=None):
    state = normalize_family(state)
    variant = _variant_reference(state, variant_id)
    record = copy.deepcopy(dict(record))
    shared_guid = str(record.get("sharedSiteGuid", ""))
    override_guid = str(record.get("overrideSiteGuid", ""))
    if not shared_guid or not override_guid:
        raise ValueError("Progressive Site override requires shared and override site GUIDs.")
    record["kind"] = PROGRESSIVE_SITE_KIND
    variant["progressiveSiteOverrides"][shared_guid] = record
    variant["forgeRevision"] = int(variant.get("forgeRevision", 1)) + 1
    state["revision"] = int(state.get("revision", 1)) + 1
    return state


def remove_progressive_site_override(state, shared_site_guid, variant_id=None):
    state = normalize_family(state)
    variant = _variant_reference(state, variant_id)
    removed = variant["progressiveSiteOverrides"].pop(str(shared_site_guid), None)
    if removed:
        variant["forgeRevision"] = int(variant.get("forgeRevision", 1)) + 1
        state["revision"] = int(state.get("revision", 1)) + 1
    return state, removed


def effective_damage_key_names(state, region_id, physical_records, variant_id=None):
    """Resolve physical shape-key records to the active variant's live set."""

    if not state:
        return [str(record.get("name", "")) for record in physical_records]
    variant = variant_by_id(state, variant_id)
    overrides = variant.get("damageKeyOverrides", {})
    site_owned = {
        str(item.get("overrideDamageKeyId", ""))
        for record in variant.get("progressiveSiteOverrides", {}).values()
        for item in record.get("ownedDamageKeys", [])
    }
    site_shared = {
        str(item.get("sharedDamageKeyId", ""))
        for record in variant.get("progressiveSiteOverrides", {}).values()
        for item in record.get("ownedDamageKeys", [])
    }
    result = []
    for record in physical_records:
        name = str(record.get("name", ""))
        key_id = str(record.get("damageKeyId", ""))
        owner_variant = str(record.get("ownerVariantId", ""))
        shared_id = str(record.get("sharedDamageKeyId", ""))
        if str(record.get("regionId", region_id)) != str(region_id):
            continue
        if owner_variant:
            if owner_variant != variant["variantId"]:
                continue
            if key_id in site_owned or any(
                value.get("overrideDamageKeyId") == key_id
                for value in overrides.values()
            ):
                result.append(name)
            continue
        override = overrides.get(key_id)
        if override:
            override_name = str(override.get("overrideName", ""))
            if override_name:
                result.append(override_name)
            continue
        if key_id in site_shared:
            continue
        if not shared_id:
            result.append(name)
    return list(dict.fromkeys(result))


def progressive_clone_plan(site, damage_keys):
    """Return the minimum coherent copy set for one Progressive Site."""

    site = copy.deepcopy(dict(site))
    by_id = {
        str(record.get("damageKeyId", "")): copy.deepcopy(dict(record))
        for record in damage_keys
        if str(record.get("damageKeyId", ""))
    }
    required = []
    errors = []
    stages = site.get("stages", {})
    if isinstance(stages, list):
        stages = {str(item.get("stage", "")).upper(): item for item in stages}
    for stage_name in ("LIGHT", "MEDIUM", "HEAVY"):
        stage = dict(stages.get(stage_name, {}))
        key_id = str(stage.get("damageKeyId", ""))
        if not key_id:
            errors.append(f"Progressive Site {stage_name} stage has no Damage Key ID.")
            continue
        if key_id not in by_id:
            errors.append(
                f"Progressive Site {stage_name} references missing Damage Key {key_id!r}."
            )
            continue
        if key_id not in required:
            required.append(key_id)
    return {
        "siteGuid": str(site.get("siteGuid", "")),
        "damageKeyIds": required,
        "damageKeys": [by_id[value] for value in required if value in by_id],
        "errors": errors,
    }


def effective_progressive_sites(state, sites, variant_id=None):
    """Resolve site replacement first, then logical Damage Key replacement."""

    if not state:
        return copy.deepcopy(list(sites))
    variant = variant_by_id(state, variant_id)
    site_overrides = variant.get("progressiveSiteOverrides", {})
    damage_overrides = variant.get("damageKeyOverrides", {})
    override_guids = {
        str(value.get("overrideSiteGuid", "")) for value in site_overrides.values()
    }
    result = []
    for source in sites:
        source = copy.deepcopy(dict(source))
        guid = str(source.get("siteGuid", ""))
        owner_variant = str(source.get("ownerVariantId", ""))
        if owner_variant and owner_variant != variant["variantId"]:
            continue
        if guid in override_guids:
            result.append(source)
            continue
        override = site_overrides.get(guid)
        if override:
            replacement_guid = str(override.get("overrideSiteGuid", ""))
            replacement = next(
                (
                    copy.deepcopy(dict(candidate))
                    for candidate in sites
                    if str(candidate.get("siteGuid", "")) == replacement_guid
                ),
                None,
            )
            if replacement is not None:
                result.append(replacement)
            continue
        if owner_variant:
            continue
        stages = source.get("stages", {})
        iterable = stages.values() if isinstance(stages, Mapping) else stages
        for stage in iterable:
            shared_id = str(stage.get("damageKeyId", ""))
            replacement = damage_overrides.get(shared_id)
            if replacement:
                stage["damageKeyId"] = str(replacement["overrideDamageKeyId"])
                stage["deformationKeyName"] = str(replacement["overrideName"])
                stage["ownerVariantId"] = variant["variantId"]
        result.append(source)
    # A site override is encountered once while replacing the shared site and
    # again when the physical variant-owned record is visited. Preserve the
    # first resolved ordering while emitting each site exactly once.
    deduplicated = []
    emitted = set()
    for site in result:
        guid = str(site.get("siteGuid", ""))
        if guid in emitted:
            continue
        emitted.add(guid)
        deduplicated.append(site)
    return deduplicated


def effective_readiness(
    state,
    *,
    appearance_approved,
    technical_compatible,
    shared_valid,
    action_validity=None,
    damage_validity=None,
    variant_id=None,
):
    variant = variant_by_id(state, variant_id)
    action_validity = action_validity or {}
    damage_validity = damage_validity or {}
    override_ids = [
        str(record.get("overrideActionId", ""))
        for record in variant.get("actionOverrides", {}).values()
    ]
    override_ids.extend(
        str(record.get("overrideDamageKeyId", ""))
        for record in variant.get("damageKeyOverrides", {}).values()
    )
    override_ids.extend(
        str(record.get("overrideSiteGuid", ""))
        for record in variant.get("progressiveSiteOverrides", {}).values()
    )
    invalid = [
        value
        for value in override_ids
        if not bool(action_validity.get(value, damage_validity.get(value, False)))
    ]
    ready = bool(
        appearance_approved
        and technical_compatible
        and shared_valid
        and not invalid
    )
    return {
        "appearanceApproved": bool(appearance_approved),
        "technicalFamilyCompatible": bool(technical_compatible),
        "sharedForgeContentValid": bool(shared_valid),
        "variantOverridesValid": not invalid,
        "invalidOverrideIds": invalid,
        "completeExportValid": ready,
        "status": "READY" if ready else "NOT_READY",
    }


def export_provenance(state, variant_id=None):
    state = normalize_family(state)
    variant = variant_by_id(state, variant_id)
    action_overrides = sorted(
        (
            {
                "sharedActionId": str(record.get("sharedActionId", shared_id)),
                "overrideActionId": str(record.get("overrideActionId", "")),
            }
            for shared_id, record in variant.get("actionOverrides", {}).items()
        ),
        key=lambda value: value["sharedActionId"],
    )
    damage_key_overrides = sorted(
        (
            {
                "sharedDamageKeyId": str(record.get("sharedDamageKeyId", shared_id)),
                "overrideDamageKeyId": str(record.get("overrideDamageKeyId", "")),
                "regionId": str(record.get("regionId", "")),
            }
            for shared_id, record in variant.get("damageKeyOverrides", {}).items()
        ),
        key=lambda value: value["sharedDamageKeyId"],
    )
    site_overrides = sorted(
        (
            {
                "sharedSiteGuid": str(record.get("sharedSiteGuid", shared_guid)),
                "overrideSiteGuid": str(record.get("overrideSiteGuid", "")),
            }
            for shared_guid, record in variant.get("progressiveSiteOverrides", {}).items()
        ),
        key=lambda value: value["sharedSiteGuid"],
    )
    revision_record = {
        "familyRevision": int(state.get("revision", 1)),
        "sharedRevision": int(state["shared"].get("revision", 1)),
        "variantRevision": int(variant.get("forgeRevision", 1)),
        "appearanceRevision": int(variant.get("appearanceRevision", 0)),
    }
    effective_revision = canonical_digest(
        {
            **revision_record,
            "actionOverrides": action_overrides,
            "damageKeyOverrides": damage_key_overrides,
            "progressiveSiteOverrides": site_overrides,
        }
    )[:20]
    return {
        "schema": FORGE_PROVENANCE_SCHEMA,
        "schemaVersion": FORGE_PROVENANCE_SCHEMA_VERSION,
        "technicalFamilyId": state["familyId"],
        "familySource": state["familySource"],
        "appearanceVariantId": variant["variantId"],
        "appearanceApprovalAuthority": variant["appearanceApprovalAuthority"],
        "appearanceFingerprint": variant["appearanceFingerprint"],
        "appearanceExportIdentity": variant["exportIdentity"],
        "technicalBodyFingerprint": state["technicalBodyFingerprint"],
        "effectiveForgeVariantIdentity": (
            f"{state['familyId']}:{variant['variantId']}:{effective_revision}"
        ),
        "effectiveForgeRevision": effective_revision,
        "revisions": revision_record,
        "sharedSocketPolicy": SOCKET_POLICY,
        "actionOverrides": action_overrides,
        "damageKeyOverrides": damage_key_overrides,
        "progressiveSiteOverrides": site_overrides,
    }


__all__ = tuple(
    name
    for name in globals()
    if name.isupper()
    or name
    in {
        "add_forge_texture_variant",
        "begin_forge_texture_variant_edit",
        "add_variant",
        "approve_forge_texture_variant",
        "canonical_digest",
        "canonical_rig_signature",
        "compatibility_errors",
        "decode_handoff",
        "effective_damage_key_names",
        "effective_progressive_sites",
        "effective_readiness",
        "export_provenance",
        "forge_texture_variant_errors",
        "handoff_errors",
        "new_family",
        "new_forge_texture_family",
        "normalize_family",
        "progressive_clone_plan",
        "register_shared_actions",
        "remove_action_override",
        "remove_damage_key_override",
        "remove_progressive_site_override",
        "require_handoff",
        "resolve_action_id",
        "rig_signature_errors",
        "safe_identifier",
        "set_action_override",
        "set_active_variant",
        "set_damage_key_override",
        "set_progressive_site_override",
        "stable_json",
        "variant_by_id",
        "variant_appearance_approved",
    }
)
