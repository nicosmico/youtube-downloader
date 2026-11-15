"""Contract of the yt-dlp command line of a download (spec: "Runner y yt-dlp")."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine import EngineManager
from app.jobs.arguments import VIDEO_SORT, UnsupportedJob, download_args
from app.jobs.models import Job, JobStatus

URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def job(quality: str | None = "best", mode: str = "video") -> Job:
    return Job(
        id="j1",
        url=URL,
        mode=mode,
        quality=quality,
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


def test_audio_is_not_supported_yet(engine: EngineManager, tmp_path: Path) -> None:
    with pytest.raises(UnsupportedJob):
        download_args(engine, job(mode="audio"), tmp_path)
