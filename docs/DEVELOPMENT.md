# Development

## User documentation boundary

The authoritative beginner-facing installation, authoring, validation, export, and reimport procedure is [USER_WORKFLOW_GUIDE.md](USER_WORKFLOW_GUIDE.md). Keep this file developer-focused. Do not duplicate the complete user workflow here.

When implementation and documentation disagree, inspect the current registered panels, operators, properties, generated names, validation contracts, and export code; then correct the user guide and any stale user-facing source text together.

## Tooling requirements

Repository tools require Python 3.10 or newer and use only the standard library. No `pip install` step is required for static validation, unit tests, or release packaging.

Blender's `bpy`, `bmesh`, and `mathutils` modules are available only inside Blender. Repository tools inspect and compile source without importing the add-on or faking a Blender environment.

## Static checks

From the repository root, run:

```text
python scripts/validate_addon.py
python -m unittest discover -s tests -p "test_*.py"
python scripts/build_release.py
```

Static validation checks parseability, compilation, version/build/schema contracts, generated names, seams, public operators and labels, trauma-field contracts, exact-index synchronization, GLB hooks, repository hygiene, and the required inventory/version/artifact markers in `docs/USER_WORKFLOW_GUIDE.md`.

Static success does not prove Blender registration, UI behavior, mesh operations, viewport presentation, sculpt transitions, GLB export, or reimport behavior.

## Build the installable ZIP

Run `python scripts/build_release.py`. It validates first and writes `dist/Dreadstone_Animation_Forge_v3_10_2.zip` with deterministic timestamps and ordering. Its exact root layout is:

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

`README.txt` is generated from the concise repository README. `dist/` is generated and must not be committed. Before a release, build twice from unchanged source and require identical SHA-256 hashes.

## Blender 5.1.2 runtime acceptance

Use the current [user workflow guide](USER_WORKFLOW_GUIDE.md) as the acceptance procedure. At minimum:

1. Install the current unextracted ZIP with the documented method and confirm the add-on registers.
2. Complete the guide's head-impact, forearm-impact, legacy-repair, attached/detached comparison, and export/reimport recipes on accepted assets.
3. Exercise every item in the guide's complete public button inventory.
4. Require Source Readiness, **Validate Morph Targets**, **Validate Complete Damage Asset** (Authoring Validation), Export Validation, and exported validation JSON to pass.
5. After building authoring assets, explicitly rerun Source Readiness and confirm its analyzed inventory is still the original source rather than `DSB_BODY_CORE` or `DSB_ATTACHED_*`.
6. On a disposable affected 3.8 file, run **Repair Source Readiness Contract** and confirm generated topology, keys, and stamps are byte-for-byte/metadata unchanged.
7. Confirm virtual welding remains analytical only, missing legacy keys are not recreated, unrepairable attached keys are not overwritten, and Trauma Field views do not rewrite render/export visibility.
8. Record Blender version, source commit, ZIP SHA-256, assets, validation outputs, and visual observations.

GitHub Actions runs static checks and packaging; it is not Blender runtime testing.

## User guide release definition of done

Every future release must complete all four items:

- [ ] Inspect the current implementation and update `docs/USER_WORKFLOW_GUIDE.md` when the workflow, UI, feature set, installation method, object names, validation process, or export process has changed.
- [ ] Confirm the guide's version number and ZIP name match the current release.
- [ ] Confirm every public user-facing operator and major workflow section is represented in the guide.
- [ ] Remove stale instructions from the previous version.

## Project workflow

This project uses a direct-to-`main` workflow. Validate the intended change, inspect the diff, commit intentionally, and push `main`. Do not commit source archives, `dist/`, Blender backups, bytecode, caches, or temporary extraction directories.

## Version bumps

For an authorized release version change:

1. Update `bl_info["version"]` in `dreadstone_animation_forge/__init__.py` and `version` in `blender_manifest.toml`.
2. Update the matching deformation version and only the build identifiers whose implementations changed.
3. Preserve manifest schemas, operator IDs, and generated DSB names unless an approved migration changes them.
4. Update validator/test contracts, `pyproject.toml`, changelog, README, release documentation, and `docs/USER_WORKFLOW_GUIDE.md`.
5. Complete the user guide release definition of done above.
6. Run static validation and unit tests.
7. Complete Blender runtime acceptance from the guide.
8. Build twice and compare SHA-256 hashes before tagging.
