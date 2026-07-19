# Dreadstone Animation Forge

Dreadstone Animation Forge `3.13.0` is a proprietary Blender add-on for animation drafting, protected damage-segment and stump authoring, portable trauma-stamp libraries, trauma-field morph authoring, high-intensity raised surface gore, and GLB/manifest export. The supported runtime is Blender `5.1.2`.

## Install and open

1. Download `Dreadstone_Animation_Forge_v3_13_0.zip`.
2. In Blender 5.1.2 choose **Edit > Preferences > Add-ons > Install from Disk**.
3. Select the ZIP without extracting it and enable **Dreadstone Animation Forge**.
4. In the 3D Viewport press `N`, then open the **Dreadstone** tab.

## Quick start

1. Import a source GLB with **File > Import > glTF 2.0 (.glb/.gltf)** and save a working `.blend`.
2. Select the imported character mesh or armature, run **Analyze Rig**, and prepare sizing/grounding only if needed.
3. Choose an explicit **Report Output Folder** and run **Analyze Source Damage Readiness** on the original imported source.
4. When all four seams are automatic and **Overall** is `SOURCE READY`, run **Load READY Handoff** and **Build Authoring Asset**.
5. Register exact-topology attached/detached pairs, capture surfaces, add trauma stamps, then run **REBUILD ACTIVE DEFORMATION**. For heavy blunt damage, choose `Gore_Crush_Heavy_Clotted` and click **Preview / Rebuild Current Gore**, or use **Apply Heavy Gore to All Deformations**. Forge keeps the original exterior intact, adds a broken stain, and builds ordinary exportable raised-clot meshes for both paired variants. Use **Save Stamp Library...** to preserve reproducible recipes without embedding mesh bytes.
6. Require **Validate Morph Targets** and **Validate Complete Damage Asset** (Authoring Validation) to pass.
7. Run **Export Damage GLB + Manifest** (Export Validation), import the GLB into a clean scene, and click **Restore Reimported GLB Intact Preview**.

Source Readiness remains bound to the preserved original source after segmentation. Do not repair intentional cut boundaries on generated `DSB_*` meshes. For an affected Forge 3.8 file whose later report analyzed generated pieces, use **Repair Source Readiness Contract**; it restores the source-only report without deleting generated topology, shape keys, or trauma stamps.

For exact object selections, every current feature and UI label, animation workflows, complete recipes, expected results, and troubleshooting, use the authoritative [Forge user workflow guide](docs/USER_WORKFLOW_GUIDE.md). Runtime consumers should also read the [raised gore export contract](docs/RAISED_GORE_EXPORT_CONTRACT.md).

## License

Copyright Herbachino1776. All rights reserved. See [LICENSE](LICENSE).
