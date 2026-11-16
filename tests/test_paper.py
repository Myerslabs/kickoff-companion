"""Phase 17 #26: the newspaper's season of headlines in game weeks (app/services/paper.py) and the season's
archive (app/feeds.py SeasonArchive). No network: hand-made headlines, games and rosters."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.cfbd.models import Game, RosterPlayer
from app.feeds import FeedResult, FeedSpec, Headline, SeasonArchive
from app.services.paper import about_game, final_of, named_players, paper_weeks, sunday_end, sunday_stories, topic_of

UTC = timezone.utc


def game(gid: int, week: int, start: str, home: str, away: str, **extra) -> Game:
    return Game.model_validate({"id": gid, "season": 2026, "week": week, "seasonType": "regular", "startDate": start, "homeTeam": home, "awayTeam": away, **extra})


def player(pid: int, first: str, last: str, team: str) -> RosterPlayer:
    return RosterPlayer.model_validate({"id": str(pid), "firstName": first, "lastName": last, "team": team})


GAMES = [
    game(1, 1, "2026-09-05T23:00:00Z", "Florida", "Akron"),
    game(2, 2, "2026-09-12T19:30:00Z", "Fresno State", "Florida"),
    game(3, 3, "2026-09-19T16:00:00Z", "Florida", "Texas State", neutralSite=True),
    game(9, 3, "2026-09-19T16:00:00Z", "Other U", "Elsewhere"),  # not ours: never a section
]
ROSTERS = [
    ("Florida", [player(11, "Jadan", "Quillfeather", "Florida"), player(12, "Sam", "Brown", "Florida"), player(13, "Lee", "Ostrander", "Florida")]),
    ("Texas State", [player(21, "Cal", "Ostrander", "Texas State"), player(22, "Rex", "Vantablack", "Texas State")]),
]


def h(title: str, when: str | None) -> dict:
    return {"title": title, "url": "https://example.com/a", "source": "Example", "feed": "espn", "publishedAt": when}


def test_topics():
    assert topic_of("Two starters questionable for Saturday") == "injury"
    assert topic_of("4-star OT sees the program in a different light") == "recruiting"
    assert topic_of("Storms in the forecast for kickoff") == "weather"
    assert topic_of("Former stars in the NFL: Week 4") == "nfl"
    assert topic_of("Basketball greats to serve as honorary captains") == "other-sport"
    assert topic_of("Head coach on what went wrong") == "coach"
    assert topic_of("Expert predictions for Saturday's game") == "game"
    assert topic_of(None) == "game" and topic_of("") == "game" and topic_of(7) == "game"


def test_named_players_full_name_or_a_unique_uncommon_last_name():
    assert [p["playerId"] for p in named_players("Jadan Quillfeather runs for 200", ROSTERS)] == ["11"]
    assert [p["playerId"] for p in named_players("Quillfeather apologizes after the loss", ROSTERS)] == ["11"]
    # a last name two players share needs the full name; an ordinary word never counts alone
    assert named_players("Ostrander out for the season", ROSTERS) == []
    assert [p["playerId"] for p in named_players("Cal Ostrander out for the season", ROSTERS)] == ["21"]
    assert named_players("Brown leads the way", ROSTERS) == []
    assert [p["team"] for p in named_players("Vantablack and Quillfeather headline the week", ROSTERS)] == ["Florida", "Texas State"]
    assert named_players(None, ROSTERS) == [] and named_players("Quillfeather", []) == []


def test_weeks_group_the_season_by_game_newest_first():
    headlines = [
        h("Preview of the opener", "2026-09-01T12:00:00Z"),           # before the first game: week 1
        h("Opener recap: a big win", "2026-09-06T08:00:00Z"),          # after the final, about the game: week 1's Sunday paper
        h("Looking ahead to Fresno State", "2026-09-07T15:00:00Z"),   # past 6 AM on the second morning: week 2
        h("Texas State week: Vantablack is the key", "2026-09-17T10:00:00Z"),
        h("Season over: what's next", "2026-12-01T10:00:00Z"),         # after the last game
        h("No date on this one", None),                                 # no time: the latest week
        {"title": None}, "junk",
    ]
    weeks = paper_weeks(headlines, GAMES, "Florida", tz=UTC, rosters=ROSTERS)
    assert [w["label"] for w in weeks] == ["After the season", "Week 3 · vs Texas State", "Week 2 · at Fresno State", "Week 1 · Sunday paper · vs Akron", "Week 1 · vs Akron"]
    by = {w["label"]: [x["title"] for x in w["headlines"]] for w in weeks}
    assert by["Week 1 · vs Akron"] == ["Preview of the opener"]
    assert by["Week 1 · Sunday paper · vs Akron"] == ["Opener recap: a big win"]
    assert by["Week 2 · at Fresno State"] == ["Looking ahead to Fresno State"]
    assert "No date on this one" in by["Week 3 · vs Texas State"]
    diner = next(w for w in weeks if w["gameId"] == 3)
    assert diner["homeAway"] == "neutral" and diner["opponent"] == "Texas State"
    key = next(x for x in diner["headlines"] if x["title"].startswith("Texas State week"))
    assert key["players"][0]["name"] == "Rex Vantablack" and key["topic"] == "game"
    assert paper_weeks([], GAMES, "Florida", tz=UTC) == []
    assert [w["label"] for w in paper_weeks([h("x", "2026-09-01T00:00:00Z")], [], "Florida", tz=UTC)] == ["After the season"]


def test_season_archive_keeps_the_season_and_the_old_ones(tmp_path: Path):
    (tmp_path / "feeds").mkdir()
    old = tmp_path / "feeds" / "season-2025.json"
    old.write_text(json.dumps({"season": 2025, "headlines": [h("Old news", "2025-10-01T00:00:00Z")]}), encoding="utf-8")
    spec = FeedSpec("espn", "ESPN", "https://example.com/rss", False)
    now = datetime(2026, 10, 7, tzinfo=UTC)
    first = FeedResult(spec, [Headline("Story one", "https://e/1", "ESPN", "espn", "2026-10-06T10:00:00Z"), Headline("Story one!", "https://e/1b", "ESPN", "espn", "2026-10-06T11:00:00Z")], now)
    archive = SeasonArchive(tmp_path)
    rows = archive.add(2026, [first])
    assert [r["title"] for r in rows] == ["Story one"], "the same story twice is kept once"
    assert old.exists(), "rollover R3 (2026-11-15): a past season's archive stays, its papers and the Seasons list read it"
    # the feed has moved on; the archive keeps what it saw, and a betting headline never gets in
    later = FeedResult(spec, [Headline("Story two", None, "ESPN", "espn", "2026-10-07T10:00:00Z"), Headline("Best bets for Saturday from DraftKings", None, "ESPN", "espn", "2026-10-07T11:00:00Z")], now)
    rows = archive.add(2026, [later])
    assert [r["title"] for r in rows] == ["Story two", "Story one"]
    again = SeasonArchive(tmp_path).load(2026)
    assert [r["title"] for r in again] == ["Story two", "Story one"], "read back from disk"
    (tmp_path / "feeds" / "season-2026.json").write_text("not json", encoding="utf-8")
    assert SeasonArchive(tmp_path).load(2026) == [], "an unreadable archive starts again"


def test_the_phase_19_topics():
    assert topic_of("Spring game gives the quarterback battle a first look") == "practice"
    assert topic_of("Bowl projections after a rivalry win") == "trophy"
    assert topic_of("Where the poll has the team after the AP Top 25 update") == "rankings"
    assert topic_of("Stadium renovation will add a new tailgate zone") == "stadium"
    assert topic_of("Home team survives a late comeback in a close game") == "scoreboard"
    assert topic_of("Two starters questionable for Saturday") == "injury", "the older topics still win first"
    assert topic_of("Head coach on what went wrong") == "coach"


EASTERN = ZoneInfo("America/New_York")


def test_the_sunday_paper_holds_only_the_game_and_gives_way_at_6_am():
    """Wave 6 (owner 2026-11-15): from the final to 6 AM on the second morning, only the stories about the game just played;
    a story in that window about anything else goes to the next week's paper."""
    headlines = [
        h("Opener preview", "2026-09-05T20:00:00Z"),                       # before kickoff: week 1
        h("Akron leads at the half", "2026-09-06T01:00:00Z"),              # during the game: week 1's paper
        h("Florida beats Akron 41-10", "2026-09-06T03:30:00Z"),            # after the final: the Sunday paper
        h("Head coach on the opener", "2026-09-06T15:00:00Z"),             # the coach: the Sunday paper
        h("Akron stadium crowd sets a record", "2026-09-06T16:00:00Z"),    # names the opponent: the Sunday paper
        h("Jadan Quillfeather's big night", "2026-09-06T17:00:00Z"),       # names one of ours: the Sunday paper
        h("Four-star prospect commits to Florida", "2026-09-06T18:00:00Z"),  # recruiting on Sunday: next week's
        h("Gators climb in the AP poll", "2026-09-06T19:00:00Z"),          # the new poll: next week's
        h("Fresno State week begins", "2026-09-07T11:00:00Z"),             # past 6 AM UTC Monday: week 2
    ]
    weeks = paper_weeks(headlines, GAMES, "Florida", tz=UTC, rosters=ROSTERS)
    by = {w["key"]: [x["title"] for x in w["headlines"]] for w in weeks}
    assert by["1"] == ["Akron leads at the half", "Opener preview"]
    assert by["1-sunday"] == ["Jadan Quillfeather's big night", "Akron stadium crowd sets a record", "Head coach on the opener", "Florida beats Akron 41-10"]
    assert by["2"] == ["Fresno State week begins", "Gators climb in the AP poll", "Four-star prospect commits to Florida"]
    sunday = next(w for w in weeks if w["key"] == "1-sunday")
    assert sunday["sunday"] is True and sunday["gameId"] == 1 and sunday["week"] == 1 and sunday["opponent"] == "Akron"
    assert sunday["from"] == "2026-09-06T02:30:00+00:00" and sunday["until"] == "2026-09-07T06:00:00+00:00"
    assert [w["key"] for w in weeks] == ["2", "1-sunday", "1"], "newest first, a Sunday paper over its week's"
    last = paper_weeks([h("Texas State recap: a win", "2026-09-20T10:00:00Z"), h("Basketball tips off", "2026-09-20T11:00:00Z")], GAMES, "Florida", tz=UTC)
    assert {w["key"]: [x["title"] for x in w["headlines"]] for w in last} == {"3-sunday": ["Texas State recap: a win"], "after": ["Basketball tips off"]}, "after the last game, the rest goes to after the season"


