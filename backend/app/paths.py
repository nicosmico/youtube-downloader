"""Resolve bundled resources, both from source and from a PyInstaller bundle."""

from __future__ import annotations

import sys
from pathlib import Path


def bundle_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


def static_dir() -> Path:
    return bundle_dir() / "static"
