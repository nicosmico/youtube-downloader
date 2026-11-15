"""Preview of a URL: classify, run yt-dlp (never downloads), map to a MediaPreview."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.engine import EngineManager
from app.engine.commands import ytdlp_base_args
from app.engine.io import ProcessError, ProcessTimeout, Runner, run_process
from app.preview.failures import classify_failure, failure
from app.preview.mapping import PreviewFailure, to_media_preview
from app.preview.urls import ClassifiedUrl, UrlKind, UrlRejected, classify_url

log = logging.getLogger("app.preview")

PREVIEW_TIMEOUT_SECONDS = 30


class PreviewService:
    def __init__(
        self,
        engine: EngineManager,
        runner: Runner = run_process,
        timeout: float = PREVIEW_TIMEOUT_SECONDS,
    ) -> None:
        self._engine = engine
        self._run = runner
        self._timeout = timeout

    def preview(self, raw_url: str) -> dict[str, Any]:
        """Blocking (a yt-dlp process): call it off the event loop. Raises PreviewFailure."""
        try:
            classified = classify_url(raw_url)
        except UrlRejected as exc:
            raise PreviewFailure(failure(exc.code)) from None
        if classified.kind is UrlKind.PLAYLIST:
            # TICKET-09: playlist and channel previews replace this temporary refusal.
            raise PreviewFailure(failure("playlist_unsupported"))
        return self._video(classified)

    def _video(self, classified: ClassifiedUrl) -> dict[str, Any]:
        args = [*ytdlp_base_args(self._engine), "-J", "--no-warnings", "--no-playlist"]
        args.append(classified.url)
        try:
            output = self._run(args, self._timeout)
        except ProcessTimeout:
            raise PreviewFailure(failure("timeout")) from None
        except ProcessError as exc:
            log.warning("yt-dlp preview failed: %s", exc)
            raise PreviewFailure(classify_failure(exc.stderr or str(exc))) from None
        try:
            data = json.loads(output)
        except ValueError:
            log.warning("yt-dlp preview returned invalid JSON")
            raise PreviewFailure(failure("preview_failed")) from None
        if not isinstance(data, dict):
            raise PreviewFailure(failure("preview_failed"))
        return to_media_preview(data, classified).to_dict()
