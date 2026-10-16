"""Program (P1 to P10), Newspaper (N1 to N4, with its weekly editions), the Top 25 page and team page (T1) routes."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Query, Request

from app.api.envelope import envelope, error_response
from app.api.players import respond
from app.api.season import archived_ids, mark_archived
from app.services.parts import Assembled, assemble
from app.services.program import ProgramService
from app.services.rankedweek import RankedWeekService

router = APIRouter(tags=["program"])
log = logging.getLogger("kickoff.program")


def _mark_program(result: Assembled, request: Request) -> None:
    """Phase 16 (audit P-03): game.archived says the Archive holds this game, so the cover can link
    to it; the picker rows carry the same flag."""
    archived = archived_ids(request)
    game = result.data.get("game")
    if isinstance(game, dict):
        game["archived"] = game.get("gameId") in archived
        # owner 2026-10-10: while In Game holds this game's final, the cover offers it; the server's time, not the device's
        held = request.app.state.live.held_final() if hasattr(request.app.state, "live") else None
        game["heldUntil"] = held["until"] if held and held.get("gameId") == game.get("gameId") else None
    mark_archived(result.data.get("picker"), archived)
    # wave B: the facts for both schools (the two-schools band) and whether the program was locked at kickoff
    notes = getattr(request.app.state, "season_notes", None)
    lock = getattr(request.app.state, "program_lock", None)
    if isinstance(game, dict):
        game["locked"] = bool(lock is not None and lock.has(game.get("gameId")))
    result.data["facts"] = {"us": notes.facts_for((result.data.get("us") or {}).get("school")) if notes else None, "them": notes.facts_for((result.data.get("them") or {}).get("school")) if notes else None}
    block = result.data.get("notes")
    if isinstance(game, dict) and isinstance(block, dict) and isinstance(game.get("gameId"), int):  # 2026-10-16: notes by hand
        from app.api.prompts import notes_location

        block.update(notes_location(request.app.state.settings.data_dir, game["gameId"]))
    for side in ("us", "them"):  # Phase 17 #2: a form square of ours opens the Archive when it holds the game
        block = result.data.get(side)
        if isinstance(block, dict):
            mark_archived(block.get("form"), archived)


@router.get("/api/program/next")
async def program_next(request: Request) -> Any:
    service: ProgramService = request.app.state.program
    result = await service.program(None)
    if result is None:
        return error_response(404, "not_found", "No games on the schedule.")
    _mark_program(result, request)
    return respond(result)


@router.get("/api/program/{game_id}")
async def program_game(game_id: str, request: Request) -> Any:
    service: ProgramService = request.app.state.program
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No game with that id.")
    result = await service.program(int(game_id))
    if result is None:
        return error_response(404, "not_found", "That game is not on our schedule.")
    _mark_program(result, request)
    return respond(result)


@router.get("/api/program/{game_id}/locked")
async def program_locked(game_id: str, request: Request) -> Any:
    """Wave B: what the program said at kickoff, for the results band on a finished game's program."""
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No game with that id.")
    locked = request.app.state.program_lock.load(int(game_id))
    if locked is None:
        return error_response(404, "not_locked", "This program was not locked at kickoff.")
    return envelope(locked, source="cache", fetched_at=locked.get("lockedAt"))


@router.get("/api/program/{game_id}/leaders")
async def program_leaders(game_id: str, request: Request) -> Any:
    """Phase 17 #17: the leaders side by side with each one's whole line, ranks and conference-game line."""
    service: ProgramService = request.app.state.program
    if not (game_id.isdigit() and len(game_id) <= 12) and game_id != "next":
        return error_response(404, "not_found", "No game with that id.")
    result = await service.leaders(None if game_id == "next" else int(game_id))
    if result is None:
        return error_response(404, "not_found", "That game is not on our schedule.")
    return respond(result)


@router.get("/api/box/{game_id}")
async def box_score(game_id: str, request: Request) -> Any:
    """Phase 17 #2: the box score of any game this season (a W or L square on a cover opens it)."""
    service: ProgramService = request.app.state.program
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No game with that id.")
    result = await service.box(int(game_id))
    if result is None:
        return error_response(404, "not_found", "No game with that id this season.")
    return respond(result)


@router.get("/api/newspaper")
async def newspaper(request: Request, delay: float = Query(0, ge=0, le=120), edition: str | None = Query(None, max_length=20)) -> Any:
    """The paper (N1 to N4) with this week's edition (items 10-12): the AP-ranked matchups with their headlines, our
    game following the delay; ?edition=week-6 opens an earlier week's saved edition (the masthead's arrows)."""
    service: ProgramService = request.app.state.program
    data, parts = await service.newspaper_parts()
    ranked: RankedWeekService = request.app.state.rankedweek
    key = edition.strip() if isinstance(edition, str) and edition.strip() else None
    try:
        parts = await ranked.paper(data, parts, float(delay), key)
    except Exception as exc:  # noqa: BLE001 - the headlines never fall with the matchups or the editions; logged and said
        log.exception("The paper's edition could not be built")
        data.pop("edition", None)  # the page draws this week's headlines without matchups
        data["editionError"] = f"The ranked games and the earlier editions could not be read ({exc.__class__.__name__}); the app tries again."
    result = assemble(data, parts)
    await request.app.state.archive.attach_recent_recap(result.data)  # Phase 16 BX: UX-07, the last final within 36 hours
    return respond(result)


@router.get("/api/top25")
async def top25(request: Request, delay: float = Query(0, ge=0, le=120)) -> Any:
    """The Top 25 page (item 11): every game of the week with an AP Top 25 team, as the cover shows it, live scores
    included; our game follows the delay."""
    ranked: RankedWeekService = request.app.state.rankedweek
    return respond(await ranked.top25(float(delay)))


@router.get("/api/injuries")
async def injuries(request: Request, team: str | None = None) -> Any:
    """The Injury Report (owner 2026-10-10): ours, or ?team=<school> for an opponent of ours, from the game notes."""
    service: ProgramService = request.app.state.program
    name = team.strip() if isinstance(team, str) and team.strip() else None
    if name is not None and len(name) > 60:
        return error_response(404, "not_found", "No team with that name.")
    result = await service.injuries(name)
    if result is None:
        return error_response(404, "not_found", f"No FBS team called {name}.")
    return respond(result)


@router.get("/api/team/{school}")
async def team_page(school: str, request: Request) -> Any:
    service: ProgramService = request.app.state.program
    name = unquote(school).strip()
    if not name or len(name) > 60:
        return error_response(404, "not_found", "No team with that name.")
    result = await service.team_page(name)
    if result is None:
        return error_response(404, "not_found", f"No FBS team called {name}.")
    if (result.data.get("team") or {}).get("isUs"):  # Phase 16 (G3-05): our schedule rows open the Archive too
        mark_archived(result.data.get("schedule"), archived_ids(request))
    result.data["facts"] = request.app.state.season_notes.facts_for((result.data.get("team") or {}).get("school") or name)  # the Prompts phase: school history
    # 2026-10-16: the season loads cover my teams only; a page of another team says so instead of pointing at Load data
    from app.api.season_notes import load_set

    try:
        _primaries, wanted = await load_set(request)
    except Exception as exc:  # noqa: BLE001 - without the team list the page still draws; its empty bands say "not loaded"
        log.warning("The load set could not be read for %s: %s", name, exc)
        wanted = None
    school_name = (result.data.get("team") or {}).get("school") or name
    result.data["inLoadSet"] = None if wanted is None else school_name in wanted
    return respond(result)
