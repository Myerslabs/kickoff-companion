"""Phase 13 (stats depth II): the pure calculations behind the new tables. No calls here; the
services fetch, these shape. Every input is untrusted: anything missing or of the wrong type is
skipped or shown as None, never raised.

- Strength of schedule from SP+ (CFBD leaves SP+'s own sos null in season): the average SP+ of the
  FBS opponents a team has played, and for us the average of those still to play.
- The résumé: expected wins (the sum of CFBD's postgame win probability for each finished game,
  CFBD's own definition), actual wins, and the week-by-week AP and Coaches ranks.
- The transfer portal joined to a roster (the portal has no player id: first and last name and the
  destination school), and a team's recruiting class rank.
- Opponent-adjusted metrics (WEPA) per team, player boards for adjusted passing and rushing EPA and
  kicker points added above replacement (PAAR), CORE and SRS beside the ratings, conference SP+.
- An opponent's tendencies from its season of rushing and passing plays: run rate and success by
  down and distance, where the runs go and how deep the passes go.
- The advanced box score of one finished game, normalized: success, value and explosiveness by
  quarter, line play, havoc, field position, finishing drives, and per-player value and usage."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from app.cfbd.models import (
    AdjustedTeamMetrics,
    ConferenceSP,
    Game,
    KickerPAAR,
    PassingPlay,
    PlayerTransfer,
    PlayerWeightedEPA,
    PollWeek,
    RushingPlay,
    TeamCoreRating,
    TeamRecruitingRanking,
    TeamSP,
    TeamSRS,
)
from app.services import gamekeys
from app.services.profiles import rank_teams, tie_ranks
from app.services.stats_extra import RankTable, rank_table, real_teams


def num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _r(value: Any, digits: int = 3) -> float | None:
    number = num(value)
    return round(number, digits) if number is not None else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# --- strength of schedule and the résumé -------------------------------------------------------------


def _is_fbs_side(game: Game, side: str) -> bool:
    classification = getattr(game, f"{side}_classification", None)
    return str(classification or "").lower() == "fbs"


def sp_ratings(sp: list[TeamSP]) -> dict[str, float]:
    return {r.team: v for r in sp if r.team and (v := num(r.rating)) is not None}


def sos_played(games: list[Game], sp: list[TeamSP]) -> dict[str, dict[str, Any]]:
    """{team: {rating, games, rank, of}}: the average SP+ of the rated opponents each team has
    played. An FCS opponent (no SP+) is left out of the average, and counted in `fcs`."""
    ratings = sp_ratings(sp)
    totals: dict[str, list[float]] = {}
    fcs: dict[str, int] = {}
    for g in games:
        if not g.completed or not g.home_team or not g.away_team:
            continue
        for team, opponent in ((g.home_team, g.away_team), (g.away_team, g.home_team)):
            if team not in ratings:
                continue
            if opponent in ratings:
                totals.setdefault(team, []).append(ratings[opponent])
            else:
                fcs[team] = fcs.get(team, 0) + 1
    averages = {team: sum(values) / len(values) for team, values in totals.items() if values}
    ranks, of = rank_teams(averages, True)
    return {team: {"rating": round(value, 2), "games": len(totals[team]), "fcs": fcs.get(team, 0), "rank": ranks.get(team), "of": of} for team, value in averages.items()}


def resume(schedule: list[Game], all_games: list[Game], team: str, sp: list[TeamSP], polls: list[PollWeek]) -> dict[str, Any]:
    """Our season so far from its schedule: expected and actual wins, the SP+ of opponents
    played and to come (with where the rest would rank among the schedules FBS teams have played,
    from every game of the season), and the poll path."""
    ratings = sp_ratings(sp)
    expected = 0.0
    wins = losses = 0
    counted = 0
    played: list[float] = []
    ahead: list[dict[str, Any]] = []
    for g in sorted((g for g in schedule if team in (g.home_team, g.away_team)), key=gamekeys.order):
        home = g.home_team == team
        opponent = g.away_team if home else g.home_team
        if g.completed:
            wp = num(g.home_postgame_win_probability if home else g.away_postgame_win_probability)
            if wp is not None and 0 <= wp <= 1:
                expected += wp
                counted += 1
            ours, theirs = (g.home_points, g.away_points) if home else (g.away_points, g.home_points)
            if _int(ours) is not None and _int(theirs) is not None:
                wins += ours > theirs
                losses += ours < theirs
            if opponent in ratings:
                played.append(ratings[opponent])
        else:
            ahead.append({"week": g.week, "postseason": gamekeys.label(g), "playoffRound": gamekeys.playoff_round(g), "neutral": bool(g.neutral_site), "opponent": opponent, "home": home, "sp": _r(ratings.get(opponent or ""), 1)})
    remaining = [a["sp"] for a in ahead if a["sp"] is not None]
    all_sos = sos_played(all_games or schedule, sp)
    remaining_avg = sum(remaining) / len(remaining) if remaining else None
    # where the remaining schedule would rank among the schedules FBS teams have played so far
    rem_rank = None
    if remaining_avg is not None and all_sos:
        rem_rank = 1 + sum(1 for v in all_sos.values() if v["rating"] > remaining_avg)
    return {
        "expectedWins": round(expected, 2) if counted else None,
        "gamesCounted": counted,
        "wins": wins,
        "losses": losses,
        "luck": round(wins - expected, 2) if counted else None,
        "sosPlayed": {**all_sos[team], "metric": "rating:sosPlayed"} if team in all_sos else None,  # Phase 16: its national list
        "remaining": {"games": ahead, "averageSp": _r(remaining_avg, 2), "rankAmongPlayed": rem_rank, "of": len(all_sos) or None, "metric": "rating:sosPlayed"},
        "polls": poll_path(polls, team),
    }


def poll_path(polls: list[PollWeek], team: str) -> list[dict[str, Any]]:
    """[{week, seasonType, ap, coaches}] in week order; a week the team was unranked has None."""
    out = []
    for week in sorted(polls, key=lambda w: ((w.season_type or "regular") != "regular", w.week)):
        row: dict[str, Any] = {"week": week.week, "seasonType": week.season_type or "regular", "ap": None, "coaches": None}
        for poll in week.polls:
            name = str(poll.poll or "")
            key = "ap" if name.startswith("AP") else "coaches" if "Coaches" in name else None
            if key is None:
                continue
            row[key] = next((r.rank for r in poll.ranks if r.school == team and _int(r.rank) is not None), None)
        out.append(row)
    return out


# --- the portal and class ranks ----------------------------------------------------------------------


def _name_key(first: Any, last: Any) -> str:
    text = f"{first or ''} {last or ''}"
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", " ", text)
    return re.sub(r"[^a-z]", "", text)


def portal_index(portal: list[PlayerTransfer], school: str) -> dict[str, dict[str, Any]]:
    """{name key: transfer} for players who transferred to `school` (the latest move wins)."""
    out: dict[str, dict[str, Any]] = {}
    for t in sorted(portal, key=lambda t: t.transfer_date or ""):
        if t.destination != school:
            continue
        key = _name_key(t.first_name, t.last_name)
        if key:
            out[key] = {"from": t.origin, "stars": _int(t.stars), "rating": _r(t.rating, 4), "date": (t.transfer_date or "")[:10] or None, "eligibility": t.eligibility, "position": t.position}
    return out


def transfer_for(index: dict[str, dict[str, Any]], first: Any, last: Any) -> dict[str, Any] | None:
    return index.get(_name_key(first, last))


def class_rank(rankings: list[TeamRecruitingRanking], team: str, asked_year: int | None = None) -> dict[str, Any] | None:
    mine = next((r for r in rankings if r.team == team), None)
    if mine is None:
        return None
    year = asked_year or _int(mine.year)
    # Phase 16: the class list (class:<year>) ranks all of Division I, as CFBD's 247 ranking does
    return {"year": year, "rank": _int(mine.rank), "points": _r(mine.points, 2), "of": len(rankings), "metric": f"class:{year}" if year else None}


# --- opponent-adjusted metrics and the other ratings ------------------------------------------------------


ADJUSTED_KEYS = [
    # (key, label, reader, higher is better, format)
    ("epa", "Adjusted EPA per play", lambda m: m.epa and m.epa.total, True, "+2f"),
    ("epaPass", "Adjusted EPA per pass", lambda m: m.epa and m.epa.passing, True, "+2f"),
    ("epaRush", "Adjusted EPA per rush", lambda m: m.epa and m.epa.rushing, True, "+2f"),
    ("success", "Adjusted success rate", lambda m: m.success_rate and m.success_rate.total, True, "pct"),
    ("epaAllowed", "Adjusted EPA allowed per play", lambda m: m.epa_allowed and m.epa_allowed.total, False, "+2f"),
    ("successAllowed", "Adjusted success rate allowed", lambda m: m.success_rate_allowed and m.success_rate_allowed.total, False, "pct"),
    ("lineYards", "Adjusted line yards per rush", lambda m: m.rushing and m.rushing.line_yards, True, "2f"),
    ("lineYardsAllowed", "Adjusted line yards allowed", lambda m: m.rushing_allowed and m.rushing_allowed.line_yards, False, "2f"),
]


def adjusted_rows(metrics: list[AdjustedTeamMetrics]) -> dict[str, dict[str, Any]]:
    """{team: {key: {value, rank, of}}} for the opponent-adjusted team metrics."""
    values: dict[str, dict[str, float]] = {key: {} for key, *_ in ADJUSTED_KEYS}
    for m in metrics:
        for key, _label, read, _higher, _fmt in ADJUSTED_KEYS:
            try:
                value = num(read(m))
            except AttributeError:
                value = None
            if value is not None:
                values[key][m.team] = value
    ranks = {key: rank_teams(values[key], higher) for key, _label, _read, higher, _fmt in ADJUSTED_KEYS}
    out: dict[str, dict[str, Any]] = {}
    for m in metrics:
        out[m.team] = {key: {"value": _r(values[key].get(m.team), 4), "rank": ranks[key][0].get(m.team), "of": ranks[key][1] or None} for key, *_ in ADJUSTED_KEYS}
    return out


def adjusted_matchup(metrics: list[AdjustedTeamMetrics], us: str, them: str | None) -> list[dict[str, Any]]:
    """Rows for the Game program: each adjusted metric for both teams with national ranks."""
    table = adjusted_rows(metrics)
    if us not in table and (them is None or them not in table):
        return []
    rows = []
    for key, label, _read, higher, fmt in ADJUSTED_KEYS:
        mine, theirs = (table.get(us) or {}).get(key) or {}, (table.get(them or "") or {}).get(key) or {}
        rows.append({"key": key, "metric": f"adjusted:{key}", "label": label, "format": fmt, "higherIsBetter": higher, "us": mine.get("value"), "usRank": mine.get("rank"), "them": theirs.get("value"), "themRank": theirs.get("rank"), "of": mine.get("of") or theirs.get("of")})
    return rows


def shared_ranks(rows: list[dict[str, Any]], value_key: str = "value", id_key: str = "playerId") -> dict[str, int]:
    """{id: rank} over rows already best first, with the one tie rule (Phase 16: the play value and
    adjusted boards used to count 1, 2, 3 through ties; now a tie shares a rank like every chip)."""
    ranks = tie_ranks([r[value_key] for r in rows])
    return {r[id_key]: rank for r, rank in zip(rows, ranks, strict=True)}


def wepa_rows(records: list[PlayerWeightedEPA]) -> list[dict[str, Any]]:
    return [{"playerId": r.athlete_id, "player": r.athlete_name, "position": r.position, "team": r.team, "conference": r.conference, "value": _r(r.wepa, 3), "detail": {"plays": _int(r.plays)}} for r in records if r.athlete_id]


def kick_rows(records: list[KickerPAAR]) -> list[dict[str, Any]]:
    return [{"playerId": r.athlete_id, "player": r.athlete_name, "position": "K", "team": r.team, "conference": r.conference, "value": _r(r.paar, 2), "detail": {"attempts": _int(r.attempts)}} for r in records if r.athlete_id]


def adjusted_board_rows(rows: list[dict[str, Any]], fbs: set[str] | None) -> list[dict[str, Any]]:
    """One adjusted board's national list: FBS players with a value, best first, ties by name."""
    rows = [r for r in rows if r["value"] is not None and (fbs is None or r["team"] in fbs)]
    rows.sort(key=lambda r: (-r["value"], r["player"] or ""))
    return rows


