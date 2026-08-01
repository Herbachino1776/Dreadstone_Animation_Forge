"""Validated built-in anatomy profiles and compatibility authorities."""

from __future__ import annotations

from .schema import AnatomyProfile, CapabilitySpec, ChainSpec, ProfileRegistry


HUMANOID_PROFILE_ID = "DSB_HUMANOID_V1"
QUADRUPED_PROFILE_ID = "DSB_QUADRUPED_MAMMAL_DIGITIGRADE_V1"


HUMANOID_ALIASES = {
    "hips": (
        "hips", "pelvis", "hip", "waist", "cog", "center", "rootpelvis",
        "basehip", "ccbasehip", "bip001pelvis", "bip01pelvis", "jpelvis",
    ),
    "spine": (
        "spine", "spine0", "spine1", "spine01", "lowerback", "abdomen",
        "torso", "spinebase", "ccbasewaist", "ccbasespine01",
    ),
    "chest": (
        "chest", "upperchest", "thorax", "ribcage", "spine2", "spine02",
        "spine3", "spine03", "ccbasespine02", "ccbasespine03",
    ),
    "neck": ("neck", "neck1", "neck01", "ccbasenecktwist01"),
    "head": ("head", "ccbasehead"),
    "thigh_l": (
        "leftupleg", "leftupperleg", "leftthigh", "thighl", "upperlegl",
        "lthigh", "thigh_l", "upper_leg_l",
    ),
    "shin_l": (
        "leftleg", "leftlowerleg", "leftshin", "shinl", "lowerlegl",
        "calfl", "lcalf", "shin_l", "lower_leg_l",
    ),
    "foot_l": ("leftfoot", "footl", "lfoot", "foot_l"),
    "thigh_r": (
        "rightupleg", "rightupperleg", "rightthigh", "thighr", "upperlegr",
        "rthigh", "thigh_r", "upper_leg_r",
    ),
    "shin_r": (
        "rightleg", "rightlowerleg", "rightshin", "shinr", "lowerlegr",
        "calfr", "rcalf", "shin_r", "lower_leg_r",
    ),
    "foot_r": ("rightfoot", "footr", "rfoot", "foot_r"),
    "upper_arm_l": (
        "leftarm", "leftupperarm", "upperarml", "lupperarm", "upper_arm_l", "arm_l",
    ),
    "lower_arm_l": (
        "leftforearm", "leftlowerarm", "forearml", "lowerarml", "lforearm",
        "lower_arm_l", "forearm_l",
    ),
    "shoulder_l": ("leftshoulder", "shoulderl", "lshoulder", "shoulder_l", "clavicle_l"),
    "hand_l": ("lefthand", "handl", "lhand", "hand_l", "wrist_l"),
    "upper_arm_r": (
        "rightarm", "rightupperarm", "upperarmr", "rupperarm", "upper_arm_r", "arm_r",
    ),
    "lower_arm_r": (
        "rightforearm", "rightlowerarm", "forearmr", "lowerarmr", "rforearm",
        "lower_arm_r", "forearm_r",
    ),
    "shoulder_r": ("rightshoulder", "shoulderr", "rshoulder", "shoulder_r", "clavicle_r"),
    "hand_r": ("righthand", "handr", "rhand", "hand_r", "wrist_r"),
}


ANIMATE_ANYTHING_PROFILE = {
    "root": "root",
    "hips": "body",
    "spine": "body_top0",
    "spine_mid": "body_top1",
    "chest": "body_top2",
    "neck": "neck",
    "head": "head",
    "shoulder_l": "shoulder_left",
    "upper_arm_l": "arm_left_top",
    "lower_arm_l": "arm_left_bot",
    "hand_l": "arm_left_hand",
    "shoulder_r": "shoulder_right",
    "upper_arm_r": "arm_right_top",
    "lower_arm_r": "arm_right_bot",
    "hand_r": "arm_right_hand",
    "thigh_l": "leg_left_top",
    "shin_l": "leg_left_bot",
    "foot_l": "leg_left_foot",
    "thigh_r": "leg_right_top",
    "shin_r": "leg_right_bot",
    "foot_r": "leg_right_foot",
}


