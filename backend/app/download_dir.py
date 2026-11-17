"""The configurable download folder (ADR-0012): read, validate, save and reset it.

The default is `Settings.download_dir` (`DOWNLOAD_DIR` or `~/Downloads`); a chosen folder is kept
in the `settings` table. The jobs API stamps the effective folder on every job when it enqueues.
"""

from __future__ import annotations

import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.db import Database
from app.errors import ApiError

SETTING_KEY = "download_dir"


class InvalidDownloadDir(ApiError):
    def __init__(self) -> None:
        super().__init__(
            422,
            "invalid_download_dir",
            "Esa ruta no es una carpeta que exista. Elige otra.",
        )


class DownloadDirNotWritable(ApiError):
    def __init__(self) -> None:
        super().__init__(
            422,
            "download_dir_not_writable",
            "No se puede escribir en esa carpeta. Elige otra.",
        )


class DownloadDirUnavailable(ApiError):
    def __init__(self, display: str) -> None:
        super().__init__(
            409,
            "download_dir_unavailable",
            f"La carpeta {display} no está disponible. Conecta el disco o elige otra carpeta.",
        )


class DownloadDir:
    def __init__(
        self,
        db: Database,
        default: Path,
        *,
        home: Callable[[], Path] = Path.home,
        on_change: Callable[[dict[str, Any]], None] = lambda _: None,
    ) -> None:
        """`on_change` gets the new `to_dict()` every time the folder actually changes."""
        self._db = db
        self.default = default
        self._home = home
        self._on_change = on_change
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        rows = self._db.query("SELECT value FROM settings WHERE key = ?", (SETTING_KEY,))
        return Path(rows[0]["value"]) if rows else self.default

    @property
    def is_default(self) -> bool:
        return self.path == self.default

    @property
    def available(self) -> bool:
        """The default one counts as available: it is created when a file is moved into it."""
        return self.is_default or self.path.is_dir()

    def display(self, path: Path | None = None) -> str:
        """The path with the home folder as `~` (the full path on Windows)."""
        path = path or self.path
        if sys.platform == "win32":
            return str(path)
        try:
            relative = path.relative_to(self._home())
        except ValueError:
            return str(path)
        return "~" if not relative.parts else f"~/{relative.as_posix()}"

    def to_dict(self) -> dict[str, Any]:
        path = self.path
        is_default = path == self.default
        return {
            "path": str(path),
            "display": self.display(path),
            "isDefault": is_default,
            "available": is_default or path.is_dir(),
        }

    def effective(self) -> Path:
        """The folder a job enqueued now goes to; a chosen one that is missing is refused."""
        if not self.available:
            raise DownloadDirUnavailable(self.display())
        return self.path

    def set(self, path: Path) -> dict[str, Any]:
        """Validate and save a folder; choosing the default one is the same as resetting."""
        validate(path)
        with self._lock:
            before = self.to_dict()
            if path == self.default:
                self._db.execute("DELETE FROM settings WHERE key = ?", (SETTING_KEY,))
            else:
                self._db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (SETTING_KEY, str(path)),
                )
            return self._changed(before)

    def reset(self) -> dict[str, Any]:
        with self._lock:
            before = self.to_dict()
            self._db.execute("DELETE FROM settings WHERE key = ?", (SETTING_KEY,))
            return self._changed(before)

    def _changed(self, before: dict[str, Any]) -> dict[str, Any]:
        after = self.to_dict()
        if after != before:
            self._on_change(after)
        return after


def validate(path: Path) -> None:
    """Absolute, an existing directory, and writable (a temporary file is created and removed)."""
    if not path.is_absolute() or not path.is_dir():
        raise InvalidDownloadDir
    try:
        with tempfile.TemporaryFile(dir=path):
            pass
    except OSError:
        raise DownloadDirNotWritable from None
