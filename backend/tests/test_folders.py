"""Folder names of a Batch and the numbering of its files."""

from __future__ import annotations

import pytest

from app.jobs.folders import (
    FALLBACK_FOLDER,
    MAX_FOLDER_BYTES,
    MAX_FOLDER_CHARS,
    numbered_name,
    padding_width,
    sanitize_folder_name,
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Select Lectures", "Select Lectures"),
        (
            'AC/DC: "Back in Black" <live> | what?*',
            "ACDC Back in Black live what",
        ),
        ("back\\slash", "backslash"),
        ("tab\tand\nnewline\x00nul", "tab and newlinenul"),
        ("Fin del mundo...", "Fin del mundo"),
        ("trailing spaces   ", "trailing spaces"),
        ("  . . leading", "leading"),
        (".hidden", "hidden"),
        ("Canción ñandú 日本語 🎵", "Canción ñandú 日本語 🎵"),
        ("Café", "Café"),  # NFC
        ("many     spaces", "many spaces"),
        ("", FALLBACK_FOLDER),
        ("   ", FALLBACK_FOLDER),
        ("...", FALLBACK_FOLDER),
        ('<>:"/\\|?*', FALLBACK_FOLDER),
        ("..", FALLBACK_FOLDER),
    ],
)
def test_sanitizes_for_macos_and_windows(title: str, expected: str) -> None:
    assert sanitize_folder_name(title) == expected


@pytest.mark.parametrize(
    "title",
    ["CON", "con", "PRN", "Aux", "NUL", "COM1", "com9", "LPT1", "lpt3", "CON.txt", "nul.", "COM¹"],
)
def test_windows_reserved_names_are_changed(title: str) -> None:
    result = sanitize_folder_name(title)

    assert result != title
    assert result.startswith(title.rstrip(".")) and result.endswith("_")


@pytest.mark.parametrize("title", ["CONSOLE", "COM10", "Aux Cord", "PRNT", "LPT"])
def test_names_that_only_look_reserved_are_kept(title: str) -> None:
    assert sanitize_folder_name(title) == title


def test_the_length_is_capped_in_characters_and_bytes() -> None:
    assert len(sanitize_folder_name("a" * 500)) == MAX_FOLDER_CHARS
    long_unicode = sanitize_folder_name("日" * 500)
    assert len(long_unicode.encode()) <= MAX_FOLDER_BYTES


def test_cutting_never_leaves_a_trailing_dot_or_space() -> None:
    title = "a" * (MAX_FOLDER_CHARS - 1) + ". tail"

    assert sanitize_folder_name(title) == "a" * (MAX_FOLDER_CHARS - 1)


@pytest.mark.parametrize(
    ("highest", "width"), [(1, 2), (9, 2), (10, 2), (99, 2), (100, 3), (500, 3), (1000, 4)]
)
def test_padding_has_at_least_two_digits(highest: int, width: int) -> None:
    assert padding_width(highest) == width


def test_numbered_names_sort_in_playlist_order() -> None:
    names = [numbered_name(i, f"v{i}.m4a", 3) for i in (100, 2, 10)]

    assert sorted(names) == ["002 - v2.m4a", "010 - v10.m4a", "100 - v100.m4a"]
