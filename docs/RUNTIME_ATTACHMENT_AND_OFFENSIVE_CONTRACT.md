# Runtime attachment and offensive Action contract

Forge release: `5.2.0`

Schemas:

- `dreadstone.attachment_sockets.v1`
- `dreadstone.offensive_action.v1`

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
Action frame schedule at scene FPS, then checked against the Action and emitted
glTF sampler. The eight generator identities are:

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

## Consumer boundary

Dreadstone treats these records as optional, versioned capabilities. An older
pack without them remains importable but reports armament unavailable. The game
owns weapon definitions, visuals, damage, reach capsules, loadouts, hit policy,
and AI. Forge owns animation and attachment authoring data only. No socket
fallback to root/chest and no name-based offensive inference is permitted.
