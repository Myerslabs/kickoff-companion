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
from app.services.identity import conference_short

COMMITTEE = "Playoff Committee Rankings"
AP = "AP Top 25"
ROUND_ORDER = {"first_round": 0, "quarterfinal": 1, "semifinal": 2, "championship": 3}

# The playoff picture (owner 2026-10-20: "if the season ended today", every week, as a bracket). The twelve-team format
# with straight seeding (2025 on): the five highest-ranked conference champions are in, seven at large, the twelve seeded by
# their ranking, seeds 1 to 4 with a bye, the first round at the higher seed's home. The 2026 season is taken to keep it;
# a sixteen-team year changes these three numbers and the first-round table.
PLAYOFF_FORMAT = {"teams": 12, "byes": 4, "autoBids": 5}
FIRST_ROUND = ((8, 9), (5, 12), (7, 10), (6, 11))  # in bracket order, top to bottom
BYE_SEEDS = (1, 4, 2, 3)  # the seed each first-round game's winner meets, in the same order
INDEPENDENTS = ("fbs independents", "independent", "independents")


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


def latest_poll(weeks: list[PollWeek], name: str, *, before: int | None = None) -> tuple[int | None, list[Any]]:
    """(week, ranks) of the latest regular-season week that has the poll `name`, else (None, []); with `before`, the latest
    week earlier than that week (last week's picture)."""
    best = None
    for week in weeks:
        poll = next((p for p in week.polls if p.poll == name), None)
        if poll is None or not isinstance(week.week, int) or (week.season_type or "regular") != "regular":
            continue
        if before is not None and week.week >= before:
            continue
        if best is None or gamekeys.poll_order(week) > gamekeys.poll_order(best[0]):
            best = (week, poll)
    if best is None:
        return None, []
    return best[0].week, [r for r in best[1].ranks if isinstance(r.rank, int) and isinstance(r.school, str)]


def _pct(line: Any) -> float | None:
    wins = getattr(line, "wins", None)
    losses = getattr(line, "losses", None)
    ties = getattr(line, "ties", None) or 0
    if not isinstance(wins, int) or not isinstance(losses, int):
        return None
    games = wins + losses + ties
    return wins / games if games else None


def _conference_of(rec: Any, teams: dict[str, dict[str, Any]]) -> str | None:
    name = rec.conference or teams.get(rec.team, {}).get("conference")
    if not isinstance(name, str) or not name.strip() or name.strip().lower() in INDEPENDENTS:
        return None
    return name.strip()


def conference_leaders(records: list[Any], teams: dict[str, dict[str, Any]], position: dict[str, int]) -> dict[str, str]:
    """If the season ended today, each conference's champion: the best conference record, then conference wins, then the
    overall record, then the ranking. A conference without a conference game yet goes by the ranking, then the record.
    Independents have no title to win."""
    by_conference: dict[str, list[Any]] = {}
    for rec in records:
        conference = _conference_of(rec, teams)
        if conference and isinstance(rec.team, str):
            by_conference.setdefault(conference, []).append(rec)
    leaders: dict[str, str] = {}
    for conference, members in by_conference.items():
        played = any((_pct(m.conference_games) is not None) for m in members)

        def key(m: Any, played: bool = played) -> tuple:
            conf_pct = _pct(m.conference_games)
            conf_wins = m.conference_games.wins if m.conference_games and isinstance(m.conference_games.wins, int) else -1
            total_pct = _pct(m.total)
            rank = position.get(m.team, 10_000)
            if played:
                return (-(conf_pct if conf_pct is not None else -1), -conf_wins, -(total_pct if total_pct is not None else -1), rank, m.team)
            return (rank, -(total_pct if total_pct is not None else -1), m.team)

        leaders[conference] = sorted(members, key=key)[0].team
    return leaders


