# Raised gore export contract

Forge 3.16 exports raised surface gore as ordinary glTF mesh nodes for paired head/forearm regions, core meshes, and compound-event participants. It does not export cavities, exposed anatomy, runtime code, or zero-scale hiding.

## Node representation

Each enabled deformation owns exactly two stable nodes when its registered region has an attached/detached pair:

- `DSB_GORE_ATTACHED_<region>_<deformation>` follows the skinned attached source and copies its vertex groups/Armature modifier.
- `DSB_GORE_DETACHED_<region>_<deformation>` follows the exact-index detached target and retains that object's rigid/skinned role.

Long or unsafe names are normalized and receive a deterministic hash suffix. Every node is Forge-owned, exportable, not preview-only, hidden for the authoring file's undamaged render state, and carries glTF extras for mesh ID, region ID, deformation key, pair role, source object/topology, linked stamp/capture, recipe/input/mesh digests, material IDs/names, triangle count, activation weight, and `defaultVisible = false`.

The mesh contains a closed organic refined shell above the intact fully deformed exterior plus, when enabled, closed inner-reddening prisms just inside each open gore-island edge. Point-domain `DSB_Gore_Source_Vertex` and `DSB_Gore_Source_Position` attributes record source ownership and the interpolated refined surface. Face-domain `DSB_Gore_Texture_Variant` and `DSB_Gore_Layer` attributes record master-seed fiber direction and base/shell/inner-barrier classification. Portable recipes do not contain generated mesh bytes.

## Materials

Every shell has exactly three zero-metallic, non-emissive Principled materials:

- `DSB_GORE_WET_CRIMSON_<recipe>`
- `DSB_GORE_DARK_CLOT_<recipe>`
- `DSB_GORE_ROUGH_EDGE_<recipe>`

The suffix is the stable recipe-digest prefix. Textured recipes add one glTF-safe Image Texture node backed by a packed additive composition of the packaged 2x2 muscle-fiber atlas and the material's procedural gore color. `goreFiberTextureStrength` and `goreBaseColorStrength` contribute independently before clamping. Every refined face gets an independent atlas quadrant chosen by the master gore seed; the source filenames are visual rotations, not anatomical orientation rules. Temporary stain-preview copies and `DSB_Surface_Gore_Mask` are cleared before export.

Viewport presentation state is not export ownership state. Export snapshots the exact morph values, stain links, object visibility, and inspection mode; temporarily zeros managed morphs and forces generated gore to its inactive/default contract; exports; then restores the snapshot in `finally`.

## Manifest mapping

`deformations.keys[].surfaceGoreOverlay` contains the normalized recipe. Raised keys additionally contain `goreGeneratedMeshIds`, `goreGeneratedNodeNames`, `goreGeometryDigests`, `goreGenerationDigests`, `goreTriangleCounts`, `goreMaterialIds`, `goreMaterialNames`, and `goreActivationContract`.

`deformations.generatedGoreMeshes[]` is the flat lookup table for runtime loading. Each record maps one stable mesh/node to its region, deformation key, attached/detached role, source object, materials, triangle count, digests, inactive default, and activation weight.

## Runtime activation

The exported enemy is semantically clean before impact:

1. Keep every gore node inactive while its matching deformation is inactive.
2. Apply or animate the deformation identified by `deformationKey`.
3. Activate the mapped gore node when the deformation reaches `activationWeight` (default `0.01`).
4. Choose the attached or detached node according to the active damage-segment state.
5. Retain the activated node through death and corpse persistence.

Forge records this contract but does not implement Folsom Field/Godot runtime activation. Consumers must not infer activation from Blender visibility alone; use the manifest and node extras.

## Validation and rebuild

Export blocks when an enabled raised recipe has missing/wrong nodes, stale recipe/deformation/capture/topology/pairing digests, altered geometry, missing ownership or refined source positions, invalid source mapping, missing skinning, floating or z-fighting-risk offsets, empty/degenerate/duplicate/non-manifold faces, missing UV/fiber/layer attributes, missing compromised inner barrier, material/image-node violations, incorrect inactive/preview flags, or triangle-budget excess.

**Rebuild All Generated Gore** deletes only Forge-owned shells and recreates them from recipe plus current capture/deformation inputs. It never changes source topology, source materials, shape keys, deformation values, or Source Readiness.
