"""Routes of the jobs: `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.engine.guard import require_engine_ready
from app.errors import ApiError
from app.jobs.queue import JobQueue
from app.jobs.repository import JobRepository
from app.preview.failures import failure
from app.preview.urls import UrlKind, UrlRejected, classify_url

DEFAULT_PAGE = 50
MAX_PAGE = 200
MAX_TITLE = 300


class CreateJob(BaseModel):
    url: str
    mode: Literal["video", "audio"]
    quality: Literal["best", "2160p", "1080p", "720p", "480p"] | None = None
    # Spec addition: the client sends the title of the MediaPreview it already showed, so the
    # Queue has something to display before yt-dlp runs.
    title: str | None = Field(default=None, max_length=MAX_TITLE)


def build_jobs_router(*, queue: JobQueue, repo: JobRepository) -> APIRouter:
    router = APIRouter(prefix="/api/jobs")

    @router.post("", dependencies=[Depends(require_engine_ready)])
    def create_job(body: CreateJob) -> dict[str, Any]:
        if body.mode == "audio":
            # TICKET-07: audio mode (`audioFormat`) and the validation of invalid combinations.
            raise ApiError(
                422, "audio_unsupported", "La descarga de audio todavía no está disponible."
            )
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
            url=classified.url, mode="video", quality=body.quality or "best", title=title
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
