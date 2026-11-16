"""GET /media/headshot/{player_id}: a cached PNG, or a 404 the UI turns into the number badge.
GET /media/logo/{team_id}?v=light|dark (Phase 16): a cached team logo, or a 404 the UI turns into
the team's mono tile."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response

from app.services.logos import LogoStore
from app.services.media import HeadshotStore
from app.services.paper_art import ArtStore

router = APIRouter(tags=["media"])

HIT_CACHE = "public, max-age=604800"  # a week: the file never changes once stored
LOGO_CACHE = "public, max-age=2592000"  # thirty days: a school's logo changes once in years
MISS_CACHE = "public, max-age=86400"  # a day: a missing photo rarely appears mid-season
ERROR_CACHE = "no-cache"  # an upstream hiccup should be retried on the next view


@router.get("/media/headshot/{player_id}", include_in_schema=False)
async def headshot(player_id: str, request: Request) -> Response:
    store: HeadshotStore = request.app.state.headshots
    result = await store.get(player_id)
    if result.path is not None:
        return FileResponse(result.path, media_type="image/png", headers={"Cache-Control": HIT_CACHE})
    cache = MISS_CACHE if result.cached or (result.reason or "").startswith("no photo") or "did not return" in (result.reason or "") else ERROR_CACHE
    return Response(status_code=404, headers={"Cache-Control": cache, "X-Headshot": result.reason or "missing"})


PAPER_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}


@router.get("/media/paper/{name}", include_in_schema=False)
async def paper_photo(name: str, request: Request) -> Response:
    """FEAT-14: a copied story's lead photo, saved once under the story's id; never fetched from the publisher here."""
    path = request.app.state.articles.store.photo_path(name)
    if path is None:
        return Response(status_code=404, headers={"Cache-Control": MISS_CACHE})
    return FileResponse(path, media_type=PAPER_TYPES.get(name.rsplit(".", 1)[-1], "application/octet-stream"), headers={"Cache-Control": LOGO_CACHE})


ART_HEADERS = {"Cache-Control": "public, max-age=3600", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"}


@router.get("/media/paper-art/{name}", include_in_schema=False)
async def paper_art(name: str, request: Request, season: int | None = None) -> Response:
    """FEAT-14 wave 4: Claude's drawing for a story, cleaned when it was saved; served so that nothing in it could load or run.
    ?season=<year>: a past season's drawing (rollover R3), read from that season's folder."""
    sid = name[:-4] if name.endswith(".svg") else ""
    settings = request.app.state.settings
    past = season if isinstance(season, int) and 2000 <= season <= 2999 and season != settings.season else None
    art = ArtStore(settings.data_dir, past) if past is not None else request.app.state.rankedweek.art
    path = art.path(sid)
    if path is None:
        return Response(status_code=404, headers={"Cache-Control": MISS_CACHE})
    return FileResponse(path, media_type="image/svg+xml", headers=ART_HEADERS)


@router.get("/media/logo/{team_id}", include_in_schema=False)
async def logo(team_id: str, request: Request, v: str = "light") -> Response:
    store: LogoStore = request.app.state.logos
    result = await store.get(team_id, v)
    if result.path is not None:
        return FileResponse(result.path, media_type="image/png", headers={"Cache-Control": LOGO_CACHE})
    reason = result.reason or "missing"
    cache = MISS_CACHE if result.cached or reason.startswith("no logo") or "did not return" in reason else ERROR_CACHE
    return Response(status_code=404, headers={"Cache-Control": cache, "X-Logo": reason})
