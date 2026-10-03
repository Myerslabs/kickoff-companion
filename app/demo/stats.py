"""Numbers from simulated plays: box scores, player lines, PPA, usage and the advanced metrics.

Counting follows the NCAA box score the app expects: a sack is a rush for the quarterback (its
yards come off the rushing total), a pass attempt is a completion, an incompletion or an
interception, two tacklers on a play split the tackle (each gets one total, no solo) and split a
sack or a tackle for loss in halves. Raw sums are kept (never averages) so a season is the sum of
its games.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from app.demo.sim import GameResult, Play

Pos = Callable[[int], str]

RUSH_TYPES = {"Rush", "Rushing Touchdown"}
PASS_TYPES = {"Pass Reception", "Pass Incompletion", "Passing Touchdown", "Sack", "Pass Interception Return", "Interception", "Interception Return Touchdown"}
FRONT_SEVEN = {"DL", "LB"}


def is_rush(p: Play) -> bool:
    return p.ptype in RUSH_TYPES or (p.ptype.startswith("Fumble") and "rusher" in p.d) or (p.ptype == "Safety" and "rusher" in p.d)


def is_pass(p: Play) -> bool:
    return p.ptype in PASS_TYPES or (p.ptype.startswith("Fumble") and "passer" in p.d) or (p.ptype == "Safety" and "passer" in p.d)


def scrimmage(plays: Iterable[Play], side: int) -> list[Play]:
    return [p for p in plays if p.side == side and (is_rush(p) or is_pass(p))]


def quarter(p: Play) -> int:
    return min(p.period, 4)


def line_yards(gained: int) -> float:
    """CFBD's line yards: a loss counts 120%, the first four yards 100%, five to ten 50%, beyond nothing."""
    if gained < 0:
        return 1.2 * gained
    return min(gained, 4) + 0.5 * max(0, min(gained, 10) - 4)


def second_level(gained: int) -> int:
    return max(0, min(gained, 10) - 5) if gained > 5 else 0


def open_field(gained: int) -> int:
    return max(0, gained - 10)


def is_explosive_ppa(p: Play) -> bool:
    return bool(p.success)


