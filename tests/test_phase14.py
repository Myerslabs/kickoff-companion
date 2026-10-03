"""Phase 14: publication schedules (weekly data kept until it can change), rechecks, the change log,
and the server's prewarm of polls and ratings."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.cache import DataKind, cache_key
from app.cfbd.client import CfbdClient
from app.cfbd.publish import (
    MIN_LIFETIME,
    POLLS,
    RATINGS,
    RESULTS,
    PublicationLog,
    game_days,
    learn_game_days,
    schedule_for,
    set_game_days,
)
from app.config import load_settings
from app.db import Database
from tests.conftest import TEST_KEY, FakeCfbd, FakeClock

# Sunday 2026-09-27 is on Eastern daylight time (UTC-4): 06:00 ET is 10:00Z, 13:00 ET is 17:00Z.
SUN_0500Z = datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc)
SAT_NOON_ET = datetime(2026, 9, 26, 16, 0, tzinfo=timezone.utc)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


# --- slots ---------------------------------------------------------------------------------------


def test_poll_slots_are_sunday_afternoon_and_tuesday_evening_eastern():
    assert POLLS.next_slot(SAT_NOON_ET) == utc(2026, 9, 27, 17, 0)  # Sunday 1 p.m. ET
    assert POLLS.next_slot(utc(2026, 9, 27, 17, 30)) == utc(2026, 9, 27, 18, 0)  # 2 p.m. ET
    assert POLLS.next_slot(utc(2026, 9, 27, 18, 0)) == utc(2026, 9, 29, 23, 30)  # Tuesday 7:30 p.m. ET
    assert POLLS.last_slot(utc(2026, 9, 28, 12, 0)) == utc(2026, 9, 27, 18, 0)


def test_slots_follow_eastern_time_across_the_clock_change():
    # 2026-11-01 ends daylight time: Sunday 6 a.m. ET is 11:00Z from then on.
    assert RATINGS.next_slot(utc(2026, 10, 30, 0, 0)) == utc(2026, 11, 1, 11, 0)
    assert RATINGS.next_slot(utc(2026, 10, 20, 0, 0)) == utc(2026, 10, 25, 10, 0)


def test_results_update_every_morning_and_sunday_noon():
    assert RESULTS.next_slot(SAT_NOON_ET) == utc(2026, 9, 27, 8, 0)  # Sunday 4 a.m. ET
    assert RESULTS.next_slot(utc(2026, 9, 27, 9, 0)) == utc(2026, 9, 27, 16, 0)  # Sunday noon ET
    assert RESULTS.next_slot(utc(2026, 9, 27, 16, 0)) == utc(2026, 9, 28, 8, 0)


def test_schedule_only_replaces_season_kinds():
    assert schedule_for("/ratings/sp", DataKind.SEASON_STATS) is RATINGS
    assert schedule_for("/rankings", DataKind.SCHEDULE) is POLLS
    assert schedule_for("/ppa/games", DataKind.FINISHED_GAME) is None  # a finished game keeps its own rule
    assert schedule_for("/games", DataKind.SCHEDULE) is None  # the schedule still refreshes on game day
    assert schedule_for("/scoreboard", DataKind.SCOREBOARD) is None


# --- lifetimes -----------------------------------------------------------------------------------


def test_a_new_answer_lives_until_the_next_slot():
    now = utc(2026, 9, 28, 12, 0)  # Monday
    assert RATINGS.lifetime(now, changed_at=None, unchanged=False) == utc(2026, 10, 4, 10, 0) - now


def test_an_unchanged_answer_after_the_slot_is_rechecked():
    now = utc(2026, 9, 27, 12, 0)  # two hours after Sunday's ratings slot
    before_slot = utc(2026, 9, 21, 12, 0)
    assert RATINGS.lifetime(now, changed_at=before_slot, unchanged=True) == timedelta(hours=3)


def test_the_recheck_stops_when_the_watch_ends():
    now = utc(2026, 10, 1, 12, 0)  # Thursday, past the four-day watch
    before_slot = utc(2026, 9, 21, 12, 0)
    assert RATINGS.lifetime(now, changed_at=before_slot, unchanged=True) == utc(2026, 10, 4, 10, 0) - now


def test_an_answer_that_changed_after_the_slot_waits_for_the_next():
    now = utc(2026, 9, 27, 12, 0)
    assert RATINGS.lifetime(now, changed_at=utc(2026, 9, 27, 11, 0), unchanged=True) == utc(2026, 10, 4, 10, 0) - now


def test_a_slot_seconds_away_still_keeps_the_answer_a_few_minutes():
    now = utc(2026, 9, 27, 16, 59, 50)
    assert POLLS.lifetime(now, changed_at=None, unchanged=False) == MIN_LIFETIME


# --- the client ------------------------------------------------------------------------------------


class Harness:
    def __init__(self, tmp_path, start: datetime):
        self.settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, data_dir=str(tmp_path))
        self.db = Database(tmp_path / "t.db")
        self.upstream = FakeCfbd()
        self.clock = FakeClock(start)
        self.client = CfbdClient(self.settings, self.db, transport=self.upstream.transport, clock=self.clock)
        self.client.quota.mark_reconcile_attempt(self.clock())
        self.client.quota.needs_reconcile = False
        self.payloads = {"sp": [{"team": "Swampwater Tech", "rating": 20.1}]}

        def sp(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=self.payloads["sp"])

        self.upstream.route("/ratings/sp", handler=sp)
        self.upstream.route("/rankings", json=[{"season": 2026, "week": 5, "polls": []}])

    def get_sp(self, **kwargs):
        return asyncio.run(self.client.get("/ratings/sp", {"year": 2026}, kind=DataKind.SEASON_STATS, **kwargs))

    def close(self) -> None:
        asyncio.run(self.client.aclose())
        self.db.close()


@pytest.fixture
def make(tmp_path):
    made: list[Harness] = []

    def factory(start: datetime) -> Harness:
        h = Harness(tmp_path, start)
        made.append(h)
        return h

    yield factory
    for h in made:
        h.close()


def test_ratings_are_not_asked_for_again_all_week(make):
    h = make(utc(2026, 9, 28, 12, 0))  # Monday
    h.get_sp()
    for hours in (1, 6, 24, 72, 120):  # the old rule asked again every hour on the weekend
        h.clock.now = utc(2026, 9, 28, 12, 0) + timedelta(hours=hours)
        assert h.get_sp().source == "cache"
    assert h.upstream.count("/ratings/sp") == 1
    entry = h.client.cache.get(cache_key("/ratings/sp", {"year": 2026}))
    assert entry.expires_at == utc(2026, 10, 4, 10, 0)


def test_ratings_are_rechecked_after_the_slot_until_they_change_then_logged(make):
    h = make(utc(2026, 9, 26, 12, 0))  # Saturday: the old week's SP+
    h.get_sp()
    h.clock.now = utc(2026, 9, 27, 10, 30)  # Sunday, past the 6 a.m. ET slot: CFBD still has last week's
    assert h.get_sp().source == "live"
    h.clock.advance(hours=1)
    assert h.get_sp().source == "cache"  # the recheck is three hours
    h.clock.advance(hours=2)
    h.payloads["sp"] = [{"team": "Swampwater Tech", "rating": 22.4}]  # CFBD loads the new ratings
    assert h.get_sp().payload == [{"team": "Swampwater Tech", "rating": 22.4}]
    h.clock.advance(hours=3)
    assert h.get_sp().source == "cache"  # changed after the slot: kept until next Sunday
    assert h.upstream.count("/ratings/sp") == 3
    summary = {s["name"]: s for s in h.client.publications.summary(h.clock())}
    change = summary["ratings"]["changes"][0]
    assert change["endpoint"] == "/ratings/sp"
    assert change["afterSlotMinutes"] == 210  # 13:30Z against the 10:00Z slot
    assert change["checks"] == 2


def test_scheduled_lifetimes_are_not_scaled_by_a_small_budget(make):
    h = make(utc(2026, 9, 28, 12, 0))
    h.client.quota.budget = 1000  # a tight month would multiply ordinary lifetimes
    h.get_sp()
    entry = h.client.cache.get(cache_key("/ratings/sp", {"year": 2026}))
    assert entry.expires_at == utc(2026, 10, 4, 10, 0)


def test_prewarm_refreshes_what_a_page_asked_for_once_the_slot_passes(make):
    h = make(utc(2026, 9, 26, 12, 0))
    h.get_sp()
    asyncio.run(h.client.get("/rankings", {"year": 2026}, kind=DataKind.SCHEDULE))
    assert asyncio.run(h.client.prewarm()) == 0  # nothing expired yet
    h.clock.now = utc(2026, 9, 27, 18, 5)  # after the ratings and both poll slots
    assert asyncio.run(h.client.prewarm()) == 2
    assert h.upstream.count("/ratings/sp") == 2 and h.upstream.count("/rankings") == 2
    assert asyncio.run(h.client.prewarm()) == 0  # fresh again (rechecks come later)


def test_prewarm_waits_out_a_live_game(make):
    h = make(utc(2026, 9, 26, 12, 0))
    h.get_sp()
    h.clock.now = utc(2026, 9, 27, 12, 0)
    h.client.live_window = True
    assert asyncio.run(h.client.prewarm()) == 0
    assert h.upstream.count("/ratings/sp") == 1


def test_prewarm_drops_keys_no_page_has_asked_for_in_two_weeks(make):
    h = make(utc(2026, 9, 26, 12, 0))
    h.get_sp()
    h.clock.now = utc(2026, 10, 12, 12, 0)
    assert asyncio.run(h.client.prewarm()) == 0


def test_a_cache_hit_keeps_the_key_on_the_prewarm_list(make):
    h = make(utc(2026, 9, 26, 12, 0))
    h.get_sp()
    log = h.client.publications
    h.clock.now = utc(2026, 9, 26, 20, 0)
    assert h.get_sp().source == "cache"
    keys = log.prewarm_keys(utc(2026, 10, 10, 12, 0))  # 14 days after the cache hit, not the call
    assert [k[1] for k in keys] == ["/ratings/sp"]


def test_the_publication_log_survives_a_bad_row(tmp_path):
    db = Database(tmp_path / "t.db")
    log = PublicationLog(db)
    log.record("k", "/ratings/sp", {"year": "2026"}, RATINGS, [1], utc(2026, 9, 27, 12, 0), asked=True)
    with db.transaction() as conn:
        conn.execute("UPDATE publications SET params = 'not json', changed_at = 'garbage'")
    assert log.prewarm_keys(utc(2026, 9, 27, 13, 0)) == []
    assert log.seen("k") is None
    db.close()


def test_health_lists_the_schedules(client):
    body = client.get("/api/health").json()
    names = [s["name"] for s in body["data"]["publications"]]
    assert names == ["polls", "ratings", "results", "media", "daily", "yearly"]
    assert all(s["nextSlot"].endswith("Z") for s in body["data"]["publications"])


# --- stats from games follow the game days ----------------------------------------------------------


@pytest.fixture(autouse=True)
def no_game_days():
    set_game_days(frozenset())
    yield
    set_game_days(frozenset())


def week_of_games():
    # Thursday 10/1, Friday 10/2 and Saturday 10/3 games (kickoffs in UTC; the Saturday night game
    # ends past midnight Eastern but kicks off Saturday).
    return [
        {"id": 1, "startDate": "2026-10-01T23:30:00.000Z"},
        {"id": 2, "startDate": "2026-10-03T00:00:00.000Z"},  # Friday 8 p.m. ET
        {"id": 3, "startDate": "2026-10-03T16:00:00.000Z"},
        {"id": 4, "startDate": "2026-10-04T02:30:00.000Z"},  # Saturday 10:30 p.m. ET
        {"id": 5, "startDate": None},
        {"id": 6, "startDate": "not a date"},
        "junk",
    ]


def test_game_days_come_from_the_schedule_in_eastern_time():
    assert learn_game_days(week_of_games()) == 3
    assert game_days() == {date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)}
    assert learn_game_days(week_of_games()) == 0
    assert learn_game_days({"not": "a list"}) == 0


def test_results_skip_the_quiet_weekdays():
    learn_game_days(week_of_games())
    monday = utc(2026, 9, 28, 12, 0)  # after Monday's 4 a.m. look
    # Nothing Tuesday, Wednesday or Thursday: the next look is Friday 4 a.m. ET, after Thursday's game.
    assert RESULTS.next_slot(monday) == utc(2026, 10, 2, 8, 0)
    assert RESULTS.next_slot(utc(2026, 10, 2, 8, 0)) == utc(2026, 10, 3, 8, 0)  # Saturday, after Friday's
    assert RESULTS.next_slot(utc(2026, 10, 3, 8, 0)) == utc(2026, 10, 4, 8, 0)  # Sunday 4 a.m.
    assert RESULTS.next_slot(utc(2026, 10, 4, 8, 0)) == utc(2026, 10, 4, 16, 0)  # Sunday noon
    assert RESULTS.next_slot(utc(2026, 10, 4, 16, 0)) == utc(2026, 10, 5, 8, 0)  # Monday corrections
    assert RESULTS.next_slot(utc(2026, 10, 5, 8, 0)) == utc(2026, 10, 12, 8, 0)  # no games known after


def test_results_fall_back_to_every_morning_until_the_game_days_are_known():
    assert RESULTS.next_slot(utc(2026, 9, 29, 12, 0)) == utc(2026, 9, 30, 8, 0)


def test_the_client_learns_game_days_from_a_games_answer(make):
    h = make(utc(2026, 9, 28, 12, 0))
    h.upstream.route("/games", json=week_of_games())
    asyncio.run(h.client.get("/games", {"year": 2026}, kind=DataKind.SCHEDULE))
    assert date(2026, 10, 3) in game_days()


def test_a_restart_reads_the_game_days_from_the_cached_schedule(make, tmp_path):
    h = make(utc(2026, 9, 28, 12, 0))
    h.upstream.route("/games", json=week_of_games())
    asyncio.run(h.client.get("/games", {"year": 2026}, kind=DataKind.SCHEDULE))
    set_game_days(frozenset())
    again = CfbdClient(h.settings, h.db, transport=h.upstream.transport, clock=h.clock)
    asyncio.run(again.aclose())
    assert date(2026, 10, 1) in game_days()
