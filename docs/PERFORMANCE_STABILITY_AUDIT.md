# Forge Performance and Stability Audit

Audit date: 2026-07-20
Baseline commit: `e139c4645d6529a3d81ac594e2b897698fd8c9c1`
Baseline version: Forge `3.14.1`
Runtime contract: Blender `5.1.2` (extension manifest minimum `4.2.0`; legacy `bl_info` minimum `3.6.0`)
Safety branch: `safety/pre-forge-healing-e139c464`

## Scope and method

This audit was completed before the healing refactor. It combines source-level call-path inspection, isolated historical worktrees, `time.perf_counter` measurements, and a focused `cProfile` run. It does not infer causation from commit order.

The comparison worktrees are:

| Revision | Forge | Purpose | Unit tests | Static validation |
|---|---:|---|---:|---:|
| `dd31aca0a50429968b0b8fd08cb45dc08fe30b02` | 3.13.0 | Raised-gore baseline | 130 | 18/18 |
| `967a0fa13fe4151b18e84c872db7510bca5f5804` | 3.14.0 | First core/compound release | 197 | 18/18 |
| `e139c4645d6529a3d81ac594e2b897698fd8c9c1` | 3.14.1 | Current main | 198 | 18/18 |

The supplied source asset is `testman_animpack_v002.glb`, SHA-256 `5849556A3EB9AFC71D1BB5C6B686EAB6870046D593675B95853E4BC88500600E`, 1,319,976 bytes. A Blender 5.1.2 factory import contains one skinned character mesh (`model`, 11,792 vertices and 19,842 polygons), one armature (`rig`), and five approved Forge Actions. Generated outputs are kept outside the repository.

## Regression-range evidence

The 3.13.0 to 3.14.0 range added 3,680 lines and removed 245 lines. Blender-facing `deformation_authoring.py` grew by 1,622 lines and `__init__.py` by 577 lines. The current 3.14.1 hotfix is small (103 additions and 38 deletions over 3.14.0) and is not a credible source of the broad interaction slowdown.

A deterministic 100 x 100 synthetic surface benchmark ran virtual-weld construction, weighted adjacency, radius-limited geodesics, and raised-gore face selection five times in each worktree. Medians were:

| Revision | Median | Minimum | Maximum | Result tuple |
|---|---:|---:|---:|---|
| 3.13.0 | 0.5146 s | 0.5039 s | 0.5192 s | 10,000 weld groups / 9,159 reached / 1,000 gore faces |
| 3.14.0 | 0.5170 s | 0.5129 s | 0.5249 s | identical |
| 3.14.1 | 0.5090 s | 0.5041 s | 0.5162 s | identical |

The focused current-main `cProfile` sample spent 0.864 s of 1.252 s cumulative in `raised_gore_face_records`, 0.452 s in multi-frequency gore noise, 0.234 s in virtual-weld construction, 0.119 s in adjacency construction, and 0.032 s in geodesics. The historical samples have the same profile and output. Therefore the pure algorithm layer did not measurably regress across the suspected range. The regression range is narrowed to Blender-facing orchestration introduced or exercised more often in 3.14, especially draw-time validation, synchronous property callbacks, repeated snapshots/fingerprints, all-participant compound rebuilds, and final gore generation during iteration.

## Confirmed hot paths

### Panel draw performs mesh-scale work

`deformation_authoring.draw_panel()` calls `_resolve_active_region()` and then `validate_region_contract()` on every redraw. For a paired region that performs two complete polygon topology hashes and one complete vertex-group/weight hash. The same draw also reparses deformation metadata and the scene registry, enumerates managed keys, and constructs the full expert UI.

Consequences on the 11,792-vertex Testman mesh:

- merely exposing or redrawing the panel hashes every polygon and every relevant vertex weight;
- dragging any UI control causes redraws that overlap the callback work described below;
- adding body and forearm regions increases the amount of registry and UI state traversed even when only one region is active.

This violates the required idle-panel contract. Full topology/weight checks belong in explicit validation and registration, not `Panel.draw()`.

### Property updates synchronously rebuild geometry

`_deformation_preview_property_updated()` calls `refresh_live_seed_preview()` directly. That function clears the geodesic cache and immediately invokes either `preview_active_stamp()` or `preview_seed()`. The preview path recreates world-coordinate lists, virtual-weld context, adjacency/geodesic results, shape-key coordinates, paired synchronization, visibility changes, and status writes during the RNA property callback.

`_deformation_metadata_property_updated()` directly calls `update_active_key_metadata()`. Its `_store_metadata()` call serializes the full key payload, writes it to object and mesh custom properties, recomputes topology and weight fingerprints, and rewrites the region registry.

