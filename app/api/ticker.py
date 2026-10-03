"""GET /api/ticker?delay=N: the scoreboard ticker (L10). Our game's entry follows the delay."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.players import respond
from app.services.ticker import TickerService

router = APIRouter(tags=["ticker"])


@router.get("/api/ticker")
async def ticker(request: Request, delay: float = Query(0, ge=0, le=120)) -> Any:
    service: TickerService = request.app.state.ticker
    return respond(await service.ticker(float(delay)))
