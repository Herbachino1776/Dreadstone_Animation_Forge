# Offensive Motion Studio contract

Forge release: `5.4.1`

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

Forge 5.4.1 adds an equally strict naturalism law: a valid hit must be achieved
through the intact character chain, never through IK stretch or local
dislocation of shoulder, upper arm, lower arm, or hand. The body supports the
weapon path with restrained continuous motion. The weapon still has to contact
the authored target during ACTIVE on the intended family, plane, and direction.

Motion Studio authors in canonical character-local space (`+Y` forward, `+Z`
up, `+X` anatomical right). It does not implement collision, hit decisions,
runtime tracking/homing, weapon assets, or damage. After commitment the baked
path is fixed and a moving target can dodge.

## VIP macro workflow and expert access

The default panel exposes Attack, Weapon, Target, horizontal/vertical aim,
Windup, Strike Power, Body Motion, Follow Through, Arm Relaxation, one Refresh
Attack action, Contact, Preview, status, Validate, and Approve. Aim rotates the
path around the recalculated first-impact surface anchor; it does not move the
weapon off target. Neutral macro values preserve the built-in Natural recipe.
Refresh rebuilds from that starter, runs character Auto Fit, validates the FK
path, and starts preview when validation passes.

Target details, weapon geometry, trajectory/control points, body style,
solver/reach, validation tolerances, and Legacy drafting remain behind one
collapsed Advanced section. Orange controls remain directly editable in the
viewport. `SUBTLE`, `NATURAL`, `FORCEFUL`, and raw expert values remain available
there; existing Actions and promoted masters are never silently rewritten.

## Versioned records and compatibility

- `dreadstone.offensive_motion_recipe.v1` stores per-Action target, proxy,
  trajectory, timing, style, solver, reach policy, tolerances, contact frame,
  Feel, and provenance.
- `dreadstone.offensive_motion_master.v1` stores a reusable target-relative
  path. The five revised starters carry built-in revision
  `5.4.1-natural.1` without changing their stable combat Action IDs.
- `dreadstone.offensive_motion_master_library.v1` stores promoted masters.
- `dreadstone.offensive_motion_validation.v1` proves the current baked FK
  socket/proxy path and its trajectory-critical digest.
- `dreadstone.offensive_motion_pose_health.v1` reports reach and pose safety.
- `dreadstone.offensive_targeting.v1` remains the optional non-homing runtime
  launch companion.

The established `dreadstone.offensive_action.v1`, runtime socket calibration,
phases, weapon class, commitment, root-motion policy, Animation Library, and
Complete Damage sidecars remain compatible. Existing approved Actions and
5.4.0 promoted artist masters are not rewritten on load. Copy-on-write
SHARED / INHERITED / OVERRIDE / REVERT TO SHARED / EDIT SHARED family behavior
is unchanged; an editable override clears stale validation and pose proof.

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

- comfortable reach: `88%` of straight arm-chain reach;
- near-lock warning: above `92%`;
- hard reachable limit: `98.5%`.

Target distance is searched from the actual character, selected target,
trajectory family, proxy, and socket. Blade contact is also searched inside the
legal strike segment. The score prefers the Natural arm-extension target,
avoids both locked and excessively folded elbows, and, for thrusts, avoids a
wrist chamber pulled behind the torso. Built-in target distance is therefore a
seed/provenance value, not a fixed humanoid truth.

For a contract-compatible humanoid whose measured arm is shorter than the
canonical tuning fixture, Auto Fit proportionally compacts non-CONTACT starter
excursions around the unchanged target-surface CONTACT point (down to a bounded
64% scale). This prevents a compact-looking weapon control path from folding
the wrist through the shoulder on a smaller arm while preserving the authored
target, surface anchor, family, and direction. The applied scale is recorded in
recipe provenance.

If no candidate stays inside the hard limit, build fails with actionable text
such as `TARGET REQUIRES 103% ARM EXTENSION. Move target 0.14 m closer or use
AUTO FIT.` Forge does not enlarge the target, relax geometry, or translate a
hand to hide an unreachable relationship.

## Arm, shoulder, and body solve

