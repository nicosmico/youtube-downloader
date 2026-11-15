"""POST /api/jobs for a playlist (Batch) with a FakeEngine at the subprocess edge."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import APP_HEADERS
from tests.fake_engine import FakeEngine
from tests.test_jobs_api import get_job, wait_for

PLAYLIST = "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
CHANNEL = "https://www.youtube.com/@Fireship"


def video_url(n: int) -> str:
    return f"https://www.youtube.com/watch?v={n:011d}"


def entry(index: int, title: str | None = None) -> dict:
    return {
        "id": f"{index:011d}",
        "url": video_url(index),
        "index": index,
        "title": title or f"Video {index}",
    }


def enqueue_playlist(
    client: TestClient, entries: list[dict], url: str = PLAYLIST, title="Select Lectures", **body
):
    payload = {
        "url": url,
        "mode": "audio",
        "audioFormat": "m4a",
        "title": title,
        "entries": entries,
        **body,
    }
    return client.post("/api/jobs", json=payload, headers=APP_HEADERS)


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


@pytest.fixture
def titled(fake_engine: FakeEngine) -> FakeEngine:
    """Each entry downloads a file named after it, like yt-dlp's `%(title)s.%(ext)s`."""
    for n in (1, 2, 3, 12, 120):
        fake_engine.scenario(video_url(n), title=f"Video {n}", ext="m4a")
    return fake_engine


class TestCreateBatch:
    def test_creates_a_batch_and_one_job_per_entry(self, make_jobs_client) -> None:
        client = make_jobs_client(spawn_job=lambda fn: None)

        response = enqueue_playlist(client, [entry(1), entry(3)])

        assert response.status_code == 200
        body = response.json()
        assert body["batchId"]
        jobs = body["jobs"]
        assert [j["playlistIndex"] for j in jobs] == [1, 3]
        assert {j["batchId"] for j in jobs} == {body["batchId"]}
        assert [j["url"] for j in jobs] == [video_url(1), video_url(3)]
        assert [j["title"] for j in jobs] == ["Video 1", "Video 3"]
        assert all(j["mode"] == "audio" and j["audioFormat"] == "m4a" for j in jobs)
        assert {(j["batchTitle"], j["batchEntryCount"]) for j in jobs} == {("Select Lectures", 2)}

    def test_the_batch_is_persisted_with_its_folder(self, make_jobs_client) -> None:
        client = make_jobs_client(spawn_job=lambda fn: None)

        batch_id = enqueue_playlist(client, [entry(1)], title='AC/DC: "Live"?').json()["batchId"]

        batch = client.app.state.jobs.get_batch(batch_id)
        assert (batch.title, batch.folder_name, batch.entry_count) == (
            'AC/DC: "Live"?',
            "ACDC Live",
            1,
        )
        assert batch.source_url == PLAYLIST

    def test_a_channel_is_a_playlist_too(self, make_jobs_client) -> None:
        client = make_jobs_client(spawn_job=lambda fn: None)

        body = enqueue_playlist(client, [entry(1)], url=CHANNEL, title="Fireship - Videos").json()

        assert body["batchId"]
        assert body["jobs"][0]["batchTitle"] == "Fireship - Videos"

    def test_jobs_are_listed_with_their_batch(self, make_jobs_client) -> None:
        client = make_jobs_client(spawn_job=lambda fn: None)
        batch_id = enqueue_playlist(client, [entry(1), entry(2)]).json()["batchId"]

        listed = client.get("/api/jobs").json()["jobs"]

        assert {j["batchId"] for j in listed} == {batch_id}
        assert {j["batchTitle"] for j in listed} == {"Select Lectures"}

    def test_a_missing_title_uses_the_fallback_folder(self, make_jobs_client) -> None:
        client = make_jobs_client(spawn_job=lambda fn: None)

        body = enqueue_playlist(client, [entry(1)], title=None).json()

        batch = client.app.state.jobs.get_batch(body["batchId"])
        assert (batch.title, batch.folder_name) == ("Playlist", "Playlist")


