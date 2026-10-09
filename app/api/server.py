"""Restart the server from the app (Phase 16 wave 3, owner ask 2026-09-28: "restart the server from the app").

POST /api/server/restart   {"confirm": true, "force": false}: the server shuts down the usual graceful way and comes back
                           in the same process and window (app/restart.py, the path the welcome page already uses).

Guarded: JSON only (a plain cross-site form can't send it), the Origin check every change goes through
(app/origin_guard.py), at most once a minute, and while our game is under way it answers 409 unless "force" is set,
because the Live sheet drops for the 10 or 15 seconds the restart takes. Every restart is logged with who asked."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import restart
from app.api.envelope import envelope, error_response
from app.build import STARTED

router = APIRouter(tags=["server"])
log = logging.getLogger("kickoff.restart")

MIN_SECONDS_BETWEEN = 60.0
_last = {"at": 0.0}


class RestartRequest(BaseModel):
    confirm: bool = False
    force: bool = False


def _game_under_way(request: Request) -> bool:
    live = getattr(request.app.state, "live", None)
    try:
        window = (live.status() or {}).get("window") if live is not None else None
    except Exception:  # noqa: BLE001 - the restart must not depend on the engine answering; logged
        log.exception("Live status unreadable while asked to restart")
        return False
    return bool(isinstance(window, dict) and window.get("inProgress"))


@router.get("/api/updates")
async def updates(request: Request, force: bool = False) -> Any:
    """Phase 16 wave 3: is a newer release out? Asked of GitHub at most once a day (force: now, from Settings)."""
    checker = request.app.state.updates
    return envelope(await checker.status(force=force), source="live")


@router.post("/api/server/restart")
async def restart_server(body: RestartRequest, request: Request) -> Any:
    if "application/json" not in request.headers.get("content-type", "").lower():
        return error_response(415, "json_only", "Send JSON.")
    if not body.confirm:
        return error_response(422, "confirm", "Confirm the restart.")
    now = time.monotonic()
    if _last["at"] and now - _last["at"] < MIN_SECONDS_BETWEEN:
        wait = int(MIN_SECONDS_BETWEEN - (now - _last["at"])) + 1
        return error_response(429, "too_soon", f"The server restarted less than a minute ago. Try again in {wait} s.")
    if _game_under_way(request) and not body.force:
        return error_response(409, "game_under_way", "Our game is under way: the Live sheet drops for about 15 seconds while the server restarts.")
    _last["at"] = now
    client = request.client.host if request.client else "unknown"
    log.warning("Restart asked from the app by %s%s", client, " during the game" if body.force else "")
    restart.request(f"asked from the app by {client}")
    return envelope({"restarting": True, "started": STARTED}, source="live")
