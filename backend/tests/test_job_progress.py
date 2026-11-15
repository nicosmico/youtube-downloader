from __future__ import annotations

import json

from app.jobs.progress import ProgressTracker, starts_processing


def line(**fields) -> str:
    return "PROGRESS" + json.dumps(fields)


def test_single_stream_percent_bytes_speed_and_eta() -> None:
    tracker = ProgressTracker()

    p = tracker.feed(
        line(status="downloading", downloaded_bytes=250, total_bytes=1000, speed=2e6, eta=3)
    )

    assert p is not None
    assert (p.percent, p.downloaded_bytes, p.total_bytes, p.speed, p.eta) == (
        25.0,
        250,
        1000,
        2e6,
        3,
    )


def test_video_and_audio_streams_are_summed_and_never_go_backwards() -> None:
    tracker = ProgressTracker()
    video = {"filename": "v.mp4", "total_bytes": 800}
    audio = {"filename": "a.m4a", "total_bytes": 200}

    tracker.feed(line(status="downloading", downloaded_bytes=400, **video))
    done_video = tracker.feed(line(status="finished", downloaded_bytes=800, **video))
    first_audio = tracker.feed(line(status="downloading", downloaded_bytes=50, **audio))
    done = tracker.feed(line(status="finished", downloaded_bytes=200, **audio))

    assert done_video is not None and done_video.percent == 100.0
    assert first_audio is not None
    # 850 of 1000 bytes, but the bar already showed 100%: it does not move back.
    assert (first_audio.downloaded_bytes, first_audio.total_bytes) == (850, 1000)
    assert first_audio.percent == 100.0
    assert done is not None and (done.downloaded_bytes, done.total_bytes) == (1000, 1000)


def test_a_finished_stream_does_not_end_the_job_percent_before_the_next_one() -> None:
    tracker = ProgressTracker()
    tracker.feed(line(status="downloading", downloaded_bytes=100, total_bytes=1000, filename="v"))

    p = tracker.feed(
        line(status="downloading", downloaded_bytes=100, total_bytes=500, filename="a")
    )

    assert p is not None
    assert (p.downloaded_bytes, p.total_bytes) == (200, 1500)
    assert round(p.percent, 1) == 13.3


def test_total_bytes_estimate_is_used_when_total_bytes_is_null() -> None:
    tracker = ProgressTracker()

    p = tracker.feed(
        line(
            status="downloading",
            downloaded_bytes=300,
            total_bytes=None,
            total_bytes_estimate=1200.5,
            speed=None,
            eta=None,
        )
    )

    assert p is not None
    assert (p.percent, p.total_bytes, p.speed, p.eta) == (25.0, 1200, None, None)


def test_unknown_total_keeps_the_percent_and_reports_no_total() -> None:
    tracker = ProgressTracker()
    tracker.feed(line(status="downloading", downloaded_bytes=100, total_bytes=1000, filename="v"))

    p = tracker.feed(line(status="downloading", downloaded_bytes=10, filename="a"))

    assert p is not None
    assert p.total_bytes is None
    assert p.percent == 10.0


def test_garbage_and_other_lines_are_ignored() -> None:
    tracker = ProgressTracker()

    for text in ("", "/downloads/x.mp4", "PROGRESS", "PROGRESS{not json", "PROGRESS[1]", line()):
        assert tracker.feed(text) is None


def test_processing_starts_with_the_first_postprocessor_that_is_not_move_files() -> None:
    def pp(status: str, name: str) -> str:
        return "POSTPROC" + json.dumps({"status": status, "postprocessor": name})

    assert starts_processing(pp("started", "Merger"))
    assert starts_processing(pp("started", "ExtractAudio"))
    assert not starts_processing(pp("finished", "Merger"))
    assert not starts_processing(pp("started", "MoveFiles"))
    assert not starts_processing("ERROR: something")
    assert not starts_processing("POSTPROC{broken")
