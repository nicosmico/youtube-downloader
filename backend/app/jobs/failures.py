"""Turns a failed yt-dlp run into a Spanish, user-safe message.

The raw stderr can hold paths, URLs with tokens or stack traces: it is only inspected here and
never shown. Messages for content problems reuse the preview ones.
"""

from __future__ import annotations

import re

from app.preview.failures import MESSAGES, classify_failure

GENERIC = "La descarga falló. Inténtalo de nuevo."
FILE_MISSING = "La descarga terminó pero no se encontró el archivo. Inténtalo de nuevo."
MOVE_FAILED = "No se pudo guardar el archivo en la carpeta de descargas."
UNSUPPORTED = "Esta combinación de opciones todavía no se puede descargar."

_CONTENT_CODES = ("live_content", "not_public", "unavailable")
_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"not a bot|unusual traffic|http error 429|too many requests", re.I),
        "YouTube bloqueó temporalmente las descargas desde esta conexión. Inténtalo más tarde.",
    ),
    (
        re.compile(r"no space left|disk quota|not enough space", re.I),
        "No hay espacio suficiente en el disco.",
    ),
    (
        re.compile(
            r"unable to download|timed out|connection (reset|refused|aborted)|"
            r"name or service not known|getaddrinfo|temporary failure|network is unreachable|"
            r"incomplete read|ssl:",
            re.I,
        ),
        "Se interrumpió la conexión con YouTube. Inténtalo de nuevo.",
    ),
    (
        re.compile(r"ffmpeg|postprocess|merger|conversion failed|invalid data", re.I),
        "No se pudo procesar el video descargado. Inténtalo de nuevo.",
    ),
)


def describe_failure(stderr: str) -> str:
    code = classify_failure(stderr).code
    if code in _CONTENT_CODES:
        return MESSAGES[code]
    errors = "\n".join(line for line in stderr.splitlines() if line.startswith("ERROR:")) or stderr
    for pattern, message in _RULES:
        if pattern.search(errors):
            return message
    return GENERIC
