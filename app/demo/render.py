"""CFBD-shaped answers from the made-up league.

Each `r_*` function takes the World, the request's query parameters (strings, as they arrive) and
the moment it is asked (`now`), and returns the JSON payload. Shapes follow the recorded CFBD
answers field for field (`tests/fixtures/league/shapes.json` checks them); values come from the
simulated seasons. What `now` hides: scores and box scores of games not yet final, polls not yet
released, season numbers from games not yet played.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.demo import names as N
from app.demo import stats as S
from app.demo.league import Player, Team, as_iso, first_saturday, saturday, week_window
from app.demo.season import COMMITTEE, POLL_VOTERS, POLLS, Record, World, _strength
from app.demo.sim import GameResult, Play, expected_points, fg_probability, normal_cdf
from app.demo.text import play_text

Params = dict[str, str]


# -- parameter helpers ---------------------------------------------------------------------
def p_int(params: Params, key: str) -> int | None:
    value = params.get(key)
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def p_str(params: Params, key: str) -> str | None:
    value = params.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def same(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and a.strip().lower() == b.strip().lower()


def r1(x: float, n: int = 1) -> float:
    return round(x, n)


def season_types(params: Params, default: str = "both") -> set[str]:
    kind = (p_str(params, "seasonType") or default).lower()
    if kind == "both":
        return {"regular", "postseason"}
    return {kind}


def team_matches(world: World, record: Record, params: Params) -> bool:
    team = p_str(params, "team")
    if team is None:
        return True
    league = world.league
    return any(same(league.by_id[t].school, team) for t in (record.slot.home, record.slot.away))


def conf_matches(world: World, record: Record, params: Params) -> bool:
    conf = p_str(params, "conference")
    if conf is None:
        return True
    league = world.league
    return any(same(league.by_id[t].conference, conf) or same(league.by_id[t].conf_short, conf) for t in (record.slot.home, record.slot.away))


def class_matches(world: World, record: Record, params: Params) -> bool:
    cls = p_str(params, "classification")
    if cls is None:
        return True
    league = world.league
    return any(league.by_id[t].classification == cls.lower() for t in (record.slot.home, record.slot.away))


def select_games(world: World, params: Params, now: datetime, *, default_type: str = "both") -> list[Record]:
    year = p_int(params, "year") or world.season
    data = world.seasons.get(year)
    if data is None:
        return []
    gid = p_int(params, "id") or p_int(params, "gameId")
    if gid is not None:
        r = data.by_id.get(gid)
        return [r] if r and (r.slot.announce is None or r.slot.announce <= now) else []
    week = p_int(params, "week")
    types = season_types(params, default_type)
    out = []
    for r in sorted(data.records, key=lambda r: (r.slot.start, r.id)):
        s = r.slot
        if s.announce is not None and s.announce > now:
            continue
        if s.season_type not in types or (week is not None and s.week != week):
            continue
        if team_matches(world, r, params) and conf_matches(world, r, params) and class_matches(world, r, params):
            out.append(r)
    return out


def team_by(world: World, name: str | None) -> Team | None:
    if not name:
        return None
    league = world.league
    t = league.by_school.get(name)
    if t:
        return t
    lowered = name.strip().lower()
    return next((x for x in league.teams if x.school.lower() == lowered), None)


# -- reference data ------------------------------------------------------------------------
def r_calendar(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    rows = []
    for week in range(1, 16):
        start, end = week_window(year, week)
        rows.append(_cal(year, week, "regular", start, end))
    start, end = week_window(year, 1, "postseason")
    rows.append(_cal(year, 1, "postseason", start, end))
    return rows


def _cal(year: int, week: int, kind: str, start: datetime, end: datetime) -> dict:
    return {"season": year, "week": week, "seasonType": kind, "startDate": as_iso(start), "endDate": as_iso(end),
            "firstGameStart": as_iso(start), "lastGameStart": as_iso(end)}


def team_row(team: Team) -> dict[str, Any]:
    v = team.venue
    return {
        "id": team.id, "school": team.school, "mascot": team.mascot, "abbreviation": team.abbr,
        "alternateNames": [team.abbr, team.school], "conference": team.conference, "division": None,
        "classification": team.classification, "color": team.color, "alternateColor": team.alt_color,
        "logos": [f"https://cdn.collegefootballdata.com/logos/500/{team.id}.png", f"https://cdn.collegefootballdata.com/logos-dark/500/{team.id}.png"],
        "twitter": team.twitter,
        "location": {
            "id": v.id, "name": v.name, "city": v.city, "state": v.state, "zip": v.zip, "countryCode": "US", "timezone": v.timezone,
            "latitude": v.latitude, "longitude": v.longitude, "elevation": f"{v.elevation:.6f}", "capacity": v.capacity,
            "constructionYear": v.construction_year, "grass": v.grass, "dome": v.dome,
        },
    }


def r_teams_fbs(world: World, params: Params, now: datetime) -> list[dict]:
    return [team_row(t) for t in sorted(world.league.fbs, key=lambda t: t.school)]


def r_teams(world: World, params: Params, now: datetime) -> list[dict]:
    conf = p_str(params, "conference")
    teams = [t for t in world.league.teams if conf is None or same(t.conference, conf) or same(t.conf_short, conf)]
    return [team_row(t) for t in sorted(teams, key=lambda t: t.school)]


def r_venues(world: World, params: Params, now: datetime) -> list[dict]:
    return [{
        "id": v.id, "name": v.name, "capacity": v.capacity, "grass": v.grass, "dome": v.dome, "city": v.city, "state": v.state,
        "zip": v.zip, "countryCode": "US", "timezone": v.timezone, "latitude": v.latitude, "longitude": v.longitude,
        "elevation": f"{v.elevation:.6f}", "constructionYear": v.construction_year,
    } for v in sorted(world.league.venues, key=lambda v: v.name)]


def r_coaches(world: World, params: Params, now: datetime) -> list[dict]:
    team = team_by(world, p_str(params, "team"))
    year = p_int(params, "year")
    teams = [team] if team else world.league.fbs
    out = []
    for t in teams:
        c = t.coach
        if c is None:
            continue
        seasons = []
        for y in range(c.hire_year, world.season + 1):
            if year is not None and y != year:
                continue
            if y in world.seasons:
                records = [r for r in world.final(y, now) if t.id in (r.slot.home, r.slot.away)]
                wins = sum(1 for r in records if (r.home_points > r.away_points) == (r.slot.home == t.id))
                losses = len(records) - wins
                strength = _strength(world, y, len(world.final(y, now)))[t.id]
                sp = (r1(29 + 0.9 * strength["offense"] - 26 - 0.9 * strength["defense"] - 3 + strength["special"]),
                      r1(29 + 0.9 * strength["offense"]), r1(26 + 0.9 * strength["defense"]))
            else:
                wins, losses = c.history.get(y, (6, 6))
                sp = (None, None, None)
            games = wins + losses
            seasons.append({
                "teamId": t.id, "school": t.school, "conference": t.conference, "year": y, "games": games, "wins": wins, "losses": losses,
                "ties": 0, "winPercentage": r1(wins / games, 3) if games else None, "preseasonRank": None, "postseasonRank": None,
                "srs": None, "spOverall": sp[0], "spOffense": sp[1], "spDefense": sp[2],
            })
        out.append({"id": c.id, "firstName": c.first, "lastName": c.last,
                    "hireDate": f"{c.hire_year - (1 if c.hire_month >= 11 else 0)}-{c.hire_month:02d}-{(c.id % 27) + 1:02d}T00:00:00.000Z",
                    "seasons": seasons})
    return out


# -- games ---------------------------------------------------------------------------------
def game_row(world: World, r: Record, now: datetime) -> dict[str, Any]:
    league = world.league
    s = r.slot
    h, a = league.by_id[s.home], league.by_id[s.away]
    final = r.end <= now
    tbd = s.start - now > timedelta(days=13) and s.season_type == "regular"
    start = s.start if not tbd else datetime.combine(s.start.date(), datetime.min.time(), timezone.utc) + timedelta(hours=4 if s.start.month < 11 else 5)
    return {
        "id": s.id, "season": s.season, "week": s.week, "seasonType": s.season_type, "startDate": as_iso(start), "startTimeTBD": tbd,
        "completed": final, "neutralSite": s.neutral, "conferenceGame": s.conference_game, "attendance": r.attendance if final else None,
        "venueId": s.venue.id, "venue": s.venue.name,
        "homeId": h.id, "homeTeam": h.school, "homeClassification": h.classification, "homeConference": h.conference,
        "homePoints": r.home_points if final else None, "homeLineScores": list(r.home_lines) if final else None,
        "homePostgameWinProbability": _post_wp(r) if final else None, "homePregameElo": r.home_pre_elo if h.is_fbs else None,
        "homePostgameElo": r.home_post_elo if final and h.is_fbs else None,
        "awayId": a.id, "awayTeam": a.school, "awayClassification": a.classification, "awayConference": a.conference,
        "awayPoints": r.away_points if final else None, "awayLineScores": list(r.away_lines) if final else None,
        "awayPostgameWinProbability": (1 - _post_wp(r)) if final else None, "awayPregameElo": r.away_pre_elo if a.is_fbs else None,
        "awayPostgameElo": r.away_post_elo if final and a.is_fbs else None,
        "excitementIndex": r.excitement if final else None, "highlights": "", "notes": s.notes, "playoff": s.playoff,
    }


def _post_wp(r: Record) -> float:
    """CFBD's postgame win probability: how likely the winner was to win given how it played."""
    margin = r.home_points - r.away_points
    return round(normal_cdf((margin + 0.3 * r.home_expected) / 11.0), 6)


