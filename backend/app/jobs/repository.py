"""Persistence of jobs (SQLite is the source of truth, ADR-0004)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.db import Database
from app.jobs.models import Batch, Job, JobStatus

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
        self._db.execute(
            "INSERT INTO jobs (id, batch_id, playlist_index, url, title, mode, quality, "
            "audio_format, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                self._stamp(),
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
        """Oldest queued jobs first (FIFO by `created_at`), marked `downloading` when taken."""
        rows = self._db.query(
            "SELECT id FROM jobs WHERE status = ? ORDER BY created_at, rowid LIMIT ?",
            (JobStatus.QUEUED.value, limit),
        )
        stamp = self._stamp()
        return [
            self.update(r["id"], status=JobStatus.DOWNLOADING.value, started_at=stamp) for r in rows
        ]

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
