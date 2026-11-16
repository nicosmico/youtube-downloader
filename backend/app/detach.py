"""macOS: the packaged app's executable hands the server to a detached child and exits.

LaunchServices allows one instance per bundle: opening the .app again while it runs asks that
process to activate, and a Python server cannot answer, so Finder reports the app as "no longer
open". If the process LaunchServices started exits right away, every double click starts a new
launcher that goes through Single Instance.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence

SERVER_CHILD_ENV = "YTDL_SERVER_CHILD"

Spawner = Callable[..., object]


def should_detach(*, frozen: bool, platform: str, env: Mapping[str, str]) -> bool:
    return frozen and platform == "darwin" and env.get(SERVER_CHILD_ENV) != "1"


def spawn_server_child(
    executable: str,
    args: Sequence[str],
    env: Mapping[str, str],
    spawner: Spawner = subprocess.Popen,
) -> None:
    """Start the same executable as the server: new session, no stdio, marked as the child."""
    spawner(
        [executable, *args],
        env={**env, SERVER_CHILD_ENV: "1"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def detach_if_needed(argv: Sequence[str]) -> bool:
    """True when a detached child took over and this process should exit with 0."""
    if not should_detach(
        frozen=bool(getattr(sys, "frozen", False)), platform=sys.platform, env=os.environ
    ):
        return False
    spawn_server_child(sys.executable, list(argv), os.environ)
    return True
