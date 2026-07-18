# Development

## Tooling requirements

Repository tools require Python 3.10 or newer and use only the standard library. No `pip install` step is required for static validation, unit tests, or release packaging.

Blender's `bpy`, `bmesh`, and `mathutils` modules are available only inside Blender. The repository tools intentionally inspect and compile source without importing the add-on; they do not fake a Blender environment.

## Static checks

From the repository root, run:

```text
python scripts/validate_addon.py
python -m unittest discover -s tests -p "test_*.py"
python scripts/build_release.py
```

Static validation checks parseability, compilation, version/build/schema contracts, generated names, seams, legacy deformation keys, registered regions, capture and stamp contracts, exact-index world-space synchronization, morph export hooks, forbidden transfer mechanisms, merge markers, and repository hygiene.

Static success means the accepted source contracts remain present. It does not prove Blender registration, UI behavior, mesh operations, viewport presentation, sculpt mode transitions, glTF export, or reimport behavior.

## Build the installable ZIP

Run `python scripts/build_release.py`. The command validates first and writes `dist/Dreadstone_Animation_Forge_v3_10_1.zip`. The archive has deterministic timestamps and ordering and contains only:

```text
blender_manifest.toml
__init__.py
damage_readiness.py
damage_authoring.py
deformation_authoring.py
trauma_field.py
README.txt
VALIDATION.txt
```

`dist/` is generated and must not be committed.

## Blender 5.1.2 runtime acceptance

Perform this exact beginner-readable acceptance in Blender 5.1.2 before accepting or publishing a release. Repository checks and GitHub Actions do not perform these steps.

1. **A — Install from Disk.** Close any old Forge session, open Blender 5.1.2, choose **Edit > Preferences > Add-ons > Install from Disk**, select `dist/Dreadstone_Animation_Forge_v3_10_1.zip` without extracting it, enable **Dreadstone Animation Forge**, and restart Blender.
2. **B — Open the affected asset.** Open the accepted Testman Damage Asset authoring Blend and save a disposable test copy before editing.
3. **C — Check the intentional deletion.** In **Object Data Properties > Shape Keys** for both `DSB_ATTACHED_HEAD` and `DSB_SEGMENT_HEAD`, confirm a previously deleted `Head_Dent_Left` is still absent. Merely opening Trauma Field must not recreate it.
4. **D — Repair legacy sync.** Open **Dreadstone > Trauma Field Authoring v3.10.1**, select region `head`, click **REPAIR LEGACY PAIR SYNC**, and record the inspected, healthy, repaired, skipped, and unrepairable counts. Confirm the deleted key remains absent.
5. **E — Validate morph targets.** Click **Validate Morph Targets** and record the complete result. A repairable stale detached legacy key should now pass; an unsafe attached key must remain unchanged and report why it is unrepairable.
6. **F — Rebuild the active procedural key.** Select or create `Head_Impact_Left_v001`, retain its Broad Cave, Compact Dent, Raised Impact Rim, and slight Directional Shear stamps, click **REBUILD ACTIVE DEFORMATION**, and confirm no unrelated stale legacy mismatch blocks the rebuild.
7. **G — Select a seam-crossing patch.** Make `DSB_ATTACHED_HEAD` active, enter Edit Mode with face selection enabled, and select one visibly continuous 30–80-face temple patch that crosses an imported GLB UV/normal/material split seam.
8. **H — Capture it.** Choose **Selected Face Patch** and click **Capture Connected Face Patch**. Confirm the panel reports one virtual seam component and does not report disconnected islands.
9. **I — Prove true islands still fail.** Add a genuinely separate face island to the selection and capture again. Confirm Forge rejects the selection as disconnected; remove the island and recapture the original patch.
10. **J — Preview Surface Distance.** Set **Surface Distance** and **Patch Feathered** or **Connected Surface**, then preview the active stamp. Confirm influence crosses the legitimate split seam smoothly and still stops at the configured feather distance or radius.
11. **K — Check for skull shortcuts.** Orbit to the opposite side and inspect the preview. Confirm influence follows connected surface edges and does not jump directly through the skull to a spatially nearby but surface-disconnected area.
12. **L — Enter Damage Detached preview.** In **Damage Segment & Stump Authoring**, choose **Head–Neck** and click **Preview Detached**. Confirm the detached head and the expected caps appear.
13. **M — Return to Trauma Attached.** In Trauma Field click **Attached**. Confirm the full `DSB_ATTACHED_HEAD` is visible, `DSB_SEGMENT_HEAD` is hidden, the upper head is present, and no stump cap was newly shown.
14. **N — Inspect Detached.** Click **Detached**. Confirm `DSB_ATTACHED_HEAD` is hidden and the complete `DSB_SEGMENT_HEAD` is visible without Trauma Field changing cap or render/export state.
15. **O — Inspect Both and restore Damage Intact.** Click **Both** and confirm both head objects overlap visibly with no new stump. Return to Damage Authoring and click **Preview Intact**; confirm the existing intact body preview still works.
16. **P — Repeat on the left forearm.** Register `DSB_ATTACHED_FOREARM_L` and `DSB_SEGMENT_FOREARM_L` as `forearm_left`, validate the pair, repeat the seam-crossing patch and true-island checks, build and rebuild one Flat Compression stamp, and repeat Attached, Detached, Both, and Damage Preview Intact checks.
17. **Q — Validate the complete asset.** In Damage Authoring run **Validate Complete Damage Asset** and record all validation output. Confirm the temporary `__DSB_DEFORMATION_SEED_PREVIEW` key is not part of export data.
18. **R — Export.** Run **Export Damage GLB + Manifest** to a project folder. Confirm the GLB, manifest JSON, and validation JSON are created and the manifest retains all three accepted schemas plus v3.10.1 deformation metadata.
19. **S — Clean reimport.** Start a clean Blender file, import the exported GLB, run **Restore Reimported GLB Intact Preview**, confirm the intact head and forearms are complete, detached pieces/caps/socket are hidden as before, and verify the expected morph names and behavior.

The repair contract is intentionally narrow: missing legacy keys are not recreated automatically, unrepairable attached keys are not overwritten, virtual welding is analytical only, and no Blender mesh merge operation occurs. Trauma Field viewport inspection does not rewrite render/export visibility.

Also require the add-on to enable without registration errors, **Validate Complete Damage Asset** to pass, the exported manifest to retain all three accepted schemas, the temporary preview key to be absent from export, and intact/detached damage previews to retain their accepted behavior.

Record the Blender version, source commit, ZIP SHA-256, asset used, validation outputs, and visual observations. Do not describe GitHub Actions as Blender runtime testing.

## Project workflow

This project uses a direct-to-`main` workflow. Validate the complete intended change, inspect the diff, commit intentionally, and push `main`. Do not commit source archives, `dist/`, Blender backup files, bytecode, caches, or temporary extraction directories.

## Version bumps

For an authorized release version change:

1. Update `bl_info["version"]` in `dreadstone_animation_forge/__init__.py`.
2. Update the matching deformation version and only those build identifiers whose implementations changed.
3. Preserve manifest schemas, operator IDs, and generated DSB names unless a separately approved migration explicitly changes them.
4. Update validator/test contracts, `pyproject.toml`, README, changelog, and release documentation.
5. Run static validation and unit tests.
6. Complete Blender runtime acceptance.
7. Build twice and compare SHA-256 hashes before tagging.
