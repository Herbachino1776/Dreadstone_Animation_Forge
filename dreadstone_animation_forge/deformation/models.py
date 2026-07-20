"""Typed, Blender-independent state models for deformation authoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class PreviewQuality(str, Enum):
    OFF = "OFF"
    FAST = "FAST"
    BALANCED = "BALANCED"
    FINAL = "FINAL"


class PreviewStatus(str, Enum):
    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
    BUILDING = "BUILDING"
    READY = "READY"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PreviewResult:
    generation: int
    quality: str
    elapsed_ms: float = 0.0
    affected_vertex_count: int = 0
    estimated_gore_triangles: int = 0
    final_gore_triangles: int = 0
    message: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class OperationFailure:
    stage: str
    exception_type: str
    message: str


PREVIEW_QUALITY_ITEMS = tuple(
    (quality.value, quality.value.title(), {
        "OFF": "Disable managed live preview",
        "FAST": "Affected vertices and lightweight stain only",
        "BALANCED": "Complete deformation with reduced-density gore after debounce",
        "FINAL": "Deterministic final geometry and focused validation",
    }[quality.value])
    for quality in PreviewQuality
)
