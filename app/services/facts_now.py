"""A school's records counting this season's games (bug round, owner 2026-11-15: "Add this season's games"; Claude's data
check of 2026-10-27: the all-time record "771-459-40" and "Jon Sumrall, 0-0 at Florida entering 2026" are the numbers
before the season). The facts are researched once a season, entering it; the app adds the season's finished games to the
all-time record and to the head coach's record at the school, from the season's games it already has (no call of its own).

Only facts researched for this season are counted forward (a school's facts from an earlier season would miss that whole
season's games); the head coach's record only while the coach the facts name still leads the team.

    with_this_season(facts, games, season, head_coach) -> facts with the two records counted forward (a copy), or as given
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.cfbd.models import Game
from app.config import default_season

WHOLE = re.compile(r"^\s*(\d{1,4})-(\d{1,4})(?:-(\d{1,4}))?\s*$")
FIRST = re.compile(r"(?<![\d-])(\d{1,4})-(\d{1,4})(?:-(\d{1,4}))?(?![\d-])")


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date() if "T" in value else date.fromisoformat(value[:10])
    except ValueError:
        return None


def tally(games: list[Any], school: str) -> tuple[int, int, int]:
    """(wins, losses, ties) of the school's finished games with both scores."""
    wins = losses = ties = 0
    for g in games:
        if not isinstance(g, Game) or g.completed is not True or school not in (g.home_team, g.away_team):
            continue
        home, away = g.home_points, g.away_points
        if not isinstance(home, int) or not isinstance(away, int):
            continue
        us, them = (home, away) if g.home_team == school else (away, home)
        if us > them:
            wins += 1
        elif us < them:
            losses += 1
        else:
            ties += 1
    return wins, losses, ties


def _bump(match: re.Match[str], wins: int, losses: int, ties: int) -> str:
    w, l, t = int(match.group(1)) + wins, int(match.group(2)) + losses, match.group(3)  # noqa: E741 - wins, losses, ties
    tied = (int(t) if t is not None else 0) + ties
    return f"{w}-{l}" + (f"-{tied}" if t is not None or ties else "")


def with_this_season(facts: dict[str, Any] | None, games: list[Any], season: int, head_coach: str | None = None) -> dict[str, Any] | None:
    if not isinstance(facts, dict) or not isinstance(facts.get("school"), str):
        return facts
    stated = facts.get("season")
    if isinstance(stated, int) and not isinstance(stated, bool):
        if stated != season:
            return facts  # researched for another season: counting forward would miss a season's games
    else:  # facts saved before they carried their season (the shipped file): the season of the day they were checked
        researched = _date(facts.get("savedAt")) or _date(facts.get("checkedAt"))
        if researched is None or default_season(researched) != season:
            return facts
    wins, losses, ties = tally(games, facts["school"])
    if wins + losses + ties == 0:
        return facts
    out = dict(facts)
    record = facts.get("allTimeRecord")
    whole = WHOLE.match(record) if isinstance(record, str) else None
    if whole:
        out["allTimeRecord"] = _bump(whole, wins, losses, ties)
    coach = facts.get("headCoachRecord")
    if isinstance(coach, str):
        surname = head_coach.split()[-1].lower() if isinstance(head_coach, str) and head_coach.split() else None
        named = re.split(r",|\d", coach, maxsplit=1)[0].strip()
        if surname is None or not named or surname in coach.lower():  # the coach the facts name still leads the team
            first = FIRST.search(coach)
            if first:
                bumped = coach[: first.start()] + _bump(first, wins, losses, ties) + coach[first.end():]
                out["headCoachRecord"] = re.sub(rf"\bentering {season}\b", f"with {season}'s games", bumped)
    return out
