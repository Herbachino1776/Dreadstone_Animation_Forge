#!/usr/bin/env python3
"""Build the deterministic Blender-installable release ZIP."""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"
DIST = ROOT / "dist"
DEFORMATION_BUILD = "2026-07-17.trauma-field.1"
MODULES = (
    "__init__.py",
    "damage_readiness.py",
    "damage_authoring.py",
    "deformation_authoring.py",
    "trauma_field.py",
)
ARCHIVE_ENTRIES = (
    "blender_manifest.toml",
    "__init__.py",
    "damage_readiness.py",
    "damage_authoring.py",
    "deformation_authoring.py",
    "trauma_field.py",
    "README.txt",
    "VALIDATION.txt",
)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def read_version() -> tuple[int, int, int]:
    tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "bl_info" for target in node.targets):
            value = ast.literal_eval(node.value)
            version = tuple(value["version"])
            if len(version) != 3 or not all(isinstance(part, int) for part in version):
                raise RuntimeError("bl_info version must be a three-integer tuple")
            return version  # type: ignore[return-value]
    raise RuntimeError("bl_info version was not found")


def run_validation() -> str:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_addon.py")],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    print(result.stdout, end="")
    if result.returncode:
        raise RuntimeError("static validation failed; release was not built")
    normalized = result.stdout.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.rstrip() + "\n"


def validation_text(version: tuple[int, int, int], report: str) -> bytes:
    dotted = ".".join(map(str, version))
    files = "\n".join(f"  dreadstone_animation_forge/{name}" for name in MODULES)
    text = f"""DREADSTONE ANIMATION FORGE v{dotted} VALIDATION
{'=' * (38 + len(dotted))}

Version: {dotted}
Deformation build: {DEFORMATION_BUILD}

Files validated:
{files}

Static validation report:
{report}
Static checks passed. Blender runtime acceptance was not performed by this
builder and remains required inside Blender 5.1.2 before release acceptance.
"""
    return text.encode("utf-8")


def zip_info(name: str, *, directory: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    mode = 0o40755 if directory else 0o100644
    info.external_attr = mode << 16
    return info


def build_zip(target: Path, readme: bytes, validation: bytes) -> None:
    payloads: dict[str, bytes] = {
        "blender_manifest.toml": (PACKAGE / "blender_manifest.toml").read_bytes(),
        "README.txt": readme,
        "VALIDATION.txt": validation,
        **{
            name: (PACKAGE / name).read_bytes()
            for name in MODULES
        },
    }
    with zipfile.ZipFile(target, "w") as archive:
        for entry in ARCHIVE_ENTRIES:
            if entry.endswith("/"):
                archive.writestr(zip_info(entry, directory=True), b"")
            else:
                archive.writestr(zip_info(entry), payloads[entry])


def verify_zip(target: Path) -> None:
    with zipfile.ZipFile(target, "r") as archive:
        actual = tuple(archive.namelist())
        if actual != ARCHIVE_ENTRIES:
            raise RuntimeError(f"archive layout mismatch: expected {ARCHIVE_ENTRIES!r}, got {actual!r}")
        bad_file = archive.testzip()
        if bad_file is not None:
            raise RuntimeError(f"archive integrity failure in {bad_file}")
        for info in archive.infolist():
            if info.date_time != ZIP_TIMESTAMP:
                raise RuntimeError(f"non-deterministic timestamp on {info.filename}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    report = run_validation()
    version = read_version()
    dotted = ".".join(map(str, version))
    filename_version = "_".join(map(str, version))
    target = DIST / f"Dreadstone_Animation_Forge_v{filename_version}.zip"
    DIST.mkdir(exist_ok=True)
    for stale in DIST.glob("Dreadstone_Animation_Forge_v*.zip"):
        stale.unlink()

    readme = (ROOT / "README.md").read_text(encoding="utf-8").encode("utf-8")
    build_zip(target, readme, validation_text(version, report))
    verify_zip(target)

    print(f"BUILT: {target.relative_to(ROOT).as_posix()}")
    print(f"VERSION: {dotted}")
    print(f"ENTRIES: {len(ARCHIVE_ENTRIES)} (exact installable layout verified)")
    print("INTEGRITY: PASS")
    print(f"SHA256: {sha256(target)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
