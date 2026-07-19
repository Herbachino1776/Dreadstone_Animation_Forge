#!/usr/bin/env python3
"""Static contract validation for Dreadstone Animation Forge.

This script intentionally does not import the add-on because Blender's ``bpy``
module is unavailable in ordinary Python and GitHub Actions.
"""

from __future__ import annotations

import ast
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dreadstone_animation_forge"
MANIFEST_PATH = PACKAGE / "blender_manifest.toml"
USER_GUIDE_PATH = ROOT / "docs" / "USER_WORKFLOW_GUIDE.md"
MODULE_NAMES = (
    "__init__.py",
    "damage_readiness.py",
    "damage_authoring.py",
    "deformation_authoring.py",
    "trauma_field.py",
)
MODULE_PATHS = tuple(PACKAGE / name for name in MODULE_NAMES)

EXPECTED_VERSION = (3, 11, 0)
EXPECTED_READINESS_BUILD = "2026-07-18.source-contract.1"
EXPECTED_AUTHORING_BUILD = "2026-07-18.source-contract.1"
EXPECTED_DEFORMATION_BUILD = "2026-07-18.stamp-library.1"

REQUIRED_GUIDE_HEADINGS = (
    "## 1. Install Dreadstone Animation Forge 3.11.0",
    "## 2. Open the Dreadstone panel",
    "## 3. Import and prepare a source GLB",
    "## 5. Author and approve animation drafts",
    "## 6. Build and validate an approved animation pack",
    "## 7. Run Source Damage Readiness",
    "## 8. Build Damage Segment and Stump Authoring assets",
    "## 9. Preview intact and detached states",
    "## 10. Register and validate deformation pairs",
    "## 12. Capture a surface with every placement mode",
    "## 13. Choose influence masks, distance modes, and damage axis",
    "## 14. Create and manage trauma stamps",
    "## 15. Preview, rebuild, compare, sculpt, and repair",
    "## 16. Run every validation command",
    "## 17. Export the damage GLB and manifest",
    "## 18. Clean reimport and verification",
    "## 19. Beginner recipes",
    "## 20. Troubleshooting and recovery",
    "## Complete public button inventory",
)

REQUIRED_GUIDE_UI_LABELS = {
    "**Adopt Imported Animation Pack**",
    "**Safe Resize**",
    "**Analyze Rig**",
    "**Analyze Source Damage Readiness**",
    "**Repair Source Readiness Contract**",
    "**Preview Candidate Seam**",
    "**Load READY Handoff**",
    "**Build Authoring Asset**",
    "**Preview Intact**",
    "**Preview Detached**",
    "**Register Selected Pair**",
    "**Validate Pair**",
    "**Capture Single Face**",
    "**Capture Connected Face Patch**",
    "**Capture Selected Vertices**",
    "**Capture 3D Cursor**",
    "**Patch Only**",
    "**Patch Feathered**",
    "**Connected Surface**",
    "**Surface Distance**",
    "**World Distance**",
    "**Add Stamp**",
    "**Update Active Stamp**",
    "**Enable / Disable**",
    "**Save Stamp Library...**",
    "**Load Stamp Library...**",
    "**Compact Dent**",
    "**Broad Cave**",
    "**Flat Compression**",
    "**Directional Shear**",
    "**Raised Impact Rim**",
    "**Ridge Collapse**",
    "**REBUILD ACTIVE DEFORMATION**",
    "**Attached**",
    "**Detached**",
    "**Both**",
    "**REPAIR LEGACY PAIR SYNC**",
    "**Validate Morph Targets**",
    "**Validate Complete Damage Asset**",
    "**Export Damage GLB + Manifest**",
    "**Restore Reimported GLB Intact Preview**",
    "**Build Approved Animation Pack**",
    "**Validate Last Built Pack**",
}

REQUIRED_SCHEMAS = {
    "dreadstone.animation_pack.v1",
    "dreadstone.damage_readiness.v1",
    "dreadstone.source_readiness.v1",
    "dreadstone.damage_authoring.v1",
    "dreadstone.damage_deformation.v1",
    "dreadstone.trauma_stamp_library.v1",
}

