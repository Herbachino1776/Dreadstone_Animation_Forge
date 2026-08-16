# Dreadstone Animation Forge 6.0.0 — User Workflow Guide

- Release archive: `Dreadstone_Animation_Forge_v6_0_0.zip`
- Supported release runtime: Blender 5.1.2
- Damage authoring model: Damage Keys → child Stamp alternatives → strong macros
- Reuse model: topology-independent Damage Blueprints

## 1. Install Dreadstone Animation Forge 6.0.0

In Blender choose **Edit > Preferences > Add-ons > Install from Disk**, select
`Dreadstone_Animation_Forge_v6_0_0.zip` without extracting it, and enable
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

## Look Variants — texture to export

### Multiply a finished character through texture projection

Use this path when the `.blend` already contains the finished
`DSB_DAMAGE_RIG`, Actions, and Damage work and you now want to run the same body
through more texture projections. No Skin & Bones family handoff is required.

1. Expand **LOOK VARIANTS · TEXTURE → EXPORT** and click **SET UP FROM THIS FINISHED CHARACTER**.
   Names are optional: Forge uses the existing Complete
   Damage export identity and calls the current appearance `Original`.
2. Name the next skin and click **MAKE EDITABLE TEXTURE COPY**. Forge duplicates
   only the active materials and referenced images; it does not duplicate the
   body, Actions, Damage Keys, Progressive Sites, gore, or sockets.
3. For another four-view projection, use the embedded **PROJECT WITH SKIN &
   BONES** steps: **LOAD 4-VIEW FOLDER**, **BUILD / REFRESH PREVIEW**, **BAKE
   FINAL TEXTURE**, then **USE FINAL ON THIS LOOK**. Forge temporarily reveals
   `SBF_CLEAN_CHARACTER`, evaluates only its provenance-verified S&B production
   rig in the neutral rest pose, and hides the derived Damage pieces so the
   preview is actually visible and matches neutral four-view plates. Returning
   to the finished look restores the S&B rig's prior display pose. It never
   changes `DSB_DAMAGE_RIG`, the current Action/frame, or either authored hand
   socket. Inactive look materials/images are kept inside the `.blend`, so they
   remain available after save/reopen. Detailed alignment and repair remain in
   the Skin & Bones tab. Skin & Bones family approval is not required for this
   Forge-owned route.
   Alternatively, paint the packed image or choose one already-finished UV Base
   Color image. A folder of front/back/left/right plates is source art, not a
   model texture.
4. Click **RETURN TO / PREVIEW FINISHED LOOK**, then **SAVE CURRENT LOOK** or
   **SAVE + EXPORT**.
5. Click any saved look to swap it in the viewport. Use **EXPORT ACTIVE LOOK**
   for one independent Complete Damage GLB or **EXPORT ALL READY LOOKS** for the
   batch, then repeat from step 2.

The primary card deliberately contains no family-source decision. A legacy
finished character such as the Warden automatically uses the Forge-owned look
route. Exact Skin & Bones 2.2 family adoption and per-look Action/Damage
copy-on-write controls remain available under collapsed **Advanced** sections.

For an older resized working file, look export automatically checks the hidden
original source against its finished authoring proof and restores only that
stored transform when necessary. **REPAIR FINISHED SOURCE PROOF** remains under
Advanced for manual diagnosis. The transaction reruns full validation and rolls
back if the asset is not valid; it does not change the runtime rig, authored
animation, Damage geometry, or socket position/rotation.

Look switching restores each Damage mesh's authored intact visibility. Detached
heads/limbs, stumps, gore, and other damage-only pieces do not become visible
merely because the appearance changed.

If a projection preview shows the new skin only on the face or chest while the
old skin remains on bent limbs, rebuild it through step 2B. Forge now reasserts
the neutral S&B source rig immediately before both preview and bake.

### Import compatible Skin & Bones family exports

Open **ADVANCED · IMPORT A SKIN & BONES 2.2 LOOK FAMILY**. To adopt
an existing fully authored approved character, select its Skin & Bones mesh or
armature and click **ADOPT SELECTED APPROVED S&B FAMILY BASE**. Existing approved Actions,
Damage Keys, Stamps, gore, Progressive Damage Sites, and managed sockets remain
the one shared authoring layer.

