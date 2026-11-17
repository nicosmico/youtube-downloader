"""Where each Engine binary comes from, per platform (ADR-0002, spike 01).

ffmpeg, ffprobe and Deno are pinned to a version and a SHA-256 of the zip archive that is
downloaded; the hashes come from each provider's published hash file and were cross-checked
against the GitHub API `digest` where available. yt-dlp is dynamic: its hash comes from the
`SHA2-256SUMS` of the release being installed.
"""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

DENO_VERSION = "2.9.8"
FFMPEG_VERSION = "9.0.2"

BINARIES = ("yt-dlp", "ffmpeg", "ffprobe", "deno")

# The public page redirects to `.../releases/tag/<tag>`: unlike api.github.com it has no
# unauthenticated rate limit of 60 requests per hour per IP.
YTDLP_LATEST_PAGE = "https://github.com/yt-dlp/yt-dlp/releases/latest"
YTDLP_RELEASES_TAG = "https://github.com/yt-dlp/yt-dlp/releases/tag"
_YTDLP_DOWNLOAD = "https://github.com/yt-dlp/yt-dlp/releases/download"
_DENO_DOWNLOAD = f"https://github.com/denoland/deno/releases/download/v{DENO_VERSION}"
_MARTIN_RIEDL = "https://ffmpeg.martin-riedl.de/download"
_GYAN = f"https://github.com/GyanD/codexffmpeg/releases/download/{FFMPEG_VERSION}"

# Platform identifiers: macos-arm64, windows-x64, linux-arm64, linux-x64.
TARGETS = ("macos-arm64", "windows-x64", "linux-arm64", "linux-x64")


@dataclass(frozen=True)
class Extract:
    """One executable to pull out of a zip. `member` matches the end of the path in the zip."""

    binary: str
    member: str


@dataclass(frozen=True)
class Archive:
    """A pinned zip archive and the executables it provides."""

    url: str
    sha256: str
    extracts: tuple[Extract, ...]

    @property
    def label(self) -> str:
        return ", ".join(e.binary for e in self.extracts)


def detect_target(system: str | None = None, machine: str | None = None) -> str | None:
    """Platform identifier for this host, or None when the app has no Engine for it."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arm = machine in ("arm64", "aarch64")
    x64 = machine in ("x86_64", "amd64")
    if system == "darwin" and arm:
        return "macos-arm64"
    if system == "windows" and x64:
        return "windows-x64"
    if system == "linux" and arm:
        return "linux-arm64"
    if system == "linux" and x64:
        return "linux-x64"
    return None


def exe_name(binary: str, target: str) -> str:
    return f"{binary}.exe" if target == "windows-x64" else binary


# -- yt-dlp (dynamic) -------------------------------------------------------------------------

# macOS and Windows use the unpackaged build (a zip with the executable and an `_internal/`
# folder): the single-file PyInstaller executable unpacks itself into a new temp folder on every
# run, and the OS scans that folder each time (~15 s per run on a real Mac). Linux (the
# development Docker) keeps the single binary.
_YTDLP_ASSETS = {
    "macos-arm64": "yt-dlp_macos.zip",
    "windows-x64": "yt-dlp_win.zip",
    "linux-arm64": "yt-dlp_linux_aarch64",
    "linux-x64": "yt-dlp_linux",
}

# Executable inside the zip (and inside `bin/<YTDLP_DIST_DIR>/` once installed).
_YTDLP_UNPACKAGED_EXECUTABLES = {
    "macos-arm64": "yt-dlp_macos",
    "windows-x64": "yt-dlp.exe",
}

# Installed folder of the unpackaged build. It cannot be `bin/yt-dlp`: that is the file of the
# single-binary installs made by earlier versions.
YTDLP_DIST_DIR = "yt-dlp-dist"


def ytdlp_asset(target: str) -> str:
    return _YTDLP_ASSETS[target]


def ytdlp_unpackaged(target: str) -> bool:
    """Whether yt-dlp is installed as a folder (unpackaged zip) on this platform."""
    return target in _YTDLP_UNPACKAGED_EXECUTABLES


def ytdlp_executable(target: str) -> str:
    """Name of the yt-dlp executable inside the unpackaged folder."""
    return _YTDLP_UNPACKAGED_EXECUTABLES[target]


def ytdlp_asset_url(tag: str, target: str) -> str:
    return f"{_YTDLP_DOWNLOAD}/{tag}/{ytdlp_asset(target)}"


def ytdlp_sums_url(tag: str) -> str:
    return f"{_YTDLP_DOWNLOAD}/{tag}/SHA2-256SUMS"


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse `<hash>  <name>` lines (also `<hash> *<name>`) into {name: hash}."""
    sums: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            sums[parts[1].strip().lstrip("*")] = parts[0].lower()
    return sums


