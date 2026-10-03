"""Phase 10a client hardening: the breaker always resolves, two breaker lanes, short live retries,
the breaker re-checked on the endpoint lock, a stuck probe shown in health, and the
finished-game settle rules (contract C4)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.health import LIVE_FAILURE_NEWS_SECONDS, _upstream_check
from app.cache import FINISHED_GAME_EMPTY_SETTLED_TTL, FINISHED_GAME_EMPTY_TTL, FINISHED_GAME_SETTLING_TTL, DataKind, cache_key, finished_game_ttl, is_empty_payload
from app.cfbd import client as client_module
from app.cfbd.client import (
    BREAKER_OPEN_SECONDS,
    BREAKER_THRESHOLD,
    EMPTY_WARN_AFTER,
    LIVE_MAX_ATTEMPTS,
    MAX_ATTEMPTS,
    Breaker,
    CfbdClient,
    CfbdRequestError,
    CfbdUnavailable,
)
from app.cfbd.quota import QuotaBlocked
from app.config import load_settings
from app.db import Database
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from tests.conftest import TEST_KEY, FakeCfbd, FakeClock, fixture_payload

GAMES = fixture_payload("games_team")
BOX_TEAMS = fixture_payload("games_teams")
LIVE = fixture_payload("live_plays")
GAME_ID = 526001015
BOX_PARAMS = {"year": 2026, "week": 4, "team": "Swampwater Tech"}


class Harness:
    """A client on a fake clock and a scripted upstream. Backoff sleeps advance the clock."""

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


def trip(breaker: Breaker, at: datetime) -> None:
    """Open a breaker the way the client does: BREAKER_THRESHOLD failures in a row at `at`."""
    for _ in range(BREAKER_THRESHOLD):
        breaker.failure(at)


def half_open(breaker: Breaker, now: datetime) -> None:
    trip(breaker, now - timedelta(seconds=BREAKER_OPEN_SECONDS + 1))
    assert breaker.state(now) == "half_open" and breaker.half_open is False


async def wait_until(condition, timeout: float = 5.0) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout)


# --- B1: the breaker always resolves ---------------------------------------------------------------


def test_4xx_half_open_probe_closes_the_breaker(harness):
    breaker = harness.client.breaker
    half_open(breaker, harness.clock())
    harness.upstream.route("/records", status=400, text='{"message":"bad week"}')

    async def scenario():
        with pytest.raises(CfbdRequestError):
            await harness.client.get("/records", {"week": "x"}, kind=DataKind.SCHEDULE)
        assert breaker.state(harness.clock()) == "closed", "CFBD answered, so the upstream is up"
        assert breaker.half_open is False and breaker.failures == 0
        harness.upstream.route("/records", json=[{"team": "Swampwater Tech"}])
        return await harness.client.get("/records", {"year": 2026}, kind=DataKind.SCHEDULE)

    fetched = run(scenario())
    assert fetched.source == "live", "the next call is not refused with 'retrying in 0 s'"
    assert harness.upstream.count("/records") == 2


def test_cancelled_probe_lets_the_next_call_probe(harness):
    breaker = harness.client.breaker
    half_open(breaker, harness.clock())

    async def scenario():
        started = asyncio.Event()
        never = asyncio.Event()

        async def hang(request: httpx.Request) -> httpx.Response:
            started.set()
            await never.wait()
            return httpx.Response(200, json=[])

        harness.upstream.route("/records", handler=hang)
        probe = asyncio.create_task(harness.client.get("/records", kind=DataKind.SCHEDULE))
        await asyncio.wait_for(started.wait(), 5)
        assert breaker.half_open is True, "the probe is out"
        with pytest.raises(CfbdUnavailable, match="test call is under way"):
            await harness.client.get("/records", {"other": 1}, kind=DataKind.SCHEDULE)

        probe.cancel()
        with pytest.raises(asyncio.CancelledError):
            await probe
        assert breaker.half_open is False and breaker.state(harness.clock()) == "half_open"

        harness.upstream.route("/records", json=[{"team": "Swampwater Tech"}])
        return await harness.client.get("/records", kind=DataKind.SCHEDULE)

    fetched = run(scenario())
    assert fetched.source == "live"
    assert breaker.state(harness.clock()) == "closed"


def test_reconcile_timeout_on_a_probe_releases_it(harness, monkeypatch):
    """The startup and hourly /info check cancels a slow call; that probe must not strand the breaker."""
    monkeypatch.setattr(client_module, "RECONCILE_TIMEOUT", 0.05)
    breaker = harness.client.breaker
    half_open(breaker, harness.clock())

    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, json=fixture_payload("info"))

    harness.upstream.route("/info", handler=hang)
    status = run(harness.client.reconcile())
    assert status.reconciled is False
    assert breaker.half_open is False
    assert breaker.allow(harness.clock()), "the next call may probe"


def test_probe_that_breaks_in_our_code_is_released(harness):
    breaker = harness.client.breaker
    half_open(breaker, harness.clock())

    def broken(request: httpx.Request) -> httpx.Response:
        raise ValueError("not an upstream failure")

    harness.upstream.route("/records", handler=broken)
    with pytest.raises(ValueError):
        run(harness.client.get("/records", kind=DataKind.SCHEDULE))
    assert breaker.half_open is False and breaker.failures == BREAKER_THRESHOLD
    assert breaker.allow(harness.clock())


@pytest.mark.parametrize("status", [501, 505, 520, 522, 524, 530, 301])
def test_a_status_that_is_not_4xx_counts_as_a_failure_not_an_answer(harness, status):
    """Only a 4xx means CFBD answered. A proxy's 52x or a redirect is the upstream not answering."""
    breaker = harness.client.breaker
    headers = {"location": "https://example.invalid/v2/records"} if status == 301 else None
    harness.upstream.route("/records", status=status, text="origin unreachable", headers=headers)

    async def scenario():
        with pytest.raises(CfbdUnavailable, match=f"HTTP {status}"):
            await harness.client.get("/records", {"year": 2026}, kind=DataKind.SCHEDULE)
        assert harness.upstream.count("/records") == 1, "not retried"
        assert breaker.failures == 1 and breaker.state(harness.clock()) == "closed"
        check = upstream_check(harness.client)
        assert check["status"] == "degraded" and check["detail"].startswith(f"last CFBD call failed: HTTP {status}")
        for _ in range(BREAKER_THRESHOLD - 1):
            with pytest.raises(CfbdUnavailable):
                await harness.client.get("/records", {"year": 2026}, kind=DataKind.SCHEDULE)

    run(scenario())
    assert breaker.state(harness.clock()) == "open", "they count toward the threshold"
    assert harness.upstream.count("/records") == BREAKER_THRESHOLD
    lane = harness.client.stats["lanes"]["general"]
    assert lane["failures"] == BREAKER_THRESHOLD and lane["last_error"].startswith(f"HTTP {status}")
    if status == 301:
        assert lane["last_error"] == "HTTP 301 to https://example.invalid/v2/records"


