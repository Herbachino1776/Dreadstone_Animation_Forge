"""Profile-specific technical readiness validation."""

from __future__ import annotations

from math import isfinite
from typing import Mapping

from .model import RigSnapshot
from .schema import AnatomyProfile, axis_vector


def _values(mapping: Mapping[str, object], role: str) -> list[str]:
    value = mapping.get(role)
    if isinstance(value, (list, tuple)):
        return [str(name) for name in value if name]
    return [str(value)] if value else []


def _first(mapping: Mapping[str, object], role: str) -> str:
    values = _values(mapping, role)
    return values[0] if values else ""


def _is_ancestor(ancestor: str, descendant: str, by_name) -> bool:
    current = by_name.get(descendant)
    visited: set[str] = set()
    while current is not None and current.name not in visited:
        if current.parent == ancestor:
            return True
        visited.add(current.name)
        current = by_name.get(current.parent)
    return False


def _dot(a, b):
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _center(by_name, name):
    return by_name[name].center


def _block(blockers, code, message):
    blockers.append({"code": str(code), "message": str(message)})


def validate_mapping(
    profile: AnatomyProfile,
    mapping: Mapping[str, object],
    snapshot: RigSnapshot,
    orientation: Mapping[str, object],
) -> dict[str, object]:
    by_name = snapshot.by_name()
    blockers: list[dict[str, str]] = []
    warnings: list[str] = []
    missing = [role for role in profile.required_roles if not _values(mapping, role)]
    missing_chains = [
        role
        for role, spec in profile.chains.items()
        if spec.required and len(_values(mapping, role)) < spec.min_count
    ]
    if missing or missing_chains:
        missing_limb = any(
            role.startswith(("front_", "hind_")) for role in missing + missing_chains
        )
        _block(
            blockers,
            "MISSING_LIMB_CHAIN" if missing_limb else "PROFILE_INCOMPLETE",
            "Missing required roles: " + ", ".join(missing + missing_chains) + ".",
        )

    missing_contacts = [role for role in profile.contact_roles if not _values(mapping, role)]
    if missing_contacts:
        _block(
            blockers,
            "MISSING_CONTACT_ROLE",
            "Missing contact roles: " + ", ".join(missing_contacts) + ".",
        )

    owners: dict[str, list[str]] = {}
    for role in profile.all_roles():
        for name in _values(mapping, role):
            owners.setdefault(name, []).append(role)
    duplicates = {
        name: roles for name, roles in owners.items() if len(roles) > 1
    }
    if duplicates:
        detail = "; ".join(
            f"{name}: {', '.join(roles)}" for name, roles in sorted(duplicates.items())
        )
        _block(blockers, "PROFILE_INCOMPLETE", "Duplicate semantic role ownership: " + detail + ".")

    required_bones = {
        name for role in profile.required_roles for name in _values(mapping, role)
    }
    for role, spec in profile.chains.items():
        if spec.required:
            required_bones.update(_values(mapping, role))
    for name in sorted(required_bones):
        bone = by_name.get(name)
        if bone is None or not bone.valid:
            _block(blockers, "PROFILE_INCOMPLETE", f"Required bone {name!r} is missing or invalid.")
            continue
        if not bone.finite:
            _block(blockers, "PROFILE_INCOMPLETE", f"Required bone {name!r} has a non-finite rest transform.")
        if not isfinite(float(bone.length)) or float(bone.length) <= 1.0e-8:
            _block(blockers, "PROFILE_INCOMPLETE", f"Required bone {name!r} has zero or invalid length.")
        if not bone.use_deform and name != _first(mapping, "ground_root"):
            _block(blockers, "PROFILE_INCOMPLETE", f"Required bone {name!r} is marked non-deforming.")

    if any(not isfinite(float(value)) for value in snapshot.scale):
        _block(blockers, "PROFILE_INCOMPLETE", "Armature scale contains a non-finite value.")
    elif max(snapshot.scale) - min(snapshot.scale) > 1.0e-5:
        _block(blockers, "PROFILE_INCOMPLETE", "Armature object has non-uniform scale.")

    for chain_role, spec in profile.chains.items():
        names = _values(mapping, chain_role)
        if len(names) < 2 or not spec.ordered:
            continue
        for parent, child in zip(names, names[1:]):
            if by_name.get(child) is None or by_name[child].parent != parent:
                _block(blockers, "PROFILE_INCOMPLETE", f"Chain {chain_role!r} is not continuous at {parent!r}/{child!r}.")
                break

    if "ORIENTATION_AMBIGUOUS" in orientation.get("warnings", []):
        _block(blockers, "ORIENTATION_AMBIGUOUS", "Forward/head orientation cannot be established confidently.")
    if "HEAD_TAIL_DIRECTION_REVERSED" in orientation.get("warnings", []):
        _block(blockers, "ORIENTATION_AMBIGUOUS", "Profile forward points toward the tail instead of the head.")

    if profile.creature_class == "QUADRUPED":
        _validate_quadruped(profile, mapping, by_name, orientation, blockers, warnings)

    unique_blockers = []
    seen = set()
    for blocker in blockers:
        key = (blocker["code"], blocker["message"])
        if key not in seen:
            seen.add(key)
            unique_blockers.append(blocker)
    ready_status = "QUADRUPED_READY" if profile.creature_class == "QUADRUPED" else "HUMANOID_READY"
    return {
        "status": ready_status if not unique_blockers else unique_blockers[0]["code"],
        "ready": not unique_blockers,
        "blockers": unique_blockers,
        "warnings": list(dict.fromkeys(warnings)),
        "missingRequirements": missing + missing_chains,
        "worstBlocker": unique_blockers[0]["message"] if unique_blockers else "",
    }


