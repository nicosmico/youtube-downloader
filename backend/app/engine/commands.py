"""Argument prefix shared by every yt-dlp invocation (spec: "Runner y yt-dlp")."""

from __future__ import annotations

from app.engine.manager import EngineManager


def ytdlp_base_args(engine: EngineManager) -> list[str]:
    """yt-dlp plus the mandatory Engine flags.

    Without `--ffmpeg-location` the default format degrades to a low-quality muxed one; without
    `--js-runtimes` yt-dlp only looks for Deno on the PATH.
    """
    return [
        str(engine.binary_path("yt-dlp")),
        "--ffmpeg-location",
        str(engine.bin_dir.absolute()),
        "--js-runtimes",
        f"deno:{engine.binary_path('deno').absolute()}",
    ]
