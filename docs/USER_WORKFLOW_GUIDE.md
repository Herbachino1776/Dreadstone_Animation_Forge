# Dreadstone Animation Forge 5.4.0 — User Workflow Guide

- Release archive: `Dreadstone_Animation_Forge_v5_4_0.zip`
- Supported release runtime: Blender 5.1.2
- Damage authoring model: Damage Keys → child Stamp alternatives → strong macros
- Reuse model: topology-independent Damage Blueprints

## 1. Install Dreadstone Animation Forge 5.4.0

In Blender choose **Edit > Preferences > Add-ons > Install from Disk**, select
`Dreadstone_Animation_Forge_v5_4_0.zip` without extracting it, and enable
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

## Character Variant Families (Skin & Bones 2.2.0+)

The **CHARACTER VARIANTS** card is the compact family control surface. To adopt
an existing fully authored approved character, select its Skin & Bones mesh or
armature and click **ADOPT AS SHARED FAMILY BASE**. Existing approved Actions,
Damage Keys, Stamps, gore, Progressive Damage Sites, and managed sockets remain
the one shared authoring layer.

To add an appearance, choose its Skin & Bones GLB and click
**ADD COMPATIBLE SKIN & BONES VARIANT**. Forge reads the shipped appearance-family handoff from
the GLB, checks its family/body fingerprint and exact canonical rig/coordinate
contract, and refuses a mismatch. A successful appearance immediately inherits
all shared Forge authoring and creates no Action or Damage Key copies.

Click a variant's radio row to make it active. The viewport switches baked
appearance while retaining the resolved technical rig, animation, damage, and
sockets. Each selected editable item is visibly `SHARED`, `INHERITED`, or
`OVERRIDE`.

For animation, select an inherited Action and click
**CREATE VARIANT OVERRIDE**. Forge creates one editable draft copy for that variant; save,
preview, and approve it through the normal workflow. Other Actions remain
inherited. Use the confirmed **EDIT SHARED** only when the change should reach
every inheriting appearance. **REVERT TO SHARED** discards the variant Action
and resolves the shared Action immediately.

For Damage, select either **Active Damage Key** or **Active Progressive Site**
as the override unit, then click **CREATE VARIANT OVERRIDE**. A Damage Key
override clones only that key's paired shape keys, Stamps, Gore, and bindings.
A Progressive Site override clones the site and exactly its assigned
Light/Medium/Heavy keys so all internal references remain variant-owned and
coherent. **REVERT TO SHARED** warns before removing variant-only data. The
normal inherited Damage controls remain locked until an override is created or
the artist deliberately confirms **EDIT SHARED**.

Selected Complete Damage export writes the active appearance plus its resolved
shared/override content. **EXPORT ALL READY VARIANTS** writes each passing
variant as a separate GLB and sidecars. Inherited approvals are reused; only
variant overrides require their own relevant preview, validation, and
approval. See
[CHARACTER_VARIANT_FAMILY_CONTRACT.md](CHARACTER_VARIANT_FAMILY_CONTRACT.md)
for exact handoff, ownership, resolution, and export rules.

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

To rename the focused key at any time, edit **Rename to** in that card and click
**RENAME**. This is especially useful immediately after **DUPLICATE ACTIVE KEY
AS STARTING POINT**. Names accept letters, numbers, and underscores. Renaming
preserves the key's stable ID, child Stamps, generated gore, animation links,
and progressive-stage assignment; an assigned site is marked for revalidation.

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

The animation workspace remains independent of Damage Key previews. Humanoid
animation requires a character rigged by Skin & Bones Forge 2.1.0+ with
`SBF_HUMANOID_YPLUS_V1` metadata. The canonical contract is Blender `+Y`
forward, `+Z` up, anatomical right `+X`, and top-level `root` motion. Animation
Forge reads the stored rig metadata and mapping; there is no canonical GLB to
import here. Old `-Y` and unversioned humanoids are unsupported—convert or
re-rig them in Skin & Bones first.

Analyze the rig, draft idle/walk/collapse/hurt or mace head-guard Actions,
inspect them, and use the explicit Version/Approve controls. Generated Actions
do not animate bone scale. Approved Actions and NLA-used Actions are protected.

For combat motion, open **OFFENSIVE MOTION STUDIO**. This is the primary attack
workflow. It starts with a target and weapon path instead of guessing arm
rotations:

