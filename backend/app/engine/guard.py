"""FastAPI dependency that blocks a route until the Engine is ready (spec: `engine_not_ready`)."""

from __future__ import annotations

from fastapi import Request

from app.engine.manager import EngineManager, EngineStatus
from app.errors import ApiError


def require_engine_ready(request: Request) -> None:
    """Use as `Depends(require_engine_ready)` on routes that need yt-dlp (preview, new jobs)."""
    engine: EngineManager = request.app.state.engine
    info = engine.info()
    if info.status != EngineStatus.READY:
        raise ApiError(
            409,
            "engine_not_ready",
            "El motor de descarga todavía no está listo.",
            {"status": info.status.value, "message": info.message},
        )
