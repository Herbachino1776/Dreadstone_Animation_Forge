"""Single-owner, debounced, generation-token live preview lifecycle."""

from __future__ import annotations

import time
from contextlib import contextmanager

import bpy
from bpy.app.handlers import persistent

from . import diagnostics
from .models import PreviewQuality, PreviewStatus


QUIET_INTERVAL_SECONDS = 0.2
_EXECUTOR = None
_CLEARER = None
_CACHE_CLEARER = None
_TIMER_REGISTERED = False
_HANDLERS_INSTALLED = False
_GENERATION = 0
_REQUESTED_AT = 0.0
_BUILDING_GENERATION = -1
_LAST_RESULT = {}
_LAST_ERROR = ""
_SUSPEND_DEPTH = 0


def configure(*, executor=None, clearer=None, cache_clearer=None):
    global _EXECUTOR, _CLEARER, _CACHE_CLEARER
    if executor is not None:
        _EXECUTOR = executor
    if clearer is not None:
        _CLEARER = clearer
    if cache_clearer is not None:
        _CACHE_CLEARER = cache_clearer


def _settings(context=None):
    scene = getattr(context, "scene", None) if context is not None else getattr(bpy.context, "scene", None)
    return getattr(scene, "daf_settings", None)


def _set_status(settings, status, *, elapsed_ms=None, affected=None, estimated=None, final=None, message=None):
    if settings is None:
        return
    settings.deformation_preview_status = str(getattr(status, "value", status))
    if elapsed_ms is not None:
        settings.deformation_preview_elapsed_ms = max(0.0, float(elapsed_ms))
    if affected is not None:
        settings.deformation_preview_affected_vertices = max(0, int(affected))
    if estimated is not None:
        settings.deformation_preview_estimated_gore_triangles = max(0, int(estimated))
    if final is not None:
        settings.deformation_preview_final_gore_triangles = max(0, int(final))
    if message is not None:
        settings.deformation_preview_message = str(message)[:512]


def request_refresh(context=None, reason="property update"):
    """Mark dirty and schedule one timer; never evaluate geometry synchronously."""

    global _GENERATION, _REQUESTED_AT, _TIMER_REGISTERED
    if _SUSPEND_DEPTH:
        return _GENERATION
    settings = _settings(context)
    if settings is None:
        return 0
    if not bool(getattr(settings, "deformation_auto_preview", True)):
        clear(context, disabled=True)
        return _GENERATION
    _GENERATION += 1
    _REQUESTED_AT = time.monotonic()
    settings.deformation_preview_generation = _GENERATION
    _set_status(settings, PreviewStatus.DIRTY, message=reason)
    quality = str(getattr(settings, "deformation_preview_quality", PreviewQuality.FAST.value))
    if not bool(getattr(settings, "deformation_live_preview", True)) or quality == PreviewQuality.OFF.value:
        clear(context, disabled=True)
        return _GENERATION
    if not _TIMER_REGISTERED:
        bpy.app.timers.register(_timer_callback, first_interval=QUIET_INTERVAL_SECONDS)
        _TIMER_REGISTERED = True
    return _GENERATION


@contextmanager
def suspend_updates():
    global _SUSPEND_DEPTH
    _SUSPEND_DEPTH += 1
    try:
        yield
    finally:
        _SUSPEND_DEPTH = max(0, _SUSPEND_DEPTH - 1)


def updates_suspended():
    return bool(_SUSPEND_DEPTH)


def _timer_callback():
    global _TIMER_REGISTERED
    quiet_for = time.monotonic() - _REQUESTED_AT
    if quiet_for < QUIET_INTERVAL_SECONDS:
        return max(0.01, QUIET_INTERVAL_SECONDS - quiet_for)
    _TIMER_REGISTERED = False
    settings = _settings()
    if settings is None:
        return None
    if not bool(getattr(settings, "deformation_live_preview", True)):
        clear(bpy.context, disabled=True)
        return None
    requested_quality = str(getattr(settings, "deformation_preview_quality", PreviewQuality.FAST.value))
    quality = PreviewQuality.BALANCED.value if requested_quality == PreviewQuality.FINAL.value else requested_quality
    if quality == PreviewQuality.OFF.value:
        clear(bpy.context, disabled=True)
        return None
    run_now(bpy.context, quality=quality, generation=_GENERATION)
    return None


