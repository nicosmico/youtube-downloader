"""Download options shared by jobs and presets: which mode takes which field."""

from __future__ import annotations

from typing import Literal

from app.errors import ApiError

Mode = Literal["video", "audio"]
QualityName = Literal["best", "2160p", "1080p", "720p", "480p"]
AudioFormatName = Literal["mp3", "m4a", "opus"]


def check_options(mode: Mode, quality: str | None, audio_format: str | None) -> None:
    """Video takes a `quality` and no `audioFormat`; audio the opposite (spec: "API REST")."""
    if mode == "video":
        if quality is None:
            raise ApiError(422, "invalid_options", "Elige una calidad para descargar el video.")
        if audio_format is not None:
            raise ApiError(
                422, "invalid_options", "El formato de audio solo se puede usar en modo audio."
            )
    else:
        if audio_format is None:
            raise ApiError(422, "invalid_options", "Elige un formato para descargar el audio.")
        if quality is not None:
            raise ApiError(422, "invalid_options", "La calidad solo se puede usar en modo video.")
