# Dreadstone Animation Forge user workflow guide

- **Current Forge version:** `3.13.0`
- **Supported Blender version:** Blender `5.1.2`
- **Current release ZIP:** `Dreadstone_Animation_Forge_v3_13_0.zip`
- **Last updated:** 2026-07-19

This is the authoritative user how-to for the current Forge release. It follows the labels and behavior implemented in the add-on. If an older note, video, or README disagrees with this guide, use this guide.

## Before you begin: five Blender terms

- A **GLB** is one file containing a 3D model and, when present, its rig and animations.
- An **armature** is Blender's skeleton object. Its bones move a skinned character mesh.
- The **active object** is the last object selected. Blender shows it with the brighter selection outline. Some Forge operations care which selected object is active.
- An **Action** is a Blender animation clip. Forge draft Actions are disposable until approved.
- A **shape key** (called a morph target after GLB export) stores an alternate vertex position. `Basis` is the undeformed starting shape.

Save a working copy of the `.blend` before authoring. Forge protects the imported source during damage authoring, but a saved project also makes relative `//` export paths predictable.

> **WARNING**
> Never apply the scale of a Forge safe wrapper such as `DSB_SIZE_ROOT_ADOPTED`. Never animate bone scale. Those operations can invalidate sizing, animation, and exact-index deformation contracts.

## 1. Install Dreadstone Animation Forge 3.13.0

1. Obtain `Dreadstone_Animation_Forge_v3_13_0.zip`.
2. Do not extract the ZIP. It is a Blender extension package whose `blender_manifest.toml` and `__init__.py` are at the ZIP root.
3. Open Blender 5.1.2.
4. Choose **Edit > Preferences > Add-ons**.
5. Open the add-on menu, choose **Install from Disk**, and select the ZIP.
6. Enable **Dreadstone Animation Forge** if Blender does not enable it automatically.
7. Close Preferences. Restart Blender if an older Forge version was loaded in this session.

> **EXPECTED RESULT**
> Blender lists Dreadstone Animation Forge version 3.13.0 and the add-on enables without a registration error.

> **TROUBLESHOOTING**
> If Blender says the package is invalid, confirm that you selected the original ZIP without extracting or rezipping it. If old labels remain after upgrading, restart Blender so no stale add-on module remains loaded.

## 2. Open the Dreadstone panel

1. Put the mouse over the 3D Viewport.
2. Press `N` to open the sidebar.
3. Click the **Dreadstone** tab.
4. Expand the sections you need by clicking their headings.

The one panel is titled **Dreadstone Animation Forge**. Its major sections are **Character Setup**, **Ground Preview**, **Rig Mapping & Direction**, **Source Damage Readiness**, **Damage Segment & Stump Authoring v3.9**, **Trauma Field Authoring v3.13.0**, **Arm & Hand Pose Polish**, **Walk Draft**, **Death / Collapse Draft**, **Flank Hurt Drafts**, **Approved Animation Pack**, and **Action Cleanup & Safety**.

## 3. Import and prepare a source GLB

### Import the source

1. Start with an empty scene when possible. Delete the default cube, camera, and light if they are not part of your project.
2. Choose **File > Import > glTF 2.0 (.glb/.gltf)**.
3. Select the character GLB and finish the import.
4. In Object Mode, select the imported character mesh, its armature, or the imported top-level parent. Press `A` only when the scene contains no unrelated objects.
5. Save the `.blend` as a working project copy.

Forge follows the selected object's parents and children to find the character. It chooses the largest related armature if more than one is found.

### Adopt an existing Forge animation pack

Use this only when the imported GLB is already a Forge animation pack and you want to continue working with its approved animations.

1. Select the imported mesh, armature, or root.
2. Expand **Character Setup**.
3. Click **Adopt Imported Animation Pack**.

Adoption recognizes the pack without resizing it, reuses an imported root or adds the neutral scale-1 wrapper `DSB_SIZE_ROOT_ADOPTED`, resets **Target Height** to 1.500 m, writes `DSB_Rig_Mapping.txt`, creates the preview floor, and recovers applicable non-draft `DSB_` Actions as approved Actions.

> **EXPECTED RESULT**
> The character hierarchy is selected. The status reports its measured height, wrapper choice, rig profile, and number of recovered Actions. A warning names any missing mapped roles.

### Safely resize a source character

Use this when the source needs the project's canonical visible height. Do not use normal transform-apply commands on the rig hierarchy.

1. Select the character mesh, armature, or root.
2. In **Character Setup**, set **Target Height**. The default is 1.500 m.
3. Click **Safe Resize**.

Forge measures the evaluated visible meshes, creates or reuses an outer safe wrapper, scales that wrapper uniformly, and preserves the character's ground reference. It does not apply scale to the mesh or armature.

> **EXPECTED RESULT**
> The message reports old height, final height, target, and scale factor. If already within tolerance, it reports that no scale change was required.

> **TROUBLESHOOTING**
> “No character mesh found” or “No armature found” means the selection does not lead to the imported hierarchy. Return to Object Mode and select the character mesh or armature. Do not include unrelated scene objects.

### Analyze and correct rig mapping

1. Keep the character selected.
2. Click **Analyze Rig** in **Character Setup**.
3. Expand **Rig Mapping & Direction**.
4. If the analyzer reports missing central bones, use the bone pickers **Pelvis / Hips**, **Lowest Spine**, and **Upper Spine / Chest**.
5. Set **Character Faces**. The Testman/Animate Anything default is **-Y (Animate Anything)**; alternatives are **+Y**, **+X**, and **-X**.
6. Leave **Invert Knees** on and **Invert Elbows** off for the accepted Testman profile. Change them only if generated bends go the wrong way.
7. Click **Analyze Rig** again after overrides.

The report is stored in the Blender Text Editor as `DSB_Rig_Mapping.txt`.

> **EXPECTED RESULT**
> The status says the rig is ready to animate or lists the exact missing roles to map.

## 4. Create a floor and align the current pose

**Ground Preview** is optional and preview-only.

1. Set **Preview Floor Size**.
2. Set **Ground Sink**. The default 0.005 m places the lowest visible point slightly below the floor to reduce a floating look.
3. Click **Create Floor** to create or update `DSB_PREVIEW_FLOOR` at world Z=0.
4. Pose or scrub the character to the frame you want to ground.
5. Select the character hierarchy and click **Align Pose**.

**Align Pose** moves only the safe outer wrapper so the current evaluated mesh meets the requested sink. The preview floor is excluded from animation-pack export.

> **EXPECTED RESULT**
> Blender reports the old lowest point, target Z, and wrapper movement.

## 5. Author and approve animation drafts

This workflow is independent of damage morph authoring, but it is part of the same public Forge panel. Generated drafts replace the current draft of the same kind; approved versions are preserved.

### Arm and hand polish

Expand **Arm & Hand Pose Polish** before generating a draft. **Use Arm & Hand Pose Polish** applies rotation-only offsets to newly generated drafts. **Left Arm / Hand** exposes **Left Arm Forward / Back**, **Left Upper-Arm Roll**, **Left Forearm Twist**, **Left Wrist Flex**, **Left Wrist Side Bend**, and **Left Wrist Roll**. **Right Arm / Hand** exposes **Right Arm Forward / Back**, **Right Upper-Arm Roll**, **Right Forearm Twist**, **Right Wrist Flex**, **Right Wrist Side Bend**, and **Right Wrist Roll**.

- Click **Zero Arm & Hand Polish** to reset all twelve sliders.
- Existing Actions are not rewritten merely by moving these controls; regenerate the draft.

### Walk draft

