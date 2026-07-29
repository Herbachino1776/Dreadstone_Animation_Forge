"""Task-oriented Forge UI and orchestrating operators."""

from . import panels, properties, workflow_state
from .operators import animations, character, compound, diagnostics, export, gore, impacts, previews, progressive, regions, validation, vip


CLASSES = (
    *character.CLASSES,
    *animations.CLASSES,
    *regions.CLASSES,
    *impacts.CLASSES,
    *previews.CLASSES,
    *progressive.CLASSES,
    *diagnostics.CLASSES,
    *gore.CLASSES,
    *compound.CLASSES,
    *validation.CLASSES,
    *export.CLASSES,
    *vip.CLASSES,
)

__all__ = ("CLASSES", "panels", "properties", "workflow_state")