To add an appearance, choose its Skin & Bones GLB and click
**ADD VERIFIED LOOK**. Forge reads the shipped appearance-family handoff from
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
shared/override content. **EXPORT ALL READY LOOKS** writes each passing
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

For combat motion, open **ATTACK ANIMATION STUDIO**. Generation is a permissive
sandbox; approval is the strict production gate:

1. Choose **Attack**, **Weapon**, and **Target**.
2. Under **LET ME COOK**, adjust aim, windup, strike power, body motion,
   follow-through, arm relaxation, target distance, weapon length, and grip-to-
   contact. Use Manual reach when testing exact meter values or Auto when you
   want character-adaptive fitting.
3. Click **GENERATE & PREVIEW**. Forge consumes every live slider and meter,
   bakes, validates, and always starts playback. A failed experiment is labeled
   Preview Only instead of being refused. The selected hand-held weapon proxy is
   replaced on every build; changing from a blade to a mace or dagger cannot
   leave the old longsword proxy visible.
4. Read **QUALITY STATUS**. Approval requires both baked-path geometry and pose
   health to report `PASS`. Auto Fit keeps the whole wrist path inside a safe
   shoulder-to-wrist annulus: at least 55% extension, below the 92% near-lock
   threshold for production starters, and never beyond the 98.5% hard limit.
   Per-frame FK rotation must remain at or below 22 degrees for a clean pass;
   more than 22 through 25 degrees is `WARN`, and more than 25 degrees fails.
5. Use **REPLAY / PREVIEW** to replay or scrub WINDUP / ACTIVE / RECOVERY. Require
   a compact anticipation, connected upper-body support, readable contact,
   visible follow-through, controlled recovery, and an unchanged authored lower
   body.
6. **CONTACT** is optional. It jumps to the impact frame and creates the reduced
   target, proxy, strike-plane, and baked-trail review helpers on demand. The
   yellow marker is the intended first-impact surface point. Confirm the blade
   segment, mace head, or thrust tip meets the selected target volume. A HEAD
   overhead is a chopping arc to the top surface, not a thrust through center.
7. Click **APPROVE** only after the current preview and both quality records pass.
   `WARN` is deliberately non-approvable; it is a request to rebuild or revise,
   not an artist-overridable success. Geometry PASS proves physical targeting,
   not beauty, so visual review remains authoritative. If the animation is good
   for your game despite rejected technical checks, click **BYPASS FAILED CHECKS
   AND SAVE** beside Preview. This accepts the exact reviewed preview, preserves
   all rejected checks in the Action audit record, and enables export. Editing
   the animation afterward invalidates that bypass.
8. Open **ADVANCED - TRAJECTORY, BODY & SOLVER** only for deliberate expert
   editing. Expert Motion Overrides, Target Details, Weapon Geometry,
   Trajectory / Control Points, Body Style, Solver / Reach, and Validation
   Tolerances remain available there. After editing, use **BUILD FROM MOTION
   MASTER** or **REBUILD EDITED CONTROLS**, then **VALIDATE BAKED PATH**. Orange
   editable controls are created only by the expert helper/repair path.
9. After human review, optionally **PROMOTE TO MOTION MASTER**. Promotion is
   explicit. Existing approved Actions and saved 5.4.0/5.4.1 promoted masters
   retain their authored records and are never silently rewritten.

Built-in starters are marked geometry valid, not artist approved. A numeric PASS
proves target contact, ACTIVE timing, plane tolerance, direction, safe reach,
and clean continuity; it does not prove that the body motion is beautiful.
Human preview remains authoritative. Starter masters are IN_PLACE and do not
hide a forward root lunge. The target is an authored launch relationship, not
runtime homing: after commitment the baked path is fixed and a player can dodge.

The production bake writes one deterministic base-pose rotation key for mapped
bones, then samples only spine, chest, active shoulder, upper arm, forearm, and
hand. It emits no deform-arm location curves, leaves pelvis, legs, and feet in
their authored base pose, preserves the seven named motion poses, and removes
redundant samples only after pose checks pass.

The approved Action stores `dreadstone.offensive_motion_recipe.v1`, current
`dreadstone.offensive_motion_validation.v1`,
`dreadstone.offensive_motion_pose_health.v1`, and a small optional
`dreadstone.offensive_targeting.v1` sidecar record. The established
`dreadstone.offensive_action.v1` combat ID, socket, weapon class, commitment,
and WINDUP/ACTIVE/RECOVERY contract remains unchanged. Optional helpers live
  only in `DSB_OFFENSIVE_MOTION_STUDIO`; ordinary Generate & Preview creates only
  the selected weapon display. CONTACT creates the reduced review set, expert repair may
