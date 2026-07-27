"""Authoritative Damage Authoring parameter and Impact Pedal contracts.

This module is deliberately Blender-free.  RNA declarations, recipe
normalizers, validators, presets, diagnostics, and tests all consume the same
inclusive numeric contracts from here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
from collections.abc import Mapping


IMPACT_CONTROL_SCHEMA = "dreadstone.impact_control.v1"
IMPACT_CONTROL_VERSION = 1
MACRO_IDENTIFIERS = (
    "deformation_impact_size",
    "deformation_impact_crush",
    "deformation_impact_profile",
    "deformation_impact_edge_safety",
    "deformation_impact_chaos",
)
MACRO_LABELS = ("SIZE", "CRUSH", "PROFILE", "EDGE SAFETY", "CHAOS")
DEFAULT_IMPACT_SEED = 1776
MAX_SEED = 2147483647


def _rna_float32(value):
    """Return Blender RNA's single-precision representation of a float."""

    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _inclusive_storage_limits(minimum, maximum):
    """Include the float32 values Blender stores for legal UI endpoints."""

    return (
        min(float(minimum), _rna_float32(minimum)),
        max(float(maximum), _rna_float32(maximum)),
    )


class ParameterSpec:
    """One inclusive artist/recipe numeric contract."""

    __slots__ = (
        "identifier", "label", "default", "hard_min", "hard_max", "soft_min",
        "soft_max", "precision", "step", "unit", "scale_semantics",
        "inclusive_min", "inclusive_max", "response_curve", "recipe_field",
        "normalizer", "validator", "preset_values", "export_field",
        "relative_scale", "measurable_output", "integer",
    )

    def __init__(
        self,
        identifier,
        label,
        default,
        hard_min,
        hard_max,
        *,
        soft_min=None,
        soft_max=None,
        precision=3,
        step=1,
        unit="NONE",
        scale_semantics="physical",
        inclusive_min=True,
        inclusive_max=True,
        response_curve="linear",
        recipe_field="",
        normalizer="parameter_schema.normalize",
        validator="parameter_schema.validate",
        preset_values=(),
        export_field="",
        relative_scale="",
        measurable_output=True,
        integer=False,
    ):
        self.identifier = str(identifier)
        self.label = str(label)
        self.default = default
        self.hard_min = hard_min
        self.hard_max = hard_max
        self.soft_min = hard_min if soft_min is None else soft_min
        self.soft_max = hard_max if soft_max is None else soft_max
        self.precision = int(precision)
        self.step = int(step)
        self.unit = str(unit)
        self.scale_semantics = str(scale_semantics)
        self.inclusive_min = bool(inclusive_min)
        self.inclusive_max = bool(inclusive_max)
        self.response_curve = str(response_curve)
        self.recipe_field = str(recipe_field)
        self.normalizer = str(normalizer)
        self.validator = str(validator)
        self.preset_values = tuple(preset_values)
        self.export_field = str(export_field or recipe_field)
        self.relative_scale = str(relative_scale)
        self.measurable_output = bool(measurable_output)
        self.integer = bool(integer)
        if not math.isfinite(float(hard_min)) or not math.isfinite(float(hard_max)):
            raise ValueError(f"{identifier} hard limits must be finite")
        if float(hard_min) > float(hard_max):
            raise ValueError(f"{identifier} hard minimum exceeds its maximum")
        if not float(hard_min) <= float(default) <= float(hard_max):
            raise ValueError(f"{identifier} default is outside its hard range")
        if not float(hard_min) <= float(self.soft_min) <= float(self.soft_max) <= float(hard_max):
            raise ValueError(f"{identifier} soft range is outside its hard range")

    def validate(self, value):
        try:
            number = int(value) if self.integer else float(value)
        except (TypeError, ValueError, OverflowError):
            return [f"{self.label} must be a finite number."]
        if not math.isfinite(float(number)):
            return [f"{self.label} must be a finite number."]
        storage_min, storage_max = _inclusive_storage_limits(self.hard_min, self.hard_max)
        effective_min = storage_min if self.inclusive_min and not self.integer else self.hard_min
        effective_max = storage_max if self.inclusive_max and not self.integer else self.hard_max
        below = number < effective_min if self.inclusive_min else number <= self.hard_min
        above = number > effective_max if self.inclusive_max else number >= self.hard_max
        if below or above:
            left = "[" if self.inclusive_min else "("
            right = "]" if self.inclusive_max else ")"
            return [f"{self.label} must be in {left}{self.hard_min}, {self.hard_max}{right}."]
        return []

    def to_normalized(self, value):
        errors = self.validate(value)
        if errors:
            raise ValueError(errors[0])
        minimum = float(self.hard_min)
        maximum = float(self.hard_max)
        if maximum == minimum:
            return 0.0
        number = float(value)
        stored_minimum = _rna_float32(minimum)
        stored_maximum = _rna_float32(maximum)
        if self.inclusive_min and min(minimum, stored_minimum) <= number <= max(minimum, stored_minimum):
            number = minimum
        if self.inclusive_max and min(maximum, stored_maximum) <= number <= max(maximum, stored_maximum):
            number = maximum
        if self.response_curve == "log":
            if minimum <= 0.0:
                raise ValueError(f"{self.identifier} log response requires a positive minimum")
            return math.log(number / minimum) / math.log(maximum / minimum)
        linear = (number - minimum) / (maximum - minimum)
        if self.response_curve == "square":
            return math.sqrt(max(0.0, linear))
        if self.response_curve == "cubic":
            return max(0.0, linear) ** (1.0 / 3.0)
        return linear

    def from_normalized(self, normalized):
        value = float(normalized)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{self.label} normalized value must be in [0, 1].")
        minimum = float(self.hard_min)
        maximum = float(self.hard_max)
        if value == 0.0:
            physical = minimum
        elif value == 1.0:
            physical = maximum
        elif self.response_curve == "log":
            physical = minimum * ((maximum / minimum) ** value)
        elif self.response_curve == "square":
            physical = minimum + (maximum - minimum) * value**2
        elif self.response_curve == "cubic":
            physical = minimum + (maximum - minimum) * value**3
        else:
            physical = minimum + (maximum - minimum) * value
        if self.integer:
            return int(round(physical))
        return physical

    def as_dict(self):
        return {
            "identifier": self.identifier,
            "label": self.label,
            "default": self.default,
            "hardMinimum": self.hard_min,
            "hardMaximum": self.hard_max,
            "softMinimum": self.soft_min,
            "softMaximum": self.soft_max,
            "precision": self.precision,
            "step": self.step,
            "unit": self.unit,
            "scaleSemantics": self.scale_semantics,
            "minimumInclusive": self.inclusive_min,
            "maximumInclusive": self.inclusive_max,
            "rnaFloat32EndpointTolerance": not self.integer,
            "responseCurve": self.response_curve,
            "recipeField": self.recipe_field,
            "normalizer": self.normalizer,
            "validator": self.validator,
            "presetValues": list(self.preset_values),
            "exportField": self.export_field,
            "relativeScale": self.relative_scale,
            "measurableOutput": self.measurable_output,
            "integer": self.integer,
        }


