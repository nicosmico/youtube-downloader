"""yt-dlp `-J` output -> MediaPreview (video)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.preview.failures import Failure, failure
from app.preview.urls import ClassifiedUrl

# Quality caps in the order the UI shows them (the Quality values of the glossary, `best` first).
CAPS = (2160, 1080, 720, 480)
BEST = "best"
# `not_live` and `was_live` are plain videos. Everything else is a live stream or a premiere:
# `is_live`, `is_upcoming` and also `post_live` (stream ended, recording still processing: its
# formats are not reliably downloadable yet). A missing `live_status` is treated as `not_live`.
_DOWNLOADABLE_LIVE_STATUS = frozenset({None, "not_live", "was_live"})


class PreviewFailure(Exception):
    """The preview is rejected; carries the API error to answer with."""

    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.code)
        self.failure = failure


@dataclass(frozen=True)
class MediaPreview:
    kind: str
    id: str
    url: str
    title: str
    thumbnail: str | None
    duration: int | None
    author: str | None
    available_qualities: list[str]
    max_quality: str
    max_resolution: int | None  # short side of the best format, for display
    playlist_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "kind": self.kind,
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "thumbnail": self.thumbnail,
            "duration": self.duration,
            "author": self.author,
            "availableQualities": self.available_qualities,
            "maxQuality": self.max_quality,
            "maxResolution": self.max_resolution,
        }
        if self.playlist_url:
            body["playlistUrl"] = self.playlist_url
        return body


def max_resolution(formats: list[dict[str, Any]]) -> int | None:
    """Short side (`min(width, height)`, same measure as yt-dlp's `res`) of the best video format.

    Audio-only formats and storyboards (`vcodec: none`) are ignored.
    """
    sides = [
        min(f["width"], f["height"])
        for f in formats
        if f.get("vcodec") not in (None, "none")
        and isinstance(f.get("width"), int)
        and isinstance(f.get("height"), int)
        and f["width"] > 0
        and f["height"] > 0
    ]
    return max(sides, default=None)


def available_qualities(max_side: int | None) -> list[str]:
    """`best` always, plus every cap that is <= the video's maximum.

    A cap above the maximum is pointless (it would download the same file as `best`), so 1440p
    offers `best`, 1080p, 720p and 480p; a 360p video offers only `best`.
    """
    return [BEST, *(f"{cap}p" for cap in CAPS if max_side is not None and cap <= max_side)]


def to_media_preview(data: dict[str, Any], classified: ClassifiedUrl) -> MediaPreview:
    """Raise PreviewFailure for live content or JSON that is not a single video."""
    if data.get("live_status") not in _DOWNLOADABLE_LIVE_STATUS or data.get("is_live"):
        raise PreviewFailure(failure("live_content"))
    video_id, title = data.get("id"), data.get("title")
    if data.get("_type", "video") != "video" or not video_id or not title:
        raise PreviewFailure(failure("preview_failed"))
    side = max_resolution(data.get("formats") or [])
    qualities = available_qualities(side)
    return MediaPreview(
        kind="video",
        id=str(video_id),
        url=classified.url,
        title=str(title),
        thumbnail=_thumbnail(data),
        duration=_duration(data.get("duration")),
        author=data.get("channel") or data.get("uploader") or None,
        available_qualities=qualities,
        max_quality=qualities[1] if len(qualities) > 1 else BEST,
        max_resolution=side,
        playlist_url=classified.playlist_url,
    )


def _thumbnail(data: dict[str, Any]) -> str | None:
    if data.get("thumbnail"):
        return str(data["thumbnail"])
    urls = [t["url"] for t in data.get("thumbnails") or [] if t.get("url")]
    return urls[-1] if urls else None


def _duration(value: Any) -> int | None:
    return round(value) if isinstance(value, int | float) and value > 0 else None
