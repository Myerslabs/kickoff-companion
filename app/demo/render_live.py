"""The game-level answers built from a game's plays: the advanced box score, the live document
(/live/plays) and the scoreboard. A game in progress shows only the plays the clock has reached."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.demo import stats as S
from app.demo.league import as_iso
from app.demo.render import Params, _visible_count, lines_for, p_int, p_str, same, weather_for
from app.demo.season import Record, World
from app.demo.sim import PLAY_TYPE_IDS, GameResult, Play
from app.demo.text import play_text

LOCATIONS = ("unknown", "deep left", "deep right", "short left", "deep middle", "short right", "short middle")
DIRECTIONS = ("left", "right", "middle", "unknown")


def _div(a: float, b: float, digits: int = 3) -> float:
    return round(a / b, digits) if b else 0


def _pass_block(plays: list[Play], with_locations: bool = True) -> dict[str, Any]:
    att = [p for p in plays if not p.d.get("sack")]
    comp = [p for p in att if p.d.get("complete")]
    ints = [p for p in att if "interceptor" in p.d]
    succ = [p for p in att if p.success]
    ppa = sum(p.ppa or 0 for p in att)
    air = sum(p.d.get("air", 0) for p in att)
    yac = sum(p.d.get("yac", 0) for p in comp)
    yards = sum(p.gained for p in comp)
    block = {
        "ppa": _div(ppa, len(att)), "attempts": len(att), "totalPpa": round(ppa, 3), "totalYards": yards, "completions": len(comp),
        "successRate": _div(len(succ), len(att)), "explosiveness": _div(sum(p.ppa or 0 for p in succ), len(succ)),
        "incompletions": len(att) - len(comp) - len(ints), "interceptions": len(ints), "totalAirYards": air,
        "completionRate": _div(len(comp), len(att)), "successfulAttempts": len(succ), "averageDepthOfTarget": _div(air, len(att), 1),
        "ppaAttemptsAvailable": len(att), "totalYardsAfterCatch": yac, "averageYardsAfterCatch": _div(yac, len(comp), 1),
        "locationEligibleAttempts": len(att), "successAttemptsAvailable": len(att), "airYardsAttemptsAvailable": len(att),
        "locationAvailableAttempts": len(att), "totalYardsAttemptsAvailable": len(att), "successfulPpaAttemptsAvailable": len(succ),
        "yardsAfterCatchAttemptsAvailable": len(comp),
    }
    if with_locations:
        block["locations"] = {loc: _location(att, loc) for loc in LOCATIONS}
    return block


def _location(att: list[Play], loc: str) -> dict[str, Any]:
    rows = [p for p in att if f"{p.d.get('depth')} {p.d.get('dir')}" == loc]
    if not rows:
        return {"ppa": 0, "attempts": 0, "totalPpa": 0, "totalYards": None, "completions": 0, "successRate": 0, "explosiveness": 0,
                "incompletions": 0, "interceptions": 0, "totalAirYards": None, "completionRate": None, "yardsPerAttempt": None,
                "airYardsPerAttempt": None, "successfulAttempts": 0, "averageDepthOfTarget": None, "ppaAttemptsAvailable": 0,
                "totalYardsAfterCatch": None, "averageYardsAfterCatch": None, "successAttemptsAvailable": 0, "airYardsAttemptsAvailable": 0,
                "totalYardsAttemptsAvailable": 0, "successfulPpaAttemptsAvailable": 0, "yardsAfterCatchAttemptsAvailable": 0}
    b = _pass_block(rows, with_locations=False)
    for key in ("locationEligibleAttempts", "locationAvailableAttempts"):
        b.pop(key, None)
    b["yardsPerAttempt"] = _div(b["totalYards"], b["attempts"], 1)
    b["airYardsPerAttempt"] = _div(b["totalAirYards"], b["attempts"], 1)
    return b


def _rush_numbers(rows: list[Play]) -> dict[str, Any]:
    n = len(rows)
    gained = [p.gained for p in rows]
    succ = [p for p in rows if p.success]
    line = sum(S.line_yards(g) for g in gained)
    second = sum(S.second_level(g) for g in gained)
    openf = sum(S.open_field(g) for g in gained)
    power = [p for p in rows if p.down in (3, 4) and p.distance <= 2]
    ppa = sum(p.ppa or 0 for p in rows)
    return {
        "ppa": _div(ppa, n), "yards": sum(gained), "carries": n, "totalPpa": round(ppa, 3), "lineYards": _div(line, n, 1),
        "stuffRate": _div(sum(1 for g in gained if g <= 0), n), "successRate": _div(len(succ), n),
        "powerSuccess": _div(sum(1 for p in power if p.gained >= p.distance), len(power)), "explosiveness": _div(sum(p.ppa or 0 for p in succ), len(succ)),
        "yardsPerCarry": _div(sum(gained), n, 1), "lineYardsTotal": round(line, 1), "openFieldYards": _div(openf, n, 1),
        "secondLevelYards": _div(second, n, 1), "openFieldYardsTotal": openf, "secondLevelYardsTotal": second,
    }


def _direction(p: Play) -> str:
    d = (p.d.get("dir") or "").split()
    return d[0] if d and d[0] in ("left", "right", "middle") else "unknown"


def _rush_block(rows: list[Play], sacks: int) -> dict[str, Any]:
    base = _rush_numbers(rows)
    kneels = sum(1 for p in rows if p.d.get("kneel"))
    return {
        "ppa": base["ppa"], "sacks": sacks, "kneels": kneels, "attempts": len(rows) + sacks, "totalPpa": base["totalPpa"],
        "lineYards": base["lineYards"], "stuffRate": base["stuffRate"],
        "directions": {d: _rush_numbers([p for p in rows if _direction(p) == d]) for d in DIRECTIONS},
        "teamRushes": 0, "successRate": base["successRate"], "powerSuccess": base["powerSuccess"], "explosiveness": base["explosiveness"],
        "yardsPerCarry": base["yardsPerCarry"], "lineYardsTotal": base["lineYardsTotal"], "openFieldYards": base["openFieldYards"],
        "secondLevelYards": base["secondLevelYards"], "rushingTouchdowns": sum(1 for p in rows if p.ptype == "Rushing Touchdown"),
        "totalRushingYards": base["yards"], "individualAttempts": len(rows), "openFieldYardsTotal": base["openFieldYardsTotal"],
        "multiCarrierAttempts": 0, "unattributedAttempts": 0, "rushingYardsAvailable": len(rows), "secondLevelYardsTotal": base["secondLevelYardsTotal"],
        "touchdownStatusAvailable": len(rows), "directionEligibleAttempts": len(rows), "directionAvailableAttempts": len(rows),
    }


def _by_quarter(plays: list[Play], fn) -> dict[str, Any]:
    out = {"total": fn(plays)}
    for q in (1, 2, 3, 4):
        out[f"quarter{q}"] = fn([p for p in plays if S.quarter(p) == q])
    return out


def _avg_ppa(rows: list[Play]) -> float:
    vals = [p.ppa for p in rows if p.ppa is not None]
    return round(sum(vals) / len(vals), 3) if vals else 0


def _sum_ppa(rows: list[Play]) -> float:
    return round(sum(p.ppa or 0 for p in rows), 1)


def _succ(rows: list[Play]) -> float:
    return round(sum(1 for p in rows if p.success) / len(rows), 3) if rows else 0


def _expl(rows: list[Play]) -> float:
    s = [p for p in rows if p.success]
    return round(sum(p.ppa or 0 for p in s) / len(s), 2) if s else 0


def box_advanced(world: World, r: Record, result: GameResult) -> dict[str, Any]:
    league = world.league
    h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
    teams = (h, a)
    base = {"week": r.slot.week, "gameId": r.id, "season": r.slot.season, "seasonType": r.slot.season_type}
    out_teams: dict[str, list] = defaultdict(list)
    out_players: dict[str, list] = defaultdict(list)
    for side, t in enumerate(teams):
        opp = teams[1 - side]
        own = S.scrimmage(result.plays, side)
        theirs = S.scrimmage(result.plays, 1 - side)
        passes = [p for p in own if S.is_pass(p)]
        rushes = [p for p in own if S.is_rush(p)]
        out_teams["ppa"].append({"team": t.school, "plays": len(own), "overall": _by_quarter(own, _avg_ppa),
                                 "passing": _by_quarter(passes, _avg_ppa), "rushing": _by_quarter(rushes, _avg_ppa)})
        out_teams["cumulativePpa"].append({"team": t.school, "plays": len(own), "overall": _by_quarter(own, _sum_ppa),
                                           "passing": _by_quarter(passes, _sum_ppa), "rushing": _by_quarter(rushes, _sum_ppa)})
        std = [p for p in own if p.d.get("down_type") != "passing"]
        pdn = [p for p in own if p.d.get("down_type") == "passing"]
        out_teams["successRates"].append({"team": t.school, "overall": _by_quarter(own, _succ), "passingDowns": _by_quarter(pdn, _succ),
                                          "standardDowns": _by_quarter(std, _succ)})
        out_teams["explosiveness"].append({"team": t.school, "overall": _by_quarter(own, _expl)})
        adv = r.advanced[side]
        out_teams["fieldPosition"].append({"team": t.school, "averageStart": round(adv["start_ytg"] / adv["drives"], 1) if adv["drives"] else 0,
                                           "averageStartingPredictedPoints": round(adv["start_ep"] / adv["drives"], 2) if adv["drives"] else 0})
        out_teams["scoringOpportunities"].append({"team": t.school, "points": int(adv["opp_points"]), "opportunities": int(adv["opps"]),
                                                  "pointsPerOpportunity": round(adv["opp_points"] / adv["opps"], 2) if adv["opps"] else 0})
        d_adv = r.advanced[1 - side]
        plays_faced = d_adv["plays"]
        out_teams["havoc"].append({"db": _div(d_adv["havoc_db"], plays_faced), "team": t.school, "total": _div(d_adv["havoc"], plays_faced),
                                   "frontSeven": _div(d_adv["havoc_front"], plays_faced)})
        out_teams["passing"].append({"team": t.school, **base, "defense": _pass_block([p for p in theirs if S.is_pass(p)]),
                                     "offense": _pass_block(passes), "opponent": opp.school, "conference": t.conference})
        rush_own = [p for p in rushes]
        rush_their = [p for p in theirs if S.is_rush(p)]
        out_teams["rushing"].append({"team": t.school, "lineYards": round(sum(S.line_yards(p.gained) for p in rush_own)),
                                     "stuffRate": _div(sum(1 for p in rush_own if p.gained <= 0), len(rush_own)),
                                     "powerSuccess": _rush_numbers(rush_own)["powerSuccess"],
                                     "openFieldYards": sum(S.open_field(p.gained) for p in rush_own),
                                     "lineYardsAverage": _div(sum(S.line_yards(p.gained) for p in rush_own), len(rush_own), 1),
                                     "secondLevelYards": sum(S.second_level(p.gained) for p in rush_own),
                                     "openFieldYardsAverage": _div(sum(S.open_field(p.gained) for p in rush_own), len(rush_own), 1),
                                     "secondLevelYardsAverage": _div(sum(S.second_level(p.gained) for p in rush_own), len(rush_own), 1)})
        out_teams["rushingAdvanced"].append({"team": t.school, **base,
                                             "defense": _rush_block(rush_their, sum(1 for p in theirs if p.d.get("sack"))),
                                             "offense": _rush_block(rush_own, sum(1 for p in own if p.d.get("sack"))),
                                             "opponent": opp.school, "conference": t.conference, "seasonType": r.slot.season_type})
        # players
        ppa_lines = r.ppa[side]
        usage = r.usage[side]
        for pid, c in sorted(ppa_lines.items(), key=lambda x: -x[1]["all_n"]):
            p = league.players.get(str(pid))
            if p is None:
                continue

            def avg(key: str, c=c) -> float | None:
                return round(c[key] / c[f"{key}_n"], 3) if c[f"{key}_n"] else None

            out_players["ppa"].append({"team": t.school, "player": p.name,
                                       "average": {"total": avg("all"), "passing": avg("pass") or 0, "rushing": avg("rush") or 0,
                                                   "quarter1": avg("q1"), "quarter2": avg("q2"), "quarter3": avg("q3"), "quarter4": avg("q4")},
                                       "position": p.position,
                                       "cumulative": {"total": round(c["all"], 1), "passing": round(c["pass"], 1), "rushing": round(c["rush"], 1),
                                                      "quarter1": round(c["q1"], 1), "quarter2": round(c["q2"], 1), "quarter3": round(c["q3"], 1),
                                                      "quarter4": round(c["q4"], 1)}})
            out_players["usage"].append({"team": t.school, "total": _div(c["all_n"], usage["all"]), "player": p.name,
                                         "passing": _div(c["pass_n"], usage["pass"]), "rushing": _div(c["rush_n"], usage["rush"]), "position": p.position,
                                         "quarter1": _div(c["q1_n"], usage["q1"]), "quarter2": _div(c["q2_n"], usage["q2"]),
                                         "quarter3": _div(c["q3_n"], usage["q3"]), "quarter4": _div(c["q4_n"], usage["q4"])})
        by_passer: dict[int, list[Play]] = defaultdict(list)
        by_rusher: dict[int, list[Play]] = defaultdict(list)
        sacks_of: Counter = Counter()
        for p in passes:
            if p.d.get("sack"):
                sacks_of[p.d.get("passer")] += 1
            else:
                by_passer[p.d.get("passer")].append(p)
        for p in rushes:
            by_rusher[p.d.get("rusher")].append(p)
        for pid, rows in by_passer.items():
            pl = league.players.get(str(pid))
            if pl is None:
                continue
            block = _pass_block(rows)
            out_players["passing"].append({**block, "team": t.school, **base, "player": pl.name, "opponent": opp.school, "playerId": pl.id,
                                           "conference": t.conference})
        for pid, rows in by_rusher.items():
            pl = league.players.get(str(pid))
            if pl is None:
                continue
            block = _rush_block(rows, sacks_of.get(pid, 0))
            block.pop("rushingTouchdowns", None)
            block.pop("touchdownStatusAvailable", None)
            out_players["rushing"].append({**block, "team": t.school, **base, "player": pl.name, "opponent": opp.school, "playerId": pl.id,
                                           "conference": t.conference})
    home_wp = 1.0 if r.home_points > r.away_points else 0.0
    post = 0.5 + (home_wp - 0.5) * 0.94
    return {
        "gameInfo": {"homeTeam": h.school, "homePoints": r.home_points, "homeWinProb": post, "awayTeam": a.school, "awayPoints": r.away_points,
                     "awayWinProb": 1 - post, "homeWinner": r.home_points > r.away_points, "excitement": r.excitement},
        "teams": dict(out_teams),
        "players": dict(out_players),
    }


def r_box_advanced(world: World, params: Params, now: datetime) -> dict | None:
    gid = p_int(params, "id") or p_int(params, "gameId")
    for data in world.seasons.values():
        r = data.by_id.get(gid) if gid else None
        if r is not None and r.end <= now:
            result = world.simulate(r.id)
            return box_advanced(world, r, result) if result else None
    return None


# -- live ------------------------------------------------------------------------------------
def _clock_str(seconds: int | None) -> str:
    if seconds is None:
        return "0:00"
    return f"{seconds // 60}:{seconds % 60:02d}"


def live_document(world: World, r: Record, now: datetime) -> dict[str, Any]:
    league = world.league
    h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
    result = world.simulate(r.id)
    count = _visible_count(r, result, now)
    final = count is None
    plays = result.plays if final else result.plays[:count]
    abbr, school = (h.abbr, a.abbr), (h.school, a.school)
    if not plays:
        return {"id": r.id, "status": "scheduled", "period": None, "clock": "", "possession": "", "down": None, "distance": None,
                "yardsToGoal": None, "teams": [_team_live(world, r, side, [], [], 1, empty=True) for side in (0, 1)], "drives": []}
    drives_out = []
    by_drive: dict[int, list[Play]] = defaultdict(list)
    current = 0
    for p in plays:  # a marker after a drive closed (the half's End Period, End of Game) stays in that drive, as CFBD's do
        current = p.drive or current
        by_drive[current].append(p)
    for d in result.drives:
        rows = by_drive.get(d.number)
        if not rows:
            continue
        finished = final or rows[-1].seq >= d.last_seq
        off, dfn = (h, a) if d.side == 0 else (a, h)
        play_rows = [_live_play(world, r, p, abbr, school) for p in rows]
        if finished:
            sc = d.start_clock or 0
            ec = d.end_clock or 0
            start_s = (d.start_period - 1) * 900 + 900 - sc if d.start_period <= 4 else 3600
            end_s = (d.end_period - 1) * 900 + 900 - ec if d.end_period <= 4 else 3600
            el = max(0, end_s - start_s)
            drives_out.append({
                "id": f"{r.id}{d.number}", "offenseId": off.id, "offense": off.school, "defenseId": dfn.id, "defense": dfn.school,
                "playCount": d.plays, "yards": d.yards, "startPeriod": d.start_period, "startClock": _clock_str(d.start_clock),
                "startYardsToGoal": d.start_ytg, "endPeriod": d.end_period, "endClock": _clock_str(d.end_clock), "endYardsToGoal": d.end_ytg,
                "duration": f"{el // 60}:{el % 60:02d}", "scoringOpportunity": d.end_ytg <= 40, "plays": play_rows,
                "result": _live_result(d.result), "pointsGained": (d.end_off_score - d.start_off_score),
            })
        else:
            last = rows[-1]
            drives_out.append({
                "id": f"{r.id}{d.number}", "offenseId": off.id, "offense": off.school, "defenseId": dfn.id, "defense": dfn.school,
                "playCount": len(rows), "yards": sum(p.gained for p in rows if p.side == d.side), "startPeriod": d.start_period,
                "startClock": _clock_str(d.start_clock), "startYardsToGoal": d.start_ytg, "endPeriod": last.period,
                "endClock": _clock_str(last.clock), "endYardsToGoal": None, "duration": None, "scoringOpportunity": None,
                "plays": play_rows, "result": None, "pointsGained": None,
            })
    last = plays[-1]
    upcoming = None if final else (result.plays[count] if count < len(result.plays) else None)
    situation = upcoming or last
    period = last.period
    teams = [_team_live(world, r, side, plays, drives_out, period) for side in (0, 1)]
    if final:
        return {"id": r.id, "status": "Final", "period": None, "clock": "", "possession": "", "down": None, "distance": None,
                "yardsToGoal": None, "teams": teams, "drives": drives_out}
    poss = situation.side if situation.ptype not in ("Kickoff",) else 1 - situation.side
    return {
        "id": r.id, "status": "in_progress", "period": last.period, "clock": _clock_str(max(0, (last.clock or 0) - last.elapsed)),
        "possession": (h if poss == 0 else a).school, "down": situation.down or None, "distance": situation.distance or None,
        "yardsToGoal": situation.ytg or None, "teams": teams, "drives": drives_out,
    }


def _live_result(result: str) -> str:
    return {"TD": "Touchdown", "FG": "Field Goal", "PUNT": "Punt", "MISSED FG": "Missed Field Goal", "INT": "Interception",
            "FUMBLE": "Fumble", "DOWNS": "Downs", "END OF HALF": "End of Half", "END OF GAME": "End of Game",
            "INT TD": "Interception Return Touchdown", "SAFETY": "Safety"}.get(result, result.title())


def _feed_success(p: Play) -> bool:
    """The feed's flag. CFBD judges every play with a down by the yards it gained, so a penalty or a punt
    can come out a success (the app judges scrimmage plays only); the sim's own call stands on a snap."""
    if p.success is not None:
        return bool(p.success)
    if p.down not in (1, 2, 3, 4) or not p.distance:
        return False
    return p.gained >= p.distance * {1: 0.5, 2: 0.7}.get(p.down, 1.0)


