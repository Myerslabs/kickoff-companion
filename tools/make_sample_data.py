"""Build static/js/sample-data.js from the made-up league (public release Phase 3).

The styleguide shows every component with numbers from a simulated season: the demo team through
week 3 of the league's season, its last game as the live sample, its next game as the program.
The league answers by the names the recorded fixtures had (app/demo/fixtures.py), so this script
reads them the same way.

    python tools/make_sample_data.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # run as a script from tools/: the app package is one level up
    sys.path.insert(0, str(ROOT))

from app.services.logos import logo_fields  # noqa: E402 - after the path fix; the app's own logo URLs (Phase 16)

OUT = ROOT / "static" / "js" / "sample-data.js"

from app.demo.fixtures import league_fixture, roles  # noqa: E402
from app.demo.upstream import load_world  # noqa: E402

WORLD = load_world(cache_dir=ROOT / "data" / "demo")
ROLES = roles(WORLD)
TEAM = ROLES["US"]
CONFERENCE = ROLES["CONF"]
_LOADED: dict[str, Any] = {}


def load(name: str) -> Any:
    """The league's answer by a recorded fixture's name (built once per name)."""
    if name not in _LOADED:
        _LOADED[name] = league_fixture(WORLD, name, values=ROLES)["payload"]
    return json.loads(json.dumps(_LOADED[name]))


def num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def clock_seconds(value: Any) -> int | None:
    if isinstance(value, dict):
        return int(value.get("minutes") or 0) * 60 + int(value.get("seconds") or 0)
    if isinstance(value, str) and ":" in value:
        minutes, seconds = value.split(":", 1)
        return int(minutes) * 60 + int(seconds)
    return None


# --- teams -------------------------------------------------------------------------------


def team_lookup() -> dict[str, dict[str, Any]]:
    teams: dict[str, dict[str, Any]] = {}
    for team in load("teams_fbs"):
        teams[team["school"]] = {
            "school": team["school"],
            "abbreviation": team.get("abbreviation"),
            "mascot": team.get("mascot"),
            "conference": team.get("conference"),
            "color": team.get("color"),
            "altColor": team.get("alternateColor"),
            **logo_fields(team.get("id"), team.get("logos")),  # /media/logo URLs: the tablet never asks the CDN
        }
    return teams


# --- season stats with ranks ---------------------------------------------------------------

# label, formula key, higher is better, format
PROFILE_ROWS = [
    ("offense", "Yards per play", "ypp", True, "1f"),
    ("offense", "Total yards per game", "ypg", True, "0f"),
    ("offense", "Rushing yards per game", "rush_ypg", True, "0f"),
    ("offense", "Passing yards per game", "pass_ypg", True, "0f"),
    ("offense", "Third down", "third", True, "pct"),
    ("offense", "First downs per game", "fd_pg", True, "1f"),
    ("offense", "Turnovers lost per game", "to_lost_pg", False, "1f"),
    ("defense", "Yards per play allowed", "ypp_d", False, "1f"),
    ("defense", "Total yards allowed per game", "ypg_d", False, "0f"),
    ("defense", "Rushing yards allowed per game", "rush_ypg_d", False, "0f"),
    ("defense", "Passing yards allowed per game", "pass_ypg_d", False, "0f"),
    ("defense", "Third down allowed", "third_d", False, "pct"),
    ("defense", "Sacks per game", "sacks_pg", True, "1f"),
    ("defense", "Takeaways per game", "takeaways_pg", True, "1f"),
    ("both", "Turnover margin", "to_margin", True, "+0f"),
    ("both", "Penalty yards per game", "pen_ypg", False, "0f"),
]


def derive(stats: dict[str, float]) -> dict[str, float | None]:
    g = stats.get("games") or 0
    if not g:
        return {}

    def s(name: str) -> float:
        return stats.get(name) or 0.0

    def div(a: float, b: float) -> float | None:
        return a / b if b else None

    plays = s("rushingAttempts") + s("passAttempts")
    plays_d = s("rushingAttemptsOpponent") + s("passAttemptsOpponent")
    lost = s("passesIntercepted") + s("fumblesLost")
    taken = s("interceptions") + s("fumblesRecovered")
    return {
        "ypp": div(s("totalYards"), plays),
        "ypg": s("totalYards") / g,
        "rush_ypg": s("rushingYards") / g,
        "pass_ypg": s("netPassingYards") / g,
        "third": div(s("thirdDownConversions"), s("thirdDowns")),
        "fd_pg": s("firstDowns") / g,
        "to_lost_pg": lost / g,
        "ypp_d": div(s("totalYardsOpponent"), plays_d),
        "ypg_d": s("totalYardsOpponent") / g,
        "rush_ypg_d": s("rushingYardsOpponent") / g,
        "pass_ypg_d": s("netPassingYardsOpponent") / g,
        "third_d": div(s("thirdDownConversionsOpponent"), s("thirdDownsOpponent")),
        "sacks_pg": s("sacks") / g,
        "takeaways_pg": taken / g,
        "to_margin": taken - lost,
        "pen_ypg": s("penaltyYards") / g,
    }


def season_profiles() -> tuple[dict[str, dict[str, Any]], set[str]]:
    by_team: dict[str, dict[str, float]] = defaultdict(dict)
    conference_of: dict[str, str] = {}
    names: set[str] = set()
    for row in load("stats_season_fbs"):
        value = num(row.get("statValue"))
        if value is None:
            continue
        by_team[row["team"]][row["statName"]] = value
        conference_of[row["team"]] = row.get("conference") or ""
        names.add(row["statName"])
    derived = {team: derive(stats) for team, stats in by_team.items()}

    profiles: dict[str, dict[str, Any]] = {}
    for side, label, key, higher_better, fmt in PROFILE_ROWS:
        national = [(team, values[key]) for team, values in derived.items() if values.get(key) is not None]
        national.sort(key=lambda item: item[1], reverse=higher_better)
        conference = [(t, v) for t, v in national if conference_of.get(t) == CONFERENCE]
        nat_rank = {team: index + 1 for index, (team, _) in enumerate(national)}
        conf_rank = {team: index + 1 for index, (team, _) in enumerate(conference)}
        for team, value in national:
            profiles.setdefault(team, {"team": team, "conference": conference_of.get(team), "rows": []})
            profiles[team]["rows"].append(
                {
                    "side": side,
                    "label": label,
                    "key": key,
                    "metric": f"profile:{key}",
                    "value": round(value, 3),
                    "format": fmt,
                    "higherIsBetter": higher_better,
                    "nationalRank": nat_rank[team],
                    "nationalOf": len(national),
                    "conferenceRank": conf_rank.get(team),
                    "conferenceOf": len(conference),
                }
            )
    return profiles, names


# --- leaders --------------------------------------------------------------------------------

LEADER_CATEGORIES = [
    ("passing", "YDS", "Passing yards"),
    ("rushing", "YDS", "Rushing yards"),
    ("receiving", "YDS", "Receiving yards"),
    ("defensive", "TOT", "Tackles"),
    ("defensive", "SACKS", "Sacks"),
    ("interceptions", "INT", "Interceptions"),
]


def player_lines(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(playerId, category) -> {player, position, team, stats{statType: value}}."""
    lines: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["playerId"], row["category"])
        line = lines.setdefault(
            key,
            {"playerId": row["playerId"], "player": row["player"], "position": row.get("position"), "team": row["team"], "stats": {}},
        )
        line["stats"][row["statType"]] = num(row["stat"]) if num(row["stat"]) is not None else row["stat"]
    return lines


