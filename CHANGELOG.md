# Changelog

## 6.0.0

- Published the finished-character look workflow at the requested 6.0 major
  release boundary. Existing 5.4.5 projects and all persisted/exported v1
  contracts remain backward compatible; no 5.4.6 package was released.
- Fixed four-view look projection retaining the old skin across bent limbs when
  the hidden Skin & Bones production body was still displaying a posed rig.
  **LOAD 4-VIEW FOLDER**, **BUILD / REFRESH PREVIEW**, and **BAKE FINAL
  TEXTURE** now evaluate the target-linked, provenance-verified S&B production
  rig in its neutral rest pose.
- Projection mode snapshots and restores the S&B rig's previous display pose.
  It never clears stored pose transforms or Actions and explicitly refuses to
  neutralize `DSB_DAMAGE_RIG`, a generated Damage rig, or any Armature datablock
  used by another object. Legacy visibility snapshots migrate in place; corrupt
  or unresolvable recovery state blocks safely instead of losing the saved pose.
- Variant-owned materials and images now retain explicit Blender fake users so
  inactive looks survive save/reopen and remain switchable without duplicating
  body geometry, Actions, or Damage data.
- Expanded finished-character acceptance to preserve all 21 runtime pose
  matrices, the shared Action, current frame, both authored hand-socket
  transforms/contracts, Damage visibility, and zero-copy look authoring across
  projection entry, preview/bake re-entry, active-projection save/reopen,
  final-image transfer, and ordinary save/reopen.

## 5.4.5

- Replaced the competing top-level family choices with one ordered **LOOK
  VARIANTS · TEXTURE → EXPORT** surface. Finished characters get one obvious
  setup action and a repeatable create → edit/load → preview → save/export loop;
  Skin & Bones handoff ingest and per-look Action/Damage overrides live under
  collapsed Advanced sections.
- Added an ordered Skin & Bones projection bridge directly inside the draft-look
  card: load a four-view folder, reveal the otherwise hidden S&B projection body,
  build/refresh preview, bake, and copy the final UV image into only the active
  Forge look. One-file replacement remains available and now rejects folders
  with an explicit source-art explanation.
- Fixed look switching revealing `DSB_SEGMENT_HEAD` or other detached Damage
  pieces. Forge now restores each mesh's authored intact/default visibility and
  preserves hand-socket position and rotation throughout projection and look
  switching.

## 5.4.4

- Zero-configuration setup now derives the look-set and shipping identity from
  the existing Complete Damage export name, calls the base look `Original`, and
  never asks a finished legacy character for nonexistent S&B family metadata.
- Active and batch look export now perform the exact transactional hidden-source
  proof repair automatically for affected older/resized finished files. The
  artist-positioned socket translation and rotation remain authoritative.
- Added **FINISHED CHARACTER -> TEXTURE MULTIPLIER** for an already-authored
  `DSB_DAMAGE_RIG`. It captures any number of material/image looks while every
  Action, Damage Key, Progressive Damage Site, gore record, and managed socket
  stays shared until an explicit Forge override is created.
- Kept this workflow distinct from imported Skin & Bones Appearance Families:
  Forge proves compatibility from the finished 21-bone rig, weighted body
  topology, UVs, transforms, and material-slot structure and records Forge-owned
  texture approval without inventing Skin & Bones handoff metadata.
- Put Preview, Save, **SAVE + EXPORT**, and **EXPORT ALL READY LOOKS** together
  in the ordered Look Variants card. Saved looks export as independent Complete
  Damage GLBs.
- Added an explicit transactional repair for older/resized authoring files whose
  hidden original source lost its stored preparation transform, plus safe managed
  socket scale normalization before variant export. Neither repair weakens the
  existing full authoring, 21-bone, or socket validation gates.
- Added **BYPASS FAILED CHECKS AND SAVE** beside Preview. It explicitly accepts
  the exact current preview even when pose-health or baked-path checks fail and
  makes the saved Action available to game/export workflows.
- Bypass decisions are never silent: the Action stores a digest-bound
  `dreadstone.offensive_motion_bypass.v1` record containing every bypassed
  error/warning, validation and pose status, timestamp, recipe digest, and the
  exact reviewed-preview digest.
- A bypass automatically becomes stale after any trajectory, curve, socket, or
  canonical-rig change. Normal **APPROVE** remains strict, and failed previews
  still display their real quality status.
