"""The native "choose a folder" dialog (ADR-0012): a host action, like `opener.py`.

Blocking: it returns when the user picks a folder or cancels, so callers run it in a worker thread.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol

PROMPT = "Elige la carpeta de descargas"

# Windows: the path to start in travels in an environment variable, never inside the script.
START_ENV = "YTDL_PICKER_START"
_WINDOWS_SCRIPT = f"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '{PROMPT}'
$dialog.ShowNewFolderButton = $true
if ($env:{START_ENV}) {{ $dialog.SelectedPath = $env:{START_ENV} }}
if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {{
  [Console]::Out.Write($dialog.SelectedPath)
}}
$owner.Dispose()
"""


class PickerUnavailable(Exception):
    """This platform has no native folder dialog (Linux, containers)."""


class FolderPicker(Protocol):
    def __call__(self, start: Path | None) -> Path | None:
        """Show the dialog, opened at `start` if it is a folder. The chosen folder, or None when
        the user cancels. Raise PickerUnavailable when unsupported, OSError when it fails."""
        ...


def choose_folder(start: Path | None) -> Path | None:
    if sys.platform == "darwin":
        return _choose_on_mac(start)
    if sys.platform == "win32":
        return _choose_on_windows(start)
    raise PickerUnavailable(sys.platform)


def applescript_string(value: str) -> str:
    """`value` as an AppleScript string literal (only `\\` and `"` are special inside one)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def mac_script(start: Path | None) -> str:
    location = f" default location (POSIX file {applescript_string(str(start))})" if start else ""
    return f"POSIX path of (choose folder with prompt {applescript_string(PROMPT)}{location})"


def _choose_on_mac(start: Path | None) -> Path | None:
    # `default location` fails when the folder is missing: then the dialog just opens anywhere.
    start = start if start is not None and start.is_dir() else None
    result = subprocess.run(
        ["osascript", "-e", mac_script(start)], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        if "User canceled" in result.stderr or "(-128)" in result.stderr:
            return None
        raise OSError(f"osascript failed: {result.stderr.strip()}")
    chosen = result.stdout.strip()
    return Path(chosen) if chosen else None


def _choose_on_windows(start: Path | None) -> Path | None:
    env = {k: v for k, v in os.environ.items() if k != START_ENV}
    if start is not None and start.is_dir():
        env[START_ENV] = str(start)
    result = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", _WINDOWS_SCRIPT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise OSError(f"powershell failed: {result.stderr.strip()}")
    chosen = result.stdout.strip()  # nothing printed: the user canceled
    return Path(chosen) if chosen else None