def leaders(team_rows: list[dict[str, Any]], conf_rows: list[dict[str, Any]], all_passing: list[dict[str, Any]]) -> dict[str, Any]:
    team_lines = player_lines(team_rows)
    conf_lines = player_lines(conf_rows)
    passing_all = player_lines(all_passing)

    def ranked(lines: dict[tuple[str, str], dict[str, Any]], category: str, stat: str) -> list[dict[str, Any]]:
        entries = [line for (_, cat), line in lines.items() if cat == category and isinstance(line["stats"].get(stat), float)]
        entries.sort(key=lambda line: line["stats"][stat], reverse=True)
        return entries

    out: dict[str, Any] = {}
    for category, stat, label in LEADER_CATEGORIES:
        conf_board = ranked(conf_lines, category, stat)
        conf_rank = {line["playerId"]: index + 1 for index, line in enumerate(conf_board)}
        nat_board = ranked(passing_all, category, stat) if category == "passing" else []
        nat_rank = {line["playerId"]: index + 1 for index, line in enumerate(nat_board)}
        team_board = ranked(team_lines, category, stat)[:5]
        out[f"{category}:{stat}"] = {
            "category": category,
            "stat": stat,
            "label": label,
            "team": [
                {
                    "playerId": line["playerId"],
                    "player": line["player"],
                    "position": line["position"],
                    "value": line["stats"][stat],
                    "detail": {k: v for k, v in line["stats"].items() if k != stat},
                    "conferenceRank": conf_rank.get(line["playerId"]),
                    "conferenceOf": len(conf_board),
                    "nationalRank": nat_rank.get(line["playerId"]),
                    "nationalOf": len(nat_board) or None,
                }
                for line in team_board
            ],
            "conferenceTop": [
                {"player": line["player"], "team": line["team"], "position": line["position"], "value": line["stats"][stat]}
                for line in conf_board[:10]
            ],
            "nationalTop": [
                {"player": line["player"], "team": line["team"], "position": line["position"], "value": line["stats"][stat]}
                for line in nat_board[:10]
            ],
        }
    return out


# --- the live game sample (the demo team's last game) ----------------------------------------------------

EXPLOSIVE_RUSH = 10
EXPLOSIVE_PASS = 20


