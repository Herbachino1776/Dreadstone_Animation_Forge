# Forge Performance and Stability Acceptance

Acceptance date: 2026-07-20
Release candidate: Forge `3.15.0` / build `2026-07-20.healing.1`
Baseline: Forge `3.14.1`, commit `e139c4645d6529a3d81ac594e2b897698fd8c9c1`
Runtime: Blender `5.1.2` (`ec6e62d40fa9`) on Windows
Source: `testman_animpack_v002.glb`, SHA-256 `5849556A3EB9AFC71D1BB5C6B686EAB6870046D593675B95853E4BC88500600E`, 1,319,976 bytes

This report records technical/runtime acceptance only. Technical seed faces were selected deterministically to exercise code paths; they are not anatomical choices. No visual or artistic approval is claimed.

## Result

**PASS** for static, unit, Blender runtime, performance gate, resource stability, lifecycle, validation, export/reimport, raised gore, compound trauma, and guard-animation contracts. Items requiring artist inspection are listed separately below.

## Historical regression comparison

Isolated worktrees used the same Blender executable, machine, and synthetic 10,000-vertex surface workload:

| Revision | Forge | Pure surface median | Tests | Static |
|---|---:|---:|---:|---:|
| `dd31aca0a50429968b0b8fd08cb45dc08fe30b02` | 3.13.0 | 514.6 ms | 130 | 18/18 |
| `967a0fa13fe4151b18e84c872db7510bca5f5804` | 3.14.0 | 517.0 ms | 197 | 18/18 |
| `e139c4645d6529a3d81ac594e2b897698fd8c9c1` | 3.14.1 | 509.0 ms | 198 | 18/18 |

Outputs were identical: 10,000 weld groups, 9,159 geodesically reached vertices, and 1,000 selected gore faces. The 3.14 pure result was 0.5% slower than 3.13 and current main was 1.1% faster. The suspected regression was therefore not in the Blender-free trauma algorithms. Profiling narrowed it to Blender-facing orchestration: draw-time topology/weight validation, synchronous RNA callback rebuilds, repeated snapshots/fingerprints, and final gore work during interactive edits.

## Relative performance gates

### Live preview

An untouched 3.14.1 callback-path sample on the prepared Testman fixture measured **76.463 ms median**. The 3.15 one-click workflow performed 25 warm FAST previews at **24.593 ms median** (23.921 ms minimum, 28.060 ms maximum). That is a **67.8% median latency improvement**, exceeding the required 50% gate.

Property callbacks in 3.15 only mark dirty state, advance a generation token, and schedule the single 200 ms debounce timer. The benchmarked geometry work was invoked explicitly after the callback, not synchronously by it.

### Final deformation rebuild

For an apples-to-apples head-only, deformation-only recipe on the same saved fixture, 15 warm rebuilds measured:

| Implementation | Median | Minimum | Maximum |
|---|---:|---:|---:|
| Untouched 3.14.1 | 122.694 ms | 121.370 ms | 147.962 ms |
| 3.15.0 | 80.040 ms | 79.445 ms | 84.741 ms |

The final deformation rebuild improved **34.8%**. The complete 3.15 rebuild on the release fixture also constructs two final raised-gore shells and runs focused deformation/pair/gore validation; representative runs measured 134.628 ms from the one-click commit and 138.609 ms in the operation harness. The equivalent untouched 3.14.1 fixture cannot complete final raised-gore validation because it reports non-manifold shell edges, so no invalid timing is presented as a passing baseline.

## Blender operation harness

The final `tests/blender_performance_acceptance.py` stress report recorded 21 PASS, 5 prerequisite SKIP, and 0 FAIL. The five skips (capture, body rebuild, forearm rebuild, compound preview, and compound rebuild) are expected on the focused single-head-key fixture and are covered by the separate workflow and comprehensive core/compound runners below.

Representative final timings from the release candidate are:

| Operation | Result |
|---|---:|
| Registration | 51.095 ms |
| Cached panel open | 0.024 ms |
| Idle cached state read, 100 repetitions | 0.005 ms median |
| Region switch | 2.012 ms median |
| Deformation-key switch | 0.789 ms median |
| Five-preview slider sequence | 126.070 ms total |
| Permanent deformation + final gore + focused validation | 138.609 ms |
| Attached/detached synchronization | 19.442 ms |
| Raised-gore rebuild | 27.787 ms |
| Complete asset validation | 1,379.375 ms |
| Save/reload | 170.418 ms |
| Disable/re-enable, 3 repetitions | 29.878 ms median |
| File reload with add-on active | 112.394 ms |
| 50 preview/clear cycles | 26.749 ms median per cycle |
| 20 region/key switches | 2.410 ms median |
| 10 final gore rebuilds | 28.153 ms median |

Timing samples vary with process startup and host load. Release gates use paired or warm medians, not the fastest observation.

## Resource and memory stability

Across the required 50 preview/clear cycles, growth was exactly zero for objects, meshes, materials, Actions, shape keys, collections, attributes, generated gore objects, temporary preview objects, Forge load handlers, and Forge preview timers. Counts remained 32 objects, 23 meshes, 6 materials, 5 Actions, 9 shape keys, 8 collections, 248 attributes, 2 generated gore objects, 0 preview objects, 1 Forge load handler, and 0 registered preview timers.

