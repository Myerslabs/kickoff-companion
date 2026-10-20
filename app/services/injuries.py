"""The Injury Report (owner 2026-10-10): a team's injuries through the season, week by week, newest first.

Built from the availability reports the game notes already hold (data/notes/<game_id>.json, one per game), so it costs no
CFBD call: the games come from the schedule the program caches. Our own report lists every game we have played plus the
next one; another team's lists our games against it (the notes cover our games only).

Each report row belongs to one of the game's two teams: its own `team` field (the notes prompt asks for it since
2026-10-10), else the school named at the start of its note ("Lake Effect. Ankle, ..."), the longest name winning so a
note that starts "Lake Effect State" never reads as Lake Effect. A row that names neither team is kept apart, never guessed. A team
named at the start of the note is taken off the note, which then reads as the injury alone.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services import gamekeys
from app.services.notes import AvailabilityRow, NotesFile

# How a status sorts in a game's list: the players who miss the game first.
STATUS_ORDER = {"out": 0, "doubtful": 1, "game-time decision": 2, "questionable": 2, "probable": 3, "available": 4}

Loader = Callable[[int], tuple[NotesFile | None, str | None]]


def _clean(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def team_names(school: str, team: dict[str, Any] | None) -> list[str]:
    """Every way a report may name a school, lower case, longest first: "lake effect squalls", "lake effect", "squalls", "le"."""
    info = team if isinstance(team, dict) else {}
    mascot = _clean(info.get("mascot"))
    names = {school.lower()}
    if mascot:
        names.add(f"{school} {mascot}".lower())
        names.add(mascot.lower())
    abbreviation = _clean(info.get("abbreviation"))
    if abbreviation:
        names.add(abbreviation.lower())
    return sorted(names, key=len, reverse=True)


SEPARATORS = ".;:,-–—"


def _leads(text: str, name: str) -> bool:
    """A note that opens with the school's name as its own lead: the note ends there or punctuation follows ("Lake Effect.
    Ankle", "Lake Effect; ankle", "Lake Effect - ankle"). Never the start of a longer name ("Lake Effect St. Knee") and
    never a name followed by a parenthesis ("Lake Effect (OH)")."""
    if not text.startswith(name):
        return False
    rest = text[len(name):]
    if not rest:
        return True
    after = rest.lstrip(" ")
    return bool(after) and after[0] in SEPARATORS


def _match(text: str | None, sides: dict[str, list[str]], *, exact: bool) -> str | None:
    """The one school `text` names, the longest name winning; None when it names neither, or both equally (a shared mascot)."""
    low = (_clean(text) or "").lower()
    if exact:
        low = low.rstrip(" .,;:")
    if not low:
        return None
    longest, winners = 0, set()
    for school, names in sides.items():
        for name in names:
            if not (low == name if exact else _leads(low, name)):
                continue
            if len(name) > longest:
                longest, winners = len(name), {school}
            elif len(name) == longest:
                winners.add(school)
    return next(iter(winners)) if len(winners) == 1 else None


def row_team(row: AvailabilityRow, sides: dict[str, list[str]]) -> tuple[str | None, bool]:
    """The school a row belongs to, and whether that came from the note (so the note can lose its leading name). The `team`
    field must be one of the school's names whole ("Lake Effect St." is no Lake Effect); then the note's lead."""
    school = _match(row.team, sides, exact=True)
    if school:
        return school, False
    school = _match(row.note, sides, exact=False)
    return (school, True) if school else (None, False)


def _strip_name(note: str | None, names: list[str]) -> str | None:
    """'Lake Effect. Ankle, hurt in the opener' -> 'Ankle, hurt in the opener' (the team is the page's or the band's)."""
    text = _clean(note)
    if not text:
        return None
    low = text.lower()
    for name in names:
        if _leads(low, name):
            rest = text[len(name):].lstrip(" " + SEPARATORS)
            return rest[:1].upper() + rest[1:] if rest else None
    return text


def _row(row: AvailabilityRow, names: list[str] | None) -> dict[str, Any]:
    note = _strip_name(row.note, names) if names else _clean(row.note)
    return {"name": row.name.strip(), "team": _clean(row.team), "position": _clean(row.position), "status": _clean(row.status) or "Not reported", "note": note}


def _sorted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (STATUS_ORDER.get(str(r.get("status") or "").lower(), 5), r["name"].lower()))


def season_long_rows(injuries: list[Any] | None) -> list[dict[str, Any]]:
    """The preseason load's injuries and suspensions as report rows (freeze wave F3: one report, both sources): the
    status as written ("Out for the season"), the detail and the expected return in the note."""
    rows: list[dict[str, Any]] = []
    for item in injuries or []:
        name = _clean(getattr(item, "name", None))
        if not name:
            continue
        detail = _clean(getattr(item, "detail", None))
        back = _clean(getattr(item, "expectedReturn", None))
        note = "; ".join(p for p in (detail, f"back {back}" if back else None) if p) or None
        rows.append({"name": name, "team": None, "position": _clean(getattr(item, "position", None)), "status": _clean(getattr(item, "status", None)) or "Not reported", "note": note, "preseason": True})
    return rows


def injury_report(games: list[Any], load: Loader, *, us: str, team: str, teams: dict[str, dict[str, Any]], season: int, preseason: list[Any] | None = None) -> dict[str, Any]:
    """The report for `team` (us, or an opponent of ours) from our schedule's games and their notes, and the preseason
    load's season-long injuries at the end (`seasonLong`)."""
    ordered = sorted((g for g in games if getattr(g, "id", None) is not None and (g.week is not None or gamekeys.is_post(g))), key=gamekeys.order)
    upcoming = next((g for g in ordered if not g.completed), None)
    if team == us:
        chosen = [g for g in ordered if g.completed] + ([upcoming] if upcoming is not None else [])
    else:
        chosen = [g for g in ordered if team in (g.home_team, g.away_team)]
    out = []
    reports = 0
    for game in reversed(chosen):  # newest first (owner 2026-10-08: time-ordered lists read newest to oldest)
        home_is_us = game.home_team == us
        opponent = game.away_team if home_is_us else game.home_team
        notes, error = load(game.id)
        sides = {school: team_names(school, teams.get(school)) for school in (us, opponent) if school}
        rows: list[dict[str, Any]] = []
        unassigned: list[dict[str, Any]] = []
        listed = list(notes.availability) if notes is not None else []
        for row in listed:
            school, from_note = row_team(row, sides)
            if school == team:
                rows.append(_row(row, sides.get(school) if from_note else None))
            elif school is None:
                unassigned.append(_row(row, None))
        if listed:
            reports += 1
        out.append({
            "gameId": game.id,
            "week": game.week,
            "label": gamekeys.label(game),
            "date": game.start_date,
            "completed": bool(game.completed),
            "next": upcoming is not None and game.id == upcoming.id,
            "homeAway": "neutral" if game.neutral_site else ("home" if home_is_us else "away"),
            "opponent": {**teams.get(opponent or "", {}), "school": opponent},
            "notes": notes is not None,
            "error": error,
            "reported": bool(listed),
            "source": _clean(notes.availabilitySource) if notes is not None else None,
            "updatedAt": _clean(notes.availabilityUpdatedAt) if notes is not None else None,
            "rows": _sorted(rows),
            "unassigned": _sorted(unassigned) if team == us else [],
        })
    season_long = season_long_rows(preseason)
    return {"season": season, "team": {**teams.get(team, {}), "school": team}, "isUs": team == us, "games": out, "seasonLong": season_long, "counts": {"games": len(out), "reports": reports, "seasonLong": len(season_long)}}
