"""Bulk cleanup of the History: DELETE /api/batches/{id} and DELETE /api/history.

Jobs are seeded straight in the repository (no yt-dlp involved) except in the end-to-end test.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.jobs import JobRepository
from app.jobs.models import TERMINAL_STATUSES, Batch
from tests.conftest import APP_HEADERS, RecordingBroadcaster
from tests.test_jobs_api import ZOO, enqueue
from tests.test_playlist_jobs import enqueue_playlist, entry

TERMINAL = [s.value for s in TERMINAL_STATUSES]
IN_PROGRESS = ["queued", "downloading", "processing"]


@pytest.fixture
def repo(tmp_path: Path) -> JobRepository:
    db = Database(tmp_path / "repo.sqlite3")
    db.migrate()
    return JobRepository(db)


def seed(repo: JobRepository, status: str, batch: Batch | None = None, n: int = 1) -> str:
    job = repo.create(
        url=f"https://www.youtube.com/watch?v={n:011d}",
        mode="video",
        quality="best",
        batch_id=batch.id if batch else None,
        playlist_index=n if batch else None,
    )
    repo.update(job.id, status=status)
    return job.id


def batch_of(repo: JobRepository, title: str = "Lista") -> Batch:
    return repo.create_batch(
        source_url="https://www.youtube.com/playlist?list=PLx",
        title=title,
        folder_name=title,
        entry_count=3,
    )


def delete_batch(client: TestClient, batch_id: str):
    return client.delete(f"/api/batches/{batch_id}", headers=APP_HEADERS)


def delete_history(client: TestClient):
    return client.delete("/api/history", headers=APP_HEADERS)


class TestRepository:
    def test_a_batch_loses_only_its_terminal_jobs_and_stays_while_it_has_others(
        self, repo: JobRepository
    ) -> None:
        batch = batch_of(repo)
        gone = [seed(repo, s, batch, n) for n, s in enumerate(TERMINAL, 1)]
        kept = [seed(repo, s, batch, 10 + n) for n, s in enumerate(IN_PROGRESS)]
        other_batch = batch_of(repo, "Otra")
        other = seed(repo, "completed", other_batch)
        single = seed(repo, "completed")

        removed = repo.delete_terminal_of_batch(batch.id)

        assert sorted(removed) == sorted(gone)
        assert all(repo.get(i) is not None for i in [*kept, other, single])
        assert repo.get_batch(batch.id) is not None
        assert repo.get_batch(other_batch.id) is not None

    def test_a_batch_left_without_jobs_is_deleted(self, repo: JobRepository) -> None:
        batch = batch_of(repo)
        seed(repo, "completed", batch, 1)
        seed(repo, "failed", batch, 2)

        assert len(repo.delete_terminal_of_batch(batch.id)) == 2
        assert repo.get_batch(batch.id) is None

    def test_a_batch_with_nothing_terminal_removes_nothing(self, repo: JobRepository) -> None:
        batch = batch_of(repo)
        seed(repo, "queued", batch)

        assert repo.delete_terminal_of_batch(batch.id) == []
        assert repo.get_batch(batch.id) is not None

    def test_the_history_removes_every_terminal_job_across_batches_and_singles(
        self, repo: JobRepository
    ) -> None:
        full = batch_of(repo, "Completa")
        partial = batch_of(repo, "Parcial")
        gone = [
            seed(repo, "completed", full, 1),
            seed(repo, "failed", full, 2),
            seed(repo, "canceled", partial, 1),
            seed(repo, "interrupted"),
            seed(repo, "completed"),
        ]
        kept = [seed(repo, "queued", partial, 2), seed(repo, "downloading")]

        removed = repo.delete_all_terminal()

        assert sorted(removed) == sorted(gone)
        assert all(repo.get(i) is not None for i in kept)
        assert repo.get_batch(full.id) is None
        assert repo.get_batch(partial.id) is not None

    def test_a_batch_still_being_created_is_not_taken_for_an_empty_one(
        self, repo: JobRepository
    ) -> None:
        creating = batch_of(repo)  # its jobs are inserted right after
        seed(repo, "completed")

        repo.delete_all_terminal()

        assert repo.get_batch(creating.id) is not None

    def test_the_output_of_a_removed_job_goes_with_it(self, repo: JobRepository) -> None:
        batch = batch_of(repo)
        failed = seed(repo, "failed", batch)
        running = seed(repo, "downloading", batch, 2)
        repo.save_output(failed, 1, ["ERROR: boom"])
        repo.save_output(running, 1, ["previous attempt"])

        repo.delete_terminal_of_batch(batch.id)

        assert repo.get_output(failed) is None
        assert repo.get_output(running) is not None

    def test_the_output_goes_with_the_job_when_the_history_is_cleared(
        self, repo: JobRepository
    ) -> None:
        failed = seed(repo, "failed")
        repo.save_output(failed, 1, ["ERROR: boom"])

        repo.delete_all_terminal()

        assert repo.get_output(failed) is None


@pytest.fixture
def client(make_jobs_client: Callable[..., TestClient]) -> TestClient:
    # Jobs never start: whatever is seeded keeps the status it was given.
    return make_jobs_client(spawn_job=lambda fn: None)


class TestRemoveBatchApi:
    def test_removes_the_terminal_jobs_and_keeps_the_rest(
        self, client: TestClient, events: RecordingBroadcaster
    ) -> None:
        repo = client.app.state.jobs
        batch = batch_of(repo)
        done = seed(repo, "completed", batch, 1)
        failed = seed(repo, "failed", batch, 2)
        running = seed(repo, "downloading", batch, 3)
        queued = seed(repo, "queued", batch, 4)

        response = delete_batch(client, batch.id)

        assert response.status_code == 200
        assert response.json() == {"removed": 2}
        assert client.get(f"/api/jobs/{done}").status_code == 404
        assert client.get(f"/api/jobs/{failed}").status_code == 404
        assert client.get(f"/api/jobs/{running}").status_code == 200
        assert client.get(f"/api/jobs/{queued}").status_code == 200
        assert repo.get_batch(batch.id) is not None
        (event,) = events.named("jobs.removed")
        assert sorted(event["ids"]) == sorted([done, failed])
        assert events.named("job.removed") == []

    def test_a_batch_with_every_job_terminal_is_deleted(self, client: TestClient) -> None:
        repo = client.app.state.jobs
        batch = batch_of(repo)
        seed(repo, "completed", batch, 1)
        seed(repo, "canceled", batch, 2)

        assert delete_batch(client, batch.id).json() == {"removed": 2}
        assert repo.get_batch(batch.id) is None
        assert client.get("/api/jobs").json()["jobs"] == []

    def test_nothing_to_remove_answers_zero_and_publishes_nothing(
        self, client: TestClient, events: RecordingBroadcaster
    ) -> None:
        repo = client.app.state.jobs
        batch = batch_of(repo)
        seed(repo, "queued", batch)

        response = delete_batch(client, batch.id)

        assert response.status_code == 200
        assert response.json() == {"removed": 0}
        assert events.named("jobs.removed") == []

    def test_an_unknown_batch_is_404(
        self, client: TestClient, events: RecordingBroadcaster
    ) -> None:
        response = delete_batch(client, "nope")

        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "batch_not_found"
        assert "playlist" in body["message"]
        assert events.named("jobs.removed") == []

    def test_a_batch_already_emptied_is_404(self, client: TestClient) -> None:
        repo = client.app.state.jobs
        batch = batch_of(repo)
        seed(repo, "completed", batch)
        delete_batch(client, batch.id)

        assert delete_batch(client, batch.id).status_code == 404

    def test_requires_the_app_header(self, client: TestClient) -> None:
        repo = client.app.state.jobs
        batch = batch_of(repo)
        seed(repo, "completed", batch)

        response = client.delete(f"/api/batches/{batch.id}")

        assert response.status_code == 403
        assert response.json()["code"] == "missing_app_header"
        assert client.get("/api/jobs").json()["jobs"] != []


class TestClearHistoryApi:
    def test_removes_only_terminal_jobs_across_batches_and_singles(
        self, client: TestClient, events: RecordingBroadcaster
    ) -> None:
        repo = client.app.state.jobs
        full = batch_of(repo, "Completa")
        partial = batch_of(repo, "Parcial")
        gone = [
            seed(repo, "completed", full, 1),
            seed(repo, "failed", partial, 1),
            seed(repo, "interrupted"),
            seed(repo, "canceled"),
        ]
        kept = [seed(repo, "queued", partial, 2), seed(repo, "processing")]

        response = delete_history(client)

        assert response.status_code == 200
        assert response.json() == {"removed": 4}
        left = [j["id"] for j in client.get("/api/jobs").json()["jobs"]]
        assert sorted(left) == sorted(kept)
        assert repo.get_batch(full.id) is None
        assert repo.get_batch(partial.id) is not None
        (event,) = events.named("jobs.removed")
        assert sorted(event["ids"]) == sorted(gone)

    def test_an_empty_history_answers_zero_and_publishes_nothing(
        self, client: TestClient, events: RecordingBroadcaster
    ) -> None:
        seed(client.app.state.jobs, "queued")

        response = delete_history(client)

        assert response.json() == {"removed": 0}
        assert events.named("jobs.removed") == []
        assert events.named("job.removed") == []

    def test_does_not_publish_queue_counts(
        self, client: TestClient, events: RecordingBroadcaster
    ) -> None:
        seed(client.app.state.jobs, "completed")
        before = len(events.named("queue.updated"))

        delete_history(client)

        assert len(events.named("queue.updated")) == before

    def test_requires_the_app_header(self, client: TestClient) -> None:
        seed(client.app.state.jobs, "completed")

        response = client.delete("/api/history")

        assert response.status_code == 403
        assert client.get("/api/jobs").json()["jobs"] != []


class TestFilesAreNeverTouched:
    def test_downloaded_files_stay_after_a_batch_removal_and_a_cleared_history(
        self, make_jobs_client, tmp_path: Path
    ) -> None:
        client = make_jobs_client()
        batch_body = enqueue_playlist(client, [entry(1), entry(2)]).json()
        single = enqueue(client, ZOO).json()["jobs"][0]
        done = [client.get(f"/api/jobs/{j['id']}").json() for j in batch_body["jobs"]]
        paths = [Path(j["outputPath"]) for j in done]
        assert len(paths) == 2 and all(p.is_file() for p in paths)
        outside = tmp_path / "elsewhere.mp4"  # a file a job points at, outside the Destination
        outside.write_bytes(b"x")
        client.app.state.jobs.update(single["id"], output_path=str(outside))

        assert delete_batch(client, batch_body["batchId"]).json() == {"removed": 2}
        assert delete_history(client).json() == {"removed": 1}

        assert client.get("/api/jobs").json()["jobs"] == []
        assert all(p.is_file() for p in paths)
        assert outside.is_file()
