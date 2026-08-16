# Offensive Motion Studio contract

Forge release: `5.4.5`

## Product law

The 5.4 weapon-first architecture is unchanged:

```text
TARGET
-> WEAPON PATH
-> BODY SOLVE
-> FK BAKE
-> BAKED WEAPON PATH VALIDATION
-> PREVIEW
-> APPROVAL
```

Forge 5.4.5 keeps the 5.4.1 intact-chain law and makes pose quality part of the
production gate. A valid hit must be achieved without IK stretch or local
dislocation of shoulder, upper arm, lower arm, or hand; the wrist path must stay
inside a safe reach annulus, and the baked chain must remain continuous. The
weapon still has to contact the authored target during ACTIVE on the intended
family, plane, and direction.

Motion Studio authors in canonical character-local space (`+Y` forward, `+Z`
up, `+X` anatomical right). It does not implement collision, hit decisions,
runtime tracking/homing, weapon assets, or damage. After commitment the baked
path is fixed and a moving target can dodge.

## Production workflow and expert access

The default panel exposes Attack, Weapon, Target, **LET ME COOK** aim/motion
sliders, target-distance and weapon meters, **GENERATE & PREVIEW**, optional
**CONTACT**, **REPLAY / PREVIEW**, **BYPASS FAILED CHECKS AND SAVE**, quality
status, and **APPROVE**. Generate &
Preview consumes every live setting, bakes it, validates it, records preview
proof, and starts playback regardless of quality status. This is intentionally
permissive: a failed experiment remains visible as Preview Only while Approval
stays blocked. The bypass button explicitly saves the exact current preview for
game/export use despite those failures. Promoted masters retain their
deliberately reviewed stored recipe values.

Ordinary generation creates only the lightweight selected-weapon display. It is
deleted immediately when the Weapon selector changes and replaced from the new
proxy recipe on generation, preventing a stale longsword. CONTACT creates the
reduced target/proxy/plane/trail review set on demand. Editable orange controls,
target details, full weapon geometry, trajectory, body style, solver/reach,
validation tolerances, promotion/repair tools, and Legacy drafting remain behind
the collapsed Advanced section. Existing Actions and promoted masters are never
silently rewritten.

## Versioned records and compatibility

- `dreadstone.offensive_motion_recipe.v1` stores per-Action target, proxy,
  trajectory, timing, style, solver, reach policy, tolerances, contact frame,
  Feel, and provenance.
- `dreadstone.offensive_motion_master.v1` stores a reusable target-relative
  path. The five current starters carry built-in revision
  `5.4.2-simple.1` without changing their stable combat Action IDs.
- `dreadstone.offensive_motion_master_library.v1` stores promoted masters.
- `dreadstone.offensive_motion_validation.v1` proves the current baked FK
  socket/proxy path and its trajectory-critical digest.
- `dreadstone.offensive_motion_pose_health.v1` reports reach and pose safety.
- `dreadstone.offensive_targeting.v1` remains the optional non-homing runtime
  launch companion.

The established `dreadstone.offensive_action.v1`, runtime socket calibration,
phases, weapon class, commitment, root-motion policy, Animation Library, and
Complete Damage sidecars remain compatible. Existing approved Actions and
5.4.0/5.4.1 promoted artist masters are not rewritten on load. A saved 5.4.1
recipe without `minimumReachRatio` remains valid and uses the compatibility
default only when rebuilt. Copy-on-write SHARED / INHERITED / OVERRIDE / REVERT
TO SHARED / EDIT SHARED family behavior is unchanged; an editable override
clears stale validation and pose proof.

## Target volumes and surface contact

Target zones retain the exact sphere/capsule geometry introduced in 5.4:

- HEAD: sphere at `0.90 * targetHeight`;
- UPPER_TORSO: vertical capsule at `0.72 * targetHeight`;
- CENTER_MASS: vertical capsule at `0.58 * targetHeight`;
- LOW_TORSO: vertical capsule at `0.44 * targetHeight`;
- CUSTOM: explicit sphere height/radius.

CONTACT now means first meaningful impact rather than target-center burial.
Recipes support `ENTRY_SURFACE`, `TOP_SURFACE`, `SIDE_SURFACE`, and `CENTER`.
Surface anchors use the same authored volume as validation with a 2 mm numeric
inset so a sampled first impact is unambiguously intersecting. Thrust defaults
to the front entry surface, overhead to the top surface, and opposite slashes
to their appropriate entry side. ACTIVE may then continue through the volume.
HEAD overhead therefore begins at the head's upper impact surface rather than
at the skull center.

