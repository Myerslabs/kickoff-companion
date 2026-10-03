"""Stat grades (public release Phase 7; app/services/grades.py).

GET /api/grades?group=QB&limit=50   the Leaders board: a group's graded FBS players, best first, plus every one
                                    of ours in that group wherever they rank.
GET /api/grades/teams?teams=A,B&top=3  players to watch: each team's best graded players, any position.

The roster and the player card carry the same grades (app/api/players.py)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.envelope import error_response
from app.api.players import respond
from app.services import grades
from app.services.parts import assemble, statuses

router = APIRouter(tags=["grades"])

MAX_TEAMS = 4


def _groups(table: grades.GradeTable) -> list[dict[str, Any]]:
    counts = table.counts()
    return [{"id": g, "name": grades.GROUP_NAMES[g], "count": counts.get(g, 0), "basis": grades.SPECS[g].basis} for g in grades.GRADED]


@router.get("/api/grades")
async def grade_board(request: Request, group: str = Query("QB", max_length=4), limit: int = Query(50, ge=1, le=200)) -> Any:
    chosen = group.strip().upper()
    if chosen not in grades.GRADED:
        return error_response(404, "not_found", f"No graded group {group!r}. Groups: {', '.join(grades.GRADED)}.")
    service: grades.GradeService = request.app.state.grades
    table, parts = await service.table()
    us = request.app.state.settings.team
    rows = table.groups.get(chosen, [])
    shown = [grades.public(r, components=False) for r in rows[:limit]]
    ours = [grades.public(r, components=False) for r in rows if r.get("team") == us]
    beyond = [r for r in ours if r["rank"] is not None and r["rank"] > limit]
    spec = grades.SPECS[chosen]
    data = {
        "group": chosen,
        "groupName": grades.GROUP_NAMES[chosen],
        "basis": spec.basis,
        "volume": {"label": spec.volume_label, "needed": spec.needed},
        "components": [{"key": c.key, "label": c.label, "weight": c.weight} for c in spec.components],
        "groups": _groups(table),
        "rows": shown,
        "beyond": beyond,
        "ours": ours,
        "of": len(rows),
        "team": us,
        "parts": statuses(parts, service.client._clock()),
    }
    return respond(assemble(data, parts))


@router.get("/api/grades/teams")
async def players_to_watch(request: Request, teams: str = Query(..., max_length=300), top: int = Query(3, ge=1, le=10)) -> Any:
    names = [t.strip() for t in teams.split(",") if t.strip()][:MAX_TEAMS]
    if not names:
        return error_response(422, "bad_teams", "Name at least one team.")
    service: grades.GradeService = request.app.state.grades
    table, parts = await service.table()
    out = []
    for name in names:
        graded = sorted((r for rows in table.groups.values() for r in rows if r.get("team") == name), key=lambda r: (-(r["grade"] or 0), r["name"] or ""))
        out.append({"team": name, "players": [grades.public(r, components=False) for r in graded[:top]], "graded": len(graded)})
    data = {"teams": out, "top": top, "parts": statuses(parts, service.client._clock())}
    return respond(assemble(data, parts))


async def attach_roster(request: Request, data: dict[str, Any]) -> list[dict[str, str]]:
    """Each roster row gets its grade (or why it has none). Answers the errors to add, never raises."""
    rows = data.get("players") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    table, parts = await request.app.state.grades.table()
    for row in rows:
        if isinstance(row, dict):
            found = table.get(row.get("playerId"))
            row["grade"] = grades.public(found, components=False) if found else table.for_position(row.get("position"))
    return [{"code": "grades_partial", "message": f"Stat grades: {p.name} did not load ({p.error})."} for p in parts.values() if not p.ok]


async def attach_player(request: Request, data: dict[str, Any], player_id: str) -> list[dict[str, str]]:
    if not isinstance(data, dict):
        return []
    table, parts = await request.app.state.grades.table()
    found = table.get(player_id)
    position = (data.get("player") or {}).get("position") if isinstance(data.get("player"), dict) else None
    data["grade"] = grades.public(found) if found else table.for_position(position)
    return [{"code": "grades_partial", "message": f"Stat grades: {p.name} did not load ({p.error})."} for p in parts.values() if not p.ok]
