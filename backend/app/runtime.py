"""`runtime.json`: tells other processes where the running instance listens."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

RUNTIME_FILE = "runtime.json"


@dataclass(frozen=True)
class RuntimeInfo:
    pid: int
    port: int
    startedAt: str  # noqa: N815 - serialized name is part of the file format


def runtime_path(data_dir: Path) -> Path:
    return data_dir / RUNTIME_FILE


def write_runtime(data_dir: Path, port: int) -> RuntimeInfo:
    info = RuntimeInfo(pid=os.getpid(), port=port, startedAt=datetime.now(UTC).isoformat())
    path = runtime_path(data_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(info)), encoding="utf-8")
    os.replace(tmp, path)
    return info


def read_runtime(data_dir: Path) -> RuntimeInfo | None:
    try:
        raw = json.loads(runtime_path(data_dir).read_text(encoding="utf-8"))
        return RuntimeInfo(
            pid=int(raw["pid"]), port=int(raw["port"]), startedAt=str(raw["startedAt"])
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def remove_runtime(data_dir: Path, *, only_pid: int | None = None) -> None:
    """Delete runtime.json; with `only_pid`, only if it still belongs to that process."""
    if only_pid is not None:
        info = read_runtime(data_dir)
        if info is not None and info.pid != only_pid:
            return
    runtime_path(data_dir).unlink(missing_ok=True)
