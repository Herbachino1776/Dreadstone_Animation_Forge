# Dreadstone Animation Forge

Dreadstone Animation Forge is a proprietary Blender add-on for animation, protected damage-segment and stump authoring, deformation shape-key authoring, and GLB/manifest export. This repository is the authoritative development source for add-on version **3.9.1**, accepted against **Blender 5.1.2**. The deformation workbench build is `2026-07-16.deformation-workbench.2`.

The v3.9.1 release preserves the accepted v3.8.1 workflow and the virtual-weld v3.7.4 Damage Readiness handoff. It adds a scale-safe deformation workbench without editing imported source mesh or armature data.

Preserved source contracts:

| Component | Version or build |
| --- | --- |
| Add-on | `3.9.1` |
| Damage Readiness revision | `virtual_weld_v3.7.4` |
| Damage Readiness build | `2026-07-15.virtual-weld.1` |
| Damage Authoring build | `2026-07-16.segment-stump-deform.1` |
| Deformation Authoring | `3.9.1` |
| Deformation build | `2026-07-16.deformation-workbench.2` |

## Install a release

1. Download `Dreadstone_Animation_Forge_v3_9_1.zip` from the repository release.
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

## Damage Deformation Authoring

The v3.9.1 workbench operates only on the generated Damage Asset and currently manages the paired head objects `DSB_ATTACHED_HEAD` and `DSB_SEGMENT_HEAD`. It verifies exact topology and vertex ordering, transfers deltas by vertex index, and performs no nearest-neighbor pair transfer.

**Create Standard Head Set** creates four paired keys at zero weight:

- `Head_Dent_Left`
- `Head_Dent_Right`
- `Head_Cave_Front`
- `Jaw_Displaced`

Each permanent key has an independent preview slider. The detached key is driver-linked to the matching attached key, and active-key selection automatically solos the preview. Attached, detached, and both/overlay viewing controls are available.

### Procedural presets and optional sculpting

Seed radius, depth, falloff exponent, direction/captured surface normal, seam protection, maximum displacement, and maximum runtime weight are editable. Radius, depth, paired deltas, and maximum-displacement validation are evaluated in world space, so differing object transforms and scales are handled correctly.

Capture the center from exactly one selected face or from the 3D cursor. Live preview refreshes the temporary `__DSB_DEFORMATION_SEED_PREVIEW` key. **BUILD ACTIVE PRESET** produces a usable localized dent, broad cave, or directional displacement; localized dents include a subtle raised rim. **Commit Seed to Active Key** copies the result into the permanent key and removes the temporary preview.

Sculpting is optional. For an artist-finished result, create or select a key, capture and tune the seed, commit it, choose **Begin Sculpt**, refine `DSB_ATTACHED_HEAD`, and choose **Finish Sculpt & Sync**. Forge exits Sculpt Mode, copies exact-index world-space deltas to `DSB_SEGMENT_HEAD`, and validates limits. **Create Mirrored Shape Key** uses Blender topology mirror across local X and then synchronizes the pair.

**Validate Morph Targets** checks paired vertex/polygon counts, topology fingerprints and vertex order, world-space per-index deltas, finite coordinates, managed-key presence, and maximum displacement. Damage GLB export removes the temporary preview, synchronizes all managed keys, validates the pair, enables glTF morph targets and morph normals, and writes schema `dreadstone.damage_deformation.v1` metadata under `deformations`.

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

The build writes `dist/Dreadstone_Animation_Forge_v3_9_1.zip`. It validates first, fixes archive ordering and timestamps, checks the exact installable layout, and tests ZIP integrity. Repeated builds from identical source are byte-for-byte deterministic.

Static CI confirms syntax and source contracts; it does **not** replace runtime acceptance in Blender 5.1.2. Repository developers must complete the exact acceptance procedure in `docs/DEVELOPMENT.md` before publishing a release.

## License

Copyright Herbachino1776. All rights reserved. See [LICENSE](LICENSE).
