# Creature Anatomy Profile contract

Contract schema: `dreadstone.creature_anatomy_profile.v1`

Forge 4.2 separates creature anatomy from a concrete rig. An **anatomy
profile** defines semantic roles, variable-length chains, bilateral groups,
symmetry, contacts, orientation, damage-region templates, aliases, and feature
capabilities. A **rig profile** defines one exact production skeleton: canonical
names, hierarchy, rest matrices, local axes and rolls, fingerprint, and
compatible Actions. This release adds anatomy profiles; it does not freeze a
quadruped rig profile.

## Built-in profiles

- `DSB_HUMANOID_V1` consumes the exact Skin & Bones Forge 2.1.0 production rig
  `SBF_HUMANOID_YPLUS_V1`: 21 deform bones, `+Y` forward, `+Z` up, and
  top-level `root` motion. Humanoid generators do not accept unversioned or
  `-Y` rigs.
- `DSB_QUADRUPED_MAMMAL_DIGITIGRADE_V1` describes dog-, wolf-, hyena-, big-cat-,
  and demon-hound-like digitigrade mammals. It has separate front-left,
  front-right, hind-left, and hind-right limb families and four unique paw
  contacts. Spine, neck, tail, and toe/dewclaw chains may vary in length.

The quadruped profile is not universal. Plantigrades, ungulates, reptiles,
birds, insects, and arbitrary limb counts need later profiles. The synthetic
test armature verifies the contract only and is not a canonical production rig.

## Detection and override

`AUTO` deterministically scores registered profiles from aliases, hierarchy,
chain completeness, bilateral structure, rest orientation, contacts, and
front/hind placement. Weak or close scores return `UNSUPPORTED_ANATOMY` or
`PROFILE_AMBIGUOUS`; Forge does not silently pick a quadruped. The artist may
select Humanoid, Quadruped Digitigrade, or Custom/Unresolved. An override selects
the validator and never waives missing roles, contradictory topology, invalid
transforms, scale, or orientation.

Readiness values include `HUMANOID_READY`, `QUADRUPED_READY`,
`PROFILE_AMBIGUOUS`, `PROFILE_INCOMPLETE`, `ORIENTATION_AMBIGUOUS`,
`MISSING_LIMB_CHAIN`, `MISSING_CONTACT_ROLE`, and `UNSUPPORTED_ANATOMY`.

## Authoritative orientation

Analysis stores character-local signed forward, up, and left axes, the measured
head-facing direction, ground-root and body-center roles, the root-motion
carrier, and contact roles. Axes must be orthogonal and the head must lie in the
declared forward direction relative to the body. Humanoid generators use the
Skin & Bones contract as the authority and produce only `+Y/+Z` motion.
Downstream systems must consume this record instead of independently inferring
forward or applying a 180° yaw correction.

## Mapping, validation, and capabilities

Role resolution normalizes aliases, produces one stable role-to-bone map, and
hashes canonical JSON into `mappingDigest`. Quadruped validation requires four
complete, unique limbs; four distinct contact endpoints; continuous core,
spine, and neck topology; reachable head and optional tail; finite nonzero rest
bones; uniform armature scale; valid left/right and front/hind ordering; and no
duplicate ownership. Unusual proportions may warn but do not fail by
themselves.

Capabilities separate `supported` from `productionReady`. The quadruped schema
declares future idle, gait, turn, attack, reaction, jaw, tail, and ear concepts,
but none are production-ready in 4.2. Humanoid Idle, Walk, Collapse, Hurt, and
Mace Guard require the Skin & Bones canonical rig. Forge reports a capability error instead of
generating motion for an incompatible anatomy. No unfinished quadruped
generator is exposed.

Damage-region templates are diagnostic preparation only. The quadruped profile
resolves head, muzzle, jaw, neck, chest, abdomen, back, bilateral shoulder/front
leg/front paw/hip/hind leg/hind paw, and tail templates. Forge 4.1 does not
automatically build those regions and does not weaken Source Readiness.

## Persistence and compatibility

The owned armature stores `dsb_creature_anatomy_json`, its schema/profile ID,
and readiness summary. The JSON record includes class, locomotion, rig profile
when known, mapping and digest, orientation, contacts, capabilities,
requirements, diagnostics, and analyzer version. It is restored after save and
reopen.

Action-package and damage-manifest schemas receive an additive `anatomy`
object. A humanoid Action package must identify `SBF_HUMANOID_YPLUS_V1` and
`+Y`; missing, unversioned, or `-Y` humanoid metadata is an import failure.
Animation Forge does not import, duplicate, or own the canonical rig asset.

Profile payload migration accepts the internal pre-v1 shape and revalidates it
as v1. Metadata migration accepts the previous rig-analysis record without
discarding its role mapping or facing result.

## External motion boundary

AnyTop is a research reference, not a Forge dependency. A future bridge must be
external: candidate generator -> BVH/measurement corpus -> external analysis ->
isolated Blender import -> anatomy-profile retargeting -> Forge draft -> Forge
validation -> artist approval -> protected production Action. Forge installs
and operates without AnyTop, PyTorch, CUDA, Conda, checkpoints, or datasets.
See [the feasibility audit](research/ANYTOP_FEASIBILITY_AUDIT.md) and
[measurement plan](research/QUADRUPED_MOTION_REFERENCE_PLAN.md).
