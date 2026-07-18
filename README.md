# Dreadstone Animation Forge

Dreadstone Animation Forge is a proprietary Blender add-on for animation, protected damage-segment and stump authoring, trauma-field deformation authoring, and GLB/manifest export. This repository is the authoritative development source for add-on version **3.10.0**. Blender runtime acceptance targets **Blender 5.1.2**; repository static checks do not execute Blender APIs. The deformation-authoring build is `2026-07-17.trauma-field.1`.

The v3.10.0 update preserves the accepted v3.9.1 workbench and virtual-weld v3.7.4 Damage Readiness handoff. It adds registered deformation regions, connected surface capture, geodesic influence, and deterministic layered trauma recipes without editing imported source mesh or armature data.

Preserved source contracts:

| Component | Version or build |
| --- | --- |
| Add-on | `3.10.0` |
| Damage Readiness revision | `virtual_weld_v3.7.4` |
| Damage Readiness build | `2026-07-15.virtual-weld.1` |
| Damage Authoring build | `2026-07-16.segment-stump-deform.1` |
| Deformation Authoring | `3.10.0` |
| Deformation build | `2026-07-17.trauma-field.1` |

## Install a release

1. Download `Dreadstone_Animation_Forge_v3_10_0.zip` from the GitHub Actions development artifact (or an approved release location when one is published).
2. In Blender 5.1.2, open **Edit > Preferences > Add-ons**.
3. Choose **Install from Disk**, select the ZIP without extracting it, and enable **Dreadstone Animation Forge**.
4. Open the **Dreadstone** panel in the 3D View sidebar.

The release ZIP deliberately contains `README.txt`, `VALIDATION.txt`, and the top-level `dreadstone_animation_forge/` package. Repository tests, scripts, workflows, and other development files are excluded.

## Damage Readiness Analyzer

The analyzer builds shell-aware seam candidates, creates virtual-weld previews, and exports fingerprinted reports. The protected authoring workflow accepts a report only when it has:

- schema `dreadstone.damage_readiness.v1`;
- analyzer revision `virtual_weld_v3.7.4`;
- overall readiness `READY`;
- `AUTOMATIC_CANDIDATE` status for all required seams;
- matching source-topology and relevant vertex-group SHA-256 fingerprints.

The four required seams are **Head–Neck**, **Left Elbow**, **Right Elbow**, and **Lower Spine**. Readiness analysis and preview behavior, Safe Resize to the canonical 1.500 m height, imported animation-pack adoption, preview floor and grounding, Animate Anything/Testman rig mapping, walk/collapse/flank-hurt draft generation, action approval and cleanup, and approved animation-pack GLB export remain available. Never apply the safe outer wrapper scale.

Report path handling is intentionally strict. There is no C-drive or drive-root fallback. An unsaved Blend file requires an explicit report folder, and a `//` relative report folder requires a saved Blend file.

## Protected Damage Segment & Stump Authoring

The authoring workflow materializes the approved interpolated contours on copied mesh data. Polygons crossed by a seam are clipped at the exact proximal/distal weight zero crossing; new boundary vertices interpolate source positions, normals, UVs, and skin weights. Polygons away from the contour are classified by distal bone-subtree weight versus proximal seam-bone weight, after which the connected distal region is retained.

Raw GLB UV, normal, tangent, and material splits remain physically separate. No global Merge by Distance is performed, and the imported source mesh is never cut or edited. Original meshes, weights, materials, UVs, armature data, actions, and modifiers remain unchanged. The source objects are hidden during authoring and can be restored by clearing or rebuilding the generated asset.

Generated intact assets:

- `DSB_BODY_CORE`
- `DSB_ATTACHED_HEAD`
- `DSB_ATTACHED_FOREARM_L`
- `DSB_ATTACHED_FOREARM_R`

Generated detached assets:

- `DSB_SEGMENT_HEAD`
- `DSB_SEGMENT_FOREARM_L`
- `DSB_SEGMENT_FOREARM_R`
- `DSB_SEGMENT_UPPER_BODY`
- `DSB_SEGMENT_LOWER_BODY`

Generated stump assets:

- `DSB_STUMP_NECK_TORSO`
- `DSB_STUMP_NECK_HEAD`
- `DSB_STUMP_ELBOW_L_UPPER`
- `DSB_STUMP_ELBOW_L_LOWER`
- `DSB_STUMP_ELBOW_R_UPPER`
- `DSB_STUMP_ELBOW_R_LOWER`
- `DSB_STUMP_WAIST_LOWER`
- `DSB_STUMP_WAIST_UPPER`

