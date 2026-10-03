"""The SQLite cache: keys, TTL policy, stale entries kept, permanent entries, stats."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.cache import NO_CACHE, Cache, DataKind, cache_key, canonical_params, ttl_for
from app.db import Database

MONDAY = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
SATURDAY = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
SUNDAY = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def cache(tmp_path):
    db = Database(tmp_path / "cache.db")
    yield Cache(db)
    db.close()


def test_canonical_params_are_sorted_stringified_and_skip_none():
    assert canonical_params({"week": 3, "year": 2026, "team": "Swampwater Tech", "extra": None, "flag": True, "off": False}) == {
        "flag": "true",
        "off": "false",
        "team": "Swampwater Tech",
        "week": "3",
        "year": "2026",
    }
    assert canonical_params(None) == {}


def test_cache_key_is_order_independent():
    assert cache_key("/games", {"year": 2026, "team": "Swampwater Tech"}) == cache_key("/games", {"team": "Swampwater Tech", "year": 2026})
    assert cache_key("/games", None) == "/games"
    assert cache_key("/games", {"team": "Swampwater Tech"}) == "/games?team=Swampwater+Tech"


@pytest.mark.parametrize(
    ("kind", "when", "game_day", "expected"),
    [
        (DataKind.TEAMS, MONDAY, False, timedelta(days=7)),
        (DataKind.ROSTER, SATURDAY, False, timedelta(days=7)),
        (DataKind.RECRUITING, MONDAY, False, timedelta(days=7)),
        (DataKind.REFERENCE, MONDAY, False, timedelta(days=7)),
        (DataKind.HISTORY, MONDAY, False, timedelta(days=30)),
        (DataKind.SCHEDULE, MONDAY, False, timedelta(hours=12)),
        (DataKind.SCHEDULE, SATURDAY, False, timedelta(minutes=15)),
        (DataKind.SCHEDULE, SUNDAY, False, timedelta(hours=12)),
        (DataKind.SEASON_STATS, MONDAY, False, timedelta(hours=6)),
        (DataKind.SEASON_STATS, SATURDAY, False, timedelta(hours=1)),
        (DataKind.SEASON_STATS, SUNDAY, False, timedelta(hours=1)),
        (DataKind.LINES, MONDAY, False, timedelta(hours=3)),
        (DataKind.LINES, MONDAY, True, timedelta(minutes=30)),
        (DataKind.WEATHER, SATURDAY, True, timedelta(minutes=30)),
        (DataKind.FINISHED_GAME, MONDAY, False, None),
        (DataKind.SCOREBOARD, MONDAY, False, timedelta(seconds=15)),
        (DataKind.LIVE, SATURDAY, True, NO_CACHE),
        (DataKind.INFO, MONDAY, False, NO_CACHE),
    ],
)
def test_ttl_policy_matches_the_architecture_table(kind, when, game_day, expected):
    assert ttl_for(kind, when, game_day=game_day) == expected


def test_put_get_roundtrip_and_freshness(cache):
    key = cache_key("/games", {"year": 2026})
    entry = cache.put(key, "/games", {"year": 2026}, [{"id": 1}], fetched_at=MONDAY, ttl=timedelta(hours=1))
    assert entry.size_bytes == len(b'[{"id":1}]')
    got = cache.get(key)
    assert got is not None
    assert got.payload == [{"id": 1}]
    assert got.params == {"year": "2026"}
    assert got.fetched_at == MONDAY
    assert got.is_fresh(MONDAY + timedelta(minutes=59))
    assert not got.is_fresh(MONDAY + timedelta(hours=1))
    assert got.age_seconds(MONDAY + timedelta(minutes=2)) == 120.0


def test_expired_entries_are_kept_for_stale_serving(cache):
    cache.put("k", "/x", None, {"a": 1}, fetched_at=MONDAY, ttl=timedelta(seconds=1))
    got = cache.get("k")
    assert got is not None
    assert not got.is_fresh(MONDAY + timedelta(days=3))
    assert got.payload == {"a": 1}


def test_permanent_entries_never_expire(cache):
    cache.put("k", "/plays", None, [1, 2, 3], fetched_at=MONDAY, ttl=None)
    got = cache.get("k")
    assert got is not None
    assert got.expires_at is None
    assert got.is_fresh(MONDAY + timedelta(days=3650))


def test_no_cache_kind_stores_nothing(cache):
    cache.put("k", "/live/plays", None, {"live": True}, fetched_at=MONDAY, ttl=NO_CACHE)
    assert cache.get("k") is None


def test_replace_overwrites(cache):
    cache.put("k", "/x", None, 1, fetched_at=MONDAY, ttl=timedelta(hours=1))
    cache.put("k", "/x", None, 2, fetched_at=MONDAY + timedelta(minutes=5), ttl=timedelta(hours=1))
    got = cache.get("k")
    assert got is not None and got.payload == 2
    assert got.fetched_at == MONDAY + timedelta(minutes=5)


def test_corrupt_rows_are_treated_as_missing(cache):
    with cache.db.transaction() as conn:
        conn.execute(
            "INSERT INTO cache (key, endpoint, params, payload, fetched_at, expires_at, size_bytes)"
            " VALUES ('bad', '/x', '{}', 'not json', '2026-09-21T12:00:00+00:00', NULL, 8)"
        )
        conn.execute(
            "INSERT INTO cache (key, endpoint, params, payload, fetched_at, expires_at, size_bytes)"
            " VALUES ('baddate', '/x', '{}', '1', 'yesterday', NULL, 1)"
        )
    assert cache.get("bad") is None
    assert cache.get("baddate") is None


def test_stats_and_clear(cache):
    cache.put("a", "/x", None, [1], fetched_at=MONDAY, ttl=timedelta(hours=1))
    cache.put("b", "/y", None, [2], fetched_at=MONDAY, ttl=timedelta(seconds=1))
    stats = cache.stats(MONDAY + timedelta(minutes=10))
    assert stats["entries"] == 2
    assert stats["fresh"] == 1
    assert stats["size_bytes"] == 6
    assert stats["db_bytes"] > 0
    assert cache.clear() == 2
    assert cache.stats(MONDAY)["entries"] == 0
