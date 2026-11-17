"""The yt-dlp command line of a download (spec: "Runner y yt-dlp")."""

from __future__ import annotations

from pathlib import Path

from app.engine import EngineManager
from app.engine.commands import ytdlp_base_args
from app.jobs.models import Job

# ADR-0009: `res` measures the short side, so a vertical video respects the Quality too.
VIDEO_SORT = {
    "best": "res,vcodec:h264,acodec:aac",
    "2160p": "res:2160,vcodec:h264,acodec:aac",
    "1080p": "res:1080,vcodec:h264,acodec:aac",
    "720p": "res:720,vcodec:h264,acodec:aac",
    "480p": "res:480,vcodec:h264,acodec:aac",
}
# Spec "Runner y yt-dlp": the `-f` picks the native audio stream; `-x` only re-encodes when the
# stream is not already in the requested format (mp3 always is).
AUDIO_FORMAT_SELECTOR = {
    "m4a": "ba[acodec^=mp4a]/ba",
    "opus": "ba[acodec=opus]/ba",
    "mp3": "ba",
}
OUTPUT_TEMPLATE = "%(title)s.%(ext)s"


class UnsupportedJob(Exception):
    """The job asks for something this build cannot download."""


def _mode_args(job: Job) -> list[str]:
    if job.mode == "audio":
        fmt = job.audio_format or ""
        selector = AUDIO_FORMAT_SELECTOR.get(fmt)
        if selector is None:
            raise UnsupportedJob(f"audio format {job.audio_format}")
        return ["-f", selector, "-x", "--audio-quality", "0", "--audio-format", fmt]
    if job.mode == "video":
        sort = VIDEO_SORT.get(job.quality or "best")
        if sort is None:
            raise UnsupportedJob(f"quality {job.quality}")
        return ["-S", sort, "--merge-output-format", "mp4"]
    raise UnsupportedJob(job.mode)


def download_args(
    engine: EngineManager, job: Job, staging: Path, info_json: Path | None = None
) -> list[str]:
    """Arguments for one video. The URL is last (the fake engine of the tests relies on it).

    With `info_json` (the output of a recent preview) yt-dlp reads the video from that file
    instead of extracting it again from the URL: `--load-info-json <file>` takes the URL's place.
    The format is chosen again from the file's format list with the same `-f`/`-S`."""
    return [
        *ytdlp_base_args(engine),
        "--no-playlist",
        "--newline",
        "--progress",
        "--no-overwrites",
        "--progress-template",
        "download:PROGRESS%(progress)j",
        "--progress-template",
        "postprocess:POSTPROC%(progress)j",
        # Whole-job size before downloading (video + audio of a merged format): a stable total.
        "--print",
        "before_dl:TOTAL%(filesize,filesize_approx)j",
        "--print",
        "after_move:filepath",
        "-P",
        str(staging),
        "-o",
        OUTPUT_TEMPLATE,
        *_mode_args(job),
        *(["--load-info-json", str(info_json)] if info_json else [job.url]),
    ]
