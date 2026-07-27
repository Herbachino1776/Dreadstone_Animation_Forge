#!/usr/bin/env python3
"""Generate the machine-readable Damage Authoring parameter audit."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"
OUTPUT = ROOT / "docs" / "DAMAGE_PARAMETER_AUDIT_v3.18.0.json"


def load_schema():
    path = PACKAGE / "parameter_schema.py"
    module_spec = importlib.util.spec_from_file_location("forge_parameter_audit_schema", path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("Could not load parameter_schema.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def literal(node, default=None):
    try:
        return ast.literal_eval(node)
    except (TypeError, ValueError):
        return default


def property_call(node):
    annotation = node.annotation if isinstance(node, ast.AnnAssign) else None
    return annotation if isinstance(annotation, ast.Call) else None


def keyword(call, name, default=None):
    for item in call.keywords:
        if item.arg == name:
            return literal(item.value, ast.unparse(item.value))
    return default


NON_NUMERIC_RECIPE_FIELDS = {
    "deformation_capture_mode": "placementMode",
    "deformation_influence_mode": "influenceMode",
    "deformation_distance_mode": "distanceMode",
    "deformation_stamp_family": "family",
    "deformation_stamp_name": "displayName",
    "deformation_seed_direction_mode": "directionMode",
    "deformation_seed_custom_direction": "directionLocal",
    "deformation_seed_center": "capture.centerLocal",
    "deformation_seed_surface_normal": "capture.normalLocal",
    "deformation_gore_enabled": "goreOverlayEnabled",
    "deformation_gore_preset": "gorePresetId",
    "deformation_gore_raised_enabled": "goreRaisedEnabled",
    "deformation_gore_texture_enabled": "goreTextureEnabled",
    "deformation_gore_inner_rim_enabled": "goreInnerRimEnabled",
    "deformation_gore_color_bias": "goreColorBias",
    "deformation_impact_control_mode": "impactControl.mode",
}


def main():
    schema = load_schema()
    init_source = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    ordinary_source = (PACKAGE / "ui" / "panels.py").read_text(encoding="utf-8")
    advanced_source = (PACKAGE / "deformation_authoring.py").read_text(encoding="utf-8")
    tree = ast.parse(init_source)
    settings_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DAFSettings"
    )
    records = []
    for node in settings_class.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        identifier = node.target.id
        if not identifier.startswith("deformation_"):
            continue
        call = property_call(node)
        if call is None:
            continue
        kind = ast.unparse(call.func)
        contract = schema.PARAMETERS.get(identifier)
        vector_contract = schema.VECTOR_PARAMETERS.get(identifier)
        if contract is not None:
            record = contract.as_dict()
        elif vector_contract is not None:
            record = dict(vector_contract)
            record["scaleSemantics"] = "linear RGB vector"
            record["presetValues"] = [
                list(preset["goreColorBias"])
                for preset in schema.GORE_PRESETS.values()
                if "goreColorBias" in preset
            ]
            record["relativeScale"] = ""
            record["integer"] = False
        else:
            default = keyword(call, "default")
            if "BoolProperty" in kind:
                hard_minimum, hard_maximum = False, True
                inclusive_minimum = inclusive_maximum = True
            else:
                hard_minimum = keyword(call, "min")
                hard_maximum = keyword(call, "max")
                inclusive_minimum = inclusive_maximum = (
                    hard_minimum is not None or hard_maximum is not None
                )
            record = {
                "identifier": identifier,
                "label": keyword(call, "name", identifier.replace("_", " ").title()),
                "default": default,
                "hardMinimum": hard_minimum,
                "hardMaximum": hard_maximum,
                "softMinimum": keyword(call, "soft_min", hard_minimum),
                "softMaximum": keyword(call, "soft_max", hard_maximum),
                "precision": keyword(call, "precision"),
                "step": keyword(call, "step"),
                "unit": keyword(call, "unit", "NONE"),
                "scaleSemantics": "state/identity" if hard_minimum is None else "linear",
                "minimumInclusive": inclusive_minimum,
                "maximumInclusive": inclusive_maximum,
                "responseCurve": "not applicable" if hard_minimum is None else "linear",
                "recipeField": NON_NUMERIC_RECIPE_FIELDS.get(identifier, ""),
                "normalizer": (
                    "parameter_schema.normalize_impact_control"
                    if identifier.startswith("deformation_impact_") else
                    "trauma_field.normalize_stamp / normalize_gore_overlay"
                    if identifier in NON_NUMERIC_RECIPE_FIELDS else ""
                ),
                "validator": (
                    "parameter_schema.normalize_impact_control"
                    if identifier.startswith("deformation_impact_") else
                    "trauma_field.validate_stamp_stack / validate_gore_overlay"
                    if identifier in NON_NUMERIC_RECIPE_FIELDS else ""
                ),
                "presetValues": [],
                "exportField": NON_NUMERIC_RECIPE_FIELDS.get(identifier, ""),
                "relativeScale": "",
                "measurableOutput": not any(
                    token in identifier for token in ("status", "message", "generation", "elapsed")
                ),
                "integer": "IntProperty" in kind,
            }
        record.update({
            "propertyKind": kind,
            "updateCallback": keyword(call, "update", ""),
            "ordinaryInterface": identifier in ordinary_source,
            "advancedInterface": identifier in advanced_source or identifier in ordinary_source,
            "sourceLine": int(node.lineno),
        })
        records.append(record)

    prefix_requirements = (
        "deformation_seed_", "deformation_stamp_", "deformation_feather_",
        "deformation_max_", "deformation_gore_",
    )
    discovered = {record["identifier"] for record in records}
    for prefix in prefix_requirements:
        declared = {
            node.target.id
            for node in settings_class.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id.startswith(prefix)
        }
        missing = sorted(declared - discovered)
        if missing:
            raise RuntimeError(f"Audit omitted {prefix} properties: {missing}")

    payload = {
        "schema": "dreadstone.damage_parameter_audit.v1",
        "forgeVersion": "3.18.0",
        "supportedBlenderRuntime": "5.1.2",
        "authority": "dreadstone_animation_forge/parameter_schema.py",
        "propertyCount": len(records),
        "properties": sorted(records, key=lambda record: record["identifier"]),
        "traumaFieldConstants": {
            "stampLibrarySchema": "dreadstone.trauma_stamp_library.v1",
            "stampLibraryFormatVersion": 4,
            "supportedStampLibraryFormats": [1, 2, 3, 4],
            "goreRecipeVersion": 3,
            "goreMaximumTrianglesPerDeformation": 12000,
            "goreMaximumTrianglesPerAsset": 48000,
            "goreMinimumSurfaceOffset": 0.00015,
            "goreMaximumSurfaceOffset": 0.012,
            "normalizers": [
                "normalize_stamp", "normalize_gore_overlay",
                "normalize_stamp_library", "normalize_impact_control",
            ],
            "validators": [
                "validate_stamp_stack", "validate_gore_overlay",
                "validate_recipe_value", "validate_vector",
            ],
        },
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"WROTE {OUTPUT.relative_to(ROOT)} ({len(records)} properties)")


if __name__ == "__main__":
    main()
