"""Bulk cancel and retry: POST /api/batches/{id}/cancel, POST /api/batches/{id}/retry and
POST /api/jobs/retry, reusing the rules of the single-job cancel and retry.

The Queue tests use real worker threads and a FakeEngine; the API tests seed jobs straight in the
repository and never start them.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import EngineManager
from app.jobs import JobStatus
from app.jobs.queue import UnknownBatch
from tests.conftest import APP_HEADERS, RecordingBroadcaster
from tests.fake_engine import FakeEngine
from tests.test_jobs_api import get_job, wait_for
from tests.test_playlist_jobs import enqueue_playlist, entry
from tests.test_queue import Harness, thread_spawn, url


@pytest.fixture
def harness(tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine) -> Harness:
    engine.install()
    return Harness(tmp_path, engine, fake_engine, cancel_grace=5.0, cancel_kill_wait=5.0)


def enqueue_batch(harness: Harness, indexes: range) -> tuple[str, list[str]]:
    batch, jobs = harness.queue.enqueue_batch(
        source_url="https://www.youtube.com/playlist?list=PLx",
        title="Lista",
        folder_name="Lista",
        entries=[{"url": url(n), "index": n, "title": f"Video {n}"} for n in indexes],
        mode="video",
        quality="best",
        audio_format=None,
    )
    return batch.id, [j.id for j in jobs]


class TestCancelBatchQueue:
    def test_cancels_queued_and_running_jobs_and_no_queued_one_ever_starts(
        self, harness: Harness, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        batch_id, ids = enqueue_batch(harness, range(1, 5))  # two run, two wait
        assert fake_engine.wait_running(2)
        outsider = harness.enqueue(9)

        jobs = harness.queue.cancel_batch(batch_id)

        assert sorted(j.id for j in jobs) == sorted(ids)
        assert all(j.status is JobStatus.CANCELED for j in jobs)
        assert [harness.status(i) for i in ids] == ["canceled"] * 4
        # The slots the running ones left went to the outsider, never to a canceled sibling.
        assert fake_engine.wait_started(3)
        assert sorted(fake_engine.started[:2]) == [url(1), url(2)]
        assert fake_engine.started[2] == url(9)
        assert url(3) not in fake_engine.started and url(4) not in fake_engine.started
        fake_engine.release()
        wait_for(lambda: harness.status(outsider) == "completed")

    def test_the_queued_ones_are_canceled_before_the_running_ones_are_stopped(
        self, harness: Harness, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        batch_id, ids = enqueue_batch(harness, range(1, 4))
        assert fake_engine.wait_running(2)

        harness.queue.cancel_batch(batch_id)

        updates = [(e["id"], e["status"]) for e in harness.events.named("job.updated")]
        first_cancel = updates.index((ids[2], "canceled"))
        assert (ids[0], "canceled") in updates[first_cancel:]
        assert (ids[1], "canceled") in updates[first_cancel:]
        assert sorted(fake_engine.started) == [url(1), url(2)]

    def test_only_the_jobs_of_that_batch_are_touched(self, harness: Harness) -> None:
        harness.queue.hold()
        batch_id, ids = enqueue_batch(harness, range(1, 3))
        _, other_ids = enqueue_batch(harness, range(5, 7))
        single = harness.enqueue(9)

        jobs = harness.queue.cancel_batch(batch_id)

        assert sorted(j.id for j in jobs) == sorted(ids)
        assert [harness.status(i) for i in [*other_ids, single]] == ["queued"] * 3

    def test_finished_jobs_are_left_alone_and_nothing_to_cancel_is_an_empty_list(
        self, harness: Harness
    ) -> None:
        harness.queue.hold()
        batch_id, ids = enqueue_batch(harness, range(1, 4))
        for job_id, status in zip(ids, ["completed", "failed", "canceled"], strict=True):
            harness.repo.update(job_id, status=status)

        assert harness.queue.cancel_batch(batch_id) == []
        assert [harness.status(i) for i in ids] == ["completed", "failed", "canceled"]

    def test_unknown_batch(self, harness: Harness) -> None:
        with pytest.raises(UnknownBatch):
            harness.queue.cancel_batch("nope")

    def test_queue_counts_end_empty(self, harness: Harness, fake_engine: FakeEngine) -> None:
        fake_engine.default.hold = True
        batch_id, _ = enqueue_batch(harness, range(1, 4))
        assert fake_engine.wait_running(2)

        harness.queue.cancel_batch(batch_id)

        wait_for(lambda: harness.events.named("queue.updated")[-1] == {"active": 0, "queued": 0})


class TestRetryBatchQueue:
    def test_retries_failed_canceled_and_interrupted_in_playlist_order(
        self, harness: Harness
    ) -> None:
        harness.queue.hold()
        batch_id, ids = enqueue_batch(harness, range(1, 6))
        statuses = ["interrupted", "completed", "failed", "canceled", "queued"]
        for job_id, status in zip(ids, statuses, strict=True):
            harness.repo.update(job_id, status=status)

        jobs = harness.queue.retry_batch(batch_id)

        assert [j.id for j in jobs] == [ids[0], ids[2], ids[3]]
        assert all(j.status is JobStatus.QUEUED and j.attempt == 2 for j in jobs)
        assert harness.status(ids[1]) == "completed"
        assert harness.repo.get(ids[1]).attempt == 1  # type: ignore[union-attr]

    def test_nothing_to_retry_is_an_empty_list(self, harness: Harness) -> None:
        harness.queue.hold()
        batch_id, _ = enqueue_batch(harness, range(1, 3))

        assert harness.queue.retry_batch(batch_id) == []

    def test_unknown_batch(self, harness: Harness) -> None:
        with pytest.raises(UnknownBatch):
            harness.queue.retry_batch("nope")


@pytest.fixture
def client(make_jobs_client: Callable[..., TestClient]) -> TestClient:
    # Jobs never start: whatever is seeded keeps the status it was given.
    return make_jobs_client(spawn_job=lambda fn: None)


def seed(client: TestClient, status: str, batch_id: str | None = None, n: int = 1) -> str:
    repo = client.app.state.jobs
    job = repo.create(
        url=f"https://www.youtube.com/watch?v={n:011d}",
        mode="video",
        quality="best",
        batch_id=batch_id,
        playlist_index=n if batch_id else None,
    )
    repo.update(job.id, status=status)
    return job.id


def new_batch(client: TestClient) -> str:
    return client.app.state.jobs.create_batch(
        source_url="https://www.youtube.com/playlist?list=PLx",
        title="Lista",
        folder_name="Lista",
        entry_count=4,
    ).id


def post(client: TestClient, path: str, body: dict | None = None):
    if body is None:
        return client.post(path, headers=APP_HEADERS)
    return client.post(path, json=body, headers=APP_HEADERS)


class TestCancelBatchApi:
    def test_cancels_the_queued_jobs_and_publishes_each_one(
        self, client: TestClient, events: RecordingBroadcaster
    ) -> None:
        client.app.state.queue.hold()
        batch_id = new_batch(client)
        queued = [seed(client, "queued", batch_id, n) for n in (1, 2)]
        done = seed(client, "completed", batch_id, 3)

        response = post(client, f"/api/batches/{batch_id}/cancel")

        assert response.status_code == 200
        jobs = response.json()["jobs"]
        assert [j["id"] for j in jobs] == queued
        assert {j["status"] for j in jobs} == {"canceled"}
        assert get_job(client, done)["status"] == "completed"
        published = [(e["id"], e["status"]) for e in events.named("job.updated")]
        assert published[-2:] == [(i, "canceled") for i in queued]

    def test_a_batch_with_nothing_to_cancel_answers_an_empty_list(self, client: TestClient) -> None:
        batch_id = new_batch(client)
        seed(client, "failed", batch_id)

        response = post(client, f"/api/batches/{batch_id}/cancel")

        assert response.status_code == 200
        assert response.json() == {"jobs": []}

    def test_unknown_batch_is_404(self, client: TestClient) -> None:
        response = post(client, "/api/batches/nope/cancel")

        assert response.status_code == 404
        assert response.json()["code"] == "batch_not_found"

    def test_requires_the_app_header(self, client: TestClient) -> None:
        assert client.post("/api/batches/x/cancel").status_code == 403

    def test_a_real_batch_with_running_jobs_is_canceled_over_http(
        self, make_jobs_client, fake_engine: FakeEngine
    ) -> None:
        fake_engine.default.hold = True
        client = make_jobs_client(spawn_job=thread_spawn)
        body = enqueue_playlist(client, [entry(n) for n in (1, 2, 3)]).json()
        assert fake_engine.wait_running(2)

        response = post(client, f"/api/batches/{body['batchId']}/cancel")

        assert response.status_code == 200
        assert len(response.json()["jobs"]) == 3
        wait_for(lambda: client.app.state.queue.active_ids() == [])
        assert [get_job(client, j["id"])["status"] for j in body["jobs"]] == ["canceled"] * 3
        assert len(fake_engine.started) == 2


class TestRetryBatchApi:
    def test_retries_the_retryable_jobs_and_publishes_each_one(
        self, client: TestClient, events: RecordingBroadcaster
    ) -> None:
        client.app.state.queue.hold()
        batch_id = new_batch(client)
        statuses = ["failed", "canceled", "interrupted", "completed", "queued"]
        ids = [seed(client, s, batch_id, n) for n, s in enumerate(statuses, 1)]

        response = post(client, f"/api/batches/{batch_id}/retry")

        assert response.status_code == 200
        jobs = response.json()["jobs"]
        assert [j["id"] for j in jobs] == ids[:3]
        assert {j["status"] for j in jobs} == {"queued"}
        assert {j["attempt"] for j in jobs} == {2}
        assert get_job(client, ids[3])["attempt"] == 1
        retried = {e["id"] for e in events.named("job.updated") if e["attempt"] == 2}
        assert retried == set(ids[:3])

    def test_nothing_to_retry_is_an_empty_list(self, client: TestClient) -> None:
        batch_id = new_batch(client)
        seed(client, "completed", batch_id)

        assert post(client, f"/api/batches/{batch_id}/retry").json() == {"jobs": []}

    def test_unknown_batch_is_404(self, client: TestClient) -> None:
        response = post(client, "/api/batches/nope/retry")

        assert response.status_code == 404
        assert response.json()["code"] == "batch_not_found"

    def test_requires_the_app_header(self, client: TestClient) -> None:
        assert client.post("/api/batches/x/retry").status_code == 403


class TestRetryManyApi:
    def test_retries_the_given_jobs_and_ignores_the_rest(self, client: TestClient) -> None:
        client.app.state.queue.hold()
        failed, canceled = seed(client, "failed", n=1), seed(client, "canceled", n=2)
        done, running = seed(client, "completed", n=3), seed(client, "downloading", n=4)
        untouched = seed(client, "failed", n=5)

        ids = [failed, done, "nope", canceled, running]
        response = post(client, "/api/jobs/retry", {"ids": ids})

        assert response.status_code == 200
        assert [j["id"] for j in response.json()["jobs"]] == [failed, canceled]
        assert get_job(client, failed)["status"] == "queued"
        assert get_job(client, done)["attempt"] == 1
        assert get_job(client, running)["status"] == "downloading"
        assert get_job(client, untouched)["status"] == "failed"

    def test_an_empty_list_answers_an_empty_list(self, client: TestClient) -> None:
        assert post(client, "/api/jobs/retry", {"ids": []}).json() == {"jobs": []}

    def test_repeated_ids_are_rejected(self, client: TestClient) -> None:
        job = seed(client, "failed")

        response = post(client, "/api/jobs/retry", {"ids": [job, job]})

        assert response.status_code == 422
        assert get_job(client, job)["attempt"] == 1

    def test_more_than_500_ids_are_rejected(self, client: TestClient) -> None:
        response = post(client, "/api/jobs/retry", {"ids": [str(n) for n in range(501)]})

        assert response.status_code == 422

    def test_500_ids_are_accepted(self, client: TestClient) -> None:
        ids = [str(n) for n in range(500)]

        assert post(client, "/api/jobs/retry", {"ids": ids}).json() == {"jobs": []}

    def test_does_not_clash_with_the_single_retry_route(self, client: TestClient) -> None:
        client.app.state.queue.hold()
        job = seed(client, "failed")

        assert post(client, f"/api/jobs/{job}/retry").status_code == 200
        assert post(client, "/api/jobs/retry", {"ids": [job]}).json() == {"jobs": []}  # queued now

    def test_requires_the_app_header(self, client: TestClient) -> None:
        assert client.post("/api/jobs/retry", json={"ids": []}).status_code == 403
