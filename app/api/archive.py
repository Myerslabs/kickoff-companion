"""GET /api/archive and /api/archive/{game_id} (X5): the games this app watched to the final."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope, error_response
from app.services.archive import ArchiveService

router = APIRouter(tags=["archive"])


@router.get("/api/archive")
async def archive_list(request: Request) -> Any:
    service: ArchiveService = request.app.state.archive
    return envelope(service.list(), source="live")


@router.get("/api/archive/{game_id}")
async def archive_game(game_id: str, request: Request) -> Any:
    service: ArchiveService = request.app.state.archive
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No archived game with that id.")
    result = await service.game(int(game_id))
    if result is None:
        return error_response(404, "not_found", "The app did not watch that game, so it is not in the archive.")
    return envelope(result["data"], stale=result["stale"], source="cache", errors=result["errors"])
