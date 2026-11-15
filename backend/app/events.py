"""Server-Sent Events: a small broadcaster plus the `GET /api/events` stream.

Later tickets publish `job.*`, `queue.updated` and `shutdown` through the same broadcaster.
Every client has a bounded queue; a client that falls behind is dropped (it reconnects and
rehydrates). Smarter slow-client handling is ticket 11.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

log = logging.getLogger("app.events")

HEARTBEAT_SECONDS = 15.0
CLIENT_QUEUE_SIZE = 100


@dataclass(frozen=True)
class Event:
    name: str
    data: Any

    def encode(self) -> str:
        return f"event: {self.name}\ndata: {json.dumps(self.data, separators=(',', ':'))}\n\n"


class Subscription:
    def __init__(self, size: int) -> None:
        self.queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=size)

    async def get(self) -> Event | None:
        return await self.queue.get()


class EventBroadcaster:
    def __init__(self, *, queue_size: int = CLIENT_QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._subscribers: set[Subscription] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def client_count(self) -> int:
        return len(self._subscribers)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the server's loop so worker threads can publish through it."""
        self._loop = loop

    def publish(self, name: str, data: Any) -> None:
        """Thread-safe: queue an event for every connected client."""
        event = Event(name, data)
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._dispatch(event)
        else:
            loop.call_soon_threadsafe(self._dispatch, event)

    def subscribe(self) -> Subscription:
        sub = Subscription(self._queue_size)
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subscribers.discard(sub)

    def close(self) -> None:
        """End every stream (server shutting down)."""
        for sub in list(self._subscribers):
            self._end(sub)

    def _dispatch(self, event: Event) -> None:
        for sub in list(self._subscribers):
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("Dropping a slow SSE client")
                self._end(sub)

    def _end(self, sub: Subscription) -> None:
        self._subscribers.discard(sub)
        while not sub.queue.empty():
            sub.queue.get_nowait()
        sub.queue.put_nowait(None)


async def event_stream(
    sub: Subscription,
    *,
    initial: list[Event],
    heartbeat: float = HEARTBEAT_SECONDS,
    on_close: Callable[[], None] = lambda: None,
) -> AsyncIterator[str]:
    try:
        for event in initial:
            yield event.encode()
        while True:
            try:
                event = await asyncio.wait_for(sub.get(), heartbeat)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if event is None:
                return
            yield event.encode()
    finally:
        on_close()


def build_events_router(
    broadcaster: EventBroadcaster,
    *,
    initial_events: Callable[[], list[Event]],
    heartbeat: float = HEARTBEAT_SECONDS,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/events")
    async def events() -> StreamingResponse:
        # Subscribe before building the snapshot so no change falls between the two.
        sub = broadcaster.subscribe()
        stream = event_stream(
            sub,
            initial=initial_events(),
            heartbeat=heartbeat,
            on_close=lambda: broadcaster.unsubscribe(sub),
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
