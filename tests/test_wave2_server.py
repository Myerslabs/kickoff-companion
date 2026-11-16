"""Post-freeze Wave 2 on the server (owner 2026-10-24): stable data is kept and an expired copy is served at once while one
background call refreshes it (ENH-2), and inside a live game window the page calls that reach CFBD take turns, so the
live poll comes first, and the background refreshes wait for the game (ENH-3)."""

from __future__ import annotations

import asyncio

import httpx

from app.cache import DataKind
from app.cfbd import client as client_module
from tests.test_client import Harness, run

TEAMS = [{"id": 1, "school": "Florida", "mascot": "Gators"}]
NEWER = [{"id": 1, "school": "Florida", "mascot": "Gators", "color": "#0021A5"}]


def test_an_expired_stable_copy_is_served_at_once_and_refreshed_behind_it(tmp_path):
    h = Harness(tmp_path)
    answers = iter([TEAMS, NEWER])
    h.upstream.route("/teams/fbs", handler=lambda request: httpx.Response(200, json=next(answers)))

    async def scenario():
        first = await h.client.get("/teams/fbs", {"year": 2026}, kind=DataKind.TEAMS)
        h.clock.advance(days=8)  # past the seven-day lifetime of teams
        served = await h.client.get("/teams/fbs", {"year": 2026}, kind=DataKind.TEAMS)
        pending = list(h.client._revalidating.values())
        await asyncio.gather(*pending)
        after = await h.client.get("/teams/fbs", {"year": 2026}, kind=DataKind.TEAMS)
        await h.close()
        return first, served, pending, after

    first, served, pending, after = run(scenario())
    assert first.source == "live" and first.payload == TEAMS
    assert served.source == "cache" and served.stale is False and served.payload == TEAMS, "the page gets the kept copy at once"
    assert len(pending) == 1, "one background refresh"
    assert after.source == "cache" and after.payload == NEWER, "the refresh replaced the copy behind the page"
    assert h.upstream.count("/teams/fbs") == 2 and h.client.stats["revalidations"] == 1


def test_one_refresh_per_key_and_none_for_kinds_that_change_or_inside_a_live_window(tmp_path):
    h = Harness(tmp_path)
    h.upstream.route("/teams/fbs", json=TEAMS)
    h.upstream.route("/games", json=[])

    async def scenario():
        await h.client.get("/teams/fbs", {"year": 2026}, kind=DataKind.TEAMS)
        await h.client.get("/games", {"year": 2026}, kind=DataKind.SCHEDULE)
        h.clock.advance(days=8)
        await h.client.get("/teams/fbs", {"year": 2026}, kind=DataKind.TEAMS)
        await h.client.get("/teams/fbs", {"year": 2026}, kind=DataKind.TEAMS)
        one = len(h.client._revalidating)
        await asyncio.gather(*h.client._revalidating.values())
        schedule = await h.client.get("/games", {"year": 2026}, kind=DataKind.SCHEDULE)
        h.clock.advance(days=8)
        h.client.live_window = True
        during = await h.client.get("/teams/fbs", {"year": 2026}, kind=DataKind.TEAMS)
        waiting = len(h.client._revalidating)
        h.client.live_window = False
        await h.close()
        return one, schedule, during, waiting

    one, schedule, during, waiting = run(scenario())
    assert one == 1, "two asks while it runs make one refresh"
    assert schedule.source == "live", "a kind that changes (the schedule) is fetched, never served expired"
    assert during.source == "cache" and waiting == 0, "inside a live window the kept copy is served and the refresh waits for the game"


def test_inside_a_live_window_page_calls_take_turns_and_the_live_lane_does_not(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    in_flight = {"general": 0, "most": 0, "live": 0}

    async def fake_request(self, endpoint, params, *, live, breaker, admission):
        lane = "live" if live else "general"
        in_flight[lane] += 1
        if lane == "general":
            in_flight["most"] = max(in_flight["most"], in_flight["general"])
        await asyncio.sleep(0.02)
        in_flight[lane] -= 1
        return [], None

    monkeypatch.setattr(client_module.CfbdClient, "_request", fake_request)

    async def scenario():
        h.client.live_window = True
        pages = [h.client.get(f"/stats/season/{n}", {"year": 2026}, kind=DataKind.SEASON_STATS) for n in range(5)]
        live = h.client.get("/live/plays", {"gameId": 1}, kind=DataKind.LIVE, live=True)
        await asyncio.gather(*pages, live)
        gated = h.client.stats["gated_in_live_window"]
        h.client.live_window = False
        await h.close()
        return gated

    gated = run(scenario())
    assert in_flight["most"] == client_module.LIVE_WINDOW_GENERAL_SLOTS == 2, "two page calls at a time while the game is live"
    assert gated >= 1, "the waits are counted for the status page"


def test_the_revalidation_never_outlives_the_client(tmp_path):
    h = Harness(tmp_path)
    h.upstream.route("/teams/fbs", json=TEAMS)

    async def scenario():
        await h.client.get("/teams/fbs", {"year": 2026}, kind=DataKind.TEAMS)
        h.clock.advance(days=8)
        await h.client.get("/teams/fbs", {"year": 2026}, kind=DataKind.TEAMS)
        await h.close()
        return dict(h.client._revalidating)

    assert run(scenario()) == {}, "closing the client ends its background refreshes"
