"""Claude Code on a schedule (Phase 18.7, owner 2026-10-08: "as few runs as quality allows", never continuous, timed to when
each source publishes, nothing after the game).

A game week is three runs:

    notes             Monday 18:00 Eastern: the written notes, depth charts, TV crew and coaches (the head coach's Monday
                      press conference and the school's game notes are out). One run.
    injuries-first    Wednesday 21:00 Eastern: the first availability report (a conference that requires one publishes its first on Wednesday).
                      A small run that merges only the report into the notes. Skipped when the notes are newer.
    injuries-last     75 minutes before kickoff: the final report (such a conference publishes it 90 minutes before). Same small run.

and the season has a few: the whole-season load in August (once, if anything is missing), again after the December and
January coaching changes, and the roster costs after each transfer-portal window. A bye week has no game, so no runs. After
the final nothing runs: CFBD's post-game numbers arrive on their own (app/cfbd/publish.py) and the Archive's second look is
app/maintenance.py. The times are the publishers' habits, not promises; the ledger shows when each run found something new,
so they can be tuned after a few weeks.

A slot is run once. A failed run is tried once more twenty minutes later, then left until the next slot. Three failures in
a row pause every scheduled run for six hours. A slot is skipped when the data is already newer than the slot (the owner
pasted it), and a slot whose window has passed is not run late. The runs go through the same locked-down runners as the
buttons (app/services/notes_task.py, season_task.py): web search only, the app writes the files.

    game_slots(game_id, kickoff, tz)    -> [Slot]   pure
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
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.answers import atomic_write

log = logging.getLogger("kickoff.schedule")

NOTES_HOUR = 18  # Monday, local time
FIRST_REPORT_HOUR = 21  # Wednesday, local time
LAST_REPORT_BEFORE_KICKOFF = timedelta(minutes=75)
RETRY_AFTER = timedelta(minutes=20)
MAX_ATTEMPTS = 2
BREAKER_FAILURES = 3
BREAKER_PAUSE = timedelta(hours=6)
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


def _local(day: date, hour: int, tz: Any) -> datetime:
    return datetime.combine(day, time(hour, 0), tzinfo=tz).astimezone(timezone.utc)


def game_slots(game_id: int, kickoff: datetime, tz: Any) -> list[Slot]:
    """The three runs of a game week. `kickoff` is timezone-aware."""
    kick = kickoff.astimezone(timezone.utc)
    day = kickoff.astimezone(tz).date()
    monday = day - timedelta(days=day.weekday())
    notes_at = min(_local(monday, NOTES_HOUR, tz), kick - timedelta(hours=48))  # a Tuesday or Wednesday game still gets its notes run first
    back = (day.weekday() - 2) % 7
    wednesday = day - timedelta(days=back)
    first_at = min(_local(wednesday, FIRST_REPORT_HOUR, tz), kick - timedelta(hours=30)) if back <= 4 else kick - timedelta(hours=30)  # a Sunday or Monday game has no Wednesday in its own week
    last_at = kick - LAST_REPORT_BEFORE_KICKOFF
    return [
        Slot(f"notes:{game_id}", "notes", "The week's notes", notes_at, kick - timedelta(hours=3), game_id),
        Slot(f"injuries-first:{game_id}", "injuries", "The first availability report", first_at, kick - timedelta(hours=2), game_id),
        Slot(f"injuries-last:{game_id}", "injuries", "The final availability report", last_at, kick + timedelta(minutes=5), game_id),
    ]


def season_slots(year: int, tz: Any) -> list[Slot]:
    """The season's triggers falling in the school year that holds `year`'s season: Aug to May of year, year + 1."""
    slots: list[Slot] = []
    for month, dom, kind, only_missing in SEASON_TRIGGERS:
        slot_year = year if month >= 8 else year + 1
        at = _local(date(slot_year, month, dom), 9, tz)
        label = {"season": "The season load", "coaches": "The coaching staffs", "costs": "Roster costs"}[kind]
        slots.append(Slot(f"{kind}:{slot_year}-{month:02d}", kind, label, at, at + timedelta(days=14), None, only_missing))
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
    ) -> None:
        self.ledger = ledger
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

    def upcoming(self, game: dict[str, Any] | None, now: datetime) -> list[Slot]:
        slots: list[Slot] = []
        if game and isinstance(game.get("kickoff"), datetime) and isinstance(game.get("gameId"), int):
            slots += game_slots(game["gameId"], game["kickoff"], self.tz)
        slots += season_slots(self.season(), self.tz) + season_slots(self.season() - 1, self.tz)
        return sorted((s for s in slots if s.until > now), key=lambda s: s.at)

    def due(self, game: dict[str, Any] | None, now: datetime) -> Slot | None:
        for slot in self.upcoming(game, now):
            if slot.at > now:
                break
            if self.ledger.succeeded(slot.key) or self.ledger.attempts(slot.key) >= MAX_ATTEMPTS:
                continue
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
        game = await self.current_game()
        slot = self.due(game, now)
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
        nxt = [s for s in self.upcoming(game, now) if not self.ledger.succeeded(s.key)][:4]
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