- Failed paths accepted by the user receive explicit intended-target metadata
  marked `technicalChecksBypassed`, allowing Animation Clip and game export
  without falsely rewriting the original failed validation report as a pass.

## 5.4.3

- Turned **GENERATE & PREVIEW** into a permissive animation sandbox. It now
  bakes and plays the live sliders and meter values even when pose health or
  weapon-path validation fails; those results remain clearly marked Preview
  Only and cannot be approved.
- Restored the primary aim, windup, power, body, follow-through, arm-relax,
  target-distance, weapon-length, and grip/contact controls to the normal Attack
  Studio surface. Generate no longer discards those values in favor of hidden
  sanitized defaults.
- Added a lightweight selected-weapon preview on the runtime hand socket.
  Changing weapon removes the old proxy immediately, and generation replaces it
  with the current blade, short blade, mace, or two-hand proxy instead of
  leaving a stale longsword visible.
- Kept strict pose, reach, trajectory, preview-proof, and socket checks on
  **APPROVE**. Structural rig errors still stop generation; artistic experiments
  do not.

## 5.4.2

- Replaced the macro-heavy default attack surface with **Attack**, **Weapon**,
  **Target**, and one **GENERATE & PREVIEW** action. Hidden expert state no
  longer leaks into the simple build; the full editor and legacy generators
  remain collapsed under Advanced.
- Made target, proxy, and trail helpers opt-in through **CONTACT** or
  **REPLAY / PREVIEW**, so ordinary generation does not populate the scene with
  editable helper objects.
- Added a 55% minimum arm-extension boundary to Auto Fit, creating a safe reach
  annulus that rejects both folded wrists and over-extension. Thrusts also fail
  if the wrist does not advance in front of the shoulder and stay ahead of the
  elbow during ACTIVE.
- Reworked elbow-pole continuity around the character's authored base pose,
  fixed socket calibration to use the stable bone-parent local transform, and
  tightened FK continuity to clean at 22 degrees or less, warning through 25
  degrees, and hard failure above 25 degrees.
- Reduced production attack baking to sparse rotation curves on spine, chest,
  active shoulder, upper arm, forearm, and hand. The lower body stays authored,
  named phase poses remain exact, and redundant per-frame keys are removed only
  after quality checks pass.
- Made every pose-health warning non-approvable. Geometry PASS remains necessary
  but cannot override folded reach, continuity, or other pose-quality warnings.

## 5.4.1

- Fixed planted feet inheriting leg-IK roll and visibly turning sideways during
  attacks; the bake now preserves the authored base-pose foot orientation and
  fails pose health if position or rotation drifts.
- Reorganized attacks as a macro-first **ATTACK ANIMATION VIP STUDIO**. Simple
  horizontal/vertical aim and five bounded motion macros feed one **REFRESH
  ATTACK** action; all raw target, weapon, trajectory, body, solver, validation,
  and legacy controls now sit behind one collapsed Advanced section.
- Naturalized all five built-in Motion Masters with compact chambers, restrained
  follow-through, subtle lower-body support, and class-specific blade/blunt
  orientations while preserving their stable combat Action IDs.
- Replaced target-center-only contact with entry, top, and side surface anchors.
  Slash and overhead blades select one legal point on the authored strike
  segment; thrust tips and blunt heads remain the leading contact region.
- Added character-specific upper/lower-arm reach measurement, Natural Auto Fit,
  88% comfortable / 92% warning / 98.5% hard reach policy, a two-bone arm IK
  chain, and bounded four-degree shoulder support.
- Removed forced hand translation after no-stretch IK. Motion Studio now solves
  wrist position through the intact arm, applies hand orientation at the solved
  endpoint, and never keys location on shoulder/upper-arm/lower-arm/hand deform
  bones merely to manufacture contact.
- Replaced the CONTACT sign flip in body support with a family-aware smooth
  envelope through all trajectory controls. Added pose-health reporting for arm
  extension, elbow bend, shoulder/torso support, deform translation, solve error,
  and frame angular continuity; unsafe drafts now fail build or approval.
- Added Subtle, Natural, and Forceful Feel presets, Reset to Natural, character-
  adaptive Auto Fit, a concise first-run Attack/Weapon/Target/Feel workflow, and
  collapsed expert sections without removing viewport control editing or legacy
  procedural drafting.
- Improved proxy readability with explicit blade tip/guard/strike segment,
  blunt head/contact region, intended surface anchor, actual baked closest point,
  and unchanged neutral runtime socket calibration.
