"""Cancel and retry (ticket 10): queued vs running jobs, TERM vs KILL, the slot, the Engine
update, the cancel/complete race, new Attempts, FIFO and a real process tree.

Real worker threads and a FakeEngine at the subprocess edge. Nothing asserts on elapsed time or on
the start order of jobs launched in parallel: tests wait on conditions.
"""

from __future__ import annotations

import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.engine import EngineManager
from app.engine.io import stream_process
from app.jobs import JobStatus
from app.jobs.queue import NotCancelable, NotRetryable, UnknownJob
from tests.conftest import APP_HEADERS, RecordingBroadcaster
from tests.fake_engine import FakeEngine
from tests.fakes import YTDLP_NEW, FakeFetcher
from tests.test_jobs_api import ZOO, downloads, enqueue, get_job, wait_for
from tests.test_queue import Harness, thread_spawn, url


@pytest.fixture
def harness(tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine) -> Harness:
    engine.install()
    return Harness(tmp_path, engine, fake_engine, cancel_grace=5.0, cancel_kill_wait=5.0)


class TestCancelQueued:
    def test_a_queued_job_is_canceled_and_never_starts(
        self, harness: Harness, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        a, b, waiting = (harness.enqueue(n) for n in (1, 2, 3))
        assert fake_engine.wait_running(2)

        job = harness.queue.cancel(waiting)

        assert job.status is JobStatus.CANCELED
        assert job.finished_at is not None and job.started_at is None
        assert harness.status(waiting) == "canceled"
        assert harness.events.named("job.updated")[-1]["status"] == "canceled"
        assert harness.events.named("queue.updated")[-1] == {"active": 2, "queued": 0}

        fake_engine.release()
        wait_for(lambda: harness.status(a) == harness.status(b) == "completed")
        assert url(3) not in fake_engine.started
        assert harness.status(waiting) == "canceled"

    def test_a_job_canceled_before_it_is_claimed_is_skipped_by_dispatch(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        engine.install()
        harness = Harness(tmp_path, engine, fake_engine)
        harness.queue.hold()
        first, second = harness.enqueue(1), harness.enqueue(2)

        harness.queue.cancel(first)
        harness.queue.release()

        wait_for(lambda: harness.status(second) == "completed")
        assert fake_engine.started == [url(2)]


class TestCancelActive:
    def test_terminates_the_process_removes_staging_and_frees_the_slot(
        self, harness: Harness, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        a, b, waiting = (harness.enqueue(n) for n in (1, 2, 3))
        assert fake_engine.wait_running(2)
        wait_for(lambda: any((harness.staging / a).glob("*")))  # it has a partial file to remove

        job = harness.queue.cancel(a)

        assert job.status is JobStatus.CANCELED  # not failed, not interrupted
        assert job.error is None and job.finished_at is not None
        handle = next(h for h in fake_engine.handles if h.url == harness.repo.get(a).url)
        assert handle.terminated and not handle.killed  # TERM was enough
        assert not (harness.staging / a).exists()
        # The freed slot goes to the next queued job; the other running one is untouched.
        assert fake_engine.wait_started(3)
        assert url(3) in fake_engine.started
        wait_for(lambda: harness.status(waiting) == "downloading")
        assert harness.status(b) == "downloading"
        assert a not in harness.queue.active_ids()
        fake_engine.release()
        wait_for(lambda: harness.status(waiting) == harness.status(b) == "completed")
        assert downloads(harness.downloads) == ["Me at the zoo (2).mp4", "Me at the zoo.mp4"]
        assert harness.status(a) == "canceled"

    def test_kills_a_process_that_ignores_terminate_after_the_grace(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        engine.install()
        fake_engine.default.hold = True
        fake_engine.default.ignore_terminate = True
        harness = Harness(tmp_path, engine, fake_engine, cancel_grace=0.05, cancel_kill_wait=5.0)
        job = harness.enqueue(1)
        assert fake_engine.wait_running(1)

        result = harness.queue.cancel(job)

        (handle,) = fake_engine.handles
        assert handle.terminated and handle.killed
        assert result.status is JobStatus.CANCELED
        assert not (harness.staging / job).exists()
        assert harness.queue.active_ids() == []

    def test_a_process_nothing_can_stop_does_not_hang_the_cancel(
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
            stuck.wait(10)
            return 1

        harness = Harness(
            tmp_path, engine, fake_engine, stream=stream, cancel_grace=0.05, cancel_kill_wait=0.05
        )
        job = harness.enqueue(1)
        wait_for(lambda: harness.queue.handle(job) is not None)

        with pytest.raises(NotCancelable):  # the process is still there: not canceled yet
            harness.queue.cancel(job)

        assert calls == ["terminate", "kill"]
        stuck.set()
        wait_for(lambda: harness.status(job) == "canceled")  # it ends as canceled once it dies

    def test_cancel_before_the_process_exists_never_starts_it(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        engine.install()
        harness = Harness(tmp_path, engine, fake_engine, cancel_grace=5.0)
        harness.deferred_spawn = True  # claimed (downloading) but the worker has not started
        job = harness.enqueue(1)
        result: list = []
        canceling = threading.Thread(target=lambda: result.append(harness.queue.cancel(job)))
        canceling.start()
        wait_for(lambda: harness.queue._is_canceling(job))

        (worker,) = harness.spawned
        worker()
        canceling.join(5)

        assert not canceling.is_alive()
        assert result[0].status is JobStatus.CANCELED
        assert fake_engine.calls == []  # yt-dlp never ran
        assert not (harness.staging / job).exists()

    def test_the_last_cancel_lets_a_pending_engine_update_apply(
        self,
        make_jobs_client,
        engine: EngineManager,
        fake_engine: FakeEngine,
        fetcher: FakeFetcher,
    ) -> None:
        fake_engine.default.hold = True
        client = make_jobs_client(spawn_job=thread_spawn)
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)
        job_id = enqueue(client, url(1)).json()["jobs"][0]["id"]
        assert fake_engine.wait_running(1)
        assert client.post("/api/system/engine/update", headers=APP_HEADERS).status_code == 202
        assert engine.info().update_pending is True

        response = client.post(f"/api/jobs/{job_id}/cancel", headers=APP_HEADERS)

        assert response.status_code == 200
        assert response.json()["status"] == "canceled"
        wait_for(lambda: engine.info().versions["yt-dlp"] == "2026.11.30")
        assert engine.info().update_pending is False


class TestCancelRace:
    """The process decides: exit 0 before the TERM took effect means the job completed."""

    def test_a_download_that_finishes_despite_the_cancel_completes_and_cancel_is_refused(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        engine.install()
        terminated = threading.Event()

        class Handle:
            def terminate(self) -> None:
                terminated.set()

            def kill(self) -> None:
                terminated.set()

        def stream(args, on_stdout, on_stderr, on_start=None) -> int:
            staging = Path(args[args.index("-P") + 1])
            (staging / "done.mp4").write_bytes(b"video")  # the download was already complete
            if on_start:
                on_start(Handle())
            terminated.wait(10)
            return 0

        harness = Harness(tmp_path, engine, fake_engine, stream=stream)
        job = harness.enqueue(1)
        wait_for(lambda: harness.queue.handle(job) is not None)

        with pytest.raises(NotCancelable):
            harness.queue.cancel(job)

        assert harness.status(job) == "completed"
        assert downloads(harness.downloads) == ["done.mp4"]
        assert not (harness.staging / job).exists()

    def test_cancel_after_the_job_ended_is_refused_and_changes_nothing(
        self, harness: Harness
    ) -> None:
        job = harness.enqueue(1)
        wait_for(lambda: harness.status(job) == "completed")

        with pytest.raises(NotCancelable):
            harness.queue.cancel(job)
        with pytest.raises(UnknownJob):
            harness.queue.cancel("nope")

        assert harness.status(job) == "completed"


class TestRetry:
    @pytest.mark.parametrize("status", ["failed", "canceled", "interrupted"])
    def test_each_retryable_status_starts_a_new_attempt(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine, status: str
    ) -> None:
        engine.install()
        harness = Harness(tmp_path, engine, fake_engine)
        harness.queue.hold()  # inspect the requeued job before anything runs
        job = harness.enqueue(1)
        harness.repo.update(
            job,
            status=status,
            progress_percent=40.0,
            downloaded_bytes=10,
            total_bytes=25,
            speed=3.0,
            eta=4,
            output_path="/x/old.mp4",
            error="boom",
            started_at="s",
            finished_at="f",
        )

        retried = harness.queue.retry(job)

        assert retried.status in (JobStatus.QUEUED, JobStatus.DOWNLOADING)
        fresh = harness.repo.get(job)
        assert fresh is not None
        assert fresh.attempt == 2
        assert (fresh.progress_percent, fresh.downloaded_bytes, fresh.total_bytes) == (
            0,
            None,
            None,
        )
        assert (fresh.speed, fresh.eta, fresh.output_path, fresh.error) == (None, None, None, None)
        assert (fresh.finished_at, fresh.url, fresh.quality) == (None, url(1), "best")
        assert harness.events.named("job.updated")[-1]["attempt"] == 2

    def test_a_failed_job_retried_over_http_completes_with_one_file(
        self, make_jobs_client, fake_engine: FakeEngine, download_dir: Path, data_dir: Path
    ) -> None:
        client = make_jobs_client()
        fake_engine.scenario(ZOO, fail_with="ERROR: [youtube] jNQXAC9IVRw: Video unavailable")
        job_id = enqueue(client).json()["jobs"][0]["id"]
        assert get_job(client, job_id)["status"] == "failed"
        stale = data_dir / "staging" / job_id
        stale.mkdir(parents=True)  # leftovers an old Attempt must not hand to the new one
        (stale / "stale.mp4").write_bytes(b"old")
        fake_engine.scenarios.clear()

        response = client.post(f"/api/jobs/{job_id}/retry", headers=APP_HEADERS)

        assert response.status_code == 200
        assert response.json()["attempt"] == 2
        job = get_job(client, job_id)
        assert job["status"] == "completed" and job["attempt"] == 2
        assert job["error"] is None and job["progressPercent"] == 100.0
        assert downloads(download_dir) == ["Me at the zoo.mp4"]
        assert not stale.exists()

    def test_a_canceled_running_job_can_be_retried_and_completes(
        self, harness: Harness, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        job = harness.enqueue(1)
        assert fake_engine.wait_running(1)
        harness.queue.cancel(job)

        fake_engine.default.hold = False
        harness.queue.retry(job)

        wait_for(lambda: harness.status(job) == "completed")
        assert harness.repo.get(job).attempt == 2  # type: ignore[union-attr]
        assert downloads(harness.downloads) == ["Me at the zoo.mp4"]

    def test_a_retry_goes_to_the_end_of_the_queue(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        engine.install()
        frozen = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)  # a coarse clock must not matter
        harness = Harness(tmp_path, engine, fake_engine, now=lambda: frozen)
        fake_engine.default.hold = True
        ids = [harness.enqueue(n) for n in range(1, 5)]
        assert fake_engine.wait_running(2)
        harness.queue.cancel(ids[2])  # the third one gives up its place...

        harness.queue.retry(ids[2])  # ...and comes back after the fourth

        fake_engine.release_url(url(1))
        assert fake_engine.wait_started(3)
        assert fake_engine.started[2] == url(4)
        fake_engine.release_url(url(2))
        assert fake_engine.wait_started(4)
        assert fake_engine.started[3] == url(3)
        fake_engine.release()
        wait_for(lambda: all(harness.status(i) == "completed" for i in ids))

    def test_a_retry_keeps_its_batch_index_and_options(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        engine.install()
        harness = Harness(tmp_path, engine, fake_engine)
        harness.queue.hold()
        batch, jobs = harness.queue.enqueue_batch(
            source_url="https://www.youtube.com/playlist?list=PLabc",
            title="Lista",
            folder_name="Lista",
            entries=[{"url": url(1), "index": 3, "title": "Uno"}],
            mode="audio",
            quality=None,
            audio_format="mp3",
        )
        (job,) = jobs
        harness.repo.update(job.id, status="failed", error="x")

        harness.queue.retry(job.id)

        fresh = harness.repo.get(job.id)
        assert fresh is not None
        assert (fresh.batch_id, fresh.playlist_index) == (batch.id, 3)
        assert (fresh.mode, fresh.audio_format, fresh.title) == ("audio", "mp3", "Uno")
        assert fresh.created_at == job.created_at  # the History keeps the original position
        assert fresh.queued_at is not None and fresh.queued_at > job.created_at

    @pytest.mark.parametrize("status", ["queued", "downloading", "processing", "completed"])
    def test_other_states_are_not_retryable(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine, status: str
    ) -> None:
        engine.install()
        harness = Harness(tmp_path, engine, fake_engine)
        harness.queue.hold()
        job = harness.enqueue(1)
        harness.repo.update(job, status=status)

        with pytest.raises(NotRetryable):
            harness.queue.retry(job)

        fresh = harness.repo.get(job)
        assert fresh is not None and (fresh.status.value, fresh.attempt) == (status, 1)


class TestApi:
    def seeded(self, make_jobs_client, status: str):
        client = make_jobs_client(spawn_job=lambda fn: None)
        job = client.app.state.jobs.create(url=ZOO, mode="video", quality="best")
        client.app.state.jobs.update(job.id, status=status)
        return client, job.id

    def test_cancel_a_queued_job(self, make_jobs_client, events: RecordingBroadcaster) -> None:
        client = make_jobs_client(spawn_job=lambda fn: None)
        client.app.state.queue.hold()  # stays queued instead of being claimed
        job_id = enqueue(client).json()["jobs"][0]["id"]

        response = client.post(f"/api/jobs/{job_id}/cancel", headers=APP_HEADERS)

        assert response.status_code == 200
        assert response.json()["status"] == "canceled"
        assert events.named("job.updated")[-1]["status"] == "canceled"

    @pytest.mark.parametrize("status", ["completed", "failed", "canceled", "interrupted"])
    def test_cancel_a_finished_job_is_409(self, make_jobs_client, status: str) -> None:
        client, job_id = self.seeded(make_jobs_client, status)

        response = client.post(f"/api/jobs/{job_id}/cancel", headers=APP_HEADERS)

        assert response.status_code == 409
        assert response.json()["code"] == "job_not_cancelable"
        assert get_job(client, job_id)["status"] == status

    @pytest.mark.parametrize("status", ["queued", "downloading", "processing", "completed"])
    def test_retry_of_a_job_that_is_not_over_or_succeeded_is_409(
        self, make_jobs_client, status: str
    ) -> None:
        client, job_id = self.seeded(make_jobs_client, status)

        response = client.post(f"/api/jobs/{job_id}/retry", headers=APP_HEADERS)

        assert response.status_code == 409
        assert response.json()["code"] == "job_not_retryable"
        assert get_job(client, job_id)["attempt"] == 1

    @pytest.mark.parametrize("action", ["cancel", "retry"])
    def test_an_unknown_job_is_404(self, jobs_client, action: str) -> None:
        response = jobs_client.post(f"/api/jobs/nope/{action}", headers=APP_HEADERS)

        assert response.status_code == 404
        assert response.json()["code"] == "job_not_found"

    @pytest.mark.parametrize("action", ["cancel", "retry"])
    def test_the_commands_need_the_app_header(self, jobs_client, action: str) -> None:
        assert jobs_client.post(f"/api/jobs/x/{action}").status_code == 403

    def test_retry_of_a_failed_job_is_published_and_queued(
        self, make_jobs_client, events: RecordingBroadcaster
    ) -> None:
        client, job_id = self.seeded(make_jobs_client, "failed")

        response = client.post(f"/api/jobs/{job_id}/retry", headers=APP_HEADERS)

        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        assert events.named("job.updated")[-1]["attempt"] == 2


@pytest.mark.skipif(sys.platform == "win32", reason="process groups; Windows uses taskkill /T")
class TestRealProcessTree:
    """A real parent with a real child, like yt-dlp with ffmpeg: nothing may survive the cancel."""

    PARENT = """
import signal, subprocess, sys, time
ignore = sys.argv[1] == "ignore"
mute = "signal.signal(signal.SIGTERM, signal.SIG_IGN)" if ignore else ""
child_code = f"import signal, time\\n{mute}\\ntime.sleep(60)"
child = subprocess.Popen([sys.executable, "-c", child_code])
if ignore:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(0.2)  # let the child install its handler
print(child.pid, flush=True)
time.sleep(60)
"""

    @staticmethod
    def alive(pid: int) -> bool:
        try:
            with open(f"/proc/{pid}/stat") as f:
                return f.read().rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            return False

    def run_cancel(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine, mode: str, **opts
    ) -> tuple[Harness, str, list[int]]:
        engine.install()
        pids: list[int] = []

        def stream(args, on_stdout, on_stderr, on_start=None) -> int:
            def out(line: str) -> None:
                pids.append(int(line))
                on_stdout(line)

            return stream_process(
                [sys.executable, "-c", self.PARENT, mode], out, on_stderr, on_start
            )

        harness = Harness(tmp_path, engine, fake_engine, stream=stream, **opts)
        job = harness.enqueue(1)
        wait_for(lambda: bool(pids))
        child = pids[0]
        assert self.alive(child)
        harness.queue.cancel(job)
        return harness, job, pids

    def test_terminate_leaves_no_orphans(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        harness, job, pids = self.run_cancel(tmp_path, engine, fake_engine, "plain")

        assert harness.status(job) == "canceled"
        wait_for(lambda: not self.alive(pids[0]))
        assert not (harness.staging / job).exists()

    def test_kill_after_the_grace_leaves_no_orphans_when_terminate_is_ignored(
        self, tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine
    ) -> None:
        harness, job, pids = self.run_cancel(
            tmp_path, engine, fake_engine, "ignore", cancel_grace=0.3, cancel_kill_wait=10.0
        )

        assert harness.status(job) == "canceled"
        wait_for(lambda: not self.alive(pids[0]))
