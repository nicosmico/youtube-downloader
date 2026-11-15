from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app import __version__
from app.runtime import read_runtime, runtime_path, write_runtime
from tests.conftest import APP_HEADERS, PORT, ShutdownRecorder


def test_health_identifies_the_app(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "app": "youtube-downloader",
        "version": __version__,
        "engine": {"status": "missing"},
        "port": PORT,
    }


def test_unknown_api_route_uses_the_error_shape(client: TestClient) -> None:
    response = client.get("/api/nope")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert "message" in response.json()


def test_wrong_method_uses_the_error_shape(client: TestClient) -> None:
    response = client.put("/api/health", headers=APP_HEADERS)

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


class TestShutdown:
    def test_removes_runtime_json_and_requests_server_stop(
        self, client: TestClient, data_dir: Path, shutdown: ShutdownRecorder
    ) -> None:
        write_runtime(data_dir, PORT)
        assert runtime_path(data_dir).exists()

        response = client.post("/api/system/shutdown", headers=APP_HEADERS)

        assert response.status_code == 202
        assert not runtime_path(data_dir).exists()
        assert shutdown.calls == 1

    def test_leaves_runtime_json_of_another_process(
        self, client: TestClient, data_dir: Path
    ) -> None:
        info = write_runtime(data_dir, PORT)
        runtime_path(data_dir).write_text(
            f'{{"pid": {os.getpid() + 1}, "port": {PORT}, "startedAt": "{info.startedAt}"}}'
        )

        client.post("/api/system/shutdown", headers=APP_HEADERS)

        assert read_runtime(data_dir) is not None

    def test_is_rejected_without_the_app_header(
        self, client: TestClient, shutdown: ShutdownRecorder
    ) -> None:
        response = client.post("/api/system/shutdown")

        assert response.status_code == 403
        assert shutdown.calls == 0
