"""yt-dlp stderr -> preview error code. Strings marked (recorded) were captured from yt-dlp
2026.10.26 against YouTube; the others are the messages of its YouTube extractor."""

from __future__ import annotations

import pytest

from app.preview.failures import classify_failure

AGE = (  # (recorded)
    "ERROR: [youtube] SkRSXFQerZs: Sign in to confirm your age. This video may be "
    "inappropriate for some users. Use --cookies-from-browser or --cookies for the "
    "authentication. See  https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
    "  for how to manually pass cookies."
)


@pytest.mark.parametrize(
    "stderr, code",
    [
        (AGE, "not_public"),
        (
            "ERROR: [youtube] abcdefghijk: Private video. Sign in if you've been granted "
            "access to this video",
            "not_public",
        ),
        (
            "ERROR: [youtube] abcdefghijk: Join this channel to get access to members-only "
            "content like this video, and other exclusive perks.",
            "not_public",
        ),
        (
            "ERROR: [youtube] abcdefghijk: This video is available to this channel's members "
            "on level: Gold (or any higher level). Join this channel to get access",
            "not_public",
        ),
        ("ERROR: [youtube] abcdefghijk: Sign in to confirm your age", "not_public"),
        ("ERROR: [youtube] aaaaaaaaaaa: This video is unavailable", "unavailable"),  # (recorded)
        (
            "ERROR: [youtube] abcdefghijk: Video unavailable. This video has been removed by "
            "the uploader",
            "unavailable",
        ),
        (
            "ERROR: [youtube] abcdefghijk: Video unavailable. This video contains content from "
            "X, who has blocked it in your country on copyright grounds",
            "unavailable",
        ),
        (
            "ERROR: [youtube] abcdefghijk: The uploader has not made this video available in "
            "your country",
            "unavailable",
        ),
        (
            "ERROR: [youtube] abcdefghijk: This video has been removed for violating YouTube's "
            "Terms of Service",
            "unavailable",
        ),
        (
            "ERROR: [youtube] abcdefghijk: This live event will begin in 7 minutes.",  # (recorded)
            "live_content",
        ),
        ("ERROR: [youtube] abcdefghijk: Premieres in 2 days", "live_content"),
        (
            "ERROR: [youtube] abcdefghijk: This live stream recording is not available.",  # (rec.)
            "live_content",
        ),
        (
            "ERROR: [youtube] abcdefghijk: Sign in to confirm you're not a bot. Use "
            "--cookies-from-browser or --cookies for the authentication.",
            "preview_failed",
        ),
        ("ERROR: Unable to download webpage: HTTP Error 429: Too Many Requests", "preview_failed"),
        (
            "ERROR: [youtube] abcdefghijk: Unable to download API page: <urlopen error>",
            "preview_failed",
        ),
        ('Traceback (most recent call last):\n  File "/x/y.py", line 3', "preview_failed"),
        ("", "preview_failed"),
    ],
)
def test_code_for_stderr(stderr: str, code: str) -> None:
    assert classify_failure(stderr).code == code


def test_only_error_lines_are_inspected() -> None:
    stderr = "WARNING: Sign in to see more\nERROR: [youtube] abcdefghijk: Something odd"

    assert classify_failure(stderr).code == "preview_failed"


def test_messages_are_spanish_and_never_leak_the_raw_output() -> None:
    stderr = "ERROR: [youtube] abcdefghijk: boom at /home/nico/.cache/yt-dlp/secret.py line 3"

    failure = classify_failure(stderr)

    assert failure.message.startswith("No se pudo")
    assert "/home" not in failure.message and "boom" not in failure.message
    assert (failure.status, failure.code) == (502, "preview_failed")


def test_status_codes() -> None:
    assert classify_failure(AGE).status == 422
