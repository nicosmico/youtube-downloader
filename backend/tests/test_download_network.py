"""Opt-in: a real download of a tiny public video. Run with `pytest -m network`."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.db import Database
from app.engine import EngineManager, EngineStatus
from app.jobs import FileMover, JobRepository, JobRunner

pytestmark = pytest.mark.network

URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo", 19 s


def test_real_download_of_a_tiny_video(tmp_path: Path) -> None:
    bin_dir = os.environ.get("ENGINE_BIN_DIR")  # reuse an installed Engine instead of downloading
    engine = EngineManager(data_dir=tmp_path, bin_dir_override=Path(bin_dir) if bin_dir else None)
    engine.install()
    assert engine.info().status == EngineStatus.READY, engine.info().message
    db = Database(tmp_path / "db.sqlite3")
    db.migrate()
    repo = JobRepository(db)
    downloads = tmp_path / "downloads"
    runner = JobRunner(
        engine=engine,
        repo=repo,
        mover=FileMover(downloads),
        staging_root=tmp_path / "staging",
        publish=lambda job: None,
    )
    repo.create(url=URL, mode="video", quality="480p")
    (job,) = repo.claim_queued(1)

    started = time.monotonic()
    done = runner.run(job)

    assert done.status.value == "completed", done.error
    assert Path(done.output_path or "").parent == downloads
    assert Path(done.output_path or "").stat().st_size > 10_000
    assert list((tmp_path / "staging").iterdir()) == []
    assert time.monotonic() - started < 120
