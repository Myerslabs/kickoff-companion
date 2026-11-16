"""GET /api/ticker?delay=N: the scoreboard ticker (L10). Our game's entry follows the delay."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.players import respond
from app.services.ticker import TickerService

router = APIRouter(tags=["ticker"])


@router.get("/api/ticker")
async def ticker(request: Request, delay: float = Query(0, ge=0, le=120), mode: str | None = Query(None, max_length=12)) -> Any:
    """?mode=national|mine overrides the ticker setting for this answer (Pick a game on In Game, 2026-11-02)."""
    service: TickerService = request.app.state.ticker
    return respond(await service.ticker(float(delay), mode=mode))
