"""My teams (public release Phase 5b).

GET /api/myteams        every primary and secondary team: record, national ranks, last and next game.
POST /api/myteams/warm  load the team pages of primaries #2 to #5 in the background (a Tier 2 key);
                        the app sends it once when a device opens it. Answers at once."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope
from app.api.players import respond
from app.services.myteams import MyTeamsService

router = APIRouter(tags=["myteams"])


@router.get("/api/myteams")
async def my_teams(request: Request) -> Any:
    service: MyTeamsService = request.app.state.myteams
    return respond(await service.page())


@router.post("/api/myteams/warm")
async def warm(request: Request) -> Any:
    service: MyTeamsService = request.app.state.myteams
    return envelope(service.warm(), source="live")
