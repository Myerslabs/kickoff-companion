"""Run with Claude (batch 4 part 3, owner 2026-11-19): the menu's row asks whether the page on screen has Claude's writing to
refresh, and starts one run that refreshes it. The host's: a guest is refused. app/refresh_setup.py does the work."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.envelope import envelope, error_response
from app.guests import is_host

router = APIRouter(tags=["refresh"])


class RunRequest(BaseModel):
    route: str = Field(default="", max_length=300)


def _now(request: Request) -> datetime:
    clock = getattr(request.app.state.cfbd, "_clock", None)
    now = clock() if callable(clock) else datetime.now(timezone.utc)
    return now.astimezone(request.app.state.settings.tzinfo)


@router.get("/api/refresh")
async def refresh_check(request: Request, route: str = "") -> Any:
    if not is_host(request.scope, request.app.state.host_access):
        return envelope({"available": False, "running": False, "label": None, "detail": None, "reason": "View only."}, source="live")
    return envelope(await request.app.state.page_refresh.check(route[:300], _now(request)), source="live")


@router.post("/api/refresh/run")
async def refresh_run(body: RunRequest, request: Request) -> Any:
    if not is_host(request.scope, request.app.state.host_access):
        return error_response(403, "view_only", "Only the host can run Claude.")
    try:
        status = await request.app.state.page_refresh.start(body.route, _now(request))
    except Exception as exc:  # noqa: BLE001 - said to the page and the log, never a bare 500
        import logging

        logging.getLogger("kickoff.refresh").exception("Run with Claude could not start for %s", body.route)
        return error_response(503, "not_started", f"The run could not start: {exc.__class__.__name__}: {exc}")
    if status.get("error") and not status.get("running"):
        return error_response(409, "not_started", str(status["error"]))
    return envelope(status, source="live")