1. Select the character mesh or armature.
2. Expand **Walk Draft**.
3. Choose **Walk Style**: **Normal**, **Heavy**, **Cautious**, **Injured Left Leg**, or **Injured Right Leg**.
4. Set **Cycle Frames**, **Stride**, **Knee Bend**, **Swing Foot Lift**, **Arm Swing**, and **Arm Drop to Sides**.
5. If needed, expand **Advanced Walk Controls** and set **Heel / Toe Roll**, **Elbow Bend**, **Hip Bob**, **Hip Sway**, **Pelvis Twist**, **Chest Counter-Twist**, **Forward Lean**, **Shoulder Sway**, **Head Stability**, and **Step Asymmetry**.
6. Click **Generate / Refresh Walk Draft**.
7. Scrub or play the `DSB_DRAFT_Walk` Action. Adjust controls and regenerate until satisfied.
8. Click **Version / Approve Walk Draft**.

Approval renames the draft to a protected version such as `DSB_Walk_NORMAL_v001`. Future generation creates a fresh draft.

### Death or collapse draft

1. Expand **Death / Collapse Draft**.
2. Choose **Collapse Style**: **Chest-Hold Forward**, **Uncontrolled Faceplant**, or **Knees First**.
3. Set **Duration**, **Pain / Hold Side**, **First Knee to Fail**, **Bracing Arm**, **Arm Drop to Body**, and **Death Wiggle / Thrash**.
4. Optionally expand **Advanced Collapse Controls** for **Knee Buckle**, **Torso Curl**, **Body Drop**, **Forward Travel**, **Body Twist**, **Head Heaviness**, **Fall Left / Right**, **Final Settle**, and **Final Pose Hold**.
5. Click **Generate / Refresh Death Draft**, review it, then click **Version / Approve Death Draft**.

The final pose is held for the requested frames. Approval creates a protected, incremented `DSB_Death_..._v###` Action.

### Left and right flank-hurt drafts

1. Expand **Flank Hurt Drafts**.
2. Set **Reaction Duration**, **Severity**, **Hand Down to Hip / Flank**, and **Torso Bend**.
3. Optionally expand **Advanced Hurt Controls** for **Hand-to-Flank Reach**, **Torso Twist**, **Knee Dip**, **Stagger Distance**, **Head Recoil**, and **Recovery by Final Frame**.
4. Click **Refresh Left** or **Refresh Right** and review the draft.
5. Click **Approve Left** or **Approve Right** for the matching draft.

> **TROUBLESHOOTING**
> A “Missing mapped bones” error means the draft cannot safely pose the requested chains. Run **Analyze Rig**, fill the manual central-bone fields if needed, verify the selected armature, and retry. If regeneration says the draft is used by an NLA strip, remove that disposable draft from the Nonlinear Animation strip before regenerating.

### Protect or clean older Actions

- To protect an older generated Action, make it the selected armature's active Action and click **Protect Active Legacy Action** in **Action Cleanup & Safety**. Its name must begin with `DSB_`.
- Click **Delete Unapproved DSB Attempts** to remove old, unapproved `DSB_` Actions after a confirmation prompt. The active Action, current drafts, approved Actions, and Actions used by NLA strips are retained.

## 6. Build and validate an approved animation pack

Use **Approved Animation Pack** when you want a GLB containing approved animation Actions rather than a damage-authoring asset.

1. Approve at least one walk, death, hurt, or legacy Action.
2. Set **Pack Output Folder**. The default `//exports/` is relative to the saved `.blend`.
3. Set **Pack Filename** without `.glb`.
4. Keep **Auto-Increment Existing Filename** enabled to avoid overwriting an existing GLB.
5. Keep **Bake / Force Sampling** enabled for robust playback unless your pipeline requires otherwise.
6. Click **Build Approved Animation Pack**.
7. Click **Validate Last Built Pack** to reread the GLB and compare its animations with the adjacent manifest.

> **EXPECTED RESULT**
> Forge writes `<name>.glb`, `<name>.json`, and `<name>_validation.json`. A pass reports the animation, mesh, and skin counts. Only approved Actions are included; `DSB_PREVIEW_FLOOR` is excluded.

> **TROUBLESHOOTING**
> “No approved Actions found” means a draft still needs its matching approve button. “No valid Last Pack Path” means no pack was built in this Blender scene or the last file was moved.

## 7. Run Source Damage Readiness

Source Damage Readiness is a non-destructive, pre-authoring inspection of the original imported source. It analyzes skinning, mesh health, and proposed contours for **Head–Neck**, **Left Elbow**, **Right Elbow**, and **Lower Spine**. It does not edit geometry, weights, modifiers, transforms, Actions, or shape keys; it adds only stable source identity metadata.

The corrected order is: run Source Damage Readiness on the original source; build authoring assets; author keys and trauma stamps; run Authoring Validation; run Export Validation; never repair intentional generated segment boundaries to satisfy Source Readiness; and use **Repair Source Readiness Contract** for an affected 3.8 file.