def test_the_sunday_paper_ends_at_6_am_on_the_second_morning_in_local_time():
    saturday_late = datetime(2026, 11, 15, 3, 30, tzinfo=UTC)  # Sat 10:30 PM EST, the final after midnight
    assert sunday_end(saturday_late, EASTERN) == datetime(2026, 11, 16, 6, 0, tzinfo=EASTERN), "Monday 6 AM"
    saturday_noon = datetime(2026, 11, 14, 17, 0, tzinfo=UTC)
    assert sunday_end(saturday_noon, EASTERN) == datetime(2026, 11, 16, 6, 0, tzinfo=EASTERN)
    thursday = datetime(2026, 11, 13, 0, 30, tzinfo=UTC)  # Thu 7:30 PM EST
    assert sunday_end(thursday, EASTERN) == datetime(2026, 11, 14, 6, 0, tzinfo=EASTERN), "a Thursday game: Saturday 6 AM"
    assert final_of(saturday_noon) == datetime(2026, 11, 14, 20, 30, tzinfo=UTC)


def test_about_the_game_and_one_games_sunday_stories():
    assert about_game({"title": "x", "topic": "scoreboard"}, None) and about_game({"title": "x", "topic": "injury"}, None)
    assert about_game({"title": "Why Kentucky's defense held", "topic": "rankings"}, "Kentucky"), "the opponent named"
    assert not about_game({"title": "Kentucky basketball opens", "topic": "recruiting"}, "Ole Miss")
    assert about_game({"title": "x", "topic": "practice", "players": [{"name": "A"}]}, None)
    assert not about_game({"title": "Florida climbs the poll", "topic": "rankings"}, "Akron")
    kickoff = datetime(2026, 9, 5, 23, 0, tzinfo=UTC)
    rows = [h("Florida beats Akron", "2026-09-06T03:00:00Z"), h("During the game", "2026-09-06T01:00:00Z"), h("Poll day", "2026-09-06T12:00:00Z"), h("Too late: Akron film", "2026-09-07T07:00:00Z"), "junk", {"title": 3}]
    assert [r["title"] for r in sunday_stories(rows, kickoff, "Akron", UTC)] == ["Florida beats Akron"]
    assert sunday_stories(rows, None, "Akron", UTC) == [] and sunday_stories("junk", kickoff, None, UTC) == []


