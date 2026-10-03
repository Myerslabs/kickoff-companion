"""GET /api/matchup?away=&home= (UX-12): two FBS teams side by side from the cached all-FBS answers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import error_response
from app.api.players import respond
from app.services.matchup import NAME_LIMIT, MatchupService, UnknownTeam

router = APIRouter(tags=["matchup"])


def _name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip()
    return name if name and len(name) <= NAME_LIMIT else None


@router.get("/api/matchup")
async def matchup(request: Request, away: str | None = None, home: str | None = None) -> Any:
    service: MatchupService = request.app.state.matchup
    away_name, home_name = _name(away), _name(home)
    if away_name is None or home_name is None:
        return error_response(404, "not_found", "Name two FBS teams: /api/matchup?away=<school>&home=<school>.")
    try:
        result = await service.matchup(away_name, home_name)
    except UnknownTeam as exc:
        return error_response(404, "not_found", str(exc))
    return respond(result)
