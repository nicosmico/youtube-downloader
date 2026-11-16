"""Idle Shutdown (ADR-0001) with an injectable clock: no test waits for real seconds."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.engine import EngineManager, EngineStatus
from app.events import EventBroadcaster
from app.idle import IDLE_SHUTDOWN_SECONDS, MAX_POLL_SECONDS, STARTUP_GRACE_SECONDS, IdleMonitor
from app.main import create_app
from tests.conftest import APP_HEADERS, HOST, PORT, RecordingBroadcaster, ShutdownRecorder
from tests.fake_engine import FakeEngine
from tests.test_jobs_api import enqueue

TIMEOUT = 15.0
GRACE = 60.0


class Ticks:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Probe:
    """The three things Idle Shutdown looks at, set by hand."""

    def __init__(self) -> None:
        self.clients = 0
        self.busy = False
        self.fired = 0
        self.ticks = Ticks()
        self.monitor = IdleMonitor(
            timeout=TIMEOUT,
            clients=lambda: self.clients,
            busy=lambda: self.busy,
            on_idle=self._fire,
            clock=self.ticks,
        )

    def _fire(self) -> None:
        self.fired += 1

    def wait(self, seconds: float) -> bool:
        self.ticks.advance(seconds)
        return self.monitor.check()

    def a_tab_visits(self, seconds: float = 1) -> None:
        """A tab connects, stays `seconds` and leaves: the app has been used."""
        self.clients = 1
        self.wait(seconds)
        self.clients = 0


@pytest.fixture
def fresh() -> Probe:
    """An app that just started: no tab has connected yet."""
    return Probe()


@pytest.fixture
def probe(fresh: Probe) -> Probe:
    """An app that already had its first tab: only the short timeout applies."""
    fresh.a_tab_visits()
    return fresh


class TestMonitor:
    def test_the_default_is_fifteen_seconds_after_the_last_tab(self) -> None:
        assert IDLE_SHUTDOWN_SECONDS == 15.0
        assert STARTUP_GRACE_SECONDS == 60.0

    def test_fires_once_after_the_timeout_with_nothing_going_on(self, probe: Probe) -> None:
        assert not probe.wait(TIMEOUT - 1)
        assert probe.wait(1)
        assert probe.fired == 1
        assert not probe.wait(TIMEOUT)  # once only
        assert probe.fired == 1

    def test_without_any_tab_since_the_start_it_waits_the_startup_grace(self, fresh: Probe) -> None:
        assert not fresh.wait(TIMEOUT)  # the 15 s do not apply until a tab has connected
        assert not fresh.wait(GRACE - TIMEOUT - 1)
        assert fresh.wait(1)
        assert fresh.fired == 1

    def test_a_longer_configured_timeout_wins_over_the_startup_grace(self) -> None:
        ticks = Ticks()
        monitor = IdleMonitor(
            timeout=600, clients=lambda: 0, busy=lambda: False, on_idle=int, clock=ticks
        )

        ticks.advance(599)
        assert not monitor.check()
        ticks.advance(1)
        assert monitor.check()

    def test_the_first_tab_switches_from_the_grace_to_the_short_timeout(self, fresh: Probe) -> None:
        fresh.wait(GRACE - 5)  # almost out of grace: the tab connects
        fresh.clients = 1
        assert not fresh.wait(30)
        fresh.clients = 0

        assert not fresh.wait(TIMEOUT - 1)
        assert fresh.wait(1)  # 15 s, not another 60

    def test_a_tab_that_came_and_went_between_polls_still_ends_the_grace(
        self, fresh: Probe
    ) -> None:
        fresh.clients = 1
        fresh.monitor.touch()  # the connection event
        fresh.clients = 0
        fresh.monitor.touch()  # the disconnection event

        assert not fresh.wait(TIMEOUT - 1)
        assert fresh.wait(1)

    def test_a_connected_client_keeps_the_app_open(self, probe: Probe) -> None:
        probe.clients = 1

        assert not probe.wait(TIMEOUT * 50)
        assert probe.fired == 0

    def test_the_timer_starts_when_the_last_client_leaves(self, probe: Probe) -> None:
        probe.clients = 1
        probe.wait(TIMEOUT * 50)
        probe.clients = 0

        assert not probe.wait(TIMEOUT - 1)
        assert probe.wait(1)

    def test_queued_or_active_jobs_and_engine_work_keep_the_app_open(self, probe: Probe) -> None:
        probe.busy = True  # the last tab closed during a download
        probe.wait(TIMEOUT * 50)
        probe.busy = False

        assert probe.fired == 0
        assert not probe.wait(TIMEOUT - 1)  # the 15 s count from when the Queue drained
        assert probe.wait(1)

    def test_work_also_holds_back_the_startup_grace(self, fresh: Probe) -> None:
        fresh.busy = True
        fresh.wait(GRACE * 3)
        fresh.busy = False

        assert not fresh.wait(GRACE - 1)
        assert fresh.wait(1)

    def test_a_reload_before_the_deadline_cancels_the_shutdown(self, probe: Probe) -> None:
        assert not probe.wait(TIMEOUT - 1)  # the old tab left; the reloaded one is not there yet
        probe.clients = 1  # ...and it connects just in time
        assert not probe.wait(1)
        assert not probe.wait(TIMEOUT * 10)
        assert probe.fired == 0

    def test_a_connection_in_between_restarts_the_timer(self, probe: Probe) -> None:
        probe.wait(TIMEOUT - 10)

        probe.monitor.touch()  # a job event between two checks

        assert not probe.wait(TIMEOUT - 1)
        assert probe.wait(1)

    def test_check_looks_at_the_conditions_each_time(self, probe: Probe) -> None:
        probe.wait(TIMEOUT - 1)
        probe.clients = 1  # reconnects right before the deadline
        assert not probe.wait(5)
        probe.clients = 0

        assert not probe.wait(TIMEOUT - 1)
        assert probe.wait(1)

    def test_the_poll_interval_lets_it_react_around_fifteen_seconds(self) -> None:
        def monitor(timeout: float) -> IdleMonitor:
            return IdleMonitor(timeout=timeout, clients=lambda: 0, busy=lambda: False, on_idle=int)

        assert MAX_POLL_SECONDS <= 1.0
        assert monitor(IDLE_SHUTDOWN_SECONDS).poll_seconds == 1.0
        assert monitor(600).poll_seconds == 1.0
        assert monitor(3).poll_seconds == pytest.approx(0.3)
        assert monitor(0.2).poll_seconds == 0.1  # never a busy loop

    def test_run_checks_in_the_background_until_it_fires(self, probe: Probe) -> None:
        polls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            polls.append(seconds)
            probe.ticks.advance(seconds * 20)  # time flies; no real waiting
            await asyncio.sleep(0)

        async def scenario() -> None:
            await asyncio.wait_for(probe.monitor.run(fake_sleep), 5)

        asyncio.run(scenario())

        assert probe.fired == 1
        assert set(polls) == {probe.monitor.poll_seconds}


class TestSettings:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, 15.0), ("", 15.0), ("20", 20.0), ("0", 0.0), ("-5", 0.0), ("soon", 15.0)],
    )
    def test_idle_shutdown_seconds_from_the_environment(
        self, value: str | None, expected: float
    ) -> None:
        env = {} if value is None else {"IDLE_SHUTDOWN_SECONDS": value}

        assert Settings.from_env(env).idle_shutdown_seconds == expected


class TestInTheApp:
    @pytest.fixture
    def ticks(self) -> Ticks:
        return Ticks()

    @pytest.fixture
    def make_app(
        self,
        data_dir: Path,
        download_dir: Path,
        static_dir: Path,
        engine: EngineManager,
        fake_engine: FakeEngine,
        shutdown: ShutdownRecorder,
        ticks: Ticks,
    ):
        engine.install()

        def factory(**kwargs):
            options = {
                "data_dir": data_dir,
                "port": PORT,
                "static_dir": static_dir,
                "engine": engine,
                "download_dir": download_dir,
                "streamer": fake_engine,
                "spawn_job": lambda fn: fn(),
                "clock": lambda: 0.0,
                "request_shutdown": shutdown,
                "idle_shutdown_seconds": TIMEOUT,
                "idle_clock": ticks,
            }
            return create_app(**{**options, **kwargs})

        return factory

    def test_it_is_off_unless_a_timeout_is_given(self, make_app) -> None:
        assert make_app(idle_shutdown_seconds=0).state.idle is None

    def test_an_idle_app_publishes_shutdown_and_stops(
        self, make_app, ticks: Ticks, shutdown: ShutdownRecorder
    ) -> None:
        events = RecordingBroadcaster()
        app = make_app(broadcaster=events)
        ticks.advance(GRACE)  # no tab ever connected: the startup grace applies

        assert app.state.idle.check()

        assert events.named("shutdown") == [{"reason": "idle"}]
        assert shutdown.calls == 1

    def test_closing_from_the_ui_tells_every_tab(
        self, make_app, shutdown: ShutdownRecorder
    ) -> None:
        events = RecordingBroadcaster()
        client = TestClient(make_app(broadcaster=events), base_url=f"http://{HOST}")

        response = client.post("/api/system/shutdown", headers=APP_HEADERS)

        assert response.status_code == 202
        assert events.named("shutdown") == [{"reason": "user"}]
        assert shutdown.calls == 1

    def test_a_subscribed_client_prevents_it_and_leaving_restarts_the_timer(
        self, make_app, ticks: Ticks, shutdown: ShutdownRecorder
    ) -> None:
        async def scenario() -> None:
            broadcaster = EventBroadcaster()
            app = make_app(broadcaster=broadcaster)
            tab = broadcaster.subscribe()
            ticks.advance(TIMEOUT * 2)
            assert not app.state.idle.check()

            broadcaster.unsubscribe(tab)  # the tab closes: 15 s start now
            ticks.advance(TIMEOUT - 1)
            assert not app.state.idle.check()
            ticks.advance(1)
            assert app.state.idle.check()

        asyncio.run(scenario())

        assert shutdown.calls == 1

    def test_a_queued_job_prevents_it(
        self, make_app, ticks: Ticks, shutdown: ShutdownRecorder
    ) -> None:
        app = make_app(spawn_job=lambda fn: None)  # the job is never started: it stays queued
        enqueue(TestClient(app, base_url=f"http://127.0.0.1:{PORT}"))
        ticks.advance(GRACE * 2)

        assert not app.state.idle.check()
        assert shutdown.calls == 0

    def test_job_activity_restarts_the_timer(
        self, make_app, ticks: Ticks, shutdown: ShutdownRecorder
    ) -> None:
        broadcaster = EventBroadcaster()
        app = make_app(broadcaster=broadcaster)
        ticks.advance(GRACE - 1)

        enqueue(TestClient(app, base_url=f"http://127.0.0.1:{PORT}"))  # runs and ends at once

        ticks.advance(GRACE - 1)
        assert not app.state.idle.check()
        ticks.advance(1)
        assert app.state.idle.check()

    def test_an_engine_install_in_progress_prevents_it(
        self, make_app, engine: EngineManager, ticks: Ticks, shutdown: ShutdownRecorder
    ) -> None:
        app = make_app()
        engine._set(status=EngineStatus.INSTALLING)
        ticks.advance(GRACE * 2)

        assert not app.state.idle.check()
        assert shutdown.calls == 0

    def test_an_engine_update_pending_or_running_prevents_it(
        self, make_app, engine: EngineManager, ticks: Ticks
    ) -> None:
        app = make_app()
        ticks.advance(GRACE * 2)
        engine._set(update_pending=True)
        assert not app.state.idle.check()
        engine._set(update_pending=False, updating=True)
        assert not app.state.idle.check()
