"""Publication schedules (Phase 14): data CFBD changes on a known rhythm is kept until it can change.

Before Phase 14 every season-long answer (SP+, the polls, season stats) lived an hour on weekends and
six hours otherwise, so opening the Ratings page on a Saturday cost fresh calls for numbers that had
not moved since Sunday. Now each such endpoint belongs to a schedule: a set of weekly slots (US
Eastern, the clock the polls are announced on) after which the data can change. An answer stays
fresh until the next slot.

Some sources land at no fixed minute (CFBD loads SP+ some time after Bill Connelly publishes it, and
the polls within an hour of their announcement). For those the schedule has a recheck: after a slot,
while the answer still matches the one from before the slot, it is asked for again every `recheck`
until it changes or `watch` runs out. Each change is written to the `publications` table with its
time, so the Status page can show when each source really lands and the slots can be tuned.

`prewarm` schedules are refreshed by the server's own task (app/main.py, `_prewarm_published`) soon
after a slot passes, so a page opened later finds them already fresh and makes no call. Only keys a
page asked for in the last `PREWARM_RECENT` are refreshed that way.

Answers of a finished game, the live feed, the scoreboard and the ticker never follow a schedule.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.cache import DataKind
from app.db import Database

log = logging.getLogger("kickoff.publish")

EASTERN = ZoneInfo("America/New_York")
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
EVERY_DAY = (MON, TUE, WED, THU, FRI, SAT, SUN)
# Kinds a schedule may replace. A caller asking for FINISHED_GAME, LIVE, SCOREBOARD, TICKER, LINES or
# WEATHER keeps its own rule even on a scheduled endpoint.
SCHEDULABLE = {DataKind.SEASON_STATS, DataKind.SCHEDULE, DataKind.RECRUITING}
PREWARM_RECENT = timedelta(days=14)
ASKED_WRITE_EVERY = timedelta(hours=1)
MIN_LIFETIME = timedelta(minutes=5)  # a slot a few seconds away must not cause a call per page load


@dataclass(frozen=True)
class Slot:
    days: tuple[int, ...]  # Monday is 0
    hour: int
    minute: int = 0


@dataclass(frozen=True)
class Schedule:
    name: str
    label: str  # how the Status page names it
    slots: tuple[Slot, ...]
    recheck: timedelta | None = None  # while unchanged after a slot, ask again this often
    watch: timedelta = timedelta(0)  # for this long after the slot
    prewarm: bool = False
    prewarm_recent: timedelta = PREWARM_RECENT
    after_games: bool = False  # slots follow the days games are played (see game_days); `slots` is the fallback

    def _candidates(self, around: datetime) -> list[datetime]:
        """Slot times (UTC) in the weeks either side of `around`."""
        local = around.astimezone(EASTERN)
        monday = (local - timedelta(days=local.weekday())).date()
        out: list[datetime] = []
        if self.after_games:
            near = [d for d in _game_days if abs((d - local.date()).days) <= GAME_DAY_REACH]
            if near:
                for day in near:
                    out.append(_eastern(day + timedelta(days=1), 4))
                    if day.weekday() == SAT:
                        out.append(_eastern(day + timedelta(days=1), 12))
                for week in (-1, 0, 1, 2):  # a Monday look for CFBD's corrections, and a floor when no games are near
                    out.append(_eastern(monday + timedelta(days=7 * week), 4))
                return sorted(set(out))
        for week in (-1, 0, 1):
            for slot in self.slots:
                for day in slot.days:
                    date = monday + timedelta(days=7 * week + day)
                    at = datetime(date.year, date.month, date.day, slot.hour, slot.minute, tzinfo=EASTERN)
                    out.append(at.astimezone(timezone.utc))
        return sorted(out)

    def next_slot(self, now: datetime) -> datetime:
        return next(at for at in self._candidates(now) if at > now)

    def last_slot(self, now: datetime) -> datetime:
        return [at for at in self._candidates(now) if at <= now][-1]

    def lifetime(self, now: datetime, *, changed_at: datetime | None, unchanged: bool) -> timedelta:
        """How long an answer fetched `now` stays fresh.

        Until the next slot, unless it is a recheck schedule, the answer is the same one CFBD gave
        before the latest slot (nothing new has landed yet), and the watch is still on: then ask
        again after `recheck` (never past the next slot).
        """
        until_next = self.next_slot(now) - now
        last = self.last_slot(now)
        waiting = (
            self.recheck is not None
            and unchanged
            and changed_at is not None
            and changed_at < last
            and now < last + self.watch
        )
        lifetime = min(self.recheck, until_next) if waiting and self.recheck is not None else until_next
        return max(lifetime, MIN_LIFETIME)

    def as_dict(self, now: datetime) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "nextSlot": _iso_z(self.next_slot(now)),
            "lastSlot": _iso_z(self.last_slot(now)),
            "recheckMinutes": round(self.recheck.total_seconds() / 60) if self.recheck else None,
            "watchHours": round(self.watch.total_seconds() / 3600, 1) if self.recheck else None,
            "prewarm": self.prewarm,
        }


# The polls: the Coaches Poll about 1 p.m. and the AP Top 25 about 2 p.m. Eastern on Sundays, the
# CFP rankings Tuesday evenings from November (a Tuesday check that finds nothing new costs one call).
POLLS = Schedule(
    "polls",
    "Polls (AP, Coaches, CFP)",
    (Slot((SUN,), 13, 0), Slot((SUN,), 14, 0), Slot((TUE,), 19, 30)),
    recheck=timedelta(minutes=20),
    watch=timedelta(hours=5),
    prewarm=True,
)
# Weekly ratings: SP+ (published by Bill Connelly early in the week, loaded by CFBD after), Elo and
# FPI after the weekend's games, CFBD's own CORE and SRS, conference SP+, opponent-adjusted EPA.
# From Sunday morning they are checked every three hours until they move, for up to four days.
RATINGS = Schedule(
    "ratings",
    "Weekly ratings (SP+, FPI, Elo, CORE, SRS, adjusted EPA)",
    (Slot((SUN,), 6, 0),),
    recheck=timedelta(hours=3),
    watch=timedelta(days=4),
    prewarm=True,
)
# Stats built from games: they move only when games finish. At 4 a.m. Eastern the morning after each
# day with games (the night games are loaded by then), again at noon the Sunday after a Saturday for
# the late West Coast games, and Monday morning for CFBD's corrections. With a normal week (games
# Thursday to Saturday) that is Friday, Saturday, Sunday twice and Monday: nothing Tuesday to
# Thursday. The game days come from the season's schedule the app already keeps (no extra call);
# until it is known, every morning plus Sunday noon.
RESULTS = Schedule(
    "results",
    "Season stats from games",
    (Slot(EVERY_DAY, 4, 0), Slot((SUN,), 12, 0)),
    after_games=True,
)
# Television assignments are announced six or twelve days ahead, usually Sunday night or Monday.
MEDIA = Schedule("media", "TV assignments", (Slot(EVERY_DAY, 4, 0), Slot(EVERY_DAY, 16, 0)))
# Pregame win probability and the transfer portal: once a day.
DAILY = Schedule("daily", "Daily lists (pregame odds, transfer portal)", (Slot(EVERY_DAY, 4, 0),))
# Roster talent and returning production are set once a year; a weekly look is plenty.
YEARLY = Schedule("yearly", "Yearly figures (talent, returning production)", (Slot((MON,), 4, 0),))

SCHEDULES: tuple[Schedule, ...] = (POLLS, RATINGS, RESULTS, MEDIA, DAILY, YEARLY)

ENDPOINT_SCHEDULES: dict[str, Schedule] = {
    "/rankings": POLLS,
    "/ratings/sp": RATINGS,
    "/ratings/sp/conferences": RATINGS,
    "/ratings/elo": RATINGS,
    "/ratings/fpi": RATINGS,
    "/ratings/core": RATINGS,
    "/ratings/srs": RATINGS,
    "/wepa/team/season": RATINGS,
    "/wepa/players/passing": RATINGS,
    "/wepa/players/rushing": RATINGS,
    "/wepa/players/kicking": RATINGS,
    "/stats/season": RESULTS,
    "/stats/season/advanced": RESULTS,
    "/stats/player/season": RESULTS,
    "/ppa/games": RESULTS,
    "/ppa/players/games": RESULTS,
    "/ppa/players/season": RESULTS,
    "/player/usage": RESULTS,
    "/records": RESULTS,
    "/rushing/plays": RESULTS,
    "/passing/plays": RESULTS,
    "/games/media": MEDIA,
    "/metrics/wp/pregame": DAILY,
    "/player/portal": DAILY,
    "/talent": YEARLY,
    "/player/returning": YEARLY,
}


# The days (US Eastern) games are played this season, learned from any /games answer the client sees.
GAME_DAY_REACH = 9  # days either side of now that decide the next slot
_game_days: frozenset[date] = frozenset()


def game_days() -> frozenset[date]:
    return _game_days


def set_game_days(days: frozenset[date]) -> None:
    global _game_days
    _game_days = frozenset(days)


def learn_game_days(payload: Any) -> int:
    """Add the kickoff dates in a /games answer to the known game days. Returns how many were new.
    Games with no or a malformed start date are skipped."""
    global _game_days
    if not isinstance(payload, list):
        return 0
    found: set[date] = set()
    for game in payload:
        raw = game.get("startDate") if isinstance(game, dict) else None
        if not isinstance(raw, str) or not raw:
            continue
        try:
            kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        found.add(kickoff.astimezone(EASTERN).date())
    new = found - _game_days
    if new:
        _game_days = _game_days | frozenset(new)
    return len(new)


def _eastern(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc)


def schedule_for(endpoint: str, kind: DataKind) -> Schedule | None:
    """The schedule an answer follows, or None for the kind's own lifetime."""
    if kind not in SCHEDULABLE:
        return None
    return ENDPOINT_SCHEDULES.get(endpoint)