# -- player lines --------------------------------------------------------------------------
def player_lines(result: GameResult, side: int) -> dict[int, Counter]:
    """Raw counting stats for every player of `side` in one game."""
    lines: dict[int, Counter] = defaultdict(Counter)
    for p in result.plays:
        d = p.d
        offense = p.side == side
        t = p.ptype
        if t in ("Kickoff", "Kickoff Return Touchdown"):
            if not offense and "returner" in d and "ret" in d:
                r = lines[d["returner"]]
                ret = d["ret"] if t == "Kickoff" else 100 - d.get("land", 0)
                r["kr_no"] += 1
                r["kr_yds"] += ret
                r["kr_long"] = max(r["kr_long"], ret)
                r["kr_td"] += t == "Kickoff Return Touchdown"
                if t == "Kickoff Return Touchdown" and "xp" in d:
                    pass
            if offense:
                for tk in d.get("tacklers", []):
                    _tackle(lines, tk, len(d["tacklers"]))
            if t == "Kickoff Return Touchdown" and not offense and "xp" in d:
                _xp(lines, d)
            continue
        if t == "Punt":
            if offense:
                k = lines[d.get("punter", 0)]
                k["punts"] += 1
                k["punt_yds"] += d.get("kick", 0)
                k["punt_long"] = max(k["punt_long"], d.get("kick", 0))
                k["punt_tb"] += bool(d.get("touchback"))
                land = p.ytg - d.get("kick", 0)
                k["punt_in20"] += (0 < land <= 20) and not d.get("touchback") and "ret" not in d
                for tk in d.get("tacklers", []):
                    _tackle(lines, tk, len(d["tacklers"]))
            elif "ret" in d:
                r = lines[d["returner"]]
                r["pr_no"] += 1
                r["pr_yds"] += d["ret"]
                r["pr_long"] = max(r["pr_long"], d["ret"])
            continue
        if t in ("Field Goal Good", "Field Goal Missed"):
            if offense:
                k = lines[d.get("kicker", 0)]
                k["fga"] += 1
                if t == "Field Goal Good":
                    k["fgm"] += 1
                    k["fg_long"] = max(k["fg_long"], d.get("kick", 0))
            continue
        if t in ("Penalty", "Timeout", "End Period", "End of Half", "End of Game", "Two Point Pass"):
            continue
        if offense:
            if "passer" in d and not d.get("sack"):
                q = lines[d["passer"]]
                if "interceptor" in d:
                    q["pass_att"] += 1
                    q["int_thrown"] += 1
                else:
                    q["pass_att"] += 1
                    if d.get("complete"):
                        q["pass_comp"] += 1
                        q["pass_yds"] += p.gained
                        q["pass_td"] += t == "Passing Touchdown"
                        w = lines[d["target"]]
                        w["rec"] += 1
                        w["rec_yds"] += p.gained
                        w["rec_td"] += t == "Passing Touchdown"
                        w["rec_long"] = max(w["rec_long"], p.gained)
                    if "target" in d:
                        lines[d["target"]]["targets"] += 1
            if d.get("sack"):
                q = lines[d["passer"]]
                q["rush_car"] += 1
                q["rush_yds"] += p.gained
                q["sacked"] += 1
            if "rusher" in d:
                r = lines[d["rusher"]]
                r["rush_car"] += 1
                r["rush_yds"] += p.gained
                r["rush_td"] += t == "Rushing Touchdown"
                r["rush_long"] = max(r["rush_long"], p.gained)
            if "fumble" in d:
                f = lines[d["fumble"]]
                f["fum"] += 1
                f["fum_lost"] += d.get("recovered") != p.side
                if d.get("recovered") == p.side:
                    lines[d.get("recoverer", d["fumble"])]["fum_rec"] += 1
            if "xp" in d and t in ("Rushing Touchdown", "Passing Touchdown"):
                _xp(lines, d)
        else:
            tack = d.get("tacklers", [])
            for tk in tack:
                _tackle(lines, tk, len(tack))
                if "rusher" in d and p.gained < 0:
                    lines[tk]["tfl"] += 1 / len(tack)
            sackers = d.get("sackers", [])
            for sk in sackers:
                share = 1 / len(sackers)
                lines[sk]["sacks"] += share
                lines[sk]["tfl"] += share
                _tackle(lines, sk, len(sackers))
            if "broken_up" in d:
                lines[d["broken_up"]]["pd"] += 1
            if "hurry" in d:
                lines[d["hurry"]]["qb_hur"] += 1
            if "interceptor" in d:
                i = lines[d["interceptor"]]
                i["ints"] += 1
                i["pd"] += 1
                i["int_yds"] += d.get("ret", 0)
                i["int_td"] += t == "Interception Return Touchdown"
                i["def_td"] += t == "Interception Return Touchdown"
                if "xp" in d:
                    _xp(lines, d)
            if "fumble" in d and d.get("recovered") != p.side:
                lines[d.get("recoverer", 0)]["fum_rec"] += 1
    lines.pop(0, None)
    return lines


def _tackle(lines: dict[int, Counter], pid: int, count: int) -> None:
    lines[pid]["tot"] += 1
    if count == 1:
        lines[pid]["solo"] += 1


def _xp(lines: dict[int, Counter], d: dict[str, Any]) -> None:
    k = lines[d.get("kicker", 0)]
    k["xpa"] += 1
    k["xpm"] += bool(d.get("xp"))