def key_play_flags(play: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    ptype = (play.get("playType") or "").lower()
    text = (play.get("playText") or "").lower()
    gained = play.get("yardsGained") or 0
    if play.get("scoring") and "touchdown" in ptype:
        flags.append("td")
    if "interception" in ptype or "fumble recovery (opponent)" in ptype:
        flags.append("turnover")
    if "sack" in ptype:
        flags.append("sack")
    if "rush" in ptype and gained >= EXPLOSIVE_RUSH:
        flags.append("explosive")
    if ("pass" in ptype or "reception" in ptype) and gained >= EXPLOSIVE_PASS:
        flags.append("explosive")
    if play.get("down") == 4 and not any(word in ptype for word in ("punt", "field goal", "kickoff", "timeout", "penalty")):
        flags.append("fourth")
    if "penalty" in ptype and ("15 yards" in text or "15 yard" in text):
        flags.append("penalty")
    return flags


def play_success(play: dict[str, Any]) -> bool | None:
    """The standard success rule: 50% of the distance on 1st down, 70% on 2nd, 100% on 3rd and 4th.
    Scrimmage plays only; anything without a down or a distance is not judged."""
    down, distance, gained = play.get("down"), play.get("distance"), play.get("yardsGained")
    ptype = (play.get("playType") or "").lower()
    if not isinstance(down, int) or not isinstance(distance, (int, float)) or not isinstance(gained, (int, float)):
        return None
    if any(word in ptype for word in ("kickoff", "punt", "field goal", "timeout", "penalty", "end of", "extra point")):
        return None
    if play.get("scoring") and "touchdown" in ptype:
        return True
    needed = {1: 0.5, 2: 0.7}.get(down, 1.0) * distance
    return gained >= needed


def box_stats(side: dict[str, Any]) -> dict[str, Any]:
    stats = {item["category"]: item["stat"] for item in side.get("stats", [])}

    def split(value: Any) -> tuple[int | None, int | None]:
        if isinstance(value, str) and "-" in value:
            a, b = value.split("-", 1)
            return (int(a) if a.isdigit() else None, int(b) if b.isdigit() else None)
        return None, None

    third = split(stats.get("thirdDownEff"))
    fourth = split(stats.get("fourthDownEff"))
    penalties = split(stats.get("totalPenaltiesYards"))
    return {
        "team": side.get("team"),
        "homeAway": side.get("homeAway"),
        "points": side.get("points"),
        "totalYards": num(stats.get("totalYards")),
        "netPassingYards": num(stats.get("netPassingYards")),
        "rushingYards": num(stats.get("rushingYards")),
        "thirdDown": {"made": third[0], "of": third[1]},
        "fourthDown": {"made": fourth[0], "of": fourth[1]},
        "turnovers": num(stats.get("turnovers")),
        "penalties": {"count": penalties[0], "yards": penalties[1]},
        "possessionTime": stats.get("possessionTime"),
        "firstDowns": num(stats.get("firstDowns")),
        "raw": stats,
    }


def live_game(teams: dict[str, dict[str, Any]]) -> dict[str, Any]:
    game_box = load("games_teams")[0]
    game_players = load("games_players")[0]
    drives = load("drives")
    plays = load("plays")
    wp = load("metrics_wp")
    schedule = load("games_team")
    game = next(g for g in schedule if g["id"] == game_box["id"])
    home, away = game["homeTeam"], game["awayTeam"]

    sides = {side["team"]: box_stats(side) for side in game_box["teams"]}
    play_count: dict[str, int] = defaultdict(int)
    for drive in drives:
        play_count[drive["offense"]] += drive.get("plays") or 0
    drive_count: dict[str, int] = defaultdict(int)
    for drive in drives:
        if not str(drive.get("driveResult") or "").upper().startswith("END OF"):
            drive_count[drive["offense"]] += 1
    explosive: dict[str, dict[str, int]] = defaultdict(lambda: {"twenty": 0, "forty": 0})
    success: dict[str, dict[str, int]] = defaultdict(lambda: {"successes": 0, "judged": 0})
    for play in plays:
        offense = play.get("offense")
        gained = play.get("yardsGained") or 0
        ptype = (play.get("playType") or "").lower()
        if offense and ("rush" in ptype or "pass" in ptype or "reception" in ptype):
            if gained >= 20:
                explosive[offense]["twenty"] += 1
            if gained >= 40:
                explosive[offense]["forty"] += 1
        verdict = play_success(play)
        if offense and verdict is not None:
            success[offense]["judged"] += 1
            success[offense]["successes"] += int(verdict)
    for team, side in sides.items():
        side["plays"] = play_count.get(team)
        side["drives"] = drive_count.get(team)
        side["explosive"] = dict(explosive.get(team, {"twenty": 0, "forty": 0}))
        judged = success.get(team, {}).get("judged") or 0
        side["successRate"] = round(success[team]["successes"] / judged, 3) if judged else None
        side["successCounts"] = dict(success.get(team, {"successes": 0, "judged": 0}))
        side["yardsPerPlay"] = round(side["totalYards"] / play_count[team], 2) if side["totalYards"] and play_count.get(team) else None
        red_trips = [d for d in drives if d["offense"] == team and (d.get("endYardsToGoal") or 100) <= 20]
        red_scores = [d for d in red_trips if (d.get("driveResult") or "").upper() in ("TD", "FG")]
        side["redZone"] = {"scores": len(red_scores), "trips": len(red_trips)}

    player_stats: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for side in game_players["teams"]:
        categories: dict[str, list[dict[str, Any]]] = {}
        for category in side.get("categories", []):
            rows: dict[str, dict[str, Any]] = {}
            for stat_type in category.get("types", []):
                for athlete in stat_type.get("athletes", []):
                    row = rows.setdefault(athlete["id"], {"playerId": athlete["id"], "name": athlete["name"], "stats": {}})
                    value = athlete.get("stat")
                    row["stats"][stat_type["name"]] = num(value) if num(value) is not None and "/" not in str(value) else value
            categories[category["name"]] = list(rows.values())
        player_stats[side["team"]] = categories

    drive_rows = []
    for drive in sorted(drives, key=lambda d: (d.get("driveNumber") or 0)):
        drive_rows.append(
            {
                "id": drive["id"],
                "number": drive.get("driveNumber"),
                "offense": drive["offense"],
                "startYardsToGoal": drive.get("startYardsToGoal"),
                "endYardsToGoal": drive.get("endYardsToGoal"),
                "plays": drive.get("plays"),
                "yards": drive.get("yards"),
                "result": drive.get("driveResult"),
                "scoring": drive.get("scoring"),
                "period": drive.get("startPeriod"),
                "startClock": drive.get("startTime"),
                "elapsedSeconds": clock_seconds(drive.get("elapsed")),
                "startScore": [drive.get("startOffenseScore"), drive.get("startDefenseScore")],
                "endScore": [drive.get("endOffenseScore"), drive.get("endDefenseScore")],
            }
        )

    play_rows = []
    for play in sorted(plays, key=lambda p: (p.get("period") or 0, -(clock_seconds(p.get("clock")) or 0), p.get("playNumber") or 0)):
        play_rows.append(
            {
                "id": play["id"],
                "driveId": play.get("driveId"),
                "period": play.get("period"),
                "clock": play.get("clock"),
                "offense": play.get("offense"),
                "down": play.get("down"),
                "distance": play.get("distance"),
                "yardsToGoal": play.get("yardsToGoal"),
                "yardsGained": play.get("yardsGained"),
                "playType": play.get("playType"),
                "text": play.get("playText"),
                "scoring": play.get("scoring"),
                "ppa": play.get("ppa"),
                "success": play_success(play),
                "offenseScore": play.get("offenseScore"),
                "defenseScore": play.get("defenseScore"),
                "flags": key_play_flags(play),
            }
        )
    play_rows.reverse()  # newest first

    wp_series = [
        {"play": row.get("playNumber"), "homeWp": row.get("homeWinProbability"), "homeScore": row.get("homeScore"), "awayScore": row.get("awayScore")}
        for row in sorted(wp, key=lambda r: r.get("playNumber") or 0)
    ]

    return {
        "gameId": game["id"],
        "week": game["week"],
        "date": game["startDate"],
        "venue": game.get("venue"),
        "home": {"school": home, **teams.get(home, {}), "points": game.get("homePoints")},
        "away": {"school": away, **teams.get(away, {}), "points": game.get("awayPoints")},
        "final": bool(game.get("completed")),
        "lineScores": {"home": game.get("homeLineScores") or [], "away": game.get("awayLineScores") or []},
        "box": sides,
        "playerStats": player_stats,
        "drives": drive_rows,
        "plays": play_rows,
        "winProbability": wp_series,
    }


# --- program sample (the demo team's next game) -----------------------------------------------------------


def tendencies(plays: list[dict[str, Any]], offense: str) -> dict[str, Any]:
    def bucket(distance: int | None) -> str:
        if distance is None:
            return "unknown"
        if distance <= 3:
            return "short (1-3)"
        if distance <= 6:
            return "medium (4-6)"
        return "long (7+)"

    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"run": 0, "pass": 0})
    for play in plays:
        if play.get("offense") != offense:
            continue
        ptype = (play.get("playType") or "").lower()
        if "rush" in ptype:
            kind = "run"
        elif "pass" in ptype or "sack" in ptype or "interception" in ptype:
            kind = "pass"
        else:
            continue
        down = play.get("down")
        if down in (1, 2, 3, 4):
            counts[f"down:{down}"][kind] += 1
            counts[f"dist:{bucket(play.get('distance'))}"][kind] += 1
    rows = []
    for key, value in sorted(counts.items()):
        total = value["run"] + value["pass"]
        rows.append({"split": key, "run": value["run"], "pass": value["pass"], "runRate": round(value["run"] / total, 3) if total else None})
    return {"offense": offense, "rows": rows, "source": "week 3 game plays"}


