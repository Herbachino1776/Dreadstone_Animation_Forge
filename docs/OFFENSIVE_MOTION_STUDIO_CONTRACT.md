# Offensive Motion Studio contract

Forge release: `5.4.0`

## Product law

The weapon path defines the attack. The body supports that path. Motion Studio
authors in canonical character-local space (`+Y` forward, `+Z` up, X lateral):

```text
TARGET
→ WEAPON TRAJECTORY
→ TEMPORARY CONSTRAINED BODY SOLVE
→ CANONICAL FK BAKE
→ ACTUAL BAKED SOCKET/PROXY SAMPLING
→ PREVIEW
→ APPROVAL
→ OPTIONAL MASTER PROMOTION
```

Forge does not implement collision, AI, hit decisions, weapon assets, damage,
or runtime homing. The target dummy is the relationship for which the animation
was authored. Before commitment a game may later use the optional launch
envelope; after commitment the baked animation follows its fixed path and a
moving player can dodge.

## Versioned records

- `dreadstone.offensive_motion_recipe.v1` — persistent per-Action authoring
  provenance: master, target, proxy, trajectory controls, timing, style, solve,
  contact frame, and tolerances.
- `dreadstone.offensive_motion_master.v1` — reusable target-relative weapon
  trajectory plus defaults. Built-in starters are `BUILT_IN_STARTER`, geometry
  valid, and explicitly not artist approved. Deliberate promotion creates an
  artist-approved `PROMOTED_MASTER`.
- `dreadstone.offensive_motion_master_library.v1` — `.blend`-resident promoted
  master collection.
- `dreadstone.offensive_motion_validation.v1` — report for the current baked FK
  Action and a digest of the trajectory-critical inputs.
- `dreadstone.offensive_targeting.v1` — small optional runtime companion handoff
  describing where the attack was authored to connect.

The established `dreadstone.offensive_action.v1` combat identity, phase,
commitment, socket, weapon-class, duration, and root-motion contract is
unchanged. Legacy `dreadstone.offensive_recipe.v1` remains supported and is
also stamped on Motion Studio Actions for existing authoring integrations.

## Target model and math

Editable target properties are height, forward distance, lateral offset,
target zone, torso radius, zone half-height, head radius, and custom sphere
height/radius. Zone centers are height-relative defaults, not Dreadstone player
truth:

- HEAD: `0.90 × targetHeight`, sphere;
- UPPER_TORSO: `0.72 × targetHeight`, vertical capsule;
- CENTER_MASS: `0.58 × targetHeight`, vertical capsule;
- LOW_TORSO: `0.44 × targetHeight`, vertical capsule;
- CUSTOM: explicit height and sphere radius.

Capsule intersection uses the exact closest distance between the weapon strike
segment and the capsule axis minus target and proxy radii. Sphere intersection
uses closest point on the weapon segment. THRUST deliberately uses the proxy's
tip/primary contact point rather than accepting an incidental shaft overlap.
Viewport wire volumes use the same centers, radii, and capsule half-heights as
validation.

## Weapon proxy

The proxy is an authoring measurement, not an art asset. Supported classes are
`ONE_HAND_BLADE`, `ONE_HAND_BLUNT`, `SHORT_BLADE`, and architecture-ready
`TWO_HAND_GENERIC`. Every proxy defines grip, local +Y weapon axis, total
length, strike-segment start/end, grip-to-primary-contact distance, and optional
head/contact radius. Proxy objects are parented beneath the existing managed
hand socket. Motion Studio never alters socket calibration.

## Trajectory and CONTACT

Each trajectory contains ordered START, ANTICIPATION, PRE_CONTACT, CONTACT,
POST_CONTACT, FOLLOW_THROUGH, and END controls. Controls store a target-space
contact-point position and weapon-axis orientation; monotone frame timing and
cubic Hermite interpolation produce a smooth editable path. CONTACT is placed
at the intended target center in starters and remains the principal inspection
frame.

Trajectory families define expected geometry and direction:

- `HORIZONTAL`: target-centered horizontal plane and lateral direction;
- `DIAGONAL_DOWN`: target-centered forward plane and high-to-low direction;
- `OVERHEAD_VERTICAL`: target-centered sagittal plane and descending direction;
- `THRUST`: target-centered line and canonical-forward direction;
- `CUSTOM`: artist-controlled direction without a built-in plane gate.

The viewport shows the target volumes, intended plane/line, weapon proxy,
orange pose controls, CONTACT marker, phase-colored weapon trail (blue WINDUP,
red ACTIVE, green RECOVERY), ACTIVE bounds, target center, and closest approach.

## Solve and FK bake

