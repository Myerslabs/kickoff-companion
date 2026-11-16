"""The season rollover's third wave (owner 2026-11-15, "Build all of R3"; his answers: the off-season paper turns over Monday
morning, Claude edits it once a week, the season in review leads between the last game and the switch): a past season's
papers read only, every season's headlines kept, the papers frozen at the switch, the weekly off-season paper, Week 1's paper
from the opener's week, who leads, last season in brief and in the prompts. No network."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.cfbd.models import Game
from app.feeds import SeasonArchive
from app.services.claude_schedule import paper_slots
from app.services.editions import Editions, is_offseason, offseason_key
from app.services.last_season import last_season_text
from app.services.paper import game_week_start, paper_weeks
from app.services.past_paper import past_paper, with_season
from app.services.rankedweek import RankedWeekService
from app.services.stops import Checks, GameRow, Status, current_stop
from app.services.writing import Lessons

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]


def game(gid: int, start: datetime, completed: bool, home: str = "Florida", away: str = "Akron", week: int = 1, season_type: str = "regular") -> Game:
    return Game.model_validate({"id": gid, "season": start.year, "week": week, "seasonType": season_type, "startDate": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "completed": completed, "homeTeam": home, "awayTeam": away, "homePoints": 30 if completed else None, "awayPoints": 10 if completed else None})


def service() -> RankedWeekService:
    program = SimpleNamespace(settings=SimpleNamespace(tzinfo=ET, data_dir=Path(".")), team="Florida", year=2026)
    return RankedWeekService(program, SimpleNamespace(), SimpleNamespace())


def test_the_off_season_paper_turns_over_monday_morning_with_last_weeks_stories():
    rw = service()
    bowl = datetime(2026, 12, 30, 20, 0, tzinfo=ET)  # a Wednesday bowl: its Sunday paper runs to Friday 6 AM
    season = [game(1, datetime(2026, 9, 5, 19, 30, tzinfo=ET), True), game(2, bowl, True, week=1, season_type="postseason")]
    assert rw.offseason_window(season, datetime(2026, 12, 31, 9, tzinfo=ET)) is None, "the bowl's Sunday paper leads first"
    start, end, turn = rw.offseason_window(season, datetime(2027, 1, 2, 9, tzinfo=ET))
    assert start == datetime(2027, 1, 1, 6, tzinfo=ET) and end == datetime(2027, 1, 2, 9, tzinfo=ET), "the days since the season, until the first Monday"
    start, end, turn = rw.offseason_window(season, datetime(2027, 1, 13, 8, tzinfo=ET))
    assert (start, end, turn) == (datetime(2027, 1, 4, 6, tzinfo=ET), datetime(2027, 1, 11, 6, tzinfo=ET), datetime(2027, 1, 11, 6, tzinfo=ET)), "last Monday to Monday"
    assert offseason_key(turn) == f"offseason-{turn.date().isoformat()}" and is_offseason(offseason_key(turn)) and turn.weekday() == 0 and turn.hour == 6
    monday_early = rw.offseason_window(season, datetime(2027, 1, 18, 5, tzinfo=ET))
    assert monday_early[2] == datetime(2027, 1, 11, 6, tzinfo=ET), "before 6 AM on Monday the last week's paper stays"
    under_way = [game(1, datetime(2026, 9, 5, 19, 30, tzinfo=ET), True), game(3, datetime(2026, 9, 19, 19, 30, tzinfo=ET), False, week=3)]
    assert rw.offseason_window(under_way, datetime(2026, 9, 14, 9, tzinfo=ET)) is None, "a bye week is still the season"
    next_season = [game(10, datetime(2027, 9, 4, 19, 30, tzinfo=ET), False), game(11, datetime(2027, 9, 11, 19, 30, tzinfo=ET), False, week=2)]
    assert rw.offseason_window(next_season, datetime(2027, 2, 10, 9, tzinfo=ET)) is not None, "after the switch: the off-season paper"
    assert rw.offseason_window(next_season, datetime(2027, 8, 30, 7, tzinfo=ET)) is None, "the opener's week: Week 1's paper"


def test_week_1s_paper_starts_with_the_openers_week():
    opener = datetime(2027, 9, 4, 19, 30, tzinfo=ET)
    rows = [{"title": "Spring practice opens", "publishedAt": "2027-03-20T15:00:00Z"}, {"title": "Akron week begins", "publishedAt": "2027-08-31T15:00:00Z"}]
    sections = paper_weeks(rows, [game(10, opener, False)], "Florida", tz=ET)
    by = {s["label"].split(" · ")[0]: [h["title"] for h in s["headlines"]] for s in sections}
    assert by["Before the season"] == ["Spring practice opens"] and by["Week 1"] == ["Akron week begins"]
    assert game_week_start(opener, ET) == datetime(2027, 8, 30, 6, tzinfo=ET)


def test_claudes_editor_runs_once_a_week_in_the_off_season():
    wednesday = datetime(2027, 1, 13, 12, tzinfo=ET)
    weekly = paper_slots(wednesday, ET, weekly=True)
    assert [s.kind for s in weekly] == ["editor", "art"] and weekly[0].key == "editor:2027-01-11-07" and weekly[1].key == "art:2027-01-11-10"
    assert len(paper_slots(wednesday, ET)) == 10, "in season: the editor every two hours and the drawings twice"
    setup = (ROOT / "app" / "schedule_setup.py").read_text(encoding="utf-8")
    assert "offseason=paper_offseason" in setup and "state.rankedweek.offseason_window(schedule.records, now) is not None" in setup


def row(gid: int, kickoff: datetime, completed: bool, week: int = 1) -> GameRow:
    return GameRow(gid, week, kickoff, "Akron", "home", completed, 30 if completed else None, 10 if completed else None)


def test_the_season_in_review_leads_once_the_season_is_over_and_the_magazine_before_it_starts():
    kick = datetime(2026, 9, 5, 19, 30, tzinfo=ET)
    closed = lambda g: Status(post_locked=True, checks=Checks(final=True, poll=True))  # noqa: E731
    over = current_stop([row(1, kick, True)], kick + timedelta(days=60), closed)
    assert over["kind"] == "book" and over["href"] == "#review" and over["label"] == "Season in review"
    ahead = current_stop([row(10, datetime(2027, 9, 4, 19, 30, tzinfo=ET), False)], datetime(2027, 2, 10, tzinfo=ET), lambda g: Status())
    assert ahead["kind"] == "preseason" and ahead["href"] == "#preseason"
    opener_week = current_stop([row(10, datetime(2027, 9, 4, 19, 30, tzinfo=ET), False)], datetime(2027, 9, 3, 7, tzinfo=ET), lambda g: Status())
    assert opener_week["kind"] == "pre", "the opener's Pre-Game takes over when it opens, the Thursday before"
    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert '(kind === "book" || kind === "preseason") && window.location.hash === "#program"' in app_js and "landHome = true;" in app_js


def test_every_seasons_headlines_stay(tmp_path: Path):
    feeds = tmp_path / "feeds"
    feeds.mkdir()
    (feeds / "season-2026.json").write_text(json.dumps({"season": 2026, "headlines": [{"title": "Bowl win", "publishedAt": "2027-01-02T00:00:00Z"}]}), encoding="utf-8")
    archive = SeasonArchive(tmp_path)
    archive.add(2027, [SimpleNamespace(headlines=[SimpleNamespace(title="Spring game set", source="X", url="https://example.com/a", as_dict=lambda: {"title": "Spring game set", "url": "https://example.com/a", "source": "X", "feed": "", "publishedAt": "2027-03-01T00:00:00Z"})])])
    assert (feeds / "season-2026.json").is_file() and (feeds / "season-2027.json").is_file(), "the switch no longer deletes last season's headlines"


def edition(key: str, week: int | None, headlines: list[dict], **extra) -> dict:
    return {"key": key, "label": key, "week": week, "seasonType": "regular", "gameId": 9001, "opponent": "Akron", "homeAway": "home", "date": "2025-09-06T23:30:00Z", "headlines": headlines, "matchups": [], "offThisWeek": [], "frozen": True, **extra}


def test_a_past_seasons_paper_is_read_from_its_own_files_alone(tmp_path: Path):
    store = Editions(tmp_path, 2025)
    store.save(edition("week-1", 1, [{"title": "Florida rolls", "url": "https://example.com/1", "source": "A", "publishedAt": "2025-09-03T12:00:00Z"}]), force=True)
    store.save(edition("week-1-sunday", 1, []), force=True)
    paper = past_paper(tmp_path, 2025, "Florida")
    assert paper["past"] == 2025 and [e["key"] for e in paper["editions"]] == ["week-1", "week-1-sunday"]
    assert paper["edition"]["key"] == "week-1-sunday", "no week asked: the season's last paper"
    week1 = past_paper(tmp_path, 2025, "Florida", "week-1")["edition"]
    assert [h["title"] for h in week1["headlines"]] == ["Florida rolls"] and isinstance(week1["layout"], dict) and week1["past"] == 2025
    assert past_paper(tmp_path, 2025, "Florida", "week-5")["edition"] is None, "a week never kept is none, never another week"
    assert not (tmp_path / "season" / "2025" / "paper" / "layout-week-1.json").exists(), "read only: no layout written"
    assert with_season({"front": {"picture": {"src": "/media/paper-art/abc.svg"}}, "x": [{"src": "/media/paper/p.jpg"}]}, 2025) == {"front": {"picture": {"src": "/media/paper-art/abc.svg?season=2025"}}, "x": [{"src": "/media/paper/p.jpg"}]}


def test_the_past_paper_routes(app, client):
    data_dir = Path(app.state.settings.data_dir)
    Editions(data_dir, 2025).save(edition("week-2", 2, []), force=True)
    answer = client.get("/api/seasons/2025/paper?edition=week-2").json()
    assert answer["data"]["edition"]["key"] == "week-2" and answer["meta"]["source"] == "cache"
    assert client.get("/api/seasons/2024/paper").json()["errors"][0]["code"] == "not_kept"
    assert client.get("/api/seasons/2026/paper").json()["errors"][0]["code"] == "current_season"
    assert client.get("/api/paper/story/0123456789abcdef?season=2025").status_code == 404
    assert client.get("/media/paper-art/0123456789abcdef.svg?season=2025").status_code == 404


def test_the_switch_freezes_the_seasons_last_papers(app, client):
    rw = app.state.rankedweek
    rw.editions.save(edition("postseason", 1, [], frozen=False, seasonType="postseason"))
    assert rw.editions.load("postseason")["frozen"] is False
    assert "postseason" in rw.freeze_season([])
    assert rw.editions.load("postseason")["frozen"] is True
    setup = (ROOT / "app" / "rollover_setup.py").read_text(encoding="utf-8")
    assert "await keep_book(app, season)\n        await freeze_papers(app)" in setup


def test_last_season_feeds_the_new_seasons_prompts(tmp_path: Path):
    assert last_season_text(tmp_path, 2027) == "", "nothing kept: nothing added"
    book = tmp_path / "season" / "2026" / "book"
    book.mkdir(parents=True)
    overview = {"team": {"school": "Florida", "conferenceShort": "SEC"}, "record": {"overall": {"wins": 9, "losses": 4}, "conference": {"wins": 5, "losses": 3}, "apRank": 18}, "ratings": {"sp": {"rank": 15}},
                "schedule": [{"week": 1, "completed": True, "result": "W", "usPoints": 59, "themPoints": 13, "opponent": {"school": "Akron"}}, {"week": 2, "completed": False, "opponent": {"school": "X"}}]}
    (book / "overview.json").write_text(json.dumps({"keptAt": "2027-01-21T16:00:00Z", "envelope": {"data": overview}}), encoding="utf-8")
    Lessons(tmp_path, 2026).add_review(1, {"lessons": ["Trust the SEC's availability report over beat writers."]})
    text = last_season_text(tmp_path, 2027)
    assert "## Last season (2026), for context only" in text and "Final record 9-4 (5-3 SEC); AP No. 18, SP+ #15." in text
    assert "- Week 1: W 59-13 vs Akron" in text and "vs X" not in text and "Trust the SEC's availability report" in text
    api = (ROOT / "app" / "api" / "season_notes.py").read_text(encoding="utf-8")
    assert api.count("+ last_season_text(data_dir, season)") == 2, "the season load's and the preseason prompts"


def test_the_pages_read_r3s_addresses():
    paper = (ROOT / "static" / "js" / "views" / "newspaper.js").read_text(encoding="utf-8")
    assert "`/api/seasons/${past}/paper" in paper and "linkSeason ? `#story=${s.id}?season=${linkSeason}`" in paper and "edition.offseason ? offseasonLine(data, edition) : null" in paper
    reader = (ROOT / "static" / "js" / "views" / "reader.js").read_text(encoding="utf-8")
    assert "`/api/paper/story/${sid}?season=${SEASON}`" in reader
    magazine = (ROOT / "static" / "js" / "views" / "preseason.js").read_text(encoding="utf-8")
    assert "lastSeasonBrief(data.season)" in magazine and "`/api/seasons/${year}/book/overview`" in magazine
    season = (ROOT / "static" / "js" / "views" / "season.js").read_text(encoding="utf-8")
    assert "pastSeason ? pastPapersBand(pastSeason) : null" in season