def program(teams: dict[str, dict[str, Any]], profiles: dict[str, dict[str, Any]], conf_rows: list[dict[str, Any]]) -> dict[str, Any]:
    schedule = load("games_team")
    upcoming = [g for g in schedule if not g.get("completed")]
    game = min(upcoming, key=lambda g: g["week"])
    opponent = game["awayTeam"] if game["homeTeam"] == TEAM else game["homeTeam"]
    media = {m["id"]: m["outlet"] for m in load("games_media") if m.get("mediaType") == "tv"}
    lines = next((l for l in load("lines") if l["id"] == game["id"]), None)
    line = (lines or {}).get("lines", [{}])[0] if lines and lines.get("lines") else {}
    pregame = next((p for p in load("metrics_wp_pregame") if p["gameId"] == game["id"]), None)
    matchup = load("teams_matchup")
    sp = {t["team"]: t for t in load("ratings_sp")}
    fpi = {t["team"]: t for t in load("ratings_fpi")}
    elo = {t["team"]: t for t in load("ratings_elo")}
    records = {r["team"]: r for r in load("records_conference")}
    polls = load("rankings")[0]["polls"]

    def rank_in(poll_name: str, team: str) -> int | None:
        for poll in polls:
            if poll["poll"] == poll_name:
                for rank in poll["ranks"]:
                    if rank["school"] == team:
                        return rank.get("rank")
        return None

    def team_block(name: str) -> dict[str, Any]:
        rec = records.get(name, {})
        return {
            **teams.get(name, {"school": name}),
            "record": rec.get("total"),
            "conferenceRecord": rec.get("conferenceGames"),
            "apRank": rank_in("AP Top 25", name),
            "coachesRank": rank_in("Coaches Poll", name),
            "sp": {"rating": sp.get(name, {}).get("rating"), "rank": sp.get(name, {}).get("ranking"), "of": sum(1 for t in sp.values() if t.get("rating") is not None and t["team"] != "nationalAverages"), "metric": "rating:sp"},
            "fpi": fpi.get(name, {}).get("fpi"),
            "elo": elo.get(name, {}).get("elo"),
        }

    home_is_us = game["homeTeam"] == TEAM
    us, them = profiles.get(TEAM, {"rows": []}), profiles.get(opponent, {"rows": []})
    them_rows = {row["key"]: row for row in them["rows"]}
    tape = []
    for row in us["rows"]:
        other = them_rows.get(row["key"])
        tape.append({"label": row["label"], "side": row["side"], "format": row["format"], "higherIsBetter": row["higherIsBetter"], "us": row, "them": other})

    pairs = [("ypp", "ypp_d", "Yards per play"), ("rush_ypg", "rush_ypg_d", "Rushing"), ("pass_ypg", "pass_ypg_d", "Passing"), ("third", "third_d", "Third down")]
    us_rows = {row["key"]: row for row in us["rows"]}
    edges = []
    for off_key, def_key, label in pairs:
        if off_key in us_rows and def_key in them_rows:
            edges.append({"label": f"{TEAM} {label.lower()} vs {opponent} defense", "side": "offense", "usRank": us_rows[off_key]["nationalRank"], "themRank": them_rows[def_key]["nationalRank"], "of": us_rows[off_key]["nationalOf"], "themOf": them_rows[def_key]["nationalOf"], "edge": them_rows[def_key]["nationalRank"] - us_rows[off_key]["nationalRank"], "usValue": us_rows[off_key]["value"], "themValue": them_rows[def_key]["value"], "usKey": off_key, "themKey": def_key, "usMetric": f"profile:{off_key}", "themMetric": f"profile:{def_key}"})
        if off_key in them_rows and def_key in us_rows:
            edges.append({"label": f"{opponent} {label.lower()} vs {TEAM} defense", "side": "defense", "usRank": us_rows[def_key]["nationalRank"], "themRank": them_rows[off_key]["nationalRank"], "of": us_rows[def_key]["nationalOf"], "themOf": them_rows[off_key]["nationalOf"], "edge": us_rows[def_key]["nationalRank"] - them_rows[off_key]["nationalRank"], "usValue": us_rows[def_key]["value"], "themValue": them_rows[off_key]["value"], "usKey": def_key, "themKey": off_key, "usMetric": f"profile:{def_key}", "themMetric": f"profile:{off_key}"})
    edges.sort(key=lambda e: -abs(e["edge"]))

    conf_lines = player_lines(conf_rows)
    side_by_side = []
    for category, stat, label in LEADER_CATEGORIES[:3]:
        def top(team: str) -> dict[str, Any] | None:
            entries = [line for (_, cat), line in conf_lines.items() if cat == category and line["team"] == team and isinstance(line["stats"].get(stat), float)]
            entries.sort(key=lambda line: line["stats"][stat], reverse=True)
            return {"player": entries[0]["player"], "position": entries[0]["position"], "value": entries[0]["stats"][stat]} if entries else None
        side_by_side.append({"label": label, "us": top(TEAM), "them": top(opponent)})

    games_hist = sorted(matchup.get("games", []), key=lambda g: (g.get("season") or 0, g.get("week") or 0), reverse=True)
    series = {
        "team1": matchup.get("team1"), "team2": matchup.get("team2"),
        "team1Wins": matchup.get("team1Wins"), "team2Wins": matchup.get("team2Wins"), "ties": matchup.get("ties"),
        "lastTen": games_hist[:10],
        "streak": None,
    }
    streak_team, streak = None, 0
    for g in games_hist:
        winner = g.get("winner")
        if not winner:
            break
        if streak_team is None:
            streak_team, streak = winner, 1
        elif winner == streak_team:
            streak += 1
        else:
            break
    series["streak"] = {"team": streak_team, "games": streak} if streak_team else None

    return {
        "gameId": game["id"],
        "week": game["week"],
        "date": game["startDate"],
        "startTimeTbd": game.get("startTimeTBD"),
        "venue": game.get("venue"),
        "neutralSite": game.get("neutralSite"),
        "tv": media.get(game["id"]),
        "homeIsUs": home_is_us,
        "us": team_block(TEAM),
        "them": team_block(opponent),
        "line": {"spread": line.get("spread"), "formatted": line.get("formattedSpread"), "spreadOpen": line.get("spreadOpen"), "overUnder": line.get("overUnder"), "overUnderOpen": line.get("overUnderOpen")},
        "pregame": {"homeWinProbability": (pregame or {}).get("homeWinProbability")},
        "taleOfTheTape": tape,
        "edges": edges[:6],
        "leadersSideBySide": side_by_side,
        "series": series,
        "tendencies": tendencies(load("plays"), next((t["team"] for t in load("games_teams")[0]["teams"] if t["team"] != TEAM), "")),
        "weather": None,
        "themProfile": them,
        "advanced": {TEAM: advanced_block(TEAM), opponent: advanced_block(opponent)},
    }


