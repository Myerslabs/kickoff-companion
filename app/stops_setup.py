"""Connects the season's line (app/services/stops.py) to this app's stores: the schedule, the kickoff and post-game locks,
the Archive, Claude's recap and the schedule's ledger. Kept apart so the rules stay pure and testable."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.cache import DataKind
from app.cfbd.models import Game
from app.services import gamekeys
from app.services.notes_task import NotesRunner
from app.services.postgame_lock import poll_after
from app.services.stops import Checks, GameRow, Status, season_line
from app.services.writing import WritingStore

log = logging.getLogger("kickoff.stops")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def claude_found(state: Any) -> bool:
    try:
        return NotesRunner.resolve_command(state.settings.claude_command) is not None
    except Exception:  # noqa: BLE001 - a broken command setting reads as not found
        return False


def game_checks(state: Any, game: Game, ranks: dict[str, Any]) -> Checks:
    """The Post-Game's closing checklist for one game. A check that cannot come (Claude Code not on this computer) counts
    as in, so the stop never waits for something that will not happen."""
    settings = state.settings
    recap_in = True
    if claude_found(state):
        try:
            recap_in = WritingStore(settings.data_dir, settings.season).load("recap", str(game.id)) is not None
        except Exception:  # noqa: BLE001 - an unreadable writing file never holds the stop
            log.warning("The recap for game %s could not be read for the checklist", game.id, exc_info=True)
            recap_in = True
    return Checks(final=bool(game.completed), poll=bool(ranks.get("AP")), recap=recap_in)


def game_row(state: Any, game: Game) -> GameRow | None:
    program = state.program
    kickoff = program._local(game.start_date)
    if kickoff is None or not isinstance(game.week, int):
        return None
    team = program.team
    if game.home_team == team:
        opponent, where = game.away_team, "neutral" if game.neutral_site else "home"
        us, them = game.home_points, game.away_points
    else:
        opponent, where = game.home_team, "neutral" if game.neutral_site else "away"
        us, them = game.away_points, game.home_points
    return GameRow(game.id, game.week, kickoff, opponent, where, bool(game.completed), us, them, (game.season_type or "regular"))


def status_for(state: Any, game: Game, weeks: list[Any]) -> Status:
    """What the stores say about one game: the kickoff lock, the Archive, the post-game lock and its time, the checklist,
    and whether Thursday's run opened the Pre-Game early."""
    pre_locked = bool(state.program_lock.has(game.id))
    archived = False
    try:
        archived = state.archive._file_for(game.id) is not None
    except Exception:  # noqa: BLE001 - the Archive is a courtesy here
        archived = False
    post = state.postgame_lock.load(game.id)
    post_at = _parse(post.get("lockedAt")) if isinstance(post, dict) else None
    if post_at is not None:
        post_at = post_at.astimezone(state.settings.tzinfo)
    _week, ranks = poll_after(weeks, game)
    checks = game_checks(state, game, ranks)
    opened = None
    ledger = getattr(getattr(state, "claude_schedule", None), "ledger", None)
    if ledger is not None:
        try:
            key = f"parts-thu:{game.id}"
            if ledger.succeeded(key):
                opened = ledger.last_attempt(key)
                if opened is not None:
                    opened = opened.astimezone(state.settings.tzinfo)
        except Exception:  # noqa: BLE001 - the ledger is a courtesy here
            opened = None
    return Status(pre_locked=pre_locked, archived=archived, post_locked=post is not None, post_locked_at=post_at, checks=checks, pre_opened_at=opened)


async def line_for(state: Any, now: datetime) -> dict[str, Any]:
    """The season's line from the cached schedule and polls: what `/api/stops` answers and the rail draws."""
    program = state.program
    schedule = await program.fetcher.fetch("schedule", "/games", {"year": program.year, "team": program.team}, Game, DataKind.SCHEDULE)
    if not schedule.ok:
        raise RuntimeError(schedule.error or "The schedule could not be read")
    core = await program._core()
    weeks = core["rankings"].records if core.get("rankings") is not None and getattr(core["rankings"], "ok", False) else []
    games = sorted((g for g in schedule.records if isinstance(g.week, int)), key=gamekeys.order)
    rows: list[GameRow] = []
    by_id: dict[int, Game] = {}
    for game in games:
        row = game_row(state, game)
        if row is not None:
            rows.append(row)
            by_id[game.id] = game
    cache: dict[int, Status] = {}

    def status(row: GameRow) -> Status:
        if row.game_id not in cache:
            cache[row.game_id] = status_for(state, by_id[row.game_id], weeks)
        return cache[row.game_id]

    local_now = now.astimezone(state.settings.tzinfo)
    line = season_line(rows, local_now, status=status, preseason=True, book_href="#review")  # Wave 7: the season book is the season in review, open once every game is closed out
    line["season"] = program.year
    line["team"] = program.team
    return line