# -- Pinned archives (Deno, ffmpeg, ffprobe) --------------------------------------------------

_DENO = {
    "macos-arm64": (
        "deno-aarch64-apple-darwin.zip",
        "9f0bf660393da2eaff044cdc7444cb08c73f235849b61d224d825a194ce7c98e",
    ),
    # Its .sha256sum is in PowerShell Get-FileHash format, so the hash is pinned, not parsed.
    "windows-x64": (
        "deno-x86_64-pc-windows-msvc.zip",
        "cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf",
    ),
    "linux-arm64": (
        "deno-aarch64-unknown-linux-gnu.zip",
        "d49596c20b9788cf8f5d8ddf644103d4bde56ed239753f0bdb92ba9361d51905",
    ),
    "linux-x64": (
        "deno-x86_64-unknown-linux-gnu.zip",
        "e890975bc2549807bbcc0b584ffafda72cc7c93349dd99c80483dd784f6c4609",
    ),
}

# martin-riedl: one zip per binary. target -> (os/arch/build path, {binary: sha256}).
_MARTIN_RIEDL_BUILDS = {
    "macos-arm64": (
        "macos/arm64/1789931890_9.0.2",
        {
            "ffmpeg": "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924",
            "ffprobe": "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6",
        },
    ),
    "linux-arm64": (
        "linux/arm64/1789931697_9.0.2",
        {
            "ffmpeg": "93a76ae90db5474eecdf951a729857c64f3de23567228d6a7d5e6e8e3cd1021b",
            "ffprobe": "bcbe80fb741c180083327afaf5434812e006b33cacde2016b9aeaf6936128330",
        },
    ),
    "linux-x64": (
        "linux/amd64/1789931100_9.0.2",
        {
            "ffmpeg": "fa8ecf4abbd290d98f7d188b8649cc6b391ae209a98452be955a15aab1909d7f",
            "ffprobe": "3f428c49070be3d24ec338602b76d412e401ffcb8a5641ef0e729181a232fc32",
        },
    ),
}

# Gyan essentials: one zip with a versioned root folder; only bin/ffmpeg.exe and bin/ffprobe.exe.
_GYAN_ZIP = f"ffmpeg-{FFMPEG_VERSION}-essentials_build.zip"
_GYAN_SHA256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"


def pinned_archives(target: str) -> tuple[Archive, ...]:
    """The archives to download for `target`, in install order."""
    deno_zip, deno_sha = _DENO[target]
    deno = Archive(
        f"{_DENO_DOWNLOAD}/{deno_zip}", deno_sha, (Extract("deno", exe_name("deno", target)),)
    )

    if target == "windows-x64":
        ffmpeg: tuple[Archive, ...] = (
            Archive(
                f"{_GYAN}/{_GYAN_ZIP}",
                _GYAN_SHA256,
                (Extract("ffmpeg", "bin/ffmpeg.exe"), Extract("ffprobe", "bin/ffprobe.exe")),
            ),
        )
    else:
        path, hashes = _MARTIN_RIEDL_BUILDS[target]
        ffmpeg = tuple(
            Archive(f"{_MARTIN_RIEDL}/{path}/{name}.zip", hashes[name], (Extract(name, name),))
            for name in ("ffmpeg", "ffprobe")
        )
    return (deno, *ffmpeg)


def parse_release_tag(location: str) -> str:
    """The tag in the `Location` of the "latest release" redirect (`.../releases/tag/<tag>`)."""
    path = urlsplit(location).path
    prefix, sep, tag = path.rpartition("/releases/tag/")
    if not sep or not prefix.endswith("/yt-dlp/yt-dlp") or not re.fullmatch(r"[\w.\-]+", tag):
        raise ValueError(f"redirección inesperada ({location[:80]!r})")
    return tag
