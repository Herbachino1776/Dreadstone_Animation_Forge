# Development

## Documentation authority

The beginner-facing workflow is
[USER_WORKFLOW_GUIDE.md](USER_WORKFLOW_GUIDE.md). Runtime contracts are
[CORE_COMPOUND_EXPORT_CONTRACT.md](CORE_COMPOUND_EXPORT_CONTRACT.md) and
[RAISED_GORE_EXPORT_CONTRACT.md](RAISED_GORE_EXPORT_CONTRACT.md). When UI,
properties, operators, persistence, or export changes, update all affected
documents and validators in the same change.

## Architecture

`deformation_authoring.py` is the Blender-facing compatibility facade.
Blender-free algorithms live in `trauma_field.py`, `parameter_schema.py`, and
the focused services under `deformation/`.

Forge 4.1 includes:

- `dreadstone.animation_clip.v1`, a native Action `.blend` package with a JSON
  manifest, required-bone/hierarchy validation, non-blocking rest/proportion
  warnings, and explicit per-character ownership on import;
- a VIP saved-Action edit transaction that works on a draft copy and reconnects
  active/NLA users only when the artist confirms overwrite;
- per-key `previewEnabled` with simultaneous multi-key presentation;
- `activeStampId` and `stampMode = ALTERNATIVES` for one previewed child Stamp
  per new Damage Key;
- `dreadstone.damage_blueprint.v1`, a topology-independent intent contract;
- `HYBRID_ADDITIVE`, expanded to independently generated raised and inlay
  components;
- recipe-v6 `goreSurfaceControl` plus a deterministic, closed, budget-aware
  cluster of varied lobulated nuclei across the deepest-response third inside
  the raised component;
- one master-randomize transaction and one managed preview request;
- a cached, disk-free panel draw path for Blueprint inventory.

Forge 5.2.0 retains the explicit Complete Damage shipping boundary in
`runtime_export.py`: property-driven object membership, strict source/damage
rig compatibility, approved Action owner/kind resolution, temporary
`DSB_DAMAGE_RIG` Action/NLA staging, Blender 5.1 Action filtering, exact
rollback, and completed-GLB skeleton/animation validation.

The same boundary now exports `dreadstone.attachment_sockets.v1` and
`dreadstone.offensive_action.v1`. Socket helpers are managed Empty objects,
not deform bones: creation/repair must preserve the exact 21-bone canonical
inventory and rest matrices. Offensive metadata must remain attached to its
Action, use seconds derived from the rounded frame schedule, and pass strict
approval, uniqueness, duration, phase, and socket compatibility checks before
shipping. The authoritative details are in
[RUNTIME_ATTACHMENT_AND_OFFENSIVE_CONTRACT.md](RUNTIME_ATTACHMENT_AND_OFFENSIVE_CONTRACT.md).

Panel draw and property callbacks must remain lightweight. Blender RNA stays on
the main thread. Caches are bounded and invalidated on file load, unregister,
topology/source changes, region removal, and explicit rebuild.

Compatibility invariants remain strict: missing legacy keys are not recreated,
unrepairable attached keys are not overwritten, and compound world fields are
analytical only with no Blender mesh merge. Viewport presentation does not rewrite render/export visibility.

## Local checks

Repository tools need Python 3.10+ and the standard library:

```text
python scripts/validate_addon.py
python -m unittest discover -s tests -p "test_*.py"
python scripts/build_release.py
```

Static checks do not prove Blender registration, mesh construction, viewport
presentation, GLB export, or reimport.

## Focused Blender 5.1.2 acceptance

Run the Creature Anatomy Profile acceptance first:

```text
blender --background --factory-startup --python tests/blender_creature_anatomy_acceptance.py
```

It must preserve the exact Skin & Bones `SBF_HUMANOID_YPLUS_V1` mapping, keep analysis
non-mutating, resolve the four architectural quadruped limbs and contacts,
reject missing/duplicate/reversed/ambiguous cases, persist through save/reopen,
round-trip additive Action-package anatomy metadata, and unregister cleanly.
The generated rig is explicitly non-production.

Run the mode-aware creation/rollback regression first:

```text
blender --background --factory-startup --python tests/blender_damage_selection_acceptance.py
```

It must create and FAST-preview a paired Damage Key from one vertex, multiple
vertices, one face, and one connected face patch. Its forced empty-selection
failure must leave neither persisted nor cached phantom key/Stamp state. Its
final VIP save must also retain exactly four paired hybrid nodes: attached and
detached `RAISED` plus attached and detached `INLAY`. Both raised nodes must
report multiple nuclei and a nonzero nucleus triangle count, retain
surface-mass metadata, use the
crushed-tissue material role, and pass closed-manifold validation. The same acceptance
changes the Gore macros without saving and requires FAST to install the current
stain mask, BALANCED to build four preview-only hybrid components, and the
committed meshes to remain hidden while the unsaved preview is active. It also
lowers an existing key-level world-displacement cap below its historical Stamp
cap and requires the rebuilt coordinates to be projected to the new limit
before focused validation.

Run the saved-animation lifecycle regression:

```text
blender --background --factory-startup --python tests/blender_animation_library_acceptance.py
```

