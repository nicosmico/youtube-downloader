"""POST /api/preview with a FakeYtdlp at the subprocess edge. No network, no real binaries."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import EngineManager
from app.main import create_app
from tests.conftest import APP_HEADERS, HOST, PORT
from tests.fakes import FakeYtdlp, load_fixture

ZOO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
SHORT = "https://www.youtube.com/watch?v=Jt5fgKBqZSY"
UHD = "https://www.youtube.com/watch?v=2PuFyjAs7JA"
LIVE = "https://www.youtube.com/watch?v=ROboUHfPUrU"
GONE = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
LIST = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"


@pytest.fixture
def ytdlp() -> FakeYtdlp:
    fake = FakeYtdlp()
    fake.respond(ZOO, load_fixture("normal"))
    fake.respond(SHORT, load_fixture("short"))
    fake.respond(UHD, load_fixture("uhd"))
    fake.respond(LIVE, load_fixture("live"))
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


class TestVideoPreview:
    def test_returns_the_media_preview(self, api: TestClient) -> None:
        response = preview(api, ZOO)

        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "video"
        assert body["title"] == "Me at the zoo"
        assert body["author"] == "jawed"
        assert body["duration"] == 19
        assert body["url"] == ZOO
        assert body["availableQualities"] == ["best"]

    def test_qualities_follow_the_video(self, api: TestClient) -> None:
        assert preview(api, UHD).json()["availableQualities"] == [
            "best",
            "2160p",
            "1080p",
            "720p",
            "480p",
        ]
        assert preview(api, SHORT).json()["maxQuality"] == "1080p"

    def test_a_video_from_a_list_offers_the_full_playlist(
        self, api: TestClient, ytdlp: FakeYtdlp
    ) -> None:
        body = preview(api, f"{ZOO}&list={LIST}&index=2").json()

        assert body["playlistUrl"] == f"https://www.youtube.com/playlist?list={LIST}"
        assert ytdlp.calls[-1][-1] == ZOO  # the list is not given to yt-dlp

    def test_short_and_youtu_be_urls_are_normalized_before_yt_dlp(
        self, api: TestClient, ytdlp: FakeYtdlp
    ) -> None:
        preview(api, "https://youtu.be/Jt5fgKBqZSY?si=abc")
        preview(api, "https://www.youtube.com/shorts/Jt5fgKBqZSY")

        assert [c[-1] for c in ytdlp.calls] == [SHORT, SHORT]

    def test_runs_yt_dlp_with_the_engine_flags_and_a_timeout(
        self, api: TestClient, ytdlp: FakeYtdlp, engine: EngineManager
    ) -> None:
        preview(api, ZOO)

        assert ytdlp.calls == [
            [
                str(engine.binary_path("yt-dlp")),
                "--ffmpeg-location",
                str(engine.bin_dir.absolute()),
                "--js-runtimes",
                f"deno:{engine.binary_path('deno').absolute()}",
                "-J",
                "--no-warnings",
                "--no-playlist",
                ZOO,
            ]
        ]
        assert 0 < ytdlp.timeouts[0] <= 60

    def test_requires_the_app_header(self, api: TestClient) -> None:
        response = api.post("/api/preview", json={"url": ZOO})

        assert response.status_code == 403

    def test_a_body_without_url_is_a_validation_error(self, api: TestClient) -> None:
        response = api.post("/api/preview", json={}, headers=APP_HEADERS)

        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"


class TestRejectedWithoutYtDlp:
    @pytest.mark.parametrize(
        "url, code",
        [
            ("https://vimeo.com/123456", "unsupported_site"),
            ("https://www.youtube.com.evil.com/watch?v=jNQXAC9IVRw", "unsupported_site"),
            (f"https://www.youtube.com/playlist?list=RD{LIST[:9]}", "mix_playlist"),
            (f"https://www.youtube.com/watch?list=RD{LIST[:9]}", "mix_playlist"),
            ("hola mundo", "invalid_url"),
            ("", "invalid_url"),
            ("https://www.youtube.com/watch?v=corto", "invalid_url"),
        ],
    )
    def test_error_codes(self, api: TestClient, ytdlp: FakeYtdlp, url: str, code: str) -> None:
        response = preview(api, url)

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == code
        assert body["message"]
        assert ytdlp.calls == []

    def test_playlists_are_temporarily_unsupported(self, api: TestClient, ytdlp: FakeYtdlp) -> None:
        for url in (f"https://www.youtube.com/playlist?list={LIST}", "https://youtube.com/@mkbhd"):
            response = preview(api, url)

            assert response.status_code == 422
            assert response.json()["code"] == "playlist_unsupported"
        assert ytdlp.calls == []

    def test_a_mix_inside_a_video_url_is_still_a_video(self, api: TestClient) -> None:
        body = preview(api, f"{ZOO}&list=RDjNQXAC9IVRw&start_radio=1").json()

        assert body["title"] == "Me at the zoo"
        assert "playlistUrl" not in body


class TestYtDlpFailures:
    def test_live_streams_are_rejected(self, api: TestClient) -> None:
        response = preview(api, LIVE)

        assert response.status_code == 422
        assert response.json()["code"] == "live_content"

    @pytest.mark.parametrize(
        "stderr, code, status",
        [
            (
                "ERROR: [youtube] aaaaaaaaaaa: This live event will begin in 7 minutes.",
                "live_content",
                422,
            ),
            ("ERROR: [youtube] aaaaaaaaaaa: Sign in to confirm your age.", "not_public", 422),
            (
                "ERROR: [youtube] aaaaaaaaaaa: Private video. Sign in if you've been granted",
                "not_public",
                422,
            ),
            ("ERROR: [youtube] aaaaaaaaaaa: This video is unavailable", "unavailable", 422),
            ("ERROR: something we never saw before", "preview_failed", 502),
        ],
    )
    def test_stderr_is_mapped_to_a_code(
        self, api: TestClient, ytdlp: FakeYtdlp, stderr: str, code: str, status: int
    ) -> None:
        ytdlp.fail(GONE, stderr)

        response = preview(api, GONE)

        assert response.status_code == status
        body = response.json()
        assert body["code"] == code
        assert "ERROR" not in body["message"] and "aaaaaaaaaaa" not in body["message"]

    def test_invalid_json_is_a_generic_failure(self, api: TestClient, ytdlp: FakeYtdlp) -> None:
        ytdlp._answers[GONE] = "not json"

        response = preview(api, GONE)

        assert (response.status_code, response.json()["code"]) == (502, "preview_failed")


class TestEngineNotReady:
    def test_answers_engine_not_ready_without_running_yt_dlp(
        self,
        engine: EngineManager,
        ytdlp: FakeYtdlp,
        data_dir: Path,
        download_dir: Path,
        static_dir: Path,
    ) -> None:
        app = create_app(
            data_dir=data_dir,
            port=PORT,
            static_dir=static_dir,
            engine=engine,
            ytdlp_runner=ytdlp,
            download_dir=download_dir,
        )
        client = TestClient(app, base_url=f"http://{HOST}")

        response = preview(client, ZOO)

        assert response.status_code == 409
        assert response.json()["code"] == "engine_not_ready"
        assert ytdlp.calls == []


class TestHangingYtDlp:
    def test_a_timeout_is_reported_and_the_api_keeps_answering(
        self, api: TestClient, ytdlp: FakeYtdlp
    ) -> None:
        ytdlp.hang(GONE)
        result: dict = {}

        def slow_preview() -> None:
            result["response"] = preview(api, GONE)

        worker = threading.Thread(target=slow_preview)
        worker.start()
        try:
            assert ytdlp.started.wait(5)
            # the preview is stuck inside yt-dlp: the rest of the API must not notice
            health = api.get("/api/health")
            other = preview(api, ZOO)
            assert health.status_code == 200
            assert other.status_code == 200
        finally:
            ytdlp.release()
            worker.join(10)

        assert not worker.is_alive()
        response = result["response"]
        assert response.status_code == 504
        assert response.json()["code"] == "timeout"
        assert response.json()["message"]


class TestNoSideEffects:
    def test_a_preview_creates_no_files(self, api: TestClient, data_dir: Path) -> None:
        def snapshot() -> set[Path]:
            return {p.relative_to(data_dir) for p in data_dir.rglob("*")}

        before = snapshot()
        for url in (ZOO, SHORT, LIVE, GONE, "https://vimeo.com/1"):
            preview(api, url)

        assert snapshot() == before
        assert not any(name == "staging" for p in before for name in p.parts)

    def test_never_asks_yt_dlp_to_download(self, api: TestClient, ytdlp: FakeYtdlp) -> None:
        preview(api, ZOO)

        args = ytdlp.calls[0]
        assert "-J" in args
        assert not {"-o", "-P", "--print", "-x", "-f", "-S"} & set(args)
