"""History (ticket 11): terminal jobs apart from the Queue, removal, reveal.

Jobs run inline over the FakeEngine; nothing here waits on time.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.opener import OpenUnavailable
from tests.conftest import APP_HEADERS, RecordingBroadcaster
from tests.fake_engine import FakeEngine
from tests.test_jobs_api import SHORT, ZOO, downloads, enqueue
from tests.test_playlist_jobs import enqueue_playlist, entry, video_url

TERMINAL = "completed,failed,canceled,interrupted"
IN_PROGRESS = "queued,downloading,processing"


def ids(client: TestClient, status: str, **params) -> list[str]:
    response = client.get("/api/jobs", params={"status": status, **params})
    return [j["id"] for j in response.json()["jobs"]]


class TestHistoryVersusQueue:
    def test_terminal_jobs_are_the_history_and_the_rest_the_queue(
        self, make_jobs_client, fake_engine: FakeEngine
    ) -> None:
        fake_engine.scenario(SHORT, fail_with="ERROR: boom")
        client = make_jobs_client()
        done = enqueue(client, ZOO).json()["jobs"][0]["id"]
        failed = enqueue(client, SHORT).json()["jobs"][0]["id"]
        # a client whose jobs never start: they stay queued
        waiting_client = make_jobs_client(spawn_job=lambda fn: None)
        waiting = enqueue(waiting_client, "https://www.youtube.com/watch?v=aaaaaaaaaaa")
        waiting_id = waiting.json()["jobs"][0]["id"]

        assert ids(client, TERMINAL) == [failed, done]
        assert ids(client, IN_PROGRESS) == [waiting_id]

    def test_the_history_pages_newest_first_and_follows_the_cursor(self, make_jobs_client) -> None:
        client = make_jobs_client()
        created = [
            enqueue(client, f"https://www.youtube.com/watch?v={n:011d}").json()["jobs"][0]["id"]
            for n in range(5)
        ]
        newest_first = list(reversed(created))

        first = client.get("/api/jobs", params={"status": TERMINAL, "limit": 2}).json()
        second = client.get(
            "/api/jobs", params={"status": TERMINAL, "limit": 2, "before": first["nextBefore"]}
        ).json()
        last = client.get(
            "/api/jobs", params={"status": TERMINAL, "limit": 2, "before": second["nextBefore"]}
        ).json()

        pages = [first, second, last]
        assert [[j["id"] for j in p["jobs"]] for p in pages] == [
            newest_first[:2],
            newest_first[2:4],
            newest_first[4:],
        ]
        assert last["nextBefore"] is None

    def test_the_history_survives_a_restart(self, make_jobs_client) -> None:
        first_run = make_jobs_client()
        job_id = enqueue(first_run).json()["jobs"][0]["id"]

        restarted = make_jobs_client()

        assert ids(restarted, TERMINAL) == [job_id]


class TestRemove:
    def test_removes_a_terminal_job_and_keeps_its_file(
        self, make_jobs_client, download_dir: Path, events: RecordingBroadcaster
    ) -> None:
        client = make_jobs_client()
        job_id = enqueue(client).json()["jobs"][0]["id"]

        response = client.delete(f"/api/jobs/{job_id}", headers=APP_HEADERS)

        assert response.status_code == 200
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert ids(client, TERMINAL) == []
        assert downloads(download_dir) == ["Me at the zoo.mp4"]  # the file stays
        assert events.named("job.removed") == [{"id": job_id}]

    def test_every_terminal_status_can_be_removed(self, make_jobs_client, fake_engine) -> None:
        fake_engine.scenario(SHORT, fail_with="ERROR: boom")
        client = make_jobs_client()
        failed = enqueue(client, SHORT).json()["jobs"][0]["id"]

        assert client.delete(f"/api/jobs/{failed}", headers=APP_HEADERS).status_code == 200

    def test_a_job_that_is_not_terminal_answers_409_and_stays(
        self, make_jobs_client, events: RecordingBroadcaster
    ) -> None:
        client = make_jobs_client(spawn_job=lambda fn: None)
        job_id = enqueue(client).json()["jobs"][0]["id"]

        response = client.delete(f"/api/jobs/{job_id}", headers=APP_HEADERS)

        assert response.status_code == 409
        assert response.json()["code"] == "job_not_removable"
        assert client.get(f"/api/jobs/{job_id}").status_code == 200
        assert events.named("job.removed") == []

    def test_an_unknown_job_is_404(self, jobs_client: TestClient) -> None:
        response = jobs_client.delete("/api/jobs/nope", headers=APP_HEADERS)

        assert response.status_code == 404
        assert response.json()["code"] == "job_not_found"

    def test_the_batch_goes_with_its_last_job(self, make_jobs_client, data_dir: Path) -> None:
        client = make_jobs_client()
        body = enqueue_playlist(client, [entry(1), entry(2)]).json()
        batch_id, jobs = body["batchId"], body["jobs"]
        repo = client.app.state.jobs

        client.delete(f"/api/jobs/{jobs[0]['id']}", headers=APP_HEADERS)
        assert repo.get_batch(batch_id) is not None  # one job still belongs to it

        client.delete(f"/api/jobs/{jobs[1]['id']}", headers=APP_HEADERS)
        assert repo.get_batch(batch_id) is None

    def test_removing_does_not_touch_other_jobs_of_the_batch(self, make_jobs_client) -> None:
        client = make_jobs_client()
        jobs = enqueue_playlist(client, [entry(1), entry(2)]).json()["jobs"]

        client.delete(f"/api/jobs/{jobs[0]['id']}", headers=APP_HEADERS)

        remaining = client.get("/api/jobs").json()["jobs"]
        assert [j["id"] for j in remaining] == [jobs[1]["id"]]
        assert remaining[0]["batchTitle"] == "Select Lectures"
        assert video_url(2) in remaining[0]["url"]


class TestReveal:
    def test_shows_the_file_of_a_completed_job(self, make_jobs_client, download_dir: Path) -> None:
        shown: list[Path] = []
        client = make_jobs_client(reveal_in_host=shown.append)
        job_id = enqueue(client).json()["jobs"][0]["id"]

        response = client.post(f"/api/jobs/{job_id}/reveal", headers=APP_HEADERS)

        assert response.status_code == 200
        assert shown == [download_dir / "Me at the zoo.mp4"]

    def test_404_file_missing_when_the_file_was_moved_or_deleted(
        self, make_jobs_client, download_dir: Path
    ) -> None:
        shown: list[Path] = []
        client = make_jobs_client(reveal_in_host=shown.append)
        job_id = enqueue(client).json()["jobs"][0]["id"]
        (download_dir / "Me at the zoo.mp4").unlink()

        response = client.post(f"/api/jobs/{job_id}/reveal", headers=APP_HEADERS)

        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "file_missing"
        assert "archivo" in body["message"]
        assert shown == []

    def test_501_where_there_is_no_opener(self, make_jobs_client) -> None:
        def unavailable(path: Path) -> None:
            raise OpenUnavailable("linux")

        client = make_jobs_client(reveal_in_host=unavailable)
        job_id = enqueue(client).json()["jobs"][0]["id"]

        response = client.post(f"/api/jobs/{job_id}/reveal", headers=APP_HEADERS)

        assert response.status_code == 501
        assert response.json()["code"] == "open_unavailable"

    def test_500_when_the_file_manager_fails(self, make_jobs_client) -> None:
        def broken(path: Path) -> None:
            raise subprocess.CalledProcessError(1, "open")

        client = make_jobs_client(reveal_in_host=broken)
        job_id = enqueue(client).json()["jobs"][0]["id"]

        response = client.post(f"/api/jobs/{job_id}/reveal", headers=APP_HEADERS)

        assert response.status_code == 500
        assert response.json()["code"] == "open_failed"

    def test_only_completed_jobs_have_a_file(self, make_jobs_client) -> None:
        shown: list[Path] = []
        client = make_jobs_client(spawn_job=lambda fn: None, reveal_in_host=shown.append)
        job_id = enqueue(client).json()["jobs"][0]["id"]

        response = client.post(f"/api/jobs/{job_id}/reveal", headers=APP_HEADERS)

        assert response.status_code == 409
        assert response.json()["code"] == "job_not_completed"
        assert shown == []

    def test_unknown_job_is_404(self, jobs_client: TestClient) -> None:
        response = jobs_client.post("/api/jobs/nope/reveal", headers=APP_HEADERS)

        assert response.status_code == 404
        assert response.json()["code"] == "job_not_found"
