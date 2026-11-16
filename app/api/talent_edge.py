"""Talent Edge (FEAT-16): the weekly job's table, read back (no CFBD call of its own).

GET /api/talent-edge/{season}/compare?teamA=Florida&teamB=Georgia   both teams and the six unit matchups
GET /api/talent-edge/{season}/{team}                                 one team: every group, the roll-ups, 247 talent

A name the table lacks is a 404 that lists the valid names; a season with no table yet (or one that could not be
read) is a 503 with the last good run and the last failure's reason (spec A.6). Team names are CFBD's, any case."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.api.envelope import envelope
from app.services.talent_edge import ALL_GROUPS, GROUPS, TalentEdgeStore, cross_units, run_state, summary_line, unavailable_words

router = APIRouter(tags=["talent-edge"])

CAVEAT = "Whole-roster talent index. Ratings are each player's 247 composite out of high school; the blue-chip share is of rated players."


def _store(request: Request, season: int) -> TalentEdgeStore:
    stores = getattr(request.app.state, "talent_edge_stores", None)
    if stores is None:
        stores = request.app.state.talent_edge_stores = {}
    if season not in stores:
        stores[season] = TalentEdgeStore(request.app.state.settings.data_dir, season)
    return stores[season]


def _runs(request: Request, season: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    return run_state(request.app.state.settings.data_dir, season)


def _unavailable(request: Request, season: int) -> JSONResponse:
    good, last = _runs(request, season)
    data = {"season": season, "lastGoodRun": good, "lastRun": last}
    return JSONResponse(status_code=503, content=envelope(data, errors=[{"code": "unavailable", "message": unavailable_words(season, good, last)}]))


def _resolve(table: dict[str, Any], name: str) -> str | None:
    teams = table.get("teams") or {}
    wanted = name.strip()
    if wanted in teams:
        return wanted
    folded = wanted.casefold()
    return next((school for school in teams if school.casefold() == folded), None)


def _unknown(table: dict[str, Any], name: str) -> JSONResponse:
    valid = sorted(table.get("teams") or {})
    message = f"{name.strip() or 'That name'} is not one of the {len(valid)} FBS teams in Talent Edge's {table.get('season')} table."
    return JSONResponse(status_code=404, content=envelope({"validTeams": valid}, errors=[{"code": "unknown_team", "message": message}]))


def _team(table: dict[str, Any], school: str) -> dict[str, Any]:
    row = table["teams"][school]
    return {"team": school, **row, "summaryLine": summary_line(row)}


def _head(request: Request, table: dict[str, Any], season: int) -> dict[str, Any]:
    good, _last = _runs(request, season)
    return {
        "season": season,
        "computedWeek": table.get("computedWeek"),
        "computedAt": good.get("finishedAt") if good else None,
        "groupOrder": list(GROUPS),
        "allGroups": list(ALL_GROUPS),
        "rollups": table.get("rollups"),
        "spider": table.get("spider"),
        "caveat": CAVEAT,
    }


@router.get("/api/talent-edge/{season}/compare")
async def compare(request: Request, season: int, teamA: str = Query(min_length=1, max_length=80), teamB: str = Query(min_length=1, max_length=80)) -> Any:  # noqa: N803 - the spec's names
    table = _store(request, season).load()
    if table is None:
        return _unavailable(request, season)
    a, b = _resolve(table, teamA), _resolve(table, teamB)
    if a is None:
        return _unknown(table, teamA)
    if b is None:
        return _unknown(table, teamB)
    first, second = _team(table, a), _team(table, b)
    return envelope({**_head(request, table, season), "a": first, "b": second, "cross_unit": cross_units(first, second)}, source="cache")


@router.get("/api/talent-edge/{season}/{team}")
async def one_team(request: Request, season: int, team: str) -> Any:
    table = _store(request, season).load()
    if table is None:
        return _unavailable(request, season)
    school = _resolve(table, team)
    if school is None:
        return _unknown(table, team)
    return envelope({**_head(request, table, season), **_team(table, school)}, source="cache")
