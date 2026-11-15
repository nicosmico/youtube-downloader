"""The Queue: takes `queued` jobs FIFO by `created_at` and runs at most `limit` at a time."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from app.engine.io import ProcessHandle
from app.jobs.events import JobEvents
from app.jobs.models import Job, JobStatus
from app.jobs.repository import JobRepository
from app.jobs.runner import JobRunner

log = logging.getLogger("app.jobs")

MAX_CONCURRENT_JOBS = 2


def start_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="download", daemon=True).start()


class JobQueue:
    def __init__(
        self,
        *,
        repo: JobRepository,
        runner: JobRunner,
        events: JobEvents,
        limit: int = MAX_CONCURRENT_JOBS,
        spawn: Callable[[Callable[[], None]], None] = start_thread,
    ) -> None:
        self._repo = repo
        self._runner = runner
        self._events = events
        self._limit = limit
        self._spawn = spawn
        self._lock = threading.Lock()
        # job id -> process handle (None until the process starts). Ticket 10 cancels through it.
        self._active: dict[str, ProcessHandle | None] = {}
        self._closed = False

    def enqueue(self, **fields) -> Job:
        """Persist a new `queued` job and start it if a slot is free."""
        job = self._repo.create(**fields)
        self._events.job_updated(job)
        self._publish_counts()
        self.kick()
        return job

    def kick(self) -> None:
        """Start as many queued jobs as there are free slots."""
        with self._lock:
            if self._closed:
                return
            free = self._limit - len(self._active)
            claimed = self._repo.claim_queued(free) if free > 0 else []
            for job in claimed:
                self._active[job.id] = None
        if not claimed:
            return
        for job in claimed:
            self._events.job_updated(job)
        self._publish_counts()
        for job in claimed:
            self._spawn(lambda job=job: self._work(job))

    def close(self) -> None:
        """Stop starting jobs (shutdown). Stopping running ones is ticket 11."""
        with self._lock:
            self._closed = True

    def handle(self, job_id: str) -> ProcessHandle | None:
        """The running process of a job, if any (for cancellation, ticket 10)."""
        with self._lock:
            return self._active.get(job_id)

    def active_ids(self) -> list[str]:
        with self._lock:
            return list(self._active)

    def _work(self, job: Job) -> None:
        try:
            self._runner.run(job, on_handle=lambda h: self._set_handle(job.id, h))
        except Exception:
            log.exception("Job %s crashed the runner", job.id)
        finally:
            with self._lock:
                self._active.pop(job.id, None)
            self._publish_counts()
            self.kick()

    def _set_handle(self, job_id: str, handle: ProcessHandle) -> None:
        with self._lock:
            if job_id in self._active:
                self._active[job_id] = handle

    def _publish_counts(self) -> None:
        with self._lock:
            active = len(self._active)
        self._events.queue_updated(active=active, queued=self._repo.count(JobStatus.QUEUED))
