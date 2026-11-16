"""The conference page (owner 2026-11-02): GET /api/conference (ours) and GET /api/conference/{name}, one answer with the
six bands from what the app already holds (app/services/conference.py). A name the FBS list lacks is a 404 that lists the
names; an FBS list that could not be read is a 503."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope, error_response
from app.services.conference import conference_page
from app.services.parts import assemble

log = logging.getLogger("kickoff.conference")

router = APIRouter(tags=["conference"])


async def _answer(request: Request, name: str | None) -> Any:
    try:
        data, parts = await conference_page(request.app.state, name)
    except Exception:  # noqa: BLE001 - the page shows its error panel; logged with the cause
        log.exception("The conference page could not be put together")
        return error_response(502, "conference_failed", "The conference page could not be put together; the app tries again.")
    teams = parts.get("teams")
    if data is None:
        if teams is None or not teams.ok:
            return error_response(503, "upstream_unavailable", f"CFBD is not answering and the FBS list is not cached yet. {teams.error if teams is not None else ''}".strip())
        wanted = (name or "").strip() or "That name"
        return error_response(404, "unknown_conference", f"{wanted} is not a conference CFBD lists this season.")
    result = assemble(data, parts)
    return envelope(result.data, stale=result.stale, source=result.source, fetched_at=result.fetched_at, errors=result.errors)


@router.get("/api/conference")
async def our_conference(request: Request) -> Any:
    return await _answer(request, None)


@router.get("/api/conference/{name}")
async def one_conference(request: Request, name: str) -> Any:
    return await _answer(request, name)
