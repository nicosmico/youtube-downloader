"""Contract of the yt-dlp command line of a download (spec: "Runner y yt-dlp")."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine import EngineManager
from app.jobs.arguments import AUDIO_FORMAT_SELECTOR, VIDEO_SORT, UnsupportedJob, download_args
from app.jobs.models import Job, JobStatus

URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def job(quality: str | None = "best", mode: str = "video", audio_format: str | None = None) -> Job:
    return Job(
        id="j1",
        url=URL,
        mode=mode,
        quality=quality,
        audio_format=audio_format,
        status=JobStatus.DOWNLOADING,
        created_at="2026-11-15T12:00:00.000000+00:00",
    )


def value_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def test_engine_flags_and_the_download_contract(engine: EngineManager, tmp_path: Path) -> None:
    args = download_args(engine, job(), tmp_path / "staging" / "j1")

    assert args[0] == str(engine.binary_path("yt-dlp"))
    assert value_after(args, "--ffmpeg-location") == str(engine.bin_dir.absolute())
    assert value_after(args, "--js-runtimes") == f"deno:{engine.binary_path('deno').absolute()}"
    for flag in ("--no-playlist", "--newline", "--progress", "--no-overwrites"):
        assert flag in args
    templates = [args[i + 1] for i, a in enumerate(args) if a == "--progress-template"]
    assert templates == ["download:PROGRESS%(progress)j", "postprocess:POSTPROC%(progress)j"]
    prints = [args[i + 1] for i, a in enumerate(args) if a == "--print"]
    assert prints == ["before_dl:TOTAL%(filesize,filesize_approx)j", "after_move:filepath"]
    assert value_after(args, "-P") == str(tmp_path / "staging" / "j1")
    assert value_after(args, "-o") == "%(title)s.%(ext)s"
    assert value_after(args, "--merge-output-format") == "mp4"
    assert args[-1] == URL


@pytest.mark.parametrize(
    ("quality", "sort"),
    [
        ("best", "res,vcodec:h264,acodec:aac"),
        ("2160p", "res:2160,vcodec:h264,acodec:aac"),
        ("1080p", "res:1080,vcodec:h264,acodec:aac"),
        ("720p", "res:720,vcodec:h264,acodec:aac"),
        ("480p", "res:480,vcodec:h264,acodec:aac"),
    ],
)
def test_sort_expression_per_quality(
    engine: EngineManager, tmp_path: Path, quality: str, sort: str
) -> None:
    args = download_args(engine, job(quality), tmp_path)

    assert value_after(args, "-S") == sort
    assert "-f" not in args  # the default `bv*+ba/b` applies


def test_every_quality_of_the_spec_has_a_sort_expression() -> None:
    assert set(VIDEO_SORT) == {"best", "2160p", "1080p", "720p", "480p"}


def test_a_missing_quality_means_best(engine: EngineManager, tmp_path: Path) -> None:
    assert value_after(download_args(engine, job(None), tmp_path), "-S") == VIDEO_SORT["best"]


def test_video_has_no_audio_flags(engine: EngineManager, tmp_path: Path) -> None:
    args = download_args(engine, job("720p"), tmp_path)

    for flag in ("-x", "--audio-format", "--audio-quality", "-f"):
        assert flag not in args


@pytest.mark.parametrize(
    ("audio_format", "selector"),
    [
        ("m4a", "ba[acodec^=mp4a]/ba"),
        ("opus", "ba[acodec=opus]/ba"),
        ("mp3", "ba"),
    ],
)
def test_audio_selects_the_native_stream_and_extracts(
    engine: EngineManager, tmp_path: Path, audio_format: str, selector: str
) -> None:
    args = download_args(engine, job(None, "audio", audio_format), tmp_path / "staging")

    assert value_after(args, "-f") == selector
    assert "-x" in args
    assert value_after(args, "--audio-quality") == "0"
    assert value_after(args, "--audio-format") == audio_format
    assert "--merge-output-format" not in args
    assert "-S" not in args
    # the shared download contract is the same as for video
    assert value_after(args, "-P") == str(tmp_path / "staging")
    assert args[-1] == URL
    assert [args[i + 1] for i, a in enumerate(args) if a == "--print"] == [
        "before_dl:TOTAL%(filesize,filesize_approx)j",
        "after_move:filepath",
    ]


def test_every_audio_format_of_the_spec_has_a_selector() -> None:
    assert set(AUDIO_FORMAT_SELECTOR) == {"mp3", "m4a", "opus"}


@pytest.mark.parametrize(
    "bad",
    [job(None, "audio", None), job(None, "audio", "flac"), job(mode="gif")],
)
def test_an_unknown_mode_or_audio_format_is_unsupported(
    engine: EngineManager, tmp_path: Path, bad: Job
) -> None:
    with pytest.raises(UnsupportedJob):
        download_args(engine, bad, tmp_path)


@pytest.mark.parametrize("mode", ["video", "audio"])
def test_load_info_json_takes_the_place_of_the_url_and_changes_nothing_else(
    engine: EngineManager, tmp_path: Path, mode: str
) -> None:
    j = job(None, "audio", "mp3") if mode == "audio" else job()
    staging = tmp_path / "staging" / "j1"
    info = staging / "info.json"

    from_url = download_args(engine, j, staging)
    from_info = download_args(engine, j, staging, info)

    assert from_url[:-1] == from_info[:-2]
    assert from_url[-1] == URL
    assert from_info[-2:] == ["--load-info-json", str(info)]
    assert URL not in from_info
