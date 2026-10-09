"""The Origin check on every route that changes something (Phase 16 wave 3; the 2026-10-07 review: "other state-changing
POST routes have no Origin check yet"). The app has no logins: anyone on the home network may use it. What it must
refuse is a web page from another site, open in a browser on the home network, sending a request to the app behind
its owner's back (writing .env on the welcome page, starting Claude Code, restarting the server).

A browser names the page that sent a request in its Origin header, and on newer browsers says in Sec-Fetch-Site
whether it was the same site. So: a POST, PUT, PATCH or DELETE whose Origin names another host than the one asked,
or whose Sec-Fetch-Site says cross-site, is answered 403 before it reaches a route. A request with no Origin (curl,
the tests, an older browser on a same-site form) passes, as GET and HEAD always do: they change nothing.

    OriginGuard(app)        the ASGI middleware
    same_origin(origin, host, scheme) -> bool
    HostGuard(app, names)   Phase 18.1 (review S2): refuses a request whose Host header is not this computer's own name
    host_allowed(host, names) -> bool

DNS rebinding: a web page on evil.example can have its name re-point at 192.168.0.20 after the page loads, so the
browser then sends the page's requests to this app as "same origin". What gives it away is the Host header, which
still says evil.example. So any Host that is not an address, a name only a local network can resolve, or a name
this install announces is refused, for every method, GET included.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from ipaddress import ip_address
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("kickoff.origin")

SAFE = frozenset({"GET", "HEAD", "OPTIONS"})
DEFAULT_PORTS = {"http": 80, "https": 443}


def _host_port(netloc: str, scheme: str) -> tuple[str, int | None]:
    parts = urlsplit(f"//{netloc}")
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    return host, port if port is not None else DEFAULT_PORTS.get(scheme)


def same_origin(origin: str | None, host: str | None, scheme: str = "http") -> bool:
    """True when the Origin names the host the request was sent to (default ports matched), or there is no Origin."""
    if origin is None:
        return True
    origin = origin.strip()
    if not origin or origin == "null":  # a sandboxed or privacy-stripped page: never trusted to change anything
        return False
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https") or not parts.netloc or not host:
        return False
    return _host_port(parts.netloc, parts.scheme) == _host_port(host, scheme)


class OriginGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "GET").upper() in SAFE:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        origin = headers.get("origin")
        site = headers.get("sec-fetch-site", "").lower()
        if site == "cross-site" or not same_origin(origin, headers.get("host"), scope.get("scheme", "http")):
            log.warning("Refused %s %s from another site (Origin %r, Sec-Fetch-Site %r)", scope.get("method"), scope.get("path"), origin, site or None)
            body = json.dumps({"data": None, "meta": {"stale": False, "source": "live"}, "errors": [{"code": "cross_site", "message": "Refused: the request came from another site's page."}]}).encode()
            await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


LOCAL_SUFFIXES = (".local", ".localdomain", ".localhost", ".lan", ".home.arpa", ".internal")


def host_allowed(host: str | None, names: frozenset[str] | set[str] = frozenset()) -> bool:
    """True when a Host header names this computer the way a home network does: an IP address, localhost, a single
    word (no dot: only a local resolver can answer it), a .local-style name, or a name this install announces."""
    if not host:
        return False
    name, _port = _host_port(host.strip(), "http")
    if not name:
        return False
    try:
        ip_address(name.strip("[]"))
        return True
    except ValueError:
        pass
    name = name.rstrip(".")
    return name in names or "." not in name or name.endswith(LOCAL_SUFFIXES)


class HostGuard:
    def __init__(self, app: ASGIApp, names: Callable[[], set[str]] | None = None) -> None:
        self.app = app
        self.names = names or (lambda: set())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if host_allowed(headers.get("host"), self.names()):
            await self.app(scope, receive, send)
            return
        log.warning("Refused %s %s: Host %r is not a name of this computer", scope.get("method", scope["type"]), scope.get("path"), headers.get("host"))
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps({"data": None, "meta": {"stale": False, "source": "live"}, "errors": [{"code": "bad_host", "message": "Refused: this address is not one of this computer's names."}]}).encode()
        await send({"type": "http.response.start", "status": 421, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