The build also creates `DSB_DAMAGE_RIG`, a protected `DSB_SOURCE_MODEL_PROTECTED`, isolated `DSB_DAMAGE_AUTHORING` collections, and the `DSB_SOCKET_ABDOMEN_VISCERA` helper. Each approved contour creates two independent caps with opposite outward normals and `DSB_INTERIOR_WOUND_MAT`. Head and elbow proximal caps use averaged source seam weights on `DSB_DAMAGE_RIG`; detached-side caps are rigid and parented to their props; waist caps are rigid and parented to upper/lower body props. Caps are hidden in intact preview mode.

### Preview and validation

**Preview Intact** shows the body core and attached head and forearms while hiding detached props, caps, and protected source. **Preview Detached** presents the anatomically appropriate pieces and paired caps for Head–Neck, either elbow, or Lower Spine; the Lower Spine preview also includes the abdomen viscera socket.

**Validate Complete Damage Asset** verifies source fingerprints, all required objects, exact one-time partition coverage, no partition overlap, cap geometry and topology, rig targets, seam-family tolerance (default 0.0005 m), closed degree-2 contour cycles, generated boundaries, wound material assignment, and cleanup/restoration after failed builds.

### Damage export and clean reimport

**Export Damage GLB + Manifest** writes `<name>.glb`, `<name>.json`, and `<name>_validation.json`. The manifest uses schema `dreadstone.damage_authoring.v1` and includes source fingerprints, readiness revision/build, virtual-weld tolerance, analyzer contour indices, materialized polygon/boundary contracts, ordered virtual loops and vertex families, generated names, stump material, collider/mass hints, fatal-detachment flags, the abdomen socket, deformation metadata, and validation results.

Damage export follows the same path-safety policy as readiness reports: unsaved files need an explicit project folder, saved files may use adjacent `//damage_exports/`, and drive roots are rejected.

A clean GLB import does not automatically interpret Forge `dsb_default_visible` metadata, and Blender may have Mesh object-type visibility disabled while Empty objects remain visible. If only a small orange sphere (`DSB_SOCKET_ABDOMEN_VISCERA`) appears, run **Restore Reimported GLB Intact Preview**. It enables Mesh visibility in open 3D Views, restores textured display and framing, shows the intact body pieces, and hides detached pieces, caps, and the socket. It does not require the original authoring-state text.

## Trauma Field Authoring v3.10.0

Trauma Field Authoring operates on an explicit registry of exact-topology attached/detached mesh pairs. Each semantic region, such as `head` or `forearm_left`, records its object names, topology fingerprint, vertex and polygon counts, optional seam, managed keys, and validation state. Artists register the two selected meshes, validate the pair, choose the active region, and then perform all capture, preview, rebuild, sculpt, and synchronization work through that region. Arbitrary objects are never silently adopted.

An accepted v3.9.1 file with `DSB_ATTACHED_HEAD` and `DSB_SEGMENT_HEAD` but no registry is migrated additively to region `head` when its topology contract is valid. Existing geometry and the legacy keys `Head_Dent_Left`, `Head_Dent_Right`, `Head_Cave_Front`, and `Jaw_Displaced` are preserved. Legacy keys are marked as manual/non-procedural; Forge does not guess recipes from sculpted coordinates or overwrite them. **Create Standard Head Set**, sculpt/sync, mirror, and attached/detached/both preview controls remain available.

### Capture, masks, and surface distance

The active attached mesh supports four placement modes:

- **Single Face** captures exactly one face.
- **Selected Face Patch** captures one connected face component, its face and vertex indices, area-weighted center/normal, world bounds, radius, selection hash, and topology fingerprint. Disconnected islands fail with an actionable recapture message.
- **Selected Vertices** captures one or more vertices, their average center, adjacent-face normal, radius, hash, and topology fingerprint.
- **Cursor** preserves the diagnostic cursor-centered workflow.

Captures are rejected when their region, object, topology, indices, or selection contract is stale. **Surface Distance** is the production default: weighted mesh-edge adjacency uses world-space edge lengths and radius-limited Dijkstra traversal from the captured seed vertices. Cached traversal is keyed by topology, object, selection, mode, and range. **World Distance** remains available for compatibility and diagnosis.