The viewport shows target volume and center, the yellow intended surface
anchor, proxy contact geometry, orange controls, strike plane/line, phase-
colored baked trail, and magenta actual baked closest/contact location.

## Weapon proxy and contact selection

Proxies remain authoring measurements under the neutral managed hand socket.
Motion Studio never rotates or recalibrates the runtime socket.

- `ONE_HAND_BLUNT` shows grip, shaft, and head/contact region. The fixed primary
  head distance leads contact.
- `ONE_HAND_BLADE` shows grip, guard, blade direction, tip, and legal strike
  segment. Slash, overhead, and diagonal Auto Fit choose one constant point
  within that segment for the attack, preferring comfortable arm posture while
  preserving the target and authored orientation. Contact never slides outside
  the segment or races independently along it per frame.
- `SHORT_BLADE` uses the same blade rule with shorter dimensions.
- `THRUST` keeps the forward tip/primary contact point fixed; an incidental
  shaft overlap is not accepted as the thrust hit.

Weapon-class axis profiles prevent one arbitrary orientation from controlling
every proxy. Normal sword overhead/slash CONTACT is forward-diagonal across the
target and reads as a chop/arc, not a vertical tip-down plunge. Its ready pose,
anticipation, contact, and recovery axes form a continuous arc. Thrust remains
primarily forward. Blunt profiles keep the mace head visibly leading.

## Natural Auto Fit and arm reach

Auto Fit is applied by default to built-in starters. It measures the selected
canonical upper-arm and lower-arm rest lengths, derives shoulder-to-wrist
maximum geometric reach, and uses these character-specific thresholds:

- minimum safe reach: `55%` of straight arm-chain reach;
- comfortable reach: `88%` of straight arm-chain reach;
- near-lock warning: above `92%`;
- hard reachable limit: `98.5%`.

Target distance and a bounded CONTACT-relative excursion scale are searched from
the actual character, selected target, trajectory family, proxy, and socket.
Blade contact is also searched inside the legal strike segment. A candidate is
accepted only when every sampled wrist pose stays inside the annulus: no sample
below 55%, no production sample in the near-lock band, and none beyond the hard
limit. The score prefers the Natural arm-extension target and, for thrusts,
requires forward wrist travel without pulling the elbow ahead of the wrist.
Built-in target distance is therefore a seed/provenance value, not a fixed
humanoid truth.

The chosen target distance, minimum/maximum/contact extension ratios, and
excursion scale are recorded in recipe provenance. CONTACT itself remains on
the authored target surface; compaction changes only the surrounding path.

If no candidate fits, build fails with actionable folded- or over-reach text.
Forge does not enlarge the target, loosen geometry, stretch the IK chain, or
translate a hand to hide an unsafe relationship.

## Arm, shoulder, and body solve

Temporary arm IK owns the anatomical upper arm and lower arm (`chain length 2`)
with stretch disabled. Its pole plane is seeded from the character's authored
base-pose elbow relationship and blended continuously frame to frame; a global
left/right pole guess cannot flip the branch on an unusually oriented rig.
Shoulder/clavicle support is applied separately and capped at `4 degrees`; it is
never an emergency extension link. Wrist position comes from the evaluated arm
chain. Hand orientation is applied at that solved endpoint, so an imperfect
orientation/contact solve is reported instead of moving the canonical hand away
from its parent endpoint. Runtime socket calibration uses the stable authored
bone-parent local transform and does not depend on the currently evaluated frame.

The canonical shoulder, upper arm, lower arm, and hand are rotation-driven for
Motion Studio. Their local locations are neither meaningfully changed nor
keyed. Other Forge systems retain their existing explicit location policies;
this is not a global ban on location channels. Root remains IN_PLACE for these
starters. Runtime sockets remain unchanged.

Body support uses the same family-specific C1 smoothstep envelope over START,
ANTICIPATION, PRE_CONTACT, CONTACT, POST_CONTACT, FOLLOW_THROUGH, and END, but
production attacks now apply it only to spine, chest, and the active shoulder.
Pelvis, both legs, knees, feet, and the non-active arm are left in the authored
base pose. This removes the broad full-body re-solve that produced near-zero
curves and could contort unusual rest orientations. Expert styles remain subject
to the same reach, translation, solve, and continuity gates.

## Natural starter behavior

All five built-ins use compact, segment-bounded smooth interpolation and modest
target-relative controls:

- Right-to-left and left-to-right slashes keep their opposite direction but
  reduce lateral windup/follow-through and torso whip.
- Overhead uses a compact raised/back anticipation, top-surface first impact,
  forward-diagonal blade chop or head-led mace contact, modest descent, and
  controlled recovery. HEAD selection does not turn it into a thrust.
- Heavy diagonal is more committed but keeps a reachable hand, proxy-specific
  anticipation orientation, and restrained follow-through.
- Thrust uses a compact roughly 0.16 m contact-point chamber, forward tip
  contact at the entry surface, modest penetration, and smooth retraction. Its
  ACTIVE wrist must remain in front of the shoulder and ahead of the elbow.

Trajectory interpolation is smoothstep-linear between authored controls. It is
C1 at controls and segment-bounded, preventing the cubic overshoot that could
fold or overextend the shoulder even when control points themselves looked
reasonable.

## FK bake and pose health

Temporary constraints are removed after the full-resolution quality solve. The
bake asserts exact canonical bone inventory/rest matrices, no scale F-Curves,
no starter root translation, and no deform-arm location curves. It writes one
base-pose rotation key for mapped bones, samples only spine, chest, active
shoulder, upper arm, lower arm, and hand through the clip, then reduces redundant
keys while preserving all seven named control poses plus ACTIVE boundaries.
Pose health tracks:

- minimum and maximum arm extension ratio and minimum elbow bend;
- thrust wrist/forearm forward-order measurements;
- maximum bounded shoulder support and torso contribution;
- maximum unexpected deform-chain translation;
- maximum per-frame wrist/contact solve error;
- maximum world-space frame-to-frame angular change and responsible bone/frame.

Hard failures include folding below 55%, extension beyond 98.5%, invalid thrust
arm ordering, deform translation above `0.0001 m`, wrist/contact solve error
above `0.015 m`, shoulder support beyond the cap, an FK angular step above `25
degrees`, target miss, wrong trajectory family/direction, or stale proof.
Warnings include extension above 92%, a near-locked elbow, high shoulder/torso
support, and angular steps above 22 through 25 degrees. Production built-ins are
expected to remain inside the 55–92% clean annulus with angular steps no greater
than 22 degrees.

## Baked-path validation and approval

Validation samples the evaluated hand, unchanged socket local transform, and
configured proxy from the baked Action, not merely the desired controls. ACTIVE
sampling remains 0.25 frame with exact target/proxy intersection, intended
CONTACT, plane/line error, direction, overhead descent, thrust forward travel,
windup/recovery checks, and input digest. Existing default geometric tolerances
remain `0.12 m` plane/line error, `0.60` direction dot, and a two-frame CONTACT
navigation window; geometry is not loosened to accommodate naturalism.

Approval requires current recipe, pose-health `PASS`, baked-geometry `PASS`,
ACTIVE and intended CONTACT, current preview proof, compatible socket, exact
skeleton, no forbidden scale/deform location curves, and current bake digest.
`WARN` is non-approvable. Promotion remains deliberate and target-relative.

**BYPASS FAILED CHECKS AND SAVE** is a separate user-decision path. It requires
current preview proof but may override pose, reach, targeting, or validation
failures. The approved Action retains the original failed reports and adds
`dreadstone.offensive_motion_bypass.v1` with the failure list, timestamp, recipe
digest, curve/socket/skeleton input digest, and reviewed preview digest. It also
stamps intended targeting metadata with `technicalChecksBypassed: true` for game
handoff. Any subsequent curve, recipe, socket, or canonical-rig change makes the
bypass stale and blocks export until the revised animation is previewed and
accepted again.

## Helpers, export, and limits

Generate & Preview creates only the current hand-held weapon proxy. CONTACT and
Replay / Preview may create target, proxy, trail, plane, and marker helpers
without editable controls; the expert repair path may restore the full control
set. Every such object is a preview-only member of
`DSB_OFFENSIVE_MOTION_STUDIO` and never exports as a GLB node, bone, skin joint,
collision object, or runtime tracker. Session recovery preserves whether the
required set is weapon-only or full review geometry. Complete Damage continues
to use zero-time temporary Action clones without mutating source Actions.

This release refines production one-hand starters. `TWO_HAND_GENERIC` remains
schema/proxy architecture, not a claimed two-hand constrained solve. Numeric
geometry and pose-health metrics catch known failures; they do not establish
artistic quality. The manual Sword Head/Torso Overhead, Mace Overhead, Thrust,
and opposite Slash reviews in the User Workflow Guide remain mandatory.
