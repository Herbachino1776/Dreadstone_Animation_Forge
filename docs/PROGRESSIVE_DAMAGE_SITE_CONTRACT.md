# Progressive Damage Site contract

Schema: `dreadstone.progressive_damage_sites.v1`

Forge release: `5.0.0`
Supported production authoring runtime: Blender `5.1.2`

## Product boundary

A Progressive Damage Site organizes three artist-authored Damage Keys:
`LIGHT`, `MEDIUM`, and `HEAVY`. Every key is a complete deformation relative
to Basis and owns its own active Stamp, capture, Impact/Gore macros, seeds,
direction, deformation family, manual settings, final geometry, and generated
raised/inlay components.

Forge never derives one stage from another, scales a stage into another,
requires related seeds, enforces monotonic visual severity, automatically
renames keys, or merges the stages into one additive Stamp stack. The artist
alone decides what Light, Medium, and Heavy look like. An explicit managed-key
rename preserves the stable Damage Key ID and retargets its existing stage;
the rename invalidates validation and disables export until approval is run
again.

Forge owns site organization, stage assignment/focus, safe preview, technical
validation, stable metadata, export, and clean-reimport verification. The
runtime owns hit resolution, energy accumulation, gameplay thresholds,
transitions, death, detachment, and persistence. Forge exports no combat
runtime implementation.

## Persisted site schema

Sites are stored inside the existing deformation registry and exported
manifest, not only in Scene RNA. Existing files migrate additively to an empty
site collection; Forge never infers sites from key names or simultaneous key
previews.

Each site contains:

- `schema`, `version`, stable `siteId`, and opaque `siteGuid`;
- artist-facing `displayName`, registered `regionId`, and
  `structuralGroup`;
- character-local `anchorLocal`, influence `radius`, and normalized
  `preferredDirectionLocal`;
- strictly ordered recommended `severityAnchors`;
- `ADJACENT_CROSSFADE`, `SMOOTHSTEP`, and `MIDPOINT_REPLACE` transition
  contracts;
- explicit draft/readiness/validation/export status;
- stable `LIGHT`, `MEDIUM`, and `HEAVY` stage records.

Each assigned stage record contains a stable `stageId`, stable `damageKeyId`,
artist-owned `deformationKeyName`, `activeStampId`, region/target ownership,
recipe/deformation/capture digests, generated component IDs and node names by
role, attached/detached/core ownership, saved/dirty state, validation
measurements, and triangle counts. Damage Key IDs are additive metadata; names
remain artist-controlled. A key may drive only one site/stage unless the artist
creates a true independent duplicate.

When a stage uses `SURFACE_STAIN` or `STAIN_AND_RAISED`, its record additionally
owns the exact `dreadstone.surface_stain_binding.v1` bindings generated for
that assigned Damage Key. Bindings are resolved by explicit region and stable
stage assignment, never by stage words or Blender object-name ordering.

## Authoring workflow

1. Create a site under **PROGRESSIVE DAMAGE SITES**.
2. Focus **LIGHT**, **MEDIUM**, or **HEAVY**.
3. Assign an existing saved custom Damage Key, create a new key through the
   current atomic selection workflow, or duplicate a key as an independent
   starting point.
4. The selected stage focuses its key and active Stamp in the existing VIP
   macro deck.
5. Author with the existing Impact macros, additive Gore macros, cohesive
   Surface Gore controls, **RANDOMIZE DAMAGE**, **UPDATE GORE PREVIEW**, and
   **SAVE DAMAGE KEY + STAMP + GORE**.
6. Repeat independently for all three stages.
7. Set the site anchor from a captured stage or edit spatial metadata under
   **Advanced Progressive Site Settings**.
8. Preview severity, validate all crossfade states, then explicitly enable the
   site for export.

Randomize dirties only the focused stage. Save updates only that stage's stored
digests/status and marks site validation stale. Neither operation modifies or
reassigns the other two stages.

## Structural crossfade evaluator

Default anchors are Basis `0.00`, Light `0.33`, Medium `0.66`, and Heavy
`1.00`. Custom anchors must remain strictly ordered.

Within one adjacent interval, Forge computes:

```text
t_smooth = t * t * (3 - 2 * t)
```

- Basis→Light: Light rises from zero to one.
- Light→Medium: Light falls while Medium rises.
- Medium→Heavy: Medium falls while Heavy rises.

At severity zero every stage weight is zero. At an exact stage anchor exactly
one stage is fully active. No more than two adjacent stages may be nonzero,
Light and Heavy may never overlap, and total structural stage weight may not
exceed `1.0` within tolerance. Each stage remains an absolute Basis-relative
result; stages are not additive visual layers.

## Detailed-gore replacement

Raised plus inlay remain additive inside one Damage Key. Complete stage
assemblies do not stack or alpha-dissolve through one another.

With `MIDPOINT_REPLACE`, the lower stage's detailed gore is shown before an
adjacent interval midpoint and the higher stage's complete assembly is shown at
or after the midpoint. Basis is the lower side of Basis→Light, so no detailed
stage gore appears before that midpoint. Severity zero always shows none.
Attached, detached, and core roles remain intact inside the selected assembly.

The schema leaves room for a future persistent cross-stage layer, but version 1
defines none.

