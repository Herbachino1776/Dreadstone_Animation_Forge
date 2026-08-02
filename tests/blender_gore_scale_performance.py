"""Blender benchmark for gore slider mesh-scale sampling.

Run from the repository root:

    blender --background --factory-startup \
      --python tests/blender_gore_scale_performance.py -- \
      --output build/gore_scale_performance.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dreadstone_animation_forge import deformation_authoring  # noqa: E402
from dreadstone_animation_forge.deformation import mesh_snapshot  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--vertices", type=int, default=100_000)
    parser.add_argument("--samples", type=int, default=7)
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(values)


def make_mesh(vertex_count):
    vertices = [
        (index * 0.001, (index % 17) * 0.0001, (index % 29) * 0.00005)
        for index in range(vertex_count)
    ]
    edges = [(index, index + 1) for index in range(vertex_count - 1)]
    mesh = bpy.data.meshes.new("DAF_Gore_Scale_Performance_Mesh")
    mesh.from_pydata(vertices, edges, [])
    obj = bpy.data.objects.new("DAF_Gore_Scale_Performance_Object", mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def legacy_full_snapshot(obj):
    mesh_snapshot.clear_cache("performance benchmark")
    positions = mesh_snapshot.world_positions(obj)
    edges = mesh_snapshot.edges(obj)
    samples = []
    for first, second in edges[:512]:
        distance = (
            Vector(positions[int(first)])
            - Vector(positions[int(second)])
        ).length
        if math.isfinite(distance) and distance > 1e-12:
            samples.append(distance)
    return sum(samples) / len(samples) if samples else None


def timed(callback, sample_count):
    callback()
    durations = []
    value = None
    for _index in range(sample_count):
        started = time.perf_counter()
        value = callback()
        durations.append((time.perf_counter() - started) * 1000.0)
    return {
        "durationsMs": [round(item, 6) for item in durations],
        "medianMs": round(statistics.median(durations), 6),
        "minimumMs": round(min(durations), 6),
        "maximumMs": round(max(durations), 6),
        "meanEdgeLength": value,
    }


def main():
    args = parse_args()
    obj = make_mesh(args.vertices)
    legacy = timed(lambda: legacy_full_snapshot(obj), args.samples)
    sampled = timed(
        lambda: deformation_authoring._sample_mean_edge_length(obj),
        args.samples,
    )
    if abs(float(legacy["meanEdgeLength"]) - float(sampled["meanEdgeLength"])) > 1e-12:
        raise RuntimeError("Direct edge sampling changed the derived mesh scale.")
    report = {
        "blenderVersion": bpy.app.version_string,
        "fixture": {
            "vertices": len(obj.data.vertices),
            "edges": len(obj.data.edges),
            "sampledEdges": 512,
        },
        "legacyFullSnapshot": legacy,
        "sampledDirect": sampled,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("DAF_GORE_SCALE_PERFORMANCE=" + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
