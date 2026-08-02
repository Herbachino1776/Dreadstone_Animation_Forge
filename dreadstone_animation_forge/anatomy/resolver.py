"""Deterministic role and variable-length chain resolution."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .model import RigSnapshot
from .profiles import ANIMATE_ANYTHING_PROFILE, HUMANOID_PROFILE_ID
from .schema import AnatomyProfile


def normalize_name(name: str) -> str:
    value = str(name).lower().replace("mixamorig", "")
    return re.sub(r"[^a-z0-9]", "", value)


def _normalized_alias_score(
    normalized: str,
    normalized_aliases: tuple[str, ...],
) -> int:
    best = 0
    for candidate in normalized_aliases:
        if not candidate:
            continue
        if normalized == candidate:
            best = max(best, 100)
        elif normalized.startswith(candidate) or normalized.endswith(candidate):
            best = max(best, 80)
        elif candidate in normalized:
            best = max(best, 60)
    return best


def _normalized_side_adjustment(role: str, normalized: str) -> int:
    left_role = role.endswith("_l") or "_l_" in role or role.startswith("left_")
    right_role = role.endswith("_r") or "_r_" in role or role.startswith("right_")
    left_name = "left" in normalized or normalized.endswith("l")
    right_name = "right" in normalized or normalized.endswith("r")
    if left_role:
        return (10 if left_name else 0) - (40 if right_name else 0)
    if right_role:
        return (10 if right_name else 0) - (40 if left_name else 0)
    return 0


def _natural_key(name: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", normalize_name(name))
        if part != ""
    )


def _order_chain(names: list[str], snapshot: RigSnapshot) -> tuple[list[str], bool]:
    if not names:
        return [], False
    selected = set(names)
    by_name = snapshot.by_name()
    roots = sorted(
        (name for name in names if by_name[name].parent not in selected),
        key=_natural_key,
    )
    ambiguous = len(roots) != 1
    if len(roots) != 1:
        return sorted(names, key=_natural_key), True
    ordered = [roots[0]]
    remaining = selected - set(ordered)
    while remaining:
        children = sorted(
            (name for name in remaining if by_name[name].parent == ordered[-1]),
            key=_natural_key,
        )
        if len(children) != 1:
            ambiguous = True
            ordered.extend(sorted(remaining, key=_natural_key))
            break
        ordered.append(children[0])
        remaining.remove(children[0])
    return ordered, ambiguous


def resolve_roles(
    profile: AnatomyProfile,
    snapshot: RigSnapshot,
    *,
    manual_overrides: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    by_name = snapshot.by_name()
    mapping: dict[str, object] = {}
    ambiguities: list[dict[str, object]] = []
    owned: set[str] = set()
    normalized_names = {
        bone.name: normalize_name(bone.name)
        for bone in snapshot.bones
    }
    normalized_aliases = {
        role: tuple(
            normalize_name(alias)
            for alias in profile.aliases.get(role, (role,))
        )
        for role in profile.all_roles()
    }

    if profile.profile_id == HUMANOID_PROFILE_ID:
        exact_required = set(ANIMATE_ANYTHING_PROFILE.values()) - {"arm_left_hand", "arm_right_hand"}
        if exact_required.issubset(by_name):
            for role, bone_name in ANIMATE_ANYTHING_PROFILE.items():
                if bone_name in by_name:
                    mapping[role] = bone_name
                    owned.add(bone_name)

    scalar_roles = profile.required_roles + profile.optional_roles
    for role in scalar_roles:
        if role in mapping:
            continue
        candidates: list[tuple[int, str]] = []
        aliases = normalized_aliases[role]
        for bone in snapshot.bones:
            normalized = normalized_names[bone.name]
            base_score = _normalized_alias_score(normalized, aliases)
            if base_score > 0:
                candidates.append((
                    base_score + _normalized_side_adjustment(role, normalized),
                    bone.name,
                ))
        candidates.sort(
            key=lambda item: (-item[0], normalized_names[item[1]], item[1])
        )
        if not candidates:
            continue
        best_score = candidates[0][0]
        tied = [name for score, name in candidates if score == best_score]
        available = [name for name in tied if name not in owned]
        chosen_pool = available or tied
        chosen = chosen_pool[0]
        mapping[role] = chosen
        owned.add(chosen)
        if len(tied) > 1:
            ambiguities.append({"role": role, "candidates": tied, "selected": chosen})

    for role, spec in profile.chains.items():
        aliases = normalized_aliases[role]
        candidates = [
            bone.name
            for bone in snapshot.bones
            if (
                _normalized_alias_score(normalized_names[bone.name], aliases) >= 60
                and bone.name not in owned
            )
        ]
        ordered, ambiguous = _order_chain(candidates, snapshot)
        if spec.max_count is not None:
            ordered = ordered[:spec.max_count]
        if ordered:
            mapping[role] = ordered
            owned.update(ordered)
        if ambiguous and ordered:
            ambiguities.append({"role": role, "candidates": ordered, "selected": ordered})

    for role, bone_name in sorted((manual_overrides or {}).items()):
        if bone_name and bone_name in by_name and role in profile.all_roles():
            mapping[role] = bone_name

    return {
        "mapping": mapping,
        "ambiguities": ambiguities,
        "mappingDigest": mapping_digest(mapping),
    }


def canonical_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for role, value in sorted(mapping.items()):
        if isinstance(value, (list, tuple)):
            result[str(role)] = [str(name) for name in value]
        elif value:
            result[str(role)] = str(value)
    return result


def mapping_digest(mapping: Mapping[str, object]) -> str:
    payload = json.dumps(
        canonical_mapping(mapping),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def mapped_bone_names(mapping: Mapping[str, object]) -> list[str]:
    values: list[str] = []
    for value in mapping.values():
        if isinstance(value, (list, tuple)):
            values.extend(str(name) for name in value if name)
        elif value:
            values.append(str(value))
    return values


__all__ = (
    "canonical_mapping",
    "mapped_bone_names",
    "mapping_digest",
    "normalize_name",
    "resolve_roles",
)
