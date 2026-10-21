"""Connects the Claude schedule (app/services/claude_schedule.py) and the one run of every prompt
(app/services/prompt_runs.py, the Prompts phase) to this app's pieces: the next game, the notes files, the two runners
and the settings. Kept apart so the schedule and the run stay testable without an app."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from app.cache import DataKind
from app.feeds import merge_headlines
from app.services import gamekeys
from app.services.claude_schedule import NOTES_BEFORE_KICKOFF, ClaudeSchedule, Ledger, Slot
from app.services.notes import load_notes, notes_path
from app.services.notes_task import NotesRunner
from app.services.prompt_runs import PromptRuns, Step
from app.services.readiness import missing_notes

log = logging.getLogger("kickoff.schedule")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def build_prompt_runs(app: FastAPI) -> PromptRuns:
    """The one run (the Prompts phase, owner 2026-10-13): every prompt in the season's order, each through its own runner."""
    state = app.state
    shim = SimpleNamespace(app=app)

    def command() -> str:
        return state.settings.claude_command

    def command_found() -> bool:
        return NotesRunner.resolve_command(command()) is not None

    async def season_status() -> dict[str, Any]:
        from app.api.season_notes import _context

        primaries, conferences, _meta = await _context(shim)
        return state.season_notes.status(primaries, conferences, datetime.now(state.settings.tzinfo).date())

    def season_poll() -> dict[str, Any]:
        season = state.season_runner
        if season.running:
            return {"running": True}
        saved = [b for b in season.batches if b.state == "saved"]
        return {"running": False, "ok": bool(season.batches) and len(saved) == len(season.batches), "error": season.error or next((b.error for b in season.batches if b.error), None), "changed": None}

    def season_start(kind: str):
        async def start(all: bool) -> dict[str, Any]:  # noqa: A002 - the run's word
            from app.api.season_notes import start_season_run

            return await start_season_run(shim, kind, None, not all)

        return start

    def season_missing(kind: str):
        async def missing() -> str | None:
            s = await season_status()
            if kind == "preseason":
                absent = [str(r.get("school")) for r in s.get("preseason", []) if not r.get("savedAt")]
                return f"preseason not loaded for {', '.join(absent[:4])}{'…' if len(absent) > 4 else ''}" if absent else None
            saved, of = s.get(f"{kind}Saved"), s.get("coachesOf")
            if isinstance(of, int) and of and saved != of:
                return f"{saved or 0} of {of} teams"
            return None

        return missing

    async def notes_start(all: bool) -> dict[str, Any]:  # noqa: A002
        from app.api.notes import _game

        game, _ok = await _game(shim, None)
        if game is None or game.completed:
            return {"error": "no upcoming game on the schedule"}
        info = {"gameId": game.id, "home": game.home_team, "away": game.away_team, "kickoff": game.start_date}
        return await state.notes.start(info, command(), "full", state.settings.claude_lookup_model or None)

    def notes_poll() -> dict[str, Any]:
        runner: NotesRunner = state.notes
        if runner.running:
            return {"running": True}
        return {"running": False, "ok": bool(runner.saved and not runner.error), "error": runner.error or ("no usable answer saved" if not runner.saved else None), "changed": runner.changed}

    async def notes_missing() -> str | None:
        from app.api.notes import _game

        try:
            game, _ok = await _game(shim, None)
        except Exception:  # noqa: BLE001 - no schedule: nothing to run this week, said in words
            return None
        if game is None or game.completed:
            return None
        # wave B: the notes run once, at the most accurate time (two hours before kickoff); until then the catch-up
        # leaves them alone, and "Run everything again" still runs them any time
        kickoff = _parse(getattr(game, "start_date", None))
        clock = getattr(state.cfbd, "_clock", None)
        now = clock() if callable(clock) else datetime.now(timezone.utc)
        if kickoff is not None and now < kickoff - NOTES_BEFORE_KICKOFF:
            return None
        notes, _problem = load_notes(state.settings.data_dir, game.id)
        if notes is None:
            return "this week's notes are not loaded"
        gaps = missing_notes(notes)
        return f"missing {', '.join(gaps)}" if gaps else None

    steps = [
        Step("preseason", "The season load", season_start("preseason"), season_poll, season_missing("preseason")),
        Step("coaches", "Coaches", season_start("coaches"), season_poll, season_missing("coaches")),
        Step("costs", "Roster costs", season_start("costs"), season_poll, season_missing("costs")),
        Step("facts", "School history and facts", season_start("facts"), season_poll, season_missing("facts")),
        Step("notes", "This week's notes", notes_start, notes_poll, notes_missing),
    ]
    return PromptRuns(steps, command_found)


