"""GET /api/games/{game_id}/analytics: win probability (L8) and play value (L9) of one of our games."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import error_response
from app.api.players import respond
from app.services.analytics import AnalyticsService

router = APIRouter(tags=["analytics"])


@router.get("/api/games/{game_id}/analytics")
async def game_analytics(game_id: str, request: Request) -> Any:
    service: AnalyticsService = request.app.state.analytics
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No game with that id.")
    result = await service.game(int(game_id))
    if result is None:
        return error_response(404, "not_found", "That game is not on our schedule.")
    return respond(result)