1. Choose a **Motion Master**. The initial proof is **1H Overhead**; the five
   starters also include opposite horizontal slashes, heavy diagonal, and
   thrust. Click **BUILD FROM MOTION MASTER**.
2. Under Target Dummy & Zone, choose HEAD, UPPER_TORSO, CENTER_MASS,
   LOW_TORSO, or CUSTOM. Set editable target height, distance, lateral offset,
   and volume dimensions. Defaults are Forge authoring dimensions, not fixed
   Dreadstone player truth.
3. Choose the Weapon Proxy class and its measured length, grip-to-contact
   distance, strike segment, and optional head radius. It is only clean
   authoring geometry; the game still owns the real weapon asset and damage.
4. Use **ANTICIPATION**, **CONTACT**, and **FOLLOW THROUGH** to jump to the key
   review states. CONTACT is sacred: at this frozen frame, verify that the red
   proxy strike segment/contact point actually passes through the selected
   target volume on the visible plane or line.
5. Move the orange trajectory controls directly in the viewport when needed,
   adjust target/proxy/timing values, then click **BUILD / REBUILD BODY SOLVE**.
   Forge uses temporary constrained arm controls and supporting torso/stance
   motion, then bakes ordinary canonical FK curves and removes constraints.
6. Click **PREVIEW**, scrub WINDUP/ACTIVE/RECOVERY with the blue/red/green
   weapon trail visible, and click **VALIDATE BAKED PATH**. Validation samples
   the real baked hand, unchanged runtime socket, and configured proxy—not only
   the pre-bake controls.
7. Click **APPROVE** only after the current preview and target validation pass.
   A useful miss reads like `Weapon contact point missed UPPER_TORSO by 0.18 m
   during ACTIVE`, rather than a generic failure.
8. After human review, optionally click **PROMOTE TO MOTION MASTER**. Promotion
   is deliberate and stores the target-relative path for reuse through the
   solver; it never silently replaces a global default.

Built-in starters are marked geometry valid, not artist approved. A numeric
PASS proves target contact, ACTIVE timing, plane tolerance, and direction; it
does not prove that the body motion is beautiful. Human preview and approval
remain authoritative. Starter masters are IN_PLACE and do not hide a forward
root lunge. The target is an authored launch relationship, not runtime homing:
after commitment the baked path is fixed and a player can dodge.

The approved Action stores `dreadstone.offensive_motion_recipe.v1`, current
`dreadstone.offensive_motion_validation.v1`, and a small optional
`dreadstone.offensive_targeting.v1` sidecar record. The established
`dreadstone.offensive_action.v1` combat ID, socket, weapon class, commitment,
and WINDUP/ACTIVE/RECOVERY contract remains unchanged. Helpers live only in
`DSB_OFFENSIVE_MOTION_STUDIO`, can be repaired after reopen, and never export
as GLB nodes or bones.

Open **LEGACY / PROCEDURAL DRAFTING** only for backward-compatible rough
drafting. **Generate / Refresh Offensive Suite** still creates all eight old
body-first drafts; **Apply Sliders / Refresh Draft**, **Preview Attack**, and
**Save / Approve This Attack** remain available, and existing Actions are not
migrated. Motion Studio does not require old approved Actions to gain target
proof retroactively.

### Exact Dread Ram God one-hand overhead acceptance

Use this manual review before calling the milestone artistically complete:

1. Open the Dread Ram God authoring `.blend`, select its canonical humanoid,
   and open **OFFENSIVE MOTION STUDIO**.
2. Choose **1H Overhead**, **1H Blunt / Mace**, and UPPER_TORSO (or HEAD when
   that is the deliberate contact). Set realistic target distance and proxy
   length/contact dimensions for the review mace.
3. Click **BUILD FROM MOTION MASTER**, then enable Show Target, Show Weapon
   Trail, and Show Strike Plane / Line.
4. Click **CONTACT**. In the frozen viewport confirm the mace contact/head and
   red strike segment physically pass through the selected mathematical target
   volume on the vertical plane. Do not accept a pass above or beside it.
5. Click **ANTICIPATION** and scrub WINDUP. Confirm the weapon raises clearly,
   the silhouette reads overhead, and torso/stance support does not create an
   impossible shoulder, inverted elbow, collapsed wrist, snap, or foot slide.
6. Scrub the red ACTIVE trail through CONTACT. Confirm a fast downward crossing
   rather than uniform speed or a slowdown at impact.
