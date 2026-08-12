# Release process

1. Update the authorized version/build IDs, manifest, README, user workflow,
   runtime contracts, validator, tests, and release filename together.
2. Run `python scripts/validate_addon.py`.
3. Run `python -m unittest discover -s tests -p "test_*.py"`.
4. Complete the focused Blender acceptance in
   [DEVELOPMENT.md](DEVELOPMENT.md), including simultaneous Damage Key toggles,
   mode-aware vertex/face selection and rollback, Stamp alternatives, hybrid
   1.0 + 1.0 components, cohesive Surface Gore macros, distributed nucleus
   geometry, VIP animation edit/overwrite/delete, portable clip compatibility,
   adaptive Blueprint reuse, validation, export, and clean reimport. For 5.4.1,
   also run the Natural Motion Studio sword/mace overhead, opposite-slash,
   thrust, reach, pose-health, and FK-bake acceptance and manually review the
   five documented attack workflows.
   Follow `docs/USER_WORKFLOW_GUIDE.md` as the authoritative user procedure.
5. Run `python scripts/build_release.py` twice and require identical SHA-256
   hashes.
6. Inspect the extension-root ZIP layout and run ZIP integrity/registration
   smoke checks.
7. Commit and publish only after the runtime evidence is recorded. Static
   success is not visual approval.

## Documentation definition of done

- [x] Version and `Dreadstone_Animation_Forge_v5_4_1.zip` match everywhere.
- [x] Creature Anatomy Profile schema/detection/orientation/persistence tests,
      the exact humanoid mapping comparison, malformed quadruped cases, and
      extracted-ZIP Blender registration pass.
- [x] AnyTop access commit, inspected files, licenses, checkpoint/data terms,
      external-only boundary, and multi-skeleton/multi-seed corpus plan are
      documented without vendored code, datasets, or checkpoints.
- [x] The VIP Damage Key -> Stamp -> macro workflow is current.
- [x] No user-facing factory preset instructions remain.
- [x] Independent multi-key Preview toggles and one active Stamp alternative
      per key are documented.
- [x] Hybrid raised + inlay 1.0 + 1.0 semantics and component export mapping
      are documented.
- [x] Surface Mass/Relief/Nucleus/Folds/Redness behavior, v6 legacy migration,
      nucleus materials/metadata, and Blueprint persistence are documented.
- [x] VIP animation Play/Edit/Save/Delete, NLA reconnection, and compatible
      `.blend` clip export/import are documented and runtime-tested.
- [x] Damage Blueprint save/apply portability and the fresh-destination-capture
      requirement are documented.
- [x] Source Readiness, validation, export, and clean-reimport procedures are
      current.
- [x] Complete Damage runtime membership, `DSB_DAMAGE_RIG`-only skeleton,
      Action owner/filter staging, source provenance, GLB v2 diagnostics, and
      clean-reimport regression pass.
- [x] Runtime hand sockets preserve the exact 21-bone rest skeleton, persist
      artist grip offsets, remain absent from GLB nodes/joints, and export
      finite canonical-hand-local transforms.
- [x] Eight offensive Actions pass approval, identity, phase, duration, socket,
      GLB inventory, sidecar, and clean-reimport regressions.
- [x] Motion Studio target volumes, proxy/trajectory schemas, opposite slash
      direction, overhead descent, thrust direction, FK bake, ACTIVE contact,
      plane tolerance, validation invalidation, approval, master promotion,
      helper exclusion, save/reopen, and targeting metadata regressions pass.
- [ ] Manual Dread Ram God mace-overhead review confirms readable anticipation,
      true target passage at CONTACT, dangerous ACTIVE speed, believable
      follow-through/recovery, no shoulder/elbow/wrist failure, and no foot
      sliding. Geometry PASS alone is not visual approval.
- [x] Character Variant Families consume exact Skin & Bones 2.2.0 metadata;
      compatibility refusal, zero-copy inheritance, Action and Damage
      copy-on-write/revert, save/reopen, two-output batch export, appearance
      materials, resolved provenance, 21-bone sockets, and zero-time clips pass.
- [x] No stale button label, version, archive name, or superseded workflow
      remains.