def _spec(identifier, label, default, minimum, maximum, **kwargs):
    return ParameterSpec(identifier, label, default, minimum, maximum, **kwargs)


PARAMETERS = {
    "deformation_feather_distance": _spec(
        "deformation_feather_distance", "Feather Distance", 0.020, 0.0, 2.0,
        soft_max=0.08, precision=4, step=1, unit="LENGTH", response_curve="square",
        recipe_field="featherDistance", relative_scale="captured patch radius",
    ),
    "deformation_stamp_strength": _spec(
        "deformation_stamp_strength", "Stamp Strength", 1.0, 0.0, 2.0,
        soft_max=1.5, precision=3, step=1, recipe_field="strength",
    ),
    "deformation_seed_radius": _spec(
        "deformation_seed_radius", "Seed Radius", 0.075, 0.005, 2.0,
        soft_min=0.015, soft_max=0.15, precision=4, step=1, unit="LENGTH",
        response_curve="square", recipe_field="radius",
        relative_scale="captured region or character scale",
    ),
    "deformation_seed_depth": _spec(
        "deformation_seed_depth", "Seed Depth", 0.025, 0.0, 0.50,
        soft_max=0.06, precision=4, step=1, unit="LENGTH",
        response_curve="square", recipe_field="depth",
    ),
    "deformation_seed_falloff": _spec(
        "deformation_seed_falloff", "Falloff Exponent", 2.2, 0.35, 6.0,
        soft_min=0.6, soft_max=4.0, precision=3, step=1, response_curve="log",
        recipe_field="falloff",
    ),
    "deformation_seed_seam_protection": _spec(
        "deformation_seed_seam_protection", "Seam Protection", 0.025, 0.0, 0.10,
        soft_max=0.06, precision=4, step=1, unit="LENGTH",
        response_curve="square", recipe_field="seamProtection",
        relative_scale="capture radius and registered seam distance",
    ),
    "deformation_max_vertex_displacement": _spec(
        "deformation_max_vertex_displacement", "Maximum Displacement", 0.065, 0.001, 2.0,
        soft_min=0.004, soft_max=0.09, precision=4, step=1, unit="LENGTH",
        response_curve="square", recipe_field="maximumDisplacement",
    ),
    "deformation_maximum_influence": _spec(
        "deformation_maximum_influence", "Maximum Runtime Weight", 1.0, 0.05, 2.0,
        soft_min=0.25, soft_max=1.25, precision=3, step=1,
        recipe_field="maximumInfluence", measurable_output=False,
    ),
    "deformation_impact_size": _spec(
        "deformation_impact_size", "SIZE", 50.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="size", export_field="impactControl.macros.size",
    ),
    "deformation_impact_crush": _spec(
        "deformation_impact_crush", "CRUSH", 50.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="crush", export_field="impactControl.macros.crush",
    ),
    "deformation_impact_profile": _spec(
        "deformation_impact_profile", "PROFILE", 50.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="profile", export_field="impactControl.macros.profile",
    ),
    "deformation_impact_edge_safety": _spec(
        "deformation_impact_edge_safety", "EDGE SAFETY", 50.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="edgeSafety", export_field="impactControl.macros.edgeSafety",
    ),
    "deformation_impact_chaos": _spec(
        "deformation_impact_chaos", "CHAOS", 35.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="chaos", export_field="impactControl.macros.chaos",
    ),
    "deformation_impact_seed": _spec(
        "deformation_impact_seed", "Master Impact Seed", DEFAULT_IMPACT_SEED, 0, MAX_SEED,
        precision=0, step=1, scale_semantics="deterministic integer identity",
        recipe_field="impactSeed", export_field="impactControl.seed", integer=True,
    ),
    "deformation_impact_gore_patch_scale": _spec(
        "deformation_impact_gore_patch_scale", "Gore Patch Scale", 0.010, 0.001, 0.10,
        soft_min=0.004, soft_max=0.04, precision=4, step=1, unit="LENGTH",
        response_curve="square", recipe_field="gorePatchScale",
        relative_scale="impact radius",
    ),
    "recipe_impact_chaos": _spec(
        "recipe_impact_chaos", "Impact Chaos", 0.0, 0.0, 1.0,
        precision=6, scale_semantics="normalized 0-1", recipe_field="impactChaos",
    ),
    "recipe_impact_seed": _spec(
        "recipe_impact_seed", "Impact Seed", DEFAULT_IMPACT_SEED, 0, MAX_SEED,
        precision=0, step=1, scale_semantics="deterministic integer identity",
        recipe_field="impactSeed", integer=True,
    ),
    "recipe_impact_profile": _spec(
        "recipe_impact_profile", "Impact Profile", 0.5, 0.0, 1.0,
        precision=6, scale_semantics="normalized 0-1", recipe_field="impactProfile",
    ),
    "recipe_profile_center_rim_balance": _spec(
        "recipe_profile_center_rim_balance", "Profile Center/Rim Balance", 0.5, 0.0, 1.0,
        precision=6, scale_semantics="normalized 0-1",
        recipe_field="profileCenterRimBalance",
    ),
}