def advanced_block(team: str) -> dict[str, Any] | None:
    """Offense and defense success rate, explosiveness, and PPA from the advanced season stats."""
    rows = [r for r in load("stats_season_advanced_fbs") if r.get("team") == team]
    if not rows:
        return None
    row = rows[0]

    def side(name: str) -> dict[str, Any]:
        block = row.get(name) or {}
        return {"successRate": num(block.get("successRate")), "explosiveness": num(block.get("explosiveness")), "ppa": num(block.get("ppa")), "plays": block.get("plays"), "drives": block.get("drives")}

    return {"offense": side("offense"), "defense": side("defense")}


# --- roster, schedule, misc ---------------------------------------------------------------------

CLASS_NAMES = {1: "FR", 2: "SO", 3: "JR", 4: "SR", 5: "GR"}


def recruit_lookup() -> dict[str, dict[str, Any]]:
    """Recruit id -> high school, stars, rating, national rank. Only the recorded class is known."""
    out: dict[str, dict[str, Any]] = {}
    for recruit in load("recruiting_players"):
        out[str(recruit.get("id"))] = {
            "highSchool": recruit.get("school"),
            "stars": recruit.get("stars"),
            "rating": num(recruit.get("rating")),
            "nationalRank": recruit.get("ranking"),
            "classYear": recruit.get("year"),
        }
    return out


