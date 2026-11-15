"""Persistence of jobs (SQLite is the source of truth, ADR-0004)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.db import Database
from app.jobs.models import Job, JobStatus

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
    ) -> Job:
        """A single video: `batch_id` stays NULL."""
        job_id = uuid.uuid4().hex
        self._db.execute(
            "INSERT INTO jobs (id, url, title, mode, quality, audio_format, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
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

    def get(self, job_id: str) -> Job | None:
        rows = self._db.query("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return Job.from_row(rows[0]) if rows else None

    def list_jobs(
        self, *, statuses: list[str] | None = None, limit: int = 50, before: str | None = None
    ) -> tuple[list[Job], str | None]:
        """Newest first. Returns the page and the `before` cursor of the next one (or None)."""
        where: list[str] = []
        params: list[Any] = []
        if statuses:
            where.append(f"status IN ({','.join('?' * len(statuses))})")
            params += statuses
        if before:
            where.append("(created_at, rowid) < (SELECT created_at, rowid FROM jobs WHERE id = ?)")
            params.append(before)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._db.query(
            f"SELECT * FROM jobs {clause} ORDER BY created_at DESC, rowid DESC LIMIT ?",
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

    def count(self, status: JobStatus) -> int:
        return self._db.query("SELECT COUNT(*) AS n FROM jobs WHERE status = ?", (status.value,))[
            0
        ]["n"]

    def now(self) -> str:
        return self._stamp()