def ppa_lines(result: GameResult, side: int) -> dict[int, Counter]:
    """PPA and usage counts for skill players: passers and targets on passes, rushers on runs."""
    out: dict[int, Counter] = defaultdict(Counter)
    for p in scrimmage(result.plays, side):
        if p.ppa is None:
            continue
        kind = "pass" if is_pass(p) else "rush"
        down_key = {1: "first", 2: "second", 3: "third"}.get(p.down)
        dtype = p.d.get("down_type", "standard")
        involved = []
        if kind == "pass":
            involved = [p.d.get("passer")] + ([p.d["target"]] if "target" in p.d else [])
        else:
            involved = [p.d.get("rusher")]
        for pid in involved:
            if not pid:
                continue
            c = out[pid]
            c["all_n"] += 1
            c["all"] += p.ppa
            c[f"{kind}_n"] += 1
            c[kind] += p.ppa
            if down_key:
                c[f"{down_key}_n"] += 1
                c[down_key] += p.ppa
            c[f"{dtype}_n"] += 1
            c[dtype] += p.ppa
            c[f"q{quarter(p)}_n"] += 1
            c[f"q{quarter(p)}"] += p.ppa
    return out


def usage_base(result: GameResult, side: int) -> Counter:
    """The team's own play counts that usage divides by."""
    c: Counter = Counter()
    for p in scrimmage(result.plays, side):
        kind = "pass" if is_pass(p) else "rush"
        c["all"] += 1
        c[kind] += 1
        down_key = {1: "first", 2: "second", 3: "third"}.get(p.down)
        if down_key:
            c[down_key] += 1
        c[p.d.get("down_type", "standard")] += 1
        c[f"q{quarter(p)}"] += 1
    return c


# -- team box ------------------------------------------------------------------------------
def team_counts(result: GameResult, side: int, pos: Pos) -> Counter:
    """Raw team counts for one side (offense and defense numbers both), summable over games."""
    c: Counter = Counter()
    lines = player_lines(result, side)
    for p in result.plays:
        d = p.d
        if p.ptype == "Penalty":
            if d.get("flag") == side:
                c["penalties"] += 1
                c["penalty_yds"] += d.get("yards", 0)
            if d.get("first") and p.side == side and d.get("flag") != side:
                c["first_downs"] += 1
            continue
        if p.side != side:
            continue
        if is_rush(p) or is_pass(p):
            if d.get("first") or p.ptype in ("Rushing Touchdown", "Passing Touchdown"):
                c["first_downs"] += 1
            if p.down == 3:
                c["third_att"] += 1
                c["third_conv"] += p.gained >= p.distance and "interceptor" not in d and d.get("recovered", side) == side
            if p.down == 4:
                c["fourth_att"] += 1
                c["fourth_conv"] += p.gained >= p.distance and "interceptor" not in d and d.get("recovered", side) == side
    for ln in lines.values():
        c["pass_comp"] += ln["pass_comp"]
        c["pass_att"] += ln["pass_att"]
        c["pass_yds"] += ln["pass_yds"]
        c["pass_td"] += ln["pass_td"]
        c["int_thrown"] += ln["int_thrown"]
        c["rush_att"] += ln["rush_car"]
        c["rush_yds"] += ln["rush_yds"]
        c["rush_td"] += ln["rush_td"]
        c["fumbles"] += ln["fum"]
        c["fumbles_lost"] += ln["fum_lost"]
        c["fumbles_rec"] += ln["fum_rec"]
        c["tackles"] += ln["tot"]
        c["sacks"] += ln["sacks"]
        c["tfl"] += ln["tfl"]
        c["pd"] += ln["pd"]
        c["qb_hur"] += ln["qb_hur"]
        c["def_td"] += ln["def_td"]
        c["ints"] += ln["ints"]
        c["int_yds"] += ln["int_yds"]
        c["int_td"] += ln["int_td"]
        c["kr"] += ln["kr_no"]
        c["kr_yds"] += ln["kr_yds"]
        c["kr_td"] += ln["kr_td"]
        c["pr"] += ln["pr_no"]
        c["pr_yds"] += ln["pr_yds"]
        c["pr_td"] += ln["pr_td"]
        c["kick_pts"] += 3 * ln["fgm"] + ln["xpm"]
    c["turnovers"] = c["int_thrown"] + c["fumbles_lost"]
    c["possession"] = possession_seconds(result, side)
    c["games"] = 1
    return c


