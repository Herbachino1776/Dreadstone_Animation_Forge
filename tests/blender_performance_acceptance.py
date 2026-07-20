"""Blender 5.1 performance/resource acceptance for Dreadstone Animation Forge.

Run with a prepared authoring file; the runner never chooses anatomical faces.
It records SKIP for operations whose authored prerequisites are absent.

Example:
  blender prepared.blend --background --factory-startup --python \
    tests/blender_performance_acceptance.py -- --output results.json \
    --source testman_animpack_v002.glb --stress
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
import traceback
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "dreadstone.forge_performance_acceptance.v1"
OPERATION_NAMES = (
    "addon_registration",
    "open_dreadstone_panel",
    "repeated_panel_redraw_idle",
    "region_switching",
    "deformation_key_switching",
    "face_patch_capture",
    "single_stamp_fast_preview",
    "slider_edit_preview_sequence",
    "permanent_deformation_rebuild",
    "attached_detached_synchronization",
    "core_body_deformation_rebuild",
    "forearm_deformation_rebuild",
    "raised_gore_preview_rebuild",
    "repeated_gore_parameter_changes",
    "compound_event_preview",
    "compound_event_rebuild",
    "gore_validation",
    "morph_validation",
    "complete_asset_validation",
    "preview_clear_state_restoration",
    "save_and_reload",
    "addon_disable_reenable",
    "file_reload_addon_active",
    "fifty_preview_clear_cycles",
    "twenty_region_key_switches",
    "ten_final_gore_rebuilds",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--stress", action="store_true")
    parser.add_argument("--commit", default="")
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(values)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(explicit=""):
    if explicit:
        return explicit
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def rss_bytes():
    try:
        import psutil
        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = (
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                )

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            get_process = ctypes.windll.kernel32.GetCurrentProcess
            get_process.restype = wintypes.HANDLE
            get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
            get_memory.argtypes = (
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD,
            )
            get_memory.restype = wintypes.BOOL
            handle = get_process()
            if get_memory(
                handle, ctypes.byref(counters), counters.cb
            ):
                return int(counters.WorkingSetSize)
        except Exception:
            pass
    return None


def register_addon():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import dreadstone_animation_forge as addon
    addon.register()
    return addon


def resource_counts(addon):
    deformation = addon.deformation_authoring
    attributes = sum(len(mesh.attributes) + len(mesh.color_attributes) for mesh in bpy.data.meshes)
    shape_keys = sum(
        len(obj.data.shape_keys.key_blocks)
        for obj in bpy.data.objects if obj.type == 'MESH' and obj.data.shape_keys
    )
    return {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "actions": len(bpy.data.actions),
        "shapeKeys": shape_keys,
        "collections": len(bpy.data.collections),
        "attributes": attributes,
        "temporaryPreviewObjects": sum(bool(obj.get("dsb_preview_only", False)) for obj in bpy.data.objects),
        "generatedGoreObjects": sum(obj.get("dsb_generated_role", "") == "raised_gore" for obj in bpy.data.objects),
        "forgeLoadHandlers": sum(
            getattr(handler, "__module__", "").endswith("deformation.preview_service")
            for handler in bpy.app.handlers.load_post
        ),
        "forgePreviewTimer": int(deformation.preview_service.state().get("timerRegistered", False)),
        "pythonCaches": deformation.service_cache_counts(),
        "rssBytes": rss_bytes(),
    }


def numeric_growth(before, after):
    keys = (
        "objects", "meshes", "materials", "actions", "shapeKeys", "collections",
        "attributes", "temporaryPreviewObjects", "generatedGoreObjects",
        "forgeLoadHandlers", "forgePreviewTimer",
    )
    return {key: int(after[key]) - int(before[key]) for key in keys}


def json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def operation_record(name, callback, failures, *, iterations=1):
    samples = []
    detail = None
    try:
        for _unused in range(iterations):
            started = time.perf_counter()
            detail = callback()
            samples.append(time.perf_counter() - started)
        return {
            "name": name,
            "status": "PASS",
            "iterations": iterations,
            "durationsMs": [round(value * 1000.0, 3) for value in samples],
            "medianMs": round(statistics.median(samples) * 1000.0, 3),
            "detail": json_safe(detail),
        }
    except SkipOperation as exc:
        return {"name": name, "status": "SKIP", "reason": str(exc), "iterations": 0, "durationsMs": []}
    except Exception as exc:
        failure = {
            "operation": name,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc()[-6000:],
        }
        failures.append(failure)
        return {"name": name, "status": "FAIL", "reason": str(exc), "iterations": len(samples), "durationsMs": [round(value * 1000.0, 3) for value in samples]}


class SkipOperation(RuntimeError):
    pass


def require_active_stamp(addon):
    deformation = addon.deformation_authoring
    settings = bpy.context.scene.daf_settings
    if not settings.deformation_active_key or not settings.deformation_active_stamp_id:
        raise SkipOperation("fixture has no active managed key/stamp")
    if not settings.deformation_seed_center_valid:
        raise SkipOperation("fixture has no active capture")
    return deformation, settings


def evaluate_relative_gate(current, healed):
    if current <= 0.0 or healed < 0.0:
        raise ValueError("preview medians must be non-negative and baseline must be positive")
    improvement = (current - healed) / current
    return {"baselineMs": current, "healedMs": healed, "improvementFraction": improvement, "pass": improvement >= 0.50}


def main():
    args = parse_args()
    failures = []
    operations = []
    started = time.perf_counter()

    registration_started = time.perf_counter()
    addon = register_addon()
    from dreadstone_animation_forge.deformation import performance as performance_contract
    registration_elapsed = time.perf_counter() - registration_started
    deformation = addon.deformation_authoring
    settings = bpy.context.scene.daf_settings
    operations.append({
        "name": "addon_registration", "status": "PASS", "iterations": 1,
        "durationsMs": [round(registration_elapsed * 1000.0, 3)],
        "medianMs": round(registration_elapsed * 1000.0, 3),
    })
    baseline = resource_counts(addon)

    operations.append(operation_record(
        "open_dreadstone_panel",
        lambda: deformation.cached_ui_summary(settings),
        failures,
    ))
    operations.append(operation_record(
        "repeated_panel_redraw_idle",
        lambda: deformation.cached_ui_summary(settings),
        failures,
        iterations=100,
    ))

    def switch_regions():
        registry = deformation._load_registry()
        ids = [str(region.get("regionId", "")) for region in registry.get("regions", [])]
        if not ids:
            raise SkipOperation("fixture has no registered regions")
        original = str(registry.get("activeRegionId", ""))
        for region_id in ids:
            deformation._set_active_region(region_id, bpy.context)
        if original:
            deformation._set_active_region(original, bpy.context)
        return {"regionIds": ids}

    operations.append(operation_record("region_switching", switch_regions, failures))

    def switch_keys():
        registry, region, attached, _detached = deformation._resolve_active_region(bpy.context)
        names = deformation._managed_names(attached)
        if not names:
            raise SkipOperation("active region has no managed keys")
        for name in names:
            deformation._select_key(settings, name)
        return {"region": region.get("regionId"), "keyCount": len(names)}

    operations.append(operation_record("deformation_key_switching", switch_keys, failures))
    operations.append({"name": "face_patch_capture", "status": "SKIP", "reason": "runner never chooses anatomical faces; prepare the fixture with an artist-selected patch", "iterations": 0, "durationsMs": []})

    operations.append(operation_record(
        "single_stamp_fast_preview",
        lambda: (require_active_stamp(addon)[0].preview_service.run_now(bpy.context, quality="FAST")),
        failures,
    ))

    def slider_sequence():
        _deformation, active_settings = require_active_stamp(addon)
        base = float(active_settings.deformation_seed_radius)
        results = []
        for offset in (-0.004, -0.002, 0.0, 0.002, 0.004):
            active_settings.deformation_seed_radius = max(0.005, base + offset)
            results.append(_deformation.preview_service.run_now(bpy.context, quality="FAST"))
        return {"previewCount": len(results), "affected": [item.get("affectedVertexCount", 0) for item in results]}

    operations.append(operation_record("slider_edit_preview_sequence", slider_sequence, failures))
    operations.append(operation_record(
        "permanent_deformation_rebuild",
        lambda: require_active_stamp(addon)[0].commit_current_tuning(bpy.context),
        failures,
    ))

    def sync_pair():
        deformation, active_settings = require_active_stamp(addon)
        registry, region, _attached, detached = deformation._resolve_active_region(bpy.context)
        if detached is None:
            raise SkipOperation("active region is CORE_SINGLE")
        deformation.sync_key_to_detached(active_settings.deformation_active_key, region.get("regionId"))
        return {"region": region.get("regionId"), "key": active_settings.deformation_active_key}

    operations.append(operation_record("attached_detached_synchronization", sync_pair, failures))

    def rebuild_named_region(region_id):
        registry = deformation._load_registry()
        region = deformation._region_record(registry, region_id)
        if region is None:
            raise SkipOperation(f"{region_id} is not registered")
        attached, _detached = deformation._resolve_region_pair(region)
        names = deformation._managed_names(attached)
        if not names:
            raise SkipOperation(f"{region_id} has no authored deformation")
        deformation._set_active_region(region_id, bpy.context)
        deformation._select_key(settings, names[0])
        return deformation.rebuild_active_deformation(bpy.context)

    operations.append(operation_record("core_body_deformation_rebuild", lambda: rebuild_named_region("body_core"), failures))
    operations.append(operation_record("forearm_deformation_rebuild", lambda: rebuild_named_region("forearm_left"), failures))

    def gore_rebuild():
        deformation, _settings = require_active_stamp(addon)
        return deformation.rebuild_current_raised_gore(bpy.context)

    operations.append(operation_record("raised_gore_preview_rebuild", gore_rebuild, failures))

    def gore_changes():
        deformation, active_settings = require_active_stamp(addon)
        base = float(active_settings.deformation_gore_coverage)
        for offset in (-0.04, -0.02, 0.0, 0.02, 0.04):
            active_settings.deformation_gore_coverage = max(0.0, min(1.0, base + offset))
            deformation.preview_service.run_now(bpy.context, quality="FAST")
        return {"changes": 5}

    operations.append(operation_record("repeated_gore_parameter_changes", gore_changes, failures))

    def compound_preview():
        registry = deformation._load_registry()
        if not registry.get("compoundEvents"):
            raise SkipOperation("fixture has no compound event")
        return deformation.preview_compound_event(bpy.context)

    operations.append(operation_record("compound_event_preview", compound_preview, failures))
    operations.append(operation_record(
        "compound_event_rebuild",
        lambda: deformation.rebuild_compound_event(bpy.context) if deformation._load_registry().get("compoundEvents") else (_ for _ in ()).throw(SkipOperation("fixture has no compound event")),
        failures,
    ))
    operations.append(operation_record("gore_validation", lambda: deformation.validate_deformations(require_keys=False), failures))
    operations.append(operation_record("morph_validation", lambda: deformation.validate_deformations(require_keys=False), failures))

    def complete_validation():
        result = bpy.ops.daf.validate_damage_authoring_asset()
        if 'FINISHED' not in result:
            raise RuntimeError("complete asset validation did not finish")
        return {"status": settings.last_damage_authoring_validation}

    operations.append(operation_record("complete_asset_validation", complete_validation, failures))
    operations.append(operation_record(
        "preview_clear_state_restoration",
        lambda: deformation.preview_service.clear(bpy.context),
        failures,
    ))

    temp_save = Path(args.output).with_suffix(".reload.blend")

    def save_and_reload():
        nonlocal settings
        result = bpy.ops.wm.save_as_mainfile(filepath=str(temp_save), check_existing=False)
        if 'FINISHED' not in result:
            raise RuntimeError("temporary save did not finish")
        result = bpy.ops.wm.open_mainfile(filepath=str(temp_save), load_ui=False)
        if 'FINISHED' not in result:
            raise RuntimeError("saved fixture did not reopen")
        if not hasattr(bpy.context.scene, "daf_settings"):
            addon.register()
        settings = bpy.context.scene.daf_settings
        return {
            "path": str(temp_save),
            "sourceContract": str(settings.source_readiness_contract_status),
            "forgeLoadHandlers": resource_counts(addon)["forgeLoadHandlers"],
        }

    operations.append(operation_record(
        "save_and_reload",
        save_and_reload,
        failures,
    ))

    def disable_reenable():
        addon.unregister()
        addon.unregister()
        addon.register()
        return {"forgeLoadHandlers": resource_counts(addon)["forgeLoadHandlers"]}

    operations.append(operation_record("addon_disable_reenable", disable_reenable, failures, iterations=3))
    settings = bpy.context.scene.daf_settings
    operations.append(operation_record(
        "file_reload_addon_active",
        lambda: {
            "result": list(bpy.ops.wm.open_mainfile(filepath=str(temp_save), load_ui=False)),
            "forgeLoadHandlers": resource_counts(addon)["forgeLoadHandlers"],
        },
        failures,
    ))
    settings = bpy.context.scene.daf_settings

    preview_cycles = 50 if args.stress else 5
    before_cycles = resource_counts(addon)

    def preview_clear_cycle():
        deformation, _active_settings = require_active_stamp(addon)
        deformation.preview_service.run_now(bpy.context, quality="FAST")
        deformation.preview_service.clear(bpy.context)
        return None

    operations.append(operation_record("fifty_preview_clear_cycles", preview_clear_cycle, failures, iterations=preview_cycles))
    after_cycles = resource_counts(addon)
    plateau_probe_cycles = 20 if args.stress else 0
    for _index in range(plateau_probe_cycles):
        preview_clear_cycle()
    after_plateau_probe = resource_counts(addon)

    switch_cycles = 20 if args.stress else 4
    operations.append(operation_record("twenty_region_key_switches", lambda: (switch_regions(), switch_keys()), failures, iterations=switch_cycles))
    final_cycles = 10 if args.stress else 1
    operations.append(operation_record("ten_final_gore_rebuilds", gore_rebuild, failures, iterations=final_cycles))

    final = resource_counts(addon)
    preview_growth = numeric_growth(before_cycles, after_cycles)
    resource_stability = performance_contract.stable_growth(preview_growth)
    memory_plateau = {"available": False, "pass": None}
    if after_cycles.get("rssBytes") is not None and after_plateau_probe.get("rssBytes") is not None:
        plateau_growth = int(after_plateau_probe["rssBytes"]) - int(after_cycles["rssBytes"])
        tolerance = max(8 * 1024 * 1024, int(after_cycles["rssBytes"] * 0.03))
        memory_plateau = {
            "available": True,
            "beforePreviewCyclesBytes": int(before_cycles["rssBytes"]),
            "afterFiftyCyclesBytes": int(after_cycles["rssBytes"]),
            "afterTwentyWarmProbeCyclesBytes": int(after_plateau_probe["rssBytes"]),
            "warmProbeGrowthBytes": plateau_growth,
            "toleranceBytes": tolerance,
            "pass": plateau_growth <= tolerance,
        }
        if not memory_plateau["pass"]:
            failures.append({
                "operation": "fifty_preview_clear_cycles",
                "type": "MemoryPlateau",
                "message": "RSS continued growing beyond the warm-cache tolerance",
            })
    if not resource_stability["pass"]:
        failures.append({
            "operation": "fifty_preview_clear_cycles",
            "type": "ResourceGrowth",
            "message": "warm preview cycles grew temporary/runtime resources",
            "detail": resource_stability["failures"],
        })
    report = {
        "schema": SCHEMA,
        "blenderVersion": bpy.app.version_string,
        "addonVersion": deformation._version_string(),
        "addonBuild": deformation.DEFORMATION_BUILD_ID,
        "commit": git_commit(args.commit),
        "sourceAsset": {
            "name": Path(args.source).name if args.source else "",
            "sha256": sha256(args.source) if args.source and Path(args.source).is_file() else "",
            "sizeBytes": Path(args.source).stat().st_size if args.source and Path(args.source).is_file() else 0,
        },
        "fixture": Path(bpy.data.filepath).name if bpy.data.filepath else "<unsaved>",
        "stress": bool(args.stress),
        "resourceCounts": {
            "baseline": baseline,
            "beforePreviewCycles": before_cycles,
            "afterPreviewCycles": after_cycles,
            "afterWarmPlateauProbe": after_plateau_probe,
            "final": final,
            "previewCycleGrowth": preview_growth,
            "totalGrowth": numeric_growth(baseline, final),
        },
        "acceptance": {
            "previewCycleResourceStability": resource_stability,
            "previewMemoryPlateau": memory_plateau,
        },
        "operations": operations,
        "failures": failures,
        "elapsedSeconds": round(time.perf_counter() - started, 3),
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("FORGE_PERFORMANCE_RESULT=" + json.dumps({
        "output": str(output),
        "failures": len(failures),
        "operationsPassed": sum(item["status"] == "PASS" for item in operations),
        "operationsSkipped": sum(item["status"] == "SKIP" for item in operations),
        "previewCycleGrowth": report["resourceCounts"]["previewCycleGrowth"],
    }, sort_keys=True))
    addon.unregister()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
