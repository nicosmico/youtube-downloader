"""Bulk routes over the jobs: clean the History, and cancel or retry a Batch or several jobs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.errors import ApiError
from app.jobs.queue import JobQueue, UnknownBatch

MAX_RETRY_IDS = 500


class RetryMany(BaseModel):
    ids: list[str] = Field(max_length=MAX_RETRY_IDS)

    @field_validator("ids")
    @classmethod
    def _no_repeats(cls, ids: list[str]) -> list[str]:
        if len(set(ids)) != len(ids):
            raise ValueError("ids must not repeat")
        return ids


def build_history_router(*, queue: JobQueue) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.delete("/batches/{batch_id}")
    def remove_batch(batch_id: str) -> dict[str, int]:
        """Quita del historial los jobs terminales de una playlist; los archivos no se tocan."""
        try:
            removed = queue.remove_batch(batch_id)
        except UnknownBatch:
            raise _unknown_batch() from None
        return {"removed": len(removed)}

    @router.post("/batches/{batch_id}/cancel")
    def cancel_batch(batch_id: str) -> dict[str, Any]:
        """Cancela los jobs en cola y en curso de una playlist; devuelve los que quedaron
        cancelados."""
        try:
            jobs = queue.cancel_batch(batch_id)
        except UnknownBatch:
            raise _unknown_batch() from None
        return {"jobs": [j.to_dict() for j in jobs]}

    @router.post("/batches/{batch_id}/retry")
    def retry_batch(batch_id: str) -> dict[str, Any]:
        """Reintenta los jobs fallidos, cancelados e interrumpidos de una playlist."""
        try:
            jobs = queue.retry_batch(batch_id)
        except UnknownBatch:
            raise _unknown_batch() from None
        return {"jobs": [j.to_dict() for j in jobs]}

    @router.post("/jobs/retry")
    def retry_jobs(body: RetryMany) -> dict[str, Any]:
        """Reintenta los jobs dados; los que no existen o no se pueden reintentar se ignoran."""
        return {"jobs": [j.to_dict() for j in queue.retry_many(body.ids)]}

    @router.delete("/history")
    def clear_history() -> dict[str, int]:
        """Quita del historial todos los jobs terminales; los archivos no se tocan."""
        return {"removed": len(queue.clear_history())}

    return router


def _unknown_batch() -> ApiError:
    return ApiError(404, "batch_not_found", "No se encontró la playlist.")