1. In Object Mode, select the original imported character mesh or its armature.
2. Expand **Source Damage Readiness**.
3. Choose an explicit project folder in **Report Output Folder**. A blank value is rejected. An unsaved `.blend` also cannot use a `//` relative path, and a drive root such as `C:\` is rejected.
4. Click **Analyze Source Damage Readiness**.

Forge preserves selection, active object, frame, active Actions, and Object Mode while it analyzes. It writes `<armature>_damage_readiness.json` and `<armature>_damage_readiness.md` and stores `DSB_SOURCE_READINESS_CONTRACT.json` in the `.blend`. The contract records the original armature, mesh objects/datablocks, source collections, bone mapping, topology and relevant-weight fingerprints, analyzer revision/build, and report time.

> **EXPECTED RESULT**
> **Last Results** changes from `NOT ANALYZED`. **Overall** becomes `SOURCE READY` only when skinning is usable, no weight or confirmed topology repair remains, and all four seams are automatic candidates. **Contract** becomes `VALID`.

### Understand the readiness report

- `AUTOMATIC_CANDIDATE`: Forge found one usable closed contour for that seam.
- `MANUAL_REVIEW`: a candidate exists, but a localized contour, topology, or confidence issue requires inspection and correction.
- `MANUAL_REQUIRED`: Forge could not find a usable shell-aware weight contour; weights or a manual loop must be authored outside the automatic workflow.
- `UNAVAILABLE`: required bone, mesh, group, or report data is missing.

Click **Open Markdown** for the readable report or **Open Report Folder** for both files. The JSON is the machine-readable handoff. It contains topology and relevant-weight fingerprints; later authoring refuses to use it if the source changes.

### Preview a candidate seam

1. Choose **Preview Seam**.
2. Click **Preview Candidate Seam**.
3. Inspect cyan selected edges, orange rejected alternatives, endpoint/branch/problem markers, and the joint plane.
4. Click **Clear Preview** when finished.

If original-source topology or relevant weights changed after analysis, the preview is rejected. Rerun **Analyze Source Damage Readiness** to produce a new fingerprinted report.

After authoring begins, an explicit rerun still resolves the registered original source by stable identity. It never substitutes `DSB_BODY_CORE`, `DSB_ATTACHED_*`, `DSB_SEGMENT_*`, `DSB_STUMP_*`, or other generated role objects. If the original is missing or replaced, Forge blocks with a source-identity error instead of analyzing generated meshes.

### Virtual-weld-aware connectivity in plain language

GLB files often contain duplicate vertices at UV, normal, tangent, or material borders even though the surface looks continuous. Forge does not merge or move those vertices: no Blender mesh merge operation occurs. For analysis only, it treats position-coincident copies within a very small world-space tolerance as one *virtual* vertex. Faces count as connected only when they share a complete virtual edge; touching at one corner is not enough. This lets a legitimate visible surface cross imported split seams without hiding real holes or joining nearby but separate surfaces.

> **WARNING**
> A report with **Overall: SOURCE REVIEW** cannot build the protected damage asset. Correct the named weights or localized topology in the original source, then rerun Source Readiness. Do not edit the original mesh after producing the READY report you intend to use. Intentional open boundaries on generated segment meshes are authoring state; do not repair them to satisfy Source Readiness.

## 8. Build Damage Segment and Stump Authoring assets

This workflow consumes a current READY report and builds on copies. The imported source is hidden and protected, not cut in place.

1. Return to Object Mode.
2. Expand **Damage Segment & Stump Authoring v3.9**.
3. Set **READY Report JSON** to the readiness JSON. If readiness was run in this scene, leaving this field blank uses the last report path stored by the analyzer.
4. Click **Load READY Handoff**.
5. Confirm the status is `READY HANDOFF LOADED`.
6. Click **Build Authoring Asset**.

No special object selection is needed at this stage: Forge resolves the exact original mesh and armature from source contract `dreadstone.source_readiness.v1`, then verifies topology and weight fingerprints. The report must use schema `dreadstone.damage_readiness.v1`, revision `virtual_weld_v3.7.4`, be overall READY, and contain one closed `AUTOMATIC_CANDIDATE` for every required seam.

Forge creates these protected/generated objects:

- Core and rig: `DSB_DAMAGE_RIG`, `DSB_SOURCE_MODEL_PROTECTED`, `DSB_BODY_CORE`, and `DSB_SOCKET_ABDOMEN_VISCERA`.
- Attached regions: `DSB_ATTACHED_HEAD`, `DSB_ATTACHED_FOREARM_L`, and `DSB_ATTACHED_FOREARM_R`.
- Detached regions: `DSB_SEGMENT_HEAD`, `DSB_SEGMENT_FOREARM_L`, `DSB_SEGMENT_FOREARM_R`, `DSB_SEGMENT_UPPER_BODY`, and `DSB_SEGMENT_LOWER_BODY`.
- Caps: `DSB_STUMP_NECK_TORSO`, `DSB_STUMP_NECK_HEAD`, `DSB_STUMP_ELBOW_L_UPPER`, `DSB_STUMP_ELBOW_L_LOWER`, `DSB_STUMP_ELBOW_R_UPPER`, `DSB_STUMP_ELBOW_R_LOWER`, `DSB_STUMP_WAIST_LOWER`, and `DSB_STUMP_WAIST_UPPER`.

They are organized beneath `DSB_DAMAGE_AUTHORING` with protected, intact, detached, stump, and helper collections. Detached pieces are rigid props; attached pieces remain skinned. Caps use `DSB_INTERIOR_WOUND_MAT`.

> **EXPECTED RESULT**
> Status becomes `BUILT — INTACT PREVIEW`, and Forge reports how many authoring objects it built. The source is hidden and the intact copied body is visible.

> **TROUBLESHOOTING**
> A source fingerprint mismatch means original topology or seam-related weights differ from the report. Generated cuts, keys, and stamps do not cause this mismatch. Restore or correct the named original source, rerun **Analyze Source Damage Readiness**, and use the new JSON. If Blender is in Edit or Sculpt Mode, switch to Object Mode before building.

Click **Clear Generated Asset / Restore Source** to delete only Forge-generated damage objects and show the original source again. This is the safe way to abandon or rebuild the authoring asset.

### Repair an affected 3.8 source contract without losing authored work

Use **Repair Source Readiness Contract** when a 3.8 `.blend` already contains generated authoring meshes and deformation work, but a later bad readiness report lists `DSB_BODY_CORE` or `DSB_ATTACHED_*` as `analyzed_object_names`.

1. Open a backup copy of the affected `.blend` in Object Mode. Do not clear or rebuild the authoring asset.
2. Expand **Source Damage Readiness** and choose a valid project **Report Output Folder** if one is not already available.
3. Click **Repair Source Readiness Contract**. No generated mesh selection is required.
4. Confirm the message names the original imported source and says authoring meshes and deformations were unchanged.
5. Open the repaired JSON and confirm `source_contract.analyzedObjectNames` contains the original source, never `DSB_BODY_CORE` or `DSB_ATTACHED_*`.
6. Confirm the four head-impact keys and their trauma stamps still exist, then run **Validate Morph Targets**.
7. Run **Validate Complete Damage Asset**, then **Export Damage GLB + Manifest**.

Repair locates the preserved original from authoring-state metadata, reruns source-only analysis, and replaces only the source report/contract references. It does not delete or rebuild generated segments, cut boundaries, deformation keys, stamp recipes, preview state, or Actions. If the original source object is actually missing or its topology/weights changed, repair blocks and names the source problem.

## 9. Preview intact and detached states

1. In **Damage Segment & Stump Authoring v3.9**, click **Preview Intact**. This shows `DSB_BODY_CORE` plus the three attached regions and hides detached props, caps, socket, and protected source.
2. Choose **Detached Preview Seam**: **Head–Neck**, **Left Elbow**, **Right Elbow**, or **Lower Spine**.
3. Click **Preview Detached**. Forge shows the appropriate detached piece and both sides of the cut. Lower Spine also uses the abdomen socket and upper/lower body pieces.
4. Return to **Preview Intact** before judging the normal assembled appearance.

> **EXPECTED RESULT**
> Intact mode has a complete head and both forearms with no stump visible. Detached mode exposes only the requested damage presentation.

The **Intact Seam Tolerance** defaults to 0.000500 m and controls how much boundary/cap deviation **Validate Complete Damage Asset** accepts. Increase it only when the project has an intentionally justified tolerance; it is not a repair tool.

## 10. Register and validate deformation pairs

Trauma Field authoring always works through an explicit pair: an attached mesh used by the intact body and its exact-topology detached counterpart. Both must have matching vertex count, polygon count, polygon indices, and loop order so Forge can copy deformation deltas by the same vertex index.

### Register a pair

1. In Object Mode, select exactly two mesh objects.
2. Select the detached object first.
3. Shift-select the attached object last so the attached object is active (brighter outline).
4. Expand **Trauma Field Authoring v3.13.0**.
5. In **New Region ID**, enter a unique semantic name such as `head`, `forearm_left`, or `forearm_right`.
6. In **Related Seam ID**, enter the matching seam ID: `head_neck`, `left_elbow`, `right_elbow`, or `lower_spine`.
7. Click **Register Selected Pair**.
8. Select it in **Active Region** and click **Use Selected Region**.
9. Click **Validate Pair**.

Common pairs are:

| Region | Attached object (active at registration) | Detached object |
| --- | --- | --- |
| `head` | `DSB_ATTACHED_HEAD` | `DSB_SEGMENT_HEAD` |
| `forearm_left` | `DSB_ATTACHED_FOREARM_L` | `DSB_SEGMENT_FOREARM_L` |
| `forearm_right` | `DSB_ATTACHED_FOREARM_R` | `DSB_SEGMENT_FOREARM_R` |

> **EXPECTED RESULT**
> The region line shows `attached ↔ detached`, topology `PASS`, matching counts, and `REGION VALID`. The validation message says it validated an exact-index region.

> **TROUBLESHOOTING**
> “Select exactly two mesh objects” means an armature, Empty, cap, or extra mesh is selected. “Intended attached object active” is solved by deselecting, selecting detached first, then Shift-selecting attached. A topology failure cannot be bypassed; build a correct matching pair.

**Remove Registration** asks for confirmation and removes only the registry entry. It does not delete shape keys or mesh data. Use it to correct a mistaken pair, then register the correct objects.

## 11. Create and select deformation shape keys

1. Activate a validated region.
2. Enter a unique **New Key Name** such as `Head_Impact_Left_v001` or `Forearm_Impact_L_v001`.
3. Click **Create Damage Shape Key**.
4. Click the key's name in **Active Deformation** to select it. The value slider previews its runtime weight; **Solo** sets that key to 1 and other managed keys to 0.

**Create Standard Head Set** is available only for region `head`. It creates paired `Head_Dent_Left`, `Head_Dent_Right`, `Head_Cave_Front`, and `Jaw_Displaced` keys. **Mirror Active** creates or updates the active key's local-X topology mirror and synchronizes it to the detached object. **Zero All** sets every shape-key preview weight to zero. **Delete Active** confirms and then deletes only that Forge-managed key from both objects.

> **WARNING**
> If a non-Forge shape key already uses the requested name, Forge refuses to take it over. Choose another name. Shape keys belong to a registered pair; switching regions clears the active key, stamp, and capture selection.

## 12. Capture a surface with every placement mode

A capture records where a stamp belongs. It includes the active region, attached object, topology, selection, center, normal, and safety hashes. Changing topology or switching regions makes the old capture stale; recapture it.

### Single Face

1. Make the active region's attached object active.
2. Press `Tab` for Edit Mode and enable Face Select.
3. Select exactly one face.
4. Set **Placement Mode** to **Single Face**.
5. Click **Capture Single Face**. Forge returns to Object Mode.

Use it for a precise, small impact seed.

### Selected Face Patch

1. Make the attached object active, enter Edit Mode, and enable Face Select.
2. Select one continuous group of faces. For a head impact, 30–80 faces is a practical visual starting point, not a hard requirement.
3. Set **Placement Mode** to **Selected Face Patch**.
4. Click **Capture Connected Face Patch**.

Use it when the affected area should be explicitly art-directed. Forge accepts one virtual-edge-connected component. A real second island or corner-only contact is rejected.

### Selected Vertices

1. Make the attached object active, enter Edit Mode, and enable Vertex Select.
2. Select one or more vertices with adjacent faces.
3. Set **Placement Mode** to **Selected Vertices**.
4. Click **Capture Selected Vertices**.

Forge uses their average center and the area-weighted normals of adjacent faces. Use this for narrow ridges or exact vertex-level placement.

### 3D Cursor

1. In Object Mode, place Blender's 3D Cursor at the desired point with the Cursor tool or `Shift`+right-click.
2. Set **Placement Mode** to **3D Cursor**.
3. Click **Capture 3D Cursor**.

Forge records the cursor and chooses the nearest attached-mesh vertex as the surface seed. The direction is radial from the object's bounding-box center. This is useful for quick placement and diagnosis, but a face or vertex capture gives a true local surface normal.

> **EXPECTED RESULT**
> **Surface Capture** reports captured face/vertex counts. Face captures also report one virtual seam component and their virtual-weld members.

> **TROUBLESHOOTING**
> If capture asks you to make the attached object active, use **Attached**, then select that object and enter the requested Edit selection mode. If it reports disconnected islands, deselect the separate island; a visual UV/material split should still connect when full virtual edges coincide.

## 13. Choose influence masks, distance modes, and damage axis

Choose these before **Add Stamp** or **Update Active Stamp**; they become part of the stored stamp recipe.

### **Influence Mask**

- **Patch Only**: only captured vertices can move. Use for a hard, exact selection boundary.
- **Patch Feathered**: captured vertices receive full influence and Forge fades across connected edges by **Feather Distance**. This is the best general starting point for a selected patch.
- **Connected Surface**: influence spreads from the captured seeds across reachable surface edges within **Seed Radius**. Use for a naturally expanding field.

### **Distance Mode**

- **Surface Distance** measures the shortest path along world-length mesh edges. Zero-cost links join virtual duplicates at legitimate imported GLB split seams. It follows the surface and avoids jumping through a thin head or arm.
- **World Distance** measures a straight 3D radius from the capture center. Use it for compatibility or diagnosis; it can affect spatially close vertices on an opposite surface.

### Damage Axis and safeguards

**Damage Axis** choices are **Inward Surface Normal**, **Outward Surface Normal**, **+X**, **-X**, **+Y**, **-Y**, **+Z**, **-Z**, and **Custom Vector**. The X/Y/Z choices are local to the attached object. **Custom Direction** appears only for **Custom Vector**.

- **Seed Radius** sets reach.
- **Seed Depth** sets the base displacement amount.
- **Falloff Exponent** shapes how quickly influence fades.
- **Stamp Strength** multiplies the family effect.
- **Seam Protection** fades the effect near the related approved cut contour.
- **Maximum Displacement** clamps the accumulated vertex displacement and is validated.

## 14. Create and manage trauma stamps

1. Select a managed deformation key and make a valid capture.
2. Set **Stamp Name**, **Trauma Family**, capture/mask/distance controls, radius, depth, falloff, strength, axis, seam protection, and maximum displacement.
3. Click **Add Stamp**. This snapshots the current settings into a new stable stamp ID.
4. Click a numbered stamp row to make it active and load its settings.
5. After editing controls, click **Update Active Stamp**. Moving sliders alone does not rewrite the stored recipe.
6. Use **Duplicate** to copy it with a new stable ID, **Move Up** or **Move Down** to change evaluation order, **Enable / Disable** to keep it in the recipe without applying it, and **Remove** to delete it from the stack.

Order can matter because each enabled stamp is applied to the result of the previous stamp. IDs survive reordering; duplication intentionally creates a new ID.

### Save stamps for a rebuild or Forge upgrade

**Save Stamp Library...** writes every procedural stamp stack in every registered deformation region to one portable `.dsbstamps.json` file. It preserves deformation-key names, stamp names and stable IDs, order, enabled state, trauma family, surface capture, influence and distance modes, radius, depth, falloff, strength, seam protection, displacement limit, damage direction, and each key's optional Surface Gore Overlay recipe. It saves recipes rather than source geometry, generated meshes, preview materials, or Source Readiness reports.

1. Save the current `.blend` as a backup.
2. In **Trauma Field Authoring v3.13.0**, click **Save Stamp Library...**.
3. Choose a project folder and filename. Forge adds `.dsbstamps.json` when needed.
4. Keep this small JSON file beside the source GLB or in source control.

This save operation works from a generated or cleanly reimported Forge Damage GLB as long as its procedural stamp metadata and exact attached/detached pair remain present. The original imported source objects and Source Readiness contract are not required merely to save the stamp library.

> **EXPECTED RESULT**
> Forge reports the number of saved deformation keys and stamps. For four one-stamp head impacts, it reports four keys and four stamps.

### Load stamps into a fresh authoring rebuild

First import the same source GLB, run Source Damage Readiness, build the Damage Authoring asset, and register the same deformation regions. Do not manually recreate the saved deformation keys.

1. Confirm each destination pair passes **Validate Pair**.
2. Click **Load Stamp Library...** and select the saved `.dsbstamps.json` file.
3. Forge first looks for the same region ID and exact topology. If GLB export/import or a compatible Forge rebuild changed only split vertices or indices, it can rebind the saved capture through analytical local-space or world-space positional anchors. Every anchor must match within `max(0.000001, local_bounds_diagonal × 0.000002)`; saved faces must still resolve as exact positional faces.
4. Forge creates the missing deformation keys, rebinds captures and optional gore linkage to the current attached object, rebuilds every enabled stack from `Basis`, synchronizes its detached partner by exact vertex index in world space, and runs **Validate Morph Targets**.
5. Select each restored key, click **Solo**, and compare **Attached**, **Detached**, and **Both**.

> **WARNING**
> A stamp capture remains surface-bound. Forge accepts exact topology or conservatively coincident positional anchors; it deliberately refuses closest-point, nearest-neighbor, or guessed remapping when the actual surface changed. It also never overwrites a different existing key or stamp stack. Delete or rename a conflicting destination key only after confirming it is disposable.

> **TROUBLESHOOTING**
> “Does not analytically match” means at least one saved vertex/face anchor moved beyond the conservative tolerance. Rebuild from the same source and compatible Damage Authoring settings/version, or recapture the stamp manually. “Keys already contain different work” means the destination is not clean; save that work separately before deleting or renaming it.

### The six trauma families

- **Compact Dent**: a localized depression with a tighter weighted center. Use for a focused blunt strike.
- **Broad Cave**: a wider, softer inward collapse. Use as the broad foundation of a large impact.
- **Flat Compression**: moves influenced points toward an impact plane instead of translating them uniformly. Use for a flattened forearm or body contact.
- **Directional Shear**: pushes along the selected axis. Use sparingly for glancing or dragged damage.
- **Raised Impact Rim**: produces a restrained raised ring around roughly the outer impact area. Layer it after a dent or cave.
- **Ridge Collapse**: pushes a protruding or curved ridge inward, weighting stronger protrusion. Use on brows, jaw edges, or limb ridges.

## 15. Preview, rebuild, compare, sculpt, and repair

### Preview and rebuild

- **Preview Active Stamp** evaluates only the selected stamp into temporary key `__DSB_DEFORMATION_SEED_PREVIEW`; it does not change the permanent key.
- **Clear Temporary Preview** deletes that uncommitted preview.
- **REBUILD ACTIVE DEFORMATION** starts from `Basis`, replays all enabled stamps in numbered order, clamps displacement, writes the permanent attached key, transfers same-index world-space deltas to the detached key, validates, clears temporary preview, and solos the result.

> **EXPECTED RESULT**
> The message reports the key name and stamp count, validation is `PASS`, and repeating rebuild with unchanged Basis and recipe produces the same result without drift.

When a key has no stamps, the legacy box appears. **BUILD ACTIVE PRESET**, **Preview Legacy Seed**, and **Commit Legacy Seed** preserve the v3.9.1/Testman starting workflow. They create legacy/manual geometry, not a modern editable stamp stack.

### Compare Attached, Detached, and Both views

1. Set the active key to a visible value or click **Solo**.
2. Click **Attached** to show and activate the intact-region object.
3. Click **Detached** to show and activate the detached prop.
4. Click **Both** to overlay the pair and look for divergence.
5. Return to **Preview Intact** in Damage Authoring when you want the full intact damage asset again.

These three buttons clear viewport blockers only along the active pair's generated DSB collection path. Trauma Field inspection does not rewrite render/export visibility and does not alter caps, sockets, `dsb_default_visible`, or other damage segments.

### Optional sculpt and synchronization

1. Select a managed key.
2. Click **Begin Sculpt**. Forge solos the key, activates the attached mesh, and enters Sculpt Mode.
3. Sculpt without changing topology. Do not remesh, subdivide, delete, or add vertices.
4. Click **Finish Sculpt & Sync**. Forge returns to Object Mode, copies exact-index world-space deltas to the detached key, records the key as externally sculpted, and validates limits.

### Repair a stale legacy pair

Use **REPAIR LEGACY PAIR SYNC** only when **Validate Morph Targets** reports a stale Forge-managed legacy attached/detached mismatch. The attached key is treated as authoritative only when topology passes, both exact keys and Basis exist, values are finite, and the attached displacement stays within its declared maximum.

1. Select the affected **Active Region** and click **Use Selected Region**.
2. Click **REPAIR LEGACY PAIR SYNC**.
3. Read the healthy, repaired, skipped, and unrepairable counts.
4. Click **Validate Morph Targets**.

Healthy keys keep their geometry and regain their detached value driver. Safe stale detached keys are rebuilt by matching vertex index in world space. Procedural stamp stacks, missing keys, arbitrary unmanaged keys, and unsafe keys remain unchanged. Forge never recreates an intentionally missing key and never overwrites an unrepairable attached key.

## Surface Gore Overlay for blunt trauma

Surface Gore Overlay is an optional authoring layer for a caved-in or crushed outer surface. It never cuts a hole, reveals anatomy, opens a cavity, deletes skin/scalp/hair/clothing, changes seam geometry, or requires a texture atlas. The original fully deformed exterior remains intact beneath both gore layers.

The **Surface Stain** is a thin, broken color mask on the original exterior. It extends slightly beneath and beyond the clots, but retains clean gaps. Forge previews it with `DSB_Surface_Gore_Mask` and temporary copies of the source materials. **Clear Stain Preview**, selecting another key, deleting the key, or exporting restores the source material slots exactly.

The **Raised Gore** layer is ordinary managed mesh geometry above the intact surface. Deterministic face selection combines the linked stamp influence, actual deformation displacement, distance from the impact core, and seeded multi-scale breakup. Selected islands become closed thin shells with varying top height and rough boundary walls. Dense displaced cores become thick clots/folds; the rim becomes broken medium clumps; the outside retains sparse fragments and substantial clean exterior.

Each recipe produces matching `DSB_GORE_ATTACHED_*` and `DSB_GORE_DETACHED_*` objects. Attached shells copy source vertex groups and Armature linkage; detached shells follow the equivalent exact-index deformed target. The three glTF-safe Principled material roles are wet crimson, dark clot, and rough clot edge. They use zero Metallic and no emission.

### Exact click-by-click workflow

1. Register the head attached/detached pair and select the `head` region as described above.
2. Click **Create Blunt Gore Head Set** to create `Head_Impact_Left_v001`, `Head_Impact_Right_v001`, `Head_Impact_Front_v001`, and `Head_Impact_Back_v001`. You can instead create any future blunt-impact key with **Create Damage Shape Key**.
3. Click one impact key so it is the active deformation.
4. Select the intended surface on the attached mesh and use **Capture Single Face**, **Capture Connected Face Patch**, **Capture Selected Vertices**, or **Capture 3D Cursor**. A connected face patch generally gives the clearest bounded head-impact mask.
5. Configure a blunt trauma family, click **Add Stamp**, select that numbered stamp, and click **REBUILD ACTIVE DEFORMATION**. Confirm that the head caves in while the exterior remains closed.
6. Expand **5. Surface Gore Overlay** and check **Enable Surface Gore Overlay**.
7. Choose `Gore_Crush_Heavy_Clotted` under **Gore Preset**, then click **Use Preset Defaults**. It is the recommended high-intensity blunt-impact preset. The five 3.12 stain presets remain lighter alternatives.
8. Under **Surface Stain**, tune **Stain Coverage**, **Stain Breakup**, and **Edge Feather**. Under **Raised Gore**, keep **Enable Raised Gore** checked and tune **Clot Coverage**, **Core Density**, **Clot Thickness**, **Thickness Variation**, **Island Breakup**, **Peripheral Fragments**, **Surface Offset**, **Geometry Density**, and **Maximum Triangles**. Under **Material Variation**, tune wetness variation, dark-clot bias, rough-edge bias, and color intensity. **Variation Seed** deterministically recreates both stain and shell breakup.
9. Click **Apply Gore Overlay Settings**. Forge stores one overlay recipe on the active deformation and links it to the currently selected stamp ID, region ID, capture hash, and capture topology.
10. Click **Preview / Rebuild Current Gore**. Forge refreshes the temporary stain and regenerates two ordinary raised meshes from the fully deformed paired targets. The status and saved recipe show attached/detached triangle counts.
11. Click **Attached**, **Detached**, and **Both**. Confirm each shell hugs its matching surface, does not expose a seam, and switches with the intended paired view.
12. If you change thickness, breakup, density, seed, capture, stamp, deformation geometry, or pairing, click **Apply Gore Overlay Settings**, then **Preview / Rebuild Current Gore**. A stale digest is a validation failure until rebuild.
13. Check **Preserve as User-Customized** only when the batch action must leave this key unchanged.
14. Click **Validate Gore Geometry**, then **Validate Morph Targets**. Require deformation, stain-overlay, raised-gore geometry, and export status to pass.
15. Click **Save Stamp Library...**. Portable format v3 stores the recipe, seed, linkage, customization flag, and digest but never generated mesh bytes. **Load Stamp Library...** accepts v1/v2/v3, migrates 3.12 overlay records to stain-only, and reproducibly rebuilds enabled raised v3 recipes.
16. Run **Validate Complete Damage Asset**, then **Export Damage GLB + Manifest**. Export removes temporary stain resources but retains ordinary raised meshes and their glTF-safe materials.

### Apply the heavy preset to every deformation

1. Ensure every intended key has at least one enabled stamp with a valid current capture and a rebuilt deformation.
2. Leave **Default New Impacts to High-Intensity Gore** enabled if the first stamp added to future keys should receive the heavy recipe automatically.
3. Click **Apply Heavy Gore to All Deformations**. Forge iterates every registered region, not just `head`, links the heavy recipe to a valid enabled stamp, builds attached/detached shells, preserves keys explicitly marked user-customized, and reports applied/skipped/failed counts. Invalid keys are reported without recipe mutation.
4. Use **Rebuild All Generated Gore** after a compatible global authoring change. Use **Clear Current Generated Gore** to remove only the active key's Forge-owned shell objects while retaining its recipe. Never delete similarly named data by wildcard outside Forge.

> **EXPECTED RESULT**
> A blunt impact remains a closed recognizable exterior. Dense raised clots and ridges occupy the displaced core; broken dark/wet islands and rough edges surround it; clean skin/hair/clothing gaps remain. Attached and detached variants agree. Saving/reopening the `.blend` preserves ordinary generated meshes; portable save/load reproducibly regenerates them.

> **TROUBLESHOOTING**
> Missing/wrong owners, changed deformation/stamp/capture/topology/pairing, altered generated vertices, removed materials, unsupported nodes, missing skinning, excessive offset, floating geometry, empty/degenerate/duplicate/non-manifold faces, default-visible/export-preview flags, and triangle limits fail raised-gore validation. Correct the named input and rebuild. If the result looks inflated, raise **Island Breakup**, lower **Clot Coverage**, or lower **Clot Thickness**. If it floats, restore the heavy **Surface Offset** and rebuild. Budget warnings are resolved by lowering **Geometry Density** or **Maximum Triangles**, not by flattening the system into a decal.

## 16. Run every validation command

Forge displays three different domains: **Source Readiness** describes only the original imported asset; **Authoring Validation** describes generated pieces, pairs, keys, stamps, and caps; **Export Validation** requires both contracts and verifies export preparation. Run them in this order for a complete project:

1. **Analyze Rig** — confirms required humanoid roles for animation generation.
2. **Analyze Source Damage Readiness** — writes the original-source health, stable identity contract, and four-seam handoff; all seams must be `AUTOMATIC_CANDIDATE` for protected auto-authoring.
3. **Load READY Handoff** — validates the schema, analyzer revision, READY state, closed contours, and current source fingerprints.
4. **Validate Pair** — checks exact attached/detached topology for the active deformation region.
5. **Validate Gore Geometry** — separately checks raised-gore node ownership, stable names/IDs, current recipe/input/mesh digests, capture linkage, attached/detached roles, closed non-degenerate geometry, surface distance, skinning, three material assignments, supported glTF nodes, inactive state, and per-key/asset triangle budgets.
6. **Validate Morph Targets** — checks every registered region, managed key pairs, finite coordinates, stored captures, stamp recipes, displacement limits, paired world-space delta equality, stain-overlay linkage/digest, raised-gore geometry, and export mapping.
7. **Validate Complete Damage Asset** — runs Authoring Validation: it verifies the existing source contract, generated pieces, cap topology/material/direction, skinning/rig targets, complete non-overlapping partitions, contour gaps against **Intact Seam Tolerance**, deformation pairs, keys, enabled stamps, and raised gore.
8. **Validate Last Built Pack** — when using the animation-pack workflow, rereads the last GLB and compares its animation inventory with its manifest.

**REBUILD ACTIVE DEFORMATION** validates after rebuilding. **Finish Sculpt & Sync** validates after synchronization. **Export Damage GLB + Manifest** runs Export Validation against the saved source contract and generated authoring state, so a failing asset is not exported. Export does not rerun full Source Damage Readiness and does not overwrite its JSON or Markdown report.

> **WARNING**
> A validation error is a stop condition, not a cosmetic warning. Fix or recapture the named item and rerun the same validation before export. A procedural deformation key whose complete stamp stack is disabled fails Authoring/Export Validation; enable at least one intended stamp or remove the invalid procedural key.

## 17. Export the damage GLB and manifest

1. Return to Object Mode.
2. Click **Clear Temporary Preview** if a stamp preview exists. **Clear Stain Preview** is optional because export safely performs the same temporary stain cleanup. Do not clear generated gore: its ordinary meshes are part of the export contract.
3. Run **Validate Morph Targets** and require `PASS`.
4. In **Damage Segment & Stump Authoring v3.9**, run **Validate Complete Damage Asset** and require `PASS`.
5. Set **Damage Export Folder**. If blank in a saved `.blend`, Forge uses `//damage_exports/`. An unsaved `.blend` requires an explicit folder. A drive root is rejected.
6. Set **Damage Asset Filename** without an extension.
7. Click **Export Damage GLB + Manifest**.
8. Click **Open Damage Export Folder**.

