# Dreadstone Animation Forge 3.20.0 — User Workflow Guide

- Release archive: `Dreadstone_Animation_Forge_v3_20_0.zip`
- Supported release runtime: Blender 5.1.2
- Damage authoring model: Damage Keys → child Stamp alternatives → strong macros
- Reuse model: topology-independent Damage Blueprints

## 1. Install Dreadstone Animation Forge 3.20.0

In Blender choose **Edit > Preferences > Add-ons > Install from Disk**, select
`Dreadstone_Animation_Forge_v3_20_0.zip` without extracting it, and enable
**Dreadstone Animation Forge**.

## 2. Open the Dreadstone panel

In the 3D Viewport press `N`, open the **Dreadstone** tab, and choose the
**Damage Authoring** workspace. The collapsible **VIP DAMAGE WORKFLOW** is the
front-facing authoring surface. Advanced compatibility and repair tools remain
under **Advanced**.

## 3. Import and prepare a source GLB

Import the character, save a working `.blend`, select its mesh or armature, and
use **Prepare Character for Damage Authoring**. The preparation workflow runs
Source Readiness, creates the protected authoring asset only after a valid
handoff, and registers the standard Head, Body, Left Forearm, and Right Forearm
regions when they exist. A `NOT READY` result is a stop condition; inspect or
repair the source rather than bypassing it.

## 4. Use the VIP Damage workflow

The normal loop is intentionally short:

1. In **1 · PLACE**, activate a region.
2. Enter Edit mode and select one vertex, multiple vertices, one face, or one
   connected face patch. The button follows Blender's active mesh selection
   mode.
3. Choose **Direction**, name the key if desired, and click
   **CREATE DAMAGE KEY FROM SELECTION**.
4. Work in the new card marked **WORKING ON**.
5. Tune the Impact and Additive Gore macros or click **RANDOMIZE DAMAGE**.
6. Click **SAVE DAMAGE KEY + STAMP + GORE**.

There are no factory presets in the authoring UI. A neutral starting recipe,
high-leverage macros, and deterministic randomization replace them.

The macros and **RANDOMIZE DAMAGE** request a managed preview automatically
after a short debounce. **FAST** shows the current deformation and live gore
stain without building geometry. **BALANCED** also builds temporary raised and
inlay gore geometry from the unsaved values. Use **UPDATE GORE PREVIEW** for an
immediate explicit refresh. **SAVE DAMAGE KEY + STAMP + GORE** is only the
commit/final-validation step; it is not required to see macro changes.

## 5. Damage Keys and simultaneous previews

Every Damage Key has a large card. The focused card is highlighted and says
**WORKING ON** so it is always clear which key receives edits.

Each card owns its own **PREVIEW ON** / **PREVIEW OFF** toggle. Preview state is
independent of focus:

- Turn on Head Impact Left and Head Impact Right to see both morphs together.
- Turn either card off to hide only that key.
- Selecting another card changes the editing focus; it does not solo or clear
  other enabled previews.

Generated gore follows the same key activation state and attached/detached/core
role. Preview toggles do not delete saved recipes or export geometry.

## 6. Child Stamp alternatives

A Stamp is shown as a visible **STAMP · name** button directly beneath its
parent Damage Key. Click **ADD STAMP ALTERNATIVE** to capture another look for
that key.

New 3.19 keys treat child Stamps as alternatives: all alternatives are saved,
but exactly one Stamp per Damage Key is active in the preview. Clicking a child
Stamp focuses its parent key and rebuilds that alternative. This matches
Blender's one visible shape-key result per Damage Key.

Files authored with the older additive Stamp Stack remain readable and retain
their recorded stack behavior until deliberately converted by new authoring.

## Progressive Damage Sites

**PROGRESSIVE DAMAGE SITES** appears after the Damage Key rack and immediately
before the existing Impact/Gore controls. A site organizes three independently
authored, complete Damage Keys:

- **LIGHT**, **MEDIUM**, and **HEAVY** are full results relative to Basis.
- Forge does not generate, scale, rename, synchronize, or judge the artistic
  progression between stages.
- Selecting a stage focuses its assigned key and active Stamp, then loads that
  key into the same Impact, Gore, **RANDOMIZE DAMAGE**, and
  **SAVE DAMAGE KEY + STAMP + GORE** workflow.

Create a site with **NEW DAMAGE SITE**. Select each large stage tab and use
**ASSIGN ACTIVE DAMAGE KEY**, or create an independent key with
**CREATE NEW KEY FOR THIS STAGE**. **DUPLICATE ACTIVE KEY AS STARTING POINT**
makes an independent copy; it creates no ongoing synchronization.

Use **SET SITE ANCHOR FROM ACTIVE STAGE** to copy the current Stamp capture
center into character-local site metadata. Advanced settings expose the radius,
preferred incoming direction, structural group, and strictly ordered recommended
severity anchors.

In the **PROGRESSION CONTROL DECK**, set **Progression Severity**, choose
**PREVIEW SITE IN ISOLATION** (the validation mode) or
**PREVIEW WITH OTHER DAMAGE**, and keep **REFRESH PROGRESSION PREVIEW**
available even when live preview is on. Structural morphs crossfade only across
Basis→Light, Light→Medium, or Medium→Heavy. Detailed raised/inlay gore switches
as a complete assembly at each transition midpoint; stage gore never stacks.
**CLEAR PROGRESSION PREVIEW** restores the exact prior key weights, previews,
gore visibility, active key/Stamp, selection, mode, frame, Action, and NLA
state.

Draft sites may remain incomplete in the `.blend`. They are omitted from export
with a warning. **VALIDATE ALL CROSSFADE STATES** evaluates the required 15
transition points and available rest/walk/hurt/collapse animation contexts.
**VALIDATE + ENABLE SITE FOR EXPORT** succeeds only when all three stages are
saved, current, technically valid, and safe to interpolate. An invalid
export-enabled site blocks export. **DELETE SITE METADATA** requires
confirmation and preserves every Damage Key, Stamp, shape key, and gore object.

## 7. Strong Impact and Gore macros

Impact has six high-leverage controls:

- **AREA** changes the affected footprint.
- **DEPTH** spans from no crush to a deep bounded deformation.
- **FALLOFF** changes center-to-rim response.
- **EDGE DAMAGE** changes the annular edge response and inversely reduces seam
  protection.
- **DISTORTION** strongly changes deterministic breakup and irregularity.
- **ASYMMETRY** shifts the center and radial response so the result is visibly
  directional.

Additive Gore has six direct controls:

- **RAISED AMOUNT** and **INLAY AMOUNT** are independent 0.0–1.0 channels.
- **COVERAGE**, **EDGE BREAKUP**, **FILL**, and **WETNESS** control the remaining
  mask, geometry, and material response.

The nested **COHESIVE LEGACY SURFACE GORE** deck adds five raised-surface
macros fed by the detailed manual controls:

- **SURFACE MASS** changes raised gore from separated islands toward one
  connected, irregular mass. High values suppress the little-triangle look.
- **RELIEF** controls height, roundness, and the strength of the raised form.
- **NUCLEUS** grows a cluster of closed solid-tissue masses across the deepest
  third of the impact. Higher values add members and increase their scale. Each
  member varies in aspect, orientation, and folds, producing a substantial
  organ-like or brain-like wound bed rather than one small isolated form.
- **FOLDS** changes corrugation, lobe count, edge irregularity, and peripheral
  fiber breakup.
- **REDNESS** increases visible crimson/tissue contribution while reducing the
  dark-clot bias.

These are deterministic recipe controls, not a separately sculpted object.
With **NUCLEUS** at zero, Surface Gore remains shell-based. With it above zero,
the raised component contains a budgeted cluster of closed lobulated submeshes
that follows the same Stamp, source skinning, activation, and export contract.

