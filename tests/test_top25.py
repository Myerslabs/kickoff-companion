"""Queue items 10 to 12 (mocks approved 2026-10-13): the week's AP-ranked games for the Top 25 page and the newspaper,
the paper's headlines, the Pick'em line and the weekly editions. No network: hand-made games, and the made-up league
behind the app for the routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo.sites import DemoSites
from app.demo.upstream import DemoUpstream
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services import headlines as H
from app.services.editions import Editions, key_for, label_for, order_of
from app.services.lines import PICKEM, short_spread, spread_text
from app.services.rankedweek import period_of, ranked_order
from tests.conftest import ROLES, league

ET = ZoneInfo("America/New_York")
NB = " "


def team(school: str, rank: int | None = None, wins: int = 3, losses: int = 1, points: int | None = None, mascot: str | None = None, lines: list[int] | None = None) -> dict:
    return {"school": school, "rank": rank, "mascot": mascot, "record": {"wins": wins, "losses": losses}, "points": points, "lineScores": lines}


def game(gid: int, status: str, away: dict, home: dict, *, kickoff: str = "2026-10-24T19:30:00Z", us: bool = False, neutral: bool = False) -> dict:
    return {"gameId": gid, "status": status, "kickoff": kickoff, "startTimeTbd": False, "neutralSite": neutral, "isUs": us, "away": away, "home": home}


# --- the headlines --------------------------------------------------------------------------------------------


def test_each_kind_of_headline():
    kind = lambda g: H.kind_of(g, us="Our U", tz=ET)  # noqa: E731
    assert kind(game(1, "pre", team("A", 3), team("B", 9))) == "preTop"
    assert kind(game(2, "pre", team("A", 3, wins=5, losses=0), team("B"))) == "preUnbeaten"
    assert kind(game(3, "pre", team("A", 3), team("B"), kickoff="2026-10-25T02:30:00Z")) == "preLate"  # 10:30 PM Eastern
    assert kind(game(4, "pre", team("A", 3), team("B"))) == "pre"
    assert kind(game(5, "final", team("A", None, points=33), team("B", 3, points=21))) == "finalUpset"
    assert kind(game(6, "final", team("A", 20, points=30), team("B", 4, points=21))) == "finalShakeup"
    assert kind(game(7, "final", team("A", 2, points=54, lines=[6, 10, 0, 24, 7, 7]), team("B", 20, points=47, lines=[3, 14, 13, 10, 7, 0]))) == "overtime"
    assert kind(game(8, "final", team("A", 2, points=48), team("B", points=41))) == "shootout"
    assert kind(game(9, "final", team("A", 2, points=31), team("B", points=10, wins=0, losses=6))) == "winless"
    assert kind(game(10, "final", team("A", 2, points=62), team("B", points=28))) == "bigNumber"
    assert kind(game(11, "final", team("A", 2, points=45), team("B", points=10))) == "rout"
    assert kind(game(12, "final", team("A", 2, points=22), team("B", points=20))) == "escape"
    assert kind(game(13, "final", team("A", 2, points=31), team("B", points=17))) == "handles"


def test_a_live_game_or_a_broken_one_gets_no_headline():
    assert H.write(game(1, "live", team("A", 3, points=7), team("B", points=0)), us=None, tz=ET) is None  # owner: pregame and postgame only
    assert H.write(game(2, "final", team("A", 3), team("B")), us=None, tz=ET) is None  # a final without its score
    assert H.write({"status": "pre", "home": {"school": "B"}}, us=None, tz=ET) is None
    assert H.write(None, us=None, tz=ET) is None and H.write("junk", us=None, tz=ET) is None


def test_our_games_are_kept_kind():
    """Owner 2026-10-13: "keep us kind". A loss of ours is never a joke, an upset of ours is never an upset story."""
    lost = game(1, "final", team("Our U", 4, points=17, mascot="Mudpuppies"), team("Rival", None, points=24, mascot="Banjos"), us=True)
    line = H.write(lost, us="Our U", tz=ET)
    assert line["kind"] == "usLose" and line["kicker"] == "Our game"
    assert "stinks" not in line["text"].lower() and "grumbl" not in line["text"].lower()
    assert "Rival" in line["text"] and "24-17" in line["text"]
    won = H.write({**lost, "away": team("Our U", 4, points=35, mascot="Mudpuppies")}, us="Our U", tz=ET)
    assert won["kind"] == "usWin" and "35-24" in won["text"]
    every_template = " ".join(t for k in ("usPre", "usWin", "usLose") for t in H.TEMPLATES[k]).lower()
    assert "stinks" not in every_template and "grumbl" not in every_template


def test_no_betting_talk_and_names_never_break():
    for kind, options in H.TEMPLATES.items():
        for text in options:
            words = text.lower()
            assert not any(w in words for w in (" line", "odds", "spread", "favorite", "favored", "cover", " bet", "underdog", "pick")), (kind, text)
    line = H.write(game(5, "final", team("Dust Devil State", None, points=33), team("Jackrabbit Junction", 3, points=21)), us=None, tz=ET)
    assert f"No.{NB}3 Jackrabbit Junction" in line["text"]  # the number never leaves "No."
    late = H.write(game(3, "pre", team("A", 9), team("B"), kickoff="2026-10-25T02:30:00Z"), us=None, tz=ET)
    assert f"10:30{NB}PM" in late["text"]


def test_a_game_keeps_its_headline_and_a_page_varies_them():
    g = game(42, "final", team("A", 2, points=31), team("B", points=17))
    assert H.write(g, us=None, tz=ET) == H.write(json.loads(json.dumps(g)), us=None, tz=ET)  # the same every refresh
    pair = H.write_all([g, game(43, "final", team("C", 5, points=24), team("D", points=10))], us=None, tz=ET)
    assert pair[0]["kind"] == pair[1]["kind"] == "handles"
    assert pair[0]["text"].split(", ")[-1] != pair[1]["text"].split(", ")[-1] or len(H.TEMPLATES["handles"]) == 1
    tbd = H.write({**game(44, "pre", team("A", 3), team("B")), "startTimeTbd": True}, us=None, tz=ET)
    assert "this week" in tbd["text"] or "TBD" in tbd["text"]
    neutral = H.write(game(45, "pre", team("A", 3), team("B", 9), neutral=True), us=None, tz=ET)
    assert "visits" not in neutral["text"]


# --- the line ------------------------------------------------------------------------------------------------


def test_a_zero_spread_is_a_pickem():
    assert spread_text("Front Porch State -0", None) == PICKEM  # the mock's "PORC -0"
    assert spread_text("Front Porch State -0.0", -0.0) == PICKEM
    assert spread_text(None, 0) == PICKEM
    assert spread_text("Saddle Sore -3.5", -3.5) == "Saddle Sore -3.5"
    assert spread_text("Team 10 -7", -7) == "Team 10 -7"  # a school ending in a number is not a zero
    assert spread_text(None, None) is None and spread_text("", None) is None
    assert short_spread("Saddle Sore -3.5", {"Saddle Sore": "SADL", "Saddle": "SAD"}) == "SADL -3.5"
    assert short_spread(PICKEM, {"A": "A"}) == PICKEM and short_spread(None, {}) is None


# --- the order and the clock ----------------------------------------------------------------------------------


def test_the_games_sit_in_ap_poll_order():
    games = [
        {"gameId": 3, "home": {"rank": 18}, "away": {"rank": 6}},
        {"gameId": 2, "home": {"rank": 20}, "away": {"rank": 2}},
        {"gameId": 4, "home": {"rank": None}, "away": {"rank": 3}},
        {"gameId": 1, "home": {"rank": 1}, "away": {"rank": None}},
        {"gameId": 6, "home": {"rank": "12"}, "away": {"rank": None}},  # a rank as text is no rank: last, by its id
        {"gameId": 5, "home": {"rank": 12}, "away": {"rank": 25}},
        {"gameId": 7, "home": {"rank": None}, "away": None},  # malformed: last
        {"gameId": None, "home": "bad", "away": {"rank": 9}},
    ]
    # the owner (layout pass, 2026-10-22): "always ... in order by the AP poll", each game at its better rank
    assert [g["gameId"] for g in ranked_order(games)] == [1, 2, 4, 3, None, 5, 6, 7]
    assert ranked_order([]) == []
    assert period_of("Q2 7:02") == (2, "7:02") and period_of("OT") == (5, None) and period_of("2OT") == (6, None)
    assert period_of("In progress") == (None, None) and period_of(None) == (None, None)


# --- the editions ---------------------------------------------------------------------------------------------


def test_editions_are_kept_and_frozen_ones_never_change(tmp_path: Path):
    store = Editions(tmp_path, 2026)
    assert key_for(7, "regular") == "week-7" and key_for(1, "postseason") == "postseason" and key_for(None, None) is None
    assert label_for("week-7") == "Week 7" and label_for("postseason") == "Bowl season"
    assert order_of("week-2") < order_of("week-10") < order_of("postseason")
    first = store.save({"key": "week-7", "week": 7, "matchups": [{"gameId": 5, "status": "final", "headline": {"text": "A beats B"}}], "frozen": False})
    assert store.load("week-7")["matchups"][0]["gameId"] == 5 and first["savedAt"]
    assert store.save({"key": "week-7", "week": 7, "matchups": [{"gameId": 5, "status": "final", "headline": {"text": "A beats B"}}], "frozen": False}) == first  # unchanged: not written
    assert store.frozen_headlines("week-7") == {5: {"text": "A beats B"}}
    store.save({"key": "week-7", "week": 7, "matchups": [], "frozen": True})
    assert store.save({"key": "week-7", "week": 7, "matchups": [{"gameId": 9}], "frozen": False})["matchups"] == []  # frozen
    store.save({"key": "week-2", "week": 2, "matchups": []})
    store.save({"key": "postseason", "matchups": []})
    assert [e["key"] for e in store.keys()] == ["week-2", "week-7", "postseason"]
    assert store.load("../etc") is None and store.save({"key": "../etc"}) == {"key": "../etc"}
    (tmp_path / "season" / "2026" / "paper" / "week-3.json").write_text("{not json", encoding="utf-8")
    assert store.load("week-3") is None and "week-3" not in [e["key"] for e in store.keys()]


# --- the routes, against the made-up league -------------------------------------------------------------------

SATURDAY = datetime(2026, 9, 26, 22, 0, tzinfo=timezone.utc)  # the league's week 4, games final, live and to come


@pytest.fixture
def league_app(settings: Settings):
    world = league()
    clock = {"now": SATURDAY}
    upstream = DemoUpstream(world, lambda: clock["now"], tier=2)
    sites = DemoSites(world, lambda: clock["now"])
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=httpx.MockTransport(upstream.handler), feeds_transport=httpx.MockTransport(sites.handler), weather_transport=httpx.MockTransport(sites.handler))
    application.state.cfbd._clock = lambda: clock["now"]
    application.state.test_clock = clock
    application.state.test_upstream = upstream
    yield application
    shutdown_logging()


@pytest.fixture
def lclient(league_app):
    with TestClient(league_app, base_url="https://testserver") as test_client:
        test_client.portal.call(league_app.state.live.stop_background)
        yield test_client


def test_the_top25_page_has_every_ranked_game_and_nothing_else(lclient: TestClient, league_app):
    data = lclient.get("/api/top25?delay=30").json()["data"]
    assert data["week"] == 4 and data["label"] == "Week 4" and data["poll"]["name"] == "AP Top 25"
    games = data["games"]
    assert games and all(g["home"]["rank"] is not None or g["away"]["rank"] is not None for g in games)
    assert [g["gameId"] for g in ranked_order(games)] == [g["gameId"] for g in games]
    ranked = {t for g in games for t in (g["home"]["school"], g["away"]["school"]) if (g["home"]["rank"] if t == g["home"]["school"] else g["away"]["rank"])}
    off = {t["school"] for t in data["offThisWeek"]}
    assert not ranked & off and len(ranked) + len(off) == data["poll"]["teams"]
    assert sum(data["counts"].values()) == len(games)
    for g in games:
        for side in ("home", "away"):
            block = g[side]
            assert block["school"] and "record" in block and "form" in block and "headCoach" in block
            assert block["lineScores"] is None or g["status"] == "final"
        assert g["href"] == ("#live" if g["isUs"] else f"#box={g['gameId']}")
        assert "headline" not in g  # owner: no funny headlines on the Top 25 page
        assert g["line"] is None or g["line"]["formatted"] != "" and "-0" not in (g["line"]["formatted"] or "")
        if g["status"] == "live":
            assert g["home"]["lineScores"] is None
        if g["isUs"] and g["status"] == "live":
            assert g["home"]["points"] is None and g["away"]["points"] is None  # the engine has released nothing: no score ahead of the TV
    assert any(g["weather"] for g in games)  # a Tier 2 key: CFBD's weather for the whole week
    assert league_app.state.test_upstream.calls.get("/coaches", 0) == 1  # every head coach in one call


def test_the_paper_prints_headlines_before_and_after_and_keeps_the_edition(lclient: TestClient, league_app, settings: Settings):
    data = lclient.get("/api/newspaper?delay=30").json()["data"]
    edition = data["edition"]
    assert edition["key"] == "week-4" and edition["current"] is True and edition["frozen"] is False
    for g in edition["matchups"]:
        if g["status"] == "live":
            assert g["headline"] is None
        else:
            assert g["headline"] and g["headline"]["text"] and g["headline"]["kicker"]
    assert [e["key"] for e in data["editions"]][-1] == "week-4" and data["editions"][-1]["current"] is True
    saved = Editions(settings.data_dir, settings.season).load("week-4")
    assert saved and [g["gameId"] for g in saved["matchups"]] == [g["gameId"] for g in edition["matchups"]]
    # an earlier week's saved edition comes back from its file, as printed, with no live week behind it
    Editions(settings.data_dir, settings.season).save({"key": "week-2", "week": 2, "label": "Week 2", "matchups": [{"gameId": 7, "status": "final", "home": {"school": "A"}, "away": {"school": "B"}}], "headlines": [], "frozen": True})
    calls = dict(league_app.state.test_upstream.calls)
    old = lclient.get("/api/newspaper?edition=week-2").json()["data"]
    assert old["edition"]["key"] == "week-2" and old["edition"]["current"] is False and old["edition"]["matchups"][0]["gameId"] == 7
    assert "week-2" in [e["key"] for e in old["editions"]]
    assert league_app.state.test_upstream.calls.get("/scoreboard", 0) == calls.get("/scoreboard", 0)  # no live scores for an old paper
    assert lclient.get("/api/newspaper?edition=week-99").json()["data"]["edition"] is None


def test_a_past_week_is_settled_from_the_season_and_frozen(lclient: TestClient, league_app, settings: Settings):
    lclient.get("/api/newspaper?delay=0")
    store = Editions(settings.data_dir, settings.season)
    before = store.load("week-4")
    assert before and before["frozen"] is False
    league_app.state.test_clock["now"] = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)  # week 5
    league_app.state.cfbd.cache.clear()
    data = lclient.get("/api/newspaper?delay=0").json()["data"]
    assert data["edition"]["key"] == "week-5"
    after = store.load("week-4")
    assert after["frozen"] is True
    assert all(g["status"] == "final" and g["headline"] and isinstance(g["home"]["points"], int) for g in after["matchups"])
    ours = [g for g in after["matchups"] if g["isUs"]]
    assert all(g["headline"]["kind"] in ("usWin", "usLose") for g in ours)  # our game: our own, kind wording
    jokes = [g for g in after["matchups"] if not g["isUs"]]
    assert all(ROLES["US"] not in g["headline"]["text"] for g in jokes)


def test_sunday_nights_new_poll_never_rewrites_the_week_that_was_played(lclient: TestClient, league_app, settings: Settings):
    """Review 2026-10-13: the next week's AP poll lands on Sunday evening, before the calendar's week ends on Monday."""
    first = lclient.get("/api/newspaper?delay=0").json()["data"]
    assert first["rankedWeek"]["poll"]["week"] == 4
    games = {g["gameId"] for g in first["edition"]["matchups"]}
    league_app.state.test_clock["now"] = datetime(2026, 9, 27, 22, 0, tzinfo=timezone.utc)  # Sunday evening, still week 4
    league_app.state.cfbd.cache.clear()
    sunday = lclient.get("/api/newspaper?delay=0").json()["data"]
    assert sunday["edition"]["key"] == "week-4" and sunday["rankedWeek"]["poll"]["week"] == 4
    assert {g["gameId"] for g in sunday["edition"]["matchups"]} == games
    top = lclient.get("/api/top25?delay=0").json()["data"]
    assert top["poll"]["week"] == 4 and {g["gameId"] for g in top["games"]} == games
    saved = Editions(settings.data_dir, settings.season).load("week-4")
    assert {g["gameId"] for g in saved["matchups"]} == games


def test_the_week_reads_its_own_poll():
    from types import SimpleNamespace as NS

    from app.services.rankedweek import week_ranks

    def poll(week: int, season_type: str = "regular", school: str = "A", rank: int = 1):
        return NS(week=week, season_type=season_type, polls=[NS(poll="AP Top 25", ranks=[NS(school=school, rank=rank), NS(school=None, rank=2), NS(school="Z", rank=None)])])

    weeks = [poll(1, school="Pre"), poll(4, school="Four"), poll(5, school="Five"), poll(1, "postseason", school="Final"), "junk"]
    assert week_ranks(weeks, 4, "regular") == ({"AP": {"Four": 1}}, 4)
    assert week_ranks(weeks, 9, "regular")[1] == 5
    assert week_ranks(weeks, 0, "regular") == ({"AP": {"Pre": 1}}, 1)  # a week before the first poll: the preseason poll
    assert week_ranks(weeks, 1, "postseason") == ({"AP": {"Five": 1}}, 5)  # bowl season: the last regular poll, never the final
    assert week_ranks([], 4, "regular") == ({}, None)


def test_a_damaged_edition_never_takes_the_paper_down(lclient: TestClient, league_app, settings: Settings, monkeypatch: pytest.MonkeyPatch):
    folder = Path(settings.data_dir) / "season" / str(settings.season) / "paper"
    folder.mkdir(parents=True, exist_ok=True)
    junk = {"key": "week-3", "week": 3, "matchups": [{"gameId": [1], "status": "live"}, {"gameId": 5, "home": "x", "away": None, "status": "pre"}, "junk", None], "frozen": False}
    (folder / "week-3.json").write_text(json.dumps(junk), encoding="utf-8")
    (folder / "week-4.json").write_text(json.dumps({**junk, "key": "week-4"}), encoding="utf-8")
    data = lclient.get("/api/newspaper?delay=0").json()["data"]
    assert data["edition"]["key"] == "week-4" and data["edition"]["matchups"]  # the live week, the junk rows left behind
    assert Editions(settings.data_dir, settings.season).load("week-3")["frozen"] is True  # an earlier week is settled anyway
    assert lclient.get("/api/newspaper?edition=week-3").status_code == 200

    async def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(league_app.state.rankedweek, "paper", broken)
    answer = lclient.get("/api/newspaper?delay=0")
    assert answer.status_code == 200
    body = answer.json()["data"]
    assert "edition" not in body and "could not be read" in body["editionError"] and body["weeks"] is not None  # the headlines stay


def test_a_game_never_played_is_kept_as_not_played_and_bowl_season_freezes_when_it_ends(settings: Settings):
    from types import SimpleNamespace as NS

    from app.services.rankedweek import RankedWeekService

    store = Editions(settings.data_dir, settings.season)
    game = lambda gid, status: {"gameId": gid, "status": status, "home": {"school": "A", "points": None}, "away": {"school": "B", "points": None}}  # noqa: E731
    store.save({"key": "week-6", "week": 6, "matchups": [game(1, "live"), game(2, "pre"), game(3, "live")], "weekEnd": "2026-10-12T06:59:00Z"})
    store.save({"key": "postseason", "matchups": [game(4, "pre")], "weekEnd": "2027-01-28T07:59:00Z"})
    from app.cfbd.models import Game

    finished = Game.model_validate({"id": 3, "season": 2026, "week": 6, "completed": True, "homePoints": 21, "awayPoints": 14, "homeLineScores": [7, 7, 7, 0], "awayLineScores": [0, 7, 7, 0]})
    service = RankedWeekService(NS(settings=settings, team="Our U"), None, store)  # only the editions are used here
    service._settle("week-7", [finished], datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc))
    week6 = store.load("week-6")
    assert week6["frozen"] is True
    by = {g["gameId"]: g for g in week6["matchups"]}
    assert by[1]["status"] == "unplayed" and by[1]["headline"] is None and by[2]["status"] == "unplayed"  # postponed or cancelled
    assert by[3]["status"] == "final" and by[3]["home"]["points"] == 21 and by[3]["headline"]["text"]
    assert store.load("postseason").get("frozen") is not True  # bowl season still to come
    # after the title game, with the app back on a regular week (a team with no bowl): bowl season freezes and stays listed
    service._settle("week-14", [], datetime(2027, 2, 2, 12, 0, tzinfo=timezone.utc))
    assert store.load("postseason")["frozen"] is True
    keys = [e["key"] for e in service._edition_list([], "week-14", datetime(2027, 2, 2, 12, 0, tzinfo=timezone.utc))]
    assert "postseason" in keys


def test_winless_waits_for_three_losses():
    opener = game(9, "final", team("A", 2, points=31), team("B", points=10, wins=0, losses=1))
    assert H.kind_of(opener, us=None, tz=ET) != "winless"
    assert H.kind_of(game(9, "final", team("A", 2, points=31), team("B", points=10, wins=0, losses=3)), us=None, tz=ET) == "winless"
