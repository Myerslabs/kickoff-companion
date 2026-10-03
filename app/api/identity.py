"""GET /api/identity: who "we" are, for the page shell (the title, the wordmark, the team colors,
and the names labels use for "us"). No CFBD call of its own: the identity service resolved it at
start, and until then it answers with the TEAM setting as written (`resolved: false`)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.api.envelope import envelope
from app.config import STATIC_DIR
from app.services.icons import SIZES, IconStore, team_colors

log = logging.getLogger("kickoff.identity")

router = APIRouter(tags=["identity"])


@router.get("/api/identity")
async def identity(request: Request) -> Any:
    current = request.app.state.identity.current
    return envelope(current.as_dict(), source="cache")


@router.get("/manifest.webmanifest", include_in_schema=False)
async def manifest(request: Request) -> Any:
    """The home-screen manifest (static/manifest.webmanifest) with this install's name on it."""
    try:
        data = json.loads((STATIC_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as exc:
        log.warning("Manifest unreadable (%s); serving a minimal one", exc)
        data = {"start_url": "/", "display": "standalone", "icons": []}
    who = request.app.state.identity.current
    data["name"] = who.title
    data["short_name"] = who.name[:12]
    data["description"] = f"Second screen for {who.school} football."
    ground, _ = team_colors(who.color, who.alt_color)
    data["background_color"] = data["theme_color"] = f"#{ground[0]:02x}{ground[1]:02x}{ground[2]:02x}"
    data["icons"] = [
        {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ]
    return JSONResponse(data, media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


@router.get("/icons/{name}", include_in_schema=False)
async def icon(name: str, request: Request) -> Any:
    """The home-screen icon in the team's colors (drawn once, then kept under data/icons/). An unknown
    name is 404; a drawing that fails falls back to the neutral icon in static/icons/."""
    if name not in SIZES:
        return Response(status_code=404)
    who = request.app.state.identity.current
    store = IconStore(request.app.state.settings.data_dir)
    try:
        data = await asyncio.to_thread(store.get, name, who.color, who.alt_color)
    except (OSError, ValueError, KeyError) as exc:
        log.warning("Team icon %s failed (%s); serving the neutral one", name, exc)
        return FileResponse(STATIC_DIR / "icons" / name, media_type="image/png")
    return Response(data, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