def _unit_interval(identifier, label, default, recipe_field, *, preset_values=()):
    PARAMETERS[identifier] = _spec(
        identifier, label, default, 0.0, 1.0, precision=3, step=1,
        scale_semantics="normalized 0-1", recipe_field=recipe_field,
        preset_values=preset_values,
    )


for _identifier, _label, _default, _field in (
    ("deformation_gore_coverage", "Coverage", 0.72, "goreCoverage"),
    ("deformation_gore_scatter", "Scatter / Breakup", 0.48, "goreScatter"),
    ("deformation_gore_edge_feather", "Edge Feather", 0.70, "goreEdgeFeather"),
    ("deformation_gore_wetness", "Wetness / Gloss", 0.92, "goreWetness"),
    ("deformation_gore_darkness", "Darkness", 0.38, "goreDarkness"),
    ("deformation_gore_clot_coverage", "Clot Coverage", 0.82, "goreClotCoverage"),
    ("deformation_gore_core_density", "Core Density", 0.94, "goreCoreDensity"),
    ("deformation_gore_thickness_variation", "Thickness Variation", 0.88, "goreThicknessVariation"),
    ("deformation_gore_island_breakup", "Island Breakup", 0.86, "goreIslandBreakup"),
    ("deformation_gore_peripheral_fragments", "Peripheral Fragments", 0.58, "gorePeripheralFragments"),
    ("deformation_gore_geometry_density", "Geometry Density", 0.72, "goreGeometryDensity"),
    ("deformation_gore_wetness_variation", "Wetness Variation", 0.84, "goreWetnessVariation"),
    ("deformation_gore_dark_clot_bias", "Dark-Clot Bias", 0.72, "goreDarkClotBias"),
    ("deformation_gore_rough_edge_bias", "Rough-Edge Bias", 0.56, "goreRoughEdgeBias"),
    ("deformation_gore_color_intensity", "Color Intensity", 1.0, "goreColorIntensity"),
    ("deformation_gore_organic_irregularity", "Organic Irregularity", 0.78, "goreOrganicIrregularity"),
    ("deformation_gore_surface_roundness", "Surface Roundness", 0.82, "goreSurfaceRoundness"),
    ("deformation_gore_fiber_texture_strength", "Muscle Fiber Contribution", 0.82, "goreFiberTextureStrength"),
    ("deformation_gore_base_color_strength", "Gore Color Contribution", 0.30, "goreBaseColorStrength"),
    ("deformation_gore_inner_rim_strength", "Barrier Compromise", 0.88, "goreInnerRimStrength"),
):
    _unit_interval(_identifier, _label, _default, _field)


