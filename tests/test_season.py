"""The season overview: assembled from recorded fixtures through the real client, with ranks
computed locally, one part failing without killing the answer, malformed records skipped and
counted, stale data served when the upstream dies, and the game-day flag set from the schedule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.season import PROFILE_ROWS
from tests.conftest import ROLES, FakeCfbd, fixture_payload, role_int


def route_season(fake: FakeCfbd) -> None:
    """Every endpoint the overview needs, from the recorded fixtures."""

    def games(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("games_team"))
        return httpx.Response(200, json=fixture_payload("games_week"))  # the all-games call, week 4 only

    def boxes(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("week") == ROLES["LASTWEEK"]:
            return httpx.Response(200, json=fixture_payload("games_teams"))
        return httpx.Response(200, json=[])  # the earlier weeks' boxes are not served: a dash, not a crash

    fake.route("/games", handler=games)
    fake.route("/games/teams", handler=boxes)
    fake.fixture("/games/media", "games_media")
    fake.fixture("/records", "records_conference")
    fake.fixture("/rankings", "rankings")
    fake.fixture("/teams/fbs", "teams_fbs")
    fake.fixture("/stats/season", "stats_season_fbs")
    fake.fixture("/stats/season/advanced", "stats_season_advanced_fbs")
    fake.fixture("/ratings/sp", "ratings_sp")
    fake.fixture("/ratings/elo", "ratings_elo")
    fake.fixture("/ratings/fpi", "ratings_fpi")


def fail_all(fake: FakeCfbd) -> None:
    for path in ("/games", "/games/teams", "/games/media", "/records", "/rankings", "/teams/fbs", "/stats/season", "/stats/season/advanced", "/ratings/sp", "/ratings/elo", "/ratings/fpi"):
        fake.route(path, status=500, text="boom")


def test_overview_is_assembled_from_fixtures(client: TestClient, fake_cfbd: FakeCfbd):
    route_season(fake_cfbd)
    response = client.get("/api/season/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    assert body["meta"]["stale"] is False and body["meta"]["source"] == "live"
    data = body["data"]

    record = next(r for r in fixture_payload("records_conference") if r["team"] == "Swampwater Tech")
    assert data["season"] == 2026 and data["team"]["school"] == "Swampwater Tech" and data["team"]["abbreviation"] == "SWT"
    assert data["record"]["overall"]["wins"] == record["total"]["wins"] and data["record"]["conference"]["games"] == record["conferenceGames"]["games"]
    assert len(data["schedule"]) == 12
    assert data["nextGameId"] and data["opponent"]["school"] == "Diner Tech"
    wk3 = next(g for g in data["schedule"] if g["week"] == role_int("LASTWEEK"))  # our last game
    assert wk3["completed"] and wk3["result"] == "W" and wk3["opponent"]["school"] == "Silver Dollar" and wk3["opponent"]["logo"]

    assert len(data["standings"]) == 16
    assert [row["place"] for row in data["standings"]] == list(range(1, 17))
    swt = next(row for row in data["standings"] if row["isUs"])
    assert swt["overall"]["wins"] == record["total"]["wins"] and swt["abbreviation"] == "SWT"

    polls = {p["poll"]: p for p in data["polls"]}
    assert {"AP", "Coaches"} <= set(polls)
    assert len(polls["AP"]["ranks"]) == 25 and polls["AP"]["ranks"][0]["rank"] == 1 and polls["AP"]["week"] == 3

    rows = data["profile"]["rows"]
    assert [row["key"] for row in rows] == [key for _, _, key, _, _ in PROFILE_ROWS]
    assert data["profile"]["games"] == record["total"]["games"]
    tried = {r["statName"]: r["statValue"] for r in fixture_payload("stats_season_fbs") if r["team"] == "Swampwater Tech"}
    for row in rows:
        if row["key"] == "fourth" and not tried.get("fourthDowns"):
            assert row["value"] is None  # no fourth-down try yet: a dash, not a zero
            continue
        assert row["value"] is not None, row["key"]
        assert isinstance(row["nationalRank"], int) and isinstance(row["conferenceRank"], int), row["key"]
        if row["key"] in ("ppg", "opp_ppg"):
            # the fake all-games list has no finished games, so points ranks span only Swampwater Tech's own opponents here
            assert row["nationalOf"] >= 2, row["key"]
        else:
            assert row["nationalOf"] >= 100 and row["conferenceOf"] == 16, row["key"]
    ypg = next(row for row in rows if row["key"] == "ypg")
    assert 300 < ypg["value"] < 800  # a top team against a soft early schedule

    assert data["ratings"]["sp"]["rank"] and data["ratings"]["elo"]["rank"] and data["ratings"]["fpi"]["rank"]
    assert data["ratings"]["sp"]["of"] > 100

    trends = data["trends"]
    assert trends["weeks"] == [1, 2] and len(trends["points"]) == 2 and all(isinstance(p, float) for p in trends["points"])
    assert trends["yardsPerPlay"][1] is not None and trends["thirdDown"][1] is not None and trends["turnoverMargin"][1] is not None
    assert trends["yardsPerPlay"][0] is None  # week 1's box not served: a dash, not a crash

    assert {name: part["status"] for name, part in data["parts"].items()} == {name: "ok" for name in data["parts"]}
    assert data["parts"]["trends"]["missingWeeks"] == []
    # Two schedule pulls: Swampwater Tech's and the league-wide one. The live engine's startup check asks for Swampwater Tech's
    # schedule too and can land before the routes exist (a 404) or share the cached answer, so it may add one.
    games = [r for r in fake_cfbd.requests if r.url.path == "/games"]
    league = [r for r in games if "team" not in r.url.params and r.url.params.get("year") == "2026"]
    last = [r for r in games if "team" not in r.url.params and r.url.params.get("year") == "2025"]  # Phase 15: last season
    ours = [r for r in games if r.url.params.get("team") == "Swampwater Tech"]
    assert len(league) == 1 and len(last) == 1 and 1 <= len(ours) <= 2 and len(games) == len(league) + len(last) + len(ours)
    stats = [r.url.params.get("year") for r in fake_cfbd.requests if r.url.path == "/stats/season"]
    assert fake_cfbd.count("/games/teams") == 2 and sorted(stats) == ["2025", "2026"]  # one box per final game of ours


def test_second_request_is_served_from_cache(client: TestClient, fake_cfbd: FakeCfbd):
    route_season(fake_cfbd)
    assert client.get("/api/season/overview").status_code == 200
    calls = fake_cfbd.count()
    body = client.get("/api/season/overview").json()
    assert fake_cfbd.count() == calls
    assert body["meta"]["source"] == "cache" and body["meta"]["stale"] is False


def test_one_failed_part_does_not_kill_the_overview(client: TestClient, fake_cfbd: FakeCfbd):
    route_season(fake_cfbd)
    fake_cfbd.route("/stats/season", status=500, text="down")
    body = client.get("/api/season/overview").json()
    data = body["data"]
    assert data["parts"]["stats"]["status"] == "error" and "500" in data["parts"]["stats"]["error"]
    assert data["parts"]["records"]["status"] == "ok"
    assert any(e["code"] == "part_unavailable" and e["message"].startswith("stats:") for e in body["errors"])
    # values still come from the schedule where they can, ranks do not
    ppg = next(row for row in data["profile"]["rows"] if row["key"] == "ppg")
    assert ppg["value"] and ppg["nationalRank"] is None
    assert all(row["value"] is None for row in data["profile"]["rows"] if row["key"] == "ypg")
    assert len(data["standings"]) == 16


def test_everything_down_and_nothing_cached_is_a_503(client: TestClient, fake_cfbd: FakeCfbd):
    fail_all(fake_cfbd)
    response = client.get("/api/season/overview")
    assert response.status_code == 503
    body = response.json()
    assert body["data"] is None and body["errors"][0]["code"] == "upstream_unavailable"


def test_malformed_records_are_skipped_and_counted(client: TestClient, fake_cfbd: FakeCfbd):
    route_season(fake_cfbd)
    good = fixture_payload("stats_season_fbs")
    junk = [None, "text", 42, {"team": None, "statName": "x"}, {"statName": "totalYards", "statValue": 5}]
    fake_cfbd.route("/stats/season", json=junk + good)
    records = fixture_payload("records_conference")
    fake_cfbd.route("/records", json=[{"team": "Ghost U", "conference": "Biscuit Belt"}] + records + ["junk"])
    body = client.get("/api/season/overview").json()
    data = body["data"]
    assert data["parts"]["stats"]["skipped"] == len(junk)
    assert any(e["code"] == "records_skipped" and e["message"].startswith("stats:") for e in body["errors"])
    ypg = next(row for row in data["profile"]["rows"] if row["key"] == "ypg")
    assert ypg["value"] and ypg["nationalRank"]
    assert len(data["standings"]) == 17  # Ghost U has no record lines and sorts last, with dashes on the page
    assert data["standings"][-1]["team"] == "Ghost U" and data["standings"][-1]["overall"] is None


def test_stale_is_served_when_the_upstream_dies_later(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_season(fake_cfbd)
    assert client.get("/api/season/overview").json()["meta"]["stale"] is False
    fail_all(fake_cfbd)
    app.state.cfbd._clock = lambda: datetime.now(timezone.utc) + timedelta(days=3)  # every cache lifetime has passed
    body = client.get("/api/season/overview").json()
    assert body["meta"]["stale"] is True and body["meta"]["source"] == "cache"
    data = body["data"]
    assert data["parts"]["schedule"]["status"] == "stale" and data["parts"]["schedule"]["ageSeconds"] > 2 * 24 * 3600
    assert "500" in data["parts"]["schedule"]["error"]
    assert len(data["schedule"]) == 12 and len(data["profile"]["rows"]) == len(PROFILE_ROWS)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 21, 16, 0, tzinfo=timezone.utc), False),  # a Monday
        (datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc), True),  # Diner Tech game day, morning in Swamp County
        (datetime(2026, 9, 27, 3, 0, tzinfo=timezone.utc), True),  # 11 pm Eastern on that Saturday
    ],
)
def test_game_day_flag_follows_the_schedule(app, client: TestClient, fake_cfbd: FakeCfbd, now: datetime, expected: bool):
    route_season(fake_cfbd)
    app.state.cfbd._clock = lambda: now
    assert client.get("/api/season/overview").status_code == 200
    assert app.state.cfbd.game_day is expected