One **RANDOMIZE DAMAGE** click creates a master seed and derives stable,
independent impact and gore seeds. It requests one managed preview instead of
triggering multiple competing rebuilds.

## 8. Hybrid additive gore

When both channels are above zero, the recipe mode is `HYBRID_ADDITIVE`.
Raised and inlay geometry are generated as two independent components per
attached, detached, or core role.

`RAISED AMOUNT = 1.0` plus `INLAY AMOUNT = 1.0` means full raised geometry plus
full inlay geometry. It is not a 0.5/0.5 blend. Reducing one channel scales that
channel without taking strength from the other.

The surface deck controls the character of the raised component; it does not
subtract from inlay depth. A full inlay can therefore remain visible around and
under a high-mass raised shell or nucleus.

Final hybrid node names add `_RAISED` or `_INLAY`. Both components remain
ordinary exportable glTF meshes with their own geometry and generation digests,
while sharing one parent recipe digest and activation mapping.

## 9. Save and reuse Damage Blueprints

In **4 · ADAPTIVE BLUEPRINT LIBRARY**:

1. Enter a **Blueprint Name**.
2. Choose the JSON **Library File**.
3. Click **ADD CURRENT RECIPE**.
4. Use **REFRESH** after changing the file outside Blender.
5. On any valid destination Damage Key and freshly captured Stamp, click
   **APPLY · blueprint name**.

A Damage Blueprint saves authored intent: the six Impact macros, six additive
Gore macros, five cohesive Surface Gore macros, exact seeds, gore identity,
Stamp family, direction/influence/distance choices, falloff, strength, maximum
influence, relative
radius/depth/feather/seam-protection/displacement ratios, texture
contributions, and semantic hint.

It deliberately does not save object names, vertex or face indices, topology
fingerprints, shape-key coordinates, or generated meshes. Applying a Blueprint
keeps the destination capture and scales the recipe to that capture. This is
how a head recipe can be adapted to a forearm, body, or another humanoid. It is
adaptive procedural reuse, not anatomical inference; the artist still chooses
the destination patch and direction.

The old `.dsbstamps.json` library remains read-compatible for same-source
migration, but it is not the universal reuse path.

## 10. Advanced capture, repair, and compound work

Use **Advanced** only when the VIP path does not cover the job:

- register a custom paired region with **Register Selected Pair** or a core
  region with **Register Selected Core Mesh**;
- use **Capture Single Face**, **Capture Connected Face Patch**,
  **Capture Selected Vertices**, or **Capture 3D Cursor**;
- choose **Patch Only**, **Patch Feathered**, or **Connected Surface**, plus
  **Surface Distance** or **World Distance**;
- enter manual physical-control modes;
- use **REBUILD ACTIVE DEFORMATION**, **REPAIR LEGACY PAIR SYNC**, or sculpt and
  exact-index synchronization tools;
- create and validate compound trauma events.

Advanced preview/view commands are diagnostic tools. The VIP per-key toggles
are the normal presentation controls.

## 11. Author and approve animation drafts

The animation workspace remains independent of Damage Key previews. Analyze the
rig, draft walk/collapse/hurt or mace head-guard actions, inspect them, and use
the explicit Version/Approve controls. Generated actions do not animate bone
scale. Approved Actions and NLA-used Actions are protected.

The **VIP ANIMATION LIBRARY** sits above every draft section and keeps the
custom sliders below fully available:

1. Current unsaved Actions appear under **CURRENT DRAFTS**. Select one, use
   **PLAY** or **EDIT**, then press **SAVE** to create its finalized Action.
2. Finalized Actions are grouped under **LOCOMOTION**, **REACTIONS**,
   **COMBAT**, or **OTHER**. Their names are editable directly in the list.
3. **PLAY** assigns the selected Action, applies its exact frame range, and
   begins playback immediately.
