"""Host file-manager commands, per platform (the processes are never really started)."""

from __future__ import annotations

from pathlib import PureWindowsPath

import pytest

from app import opener


@pytest.fixture
def popen(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    monkeypatch.setattr(opener.subprocess, "Popen", lambda args, **_: calls.append(args))
    return calls


def test_windows_reveal_quotes_only_the_path_so_explorer_selects_names_with_spaces(
    monkeypatch: pytest.MonkeyPatch, popen: list[object]
) -> None:
    monkeypatch.setattr(opener.sys, "platform", "win32")
    path = PureWindowsPath(r"C:\Users\Ana\Downloads\Rex Orange County - Finally.mp3")

    opener.reveal_file(path)  # type: ignore[arg-type]

    assert popen == [r'explorer /select,"C:\Users\Ana\Downloads\Rex Orange County - Finally.mp3"']


def test_windows_open_folder_still_passes_the_folder_as_one_argument(
    monkeypatch: pytest.MonkeyPatch, popen: list[object]
) -> None:
    monkeypatch.setattr(opener.sys, "platform", "win32")

    opener.open_folder(PureWindowsPath(r"C:\Users\Ana\Mis descargas"))  # type: ignore[arg-type]

    assert popen == [["explorer", r"C:\Users\Ana\Mis descargas"]]
