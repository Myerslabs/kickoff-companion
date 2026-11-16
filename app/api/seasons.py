"""The Seasons list (rollover R2; owner 2026-11-15: "A Seasons list", "The book and its games"). Nothing here calls CFBD:
every past season is read from what was kept on disk.

    GET /api/seasons                       this season and each past one with something kept, and the switch's state
    GET /api/seasons/{year}/book/{part}    a past season's season in review, as kept at the switch (overview, players,
                                           stops, blame); 404 when it was never kept
    GET /api/seasons/{year}/game/{id}      a past season's game as its program stood when kept: the Post-Game lock's
                                           (closed out), else the kickoff lock's; "past": year marks it for the page
    GET /api/seasons/{year}/paper          a past season's paper, read only (app/services/past_paper.py): ?edition=week-8,
                                           else the season's last paper; its editions for the week chips (R3)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.envelope import envelope, error_response
from app.rollover_setup import book_dir, read_book
from app.services.past_paper import past_paper
from app.services.postgame_lock import PostgameLock
from app.services.program_lock import ProgramLock

log = logging.getLogger("kickoff.seasons")

router = APIRouter(tags=["seasons"])

PART = re.compile(r"^[a-z][a-z-]{0,19}$")
YEAR = re.compile(r"^\d{4}$")


def _count(folder: Path, pattern: str) -> int:
    try:
        return sum(1 for p in folder.glob(pattern) if p.is_file()) if folder.is_dir() else 0
    except OSError:
        return 0


def past_seasons(data_dir: Path, current: int) -> list[dict[str, Any]]:
    """Each folder data/season/<year> before this season holding a kept book or a game's lock, newest first."""
    root = Path(data_dir) / "season"
    rows: list[dict[str, Any]] = []
    try:
        names = [p.name for p in root.iterdir() if p.is_dir() and YEAR.match(p.name)] if root.is_dir() else []
    except OSError:
        log.warning("The season folders could not be listed", exc_info=True)
        names = []
    for name in names:
        year = int(name)
        if year >= current:
            continue
        folder = root / name
        overview = read_book(data_dir, year, "overview")
        games = _count(folder / "postgame", "*.json")
        pre = _count(folder / "program", "*.json")
        if overview is None and games == 0 and pre == 0:
            continue
        rows.append({"season": year, "current": False, "book": overview is not None, "keptAt": overview.get("keptAt") if overview else None, "games": games, "preGames": pre, "href": f"#review={year}"})
    return sorted(rows, key=lambda r: r["season"], reverse=True)


@router.get("/api/seasons")
async def seasons(request: Request) -> Any:
    settings = request.app.state.settings
    current = int(settings.season)
    switch = None
    rollover = getattr(request.app.state, "rollover", None)
    if rollover is not None and not getattr(request.app.state, "demo_mode", False):
        try:
            switch = rollover.status()
        except Exception:  # noqa: BLE001 - the list never falls with the switch's state; logged
            log.exception("The switch's state could not be read")
    rows = [{"season": current, "current": True, "book": False, "keptAt": None, "href": "#season"}, *past_seasons(settings.data_dir, current)]
    return envelope({"current": current, "seasons": rows, "switch": switch}, source="cache")


@router.get("/api/seasons/{year}/book/{part}")
async def season_book(year: str, part: str, request: Request) -> Any:
    settings = request.app.state.settings
    if not YEAR.match(year) or not PART.match(part):
        return error_response(404, "not_found", "No such season or part.")
    if int(year) >= int(settings.season):
        return error_response(404, "current_season", f"{year} is this season: its pages are the live ones.")
    kept = read_book(settings.data_dir, int(year), part)
    if kept is None:
        where = book_dir(settings.data_dir, int(year))
        return error_response(404, "not_kept", f"The {year} season's {part.replace('-', ' ')} was not kept when the app moved on ({where.name} has no copy).")
    body = kept["envelope"]
    errors = [e for e in body.get("errors") or [] if isinstance(e, dict)] if isinstance(body.get("errors"), list) else []
    return envelope(body.get("data"), source="cache", fetched_at=kept.get("keptAt") if isinstance(kept.get("keptAt"), str) else None, errors=errors)


@router.get("/api/seasons/{year}/game/{game_id}")
async def season_game(year: str, game_id: str, request: Request) -> Any:
    settings = request.app.state.settings
    if not YEAR.match(year) or not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No such season or game.")
    season = int(year)
    if season >= int(settings.season):
        return error_response(404, "current_season", f"{year} is this season: its games are on the live pages.")
    for lock, kept_from in ((PostgameLock(settings.data_dir, season), "postgame"), (ProgramLock(settings.data_dir, season), "kickoff")):
        locked = lock.load(int(game_id))
        program = locked.get("program") if isinstance(locked, dict) else None
        if isinstance(program, dict) and isinstance(program.get("game"), dict):
            data = {**program, "past": season, "keptFrom": kept_from}
            return envelope(data, source="cache", fetched_at=locked.get("lockedAt") if isinstance(locked.get("lockedAt"), str) else None)
    return error_response(404, "not_kept", f"This game's program was not kept in {year}.")


@router.get("/api/seasons/{year}/paper")
async def season_paper(year: str, request: Request, edition: str | None = Query(None, max_length=20)) -> Any:
    settings = request.app.state.settings
    if not YEAR.match(year):
        return error_response(404, "not_found", "No such season.")
    if int(year) >= int(settings.season):
        return error_response(404, "current_season", f"{year} is this season: its paper is the live one.")
    data = past_paper(settings.data_dir, int(year), request.app.state.program.team, edition.strip() if isinstance(edition, str) and edition.strip() else None)
    if not data["editions"]:
        return error_response(404, "not_kept", f"No paper was kept for {year}.")
    return envelope(data, source="cache")