7. Click **FOLLOW THROUGH**, scrub RECOVERY, and confirm the weapon exits the
   target, carries momentum, and returns cleanly without a spine discontinuity.
8. Click **PREVIEW**, then **VALIDATE BAKED PATH**. Require PASS for actual
   baked FK ACTIVE contact, intended CONTACT, vertical descent, plane tolerance,
   unchanged socket, no scale channels, exact skeleton, and IN_PLACE root.
9. If the motion also passes human visual review, click **APPROVE**. Export
   through the ordinary Animation Pack or Complete Damage path and clean-
   reimport to confirm no `DSB_MS_*` helpers and the unchanged 21-bone rig.
10. Only after that review, optionally click **PROMOTE TO MOTION MASTER** and
    build it on a second compatible humanoid to confirm the target-relative
    solver workflow.

Record visual defects as manual acceptance failures even when geometric tests
pass. The decisive proof is a believable body supporting a baked mace path that
actually descends through the authored target during ACTIVE.

Click **Create / Repair Runtime Hand Sockets** after `DSB_DAMAGE_RIG` exists.
Forge creates managed artist-adjustable Empty helpers on `arm_right_hand` and
`arm_left_hand`. Re-running the command repairs ownership/parenting without
resetting an artist's local grip offset. The helpers never add bones, change
rest matrices or weights, or ship as GLB nodes; their bone-local position and
quaternion are written to the JSON sidecar for Dreadstone's runtime resolver.

Use **Generate Humanoid Idle** for a seamless in-place breathing and
weight-shift loop. Idle and Walk use `+Y` consistently, with no hidden 180° yaw
or legacy knee/elbow inversion.

The Walk cycle treats rear as Blender `-Y` and forward as Blender `+Y`: each
airborne foot travels rear-to-front before contact. Positive **Elbow Bend**
increases natural anatomical flexion on the Skin & Bones canonical rig. Leave
**Invert Elbows** off unless deliberately authoring an exceptional rig or
stylized reverse hinge. **Torso Lean** and every Death travel direction retain
their existing `+Y` behavior.

Keep the Skin & Bones high A-pose as the canonical rigging/rest pose. To give
an animation a more natural stance without changing skinning, use Idle's
**Draft Base Pose**:

1. Click **EDIT IDLE BASE POSE**. Forge temporarily detaches Action/NLA
   playback, resets to the stored Idle base (or the canonical rest pose), and
   enters Pose Mode.
2. Rotate or move the mapped body bones into the relaxed stance you want.
   The top-level `root` is deliberately excluded from capture.
3. Click **CAPTURE BASE + PREVIEW IDLE**. Forge stores the pose by semantic
   role and regenerates breathing and weight shift on top of it.
4. Use **CANCEL EDIT** to discard uncaptured adjustments or **CLEAR BASE** to
   return Idle to the canonical rest pose.

**Arm Drop to Sides** remains a quick additive control. Increasing it lowers
both complete arm chains toward the torso from the captured base pose. Editing
a manual Idle base resets this slider to zero to prevent an accidental double
drop. The rest armature and weights are never changed. The same stored-pose
contract is also exposed in **Flank Hurt Drafts** and **Mace Head-Guard
Drafts**. Hurt uses one shared base for both left/right reactions. Mace Guard
uses one shared base for its Two-Arm, Left-Arm, and Right-Arm variants. Their
Capture buttons regenerate every affected preview; Clear returns that family
to the canonical rest pose. Future weapon-ready and attack generators can use
the same contract.

Every death style bakes signed floor alignment through the top-level `root` and
ends in a validated low-profile torso-contact pose. Pelvis, lower spine, middle
spine, and chest are measured independently, so hand or arm contact cannot
hide a floating torso. Select **Instant Unconscious** for
an immediate, brace-free loss of consciousness; its separate duration control
defaults to a fully limp terminal contact in under one second. Chest Hold,
Faceplant, and Knees First retain their authored lead-ins but use the same final
ground-contact guarantee.

Start with the compact anatomy card and click **ANALYZE CREATURE ANATOMY**. It
shows creature class, selected anatomy profile, confidence, authoritative
orientation, mapped-role count, readiness, and the worst blocker. Leave the
selector on **Auto Detect** for clear rigs. If detection is ambiguous, select
**Humanoid**, **Quadruped Digitigrade**, or **Custom / unresolved** explicitly;
an override chooses the validation contract and never bypasses its requirements.
Use **SHOW ROLE MAPPING** for the resolved diagnostic and **CLEAR PROFILE
OVERRIDE** to return to automatic selection. Raw details stay under **Advanced
Anatomy Mapping**.

