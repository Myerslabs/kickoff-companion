"""Final pass (security-4): headers on every answer. The app is never shown inside another site's frame (no
clickjacking of the host's buttons from a page the server computer's browser has open), and browsers never guess a
file's type. Pure ASGI, like the other guards, so the event stream is untouched."""

from __future__ import annotations

from typing import Any

from starlette.datastructures import MutableHeaders

HEADERS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}


class SecurityHeaders:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Any) -> None:
            if message.get("type") == "http.response.start":
                headers = MutableHeaders(raw=message.setdefault("headers", []))
                for name, value in HEADERS.items():
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
