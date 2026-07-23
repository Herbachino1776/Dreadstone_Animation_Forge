# Dreadstone Animation Forge 3.16.2 — User Workflow Guide

- **Supported Blender:** `5.1.2`
- **Release archive:** `Dreadstone_Animation_Forge_v3_16_2.zip`
- **Primary rule:** the artist chooses anatomical surfaces; Forge automates processing, not anatomy.
- **Safety rule:** Source Damage Readiness and `NOT READY` behavior are unchanged and are never bypassed by an orchestrator.

## Fastest beginner route

1. Import the source GLB and save a working `.blend`.
2. Select the character and open **Start / Character**.
3. Choose an explicit readiness output folder and target height, then run **Prepare Character for Damage Authoring**.
4. Open **Damage Authoring**, choose Head, Body, Left Forearm, or Right Forearm, enter Face Edit mode, and select one connected patch.
5. Choose an impact preset and click **Create Impact From Current Selection**.
6. Tune with `FAST` live preview; click **Commit** when the result is ready for final raised-gore construction and focused validation.
7. Open **Validate & Export**, run complete validation, export, and clean-reimport.

The top “Next” card derives its recommendation from current source, readiness, region, capture, key, preview, and validation state. It is guidance, not a validation override.

## 1. Install Dreadstone Animation Forge 3.16.2

In Blender 5.1.2 choose **Edit > Preferences > Add-ons > Install from Disk**, select `Dreadstone_Animation_Forge_v3_16_2.zip` without extracting it, and enable the add-on. A successful install shows version 3.16.2 without a registration error.

## 2. Open the Dreadstone panel

In the 3D Viewport press `N` and open the **Dreadstone** tab. The primary workspaces are:

- **Start / Character** — source preparation dashboard and one safe orchestrator.
- **Damage Authoring** — active context, region buttons, one-click drafts, tuning, preview, Commit/Revert.
- **Animation** — rig analysis, imported pack adoption, drafts, guard Actions, and Approved Pack work.
- **Validate & Export** — focused validation, complete authoring validation, and damage export.
- **Advanced** — every manual, expert, legacy, portable, compound, gore, and diagnostics control.

Panel display reads cached summaries only. Merely opening or redrawing it does not rebuild meshes, solve geodesics, validate geometry, rewrite JSON, create materials, or alter selection.

## 3. Import and prepare a source GLB

Import with **File > Import > glTF 2.0**, save a working `.blend`, and select the character mesh or armature. Set the target height and explicit readiness folder.

Click **Prepare Character for Damage Authoring**. It performs and reports these stages in order:

1. resolve the selected character hierarchy;
2. **Analyze Rig**;
3. measure height and run **Safe Resize** only when the configured target differs;
4. run Source Damage Readiness into the explicit folder;
5. stop immediately when the result is `NOT READY`;
6. load the verified READY handoff;
7. build the protected authoring asset;
8. register and validate existing `head`, `body_core`, `forearm_left`, and `forearm_right` generated regions;
9. recommend the next action.

The summary is stored with the scene. A failed stage is visible and transactional cleanup removes only resources created by that operation. Individual **Analyze Rig**, **Safe Resize**, **Analyze Source Damage Readiness**, **Load READY Handoff**, and **Build Authoring Asset** actions remain in Advanced.

## 4. Create, tune, commit, and revert an impact

In **Damage Authoring**, click a registered region button. Forge activates its managed object; a paired region also shows its detached partner. Enter Face Edit mode and select one connected patch on that active mesh.

Choose the impact family, direction, intensity, and one of Head Left, Head Right, Head Front, Head Back, Body Front, Body Left, Body Right, Body Back, Forearm Outer, or Custom Impact. Presets configure defaults but never select polygons.

Click **Create Impact From Current Selection**. Atomically, Forge validates the region and connected patch, allocates a unique managed key, captures the surface, creates a blunt stamp, applies direction/intensity defaults, attaches the enabled heavy-gore recipe, selects the draft, and produces `FAST` preview. Any required-stage failure restores shape keys, coordinates, metadata, settings, materials, visibility, selection, mode, frame, and owned helpers.

The primary tuning controls are Radius, Depth, Falloff, Impact Direction, Shape, Seam Safety, Gore Amount, Gore Thickness, Gore Breakup, additive Muscle Fiber and Original Gore Color contributions, and Preview Quality.

- `OFF` performs no automatic preview and atomically clears any active damage presentation.
- `FAST` evaluates affected vertices with one reusable temporary key and never builds final raised-gore shells.
- `BALANCED` evaluates the complete stamp stack non-destructively and may use reduced preview feedback after the debounce.
- `FINAL` is explicit final work: permanent deformation, final-budget gore, and focused validation.