- Added pure and Blender regressions for Natural Sword/Head and Sword/Torso
  overheads, mace overhead, compact thrust, opposite slash directions, heavy
  diagonal reach, surface contact, blade contact selection, continuous support,
  no deform-chain translation, pose health, approval, persistence, and export
  compatibility. Automated contact remains geometry evidence, not artistic sign-
  off.

## 5.4.0

- Added weapon-first **OFFENSIVE MOTION STUDIO**: editable target dummy and
  mathematical target zones, geometric weapon proxies, explicit trajectory
  controls/families, sacred CONTACT navigation, strike plane/line, and
  phase-colored actual weapon trails.
- Added versioned Motion recipe, Motion Master/library, baked validation, and
  optional targeting handoff schemas. Five built-in one-hand masters cover
  opposite horizontal slashes, overhead, heavy diagonal, and thrust while
  retaining the established combat Action IDs.
- Added a temporary no-stretch arm IK/body-support solve with planted-foot
  constraints that bakes back to the exact canonical 21-bone FK rig, removes
  constraints/helpers, forbids scale animation and hidden starter root motion,
  and leaves runtime sockets intact.
- Approval now fails closed for Motion Studio attacks unless the current baked
  FK socket/proxy path intersects the intended target at CONTACT during ACTIVE,
  matches plane/direction tolerances, and has current preview proof.
- Added explicit reviewed-attack promotion to reusable target-relative Motion
  Masters, Character Variant Action copy-on-write invalidation, save/reopen
  repair, helper lifecycle/export exclusion, and optional non-homing launch-
  envelope metadata in Animation Pack and Complete Damage sidecars.
- Preserved 5.3 Character Variant Families, 5.2.2 zero-time temporary runtime
  staging, `dreadstone.offensive_action.v1`, existing approved Actions, and the
  full eight-generator workflow under LEGACY / PROCEDURAL DRAFTING.
- Added deterministic target/intersection/plane/direction/schema/invalidation
  tests and Blender acceptance for overhead, opposite slashes, thrust, FK bake,
  sockets, helper cleanup, persistence, approval, and export exclusion. Numeric
  geometry validation is not a claim of human artistic approval.

## 5.3.0

- Added Character Variant Families using the exact approved Skin & Bones 2.2.0
  `skin-and-bones-appearance-family-handoff-v1` metadata, including strict
  technical-body fingerprint and canonical rig/coordinate compatibility gates.
- Added a persistent shared Forge authoring layer with sparse copy-on-write
  Action, Damage Key, and Progressive Damage Site override maps. Compatible
  appearance-only variants create no duplicate Actions or Damage Keys.
- Added compact `SHARED` / `INHERITED` / `OVERRIDE` UI, direct appearance
  switching, confirmed shared edits, single-item override/revert operations,
  and an explicit lock against accidental family-wide Damage edits.
- Offensive Actions inherit their existing approval and socket/timing recipes;
  an explicit variant override becomes a new draft and must pass the normal
  preview and approval gate.
- Progressive Site overrides clone only the Site and its distinct assigned
  Light/Medium/Heavy Damage Keys, preserving coherent stage references while
  unrelated Damage stays inherited.
- Complete Damage export now resolves the selected appearance plus shared and
  overridden Forge content, emits versioned family/variant provenance, and can
  export every ready variant as an independent GLB and sidecars.
- Preserved the 21-bone `DSB_DAMAGE_RIG`, family-shared managed sockets,
  zero-time temporary runtime Action staging, declared clip duration checks,
  offensive timing validation, and standalone 5.2.2 project behavior.
- Added pure family/resolution regression coverage and Blender 5.1.2
  active-switch, copy-count, override/revert, and save/reopen acceptance.

## 5.2.2

- Complete Damage export now shifts only temporary runtime Action clones to a
  zero-based timeline, so authored frame-1 Actions export with their first glTF
  sample at `0.0` and their last sample at `clipDurationSeconds`.
- Final GLB validation now independently requires zero minimum time, declared
  maximum time, declared duration, and a contiguous WINDUP / ACTIVE / RECOVERY
  contract ending at the normalized offensive clip end.
- Expanded the Complete Damage regression to prove multiple frame-1 Actions,
  source Action immutability, exact runtime timing, the 21-bone
  `DSB_DAMAGE_RIG`-only skeleton, and unchanged hand socket helpers.

## 5.2.1

- Added visible per-attack timing and motion sliders for all eight humanoid
  offensive drafts.