def _live_play(world: World, r: Record, p: Play, abbr, school) -> dict[str, Any]:
    league = world.league
    team = league.by_id[r.slot.home if p.side == 0 else r.slot.away]
    return {
        "id": f"{r.id}{p.seq}", "homeScore": p.home_after, "awayScore": p.away_after, "period": p.period, "clock": _clock_str(p.clock),
        "wallClock": as_iso(r.slot.start + timedelta(seconds=p.wall)), "teamId": team.id, "team": team.school, "down": p.down,
        "distance": p.distance, "yardsToGoal": p.ytg, "yardsGained": p.gained, "playTypeId": PLAY_TYPE_IDS.get(p.ptype, 0), "playType": p.ptype,
        "epa": round(p.ppa, 3) if p.ppa is not None else None, "garbageTime": False, "success": _feed_success(p),
        "rushPass": "rush" if S.is_rush(p) else "pass" if S.is_pass(p) else "other", "downType": p.d.get("down_type", "standard"),
        "playText": play_text(p, world.who, abbr, school),
    }


def _team_live(world: World, r: Record, side: int, plays: list[Play], drives: list[dict], period: int, empty: bool = False) -> dict[str, Any]:
    league = world.league
    t = league.by_id[r.slot.home if side == 0 else r.slot.away]
    shell = {"teamId": t.id, "team": t.school, "homeAway": "home" if side == 0 else "away"}
    keys = ("lineScores", "points", "drives", "scoringOpportunities", "pointsPerOpportunity", "averageStartYardLine", "plays", "lineYards",
            "lineYardsPerRush", "secondLevelYards", "secondLevelYardsPerRush", "openFieldYards", "openFieldYardsPerRush", "epaPerPlay",
            "totalEpa", "passingEpa", "epaPerPass", "rushingEpa", "epaPerRush", "successRate", "standardDownSuccessRate",
            "passingDownSuccessRate", "explosiveness", "deserveToWin")
    if empty:
        return {**shell, **{k: None for k in keys}, "points": 0, "lineScores": []}
    lines = [0] * max(4, period)
    score = 0
    for p in plays:
        after = p.home_after if side == 0 else p.away_after
        if after != score:
            lines[min(p.period, len(lines)) - 1] += after - score
            score = after
    lines = lines[:max(1, period)]
    own = [p for p in plays if p.side == side and (S.is_rush(p) or S.is_pass(p))]
    rush = [p for p in own if S.is_rush(p)]
    pas = [p for p in own if S.is_pass(p)]
    my_drives = [d for d in drives if d["offenseId"] == t.id]
    opps = [d for d in my_drives if d.get("scoringOpportunity")]
    epa = lambda rows: sum(p.ppa or 0 for p in rows)  # noqa: E731
    line = sum(S.line_yards(p.gained) for p in rush)
    second = sum(S.second_level(p.gained) for p in rush)
    openf = sum(S.open_field(p.gained) for p in rush)
    std = [p for p in own if p.d.get("down_type") != "passing"]
    pdn = [p for p in own if p.d.get("down_type") == "passing"]
    succ = [p for p in own if p.success]
    my_wp = plays[-1].wp if side == 0 else 1 - plays[-1].wp
    return {
        **shell, "lineScores": lines, "points": score, "drives": len(my_drives), "scoringOpportunities": len(opps),
        "pointsPerOpportunity": round(sum(d.get("pointsGained") or 0 for d in opps) / len(opps), 1) if opps else 0,
        "averageStartYardLine": round(sum(100 - d["startYardsToGoal"] for d in my_drives) / len(my_drives), 1) if my_drives else 0,
        "plays": len(own), "lineYards": round(line, 1), "lineYardsPerRush": _div(line, len(rush), 1), "secondLevelYards": second,
        "secondLevelYardsPerRush": _div(second, len(rush), 1), "openFieldYards": openf, "openFieldYardsPerRush": _div(openf, len(rush), 1),
        "epaPerPlay": _div(epa(own), len(own)), "totalEpa": round(epa(own), 1), "passingEpa": round(epa(pas), 1), "epaPerPass": _div(epa(pas), len(pas)),
        "rushingEpa": round(epa(rush), 1), "epaPerRush": _div(epa(rush), len(rush)), "successRate": _div(len(succ), len(own)),
        "standardDownSuccessRate": _div(sum(1 for p in std if p.success), len(std)),
        "passingDownSuccessRate": _div(sum(1 for p in pdn if p.success), len(pdn)),
        "explosiveness": _div(sum(p.ppa or 0 for p in succ), len(succ)), "deserveToWin": round(0.5 + (my_wp - 0.5) * 0.6, 3),
    }


