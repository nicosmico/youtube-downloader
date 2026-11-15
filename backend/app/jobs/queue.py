"""The Queue: takes `queued` jobs FIFO by `created_at` and runs at most `limit` at a time."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from app.engine.io import ProcessHandle
from app.jobs import failures
from app.jobs.events import JobEvents
from app.jobs.models import Job, JobStatus
from app.jobs.repository import JobRepository
from app.jobs.runner import JobRunner

log = logging.getLogger("app.jobs")

MAX_CONCURRENT_JOBS = 2


def start_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="download", daemon=True).start()


class JobQueue:
    """FIFO dispatcher. All its state changes under one lock, so `limit` is never exceeded.

    Two reasons to stop dispatching: `hold()` (a yt-dlp update waits for the active jobs to
    drain, ADR-0002) and `shutdown()`. Queued jobs stay `queued` meanwhile.
    """

    def __init__(
        self,
        *,
        repo: JobRepository,
        runner: JobRunner,
        events: JobEvents,
        limit: int = MAX_CONCURRENT_JOBS,
        spawn: Callable[[Callable[[], None]], None] = start_thread,
        on_drained: Callable[[], None] = lambda: None,
    ) -> None:
        """`on_drained` runs when the last active job ends while the Queue is held."""
        self._repo = repo
        self._runner = runner
        self._events = events
        self._limit = limit
        self._spawn = spawn
        self.on_drained = on_drained
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        # job id -> process handle (None until the process starts). Ticket 10 cancels through it.
        self._active: dict[str, ProcessHandle | None] = {}
        self._stopping: set[str] = set()  # active jobs being interrupted by a shutdown
        self._held = False
        self._closed = False

    def start(self) -> None:
        """At startup: jobs the last run left active are `interrupted`; `queued` ones resume.

        Their staging is removed by `clean_orphans`, which the caller runs at the same moment.
        """
        for job in self._repo.interrupt_active(failures.INTERRUPTED):
            self._events.job_updated(job)
        self._publish_counts()
        self.kick()

    def enqueue(self, **fields) -> Job:
        """Persist a new `queued` job and start it if a slot is free."""
        job = self._repo.create(**fields)
        self._events.job_updated(job)
        self._publish_counts()
        self.kick()
        return job

    def kick(self) -> None:
        """Start as many queued jobs as there are free slots (none while held or closed)."""
        with self._lock:
            if self._closed or self._held:
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

    def hold(self) -> None:
        """Stop dispatching new jobs; the active ones keep running."""
        with self._lock:
            self._held = True

    def release(self) -> None:
        """Resume dispatching."""
        with self._lock:
            self._held = False
        self.kick()

    def is_idle(self) -> bool:
        """No job is running (what a yt-dlp update needs)."""
        with self._lock:
            return not self._active

    def counts(self) -> dict[str, int]:
        with self._lock:
            return self._counts()

    def shutdown(self, *, grace: float = 3.0, kill_wait: float = 2.0) -> None:
        """Orderly stop: no more dispatching, terminate the running yt-dlp trees, mark their jobs
        `interrupted`. Bounded: `grace` for TERM, then KILL and `kill_wait` more. Idempotent."""
        with self._lock:
            self._closed = True
            self._stopping.update(self._active)
            handles = [h for h in self._active.values() if h is not None]
        for handle in handles:
            handle.terminate()
        if not self._wait_drained(grace):
            with self._lock:
                handles = [h for h in self._active.values() if h is not None]
            for handle in handles:
                handle.kill()
            if not self._wait_drained(kill_wait):
                log.error("Jobs still running after shutdown: %s", self.active_ids())
        # Whatever a runner did not get to mark (stuck, or killed before it could) is interrupted.
        for job in self._repo.interrupt_active(failures.INTERRUPTED):
            self._events.job_updated(job)
        self._publish_counts()

    def handle(self, job_id: str) -> ProcessHandle | None:
        """The running process of a job, if any (for cancellation, ticket 10)."""
        with self._lock:
            return self._active.get(job_id)

    def active_ids(self) -> list[str]:
        with self._lock:
            return list(self._active)

    def _wait_drained(self, timeout: float) -> bool:
        with self._changed:
            return self._changed.wait_for(lambda: not self._active, timeout)

    def _work(self, job: Job) -> None:
        try:
            self._runner.run(
                job,
                on_handle=lambda h: self._set_handle(job.id, h),
                interrupted=lambda: self._is_stopping(job.id),
            )
        except Exception:
            log.exception("Job %s crashed the runner", job.id)
        finally:
            with self._changed:
                self._active.pop(job.id, None)
                self._stopping.discard(job.id)
                drained = self._held and not self._active
                self._changed.notify_all()
            self._publish_counts()
            if drained:
                self._run_hook(self.on_drained)
            self.kick()

    def _run_hook(self, hook: Callable[[], None]) -> None:
        try:
            hook()
        except Exception:
            log.exception("Queue drain hook failed")

    def _is_stopping(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._stopping

    def _set_handle(self, job_id: str, handle: ProcessHandle) -> None:
        with self._lock:
            if job_id not in self._active:
                return
            self._active[job_id] = handle
            stop = job_id in self._stopping
        if stop:  # shutdown began before the process existed
            handle.terminate()

    def _counts(self) -> dict[str, int]:
        return {"active": len(self._active), "queued": self._repo.count(JobStatus.QUEUED)}

    def _publish_counts(self) -> None:
        # Under the lock so concurrent changes publish in the order they happened.
        with self._lock:
            self._events.queue_updated(**self._counts())
