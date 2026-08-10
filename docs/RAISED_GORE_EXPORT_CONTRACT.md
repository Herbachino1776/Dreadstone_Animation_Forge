# Gore geometry export contract

Forge 3.20 exports `LEGACY_RAISED`, `CAVITY_INLAY`, and
`HYBRID_ADDITIVE` gore as ordinary glTF mesh nodes for paired, core, and
compound-event regions. `STAIN_ONLY` exports no gore geometry. Source topology
is never cut by gore generation.

## Geometry modes

- `LEGACY_RAISED` owns one raised component per required region role.
- `CAVITY_INLAY` owns one recessed manifold component per required role.
- `HYBRID_ADDITIVE` owns two independent components per role: `RAISED` and
  `INLAY`.
- `STAIN_ONLY` owns no final gore node.

Hybrid amounts are independent. `goreRaisedAmount = 1.0` and
`goreInlayAmount = 1.0` generate full raised geometry plus full inlay geometry;
the values are not normalized against each other.

## Stable node representation

Single-component node names retain the compatibility form:

- `DSB_GORE_ATTACHED_<region>_<deformation>`
- `DSB_GORE_DETACHED_<region>_<deformation>`
- `DSB_GORE_CORE_<region>_<deformation>`

Hybrid nodes append `_RAISED` or `_INLAY`. Unsafe or long names receive a
deterministic hash suffix.

Each final node is Forge-owned, exportable, not preview-only, and inactive in
the undamaged authoring state. glTF extras include stable mesh ID, region,
deformation key, pair role, component, source object/topology, linked
Stamp/capture, component recipe digest, parent hybrid recipe digest,
deformation/generation/geometry digests, geometry mode, material IDs, layer
measurements, triangle count, activation weight, and `defaultVisible = false`.

## Raised component

The raised component is a closed refined shell above the final deformed host
surface. It retains source-position ownership, texture direction, layer,
fiber-atlas, non-emissive Principled material, and armature-copy contracts.
`goreRaisedAmount` scales its thickness without reducing the inlay component.

Recipe v6 adds `goreSurfaceControl`, `goreSurfaceMass`,
`goreNucleusAmount`, and `goreNucleusLobes`. Surface mass changes face
retention and breakup so the shell can become a connected irregular form rather
than a collection of isolated plates. A nonzero nucleus amount adds a
deterministic cluster of closed lobulated submeshes inside the same raised
node. Candidate anchors are ranked by deformation response, limited to the
deepest-response third of the impact, and spread within that zone. The amount
controls both member count and scale; the members vary in aspect, orientation,
and fold structure while remaining partially embedded in the host/inlay
silhouette. Each cluster:

- is deterministic for the recipe and seed;
- inherits each selected surface anchor's source-position and skinning
  ownership;
- uses layer `3` and the `DSB_GORE_CRUSHED_TISSUE` material role;
- contributes to the same per-deformation triangle budget;
- reports `dsb_gore_surface_mass`, `dsb_gore_nucleus_amount`,
  `dsb_gore_nucleus_lobes`, `dsb_gore_nucleus_count`,
  `dsb_gore_nucleus_depth_fraction`, and
  `dsb_gore_nucleus_triangle_count`.

Untouched v1-v5 recipes normalize with surface mass and nucleus disabled, and
their historical digests remain unchanged.

## Inlay component

The inlay component is a closed manifold below the final deformed host surface.
Its boundary remains near the host while liner and enabled internal layers
recess along stored stable source normals. Required ordering is host → rim →
optional clot/tissue/bone → wound bed, with positive separation and bounded
proudness. Skinning uses at most four normalized deform-bone influences.
`goreInlayAmount` scales its cavity depth without reducing the raised component.

## Materials

Inlay may use:

