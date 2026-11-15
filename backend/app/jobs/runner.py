"""Runs one DownloadJob: yt-dlp in a staging folder, progress, final move, final status.

Blocking (a whole download): the queue calls it from a worker thread, never from the event loop.
Progress is persisted and published at most once per `flush_interval`; status changes are
immediate.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

from app.engine import EngineManager
from app.engine.io import ProcessError, ProcessHandle, Streamer, stream_process
from app.jobs import failures
from app.jobs.arguments import UnsupportedJob, download_args
from app.jobs.files import (
    FileMover,
    find_staged_file,
    prepare_staging,
    remove_staging,
)
from app.jobs.models import Job, JobStatus
from app.jobs.progress import (
    Progress,
    ProgressTracker,
    is_progress_line,
    starts_processing,
)
from app.jobs.repository import JobRepository

log = logging.getLogger("app.jobs")

FLUSH_INTERVAL_SECONDS = 1.0
STDERR_LINES_KEPT = 200


class JobRunner:
    def __init__(
        self,
        *,
        engine: EngineManager,
        repo: JobRepository,
        mover: FileMover,
        staging_root: Path,
        publish: Callable[[Job], None],
        stream: Streamer = stream_process,
        clock: Callable[[], float] = time.monotonic,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
    ) -> None:
        self._engine = engine
        self._repo = repo
        self._mover = mover
        self._staging_root = staging_root
        self._publish = publish
        self._stream = stream
        self._clock = clock
        self._flush_interval = flush_interval

    def run(self, job: Job, on_handle: Callable[[ProcessHandle], None] | None = None) -> Job:
        """Run an Attempt that is already `downloading`; always ends in a final status."""
        try:
            return self._run(job, on_handle)
        except Exception:
            log.exception("Unexpected error in job %s", job.id)
            return self._fail(job.id, failures.GENERIC)

    def _run(self, job: Job, on_handle: Callable[[ProcessHandle], None] | None) -> Job:
        staging = prepare_staging(self._staging_root, job.id)
        try:
            args = download_args(self._engine, job, staging)
        except UnsupportedJob:
            return self._fail(job.id, failures.UNSUPPORTED)

        attempt = _Attempt(self, job.id)
        try:
            code = self._stream(args, attempt.on_stdout, attempt.on_stderr, on_handle)
        except ProcessError as exc:
            log.warning("job %s: could not start yt-dlp: %s", job.id, exc)
            return self._fail(job.id, failures.GENERIC)
        attempt.flush()

        if code != 0:
            log.warning("job %s: yt-dlp exited with %s: %s", job.id, code, attempt.stderr_tail())
            return self._fail(job.id, failures.describe_failure(attempt.stderr_tail()))
        staged = find_staged_file(staging, attempt.reported_path)
        if staged is None:
            log.warning("job %s: no output file in staging", job.id)
            return self._fail(job.id, failures.FILE_MISSING)
        try:
            final = self._mover.move(staged)
        except OSError:
            log.exception("job %s: could not move %s", job.id, staged)
            return self._fail(job.id, failures.MOVE_FAILED)

        # `completed` only now: the file is already in the Destination.
        remove_staging(self._staging_root, job.id)
        progress = attempt.last_progress
        done = self._repo.update(
            job.id,
            status=JobStatus.COMPLETED.value,
            progress_percent=100.0,
            downloaded_bytes=progress.downloaded_bytes if progress else None,
            total_bytes=(progress.total_bytes if progress else None),
            speed=None,
            eta=None,
            output_path=str(final),
            error=None,
            finished_at=self._repo.now(),
        )
        self._publish(done)
        return done

    def _fail(self, job_id: str, message: str) -> Job:
        remove_staging(self._staging_root, job_id)
        failed = self._repo.update(
            job_id,
            status=JobStatus.FAILED.value,
            speed=None,
            eta=None,
            error=message,
            finished_at=self._repo.now(),
        )
        self._publish(failed)
        return failed


class _Attempt:
    """Output handlers of one yt-dlp run. stdout and stderr arrive on different threads."""

    def __init__(self, runner: JobRunner, job_id: str) -> None:
        self._runner = runner
        self._job_id = job_id
        self._lock = threading.Lock()
        self._tracker = ProgressTracker()
        self._stderr: deque[str] = deque(maxlen=STDERR_LINES_KEPT)
        self._dirty = False
        self._status = JobStatus.DOWNLOADING
        self._last_flush: float | None = None
        self.reported_path: str | None = None
        self.last_progress: Progress | None = None

    def on_stdout(self, line: str) -> None:
        with self._lock:
            if is_progress_line(line):
                progress = self._tracker.feed(line)
                if progress is not None:
                    self.last_progress = progress
                    self._dirty = True
                    self._flush_if_due()
            elif line.strip():
                self.reported_path = line.strip()  # the last one is `after_move:filepath`

    def on_stderr(self, line: str) -> None:
        with self._lock:
            if starts_processing(line):
                if self._status is JobStatus.DOWNLOADING:
                    self._status = JobStatus.PROCESSING
                    self._dirty = True
                    self._flush()
            elif line.strip():
                self._stderr.append(line)

    def stderr_tail(self) -> str:
        with self._lock:
            return "\n".join(self._stderr)

    def flush(self) -> None:
        with self._lock:
            self._flush()

    def _flush_if_due(self) -> None:
        now = self._runner._clock()
        if self._last_flush is None or now - self._last_flush >= self._runner._flush_interval:
            self._flush()

    def _flush(self) -> None:
        if not self._dirty:
            return
        runner = self._runner
        p = self.last_progress
        fields: dict = {"status": self._status.value}
        if p is not None:
            fields.update(
                progress_percent=p.percent,
                downloaded_bytes=p.downloaded_bytes,
                total_bytes=p.total_bytes,
                speed=p.speed,
                eta=p.eta,
            )
        job = runner._repo.update(self._job_id, **fields)
        runner._publish(job)
        self._dirty = False
        self._last_flush = runner._clock()