- Added selected-draft refresh and playback controls so attacks can be reviewed
  on the current character before approval.
- Offensive approval now requires preview proof for the current generated
  draft; regenerating a draft clears that proof.
- Added persistent `dreadstone.offensive_recipe.v1` authoring metadata so
  character-specific settings survive suite refresh, approval, and `.blend`
  save/reload without changing built-in humanoid defaults.

## 5.2.0

- Added eight reviewed humanoid offensive Action generators covering one-hand
  and two-hand slash, overhead, thrust, and committed heavy motion families.
- Added strict `dreadstone.offensive_action.v1` clip metadata with stable
  combat IDs, weapon compatibility, socket roles, commitment, and contiguous
  WINDUP / ACTIVE / RECOVERY intervals expressed in seconds.
- Added artist-adjustable, idempotent right/left hand attachment helpers and
  `dreadstone.attachment_sockets.v1` runtime sidecar export. Helpers remain
  authoring-only and never alter the canonical rest skeleton or skin joints.
- Complete Damage export now rejects malformed, duplicate, draft, unapproved,
  socket-incompatible, or duration-inconsistent offensive capabilities and
  validates the completed GLB without leaking helper nodes.

## 5.1.3

- Fixed Complete Damage export allowing Blender 5.1.2 `ACTIONS` mode to scan
  every bone Action when a single armature was selected. Source-owned
  Idle/Walk families could therefore appear beside intended damage-rig clips.
- Added an explicit role-validated runtime graph. Complete Damage Asset ships
  `DSB_DAMAGE_RIG` as the only intended runtime skeleton;
  `SBF_ProductionRig`, `SBF_CLEAN_CHARACTER`, and
  `DSB_SOURCE_MODEL_PROTECTED` remain authoring/provenance data.
- Added non-destructive approved-Action auditing and temporary
  `DSB_DAMAGE_RIG` Action/NLA staging. Runtime-owned kinds supersede matching
  source families; compatible source-only clips may be mirrored after exact
  skeleton checks. Blender's Action allow-list is mandatory and global
  single-armature Action discovery is disabled.
- Upgraded completed-GLB diagnostics to
  `dreadstone.final_glb_validation.v2`, validating skeleton/joint ancestry,
  intact and rigid bindings, required bones, exact animation inventory,
  channel targets, owner/kind extras, and sampler duration.
- Added a self-contained Blender 5.1.2 regression with duplicate source/runtime
  Idle and Walk Actions, morphs, rigid pieces, raised gore, portable stains,
  transactional rollback, source sidecar provenance, and clean reimport.

## 5.1.2

- Fixed Approved Animation Pack export rejecting visually correct local
  Actions that retained pre-canonical `-Y` or unversioned anatomy metadata.
  Export now refreshes approved Action provenance from the selected exact Skin
  & Bones Y+ rig before validation, without changing curves, timing, or poses.
- Approval metadata errors are no longer silently ignored.

## 5.1.1

- Extended animation-only Draft Base Poses to Flank Hurt and Mace Guard.
  One shared Hurt base drives both left/right drafts; one shared Mace Guard
  base drives all three guard variants. Capture and clear regenerate every
  affected preview while preserving the rest rig, weights, and root.

## 5.1.0

- Reversed the canonical Walk thigh swing and heel/toe roll basis so the
  airborne foot travels from rear `-Y` to forward `+Y` on
  `SBF_HUMANOID_YPLUS_V1`, instead of visually walking backward.
- Corrected the Walk **Elbow Bend** and optional elbow pose-polish signs.
  Increasing positive bend now increases anatomical flexion by default;
  **Invert Elbows** is again a true exceptional-direction override.
- Added live Townsman trajectory and joint-angle acceptance proving forward
  foot travel, increasing elbow flex, and unchanged grounded Death behavior.

## 5.0.0

- Fixed the Humanoid Idle panel terminating at **Edit Idle Base Pose** in
  Blender 5.1. The button used an invalid `POSE_DATA` icon identifier, causing
  Blender to abort the remainder of the panel draw and shorten the scrollbar.
- Added a regression assertion that all Idle Base Pose controls use the valid
  `POSE_HLT` icon path so the Generate button and every section below Idle
  remain reachable.

## 4.2.1

- Corrected the Skin & Bones `+Y` left/right signs for **Arm Drop to Sides**;
  increasing the control now lowers both complete arm chains from the A-pose
  toward the torso.
