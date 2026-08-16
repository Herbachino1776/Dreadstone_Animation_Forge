# Dreadstone Animation Forge

Dreadstone Animation Forge `6.0.1` is a proprietary Blender add-on for
animation drafting and compatibility-preserving damage authoring. The supported
release runtime is Blender `5.1.2`.

An already-finished `DSB_DAMAGE_RIG` now gets one ordered **LOOK VARIANTS ·
TEXTURE → EXPORT** loop. Start with the current look, make an editable texture
copy, paint it or load a final projected/baked Base Color, preview, then Save or
Save + Export. The finished rig, Actions, Damage Keys, Progressive Damage Sites,
gore, and artist-positioned sockets remain one shared authoring layer; adding a
look does not copy them. The normal UI never asks the artist to choose a family
implementation. Exact Skin & Bones 2.2 handoff import remains available under
Advanced and is never counterfeited for a legacy finished character.

Forge 4.0 keeps the compact VIP workflow built around
Damage Keys, visible child Stamp alternatives, strong macros, one-click
deterministic randomization, additive raised + inlay gore, and portable
topology-independent Damage Blueprints. It adds first-class Progressive Damage
Sites: an artist assigns three complete, independently authored Light, Medium,
and Heavy Damage Keys, previews adjacent replacement crossfades, validates
actual evaluated geometry, and exports an explicit runtime contract. Forge
never invents or scales one stage from another. A dedicated cohesive surface deck can
form irregular connected relief or a closed lobulated tissue nucleus instead
of limiting raised gore to scattered face patches. Broad smooth stains now
export as stage-owned standard glTF PBR overlay meshes with RGBA `COLOR_0`
masks instead of depending on Blender-only preview attributes.

The Animation workspace also includes a compact VIP library for playing,
editing, overwriting, deleting, and renaming saved Actions. Individual clips
can be exported as native `.blend` Action packages and imported onto another
humanoid after bone/hierarchy compatibility checks.

Forge 4.2 adopts the Skin & Bones Forge 2.1 canonical humanoid contract:
`SBF_HUMANOID_YPLUS_V1`, Blender `+Y` forward, `+Z` up, and top-level `root`
motion. Animation Forge consumes the rig metadata and semantic bone mapping
already stored on a Skin & Bones character; it does not import or bundle a
separate canonical GLB. Unversioned and `-Y` humanoids are rejected and must be
re-rigged or converted in Skin & Bones.

Humanoids now have a seamless in-place breathing/weight-shift idle. Walk,
hurt, guard, and death generators all use the same `+Y` basis with direct
canonical knee and elbow defaults. Every generated death is grounded through
the top-level `root` and validates pelvis, lower spine, middle spine, and chest
contact so an arm touching the floor cannot leave the torso floating.

Idle also has an animation-only **Draft Base Pose**. Keep the canonical high
A-pose as the rigging/rest pose, click **Edit Idle Base Pose**, relax or pose
the mapped bones in Pose Mode, then click **Capture Base + Preview Idle**.
Breathing and weight shift are regenerated on top of that stance; the root is
excluded so the loop remains in place. **Arm Drop to Sides** is an optional
additive shortcut and now lowers both complete arm chains correctly for `+Y`.

Forge 4.1 introduces centralized, versioned Creature Anatomy Profiles. The
existing humanoid mapping remains compatible, while the first digitigrade
quadruped profile provides semantic core, spine/neck/tail, four distinct limb,
contact, orientation, capability, and future damage-region contracts. This is
an architecture milestone: it does not expose production quadruped gait,
attack, reaction, paw-IK, or damage generators, and its synthetic test rig is
not a canonical production skeleton.

Animation Forge also includes independent left/right elbow-flex polish, longer
natural head-guard and cowering timing, editable cover/wrap/hunch/tuck controls,
and a selectable Zombie-Insect Attack generator shape. Forearm-to-head
coverage is advisory and never blocks approval or export. Portable humanoid
Action clips must carry the current Skin & Bones canonical rig and `+Y`
anatomy metadata.