def _cap(supported=True, ready=False, roles=()):
    return CapabilitySpec(bool(supported), bool(ready), tuple(roles))


HUMANOID_PROFILE = AnatomyProfile(
    profile_id=HUMANOID_PROFILE_ID,
    creature_class="HUMANOID",
    locomotion_class="BIPED_PLANTIGRADE",
    forward_axis="-Y",
    up_axis="+Z",
    required_roles=(
        "hips", "thigh_l", "shin_l", "foot_l", "thigh_r", "shin_r", "foot_r",
        "upper_arm_l", "upper_arm_r",
    ),
    optional_roles=(
        "root", "spine", "chest", "neck", "head", "shoulder_l", "lower_arm_l",
        "hand_l", "shoulder_r", "lower_arm_r", "hand_r",
    ),
    chains={
        "spine_chain": ChainSpec(min_count=0, required=False),
        "neck_chain": ChainSpec(min_count=0, required=False),
    },
    bilateral_groups={
        "arms": ("upper_arm_l", "upper_arm_r"),
        "legs": ("thigh_l", "thigh_r"),
        "feet": ("foot_l", "foot_r"),
    },
    symmetry_pairs=(
        ("shoulder_l", "shoulder_r"), ("upper_arm_l", "upper_arm_r"),
        ("lower_arm_l", "lower_arm_r"), ("hand_l", "hand_r"),
        ("thigh_l", "thigh_r"), ("shin_l", "shin_r"), ("foot_l", "foot_r"),
    ),
    contact_roles=("foot_l", "foot_r"),
    aliases=HUMANOID_ALIASES,
    capabilities={
        "idle": _cap(True, False),
        "walk": _cap(True, True, ("hips", "thigh_l", "thigh_r", "foot_l", "foot_r")),
        "collapse": _cap(True, True, ("hips", "spine", "head")),
        "hurt": _cap(True, True, ("hips", "spine", "upper_arm_l", "upper_arm_r")),
        "mace_head_guard": _cap(True, True, ("head", "upper_arm_l", "upper_arm_r")),
        "jaw_motion": _cap(False, False),
        "tail_motion": _cap(False, False),
        "ear_motion": _cap(False, False),
    },
    damage_region_templates=(
        {"regionId": "head", "roleRefs": ["head"]},
        {"regionId": "body_core", "roleRefs": ["hips", "spine", "chest"]},
        {"regionId": "forearm_left", "roleRefs": ["lower_arm_l", "hand_l"]},
        {"regionId": "forearm_right", "roleRefs": ["lower_arm_r", "hand_r"]},
    ),
)


