"""Network and process seams of the Engine Manager (replaced by fakes in tests)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from app import APP_ID, __version__

TIMEOUT_SECONDS = 30


class FetchError(Exception):
    """A download failed (network, HTTP status or disk)."""


class ProcessError(Exception):
    """A process could not be started, timed out or exited with an error."""


class Fetcher(Protocol):
    def get_bytes(self, url: str) -> bytes: ...

    def download(self, url: str, dest: Path) -> None: ...


class Runner(Protocol):
    def __call__(self, args: Sequence[str]) -> str:
        """Run a command and return its stdout; raise ProcessError on failure."""
        ...


class UrllibFetcher:
    def _open(self, url: str):
        request = urllib.request.Request(
            url, headers={"User-Agent": f"{APP_ID}/{__version__}", "Accept": "*/*"}
        )
        return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)

    def get_bytes(self, url: str) -> bytes:
        try:
            with self._open(url) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchError(_reason(exc)) from exc

    def download(self, url: str, dest: Path) -> None:
        try:
            with self._open(url) as response, dest.open("wb") as out:
                shutil.copyfileobj(response, out, length=1024 * 1024)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchError(_reason(exc)) from exc


def _reason(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    return str(getattr(exc, "reason", None) or exc)


def run_process(args: Sequence[str]) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        done = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            creationflags=flags,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProcessError(str(exc)) from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise ProcessError(detail[-1] if detail else f"exit code {done.returncode}")
    return done.stdout