def run_now(context=None, *, quality=None, generation=None):
    global _BUILDING_GENERATION, _LAST_RESULT, _LAST_ERROR
    context = context or bpy.context
    if generation is None:
        cancel_timer()
    settings = _settings(context)
    if settings is None:
        return {}
    resolved_quality = str(quality or getattr(settings, "deformation_preview_quality", PreviewQuality.FAST.value))
    if resolved_quality == PreviewQuality.OFF.value:
        clear(context)
        return {}
    token = _GENERATION if generation is None else int(generation)
    _BUILDING_GENERATION = token
    _set_status(settings, PreviewStatus.BUILDING, message=f"Building {resolved_quality.title()} preview")
    started = time.perf_counter()
    try:
        if not callable(_EXECUTOR):
            raise RuntimeError("Forge preview executor is not configured.")
        result = dict(_EXECUTOR(context, resolved_quality, token) or {})
        if token != _GENERATION:
            if callable(_CLEARER):
                _CLEARER(context, stale_only=True)
            _set_status(settings, PreviewStatus.DIRTY, message="Stale preview discarded")
            return {"stale": True, "generation": token}
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        result.update({"generation": token, "quality": resolved_quality, "elapsedMs": elapsed_ms})
        _LAST_RESULT = result
        _LAST_ERROR = ""
        _set_status(
            settings,
            PreviewStatus.READY,
            elapsed_ms=elapsed_ms,
            affected=result.get("affectedVertexCount", result.get("vertexCount", 0)),
            estimated=result.get("estimatedGoreTriangleCount", 0),
            final=result.get("finalGoreTriangleCount", result.get("raisedTriangleCount", 0)),
            message=result.get("message", f"{resolved_quality.title()} preview ready"),
        )
        diagnostics.record_operation(f"preview.{resolved_quality.lower()}", elapsed_ms / 1000.0)
        return result
    except Exception as exc:
        elapsed = time.perf_counter() - started
        _LAST_ERROR = str(exc)
        diagnostics.record_operation(f"preview.{resolved_quality.lower()}", elapsed, "FAIL", str(exc))
        diagnostics.record_exception("managed preview", exc)
        try:
            if callable(_CLEARER):
                _CLEARER(context, failed=True)
        finally:
            _set_status(settings, PreviewStatus.FAILED, elapsed_ms=elapsed * 1000.0, message=str(exc))
        return {"failed": True, "generation": token, "error": str(exc)}
    finally:
        _BUILDING_GENERATION = -1


def clear(context=None, **flags):
    global _LAST_RESULT, _LAST_ERROR
    cancel_timer()
    if callable(_CLEARER):
        _CLEARER(context or bpy.context, **flags)
    _LAST_RESULT = {}
    _LAST_ERROR = ""
    _set_status(_settings(context), PreviewStatus.CLEAN, elapsed_ms=0.0, affected=0, estimated=0, final=0, message="Preview cleared")


def cancel_timer():
    global _TIMER_REGISTERED
    try:
        if bpy.app.timers.is_registered(_timer_callback):
            bpy.app.timers.unregister(_timer_callback)
    except Exception:
        pass
    _TIMER_REGISTERED = False


@persistent
def _load_post(_unused):
    global _GENERATION, _LAST_RESULT, _LAST_ERROR
    cancel_timer()
    _GENERATION += 1
    _LAST_RESULT = {}
    _LAST_ERROR = ""
    if callable(_CACHE_CLEARER):
        _CACHE_CLEARER("file load")


def install_handlers():
    global _HANDLERS_INSTALLED
    handlers = bpy.app.handlers.load_post
    duplicates = [handler for handler in handlers if getattr(handler, "__name__", "") == _load_post.__name__ and getattr(handler, "__module__", "") == _load_post.__module__]
    for handler in duplicates:
        handlers.remove(handler)
    handlers.append(_load_post)
    _HANDLERS_INSTALLED = True


def remove_handlers():
    global _HANDLERS_INSTALLED
    handlers = bpy.app.handlers.load_post
    for handler in tuple(handlers):
        if getattr(handler, "__name__", "") == _load_post.__name__ and getattr(handler, "__module__", "") == _load_post.__module__:
            handlers.remove(handler)
    _HANDLERS_INSTALLED = False


def shutdown():
    cancel_timer()
    remove_handlers()
    if callable(_CACHE_CLEARER):
        _CACHE_CLEARER("unregister")


def state():
    settings = _settings()
    return {
        "generation": _GENERATION,
        "buildingGeneration": _BUILDING_GENERATION,
        "timerRegistered": bool(_TIMER_REGISTERED),
        "handlersInstalled": bool(_HANDLERS_INSTALLED),
        "status": str(getattr(settings, "deformation_preview_status", PreviewStatus.CLEAN.value)) if settings else PreviewStatus.CLEAN.value,
        "quality": str(getattr(settings, "deformation_preview_quality", PreviewQuality.FAST.value)) if settings else PreviewQuality.FAST.value,
        "lastResult": dict(_LAST_RESULT),
        "lastError": _LAST_ERROR,
    }