Windows process working set was 294.031 MiB immediately before the 50-cycle stress block, 293.949 MiB after it, 294.020 MiB after 20 additional warm plateau-probe cycles, and 294.031 MiB at completion. The warm probe grew only 72 KiB and passed the 8 MiB/3% plateau tolerance. Bounded final Python cache counts were: geodesic contexts 1, geodesic distances 1, gore face records 1, mesh snapshots 9, seam factors 1, serialized payloads 5, validation summaries 2, and weighted adjacency 1.

Three repeated disable/re-enable cycles retained exactly one Forge load handler and no preview timer. Save/reload and an additional active-add-on file reload both passed. No crash occurred.

## Live Testman acceptance

### Character processing

The untouched supplied GLB imported as 11,792 vertices, 19,842 polygons, one armature, and five source Actions. `Prepare Character for Damage Authoring` measured the 4.762897 m source, applied the existing 1.5 m target-height contract (factor 0.31493), ran Source Damage Readiness, loaded the READY handoff, built the authoring asset, registered head/body/left-forearm/right-forearm regions, ensured their Basis keys, validated the result, and saved/reloaded it. Total import-plus-orchestration time was 7.896 s. Source readiness and complete authoring validation passed after reload.

### One-click impact and transaction

`Create Impact From Current Selection` used 13 explicitly selected technical faces. An invalid empty selection first returned CANCELLED and left the managed-key inventory unchanged. The valid call created `Technical_Testman_Impact_v001` in 80.981 ms, generated FAST preview, selected/soloed the draft, and committed deterministic final output in 134.628 ms. Focused and complete validation both passed; attached and detached final gore each contain 40 triangles.

### Body, forearms, compound event, and guards

A comprehensive technical fixture built four head keys, two body-core keys, one key on each forearm, and the two-participant `Neck_Shoulder_Crush_Left` compound event. Validation passed. Core/compound/guard acceptance then passed with:

- body final gore: 3,808 and 112 CORE triangles;
- left forearm: 132 attached + 132 detached triangles;
- right forearm: 164 attached + 164 detached triangles;
- head/body full-weight seam mismatch: 0.0 m against 0.0005 m tolerance;
- no seam-topology mutation;
- three guard drafts validated with `Brace_Start=1`, `Guard_Active=9`, and `Brace_End=17`.

Compound participants carry region/topology, child-key, shared-field, seam, gore-recipe, and preview-generation digests. Only dirty participants inside the active event are recomputed; unrelated regions/events are not rebuilt. Shared-field changes correctly dirty every participant whose output depends on that field.

### Raised gore

The four standard head deformations each produced 40 attached + 40 detached final triangles. Sixteen generated gore nodes survived manifest export and clean reimport, retained material contracts, and remained inactive by default. Manifold filtering and island separation prevent pinched/corner-sharing technical patches from producing non-manifold vertical shell edges. High-intensity raised geometry was preserved; it was not replaced by flat decals.

### Diagnostics

Startup Self-Check returned PASS with zero findings. `Write Forge Diagnostic Report` produced JSON and Markdown plus a Blender Text datablock. The privacy-safe report included version/build, Blender version, datablock and generated-gore totals, handler/timer and bounded-cache counts, active region/key/capture/stamp/event, validation states, recent timings, and last-exception state without mesh payloads.

## Export and compatibility acceptance

Damage authoring/export validation, GLB export, additive manifest generation, and clean reimport passed. Morphs, raised-gore nodes, materials, inactive defaults, ownership, compound metadata, and exact-index pair mappings passed. Approved Animation Pack validation and clean reimport passed with only the approved Actions. The preserved original rig/hierarchy is now resolved for animation export even when the generated authoring rig is active or the source hierarchy is hidden after reload.

Portable stamp library formats 1-4 and exact-topology round trips remain covered by unit/runtime tests. A source-recovery exercise did not force analytical positional rebinding because the rebuilt source had identical topology and therefore correctly used exact-index binding; analytical rebind remains unit-covered but is not claimed as a live topology-change acceptance result.

## User visual approval still required

The user should inspect and approve:

1. head impact deformation shape and heavy raised-gore silhouette;
2. front/side torso capture placement and deformation quality;
3. left/right forearm capture placement, deformation quality, and elbow appearance;
4. clot silhouette, clean gaps, wet/dark material variation, shell thickness, and triangle budgets;
5. head/body compound seam appearance at full weight;
6. left-arm, right-arm, and two-arm `Guard_Active` poses, intersections, and weapon readability;
7. final damage and animation appearance after clean reimport.

## Release gate summary

- Unit tests: **209 PASS** (baseline 198).
- Static validator: **18/18 PASS**.
- Performance runner: **21 PASS / 5 prerequisite SKIP / 0 FAIL**.
- Workflow, raised-gore, core/compound/guard, diagnostics, export, and clean-reimport runners: **PASS**.
- Preview/resource stress and memory plateau: **PASS**.
- Registration, repeated unregister/register, save/reload, and active file reload: **PASS**.
- Deterministic release build: **PASS**, two 930,781-byte ZIPs matched at SHA-256 `E3549B301AF2D1F98090748DE4C5DE02479C3CC32FD15268092C528D3005409D`; all 38 entries are at the extension root or expected package subpaths.
- Clean-profile ZIP install: **PASS** through Blender's extension installer. Disable removed the scene properties, re-enable restored the task operator and one Forge load handler, and a new Blender process restarted enabled with Startup Self-Check PASS and no timer.
- Visual approval: **not claimed; user action required**.
