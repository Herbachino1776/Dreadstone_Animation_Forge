# Dreadstone Animation Forge

Dreadstone Animation Forge `3.19.0` is a proprietary Blender add-on for
animation drafting and compatibility-preserving damage authoring. The supported
release runtime is Blender `5.1.2`.

Forge 3.19 replaces factory presets with a compact VIP workflow built around
Damage Keys, visible child Stamp alternatives, strong macros, one-click
deterministic randomization, additive raised + inlay gore, and portable
topology-independent Damage Blueprints. A dedicated cohesive surface deck can
form irregular connected relief or a closed lobulated tissue nucleus instead
of limiting raised gore to scattered face patches.

## Install and open

1. Download `Dreadstone_Animation_Forge_v3_19_0.zip`.
2. In Blender choose **Edit > Preferences > Add-ons > Install from Disk**.
3. Select the ZIP without extracting it and enable the add-on.
4. In the 3D Viewport press `N`, open **Dreadstone**, then choose
   **Damage Authoring**.

## Quick start

1. Import the source GLB and run **Prepare Character for Damage Authoring**.
2. Open **VIP DAMAGE WORKFLOW**, activate a region, and select one vertex,
   multiple vertices, one face, or one connected face patch.
3. Click **CREATE DAMAGE KEY FROM SELECTION**. The highlighted card clearly
   identifies the key being edited.
4. Toggle each Damage Key independently; any number of key previews can be on
   together. Pick one visible child Stamp alternative per key.
5. Tune the six Impact macros, six additive Gore macros, and the five
   **COHESIVE LEGACY SURFACE GORE** macros, or click **RANDOMIZE DAMAGE**.
   **SURFACE MASS** joins the raised patch, **NUCLEUS** creates solid internal
   tissue, **FOLDS** makes it lobulated, and **REDNESS** shifts the material
   response toward visible blood-red tissue. FAST previews the current stain;
   BALANCED adds temporary raised/inlay geometry. **UPDATE GORE PREVIEW**
   refreshes now.
6. Click **SAVE DAMAGE KEY + STAMP + GORE** only when the look is ready to
   commit and validate.
7. Save useful recipes with **ADD CURRENT RECIPE**. Apply them to a fresh
   capture on a different region or character from the adaptive Blueprint
   library.
8. Validate morphs, gore, and the complete asset before exporting the damage
   GLB and manifest.

At `RAISED AMOUNT = 1.0` and `INLAY AMOUNT = 1.0`, hybrid gore generates both
channels at full strength; it is not a half-and-half blend.

The authoritative procedure and complete button inventory are in the
[user workflow guide](docs/USER_WORKFLOW_GUIDE.md). Runtime consumers should
also read the [core/compound export contract](docs/CORE_COMPOUND_EXPORT_CONTRACT.md)
and [gore geometry export contract](docs/RAISED_GORE_EXPORT_CONTRACT.md).

## Persistence and compatibility

Damage Blueprints contain macros, seeds, relative scale ratios, and semantic
intent, including the cohesive surface controls. They never contain source
object names, topology fingerprints, vertex indices, or generated mesh bytes,
so the destination capture—not the source topology—controls placement.

Older authored deformation and gore records remain migration-readable. Legacy
factory recipe identifiers are internal compatibility data only and are not
offered as authoring presets.

## License

Copyright © Dreadstone. All rights reserved. No permission is granted to copy,
modify, distribute, sublicense, sell, or create derivative works except under a
separate written license from the copyright holder. See [LICENSE](LICENSE).