def test_the_name_index_matches_the_old_rule_and_never_a_stale_roster():
    """Batch 1 (the review, 2026-11-16): the roster names worked out once give the same players as testing every name, a
    two-word last name in the plural included, and a roster list read again is never served an older one's index."""
    from app.cfbd.models import RosterPlayer
    from app.services.paper import named_players

    def player(pid: int, first: str, last: str) -> RosterPlayer:
        return RosterPlayer.model_validate({"id": str(pid), "firstName": first, "lastName": last, "team": "Florida"})

    roster = [player(1, "Tim", "Van Dyke"), player(2, "Ray", "O'Neal"), player(3, "Jo", "Smith-Jones"), player(4, "Al", "Brown")]
    found = lambda title, r: [p["playerId"] for p in named_players(title, [("Florida", r)])]  # noqa: E731
    assert found("The Van Dykes carry Florida", roster) == ["1"], "a two-word last name in the plural"
    assert found("Tim Van Dyke runs for 120", roster) == ["1"]
    assert found("Smith-Jones and the defense", roster) == ["3"]
    assert found("Brown leads the way", roster) == [], "an ordinary word alone is not a player"
    again = [player(9, "New", "Guy")] + roster[1:]  # a list read again, the same length
    assert found("New Guy starts", again) == ["9"], "never the index of another list"
