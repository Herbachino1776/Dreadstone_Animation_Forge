"""Low-noise timing, exception, lifecycle, and support-report diagnostics."""

from __future__ import annotations

import json
import time
import traceback
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import bpy


_OPERATIONS = deque(maxlen=10)
_LAST_EXCEPTION = {}
_CACHE_PROVIDER = None
_PREVIEW_PROVIDER = None
_CACHED_SUMMARY = {}


def configure(*, cache_provider=None, preview_provider=None):
    global _CACHE_PROVIDER, _PREVIEW_PROVIDER
    if cache_provider is not None:
        _CACHE_PROVIDER = cache_provider
    if preview_provider is not None:
        _PREVIEW_PROVIDER = preview_provider


def record_operation(name, elapsed_seconds, status="PASS", detail=""):
    _OPERATIONS.append({
        "name": str(name),
        "elapsedMs": round(float(elapsed_seconds) * 1000.0, 3),
        "status": str(status),
        "detail": str(detail)[:400],
        "utc": datetime.now(timezone.utc).isoformat(),
    })
    if _CACHED_SUMMARY:
        _CACHED_SUMMARY["lastOperations"] = list(_OPERATIONS)


def record_exception(stage, exc):
    global _LAST_EXCEPTION
    _LAST_EXCEPTION = {
        "stage": str(stage),
        "type": type(exc).__name__,
        "message": str(exc)[:1000],
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:],
        "utc": datetime.now(timezone.utc).isoformat(),
    }
    if _CACHED_SUMMARY:
        _CACHED_SUMMARY["lastException"] = dict(_LAST_EXCEPTION)


@contextmanager
def timed(name):
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        record_operation(name, time.perf_counter() - started, "FAIL", str(exc))
        record_exception(name, exc)
        raise
    else:
        record_operation(name, time.perf_counter() - started)


def _handler_counts():
    result = {}
    handlers = getattr(bpy.app, "handlers", None)
    for name in ("load_post", "depsgraph_update_post", "save_post", "frame_change_post"):
        values = getattr(handlers, name, ()) if handlers is not None else ()
        result[name] = len(tuple(values))
    return result


def _generated_gore_totals():
    objects = [obj for obj in bpy.data.objects if obj.get("dsb_generated_role", "") == "raised_gore"]
    return {
        "objects": len(objects),
        "triangles": sum(int(obj.get("dsb_gore_triangle_count", 0)) for obj in objects),
    }


def _active_context():
    settings = getattr(getattr(bpy.context, "scene", None), "daf_settings", None)
    if settings is None:
        return {}
    raw_capture = str(getattr(settings, "deformation_capture_json", "") or "")
    capture = {}
    if raw_capture:
        try:
            decoded = json.loads(raw_capture)
            capture = decoded if isinstance(decoded, dict) else {}
        except Exception:
            capture = {}
    return {
        "region": str(getattr(settings, "deformation_region", "")),
        "key": str(getattr(settings, "deformation_active_key", "")),
        "captureStatus": "CAPTURED" if capture else "EMPTY",
        "captureFaceCount": len(capture.get("faceIndices", ())),
        "captureVertexCount": len(capture.get("vertexIndices", ())),
        "stamp": str(getattr(settings, "deformation_active_stamp_id", "")),
        "compoundEvent": str(getattr(settings, "compound_active_event_id", "")),
    }


def _validation_states():
    settings = getattr(getattr(bpy.context, "scene", None), "daf_settings", None)
    if settings is None:
        return {}
    return {
        "sourceReadiness": str(getattr(settings, "source_readiness_contract_status", "NOT ANALYZED")),
        "authoring": str(getattr(settings, "last_damage_authoring_validation", "NOT VALIDATED")),
        "export": str(getattr(settings, "last_damage_export_validation", "NOT VALIDATED")),
        "deformation": str(getattr(settings, "last_deformation_validation", "NOT VALIDATED")),
    }


def snapshot(version="", build=""):
    cache_counts = _CACHE_PROVIDER() if callable(_CACHE_PROVIDER) else {}
    preview = _PREVIEW_PROVIDER() if callable(_PREVIEW_PROVIDER) else {}
    return {
        "schema": "dreadstone.forge_diagnostics.v1",
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "forgeVersion": str(version),
        "forgeBuild": str(build),
        "blenderVersion": bpy.app.version_string,
        "file": Path(bpy.data.filepath).name if bpy.data.filepath else "<unsaved>",
        "datablocks": {
            "objects": len(bpy.data.objects),
            "meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials),
            "actions": len(bpy.data.actions),
            "collections": len(bpy.data.collections),
            "shapeKeys": sum(len(obj.data.shape_keys.key_blocks) for obj in bpy.data.objects if obj.type == 'MESH' and obj.data.shape_keys),
        },
        "handlers": _handler_counts(),
        "timers": {"forgePreviewRegistered": bool(preview.get("timerRegistered", False))},
        "caches": cache_counts,
        "preview": preview,
        "generatedGore": _generated_gore_totals(),
        "activeContext": _active_context(),
        "validationStates": _validation_states(),
        "lastOperations": list(_OPERATIONS),
        "lastException": dict(_LAST_EXCEPTION),
    }


def refresh_summary(version="", build=""):
    global _CACHED_SUMMARY
    _CACHED_SUMMARY = snapshot(version, build)
    return dict(_CACHED_SUMMARY)


def cached_summary():
    return dict(_CACHED_SUMMARY)


def clear_cached_summary():
    _CACHED_SUMMARY.clear()


def markdown(report):
    blocks = [
        "# Dreadstone Animation Forge Diagnostic Report",
        "",
        f"- Forge: `{report.get('forgeVersion', '')}` / `{report.get('forgeBuild', '')}`",
        f"- Blender: `{report.get('blenderVersion', '')}`",
        f"- File: `{report.get('file', '')}` (filename only; no proprietary mesh payload)",
        f"- Generated: `{report.get('generatedUtc', '')}`",
        "",
        "## Datablocks",
        "",
        "```json",
        json.dumps(report.get("datablocks", {}), indent=2, sort_keys=True),
        "```",
        "",
        "## Lifecycle and caches",
        "",
        "```json",
        json.dumps({key: report.get(key, {}) for key in ("handlers", "timers", "caches", "preview", "generatedGore", "activeContext", "validationStates")}, indent=2, sort_keys=True),
        "```",
        "",
        "## Recent operations and last exception",
        "",
        "```json",
        json.dumps({"lastOperations": report.get("lastOperations", []), "lastException": report.get("lastException", {})}, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(blocks) + "\n"


def write_reports(directory, version="", build="", *, blender_text=True):
    target = Path(bpy.path.abspath(str(directory))).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    report = refresh_summary(version, build)
    json_path = target / "Dreadstone_Forge_Diagnostics.json"
    markdown_path = target / "Dreadstone_Forge_Diagnostics.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rendered = markdown(report)
    markdown_path.write_text(rendered, encoding="utf-8")
    if blender_text:
        text = bpy.data.texts.get("DSB_Forge_Diagnostics.md") or bpy.data.texts.new("DSB_Forge_Diagnostics.md")
        text.clear()
        text.write(rendered)
    return {"json": str(json_path), "markdown": str(markdown_path), "report": report}