# (id, label, stat, format, detail columns, note)
ADJUSTED_BOARDS: list[tuple[str, str, str, str, list[dict[str, Any]], str]] = [
    ("wepa:passing", "Adjusted passing EPA per play", "Adj EPA", "+2f", [{"key": "plays", "label": "Plays", "format": "0f"}], "Passing EPA per play adjusted for the defenses faced (CFBD's WEPA)."),
    ("wepa:rushing", "Adjusted rushing EPA per play", "Adj EPA", "+2f", [{"key": "plays", "label": "Plays", "format": "0f"}], "Rushing EPA per play adjusted for the defenses faced (CFBD's WEPA)."),
    ("paar:kicking", "Kicker points added above replacement", "PAAR", "+1f", [{"key": "attempts", "label": "Kicks", "format": "0f"}], "Points a kicker added over a replacement-level kicker on his attempts (CFBD's PAAR)."),
]


def adjusted_source_rows(board_id: str, passing: list[PlayerWeightedEPA], rushing: list[PlayerWeightedEPA], kicking: list[KickerPAAR]) -> list[dict[str, Any]]:
    return wepa_rows(passing) if board_id == "wepa:passing" else wepa_rows(rushing) if board_id == "wepa:rushing" else kick_rows(kicking)


def player_boards(passing: list[PlayerWeightedEPA], rushing: list[PlayerWeightedEPA], kicking: list[KickerPAAR], *, team: str, opponent: str | None, conference: str, fbs: set[str] | None, top: int | None = 10, team_top: int = 8) -> list[dict[str, Any]]:
    """Leaders boards in the same shape as the other boards: adjusted passing and rushing EPA per
    play (CFBD's WEPA) and kicker points added above replacement (PAAR). top=None keeps the whole
    national and conference lists (the national list view)."""

    def board(board_id: str, label: str, stat: str, fmt: str, detail: list[dict[str, Any]], note: str) -> dict[str, Any]:
        national = adjusted_board_rows(adjusted_source_rows(board_id, passing, rushing, kicking), fbs)
        conf = [r for r in national if r["conference"] == conference]
        nat_rank = shared_ranks(national)
        conf_rank = shared_ranks(conf)

        def entry(r: dict[str, Any], rank: int | None = None) -> dict[str, Any]:
            return {**r, "metric": f"board:{board_id}", "isUs": r["team"] == team, "rank": rank, "conferenceRank": conf_rank.get(r["playerId"]), "conferenceOf": len(conf) or None, "nationalRank": nat_rank.get(r["playerId"]), "nationalOf": len(national) or None, "headshotUrl": f"/media/headshot/{r['playerId']}"}

        mine = [r for r in national if r["team"] == team][:team_top]
        theirs = [r for r in national if opponent and r["team"] == opponent][:team_top]
        return {
            "id": board_id,
            "metric": f"board:{board_id}",  # Phase 16: the full national list behind the chips
            "category": "adjusted",
            "stat": stat,
            "label": label,
            "format": fmt,
            "minimum": None,
            "detailColumns": detail,
            "team": [entry(r) for r in mine],
            "opponent": [entry(r) for r in theirs],
            "conference": [entry(r, conf_rank[r["playerId"]]) for r in conf[:top]],
            "national": [entry(r, nat_rank[r["playerId"]]) for r in national[:top]],
            "conferenceOf": len(conf) or None,
            "nationalOf": len(national) or None,
            "usBest": {"conferenceRank": min((conf_rank[r["playerId"]] for r in mine), default=None), "nationalRank": min((nat_rank[r["playerId"]] for r in mine), default=None)},
            "note": note,
        }

    empty_note = " CFBD has not published it for this season yet." if not passing and not rushing else ""
    return [board(board_id, label, stat, fmt, detail, note + (empty_note if board_id.startswith("wepa") else "")) for board_id, label, stat, fmt, detail, note in ADJUSTED_BOARDS]


