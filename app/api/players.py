"""Leaders (S6 to S9), roster, recruiting, and player card routes. Each answers with the envelope;
503 only when nothing at all could be loaded, 404 for a player nobody knows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope, error_response
from app.services.parts import Assembled
from app.services.players import PlayerService

router = APIRouter(tags=["players"])


def respond(result: Assembled) -> Any:
    if result.all_failed:
        first = result.errors[0]["message"] if result.errors else "nothing could be loaded"
        return error_response(503, "upstream_unavailable", f"CFBD is not answering and nothing is cached yet. {first}")
    return envelope(result.data, stale=result.stale, source=result.source, fetched_at=result.fetched_at, errors=result.errors)


@router.get("/api/season/leaders")
async def leaders(request: Request) -> Any:
    service: PlayerService = request.app.state.players
    return respond(await service.leaders())


@router.get("/api/roster")
async def roster(request: Request) -> Any:
    from app.api.grades import attach_roster  # public release Phase 7: each row's stat grade

    service: PlayerService = request.app.state.players
    result = await service.roster()
    if not result.all_failed:
        result.errors.extend(await attach_roster(request, result.data))
    return respond(result)


@router.get("/api/recruiting")
async def recruiting(request: Request) -> Any:
    service: PlayerService = request.app.state.players
    return respond(await service.recruiting())


@router.get("/api/players/{player_id}")
async def player(player_id: str, request: Request, team: str | None = None) -> Any:
    service: PlayerService = request.app.state.players
    if not player_id.isdigit() or len(player_id) > 12:
        return error_response(404, "not_found", "No player with that id.")
    hint = team.strip()[:80] if isinstance(team, str) and team.strip() else None
    result = await service.player(player_id, hint)
    if result is None:
        return error_response(404, "not_found", "No card for this player: cards cover our team, the next opponent, and this season's players of an FBS team found by search.")
    if not result.all_failed:
        from app.api.grades import attach_player  # public release Phase 7: the stat grade and its parts

        result.errors.extend(await attach_player(request, result.data, player_id))
    return respond(result)
