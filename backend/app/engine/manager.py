"""Engine Manager: installs, verifies and updates yt-dlp, ffmpeg, ffprobe and Deno.

State machine: `missing -> installing -> ready | error`. Any failure leaves the Engine in
`error` (no degraded mode); `install()` retries. A yt-dlp update keeps the Engine `ready` and
only raises the `updating` flag; if it fails the old binary stays in place.

On macOS and Windows yt-dlp is the unpackaged build, installed as a folder (`bin/yt-dlp-dist/`);
the install and update logic treats that folder as the unit to swap, instead of a single file.

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
import shutil
import stat
import tempfile
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.engine import sources
from app.engine.io import Fetcher, FetchError, ProcessError, Runner, UrllibFetcher, run_process

log = logging.getLogger("app.engine")

UPDATE_INTERVAL = timedelta(hours=24)
TICK_SECONDS = 3600
MANIFEST_NAME = "engine.json"
LEFTOVER_SUFFIXES = (".old", ".new", ".tmp")
EXECUTABLE_MODE = 0o755
# The first run after an install or update is slow (~17 s on a real Mac: the OS scans the
# unpackaged yt-dlp once), so the version check gets far more than the default process timeout.
VERSION_CHECK_TIMEOUT_SECONDS = 90

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
    DEFERRED = "deferred"  # active downloads: the update is pending until the Queue drains
    BUSY = "busy"  # an install or update is already running or pending
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
    update_pending: bool = False  # waiting for the active downloads to finish (ADR-0002)
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
            "updatePending": self.update_pending,
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
        hold_queue: Callable[[], None] = lambda: None,
        release_queue: Callable[[], None] = lambda: None,
        spawn: Callable[[Callable[[], None]], None] = _start_thread,
        pinned: Callable[[str], tuple[sources.Archive, ...]] = sources.pinned_archives,
    ) -> None:
        """The Queue plugs into the update through three hooks (ADR-0002): `hold_queue` stops it
        dispatching new jobs, `can_update` says whether no download is running, `release_queue`
        resumes it. The Queue calls `apply_pending_update` when it drains while held."""
        self.data_dir = data_dir
        self.external = bin_dir_override is not None
        self.bin_dir = bin_dir_override or data_dir / "bin"
        self.target = target if target is not None else sources.detect_target()
        self._fetcher = fetcher or UrllibFetcher()
        self._run = runner
        self._now = now
        self.can_update = can_update
        self.hold_queue = hold_queue
        self.release_queue = release_queue
        self._spawn = spawn
        self._pinned = pinned
        self._lock = threading.RLock()  # guards _info and _listeners
        self._op_lock = threading.Lock()  # one install/update at a time
        self._update_claimed = False  # an update is pending or running (guarded by _lock)
        self._swap_started = False  # its swap began (guarded by _lock)
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
        target = self.target or "linux-x64"
        if binary == "yt-dlp" and self._ytdlp_is_folder:
            return self._ytdlp_dist / sources.ytdlp_executable(target)
        return self.bin_dir / sources.exe_name(binary, target)

    @property
    def _ytdlp_is_folder(self) -> bool:
        """yt-dlp is installed as the unpackaged folder (macOS, Windows), managed by the app."""
        return not self.external and sources.ytdlp_unpackaged(self.target or "linux-x64")

    @property
    def _ytdlp_dist(self) -> Path:
        return self.bin_dir / sources.YTDLP_DIST_DIR

    def _ytdlp_unit(self) -> Path:
        """What an install or update swaps: the folder, or the single binary."""
        return self._ytdlp_dist if self._ytdlp_is_folder else self.binary_path("yt-dlp")

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
        """Manual yt-dlp update. UPDATED: running in the background; DEFERRED: pending until the
        active downloads finish. Anything else is a refusal."""
        refusal = self._begin_update()
        if refusal is not None:
            return refusal
        self._spawn(self._swap)
        return UpdateOutcome.UPDATED

    def apply_pending_update(self) -> None:
        """The Queue drained while held: run the pending update in the background."""
        if self.info().update_pending:
            self._spawn(self._swap)

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
        """Replace yt-dlp with the latest release if newer. Blocking; never raises.

        With downloads running it only leaves the update pending and returns DEFERRED.
        """
        refusal = self._begin_update()
        return refusal if refusal is not None else self._swap()

    def _begin_update(self) -> UpdateOutcome | None:
        """Claim the update and stop the Queue. None: nothing runs, the swap may go ahead."""
        if self.external:
            return UpdateOutcome.UNSUPPORTED
        if self.info().status != EngineStatus.READY:
            return UpdateOutcome.NOT_READY
        with self._lock:
            if self._update_claimed:
                return UpdateOutcome.BUSY
            self._update_claimed = True
        self.hold_queue()  # from here on nothing new starts, so `can_update` can only turn true
        if self.can_update():
            return None
        self._set(update_pending=True)
        if self.can_update():  # drained in between: the Queue's drain hook may have missed us
            return None
        return UpdateOutcome.DEFERRED

    def _swap(self) -> UpdateOutcome:
        """Run the claimed update (the Queue is idle and held); always resumes the Queue."""
        with self._lock:
            if self._swap_started:
                return UpdateOutcome.BUSY  # the drain hook and the caller raced: one wins
            self._swap_started = True
        try:
            if not self._op_lock.acquire(blocking=False):
                return UpdateOutcome.BUSY
            try:
                self._set(updating=True, update_pending=False, update_message=None)
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
        finally:
            with self._lock:
                self._update_claimed = False
                self._swap_started = False
            self._set(update_pending=False)
            self.release_queue()

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
        """Delete `.old`, `.new` and temp files and folders left by an interrupted install or
        update."""
        for path in self.bin_dir.glob("*") if self.bin_dir.is_dir() else ():
            if path.suffix in LEFTOVER_SUFFIXES:
                with contextlib.suppress(OSError):
                    _remove(path)
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
        self._remove_legacy_ytdlp()
        for archive in self._pinned(self.target):
            if not all(self._installed(e.binary, archive.sha256) for e in archive.extracts):
                self._install_archive(archive)
        self._verify()

    def _installed(self, binary: str, archive_sha256: str | None = None) -> bool:
        entry = self._manifest.get("binaries", {}).get(binary)
        if not isinstance(entry, dict) or not self.binary_path(binary).is_file():
            return False
        if binary == "yt-dlp" and self._ytdlp_is_folder and not entry.get("archiveSha256"):
            return False  # installed by an earlier version as a single binary: reinstall
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
            tag = sources.parse_release_tag(
                self._fetcher.redirect_location(sources.YTDLP_LATEST_PAGE)
            )
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
        """Download and verify the release; return the staged unit (`.new` file or folder)."""
        assert self.target is not None
        tmp = self._download(sources.ytdlp_asset_url(tag, self.target), "yt-dlp")
        try:
            _check_sha256(tmp, sha256, "yt-dlp")
            unit = self._ytdlp_unit()
            new = unit.with_name(unit.name + ".new")
            if self._ytdlp_is_folder:
                self._extract_ytdlp(tmp, new)
            else:
                os.replace(tmp, new)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        tmp.unlink(missing_ok=True)
        return new

    def _extract_ytdlp(self, archive: Path, dest: Path) -> None:
        """Unpack the (verified) zip into `dest`; on any failure nothing is left behind."""
        assert self.target is not None
        shutil.rmtree(dest, ignore_errors=True)
        try:
            with zipfile.ZipFile(archive) as zf:
                _extract_zip(zf, dest)
            executable = dest / sources.ytdlp_executable(self.target)
            if not executable.is_file():
                raise EngineError(
                    f"No se encontró {executable.name} dentro de la descarga de yt-dlp."
                )
            if os.name == "posix":
                executable.chmod(EXECUTABLE_MODE)
        except (zipfile.BadZipFile, OSError) as exc:
            shutil.rmtree(dest, ignore_errors=True)
            raise EngineError(f"El archivo de yt-dlp no es válido: {exc}") from exc
        except BaseException:
            shutil.rmtree(dest, ignore_errors=True)
            raise

    def _install_ytdlp(self, tag: str, sha256: str) -> None:
        new = self._stage_ytdlp(tag, sha256)
        try:
            if self._ytdlp_is_folder:
                self._activate_ytdlp_folder(new, sha256)
            else:
                self._activate("yt-dlp", new)
        finally:
            _remove(new)

    def _activate_ytdlp_folder(self, new: Path, archive_sha256: str) -> None:
        final = self._ytdlp_dist
        try:
            shutil.rmtree(final, ignore_errors=True)  # a folder left by an interrupted install
            os.replace(new, final)
        except OSError as exc:
            raise EngineError(f"No se pudo instalar yt-dlp: {exc}") from exc
        self._record("yt-dlp", self.binary_path("yt-dlp"), archive_sha256=archive_sha256)
        self._remove_legacy_ytdlp()

    def _remove_legacy_ytdlp(self) -> None:
        """Delete the single binary of earlier versions once the folder is installed.

        On Windows it can be locked by a running process: the error is ignored, and it is
        deleted at the next start.
        """
        if not self._ytdlp_is_folder or not self._installed("yt-dlp"):
            return
        legacy = self.bin_dir / sources.exe_name("yt-dlp", self.target or "linux-x64")
        try:
            legacy.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not delete %s: %s", legacy, exc)

    def _update_ytdlp(self) -> UpdateOutcome:
        current = self.info().versions.get("yt-dlp", "")
        tag, sha256 = self._latest_ytdlp()
        self._touch_last_check()
        if not _is_newer(tag, current):
            return UpdateOutcome.UP_TO_DATE

        new = self._stage_ytdlp(tag, sha256)
        final = self._ytdlp_unit()  # the folder (macOS, Windows) or the single binary
        old = final.with_name(final.name + ".old")
        try:
            if not self._ytdlp_is_folder and os.name == "posix":
                new.chmod(EXECUTABLE_MODE)
            try:
                _remove(old)  # may still be locked by a process on Windows
                os.replace(final, old)  # current -> .old
            except OSError as exc:
                raise EngineError(f"No se pudo reemplazar yt-dlp: {exc}") from exc
            try:
                os.replace(new, final)  # new -> current
                version = self._check_version("yt-dlp")
            except (OSError, EngineError) as exc:
                _remove(final, ignore_errors=True)  # whatever of the new one is in place
                os.replace(old, final)  # roll back to the working one
                if isinstance(exc, EngineError):
                    raise
                raise EngineError(f"No se pudo reemplazar yt-dlp: {exc}") from exc
        finally:
            _remove(new, ignore_errors=True)
        try:
            _remove(old)
        except OSError as exc:  # still locked: cleaned up at the next start
            log.warning("Could not delete %s: %s", old, exc)

        archive_sha256 = sha256 if self._ytdlp_is_folder else None
        self._record("yt-dlp", self.binary_path("yt-dlp"), archive_sha256=archive_sha256)
        self._manifest["binaries"]["yt-dlp"]["version"] = version
        self._save_manifest()
        self._set(versions={**self.info().versions, "yt-dlp": version})
        return UpdateOutcome.UPDATED

    # -- verification -------------------------------------------------------------------------

    def _check_version(self, binary: str) -> str:
        path = self.binary_path(binary)
        try:
            output = self._run(
                [str(path), _VERSION_FLAGS[binary]], timeout=VERSION_CHECK_TIMEOUT_SECONDS
            )
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


def _remove(path: Path, *, ignore_errors: bool = False) -> None:
    """Delete a file or a whole folder; a missing path is fine."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=ignore_errors)
    elif ignore_errors:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
    else:
        path.unlink(missing_ok=True)


def _extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract every entry into `dest`, refusing paths that would land outside it (zip slip).

    `zipfile` drops the Unix permissions of the entries: those with an execute bit are restored.
    """
    root = dest.resolve()
    dest.mkdir(parents=True)
    for info in zf.infolist():
        name = info.filename
        if (
            name.startswith(("/", "\\"))
            or PureWindowsPath(name).drive
            or ".." in PurePosixPath(name.replace("\\", "/")).parts
        ):
            raise EngineError(f"La descarga de yt-dlp trae una ruta no permitida ({name!r}).")
        target = (root / name).resolve()
        if not target.is_relative_to(root):
            raise EngineError(f"La descarga de yt-dlp trae una ruta no permitida ({name!r}).")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            _copy(src, out)
        mode = stat.S_IMODE(info.external_attr >> 16) if info.create_system == 3 else 0
        if os.name == "posix" and mode & 0o111:
            target.chmod(mode | 0o600)


def _copy(src, dst) -> None:
    while chunk := src.read(1024 * 1024):
        dst.write(chunk)