- `DSB_GORE_WET_CRIMSON`
- `DSB_GORE_DARK_CLOT`
- `DSB_GORE_ROUGH_EDGE`
- `DSB_GORE_DEEP_WOUND_BED`
- `DSB_GORE_CRUSHED_TISSUE`
- `DSB_GORE_EXPOSED_BONE`

Raised uses its compatible wet/clot/edge roles and may additionally use
`DSB_GORE_CRUSHED_TISSUE` for solid nuclei. All final materials are
zero-metallic and non-emissive. Wetness changes roughness/coat; redness changes
crimson/tissue intensity and dark-clot bias.

The Blender-only preview material and `DSB_Surface_Gore_Mask` attribute are
still removed before export. Forge converts their authored result into a
portable, lightweight overlay mesh per Damage Key and ownership role. Each
overlay uses standard glTF `COLOR_0` RGBA vertex color, alpha blending, copied
skinning, the matching deformation morph, and a small authored normal offset.
RGB carries the authored wet/dark red response and alpha carries the exact
per-vertex smooth mask already evaluated by Forge.
The original character material and normal map remain on the host mesh.

## Manifest mapping and activation

`deformations.keys[].surfaceGoreOverlay` contains the normalized parent recipe,
both additive amounts, `goreControl`, `goreSurfaceControl`, measurements, and
digest. Geometric keys also contain component-aware node names, mesh IDs,
geometry/generation digests, total/nucleus triangle counts, materials, and
activation contract. Hybrid dictionary keys use `<ROLE>:<COMPONENT>`, for
example `ATTACHED:RAISED`.

Keys that include a surface stain also contain `surfaceStainBindings[]` using
`dreadstone.surface_stain_binding.v1`. Every binding names the exported stain
node, PBR material, matching morph target, source host,
attached/detached/core ownership, `COLOR_0` attribute semantic, activation
weight, hidden-at-Basis contract, depth behavior, and renderer requirements.
`portableArtifactIncluded` reports
whether the GLB contains the actual visual. `runtimeImplementationIncluded`
remains false because Forge does not ship the game-side visibility/morph
controller.

At runtime:

1. Keep all mapped gore nodes inactive while the Damage Key is inactive.
2. Apply the deformation identified by `deformationKey`.
3. At `activationWeight`, activate the node(s) for the current
   attached/detached/core role.
4. For hybrid recipes, activate both mapped components.

Forge records this mapping but does not implement engine-side activation.

For a Progressive Damage Site, raised and inlay remain additive inside one
stage, but complete stage assemblies are mutually exclusive. During an adjacent
structural transition, `MIDPOINT_REPLACE` shows only the lower stage assembly
before the midpoint and only the higher stage assembly at or after it. At
severity zero no stage gore is active. Resident cost still reports every
packaged hidden assembly; visible and transition costs report the one assembly
that can actually be shown.

## Validation and rebuild

Export blocks on missing or duplicate components, wrong deterministic names,
stale topology/capture/deformation/component/parent digests, altered or
non-manifold shell/nucleus geometry, invalid layer ordering, bad skinning, material
violations, excessive depth/proudness, incorrect inactive/preview flags, or
triangle-budget excess.

After writing the GLB, Forge parses its completed JSON chunk and separately
validates surface stains, base host materials, and INLAY/RAISED geometry.
`STAIN_ONLY` or `STAIN_AND_RAISED` cannot pass merely because a Blender preview
material existed: every required node, material, RGBA `COLOR_0` accessor, morph
target, ownership role, and explicit progressive-stage binding must resolve in
the finished GLB.

The same `dreadstone.final_glb_validation.v2` pass also validates the runtime
skeleton/skin graph and exact approved animation inventory. Gore or stain
skinning may reference only joints under `DSB_DAMAGE_RIG`; detached rigid gore
remains unskinned according to its owning segment.

**Rebuild All Generated Gore** recreates only Forge-owned final nodes from the
saved recipe, current capture, and current deformation. It does not alter source
topology, source materials, Damage Key weights, or Source Readiness.
