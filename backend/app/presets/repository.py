"""Persistence of presets. Names are unique ignoring case (the table's UNIQUE is case-sensitive)."""

from __future__ import annotations

import sqlite3
import threading
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db import Database

# Seeded at startup only while the table is empty (see `seed_defaults`).
DEFAULT_PRESETS: tuple[tuple[str, str, str | None, str | None], ...] = (
    ("Mejor video", "video", "best", None),
    ("MP3", "audio", None, "mp3"),
)


class PresetNameTaken(Exception):
    pass


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    mode: str
    quality: str | None
    audio_format: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Preset:
        return cls(
            id=row["id"],
            name=row["name"],
            mode=row["mode"],
            quality=row["quality"],
            audio_format=row["audio_format"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "quality": self.quality,
            "audioFormat": self.audio_format,
            "createdAt": self.created_at,
        }


def _sort_key(name: str) -> str:
    """Case- and accent-insensitive, so `Álamo` sorts next to `alfa`."""
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PresetRepository:
    def __init__(self, db: Database, now: Callable[[], datetime] = _utcnow) -> None:
        self._db = db
        self._now = now
        # Makes "is the name free?" + write atomic between request threads.
        self._lock = threading.Lock()

    def seed_defaults(self) -> bool:
        """Insert `Mejor video` and `MP3` if the table is empty; returns whether it did.

        Runs on every startup, so deleting every preset brings the defaults back at the next
        launch: "empty" is the only condition, no "already seeded" flag is kept.
        """
        with self._lock:
            if self._db.query("SELECT 1 FROM presets LIMIT 1"):
                return False
            for name, mode, quality, audio_format in DEFAULT_PRESETS:
                self._insert(name, mode, quality, audio_format)
            return True

    def list_presets(self) -> list[Preset]:
        """Sorted by name ignoring case and accents (SQLite's NOCASE would only fold ASCII)."""
        rows = self._db.query("SELECT * FROM presets")
        return sorted((Preset.from_row(r) for r in rows), key=lambda p: (_sort_key(p.name), p.id))

    def get(self, preset_id: str) -> Preset | None:
        rows = self._db.query("SELECT * FROM presets WHERE id = ?", (preset_id,))
        return Preset.from_row(rows[0]) if rows else None

    def create(
        self, *, name: str, mode: str, quality: str | None, audio_format: str | None
    ) -> Preset:
        with self._lock:
            self._ensure_free(name)
            return self._insert(name, mode, quality, audio_format)

    def update(
        self,
        preset_id: str,
        *,
        name: str,
        mode: str,
        quality: str | None,
        audio_format: str | None,
    ) -> Preset | None:
        """Replaces the fields of an existing preset; `None` when the id is unknown."""
        with self._lock:
            if self.get(preset_id) is None:
                return None
            self._ensure_free(name, except_id=preset_id)
            self._db.execute(
                "UPDATE presets SET name = ?, mode = ?, quality = ?, audio_format = ? WHERE id = ?",
                (name, mode, quality, audio_format, preset_id),
            )
            return self.get(preset_id)

    def delete(self, preset_id: str) -> bool:
        with self._lock:
            return self._db.execute("DELETE FROM presets WHERE id = ?", (preset_id,)) > 0

    def _ensure_free(self, name: str, except_id: str | None = None) -> None:
        folded = name.casefold()
        for preset in self.list_presets():
            if preset.id != except_id and preset.name.casefold() == folded:
                raise PresetNameTaken(name)

    def _insert(
        self, name: str, mode: str, quality: str | None, audio_format: str | None
    ) -> Preset:
        preset_id = uuid.uuid4().hex
        self._db.execute(
            "INSERT INTO presets (id, name, mode, quality, audio_format, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                preset_id,
                name,
                mode,
                quality,
                audio_format,
                self._now().isoformat(timespec="microseconds"),
            ),
        )
        preset = self.get(preset_id)
        assert preset is not None
        return preset