def build_program_lock(app: FastAPI):
    """lock_program(now): at kickoff, write the program's expectations once (wave B). Cheap until kickoff: it reads the
    cached schedule only; the one program call happens once per game."""
    state = app.state
    shim = SimpleNamespace(app=app)
    tried: dict[int, datetime] = {}

    async def lock_program(now: datetime) -> bool:
        from app.api.notes import _game
        from app.services.program_lock import lock_due, snapshot

        lock = state.program_lock
        try:
            game, _ok = await _game(shim, None)
        except Exception:  # noqa: BLE001 - no schedule now: nothing to lock; the loop tries again next tick
            return False
        if game is None or not lock_due(game.start_date, game.completed, now) or lock.has(game.id):
            return False
        last = tried.get(game.id)
        if last is not None and now - last < timedelta(minutes=5):
            return False  # a program that could not be read is asked again in a few minutes, not every tick
        tried[game.id] = now
        assembled = await state.program.program(game.id)
        if assembled is None:
            return False
        headlines: list[dict[str, Any]] = []
        try:
            headlines = merge_headlines(await state.feeds.all())[:8]  # the day's headlines, kept with the lock (F8 feature 1)
        except Exception:  # noqa: BLE001 - no headlines is no reason not to lock; logged
            log.warning("The headlines could not be read for the kickoff lock", exc_info=True)
        return lock.save(game.id, snapshot(assembled.data, now, headlines=headlines))

    return lock_program


def build_postgame_lock(app: FastAPI):
    """lock_postgame(now): once the AP poll after one of our finished games is out, write that game's Post-Game Program once
    (F8 feature 1, owner 2026-10-21). One game per tick, oldest first, so this season's played games back-fill over the
    first minutes after a start. Cheap when nothing is due: the cached schedule and polls only."""
    state = app.state
    tried: dict[int, datetime] = {}

    async def lock_postgame(now: datetime) -> bool:
        from app.cfbd.models import Game, TeamSP
        from app.feeds import team_matcher
        from app.services.playoff import picture
        from app.services.postgame_lock import BACKFILL_AFTER, as_of, news_for, poll_after, records_after, snapshot_after
        from app.services.race import race

        lock = state.postgame_lock
        program = state.program
        try:
            schedule = await program.fetcher.fetch("schedule", "/games", {"year": program.year, "team": program.team}, Game, DataKind.SCHEDULE)
        except Exception:  # noqa: BLE001 - no schedule now: nothing to lock; the loop tries again next tick
            return False
        if not schedule.ok:
            return False
        done = sorted((g for g in schedule.records if g.completed and isinstance(g.week, int)), key=gamekeys.order)
        pending = [g for g in done if not lock.has(g.id)]
        if not pending:
            return False
        core = await program._core()
        weeks = core["rankings"].records
        for game in pending:
            poll_week, ranks = poll_after(weeks, game)
            if not ranks.get("AP"):
                continue  # the poll after this game is not out yet
            last = tried.get(game.id)
            if last is not None and now - last < timedelta(minutes=5):
                continue
            tried[game.id] = now
            assembled = await program.program(game.id)
            if assembled is None:
                return False
            games = core["games"].records
            kickoff = _parse(game.start_date)
            backfilled = kickoff is not None and now - kickoff > BACKFILL_AFTER
            upto = as_of(games, game.week)
            the_race = race(upto, program.team, state.settings.conference, week=game.week + 1)
            sp = await program._f("sp", "/ratings/sp", {"year": program.year}, TeamSP, DataKind.SEASON_STATS)
            teams = program._teams(core["teams"])
            poll_cut = next((gamekeys.poll_order(w) for w in weeks if getattr(w, "week", None) == poll_week and (getattr(w, "season_type", None) or "regular") == (game.season_type or "regular")), None)
            weeks_upto = [w for w in weeks if poll_cut is None or gamekeys.poll_order(w) <= poll_cut]
            try:
                full = picture(weeks_upto, core["records"].records, sp.records, program.team, teams)
            except Exception:  # noqa: BLE001 - the picture is a courtesy; the lock goes on without it
                log.exception("The playoff picture could not be drawn for the Post-Game lock")
                full = None
            pic = None
            if full:
                pic = {"source": full.get("source"), "sourceLabel": full.get("sourceLabel"), "week": full.get("week"), "us": full.get("us"), "seeds": [{"seed": e.get("seed"), "school": e.get("school"), "abbreviation": e.get("abbreviation"), "isUs": e.get("isUs"), "autoBid": e.get("autoBid")} for e in (full.get("field") or []) if isinstance(e, dict)], "firstFourOut": [{"school": e.get("school"), "abbreviation": e.get("abbreviation"), "isUs": e.get("isUs")} for e in (full.get("firstFourOut") or []) if isinstance(e, dict)]}
            who = state.identity.current
            opponent = game.away_team if game.home_team == program.team else game.home_team
            them_meta = teams.get(opponent or "", {})
            items: list[dict[str, Any]] = list(program.archive.load(program.year))
            try:
                items += merge_headlines(await state.feeds.all())
            except Exception:  # noqa: BLE001 - the archive alone then; logged
                log.warning("The feeds could not be read for the Post-Game lock", exc_info=True)
            news = news_for(items, team_matcher(who.school, who.mascot), team_matcher(opponent, them_meta.get("mascot")) if opponent else None, kickoff)
            snap = snapshot_after(assembled.data, now, poll_week=poll_week, ranks=ranks, records=records_after(games, game.week), race=the_race, picture=pic, news=news, backfilled=backfilled)
            return lock.save(game.id, snap)
        return False

    return lock_postgame