def possession_seconds(result: GameResult, side: int) -> int:
    return sum(p.elapsed for p in result.plays if p.side == side and p.ptype not in ("Kickoff", "Punt", "Kickoff Return Touchdown")) + \
        sum(p.elapsed for p in result.plays if p.side != side and p.ptype in ("Kickoff", "Punt"))


def _clock(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _num(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.1f}"


def team_box_stats(c: Counter) -> list[dict[str, str]]:
    """/games/teams `stats` for one side, in the feed's own string formats."""
    rows = [
        ("firstDowns", str(c["first_downs"])),
        ("thirdDownEff", f"{c['third_conv']}-{c['third_att']}"),
        ("fourthDownEff", f"{c['fourth_conv']}-{c['fourth_att']}"),
        ("totalYards", str(c["pass_yds"] + c["rush_yds"])),
        ("netPassingYards", str(c["pass_yds"])),
        ("completionAttempts", f"{c['pass_comp']}-{c['pass_att']}"),
        ("yardsPerPass", f"{c['pass_yds'] / c['pass_att']:.1f}" if c["pass_att"] else "0.0"),
        ("rushingYards", str(c["rush_yds"])),
        ("rushingAttempts", str(c["rush_att"])),
        ("yardsPerRushAttempt", f"{c['rush_yds'] / c['rush_att']:.1f}" if c["rush_att"] else "0.0"),
        ("totalPenaltiesYards", f"{c['penalties']}-{c['penalty_yds']}"),
        ("turnovers", str(c["turnovers"])),
        ("fumblesLost", str(c["fumbles_lost"])),
        ("interceptions", str(c["int_thrown"])),
        ("possessionTime", _clock(c["possession"])),
        ("passesDeflected", str(c["pd"])),
        ("qbHurries", str(c["qb_hur"])),
        ("sacks", _num(c["sacks"])),
        ("tackles", str(c["tackles"])),
        ("defensiveTDs", str(c["def_td"])),
        ("tacklesForLoss", _num(c["tfl"])),
        ("passesIntercepted", str(c["ints"])),
        ("interceptionTDs", str(c["int_td"])),
        ("interceptionYards", str(c["int_yds"])),
        ("kickingPoints", str(c["kick_pts"])),
        ("kickReturns", str(c["kr"])),
        ("kickReturnTDs", str(c["kr_td"])),
        ("kickReturnYards", str(c["kr_yds"])),
        ("passingTDs", str(c["pass_td"])),
        ("rushingTDs", str(c["rush_td"])),
    ]
    if c["pr"]:
        rows += [("puntReturns", str(c["pr"])), ("puntReturnYards", str(c["pr_yds"])), ("puntReturnTDs", str(c["pr_td"]))]
    if c["fumbles"]:
        rows += [("totalFumbles", str(c["fumbles"]))]
    return [{"category": k, "stat": v} for k, v in rows]


def season_team_stats(c: Counter, o: Counter) -> list[tuple[str, int]]:
    """/stats/season rows (statName, statValue) for a team `c` and its opponents `o`."""
    rows = [
        ("games", c["games"]), ("firstDowns", c["first_downs"]), ("thirdDowns", c["third_att"]), ("thirdDownConversions", c["third_conv"]),
        ("fourthDowns", c["fourth_att"]), ("fourthDownConversions", c["fourth_conv"]), ("totalYards", c["pass_yds"] + c["rush_yds"]),
        ("netPassingYards", c["pass_yds"]), ("passCompletions", c["pass_comp"]), ("passAttempts", c["pass_att"]),
        ("passingTDs", c["pass_td"]), ("rushingYards", c["rush_yds"]), ("rushingAttempts", c["rush_att"]), ("rushingTDs", c["rush_td"]),
        ("penalties", c["penalties"]), ("penaltyYards", c["penalty_yds"]), ("turnovers", c["turnovers"]), ("fumblesLost", c["fumbles_lost"]),
        ("fumblesRecovered", c["fumbles_rec"]), ("interceptions", c["int_thrown"]), ("passesIntercepted", c["ints"]),
        ("interceptionYards", c["int_yds"]), ("interceptionTDs", c["int_td"]), ("sacks", round(c["sacks"])), ("tacklesForLoss", round(c["tfl"])),
        ("kickReturns", c["kr"]), ("kickReturnYards", c["kr_yds"]), ("kickReturnTDs", c["kr_td"]), ("puntReturns", c["pr"]),
        ("puntReturnYards", c["pr_yds"]), ("puntReturnTDs", c["pr_td"]), ("possessionTime", c["possession"]),
    ]
    opponent = [
        ("firstDownsOpponent", o["first_downs"]), ("thirdDownsOpponent", o["third_att"]), ("thirdDownConversionsOpponent", o["third_conv"]),
        ("fourthDownsOpponent", o["fourth_att"]), ("fourthDownConversionsOpponent", o["fourth_conv"]),
        ("totalYardsOpponent", o["pass_yds"] + o["rush_yds"]), ("netPassingYardsOpponent", o["pass_yds"]),
        ("passCompletionsOpponent", o["pass_comp"]), ("passAttemptsOpponent", o["pass_att"]), ("passingTDsOpponent", o["pass_td"]),
        ("rushingYardsOpponent", o["rush_yds"]), ("rushingAttemptsOpponent", o["rush_att"]), ("rushingTDsOpponent", o["rush_td"]),
        ("penaltiesOpponent", o["penalties"]), ("penaltyYardsOpponent", o["penalty_yds"]), ("turnoversOpponent", o["turnovers"]),
        ("fumblesLostOpponent", o["fumbles_lost"]), ("fumblesRecoveredOpponent", o["fumbles_rec"]),
        ("interceptionsOpponent", o["int_thrown"]), ("passesInterceptedOpponent", o["ints"]),
        ("interceptionYardsOpponent", o["int_yds"]), ("interceptionTDsOpponent", o["int_td"]), ("sacksOpponent", round(o["sacks"])),
        ("tacklesForLossOpponent", round(o["tfl"])), ("kickReturnsOpponent", o["kr"]), ("kickReturnYardsOpponent", o["kr_yds"]),
        ("kickReturnTDsOpponent", o["kr_td"]), ("possessionTimeOpponent", o["possession"]),
    ]
    return rows + opponent


# -- advanced ------------------------------------------------------------------------------
def advanced_counts(result: GameResult, side: int, pos: Pos) -> Counter:
    """Raw sums for the offense of `side` (the defense's numbers are the opponent's offense)."""
    c: Counter = Counter()
    plays = scrimmage(result.plays, side)
    for p in plays:
        ppa = p.ppa or 0.0
        kind = "rush" if is_rush(p) else "pass"
        dtype = p.d.get("down_type", "standard")
        c["plays"] += 1
        c["ppa"] += ppa
        for key in (kind, dtype):
            c[f"{key}_n"] += 1
            c[f"{key}_ppa"] += ppa
        if p.success:
            c["succ"] += 1
            c["expl"] += ppa
            c[f"{kind}_succ"] += 1
            c[f"{kind}_expl"] += ppa
            c[f"{dtype}_succ"] += 1
            c[f"{dtype}_expl"] += ppa
        if kind == "rush":
            g = p.gained
            c["line_yds"] += line_yards(g)
            c["second_yds"] += second_level(g)
            c["open_yds"] += open_field(g)
            c["stuffed"] += g <= 0
            if p.down in (3, 4) and p.distance <= 2:
                c["power_n"] += 1
                c["power_succ"] += g >= p.distance
        d = p.d
        # havoc against this offense, credited to the defense's players
        havoc_players = list(d.get("sackers", [])) + ([d["interceptor"]] if "interceptor" in d else []) + ([d["broken_up"]] if "broken_up" in d else [])
        if "rusher" in d and p.gained < 0:
            havoc_players += d.get("tacklers", [])[:1]
        if "fumble" in d:
            havoc_players += d.get("tacklers", [])[:1] or [d.get("recoverer", 0)]
        if havoc_players:
            c["havoc"] += 1
            if pos(havoc_players[0]) in FRONT_SEVEN:
                c["havoc_front"] += 1
            else:
                c["havoc_db"] += 1
    for dr in result.drives:
        if dr.side != side:
            continue
        c["drives"] += 1
        c["start_ytg"] += dr.start_ytg
        c["start_ep"] += _ep(dr.start_ytg)
        reached = dr.end_ytg <= 40 or dr.result in ("TD", "FG", "MISSED FG")
        if reached:
            c["opps"] += 1
            c["opp_points"] += 7 if dr.result == "TD" else 3 if dr.result == "FG" else 0
    return c


def _ep(ytg: int) -> float:
    from app.demo.sim import expected_points

    return expected_points(ytg)


def advanced_block(c: Counter) -> dict[str, Any]:
    """The /stats/season/advanced offense or defense block from summed raw counts."""

    def div(a: float, b: float) -> float:
        return a / b if b else 0.0

    rush_n = c["rush_n"]
    return {
        "plays": c["plays"],
        "drives": c["drives"],
        "ppa": div(c["ppa"], c["plays"]),
        "totalPPA": c["ppa"],
        "successRate": div(c["succ"], c["plays"]),
        "explosiveness": div(c["expl"], c["succ"]),
        "powerSuccess": div(c["power_succ"], c["power_n"]),
        "stuffRate": div(c["stuffed"], rush_n),
        "lineYards": div(c["line_yds"], rush_n),
        "lineYardsTotal": round(c["line_yds"]),
        "secondLevelYards": div(c["second_yds"], rush_n),
        "secondLevelYardsTotal": c["second_yds"],
        "openFieldYards": div(c["open_yds"], rush_n),
        "openFieldYardsTotal": c["open_yds"],
        "totalOpportunies": c["opps"],
        "pointsPerOpportunity": div(c["opp_points"], c["opps"]),
        "fieldPosition": {"averageStart": round(div(c["start_ytg"], c["drives"]), 1), "averagePredictedPoints": round(div(c["start_ep"], c["drives"]), 3)},
        "havoc": {"total": round(div(c["havoc"], c["plays"]), 3), "frontSeven": round(div(c["havoc_front"], c["plays"]), 3), "db": round(div(c["havoc_db"], c["plays"]), 3)},
        "standardDowns": {"rate": div(c["standard_n"], c["plays"]), "ppa": div(c["standard_ppa"], c["standard_n"]),
                          "successRate": div(c["standard_succ"], c["standard_n"]), "explosiveness": div(c["standard_expl"], c["standard_succ"])},
        "passingDowns": {"rate": div(c["passing_n"], c["plays"]), "ppa": div(c["passing_ppa"], c["passing_n"]),
                         "successRate": div(c["passing_succ"], c["passing_n"]), "explosiveness": div(c["passing_expl"], c["passing_succ"])},
        "rushingPlays": {"rate": div(c["rush_n"], c["plays"]), "ppa": div(c["rush_ppa"], c["rush_n"]), "totalPPA": c["rush_ppa"],
                         "successRate": div(c["rush_succ"], c["rush_n"]), "explosiveness": div(c["rush_expl"], c["rush_succ"])},
        "passingPlays": {"rate": div(c["pass_n"], c["plays"]), "ppa": div(c["pass_ppa"], c["pass_n"]), "totalPPA": c["pass_ppa"],
                         "successRate": div(c["pass_succ"], c["pass_n"]), "explosiveness": div(c["pass_expl"], c["pass_succ"])},
    }


def ppa_split(plays: list[Play]) -> dict[str, float]:
    """Average PPA overall, passing, rushing and by down, for /ppa/games."""
    def avg(sel: list[Play]) -> float:
        vals = [p.ppa for p in sel if p.ppa is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "overall": avg(plays),
        "passing": avg([p for p in plays if is_pass(p)]),
        "rushing": avg([p for p in plays if is_rush(p)]),
        "firstDown": avg([p for p in plays if p.down == 1]),
        "secondDown": avg([p for p in plays if p.down == 2]),
        "thirdDown": avg([p for p in plays if p.down == 3]),
    }