PARAMETERS.update({
    "deformation_gore_clot_thickness": _spec(
        "deformation_gore_clot_thickness", "Clot Thickness", 0.0048, 0.0001, 0.05,
        soft_min=0.0005, soft_max=0.012, precision=5, step=1, unit="LENGTH",
        response_curve="log", recipe_field="goreClotThickness",
    ),
    "deformation_gore_surface_offset": _spec(
        "deformation_gore_surface_offset", "Surface Offset", 0.00065, 0.00015, 0.012,
        soft_max=0.003, precision=6, step=1, unit="LENGTH",
        response_curve="log", recipe_field="goreSurfaceOffset",
    ),
    "deformation_gore_inner_rim_width": _spec(
        "deformation_gore_inner_rim_width", "Inner Reddening Width", 0.0032, 0.0001, 0.03,
        soft_min=0.0005, soft_max=0.01, precision=5, step=1, unit="LENGTH",
        response_curve="log", recipe_field="goreInnerRimWidth",
    ),
    "deformation_gore_maximum_triangles": _spec(
        "deformation_gore_maximum_triangles", "Maximum Triangles", 12000, 128, 100000,
        soft_min=1000, soft_max=24000, precision=0, step=100,
        scale_semantics="integer triangle budget", recipe_field="goreMaximumTriangles",
        integer=True, measurable_output=False,
    ),
    "deformation_gore_mask_seed": _spec(
        "deformation_gore_mask_seed", "Master Gore Seed", DEFAULT_IMPACT_SEED, 0, MAX_SEED,
        precision=0, step=1, scale_semantics="deterministic integer identity",
        recipe_field="goreMaskSeed", integer=True,
    ),
})


_RECIPE_PARAMETERS = {
    spec.recipe_field: spec
    for spec in PARAMETERS.values()
    if spec.recipe_field and "." not in spec.export_field
}

VECTOR_PARAMETERS = {
    "deformation_gore_color_bias": {
        "identifier": "deformation_gore_color_bias",
        "label": "Color Bias",
        "default": (0.34, 0.012, 0.008),
        "size": 3,
        "hardMinimum": 0.0,
        "hardMaximum": 1.0,
        "softMinimum": 0.0,
        "softMaximum": 1.0,
        "precision": 4,
        "step": 1,
        "unit": "COLOR",
        "minimumInclusive": True,
        "maximumInclusive": True,
        "recipeField": "goreColorBias",
        "normalizer": "parameter_schema.normalize_vector",
        "validator": "parameter_schema.validate_vector",
        "exportField": "goreColorBias",
        "measurableOutput": True,
    },
}


