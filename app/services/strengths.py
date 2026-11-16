"""Strengths and weaknesses (ENH-11, with chart 1 of ENH-19). The owner, 2026-10-23: "Strengths and weaknesses should be in
a few categories, like this: Offense (Run, Pass), Defense (Run, Pass), Special Teams, Coaching (Base this on the coaches
overall win loss percentage), Talent, Cost"; asked career or current school, "Both"; cost "can be filled in from the prompt
in the settings, the roster cost one, so link to it". His board of 2026-10-28
("Build it"): a band under Tale of the tape, run and pass ranked by CFBD's points added per play, each team's bar growing
from the middle toward its own side.

Every rank is national and out of the teams that have the number, 1 the best, ties sharing a rank (the one tie rule):
run and pass among the FBS teams of the season's advanced stats, special teams among SP+'s, talent among the 247
composite's, coaching among the season's FBS head coaches, cost among the schools whose roster costs are loaded.

Coaching reads CFBD's /coaches for every coach since 1990 in one answer (checked against the live reference and a real
answer, 2026-10-28). CFBD keeps the season under way at 0-0 until it ends (Florida's Jon Sumrall, Georgia's Kirby Smart,
2026-10-21 and 10-28), so that season's row is never read: the school's finished games this season count instead. A school
with two head coaches listed this season (a mid-season change) takes the one hired last.

    coach_records(coaches, games, season, fbs) -> {school: {coach, career, school, careerRank, schoolRank, of}}
    block(advanced_us, advanced_them, special, talent, coaching, costs, us, them) -> the program's `strengths`
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from app.cfbd.models import Coach, Game
from app.services.profiles import advanced_key, tie_ranks
from app.services.stats_extra import RankTable

COACH_MIN_YEAR = 1990  # every coach in charge today began after it; one answer of about 700 coaches

# (group, row key, label, advanced side, advanced attribute, words after the value)
PPA_ROWS = (
    ("offense", "offenseRun", "Run", "offense", "rushing_plays.ppa", "a run"),
    ("offense", "offensePass", "Pass", "offense", "passing_plays.ppa", "a pass"),
    ("defense", "defenseRun", "Run", "defense", "rushing_plays.ppa", "allowed"),
    ("defense", "defensePass", "Pass", "defense", "passing_plays.ppa", "allowed"),
)


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def ranked(values: dict[str, float], higher: bool = True) -> tuple[dict[str, int], dict[str, bool], int]:
    """(rank by key, whether that rank is shared, how many were ranked), the one tie rule."""
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=higher)
    ranks = dict(zip((k for k, _ in ordered), tie_ranks([v for _, v in ordered]), strict=True))
    shared: dict[int, int] = {}
    for rank in ranks.values():
        shared[rank] = shared.get(rank, 0) + 1
    return ranks, {k: shared[r] > 1 for k, r in ranks.items()}, len(ordered)


def season_records(games: Iterable[Game], season: int) -> dict[str, tuple[int, int]]:
    """school -> (wins, losses) from this season's finished games with both scores."""
    out: dict[str, tuple[int, int]] = {}
    for g in games:
        if not isinstance(g, Game) or not g.completed or g.home_points is None or g.away_points is None:
            continue
        if g.season is not None and g.season != season:
            continue
        for team, mine, theirs in ((g.home_team, g.home_points, g.away_points), (g.away_team, g.away_points, g.home_points)):
            if isinstance(team, str) and team:
                won, lost = out.get(team, (0, 0))
                out[team] = (won + (mine > theirs), lost + (mine < theirs))
    return out


def coach_records(coaches: Iterable[Coach], games: Iterable[Game], season: int, fbs: set[str] | None) -> dict[str, dict[str, Any]]:
    """Each FBS school's head coach this season: his career record and his record at the school (earlier seasons from CFBD,
    this one from the games), each win percentage ranked among the season's FBS head coaches."""
    current: dict[str, Coach] = {}
    for c in coaches:
        if not isinstance(c, Coach):
            continue
        here = next((s for s in c.seasons if s.year == season and isinstance(s.school, str) and s.school and (fbs is None or s.school in fbs)), None)
        if here is None:
            continue
        held = current.get(here.school)
        if held is None or (c.hire_date or "") > (held.hire_date or ""):
            current[here.school] = c
    now = season_records(games, season)
    lines: dict[str, dict[str, Any]] = {}
    for school, c in current.items():
        past = [s for s in c.seasons if isinstance(s.year, int) and s.year < season]
        tw, tl = now.get(school, (0, 0))
        cw = sum(_count(s.wins) for s in past) + tw
        cl = sum(_count(s.losses) for s in past) + tl
        sw = sum(_count(s.wins) for s in past if s.school == school) + tw
        sl = sum(_count(s.losses) for s in past if s.school == school) + tl
        name = " ".join(p for p in (c.first_name, c.last_name) if isinstance(p, str) and p.strip()) or None
        lines[school] = {"coach": name, "career": (cw, cl), "school": (sw, sl)}

    def pct(record: tuple[int, int]) -> float | None:
        won, lost = record
        return won / (won + lost) if won + lost else None

    for which in ("career", "school"):
        values = {school: p for school, line in lines.items() if (p := pct(line[which])) is not None}
        ranks, ties, of = ranked(values)
        for school, line in lines.items():
            line[f"{which}Rank"] = ranks.get(school)
            line[f"{which}Tie"] = ties.get(school, False)
            line[f"{which}Pct"] = round(values[school], 3) if school in values else None
            line["of"] = of or None
    return lines


