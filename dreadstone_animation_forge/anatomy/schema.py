"""Versioned, Blender-independent Creature Anatomy Profile schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


PROFILE_SCHEMA = "dreadstone.creature_anatomy_profile.v1"
PROFILE_SCHEMA_VERSION = 1
VALID_AXES = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")


def axis_vector(axis: str) -> tuple[float, float, float]:
    try:
        sign = 1.0 if axis[0] == "+" else -1.0
        index = "XYZ".index(axis[1])
    except (IndexError, ValueError, TypeError):
        raise ValueError(f"Invalid signed axis {axis!r}.") from None
    values = [0.0, 0.0, 0.0]
    values[index] = sign
    return tuple(values)


def axes_orthogonal(first: str, second: str) -> bool:
    a = axis_vector(first)
    b = axis_vector(second)
    return abs(sum(x * y for x, y in zip(a, b))) <= 1.0e-8


@dataclass(frozen=True)
class ChainSpec:
    min_count: int = 0
    max_count: int | None = None
    required: bool = False
    ordered: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "minCount": int(self.min_count),
            "maxCount": self.max_count,
            "required": bool(self.required),
            "ordered": bool(self.ordered),
        }


@dataclass(frozen=True)
class CapabilitySpec:
    supported: bool
    production_ready: bool = False
    required_roles: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": bool(self.supported),
            "productionReady": bool(self.production_ready),
            "requiredRoles": list(self.required_roles),
        }


@dataclass(frozen=True)
class AnatomyProfile:
    profile_id: str
    creature_class: str
    locomotion_class: str
    forward_axis: str
    up_axis: str
    required_roles: tuple[str, ...]
    optional_roles: tuple[str, ...] = ()
    chains: Mapping[str, ChainSpec] = field(default_factory=dict)
    bilateral_groups: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    symmetry_pairs: tuple[tuple[str, str], ...] = ()
    contact_roles: tuple[str, ...] = ()
    aliases: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    capabilities: Mapping[str, CapabilitySpec] = field(default_factory=dict)
    damage_region_templates: tuple[Mapping[str, Any], ...] = ()
    schema: str = PROFILE_SCHEMA

    def all_roles(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            self.required_roles + self.optional_roles + tuple(self.chains)
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "profileId": self.profile_id,
            "creatureClass": self.creature_class,
            "locomotionClass": self.locomotion_class,
            "forwardAxis": self.forward_axis,
            "upAxis": self.up_axis,
            "requiredRoles": list(self.required_roles),
            "optionalRoles": list(self.optional_roles),
            "chains": {
                name: spec.to_dict() for name, spec in sorted(self.chains.items())
            },
            "bilateralGroups": {
                name: list(pair) for name, pair in sorted(self.bilateral_groups.items())
            },
            "symmetryPairs": [list(pair) for pair in self.symmetry_pairs],
            "contactRoles": list(self.contact_roles),
            "damageRegionTemplates": [dict(value) for value in self.damage_region_templates],
            "capabilities": {
                name: spec.to_dict() for name, spec in sorted(self.capabilities.items())
            },
            "aliases": {
                name: list(values) for name, values in sorted(self.aliases.items())
            },
        }


def validate_profile(profile: AnatomyProfile) -> list[str]:
    errors: list[str] = []
    if profile.schema != PROFILE_SCHEMA:
        errors.append(f"Unsupported anatomy profile schema {profile.schema!r}.")
    if not profile.profile_id or profile.profile_id != profile.profile_id.upper():
        errors.append("profileId must be a non-empty uppercase stable identifier.")
    if profile.forward_axis not in VALID_AXES or profile.up_axis not in VALID_AXES:
        errors.append("forwardAxis and upAxis must use signed X/Y/Z notation.")
    else:
        if not axes_orthogonal(profile.forward_axis, profile.up_axis):
            errors.append("forwardAxis and upAxis must be orthogonal.")
    if not profile.creature_class:
        errors.append("creatureClass is required.")
    if not profile.locomotion_class:
        errors.append("locomotionClass is required.")
    scalar_roles = profile.required_roles + profile.optional_roles
    duplicates = sorted({role for role in scalar_roles if scalar_roles.count(role) > 1})
    if duplicates:
        errors.append("Duplicate scalar roles: " + ", ".join(duplicates) + ".")
    known = set(profile.all_roles())
    for name, spec in profile.chains.items():
        if not name:
            errors.append("Chain identifiers cannot be empty.")
        if spec.min_count < 0:
            errors.append(f"Chain {name!r} has a negative minimum.")
        if spec.required and spec.min_count < 1:
            errors.append(f"Required chain {name!r} must require at least one bone.")
        if spec.max_count is not None and spec.max_count < spec.min_count:
            errors.append(f"Chain {name!r} has maxCount below minCount.")
    for left, right in profile.symmetry_pairs:
        if left == right or left not in known or right not in known:
            errors.append(f"Invalid symmetry pair {left!r}/{right!r}.")
    for role in profile.contact_roles:
        if role not in known:
            errors.append(f"Unknown contact role {role!r}.")
    for name, pair in profile.bilateral_groups.items():
        if len(pair) != 2 or pair[0] not in known or pair[1] not in known:
            errors.append(f"Invalid bilateral group {name!r}.")
    for role in profile.aliases:
        if role not in known:
            errors.append(f"Aliases reference unknown role {role!r}.")
    region_ids = [str(value.get("regionId", "")) for value in profile.damage_region_templates]
    if any(not value for value in region_ids):
        errors.append("Every damage-region template needs a regionId.")
    if len(set(region_ids)) != len(region_ids):
        errors.append("Damage-region template IDs must be unique.")
    for name, capability in profile.capabilities.items():
        if not name:
            errors.append("Capability identifiers cannot be empty.")
        for role in capability.required_roles:
            if role not in known:
                errors.append(f"Capability {name!r} requires unknown role {role!r}.")
    return errors


def migrate_profile_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Migrate the small pre-v1 prototype shape into the public v1 contract."""

    value = dict(payload)
    schema = str(value.get("schema", ""))
    if schema == PROFILE_SCHEMA:
        return value
    if schema not in {"", "dreadstone.creature_profile.v0"}:
        raise ValueError(f"Unsupported anatomy profile schema {schema!r}.")
    aliases = {
        "id": "profileId",
        "creature_class": "creatureClass",
        "locomotion_class": "locomotionClass",
        "forward_axis": "forwardAxis",
        "up_axis": "upAxis",
        "required_roles": "requiredRoles",
        "optional_roles": "optionalRoles",
        "bilateral_groups": "bilateralGroups",
        "symmetry_pairs": "symmetryPairs",
        "contact_roles": "contactRoles",
        "damage_regions": "damageRegionTemplates",
    }
    for old, new in aliases.items():
        if new not in value and old in value:
            value[new] = value.pop(old)
    value["schema"] = PROFILE_SCHEMA
    value.setdefault("chains", {})
    value.setdefault("bilateralGroups", {})
    value.setdefault("capabilities", {})
    value.setdefault("aliases", {})
    return value