RAISED_GORE_DEFAULTS = {
    "goreOverlayMode": "SURFACE_STAIN",
    "goreIntensityClass": "LIGHT",
    "goreRaisedEnabled": False,
    "goreClotCoverage": 0.0,
    "goreCoreDensity": 0.0,
    "goreClotThickness": 0.0015,
    "goreThicknessVariation": 0.0,
    "goreIslandBreakup": 0.0,
    "gorePeripheralFragments": 0.0,
    "goreSurfaceOffset": 0.00035,
    "goreGeometryDensity": 0.35,
    "goreWetnessVariation": 0.0,
    "goreDarkClotBias": 0.0,
    "goreRoughEdgeBias": 0.0,
    "goreColorIntensity": 1.0,
    "goreOrganicIrregularity": 0.0,
    "goreSurfaceRoundness": 0.0,
    "goreTextureEnabled": False,
    "goreFiberTextureStrength": 0.0,
    "goreBaseColorStrength": 1.0,
    "goreInnerRimEnabled": False,
    "goreInnerRimWidth": 0.0025,
    "goreInnerRimStrength": 0.0,
    "goreMaximumTriangles": 12000,
    "goreDefaultVisible": False,
    "goreActivationWeight": 0.01,
    "goreUserCustomized": False,
}


GORE_PRESETS = {
    "Gore_Ooze_Wet": {
        "goreCoverage": 0.72, "goreScatter": 0.48, "goreEdgeFeather": 0.70,
        "goreWetness": 0.92, "goreDarkness": 0.38,
        "goreColorBias": (0.34, 0.012, 0.008), "gorePatchScale": 0.018,
    },
    "Gore_Clot_Dark": {
        "goreCoverage": 0.64, "goreScatter": 0.62, "goreEdgeFeather": 0.54,
        "goreWetness": 0.58, "goreDarkness": 0.72,
        "goreColorBias": (0.24, 0.008, 0.006), "gorePatchScale": 0.012,
    },
    "Gore_Smear_Heavy": {
        "goreCoverage": 0.86, "goreScatter": 0.30, "goreEdgeFeather": 0.82,
        "goreWetness": 0.80, "goreDarkness": 0.48,
        "goreColorBias": (0.38, 0.014, 0.009), "gorePatchScale": 0.028,
    },
    "Gore_Speckled_Impact": {
        "goreCoverage": 0.46, "goreScatter": 0.90, "goreEdgeFeather": 0.62,
        "goreWetness": 0.74, "goreDarkness": 0.42,
        "goreColorBias": (0.42, 0.016, 0.010), "gorePatchScale": 0.008,
    },
    "Gore_Crush_Bloodied": {
        "goreCoverage": 0.78, "goreScatter": 0.68, "goreEdgeFeather": 0.66,
        "goreWetness": 0.86, "goreDarkness": 0.56,
        "goreColorBias": (0.30, 0.010, 0.007), "gorePatchScale": 0.015,
    },
    "Gore_Crush_Heavy_Clotted": {
        "goreCoverage": 0.76, "goreScatter": 0.92, "goreEdgeFeather": 0.42,
        "goreWetness": 0.82, "goreDarkness": 0.68,
        "goreColorBias": (0.31, 0.006, 0.004), "gorePatchScale": 0.010,
        "goreOverlayMode": "STAIN_AND_RAISED", "goreIntensityClass": "HIGH",
        "goreRaisedEnabled": True, "goreClotCoverage": 0.82,
        "goreCoreDensity": 0.94, "goreClotThickness": 0.0048,
        "goreThicknessVariation": 0.88, "goreIslandBreakup": 0.86,
        "gorePeripheralFragments": 0.58, "goreSurfaceOffset": 0.00065,
        "goreGeometryDensity": 0.72, "goreWetnessVariation": 0.84,
        "goreDarkClotBias": 0.72, "goreRoughEdgeBias": 0.56,
        "goreColorIntensity": 1.0, "goreOrganicIrregularity": 0.78,
        "goreSurfaceRoundness": 0.82, "goreTextureEnabled": True,
        "goreFiberTextureStrength": 0.82, "goreBaseColorStrength": 0.30,
        "goreInnerRimEnabled": True, "goreInnerRimWidth": 0.0032,
        "goreInnerRimStrength": 0.88, "goreMaximumTriangles": 12000,
        "goreDefaultVisible": False, "goreActivationWeight": 0.01,
        "goreUserCustomized": False,
    },
}

