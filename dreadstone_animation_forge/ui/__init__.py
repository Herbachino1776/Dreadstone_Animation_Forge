"""Task-oriented Forge UI and orchestrating operators."""

from . import panels, properties, workflow_state
from .operators import character, compound, diagnostics, export, gore, impacts, previews, regions, validation


CLASSES = (
    *character.CLASSES,
    *regions.CLASSES,
    *impacts.CLASSES,
    *previews.CLASSES,
    *diagnostics.CLASSES,
    *gore.CLASSES,
    *compound.CLASSES,
    *validation.CLASSES,
    *export.CLASSES,
)

__all__ = ("CLASSES", "panels", "properties", "workflow_state")
