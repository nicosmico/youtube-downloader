"""Short-lived cache of the raw `yt-dlp -J` output of single videos.

A download that starts soon after its preview reuses that output (`--load-info-json`) instead of
making yt-dlp extract the same information again from YouTube. Entries are kept in memory only.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable

# The format URLs inside the JSON expire after about 6 hours: one hour is well inside that.
INFO_TTL_SECONDS = 3600.0
INFO_MAX_ENTRIES = 20


class InfoCache:
    """LRU of at most `max_entries` raw JSON texts, valid for `ttl` seconds, keyed by the
    canonical video URL. Thread-safe: previews run in the API threadpool, downloads in the
    runner threads."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl: float = INFO_TTL_SECONDS,
        max_entries: int = INFO_MAX_ENTRIES,
    ) -> None:
        self._clock = clock
        self._ttl = ttl
        self._max = max_entries
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def put(self, url: str, raw: str) -> None:
        with self._lock:
            self._entries[url] = (self._clock(), raw)
            self._entries.move_to_end(url)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)

    def get(self, url: str) -> str | None:
        """The stored text if it is still valid (and now the most recently used), else None."""
        with self._lock:
            entry = self._entries.get(url)
            if entry is None:
                return None
            obtained_at, raw = entry
            if self._clock() - obtained_at >= self._ttl:
                del self._entries[url]
                return None
            self._entries.move_to_end(url)
            return raw

    def discard(self, url: str) -> None:
        with self._lock:
            self._entries.pop(url, None)