_GORE_PRESET_FIELDS = {
    field
    for preset in GORE_PRESETS.values()
    for field in preset
}
for _field in _GORE_PRESET_FIELDS:
    _contract = _RECIPE_PARAMETERS.get(_field)
    if _contract is not None:
        _contract.preset_values = tuple(
            preset[_field]
            for preset in GORE_PRESETS.values()
            if _field in preset and not isinstance(preset[_field], (tuple, list))
        )
for _identifier, _values in {
    "deformation_impact_size": (34.0, 50.0, 68.0),
    "deformation_impact_crush": (28.0, 50.0, 78.0),
    "deformation_impact_profile": (58.0, 45.0, 34.0),
    "deformation_impact_edge_safety": (66.0, 55.0, 46.0),
    "deformation_impact_chaos": (22.0, 35.0, 60.0),
}.items():
    PARAMETERS[_identifier].preset_values = _values


def spec(identifier):
    try:
        return PARAMETERS[str(identifier)]
    except KeyError:
        raise KeyError(f"Unknown Damage Authoring parameter {identifier!r}.") from None


def recipe_spec(field):
    return _RECIPE_PARAMETERS.get(str(field))


def blender_kwargs(identifier):
    contract = spec(identifier)
    result = {
        "name": contract.label,
        "default": contract.default,
        "min": contract.hard_min,
        "max": contract.hard_max,
        "soft_min": contract.soft_min,
        "soft_max": contract.soft_max,
        "step": contract.step,
    }
    if not contract.integer:
        result["precision"] = contract.precision
    if contract.unit != "NONE":
        result["unit"] = contract.unit
    return result


def blender_vector_kwargs(identifier):
    try:
        contract = VECTOR_PARAMETERS[str(identifier)]
    except KeyError:
        raise KeyError(f"Unknown Damage Authoring vector parameter {identifier!r}.") from None
    return {
        "name": contract["label"],
        "default": contract["default"],
        "size": contract["size"],
        "min": contract["hardMinimum"],
        "max": contract["hardMaximum"],
        "soft_min": contract["softMinimum"],
        "soft_max": contract["softMaximum"],
        "precision": contract["precision"],
        "step": contract["step"],
    }


def validate_vector(identifier, value):
    contract = VECTOR_PARAMETERS[str(identifier)]
    try:
        channels = tuple(float(channel) for channel in value)
    except (TypeError, ValueError):
        return [f"{contract['label']} must contain {contract['size']} finite channels."]
    if len(channels) != int(contract["size"]):
        return [f"{contract['label']} must contain {contract['size']} finite channels."]
    storage_min, storage_max = _inclusive_storage_limits(
        contract["hardMinimum"],
        contract["hardMaximum"],
    )
    if any(
        not math.isfinite(channel)
        or channel < storage_min
        or channel > storage_max
        for channel in channels
    ):
        return [
            f"{contract['label']} channels must be in "
            f"[{contract['hardMinimum']}, {contract['hardMaximum']}]."
        ]
    return []


def validate(identifier, value):
    return spec(identifier).validate(value)


def validate_recipe_value(field, value):
    contract = recipe_spec(field)
    return [] if contract is None else contract.validate(value)


def normalize(identifier, value):
    return spec(identifier).to_normalized(value)


def inverse(identifier, normalized_value):
    return spec(identifier).from_normalized(normalized_value)


def parameter_report():
    return {
        "schema": "dreadstone.damage_parameter_contract.v1",
        "impactControlSchema": IMPACT_CONTROL_SCHEMA,
        "parameters": [PARAMETERS[key].as_dict() for key in sorted(PARAMETERS)],
        "vectorParameters": [copy.deepcopy(VECTOR_PARAMETERS[key]) for key in sorted(VECTOR_PARAMETERS)],
    }


def _macro_values(macros):
    if isinstance(macros, Mapping):
        raw = (
            macros.get("size", macros.get(MACRO_IDENTIFIERS[0], 50.0)),
            macros.get("crush", macros.get(MACRO_IDENTIFIERS[1], 50.0)),
            macros.get("profile", macros.get(MACRO_IDENTIFIERS[2], 50.0)),
            macros.get("edgeSafety", macros.get(MACRO_IDENTIFIERS[3], 50.0)),
            macros.get("chaos", macros.get(MACRO_IDENTIFIERS[4], 35.0)),
        )
    else:
        raw = tuple(macros)
    if len(raw) != 5:
        raise ValueError("Impact Pedal requires exactly five macro values.")
    values = tuple(float(value) for value in raw)
    for identifier, value in zip(MACRO_IDENTIFIERS, values):
        errors = validate(identifier, value)
        if errors:
            raise ValueError(errors[0])
    return values


