"""GET /api/archive and /api/archive/{game_id} (X5): the games this app watched to the final. /api/archive/latest is the
newest of them by kickoff (the menu's "The last game watched", owner 2026-10-28: every band its own flyout and page)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope, error_response
from app.services.archive import ArchiveService

router = APIRouter(tags=["archive"])


@router.get("/api/archive")
async def archive_list(request: Request) -> Any:
    service: ArchiveService = request.app.state.archive
    return envelope(await service.list(), source="live")


@router.get("/api/archive/{game_id}")
async def archive_game(game_id: str, request: Request) -> Any:
    service: ArchiveService = request.app.state.archive
    if game_id == "latest":
        games = (await service.list()).get("games") or []
        newest = next((g.get("gameId") for g in games if isinstance(g, dict) and isinstance(g.get("gameId"), int)), None)
        if newest is None:
            return error_response(404, "not_found", "The archive holds no games yet: a game is archived at its final.")
        game_id = str(newest)
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No archived game with that id.")
    result = await service.game(int(game_id))
    if result is None:
        return error_response(404, "not_found", "The app did not watch that game, so it is not in the archive.")
    return envelope(result["data"], stale=result["stale"], source="cache", errors=result["errors"])
