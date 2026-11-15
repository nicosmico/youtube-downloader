"""Staging per Attempt and the final move into the Destination (ADR-0010)."""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("app.jobs")

STAGING_DIR = "staging"
PARTIAL_SUFFIXES = (".part", ".ytdl", ".temp")


def staging_root(data_dir: Path) -> Path:
    return data_dir / STAGING_DIR


def prepare_staging(root: Path, job_id: str) -> Path:
    """An empty `staging/<job_id>/` (a retry never inherits files from an older Attempt)."""
    path = root / job_id
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def remove_staging(root: Path, job_id: str) -> None:
    shutil.rmtree(root / job_id, ignore_errors=True)


def clean_orphans(root: Path, keep: frozenset[str] = frozenset()) -> int:
    """Delete the staging folders of jobs that are not running. Returns how many."""
    removed = 0
    if root.is_dir():
        for child in root.iterdir():
            if child.name not in keep:
                shutil.rmtree(child, ignore_errors=True)
                child.unlink(missing_ok=True)
                removed += 1
    return removed


def find_staged_file(staging: Path, reported: str | None) -> Path | None:
    """The finished file: the path yt-dlp printed if it is inside staging, else the only file."""
    if reported:
        candidate = Path(reported)
        if not candidate.is_absolute():
            candidate = staging / candidate
        try:
            if candidate.is_file() and candidate.resolve().is_relative_to(staging.resolve()):
                return candidate
        except OSError:
            pass
    files = [p for p in staging.rglob("*") if p.is_file() and not p.name.endswith(PARTIAL_SUFFIXES)]
    return files[0] if len(files) == 1 else None


class FileMover:
    """Moves finished files into the Destination under one process-wide lock.

    Choosing a free name and moving happen inside the lock, so two jobs with the same title
    never pick the same name. `rename` is injectable to simulate a different volume.
    """

    def __init__(
        self,
        download_dir: Path,
        *,
        rename: Callable[[Path, Path], None] = os.rename,
    ) -> None:
        self.download_dir = download_dir
        self._rename = rename
        self._lock = threading.Lock()

    def move(self, source: Path, subdir: str | None = None, name: str | None = None) -> Path:
        """Move `source` into the Destination (as `name` if given) and return its final path.

        `subdir` is created if missing and reused if it exists (the folder of a Batch).
        """
        folder = self.download_dir / subdir if subdir else self.download_dir
        with self._lock:
            folder.mkdir(parents=True, exist_ok=True)
            target = _free_name(folder, name or source.name)
            try:
                self._rename(source, target)
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                self._copy_then_delete(source, target)
            return target

    @staticmethod
    def _copy_then_delete(source: Path, target: Path) -> None:
        """Different volumes: copy under a temporary name so a crash never leaves a half file."""
        partial = target.with_name(target.name + ".part")
        try:
            shutil.copyfile(source, partial)
            os.replace(partial, target)
        except BaseException:
            with contextlib.suppress(OSError):
                partial.unlink(missing_ok=True)
            raise
        source.unlink()


def _free_name(folder: Path, name: str) -> Path:
    """`name`, or `stem (2).ext`, `stem (3).ext`… the first that does not exist."""
    candidate = folder / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 2
    while True:
        candidate = folder / f"{stem} ({number}){suffix}"
        if not candidate.exists():
            return candidate
        number += 1
