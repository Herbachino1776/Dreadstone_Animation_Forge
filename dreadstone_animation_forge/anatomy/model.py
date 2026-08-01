"""Neutral rig snapshot model consumed by anatomy services."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable


@dataclass(frozen=True)
class BoneRecord:
    name: str
    parent: str = ""
    head: tuple[float, float, float] = (0.0, 0.0, 0.0)
    tail: tuple[float, float, float] = (0.0, 0.0, 0.0)
    length: float = 1.0
    use_deform: bool = True
    valid: bool = True

    @property
    def center(self) -> tuple[float, float, float]:
        return tuple((a + b) * 0.5 for a, b in zip(self.head, self.tail))

    @property
    def finite(self) -> bool:
        return (
            isfinite(float(self.length))
            and all(isfinite(float(value)) for value in self.head + self.tail)
        )


@dataclass(frozen=True)
class RigSnapshot:
    bones: tuple[BoneRecord, ...]
    armature_name: str = ""
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)

    @classmethod
    def from_bones(
        cls,
        bones: Iterable[BoneRecord],
        *,
        armature_name: str = "",
        scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    ) -> "RigSnapshot":
        return cls(tuple(bones), armature_name=armature_name, scale=scale)

    def by_name(self) -> dict[str, BoneRecord]:
        return {bone.name: bone for bone in self.bones}

    def children(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {bone.name: [] for bone in self.bones}
        for bone in self.bones:
            if bone.parent in result:
                result[bone.parent].append(bone.name)
        for names in result.values():
            names.sort()
        return result


__all__ = ("BoneRecord", "RigSnapshot")