REQUIRED_OBJECT_NAMES = {
    "DSB_DAMAGE_RIG",
    "DSB_SOURCE_MODEL_PROTECTED",
    "DSB_BODY_CORE",
    "DSB_ATTACHED_HEAD",
    "DSB_ATTACHED_FOREARM_L",
    "DSB_ATTACHED_FOREARM_R",
    "DSB_SEGMENT_HEAD",
    "DSB_SEGMENT_FOREARM_L",
    "DSB_SEGMENT_FOREARM_R",
    "DSB_SEGMENT_UPPER_BODY",
    "DSB_SEGMENT_LOWER_BODY",
    "DSB_STUMP_NECK_TORSO",
    "DSB_STUMP_NECK_HEAD",
    "DSB_STUMP_ELBOW_L_UPPER",
    "DSB_STUMP_ELBOW_L_LOWER",
    "DSB_STUMP_ELBOW_R_UPPER",
    "DSB_STUMP_ELBOW_R_LOWER",
    "DSB_STUMP_WAIST_LOWER",
    "DSB_STUMP_WAIST_UPPER",
    "DSB_SOCKET_ABDOMEN_VISCERA",
}

REQUIRED_SEAMS = {"Head–Neck", "Left Elbow", "Right Elbow", "Lower Spine"}
REQUIRED_DEFORMATION_KEYS = {
    "Head_Dent_Left",
    "Head_Dent_Right",
    "Head_Cave_Front",
    "Jaw_Displaced",
}

REQUIRED_OPERATORS = {
    "daf.analyze_damage_readiness": "Analyze Source Damage Readiness",
    "daf.repair_source_readiness_contract": "Repair Source Readiness Contract",
    "daf.restore_imported_damage_intact_preview": "Restore Imported GLB Intact Preview",
    "daf.export_damage_asset": "Export Damage GLB + Manifest",
    "daf.create_damage_shape_key": "Create Damage Shape Key",
    "daf.create_standard_head_deformations": "Create Standard Head Set",
    "daf.select_deformation_key": "Select Deformation Key",
    "daf.solo_deformation_key": "Solo Deformation Key",
    "daf.zero_deformations": "Zero All Deformations",
    "daf.delete_managed_deformation": "Delete Managed Deformation",
    "daf.capture_deformation_selected_face": "Capture Center from Selected Face",
    "daf.capture_deformation_cursor": "Capture Center from 3D Cursor",
    "daf.preview_deformation_seed": "Preview Procedural Seed",
    "daf.commit_deformation_seed": "Commit Seed to Active Key",
    "daf.clear_deformation_seed": "Clear Uncommitted Seed",
    "daf.begin_deformation_sculpt": "Begin Sculpt",
    "daf.finish_deformation_sculpt": "Finish Sculpt & Sync",
    "daf.create_mirrored_deformation": "Create Mirrored Shape Key",
    "daf.build_active_deformation_preset": "Build Active Preset",
    "daf.show_deformation_attached": "Show Attached",
    "daf.show_deformation_detached": "Show Detached",
    "daf.show_deformation_overlay": "Show Both",
    "daf.validate_deformations": "Validate Deformations",
    "daf.register_deformation_region": "Register Selected Region Pair",
    "daf.select_deformation_region": "Select Active Region",
    "daf.validate_deformation_region": "Validate Registered Pair",
    "daf.remove_deformation_region": "Remove Region Registration",
    "daf.capture_deformation_selected_patch": "Capture Connected Face Patch",
    "daf.capture_deformation_selected_vertices": "Capture Selected Vertices",
    "daf.add_trauma_stamp": "Add Stamp",
    "daf.select_trauma_stamp": "Select Active Stamp",
    "daf.update_trauma_stamp": "Update Active Stamp",
    "daf.duplicate_trauma_stamp": "Duplicate Stamp",
    "daf.remove_trauma_stamp": "Remove Stamp",
    "daf.move_trauma_stamp_up": "Move Stamp Up",
    "daf.move_trauma_stamp_down": "Move Stamp Down",
    "daf.toggle_trauma_stamp": "Enable / Disable Stamp",
    "daf.preview_active_trauma_stamp": "Preview Active Stamp",
    "daf.rebuild_active_deformation": "Rebuild Active Deformation",
    "daf.repair_legacy_pair_sync": "Repair Legacy Pair Sync",
    "daf.save_trauma_stamp_library": "Save Trauma Stamp Library",
    "daf.load_trauma_stamp_library": "Load Trauma Stamp Library",
}

