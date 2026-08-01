# Quadruped canonical fixture requirements

Forge 4.1 has no inspected production quadruped fixture. Its generated
`DSB_SYNTHETIC_ARCHITECTURAL_QUADRUPED` exists only for deterministic schema,
resolver, validation, persistence, and Blender runtime tests. It must not define
production bone names, proportions, deformation quality, or animation quality.

A later canonical digitigrade fixture must provide:

- a documented parent hierarchy and stable canonical names;
- exact character-local rest transforms, head/tail coordinates, local axes,
  roll, bone lengths, and deform flags;
- explicit `+Y` forward and `+Z` up proof, with ground root separate from the
  body/pelvis motion carrier;
- four distinct contact endpoints and unambiguous front/hind and left/right
  ownership;
- documented scapula, carpus, pelvis/hip, hock, spine, neck, jaw, paw/toe, and
  tail conventions, including allowed variable segments;
- a clean, licensed GLB with uniform armature scale, finite weights, no hidden
  helper dependency, and preserved skin/rest state after clean reimport;
- representative idle, walk, trot, pace, canter, gallop, turn, bite, paw
  attack, pounce, hurt, and collapse Actions where available;
- armature, hierarchy, rest-matrix, mesh/topology, weight, and Action
  fingerprints plus provenance and redistribution terms;
- save/reopen, Action-package, GLB export, and clean-reimport inventory proof
  in Blender 5.1.2.

Acceptance requires direct inspection of hierarchy, transforms, axes, bounds,
weights, and Actions. Names alone are not evidence. Large binary assets require
repository-policy approval before commit.
