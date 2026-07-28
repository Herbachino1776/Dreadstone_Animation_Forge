# Gore geometry export contract

Forge 3.19 exports `LEGACY_RAISED`, `CAVITY_INLAY`, and
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
than a collection of isolated plates. A nonzero nucleus amount may add one
closed lobulated submesh inside the same raised node, anchored to the dominant
captured island and partially embedded in the host/inlay silhouette. It:

- is deterministic for the recipe and seed;
- inherits the dominant island's source-position and skinning ownership;
- uses layer `3` and the `DSB_GORE_CRUSHED_TISSUE` material role;
- contributes to the same per-deformation triangle budget;
- reports `dsb_gore_surface_mass`, `dsb_gore_nucleus_amount`,
  `dsb_gore_nucleus_lobes`, and `dsb_gore_nucleus_triangle_count`.

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
`DSB_GORE_CRUSHED_TISSUE` for a solid nucleus. All final materials are
zero-metallic and non-emissive. Wetness changes roughness/coat; redness changes
crimson/tissue intensity and dark-clot bias. Temporary stain copies and
`DSB_Surface_Gore_Mask` are removed before export.

## Manifest mapping and activation

`deformations.keys[].surfaceGoreOverlay` contains the normalized parent recipe,
both additive amounts, `goreControl`, `goreSurfaceControl`, measurements, and
digest. Geometric keys also contain component-aware node names, mesh IDs,
geometry/generation digests, total/nucleus triangle counts, materials, and
activation contract. Hybrid dictionary keys use `<ROLE>:<COMPONENT>`, for
example `ATTACHED:RAISED`.

At runtime:

1. Keep all mapped gore nodes inactive while the Damage Key is inactive.
2. Apply the deformation identified by `deformationKey`.
3. At `activationWeight`, activate the node(s) for the current
   attached/detached/core role.
4. For hybrid recipes, activate both mapped components.

Forge records this mapping but does not implement engine-side activation.

## Validation and rebuild

Export blocks on missing or duplicate components, wrong deterministic names,
stale topology/capture/deformation/component/parent digests, altered or
non-manifold shell/nucleus geometry, invalid layer ordering, bad skinning, material
violations, excessive depth/proudness, incorrect inactive/preview flags, or
triangle-budget excess.

**Rebuild All Generated Gore** recreates only Forge-owned final nodes from the
saved recipe, current capture, and current deformation. It does not alter source
topology, source materials, Damage Key weights, or Source Readiness.
