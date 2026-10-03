"""The Playoff band (Phase 15): the committee's rankings and the bracket, both as tables.

The committee ranks teams on Tuesdays from November (the "Playoff Committee Rankings" poll in
/rankings, regular-season weeks only; the postseason's final polls have no committee ranking). The
bracket comes from the season's /games answer the Season page already has (CFBD's default includes
the postseason): each playoff game carries a `playoff` block with the round, the bracket slot and both
seeds (recorded for the 2025 twelve-team field). No extra call.
"""

from __future__ import annotations

from typing import Any

from app.cfbd.models import Game, PollWeek
from app.services import gamekeys

COMMITTEE = "Playoff Committee Rankings"
ROUND_ORDER = {"first_round": 0, "quarterfinal": 1, "semifinal": 2, "championship": 3}


def committee(weeks: list[PollWeek]) -> tuple[int | None, list[Any]]:
    """(week, ranks) of the latest week that has the committee's rankings, else (None, [])."""
    best = None
    for week in weeks:
        poll = next((p for p in week.polls if p.poll == COMMITTEE), None)
        if poll is None or not isinstance(week.week, int):
            continue
        if best is None or gamekeys.poll_order(week) > gamekeys.poll_order(best[0]):
            best = (week, poll)
    if best is None:
        return None, []
    return best[0].week, [r for r in best[1].ranks if isinstance(r.rank, int)]


def _round_key(game: Game) -> tuple[int, str, str]:
    block = game.playoff
    order = ROUND_ORDER.get((block.round or "") if block else "", 9)
    return order, (block.bracket_slot or "") if block else "", game.start_date or ""


def _game_name(game: Game) -> str | None:
    """The bowl hosting the game ("Rose Bowl"); a first-round game has none, so its stadium."""
    block = game.playoff
    name = (block.bowl_name if block and block.bowl_name else None) or game.notes
    if name and "college football playoff" in name.lower() and "championship" not in name.lower() and game.venue:
        return f"At {game.venue}"
    return name


def playoff_block(weeks: list[PollWeek], games: list[Game], team: str, teams: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """The band's data, or None before the committee's first ranking and without any playoff game."""
    week, ranks = committee(weeks)
    playoff_games = sorted((g for g in games if gamekeys.is_post(g) and gamekeys.playoff_round(g)), key=_round_key)
    if not ranks and not playoff_games:
        return None
    cfp = {r.school: r.rank for r in ranks}
    rankings = [
        {
            "rank": r.rank,
            "school": r.school,
            "conference": r.conference or teams.get(r.school, {}).get("conference"),
            "abbreviation": teams.get(r.school, {}).get("abbreviation"),
            "logo": teams.get(r.school, {}).get("logo"),
            "logoDark": teams.get(r.school, {}).get("logoDark"),
            "isUs": r.school == team,
        }
        for r in sorted(ranks, key=lambda r: r.rank)
    ]
    rounds: list[dict[str, Any]] = []
    for game in playoff_games:
        name = gamekeys.playoff_round(game) or "Playoff"
        if not rounds or rounds[-1]["round"] != name:
            rounds.append({"round": name, "games": []})
        block = game.playoff
        winner = None
        if game.completed and game.home_points is not None and game.away_points is not None and game.home_points != game.away_points:
            winner = game.home_team if game.home_points > game.away_points else game.away_team
        rounds[-1]["games"].append({
            "gameId": game.id,
            "date": game.start_date,
            "startTimeTbd": bool(game.start_time_tbd),
            "bowl": _game_name(game),
            "venue": game.venue,
            "slot": block.bracket_slot if block else None,
            "completed": bool(game.completed),
            "winner": winner,
            "isUs": team in (game.home_team, game.away_team),
            "home": {"school": game.home_team, "seed": block.home_seed if block else None, "cfpRank": cfp.get(game.home_team or ""), "points": game.home_points, **{k: teams.get(game.home_team or "", {}).get(k) for k in ("abbreviation", "logo", "logoDark")}},
            "away": {"school": game.away_team, "seed": block.away_seed if block else None, "cfpRank": cfp.get(game.away_team or ""), "points": game.away_points, **{k: teams.get(game.away_team or "", {}).get(k) for k in ("abbreviation", "logo", "logoDark")}},
        })
    us = next((r for r in rankings if r["isUs"]), None)
    return {"week": week, "metric": "poll:CFP", "rankings": rankings, "usRank": us["rank"] if us else None, "rounds": rounds}  # Phase 16: the committee list
