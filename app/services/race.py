"""The conference race: what we need (the F8 talk-through, feature 1, owner 2026-10-21).

Paths to the conference title game from the season's games alone (CFBD /games, the Season page's answer: a conference
game carries both teams' conference and its result). The title game takes the top two by conference record. For every
team: the record, the games left, the best record it can still reach, and whether it has clinched a spot, is out, or
is alive. For our team: the lines a fan wants in words (win out, win all but one, what Saturday does, the clinch number),
who has to lose, and the week's games that help us with whom to pull for. No call: the games are already cached.

    race(games, team, conference, week=None) -> dict   (the shape under `race` in the season overview and the program)

Exact where it can be exact. A team's standing is settled by counting when counting settles it (every other team
winning out is the worst case; every other team losing out the best), and by playing out every remaining game among
the teams that matter when it does not (at most RACE_MAX_GAMES games, 2^16 outcomes; beyond that, early in the season,
nobody is clinched or out and the count is the answer). Where a finish comes down to a tie the race says "tiebreaker"
and stops: the tiebreakers (head to head, common opponents, the committee's ranking) are not modelled.

A conference with divisions (the Sun Belt) reads as a top-two race; the title game pairing may differ there."""

from __future__ import annotations

import itertools
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.cfbd.models import Game

SPOTS = 2  # the title game's two places
RACE_MAX_GAMES = 16  # the most remaining games played out exactly (65,536 outcomes)
NEAR = 1  # a team within this many conference wins of ours counts as a threat on the watch list


@dataclass
class Line:
    team: str
    wins: int = 0
    losses: int = 0
    total_wins: int = 0
    total_losses: int = 0
    left: list[Game] = field(default_factory=list)

    @property
    def played(self) -> int:
        return self.wins + self.losses

    @property
    def best(self) -> int:
        return self.wins + len(self.left)

    @property
    def pct(self) -> float:
        return self.wins / self.played if self.played else 0.0


def _is_title_game(game: Game) -> bool:
    notes = (game.notes or "").lower()
    return "championship" in notes or "title game" in notes


def conference_games(games: list[Game], conference: str) -> list[Game]:
    """The conference's own games of the regular season, the title game left out."""
    out = []
    for g in games:
        if not isinstance(g, Game) or not g.conference_game or g.season_type not in (None, "regular"):
            continue
        if g.home_conference != conference or g.away_conference != conference:
            continue
        if not g.home_team or not g.away_team or _is_title_game(g):
            continue
        out.append(g)
    return out


def lines_of(games: list[Game], conference: str) -> dict[str, Line]:
    """Every team's conference line from the conference's games: wins, losses and the games left."""
    lines: dict[str, Line] = {}
    for g in conference_games(games, conference):
        home = lines.setdefault(g.home_team, Line(g.home_team))
        away = lines.setdefault(g.away_team, Line(g.away_team))
        if g.completed and isinstance(g.home_points, int) and isinstance(g.away_points, int):
            if g.home_points == g.away_points:
                continue  # a tie counts for nobody (none since 1996)
            winner, loser = (home, away) if g.home_points > g.away_points else (away, home)
            winner.wins += 1
            loser.losses += 1
        elif not g.completed:
            home.left.append(g)
            away.left.append(g)
    return lines


def totals_of(games: list[Game], lines: dict[str, Line]) -> None:
    """Each team's overall record from every game it played, for the standings table."""
    for g in games:
        if not isinstance(g, Game) or not g.completed or not isinstance(g.home_points, int) or not isinstance(g.away_points, int):
            continue
        for school, pts, opp in ((g.home_team, g.home_points, g.away_points), (g.away_team, g.away_points, g.home_points)):
            line = lines.get(school or "")
            if line is None or pts == opp:
                continue
            if pts > opp:
                line.total_wins += 1
            else:
                line.total_losses += 1


def _order(lines: dict[str, Line]) -> list[Line]:
    return sorted(lines.values(), key=lambda line: (-line.pct, -line.wins, line.losses, line.team))


def _rank(wins: int, others: list[int], ties_count_against: bool) -> int:
    above = sum(1 for w in others if w > wins)
    level = sum(1 for w in others if w == wins) if ties_count_against else 0
    return 1 + above + level


