# Release process

1. **Update version contracts.** Change the authorized add-on and component versions/build IDs, `docs/USER_WORKFLOW_GUIDE.md`, README, changelog, validator, tests, and release filename together. Do not silently change schemas, operator identifiers, or generated DSB names.
2. **Run static validation.** Run `python scripts/validate_addon.py` and `python -m unittest discover -s tests -p "test_*.py"` from a clean checkout.
3. **Run Blender runtime acceptance.** Complete and record the current procedures and recipes in `docs/USER_WORKFLOW_GUIDE.md`. For Forge 3.14, run both `tests/blender_raised_gore_acceptance.py` and `tests/blender_core_compound_guard_acceptance.py` from appropriate prepared authoring `.blend` files. Record head/body/forearm triangle counts, full-weight compound seam mismatch/topology state, all guard validations, and both clean-reimport results. Static CI is not runtime acceptance or visual approval.
4. **Build the deterministic ZIP.** Run `python scripts/build_release.py` twice and require identical SHA-256 hashes.
5. **Inspect archive layout.** Confirm the exact eight-entry Blender-installable layout and run a ZIP integrity check.
6. **Tag the release.** Commit directly to `main`, push, and create an annotated `v*` tag for the accepted commit.
7. **Publish with GitHub Actions.** Push the tag. The release workflow reruns static validation/tests, rebuilds the deterministic ZIP, creates or updates the GitHub Release, and attaches the ZIP. It does not claim Blender runtime testing.

## User guide release definition of done

- [ ] Inspect the current implementation and update `docs/USER_WORKFLOW_GUIDE.md` when the workflow, UI, feature set, installation method, object names, validation process, or export process has changed.
- [ ] Confirm the guide's version number and ZIP name match the current release.
- [ ] Confirm every public user-facing operator and major workflow section is represented in the guide.
- [ ] Confirm Source Readiness reruns use only the registered original inventory after authoring and never report generated cut boundaries as source defects.
- [ ] Confirm Authoring Validation and Export Validation are distinct, and export does not rewrite the source-readiness JSON/Markdown report.
- [ ] Confirm **Repair Source Readiness Contract** preserves generated topology, managed shape keys, and trauma stamps in an affected 3.8 file.
- [ ] Confirm the GLB/manifest satisfies `docs/RAISED_GORE_EXPORT_CONTRACT.md`: stable paired nodes, three glTF-safe materials, inactive defaults, deformation activation mapping, geometry digests, and clean reimport.
- [ ] Confirm the GLB/manifest satisfies `docs/CORE_COMPOUND_EXPORT_CONTRACT.md`: explicit region mode, per-mesh child morphs, synchronized compound activation, participant gore roles, seam report, brace metadata, and clean reimport.
- [ ] Confirm Source Damage Readiness and `NOT READY` repair behavior were not loosened, reinterpreted, or speculatively expanded.
- [ ] Remove stale instructions from the previous version.
