"""Single Instance: a file lock plus a health probe on the recorded port."""

from __future__ import annotations

import json
import logging
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from app import APP_ID
from app.runtime import RuntimeInfo, read_runtime, remove_runtime

LOCK_FILE = "instance.lock"
log = logging.getLogger(__name__)

Probe = Callable[[int], bool]


class InstanceLock:
    """Exclusive, non-blocking lock on a file; released automatically if the process dies."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: IO[bytes] | None = None

    def acquire(self) -> bool:
        if self._file is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")  # noqa: SIM115 - kept open for the process lifetime
        try:
            _lock(handle)
        except OSError:
            handle.close()
            return False
        self._file = handle
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            _unlock(self._file)
        finally:
            self._file.close()
            self._file = None


def _lock(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def probe_health(port: int, timeout: float = 1.0) -> bool:
    """True if something on 127.0.0.1:<port> answers /api/health as this app."""
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            payload = json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return isinstance(payload, dict) and payload.get("app") == APP_ID


@dataclass(frozen=True)
class Reuse:
    """A healthy instance already exists: open it and exit."""

    info: RuntimeInfo


@dataclass(frozen=True)
class Start:
    """This process owns the lock and must start the server."""

    lock: InstanceLock


class InstanceBusy(Exception):
    """Another process holds the lock but no healthy instance showed up."""


def acquire_instance(
    data_dir: Path,
    *,
    probe: Probe = probe_health,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = 20,
    interval: float = 0.25,
) -> Reuse | Start:
    lock = InstanceLock(data_dir / LOCK_FILE)
    if lock.acquire():
        info = read_runtime(data_dir)
        if info is not None and probe(info.port):
            # Healthy instance that did not hold our lock (e.g. a filesystem without locks).
            lock.release()
            return Reuse(info)
        if info is not None:
            log.info("Replacing stale runtime.json (port %s)", info.port)
            remove_runtime(data_dir)
        return Start(lock)

    # Another process holds the lock: it is starting up or running. Wait for it to answer.
    for _ in range(attempts):
        info = read_runtime(data_dir)
        if info is not None and probe(info.port):
            return Reuse(info)
        sleep(interval)
    raise InstanceBusy("Another instance holds the lock but is not answering.")
