# Runtime attachment and offensive Action contract

Forge release: `6.0.3`

Schemas:

- `dreadstone.attachment_sockets.v1`
- `dreadstone.offensive_action.v1`
- optional `dreadstone.offensive_targeting.v1`

## Attachment sockets

The canonical humanoid runtime armature remains `DSB_DAMAGE_RIG` with the exact
21 Skin & Bones bones. Forge manages two authoring-only Empty helpers in
`DSB_RUNTIME_ATTACHMENT_SOCKETS`:

| Socket ID | Semantic role | Parent runtime bone |
| --- | --- | --- |
| `hand_right_weapon` | `MAIN_HAND_R` | `arm_right_hand` |
| `hand_left_weapon` | `MAIN_HAND_L` | `arm_left_hand` |

Creation and repair are idempotent. Forge may restore a missing helper or its
managed ownership/parenting, but it preserves an existing artist-authored world
transform. The operation must not change the bone inventory, parent hierarchy,
rest matrices, weights, or Action inventory.

At export, Forge converts each helper to a bone-local `localPosition` and
normalized `[x,y,z,w]` `localQuaternion`. Socket IDs and semantic roles must be
unique, parents must be in the runtime hierarchy, all values must be finite,
and non-unit local scale is rejected. The helpers are authoring-only: their
collection, objects, and names cannot appear as completed-GLB nodes or skin
joints.

## Offensive Actions

Every offensive Action has a stable lowercase `combatActionId`, an attack
family, primary hand role, optional secondary hand role, non-empty compatible
weapon classes, attack-source role, root-motion policy, clip duration, optional
commitment, and three phase intervals in seconds. The phases are exactly:

```text
WINDUP [0, activeStart)
ACTIVE [activeStart, activeEnd)
RECOVERY [activeEnd, clipDuration]
```

They must be finite, contiguous, non-overlapping, inside the clip, and ACTIVE
must have positive duration. The duration is derived from the actual rounded
Action frame schedule at scene FPS. Complete Damage export leaves that authored
range intact and shifts only its temporary runtime copy so the emitted glTF
sampler begins at zero and ends at the declared duration. Final validation
checks sampler minimum, maximum, and span separately. The eight generator
identities are:

- `humanoid_one_hand_slash_rtl`
- `humanoid_one_hand_slash_ltr`
- `humanoid_one_hand_overhead`
- `humanoid_one_hand_thrust`
- `humanoid_one_hand_heavy`
- `humanoid_two_hand_slash`
- `humanoid_two_hand_overhead`
- `humanoid_two_hand_thrust`

Metadata may live on a draft for preview and validation. Runtime export is
strict: the Action must be explicitly approved, non-draft, compatible with the
runtime skeleton, reference available socket roles, and have a unique combat
ID. Forge never infers attack capability from an Action name.

Motion Studio Actions additionally require a current `PASS` report from the
actual baked FK hand/socket/proxy path and a pose-health `PASS`, with intended
target contact during ACTIVE. A pose-health `WARN` is reviewable but cannot be
approved for runtime export. Their small optional
`dreadstone.offensive_targeting.v1` companion
records where the attack was authored to connect: target zone and local offset,
preferred distance/contact height, horizontal/vertical/depth tolerances,
trajectory family, contact time, and proxy reach. It contains no IK, helper,
collision, homing, or hit-result data. See
[Offensive Motion Studio](OFFENSIVE_MOTION_STUDIO_CONTRACT.md).

Character Variant Families share sockets and approved offensive Actions by
default. An appearance-only variant reuses the family Action, recipe, preview,
and approval without duplicate review. Creating an offensive variant override
copies only that Action and embedded Motion Studio provenance, preserves the
combat/weapon/socket/phase contract, clears preview/trajectory validation,
targeting and approval, and requires the normal gate again. The effective
resolver supplies exactly one shared or overridden Action to runtime staging.

### Legacy character-specific slider recipe and preview gate

Each generated offensive draft also carries authoring-only
`dreadstone.offensive_recipe.v1` JSON. It stores the visible timing sliders and
motion-shaping controls for anticipation, strike, follow-through, torso, arm,
elbow, wrist, and stance. The recipe persists with approved Actions and through
`.blend` save/reload, but it is not runtime damage or weapon metadata and is
not required by Dreadstone.

Refreshing a selected draft applies the current sliders and clears its preview
proof. **Preview Attack** plays that precise Action on the active character and
records that the current draft was reviewed. Offensive approval fails closed
until this preview has occurred. Approval preserves the character recipe; it
does not mutate the built-in humanoid starting recipes. Motion Studio promotion
is a separate explicit action and never mutates built-in or family-wide
defaults. The body-first slider recipe remains legacy compatible.

## Consumer boundary

Dreadstone treats these records as optional, versioned capabilities. An older
pack without them remains importable but reports armament unavailable. The game
owns weapon definitions, visuals, damage, reach capsules, physical world-space
sweeps, loadouts, hit/miss policy, and AI. Forge owns animation,
target/trajectory authoring geometry, and attachment authoring data only. The
target record is a pre-commitment launch-envelope hint; after commitment the
fixed baked Action cannot track the player. No socket
fallback to root/chest and no name-based offensive inference is permitted.