REQUIRED_UI_TEXT = {
    "Source Damage Readiness",
    "Damage Segment & Stump Authoring v3.9",
    "Trauma Field Authoring v3.11.0",
    "Restore Reimported GLB Intact Preview",
    "Validate Complete Damage Asset",
    "BUILD ACTIVE PRESET",
    "Attached",
    "Detached",
    "Both",
    "Sculpting is optional; presets are now intended to read clearly out of the box",
}

REQUIRED_TRAUMA_FAMILIES = {
    "COMPACT_DENT",
    "BROAD_CAVE",
    "FLAT_COMPRESSION",
    "DIRECTIONAL_SHEAR",
    "RAISED_IMPACT_RIM",
    "RIDGE_COLLAPSE",
}
REQUIRED_CAPTURE_MODES = {"SINGLE_FACE", "SELECTED_FACE_PATCH", "SELECTED_VERTICES", "CURSOR"}
REQUIRED_INFLUENCE_MODES = {"PATCH_ONLY", "PATCH_FEATHERED", "CONNECTED_SURFACE"}
REQUIRED_DISTANCE_MODES = {"SURFACE_DISTANCE", "WORLD_DISTANCE"}

FORBIDDEN_TRANSFER_IDENTIFIERS = {
    "kdtree",
    "find_nearest",
    "nearest_neighbor",
    "nearest_neighbors",
    "closest_point_on_mesh",
}