def r_live_plays(world: World, params: Params, now: datetime) -> dict | None:
    gid = p_int(params, "gameId")
    for data in world.seasons.values():
        r = data.by_id.get(gid) if gid else None
        if r is not None:
            return live_document(world, r, now)
    return None


def r_scoreboard(world: World, params: Params, now: datetime) -> list[dict]:
    """The games of the current week (or the coming one between weeks), as the scoreboard shows them."""
    league = world.league
    data = world.seasons[world.season]
    cls = (p_str(params, "classification") or "fbs").lower()
    conf = p_str(params, "conference")
    shown = [r for r in data.records if r.slot.announce is None or r.slot.announce <= now]
    upcoming = sorted((r for r in shown if r.end > now - timedelta(hours=30)), key=lambda r: r.slot.start)
    if not upcoming:
        return []
    anchor = upcoming[0].slot
    week_games = [r for r in shown if r.slot.week == anchor.week and r.slot.season_type == anchor.season_type]
    out = []
    for r in sorted(week_games, key=lambda r: (r.slot.start, r.id)):
        h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
        if cls == "fbs" and not (h.is_fbs or a.is_fbs):
            continue
        if conf and not (same(h.conference, conf) or same(a.conference, conf)):
            continue
        out.append(scoreboard_entry(world, r, now))
    return out


