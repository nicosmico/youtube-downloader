from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from app.engine import (
    EngineInfo,
    EngineManager,
    EngineStatus,
    UpdateOutcome,
    run_periodic,
    sources,
)
from tests.conftest import FakeClock
from tests.fakes import (
    DENO,
    FFMPEG,
    FFPROBE,
    YTDLP_NEW,
    YTDLP_OLD,
    FakeFetcher,
    FakeRunner,
    fake_archives,
    make_zip,
    sha256,
    ytdlp_zip,
)

MakeEngine = Callable[..., EngineManager]


def bin_dir(data_dir: Path) -> Path:
    return data_dir / "bin"


def manifest(data_dir: Path) -> dict:
    return json.loads((data_dir / "engine.json").read_text())


class TestInstall:
    def test_fresh_install_downloads_verifies_and_activates_the_four_binaries(
        self, engine: EngineManager, data_dir: Path, clock: FakeClock
    ) -> None:
        seen: list[EngineStatus] = []
        engine.subscribe(lambda info: seen.append(info.status))
        assert engine.info().status == EngineStatus.MISSING

        engine.install()

        info = engine.info()
        assert info.status == EngineStatus.READY
        assert info.message is None
        assert info.versions == {
            "yt-dlp": "2026.10.26",
            "ffmpeg": "9.0.2",
            "ffprobe": "9.0.2",
            "deno": "2.9.8",
        }
        # (listeners also hear about intermediate changes, e.g. the last-check time)
        assert [s for i, s in enumerate(seen) if i == 0 or s != seen[i - 1]] == [
            EngineStatus.INSTALLING,
            EngineStatus.READY,
        ]
        assert sorted(p.name for p in bin_dir(data_dir).iterdir()) == [
            "deno",
            "ffmpeg",
            "ffprobe",
            "yt-dlp",
        ]
        for name in ("deno", "ffmpeg", "ffprobe", "yt-dlp"):
            assert os.access(bin_dir(data_dir) / name, os.X_OK)

    def test_engine_json_records_version_and_hash_of_each_binary(
        self, engine: EngineManager, data_dir: Path, clock: FakeClock
    ) -> None:
        engine.install()

        saved = manifest(data_dir)
        assert saved["lastUpdateCheck"] == clock().isoformat()
        assert {name: entry["version"] for name, entry in saved["binaries"].items()} == {
            "yt-dlp": "2026.10.26",
            "ffmpeg": "9.0.2",
            "ffprobe": "9.0.2",
            "deno": "2.9.8",
        }
        assert saved["binaries"]["yt-dlp"]["sha256"] == sha256(YTDLP_OLD)
        assert saved["binaries"]["ffmpeg"]["sha256"] == sha256(FFMPEG)
        assert saved["binaries"]["ffprobe"]["sha256"] == sha256(FFPROBE)
        assert saved["binaries"]["deno"]["sha256"] == sha256(DENO)

    def test_hash_mismatch_is_an_error_and_activates_nothing(
        self, make_engine: MakeEngine, fetcher: FakeFetcher, data_dir: Path
    ) -> None:
        archives, routes = fake_archives()
        tampered = routes[archives[1].url] + b"tampered"  # ffmpeg.zip differs from its pinned hash
        fetcher.add(archives[1].url, tampered)
        engine = make_engine()

        engine.install()

        info = engine.info()
        assert info.status == EngineStatus.ERROR
        assert info.message is not None and "ffmpeg" in info.message and "SHA-256" in info.message
        assert not (bin_dir(data_dir) / "ffmpeg").exists()
        assert "ffmpeg" not in manifest(data_dir)["binaries"]
        assert [p.name for p in bin_dir(data_dir).iterdir() if p.suffix in (".tmp", ".new")] == []

    def test_ytdlp_with_hash_not_in_sha2_256sums_is_not_activated(
        self, make_engine: MakeEngine, fetcher: FakeFetcher, data_dir: Path
    ) -> None:
        fetcher.publish_ytdlp("2026.10.26", YTDLP_OLD, sums_sha256="f" * 64)
        engine = make_engine()

        engine.install()

        assert engine.info().status == EngineStatus.ERROR
        assert not (bin_dir(data_dir) / "yt-dlp").exists()

    def test_deno_failing_its_version_check_is_an_error_not_a_degraded_mode(
        self, make_engine: MakeEngine, fetcher: FakeFetcher
    ) -> None:
        archives, routes = fake_archives(deno=b"FAIL: cannot execute")
        for url, data in routes.items():
            fetcher.add(url, data)
        engine = make_engine(pinned=lambda _t: archives)

        engine.install()

        info = engine.info()
        assert info.status == EngineStatus.ERROR
        assert info.message is not None and "deno" in info.message
        assert info.versions == {}

    def test_network_failure_is_an_error_and_install_retry_reaches_ready(
        self, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        ffmpeg_url = "https://example.test/ffmpeg.zip"
        fetcher.failing.add(ffmpeg_url)

        engine.install()

        assert engine.info().status == EngineStatus.ERROR
        assert "conexión" in (engine.info().message or "")

        fetcher.failing.clear()
        assert engine.start_install() is True

        assert engine.info().status == EngineStatus.READY
        assert engine.info().message is None

    def test_retry_does_not_download_finished_components_again(
        self, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        fetcher.failing.add("https://example.test/ffprobe.zip")
        engine.install()

        fetcher.failing.clear()
        engine.install()

        assert fetcher.downloads_of("deno.zip") == 1
        assert fetcher.downloads_of("/ffmpeg.zip") == 1
        assert fetcher.downloads_of("ffprobe.zip") == 2
        assert fetcher.downloads_of("releases/latest") == 1

    def test_unreachable_release_api_is_an_error(
        self, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        fetcher.routes.clear()

        engine.install()

        assert engine.info().status == EngineStatus.ERROR
        assert "yt-dlp" in (engine.info().message or "")

    def test_restart_with_an_installed_engine_only_verifies_it(
        self, engine: EngineManager, make_engine: MakeEngine, fetcher: FakeFetcher
    ) -> None:
        engine.install()
        fetcher.requests.clear()

        restarted = make_engine()
        restarted.install()

        assert restarted.info().status == EngineStatus.READY
        assert restarted.info().versions["yt-dlp"] == "2026.10.26"
        assert fetcher.requests == []

    def test_a_new_pinned_version_reinstalls_only_that_archive(
        self, engine: EngineManager, make_engine: MakeEngine, fetcher: FakeFetcher
    ) -> None:
        engine.install()
        fetcher.requests.clear()
        archives, routes = fake_archives(deno=b"deno 2.9.9 (stable)\n")
        for url, data in routes.items():
            fetcher.add(url, data)

        upgraded = make_engine(pinned=lambda _t: archives)
        upgraded.install()

        assert upgraded.info().versions["deno"] == "2.9.9"
        assert fetcher.requests == ["https://example.test/deno.zip"]

    def test_unsupported_platform_is_an_error(self, make_engine: MakeEngine) -> None:
        engine = make_engine(target=None)
        engine.target = None

        engine.install()

        assert engine.info().status == EngineStatus.ERROR
        assert "soportado" in (engine.info().message or "")

    def test_start_installs_in_the_background_without_blocking(
        self, make_engine: MakeEngine
    ) -> None:
        queued: list[Callable[[], None]] = []
        engine = make_engine(spawn=queued.append)

        engine.start()

        assert engine.info().status == EngineStatus.MISSING  # nothing ran yet
        queued.pop()()
        assert engine.info().status == EngineStatus.READY

    def test_install_is_a_no_op_when_ready(
        self, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        engine.install()
        fetcher.requests.clear()

        assert engine.start_install() is False
        assert fetcher.requests == []


class TestLeftovers:
    def test_old_new_and_tmp_files_are_deleted_at_startup(
        self, engine: EngineManager, data_dir: Path
    ) -> None:
        directory = bin_dir(data_dir)
        directory.mkdir()
        for name in ("yt-dlp.old", "ffmpeg.new", "partial.tmp"):
            (directory / name).write_bytes(b"leftover")
        (directory / "keep.txt").write_text("not ours to delete")

        engine.install()

        assert sorted(p.name for p in directory.iterdir()) == [
            "deno",
            "ffmpeg",
            "ffprobe",
            "keep.txt",
            "yt-dlp",
        ]

    def test_old_and_new_folders_are_deleted_but_not_the_installed_one(
        self, make_engine: MakeEngine, data_dir: Path
    ) -> None:
        directory = bin_dir(data_dir)
        for name in ("yt-dlp-dist.old", "yt-dlp-dist.new"):
            (directory / name / "_internal").mkdir(parents=True)
            (directory / name / "_internal" / "lib.so").write_bytes(b"leftover")
        (directory / "yt-dlp-dist" / "_internal").mkdir(parents=True)

        make_engine(target="macos-arm64").cleanup_leftovers()

        assert sorted(p.name for p in directory.iterdir()) == ["yt-dlp-dist"]


class TestUnpackagedYtdlp:
    """macOS and Windows: yt-dlp is the unpackaged zip, installed as the folder `yt-dlp-dist/`."""

    @pytest.fixture(params=["macos-arm64", "windows-x64"])
    def target(self, request: pytest.FixtureRequest, fetcher: FakeFetcher) -> str:
        fetcher.publish_ytdlp("2026.10.26", YTDLP_OLD, target=request.param)
        return request.param

    @pytest.fixture
    def dist(self, data_dir: Path) -> Path:
        return bin_dir(data_dir) / "yt-dlp-dist"

    def exe(self, target: str) -> str:
        return sources.ytdlp_executable(target)

    def legacy(self, target: str, data_dir: Path) -> Path:
        """The single binary an earlier version installed."""
        return bin_dir(data_dir) / ("yt-dlp.exe" if target == "windows-x64" else "yt-dlp")

    def test_installs_the_folder_verified_by_the_zip_hash(
        self,
        make_engine: MakeEngine,
        target: str,
        dist: Path,
        data_dir: Path,
        runner: FakeRunner,
    ) -> None:
        engine = make_engine(target=target)

        engine.install()

        assert engine.info().status == EngineStatus.READY, engine.info().message
        assert engine.info().versions["yt-dlp"] == "2026.10.26"
        assert engine.binary_path("yt-dlp") == dist / self.exe(target)
        assert (dist / self.exe(target)).read_bytes() == YTDLP_OLD
        assert (dist / "_internal" / "base_library.zip").read_bytes() == b"lib"
        assert sorted(p.name for p in bin_dir(data_dir).iterdir() if p.name.startswith("yt")) == [
            "yt-dlp-dist"
        ]
        entry = manifest(data_dir)["binaries"]["yt-dlp"]
        assert entry["archiveSha256"] == sha256(ytdlp_zip(YTDLP_OLD, target))
        assert entry["sha256"] == sha256(YTDLP_OLD)
        assert entry["version"] == "2026.10.26"
        assert str(dist / self.exe(target)) in [call[0] for call in runner.calls]

    def test_restores_the_execute_bits_of_the_zip_on_macos(
        self, make_engine: MakeEngine, fetcher: FakeFetcher, dist: Path
    ) -> None:
        fetcher.publish_ytdlp("2026.10.26", YTDLP_OLD, target="macos-arm64")
        engine = make_engine(target="macos-arm64")

        engine.install()

        assert engine.info().status == EngineStatus.READY, engine.info().message
        assert os.access(dist / "yt-dlp_macos", os.X_OK)
        assert os.access(dist / "_internal" / "libpython.dylib", os.X_OK)
        assert not os.access(dist / "_internal" / "base_library.zip", os.X_OK)

    def test_the_version_check_gets_time_for_the_slow_first_run(
        self, make_engine: MakeEngine, target: str, runner: FakeRunner
    ) -> None:
        make_engine(target=target).install()

        assert runner.timeouts
        assert min(runner.timeouts) >= 60

    @pytest.mark.parametrize(
        "name", ["../evil.txt", "_internal/../../evil.txt", "/tmp/evil.txt", "..\\evil.txt"]
    )
    def test_an_entry_outside_the_folder_fails_the_install_and_leaves_nothing(
        self,
        make_engine: MakeEngine,
        fetcher: FakeFetcher,
        target: str,
        dist: Path,
        data_dir: Path,
        name: str,
    ) -> None:
        bad = make_zip({self.exe(target): YTDLP_OLD, name: b"pwned"})
        fetcher.publish_ytdlp("2026.10.26", YTDLP_OLD, target=target, archive=bad)
        engine = make_engine(target=target)

        engine.install()

        assert engine.info().status == EngineStatus.ERROR
        assert "ruta no permitida" in (engine.info().message or "")
        assert not dist.exists()
        assert not (data_dir / "evil.txt").exists()
        assert not (bin_dir(data_dir) / "evil.txt").exists()
        assert [p.name for p in bin_dir(data_dir).iterdir() if p.name.startswith("yt")] == []
        assert [p.name for p in bin_dir(data_dir).iterdir() if p.suffix in (".tmp", ".new")] == []

    def test_a_zip_hash_not_in_sha2_256sums_installs_nothing(
        self, make_engine: MakeEngine, fetcher: FakeFetcher, target: str, dist: Path
    ) -> None:
        fetcher.publish_ytdlp("2026.10.26", YTDLP_OLD, target=target, sums_sha256="f" * 64)
        engine = make_engine(target=target)

        engine.install()

        assert engine.info().status == EngineStatus.ERROR
        assert not dist.exists()

    def test_a_zip_without_the_executable_is_an_error(
        self, make_engine: MakeEngine, fetcher: FakeFetcher, target: str, dist: Path
    ) -> None:
        empty = make_zip({"_internal/base_library.zip": b"lib"})
        fetcher.publish_ytdlp("2026.10.26", YTDLP_OLD, target=target, archive=empty)
        engine = make_engine(target=target)

        engine.install()

        assert engine.info().status == EngineStatus.ERROR
        assert self.exe(target) in (engine.info().message or "")
        assert not dist.exists()

    def test_restart_with_an_installed_folder_only_verifies_it(
        self, make_engine: MakeEngine, fetcher: FakeFetcher, target: str
    ) -> None:
        make_engine(target=target).install()
        fetcher.requests.clear()

        restarted = make_engine(target=target)
        restarted.install()

        assert restarted.info().status == EngineStatus.READY
        assert fetcher.requests == []

    def test_an_install_with_the_single_binary_is_migrated_and_the_old_file_deleted(
        self,
        make_engine: MakeEngine,
        fetcher: FakeFetcher,
        target: str,
        dist: Path,
        data_dir: Path,
    ) -> None:
        make_engine(target=target).install()
        # What an earlier version left: the single binary, and no `archiveSha256` in engine.json.
        shutil.rmtree(dist)
        legacy = self.legacy(target, data_dir)
        legacy.write_bytes(YTDLP_OLD)
        saved = manifest(data_dir)
        del saved["binaries"]["yt-dlp"]["archiveSha256"]
        (data_dir / "engine.json").write_text(json.dumps(saved))
        fetcher.requests.clear()

        engine = make_engine(target=target)
        engine.install()

        assert engine.info().status == EngineStatus.READY, engine.info().message
        assert not legacy.exists()
        assert (dist / self.exe(target)).read_bytes() == YTDLP_OLD
        assert manifest(data_dir)["binaries"]["yt-dlp"]["archiveSha256"]
        assert fetcher.downloads_of("yt-dlp_") == 1
        assert fetcher.downloads_of("deno.zip") == 0  # the rest of the Engine is kept

    def test_a_locked_old_binary_does_not_fail_the_migration(
        self,
        make_engine: MakeEngine,
        target: str,
        dist: Path,
        data_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        legacy = self.legacy(target, data_dir)
        legacy.parent.mkdir()
        legacy.write_bytes(YTDLP_OLD)
        real_unlink = Path.unlink

        def locked(path: Path, *args: object, **kwargs: object) -> None:
            if path == legacy:
                raise PermissionError("in use by another process")
            real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "unlink", locked)

        engine = make_engine(target=target)
        engine.install()

        assert engine.info().status == EngineStatus.READY, engine.info().message
        assert legacy.exists()
        assert (dist / self.exe(target)).is_file()

    def test_update_swaps_the_whole_folder(
        self,
        make_engine: MakeEngine,
        fetcher: FakeFetcher,
        target: str,
        dist: Path,
        data_dir: Path,
    ) -> None:
        engine = make_engine(target=target)
        engine.install()
        new_zip = ytdlp_zip(YTDLP_NEW, target, {"_internal/extra.bin": b"only in the new one"})
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW, target=target, archive=new_zip)

        assert engine.update_ytdlp() == UpdateOutcome.UPDATED

        assert engine.info().versions["yt-dlp"] == "2026.11.30"
        assert (dist / self.exe(target)).read_bytes() == YTDLP_NEW
        assert (dist / "_internal" / "extra.bin").exists()
        assert sorted(p.name for p in bin_dir(data_dir).iterdir() if p.name.startswith("yt")) == [
            "yt-dlp-dist"
        ]
        entry = manifest(data_dir)["binaries"]["yt-dlp"]
        assert entry == {
            "sha256": sha256(YTDLP_NEW),
            "version": "2026.11.30",
            "archiveSha256": sha256(new_zip),
        }
        # the update must not look like an old install at the next start
        fetcher.requests.clear()
        restarted = make_engine(target=target)
        restarted.install()
        assert restarted.info().versions["yt-dlp"] == "2026.11.30"
        assert fetcher.requests == []

    def test_a_new_version_that_does_not_run_is_rolled_back_to_the_old_folder(
        self,
        make_engine: MakeEngine,
        fetcher: FakeFetcher,
        target: str,
        dist: Path,
        data_dir: Path,
    ) -> None:
        engine = make_engine(target=target)
        engine.install()
        bad = ytdlp_zip(b"FAIL: bad build", target, {"_internal/new-only.bin": b"x"})
        fetcher.publish_ytdlp("2026.11.30", b"", target=target, archive=bad)

        assert engine.update_ytdlp() == UpdateOutcome.FAILED

        assert (dist / self.exe(target)).read_bytes() == YTDLP_OLD
        assert not (dist / "_internal" / "new-only.bin").exists()
        assert sorted(p.name for p in bin_dir(data_dir).iterdir() if p.name.startswith("yt")) == [
            "yt-dlp-dist"
        ]
        assert manifest(data_dir)["binaries"]["yt-dlp"]["version"] == "2026.10.26"
        assert engine.info().status == EngineStatus.READY
        assert engine.info().versions["yt-dlp"] == "2026.10.26"

    def test_an_update_with_an_entry_outside_the_folder_keeps_the_old_one(
        self,
        make_engine: MakeEngine,
        fetcher: FakeFetcher,
        target: str,
        dist: Path,
        data_dir: Path,
    ) -> None:
        engine = make_engine(target=target)
        engine.install()
        bad = make_zip({self.exe(target): YTDLP_NEW, "../evil.txt": b"pwned"})
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW, target=target, archive=bad)

        assert engine.update_ytdlp() == UpdateOutcome.FAILED

        assert (dist / self.exe(target)).read_bytes() == YTDLP_OLD
        assert not (bin_dir(data_dir) / "evil.txt").exists()
        assert [p.name for p in bin_dir(data_dir).iterdir() if p.suffix in (".new", ".old")] == []


class TestExternalBinDir:
    def make_external(self, tmp_path: Path, **contents: bytes) -> Path:
        directory = tmp_path / "mounted"
        directory.mkdir()
        files = {
            "yt-dlp": YTDLP_OLD,
            "ffmpeg": FFMPEG,
            "ffprobe": FFPROBE,
            "deno": DENO,
        } | contents
        for name, data in files.items():
            (directory / name).write_bytes(data)
        return directory

    def test_uses_the_binaries_as_they_are_without_downloading(
        self, make_engine: MakeEngine, fetcher: FakeFetcher, tmp_path: Path, data_dir: Path
    ) -> None:
        directory = self.make_external(tmp_path)
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        engine = make_engine(bin_dir_override=directory)

        engine.install()

        assert engine.info().status == EngineStatus.READY
        assert engine.info().versions["deno"] == "2.9.8"
        assert fetcher.requests == []
        assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
        assert engine.binary_path("deno") == directory / "deno"

    def test_a_missing_binary_is_an_error(self, make_engine: MakeEngine, tmp_path: Path) -> None:
        directory = self.make_external(tmp_path)
        (directory / "deno").unlink()
        engine = make_engine(bin_dir_override=directory)

        engine.install()

        assert engine.info().status == EngineStatus.ERROR
        assert "deno" in (engine.info().message or "")

    def test_a_binary_that_fails_its_version_check_is_an_error(
        self, make_engine: MakeEngine, tmp_path: Path
    ) -> None:
        directory = self.make_external(tmp_path, ffmpeg=b"FAIL: broken")
        engine = make_engine(bin_dir_override=directory)

        engine.install()

        assert engine.info().status == EngineStatus.ERROR

    def test_ytdlp_updates_are_not_available(
        self, make_engine: MakeEngine, tmp_path: Path, fetcher: FakeFetcher
    ) -> None:
        engine = make_engine(bin_dir_override=self.make_external(tmp_path))
        engine.install()

        assert engine.update_ytdlp() == UpdateOutcome.UNSUPPORTED
        assert engine.start_update() == UpdateOutcome.UNSUPPORTED
        assert engine.tick() is None
        assert fetcher.requests == []


class TestUpdate:
    @pytest.fixture
    def ready(self, engine: EngineManager, fetcher: FakeFetcher) -> EngineManager:
        engine.install()
        fetcher.requests.clear()
        return engine

    def test_swaps_the_binary_and_rewrites_engine_json(
        self, ready: EngineManager, fetcher: FakeFetcher, data_dir: Path, clock: FakeClock
    ) -> None:
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)
        clock.advance(hours=30)
        events: list[EngineInfo] = []
        ready.subscribe(events.append)

        outcome = ready.update_ytdlp()

        assert outcome == UpdateOutcome.UPDATED
        assert (bin_dir(data_dir) / "yt-dlp").read_bytes() == YTDLP_NEW
        assert os.access(bin_dir(data_dir) / "yt-dlp", os.X_OK)
        assert not (bin_dir(data_dir) / "yt-dlp.old").exists()
        assert not (bin_dir(data_dir) / "yt-dlp.new").exists()
        info = ready.info()
        assert info.status == EngineStatus.READY
        assert info.versions["yt-dlp"] == "2026.11.30"
        assert info.updating is False
        entry = manifest(data_dir)["binaries"]["yt-dlp"]
        assert entry == {"sha256": sha256(YTDLP_NEW), "version": "2026.11.30"}
        assert manifest(data_dir)["lastUpdateCheck"] == clock().isoformat()
        assert any(e.updating for e in events)
        assert events[-1].updating is False
        assert events[-1].versions["yt-dlp"] == "2026.11.30"

    def test_does_nothing_when_the_latest_release_is_not_newer(
        self, ready: EngineManager, fetcher: FakeFetcher, data_dir: Path, clock: FakeClock
    ) -> None:
        clock.advance(hours=30)

        assert ready.update_ytdlp() == UpdateOutcome.UP_TO_DATE

        assert fetcher.downloads_of("yt-dlp_linux") == 0
        assert (bin_dir(data_dir) / "yt-dlp").read_bytes() == YTDLP_OLD
        assert manifest(data_dir)["lastUpdateCheck"] == clock().isoformat()

    def test_a_download_that_does_not_match_sha2_256sums_keeps_the_old_binary(
        self, ready: EngineManager, fetcher: FakeFetcher, data_dir: Path
    ) -> None:
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW, sums_sha256="e" * 64)

        assert ready.update_ytdlp() == UpdateOutcome.FAILED

        assert (bin_dir(data_dir) / "yt-dlp").read_bytes() == YTDLP_OLD
        assert ready.info().status == EngineStatus.READY
        assert ready.info().update_message is not None
        assert ready.info().versions["yt-dlp"] == "2026.10.26"

    def test_a_new_binary_that_does_not_run_is_rolled_back(
        self, ready: EngineManager, fetcher: FakeFetcher, data_dir: Path
    ) -> None:
        fetcher.publish_ytdlp("2026.11.30", b"FAIL: bad build")

        assert ready.update_ytdlp() == UpdateOutcome.FAILED

        assert (bin_dir(data_dir) / "yt-dlp").read_bytes() == YTDLP_OLD
        assert not (bin_dir(data_dir) / "yt-dlp.old").exists()
        assert manifest(data_dir)["binaries"]["yt-dlp"]["version"] == "2026.10.26"

    def test_a_network_failure_keeps_the_engine_ready(
        self, ready: EngineManager, fetcher: FakeFetcher
    ) -> None:
        fetcher.routes.clear()

        assert ready.update_ytdlp() == UpdateOutcome.FAILED

        assert ready.info().status == EngineStatus.READY
        assert "yt-dlp" in (ready.info().update_message or "")

    def test_is_deferred_while_downloads_run_and_applied_when_the_queue_drains(
        self, make_engine: MakeEngine, fetcher: FakeFetcher
    ) -> None:
        running = [True]
        held: list[str] = []
        engine = make_engine(
            can_update=lambda: not running[0],
            hold_queue=lambda: held.append("hold"),
            release_queue=lambda: held.append("release"),
        )
        engine.install()
        fetcher.requests.clear()
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)

        assert engine.update_ytdlp() == UpdateOutcome.DEFERRED
        assert engine.info().update_pending is True
        assert held == ["hold"]
        assert fetcher.requests == []  # nothing is fetched or swapped while downloads run
        assert engine.start_update() == UpdateOutcome.BUSY  # already pending

        running[0] = False
        engine.apply_pending_update()  # what the Queue calls when it drains

        assert engine.info().versions["yt-dlp"] == "2026.11.30"
        assert engine.info().update_pending is False
        assert held == ["hold", "release"]
        assert engine.start_update() == UpdateOutcome.UPDATED  # claim released: a new one may run

    def test_apply_pending_update_does_nothing_without_a_pending_update(
        self, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        engine.install()
        fetcher.requests.clear()

        engine.apply_pending_update()

        assert fetcher.requests == []

    def test_a_failed_update_still_releases_the_queue(
        self, make_engine: MakeEngine, fetcher: FakeFetcher
    ) -> None:
        released: list[str] = []
        engine = make_engine(release_queue=lambda: released.append("release"))
        engine.install()
        fetcher.routes.clear()

        assert engine.update_ytdlp() == UpdateOutcome.FAILED

        assert released == ["release"]
        assert engine.info().update_pending is False

    def test_pending_is_visible_to_listeners_and_cleared_when_the_swap_starts(
        self, make_engine: MakeEngine, fetcher: FakeFetcher
    ) -> None:
        running = [True]
        engine = make_engine(can_update=lambda: not running[0])
        engine.install()
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)
        events: list[EngineInfo] = []
        engine.subscribe(events.append)

        engine.start_update()
        running[0] = False
        engine.apply_pending_update()

        states = [(e.update_pending, e.updating) for e in events]
        assert states[0] == (True, False)
        assert (False, True) in states
        assert states[-1] == (False, False)

    def test_requires_a_ready_engine(self, engine: EngineManager) -> None:
        assert engine.update_ytdlp() == UpdateOutcome.NOT_READY
        assert engine.start_update() == UpdateOutcome.NOT_READY

    def test_manual_update_runs_in_the_background(
        self, make_engine: MakeEngine, fetcher: FakeFetcher
    ) -> None:
        queued: list[Callable[[], None]] = []
        engine = make_engine(spawn=queued.append)
        engine.install()
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)

        assert engine.start_update() == UpdateOutcome.UPDATED
        assert engine.info().versions["yt-dlp"] == "2026.10.26"
        queued.pop()()

        assert engine.info().versions["yt-dlp"] == "2026.11.30"