QUADRUPED_ALIASES = {
    "ground_root": ("ground_root", "groundroot", "root", "master", "global"),
    "body_center": ("body_center", "bodycenter", "body", "cog", "center", "torso"),
    "pelvis": ("pelvis", "hips", "hip", "croup"),
    "chest": ("chest", "withers", "thorax", "ribcage", "shouldercenter"),
    "head": ("head", "skull", "cranium"),
    "jaw": ("jaw", "mandible", "lowerjaw"),
    "ear_l": ("ear_l", "leftear", "earleft", "l_ear"),
    "ear_r": ("ear_r", "rightear", "earright", "r_ear"),
    "horn_l": ("horn_l", "lefthorn", "hornleft", "l_horn"),
    "horn_r": ("horn_r", "righthorn", "hornright", "r_horn"),
    "tongue": ("tongue",),
    "front_l_scapula": ("front_l_scapula", "scapula_l", "leftscapula", "frontleftshoulder"),
    "front_l_upper": ("front_l_upper", "frontleftupper", "leftforeupper", "upperforeleg_l"),
    "front_l_lower": ("front_l_lower", "frontleftlower", "leftforelower", "lowerforeleg_l"),
    "front_l_carpus": ("front_l_carpus", "frontleftcarpus", "carpus_l", "wrist_front_l"),
    "front_l_paw": ("front_l_paw", "frontleftpaw", "forepaw_l", "paw_fl", "frontfoot_l"),
    "front_r_scapula": ("front_r_scapula", "scapula_r", "rightscapula", "frontrightshoulder"),
    "front_r_upper": ("front_r_upper", "frontrightupper", "rightforeupper", "upperforeleg_r"),
    "front_r_lower": ("front_r_lower", "frontrightlower", "rightforelower", "lowerforeleg_r"),
    "front_r_carpus": ("front_r_carpus", "frontrightcarpus", "carpus_r", "wrist_front_r"),
    "front_r_paw": ("front_r_paw", "frontrightpaw", "forepaw_r", "paw_fr", "frontfoot_r"),
    "hind_l_hip": ("hind_l_hip", "hindlefthip", "rearhip_l", "haunch_l"),
    "hind_l_upper": ("hind_l_upper", "hindleftupper", "leftrearupper", "upperhindleg_l"),
    "hind_l_lower": ("hind_l_lower", "hindleftlower", "leftrearlower", "lowerhindleg_l"),
    "hind_l_hock": ("hind_l_hock", "hindlefthock", "hock_l", "ankle_hind_l"),
    "hind_l_paw": ("hind_l_paw", "hindleftpaw", "rearpaw_l", "paw_hl", "hindfoot_l"),
    "hind_r_hip": ("hind_r_hip", "hindrighthip", "rearhip_r", "haunch_r"),
    "hind_r_upper": ("hind_r_upper", "hindrightupper", "rightrearupper", "upperhindleg_r"),
    "hind_r_lower": ("hind_r_lower", "hindrightlower", "rightrearlower", "lowerhindleg_r"),
    "hind_r_hock": ("hind_r_hock", "hindrighthock", "hock_r", "ankle_hind_r"),
    "hind_r_paw": ("hind_r_paw", "hindrightpaw", "rearpaw_r", "paw_hr", "hindfoot_r"),
    "spine_chain": ("spine", "back", "vertebra"),
    "neck_chain": ("neck", "cervical"),
    "tail_chain": ("tail", "caudal"),
    "front_l_toe_chain": ("front_l_toe", "foretoe_l", "dewclaw_fl"),
    "front_r_toe_chain": ("front_r_toe", "foretoe_r", "dewclaw_fr"),
    "hind_l_toe_chain": ("hind_l_toe", "hindtoe_l", "dewclaw_hl"),
    "hind_r_toe_chain": ("hind_r_toe", "hindtoe_r", "dewclaw_hr"),
}


QUADRUPED_REQUIRED = (
    "ground_root", "body_center", "pelvis", "chest", "head",
    "front_l_scapula", "front_l_upper", "front_l_lower", "front_l_carpus", "front_l_paw",
    "front_r_scapula", "front_r_upper", "front_r_lower", "front_r_carpus", "front_r_paw",
    "hind_l_hip", "hind_l_upper", "hind_l_lower", "hind_l_hock", "hind_l_paw",
    "hind_r_hip", "hind_r_upper", "hind_r_lower", "hind_r_hock", "hind_r_paw",
)


