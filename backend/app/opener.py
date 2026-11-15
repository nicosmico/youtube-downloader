"""Opens a folder in the desktop file manager (Finder / Explorer): a host action."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Protocol


class OpenUnavailable(Exception):
    """This platform cannot open a folder (Linux, containers)."""


class FolderOpener(Protocol):
    def __call__(self, path: Path) -> None:
        """Raise OpenUnavailable when unsupported, OSError when the file manager fails."""
        ...


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True, capture_output=True)
    elif sys.platform == "win32":
        # explorer.exe reports exit code 1 even when it worked: the code is not checked.
        subprocess.Popen(
            ["explorer", str(path)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        raise OpenUnavailable(sys.platform)


class FileRevealer(Protocol):
    def __call__(self, path: Path) -> None:
        """Select the file in the file manager. Same errors as `FolderOpener`."""
        ...


def reveal_file(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=True, capture_output=True)
    elif sys.platform == "win32":
        # explorer.exe reports exit code 1 even when it worked: the code is not checked.
        subprocess.Popen(
            ["explorer", f"/select,{path}"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        raise OpenUnavailable(sys.platform)