class TestScheduling:
    @pytest.fixture
    def ready(self, engine: EngineManager, fetcher: FakeFetcher) -> EngineManager:
        engine.install()
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)
        fetcher.requests.clear()
        return engine

    def test_no_check_before_24_hours(
        self, ready: EngineManager, fetcher: FakeFetcher, clock: FakeClock
    ) -> None:
        clock.advance(hours=23, minutes=59)

        assert ready.tick() is None
        assert fetcher.requests == []

    def test_checks_and_updates_once_24_hours_have_passed(
        self, ready: EngineManager, fetcher: FakeFetcher, clock: FakeClock
    ) -> None:
        clock.advance(hours=24)

        assert ready.tick() == UpdateOutcome.UPDATED
        assert ready.info().versions["yt-dlp"] == "2026.11.30"

        # the check restarts the 24 h window
        fetcher.requests.clear()
        clock.advance(hours=23)
        assert ready.tick() is None
        clock.advance(hours=1)
        assert ready.tick() == UpdateOutcome.UP_TO_DATE

    def test_a_due_check_with_downloads_running_stays_pending_until_the_queue_drains(
        self, make_engine: MakeEngine, fetcher: FakeFetcher, clock: FakeClock
    ) -> None:
        running = [True]
        engine = make_engine(can_update=lambda: not running[0])
        engine.install()
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)
        clock.advance(hours=25)

        assert engine.tick() == UpdateOutcome.DEFERRED
        assert engine.info().update_pending is True
        assert engine.tick() == UpdateOutcome.BUSY  # the next hourly tick does not pile up

        running[0] = False
        engine.apply_pending_update()

        assert engine.info().versions["yt-dlp"] == "2026.11.30"

    def test_start_updates_when_the_last_check_is_older_than_24_hours(
        self, engine: EngineManager, make_engine: MakeEngine, fetcher: FakeFetcher, clock: FakeClock
    ) -> None:
        engine.install()
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)
        clock.advance(hours=48)

        restarted = make_engine()
        restarted.start()

        assert restarted.info().versions["yt-dlp"] == "2026.11.30"

    def test_start_does_not_check_again_within_24_hours(
        self, engine: EngineManager, make_engine: MakeEngine, fetcher: FakeFetcher, clock: FakeClock
    ) -> None:
        engine.install()
        fetcher.publish_ytdlp("2026.11.30", YTDLP_NEW)
        clock.advance(hours=2)

        restarted = make_engine()
        restarted.start()

        assert restarted.info().versions["yt-dlp"] == "2026.10.26"

    def test_run_periodic_ticks_after_every_sleep(self, ready: EngineManager) -> None:
        ticks: list[int] = []
        ready.tick = lambda: ticks.append(1)  # type: ignore[method-assign]
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            if len(sleeps) == 3:
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run_periodic(ready, interval=3600, sleep=fake_sleep))

        assert sleeps == [3600, 3600, 3600]
        assert len(ticks) == 2


def test_runner_is_called_with_the_version_flag_of_each_binary(
    engine: EngineManager, runner: FakeRunner, data_dir: Path
) -> None:
    engine.install()

    flags = {Path(call[0]).name: call[1] for call in runner.calls}
    assert flags == {
        "yt-dlp": "--version",
        "ffmpeg": "-version",
        "ffprobe": "-version",
        "deno": "--version",
    }


class TestLatestYtdlpRedirect:
    def test_malformed_location_is_a_clear_spanish_error(
        self, engine: EngineManager, fetcher: FakeFetcher
    ) -> None:
        fetcher.add(sources.YTDLP_LATEST_PAGE, b"https://example.test/login")

        engine.install()

        assert engine.info().status == EngineStatus.ERROR
        message = engine.info().message or ""
        assert "No se pudo consultar la última versión de yt-dlp" in message
        assert "redirección inesperada" in message

    def test_parse_release_tag(self) -> None:
        assert sources.parse_release_tag(f"{sources.YTDLP_RELEASES_TAG}/2026.11.30") == "2026.11.30"