def test_half_open_probe_answered_522_keeps_the_lane_open(harness):
    """The live engine's box poll as the probe: a 522 is a failure, and the last box is served stale."""
    breaker = harness.client.live_breaker
    half_open(breaker, harness.clock())
    harness.client.cache.put(
        cache_key("/games/teams", BOX_PARAMS), "/games/teams", BOX_PARAMS, BOX_TEAMS,
        fetched_at=harness.clock() - timedelta(hours=2), ttl=timedelta(hours=1),
    )
    harness.upstream.route("/games/teams", status=522, text="origin unreachable")
    fetched = run(harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME, live=True))
    assert fetched.stale is True and fetched.payload == BOX_TEAMS and "HTTP 522" in (fetched.error or "")
    assert harness.upstream.count("/games/teams") == 1
    assert breaker.state(harness.clock()) == "open" and breaker.half_open is False
    assert breaker.failures == BREAKER_THRESHOLD + 1
    assert harness.client.stats["lanes"]["live"]["last_error"] == "HTTP 522: origin unreachable"
    check = upstream_check(harness.client)
    assert check["status"] == "degraded" and check["detail"].startswith("CFBD live calls paused")
    assert harness.client.breaker.state(harness.clock()) == "closed", "the general lane is untouched"


def test_a_refusal_that_is_not_4xx_never_closes_the_breaker(harness, monkeypatch):
    """get()'s own guard: should any non-4xx refusal ever be raised, it opens the lane, never closes it."""
    breaker = harness.client.breaker
    half_open(breaker, harness.clock())

    async def refuse(endpoint, params, *, live):
        raise CfbdRequestError(522, endpoint, "origin unreachable")

    monkeypatch.setattr(harness.client, "_request_serialised", refuse)
    with pytest.raises(CfbdRequestError):
        run(harness.client.get("/records", kind=DataKind.SCHEDULE))
    assert breaker.state(harness.clock()) == "open" and breaker.half_open is False
    assert breaker.failures == BREAKER_THRESHOLD + 1


