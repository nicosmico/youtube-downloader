from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from app import __version__
from app.runtime import read_runtime, runtime_path, write_runtime
from app.single_instance import (
    Health,
    InstanceBusy,
    InstanceLock,
    Reuse,
    Start,
    acquire_instance,
    probe_health,
    request_shutdown,
)

NEVER_ANSWERS = lambda port: None  # noqa: E731
ALWAYS_ANSWERS = lambda port: Health(__version__)  # noqa: E731


class TestInstanceLock:
    def test_second_holder_is_refused_until_the_first_releases(self, tmp_path: Path) -> None:
        first = InstanceLock(tmp_path / "x.lock")
        second = InstanceLock(tmp_path / "x.lock")

        assert first.acquire()
        assert not second.acquire()

        first.release()
        assert second.acquire()
        second.release()


class TestAcquireInstance:
    def test_fresh_start_takes_the_lock(self, data_dir: Path) -> None:
        outcome = acquire_instance(data_dir, probe=NEVER_ANSWERS)

        assert isinstance(outcome, Start)
        outcome.lock.release()

    def test_healthy_existing_instance_is_reused(self, data_dir: Path) -> None:
        write_runtime(data_dir, 4242)
        held = InstanceLock(data_dir / "instance.lock")
        assert held.acquire()  # the running instance owns the lock
        probed: list[int] = []

        def probe(port: int) -> Health:
            probed.append(port)
            return Health(__version__)

        outcome = acquire_instance(data_dir, probe=probe, sleep=lambda _: None)

        assert isinstance(outcome, Reuse)
        assert outcome.info.port == 4242
        assert probed == [4242]
        held.release()

    def test_stale_runtime_json_is_replaced(self, data_dir: Path) -> None:
        write_runtime(data_dir, 4242)  # leftover from a crashed run, nobody answers

        outcome = acquire_instance(data_dir, probe=NEVER_ANSWERS)

        assert isinstance(outcome, Start)
        assert read_runtime(data_dir) is None
        outcome.lock.release()

    def test_corrupt_runtime_json_counts_as_stale(self, data_dir: Path) -> None:
        runtime_path(data_dir).write_text("not json")

        outcome = acquire_instance(data_dir, probe=ALWAYS_ANSWERS)

        assert isinstance(outcome, Start)
        outcome.lock.release()

    def test_healthy_instance_without_lock_is_still_reused(self, data_dir: Path) -> None:
        write_runtime(data_dir, 4242)

        outcome = acquire_instance(data_dir, probe=ALWAYS_ANSWERS)

        assert isinstance(outcome, Reuse)

    def test_waits_for_an_instance_that_is_still_starting(self, data_dir: Path) -> None:
        held = InstanceLock(data_dir / "instance.lock")
        assert held.acquire()
        sleeps = 0

        def sleep(_: float) -> None:
            nonlocal sleeps
            sleeps += 1
            if sleeps == 3:  # the other instance finishes starting
                write_runtime(data_dir, 4242)

        outcome = acquire_instance(data_dir, probe=ALWAYS_ANSWERS, sleep=sleep)

        assert isinstance(outcome, Reuse)
        assert sleeps == 3
        held.release()

    def test_gives_up_when_the_lock_holder_never_answers(self, data_dir: Path) -> None:
        held = InstanceLock(data_dir / "instance.lock")
        assert held.acquire()

        with pytest.raises(InstanceBusy):
            acquire_instance(data_dir, probe=NEVER_ANSWERS, sleep=lambda _: None, attempts=3)
        held.release()


