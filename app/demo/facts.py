"""School facts for the made-up league (the trivia, owner 2026-10-21), so the demo and the simulator can ask questions.

Every FBS team of the league gets a row in the facts prompt's shape, drawn deterministically from the team's id: a
founding year, its stadium from the league's venue, titles and Heismans for the proud programs, two rivals of its
conference with a trophy for the first, the coach's record from the league's coach, a mascot's name, a fight song, a
few traditions and five dated events. Nothing here names a real school; it reads like the league's own lore.

    league_facts(league, season) -> {school: row}
    write_demo_facts(data_dir, league, season)   writes data/facts.json for a demo install when there is none"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.demo import names as N
from app.services.answers import atomic_write

log = logging.getLogger("kickoff.demo")

TROPHIES = ("The Skillet", "The Biscuit Bowl", "The Gravy Boat", "The Iron Spatula", "The Brass Ladle", "The Golden Whisk", "The Cast Iron Pan", "The Pickle Jar", "The Butter Dish", "The Old Oven Mitt", "The Silver Sifter", "The Copper Kettle", "The Rolling Pin", "The Tin Cup")
NICKNAMES = ("The Pantry", "The Pit", "The Furnace", "The Icebox", "The Kettle", "The Skillet", "The Cellar", "The Oven")
MASCOT_HEADS = ("Big", "Ol'", "Captain", "Chef", "Major", "Mister", "Doc", "Uncle", "Biscuit", "Gravy")
SONGS = ("Hail, {school}", "On, {mascot}", "{school} Forever", "Fight, {mascot}, Fight", "The {school} March", "Roll On, {mascot}")
TRADITIONS = ("The pregame walk through the tailgate", "The fourth-quarter whistle", "The biscuit toss after a touchdown", "The gravy pour at halftime", "The kettle bell before kickoff", "The skillet drum on third down", "The lantern walk after a night win", "Singing the song with arms locked")
COLOR_STORIES = ("picked by the first team from the cloth the town store had", "voted by the students of {founded}", "borrowed from the county fair's ribbons", "chosen by the founder's wife, who sewed the first banners")


def _team_rng(team: Any) -> random.Random:
    return random.Random(f"facts:{getattr(team, 'id', 0)}:{getattr(team, 'school', '')}")


def _name(rng: random.Random) -> str:
    return f"{rng.choice(N.FIRST_NAMES)} {rng.choice(N.LAST_NAMES)}"


def _record(rng: random.Random, games: int, share: float) -> str:
    wins = int(games * share)
    ties = rng.randint(0, 12) if games > 400 else rng.randint(0, 3)
    return f"{wins}-{games - wins - ties}-{ties}"


def _years(rng: random.Random, count: int, low: int, high: int) -> list[int]:
    if count <= 0 or high <= low:
        return []
    pool = list(range(low, high + 1))
    return sorted(rng.sample(pool, min(count, len(pool))))


def team_facts(team: Any, rivals: list[Any], season: int) -> dict[str, Any]:
    rng = _team_rng(team)
    prestige = float(getattr(team, "prestige", 0.5) or 0.5)
    venue = getattr(team, "venue", None)
    school, mascot = team.school, team.mascot
    founded = rng.randint(1851, 1968)
    first_season = min(founded + rng.randint(4, 30), season - 50)
    opened = int(getattr(venue, "construction_year", 0) or 0) or max(first_season + rng.randint(2, 40), 1900)
    capacity = int(getattr(venue, "capacity", 0) or 0) or rng.randint(18000, 80000)
    stadium = str(getattr(venue, "name", "") or f"{school} Stadium")
    conference_since = rng.randint(max(first_season + 5, 1932), 2014)
    games = (season - first_season) * 10
    all_time = _record(rng, games, 0.38 + prestige * 0.3)
    titles = _years(rng, 1 + rng.randint(0, 2), first_season + 20, season - 2) if prestige > 0.8 else []
    conf_titles = _years(rng, int(prestige * 12) + rng.randint(0, 3), conference_since, season - 1)
    heismans = [f"{_name(rng)} ({y})" for y in _years(rng, rng.randint(1, 2), 1950, season - 3)] if prestige > 0.75 else []
    coach = getattr(team, "coach", None)
    hist = getattr(coach, "history", None) or {}
    wins, losses = (sum(w for w, _ in hist.values()), sum(lost for _, lost in hist.values())) if isinstance(hist, dict) else (0, 0)
    head_coach = f"{coach.first} {coach.last}, {wins}-{losses}, since {coach.hire_year}" if coach else None
    best_coach = _name(rng)
    best_from = rng.randint(first_season + 10, season - 30)
    best_wins = rng.randint(60, 90 + int(prestige * 100))
    streak = rng.randint(7, 12 + int(prestige * 20))
    streak_year = rng.randint(first_season + 10, season - 2)
    rival_rows = []
    for i, rival in enumerate(rivals[:2]):
        first = min(rng.randint(max(first_season, 1900), max(first_season, 1900) + 40), season - 10)
        rival_rows.append({"rival": rival.school, "trophy": rng.choice(TROPHIES) if i == 0 else None, "firstMeeting": first, "record": _record(rng, season - first - rng.randint(0, 6), 0.4 + prestige * 0.2)})
    crowd_rival = rivals[0].school if rivals else "the rival"
    crowd_year = rng.randint(min(max(opened, 1990), season - 1), season - 1)
    retired = [f"{_name(rng)} (No. {n})" for n in sorted(rng.sample(range(1, 90), rng.randint(0, 3)))]
    mascot_name = f"{rng.choice(MASCOT_HEADS)} {rng.choice(N.LAST_NAMES)}"
    mascot_year = rng.randint(first_season, min(first_season + 40, season - 10))
    dates = [
        {"date": f"{founded}-09-{rng.randint(10, 28):02d}", "event": f"{school} opens its doors."},
        {"date": f"{first_season}-10-{rng.randint(1, 28):02d}", "event": f"The first football game, against {crowd_rival}."},
        {"date": f"{opened}-09-{rng.randint(1, 28):02d}", "event": f"{stadium} opens."},
        {"date": f"{conference_since}-07-01", "event": f"{school} joins the {team.conference}."},
        {"date": f"{mascot_year}-11-{rng.randint(1, 28):02d}", "event": f"{mascot_name} walks the sideline for the first time."},
    ]
    if titles:
        dates.append({"date": f"{titles[-1] + 1}-01-{rng.randint(1, 9):02d}", "event": f"The {titles[-1]} season ends with the national title."})
    return {
        "founded": founded,
        "stadium": stadium,
        "stadiumNickname": rng.choice(NICKNAMES) if rng.random() < 0.35 else None,
        "stadiumOpened": opened,
        "capacity": capacity,
        "conferenceSince": conference_since,
        "firstSeason": first_season,
        "allTimeRecord": all_time,
        "nationalTitles": titles,
        "conferenceTitles": len(conf_titles),
        "conferenceTitleYears": conf_titles,
        "heismans": heismans,
        "bowlRecord": f"{rng.randint(2, 20)}-{rng.randint(2, 20)}",
        "rivalries": rival_rows,
        "headCoachRecord": head_coach,
        "winningestCoach": f"{best_coach}, {best_wins} wins ({best_from} to {best_from + rng.randint(8, 22)})",
        "longestWinStreak": f"{streak} games ({streak_year} to {streak_year + 1})",
        "recordCrowd": f"{capacity + rng.randint(300, 4000):,} vs {crowd_rival}, {crowd_year}-{rng.randint(9, 11):02d}-{rng.randint(1, 28):02d}",
        "retiredNumbers": retired,
        "mascotName": mascot_name,
        "mascotOrigin": f"The {mascot} name dates from {rng.randint(founded, first_season + 5)}; the costumed {mascot_name} arrived in {mascot_year}.",
        "colorsOrigin": f"The colors were {rng.choice(COLOR_STORIES).format(founded=founded)}.",
        "fightSong": rng.choice(SONGS).format(school=school, mascot=mascot),
        "traditions": rng.sample(TRADITIONS, 2),
        "nflAlumni": [_name(rng) for _ in range(rng.randint(0, 3))],
        "dates": dates,
    }


def league_facts(league: Any, season: int | None = None) -> dict[str, dict[str, Any]]:
    """A facts row per FBS team of the league, keyed by school, each with its conference and the demo's own stamp."""
    year = int(season or getattr(league, "season", 0) or datetime.now(timezone.utc).year)
    teams = [t for t in getattr(league, "by_school", {}).values() if getattr(t, "is_fbs", False)]
    by_conference: dict[str, list[Any]] = {}
    for team in sorted(teams, key=lambda t: t.id):
        by_conference.setdefault(team.conference, []).append(team)
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: dict[str, dict[str, Any]] = {}
    for conference, members in by_conference.items():
        for i, team in enumerate(members):
            rivals = [members[(i + k) % len(members)] for k in (1, 2) if len(members) > k]
            row = team_facts(team, rivals, year)
            out[team.school] = {**row, "conference": conference, "savedAt": when, "checkedAt": when, "sources": [{"label": "The league's record book", "url": f"https://demo.invalid/{team.abbr.lower()}/history"}]}
    return out


def write_demo_facts(data_dir: Path, league: Any, season: int | None = None) -> Path | None:
    """data/facts.json for a demo install, written once (an install that loaded its own facts keeps them)."""
    path = Path(data_dir) / "facts.json"
    if path.exists():
        return None
    rows = league_facts(league, season)
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batches = {}
    for row in rows.values():
        batches.setdefault(row["conference"], {"savedAt": when, "teams": 0, "of": 0, "author": "the demo"})
        batches[row["conference"]]["teams"] += 1
        batches[row["conference"]]["of"] += 1
    try:
        atomic_write(path, json.dumps({"teams": rows, "batches": batches, "marks": {}}, indent=1, ensure_ascii=False) + "\n")
    except OSError:
        log.warning("The demo's school facts could not be written to %s", path, exc_info=True)
        return None
    return path