def test_breaker_tickets_and_readmission():
    t0 = datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)
    breaker = Breaker("live")
    early = breaker.admit(t0)
    assert early is not None and early.probe is None, "closed: a plain pass, not a probe"

    trip(breaker, t0)
    assert breaker.readmit(early, t0 + timedelta(seconds=10)) is False, "opened while it waited"
    later = t0 + timedelta(seconds=BREAKER_OPEN_SECONDS + 1)
    assert breaker.readmit(early, later) is True, "half-open by its turn: it becomes the probe"
    assert breaker.holds(early) and breaker.admit(later) is None

    breaker.failure(later)  # another call on the lane failed: the probe's ticket is void
    breaker.release(early)
    assert breaker.state(later) == "open" and breaker.half_open is False
    assert breaker.readmit(early, later) is False

    after = later + timedelta(seconds=BREAKER_OPEN_SECONDS + 1)
    probe = breaker.admit(after)
    assert probe is not None and probe.probe is not None
    assert breaker.probe_seconds(after + timedelta(seconds=30)) == 30.0
    assert breaker.as_dict(after + timedelta(seconds=61))["probe_stuck"] is True
    breaker.release(probe)
    assert breaker.probe_seconds(after) is None and breaker.allow(after)


# --- B2: the breaker is asked again on the endpoint lock ---------------------------------------------


def test_breaker_opening_stops_calls_queued_on_the_endpoint(harness):
    breaker = harness.client.breaker
    for _ in range(BREAKER_THRESHOLD - 1):
        breaker.failure(harness.clock())  # one more failed call opens it
    stale_key = cache_key("/records", {"year": 2025})
    harness.client.cache.put(
        stale_key, "/records", {"year": 2025}, [{"old": True}], fetched_at=harness.clock() - timedelta(hours=8), ttl=timedelta(hours=6)
    )
    admitted: list[object] = []
    original_admit = breaker.admit

    def spy(now):
        result = original_admit(now)
        admitted.append(result)
        return result

    breaker.admit = spy  # type: ignore[method-assign]

    async def scenario():
        gate = asyncio.Event()
        first_seen = {"done": False}

        async def failing(request: httpx.Request) -> httpx.Response:
            if not first_seen["done"]:
                first_seen["done"] = True
                await gate.wait()  # hold the endpoint until the other calls are queued behind it
            return httpx.Response(503, text="down")

        harness.upstream.route("/records", handler=failing)
        first = asyncio.create_task(harness.client.get("/records", {"year": 2026}, kind=DataKind.SCHEDULE))
        await wait_until(lambda: first_seen["done"])
        queued = [
            asyncio.create_task(harness.client.get("/records", {"year": year}, kind=DataKind.SCHEDULE))
            for year in (2023, 2024, 2025)
        ]
        await wait_until(lambda: len(admitted) >= 4)  # all four let in while the breaker was closed
        gate.set()
        return await asyncio.gather(first, *queued, return_exceptions=True)

    first, *queued = run(scenario())
    assert isinstance(first, CfbdUnavailable) and "HTTP 503" in str(first)
    assert harness.upstream.count("/records") == MAX_ATTEMPTS, "only the first call reached CFBD"
    assert breaker.state(harness.clock()) == "open"
    refused = [r for r in queued if isinstance(r, CfbdUnavailable)]
    assert len(refused) == 2 and all("paused" in str(r) for r in refused)
    stale = next(r for r in queued if not isinstance(r, BaseException))
    assert stale.stale is True and stale.payload == [{"old": True}] and "paused" in (stale.error or "")


