# Core and compound trauma export contract

Forge 3.20 supports explicit single-mesh core regions and synchronized compound
trauma events while preserving the paired-segment contract. glTF morph targets
always remain owned by an individual mesh or primitive; Forge never represents
a compound event as one literal cross-object shape key.

## Region modes

Each `registeredRegions[]` entry declares `regionMode`:

- `PAIRED_SEGMENT` owns an attached mesh and its exact-index detached counterpart. A managed deformation name exists on both meshes, and the detached morph receives the attached morph's world-space delta by the same vertex index.
- `CORE_SINGLE` owns one `targetObject`; `detachedObject` is empty. The core morph and optional `CORE` gore node belong only to that mesh.

Both modes export target identity, topology and source-weight fingerprints,
counts, seam association, managed key names, validation state, morph metadata,
ordered Stamp recipes, `activeStampId`, `stampMode`, `previewEnabled`, optional
Blueprint ID/digest, and gore linkage. Missing detached data does not implicitly
change a region to core mode.

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

## Progressive Damage Sites

`deformationAuthoring.progressiveDamageSites[]` is additive to all existing
single-key and compound records. Each enabled site maps stable Damage Key IDs
to explicit `LIGHT`, `MEDIUM`, and `HEAVY` stages without parsing key names.
Every stage remains a complete mesh-local result relative to Basis. Structural
activation is adjacent replacement crossfading, while detailed stage gore uses
midpoint replacement. A Progressive Damage Site does not replace or reinterpret
a compound event, and it does not add runtime hit, energy, death, detachment, or
persistence logic. See `PROGRESSIVE_DAMAGE_SITE_CONTRACT.md`.

## Gore nodes

`generatedGoreMeshes[]` is the flat runtime map. A single-mode recipe produces
one owner for each required `CORE`, `ATTACHED`, or `DETACHED` role. A
`HYBRID_ADDITIVE` recipe produces independent `RAISED` and `INLAY` components
for every required role. Each record exposes `component`,
`parentRecipeDigest`, its component recipe/generation/geometry digests, and the
shared activation mapping. Recipe-v6 raised components may also contain a
cluster of closed lobulated nuclei distributed across the deepest-response
third in the same node; its surface controls, material role, nucleus count, and
nucleus triangle count remain part of that component's recipe and mesh
metadata. Compound participants derive deterministic,
coordinated, non-identical seeds from event seed + region ID + mesh identity.
Every node is ordinary exportable mesh geometry with glTF-safe Principled
materials and is inactive by default.

## Mace head-guard Actions

Approved brace Actions appear in `maceHeadGuardActions[]` and the Approved Animation Pack manifest. Metadata includes action name, guard variant, `Guard_Active` frame/time, presented regions, interruptibility, in-place root-motion policy, and validation state. The Action contains mapped pose-bone rotation/location keys and no bone-scale or shape-key animation. Animation GLB export remains the Approved Animation Pack workflow; the damage manifest carries the cross-domain semantic reference.

## Reimport verification

A clean reimport must contain every declared mesh-local morph, every non-empty generated gore node and its material roles, and the expected inactive/default object state. The separately imported Approved Animation Pack must contain each approved guard Action. Compare imported inventory with both manifests; do not infer success from export completion alone.
