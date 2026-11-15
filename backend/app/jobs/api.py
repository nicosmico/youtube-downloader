"""Routes of the jobs: `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.engine.guard import require_engine_ready
from app.errors import ApiError
from app.jobs.options import AudioFormatName, Mode, QualityName, check_options
from app.jobs.queue import JobQueue
from app.jobs.repository import JobRepository
from app.preview.failures import failure
from app.preview.urls import UrlKind, UrlRejected, classify_url

DEFAULT_PAGE = 50
MAX_PAGE = 200
MAX_TITLE = 300


class CreateJob(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    mode: Mode
    quality: QualityName | None = None
    audio_format: AudioFormatName | None = Field(default=None, alias="audioFormat")
    # Spec addition: the client sends the title of the MediaPreview it already showed, so the
    # Queue has something to display before yt-dlp runs.
    title: str | None = Field(default=None, max_length=MAX_TITLE)


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
        if classified.kind is UrlKind.PLAYLIST:
            # TICKET-09: playlists become a Batch with one job per Entry.
            f = failure("playlist_unsupported")
            raise ApiError(
                f.status, f.code, "Las playlists y canales todavía no se pueden descargar."
            )
        title = (body.title or "").strip() or None
        job = queue.enqueue(
            url=classified.url,
            mode=body.mode,
            quality=body.quality,
            audio_format=body.audio_format,
            title=title,
        )
        return {"batchId": None, "jobs": [job.to_dict()]}

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
