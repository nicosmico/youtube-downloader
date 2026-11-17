"""The native folder dialog, per platform (the processes are never really started)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import folder_picker


class FakeRun:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, args: list[str], **kwargs) -> SimpleNamespace:
        self.calls.append((args, kwargs))
        return self.result


def install(monkeypatch: pytest.MonkeyPatch, platform: str, run: FakeRun) -> None:
    monkeypatch.setattr(folder_picker.sys, "platform", platform)
    monkeypatch.setattr(folder_picker.subprocess, "run", run)


class TestMac:
    def test_runs_osascript_at_the_current_folder_and_returns_the_choice(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run = FakeRun(stdout="/Users/ana/Música/\n")
        install(monkeypatch, "darwin", run)

        chosen = folder_picker.choose_folder(tmp_path)

        assert chosen == Path("/Users/ana/Música")
        assert len(run.calls) == 1
        args = run.calls[0][0]
        assert args[:4] == ["osascript", "-e", "activate", "-e"]
        assert args[-1] == (
            'POSIX path of (choose folder with prompt "Elige la carpeta de descargas" '
            f'default location (POSIX file "{tmp_path}"))'
        )

    def test_the_start_path_is_escaped_for_applescript(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        nasty = tmp_path / 'a"b\\c'
        nasty.mkdir()
        run = FakeRun(stdout="/x/\n")
        install(monkeypatch, "darwin", run)

        folder_picker.choose_folder(nasty)

        script = run.calls[0][0][-1]
        assert f'(POSIX file "{tmp_path}/a\\"b\\\\c")' in script

    def test_a_start_folder_that_does_not_exist_is_left_out(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run = FakeRun(stdout="/x/\n")
        install(monkeypatch, "darwin", run)

        folder_picker.choose_folder(tmp_path / "missing")
        folder_picker.choose_folder(None)

        assert [call[0][-1] for call in run.calls] == [
            'POSIX path of (choose folder with prompt "Elige la carpeta de descargas")'
        ] * 2

    def test_canceling_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        run = FakeRun(returncode=1, stderr="execution error: User canceled. (-128)")
        install(monkeypatch, "darwin", run)

        assert folder_picker.choose_folder(None) is None

    def test_another_failure_is_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        run = FakeRun(returncode=1, stderr="execution error: something else (-1700)")
        install(monkeypatch, "darwin", run)

        with pytest.raises(OSError):
            folder_picker.choose_folder(None)


class TestWindows:
    def test_runs_powershell_sta_without_a_console_and_returns_the_choice(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run = FakeRun(stdout="/Users/Ana/Música\r\n")
        install(monkeypatch, "win32", run)
        monkeypatch.setattr(folder_picker.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

        chosen = folder_picker.choose_folder(tmp_path)

        assert chosen == Path("/Users/Ana/Música")
        assert len(run.calls) == 1
        args, kwargs = run.calls[0]
        assert args[:4] == ["powershell", "-NoProfile", "-STA", "-Command"]
        script = args[4]
        assert "FolderBrowserDialog" in script
        assert "ShowNewFolderButton = $true" in script
        assert "TopMost = $true" in script
        assert "ShowDialog($owner)" in script
        assert kwargs["creationflags"] == 0x08000000

    def test_the_start_path_travels_in_the_environment_not_in_the_script(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        nasty = tmp_path / "it's $(x) q"
        nasty.mkdir()
        run = FakeRun(stdout="C:\\x")
        install(monkeypatch, "win32", run)

        folder_picker.choose_folder(nasty)

        args, kwargs = run.calls[0]
        assert kwargs["env"][folder_picker.START_ENV] == str(nasty)
        assert str(nasty) not in args[4]

    def test_without_a_start_folder_the_variable_is_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(folder_picker.START_ENV, "leftover")
        run = FakeRun(stdout="C:\\x")
        install(monkeypatch, "win32", run)

        folder_picker.choose_folder(None)

        assert folder_picker.START_ENV not in run.calls[0][1]["env"]

    def test_printing_nothing_means_canceled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, "win32", FakeRun(stdout=""))

        assert folder_picker.choose_folder(None) is None

    def test_a_failing_script_is_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, "win32", FakeRun(returncode=1, stderr="boom"))

        with pytest.raises(OSError):
            folder_picker.choose_folder(None)


def test_other_systems_have_no_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun()
    install(monkeypatch, "linux", run)

    with pytest.raises(folder_picker.PickerUnavailable):
        folder_picker.choose_folder(None)

    assert run.calls == []


def test_windows_output_with_a_bom_is_read_as_the_plain_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(stdout="C:\\Users\\Ana\\Música")
    install(monkeypatch, "win32", run)

    folder_picker.choose_folder(None)

    # `utf-8-sig` drops a leading BOM that PowerShell may write before the path.
    assert run.calls[0][1]["encoding"] == "utf-8-sig"
