from __future__ import annotations

import pytest

from app.preview.urls import ClassifiedUrl, UrlKind, UrlRejected, classify_url, require_video_url

VID = "dQw4w9WgXcQ"
WATCH = f"https://www.youtube.com/watch?v={VID}"
LIST = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
PLAYLIST = f"https://www.youtube.com/playlist?list={LIST}"


def video(url: str = WATCH, playlist_url: str | None = None) -> ClassifiedUrl:
    return ClassifiedUrl(UrlKind.VIDEO, url, playlist_url)


def playlist(url: str) -> ClassifiedUrl:
    return ClassifiedUrl(UrlKind.PLAYLIST, url)


@pytest.mark.parametrize(
    "raw",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}",
        f"http://www.youtube.com/watch?v={VID}",
        f"https://WWW.YouTube.COM/watch?v={VID}",
        f"https://www.youtube.com/watch?v={VID}&t=42s&feature=share",
        f"https://www.youtube.com/watch?feature=share&v={VID}",
        f"https://www.youtube.com./watch?v={VID}",
        f"www.youtube.com/watch?v={VID}",
        f"youtube.com/watch?v={VID}",
        f"  https://www.youtube.com/watch?v={VID}\n",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?si=abcdef&t=10",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/shorts/{VID}?feature=share",
        f"https://m.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/live/{VID}",
        f"https://www.youtube.com/live/{VID}?si=x",
        f"https://www.youtube.com/embed/{VID}",
        f"https://youtube.com/watch/?v={VID}",
    ],
)
def test_video_urls_are_normalized(raw: str) -> None:
    assert classify_url(raw) == video()


class TestVideoWithList:
    def test_watch_with_a_regular_list_offers_the_full_playlist(self) -> None:
        result = classify_url(f"{WATCH}&list={LIST}&index=3")

        assert result == video(playlist_url=PLAYLIST)

    def test_youtu_be_and_shorts_keep_their_list_too(self) -> None:
        assert classify_url(f"https://youtu.be/{VID}?list={LIST}") == video(playlist_url=PLAYLIST)
        assert classify_url(f"https://www.youtube.com/live/{VID}?list={LIST}").playlist_url == (
            PLAYLIST
        )

    @pytest.mark.parametrize("mix", ["RDdQw4w9WgXcQ", "RDMM", "RDCLAK5uy_abc", "RDEMabcdef"])
    def test_a_mix_list_does_not_make_a_playlist_url(self, mix: str) -> None:
        assert classify_url(f"{WATCH}&list={mix}&start_radio=1") == video()

    @pytest.mark.parametrize("private", ["WL", "LL"])
    def test_private_auto_lists_do_not_make_a_playlist_url(self, private: str) -> None:
        assert classify_url(f"{WATCH}&list={private}") == video()

    def test_a_malformed_list_is_ignored_for_videos(self) -> None:
        assert classify_url(f"{WATCH}&list=%00%00") == video()
        assert classify_url(f"{WATCH}&list=") == video()


class TestPlaylists:
    def test_playlist_url(self) -> None:
        assert classify_url(f"https://www.youtube.com/playlist?list={LIST}") == playlist(PLAYLIST)
        assert classify_url(f"https://music.youtube.com/playlist?list={LIST}&si=x") == playlist(
            PLAYLIST
        )

    def test_watch_with_only_a_list_is_a_playlist(self) -> None:
        assert classify_url(f"https://www.youtube.com/watch?list={LIST}") == playlist(PLAYLIST)

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("https://www.youtube.com/@mkbhd", "https://www.youtube.com/@mkbhd/videos"),
            ("https://www.youtube.com/@mkbhd/videos", "https://www.youtube.com/@mkbhd/videos"),
            ("https://m.youtube.com/@mkbhd/shorts", "https://www.youtube.com/@mkbhd/shorts"),
            (
                "https://www.youtube.com/@mkbhd/streams?x=1",
                "https://www.youtube.com/@mkbhd/streams",
            ),
            ("https://www.youtube.com/@mkbhd/", "https://www.youtube.com/@mkbhd/videos"),
            ("https://www.youtube.com/@mkbhd/featured", "https://www.youtube.com/@mkbhd/videos"),
            ("https://www.youtube.com/@mkbhd/playlists", "https://www.youtube.com/@mkbhd/videos"),
            (
                "https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ",
                "https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ/videos",
            ),
            ("https://www.youtube.com/c/Marques", "https://www.youtube.com/c/Marques/videos"),
            (
                "https://www.youtube.com/user/marquesbrownlee",
                "https://www.youtube.com/user/marquesbrownlee/videos",
            ),
            ("https://www.youtube.com/@%E3%83%86%E3%82%B9%E3%83%88", None),
            ("https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ", None),
            ("https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ/videos", None),
            ("https://www.youtube.com/c/Marques", None),
            ("https://www.youtube.com/c/Marques/playlists", None),
            ("https://www.youtube.com/user/marquesbrownlee", None),
            ("https://www.youtube.com/user/marquesbrownlee/videos", None),
            ("https://music.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ", None),
            ("youtube.com/@mkbhd", "https://www.youtube.com/@mkbhd/videos"),
        ],
    )
    def test_channels_and_their_tabs(self, raw: str, expected: str | None) -> None:
        result = classify_url(raw)

        assert result.kind is UrlKind.PLAYLIST
        assert result.playlist_url is None
        if expected:
            assert result.url == expected
        else:
            assert result.url.startswith("https://www.youtube.com/")
            assert "?" not in result.url