> **EXPECTED RESULT**
> Forge reports “Exported `<name>.glb` and validated manifest.” The folder contains `<name>.glb`, `<name>.json`, and `<name>_validation.json`. The manifest uses `dreadstone.damage_authoring.v1` with additive `dreadstone.damage_deformation.v1` data. Each raised recipe records preset/intensity, region and deformation ownership, stamp/capture linkage, stain and shell settings, seed, recipe digest, stable mesh IDs/node names, pair role, materials, triangle counts, generation/geometry digests, and validation status. `generatedGoreMeshes` provides the flat runtime node map.

The panel shows **Source Readiness: VALID**, **Authoring Validation: PASS**, and **Export Validation: PASS**. Export includes generated gore as ordinary mesh nodes and exports object extras plus three Principled material roles; it excludes the protected source copy and temporary stain materials/attributes. The manifest contract sets `defaultVisible: false`, `undamagedState: INACTIVE`, and identifies the matching deformation key plus activation weight. Folsom Field must keep the node inactive before impact, activate it with that deformation state, and retain it through death/corpse persistence. Forge 3.13 does not implement that game runtime behavior and does not use zero-scale hiding.

## 18. Clean reimport and verification

1. Save and close the authoring file.
2. Start a new empty Blender scene.
3. Choose **File > Import > glTF 2.0 (.glb/.gltf)** and import the exported damage GLB.
4. Open the **Dreadstone** panel and expand **Damage Segment & Stump Authoring v3.9**.
5. Click **Restore Reimported GLB Intact Preview**. No object selection is required.
6. Confirm that `DSB_BODY_CORE`, `DSB_ATTACHED_HEAD`, `DSB_ATTACHED_FOREARM_L`, and `DSB_ATTACHED_FOREARM_R` form a complete intact body.
7. Confirm detached pieces, stump caps, and `DSB_SOCKET_ABDOMEN_VISCERA` are hidden.
8. Inspect the imported mesh morph targets and confirm expected names and visible behavior.
9. Confirm every manifest `generatedGoreMeshes[].nodeName` exists as a non-empty imported Mesh, keeps three gore materials, and retains stable ownership extras when the importer preserves glTF extras.
10. Confirm the manifest says every gore node is inactive by default and activates with its matching deformation. The clean scene has no authoring-only stain material or `DSB_Surface_Gore_Mask` dependency.
11. Open `<name>_validation.json` and require `"status": "PASS"`; inspect `<name>.json` for the expected registered regions, deformation keys, and attached/detached gore roles.

