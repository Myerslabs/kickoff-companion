"""One answer to "who coaches them" (freeze wave F3, 2026-10-20: one fact, one source).

Three sources name a team's head coach and coordinators: the game's notes (the newest: written in game week), the
season's coaches load (one paste per conference, early in the season) and CFBD's /coaches (head coaches only, with the
hire date and the record). Before this module the cover and In Game took the notes then the load, the Top 25 took CFBD
then the load, the team page drew two tables, so an interim coach could read three ways on one screen. Every payload
now asks resolve(): the notes, then the load, then CFBD, name by name.
"""

from __future__ import annotations

from typing import Any

ROLES = ("headCoach", "offensiveCoordinator", "defensiveCoordinator")
LABELS = {"notes": "The game's notes", "season": "The season's coaches load", "cfbd": "CFBD"}


def _name(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def resolve(school: str | None, *, notes: dict[str, Any] | None = None, season: dict[str, Any] | None = None, cfbd_head: str | None = None) -> dict[str, Any]:
    """The team's coaches: {team, headCoach, offensiveCoordinator, defensiveCoordinator, sources: {role: notes|season|cfbd},
    source: the label of the newest source used, or None}. A name from the notes stands over the load, the load over CFBD;
    CFBD names the head coach only."""
    out: dict[str, Any] = {"team": school}
    sources: dict[str, str] = {}
    for role in ROLES:
        chosen: str | None = None
        for label, block in (("notes", notes), ("season", season)):
            chosen = _name((block or {}).get(role)) if isinstance(block, dict) else None
            if chosen:
                sources[role] = label
                break
        if not chosen and role == "headCoach" and _name(cfbd_head):
            chosen, sources[role] = _name(cfbd_head), "cfbd"
        out[role] = chosen
    used = [sources[r] for r in ROLES if r in sources]
    out["sources"] = sources
    out["source"] = LABELS[sorted(used, key=("notes", "season", "cfbd").index)[0]] if used else None
    return out


def cfbd_head_coach(records: list[Any], school: str, year: int) -> str | None:
    """The head coach CFBD lists for `school` in `year` from a /coaches answer (first and last name), or None."""
    for coach in records:
        first, last = getattr(coach, "first_name", None), getattr(coach, "last_name", None)
        name = " ".join(p for p in (_name(first), _name(last)) if p)
        if not name:
            continue
        for season in getattr(coach, "seasons", None) or []:
            if getattr(season, "school", None) == school and getattr(season, "year", None) == year:
                return name
    return None
