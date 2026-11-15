import ssl

import pytest
import truststore

from app.engine import io
from app.engine.io import UrllibFetcher, default_ssl_context


def test_default_context_trusts_the_os_store():
    assert isinstance(default_ssl_context(), truststore.SSLContext)


def test_fetcher_uses_the_explicit_context_for_every_request(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(request, timeout, context):
        seen.append(context)
        return Response()

    monkeypatch.setattr(io.urllib.request, "urlopen", fake_urlopen)
    context = ssl.create_default_context()
    assert UrllibFetcher(context).get_bytes("https://example.com/x") == b"ok"
    assert seen == [context]
    UrllibFetcher().get_bytes("https://example.com/y")
    assert isinstance(seen[1], truststore.SSLContext)


def test_falls_back_to_certifi_when_truststore_is_missing(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "truststore", None)
    context = default_ssl_context()
    assert isinstance(context, ssl.SSLContext)
    assert not hasattr(context, "_ctx")  # not truststore's wrapper


def test_redirect_location_is_read_without_following_it(monkeypatch):
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/latest":
                self.send_response(302)
                self.send_header("Location", "/releases/tag/2026.11.30")
            else:
                self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        fetcher = UrllibFetcher(ssl.create_default_context())
        assert fetcher.redirect_location(f"{base}/latest") == f"{base}/releases/tag/2026.11.30"
        with pytest.raises(io.FetchError):
            fetcher.redirect_location(f"{base}/other")
    finally:
        server.shutdown()
