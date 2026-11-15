"""Parser of the yt-dlp progress lines (spec: "Runner y yt-dlp").

PROGRESS lines arrive on stdout, POSTPROC lines on stderr, both as `PREFIX{json}` (the progress
templates). A video with separate video and audio streams is two consecutive downloads that
each end in `"status": "finished"`; neither marks the end of the job, so the job's bytes are the
sum of every stream seen so far (told apart by `filename`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

PROGRESS_PREFIX = "PROGRESS"
POSTPROC_PREFIX = "POSTPROC"
MOVE_FILES = "MoveFiles"


@dataclass(frozen=True)
class Progress:
    percent: float
    downloaded_bytes: int
    total_bytes: int | None
    speed: float | None
    eta: int | None


def _payload(line: str, prefix: str) -> dict[str, Any] | None:
    if not line.startswith(prefix):
        return None
    try:
        data = json.loads(line[len(prefix) :])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def is_progress_line(line: str) -> bool:
    return line.startswith(PROGRESS_PREFIX)


def starts_processing(line: str) -> bool:
    """True for a POSTPROC `started` of anything but yt-dlp's own `MoveFiles` (inside staging)."""
    data = _payload(line, POSTPROC_PREFIX)
    return (
        data is not None
        and data.get("status") == "started"
        and data.get("postprocessor") != MOVE_FILES
    )


class ProgressTracker:
    """Aggregates the PROGRESS lines of one Attempt. Not thread-safe: the caller serializes."""

    def __init__(self) -> None:
        # filename -> (downloaded bytes, total bytes or None while unknown)
        self._streams: dict[str, tuple[int, int | None]] = {}
        self._percent = 0.0
        self._speed: float | None = None
        self._eta: int | None = None

    def feed(self, line: str) -> Progress | None:
        """Consume a stdout line; returns the new aggregate for a usable PROGRESS line."""
        data = _payload(line, PROGRESS_PREFIX)
        if data is None:
            return None
        downloaded = _number(data.get("downloaded_bytes"))
        if downloaded is None:
            return None
        name = str(data.get("filename") or data.get("tmpfilename") or "")
        # `total_bytes` may be missing; fragmented streams only give an estimate.
        total = _number(data.get("total_bytes"))
        if total is None:
            total = _number(data.get("total_bytes_estimate"))
        if data.get("status") == "finished":
            total = downloaded
        else:
            self._speed = _number(data.get("speed"))
            eta = _number(data.get("eta"))
            self._eta = int(eta) if eta is not None else None
        self._streams[name] = (int(downloaded), int(total) if total is not None else None)

        done = sum(d for d, _ in self._streams.values())
        totals = [t for _, t in self._streams.values()]
        total_bytes = None if any(t is None for t in totals) else sum(t for t in totals if t)
        if total_bytes:
            # Never go backwards: the audio stream is unknown until it starts and grows the total.
            self._percent = max(self._percent, min(100.0, done / total_bytes * 100))
        return Progress(self._percent, done, total_bytes, self._speed, self._eta)
