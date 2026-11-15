"""Fakes for the Engine's network and process seams. No real network or binaries."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Sequence
from pathlib import Path

from app.engine import sources
from app.engine.io import FetchError, ProcessError

TARGET = "linux-x64"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


class FakeFetcher:
    """Serves bytes by URL; a URL in `failing` raises like a network error."""

    def __init__(self) -> None:
        self.routes: dict[str, bytes] = {}
        self.failing: set[str] = set()
        self.requests: list[str] = []

    def add(self, url: str, data: bytes) -> None:
        self.routes[url] = data

    def _serve(self, url: str) -> bytes:
        self.requests.append(url)
        if url in self.failing:
            raise FetchError("sin conexión")
        if url not in self.routes:
            raise FetchError("HTTP 404")
        return self.routes[url]

    def get_bytes(self, url: str) -> bytes:
        return self._serve(url)

    def download(self, url: str, dest: Path) -> None:
        dest.write_bytes(self._serve(url))

    def downloads_of(self, fragment: str) -> int:
        return sum(1 for url in self.requests if fragment in url)

    # -- yt-dlp releases ----------------------------------------------------------------------

    def publish_ytdlp(
        self, tag: str, content: bytes, *, sums_sha256: str | None = None, target: str = TARGET
    ) -> None:
        asset = sources.ytdlp_asset(target)
        self.add(sources.YTDLP_LATEST_API, json.dumps({"tag_name": tag}).encode())
        digest = sums_sha256 or sha256(content)
        self.add(
            sources.ytdlp_sums_url(tag), f"{'0' * 64}  other-asset\n{digest}  {asset}\n".encode()
        )
        self.add(sources.ytdlp_asset_url(tag, target), content)


class FakeRunner:
    """A fake binary is a file whose text is what `--version` prints; `FAIL...` makes it crash."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        self.calls.append(list(args))
        content = Path(args[0]).read_text()
        if content.startswith("FAIL"):
            raise ProcessError(content)
        return content


YTDLP_OLD = b"2026.10.26\n"
YTDLP_NEW = b"2026.11.30\n"
FFMPEG = b"ffmpeg version 9.0.2-test Copyright\n"
FFPROBE = b"ffprobe version 9.0.2-test Copyright\n"
DENO = b"deno 2.9.8 (stable, release)\n"


def fake_archives(
    *, ffmpeg: bytes = FFMPEG, ffprobe: bytes = FFPROBE, deno: bytes = DENO
) -> tuple[tuple[sources.Archive, ...], dict[str, bytes]]:
    """Archives shaped like the real ones for linux-x64, plus {url: bytes} to serve."""
    parts = {
        "deno": ("https://example.test/deno.zip", {"deno": deno}),
        "ffmpeg": ("https://example.test/ffmpeg.zip", {"ffmpeg": ffmpeg}),
        "ffprobe": ("https://example.test/ffprobe.zip", {"ffprobe": ffprobe}),
    }
    archives = []
    routes = {}
    for binary, (url, files) in parts.items():
        data = make_zip(files)
        routes[url] = data
        archives.append(sources.Archive(url, sha256(data), (sources.Extract(binary, binary),)))
    return tuple(archives), routes