# --- B3: two lanes ------------------------------------------------------------------------------------


def test_general_failures_never_pause_the_live_lane(harness):
    harness.upstream.route("/recruiting/players", status=503, text="down")
    harness.upstream.route("/live/plays", json=LIVE)

    async def scenario():
        for _ in range(BREAKER_THRESHOLD):
            with pytest.raises(CfbdUnavailable):
                await harness.client.get("/recruiting/players", {"year": 2027, "team": "Swampwater Tech"}, kind=DataKind.RECRUITING)
        assert harness.client.breaker.state(harness.clock()) == "open"
        return await harness.client.get("/live/plays", {"gameId": GAME_ID}, kind=DataKind.LIVE, live=True, use_cache=False)

    fetched = run(scenario())
    assert fetched.source == "live" and fetched.stale is False
    assert harness.upstream.count("/live/plays") == 1
    status = harness.client.status()
    assert status["breaker"]["state"] == "open" and status["live_breaker"]["state"] == "closed"
    lanes = status["stats"]["lanes"]
    assert lanes["general"]["failures"] == BREAKER_THRESHOLD * MAX_ATTEMPTS
    assert lanes["live"] == {"calls": 1, "failures": 0, "last_success_at": lanes["live"]["last_success_at"], "last_failure_at": None, "last_error": None}
    assert lanes["live"]["last_success_at"]


def test_live_failures_never_pause_the_general_lane(harness):
    harness.upstream.route("/live/plays", status=502, text="bad gateway")
    harness.upstream.route("/games", json=GAMES)

    async def scenario():
        for _ in range(BREAKER_THRESHOLD):
            with pytest.raises(CfbdUnavailable):
                await harness.client.get("/live/plays", {"gameId": GAME_ID}, kind=DataKind.LIVE, live=True, use_cache=False)
        assert harness.client.live_breaker.state(harness.clock()) == "open"
        with pytest.raises(CfbdUnavailable, match="CFBD live calls paused"):
            await harness.client.get("/live/plays", {"gameId": GAME_ID}, kind=DataKind.LIVE, live=True, use_cache=False)
        return await harness.client.get("/games", {"year": 2026}, kind=DataKind.SCHEDULE)

    fetched = run(scenario())
    assert fetched.source == "live"
    assert harness.client.breaker.state(harness.clock()) == "closed"
    assert harness.upstream.count("/live/plays") == BREAKER_THRESHOLD * LIVE_MAX_ATTEMPTS


# --- B4: short live retries ---------------------------------------------------------------------------


def test_live_call_makes_at_most_two_attempts(harness):
    harness.upstream.route("/live/plays", status=500, text="oops")
    with pytest.raises(CfbdUnavailable, match="HTTP 500"):
        run(harness.client.get("/live/plays", {"gameId": GAME_ID}, kind=DataKind.LIVE, live=True, use_cache=False))
    assert LIVE_MAX_ATTEMPTS == 2
    assert harness.upstream.count("/live/plays") == 2
    assert len(harness.sleeps) == 1
    assert harness.client.live_breaker.failures == 1 and harness.client.breaker.failures == 0