The restore button enables Mesh visibility in open 3D Views, unhides the imported default-visible body pieces, hides tagged helpers/detached objects, selects and frames the intact meshes, and does not require the original authoring-state text.

> **TROUBLESHOOTING**
> If only the orange socket sphere appears after import, click **Restore Reimported GLB Intact Preview**. If it reports that no Damage GLB objects were found, confirm that you imported the Forge damage GLB rather than the source or animation-pack GLB.

## 19. Beginner recipes

### Recipe: create a layered head impact

1. Build the damage authoring asset and register `DSB_ATTACHED_HEAD` (active) with `DSB_SEGMENT_HEAD` as region `head`; click **Validate Pair**.
2. Create key `Head_Impact_Left_v001` with **Create Damage Shape Key**.
3. On `DSB_ATTACHED_HEAD`, select a connected temple patch in Edit Mode. Choose **Selected Face Patch**, **Patch Feathered**, and **Surface Distance**, then click **Capture Connected Face Patch**.
4. Add a **Broad Cave** with **Inward Surface Normal** for the wide base.
5. Reduce **Seed Radius**, add a **Compact Dent** for the focused center.
6. Add a subtle **Raised Impact Rim** using the same or a slightly wider capture.
7. Optionally add a low-strength **Directional Shear** along a suitable local axis.
8. Select each stamp after edits and click **Update Active Stamp**.
9. Click **REBUILD ACTIVE DEFORMATION**, then **Attached**, **Detached**, and **Both**.
10. Run **Validate Morph Targets**.

