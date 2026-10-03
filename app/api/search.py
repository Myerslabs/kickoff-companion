"""GET /api/search?q=...&wide=1: teams and players by name (Phase 15). Without `wide` it never calls CFBD
beyond the cached team list and rosters; `wide=1` adds CFBD's player search (one call per new term)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.players import respond
from app.services.search import SearchService

router = APIRouter(tags=["search"])


@router.get("/api/search")
async def search(request: Request, q: str = "", wide: int = 0) -> Any:
    service: SearchService = request.app.state.search
    return respond(await service.search(q, wide=bool(wide)))
