# Changelog

## 3.11.0

- Add **Save Stamp Library...** to preserve every procedural stamp stack across all registered deformation regions in a portable `.dsbstamps.json` file.
- Add **Load Stamp Library...** to recreate missing deformation keys, rebind captures to current registered objects, rebuild paired morph geometry from `Basis`, and validate the result.
- Prefer exact region topology and add deterministic positional anchors that survive GLB split-vertex/index changes when the same surface coordinates match within a conservative quantization tolerance; incompatible targets are rejected without nearest-neighbor or guessed remapping.
- Preserve stamp IDs, names, order, enabled state, family, captures, masks, distance modes, parameters, and portable local damage direction metadata.
- Never overwrite a different existing deformation key or stamp stack; identical already-loaded recipes are skipped safely.
- Support saving stamps from a generated/reimported Damage GLB without requiring the missing original source-readiness objects.

## 3.10.2

- Separate Source Readiness, Generated Authoring Validation, and Export Validation so intentional authored cut boundaries can never invalidate the original source contract.
- Persist stable source armature, mesh-object, mesh-datablock, collection, mapping, topology, weight, analyzer, and report identity in `DSB_SOURCE_READINESS_CONTRACT.json`.
- Resolve explicit source-readiness reruns from the stored original inventory and reject missing originals instead of falling back to generated `DSB_*` authoring meshes.
- Verify the existing source contract during export without rerunning or overwriting the full readiness report.
- Add **Repair Source Readiness Contract** for affected 3.8 files; repair rebuilds only the source report/contract and preserves segment topology, deformation keys, and trauma stamps.
- Define staleness around original topology, relevant weights, armature/mapping, compatible analyzer revision, object/datablock identity, and source collection identity while ignoring generated authoring and preview/export state.
- Reject a procedural deformation stack with no enabled trauma stamp as a genuine authoring/export validation error.
- Add focused source-contract regression coverage and retain the exact Blender 5.1 extension ZIP layout.

## 3.10.1

- Add `docs/USER_WORKFLOW_GUIDE.md` as the release-controlled, beginner-facing source of truth for every current Forge workflow, public operator, validation path, and export/reimport recipe.
- Enforce the guide's presence, current version, release ZIP name, workflow headings, and key UI inventory in static validation and release checklists.
- Add guarded attached-authority repair for stale Forge-managed legacy detached keys while preserving strict exact-index world-space validation.
- Restore detached value drivers for healthy and repaired legacy pairs, record additive sync metadata, and leave missing or unrepairable keys untouched.
- Add deterministic analytical virtual welding for imported GLB split seams using `max(1e-7, world_bounds_diagonal * 1e-7)`.
- Define selected-face connectivity by shared virtualized edges, preserving rejection of true islands and corner-only contact.
- Add zero-cost links within virtual weld groups so radius-limited surface geodesics cross legitimate split seams without destructive topology edits.
- Include virtual weld digest and tolerance in capture metadata and geodesic cache identity.
- Normalize only the active registered pair and relevant DSB collection path for Attached, Detached, and Both viewport inspection without changing render/export visibility.
- Preserve the Blender 5.1.2 extension-root ZIP layout and deterministic release build.

## 3.10.0

- Package the add-on as a Blender extension with `blender_manifest.toml` and `__init__.py` at the ZIP root for Blender 5.1.2 **Install from Disk** compatibility.
- Add explicit registered attached/detached deformation regions with active-region selection and safe legacy `head` migration.
- Add connected face-patch, selected-vertex, single-face, and cursor capture with stale-capture detection.
- Add world-edge geodesic distance with radius-limited Dijkstra traversal and topology-aware caching.
- Add patch-only, patch-feathered, and connected-surface influence masks.
- Add editable, ordered trauma-stamp recipes with stable IDs and deterministic Basis rebuilds.
- Add Compact Dent, Broad Cave, Flat Compression, Directional Shear, Raised Impact Rim, and Ridge Collapse families.
- Preserve exact-index world-space attached/detached synchronization, legacy standard head keys, preview controls, sculpt/sync, mirror, GLB morph export, and schema `dreadstone.damage_deformation.v1`.
- Extend deformation manifests additively with registered regions and compact ordered stamp metadata.
- Add standard-library trauma-field algorithm tests and expanded static contracts.

## 3.9.1

- Evaluate seed radius and depth in world space.
- Synchronize attached/detached deltas with world-transform awareness.
- Validate deformation deltas and maximum displacement in world space.
- Add attached, detached, and both/overlay preview controls.
- Initialize standard deformation keys at zero.
- Automatically solo the active deformation key and seed preview.
- Add **BUILD ACTIVE PRESET**.
- Add a localized dent preset with a subtle raised rim.
- Strengthen preset and slider ranges for readable world-scale results.
- Keep sculpting optional.
