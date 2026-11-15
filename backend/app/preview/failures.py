"""Maps yt-dlp failures to preview error codes with Spanish, user-safe messages.

The raw stderr is only inspected, never shown: it can contain paths or URLs with tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Failure:
    status: int
    code: str
    message: str


MESSAGES = {
    "invalid_url": "La dirección no es válida. Pega el enlace completo de un video de YouTube.",
    "unsupported_site": "Solo se admiten enlaces de YouTube.",
    "mix_playlist": "Los mixes automáticos de YouTube no se pueden descargar.",
    "live_content": "Los directos y estrenos pendientes no se pueden descargar.",
    "not_public": (
        "Este contenido no es público: es privado, tiene restricción de edad o requiere "
        "iniciar sesión."
    ),
    "unavailable": "El video no está disponible: fue eliminado o está bloqueado en tu país.",
    "timeout": "YouTube tardó demasiado en responder. Inténtalo de nuevo.",
    "preview_failed": "No se pudo obtener la información del video. Inténtalo de nuevo.",
}

_STATUS = {"timeout": 504, "preview_failed": 502}


def failure(code: str, message: str | None = None) -> Failure:
    return Failure(_STATUS.get(code, 422), code, message or MESSAGES[code])


# Order matters: the first matching rule wins. Texts come from yt-dlp's YouTube extractor.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "live_content",
        re.compile(
            r"live event will begin|premieres? in|premiere will begin|this live (stream|event)",
            re.I,
        ),
    ),
    # A bot check is about the caller's connection, not about the video being private.
    (
        "preview_failed",
        re.compile(r"not a bot|unusual traffic|http error 429|too many requests", re.I),
    ),
    (
        "not_public",
        re.compile(
            r"private video|sign in|log in|login required|members-only|members only|"
            r"channel's members|join this channel|age[- ]restricted|confirm your age|"
            r"inappropriate for some users",
            re.I,
        ),
    ),
    (
        "unavailable",
        re.compile(
            r"video unavailable|is unavailable|no longer available|has been removed|"
            r"removed by the uploader|terms of service|has been terminated|does not exist|"
            r"not available in your country|blocked it in your country|geo[- ]?restrict|"
            r"not made this video available|copyright",
            re.I,
        ),
    ),
)
_ERROR_LINE = re.compile(r"^ERROR:", re.M)


def classify_failure(stderr: str) -> Failure:
    """Pick the code for the `ERROR:` lines of yt-dlp's stderr (anything else is generic)."""
    errors = "\n".join(line for line in stderr.splitlines() if _ERROR_LINE.match(line)) or stderr
    for code, pattern in _RULES:
        if pattern.search(errors):
            return failure(code)
    return failure("preview_failed")
