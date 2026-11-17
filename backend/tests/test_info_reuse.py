"""A download reuses the JSON of the preview (`--load-info-json`): the cache, the runner that
looks it up when a job starts, the transparent fallback to the URL, and the whole path through the
API. FakeEngine and FakeYtdlp at the subprocess edges; a fake clock; no network."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.engine import EngineManager
from app.engine.io import ProcessHandle
from app.jobs import FileMover, Job, JobRepository, JobRunner
from app.jobs.files import INFO_JSON_NAME, find_staged_file
from app.main import create_app
from app.preview import PreviewService
from app.preview.cache import INFO_MAX_ENTRIES, INFO_TTL_SECONDS, InfoCache
from tests.conftest import APP_HEADERS, HOST, PORT
from tests.fake_engine import FakeEngine
from tests.fakes import FakeYtdlp, load_fixture
from tests.test_jobs_api import downloads, enqueue, get_job, wait_for

URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
LIST = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
INFO = json.dumps({"id": "jNQXAC9IVRw", "webpage_url": URL, "title": "Me at the zoo"})


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# -- the cache ----------------------------------------------------------------------------------


class TestInfoCache:
    def test_returns_what_was_stored_while_it_is_valid(self) -> None:
        clock = Clock()
        cache = InfoCache(clock=clock)
        cache.put(URL, INFO)

        clock.now += INFO_TTL_SECONDS - 1

        assert cache.get(URL) == INFO

    def test_an_entry_expires_after_an_hour(self) -> None:
        clock = Clock()
        cache = InfoCache(clock=clock)
        cache.put(URL, INFO)

        clock.now += INFO_TTL_SECONDS

        assert cache.get(URL) is None

    def test_an_unknown_url_is_a_miss(self) -> None:
        assert InfoCache().get(URL) is None

    def test_putting_again_restarts_the_validity(self) -> None:
        clock = Clock()
        cache = InfoCache(clock=clock)
        cache.put(URL, "old")
        clock.now += INFO_TTL_SECONDS - 1

        cache.put(URL, "new")
        clock.now += INFO_TTL_SECONDS - 1

        assert cache.get(URL) == "new"

    def test_discard_removes_the_entry(self) -> None:
        cache = InfoCache()
        cache.put(URL, INFO)

        cache.discard(URL)
        cache.discard("https://www.youtube.com/watch?v=unknown")  # no error

        assert cache.get(URL) is None

    def test_keeps_at_most_twenty_entries_dropping_the_least_recently_used(self) -> None:
        assert INFO_MAX_ENTRIES == 20
        cache = InfoCache()
        for n in range(20):
            cache.put(f"u{n}", f"raw{n}")
        assert cache.get("u0") == "raw0"  # u0 is now the most recently used; u1 the oldest

        cache.put("u20", "raw20")

        assert cache.get("u1") is None
        assert cache.get("u0") == "raw0"
        assert [cache.get(f"u{n}") for n in (2, 19, 20)] == ["raw2", "raw19", "raw20"]

    def test_is_safe_across_threads(self) -> None:
        cache = InfoCache(max_entries=10)
        errors: list[Exception] = []

        def hammer(seed: int) -> None:
            try:
                for n in range(300):
                    key = f"u{(seed + n) % 25}"
                    cache.put(key, "x")
                    cache.get(key)
                    if n % 7 == 0:
                        cache.discard(key)
            except Exception as exc:  # pragma: no cover - only on a race
                errors.append(exc)

        threads = [threading.Thread(target=hammer, args=(s,)) for s in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert sum(cache.get(f"u{n}") is not None for n in range(25)) <= 10


class TestPreviewFillsTheCache:
    @pytest.fixture
    def ytdlp(self) -> FakeYtdlp:
        fake = FakeYtdlp()
        fake.respond(URL, load_fixture("normal"))
        fake.respond(f"https://www.youtube.com/playlist?list={LIST}", load_fixture("playlist"))
        fake.respond("https://www.youtube.com/watch?v=ROboUHfPUrU", load_fixture("live"))
        return fake

    def test_a_video_preview_stores_the_raw_output_under_the_canonical_url(
        self, engine: EngineManager, ytdlp: FakeYtdlp
    ) -> None:
        engine.install()
        cache = InfoCache()
        service = PreviewService(engine, ytdlp, cache=cache)

        service.preview(f"https://youtu.be/jNQXAC9IVRw?si=abc&list={LIST}")  # normalized to URL

        assert cache.get(URL) == json.dumps(load_fixture("normal"))

    def test_a_playlist_is_not_stored(self, engine: EngineManager, ytdlp: FakeYtdlp) -> None:
        engine.install()
        cache = InfoCache()
        service = PreviewService(engine, ytdlp, cache=cache)

        service.preview(f"https://www.youtube.com/playlist?list={LIST}")

        assert cache.get(f"https://www.youtube.com/playlist?list={LIST}") is None

    def test_a_preview_that_fails_is_not_stored(
        self, engine: EngineManager, ytdlp: FakeYtdlp
    ) -> None:
        from app.preview import PreviewFailure

        engine.install()
        cache = InfoCache()
        service = PreviewService(engine, ytdlp, cache=cache)

        with pytest.raises(PreviewFailure):
            service.preview("https://www.youtube.com/watch?v=ROboUHfPUrU")  # a live stream

        assert cache.get("https://www.youtube.com/watch?v=ROboUHfPUrU") is None


# -- the runner ---------------------------------------------------------------------------------


class Harness:
    def __init__(self, tmp_path: Path, engine: EngineManager, fake: FakeEngine) -> None:
        db = Database(tmp_path / "db.sqlite3")
        db.migrate()
        self.repo = JobRepository(db)
        self.clock = Clock()
        self.cache = InfoCache(clock=self.clock)
        self.published: list[Job] = []
        self.staging = tmp_path / "staging"
        self.downloads = tmp_path / "downloads"
        self.fake = fake
        self.runner = JobRunner(
            engine=engine,
            repo=self.repo,
            mover=FileMover(self.downloads),
            staging_root=self.staging,
            publish=self.published.append,
            stream=fake,
            clock=self.clock,
            cached_info=self.cache.get,
            discard_info=self.cache.discard,
        )

    def claim(self, **options) -> Job:
        self.repo.create(url=URL, **({"mode": "video", "quality": "best"} | options))
        (job,) = self.repo.claim_queued(1)
        return job

    def run(self, **options) -> Job:
        return self.runner.run(self.claim(**options))

    def statuses(self, job_id: str) -> list[str]:
        return [j.status.value for j in self.published if j.id == job_id]


@pytest.fixture
def harness(tmp_path: Path, engine: EngineManager, fake_engine: FakeEngine) -> Harness:
    engine.install()
    return Harness(tmp_path, engine, fake_engine)


def loaded_info(args: list[str]) -> str:
    return args[args.index("--load-info-json") + 1]


class TestRunnerReusesTheInfo:
    def test_a_recent_preview_starts_the_job_with_load_info_json_and_without_the_url(
        self, harness: Harness
    ) -> None:
        harness.cache.put(URL, INFO)

        job = harness.run()

        assert job.status.value == "completed"
        (args,) = harness.fake.calls
        assert URL not in args
        assert args[-2] == "--load-info-json"
        assert Path(args[-1]).name == INFO_JSON_NAME
        assert Path(args[-1]).parent.parent == harness.staging
        # the rest of the command line is the one of a download from the URL
        assert "--no-playlist" in args and "-S" in args and "--merge-output-format" in args

    def test_the_info_file_holds_the_text_of_the_preview(self, harness: Harness) -> None:
        harness.cache.put(URL, INFO)
        seen: list[str] = []
        harness.fake.on_begin = lambda url: seen.append(
            Path(loaded_info(harness.fake.calls[-1])).read_text("utf-8")
        )

        harness.run()

        assert seen == [INFO]

    def test_without_a_preview_the_url_goes_last_as_before(self, harness: Harness) -> None:
        job = harness.run()

        assert job.status.value == "completed"
        (args,) = harness.fake.calls
        assert args[-1] == URL
        assert "--load-info-json" not in args

    def test_an_expired_preview_is_not_used(self, harness: Harness) -> None:
        harness.cache.put(URL, INFO)
        harness.clock.now += INFO_TTL_SECONDS

        harness.run()

        (args,) = harness.fake.calls
        assert args[-1] == URL

    def test_it_is_looked_up_when_the_job_starts_not_when_it_was_created(
        self, harness: Harness
    ) -> None:
        job = harness.claim()  # created while there was no preview...
        harness.cache.put(URL, INFO)  # ...which arrived before it ran

        harness.runner.run(job)

        assert "--load-info-json" in harness.fake.calls[0]

    def test_a_playlist_entry_never_uses_the_cache(self, harness: Harness) -> None:
        harness.cache.put(URL, INFO)
        batch = harness.repo.create_batch(
            source_url="https://www.youtube.com/playlist?list=PL1",
            title="L",
            folder_name="L",
            entry_count=1,
        )

        job = harness.runner.run(harness.claim(batch_id=batch.id, playlist_index=1))

        assert job.status.value == "completed"
        (args,) = harness.fake.calls
        assert args[-1] == URL

    def test_info_json_is_never_moved_to_the_downloads_folder(self, harness: Harness) -> None:
        harness.cache.put(URL, INFO)

        job = harness.run()

        assert job.status.value == "completed"
        assert sorted(p.name for p in harness.downloads.iterdir()) == ["Me at the zoo.mp4"]
        assert not (harness.staging / job.id).exists()

    def test_find_staged_file_ignores_info_json(self, tmp_path: Path) -> None:
        (tmp_path / INFO_JSON_NAME).write_text(INFO)
        video = tmp_path / "Me at the zoo.mp4"
        video.write_bytes(b"v")

        assert find_staged_file(tmp_path, None) == video
        video.unlink()
        assert find_staged_file(tmp_path, None) is None


class TestFallbackToTheUrl:
    def test_a_failure_with_the_info_is_retried_from_the_url_in_the_same_attempt(
        self, harness: Harness, caplog: pytest.LogCaptureFixture
    ) -> None:
        harness.cache.put(URL, INFO)
        harness.fake.default.fail_from_info = "ERROR: Unable to download: 403 Forbidden"

        with caplog.at_level(logging.WARNING, logger="app.jobs"):
            job = harness.run()

        assert job.status.value == "completed"
        assert job.attempt == 1
        first, second = harness.fake.calls
        assert "--load-info-json" in first and URL not in first
        assert second[-1] == URL and "--load-info-json" not in second
        assert f"job {job.id}: cached info failed, retrying from the URL" in caplog.messages
        assert harness.cache.get(URL) is None  # the entry is dropped
        assert "failed" not in harness.statuses(job.id)
        assert sorted(p.name for p in harness.downloads.iterdir()) == ["Me at the zoo.mp4"]

    def test_it_retries_only_once_when_the_url_fails_too(self, harness: Harness) -> None:
        harness.cache.put(URL, INFO)
        harness.fake.default.fail_with = "ERROR: Video unavailable"

        job = harness.run()

        assert job.status.value == "failed"
        assert len(harness.fake.calls) == 2
        assert harness.statuses(job.id).count("failed") == 1
        assert harness.statuses(job.id)[-1] == "failed"

    def test_the_retry_starts_from_a_clean_staging(self, harness: Harness) -> None:
        harness.cache.put(URL, INFO)
        harness.fake.default.fail_from_info = "ERROR: boom"
        job = harness.claim()
        leftovers: list[list[str]] = []
        harness.fake.on_begin = lambda url: leftovers.append(
            sorted(p.name for p in (harness.staging / job.id).iterdir())
        )

        harness.runner.run(job)

        assert leftovers == [[INFO_JSON_NAME], []]

    def test_a_failure_without_the_info_is_not_retried(self, harness: Harness) -> None:
        harness.fake.default.fail_with = "ERROR: Video unavailable"

        job = harness.run()

        assert job.status.value == "failed"
        assert len(harness.fake.calls) == 1

    def test_a_shutdown_during_the_run_with_the_info_does_not_fall_back(
        self, harness: Harness
    ) -> None:
        harness.cache.put(URL, INFO)
        harness.fake.default.hold = True
        stopping = threading.Event()
        handles: list[ProcessHandle] = []

        def on_handle(handle: ProcessHandle) -> None:
            handles.append(handle)
            stopping.set()
            handle.terminate()

        job = harness.runner.run(harness.claim(), on_handle, interrupted=stopping.is_set)

        assert job.status.value == "interrupted"
        assert len(harness.fake.calls) == 1
        assert harness.cache.get(URL) == INFO  # nothing was wrong with it


class TestCancelWithTheInfo:
    def test_canceling_while_it_runs_does_not_trigger_the_fallback(self, harness: Harness) -> None:
        harness.cache.put(URL, INFO)
        harness.fake.default.hold = True
        canceled = threading.Event()

        def on_handle(handle: ProcessHandle) -> None:
            canceled.set()
            handle.terminate()

        job = harness.runner.run(harness.claim(), on_handle, canceled=canceled.is_set)

        assert job.status.value == "canceled"
        assert len(harness.fake.calls) == 1
        assert harness.statuses(job.id)[-1] == "canceled"
        assert harness.cache.get(URL) == INFO
        assert not (harness.staging / job.id).exists()


# -- through the API ----------------------------------------------------------------------------


class TestThroughTheApi:
    @pytest.fixture
    def ytdlp(self) -> FakeYtdlp:
        fake = FakeYtdlp()
        fake.respond(URL, load_fixture("normal"))
        return fake

    @pytest.fixture
    def client(
        self,
        engine: EngineManager,
        ytdlp: FakeYtdlp,
        fake_engine: FakeEngine,
        data_dir: Path,
        download_dir: Path,
        static_dir: Path,
    ) -> TestClient:
        engine.install()
        app = create_app(
            data_dir=data_dir,
            port=PORT,
            static_dir=static_dir,
            engine=engine,
            ytdlp_runner=ytdlp,
            streamer=fake_engine,
            download_dir=download_dir,
            spawn_job=lambda fn: fn(),
        )
        return TestClient(app, base_url=f"http://{HOST}")

    def test_a_download_after_its_preview_loads_the_info_of_the_preview(
        self, client: TestClient, ytdlp: FakeYtdlp, fake_engine: FakeEngine, download_dir: Path
    ) -> None:
        client.post("/api/preview", json={"url": URL}, headers=APP_HEADERS)

        (job,) = enqueue(client).json()["jobs"]

        wait_for(lambda: get_job(client, job["id"])["status"] == "completed")
        assert len(ytdlp.calls) == 1  # only the preview talked to YouTube
        (args,) = fake_engine.calls
        assert "--load-info-json" in args and URL not in args
        assert downloads(download_dir) == ["Me at the zoo.mp4"]

    def test_a_download_without_a_preview_uses_the_url(
        self, client: TestClient, fake_engine: FakeEngine
    ) -> None:
        (job,) = enqueue(client).json()["jobs"]

        wait_for(lambda: get_job(client, job["id"])["status"] == "completed")
        assert fake_engine.calls[0][-1] == URL
