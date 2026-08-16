# Character Variant Family contract

Forge release: `6.0.2`

Native look capture may transactionally recover a missing variant-owned
material palette from the intact runtime slots and may restore texture-only
source-coordinate drift from Complete Damage's protected source. Neither path
changes topology, weights, the runtime rig, sockets, Actions, or Damage data.

Forge schema: `dreadstone.character_variant_family.v1`

Resolved export provenance: `dreadstone.character_variant_provenance.v1`

## Product law and ownership

Most variants differ only in baked appearance. They share Forge authoring until
the artist explicitly creates an override. An imported compatible appearance
therefore creates no Action, Damage Key, Stamp, gore, Progressive Damage Site,
or socket copy.

For an imported Skin & Bones family, Skin & Bones owns appearance identity,
approval, and proof that appearances use the same technical body. Forge owns
shared animation/damage authoring, explicit copy-on-write overrides, effective
resolution, and resolved shipping export.
The game receives an independent, fully resolved asset and does not need to
implement Blender inheritance. World movement and AI speed remain game-owned.

## Skin & Bones 2.2.0 handoff consumed

Forge consumes the shipped `skin-and-bones-appearance-family-handoff-v1`
schema version `1`; it does not define a parallel family format. The compact
JSON record is read from `sbf_appearance_family_handoff` on imported mesh and
armature nodes and cross-checked against these scalar glTF extras:

- `sbf_appearance_family_id`
- `sbf_appearance_variant_id`
- `sbf_technical_body_fingerprint`

When present, the sibling `<asset>.glb.sbf.json` `appearance_family` record
must match the node handoff exactly. The handoff fields consumed are:

- `schema`, `schema_version`
- `family_schema`, `family_schema_version`
- `family_id`, `family_display_name`
- `variant_id`, `variant_display_name`, `export_identity`
- `technical_body_schema`, `technical_body_schema_version`
- `technical_body_fingerprint`
- `appearance_revision`
- `approval.state`, `approval.approved_revision`,
  `approval.appearance_fingerprint`, `approval.approved_at_utc`, and
  `approval.addon_version`

The accepted family schema is `skin-and-bones-appearance-family-v1`; the
accepted body schema is `skin-and-bones-technical-body-v1`. Both are version
`1`. Appearance approval must be `APPROVED` and its approved revision must
equal the current appearance revision.

## Compatibility gate

Joining an existing family requires exact equality for Skin & Bones
`family_id`, technical-body schema/version, and the 64-character SHA-256 body
fingerprint. Forge also revalidates the canonical rig signature through its
Skin & Bones adapter: `SBF_HUMANOID_YPLUS_V1`, rig contract version `1`,
orientation revision `1`, `+Y` forward, `+Z` up, top-level `root`, unit scale
`1`, and the exact 21-bone semantic role map and hierarchy.

Skin & Bones' body fingerprint already covers topology, rest rig, weights, UV,
world transform, scale, and coordinate axes. Object names are never a
compatibility signal. Any mismatch refuses the join before family state is
changed; a failed GLB import removes only objects imported by that attempted
transaction and cleans its unused mesh, armature, material, and image data.
Variant IDs and case-insensitive sanitized shipping filenames must also remain
unique within the family so batch export cannot overwrite another appearance.

## Finished character texture multiplier

Forge also supports a finished-character source that already has a generated
`DSB_DAMAGE_RIG`, runtime body, approved Actions, and Damage authoring but no
Skin & Bones 2.2.0 Appearance Family handoff. This is an explicit second source
mode, `FORGE_FINISHED_TEXTURE_CAPTURE`; it does not synthesize a Skin & Bones
handoff or attach fake `sbf_*` family metadata to the shipping asset.

The artist starts the family from the finished Damage rig. Forge derives a
`dreadstone-finished-damage-body-v1` SHA-256 technical fingerprint from the
exact canonical 21-bone rest hierarchy and the runtime body's topology, vertex
weights, UVs, object transforms, and material-slot structure. Material and
image content are intentionally excluded so another baked look can remain
compatible. A changed rig, body, weights, UV layout, transform, or slot
structure makes the look incompatible rather than silently inheriting content.

The base look snapshots the runtime body's exact material-slot bindings. **MAKE
EDITABLE TEXTURE COPY** duplicates only the active materials and their referenced
images, immediately applies them to the same runtime body, and creates a draft
variant with empty Action, Damage Key, and Progressive Site override maps. Packed
images and dirty in-memory pixels are included in the appearance fingerprint.
Approving the look is Forge-owned and records
`ANIMATION_FORGE_TEXTURE_CAPTURE`, the appearance fingerprint, revision, and
approval time. **EDIT / TWEAK THIS LOOK** deliberately returns one look to Draft
without touching shared authoring. Editing pixels or material content blocks
export until **SAVE CURRENT LOOK** or **SAVE + EXPORT** snapshots it again.

