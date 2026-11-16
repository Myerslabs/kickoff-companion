"""GET /api/national/{metric} (Phase 16, feature N1): the national list behind a rank chip.

    /api/national/profile:ypp_d?team=Iowa&year=2025&scope=conference&conf=Big%20Ten

The metric key comes from the page payloads (`metric`, `usMetric`, `themMetric`). An unknown or
malformed key, a year other than this season (or last season for the stat profile), an unknown
scope or an over-long team or conference name is a 404 before anything is fetched. The answer is
the usual envelope: 503 only when nothing at all could be loaded."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import error_response
from app.api.players import respond
from app.services.fullstats import CATEGORIES, FullStatsService
from app.services.national import NationalService, validate

router = APIRouter(tags=["national"])


@router.get("/api/national/{metric}")
async def national(metric: str, request: Request, team: str | None = None, year: str | None = None, scope: str | None = None, conf: str | None = None) -> Any:
    service: NationalService = request.app.state.national
    checked = validate(metric, team=team, year=year, scope=scope, conf=conf, season=service.season)
    if isinstance(checked, str):
        return error_response(404, "not_found", checked)
    result = await service.listing(checked)
    if isinstance(result, str):
        return error_response(404, "not_found", result)
    return respond(result)


@router.get("/api/stats/{category}")
async def full_stats(category: str, request: Request) -> Any:
    """ENH-10: one category's full national lists, every FBS team and every qualified player (app/services/fullstats.py)."""
    if category not in CATEGORIES:
        return error_response(404, "not_found", f"No full list called {category[:40]!r}; there are {', '.join(CATEGORIES)}.")
    service: FullStatsService = request.app.state.fullstats
    result = await service.listing(category)
    if result is None:
        return error_response(404, "not_found", "No such list.")
    return respond(result)
