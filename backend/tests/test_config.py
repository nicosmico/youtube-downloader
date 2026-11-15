from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_defaults_bind_loopback_on_a_free_port() -> None:
    settings = Settings.from_env({})

    assert settings.bind_host == "127.0.0.1"
    assert settings.port == 0
    assert settings.open_browser is True
    assert settings.data_dir == Path.home() / ".youtube-downloader"
    assert settings.download_dir == Path.home() / "Downloads"


def test_environment_overrides() -> None:
    settings = Settings.from_env(
        {
            "BIND_HOST": "0.0.0.0",
            "PORT": "8765",
            "OPEN_BROWSER": "0",
            "DATA_DIR": "/data",
            "DOWNLOAD_DIR": "/downloads",
        }
    )

    assert settings.bind_host == "0.0.0.0"
    assert settings.port == 8765
    assert settings.open_browser is False
    assert settings.data_dir == Path("/data")
    assert settings.download_dir == Path("/downloads")