The optional Skin & Bones projection bridge is a narrow editor integration, not
a second family model. **LOAD 4-VIEW FOLDER** reveals S&B's original full-body
mesh on its target-linked, `sbf_production_rig`-proven armature in `REST` and
hides Forge's derived Damage pieces; **BUILD / REFRESH PREVIEW** and **BAKE FINAL
TEXTURE** reassert that neutral evaluation before invoking the installed S&B
operators. **USE FINAL ON THIS LOOK** copies the resulting final Base Color into
the active Forge-owned look, restores the source rig's prior display pose, and
restores the intact Damage preview. Forge refuses a target connected to
`DSB_DAMAGE_RIG`, a generated Damage rig, or an Armature datablock used by any
second object. The versioned display-recovery snapshot migrates the older
visibility-only state; corrupt, mismatched, or unresolvable recovery data blocks
before either rig is changed and is retained for safe recovery. Forge never
clears the source rig's stored pose/Action, changes the scene frame, requires S&B
family approval for this native finished-character route, or touches socket
transforms. Final baking is locked to the existing `sbf_repair_uv` or
`SBF_BaseColorUV` atlas present on both the S&B target and every finished Damage
piece. Forge disables S&B bake-UV generation, preserves PBR UV-node bindings,
and refuses or rolls back a bake that changes the locked coordinates. The
manual alternative
accepts exactly one final UV image and explicitly rejects a four-view source
folder. Camera projection and calibration remain Skin & Bones work; Forge owns
the saved finished look and resolved shipping character.

Every Forge-owned look material and image carries an explicit Blender fake user.
This keeps inactive looks alive through save/reopen even though only one palette
can occupy the runtime body slots at a time. Replacing an owned snapshot removes
that retention only after the replacement is installed, so it does not create a
growing orphan-data trail.

This route is intentionally for texture/material iteration on the same finished
body. A Skin & Bones GLB cannot be joined to a native Forge texture family, and
a native snapshot cannot be joined to an imported Skin & Bones family. Use the
Skin & Bones route whenever the technical body itself must change.

An intentional change to an already-finished native body requires the confirmed
**VALIDATE + ACCEPT CURRENT BODY** recovery. It is unavailable to imported S&B
families and refuses a changed canonical rig, invalid Complete Damage state,
invalid sockets, an active projection transaction, or changed/missing runtime
material-slot bindings. Success replaces the native family's technical
fingerprint and preserves look images/materials plus every Action/Damage
override. Because a technical change can affect texture mapping, every look's
appearance approval is cleared and each look must be reviewed and saved again.
Before setup, copy, approval, and export comparisons, Forge restores the stored
finished-source transform proof and runs Complete Damage validation. This makes
resized generated-piece transforms deterministic and prevents a save/reopen
evaluation difference from masquerading as a technical-body change.

## Persisted Forge family state

The normalized family record persists as JSON on the Blender Scene and, when
present, `DSB_DAMAGE_RIG`. It stores technical family identity, canonical rig
signature, body fingerprint, base and active variant IDs, shared and family
revisions, the shared Action ID set, shared Damage revision, and the fixed
`FAMILY_SHARED_NO_VARIANT_OVERRIDE` socket policy.

Each variant stores the original Skin & Bones handoff, captured appearance
object/material identity, Forge revision, and three sparse maps:

- shared Action ID to variant Action override ID;
- shared Damage Key ID to variant Damage Key override record;
- shared Progressive Site GUID to variant site override record and its owned
  stage-key clones.

Save/reopen normalization rejects missing or duplicate variant IDs and missing
base/active variants. It never synthesizes physical authoring copies.

## Central effective resolution

The pure `variant_family.py` layer is authoritative. Blender integrations call
its effective Action, Damage Key, and Progressive Site resolvers; panels and
exporters do not independently guess ownership.

For a logical shared Action ID, resolution returns the active variant's mapped
override when one exists, otherwise the shared Action. For a shared Damage Key
or Site identity, resolution follows the same rule and filters physical
variant-owned records belonging to other appearances. A shared edit is visible
immediately to every inheritor; an override remains unchanged.

## Animation copy-on-write

An approved Action adopted with the base, or approved after family creation,
belongs to the shared layer. Ordinary and offensive Actions use the same
resolver.

