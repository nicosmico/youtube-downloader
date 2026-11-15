"""Hola mundo del spike 01. Codigo desechable."""
import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
STATIC = BASE / "static"

app = FastAPI()


@app.get("/api/health")
def health():
    return {"app": "youtube-downloader-spike", "version": "0.0.0"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "0")))
    args = p.parse_args()
    host = os.environ.get("BIND_HOST", "127.0.0.1")
    open_browser = os.environ.get("OPEN_BROWSER", "1") != "0" and not args.no_browser
    config = uvicorn.Config(app, host=host, port=args.port, log_config=None)
    server = uvicorn.Server(config)
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}/")).start()
    server.run()


if __name__ == "__main__":
    main()