`DSB_QUADRUPED_MAMMAL_DIGITIGRADE_V1` is architectural support for digitigrade
mammals, not a claim of plantigrade, ungulate, reptile, bird, insect, or
arbitrary-creature support. Quadruped animation capabilities are declared but
not production-ready in this release, so no quadruped Generate controls are
shown. Forge reports a capability blocker instead of creating a broken Action.

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
Both humanoids must carry the exact `SBF_HUMANOID_YPLUS_V1` mapping and `+Y`
orientation. Every animated bone must exist and retain the same parent chain.
Different proportions or pose-bone translation channels can produce warnings.

Humanoid packages without current anatomy, canonical-rig, and `+Y` orientation
metadata are rejected; Forge never guesses or rotates an old Action. AnyTop and
other external motion systems are not installed or
run inside Blender; candidate BVH must be rights-cleared, imported in isolation,
retargeted through the anatomy profile, validated, and artist-approved before it
becomes a protected production Action.

## 12. Validate and export

Before export:

1. Run **Validate Morph Targets**.
2. Run **Validate Gore Geometry**.
3. Validate compound events when used.
4. Run **Validate Humanoid Offensive Suite** when offensive Actions exist.
5. Run **Create / Repair Runtime Hand Sockets** for an armed humanoid export.
6. Run **Validate Complete Damage Asset**.
7. Click **Export Damage GLB + Manifest**.
8. For each intended runtime progression, run
   **VALIDATE ALL CROSSFADE STATES** and
   **VALIDATE + ENABLE SITE FOR EXPORT**.

Export validation requires current capture/topology/deformation/recipe
digests, correct Stamp selection, exact-index paired morphs, mode-correct hybrid
components, glTF-safe materials, skinning, layer ordering, inactive defaults,
and triangle budgets. Blender-only preview materials are removed; their broad
surface stain is converted into a stage-owned glTF overlay mesh with an
RGBA `COLOR_0` mask, PBR material, matching deformation morph, and explicit
attached/detached/core binding. Forge parses the completed GLB and fails export
if the portable stain, base material, or required raised/inlay node is missing.

Complete Damage Asset ships `DSB_DAMAGE_RIG` as the runtime skeleton.
`SBF_ProductionRig` remains source-authoring provenance and is not included in
the runtime GLB. Approved source Actions are never gathered merely because
Blender sees them in `bpy.data.actions`: Forge resolves owner/kind metadata,
mirrors only provably compatible source-only clips, stages runtime-owned copies
on `DSB_DAMAGE_RIG`, and applies an exact glTF Action filter. Drafts,
unapproved clips, source duplicates, and source NLA are excluded. An
incompatible approved source clip is an actionable export failure.

Authored Actions may continue to start at frame 1 or another normal Blender
frame. Complete Damage export shifts only its temporary Action copies: every
runtime animation must have a first sample at `0.0` seconds and a final sample
and span equal to the declared `clipDurationSeconds`. The approved Actions in
the saved `.blend`, phase lengths, combat IDs, and commitment timing are not
rewritten.

Approved offensive clips are held to an additional fail-closed contract.
Duplicate combat IDs, absent hand roles, non-finite or overlapping timing,
zero-length ACTIVE windows, draft/unapproved state, and sampler-duration drift
all block export. The sidecar is the only attachment capability handoff;
Dreadstone must report the capability unavailable when an older pack omits it.
Motion Studio clips add current baked FK target contact, intended CONTACT,
plane/direction, socket, skeleton/rest, scale-channel, and preview-digest gates.
The optional targeting record is a future pre-commitment launch-envelope hint;
it does not guarantee a hit and contains no runtime tracking.

## 13. Clean reimport and verification

Reimport the exported GLB into a clean Blender file. Confirm:

- exactly one intended armature hierarchy exists and it is `DSB_DAMAGE_RIG`;
- `SBF_ProductionRig`, `SBF_CLEAN_CHARACTER`, and
  `DSB_SOURCE_MODEL_PROTECTED` are absent;
- all intact skinned meshes resolve to `DSB_DAMAGE_RIG`, while detached rigid
  pieces remain unskinned;
- the exact approved runtime Action inventory plays and every channel targets
  the damage rig or one of its bones;
- every runtime Action starts at `0.0` seconds and ends at its declared
  `clipDurationSeconds`;