QUADRUPED_PROFILE = AnatomyProfile(
    profile_id=QUADRUPED_PROFILE_ID,
    creature_class="QUADRUPED",
    locomotion_class="DIGITIGRADE",
    forward_axis="+Y",
    up_axis="+Z",
    required_roles=QUADRUPED_REQUIRED,
    optional_roles=("jaw", "ear_l", "ear_r", "horn_l", "horn_r", "tongue"),
    chains={
        "spine_chain": ChainSpec(min_count=1, required=True),
        "neck_chain": ChainSpec(min_count=1, required=True),
        "tail_chain": ChainSpec(min_count=0, required=False),
        "front_l_toe_chain": ChainSpec(min_count=0, required=False),
        "front_r_toe_chain": ChainSpec(min_count=0, required=False),
        "hind_l_toe_chain": ChainSpec(min_count=0, required=False),
        "hind_r_toe_chain": ChainSpec(min_count=0, required=False),
    },
    bilateral_groups={
        "front_limbs": ("front_l_upper", "front_r_upper"),
        "hind_limbs": ("hind_l_upper", "hind_r_upper"),
        "front_contacts": ("front_l_paw", "front_r_paw"),
        "hind_contacts": ("hind_l_paw", "hind_r_paw"),
    },
    symmetry_pairs=(
        ("front_l_scapula", "front_r_scapula"),
        ("front_l_upper", "front_r_upper"), ("front_l_lower", "front_r_lower"),
        ("front_l_carpus", "front_r_carpus"), ("front_l_paw", "front_r_paw"),
        ("hind_l_hip", "hind_r_hip"), ("hind_l_upper", "hind_r_upper"),
        ("hind_l_lower", "hind_r_lower"), ("hind_l_hock", "hind_r_hock"),
        ("hind_l_paw", "hind_r_paw"), ("ear_l", "ear_r"), ("horn_l", "horn_r"),
    ),
    contact_roles=("front_l_paw", "front_r_paw", "hind_l_paw", "hind_r_paw"),
    aliases=QUADRUPED_ALIASES,
    capabilities={
        name: _cap(True, False)
        for name in (
            "idle", "walk", "trot", "pace", "canter", "gallop", "turn", "bite",
            "paw_attack", "pounce", "quadruped_hurt", "quadruped_collapse",
            "jaw_motion", "tail_motion", "ear_motion",
        )
    },
    damage_region_templates=tuple(
        {"regionId": region_id, "roleRefs": list(roles)}
        for region_id, roles in (
            ("head", ("head",)), ("muzzle", ("head",)), ("jaw", ("jaw",)),
            ("neck", ("neck_chain",)), ("chest", ("chest",)),
            ("abdomen", ("body_center", "pelvis")), ("back", ("spine_chain",)),
            ("shoulder_left", ("front_l_scapula",)), ("shoulder_right", ("front_r_scapula",)),
            ("front_leg_left", ("front_l_upper", "front_l_lower", "front_l_carpus")),
            ("front_leg_right", ("front_r_upper", "front_r_lower", "front_r_carpus")),
            ("front_paw_left", ("front_l_paw",)), ("front_paw_right", ("front_r_paw",)),
            ("hip_left", ("hind_l_hip",)), ("hip_right", ("hind_r_hip",)),
            ("hind_leg_left", ("hind_l_upper", "hind_l_lower", "hind_l_hock")),
            ("hind_leg_right", ("hind_r_upper", "hind_r_lower", "hind_r_hock")),
            ("hind_paw_left", ("hind_l_paw",)), ("hind_paw_right", ("hind_r_paw",)),
            ("tail", ("tail_chain",)),
        )
    ),
)


registry = ProfileRegistry()
registry.register(HUMANOID_PROFILE)
registry.register(QUADRUPED_PROFILE)


def get_builtin_profile(profile_id: str) -> AnatomyProfile:
    return registry.require(profile_id)


def capability_status(
    profile: AnatomyProfile,
    capability: str,
    mapping: dict[str, object] | None = None,
) -> dict[str, object]:
    spec = profile.capabilities.get(str(capability))
    if spec is None:
        return {"supported": False, "productionReady": False, "missingRoles": []}
    mapping = mapping or {}
    missing = [role for role in spec.required_roles if not mapping.get(role)]
    return {
        "supported": bool(spec.supported),
        "productionReady": bool(spec.production_ready and not missing),
        "missingRoles": missing,
    }


__all__ = (
    "ANIMATE_ANYTHING_PROFILE",
    "HUMANOID_ALIASES",
    "HUMANOID_PROFILE",
    "HUMANOID_PROFILE_ID",
    "QUADRUPED_PROFILE",
    "QUADRUPED_PROFILE_ID",
    "capability_status",
    "get_builtin_profile",
    "registry",
)
