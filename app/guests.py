"""Guests are view-only (Phase 18.6). Once a host PIN is set (app/services/host.py), a request that changes something
(POST, PUT, PATCH, DELETE) is refused with 403 unless it comes from a host: the server computer itself, or a device
holding the host cookie. Reading is always open, so a friend on the Wi-Fi sees every page and the live game and can
change nothing. With no PIN set the guard does nothing at all.

A few writes stay open to everyone because they change nothing that is shared: the browser's error report, the host
login itself, and the quiet warm-up a page asks for.

Away from home (group five, owner 2026-10-09): with the awayFromHome preference on, a device that is not the server
computer and holds neither the host cookie nor the join cookie (set by /join/<code>, the link in the invite QR) gets a
short page saying the companion is away, and 403 on /api. The health route, the join route and the icons stay open.

    is_host(scope, access) -> bool
    is_trusted(scope, access) -> bool   the server computer, the host cookie or the join cookie, PIN or not
    GuestGuard(app)             the ASGI middleware; finds the HostAccess at app.state.host_access
"""

from __future__ import annotations

import json
from http.cookies import SimpleCookie
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from app import APP_NAME
from app.netinfo import lan_ip
from app.services.host import COOKIE, JOIN_COOKIE

SAFE = frozenset({"GET", "HEAD", "OPTIONS"})
GUEST_WRITES = frozenset({"/api/client-log", "/api/host/login", "/api/myteams/warm"})
LOOPBACK = ("127.0.0.1", "::1", "localhost")
AWAY_OPEN = ("/join/", "/api/health", "/api/client-log", "/favicon", "/icons/", "/manifest.webmanifest")
AWAY_PAGE = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    f"<title>{APP_NAME} is away from home</title>"
    "<style>body{margin:0;min-height:100vh;display:grid;place-items:center;box-sizing:border-box;padding:24px;background:#1c1f24;color:#e9e7e1;"
    "font:17px/1.5 system-ui,sans-serif}main{max-width:34rem}h1{font-size:28px;line-height:1.15;margin:0 0 12px}p{margin:0 0 10px;color:#c9c6bf}</style></head>"
    f"<body><main><h1>{APP_NAME} is away from home</h1><p>Only devices that scan the host's code can watch along right now.</p>"
    "<p>Ask the host to show the code: it is in the corner of the board, on the Invite friends page, and in Settings.</p></main></body></html>"
)


def on_server_computer(scope: Scope) -> bool:
    client = scope.get("client")
    host = client[0] if client else ""
    return host in LOOPBACK or (bool(host) and host == lan_ip())


def cookie_value(scope: Scope, name: str = COOKIE) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(value.decode("latin-1"))
            except Exception:  # noqa: BLE001 - a malformed Cookie header is just "no cookie"
                return None
            morsel = jar.get(name)
            return morsel.value if morsel else None
    return None


def is_trusted(scope: Scope, access: Any) -> bool:
    """Away from home: the server computer, a device with the host cookie, or one that came in through the code."""
    if on_server_computer(scope):
        return True
    if access is None:
        return False
    return bool(access.valid_token(cookie_value(scope))) or bool(access.valid_join(cookie_value(scope, JOIN_COOKIE)))


def away_open(path: str) -> bool:
    return any(path.startswith(p) for p in AWAY_OPEN)


def away_from_home(scope: Scope) -> bool:
    state = getattr(scope.get("app"), "state", None)
    prefs = getattr(getattr(state, "prefs", None), "prefs", None)
    return bool(getattr(prefs, "awayFromHome", False))


def is_host(scope: Scope, access: Any) -> bool:
    if access is None or not access.pin_set:
        return True
    return on_server_computer(scope) or access.valid_token(cookie_value(scope))


class GuestGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = getattr(scope.get("app"), "state", None)
        access = getattr(state, "host_access", None)
        path = scope.get("path", "")
        if away_from_home(scope) and not away_open(path) and not is_trusted(scope, access):
            await self._away(scope, receive, send)
            return
        if scope.get("method", "GET").upper() in SAFE or path in GUEST_WRITES:
            await self.app(scope, receive, send)
            return
        if is_host(scope, access):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"data": None, "meta": {"stale": False, "source": "live"}, "errors": [{"code": "view_only", "message": "This device is view-only. The host can change things from the server computer, or from a device signed in with the host PIN."}]}).encode()
        await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def _away(self, scope: Scope, receive: Receive, send: Send) -> None:
        """A stranger while away from home: 403 on the API, the short page everywhere else."""
        if scope.get("path", "").startswith("/api/"):
            body = json.dumps({"data": None, "meta": {"stale": False, "source": "live"}, "errors": [{"code": "away_from_home", "message": f"{APP_NAME} is away from home: only devices that scanned the host's code can watch."}]}).encode()
            headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]
            await send({"type": "http.response.start", "status": 403, "headers": headers})
        else:
            body = AWAY_PAGE.encode("utf-8")
            headers = [(b"content-type", b"text/html; charset=utf-8"), (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": body})
