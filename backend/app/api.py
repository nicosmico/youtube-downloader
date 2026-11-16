"""HTTP API routes."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from app import APP_ID, __version__
from app.engine import EngineManager, UpdateOutcome
from app.engine.guard import require_engine_ready
from app.errors import ApiError
from app.logs import MAX_LINES, read_log_tail
from app.opener import FolderOpener, OpenUnavailable
from app.preview import PreviewFailure, PreviewService
from app.runtime import remove_runtime

_UPDATE_REFUSALS = {
    UpdateOutcome.NOT_READY: (409, "engine_not_ready", "El motor de descarga no está listo."),
    UpdateOutcome.BUSY: (409, "engine_busy", "Ya hay una actualización en curso o pendiente."),
    UpdateOutcome.UNSUPPORTED: (
        409,
        "engine_external",
        "Los binarios vienen de ENGINE_BIN_DIR y no se actualizan desde la app.",
    ),
}


class PreviewRequest(BaseModel):
    url: str


def build_router(
    *,
    data_dir: Path,
    port: int,
    request_shutdown: Callable[[], None],
    engine: EngineManager,
    previews: PreviewService,
    download_dir: Path,
    open_folder: FolderOpener,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {
            "app": APP_ID,
            "version": __version__,
            "engine": engine.info().to_dict(),
            "port": port,
            "platform": sys.platform,
        }

    @router.get("/logs")
    def logs(
        lines: int = Query(default=MAX_LINES, ge=1, le=MAX_LINES),
        requests: bool = False,
    ) -> dict[str, Any]:
        """Tail of `app.log`, read-only. Plain `def`: it runs in a worker thread, off the loop.
        HTTP requests (`uvicorn.access`) are left out unless `requests=true`."""
        return {"lines": read_log_tail(data_dir, lines, requests)}

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
        """202 also when downloads are active: the update stays pending (`updatePending`)."""
        outcome = engine.start_update()
        if outcome in _UPDATE_REFUSALS:
            status, code, message = _UPDATE_REFUSALS[outcome]
            raise ApiError(status, code, message)
        return engine.info().to_dict()

    @router.post("/preview", dependencies=[Depends(require_engine_ready)])
    def preview(body: PreviewRequest) -> dict[str, Any]:
        """Plain `def`: FastAPI runs it in a worker thread, so a slow yt-dlp never blocks."""
        try:
            return previews.preview(body.url)
        except PreviewFailure as exc:
            f = exc.failure
            raise ApiError(f.status, f.code, f.message) from None

    @router.post("/system/open-downloads")
    def open_downloads() -> dict[str, str]:
        """Host action: the dev container (Linux) cannot open Finder, so it answers 501."""
        try:
            download_dir.mkdir(parents=True, exist_ok=True)
            open_folder(download_dir)
        except OpenUnavailable:
            raise ApiError(
                501,
                "open_unavailable",
                "Esta acción solo funciona en la aplicación de escritorio (macOS o Windows).",
            ) from None
        except OSError:
            raise ApiError(
                500, "open_failed", "No se pudo abrir la carpeta de descargas."
            ) from None
        return {"status": "opened"}

    @router.post("/system/shutdown", status_code=202)
    def shutdown(background: BackgroundTasks) -> dict[str, str]:
        remove_runtime(data_dir, only_pid=os.getpid())
        # Runs after the response is sent so the client gets its answer.
        background.add_task(request_shutdown)
        return {"status": "shutting_down"}

    return router
