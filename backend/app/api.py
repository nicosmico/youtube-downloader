"""HTTP API routes."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks

from app import APP_ID, __version__
from app.engine import EngineManager, UpdateOutcome
from app.errors import ApiError
from app.runtime import remove_runtime

_UPDATE_REFUSALS = {
    UpdateOutcome.NOT_READY: (409, "engine_not_ready", "El motor de descarga no está listo."),
    UpdateOutcome.BUSY: (409, "engine_busy", "Ya hay una actualización en curso."),
    UpdateOutcome.DEFERRED: (
        409,
        "engine_busy",
        "Hay descargas activas; yt-dlp se actualizará cuando terminen.",
    ),
    UpdateOutcome.UNSUPPORTED: (
        409,
        "engine_external",
        "Los binarios vienen de ENGINE_BIN_DIR y no se actualizan desde la app.",
    ),
}


def build_router(
    *, data_dir: Path, port: int, request_shutdown: Callable[[], None], engine: EngineManager
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {
            "app": APP_ID,
            "version": __version__,
            "engine": engine.info().to_dict(),
            "port": port,
        }

    @router.get("/system/engine")
    def engine_status() -> dict[str, Any]:
        return engine.info().to_dict()

    @router.post("/system/engine/install", status_code=202)
    def engine_install() -> dict[str, Any]:
        """Retry a failed install. No-op when the Engine is ready or already installing."""
        engine.start_install()
        return engine.info().to_dict()

    @router.post("/system/engine/update", status_code=202)
    def engine_update() -> dict[str, Any]:
        outcome = engine.start_update()
        if outcome in _UPDATE_REFUSALS:
            status, code, message = _UPDATE_REFUSALS[outcome]
            raise ApiError(status, code, message)
        return engine.info().to_dict()

    @router.post("/system/shutdown", status_code=202)
    def shutdown(background: BackgroundTasks) -> dict[str, str]:
        remove_runtime(data_dir, only_pid=os.getpid())
        # Runs after the response is sent so the client gets its answer.
        background.add_task(request_shutdown)
        return {"status": "shutting_down"}

    return router
