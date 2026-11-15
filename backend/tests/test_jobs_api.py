"""POST/GET /api/jobs with a FakeEngine at the subprocess edge. No network, no real binaries."""

from __future__ import annotations

import errno
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.jobs.failures import GENERIC
from app.opener import OpenUnavailable
from tests.conftest import APP_HEADERS, RecordingBroadcaster
from tests.fake_engine import FakeEngine

ZOO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
SHORT = "https://www.youtube.com/watch?v=Jt5fgKBqZSY"


def enqueue(client: TestClient, url: str = ZOO, **body):
    payload = {"url": url, "mode": "video", "quality": "best", **body}
    return client.post("/api/jobs", json=payload, headers=APP_HEADERS)


def get_job(client: TestClient, job_id: str) -> dict:
    return client.get(f"/api/jobs/{job_id}").json()


def wait_for(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the condition"
        time.sleep(0.01)


def downloads(download_dir: Path) -> list[str]:
    return sorted(p.name for p in download_dir.iterdir()) if download_dir.exists() else []


class TestCreate:
    def test_a_single_video_has_no_batch_and_is_queued(self, make_jobs_client) -> None:
        # a spawn that never runs: the job stays as it was created
        client = make_jobs_client(spawn_job=lambda fn: None)

        response = enqueue(client, title="Me at the zoo")

        assert response.status_code == 200
        body = response.json()
        assert body["batchId"] is None
        (job,) = body["jobs"]
        assert job["batchId"] is None
        assert job["url"] == ZOO
        assert job["title"] == "Me at the zoo"
        assert job["mode"] == "video"
        assert job["quality"] == "best"
        assert job["status"] == "queued" or job["status"] == "downloading"
        assert job["attempt"] == 1
        assert set(job) >= {
            "id",
            "playlistIndex",
            "audioFormat",
            "progressPercent",
            "downloadedBytes",
            "totalBytes",
            "speed",
            "eta",
            "outputPath",
            "error",
            "createdAt",
            "startedAt",
            "finishedAt",
        }

    def test_the_url_is_normalized_and_the_quality_defaults_to_best(
        self, jobs_client: TestClient
    ) -> None:
        response = jobs_client.post(
            "/api/jobs",
            json={"url": "youtu.be/jNQXAC9IVRw?si=abc", "mode": "video"},
            headers=APP_HEADERS,
        )

        job = response.json()["jobs"][0]
        assert job["url"] == ZOO
        assert job["quality"] == "best"

    @pytest.mark.parametrize(
        ("url", "code"),
        [
            ("https://vimeo.com/1", "unsupported_site"),
            ("not a url", "invalid_url"),
            ("https://www.youtube.com/watch?v=abc", "invalid_url"),
            ("https://www.youtube.com/playlist?list=RDabcdef", "mix_playlist"),
            ("https://www.youtube.com/playlist?list=PLabcdef", "playlist_unsupported"),
        ],
    )
    def test_rejects_urls_the_classifier_rejects(
        self, jobs_client: TestClient, fake_engine: FakeEngine, url: str, code: str
    ) -> None:
        response = enqueue(jobs_client, url)

        assert response.status_code == 422
        assert response.json()["code"] == code
        assert jobs_client.get("/api/jobs").json()["jobs"] == []
        assert fake_engine.calls == []

    def test_audio_is_refused_until_ticket_07(
        self, jobs_client: TestClient, fake_engine: FakeEngine
    ) -> None:
        response = jobs_client.post(
            "/api/jobs",
            json={"url": ZOO, "mode": "audio", "audioFormat": "mp3"},
            headers=APP_HEADERS,
        )

        assert response.status_code == 422
        assert response.json()["code"] == "audio_unsupported"
        assert response.json()["message"]
        assert fake_engine.calls == []

    def test_an_unknown_quality_is_a_validation_error(self, jobs_client: TestClient) -> None:
        response = enqueue(jobs_client, quality="4k")

        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    def test_requires_the_app_header(self, jobs_client: TestClient) -> None:
        response = jobs_client.post("/api/jobs", json={"url": ZOO, "mode": "video"})

        assert response.status_code == 403


class TestEngineNotReady:
    def test_answers_engine_not_ready_and_creates_nothing(
        self, make_jobs_client, fake_engine: FakeEngine
    ) -> None:
        client = make_jobs_client(ready=False)

        response = enqueue(client)

        assert response.status_code == 409
        assert response.json()["code"] == "engine_not_ready"
        assert client.get("/api/jobs").json()["jobs"] == []
        assert fake_engine.calls == []


class TestHappyPath:
    def test_completes_only_with_the_file_in_the_destination_and_empty_staging(
        self, jobs_client: TestClient, download_dir: Path, data_dir: Path
    ) -> None:
        job_id = enqueue(jobs_client, title="x").json()["jobs"][0]["id"]

        job = get_job(jobs_client, job_id)

        assert job["status"] == "completed"
        assert job["outputPath"] == str(download_dir / "Me at the zoo.mp4")
        assert (download_dir / "Me at the zoo.mp4").read_bytes() == b"fake-video-bytes"
        assert downloads(download_dir) == ["Me at the zoo.mp4"]
        assert job["progressPercent"] == 100.0
        assert job["finishedAt"] and job["startedAt"] and job["error"] is None
        assert not (data_dir / "staging" / job_id).exists()

    def test_the_file_is_in_the_destination_before_the_job_is_completed(
        self, make_jobs_client, download_dir: Path, events: RecordingBroadcaster
    ) -> None:
        client = make_jobs_client()
        seen: list[tuple[str, bool]] = []
        original = events.publish

        def spy(name: str, data) -> None:
            if name == "job.updated":
                seen.append((data["status"], (download_dir / "Me at the zoo.mp4").exists()))
            original(name, data)

        events.publish = spy  # type: ignore[method-assign]
        enqueue(client)

        completed = [present for status, present in seen if status == "completed"]
        others = [present for status, present in seen if status != "completed"]
        assert completed == [True]
        assert not any(others)

    def test_passes_the_requested_quality_to_yt_dlp(
        self, jobs_client: TestClient, fake_engine: FakeEngine
    ) -> None:
        enqueue(jobs_client, quality="720p")

        args = fake_engine.calls[0]
        assert args[args.index("-S") + 1] == "res:720,vcodec:h264,acodec:aac"
        assert args[-1] == ZOO

    def test_statuses_go_through_downloading_processing_completed(
        self, jobs_client: TestClient, events: RecordingBroadcaster
    ) -> None:
        job_id = enqueue(jobs_client).json()["jobs"][0]["id"]

        statuses = [d["status"] for d in events.named("job.updated") if d["id"] == job_id]

        deduped = [s for i, s in enumerate(statuses) if i == 0 or s != statuses[i - 1]]
        assert deduped == ["queued", "downloading", "processing", "completed"]

    def test_progress_aggregates_both_streams(
        self, jobs_client: TestClient, events: RecordingBroadcaster
    ) -> None:
        enqueue(jobs_client)

        # The clock is frozen: throttled lines wait for the status change, which flushes them.
        updates = [d for d in events.named("job.updated") if d["status"] != "queued"]
        processing = next(d for d in updates if d["status"] == "processing")
        assert (processing["downloadedBytes"], processing["totalBytes"]) == (5000, 5000)
        assert processing["speed"] == 1_000_000.0
        percents = [d["progressPercent"] for d in updates]
        assert percents == sorted(percents)

    def test_queue_updated_follows_the_active_and_queued_counts(
        self, jobs_client: TestClient, events: RecordingBroadcaster
    ) -> None:
        enqueue(jobs_client)

        queue = events.named("queue.updated")
        assert {"active": 1, "queued": 0} in queue
        assert queue[-1] == {"active": 0, "queued": 0}


class TestFailure:
    def test_a_failed_job_has_a_sanitized_message_and_no_staging(
        self,
        jobs_client: TestClient,
        fake_engine: FakeEngine,
        data_dir: Path,
        download_dir: Path,
    ) -> None:
        fake_engine.scenario(
            ZOO,
            fail_with=(
                "ERROR: [youtube] jNQXAC9IVRw: unable to download video data: "
                "<urlopen error timed out> at /downloads/secret/path.py line 12 token=abc123"
            ),
        )

        job_id = enqueue(jobs_client).json()["jobs"][0]["id"]
        job = get_job(jobs_client, job_id)

        assert job["status"] == "failed"
        assert job["error"] == "Se interrumpió la conexión con YouTube. Inténtalo de nuevo."
        for leak in ("/downloads", "abc123", "urlopen", "line 12"):
            assert leak not in job["error"]
        assert job["finishedAt"]
        assert not (data_dir / "staging" / job_id).exists()
        assert downloads(download_dir) == []

    @pytest.mark.parametrize(
        ("stderr", "expected"),
        [
            (
                "ERROR: [youtube] x: Private video. Sign in if you've been granted access",
                "no es público",
            ),
            ("ERROR: [youtube] x: Video unavailable", "no está disponible"),
            ("ERROR: [youtube] x: Sign in to confirm you're not a bot", "bloqueó temporalmente"),
            ("ERROR: unable to write data: [Errno 28] No space left on device", "espacio"),
            ("ERROR: Postprocessing: ffmpeg exited with code 1", "procesar el video"),
            ('Traceback (most recent call last):\n  File "/x.py", line 1', GENERIC),
        ],
    )
    def test_common_yt_dlp_errors_get_a_spanish_message(
        self, jobs_client: TestClient, fake_engine: FakeEngine, stderr: str, expected: str
    ) -> None:
        fake_engine.scenario(ZOO, fail_with=stderr)

        job_id = enqueue(jobs_client).json()["jobs"][0]["id"]

        error = get_job(jobs_client, job_id)["error"]
        assert expected in error
        assert "Traceback" not in error and "/x.py" not in error

    def test_a_process_that_cannot_start_fails_the_job(
        self, jobs_client: TestClient, fake_engine: FakeEngine
    ) -> None:
        fake_engine.start_error = "[Errno 2] No such file or directory: '/data/bin/yt-dlp'"

        job = get_job(jobs_client, enqueue(jobs_client).json()["jobs"][0]["id"])

        assert job["status"] == "failed"
        assert job["error"] == GENERIC

    def test_a_missing_output_file_fails_the_job(
        self, jobs_client: TestClient, fake_engine: FakeEngine, download_dir: Path
    ) -> None:
        fake_engine.scenario(ZOO, no_path=True, postprocessors=())
        original = fake_engine._run

        def run_without_file(sc, staging, on_stdout, on_stderr):
            code = original(sc, staging, on_stdout, on_stderr)
            for f in staging.iterdir():
                f.unlink()
            return code

        fake_engine._run = run_without_file  # type: ignore[method-assign]

        job = get_job(jobs_client, enqueue(jobs_client).json()["jobs"][0]["id"])

        assert job["status"] == "failed"
        assert "no se encontró el archivo" in job["error"]

    def test_a_failure_does_not_stop_the_next_job(
        self, jobs_client: TestClient, fake_engine: FakeEngine
    ) -> None:
        fake_engine.scenario(ZOO, fail_with="ERROR: boom")

        enqueue(jobs_client, ZOO)
        second = enqueue(jobs_client, SHORT).json()["jobs"][0]["id"]

        assert get_job(jobs_client, second)["status"] == "completed"


class TestCollisions:
    def test_the_same_title_twice_gives_two_files(
        self, jobs_client: TestClient, download_dir: Path
    ) -> None:
        enqueue(jobs_client)
        enqueue(jobs_client)

        assert downloads(download_dir) == ["Me at the zoo (2).mp4", "Me at the zoo.mp4"]

    def test_simultaneous_downloads_with_the_same_title_give_distinct_files(
        self, make_jobs_client, fake_engine: FakeEngine, download_dir: Path
    ) -> None:
        client = make_jobs_client(spawn_job=lambda fn: threading.Thread(target=fn).start())
        fake_engine.default.hold = True

        ids = [enqueue(client, u).json()["jobs"][0]["id"] for u in (ZOO, SHORT)]
        assert fake_engine.wait_running(2)  # both inside yt-dlp at once, same title
        fake_engine.release()
        wait_for(lambda: all(get_job(client, i)["status"] == "completed" for i in ids))

        assert downloads(download_dir) == ["Me at the zoo (2).mp4", "Me at the zoo.mp4"]
        paths = {get_job(client, i)["outputPath"] for i in ids}
        assert len(paths) == 2

    def test_works_across_volumes(
        self, make_jobs_client, download_dir: Path, data_dir: Path
    ) -> None:
        def cross_device(src: Path, dst: Path) -> None:
            raise OSError(errno.EXDEV, "Invalid cross-device link")

        client = make_jobs_client(rename=cross_device)

        job_id = enqueue(client).json()["jobs"][0]["id"]

        assert get_job(client, job_id)["status"] == "completed"
        assert downloads(download_dir) == ["Me at the zoo.mp4"]
        assert not (data_dir / "staging" / job_id).exists()


class TestDispatcher:
    def test_runs_at_most_two_at_a_time_and_keeps_the_rest_queued(
        self, make_jobs_client, fake_engine: FakeEngine
    ) -> None:
        client = make_jobs_client(spawn_job=lambda fn: threading.Thread(target=fn).start())
        fake_engine.default.hold = True
        urls = [f"https://www.youtube.com/watch?v={c * 11}" for c in "abc"]

        ids = [enqueue(client, u).json()["jobs"][0]["id"] for u in urls]
        assert fake_engine.wait_running(2)

        statuses = [get_job(client, i)["status"] for i in ids]
        assert statuses == ["downloading", "downloading", "queued"]
        fake_engine.release()
        wait_for(lambda: all(get_job(client, i)["status"] == "completed" for i in ids))

    def test_queued_jobs_resume_at_startup_and_orphan_staging_is_removed(
        self, make_jobs_client, data_dir: Path, download_dir: Path
    ) -> None:
        orphan = data_dir / "staging" / "deadbeef"
        orphan.mkdir(parents=True)
        (orphan / "x.mp4.part").write_bytes(b"x")
        client = make_jobs_client(spawn_job=lambda fn: None)  # nothing runs while enqueuing
        job_id = enqueue(client).json()["jobs"][0]["id"]
        assert get_job(client, job_id)["status"] in ("queued", "downloading")
        client.app.state.jobs.update(job_id, status="queued")  # as if the app had been closed

        again = make_jobs_client(spawn_job=lambda fn: fn())
        with again:  # lifespan: clean staging, resume the queue
            wait_for(lambda: get_job(again, job_id)["status"] == "completed")

        assert not orphan.exists()
        assert downloads(download_dir) == ["Me at the zoo.mp4"]


class TestListing:
    def test_lists_newest_first_with_status_filter_and_pagination(
        self, jobs_client: TestClient, fake_engine: FakeEngine
    ) -> None:
        fake_engine.scenario(SHORT, fail_with="ERROR: boom")
        first = enqueue(jobs_client, ZOO).json()["jobs"][0]["id"]
        second = enqueue(jobs_client, SHORT).json()["jobs"][0]["id"]
        third = enqueue(jobs_client, ZOO).json()["jobs"][0]["id"]

        everything = jobs_client.get("/api/jobs").json()
        assert [j["id"] for j in everything["jobs"]] == [third, second, first]
        assert everything["nextBefore"] is None

        failed = jobs_client.get("/api/jobs", params={"status": "failed"}).json()
        assert [j["id"] for j in failed["jobs"]] == [second]
        both = jobs_client.get("/api/jobs", params={"status": "failed,completed"}).json()
        assert len(both["jobs"]) == 3

        page = jobs_client.get("/api/jobs", params={"limit": 2}).json()
        assert [j["id"] for j in page["jobs"]] == [third, second]
        assert page["nextBefore"] == second
        rest = jobs_client.get("/api/jobs", params={"limit": 2, "before": second}).json()
        assert [j["id"] for j in rest["jobs"]] == [first]
        assert rest["nextBefore"] is None

    def test_limit_is_bounded(self, jobs_client: TestClient) -> None:
        assert jobs_client.get("/api/jobs", params={"limit": 0}).status_code == 422
        assert jobs_client.get("/api/jobs", params={"limit": 5000}).status_code == 422

    def test_unknown_job_is_404(self, jobs_client: TestClient) -> None:
        response = jobs_client.get("/api/jobs/nope")

        assert response.status_code == 404
        assert response.json()["code"] == "job_not_found"


class TestOpenDownloads:
    def test_opens_the_download_folder(self, make_jobs_client, download_dir: Path) -> None:
        opened: list[Path] = []
        client = make_jobs_client(open_folder_in_host=opened.append)

        response = client.post("/api/system/open-downloads", headers=APP_HEADERS)

        assert response.status_code == 200
        assert response.json() == {"status": "opened"}
        assert opened == [download_dir]
        assert download_dir.is_dir()

    def test_says_so_where_it_is_unavailable(self, make_jobs_client) -> None:
        def unavailable(path: Path) -> None:
            raise OpenUnavailable("linux")

        client = make_jobs_client(open_folder_in_host=unavailable)

        response = client.post("/api/system/open-downloads", headers=APP_HEADERS)

        assert response.status_code == 501
        body = response.json()
        assert body["code"] == "open_unavailable"
        assert "escritorio" in body["message"]

    def test_reports_a_file_manager_failure(self, make_jobs_client) -> None:
        def broken(path: Path) -> None:
            raise OSError("boom")

        client = make_jobs_client(open_folder_in_host=broken)

        response = client.post("/api/system/open-downloads", headers=APP_HEADERS)

        assert response.status_code == 500
        assert response.json()["code"] == "open_failed"