def test_live_box_poll_also_stops_after_two_attempts(harness):
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    harness.upstream.route("/games/teams", handler=boom)
    with pytest.raises(CfbdUnavailable, match="ReadTimeout"):
        run(harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME, live=True, use_cache=False))
    assert harness.upstream.count("/games/teams") == LIVE_MAX_ATTEMPTS
    assert harness.client.quota.status(harness.clock()).ledger_calls_this_month == LIVE_MAX_ATTEMPTS


# --- B6 and C4: finished-game lifetimes ---------------------------------------------------------------


@pytest.mark.parametrize("empty", [[], {}, None], ids=["list", "object", "null"])
def test_empty_finished_game_answer_is_cached_ten_minutes_then_refetched(harness, empty):
    first = httpx.Response(200, content=b"null", headers={"content-type": "application/json"}) if empty is None else httpx.Response(200, json=empty)
    harness.upstream.route("/games/teams", sequence=[first, httpx.Response(200, json=BOX_TEAMS)])
    key = cache_key("/games/teams", BOX_PARAMS)
    harness.client.settle_until = harness.clock() + timedelta(minutes=10, seconds=30)  # the game settles until just after the refetch

    async def scenario():
        await harness.client.reconcile()  # the fake /info is the Free tier: other lifetimes x4, these never
        answers = [await harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME)]
        entry = harness.client.cache.get(key)
        assert entry is not None and entry.expires_at == entry.fetched_at + timedelta(minutes=10)
        harness.clock.advance(minutes=9)
        answers.append(await harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME))
        harness.clock.advance(minutes=2)
        answers.append(await harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME))
        return answers

    fresh, cached, refetched = run(scenario())
    assert fresh.source == "live" and fresh.payload == empty
    assert cached.source == "cache" and cached.payload == empty
    assert refetched.source == "live" and refetched.payload == BOX_TEAMS
    assert harness.upstream.count("/games/teams") == 2
    entry = harness.client.cache.get(key)
    assert entry is not None and entry.expires_at is None, "a real answer outside the settle window is permanent"


def test_finished_game_answer_that_stays_empty_is_logged(harness, caplog):
    """An answer that never fills costs a call every ten minutes while the game settles: the log says so once it has for an hour."""
    params = {"gameId": GAME_ID}
    harness.upstream.route("/metrics/wp", json=[])
    harness.client.settle_until = harness.clock() + timedelta(hours=24)

    async def ask_every_eleven_minutes(times: int) -> None:
        for _ in range(times):
            await harness.client.get("/metrics/wp", params, kind=DataKind.FINISHED_GAME)
            harness.clock.advance(minutes=11)

    def warnings() -> list[str]:
        return [r.getMessage() for r in caplog.records if "answered empty" in r.getMessage()]

    with caplog.at_level(logging.WARNING, logger="kickoff.cfbd"):
        run(ask_every_eleven_minutes(EMPTY_WARN_AFTER - 1))
        assert warnings() == []
        run(ask_every_eleven_minutes(1))
        assert len(warnings()) == 1 and f"answered empty {EMPTY_WARN_AFTER} times in a row" in warnings()[0]
        run(ask_every_eleven_minutes(1))
        assert len(warnings()) == 1, "one warning, not one per refetch"
    assert harness.upstream.count("/metrics/wp") == EMPTY_WARN_AFTER + 1

    harness.upstream.route("/metrics/wp", json=[{"playId": "1", "homeWinProbability": 0.6}])
    run(harness.client.get("/metrics/wp", params, kind=DataKind.FINISHED_GAME))
    assert harness.client._empty_answers == {}, "a real answer resets the count"


def test_empty_finished_game_answer_outside_the_settle_window_is_kept_six_hours(harness):
    """An older game CFBD never filled is asked about a few times a day, not every ten minutes."""
    harness.upstream.route("/games/teams", json=[])
    key = cache_key("/games/teams", BOX_PARAMS)

    async def scenario():
        await harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME)
        entry = harness.client.cache.get(key)
        assert entry is not None and entry.expires_at == entry.fetched_at + timedelta(hours=6)
        harness.clock.advance(minutes=11)
        cached = await harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME)
        harness.clock.advance(hours=6)
        refetched = await harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME)
        return cached, refetched

    cached, refetched = run(scenario())
    assert cached.source == "cache" and refetched.source == "live"
    assert harness.upstream.count("/games/teams") == 2