def r_games(world: World, params: Params, now: datetime) -> list[dict]:
    return [game_row(world, r, now) for r in select_games(world, params, now)]


def r_games_teams(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    league = world.league
    for r in select_games(world, params, now):
        if r.end > now:
            continue
        teams = []
        for side, tid in ((0, r.slot.home), (1, r.slot.away)):
            t = league.by_id[tid]
            teams.append({"teamId": t.id, "team": t.school, "conference": t.conference, "homeAway": "home" if side == 0 else "away",
                          "points": r.home_points if side == 0 else r.away_points, "stats": S.team_box_stats(r.counts[side])})
        out.append({"id": r.id, "teams": teams})
    return out


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}"


def player_categories(world: World, lines: dict[int, Counter], year: int) -> list[dict]:
    def athletes(keyfn, rows) -> list[dict]:
        return [{"id": str(pid), "name": _name(world, pid), "stat": keyfn(c)} for pid, c in rows]

    def section(name: str, pred, types: list[tuple[str, Any]], order) -> dict | None:
        rows = sorted(((pid, c) for pid, c in lines.items() if pred(c)), key=order)
        if not rows:
            return None
        return {"name": name, "types": [{"name": tname, "athletes": athletes(fn, rows)} for tname, fn in types]}

    sections = [
        section("passing", lambda c: c["pass_att"] > 0, [
            ("C/ATT", lambda c: f"{c['pass_comp']}/{c['pass_att']}"), ("YDS", lambda c: str(c["pass_yds"])),
            ("AVG", lambda c: _fmt(c["pass_yds"] / c["pass_att"])), ("TD", lambda c: str(c["pass_td"])), ("INT", lambda c: str(c["int_thrown"])),
            ("QBR", lambda c: _fmt(max(0.0, min(99.9, 50 + 6 * (c["pass_yds"] / c["pass_att"] - 7) + 6 * c["pass_td"] - 12 * c["int_thrown"])))),
        ], lambda x: -x[1]["pass_att"]),
        section("rushing", lambda c: c["rush_car"] > 0, [
            ("CAR", lambda c: str(c["rush_car"])), ("YDS", lambda c: str(c["rush_yds"])), ("AVG", lambda c: _fmt(c["rush_yds"] / c["rush_car"])),
            ("TD", lambda c: str(c["rush_td"])), ("LONG", lambda c: str(c["rush_long"])),
        ], lambda x: -x[1]["rush_yds"]),
        section("receiving", lambda c: c["rec"] > 0, [
            ("REC", lambda c: str(c["rec"])), ("YDS", lambda c: str(c["rec_yds"])), ("AVG", lambda c: _fmt(c["rec_yds"] / c["rec"])),
            ("TD", lambda c: str(c["rec_td"])), ("LONG", lambda c: str(c["rec_long"])),
        ], lambda x: -x[1]["rec_yds"]),
        section("fumbles", lambda c: c["fum"] > 0 or c["fum_rec"] > 0, [
            ("FUM", lambda c: str(c["fum"])), ("LOST", lambda c: str(c["fum_lost"])), ("REC", lambda c: str(c["fum_rec"])),
        ], lambda x: -x[1]["fum"]),
        section("defensive", lambda c: c["tot"] > 0 or c["pd"] > 0 or c["qb_hur"] > 0, [
            ("TOT", lambda c: str(c["tot"])), ("SOLO", lambda c: str(c["solo"])), ("SACKS", lambda c: _num(c["sacks"])),
            ("TFL", lambda c: _num(c["tfl"])), ("PD", lambda c: str(c["pd"])), ("QB HUR", lambda c: str(c["qb_hur"])), ("TD", lambda c: str(c["def_td"])),
        ], lambda x: -x[1]["tot"]),
        section("interceptions", lambda c: c["ints"] > 0, [
            ("INT", lambda c: str(c["ints"])), ("YDS", lambda c: str(c["int_yds"])), ("TD", lambda c: str(c["int_td"])),
        ], lambda x: -x[1]["ints"]),
        section("kickReturns", lambda c: c["kr_no"] > 0, [
            ("NO", lambda c: str(c["kr_no"])), ("YDS", lambda c: str(c["kr_yds"])), ("AVG", lambda c: _fmt(c["kr_yds"] / c["kr_no"])),
            ("LONG", lambda c: str(c["kr_long"])), ("TD", lambda c: str(c["kr_td"])),
        ], lambda x: -x[1]["kr_no"]),
        section("puntReturns", lambda c: c["pr_no"] > 0, [
            ("NO", lambda c: str(c["pr_no"])), ("YDS", lambda c: str(c["pr_yds"])), ("AVG", lambda c: _fmt(c["pr_yds"] / c["pr_no"])),
            ("LONG", lambda c: str(c["pr_long"])), ("TD", lambda c: str(c["pr_td"])),
        ], lambda x: -x[1]["pr_no"]),
        section("kicking", lambda c: c["fga"] > 0 or c["xpa"] > 0, [
            ("FG", lambda c: f"{c['fgm']}/{c['fga']}"), ("PCT", lambda c: _fmt(100 * c["fgm"] / c["fga"] if c["fga"] else 0)),
            ("LONG", lambda c: str(c["fg_long"])), ("XP", lambda c: f"{c['xpm']}/{c['xpa']}"), ("PTS", lambda c: str(3 * c["fgm"] + c["xpm"])),
        ], lambda x: -x[1]["fga"]),
        section("punting", lambda c: c["punts"] > 0, [
            ("NO", lambda c: str(c["punts"])), ("YDS", lambda c: str(c["punt_yds"])), ("AVG", lambda c: _fmt(c["punt_yds"] / c["punts"])),
            ("TB", lambda c: str(c["punt_tb"])), ("In 20", lambda c: str(c["punt_in20"])), ("LONG", lambda c: str(c["punt_long"])),
        ], lambda x: -x[1]["punts"]),
    ]
    return [s for s in sections if s]


def _num(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.1f}"


def _name(world: World, pid: int) -> str:
    p = world.league.players.get(str(pid))
    return p.name if p else "Team"


