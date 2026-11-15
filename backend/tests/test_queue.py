"""The Queue: concurrency, FIFO, restarts, orderly shutdown and the yt-dlp update pause.

Real worker threads, a FakeEngine at the subprocess edge and a temporary SQLite. Nothing here
asserts on elapsed time: downloads are gated by the FakeEngine and tests wait on conditions.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.engine import EngineManager, UpdateOutcome
from app.jobs import FileMover, JobEvents, JobQueue, JobRepository, JobRunner
from app.jobs.failures import INTERRUPTED
from tests.conftest import APP_HEADERS, FakeClock, RecordingBroadcaster
from tests.fake_engine import FakeEngine
from tests.fakes import YTDLP_NEW, FakeFetcher
from tests.test_jobs_api import downloads, enqueue, get_job, wait_for


def url(n: int) -> str:
    return f"https://www.youtube.com/watch?v={str(n) * 11}"


def thread_spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class Harness:
    """A JobQueue wired by hand (no HTTP) over a temporary SQLite."""

    def __init__(
        self,
        tmp_path: Path,
        engine: EngineManager,
        fake: FakeEngine,
        *,
        stream=None,
        now: Callable[[], datetime] | None = None,
        **queue_options,
    ) -> None:
        db = Database(tmp_path / "db.sqlite3")
        db.migrate()
        self.repo = JobRepository(db, now=now) if now else JobRepository(db)
        self.events = RecordingBroadcaster()
        job_events = JobEvents(self.events)
        self.staging = tmp_path / "staging"
        self.downloads = tmp_path / "downloads"
        self.spawned: list[Callable[[], None]] = []
        self.deferred_spawn = False
        self.queue = JobQueue(
            repo=self.repo,
            runner=JobRunner(
                engine=engine,
                repo=self.repo,
                mover=FileMover(self.downloads),
                staging_root=self.staging,
                publish=job_events.job_updated,
                stream=stream or fake,
                clock=lambda: 0.0,
            ),
            events=job_events,
            spawn=self._spawn,
            **queue_options,
        )

    def _spawn(self, fn: Callable[[], None]) -> None:
        if self.deferred_spawn:
            self.spawned.append(fn)
        else:
            thread_spawn(fn)

    def enqueue(self, n: int) -> str:
        return self.queue.enqueue(url=url(n), mode="video", quality="best").id

    def status(self, job_id: str) -> str:
        job = self.repo.get(job_id)
        assert job is not None
        return job.status.value


@pytest.fixture
def harness(tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine) -> Harness:
    engine.install()
    return Harness(tmp_path, engine, fake_engine)


class TestConcurrencyAndFifo:
    def test_five_jobs_never_run_more_than_two_at_once_and_start_in_order(
        self, harness: Harness, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        ids = [harness.enqueue(n) for n in range(1, 6)]

        assert fake_engine.wait_started(2)
        assert sorted(fake_engine.started) == [url(1), url(2)]  # two threads: start order is racy
        assert [harness.status(i) for i in ids] == ["downloading"] * 2 + ["queued"] * 3

        # Free one slot at a time: the next job in line takes it, never a later one.
        for finished, expected_started in ((1, 3), (2, 4), (3, 5)):
            fake_engine.release_url(url(finished))
            assert fake_engine.wait_started(expected_started)
            assert fake_engine.started[2:] == [url(n) for n in range(3, expected_started + 1)]
        fake_engine.release()
        wait_for(lambda: all(harness.status(i) == "completed" for i in ids))

        assert fake_engine.peak == 2
        counts = harness.events.named("queue.updated")
        assert all(c["active"] <= 2 for c in counts)
        assert counts[-1] == {"active": 0, "queued": 0}

    def test_queue_updated_is_published_on_every_change(
        self, harness: Harness, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        harness.enqueue(1)
        assert fake_engine.wait_started(1)
        harness.enqueue(2)
        harness.enqueue(3)
        assert fake_engine.wait_started(2)

        assert harness.events.named("queue.updated") == [
            {"active": 0, "queued": 1},  # enqueued
            {"active": 1, "queued": 0},  # claimed
            {"active": 1, "queued": 1},
            {"active": 2, "queued": 0},
            {"active": 2, "queued": 1},
        ]
        fake_engine.release()
        wait_for(lambda: harness.events.named("queue.updated")[-1] == {"active": 0, "queued": 0})

    def test_jobs_with_the_same_created_at_keep_their_insertion_order(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        frozen = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
        harness = Harness(tmp_path, engine, fake_engine, now=lambda: frozen)
        ids = [harness.repo.create(url=url(n), mode="video", quality="best").id for n in range(5)]

        claimed = [j.id for j in harness.repo.claim_queued(5)]

        assert claimed == ids

    def test_fifo_follows_created_at_not_insertion_order(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        base = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
        stamps = iter([base + timedelta(seconds=s) for s in (2, 1)])
        harness = Harness(
            tmp_path, engine, fake_engine, now=lambda: next(stamps, base + timedelta(seconds=9))
        )
        later = harness.repo.create(url=url(1), mode="video", quality="best").id
        earlier = harness.repo.create(url=url(2), mode="video", quality="best").id

        assert [j.id for j in harness.repo.claim_queued(2)] == [earlier, later]


class TestRestart:
    """Two apps over the same data dir: what a restart finds in the SQLite file."""

    def seed(self, make_jobs_client) -> dict[str, str]:
        client = make_jobs_client(spawn_job=lambda fn: None)  # nothing runs while seeding
        repo: JobRepository = client.app.state.jobs
        ids: dict[str, str] = {}
        for n, (name, status) in enumerate(
            [
                ("completed", "completed"),
                ("failed", "failed"),
                ("downloading", "downloading"),
                ("processing", "processing"),
                ("queued1", "queued"),
                ("queued2", "queued"),
            ],
            start=1,
        ):
            ids[name] = repo.create(url=url(n), mode="video", quality="best", title=name).id
            repo.update(ids[name], status=status)
        repo.update(ids["failed"], error="La descarga falló. Inténtalo de nuevo.")
        repo.update(ids["completed"], output_path="/downloads/done.mp4", progress_percent=100.0)
        return ids

    def test_a_restart_keeps_terminal_jobs_interrupts_active_ones_and_resumes_queued_ones(
        self, make_jobs_client, data_dir: Path, download_dir: Path, fake_engine: FakeEngine
    ) -> None:
        ids = self.seed(make_jobs_client)
        for name in ("downloading", "processing"):  # leftovers of the killed run
            (data_dir / "staging" / ids[name]).mkdir(parents=True)
            (data_dir / "staging" / ids[name] / "x.mp4.part").write_bytes(b"x")
        peek = make_jobs_client(spawn_job=lambda fn: None)
        before = {n: get_job(peek, i) for n, i in ids.items()}

        restarted = make_jobs_client(spawn_job=lambda fn: fn())
        with restarted:
            jobs = {n: get_job(restarted, i) for n, i in ids.items()}

            assert jobs["completed"] == before["completed"]
            assert jobs["failed"] == before["failed"]
            for name in ("downloading", "processing"):
                assert jobs[name]["status"] == "interrupted"
                assert jobs[name]["error"] == INTERRUPTED
                assert jobs[name]["finishedAt"] is not None
                assert not (data_dir / "staging" / ids[name]).exists()
            assert jobs["queued1"]["status"] == "completed"
            assert jobs["queued2"]["status"] == "completed"

        # Interrupted jobs are not resumed; the queued ones ran in FIFO order.
        assert [c[-1] for c in fake_engine.calls] == [url(5), url(6)]
        assert downloads(download_dir) == ["Me at the zoo (2).mp4", "Me at the zoo.mp4"]

    def test_the_reconciliation_is_published_and_a_second_restart_changes_nothing(
        self, make_jobs_client, events: RecordingBroadcaster
    ) -> None:
        ids = self.seed(make_jobs_client)

        with make_jobs_client(spawn_job=lambda fn: fn()):
            interrupted = [
                j["id"] for j in events.named("job.updated") if j["status"] == "interrupted"
            ]
        assert sorted(interrupted) == sorted([ids["downloading"], ids["processing"]])

        again = make_jobs_client(spawn_job=lambda fn: fn())
        with again:
            statuses = {n: get_job(again, i)["status"] for n, i in ids.items()}
        assert statuses["downloading"] == statuses["processing"] == "interrupted"
        assert statuses["completed"] == "completed"


class TestShutdown:
    def test_terminates_active_jobs_marks_them_interrupted_and_leaves_nothing_running(
        self, harness: Harness, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        a, b, waiting = (harness.enqueue(n) for n in (1, 2, 3))
        assert fake_engine.wait_running(2)

        harness.queue.shutdown()

        assert [h.terminated for h in fake_engine.handles] == [True, True]
        assert not any(h.killed for h in fake_engine.handles)  # TERM was enough
        assert fake_engine.wait_running(0)
        assert harness.status(a) == harness.status(b) == "interrupted"
        job = harness.repo.get(a)
        assert job is not None and job.error == INTERRUPTED and job.finished_at
        assert harness.status(waiting) == "queued"  # never started
        assert sorted(fake_engine.started) == [url(1), url(2)]  # two threads: start order is racy
        assert harness.queue.active_ids() == []
        assert not list(harness.staging.glob("*/*"))  # staging of the active jobs is gone
        assert harness.events.named("queue.updated")[-1] == {"active": 0, "queued": 1}

    def test_stops_dispatching(self, harness: Harness, fake_engine: FakeEngine) -> None:
        fake_engine.default.hold = True
        harness.enqueue(1)
        harness.enqueue(2)
        waiting = harness.enqueue(3)
        assert fake_engine.wait_running(2)

        harness.queue.shutdown()  # the two jobs end: their slots must not start the third
        harness.queue.kick()
        late = harness.enqueue(4)

        assert harness.status(waiting) == harness.status(late) == "queued"
        assert sorted(fake_engine.started) == [url(1), url(2)]  # two threads: start order is racy

    def test_kills_a_process_that_ignores_terminate(
        self, harness: Harness, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        fake_engine.default.ignore_terminate = True
        job = harness.enqueue(1)
        assert fake_engine.wait_running(1)

        harness.queue.shutdown(grace=0.05)

        (handle,) = fake_engine.handles
        assert handle.terminated and handle.killed
        assert harness.status(job) == "interrupted"
        assert fake_engine.wait_running(0)

    def test_does_not_hang_on_a_process_nothing_can_stop(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        engine.install()
        stuck = threading.Event()
        calls: list[str] = []

        class Deaf:
            def terminate(self) -> None:
                calls.append("terminate")

            def kill(self) -> None:
                calls.append("kill")

        def stream(args, on_stdout, on_stderr, on_start=None) -> int:
            if on_start:
                on_start(Deaf())
            stuck.wait(10)  # never returns on its own
            return 1

        harness = Harness(tmp_path, engine, fake_engine, stream=stream)
        job = harness.enqueue(1)
        wait_for(lambda: harness.queue.handle(job) is not None)

        harness.queue.shutdown(grace=0.05, kill_wait=0.05)

        assert calls == ["terminate", "kill"]
        assert harness.status(job) == "interrupted"  # marked by the shutdown itself
        stuck.set()

    def test_stops_a_job_whose_process_starts_after_the_shutdown_began(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        engine.install()
        fake_engine.default.hold = True
        harness = Harness(tmp_path, engine, fake_engine)
        harness.deferred_spawn = True  # the worker thread has not started yet
        job = harness.enqueue(1)

        shutting_down = threading.Thread(target=lambda: harness.queue.shutdown(grace=5))
        shutting_down.start()
        wait_for(lambda: harness.queue._closed)
        (worker,) = harness.spawned
        worker()  # the worker starts now: its process is terminated as soon as it exists
        shutting_down.join(5)

        assert not shutting_down.is_alive()
        assert fake_engine.handles[0].terminated
        assert harness.status(job) == "interrupted"

    def test_closing_the_app_shuts_the_queue_down(
        self, make_jobs_client, fake_engine: FakeEngine, data_dir: Path
    ) -> None:
        fake_engine.default.hold = True
        client = make_jobs_client(spawn_job=thread_spawn)

        with client:
            job_id = enqueue(client).json()["jobs"][0]["id"]
            assert fake_engine.wait_running(1)

        peek = make_jobs_client(spawn_job=lambda fn: None)
        assert get_job(peek, job_id)["status"] == "interrupted"
        assert fake_engine.wait_running(0)
        assert not list((data_dir / "staging").glob("*"))


class TestEngineUpdatePause:
    """ADR-0002: the yt-dlp swap waits for the active jobs and nothing new starts meanwhile."""

    @pytest.fixture
    def seen(self, engine: EngineManager, fake_engine: FakeEngine) -> dict[str, str]:
        """The yt-dlp version in place when each download began."""
        versions: dict[str, str] = {}
        fake_engine.on_begin = lambda u: versions.__setitem__(u, engine.info().versions["yt-dlp"])
        return versions

    @pytest.fixture
    def client(self, make_jobs_client, fake_engine: FakeEngine, fetcher: FakeFetcher) -> TestClient:
        fake_engine.default.hold = True
        app = make_jobs_client(spawn_job=thread_spawn)  # installs yt-dlp 2026.10.26
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)  # a newer release appears afterwards
        return app

    def post_update(self, client: TestClient):
        return client.post("/api/system/engine/update", headers=APP_HEADERS)

    def test_a_manual_update_waits_for_the_active_jobs_then_resumes_dispatch(
        self,
        client: TestClient,
        engine: EngineManager,
        fake_engine: FakeEngine,
        events: RecordingBroadcaster,
        seen: dict[str, str],
    ) -> None:
        ids = [enqueue(client, url(n)).json()["jobs"][0]["id"] for n in (1, 2, 3)]
        assert fake_engine.wait_running(2)

        response = self.post_update(client)

        assert response.status_code == 202
        assert response.json()["updatePending"] is True
        assert self.post_update(client).status_code == 409  # already pending
        assert events.named("engine.updated")[-1]["updatePending"] is True

        # A job enqueued meanwhile stays queued, like the third one.
        late = enqueue(client, url(4)).json()["jobs"][0]["id"]
        assert [get_job(client, i)["status"] for i in (*ids, late)] == [
            "downloading",
            "downloading",
            "queued",
            "queued",
        ]

        # One finishes: still no swap and no new dispatch, because the other one still runs.
        fake_engine.release_url(url(1))
        wait_for(lambda: get_job(client, ids[0])["status"] == "completed")
        assert engine.info().versions["yt-dlp"] == "2026.10.26"
        assert engine.info().update_pending is True
        assert get_job(client, ids[2])["status"] == "queued"
        assert sorted(fake_engine.started) == [url(1), url(2)]  # two threads: start order is racy

        # The last one finishes: swap, then the queue resumes with the new binary.
        fake_engine.release_url(url(2))
        assert fake_engine.wait_started(4)
        assert engine.info().versions["yt-dlp"] == "2026.11.30"
        assert engine.info().update_pending is False
        assert seen == {
            url(1): "2026.10.26",
            url(2): "2026.10.26",
            url(3): "2026.11.30",
            url(4): "2026.11.30",
        }
        assert sorted(fake_engine.started[2:]) == [url(3), url(4)]  # both slots free at once
        fake_engine.release()
        wait_for(lambda: all(get_job(client, i)["status"] == "completed" for i in (*ids, late)))
        assert fake_engine.peak == 2

    def test_an_update_with_an_idle_queue_runs_right_away(
        self, client: TestClient, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        response = self.post_update(client)

        assert response.status_code == 202
        assert response.json()["updatePending"] is False
        assert engine.info().versions["yt-dlp"] == "2026.11.30"
        enqueue(client, url(1))  # and the queue was released again
        assert fake_engine.wait_started(1)
        fake_engine.release()

    def test_the_automatic_check_follows_the_same_path(
        self,
        client: TestClient,
        engine: EngineManager,
        fake_engine: FakeEngine,
        clock: FakeClock,
        seen: dict[str, str],
    ) -> None:
        ids = [enqueue(client, url(n)).json()["jobs"][0]["id"] for n in (1, 2, 3)]
        assert fake_engine.wait_running(2)
        clock.advance(hours=25)

        assert engine.tick() == UpdateOutcome.DEFERRED  # what the hourly scheduler does
        assert engine.info().update_pending is True
        assert get_job(client, ids[2])["status"] == "queued"
        assert engine.tick() == UpdateOutcome.BUSY  # the next tick does not pile up

        fake_engine.release_url(url(1))
        fake_engine.release_url(url(2))
        assert fake_engine.wait_started(3)

        assert engine.info().versions["yt-dlp"] == "2026.11.30"
        assert seen[url(3)] == "2026.11.30"
        fake_engine.release()

    def test_a_failed_update_still_resumes_the_queue(
        self,
        client: TestClient,
        engine: EngineManager,
        fake_engine: FakeEngine,
        fetcher: FakeFetcher,
    ) -> None:
        ids = [enqueue(client, url(n)).json()["jobs"][0]["id"] for n in (1, 2, 3)]
        assert fake_engine.wait_running(2)
        assert self.post_update(client).status_code == 202
        fetcher.routes.clear()  # the release cannot be fetched any more

        fake_engine.release_url(url(1))
        fake_engine.release_url(url(2))
        assert fake_engine.wait_started(3)

        assert engine.info().versions["yt-dlp"] == "2026.10.26"
        assert engine.info().update_pending is False
        assert "yt-dlp" in (engine.info().update_message or "")
        fake_engine.release()
        wait_for(lambda: get_job(client, ids[2])["status"] == "completed")