def _relevant_games(lines: dict[str, Line], team: str) -> tuple[list[Game], set[str]]:
    """The teams that can still finish level with or above `team`'s worst case, and the games left that involve any of
    them or the team itself."""
    me = lines[team]
    threats = {t for t, line in lines.items() if t != team and line.best >= me.wins}
    seen: set[int] = set()
    games: list[Game] = []
    for name in (team, *sorted(threats)):
        for g in lines[name].left:
            if g.id not in seen:
                seen.add(g.id)
                games.append(g)
    return games, threats


def _finals(lines: dict[str, Line], games: list[Game], outcome: tuple[bool, ...]) -> dict[str, int]:
    """Final conference wins per team for one outcome (True: the home team wins) of the games played out."""
    wins = {t: line.wins for t, line in lines.items()}
    for g, home_wins in zip(games, outcome, strict=True):
        wins[g.home_team if home_wins else g.away_team] += 1
    return wins


def status_of(lines: dict[str, Line], team: str) -> dict[str, Any]:
    """{"status": clinched|tiebreaker|alive|out, "exact": bool} for one team's title-game spot.

    clinched: a top-two finish whatever happens, ties counted against it. tiebreaker: a top-two finish whatever happens
    unless a tie goes against it. out: no top-two finish possible even with every tie in its favour. alive: the rest."""
    me = lines.get(team)
    if me is None:
        return {"status": "alive", "exact": False}
    others = [line for t, line in lines.items() if t != team]
    worst = _rank(me.wins, [o.best for o in others], True)  # everyone else wins out, every tie against us
    best = _rank(me.best, [o.wins for o in others], False)  # everyone else loses out, every tie for us
    if worst <= SPOTS:
        return {"status": "clinched", "exact": True}
    if best > SPOTS:
        return {"status": "out", "exact": True}
    games, _threats = _relevant_games(lines, team)
    if len(games) > RACE_MAX_GAMES:
        return {"status": "alive", "exact": False}
    worst_seen = 1
    best_seen = 1
    for outcome in itertools.product((True, False), repeat=len(games)):
        finals = _finals(lines, games, outcome)
        mine = finals[team]
        other_wins = [w for t, w in finals.items() if t != team]
        worst_seen = max(worst_seen, _rank(mine, other_wins, True))
        best_seen = max(best_seen, _rank(mine, other_wins, False))
    if worst_seen <= SPOTS:
        return {"status": "clinched", "exact": True}
    if best_seen <= SPOTS:
        return {"status": "tiebreaker", "exact": True}
    # out when no outcome at all reaches the spots with ties in our favour
    reachable = False
    for outcome in itertools.product((True, False), repeat=len(games)):
        finals = _finals(lines, games, outcome)
        if _rank(finals[team], [w for t, w in finals.items() if t != team], False) <= SPOTS:
            reachable = True
            break
    return {"status": "alive" if reachable else "out", "exact": True}


def _verdict(lines: dict[str, Line], team: str, our_wins_total: int) -> tuple[int, int]:
    """(worst rank, best rank) over every outcome of the other teams' games when we finish with `our_wins_total` wins
    (our own games fixed: the wins we take are against the opponents that leave the most doubt, so the words err on the
    careful side). Counting bounds when there are too many games to play out."""
    me = lines[team]
    games, _threats = _relevant_games(lines, team)
    ours = [g for g in games if team in (g.home_team, g.away_team)]
    theirs = [g for g in games if team not in (g.home_team, g.away_team)]
    wins_to_take = max(0, min(len(ours), our_wins_total - me.wins))
    if len(theirs) > RACE_MAX_GAMES:
        others = [line for t, line in lines.items() if t != team]
        return _rank(our_wins_total, [o.best for o in others], True), _rank(our_wins_total, [o.wins for o in others], False)
    worst_seen = 1
    best_seen = 1
    # which of our games we win: every choice, so a loss to a threat (which lifts the threat) is covered
    for ours_won in itertools.combinations(range(len(ours)), wins_to_take):
        fixed = []
        for index, g in enumerate(ours):
            we_are_home = g.home_team == team
            won = index in ours_won
            fixed.append(won if we_are_home else not won)
        for outcome in itertools.product((True, False), repeat=len(theirs)):
            finals = _finals(lines, [*ours, *theirs], (*fixed, *outcome))
            mine = finals[team]
            other_wins = [w for t, w in finals.items() if t != team]
            worst_seen = max(worst_seen, _rank(mine, other_wins, True))
            best_seen = max(best_seen, _rank(mine, other_wins, False))
    return worst_seen, best_seen


