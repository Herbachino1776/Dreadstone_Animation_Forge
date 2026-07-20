# Dreadstone Animation Forge

Dreadstone Animation Forge `3.14.0` is a proprietary Blender add-on for animation drafting, protected damage-segment and stump authoring, paired and core-mesh trauma fields, compound multi-region impacts, high-intensity raised surface gore, mace head-guard drafts, and GLB/manifest export. The supported runtime is Blender `5.1.2`.

## Install and open

1. Download `Dreadstone_Animation_Forge_v3_14_0.zip`.
2. In Blender 5.1.2 choose **Edit > Preferences > Add-ons > Install from Disk**.
3. Select the ZIP without extracting it and enable **Dreadstone Animation Forge**.
4. In the 3D Viewport press `N`, then open the **Dreadstone** tab.

## Quick start

1. Import a source GLB with **File > Import > glTF 2.0 (.glb/.gltf)** and save a working `.blend`.
2. Select the imported character mesh or armature, run **Analyze Rig**, and prepare sizing/grounding only if needed.
3. Choose an explicit **Report Output Folder** and run **Analyze Source Damage Readiness** on the original imported source.
4. When all four seams are automatic and **Overall** is `SOURCE READY`, run **Load READY Handoff** and **Build Authoring Asset**.
5. Register exact-topology attached/detached pairs with **Register Selected Pair**, or register `DSB_BODY_CORE` without a fake partner using **Register Selected Core Mesh**. Capture the intended artist-selected surface, add trauma stamps, then run **REBUILD ACTIVE DEFORMATION**.
6. For one impact crossing objects, create a **Compound Trauma Event**, add two or more active region/key participants, capture its shared world-space field, link any real seam contract, and run **REBUILD COMPOUND EVENT**. Forge writes one mesh-local morph per participant and exports one synchronized semantic activation contract.
7. For heavy blunt damage, choose `Gore_Crush_Heavy_Clotted` and click **Preview / Rebuild Current Gore**, or use **Apply Heavy Gore to All Deformations**. Forge adds a broken stain plus smoother tapered raised-clot shells to head, core, and forearm regions while leaving the original exterior intact.
8. Generate the three disposable mace head-guard drafts in **Mace Head-Guard Drafts**, preview `Guard_Active`, visually inspect the pose, then explicitly promote acceptable drafts into the Approved Animation Pack.
9. Use **Save Stamp Library...** to preserve core, paired, and compound recipes without embedding mesh bytes. Require **Validate Morph Targets**, **Validate Compound Event**, and **Validate Complete Damage Asset** to pass.
10. Run **Export Damage GLB + Manifest** (Export Validation), import the GLB into a clean scene, and click **Restore Reimported GLB Intact Preview**. Build the Approved Animation Pack separately for approved brace Actions.

Source Readiness remains bound to the preserved original source after segmentation. Forge 3.14 does not loosen, reinterpret, or add new `NOT READY` repair behavior. Do not repair intentional cut boundaries on generated `DSB_*` meshes; a real failure report is required before any future readiness change.

For exact object selections, every current feature and UI label, animation workflows, complete recipes, expected results, and troubleshooting, use the authoritative [Forge user workflow guide](docs/USER_WORKFLOW_GUIDE.md). Runtime consumers should also read the [core/compound export contract](docs/CORE_COMPOUND_EXPORT_CONTRACT.md) and [raised gore export contract](docs/RAISED_GORE_EXPORT_CONTRACT.md).

## License

Copyright Herbachino1776. All rights reserved. See [LICENSE](LICENSE).
