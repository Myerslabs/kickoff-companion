"""The season as one line (the owner's direction of 2026-10-30; his boards).

The middle tab follows the week and the cover's rail walks every stop of the season. The stops:

    preseason   the Preseason Magazine, at the head of the line
    pre         a week's Pre-Game Program: live from the Thursday before the game (the day before a game played Monday to
                Thursday), or earlier when Thursday's Claude run has landed; saved at kickoff by the kickoff lock
    game        the game itself: In Game while it plays, the Archive after
    post        the Post-Game Program: live from the final until it closes out, then saved by the post-game lock
    season      "the season right now", the one stop that moves forward; it leads Monday to Wednesday and all of a bye week
    book        the season book, at the end of the line

The Post-Game closes out when the checklist is in (the final, the AP poll after the game, What decided it) or at 6 AM on
the Tuesday after the game, whichever comes first (the owner, 2026-10-30: whenever the most important stuff comes in, the
Post-Game closes out). A check that cannot come (Claude Code not on the computer) counts as in.

Pure functions over plain rows, so the rules test without the app:

    GameRow, Status, Checks           what the line needs of a game and of the stores
    pre_open_at(kickoff)              when the Pre-Game stop opens (local)
    backstop_at(kickoff)              the Tuesday 6 AM after the game (local)
    closed_out(checks, kickoff, now)  the checklist is in, or the backstop has passed
    post_open(kickoff, locked, now)   the Post-Game stop is the one that leads (the front page's rule since Wave 1)
    season_line(games, now, status=)  the line as the rail draws it: items in order, the now marker placed, the current stop
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

PRE_OPEN_HOUR = 6  # the Pre-Game stop opens at 6 AM local on its day when Thursday's run has not opened it first
CLOSEOUT_BACKSTOP_HOUR = 6  # the Post-Game stop closes out at 6 AM local on the Tuesday after the game at the latest
POST_CHECKS = ("final", "poll", "recap")


@dataclass
class GameRow:
    """One of our games as the line needs it. `kickoff` is local and tz-aware."""

    game_id: int
    week: int
    kickoff: datetime
    opponent: str | None
    home_away: str  # "home", "away" or "neutral"
    completed: bool
    us_points: int | None = None
    them_points: int | None = None
    season_type: str = "regular"

    @property
    def won(self) -> bool | None:
        if not self.completed or self.us_points is None or self.them_points is None:
            return None
        if self.us_points == self.them_points:
            return None
        return self.us_points > self.them_points


@dataclass
class Checks:
    """The Post-Game stop's closing checklist. A check that cannot come counts as in."""

    final: bool = False
    poll: bool = False
    recap: bool = True

    def complete(self) -> bool:
        return self.final and self.poll and self.recap

    def missing(self) -> list[str]:
        return [name for name in POST_CHECKS if not getattr(self, name)]

    def as_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in POST_CHECKS}


@dataclass
class Status:
    """What the stores say about one game."""

    pre_locked: bool = False
    archived: bool = False
    post_locked: bool = False
    post_locked_at: datetime | None = None
    checks: Checks = field(default_factory=Checks)
    pre_opened_at: datetime | None = None  # Thursday's run landed: the Pre-Game opened then


def _at(day: date, hour: int, tz: Any) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=tz)


def pre_open_at(kickoff: datetime) -> datetime:
    """The Thursday of the game's week at PRE_OPEN_HOUR local; a game played Monday to Thursday opens the day before."""
    day = kickoff.date()
    thursday = day - timedelta(days=day.weekday()) + timedelta(days=3)
    opens = day - timedelta(days=1) if thursday >= day else thursday
    return _at(opens, PRE_OPEN_HOUR, kickoff.tzinfo)


def backstop_at(kickoff: datetime) -> datetime:
    """The Tuesday after the game at CLOSEOUT_BACKSTOP_HOUR local, never the game's own day."""
    days = (1 - kickoff.weekday()) % 7 or 7
    return _at(kickoff.date() + timedelta(days=days), CLOSEOUT_BACKSTOP_HOUR, kickoff.tzinfo)


def closed_out(checks: Checks, kickoff: datetime, now: datetime) -> bool:
    """The checklist is in, or the backstop has passed."""
    return checks.complete() or now >= backstop_at(kickoff)


