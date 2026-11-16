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
    # URL of the thumbnail the preview showed (loaded by the browser from YouTube).
    thumbnail: str | None = None
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
    # When the job last entered the Queue: `created_at` at first, later a retry. FIFO follows it.
    queued_at: str | None = None
    # Of its Batch (joined on read); None for a single video.
    batch_title: str | None = None
    batch_entry_count: int | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        data = dict(row)
        data["status"] = JobStatus(data["status"])
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "batchId": self.batch_id,
            "batchTitle": self.batch_title,
            "batchEntryCount": self.batch_entry_count,
            "playlistIndex": self.playlist_index,
            "url": self.url,
            "title": self.title,
            "thumbnail": self.thumbnail,
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


@dataclass(frozen=True)
class Batch:
    """A playlist enqueue: N jobs that share a title and a folder in the Destination."""

    id: str
    source_url: str
    title: str
    folder_name: str
    entry_count: int
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Batch:
        return cls(**dict(row))