- Added a non-destructive, animation-only **Draft Base Pose** workflow for
  Humanoid Idle. Artists can enter Pose Mode, relax or reposition mapped
  bones, capture the stance, and immediately preview breathing and weight
  shift layered over it without altering the armature rest pose or weights.
- Stored captured poses by semantic bone role with exact
  `SBF_HUMANOID_YPLUS_V1` provenance, excluded the top-level `root` to preserve
  in-place motion, and stamped generated Idle Actions with their base-pose
  recipe. The generic pose store is ready for later weapon, guard, and attack
  generators.
- Added live Townsman acceptance for manual base-pose capture, additive Idle
  motion, arm lowering, seamless endpoints, and zero root drift.

## 4.2.0

- Adopted Skin & Bones Forge 2.1.0's exact
  `SBF_HUMANOID_YPLUS_V1` handoff. Humanoid authoring now consumes stored rig
  metadata and the 21-role semantic mapping without importing a canonical GLB.
- Made Blender `+Y` the sole humanoid forward direction. Unversioned and `-Y`
  rigs or Action clips are rejected with a Skin & Bones conversion message;
  legacy yaw and knee/elbow inversion defaults are gone.
- Added a seamless, in-place humanoid idle with breathing, weight shift, arm
  drop, protected draft/approval metadata, and portable clip support.
- Reworked terminal death grounding to translate the top-level `root` and
  validate the weighted pelvis/lower-spine/middle-spine/chest regions
  independently, preventing arm contact from masking a floating torso.
- Added live Townsman-derived Skin & Bones acceptance for Idle, Walk, Hurt, and
  all four Death styles.

## 4.1.1

- Added a signed, per-frame death grounding bake so generated collapse Actions
  can move down to the floor as well as recover from penetration.
- Added low-profile terminal contact poses and validation to Chest Hold,
  Faceplant, and Knees First, including explicit support for rigs that disable
  rotation inheritance on deform chains.
- Added **Instant Unconscious**, a fast, brace-free and wiggle-free collapse
  that reaches a fully limp terminal pose in under one second by default.
- Raised the validated per-asset triangle allowance for raised gore from
  48,000 to 60,000.

## 4.1.0

- Added centralized, versioned Creature Anatomy Profiles with deterministic
  detection, explicit override, one orientation authority, readiness
  validation, capability gating, persistence, and additive export metadata.
- Migrated existing humanoid aliases and Animate Anything mapping into
  `DSB_HUMANOID_V1` while preserving public compatibility functions and current
  generators.
- Added the architectural `DSB_QUADRUPED_MAMMAL_DIGITIGRADE_V1` semantic
  contract, four distinct limb/contact families, variable spine/neck/tail/toe
  chains, damage-region templates, synthetic Blender fixture coverage, and
  explicit non-production generator gates.
- Added the AnyTop access/licensing feasibility audit, production fixture
  requirements, and an empirical multi-skeleton/multi-seed motion corpus plan.

## 4.0.0

- Fixed broad smooth damage stains disappearing from exported GLBs. Forge now
  packages one portable PBR overlay per Damage Key/ownership role, writes exact
  progressive-stage bindings, and validates the completed GLB separately from
  raised/inlay geometry.
- Added identity-preserving managed Damage Key renames. Existing stable IDs and
  progressive assignments follow the new artist name, generated gore is safely
  rebuilt, and the export latch is invalidated until validation is approved
  again.
- Added independent left/right **Elbow Flex** controls inside Arm & Hand Pose
  Polish. They remain rotation-only and overlay newly generated animation
  drafts without resizing or reweighting the character.
- Reworked mace head-guard generation around a longer recognition, covering,
  protected hold, and interruptible release. New Cowering, Defensive, and
  Zombie-Insect Attack styles preserve the useful legacy shape while exposing
  arm cover, elbow, forearm wrap, hunch, torso curl, head tuck, crouch,
  asymmetry, and release controls.
- Replaced the scale-dependent forearm-height failure with world-space
  coverage guidance. A distant forearm can warn the artist but never blocks
  approval or Approved Animation Pack export.
- Added explicit legacy animation-clip provenance and acceptance coverage.
  3.20.1 v1 clips import with Action curves, keyframes, names, and their
  original settings payload unchanged; new 4.0 controls are only used when a
  new draft is deliberately generated.

## 3.20.1