def core_tables(core: list[TeamCoreRating], fbs: set[str] | None = None) -> dict[str, RankTable]:
    """CFBD's CORE rating, offense and defense (lower is better: CFBD's defense number is points
    allowed relative to average), ranked here with the tie rule over the FBS teams."""
    rows = real_teams(core, fbs)
    conf = {r.team: r.conference for r in rows if r.conference}
    return {
        "core": rank_table({r.team: v for r in rows if (v := num(r.overall)) is not None}, True, None, conf),
        "coreOffense": rank_table({r.team: v for r in rows if (v := num(r.offense)) is not None}, True, None, conf),
        "coreDefense": rank_table({r.team: v for r in rows if (v := num(r.defense)) is not None}, False, None, conf),
    }


def srs_table(srs: list[TeamSRS]) -> RankTable:
    """SRS over all of Division I, as CFBD ranks it (266 teams in the 2025 recording; an FBS team can
    rank past 138). The tie rule stands in only when CFBD ranked no one."""
    rows = real_teams(srs, None)
    values = {r.team: v for r in rows if (v := num(r.rating)) is not None}
    ranks = {r.team: r.ranking for r in rows if r.team in values and _int(r.ranking) is not None and r.ranking > 0}
    return rank_table(values, True, ranks, {r.team: r.conference for r in rows if r.conference})