def test_settle_until_gives_one_hour_then_permanent(harness):
    harness.client.settle_until = harness.clock() + timedelta(hours=24)
    versions = [[{"id": GAME_ID, "teams": [{"team": "Swampwater Tech", "points": n}]}] for n in (24, 27, 27)]
    harness.upstream.route("/games/players", sequence=[httpx.Response(200, json=v) for v in versions])
    key = cache_key("/games/players", BOX_PARAMS)

    async def get():
        return await harness.client.get("/games/players", BOX_PARAMS, kind=DataKind.FINISHED_GAME)

    async def scenario():
        first = await get()
        entry = harness.client.cache.get(key)
        assert entry is not None and entry.expires_at == entry.fetched_at + timedelta(hours=1)
        harness.clock.advance(minutes=30)
        assert (await get()).source == "cache"
        harness.clock.advance(minutes=31)
        corrected = await get()
        entry = harness.client.cache.get(key)
        assert entry is not None and entry.expires_at == entry.fetched_at + timedelta(hours=1), "still settling"
        assert harness.client.status()["settling"] is True
        harness.clock.advance(hours=24)
        settled = await get()
        entry = harness.client.cache.get(key)
        assert entry is not None and entry.expires_at is None
        harness.clock.advance(days=30)
        kept = await get()
        return first, corrected, settled, kept

    first, corrected, settled, kept = run(scenario())
    assert [first.source, corrected.source, settled.source, kept.source] == ["live", "live", "live", "cache"]
    assert corrected.payload == versions[1]
    assert harness.upstream.count("/games/players") == 3
    assert harness.client.status()["settling"] is False


def test_legacy_permanent_empty_entry_is_refetched(harness):
    """Rows cached forever before the empty rule existed heal themselves; real permanent rows stay."""
    empty_key = cache_key("/games/teams", BOX_PARAMS)
    full_params = {**BOX_PARAMS, "week": 3}
    full_key = cache_key("/games/teams", full_params)
    old = harness.clock() - timedelta(days=2)
    harness.client.cache.put(empty_key, "/games/teams", BOX_PARAMS, [], fetched_at=old, ttl=None)
    harness.client.cache.put(full_key, "/games/teams", full_params, BOX_TEAMS, fetched_at=old, ttl=None)
    harness.upstream.route("/games/teams", json=BOX_TEAMS)

    async def scenario():
        healed = await harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME)
        kept = await harness.client.get("/games/teams", full_params, kind=DataKind.FINISHED_GAME)
        return healed, kept

    healed, kept = run(scenario())
    assert healed.source == "live" and healed.payload == BOX_TEAMS
    assert kept.source == "cache"
    assert harness.upstream.count("/games/teams") == 1


def test_uncached_finished_game_calls_store_nothing(harness):
    harness.client.settle_until = harness.clock() + timedelta(hours=24)
    harness.upstream.route("/metrics/wp", json=[])
    run(harness.client.get("/metrics/wp", {"gameId": GAME_ID}, kind=DataKind.FINISHED_GAME, live=True, use_cache=False))
    assert harness.client.cache.get(cache_key("/metrics/wp", {"gameId": GAME_ID})) is None


def test_settle_until_is_read_defensively(harness):
    now = harness.clock()
    harness.client.settle_until = (now + timedelta(hours=2)).replace(tzinfo=None)  # naive: read as UTC
    assert harness.client.status()["settling"] is True
    assert harness.client.status()["settle_until"].endswith("Z")
    harness.client.settle_until = "tomorrow"  # type: ignore[assignment]
    assert harness.client.status()["settle_until"] is None and harness.client.status()["settling"] is False
    harness.upstream.route("/games/teams", json=BOX_TEAMS)
    run(harness.client.get("/games/teams", BOX_PARAMS, kind=DataKind.FINISHED_GAME))
    entry = harness.client.cache.get(cache_key("/games/teams", BOX_PARAMS))
    assert entry is not None and entry.expires_at is None


