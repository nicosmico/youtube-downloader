"""Network and process seams of the Engine Manager (replaced by fakes in tests)."""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import signal
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from app import APP_ID, __version__

TIMEOUT_SECONDS = 30

log = logging.getLogger("app.engine")


class FetchError(Exception):
    """A download failed (network, HTTP status or disk)."""


class ProcessError(Exception):
    """A process could not be started, timed out or exited with an error.

    `stderr` keeps the whole error stream (for classification); it is never shown to the user.
    """

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


class ProcessTimeout(ProcessError):
    """The process ran past its timeout and was killed (with its children)."""


class Fetcher(Protocol):
    def get_bytes(self, url: str) -> bytes: ...

    def download(self, url: str, dest: Path) -> None: ...


class Runner(Protocol):
    def __call__(self, args: Sequence[str], timeout: float = TIMEOUT_SECONDS) -> str:
        """Run a command and return its stdout; raise ProcessError (ProcessTimeout) on failure."""
        ...


class ProcessHandle(Protocol):
    """A running process the caller may stop (cancel, ticket 10): TERM first, KILL after a grace."""

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


class Streamer(Protocol):
    def __call__(
        self,
        args: Sequence[str],
        on_stdout: Callable[[str], None],
        on_stderr: Callable[[str], None],
        on_start: Callable[[ProcessHandle], None] | None = None,
    ) -> int:
        """Run a command, feeding its output line by line from both streams as they arrive.

        Blocking, with no time limit; returns the exit code. Raises ProcessError if the process
        cannot be started.
        """
        ...


def default_ssl_context() -> ssl.SSLContext:
    """Trust the OS certificate store (Keychain / Windows store, so corporate CAs work).

    The Python bundled by PyInstaller has no CA bundle of its own on an end-user Mac, so OpenSSL's
    defaults cannot be relied on. Falls back to certifi's bundle if truststore is unavailable.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())


class UrllibFetcher:
    def __init__(self, context: ssl.SSLContext | None = None) -> None:
        self._context = context or default_ssl_context()

    def _open(self, url: str):
        headers = {"User-Agent": f"{APP_ID}/{__version__}", "Accept": "*/*"}
        token = os.environ.get("GITHUB_TOKEN")
        # CI only: unauthenticated GitHub API calls are rate limited per IP, and runners share IPs.
        # The token goes to api.github.com and nowhere else.
        if token and urllib.parse.urlsplit(url).hostname == "api.github.com":
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers)
        return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=self._context)

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


def run_process(args: Sequence[str], timeout: float = TIMEOUT_SECONDS) -> str:
    """Blocking; call it off the event loop. On timeout the whole process tree is killed."""
    options: dict = {}
    if sys.platform == "win32":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        options["start_new_session"] = True  # own process group, so the timeout kills children
    try:
        proc = subprocess.Popen(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **options,
        )
    except OSError as exc:
        raise ProcessError(str(exc)) from exc
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        proc.communicate()
        raise ProcessTimeout(f"timed out after {timeout:g}s") from None
    except BaseException:
        _kill_tree(proc)
        raise
    if proc.returncode != 0:
        detail = (stderr or stdout).strip().splitlines()
        raise ProcessError(detail[-1] if detail else f"exit code {proc.returncode}", stderr)
    return stdout


def _kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            creationflags=flags,
        )
    else:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(OSError):
        proc.kill()


def _popen_options() -> dict:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {"start_new_session": True}  # own process group: the whole tree can be stopped


class _PopenHandle:
    def __init__(self, proc: subprocess.Popen) -> None:
        self._proc = proc

    def terminate(self) -> None:
        if self._proc.poll() is not None:
            return
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(
                ["taskkill", "/PID", str(self._proc.pid), "/T"],
                capture_output=True,
                creationflags=flags,
            )
        else:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(self._proc.pid, signal.SIGTERM)

    def kill(self) -> None:
        _kill_tree(self._proc)


def stream_process(
    args: Sequence[str],
    on_stdout: Callable[[str], None],
    on_stderr: Callable[[str], None],
    on_start: Callable[[ProcessHandle], None] | None = None,
) -> int:
    """Blocking; call it off the event loop. Both pipes are read concurrently (no deadlock)."""
    try:
        proc = subprocess.Popen(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_popen_options(),
        )
    except OSError as exc:
        raise ProcessError(str(exc)) from exc

    def pump(pipe, callback: Callable[[str], None]) -> None:
        for line in pipe:
            try:
                callback(line.rstrip("\r\n"))
            except Exception:  # a broken listener must not stop draining the pipe
                log.exception("Error handling a process output line")

    readers = [
        threading.Thread(target=pump, args=(proc.stdout, on_stdout), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, on_stderr), daemon=True),
    ]
    try:
        for reader in readers:
            reader.start()
        if on_start is not None:
            on_start(_PopenHandle(proc))
        code = proc.wait()
        for reader in readers:
            reader.join()
        return code
    except BaseException:
        _kill_tree(proc)
        raise
