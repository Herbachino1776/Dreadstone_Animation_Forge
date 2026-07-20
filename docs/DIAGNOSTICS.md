# Forge diagnostics and crash support

Forge 3.15 exposes diagnostics under **Advanced > Diagnostics and Crash Support**.

## Startup Self-Check

Run **Startup Self-Check** after installation, add-on reload, or a suspicious file reopen. It checks the managed preview lifecycle, duplicate Forge load handlers, active timer ownership, stale temporary preview keys/attributes, cached state availability, and registered task operators. Cleanup is scoped to Forge-owned temporary resources.

## WRITE FORGE DIAGNOSTIC REPORT

Choose an output directory and click **WRITE FORGE DIAGNOSTIC REPORT**. Forge writes JSON and Markdown and can mirror the report into a Blender Text datablock. The report includes:

- Forge version/build and Blender version;
- handler/timer and bounded-cache counts;
- object, mesh, material, Action, preview-resource, and generated-gore totals;
- the last ten timed Forge operations and last exception summary;
- active region, key, capture, stamp, and compound event identifiers;
- source, authoring, deformation, and export validation states.

The report intentionally excludes vertex coordinates, faces, weights, textures, and other proprietary mesh payloads.

## Useful crash report bundle

Provide the JSON and Markdown reports, Blender version, Forge ZIP SHA-256, source asset fingerprint when shareable, the last saved `.blend` only when authorized, and exact reproduction steps. Note whether the failure occurred during FAST preview, Final/Commit, gore generation, compound rebuild, full validation, save/reload, or export.

If a crash prevents report generation, rerun the same steps in a copy with Blender started from a console and include the console tail. Do not disable Source Readiness or validation to obtain a passing report.
