"""Fakes for the Engine's network and process seams. No real network or binaries."""

from __future__ import annotations

import hashlib
import io
import json
import threading
import zipfile
from collections.abc import Sequence
from pathlib import Path

from app.engine import sources
from app.engine.io import FetchError, ProcessError, ProcessTimeout

TARGET = "linux-x64"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_zip(files: dict[str, bytes], modes: dict[str, int] | None = None) -> bytes:
    """A zip of `files`; `modes` sets the Unix permissions of some entries (like a zip made on
    macOS, which `zipfile` does not restore when extracting)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = ((modes or {}).get(name, 0o644) | 0o100000) << 16
            zf.writestr(info, data)
    return buf.getvalue()


def ytdlp_zip(content: bytes, target: str, extra: dict[str, bytes] | None = None) -> bytes:
    """The unpackaged yt-dlp release asset: the executable plus an `_internal/` folder."""
    executable = sources.ytdlp_executable(target)
    files = {
        executable: content,
        "_internal/base_library.zip": b"lib",
        "_internal/libpython.dylib": b"dylib",
    } | (extra or {})
    return make_zip(files, {executable: 0o755, "_internal/libpython.dylib": 0o755})


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

    def redirect_location(self, url: str) -> str:
        return self._serve(url).decode()

    def download(self, url: str, dest: Path) -> None:
        dest.write_bytes(self._serve(url))

    def downloads_of(self, fragment: str) -> int:
        return sum(1 for url in self.requests if fragment in url)

    # -- yt-dlp releases ----------------------------------------------------------------------

    def publish_ytdlp(
        self,
        tag: str,
        content: bytes,
        *,
        sums_sha256: str | None = None,
        target: str = TARGET,
        archive: bytes | None = None,
    ) -> None:
        """`content` is what the yt-dlp executable prints for `--version`. Where yt-dlp is the
        unpackaged zip it is served inside one (or `archive`, to serve a specific zip)."""
        asset = sources.ytdlp_asset(target)
        served = content
        if sources.ytdlp_unpackaged(target):
            served = archive if archive is not None else ytdlp_zip(content, target)
        self.add(sources.YTDLP_LATEST_PAGE, f"{sources.YTDLP_RELEASES_TAG}/{tag}".encode())
        digest = sums_sha256 or sha256(served)
        self.add(
            sources.ytdlp_sums_url(tag), f"{'0' * 64}  other-asset\n{digest}  {asset}\n".encode()
        )
        self.add(sources.ytdlp_asset_url(tag, target), served)


class FakeRunner:
    """A fake binary is a file whose text is what `--version` prints; `FAIL...` makes it crash."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.timeouts: list[float] = []

    def __call__(self, args: Sequence[str], timeout: float = 30) -> str:
        self.calls.append(list(args))
        self.timeouts.append(timeout)
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


# -- yt-dlp at the subprocess edge (preview) -----------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures" / "ytdlp"


def load_fixture(name: str) -> dict:
    """A real `yt-dlp -J` output recorded with network and trimmed to the fields the app reads."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


class FakeYtdlp:
    """Stands in for the yt-dlp process: answers by the URL (last argument) it is asked about.

    `respond(url, data)` prints JSON, `fail(url, stderr)` exits with an error, `hang(url)` blocks
    until `release()` (and then raises the timeout, like the real runner does).
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.timeouts: list[float] = []
        self._answers: dict[str, object] = {}
        self._release = threading.Event()
        self.started = threading.Event()

    def respond(self, url: str, data: dict) -> None:
        self._answers[url] = json.dumps(data)

    def fail(self, url: str, stderr: str) -> None:
        self._answers[url] = ProcessError(stderr.splitlines()[-1], stderr)

    def hang(self, url: str) -> None:
        self._answers[url] = "hang"

    def release(self) -> None:
        self._release.set()

    def __call__(self, args: Sequence[str], timeout: float = 30) -> str:
        self.calls.append(list(args))
        self.timeouts.append(timeout)
        answer = self._answers.get(args[-1])
        if answer == "hang":
            self.started.set()
            self._release.wait(10)
            raise ProcessTimeout(f"timed out after {timeout:g}s")
        if isinstance(answer, ProcessError):
            raise answer
        if answer is None:
            raise ProcessError("no answer configured", f"ERROR: unexpected URL {args[-1]}")
        return str(answer)