**CREATE VARIANT OVERRIDE** copies only the selected shared Action, assigns a
new clip ID and active variant owner, makes it a draft, and clears approval.
For an offensive Action it also clears preview proof. A Motion Studio override
retains only that Action's recipe/master provenance but clears baked-path
validation, optional targeting metadata, and approval; the override must be
rebuilt, previewed, and target-validated. Other Actions remain inherited. The
shared source is never assigned for editing by this operation.

An inherited Action cannot use the ordinary Edit or Delete controls.
**EDIT SHARED** is a confirmed, explicit family-wide operation.
**REVERT TO SHARED** removes the sparse map entry and variant Action and then
selects the live shared Action. Existing Action kind, combat ID, family,
weapon/socket roles, source, WINDUP/ACTIVE/RECOVERY timing, commitment,
recipe, preview, and approval validation remain mandatory.

Runtime export still uses normal authored Actions and temporary normalized
zero-time copies. Source Actions and overrides retain their authored frame
ranges; only staging copies begin at `0.0` seconds.

## Damage copy-on-write and override boundaries

The narrow Damage Key boundary is one existing stable Damage Key ID together
with the paired attached/detached shape keys, that key's Stamp/capture/recipe
metadata, and any generated raised/inlay gore it owns. The clone receives a
new Damage Key ID, variant owner, and shared-key link. No unrelated key or site
is copied.

A Progressive Damage Site is a coherent larger boundary. Creating its
override clones the site metadata and exactly the distinct Damage Keys assigned
to its `LIGHT`, `MEDIUM`, and `HEAVY` stages. Stage references are
deterministically retargeted to the clones; duplicate stage references are
cloned once. The cloned site receives a new GUID/ID, variant ownership, and
reset validation/export status. Other sites remain inherited.

This boundary prevents shared/variant dangling references. **REVERT TO
SHARED** removes the variant site plus its owned stage keys, metadata, shape
keys, and owned gore, then restores the shared site. Reverting an individual
Damage Key removes only that key's owned graph. Both operations confirm that
variant-only edits will be discarded and never delete shared data.

Inherited Damage editing is locked in the family UI. The artist must either
create a variant override or confirm **EDIT SHARED**; switching variants locks
shared editing again.

## Approval and readiness

Skin & Bones appearance approval is inherited from its provenance. Forge
approval remains Forge-owned. Effective readiness consists of current approved
appearance, exact technical compatibility, valid shared Forge content, valid
variant overrides, and a successful Complete Damage export validation.

Inherited approved Actions and Damage do not require per-appearance approval.
Only newly created overrides re-enter their existing relevant draft,
preview/validation, and approval gates. An unsaved or unapproved Action
override blocks selected or batch export.

## Appearance switching and sockets

Switching the active variant shows its source appearance before Damage Asset
construction. After construction, Forge applies the selected variant's
captured material palette to the shared generated runtime body. It does not
replace the technical rig, Actions, Damage Keys, Sites, sockets, or metadata.
Managed hand sockets and the runtime 21-bone contract are family-shared; this
release exposes no socket override.

## Resolved selected and batch export

Selected Complete Damage export uses the active appearance export identity as
its filename and stages only effective Actions, Damage Keys, Sites, gore, and
stains. Non-effective variant morphs and gore are excluded. Normal Complete
Damage validation remains responsible for `DSB_DAMAGE_RIG`, exact 21-bone
membership, zero-time clip bounds and declared durations, offensive timing,
sockets, materials, morphs, gore, and clean reimport.

**EXPORT ALL READY VARIANTS** switches each family member in turn and runs the
ordinary Complete Damage export transaction. Every passing appearance becomes
its own GLB and sidecars; failed/not-ready variants are reported and skipped.
The original active appearance and configured filename are restored.

The sidecar `characterVariant` record and runtime object extras expose:

- technical family and appearance variant IDs;
- Skin & Bones body fingerprint and appearance export identity;
- deterministic effective Forge variant identity/revision;
- a resolved-content revision derived from effective approved Action curves and
  effective Damage/Site metadata, so shared edits advance inheriting outputs;
- family, shared, variant, and appearance revisions;
- shared socket policy;
- stable shared-to-override Action, Damage Key, and Progressive Site mappings.

No Blender object names or unresolved inheritance are required by the game.

## Backward compatibility and limits

Files without family state follow the exact 5.2.2 standalone Action, Damage,
socket, and Complete Damage paths. Adoption is explicit and non-destructive;
there is no automatic migration. Imported families require the exact Skin &
Bones humanoid contract; finished texture families require an exact compatible
Forge `DSB_DAMAGE_RIG` and runtime body. Neither route adds socket overrides,
merges appearances into one GLB, or defines game movement/AI policy.
