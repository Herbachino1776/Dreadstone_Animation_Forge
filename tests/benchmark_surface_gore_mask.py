"""Repeatable pure-Python benchmark for surface-gore mask evaluation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "dreadstone_animation_forge" / "trauma_field.py"
SPEC = importlib.util.spec_from_file_location(
    "dreadstone_trauma_field_benchmark",
    MODULE_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load trauma_field.py")
trauma_field = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trauma_field)


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--vertices", type=int, default=11_792)
    parser.add_argument("--samples", type=int, default=5)
    return parser.parse_args()


def timed(callback, sample_count):
    callback()
    durations = []
    values = None
    for _index in range(sample_count):
        started = time.perf_counter()
        values = callback()
        durations.append((time.perf_counter() - started) * 1000.0)
    return {
        "durationsMs": [round(value, 6) for value in durations],
        "medianMs": round(statistics.median(durations), 6),
        "minimumMs": round(min(durations), 6),
        "maximumMs": round(max(durations), 6),
        "checksum": {
            "count": len(values),
            "sum": round(sum(values), 12),
            "maximum": round(max(values, default=0.0), 12),
        },
    }


def main():
    args = arguments()
    overlay = trauma_field.default_gore_overlay(
        "Gore_Crush_Bloodied",
        enabled=True,
        region_id="head",
        linked_stamp_id="head_0",
        selection_hash="abc",
        topology_fingerprint="a" * 64,
        seed=1776,
    )
    weights = [
        (index % 101) / 100.0
        for index in range(args.vertices)
    ]
    positions = [
        (
            (index % 113) * 0.007,
            ((index // 113) % 97) * 0.009,
            (index % 43) * 0.005,
        )
        for index in range(args.vertices)
    ]
    scalar = timed(
        lambda: [
            trauma_field.gore_mask_value(weight, position, overlay)
            for weight, position in zip(weights, positions)
        ],
        args.samples,
    )
    bulk = timed(
        lambda: trauma_field.gore_mask_values(
            weights,
            positions,
            overlay,
        ),
        args.samples,
    )
    if scalar["checksum"] != bulk["checksum"]:
        raise RuntimeError("Bulk gore masking changed the deterministic output.")
    report = {
        "fixture": {
            "vertices": args.vertices,
            "seed": 1776,
            "preset": "Gore_Crush_Bloodied",
        },
        "scalarPerVertexNormalization": scalar,
        "bulkSingleNormalization": bulk,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("DAF_SURFACE_GORE_MASK_PERFORMANCE=" + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