def _positions(ranks: list[Any], sp: list[Any], teams: dict[str, dict[str, Any]], records: list[Any]) -> tuple[dict[str, int], dict[str, str]]:
    """Every FBS team in one order: the poll's Top 25, then the rest by SP+ rating, then the rest by record. Returns the
    position per school and what it rests on ("poll", "SP+", "record")."""
    position: dict[str, int] = {}
    basis: dict[str, str] = {}
    for r in sorted(ranks, key=lambda r: r.rank):
        if r.school not in position:
            position[r.school] = r.rank
            basis[r.school] = "poll"
    fbs = set(teams) | {r.team for r in records if isinstance(r.team, str)}
    rated = sorted(((s.rating, s.team) for s in sp if isinstance(s.team, str) and isinstance(s.rating, int | float) and s.team not in position and s.team in fbs), key=lambda t: (-t[0], t[1]))
    nxt = max(position.values(), default=0) + 1
    for _rating, school in rated:
        position[school] = nxt
        basis[school] = "SP+"
        nxt += 1
    rest = sorted((-(_pct(r.total) if _pct(r.total) is not None else -1), r.team) for r in records if isinstance(r.team, str) and r.team not in position and r.team in fbs)
    for _pct_key, school in rest:
        position[school] = nxt
        basis[school] = "record"
        nxt += 1
    return position, basis