class TestValidation:
    @pytest.mark.parametrize(
        "bad_url",
        [
            "https://vimeo.com/123",
            "https://www.youtube.com/playlist?list=PLabc",
            "https://www.youtube.com/@Fireship",
            "not a url",
            "https://evil.com/watch?v=00000000001",
            "",
        ],
    )
    def test_every_entry_must_be_a_youtube_video(
        self, jobs_client: TestClient, fake_engine: FakeEngine, bad_url: str
    ) -> None:
        entries = [entry(1), {**entry(2), "url": bad_url}]

        response = enqueue_playlist(jobs_client, entries)

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_entry"
        assert jobs_client.get("/api/jobs").json()["jobs"] == []  # not even the valid one
        assert fake_engine.calls == []

    def test_entry_urls_are_normalized(self, make_jobs_client) -> None:
        client = make_jobs_client(spawn_job=lambda fn: None)
        raw = {**entry(1), "url": "https://youtu.be/00000000001?si=x&list=PLabc"}

        jobs = enqueue_playlist(client, [raw]).json()["jobs"]

        assert jobs[0]["url"] == video_url(1)

    @pytest.mark.parametrize("entries", [[], None])
    def test_an_empty_selection_is_rejected(self, jobs_client: TestClient, entries) -> None:
        response = jobs_client.post(
            "/api/jobs",
            json={"url": PLAYLIST, "mode": "video", "quality": "best", "entries": entries},
            headers=APP_HEADERS,
        )

        assert response.status_code == 422
        assert response.json()["code"] == "no_entries"
        assert jobs_client.get("/api/jobs").json()["jobs"] == []

    def test_repeated_positions_are_rejected(self, jobs_client: TestClient) -> None:
        response = enqueue_playlist(jobs_client, [entry(1), entry(1)])

        assert response.status_code == 422
        assert jobs_client.get("/api/jobs").json()["jobs"] == []

    def test_more_than_500_entries_are_rejected(self, jobs_client: TestClient) -> None:
        response = enqueue_playlist(jobs_client, [entry(i) for i in range(1, 502)])

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "options",
        [
            {"mode": "video"},  # no quality
            {"mode": "video", "quality": "best", "audioFormat": "mp3"},
            {"mode": "audio"},
            {"mode": "audio", "audioFormat": "mp3", "quality": "best"},
        ],
    )
    def test_the_same_option_rules_as_a_single_video(
        self, jobs_client: TestClient, options: dict
    ) -> None:
        response = jobs_client.post(
            "/api/jobs",
            json={"url": PLAYLIST, "entries": [entry(1)], **options},
            headers=APP_HEADERS,
        )

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_options"
        assert jobs_client.get("/api/jobs").json()["jobs"] == []

    def test_a_single_video_does_not_take_entries(self, jobs_client: TestClient) -> None:
        response = enqueue_playlist(jobs_client, [entry(1)], url=video_url(1))

        assert response.status_code == 422
        assert jobs_client.get("/api/jobs").json()["jobs"] == []

    def test_requires_the_engine(self, make_jobs_client) -> None:
        client = make_jobs_client(ready=False)

        response = enqueue_playlist(client, [entry(1)])

        assert response.status_code == 409
        assert response.json()["code"] == "engine_not_ready"


