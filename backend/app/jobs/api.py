"""Routes of the jobs: `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.engine.guard import require_engine_ready
from app.errors import ApiError
from app.jobs.folders import FALLBACK_FOLDER, sanitize_folder_name
from app.jobs.options import AudioFormatName, Mode, QualityName, check_options
from app.jobs.queue import JobQueue
from app.jobs.repository import JobRepository
from app.preview.failures import failure
from app.preview.urls import UrlKind, UrlRejected, classify_url, require_video_url

DEFAULT_PAGE = 50
MAX_PAGE = 200
MAX_TITLE = 300
MAX_ENTRIES = 500


class CreateEntry(BaseModel):
    id: str | None = None
    url: str
    index: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=MAX_TITLE)


class CreateJob(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    mode: Mode
    quality: QualityName | None = None
    audio_format: AudioFormatName | None = Field(default=None, alias="audioFormat")
    # Spec addition: the client sends the title of the MediaPreview it already showed, so the
    # Queue has something to display before yt-dlp runs.
    title: str | None = Field(default=None, max_length=MAX_TITLE)
    # Playlist: the Entries the user kept selected. The URL is then the playlist's.
    entries: list[CreateEntry] | None = Field(default=None, max_length=MAX_ENTRIES)


def build_jobs_router(*, queue: JobQueue, repo: JobRepository) -> APIRouter:
    router = APIRouter(prefix="/api/jobs")

    @router.post("", dependencies=[Depends(require_engine_ready)])
    def create_job(body: CreateJob) -> dict[str, Any]:
        check_options(body.mode, body.quality, body.audio_format)
        try:
            classified = classify_url(body.url)
        except UrlRejected as exc:
            f = failure(exc.code)
            raise ApiError(f.status, f.code, f.message) from None
        title = (body.title or "").strip() or None
        if classified.kind is UrlKind.PLAYLIST:
            return _create_batch(body, classified.url, title)
        if body.entries is not None:
            raise ApiError(422, "invalid_entries", "Un video suelto no lleva lista de videos.")
        job = queue.enqueue(
            url=classified.url,
            mode=body.mode,
            quality=body.quality,
            audio_format=body.audio_format,
            title=title,
        )
        return {"batchId": None, "jobs": [job.to_dict()]}

    def _create_batch(body: CreateJob, source_url: str, title: str | None) -> dict[str, Any]:
        if not body.entries:
            raise ApiError(422, "no_entries", "Elige al menos un video de la lista.")
        entries: list[dict[str, Any]] = []
        seen: set[int] = set()
        for entry in body.entries:
            try:
                url = require_video_url(entry.url)
            except UrlRejected:
                raise ApiError(
                    422, "invalid_entry", "Uno de los videos elegidos no es un enlace de YouTube."
                ) from None
            if entry.index in seen:
                raise ApiError(422, "invalid_entries", "Hay videos repetidos en la selección.")
            seen.add(entry.index)
            entries.append(
                {
                    "url": url,
                    "index": entry.index,
                    "title": (entry.title or "").strip() or None,
                }
            )
        entries.sort(key=lambda e: e["index"])
        batch, jobs = queue.enqueue_batch(
            source_url=source_url,
            title=title or FALLBACK_FOLDER,
            folder_name=sanitize_folder_name(title or ""),
            entries=entries,
            mode=body.mode,
            quality=body.quality,
            audio_format=body.audio_format,
        )
        return {"batchId": batch.id, "jobs": [j.to_dict() for j in jobs]}

    @router.get("")
    def list_jobs(
        status: str | None = None,
        limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
        before: str | None = None,
    ) -> dict[str, Any]:
        """Newest first. `status` is one status or a comma list; `before` is the cursor."""
        statuses = [s for s in (status or "").split(",") if s] or None
        jobs, next_before = repo.list_jobs(statuses=statuses, limit=limit, before=before)
        return {"jobs": [j.to_dict() for j in jobs], "nextBefore": next_before}

    @router.get("/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = repo.get(job_id)
        if job is None:
            raise ApiError(404, "job_not_found", "No se encontró la descarga.")
        return job.to_dict()

    return router
