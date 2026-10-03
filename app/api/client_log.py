"""Front-end problems reach the server log (added on the game night of 2026-09-26): a JavaScript
error, a rejected promise, or a console.error / console.warn on the tablet used to live only in
that browser's console. static/js/client-log.js sends them here and they land in logs/app.log
under kickoff.client with the device, the page and the build, so a bug seen on the tablet can be
matched to the server's own lines and to the raw recordings.

The route trusts nothing: every field is length-capped, and each device may send at most
RATE_MAX reports per RATE_WINDOW seconds (the rest are counted and summarized once). The same
message from the same device inside REPEAT_SECONDS is counted, not logged again."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, ValidationError

from app.api.envelope import envelope, error_response

router = APIRouter()
log = logging.getLogger("kickoff.client")

RATE_MAX = 30
RATE_WINDOW = 60.0
REPEAT_SECONDS = 300.0
MAX_DEVICES = 50


class ClientReport(BaseModel):
    level: Literal["error", "warn", "info"] = "error"
    kind: str = Field(default="console", max_length=40)  # console, error, rejection
    message: str = Field(max_length=2000)
    stack: str | None = Field(default=None, max_length=4000)
    page: str | None = Field(default=None, max_length=200)
    build: str | None = Field(default=None, max_length=40)
    agent: str | None = Field(default=None, max_length=300)


class _Device:
    __slots__ = ("sent", "dropped", "seen")

    def __init__(self) -> None:
        self.sent: deque[float] = deque()
        self.dropped = 0
        self.seen: dict[str, tuple[float, int]] = {}  # message -> (first logged, repeats since)


_devices: dict[str, _Device] = {}


def _device(address: str) -> _Device:
    if address not in _devices and len(_devices) >= MAX_DEVICES:
        _devices.pop(next(iter(_devices)))
    return _devices.setdefault(address, _Device())


def reset() -> None:
    """Forget the rate state (tests)."""
    _devices.clear()


@router.post("/api/client-log")
async def client_log(request: Request) -> Any:
    try:
        body = await request.json()
    except ValueError:
        return error_response(422, "bad_report", "the report is not JSON")
    try:
        report = ClientReport.model_validate(body)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        return error_response(422, "bad_report", f"{'.'.join(str(p) for p in first.get('loc', ())) or 'report'}: {first.get('msg', 'invalid')}")
    address = request.client.host if request.client else "unknown"
    device = _device(address)
    now = time.monotonic()
    while device.sent and now - device.sent[0] > RATE_WINDOW:
        device.sent.popleft()
    if len(device.sent) >= RATE_MAX:
        device.dropped += 1
        return envelope({"logged": False, "reason": "rate"})
    key = f"{report.kind}|{report.message[:300]}"
    last = device.seen.get(key)
    if last is not None and now - last[0] < REPEAT_SECONDS:
        device.seen[key] = (last[0], last[1] + 1)
        return envelope({"logged": False, "reason": "repeat"})
    repeats = last[1] if last is not None else 0
    device.seen[key] = (now, 0)
    if len(device.seen) > 500:
        device.seen.pop(next(iter(device.seen)))
    device.sent.append(now)
    extra = []
    if repeats:
        extra.append(f"repeated {repeats} more times in the last {int(REPEAT_SECONDS / 60)} min")
    if device.dropped:
        extra.append(f"{device.dropped} reports dropped by the rate limit")
        device.dropped = 0
    line = f"{address} [{report.kind}] page={report.page or '-'} build={report.build or '-'}: {report.message}"
    if extra:
        line += f" ({'; '.join(extra)})"
    if report.stack:
        line += f"\n    stack: {report.stack.strip()[:1500]}"
    if report.agent and address not in _agents_logged:
        _agents_logged.add(address)
        log.info("%s is %s", address, report.agent)
    level = {"error": logging.ERROR, "warn": logging.WARNING, "info": logging.INFO}[report.level]
    log.log(level, "%s", line)
    return envelope({"logged": True})


_agents_logged: set[str] = set()
