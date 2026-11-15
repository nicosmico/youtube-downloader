"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from fastapi import FastAPI

from app import __version__
from app.api import build_router
from app.db import Database
from app.engine import EngineInfo, EngineManager, run_periodic
from app.engine.io import Runner, Streamer, run_process, stream_process
from app.errors import install_error_handlers
from app.events import Event, EventBroadcaster, build_events_router
from app.jobs import (
    FileMover,
    JobEvents,
    JobQueue,
    JobRepository,
    JobRunner,
    clean_orphans,
    staging_root,
)
from app.jobs.api import build_jobs_router
from app.jobs.queue import start_thread
from app.opener import FolderOpener, open_folder
from app.paths import static_dir as default_static_dir
from app.preview import PreviewService
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
    ytdlp_runner: Runner = run_process,
    download_dir: Path | None = None,
    streamer: Streamer = stream_process,
    open_folder_in_host: FolderOpener = open_folder,
    clock: Callable[[], float] = time.monotonic,
    spawn_job: Callable[[Callable[[], None]], None] = start_thread,
    rename: Callable[[Path, Path], None] = os.rename,
    broadcaster: EventBroadcaster | None = None,
    heartbeat_seconds: float = 15.0,
) -> FastAPI:
    engine = engine or EngineManager(data_dir=data_dir, bin_dir_override=engine_bin_dir)
    broadcaster = broadcaster or EventBroadcaster()
    download_dir = download_dir or Path.home() / "Downloads"

    database = Database(data_dir / "db.sqlite3")
    database.migrate()
    repo = JobRepository(database)
    staging = staging_root(data_dir)
    queue = JobQueue(
        repo=repo,
        runner=JobRunner(
            engine=engine,
            repo=repo,
            mover=FileMover(download_dir, rename=rename),
            staging_root=staging,
            publish=JobEvents(broadcaster).job_updated,
            stream=streamer,
            clock=clock,
        ),
        events=JobEvents(broadcaster),
        spawn=spawn_job,
    )

    # The yt-dlp update and the Queue coordinate (ADR-0002): see EngineManager.
    engine.hold_queue = queue.hold
    engine.release_queue = queue.release
    engine.can_update = queue.is_idle
    queue.on_drained = engine.apply_pending_update

    def publish_engine(info: EngineInfo) -> None:
        broadcaster.publish("engine.updated", info.to_dict())

    engine.subscribe(publish_engine)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        broadcaster.bind_loop(asyncio.get_running_loop())
        engine.start()  # installs in the background if binaries are missing
        clean_orphans(staging)  # nothing runs yet: every staging folder is a leftover
        queue.start()  # active jobs of the last run become `interrupted`; queued ones resume
        scheduler = asyncio.create_task(run_periodic(engine))
        try:
            yield
        finally:
            scheduler.cancel()
            # Orderly stop: terminate yt-dlp, mark the active jobs `interrupted`, clean staging.
            await asyncio.to_thread(queue.shutdown)
            clean_orphans(staging)
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
    app.state.queue = queue
    app.state.jobs = repo
    install_error_handlers(app)
    app.add_middleware(LocalSecurityMiddleware, port=port)
    app.include_router(
        build_router(
            data_dir=data_dir,
            port=port,
            request_shutdown=request_shutdown,
            engine=engine,
            previews=PreviewService(engine, ytdlp_runner),
            download_dir=download_dir,
            open_folder=open_folder_in_host,
        )
    )
    app.include_router(build_jobs_router(queue=queue, repo=repo))
    app.include_router(
        build_events_router(
            broadcaster,
            initial_events=lambda: [
                Event("engine.updated", engine.info().to_dict()),
                Event("queue.updated", queue.counts()),
            ],
            heartbeat=heartbeat_seconds,
        )
    )
    mount_spa(app, static_dir or default_static_dir())
    return app
