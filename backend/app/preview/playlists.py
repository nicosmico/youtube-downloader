"""yt-dlp `-J --flat-playlist` output -> MediaPreview (playlist or channel)."""

from __future__ import annotations

import re
from typing import Any

from app.preview.failures import failure
from app.preview.mapping import PreviewFailure
from app.preview.urls import CANONICAL_HOST, ClassifiedUrl

MAX_ENTRIES = 500
FALLBACK_TITLE = "Playlist"
UNTITLED_ENTRY = "Video no disponible"

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PLACEHOLDER_TITLES = {
    "[private video]": "Video privado",
    "[deleted video]": "Video eliminado",
}
_AVAILABILITY_REASONS = {
    "private": "Video privado",
    "needs_auth": "Requiere iniciar sesión",
    "subscriber_only": "Solo para miembros del canal",
    "premium_only": "Solo para suscriptores de YouTube Premium",
}
_LIVE_STATUSES = frozenset({"is_live", "is_upcoming", "post_live"})
# A flat entry without a title is what yt-dlp returns for videos it cannot see (the real
# fixture `playlist_unavailable.json` has three of them).
_NO_TITLE_REASON = "Video privado o eliminado"
_LIVE_REASON = "Directo o estreno pendiente"
_THUMBNAIL_HOST = "https://i.ytimg.com"


def to_playlist_preview(data: dict[str, Any], classified: ClassifiedUrl) -> dict[str, Any]:
    """Raise PreviewFailure when the JSON is not a playlist of videos or has nothing in it."""
    raw_entries = data.get("entries")
    if data.get("_type") != "playlist" or not isinstance(raw_entries, list):
        raise PreviewFailure(failure("preview_failed"))
    if any(isinstance(e, dict) and e.get("_type") == "playlist" for e in raw_entries):
        # A channel root that was not redirected to a tab: nested playlists, not videos.
        raise PreviewFailure(failure("preview_failed"))
    if not raw_entries:
        raise PreviewFailure(failure("unavailable", "Esta playlist no tiene videos."))

    count = data.get("playlist_count")
    truncated = (count > MAX_ENTRIES) if isinstance(count, int) else len(raw_entries) >= MAX_ENTRIES
    entries = [
        _entry(index, raw)
        for index, raw in enumerate(raw_entries[:MAX_ENTRIES], start=1)
        if isinstance(raw, dict)
    ]
    return {
        "kind": "playlist",
        "id": str(data.get("id") or ""),
        "url": classified.url,
        "title": str(data.get("title") or "").strip() or FALLBACK_TITLE,
        "author": data.get("channel") or data.get("uploader") or None,
        "thumbnail": _thumbnail(data),
        "entryCount": len(entries),
        "truncated": truncated,
        "entries": entries,
    }


def _entry(index: int, raw: dict[str, Any]) -> dict[str, Any]:
    video_id = str(raw.get("id") or "")
    reason = _unavailable_reason(raw, video_id)
    title = str(raw.get("title") or "").strip()
    if title.lower() in _PLACEHOLDER_TITLES:
        title = ""
    duration = raw.get("duration")
    entry: dict[str, Any] = {
        "id": video_id,
        "url": f"{CANONICAL_HOST}/watch?v={video_id}" if _VIDEO_ID.match(video_id) else "",
        "index": index,
        "title": title or UNTITLED_ENTRY,
        "duration": round(duration) if isinstance(duration, int | float) and duration > 0 else None,
        "available": reason is None,
        # flat playlists carry no thumbnails: YouTube serves them at a fixed address
        "thumbnail": f"{_THUMBNAIL_HOST}/vi/{video_id}/mqdefault.jpg"
        if _VIDEO_ID.match(video_id)
        else None,
    }
    if reason:
        entry["unavailableReason"] = reason
    return entry


def _unavailable_reason(raw: dict[str, Any], video_id: str) -> str | None:
    if not _VIDEO_ID.match(video_id):
        return _NO_TITLE_REASON
    title = str(raw.get("title") or "").strip()
    if title.lower() in _PLACEHOLDER_TITLES:
        return _PLACEHOLDER_TITLES[title.lower()]
    if raw.get("availability") in _AVAILABILITY_REASONS:
        return _AVAILABILITY_REASONS[raw["availability"]]
    if raw.get("live_status") in _LIVE_STATUSES:
        return _LIVE_REASON
    return None if title else _NO_TITLE_REASON


def _thumbnail(data: dict[str, Any]) -> str | None:
    urls = [t["url"] for t in data.get("thumbnails") or [] if isinstance(t, dict) and t.get("url")]
    return urls[-1] if urls else None