Slider changes only mark the recipe dirty, increment a generation token, and schedule one 200 ms main-thread timer. A newer generation invalidates stale work. Use **Commit** for deterministic final output, **Revert** for the stored recipe, **CLEAR DAMAGE PREVIEW** to zero managed morphs, remove temporary stain resources, and hide inactive raised gore as one operation, or **Undo Draft** for an uncommitted one-click draft. Clearing never deletes a stored recipe or generated export mesh.

## 5. Author and approve animation drafts

Open **Animation** at any point in the character, gore, or deformation workflow and select any mesh or armature that belongs to the target character. Animation authoring is not gated by Source Readiness, the active damage region, or whether the target is an imported source rig or generated damage rig. Use **Adopt Imported Animation Pack** when the GLB already contains appropriate Actions.

The restored collapsible sections expose Ground Preview, Rig Mapping & Direction, Arm & Hand Pose Polish, Walk Draft, Death / Collapse Draft, Flank Hurt Drafts, Mace Head-Guard Drafts, Approved Animation Pack, and Action Approval & Safety. Walk, collapse, and hurt retain their primary and advanced creation sliders. Mace guards retain timing controls and now also use the shared rotation-only arm/hand pose-polish sliders. Change the desired values and click the matching **Generate / Refresh** operation to build a disposable custom draft.

Generation never overwrites an imported, approved, or NLA-used Action. Inspect the draft, then use its **Version / Approve** control to preserve it as a new permanent Action. Use **Protect Active DSB Action** for an adopted or manually edited DSB Action that should be export-eligible. A disposable draft is not exported as approved merely because it exists.

## 6. Build and validate an approved animation pack

Choose the pack output directory and filename, then use **Build Approved Animation Pack** and **Validate Last Built Pack**. Guard Actions retain `Brace_Start`, `Guard_Active`, and `Brace_End` markers and their stable Action naming/semantic contracts.

## 7. Run Source Damage Readiness

The Advanced manual route uses **Analyze Source Damage Readiness**. It inspects the preserved original source inventory only. Review Head–Neck, Left Elbow, Right Elbow, and Lower Spine results and the JSON/Markdown reports. Use **Preview Candidate Seam** for inspection.

If the result is `NOT READY`, stop and correct the source outside any guessed-repair path. **Repair Source Readiness Contract** repairs only an eligible stale identity contract from the preserved original; it does not weaken geometry requirements or substitute generated meshes.

## 8. Build Damage Segment and Stump Authoring assets

For the manual route, select the verified report with **Load READY Handoff** and click **Build Authoring Asset**. Forge preserves the original, creates `DSB_DAMAGE_RIG`, `DSB_SOURCE_MODEL_PROTECTED`, body/head/forearm/lower-body pieces, stump caps, and helpers under owned collections.

## 9. Preview intact and detached states

Use **Preview Intact** and **Preview Detached** to inspect cut boundaries and caps. These views are viewport presentation only. The Trauma Field Attached/Detached/Both view does not rewrite render/export visibility.

## 10. Register and validate trauma regions

Prepare Character registers existing standard generated regions automatically. Advanced manual registration remains available through **Register Selected Pair**, **Register Selected Core Mesh**, and **Validate Region**.

- `PAIRED_SEGMENT` requires exact compatible attached/detached topology and uses exact-index world-space delta synchronization.
- `CORE_SINGLE` owns one target mesh and never invents a fake partner.

Use **REPAIR LEGACY PAIR SYNC** only for eligible legacy metadata. For compatibility, missing legacy keys are not recreated and unrepairable attached keys are not overwritten.

## 11. Body, forearm, and compound workflows

For Body, select a connected torso patch on `DSB_BODY_CORE`; Forge rebuilds only that core region. For either forearm, select the intended patch on the attached forearm and inspect exact-index attached/detached variants and elbow seam protection.

For a multi-region injury, use **New Compound Trauma Event**, activate each desired region/key, use **Add Active Region to Event**, then **Capture Shared Impact Field**. Link real seam IDs where appropriate, preview, and run the explicit compound rebuild. All child morphs, stains, and gore nodes activate or clear atomically. `Event Zero` returns every child to the inactive preview state without deleting recipes or generated geometry.

Compound continuity modes retain shared-field locking, blend-across-seam, and seam protection. They are analytical only: there is no Blender mesh merge, weld, or topology mutation.

## 12. Capture a surface with every placement mode

Advanced offers **Capture Single Face**, **Capture Connected Face Patch**, **Capture Selected Vertices**, and **Capture 3D Cursor**. Use face/vertex modes for artist-approved anatomy. Cursor capture is an explicit artist placement, not inferred anatomy.

