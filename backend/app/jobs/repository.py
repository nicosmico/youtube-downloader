"""Persistence of jobs (SQLite is the source of truth, ADR-0004)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db import Database
from app.jobs.models import TERMINAL_STATUSES, Batch, Job, JobStatus

# Columns the runner and the queue may change after creation.
_MUTABLE = frozenset(
    {
        "title",
        "status",
        "progress_percent",
        "downloaded_bytes",
        "total_bytes",
        "speed",
        "eta",
        "output_path",
        "error",
        "attempt",
        "started_at",
        "finished_at",
    }
)


# A job with the title and size of its Batch, when it has one.
_SELECT = (
    "SELECT jobs.*, batches.title AS batch_title, batches.entry_count AS batch_entry_count "
    "FROM jobs LEFT JOIN batches ON batches.id = jobs.batch_id"
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class JobRepository:
    def __init__(self, db: Database, now: Callable[[], datetime] = utcnow) -> None:
        self._db = db
        self._now = now

    def _stamp(self) -> str:
        # Fixed-width ISO text sorts like the time it represents.
        return self._now().isoformat(timespec="microseconds")

    def create(
        self,
        *,
        url: str,
        mode: str,
        quality: str | None,
        audio_format: str | None = None,
        title: str | None = None,
        batch_id: str | None = None,
        playlist_index: int | None = None,
    ) -> Job:
        """A single video (`batch_id` NULL) or one Entry of a Batch."""
        job_id = uuid.uuid4().hex
        stamp = self._stamp()
        self._db.execute(
            "INSERT INTO jobs (id, batch_id, playlist_index, url, title, mode, quality, "
            "audio_format, status, created_at, queued_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                batch_id,
                playlist_index,
                url,
                title,
                mode,
                quality,
                audio_format,
                JobStatus.QUEUED.value,
                stamp,
                stamp,
            ),
        )
        return self.get(job_id)  # type: ignore[return-value]

    def create_batch(
        self, *, source_url: str, title: str, folder_name: str, entry_count: int
    ) -> Batch:
        batch_id = uuid.uuid4().hex
        self._db.execute(
            "INSERT INTO batches (id, source_url, title, folder_name, entry_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (batch_id, source_url, title, folder_name, entry_count, self._stamp()),
        )
        return self.get_batch(batch_id)  # type: ignore[return-value]

    def get_batch(self, batch_id: str) -> Batch | None:
        rows = self._db.query("SELECT * FROM batches WHERE id = ?", (batch_id,))
        return Batch.from_row(rows[0]) if rows else None

    def highest_index(self, batch_id: str) -> int:
        """The largest playlist position among the jobs of a Batch (0 if it has none)."""
        rows = self._db.query(
            "SELECT MAX(playlist_index) AS top FROM jobs WHERE batch_id = ?", (batch_id,)
        )
        return rows[0]["top"] or 0

    def get(self, job_id: str) -> Job | None:
        rows = self._db.query(f"{_SELECT} WHERE jobs.id = ?", (job_id,))
        return Job.from_row(rows[0]) if rows else None

    def list_jobs(
        self, *, statuses: list[str] | None = None, limit: int = 50, before: str | None = None
    ) -> tuple[list[Job], str | None]:
        """Newest first. Returns the page and the `before` cursor of the next one (or None)."""
        where: list[str] = []
        params: list[Any] = []
        if statuses:
            where.append(f"jobs.status IN ({','.join('?' * len(statuses))})")
            params += statuses
        if before:
            where.append(
                "(jobs.created_at, jobs.rowid) < (SELECT created_at, rowid FROM jobs WHERE id = ?)"
            )
            params.append(before)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._db.query(
            f"{_SELECT} {clause} ORDER BY jobs.created_at DESC, jobs.rowid DESC LIMIT ?",
            [*params, limit + 1],
        )
        jobs = [Job.from_row(r) for r in rows[:limit]]
        return jobs, (jobs[-1].id if len(rows) > limit else None)

    def delete_terminal(self, job_id: str) -> Job | None:
        """Remove a finished job from the History (its file is never touched). The Batch goes
        with its last job. None if the job is not terminal (or does not exist): one atomic
        statement, so a job that a retry just requeued is not removed."""
        job = self.get(job_id)
        if job is None:
            return None
        marks = ",".join("?" * len(TERMINAL_STATUSES))
        removed = self._db.execute(
            f"DELETE FROM jobs WHERE id = ? AND status IN ({marks})",
            (job_id, *(s.value for s in TERMINAL_STATUSES)),
        )
        if not removed:
            return None
        if job.batch_id:
            self._db.execute(
                "DELETE FROM batches WHERE id = ? "
                "AND NOT EXISTS (SELECT 1 FROM jobs WHERE batch_id = ?)",
                (job.batch_id, job.batch_id),
            )
        return job

    def update(self, job_id: str, **fields: Any) -> Job:
        unknown = set(fields) - _MUTABLE
        if unknown:
            raise ValueError(f"not updatable: {sorted(unknown)}")
        if fields:
            assignments = ", ".join(f"{name} = ?" for name in fields)
            self._db.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?", [*fields.values(), job_id]
            )
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def claim_queued(self, limit: int) -> list[Job]:
        """The longest-waiting queued jobs first (FIFO by `queued_at`: a retry goes to the end),
        marked `downloading` when taken."""
        rows = self._db.query(
            "SELECT id FROM jobs WHERE status = ? "
            "ORDER BY COALESCE(queued_at, created_at), rowid LIMIT ?",
            (JobStatus.QUEUED.value, limit),
        )
        stamp = self._stamp()
        return [
            self.update(r["id"], status=JobStatus.DOWNLOADING.value, started_at=stamp) for r in rows
        ]

    def cancel_queued(self, job_id: str) -> Job | None:
        """A `queued` job becomes `canceled` without ever running. None if it was not queued."""
        changed = self._db.execute(
            "UPDATE jobs SET status = ?, finished_at = ? WHERE id = ? AND status = ?",
            (JobStatus.CANCELED.value, self._stamp(), job_id, JobStatus.QUEUED.value),
        )
        return self.get(job_id) if changed else None

    def requeue(self, job_id: str) -> Job | None:
        """A `failed`/`canceled`/`interrupted` job starts a new Attempt at the end of the line:
        `attempt + 1`, progress, error and output cleared. `created_at` is kept (History).
        None if the job was not in one of those states."""
        stamp = self._queue_stamp()
        changed = self._db.execute(
            "UPDATE jobs SET status = ?, attempt = attempt + 1, progress_percent = 0, "
            "downloaded_bytes = NULL, total_bytes = NULL, speed = NULL, eta = NULL, "
            "output_path = NULL, error = NULL, started_at = NULL, finished_at = NULL, "
            "queued_at = ? WHERE id = ? AND status IN (?, ?, ?)",
            (
                JobStatus.QUEUED.value,
                stamp,
                job_id,
                JobStatus.FAILED.value,
                JobStatus.CANCELED.value,
                JobStatus.INTERRUPTED.value,
            ),
        )
        return self.get(job_id) if changed else None

    def _queue_stamp(self) -> str:
        """Now, but strictly after every `queued_at` so far (a coarse clock cannot let a retry
        jump the line)."""
        stamp = self._stamp()
        rows = self._db.query("SELECT MAX(COALESCE(queued_at, created_at)) AS top FROM jobs")
        top = rows[0]["top"]
        if top is not None and top >= stamp:
            return (datetime.fromisoformat(top) + timedelta(microseconds=1)).isoformat(
                timespec="microseconds"
            )
        return stamp

    def interrupt_active(self, message: str) -> list[Job]:
        """`downloading`/`processing` jobs become `interrupted` (their process is gone)."""
        rows = self._db.query(
            "SELECT id FROM jobs WHERE status IN (?, ?) ORDER BY created_at, rowid",
            (JobStatus.DOWNLOADING.value, JobStatus.PROCESSING.value),
        )
        stamp = self._stamp()
        return [
            self.update(
                r["id"],
                status=JobStatus.INTERRUPTED.value,
                speed=None,
                eta=None,
                error=message,
                finished_at=stamp,
            )
            for r in rows
        ]

    def count(self, status: JobStatus) -> int:
        return self._db.query("SELECT COUNT(*) AS n FROM jobs WHERE status = ?", (status.value,))[
            0
        ]["n"]

    def now(self) -> str:
        return self._stamp()
