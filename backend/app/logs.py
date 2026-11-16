"""Read-only tail of the app log (`$DATA_DIR/app.log`) for the "Registros" section."""

from __future__ import annotations

from pathlib import Path

from app.logging_setup import LOG_FILE

MAX_LINES = 500
_CHUNK = 64 * 1024
# `uvicorn.access` lines are one per HTTP request: they bury everything else.
_REQUEST_MARK = " uvicorn.access: "


def read_log_tail(data_dir: Path, count: int, include_requests: bool) -> list[str]:
    """The last `count` lines (oldest first), continuing into the rotated `app.log.1` when the
    current file has fewer. Filters before counting, so the result is `count` useful lines."""
    count = max(0, min(count, MAX_LINES))
    base = data_dir / LOG_FILE
    collected: list[str] = []  # newest first
    for path in (base, base.with_name(f"{LOG_FILE}.1")):
        if len(collected) >= count:
            break
        for line in _reverse_lines(path):
            if include_requests or _REQUEST_MARK not in line:
                collected.append(line)
                if len(collected) >= count:
                    break
    collected.reverse()
    return collected


def _reverse_lines(path: Path):
    """Lines of a text file from the last to the first, reading it backwards in chunks so a
    large file is never loaded whole. Missing or unreadable files yield nothing."""
    try:
        with path.open("rb") as f:
            position = f.seek(0, 2)
            pending = b""
            while position > 0:
                size = min(_CHUNK, position)
                position -= size
                f.seek(position)
                pending = f.read(size) + pending
                pending, *rest = pending.split(b"\n")  # `pending` may be a partial first line
                for raw in reversed(rest):
                    if raw:
                        yield _decode(raw)
            if pending:
                yield _decode(pending)
    except OSError:
        return


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").rstrip("\r")
