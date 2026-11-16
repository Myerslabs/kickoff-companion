"""Program (P1 to P10), Newspaper (N1 to N4, with its weekly editions), the Top 25 page and team page (T1) routes."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Query, Request

from app.api.envelope import envelope, error_response
from app.api.players import respond
from app.api.season import archived_ids, mark_archived
from app.services.facts_now import with_this_season
from app.services.parts import Assembled, assemble
from app.services.postgame_lock import PostgameLock
from app.services.program import ProgramService
from app.services.program_lock import ProgramLock
from app.services.rankedweek import RankedWeekService

router = APIRouter(tags=["program"])
log = logging.getLogger("kickoff.program")


def facts_with_venue(facts: dict[str, Any] | None, location: dict[str, Any] | None) -> dict[str, Any] | None:
    """The school's facts with CFBD's stadium figures where it has them (freeze wave F3, one fact, one source): the cover's
    conditions line took the venue from CFBD while the facts bands took it from the AI's answer, so one page could show two
    capacities and two opened years for one stadium. The name, the capacity and the opened year come from CFBD's team
    record when present; the AI's stay for the rest, and `venueSource` says which won."""
    if not isinstance(facts, dict):
        return facts
    loc = location if isinstance(location, dict) else {}
    out = dict(facts)
    took = False
    name = loc.get("venue")
    if isinstance(name, str) and name.strip():
        out["stadium"], took = name.strip(), True
    capacity = loc.get("capacity")
    if isinstance(capacity, int) and not isinstance(capacity, bool) and capacity > 0:
        out["capacity"], took = capacity, True
    built = loc.get("yearBuilt")
    if isinstance(built, int) and not isinstance(built, bool):
        out["stadiumOpened"], took = built, True
    out["venueSource"] = "CFBD" if took else "notes"
    return out


async def _season_games(service: ProgramService | None) -> list[Any]:
    """This season's games, as cached for every program (no call of its own); none when they cannot be read."""
    if service is None:
        return []
    try:
        core = await service._core()
    except Exception:  # noqa: BLE001 - the records stay as researched; logged
        log.warning("This season's games could not be read to count the records forward", exc_info=True)
        return []
    part = core.get("games")
    return part.records if part is not None and part.ok else []


def _counted(request: Request, facts: dict[str, Any] | None, games: list[Any]) -> dict[str, Any] | None:
    """The bug round (owner 2026-11-15, "Add this season's games"): the all-time record and the head coach's record at the
    school with this season's finished games (app/services/facts_now.py)."""
    season = getattr(getattr(request.app.state, "settings", None), "season", None)
    if not isinstance(facts, dict) or not isinstance(season, int):
        return facts  # no facts, or no season to count (a bare app in the tests): as researched
    notes = getattr(request.app.state, "season_notes", None)
    school = facts.get("school")
    row = notes.coaches_for(school) if notes is not None and isinstance(school, str) and hasattr(notes, "coaches_for") else None
    coach = row.get("headCoach") if isinstance(row, dict) else None
    return with_this_season(facts, games, season, coach if isinstance(coach, str) else None)


async def _mark_program(result: Assembled, request: Request) -> None:
    """Phase 16 (audit P-03): game.archived says the Archive holds this game, so the cover can link
    to it; the picker rows carry the same flag. Async since freeze wave F3: the two schools' facts take each school's
    stadium from the cached team list."""
    service: ProgramService | None = getattr(request.app.state, "program", None)
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
    post = getattr(request.app.state, "postgame_lock", None)
    if isinstance(game, dict):
        game["locked"] = bool(lock is not None and lock.has(game.get("gameId")))
        game["postLocked"] = bool(post is not None and post.has(game.get("gameId")))  # F8 feature 1: the Post-Game Program is kept
    facts: dict[str, Any] = {}
    games = await _season_games(service)
    for side in ("us", "them"):
        school = (result.data.get(side) or {}).get("school")
        facts[side] = _counted(request, facts_with_venue(notes.facts_for(school) if notes else None, await service.location_of(school) if service is not None else None), games)  # freeze wave F3: CFBD's stadium figures first; the bug round: the records with this season's games
    result.data["facts"] = facts
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
    await _mark_program(result, request)
    return respond(result)


