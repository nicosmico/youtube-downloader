from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import logs
from app.logging_setup import LOG_FILE, configure_logging
from tests.conftest import APP_HEADERS

APP = "2026-11-15 12:00:00,000 INFO app.jobs: "
REQUEST = "2026-11-15 12:00:00,000 INFO uvicorn.access: "


def write_log(data_dir: Path, lines: list[str], name: str = LOG_FILE) -> None:
    (data_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def get(client: TestClient, **params) -> list[str]:
    response = client.get("/api/logs", params=params)
    assert response.status_code == 200
    return response.json()["lines"]


def test_without_a_log_file_it_answers_empty(client: TestClient) -> None:
    assert get(client) == []


def test_returns_the_lines_in_order(client: TestClient, data_dir: Path) -> None:
    write_log(data_dir, [f"{APP}one", f"{APP}two", f"{APP}three"])

    assert get(client) == [f"{APP}one", f"{APP}two", f"{APP}three"]


def test_requests_are_left_out_unless_asked(client: TestClient, data_dir: Path) -> None:
    write_log(data_dir, [f"{APP}one", f'{REQUEST}"GET /api/jobs" 200', f"{APP}two"])

    assert get(client) == [f"{APP}one", f"{APP}two"]
    assert get(client, requests="false") == [f"{APP}one", f"{APP}two"]
    assert len(get(client, requests="true")) == 3


def test_returns_only_the_last_n_after_filtering(client: TestClient, data_dir: Path) -> None:
    lines = []
    for i in range(10):
        lines += [f"{APP}line {i}", f"{REQUEST}req {i}"]
    write_log(data_dir, lines)

    assert get(client, lines=3) == [f"{APP}line 7", f"{APP}line 8", f"{APP}line 9"]
    assert get(client, lines=3, requests="true") == [
        f"{REQUEST}req 8",
        f"{APP}line 9",
        f"{REQUEST}req 9",
    ]


def test_the_count_is_capped_at_500(client: TestClient, data_dir: Path) -> None:
    write_log(data_dir, [f"{APP}{i}" for i in range(600)])

    assert len(get(client)) == 500
    assert get(client, lines=500)[-1] == f"{APP}599"
    assert client.get("/api/logs", params={"lines": 501}).status_code == 422
    assert client.get("/api/logs", params={"lines": 0}).status_code == 422


def test_continues_into_the_rotated_file(client: TestClient, data_dir: Path) -> None:
    write_log(data_dir, [f"{APP}old 1", f"{APP}old 2"], name=f"{LOG_FILE}.1")
    write_log(data_dir, [f"{APP}new 1"])

    assert get(client, lines=3) == [f"{APP}old 1", f"{APP}old 2", f"{APP}new 1"]
    assert get(client, lines=2) == [f"{APP}old 2", f"{APP}new 1"]


def test_reads_a_big_file_backwards_without_losing_lines(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(logs, "_CHUNK", 64)  # force many chunks and lines split across them
    lines = [f"{APP}message number {i:04d} " + "x" * (i % 17) for i in range(300)]
    write_log(tmp_path, lines)

    assert logs.read_log_tail(tmp_path, 200, include_requests=True) == lines[-200:]
    assert logs.read_log_tail(tmp_path, 500, include_requests=True) == lines[-500:]


def test_keeps_traceback_lines_and_survives_bad_bytes(client: TestClient, data_dir: Path) -> None:
    (data_dir / LOG_FILE).write_bytes(
        f"{APP}boom\nTraceback (most recent call last):\n  caf\xc3\xa9 \xff\n".encode("latin-1")
    )

    result = get(client)

    assert result[0] == f"{APP}boom"
    assert result[1] == "Traceback (most recent call last):"
    assert "caf" in result[2]


def test_is_read_only(client: TestClient) -> None:
    assert client.post("/api/logs", headers=APP_HEADERS).status_code in (404, 405)


@pytest.fixture
def clean_root_logger():
    root = logging.getLogger()
    saved = list(root.handlers)
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in saved:
        root.addHandler(handler)


def test_logs_reach_the_file_without_a_console(
    client: TestClient, data_dir: Path, monkeypatch, clean_root_logger
) -> None:
    """The Windows exe has no stderr (PyInstaller --noconsole): the file is the only sink."""
    monkeypatch.setattr("sys.stderr", None)
    configure_logging(data_dir)

    logging.getLogger("app.jobs").warning("something failed")
    logging.getLogger("uvicorn.access").info("GET /api/jobs")

    lines = get(client)
    assert any("app.jobs: something failed" in line for line in lines)
    assert not any("uvicorn.access" in line for line in lines)
    assert any("uvicorn.access" in line for line in get(client, requests="true"))
