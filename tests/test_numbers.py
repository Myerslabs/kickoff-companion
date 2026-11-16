"""FEAT-8: the app's own numbers from every play (success by down and distance, explosive plays, havoc, red-zone
finishing), the store they are kept in, the season table with its national ranks, and the nightly sweep that fills it."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import numbers as N
from tests.conftest import fixture_payload


def test_one_recorded_game_counts_both_offenses():
    plays = fixture_payload("plays")  # one game of ours in CFBD's shape (the league's twin of the recording)
    counts = N.game_counts(plays)
    assert len(counts) == 2 and "Florida" in counts
    for team, row in counts.items():
        assert 40 <= row["snaps"] <= 110, (team, row["snaps"])
        assert 0 < row["success"] <= row["judged"] <= row["snaps"]
        assert row["by"]["standard"][1] + row["by"]["passing"][1] == row["judged"], "every judged snap is a standard or a passing down"
        downs = sum(row["by"][k][1] for k in ("first", "second_short", "second_medium", "second_long", "third_short", "third_medium", "third_long"))
        assert downs == row["judged"]
        assert row["havoc"] == row["tfl"] + row["sacks"] + row["takeaways"] - _both(plays, team)
        assert row["rzTd"] + row["rzFg"] <= row["rzTrips"]


def _both(plays, team) -> int:
    """Snaps counted twice in the havoc parts (a sack that is also a fumble lost): the havoc counts each snap once."""
    seen = 0
    for p in plays:
        kind = str(p.get("playType") or "")
        if p.get("offense") == team and N.SACK.search(kind) and N.TURNOVER.search(kind):
            seen += 1
    return seen


def test_the_rules_on_made_up_snaps():
    def snap(offense, down, distance, gained, kind="Rush", ytg=50, drive="d1", scoring=False):
        return {"offense": offense, "down": down, "distance": distance, "yardsGained": gained, "playType": kind, "yardsToGoal": ytg, "driveId": drive, "scoring": scoring}

    plays = [
        snap("A", 1, 10, 5),  # success: half the distance
        snap("A", 2, 5, 3),  # fails: 70% of 5 is 3.5
        snap("A", 3, 2, 25, kind="Pass Reception"),  # success, explosive, a pass
        snap("A", 1, 10, -2),  # a tackle for loss
        snap("A", 2, 12, -7, kind="Sack"),
        snap("A", 1, 10, 0, kind="Pass Interception Return"),  # a takeaway, fails
        snap("A", 1, 10, 4, ytg=15, drive="d2"),  # inside the 20: a trip
        snap("A", 2, 6, 15, kind="Rushing Touchdown", ytg=15, drive="d2", scoring=True),
        snap("A", 1, 10, 3, ytg=18, drive="d3"),
        {"offense": "A", "playType": "Field Goal Good", "driveId": "d3", "yardsToGoal": 15},
        {"offense": "A", "playType": "Kickoff", "driveId": "d4", "down": 1, "distance": 10, "yardsGained": 60},  # not a snap
    ]
    row = N.game_counts(plays)["A"]
    assert row["snaps"] == 9 and row["judged"] == 9 and row["success"] == 3  # the 5-yard first down, the 3rd and 2, the touchdown
    assert row["explosive"] == 1 and row["passes"] == 3 and row["rushes"] == 6
    assert (row["tfl"], row["sacks"], row["takeaways"], row["havoc"]) == (1, 1, 1, 3)
    assert (row["rzTrips"], row["rzTd"], row["rzFg"]) == (2, 1, 1)
    assert row["by"]["third_short"] == [1, 1] and row["by"]["second_long"] == [0, 1] and row["by"]["passing"] == [0, 1]


@pytest.mark.parametrize("junk", [None, "x", 5, [], {}, {"offense": None, "playType": "Rush"}, {"offense": "A"}, {"offense": "A", "playType": 7},
                                  {"offense": "A", "playType": "Rush", "down": "1", "distance": None, "yardsGained": "4"}, {"offense": "A", "playType": "Rush", "down": True, "distance": 10, "yardsGained": 3}])
def test_a_damaged_row_is_skipped_or_counted_without_a_verdict(junk):
    counts = N.game_counts([junk, {"offense": "B", "playType": "Rush", "down": 1, "distance": 10, "yardsGained": 6}])
    assert counts["B"]["success"] == 1
    row = counts.get("A")
    assert row is None or row["judged"] == 0, "no down and distance: a snap with no verdict"


def test_the_season_table_reads_a_defense_from_its_opponents_and_ranks_with_ties(monkeypatch):
    monkeypatch.setattr(N, "MIN_SNAPS", 1)
    a = N._empty() | {"snaps": 10, "judged": 10, "success": 6, "explosive": 2, "havoc": 1, "rzTrips": 2, "rzTd": 1}
    b = N._empty() | {"snaps": 10, "judged": 10, "success": 3, "explosive": 0, "havoc": 3, "rzTrips": 1, "rzTd": 0, "rzFg": 1}
    c = N._empty() | {"snaps": 10, "judged": 10, "success": 6, "explosive": 1}
    games = {"1": {"week": 1, "home": "A", "away": "B", "teams": {"A": a, "B": b}}, "2": {"week": 2, "home": "C", "away": "A", "teams": {"C": c}}, "3": "junk"}
    table = N.season_table(games)
    line = N.team_line(table, "A")
    assert line["games"] == 1 and line["offense"]["successRate"] == 0.6 and line["offense"]["redZone"]["pointsPerTrip"] == 3.5
    assert line["defense"]["snaps"] == 20 and line["defense"]["successRate"] == pytest.approx(0.45), "B's and C's snaps against A"
    assert line["offense"]["ranks"]["successRate"] == 1 and N.team_line(table, "C")["offense"]["ranks"]["successRate"] == 1, "a tie shares the rank"
    assert N.team_line(table, "B")["offense"]["ranks"]["successRate"] == 3
    assert table["rankOf"]["offense.successRate"] == 3 and N.team_line(table, "Nowhere") is None
    only = N.season_table(games, {"A"})
    assert [r["school"] for r in only["teams"]] == ["A"]


def test_the_store_keeps_each_game_and_survives_a_damaged_file(tmp_path):
    store = N.NumbersStore(tmp_path, 2026)
    assert not store.has(1)
    store.put(1, 3, "A", "B", {"A": N._empty()})
    store.save()
    again = N.NumbersStore(tmp_path, 2026)
    assert again.has(1) and again.games()["1"]["week"] == 3
    again.path.write_text("{broken", encoding="utf-8")
    assert N.NumbersStore(tmp_path, 2026).games() == {}
    again.path.write_text('{"format": 99, "games": {"1": {}}}', encoding="utf-8")
    assert N.NumbersStore(tmp_path, 2026).games() == {}, "another format starts over"


def test_the_sweep_fills_the_numbers_and_the_routes_serve_them(tmp_path):
    import httpx
    from fastapi.testclient import TestClient

    from app.config import load_settings
    from app.demo.sites import DemoSites
    from app.demo.upstream import DemoUpstream
    from app.logging_setup import configure_logging, shutdown_logging
    from app.main import create_app
    from tests.conftest import TEST_KEY, league
    from tests.test_any_team import SATURDAY  # the simulated league's week 4

    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, team="Florida", conference="SEC", season=league().season, data_dir=str(tmp_path / "data"), log_dir=str(tmp_path / "logs"))
    world = league()
    upstream = DemoUpstream(world, lambda: SATURDAY, tier=2)
    sites = DemoSites(world, lambda: SATURDAY)
    configure_logging(settings)
    application = create_app(settings, cfbd_transport=httpx.MockTransport(upstream.handler), feeds_transport=httpx.MockTransport(sites.handler), weather_transport=httpx.MockTransport(sites.handler))
    application.state.cfbd._clock = lambda: SATURDAY
    try:
        with TestClient(application, base_url="https://testserver") as client:
            client.portal.call(application.state.live.stop_background)
            warm = application.state.warm
            done = client.portal.call(warm.sweep, datetime(2026, 9, 27, 4, 0, tzinfo=timezone.utc))
            assert done["swept"] > 20 and done["stoppedBy"] is None and done["left"] == 0, done
            assert warm.numbers.path.is_file()
            again = client.portal.call(warm.sweep, datetime(2026, 9, 27, 4, 0, tzinfo=timezone.utc))
            assert again["swept"] == 0 and again["calls"] == 0, "a swept game is never asked again"
            table = client.get("/api/numbers").json()["data"]
            assert table["games"] == done["swept"] and len(table["teams"]) > 40
            texas = client.get("/api/numbers/Texas").json()["data"]["team"]
            assert texas["offense"]["snaps"] > 100 and 0 < texas["offense"]["successRate"] < 1 and texas["offense"]["downs"][0]["key"] == "first"
            assert client.get("/api/numbers/No%20Such%20School").status_code == 404
    finally:
        shutdown_logging()
