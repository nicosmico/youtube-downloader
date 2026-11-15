"""/api/presets: seed, CRUD, uniqueness and option validation. No engine involved."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from tests.conftest import APP_HEADERS


def create(client: TestClient, **body):
    payload = {"name": "Mi preset", "mode": "video", "quality": "720p", **body}
    return client.post("/api/presets", json=payload, headers=APP_HEADERS)


def names(client: TestClient) -> list[str]:
    return [p["name"] for p in client.get("/api/presets").json()]


class TestSeed:
    def test_a_fresh_database_gets_the_two_defaults(self, client: TestClient) -> None:
        assert names(client) == ["Mejor video", "MP3"]

    def test_defaults_have_the_right_options(self, client: TestClient) -> None:
        by_name = {p["name"]: p for p in client.get("/api/presets").json()}

        assert by_name["Mejor video"]["mode"] == "video"
        assert by_name["Mejor video"]["quality"] == "best"
        assert by_name["Mejor video"]["audioFormat"] is None
        assert by_name["MP3"]["mode"] == "audio"
        assert by_name["MP3"]["quality"] is None
        assert by_name["MP3"]["audioFormat"] == "mp3"

    def test_a_restart_does_not_duplicate_or_resurrect_edits(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        first = make_client()
        mp3 = next(p for p in first.get("/api/presets").json() if p["name"] == "MP3")
        first.patch(f"/api/presets/{mp3['id']}", json={"name": "Solo audio"}, headers=APP_HEADERS)
        create(first, name="Extra")

        again = make_client()

        assert names(again) == ["Extra", "Mejor video", "Solo audio"]

    def test_the_seed_only_runs_when_the_table_is_empty(
        self, make_client: Callable[..., TestClient], data_dir: Path
    ) -> None:
        first = make_client()
        for preset in first.get("/api/presets").json():
            first.delete(f"/api/presets/{preset['id']}", headers=APP_HEADERS)
        create(first, name="Solo este")

        assert names(make_client()) == ["Solo este"]

    def test_an_emptied_table_is_seeded_again_at_the_next_start(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        first = make_client()
        for preset in first.get("/api/presets").json():
            first.delete(f"/api/presets/{preset['id']}", headers=APP_HEADERS)
        assert names(first) == []

        assert names(make_client()) == ["Mejor video", "MP3"]

    def test_presets_survive_a_restart(self, make_client: Callable[..., TestClient]) -> None:
        created = create(make_client(), name="Persistente", quality="480p").json()

        again = {p["id"]: p for p in make_client().get("/api/presets").json()}

        assert again[created["id"]]["name"] == "Persistente"
        assert again[created["id"]]["quality"] == "480p"


class TestList:
    def test_sorted_by_name_ignoring_case(self, client: TestClient) -> None:
        for name in ("zeta", "Álamo", "alfa", "Beta"):
            create(client, name=name)

        assert names(client) == ["Álamo", "alfa", "Beta", "Mejor video", "MP3", "zeta"]

    def test_camel_case_json(self, client: TestClient) -> None:
        preset = client.get("/api/presets").json()[0]

        assert set(preset) == {"id", "name", "mode", "quality", "audioFormat", "createdAt"}


class TestCreate:
    def test_video_preset(self, client: TestClient) -> None:
        response = create(client)

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Mi preset"
        assert (body["mode"], body["quality"], body["audioFormat"]) == ("video", "720p", None)
        assert body["id"]
        assert client.get("/api/presets").json().count(body) == 1

    def test_audio_preset(self, client: TestClient) -> None:
        response = create(client, mode="audio", quality=None, audioFormat="opus")

        assert response.status_code == 201
        assert response.json()["audioFormat"] == "opus"
        assert response.json()["quality"] is None

    def test_the_name_is_trimmed(self, client: TestClient) -> None:
        response = create(client, name="   Con espacios  ")

        assert response.json()["name"] == "Con espacios"

    @pytest.mark.parametrize("name", ["", "   ", "x" * 41])
    def test_a_name_outside_1_to_40_characters_is_rejected(
        self, client: TestClient, name: str
    ) -> None:
        response = create(client, name=name)

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_name"

    def test_forty_characters_are_fine(self, client: TestClient) -> None:
        assert create(client, name=" " + "x" * 40 + " ").status_code == 201

    @pytest.mark.parametrize("other", ["Mi preset", "mi PRESET", "MI PRESET  ", "mejor VIDEO"])
    def test_duplicate_names_are_refused_ignoring_case(
        self, client: TestClient, other: str
    ) -> None:
        create(client)

        response = create(client, name=other)

        assert response.status_code == 409
        assert response.json()["code"] == "preset_name_taken"
        assert "Ya existe" in response.json()["message"]

    def test_unicode_case_is_folded_too(self, client: TestClient) -> None:
        create(client, name="Ñandú")

        assert create(client, name="ñANDÚ").status_code == 409

    @pytest.mark.parametrize(
        "options",
        [
            {"mode": "video", "quality": None},
            {"mode": "video", "quality": "720p", "audioFormat": "mp3"},
            {"mode": "audio", "quality": None, "audioFormat": None},
            {"mode": "audio", "quality": "720p", "audioFormat": "mp3"},
            {"mode": "audio", "quality": "720p", "audioFormat": None},
        ],
    )
    def test_invalid_combinations_are_refused(self, client: TestClient, options: dict) -> None:
        response = create(client, **options)

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_options"
        assert names(client) == ["Mejor video", "MP3"]

    def test_values_outside_the_enums_are_validation_errors(self, client: TestClient) -> None:
        assert create(client, quality="144p").status_code == 422
        assert create(client, mode="gif").status_code == 422

    def test_a_refused_preset_is_not_stored(self, client: TestClient) -> None:
        create(client, name="Mala", quality=None)

        assert "Mala" not in names(client)

    def test_the_app_header_is_required(self, client: TestClient) -> None:
        response = client.post("/api/presets", json={"name": "x", "mode": "video"})

        assert response.status_code == 403


class TestUpdate:
    def preset_id(self, client: TestClient, name: str = "MP3") -> str:
        return next(p["id"] for p in client.get("/api/presets").json() if p["name"] == name)

    def patch(self, client: TestClient, preset_id: str, **body):
        return client.patch(f"/api/presets/{preset_id}", json=body, headers=APP_HEADERS)

    def test_rename_keeps_the_options(self, client: TestClient) -> None:
        response = self.patch(client, self.preset_id(client), name="  Audio  ")

        assert response.status_code == 200
        body = response.json()
        assert (body["name"], body["mode"], body["audioFormat"]) == ("Audio", "audio", "mp3")

    def test_renaming_to_its_own_name_with_other_case_is_allowed(self, client: TestClient) -> None:
        response = self.patch(client, self.preset_id(client), name="mp3")

        assert response.status_code == 200
        assert response.json()["name"] == "mp3"

    def test_renaming_to_an_existing_name_conflicts(self, client: TestClient) -> None:
        response = self.patch(client, self.preset_id(client), name="mejor VIDEO")

        assert response.status_code == 409
        assert response.json()["code"] == "preset_name_taken"
        assert "MP3" in names(client)

    def test_change_options_within_the_mode(self, client: TestClient) -> None:
        response = self.patch(client, self.preset_id(client), audioFormat="opus")

        assert response.status_code == 200
        assert response.json()["audioFormat"] == "opus"

    def test_switch_mode_replaces_the_options(self, client: TestClient) -> None:
        response = self.patch(client, self.preset_id(client), mode="video", quality="480p")

        assert response.status_code == 200
        body = response.json()
        assert (body["mode"], body["quality"], body["audioFormat"]) == ("video", "480p", None)

    def test_switch_mode_without_the_new_options_is_invalid(self, client: TestClient) -> None:
        response = self.patch(client, self.preset_id(client), mode="video")

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_options"

    def test_a_stale_field_after_a_mode_switch_is_invalid(self, client: TestClient) -> None:
        response = self.patch(
            client, self.preset_id(client), mode="video", quality="480p", audioFormat="mp3"
        )

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_options"

    def test_invalid_patch_changes_nothing(self, client: TestClient) -> None:
        pid = self.preset_id(client)

        self.patch(client, pid, name="Nuevo", quality="720p")

        assert names(client) == ["Mejor video", "MP3"]

    @pytest.mark.parametrize("name", ["", "  ", "x" * 41, None])
    def test_invalid_names(self, client: TestClient, name: str | None) -> None:
        response = self.patch(client, self.preset_id(client), name=name)

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_name"

    def test_an_empty_patch_is_a_no_op(self, client: TestClient) -> None:
        pid = self.preset_id(client)
        before = client.get("/api/presets").json()

        assert self.patch(client, pid).status_code == 200
        assert client.get("/api/presets").json() == before

    def test_unknown_id(self, client: TestClient) -> None:
        response = self.patch(client, "nope", name="x")

        assert response.status_code == 404
        assert response.json()["code"] == "preset_not_found"


class TestDelete:
    def test_removes_the_preset(self, client: TestClient) -> None:
        pid = next(p["id"] for p in client.get("/api/presets").json() if p["name"] == "MP3")

        response = client.delete(f"/api/presets/{pid}", headers=APP_HEADERS)

        assert response.status_code == 204
        assert names(client) == ["Mejor video"]

    def test_the_name_is_free_again(self, client: TestClient) -> None:
        pid = next(p["id"] for p in client.get("/api/presets").json() if p["name"] == "MP3")
        client.delete(f"/api/presets/{pid}", headers=APP_HEADERS)

        assert create(client, name="mp3").status_code == 201

    def test_unknown_id(self, client: TestClient) -> None:
        response = client.delete("/api/presets/nope", headers=APP_HEADERS)

        assert response.status_code == 404
        assert response.json()["code"] == "preset_not_found"


class TestMigration:
    def test_the_presets_table_matches_the_spec(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "db.sqlite3")
        db.migrate()

        columns = {r["name"]: r for r in db.query("PRAGMA table_info(presets)")}

        assert set(columns) == {"id", "name", "mode", "quality", "audio_format", "created_at"}
        assert columns["name"]["notnull"] == 1
        assert any(
            r["unique"]
            and [c["name"] for c in db.query(f"PRAGMA index_info({r['name']})")] == ["name"]
            for r in db.query("PRAGMA index_list(presets)")
        )

    def test_an_existing_v1_database_gets_the_table_and_keeps_its_jobs(
        self, tmp_path: Path
    ) -> None:
        from app.db import MIGRATIONS

        path = tmp_path / "db.sqlite3"
        old = Database(path, MIGRATIONS[:1])
        assert old.migrate() == 1
        old.execute(
            "INSERT INTO jobs (id, url, mode, status, created_at) "
            "VALUES ('a', 'u', 'video', 'queued', 't')"
        )
        old.close()

        db = Database(path)
        assert db.migrate() == 3
        assert db.query("SELECT id FROM jobs")[0]["id"] == "a"
        # Jobs that predate `queued_at` keep their place in the line.
        assert db.query("SELECT queued_at FROM jobs")[0]["queued_at"] == "t"
        assert db.query("SELECT COUNT(*) FROM presets")[0][0] == 0