def sos_table(games: list[Game], sp: list[TeamSP], fbs: set[str] | None = None) -> RankTable:
    """The SP+ strength of schedule played (sos_played) as a rank table, hardest first."""
    sos = sos_played(games, real_teams(sp, fbs))
    return RankTable({t: v["rating"] for t, v in sos.items()}, {t: v["rank"] for t, v in sos.items() if v.get("rank") is not None}, True, "local")


def more_ratings(core: list[TeamCoreRating], srs: list[TeamSRS], adjusted: list[AdjustedTeamMetrics], fbs: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """{team: {core, coreOffense, coreDefense, srs, adjEpa, adjEpaAllowed} each {value, rank}} for the ratings page."""
    cores = core_tables(core, fbs)
    srs_ranked = srs_table(srs)
    adj = adjusted_rows(adjusted)
    teams = set(cores["core"].values) | set(cores["coreOffense"].values) | set(cores["coreDefense"].values) | set(srs_ranked.values) | set(adj)
    out: dict[str, dict[str, Any]] = {}
    for team in teams:
        a = adj.get(team) or {}
        out[team] = {
            "core": {"value": _r(cores["core"].value(team), 2), "rank": cores["core"].rank(team)},
            "coreOffense": {"value": _r(cores["coreOffense"].value(team), 2), "rank": cores["coreOffense"].rank(team)},
            "coreDefense": {"value": _r(cores["coreDefense"].value(team), 2), "rank": cores["coreDefense"].rank(team)},
            "srs": {"value": _r(srs_ranked.value(team), 1), "rank": srs_ranked.rank(team)},
            "adjEpa": {"value": (a.get("epa") or {}).get("value"), "rank": (a.get("epa") or {}).get("rank")},
            "adjEpaAllowed": {"value": (a.get("epaAllowed") or {}).get("value"), "rank": (a.get("epaAllowed") or {}).get("rank")},
        }
    return out


def conference_rows(conferences: list[ConferenceSP]) -> list[dict[str, Any]]:
    rows = [
        {"conference": c.conference, "rating": _r(c.rating, 1), "offense": _r(c.offense.rating if c.offense else None, 1), "defense": _r(c.defense.rating if c.defense else None, 1), "specialTeams": _r(c.special_teams.rating if c.special_teams else None, 2), "sos": _r(c.sos, 3)}
        for c in conferences
        if c.conference
    ]
    rated = {r["conference"]: r["rating"] for r in rows if r["rating"] is not None}
    ranks, _ = rank_teams(rated, True)
    for r in rows:
        r["rank"] = ranks.get(r["conference"])
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0))
    return rows


