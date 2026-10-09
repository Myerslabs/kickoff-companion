"""What a request may cost (Phase 18.1, review items S6 to S8). The app has no logins, so anyone on the network could
drain the CFBD quota with searches, restart things in a loop, or send a body big enough to fill memory. Two small
ASGI middlewares close that without touching a route:

    BodyLimit(app, max_bytes)    413 for a body over the ceiling, judged on Content-Length and again while it arrives
    RateLimit(app, rules)        429 for a client that repeats a costly request faster than its rule allows

Rules are (name, method, path, query test, limit, per-seconds). Every client address has its own count, kept in
memory for the length of the window; a restart forgets them, which is fine for a nuisance guard.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("kickoff.limits")

MAX_BODY_BYTES = 2 * 1024 * 1024  # the largest legitimate body is a pasted answer, 400,000 characters


def _refusal(status: int, code: str, message: str, extra: list[tuple[bytes, bytes]] | None = None) -> tuple[dict, dict]:
    body = json.dumps({"data": None, "meta": {"stale": False, "source": "live"}, "errors": [{"code": code, "message": message}]}).encode()
    start = {"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *(extra or [])]}
    return start, {"type": "http.response.body", "body": body}


class BodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "GET").upper() in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        declared = headers.get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await self._refuse(scope, send)
            return
        seen = 0
        started = False

        async def counted() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _TooBig
            return message

        async def tracking(message: Message) -> None:
            nonlocal started
            started = True
            await send(message)

        try:
            await self.app(scope, counted, tracking)
        except _TooBig:
            if not started:
                await self._refuse(scope, send)

    async def _refuse(self, scope: Scope, send: Send) -> None:
        log.warning("Refused %s %s: body over %d bytes", scope.get("method"), scope.get("path"), self.max_bytes)
        start, body = _refusal(413, "too_large", "That request is larger than this app accepts.")
        await send(start)
        await send(body)


class _TooBig(Exception):
    pass


def wide_search(query: str) -> bool:
    """Whether a /api/search query asks for CFBD's player search: any wide value but empty, 0 or false (final pass:
    "wide=2" or "wide=on" cost the same call and used to slip past the rule)."""
    return any(key == "wide" and value.strip().lower() not in ("", "0", "false", "no", "off") for key, value in parse_qsl(query, keep_blank_values=True))


@dataclass(frozen=True)
class Rule:
    name: str
    method: str  # "*" for any
    path: str  # exact path
    limit: int
    seconds: int
    query: Callable[[str], bool] | None = None  # None: every request on the path counts
    prefix: bool = False  # True: `path` is a prefix (a route with an id in it)


DEFAULT_RULES: tuple[Rule, ...] = (
    Rule("wide-search", "GET", "/api/search", 20, 60, query=lambda q: wide_search(q)),  # one CFBD call per new name
    Rule("myteams-warm", "POST", "/api/myteams/warm", 10, 60),
    Rule("demo-switch", "POST", "/api/demo/enter", 3, 60),
    Rule("demo-leave", "POST", "/api/demo/leave", 3, 60),
    Rule("replay", "POST", "/api/live/replay", 10, 60),
    Rule("replay-stop", "DELETE", "/api/live/replay", 10, 60),
    # final pass (S7, S11): routes that cost a CFBD call or an outbound fetch per NEW id; a page's own needs stay far below
    Rule("box-score", "GET", "/api/box/", 30, 60, prefix=True),
    Rule("team-page", "GET", "/api/team/", 30, 60, prefix=True),
    Rule("player-card", "GET", "/api/players/", 60, 60, prefix=True),
    Rule("headshots", "GET", "/media/headshot/", 400, 60, prefix=True),
    Rule("logos", "GET", "/media/logo/", 400, 60, prefix=True),
)


class RateLimit:
    def __init__(self, app: ASGIApp, rules: tuple[Rule, ...] = DEFAULT_RULES, clock: Callable[[], float] = time.monotonic) -> None:
        self.app = app
        self.rules = rules
        self.clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def _rule(self, scope: Scope) -> Rule | None:
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        query = scope.get("query_string", b"").decode("latin-1")
        for rule in self.rules:
            if (rule.path == path or (rule.prefix and path.startswith(rule.path))) and rule.method in ("*", method) and (rule.query is None or rule.query(query)):
                return rule
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        rule = self._rule(scope) if scope["type"] == "http" else None
        if rule is None:
            await self.app(scope, receive, send)
            return
        client = (scope.get("client") or ("?", 0))[0]
        now = self.clock()
        hits = self._hits[(client, rule.name)]
        while hits and now - hits[0] >= rule.seconds:
            hits.popleft()
        if len(hits) >= rule.limit:
            wait = max(1, int(rule.seconds - (now - hits[0])) + 1)
            log.warning("Rate limit %s for %s: %d in %d s", rule.name, client, rule.limit, rule.seconds)
            start, body = _refusal(429, "slow_down", f"Too many of these requests. Try again in {wait} seconds.", [(b"retry-after", str(wait).encode())])
            await send(start)
            await send(body)
            return
        hits.append(now)
        await self.app(scope, receive, send)
