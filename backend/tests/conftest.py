from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import EngineManager
from app.events import EventBroadcaster
from app.main import create_app
from tests.fake_engine import FakeEngine
from tests.fakes import TARGET, YTDLP_OLD, FakeFetcher, FakeRunner, fake_archives

PORT = 54321
HOST = f"127.0.0.1:{PORT}"
APP_HEADERS = {"X-Requested-With": "youtube-downloader"}


class ShutdownRecorder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "data"
    path.mkdir()
    return path


@pytest.fixture
def download_dir(tmp_path: Path) -> Path:
    return tmp_path / "downloads"


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
def fetcher() -> FakeFetcher:
    fake = FakeFetcher()
    fake.publish_ytdlp("2026.10.26", YTDLP_OLD)
    return fake


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_engine(
    data_dir: Path, fetcher: FakeFetcher, runner: FakeRunner, clock: FakeClock
) -> Callable[..., EngineManager]:
    """Engine Manager over fakes; background work runs inline. Archives are served by `fetcher`."""
    archives, routes = fake_archives()
    for url, data in routes.items():
        fetcher.add(url, data)

    def factory(**kwargs) -> EngineManager:
        options = {
            "data_dir": data_dir,
            "target": TARGET,
            "fetcher": fetcher,
            "runner": runner,
            "now": clock,
            "spawn": lambda fn: fn(),
            "pinned": lambda _target: archives,
        }
        return EngineManager(**{**options, **kwargs})

    return factory


@pytest.fixture
def engine(make_engine: Callable[..., EngineManager]) -> EngineManager:
    return make_engine()


@pytest.fixture
def make_client(
    data_dir: Path,
    download_dir: Path,
    static_dir: Path,
    shutdown: ShutdownRecorder,
    engine: EngineManager,
) -> Callable[..., TestClient]:
    def factory(**kwargs) -> TestClient:
        app = create_app(
            data_dir=data_dir,
            port=PORT,
            request_shutdown=shutdown,
            static_dir=static_dir,
            engine=engine,
            download_dir=download_dir,
        )
        return TestClient(app, base_url=f"http://{HOST}", **kwargs)

    return factory


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()


# -- jobs ---------------------------------------------------------------------------------------


class RecordingBroadcaster(EventBroadcaster):
    """Keeps every published event instead of queueing it for SSE clients."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, object]] = []

    def publish(self, name: str, data: object) -> None:
        self.events.append((name, data))

    def named(self, name: str) -> list:
        return [data for n, data in self.events if n == name]


@pytest.fixture
def fake_engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def events() -> RecordingBroadcaster:
    return RecordingBroadcaster()


@pytest.fixture
def make_jobs_client(
    data_dir: Path,
    download_dir: Path,
    static_dir: Path,
    engine: EngineManager,
    fake_engine: FakeEngine,
    events: RecordingBroadcaster,
) -> Callable[..., TestClient]:
    """App over the FakeEngine. By default jobs run inline (synchronously) in the request."""

    def factory(*, ready: bool = True, **kwargs) -> TestClient:
        if ready:
            engine.install()
        options = {
            "data_dir": data_dir,
            "port": PORT,
            "static_dir": static_dir,
            "engine": engine,
            "download_dir": download_dir,
            "streamer": fake_engine,
            "broadcaster": events,
            "spawn_job": lambda fn: fn(),
        }
        return TestClient(create_app(**{**options, **kwargs}), base_url=f"http://{HOST}")

    return factory


@pytest.fixture
def jobs_client(make_jobs_client: Callable[..., TestClient]) -> TestClient:
    return make_jobs_client()
