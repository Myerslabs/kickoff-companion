"""The season line's Wave 6, first half (owner 2026-11-15): the Sunday paper after each game, from the final to 6 AM on
the second morning, with only the game's stories; the paper three pages at most, copied stories first; the edition keys, the folded weeks and the reader's store for the Sunday papers;
the editor told; and The game in the news reading the Sunday paper. No network: games and stories are made up here."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.cfbd.models import Game
from app.services.editions import KEY, Editions, is_sunday, key_for, label_for, order_of, week_key
from app.services.paper_layout import PER_PAGE, LayoutStore, folded_weeks, layout
from app.services.postgame_lock import news_for
from app.services.rankedweek import RankedWeekService
from app.services.writing import KINDS
from tests.test_feat14_layout import story

ET = ZoneInfo("America/New_York")
UTC = timezone.utc


# --- the edition keys -------------------------------------------------------------------------------------------------


def test_a_sunday_paper_has_its_own_key_label_and_place():
    assert key_for(11, "regular", sunday=True) == "week-11-sunday" and key_for(11, "regular") == "week-11"
    assert key_for(1, "postseason", sunday=True) == "postseason-sunday" and key_for(None, "regular", sunday=True) is None
    assert label_for("week-11-sunday") == "Week 11 · Sunday paper" and label_for("postseason-sunday") == "Bowl season · Sunday paper" and label_for("week-11") == "Week 11"
    assert label_for("week-11-monday") == "This week"
    keys = ["postseason-sunday", "week-12", "week-3-sunday", "postseason", "week-3", "week-11-sunday", "week-11", "nonsense"]
    assert sorted(keys, key=order_of) == ["week-3", "week-3-sunday", "week-11", "week-11-sunday", "week-12", "postseason", "postseason-sunday", "nonsense"]
    assert is_sunday("week-3-sunday") and not is_sunday("week-3") and not is_sunday("sunday") and not is_sunday(None)
    assert week_key("week-3-sunday") == "week-3" and week_key("postseason") == "postseason" and week_key("../x") is None
    for bad in ("week-3-sunday-sunday", "week-100", "week-3sunday", "postseason-", "-sunday"):
        assert not KEY.match(bad), bad


def test_a_sunday_paper_is_saved_listed_and_frozen_like_any_edition(tmp_path: Path):
    editions = Editions(tmp_path, 2026)
    for key, week in (("week-3", 3), ("week-3-sunday", 3), ("week-4", 4)):
        editions.save({"key": key, "week": week, "seasonType": "regular", "headlines": [], "matchups": [], "frozen": False})
    assert [e["key"] for e in editions.keys()] == ["week-3", "week-3-sunday", "week-4"]
    assert editions.keys()[1]["label"] == "Week 3 · Sunday paper"
    assert editions.load("week-3-sunday")["key"] == "week-3-sunday" and editions.load("week-3-sundae") is None


# --- three pages at most, copied stories first --------------------------------------------------------------------------


def test_the_paper_is_three_pages_and_the_headline_only_stories_go_first():
    copied = [story(n, copied=True, photo=n % 2 == 0, hours=n) for n in range(1, 13)]
    headline_only = [story(n, topic="recruiting", hours=n) for n in range(13, 110)]
    built = layout(copied + headline_only)
    assert len(built["more"]) == 1 and built["more"][0]["page"] == 3 and built["more"][0]["count"] == PER_PAGE, "page 3 is the last, full"
    placed = set(built["order"])
    assert {s["id"] for s in copied} <= placed, "every copied story is in the paper"
    assert built["left"] == len(copied) + len(headline_only) - len(placed) > 0
    assert set(built["stories"]) == placed, "the paper's stories are the placed ones"
    assert built["count"] == len(placed)
    inside = built["front"]["inside"][-1]
    assert inside["page"] == 3 and inside["words"] == f"{PER_PAGE} more of the week's stories"


def test_page_3_takes_the_copied_stories_before_any_headline_only_one():
    copied = [story(n, copied=True, hours=n) for n in range(1, 41)]  # more copied than the pages hold
    headline_only = [story(n, topic="injury", hours=n) for n in range(41, 61)]
    built = layout(copied + headline_only)
    page3 = [item["id"] for column in built["more"][0]["columns"] for item in column if "id" in item]
    assert len(page3) == PER_PAGE
    by_id = {s["id"]: s for s in copied + headline_only}
    assert all(by_id[i]["copied"] for i in page3), "page 3 holds copied stories while there are any"
    left_ids = {s["id"] for s in copied + headline_only} - set(built["order"])
    assert any(not by_id[i]["copied"] for i in left_ids), "the headline-only stories are the first out"


def test_a_short_week_keeps_every_story():
    built = layout([story(n, copied=n < 3, hours=n) for n in range(1, 15)])
    assert built["left"] == 0 and built["count"] == 14 and len(built["more"]) <= 1
    empty = layout([])
    assert empty["left"] == 0 and empty["more"] == [] and empty["count"] == 0


# --- when the Sunday paper leads ----------------------------------------------------------------------------------------


def game(gid: int, week: int, start: str, *, completed: bool = True, home: str = "Kentucky", away: str = "Florida") -> Game:
    return Game.model_validate({"id": gid, "season": 2026, "week": week, "seasonType": "regular", "startDate": start, "homeTeam": home, "awayTeam": away, "completed": completed})


def leads(games: list[Game], now: datetime):
    fake = SimpleNamespace(program=SimpleNamespace(settings=SimpleNamespace(tzinfo=ET)), team="Florida")
    return RankedWeekService._sunday_now(fake, games, now)


KENTUCKY = game(401856884, 11, "2026-11-14T23:15:00Z")  # Sat 6:15 PM EST
EARLIER = game(401856739, 10, "2026-11-07T20:00:00Z")
NEXT = game(401856900, 12, "2026-11-21T17:00:00Z", completed=False, home="Florida", away="Tennessee")


def test_the_sunday_paper_leads_from_the_final_to_6_am_monday():
    season = [EARLIER, KENTUCKY, NEXT]
    assert leads(season, datetime(2026, 11, 15, 3, 0, tzinfo=UTC)) is KENTUCKY, "Saturday night after the final"
    assert leads(season, datetime(2026, 11, 15, 15, 0, tzinfo=UTC)) is KENTUCKY, "Sunday"
    assert leads(season, datetime(2026, 11, 16, 10, 59, tzinfo=UTC)) is KENTUCKY, "Monday 5:59 AM EST"
    assert leads(season, datetime(2026, 11, 16, 11, 1, tzinfo=UTC)) is None, "Monday 6:01 AM: the new week"
    playing = [EARLIER, game(401856884, 11, "2026-11-14T23:15:00Z", completed=False), NEXT]
    assert leads(playing, datetime(2026, 11, 15, 1, 0, tzinfo=UTC)) is None, "until CFBD calls it final, the week's paper"
    assert leads([NEXT], datetime(2026, 11, 22, 3, 0, tzinfo=UTC)) is None, "a game not completed never has a Sunday paper"
    assert leads([game(5, 11, "2026-11-14T23:15:00Z", home="Ohio State", away="Michigan")], datetime(2026, 11, 15, 3, 0, tzinfo=UTC)) is None, "not our game"
    assert leads([], datetime(2026, 11, 15, 3, 0, tzinfo=UTC)) is None and leads(season, None) is None
    assert leads(["junk", None, EARLIER], datetime(2026, 11, 8, 12, 0, tzinfo=UTC)) is EARLIER


def test_the_sunday_paper_never_stays_past_6_am():
    season = [EARLIER, KENTUCKY, NEXT]
    assert leads(season, datetime(2026, 11, 16, 16, 59, tzinfo=UTC)) is None, "Monday 11:59 AM EST: the new week's paper"


# --- the folded weeks and the reader's store ------------------------------------------------------------------------------


def test_a_sunday_paper_folds_over_its_weeks_paper_with_its_own_lead():
    games = [SimpleNamespace(id=1, week=3, season_type="regular", start_date="2026-09-19T16:00:00Z", home_team="Florida", away_team="Akron", completed=True, home_points=41, away_points=10)]
    editions = [
        {"key": "week-3", "week": 3, "label": "Week 3", "saved": True},
        {"key": "week-3-sunday", "week": 3, "label": "Week 3 · Sunday paper", "saved": True},
        {"key": "week-4", "week": 4, "current": True},
    ]
    rows = folded_weeks(editions, games, "Florida", "week-4", tz=ET, leads={"week-3-sunday": "Florida rolls past Akron", "week-3": "Akron week"})
    assert [r["key"] for r in rows] == ["week-3-sunday", "week-3"]
    sunday, week = rows
    assert sunday["sunday"] is True and sunday["lead"] == "Florida rolls past Akron" and sunday["final"] == "Florida 41, Akron 10"
    assert week["sunday"] is False and week["lead"] == "Florida 41, Akron 10", "a week's paper by its final, as before"
    assert sunday["weekOf"] == week["weekOf"]


def test_the_readers_store_knows_the_sunday_papers(tmp_path: Path):
    store = LayoutStore(tmp_path, 2026)
    store.save("week-11", {"order": ["a"], "stories": {"a": {"title": "A"}}})
    store.save("week-11-sunday", {"order": ["b", "c"], "stories": {"b": {"title": "B"}, "c": {"title": "C"}}})
    store.save("postseason-sunday", {"order": ["d"], "stories": {}})
    store.save("week-11-sundae", {"order": ["x"], "stories": {}})
    assert store.keys() == ["postseason-sunday", "week-11-sunday", "week-11"]
    place = store.place("c")
    assert place["key"] == "week-11-sunday" and place["label"] == "Week 11 · Sunday paper" and place["position"] == 2 and place["prev"]["id"] == "b"


# --- the editor and the Post-Game's news ---------------------------------------------------------------------------------


def test_the_editor_is_told_the_three_pages_and_the_sunday_rule():
    task = KINDS["editor"].task
    assert "three pages and page 3 holds 24 stories at most" in task and "copied stories in first" in task
    assert '"sunday": true' in task and "about the game just played" in task


def test_the_game_in_the_news_reads_the_sunday_papers_stories_without_a_name_test():
    kickoff = datetime(2026, 11, 14, 23, 15, tzinfo=UTC)
    rows = [
        {"title": "Sumrall: 'We have to be better'", "url": "https://x/1", "source": "On3", "publishedAt": "2026-11-15T14:00:00Z"},
        {"title": "Sumrall: 'We have to be better'", "url": "https://x/2", "source": "247", "publishedAt": "2026-11-15T13:00:00Z"},
        {"title": "Late: Monday film", "url": "https://x/3", "source": "On3", "publishedAt": "2026-11-16T12:00:00Z"},
        {"title": None}, "junk",
    ]
    news = news_for(rows, None, None, kickoff, named=False, until=datetime(2026, 11, 16, 11, 0, tzinfo=UTC))
    assert [n["title"] for n in news] == ["Sumrall: 'We have to be better'"], "deduped, inside the Sunday paper's window"
    assert news_for(rows, None, None, kickoff) == [], "the old rule still needs a team named"