restore editable controls, and no helper exports as a GLB node or bone.

Open **LEGACY / PROCEDURAL DRAFTING** only for backward-compatible rough
drafting. **Generate / Refresh Offensive Suite** still creates all eight old
body-first drafts; **Apply Sliders / Refresh Draft**, **Preview Attack**, and
**Save / Approve This Attack** remain available, and existing Actions are not
migrated. Motion Studio does not require old approved Actions to gain target
proof retroactively.

### Exact 6.0.0 production attack acceptance

For every case, select the canonical humanoid, open **ATTACK ANIMATION
STUDIO**, choose inputs, adjust **LET ME COOK** controls, and click **GENERATE &
PREVIEW**. Preview must play even for deliberately invalid settings; Approval
must remain blocked until geometry and pose-health both `PASS`. Use
**CONTACT** only when target, proxy, and trail helpers are useful for review.
Any `WARN` blocks approval.

1. **Sword Overhead → Head:** choose 1H Overhead / 1H Blade / Head. Confirm a
   compact raised guard, bent elbow, modest body support, a blade-led chopping
   arc to the yellow top-surface anchor, target entry during ACTIVE, visible
   follow-through, and controlled recovery. Reject a hand telescoped above the
   head, a nearly vertical tip-down plunge, a shoulder wrench, or a snap.
2. **Sword Overhead → Upper Torso:** change only Target to Upper Torso and
   rebuild. Confirm the same readable chop at a naturally adapted distance;
   the blade may meet the torso with any selected point inside the visible red
   strike segment.
3. **Mace Overhead → Upper Torso:** change Weapon to 1H Blunt / Mace. Confirm
   the visible head/contact region leads, the shaft/hand relationship is clear,
   and the result feels heavier but controlled. The mace does not use a sliding
   blade contact point.
4. **Sword Thrust → Center Mass:** choose 1H Thrust / 1H Blade / Center Mass.
   Confirm a small chamber that does not yank the wrist far behind the torso,
   forward-aligned blade, bent-to-comfortable extension, tip contact at the
   front entry surface, modest penetration, and smooth retraction.
5. **RTL and LTR Slash → Upper Torso:** build both starters with 1H Blade.
   Confirm each crosses the side-surface anchor in its named direction, uses a
   moderate side-to-side path and torso response, and exits without an elbow
   flip or violent twist.

When CONTACT helpers are visible, inspect the target volume, yellow intended
surface anchor, proxy tip/head/strike segment, and magenta baked closest point.
Before approval verify that arm extension never falls below 55% or reaches the
92% warning band, deform-arm translation is effectively zero, solve error stays
within tolerance, and maximum one-frame angular change is at most 22 degrees.
Confirm only the six upper-body support bones carry sampled attack motion and
that key reduction preserves all named poses. Export through Animation Pack or
Complete Damage and clean-reimport to confirm no `DSB_MS_*` helper and the
unchanged 21-bone runtime rig. Record visual defects as failures even when
automated geometry passes; the decisive standard is restrained, connected,
smooth, reachable, believable motion that is still physically aimed at target.

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
  **Validate Mace Head-Guard Drafts**, **GENERATE & PREVIEW**, **CONTACT**,
  **REPLAY / PREVIEW**, **QUALITY STATUS**, **APPROVE**,
  **BUILD FROM MOTION MASTER**, **REBUILD EDITED CONTROLS**,
  **VALIDATE BAKED PATH**,
  **PROMOTE TO MOTION MASTER**, **Repair Helpers**, **Remove Helpers**,
  **Apply Sliders / Refresh Draft**,
  **Preview Attack**, **Save / Approve This Attack**,
  **Generate / Refresh Offensive Suite**, **Validate Humanoid Offensive Suite**,
  **Create / Repair Runtime Hand Sockets**,
  **VIP ANIMATION LIBRARY**, **PLAY**,
  **EDIT**, **SAVE**, **DELETE**, **EXPORT SELECTED**, **IMPORT TO CHARACTER**,
  **Build Approved Animation Pack**, **Validate Last Built Pack**.
