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
GORE_CONTROL_SCHEMA = "dreadstone.gore_control.v1"
GORE_CONTROL_VERSION = 1
SURFACE_GORE_CONTROL_SCHEMA = "dreadstone.surface_gore_control.v1"
SURFACE_GORE_CONTROL_VERSION = 1
MACRO_IDENTIFIERS = (
    "deformation_impact_size",
    "deformation_impact_crush",
    "deformation_impact_profile",
    "deformation_impact_edge_safety",
    "deformation_impact_chaos",
    "deformation_impact_asymmetry",
)
MACRO_LABELS = ("AREA", "DEPTH", "FALLOFF", "EDGE DAMAGE", "DISTORTION", "ASYMMETRY")
GORE_MACRO_IDENTIFIERS = (
    "deformation_gore_exposure",
    "deformation_gore_cavity",
    "deformation_gore_clot_fill",
    "deformation_gore_breakup",
    "deformation_gore_wetness_macro",
    "deformation_gore_variation",
)
GORE_MACRO_LABELS = (
    "COVERAGE",
    "INLAY",
    "FILL",
    "EDGE BREAKUP",
    "WETNESS",
    "RAISED",
)
SURFACE_GORE_MACRO_IDENTIFIERS = (
    "deformation_gore_surface_mass",
    "deformation_gore_surface_relief",
    "deformation_gore_nucleus",
    "deformation_gore_lobes",
    "deformation_gore_redness",
)
SURFACE_GORE_MACRO_LABELS = (
    "SURFACE MASS",
    "RELIEF",
    "NUCLEUS",
    "FOLDS",
    "REDNESS",
)
SURFACE_GORE_MACRO_DEFAULTS = {
    "mass": 0.0,
    "relief": 58.0,
    "nucleus": 0.0,
    "lobes": 55.0,
    "redness": 78.0,
}
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
        "deformation_impact_size", "AREA", 50.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="size", export_field="impactControl.macros.size",
    ),
    "deformation_impact_crush": _spec(
        "deformation_impact_crush", "DEPTH", 50.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="crush", export_field="impactControl.macros.crush",
    ),
    "deformation_impact_profile": _spec(
        "deformation_impact_profile", "FALLOFF", 50.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="profile", export_field="impactControl.macros.profile",
    ),
    "deformation_impact_edge_safety": _spec(
        "deformation_impact_edge_safety", "EDGE DAMAGE", 45.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="edgeSafety", export_field="impactControl.macros.edgeSafety",
    ),
    "deformation_impact_chaos": _spec(
        "deformation_impact_chaos", "DISTORTION", 42.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="chaos", export_field="impactControl.macros.chaos",
    ),
    "deformation_impact_asymmetry": _spec(
        "deformation_impact_asymmetry", "ASYMMETRY", 38.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="asymmetry", export_field="impactControl.macros.asymmetry",
    ),
    "deformation_impact_seed": _spec(
        "deformation_impact_seed", "Master Impact Seed", DEFAULT_IMPACT_SEED, 0, MAX_SEED,
        precision=0, step=1, scale_semantics="deterministic integer identity",
        recipe_field="impactSeed", export_field="impactControl.seed", integer=True,
    ),
    "deformation_gore_exposure": _spec(
        "deformation_gore_exposure", "COVERAGE", 72.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="exposure", export_field="goreControl.macros.exposure",
    ),
    "deformation_gore_cavity": _spec(
        "deformation_gore_cavity", "INLAY", 72.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="cavity", export_field="goreControl.macros.cavity",
    ),
    "deformation_gore_clot_fill": _spec(
        "deformation_gore_clot_fill", "FILL", 52.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="clotFill", export_field="goreControl.macros.clotFill",
    ),
    "deformation_gore_breakup": _spec(
        "deformation_gore_breakup", "EDGE BREAKUP", 62.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="breakup", export_field="goreControl.macros.breakup",
    ),
    "deformation_gore_wetness_macro": _spec(
        "deformation_gore_wetness_macro", "WETNESS", 68.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="wetness", export_field="goreControl.macros.wetness",
    ),
    "deformation_gore_variation": _spec(
        "deformation_gore_variation", "RAISED", 64.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="variation", export_field="goreControl.macros.variation",
    ),
    "deformation_gore_surface_mass": _spec(
        "deformation_gore_surface_mass", "SURFACE MASS", 0.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="surfaceMass",
        export_field="goreSurfaceControl.macros.mass",
    ),
    "deformation_gore_surface_relief": _spec(
        "deformation_gore_surface_relief", "RELIEF", 58.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="surfaceRelief",
        export_field="goreSurfaceControl.macros.relief",
    ),
    "deformation_gore_nucleus": _spec(
        "deformation_gore_nucleus", "NUCLEUS", 0.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="nucleus",
        export_field="goreSurfaceControl.macros.nucleus",
    ),
    "deformation_gore_lobes": _spec(
        "deformation_gore_lobes", "FOLDS", 55.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="lobes",
        export_field="goreSurfaceControl.macros.lobes",
    ),
    "deformation_gore_redness": _spec(
        "deformation_gore_redness", "REDNESS", 78.0, 0.0, 100.0,
        precision=1, step=1, scale_semantics="normalized 0-100",
        recipe_field="redness",
        export_field="goreSurfaceControl.macros.redness",
    ),
    "deformation_gore_inlay_amount": _spec(
        "deformation_gore_inlay_amount", "INLAY AMOUNT", 0.72, 0.0, 1.0,
        soft_min=0.0, soft_max=1.0, precision=2, step=1,
        scale_semantics="independent additive factor",
        recipe_field="goreInlayAmount",
    ),
    "deformation_gore_raised_amount": _spec(
        "deformation_gore_raised_amount", "RAISED AMOUNT", 0.64, 0.0, 1.0,
        soft_min=0.0, soft_max=1.0, precision=2, step=1,
        scale_semantics="independent additive factor",
        recipe_field="goreRaisedAmount",
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
    ("deformation_gore_host_deformation_contribution", "Host Deformation Contribution", 0.72, "goreHostDeformationContribution"),
    ("deformation_gore_bone_reveal", "Bone Reveal", 0.0, "goreBoneReveal"),
    ("deformation_gore_tissue_coverage", "Tissue Coverage", 0.45, "goreTissueCoverage"),
    ("deformation_gore_surface_mass_value", "Surface Mass", 0.0, "goreSurfaceMass"),
    ("deformation_gore_nucleus_amount", "Solid Nucleus", 0.0, "goreNucleusAmount"),
    ("deformation_gore_nucleus_lobes", "Nucleus Folds", 0.55, "goreNucleusLobes"),
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
    "deformation_gore_cavity_depth": _spec(
        "deformation_gore_cavity_depth", "Cavity Depth", 0.018, 0.0, 0.15,
        soft_max=0.06, precision=5, step=1, unit="LENGTH",
        response_curve="square", recipe_field="goreCavityDepth",
        relative_scale="actual host displacement, capture radius, and mean edge length",
    ),
    "deformation_gore_liner_separation": _spec(
        "deformation_gore_liner_separation", "Liner Separation", 0.00035, 0.00002, 0.02,
        soft_max=0.003, precision=6, step=1, unit="LENGTH",
        response_curve="log", recipe_field="goreLinerSeparation",
        relative_scale="capture radius and mean source edge length",
    ),
    "deformation_gore_rim_width": _spec(
        "deformation_gore_rim_width", "Cavity Rim Width", 0.004, 0.0, 0.05,
        soft_max=0.015, precision=5, step=1, unit="LENGTH",
        response_curve="square", recipe_field="goreRimWidth",
        relative_scale="capture radius and mean source edge length",
    ),
    "deformation_gore_clot_fill_depth": _spec(
        "deformation_gore_clot_fill_depth", "Clot Fill Depth", 0.008, 0.0, 0.15,
        soft_max=0.05, precision=5, step=1, unit="LENGTH",
        response_curve="square", recipe_field="goreClotFillDepth",
        relative_scale="cavity depth",
    ),
    "deformation_gore_proudness_limit": _spec(
        "deformation_gore_proudness_limit", "Proudness Limit", 0.0, 0.0, 0.01,
        soft_max=0.0015, precision=6, step=1, unit="LENGTH",
        response_curve="square", recipe_field="goreProudnessLimit",
        relative_scale="capture radius and mean source edge length",
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
    "goreGeometryMode": "STAIN_ONLY",
    "goreIdentityId": "Gore_Ooze_Wet",
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
    "goreCavityDepth": 0.0,
    "goreLinerSeparation": 0.00035,
    "goreRimWidth": 0.004,
    "goreClotFillDepth": 0.0,
    "goreProudnessLimit": 0.0,
    "goreHostDeformationContribution": 0.0,
    "goreBoneReveal": 0.0,
    "goreTissueCoverage": 0.0,
    "goreWoundBedEnabled": False,
    "goreClotLayerEnabled": False,
    "goreTissueLayerEnabled": False,
    "goreBoneLayerEnabled": False,
    "goreBarrierLayerEnabled": False,
    "goreRaisedRimOptIn": False,
    "goreAllowInternalFragments": False,
    "goreSurfaceMass": 0.0,
    "goreNucleusAmount": 0.0,
    "goreNucleusLobes": 0.55,
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


GORE_IDENTITIES = {
    "BRUISED_DENT": {
        "label": "Bruised Dent",
        "purpose": "A shallow crushed depression led by stain and compressed skin.",
        "macros": (42.0, 28.0, 12.0, 24.0, 24.0, 38.0),
        "layers": ("WOUND_BED",),
        "triangleBudget": 4200,
        "presetId": "Gore_Bruised_Dent",
    },
    "BLOODY_CRATER": {
        "label": "Bloody Crater",
        "purpose": "A wet open crater with a visible recessed bed and restrained clot fill.",
        "macros": (78.0, 76.0, 48.0, 62.0, 72.0, 66.0),
        "layers": ("WOUND_BED", "CLOT", "BARRIER"),
        "triangleBudget": 9000,
        "presetId": "Gore_Bloody_Crater",
    },
    "DARK_CLOT_CAVITY": {
        "label": "Dark Clot Cavity",
        "purpose": "A deep recess partially occupied by a dark, rough clot.",
        "macros": (68.0, 70.0, 86.0, 44.0, 34.0, 58.0),
        "layers": ("WOUND_BED", "CLOT"),
        "triangleBudget": 8600,
        "presetId": "Gore_Dark_Clot_Cavity",
    },
    "CRUSHED_TISSUE": {
        "label": "Crushed Tissue",
        "purpose": "A broad compressed wound with deterministic fiber and tissue breakup.",
        "macros": (74.0, 66.0, 56.0, 74.0, 50.0, 80.0),
        "layers": ("WOUND_BED", "CLOT", "TISSUE", "BARRIER"),
        "triangleBudget": 11000,
        "presetId": "Gore_Crushed_Tissue",
    },
    "EXPOSED_CRANIUM": {
        "label": "Exposed Cranium",
        "purpose": "A deep low-fill cavity with a pale plate beneath the wound bed.",
        "macros": (62.0, 92.0, 16.0, 48.0, 34.0, 56.0),
        "layers": ("WOUND_BED", "BONE", "BARRIER"),
        "triangleBudget": 9800,
        "presetId": "Gore_Exposed_Cranium",
    },
    "RAGGED_IMPACT": {
        "label": "Ragged Impact",
        "purpose": "An irregular torn-looking cavity with bounded peripheral fragments.",
        "macros": (82.0, 78.0, 46.0, 96.0, 68.0, 92.0),
        "layers": ("WOUND_BED", "CLOT", "TISSUE", "BARRIER"),
        "triangleBudget": 12000,
        "presetId": "Gore_Ragged_Impact",
        "raisedRimOptIn": True,
    },
}


for _identity_id, _identity in GORE_IDENTITIES.items():
    _layers = set(_identity["layers"])
    _preset_id = str(_identity["presetId"])
    GORE_PRESETS[_preset_id] = {
        "goreCoverage": 0.72,
        "goreScatter": 0.58,
        "goreEdgeFeather": 0.62,
        "goreWetness": 0.62,
        "goreDarkness": 0.56,
        "goreColorBias": (0.30, 0.008, 0.006),
        "gorePatchScale": 0.012,
        "goreOverlayMode": "STAIN_AND_RAISED",
        "goreGeometryMode": "CAVITY_INLAY",
        "goreIdentityId": _identity_id,
        "goreIntensityClass": "HIGH",
        "goreRaisedEnabled": True,
        "goreWoundBedEnabled": "WOUND_BED" in _layers,
        "goreClotLayerEnabled": "CLOT" in _layers,
        "goreTissueLayerEnabled": "TISSUE" in _layers,
        "goreBoneLayerEnabled": "BONE" in _layers,
        "goreBarrierLayerEnabled": "BARRIER" in _layers,
        "goreRaisedRimOptIn": bool(_identity.get("raisedRimOptIn", False)),
        "goreAllowInternalFragments": _identity_id in {"CRUSHED_TISSUE", "RAGGED_IMPACT"},
        "goreMaximumTriangles": int(_identity["triangleBudget"]),
        "goreMacroDefaults": {
            label: value
            for label, value in zip(
                ("exposure", "cavity", "clotFill", "breakup", "wetness", "variation"),
                _identity["macros"],
            )
        },
    }

# The only default used by the v3.19 front-facing workflow is a neutral
# user-authored recipe.  Named factory records above remain read-only migration
# sources for older .blend files and libraries; they are not exposed as choices.
GORE_PRESETS["USER_AUTHORED"] = copy.deepcopy(
    GORE_PRESETS["Gore_Bloody_Crater"]
)
GORE_PRESETS["USER_AUTHORED"].update({
    "goreIdentityId": "BLOODY_CRATER",
    "goreGeometryMode": "HYBRID_ADDITIVE",
    "goreMacroDefaults": {
        "exposure": 70.0,
        "cavity": 70.0,
        "clotFill": 52.0,
        "breakup": 58.0,
        "wetness": 68.0,
        "variation": 70.0,
    },
})

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
for _macro_index, _identifier in enumerate(GORE_MACRO_IDENTIFIERS):
    PARAMETERS[_identifier].preset_values = tuple(
        float(identity["macros"][_macro_index])
        for identity in GORE_IDENTITIES.values()
    )


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
        "goreControlSchema": GORE_CONTROL_SCHEMA,
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
            macros.get("asymmetry", macros.get(MACRO_IDENTIFIERS[5], 38.0)),
        )
    else:
        raw = tuple(macros)
        # v1 Impact Pedal records had five controls.  They remain readable and
        # receive the neutral v3.19 asymmetry value.
        if len(raw) == 5:
            raw = (*raw, 38.0)
    if len(raw) != 6:
        raise ValueError("Impact controls require exactly six macro values.")
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
    size, crush, profile, edge_safety, chaos, asymmetry = _macro_values(metadata.get("macros", {}))
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
            "asymmetry": asymmetry,
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
        size, crush, profile, edge_safety, chaos, asymmetry = _macro_values(metadata)
        payload = {
            "schema": IMPACT_CONTROL_SCHEMA,
            "version": IMPACT_CONTROL_VERSION,
            "mode": "MACRO",
            "macros": {
                "size": size, "crush": crush, "profile": profile,
                "edgeSafety": edge_safety, "chaos": chaos, "asymmetry": asymmetry,
            },
            "seed": DEFAULT_IMPACT_SEED,
        }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _gore_macro_values(macros):
    if isinstance(macros, Mapping):
        raw = (
            macros.get("exposure", macros.get(GORE_MACRO_IDENTIFIERS[0], 72.0)),
            macros.get("cavity", macros.get(GORE_MACRO_IDENTIFIERS[1], 72.0)),
            macros.get("clotFill", macros.get(GORE_MACRO_IDENTIFIERS[2], 52.0)),
            macros.get("breakup", macros.get(GORE_MACRO_IDENTIFIERS[3], 62.0)),
            macros.get("wetness", macros.get(GORE_MACRO_IDENTIFIERS[4], 68.0)),
            macros.get("variation", macros.get(GORE_MACRO_IDENTIFIERS[5], 64.0)),
        )
    else:
        raw = tuple(macros)
    if len(raw) != 6:
        raise ValueError("Gore Pedal requires exactly six macro values.")
    values = tuple(float(value) for value in raw)
    for identifier, value in zip(GORE_MACRO_IDENTIFIERS, values):
        errors = validate(identifier, value)
        if errors:
            raise ValueError(errors[0])
    return values


def _surface_gore_macro_values(macros):
    defaults = SURFACE_GORE_MACRO_DEFAULTS
    if isinstance(macros, Mapping):
        raw = (
            macros.get(
                "mass",
                macros.get(
                    SURFACE_GORE_MACRO_IDENTIFIERS[0],
                    defaults["mass"],
                ),
            ),
            macros.get(
                "relief",
                macros.get(
                    SURFACE_GORE_MACRO_IDENTIFIERS[1],
                    defaults["relief"],
                ),
            ),
            macros.get(
                "nucleus",
                macros.get(
                    SURFACE_GORE_MACRO_IDENTIFIERS[2],
                    defaults["nucleus"],
                ),
            ),
            macros.get(
                "lobes",
                macros.get(
                    SURFACE_GORE_MACRO_IDENTIFIERS[3],
                    defaults["lobes"],
                ),
            ),
            macros.get(
                "redness",
                macros.get(
                    SURFACE_GORE_MACRO_IDENTIFIERS[4],
                    defaults["redness"],
                ),
            ),
        )
    else:
        raw = tuple(macros)
    if len(raw) != len(SURFACE_GORE_MACRO_IDENTIFIERS):
        raise ValueError("Surface Gore macros require exactly five values.")
    values = tuple(float(value) for value in raw)
    for identifier, value in zip(
        SURFACE_GORE_MACRO_IDENTIFIERS,
        values,
    ):
        errors = validate(identifier, value)
        if errors:
            raise ValueError(errors[0])
    return values


def normalize_surface_gore_control(metadata=None):
    raw = {} if metadata is None else metadata
    if not isinstance(raw, Mapping):
        raise ValueError("Surface Gore control metadata must be an object.")
    schema_name = str(
        raw.get("schema", SURFACE_GORE_CONTROL_SCHEMA)
    )
    version = int(
        raw.get("version", SURFACE_GORE_CONTROL_VERSION)
    )
    if (
        schema_name != SURFACE_GORE_CONTROL_SCHEMA
        or version != SURFACE_GORE_CONTROL_VERSION
    ):
        raise ValueError(
            f"Unsupported Surface Gore control metadata "
            f"{schema_name!r} version {version}."
        )
    mass, relief, nucleus, lobes, redness = (
        _surface_gore_macro_values(raw.get("macros", {}))
    )
    normalized = {
        "schema": SURFACE_GORE_CONTROL_SCHEMA,
        "version": SURFACE_GORE_CONTROL_VERSION,
        "macros": {
            "mass": mass,
            "relief": relief,
            "nucleus": nucleus,
            "lobes": lobes,
            "redness": redness,
        },
    }
    normalized["identityDigest"] = surface_gore_identity_digest(
        normalized
    )
    return normalized


def surface_gore_identity_digest(metadata):
    if isinstance(metadata, Mapping) and "macros" in metadata:
        values = _surface_gore_macro_values(
            metadata.get("macros", {})
        )
    else:
        values = _surface_gore_macro_values(metadata)
    payload = {
        "schema": SURFACE_GORE_CONTROL_SCHEMA,
        "version": SURFACE_GORE_CONTROL_VERSION,
        "macros": {
            label: value
            for label, value in zip(
                ("mass", "relief", "nucleus", "lobes", "redness"),
                values,
            )
        },
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_surface_gore_parameters(
    macros,
    *,
    region_scale=0.075,
    mean_edge_length=0.004,
):
    """Map cohesive surface macros to raised-shell and nucleus controls."""

    mass, relief, nucleus, lobes, redness = (
        _surface_gore_macro_values(macros)
    )
    mass_n, relief_n, nucleus_n, lobes_n, redness_n = (
        value / 100.0
        for value in (mass, relief, nucleus, lobes, redness)
    )
    region = float(region_scale)
    if not math.isfinite(region) or region <= 0.0:
        region = 0.075
    region = max(0.005, min(2.0, region))
    edge = float(mean_edge_length)
    if not math.isfinite(edge) or edge <= 0.0:
        edge = region * 0.05
    edge = max(1e-6, edge)
    scale_floor = max(edge * 1.2, region * 0.012)
    clot_thickness = max(
        0.0001,
        min(
            0.05,
            scale_floor
            * (0.08 + 0.82 * relief_n**1.35)
            * (0.72 + 0.38 * mass_n),
        ),
    )
    surface_offset = max(
        0.00015,
        min(
            0.012,
            scale_floor * (0.025 + 0.10 * relief_n),
        ),
    )
    island_breakup = min(
        1.0,
        0.04
        + (1.0 - mass_n) * (0.38 + 0.46 * lobes_n)
        + 0.10 * lobes_n,
    )
    peripheral = min(
        1.0,
        (1.0 - mass_n) ** 1.35
        * (0.16 + 0.84 * lobes_n),
    )
    result = {
        "goreSurfaceMass": mass_n,
        "goreNucleusAmount": nucleus_n,
        "goreNucleusLobes": lobes_n,
        "goreClotCoverage": min(
            1.0,
            0.12 + 0.88 * mass_n**0.72,
        ),
        "goreCoreDensity": min(
            1.0,
            0.18 + 0.82 * mass_n**0.78,
        ),
        "goreClotThickness": clot_thickness,
        "goreThicknessVariation": min(
            1.0,
            0.06
            + 0.72
            * lobes_n
            * (0.45 + 0.55 * relief_n),
        ),
        "goreIslandBreakup": island_breakup,
        "gorePeripheralFragments": peripheral,
        "goreSurfaceOffset": surface_offset,
        "goreGeometryDensity": min(
            1.0,
            0.25 + 0.75 * mass_n**0.65,
        ),
        "goreDarkClotBias": min(
            1.0,
            max(
                0.0,
                0.76
                - 0.54 * redness_n
                + 0.12 * (1.0 - mass_n),
            ),
        ),
        "goreRoughEdgeBias": min(
            1.0,
            0.16
            + 0.64 * lobes_n * (1.0 - 0.58 * mass_n),
        ),
        "goreColorIntensity": min(
            1.0,
            0.36 + 0.64 * redness_n,
        ),
        "goreDarkness": min(
            1.0,
            max(
                0.0,
                0.68
                - 0.52 * redness_n
                + 0.08 * (1.0 - relief_n),
            ),
        ),
        "goreOrganicIrregularity": min(
            1.0,
            0.10 + 0.86 * lobes_n,
        ),
        "goreSurfaceRoundness": min(
            1.0,
            0.08 + 0.86 * relief_n,
        ),
        "goreFiberTextureStrength": min(
            1.0,
            0.20
            + 0.65 * lobes_n * (1.0 - 0.55 * nucleus_n),
        ),
        "goreBaseColorStrength": min(
            1.0,
            0.25 + 0.75 * redness_n,
        ),
    }
    for field, value in result.items():
        errors = validate_recipe_value(field, value)
        if errors:
            raise ValueError(errors[0])
    return result


def gore_identity_for_preset(preset_id):
    preset = GORE_PRESETS.get(str(preset_id), {})
    identity = str(preset.get("goreIdentityId", ""))
    return identity if identity in GORE_IDENTITIES else ""


def gore_identity_defaults(identity_id):
    identity = GORE_IDENTITIES.get(str(identity_id))
    if identity is None:
        raise ValueError(f"Unsupported gore identity {identity_id!r}.")
    return {
        "identityId": str(identity_id),
        "label": str(identity["label"]),
        "purpose": str(identity["purpose"]),
        "macros": {
            label: float(value)
            for label, value in zip(
                ("exposure", "cavity", "clotFill", "breakup", "wetness", "variation"),
                identity["macros"],
            )
        },
        "layers": list(identity["layers"]),
        "triangleBudget": int(identity["triangleBudget"]),
        "raisedRimOptIn": bool(identity.get("raisedRimOptIn", False)),
        "presetId": str(identity["presetId"]),
    }


def normalize_gore_control(metadata):
    if not isinstance(metadata, Mapping):
        raise ValueError("Gore control metadata must be an object.")
    schema_name = str(metadata.get("schema", GORE_CONTROL_SCHEMA))
    version = int(metadata.get("version", GORE_CONTROL_VERSION))
    if schema_name != GORE_CONTROL_SCHEMA or version != GORE_CONTROL_VERSION:
        raise ValueError(f"Unsupported gore control metadata {schema_name!r} version {version}.")
    mode = str(metadata.get("mode", "MACRO")).upper()
    if mode not in {"MACRO", "MANUAL"}:
        raise ValueError("Gore control mode must be MACRO or MANUAL.")
    identity_id = str(metadata.get("identityId", "BLOODY_CRATER"))
    if identity_id not in GORE_IDENTITIES:
        raise ValueError(f"Unsupported gore identity {identity_id!r}.")
    exposure, cavity, clot_fill, breakup, wetness, variation = _gore_macro_values(
        metadata.get("macros", {})
    )
    seed = int(metadata.get("seed", DEFAULT_IMPACT_SEED))
    errors = validate("deformation_gore_mask_seed", seed)
    if errors:
        raise ValueError(errors[0])
    normalized = {
        "schema": GORE_CONTROL_SCHEMA,
        "version": GORE_CONTROL_VERSION,
        "mode": mode,
        "recipeClass": "GORE_PEDAL" if mode == "MACRO" else "CUSTOM",
        "identityId": identity_id,
        "macros": {
            "exposure": exposure,
            "cavity": cavity,
            "clotFill": clot_fill,
            "breakup": breakup,
            "wetness": wetness,
            "variation": variation,
        },
        "seed": seed,
    }
    normalized["identityDigest"] = gore_identity_digest(normalized)
    return normalized


def gore_identity_digest(metadata):
    if isinstance(metadata, Mapping) and "macros" in metadata:
        payload = {
            "schema": str(metadata.get("schema", GORE_CONTROL_SCHEMA)),
            "version": int(metadata.get("version", GORE_CONTROL_VERSION)),
            "mode": str(metadata.get("mode", "MACRO")).upper(),
            "identityId": str(metadata.get("identityId", "BLOODY_CRATER")),
            "macros": dict(metadata.get("macros", {})),
            "seed": int(metadata.get("seed", DEFAULT_IMPACT_SEED)),
        }
    else:
        values = _gore_macro_values(metadata)
        payload = {
            "schema": GORE_CONTROL_SCHEMA,
            "version": GORE_CONTROL_VERSION,
            "mode": "MACRO",
            "identityId": "BLOODY_CRATER",
            "macros": {
                label: value
                for label, value in zip(
                    ("exposure", "cavity", "clotFill", "breakup", "wetness", "variation"),
                    values,
                )
            },
            "seed": DEFAULT_IMPACT_SEED,
        }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_gore_parameters(
    macros,
    *,
    identity_id="BLOODY_CRATER",
    region_scale=0.075,
    stamp_depth=0.025,
    mean_edge_length=0.004,
):
    """Map the six Gore Pedal controls to one bounded scale-relative inlay recipe."""

    exposure, cavity, clot_fill, breakup, wetness, variation = _gore_macro_values(macros)
    if identity_id not in GORE_IDENTITIES:
        raise ValueError(f"Unsupported gore identity {identity_id!r}.")
    # v3.19 keeps the serialized v1 field names readable while presenting a
    # preset-free contract: exposure=coverage, cavity=inlay amount,
    # clotFill=fill, and variation=raised amount.
    exposure_n, cavity_n, clot_n, breakup_n, wet_n, variation_n = (
        value / 100.0
        for value in (exposure, cavity, clot_fill, breakup, wetness, variation)
    )
    region = float(region_scale)
    if not math.isfinite(region) or region <= 0.0:
        region = 0.075
    region = max(0.005, min(2.0, region))
    depth = max(0.0, float(stamp_depth))
    if not math.isfinite(depth):
        depth = 0.025
    edge = max(1e-6, float(mean_edge_length))
    if not math.isfinite(edge):
        edge = region * 0.05
    identity = GORE_IDENTITIES[identity_id]
    identity_factors = {
        "BRUISED_DENT": (0.62, 0.30, 0.72),
        "BLOODY_CRATER": (1.00, 1.00, 1.00),
        "DARK_CLOT_CAVITY": (0.92, 0.96, 1.10),
        "CRUSHED_TISSUE": (1.04, 0.88, 1.16),
        "EXPOSED_CRANIUM": (0.82, 1.18, 0.78),
        "RAGGED_IMPACT": (1.08, 1.02, 1.25),
    }[identity_id]
    exposure_factor, cavity_factor, breakup_factor = identity_factors
    scale_floor = max(edge * 1.6, region * 0.018)
    host_contribution = min(1.0, cavity_factor * (0.08 + 0.92 * cavity_n**1.35))
    cavity_depth = min(
        0.15,
        max(
            0.0,
            min(depth * 0.72, region * 0.34)
            * cavity_factor
            * cavity_n**1.45,
        ),
    )
    if cavity_n <= 1e-8:
        cavity_depth = 0.0
    liner_separation = max(0.00002, min(0.02, scale_floor * (0.014 + 0.018 * cavity_n)))
    if cavity_n > 1e-8:
        cavity_depth = min(0.15, max(cavity_depth, liner_separation * 2.5))
    rim_width = max(0.0, min(0.05, region * (0.025 + 0.075 * cavity_n) + edge * 0.18))
    clot_fill_depth = (
        0.0
        if cavity_depth <= 0.0 or clot_n <= 0.0
        else max(
            liner_separation * 1.5,
            cavity_depth * (0.17 + 0.38 * (1.0 - clot_n)),
        )
    )
    raised_opt_in = bool(identity.get("raisedRimOptIn", False))
    proudness_limit = (
        min(0.01, max(edge * 0.035, region * 0.0025) * breakup_n)
        if raised_opt_in else 0.0
    )
    coverage = min(
        1.0,
        exposure_factor
        * (
            0.10
            + 0.58 * exposure_n**0.78
            + 0.20 * exposure_n * cavity_n
            + 0.08 * exposure_n * (1.0 - clot_n)
        ),
    )
    clot_coverage = min(1.0, clot_n**0.82 * (0.28 + 0.72 * exposure_n))
    tissue_coverage = min(
        1.0,
        (0.18 + 0.58 * exposure_n) * (0.30 + 0.70 * breakup_n) * (1.0 - clot_n * 0.42),
    )
    bone_identity = 1.0 if identity_id == "EXPOSED_CRANIUM" else 0.35
    bone_reveal = min(1.0, bone_identity * cavity_n**1.8 * (1.0 - clot_n)**1.25)
    wet_roughness_response = wet_n**0.82
    raised_amount = variation_n
    inlay_amount = cavity_n
    if raised_amount > 1e-8 and inlay_amount > 1e-8:
        geometry_mode = "HYBRID_ADDITIVE"
    elif inlay_amount > 1e-8:
        geometry_mode = "CAVITY_INLAY"
    elif raised_amount > 1e-8:
        geometry_mode = "LEGACY_RAISED"
    else:
        geometry_mode = "STAIN_ONLY"
    result = {
        "goreGeometryMode": geometry_mode,
        "goreIdentityId": identity_id,
        "goreInlayAmount": inlay_amount,
        "goreRaisedAmount": raised_amount,
        "goreCoverage": coverage,
        "goreScatter": min(1.0, 0.08 + 0.92 * breakup_n),
        "goreEdgeFeather": min(1.0, 0.28 + 0.50 * exposure_n + 0.22 * (1.0 - breakup_n)),
        "goreWetness": wet_roughness_response,
        "goreDarkness": min(1.0, 0.28 + 0.38 * (1.0 - wet_n) + 0.22 * clot_n),
        "gorePatchScale": max(0.001, min(0.10, region * (0.08 + 0.12 * exposure_n))),
        "goreClotCoverage": clot_coverage,
        "goreCoreDensity": min(1.0, 0.26 + 0.48 * exposure_n + 0.26 * cavity_n),
        "goreClotThickness": max(0.0001, min(0.05, scale_floor * (0.10 + 0.30 * clot_n))),
        "goreThicknessVariation": min(1.0, 0.08 + 0.72 * breakup_n),
        "goreIslandBreakup": min(1.0, breakup_factor * (0.06 + 0.88 * breakup_n)),
        "gorePeripheralFragments": min(1.0, breakup_n**1.35),
        "goreSurfaceOffset": max(0.00015, min(0.012, liner_separation)),
        "goreGeometryDensity": min(1.0, 0.18 + 0.62 * exposure_n + 0.20 * breakup_n),
        "goreWetnessVariation": min(1.0, wet_n * (0.30 + 0.70 * breakup_n)),
        "goreDarkClotBias": min(1.0, 0.18 + 0.68 * clot_n + 0.14 * (1.0 - wet_n)),
        "goreRoughEdgeBias": min(1.0, 0.24 + 0.62 * breakup_n),
        "goreColorIntensity": min(1.0, 0.46 + 0.54 * exposure_n),
        "goreOrganicIrregularity": min(1.0, breakup_n**0.72),
        "goreSurfaceRoundness": min(1.0, 0.08 + 0.30 * clot_n),
        "goreFiberTextureStrength": min(1.0, 0.18 + 0.70 * breakup_n),
        "goreBaseColorStrength": min(1.0, 0.28 + 0.58 * exposure_n),
        "goreInnerRimWidth": rim_width,
        "goreInnerRimStrength": min(1.0, 0.22 + 0.68 * cavity_n),
        "goreCavityDepth": cavity_depth,
        "goreLinerSeparation": liner_separation,
        "goreRimWidth": rim_width,
        "goreClotFillDepth": min(cavity_depth, clot_fill_depth),
        "goreProudnessLimit": proudness_limit,
        "goreHostDeformationContribution": host_contribution,
        "goreBoneReveal": bone_reveal,
        "goreTissueCoverage": tissue_coverage,
        "goreWoundBedEnabled": "WOUND_BED" in identity["layers"],
        "goreClotLayerEnabled": (
            "CLOT" in identity["layers"] and clot_coverage > 1e-6 and cavity_depth > 0.0
        ),
        "goreTissueLayerEnabled": (
            "TISSUE" in identity["layers"] and tissue_coverage > 1e-6 and cavity_depth > 0.0
        ),
        "goreBoneLayerEnabled": (
            "BONE" in identity["layers"] and bone_reveal > 1e-6 and cavity_depth > 0.0
        ),
        "goreBarrierLayerEnabled": "BARRIER" in identity["layers"] and cavity_depth > 0.0,
        "goreRaisedRimOptIn": raised_opt_in,
        "goreAllowInternalFragments": identity_id in {"CRUSHED_TISSUE", "RAGGED_IMPACT"},
        "goreMaximumTriangles": int(identity["triangleBudget"]),
    }
    fields = (
        "goreCoverage", "goreScatter", "goreEdgeFeather", "goreWetness", "goreDarkness",
        "gorePatchScale", "goreClotCoverage", "goreCoreDensity", "goreClotThickness",
        "goreThicknessVariation", "goreIslandBreakup", "gorePeripheralFragments",
        "goreSurfaceOffset", "goreGeometryDensity", "goreWetnessVariation",
        "goreDarkClotBias", "goreRoughEdgeBias", "goreColorIntensity",
        "goreOrganicIrregularity", "goreSurfaceRoundness", "goreFiberTextureStrength",
        "goreBaseColorStrength", "goreInnerRimWidth", "goreInnerRimStrength",
        "goreCavityDepth", "goreLinerSeparation", "goreRimWidth",
        "goreClotFillDepth", "goreProudnessLimit", "goreHostDeformationContribution",
        "goreBoneReveal", "goreTissueCoverage", "goreMaximumTriangles",
        "goreInlayAmount", "goreRaisedAmount",
    )
    errors = []
    for field in fields:
        errors.extend(validate_recipe_value(field, result[field]))
    if errors:
        raise ValueError("; ".join(errors))
    return result


def derive_impact_parameters(macros, *, region_scale=0.075, family="COMPACT_DENT", seed=DEFAULT_IMPACT_SEED):
    """Map six high-leverage controls to one bounded physical recipe.

    ``region_scale`` is the captured patch's estimated world-space radius.  It
    changes only the response scale; it never changes capture indices or the
    placement anchor.
    """

    size, crush, profile, edge_safety, chaos, asymmetry = _macro_values(macros)
    seed = int(seed)
    seed_errors = validate("deformation_impact_seed", seed)
    if seed_errors:
        raise ValueError(seed_errors[0])
    size_n, crush_n, profile_n, edge_n, chaos_n, asymmetry_n = (
        value / 100.0
        for value in (size, crush, profile, edge_safety, chaos, asymmetry)
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
    # Edge Damage is intentionally visible even away from a registered seam.
    # Seam protection remains conservative and inversely follows edge damage.
    seam_protection = radius * (0.02 + 0.18 * (1.0 - edge_n) ** 1.4)
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
        "impactEdgeDamage": edge_n,
        "impactAsymmetry": asymmetry_n,
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
        0.02 + 0.18 * (1.0 - candidate / 100.0) ** 1.4 - target
    ))
    chaos = 100.0 * max(0.0, min(1.0, float(values.get("impactChaos", 0.0))))
    asymmetry = 100.0 * max(0.0, min(1.0, float(values.get("impactAsymmetry", 0.38))))
    return {
        "size": round(size, 3),
        "crush": round(crush, 3),
        "profile": round(profile, 3),
        "edgeSafety": float(edge),
        "chaos": round(chaos, 3),
        "asymmetry": round(asymmetry, 3),
    }


def gore_presets():
    return copy.deepcopy(GORE_PRESETS)


def gore_identities():
    return copy.deepcopy(GORE_IDENTITIES)


def raised_gore_defaults():
    return copy.deepcopy(RAISED_GORE_DEFAULTS)
