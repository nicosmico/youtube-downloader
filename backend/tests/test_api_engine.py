from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.engine import EngineManager
from app.engine.guard import require_engine_ready
from app.errors import install_error_handlers
from app.main import create_app
from tests.conftest import APP_HEADERS, HOST, PORT
from tests.fakes import YTDLP_NEW, FakeFetcher

MakeEngine = Callable[..., EngineManager]


class TestEngineStatus:
    def test_reports_missing_before_anything_is_installed(self, client: TestClient) -> None:
        response = client.get("/api/system/engine")

        assert response.status_code == 200
        assert response.json() == {
            "status": "missing",
            "message": None,
            "versions": {"ytDlp": None, "ffmpeg": None, "ffprobe": None, "deno": None},
            "updating": False,
            "lastUpdateCheck": None,
            "updateMessage": None,
        }

    def test_reports_versions_when_ready_and_health_follows(
        self, client: TestClient, engine: EngineManager
    ) -> None:
        engine.install()

        body = client.get("/api/system/engine").json()
        assert body["status"] == "ready"
        assert body["versions"] == {
            "ytDlp": "2026.10.26",
            "ffmpeg": "9.0.2",
            "ffprobe": "9.0.2",
            "deno": "2.9.8",
        }
        assert client.get("/api/health").json()["engine"] == body

    def test_reports_the_error_message(
        self, client: TestClient, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        fetcher.routes.clear()
        engine.install()

        body = client.get("/api/health").json()["engine"]
        assert body["status"] == "error"
        assert body["message"]


class TestInstallRetry:
    def test_retry_after_an_error_installs(
        self, client: TestClient, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        failing = "https://example.test/deno.zip"
        fetcher.failing.add(failing)
        engine.install()
        assert client.get("/api/system/engine").json()["status"] == "error"

        fetcher.failing.clear()
        response = client.post("/api/system/engine/install", headers=APP_HEADERS)

        assert response.status_code == 202
        assert client.get("/api/system/engine").json()["status"] == "ready"

    def test_is_a_no_op_when_already_ready(
        self, client: TestClient, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        engine.install()
        fetcher.requests.clear()

        response = client.post("/api/system/engine/install", headers=APP_HEADERS)

        assert response.status_code == 202
        assert response.json()["status"] == "ready"
        assert fetcher.requests == []

    def test_requires_the_app_header(self, client: TestClient) -> None:
        for path in ("/api/system/engine/install", "/api/system/engine/update"):
            response = client.post(path)

            assert response.status_code == 403
            assert response.json()["code"] == "missing_app_header"


class TestManualUpdate:
    def test_updates_ytdlp(
        self, client: TestClient, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        engine.install()
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)

        response = client.post("/api/system/engine/update", headers=APP_HEADERS)

        assert response.status_code == 202
        assert client.get("/api/system/engine").json()["versions"]["ytDlp"] == "2026.11.30"

    def test_conflicts_when_the_engine_is_not_ready(self, client: TestClient) -> None:
        response = client.post("/api/system/engine/update", headers=APP_HEADERS)

        assert response.status_code == 409
        assert response.json()["code"] == "engine_not_ready"

    def test_conflicts_while_downloads_are_active(
        self, make_engine: MakeEngine, make_client: Callable[..., TestClient]
    ) -> None:
        engine = make_engine(can_update=lambda: False)
        engine.install()
        client = TestClient(
            create_app(data_dir=engine.data_dir, port=PORT, engine=engine),
            base_url=f"http://{HOST}",
        )

        response = client.post("/api/system/engine/update", headers=APP_HEADERS)

        assert response.status_code == 409
        assert response.json()["code"] == "engine_busy"


class TestEngineReadyGuard:
    @pytest.fixture
    def guarded(self, engine: EngineManager) -> TestClient:
        """A test-only route behind the guard, in an app wired like the real one."""
        app = FastAPI()
        app.state.engine = engine
        install_error_handlers(app)

        @app.get("/api/test-only/guarded", dependencies=[Depends(require_engine_ready)])
        def guarded_route() -> dict[str, str]:
            return {"ok": "yes"}

        return TestClient(app)

    def test_rejects_with_engine_not_ready_until_ready(
        self, guarded: TestClient, engine: EngineManager
    ) -> None:
        response = guarded.get("/api/test-only/guarded")

        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "engine_not_ready"
        assert body["message"]
        assert body["detail"]["status"] == "missing"

        engine.install()
        assert guarded.get("/api/test-only/guarded").json() == {"ok": "yes"}

    def test_rejects_while_in_error(
        self, guarded: TestClient, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        fetcher.routes.clear()
        engine.install()

        response = guarded.get("/api/test-only/guarded")

        assert response.status_code == 409
        assert response.json()["detail"]["status"] == "error"


class LiveServer:
    """The app on a real socket: TestClient cannot stream an endless response."""

    def __init__(self, app: FastAPI, sock: socket.socket) -> None:
        self.server = uvicorn.Server(uvicorn.Config(app, log_config=None))
        self.sock = sock
        self.thread = threading.Thread(target=lambda: self.server.run(sockets=[sock]), daemon=True)

    def __enter__(self) -> LiveServer:
        self.thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)
        self.sock.close()


@pytest.fixture
def live(make_engine: MakeEngine, data_dir: Path) -> Iterator[Callable[..., tuple[str, dict]]]:
    stack: list[LiveServer] = []

    def start(**kwargs) -> tuple[str, dict]:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        app = create_app(data_dir=data_dir, port=port, static_dir=data_dir, **kwargs)
        stack.append(LiveServer(app, sock).__enter__())
        return f"http://127.0.0.1:{port}", {"X-Requested-With": "youtube-downloader"}

    yield start
    for server in stack:
        server.__exit__()


def read_events(lines: Iterator[str], wanted: int) -> list[tuple[str, str]]:
    """Read `wanted` SSE messages (event name, data) or comment lines from a line iterator."""
    messages: list[tuple[str, str]] = []
    name = ""
    for line in lines:
        if line.startswith(":"):
            messages.append(("comment", line))
        elif line.startswith("event: "):
            name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            messages.append((name, line.removeprefix("data: ")))
        if len(messages) >= wanted:
            break
    return messages


class TestEventsEndpoint:
    def test_streams_the_snapshot_then_engine_updated_on_every_change(
        self, live, make_engine: MakeEngine
    ) -> None:
        armed = [False]  # the install that starts with the app must not race the first read

        def spawn(fn: Callable[[], None]) -> None:
            if armed[0]:
                threading.Thread(target=fn, daemon=True).start()

        engine = make_engine(spawn=spawn)
        base, headers = live(engine=engine)

        with httpx.stream("GET", f"{base}/api/events", timeout=5) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            lines = response.iter_lines()
            first = read_events(lines, 1)
            assert first[0][0] == "engine.updated"
            assert '"status":"missing"' in first[0][1]

            armed[0] = True
            httpx.post(f"{base}/api/system/engine/install", headers=headers).raise_for_status()
            statuses: list[str] = []
            while not statuses or statuses[-1] != "ready":
                ((name, data),) = read_events(lines, 1)
                assert name == "engine.updated"
                statuses.append(data.split('"status":"')[1].split('"')[0])

        assert statuses[0] == "installing"
        assert statuses[-1] == "ready"

    def test_sends_a_heartbeat_when_idle(self, live) -> None:
        base, _ = live(heartbeat_seconds=0.05)

        with httpx.stream("GET", f"{base}/api/events", timeout=5) as response:
            messages = read_events(response.iter_lines(), 3)

        assert messages[0][0] == "engine.updated"
        assert [m[0] for m in messages[1:]] == ["comment", "comment"]

    def test_rejects_a_foreign_host(self, client: TestClient) -> None:
        response = client.get("/api/events", headers={"Host": "evil.test"})

        assert response.status_code == 403
