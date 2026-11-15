"""URL classifier: pure, decides what a pasted URL is before yt-dlp is ever invoked.

Accepted hosts (ADR-0006): youtube.com, www., m., music.youtube.com and youtu.be. A URL with a
video id is a video even if it carries `list=`; then `playlist_url` points at the full list,
unless the list is a Mix (`RD...`) or a private auto list (`WL`, `LL`). Playlist URLs and channel
URLs (any tab) are playlists; a Mix playlist is rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qs, urlsplit

MAX_URL_LENGTH = 2048
YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
)
CANONICAL_HOST = "https://www.youtube.com"

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_LIST_ID = re.compile(r"^[A-Za-z0-9_-]{2,}$")
_HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9-]{1,63}\.)+[a-z0-9-]{2,63}$")
_ID_PREFIXES = ("shorts", "live", "embed")
_CHANNEL_PREFIXES = ("channel", "c", "user")
_PRIVATE_LISTS = frozenset({"WL", "LL"})


class UrlKind(StrEnum):
    VIDEO = "video"
    PLAYLIST = "playlist"


class UrlRejected(Exception):
    """The URL cannot be previewed; `code` is one of the API preview error codes."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ClassifiedUrl:
    kind: UrlKind
    url: str  # normalized: what is passed to yt-dlp
    playlist_url: str | None = None  # videos only: the list the URL came from


def classify_url(raw: str) -> ClassifiedUrl:
    """Raise UrlRejected with `invalid_url`, `unsupported_site` or `mix_playlist`."""
    host, segments, query = _split(raw)
    if host not in YOUTUBE_HOSTS:
        raise UrlRejected("unsupported_site")
    list_id = _list_id(query)

    if host == "youtu.be":
        return _video(segments[0] if segments else None, list_id)

    head = segments[0] if segments else ""
    if head == "watch":
        video = query.get("v", [None])[0]
        if video is None and list_id:
            return _playlist_by_list(list_id)
        return _video(video, list_id)
    if head in _ID_PREFIXES and len(segments) == 2:
        return _video(segments[1], list_id)
    if head == "playlist":
        if not list_id:
            raise UrlRejected("invalid_url")
        return _playlist_by_list(list_id)
    if _is_channel(segments):
        return ClassifiedUrl(UrlKind.PLAYLIST, f"{CANONICAL_HOST}/{'/'.join(segments)}")
    raise UrlRejected("invalid_url")


def _split(raw: str) -> tuple[str, list[str], dict[str, list[str]]]:
    text = (raw or "").strip()
    if not text or len(text) > MAX_URL_LENGTH or re.search(r"\s", text):
        raise UrlRejected("invalid_url")
    if "://" not in text:
        text = f"https://{text}"
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise UrlRejected("invalid_url") from None
    host = (parts.hostname or "").rstrip(".").lower()
    if (
        parts.scheme not in ("http", "https")
        or parts.username is not None
        or port is not None
        or not _HOSTNAME.match(host)
    ):
        raise UrlRejected("invalid_url")
    segments = [s for s in parts.path.split("/") if s]
    return host, segments, parse_qs(parts.query)


def _list_id(query: dict[str, list[str]]) -> str | None:
    value = query.get("list", [None])[0]
    return value if value and _LIST_ID.match(value) else None


def _video(video_id: str | None, list_id: str | None) -> ClassifiedUrl:
    if not video_id or not _VIDEO_ID.match(video_id):
        raise UrlRejected("invalid_url")
    playlist_url = None
    if list_id and not _is_mix(list_id) and list_id not in _PRIVATE_LISTS:
        playlist_url = f"{CANONICAL_HOST}/playlist?list={list_id}"
    return ClassifiedUrl(UrlKind.VIDEO, f"{CANONICAL_HOST}/watch?v={video_id}", playlist_url)


def _playlist_by_list(list_id: str) -> ClassifiedUrl:
    if _is_mix(list_id):
        raise UrlRejected("mix_playlist")
    return ClassifiedUrl(UrlKind.PLAYLIST, f"{CANONICAL_HOST}/playlist?list={list_id}")


def _is_mix(list_id: str) -> bool:
    return list_id.startswith("RD")


def _is_channel(segments: list[str]) -> bool:
    """`/@handle`, `/channel/<id>`, `/c/<name>`, `/user/<name>`, each with an optional tab."""
    if not segments:
        return False
    if segments[0].startswith("@") and len(segments[0]) > 1:
        return len(segments) <= 2
    if segments[0] in _CHANNEL_PREFIXES:
        return 2 <= len(segments) <= 3
    return False
