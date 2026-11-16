"""Ticket 05: the yt-dlp output of a failed Attempt ("Ver detalle")."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import Database
from app.jobs import JobRepository
from app.jobs.runner import OUTPUT_LINE_MAX, OUTPUT_LINES_KEPT
from tests.conftest import APP_HEADERS
from tests.fake_engine import FakeEngine
from tests.test_jobs_api import ZOO, enqueue, get_job

ERROR = "ERROR: [youtube] jNQXAC9IVRw: Video unavailable"


def output(client: TestClient, job_id: str):
    return client.get(f"/api/jobs/{job_id}/output")


def failed_job(client: TestClient, fake_engine: FakeEngine, **scenario) -> str:
    fake_engine.scenario(ZOO, fail_with=ERROR, **scenario)
    job_id = enqueue(client).json()["jobs"][0]["id"]
    assert get_job(client, job_id)["status"] == "failed"
    return job_id


def test_a_failed_job_keeps_the_known_stderr(
    jobs_client: TestClient, fake_engine: FakeEngine
) -> None:
    job_id = failed_job(
        jobs_client,
        fake_engine,
        stderr_lines=("WARNING: [youtube] player client web skipped",),
        stdout_lines=("[info] jNQXAC9IVRw: Downloading 1 format(s)",),
    )

    response = output(jobs_client, job_id)

    assert response.status_code == 200
    body = response.json()
    assert body["attempt"] == 1
    # Progress lines are left out; the rest keeps its order (stdout before stderr in the fake).
    assert body["lines"] == [
        "[info] jNQXAC9IVRw: Downloading 1 format(s)",
        "WARNING: [youtube] player client web skipped",
        ERROR,
    ]


def test_the_friendly_error_stays_separate_from_the_raw_output(
    jobs_client: TestClient, fake_engine: FakeEngine
) -> None:
    job_id = failed_job(jobs_client, fake_engine)

    job = get_job(jobs_client, job_id)

    assert "yt-dlp" not in (job["error"] or "") and ERROR not in (job["error"] or "")
    assert ERROR in output(jobs_client, job_id).json()["lines"]


def test_only_the_last_lines_are_kept(jobs_client: TestClient, fake_engine: FakeEngine) -> None:
    noise = tuple(f"WARNING: line {i}" for i in range(OUTPUT_LINES_KEPT + 50))
    job_id = failed_job(jobs_client, fake_engine, stderr_lines=noise)

    lines = output(jobs_client, job_id).json()["lines"]

    assert len(lines) == OUTPUT_LINES_KEPT
    assert lines[-1] == ERROR
    assert lines[0] == "WARNING: line 51"  # 250 noise lines + the error: the first 51 are gone
    assert "WARNING: line 0" not in lines


def test_a_huge_line_is_cut(jobs_client: TestClient, fake_engine: FakeEngine) -> None:
    job_id = failed_job(jobs_client, fake_engine, stderr_lines=("x" * 100_000,))

    lines = output(jobs_client, job_id).json()["lines"]

    assert all(len(line) <= OUTPUT_LINE_MAX + 1 for line in lines)


def test_a_completed_job_has_no_detail(jobs_client: TestClient, fake_engine: FakeEngine) -> None:
    job_id = enqueue(jobs_client).json()["jobs"][0]["id"]
    assert get_job(jobs_client, job_id)["status"] == "completed"

    response = output(jobs_client, job_id)

    assert response.status_code == 404
    assert response.json()["code"] == "output_unavailable"
    assert "detalle" in response.json()["message"]


def test_a_job_that_failed_before_yt_dlp_started_has_no_detail(
    jobs_client: TestClient, fake_engine: FakeEngine
) -> None:
    fake_engine.start_error = "no such file"
    job_id = enqueue(jobs_client).json()["jobs"][0]["id"]
    assert get_job(jobs_client, job_id)["status"] == "failed"

    assert output(jobs_client, job_id).json()["code"] == "output_unavailable"


def test_an_unknown_job_is_job_not_found(jobs_client: TestClient) -> None:
    response = output(jobs_client, "nope")

    assert response.status_code == 404
    assert response.json()["code"] == "job_not_found"


def test_a_retry_discards_the_previous_output(
    jobs_client: TestClient, fake_engine: FakeEngine
) -> None:
    job_id = failed_job(jobs_client, fake_engine)
    fake_engine.scenario(ZOO, fail_with="ERROR: second failure")

    jobs_client.post(f"/api/jobs/{job_id}/retry", headers=APP_HEADERS)

    body = output(jobs_client, job_id).json()
    assert body["attempt"] == 2
    assert "ERROR: second failure" in body["lines"] and ERROR not in body["lines"]


def test_a_retry_that_succeeds_leaves_no_output(
    jobs_client: TestClient, fake_engine: FakeEngine
) -> None:
    job_id = failed_job(jobs_client, fake_engine)
    fake_engine.scenarios.clear()

    jobs_client.post(f"/api/jobs/{job_id}/retry", headers=APP_HEADERS)

    assert get_job(jobs_client, job_id)["status"] == "completed"
    assert output(jobs_client, job_id).status_code == 404


def test_removing_the_job_from_the_history_discards_the_output(
    make_jobs_client: Callable[..., TestClient], fake_engine: FakeEngine, data_dir: Path
) -> None:
    client = make_jobs_client()
    job_id = failed_job(client, fake_engine)
    db = Database(data_dir / "db.sqlite3")
    assert JobRepository(db).get_output(job_id) is not None

    assert client.delete(f"/api/jobs/{job_id}", headers=APP_HEADERS).status_code == 200

    assert output(client, job_id).status_code == 404
    assert db.query("SELECT COUNT(*) AS n FROM job_output")[0]["n"] == 0


def test_the_output_survives_a_restart(
    make_jobs_client: Callable[..., TestClient], fake_engine: FakeEngine
) -> None:
    job_id = failed_job(make_jobs_client(), fake_engine)

    again = make_jobs_client()

    assert ERROR in output(again, job_id).json()["lines"]