@router.get("/api/program/{game_id}")
async def program_game(game_id: str, request: Request, team: str | None = None) -> Any:
    """Any FBS game's program (FEAT-5): ours from our side; another from `team`'s side when it plays in it, else the home side."""
    service: ProgramService = request.app.state.program
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No game with that id.")
    result = await service.any_program(int(game_id), team.strip() if isinstance(team, str) else None)
    if result is None:
        return error_response(404, "not_found", "No FBS game with that id this season.")
    await _mark_program(result, request)
    return respond(result)


def _past_season(request: Request, season: int | None) -> int | None:
    """Rollover R2: a season before this one asked for by ?season=, else None (this season's locks)."""
    current = request.app.state.settings.season
    return season if season is not None and season != current else None


@router.get("/api/program/{game_id}/postgame")
async def program_postgame(game_id: str, request: Request, season: int | None = Query(None, ge=2000, le=2999)) -> Any:
    """The Post-Game Program locked once the poll after the game was out (F8 feature 1): both teams as that poll had
    them, the final, the race and the picture as they stood, the news, and the program's answer as it stood then."""
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No game with that id.")
    past = _past_season(request, season)
    lock = PostgameLock(request.app.state.settings.data_dir, past) if past is not None else getattr(request.app.state, "postgame_lock", None)
    locked = lock.load(int(game_id)) if lock is not None else None
    if locked is None:
        return error_response(404, "not_locked", "This game's Post-Game Program is not kept yet: it is written once the poll after the game is out.")
    return envelope(locked, source="cache", fetched_at=locked.get("lockedAt"))


@router.get("/api/program/{game_id}/locked")
async def program_locked(game_id: str, request: Request, season: int | None = Query(None, ge=2000, le=2999)) -> Any:
    """Wave B: what the program said at kickoff, for the results band on a finished game's program."""
    if not game_id.isdigit() or len(game_id) > 12:
        return error_response(404, "not_found", "No game with that id.")
    past = _past_season(request, season)
    locked = (ProgramLock(request.app.state.settings.data_dir, past) if past is not None else request.app.state.program_lock).load(int(game_id))
    if locked is None:
        return error_response(404, "not_locked", "This program was not locked at kickoff.")
    return envelope(locked, source="cache", fetched_at=locked.get("lockedAt"))


@router.get("/api/program/{game_id}/leaders")
async def program_leaders(game_id: str, request: Request, team: str | None = None) -> Any:
    """Phase 17 #17: the leaders side by side with each one's whole line, ranks and conference-game line (any game, FEAT-5)."""
    service: ProgramService = request.app.state.program
    if not (game_id.isdigit() and len(game_id) <= 12) and game_id != "next":
        return error_response(404, "not_found", "No game with that id.")
    result = await (service.leaders(None) if game_id == "next" else service.any_leaders(int(game_id), team.strip() if isinstance(team, str) else None))
    if result is None:
        return error_response(404, "not_found", "No FBS game with that id this season.")
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


@router.get("/api/newspaper/headlines")
async def newspaper_headlines(request: Request, limit: int = Query(10, ge=1, le=50)) -> Any:
    """Batch 1 (owner 2026-11-15, "Every page in ~1.5 s"): the team's newest headlines alone, for the bands that show them
    beside a program (the Pre-Game, the Post-Game, the Magazine). They asked for the whole paper (260 KB, 0.6 to 2 s) to read
    its first ten headlines; this answers from the feeds as kept, no edition built, no CFBD call."""
    from app.feeds import merge_headlines

    service: ProgramService = request.app.state.program
    results = await service.feeds.all()
    now = service.client._clock()
    news = merge_headlines(results)[:limit]
    return envelope({"news": news, "feeds": {r.feed.id: {"name": r.feed.name, **r.status(now)} for r in results}}, source="cache")


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
    result.data["facts"] = _counted(request, facts_with_venue(request.app.state.season_notes.facts_for((result.data.get("team") or {}).get("school") or name), result.data.get("location")), await _season_games(service))  # the Prompts phase: school history; freeze wave F3: CFBD's stadium figures first
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