- Removed the Safe Resize wrapper prerequisite from Approved Animation Pack
  export. A selected native-sized armature now discovers sibling skinned meshes
  through their Armature modifiers, exports without hierarchy mutation, and
  records `NATIVE_RIG` sizing metadata when no wrapper exists.
- Added per-frame floor grounding to generated death/collapse Actions plus
  approved-pack floor validation. The configured Ground Sink is baked into the
  hips translation so preview and exported runtime motion share the same floor
  contract.
- Clarified that saved/approved Actions remain editable in the authoring
  `.blend`; force sampling bakes the delivery GLB and never requires reimporting
  that GLB before continuing gore or animation work.

## 3.20.0

- Added first-class, versioned Progressive Damage Sites with stable site,
  stage, and Damage Key IDs persisted in the deformation registry.
- Added independently authored Light, Medium, and Heavy stage assignment,
  stage-to-VIP-workflow focus, isolated Randomize/Save status tracking, safe
  metadata duplication, and non-destructive metadata deletion.
- Added pure adjacent crossfade evaluation with ordered severity anchors,
  smoothstep interpolation, a maximum of two adjacent active morphs, and
  midpoint replacement for complete detailed-gore assemblies.
- Added managed, snapshot-restoring progression preview; technical crossfade
  sampling across available rest/walk/hurt/collapse contexts; explicit
  draft/export states; and resident, visible, and transition cost reporting.
- Extended the damage manifest and clean-reimport contract with explicit
  `progressiveDamageSites` metadata while preserving all 3.19 Damage Keys,
  child Stamps, Blueprints, raised/inlay components, and non-progression export.

## 3.19.0

- Added a compact **VIP ANIMATION LIBRARY** at the top of the Animation
  workspace. It groups current drafts and saved Actions by locomotion,
  reactions, combat, and other clips; Action names are editable in place.
- Added one-click **PLAY**, **EDIT**, **SAVE**, and **DELETE** lifecycle
  controls. Editing a saved clip creates a safe working Action, restores its
  captured custom sliders when available, and SAVE explicitly overwrites the
  original name/identity while reconnecting active Action and NLA users.
- Added native portable animation clips: **EXPORT SELECTED** writes one
  compressed `.blend` Action plus a readable JSON manifest, and **IMPORT TO
  CHARACTER** blocks missing bones or changed parent chains while warning
  about rest-orientation, proportion, and pose-translation differences.
- Replaced factory-preset authoring with the collapsible **VIP DAMAGE WORKFLOW**:
  clear Damage Key cards, unmistakable **WORKING ON** focus, independent
  per-key Preview toggles, and visible child Stamp alternatives.
- Added simultaneous multi-key preview persistence. Selecting a key changes
  editing focus without soloing it; new keys save multiple Stamp alternatives
  while previewing exactly one active Stamp per key.
- Replaced the old low-leverage front controls with six strong Impact macros
  (**AREA**, **DEPTH**, **FALLOFF**, **EDGE DAMAGE**, **DISTORTION**,
  **ASYMMETRY**) and six direct Gore controls.
- Added the five-control **COHESIVE LEGACY SURFACE GORE** deck: **SURFACE
  MASS**, **RELIEF**, **NUCLEUS**, **FOLDS**, and **REDNESS**. These macros
  expose the existing raised-gore manual controls as a coherent high-leverage
  surface system instead of relying on scattered triangular overlay patches.
- Added deterministic clusters of closed, lobulated solid-tissue nuclei to
  each raised component. They spread across the deepest-response third of the
  impact, vary in scale, aspect, orientation, and folds, inherit source
  skinning, stay inside the per-key triangle budget, use the crushed-tissue
  material role, and compose additively with the full inlay channel.
- Added one master **RANDOMIZE DAMAGE** transaction that deterministically
  derives independent impact and gore seeds and schedules one managed preview.
- Added `HYBRID_ADDITIVE` gore with independent 0.0–1.0 raised and inlay
  channels. A 1.0 + 1.0 recipe generates full raised and full recessed
  components with stable component nodes, IDs, digests, manifests, validation,
  preview, and export behavior.
- Added `dreadstone.damage_blueprint.v1` and its JSON library. Blueprints save
  macros, seeds, texture contributions, semantic intent, and capture-relative
  scale ratios while excluding object names, topology, indices, coordinates,
  and generated mesh bytes. Applying always rebinds to a fresh destination
  capture, enabling adaptive reuse across regions and characters.
- Removed preset operators and preset controls from registered/user-facing
  workflows while retaining internal migration data for older authored files.