class TestRejections:
    @pytest.mark.parametrize(
        "raw",
        [
            "https://www.youtube.com/playlist?list=RDdQw4w9WgXcQ",
            "https://www.youtube.com/playlist?list=RDMM",
            "https://www.youtube.com/watch?list=RDdQw4w9WgXcQ",
            "https://music.youtube.com/playlist?list=RDCLAK5uy_abc",
        ],
    )
    def test_mix_playlists(self, raw: str) -> None:
        with pytest.raises(UrlRejected) as err:
            classify_url(raw)

        assert err.value.code == "mix_playlist"

    @pytest.mark.parametrize(
        "raw",
        [
            "https://vimeo.com/12345",
            "https://example.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com.evil.com/watch?v=dQw4w9WgXcQ",
            "https://evilyoutube.com/watch?v=dQw4w9WgXcQ",
            "https://notyoutu.be/dQw4w9WgXcQ",
            "https://youtube.com.attacker.io/@x",
            "https://studio.youtube.com/video/dQw4w9WgXcQ",
            "https://gaming.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube-nocookie.com/embed/dQw4w9WgXcQ",
            "https://soundcloud.com/a/b",
            "https://twitter.com",
            "example.com",
        ],
    )
    def test_other_sites(self, raw: str) -> None:
        with pytest.raises(UrlRejected) as err:
            classify_url(raw)

        assert err.value.code == "unsupported_site"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "hola",
            "hola mundo",
            "not a url at all",
            "https://",
            "https:///watch?v=dQw4w9WgXcQ",
            "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "https://user:pass@www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com:8080/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com:abc/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com",
            "https://www.youtube.com/",
            "https://www.youtube.com/watch",
            "https://www.youtube.com/watch?v=",
            "https://www.youtube.com/watch?v=short",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQextra",
            "https://www.youtube.com/watch?v=dQw4w9WgX;Q",
            "https://youtu.be/",
            "https://youtu.be/short",
            "https://www.youtube.com/shorts/",
            "https://www.youtube.com/shorts/abc",
            "https://www.youtube.com/live",
            "https://www.youtube.com/embed/",
            "https://www.youtube.com/playlist",
            "https://www.youtube.com/playlist?list=",
            "https://www.youtube.com/results?search_query=cats",
            "https://www.youtube.com/feed/subscriptions",
            "https://www.youtube.com/@",
            "https://www.youtube.com/channel",
            "https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ/videos/extra",
            "https://www.youtube.com/@mkbhd/videos/extra",
            "https://www.youtube.com/" + "a" * 3000,
        ],
    )
    def test_garbage_is_an_invalid_url(self, raw: str) -> None:
        with pytest.raises(UrlRejected) as err:
            classify_url(raw)

        assert err.value.code == "invalid_url"

    def test_none_is_invalid(self) -> None:
        with pytest.raises(UrlRejected):
            classify_url(None)  # type: ignore[arg-type]


class TestRequireVideoUrl:
    def test_returns_the_normalized_video_url(self) -> None:
        assert require_video_url(f"https://youtu.be/{VID}?si=x") == WATCH

    @pytest.mark.parametrize(
        "raw", [PLAYLIST, "https://www.youtube.com/@mkbhd", "https://vimeo.com/1", "nope"]
    )
    def test_anything_else_is_rejected(self, raw: str) -> None:
        with pytest.raises(UrlRejected):
            require_video_url(raw)
