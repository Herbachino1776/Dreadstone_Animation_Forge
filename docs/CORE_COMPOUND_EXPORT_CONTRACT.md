# Core and compound trauma export contract

Forge 3.14 adds explicit single-mesh core regions and synchronized compound trauma events while preserving the existing paired-segment contract. glTF morph targets always remain owned by an individual mesh or primitive; Forge never represents a compound event as one literal cross-object shape key.

## Region modes

Each `registeredRegions[]` entry declares `regionMode`:

- `PAIRED_SEGMENT` owns an attached mesh and its exact-index detached counterpart. A managed deformation name exists on both meshes, and the detached morph receives the attached morph's world-space delta by the same vertex index.
- `CORE_SINGLE` owns one `targetObject`; `detachedObject` is empty. The core morph and optional `CORE` gore node belong only to that mesh.

Both modes export target identity, topology and source-weight fingerprints, counts, seam association, managed key names, validation state, morph metadata, ordered stamp recipes, and gore linkage. Missing detached data does not implicitly change a region to core mode.

## Compound event mapping

`deformationAuthoring.compoundTraumaEvents[]` describes one semantic event that activates multiple mesh-local targets. Each event exports:

- stable `eventId`, display name, trauma family, semantic impact direction, optional severity, event seed, and recipe digest;
- the normalized shared `worldField`, including world origin/direction/normal, radius, depth, falloff, strength, displacement limit, and participant intersection records;
- participant region and mesh identities;
- `morphTargets[]`, with mesh name, child morph name, region ID, and `CORE`, `ATTACHED`, or `DETACHED` role;
- all separately owned `goreNodes[]`;
- linked seam IDs and measured continuity records;
- synchronized activation weight/rule and inactive default.

The undamaged state is `ALL_CHILD_MORPHS_ZERO_AND_GORE_INACTIVE`. A runtime selects the semantic event, sets all listed child morph weights together, and activates all listed gore nodes together. Forge exports the data contract, not game logic.

## Seam continuity

For a linked generated seam, Forge evaluates the same world-space field against each participant and maps boundary vertices to the protected Source Readiness contour. `LOCK_BOUNDARY_TO_SHARED_FIELD` assigns an identical compatible boundary displacement. `BLEND_ACROSS_SEAM` additionally feathers that motion into adjacent interior rings. `PROTECT_SEAM` assigns zero displacement to mapped boundaries. Records include mapped count, maximum mismatch before/after resolution, tolerance, feathered interior count, and `topologyMutated: false`.

Forge does not weld, merge, add, or delete source/generated vertices. Source Damage Readiness rules and `NOT READY` repair behavior are unchanged.

## Gore nodes

`generatedGoreMeshes[]` is the flat runtime map. Core keys produce one `CORE` owner; paired keys produce `ATTACHED` and `DETACHED` owners. Compound participants share the event's gore family but derive deterministic, coordinated, non-identical seeds from event seed + region ID + mesh identity. Every node is ordinary exportable mesh geometry using the three glTF-safe Principled gore materials and is inactive by default.

## Mace head-guard Actions

Approved brace Actions appear in `maceHeadGuardActions[]` and the Approved Animation Pack manifest. Metadata includes action name, guard variant, `Guard_Active` frame/time, presented regions, interruptibility, in-place root-motion policy, and validation state. The Action contains mapped pose-bone rotation/location keys and no bone-scale or shape-key animation. Animation GLB export remains the Approved Animation Pack workflow; the damage manifest carries the cross-domain semantic reference.

## Reimport verification

A clean reimport must contain every declared mesh-local morph, every non-empty generated gore node and its material roles, and the expected inactive/default object state. The separately imported Approved Animation Pack must contain each approved guard Action. Compare imported inventory with both manifests; do not infer success from export completion alone.