### Recipe: build heavy clotted gore on all four head impacts

1. Click **Create Blunt Gore Head Set**, then finish one valid capture/stamp and **REBUILD ACTIVE DEFORMATION** for each of the four `Head_Impact_*_v001` keys.
2. Click **Apply Heavy Gore to All Deformations**. Read the applied/skipped/failed summary; no head key may fail.
3. Select each key and click **Preview / Rebuild Current Gore**. Use **Attached**, **Detached**, and **Both** to inspect placement.
4. For the left impact, look for reference-level density and thickness without an open head: multiple dark maroon clots, wet crimson highlights, rough broken edges, small-scale shadowing, and clean recognizable hair/skin gaps. Require the same intensity localized to the front, right, and back keys.
5. Read the attached/detached triangle counts. Lower **Geometry Density** if a key approaches **Maximum Triangles**; retain thickness and material variation rather than replacing the shell with a flat decal.
6. Run **Validate Gore Geometry**, **Validate Morph Targets**, and **Save Stamp Library...**. Clear the current generated gore, rebuild it, and confirm deterministic names/counts/digests before export.

### Recipe: create a left forearm impact

1. Register `DSB_ATTACHED_FOREARM_L` (active) with `DSB_SEGMENT_FOREARM_L` as `forearm_left`, related to `left_elbow`; click **Validate Pair**.
2. Create `Forearm_Impact_L_v001`.
3. Select a connected patch on `DSB_ATTACHED_FOREARM_L`, then use **Selected Face Patch**, **Patch Feathered**, **Surface Distance**, and **Capture Connected Face Patch**.
4. Add **Flat Compression** with an inward axis. Keep **Seam Protection** high enough to avoid disturbing the elbow contour.
5. Optionally layer a small **Compact Dent**.
6. Click **REBUILD ACTIVE DEFORMATION**, compare **Attached**, **Detached**, and **Both**, then run **Validate Morph Targets**.

