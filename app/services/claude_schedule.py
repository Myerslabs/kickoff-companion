"""Claude Code on a schedule (Phase 18.7, owner 2026-10-08: "as few runs as quality allows", never continuous, timed to when
each source publishes, nothing after the game).

P4 (owner 2026-10-25: Claude Code doing more each week) adds the game week's other runs, each filling only its part of the
notes or writing its own piece, and the morning after:

    Monday 10 AM      the depth charts, the schemes, the staffs and the TV crew (the notes' parts, merged)
    Monday 1 PM       the scouting report on the opponent
    Wednesday 7 PM    the availability report (merged)
    Thursday noon     the paper's stories and the Picks of the week
    Thursday 7 PM     the availability report again
    Friday noon       the recruits visiting (merged)
    Friday 3 PM       the game-day trivia
    kickoff + 14 h    the post-game piece, what decided it
    kickoff + 15 h    the weekly review: the notes against the box score, the lessons and the prompt's additions
    Tuesday 10 AM     the weekly data check, every week
    every 2 hours     the paper laid out by Claude, 7 AM to 9 PM, only when new stories came in (FEAT-14 wave 4)
    10 AM and 4 PM    drawings for the paper's placed stories with no picture, two a run (FEAT-14 wave 4)

Each one only before the notes' last run, two hours before kickoff, so the program locks with everything in. The whole-week
run below stays the one that fills everything (the Prompts phase, wave B, owner 2026-10-13: "I want the pre-game program to
run once at the most accurate time"):

    notes             two hours before kickoff: the written notes, the availability report (a conference that requires one
                      publishes its final report 90 minutes before), both depth charts, the TV crew and the coaches, in
                      one answer. The program is locked at kickoff right after (app/services/program_lock.py).

Until then (Phase 18.7) it was three: Monday's notes, Wednesday's first report, the final report 75 minutes before; the
injuries-only merge stays in the runner for a run by hand.

and the season has a few: the whole-season load in August (once, if anything is missing), again after the December and
January coaching changes, and the roster costs after each transfer-portal window. A bye week has no game, so no runs. After
the final nothing runs: CFBD's post-game numbers arrive on their own (app/cfbd/publish.py) and the Archive's second look is
app/maintenance.py. The times are the publishers' habits, not promises; the ledger shows when each run found something new,
so they can be tuned after a few weeks.

The schedule is a choice (Kickoff Companion 2.0): off until Settings turns it on, since each run uses the person's own Claude
plan, and only ever with Claude Code's command found. Its first tick each day runs "everything that is missing" (app/services/prompt_runs.py, the same run as
`python -m app prompts`), so an install with Claude Code starts loading by itself; a slot never starts while that run is busy.

A slot is run once. A failed run is tried once more twenty minutes later, then left until the next slot. Three failures in
a row pause every scheduled run for six hours. A slot is skipped when the data is already newer than the slot (the owner
pasted it), and a slot whose window has passed is not run late. The runs go through the same locked-down runners as the
buttons (app/services/notes_task.py, season_task.py): web search only, the app writes the files.

    game_slots(game_id, kickoff, tz)    -> [Slot]   pure
    week_slots(game_id, kickoff, tz, week)  -> [Slot]   the game week's other runs (P4); pure
    after_slots(game_id, kickoff)       -> [Slot]   the morning after our game (P4); pure
    weekly_slots(now, tz)               -> [Slot]   the weekly data check (P4); pure
    paper_slots(now, tz)                -> [Slot]   the paper's editor and drawings today (FEAT-14 wave 4); pure
    season_slots(year, tz)              -> [Slot]   pure
    Ledger(path)                        what ran and what came of it
    ClaudeSchedule(...).tick()          one decision; .start()/.stop() run the loop
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone  # noqa: F401 - time: the season slots' hour
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write

log = logging.getLogger("kickoff.schedule")

NOTES_BEFORE_KICKOFF = timedelta(hours=2)  # after the final availability report, before the program locks at kickoff
NOTES_UNTIL_AFTER_KICKOFF = timedelta(minutes=5)
RETRY_AFTER = timedelta(minutes=20)
MAX_ATTEMPTS = 2
BREAKER_FAILURES = 3
BREAKER_PAUSE = timedelta(hours=6)
CATCH_UP_KEY = "catch-up"
CATCH_UP_EVERY = timedelta(hours=20)  # once a day, whatever hour the server started
LEDGER_KEEP = 200
TICK_SECONDS = 120

# (month, day, kind): the season's own triggers. The load runs once if anything is missing in August (after media days
# and the preseason polls); the staffs change in December and January; the costs follow each portal window.
SEASON_TRIGGERS: tuple[tuple[int, int, str, bool], ...] = (
    (8, 22, "season", True),  # after fall practice (owner 2026-10-09): the depth charts and staffs are set; only when something is not loaded
    (12, 15, "coaches", False),  # the staffs change in December and January: the coaches prompt only, never the whole season load again
    (1, 20, "coaches", False),
    (1, 25, "costs", False),
    (5, 10, "costs", False),
)


@dataclass(frozen=True)
class Slot:
    key: str  # unique and stable: the ledger remembers it
    kind: str  # notes | injuries | season | costs
    label: str
    at: datetime  # UTC, not before
    until: datetime  # UTC, not after
    game_id: int | None = None
    only_if_missing: bool = False
    mode: str | None = None  # P4: "parts:lineups,..." for a notes run of some parts
    writing_key: str | None = None  # P4: the key a writing run is saved under (a game id, "week-8", a day)
    season: int | None = None  # rollover R1: the season the run is for; it waits while the app is on another


def _local(day: date, hour: int, tz: Any) -> datetime:
    return datetime.combine(day, time(hour, 0), tzinfo=tz).astimezone(timezone.utc)


def game_slots(game_id: int, kickoff: datetime, tz: Any) -> list[Slot]:
    """The one run of a game week: the notes two hours before kickoff. `kickoff` is timezone-aware; `tz` is kept for the
    callers and the season slots."""
    kick = kickoff.astimezone(timezone.utc)
    return [Slot(f"notes:{game_id}", "notes", "The game's notes", kick - NOTES_BEFORE_KICKOFF, kick + NOTES_UNTIL_AFTER_KICKOFF, game_id)]


WEEK_RUNS: tuple[tuple[int, int, str, str, str | None, str], ...] = (  # (weekday, hour ET, key, kind, notes parts, label)
    (0, 10, "parts-mon", "parts", "lineups,schemes,coaches,broadcast", "Monday: the depth charts, schemes, staffs and TV crew"),
    (0, 13, "scout", "scout", None, "The scouting report"),
    (2, 19, "parts-wed", "parts", "availability", "Wednesday's availability report"),
    (3, 10, "numbers", "numbers", None, "By the numbers"),  # Wave 6 (owner 2026-11-15): the paper's own article, page 2's lead
    (3, 12, "paper", "paper", None, "The week's stories and picks"),
    (3, 14, "picks", "picks", None, "Picks of the week"),  # FEAT-2: every game, after the paper
    (3, 19, "parts-thu", "parts", "availability", "Thursday's availability report"),
    (4, 12, "parts-fri", "parts", "visitors", "Friday: the recruits visiting"),
    (4, 15, "trivia", "trivia", None, "Game-day trivia"),
)
WEEK_RUN_HOURS = timedelta(hours=10)
RECAP_AFTER = timedelta(hours=14)
REVIEW_AFTER = timedelta(hours=15)
AFTER_FOR = timedelta(days=4)


def week_slots(game_id: int, kickoff: datetime, tz: Any, week: int | None = None, season_type: str | None = None) -> list[Slot]:
    """The game week's other runs (P4), on the days of the week the game is played in, each before the notes' last run.
    A Thursday game keeps only what falls before its kickoff."""
    kick = kickoff.astimezone(timezone.utc)
    last = kick - NOTES_BEFORE_KICKOFF
    local = kickoff.astimezone(tz)
    monday = local.date() - timedelta(days=local.weekday())
    slots: list[Slot] = []
    for weekday, hour, key, kind, parts, label in WEEK_RUNS:
        at = _local(monday + timedelta(days=weekday), hour, tz)
        if at >= last:
            continue
        if kind in ("paper", "picks", "numbers"):
            # the edition's key (rollover R1, 2026-11-15): "week-8", or "postseason" for a bowl, which CFBD calls week 1 (keyed
            # week-1, the bowl's paper and numbers wrote over the regular season's Week 1 and its picks never ran)
            from app.services.editions import key_for

            writing: str | None = key_for(week, season_type)
            if writing is None:
                continue
        elif kind in ("scout", "trivia"):
            writing = str(game_id)
        else:
            writing = None
        until = min(at + WEEK_RUN_HOURS, last) if kind == "parts" else kick
        slot_key = f"{key}:{writing}" if kind in ("paper", "picks", "numbers") else f"{key}:{game_id}"
        slots.append(Slot(slot_key, kind, label, at, until, game_id, mode=f"parts:{parts}" if parts else None, writing_key=writing))
    return slots


def after_slots(game_id: int, kickoff: datetime) -> list[Slot]:
    """The morning after our game (P4): what decided it, then the weekly review."""
    kick = kickoff.astimezone(timezone.utc)
    return [
        Slot(f"recap:{game_id}", "recap", "What decided it", kick + RECAP_AFTER, kick + AFTER_FOR, game_id, writing_key=str(game_id)),
        Slot(f"review:{game_id}", "review", "The weekly review", kick + REVIEW_AFTER, kick + AFTER_FOR, game_id, writing_key=str(game_id)),
    ]


def weekly_slots(now: datetime, tz: Any) -> list[Slot]:
    """The weekly data check (P4): Tuesday 10 AM Eastern, this week's and next week's."""
    local = now.astimezone(tz)
    tuesday = local.date() - timedelta(days=local.weekday()) + timedelta(days=1)
    slots = []
    for day in (tuesday, tuesday + timedelta(days=7)):
        at = _local(day, 10, tz)
        slots.append(Slot(f"datacheck:{day.isoformat()}", "datacheck", "The weekly data check", at, at + timedelta(days=2), None, writing_key=day.isoformat()))
    return slots


EDITOR_HOURS = (7, 9, 11, 13, 15, 17, 19, 21)  # owner's plan 2026-10-27: at most every two hours, 7 AM to 11 PM
ART_HOURS = (10, 16)


def paper_slots(now: datetime, tz: Any, weekly: bool = False) -> list[Slot]:
    """Today's paper runs (FEAT-14 wave 4, Eastern time): the editor every two hours, the drawings twice. The schedule skips
    one when nothing changed (no new story since the editor's last run, no story that needs a drawing). weekly (rollover R3,
    owner 2026-11-15 "Claude, once a week"): the off-season paper turns over Monday at 6 AM, so the editor runs Monday at 7
    and the drawings at 10, each with two days to run in."""
    if weekly:
        local = now.astimezone(tz).date()
        monday = local - timedelta(days=local.weekday())
        return [
            Slot(f"editor:{monday.isoformat()}-07", "editor", "The off-season paper laid out by Claude", _local(monday, 7, tz), _local(monday, 7, tz) + timedelta(days=2), None, writing_key=f"{monday.isoformat()}-07"),
            Slot(f"art:{monday.isoformat()}-10", "art", "Drawings for the off-season paper", _local(monday, 10, tz), _local(monday, 10, tz) + timedelta(days=2), None, writing_key=f"{monday.isoformat()}-10"),
        ]
    day = now.astimezone(tz).date()
    slots = [Slot(f"editor:{day.isoformat()}-{h:02d}", "editor", "The paper laid out by Claude", _local(day, h, tz), _local(day, h, tz) + timedelta(hours=2), None, writing_key=f"{day.isoformat()}-{h:02d}") for h in EDITOR_HOURS]
    slots += [Slot(f"art:{day.isoformat()}-{h:02d}", "art", "Drawings for the paper", _local(day, h, tz), _local(day, h, tz) + timedelta(hours=6), None, writing_key=f"{day.isoformat()}-{h:02d}") for h in ART_HOURS]
    return slots


TRIP_HOUR = 14  # Monday 2 PM Eastern, after the morning's parts run


def trip_slots(venues: list[Any], now: datetime, tz: Any, season: int) -> list[Slot]:
    """Getting there (ENH-15, owner 2026-10-24: "Just the primary teams"): once a season for each primary team's stadium and
    our next game's, from this week's Monday 2 PM; the schedule skips a stadium already written this season."""
    local = now.astimezone(tz)
    at = _local(local.date() - timedelta(days=local.weekday()), TRIP_HOUR, tz)
    wanted = [v for v in dict.fromkeys(venues) if isinstance(v, int) and not isinstance(v, bool)]
    return [Slot(f"trip:{season}:{v}", "trip", "Getting there", at, at + timedelta(days=7), None, writing_key=str(v)) for v in wanted]


def switch_slots(season: int, switched: datetime | None, ledger: Ledger, tz: Any) -> list[Slot]:
    """Rollover R2: the staffs and the costs for `season` whose two weeks closed before the app moved to it (CFBD listed the
    season late), none of them tried and none still to come, run once from the switch, two weeks to do it."""
    if switched is None:
        return []
    slots: list[Slot] = []
    labels = {"coaches": "The coaching staffs", "costs": "Roster costs"}
    for kind, label in labels.items():
        mine = [s for s in season_slots(season - 1, tz) + season_slots(season, tz) if s.kind == kind and s.season == season]
        missed = [s for s in mine if s.until <= switched]
        to_come = any(s.until > switched for s in mine)  # a run still open or ahead (January's after an early switch, May's costs) does it
        if missed and not to_come and not any(ledger.last_attempt(s.key) is not None for s in mine):
            slots.append(Slot(f"{kind}:after-switch-{season}", kind, label, switched, switched + timedelta(days=14), None, False, season=season))
    return slots


def season_slots(year: int, tz: Any) -> list[Slot]:
    """The season's triggers falling in the school year that holds `year`'s season: Aug to May of year, year + 1."""
    slots: list[Slot] = []
    for month, dom, kind, only_missing in SEASON_TRIGGERS:
        slot_year = year if month >= 8 else year + 1
        at = _local(date(slot_year, month, dom), 9, tz)
        label = {"season": "The season load", "coaches": "The coaching staffs", "costs": "Roster costs"}[kind]
        # rollover R1 (2026-11-15): December's and January's staffs and the winter and spring portals' costs are the coming
        # season's; they write into whatever season the app is on, so they wait until it is on that one (2026's never lost)
        target = year if kind == "season" else year + 1
        slots.append(Slot(f"{kind}:{slot_year}-{month:02d}", kind, label, at, at + timedelta(days=14), None, only_missing, season=target))
    return slots


class Ledger:
    """data/claude/ledger.json: one row per attempt, newest last, the last LEDGER_KEEP kept."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.rows = self._read()

    def _read(self) -> list[dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        rows = raw.get("runs") if isinstance(raw, dict) else None
        return [r for r in rows if isinstance(r, dict) and isinstance(r.get("key"), str)] if isinstance(rows, list) else []

    def add(self, row: dict[str, Any]) -> None:
        self.rows = [*self.rows, row][-LEDGER_KEEP:]
        try:
            atomic_write(self.path, json.dumps({"runs": self.rows}, indent=1) + "\n")
        except OSError as exc:
            log.warning("Could not write the Claude ledger: %s", exc)

    def attempts(self, key: str) -> int:
        return sum(1 for r in self.rows if r["key"] == key)

    def succeeded(self, key: str) -> bool:
        return any(r["key"] == key and r.get("ok") for r in self.rows)

    def last_attempt(self, key: str) -> datetime | None:
        times = [r.get("finishedAt") for r in self.rows if r["key"] == key and isinstance(r.get("finishedAt"), str)]
        try:
            return datetime.fromisoformat(max(times).replace("Z", "+00:00")) if times else None
        except ValueError:
            return None

    def trailing_failures(self) -> int:
        count = 0
        for row in reversed(self.rows):
            if row.get("ok"):
                break
            count += 1
        return count


@dataclass
class Pending:
    slot: Slot
    started: datetime
    attempt: int


class ClaudeSchedule:
    """`actions` supplies what the schedule cannot know on its own; every callable may be async or plain."""

    def __init__(
        self,
        *,
        ledger: Ledger,
        enabled: Callable[[], bool],
        command_found: Callable[[], bool],
        current_game: Callable[[], Awaitable[dict[str, Any] | None]],
        season: Callable[[], int],
        tz: Any,
        data_is_current: Callable[[Slot], Awaitable[bool]],
        start: Callable[[Slot, dict[str, Any] | None], Awaitable[dict[str, Any]]],
        poll: Callable[[Slot], dict[str, Any]],
        clock: Callable[[], datetime] | None = None,
        catch_up: Callable[[], Awaitable[dict[str, Any]]] | None = None,
        busy: Callable[[], bool] | None = None,
        last_game: Callable[[], Awaitable[dict[str, Any] | None]] | None = None,
        writing: bool = False,
        switched_at: Callable[[], datetime | None] | None = None,
        offseason: Callable[[datetime], Awaitable[bool]] | None = None,
    ) -> None:
        self.offseason = offseason  # rollover R3: whether the paper is the off-season's (its runs once a week), asked each tick
        self.paper_weekly = False
        self.switched_at = switched_at  # rollover R2: when the app moved to this season, for the runs it missed
        self.last_game = last_game  # P4: our latest final, for the morning after
        self.writing = writing  # P4: the game week's other runs and the weekly ones; off in the tests made before them
        self.ledger = ledger
        self.catch_up = catch_up  # the one run of everything missing (the Prompts phase); None in the tests that have none
        self.busy = busy or (lambda: False)
        self.enabled = enabled
        self.command_found = command_found
        self.current_game = current_game
        self.season = season
        self.tz = tz
        self.data_is_current = data_is_current
        self._start = start
        self._poll = poll
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.pending: Pending | None = None
        self.paused_until: datetime | None = None
        self._task: asyncio.Task[Any] | None = None

    # --- what is next -------------------------------------------------------------------------------------

    def upcoming(self, game: dict[str, Any] | None, now: datetime, last: dict[str, Any] | None = None) -> list[Slot]:
        slots: list[Slot] = []
        if game and isinstance(game.get("kickoff"), datetime) and isinstance(game.get("gameId"), int):
            slots += game_slots(game["gameId"], game["kickoff"], self.tz)
            if self.writing:
                slots += week_slots(game["gameId"], game["kickoff"], self.tz, game.get("week") if isinstance(game.get("week"), int) else None, game.get("seasonType") if isinstance(game.get("seasonType"), str) else None)
        if self.writing:
            if last and isinstance(last.get("kickoff"), datetime) and isinstance(last.get("gameId"), int):
                slots += after_slots(last["gameId"], last["kickoff"])
            slots += weekly_slots(now, self.tz)
            slots += paper_slots(now, self.tz, weekly=self.paper_weekly)
            if game and isinstance(game.get("venues"), list):
                slots += trip_slots(game["venues"], now, self.tz, self.season())
        slots += season_slots(self.season(), self.tz) + season_slots(self.season() - 1, self.tz)
        if self.switched_at is not None:
            slots += switch_slots(self.season(), self.switched_at(), self.ledger, self.tz)
        return sorted((s for s in slots if s.until > now), key=lambda s: s.at)

    def due(self, game: dict[str, Any] | None, now: datetime, last: dict[str, Any] | None = None) -> Slot | None:
        for slot in self.upcoming(game, now, last):
            if slot.at > now:
                break
            if self.ledger.succeeded(slot.key) or self.ledger.attempts(slot.key) >= MAX_ATTEMPTS:
                continue
            if slot.season is not None and slot.season != self.season():
                continue  # rollover R1: a run for another season waits for the app to be on it
            last = self.ledger.last_attempt(slot.key)
            if last is not None and now - last < RETRY_AFTER:
                continue
            return slot
        return None

    # --- one decision -------------------------------------------------------------------------------------

    async def tick(self) -> str:
        """Returns what it did, for the log and the tests."""
        now = self._clock()
        if self.pending is not None:
            return await self._finish(now)
        if not self.enabled():
            return "off"
        if not self.command_found():
            return "no command"
        if self.paused_until is not None:
            if now < self.paused_until:
                return "paused"
            self.paused_until = None
        if self.busy():
            return "busy"  # the one run (the page's button, the command line or the catch-up) has the runners
        if self.catch_up is not None:
            last = self.ledger.last_attempt(CATCH_UP_KEY)
            if last is None or now - last >= CATCH_UP_EVERY:
                status = await self.catch_up()
                started = bool(status.get("running")) if isinstance(status, dict) else False
                self.ledger.add({"key": CATCH_UP_KEY, "kind": CATCH_UP_KEY, "ok": started, "error": None if started else str((status or {}).get("error") or "did not start") if isinstance(status, dict) else "did not start", "startedAt": _iso(now), "finishedAt": _iso(now)})
                if started:
                    log.info("Claude catch-up started: everything that is missing.")
                    return "catch-up started"
        if self.offseason is not None:
            try:
                self.paper_weekly = bool(await self.offseason(now))
            except Exception:  # noqa: BLE001 - the paper's runs keep their daily rhythm when the season cannot be read; logged
                log.exception("Could not tell whether the paper is the off-season's")
                self.paper_weekly = False
        game = await self.current_game()
        last = await self.last_game() if self.last_game is not None else None
        slot = self.due(game, now, last)
        if slot is None:
            return "nothing due"
        if await self.data_is_current(slot):
            self.ledger.add({"key": slot.key, "kind": slot.kind, "gameId": slot.game_id, "ok": True, "skipped": "the data was already newer than the slot", "finishedAt": _iso(now)})
            log.info("Claude run %s skipped: the data is already current.", slot.key)
            return f"skipped {slot.key}"
        status = await self._start(slot, game)
        if status.get("error") and not status.get("running"):
            self._record(slot, now, now, False, str(status["error"]), None)
            self._maybe_trip(now)
            return f"could not start {slot.key}"
        self.pending = Pending(slot, now, self.ledger.attempts(slot.key) + 1)
        log.info("Claude run %s started (attempt %d).", slot.key, self.pending.attempt)
        return f"started {slot.key}"

    async def _finish(self, now: datetime) -> str:
        pending = self.pending
        assert pending is not None
        result = self._poll(pending.slot)
        if result.get("running"):
            return "running"
        self.pending = None
        ok = bool(result.get("ok"))
        self._record(pending.slot, pending.started, now, ok, None if ok else str(result.get("error") or "the run did not finish"), result.get("changed"))
        if ok:
            log.info("Claude run %s finished%s.", pending.slot.key, "" if result.get("changed") is None else (", with new information" if result.get("changed") else ", nothing new"))
        else:
            log.warning("Claude run %s failed: %s", pending.slot.key, result.get("error"))
            self._maybe_trip(now)
        return f"finished {pending.slot.key}"

    def _record(self, slot: Slot, started: datetime, finished: datetime, ok: bool, error: str | None, changed: Any) -> None:
        row: dict[str, Any] = {"key": slot.key, "kind": slot.kind, "gameId": slot.game_id, "attempt": self.ledger.attempts(slot.key) + 1, "startedAt": _iso(started), "finishedAt": _iso(finished), "ok": ok}
        if error:
            row["error"] = error[:300]
        if isinstance(changed, bool):
            row["changed"] = changed
        self.ledger.add(row)

    def _maybe_trip(self, now: datetime) -> None:
        if self.ledger.trailing_failures() >= BREAKER_FAILURES:
            self.paused_until = now + BREAKER_PAUSE
            log.warning("Claude runs failed %d times in a row; paused for %d hours.", BREAKER_FAILURES, BREAKER_PAUSE.total_seconds() // 3600)

    # --- what the page shows ------------------------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        now = self._clock()
        game = await self.current_game()
        last = await self.last_game() if self.last_game is not None else None
        nxt = [s for s in self.upcoming(game, now, last) if not self.ledger.succeeded(s.key)][:6]
        return {
            "enabled": self.enabled(),
            "commandFound": self.command_found(),
            "running": self.pending.slot.key if self.pending else None,
            "pausedUntil": _iso(self.paused_until) if self.paused_until and self.paused_until > now else None,
            "next": [{"key": s.key, "label": s.label, "at": _iso(s.at), "until": _iso(s.until)} for s in nxt],
            "recent": list(reversed(self.ledger.rows[-12:])),
        }

    # --- the loop -----------------------------------------------------------------------------------------

    async def _loop(self) -> None:
        await asyncio.sleep(45)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop must survive; logged with the traceback
                log.exception("The Claude schedule hit an error; it will look again shortly.")
            await asyncio.sleep(TICK_SECONDS)

    def start(self) -> None:
        loop = asyncio.get_running_loop()
        if self._task is None or self._task.done() or self._task.get_loop() is not loop:
            self._task = loop.create_task(self._loop())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            if task.get_loop() is asyncio.get_running_loop():
                with contextlib.suppress(asyncio.CancelledError):
                    await task


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