Influence masks are **Patch Only** (captured vertices only), **Patch Feathered** (full patch plus a controlled geodesic margin, the multi-selection default), and **Connected Surface** (spread through the reachable surface within the configured radius).

### Layered trauma stamps and deterministic rebuild

A managed key may carry an ordered stamp stack. Every stamp has a stable ID, name, enable state, family, placement/capture data, center and direction, radius, depth, falloff, influence and distance modes, feather distance, seam protection, strength, maximum displacement, and explicit order. Artists can add, duplicate, delete, reorder, enable/disable, select, edit, and preview stamps. Duplicating creates a new ID; reordering preserves IDs.

The six v3.10.0 families are exactly:

- **Compact Dent** — localized inward depression.
- **Broad Cave** — wide, soft inward collapse.
- **Flat Compression** — moves the patch toward an impact plane rather than translating it uniformly.
- **Directional Shear** — controlled lateral movement.
- **Raised Impact Rim** — restrained raised lip designed for layering.
- **Ridge Collapse** — directed inward collapse of a protruding or curved ridge.

**Preview Active Stamp** writes only the temporary `__DSB_DEFORMATION_SEED_PREVIEW` key. **Rebuild Active Deformation** always starts from attached Basis, evaluates enabled stamps in explicit order in world units, clamps displacement, writes the permanent attached key, converts the same-index attached local deltas through world space into detached local deltas, validates the pair, updates additive metadata, clears temporary preview data, and solos the rebuilt key. Identical Basis and recipes therefore rebuild without accumulated drift.

**Validate Morph Targets** checks the region registry, exact topology and index safety, captures and stamp recipes, finite values and directions, displacement limits, preview cleanup, and paired world-space delta equality. Damage export synchronizes every registered region, enables glTF morph targets and morph normals, and extends schema `dreadstone.damage_deformation.v1` with compact region and ordered recipe metadata. It does not use nearest-neighbor transfer, KD-tree pair matching, topology repair, or destructive source edits.

### Runtime acceptance and scope

The primary Blender 5.1.2 acceptance uses the accepted Testman Damage Asset: verify legacy migration, capture a connected left-temple patch, layer Broad Cave, Compact Dent, Raised Impact Rim, and slight Directional Shear into `Head_Impact_Left_v001`, rebuild after editing one stamp, inspect attached and detached views, validate, export, clean-reimport, and confirm morph names and behavior. A secondary smoke test registers `DSB_ATTACHED_FOREARM_L` with `DSB_SEGMENT_FOREARM_L` as `forearm_left`, captures a connected patch, rebuilds one Flat Compression stamp, and validates paired synchronization. The exact numbered procedure is in `docs/DEVELOPMENT.md`.

Version 3.10.0 intentionally does not include gore reveal, gore/slice decals, tissue exposure, puncture stamps, reveal masks, seam variants, arbitrary runtime cutting, creature-profile automation, topology-family generation, armor authoring, or game-runtime integration/morph blending.

## Typical protected-authoring workflow

1. Save the Blend file in the damage-authoring project folder.
2. Select the original Testman mesh or armature.
3. Open **Dreadstone > Damage Segment & Stump Authoring v3.9.1**.
4. Select the `rig_damage_readiness` JSON produced by v3.7.4.
5. Choose **Load READY Handoff**, then **Build Authoring Asset**.
6. Inspect intact preview with representative approved animations.
7. Inspect Head–Neck detached first, then both elbows and Lower Spine.
8. Run **Validate Complete Damage Asset**.
9. Choose a project-safe Damage Export folder.
10. Run **Export Damage GLB + Manifest**.

## Repository validation and release build

Repository tooling uses only the Python standard library and never imports Blender's `bpy` module:

```text
python scripts/validate_addon.py
python -m unittest discover -s tests -p "test_*.py"
python scripts/build_release.py
```

The build writes `dist/Dreadstone_Animation_Forge_v3_10_0.zip`. It validates first, fixes archive ordering and timestamps, checks the exact installable layout (including `trauma_field.py`), and tests ZIP integrity. Repeated builds from identical source are byte-for-byte deterministic.

Static CI confirms syntax and source contracts; it does **not** replace runtime acceptance in Blender 5.1.2. Repository developers must complete the exact acceptance procedure in `docs/DEVELOPMENT.md` before publishing a release.

## License

Copyright Herbachino1776. All rights reserved. See [LICENSE](LICENSE).
