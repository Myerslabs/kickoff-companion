"""The app's own numbers (FEAT-8): every FBS team's success rate by down and distance, explosive plays, havoc and red-zone
finishing, offense and defense, with national ranks, from the plays the nightly sweep reads (app/services/warm.py).

GET /api/numbers            every team's line, plus how many games the season's numbers hold
GET /api/numbers/{school}   one team's line (404 for a name CFBD's FBS list lacks)

A read of data/season/<year>/numbers.json and the cached FBS list; no CFBD call of its own."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope, error_response
from app.services.numbers import season_table, team_line

router = APIRouter(tags=["numbers"])


async def _table(request: Request) -> tuple[dict[str, Any], set[str]]:
    """The season table over the FBS list the program already caches (an empty list keeps every team the store has)."""
    fbs = {t.school for t in await request.app.state.program.fbs_teams() if isinstance(t.school, str)}
    return season_table(request.app.state.warm.numbers.games(), fbs or None), fbs


@router.get("/api/numbers")
async def numbers(request: Request) -> Any:
    table, _fbs = await _table(request)
    return envelope({**table, "season": request.app.state.settings.season}, source="cache")


@router.get("/api/numbers/{school}")
async def team_numbers(school: str, request: Request) -> Any:
    table, fbs = await _table(request)
    name = school.strip()
    line = team_line(table, name)
    if line is None and fbs and name not in fbs:
        return error_response(404, "unknown_team", f"CFBD does not list {name} among this season's FBS teams.")
    return envelope({"season": request.app.state.settings.season, "team": line, "games": table["games"], "rankOf": table.get("rankOf", {})}, source="cache")
