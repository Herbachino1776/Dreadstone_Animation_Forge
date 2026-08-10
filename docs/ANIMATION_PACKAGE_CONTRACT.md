# Native Action package contract

Schema: `dreadstone.animation_clip.v1`

`EXPORT SELECTED` writes one native `.blend` Action package and adjacent JSON
manifest. Existing required-bone, parent-chain, rest/proportion warning,
location-channel, ownership, edit, and NLA reconnection behavior is unchanged.

Forge 4.2 records `anatomy` in the Action and manifest. The record
contains anatomy schema/profile, creature and locomotion classes, role mapping
and digest, authoritative orientation, contacts, capabilities, readiness, and
analyzer version. Imports compare known source and target anatomy profiles and
reject an explicit profile mismatch before mutating the target.

Humanoid packages must record `SBF_HUMANOID_YPLUS_V1`, Blender `+Y` forward,
`+Z` up, and top-level `root` motion. Missing, unversioned, and `-Y` humanoid
packages are rejected; Forge neither guesses an orientation nor applies a
legacy yaw correction. Clip identity, keyframes, generator settings, approval
metadata, and exact bone/parent compatibility remain preserved for accepted
packages.

An Idle generated from a captured Draft Base Pose records
`dsb_animation_base_pose_kind=IDLE` and the semantic-role pose recipe in
`dsb_animation_base_pose_json`. The recipe is additive animation-authoring
data, not a replacement for the Skin & Bones rest rig. It excludes the
top-level `root`, carries the exact `SBF_HUMANOID_YPLUS_V1` version, and is
preserved with the Action so later editing or portable clip inspection can
identify the stance underneath the procedural motion.

An exported package never embeds AnyTop files, checkpoints, datasets, Python
environments, or model output provenance. External candidate motion must enter
through a separately reviewed BVH/import process before it becomes a Forge
draft or protected Action.

This portable clip/package contract is distinct from Complete Damage export.
For a Complete Damage GLB, approved clips are ownership-audited and staged only
on `DSB_DAMAGE_RIG`; source-rig Actions cannot enter through Blender's global
Action inventory. See `RUNTIME_DAMAGE_EXPORT_CONTRACT.md`.

An offensive Action additionally carries `dreadstone.offensive_action.v1` in
`dsb_offensive_action_json`. The record preserves its stable combat ID,
attack family, compatible weapon classes, primary/secondary hand roles,
in-place/root-motion policy, commitment point, exact clip duration, and
contiguous WINDUP / ACTIVE / RECOVERY intervals in seconds. Draft or
unapproved metadata may remain in an authoring `.blend`, but it cannot enter an
approved animation pack or Complete Damage runtime export.
