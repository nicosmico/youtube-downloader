"""Idle Shutdown (ADR-0001): the app closes itself when nobody is using it.

Idle means: no SSE client, no `queued`/`downloading`/`processing` job and no Engine install or
update in progress. Once all three hold, a timer runs; any connection (or disconnection) and any
event published (a job or the Engine changing) restarts it. The clock is injected, so tests move
time by hand and call `check()` instead of waiting.

The timeout is short (15 s) because the app has no window: closing the last tab should end it, and
an update needs the old app gone. Until the first tab has ever connected the app waits at least
`STARTUP_GRACE_SECONDS`, so a slow browser launch does not find the app already closed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

log = logging.getLogger("app.idle")

IDLE_SHUTDOWN_SECONDS = 15.0
STARTUP_GRACE_SECONDS = 60.0
MAX_POLL_SECONDS = 1.0


class IdleMonitor:
    def __init__(
        self,
        *,
        timeout: float,
        clients: Callable[[], int],
        busy: Callable[[], bool],
        on_idle: Callable[[], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout = timeout
        self._clients = clients
        self._busy = busy
        self._on_idle = on_idle
        self._clock = clock
        # Starting the app counts as activity: the first tab has `timeout` to show up.
        self._since = clock()
        self._fired = False
        self._seen_client = False

    @property
    def poll_seconds(self) -> float:
        return max(0.1, min(MAX_POLL_SECONDS, self.timeout / 10))

    @property
    def effective_timeout(self) -> float:
        """Before any tab has ever connected the first one gets the startup grace."""
        return self.timeout if self._seen_client else max(STARTUP_GRACE_SECONDS, self.timeout)

    def touch(self) -> None:
        """Something happened (a connection, a job, the Engine): the idle time starts over."""
        if self._clients() > 0:
            self._seen_client = True  # a tab that came and went between two polls still counts
        self._since = self._clock()

    def check(self) -> bool:
        """Evaluate the conditions now. True (once) when it triggered the shutdown."""
        if self._fired:
            return False
        now = self._clock()
        if self._clients() > 0:
            self._seen_client = True
            self._since = now
            return False
        if self._busy():
            self._since = now
            return False
        if now - self._since < self.effective_timeout:
            return False
        self._fired = True
        log.info("Idle for %.0f s: shutting down", now - self._since)
        self._on_idle()
        return True

    async def run(self, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        while not self._fired:
            await sleep(self.poll_seconds)
            try:
                self.check()
            except Exception:
                log.exception("Idle check failed")