It must finalize a current walk draft, assign the exact playback range, edit on
a safe copy, overwrite under the original Action name/clip identity, reconnect
an NLA strip, export and import a native clip on a proportionally different
compatible rig, reject a missing-bone target, and delete without leaking Action
datablocks.

Run the Complete Damage runtime-skeleton regression:

```text
blender --background --factory-startup --python tests/blender_runtime_skeleton_export_acceptance.py
```

It must reject source-owned Idle/Walk duplicates by actual owner and approved
kind, mirror one compatible source-only clip without modifying it, normalize
multiple frame-1 temporary runtime copies to exact `0..clipDurationSeconds`
sampler bounds, preserve offensive phases and authored Actions, export only
`DSB_DAMAGE_RIG`, validate every skin/joint/channel relationship, retain rigid
pieces, hand sockets, and Light/Medium/Heavy morphs, clean-reimport one
armature hierarchy, and remove every temporary Action/NLA staging record.

Run the Character Variant Family ingest/save regression:

```text
blender --background --factory-startup --python tests/blender_character_variant_family_acceptance.py
```

It must consume exact Skin & Bones 2.2.0 handoff extras, switch two compatible
appearances, create no Action copies for the new appearance, create exactly one
copy for one explicit Action override, preserve active/override state through
save and reopen, and remove the owned Action on revert. The Complete Damage
runtime-skeleton regression additionally batch-exports two materially distinct
appearances, resolves one variant Walk override, preserves the zero-time
21-bone runtime contract, and clean-reimports the selected output.

The Progressive Damage Site regression also exercises both Damage copy-on-write
boundaries. It must clone exactly one Damage Key for a narrow override, exactly
the three assigned stage keys for a Site override, preserve shared coordinates,
leave unrelated keys inherited, and restore the shared graph without orphans on
revert.

Run the M6 offensive Action/socket regression as part of the same release gate:

```text
blender --background --factory-startup --python tests/blender_offensive_animation_acceptance.py
```

It must generate eight phase-valid offensive drafts, prove the custom timing
and motion sliders alter phase frames and keyframes, preserve each per-character
recipe across suite refresh, reject approval before preview, preview and
explicitly approve all eight Actions, and persist the recipe through
save/reload. It must also prove that none animates scale, preserve the exact
21-bone rest skeleton, keep socket ensure idempotent, persist an
artist-adjusted grip, and emit the two canonical hand socket records.

Run the 5.4.1 Natural Motion Studio regression:

```text
blender --background --factory-startup --python tests/blender_offensive_motion_studio_acceptance.py
```

It must build Sword Overhead to Head and Upper Torso, Mace Overhead, compact
Sword Thrust, both horizontal slashes, and Heavy Diagonal. Require exact ACTIVE
surface contact and direction, Natural extension below 92%, continuous body
support, bounded torso/shoulder response, no deform-arm location curves, no
one-frame FK step above 45 degrees, actionable impossible-reach blocking,
current pose-health/geometry/preview proof, approval, promotion, and helper
save/reopen recovery. Automated evidence does not replace the manual workflows
in the User Workflow Guide.

The Blender-free cavity suite exercises all six Gore identities, each macro at
0/25/50/75/100, and the exact reported head-macro regression. Every generated
internal layer must remain ordered between the measured rim and liner before a
release archive is built.

Use an artist-prepared source and run one bounded acceptance pass:

1. Register the add-on and prepare the character.
2. Create two Damage Keys in one region; enable both previews; toggle one off
   and confirm the other remains active.
3. Add two child Stamps to one key and confirm selecting a child changes only
   that key's one active alternative.
4. Exercise every Impact/additive Gore/cohesive Surface Gore macro endpoint and
   confirm it produces a meaningful numeric/geometry response without
   exceeding bounds. In particular, high Surface Mass must increase connected
   face retention and nonzero Nucleus must create multiple closed, varied
   lobulated masses across the deepest-response third.
5. Generate a hybrid recipe at raised 1.0 + inlay 1.0 and require both
   component nodes per role, distinct IDs/digests, valid materials, manifold
   shell/nucleus geometry, and inactive export defaults.
6. Save a Damage Blueprint from a head capture; apply it to fresh forearm/body
   captures and to another compatible humanoid asset. Confirm the destination
   capture/topology is used and no source indices appear in the Blueprint.
7. Save/reload the `.blend`, validate, export, clean-reimport, and confirm the
   manifest/component activation mapping.

Image-based artistic review is separate from this technical acceptance and
should be performed only when requested.

## Release archive

`python scripts/build_release.py` validates first and writes
`dist/Dreadstone_Animation_Forge_v5_4_1.zip`. Every package Python file is
discovered recursively, so new service/operator modules must appear in the
archive automatically. `dist/`, bytecode, caches, Blender backups, and
temporary extraction directories are generated artifacts and are not
committed.

Build twice from unchanged source and require identical SHA-256 hashes before a
release.

## Version changes

An authorized version change updates together:

1. `bl_info`, `blender_manifest.toml`, and component/build identifiers;
2. static validator and test expectations;
3. README, user workflow, runtime contracts, release guide, and changelog;
4. report filenames only when new reports are actually generated;
5. deterministic ZIP name and release metadata.

Do not claim Blender runtime or visual acceptance from static tests.
