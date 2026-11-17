"""The configurable download folder (ADR-0012): settings API, jobs, files and open-downloads.

The native dialog is never opened: `pick_folder` is a fake injected into the app.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import download_dir as download_dir_module
from app.download_dir import DownloadDir
from app.folder_picker import PickerUnavailable
from app.jobs.failures import DOWNLOAD_DIR_UNAVAILABLE
from tests.conftest import APP_HEADERS, RecordingBroadcaster
from tests.fake_engine import FakeEngine
from tests.test_jobs_api import ZOO, downloads, enqueue, get_job
from tests.test_playlist_jobs import enqueue_playlist, entry, tree

URL = "/api/settings/download-dir"


class FakePicker:
    """Stands in for the native dialog: answers `result` (or raises `error`) and records `start`."""

    def __init__(self) -> None:
        self.result: Path | None = None
        self.error: Exception | None = None
        self.starts: list[Path | None] = []
        self.entered = threading.Event()  # set when a call is inside the "dialog"
        self.close = threading.Event()  # when `hold` is on, the dialog stays open until set
        self.hold = False

    def __call__(self, start: Path | None) -> Path | None:
        self.starts.append(start)
        self.entered.set()
        if self.hold:
            assert self.close.wait(5)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def picker() -> FakePicker:
    return FakePicker()


@pytest.fixture
def chosen(tmp_path: Path) -> Path:
    path = tmp_path / "Música"
    path.mkdir()
    return path


@pytest.fixture
def client(make_jobs_client: Callable[..., TestClient], picker: FakePicker) -> TestClient:
    return make_jobs_client(pick_folder=picker)


def put(client: TestClient, path: Path | str):
    return client.put(URL, json={"path": str(path)}, headers=APP_HEADERS)


class TestReadAndWrite:
    def test_starts_on_the_default_folder(
        self, client: TestClient, download_dir: Path, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))  # `~` is where the default lives

        body = client.get(URL).json()

        assert body == {
            "path": str(download_dir),
            "display": "~/downloads",
            "isDefault": True,
            "available": True,  # it does not exist yet: it is created when a file is moved in
        }

    def test_put_saves_a_valid_folder_and_publishes_settings_updated(
        self,
        client: TestClient,
        chosen: Path,
        tmp_path: Path,
        events: RecordingBroadcaster,
        monkeypatch,
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))

        response = put(client, chosen)

        expected = {
            "path": str(chosen),
            "display": "~/Música",
            "isDefault": False,
            "available": True,
        }
        assert response.status_code == 200
        assert response.json() == expected
        assert client.get(URL).json() == expected
        assert events.named("settings.updated") == [expected]

    def test_a_folder_outside_home_shows_its_full_path(
        self, client: TestClient, chosen: Path, tmp_path: Path, monkeypatch
    ) -> None:
        home = tmp_path / "somebody"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))

        assert put(client, chosen).json()["display"] == str(chosen)

    @pytest.mark.parametrize("kind", ["relative", "missing", "file", "empty"])
    def test_put_rejects_what_is_not_an_existing_absolute_folder(
        self, client: TestClient, tmp_path: Path, events: RecordingBroadcaster, kind: str
    ) -> None:
        (tmp_path / "a-file").write_text("x")
        path = {
            "relative": "Música",
            "missing": str(tmp_path / "nope"),
            "file": str(tmp_path / "a-file"),
            "empty": "",
        }[kind]

        response = put(client, path)

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_download_dir"
        assert client.get(URL).json()["isDefault"] is True
        assert events.named("settings.updated") == []

    def test_put_rejects_a_folder_that_cannot_be_written(
        self, client: TestClient, chosen: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def denied(*args, **kwargs):
            raise PermissionError("read-only")

        monkeypatch.setattr(download_dir_module.tempfile, "TemporaryFile", denied)

        response = put(client, chosen)

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "download_dir_not_writable"
        assert body["message"] == "No se puede escribir en esa carpeta. Elige otra."
        assert client.get(URL).json()["isDefault"] is True

    def test_the_writability_check_leaves_nothing_behind(
        self, client: TestClient, chosen: Path
    ) -> None:
        put(client, chosen)

        assert list(chosen.iterdir()) == []

    def test_putting_the_default_folder_is_the_same_as_resetting(
        self, client: TestClient, chosen: Path, download_dir: Path
    ) -> None:
        put(client, chosen)
        download_dir.mkdir()

        body = put(client, download_dir).json()

        assert body["isDefault"] is True and body["path"] == str(download_dir)

    def test_delete_goes_back_to_the_default_and_publishes(
        self, client: TestClient, chosen: Path, download_dir: Path, events: RecordingBroadcaster
    ) -> None:
        put(client, chosen)

        response = client.delete(URL, headers=APP_HEADERS)

        assert response.status_code == 200
        assert response.json()["path"] == str(download_dir)
        assert response.json()["isDefault"] is True
        assert [e["isDefault"] for e in events.named("settings.updated")] == [False, True]

    def test_nothing_is_published_when_nothing_changes(
        self, client: TestClient, events: RecordingBroadcaster
    ) -> None:
        client.delete(URL, headers=APP_HEADERS)

        assert events.named("settings.updated") == []

    def test_a_chosen_folder_that_disappears_is_reported_unavailable(
        self, client: TestClient, chosen: Path
    ) -> None:
        put(client, chosen)
        chosen.rmdir()

        body = client.get(URL).json()

        assert body["available"] is False and body["isDefault"] is False

    def test_the_choice_survives_a_restart(
        self, make_jobs_client: Callable[..., TestClient], chosen: Path
    ) -> None:
        put(make_jobs_client(), chosen)

        again = make_jobs_client()  # same data dir: a new app over the same SQLite

        assert again.get(URL).json()["path"] == str(chosen)

    def test_display_abbreviates_the_home_folder_itself(self, tmp_path: Path) -> None:
        setting = DownloadDir(None, tmp_path / "d", home=lambda: tmp_path)  # type: ignore[arg-type]

        assert setting.display(tmp_path) == "~"
        assert setting.display(tmp_path / "a" / "b") == "~/a/b"

    def test_display_is_the_full_path_on_windows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(download_dir_module.sys, "platform", "win32")
        setting = DownloadDir(None, tmp_path / "d", home=lambda: tmp_path)  # type: ignore[arg-type]

        assert setting.display(tmp_path / "a") == str(tmp_path / "a")


class TestChoose:
    def test_saves_the_chosen_folder_and_returns_the_get_object(
        self,
        client: TestClient,
        picker: FakePicker,
        chosen: Path,
        download_dir: Path,
        events: RecordingBroadcaster,
    ) -> None:
        picker.result = chosen

        response = client.post(f"{URL}/choose", headers=APP_HEADERS)

        assert response.status_code == 200
        assert response.json() == client.get(URL).json()
        assert response.json()["path"] == str(chosen)
        assert picker.starts == [download_dir]  # opens at the current folder
        assert len(events.named("settings.updated")) == 1

    def test_the_next_dialog_opens_at_the_chosen_folder(
        self, client: TestClient, picker: FakePicker, chosen: Path
    ) -> None:
        picker.result = chosen
        client.post(f"{URL}/choose", headers=APP_HEADERS)

        client.post(f"{URL}/choose", headers=APP_HEADERS)

        assert picker.starts[-1] == chosen

    def test_canceling_changes_nothing(
        self, client: TestClient, picker: FakePicker, events: RecordingBroadcaster
    ) -> None:
        picker.result = None

        response = client.post(f"{URL}/choose", headers=APP_HEADERS)

        assert response.status_code == 200
        assert response.json() == {"canceled": True}
        assert client.get(URL).json()["isDefault"] is True
        assert events.named("settings.updated") == []

    def test_without_a_native_dialog_it_is_501(
        self, client: TestClient, picker: FakePicker
    ) -> None:
        picker.error = PickerUnavailable("linux")

        response = client.post(f"{URL}/choose", headers=APP_HEADERS)

        assert response.status_code == 501
        body = response.json()
        assert body["code"] == "picker_unavailable"
        assert body["message"] == (
            "Esta acción solo funciona en la aplicación de escritorio (macOS o Windows)."
        )

    def test_a_dialog_that_fails_is_500(self, client: TestClient, picker: FakePicker) -> None:
        picker.error = OSError("osascript crashed")

        response = client.post(f"{URL}/choose", headers=APP_HEADERS)

        assert response.status_code == 500
        assert response.json()["code"] == "picker_failed"

    def test_a_folder_that_cannot_be_written_is_422_and_not_saved(
        self, client: TestClient, picker: FakePicker, chosen: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def denied(*args, **kwargs):
            raise PermissionError("read-only")

        monkeypatch.setattr(download_dir_module.tempfile, "TemporaryFile", denied)
        picker.result = chosen

        response = client.post(f"{URL}/choose", headers=APP_HEADERS)

        assert response.status_code == 422
        assert response.json()["code"] == "download_dir_not_writable"
        assert client.get(URL).json()["isDefault"] is True

    def test_a_second_choose_while_the_dialog_is_open_is_409(
        self, client: TestClient, picker: FakePicker, chosen: Path
    ) -> None:
        picker.hold = True
        picker.result = chosen
        first: list[int] = []
        thread = threading.Thread(
            target=lambda: first.append(
                client.post(f"{URL}/choose", headers=APP_HEADERS).status_code
            )
        )
        thread.start()
        try:
            assert picker.entered.wait(5)

            second = client.post(f"{URL}/choose", headers=APP_HEADERS)

            assert second.status_code == 409
            assert second.json()["code"] == "picker_busy"
        finally:
            picker.close.set()
            thread.join(5)
        assert first == [200]
        assert client.post(f"{URL}/choose", headers=APP_HEADERS).status_code == 200  # free again


class TestJobsUseTheFolder:
    def test_a_job_downloads_into_the_chosen_folder(
        self, client: TestClient, chosen: Path, download_dir: Path
    ) -> None:
        put(client, chosen)

        job_id = enqueue(client).json()["jobs"][0]["id"]

        job = get_job(client, job_id)
        assert job["status"] == "completed"
        assert job["outputPath"] == str(chosen / "Me at the zoo.mp4")
        assert downloads(chosen) == ["Me at the zoo.mp4"]
        assert downloads(download_dir) == []

    def test_a_playlist_goes_into_a_subfolder_of_the_chosen_folder(
        self, client: TestClient, chosen: Path, download_dir: Path
    ) -> None:
        put(client, chosen)

        enqueue_playlist(client, [entry(1), entry(2)])

        assert len(tree(chosen)) == 2
        assert all(name.startswith("Select Lectures/") for name in tree(chosen))
        assert not download_dir.exists()

    def test_changing_the_folder_does_not_move_what_is_already_queued(
        self,
        make_jobs_client: Callable[..., TestClient],
        picker: FakePicker,
        chosen: Path,
        tmp_path: Path,
        download_dir: Path,
    ) -> None:
        spawned: list[Callable[[], None]] = []
        client = make_jobs_client(pick_folder=picker, spawn_job=spawned.append)
        first = enqueue(client).json()["jobs"][0]["id"]  # queued under the default folder
        put(client, chosen)
        second = enqueue(client, "https://www.youtube.com/watch?v=Jt5fgKBqZSY").json()["jobs"][0][
            "id"
        ]

        for run in spawned:
            run()

        assert get_job(client, first)["outputPath"].startswith(str(download_dir))
        assert get_job(client, second)["outputPath"].startswith(str(chosen))
        assert len(downloads(download_dir)) == 1 and len(downloads(chosen)) == 1

    def test_changing_the_folder_does_not_split_a_queued_playlist(
        self,
        make_jobs_client: Callable[..., TestClient],
        picker: FakePicker,
        chosen: Path,
        download_dir: Path,
    ) -> None:
        spawned: list[Callable[[], None]] = []
        client = make_jobs_client(pick_folder=picker, spawn_job=spawned.append)
        enqueue_playlist(client, [entry(1), entry(2)])
        put(client, chosen)

        for run in spawned:
            run()

        assert len(tree(download_dir)) == 2
        assert tree(chosen) == []

    def test_a_retry_keeps_the_folder_of_the_job(
        self,
        client: TestClient,
        fake_engine: FakeEngine,
        chosen: Path,
        download_dir: Path,
        tmp_path: Path,
    ) -> None:
        put(client, chosen)
        fake_engine.scenario(ZOO, fail_with="ERROR: [youtube] jNQXAC9IVRw: Video unavailable")
        job_id = enqueue(client).json()["jobs"][0]["id"]
        assert get_job(client, job_id)["status"] == "failed"
        other = tmp_path / "Otra"
        other.mkdir()
        put(client, other)  # the folder changes while the job sits in the History
        fake_engine.scenarios.clear()

        client.post(f"/api/jobs/{job_id}/retry", headers=APP_HEADERS)

        job = get_job(client, job_id)
        assert job["status"] == "completed" and job["attempt"] == 2
        assert downloads(chosen) == ["Me at the zoo.mp4"]
        assert downloads(other) == []

    def test_enqueueing_is_409_when_the_chosen_folder_is_not_there(
        self, client: TestClient, chosen: Path
    ) -> None:
        put(client, chosen)
        chosen.rmdir()

        response = enqueue(client)

        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "download_dir_unavailable"
        assert body["message"] == (
            f"La carpeta {chosen} no está disponible. Conecta el disco o elige otra carpeta."
        )
        assert client.get("/api/jobs").json()["jobs"] == []
        assert not chosen.exists()  # a chosen folder is never created

    def test_a_playlist_is_409_too_and_creates_no_job(
        self, client: TestClient, chosen: Path
    ) -> None:
        put(client, chosen)
        chosen.rmdir()

        response = enqueue_playlist(client, [entry(1)])

        assert response.status_code == 409
        assert response.json()["code"] == "download_dir_unavailable"
        assert client.get("/api/jobs").json()["jobs"] == []

    def test_a_missing_default_folder_does_not_block_enqueueing(
        self, client: TestClient, download_dir: Path
    ) -> None:
        assert not download_dir.exists()

        assert enqueue(client).status_code == 200
        assert downloads(download_dir) == ["Me at the zoo.mp4"]

    def test_the_job_fails_clearly_if_the_folder_vanishes_before_the_move(
        self, client: TestClient, fake_engine: FakeEngine, chosen: Path
    ) -> None:
        put(client, chosen)
        fake_engine.on_begin = lambda url: chosen.rmdir()  # the disk is unplugged mid-download

        job_id = enqueue(client).json()["jobs"][0]["id"]

        job = get_job(client, job_id)
        assert job["status"] == "failed"
        assert job["error"] == DOWNLOAD_DIR_UNAVAILABLE
        assert job["outputPath"] is None
        assert not chosen.exists()  # not recreated

    def test_a_job_without_a_stored_folder_uses_the_default(
        self, make_jobs_client: Callable[..., TestClient], chosen: Path, download_dir: Path
    ) -> None:
        spawned: list[Callable[[], None]] = []
        client = make_jobs_client(spawn_job=spawned.append)
        job_id = enqueue(client).json()["jobs"][0]["id"]
        client.app.state.jobs._db.execute("UPDATE jobs SET download_dir = NULL")  # an old job
        put(client, chosen)

        spawned[0]()

        assert get_job(client, job_id)["outputPath"].startswith(str(download_dir))


class TestOpenDownloads:
    def test_opens_the_chosen_folder(
        self, make_jobs_client: Callable[..., TestClient], chosen: Path, download_dir: Path
    ) -> None:
        opened: list[Path] = []
        client = make_jobs_client(open_folder_in_host=opened.append)
        put(client, chosen)

        response = client.post("/api/system/open-downloads", headers=APP_HEADERS)

        assert response.status_code == 200
        assert opened == [chosen]
        assert not download_dir.exists()

    def test_a_missing_chosen_folder_is_409_and_not_created(
        self, make_jobs_client: Callable[..., TestClient], chosen: Path
    ) -> None:
        opened: list[Path] = []
        client = make_jobs_client(open_folder_in_host=opened.append)
        put(client, chosen)
        chosen.rmdir()

        response = client.post("/api/system/open-downloads", headers=APP_HEADERS)

        assert response.status_code == 409
        assert response.json()["code"] == "download_dir_unavailable"
        assert opened == [] and not chosen.exists()
