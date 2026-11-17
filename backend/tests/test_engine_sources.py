from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from app.engine import EngineManager, sources
from tests.fakes import FakeFetcher, FakeRunner, make_zip, sha256


@pytest.mark.parametrize(
    ("system", "machine", "target"),
    [
        ("Darwin", "arm64", "macos-arm64"),
        ("Windows", "AMD64", "windows-x64"),
        ("Linux", "aarch64", "linux-arm64"),
        ("Linux", "x86_64", "linux-x64"),
        ("Darwin", "x86_64", None),
        ("Windows", "ARM64", None),
    ],
)
def test_detect_target(system: str, machine: str, target: str | None) -> None:
    assert sources.detect_target(system, machine) == target


YTDLP_ASSETS = {
    "macos-arm64": "yt-dlp_macos.zip",
    "windows-x64": "yt-dlp_win.zip",
    "linux-arm64": "yt-dlp_linux_aarch64",
    "linux-x64": "yt-dlp_linux",
}


@pytest.mark.parametrize("target", sources.TARGETS)
def test_ytdlp_asset_per_target(target: str) -> None:
    assert sources.ytdlp_asset(target) == YTDLP_ASSETS[target]
    assert sources.ytdlp_asset_url("2026.10.26", target) == (
        f"https://github.com/yt-dlp/yt-dlp/releases/download/2026.10.26/{YTDLP_ASSETS[target]}"
    )


@pytest.mark.parametrize(
    ("target", "unpackaged", "executable"),
    [
        ("macos-arm64", True, "yt-dlp_macos"),
        ("windows-x64", True, "yt-dlp.exe"),
        ("linux-arm64", False, None),
        ("linux-x64", False, None),
    ],
)
def test_ytdlp_is_unpackaged_only_on_macos_and_windows(
    target: str, unpackaged: bool, executable: str | None
) -> None:
    assert sources.ytdlp_unpackaged(target) is unpackaged
    if executable:
        assert sources.ytdlp_executable(target) == executable


def test_ytdlp_sums_url() -> None:
    assert sources.ytdlp_sums_url("2026.10.26").endswith("/2026.10.26/SHA2-256SUMS")


def by_binary(target: str) -> dict[str, tuple[sources.Archive, str]]:
    return {
        e.binary: (archive, e.member)
        for archive in sources.pinned_archives(target)
        for e in archive.extracts
    }


@pytest.mark.parametrize("target", sources.TARGETS)
def test_every_target_pins_deno_ffmpeg_and_ffprobe(target: str) -> None:
    pinned = by_binary(target)

    assert set(pinned) == {"deno", "ffmpeg", "ffprobe"}
    for archive, _ in pinned.values():
        assert re.fullmatch(r"[0-9a-f]{64}", archive.sha256)
        assert archive.url.startswith("https://")


EXPECTED_DENO = {
    "macos-arm64": (
        "deno-aarch64-apple-darwin.zip",
        "9f0bf660393da2eaff044cdc7444cb08c73f235849b61d224d825a194ce7c98e",
        "deno",
    ),
    "windows-x64": (
        "deno-x86_64-pc-windows-msvc.zip",
        "cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf",
        "deno.exe",
    ),
    "linux-arm64": (
        "deno-aarch64-unknown-linux-gnu.zip",
        "d49596c20b9788cf8f5d8ddf644103d4bde56ed239753f0bdb92ba9361d51905",
        "deno",
    ),
    "linux-x64": (
        "deno-x86_64-unknown-linux-gnu.zip",
        "e890975bc2549807bbcc0b584ffafda72cc7c93349dd99c80483dd784f6c4609",
        "deno",
    ),
}


@pytest.mark.parametrize("target", sources.TARGETS)
def test_deno_asset_and_hash_per_target(target: str) -> None:
    asset, digest, member = EXPECTED_DENO[target]
    archive, extracted = by_binary(target)["deno"]

    assert archive.url == f"https://github.com/denoland/deno/releases/download/v2.9.8/{asset}"
    assert archive.sha256 == digest
    assert extracted == member


