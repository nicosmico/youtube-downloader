"""The real subprocess runner (a stand-in command instead of yt-dlp)."""

from __future__ import annotations

import sys
import time

import pytest

from app.engine.io import ProcessError, ProcessTimeout, run_process

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="uses the Python interpreter")


def test_returns_stdout() -> None:
    assert run_process([sys.executable, "-c", "print('hola')"]).strip() == "hola"


def test_failure_carries_the_whole_stderr() -> None:
    code = "import sys; sys.stderr.write('ERROR: uno\\nERROR: dos\\n'); sys.exit(3)"

    with pytest.raises(ProcessError) as err:
        run_process([sys.executable, "-c", code])

    assert not isinstance(err.value, ProcessTimeout)
    assert str(err.value) == "ERROR: dos"
    assert err.value.stderr == "ERROR: uno\nERROR: dos\n"


def test_a_missing_binary_is_a_process_error() -> None:
    with pytest.raises(ProcessError):
        run_process(["/nonexistent/yt-dlp"])


def test_a_hanging_process_times_out_and_its_children_die() -> None:
    code = (
        "import subprocess, sys, time;"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "time.sleep(60)"
    )
    started = time.monotonic()

    with pytest.raises(ProcessTimeout):
        run_process([sys.executable, "-c", code], timeout=0.5)

    assert time.monotonic() - started < 10
