"""GET /api/wiki?team=A&team=B&venue=V&coach=Name|School: Wikipedia links for the big headers (Phase 17 #4; Phase 19: coaches). For each team its football
page and its school's page, for the venue its page; what can't be found is a Wikipedia search link, so every link
works. The first lookup of a team takes a few seconds (Wikipedia, one request at a time); after that it is read from
data/wiki/links.json. No CFBD call beyond the cached team list."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from app.api.envelope import envelope
from app.services.program import ProgramService
from app.wiki import WikiClient

router = APIRouter(tags=["wiki"])
MAX_TEAMS = 4
MAX_COACHES = 12


@router.get("/api/wiki")
async def wiki_links(request: Request, team: Annotated[list[str] | None, Query()] = None, venue: str | None = None, coach: Annotated[list[str] | None, Query()] = None) -> Any:
    client: WikiClient = request.app.state.wiki
    program: ProgramService = request.app.state.program
    names = [t.strip() for t in (team or []) if isinstance(t, str) and t.strip()][:MAX_TEAMS]
    meta: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    if names:
        try:
            meta = await program.team_meta()
        except Exception as exc:  # noqa: BLE001 - without mascots the lookups still give search links; logged by the fetcher
            errors.append({"code": "teams_unavailable", "message": f"The team list did not load ({exc.__class__.__name__}); links are searches."})
    teams = {name: await client.team(name, (meta.get(name) or {}).get("mascot")) for name in names}
    venues = {venue.strip(): await client.venue(venue)} if isinstance(venue, str) and venue.strip() else {}
    coaches: dict[str, Any] = {}
    for item in [c for c in (coach or []) if isinstance(c, str) and c.strip()][:MAX_COACHES]:
        person, _bar, school = item.partition("|")
        if person.strip():
            coaches[item.strip()] = await client.coach(person.strip(), school.strip() or None)
    return envelope({"teams": teams, "venues": venues, "coaches": coaches}, source="live", errors=errors)
