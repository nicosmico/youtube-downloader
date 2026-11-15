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
    fail_with: str | None = None  # stderr text; the process exits with 1 after some progress
    hold: bool = False  # block after the first progress line until `release()`
    content: bytes = b"fake-video-bytes"
    no_path: bool = False  # do not print the final path (the runner must find the file)


class FakeHandle:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.handles: list[FakeHandle] = []
        self.scenarios: dict[str, Scenario] = {}
        self.default = Scenario()
        self.tick: Callable[[], None] = lambda: None  # called after every progress line
        self.start_error: str | None = None
        self._release = threading.Event()
        self._cond = threading.Condition()
        self._running = 0

    def scenario(self, url: str, **changes) -> Scenario:
        sc = Scenario(**changes)
        self.scenarios[url] = sc
        return sc

    def release(self) -> None:
        self._release.set()

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
        handle = FakeHandle()
        self.handles.append(handle)
        if on_start:
            on_start(handle)
        with self._cond:
            self._running += 1
            self._cond.notify_all()
        try:
            return self._run(sc, staging, on_stdout, on_stderr)
        finally:
            with self._cond:
                self._running -= 1

    def _run(self, sc: Scenario, staging: Path, on_stdout, on_stderr) -> int:
        first = True
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
                        self._release.wait(10)
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