4. **EDIT** creates a safe working copy, enters Pose Mode, and restores the
   clip's saved custom slider values when that metadata exists. The ordinary
   walk/death/hurt/guard draft controls remain usable.
5. **SAVE** confirms before replacing the original Action with the edit draft.
   The original name and clip identity are retained, and active/NLA users are
   reconnected. **CANCEL** discards the working copy.
6. **DELETE** confirms before removing the saved Action and its NLA strip
   references from the character.

Saving or approving an animation writes the protected, still-editable Action in
the current authoring `.blend`. It does not require a GLB round trip. Continue
authoring Damage Keys, gore, or another animation in the same file; those
workspaces preserve the current Action/NLA state independently.

**Build Approved Animation Pack** is the delivery step, not an import step. With
**Bake / Force Sampling** enabled (the default), Forge bakes the approved
Actions while writing the animation-pack GLB. Do not reimport that GLB into the
same authoring file. Reimport into a separate clean file only when performing
the verification described in section 13.

For cross-character reuse, choose a folder and press **EXPORT SELECTED**. Forge
writes a native `.blend` Action clip plus a JSON manifest. On another humanoid,
choose that `.blend` under **Clip to Import** and press **IMPORT TO CHARACTER**.
Every animated bone must exist and retain the same parent chain. Different rest
orientations, proportions, or pose-bone translation channels produce warnings
because they may need manual adjustment, but do not block an otherwise
compatible import.

## 12. Validate and export

Before export:

1. Run **Validate Morph Targets**.
2. Run **Validate Gore Geometry**.
3. Validate compound events when used.
4. Run **Validate Complete Damage Asset**.
5. Click **Export Damage GLB + Manifest**.
6. For each intended runtime progression, run
   **VALIDATE ALL CROSSFADE STATES** and
   **VALIDATE + ENABLE SITE FOR EXPORT**.

Export validation requires current capture/topology/deformation/recipe
digests, correct Stamp selection, exact-index paired morphs, mode-correct hybrid
components, glTF-safe materials, skinning, layer ordering, inactive defaults,
and triangle budgets. Preview-only objects and temporary stain materials are
removed before export.

## 13. Clean reimport and verification

Reimport the exported GLB into a clean Blender file. Confirm:

- the intact character is visible;
- each Damage Key morph is present;
- hybrid recipes have both `_RAISED` and `_INLAY` nodes for every required role;
- raised nodes with **NUCLEUS** above zero contain a nonzero nucleus count and
  triangle count plus the crushed-tissue material role;
- gore nodes default inactive and map to the matching deformation key;
- materials are non-emissive and zero-metallic;
- the manifest lists Blueprint metadata, active Stamp, component/node IDs,
  digests, triangle counts, and activation weight.
- `progressiveDamageSites` lists stable site/stage/Damage Key IDs, explicit
  adjacent-crossfade and midpoint-gore contracts, validation measurements, and
  resident/visible/transition costs for every enabled site.

Use **Restore Reimported GLB Intact Preview** when inspecting a reimported
authoring asset.

## 14. Troubleshooting and recovery

- No key is created: make the registered attached/core mesh active in Edit
  mode, select one vertex, multiple vertices, one face, or one connected face
  patch, and retry.
- A Blueprint will not apply: recapture a valid destination surface; stale
  source indices are intentionally rejected.
- A Stamp button changes the wrong result: verify the highlighted
  **WORKING ON** card and the child button marked **ACTIVE**.
- A key is invisible: turn its card to **PREVIEW ON**.
- Hybrid validation reports a missing component: save the recipe again and
  rebuild generated gore. A paired hybrid key must finish with attached and
  detached `RAISED` plus attached and detached `INLAY` components.
- An older build reports that a macro-edited key exceeds its maximum world
  displacement: install the current 3.20 archive and rebuild the key. Current
  preview and Save paths project the generated coordinates into the recipe's
  world-space cap before strict validation.
