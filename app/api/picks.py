"""Picks of the week (FEAT-2): GET /api/picks, this week's games with an FBS team in their four kickoff windows, Power and
Group of 5, the market's line and Claude Code's pick for each (app/services/picks.py). No CFBD call of its own beyond the
week's games, lines and TV the Top 25 page caches. Write the picks now: POST /api/writing/picks/<key>/run."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope, error_response
from app.services.notes_task import NotesRunner
from app.services.picks import picks_week

log = logging.getLogger("kickoff.picks")

router = APIRouter(tags=["picks"])


@router.get("/api/picks")
async def picks(request: Request) -> Any:
    state = request.app.state
    try:
        data = await picks_week(state)
    except Exception:  # noqa: BLE001 - the page shows its error panel; logged with the cause
        log.exception("The picks of the week could not be put together")
        return error_response(502, "picks_failed", "The week's games could not be put together; the app tries again.")
    runner = state.writing
    data["running"] = bool(runner.running and runner.job is not None and runner.job.kind == "picks")
    data["commandFound"] = NotesRunner.resolve_command(state.settings.claude_command) is not None
    return envelope(data, source="cache", fetched_at=data.get("writtenAt"))