def test_finished_game_ttl_policy():
    now = datetime(2026, 9, 26, 23, 30, tzinfo=timezone.utc)
    settle = now + timedelta(hours=20)
    assert finished_game_ttl([], now, None) == FINISHED_GAME_EMPTY_SETTLED_TTL == timedelta(hours=6)
    assert finished_game_ttl([], settle, settle) == FINISHED_GAME_EMPTY_SETTLED_TTL
    assert finished_game_ttl([], now, settle) == FINISHED_GAME_EMPTY_TTL == timedelta(minutes=10)
    assert finished_game_ttl({}, now, settle) == FINISHED_GAME_EMPTY_TTL
    assert finished_game_ttl(None, now, settle) == FINISHED_GAME_EMPTY_TTL
    assert finished_game_ttl([1], now, settle) == FINISHED_GAME_SETTLING_TTL == timedelta(hours=1)
    assert finished_game_ttl([1], settle, settle) is None
    assert finished_game_ttl({"a": 1}, now, None) is None
    assert is_empty_payload("") and not is_empty_payload(0) and not is_empty_payload(False)


# --- CLAUDE.md rule 7: the quota guard before the breaker ------------------------------------------


def test_quota_blocked_call_never_touches_the_breaker(tmp_path):
    h = Harness(tmp_path, monthly_call_budget=10, quota_hard_stop_pct=90)
    try:
        for _ in range(10):
            h.client.quota.record("/x", 200, True, live=False, now=h.clock())
        assert h.client.quota.status(h.clock()).mode.value == "exhausted", "live calls are stopped too"
        for breaker in (h.client.breaker, h.client.live_breaker):
            half_open(breaker, h.clock())
        before = [(b.failures, b.opened_at, b.half_open) for b in (h.client.breaker, h.client.live_breaker)]

        async def scenario():
            with pytest.raises(QuotaBlocked):
                await h.client.get("/records", kind=DataKind.SCHEDULE)
            with pytest.raises(QuotaBlocked):
                await h.client.get("/live/plays", {"gameId": GAME_ID}, kind=DataKind.LIVE, live=True, use_cache=False)

        run(scenario())
        after = [(b.failures, b.opened_at, b.half_open) for b in (h.client.breaker, h.client.live_breaker)]
        assert after == before, "no probe taken, no failure counted"
        assert h.upstream.count() == 0
        assert h.client.stats["blocked_by_quota"] == 2
    finally:
        run(h.close())


# --- B5: health ------------------------------------------------------------------------------------


def upstream_check(client: CfbdClient) -> dict[str, str]:
    return _upstream_check(client.status())


def test_health_is_degraded_with_a_stuck_half_open_probe(harness):
    now = harness.clock()
    breaker = harness.client.breaker
    trip(breaker, now - timedelta(seconds=200))
    assert breaker.admit(now - timedelta(seconds=90)) is not None  # the probe went out 90 s ago
    check = upstream_check(harness.client)
    assert check["status"] == "degraded"
    assert "stuck" in check["detail"] and "1 min 30 s" in check["detail"]
    assert harness.client.status()["breaker"]["probe_stuck"] is True


def test_health_is_ok_with_a_young_probe(harness):
    now = harness.clock()
    trip(harness.client.live_breaker, now - timedelta(seconds=100))
    assert harness.client.live_breaker.admit(now - timedelta(seconds=30)) is not None
    check = upstream_check(harness.client)
    assert check["status"] == "ok", check


