"""Runtime settings, resolved from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.idle import IDLE_SHUTDOWN_SECONDS


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    download_dir: Path
    # Dev-only overrides (ADR-0008): inside Docker the server must listen on 0.0.0.0:<PORT>.
    # In production the Launcher binds 127.0.0.1:0 and learns the real port from the socket.
    bind_host: str = "127.0.0.1"
    port: int = 0
    open_browser: bool = True
    # Dev/CI only: use the Engine binaries found here as they are (no download, no pinned hashes).
    engine_bin_dir: Path | None = None
    # Idle Shutdown (ADR-0001): seconds without clients or work before the app closes; 0 disables.
    idle_shutdown_seconds: float = IDLE_SHUTDOWN_SECONDS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        home = Path.home()
        return cls(
            data_dir=_path(env.get("DATA_DIR"), home / ".youtube-downloader"),
            download_dir=_path(env.get("DOWNLOAD_DIR"), home / "Downloads"),
            bind_host=env.get("BIND_HOST") or "127.0.0.1",
            port=int(env.get("PORT") or 0),
            open_browser=env.get("OPEN_BROWSER", "1") != "0",
            engine_bin_dir=Path(env["ENGINE_BIN_DIR"]).expanduser()
            if env.get("ENGINE_BIN_DIR")
            else None,
            idle_shutdown_seconds=_seconds(env.get("IDLE_SHUTDOWN_SECONDS")),
        )


def _path(value: str | None, default: Path) -> Path:
    return Path(value).expanduser() if value else default


def _seconds(value: str | None) -> float:
    """Unset or unreadable: the default. Negative values disable it, like 0."""
    try:
        return max(0.0, float(value)) if value else IDLE_SHUTDOWN_SECONDS
    except ValueError:
        return IDLE_SHUTDOWN_SECONDS