### Recipe: carry four head stamps into a clean source rebuild

1. Open the old generated/reimported Damage `.blend` that still contains the four head-impact keys and stamps.
2. Expand **Trauma Field Authoring v3.13.0** and click **Save Stamp Library...**. Confirm the message says four keys and four stamps.
3. Start a new `.blend`, import the same original source GLB, and run **Analyze Source Damage Readiness**.
4. Run **Load READY Handoff** and **Build Authoring Asset**.
5. Register `DSB_ATTACHED_HEAD` with `DSB_SEGMENT_HEAD` as region `head`, then require **Validate Pair** to pass.
6. Do not create the old impact keys manually. Click **Load Stamp Library...** and choose the saved file.
7. Require the load report and **Validate Morph Targets** to pass.
8. Inspect all four restored keys with **Solo**, **Attached**, **Detached**, and **Both** before continuing authoring or export.

### Recipe: repair a stale legacy deformation pair

1. Open the accepted legacy authoring `.blend` as a disposable copy.
2. In **Active Region**, choose `head` and click **Use Selected Region**. Accepted Testman head pairs can migrate additively when their exact topology is valid.
3. Run **Validate Morph Targets** and record the mismatch.
4. Click **REPAIR LEGACY PAIR SYNC**.
5. Confirm any intentionally missing key remains missing. Read the healthy/repaired/skipped/unrepairable summary.
6. Run **Validate Morph Targets** again. If an item is unrepairable, preserve it and fix the attached source/key contract manually; do not keep pressing repair.

### Recipe: compare attached and detached results

1. Activate the desired region and key, then click **Solo**.
2. Click **Attached** and inspect the intact-region deformation.
3. Click **Detached** and inspect the prop at the same key value.
4. Click **Both** and look for doubled silhouettes; a correct exact-index pair should overlay at its authored placement.
5. Click **Validate Morph Targets** for the numerical check.
6. Return to Damage Authoring and click **Preview Intact** to restore the full intact presentation.

### Recipe: export and reimport a completed asset

1. Confirm **Source Readiness: VALID**, then run **Validate Morph Targets** and **Validate Complete Damage Asset**; require Authoring Validation to pass.
2. Set a project-safe **Damage Export Folder** and **Damage Asset Filename**.
3. In Object Mode, click **Export Damage GLB + Manifest** and require **Export Validation: PASS**.
4. Confirm the GLB, manifest JSON, and validation JSON exist.
5. Start a clean scene and import that GLB.
6. Click **Restore Reimported GLB Intact Preview**.
7. Verify complete intact visibility, hidden detached/cap/socket objects, expected morph names, and `PASS` in the validation JSON.

## 20. Troubleshooting and recovery

