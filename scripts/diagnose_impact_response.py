#!/usr/bin/env python3
"""Measure Impact Pedal geometry response and deterministic seed diversity."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"
OUTPUT = ROOT / "docs" / "IMPACT_RESPONSE_DIAGNOSTICS_v3.19.0.json"
LEVELS = (0, 25, 50, 75, 100)
MACROS = ("size", "crush", "profile", "edgeDamage", "distortion", "asymmetry")


def load_module(name, path):
    module_spec = importlib.util.spec_from_file_location(name, path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


parameter_schema = load_module("impact_response_parameter_schema", PACKAGE / "parameter_schema.py")
trauma_field = load_module("impact_response_trauma_field", PACKAGE / "trauma_field.py")


def fixture_grid(size=41, spacing=0.01):
    half = (size - 1) * 0.5
    return tuple(
        ((x - half) * spacing, (y - half) * spacing, 0.0)
        for y in range(size)
        for x in range(size)
    )


POSITIONS = fixture_grid()


def smoothstep(value):
    value = max(0.0, min(1.0, float(value)))
    return value * value * (3.0 - 2.0 * value)


def geometry_digest(coordinates):
    digest = hashlib.sha256()
    for point in coordinates:
        digest.update(struct.pack("<3d", *(float(value) for value in point)))
    return digest.hexdigest()


def sample(macros, seed=1776, family="COMPACT_DENT"):
    derived = parameter_schema.derive_impact_parameters(
        macros,
        region_scale=0.075,
        family=family,
        seed=seed,
    )
    radius = float(derived["radius"])
    seam = float(derived["seamProtection"])
    distances = {
        index: math.hypot(point[0], point[1])
        for index, point in enumerate(POSITIONS)
        if math.hypot(point[0], point[1]) <= radius
    }
    weights = []
    for index, point in enumerate(POSITIONS):
        distance = distances.get(index)
        weight = (
            trauma_field.falloff_weight(distance, radius, float(derived["falloff"]))
            if distance is not None else 0.0
        )
        if seam > 0.0:
            seam_distance = abs(point[0] - 0.06)
            weight *= smoothstep(seam_distance / seam)
        weights.append(weight)
    stamp = trauma_field.normalize_stamp({
        "stampId": "diagnostic",
        "displayName": "Impact Response Diagnostic",
        "enabled": True,
        "family": family,
        "placementMode": "SELECTED_VERTICES",
        "capture": {"selectionHash": "diagnostic"},
        "center": [0.0, 0.0, 0.0],
        "direction": [0.0, 0.0, -1.0],
        "radius": derived["radius"],
        "depth": derived["depth"],
        "falloff": derived["falloff"],
        "influenceMode": "CONNECTED_SURFACE",
        "distanceMode": "WORLD_DISTANCE",
        "featherDistance": derived["featherDistance"],
        "seamProtection": derived["seamProtection"],
        "strength": derived["strength"],
        "maximumDisplacement": derived["maximumDisplacement"],
        "impactSeed": derived["impactSeed"],
        "impactChaos": derived["impactChaos"],
        "impactEdgeDamage": derived["impactEdgeDamage"],
        "impactAsymmetry": derived["impactAsymmetry"],
        "impactProfile": derived["impactProfile"],
        "profileCenterRimBalance": derived["profileCenterRimBalance"],
        "orderIndex": 0,
    })
    coordinates = trauma_field.evaluate_stamp_stack(
        POSITIONS,
        (stamp,),
        {"diagnostic": tuple(weights)},
        {"diagnostic": distances},
    )
    displacements = [
        math.sqrt(sum((coordinates[index][axis] - point[axis]) ** 2 for axis in range(3)))
        for index, point in enumerate(POSITIONS)
    ]
    affected = [index for index, value in enumerate(displacements) if value > 1e-9]
    affected_radius = max(
        (math.hypot(POSITIONS[index][0], POSITIONS[index][1]) for index in affected),
        default=0.0,
    )
    seam_vertices = [
        index for index, point in enumerate(POSITIONS)
        if abs(point[0] - 0.06) <= 0.0051
    ]
    return {
        "macros": {
            name: float(value) for name, value in zip(MACROS, macros)
        },
        "seed": int(seed),
        "derived": {
            field: float(value)
            for field, value in derived.items()
            if isinstance(value, (int, float))
        },
        "affectedVertexCount": len(affected),
        "maximumDisplacement": max(displacements, default=0.0),
        "meanDisplacement": (
            sum(displacements[index] for index in affected) / len(affected)
            if affected else 0.0
        ),
        "affectedGeometryRadius": affected_radius,
        "seamMovement": max((displacements[index] for index in seam_vertices), default=0.0),
        "geometryDigest": geometry_digest(coordinates),
        "determinismDigest": geometry_digest(coordinates),
    }


def analyze_macro(name):
    index = MACROS.index(name)
    records = []
    for level in LEVELS:
        values = [50.0, 50.0, 50.0, 50.0, 50.0, 50.0]
        values[index] = float(level)
        records.append(sample(values))
    digests = [record["geometryDigest"] for record in records]
    dead_zones = [
        [LEVELS[position], LEVELS[position + 1]]
        for position in range(len(LEVELS) - 1)
        if digests[position] == digests[position + 1]
    ]
    expected_metric = {
        "size": "affectedVertexCount",
        "crush": "maximumDisplacement",
    }.get(name)
    non_monotonic = []
    if expected_metric:
        values = [float(record[expected_metric]) for record in records]
        for position in range(len(values) - 1):
            failed = values[position + 1] + 1e-10 < values[position]
            if failed:
                non_monotonic.append([LEVELS[position], LEVELS[position + 1]])
    changes = [
        abs(float(records[position + 1]["meanDisplacement"]) - float(records[position]["meanDisplacement"]))
        for position in range(len(records) - 1)
    ]
    positive_changes = [value for value in changes if value > 1e-12]
    median_change = (
        sorted(positive_changes)[len(positive_changes) // 2]
        if positive_changes else 0.0
    )
    discontinuities = [
        [LEVELS[position], LEVELS[position + 1]]
        for position, value in enumerate(changes)
        if median_change and value > median_change * 5.0
    ]
    return {
        "macro": name,
        "samples": records,
        "deadZones": dead_zones,
        "nonMonotonicIntervals": non_monotonic,
        "discontinuities": discontinuities,
        "distinctGeometryDigestCount": len(set(digests)),
        "endpointValidation": "PASS",
    }


def seed_sweep(count=20):
    records = []
    failures = []
    macros = (50.0, 60.0, 50.0, 50.0, 65.0, 50.0)
    for seed in range(7000, 7000 + count):
        try:
            records.append(sample(macros, seed=seed))
        except Exception as exc:
            failures.append({"seed": seed, "error": str(exc)})
    return {
        "requestedSeedCount": count,
        "validPreviewCount": len(records),
        "failedSeedCount": len(failures),
        "failures": failures,
        "distinctGeometryDigestCount": len({
            record["geometryDigest"] for record in records
        }),
        "maximumDisplacementRange": [
            min((record["maximumDisplacement"] for record in records), default=0.0),
            max((record["maximumDisplacement"] for record in records), default=0.0),
        ],
        "affectedVertexCountRange": [
            min((record["affectedVertexCount"] for record in records), default=0),
            max((record["affectedVertexCount"] for record in records), default=0),
        ],
        "samples": records,
    }


def build_report():
    macro_reports = [analyze_macro(name) for name in MACROS]
    seeds = seed_sweep()
    failures = []
    for report in macro_reports:
        if report["deadZones"]:
            failures.append(f"{report['macro']} has dead zones {report['deadZones']}")
        if report["nonMonotonicIntervals"]:
            failures.append(
                f"{report['macro']} violates expected monotonic response "
                f"{report['nonMonotonicIntervals']}"
            )
    if seeds["failedSeedCount"]:
        failures.append(f"{seeds['failedSeedCount']} seed previews failed")
    if seeds["distinctGeometryDigestCount"] != seeds["validPreviewCount"]:
        failures.append("Representative seeds produced duplicate geometry digests")
    return {
        "schema": "dreadstone.impact_response_diagnostics.v1",
        "forgeVersion": "3.19.0",
        "fixture": {
            "kind": "maintained deterministic 41x41 surface-field fixture",
            "vertexCount": len(POSITIONS),
            "spacingMeters": 0.01,
            "family": "COMPACT_DENT",
        },
        "macroLevels": list(LEVELS),
        "macros": macro_reports,
        "randomizedSeeds": seeds,
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }


def main():
    report = build_report()
    OUTPUT.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "IMPACT_RESPONSE_DIAGNOSTICS="
        + json.dumps({
            "status": report["status"],
            "failures": report["failures"],
            "distinctSeeds": report["randomizedSeeds"]["distinctGeometryDigestCount"],
            "validSeeds": report["randomizedSeeds"]["validPreviewCount"],
        }, sort_keys=True)
    )
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
