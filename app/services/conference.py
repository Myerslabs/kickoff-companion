"""The conference page (owner 2026-11-02: "Lets do the conference page first"; "Any conference, ours first"; the board
"Build as drawn"): one page for a conference, the SEC first, with a chip
row for the other ten, from answers the app already holds. No CFBD call of its own but one /records read per conference
(an hour's cache), the same answer every team page of that conference reads.

    conference_page(state, name=None) -> (dict, parts)    the page's one answer (app.state and a conference's name; None: ours)

The six bands, in the board's order:
  against     the Conference SP+ table (the Ratings page's) and, on a switch, each conference's teams averaged a game at a
              time from the Stats pages' full lists (pass and rush yards, allowed, sacks, takeaways), ranked among the eleven
  standings   the conference's standings from /records with the race played out (where each team can still finish, from
              app/services/race.py); our four What-we-need lines on our own conference only
  week        this week's games with a team of the conference, the Picks of the week rows (kickoff, TV, the line, the pick),
              the race's Pull for on ours
  rated       every team of the conference by SP+, with its offense and defense, Elo, FPI, talent and the Talent Edge
              percentile, each with its FBS rank
  leaders     the conference's top five of the full lists' lead stat in passing, rushing, receiving and defense
  land        each school's cells on the Imperialism Map's latest snapshot, the week's change, the conference's share

A piece that cannot be read is `{"available": false, "words": why}` on its own key; the rest of the page still draws. The
pure helpers are exported for the tests: `conference_list`, `resolve_conference`, `numbers_table`, `rated_rows`,
`leaders_of`, `land_rows`, `week_games`, `standings_block`, `form_of`."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any

from app.cache import DataKind
from app.cfbd.models import Game, PollWeek, Team, TeamRecords
from app.services.identity import conference_short
from app.services.imperialism import ImperialismStore
from app.services.parts import Part
from app.services.picks import picks_week
from app.services.race import race, stamp_of
from app.services.season import standings_rows
from app.services.talent_edge import TalentEdgeStore

log = logging.getLogger("kickoff.conference")

POWER = ("SEC", "Big Ten", "Big 12", "ACC")  # the chip row: ours, then the Power conferences, then the rest by name, independents last
INDEPENDENTS = "FBS Independents"
LEADERS = ("passing", "rushing", "receiving", "defense")
LEADERS_SHOWN = 5

# the averaged stats: key, label, the long name, the full list's category, its side, the column, higher is better
NUMBERS: tuple[tuple[str, str, str, str, str, str, bool], ...] = (
    ("passYpg", "Pass Y/G", "Passing yards a game", "passing", "offense", "ypg", True),
    ("rushYpg", "Rush Y/G", "Rushing yards a game", "rushing", "offense", "ypg", True),
    ("passAllowed", "Pass allowed", "Passing yards allowed a game", "passing", "allowed", "ypg", False),
    ("rushAllowed", "Rush allowed", "Rushing yards allowed a game", "rushing", "allowed", "ypg", False),
    ("sacksPerGame", "Sacks/G", "Sacks a game", "defense", "offense", "spg", True),
    ("sacksGivenPerGame", "Sacks given/G", "Sacks allowed a game", "defense", "allowed", "spg", False),
    ("takeawaysPerGame", "Takeaways/G", "Takeaways a game", "defense", "offense", "takePerGame", True),
)


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _words(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _unavailable(words: str) -> dict[str, Any]:
    return {"available": False, "words": words}


# --- the conferences ------------------------------------------------------------------------------------------------


def conference_list(teams: dict[str, dict[str, Any]], ours: str | None) -> list[dict[str, Any]]:
    """Every conference the FBS list names with its team count: ours first, then the Power conferences in their order,
    then the rest by name, the independents last."""
    counts: Counter[str] = Counter()
    for meta in teams.values():
        name = _words(meta.get("conference")) if isinstance(meta, dict) else None
        if name:
            counts[name] += 1

    def order(name: str) -> tuple[int, int, str]:
        if name == ours:
            return (0, 0, name)
        if name in POWER:
            return (1, POWER.index(name), name)
        if name == INDEPENDENTS:
            return (3, 0, name)
        return (2, 0, name)

    return [{"name": name, "short": conference_short(name) or name, "teams": counts[name], "isOurs": name == ours} for name in sorted(counts, key=order)]


def resolve_conference(names: list[str], wanted: Any) -> str | None:
    """A conference by its name or its short name, any case ("sec", "B1G", "Big Ten"); None when the list lacks it."""
    key = _words(wanted)
    if not key:
        return None
    folded = key.casefold()
    for name in names:
        if name.casefold() == folded:
            return name
    for name in names:
        short = conference_short(name)
        if short and short.casefold() == folded:
            return name
    return None


def members_of(teams: dict[str, dict[str, Any]], conference: str) -> list[str]:
    return sorted(school for school, meta in teams.items() if isinstance(meta, dict) and meta.get("conference") == conference)


# --- against the rest ----------------------------------------------------------------------------------------------


def numbers_table(listings: dict[str, dict[str, Any] | None], conference: str, order: list[str] | None = None) -> dict[str, Any]:
    """Each conference's teams averaged, a column a stat, with the conference's rank among the conferences in each. The
    rows follow `order` (the SP+ table's) where given; a conference whose teams have no numbers is left out."""
    columns = [{"key": key, "label": label, "long": long, "format": "1f", "higherIsBetter": higher} for key, label, long, *_rest, higher in NUMBERS]
    sums: dict[str, dict[str, list[float]]] = {}
    teams: dict[str, set[str]] = {}
    for key, _label, _long, category, side, column, _higher in NUMBERS:
        listing = listings.get(category)
        table = ((listing or {}).get("teams") or {}).get(side) if isinstance(listing, dict) else None
        rows = table.get("rows") if isinstance(table, dict) else None
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            name = _words(row.get("conference"))
            if not name:
                continue
            value = _num(row.get(column))
            if column == "takePerGame":  # the defense table carries the season's takeaways whole
                take, games = _num(row.get("take")), _num(row.get("games"))
                value = take / games if take is not None and games else None
            if value is None:
                continue
            sums.setdefault(name, {}).setdefault(key, []).append(value)
            teams.setdefault(name, set()).add(str(row.get("team")))
    out: list[dict[str, Any]] = []
    for name, by_key in sums.items():
        row: dict[str, Any] = {"conference": name, "short": conference_short(name) or name, "teams": len(teams.get(name, ())), "isUs": name == conference}
        for key, *_rest in NUMBERS:
            values = by_key.get(key) or []
            row[key] = round(sum(values) / len(values), 1) if values else None
        out.append(row)
    for key, *_rest, higher in NUMBERS:
        ranked = sorted((r for r in out if r.get(key) is not None), key=lambda r: r[key], reverse=higher)
        rank, last = 0, None
        for place, r in enumerate(ranked, start=1):
            if r[key] != last:
                rank, last = place, r[key]
            r[f"{key}Rank"] = rank
    if order:
        place = {name: i for i, name in enumerate(order)}
        out.sort(key=lambda r: (place.get(r["conference"], len(place)), r["conference"]))
    else:
        out.sort(key=lambda r: r["conference"])
    return {"columns": columns, "rows": out, "of": len(out)}


# --- the standings and the race ------------------------------------------------------------------------------------


FORM_GAMES = 5


def form_of(games: list[Game], team: str, limit: int = FORM_GAMES) -> list[dict[str, Any]]:
    """The team's last results, oldest first, the shape the team pages' Last 5 squares read (result, points, opponent)."""
    played = []
    for g in games:
        if not isinstance(g, Game) or not g.completed or team not in (g.home_team, g.away_team):
            continue
        home = g.home_team == team
        us, them = (g.home_points, g.away_points) if home else (g.away_points, g.home_points)
        if not isinstance(us, int) or not isinstance(them, int):
            continue
        played.append({
            "gameId": g.id, "week": g.week, "postseason": g.season_type if g.season_type not in (None, "regular") else None,
            "result": "W" if us > them else "L" if us < them else "T", "points": us, "opponentPoints": them,
            "opponent": g.away_team if home else g.home_team, "homeAway": "neutral" if g.neutral_site else "home" if home else "away",
            "_order": (g.start_date or "", g.id or 0),
        })
    played.sort(key=lambda r: r.pop("_order"))
    return played[-limit:]


def standings_block(records: list[TeamRecords], teams: dict[str, dict[str, Any]], ap: dict[str, int], conference: str, ours: str | None, games: list[Game], week: int | None, stamp: Any = None) -> dict[str, Any]:
    """The conference's standings with the race played out on each row and each team's last five; our lines, watch list
    and helps when it is our conference. A conference the games do not name (the independents) has the table alone."""
    us = ours if ours and any(r.team == ours for r in records) else None
    rows = standings_rows(records, teams, ap, conference, us)
    anchor = us or (rows[0]["team"] if rows else None)
    the_race = race(games, anchor, conference, week=week, stamp=stamp) if anchor else None
    by_team = {r["team"]: r for r in (the_race or {}).get("standings") or [] if isinstance(r, dict)}
    for row in rows:
        r = by_team.get(row["team"]) or {}
        row["raceStatus"] = r.get("status")
        row["bestPlace"] = r.get("bestPlace")
        row["worstPlace"] = r.get("worstPlace")
        row["form"] = form_of(games, row["team"])
    ours_race = the_race if the_race and us else None
    return {
        "rows": rows,
        "ours": bool(us),
        "race": {k: ours_race.get(k) for k in ("conference", "spots", "week", "settled", "rangeExact", "us", "lines", "watch")} if ours_race else None,
        "helps": (ours_race or {}).get("helps") or {},
    }


# --- this week --------------------------------------------------------------------------------------------------------


def week_games(picks: dict[str, Any], members: set[str], helps: dict[Any, Any]) -> dict[str, Any]:
    """The week's games with a team of the conference, in kickoff order, the unscheduled last: the Picks of the week
    rows with the race's Pull for on each game the race watches."""
    rows: list[dict[str, Any]] = []
    for slot in picks.get("slots") or []:
        for g in (slot.get("games") or []) if isinstance(slot, dict) else []:
            if isinstance(g, dict):
                rows.append(g)
    later = [g for g in picks.get("unscheduled") or [] if isinstance(g, dict)]
    mine = [g for g in rows if ((g.get("home") or {}).get("school") in members or (g.get("away") or {}).get("school") in members)]
    mine.sort(key=lambda g: (str(g.get("kickoff") or ""), g.get("gameId") or 0))
    mine += [g for g in later if ((g.get("home") or {}).get("school") in members or (g.get("away") or {}).get("school") in members)]
    out = []
    for g in mine:
        row = dict(g)
        h = helps.get(g.get("gameId")) if isinstance(helps, dict) else None
        row["helps"] = h if isinstance(h, dict) else None
        row["conferenceGame"] = (g.get("home") or {}).get("school") in members and (g.get("away") or {}).get("school") in members
        out.append(row)
    return {
        "week": picks.get("week"), "seasonType": picks.get("seasonType"), "label": picks.get("label"), "key": picks.get("key"),
        "picksBy": picks.get("picksBy"), "writtenAt": picks.get("writtenAt"), "ready": picks.get("ready"), "note": picks.get("note"),
        "games": out,
        "record": _record_of(out),
    }


def _record_of(games: list[dict[str, Any]]) -> dict[str, int]:
    right = sum(1 for g in games if g.get("right") is True)
    wrong = sum(1 for g in games if g.get("right") is False)
    return {"right": right, "wrong": wrong}


# --- the teams, rated ----------------------------------------------------------------------------------------------


def rated_rows(ratings: list[dict[str, Any]], members: set[str], talent: dict[str, Any] | None, ours: str | None, teams: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The conference's teams from the Ratings page's rows, by SP+, each with the Talent Edge roll-up when it is here."""
    tables = (talent or {}).get("teams") if isinstance(talent, dict) else None
    out = []
    for r in ratings:
        if not isinstance(r, dict) or r.get("team") not in members:
            continue
        school = r["team"]
        t = (tables.get(school) or {}).get("groups") if isinstance(tables, dict) and isinstance(tables.get(school), dict) else None
        tot = t.get("TOT") if isinstance(t, dict) and isinstance(t.get("TOT"), dict) else None
        meta = (teams or {}).get(school) or {}
        out.append({
            "team": school,
            "abbreviation": r.get("abbreviation") or meta.get("abbreviation"),
            "logo": r.get("logo") or meta.get("logo"),
            "logoDark": r.get("logoDark") or meta.get("logoDark"),
            "isUs": school == ours,
            "sp": r.get("sp"), "spOffense": r.get("spOffense"), "spDefense": r.get("spDefense"), "spSpecial": r.get("spSpecial"),
            "elo": r.get("elo"), "fpi": r.get("fpi"), "talent": r.get("talent"),
            "talentEdge": {"rank": tot.get("rank"), "of": tot.get("of"), "pct": tot.get("pct")} if tot else None,
        })

    def sp_key(row: dict[str, Any]) -> tuple[int, float, str]:
        value = _num((row.get("sp") or {}).get("rating")) if isinstance(row.get("sp"), dict) else None
        return (0, -value, row["team"]) if value is not None else (1, 0.0, row["team"])

    out.sort(key=sp_key)
    for place, row in enumerate(out, start=1):
        row["place"] = place
    return out


# --- the leaders ------------------------------------------------------------------------------------------------------


def leaders_of(listing: dict[str, Any] | None, members: set[str], shown: int = LEADERS_SHOWN) -> dict[str, Any]:
    """The conference's top of one full list, in the list's own order (its lead stat), with each man's FBS rank."""
    players = listing.get("players") if isinstance(listing, dict) else None
    if not isinstance(players, dict):
        return {"lead": None, "label": None, "rows": [], "available": False}
    lead = _words(players.get("lead"))
    columns = players.get("columns") if isinstance(players.get("columns"), list) else []
    label = next((c.get("label") for c in columns if isinstance(c, dict) and c.get("key") == lead), lead)
    rows = []
    for row in players.get("rows") if isinstance(players.get("rows"), list) else []:
        if not isinstance(row, dict) or row.get("team") not in members:
            continue
        rows.append({
            "playerId": row.get("playerId"), "player": row.get("player"), "position": row.get("position"), "team": row.get("team"),
            "abbreviation": row.get("abbreviation"), "headshotUrl": row.get("headshotUrl"), "isUs": row.get("isUs") is True,
            "value": row.get(lead) if lead else None, "rank": row.get(f"{lead}Rank") if lead else None,
        })
        if len(rows) >= shown:
            break
    return {"lead": lead, "label": label, "category": listing.get("category"), "rows": rows, "available": True}


# --- the land ------------------------------------------------------------------------------------------------------------


def land_rows(table: dict[str, Any] | None, members: set[str]) -> dict[str, Any]:
    """Each school's cells on the map's latest snapshot, its rank among every school, the change since the snapshot
    before; the conference's share of the map."""
    if not isinstance(table, dict) or not isinstance(table.get("snapshots"), list) or not table["snapshots"] or not isinstance(table.get("teams"), list):
        return _unavailable("The Imperialism Map has not been worked out yet; the weekly run draws it Sundays from 6 AM.")
    names = [t.get("team") if isinstance(t, dict) else None for t in table["teams"]]
    snaps = [s for s in table["snapshots"] if isinstance(s, dict) and isinstance(s.get("owners"), list)]
    if not snaps:
        return _unavailable("The Imperialism Map's snapshots could not be read.")
    last, before = snaps[-1], (snaps[-2] if len(snaps) >= 2 else None)
    now = Counter(last["owners"])
    prior = Counter(before["owners"]) if before else None
    total = len(last["owners"]) or 1
    ranked = sorted(((n, names[i]) for i, n in now.items() if isinstance(i, int) and 0 <= i < len(names) and names[i]), key=lambda x: (-x[0], str(x[1])))
    rank_of: dict[str, int] = {}
    rank, last_n = 0, None
    for place, (n, name) in enumerate(ranked, start=1):
        if n != last_n:
            rank, last_n = place, n
        rank_of[str(name)] = rank
    rows = []
    for index, name in enumerate(names):
        if name not in members:
            continue
        cells = now.get(index, 0)
        rows.append({"team": name, "cells": cells, "pct": round(100 * cells / total, 1), "rank": rank_of.get(name), "change": (cells - prior.get(index, 0)) if prior is not None else None})
    rows.sort(key=lambda r: (-r["cells"], r["team"]))
    held = sum(r["cells"] for r in rows)
    return {
        "available": True,
        "computedWeek": table.get("computedWeek"),
        "label": last.get("label"),
        "cells": total,
        "held": held,
        "pct": round(100 * held / total, 1),
        "of": len(ranked),
        "rows": rows,
    }


# --- the page ----------------------------------------------------------------------------------------------------------


async def conference_page(state: Any, name: Any = None) -> tuple[dict[str, Any] | None, dict[str, Part]]:
    """The page's answer and the CFBD parts behind it (for the envelope). None for a conference the FBS list lacks (the
    answer's `conferences` still lists the names) or when the FBS list itself could not be read."""
    settings, season_service = state.settings, state.season
    year = settings.season
    parts: dict[str, Part] = {}
    parts["teams"] = await season_service._part("teams", "/teams/fbs", {"year": year}, Team, DataKind.TEAMS)
    teams = season_service._team_lookup(parts["teams"].records)
    conferences = conference_list(teams, settings.conference)
    names = [c["name"] for c in conferences]
    conference = resolve_conference(names, name) if name else (settings.conference if settings.conference in names else (names[0] if names else None))
    if conference is None:
        return None, parts
    members = members_of(teams, conference)
    member_set = set(members)
    ours = settings.team if settings.team in member_set else None

    parts["records"] = await season_service._part("records", "/records", {"year": year, "conference": conference}, TeamRecords, DataKind.SCHEDULE)
    parts["games"] = await season_service._part("games", "/games", {"year": year}, Game, DataKind.SCHEDULE)
    parts["rankings"] = await season_service._part("rankings", "/rankings", {"year": year}, PollWeek, DataKind.SCHEDULE)
    _polls, poll_ranks = season_service._polls(parts["rankings"].records, teams)
    ap = poll_ranks.get("AP", {}) if isinstance(poll_ranks, dict) else {}

    week_answer = await _guarded("the week's games", picks_week, state)
    week_number = week_answer.get("week") if isinstance(week_answer, dict) else None
    standings = standings_block(parts["records"].records, teams, ap, conference, ours, parts["games"].records, week_number if isinstance(week_number, int) else None, stamp=stamp_of(parts["games"]))
    week = week_games(week_answer, member_set, standings["helps"]) if isinstance(week_answer, dict) else _unavailable("The week's games could not be read.")

    ratings = await _guarded("the ratings", _ratings_data, state)
    conf_rows = [dict(c, isUs=c.get("conference") == conference, short=conference_short(c.get("conference")) or c.get("conference")) for c in (ratings or {}).get("conferences") or [] if isinstance(c, dict)]
    listings = {cat: await _guarded(f"the {cat} list", _listing_data, state, cat) for cat in LEADERS}
    sp_order = [c["conference"] for c in conf_rows if isinstance(c.get("conference"), str)]
    numbers = numbers_table(listings, conference, sp_order)

    talent = _read_talent(settings)
    rated = rated_rows((ratings or {}).get("rows") or [], member_set, talent, ours, teams)
    leaders = {cat: leaders_of(listings.get(cat), member_set) for cat in LEADERS}
    land = land_rows(_read_map(settings), member_set)

    ranked = sum(1 for r in standings["rows"] if isinstance(r.get("apRank"), int))
    now = season_service.client._clock()
    data = {
        "season": year,
        "conference": {
            "name": conference,
            "short": conference_short(conference) or conference,
            "teams": len(members),
            "members": members,
            "ranked": ranked,
            "isOurs": conference == settings.conference,
            "ourTeam": ours,
            "spRank": next((c.get("rank") for c in conf_rows if c.get("conference") == conference), None),
            "spOf": len(conf_rows) or None,
        },
        "conferences": conferences,
        "against": {"sp": conf_rows, "numbers": numbers, "available": bool(conf_rows) or bool(numbers["rows"])},
        "standings": standings,
        "week": week,
        "rated": rated,
        "talentEdge": {"available": talent is not None, "computedWeek": (talent or {}).get("computedWeek")},
        "leaders": leaders,
        "land": land,
        "parts": {name: part.status(now) for name, part in parts.items()} | {"ratings": (ratings or {}).get("parts", {}).get("sp") or {"status": "error", "error": "the ratings could not be read"}, "stats": ((listings.get("passing") or {}).get("parts") or {}).get("stats") or {"status": "error", "error": "the full lists could not be read"}},
    }
    return data, parts


async def _guarded(what: str, fn: Any, *args: Any) -> Any:
    """One piece that fails is logged and left out; the page still answers (defensive rule 2)."""
    try:
        return await fn(*args)
    except Exception as exc:  # noqa: BLE001 - every piece is someone else's answer; one must not take the page down
        log.warning("Conference page: %s could not be read (%s: %s)", what, exc.__class__.__name__, exc)
        return None


async def _ratings_data(state: Any) -> dict[str, Any] | None:
    assembled = await state.ratings.ratings()
    return assembled.data if assembled is not None and not assembled.all_failed else None


async def _listing_data(state: Any, category: str) -> dict[str, Any] | None:
    assembled = await state.fullstats.listing(category)
    return assembled.data if assembled is not None and not assembled.all_failed else None


def _read_talent(settings: Any) -> dict[str, Any] | None:
    try:
        return TalentEdgeStore(settings.data_dir, settings.season).load()
    except Exception as exc:  # noqa: BLE001 - a file on disk; the page says the band is not here yet
        log.warning("Conference page: Talent Edge's table could not be read (%s)", exc)
        return None


def _read_map(settings: Any) -> dict[str, Any] | None:
    try:
        return ImperialismStore(settings.data_dir, settings.season).load()
    except Exception as exc:  # noqa: BLE001
        log.warning("Conference page: the Imperialism Map could not be read (%s)", exc)
        return None


def now_iso(now: datetime) -> str:
    return now.isoformat()