# --- an opponent's tendencies -----------------------------------------------------------------------------


SITUATIONS = [
    ("first", "1st down"),
    ("second_short", "2nd and 1 to 3"),
    ("second_medium", "2nd and 4 to 7"),
    ("second_long", "2nd and 8 or more"),
    ("third_short", "3rd and 1 to 3"),
    ("third_medium", "3rd and 4 to 6"),
    ("third_long", "3rd and 7 or more"),
    ("fourth", "4th down"),
    ("red_zone", "Red zone (20 and in)"),
    ("goal_to_go", "Inside the 10"),
]


def _situations(down: Any, distance: Any, ytg: Any) -> list[str]:
    down, distance, ytg = _int(down), _int(distance), _int(ytg)
    found = []
    if down == 1:
        found.append("first")
    elif down == 2 and distance is not None:
        found.append("second_short" if distance <= 3 else "second_medium" if distance <= 7 else "second_long")
    elif down == 3 and distance is not None:
        found.append("third_short" if distance <= 3 else "third_medium" if distance <= 6 else "third_long")
    elif down == 4:
        found.append("fourth")
    if ytg is not None and 0 < ytg <= 20:
        found.append("red_zone")
    if ytg is not None and 0 < ytg <= 10:
        found.append("goal_to_go")
    return found