Temporary arm IK owns the anatomical upper arm and lower arm (`chain length 2`)
with stretch disabled. Shoulder/clavicle support is applied separately and is
capped at `4 degrees`; it is never an emergency extension link. Wrist position
comes from the evaluated arm chain. Hand orientation is applied at that solved
endpoint, so an imperfect orientation/contact solve is reported instead of
moving the canonical hand away from its parent endpoint.

The canonical shoulder, upper arm, lower arm, and hand are rotation-driven for
Motion Studio. Their local locations are neither meaningfully changed nor
keyed. Other Forge systems retain their existing explicit location policies;
this is not a global ban on location channels. Root remains IN_PLACE for these
starters. Runtime sockets remain unchanged.

Body support uses a family-specific C1 smoothstep envelope over START,
ANTICIPATION, PRE_CONTACT, CONTACT, POST_CONTACT, FOLLOW_THROUGH, and END. It
passes continuously from the small opposite preload into modest strike support
and declining follow-through; there is no sign/state flip at CONTACT. Natural
torso, stance, knee compression, and planted-foot response are intentionally
small. Leg IK may hold ankle position but never owns terminal foot orientation:
each foot retains its authored IDLE base-pose transform. Position or orientation
drift is a pose-health failure. Forceful may add support but remains subject to
the same hard reach, translation, solve, and continuity gates.

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
- Thrust uses a roughly 0.30 m maximum contact-point chamber rather than the
  5.4 giant withdrawal, forward tip contact at the entry surface, modest
  penetration, and smooth retraction.

Trajectory interpolation is smoothstep-linear between authored controls. It is
C1 at controls and segment-bounded, preventing the cubic overshoot that could
fold or overextend the shoulder even when control points themselves looked
reasonable.

## FK bake and pose health

Temporary constraints/helpers are removed after every-frame FK bake. The bake
asserts exact canonical bone inventory/rest matrices, no scale F-Curves, no
starter root translation, and no deform-arm location curves. Pose health tracks:

- maximum arm extension ratio and minimum elbow bend;
- maximum bounded shoulder support and torso contribution;
- maximum unexpected deform-chain translation;
- maximum per-frame wrist/contact solve error;
- maximum world-space frame-to-frame angular change and responsible bone/frame.

Hard failures include extension beyond 98.5%, deform translation above
`0.0001 m`, wrist/contact solve error above `0.015 m`, shoulder support beyond
the cap, an FK angular step above `45 degrees`, target miss, wrong trajectory
family/direction, or stale proof. Warnings include extension above 92%, a near-
locked elbow, high shoulder/torso support, and angular steps above 30 degrees.
Natural built-ins are expected to remain below the warning reach threshold on
the canonical acceptance humanoid.

## Baked-path validation and approval

Validation samples the evaluated hand, unchanged socket local transform, and
configured proxy from the baked Action, not merely the desired controls. ACTIVE
sampling remains 0.25 frame with exact target/proxy intersection, intended
CONTACT, plane/line error, direction, overhead descent, thrust forward travel,
windup/recovery checks, and input digest. Existing default geometric tolerances
remain `0.12 m` plane/line error, `0.60` direction dot, and a two-frame CONTACT
navigation window; geometry is not loosened to accommodate naturalism.

Approval requires current recipe, pose health without hard failure, PASS baked
geometry, ACTIVE and intended CONTACT, current preview proof, compatible socket,
exact skeleton, no forbidden scale/deform location curves, and current bake
digest. Promotion remains deliberate and target-relative.

## Helpers, export, and limits

All `DSB_MS_*` target, proxy, control, trail, plane, and solver objects are
preview-only members of `DSB_OFFENSIVE_MOTION_STUDIO`; they can be repaired
after reopen and never export as GLB nodes, bones, skin joints, collision, or
runtime tracking. Complete Damage continues to use zero-time temporary Action
clones without mutating source Actions.

This release refines production one-hand starters. `TWO_HAND_GENERIC` remains
schema/proxy architecture, not a claimed two-hand constrained solve. Numeric
geometry and pose-health metrics catch known failures; they do not establish
artistic quality. The manual Sword Head/Torso Overhead, Mace Overhead, Thrust,
and opposite Slash reviews in the User Workflow Guide remain mandatory.