class TestFiles:
    def test_files_go_to_the_folder_numbered_by_playlist_position(
        self, jobs_client: TestClient, titled: FakeEngine, download_dir: Path
    ) -> None:
        body = enqueue_playlist(jobs_client, [entry(1), entry(3), entry(12)]).json()

        assert tree(download_dir) == [
            "Select Lectures/01 - Video 1.m4a",
            "Select Lectures/03 - Video 3.m4a",
            "Select Lectures/12 - Video 12.m4a",
        ]
        job = get_job(jobs_client, body["jobs"][1]["id"])
        assert job["status"] == "completed"
        assert job["outputPath"] == str(download_dir / "Select Lectures" / "03 - Video 3.m4a")

    def test_padding_grows_with_the_highest_position(
        self, jobs_client: TestClient, titled: FakeEngine, download_dir: Path
    ) -> None:
        enqueue_playlist(jobs_client, [entry(1), entry(120)])

        assert tree(download_dir) == [
            "Select Lectures/001 - Video 1.m4a",
            "Select Lectures/120 - Video 120.m4a",
        ]

    def test_the_folder_name_is_sanitized(
        self, jobs_client: TestClient, titled: FakeEngine, download_dir: Path
    ) -> None:
        enqueue_playlist(jobs_client, [entry(1)], title="CON")
        enqueue_playlist(jobs_client, [entry(2)], title="../../etc: x*")

        assert tree(download_dir) == ["CON_/01 - Video 1.m4a", "etc x/02 - Video 2.m4a"]

    def test_downloading_the_same_playlist_twice_reuses_the_folder(
        self, jobs_client: TestClient, titled: FakeEngine, download_dir: Path
    ) -> None:
        enqueue_playlist(jobs_client, [entry(1), entry(2)])
        enqueue_playlist(jobs_client, [entry(1), entry(2)])

        assert tree(download_dir) == [
            "Select Lectures/01 - Video 1 (2).m4a",
            "Select Lectures/01 - Video 1.m4a",
            "Select Lectures/02 - Video 2 (2).m4a",
            "Select Lectures/02 - Video 2.m4a",
        ]

    def test_an_existing_folder_with_other_files_is_kept(
        self, jobs_client: TestClient, titled: FakeEngine, download_dir: Path
    ) -> None:
        (download_dir / "Select Lectures").mkdir(parents=True)
        (download_dir / "Select Lectures" / "notes.txt").write_text("mine")

        enqueue_playlist(jobs_client, [entry(1)])

        assert tree(download_dir) == [
            "Select Lectures/01 - Video 1.m4a",
            "Select Lectures/notes.txt",
        ]

    def test_a_single_video_still_goes_to_the_destination_root(
        self, jobs_client: TestClient, titled: FakeEngine, download_dir: Path
    ) -> None:
        jobs_client.post(
            "/api/jobs",
            json={"url": video_url(1), "mode": "audio", "audioFormat": "m4a"},
            headers=APP_HEADERS,
        )

        assert tree(download_dir) == ["Video 1.m4a"]

    def test_simultaneous_jobs_with_the_same_name_do_not_collide(
        self, make_jobs_client, fake_engine: FakeEngine, download_dir: Path
    ) -> None:
        client = make_jobs_client(spawn_job=lambda fn: threading.Thread(target=fn).start())
        fake_engine.default.hold = True
        fake_engine.default.title = "Same"  # two entries, one position each, one clash across runs
        first = enqueue_playlist(client, [entry(1), entry(2)]).json()["jobs"]
        assert fake_engine.wait_running(2)
        fake_engine.release()
        wait_for(lambda: all(get_job(client, j["id"])["status"] == "completed" for j in first))
        second = enqueue_playlist(client, [entry(1)]).json()["jobs"]
        wait_for(lambda: get_job(client, second[0]["id"])["status"] == "completed")

        assert tree(download_dir) == [
            "Select Lectures/01 - Same (2).mp4",
            "Select Lectures/01 - Same.mp4",
            "Select Lectures/02 - Same.mp4",
        ]


class TestIndependence:
    def test_one_failing_job_does_not_stop_the_rest(
        self, jobs_client: TestClient, titled: FakeEngine, download_dir: Path
    ) -> None:
        titled.scenario(video_url(2), fail_with="ERROR: [youtube] x: Private video")

        jobs = enqueue_playlist(jobs_client, [entry(1), entry(2), entry(3)]).json()["jobs"]

        statuses = [get_job(jobs_client, j["id"])["status"] for j in jobs]
        assert statuses == ["completed", "failed", "completed"]
        assert tree(download_dir) == [
            "Select Lectures/01 - Video 1.m4a",
            "Select Lectures/03 - Video 3.m4a",
        ]
        assert get_job(jobs_client, jobs[1]["id"])["error"]

    def test_respects_the_concurrency_limit(
        self, make_jobs_client, fake_engine: FakeEngine
    ) -> None:
        client = make_jobs_client(spawn_job=lambda fn: threading.Thread(target=fn).start())
        fake_engine.default.hold = True

        jobs = enqueue_playlist(client, [entry(1), entry(2), entry(3)]).json()["jobs"]
        assert fake_engine.wait_running(2)

        assert [get_job(client, j["id"])["status"] for j in jobs] == [
            "downloading",
            "downloading",
            "queued",
        ]
        fake_engine.release()
        wait_for(lambda: all(get_job(client, j["id"])["status"] == "completed" for j in jobs))
        assert fake_engine.peak == 2
