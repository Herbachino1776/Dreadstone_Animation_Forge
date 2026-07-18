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

Run `python scripts/build_release.py`. The command validates first and writes `dist/Dreadstone_Animation_Forge_v3_10_0.zip`. The archive has deterministic timestamps and ordering and contains only:

```text
README.txt
VALIDATION.txt
dreadstone_animation_forge/
dreadstone_animation_forge/__init__.py
dreadstone_animation_forge/damage_readiness.py
dreadstone_animation_forge/damage_authoring.py
dreadstone_animation_forge/deformation_authoring.py
dreadstone_animation_forge/trauma_field.py
```

`dist/` is generated and must not be committed.

## Blender 5.1.2 runtime acceptance

Perform this exact primary test in Blender 5.1.2 before accepting or publishing a release:

1. Install the generated v3.10.0 ZIP.
2. Restart Blender fully.
3. Open the accepted Testman Damage Asset Blend.
4. Confirm legacy v3.9.1 keys remain present.
5. Confirm the head pair migrates or registers as region `head`.
6. Select a connected left-temple face patch.
7. Capture the patch.
8. Use `SURFACE_DISTANCE`.
9. Use `PATCH_FEATHERED`.
10. Create a new key named `Head_Impact_Left_v001`.
11. Add Broad Cave, Compact Dent, Raised Impact Rim, and slight Directional Shear stamps.
12. Rebuild the deformation.
13. Modify one stamp and rebuild.
14. Confirm the remaining stamps persist correctly.
15. Preview attached.
16. Preview detached.
17. Confirm deformation physical size matches.
18. Validate morph targets.
19. Export GLB and manifest.
20. Clean-reimport.
21. Confirm morph names and behavior remain correct.

Then perform this secondary generic-region smoke test:

1. Register `DSB_ATTACHED_FOREARM_L` and `DSB_SEGMENT_FOREARM_L`.
2. Use region ID `forearm_left`.
3. Capture a connected surface patch.
4. Build one Flat Compression stamp.
5. Rebuild.
6. Validate attached/detached synchronization.

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
