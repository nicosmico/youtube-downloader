"""FakeEngine: stands in for the yt-dlp *download* process at the `Streamer` edge.

It reads the same arguments the real process gets (`-P <staging>`, `-o`, the URL last), emits
realistic `PROGRESS` lines on stdout (video then audio stream) and `POSTPROC` lines on stderr,
writes the final file inside the staging folder and prints its path as the last stdout line.
A scenario can also fail with stderr or hold the download open until `release()`.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.engine.io import ProcessError, ProcessHandle


@dataclass
class Scenario:
    title: str = "Me at the zoo"
    ext: str = "mp4"
    # (filename, total bytes): yt-dlp downloads video and audio as two consecutive streams.
    streams: list[tuple[str, int | None]] = field(
        default_factory=lambda: [("zoo.f399.mp4", 4000), ("zoo.f140.m4a", 1000)]
    )
    lines_per_stream: int = 3
    estimate_only: bool = False  # `total_bytes` null, `total_bytes_estimate` set (fragments)
    postprocessors: tuple[str, ...] = ("Merger", "MoveFiles")
    stdout_lines: tuple[str, ...] = ()  # plain (non-progress) lines printed before the end
    stderr_lines: tuple[str, ...] = ()  # warnings printed on stderr before the end
    fail_with: str | None = None  # stderr text; the process exits with 1 after some progress
    hold: bool = False  # block after the first progress line until `release()` or a stop
    ignore_terminate: bool = False  # a stubborn process: only `kill()` stops it
    content: bytes = b"fake-video-bytes"
    announce_total: bool = True  # print `TOTAL<sum of the streams>` first (before_dl)
    total_override: int | None = None  # what TOTAL announces instead (e.g. an approximation)
    no_path: bool = False  # do not print the final path (the runner must find the file)


class FakeHandle:
    """terminate() ends a held process with a signal exit code, like a real one would."""

    def __init__(self, url: str = "", ignore_terminate: bool = False) -> None:
        self.url = url
        self.terminated = False
        self.killed = False
        self._ignore_terminate = ignore_terminate
        self.wake = threading.Event()

    def terminate(self) -> None:
        self.terminated = True
        if not self._ignore_terminate:
            self.wake.set()

    def kill(self) -> None:
        self.killed = True
        self.wake.set()

    @property
    def stopped(self) -> bool:
        return self.killed or (self.terminated and not self._ignore_terminate)


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.handles: list[FakeHandle] = []
        self.scenarios: dict[str, Scenario] = {}
        self.default = Scenario()
        self.tick: Callable[[], None] = lambda: None  # called after every progress line
        self.start_error: str | None = None
        self.on_begin: Callable[[str], None] = lambda url: None  # called as a download begins
        self.started: list[str] = []  # URLs, in the order their process began
        self.peak = 0  # most downloads inside the fake process at the same time
        self._release = threading.Event()
        self._cond = threading.Condition()
        self._running = 0

    def scenario(self, url: str, **changes) -> Scenario:
        sc = Scenario(**changes)
        self.scenarios[url] = sc
        return sc

    def release(self) -> None:
        """Let every held download (now and later) go on."""
        self._release.set()
        for handle in list(self.handles):
            handle.wake.set()

    def release_url(self, url: str) -> None:
        """Let the held download of one URL go on."""
        for handle in list(self.handles):
            if handle.url == url:
                handle.wake.set()

    def wait_started(self, count: int, timeout: float = 5) -> bool:
        """Wait until `count` downloads have begun in total."""
        with self._cond:
            return self._cond.wait_for(lambda: len(self.started) >= count, timeout)

    def wait_running(self, count: int, timeout: float = 5) -> bool:
        """Wait until `count` downloads are inside the fake process at the same time."""
        with self._cond:
            return self._cond.wait_for(lambda: self._running >= count, timeout)

    def __call__(
        self,
        args: Sequence[str],
        on_stdout: Callable[[str], None],
        on_stderr: Callable[[str], None],
        on_start: Callable[[ProcessHandle], None] | None = None,
    ) -> int:
        self.calls.append(list(args))
        if self.start_error:
            raise ProcessError(self.start_error)
        staging = Path(args[args.index("-P") + 1])
        sc = self.scenarios.get(args[-1], self.default)
        handle = FakeHandle(args[-1], sc.ignore_terminate)
        self.handles.append(handle)
        if on_start:
            on_start(handle)
        self.on_begin(args[-1])
        with self._cond:
            self._running += 1
            self.peak = max(self.peak, self._running)
            self.started.append(args[-1])
            self._cond.notify_all()
        try:
            return self._run(sc, staging, on_stdout, on_stderr, handle)
        finally:
            with self._cond:
                self._running -= 1

    def _run(self, sc: Scenario, staging: Path, on_stdout, on_stderr, handle: FakeHandle) -> int:
        first = True
        if sc.announce_total:
            sizes = [t if t is not None else 300 for _, t in sc.streams]
            total = sc.total_override if sc.total_override is not None else sum(sizes)
            on_stdout(f"TOTAL{total}")
        for name, total in sc.streams:
            tmp = str(staging / f"{name}.part")
            size = total if total is not None else 300
            for i in range(1, sc.lines_per_stream + 1):
                done = size * i // sc.lines_per_stream
                on_stdout(
                    "PROGRESS"
                    + json.dumps(
                        {
                            "status": "downloading",
                            "downloaded_bytes": done,
                            "total_bytes": None if sc.estimate_only else total,
                            "total_bytes_estimate": size if sc.estimate_only else None,
                            "speed": 1_000_000.0,
                            "eta": sc.lines_per_stream - i,
                            "filename": str(staging / name),
                            "tmpfilename": tmp,
                        }
                    )
                )
                self.tick()
                if first:
                    first = False
                    (staging / f"{name}.part").write_bytes(b"partial")
                    if sc.hold:
                        if not self._release.is_set():
                            handle.wake.wait(10)
                        if handle.stopped:
                            return -15
            on_stdout(
                "PROGRESS"
                + json.dumps(
                    {
                        "status": "finished",
                        "downloaded_bytes": size,
                        "total_bytes": size,
                        "filename": str(staging / name),
                        "tmpfilename": tmp,
                    }
                )
            )
        for line in sc.stdout_lines:
            on_stdout(line)
        for line in sc.stderr_lines:
            on_stderr(line)
        if sc.fail_with is not None:
            on_stderr(sc.fail_with)
            return 1
        for pp in sc.postprocessors:
            on_stderr("POSTPROC" + json.dumps({"status": "started", "postprocessor": pp}))
            on_stderr("POSTPROC" + json.dumps({"status": "finished", "postprocessor": pp}))
        final = staging / f"{sc.title}.{sc.ext}"
        final.write_bytes(sc.content)
        for part in staging.glob("*.part"):
            part.unlink()
        if not sc.no_path:
            on_stdout(str(final))
        return 0
