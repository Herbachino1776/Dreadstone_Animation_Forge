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

Static validation checks parseability, compilation, version/build/schema contracts, generated names, seams, deformation keys, operator IDs and labels, exact-index world-space synchronization, morph export hooks, forbidden transfer mechanisms, merge markers, and repository hygiene.

Static success means the accepted source contracts remain present. It does not prove Blender registration, UI behavior, mesh operations, viewport presentation, sculpt mode transitions, glTF export, or reimport behavior.

## Build the installable ZIP

Run `python scripts/build_release.py`. The command validates first and writes `dist/Dreadstone_Animation_Forge_v3_9_1.zip`. The archive has deterministic timestamps and ordering and contains only:

```text
README.txt
VALIDATION.txt
dreadstone_animation_forge/
dreadstone_animation_forge/__init__.py
dreadstone_animation_forge/damage_readiness.py
dreadstone_animation_forge/damage_authoring.py
dreadstone_animation_forge/deformation_authoring.py
```

`dist/` is generated and must not be committed.

## Blender 5.1.2 runtime acceptance

Perform this test in Blender 5.1.2 before accepting or publishing a release:

1. Build the release ZIP and install or reload it in Blender.
2. Confirm the add-on enables and its classes register without errors.
3. Open an existing protected Damage Asset Blend containing the generated attached/detached head pair.
4. Open **Damage Deformation Authoring v3.9.1** and choose **Attached** authoring view.
5. Select exactly one face on `DSB_ATTACHED_HEAD` and run **Capture Center from Selected Face**.
6. Select a standard key and click **BUILD ACTIVE PRESET**.
7. Confirm the preset is visibly readable at world scale and the managed key begins at/returns to zero when expected.
8. Switch to **Detached** and confirm the matching deformation has the same world-space delta despite object transforms.
9. Inspect **Both** overlay mode and attached/detached preview visibility controls.
10. Optionally run **Begin Sculpt**, make a small edit, then **Finish Sculpt & Sync** and confirm the exact-index pair remains valid.
11. Run **Validate Morph Targets** and require a pass.
12. Run **Validate Complete Damage Asset** and require a pass.
13. Export **Damage GLB + Manifest**; verify morph targets, morph normals, manifest schemas, deformation metadata, and the absence of the temporary seed key.
14. Import the GLB into a clean scene, run **Restore Reimported GLB Intact Preview**, and confirm intact geometry, visibility, textured display, framing, and hidden socket/caps/detached props.
15. Exercise Head–Neck, both elbows, and Lower Spine detached previews with representative approved animations.

Record the Blender version, source commit, release ZIP SHA-256, asset used, validation outputs, and any visual observations. Do not describe GitHub Actions as Blender runtime testing.

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
