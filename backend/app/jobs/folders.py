"""Names inside the Destination: the folder of a Batch and the numbered files in it."""

from __future__ import annotations

import re
import unicodedata

FALLBACK_FOLDER = "Playlist"
MAX_FOLDER_CHARS = 100
MAX_FOLDER_BYTES = 200  # macOS allows 255 bytes per name; leave room for ` (2)`-style suffixes
MIN_PADDING = 2

_FORBIDDEN = re.compile(r'[<>:"/\\|?*]')
_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in "0123456789¹²³"}
    | {f"LPT{n}" for n in "0123456789¹²³"}
)


def sanitize_folder_name(title: str) -> str:
    """A folder name that is valid on macOS and Windows.

    Removes `<>:"/\\|?*` and control characters, collapses whitespace, strips leading dots (a
    hidden folder on macOS) and trailing dots and spaces (Windows drops them), caps the length,
    avoids the Windows reserved device names and falls back to "Playlist".
    """
    text = unicodedata.normalize("NFC", title)
    text = re.sub(r"[\t\r\n]", " ", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cc")
    text = _FORBIDDEN.sub("", text)
    text = re.sub(r"\s+", " ", text)
    text = _tidy(text)[:MAX_FOLDER_CHARS]
    while len(text.encode("utf-8")) > MAX_FOLDER_BYTES:
        text = text[:-1]
    text = _tidy(text)
    if not text:
        return FALLBACK_FOLDER
    # `CON`, `CON.txt` and `con .x` are all the device on Windows.
    if text.split(".")[0].strip().upper() in _RESERVED:
        text += "_"
    return text


def _tidy(text: str) -> str:
    return text.lstrip(". ").rstrip(". ")


def padding_width(highest_index: int) -> int:
    """Digits of the `NN` prefix: at least two, more when the playlist has 100+ entries."""
    return max(MIN_PADDING, len(str(highest_index)))


def numbered_name(index: int, name: str, width: int) -> str:
    """`<NN> - <name>`: the playlist position keeps the original order when sorted by name."""
    return f"{index:0{width}d} - {name}"
