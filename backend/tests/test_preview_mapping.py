"""MediaPreview mapping, from real `yt-dlp -J` outputs recorded with network (trimmed)."""

from __future__ import annotations

import pytest

from app.preview.mapping import (
    PreviewFailure,
    available_qualities,
    max_resolution,
    to_media_preview,
)
from app.preview.urls import ClassifiedUrl, UrlKind
from tests.fakes import load_fixture


def classified(video_id: str, playlist_url: str | None = None) -> ClassifiedUrl:
    return ClassifiedUrl(UrlKind.VIDEO, f"https://www.youtube.com/watch?v={video_id}", playlist_url)


class TestRecordedVideos:
    def test_a_regular_video(self) -> None:
        preview = to_media_preview(load_fixture("normal"), classified("jNQXAC9IVRw")).to_dict()

        assert preview["kind"] == "video"
        assert preview["id"] == "jNQXAC9IVRw"
        assert preview["url"] == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        assert preview["title"] == "Me at the zoo"
        assert preview["author"] == "jawed"
        assert preview["duration"] == 19
        assert preview["thumbnail"].startswith("https://i.ytimg.com/vi/jNQXAC9IVRw/")
        # the best format of this video is 240p: below every cap, only `best` makes sense
        assert preview["maxResolution"] == 240
        assert preview["availableQualities"] == ["best"]
        assert preview["maxQuality"] == "best"
        assert "playlistUrl" not in preview

    def test_a_vertical_short_measures_the_short_side(self) -> None:
        data = load_fixture("short")
        tallest = max(f["height"] for f in data["formats"] if f.get("vcodec") != "none")
        assert tallest == 1920  # the long side would suggest 2160p

        preview = to_media_preview(data, classified("Jt5fgKBqZSY")).to_dict()

        assert preview["maxResolution"] == 1080
        assert preview["availableQualities"] == ["best", "1080p", "720p", "480p"]
        assert preview["maxQuality"] == "1080p"

    def test_a_4k_video_offers_every_quality(self) -> None:
        preview = to_media_preview(load_fixture("uhd"), classified("2PuFyjAs7JA")).to_dict()

        assert preview["maxResolution"] == 2160
        assert preview["availableQualities"] == ["best", "2160p", "1080p", "720p", "480p"]
        assert preview["maxQuality"] == "2160p"
        assert preview["duration"] == 11

    def test_the_playlist_url_is_passed_through(self) -> None:
        url = "https://www.youtube.com/playlist?list=PLabc"

        preview = to_media_preview(load_fixture("normal"), classified("jNQXAC9IVRw", url))

        assert preview.to_dict()["playlistUrl"] == url

    def test_a_live_stream_is_rejected(self) -> None:
        data = load_fixture("live")
        assert data["live_status"] == "is_live"

        with pytest.raises(PreviewFailure) as err:
            to_media_preview(data, classified("ROboUHfPUrU"))

        assert err.value.failure.code == "live_content"


class TestLiveStatus:
    @pytest.mark.parametrize("status", [None, "not_live", "was_live"])
    def test_finished_videos_are_accepted(self, status: str | None) -> None:
        data = load_fixture("normal")
        data["live_status"] = status

        assert to_media_preview(data, classified("jNQXAC9IVRw")).id == "jNQXAC9IVRw"

    @pytest.mark.parametrize("status", ["is_live", "is_upcoming", "post_live", "surprise"])
    def test_everything_else_is_live_content(self, status: str) -> None:
        data = load_fixture("normal")
        data["live_status"] = status

        with pytest.raises(PreviewFailure) as err:
            to_media_preview(data, classified("jNQXAC9IVRw"))

        assert err.value.failure.code == "live_content"


class TestMalformedOutput:
    @pytest.mark.parametrize("missing", ["id", "title"])
    def test_a_video_without_id_or_title_is_a_generic_failure(self, missing: str) -> None:
        data = load_fixture("normal")
        del data[missing]

        with pytest.raises(PreviewFailure) as err:
            to_media_preview(data, classified("jNQXAC9IVRw"))

        assert err.value.failure.code == "preview_failed"

    def test_a_playlist_result_is_not_a_video(self) -> None:
        data = {**load_fixture("normal"), "_type": "playlist"}

        with pytest.raises(PreviewFailure):
            to_media_preview(data, classified("jNQXAC9IVRw"))

    def test_optional_fields_may_be_missing(self) -> None:
        preview = to_media_preview({"id": "abc", "title": "t"}, classified("jNQXAC9IVRw"))

        assert (preview.thumbnail, preview.duration, preview.author) == (None, None, None)
        assert preview.available_qualities == ["best"]

    def test_the_thumbnail_falls_back_to_the_last_of_the_list(self) -> None:
        data = {"id": "a", "title": "t", "thumbnails": [{"url": "u1"}, {"url": "u2"}]}

        assert to_media_preview(data, classified("jNQXAC9IVRw")).thumbnail == "u2"

    def test_the_author_falls_back_to_the_uploader(self) -> None:
        data = {"id": "a", "title": "t", "uploader": "Someone"}

        assert to_media_preview(data, classified("jNQXAC9IVRw")).author == "Someone"


def video_format(width: int, height: int, vcodec: str = "avc1.640028") -> dict:
    return {"vcodec": vcodec, "width": width, "height": height}


class TestAvailableQualities:
    """`best` always, plus every cap <= the video's maximum short side."""

    @pytest.mark.parametrize(
        "side, expected",
        [
            (None, ["best"]),
            (144, ["best"]),
            (360, ["best"]),
            (479, ["best"]),
            (480, ["best", "480p"]),
            (600, ["best", "480p"]),
            (719, ["best", "480p"]),
            (720, ["best", "720p", "480p"]),
            (1079, ["best", "720p", "480p"]),
            (1080, ["best", "1080p", "720p", "480p"]),
            (1440, ["best", "1080p", "720p", "480p"]),
            (2159, ["best", "1080p", "720p", "480p"]),
            (2160, ["best", "2160p", "1080p", "720p", "480p"]),
            (4320, ["best", "2160p", "1080p", "720p", "480p"]),
        ],
    )
    def test_rule(self, side: int | None, expected: list[str]) -> None:
        assert available_qualities(side) == expected


class TestMaxResolution:
    def test_uses_the_short_side_of_the_best_video_format(self) -> None:
        formats = [video_format(1920, 1080), video_format(1080, 1920), video_format(1280, 720)]

        assert max_resolution(formats) == 1080

    def test_ignores_audio_only_formats_and_storyboards(self) -> None:
        formats = [
            {"vcodec": "none", "acodec": "mp4a", "width": None, "height": None},
            {"vcodec": "none", "acodec": "none", "width": 320, "height": 180, "ext": "mhtml"},
            video_format(640, 360),
        ]

        assert max_resolution(formats) == 360

    def test_without_video_formats_there_is_no_maximum(self) -> None:
        assert max_resolution([]) is None
        assert max_resolution([{"vcodec": "none", "width": None, "height": None}]) is None
        assert max_resolution([{"vcodec": "avc1", "width": None, "height": None}]) is None
