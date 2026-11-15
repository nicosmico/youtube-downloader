"""Engine Manager: installs, verifies and updates yt-dlp, ffmpeg, ffprobe and Deno.

State machine: `missing -> installing -> ready | error`. Any failure leaves the Engine in
`error` (no degraded mode); `install()` retries. A yt-dlp update keeps the Engine `ready` and
only raises the `updating` flag; if it fails the old binary stays in place.

All work is blocking and runs in a background thread (`start()`); `info()` is cheap and safe
to call from any thread, and listeners are called after every change of the public state.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.engine import sources
from app.engine.io import Fetcher, FetchError, ProcessError, Runner, UrllibFetcher, run_process

log = logging.getLogger("app.engine")

UPDATE_INTERVAL = timedelta(hours=24)
TICK_SECONDS = 3600
MANIFEST_NAME = "engine.json"
LEFTOVER_SUFFIXES = (".old", ".new", ".tmp")
EXECUTABLE_MODE = 0o755

_VERSION_FLAGS = {
    "yt-dlp": "--version",
    "ffmpeg": "-version",
    "ffprobe": "-version",
    "deno": "--version",
}
_VERSION_PATTERNS = {
    "yt-dlp": re.compile(r"^(\d{4}\.\d{2}\.\d{2}\S*)"),
    "ffmpeg": re.compile(r"^ffmpeg version (\S+)"),
    "ffprobe": re.compile(r"^ffprobe version (\S+)"),
    "deno": re.compile(r"^deno (\S+)"),
}


class EngineStatus(StrEnum):
    MISSING = "missing"
    INSTALLING = "installing"
    READY = "ready"
    ERROR = "error"


class UpdateOutcome(StrEnum):
    UPDATED = "updated"
    UP_TO_DATE = "up_to_date"
    DEFERRED = "deferred"  # can_update() said no (active downloads)
    BUSY = "busy"  # an install or update is already running
    NOT_READY = "not_ready"
    UNSUPPORTED = "unsupported"  # ENGINE_BIN_DIR: binaries are managed by hand
    FAILED = "failed"


class EngineError(Exception):
    """A step failed; the message is shown to the user as is (Spanish)."""


@dataclass(frozen=True)
class EngineInfo:
    status: EngineStatus = EngineStatus.MISSING
    message: str | None = None
    versions: dict[str, str] = field(default_factory=dict)
    updating: bool = False
    last_update_check: str | None = None
    update_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "versions": {
                "ytDlp": self.versions.get("yt-dlp"),
                "ffmpeg": self.versions.get("ffmpeg"),
                "ffprobe": self.versions.get("ffprobe"),
                "deno": self.versions.get("deno"),
            },
            "updating": self.updating,
            "lastUpdateCheck": self.last_update_check,
            "updateMessage": self.update_message,
        }


def _start_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="engine", daemon=True).start()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EngineManager:
    def __init__(
        self,
        *,
        data_dir: Path,
        bin_dir_override: Path | None = None,
        target: str | None = None,
        fetcher: Fetcher | None = None,
        runner: Runner = run_process,
        now: Callable[[], datetime] = _utcnow,
        can_update: Callable[[], bool] = lambda: True,
        spawn: Callable[[Callable[[], None]], None] = _start_thread,
        pinned: Callable[[str], tuple[sources.Archive, ...]] = sources.pinned_archives,
    ) -> None:
        """`can_update` is the hook the Queue uses to defer yt-dlp updates while downloads run."""
        self.data_dir = data_dir
        self.external = bin_dir_override is not None
        self.bin_dir = bin_dir_override or data_dir / "bin"
        self.target = target if target is not None else sources.detect_target()
        self._fetcher = fetcher or UrllibFetcher()
        self._run = runner
        self._now = now
        self.can_update = can_update
        self._spawn = spawn
        self._pinned = pinned
        self._lock = threading.RLock()  # guards _info and _listeners
        self._op_lock = threading.Lock()  # one install/update at a time
        self._info = EngineInfo()
        self._listeners: list[Callable[[EngineInfo], None]] = []
        self._manifest: dict[str, Any] = self._load_manifest()
        self._info = dataclasses.replace(
            self._info, last_update_check=self._manifest.get("lastUpdateCheck")
        )

    # -- public API ---------------------------------------------------------------------------

    def info(self) -> EngineInfo:
        with self._lock:
            return self._info

    def subscribe(self, listener: Callable[[EngineInfo], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def binary_path(self, binary: str) -> Path:
        """Absolute path of an Engine binary (for the runner, ticket 04+)."""
        return self.bin_dir / sources.exe_name(binary, self.target or "linux-x64")

    def start(self) -> None:
        """Install in the background if needed, then run a due yt-dlp update check."""
        self._spawn(self._bootstrap)

    def start_install(self) -> bool:
        """Retry a failed (or missing) install in the background. False if nothing to do."""
        if self.info().status in (EngineStatus.READY, EngineStatus.INSTALLING):
            return False
        self._spawn(self.install)
        return True

    def start_update(self) -> UpdateOutcome:
        """Manual yt-dlp update in the background; returns why it did not start, or UPDATED."""
        info = self.info()
        if self.external:
            return UpdateOutcome.UNSUPPORTED
        if info.status != EngineStatus.READY:
            return UpdateOutcome.NOT_READY
        if info.updating:
            return UpdateOutcome.BUSY
        if not self.can_update():
            return UpdateOutcome.DEFERRED
        self._spawn(self.update_ytdlp)
        return UpdateOutcome.UPDATED

    def install(self) -> bool:
        """Install (or verify) the Engine. Blocking. False if busy or already ready."""
        if not self._op_lock.acquire(blocking=False):
            return False
        try:
            if self.info().status == EngineStatus.READY:
                return False
            self._set(status=EngineStatus.INSTALLING, message=None)
            try:
                if self.external:
                    self._verify_external()
                else:
                    self._install_all()
            except EngineError as exc:
                log.warning("Engine install failed: %s", exc)
                self._set(status=EngineStatus.ERROR, message=str(exc))
            except Exception:
                log.exception("Unexpected error installing the Engine")
                self._set(
                    status=EngineStatus.ERROR,
                    message="Error inesperado al preparar el motor. Revisa el registro.",
                )
            return True
        finally:
            self._op_lock.release()

    def update_ytdlp(self) -> UpdateOutcome:
        """Replace yt-dlp with the latest release if newer. Blocking; never raises."""
        if self.external:
            return UpdateOutcome.UNSUPPORTED
        if self.info().status != EngineStatus.READY:
            return UpdateOutcome.NOT_READY
        if not self._op_lock.acquire(blocking=False):
            return UpdateOutcome.BUSY
        try:
            if not self.can_update():
                return UpdateOutcome.DEFERRED
            self._set(updating=True, update_message=None)
            try:
                return self._update_ytdlp()
            except EngineError as exc:
                log.warning("yt-dlp update failed: %s", exc)
                self._set(update_message=str(exc))
                return UpdateOutcome.FAILED
            except Exception:
                log.exception("Unexpected error updating yt-dlp")
                self._set(update_message="Error inesperado al actualizar yt-dlp.")
                return UpdateOutcome.FAILED
            finally:
                self._set(updating=False)
        finally:
            self._op_lock.release()

    def tick(self) -> UpdateOutcome | None:
        """Run the yt-dlp update check if the last one is older than 24 h."""
        info = self.info()
        if self.external or info.status != EngineStatus.READY or not self._update_due():
            return None
        return self.update_ytdlp()

    # -- state --------------------------------------------------------------------------------

    def _set(self, **changes: Any) -> None:
        with self._lock:
            new = dataclasses.replace(self._info, **changes)
            if new == self._info:
                return
            self._info = new
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(new)
            except Exception:
                log.exception("Engine listener failed")

    def _bootstrap(self) -> None:
        self.install()
        self.tick()

    def _update_due(self) -> bool:
        last = self.info().last_update_check
        if last is None:
            return True
        try:
            return self._now() - datetime.fromisoformat(last) >= UPDATE_INTERVAL
        except ValueError:
            return True

    # -- manifest (engine.json) ---------------------------------------------------------------

    @property
    def _manifest_path(self) -> Path:
        return self.data_dir / MANIFEST_NAME

    def _load_manifest(self) -> dict[str, Any]:
        try:
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) and isinstance(data.get("binaries"), dict) else {}

    def _save_manifest(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._manifest_path.with_name(MANIFEST_NAME + ".tmp")
        tmp.write_text(json.dumps(self._manifest, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self._manifest_path)

    def _record(self, binary: str, path: Path, *, archive_sha256: str | None = None) -> None:
        entry: dict[str, Any] = {"sha256": _sha256_file(path)}
        if archive_sha256:
            entry["archiveSha256"] = archive_sha256
        self._manifest.setdefault("binaries", {})[binary] = entry
        self._manifest["platform"] = self.target
        self._save_manifest()

    def _touch_last_check(self) -> None:
        stamp = self._now().isoformat()
        self._manifest["lastUpdateCheck"] = stamp
        self._save_manifest()
        self._set(last_update_check=stamp)

    # -- install ------------------------------------------------------------------------------

    def cleanup_leftovers(self) -> None:
        """Delete `.old`, `.new` and temp files left by an interrupted install or update."""
        for path in self.bin_dir.glob("*") if self.bin_dir.is_dir() else ():
            if path.suffix in LEFTOVER_SUFFIXES:
                with contextlib.suppress(OSError):
                    path.unlink()
        with contextlib.suppress(OSError):
            (self._manifest_path.with_name(MANIFEST_NAME + ".tmp")).unlink()

    def _install_all(self) -> None:
        if self.target is None:
            raise EngineError("Este sistema no está soportado (solo macOS arm64 y Windows x64).")
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        self.cleanup_leftovers()
        self._manifest = self._load_manifest()

        if not self._installed("yt-dlp"):
            tag, sha = self._latest_ytdlp()
            self._install_ytdlp(tag, sha)
            self._touch_last_check()
        for archive in self._pinned(self.target):
            if not all(self._installed(e.binary, archive.sha256) for e in archive.extracts):
                self._install_archive(archive)
        self._verify()

    def _installed(self, binary: str, archive_sha256: str | None = None) -> bool:
        entry = self._manifest.get("binaries", {}).get(binary)
        if not isinstance(entry, dict) or not self.binary_path(binary).is_file():
            return False
        return archive_sha256 is None or entry.get("archiveSha256") == archive_sha256

    def _install_archive(self, archive: sources.Archive) -> None:
        tmp = self._download(archive.url, archive.label)
        staged: list[tuple[str, Path]] = []
        try:
            _check_sha256(tmp, archive.sha256, archive.label)
            try:
                with zipfile.ZipFile(tmp) as zf:
                    for extract in archive.extracts:
                        staged.append((extract.binary, self._stage_member(zf, extract)))
            except (zipfile.BadZipFile, OSError) as exc:
                raise EngineError(f"El archivo de {archive.label} no es válido: {exc}") from exc
            for binary, new in staged:
                self._activate(binary, new, archive_sha256=archive.sha256)
        finally:
            tmp.unlink(missing_ok=True)
            for _, new in staged:
                new.unlink(missing_ok=True)

    def _stage_member(self, zf: zipfile.ZipFile, extract: sources.Extract) -> Path:
        member = next(
            (
                info
                for info in zf.infolist()
                if not info.is_dir()
                and (
                    info.filename == extract.member or info.filename.endswith("/" + extract.member)
                )
            ),
            None,
        )
        if member is None:
            raise EngineError(f"No se encontró {extract.member} dentro de la descarga.")
        new = self.binary_path(extract.binary).with_name(
            self.binary_path(extract.binary).name + ".new"
        )
        with zf.open(member) as src, new.open("wb") as out:
            _copy(src, out)
        return new

    def _activate(self, binary: str, new: Path, *, archive_sha256: str | None = None) -> None:
        """chmod +x and atomically move a staged, verified file into place."""
        final = self.binary_path(binary)
        if os.name == "posix":
            new.chmod(EXECUTABLE_MODE)
        try:
            os.replace(new, final)
        except OSError as exc:
            raise EngineError(f"No se pudo instalar {binary}: {exc}") from exc
        self._record(binary, final, archive_sha256=archive_sha256)

    def _download(self, url: str, label: str) -> Path:
        fd, name = tempfile.mkstemp(dir=self.bin_dir, suffix=".tmp")
        os.close(fd)
        tmp = Path(name)
        try:
            self._fetcher.download(url, tmp)
        except FetchError as exc:
            tmp.unlink(missing_ok=True)
            raise EngineError(
                f"No se pudo descargar {label}: {exc}. Revisa tu conexión e inténtalo de nuevo."
            ) from exc
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return tmp

    # -- yt-dlp -------------------------------------------------------------------------------

    def _latest_ytdlp(self) -> tuple[str, str]:
        """Latest release tag and the SHA-256 of this platform's asset, from SHA2-256SUMS."""
        assert self.target is not None
        try:
            release = json.loads(self._fetcher.get_bytes(sources.YTDLP_LATEST_API))
            tag = str(release["tag_name"])
            sums = sources.parse_sha256sums(
                self._fetcher.get_bytes(sources.ytdlp_sums_url(tag)).decode("utf-8", "replace")
            )
        except (FetchError, ValueError, KeyError, TypeError) as exc:
            raise EngineError(
                f"No se pudo consultar la última versión de yt-dlp: {exc}. "
                "Revisa tu conexión e inténtalo de nuevo."
            ) from exc
        asset = sources.ytdlp_asset(self.target)
        if asset not in sums:
            raise EngineError(f"La versión {tag} de yt-dlp no publica {asset}.")
        return tag, sums[asset]

    def _stage_ytdlp(self, tag: str, sha256: str) -> Path:
        assert self.target is not None
        tmp = self._download(sources.ytdlp_asset_url(tag, self.target), "yt-dlp")
        try:
            _check_sha256(tmp, sha256, "yt-dlp")
            final = self.binary_path("yt-dlp")
            new = final.with_name(final.name + ".new")
            os.replace(tmp, new)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return new

    def _install_ytdlp(self, tag: str, sha256: str) -> None:
        new = self._stage_ytdlp(tag, sha256)
        try:
            self._activate("yt-dlp", new)
        finally:
            new.unlink(missing_ok=True)

    def _update_ytdlp(self) -> UpdateOutcome:
        current = self.info().versions.get("yt-dlp", "")
        tag, sha256 = self._latest_ytdlp()
        self._touch_last_check()
        if not _is_newer(tag, current):
            return UpdateOutcome.UP_TO_DATE

        new = self._stage_ytdlp(tag, sha256)
        final = self.binary_path("yt-dlp")
        old = final.with_name(final.name + ".old")
        try:
            if os.name == "posix":
                new.chmod(EXECUTABLE_MODE)
            try:
                old.unlink(missing_ok=True)  # may still be locked by a process on Windows
                os.replace(final, old)  # current -> .old
            except OSError as exc:
                raise EngineError(f"No se pudo reemplazar yt-dlp: {exc}") from exc
            try:
                os.replace(new, final)  # new -> current
                version = self._check_version("yt-dlp")
            except (OSError, EngineError) as exc:
                os.replace(old, final)  # roll back to the working binary
                if isinstance(exc, EngineError):
                    raise
                raise EngineError(f"No se pudo reemplazar yt-dlp: {exc}") from exc
        finally:
            new.unlink(missing_ok=True)
        try:
            old.unlink(missing_ok=True)
        except OSError as exc:  # still locked: cleaned up at the next start
            log.warning("Could not delete %s: %s", old, exc)

        self._record("yt-dlp", final)
        self._manifest["binaries"]["yt-dlp"]["version"] = version
        self._save_manifest()
        self._set(versions={**self.info().versions, "yt-dlp": version})
        return UpdateOutcome.UPDATED

    # -- verification -------------------------------------------------------------------------

    def _check_version(self, binary: str) -> str:
        path = self.binary_path(binary)
        try:
            output = self._run([str(path), _VERSION_FLAGS[binary]])
        except ProcessError as exc:
            raise EngineError(f"{binary} no se pudo ejecutar: {exc}") from exc
        match = _VERSION_PATTERNS[binary].match(
            output.strip().splitlines()[0] if output.strip() else ""
        )
        if match is None:
            raise EngineError(f"{binary} devolvió una versión que no se reconoce.")
        return _short_version(match.group(1))

    def _verify(self) -> None:
        versions = {binary: self._check_version(binary) for binary in sources.BINARIES}
        for binary, version in versions.items():
            self._manifest["binaries"][binary]["version"] = version
        self._save_manifest()
        self._set(status=EngineStatus.READY, message=None, versions=versions)

    def _verify_external(self) -> None:
        """ENGINE_BIN_DIR: use the binaries as they are, only check that they run."""
        target = self.target or "linux-x64"
        for binary in sources.BINARIES:
            if not (self.bin_dir / sources.exe_name(binary, target)).is_file():
                raise EngineError(f"Falta {binary} en ENGINE_BIN_DIR ({self.bin_dir}).")
        versions = {binary: self._check_version(binary) for binary in sources.BINARIES}
        self._manifest = {
            "external": str(self.bin_dir),
            "binaries": {b: {"version": v} for b, v in versions.items()},
        }
        self._save_manifest()
        self._set(status=EngineStatus.READY, message=None, versions=versions)


async def run_periodic(
    engine: EngineManager,
    *,
    interval: float = TICK_SECONDS,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> None:
    """Every `interval` seconds run the (24 h) yt-dlp update check off the event loop."""
    while True:
        await sleep(interval)
        await asyncio.to_thread(engine.tick)


def _short_version(token: str) -> str:
    """`9.0.2-https://www.martin-riedl.de` -> `9.0.2`; unknown shapes are kept as they are."""
    match = re.match(r"n?(\d+(?:\.\d+)*)(?:-|$)", token)
    return match.group(1) if match else token


def _is_newer(candidate: str, current: str) -> bool:
    def key(version: str) -> tuple[int, ...]:
        return tuple(int(p) for p in re.findall(r"\d+", version))

    return not current or key(candidate) > key(current)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _check_sha256(path: Path, expected: str, label: str) -> None:
    if _sha256_file(path) != expected.lower():
        raise EngineError(
            f"La descarga de {label} no coincide con su SHA-256 esperado y no se activó."
        )


def _copy(src, dst) -> None:
    while chunk := src.read(1024 * 1024):
        dst.write(chunk)
