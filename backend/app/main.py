"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from fastapi import FastAPI

from app import __version__
from app.api import build_router
from app.engine import EngineInfo, EngineManager, run_periodic
from app.errors import install_error_handlers
from app.events import Event, EventBroadcaster, build_events_router
from app.paths import static_dir as default_static_dir
from app.security import LocalSecurityMiddleware
from app.spa import mount_spa


def create_app(
    *,
    data_dir: Path,
    port: int,
    request_shutdown: Callable[[], None] = lambda: None,
    static_dir: Path | None = None,
    engine: EngineManager | None = None,
    engine_bin_dir: Path | None = None,
    broadcaster: EventBroadcaster | None = None,
    heartbeat_seconds: float = 15.0,
) -> FastAPI:
    engine = engine or EngineManager(data_dir=data_dir, bin_dir_override=engine_bin_dir)
    broadcaster = broadcaster or EventBroadcaster()

    def publish_engine(info: EngineInfo) -> None:
        broadcaster.publish("engine.updated", info.to_dict())

    engine.subscribe(publish_engine)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        broadcaster.bind_loop(asyncio.get_running_loop())
        engine.start()  # installs in the background if binaries are missing
        scheduler = asyncio.create_task(run_periodic(engine))
        try:
            yield
        finally:
            scheduler.cancel()
            broadcaster.close()

    app = FastAPI(
        title="youtube-downloader",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.broadcaster = broadcaster
    install_error_handlers(app)
    app.add_middleware(LocalSecurityMiddleware, port=port)
    app.include_router(
        build_router(data_dir=data_dir, port=port, request_shutdown=request_shutdown, engine=engine)
    )
    app.include_router(
        build_events_router(
            broadcaster,
            initial_events=lambda: [Event("engine.updated", engine.info().to_dict())],
            heartbeat=heartbeat_seconds,
        )
    )
    mount_spa(app, static_dir or default_static_dir())
    return app