def post_open(kickoff: datetime, locked: bool, now: datetime) -> bool:
    """The Post-Game stop still leads: the game is over, its lock is not written and the backstop has not passed. The loop
    writes the lock when the checklist is in, so a written lock is the close-out."""
    return not locked and kickoff <= now < backstop_at(kickoff)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="minutes") if isinstance(value, datetime) else None


def _stop(kind: str, key: str, state: str, when: datetime | None, href: str | None, label: str) -> dict[str, Any]:
    return {"kind": kind, "key": key, "state": state, "date": _iso(when), "href": href, "label": label}


def _pre(g: GameRow, s: Status, now: datetime) -> dict[str, Any]:
    opens = s.pre_opened_at if isinstance(s.pre_opened_at, datetime) and s.pre_opened_at < pre_open_at(g.kickoff) else pre_open_at(g.kickoff)
    if s.pre_locked:
        state = "saved"
    elif g.completed or now >= g.kickoff:
        state = "missing"  # played before the kickoff lock existed: never kept (the owner, 2026-10-30: "don't stretch for it")
    elif now >= opens:
        state = "live"
    else:
        state = "open"  # ahead: what is known today, filling in as the week comes
    href = f"#program={g.game_id}?tab=pre" if g.completed else f"#program={g.game_id}"
    return _stop("pre", f"pre:{g.game_id}", state, opens, href if state != "missing" else None, "Pre-Game Program")


def _game(g: GameRow, s: Status, now: datetime) -> dict[str, Any]:
    if g.completed:
        state = "done"
        href = f"#archive={g.game_id}"
    elif now >= g.kickoff:
        state = "live"
        href = "#live"
    else:
        state = "to_come"
        href = None
    stop = _stop("game", f"game:{g.game_id}", state, g.kickoff, href, "The game")
    if g.completed:
        stop["result"] = {"usPoints": g.us_points, "themPoints": g.them_points, "won": g.won}
    return stop


def _post(g: GameRow, s: Status, now: datetime) -> dict[str, Any]:
    day_after = g.kickoff + timedelta(days=1)
    if s.post_locked:
        state = "saved"
        when = s.post_locked_at or day_after
    elif g.completed:
        state = "closed" if closed_out(s.checks, g.kickoff, now) else "live"
        when = min(now, backstop_at(g.kickoff)) if state == "closed" else day_after  # closed by the checks: now; by the backstop: that Tuesday, not today
    else:
        state = "to_come"
        when = day_after
    href = f"#postgame={g.game_id}" if g.completed else None
    stop = _stop("post", f"post:{g.game_id}", state, when, href, "Post-Game Program")
    if g.completed and not s.post_locked:
        stop["checks"] = s.checks.as_dict()
        stop["backstop"] = _iso(backstop_at(g.kickoff))
    return stop


def _week_item(g: GameRow, s: Status, now: datetime) -> dict[str, Any]:
    return {
        "kind": "week",
        "week": g.week,
        "seasonType": g.season_type,
        "gameId": g.game_id,
        "opponent": g.opponent,
        "homeAway": g.home_away,
        "date": _iso(g.kickoff),
        "result": {"usPoints": g.us_points, "themPoints": g.them_points, "won": g.won} if g.completed else None,
        "stops": {"pre": _pre(g, s, now), "game": _game(g, s, now), "post": _post(g, s, now)},
    }