def payload_hash(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Seen:
    changed_at: datetime
    hash: str


class PublicationLog:
    """What each scheduled key last looked like, when it last changed, and when a page last asked."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._asked: dict[str, datetime] = {}

    def seen(self, key: str) -> Seen | None:
        with self.db.read() as conn:
            row = conn.execute("SELECT hash, changed_at FROM publications WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        changed = _parse(row["changed_at"])
        return Seen(changed, row["hash"]) if changed is not None else None

    def asked(self, key: str, now: datetime) -> None:
        """A page (not the prewarm task) was served this key from the cache: keep it on the prewarm
        list. Written at most once an hour per key, so page loads do not each cost a write."""
        last = self._asked.get(key)
        if last is not None and now - last < ASKED_WRITE_EVERY:
            return
        with self.db.transaction() as conn:
            conn.execute("UPDATE publications SET asked_at = ? WHERE key = ?", (_iso_z(now), key))
        self._asked[key] = now

    def record(self, key: str, endpoint: str, params: dict[str, str], schedule: Schedule, payload: Any, now: datetime, *, asked: bool) -> tuple[bool, Seen | None]:
        """Note a fresh answer. Returns (unchanged, what was seen before)."""
        digest = payload_hash(payload)
        before = self.seen(key)
        unchanged = before is not None and before.hash == digest
        stamp = _iso_z(now)
        with self.db.transaction() as conn:
            if before is None:
                conn.execute(
                    "INSERT OR REPLACE INTO publications (key, endpoint, params, schedule, hash, changed_at, checked_at, asked_at, checks)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (key, endpoint, json.dumps(params, separators=(",", ":")), schedule.name, digest, stamp, stamp, stamp),
                )
            elif unchanged:
                conn.execute(
                    "UPDATE publications SET checked_at = ?, checks = checks + 1, schedule = ?" + (", asked_at = ?" if asked else "") + " WHERE key = ?",
                    (stamp, schedule.name, *( [stamp] if asked else []), key),
                )
            else:
                row = conn.execute("SELECT checks FROM publications WHERE key = ?", (key,)).fetchone()
                checks = int(row["checks"]) if row is not None else 0
                slot = schedule.last_slot(now)
                conn.execute(
                    "INSERT INTO publication_log (endpoint, key, schedule, slot, changed_at, checks) VALUES (?, ?, ?, ?, ?, ?)",
                    (endpoint, key, schedule.name, _iso_z(slot), stamp, checks),
                )
                conn.execute(
                    "UPDATE publications SET hash = ?, changed_at = ?, checked_at = ?, checks = 1, schedule = ?" + (", asked_at = ?" if asked else "") + " WHERE key = ?",
                    (digest, stamp, stamp, schedule.name, *([stamp] if asked else []), key),
                )
                late = now - slot
                log.info(
                    "%s changed %s after the %s slot (%s, %d checks since it last changed)",
                    key,
                    _describe(late),
                    schedule.name,
                    slot.astimezone(EASTERN).strftime("%a %H:%M ET"),
                    checks,
                )
        return unchanged, before

    def prewarm_keys(self, now: datetime) -> list[tuple[str, str, dict[str, str], Schedule]]:
        """Scheduled keys a page asked for recently whose schedule allows the server to refresh them."""
        by_name = {s.name: s for s in SCHEDULES}
        with self.db.read() as conn:
            rows = conn.execute("SELECT key, endpoint, params, schedule, asked_at FROM publications").fetchall()
        out = []
        for row in rows:
            schedule = by_name.get(row["schedule"])
            asked = _parse(row["asked_at"])
            if schedule is None or not schedule.prewarm or asked is None or now - asked > schedule.prewarm_recent:
                continue
            try:
                params = json.loads(row["params"])
            except ValueError:
                continue
            out.append((row["key"], row["endpoint"], params if isinstance(params, dict) else {}, schedule))
        return out

    def summary(self, now: datetime, limit: int = 8) -> list[dict[str, Any]]:
        """Per schedule: its next slot and the recent times its sources actually changed."""
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT endpoint, schedule, slot, changed_at, checks FROM publication_log ORDER BY changed_at DESC LIMIT 200"
            ).fetchall()
            keys = conn.execute("SELECT schedule, COUNT(*) AS n FROM publications GROUP BY schedule").fetchall()
        counts = {row["schedule"]: int(row["n"]) for row in keys}
        out = []
        for schedule in SCHEDULES:
            changes = [
                {
                    "endpoint": row["endpoint"],
                    "slot": row["slot"],
                    "changedAt": row["changed_at"],
                    "afterSlotMinutes": _minutes_between(row["slot"], row["changed_at"]),
                    "checks": int(row["checks"]),
                }
                for row in rows
                if row["schedule"] == schedule.name
            ][:limit]
            out.append({**schedule.as_dict(now), "keys": counts.get(schedule.name, 0), "changes": changes})
        return out


def _describe(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min"


def _minutes_between(start: str, end: str) -> int | None:
    a, b = _parse(start), _parse(end)
    if a is None or b is None:
        return None
    return int((b - a).total_seconds() // 60)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
