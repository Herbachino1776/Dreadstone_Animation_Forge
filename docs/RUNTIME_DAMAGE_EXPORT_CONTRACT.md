# Complete Damage runtime export contract

Contract diagnostics: `dreadstone.final_glb_validation.v2`

Complete Damage Asset ships `DSB_DAMAGE_RIG` as the runtime skeleton.
`SBF_ProductionRig` remains source-authoring provenance and is not included in
the runtime GLB. `SBF_CLEAN_CHARACTER`, `DSB_SOURCE_MODEL_PROTECTED`, preview
geometry, readiness helpers, diagnostics, and export staging data are also
authoring-only.

## Runtime object membership

Forge constructs one explicit export graph from the persisted Damage
Authoring state and object role properties. It includes the generated damage
rig; intact body/core and attached skinned segments; supported rigid detached
segments; stump/cap/socket content; committed raised/inlay gore; and temporary
portable surface-stain artifacts. Names assert canonical generated identities,
but a prefix, selection, visibility, or repaired source name never grants
runtime membership.

Every intact runtime mesh and every skinned generated visual must target
`DSB_DAMAGE_RIG`. Detached rigid props remain unskinned. Forge does not add an
Armature modifier to a rigid piece for export convenience. A runtime object
with an authoring-only parent, an unknown role, or a non-runtime Armature
dependency blocks export.

## Runtime animation ownership

Only Actions with explicit approved/non-draft metadata and an approved kind
are candidates. Forge audits Action owner metadata, active/NLA users, bone-only
curves, finite frame bounds, required bones, and compatibility with the
independent damage-rig skeleton. Source and damage Actions are never selected
by numeric filename suffix.

When a kind has an approved `DSB_DAMAGE_RIG` owner, that runtime-owned family
wins and source-owned Actions of the same kind are rejected from shipping. If
no runtime-owned equivalent exists, an approved source Action may be mirrored
only after exact source/damage bone hierarchy and rest-matrix compatibility is
proved. Incompatible or ambiguous candidates fail export.

For export, Forge makes temporary Action copies, records
`DSB_DAMAGE_RIG` as their runtime owner, exposes them through temporary NLA
tracks, and enables Blender 5.1's exact Action filter. `ACTIONS` mode runs with
`export_anim_single_armature = false`, preventing Blender's default
single-armature scan from gathering every bone Action in `bpy.data.actions`.
Each temporary copy is shifted by its authored minimum frame so its runtime
keys span `0..(endFrame - startFrame)`. Key values, interpolation handles,
phase durations, combat IDs, commitment timing, and approval metadata remain
unchanged. The saved approved Action is never shifted.
The source Actions, source rig, damage-rig rest pose, active Action, NLA state,
selection, visibility, and frame state are restored on success and failure.
Temporary Action copies and tracks are removed.

## Sidecar provenance

The JSON sidecar continues to identify the immutable source:

```text
source.object = SBF_CLEAN_CHARACTER
source.armature = SBF_ProductionRig
```

Source object/data IDs, topology and weight fingerprints, readiness revision,
matrix/export scale, virtual-weld data, and anatomy metadata remain unchanged.
The sidecar says where the body came from; the GLB says what the game runs.

## Completed-GLB validation

Forge parses the emitted GLB JSON chunk. `runtimeSkeleton` fails when a source
or protected node is present, `DSB_DAMAGE_RIG` or a required bone is missing,
a skin joint lies outside the damage-rig hierarchy, an intact mesh lacks a
valid skin, a rigid piece has a skin, or multiple generated armature
hierarchies appear. Multiple glTF skin records are allowed only when every
joint set belongs to the same runtime hierarchy.

`runtimeAnimations` requires the exact staged clip inventory. Every clip must
have a non-empty unique name, retained approved kind/runtime-owner extras,
channels targeting only the damage rig or its bones, and finite sampler time
bounds. The minimum sampler time must be zero, the maximum sampler time must
equal `clipDurationSeconds`, and their span must independently equal
`clipDurationSeconds`, within `1e-4` seconds. Offensive clips must additionally
retain contiguous WINDUP → ACTIVE → RECOVERY intervals from zero through the
exported clip end. Missing, duplicate, unexpected, draft, unapproved, or
source-targeted clips fail validation. Diagnostics report each clip, channel
count, declared duration, minimum time, maximum time, duration, rejected source
Action count, and all errors.

Clean reimport remains mandatory. It must produce one armature hierarchy,
`DSB_DAMAGE_RIG`, correct intact skinning, rigid detached props, approved
Actions, morph targets, gore, stains, and materials, with no source-only node.

## Runtime armament capabilities

Complete Damage sidecars may additionally contain versioned
`runtimeAttachmentSockets` and offensive Action metadata. Socket helpers are
excluded from the GLB node and skin-joint inventories; their hand-bone-local
position and quaternion are data for the game-side resolver. Approved attack
clips ship only when their stable combat ID is unique, their declared clip
duration matches the Action and emitted glTF sampler, their WINDUP / ACTIVE /
RECOVERY intervals are finite and contiguous, and every required socket role
exists. See `RUNTIME_ATTACHMENT_AND_OFFENSIVE_CONTRACT.md`.
