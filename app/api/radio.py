"""GET /api/radio/sources: the radio sources (X4), in order, with a stable id per entry for the browser to
remember. Public release Phase 5b: RADIO_SOURCES in .env, then the stations added in Settings, then the
repo's station list for my primary teams (app/services/stations.py). `help` carries, for each primary team
with no station, links to find its broadcast and the GitHub form to request it. No secrets live here."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope
from app.services import stations, teamset

router = APIRouter(tags=["radio"])

AUDIO_NOTE = "Audio plays from the station's own player or stream and cannot be delayed. The spoiler delay applies to the data panels only."


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "source"


def source_id(index: int, name: str) -> str:
    """The stable id of the source at a 0-based index. The player saves it as the owner's choice and the
    Settings picker matches on it, so both routes build it here."""
    return f"{index + 1}-{_slug(name)}"


def all_sources(request: Request) -> list[dict[str, Any]]:
    """Every source with its id, in order: .env, Settings, the repo list (my primary teams only)."""
    state = request.app.state
    prefs = getattr(state, "prefs", None)
    saved = list(getattr(getattr(prefs, "prefs", None), "radioStations", []) or [])
    chosen = teamset.current(state.settings, prefs, state.cfbd)
    rows = stations.combined(state.settings, saved, list(chosen.primaries))
    return [{"id": source_id(index, row["name"]), **row} for index, row in enumerate(rows)]


def radio_help(request: Request, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each primary team without a station: where to find its broadcast and how to ask for it."""
    state = request.app.state
    chosen = teamset.current(state.settings, getattr(state, "prefs", None), state.cfbd)
    covered = {s["team"].lower() for s in sources if isinstance(s.get("team"), str)}
    if any(s["origin"] == "env" for s in sources):
        covered.add(chosen.home.lower())  # this install's own RADIO_SOURCES are the home team's
    identity = getattr(getattr(state, "identity", None), "current", None)
    out = []
    for school in chosen.primaries:
        if not school or school.lower() in covered:
            continue
        mascot = identity.mascot if identity is not None and school == chosen.home else None
        out.append({"school": school, "search": stations.search_links(school, mascot), "requestUrl": stations.request_url(school)})
    return out


@router.get("/api/radio/sources")
async def radio_sources(request: Request) -> Any:
    sources = all_sources(request)
    return envelope({"sources": sources, "note": AUDIO_NOTE, "help": radio_help(request, sources), "requestUrl": stations.request_url(None)}, source="live")
