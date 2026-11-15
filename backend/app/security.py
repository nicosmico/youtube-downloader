"""Local-only protections (spec: "Seguridad local").

* `Host` must be 127.0.0.1:<port> or localhost:<port> (defends against DNS rebinding).
* Mutating methods need `X-Requested-With: youtube-downloader` and, when an `Origin`
  header is present, it must be one of the local origins (defends against CSRF).
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app import APP_ID
from app.errors import error_response

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = "x-requested-with"


class LocalSecurityMiddleware:
    def __init__(self, app: ASGIApp, port: int) -> None:
        self.app = app
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.origins = {f"http://{host}" for host in self.hosts}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        rejection = self._check(scope["method"], headers)
        if rejection is not None:
            await rejection(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _check(self, method: str, headers: Headers):
        if headers.get("host", "").lower() not in self.hosts:
            return error_response(403, "invalid_host", "Host not allowed.")
        if method in MUTATING_METHODS:
            if headers.get(CSRF_HEADER) != APP_ID:
                return error_response(
                    403, "missing_app_header", f"Header X-Requested-With: {APP_ID} is required."
                )
            origin = headers.get("origin")
            if origin is not None and origin.lower() not in self.origins:
                return error_response(403, "invalid_origin", "Origin not allowed.")
        return None
