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
from app.engine import EngineInfo, EngineManager, EngineStatus, run_periodic
from app.engine.io import Runner, Streamer, run_process, stream_process
from app.errors import install_error_handlers
from app.events import Event, EventBroadcaster, build_events_router
from app.idle import IdleMonitor
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
from app.opener import FileRevealer, FolderOpener, open_folder, reveal_file
from app.paths import static_dir as default_static_dir
from app.preview import PreviewService
from app.runtime import remove_runtime
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
    reveal_in_host: FileRevealer = reveal_file,
    clock: Callable[[], float] = time.monotonic,
    spawn_job: Callable[[Callable[[], None]], None] = start_thread,
    rename: Callable[[Path, Path], None] = os.rename,
    broadcaster: EventBroadcaster | None = None,
    heartbeat_seconds: float = 15.0,
    idle_shutdown_seconds: float = 0.0,
    idle_clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    """`idle_shutdown_seconds` > 0 turns Idle Shutdown on (the Launcher passes the setting)."""
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

    def engine_busy() -> bool:
        info = engine.info()
        return info.status is EngineStatus.INSTALLING or info.updating or info.update_pending

    def shutdown_idle() -> None:
        broadcaster.publish("shutdown", {"reason": "idle"})
        remove_runtime(data_dir, only_pid=os.getpid())  # a new launch must not reuse a dying app
        request_shutdown()

    def shutdown_by_user() -> None:
        # Every open tab learns the app closed, not only the one whose button was pressed.
        broadcaster.publish("shutdown", {"reason": "user"})
        request_shutdown()

    idle: IdleMonitor | None = None
    if idle_shutdown_seconds > 0:
        idle = IdleMonitor(
            timeout=idle_shutdown_seconds,
            clients=lambda: broadcaster.client_count,
            busy=lambda: queue.has_work() or engine_busy(),
            on_idle=shutdown_idle,
            clock=idle_clock,
        )
        broadcaster.add_activity_listener(idle.touch)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        broadcaster.bind_loop(asyncio.get_running_loop())
        engine.start()  # installs in the background if binaries are missing
        clean_orphans(staging)  # nothing runs yet: every staging folder is a leftover
        queue.start()  # active jobs of the last run become `interrupted`; queued ones resume
        scheduler = asyncio.create_task(run_periodic(engine))
        watcher = asyncio.create_task(idle.run()) if idle else None
        try:
            yield
        finally:
            scheduler.cancel()
            if watcher:
                watcher.cancel()
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
    app.state.idle = idle
    install_error_handlers(app)
    app.add_middleware(LocalSecurityMiddleware, port=port)
    app.include_router(
        build_router(
            data_dir=data_dir,
            port=port,
            request_shutdown=shutdown_by_user,
            engine=engine,
            previews=PreviewService(engine, ytdlp_runner),
            download_dir=download_dir,
            open_folder=open_folder_in_host,
        )
    )
    app.include_router(build_jobs_router(queue=queue, repo=repo, reveal=reveal_in_host))
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
