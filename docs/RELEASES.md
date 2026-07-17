# Release process

1. **Update version contracts.** Change the authorized add-on and component versions/build IDs, documentation, changelog, validator, tests, and release filename together. Do not silently change schemas, operator identifiers, or generated DSB names.
2. **Run static validation.** Run `python scripts/validate_addon.py` and `python -m unittest discover -s tests -p "test_*.py"` from a clean checkout.
3. **Run Blender runtime acceptance.** Complete and record every Blender 5.1.2 step in `docs/DEVELOPMENT.md`. Static CI is not runtime acceptance.
4. **Build the deterministic ZIP.** Run `python scripts/build_release.py` twice and require identical SHA-256 hashes.
5. **Inspect archive layout.** Confirm the exact seven-entry Blender-installable layout and run a ZIP integrity check.
6. **Tag the release.** Commit directly to `main`, push, and create an annotated `v*` tag for the accepted commit.
7. **Publish with GitHub Actions.** Push the tag. The release workflow reruns static validation/tests, rebuilds the deterministic ZIP, creates or updates the GitHub Release, and attaches the ZIP. It does not claim Blender runtime testing.
