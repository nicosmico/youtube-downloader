"""Notice of a newer app version (ADR-0011): a one-shot check of the latest GitHub Release.

The app never updates itself. At startup a background thread asks the public "latest release"
page where it redirects (no API, no token, no rate limit), compares the tag with the running
version and, only if it is strictly newer, remembers it and tells the open tabs. Any failure is
logged and swallowed: the check must never get in the way of the app or the Engine.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from app import __version__
from app.engine.io import Fetcher, FetchError, UrllibFetcher

log = logging.getLogger("app.updates")

REPO = "nicosmico/youtube-downloader"
LATEST_PAGE = f"https://github.com/{REPO}/releases/latest"
RELEASE_TAG_URL = f"https://github.com/{REPO}/releases/tag"

_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def parse_latest_version(location: str) -> str:
    """`X.Y.Z` from the `Location` of the "latest release" redirect (`.../releases/tag/vX.Y.Z`)."""
    prefix, sep, tag = urlsplit(location).path.rpartition("/releases/tag/")
    match = _TAG.fullmatch(tag)
    if not sep or prefix != f"/{REPO}" or not match:
        raise ValueError(f"redirección inesperada ({location[:80]!r})")
    return ".".join(match.groups())


def version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def is_newer(published: str, current: str) -> bool:
    return version_tuple(published) > version_tuple(current)


class UpdateNotice:
    """Holds the newer version found at startup (None until then, and if there is none)."""

    def __init__(
        self,
        *,
        fetcher: Fetcher | None = None,
        publish: Callable[[str, Any], None],
        current_version: str = __version__,
    ) -> None:
        self._fetcher = fetcher  # None: the real one, built only when the check runs
        self._publish = publish
        self._current = current_version
        self._update: dict[str, str] | None = None

    @property
    def update(self) -> dict[str, str] | None:
        return self._update

    def check(self) -> None:
        """Blocking, one attempt. Never raises."""
        try:
            fetcher = self._fetcher or UrllibFetcher()
            version = parse_latest_version(fetcher.redirect_location(LATEST_PAGE))
            if not is_newer(version, self._current):
                log.info("App up to date (installed %s, published %s)", self._current, version)
                return
            update = {"version": version, "url": f"{RELEASE_TAG_URL}/v{version}"}
            self._update = update
            log.info("New app version available: %s", version)
            self._publish("app.update", update)
        except FetchError as exc:
            log.info("Could not check for a new app version: %s", exc)
        except ValueError as exc:
            log.warning("Could not check for a new app version: %s", exc)
        except Exception:
            log.warning("Unexpected error checking for a new app version", exc_info=True)


def start_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="update-check", daemon=True).start()
