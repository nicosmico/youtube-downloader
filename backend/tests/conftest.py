from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PORT = 54321
HOST = f"127.0.0.1:{PORT}"
APP_HEADERS = {"X-Requested-With": "youtube-downloader"}


class ShutdownRecorder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "data"
    path.mkdir()
    return path


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    path = tmp_path / "static"
    path.mkdir()
    (path / "index.html").write_text("<!doctype html><app-root>shell</app-root>")
    (path / "main-abc.js").write_text("console.log('app')")
    (tmp_path / "secret.txt").write_text("outside of static")
    return path


@pytest.fixture
def shutdown() -> ShutdownRecorder:
    return ShutdownRecorder()


@pytest.fixture
def make_client(
    data_dir: Path, static_dir: Path, shutdown: ShutdownRecorder
) -> Callable[..., TestClient]:
    def factory(**kwargs) -> TestClient:
        app = create_app(
            data_dir=data_dir, port=PORT, request_shutdown=shutdown, static_dir=static_dir
        )
        return TestClient(app, base_url=f"http://{HOST}", **kwargs)

    return factory


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