class ContractError(RuntimeError):
    """Raised when a static source contract is not satisfied."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def read_sources() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in MODULE_PATHS
        if path.is_file()
    }


def parse_sources(sources: dict[str, str]) -> dict[str, ast.Module]:
    return {
        name: ast.parse(source, filename=f"dreadstone_animation_forge/{name}")
        for name, source in sources.items()
    }


def literal_assignment(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return ast.literal_eval(node.value)
    raise ContractError(f"assignment {name} was not found")


def read_bl_info_version(tree: ast.Module) -> tuple[int, int, int]:
    bl_info = literal_assignment(tree, "bl_info")
    require(isinstance(bl_info, dict), "bl_info is not a dictionary literal")
    version = tuple(bl_info.get("version", ()))
    return version  # type: ignore[return-value]


def string_literals(trees: Iterable[ast.AST]) -> set[str]:
    return {
        node.value
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def operator_contracts(trees: Iterable[ast.Module]) -> dict[str, str]:
    result: dict[str, str] = {}
    for tree in trees:
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            values: dict[str, str] = {}
            for statement in node.body:
                if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                if not isinstance(statement.value, ast.Constant) or not isinstance(statement.value.value, str):
                    continue
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in {"bl_idname", "bl_label"}:
                        values[target.id] = statement.value.value
            if "bl_idname" in values:
                result[values["bl_idname"]] = values.get("bl_label", "")
    return result


def dict_literal_pairs(tree: ast.AST) -> set[tuple[str, object]]:
    pairs: set[tuple[str, object]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and isinstance(value, ast.Constant)
            ):
                try:
                    pairs.add((key.value, value.value))
                except TypeError:
                    pass
    return pairs


def executable_identifiers(tree: ast.AST) -> set[str]:
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr.lower())
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                identifiers.update(part.lower() for part in alias.name.split("."))
    return identifiers


def require_markers(source: str, markers: Iterable[str], contract: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    require(not missing, f"{contract} missing markers: {', '.join(missing)}")


def check_module_files() -> None:
    missing = [path.relative_to(ROOT).as_posix() for path in MODULE_PATHS if not path.is_file()]
    if not MANIFEST_PATH.is_file():
        missing.append(MANIFEST_PATH.relative_to(ROOT).as_posix())
    require(not missing, f"missing modules: {', '.join(missing)}")


def current_version_string() -> str:
    return ".".join(map(str, EXPECTED_VERSION))


def current_zip_name() -> str:
    return f"Dreadstone_Animation_Forge_v{'_'.join(map(str, EXPECTED_VERSION))}.zip"


def check_user_workflow_guide() -> None:
    require(USER_GUIDE_PATH.is_file(), "docs/USER_WORKFLOW_GUIDE.md is missing")
    guide = USER_GUIDE_PATH.read_text(encoding="utf-8")
    require(current_version_string() in guide, f"user guide does not contain version {current_version_string()}")
    require(current_zip_name() in guide, f"user guide does not contain release ZIP {current_zip_name()}")
    missing_headings = [heading for heading in REQUIRED_GUIDE_HEADINGS if heading not in guide]
    require(not missing_headings, "user guide missing workflow headings: " + "; ".join(missing_headings))
    missing_labels = sorted(label for label in REQUIRED_GUIDE_UI_LABELS if label not in guide)
    require(not missing_labels, "user guide missing key UI labels: " + ", ".join(missing_labels))

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    development = (ROOT / "docs" / "DEVELOPMENT.md").read_text(encoding="utf-8")
    releases = (ROOT / "docs" / "RELEASES.md").read_text(encoding="utf-8")
    require("docs/USER_WORKFLOW_GUIDE.md" in readme, "README does not link to the authoritative user guide")
    require("USER_WORKFLOW_GUIDE.md" in development, "DEVELOPMENT does not link to the authoritative user guide")
    require("docs/USER_WORKFLOW_GUIDE.md" in releases, "release checklist does not reference the authoritative user guide")


def check_extension_manifest() -> None:
    source = MANIFEST_PATH.read_text(encoding="utf-8")
    require_markers(
        source,
        (
            'schema_version = "1.0.0"',
            'id = "dreadstone_animation_forge"',
            'version = "3.11.0"',
            'name = "Dreadstone Animation Forge"',
            'type = "add-on"',
            'blender_version_min = "4.2.0"',
            '"SPDX:LicenseRef-Proprietary"',
        ),
        "Blender extension manifest",
    )


def check_parse(sources: dict[str, str]) -> None:
    require(set(sources) == set(MODULE_NAMES), "not all required module sources were read")
    parse_sources(sources)


def check_compile() -> None:
    with tempfile.TemporaryDirectory(prefix="dreadstone-static-compile-") as temp_dir:
        for path in MODULE_PATHS:
            output = Path(temp_dir) / f"{path.name}.pyc"
            py_compile.compile(str(path), cfile=str(output), doraise=True)


def check_versions(trees: dict[str, ast.Module]) -> None:
    add_on = read_bl_info_version(trees["__init__.py"])
    readiness_build = literal_assignment(trees["damage_readiness.py"], "ANALYZER_BUILD_ID")
    authoring_build = literal_assignment(trees["damage_authoring.py"], "AUTHORING_BUILD_ID")
    deformation = tuple(literal_assignment(trees["deformation_authoring.py"], "DEFORMATION_VERSION"))
    build = literal_assignment(trees["deformation_authoring.py"], "DEFORMATION_BUILD_ID")
    require(add_on == EXPECTED_VERSION, f"bl_info version is {add_on}, expected {EXPECTED_VERSION}")
    require(readiness_build == EXPECTED_READINESS_BUILD, f"readiness build is {readiness_build!r}")
    require(authoring_build == EXPECTED_AUTHORING_BUILD, f"damage authoring build is {authoring_build!r}")
    require(deformation == EXPECTED_VERSION, f"deformation version is {deformation}, expected {EXPECTED_VERSION}")
    require(build == EXPECTED_DEFORMATION_BUILD, f"deformation build is {build!r}")


def check_package_imports(sources: dict[str, str]) -> None:
    init_source = sources["__init__.py"]
    require_markers(
        init_source,
        (
            'importlib.import_module(".damage_readiness", __package__)',
            'importlib.import_module(".damage_authoring", __package__)',
            'importlib.import_module(".deformation_authoring", __package__)',
        ),
        "package module imports",
    )
    require("from . import damage_readiness" in sources["damage_authoring.py"], "damage_authoring relative import changed")
    require("from . import trauma_field" in sources["deformation_authoring.py"], "trauma_field relative import is missing")


def check_schemas_names_keys_seams(trees: dict[str, ast.Module]) -> None:
    literals = string_literals(trees.values())
    missing_schemas = sorted(REQUIRED_SCHEMAS - literals)
    missing_names = sorted(REQUIRED_OBJECT_NAMES - literals)
    missing_keys = sorted(REQUIRED_DEFORMATION_KEYS - literals)
    missing_seams = sorted(REQUIRED_SEAMS - literals)
    require(not missing_schemas, f"missing schemas: {', '.join(missing_schemas)}")
    require(not missing_names, f"missing generated names: {', '.join(missing_names)}")
    require(not missing_keys, f"missing standard deformation keys: {', '.join(missing_keys)}")
    require(not missing_seams, f"missing required seams: {', '.join(missing_seams)}")


def check_operators_and_ui(trees: dict[str, ast.Module]) -> None:
    actual = operator_contracts(trees.values())
    mismatches = [
        f"{operator_id} ({actual.get(operator_id)!r} != {label!r})"
        for operator_id, label in REQUIRED_OPERATORS.items()
        if actual.get(operator_id) != label
    ]
    require(not mismatches, "operator contracts changed: " + "; ".join(mismatches))
    literals = string_literals(trees.values())
    missing_ui = sorted(REQUIRED_UI_TEXT - literals)
    require(not missing_ui, f"missing UI labels: {', '.join(missing_ui)}")


def check_world_space_and_exact_index(source: str) -> None:
    require_markers(
        source,
        (
            "center_world = attached.matrix_world @ center_local",
            "basis_world = attached.matrix_world @ basis_local",
            "distance = offset_world.length",
            "inverse_world = attached.matrix_world.inverted()",
            "coordinates.append(inverse_world @ result_world)",
            "return obj.matrix_world.to_3x3()",
            "delta_world = _local_delta_to_world(attached, delta_attached_local)",
            "delta_detached_local = _world_delta_to_local(detached, delta_world)",
            "for index in range(len(attached_key.data)):",
            "delta_a = _local_delta_to_world(attached, attached_key.data[index].co - attached_basis.data[index].co)",
            "delta_d = _local_delta_to_world(detached, detached_key.data[index].co - detached_basis.data[index].co)",
            "def _max_displacement(obj, name):",
            "_local_delta_to_world(obj, key.data[i].co - basis.data[i].co).length",
        ),
        "world-space exact-index synchronization",
    )


def check_preview_and_presets(source: str) -> None:
    require_markers(
        source,
        (
            'PREVIEW_KEY_NAME = "__DSB_DEFORMATION_SEED_PREVIEW"',
            "attached.hide_set(not show_attached)",
            "detached.hide_set(not show_detached)",
            "obj.hide_viewport = False",
            "layer_collection.exclude = False",
            "layer_collection.hide_viewport = False",
            "def _visibility_blocker(context, obj):",
            'bl_idname = "daf.show_deformation_attached"',
            'bl_idname = "daf.show_deformation_detached"',
            'bl_idname = "daf.show_deformation_overlay"',
            'bl_idname = "daf.build_active_deformation_preset"',
            'text="BUILD ACTIVE PRESET"',
            'family == "localized_dent"',
            'family == "broad_cave"',
            'family == "directional_displacement"',
            "outward_world * rim",
            "attached_key.value = 0.0",
            "_zero_managed_weights(attached)",
            'bl_idname = "daf.begin_deformation_sculpt"',
            'bl_idname = "daf.finish_deformation_sculpt"',
            "Sculpting is optional",
        ),
        "legacy preview/preset/sculpt contracts",
    )


def check_trauma_field_contracts(sources: dict[str, str], trees: dict[str, ast.Module]) -> None:
    trauma_tree = trees["trauma_field.py"]
    families = set(literal_assignment(trauma_tree, "TRAUMA_FAMILIES"))
    placements = set(literal_assignment(trauma_tree, "PLACEMENT_MODES"))
    influences = set(literal_assignment(trauma_tree, "INFLUENCE_MODES"))
    distances = set(literal_assignment(trauma_tree, "DISTANCE_MODES"))
    require(families == REQUIRED_TRAUMA_FAMILIES, f"trauma families changed: {sorted(families)}")
    require(placements == REQUIRED_CAPTURE_MODES, f"capture modes changed: {sorted(placements)}")
    require(influences == REQUIRED_INFLUENCE_MODES, f"influence modes changed: {sorted(influences)}")
    require(distances == REQUIRED_DISTANCE_MODES, f"distance modes changed: {sorted(distances)}")
    require_markers(
        sources["trauma_field.py"],
        (
            "def build_virtual_weld_map(",
            "def virtualize_edges(",
            "def virtual_face_components(",
            "def build_weighted_adjacency(",
            "def geodesic_distances(",
            "def selection_hash(",
            "def geodesic_cache_key(",
            "def surface_mask_weights(",
            "def validate_stamp_stack(",
            "def evaluate_stamp_stack(",
            "def normalize_stamp_library(",
            "def match_positional_anchors(",
            "def portable_anchor_tolerance(",
            "heapq.heappop",
            '"virtualWeldDigest"',
            '"virtualWeldTolerance"',
        ),
        "pure trauma-field algorithms",
    )
    require_markers(
        sources["deformation_authoring.py"],
        (
            'REGISTRY_PROPERTY = "dsb_deformation_region_registry_json"',
            "def _resolve_active_region(",
            'bl_idname = "daf.register_deformation_region"',
            'bl_idname = "daf.capture_deformation_selected_patch"',
            'bl_idname = "daf.capture_deformation_selected_vertices"',
            'bl_idname = "daf.preview_active_trauma_stamp"',
            'bl_idname = "daf.rebuild_active_deformation"',
            'bl_idname = "daf.repair_legacy_pair_sync"',
            'bl_idname = "daf.save_trauma_stamp_library"',
            'bl_idname = "daf.load_trauma_stamp_library"',
            "trauma_field.evaluate_stamp_stack",
            "trauma_field.build_virtual_weld_map",
            "trauma_field.virtual_face_components",
            'virtual_members=virtual_weld["virtual_members"]',
            '"virtualConnectedComponentCount"',
            '"legacySyncStatus"',
            '"legacySyncErrorBefore"',
            '"legacySyncErrorAfter"',
            '"legacySyncRepairApplied"',
            'text="REPAIR LEGACY PAIR SYNC"',
            'text="Save Stamp Library..."',
            'text="Load Stamp Library..."',
            '"ANALYTICAL_POSITIONAL_ANCHORS"',
            '"portableVertexAnchorsLocal"',
            '"portableFaceAnchorsLocal"',
            '"registeredRegions"',
            '"orderedStamps"',
            '"activeRegionId"',
            '"maximumPairDeltaError"',
            '"validationStatus"',
            '"recipeStatus": "LEGACY_MANUAL"',
        ),
        "region registry and trauma authoring integration",
    )


def check_source_readiness_contracts(sources: dict[str, str], trees: dict[str, ast.Module]) -> None:
    require_markers(
        sources["damage_readiness.py"],
        (
            'SOURCE_CONTRACT_SCHEMA = "dreadstone.source_readiness.v1"',
            'SOURCE_CONTRACT_TEXT_NAME = "DSB_SOURCE_READINESS_CONTRACT.json"',
            'SOURCE_OBJECT_ID_PROPERTY = "dsb_source_readiness_object_id"',
            'SOURCE_DATA_ID_PROPERTY = "dsb_source_readiness_data_id"',
            'SOURCE_COLLECTION_ID_PROPERTY = "dsb_source_readiness_collection_id"',
            "def resolve_source_readiness_inputs(context):",
            "load_source_readiness_contract()",
            "return _resolve_authoring_state_objects(context, authoring_state)",
            "def validate_source_readiness_contract(contract, context):",
            "def persist_source_readiness_contract(report, json_path, markdown_path):",
            'bl_idname = "daf.repair_source_readiness_contract"',
            'bl_label = "Repair Source Readiness Contract"',
            "generated DSB_* meshes cannot replace it",
        ),
        "source-readiness identity and recovery",
    )
    require_markers(
        sources["damage_authoring.py"],
        (
            '"source_readiness_contract": source_contract',
            "validate_source_readiness_contract(contract, bpy.context)",
            '"source_readiness": {',
            '"Export validation failed: Authoring validation failed: "',
        ),
        "separate authoring/export validation",
    )
    require_markers(
        sources["trauma_field.py"],
        (
            "def is_generated_authoring_role(",
            "def source_readiness_stale_reasons(",
            "def enabled_stamp_contract_errors(",
            '"DSB_BODY_CORE"',
            '"DSB_ATTACHED_"',
            '"DSB_DETACHED_"',
            '"DSB_STUMP_"',
            '"DSB_DAMAGE_"',
        ),
        "pure source-readiness contract rules",
    )
    export = next(
        node for node in trees["damage_authoring.py"].body
        if isinstance(node, ast.FunctionDef) and node.name == "_export_asset"
    )
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(export)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    forbidden = {
        "build_damage_readiness_report",
        "write_damage_readiness_reports",
        "persist_source_readiness_contract",
    }
    require(not (called & forbidden), "export reruns or overwrites source readiness")
    require("_validate_authoring" in called, "export does not run generated authoring validation")


def check_glb_morph_hooks(tree: ast.Module) -> None:
    pairs = dict_literal_pairs(tree)
    required = {
        ("export_morph", True),
        ("export_morph_normal", True),
        ("export_morph_tangent", False),
    }
    require(required <= pairs, "GLB morph export flags changed or are missing")


def check_no_nearest_neighbor(trees: Iterable[ast.Module]) -> None:
    found = sorted(FORBIDDEN_TRANSFER_IDENTIFIERS & set().union(*(executable_identifiers(tree) for tree in trees)))
    require(not found, f"nearest-neighbor transfer identifiers found: {', '.join(found)}")


def check_merge_markers(sources: dict[str, str]) -> None:
    markers = ("<<<<<<<", "=======", ">>>>>>>")
    affected = [name for name, source in sources.items() if any(marker in source for marker in markers)]
    require(not affected, f"unresolved merge markers in: {', '.join(affected)}")


def tracked_paths() -> list[PurePosixPath]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    return [PurePosixPath(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def check_repository_hygiene() -> None:
    offenders: list[str] = []
    for path in tracked_paths():
        lowered_parts = {part.lower() for part in path.parts}
        lowered_name = path.name.lower()
        if "__pycache__" in lowered_parts or lowered_name.endswith((".pyc", ".pyo")):
            offenders.append(path.as_posix())
        elif lowered_name.endswith((".blend1", ".blend2", ".blend@", ".tmp", ".temp")):
            offenders.append(path.as_posix())
        elif path.parts and path.parts[0].lower() in {"dist", "build"}:
            offenders.append(path.as_posix())
        elif lowered_name.endswith(".zip"):
            offenders.append(path.as_posix())
    require(not offenders, "generated/temporary files are tracked: " + ", ".join(offenders))


def main() -> int:
    print("DREADSTONE ANIMATION FORGE v3.11.0 STATIC VALIDATION")
    print("Blender is not imported; runtime acceptance remains separate.")

    sources: dict[str, str] = {}
    trees: dict[str, ast.Module] = {}
    checks: list[tuple[str, Callable[[], None]]] = [
        ("all five package modules exist", check_module_files),
        ("Blender extension manifest exists and matches v3.11.0", check_extension_manifest),
        ("all Python modules parse with ast.parse", lambda: check_parse(sources)),
        ("all Python modules compile with py_compile", check_compile),
        ("add-on/deformation version and build contracts", lambda: check_versions(trees)),
        ("expected package-relative module imports", lambda: check_package_imports(sources)),
        ("manifest schemas, DSB names, seams, and standard keys", lambda: check_schemas_names_keys_seams(trees)),
        ("required operators and UI labels", lambda: check_operators_and_ui(trees)),
        ("world-space exact-index deformation synchronization", lambda: check_world_space_and_exact_index(sources["deformation_authoring.py"])),
        ("attached/detached preview, preset, and optional sculpt contracts", lambda: check_preview_and_presets(sources["deformation_authoring.py"])),
        ("trauma-field algorithms, registry, stamps, rebuild, and additive manifest contracts", lambda: check_trauma_field_contracts(sources, trees)),
        ("source-readiness identity, staleness, repair, and export separation", lambda: check_source_readiness_contracts(sources, trees)),
        ("GLB morph target and morph normal export hooks", lambda: check_glb_morph_hooks(trees["damage_authoring.py"])),
        ("no nearest-neighbor deformation transfer implementation", lambda: check_no_nearest_neighbor((trees["deformation_authoring.py"], trees["trauma_field.py"]))),
        ("no unresolved source merge markers", lambda: check_merge_markers(sources)),
        ("no generated, cache, backup, archive, or temporary files tracked", check_repository_hygiene),
        ("authoritative user workflow guide inventory and release metadata", check_user_workflow_guide),
    ]

    failures: list[str] = []
    for index, (label, check) in enumerate(checks):
        if index == 1:
            sources = read_sources()
        if index == 3:
            trees = parse_sources(sources)
        try:
            check()
        except Exception as exc:  # Report every independent contract in one run.
            failures.append(f"{label}: {exc}")
            print(f"FAIL - {label}: {exc}")
        else:
            print(f"PASS - {label}")

    if failures:
        print(f"RESULT: FAIL ({len(checks) - len(failures)}/{len(checks)} checks passed)")
        return 1

    print(f"RESULT: PASS ({len(checks)}/{len(checks)} checks passed)")
    print("RUNTIME: Blender 5.1.2 acceptance is still required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