def test_health_names_the_live_lane(harness):
    harness.upstream.route("/live/plays", status=503, text="down")

    async def scenario():
        with pytest.raises(CfbdUnavailable):
            await harness.client.get("/live/plays", {"gameId": GAME_ID}, kind=DataKind.LIVE, live=True, use_cache=False)

    run(scenario())
    check = upstream_check(harness.client)
    assert check["status"] == "degraded" and check["detail"].startswith("last live CFBD call failed: HTTP 503")

    for _ in range(BREAKER_THRESHOLD - 1):
        run(scenario())
    check = upstream_check(harness.client)
    assert check["status"] == "degraded"
    assert check["detail"].startswith(f"CFBD live calls paused after {BREAKER_THRESHOLD} failures in a row")


def test_old_live_failure_outside_a_window_is_not_a_standing_alarm(harness):
    """The live lane is idle between games: its failed last call must not keep /status degraded for a week."""
    harness.upstream.route("/live/plays", status=503, text="down")
    with pytest.raises(CfbdUnavailable):
        run(harness.client.get("/live/plays", {"gameId": GAME_ID}, kind=DataKind.LIVE, live=True, use_cache=False))
    assert harness.client.live_window is False
    assert upstream_check(harness.client)["status"] == "degraded"

    harness.clock.advance(seconds=LIVE_FAILURE_NEWS_SECONDS - 60)
    assert upstream_check(harness.client)["status"] == "degraded", "still recent"
    harness.clock.advance(minutes=6)
    assert upstream_check(harness.client) == {"name": "upstream", "status": "ok", "detail": "no CFBD calls yet this session"}

    harness.client.live_window = True
    check = upstream_check(harness.client)
    assert check["status"] == "degraded" and check["detail"] == "last live CFBD call failed: HTTP 503: down."
    harness.client.live_window = False

    harness.upstream.route("/records", status=503, text="down")
    with pytest.raises(CfbdUnavailable):
        run(harness.client.get("/records", kind=DataKind.SCHEDULE))
    harness.clock.advance(hours=2)
    check = upstream_check(harness.client)
    assert check["status"] == "degraded" and check["detail"].startswith("last CFBD call failed"), "the general lane has no age limit"


def test_live_failure_with_an_unreadable_time_is_reported():
    status = {
        "checked_at": "2026-09-26T21:00:00Z",
        "live_window": False,
        "stats": {"lanes": {"general": {}, "live": {"last_failure_at": "not a time", "last_error": "HTTP 503"}}},
    }
    check = _upstream_check(status)
    assert check["status"] == "degraded" and check["detail"] == "last live CFBD call failed: HTTP 503."


def test_health_check_survives_an_old_status_shape():
    old = {"breaker": {"state": "closed"}, "stats": {"last_success_at": "2026-09-21T12:00:00+00:00", "session_calls": 3}}
    assert _upstream_check(old) == {"name": "upstream", "status": "ok", "detail": "CFBD answering, 3 calls this session"}
    assert _upstream_check({})["status"] == "ok"


def test_health_endpoint_shows_the_live_lane_and_a_stuck_probe(settings, fake_cfbd):
    configure_logging(settings)
    try:
        with TestClient(create_app(settings, cfbd_transport=fake_cfbd.transport), base_url="https://testserver") as client:
            cfbd: CfbdClient = client.app.state.cfbd
            now = datetime.now(timezone.utc)
            trip(cfbd.live_breaker, now - timedelta(seconds=300))
            assert cfbd.live_breaker.admit(now - timedelta(seconds=120)) is not None
            data = client.get("/api/health").json()["data"]
            assert data["status"] == "degraded"
            upstream = next(check for check in data["checks"] if check["name"] == "upstream")
            assert upstream["status"] == "degraded"
            assert upstream["detail"].startswith("CFBD live calls: the test call after a pause has been out 2 min")
            assert data["upstream"]["live_breaker"]["state"] == "half_open"
            assert data["upstream"]["live_breaker"]["probe_stuck"] is True
            assert data["upstream"]["breaker"]["probe_stuck"] is False
            assert data["upstream"]["settle_until"] is None and data["upstream"]["settling"] is False
            assert set(data["upstream"]["stats"]["lanes"]) == {"general", "live"}
    finally:
        shutdown_logging()