def cost_ranks(teams: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """school -> {totalUsd, rank, tie, of} among the schools whose rumored roster total is loaded."""
    totals = {school: v for school, row in (teams or {}).items() if isinstance(row, dict) and (v := _finite(row.get("totalUsd"))) is not None and v > 0}
    ranks, ties, of = ranked(totals)
    return {school: {"totalUsd": totals[school], "rank": ranks[school], "tie": ties[school], "of": of} for school in totals}


def _side(value: Any, rank: Any, of: Any, metric: str | None, **extra: Any) -> dict[str, Any]:
    ok = isinstance(rank, int) and not isinstance(rank, bool)
    return {"value": value, "rank": rank if ok else None, "of": of if ok else None, "metric": metric if ok else None, **extra}


def block(advanced_us: list[dict[str, Any]], advanced_them: list[dict[str, Any]], special: RankTable | None, talent: dict[str, dict[str, Any]], coaching: dict[str, dict[str, Any]], costs: dict[str, dict[str, Any]], us: str, them: str | None) -> dict[str, Any]:
    """The program's `strengths`: the groups of rows in the owner's order, each row both teams' value, rank and list, then
    the cost (its own shape: a total and its rank among the schools loaded, None for a school not loaded)."""

    def ppa_side(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
        row = next((r for r in rows if isinstance(r, dict) and r.get("key") == key), {})
        return _side(row.get("value"), row.get("nationalRank"), row.get("nationalOf"), row.get("metric"))

    groups: list[dict[str, Any]] = []
    for group, label in (("offense", "Offense"), ("defense", "Defense")):
        rows = []
        for g, key, row_label, side, attr, words in PPA_ROWS:
            if g != group:
                continue
            akey = advanced_key(side, attr)
            rows.append({"key": key, "label": row_label, "format": "+2f", "words": words, "us": ppa_side(advanced_us, akey), "them": ppa_side(advanced_them, akey)})
        groups.append({"key": group, "label": label, "rows": rows})

    def special_side(school: str | None) -> dict[str, Any]:
        if special is None or not school or special.value(school) is None:
            return _side(None, None, None, None)
        return _side(special.value(school), special.rank(school), special.of or None, "rating:spSpecial")

    groups.append({"key": "special", "label": "Special teams", "rows": [{"key": "special", "label": "SP+ special teams", "format": "+1f", "words": "", "us": special_side(us), "them": special_side(them)}]})

    def coach_side(school: str | None, which: str) -> dict[str, Any]:
        line = coaching.get(school or "")
        if not line:
            return _side(None, None, None, None, wins=None, losses=None, tie=False)
        wins, losses = line[which]
        return _side(line.get(f"{which}Pct"), line.get(f"{which}Rank"), line.get("of"), None, wins=wins, losses=losses, tie=bool(line.get(f"{which}Tie")))

    groups.append({
        "key": "coaching",
        "label": "Coaching",
        "coaches": {"us": (coaching.get(us) or {}).get("coach"), "them": (coaching.get(them or "") or {}).get("coach")},
        "rows": [
            {"key": "coachCareer", "label": "Career", "format": "pct3", "words": "", "us": coach_side(us, "career"), "them": coach_side(them, "career")},
            {"key": "coachSchool", "label": "At this school", "format": "pct3", "words": "", "us": coach_side(us, "school"), "them": coach_side(them, "school")},
        ],
    })

    def talent_side(school: str | None) -> dict[str, Any]:
        t = talent.get(school or "") or {}
        return _side(t.get("talent"), t.get("rank"), t.get("of"), t.get("metric"))

    groups.append({"key": "talent", "label": "Talent", "rows": [{"key": "talent", "label": "247 composite", "format": "0f", "words": "", "us": talent_side(us), "them": talent_side(them)}]})

    of = next((c["of"] for c in costs.values()), 0) or None
    return {"groups": groups, "cost": {"us": costs.get(us), "them": costs.get(them or ""), "of": of}}