def recruiting() -> dict[str, Any]:
    commits = []
    counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for recruit in load("recruiting_players"):
        stars = recruit.get("stars")
        if isinstance(stars, int) and stars in counts:
            counts[stars] += 1
        height = recruit.get("height")
        commits.append(
            {
                "recruitId": str(recruit.get("id")),
                "athleteId": recruit.get("athleteId"),
                "name": recruit.get("name"),
                "position": recruit.get("position"),
                "stars": stars,
                "rating": num(recruit.get("rating")),
                "nationalRank": recruit.get("ranking"),
                "highSchool": recruit.get("school"),
                "hometown": ", ".join(part for part in (recruit.get("city"), recruit.get("stateProvince")) if part) or None,
                "height": f"{int(height // 12)}-{int(height % 12)}" if height else None,
                "weight": recruit.get("weight"),
                "committedTo": recruit.get("committedTo"),
            }
        )
    commits.sort(key=lambda c: (c["nationalRank"] is None, c["nationalRank"] or 0))
    rated = [c["stars"] for c in commits if isinstance(c["stars"], int)]
    year = next((load("recruiting_players")[0].get("year") for _ in [0] if load("recruiting_players")), None)
    return {
        "year": year,
        "commits": commits,
        "starCounts": {str(k): v for k, v in counts.items()},
        "average": round(sum(rated) / len(rated), 2) if rated else None,
        "nextYear": {"year": (year or 0) + 1, "commits": [], "note": "Next year's class needs one recruiting call. Not recorded yet."},
        "visitors": {"home": [], "away": [], "note": "Visitors come from the per-game notes file. None written for this game."},
    }