## Managed preview and restoration

Progression preview uses Forge's existing debounced main-thread preview owner.
It installs no competing timer or handler. The first preview snapshots relevant
shape-key weights, per-key preview state, generated gore visibility, active
key/Stamp, active object, selection, mode, frame, preview generation, managed
preview state, active Actions, and NLA mute/solo/influence state.

**PREVIEW SITE IN ISOLATION** is authoritative for validation.
**PREVIEW WITH OTHER DAMAGE** preserves unrelated preview entries where the
current representation can do so. **REFRESH PROGRESSION PREVIEW** remains
available with live preview enabled. Clearing restores the captured state and
does not save recipes, mark stages dirty, edit Actions, or change bone scale.

## Technical validation

Validation samples `0.00`, `0.25`, `0.50`, `0.75`, and `1.00` within each of
Basis→Light, Light→Medium, and Medium→Heavy. It evaluates actual Blender mesh
geometry in isolation and repeats those 15 points for available rest/current,
walk, hurt, and collapse/death contexts.

The machine-readable report stores weights, selected detailed-gore stage,
maximum displacement, bounds expansion, non-finite count, seam/pair error,
visible triangles, active morph count, total structural weight, and status for
every sample. Blocking checks include:

- missing or non-Basis-relative shape keys;
- wrong region/target or ambiguous assignment;
- unsaved stages or stale recipe/deformation/capture digests;
- failed existing deformation/gore validation;
- missing or invalid generated ownership;
- non-finite coordinates, excessive displacement, or extreme bounds growth;
- paired-region mismatch or unsafe seam error;
- non-adjacent/three-stage activation or total weight above one;
- invalid triangle/morph budgets.

Existing deformation/gore validation remains authoritative for paired sync,
core-single ownership, cavity host/layer relationships, materials, skinning,
inactive defaults, and triangle limits. Artistic non-monotonicity, different
seeds, different captures, and large changes in visual identity are not
blocking.

Validation restores the exact previous Action, NLA state, frame, mode,
selection, active key/Stamp, preview state, and visibility.

## Draft and export states

Incomplete sites may remain in a `.blend`. `EMPTY`, `DRAFT`,
`NEEDS_STAGE_SAVE`, `NEEDS_VALIDATION`, `READY_FOR_PREVIEW`, `FAILED`, and
`READY_FOR_EXPORT` communicate technical state.

A site becomes `READY_FOR_EXPORT` only when all three assignments are saved,
their existing deformation/gore checks pass, crossfade validation passes, and
ownership/export requirements are current. **VALIDATE + ENABLE SITE FOR
EXPORT** is explicit. An invalid enabled site blocks export. A non-enabled draft
is omitted with a warning; ordinary non-progression Damage Keys remain
exportable exactly as before.

Creating, editing, saving, assigning, renaming, or validating a stage turns
the export latch off. This prevents a previously approved site from remaining
enabled after its authored state changes.

Deleting a site deletes metadata only and requires confirmation. It preserves
assigned Damage Keys, Stamps, shape keys, captures, and gore.

## Manifest contract

`deformations.progressiveDamageSites[]` contains only valid, explicitly enabled
sites. Each record exports:

- schema/version, stable site ID/GUID, display name, region/group, local anchor,
  radius, and preferred direction;
- severity anchors, transition mode/curve, gore transition, and stage order;
- stable stage and Damage Key IDs, artist key name, active Stamp, all three
  digests, generated components/nodes by role, explicit attached/detached/core
  mesh mapping, ownership, validation, and cost;
- an activation contract declaring absolute Basis-relative stage results,
  adjacent smoothstep crossfading, at most two simultaneous stage morphs,
  midpoint detailed-gore replacement, inactive defaults, runtime-owned gameplay
  thresholds/energy, and `runtimeImplementationIncluded: false`.
- exact per-stage `surfaceStainBindings`, plus a site-level
  `surfaceStainContract` declaring explicit stage ownership, hidden Basis,
  transition behavior, portable-artifact presence, and truthful
  `runtimeImplementationIncluded: false`.

All pre-3.20 key, Stamp, Blueprint, gore, compound-event, and guard-Action
manifest records remain intact.

## Cost meanings

- Resident stage gore triangles: all packaged stage gore, including hidden
  assemblies.
- Maximum visible stage gore triangles: the largest single role-correct stage
  assembly that can be visible.
- Maximum transition gore triangles: the larger adjacent midpoint-selected
  assembly, not the sum of both stages.
- Managed stage morph targets: logical assigned stage morphs.
- Maximum simultaneous stage morphs: two.
- Hidden generated node count: packaged generated nodes that default inactive.

The asset summary also reports enabled site count and aggregate resident,
visible, transition, morph, and hidden-node costs. Asset-level visible and
transition totals sum the corresponding per-site maxima because independent
sites may be active together. Hidden geometry and morphs are not treated as
free.

## Backward compatibility

Files without Progressive Damage Sites open with an empty version-1 collection.
Forge does not create sites from names containing Light, Medium, or Heavy and
does not reinterpret existing simultaneous previews. Damage Keys, child Stamp
alternatives, Damage Blueprints, hybrid raised/inlay components, and unchanged
digests retain their existing behavior. The new manifest fields are additive.
