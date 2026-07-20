# Development

## User documentation boundary

The authoritative beginner-facing installation, authoring, validation, export, and reimport procedure is [USER_WORKFLOW_GUIDE.md](USER_WORKFLOW_GUIDE.md). Runtime-facing contracts are in [CORE_COMPOUND_EXPORT_CONTRACT.md](CORE_COMPOUND_EXPORT_CONTRACT.md) and [RAISED_GORE_EXPORT_CONTRACT.md](RAISED_GORE_EXPORT_CONTRACT.md). Keep this file developer-focused. Do not duplicate the complete user workflow here.

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

Static validation checks parseability, compilation, version/build/schema contracts, generated names, seams, public operators and labels, core/paired/compound trauma-field and surface-gore contracts, guard action metadata, managed preview cleanup, exact-index synchronization, GLB hooks, repository hygiene, and the required inventory/version/artifact markers in `docs/USER_WORKFLOW_GUIDE.md`.

Static success does not prove Blender registration, UI behavior, mesh operations, viewport presentation, sculpt transitions, GLB export, or reimport behavior.

## Build the installable ZIP

Run `python scripts/build_release.py`. It validates first and writes `dist/Dreadstone_Animation_Forge_v3_15_1.zip` with deterministic timestamps and ordering. Its extension-root layout is:

```text
blender_manifest.toml
__init__.py
damage_readiness.py
damage_authoring.py
deformation_authoring.py
trauma_field.py
deformation/__init__.py
deformation/*.py
ui/__init__.py
ui/*.py
ui/operators/*.py
README.txt
VALIDATION.txt
```

Every package Python file is discovered recursively, normalized to a POSIX archive path, and sorted before writing. `README.txt` is generated from the concise repository README. `dist/` is generated and must not be committed. Before a release, build twice from unchanged source and require identical SHA-256 hashes.

## Healing architecture and hot-path rules

`deformation_authoring.py` remains the public compatibility facade. New Blender-facing ownership is split among bounded registry/cache services, bulk mesh and shape-key access, capture/deformation/pair/compound/gore services, one preview lifecycle, focused validation summaries, serialization, transactions, diagnostics, and task UI modules. `trauma_field.py` remains the Blender-free algorithm layer.

Panel draw and property callbacks must stay lightweight. Draw reads cached summaries and renders controls. Updates mark dirty and schedule the one preview manager timer. Mesh snapshots and Blender RNA are main-thread only; pure numeric work may be separated only after safe copying. Caches must be bounded and invalidated on file load, unregister, topology/transform/source changes, region removal, and explicit rebuild.

Run the performance/resource harness against an artist-prepared fixture:

```text
blender prepared.blend --factory-startup --background --python tests/blender_performance_acceptance.py -- --output performance.json --source source.glb --stress
```

The runner records operation medians, exceptions, cache/handler/timer counts, RSS where available, and warm-cycle resource growth. It never chooses anatomical faces and reports `SKIP` when the prepared fixture lacks an authored prerequisite. A release must not relabel those skips as visual or runtime approval.

## Blender 5.1.2 runtime acceptance

Use the current [user workflow guide](USER_WORKFLOW_GUIDE.md) as the acceptance procedure. At minimum:

1. Install the current unextracted ZIP with the documented method and confirm the add-on registers.
2. Complete the guide's head-impact, forearm-impact, legacy-repair, attached/detached comparison, and export/reimport recipes on accepted assets.
3. Exercise every item in the guide's complete public button inventory.
4. Require Source Readiness, **Validate Morph Targets**, **Validate Complete Damage Asset** (Authoring Validation), Export Validation, and exported validation JSON to pass.
5. After building authoring assets, explicitly rerun Source Readiness and confirm its analyzed inventory is still the original source rather than `DSB_BODY_CORE` or `DSB_ATTACHED_*`.
6. On a disposable affected 3.8 file, run **Repair Source Readiness Contract** and confirm generated topology, keys, and stamps are byte-for-byte/metadata unchanged.
7. Build `Head_Impact_Left_v001`, `Head_Impact_Right_v001`, `Head_Impact_Front_v001`, and `Head_Impact_Back_v001`; apply `Gore_Crush_Heavy_Clotted`, rebuild each raised shell, and verify dense irregular thickness, multiple disconnected islands, clean exterior gaps, three material roles, and correct attached/detached placement without holes or exposed tissue.
8. Clear every stain preview and confirm original material slots return exactly. Rebuild raised gore, then export and confirm temporary stain materials/attributes are removed while ordinary gore nodes, glTF-safe materials, ownership/digest extras, triangle counts, and inactive activation semantics remain in the GLB/manifest.
9. Save a multi-key **Stamp Library**, load it into a clean authoring rebuild from the same source, and confirm names, stable IDs, order, enabled state, captures, gore settings/seeds/digests, rebuilt geometry, exact-index pairing, and validation survive the round trip. Exercise both exact-topology loading and analytical positional-anchor rebinding across GLB split/index changes; confirm unmatched anchors and conflicting existing keys are rejected without mutation.
10. Confirm virtual welding remains analytical only, missing legacy keys are not recreated, unrepairable attached keys are not overwritten, and Trauma Field views do not rewrite render/export visibility.
11. Run `blender prepared.blend --background --python tests/blender_raised_gore_acceptance.py -- --output <folder>` where possible; record Blender version, source commit, ZIP SHA-256, per-head attached/detached triangle counts, validation outputs, surface-gore/material observations, and clean-reimport manifest observations.
12. From a prepared 3.14 file containing explicit artist-authored body/forearm captures plus a two-region head/body compound event, run `blender prepared.blend --background --python tests/blender_core_compound_guard_acceptance.py -- --output <folder>`. Retain `core_compound_guard_acceptance.json` with body/forearm triangle counts, full-weight seam mismatch, topology-mutation flag, compound manifest mapping, three guard marker/pose validations, damage GLB reimport, and Approved Animation Pack reimport.
13. Static or background checks do not approve visual quality. Record user approval separately for body/arm anatomy, clot silhouette, cracks, all three guard poses, intersections, and final imported appearance.

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