These callbacks explain slider stalls and make recursive updates possible when preview/load functions assign other update-enabled settings. They also create large undo/depsgraph bursts during continuous mouse motion.

### Snapshot and fingerprint duplication

World positions, basis positions, topology fingerprints, weight fingerprints, virtual welds, edge lists, adjacency, deformation-point digests, normals, and face records are assembled independently by capture, preview, validation, gore, and compound paths. There is no shared topology-state snapshot service.

The geodesic cache avoids only the final shortest-path solve. Its key is appropriately sensitive to topology, object identity, selection, distance mode/range, and virtual-weld state, but the expensive inputs needed to construct that key are recalculated before every lookup.

### Unbounded and file-unsafe caches

`_GEODESIC_CACHE` and `_GEODESIC_CACHE_CONTEXT` are ordinary unbounded dictionaries. Many operators clear them, but there is no file-load handler and unregister only clears gore previews. Cache context stores names rather than RNA objects, which is safer, but old entries can survive loading a different file until a later operator happens to invalidate them.

### Raised-gore iteration always pays final cost

`rebuild_raised_gore_for_key()` selects final-budget faces and builds final attached/core and detached shell objects. Material and object generation are coupled to evaluation. Stain preview copies materials and writes preview state independently. There is no FAST representation, no face-record cache separated from generated objects, and no quiet-period distinction between slider feedback and final deterministic output.

Final gore quality is not the problem to remove. The problem is invoking final topology generation during ordinary tuning and recomputing source-derived face data for both pair roles.

### Compound rebuild is all-or-nothing

`rebuild_compound_event()` recomputes every participant, synchronizes every child key, creates a heavy gore recipe, and calls final raised-gore rebuild inside the participant loop. It has no participant digest cache or dirty set. Changing one shared-field value necessarily rebuilds unrelated participants and their gore.

The rollback path is conscientious but expensive: after an exception it restores shape-key coordinates and metadata, removes generated gore, and attempts to regenerate prior final gore. A second failure during recovery can leave validation to report missing/stale geometry rather than restoring the exact prior generated resources.

## Likely crash and corruption paths

These are evidence-backed risks; a Blender crash dump was not available, so they are not claimed as the unique cause of the reported crash.

1. **Synchronous callback re-entry and depsgraph pressure.** RNA updates perform shape-key writes, visibility changes, metadata writes, cache invalidation, and paired synchronization before returning. Continuous sliders can interleave redraw and depsgraph work without a generation token.
2. **Non-idempotent registration.** `register()` calls `bpy.utils.register_class()` unconditionally. A partial prior registration or reload raises midway. `unregister()` can likewise stop on a missing class. There is no central lifecycle state or cleanup in `finally`.
3. **No timer ownership.** Current preview is synchronous, so there is no duplicate timer today; adding debounce without a single owner would easily create stacked timers. The healing design must make timer ownership explicit and unregister-safe.
4. **Partial context restoration.** Multiple operators switch mode, active object, selection, visibility, shape-key values, Actions, and materials with local ad-hoc backups. Exception coverage differs by operator, and internal `bpy.ops` calls depend on the current context.
5. **Generated-resource replacement windows.** Gore rebuild removes/replaces generated objects and materials around several failure points. Preview material copies and state JSON can become inconsistent if Blender raises during node/material or mesh creation.
6. **Unbounded warm-session state.** Geodesic entries have no capacity limit or load-file invalidation. Repeated unique selections/radii can grow Python memory until another coarse invalidation happens.
7. **Compound rollback amplification.** One participant failure can trigger final-gore rebuilds for earlier participants during exception handling, increasing allocation and failure pressure at the worst time.

No worker-thread access to `bpy` was found. No persistent app handlers, depsgraph handlers, draw handlers, or msgbus subscriptions exist in the baseline. `bmesh.from_edit_mesh()` uses Blender-owned edit BMesh objects; no leaked `bmesh.new()` allocation was found.

## Healing decisions

The implementation should preserve `trauma_field.py` as the Blender-free algorithm layer and retain `deformation_authoring.py` as a compatibility facade. The first architectural boundaries are:

- bounded, name/data-only caches with explicit file-load/unregister invalidation;
- bulk mesh snapshots shared by capture, preview, gore, and validation;
- one main-thread preview manager with OFF/FAST/BALANCED/FINAL quality, one debounce timer, generation tokens, and exact cleanup;
- transaction capture/rollback for multi-step operators;
- cached UI summaries so draw functions never validate or hash meshes;
- source-data and recipe-output separation for raised gore;
- per-participant compound digests and dirty recomputation;
- idempotent lifecycle registration with startup self-check and diagnostics.

Full Blender measurements and resource-growth results belong in `PERFORMANCE_STABILITY_ACCEPTANCE.md`. Visual quality and anatomical surface approval always remain user decisions.
