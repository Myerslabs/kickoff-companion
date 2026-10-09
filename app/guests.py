"""Guests are view-only (Phase 18.6). Once a host PIN is set (app/services/host.py), a request that changes something
(POST, PUT, PATCH, DELETE) is refused with 403 unless it comes from a host: the server computer itself, or a device
holding the host cookie. Reading is always open, so a friend on the Wi-Fi sees every page and the live game and can
change nothing. With no PIN set the guard does nothing at all.

A few writes stay open to everyone because they change nothing that is shared: the browser's error report, the host
login itself, and the quiet warm-up a page asks for.

    is_host(scope, access) -> bool
    GuestGuard(app)             the ASGI middleware; finds the HostAccess at app.state.host_access
"""

from __future__ import annotations

import json
from http.cookies import SimpleCookie
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from app.netinfo import lan_ip
from app.services.host import COOKIE

SAFE = frozenset({"GET", "HEAD", "OPTIONS"})
GUEST_WRITES = frozenset({"/api/client-log", "/api/host/login", "/api/myteams/warm"})
LOOPBACK = ("127.0.0.1", "::1", "localhost")


def on_server_computer(scope: Scope) -> bool:
    client = scope.get("client")
    host = client[0] if client else ""
    return host in LOOPBACK or (bool(host) and host == lan_ip())


def cookie_value(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(value.decode("latin-1"))
            except Exception:  # noqa: BLE001 - a malformed Cookie header is just "no cookie"
                return None
            morsel = jar.get(COOKIE)
            return morsel.value if morsel else None
    return None


def is_host(scope: Scope, access: Any) -> bool:
    if access is None or not access.pin_set:
        return True
    return on_server_computer(scope) or access.valid_token(cookie_value(scope))


class GuestGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "GET").upper() in SAFE or scope.get("path") in GUEST_WRITES:
            await self.app(scope, receive, send)
            return
        state = getattr(scope.get("app"), "state", None)
        access = getattr(state, "host_access", None)
        if is_host(scope, access):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"data": None, "meta": {"stale": False, "source": "live"}, "errors": [{"code": "view_only", "message": "This device is view-only. The host can change things from the server computer, or from a device signed in with the host PIN."}]}).encode()
        await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
