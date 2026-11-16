"""Routes that clean the History in bulk: remove a Batch's finished jobs, or all of them."""

from __future__ import annotations

from fastapi import APIRouter

from app.errors import ApiError
from app.jobs.queue import JobQueue, UnknownBatch


def build_history_router(*, queue: JobQueue) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.delete("/batches/{batch_id}")
    def remove_batch(batch_id: str) -> dict[str, int]:
        """Quita del historial los jobs terminales de una playlist; los archivos no se tocan."""
        try:
            removed = queue.remove_batch(batch_id)
        except UnknownBatch:
            raise ApiError(404, "batch_not_found", "No se encontró la playlist.") from None
        return {"removed": len(removed)}

    @router.delete("/history")
    def clear_history() -> dict[str, int]:
        """Quita del historial todos los jobs terminales; los archivos no se tocan."""
        return {"removed": len(queue.clear_history())}

    return router
