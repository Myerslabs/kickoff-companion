"""Context tables for the days between games (Phase 15, audit "off-day scouting" and "last season").

- last_season: this season's stat profile beside last season's, each with its national rank, from
  last season's all-FBS /stats/season and /games (kept 30 days: a finished season does not change).
- road_ahead: every remaining opponent with its record, poll rank, SP+ and last three results, all
  from answers the Season page already has (no extra call).
- common_opponents: teams both we and the next opponent have played this season, with each
  result and margin, from the season's all-games answer (no extra call).
"""

from __future__ import annotations

from typing import Any

from app.cfbd.models import Game, TeamSP
from app.services import gamekeys
from app.services.profiles import PROFILE_ROWS, Profiles
from app.services.stats_extra import sp_tables


def last_season(now_rows: list[dict[str, Any]], last: Profiles | None, team: str, season: int | None = None) -> list[dict[str, Any]]:
    """One row per profile stat: this season's value and rank, last season's, and which is better.
    Phase 16: `metric` names the national list; now.year and last.year say which season each chip
    opens (metricYear is last season's, the one that needs ?year= on the list)."""
    if last is None:
        return []
    by_key = {r.get("key"): r for r in now_rows if isinstance(r, dict)}
    out: list[dict[str, Any]] = []
    for spec in PROFILE_ROWS:
        side, label, key, higher, fmt = spec
        now = by_key.get(key) or {}
        before = last.row(team, *spec)
        a, b = now.get("value"), before.get("value")
        better = None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a != b:
            better = (a > b) == higher
        out.append({
            "side": side,
            "label": label,
            "key": key,
            "metric": f"profile:{key}",
            "metricYear": season - 1 if season else None,
            "format": fmt,
            "higherIsBetter": higher,
            "now": {"value": a, "rank": now.get("nationalRank"), "of": now.get("nationalOf"), "year": season},
            "last": {"value": b, "rank": before.get("nationalRank"), "of": before.get("nationalOf"), "year": season - 1 if season else None},
            "better": better,
        })
    return out


def _result(game: Game, team: str) -> dict[str, Any] | None:
    """{result, score, opponent, date} of a finished game from `team`'s side, else None."""
    if not game.completed or game.home_points is None or game.away_points is None:
        return None
    home = game.home_team == team
    us, them = (game.home_points, game.away_points) if home else (game.away_points, game.home_points)
    result = "W" if us > them else "L" if us < them else "T"
    return {"result": result, "score": f"{us}-{them}", "margin": us - them, "opponent": game.away_team if home else game.home_team, "date": game.start_date, "gameId": game.id}


def _played(games: list[Game], team: str) -> list[Game]:
    seen: set[int] = set()
    out = []
    for g in sorted(games, key=gamekeys.order):
        if team in (g.home_team, g.away_team) and g.completed and g.id not in seen:
            seen.add(g.id)
            out.append(g)
    return out


def road_ahead(schedule: list[Game], all_games: list[Game], team: str, sp: list[TeamSP], ap: dict[str, int], fbs: set[str] | None = None) -> list[dict[str, Any]]:
    """Every remaining opponent: date, site, record so far, AP rank, SP+ and its rank, last three results.
    Phase 16: the SP+ rank and its "of" come from the rating table (no nationalAverages: of 138)."""
    ratings = {r.team: r for r in sp if r.team}
    sp_ranked = sp_tables(sp, fbs)["sp"]
    pool = list(all_games) + list(schedule)
    out: list[dict[str, Any]] = []
    for g in sorted((g for g in schedule if not g.completed and team in (g.home_team, g.away_team)), key=gamekeys.order):
        opponent = gamekeys.opponent_of(g, team)
        if not opponent:
            continue
        results = [r for game in _played(pool, opponent) if (r := _result(game, opponent)) is not None]
        wins = sum(r["result"] == "W" for r in results)
        losses = sum(r["result"] == "L" for r in results)
        rating = ratings.get(opponent)
        out.append({
            "gameId": g.id,
            "week": g.week,
            "postseason": gamekeys.label(g),
            "playoffRound": gamekeys.playoff_round(g),
            "date": g.start_date,
            "startTimeTbd": bool(g.start_time_tbd),
            "site": "Neutral" if g.neutral_site else ("Home" if g.home_team == team else "Away"),
            "opponent": opponent,
            "record": f"{wins}-{losses}" if results else None,
            "wins": wins if results else None,
            "apRank": ap.get(opponent),
            "sp": rating.rating if rating else None,
            "spRank": sp_ranked.rank(opponent),
            "spOf": sp_ranked.of or None,
            "spMetric": "rating:sp",
            "lastThree": [{"result": r["result"], "score": r["score"], "opponent": r["opponent"]} for r in results[-3:]],
        })
    return out


def common_opponents(all_games: list[Game], us: str, them: str | None) -> list[dict[str, Any]]:
    """Teams both have played this season, with each result. Empty when there is no opponent."""
    if not them:
        return []
    ours: dict[str, list[dict[str, Any]]] = {}
    theirs: dict[str, list[dict[str, Any]]] = {}
    for g in _played(all_games, us):
        r = _result(g, us)
        if r and r["opponent"] and r["opponent"] != them:
            ours.setdefault(r["opponent"], []).append(r)
    for g in _played(all_games, them):
        r = _result(g, them)
        if r and r["opponent"] and r["opponent"] != us:
            theirs.setdefault(r["opponent"], []).append(r)
    out = []
    for opponent in sorted(set(ours) & set(theirs)):
        a, b = ours[opponent], theirs[opponent]
        out.append({
            "opponent": opponent,
            "us": [{"result": r["result"], "score": r["score"], "margin": r["margin"]} for r in a],
            "them": [{"result": r["result"], "score": r["score"], "margin": r["margin"]} for r in b],
            "usMargin": sum(r["margin"] for r in a),
            "themMargin": sum(r["margin"] for r in b),
        })
    return out