class _Handler(BaseHTTPRequestHandler):
    body: dict = {}

    def do_GET(self) -> None:
        payload = json.dumps(self.body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:
        pass


def _serve(body: dict):
    handler = type("Handler", (_Handler,), {"body": body})
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class TestProbeHealth:
    def test_recognizes_this_app(self) -> None:
        server = _serve({"app": "youtube-downloader", "version": "0.2.2"})
        try:
            assert probe_health(server.server_port) == Health("0.2.2")
        finally:
            server.shutdown()

    def test_reports_no_version_when_the_instance_does_not_send_one(self) -> None:
        server = _serve({"app": "youtube-downloader"})
        try:
            assert probe_health(server.server_port) == Health(None)
        finally:
            server.shutdown()

    def test_ignores_other_servers_on_the_port(self) -> None:
        server = _serve({"app": "something-else"})
        try:
            assert probe_health(server.server_port) is None
        finally:
            server.shutdown()

    def test_nothing_listening_is_not_healthy(self) -> None:
        server = _serve({})
        port = server.server_port
        server.shutdown()
        server.server_close()

        assert probe_health(port) is None


class TestVersionTakeover:
    """acquire_instance with fake probe/shutdown/sleep: an older instance is replaced."""

    def _running(self, data_dir: Path, version: str | None):
        write_runtime(data_dir, 4242)
        held = InstanceLock(data_dir / "instance.lock")
        assert held.acquire()  # the running instance owns the lock
        return held, (lambda port: Health(version))

    @pytest.mark.parametrize("running", ["0.2.3", "0.2.4", "1.0.0", "0.10.0"])
    def test_same_or_newer_version_is_reused(self, data_dir: Path, running: str) -> None:
        held, probe = self._running(data_dir, running)
        shutdowns: list[int] = []

        outcome = acquire_instance(
            data_dir,
            probe=probe,
            shutdown=shutdowns.append,
            own_version="0.2.3",
            sleep=lambda _: None,
        )

        assert isinstance(outcome, Reuse)
        assert shutdowns == []
        held.release()

    @pytest.mark.parametrize("running", ["0.2.2", "0.1.9", "0.0.9", None, "banana"])
    def test_older_missing_or_unparseable_version_is_taken_over(
        self, data_dir: Path, running: str | None, caplog: pytest.LogCaptureFixture
    ) -> None:
        held, probe = self._running(data_dir, running)
        shutdowns: list[int] = []

        def shutdown(port: int) -> None:
            shutdowns.append(port)
            held.release()  # the old instance closes in an orderly way

        with caplog.at_level("INFO"):
            outcome = acquire_instance(
                data_dir,
                probe=probe,
                shutdown=shutdown,
                own_version="0.2.3",
                sleep=lambda _: None,
            )

        assert isinstance(outcome, Start)
        assert shutdowns == [4242]
        assert read_runtime(data_dir) is None  # stale runtime.json removed
        assert f"Taking over from version 0.2.3 (running {running})" in caplog.text
        outcome.lock.release()

    def test_waits_until_the_old_instance_releases_the_lock(self, data_dir: Path) -> None:
        held, probe = self._running(data_dir, "0.2.2")
        sleeps = 0

        def sleep(_: float) -> None:
            nonlocal sleeps
            sleeps += 1
            if sleeps == 4:
                held.release()

        outcome = acquire_instance(
            data_dir, probe=probe, shutdown=lambda port: None, own_version="0.2.3", sleep=sleep
        )

        assert isinstance(outcome, Start)
        assert sleeps == 4
        outcome.lock.release()

    def test_a_failing_shutdown_request_still_waits_for_the_lock(self, data_dir: Path) -> None:
        held, probe = self._running(data_dir, "0.2.2")
        sleeps = 0

        def sleep(_: float) -> None:
            nonlocal sleeps
            sleeps += 1
            held.release()  # it was closing anyway

        outcome = acquire_instance(
            data_dir, probe=probe, shutdown=lambda port: None, own_version="0.2.3", sleep=sleep
        )

        assert isinstance(outcome, Start)
        outcome.lock.release()

    def test_takes_over_even_when_the_lock_was_free_but_an_old_instance_answers(
        self, data_dir: Path
    ) -> None:
        write_runtime(data_dir, 4242)
        shutdowns: list[int] = []

        outcome = acquire_instance(
            data_dir,
            probe=lambda port: Health("0.2.2"),
            shutdown=shutdowns.append,
            own_version="0.2.3",
            sleep=lambda _: None,
        )

        assert isinstance(outcome, Start)
        assert shutdowns == [4242]
        assert read_runtime(data_dir) is None
        outcome.lock.release()

    def test_old_instance_that_never_closes_is_reused_with_a_warning(
        self, data_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        held, probe = self._running(data_dir, "0.2.2")
        sleeps = 0

        def sleep(_: float) -> None:
            nonlocal sleeps
            sleeps += 1

        with caplog.at_level("WARNING"):
            outcome = acquire_instance(
                data_dir,
                probe=probe,
                shutdown=lambda port: None,
                own_version="0.2.3",
                sleep=sleep,
                takeover_attempts=5,
            )

        assert isinstance(outcome, Reuse)
        assert outcome.info.port == 4242
        assert sleeps == 5
        assert "did not shut down in time" in caplog.text
        held.release()


class _ShutdownHandler(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def do_POST(self) -> None:
        self.seen.append(
            {"path": self.path, "host": self.headers["Host"], "headers": dict(self.headers)}
        )
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args) -> None:
        pass


class TestRequestShutdown:
    def test_posts_to_loopback_with_the_app_header_and_no_origin(self) -> None:
        seen: list[dict] = []
        handler = type("Handler", (_ShutdownHandler,), {"seen": seen})
        server = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            request_shutdown(server.server_port)
        finally:
            server.shutdown()
            server.server_close()

        assert len(seen) == 1
        assert seen[0]["path"] == "/api/system/shutdown"
        assert seen[0]["host"] == f"127.0.0.1:{server.server_port}"
        headers = {k.lower(): v for k, v in seen[0]["headers"].items()}
        assert headers["x-requested-with"] == "youtube-downloader"
        assert "origin" not in headers

    def test_a_dead_port_does_not_raise(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _ShutdownHandler)
        port = server.server_port
        server.server_close()

        request_shutdown(port)