def build_schedule(app: FastAPI) -> ClaudeSchedule:
    state = app.state
    shim = SimpleNamespace(app=app)  # the API helpers want something with `.app.state`

    def command() -> str:
        return state.settings.claude_command

    async def current_game() -> dict[str, Any] | None:
        from app.api.notes import _game

        try:
            game, _ok = await _game(shim, None)  # (game, whether the schedule could be read) since the final pass; the old one-value read planned no game runs (bug found 2026-10-13)
        except Exception:  # noqa: BLE001 - no schedule is a quiet "nothing to run", not a crash; logged once per tick at most
            log.warning("The Claude schedule could not read the schedule; no game runs are planned.", exc_info=True)
            return None
        kickoff = _parse(getattr(game, "start_date", None)) if game is not None else None
        if game is None or game.completed or kickoff is None or getattr(game, "start_time_tbd", False):
            return None
        return {"gameId": game.id, "home": game.home_team, "away": game.away_team, "kickoff": kickoff}

    def notes_file(game_id: int) -> dict[str, Any]:
        try:
            raw = json.loads(notes_path(state.settings.data_dir, game_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    async def data_is_current(slot: Slot) -> bool:
        if slot.game_id is not None:
            raw = notes_file(slot.game_id)
            stamp = _parse(raw.get("availabilityUpdatedAt")) if slot.kind == "injuries" else None
            stamp = stamp or _parse(raw.get("writtenAt"))
            return stamp is not None and stamp >= slot.at
        if slot.only_if_missing:
            from app.api.season_notes import _context

            primaries, conferences, _meta = await _context(shim)
            status = state.season_notes.status(primaries, conferences, datetime.now(settings_tz()).date())
            return all(r.get("savedAt") for r in status["preseason"]) and status["coachesSaved"] == status["coachesOf"]
        return False

    def settings_tz() -> Any:
        return state.settings.tzinfo

    async def start(slot: Slot, game: dict[str, Any] | None) -> dict[str, Any]:
        if slot.kind in ("notes", "injuries"):
            if game is None or game["gameId"] != slot.game_id:
                return {"error": "the game is not on the schedule any more"}
            info = {"gameId": game["gameId"], "home": game["home"], "away": game["away"], "kickoff": game["kickoff"].isoformat()}
            mode = "injuries" if slot.kind == "injuries" else "full"
            return await state.notes.start(info, command(), mode, state.settings.claude_lookup_model or None)
        from app.api.season_notes import start_season_run

        return await start_season_run(shim, slot.kind, None, slot.only_if_missing)

    def poll(slot: Slot) -> dict[str, Any]:
        if slot.kind in ("notes", "injuries"):
            runner: NotesRunner = state.notes
            if runner.running:
                return {"running": True}
            return {"running": False, "ok": bool(runner.saved and not runner.error), "error": runner.error or ("no usable answer saved" if not runner.saved else None), "changed": runner.changed}
        season = state.season_runner
        if season.running:
            return {"running": True}
        saved = [b for b in season.batches if b.state == "saved"]
        return {"running": False, "ok": bool(season.batches) and len(saved) == len(season.batches), "error": season.error or next((b.error for b in season.batches if b.error), None), "changed": None}

    def command_found() -> bool:
        return NotesRunner.resolve_command(command()) is not None

    def enabled() -> bool:
        # the Prompts phase (owner 2026-10-13): on whenever the command is found, unless Settings said otherwise
        choice = state.prefs.prefs.scheduledRuns
        return command_found() if choice is None else bool(choice)

    runs: PromptRuns = state.prompt_runs

    return ClaudeSchedule(
        ledger=Ledger(state.settings.data_dir / "claude" / "ledger.json"),
        enabled=enabled,
        command_found=command_found,
        catch_up=lambda: runs.start(all=False),
        busy=lambda: runs.running,
        current_game=current_game,
        season=lambda: state.settings.season,
        tz=ZoneInfo("America/New_York"),  # the publishers' times are Eastern, wherever this computer is
        data_is_current=data_is_current,
        start=start,
        poll=poll,
    )
