from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from app.runtime import read_runtime, runtime_path, write_runtime
from app.single_instance import (
    InstanceBusy,
    InstanceLock,
    Reuse,
    Start,
    acquire_instance,
    probe_health,
)

NEVER_ANSWERS = lambda port: False  # noqa: E731
ALWAYS_ANSWERS = lambda port: True  # noqa: E731


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

        def probe(port: int) -> bool:
            probed.append(port)
            return True

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
        server = _serve({"app": "youtube-downloader"})
        try:
            assert probe_health(server.server_port)
        finally:
            server.shutdown()

    def test_ignores_other_servers_on_the_port(self) -> None:
        server = _serve({"app": "something-else"})
        try:
            assert not probe_health(server.server_port)
        finally:
            server.shutdown()

    def test_nothing_listening_is_not_healthy(self) -> None:
        server = _serve({})
        port = server.server_port
        server.shutdown()
        server.server_close()

        assert not probe_health(port)
