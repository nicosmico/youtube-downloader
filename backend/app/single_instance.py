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

from app import APP_ID, __version__
from app.runtime import RuntimeInfo, read_runtime, remove_runtime
from app.updates import is_newer

LOCK_FILE = "instance.lock"
log = logging.getLogger(__name__)

CSRF_HEADER = "X-Requested-With"
TAKEOVER_ATTEMPTS = 60  # x 0.25 s = 15 s for the old instance to release the lock


@dataclass(frozen=True)
class Health:
    """A running instance of this app; ``version`` is None when it does not report one."""

    version: str | None


Probe = Callable[[int], Health | None]
Shutdown = Callable[[int], None]


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


def probe_health(port: int, timeout: float = 1.0) -> Health | None:
    """The instance on 127.0.0.1:<port> if it answers /api/health as this app, else None."""
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            payload = json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if not isinstance(payload, dict) or payload.get("app") != APP_ID:
        return None
    version = payload.get("version")
    return Health(version if isinstance(version, str) else None)


def request_shutdown(port: int, timeout: float = 2.0) -> None:
    """Ask the instance on 127.0.0.1:<port> to shut down. Errors are logged, never raised."""
    request = urllib.request.Request(  # noqa: S310
        f"http://127.0.0.1:{port}/api/system/shutdown",
        data=b"",
        method="POST",
        headers={CSRF_HEADER: APP_ID},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310
            pass
    except (OSError, urllib.error.URLError) as error:
        # It may already be closing; the caller waits for the lock either way.
        log.info("Shutdown request to port %s failed: %s", port, error)


def _is_older(running: str | None, own: str) -> bool:
    """True if the running version is older than ours; missing or unparseable counts as older."""
    if running is None:
        return True
    try:
        return is_newer(own, running)
    except ValueError:
        return True


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
    shutdown: Shutdown = request_shutdown,
    own_version: str = __version__,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = 20,
    takeover_attempts: int = TAKEOVER_ATTEMPTS,
    interval: float = 0.25,
) -> Reuse | Start:
    lock = InstanceLock(data_dir / LOCK_FILE)
    if lock.acquire():
        info = read_runtime(data_dir)
        health = probe(info.port) if info is not None else None
        if info is not None and health is not None:
            # Healthy instance that did not hold our lock (e.g. a filesystem without locks).
            lock.release()
            return _reuse_or_take_over(
                data_dir,
                info,
                health,
                own_version,
                lock,
                shutdown,
                sleep,
                takeover_attempts,
                interval,
            )
        if info is not None:
            log.info("Replacing stale runtime.json (port %s)", info.port)
            remove_runtime(data_dir)
        return Start(lock)

    # Another process holds the lock: it is starting up or running. Wait for it to answer.
    for _ in range(attempts):
        info = read_runtime(data_dir)
        health = probe(info.port) if info is not None else None
        if info is not None and health is not None:
            return _reuse_or_take_over(
                data_dir,
                info,
                health,
                own_version,
                lock,
                shutdown,
                sleep,
                takeover_attempts,
                interval,
            )
        sleep(interval)
    raise InstanceBusy("Another instance holds the lock but is not answering.")


def _reuse_or_take_over(
    data_dir: Path,
    info: RuntimeInfo,
    health: Health,
    own_version: str,
    lock: InstanceLock,
    shutdown: Shutdown,
    sleep: Callable[[float], None],
    attempts: int,
    interval: float,
) -> Reuse | Start:
    """Reuse a healthy instance, unless it is older than us: then replace it (never downgrade)."""
    if not _is_older(health.version, own_version):
        return Reuse(info)

    log.info("Taking over from version %s (running %s)", own_version, health.version)
    shutdown(info.port)
    for _ in range(attempts):
        if lock.acquire():
            remove_runtime(data_dir)
            return Start(lock)
        sleep(interval)
    log.warning(
        "Instance %s on port %s did not shut down in time; reusing it", health.version, info.port
    )
    return Reuse(info)
