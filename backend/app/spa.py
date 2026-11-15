"""Serve the Angular build with an index.html fallback for client-side routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

from app.errors import ApiError

_MISSING = (
    "<!doctype html><meta charset=utf-8><title>YouTube Downloader</title>"
    "<p>La interfaz no está compilada. Ejecuta <code>npm run build</code> en "
    "<code>frontend/</code> o usa <code>docker compose up --build</code>.</p>"
)


def mount_spa(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise ApiError(404, "not_found", f"Unknown API route: /{path}")
        index = root / "index.html"
        if not index.is_file():
            return HTMLResponse(_MISSING, status_code=503)
        if path:
            candidate = (root / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
        return FileResponse(index)
