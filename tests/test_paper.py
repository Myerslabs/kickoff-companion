"""Phase 17 #26: the newspaper's season of headlines in game weeks (app/services/paper.py) and the season's
archive (app/feeds.py SeasonArchive). No network: hand-made headlines, games and rosters."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.cfbd.models import Game, RosterPlayer
from app.feeds import FeedResult, FeedSpec, Headline, SeasonArchive
from app.services.paper import named_players, paper_weeks, topic_of

UTC = timezone.utc


def game(gid: int, week: int, start: str, home: str, away: str, **extra) -> Game:
    return Game.model_validate({"id": gid, "season": 2026, "week": week, "seasonType": "regular", "startDate": start, "homeTeam": home, "awayTeam": away, **extra})


def player(pid: int, first: str, last: str, team: str) -> RosterPlayer:
    return RosterPlayer.model_validate({"id": str(pid), "firstName": first, "lastName": last, "team": team})


GAMES = [
    game(1, 1, "2026-09-05T23:00:00Z", "Swampwater Tech", "Rhubarb State"),
    game(2, 2, "2026-09-12T19:30:00Z", "Silver Dollar", "Swampwater Tech"),
    game(3, 3, "2026-09-19T16:00:00Z", "Swampwater Tech", "Diner Tech", neutralSite=True),
    game(9, 3, "2026-09-19T16:00:00Z", "Other U", "Elsewhere"),  # not ours: never a section
]
ROSTERS = [
    ("Swampwater Tech", [player(11, "Jadan", "Quillfeather", "Swampwater Tech"), player(12, "Sam", "Brown", "Swampwater Tech"), player(13, "Lee", "Ostrander", "Swampwater Tech")]),
    ("Diner Tech", [player(21, "Cal", "Ostrander", "Diner Tech"), player(22, "Rex", "Vantablack", "Diner Tech")]),
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
    assert [p["team"] for p in named_players("Vantablack and Quillfeather headline the week", ROSTERS)] == ["Swampwater Tech", "Diner Tech"]
    assert named_players(None, ROSTERS) == [] and named_players("Quillfeather", []) == []


def test_weeks_group_the_season_by_game_newest_first():
    headlines = [
        h("Preview of the opener", "2026-09-01T12:00:00Z"),           # before the first game: week 1
        h("Opener recap: a big win", "2026-09-06T08:00:00Z"),          # within 12 h of game 1: still week 1
        h("Looking ahead to Silver Dollar", "2026-09-07T15:00:00Z"),   # the morning after: week 2
        h("Diner Tech week: Vantablack is the key", "2026-09-17T10:00:00Z"),
        h("Season over: what's next", "2026-12-01T10:00:00Z"),         # after the last game
        h("No date on this one", None),                                 # no time: the latest week
        {"title": None}, "junk",
    ]
    weeks = paper_weeks(headlines, GAMES, "Swampwater Tech", tz=UTC, rosters=ROSTERS)
    assert [w["label"] for w in weeks] == ["After the season", "Week 3 · vs Diner Tech", "Week 2 · at Silver Dollar", "Week 1 · vs Rhubarb State"]
    by = {w["label"]: [x["title"] for x in w["headlines"]] for w in weeks}
    assert by["Week 1 · vs Rhubarb State"] == ["Opener recap: a big win", "Preview of the opener"]
    assert by["Week 2 · at Silver Dollar"] == ["Looking ahead to Silver Dollar"]
    assert "No date on this one" in by["Week 3 · vs Diner Tech"]
    diner = next(w for w in weeks if w["gameId"] == 3)
    assert diner["homeAway"] == "neutral" and diner["opponent"] == "Diner Tech"
    key = next(x for x in diner["headlines"] if x["title"].startswith("Diner Tech week"))
    assert key["players"][0]["name"] == "Rex Vantablack" and key["topic"] == "game"
    assert paper_weeks([], GAMES, "Swampwater Tech", tz=UTC) == []
    assert [w["label"] for w in paper_weeks([h("x", "2026-09-01T00:00:00Z")], [], "Swampwater Tech", tz=UTC)] == ["After the season"]


def test_season_archive_keeps_the_season_and_drops_old_ones(tmp_path: Path):
    (tmp_path / "feeds").mkdir()
    old = tmp_path / "feeds" / "season-2025.json"
    old.write_text(json.dumps({"season": 2025, "headlines": [h("Old news", "2025-10-01T00:00:00Z")]}), encoding="utf-8")
    spec = FeedSpec("espn", "ESPN", "https://example.com/rss", False)
    now = datetime(2026, 10, 7, tzinfo=UTC)
    first = FeedResult(spec, [Headline("Story one", "https://e/1", "ESPN", "espn", "2026-10-06T10:00:00Z"), Headline("Story one!", "https://e/1b", "ESPN", "espn", "2026-10-06T11:00:00Z")], now)
    archive = SeasonArchive(tmp_path)
    rows = archive.add(2026, [first])
    assert [r["title"] for r in rows] == ["Story one"], "the same story twice is kept once"
    assert not old.exists(), "a new season removes the old archive"
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
