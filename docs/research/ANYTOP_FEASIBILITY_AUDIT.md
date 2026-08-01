# AnyTop access and feasibility audit

Inspection date: 2026-07-31 (America/New_York)

## Access and scope

Read-only web access and `git ls-remote` succeeded for
[Anytop2025/Anytop](https://github.com/Anytop2025/Anytop). The exact inspected
`main` commit is
[`e780d1575ca0121f29bb53821b309cf564156a95`](https://github.com/Anytop2025/Anytop/commit/e780d1575ca0121f29bb53821b309cf564156a95).
The first sandboxed Git network attempt failed name resolution; an approved
read-only `git ls-remote` and shallow source clone then succeeded. GitHub's web
cache also failed to return two raw dependency-license files, so the small
GANimator evaluation dependency was source-cloned separately for license
inspection. No dataset or checkpoint was downloaded.

Files directly inspected were `README.md`, `LICENSE`, `environment.yaml`,
`utils/process_new_skeleton.py`, `utils/download_dependencies.py`,
`utils/hf_handler.py`, `utils/fixseed.py`, `utils/parser_util.py`,
`utils/PYTORCH3D_LICENSE`, Truebones `motion_process.py`, `param_utils.py`,
`process_new_skeleton.py`, `plot_script.py`, `data/dataset.py`,
`model/anytop.py`, `model/motion_transformer.py`, `model/conditioners.py`,
`sample/generate.py`, `sample/edit.py`, `sample/dift_correspondence.py`,
`visualization/bvh2skeleton.py`, the Blender stick-figure visualizer, and the
evaluation entry points.

## Architecture relevant to arbitrary skeletons

New-skeleton preprocessing consumes BVH clips, four face joints (right/left hip
and right/left shoulder), and preferably a named natural rest-pose BVH. If no
rest file is provided it heuristically chooses a `tpos`, then `idle`, then the
first BVH, which is too weak for production ingestion. It normalizes global
facing to `+Z` with `Y` up, grounds the motion on the XZ plane, moves root XZ to
the origin, and scales by average bone length. Forge uses `+Y` forward and `+Z`
up for its digitigrade profile, so a measured coordinate conversion is
mandatory.

The per-joint motion feature is root-relative position (3), continuous 6D
rotation (6), velocity (3), and contact (1). Conditioning stores the first
rest-pose frame, parents, offsets, joint names, kinematic chains, mean/std, and
topological relations/distances. Relations distinguish self, parent, child,
sibling, disconnected, end-effector, and temporal-token cases; graph distance
is clipped to five. T5 encodes normalized textual joint descriptions after
prefix removal. The graph/temporal transformer therefore has a credible
arbitrary-skeleton research design without requiring one fixed joint count.

The Truebones subset includes humanoids, quadrupeds, and other skeletons; that
is evidence of broad experiments, not production support for every anatomy.
Foot/contact aliases include toe, foot, phalanx, hoof, Japanese `ashi`, and all
children. Contact uses a fixed squared 3D velocity threshold (`0.002`) and
absolute Y-height threshold (`0.3`). Face joints, rest-pose selection, name
normalization, and contact thresholds are heuristic and require corpus-specific
verification. Snakes treat all joints as feet, underscoring that topology alone
does not provide Forge-grade semantics.

## Generation, editing, and output

Generation accepts text, skeleton conditioning, length, seed, and repetitions;
the documented maximum is about 9.8 seconds, default FPS is 20, and the default
example length is six seconds. Long preprocessing windows are bounded and
segmented. Seed handling covers Python, NumPy, and PyTorch and disables cuDNN
benchmarking, but the code does not enable every strict deterministic mode, so
bit-identical cross-device output is not established.

Outputs include feature/XYZ NumPy data, MP4 preview, and BVH reconstructed from
positions by iterative IK. Editing supports in-between and upper-body masks;
DIFT tooling explores spatial and temporal correspondences. The Blender script
imports a BVH and builds a stick-figure visualization with subset-specific
scale/location adjustments. It is not production retargeting and asks Blender's
Python to carry Motion/scientific dependencies, which Forge must not adopt.

## Runtime and acquisition

The pinned environment targets Linux/Ubuntu-era tooling, Python 3.8.15,
PyTorch 2.4.1, CUDA 12.1/cuDNN, Transformers 4.46.3, spaCy 3.7.2, NumPy 1.24.4,
SciPy 1.10.1, Matplotlib 3.1.3, MoviePy, ImageIO, Hugging Face Hub, and an
external `inbar-2344/Motion` Git dependency. Dependency tooling downloads spaCy
and T5 assets. Checkpoint/data acquisition snapshots
[`Inbar2344/AnyTop`](https://huggingface.co/Inbar2344/AnyTop/tree/main) and links
checkpoint and conditioning-data folders. The repository README says the
processed training dataset is withheld while licensing is clarified.

## License and redistribution findings

| Item | Observed terms | Forge decision |
| --- | --- | --- |
| AnyTop source | MIT `LICENSE` | Research reading allowed; no code copied or vendored in this milestone. |
| Included PyTorch3D notice | BSD 3-Clause-style | Retain attribution if ever redistributed. |
| Python / PyTorch / NumPy / SciPy / NetworkX | PSF / BSD-family | External-runtime dependencies only. |
| Transformers / Hugging Face Hub / Google T5 family | Apache-2.0 indicated by upstream projects/models | Reverify exact model revision and notices before use. |
| spaCy / MoviePy / blobfile / PyYAML | MIT-family | External-runtime dependencies only. |
| num2words | LGPL-2.1; `tqdm` | MPL-2.0/MIT dual terms | Keep isolated and review redistribution/notice obligations. |
| ImageIO | BSD-2-Clause; Matplotlib | PSF-derived; Pillow | HPND; preserve notices if redistributed. |
| Requests / SentencePiece / safetensors | Apache-2.0 family | External-runtime dependencies only; lock exact revisions before use. |
| ImageIO-FFmpeg / FFmpeg binary | Wrapper and codec binary have separate license/build-option implications | Audit the exact binary and enabled codecs before acquisition or redistribution. |
| GANimator evaluation kernel / vendored pybind11 | BSD-2-Clause / BSD-3-Clause in the inspected dependency `LICENSE` | Evaluation-only external dependency; retain notices. |
| CUDA/cuDNN | NVIDIA proprietary/EULA terms | Never bundle through Forge; installation and redistribution need separate review. |
| [`inbar-2344/Motion`](https://github.com/inbar-2344/Motion) | No license file or detected license in the inspected repository | **Blocking license ambiguity**; default copyright applies absent permission. |
| Hugging Face AnyTop checkpoint repository | MIT tag, minimal model card, no detailed training-data provenance/terms | Tag alone is insufficient for production redistribution or output clearance. |
| Truebones source BVH/FBX | [Royalty-free use claimed, but raw redistribution/resale prohibited](https://truebones.gumroad.com/l/vlvPq) | Do not redistribute source assets or derived conditioning dataset; obtain legal review. |
| Generated motion | No extra restriction stated by AnyTop source license | Checkpoint/data provenance may affect output rights; production distribution remains unresolved. |

This is an engineering audit, not legal advice. Exact dependency revisions,
notices, checkpoint permission, training-data provenance, Truebones derivative
limits, and generated-output rights need a separate licensing decision before
AnyTop output calibrates or ships with Forge.

## Feasibility decision

AnyTop is suitable as a motion-design reference: its topology conditioning,
semantic joint text, multi-skeleton preprocessing, contact channels,
correspondence, and inpainting suggest useful measurements. It may become an
optional **external** candidate generator after licensing and environment
qualification. It is unsuitable as an in-Blender library, bundled dependency,
direct production retargeter, canonical skeleton authority, or source of copied
implementation. GPU/CUDA, old Python constraints, the unlicensed Motion
dependency, heuristic orientation/contact logic, rest-pose quality, checkpoint
provenance, and dataset terms remain blockers.

Native Forge animation remains required because it must be deterministic,
editable, anatomy-aware, validation-gated, licensable, installable without ML,
and compatible with protected production Actions. No gait defaults are guessed
in this milestone.
