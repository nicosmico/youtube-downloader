"""The Queue: takes `queued` jobs FIFO by `queued_at` and runs at most `limit` at a time."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from app.engine.io import ProcessHandle
from app.jobs import failures
from app.jobs.events import JobEvents
from app.jobs.models import Batch, Job, JobStatus
from app.jobs.repository import JobRepository
from app.jobs.runner import JobRunner

log = logging.getLogger("app.jobs")

MAX_CONCURRENT_JOBS = 2
CANCEL_GRACE_SECONDS = 5.0  # TERM first; KILL if the process tree is still there after this
CANCEL_KILL_WAIT_SECONDS = 2.0


class UnknownJob(Exception):
    """There is no job with that id."""


class NotCancelable(Exception):
    """The job is already over (or ended before the cancellation could take effect)."""


class NotRetryable(Exception):
    """Only `failed`, `canceled` and `interrupted` jobs can be retried."""


class NotRemovable(Exception):
    """Only terminal jobs (`completed`, `failed`, `canceled`, `interrupted`) leave the History."""


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
        cancel_grace: float = CANCEL_GRACE_SECONDS,
        cancel_kill_wait: float = CANCEL_KILL_WAIT_SECONDS,
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
        # job id -> process handle (None until the process starts); cancel and shutdown stop it.
        self._active: dict[str, ProcessHandle | None] = {}
        self._stopping: set[str] = set()  # active jobs being interrupted by a shutdown
        self._canceling: set[str] = set()  # active jobs the user asked to cancel
        self._cancel_grace = cancel_grace
        self._cancel_kill_wait = cancel_kill_wait
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

    def enqueue_batch(
        self,
        *,
        source_url: str,
        title: str,
        folder_name: str,
        entries: list[dict],
        **options,
    ) -> tuple[Batch, list[Job]]:
        """A playlist: one Batch and one `queued` job per Entry (`url`, `index`, `title`)."""
        batch = self._repo.create_batch(
            source_url=source_url,
            title=title,
            folder_name=folder_name,
            entry_count=len(entries),
        )
        jobs = [
            self._repo.create(
                url=e["url"],
                title=e["title"],
                thumbnail=e.get("thumbnail"),
                batch_id=batch.id,
                playlist_index=e["index"],
                **options,
            )
            for e in entries
        ]
        for job in jobs:
            self._events.job_updated(job)
        self._publish_counts()
        self.kick()
        return batch, jobs

    def cancel(self, job_id: str) -> Job:
        """Cancel a `queued` or running job and return it in its final state.

        A queued job never starts. A running one has its whole process tree terminated (TERM,
        then KILL after `cancel_grace`); its staging is removed by the runner and its slot goes
        to the next queued job. Blocks until the job has ended.

        Race with completion: the outcome is decided by the process. If it had already exited
        successfully when the TERM arrived, the job `completed` and this raises `NotCancelable`
        (the file is in the Destination); otherwise it ends `canceled`, whatever the exit code.
        """
        with self._lock:
            job = self._repo.get(job_id)
            if job is None:
                raise UnknownJob(job_id)
            if job.status is JobStatus.QUEUED:
                canceled = self._repo.cancel_queued(job_id)
                if canceled is None:  # unreachable under the lock, but never claim a false cancel
                    raise NotCancelable(job_id)
                handle = None
            elif job_id in self._active:
                canceled = None
                self._canceling.add(job_id)
                handle = self._active[job_id]
            else:
                raise NotCancelable(job_id)
        if canceled is not None:
            self._events.job_updated(canceled)
            self._publish_counts()
            return canceled
        if handle is not None:  # None: `_set_handle` terminates it as soon as it exists
            handle.terminate()
        if not self._wait_gone(job_id, self._cancel_grace):
            with self._lock:
                handle = self._active.get(job_id)
            if handle is not None:
                handle.kill()
            if not self._wait_gone(job_id, self._cancel_kill_wait):
                log.error("Job %s still running after cancel", job_id)
        final = self._repo.get(job_id)
        if final is None or final.status is not JobStatus.CANCELED:
            raise NotCancelable(job_id)
        return final

    def retry(self, job_id: str) -> Job:
        """A new Attempt of a `failed`, `canceled` or `interrupted` job, at the end of the line."""
        with self._changed:
            job = self._repo.get(job_id)
            if job is None:
                raise UnknownJob(job_id)
            # The runner publishes the final status just before its slot is released.
            self._changed.wait_for(lambda: job_id not in self._active, self._cancel_kill_wait)
            queued = None if job_id in self._active else self._repo.requeue(job_id)
        if queued is None:
            raise NotRetryable(job_id)
        self._events.job_updated(queued)
        self._publish_counts()
        self.kick()
        return queued

    def remove(self, job_id: str) -> None:
        """Take a finished job out of the History. The downloaded file stays where it is."""
        if self._repo.get(job_id) is None:
            raise UnknownJob(job_id)
        if self._repo.delete_terminal(job_id) is None:
            raise NotRemovable(job_id)
        self._events.job_removed(job_id)

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

    def has_work(self) -> bool:
        """Something is `queued`, `downloading` or `processing`."""
        with self._lock:
            return bool(self._active) or self._repo.count(JobStatus.QUEUED) > 0

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
        """The running process of a job, if any."""
        with self._lock:
            return self._active.get(job_id)

    def active_ids(self) -> list[str]:
        with self._lock:
            return list(self._active)

    def _wait_gone(self, job_id: str, timeout: float) -> bool:
        with self._changed:
            return self._changed.wait_for(lambda: job_id not in self._active, timeout)

    def _wait_drained(self, timeout: float) -> bool:
        with self._changed:
            return self._changed.wait_for(lambda: not self._active, timeout)

    def _work(self, job: Job) -> None:
        try:
            self._runner.run(
                job,
                on_handle=lambda h: self._set_handle(job.id, h),
                interrupted=lambda: self._is_stopping(job.id),
                canceled=lambda: self._is_canceling(job.id),
            )
        except Exception:
            log.exception("Job %s crashed the runner", job.id)
        finally:
            with self._changed:
                self._active.pop(job.id, None)
                self._stopping.discard(job.id)
                self._canceling.discard(job.id)
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

    def _is_canceling(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._canceling

    def _set_handle(self, job_id: str, handle: ProcessHandle) -> None:
        with self._lock:
            if job_id not in self._active:
                return
            self._active[job_id] = handle
            stop = job_id in self._stopping or job_id in self._canceling
        if stop:  # shutdown or cancel began before the process existed
            handle.terminate()

    def _counts(self) -> dict[str, int]:
        return {"active": len(self._active), "queued": self._repo.count(JobStatus.QUEUED)}

    def _publish_counts(self) -> None:
        # Under the lock so concurrent changes publish in the order they happened.
        with self._lock:
            self._events.queue_updated(**self._counts())
