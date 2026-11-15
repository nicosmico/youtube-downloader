"""Playlist and channel previews, from real `yt-dlp --flat-playlist` outputs and synthetic ones."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import EngineManager
from app.main import create_app
from app.preview.mapping import PreviewFailure
from app.preview.playlists import MAX_ENTRIES, to_playlist_preview
from app.preview.urls import ClassifiedUrl, UrlKind
from tests.conftest import APP_HEADERS, HOST, PORT
from tests.fakes import FakeYtdlp, load_fixture

LIST = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
PLAYLIST = f"https://www.youtube.com/playlist?list={LIST}"
UNAVAILABLE = "https://www.youtube.com/playlist?list=PL59FEE129ADFF2B12"
FIRESHIP = "https://www.youtube.com/@Fireship"
FIRESHIP_VIDEOS = f"{FIRESHIP}/videos"
JAWED = "https://www.youtube.com/@jawed"
JAWED_VIDEOS = f"{JAWED}/videos"


def classified(url: str = PLAYLIST) -> ClassifiedUrl:
    return ClassifiedUrl(UrlKind.PLAYLIST, url)


def synthetic(count: int, **extra) -> dict:
    return {
        "_type": "playlist",
        "id": "PLbig",
        "title": "Big",
        "playlist_count": count,
        "entries": [
            {"id": f"{i:011d}", "title": f"Video {i}", "duration": 10, "_type": "url"}
            for i in range(1, min(count, MAX_ENTRIES) + 1)
        ],
        **extra,
    }


class TestMapping:
    def test_a_normal_playlist(self) -> None:
        preview = to_playlist_preview(load_fixture("playlist"), classified())

        assert preview["kind"] == "playlist"
        assert preview["title"] == "Select Lectures"
        assert preview["author"] == "Lex Fridman"
        assert preview["thumbnail"].startswith("https://i.ytimg.com/")
        assert preview["entryCount"] == 2
        assert preview["truncated"] is False
        first = preview["entries"][0]
        assert first == {
            "id": "0VH1Lim8gL8",
            "url": "https://www.youtube.com/watch?v=0VH1Lim8gL8",
            "index": 1,
            "title": "Deep Learning State of the Art (2020)",
            "duration": 5261,
            "available": True,
        }
        assert [e["index"] for e in preview["entries"]] == [1, 2]

    def test_private_or_deleted_entries_are_unavailable_with_a_reason(self) -> None:
        preview = to_playlist_preview(load_fixture("playlist_unavailable"), classified())

        entries = preview["entries"]
        assert preview["entryCount"] == 11
        gone = [e for e in entries if not e["available"]]
        assert [e["index"] for e in gone] == [4, 8, 10]  # positions in the playlist
        assert all(e["unavailableReason"] == "Video privado o eliminado" for e in gone)
        assert all(e["title"] == "Video no disponible" for e in gone)
        assert all("unavailableReason" not in e for e in entries if e["available"])

    @pytest.mark.parametrize(
        ("raw", "reason"),
        [
            ({"title": "[Private video]"}, "Video privado"),
            ({"title": "[Deleted video]"}, "Video eliminado"),
            ({"title": "Members", "availability": "subscriber_only"}, "Solo para miembros"),
            ({"title": "Login", "availability": "needs_auth"}, "Requiere iniciar sesión"),
            ({"title": "Soon", "live_status": "is_upcoming"}, "Directo o estreno pendiente"),
            ({"title": "On air", "live_status": "is_live"}, "Directo o estreno pendiente"),
        ],
    )
    def test_reasons(self, raw: dict, reason: str) -> None:
        data = synthetic(1)
        data["entries"][0].update(raw)

        (entry,) = to_playlist_preview(data, classified())["entries"]

        assert entry["available"] is False
        assert entry["unavailableReason"].startswith(reason)
        assert entry["title"] in (raw["title"], "Video no disponible")
        assert not entry["title"].startswith("[")

    def test_an_entry_without_a_valid_id_is_unavailable_and_has_no_url(self) -> None:
        data = synthetic(1)
        data["entries"][0]["id"] = "x"

        (entry,) = to_playlist_preview(data, classified())["entries"]

        assert entry["available"] is False
        assert entry["url"] == ""

    def test_more_than_500_is_truncated(self) -> None:
        preview = to_playlist_preview(synthetic(730), classified())

        assert preview["entryCount"] == MAX_ENTRIES
        assert preview["truncated"] is True
        assert preview["entries"][-1]["index"] == MAX_ENTRIES

    def test_exactly_500_is_not_truncated(self) -> None:
        preview = to_playlist_preview(synthetic(500), classified())

        assert (preview["entryCount"], preview["truncated"]) == (500, False)

    def test_without_a_count_a_full_page_is_assumed_truncated(self) -> None:
        data = synthetic(500)
        del data["playlist_count"]

        assert to_playlist_preview(data, classified())["truncated"] is True

    def test_an_empty_playlist_is_refused(self) -> None:
        data = synthetic(0)

        with pytest.raises(PreviewFailure) as exc:
            to_playlist_preview(data, classified())

        assert exc.value.failure.code == "unavailable"

    def test_a_missing_title_falls_back(self) -> None:
        data = synthetic(1)
        del data["title"]

        assert to_playlist_preview(data, classified())["title"] == "Playlist"

    def test_nested_playlists_are_not_videos(self) -> None:
        with pytest.raises(PreviewFailure) as exc:
            to_playlist_preview(load_fixture("channel_tabs"), classified(FIRESHIP))

        assert exc.value.failure.code == "preview_failed"

    def test_a_video_json_is_not_a_playlist(self) -> None:
        with pytest.raises(PreviewFailure):
            to_playlist_preview(load_fixture("normal"), classified())

    def test_channel_videos_tab(self) -> None:
        preview = to_playlist_preview(load_fixture("channel_videos"), classified(FIRESHIP_VIDEOS))

        assert preview["title"] == "Fireship - Videos"
        assert preview["author"] == "Fireship"
        assert preview["entryCount"] == 3
        assert all(e["available"] for e in preview["entries"])


@pytest.fixture
def ytdlp() -> FakeYtdlp:
    fake = FakeYtdlp()
    fake.respond(PLAYLIST, load_fixture("playlist"))
    fake.respond(UNAVAILABLE, load_fixture("playlist_unavailable"))
    fake.respond(FIRESHIP_VIDEOS, load_fixture("channel_videos"))
    fake.respond(JAWED_VIDEOS, load_fixture("channel_single"))
    return fake


@pytest.fixture
def api(
    engine: EngineManager, ytdlp: FakeYtdlp, data_dir: Path, download_dir: Path, static_dir: Path
) -> TestClient:
    engine.install()
    app = create_app(
        data_dir=data_dir,
        port=PORT,
        static_dir=static_dir,
        engine=engine,
        ytdlp_runner=ytdlp,
        download_dir=download_dir,
    )
    return TestClient(app, base_url=f"http://{HOST}")


def preview(client: TestClient, url: str):
    return client.post("/api/preview", json={"url": url}, headers=APP_HEADERS)


class TestPreviewApi:
    def test_lists_the_entries_without_downloading(
        self, api: TestClient, ytdlp: FakeYtdlp, engine: EngineManager, download_dir: Path
    ) -> None:
        response = preview(api, PLAYLIST)

        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "playlist" and body["entryCount"] == 2
        assert body["url"] == PLAYLIST
        assert "availableQualities" not in body
        assert ytdlp.calls == [
            [
                str(engine.binary_path("yt-dlp")),
                "--ffmpeg-location",
                str(engine.bin_dir.absolute()),
                "--js-runtimes",
                f"deno:{engine.binary_path('deno').absolute()}",
                "-J",
                "--flat-playlist",
                "--playlist-end",
                "500",
                "--no-warnings",
                PLAYLIST,
            ]
        ]
        assert not download_dir.exists()

    def test_unavailable_entries_come_with_their_reason(self, api: TestClient) -> None:
        entries = preview(api, UNAVAILABLE).json()["entries"]

        assert sum(not e["available"] for e in entries) == 3
        assert all(e["unavailableReason"] for e in entries if not e["available"])

    def test_a_bare_channel_url_asks_for_the_videos_tab(
        self, api: TestClient, ytdlp: FakeYtdlp
    ) -> None:
        body = preview(api, FIRESHIP).json()

        assert ytdlp.calls[-1][-1] == FIRESHIP_VIDEOS
        assert body["url"] == FIRESHIP_VIDEOS
        assert body["title"] == "Fireship - Videos"

    def test_a_channel_that_yt_dlp_resolves_by_itself(self, api: TestClient) -> None:
        body = preview(api, JAWED).json()

        assert body["entryCount"] == 1
        assert body["entries"][0]["title"] == "Me at the zoo"

    def test_a_channel_tab_url_is_kept(self, api: TestClient, ytdlp: FakeYtdlp) -> None:
        ytdlp.respond(f"{FIRESHIP}/shorts", load_fixture("channel_videos"))

        assert preview(api, f"{FIRESHIP}/shorts").status_code == 200
        assert ytdlp.calls[-1][-1] == f"{FIRESHIP}/shorts"

    def test_the_channel_root_with_tabs_is_never_shown_as_videos(
        self, api: TestClient, ytdlp: FakeYtdlp
    ) -> None:
        ytdlp.respond(FIRESHIP_VIDEOS, load_fixture("channel_tabs"))

        response = preview(api, FIRESHIP)

        assert response.status_code == 502
        assert response.json()["code"] == "preview_failed"

    def test_the_playlist_gets_a_longer_timeout_than_a_video(
        self, api: TestClient, ytdlp: FakeYtdlp
    ) -> None:
        preview(api, PLAYLIST)

        assert ytdlp.timeouts[-1] > 30

    def test_a_private_playlist_is_mapped_like_a_video_failure(
        self, api: TestClient, ytdlp: FakeYtdlp
    ) -> None:
        ytdlp.fail(PLAYLIST, "ERROR: [youtube:tab] x: The playlist does not exist.")

        response = preview(api, PLAYLIST)

        assert response.status_code == 422
        assert response.json()["code"] == "unavailable"

    def test_a_mix_is_still_rejected_without_yt_dlp(
        self, api: TestClient, ytdlp: FakeYtdlp
    ) -> None:
        response = preview(api, "https://www.youtube.com/playlist?list=RDabcdef")

        assert response.json()["code"] == "mix_playlist"
        assert ytdlp.calls == []
