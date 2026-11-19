"""Connects Run with Claude (app/services/page_refresh.py) to this app's runners: which pieces a page holds, the window it
refreshes in, and one queue that runs them one after another with the loading bar following it (batch 4 part 3, owner
2026-11-19: "Do add all the claude code peices"). Each piece runs through the runner that wrote it, with what it holds now
and the refresh rules:

    pre        this week's notes (the full run carries the notes so far), the scouting report, the trivia, By the numbers,
               Getting there
    trivia     the next game's trivia
    post       What decided it, the weekly review, and the Circle of Blame when it is our latest final
    preseason  the season load for my primary teams
    season     the coaches, the roster costs and the school facts of our conference, the data check, the Circle of Blame
    book       the same as My Team: the season in review is My Team at the season's end
    paper      the week's stories and picks, the layout, the drawings, By the numbers
    picks      the Picks of the week

Each piece leaves a line in data/claude/refresh-log.jsonl with what it changed (page_refresh.diff).

    RefreshRuns(app)
      await check(route, now) -> {available, label, detail, reason, running}
      await start(route, now) -> {running, error, ...}
      status() -> the queue's status (PromptRuns' shape) and the page
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from app.cache import DataKind
from app.cfbd.models import Game
from app.services.notes import load_notes
from app.services.notes_task import NotesRunner
from app.services.page_refresh import Page, RefreshLog, diff, page_of
from app.services.prompt_runs import POLL_SECONDS, PromptRuns, Step
from app.services.refresh_windows import Window, window_for
from app.services.writing import WritingStore

log = logging.getLogger("kickoff.refresh")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _dump(value: Any) -> Any:
    if value is None:
        return None
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(exclude_none=True)
    if isinstance(value, dict):
        return {k: _dump(v) for k, v in value.items()}
    return value


@dataclass
class Piece:
    kind: str
    label: str
    start: Callable[[], Awaitable[dict[str, Any]]]
    poll: Callable[[], dict[str, Any]]
    read: Callable[[], Any]


class RefreshRuns:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.state = app.state
        self.shim = SimpleNamespace(app=app)
        self.runs: PromptRuns | None = None
        self.page: Page | None = None
        self.poll_seconds = POLL_SECONDS  # the tests ask faster
        self.lock = asyncio.Lock()  # two taps at once (the tablet and the desktop) start one queue, never two

    # --- the queue ---------------------------------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.runs is not None and self.runs.running

    def command_found(self) -> bool:
        return NotesRunner.resolve_command(self.state.settings.claude_command) is not None

    def status(self) -> dict[str, Any]:
        out = self.runs.status() if self.runs is not None else {"running": False, "steps": [], "startedAt": None, "finishedAt": None}
        return {**out, "page": self.page.kind if self.page else None, "label": self.page.label if self.page else None}

    async def stop(self) -> None:
        if self.runs is not None:
            await self.runs.stop()

    # --- the page ----------------------------------------------------------------------------------------------------

    async def _schedule(self) -> list[Game]:
        program = self.state.program
        schedule = await program.fetcher.fetch("schedule", "/games", {"year": program.year, "team": program.team}, Game, DataKind.SCHEDULE)
        if not schedule.ok:
            raise RuntimeError(schedule.error or "The schedule could not be read")
        return [g for g in schedule.records if isinstance(g, Game)]

    def _local(self, value: Any) -> datetime | None:
        """A CFBD time (UTC) in the server's zone, so "the Monday after" is the local Monday (batch 4's reviewer)."""
        parsed = _parse(value)
        return parsed.astimezone(self.state.settings.tzinfo) if parsed is not None else None

    async def window(self, page: Page, now: datetime) -> tuple[Window, Game | None]:
        games = await self._schedule()
        if page.kind in ("pre", "post", "trivia"):
            game = self.state.program._pick_game(games, page.game_id)
            if game is None:
                return Window(False, "That game is not on our schedule."), None
            return window_for("post" if page.kind == "post" else "pre", now=now, kickoff=self._local(game.start_date)), game
        if page.kind == "preseason":
            kicks = [k for k in (self._local(g.start_date) for g in games) if k is not None]
            return window_for("preseason", now=now, first_kickoff=min(kicks) if kicks else None), None
        # My Team, the book, the paper and the picks: the season's window (the switch after the title game ends it)
        return window_for("season", now=now), None

    async def pieces(self, page: Page, game: Game | None, now: datetime | None = None) -> list[Piece]:
        """Every piece Claude Code writes for the page (owner 2026-11-19: "Do add all the claude code peices, we want the user
        to be able ot rerun with most current info on everything"). A piece with nothing to write from yet (no story
        needing a drawing) is skipped when its turn comes, never a failure."""
        from app.services.editions import key_for

        state = self.state
        now = now or datetime.now(timezone.utc)
        slot = now.astimezone(state.settings.tzinfo).strftime("%Y-%m-%d-%H")  # the editor's and the drawings' key, as the schedule names them
        out: list[Piece] = []
        if page.kind == "pre" and game is not None and not game.completed:
            out.append(self._notes_piece(game))
            out.append(self._writing_piece("scout", str(game.id), "The scouting report"))
            out.append(self._writing_piece("trivia", str(game.id), "The trivia"))
            week_key = key_for(game.week, game.season_type)
            if week_key:
                out.append(self._writing_piece("numbers", week_key, "By the numbers"))
            if getattr(game, "venue_id", None):
                out.append(self._writing_piece("trip", str(game.venue_id), "Getting there"))
        elif page.kind == "trivia" and game is not None and not game.completed:
            out.append(self._writing_piece("trivia", str(game.id), "The trivia"))
        elif page.kind == "post" and game is not None and game.completed:
            out.append(self._writing_piece("recap", str(game.id), "What decided it"))
            out.append(self._review_piece(game))
            if await self._latest_final(game):
                out.append(self._blame_piece())
        elif page.kind == "preseason":
            out.append(self._season_piece("preseason", None, "The Preseason Magazine", lambda: _dump(state.season_notes.preseason())))
        elif page.kind in ("season", "book"):
            conference = await self._our_conference()
            if conference:
                name, schools = conference
                out.append(self._season_piece("coaches", [name], "The coaches", lambda: {s: state.season_notes.coaches_for(s) for s in schools}))
                out.append(self._season_piece("costs", [name], "Roster costs", lambda: {s: state.season_notes.costs_for(s) for s in schools}))
                out.append(self._season_piece("facts", [name], "School history and facts", lambda: {s: state.season_notes.facts_for(s) for s in schools}))
            out.append(self._writing_piece("datacheck", now.astimezone(state.settings.tzinfo).date().isoformat(), "The data check"))
            _ahead, played = await self._games_around()
            if played is not None:  # the Circle of Blame writes our latest final: none before the first
                out.append(self._blame_piece())
        elif page.kind == "paper":
            from app.writing_setup import paper_week

            key, _rows, _layout = await paper_week(self.app)
            if key:
                store = WritingStore(state.settings.data_dir, state.settings.season)
                out.append(self._writing_piece("paper", key, "The week's stories and picks"))
                out.append(self._writing_piece("editor", slot, "The paper's layout", read=lambda: store.load("editor", key)))
                out.append(self._writing_piece("art", slot, "The paper's drawings"))
            ahead, played = await self._games_around()
            ahead_key = key_for(ahead.week, ahead.season_type) if ahead is not None else None
            if ahead_key:
                out.append(self._writing_piece("numbers", ahead_key, "By the numbers"))
        elif page.kind == "picks":
            from app.services.picks import picks_week

            week = await picks_week(state)
            if isinstance(week.get("key"), str) and week["key"]:
                out.append(self._writing_piece("picks", week["key"], "The Picks of the week"))
        return out

    async def _games_around(self) -> tuple[Game | None, Game | None]:
        """(our next game not played, our last game played) on the cached schedule."""
        dated = [(k, g) for g in await self._schedule() if (k := _parse(g.start_date)) is not None]
        dated.sort(key=lambda pair: pair[0])
        ahead = next((g for _k, g in dated if not g.completed), None)
        played = next((g for _k, g in reversed(dated) if g.completed), None)
        return ahead, played

    async def _latest_final(self, game: Game) -> bool:
        """The Circle of Blame always writes our latest final: only that game's Post-Game reruns it."""
        _ahead, played = await self._games_around()
        return played is not None and played.id == game.id

    async def _our_conference(self) -> tuple[str, list[str]] | None:
        from app.api.season_notes import _context

        _primaries, conferences, _meta = await _context(self.shim)
        team = str(self.state.program.team or "").lower()
        for name, schools in conferences.items():
            if any(s.lower() == team for s in schools):
                return name, schools
        return None

    # --- the pieces --------------------------------------------------------------------------------------------------

    def _notes_piece(self, game: Game) -> Piece:
        state = self.state

        async def start() -> dict[str, Any]:
            from app.api.notes import _game_dict, with_figures

            info = await with_figures(state, _game_dict(game))
            return await state.notes.start(info, state.settings.claude_command, "full", state.settings.claude_lookup_model or None)

        def poll() -> dict[str, Any]:
            runner = state.notes
            if runner.running:
                return {"running": True}
            return {"running": False, "ok": bool(runner.saved and not runner.error), "error": runner.error or ("no usable answer saved" if not runner.saved else None), "changed": runner.changed}

        return Piece("notes", "This week's notes", start, poll, lambda: _dump(load_notes(state.settings.data_dir, game.id)[0]))

    def _writing_piece(self, kind: str, key: str, label: str, read: Callable[[], Any] | None = None) -> Piece:
        state = self.state
        store = WritingStore(state.settings.data_dir, state.settings.season)

        async def start() -> dict[str, Any]:
            from app.writing_setup import build_job

            job = await build_job(self.app, kind, key)
            if job is None:
                return {"skipped": "nothing to write from yet"}
            job.so_far = (read or (lambda: store.load(kind, key)))()  # what the page shows (the editor's layout is kept by the week)
            return await state.writing.start(job, state.settings.claude_command)

        def poll() -> dict[str, Any]:
            runner = state.writing
            if runner.running:
                return {"running": True}
            return {"running": False, "ok": bool(runner.saved and not runner.error), "error": runner.error or ("no usable answer saved" if not runner.saved else None), "changed": runner.changed}

        return Piece(kind, label, start, poll, read or (lambda: store.load(kind, key)))

    def _review_piece(self, game: Game) -> Piece:
        """The weekly review: its lessons go into data/claude/lessons.json (the earlier ones are in its packet already)."""
        from app.services.writing import Lessons

        piece = self._writing_piece("review", str(game.id), "The weekly review")
        lessons = Lessons(self.state.settings.data_dir, self.state.settings.season)
        piece.read = lambda: [row for row in lessons.load().get("lessons", []) if isinstance(row, dict) and row.get("gameId") == game.id]
        return piece

    def _blame_piece(self) -> Piece:
        """The Circle of Blame, our latest final's, written again with the report as it stands (the weekly jobs' runner)."""
        from app.jobs.circle_of_blame import NAME
        from app.jobs.weekly import JobBusy
        from app.services.blame import BlameStore

        state = self.state
        held: dict[str, Any] = {}

        async def start() -> dict[str, Any]:
            jobs = getattr(state, "jobs", None)
            if jobs is None:
                return {"skipped": "the weekly jobs are not set up"}
            try:
                run = jobs.start(NAME, refresh=True)
            except JobBusy:
                return {"error": "another weekly job is running"}
            held["id"] = run.get("id")
            return {"running": True}

        def poll() -> dict[str, Any]:
            jobs = state.jobs
            if jobs.current is not None and jobs.current.get("id") == held.get("id"):
                return {"running": True}
            run = jobs.runs.get(held["id"]) if held.get("id") else None
            status = (run or {}).get("status")
            if status == "skipped":
                return {"running": False, "skipped": (run or {}).get("message") or "nothing to write yet"}
            return {"running": False, "ok": status == "ok", "error": None if status == "ok" else (run or {}).get("message") or "the report was not written", "changed": None}

        def read() -> Any:
            latest = BlameStore(state.settings.data_dir, state.settings.season).latest()
            return latest[1] if latest else None

        return Piece("blame", "The Circle of Blame", start, poll, read)

    def _season_piece(self, kind: str, keys: list[str] | None, label: str, read: Callable[[], Any]) -> Piece:
        state = self.state

        async def start() -> dict[str, Any]:
            from app.api.season_notes import start_season_run

            return await start_season_run(self.shim, kind, keys, False, refresh=True)

        def poll() -> dict[str, Any]:
            season = state.season_runner
            if season.running:
                return {"running": True}
            saved = [b for b in season.batches if b.state == "saved"]
            return {"running": False, "ok": bool(season.batches) and len(saved) == len(season.batches), "error": season.error or next((b.error for b in season.batches if b.error), None), "changed": None}

        return Piece(kind, label, start, poll, read)

    # --- the two questions -------------------------------------------------------------------------------------------

    def _busy(self) -> str | None:
        if self.running:
            return "Claude is already refreshing a page."
        if self.state.prompt_runs.running or self.state.notes.running or self.state.season_runner.running or self.state.writing.running or getattr(getattr(self.state, "jobs", None), "running", False):
            return "Claude Code is busy with another run; try again when the loading bar is gone."
        return None

    async def check(self, route: Any, now: datetime) -> dict[str, Any]:
        page = page_of(route)
        none = {"available": False, "running": self.running, "label": None, "detail": None, "reason": None}
        if page is None:
            return {**none, "reason": "Claude wrote nothing on this page."}
        if not self.command_found():
            return {**none, "label": page.label, "reason": "Claude Code's command was not found on the server computer."}
        try:
            window, game = await self.window(page, now)
            pieces = await self.pieces(page, game, now) if window.open else []
        except Exception as exc:  # noqa: BLE001 - the row stays hidden, said in the log
            log.exception("Run with Claude could not size up %s", route)
            return {**none, "label": page.label, "reason": f"{exc.__class__.__name__}: {exc}"}
        if not window.open:
            return {**none, "label": page.label, "reason": window.reason}
        if not pieces:
            return {**none, "label": page.label, "reason": "Nothing of Claude's to refresh here yet."}
        words = [p.label[0].lower() + p.label[1:] for p in pieces]
        names = words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"
        return {"available": True, "running": self.running, "label": page.label, "detail": f"Refresh {names}", "reason": window.reason}

    async def start(self, route: Any, now: datetime) -> dict[str, Any]:
        if self.lock.locked():
            return {"running": True, "error": "Claude is already starting a refresh."}
        async with self.lock:
            return await self._start(route, now)

    async def _start(self, route: Any, now: datetime) -> dict[str, Any]:
        page = page_of(route)
        if page is None:
            return {"running": False, "error": "Claude wrote nothing on this page."}
        busy = self._busy()
        if busy:
            return {"running": self.running, "error": busy}
        window, game = await self.window(page, now)
        if not window.open:
            return {"running": False, "error": window.reason}
        pieces = await self.pieces(page, game, now)
        if not pieces:
            return {"running": False, "error": "Nothing of Claude's to refresh here yet."}
        book = RefreshLog(self.state.settings.data_dir)
        run_at = now.isoformat(timespec="seconds")
        steps = [self._step(piece, page, route, run_at, book) for piece in pieces]
        self.page = page
        self.runs = PromptRuns(steps, self.command_found, poll_seconds=self.poll_seconds)
        log.info("Run with Claude: %s (%s), %d pieces.", page.label, route, len(steps))
        return await self.runs.start(all=True)

    def _step(self, piece: Piece, page: Page, route: str, run_at: str, book: RefreshLog) -> Step:
        held: dict[str, Any] = {}

        async def start(_all: bool) -> dict[str, Any]:
            try:
                held["before"] = piece.read()
            except Exception:  # noqa: BLE001 - the log line says so; the run goes on
                log.exception("Run with Claude: %s could not be read before the run", piece.kind)
                held["before"] = None
            try:
                status = await piece.start()
            except Exception as exc:
                book.add({"runAt": run_at, "route": route, "page": page.kind, "gameId": page.game_id, "piece": piece.kind, "ok": False, "error": f"{exc.__class__.__name__}: {exc}", "changes": None})
                raise  # the queue logs it with its traceback and goes on to the next piece
            if not isinstance(status, dict):
                status = {}
            if status.get("error"):  # a busy runner refuses with running: True; that is no start
                status = {**status, "running": False}
                book.add({"runAt": run_at, "route": route, "page": page.kind, "gameId": page.game_id, "piece": piece.kind, "ok": False, "error": status.get("error"), "changes": None})
            elif status.get("skipped"):
                book.add({"runAt": run_at, "route": route, "page": page.kind, "gameId": page.game_id, "piece": piece.kind, "ok": True, "skipped": status.get("skipped"), "changes": None})
            return status

        def poll() -> dict[str, Any]:
            result = piece.poll()
            if isinstance(result, dict) and not result.get("running") and not held.get("logged"):
                held["logged"] = True
                try:
                    after = piece.read()
                except Exception:  # noqa: BLE001
                    log.exception("Run with Claude: %s could not be read after the run", piece.kind)
                    after = None
                book.add({"runAt": run_at, "route": route, "page": page.kind, "gameId": page.game_id, "piece": piece.kind, "ok": bool(result.get("ok")), "error": result.get("error"), "changes": diff(held.get("before"), after)})
            return result

        async def missing() -> str | None:
            return "refresh"

        return Step(piece.kind, piece.label, start, poll, missing)
