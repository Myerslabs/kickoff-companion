"""What we need and the Post-Game Program on the server (F8 feature 1, owner 2026-10-21): the race in the Season overview
with the standings wearing it, the program carrying the race and the picture's line, the Top 25 page and the ticker
marking the games that help, the kickoff lock grown, the Post-Game lock (the poll after, the games as of a week, the
records, the news, the snapshot, the file), the housekeeping hook through the app, the route, and the front page on the
Post-Game until Monday."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.cfbd.models import PollWeek
from app.feeds import team_matcher
from app.services.postgame_lock import NEWS_LIMIT, PostgameLock, as_of, news_for, poll_after, records_after, snapshot_after
from app.services.program_lock import snapshot
from tests import league_facts as facts
from tests.conftest import CONFERENCE, TEAM
from tests.test_race import game as race_game
from tests.test_season_notes import league  # noqa: F401 - routes the fake CFBD
from tests.test_wave_b import NOW, PROGRAM

LAST_GAME = facts.last_game()["id"]


def poll(week: int, schools: list[tuple[int, str]], season_type: str = "regular") -> PollWeek:
    return PollWeek.model_validate({"season": 2026, "seasonType": season_type, "week": week, "polls": [{"poll": "AP Top 25", "ranks": [{"rank": r, "school": s} for r, s in schools]}]})


# --- the pages ----------------------------------------------------------------------------------------------------------------


def test_the_overview_carries_the_race_and_the_standings_wear_it(client, league):  # noqa: F811
    data = client.get("/api/season/overview").json()["data"]
    race = data["race"]
    assert race is not None and race["conference"] == CONFERENCE and race["us"]["team"] == TEAM and race["spots"] == 2
    assert race["standings"] and all({"team", "confWins", "confLosses", "left", "best", "status"} <= set(row) for row in race["standings"])
    statuses = {row["team"]: row["status"] for row in race["standings"]}
    assert data["standings"] and all(row["raceStatus"] == statuses.get(row["team"]) for row in data["standings"]), "the standings table wears each team's standing in the race"
    assert {line["key"] for line in race["lines"]} <= {"winOut", "allButOne", "next", "clinch"}
    assert all(isinstance(row.get("pullFor"), str) and row.get("why") for row in race["watch"])
    assert set(race["helps"]) == {row["gameId"] for row in race["watch"]}


def test_the_program_carries_the_race_the_picture_and_the_lock_flags(client, league):  # noqa: F811
    data = client.get("/api/program/next").json()["data"]
    race = data["race"]
    assert race is not None and race["us"]["team"] == TEAM and len(race["standings"]) <= 6 and isinstance(race["others"], int) and isinstance(race["outCount"], int)
    picture = data["picture"]
    assert picture is None or ("us" in picture and isinstance(picture["seeds"], list) and all({"seed", "school", "isUs"} <= set(s) for s in picture["seeds"]))
    assert data["game"]["postLocked"] is False
    assert client.get(f"/api/program/{data['game']['gameId']}/postgame").status_code == 404
    assert client.get("/api/program/x/postgame").status_code == 404 and client.get("/api/program/1234567890123/postgame").status_code == 404


def test_the_top25_page_and_the_ticker_mark_the_games_that_help(client, league):  # noqa: F811
    top = client.get("/api/top25").json()["data"]
    assert top["games"] and all("helps" in g for g in top["games"])
    for g in top["games"]:
        if g["helps"] is not None:
            assert {"pullFor", "why", "ours"} <= set(g["helps"])
    tick = client.get("/api/ticker").json()["data"]
    assert all("helps" in g for g in tick["games"])


# --- the kickoff lock grown ------------------------------------------------------------------------------------------------


def test_the_kickoff_snapshot_keeps_the_ranks_the_race_the_headlines_and_the_program():
    data = {**PROGRAM, "race": {"us": {"team": TEAM}, "lines": []}, "picture": {"us": {"seed": 10}}, "us": {**PROGRAM["us"], "cfpRank": 9, "conferenceRecord": {"wins": 3, "losses": 0}}, "parts": {"x": 1}, "picker": [1]}
    snap = snapshot(data, NOW, headlines=[{"title": "A"}, {"title": "B"}, "junk", {"no": "title"}] + [{"title": f"H{i}"} for i in range(10)])
    assert snap["format"] == 2
    assert snap["ranks"] == {"us": {"ap": 5, "cfp": 9}, "them": {"ap": None, "cfp": None}}
    assert snap["records"]["us"] == {"total": {"wins": 4}, "conference": {"wins": 3, "losses": 0}}
    assert snap["race"]["us"]["team"] == TEAM and snap["picture"]["us"]["seed"] == 10
    assert [h["title"] for h in snap["headlines"]] == ["A", "B", "H0", "H1", "H2", "H3", "H4", "H5"], "eight headlines, junk dropped"
    assert "parts" not in snap["program"] and "picker" not in snap["program"] and "final" not in snap["program"] and snap["program"]["line"]["spread"] == -7.5
    assert snap["us"] == {"school": TEAM, "abbreviation": "US", "mascot": "Us", "apRank": 5, "record": {"wins": 4}}, "the results band's slice is as it was"
    assert snapshot("junk", NOW)["ranks"] == {"us": {"ap": None, "cfp": None}, "them": {"ap": None, "cfp": None}} and snapshot("junk", NOW)["headlines"] == []


# --- the Post-Game lock -------------------------------------------------------------------------------------------------------


def test_the_poll_after_a_game_is_the_next_weeks():
    weeks = [poll(9, [(1, "A"), (7, "Diner")]), poll(10, [(1, "A"), (19, "Diner"), (8, "Swamp")]), poll(1, [(1, "A")], "postseason")]
    g = race_game(1, 9, "Diner", "Swamp", 24, 31)
    assert poll_after(weeks, g) == (10, {"AP": {"A": 1, "Diner": 19, "Swamp": 8}})
    assert poll_after(weeks, race_game(2, 10, "A", "B", 1, 0)) == (None, {}), "the poll after week 10 is not out"
    assert poll_after(weeks, race_game(3, 1, "A", "B", 1, 0, season_type="postseason")) == (1, {"AP": {"A": 1}}), "a bowl game takes the final poll"
    assert poll_after([], g) == (None, {})


def test_the_games_as_of_a_week_and_the_records_after_it():
    games = [race_game(1, 8, "A", "B", 20, 10), race_game(2, 9, "A", "C", 7, 3), race_game(3, 10, "B", "C", 14, 7), race_game(4, 11, "A", "B"), race_game(5, 1, "A", "C", 9, 8, season_type="postseason")]
    upto = as_of(games, 9)
    assert [g.completed for g in upto] == [True, True, False, False, False] and upto[2].home_points is None and upto[2].id == 3
    assert games[2].completed is True, "the season's own list is untouched"
    after = records_after(games, 9)
    assert after == {"A": {"wins": 2, "losses": 0, "confWins": 2, "confLosses": 0}, "B": {"wins": 0, "losses": 1, "confWins": 0, "confLosses": 1}, "C": {"wins": 0, "losses": 1, "confWins": 0, "confLosses": 1}}
    assert records_after(games, 10)["B"] == {"wins": 1, "losses": 1, "confWins": 1, "confLosses": 1}
    assert records_after([race_game(6, 2, "A", "B", 10, 10)], 5) == {}, "a tie counts for nobody"


def test_the_news_about_the_game_is_picked_by_name_and_date():
    kickoff = datetime(2026, 10, 24, 19, 30, tzinfo=timezone.utc)
    items = [
        {"title": "Mudpuppies hold off Diner Tech", "url": "https://x/1", "source": "Gazette", "publishedAt": "2026-10-25T03:08:00Z"},
        {"title": "Swampwater Tech climbs to second", "url": "https://x/2", "source": "Belt Report", "publishedAt": "2026-10-25T13:30:00Z"},
        {"title": "Diner Tech falls at home", "url": None, "source": "Herald", "publishedAt": "2026-10-25T03:40:00Z"},
        {"title": "Mudpuppies hold off Diner Tech", "url": "https://x/dup", "source": "Other", "publishedAt": "2026-10-25T04:00:00Z"},
        {"title": "Swampwater Tech preview: what to watch", "url": "https://x/old", "source": "Gazette", "publishedAt": "2026-10-23T12:00:00Z"},
        {"title": "Swampwater Tech a week later", "url": "https://x/late", "source": "Gazette", "publishedAt": "2026-10-30T12:00:00Z"},
        {"title": "Somebody else wins", "url": "https://x/other", "source": "Gazette", "publishedAt": "2026-10-25T05:00:00Z"},
        {"title": "No date at all", "url": "https://x/nd", "source": "Gazette", "publishedAt": None},
        "junk",
    ]
    us = team_matcher("Swampwater Tech", "Mudpuppies")
    them = team_matcher("Diner Tech", "Griddles")
    picked = news_for(items, us, them, kickoff)
    assert [h["title"] for h in picked] == ["Swampwater Tech climbs to second", "Diner Tech falls at home", "Mudpuppies hold off Diner Tech"], "newest first, the window kept, the duplicate dropped, the stranger left out"
    assert picked[1]["url"] is None and picked[2]["source"] == "Gazette" and picked[0]["publishedAt"] == "2026-10-25T13:30:00Z"
    assert news_for(items, us, None, None) == []
    many = [{"title": f"Swampwater Tech item {i}", "url": None, "source": "s", "publishedAt": f"2026-10-25T{i:02d}:00:00Z"} for i in range(12)]
    assert len(news_for(many, us, None, kickoff)) == NEWS_LIMIT


def test_the_snapshot_after_and_the_lock_file(tmp_path: Path):
    data = {**PROGRAM, "game": {**PROGRAM["game"], "completed": True, "usPoints": 31, "themPoints": 24, "week": 9}, "profile": {"us": [{"key": "ppg", "value": 29.6}], "them": [{"key": "ppg", "value": 32.1}]}, "parts": {"x": 1}, "picker": [1]}
    ranks = {"AP": {TEAM: 8, "Them U": 19}, "CFP": {TEAM: 7}}
    records = {TEAM: {"wins": 7, "losses": 2, "confWins": 5, "confLosses": 1}, "Them U": {"wins": 6, "losses": 3, "confWins": 4, "confLosses": 2}}
    snap = snapshot_after(data, NOW, poll_week=10, ranks=ranks, records=records, race={"us": {"team": TEAM}}, picture={"us": {"seed": 8}}, news=[{"title": "N"}], backfilled=False)
    assert snap["format"] == 1 and snap["gameId"] == 77 and snap["week"] == 9 and snap["pollWeek"] == 10 and snap["backfilled"] is False and snap["lockedAt"] == "2026-10-10T19:31:00Z"
    assert snap["final"] == {"usPoints": 31, "themPoints": 24}
    assert snap["us"]["apRank"] == 8 and snap["us"]["cfpRank"] == 7 and snap["us"]["record"] == {"wins": 7, "losses": 2} and snap["us"]["conferenceRecord"] == {"wins": 5, "losses": 1}
    assert snap["them"]["apRank"] == 19 and snap["them"]["cfpRank"] is None and snap["them"]["record"] == {"wins": 6, "losses": 3}
    assert snap["profile"] == {"us": [{"key": "ppg", "value": 29.6}], "them": [{"key": "ppg", "value": 32.1}]} and snap["news"] == [{"title": "N"}]
    assert "parts" not in snap["program"] and "picker" not in snap["program"] and snap["program"]["us"]["apRank"] == 8 and snap["program"]["race"] == {"us": {"team": TEAM}} and snap["program"]["picture"] == {"us": {"seed": 8}}
    assert snapshot_after(data, NOW, poll_week=10, ranks=ranks, records={}, race=None, picture=None, news=[], backfilled=True)["profile"] is None, "a back-fill has no season numbers of that day"
    assert snapshot_after("junk", NOW, poll_week=None, ranks={}, records={}, race=None, picture=None, news=[], backfilled=True)["gameId"] is None
    lock = PostgameLock(tmp_path / "data", 2026)
    assert not lock.has(77) and lock.load(77) is None and lock.load("x") is None and not lock.has("x")
    assert lock.save(77, snap) is True and lock.has(77) and lock.load(77)["us"]["apRank"] == 8
    assert lock.save(77, {"gameId": 77}) is False and lock.load(77)["us"]["apRank"] == 8, "the first lock wins"
    lock.path(77).write_text("{broken", encoding="utf-8")
    assert lock.load(77) is None and lock.has(77)
    lock.path(78).write_text(json.dumps({"gameId": 1}), encoding="utf-8")
    assert lock.load(78) is None


def test_the_housekeeping_hook_writes_the_postgame_once_the_poll_is_out(client, league, app):  # noqa: F811
    hook = app.state.maintenance.lock_postgame
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    written = 0
    for _ in range(12):
        if not client.portal.call(hook, now):
            break
        written += 1
    assert written >= 1 and app.state.postgame_lock.has(LAST_GAME), "the last game's poll after is out: its Post-Game Program is kept"
    kept = client.get(f"/api/program/{LAST_GAME}/postgame").json()["data"]
    assert kept["gameId"] == LAST_GAME and kept["us"]["school"] == TEAM and isinstance(kept["news"], list) and isinstance(kept["pollWeek"], int)
    assert kept["race"] is not None and kept["race"]["us"]["team"] == TEAM and "program" in kept and kept["program"]["game"]["gameId"] == LAST_GAME
    assert isinstance(kept["backfilled"], bool) and (kept["profile"] is None) == kept["backfilled"]
    assert client.get(f"/api/program/{LAST_GAME}").json()["data"]["game"]["postLocked"] is True
    assert client.portal.call(hook, now) is False, "nothing left to lock"


# --- the front page on the Post-Game until Monday ---------------------------------------------------------------------------


def test_the_front_page_keeps_the_postgame_until_monday(app, client, league):  # noqa: F811
    program = app.state.program
    played = race_game(1, 9, "Diner", TEAM, 24, 31)  # Saturday Oct 24, 7:30 pm UTC
    played = played.model_copy(update={"start_date": "2026-10-24T19:30:00.000Z"})
    upcoming = race_game(2, 10, TEAM, "Bagel").model_copy(update={"start_date": "2026-10-31T19:30:00.000Z"})
    sunday = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)
    assert program.postgame_front(played, sunday) is True
    assert program.postgame_front(played, datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)) is True, "5 am Monday in the East: still the Post-Game"
    assert program.postgame_front(played, datetime(2026, 10, 26, 11, 0, tzinfo=timezone.utc)) is False, "7 am Monday: next week's Pre-Game"
    assert program.postgame_front(played, datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)) is False, "before kickoff"
    assert program.postgame_front(played.model_copy(update={"start_date": None}), sunday) is False
    app.state.cfbd._clock = lambda: sunday
    assert program._pick_game([upcoming, played], None) is played
    app.state.cfbd._clock = lambda: datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    assert program._pick_game([upcoming, played], None) is upcoming
    assert program._pick_game([upcoming, played], 1) is played and program._pick_game([played], None) is played