| Symptom or message | Cause | Recovery |
| --- | --- | --- |
| Dreadstone tab is missing | Add-on disabled, invalid ZIP, or stale session | Reinstall the unextracted current ZIP, enable it, and restart Blender. |
| “Select the imported character” | No related object is selected | In Object Mode select the source mesh, armature, or its root. |
| “No armature found” | Selection does not lead to a rig | Select the skinned mesh or armature; inspect its Armature modifier. |
| Limbs bend backward | Facing or hinge sign is wrong | Correct **Character Faces**, **Invert Knees**, and **Invert Elbows**, then regenerate the draft. |
| Readiness folder error | Blank path, unsaved `//` path, or drive root | Choose an explicit project subfolder in **Report Output Folder**. |
| **Overall** is `REVIEW` | One or more health/seam requirements failed | Open the Markdown report, preview the named seam, fix only the cited source topology/weights, and rerun readiness. |
| READY handoff is rejected | Old schema/revision, non-READY report, open contour, or original-source fingerprint mismatch | Rerun **Analyze Source Damage Readiness** on the unchanged original source. |
| A bad 3.8 report lists `DSB_BODY_CORE` / `DSB_ATTACHED_*` | Older readiness discovery selected generated authoring meshes | Do not repair generated open cuts and do not clear the authored asset. Run **Repair Source Readiness Contract**, verify the original inventory, then validate/export. |
| Source readiness is stale | Original topology, relevant weights/groups, armature/mapping, analyzer contract revision, source identity, or source collection identity changed | Restore/correct the specifically named original source item and explicitly rerun Source Readiness. Generated topology, keys, stamps, previews, Actions, and export metadata are not causes. |
| Source identity is missing or replaced | The original imported object/datablock no longer resolves | Restore the original source from backup. Forge deliberately refuses to fall back to generated `DSB_*` meshes. |
| Build/export says switch modes | Blender is in Edit or Sculpt Mode | Press `Tab` or choose Object Mode, then retry. |
| Region registration is reversed | Detached object was active | Remove the registration; select detached first and attached last, then register again. |
| Pair validation fails | Vertex/polygon/index/loop topology differs | Use a pair generated by the same Damage Authoring build. Do not use nearest-object transfer or remeshing. |
| Capture is stale | Region, object, topology, selection hash, or virtual-weld state changed | Activate the intended region and recapture on the current attached mesh. |
| Patch reports disconnected islands | Selection includes a real separate component or corner-only contact | Deselect the island. Select one component connected by full edges. |
| Stamp edits appear ignored after rebuild | Stored stamp was not updated | Select the stamp and click **Update Active Stamp**, then rebuild. |
| Stamp library says the capture does not analytically match | Destination surface positions changed beyond the conservative anchor tolerance | Rebuild from the same original source and compatible authoring settings. Forge handles split/index changes but will not guess a changed surface mapping. |
| Stamp library says existing keys contain different work | A destination key or stack would be overwritten | Save the destination work, then explicitly delete or rename only the disposable conflicting key and load again. |
| Old generated `.blend` cannot run Source Readiness | It contains exported `DSB_*` pieces but no original protected source | You can still use **Save Stamp Library...** to preserve procedural stamps. Start over from the original source GLB, build/register the matching pair, then use **Load Stamp Library...**. |
| Export says a deformation key has no enabled trauma stamp | A procedural stack exists but every stamp is disabled | Enable at least one intended stamp, rebuild the key, run **Validate Morph Targets**, and export again. |
| Preview crosses through a head/limb | **World Distance** uses straight 3D proximity | Switch to **Surface Distance** and recapture/rebuild. |
| Rebuild says no trauma stamps | Key is legacy/manual or stamp was not added | Add a captured stamp, or use the displayed legacy preset/sculpt workflow without overwriting it. |
| Deformation exceeds limit | Depth/strength/stack is above declared maximum | Reduce **Seed Depth** or **Stamp Strength**, increase the maximum only when intentional, update stamps, and rebuild. |
| Legacy repair says unrepairable | Attached authority failed topology, finite-value, key, Basis, or maximum checks | Leave it unchanged; repair the underlying attached key or topology contract manually, then validate. |
| Damage validation reports a gap/cap error | Generated contour or cap no longer matches the approved source | Clear generated assets, rerun readiness if the source changed, and rebuild. Do not hide the issue by arbitrarily raising tolerance. |
| Export folder error | Unsaved file with blank/relative path or drive root | Save the `.blend` or choose an explicit project subfolder. |
| Reimport shows only a socket/Empty | Imported visibility metadata was not interpreted by Blender | Click **Restore Reimported GLB Intact Preview**. |

## Complete public button inventory

Use this inventory during release acceptance to make sure no public operation has disappeared from the workflow above.

- **Character Setup:** **Adopt Imported Animation Pack**, **Safe Resize**, **Analyze Rig**.
- **Ground Preview:** **Create Floor**, **Align Pose**.
- **Source Damage Readiness:** **Analyze Source Damage Readiness**, **Repair Source Readiness Contract**, **Preview Candidate Seam**, **Clear Preview**, **Open Report Folder**, **Open Markdown**.
- **Damage Segment & Stump Authoring v3.9:** **Load READY Handoff**, **Build Authoring Asset**, **Clear Generated Asset / Restore Source**, **Preview Intact**, **Preview Detached**, **Restore Reimported GLB Intact Preview**, **Validate Complete Damage Asset**, **Export Damage GLB + Manifest**, **Open Damage Export Folder**.
- **Trauma Field — regions and keys:** **Use Selected Region**, **Validate Pair**, **Register Selected Pair**, **Remove Registration**, **Create Damage Shape Key**, **Create Standard Head Set**, **Create Blunt Gore Head Set**, each managed key button, **Solo**, **Zero All**, **Delete Active**, **Mirror Active**.
- **Trauma Field — capture and stamps:** **Capture Single Face**, **Capture Connected Face Patch**, **Capture Selected Vertices**, **Capture 3D Cursor**, each numbered stamp button, **Add Stamp**, **Duplicate**, **Remove**, **Move Up**, **Move Down**, **Enable / Disable**, **Save Stamp Library...**, **Load Stamp Library...**, **Update Active Stamp**.
- **Trauma Field — Surface Gore Overlay:** **Enable Surface Gore Overlay**, **Default New Impacts to High-Intensity Gore**, **Gore Preset**, **Use Preset Defaults**, **Enable Raised Gore**, stain/raised/material/variation controls, **Preserve as User-Customized**, **Apply Gore Overlay Settings**, **Preview / Rebuild Current Gore**, **Apply Heavy Gore to All Deformations**, **Clear Current Generated Gore**, **Clear Stain Preview**, **Rebuild All Generated Gore**, **Validate Gore Geometry**.
- **Trauma Field — preview, sculpt, and validation:** **Attached**, **Detached**, **Both**, **Preview Active Stamp**, **Clear Temporary Preview**, **REBUILD ACTIVE DEFORMATION**, conditional **BUILD ACTIVE PRESET**, **Preview Legacy Seed**, **Commit Legacy Seed**, **Begin Sculpt**, **Finish Sculpt & Sync**, **Validate Morph Targets**, **REPAIR LEGACY PAIR SYNC**.
- **Arm & Hand Pose Polish:** **Zero Arm & Hand Polish**.
- **Walk Draft:** **Generate / Refresh Walk Draft**, **Version / Approve Walk Draft**.
- **Death / Collapse Draft:** **Generate / Refresh Death Draft**, **Version / Approve Death Draft**.
- **Flank Hurt Drafts:** **Refresh Left**, **Refresh Right**, **Approve Left**, **Approve Right**.
- **Approved Animation Pack:** **Build Approved Animation Pack**, **Validate Last Built Pack**.
- **Action Cleanup & Safety:** **Protect Active Legacy Action**, **Delete Unapproved DSB Attempts**.
