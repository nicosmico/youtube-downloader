"""Launcher: prepares the environment, starts the local server and opens the browser."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import threading
import webbrowser

import uvicorn

from app.config import Settings
from app.logging_setup import configure_logging
from app.main import create_app
from app.runtime import remove_runtime, write_runtime
from app.single_instance import InstanceBusy, Reuse, acquire_instance

log = logging.getLogger("app.launcher")


def bind_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    return sock


def open_browser(port: int) -> None:
    webbrowser.open(f"http://127.0.0.1:{port}/")


def run(settings: Settings) -> int:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(settings.data_dir)

    try:
        outcome = acquire_instance(settings.data_dir)
    except InstanceBusy:
        log.error("Another instance is starting or stuck; giving up.")
        return 1

    if isinstance(outcome, Reuse):
        log.info("Reusing instance on port %s", outcome.info.port)
        if settings.open_browser:
            open_browser(outcome.info.port)
        return 0

    lock = outcome.lock
    sock: socket.socket | None = None
    try:
        sock = bind_socket(settings.bind_host, settings.port)
        port = sock.getsockname()[1]
        server_ref: list[uvicorn.Server] = []

        def request_shutdown() -> None:
            if server_ref:
                server_ref[0].should_exit = True

        app = create_app(data_dir=settings.data_dir, port=port, request_shutdown=request_shutdown)
        # log_config=None: no console under PyInstaller --noconsole; logging goes to a file.
        server = uvicorn.Server(uvicorn.Config(app, log_config=None))
        server_ref.append(server)

        write_runtime(settings.data_dir, port)
        log.info("Serving on %s:%s (data dir %s)", settings.bind_host, port, settings.data_dir)
        if settings.open_browser:
            threading.Thread(target=_open_when_ready, args=(server, port), daemon=True).start()

        # uvicorn swaps in its own SIGINT/SIGTERM handlers while serving, then restores ours and
        # re-raises the signal. Ours must not kill the process, or the cleanup below would not run.
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: request_shutdown())
        server.run(sockets=[sock])
        return 0
    finally:
        remove_runtime(settings.data_dir, only_pid=os.getpid())
        if sock is not None:
            sock.close()
        lock.release()
        log.info("Stopped")


def _open_when_ready(server: uvicorn.Server, port: int) -> None:
    for _ in range(100):
        if server.started:
            open_browser(port)
            return
        threading.Event().wait(0.1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="youtube-downloader")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.no_browser:
        settings = Settings(**{**settings.__dict__, "open_browser": False})
    return run(settings)


if __name__ == "__main__":
    sys.exit(main())