def normalize_impact_control(metadata):
    if not isinstance(metadata, Mapping):
        raise ValueError("Impact control metadata must be an object.")
    schema_name = str(metadata.get("schema", IMPACT_CONTROL_SCHEMA))
    version = int(metadata.get("version", IMPACT_CONTROL_VERSION))
    if schema_name != IMPACT_CONTROL_SCHEMA or version != IMPACT_CONTROL_VERSION:
        raise ValueError(f"Unsupported impact control metadata {schema_name!r} version {version}.")
    mode = str(metadata.get("mode", "MANUAL")).upper()
    if mode not in {"MACRO", "MANUAL"}:
        raise ValueError("Impact control mode must be MACRO or MANUAL.")
    size, crush, profile, edge_safety, chaos = _macro_values(metadata.get("macros", {}))
    seed = int(metadata.get("seed", DEFAULT_IMPACT_SEED))
    errors = validate("deformation_impact_seed", seed)
    if errors:
        raise ValueError(errors[0])
    normalized = {
        "schema": IMPACT_CONTROL_SCHEMA,
        "version": IMPACT_CONTROL_VERSION,
        "mode": mode,
        "recipeClass": "IMPACT_PEDAL" if mode == "MACRO" else "CUSTOM",
        "macros": {
            "size": size,
            "crush": crush,
            "profile": profile,
            "edgeSafety": edge_safety,
            "chaos": chaos,
        },
        "seed": seed,
    }
    normalized["identityDigest"] = impact_identity_digest(normalized)
    return normalized