def _names(teams: list[str]) -> str:
    if not teams:
        return ""
    if len(teams) == 1:
        return teams[0]
    return ", ".join(teams[:-1]) + " and " + teams[-1]


def _few(names: list[str], most: int = 3) -> str:
    """Up to `most` names, then "and N more": a sixteen-team league in September has a dozen level with us."""
    if len(names) <= most:
        return _names(names)
    return ", ".join(names[:most]) + f" and {len(names) - most} more"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _times(n: int) -> str:
    return "once more" if n == 1 else "twice more" if n == 2 else f"{n} more times"


def _threat_words(lines: dict[str, Line], team: str, our_final: int) -> tuple[list[str], list[str]]:
    """The teams that must fall below us (with the losses each needs) and the teams that can tie us, when we finish with
    `our_final` wins. Two spots: the strongest team may finish above us; every other team that can must lose enough.
    A team we still play is counted as losing that game to us when we win out."""
    me = lines[team]
    above: list[tuple[int, str]] = []
    level: list[str] = []
    for name, line in lines.items():
        if name == team:
            continue
        meets = sum(1 for g in line.left if team in (g.home_team, g.away_team))
        best = line.best - meets if our_final == me.best else line.best  # winning out takes every game we still play against them
        if best > our_final:
            above.append((best, name))
        elif best == our_final:
            level.append(name)
    above.sort(reverse=True)
    needed = [f"{name} loses {_times(best - our_final)}" for best, name in above[SPOTS - 1 :]]
    return needed, level


def our_lines(lines: dict[str, Line], team: str, status: str) -> list[dict[str, str]]:
    """The four lines in words for our team: win out, win all but one, Saturday, the clinch number."""
    me = lines.get(team)
    if me is None or status in ("clinched", "out") or not me.left:
        return []
    out: list[dict[str, str]] = []
    left = len(me.left)
    for key, wins_total, lead in (("winOut", me.best, f"Win out ({left} left)"), ("allButOne", me.best - 1, "Win all but one")):
        if wins_total < me.wins:
            continue
        worst, best = _verdict(lines, team, wins_total)
        above, level = _threat_words(lines, team, wins_total)
        if worst <= SPOTS:
            text = "in."
        else:
            parts = []
            if above:
                parts.append("in only if " + _few(above))
            if level:
                parts.append(("and " if above else "in, unless ") + _few(level) + (" wins" if len(level) == 1 else " win") + " out too; then a tiebreaker")
            text = ", ".join(parts) + "." if parts else "in, unless a tie goes against us."
        out.append({"key": key, "lead": lead, "text": text})
    # Saturday: our next conference game
    nxt = me.left[0]
    opponent = nxt.away_team if nxt.home_team == team else nxt.home_team
    others = [line for t, line in lines.items() if t != team]
    after_win = _rank(me.wins + 1, [o.wins + (1 if o.team != opponent and any(g.week == nxt.week for g in o.left) else 0) for o in others], True)
    after_loss = _rank(me.wins, [o.wins for o in others], False)
    win_words = _place_words(after_win)
    loss_words = _place_words(after_loss)
    out.append({"key": "next", "lead": f"Beat {opponent}", "text": f"and we are no worse than {win_words}; lose, and we are no better than {loss_words}."})
    # the clinch number: our wins and the second-best threat's losses, any mix, as the magic number is reckoned
    bests = sorted(((o.best, o.team) for o in others), reverse=True)
    if len(bests) >= SPOTS:
        second = bests[SPOTS - 1][0]
        magic = second - me.wins + 1
        counted = [name for b, name in bests if b == second]
        if magic > 0:
            out.append({"key": "clinch", "lead": "Clinch number", "text": f"{magic}: each win of ours and each loss by {_names(counted)} counts one; a tie at the line goes to a tiebreaker."})
    return out


