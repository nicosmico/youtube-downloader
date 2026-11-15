"""HTTP API routes."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks

from app import APP_ID, __version__
from app.runtime import remove_runtime


def build_router(*, data_dir: Path, port: int, request_shutdown: Callable[[], None]) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, Any]:
        # Engine status is a placeholder until the Engine Manager exists (ticket 03).
        return {
            "app": APP_ID,
            "version": __version__,
            "engine": {"status": "missing"},
            "port": port,
        }

    @router.post("/system/shutdown", status_code=202)
    def shutdown(background: BackgroundTasks) -> dict[str, str]:
        remove_runtime(data_dir, only_pid=os.getpid())
        # Runs after the response is sent so the client gets its answer.
        background.add_task(request_shutdown)
        return {"status": "shutting_down"}

    return router
