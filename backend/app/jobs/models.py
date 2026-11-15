"""DownloadJob: the persisted unit of the Queue (one video, one Attempt at a time)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    INTERRUPTED = "interrupted"


ACTIVE_STATUSES = (JobStatus.DOWNLOADING, JobStatus.PROCESSING)
TERMINAL_STATUSES = (
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
    JobStatus.INTERRUPTED,
)


@dataclass(frozen=True)
class Job:
    id: str
    url: str
    mode: str
    status: JobStatus
    created_at: str
    quality: str | None = None
    audio_format: str | None = None
    title: str | None = None
    batch_id: str | None = None
    playlist_index: int | None = None
    progress_percent: float = 0.0
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: int | None = None
    output_path: str | None = None
    error: str | None = None
    attempt: int = 1
    started_at: str | None = None
    finished_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        data = dict(row)
        data["status"] = JobStatus(data["status"])
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "batchId": self.batch_id,
            "playlistIndex": self.playlist_index,
            "url": self.url,
            "title": self.title,
            "mode": self.mode,
            "quality": self.quality,
            "audioFormat": self.audio_format,
            "status": self.status.value,
            "progressPercent": self.progress_percent,
            "downloadedBytes": self.downloaded_bytes,
            "totalBytes": self.total_bytes,
            "speed": self.speed,
            "eta": self.eta,
            "outputPath": self.output_path,
            "error": self.error,
            "attempt": self.attempt,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
        }