@pytest.mark.parametrize(
    ("target", "build", "ffmpeg_sha", "ffprobe_sha"),
    [
        (
            "macos-arm64",
            "macos/arm64/1789931890_9.0.2",
            "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924",
            "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6",
        ),
        (
            "linux-arm64",
            "linux/arm64/1789931697_9.0.2",
            "93a76ae90db5474eecdf951a729857c64f3de23567228d6a7d5e6e8e3cd1021b",
            "bcbe80fb741c180083327afaf5434812e006b33cacde2016b9aeaf6936128330",
        ),
        (
            "linux-x64",
            "linux/amd64/1789931100_9.0.2",
            "fa8ecf4abbd290d98f7d188b8649cc6b391ae209a98452be955a15aab1909d7f",
            "3f428c49070be3d24ec338602b76d412e401ffcb8a5641ef0e729181a232fc32",
        ),
    ],
)
def test_martin_riedl_has_one_zip_per_binary(
    target: str, build: str, ffmpeg_sha: str, ffprobe_sha: str
) -> None:
    pinned = by_binary(target)

    for binary, digest in (("ffmpeg", ffmpeg_sha), ("ffprobe", ffprobe_sha)):
        archive, member = pinned[binary]
        assert archive.url == f"https://ffmpeg.martin-riedl.de/download/{build}/{binary}.zip"
        assert archive.sha256 == digest
        assert member == binary
        assert len(archive.extracts) == 1


def test_windows_uses_one_gyan_zip_with_bin_executables() -> None:
    pinned = by_binary("windows-x64")
    ffmpeg, ffmpeg_member = pinned["ffmpeg"]
    ffprobe, ffprobe_member = pinned["ffprobe"]

    assert ffmpeg is ffprobe
    assert ffmpeg.url == (
        "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/"
        "ffmpeg-9.0.2-essentials_build.zip"
    )
    assert ffmpeg.sha256 == "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
    assert (ffmpeg_member, ffprobe_member) == ("bin/ffmpeg.exe", "bin/ffprobe.exe")


def test_gyan_zip_layout_is_extracted_from_its_versioned_root(tmp_path: Path) -> None:
    """Real Gyan members under a versioned root; only the two executables are taken."""
    root = "ffmpeg-9.0.2-essentials_build"
    zip_bytes = make_zip(
        {
            f"{root}/README.txt": b"readme",
            f"{root}/bin/ffmpeg.exe": b"ffmpeg version 9.0.2-essentials_build-www.gyan.dev\n",
            f"{root}/bin/ffplay.exe": b"not needed",
            f"{root}/bin/ffprobe.exe": b"ffprobe version 9.0.2-essentials_build-www.gyan.dev\n",
        }
    )
    real = sources.pinned_archives("windows-x64")
    gyan = dataclasses.replace(real[1], sha256=sha256(zip_bytes))
    fetcher = FakeFetcher()
    fetcher.add(gyan.url, zip_bytes)
    fetcher.add(real[0].url, make_zip({"deno.exe": b"deno 2.9.8 (stable)\n"}))
    fetcher.publish_ytdlp("2026.10.26", b"2026.10.26\n", target="windows-x64")
    deno = dataclasses.replace(real[0], sha256=sha256(fetcher.routes[real[0].url]))

    engine = EngineManager(
        data_dir=tmp_path,
        target="windows-x64",
        fetcher=fetcher,
        runner=FakeRunner(),
        spawn=lambda fn: fn(),
        pinned=lambda _t: (deno, gyan),
    )
    engine.install()

    assert engine.info().status == "ready", engine.info().message
    assert sorted(p.name for p in (tmp_path / "bin").iterdir()) == [
        "deno.exe",
        "ffmpeg.exe",
        "ffprobe.exe",
        "yt-dlp-dist",
    ]
    assert (tmp_path / "bin" / "yt-dlp-dist" / "yt-dlp.exe").is_file()
    assert fetcher.downloads_of("essentials_build.zip") == 1


def test_parse_sha256sums_reads_the_ytdlp_format() -> None:
    digest = "a" * 64
    text = f"{digest}  yt-dlp\n{'b' * 64} *yt-dlp.exe\nnot a line\n"

    assert sources.parse_sha256sums(text) == {"yt-dlp": digest, "yt-dlp.exe": "b" * 64}


@pytest.mark.parametrize(
    ("target", "expected"),
    [("windows-x64", "ffmpeg.exe"), ("macos-arm64", "ffmpeg"), ("linux-x64", "ffmpeg")],
)
def test_exe_name(target: str, expected: str) -> None:
    assert sources.exe_name("ffmpeg", target) == expected
