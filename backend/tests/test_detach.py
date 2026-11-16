import subprocess
import sys

from app import detach
from app.detach import SERVER_CHILD_ENV, should_detach, spawn_server_child


def test_detaches_only_when_frozen_on_macos_and_not_the_child():
    assert should_detach(frozen=True, platform="darwin", env={})
    assert not should_detach(frozen=False, platform="darwin", env={})
    assert not should_detach(frozen=True, platform="win32", env={})
    assert not should_detach(frozen=True, platform="linux", env={})
    assert not should_detach(frozen=True, platform="darwin", env={SERVER_CHILD_ENV: "1"})


def test_spawn_passes_args_env_and_detaches():
    calls = []

    def fake(cmd, **kwargs):
        calls.append((cmd, kwargs))

    spawn_server_child("/app/exe", ["--no-browser"], {"DATA_DIR": "/d", "X": "y"}, fake)

    ((cmd, kwargs),) = calls
    assert cmd == ["/app/exe", "--no-browser"]
    assert kwargs["env"] == {"DATA_DIR": "/d", "X": "y", SERVER_CHILD_ENV: "1"}
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL


def test_detach_if_needed_does_nothing_when_not_frozen(monkeypatch):
    spawned = []
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(detach, "spawn_server_child", lambda *a: spawned.append(a))
    assert detach.detach_if_needed(["--no-browser"]) is False
    assert spawned == []


def test_detach_if_needed_spawns_when_frozen_on_macos(monkeypatch):
    spawned = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv(SERVER_CHILD_ENV, raising=False)
    monkeypatch.setattr(detach, "spawn_server_child", lambda *a: spawned.append(a[:2]))
    assert detach.detach_if_needed(["--no-browser"]) is True
    assert spawned == [(sys.executable, ["--no-browser"])]


def test_detach_if_needed_does_nothing_in_the_server_child(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv(SERVER_CHILD_ENV, "1")
    assert detach.detach_if_needed([]) is False