def current_stop(games: list[GameRow], now: datetime, status: Callable[[GameRow], Status], *, book_href: str | None = "#review") -> dict[str, Any]:
    """Which stop leads now. During a game the Pre-Game (In Game is its own tab); after the final the Post-Game until it
    closes out; from the Pre-Game's opening the Pre-Game; rollover R3 (owner 2026-11-15): once every game is closed out the
    season in review ("The season in review", until the switch), and before any game is played the Preseason Magazine
    ("The 2027 Magazine early, leading from the switch"); else the Season."""
    ordered = sorted(games, key=lambda g: (g.kickoff, g.week))
    for g in ordered:
        if not g.completed and g.kickoff <= now:
            return {"kind": "pre", "gameId": g.game_id, "week": g.week, "href": f"#program={g.game_id}", "label": "Pre-Game Program", "detail": _detail(g)}
    played = [g for g in ordered if g.completed]
    if played:
        last = played[-1]
        s = status(last)
        if post_open(last.kickoff, s.post_locked or closed_out(s.checks, last.kickoff, now), now):
            return {"kind": "post", "gameId": last.game_id, "week": last.week, "href": f"#postgame={last.game_id}", "label": "Post-Game Program", "detail": _detail(last)}
    upcoming = [g for g in ordered if not g.completed and g.kickoff > now]
    if upcoming:
        nxt = upcoming[0]
        s = status(nxt)
        opens = s.pre_opened_at if isinstance(s.pre_opened_at, datetime) else None
        if now >= pre_open_at(nxt.kickoff) or (opens is not None and now >= opens):
            return {"kind": "pre", "gameId": nxt.game_id, "week": nxt.week, "href": f"#program={nxt.game_id}", "label": "Pre-Game Program", "detail": _detail(nxt)}
    if ordered and all(g.completed and (status(g).post_locked or closed_out(status(g).checks, g.kickoff, now)) for g in ordered):
        return {"kind": "book", "gameId": None, "week": None, "href": book_href or "#review", "label": "Season in review", "detail": "the season, final"}
    if ordered and not played and upcoming:
        return {"kind": "preseason", "gameId": None, "week": None, "href": "#preseason", "label": "Preseason Magazine", "detail": "the season ahead"}
    return {"kind": "season", "gameId": None, "week": None, "href": "#season", "label": "My Team", "detail": "the season right now"}  # the Season page until 2026-11-01


def _detail(g: GameRow) -> str:
    who = g.opponent or "TBA"
    where = {"away": f"at {who}", "home": f"vs {who}", "neutral": f"vs {who}"}.get(g.home_away, who)
    week = f"Week {g.week}" if g.season_type == "regular" else g.season_type.title()
    if g.completed and g.us_points is not None and g.them_points is not None:
        mark = "W" if g.won else "T" if g.won is None else "L"
        return f"{week} · {where} · {mark} {g.us_points}-{g.them_points}"
    return f"{week} · {where}"


def season_line(games: list[GameRow], now: datetime, *, status: Callable[[GameRow], Status], preseason: bool = True, book_href: str | None = None) -> dict[str, Any]:
    """The line as the rail draws it: the preseason, every week (byes between), the now marker by date, the book; and the
    stop that leads now. Games without a week or a kickoff are left out by the caller."""
    ordered = sorted(games, key=lambda g: (g.kickoff, g.week))
    items: list[dict[str, Any]] = []
    items.append({"kind": "preseason", "state": "saved" if preseason else "missing", "href": "#preseason" if preseason else None, "label": "Preseason Magazine", "date": _iso(ordered[0].kickoff - timedelta(days=14)) if ordered else None})
    regular = [g for g in ordered if g.season_type == "regular"]
    weeks_seen = {g.week for g in regular}
    for g in ordered:
        s = status(g)
        if g.season_type == "regular" and regular:
            # byes: the regular-season weeks between the first and this game with no game of ours
            prev = max((h.week for h in regular if h.week < g.week), default=None)
            if prev is not None:
                for w in range(prev + 1, g.week):
                    if w not in weeks_seen:
                        by = next((h for h in regular if h.week == prev), None)
                        items.append({"kind": "bye", "week": w, "date": _iso((by.kickoff if by else g.kickoff) + timedelta(days=7 * (w - prev))), "label": "Bye"})
        items.append(_week_item(g, s, now))
    all_closed = bool(ordered) and all(g.completed and (status(g).post_locked or closed_out(status(g).checks, g.kickoff, now)) for g in ordered)
    items.append({"kind": "book", "state": "open" if all_closed else "to_come", "href": book_href if all_closed else None, "label": "Season book", "date": None})
    # the now marker by date: after the last item whose date is before now
    marker = {"kind": "now", "date": _iso(now), "href": "#season", "label": "My Team now", "state": "now"}
    at = 1
    for i, item in enumerate(items):
        when = item.get("date")
        if item["kind"] in ("week", "bye") and when and datetime.fromisoformat(when) <= now:
            at = i + 1
    items.insert(at, marker)
    return {"now": _iso(now), "current": current_stop(games, now, status, book_href=book_href), "items": items}
