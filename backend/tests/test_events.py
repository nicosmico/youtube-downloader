from __future__ import annotations

import asyncio
import threading

from app.events import Event, EventBroadcaster, event_stream


def run(coro):
    return asyncio.run(coro)


def test_event_encoding() -> None:
    assert Event("engine.updated", {"status": "ready"}).encode() == (
        'event: engine.updated\ndata: {"status":"ready"}\n\n'
    )


def test_publish_reaches_every_subscriber() -> None:
    async def scenario() -> list[Event | None]:
        broadcaster = EventBroadcaster()
        broadcaster.bind_loop(asyncio.get_running_loop())
        first, second = broadcaster.subscribe(), broadcaster.subscribe()
        broadcaster.publish("x", 1)
        return [await first.get(), await second.get()]

    assert run(scenario()) == [Event("x", 1), Event("x", 1)]


def test_publish_from_another_thread_is_delivered_on_the_loop() -> None:
    async def scenario() -> Event | None:
        broadcaster = EventBroadcaster()
        broadcaster.bind_loop(asyncio.get_running_loop())
        sub = broadcaster.subscribe()
        threading.Thread(target=lambda: broadcaster.publish("from-thread", {"n": 1})).start()
        return await asyncio.wait_for(sub.get(), 2)

    assert run(scenario()) == Event("from-thread", {"n": 1})


def test_a_slow_client_is_dropped_and_its_queue_is_bounded() -> None:
    async def scenario() -> tuple[int, list[Event | None], int]:
        broadcaster = EventBroadcaster(queue_size=2)
        broadcaster.bind_loop(asyncio.get_running_loop())
        slow, fast = broadcaster.subscribe(), broadcaster.subscribe()
        broadcaster.publish("e", 1)
        broadcaster.publish("e", 2)
        await asyncio.sleep(0)
        fast.queue.get_nowait()
        fast.queue.get_nowait()
        broadcaster.publish("e", 3)  # slow is full now
        await asyncio.sleep(0)
        return slow.queue.qsize(), [await slow.get()], broadcaster.client_count

    size, drained, clients = run(scenario())

    assert size == 1  # emptied and ended with the close sentinel
    assert drained == [None]
    assert clients == 1


def test_stream_emits_initial_events_heartbeats_and_ends_on_close() -> None:
    async def scenario() -> list[str]:
        broadcaster = EventBroadcaster()
        broadcaster.bind_loop(asyncio.get_running_loop())
        sub = broadcaster.subscribe()
        closed: list[bool] = []
        chunks: list[str] = []
        stream = event_stream(
            sub,
            initial=[Event("engine.updated", {"status": "missing"})],
            heartbeat=0.02,
            on_close=lambda: closed.append(True),
        )
        async for chunk in stream:
            chunks.append(chunk)
            if len(chunks) == 2:
                broadcaster.publish("engine.updated", {"status": "ready"})
            if len(chunks) == 4:
                broadcaster.close()
        assert closed == [True]
        return chunks

    chunks = run(scenario())

    assert chunks[0].startswith("event: engine.updated")
    assert ": heartbeat\n\n" in chunks
    assert 'data: {"status":"ready"}' in "".join(chunks)