def impact_identity_digest(metadata):
    if isinstance(metadata, Mapping) and "macros" in metadata:
        payload = {
            "schema": str(metadata.get("schema", IMPACT_CONTROL_SCHEMA)),
            "version": int(metadata.get("version", IMPACT_CONTROL_VERSION)),
            "mode": str(metadata.get("mode", "MACRO")).upper(),
            "macros": dict(metadata.get("macros", {})),
            "seed": int(metadata.get("seed", DEFAULT_IMPACT_SEED)),
        }
    else:
        size, crush, profile, edge_safety, chaos = _macro_values(metadata)
        payload = {
            "schema": IMPACT_CONTROL_SCHEMA,
            "version": IMPACT_CONTROL_VERSION,
            "mode": "MACRO",
            "macros": {
                "size": size, "crush": crush, "profile": profile,
                "edgeSafety": edge_safety, "chaos": chaos,
            },
            "seed": DEFAULT_IMPACT_SEED,
        }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_impact_parameters(macros, *, region_scale=0.075, family="COMPACT_DENT", seed=DEFAULT_IMPACT_SEED):
    """Map five normalized knobs to one bounded physical recipe.

    ``region_scale`` is the captured patch's estimated world-space radius.  It
    changes only the response scale; it never changes capture indices or the
    placement anchor.
    """

    size, crush, profile, edge_safety, chaos = _macro_values(macros)
    seed = int(seed)
    seed_errors = validate("deformation_impact_seed", seed)
    if seed_errors:
        raise ValueError(seed_errors[0])
    size_n, crush_n, profile_n, edge_n, chaos_n = (
        value / 100.0 for value in (size, crush, profile, edge_safety, chaos)
    )
    radius_spec = spec("deformation_seed_radius")
    capture_scale = float(region_scale)
    if not math.isfinite(capture_scale) or capture_scale <= 0.0:
        capture_scale = float(radius_spec.default)
    capture_scale = max(float(radius_spec.hard_min), min(0.30, capture_scale))
    radius = capture_scale * (0.48 + 1.32 * size_n**1.35)
    radius = max(float(radius_spec.hard_min), min(0.30, radius))

    family_factor = {
        "COMPACT_DENT": 1.0,
        "BROAD_CAVE": 0.92,
        "FLAT_COMPRESSION": 0.82,
        "DIRECTIONAL_SHEAR": 0.88,
        "RAISED_IMPACT_RIM": 0.72,
        "RIDGE_COLLAPSE": 1.0,
    }.get(str(family), 1.0)
    depth = 0.12 * family_factor * crush_n**2.05
    strength = 0.35 + 1.55 * crush_n**0.78
    if crush_n == 0.0:
        depth = 0.0
        strength = 0.0
    maximum_displacement = max(0.001, depth * strength * 1.08 + 0.001)
    maximum_displacement = min(0.15, maximum_displacement)
    falloff = inverse("deformation_seed_falloff", profile_n)
    base_feather = radius * (0.18 + 0.42 * size_n)
    feather = base_feather * (1.0 - 0.30 * edge_n)
    feather = max(0.0, min(0.30, feather))
    seam_protection = radius * (0.04 * edge_n + 0.70 * edge_n**1.55)
    seam_protection = max(0.0, min(0.10, seam_protection))
    gore_patch_scale = max(0.001, min(0.10, radius * (0.12 + 0.10 * size_n)))
    gore_coverage = min(1.0, 0.20 + 0.62 * crush_n + 0.10 * size_n)
    gore_scatter = min(1.0, 0.12 + 0.82 * chaos_n)
    gore_breakup = min(1.0, 0.08 + 0.88 * chaos_n)
    gore_irregularity = min(1.0, 0.06 + 0.90 * chaos_n)

    result = {
        "radius": radius,
        "depth": depth,
        "falloff": falloff,
        "featherDistance": feather,
        "seamProtection": seam_protection,
        "strength": strength,
        "maximumDisplacement": maximum_displacement,
        "gorePatchScale": gore_patch_scale,
        "goreCoverage": gore_coverage,
        "goreScatter": gore_scatter,
        "goreIslandBreakup": gore_breakup,
        "goreOrganicIrregularity": gore_irregularity,
        "impactSeed": seed,
        "impactChaos": chaos_n,
        "impactProfile": profile_n,
        "profileCenterRimBalance": profile_n,
    }
    field_specs = (
        "radius", "depth", "falloff", "featherDistance", "seamProtection",
        "strength", "maximumDisplacement", "gorePatchScale", "goreCoverage",
        "goreScatter", "goreIslandBreakup", "goreOrganicIrregularity",
        "impactSeed",
    )
    errors = []
    for field in field_specs:
        errors.extend(validate_recipe_value(field, result[field]))
    if errors:
        raise ValueError("; ".join(errors))
    return result


def fit_macros_to_parameters(values, *, region_scale=0.075, family="COMPACT_DENT"):
    """Estimate the nearest macro state without mutating the manual recipe."""

    capture_scale = max(0.005, min(0.30, float(region_scale or 0.075)))
    radius = float(values.get("radius", 0.075))
    size_ratio = max(0.0, (radius / capture_scale - 0.48) / 1.32)
    size = 100.0 * min(1.0, size_ratio ** (1.0 / 1.35))
    family_factor = {
        "COMPACT_DENT": 1.0, "BROAD_CAVE": 0.92, "FLAT_COMPRESSION": 0.82,
        "DIRECTIONAL_SHEAR": 0.88, "RAISED_IMPACT_RIM": 0.72,
        "RIDGE_COLLAPSE": 1.0,
    }.get(str(family), 1.0)
    depth = max(0.0, float(values.get("depth", 0.025)))
    crush = 100.0 * min(1.0, (depth / max(1e-12, 0.12 * family_factor)) ** (1.0 / 2.05))
    profile = 100.0 * spec("deformation_seed_falloff").to_normalized(
        max(0.35, min(6.0, float(values.get("falloff", 2.2))))
    )
    seam = max(0.0, float(values.get("seamProtection", 0.025)))
    target = seam / max(1e-12, radius)
    edge = min(range(101), key=lambda candidate: abs(
        0.04 * (candidate / 100.0) + 0.70 * (candidate / 100.0) ** 1.55 - target
    ))
    chaos = 100.0 * max(0.0, min(1.0, float(values.get("impactChaos", 0.0))))
    return {
        "size": round(size, 3),
        "crush": round(crush, 3),
        "profile": round(profile, 3),
        "edgeSafety": float(edge),
        "chaos": round(chaos, 3),
    }


def gore_presets():
    return copy.deepcopy(GORE_PRESETS)


def raised_gore_defaults():
    return copy.deepcopy(RAISED_GORE_DEFAULTS)
