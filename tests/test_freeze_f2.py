"""Freeze wave F2 (2026-10-20): a free key fits the month.

- The publication schedules take a lean shape on the free profile: the same names, fewer slots, no rechecks, no prewarm.
- A settling game's empty answer is asked again hourly on the free profile, a filled one kept six hours; and the settle
  rule names its game, so another finished game's answer stays permanent.
- RESTRICTED mode keeps the week's slate and the schedule beside the live calls.
- The ledger's breakdown by endpoint and by day, and its route for the status page.
- The rehearsal tool's patterns."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cache import DataKind, cache_key, finished_game_empty_ttl, finished_game_ttl
from app.cfbd.client import CfbdClient
from app.cfbd.publish import LEAN_SLOTS, RATINGS, RESULTS, SCHEDULES, lean
from app.cfbd.quota import QuotaBlocked, QuotaMode
from app.config import load_settings
from app.db import Database
from tests.conftest import TEST_KEY, FakeCfbd, FakeClock
from tests.test_quota import NOW, burn, guard  # noqa: F401 - the guard fixture

EASTERN = ZoneInfo("America/New_York")


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


# --- lean schedules ------------------------------------------------------------------------------------------------


def test_lean_schedules_keep_their_names_and_drop_the_rechecks():
    for schedule in SCHEDULES:
        slim = lean(schedule)
        assert slim.name == schedule.name and slim.label == schedule.label
        assert slim.slots == LEAN_SLOTS[schedule.name]
        assert slim.recheck is None and slim.watch == timedelta(0) and slim.prewarm is False and slim.after_games is False
    assert len(lean(RATINGS).slots) == 2 and len(lean(RESULTS).slots) == 2


def test_the_lean_results_slots_are_sunday_noon_and_monday_morning():
    monday = utc(2026, 9, 28, 12, 0)  # a Monday at 8 a.m. Eastern
    slim = lean(RESULTS)
    assert slim.next_slot(monday) == utc(2026, 10, 4, 16, 0)  # Sunday noon EDT
    assert slim.last_slot(monday) == utc(2026, 9, 28, 8, 0)  # Monday 4 a.m. EDT


class ScheduleHarness:
    def __init__(self, tmp_path, start: datetime, budget: int):
        self.settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, data_dir=str(tmp_path), monthly_call_budget=budget)
        self.db = Database(tmp_path / "t.db")
        self.upstream = FakeCfbd()
        self.clock = FakeClock(start)
        self.client = CfbdClient(self.settings, self.db, transport=self.upstream.transport, clock=self.clock)
        self.client.quota.mark_reconcile_attempt(self.clock())
        self.client.quota.needs_reconcile = False
        self.upstream.route("/ratings/sp", handler=lambda _r: httpx.Response(200, json=[{"team": "Swampwater Tech", "rating": 20.1}]))

    def get_sp(self):
        return asyncio.run(self.client.get("/ratings/sp", {"year": 2026}, kind=DataKind.SEASON_STATS))

    def close(self) -> None:
        asyncio.run(self.client.aclose())
        self.db.close()


@pytest.mark.parametrize(("budget", "expires"), [(30000, utc(2026, 10, 4, 10, 0)), (1000, utc(2026, 9, 30, 8, 0))])
def test_a_small_budget_takes_the_lean_schedule(tmp_path, budget, expires):
    # Monday 2026-09-28 8 a.m. Eastern: the full ratings schedule waits for Sunday 6 a.m.; the lean one looks again Wednesday 4 a.m.
    h = ScheduleHarness(tmp_path, utc(2026, 9, 28, 12, 0), budget)
    try:
        h.get_sp()
        entry = h.client.cache.get(cache_key("/ratings/sp", {"year": 2026}))
        assert entry.expires_at == expires
        assert h.client.lean_profile is (budget < 20000)
    finally:
        h.close()


# --- settling games -------------------------------------------------------------------------------------------------


def test_finished_game_lifetimes_on_the_free_profile():
    now = utc(2026, 10, 25, 2, 0)
    settling = now + timedelta(hours=20)
    assert finished_game_empty_ttl(now, settling) == timedelta(minutes=10)
    assert finished_game_empty_ttl(now, settling, lean=True) == timedelta(hours=1)
    assert finished_game_empty_ttl(now, None, lean=True) == timedelta(hours=6)
    assert finished_game_ttl([{"x": 1}], now, settling) == timedelta(hours=1)
    assert finished_game_ttl([{"x": 1}], now, settling, lean=True) == timedelta(hours=6)
    assert finished_game_ttl([{"x": 1}], now, None, lean=True) is None


def test_the_settle_rule_names_its_game(tmp_path):
    h = ScheduleHarness(tmp_path, utc(2026, 10, 25, 2, 0), 30000)
    try:
        client = h.client
        assert client._settling("/games/players", {"year": "2026", "week": "5", "team": "A"}) is True  # no game named: as before
        client.settle_until = utc(2026, 10, 25, 23, 0)
        client.settle_game = {"gameId": 88, "week": 8, "seasonType": "regular"}
        assert client._settling("/games/players", {"year": "2026", "week": "8", "team": "A"}) is True
        assert client._settling("/games/players", {"year": "2026", "week": "5", "team": "B"}) is False  # weeks ago: permanent
        assert client._settling("/games/teams", {"year": "2026", "week": "8", "team": "B", "seasonType": "postseason"}) is False
        assert client._settling("/game/box/advanced", {"id": "88"}) is True
        assert client._settling("/metrics/wp", {"gameId": "77"}) is False
        status = client.quota.status(client._clock())
        assert client._ttl(DataKind.FINISHED_GAME, [{"x": 1}], client._clock(), status, endpoint="/games/players", params={"week": "5"}) is None
        assert client._ttl(DataKind.FINISHED_GAME, [{"x": 1}], client._clock(), status, endpoint="/games/players", params={"week": "8"}) == timedelta(hours=1)
    finally:
        h.close()


# --- restricted mode ----------------------------------------------------------------------------------------------------


def test_restricted_mode_keeps_the_slate_and_the_schedule(guard):  # noqa: F811
    burn(guard, 90)
    assert guard.status(NOW).mode is QuotaMode.RESTRICTED
    with pytest.raises(QuotaBlocked, match="slate"):
        guard.check(live=False, now=NOW)
    assert guard.check(live=False, now=NOW, essential=True).mode is QuotaMode.RESTRICTED
    assert guard.check(live=True, now=NOW).mode is QuotaMode.RESTRICTED
    burn(guard, 7)
    with pytest.raises(QuotaBlocked, match="exhausted"):
        guard.check(live=False, now=NOW, essential=True)  # EXHAUSTED stops the essential calls too


# --- where the calls go ----------------------------------------------------------------------------------------------


def test_the_ledger_breakdown_by_endpoint_and_day(guard):  # noqa: F811
    burn(guard, 3)
    guard.record("/scoreboard", 200, True, live=True, now=NOW + timedelta(days=1))
    guard.record("/scoreboard", 500, False, live=True, now=NOW + timedelta(days=1))
    out = guard.breakdown(NOW + timedelta(days=1))
    assert out["month"] == NOW.strftime("%Y-%m") and out["total"] == 5 and out["live"] == 2
    assert out["byEndpoint"][0] == {"endpoint": "/games", "calls": 3, "live": 0, "failed": 0}
    assert out["byEndpoint"][1] == {"endpoint": "/scoreboard", "calls": 2, "live": 2, "failed": 1}
    assert [d["calls"] for d in out["byDay"]] == [2, 3]  # newest day first


def test_the_calls_route_answers_the_breakdown(client: TestClient):
    body = client.get("/api/quota/calls").json()
    data = body["data"]
    assert set(data) >= {"month", "total", "live", "byEndpoint", "byDay", "profile"}
    assert isinstance(data["byEndpoint"], list) and data["profile"] in ("free", "full")


def test_health_says_which_profile_the_schedules_follow(client: TestClient):
    body = client.get("/api/health").json()
    rows = body["data"]["publications"]
    assert rows and all(isinstance(s["lean"], bool) for s in rows)


# --- the rehearsal tool -----------------------------------------------------------------------------------------------


def test_the_rehearsal_patterns_cover_the_game_and_the_week():
    from tools.quota_rehearsal import MON, PAGES, SAT, SUN, at, daily_pattern, dig, weekend_pattern

    monday = datetime(2026, 10, 26, 0, 0, tzinfo=EASTERN)
    kickoff = at(monday, SAT, 19, 0)
    final = kickoff + timedelta(hours=3, minutes=12)
    weekend = weekend_pattern(monday, kickoff, final)
    ticks = [s for s in weekend if "live" in s[1]]
    assert ticks[0][0] == kickoff - timedelta(minutes=30) and ticks[-1][0] >= final
    assert all(s[0].weekday() in (SAT, SUN) for s in weekend)
    daily = daily_pattern(monday, kickoff, final)
    assert len(daily) == len(weekend) + 5 and any(s[0].weekday() == MON and "team_opponent" in s[1] for s in daily)
    assert every_page_is_known(daily)
    assert dig({"a": [{"b": {"gameId": 7}}]}, "gameId") == 7 and dig([], "gameId") is None
    assert PAGES["live"][0] == "/api/live/status"


def every_page_is_known(steps) -> bool:
    from tools.quota_rehearsal import PAGES

    return all(page == "team_opponent" or page in PAGES for _, pages in steps for page in pages)
