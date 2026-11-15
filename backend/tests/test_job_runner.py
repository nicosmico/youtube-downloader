"""JobRunner on its own: progress throttling (injectable clock) and the processing transition."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db import Database
from app.engine import EngineManager
from app.jobs import FileMover, Job, JobRepository, JobRunner
from tests.fake_engine import FakeEngine

URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Harness:
    def __init__(self, tmp_path: Path, engine: EngineManager, fake: FakeEngine) -> None:
        db = Database(tmp_path / "db.sqlite3")
        db.migrate()
        self.repo = JobRepository(db)
        self.clock = Clock()
        self.published: list[Job] = []
        self.staging = tmp_path / "staging"
        self.downloads = tmp_path / "downloads"
        self.fake = fake
        self.runner = JobRunner(
            engine=engine,
            repo=self.repo,
            mover=FileMover(self.downloads),
            staging_root=self.staging,
            publish=self.published.append,
            stream=fake,
            clock=self.clock,
        )

    def run(self) -> Job:
        self.repo.create(url=URL, mode="video", quality="best")
        (job,) = self.repo.claim_queued(1)
        return self.runner.run(job)

    def statuses(self, job_id: str) -> list[str]:
        return [j.status.value for j in self.published if j.id == job_id]


@pytest.fixture
def harness(tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine) -> Harness:
    engine.install()
    return Harness(tmp_path, engine, fake_engine)


def test_progress_is_persisted_and_published_at_most_once_per_second(harness: Harness) -> None:
    harness.fake.default.streams = [("zoo.mp4", 1000)]
    harness.fake.default.lines_per_stream = 10
    harness.fake.default.postprocessors = ()
    harness.fake.tick = lambda: setattr(harness.clock, "now", harness.clock.now + 0.25)

    job = harness.run()

    downloading = [j for j in harness.published if j.status.value == "downloading"]
    # 10 progress lines over 2.5 s (+ the "finished" line): t=0, 1.0, 2.0, then the final flush
    assert [round(j.downloaded_bytes / 10) for j in downloading] == [10, 50, 90, 100]
    assert harness.statuses(job.id)[-1] == "completed"


def test_nothing_is_published_between_flushes_when_time_stands_still(harness: Harness) -> None:
    harness.fake.default.postprocessors = ()

    harness.run()

    downloading = [j for j in harness.published if j.status.value == "downloading"]
    # clock frozen: the first line flushes immediately, the rest is held until the final flush
    assert len(downloading) == 2


def test_processing_starts_at_the_first_postprocessor_that_is_not_move_files(
    harness: Harness,
) -> None:
    harness.fake.default.postprocessors = ("MoveFiles",)
    job = harness.run()
    assert "processing" not in harness.statuses(job.id)

    harness.published.clear()
    harness.fake.default.postprocessors = ("Merger", "MoveFiles")
    job = harness.run()
    statuses = harness.statuses(job.id)
    assert statuses.index("processing") > max(
        i for i, s in enumerate(statuses) if s == "downloading"
    )
    assert statuses[-1] == "completed"


def test_processing_is_persisted(harness: Harness) -> None:
    seen: list[str] = []
    original = harness.runner._publish

    def spy(job: Job) -> None:
        if job.status.value == "processing":
            seen.append(harness.repo.get(job.id).status.value)  # type: ignore[union-attr]
        original(job)

    harness.runner._publish = spy
    harness.run()

    assert seen == ["processing"]


def test_total_bytes_estimate_streams_complete(harness: Harness) -> None:
    harness.fake.default.estimate_only = True
    harness.fake.default.streams = [("a.mp4", None)]

    job = harness.run()

    assert job.status.value == "completed"


def test_the_runner_finds_the_file_when_the_path_is_not_printed(harness: Harness) -> None:
    harness.fake.default.no_path = True

    job = harness.run()

    assert job.status.value == "completed"
    assert Path(job.output_path or "").read_bytes() == b"fake-video-bytes"


def test_the_process_handle_is_reachable_while_running(
    tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
) -> None:
    engine.install()
    h = Harness(tmp_path, engine, fake_engine)
    h.repo.create(url=URL, mode="video", quality="best")
    (job,) = h.repo.claim_queued(1)
    handles: list[object] = []

    h.runner.run(job, on_handle=handles.append)

    assert handles == fake_engine.handles
