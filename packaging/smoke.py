"""Smoke test of the packaged app (ticket 14). Standard library only; runs on macOS and Windows.

    python packaging/smoke.py <path to the youtube-downloader executable> [--empty-ca-store]

`--empty-ca-store` points SSL_CERT_FILE / SSL_CERT_DIR at an empty file / directory, so OpenSSL's
default CA lookup cannot rescue the app: the Engine must still install, which proves the app uses
its own explicit trust store (an end-user Mac has no CA bundle for the bundled Python). The video
download is skipped in that mode: yt-dlp's own binary reads the same variables.

Starts the executable with `--no-browser` and temporary DATA_DIR / DOWNLOAD_DIR, then checks:
health, Engine `ready` (real binaries downloaded and verified), "open folder", a real download
and a clean shutdown (process exits, runtime.json removed).

Exit codes: 0 all good; 1 failure; 10 everything passed except the download, which YouTube
refused with its bot check (a known limit of datacenter IPs: never bypassed).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
ENGINE_TIMEOUT = 600
DOWNLOAD_TIMEOUT = 300
BOT_MARKER = "YouTube bloqueó"  # message of the job error for the bot check (jobs/failures.py)
EXIT_BOT_CHECK = 10


class SmokeError(Exception):
    pass


def step(message: str) -> None:
    print(f"==> {message}", flush=True)


def wait_for(description: str, timeout: float, probe, interval: float = 1.0):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value:
                return value
        except SmokeError:
            raise
        except Exception as exc:  # noqa: BLE001 - the probe is retried
            last_error = exc
        time.sleep(interval)
    raise SmokeError(f"Timed out waiting for {description} (last error: {last_error})")


class Client:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.host = f"127.0.0.1:{port}"

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Host", self.host)
        request.add_header("X-Requested-With", "youtube-downloader")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")


def run(exe: Path, work: Path, empty_ca_store: bool = False) -> int:
    data_dir = work / "data"
    download_dir = work / "downloads"
    data_dir.mkdir()
    download_dir.mkdir()
    env = {**os.environ, "DATA_DIR": str(data_dir), "DOWNLOAD_DIR": str(download_dir)}
    env.pop("ENGINE_BIN_DIR", None)
    if empty_ca_store:
        (work / "empty-ca.pem").write_text("")
        (work / "empty-ca-dir").mkdir()
        env["SSL_CERT_FILE"] = str(work / "empty-ca.pem")
        env["SSL_CERT_DIR"] = str(work / "empty-ca-dir")

    step(f"Starting {exe}")
    proc = subprocess.Popen([str(exe), "--no-browser"], env=env)
    runtime_file = data_dir / "runtime.json"
    try:
        info = wait_for(
            "runtime.json", 60, lambda: json.loads(runtime_file.read_text(encoding="utf-8"))
        )
        port = info["port"]
        print(f"runtime.json: {info}", flush=True)
        client = Client(port)

        step("GET /api/health")
        health = wait_for("/api/health", 60, lambda: client.call("GET", "/api/health")[1] or None)
        if health.get("app") != "youtube-downloader":
            raise SmokeError(f"Unexpected health payload: {health}")
        print(health, flush=True)

        step("Serving the Angular build")
        request = urllib.request.Request(client.base + "/")
        request.add_header("Host", client.host)
        with urllib.request.urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", "replace")
        if "<app-root" not in page:
            raise SmokeError("GET / did not return the Angular index.html")

        step(f"Waiting for the Engine to be ready (up to {ENGINE_TIMEOUT}s)")
        last = {"status": None}

        def engine_ready():
            engine = client.call("GET", "/api/system/engine")[1]
            if engine["status"] != last["status"]:
                print(f"engine: {engine['status']} {engine.get('message') or ''}", flush=True)
                last["status"] = engine["status"]
            if engine["status"] == "error":
                raise SmokeError(f"Engine failed to install: {engine}")
            return engine if engine["status"] == "ready" else None

        engine = wait_for("Engine ready", ENGINE_TIMEOUT, engine_ready, interval=2.0)
        print(engine["versions"], flush=True)

        step("POST /api/system/open-downloads")
        status, body = client.call("POST", "/api/system/open-downloads")
        if status != 200:
            raise SmokeError(f"open-downloads answered {status}: {body}")

        bot_blocked = False
        try:
            if empty_ca_store:
                step("Download skipped (--empty-ca-store)")
            else:
                step(f"Downloading {VIDEO_URL}")
                download(client, download_dir)
        except SmokeError as exc:
            if BOT_MARKER in str(exc):
                bot_blocked = True
                print(f"WARNING: download blocked by YouTube's bot check: {exc}", flush=True)
            else:
                raise

        step("POST /api/system/shutdown")
        status, body = client.call("POST", "/api/system/shutdown")
        if status != 202:
            raise SmokeError(f"shutdown answered {status}: {body}")
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise SmokeError("The process did not exit within 30s of the shutdown") from None
        print(f"exit code: {proc.returncode}", flush=True)
        if runtime_file.exists():
            raise SmokeError("runtime.json still exists after shutdown")
        return EXIT_BOT_CHECK if bot_blocked else 0
    except BaseException:
        log = data_dir / "app.log"
        print("\n----- app.log -----", flush=True)
        print(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "(none)")
        raise
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def download(client: Client, download_dir: Path) -> None:
    status, body = client.call(
        "POST", "/api/jobs", {"url": VIDEO_URL, "mode": "video", "quality": "720p"}
    )
    if status != 200:
        raise SmokeError(f"POST /api/jobs answered {status}: {body}")
    job_id = body["jobs"][0]["id"]
    last = {"status": None}

    def finished():
        job = client.call("GET", f"/api/jobs/{job_id}")[1]
        if job["status"] != last["status"]:
            print(f"job: {job['status']} {job.get('progressPercent')}%", flush=True)
            last["status"] = job["status"]
        if job["status"] in ("failed", "canceled", "interrupted"):
            raise SmokeError(f"Job {job['status']}: {job.get('error')}")
        return job if job["status"] == "completed" else None

    job = wait_for("the job to complete", DOWNLOAD_TIMEOUT, finished)
    files = [p for p in download_dir.rglob("*") if p.is_file()]
    print(f"output: {job['outputPath']} / files: {[str(p) for p in files]}", flush=True)
    if not files or not any(p.stat().st_size > 0 for p in files):
        raise SmokeError(f"No downloaded file found in {download_dir}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if len(args) != 1 or flags - {"--empty-ca-store"}:
        print(__doc__)
        return 2
    exe = Path(args[0]).resolve()
    with tempfile.TemporaryDirectory(prefix="ytdl-smoke-") as tmp:
        try:
            return run(exe, Path(tmp), "--empty-ca-store" in flags)
        except SmokeError as exc:
            print(f"SMOKE FAILED: {exc}", flush=True)
            return 1


if __name__ == "__main__":
    sys.exit(main())
