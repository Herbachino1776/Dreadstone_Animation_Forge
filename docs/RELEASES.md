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
   adaptive Blueprint reuse, validation, export, and clean reimport.
   Follow `docs/USER_WORKFLOW_GUIDE.md` as the authoritative user procedure.
5. Run `python scripts/build_release.py` twice and require identical SHA-256
   hashes.
6. Inspect the extension-root ZIP layout and run ZIP integrity/registration
   smoke checks.
7. Commit and publish only after the runtime evidence is recorded. Static
   success is not visual approval.

## Documentation definition of done

- [ ] Version and `Dreadstone_Animation_Forge_v5_2_2.zip` match everywhere.
- [ ] Creature Anatomy Profile schema/detection/orientation/persistence tests,
      the exact humanoid mapping comparison, malformed quadruped cases, and
      extracted-ZIP Blender registration pass.
- [ ] AnyTop access commit, inspected files, licenses, checkpoint/data terms,
      external-only boundary, and multi-skeleton/multi-seed corpus plan are
      documented without vendored code, datasets, or checkpoints.
- [ ] The VIP Damage Key -> Stamp -> macro workflow is current.
- [ ] No user-facing factory preset instructions remain.
- [ ] Independent multi-key Preview toggles and one active Stamp alternative
      per key are documented.
- [ ] Hybrid raised + inlay 1.0 + 1.0 semantics and component export mapping
      are documented.
- [ ] Surface Mass/Relief/Nucleus/Folds/Redness behavior, v6 legacy migration,
      nucleus materials/metadata, and Blueprint persistence are documented.
- [ ] VIP animation Play/Edit/Save/Delete, NLA reconnection, and compatible
      `.blend` clip export/import are documented and runtime-tested.
- [ ] Damage Blueprint save/apply portability and the fresh-destination-capture
      requirement are documented.
- [ ] Source Readiness, validation, export, and clean-reimport procedures are
      current.
- [ ] Complete Damage runtime membership, `DSB_DAMAGE_RIG`-only skeleton,
      Action owner/filter staging, source provenance, GLB v2 diagnostics, and
      clean-reimport regression pass.
- [ ] Runtime hand sockets preserve the exact 21-bone rest skeleton, persist
      artist grip offsets, remain absent from GLB nodes/joints, and export
      finite canonical-hand-local transforms.
- [ ] Eight offensive Actions pass approval, identity, phase, duration, socket,
      GLB inventory, sidecar, and clean-reimport regressions.
- [ ] No stale button label, version, archive name, or superseded workflow
      remains.
