"""GET /api/season/overview: the Season tab in one answer (S1 to S5, S10, team-page summary)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from app.api.envelope import envelope, error_response
from app.services import teamset
from app.services.myteams import season_picker
from app.services.season import SeasonService, UnknownTeam

router = APIRouter(tags=["season"])
log = logging.getLogger("kickoff.api.season")


def archived_ids(request: Request) -> set[int]:
    """Game ids with an archive file (Phase 16, audit G3-05 and P-03), so a schedule row or a program
    of a game the app watched to the final can open the Archive; any other game opens its program.
    A file name check only: a damaged file still answers 404 on the Archive route, which says why."""
    folder = getattr(getattr(request.app.state, "archive", None), "folder", None)
    if folder is None:
        return set()
    try:
        return {int(path.stem) for path in folder.glob("*.json") if path.stem.isdigit() and path.is_file()}
    except OSError as exc:
        log.warning("Could not list the archive folder: %s", exc)
        return set()


def mark_archived(rows: Any, archived: set[int]) -> None:
    """Set `archived` on each schedule row (true only for a game with an archive file)."""
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            row["archived"] = row.get("gameId") in archived


@router.get("/api/season/overview")
async def season_overview(request: Request, team: str | None = None) -> Any:
    """The Season page. `team` (Season with My Teams, board 9) names another team the reader follows; a name outside the
    team set answers 404, so a typed address never spends calls on a team nobody follows."""
    service: SeasonService = request.app.state.season
    settings = request.app.state.settings
    teams = await service.fbs_teams()
    chosen = teamset.current(settings, getattr(request.app.state, "prefs", None), service.client, teams.records if teams.ok else None)
    picked = team.strip() if isinstance(team, str) and team.strip() else settings.team
    if picked != settings.team and picked not in chosen.mine():
        return error_response(404, "not_followed", f"{picked} is not one of your teams. Add it under My teams in Settings, then open it here.")
    try:
        result = await service.overview(picked if picked != settings.team else None)
    except UnknownTeam:
        return error_response(404, "unknown_team", f"CFBD does not list {picked} among this season's FBS teams.")
    if result.all_failed:
        first = result.errors[0]["message"] if result.errors else "no part of the overview could be loaded"
        return error_response(503, "upstream_unavailable", f"CFBD is not answering and nothing is cached yet. {first}")
    mark_archived(result.data.get("schedule"), archived_ids(request))
    # freeze wave F4: the facts' dated events, for "On this day" lines under the schedule's rows
    notes = getattr(request.app.state, "season_notes", None)
    facts = notes.facts_for(picked) if notes is not None else None
    result.data["dates"] = [d for d in ((facts or {}).get("dates") or []) if isinstance(d, dict) and isinstance(d.get("date"), str) and isinstance(d.get("event"), str)]
    result.data["picker"] = season_picker(chosen, teams.records, picked)
    return envelope(result.data, stale=result.stale, source=result.source, fetched_at=result.fetched_at, errors=result.errors)