def scoreboard_entry(world: World, r: Record, now: datetime) -> dict[str, Any]:
    league = world.league
    h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
    status = "completed" if r.end <= now else "in_progress" if r.slot.start <= now else "scheduled"
    period = clock = situation = possession = last_play = None
    home_pts = away_pts = None
    home_lines = away_lines = None
    home_wp = None
    if status != "scheduled":
        result = world.simulate(r.id)
        count = _visible_count(r, result, now)
        plays = result.plays if count is None else result.plays[:count]
        if plays:
            last = plays[-1]
            home_pts, away_pts = last.home_after, last.away_after
            home_wp = round(last.wp, 3)
            doc = live_document(world, r, now) if status == "in_progress" else None
            if doc:
                period = doc["period"]
                clock = doc["clock"]
                poss_team = doc["possession"]
                possession = "home" if poss_team == h.school else "away" if poss_team else None
                if doc["down"]:
                    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(doc["down"], f"{doc['down']}th")
                    situation = f"{ordinal} & {doc['distance']} at {doc['yardsToGoal']}"
                last_play = play_text(last, world.who, (h.abbr, a.abbr), (h.school, a.school))
                lines = [t["lineScores"] for t in doc["teams"]]
                home_lines, away_lines = lines[0], lines[1]
            else:
                home_lines, away_lines = list(r.home_lines), list(r.away_lines)
                home_wp = 1.0 if r.home_points > r.away_points else 0.0
    w = weather_for(r)
    lines = lines_for(world, r)[0] if (h.is_fbs and a.is_fbs) else None
    return {
        "id": r.id, "startDate": as_iso(r.slot.start), "startTimeTBD": False, "tv": r.slot.outlet, "neutralSite": r.slot.neutral,
        "conferenceGame": r.slot.conference_game, "status": status, "period": period, "clock": clock, "situation": situation,
        "possession": possession, "lastPlay": last_play,
        "venue": {"name": r.slot.venue.name, "city": r.slot.venue.city, "state": r.slot.venue.state},
        "homeTeam": {"id": h.id, "name": f"{h.school} {h.mascot}", "conference": h.conference, "classification": h.classification,
                     "points": home_pts, "lineScores": home_lines, "winProbability": home_wp},
        "awayTeam": {"id": a.id, "name": f"{a.school} {a.mascot}", "conference": a.conference, "classification": a.classification,
                     "points": away_pts, "lineScores": away_lines, "winProbability": None if home_wp is None else round(1 - home_wp, 3)},
        "weather": {"temperature": w["temperature"], "description": w["description"], "windSpeed": w["windSpeed"], "windDirection": w["windDirection"]},
        "betting": {"spread": lines["spread"] if lines else None, "overUnder": lines["overUnder"] if lines else None,
                    "homeMoneyline": lines["homeMoneyline"] if lines else None, "awayMoneyline": lines["awayMoneyline"] if lines else None},
    }
