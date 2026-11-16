"""The Imperialism Map (FEAT-17): the weekly job's season, read back (no CFBD call of its own). Owner 2026-10-30, "Tablet
draws it": the grid goes to the tablet once and every week's owners in one answer, so the slider never waits.

GET /api/imperialism/grid?v=<version>               the lattice, each cell's (col, row) and the states' outlines; kept a year
                                                     when v is the current version
GET /api/imperialism/now                             the page's one answer: this season's every week, the teams with their
                                                     logos and Talent Edge lines, what is still to come, our schedule; with no
                                                     map yet, `available` false and the words why (never an error page)
GET /api/imperialism/{season}/all                    every snapshot's owners, the teams, the events, the records
GET /api/imperialism/{season}/weeks                  [{phase, week, label, partial}] in order
GET /api/imperialism/{season}/team/{team}            the team's cells by snapshot, its events, its share and rank by land
GET /api/imperialism/{season}/{phase}/{week}         one snapshot: owners, leaderboard, that snapshot's events

No map for the season is a 503 that says since when and why; an unknown team or week is a 404 (the team's lists the names)."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.api.envelope import envelope
from app.jobs import last_of, read_runs
from app.jobs.imperialism import NAME, grid_version
from app.services.imperialism import ImperialismStore
from app.services.imperialism_grid import load_grid
from app.services.talent_edge import TalentEdgeStore, summary_line

router = APIRouter(tags=["imperialism"])
log = logging.getLogger("kickoff.api.imperialism")

YEAR = 31536000


def _stores(request: Request, season: int) -> tuple[ImperialismStore, TalentEdgeStore]:
    held = getattr(request.app.state, "imperialism_stores", None)
    if held is None:
        held = request.app.state.imperialism_stores = {}
    if season not in held:
        data_dir = request.app.state.settings.data_dir
        held[season] = (ImperialismStore(data_dir, season), TalentEdgeStore(data_dir, season))
    return held[season]


def _why(request: Request, season: int) -> dict[str, Any]:
    """Since when and why there is no map for the season (the spec: never an empty chart)."""
    runs = read_runs(request.app.state.settings.data_dir)
    good, last = last_of(runs, NAME, season, "ok"), last_of(runs, NAME, season)
    if last is not None and last.get("status") == "running":
        message = f"The Imperialism Map for {season} is being worked out now (started {last.get('startedAt')})."
    elif last is not None and last.get("status") == "failed" and good is None:
        message = f"The Imperialism Map for {season} is unavailable since {last.get('startedAt')}: {last.get('message')}"
    elif good is not None:
        message = f"The Imperialism Map for {season} could not be read; the last good run finished {good.get('finishedAt')}."
    else:
        message = f"The Imperialism Map for {season} has not been worked out yet. The server works it out on its first start with it, then Sundays from 6 AM."
    return {"season": season, "lastGoodRun": good, "lastRun": last, "failed": bool(last and last.get("status") == "failed"), "message": message}


def _unavailable(request: Request, season: int) -> JSONResponse:
    why = _why(request, season)
    return JSONResponse(status_code=503, content=envelope(why, errors=[{"code": "unavailable", "message": why["message"]}]))


def _not_found(message: str, data: Any = None) -> JSONResponse:
    return JSONResponse(status_code=404, content=envelope(data, errors=[{"code": "not_found", "message": message}]))


def _teams(table: dict[str, Any], talent: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = (talent or {}).get("teams") if isinstance((talent or {}).get("teams"), dict) else {}
    out = []
    for t in table["teams"]:
        tid = t.get("id") if isinstance(t.get("id"), int) and not isinstance(t.get("id"), bool) else None
        logos = {"logo": f"/media/logo/{tid}", "logoDark": f"/media/logo/{tid}?v=dark"} if tid is not None else {"logo": None, "logoDark": None}
        out.append({**{k: t.get(k) for k in ("team", "index", "quota", "home", "campus", "abbreviation", "conference", "color", "altColor")}, **logos, "talentEdge": summary_line(rows.get(t.get("team")))})
    return out


async def _our_schedule(request: Request) -> list[dict[str, Any]]:
    """Our season's games for the page's Next line, from the schedule the program already keeps (no call of its own)."""
    team = request.app.state.settings.team
    try:
        parts = await request.app.state.program._core()
        games = parts["schedule"].records
    except Exception:  # noqa: BLE001 - the Next line is a courtesy; the map stands without it (logged)
        log.exception("The Imperialism Map could not read our schedule")
        return []
    out = []
    for g in sorted(games, key=lambda g: (str(g.season_type or ""), str(g.start_date or ""))):
        home = g.home_team == team
        if team not in (g.home_team, g.away_team):
            continue
        us, them = (g.home_points, g.away_points) if home else (g.away_points, g.home_points)
        out.append({"week": g.week, "seasonType": g.season_type, "opponent": g.away_team if home else g.home_team, "home": home, "neutral": bool(g.neutral_site), "start": g.start_date, "completed": g.completed is True, "us": us, "them": them})
    return out


def _leaderboard(table: dict[str, Any], owners: list[int]) -> list[dict[str, Any]]:
    counts = Counter(owners)
    total = len(owners) or 1
    names = [t["team"] for t in table["teams"]]
    ranked = sorted(((n, names[i]) for i, n in counts.items() if 0 <= i < len(names)), key=lambda x: (-x[0], x[1]))
    out, rank, last = [], 0, None
    for place, (n, name) in enumerate(ranked, start=1):
        if n != last:
            rank, last = place, n
        out.append({"rank": rank, "team": name, "cells": n, "pct": round(100 * n / total, 1)})
    return out


def _head(request: Request, table: dict[str, Any]) -> dict[str, Any]:
    return {"season": table.get("season"), "computedWeek": table.get("computedWeek"), "gridVersion": table.get("gridVersion"), "cells": table.get("cells"), "rules": table.get("rules"), "notes": table.get("notes") or [], "ourTeam": request.app.state.settings.team}


def _snapshot_events(table: dict[str, Any], snap: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in table.get("events") or [] if e.get("phase") == snap["phase"] and e.get("week") == snap["week"] and e.get("cellsMoved")]


@router.get("/api/imperialism/grid")
async def grid(request: Request, v: str | None = Query(default=None, max_length=40)) -> Any:
    held = getattr(request.app.state, "imperialism_grid", None)
    version = grid_version()
    if held is None or held[0] != version:
        try:
            held = request.app.state.imperialism_grid = (version, load_grid().compact())
        except (OSError, ValueError) as exc:
            return JSONResponse(status_code=503, content=envelope(None, errors=[{"code": "no_grid", "message": f"The map's grid could not be read: {exc}"}]))
    cache = f"public, max-age={YEAR}, immutable" if v == version else "no-cache"
    return JSONResponse(content=envelope({**held[1], "version": version}, source="cache"), headers={"Cache-Control": cache})


@router.get("/api/imperialism/now")
async def now(request: Request) -> Any:
    season = request.app.state.settings.season
    store, talent = _stores(request, season)
    table = store.load()
    if table is None:
        return envelope({"available": False, **_why(request, season)}, source="cache")
    snapshots = [{k: s[k] for k in ("phase", "week", "label", "partial", "owners", "records")} for s in table["snapshots"]]
    runs = read_runs(request.app.state.settings.data_dir)
    return envelope({
        "available": True,
        **_head(request, table),
        "runs": {"lastGood": last_of(runs, NAME, season, "ok"), "last": last_of(runs, NAME, season)},
        "upcoming": table.get("upcoming") or [],
        "teams": _teams(table, talent.load()),
        "snapshots": snapshots,
        "events": [e for e in table.get("events") or [] if e.get("cellsMoved")],
        "schedule": await _our_schedule(request),
    }, source="cache")


@router.get("/api/imperialism/{season}/all")
async def every_week(request: Request, season: int) -> Any:
    store, talent = _stores(request, season)
    table = store.load()
    if table is None:
        return _unavailable(request, season)
    snapshots = [{k: s[k] for k in ("phase", "week", "label", "partial", "owners", "records")} for s in table["snapshots"]]
    return envelope({**_head(request, table), "teams": _teams(table, talent.load()), "snapshots": snapshots, "events": [e for e in table.get("events") or [] if e.get("cellsMoved")]}, source="cache")


@router.get("/api/imperialism/{season}/weeks")
async def weeks(request: Request, season: int) -> Any:
    store, _talent = _stores(request, season)
    table = store.load()
    if table is None:
        return _unavailable(request, season)
    return envelope({**_head(request, table), "weeks": [{k: s[k] for k in ("phase", "week", "label", "partial")} for s in table["snapshots"]]}, source="cache")


@router.get("/api/imperialism/{season}/team/{team}")
async def one_team(request: Request, season: int, team: str) -> Any:
    store, talent = _stores(request, season)
    table = store.load()
    if table is None:
        return _unavailable(request, season)
    names = [t["team"] for t in table["teams"]]
    wanted = team.strip().casefold()
    name = next((n for n in names if n.casefold() == wanted), None)
    if name is None:
        return _not_found(f"{team.strip() or 'That name'} holds no land on the {season} map.", {"validTeams": names})
    index = names.index(name)
    by_week = [{"phase": s["phase"], "week": s["week"], "label": s["label"], "partial": s["partial"], "cells": s["owners"].count(index), "record": s["records"].get(name)} for s in table["snapshots"]]
    last = table["snapshots"][-1]
    board = _leaderboard(table, last["owners"])
    row = next((r for r in board if r["team"] == name), {"rank": None, "cells": 0, "pct": 0.0})
    events = [e for e in table.get("events") or [] if e.get("cellsMoved") and name in (e.get("winner"), e.get("loser"))]
    team_row = next((t for t in _teams(table, talent.load()) if t["team"] == name), {})
    return envelope({**_head(request, table), **team_row, "weeks": by_week, "events": events, "now": {"cells": row["cells"], "pct": row["pct"], "rank": row["rank"], "of": len(board)}}, source="cache")


@router.get("/api/imperialism/{season}/{phase}/{week}")
async def one_week(request: Request, season: int, phase: str, week: int) -> Any:
    store, talent = _stores(request, season)
    table = store.load()
    if table is None:
        return _unavailable(request, season)
    snap = next((s for s in table["snapshots"] if s["phase"] == phase and s["week"] == week), None)
    if snap is None:
        return _not_found(f"No {phase} week {week} on the {season} map.", {"weeks": [{k: s[k] for k in ("phase", "week", "label")} for s in table["snapshots"]]})
    return envelope({**_head(request, table), "phase": snap["phase"], "week": snap["week"], "label": snap["label"], "partial": snap["partial"], "teams": _teams(table, talent.load()), "holdings": snap["owners"], "leaderboard": _leaderboard(table, snap["owners"]), "events": _snapshot_events(table, snap)}, source="cache")