## 13. Choose influence masks, distance modes, and damage axis

Influence choices remain **Patch Only**, **Patch Feathered**, and **Connected Surface**. Distance choices remain **Surface Distance** and **World Distance**. Direction can follow the surface, semantic presets, or an explicit custom vector. Seam safety remains independently controllable.

## 14. Create and manage trauma stamps

Advanced retains **Add Stamp**, **Update Active Stamp**, **Enable / Disable**, duplicate/remove/reorder controls, exact placement modes, custom vectors, geometry budgets, and recipe metadata. Portable **Save Stamp Library...** and **Load Stamp Library...** retain formats 1–4; they serialize recipes and analytical anchors, never proprietary mesh payloads.

## Surface Gore Overlay for blunt trauma

High-intensity raised gore remains ordinary deterministic mesh geometry, not a flat-decal replacement. The heavy preset refines each selected source face into smaller rounded facets, breaks up straight edges with **Organic Irregularity**, and controls the bulged surface with **Surface Roundness**. **Use Muscle-Fiber Textures** wraps each refined face in one independently selected direction from the packaged texture set; the direction is visual variation and does not claim anatomical alignment.

**Muscle Fiber Contribution** and **Gore Color Contribution** are independent additive sliders. The exportable packed surface texture adds both signals and clamps the final result; increasing one does not replace or proportionally reduce the other.

**Compromised Inner Reddening** adds a second closed barrier just inside the open gore-island edge. Tune **Inner Reddening Width** and **Barrier Compromise** to control the visible band beneath the clot shell.

**Randomize Master Gore Seed** changes the full overlay, not only its texture: stain breakup, selected islands, peripheral fragments, thickness, material classification, organic shape, and fiber directions all derive from the same repeatable seed. Click **Preview / Rebuild Current Gore** after randomizing to see and save the new result.

Use **Create Blunt Gore Head Set**, **Enable Surface Gore Overlay**, **Use Preset Defaults**, **Apply Gore Overlay Settings**, and **Preview / Rebuild Current Gore** in Advanced. **Clear Stain Preview** removes temporary material/attribute feedback and restores original slots exactly. **Apply Heavy Gore to All Deformations**, **Clear Current Generated Gore**, **Rebuild All Generated Gore**, and **Validate Gore Geometry** remain available.

During ordinary tuning, `FAST` avoids final attached/detached shells. Final generation retains stable owned `DSB_GORE_*` nodes, deterministic recipes, tapered raised geometry, glTF-safe materials, triangle budgets, and inactive-by-default runtime activation metadata.

## 15. Preview, rebuild, compare, sculpt, and repair

The default workflow uses managed preview and **Commit**. Advanced retains **REBUILD ACTIVE DEFORMATION**, **Attached**, **Detached**, **Both**, optional sculpt begin/finish, synchronization, **REPAIR LEGACY PAIR SYNC**, and the prior seed preview/rebuild controls. Sculpting is optional and never silently substitutes for recipe state.

## 16. Run every validation command

Focused checks are **Validate Morph Targets**, **Validate Gore Geometry**, **Validate Compound Event**, and **Validate Mace Head-Guard Drafts**. **Validate Complete Damage Asset** is Authoring Validation. It remains separate from Export Validation and does not weaken Source Readiness.

The explicit complete validator may briefly evaluate hidden saved hierarchies so Blender returns their real world matrices after reopen; it restores exact visibility before returning.

## 17. Export the damage GLB and manifest

Set the export folder and filename, then click **Export Damage GLB + Manifest**. Export snapshots the exact Blender preview, temporarily zeros every managed morph, clears stain resources, forces generated gore into its inactive/default export state, exports, and restores the snapshot in a guaranteed cleanup block. Recipes, owned raised-gore nodes, compound mappings, materials, stable IDs, object/morph naming, and inactive runtime activation semantics remain independent of viewport state.

## 18. Clean reimport and verification

Import the exported GLB into a clean scene. Click **Restore Reimported GLB Intact Preview** and verify morph names, attached/detached mappings, core targets, gore nodes/materials, compound activation records, default visibility, and ownership extras. Runtime activation remains outside Forge; the existing Folsom Field contract is unchanged.

## 19. Beginner recipes

- Head blunt impact: Head region → connected face patch → Head direction preset → Medium/Heavy → Create → FAST tune → Commit → inspect Both.
- Body impact: Body region → torso patch → Body direction preset → Create → tune → Commit → validate core target.
- Forearm impact: forearm region → outer patch → Forearm Outer → Create → tune seam safety → Commit → inspect attached/detached.
- Compound impact: create authored child impacts first → new event → add participants → capture shared field → preview → rebuild → validate seam mismatch.