- Fixed paired-region Damage Key creation failing during preview with an
  undefined detached-mesh reference. The same button now accepts one vertex,
  multiple vertices, one face, or one connected face patch, and a cancelled
  transaction immediately rebuilds the panel cache so no phantom Stamp remains.
- Fixed raised-gore component ownership being overwritten by an internal face
  island list. Paired hybrid saves now retain all four final nodes (attached
  raised/inlay and detached raised/inlay), pass stable-ID validation, and show
  the saved gore without discarding the Damage Key or Stamp recipe.
- Fixed legal Gore macro combinations placing the clot plate shallower than
  the generated cavity rim. Internal clot/tissue medians are now projected
  into the measured rim-to-liner interval, so slider edits and VIP Save retain
  strict surface-to-rim-to-clot/tissue-to-liner depth order.
- Fixed per-key **PREVIEW OFF** leaving the live stain material or temporary
  gore geometry visible through the intact mesh. Preview toggles now govern
  final nodes, preview-only nodes, the stain attribute, and its temporary
  material/state as one lifecycle.
- Made the VIP preview contract explicit and executable: debounced macro edits
  and Randomize update the unsaved look, FAST shows its live stain, BALANCED
  adds temporary raised/inlay geometry, and **UPDATE GORE PREVIEW** refreshes
  immediately. Save now reads clearly as the commit/final-validation step.
- Fixed a macro-edit boundary mismatch where a generated Damage Key could
  remain slightly beyond its newly derived maximum world displacement. Preview
  and final rebuild coordinates are now independently projected into the
  current recipe cap before writing the shape key; strict validation remains
  unchanged.
- Bumped normalized gore recipes to v6 while preserving v1-v5 digests and
  keeping new surface mass/nucleus geometry disabled on untouched legacy
  records. Damage Blueprints now round-trip all five surface macros.
- Fixed valid v1 Damage Blueprint libraries saved before cohesive surface
  macros being rejected as corrupt. Their original blueprint and library
  digests are now verified in the legacy shape, then migrated to the current
  canonical records when refreshed or saved.
- Fixed the VIP Damage Key and Stamp cards disappearing after file loads,
  region switches, captures, or Stamp edits. Normal runtime-cache invalidation
  now immediately restores the lightweight active-region inventory from
  persisted authoring metadata without doing mesh work during panel draws.

## 3.18.0

- Added recessed `CAVITY_INLAY` gore that follows the final deformed surface without editing source topology, with closed manifold liners, near-host rims, bounded proudness, scale-relative depth/separation, optional clot/crushed-tissue/exposed-bone layers, normalized deform-bone skinning, and exportable source/depth/layer attributes.
- Added the top **GORE CONTROL DECK** and six-control **GORE PEDAL**: **EXPOSURE**, **CAVITY**, **CLOT FILL**, **BREAKUP**, **WETNESS**, and **VARIATION**, plus independent deterministic gore-seed randomization, preview, commit, revert, clear, final-preview, validation, measurements, MACRO/MANUAL behavior, and one-transaction dirty/preview semantics.
- Added six strongly differentiated identities: Bruised Dent, Bloody Crater, Dark Clot Cavity, Crushed Tissue, Exposed Cranium, and Ragged Impact.
- Added preview-only BALANCED/FINAL gore geometry that cannot leak into final nodes or manifests; failed previews/commits preserve the previous valid state.
- Preserved `STAIN_ONLY` and explicit `LEGACY_RAISED` behavior, three-material/fiber/inner-barrier contracts, public identifiers, old recipe migrations, and unchanged legacy digest behavior.
- Added Blender-free cavity generation and a deterministic matrix over identities, macro endpoints, seeds, scales, manifoldness, triangle budgets, layer order, proudness, separation, seed preservation, and invalid input rejection.

## 3.17.0

- Added the compact top **IMPACT CONTROL DECK** with the five normalized **SIZE**, **CRUSH**, **PROFILE**, **EDGE SAFETY**, and **CHAOS** macros, master seed, deterministic identity, preview quality, status, Randomize, Preview, Commit, Revert, and Clear actions.
- Centralized deformation, stamp, feather, displacement, and gore ranges in a Blender-free parameter-contract layer used by RNA declarations, normalization, validation, presets, macro conversion, migration, and export checks. Every exposed numeric endpoint is accepted inclusively, including Blender RNA's float32 representation of an exact endpoint.
- Added guarded macro and seed transactions that validate first, assign derived physical settings without recursive callbacks, mark dirty once, increment one generation token, and schedule at most one managed preview.
- Added explicit MACRO and MANUAL/CUSTOM behavior, macro fitting, confirmed return to macro control, additive versioned recipe metadata, and safe legacy format-1–4 migration without changing unchanged legacy recipe digests.
- Added a machine-readable property audit, geometry-response diagnostics, ordinary endpoint/determinism tests, and Blender 5.1.2 Impact Pedal acceptance across all six families, paired/core regions, macro endpoints, and repeated seeds.

