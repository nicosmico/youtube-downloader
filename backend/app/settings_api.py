"""Routes of the download folder setting (ADR-0012): `/api/settings/download-dir`.

`choose` and `PUT` are plain `def`: FastAPI runs them in a worker thread, so the native dialog
(which blocks until the user answers) and the writability check never stall the event loop.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.download_dir import DownloadDir
from app.errors import ApiError
from app.folder_picker import FolderPicker, PickerUnavailable


class SetDownloadDir(BaseModel):
    path: str


def build_settings_router(*, download_dir: DownloadDir, choose_folder: FolderPicker) -> APIRouter:
    router = APIRouter(prefix="/api/settings/download-dir")
    dialog_open = threading.Lock()  # one native dialog at a time

    @router.get("")
    def get_download_dir() -> dict[str, Any]:
        return download_dir.to_dict()

    @router.put("")
    def put_download_dir(body: SetDownloadDir) -> dict[str, Any]:
        """For tests and development (the UI uses `choose`)."""
        return download_dir.set(Path(body.path))

    @router.delete("")
    def reset_download_dir() -> dict[str, Any]:
        return download_dir.reset()

    @router.post("/choose")
    def choose_download_dir() -> dict[str, Any]:
        if not dialog_open.acquire(blocking=False):
            raise ApiError(
                409, "picker_busy", "Ya hay un diálogo de carpetas abierto. Termina ahí primero."
            )
        try:
            chosen = choose_folder(download_dir.path)
        except PickerUnavailable:
            raise ApiError(
                501,
                "picker_unavailable",
                "Esta acción solo funciona en la aplicación de escritorio (macOS o Windows).",
            ) from None
        except (OSError, subprocess.SubprocessError):
            raise ApiError(
                500, "picker_failed", "No se pudo abrir el diálogo para elegir la carpeta."
            ) from None
        finally:
            dialog_open.release()
        if chosen is None:
            return {"canceled": True}
        return download_dir.set(chosen)

    return router