## 20. Troubleshooting and recovery

- Slow slider response: confirm Preview Quality is `FAST`; run **Startup Self-Check** and inspect cache/timer counts.
- `FAILED` preview: the previous valid/clean state is restored. Read the preview message; correct the active region/key/capture before retrying.
- `NOT READY`: inspect the source report. Do not build from generated substitutes or guess-repair seams.
- Wrong selected object: click the region button to activate the managed target before entering Face Edit mode.
- Crash or unexplained slowdown: expand **Advanced > Diagnostics & Crash Support**, choose a folder, run **WRITE FORGE DIAGNOSTIC REPORT**, and attach the JSON/Markdown plus Blender version and exact reproduction steps. Reports omit mesh payloads.
- Duplicate handler/timer suspicion: run **Startup Self-Check**, disable/re-enable once, and include the report if counts do not return to one handler and at most one active preview timer.
- Legacy pair problem: use the guarded repair only when validation identifies an eligible stale pair. Virtual welding remains analytical only and user topology is not changed.

## Advanced compatibility reference

Forge 3.15 preserves public operator IDs, scene/custom-property keys, Source Readiness and authoring schemas, generated `DSB_*` names, portable library formats 1–4, paired/core modes, compound semantics, attached/detached exact-index behavior, seam modes, Action names/markers, and GLB/manifest runtime contracts. Expert controls moved under Advanced; they were not removed.

## Complete public button inventory

The task UI and Advanced workspace together represent every prior public control plus the new orchestrators. Advanced groups its expert controls into remembered collapsible sections so only the workflows you are using occupy vertical space. Its Trauma group is also divided into region, deformation, capture, stamp, gore, compound, and preview/validation foldouts:

- Character/source: **Adopt Imported Animation Pack**, **Safe Resize**, **Analyze Rig**, **Analyze Source Damage Readiness**, **Repair Source Readiness Contract**, **Preview Candidate Seam**, **Load READY Handoff**, **Build Authoring Asset**, **Prepare Character for Damage Authoring**.
- Segment preview/region: **Preview Intact**, **Preview Detached**, **Register Selected Pair**, **Register Selected Core Mesh**, **Validate Region**.
- Capture/influence: **Capture Single Face**, **Capture Connected Face Patch**, **Capture Selected Vertices**, **Capture 3D Cursor**, **Patch Only**, **Patch Feathered**, **Connected Surface**, **Surface Distance**, **World Distance**.
- Stamps/libraries: **Add Stamp**, **Update Active Stamp**, **Enable / Disable**, **Save Stamp Library...**, **Load Stamp Library...**.
- Gore: **Create Blunt Gore Head Set**, **Enable Surface Gore Overlay**, **Use Preset Defaults**, **Apply Gore Overlay Settings**, **Preview / Rebuild Current Gore**, **Clear Stain Preview**, **Apply Heavy Gore to All Deformations**, **Clear Current Generated Gore**, **Rebuild All Generated Gore**, **Validate Gore Geometry**.
- Starters/compound: **Create Body Impact Starters**, **Create Forearm Impact Starter**, **New Compound Trauma Event**, **Add Active Region to Event**, **Capture Shared Impact Field**, **Preview Compound Event**, **Validate Compound Event**.
- Animation creation: **Create Floor**, **Align Pose**, rig bone mapping/direction, rotation-only left/right arm and hand polish, primary/advanced walk sliders, primary/advanced collapse sliders, primary/advanced flank-hurt sliders, **Generate / Refresh** drafts, and per-draft **Version / Approve** controls.
- Guards: **Generate Three Mace Head-Guard Drafts**, **Preview Guard_Active**, **Validate Mace Head-Guard Drafts**.
- Shapes/final: **Compact Dent**, **Broad Cave**, **Flat Compression**, **Directional Shear**, **Raised Impact Rim**, **Ridge Collapse**, **REBUILD ACTIVE DEFORMATION**, **Attached**, **Detached**, **Both**, **REPAIR LEGACY PAIR SYNC**.
- Validation/export: **Validate Morph Targets**, **Validate Complete Damage Asset**, **Export Damage GLB + Manifest**, **Restore Reimported GLB Intact Preview**, **Build Approved Animation Pack**, **Validate Last Built Pack**.
- Managed workflow: **Create Impact From Current Selection**, **Commit**, **Revert**, **CLEAR DAMAGE PREVIEW**, **Undo Draft**, **Final Preview**, **Protect Active DSB Action**, **Delete Unapproved DSB Attempts**, **WRITE FORGE DIAGNOSTIC REPORT**, **Startup Self-Check**.
