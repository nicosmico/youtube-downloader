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
    DownloadDirMissing,
    FileMover,
    find_staged_file,
    prepare_staging,
    remove_staging,
)
from app.jobs.folders import numbered_name, padding_width
from app.jobs.models import Job, JobStatus
from app.jobs.progress import (
    Progress,
    ProgressTracker,
    is_progress_line,
    is_total_line,
    starts_processing,
)
from app.jobs.repository import JobRepository

log = logging.getLogger("app.jobs")

FLUSH_INTERVAL_SECONDS = 1.0
STDERR_LINES_KEPT = 200
# "Ver detalle": the last lines of yt-dlp output (stdout and stderr, without progress lines) of
# an Attempt, kept only if it fails. Long lines are cut so the stored text stays small.
OUTPUT_LINES_KEPT = 200
OUTPUT_LINE_MAX = 2000


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

    def run(
        self,
        job: Job,
        on_handle: Callable[[ProcessHandle], None] | None = None,
        interrupted: Callable[[], bool] = lambda: False,
        canceled: Callable[[], bool] = lambda: False,
    ) -> Job:
        """Run an Attempt that is already `downloading`; always ends in a final status.

        `interrupted()` tells that the app is shutting down: a process that dies after that is an
        `interrupted` job, not a `failed` one. `canceled()` tells that the user cancelled: a
        process that dies after that is a `canceled` job. A process that still exits 0 completed
        its download first, so the job completes (the cancel lost the race).
        """
        try:
            return self._run(job, on_handle, interrupted, canceled)
        except Exception:
            log.exception("Unexpected error in job %s", job.id)
            return self._fail(job.id, failures.GENERIC)

    def _run(
        self,
        job: Job,
        on_handle: Callable[[ProcessHandle], None] | None,
        interrupted: Callable[[], bool],
        canceled: Callable[[], bool],
    ) -> Job:
        staging = prepare_staging(self._staging_root, job.id)
        if canceled():  # cancelled before the process existed
            return self._cancel(job.id)
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

        if code != 0 and canceled():
            return self._cancel(job.id)
        if code != 0 and interrupted():
            return self._interrupt(job.id)
        if code != 0:
            log.warning("job %s: yt-dlp exited with %s: %s", job.id, code, attempt.stderr_tail())
            return self._fail(
                job.id,
                failures.describe_failure(attempt.stderr_tail()),
                output=(job.attempt, attempt.output()),
            )
        staged = find_staged_file(staging, attempt.reported_path)
        if staged is None:
            log.warning("job %s: no output file in staging", job.id)
            return self._fail(job.id, failures.FILE_MISSING, output=(job.attempt, attempt.output()))
        try:
            subdir, name = self._destination(job, staged)
            base = Path(job.download_dir) if job.download_dir else None
            final = self._mover.move(staged, subdir, name, base)
        except DownloadDirMissing:
            log.warning("job %s: the download folder %s is not available", job.id, job.download_dir)
            return self._fail(
                job.id, failures.DOWNLOAD_DIR_UNAVAILABLE, output=(job.attempt, attempt.output())
            )
        except OSError:
            log.exception("job %s: could not move %s", job.id, staged)
            return self._fail(job.id, failures.MOVE_FAILED, output=(job.attempt, attempt.output()))

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

    def _destination(self, job: Job, staged: Path) -> tuple[str | None, str]:
        """A single video goes to the Destination as yt-dlp named it; an Entry of a playlist goes
        to the folder of its Batch as `<NN> - <name>` (spec: "Archivos")."""
        batch = self._repo.get_batch(job.batch_id) if job.batch_id else None
        if batch is None or job.playlist_index is None:
            return None, staged.name
        width = padding_width(max(batch.entry_count, self._repo.highest_index(batch.id)))
        return batch.folder_name, numbered_name(job.playlist_index, staged.name, width)

    def _cancel(self, job_id: str) -> Job:
        remove_staging(self._staging_root, job_id)
        job = self._repo.update(
            job_id,
            status=JobStatus.CANCELED.value,
            speed=None,
            eta=None,
            error=None,
            finished_at=self._repo.now(),
        )
        self._publish(job)
        return job

    def _interrupt(self, job_id: str) -> Job:
        remove_staging(self._staging_root, job_id)
        job = self._repo.update(
            job_id,
            status=JobStatus.INTERRUPTED.value,
            speed=None,
            eta=None,
            error=failures.INTERRUPTED,
            finished_at=self._repo.now(),
        )
        self._publish(job)
        return job

    def _fail(self, job_id: str, message: str, output: tuple[int, list[str]] | None = None) -> Job:
        remove_staging(self._staging_root, job_id)
        if output is not None and output[1]:
            # Before the status change: whoever sees `failed` can already ask for the detail.
            self._repo.save_output(job_id, *output)
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
        self._output: deque[str] = deque(maxlen=OUTPUT_LINES_KEPT)
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
            elif is_total_line(line):
                self._tracker.set_expected(line)
            elif line.strip():
                self.reported_path = line.strip()  # the last one is `after_move:filepath`
                self._keep(line)

    def on_stderr(self, line: str) -> None:
        with self._lock:
            if starts_processing(line):
                if self._status is JobStatus.DOWNLOADING:
                    self._status = JobStatus.PROCESSING
                    self._dirty = True
                    self._flush()
            elif line.strip():
                self._stderr.append(line)
                self._keep(line)

    def _keep(self, line: str) -> None:
        self._output.append(line if len(line) <= OUTPUT_LINE_MAX else line[:OUTPUT_LINE_MAX] + "…")

    def output(self) -> list[str]:
        with self._lock:
            return list(self._output)

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