def _place_words(n: int) -> str:
    return {1: "first", 2: "second", 3: "third"}.get(n, _ordinal(n))


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def watch_list(lines: dict[str, Line], team: str, week: int | None, status: str) -> list[dict[str, Any]]:
    """The week's conference games that change our path: ours first, then every game with a team near us or above us,
    with whom to pull for and why."""
    me = lines.get(team)
    if me is None or week is None or status in ("clinched", "out"):
        return []
    threats = {t for t, line in lines.items() if t != team and line.best >= me.wins and line.wins >= me.wins - NEAR}
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    for line in _order(lines):
        for g in line.left:
            if g.week != week or g.id in seen:
                continue
            seen.add(g.id)
            home, away = g.home_team, g.away_team
            if team in (home, away):
                rows.insert(0, {"gameId": g.id, "home": home, "away": away, "kickoff": g.start_date, "ours": True, "pullFor": team, "why": "Our own game: the one that moves us most."})
                continue
            home_threat, away_threat = home in threats, away in threats
            if not home_threat and not away_threat:
                continue
            if home_threat and away_threat:
                lower = min((home, away), key=lambda t: (lines[t].pct, lines[t].wins))
                higher = away if lower == home else home
                why = f"Two teams in our way: a loss by {higher} helps most, and one of them must lose."
                pull = lower
            else:
                threat = home if home_threat else away
                pull = away if home_threat else home
                why = f"A loss by {threat} takes a team we could tie with out of the way." if lines[threat].best == me.best else f"A loss by {threat} opens a spot above us."
            rows.append({"gameId": g.id, "home": home, "away": away, "kickoff": g.start_date, "ours": False, "pullFor": pull, "why": why})
    return rows


_MEMO: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
MEMO_LIMIT = 8


def stamp_of(part: Any) -> str | None:
    """A part's fetch time as the memo's key (None for a failed part: played out again next time)."""
    fetched = getattr(part, "fetched", None)
    at = getattr(fetched, "fetched_at", None)
    return at.isoformat() if isinstance(at, datetime) else None


def compact(result: dict[str, Any] | None, standings: int = 6) -> dict[str, Any] | None:
    """The race as a program keeps it: the top of the standings, our line, the words, the week's games (the full
    standings stay on the Season page)."""
    if not isinstance(result, dict):
        return None
    rows = result.get("standings") if isinstance(result.get("standings"), list) else []
    return {**result, "standings": rows[:standings], "others": max(0, len(rows) - standings), "outCount": sum(1 for r in rows[standings:] if isinstance(r, dict) and r.get("status") == "out")}


def race(games: list[Game], team: str, conference: str, week: int | None = None, stamp: Any = None) -> dict[str, Any] | None:
    """The race of our conference. None for an independent or a conference the games do not name. `stamp` (the games'
    fetch time) keys a memo, since the outcomes are played out again only when the games change."""
    if not conference or not team:
        return None
    key = (stamp, team, conference, week) if stamp is not None else None
    if key is not None and key in _MEMO:
        _MEMO.move_to_end(key)
        return _MEMO[key]
    lines = lines_of(games, conference)
    if team not in lines:
        return None
    totals_of(games, lines)
    if week is None:
        me = lines[team]
        week = me.left[0].week if me.left else None
    statuses = {t: status_of(lines, t) for t in lines}
    ordered = _order(lines)
    standings = []
    for place, line in enumerate(ordered, start=1):
        standings.append(
            {
                "place": place,
                "team": line.team,
                "confWins": line.wins,
                "confLosses": line.losses,
                "wins": line.total_wins,
                "losses": line.total_losses,
                "left": len(line.left),
                "best": line.best,
                "status": statuses[line.team]["status"],
                "isUs": line.team == team,
            }
        )
    me = lines[team]
    mine = statuses[team]
    watch = watch_list(lines, team, week, mine["status"])
    helps = {row["gameId"]: {"pullFor": row["pullFor"], "why": row["why"], "ours": row["ours"]} for row in watch}
    result = {
        "conference": conference,
        "spots": SPOTS,
        "week": week,
        "settled": not any(line.left for line in lines.values()),
        "standings": standings,
        "us": {"team": team, "place": next(s["place"] for s in standings if s["isUs"]), "confWins": me.wins, "confLosses": me.losses, "left": len(me.left), "best": me.best, "status": mine["status"], "exact": mine["exact"]},
        "lines": our_lines(lines, team, mine["status"]),
        "watch": watch,
        "helps": helps,
    }
    if key is not None:
        _MEMO[key] = result
        while len(_MEMO) > MEMO_LIMIT:
            _MEMO.popitem(last=False)
    return result