def tendencies(rushes: list[RushingPlay], passes: list[PassingPlay], team: str) -> dict[str, Any]:
    """The team's offense over its season: by situation (plays, run rate, yards and success on
    runs and on passes), run direction and pass depth. A sack is a called pass; kneels and spikes
    are left out. Only plays by `team` on offense count (the endpoint returns both sides)."""
    snaps: list[dict[str, Any]] = []
    for r in rushes:
        if r.offense != team or r.is_kneel:
            continue
        snaps.append({"kind": "pass" if r.is_sack else "run", "down": r.down, "distance": r.distance, "ytg": r.start_yards_to_goal, "yards": _int(r.rushing_yards), "success": r.success if isinstance(r.success, bool) else None, "direction": None if r.is_sack else (r.rush_direction or None), "depth": None, "game": r.game_id})
    for p in passes:
        if p.offense != team or p.is_spike:
            continue
        snaps.append({"kind": "pass", "down": p.down, "distance": p.distance, "ytg": p.start_yards_to_goal, "yards": _int(p.total_yards), "success": p.success if isinstance(p.success, bool) else None, "direction": None, "depth": p.pass_depth or None, "game": p.game_id})

    def tally(rows: list[dict[str, Any]]) -> dict[str, Any]:
        runs = [s for s in rows if s["kind"] == "run"]
        passes_ = [s for s in rows if s["kind"] == "pass"]

        def side(items: list[dict[str, Any]]) -> dict[str, Any]:
            judged = [s for s in items if s["success"] is not None]
            yards = [s["yards"] for s in items if s["yards"] is not None]
            return {"plays": len(items), "success": {"made": sum(1 for s in judged if s["success"]), "of": len(judged)}, "yardsPerPlay": round(sum(yards) / len(yards), 1) if yards else None}

        return {"plays": len(rows), "runRate": round(len(runs) / len(rows), 3) if rows else None, "run": side(runs), "pass": side(passes_)}

    by_situation = []
    for key, label in SITUATIONS:
        rows = [s for s in snaps if key in _situations(s["down"], s["distance"], s["ytg"])]
        by_situation.append({"key": key, "label": label, **tally(rows)})
    directions = []
    for key, label in (("left", "Left"), ("middle", "Middle"), ("right", "Right")):
        rows = [s for s in snaps if s["kind"] == "run" and str(s["direction"] or "").lower() == key]
        t = tally(rows)
        directions.append({"key": key, "label": label, "plays": t["run"]["plays"], "yardsPerPlay": t["run"]["yardsPerPlay"], "success": t["run"]["success"]})
    depths = []
    for key in sorted({str(s["depth"]).lower() for s in snaps if s["kind"] == "pass" and s["depth"]}):
        rows = [s for s in snaps if s["kind"] == "pass" and str(s["depth"] or "").lower() == key]
        t = tally(rows)
        depths.append({"key": key, "label": key.replace("_", " ").capitalize(), "plays": t["pass"]["plays"], "yardsPerPlay": t["pass"]["yardsPerPlay"], "success": t["pass"]["success"]})
    total = tally(snaps)
    return {"team": team, "games": len({s["game"] for s in snaps if s["game"] is not None}), "plays": total["plays"], "runRate": total["runRate"], "bySituation": by_situation, "runDirection": directions, "passDepth": depths}


