# Native Action package contract

Schema: `dreadstone.animation_clip.v1`

`EXPORT SELECTED` writes one native `.blend` Action package and adjacent JSON
manifest. Existing required-bone, parent-chain, rest/proportion warning,
location-channel, ownership, edit, and NLA reconnection behavior is unchanged.

Forge 4.1 additively records `anatomy` in the Action and manifest. The record
contains anatomy schema/profile, creature and locomotion classes, role mapping
and digest, authoritative orientation, contacts, capabilities, readiness, and
analyzer version. Imports compare known source and target anatomy profiles and
reject an explicit profile mismatch before mutating the target.

Packages made before anatomy metadata remain compatible. Forge infers the
existing humanoid route, sets `anatomyLegacy: true`, and emits a warning; missing
metadata is not itself an import error. Clip identity, keyframes, generator
settings, approval metadata, and compatibility rules are otherwise preserved.

An exported package never embeds AnyTop files, checkpoints, datasets, Python
environments, or model output provenance. External candidate motion must enter
through a separately reviewed BVH/import process before it becomes a Forge
draft or protected Action.
