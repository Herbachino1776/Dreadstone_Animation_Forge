"""Blender-free performance-report contracts and relative gate evaluation."""

from __future__ import annotations


SCHEMA = "dreadstone.forge_performance_acceptance.v1"
STABLE_RESOURCE_KEYS = (
    "objects",
    "meshes",
    "materials",
    "actions",
    "shapeKeys",
    "collections",
    "attributes",
    "temporaryPreviewObjects",
    "forgeLoadHandlers",
    "forgePreviewTimer",
)


def numeric_growth(before, after, keys=STABLE_RESOURCE_KEYS):
    """Return deterministic integer growth for inspectable resource counters."""

    return {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in keys}


def stable_growth(growth, allowed=None):
    """Check that temporary/runtime resources do not grow across warm cycles."""

    allowed = dict(allowed or {})
    failures = {
        key: int(value)
        for key, value in growth.items()
        if int(value) > int(allowed.get(key, 0))
    }
    return {"pass": not failures, "growth": dict(growth), "failures": failures}


def relative_preview_gate(baseline_ms, healed_ms, minimum_improvement=0.50):
    baseline_ms = float(baseline_ms)
    healed_ms = float(healed_ms)
    if baseline_ms <= 0.0 or healed_ms < 0.0:
        raise ValueError("preview medians must be non-negative and baseline must be positive")
    improvement = (baseline_ms - healed_ms) / baseline_ms
    return {
        "baselineMs": baseline_ms,
        "healedMs": healed_ms,
        "improvementFraction": improvement,
        "minimumImprovementFraction": float(minimum_improvement),
        "pass": improvement >= float(minimum_improvement),
    }


def no_regression_gate(baseline_ms, healed_ms, maximum_regression=0.10):
    baseline_ms = float(baseline_ms)
    healed_ms = float(healed_ms)
    if baseline_ms <= 0.0 or healed_ms < 0.0:
        raise ValueError("operation medians must be non-negative and baseline must be positive")
    regression = (healed_ms - baseline_ms) / baseline_ms
    return {
        "baselineMs": baseline_ms,
        "healedMs": healed_ms,
        "regressionFraction": regression,
        "maximumRegressionFraction": float(maximum_regression),
        "pass": regression <= float(maximum_regression),
    }


def validate_report(report):
    errors = []
    if not isinstance(report, dict):
        return ["report must be an object"]
    if report.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    for key in ("blenderVersion", "addonVersion", "commit", "sourceAsset", "resourceCounts", "operations", "failures"):
        if key not in report:
            errors.append(f"missing {key}")
    if not isinstance(report.get("operations", []), list):
        errors.append("operations must be an array")
    return errors
