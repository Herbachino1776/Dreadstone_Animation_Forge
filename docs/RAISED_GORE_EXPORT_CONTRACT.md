# Gore geometry export contract

Forge 3.18 exports `CAVITY_INLAY` and `LEGACY_RAISED` gore as ordinary glTF mesh nodes for paired head/forearm regions, core meshes, and compound-event participants. `STAIN_ONLY` exports no gore geometry. Forge does not cut source topology, export runtime code, or use zero-scale hiding.

## Node representation

Each enabled geometric recipe owns one stable node per region role:

- `DSB_GORE_ATTACHED_<region>_<deformation>` follows the skinned attached source and copies normalized deform-bone weights plus its Armature modifier.
- `DSB_GORE_DETACHED_<region>_<deformation>` follows the exact-index detached target and retains that object's rigid/skinned role.
- A core region owns one corresponding core node.

Long or unsafe names receive a deterministic hash suffix. Every final node is Forge-owned, exportable, not preview-only, hidden for the authoring file's undamaged render state, and carries glTF extras for mesh ID, region, key, pair role, source topology, linked stamp/capture, recipe/control/geometry digests, geometry mode, identity, materials, layer measurements, triangle count, activation weight, and `defaultVisible = false`.

`CAVITY_INLAY` is a closed manifold inlay below the final deformed host surface. Its boundary remains near the host while the liner and optional internal layers recess inward along stored stable source normals. It records point-domain source position, source world normal, source vertex/blend ownership, inward depth, and layer/variant attributes. Required ordering is host → rim → optional clot/tissue/bone → wound bed, with positive z-fighting separation and bounded proudness. Vertex skinning uses at most four normalized deform-bone influences.

`LEGACY_RAISED` retains the closed refined shell and optional inner-reddening barrier from Forge 3.13–3.17. Its original source-position, texture-variant, layer, fiber-atlas, and three-material contracts remain valid. Portable recipes contain recipes and analytical anchors, never generated mesh bytes.

BALANCED and FINAL previews may create temporary owned nodes, but preview-only nodes are excluded from final lookup and manifests and are deleted by clear, commit cleanup, file-load cleanup, and startup self-check.

## Materials

Cavity/inlay nodes use six zero-metallic, non-emissive Principled roles:

- `DSB_GORE_DEEP_WOUND_BED`
- `DSB_GORE_CRUSHED_TISSUE`
- `DSB_GORE_EXPOSED_BONE`
- the retained wet crimson, dark clot, and rough edge roles

Not every identity must use every optional layer, but its enabled layers and material slots must match its normalized recipe. Wetness affects roughness/coat only. Exposed bone remains a material/geometry layer, not a claim of inferred anatomy. Legacy-raised nodes retain their exact three-material family and optional packed fiber-atlas texture. Temporary stain copies and `DSB_Surface_Gore_Mask` are cleared before export.

## Manifest mapping

`deformations.keys[].surfaceGoreOverlay` contains the normalized recipe, geometry mode, identity, `goreControl`, measurements, and deterministic digest. Geometric keys also contain `goreGeneratedMeshIds`, `goreGeneratedNodeNames`, `goreGeometryDigests`, `goreGenerationDigests`, `goreTriangleCounts`, `goreMaterialIds`, `goreMaterialNames`, and `goreActivationContract`.

`deformations.generatedGoreMeshes[]` maps each final mesh/node to its region, key, attached/detached/core role, source object, geometry mode, identity, materials, layer metrics, triangle count, digests, inactive default, and activation weight. Preview-only nodes are forbidden.

## Runtime activation

The exported enemy is semantically clean before impact:

1. Keep every gore node inactive while its matching deformation is inactive.
2. Apply or animate the deformation identified by `deformationKey`.
3. Activate the mapped gore node at `activationWeight` (default `0.01`).
4. Choose attached/detached according to damage-segment state, or the sole core node for `CORE_SINGLE`.
5. Retain the activated node through death and corpse persistence.

Forge records this contract but does not implement Folsom Field/Godot runtime activation. Consumers must use manifest/extras instead of inferring activation from Blender visibility.

## Validation and rebuild

Export blocks when an enabled geometric recipe has missing/wrong nodes, stale recipe/control/deformation/capture/topology/pairing digests, altered geometry, missing ownership/source data, invalid or non-deform skinning, excessive proudness, z-fighting separation, invalid layer ordering, over-depth geometry, empty/degenerate/duplicate/non-manifold faces, material violations, wrong inactive/preview flags, or triangle-budget excess.

**Rebuild All Generated Gore** deletes only Forge-owned final nodes and recreates them from the recipe plus current capture/deformation inputs. It never changes source topology, source materials, shape keys, deformation values, or Source Readiness. Legacy recipes rebuild in their recorded compatibility mode; they are never silently converted to cavities.