The one-hand solve creates a temporary desired hand/grip target and elbow pole.
A temporary IK constraint solves the shoulder/upper-arm/lower-arm chain without
stretch. Temporary two-bone foot targets and knee poles keep both canonical feet
planted while hips and stance support the strike. The evaluated matrices are
copied back to ordinary pose bones; the hand matrix is aligned so the unchanged
runtime socket places the proxy on the desired grip/axis. Hips, spine, chest,
stance, wrist, and elbow-pole placement provide secondary style support.

Every authored frame is keyed on the existing Skin & Bones semantic mapping.
Constraints and temporary solve objects are removed immediately. The bake
asserts exact 21-bone rest/inventory identity, no scale F-Curves, and IN_PLACE
root translation. Runtime GLBs contain only normal canonical FK animation.

## Baked-path validation

Validation samples the real evaluated hand pose, the existing managed socket
local transform, and the configured proxy from the baked Action. It never
trusts only the pre-bake control path. ACTIVE is sampled at 0.25-frame steps;
WINDUP and RECOVERY at no coarser than 0.5 frame.

Default documented tolerances are:

- maximum strike plane/line deviation: `0.12 m`;
- expected direction dot product: at least `0.60`;
- intended contact navigation window: `2 frames` (the current gate requires
  actual intersection at the sampled CONTACT state, not merely proximity);
- overhead descending contribution: at least `60%` of ACTIVE displacement;
- thrust forward contribution: at least `72%`;
- horizontal lateral contribution: at least `72%`.

The report includes target contact, ACTIVE contact, intended CONTACT
intersection, contact time/frame, target clearance or miss distance, closest
points, plane error, actual/expected directions, and family-specific ratios.
WINDUP intersection, remaining buried throughout RECOVERY, wrong direction,
overhead lateral sweeps, and lateral “thrusts” fail. These tolerances constrain
geometry; they are not an assertion of artistic beauty.

## Invalidation and approval

The validation input digest covers the full Motion recipe (target dimensions
and transform, target zone, proxy, controls, family, contact/timing, solver,
style, and tolerances), all Action curve samples, the selected runtime socket
record, and the canonical skeleton/rest matrices. Any material change makes the
saved proof stale. Entering an editable draft or creating a Character Variant
override also clears preview, validation, targeting, and approval proof.

Motion Studio approval requires current offensive metadata and phases, recipe,
preview digest, PASS baked validation, ACTIVE and intended CONTACT
intersection, optional targeting record, compatible socket, exact skeleton,
no scale channels, and current FK bake recipe digest. Errors lead with useful
geometry, for example: `Weapon contact point missed UPPER_TORSO by 0.18 m
during ACTIVE.` Human approval remains authoritative for motion quality.

## Motion Masters and Animation Library

Five starter masters ship: 1H slash right-to-left, 1H slash left-to-right, 1H
overhead, 1H heavy diagonal, and 1H thrust. They reuse the existing combat
Action IDs. An approved reviewed Motion Studio Action can be explicitly
promoted. Promotion converts its absolute controls back to target-relative
controls, records source Action/clip provenance, and adds it to the `.blend`
master library. Building that master on another compatible humanoid runs the
weapon-first solver again instead of copying raw arm rotations. Ordinary
approved Actions remain managed by the existing Animation Library.

## Character Variant Families

Shared and inherited Actions retain one shared Motion recipe and validation.
Motion Studio refuses to replace an existing saved/inherited logical attack.
The artist must use the existing EDIT, CREATE VARIANT OVERRIDE, or confirmed
EDIT SHARED workflow. A variant override clones only that Action and its Motion
record, becomes a draft, and clears preview/validation/targeting. REVERT TO
SHARED deletes the variant-owned Action and all embedded Motion state with it.

## Helpers, save/reopen, and export

All target, proxy, controls, path, plane, and solve helpers are owned by
`DSB_OFFENSIVE_MOTION_STUDIO`, stamped preview-only with the
`offensive_motion_studio_helper` authoring role, and excluded from Animation
Pack and Complete Damage membership. They never become bones or skin joints.
Creation is idempotent, repair reconstructs from the saved Action recipe, and
remove affects helpers only. A scene session record allows missing helpers to
be reconstructed after load; recipes, validation, promotion provenance, and
helpers themselves persist in `.blend` files.

Complete Damage continues to stage temporary zero-time Action clones exactly as
in 5.2.2. The optional targeting record contains only target zone/offset,
preferred distance/contact height, axis tolerances, trajectory family, contact
time, and proxy reach. No helper, IK, tracking, homing, collision, or hit result
is exported.

## Compatibility and limits

The eight body-first generators remain unchanged under LEGACY / PROCEDURAL
DRAFTING. Existing 5.2.x/5.3 Actions and recipes are not migrated or newly
required to pass target validation. This release polishes one-hand solving;
`TWO_HAND_GENERIC` establishes proxy/schema architecture but does not claim a
production two-hand constrained solve. Numeric geometry validates contact, not
human aesthetic quality; Dread Ram God and the mace overhead require the manual
acceptance in the User Workflow Guide.
