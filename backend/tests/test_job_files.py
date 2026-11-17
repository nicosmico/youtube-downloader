from __future__ import annotations

import errno
from pathlib import Path

import pytest

from app.jobs.files import (
    DownloadDirMissing,
    FileMover,
    clean_orphans,
    find_staged_file,
    prepare_staging,
)


def staged(root: Path, name: str, content: bytes = b"x") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_bytes(content)
    return path


class TestMove:
    def test_moves_into_the_destination(self, tmp_path: Path) -> None:
        mover = FileMover(tmp_path / "downloads")
        src = staged(tmp_path / "s", "Video.mp4", b"data")

        final = mover.move(src)

        assert final == tmp_path / "downloads" / "Video.mp4"
        assert final.read_bytes() == b"data"
        assert not src.exists()

    def test_collisions_get_a_numeric_suffix_and_never_overwrite(self, tmp_path: Path) -> None:
        mover = FileMover(tmp_path / "downloads")

        names = [
            mover.move(staged(tmp_path / f"s{i}", "Video.mp4", str(i).encode())).name
            for i in range(3)
        ]

        assert names == ["Video.mp4", "Video (2).mp4", "Video (3).mp4"]
        assert (tmp_path / "downloads" / "Video.mp4").read_bytes() == b"0"

    def test_across_volumes_copies_then_deletes(self, tmp_path: Path) -> None:
        def cross_device(src: Path, dst: Path) -> None:
            raise OSError(errno.EXDEV, "Invalid cross-device link")

        mover = FileMover(tmp_path / "downloads", rename=cross_device)
        src = staged(tmp_path / "s", "Video.mp4", b"big")

        final = mover.move(src)

        assert final.read_bytes() == b"big"
        assert not src.exists()
        assert [p.name for p in final.parent.iterdir()] == ["Video.mp4"]  # no .part left

    def test_across_volumes_still_avoids_collisions(self, tmp_path: Path) -> None:
        def cross_device(src: Path, dst: Path) -> None:
            raise OSError(errno.EXDEV, "x")

        mover = FileMover(tmp_path / "downloads", rename=cross_device)
        mover.move(staged(tmp_path / "a", "V.mp4"))

        assert mover.move(staged(tmp_path / "b", "V.mp4")).name == "V (2).mp4"

    def test_other_errors_are_not_swallowed(self, tmp_path: Path) -> None:
        def denied(src: Path, dst: Path) -> None:
            raise PermissionError(errno.EACCES, "denied")

        mover = FileMover(tmp_path / "downloads", rename=denied)

        with pytest.raises(PermissionError):
            mover.move(staged(tmp_path / "s", "V.mp4"))


class TestMoveIntoAnotherBase:
    def test_a_chosen_base_that_exists_is_used_instead_of_the_default(self, tmp_path: Path) -> None:
        base = tmp_path / "Música"
        base.mkdir()
        mover = FileMover(tmp_path / "downloads")

        final = mover.move(staged(tmp_path / "s", "V.mp4"), base=base)

        assert final == base / "V.mp4"
        assert not (tmp_path / "downloads").exists()

    def test_a_chosen_base_that_is_missing_is_not_created(self, tmp_path: Path) -> None:
        base = tmp_path / "Disco externo"
        mover = FileMover(tmp_path / "downloads")
        src = staged(tmp_path / "s", "V.mp4")

        with pytest.raises(DownloadDirMissing):
            mover.move(src, "Lista", base=base)

        assert not base.exists()
        assert src.exists()

    def test_the_default_base_is_created_even_when_passed_explicitly(self, tmp_path: Path) -> None:
        mover = FileMover(tmp_path / "downloads")

        final = mover.move(staged(tmp_path / "s", "V.mp4"), base=tmp_path / "downloads")

        assert final == tmp_path / "downloads" / "V.mp4"

    def test_playlist_subfolders_are_created_inside_the_chosen_base(self, tmp_path: Path) -> None:
        base = tmp_path / "Música"
        base.mkdir()
        mover = FileMover(tmp_path / "downloads")

        final = mover.move(staged(tmp_path / "s", "V.mp4"), "Lista", "01 - V.mp4", base)

        assert final == base / "Lista" / "01 - V.mp4"


class TestStaging:
    def test_prepare_returns_an_empty_folder(self, tmp_path: Path) -> None:
        old = staged(tmp_path / "job1", "leftover.mp4")

        folder = prepare_staging(tmp_path, "job1")

        assert folder == tmp_path / "job1"
        assert not old.exists()
        assert list(folder.iterdir()) == []

    def test_clean_orphans_removes_every_folder_except_the_kept_ones(self, tmp_path: Path) -> None:
        staged(tmp_path / "a", "x.part")
        staged(tmp_path / "b", "y.mp4")

        assert clean_orphans(tmp_path, keep=frozenset({"b"})) == 1

        assert [p.name for p in tmp_path.iterdir()] == ["b"]

    def test_clean_orphans_tolerates_a_missing_root(self, tmp_path: Path) -> None:
        assert clean_orphans(tmp_path / "nope") == 0

    def test_finds_the_reported_file_or_the_only_one(self, tmp_path: Path) -> None:
        folder = tmp_path / "j"
        a = staged(folder, "A.mp4")
        staged(folder, "B.f140.m4a.part")

        assert find_staged_file(folder, str(a)) == a
        assert find_staged_file(folder, None) == a
        assert find_staged_file(folder, "/etc/passwd") == a  # outside staging: ignored

    def test_gives_up_when_it_is_ambiguous_or_empty(self, tmp_path: Path) -> None:
        folder = tmp_path / "j"
        folder.mkdir()
        assert find_staged_file(folder, None) is None
        staged(folder, "A.mp4")
        staged(folder, "B.mp4")
        assert find_staged_file(folder, None) is None