def profile_from_dict(payload: Mapping[str, Any]) -> AnatomyProfile:
    value = migrate_profile_payload(payload)
    profile = AnatomyProfile(
        schema=str(value["schema"]),
        profile_id=str(value["profileId"]),
        creature_class=str(value["creatureClass"]),
        locomotion_class=str(value["locomotionClass"]),
        forward_axis=str(value["forwardAxis"]),
        up_axis=str(value["upAxis"]),
        required_roles=tuple(str(role) for role in value.get("requiredRoles", [])),
        optional_roles=tuple(str(role) for role in value.get("optionalRoles", [])),
        chains={
            str(name): ChainSpec(
                min_count=int(spec.get("minCount", 0)),
                max_count=(
                    None if spec.get("maxCount") is None else int(spec["maxCount"])
                ),
                required=bool(spec.get("required", False)),
                ordered=bool(spec.get("ordered", True)),
            )
            for name, spec in value.get("chains", {}).items()
        },
        bilateral_groups={
            str(name): (str(pair[0]), str(pair[1]))
            for name, pair in value.get("bilateralGroups", {}).items()
        },
        symmetry_pairs=tuple(
            (str(pair[0]), str(pair[1])) for pair in value.get("symmetryPairs", [])
        ),
        contact_roles=tuple(str(role) for role in value.get("contactRoles", [])),
        damage_region_templates=tuple(
            dict(template) for template in value.get("damageRegionTemplates", [])
        ),
        capabilities={
            str(name): CapabilitySpec(
                supported=bool(spec.get("supported", False)),
                production_ready=bool(spec.get("productionReady", False)),
                required_roles=tuple(str(role) for role in spec.get("requiredRoles", [])),
            )
            for name, spec in value.get("capabilities", {}).items()
        },
        aliases={
            str(name): tuple(str(alias) for alias in values)
            for name, values in value.get("aliases", {}).items()
        },
    )
    errors = validate_profile(profile)
    if errors:
        raise ValueError("Invalid Creature Anatomy Profile: " + " ".join(errors))
    return profile


class ProfileRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, AnatomyProfile] = {}

    def register(self, profile: AnatomyProfile) -> AnatomyProfile:
        errors = validate_profile(profile)
        if errors:
            raise ValueError("Invalid Creature Anatomy Profile: " + " ".join(errors))
        prior = self._profiles.get(profile.profile_id)
        if prior is not None and prior != profile:
            raise ValueError(f"Profile {profile.profile_id!r} is already registered.")
        self._profiles[profile.profile_id] = profile
        return profile

    def get(self, profile_id: str) -> AnatomyProfile | None:
        return self._profiles.get(str(profile_id))

    def require(self, profile_id: str) -> AnatomyProfile:
        profile = self.get(profile_id)
        if profile is None:
            raise KeyError(f"Unknown Creature Anatomy Profile {profile_id!r}.")
        return profile

    def all(self) -> tuple[AnatomyProfile, ...]:
        return tuple(self._profiles[name] for name in sorted(self._profiles))


__all__ = (
    "PROFILE_SCHEMA",
    "PROFILE_SCHEMA_VERSION",
    "VALID_AXES",
    "AnatomyProfile",
    "CapabilitySpec",
    "ChainSpec",
    "ProfileRegistry",
    "axes_orthogonal",
    "axis_vector",
    "migrate_profile_payload",
    "profile_from_dict",
    "validate_profile",
)
