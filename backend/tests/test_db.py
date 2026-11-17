from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db import MIGRATIONS, Database


def tables(db: Database) -> set[str]:
    return {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_migrations_create_batches_and_jobs_in_wal_mode(tmp_path: Path) -> None:
    db = Database(tmp_path / "db.sqlite3")

    assert db.migrate() == len(MIGRATIONS)

    assert {"batches", "jobs"} <= tables(db)
    assert "presets" not in tables(db)
    assert db.query("PRAGMA journal_mode")[0][0] == "wal"
    columns = {r["name"] for r in db.query("PRAGMA table_info(jobs)")}
    assert {"batch_id", "playlist_index", "audio_format", "output_path", "attempt"} <= columns


def test_migrate_is_idempotent_and_keeps_data(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite3"
    db = Database(path)
    db.migrate()
    db.execute(
        "INSERT INTO jobs (id, url, mode, status, created_at) "
        "VALUES ('a', 'u', 'video', 'queued', 't')"
    )
    db.close()

    again = Database(path)
    assert again.migrate() == len(MIGRATIONS)
    assert again.migrate() == len(MIGRATIONS)
    assert again.query("SELECT id FROM jobs")[0]["id"] == "a"


def test_only_pending_migrations_run(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite3"
    Database(path).migrate()
    extra = (*MIGRATIONS, (99, "CREATE TABLE extra (id TEXT); CREATE TABLE extra2 (id TEXT)"))

    db = Database(path, extra)

    assert db.migrate() == 99
    assert {"extra", "extra2"} <= tables(db)


def test_a_failing_migration_rolls_back(tmp_path: Path) -> None:
    db = Database(tmp_path / "db.sqlite3", ((1, "CREATE TABLE ok (id TEXT); NOT SQL"),))

    with pytest.raises(sqlite3.OperationalError):
        db.migrate()

    assert "ok" not in tables(db)
    assert db.query("PRAGMA user_version")[0][0] == 0


def test_a_v0_1_0_database_migrates_and_loses_the_presets_table(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite3"
    v0_1_0 = Database(path, MIGRATIONS[:3])
    assert v0_1_0.migrate() == 3
    v0_1_0.execute(
        "INSERT INTO presets (id, name, mode, quality, audio_format, created_at) "
        "VALUES ('p', 'Ligero', 'video', '480p', NULL, 't')"
    )
    v0_1_0.execute(
        "INSERT INTO jobs (id, url, mode, status, created_at) "
        "VALUES ('a', 'u', 'video', 'completed', 't')"
    )
    v0_1_0.close()

    db = Database(path)

    assert db.migrate() == len(MIGRATIONS)
    assert "presets" not in tables(db)
    assert db.query("SELECT id FROM jobs")[0]["id"] == "a"


def test_a_v0_1_1_database_migrates_and_its_jobs_have_no_thumbnail(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite3"
    v0_1_1 = Database(path, MIGRATIONS[:5])
    assert v0_1_1.migrate() == 5
    v0_1_1.execute(
        "INSERT INTO jobs (id, url, mode, status, created_at) "
        "VALUES ('a', 'u', 'video', 'completed', 't')"
    )
    v0_1_1.close()

    db = Database(path)

    assert db.migrate() == len(MIGRATIONS)
    assert "thumbnail" in {r["name"] for r in db.query("PRAGMA table_info(jobs)")}
    assert db.query("SELECT thumbnail FROM jobs WHERE id = 'a'")[0]["thumbnail"] is None


def test_a_v0_2_4_database_migrates_to_settings_and_job_download_dir(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite3"
    v0_2_4 = Database(path, MIGRATIONS[:6])
    assert v0_2_4.migrate() == 6
    v0_2_4.execute(
        "INSERT INTO jobs (id, url, mode, status, created_at) "
        "VALUES ('a', 'u', 'video', 'completed', 't')"
    )
    v0_2_4.close()

    db = Database(path)

    assert db.migrate() == len(MIGRATIONS)
    assert "settings" in tables(db)
    assert db.query("SELECT download_dir FROM jobs WHERE id = 'a'")[0]["download_dir"] is None