def _validate_quadruped(profile, mapping, by_name, orientation, blockers, warnings):
    limbs = {
        "front_l": ("front_l_scapula", "front_l_upper", "front_l_lower", "front_l_carpus", "front_l_paw"),
        "front_r": ("front_r_scapula", "front_r_upper", "front_r_lower", "front_r_carpus", "front_r_paw"),
        "hind_l": ("hind_l_hip", "hind_l_upper", "hind_l_lower", "hind_l_hock", "hind_l_paw"),
        "hind_r": ("hind_r_hip", "hind_r_upper", "hind_r_lower", "hind_r_hock", "hind_r_paw"),
    }
    complete = 0
    for limb, roles in limbs.items():
        names = [_first(mapping, role) for role in roles]
        if all(names):
            complete += 1
            for parent, child in zip(names, names[1:]):
                if child in by_name and by_name[child].parent != parent:
                    _block(blockers, "MISSING_LIMB_CHAIN", f"{limb} is not a continuous primary limb chain.")
                    break
    if complete != 4:
        _block(blockers, "MISSING_LIMB_CHAIN", f"Expected exactly four complete primary limbs; resolved {complete}.")

    contacts = [_first(mapping, role) for role in profile.contact_roles]
    if all(contacts) and len(set(contacts)) != 4:
        _block(blockers, "MISSING_CONTACT_ROLE", "The four paw/contact endpoints must have unique bone ownership.")

    spine = _values(mapping, "spine_chain")
    neck = _values(mapping, "neck_chain")
    ground = _first(mapping, "ground_root")
    body = _first(mapping, "body_center")
    pelvis = _first(mapping, "pelvis") or _first(mapping, "body_center")
    chest = _first(mapping, "chest")
    head = _first(mapping, "head")
    if ground and body and not (
        by_name[body].parent == ground or _is_ancestor(ground, body, by_name)
    ):
        _block(blockers, "PROFILE_INCOMPLETE", "Body center is not reachable from the ground root.")
    if body and pelvis and body != pelvis and not (
        by_name[pelvis].parent == body or _is_ancestor(body, pelvis, by_name)
    ):
        _block(blockers, "PROFILE_INCOMPLETE", "Pelvis is not reachable from the body center.")
    if spine:
        if pelvis and not (by_name[spine[0]].parent == pelvis or _is_ancestor(pelvis, spine[0], by_name)):
            _block(blockers, "PROFILE_INCOMPLETE", "Spine chain is not reachable from the pelvis/body core.")
        if chest and not (spine[-1] == chest or _is_ancestor(spine[-1], chest, by_name)):
            _block(blockers, "PROFILE_INCOMPLETE", "Chest is not reachable from the ordered spine chain.")
    if neck and chest and not (by_name[neck[0]].parent == chest or _is_ancestor(chest, neck[0], by_name)):
        _block(blockers, "PROFILE_INCOMPLETE", "Neck chain is not reachable from the chest.")
    if head and neck and not (by_name[head].parent == neck[-1] or _is_ancestor(neck[-1], head, by_name)):
        _block(blockers, "PROFILE_INCOMPLETE", "Head is not reachable from the neck/core hierarchy.")

    tail = _values(mapping, "tail_chain")
    if tail and pelvis and not (by_name[tail[0]].parent == pelvis or _is_ancestor(pelvis, tail[0], by_name)):
        _block(blockers, "PROFILE_INCOMPLETE", "Tail chain is not reachable from the pelvis/body hierarchy.")

    forward_axis = str(orientation.get("forwardAxis", profile.forward_axis))
    left_axis = str(orientation.get("leftAxis", ""))
    if left_axis:
        left = axis_vector(left_axis)
        for prefix in ("front", "hind"):
            left_name = _first(mapping, f"{prefix}_l_paw")
            right_name = _first(mapping, f"{prefix}_r_paw")
            if left_name in by_name and right_name in by_name:
                delta = tuple(a - b for a, b in zip(_center(by_name, left_name), _center(by_name, right_name)))
                if _dot(delta, left) <= 1.0e-5:
                    _block(blockers, "PROFILE_INCOMPLETE", f"{prefix} left/right spatial ordering contradicts the orientation contract.")
    forward = axis_vector(forward_axis)
    front_names = [_first(mapping, role) for role in ("front_l_scapula", "front_r_scapula")]
    hind_names = [_first(mapping, role) for role in ("hind_l_hip", "hind_r_hip")]
    if all(name in by_name for name in front_names + hind_names):
        front = sum(_dot(_center(by_name, name), forward) for name in front_names) / 2.0
        hind = sum(_dot(_center(by_name, name), forward) for name in hind_names) / 2.0
        if front <= hind + 1.0e-5:
            _block(blockers, "PROFILE_INCOMPLETE", "Front/hind spatial ordering contradicts profile forward.")

    lengths = [float(by_name[name].length) for name in contacts if name in by_name]
    if lengths and max(lengths) > max(min(lengths), 1.0e-8) * 4.0:
        warnings.append("Paw proportions are unusual; confirm the contact mapping.")


__all__ = ("validate_mapping",)
