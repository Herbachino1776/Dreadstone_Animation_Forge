# Dreadstone Animation Forge

Dreadstone Animation Forge `3.18.0` is a proprietary Blender add-on for animation drafting and compatibility-preserving damage authoring. It retains protected Source Readiness, paired and core trauma fields, compound events, exact-index morph synchronization, legacy gore modes, brace Actions, and GLB/manifest export. Forge 3.18 adds scale-relative recessed Cavity/Inlay Gore, a six-control Gore Pedal, six distinct wound identities, deterministic seed exploration, preview-only quality levels, and manifold export geometry. The supported release runtime is Blender `5.1.2`.

## Install and open

1. Download `Dreadstone_Animation_Forge_v3_18_0.zip`.
2. In Blender 5.1.2 choose **Edit > Preferences > Add-ons > Install from Disk**.
3. Select the ZIP without extracting it and enable **Dreadstone Animation Forge**.
4. In the 3D Viewport press `N`, then open the **Dreadstone** tab.

## Quick start

1. Import a source GLB, save a working `.blend`, select its mesh or armature, and open **Start / Character**.
2. Choose the explicit readiness output folder and target height, then click **Prepare Character for Damage Authoring**. The orchestrator reports every step and stops on `NOT READY`; it never guesses a repair.
3. In **Damage Authoring**, activate Head, Body, Left Forearm, or Right Forearm. Enter Face Edit mode and select one connected surface patch chosen by the artist.
4. Choose the impact direction, family, intensity, and optional semantic name, then click **Create Impact From Current Selection**.
5. Use the top **IMPACT CONTROL DECK** to tune **SIZE**, **CRUSH**, **PROFILE**, **EDGE SAFETY**, and **CHAOS**. Directly below it, use the **GORE CONTROL DECK** to choose a wound identity, tune **EXPOSURE**, **CAVITY**, **CLOT FILL**, **BREAKUP**, **WETNESS**, and **VARIATION**, randomize only the gore seed, generate a preview, and commit. Advanced raw controls remain available through explicit MANUAL modes.
6. Use **Validate & Export** for focused morph/gore checks, complete authoring validation, and **Export Damage GLB + Manifest**. Clean-reimport the GLB and restore its intact preview for inspection.
7. Use **Advanced** for every manual 3.14 workflow: explicit readiness/build steps, custom region registration, capture modes, stamp ordering, pair synchronization, portable libraries v1–v4, compound participants, detailed gore budgets, legacy presets, and diagnostics.

Source Readiness remains bound to the preserved original source after segmentation. Forge 3.18 does not weaken or reinterpret `NOT READY`, and it does not repair intentional generated cut boundaries as if they were source damage.

For exact selections, body/forearm/compound recipes, all legacy controls, diagnostics, export checks, and troubleshooting, use the authoritative [Forge user workflow guide](docs/USER_WORKFLOW_GUIDE.md). Runtime consumers should also read the [core/compound export contract](docs/CORE_COMPOUND_EXPORT_CONTRACT.md) and [raised gore export contract](docs/RAISED_GORE_EXPORT_CONTRACT.md).

## Performance and crash support

The preview manager debounces slider changes on Blender's main thread, reuses a single temporary deformation key, bounds reusable caches, and keeps BALANCED/FINAL gore preview objects preview-only until an explicit commit. If a problem occurs, open **Advanced > Diagnostics and Crash Support**, run **Startup Self-Check**, then click **WRITE FORGE DIAGNOSTIC REPORT**. Reports contain timings and contract state, not proprietary mesh payloads.

## License

Copyright Herbachino1776. All rights reserved. See [LICENSE](LICENSE).