Forge 5.2 adds a reviewed humanoid offensive suite and a runtime armament
handoff. Eight attack drafts carry explicit weapon classes, hand socket roles,
stable combat IDs, and contiguous WINDUP / ACTIVE / RECOVERY timing in seconds.
Managed right/left hand socket helpers remain editable in the authoring file
but export only as versioned sidecar transforms; they do not become runtime
bones or GLB nodes. See
[the runtime attachment and offensive contract](docs/RUNTIME_ATTACHMENT_AND_OFFENSIVE_CONTRACT.md).

Forge 5.2.2 introduced character-specific attack sliders and a mandatory preview
gate, and makes Complete Damage runtime animations zero-time-based. Authored
Actions keep their normal frame ranges in the `.blend`; export shifts only
temporary copies so each GLB clip begins at `0.0` seconds and ends at its
declared `clipDurationSeconds`.

Forge 5.3 adds Character Variant Families for approved Skin & Bones 2.2.0+
appearance exports. Compatible appearances share one normal Action, Damage,
Progressive Site, gore, and socket authoring layer. A variant stores only its
appearance and deliberate copy-on-write overrides; adding a texture-only
variant creates no duplicate Actions or Damage Keys. See the
[Character Variant Family contract](docs/CHARACTER_VARIANT_FAMILY_CONTRACT.md).

Forge also supports the inverse production order: start from a finished
Forge Damage character, turn it into a texture family, then capture additional
looks. Its optional Skin & Bones bridge reveals the hidden full-body projection
target on its provenance-verified neutral S&B production rig, runs
folder/preview/bake in order, restores the prior S&B display pose, and copies
only the final UV texture back into the active Forge look. The runtime Damage
Rig, Actions, and artist-positioned sockets never change. Inactive look
materials/images remain packed and persistent through save/reopen. Forge
fingerprints the actual finished technical body and keeps appearance approval
explicitly Forge-owned.

Forge 5.4 adds **OFFENSIVE MOTION STUDIO**, a target-constrained weapon-first
workflow. Artists place a mathematical target dummy, choose a target zone and
weapon proxy, edit an explicit horizontal/diagonal/overhead/thrust trajectory,
solve the canonical body around that path, bake ordinary FK curves, and then
validate the real baked hand/socket/proxy path during ACTIVE. Five geometry-
valid one-hand starter masters ship; reviewed approved attacks can be promoted
deliberately for reuse on another compatible humanoid. The existing eight
body-first generators remain under LEGACY / PROCEDURAL DRAFTING. See the
[Offensive Motion Studio contract](docs/OFFENSIVE_MOTION_STUDIO_CONTRACT.md).

Forge uses an animation sandbox. In **ATTACK ANIMATION
STUDIO**, choose **Attack**, **Weapon**, and **Target**, adjust the visible aim,
motion, distance, and weapon meters, then click **GENERATE & PREVIEW**. Every live
control is baked and playback starts even when the experiment fails pose or
weapon-path checks. Failed experiments are Preview Only; **APPROVE** remains
strict. If a technically rejected animation is artistically right, **BYPASS
FAILED CHECKS AND SAVE** accepts the exact current preview for game export and
stores every overridden failure in a digest-bound Action audit record. The
selected weapon is rebuilt visibly on the hand socket every time, so
switching to a mace, dagger, or other proxy cannot leave the previous longsword
as the Motion Studio preview.

The production quality gate rejects a wrist folded below 55% arm extension, preserves
the existing 92% near-lock warning and 98.5% hard reach ceiling, and requires
clean per-frame FK continuity at or below 22 degrees. A step above 25 degrees is
a hard failure; the interval between is a non-approvable warning. The bake now
samples only spine, chest, active shoulder, upper arm, forearm, and hand after a
single base-pose key, then removes redundant keys while preserving authored
phase poses. Lower-body motion is left exactly as authored. Expert target,
proxy, trajectory, body, reach, and tolerance controls remain behind the
collapsed Advanced section. Existing approved Actions and saved 5.4.0/5.4.1
promoted masters are not silently rewritten.

## Install and open