- no `DSB_ATTACHMENT_SOCKET_*` helper is a GLB node or skin joint;
- no `DSB_MS_*` Motion Studio target, proxy, control, plane, or trail helper is
  a GLB node or skin joint;
- `runtimeAttachmentSockets` names the two canonical hand bones and contains
  finite normalized local transforms;
- each offensive clip's combat ID, compatible weapon classes, phases, and
  duration match the runtime animation record;
- each Motion Studio clip's optional targeting schema, target zone, preferred
  distance/contact height, trajectory family, contact time, and proxy reach
  match its approved baked-path proof;
- the intact character is visible;
- each Damage Key morph is present;
- hybrid recipes have both `_RAISED` and `_INLAY` nodes for every required role;
- raised nodes with **NUCLEUS** above zero contain a nonzero nucleus count and
  triangle count plus the crushed-tissue material role;
- gore nodes default inactive and map to the matching deformation key;
- each surface-stain stage has its own hidden-at-Basis overlay node, RGBA
  `COLOR_0` mask, matching deformation morph, and correct ownership role;
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
- Anatomy reports `PROFILE_AMBIGUOUS`: choose an explicit profile only after
  checking **SHOW ROLE MAPPING**. The override selects a validator; it does not
  make an incomplete rig ready.
- A humanoid reports a canonical-rig or orientation blocker: install Skin &
  Bones Forge 2.1.0+, then convert or re-rig the character as
  `SBF_HUMANOID_YPLUS_V1`. Animation Forge accepts only Blender `+Y` forward.
- A quadruped generator is unavailable: this release defines capabilities and
  validation but intentionally does not ship production quadruped motion.
- An old humanoid Action package is rejected: regenerate it for the Skin &
  Bones `SBF_HUMANOID_YPLUS_V1` rig. Forge does not maintain a `-Y` import path.
- Runtime animation audit fails: inspect the Action's `dsb_approved_kind`,
  `dsb_animation_owner_rig`, anatomy, and active/NLA owner. Do not rename a
  `_v001`/`_v002` suffix to force selection; repair approval/ownership metadata
  or approve a compatible Action on `DSB_DAMAGE_RIG`.

## Complete public button inventory

- Start/character: **Prepare Character for Damage Authoring**,
  **Analyze Source Damage Readiness**, **Repair Source Readiness Contract**,
  **Load READY Handoff**, **Build Authoring Asset**.
- VIP placement: Head, Body, Left Forearm, Right Forearm,
  **CREATE DAMAGE KEY FROM SELECTION**.
- VIP keys/stamps: **WORKING ON**, **Rename to**, **RENAME**, **PREVIEW ON**,
  **PREVIEW OFF**, **ADD STAMP ALTERNATIVE**, **REMOVE ACTIVE**,
  **STAMP · name**.
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
- Anatomy: **ANALYZE CREATURE ANATOMY**, profile override selector,
  **SHOW ROLE MAPPING**, **CLEAR PROFILE OVERRIDE**, **Advanced Anatomy
  Mapping**.
- Animation: **Generate Humanoid Idle**, **Generate / Refresh Walk Draft**,
  **EDIT IDLE BASE POSE**, **CAPTURE BASE + PREVIEW IDLE**, **CANCEL EDIT**,
  **CLEAR BASE**,
  **Generate / Refresh Death Draft**, flank-hurt draft controls,
  **Generate Three Mace Head-Guard Drafts**, **Preview Guard_Active**,
  **Validate Mace Head-Guard Drafts**, **BUILD FROM MOTION MASTER**,
  **BUILD / REBUILD BODY SOLVE**, **ANTICIPATION**, **CONTACT**,
  **FOLLOW THROUGH**, **PREVIEW**, **VALIDATE BAKED PATH**, **APPROVE**,
  **PROMOTE TO MOTION MASTER**, **Repair Helpers**, **Remove Helpers**,
  **Apply Sliders / Refresh Draft**,
  **Preview Attack**, **Save / Approve This Attack**,
  **Generate / Refresh Offensive Suite**, **Validate Humanoid Offensive Suite**,
  **Create / Repair Runtime Hand Sockets**,
  **VIP ANIMATION LIBRARY**, **PLAY**,
  **EDIT**, **SAVE**, **DELETE**, **EXPORT SELECTED**, **IMPORT TO CHARACTER**,
  **Build Approved Animation Pack**, **Validate Last Built Pack**.
