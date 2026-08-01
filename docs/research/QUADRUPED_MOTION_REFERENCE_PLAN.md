# Quadruped motion-reference corpus plan

The next milestone will measure candidate motion before implementing native
gaits. It must include several independently structured, licensed digitigrade
skeletons and multiple fixed seeds per motion, speed, and skeleton. One
favorable render cannot establish a default. Preserve generator/version,
checkpoint, prompt, skeleton fingerprint, rest pose, coordinate conversion,
seed, length, FPS, and license provenance for every sample.

## Isolated flow

External candidate generator -> BVH/measurement corpus -> external analysis ->
isolated Blender import -> Creature Anatomy Profile retargeting -> Forge draft
-> Forge technical validation -> artist approval -> protected production
Action. AnyTop/PyTorch/CUDA/Conda stays outside Blender and Forge. Raw datasets,
checkpoints, and restricted source assets are never committed or embedded.

## Required measurements

Normalize without hiding defects and record:

- source and evaluated frame rate, frame count, cycle boundaries/duration, root
  trajectory, speed, drift, and declared/measured forward direction;
- all four paw contact intervals, phase offsets, duty factor (stance/swing
  percentages), stride length, paw clearance, foot sliding, and floor
  penetration;
- elbow, stifle, carpus, and hock angular ranges; scapula travel; pelvis
  translation/rotation; spine compression/extension; chest counter-motion;
  neck/head stabilization; and tail phase lag;
- bilateral/front-hind symmetry and intended asymmetry by motion family;
- per-bone length change, every non-root translation and scale channel,
  quaternion/Euler discontinuity, velocity/acceleration spikes, loop seam, IK
  reconstruction error, and retargeting residual.

Report distributions across skeletons and seeds, not only averages. Include
median, robust spread, extrema, failure counts, contact confusion, and
cross-skeleton covariance. Review original, converted, and retargeted motion at
the same ground plane and orientation.

## Classification

- `ACCEPTED_REFERENCE`: technically valid, repeatably useful across the corpus,
  rights-cleared, and artist-approved as a measurement reference.
- `USEFUL_BUT_FLAWED`: contains measurable ideas but needs repair or is not
  robust enough to define defaults; isolate the usable observations.
- `REJECTED`: invalid topology/rights, severe sliding/penetration/discontinuity,
  broken anatomy, or unrepresentative result.

Rejected motions must not calibrate Forge defaults. Unresolved licensing also
prevents `ACCEPTED_REFERENCE` even when motion looks good.

## Native macro calibration

Future macro families are **SPEED**, **STRIDE**, **LIFT**, **DRIVE**,
**BODY MOTION**, and **WILDNESS**. Their mappings will be fitted from measured
relationships and covariance among cadence, stride, duty factor, joint ranges,
root/pelvis/chest/spine motion, contact stability, and controlled residual
variation. They will not be arbitrary independent multipliers. Correlated
constraints must preserve contact timing, bone lengths, continuity, and the
anatomy profile's orientation while exposing artist-meaningful control.
