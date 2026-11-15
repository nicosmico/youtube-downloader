"""Opt-in: installs the real Engine for this platform. Run with `pytest -m network`."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine import EngineManager, EngineStatus, sources

pytestmark = pytest.mark.network


def test_real_engine_installs_and_runs(tmp_path: Path) -> None:
    target = sources.detect_target()
    assert target is not None

    engine = EngineManager(data_dir=tmp_path)
    engine.install()

    info = engine.info()
    assert info.status == EngineStatus.READY, info.message
    assert info.versions["deno"] == sources.DENO_VERSION
    assert info.versions["ffmpeg"].startswith(sources.FFMPEG_VERSION)
    assert info.versions["ffprobe"].startswith(sources.FFMPEG_VERSION)
    assert info.versions["yt-dlp"][:4].isdigit()
    saved = (tmp_path / "engine.json").read_text()
    assert "lastUpdateCheck" in saved and "sha256" in saved
