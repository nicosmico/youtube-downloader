"""Several tabs and slow clients (ticket 11), against the real broadcaster.

The server loop runs in a thread of its own, like uvicorn's; the jobs run in the test thread
through the HTTP API. Nothing waits on time: the loop is fenced by scheduling a callback on it.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Callable, Iterator

import pytest

from app.events import Event, EventBroadcaster, Subscription
from tests.conftest import APP_HEADERS
from tests.test_jobs_api import SHORT, ZOO, enqueue


class LoopThread:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self._thread.start()

    def call(self, fn: Callable[[], object]) -> object:
        """Run `fn` on the loop, after everything scheduled on it before."""
        done: concurrent.futures.Future[object] = concurrent.futures.Future()
        self.loop.call_soon_threadsafe(lambda: done.set_result(fn()))
        return done.result(5)

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(5)
        self.loop.close()


@pytest.fixture
def server_loop() -> Iterator[LoopThread]:
    thread = LoopThread()
    yield thread
    thread.stop()


def drain(sub: Subscription) -> list[Event | None]:
    items: list[Event | None] = []
    while not sub.queue.empty():
        items.append(sub.queue.get_nowait())
    return items


def test_two_tabs_see_the_same_events(make_jobs_client, server_loop: LoopThread) -> None:
    broadcaster = EventBroadcaster()
    broadcaster.bind_loop(server_loop.loop)
    first, second = broadcaster.subscribe(), broadcaster.subscribe()
    client = make_jobs_client(broadcaster=broadcaster)

    enqueue(client, ZOO)
    enqueue(client, SHORT)
    one = server_loop.call(lambda: drain(first))
    two = server_loop.call(lambda: drain(second))

    assert one == two
    names = [e.name for e in one if e]
    assert names.count("job.updated") >= 4
    assert "queue.updated" in names
    final = [e.data["status"] for e in one if e and e.name == "job.updated"]
    assert final.count("completed") == 2


def test_removals_reach_every_tab(make_jobs_client, server_loop: LoopThread) -> None:
    broadcaster = EventBroadcaster()
    broadcaster.bind_loop(server_loop.loop)
    client = make_jobs_client(broadcaster=broadcaster)
    job_id = enqueue(client).json()["jobs"][0]["id"]
    tabs = [broadcaster.subscribe(), broadcaster.subscribe()]

    client.delete(f"/api/jobs/{job_id}", headers=APP_HEADERS)

    for tab in tabs:
        assert server_loop.call(lambda tab=tab: drain(tab)) == [
            Event("job.removed", {"id": job_id})
        ]


def test_a_slow_client_blocks_neither_the_runner_nor_the_other_clients(
    make_jobs_client, server_loop: LoopThread, fake_engine
) -> None:
    broadcaster = EventBroadcaster()
    broadcaster.bind_loop(server_loop.loop)
    stuck = broadcaster.subscribe(size=2)  # a tab that never reads
    healthy = broadcaster.subscribe(size=10_000)
    client = make_jobs_client(broadcaster=broadcaster)

    # Inline jobs: if publishing could block, these requests would hang instead of completing.
    ids = [enqueue(client, url).json()["jobs"][0]["id"] for url in (ZOO, SHORT)]

    assert [client.get(f"/api/jobs/{i}").json()["status"] for i in ids] == ["completed"] * 2
    seen = server_loop.call(lambda: drain(healthy))
    statuses = [e.data["status"] for e in seen if e and e.name == "job.updated"]
    assert statuses.count("completed") == 2  # the healthy tab missed nothing
    assert broadcaster.client_count == 1  # the stuck one was dropped...
    assert server_loop.call(lambda: drain(stuck)) == [None]  # ...its stream ends and is empty


def test_a_dropped_client_can_reconnect_and_rehydrate(
    make_jobs_client, server_loop: LoopThread
) -> None:
    broadcaster = EventBroadcaster()
    broadcaster.bind_loop(server_loop.loop)
    stuck = broadcaster.subscribe(size=1)
    client = make_jobs_client(broadcaster=broadcaster)
    job_id = enqueue(client).json()["jobs"][0]["id"]
    assert server_loop.call(lambda: drain(stuck))[-1] is None

    # The browser reconnects: a new subscription and the current state from the API.
    broadcaster.unsubscribe(stuck)
    again = broadcaster.subscribe()
    page = client.get("/api/jobs", params={"status": "completed"}).json()

    assert broadcaster.client_count == 1
    assert [j["id"] for j in page["jobs"]] == [job_id]
    assert again.queue.empty()
