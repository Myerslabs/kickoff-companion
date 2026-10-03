"""GET /api/ratings: every FBS team's SP+, Elo, FPI and talent with ranks (Phase 10)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.players import respond
from app.services.ratings import RatingsService

router = APIRouter(tags=["ratings"])


@router.get("/api/ratings")
async def ratings(request: Request) -> Any:
    service: RatingsService = request.app.state.ratings
    return respond(await service.ratings())
