"""Creature Anatomy Profile foundation.

The modules in this package are intentionally Blender-independent except for
``blender_adapter``.  This keeps profile detection, validation, migration, and
serialization usable in ordinary Python tests and future external tooling.
"""

from .profiles import (
    HUMANOID_PROFILE_ID,
    QUADRUPED_PROFILE_ID,
    get_builtin_profile,
    registry,
)
from .schema import PROFILE_SCHEMA, AnatomyProfile, CapabilitySpec, ChainSpec

__all__ = (
    "PROFILE_SCHEMA",
    "AnatomyProfile",
    "CapabilitySpec",
    "ChainSpec",
    "HUMANOID_PROFILE_ID",
    "QUADRUPED_PROFILE_ID",
    "get_builtin_profile",
    "registry",
)
