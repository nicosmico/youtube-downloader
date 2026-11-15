"""Opt-in: a real preview against YouTube with the real Engine. Run with `pytest -m network`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.engine import EngineManager, EngineStatus
from app.preview import PreviewService

pytestmark = pytest.mark.network


def test_real_preview_of_a_public_video(tmp_path: Path) -> None:
    bin_dir = os.environ.get("ENGINE_BIN_DIR")  # reuse an installed Engine instead of downloading
    engine = EngineManager(data_dir=tmp_path, bin_dir_override=Path(bin_dir) if bin_dir else None)
    engine.install()
    assert engine.info().status == EngineStatus.READY, engine.info().message

    preview = PreviewService(engine).preview("https://www.youtube.com/watch?v=jNQXAC9IVRw")

    assert preview["title"] == "Me at the zoo"
    assert preview["duration"] == 19
    assert preview["availableQualities"][0] == "best"
    assert not [p for p in tmp_path.rglob("*") if p.suffix in {".mp4", ".webm", ".m4a"}]
