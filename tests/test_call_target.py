"""ENH-27 (owner 2026-10-25: "We also want to use all the calls we can as opposed to limiting the calls" and "Let's target
2/3rds in a month"): the month's target for the background loads, kept in step with the calendar, with the rest of the
budget held back for pages someone opens and live games; and the shorter cache lifetimes that spend it."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.cache import DataKind, ttl_for
from app.cfbd.client import CfbdClient, paced_calls
from app.cfbd.quota import QuotaBlocked, QuotaGuard, pace_allowed
from app.config import load_settings
from app.db import Database
from tests.conftest import TEST_KEY, FakeCfbd, FakeClock, fixture_payload

OCT_15 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def test_the_target_is_shared_out_over_the_month():
    assert pace_allowed(20000, datetime(2026, 10, 1, 1, tzinfo=timezone.utc)) == 645  # a 31st of it on the first
    assert pace_allowed(20000, OCT_15) == 9677
    assert pace_allowed(20000, datetime(2026, 10, 31, 23, tzinfo=timezone.utc)) == 20000
    assert pace_allowed(20000, datetime(2026, 2, 14, tzinfo=timezone.utc)) == 10000  # February has 28 days
    assert pace_allowed(0, OCT_15) == 0


@pytest.fixture
def guard(tmp_path):
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, monthly_call_budget=300, monthly_call_target=200)
    db = Database(tmp_path / "q.db")
    yield QuotaGuard(db, settings)
    db.close()


def burn(guard: QuotaGuard, calls: int, at: datetime = OCT_15) -> None:
    for _ in range(calls):
        guard.record("/games", 200, True, live=False, now=at)


def test_paced_calls_stop_at_the_days_share_and_nothing_else_does(guard):
    allowed = pace_allowed(200, OCT_15)  # 97 of 200 by the 15th
    burn(guard, allowed - 1)
    status = guard.check(live=False, now=OCT_15, paced=True)
    assert status.target == 200 and status.pace_allowed == allowed and status.paced_open is True
    burn(guard, 1)
    with pytest.raises(QuotaBlocked, match="keep to the month's target"):
        guard.check(live=False, now=OCT_15, paced=True)
    assert guard.check(live=False, now=OCT_15).paced_open is False, "a page someone opened still goes"
    assert guard.check(live=True, now=OCT_15, paced=True), "a live call is never paced"
    tomorrow = OCT_15 + timedelta(days=1)
    assert guard.check(live=False, now=tomorrow, paced=True).paced_open, "the next day's share opens"


def test_the_target_is_never_more_than_two_thirds_of_the_budget(tmp_path):
    # Kickoff Companion 2.0: ENH-27's two thirds, of the key's own month, so a Free key's pages keep 334 calls
    for budget, target, expected in ((1000, 20000, 666), (30000, 20000, 20000), (30000, 5000, 5000)):
        settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, monthly_call_budget=budget, monthly_call_target=target)
        db = Database(tmp_path / f"q{budget}-{target}.db")
        try:
            assert QuotaGuard(db, settings).status(OCT_15).target == expected, (budget, target)
        finally:
            db.close()


def test_a_paced_block_serves_the_cached_copy_and_a_page_still_asks(tmp_path):
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, data_dir=str(tmp_path), monthly_call_budget=300, monthly_call_target=200)
    db = Database(tmp_path / "t.db")
    upstream = FakeCfbd()
    upstream.route("/games", json=fixture_payload("games_team"))
    clock = FakeClock(OCT_15)
    client = CfbdClient(settings, db, transport=upstream.transport, clock=clock)
    client.quota.mark_reconcile_attempt(clock())
    client.quota.needs_reconcile = False

    async def go() -> None:
        try:
            first = await client.get("/games", {"year": 2026, "team": "Florida"}, kind=DataKind.SCHEDULE)
            assert first.source == "live"
            burn(client.quota, pace_allowed(200, OCT_15))
            clock.advance(hours=6)  # the copy is out of date now (a 300-call month is the Free profile: four hours on a Thursday)
            with paced_calls():
                held = await client.get("/games", {"year": 2026, "team": "Florida"}, kind=DataKind.SCHEDULE)
            assert held.stale and "target" in (held.error or ""), "the background load waits and the copy is served"
            with pytest.raises(QuotaBlocked):
                with paced_calls():
                    await client.get("/games", {"year": 2026, "team": "Texas"}, kind=DataKind.SCHEDULE)
            page = await client.get("/games", {"year": 2026, "team": "Texas"}, kind=DataKind.SCHEDULE)
            assert page.source == "live", "a page someone opened goes on into the reserve"
        finally:
            await client.aclose()
            db.close()

    asyncio.run(go())


def test_the_shorter_lifetimes_spend_it():
    monday, thursday = datetime(2026, 10, 19, 12, 0), datetime(2026, 10, 22, 12, 0)
    assert ttl_for(DataKind.SCHEDULE, thursday) == timedelta(minutes=15)
    assert ttl_for(DataKind.SCHEDULE, monday) == timedelta(hours=1)
    assert ttl_for(DataKind.SEASON_STATS, monday) == timedelta(hours=1)
    assert ttl_for(DataKind.LINES, monday) == timedelta(hours=1) and ttl_for(DataKind.WEATHER, monday, game_day=True) == timedelta(minutes=15)
