"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI

from app import __version__
from app.api import build_router
from app.errors import install_error_handlers
from app.paths import static_dir as default_static_dir
from app.security import LocalSecurityMiddleware
from app.spa import mount_spa


def create_app(
    *,
    data_dir: Path,
    port: int,
    request_shutdown: Callable[[], None] = lambda: None,
    static_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(
        title="youtube-downloader",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    install_error_handlers(app)
    app.add_middleware(LocalSecurityMiddleware, port=port)
    app.include_router(
        build_router(data_dir=data_dir, port=port, request_shutdown=request_shutdown)
    )
    mount_spa(app, static_dir or default_static_dir())
    return app
