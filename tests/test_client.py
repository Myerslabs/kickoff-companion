"""The CFBD client: cache, single-flight, retries, breaker, stale-while-error, quota, /info."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import pytest

from app.cache import DataKind, cache_key
from app.cfbd.client import (
    BREAKER_OPEN_SECONDS,
    BREAKER_THRESHOLD,
    MAX_ATTEMPTS,
    CfbdClient,
    CfbdRequestError,
    CfbdUnavailable,
    backoff_seconds,
)
from app.cfbd.quota import QuotaBlocked
from app.config import load_settings
from app.db import Database
from tests.conftest import TEST_KEY, FakeCfbd, FakeClock, fixture_payload

GAMES = fixture_payload("games_team")


class Harness:
    def __init__(self, tmp_path, **overrides):
        self.settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, data_dir=str(tmp_path), **overrides)
        self.db = Database(tmp_path / "t.db")
        self.upstream = FakeCfbd()
        self.clock = FakeClock()
        self.sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            self.clock.advance(seconds=seconds)

        self.client = CfbdClient(self.settings, self.db, transport=self.upstream.transport, clock=self.clock, sleep=fake_sleep)
        # The app reconciles at startup; tests decide themselves when /info is called.
        self.client.quota.mark_reconcile_attempt(self.clock())
        self.client.quota.needs_reconcile = False

    async def close(self) -> None:
        await self.client.aclose()
        self.db.close()


@pytest.fixture
def harness(tmp_path):
    h = Harness(tmp_path)
    yield h
    asyncio.run(h.close())


def run(coro):
    return asyncio.run(coro)


def test_get_caches_and_serves_from_cache(harness):
    harness.upstream.route("/games", json=GAMES)

    async def scenario():
        first = await harness.client.get("/games", {"year": 2026, "team": "Swampwater Tech"}, kind=DataKind.SCHEDULE)
        second = await harness.client.get("/games", {"team": "Swampwater Tech", "year": 2026}, kind=DataKind.SCHEDULE)
        return first, second

    first, second = run(scenario())
    assert first.source == "live" and first.stale is False and first.payload == GAMES
    assert second.source == "cache" and second.stale is False and second.age_seconds == 0.0
    assert harness.upstream.count("/games") == 1
    assert harness.client.stats["cache_hits"] == 1
    request = harness.upstream.requests[0]
    assert request.headers["authorization"] == f"Bearer {TEST_KEY}"
    assert request.url.params["team"] == "Swampwater Tech"


def test_ttl_is_scaled_to_a_small_budget(harness):
    harness.upstream.route("/games", json=GAMES)

    async def scenario():
        await harness.client.reconcile()  # the fake /info says Free tier, 1,000 calls
        await harness.client.get("/games", {"year": 2026}, kind=DataKind.SCHEDULE)

    run(scenario())
    entry = harness.client.cache.get(cache_key("/games", {"year": 2026}))
    assert entry is not None
    assert entry.expires_at == entry.fetched_at + timedelta(hours=12) * 4  # Monday, x4 for a 1,000-call budget


def test_expired_entry_is_refreshed(harness):
    harness.upstream.route("/games", sequence=[httpx.Response(200, json=[{"id": 1}]), httpx.Response(200, json=[{"id": 2}])])

    async def scenario():
        await harness.client.get("/games", kind=DataKind.SCOREBOARD)  # 15 s TTL
        harness.clock.advance(seconds=20)
        return await harness.client.get("/games", kind=DataKind.SCOREBOARD)

    fetched = run(scenario())
    assert fetched.source == "live" and fetched.payload == [{"id": 2}]
    assert harness.upstream.count("/games") == 2


def test_stale_is_served_when_upstream_fails(harness):
    harness.upstream.route(
        "/games", sequence=[httpx.Response(200, json=[{"id": 1}]), httpx.Response(503, text="down")]
    )

    async def scenario():
        await harness.client.get("/games", kind=DataKind.SCOREBOARD)
        harness.clock.advance(seconds=20)
        return await harness.client.get("/games", kind=DataKind.SCOREBOARD)

    fetched = run(scenario())
    assert fetched.source == "cache" and fetched.stale is True
    assert fetched.payload == [{"id": 1}]
    assert fetched.age_seconds >= 20
    assert "HTTP 503" in (fetched.error or "")
    assert harness.upstream.count("/games") == 1 + MAX_ATTEMPTS
    assert harness.client.stats["stale_serves"] == 1
    assert harness.client.breaker.failures == 1


def test_no_cache_and_upstream_down_raises(harness):
    harness.upstream.route("/records", status=502, text="bad gateway")
    with pytest.raises(CfbdUnavailable, match="HTTP 502"):
        run(harness.client.get("/records", kind=DataKind.SCHEDULE))
    assert harness.upstream.count("/records") == MAX_ATTEMPTS
    assert len(harness.sleeps) == MAX_ATTEMPTS - 1
    assert harness.sleeps[0] < harness.sleeps[1] < harness.sleeps[2]


def test_timeouts_are_retried_then_fail(harness):
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    harness.upstream.route("/records", handler=boom)
    with pytest.raises(CfbdUnavailable, match="ReadTimeout"):
        run(harness.client.get("/records", kind=DataKind.SCHEDULE))
    assert harness.upstream.count("/records") == MAX_ATTEMPTS
    assert harness.client.quota.status(harness.clock()).ledger_calls_this_month == MAX_ATTEMPTS


def test_429_honours_retry_after(harness):
    harness.upstream.route(
        "/records",
        sequence=[httpx.Response(429, headers={"Retry-After": "3"}, text="slow down"), httpx.Response(200, json=[])],
    )
    fetched = run(harness.client.get("/records", kind=DataKind.SCHEDULE))
    assert fetched.payload == []
    assert harness.sleeps == [3.0]


def test_backoff_grows_and_caps():
    assert 0.5 <= backoff_seconds(1) <= 0.75
    assert 1.0 <= backoff_seconds(2) <= 1.25
    assert 8.0 <= backoff_seconds(10) <= 8.25
    assert backoff_seconds(1, retry_after=99) == 10.0


def test_non_retryable_4xx_raises_without_retry(harness):
    harness.upstream.route("/records", status=400, text='{"message":"bad week"}')
    with pytest.raises(CfbdRequestError) as info:
        run(harness.client.get("/records", {"week": "x"}, kind=DataKind.SCHEDULE))
    assert info.value.status == 400
    assert info.value.tier_gate is False
    assert harness.upstream.count("/records") == 1
    assert harness.client.breaker.failures == 0


def test_tier_gate_401_is_recognised_and_capability_switched_off(harness, caplog):
    harness.upstream.fixture("/games/weather", "games_weather")
    with pytest.raises(CfbdRequestError) as info:
        run(harness.client.get("/games/weather", {"year": 2026}, kind=DataKind.WEATHER))
    assert info.value.status == 401
    assert info.value.tier_gate is True
    assert harness.client.capabilities.weather is False
    assert harness.client.stats["last_error"] is None, "a tier gate is not an upstream failure"
    assert "rejected the API key" not in caplog.text


def test_plain_401_is_reported_as_a_bad_key(harness, caplog):
    harness.upstream.route("/records", status=401, text='{"message":"Unauthorized"}')
    with pytest.raises(CfbdRequestError) as info:
        run(harness.client.get("/records", kind=DataKind.SCHEDULE))
    assert info.value.tier_gate is False
    assert "rejected the API key" in caplog.text
    assert TEST_KEY not in caplog.text


def test_breaker_opens_after_repeated_failures_and_recovers(harness):
    harness.upstream.route("/records", status=503, text="down")
    harness.upstream.route("/games", json=GAMES)

    async def scenario():
        await harness.client.get("/games", kind=DataKind.SCHEDULE)  # something to serve stale later
        for _ in range(BREAKER_THRESHOLD):
            with pytest.raises(CfbdUnavailable):
                await harness.client.get("/records", kind=DataKind.SCHEDULE)
        assert harness.client.breaker.state(harness.clock()) == "open"
        calls_before = harness.upstream.count()

        harness.clock.advance(hours=13)  # schedule entry (12 h TTL on a Monday) expired; reopen the breaker as if it just tripped
        harness.client.breaker.opened_at = harness.clock() - timedelta(seconds=10)
        stale = await harness.client.get("/games", kind=DataKind.SCHEDULE)
        assert stale.stale is True and "paused" in (stale.error or "")
        with pytest.raises(CfbdUnavailable, match="paused"):
            await harness.client.get("/records", {"other": 1}, kind=DataKind.SCHEDULE)
        assert harness.upstream.count() == calls_before, "an open breaker makes no upstream calls"

        harness.clock.advance(seconds=BREAKER_OPEN_SECONDS)
        assert harness.client.breaker.state(harness.clock()) == "half_open"
        harness.upstream.route("/records", json=[{"team": "Swampwater Tech"}])
        recovered = await harness.client.get("/records", kind=DataKind.SCHEDULE)
        assert recovered.source == "live"
        assert harness.client.breaker.state(harness.clock()) == "closed"

    run(scenario())


def test_quota_blocks_new_calls_and_serves_stale(tmp_path):
    h = Harness(tmp_path, monthly_call_budget=10, quota_hard_stop_pct=90)
    try:
        h.upstream.route("/games", json=GAMES)
        h.upstream.route("/records", json=[])

        async def scenario():
            await h.client.get("/games", kind=DataKind.SCHEDULE)
            for _ in range(9):
                h.client.quota.record("/x", 200, True, live=False, now=h.clock())
            with pytest.raises(QuotaBlocked, match="exhausted"):
                await h.client.get("/records", kind=DataKind.SCHEDULE)
            h.clock.advance(days=3)  # past the Monday schedule lifetime, budget-scaled
            stale = await h.client.get("/games", kind=DataKind.SCHEDULE)
            return stale

        stale = run(scenario())
        assert stale.stale is True and "quota" in (stale.error or "").lower()
        assert h.upstream.count("/records") == 0
        assert h.client.stats["blocked_by_quota"] == 2
    finally:
        run(h.close())


def test_info_reconciles_quota_and_capabilities(harness):
    async def scenario():
        fetched = await harness.client.info()
        return fetched

    fetched = run(scenario())
    assert fetched.payload["tierName"] == "Free"
    status = harness.client.quota.status(harness.clock())
    assert status.reconciled is True and status.budget == 1000 and status.remaining == 1000
    caps = harness.client.capabilities
    assert caps.tier_name == "Free" and caps.live_plays is False and caps.monthly_limit == 1000
    assert harness.upstream.count("/info") == 1, "one /info call must not trigger a second"
    assert harness.client.status()["ttl_scale"] == 4


def test_reconcile_survives_upstream_failure(harness):
    harness.upstream.route("/info", status=503, text="down")
    status = run(harness.client.reconcile())
    assert status.reconciled is False
    assert harness.client.breaker.failures == 1


def test_maybe_reconcile_follows_the_schedule(harness):
    harness.client.quota.last_reconcile_attempt = None  # a fresh process

    async def scenario():
        first = await harness.client.maybe_reconcile()
        second = await harness.client.maybe_reconcile()
        harness.clock.advance(hours=7)
        third = await harness.client.maybe_reconcile()
        return first, second, third

    first, second, third = run(scenario())
    assert first is not None and second is None and third is not None
    assert harness.upstream.count("/info") == 2


def test_single_flight_shares_one_upstream_call(harness):
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=GAMES)

    harness.upstream.route("/games", handler=slow)

    async def scenario():
        return await asyncio.gather(
            *[harness.client.get("/games", {"year": 2026}, kind=DataKind.SCHEDULE) for _ in range(5)]
        )

    results = run(scenario())
    assert harness.upstream.count("/games") == 1
    assert [r.source for r in results].count("live") == 1
    assert all(r.payload == GAMES for r in results)


def test_non_json_body_is_a_failure(harness):
    harness.upstream.route("/records", text="<html>maintenance</html>")
    with pytest.raises(CfbdUnavailable, match="not JSON"):
        run(harness.client.get("/records", kind=DataKind.SCHEDULE))


def test_use_cache_false_bypasses_but_still_records(harness):
    harness.upstream.route("/games", json=GAMES)

    async def scenario():
        await harness.client.get("/games", kind=DataKind.SCHEDULE, use_cache=False)
        await harness.client.get("/games", kind=DataKind.SCHEDULE, use_cache=False)

    run(scenario())
    assert harness.upstream.count("/games") == 2
    assert harness.client.cache.get(cache_key("/games", None)) is None
    assert harness.client.quota.status(harness.clock()).ledger_calls_this_month == 2


def test_aclose_cancels_a_pending_background_reconcile(harness):
    async def slow_info(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.5)
        return httpx.Response(200, json=fixture_payload("info"))

    harness.upstream.route("/info", handler=slow_info)
    harness.upstream.route("/games", json=GAMES)

    async def scenario():
        harness.client.quota.last_reconcile_attempt = None
        harness.client.quota.needs_reconcile = True
        await harness.client.get("/games", kind=DataKind.SCHEDULE)  # schedules the check in the background
        task = harness.client._reconcile_task
        assert task is not None and not task.done()
        await harness.client.aclose()
        assert task.done()
        status = await harness.client.reconcile()  # after close: a no-op, never an error
        assert status.reconciled is False

    run(scenario())


def test_capabilities_are_restored_after_a_restart(tmp_path):
    first = Harness(tmp_path)
    run(first.client.reconcile())
    run(first.client.aclose())
    try:
        second = CfbdClient(first.settings, first.db, transport=first.upstream.transport, clock=first.clock)
        assert second.capabilities.tier_name == "Free"
        assert second.capabilities.live_plays is False
        assert second.capabilities.source == "stored"
        assert second.status()["ttl_scale"] == 4
        run(second.aclose())
    finally:
        first.db.close()


def test_status_shape(harness):
    status = harness.client.status()
    assert status["base_url"] == "https://api.collegefootballdata.com"
    closed = {"state": "closed", "consecutive_failures": 0, "retry_in_seconds": 0.0, "probe_seconds": None, "probe_stuck": False}
    assert status["breaker"] == closed
    assert status["live_breaker"] == closed
    assert status["settle_until"] is None and status["settling"] is False
    assert set(status["stats"]["lanes"]) == {"general", "live"}
    assert status["stats"]["lanes"]["live"] == {"calls": 0, "failures": 0, "last_success_at": None, "last_failure_at": None, "last_error": None}
    assert status["quota"]["mode"] == "normal"
    assert status["capabilities"]["source"] == "unknown"
    assert status["ttl_scale"] == 1
    assert status["live_window"] is False
    assert TEST_KEY not in str(status)


def test_calls_to_one_endpoint_run_one_at_a_time_while_endpoints_overlap(settings, tmp_path):
    """CFBD answers 429 to concurrent calls on one endpoint, so the client serialises per endpoint."""
    import asyncio

    import httpx

    from app.cache import DataKind
    from app.cfbd.client import CfbdClient
    from app.db import Database

    in_flight: dict[str, int] = {}
    peak: dict[str, int] = {}
    overlap = {"max": 0}
    active = {"total": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        in_flight[path] = in_flight.get(path, 0) + 1
        active["total"] += 1
        peak[path] = max(peak.get(path, 0), in_flight[path])
        overlap["max"] = max(overlap["max"], active["total"])
        await asyncio.sleep(0.02)
        in_flight[path] -= 1
        active["total"] -= 1
        return httpx.Response(200, json=[{"team": "Swampwater Tech", "statName": "x", "statValue": 1}])

    async def run() -> None:
        db = Database(tmp_path / "c.db")
        client = CfbdClient(settings, db, transport=httpx.MockTransport(handler))
        try:
            await asyncio.gather(
                *(client.get("/stats/player/season", {"year": 2026, "category": c}, kind=DataKind.SEASON_STATS) for c in ("a", "b", "c", "d")),
                client.get("/records", {"year": 2026}, kind=DataKind.SCHEDULE),
                client.get("/rankings", {"year": 2026}, kind=DataKind.SCHEDULE),
            )
        finally:
            await client.aclose()
            db.close()

    asyncio.run(run())
    assert peak["/stats/player/season"] == 1
    assert overlap["max"] >= 2  # other endpoints were not held up