1. Download `Dreadstone_Animation_Forge_v6_0_1.zip`.
2. In Blender choose **Edit > Preferences > Add-ons > Install from Disk**.
3. Select the ZIP without extracting it and enable the add-on.
4. In the 3D Viewport press `N`, open **Dreadstone**, then choose
   **Damage Authoring**.

## Quick start

1. Import the source GLB and run **Prepare Character for Damage Authoring**.
2. Open **VIP DAMAGE WORKFLOW**, activate a region, and select one vertex,
   multiple vertices, one face, or one connected face patch.
3. Click **CREATE DAMAGE KEY FROM SELECTION**. The highlighted card clearly
   identifies the key being edited.
4. Toggle each Damage Key independently; any number of key previews can be on
   together. Pick one visible child Stamp alternative per key.
5. Tune the six Impact macros, six additive Gore macros, and the five
   **COHESIVE LEGACY SURFACE GORE** macros, or click **RANDOMIZE DAMAGE**.
   **SURFACE MASS** joins the raised patch, **NUCLEUS** creates solid internal
   tissue, **FOLDS** makes it lobulated, and **REDNESS** shifts the material
   response toward visible blood-red tissue. FAST previews the current stain;
   BALANCED adds temporary raised/inlay geometry. **UPDATE GORE PREVIEW**
   refreshes now.
6. Click **SAVE DAMAGE KEY + STAMP + GORE** only when the look is ready to
   commit and validate.
7. Save useful recipes with **ADD CURRENT RECIPE**. Apply them to a fresh
   capture on a different region or character from the adaptive Blueprint
   library.
8. Validate morphs, gore, and the complete asset before exporting the damage
   GLB and manifest.
9. Optionally create a **PROGRESSIVE DAMAGE SITE**, assign three saved custom
   Damage Keys, preview severity, validate all crossfade states, and explicitly
   enable the site for export.

At `RAISED AMOUNT = 1.0` and `INLAY AMOUNT = 1.0`, hybrid gore generates both
channels at full strength; it is not a half-and-half blend.

The authoritative procedure and complete button inventory are in the
[user workflow guide](docs/USER_WORKFLOW_GUIDE.md). Runtime consumers should
also read the [core/compound export contract](docs/CORE_COMPOUND_EXPORT_CONTRACT.md)
and [gore geometry export contract](docs/RAISED_GORE_EXPORT_CONTRACT.md).
The [Complete Damage runtime export contract](docs/RUNTIME_DAMAGE_EXPORT_CONTRACT.md)
defines the shipping skeleton and animation boundary.
Progressive runtime consumers must also follow the
[Progressive Damage Site contract](docs/PROGRESSIVE_DAMAGE_SITE_CONTRACT.md).
Animation and retargeting consumers should read the
[Creature Anatomy Profile contract](docs/CREATURE_ANATOMY_PROFILE_CONTRACT.md)
and [native Action package contract](docs/ANIMATION_PACKAGE_CONTRACT.md).

Complete Damage Asset ships `DSB_DAMAGE_RIG` as the runtime skeleton.
`SBF_ProductionRig` remains source-authoring provenance and is not included in
the runtime GLB. The source object and protected source copy likewise remain in
the `.blend` and sidecar provenance, not in the game asset.

## Persistence and compatibility

Damage Blueprints contain macros, seeds, relative scale ratios, and semantic
intent, including the cohesive surface controls. They never contain source
object names, topology fingerprints, vertex indices, or generated mesh bytes,
so the destination capture—not the source topology—controls placement.

Older authored deformation and gore records remain migration-readable. Legacy
factory recipe identifiers are internal compatibility data only and are not
offered as authoring presets.

Humanoid Action packages without exact `SBF_HUMANOID_YPLUS_V1` and `+Y`
anatomy metadata are intentionally rejected. AnyTop is an optional external
research reference, not a Forge dependency; Forge bundles no ML runtime,
checkpoint, dataset, or third-party motion source. See the
[AnyTop feasibility audit](docs/research/ANYTOP_FEASIBILITY_AUDIT.md).

## License

Copyright © Dreadstone. All rights reserved. No permission is granted to copy,
modify, distribute, sublicense, sell, or create derivative works except under a
separate written license from the copyright holder. See [LICENSE](LICENSE).