## 3.16.3

- Fixed **Prepare Character for Damage Authoring** on production rigs whose waist surface is distributed across the spine, torso, limb, and head vertex groups. Seam analysis, face partitioning, and contour reconstruction now use the complete distal deform subtree versus all other deform bones instead of comparing only the two bones immediately beside the joint.
- Non-deforming root anchors and controls are excluded from seam weights, while deforming hand bones remain on the correct forearm side. This closes deterministic waist contours without weakening topology or readiness gates.
- Added an end-to-end Blender 5.1.2 regression using a saved Skin & Bones production character; one-click preparation and generated authoring validation both pass without saving the source blend.

## 3.16.2

- Restored the complete Animation workspace in the task UI: rig mapping, ground preview, arm/hand pose polish, walk, collapse, flank-hurt, mace-guard, approval, safety, and approved-pack controls are available independently of damage-authoring state.
- Mace head-guard generation now applies the shared rotation-only arm and hand refinement sliders, allowing the two-arm, left-arm, and right-arm guards to be customized before versioning/approval.
- Split Advanced into remembered collapsible **Character & Source Workflows**, **Trauma, Gore, Compound & Legacy Tools**, and **Diagnostics & Crash Support** sections. Trauma is further divided into collapsible region, deformation, capture, stamp, gore, compound, and preview/validation groups to remove the forced full-panel scroll.

## 3.16.1

- Unified deformation weights, surface stains, raised-gore ownership, and attached/detached/core inspection into one atomic Blender preview state. Inactive or zero-weight deformations can no longer leave generated gore visible through intact skin.
- Added one prominent **CLEAR DAMAGE PREVIEW** operation across ordinary workflows. It clears temporary stain resources, zeros managed morphs, and hides raised gore while preserving recipes and generated export meshes.
- Made key/region switching, live-preview disable, preview quality `OFF`, intact/detached presentation, event zero, and compound child activation use the same lifecycle. Compound previews now transition all participant morphs and gore nodes together.
- Separated viewport presentation from export ownership. Damage export snapshots the exact preview, forces the inactive morph/gore state, exports, and restores the snapshot in `finally` even when validation or export fails.
- Added independent additive **Muscle Fiber Contribution** and **Gore Color Contribution** sliders. Raised-gore materials use packed exportable textures composed from both signals without one replacing the other.
- Added atomic lifecycle regression coverage for clear/re-preview, stale-key visibility, preserved recipes/meshes, export snapshot restoration, and 50 repeated cycles without leaked preview resources.

## 3.16.0

- Replaced one-prism-per-source-face raised gore with deterministic edge/centroid refinement, interpolated skin weights, relaxed thickness, rounded center bulges, and seed-driven tangent jitter so imported triangulation no longer dominates the silhouette.
- Packaged the four supplied muscle-fiber rotations plus a 2x2 atlas. Every refined gore facet receives an independent master-seed-selected direction through exportable glTF UVs and image-texture materials.
- Added an exportable compromised inner-reddening barrier as a closed secondary layer just inside every open gore-island boundary, with artist controls for width and compromise strength.
- Added **Randomize Master Gore Seed**. The one master seed changes the complete overlay: stain breakup, selected islands, fragments, thickness, clot/edge material response, organic geometry, and fiber directions.
- Added organic irregularity, surface roundness, muscle-fiber texture, and inner-barrier settings to normalized recipes, digests, portable metadata, rebuild staleness, UI, and validation.
- Added Blender 5.1.2 runtime acceptance for manifold multilayer geometry, triangle budgets, atlas UVs, all four fiber directions, three material roles, packaged image paths, and source-surface ownership.

## 3.15.1

- Fixed the Advanced workspace panel scope so cached diagnostics render correctly while using Preview/Rebuild Current Gore and other expert controls.
- Added a regression contract for the Advanced helper's explicit deformation-authoring dependency and verified the exact draw path in Blender 5.1.2.

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
