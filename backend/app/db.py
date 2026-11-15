"""SQLite access (ADR-0004): one WAL connection shared by all threads, plus numbered migrations.

`PRAGMA user_version` stores the last applied migration, so `migrate()` is idempotent. Presets
(ticket 08) get their own migration; this file only holds what each ticket needs.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE batches (
          id TEXT PRIMARY KEY,
          source_url TEXT NOT NULL,
          title TEXT NOT NULL,
          folder_name TEXT NOT NULL,
          entry_count INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE jobs (
          id TEXT PRIMARY KEY,
          batch_id TEXT REFERENCES batches(id),
          playlist_index INTEGER,
          url TEXT NOT NULL,
          title TEXT,
          mode TEXT NOT NULL CHECK (mode IN ('video','audio')),
          quality TEXT,
          audio_format TEXT,
          status TEXT NOT NULL,
          progress_percent REAL NOT NULL DEFAULT 0,
          downloaded_bytes INTEGER,
          total_bytes INTEGER,
          speed REAL,
          eta INTEGER,
          output_path TEXT,
          error TEXT,
          attempt INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT
        );

        CREATE INDEX jobs_status_created ON jobs (status, created_at);
        """,
    ),
)


class Database:
    def __init__(self, path: Path, migrations: Iterable[tuple[int, str]] = MIGRATIONS) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # Autocommit: every statement is atomic; migrations open their own transaction.
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrations = tuple(sorted(migrations))

    def migrate(self) -> int:
        """Apply the pending migrations in order; returns the schema version."""
        with self._lock:
            current = self._conn.execute("PRAGMA user_version").fetchone()[0]
            for version, script in self._migrations:
                if version <= current:
                    continue
                self._conn.execute("BEGIN")
                try:
                    for statement in _statements(script):
                        self._conn.execute(statement)
                    self._conn.execute(f"PRAGMA user_version = {int(version)}")
                except BaseException:
                    self._conn.execute("ROLLBACK")
                    raise
                self._conn.execute("COMMIT")
                current = version
            return current

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Run a write; returns the number of rows changed."""
        with self._lock:
            return self._conn.execute(sql, tuple(params)).rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _statements(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]