def r_games_players(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    league = world.league
    for r in select_games(world, params, now):
        if r.end > now:
            continue
        teams = []
        for side, tid in ((0, r.slot.home), (1, r.slot.away)):
            t = league.by_id[tid]
            teams.append({"team": t.school, "conference": t.conference, "homeAway": "home" if side == 0 else "away",
                          "points": r.home_points if side == 0 else r.away_points,
                          "categories": player_categories(world, r.lines[side], r.slot.season)})
        out.append({"id": r.id, "teams": teams})
    return out


def r_games_media(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    league = world.league
    for r in select_games(world, params, now):
        s = r.slot
        h, a = league.by_id[s.home], league.by_id[s.away]
        outlet = s.outlet or N.NETWORKS[0]
        out.append({
            "id": s.id, "season": s.season, "week": s.week, "seasonType": s.season_type, "startTime": as_iso(s.start),
            "isStartTimeTBD": False, "homeTeam": h.school, "homeConference": h.conference, "awayTeam": a.school,
            "awayConference": a.conference, "mediaType": "web" if outlet in N.STREAMING else "tv", "outlet": outlet,
        })
    return out


def weather_for(r: Record) -> dict[str, Any]:
    rng = random.Random(r.id * 3)
    v = r.slot.venue
    month = r.slot.start.month
    base = {8: 86, 9: 80, 10: 68, 11: 56, 12: 48, 1: 45}.get(month, 70) - (v.latitude - 33) * 1.4
    temp = round(base + rng.gauss(0, 5), 1)
    code = rng.choices([0, 1, 2, 3, 7, 8], weights=[45, 20, 15, 10, 7, 3])[0]
    return {
        "temperature": temp, "dewPoint": round(temp - rng.uniform(8, 30), 1), "humidity": rng.randint(25, 90),
        "precipitation": 0 if code < 7 else round(rng.uniform(0.01, 0.3), 2), "snowfall": 0, "windDirection": rng.randint(0, 359),
        "windSpeed": round(abs(rng.gauss(8, 4)), 1), "pressure": round(rng.uniform(1005, 1025), 1), "weatherConditionCode": code,
        "description": {0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Cloudy", 7: "Light Rain", 8: "Rain"}[code],
        "indoors": v.dome,
    }


def r_games_weather(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    league = world.league
    for r in select_games(world, params, now):
        s = r.slot
        if s.start - now > timedelta(days=10):
            continue
        h, a = league.by_id[s.home], league.by_id[s.away]
        w = weather_for(r)
        out.append({
            "id": s.id, "season": s.season, "week": s.week, "seasonType": s.season_type, "startTime": as_iso(s.start),
            "gameIndoors": w["indoors"], "homeTeam": h.school, "homeConference": h.conference, "awayTeam": a.school,
            "awayConference": a.conference, "venueId": s.venue.id, "venue": s.venue.name, "temperature": w["temperature"],
            "dewPoint": w["dewPoint"], "humidity": w["humidity"], "precipitation": w["precipitation"], "snowfall": w["snowfall"],
            "windDirection": w["windDirection"], "windSpeed": w["windSpeed"], "pressure": w["pressure"],
            "weatherConditionCode": w["weatherConditionCode"], "weatherCondition": None,
        })
    return out


def moneyline(p: float) -> int:
    p = max(0.02, min(0.98, p))
    if p >= 0.5:
        return -int(round(100 * p / (1 - p) / 5) * 5)
    return int(round(100 * (1 - p) / p / 5) * 5)


def lines_for(world: World, r: Record) -> list[dict]:
    league = world.league
    h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
    data = world.seasons[r.slot.season]
    ho, hd, _ = data.strength[h.id]
    ao, ad, _ = data.strength[a.id]
    total = 56 + 0.8 * (ho + ao + hd + ad)
    out = []
    for i, provider in enumerate(N.PROVIDERS):
        rng = random.Random(r.id * 11 + i)
        spread = r.spread + rng.choice((0, 0, 0.5, -0.5))
        favorite = h.school if spread < 0 else a.school
        fmt = f"{favorite} -{abs(spread):g}" if i == 0 else f"{favorite} -{abs(spread):.1f}"
        wp = normal_cdf(-spread / 14.0)
        out.append({
            "provider": provider, "spread": spread, "formattedSpread": fmt, "spreadOpen": spread + rng.choice((0, 0.5, -0.5, 1, -1)),
            "overUnder": round(total * 2) / 2, "overUnderOpen": round((total + rng.uniform(-3, 3)) * 2) / 2,
            "homeMoneyline": moneyline(wp), "awayMoneyline": moneyline(1 - wp),
        })
    return out


def r_lines(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    league = world.league
    for r in select_games(world, params, now):
        s = r.slot
        h, a = league.by_id[s.home], league.by_id[s.away]
        if not (h.is_fbs and a.is_fbs) or s.start - now > timedelta(days=12):
            continue
        final = r.end <= now
        out.append({
            "id": s.id, "season": s.season, "seasonType": s.season_type, "week": s.week, "startDate": as_iso(s.start),
            "homeTeamId": h.id, "homeTeam": h.school, "homeConference": h.conference, "homeClassification": h.classification,
            "homeScore": r.home_points if final else None, "awayTeamId": a.id, "awayTeam": a.school, "awayConference": a.conference,
            "awayClassification": a.classification, "awayScore": r.away_points if final else None, "lines": lines_for(world, r),
        })
    return out


def r_records(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    data = world.seasons.get(year)
    if data is None:
        return []
    final = world.final(year, now)
    table = world.standings(data, final)
    team = p_str(params, "team")
    conf = p_str(params, "conference")
    out = []
    for t in sorted(world.league.fbs, key=lambda t: t.school):
        if team and not same(t.school, team):
            continue
        if conf and not (same(t.conference, conf) or same(t.conf_short, conf)):
            continue
        row = table[t.id]

        def bucket(name: str, row=row) -> dict:
            c = row[name]
            return {"games": c["games"], "wins": c["wins"], "losses": c["losses"], "ties": 0}

        out.append({
            "year": year, "teamId": t.id, "team": t.school, "classification": "fbs", "conference": t.conference, "division": "",
            "expectedWins": row["_"]["expected"], "total": bucket("total"), "conferenceGames": bucket("conferenceGames"),
            "homeGames": bucket("homeGames"), "awayGames": bucket("awayGames"), "neutralSiteGames": bucket("neutralSiteGames"),
            "regularSeason": bucket("regularSeason"), "postseason": bucket("postseason"),
        })
    return out


# -- polls and ratings -----------------------------------------------------------------------
# CFBD files a poll under the week it comes before: the polls of the Sunday after the conference title
# games (the committee's selection-day ranking among them) are regular week 16.
SELECTION_WEEK = 16


def poll_release(year: int, week: int, kind: str, poll: str) -> datetime:
    if kind == "postseason":
        return datetime(year + 1, 1, 21, 15, tzinfo=timezone.utc)
    if poll == COMMITTEE and week == SELECTION_WEEK:  # selection day, the Sunday after the conference title games
        return datetime.combine(saturday(year, 15), datetime.min.time(), timezone.utc) + timedelta(days=1, hours=17)
    if poll == COMMITTEE:
        return datetime.combine(saturday(year, week) - timedelta(days=4), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    if week == 1:
        return datetime(year, 8, 11, 16, tzinfo=timezone.utc)
    hour = 17 if poll == "Coaches Poll" else 18
    return datetime.combine(saturday(year, week - 1) + timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=hour)


def poll_ranks(world: World, year: int, week: int, kind: str, poll: str) -> list[dict]:
    """The top 25 a poll would publish from the results before it."""
    data = world.seasons[year]
    league = world.league
    if week == SELECTION_WEEK and poll == COMMITTEE:  # the order the field was seeded in
        power = data.__dict__.get("selection_power") or {}
        ranked = sorted(league.fbs, key=lambda t: -power.get(t.id, 0.0))[:25]
        return [{"rank": i, "teamId": t.id, "school": t.school, "conference": t.conference, "firstPlaceVotes": 0, "points": 0}
                for i, t in enumerate(ranked, start=1)]
    if kind == "postseason":
        cutoff = datetime(year + 1, 1, 21, 6, tzinfo=timezone.utc)
    elif week == 1:
        cutoff = datetime(year, 8, 1, tzinfo=timezone.utc)
    else:
        cutoff = datetime.combine(saturday(year, week - 1) + timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=12)
    records = world.final(year, cutoff)
    elo = {t.id: data.elo_start[t.id] for t in league.teams}
    for r in records:
        elo[r.slot.home] = r.home_post_elo
        elo[r.slot.away] = r.away_post_elo
    table = world.standings(data, records)
    rng = random.Random(f"{year}-{week}-{kind}-{poll}")
    score = {}
    for t in league.fbs:
        tot = table[t.id]["total"]
        power = (t.conference in N.POWER_CONFERENCES) * 60
        score[t.id] = elo[t.id] + 30 * tot["wins"] - 85 * tot["losses"] + power + rng.gauss(0, 15) + (data.preseason[t.id] * 6 if week <= 2 else 0)
    ranked = sorted(league.fbs, key=lambda t: -score[t.id])[:25]
    voters = POLL_VOTERS.get(poll, 0)
    rows = []
    remaining = voters
    for i, t in enumerate(ranked, start=1):
        if poll == COMMITTEE:
            fpv, points = 0, 0
        else:
            fpv = 0
            if i == 1:
                fpv = int(voters * rng.uniform(0.5, 0.85))
            elif i <= 4:
                fpv = min(remaining, int(voters * rng.uniform(0, 0.12)))
            remaining = max(0, remaining - fpv)
            points = max(1, voters * (26 - i) - int(rng.uniform(0, voters * 0.8 * min(i, 6))) + fpv)
        rows.append({"rank": i, "teamId": t.id, "school": t.school, "conference": t.conference, "firstPlaceVotes": fpv, "points": points})
    return rows


def r_rankings(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    if year not in world.seasons:
        return []
    week_filter = p_int(params, "week")
    types = season_types(params, "both")  # CFBD answers both unless asked
    out = []
    entries = [("regular", w) for w in range(1, SELECTION_WEEK + 1)] + [("postseason", 1)]
    for kind, week in entries:
        if kind not in types or (week_filter is not None and week != week_filter):
            continue
        polls = []
        names = list(POLLS) + ([COMMITTEE] if kind == "regular" and week >= 10 else [])  # the final poll has no committee
        for poll in names:
            if poll_release(year, week, kind, poll) > now:
                continue
            polls.append({"poll": poll, "isFinal": True if kind == "postseason" else None, "ranks": poll_ranks(world, year, week, kind, poll)})
        if polls:
            out.append({"season": year, "seasonType": kind, "week": week, "polls": polls})
    return out


def _sp_numbers(world: World, year: int, now: datetime) -> dict[int, dict[str, float]]:
    count = len(world.final(year, now))
    raw = _strength(world, year, count)
    out = {}
    for t in world.league.fbs:
        s = raw[t.id]
        off = 29 + 0.9 * s["offense"]
        dfn = 26 + 0.9 * s["defense"]
        st = round(0.6 * s["special"], 1)
        out[t.id] = {"offense": off, "defense": dfn, "special": st, "rating": off - dfn - 3 + st, "games": s["games"]}
    return out


def _rank(values: dict[int, float], reverse: bool = True) -> dict[int, int]:
    ordered = sorted(values, key=lambda k: values[k], reverse=reverse)
    return {k: i + 1 for i, k in enumerate(ordered)}


def r_ratings_sp(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    if year not in world.seasons:
        return []
    sp = _sp_numbers(world, year, now)
    overall = _rank({k: v["rating"] for k, v in sp.items()})
    off_rank = _rank({k: v["offense"] for k, v in sp.items()})
    def_rank = _rank({k: v["defense"] for k, v in sp.items()}, reverse=False)
    team = p_str(params, "team")
    rows = []
    for t in sorted(world.league.fbs, key=lambda t: t.school):
        if team and not same(t.school, team):
            continue
        v = sp[t.id]
        rows.append(_sp_row(year, t.school, t.conference, r1(v["rating"]), overall[t.id], r1(v["offense"]), off_rank[t.id], r1(v["defense"]), def_rank[t.id], v["special"]))
    if not team:
        n = len(sp)
        rows.append(_sp_row(year, "nationalAverages", None, sum(v["rating"] for v in sp.values()) / n, None,
                            sum(v["offense"] for v in sp.values()) / n, None, sum(v["defense"] for v in sp.values()) / n, None,
                            sum(v["special"] for v in sp.values()) / n))
    return rows


def _sp_row(year, team, conference, rating, ranking, off, off_rank, dfn, def_rank, special) -> dict:
    row = {
        "year": year, "team": team, "conference": conference, "rating": rating, "ranking": ranking, "secondOrderWins": None, "sos": None,
        "offense": {"ranking": off_rank, "rating": off, "success": None, "explosiveness": None, "rushing": None, "passing": None,
                    "standardDowns": None, "passingDowns": None, "runRate": None, "pace": None},
        "defense": {"ranking": def_rank, "rating": dfn, "success": None, "explosiveness": None, "rushing": None, "passing": None,
                    "standardDowns": None, "passingDowns": None, "havoc": {"total": None, "frontSeven": None, "db": None}},
        "specialTeams": {"rating": special},
    }
    if conference is None:
        del row["conference"]
    return row


def r_ratings_sp_conferences(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    if year not in world.seasons:
        return []
    sp = _sp_numbers(world, year, now)
    by_conf: dict[str, list[dict]] = defaultdict(list)
    for t in world.league.fbs:
        by_conf[t.conference].append(sp[t.id])
    out = []
    for conf in sorted(by_conf):
        vals = by_conf[conf]
        n = len(vals)
        out.append({
            "year": year, "conference": conf, "rating": sum(v["rating"] for v in vals) / n, "secondOrderWins": None, "sos": None,
            "offense": {"rating": sum(v["offense"] for v in vals) / n, "success": None, "explosiveness": None, "rushing": None, "passing": None,
                        "standardDowns": None, "passingDowns": None, "runRate": None, "pace": None},
            "defense": {"rating": sum(v["defense"] for v in vals) / n, "success": None, "explosiveness": None, "rushing": None, "passing": None,
                        "standardDowns": None, "passingDowns": None, "havoc": {"total": None, "frontSeven": None, "db": None}},
            "specialTeams": {"rating": sum(v["special"] for v in vals) / n},
        })
    return out


def current_elo(world: World, year: int, now: datetime) -> dict[int, int]:
    data = world.seasons[year]
    elo = {t.id: round(data.elo_start[t.id]) for t in world.league.teams}
    for r in world.final(year, now):
        elo[r.slot.home] = r.home_post_elo
        elo[r.slot.away] = r.away_post_elo
    return elo


def r_ratings_elo(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    if year not in world.seasons:
        return []
    elo = current_elo(world, year, now)
    team = p_str(params, "team")
    return [{"year": year, "team": t.school, "conference": t.conference, "elo": elo[t.id]}
            for t in sorted(world.league.fbs, key=lambda t: t.school) if not team or same(t.school, team)]


def r_ratings_fpi(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    if year not in world.seasons:
        return []
    sp = _sp_numbers(world, year, now)
    rng = random.Random(year * 5)
    fpi = {k: v["rating"] * 1.05 + rng.gauss(0, 2.0) for k, v in sp.items()}
    data = world.seasons[year]
    final = world.final(year, now)
    table = world.standings(data, final)
    sor = {t.id: table[t.id]["total"]["wins"] * 2 - table[t.id]["total"]["losses"] * 2 + fpi[t.id] * 0.1 for t in world.league.fbs}
    sched: dict[int, list[float]] = defaultdict(list)
    remaining: dict[int, list[float]] = defaultdict(list)
    for r in data.records:
        if r.slot.season_type != "regular":
            continue
        for tid, opp in ((r.slot.home, r.slot.away), (r.slot.away, r.slot.home)):
            (sched if r.end <= now else remaining)[tid].append(fpi.get(opp, -20))
    sos = {t.id: sum(sched[t.id] + remaining[t.id]) / max(1, len(sched[t.id] + remaining[t.id])) for t in world.league.fbs}
    rsos = {t.id: sum(remaining[t.id]) / max(1, len(remaining[t.id])) for t in world.league.fbs}
    ranks = {"fpi": _rank(fpi), "strengthOfRecord": _rank(sor), "averageWinProbability": _rank({k: v + rng.gauss(0, 1) for k, v in fpi.items()}),
             "strengthOfSchedule": _rank(sos), "remainingStrengthOfSchedule": _rank(rsos), "gameControl": _rank({k: v + rng.gauss(0, 3) for k, v in fpi.items()})}
    out = []
    for t in sorted(world.league.fbs, key=lambda t: -fpi[t.id]):
        v = sp[t.id]
        out.append({
            "year": year, "team": t.school, "conference": t.conference, "fpi": round(fpi[t.id], 3),
            "resumeRanks": {key: ranks[key][t.id] for key in ("strengthOfRecord", "fpi", "averageWinProbability", "strengthOfSchedule", "remainingStrengthOfSchedule", "gameControl")},
            "efficiencies": {"overall": round(max(1, min(99, 50 + 2.2 * v["rating"])), 3), "offense": round(max(1, min(99, 50 + 2.2 * (v["offense"] - 29))), 3),
                             "defense": round(max(1, min(99, 50 - 2.2 * (v["defense"] - 26))), 3), "specialTeams": round(max(1, min(99, 50 + 8 * v["special"])), 3)},
        })
    return out


def r_ratings_srs(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    if year not in world.seasons:
        return []
    final = world.final(year, now)
    if len({r.slot.week for r in final if r.slot.season_type == "regular"}) < 6:
        return []
    league = world.league
    games: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for r in final:
        hfa = 0 if r.slot.neutral else 2.5
        m = max(-24, min(24, r.home_points - r.away_points - hfa))
        games[r.slot.home].append((r.slot.away, m))
        games[r.slot.away].append((r.slot.home, -m))
    # CFBD's SRS covers Division I, FCS teams included (a 2025 answer had 266 rows): every team that played.
    rated = [t for t in league.teams if t.is_fbs or games.get(t.id)]
    rating = {t.id: 0.0 for t in league.teams}
    for _ in range(40):
        new = {}
        for t in rated:
            g = games.get(t.id, [])
            new[t.id] = sum(m + rating[o] for o, m in g) / len(g) if g else 0.0
        mean = sum(new[t.id] for t in rated if t.is_fbs) / max(1, sum(1 for t in rated if t.is_fbs))
        for k, v in new.items():
            rating[k] = v - mean
    ordered = sorted(rated, key=lambda t: -rating[t.id])
    return [{"year": year, "team": t.school, "conference": t.conference, "division": None, "ranking": i + 1, "rating": round(rating[t.id], 1)}
            for i, t in enumerate(ordered)]


def r_ratings_core(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    if year not in world.seasons:
        return []
    final = world.final(year, now)
    sp = _sp_numbers(world, year, now)
    plays: Counter = Counter()
    dplays: Counter = Counter()
    for r in final:
        plays[r.slot.home] += r.advanced[0]["plays"]
        plays[r.slot.away] += r.advanced[1]["plays"]
        dplays[r.slot.home] += r.advanced[1]["plays"]
        dplays[r.slot.away] += r.advanced[0]["plays"]
    weeks = [r.slot.week for r in final if r.slot.season_type == "regular"]
    through = max(weeks) if weeks else 0
    out = []
    for t in sorted(world.league.fbs, key=lambda t: t.school):
        v = sp[t.id]
        out.append({
            "year": year, "throughSeasonType": "regular", "throughWeek": through, "team": t.school, "conference": t.conference,
            "overall": round(v["rating"], 2), "offense": round(v["offense"] - 29, 2), "defense": round(v["defense"] - 26, 2),
            "offensePlays": plays[t.id], "defensePlays": dplays[t.id], "modelVersion": "core-preseason-v1" if through < 5 else "core-v1",
        })
    return out


def team_talent(world: World, team: Team, year: int) -> float:
    league = world.league
    ratings = sorted((league.recruits[p.recruit].rating for p in league.roster(team.id, year) if p.recruit), reverse=True)[:85]
    return round(sum(max(0.0, r - 0.78) for r in ratings) * 78, 2)


def r_talent(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    rows = [{"year": year, "team": t.school, "talent": team_talent(world, t, year)} for t in world.league.fbs]
    rows.sort(key=lambda r: -r["talent"])
    return rows


# -- recruiting, rosters, people -----------------------------------------------------------
def recruit_row(world: World, rc) -> dict[str, Any]:
    league = world.league
    team = league.by_id.get(rc.committed) if rc.committed else None
    return {
        "id": rc.id, "athleteId": rc.athlete, "recruitType": "HighSchool", "year": rc.year, "ranking": rc.ranking, "name": rc.name,
        "school": rc.high_school, "committedTo": team.school if team else None, "position": rc.position, "height": rc.height,
        "weight": rc.weight, "stars": rc.stars, "rating": rc.rating, "city": rc.city, "stateProvince": rc.state, "country": "USA",
        "hometownInfo": {"latitude": rc.latitude, "longitude": rc.longitude, "fipsCode": rc.fips},
    }


def r_recruiting_players(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    team = team_by(world, p_str(params, "team"))
    pos = p_str(params, "position")
    state = p_str(params, "state")
    rows = world.league.recruits_by_year.get(year, [])
    out = []
    for rc in rows:
        if team is not None and rc.committed != team.id:
            continue
        if pos and not same(rc.position, pos):
            continue
        if state and not same(rc.state, state):
            continue
        row = recruit_row(world, rc)
        if year > world.season:
            row["athleteId"] = None
        out.append(row)
    return out


def r_recruiting_teams(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    if year > world.season:
        return []
    by_team: dict[int, list[float]] = defaultdict(list)
    for rc in world.league.recruits_by_year.get(year, []):
        if rc.committed:
            by_team[rc.committed].append(rc.rating)
    points = {tid: sum((r * 100 - 70) * 0.94 ** i for i, r in enumerate(sorted(v, reverse=True))) for tid, v in by_team.items()}
    team = p_str(params, "team")
    ordered = sorted(points, key=lambda k: -points[k])
    out = []
    for i, tid in enumerate(ordered, start=1):
        t = world.league.by_id[tid]
        if team and not same(t.school, team):
            continue
        out.append({"year": year, "team": t.school, "rank": i, "points": round(points[tid], 2)})
    return out


def roster_row(world: World, p: Player, team: Team, year: int) -> dict[str, Any]:
    stint = p.stint_in(year)
    return {
        "id": p.id, "firstName": p.first, "lastName": p.last, "team": team.school, "weight": p.weight, "height": p.height,
        "jersey": stint.jersey if stint else None, "year": max(1, min(4, year - p.enroll + 1)), "position": p.position,
        "homeCity": p.city, "homeState": p.state, "homeCountry": "USA", "homeLatitude": p.latitude, "homeLongitude": p.longitude,
        "homeCountyFIPS": p.fips, "recruitIds": [p.recruit] if p.recruit else [],
    }


def r_roster(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    team = team_by(world, p_str(params, "team"))
    teams = [team] if team else world.league.fbs
    out = []
    for t in teams:
        for p in world.league.roster(t.id, year):
            out.append(roster_row(world, p, t, year))
    return out


def r_player_portal(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    return [{
        "season": tr.season, "firstName": tr.first, "lastName": tr.last, "position": tr.position, "origin": tr.origin,
        "destination": tr.destination, "transferDate": as_iso(tr.date), "rating": tr.rating, "stars": tr.stars, "eligibility": tr.eligibility,
    } for tr in world.league.transfers if tr.season == year]


def r_player_search(world: World, params: Params, now: datetime) -> list[dict]:
    term = (p_str(params, "searchTerm") or "").lower()
    if len(term) < 2:
        return []
    year = p_int(params, "year")
    team = team_by(world, p_str(params, "team"))
    pos = p_str(params, "position")
    league = world.league
    out = []
    for p in sorted(league.players.values(), key=lambda p: (p.first, p.last, p.id)):
        if term not in p.name.lower():
            continue
        stint = p.stint_in(year) if year else (p.stint_in(world.season) or (p.stints[-1] if p.stints else None))
        if stint is None:
            continue
        t = league.by_id[stint.team]
        if team and t.id != team.id:
            continue
        if pos and not same(p.position, pos):
            continue
        out.append({
            "id": p.id, "team": t.school, "name": p.name, "firstName": p.first, "lastName": p.last, "weight": p.weight, "height": p.height,
            "jersey": stint.jersey, "position": p.position, "hometown": p.city, "teamColor": t.color, "teamColorSecondary": t.alt_color,
            "activeStartYear": p.enroll, "activeEndYear": min(p.leave - 1, world.season),
            "teamStints": [{"team": league.by_id[s.team].school, "startYear": s.start, "endYear": min(s.end - 1, world.season)} for s in p.stints],
        })
        if len(out) >= 100:
            break
    return out


# -- season player and team numbers ---------------------------------------------------------
def _season_records(world: World, params: Params, now: datetime) -> list[Record]:
    year = p_int(params, "year") or world.season
    if year not in world.seasons:
        return []
    types = season_types(params, "both")
    start_week = p_int(params, "startWeek")
    end_week = p_int(params, "endWeek")
    out = []
    for r in world.final(year, now):
        if r.slot.season_type not in types:
            continue
        if r.slot.season_type == "regular" and ((start_week and r.slot.week < start_week) or (end_week and r.slot.week > end_week)):
            continue
        out.append(r)
    return out


def _player_season(world: World, records: list[Record]) -> tuple[dict[int, Counter], dict[int, int]]:
    """Summed raw lines per player, and each player's team for the season."""
    totals: dict[int, Counter] = defaultdict(Counter)
    team_of: dict[int, int] = {}
    for r in records:
        for side, tid in ((0, r.slot.home), (1, r.slot.away)):
            for pid, c in r.lines[side].items():
                t = totals[pid]
                for k, v in c.items():
                    if k.endswith("_long"):
                        t[k] = max(t[k], v)
                    else:
                        t[k] += v
                team_of[pid] = tid
    return totals, team_of


def _ppa_season(world: World, records: list[Record]) -> tuple[dict[int, Counter], dict[int, int], dict[int, Counter]]:
    totals: dict[int, Counter] = defaultdict(Counter)
    team_of: dict[int, int] = {}
    base: dict[int, Counter] = defaultdict(Counter)
    for r in records:
        for side, tid in ((0, r.slot.home), (1, r.slot.away)):
            base[tid].update(r.usage[side])
            for pid, c in r.ppa[side].items():
                totals[pid].update(c)
                team_of[pid] = tid
    return totals, team_of, base


STAT_ROWS = {
    "passing": [("ATT", "pass_att"), ("COMPLETIONS", "pass_comp"), ("INT", "int_thrown"), ("PCT", None), ("TD", "pass_td"), ("YDS", "pass_yds"), ("YPA", None)],
    "rushing": [("CAR", "rush_car"), ("LONG", "rush_long"), ("TD", "rush_td"), ("YDS", "rush_yds"), ("YPC", None)],
    "receiving": [("LONG", "rec_long"), ("REC", "rec"), ("TD", "rec_td"), ("YDS", "rec_yds"), ("YPR", None)],
    "defensive": [("PD", "pd"), ("QB HUR", "qb_hur"), ("SACKS", "sacks"), ("SOLO", "solo"), ("TD", "def_td"), ("TFL", "tfl"), ("TOT", "tot")],
    "interceptions": [("AVG", None), ("INT", "ints"), ("TD", "int_td"), ("YDS", "int_yds")],
    "fumbles": [("FUM", "fum"), ("LOST", "fum_lost"), ("REC", "fum_rec")],
    "kickReturns": [("AVG", None), ("LONG", "kr_long"), ("NO", "kr_no"), ("TD", "kr_td"), ("YDS", "kr_yds")],
    "puntReturns": [("AVG", None), ("LONG", "pr_long"), ("NO", "pr_no"), ("TD", "pr_td"), ("YDS", "pr_yds")],
    "kicking": [("FGA", "fga"), ("FGM", "fgm"), ("LONG", "fg_long"), ("PCT", None), ("PTS", None), ("XPA", "xpa"), ("XPM", "xpm")],
    "punting": [("In 20", "punt_in20"), ("LONG", "punt_long"), ("NO", "punts"), ("TB", "punt_tb"), ("YDS", "punt_yds"), ("YPP", None)],
}
CATEGORY_GATE = {"passing": "pass_att", "rushing": "rush_car", "receiving": "rec", "defensive": "tot", "interceptions": "ints",
                 "fumbles": "fum", "kickReturns": "kr_no", "puntReturns": "pr_no", "kicking": "xpa", "punting": "punts"}


def _derived(category: str, stat: str, c: Counter) -> str:
    def ratio(a: float, b: float, digits: int = 1) -> str:
        return f"{(a / b if b else 0):.{digits}f}"

    if category == "passing":
        return ratio(c["pass_comp"], c["pass_att"], 3) if stat == "PCT" else ratio(c["pass_yds"], c["pass_att"])
    if category == "rushing":
        return ratio(c["rush_yds"], c["rush_car"])
    if category == "receiving":
        return ratio(c["rec_yds"], c["rec"])
    if category == "interceptions":
        return ratio(c["int_yds"], c["ints"])
    if category == "kickReturns":
        return ratio(c["kr_yds"], c["kr_no"])
    if category == "puntReturns":
        return ratio(c["pr_yds"], c["pr_no"])
    if category == "kicking":
        return ratio(c["fgm"], c["fga"], 3) if stat == "PCT" else str(3 * c["fgm"] + c["xpm"])
    if category == "punting":
        return ratio(c["punt_yds"], c["punts"])
    return "0"


def r_stats_player_season(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    records = _season_records(world, params, now)
    totals, team_of = _player_season(world, records)
    team = team_by(world, p_str(params, "team"))
    conf = p_str(params, "conference")
    category = p_str(params, "category")
    league = world.league
    out = []
    for pid in sorted(totals, key=lambda k: (team_of[k], k)):
        tid = team_of[pid]
        t = league.by_id[tid]
        if not t.is_fbs or (team and t.id != team.id) or (conf and not (same(t.conference, conf) or same(t.conf_short, conf))):
            continue
        c = totals[pid]
        p = league.players.get(str(pid))
        for cat, rows in STAT_ROWS.items():
            if category and cat != category:
                continue
            gate = CATEGORY_GATE[cat]
            if c[gate] <= 0 and not (cat == "kicking" and c["fga"] > 0) and not (cat == "fumbles" and c["fum_rec"] > 0) and not (cat == "defensive" and c["pd"] > 0):
                continue
            for stat, key in rows:
                value = _derived(cat, stat, c) if key is None else (_num(c[key]) if isinstance(c[key], float) else str(c[key]))
                out.append({"season": year, "playerId": str(pid), "player": p.name if p else "Team", "position": p.position if p else "",
                            "team": t.school, "conference": t.conference, "category": cat, "statType": stat, "stat": value})
    return out


def r_stats_categories(world: World, params: Params, now: datetime) -> list[str]:
    return ['completionAttempts', 'defensiveTDs', 'extraPoints', 'fieldGoalPct', 'fieldGoals', 'firstDowns', 'fourthDownEff', 'fumblesLost',
            'fumblesRecovered', 'interceptions', 'interceptionTDs', 'interceptionYards', 'kickingPoints', 'kickReturns', 'kickReturnTDs',
            'kickReturnYards', 'netPassingYards', 'passesDeflected', 'passesIntercepted', 'passingTDs', 'possessionTime', 'puntReturns',
            'puntReturnTDs', 'puntReturnYards', 'qbHurries', 'rushingAttempts', 'rushingTDs', 'rushingYards', 'sacks', 'tackles',
            'tacklesForLoss', 'thirdDownEff', 'totalFumbles', 'totalPenaltiesYards', 'totalYards', 'turnovers', 'yardsPerPass', 'yardsPerRushAttempt']


def _team_season(world: World, records: list[Record]) -> tuple[dict[int, Counter], dict[int, Counter], dict[int, Counter], dict[int, Counter]]:
    own: dict[int, Counter] = defaultdict(Counter)
    opp: dict[int, Counter] = defaultdict(Counter)
    adv_o: dict[int, Counter] = defaultdict(Counter)
    adv_d: dict[int, Counter] = defaultdict(Counter)
    for r in records:
        for side, tid in ((0, r.slot.home), (1, r.slot.away)):
            own[tid].update(r.counts[side])
            opp[tid].update(r.counts[1 - side])
            adv_o[tid].update(r.advanced[side])
            adv_d[tid].update(r.advanced[1 - side])
    return own, opp, adv_o, adv_d


def _team_filter(world: World, params: Params) -> list[Team]:
    team = team_by(world, p_str(params, "team"))
    conf = p_str(params, "conference")
    return [t for t in sorted(world.league.fbs, key=lambda t: t.school)
            if (team is None or t.id == team.id) and (conf is None or same(t.conference, conf) or same(t.conf_short, conf))]


def r_stats_season(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    records = _season_records(world, params, now)
    own, opp, _, _ = _team_season(world, records)
    out = []
    for t in _team_filter(world, params):
        if own[t.id]["games"] == 0:
            continue
        for name, value in S.season_team_stats(own[t.id], opp[t.id]):
            out.append({"season": year, "team": t.school, "conference": t.conference, "statName": name, "statValue": int(value)})
    return out


def r_stats_season_advanced(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    records = _season_records(world, params, now)
    _, _, adv_o, adv_d = _team_season(world, records)
    out = []
    for t in _team_filter(world, params):
        if adv_o[t.id]["plays"] == 0:
            continue
        defense = S.advanced_block(adv_d[t.id])
        defense["passingDowns"]["totalPPA"] = adv_d[t.id]["passing_ppa"]
        out.append({"season": year, "team": t.school, "conference": t.conference, "offense": S.advanced_block(adv_o[t.id]), "defense": defense})
    return out


def r_ppa_games(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    league = world.league
    team = team_by(world, p_str(params, "team"))
    for r in select_games(world, params, now):
        if r.end > now:
            continue
        for side, tid in ((0, r.slot.home), (1, r.slot.away)):
            t = league.by_id[tid]
            if not t.is_fbs or (team and t.id != team.id):
                continue
            opp = league.by_id[r.slot.away if side == 0 else r.slot.home]
            out.append({"gameId": r.id, "season": r.slot.season, "week": r.slot.week, "seasonType": r.slot.season_type, "team": t.school,
                        "conference": t.conference, "opponent": opp.school, "offense": dict(r.ppa_split[side]), "defense": dict(r.ppa_split[1 - side])})
    return out


def _avg(c: Counter, key: str) -> float | None:
    n = c[f"{key}_n"]
    return round(c[key] / n, 3) if n else None


def r_ppa_players_games(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    league = world.league
    team = team_by(world, p_str(params, "team"))
    for r in select_games(world, params, now):
        if r.end > now:
            continue
        for side, tid in ((0, r.slot.home), (1, r.slot.away)):
            t = league.by_id[tid]
            if team and t.id != team.id:
                continue
            opp = league.by_id[r.slot.away if side == 0 else r.slot.home]
            for pid, c in sorted(r.ppa[side].items(), key=lambda x: -x[1]["all_n"]):
                p = league.players.get(str(pid))
                if p is None or c["all_n"] < 3:
                    continue
                out.append({"season": r.slot.season, "week": r.slot.week, "seasonType": r.slot.season_type, "id": str(pid), "name": p.name,
                            "position": p.position, "team": t.school, "opponent": opp.school,
                            "averagePPA": {"all": _avg(c, "all"), "pass": _avg(c, "pass"), "rush": _avg(c, "rush")}})
    return out


def r_ppa_players_season(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    records = _season_records(world, params, now)
    totals, team_of, _ = _ppa_season(world, records)
    team = team_by(world, p_str(params, "team"))
    conf = p_str(params, "conference")
    pos = p_str(params, "position")
    threshold = p_int(params, "threshold")
    league = world.league
    out = []
    for pid, c in sorted(totals.items(), key=lambda x: -x[1]["all"]):
        t = league.by_id[team_of[pid]]
        p = league.players.get(str(pid))
        if p is None or not t.is_fbs or (team and t.id != team.id) or (conf and not same(t.conference, conf)) or (pos and not same(p.position, pos)):
            continue
        if threshold is not None and c["all_n"] < threshold:
            continue
        if threshold is None and c["all_n"] < 5:
            continue
        keys = [("all", "all"), ("pass", "pass"), ("rush", "rush"), ("firstDown", "first"), ("secondDown", "second"), ("thirdDown", "third"),
                ("standardDowns", "standard"), ("passingDowns", "passing")]
        out.append({
            "season": year, "id": str(pid), "name": p.name, "position": p.position, "team": t.school, "conference": t.conference,
            "averagePPA": {k: (_avg(c, v) if k != "all" else round(c["all"] / c["all_n"], 3)) for k, v in keys},
            "totalPPA": {k: round(c[v], 3) for k, v in keys},
        })
    return out


def r_player_usage(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    records = _season_records(world, params, now)
    totals, team_of, base = _ppa_season(world, records)
    team = team_by(world, p_str(params, "team"))
    conf = p_str(params, "conference")
    pos = p_str(params, "position")
    league = world.league
    out = []
    for pid, c in sorted(totals.items(), key=lambda x: -x[1]["all_n"]):
        t = league.by_id[team_of[pid]]
        p = league.players.get(str(pid))
        if p is None or not t.is_fbs or (team and t.id != team.id) or (conf and not same(t.conference, conf)) or (pos and not same(p.position, pos)):
            continue
        if c["all_n"] < 5:
            continue
        b = base[t.id]

        def share(key: str, base_key: str, c=c, b=b) -> float:
            return round(c[f"{key}_n"] / b[base_key], 3) if b[base_key] else 0

        out.append({"season": year, "id": str(pid), "name": p.name, "position": p.position, "team": t.school, "conference": t.conference,
                    "usage": {"overall": share("all", "all"), "pass": share("pass", "pass"), "rush": share("rush", "rush"),
                              "firstDown": share("first", "first"), "secondDown": share("second", "second"), "thirdDown": share("third", "third"),
                              "standardDowns": share("standard", "standard"), "passingDowns": share("passing", "passing")}})
    return out


def r_player_returning(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    prev = year - 1
    if prev not in world.seasons:
        return []
    records = world.final(prev, datetime(prev + 1, 6, 1, tzinfo=timezone.utc))
    totals, team_of, base = _ppa_season(world, records)
    league = world.league
    by_team: dict[int, Counter] = defaultdict(Counter)
    for pid, c in totals.items():
        tid = team_of[pid]
        p = league.players.get(str(pid))
        stays = p is not None and (s := p.stint_in(year)) is not None and s.team == tid
        pass_ppa = c["pass"] if p is not None and p.position == "QB" else 0.0
        rec_ppa = c["pass"] if p is not None and p.position != "QB" else 0.0
        rush_ppa = c["rush"]
        for k, v in (("total", c["all"]), ("pass", pass_ppa), ("rec", rec_ppa), ("rush", rush_ppa),
                     ("use", c["all_n"]), ("use_pass", c["pass_n"] if p is not None and p.position == "QB" else 0),
                     ("use_rec", c["pass_n"] if p is not None and p.position != "QB" else 0), ("use_rush", c["rush_n"])):
            by_team[tid][k] += abs(v)
            if stays:
                by_team[tid][f"r_{k}"] += abs(v)
    out = []
    for t in _team_filter(world, params):
        c = by_team[t.id]

        def pct(k: str, c=c) -> float:
            return round(c[f"r_{k}"] / c[k], 3) if c[k] else 0

        out.append({"season": year, "team": t.school, "conference": t.conference, "totalPPA": round(c["r_total"], 1),
                    "totalPassingPPA": round(c["r_pass"], 1), "totalReceivingPPA": round(c["r_rec"], 1), "totalRushingPPA": round(c["r_rush"], 1),
                    "percentPPA": pct("total"), "percentPassingPPA": pct("pass"), "percentReceivingPPA": pct("rec"), "percentRushingPPA": pct("rush"),
                    "usage": pct("use"), "passingUsage": pct("use_pass"), "receivingUsage": pct("use_rec"), "rushingUsage": pct("use_rush")})
    return out


def r_ppa_predicted(world: World, params: Params, now: datetime) -> list[dict]:
    down = p_int(params, "down") or 1
    distance = p_int(params, "distance") or 10
    return [{"yardLine": yl, "predictedPoints": round(expected_points(100 - yl, down, distance), 2)} for yl in range(99, 0, -1) if 100 - yl >= distance or down == 1]


def r_metrics_fg_ep(world: World, params: Params, now: datetime) -> list[dict]:
    return [{"yardsToGoal": ytg, "distance": ytg + 17, "expectedPoints": round(3 * fg_probability(ytg + 17), 2)} for ytg in range(0, 100)]


def r_wp_pregame(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    league = world.league
    for r in select_games(world, params, now):
        h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
        if not (h.is_fbs and a.is_fbs) or r.slot.start - now > timedelta(days=12):
            continue
        out.append({"season": r.slot.season, "week": r.slot.week, "seasonType": r.slot.season_type, "gameId": r.id, "homeTeam": h.school,
                    "awayTeam": a.school, "spread": r.spread, "homeWinProbability": r.home_wp_pre})
    return out


def r_talent_placeholder(world: World, params: Params, now: datetime) -> list[dict]:
    return []


def _wepa_ready(world: World, year: int, now: datetime) -> bool:
    final = world.final(year, now)
    return len({r.slot.week for r in final if r.slot.season_type == "regular"}) >= 4


def r_wepa_team(world: World, params: Params, now: datetime) -> list[dict]:
    year = p_int(params, "year") or world.season
    if year not in world.seasons or not _wepa_ready(world, year, now):
        return []
    records = _season_records(world, {"year": str(year)}, now)
    _, _, adv_o, adv_d = _team_season(world, records)
    out = []
    for t in _team_filter(world, params):
        o, d = adv_o[t.id], adv_d[t.id]

        def div(a: float, b: float) -> float:
            return a / b if b else 0.0

        out.append({
            "year": year, "teamId": t.id, "team": t.school, "conference": t.conference,
            "epa": {"total": div(o["ppa"], o["plays"]), "passing": div(o["pass_ppa"], o["pass_n"]), "rushing": div(o["rush_ppa"], o["rush_n"])},
            "epaAllowed": {"total": div(d["ppa"], d["plays"]), "passing": div(d["pass_ppa"], d["pass_n"]), "rushing": div(d["rush_ppa"], d["rush_n"])},
            "successRate": {"total": div(o["succ"], o["plays"]), "standardDowns": div(o["standard_succ"], o["standard_n"]), "passingDowns": div(o["passing_succ"], o["passing_n"])},
            "successRateAllowed": {"total": div(d["succ"], d["plays"]), "standardDowns": div(d["standard_succ"], d["standard_n"]), "passingDowns": div(d["passing_succ"], d["passing_n"])},
            "rushing": {"lineYards": div(o["line_yds"], o["rush_n"]), "secondLevelYards": div(o["second_yds"], o["rush_n"]), "openFieldYards": div(o["open_yds"], o["rush_n"]),
                        "highlightYards": div(o["second_yds"] + o["open_yds"], o["rush_n"])},
            "rushingAllowed": {"lineYards": div(d["line_yds"], d["rush_n"]), "secondLevelYards": div(d["second_yds"], d["rush_n"]), "openFieldYards": div(d["open_yds"], d["rush_n"]),
                               "highlightYards": div(d["second_yds"] + d["open_yds"], d["rush_n"])},
            "explosiveness": div(o["expl"], o["succ"]), "explosivenessAllowed": div(d["expl"], d["succ"]),
        })
    return out


def r_wepa_players(kind: str):
    def handler(world: World, params: Params, now: datetime) -> list[dict]:
        year = p_int(params, "year") or world.season
        if year not in world.seasons:
            return []
        if kind != "kicking" and not _wepa_ready(world, year, now):
            return []
        records = _season_records(world, {"year": str(year)}, now)
        league = world.league
        team = team_by(world, p_str(params, "team"))
        conf = p_str(params, "conference")
        out = []
        if kind == "kicking":
            totals, team_of = _player_season(world, records)
            for pid, c in sorted(totals.items(), key=lambda x: -x[1]["fga"]):
                if c["fga"] < 2:
                    continue
                t = league.by_id[team_of[pid]]
                p = league.players.get(str(pid))
                if p is None or not t.is_fbs or (team and t.id != team.id) or (conf and not same(t.conference, conf)):
                    continue
                paar = (c["fgm"] - 0.8 * c["fga"]) * 3 + random.Random(pid).gauss(0, 0.8)
                out.append({"year": year, "athleteId": str(pid), "athleteName": p.name, "team": t.school, "conference": t.conference,
                            "paar": round(paar, 1), "attempts": c["fga"] + c["xpa"]})
            return out
        totals, team_of, _ = _ppa_season(world, records)
        key = "pass" if kind == "passing" else "rush"
        for pid, c in sorted(totals.items(), key=lambda x: -(x[1][key] / max(1, x[1][f"{key}_n"]))):
            n = c[f"{key}_n"]
            if n < (40 if kind == "passing" else 25):
                continue
            t = league.by_id[team_of[pid]]
            p = league.players.get(str(pid))
            if p is None or not t.is_fbs or (team and t.id != team.id) or (conf and not same(t.conference, conf)):
                continue
            if kind == "passing" and p.position != "QB":
                continue
            out.append({"year": year, "athleteId": str(pid), "athleteName": p.name, "position": p.position, "team": t.school,
                        "conference": t.conference, "wepa": round(c[key] / n * 0.95, 2), "plays": n})
        return out
    return handler


def r_matchup(world: World, params: Params, now: datetime) -> dict:
    a = team_by(world, p_str(params, "team1"))
    b = team_by(world, p_str(params, "team2"))
    if a is None or b is None:
        return {"team1": p_str(params, "team1"), "team2": p_str(params, "team2"), "team1Wins": 0, "team2Wins": 0, "ties": 0, "games": []}
    first, second = sorted((a, b), key=lambda t: t.id)
    rng = random.Random(first.id * 10007 + second.id)
    games = []
    year = 1950 + rng.randint(0, 40)
    edge = (a.prestige - b.prestige) * 0.6
    while year < world.season - 1:
        if rng.random() < 0.55:
            home = a if rng.random() < 0.5 else b
            away = b if home is a else a
            hs = max(0, int(rng.gauss(24, 10)))
            as_ = max(0, int(rng.gauss(24 - 10 * (edge if home is a else -edge), 10)))
            if hs == as_:
                hs += rng.choice((3, 7))
            sat = first_saturday(year) + timedelta(days=7 * rng.randint(3, 11))
            games.append({"season": year, "week": rng.randint(3, 12), "seasonType": "regular", "date": f"{sat.isoformat()}T00:00:00.000Z",
                          "neutralSite": False, "venue": home.venue.name, "homeTeam": home.school, "homeScore": hs, "awayTeam": away.school,
                          "awayScore": as_, "winner": home.school if hs > as_ else away.school})
        year += 1
    for y in sorted(world.seasons):
        for r in world.final(y, now):
            if {r.slot.home, r.slot.away} == {a.id, b.id}:
                home = world.league.by_id[r.slot.home]
                away = world.league.by_id[r.slot.away]
                games.append({"season": y, "week": r.slot.week, "seasonType": r.slot.season_type, "date": as_iso(r.slot.start),
                              "neutralSite": r.slot.neutral, "venue": r.slot.venue.name, "homeTeam": home.school, "homeScore": r.home_points,
                              "awayTeam": away.school, "awayScore": r.away_points,
                              "winner": home.school if r.home_points > r.away_points else away.school})
    wins_a = sum(1 for g in games if g["winner"] == a.school)
    wins_b = sum(1 for g in games if g["winner"] == b.school)
    return {"team1": a.school, "team2": b.school, "team1Wins": wins_a, "team2Wins": wins_b, "ties": 0, "games": games}


# -- play by play ----------------------------------------------------------------------------
def _play_rows(world: World, r: Record, result: GameResult, upto: int | None = None) -> list[dict]:
    """/plays rows for one game (all of it, or its first `upto` plays)."""
    league = world.league
    h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
    abbr = (h.abbr, a.abbr)
    school = (h.school, a.school)
    out = []
    drive_ids = {}
    for p in result.plays[:upto]:
        off = h if p.side == 0 else a
        dfn = a if p.side == 0 else h
        drive_no = p.drive or _drive_for(result, p)
        drive_id = drive_ids.setdefault(drive_no, f"{r.id}{drive_no}")
        clock = p.clock if p.clock is not None else 0
        out.append({
            "gameId": r.id, "driveId": drive_id, "id": f"{r.id}{p.seq:03d}" if False else f"{r.id}{p.seq}", "driveNumber": drive_no,
            "playNumber": p.number or 1, "offense": off.school, "offenseConference": off.conference,
            "offenseScore": p.home_score if p.side == 0 else p.away_score, "defense": dfn.school, "defenseConference": dfn.conference,
            "defenseScore": p.away_score if p.side == 0 else p.home_score, "home": h.school, "away": a.school, "period": p.period,
            "clock": {"minutes": clock // 60, "seconds": clock % 60}, "offenseTimeouts": p.off_timeouts, "defenseTimeouts": p.def_timeouts,
            "yardline": (100 - p.ytg) if p.side == 0 else p.ytg, "yardsToGoal": p.ytg, "down": p.down, "distance": p.distance,
            "yardsGained": p.gained, "scoring": p.scoring, "playType": p.ptype, "playText": play_text(p, world.who, abbr, school),
            "ppa": p.ppa, "wallclock": as_iso(r.slot.start + timedelta(seconds=p.wall)),
        })
    return out


def _drive_for(result: GameResult, p: Play) -> int:
    for d in result.drives:
        if d.first_seq <= p.seq <= max(d.last_seq, d.first_seq):
            return d.number
    return result.drives[-1].number if result.drives else 1


def _visible_count(r: Record, result: GameResult, now: datetime) -> int | None:
    """How many plays the clock has reached: all when final, none before kickoff."""
    if r.end <= now:
        return None
    if now < r.slot.start:
        return 0
    elapsed = (now - r.slot.start).total_seconds()
    return sum(1 for p in result.plays if p.wall <= elapsed)


def r_plays(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    for r in select_games(world, params, now, default_type="regular"):
        if r.slot.start > now:
            continue
        result = world.simulate(r.id)
        if result is None:
            continue
        count = _visible_count(r, result, now)
        out.extend(_play_rows(world, r, result, count))
    return out


def _drive_rows(world: World, r: Record, result: GameResult) -> list[dict]:
    league = world.league
    h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
    out = []
    for d in result.drives:
        off = h if d.side == 0 else a
        dfn = a if d.side == 0 else h
        sc = d.start_clock if d.start_clock is not None else 0
        ec = d.end_clock if d.end_clock is not None else 0
        start_s = (d.start_period - 1) * 900 + 900 - sc if d.start_period <= 4 else 3600
        end_s = (d.end_period - 1) * 900 + 900 - ec if d.end_period <= 4 else 3600
        el = max(0, end_s - start_s)
        out.append({
            "id": f"{r.id}{d.number}", "gameId": r.id, "offense": off.school, "offenseConference": off.conference, "defense": dfn.school,
            "defenseConference": dfn.conference, "driveNumber": d.number, "scoring": d.scoring, "startPeriod": d.start_period,
            "startYardline": (100 - d.start_ytg) if d.side == 0 else d.start_ytg, "startYardsToGoal": d.start_ytg,
            "startTime": {"minutes": sc // 60, "seconds": sc % 60}, "endPeriod": d.end_period,
            "endYardline": (100 - d.end_ytg) if d.side == 0 else d.end_ytg, "endYardsToGoal": d.end_ytg,
            "endTime": {"minutes": ec // 60, "seconds": ec % 60}, "elapsed": {"minutes": el // 60, "seconds": el % 60},
            "plays": d.plays, "yards": d.yards, "driveResult": d.result, "isHomeOffense": d.side == 0,
            "startOffenseScore": d.start_off_score, "startDefenseScore": d.start_def_score, "endOffenseScore": d.end_off_score,
            "endDefenseScore": d.end_def_score,
        })
    return out


def r_drives(world: World, params: Params, now: datetime) -> list[dict]:
    out = []
    for r in select_games(world, params, now, default_type="regular"):
        if r.end > now:
            continue
        result = world.simulate(r.id)
        if result is not None:
            out.extend(_drive_rows(world, r, result))
    return out


def r_metrics_wp(world: World, params: Params, now: datetime) -> list[dict]:
    gid = p_int(params, "gameId")
    out: list[dict] = []
    for data in world.seasons.values():
        r = data.by_id.get(gid) if gid else None
        if r is None:
            continue
        if r.end > now:
            return []
        result = world.simulate(r.id)
        league = world.league
        h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
        abbr = (h.abbr, a.abbr)
        school = (h.school, a.school)
        n = 0
        for p in result.plays:
            # CFBD's series: the snaps and kicks, the ends of the first three quarters (the app times the game by
            # them), then one "Game ended" point at the final.
            quarter_end = p.ptype == "End Period" and p.d.get("ended", p.period) in (1, 2, 3)
            if not (S.is_rush(p) or S.is_pass(p) or quarter_end or p.ptype in ("Punt", "Field Goal Good", "Field Goal Missed", "Kickoff", "Penalty")):
                continue
            out.append({"gameId": r.id, "homeId": h.id, "home": h.school, "awayId": a.id, "away": a.school, "playId": f"{r.id}{p.seq}",
                        "playText": play_text(p, world.who, abbr, school), "homeScore": p.home_after, "awayScore": p.away_after,
                        "down": p.down, "distance": p.distance, "homeWinProbability": round(p.wp, 4), "spread": int(round(r.spread)),
                        "yardLine": p.ytg, "homeBall": p.side == 0, "playNumber": n})
            n += 1
        last = result.plays[-1]
        out.append({"gameId": r.id, "homeId": h.id, "home": h.school, "awayId": a.id, "away": a.school, "playId": f"{r.id}{last.seq + 1}",
                    "playText": "Game ended", "homeScore": r.home_points, "awayScore": r.away_points, "down": 0, "distance": 0,
                    "homeWinProbability": 1.0 if r.home_points > r.away_points else 0.0, "spread": int(round(r.spread)),
                    "yardLine": 0, "homeBall": last.side == 0, "playNumber": n})
    return out


def _pass_rows(world: World, r: Record, result: GameResult, team: Team) -> list[dict]:
    league = world.league
    h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
    side = 0 if team.id == h.id else 1
    off, dfn = (h, a) if side == 0 else (a, h)
    abbr, school = (h.abbr, a.abbr), (h.school, a.school)
    out = []
    for p in result.plays:
        if p.side != side or not S.is_pass(p) or p.d.get("sack"):
            continue
        d = p.d
        passer = league.players.get(str(d.get("passer")))
        target = league.players.get(str(d.get("target"))) if "target" in d else None
        outcome = "interception" if "interceptor" in d else "completion" if d.get("complete") else "incompletion"
        air = d.get("air")
        yac = d.get("yac") if outcome == "completion" else None
        out.append({
            "gameId": r.id, "playId": f"{r.id}{p.seq}", "driveId": f"{r.id}{p.drive}", "season": r.slot.season, "week": r.slot.week,
            "seasonType": r.slot.season_type, "offenseId": off.id, "offense": off.school, "offenseConference": off.conference,
            "defenseId": dfn.id, "defense": dfn.school, "defenseConference": dfn.conference, "period": p.period,
            "clock": {"minutes": (p.clock or 0) // 60, "seconds": (p.clock or 0) % 60}, "down": p.down, "distance": p.distance,
            "playText": play_text(p, world.who, abbr, school), "passerId": passer.id if passer else None, "passer": passer.name if passer else None,
            "targetId": target.id if target else None, "target": target.name if target else None, "outcome": outcome, "airYards": air,
            "passDepth": d.get("depth"), "passDirection": d.get("dir"), "passLocation": f"{d.get('depth')} {d.get('dir')}",
            "totalYards": p.gained, "yardsAfterCatch": yac, "startYardline": (100 - p.ytg) if side == 0 else p.ytg,
            "startYardsToGoal": p.ytg, "targetYardsToGoal": max(0, p.ytg - (air or 0)), "isSpike": False, "isThrowaway": False,
            "isIntentionalGrounding": False, "parseStatus": "complete", "ppa": p.ppa, "success": bool(p.success), "locationAnalysisEligible": True,
        })
    return out


def _rush_rows(world: World, r: Record, result: GameResult, team: Team) -> list[dict]:
    league = world.league
    h, a = league.by_id[r.slot.home], league.by_id[r.slot.away]
    side = 0 if team.id == h.id else 1
    off, dfn = (h, a) if side == 0 else (a, h)
    abbr, school = (h.abbr, a.abbr), (h.school, a.school)
    out = []
    for p in result.plays:
        if p.side != side or not (S.is_rush(p) or p.d.get("sack")):
            continue
        d = p.d
        sack = bool(d.get("sack"))
        rusher = league.players.get(str(d.get("passer") if sack else d.get("rusher")))
        direction = (d.get("dir") or "middle").split()[0] if not sack else None
        out.append({
            "gameId": r.id, "playId": f"{r.id}{p.seq}", "driveId": f"{r.id}{p.drive}", "season": r.slot.season, "week": r.slot.week,
            "seasonType": r.slot.season_type, "offenseId": off.id, "offense": off.school, "offenseConference": off.conference,
            "defenseId": dfn.id, "defense": dfn.school, "defenseConference": dfn.conference, "period": p.period,
            "clock": {"minutes": (p.clock or 0) // 60, "seconds": (p.clock or 0) % 60}, "down": p.down, "distance": p.distance,
            "playText": play_text(p, world.who, abbr, school), "startYardline": (100 - p.ytg) if side == 0 else p.ytg,
            "startYardsToGoal": p.ytg, "rusherId": rusher.id if rusher else None, "rusher": rusher.name if rusher else None,
            "rushDirection": direction, "rushingYards": p.gained, "rusherYards": p.gained, "isRushingTouchdown": p.ptype == "Rushing Touchdown",
            "isSack": sack, "isKneel": bool(d.get("kneel")), "isTeamRush": False, "attributionStatus": "individual",
            "directionAnalysisEligible": not sack, "parseStatus": "complete", "ppa": p.ppa, "success": bool(p.success),
        })
    return out


def _team_plays(world: World, params: Params, now: datetime, rows) -> list[dict]:
    team = team_by(world, p_str(params, "team"))
    if team is None:
        return []
    out = []
    for r in select_games(world, params, now, default_type="regular"):
        if r.end > now:
            continue
        result = world.simulate(r.id)
        if result is not None:
            out.extend(rows(world, r, result, team))
    return out


def r_passing_plays(world: World, params: Params, now: datetime) -> list[dict]:
    return _team_plays(world, params, now, _pass_rows)


def r_rushing_plays(world: World, params: Params, now: datetime) -> list[dict]:
    return _team_plays(world, params, now, _rush_rows)