def roster() -> list[dict[str, Any]]:
    recruits = recruit_lookup()
    rows = []
    for player in load("roster"):
        height = player.get("height")
        recruit_ids = [str(r) for r in (player.get("recruitIds") or [])]
        recruit = next((recruits[r] for r in recruit_ids if r in recruits), {})
        rows.append(
            {
                "playerId": player["id"],
                "number": player.get("jersey"),
                "name": f"{player.get('firstName', '')} {player.get('lastName', '')}".strip(),
                "position": player.get("position"),
                "classYear": CLASS_NAMES.get(player.get("year") or 0),
                "height": f"{int(height // 12)}-{int(height % 12)}" if height else None,
                "weight": player.get("weight"),
                "hometown": ", ".join(part for part in (player.get("homeCity"), player.get("homeState")) if part) or None,
                "highSchool": recruit.get("highSchool"),
                "stars": recruit.get("stars"),
                "rating": recruit.get("rating"),
                "recruitRank": recruit.get("nationalRank"),
                "recruitIds": recruit_ids,
            }
        )
    rows.sort(key=lambda r: (r["number"] is None, r["number"] or 0, r["name"]))
    return rows


def schedule(teams: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    media = {m["id"]: m["outlet"] for m in load("games_media") if m.get("mediaType") == "tv"}
    rows = []
    for game in sorted(load("games_team"), key=lambda g: g["week"]):
        home_is_us = game["homeTeam"] == TEAM
        opponent = game["awayTeam"] if home_is_us else game["homeTeam"]
        us_points = game.get("homePoints") if home_is_us else game.get("awayPoints")
        them_points = game.get("awayPoints") if home_is_us else game.get("homePoints")
        result = None
        if game.get("completed") and us_points is not None and them_points is not None:
            result = "W" if us_points > them_points else "L" if us_points < them_points else "T"
        rows.append(
            {
                "gameId": game["id"],
                "week": game["week"],
                "date": game["startDate"],
                "startTimeTbd": game.get("startTimeTBD"),
                "opponent": {**teams.get(opponent, {"school": opponent})},
                "homeAway": "neutral" if game.get("neutralSite") else ("home" if home_is_us else "away"),
                "venue": game.get("venue"),
                "completed": bool(game.get("completed")),
                "result": result,
                "usPoints": us_points,
                "themPoints": them_points,
                "tv": media.get(game["id"]),
                "conferenceGame": game.get("conferenceGame"),
            }
        )
    return rows


def local_date(iso: str | None) -> str | None:
    """The calendar date in the owner's time zone, so a 7:30 pm ET Saturday kickoff stays on Saturday."""
    if not iso:
        return None
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except (ValueError, TypeError):
        return None


def newspaper(teams: dict[str, dict[str, Any]], prog: dict[str, Any]) -> dict[str, Any]:
    """The Saturday slate (N1): every game on our game day with a Top 25 or conference team, from the
    week-wide fixtures recorded 2026-09-21. Ranks come from the latest recorded poll."""
    games = [g for g in load("games_week") if isinstance(g, dict)]
    lines = {l.get("id"): l for l in load("lines_week") if isinstance(l, dict)}
    wp = {w.get("gameId"): w for w in load("metrics_wp_pregame_week") if isinstance(w, dict)}
    media = {m.get("id"): m.get("outlet") for m in load("games_media_week") if isinstance(m, dict) and m.get("mediaType") == "tv"}
    records = {r.get("team"): r for r in load("records_all") if isinstance(r, dict)}
    polls = load("rankings")[0]["polls"]
    ap = {r["school"]: r.get("rank") for p in polls if p.get("poll") == "AP Top 25" for r in p.get("ranks", [])}
    coaches = {r["school"]: r.get("rank") for p in polls if p.get("poll") == "Coaches Poll" for r in p.get("ranks", [])}

    us_game = next((g for g in games if TEAM in (g.get("homeTeam"), g.get("awayTeam"))), None)
    day = local_date((us_game or {}).get("startDate")) or local_date(prog.get("date"))

    def block(name: str) -> dict[str, Any]:
        rec = records.get(name, {})
        return {**teams.get(name, {"school": name}), "school": name, "record": rec.get("total"), "conferenceRecord": rec.get("conferenceGames"), "apRank": ap.get(name), "coachesRank": coaches.get(name)}

    slate = []
    for g in games:
        if local_date(g.get("startDate")) != day:
            continue
        home, away = g.get("homeTeam"), g.get("awayTeam")
        if not home or not away:
            continue
        top25 = home in ap or away in ap
        sec = CONFERENCE in (g.get("homeConference"), g.get("awayConference"))
        if not (top25 or sec):
            continue
        book = ((lines.get(g.get("id")) or {}).get("lines") or [{}])[0] or {}
        slate.append(
            {
                "gameId": g.get("id"),
                "week": g.get("week"),
                "kickoff": g.get("startDate"),
                "startTimeTbd": g.get("startTimeTBD"),
                "tv": media.get(g.get("id")),
                "venue": g.get("venue"),
                "neutralSite": g.get("neutralSite"),
                "conferenceGame": g.get("conferenceGame"),
                "home": block(home),
                "away": block(away),
                "isUs": TEAM in (home, away),
                "line": {"spread": book.get("spread"), "formatted": book.get("formattedSpread"), "overUnder": book.get("overUnder")},
                "homeWinProbability": (wp.get(g.get("id")) or {}).get("homeWinProbability"),
            }
        )
    slate.sort(key=lambda s: (not s["isUs"], s.get("kickoff") or ""))
    week = (us_game or {}).get("week") or prog.get("week")
    return {
        "date": (us_game or {}).get("startDate") or prog.get("date"),
        "week": week,
        "slate": slate,
        "slateNote": f"Week {week}: {len(slate)} games on {day} with a Top 25 or {CONFERENCE} team, out of {len(games)} games that week. From the made-up league.",
        "news": [],
        "newsNote": "Headlines come from the team's own feed, two national feeds, and a news search for the team.",
    }


def roster_history() -> dict[str, list[dict[str, Any]]]:
    """Player id -> one row per recorded season on the roster (2022 to the current year)."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    names = ["roster_2022", "roster_2023", "roster_2024", "roster_2025", "roster"]  # four seasons back, then this one
    for name in names:
        data = league_fixture(WORLD, name, values=ROLES)
        year = int((data.get("params") or {}).get("year") or 0) or None
        for player in data.get("payload") or []:
            if not isinstance(player, dict) or not player.get("id"):
                continue
            out[str(player["id"])].append(
                {"year": year, "team": player.get("team"), "classYear": CLASS_NAMES.get(player.get("year") or 0), "position": player.get("position"), "number": player.get("jersey")}
            )
    for rows in out.values():
        rows.sort(key=lambda r: r["year"] or 0)
    return dict(out)


def main() -> int:
    teams = team_lookup()
    profiles, stat_names = season_profiles()
    conf_rows = load("stats_player_season_conference")
    records = {r["team"]: r for r in load("records_conference")}
    ours = records.get(TEAM, {})
    sched = schedule(teams)
    program_sample = program(teams, profiles, conf_rows)
    points_us = [g["usPoints"] for g in sched if g["completed"]]
    points_them = [g["themPoints"] for g in sched if g["completed"]]

    sample = {
        "generatedFrom": "the made-up league (app/demo), as of the Monday after week 3",
        "season": int(ROLES["S"]),
        "team": teams.get(TEAM),
        "record": {
            "overall": ours.get("total"),
            "conference": ours.get("conferenceGames"),
            "home": ours.get("homeGames"),
            "away": ours.get("awayGames"),
        },
        "schedule": sched,
        "polls": [{"poll": p["poll"], "top": p["ranks"][:10]} for p in load("rankings")[0]["polls"][:2]],
        "profile": profiles.get(TEAM),
        "profiles": {name: profiles.get(name) for name in (TEAM, program_sample["them"]["school"]) if profiles.get(name)},
        "trends": {
            "points": points_us,
            "pointsAllowed": points_them,
            "weeks": [g["week"] for g in sched if g["completed"]],
        },
        "leaders": leaders(load("stats_player_season_team"), conf_rows, load("stats_player_season_all_passing")),
        "live": live_game(teams),
        "program": program_sample,
        "newspaper": newspaper(teams, program_sample),
        "recruiting": recruiting(),
        "roster": roster(),
        "rosterHistory": roster_history(),
        "ratings": {
            "sp": next((t for t in load("ratings_sp") if t["team"] == TEAM), None),
            "fpi": next((t for t in load("ratings_fpi") if t["team"] == TEAM), None),
            "elo": next((t for t in load("ratings_elo") if t["team"] == TEAM), None),
        },
        "statNames": sorted(stat_names),
    }
    body = json.dumps(sample, indent=1, ensure_ascii=False)
    OUT.write_text(
        "// Generated by tools/make_sample_data.py from the recorded CFBD fixtures. Do not edit by hand.\n"
        f"export const sample = {body};\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    print("stat names:", ", ".join(sorted(stat_names)))
    print("profile rows:", len((profiles.get(TEAM) or {}).get("rows", [])), "| leaders:", list(sample["leaders"].keys()))
    print("live:", sample["live"]["home"]["school"], sample["live"]["home"]["points"], "-", sample["live"]["away"]["school"], sample["live"]["away"]["points"], "| drives", len(sample["live"]["drives"]), "| plays", len(sample["live"]["plays"]))
    print("newspaper:", sample["newspaper"]["week"], "slate", len(sample["newspaper"]["slate"]), "| roster history players", len(sample["rosterHistory"]))
    print("program:", sample["program"]["them"]["school"], "week", sample["program"]["week"], "| edges", [(e["label"], e["edge"]) for e in sample["program"]["edges"][:3]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
