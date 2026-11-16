"""Restart the server from the app (Phase 16 wave 3, owner ask 2026-09-28: "restart the server from the app"), and update it
from GitHub (FEAT-13, owner 2026-10-26).

GET  /api/updates            new commits on GitHub's main, asked of GitHub at most once an hour (force: now)
POST /api/updates/apply      {"confirm": true, "force": false}: bring them in, then restart with the new code
POST /api/server/restart     {"confirm": true, "force": false}: the server shuts down the usual graceful way and comes back
                             (app/restart.py: a fresh process under the tray or start.ps1's window, BUG-22)

Guarded: JSON only (a plain cross-site form can't send it), the Origin check every change goes through
(app/origin_guard.py), a guest can't send either (app/guests.py), at most once a minute, and while our game is under way
both answer 409 unless "force" is set, because the In Game sheet drops for the 10 or 15 seconds a restart takes. Every
restart and update is logged with who asked."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import restart
from app.api.envelope import envelope, error_response
from app.build import STARTED
from app.services.updates import UpdateRefused

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


class UpdateRequest(BaseModel):
    confirm: bool = False
    force: bool = False


@router.get("/api/updates")
async def updates(request: Request, force: bool = False) -> Any:
    """FEAT-13: new commits on GitHub's main? Asked of GitHub at most once an hour (force: now, from Settings)."""
    return envelope(await request.app.state.updates.status(force=force), source="live")


@router.post("/api/updates/apply")
async def apply_update(body: UpdateRequest, request: Request) -> Any:
    """FEAT-13: bring GitHub's new commits in, only on the host's tap, then restart with the new code."""
    if "application/json" not in request.headers.get("content-type", "").lower():
        return error_response(415, "json_only", "Send JSON.")
    if not body.confirm:
        return error_response(422, "confirm", "Confirm the update.")
    now = time.monotonic()
    if _last["at"] and now - _last["at"] < MIN_SECONDS_BETWEEN:
        wait = int(MIN_SECONDS_BETWEEN - (now - _last["at"])) + 1
        return error_response(429, "too_soon", f"The server restarted less than a minute ago. Try again in {wait} s.")
    if _game_under_way(request) and not body.force:
        return error_response(409, "game_under_way", "Our game is under way: the In Game sheet drops while the server restarts with the update.")
    client = request.client.host if request.client else "unknown"
    try:
        result = await request.app.state.updates.apply()
    except UpdateRefused as refused:
        log.warning("Update from GitHub refused for %s: %s", client, refused.message)
        return error_response(refused.status, refused.code, refused.message)
    _last["at"] = now
    log.warning("Update from GitHub asked by %s%s: restarting", client, " during the game" if body.force else "")
    restart.request(f"updated from GitHub, asked by {client}")
    return envelope({**result, "restarting": True, "started": STARTED}, source="live")


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
        return error_response(409, "game_under_way", "Our game is under way: the In Game sheet drops for about 15 seconds while the server restarts.")
    _last["at"] = now
    client = request.client.host if request.client else "unknown"
    log.warning("Restart asked from the app by %s%s", client, " during the game" if body.force else "")
    restart.request(f"asked from the app by {client}")
    return envelope({"restarting": True, "started": STARTED}, source="live")