def _field(ranks: list[Any], records: list[Any], sp: list[Any], teams: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The field if the season ended today: the champions in, the at-large teams, the seeds, and the next teams out."""
    position, basis = _positions(ranks, sp, teams, records)
    leaders = conference_leaders(records, teams, position)
    champions = sorted(leaders.values(), key=lambda s: position.get(s, 10_000))
    auto = champions[: PLAYOFF_FORMAT["autoBids"]]
    ordered = sorted(position, key=lambda s: position[s])
    at_large = [s for s in ordered if s not in auto][: max(0, PLAYOFF_FORMAT["teams"] - len(auto))]
    field = sorted(auto + at_large, key=lambda s: position[s])
    seeds = {school: seed for seed, school in enumerate(field, start=1)}
    out = [s for s in ordered if s not in seeds]
    return {"position": position, "basis": basis, "leaders": leaders, "auto": auto, "atLarge": at_large, "seeds": seeds, "out": out}


def picture(weeks: list[PollWeek], records: list[Any], sp: list[Any], team: str, teams: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """The playoff picture if the season ended today: by the committee's latest ranking once it has one, by the AP poll
    before that; None without either. Rules-based, no call: the Season page's rankings, records and SP+ answers."""
    source = "committee"
    week, ranks = latest_poll(weeks, COMMITTEE)
    if not ranks:
        source = "AP"
        week, ranks = latest_poll(weeks, AP)
    if not ranks:
        return None
    now = _field(ranks, records, sp, teams)
    previous_week, previous_ranks = latest_poll(weeks, COMMITTEE if source == "committee" else AP, before=week)
    last = _field(previous_ranks, records, sp, teams)["seeds"] if previous_ranks else {}
    champion_of = {school: conference for conference, school in now["leaders"].items()}

    def entry(school: str, seed: int | None = None) -> dict[str, Any]:
        meta = teams.get(school, {})
        conference = meta.get("conference") or next((r.conference for r in records if r.team == school), None)
        return {
            "school": school,
            "seed": seed,
            "lastSeed": last.get(school),
            "rank": now["position"].get(school),
            "rankBasis": now["basis"].get(school),
            "champion": champion_of.get(school),
            "autoBid": school in now["auto"],
            "conference": conference,
            "conferenceShort": conference_short(conference),
            "abbreviation": meta.get("abbreviation"),
            "logo": meta.get("logo"),
            "logoDark": meta.get("logoDark"),
            "isUs": school == team,
        }

    field = [entry(school, seed) for school, seed in sorted(now["seeds"].items(), key=lambda kv: kv[1])]
    by_seed = {e["seed"]: e for e in field}
    first_round = [
        {"slot": f"FR{i}", "home": by_seed.get(high), "away": by_seed.get(low), "feeds": f"QF{i}", "label": f"({low}) at ({high})"}
        for i, (high, low) in enumerate(FIRST_ROUND, start=1)
    ]
    quarterfinals = [
        {"slot": f"QF{i}", "home": by_seed.get(seed), "away": None, "from": f"FR{i}", "label": f"({seed}) v the winner of ({FIRST_ROUND[i - 1][0]}) and ({FIRST_ROUND[i - 1][1]})"}
        for i, seed in enumerate(BYE_SEEDS, start=1)
    ]
    semifinals = [{"slot": "SF1", "from": ["QF1", "QF2"]}, {"slot": "SF2", "from": ["QF3", "QF4"]}]
    final = {"slot": "CH", "from": ["SF1", "SF2"]}
    out_entries = [entry(school) for school in now["out"][:8]]
    champions = [
        {**entry(school, now["seeds"].get(school)), "conference": conference, "conferenceShort": conference_short(conference), "in": school in now["auto"]}
        for conference, school in sorted(now["leaders"].items(), key=lambda kv: now["position"].get(kv[1], 10_000))
    ]
    us = next((e for e in field if e["isUs"]), None)
    us_out = next((i for i, school in enumerate(now["out"], start=1) if school == team), None)
    if us is not None and us["seed"] <= PLAYOFF_FORMAT["byes"]:
        status, line = "bye", f"{team}: the {_ordinal(us['seed'])} seed, with a first-round bye"
    elif us is not None:
        high = next((h for h, lo in FIRST_ROUND if lo == us["seed"]), None)
        low = next((lo for h, lo in FIRST_ROUND if h == us["seed"]), None)
        visitor = by_seed.get(low) if low else None
        host = by_seed.get(high) if high else None
        status = "host" if low else "road"
        line = f"{team}: the {_ordinal(us['seed'])} seed, hosting ({low}) {visitor['school'] if visitor else '?'}" if low else f"{team}: the {_ordinal(us['seed'])} seed, at ({high}) {host['school'] if host else '?'}"
    elif us_out is not None and us_out <= 4:
        status, line = "out", f"{team}: the {_ordinal(us_out)} team out"
    elif us_out is not None:
        rank = now["position"].get(team)
        status, line = "out", f"{team}: out, {_ordinal(rank)} in the order" if rank else f"{team}: out"
    else:
        status, line = "unknown", f"{team}: not in the picture yet"
    return {
        "source": source,
        "sourceLabel": "the committee's ranking" if source == "committee" else "the AP poll",
        "week": week,
        "previousWeek": previous_week,
        "format": dict(PLAYOFF_FORMAT),
        "field": field,
        "champions": champions,
        "lastFourIn": [e for e in field if not e["autoBid"]][-4:],
        "firstFourOut": out_entries[:4],
        "nextOut": out_entries[4:8],
        "bracket": {"firstRound": first_round, "quarterfinals": quarterfinals, "semifinals": semifinals, "final": final},
        "us": {"school": team, "seed": us["seed"] if us else None, "status": status, "outBy": us_out, "line": line},
    }


def _ordinal(n: int | None) -> str:
    if not isinstance(n, int):
        return "?"
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


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


def playoff_block(weeks: list[PollWeek], games: list[Game], team: str, teams: dict[str, dict[str, Any]], records: list[Any] | None = None, sp: list[Any] | None = None) -> dict[str, Any] | None:
    """The band's data: the picture if the season ended today from the first poll on (owner 2026-10-20), the committee's
    rankings once it has them, the real bracket once the games are set. None without any of the three."""
    week, ranks = committee(weeks)
    playoff_games = sorted((g for g in games if gamekeys.is_post(g) and gamekeys.playoff_round(g)), key=_round_key)
    today = picture(weeks, records or [], sp or [], team, teams) if records is not None else None
    if not ranks and not playoff_games and today is None:
        return None
    cfp = {r.school: r.rank for r in ranks}
    rankings = [
        {
            "rank": r.rank,
            "school": r.school,
            "conference": r.conference or teams.get(r.school, {}).get("conference"),
            "conferenceShort": conference_short(r.conference or teams.get(r.school, {}).get("conference")),  # tables wave 3: the column's medium form
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
    return {"week": week, "metric": "poll:CFP", "rankings": rankings, "usRank": us["rank"] if us else None, "rounds": rounds, "picture": today}  # Phase 16: the committee list; the picture (2026-10-20)