- A library appears empty: verify **Library File** and click **REFRESH**.
- Source Readiness says `NOT READY`: fix or explicitly repair the source
  contract; do not treat generated cut boundaries as source defects.
- A site says `NEEDS_STAGE_SAVE`: focus each assigned stage and save that
  Damage Key; Randomize intentionally dirties only the selected stage.
- Progression validation reports a stale digest: the assigned stage changed
  after its site record was captured. Save the stage again, then revalidate.
- An incomplete site is missing from the manifest: drafts are intentionally
  omitted until **VALIDATE + ENABLE SITE FOR EXPORT** succeeds.

## Complete public button inventory

- Start/character: **Prepare Character for Damage Authoring**,
  **Analyze Source Damage Readiness**, **Repair Source Readiness Contract**,
  **Load READY Handoff**, **Build Authoring Asset**.
- VIP placement: Head, Body, Left Forearm, Right Forearm,
  **CREATE DAMAGE KEY FROM SELECTION**.
- VIP keys/stamps: **WORKING ON**, **PREVIEW ON**, **PREVIEW OFF**,
  **ADD STAMP ALTERNATIVE**, **REMOVE ACTIVE**, **STAMP · name**.
- VIP macros/actions: **AREA**, **DEPTH**, **FALLOFF**, **EDGE DAMAGE**,
  **DISTORTION**, **ASYMMETRY**, **RAISED AMOUNT**, **INLAY AMOUNT**,
  **COVERAGE**, **EDGE BREAKUP**, **FILL**, **WETNESS**,
  **RANDOMIZE DAMAGE**, **SAVE DAMAGE KEY + STAMP + GORE**.
- Progressive Damage Sites: **PROGRESSIVE DAMAGE SITES**,
  **NEW DAMAGE SITE**, **SELECT SITE**, **RENAME SITE**,
  **DUPLICATE SITE METADATA**, **DELETE SITE METADATA**, **LIGHT**,
  **MEDIUM**, **HEAVY**, **ASSIGN ACTIVE DAMAGE KEY**,
  **CREATE NEW KEY FOR THIS STAGE**,
  **DUPLICATE ACTIVE KEY AS STARTING POINT**, **GO TO ASSIGNED KEY**,
  **UNASSIGN STAGE**, **SET SITE ANCHOR FROM ACTIVE STAGE**,
  **PREVIEW SITE IN ISOLATION**, **PREVIEW WITH OTHER DAMAGE**,
  **REFRESH PROGRESSION PREVIEW**, **CLEAR PROGRESSION PREVIEW**,
  **VALIDATE ALL CROSSFADE STATES**, and
  **VALIDATE + ENABLE SITE FOR EXPORT**.
- Blueprint library: **ADD CURRENT RECIPE**, **REFRESH**,
  **APPLY · blueprint name**.
- Advanced authoring: **Register Selected Pair**,
  **Register Selected Core Mesh**, **Capture Single Face**,
  **Capture Connected Face Patch**, **Capture Selected Vertices**,
  **Capture 3D Cursor**, **REBUILD ACTIVE DEFORMATION**,
  **REPAIR LEGACY PAIR SYNC**.
- Validation/export: **Validate Morph Targets**, **Validate Gore Geometry**,
  **Validate Complete Damage Asset**, **Export Damage GLB + Manifest**,
  **Restore Reimported GLB Intact Preview**.
- Animation: **Generate / Refresh Walk Draft**,
  **Generate / Refresh Death Draft**, flank-hurt draft controls,
  **Generate Three Mace Head-Guard Drafts**, **Preview Guard_Active**,
  **Validate Mace Head-Guard Drafts**, **VIP ANIMATION LIBRARY**, **PLAY**,
  **EDIT**, **SAVE**, **DELETE**, **EXPORT SELECTED**, **IMPORT TO CHARACTER**,
  **Build Approved Animation Pack**, **Validate Last Built Pack**.
