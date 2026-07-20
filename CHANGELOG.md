# Changelog

## 3.15.0

- Added one managed `OFF`/`FAST`/`BALANCED`/`FINAL` preview lifecycle with a single 200 ms main-thread debounce timer, stale-generation rejection, exact preview-state restoration, and explicit Commit/Revert/Clear actions.
- Replaced heavy synchronous deformation property callbacks and panel work with dirty marking and cached UI summaries; Testman FAST preview median improved from 76.46 ms on 3.14.1 to 24.59 ms on the same Blender 5.1.2 fixture and hardware (67.8%).
- Added bounded topology, adjacency, seam-factor, mesh-snapshot, serialization, gore-record, compound-participant, seam-mapping, and validation-summary caches with file-load, unregister, topology, region, and explicit-rebuild invalidation.
- Added task-oriented Start / Character, Damage Authoring, Animation, Validate & Export, and Advanced workspaces while retaining every previous public operator and expert workflow.
- Added transactional **Prepare Character for Damage Authoring** and **Create Impact From Current Selection** orchestration, standard head/body/forearm registration, impact presets, draft rollback, and focused final validation.
- Modularized Blender-facing deformation responsibilities under `deformation/` and `ui/` while preserving the `deformation_authoring.py` compatibility facade, schemas, generated names, exact-index behavior, portable libraries v1–v4, and export contracts.
- Added diagnostics JSON/Markdown/Text reporting, a cached in-panel runtime summary, startup duplicate-handler/timer checks, a repeatable Blender performance/resource/RSS runner, warm-cache plateau accounting, and focused architecture/performance tests.
- Fixed hidden source and generated-object transform validation after save/reload without weakening Source Readiness; validation briefly evaluates the saved hierarchy and restores exact visibility.
- Preserved high-intensity raised gore and made replacement transactional so a failed rebuild restores the prior owned geometry and metadata.
- Fixed pinched/corner-sharing raised-gore shell islands so final technical outputs remain manifold without flattening or weakening geometry validation.
- Fixed Approved Animation Pack export from hidden preserved source rigs and scoped glTF Action filtering so only approved Actions are exported and existing exporter filter state is restored.

## 3.14.1

- Fixed raised-gore validation in Blender builds whose Principled shader defaults expose a non-black emission color at zero strength. Generated gore now explicitly sets emission color to black and strength to zero, while validation rejects actual emissive output and linked emission inputs. Wetness continues to use Roughness and Coat Weight only.

## 3.14.0

- Added explicit `CORE_SINGLE` trauma-region registration for `DSB_BODY_CORE` and other single meshes without fake detached partners, while retaining `PAIRED_SEGMENT` exact-index behavior.
- Added body-core and left/right forearm impact starter records; artists still choose and capture the intended surface before stamping or rebuilding.
- Added first-class compound trauma events with one shared world-space field, deterministic per-participant seeds, mesh-local child morphs, synchronized preview, portable serialization, validation, and runtime manifest ownership.
- Added mapped seam-boundary continuity modes (`LOCK_BOUNDARY_TO_SHARED_FIELD`, `BLEND_ACROSS_SEAM`, and `PROTECT_SEAM`) without welding, merging, or mutating generated topology.
- Generalized thin stain and raised-gore generation to core meshes, forearms, and compound participants. Raised shells now use deterministic thickness relaxation and boundary tapering to reduce jagged triangular silhouettes.
- Added three FPS-aware mace head-guard animation drafts with `Brace_Start`, `Guard_Active`, and `Brace_End` markers, presented-region metadata, validation, preview, and Approved Animation Pack promotion.
- Extended portable trauma libraries to format 4 and GLB/manifest metadata with core region modes, compound activation mappings, participant gore nodes, seam reports, and approved brace semantics. Versions 1–3 remain supported.
- Added 67 focused core/compound, seam, body/arm, gore, animation, and export tests plus a prepared-scene Blender acceptance runner.
- Source Damage Readiness and `NOT READY` repair behavior were not changed.

## 3.13.0

- Add `Gore_Crush_Heavy_Clotted` as the recommended high-intensity preset for all Trauma Field regions, with dense core clots, broken rim islands, peripheral fragments, strong thickness variation, and clean gaps over the intact exterior.
- Upgrade Surface Gore Overlay to a hybrid stain plus deterministic ordinary-mesh shell. Shells follow each fully deformed target, use stamp influence and deformation magnitude, remain region-independent, and are generated once for matching attached/detached exact-index variants.
- Add three glTF-safe Principled material roles: wet crimson, dark clot, and rough clot edge. Metallic and emission remain zero; the temporary stain material is still removed before export.
- Add stable `DSB_GORE_ATTACHED_*` / `DSB_GORE_DETACHED_*` nodes, mesh IDs, ownership/source metadata, recipe/generation/geometry digests, source-vertex attributes, copied skinning, inactive-by-default extras, activation weight, material IDs, and triangle counts.
- Export raised gore meshes in the Damage GLB and record per-deformation node mappings plus the runtime activation contract in the manifest. Runtime activation itself remains intentionally outside Forge.
- Add **Apply Heavy Gore to All Deformations**, default-new-impact preference, custom-recipe preservation, **Clear Current Generated Gore**, **Rebuild All Generated Gore**, and separate **Validate Gore Geometry** actions.
- Extend portable stamp libraries to format v3 for raised recipes while retaining deterministic v1/v2 and Forge 3.12 stain-only migration. Generated mesh bytes are never serialized.
- Detect missing, stale, altered, incorrectly owned, preview-only, floating, empty, degenerate, duplicate, non-manifold, over-budget, unskinned, wrongly paired, wrongly visible, or non-glTF-safe raised gore.
- Add Blender runtime acceptance automation for four head impacts, paired previews, export, clean reimport, material preservation, node mappings, activation metadata, and recorded triangle counts.
- Add 29 focused Blender-independent raised-gore tests while retaining all readiness, deformation, stamp, legacy no-gore, and packaging contracts.

## 3.12.0

- Add optional **Surface Gore Overlay** authoring per deformation key for blunt trauma without exposed tissue, cavities, holes, or runtime game-side shader playback.
- Add five procedural presets: `Gore_Ooze_Wet`, `Gore_Clot_Dark`, `Gore_Smear_Heavy`, `Gore_Speckled_Impact`, and `Gore_Crush_Bloodied`.
- Generate a repeatable patchy mask from the linked trauma stamp's captured surface influence, edge feather, coverage, scatter, physical patch scale, and variation seed so no custom art is required.
- Preview wet/dark gore on the deformed outer surface through a managed color attribute and temporary copies of each object's original materials; clearing or exporting restores the original attached/detached material slots.
- Add the four directional `Head_Impact_*_v001` blunt-impact targets and author one linked overlay recipe that previews consistently on both exact-index paired meshes.
- Extend portable stamp-library v2 records with optional surface-gore recipes and digests while continuing to load v1 libraries and leaving keys without gore unchanged.
- Export additive preset, region, linked stamp/capture, coverage, scatter, feather, wetness, darkness, color, scale, seed, digest, and validation metadata under each authored deformation.
- Separate deformation, gore-overlay, and export validation status and detect invalid presets/ranges, missing or stale capture linkage, removed stamps/regions, broken recipes/digests, and missing claimed preview resources.
- Add focused deterministic serialization, validation, portable round-trip, tamper detection, seed/mask, no-gore regression, UI/preview, and export contract tests.

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