# --- the advanced box score of one game -------------------------------------------------------------------


QUARTERS = ("quarter1", "quarter2", "quarter3", "quarter4")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _by_quarter(block: Any) -> dict[str, float | None]:
    b = _dict(block)
    return {"total": _r(b.get("total")), **{q: _r(b.get(q)) for q in QUARTERS}}


def advanced_box(payload: Any) -> dict[str, Any] | None:
    """The /game/box/advanced answer, normalized for the tables. None when it is not one."""
    body = _dict(payload)
    teams = _dict(body.get("teams"))
    players = _dict(body.get("players"))
    info = _dict(body.get("gameInfo"))
    if not teams:
        return None
    names = [t.get("team") for t in _list(teams.get("ppa")) if isinstance(t.get("team"), str)]
    out_teams: dict[str, dict[str, Any]] = {}
    for name in names:
        pick = lambda key, name=name: next((t for t in _list(teams.get(key)) if t.get("team") == name), {})  # noqa: E731
        ppa, success, explosive = pick("ppa"), pick("successRates"), pick("explosiveness")
        rushing, havoc, field, scoring = pick("rushing"), pick("havoc"), pick("fieldPosition"), pick("scoringOpportunities")
        out_teams[name] = {
            "plays": _int(ppa.get("plays")),
            "ppa": {"overall": _by_quarter(ppa.get("overall")), "passing": _by_quarter(ppa.get("passing")), "rushing": _by_quarter(ppa.get("rushing"))},
            "success": {"overall": _by_quarter(success.get("overall")), "standardDowns": _by_quarter(success.get("standardDowns")), "passingDowns": _by_quarter(success.get("passingDowns"))},
            "explosiveness": _by_quarter(_dict(explosive).get("overall")),
            "line": {"lineYards": _r(rushing.get("lineYardsAverage"), 2), "stuffRate": _r(rushing.get("stuffRate")), "powerSuccess": _r(rushing.get("powerSuccess")), "secondLevelYards": _r(rushing.get("secondLevelYardsAverage"), 2), "openFieldYards": _r(rushing.get("openFieldYardsAverage"), 2)},
            "havoc": {"total": _r(havoc.get("total")), "frontSeven": _r(havoc.get("frontSeven")), "db": _r(havoc.get("db"))},
            "fieldPosition": {"averageStart": _r(field.get("averageStart"), 1), "averageStartingPredictedPoints": _r(field.get("averageStartingPredictedPoints"), 2)},
            "scoring": {"opportunities": _int(scoring.get("opportunities")), "points": _int(scoring.get("points")), "pointsPerOpportunity": _r(scoring.get("pointsPerOpportunity"), 2)},
        }
    usage = {(u.get("team"), u.get("player")): u for u in _list(players.get("usage"))}
    out_players = []
    for p in _list(players.get("ppa")):
        name, team = p.get("player"), p.get("team")
        if not isinstance(name, str) or not isinstance(team, str):
            continue
        avg, cum, use = _dict(p.get("average")), _dict(p.get("cumulative")), _dict(usage.get((team, name)))
        out_players.append({
            "player": name,
            "team": team,
            "position": p.get("position") if isinstance(p.get("position"), str) else None,
            "ppa": _r(avg.get("total")),
            "passPpa": _r(avg.get("passing")),
            "rushPpa": _r(avg.get("rushing")),
            "totalPpa": _r(cum.get("total"), 1),
            "usage": _r(use.get("total")),
        })
    out_players.sort(key=lambda r: -(r["totalPpa"] if r["totalPpa"] is not None else -999))
    return {
        "teams": out_teams,
        "players": out_players,
        "excitement": _r(info.get("excitement"), 2),
        "homeWinProbability": _r(info.get("homeWinProb")),
        "home": info.get("homeTeam") if isinstance(info.get("homeTeam"), str) else None,
        "away": info.get("awayTeam") if isinstance(info.get("awayTeam"), str) else None,
    }
