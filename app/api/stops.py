"""The season as one line (owner 2026-10-30): `GET /api/stops`, the rail's data and the stop that leads now.

    GET /api/stops   { now, current: {kind, gameId, week, href, label, detail}, items: [...], season, team }

`items` is the line in order: the Preseason Magazine, every week with its three stops (pre, game, post: state, date, href),
the byes, the now marker where today falls, the season book. No CFBD call of its own: the cached schedule and polls, the
locks, the Archive and Claude's recap (app/stops_setup.py)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope, error_response
from app.stops_setup import line_for

log = logging.getLogger("kickoff.api.stops")

router = APIRouter(tags=["stops"])


@router.get("/api/stops")
async def stops(request: Request) -> Any:
    state = request.app.state
    now = state.cfbd._clock()
    try:
        line = await line_for(state, now)
    except Exception as exc:  # noqa: BLE001 - the rail says why instead of a blank strip
        log.warning("The season's line could not be built: %s", exc)
        return error_response(503, "upstream_unavailable", f"The schedule is not available yet. {exc}")
    return envelope(line, source="live", fetched_at=now.isoformat())
