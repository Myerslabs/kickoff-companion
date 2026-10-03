"""The only module allowed to call the CFBD API.

Every request goes through, in order: the quota guard, the cache, the circuit breaker,
HTTP with a timeout and bounded retries, then the cache write. When the upstream fails and
an old payload exists, the old payload is served and labelled stale with its age.

There are two breaker lanes: live=True calls (the game-day poller) have their own, so a dead
season endpoint never pauses the live poll, and a failing live feed never pauses the rest.

Rules from docs/02-ARCHITECTURE.md, "CFBD client rules".
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Literal

import httpx

from app import APP_NAME, __version__
from app.cache import (
    NO_CACHE,
    Cache,
    CacheEntry,
    DataKind,
    cache_key,
    canonical_params,
    finished_game_empty_ttl,
    finished_game_ttl,
    is_empty_payload,
    ttl_for,
)
from app.cfbd.capabilities import Capabilities
from app.cfbd.publish import PublicationLog, learn_game_days, schedule_for
from app.cfbd.quota import QuotaBlocked, QuotaGuard, QuotaStatus
from app.config import Settings
from app.db import Database

log = logging.getLogger("kickoff.cfbd")

TIMEOUT = httpx.Timeout(10.0, connect=10.0)
# Phase 13: the big season-wide answers (all-FBS advanced stats, 430 KB) outlast 10 s when CFBD is
# busy on a game night, and CFBD keeps working on a request we gave up on, so a quick retry meets
# "Too many concurrent requests for this endpoint" (game night 2026-09-26, 18:29). Non-live calls wait
# longer, a retry after a timeout or that 429 waits BUSY_WAIT_SECONDS, and an endpoint that ends
# its retries busy rests ENDPOINT_COOLDOWN while its cached copy is served.
BULK_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
BUSY_WAIT_SECONDS = 15.0
ENDPOINT_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 4  # one try plus three retries
LIVE_MAX_ATTEMPTS = 2  # a live poll comes round again in seconds; a long retry chain only delays the next one
BACKOFF_BASE = 0.5
BACKOFF_MAX = 8.0
BACKOFF_JITTER = 0.25
RETRY_AFTER_MAX = 10.0
RETRY_STATUSES = {429, 500, 502, 503, 504}
BREAKER_THRESHOLD = 5
BREAKER_OPEN_SECONDS = 60.0
PROBE_STUCK_SECONDS = 60.0  # a half-open probe out longer than this is reported as stuck
RECONCILE_TIMEOUT = 45.0
EMPTY_WARN_AFTER = 6  # an hour of ten-minute refetches of one finished-game answer that stays empty
EMPTY_WARN_EVERY = 36  # then a reminder every six hours while it still costs a call each time

Source = Literal["live", "cache"]
Lane = Literal["general", "live"]
Clock = Callable[[], datetime]


class CfbdError(Exception):
    """Base for everything the client raises on purpose."""


class CfbdUnavailable(CfbdError):
    """The upstream could not be reached or answered badly, and nothing is cached."""


class CfbdRequestError(CfbdError):
    """A 4xx that a retry will not fix: bad parameters, a rejected key, a tier limit."""

    def __init__(self, status: int, endpoint: str, body: str) -> None:
        self.status = status
        self.endpoint = endpoint
        self.body = body
        self.tier_gate = status in (401, 403) and is_tier_gate(body)
        super().__init__(f"CFBD refused {endpoint} with HTTP {status}: {body[:200] or 'no detail'}")


def is_tier_gate(body: str) -> bool:
    """CFBD answers 401 with 'requires a Patreon subscription at Tier N' for gated endpoints."""
    lowered = body.lower()
    return any(word in lowered for word in ("patreon", "tier", "subscription"))


@dataclass(frozen=True)
class Fetched:
    """What a call returns: the payload plus where it came from and how old it is."""

    endpoint: str
    params: dict[str, str]
    payload: Any
    fetched_at: datetime
    source: Source
    stale: bool
    age_seconds: float
    error: str | None = None  # why it is stale, when it is

    @property
    def meta(self) -> dict[str, Any]:
        return {
            "fetched_at": self.fetched_at.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "stale": self.stale,
            "source": self.source,
        }


@dataclass
class Admission:
    """One call's permission from a breaker. `probe` is the half-open ticket when the call is the probe."""

    probe: int | None = None


class Breaker:
    """After BREAKER_THRESHOLD straight failures, stop calling for BREAKER_OPEN_SECONDS.

    Then exactly one call goes through as a probe. An answer closes the breaker, a failure opens
    it again, and a probe that ends without either (cancelled, or broken in our own code) is
    released so the next call can probe. The client keeps one breaker per lane.
    """

    def __init__(self, lane: Lane = "general") -> None:
        self.lane = lane
        self.failures = 0
        self.opened_at: datetime | None = None
        self.half_open = False  # a probe is out
        self.probe_started_at: datetime | None = None
        self._ticket = 0

    @property
    def _label(self) -> str:
        return "CFBD live calls" if self.lane == "live" else "CFBD"

    def state(self, now: datetime) -> str:
        if self.opened_at is None:
            return "closed"
        if (now - self.opened_at).total_seconds() >= BREAKER_OPEN_SECONDS:
            return "half_open"
        return "open"

    def retry_in(self, now: datetime) -> float:
        if self.opened_at is None:
            return 0.0
        return max(BREAKER_OPEN_SECONDS - (now - self.opened_at).total_seconds(), 0.0)

    def admit(self, now: datetime) -> Admission | None:
        """Let a call through, or None while the breaker is open or another call is probing."""
        state = self.state(now)
        if state == "closed":
            return Admission()
        if state == "half_open" and not self.half_open:
            self.half_open = True  # let exactly one probe through
            self.probe_started_at = now
            self._ticket += 1
            return Admission(probe=self._ticket)
        return None

    def allow(self, now: datetime) -> bool:
        return self.admit(now) is not None

    def holds(self, admission: Admission) -> bool:
        """True while this admission is the probe that is still out."""
        return admission.probe is not None and self.half_open and admission.probe == self._ticket

    def readmit(self, admission: Admission, now: datetime) -> bool:
        """Check again once the call has its turn on the endpoint; the breaker may have opened while it
        waited. A call let in while closed may become the probe if the breaker is half-open by now.
        False means the call must not reach the upstream."""
        if self.holds(admission):
            return True  # still the probe: nothing has resolved the breaker since
        admission.probe = None
        again = self.admit(now)
        if again is None:
            return False
        admission.probe = again.probe
        return True

    def release(self, admission: Admission) -> None:
        """The call ended without an answer or a failure. If it was the probe, the next call may probe."""
        if self.holds(admission):
            self.half_open = False
            self.probe_started_at = None
            log.warning("%s: the test call after a pause ended without an answer; the next call tests again", self._label)
        admission.probe = None

    def probe_seconds(self, now: datetime) -> float | None:
        """How long the outstanding probe has been out, or None when no probe is out."""
        if not self.half_open or self.probe_started_at is None:
            return None
        return max((now - self.probe_started_at).total_seconds(), 0.0)

    def success(self) -> None:
        if self.opened_at is not None:
            log.info("%s answering again; circuit breaker closed", self._label)
        self.failures = 0
        self.opened_at = None
        self.half_open = False
        self.probe_started_at = None

    def failure(self, now: datetime) -> None:
        self.failures += 1
        self.half_open = False
        self.probe_started_at = None
        if self.failures >= BREAKER_THRESHOLD and self.opened_at is None:
            log.warning("%s failed %d times in a row; pausing calls for %.0f s", self._label, self.failures, BREAKER_OPEN_SECONDS)
        if self.failures >= BREAKER_THRESHOLD:
            self.opened_at = now

    def paused_reason(self, now: datetime) -> str:
        if self.state(now) == "half_open":
            return f"{self._label} paused after repeated failures; a test call is under way"
        return f"{self._label} paused after repeated failures; retrying in {self.retry_in(now):.0f} s"

    def as_dict(self, now: datetime) -> dict[str, Any]:
        probe = self.probe_seconds(now)
        return {
            "state": self.state(now),
            "consecutive_failures": self.failures,
            "retry_in_seconds": round(self.retry_in(now), 1),
            "probe_seconds": round(probe, 1) if probe is not None else None,
            "probe_stuck": probe is not None and probe > PROBE_STUCK_SECONDS,
        }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def backoff_seconds(attempt: int, retry_after: float | None = None) -> float:
    if retry_after is not None:
        return min(max(retry_after, 0.0), RETRY_AFTER_MAX)
    base = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_MAX)
    return base + random.uniform(0, BACKOFF_JITTER)


class CfbdClient:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock = _utc_now,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self.cache = Cache(db)
        self.publications = PublicationLog(db)  # Phase 14: when scheduled sources last changed
        self.quota = QuotaGuard(db, settings)
        self.breaker = Breaker("general")  # every call that is not live=True
        self.live_breaker = Breaker("live")  # the game-day poller's own lane
        self.capabilities = Capabilities()
        self.live_window = False  # Phase 6's poller sets this inside a game window
        self.game_day = False  # Phase 3 sets this from the schedule
        # The live engine sets this to kickoff + 24 h after our game: until then CFBD may still
        # correct a finished game, so its answers are kept an hour instead of forever. UTC-aware.
        self.settle_until: datetime | None = None
        self._clock = clock
        self._sleep = sleep
        self._locks: dict[str, asyncio.Lock] = {}
        self._endpoint_locks: dict[str, asyncio.Lock] = {}  # CFBD answers 429 to concurrent calls on one endpoint (seen 2026-09-23)
        self._busy_until: dict[str, datetime] = {}  # endpoints resting after CFBD said busy (Phase 13)
        self._empty_answers: dict[str, int] = {}  # cached finished-game keys that answered empty, and how many times in a row
        self._reconcile_lock = asyncio.Lock()
        self._reconcile_task: asyncio.Task[Any] | None = None
        self._closed = False
        self._http = httpx.AsyncClient(
            base_url=settings.cfbd_base_url,
            headers={
                "Authorization": f"Bearer {settings.cfbd_api_key.get_secret_value()}",
                "Accept": "application/json",
                "User-Agent": f"{APP_NAME.replace(' ', '')}/{__version__} (personal second screen, single user)",
            },
            timeout=TIMEOUT,
            transport=transport,
        )
        self.stats: dict[str, Any] = {
            "session_calls": 0,
            "session_failures": 0,
            "cache_hits": 0,
            "stale_serves": 0,
            "blocked_by_quota": 0,
            "last_success_at": None,
            "last_failure_at": None,
            "last_error": None,
            "lanes": {lane: _lane_stats() for lane in ("general", "live")},
        }
        self._restore_capabilities()
        self._restore_game_days()

    def _restore_game_days(self) -> None:
        """Phase 14: the stats-from-games schedule needs the days games are played; read them from
        the season's cached schedule so a restart does not fall back to a refresh every morning."""
        for params in ({"year": self.settings.season}, {"year": self.settings.season, "team": self.settings.team}):
            try:
                entry = self.cache.get(cache_key("/games", params))
            except Exception:  # noqa: BLE001 - a broken row must not stop the app
                log.exception("Could not read the cached schedule for the game days")
                continue
            if entry is not None:
                learn_game_days(entry.payload)

    def _restore_capabilities(self) -> None:
        """After a restart, start from what /info said last time this month until the next check."""
        try:
            stored = self.quota.last_reconcile_raw(self._clock())
        except Exception:  # noqa: BLE001 - a broken row must not stop the app
            log.exception("Could not read the last quota check from the database")
            return
        if stored is not None:
            payload, at = stored
            self.capabilities.update_from_info(payload, at)
            self.capabilities.source = "stored"

    # --- public API -------------------------------------------------------------------

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        kind: DataKind,
        live: bool = False,
        use_cache: bool = True,
        max_age: timedelta | None = None,
        prewarm: bool = False,
    ) -> Fetched:
        """Fetch one endpoint. Returns fresh data, cached data, or stale data with a reason.

        `max_age` is a ceiling on top of the kind's lifetime: an entry older than it is refetched
        even while fresh (the ticker uses it to refresh the week's games every five minutes).

        An endpoint with a publication schedule (app/cfbd/publish.py) is kept until its next slot
        instead of the kind's lifetime. `prewarm` marks the server's own refresh of such a key, which
        does not count as a page asking for it.

        Raises QuotaBlocked, CfbdUnavailable, or CfbdRequestError when there is nothing to return.
        """
        canonical = canonical_params(params)
        key = cache_key(endpoint, canonical)
        now = self._clock()
        schedule = schedule_for(endpoint, kind) if use_cache else None
        entry = await asyncio.to_thread(self.cache.get, key) if use_cache else None
        if entry is not None and self._usable(entry, now, max_age, kind):
            self.stats["cache_hits"] += 1
            if schedule is not None and schedule.prewarm and not prewarm:
                await self._note_asked(key, now)
            return self._from_entry(entry, now, stale=False)

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if use_cache:
                entry = await asyncio.to_thread(self.cache.get, key)
                now = self._clock()
                if entry is not None and self._usable(entry, now, max_age, kind):
                    self.stats["cache_hits"] += 1
                    return self._from_entry(entry, now, stale=False)

            try:
                quota_status = self.quota.check(live=live, now=now, reconciling=endpoint == "/info")
            except QuotaBlocked as exc:
                self.stats["blocked_by_quota"] += 1
                if entry is not None:
                    log.warning("Serving stale %s (%s)", key, exc)
                    self.stats["stale_serves"] += 1
                    return self._from_entry(entry, now, stale=True, error=str(exc))
                raise

            busy = self._busy_until.get(endpoint)
            if not live and busy is not None and now < busy and entry is not None:
                self.stats["stale_serves"] += 1
                log.info("Serving cached %s: CFBD said the endpoint was busy; asking again after %s", key, busy.isoformat(timespec="seconds"))
                return self._from_entry(entry, now, stale=True, error="CFBD was busy with this endpoint; the app asks again in a minute")

            breaker = self.lane(live)
            admission = breaker.admit(now)
            if admission is None:
                return self._paused(entry, now, breaker)

            # Whatever happens to the call, the breaker must resolve: a probe left out would refuse
            # every later call on the lane for good.
            try:
                result = await self._request(endpoint, canonical, live=live, breaker=breaker, admission=admission)
            except CfbdRequestError as exc:
                # CFBD answered: a 4xx is about this request, not about the upstream being down. Only a 4xx
                # is raised as a refusal; any other status is a failure, should one ever arrive this way.
                if 400 <= exc.status < 500:
                    breaker.success()
                else:
                    breaker.failure(self._clock())
                raise
            except BaseException:
                breaker.release(admission)  # cancelled, or broken in our own code
                raise
            now = self._clock()
            if result is None:  # the lane opened while this call waited its turn; nothing was sent
                return self._paused(entry, now, breaker)
            payload, error = result
            if error is None:
                breaker.success()
                if endpoint == "/games":
                    learn_game_days(payload)
                if schedule is not None:
                    ttl = await self._scheduled_ttl(schedule, key, endpoint, canonical, payload, now, asked=not prewarm)
                else:
                    ttl = self._ttl(kind, payload, now, quota_status)
                fetched_at = now
                if use_cache and kind is DataKind.FINISHED_GAME:
                    self._count_empty_answer(key, payload)
                if use_cache and ttl != NO_CACHE:
                    if kind is DataKind.FINISHED_GAME and ttl is not None:
                        log.info(
                            "Keeping %s %.0f min, not permanently (%s)",
                            key,
                            ttl.total_seconds() / 60,
                            "empty answer" if is_empty_payload(payload) else "game still settling",
                        )
                    await asyncio.to_thread(
                        self.cache.put, key, endpoint, canonical, payload, fetched_at=fetched_at, ttl=ttl
                    )
                if endpoint == "/info":
                    self._apply_info(payload, now)  # every /info answer is a reconciliation
                else:
                    self._maybe_schedule_reconcile(now)
                return Fetched(endpoint, canonical, payload, fetched_at, "live", False, 0.0)

            breaker.failure(now)
            if entry is not None:
                log.warning("Serving stale %s, %.0f s old: %s", key, entry.age_seconds(now), error)
                self.stats["stale_serves"] += 1
                return self._from_entry(entry, now, stale=True, error=error)
            raise CfbdUnavailable(f"{endpoint}: {error}")

    def lane(self, live: bool) -> Breaker:
        """The breaker a call answers to: live=True calls have their own."""
        return self.live_breaker if live else self.breaker

    def _paused(self, entry: CacheEntry | None, now: datetime, breaker: Breaker) -> Fetched:
        """The lane refuses the call: serve the old payload labelled stale, or raise."""
        reason = breaker.paused_reason(now)
        if entry is not None:
            self.stats["stale_serves"] += 1
            return self._from_entry(entry, now, stale=True, error=reason)
        raise CfbdUnavailable(reason)

    def _ttl(self, kind: DataKind, payload: Any, now: datetime, quota_status: QuotaStatus) -> timedelta | None:
        """The lifetime of a fresh answer. Finished-game answers follow the settle rule and are never
        budget-scaled: ten minutes when empty, an hour while the game settles, then permanent."""
        if kind is DataKind.FINISHED_GAME:
            return finished_game_ttl(payload, now, self._settle_until())
        ttl = ttl_for(kind, now.astimezone(self.settings.tzinfo), game_day=self.game_day)
        if ttl is not None and ttl != NO_CACHE and kind is not DataKind.TICKER:  # the ticker cadence is the owner's approved figure on every tier
            ttl = ttl * self.ttl_scale(quota_status)
        return ttl

    async def _scheduled_ttl(self, schedule: Any, key: str, endpoint: str, params: dict[str, str], payload: Any, now: datetime, *, asked: bool) -> timedelta:
        """The lifetime of a scheduled answer: until the next slot, or the recheck while CFBD still
        serves what it had before the slot. Never scaled by the quota: it is already the minimum."""
        try:
            unchanged, before = await asyncio.to_thread(self.publications.record, key, endpoint, params, schedule, payload, now, asked=asked)
        except Exception:  # noqa: BLE001 - the log is a helper; a broken row must not cost the answer
            log.exception("Could not note the publication state of %s", key)
            unchanged, before = False, None
        return schedule.lifetime(now, changed_at=before.changed_at if before else None, unchanged=unchanged)

    async def _note_asked(self, key: str, now: datetime) -> None:
        try:
            await asyncio.to_thread(self.publications.asked, key, now)
        except Exception:  # noqa: BLE001
            log.exception("Could not note that %s was asked for", key)

    def _count_empty_answer(self, key: str, payload: Any) -> None:
        """Count straight empty answers per cached finished-game key. An empty answer is kept only ten
        minutes while a game settles (six hours after), so one that never fills costs a call every time
        it is asked for again: say so in the log."""
        if not is_empty_payload(payload):
            self._empty_answers.pop(key, None)
            return
        count = self._empty_answers.get(key, 0) + 1
        self._empty_answers[key] = count
        if count == EMPTY_WARN_AFTER or count % EMPTY_WARN_EVERY == 0:
            log.warning(
                "%s has answered empty %d times in a row; each refetch costs a CFBD call",
                key,
                count,
            )

    def _settle_until(self) -> datetime | None:
        """settle_until as a UTC-aware datetime; a naive one is read as UTC, anything else is ignored."""
        value = self.settle_until
        if value is None:
            return None
        if not isinstance(value, datetime):
            log.warning("Ignoring settle_until of type %s; finished-game answers are kept permanently", type(value).__name__)
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    def _usable(self, entry: Any, now: datetime, max_age: timedelta | None, kind: DataKind) -> bool:
        """Fresh by its own lifetime, and no older than the caller's ceiling when one is given.

        An empty finished-game answer is never good for longer than the empty rule allows (ten minutes
        while a game settles, six hours otherwise), whatever lifetime it was stored with: rows written
        permanently before that rule existed heal themselves."""
        if not entry.is_fresh(now):
            return False
        age = entry.age_seconds(now)
        if kind is DataKind.FINISHED_GAME and is_empty_payload(entry.payload) and age >= finished_game_empty_ttl(now, self._settle_until()).total_seconds():
            return False
        return max_age is None or age <= max_age.total_seconds()

    async def info(self) -> Fetched:
        return await self.get("/info", kind=DataKind.INFO, use_cache=False)

    async def try_key(self, key: str) -> tuple[int | None, Any, str | None]:
        """Ask /info with a key the /welcome page was given (public release Phase 5a), before it is
        saved: one attempt, recorded in the quota ledger like any call, never cached, the key never
        logged. Returns (HTTP status or None, payload or None, error or None)."""
        now = self._clock()
        if self._closed:
            return None, None, "the CFBD client is closed"
        self.stats["session_calls"] += 1
        try:
            response = await self._http.get("/info", headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            await asyncio.to_thread(self.quota.record, "/info", None, False, live=False, now=now)
            error = f"{type(exc).__name__}: {exc}".strip(": ")
            log.warning("Checking a new CFBD key failed: %s", error)
            return None, None, error
        status = response.status_code
        ok = 200 <= status < 300
        await asyncio.to_thread(self.quota.record, "/info", status, ok, live=False, now=now)
        if not ok:
            log.warning("CFBD refused a new key with HTTP %d", status)
            return status, None, _body_excerpt(response) or f"HTTP {status}"
        try:
            payload = response.json()
        except ValueError:
            return status, None, f"HTTP {status} with a body that is not JSON"
        log.info("A new CFBD key answered /info")
        return status, payload, None

    def use_key(self, key: str) -> None:
        """Setup mode (Phase 5a): call CFBD with the key the /welcome page just checked, until the
        restart reads it from .env. Only used while no key is configured, so nothing else is calling."""
        self._http.headers["Authorization"] = f"Bearer {key}"

    async def prewarm(self) -> int:
        """Refresh scheduled keys a page asked for lately whose slot has passed (Phase 14), one at a
        time, so the page finds them fresh. Skipped inside a live game window: the live lane has the
        stage and these can wait until the game ends. Returns how many calls it made."""
        if self.live_window or self._closed:
            return 0
        from app.services import plan  # the Free profile (Phase 5a): no refresh nobody asked for

        if plan.lean(self):
            return 0
        now = self._clock()
        try:
            keys = await asyncio.to_thread(self.publications.prewarm_keys, now)
        except Exception:  # noqa: BLE001
            log.exception("Could not read the prewarm list")
            return 0
        made = 0
        for key, endpoint, params, schedule in keys:
            entry = await asyncio.to_thread(self.cache.get, key)
            if entry is not None and entry.is_fresh(self._clock()):
                continue
            try:
                fetched = await self.get(endpoint, params, kind=DataKind.SEASON_STATS, prewarm=True)
            except (CfbdError, QuotaBlocked) as exc:
                log.info("Prewarm of %s skipped: %s", key, exc)
                continue
            if fetched.source == "live":
                made += 1
                log.info("Prewarmed %s (%s schedule)", key, schedule.name)
            if self.live_window or self._closed:
                break
        return made

    async def reconcile(self, payload: Any = None) -> QuotaStatus:
        """Ask /info what is left on the key and correct the ledger. Never raises.

        A payload can be passed in when the caller already fetched /info, saving a call.
        """
        async with self._reconcile_lock:
            now = self._clock()
            if self._closed:
                return self.quota.status(now)
            self.quota.mark_reconcile_attempt(now)
            if payload is not None:
                return self._apply_info(payload, now)
            try:
                await asyncio.wait_for(self.info(), timeout=RECONCILE_TIMEOUT)  # a good answer applies itself
            except (TimeoutError, CfbdError) as exc:
                log.warning("Quota check with /info failed: %s", exc)
            except RuntimeError as exc:  # the HTTP client was closed underneath us
                log.info("Quota check skipped: %s", exc)
            return self.quota.status(self._clock())

    def _apply_info(self, payload: Any, now: datetime) -> QuotaStatus:
        self.capabilities.update_from_info(payload, now)
        status = self.quota.reconcile(
            remaining=self.capabilities.remaining_calls,
            budget=self.capabilities.monthly_limit,
            tier_level=self.capabilities.tier_level,
            tier_name=self.capabilities.tier_name,
            raw=payload,
            now=now,
        )
        log.info(
            "Quota reconciled with CFBD: %s of %s calls left this month, tier %s, mode %s, cache lifetimes x%d",
            f"{status.remaining:,}" if status.reconciled else "unknown",
            f"{status.budget:,}",
            self.capabilities.tier_name or "unknown",
            status.mode.value,
            self.ttl_scale(status),
        )
        return status

    @staticmethod
    def ttl_scale(status: QuotaStatus) -> int:
        """Stretch cache lifetimes when the monthly budget is small.

        The architecture's TTL table assumes a paid tier. A free key gets 1,000 calls a
        month, so everything stays fresh four times longer on it.
        """
        if status.budget >= 20_000:
            return 1
        if status.budget >= 5_000:
            return 2
        return 4

    async def maybe_reconcile(self) -> QuotaStatus | None:
        """Reconcile when the adaptive schedule says so. Called by the app's periodic task."""
        if self.quota.should_reconcile(self._clock(), live_window=self.live_window):
            return await self.reconcile()
        return None

    def status(self) -> dict[str, Any]:
        """Everything /api/health needs. Makes no upstream call."""
        now = self._clock()
        quota = self.quota.status(now)
        settle_until = self._settle_until()
        stats = dict(self.stats)
        stats["lanes"] = {name: dict(lane) for name, lane in self.stats["lanes"].items()}
        return {
            "checked_at": _iso_z(now),  # the client's own clock, so health ages the lanes' times against it
            "base_url": self.settings.cfbd_base_url,
            "breaker": self.breaker.as_dict(now),
            "live_breaker": self.live_breaker.as_dict(now),
            "settle_until": _iso_z(settle_until) if settle_until is not None else None,
            "settling": settle_until is not None and now < settle_until,
            "stats": stats,
            "quota": quota.as_dict(),
            "ttl_scale": self.ttl_scale(quota),
            "capabilities": self.capabilities.as_dict(),
            "live_window": self.live_window,
        }

    async def aclose(self) -> None:
        self._closed = True
        task = self._reconcile_task
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        await self._http.aclose()

    # --- internals ---------------------------------------------------------------------

    def _from_entry(self, entry: CacheEntry, now: datetime, *, stale: bool, error: str | None = None) -> Fetched:
        return Fetched(
            endpoint=entry.endpoint,
            params=entry.params,
            payload=entry.payload,
            fetched_at=entry.fetched_at,
            source="cache",
            stale=stale,
            age_seconds=round(entry.age_seconds(now), 1),
            error=error,
        )

    async def _request(
        self, endpoint: str, params: dict[str, str], *, live: bool, breaker: Breaker, admission: Admission
    ) -> tuple[Any, str | None] | None:
        """One logical request with retries. Returns (payload, None) or (None, error), or None when
        the breaker lane opened while the call waited for the endpoint, in which case nothing was sent.

        Calls to the same endpoint run one at a time: CFBD refuses concurrent requests on one
        endpoint with HTTP 429 "Too many concurrent requests for this endpoint" (seen 2026-09-23
        with the seven category pulls), and a refused attempt still counts against the ledger.
        Different endpoints still run in parallel. The breaker is asked again once the lock is
        held, so calls queued behind failing ones add no attempts after the lane has opened."""
        lock = self._endpoint_locks.setdefault(endpoint, asyncio.Lock())
        async with lock:
            if not breaker.readmit(admission, self._clock()):
                log.info("Skipped %s: %s opened while the call waited its turn", endpoint, "the live breaker" if live else "the breaker")
                return None
            return await self._request_serialised(endpoint, params, live=live)

    async def _request_serialised(self, endpoint: str, params: dict[str, str], *, live: bool) -> tuple[Any, str | None]:
        error = "no attempt made"
        attempts = LIVE_MAX_ATTEMPTS if live else MAX_ATTEMPTS
        lane = self.stats["lanes"]["live" if live else "general"]
        payload, error, busy = await self._attempts(endpoint, params, live=live, attempts=attempts, lane=lane)
        if error is not None and busy and not live:
            self._busy_until[endpoint] = self._clock() + ENDPOINT_COOLDOWN
        elif error is None:
            self._busy_until.pop(endpoint, None)
        return payload, error

    async def _attempts(self, endpoint: str, params: dict[str, str], *, live: bool, attempts: int, lane: dict[str, Any]) -> tuple[Any, str | None, bool]:
        error = "no attempt made"
        busy = False
        for attempt in range(1, attempts + 1):
            started = perf_counter()
            now = self._clock()
            self.stats["session_calls"] += 1
            lane["calls"] += 1
            try:
                response = await self._http.get(endpoint, params=params, timeout=TIMEOUT if live else BULK_TIMEOUT)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                error = f"{type(exc).__name__}: {exc}".strip(": ")
                busy = isinstance(exc, httpx.TimeoutException)
                await asyncio.to_thread(self.quota.record, endpoint, None, False, live=live, now=now)
                self._note_failure(error, live=live)
                log.warning("CFBD %s attempt %d/%d failed: %s", endpoint, attempt, attempts, error)
                if attempt < attempts:
                    await self._sleep(max(backoff_seconds(attempt), BUSY_WAIT_SECONDS) if busy and not live else backoff_seconds(attempt))
                continue
            busy = False

            status = response.status_code
            ok = 200 <= status < 300
            elapsed_ms = (perf_counter() - started) * 1000
            await asyncio.to_thread(self.quota.record, endpoint, status, ok, live=live, now=now)
            self.capabilities.note_probe(endpoint, status, now)

            if ok:
                try:
                    payload = response.json()
                except ValueError:
                    error = f"HTTP {status} with a body that is not JSON"
                    self._note_failure(error, live=live)
                    log.warning("CFBD %s attempt %d/%d: %s", endpoint, attempt, attempts, error)
                    if attempt < attempts:
                        await self._sleep(backoff_seconds(attempt))
                    continue
                self.stats["last_success_at"] = now.isoformat(timespec="seconds")
                lane["last_success_at"] = self.stats["last_success_at"]
                log.info("CFBD %s %d in %.0f ms (%s)", endpoint, status, elapsed_ms, _describe_size(payload))
                return payload, None, False

            body = _body_excerpt(response)
            if status in RETRY_STATUSES:
                error = f"HTTP {status}" + (f": {body}" if body else "")
                self._note_failure(error, live=live)
                retry_after = _retry_after(response)
                busy = status == 429 and "concurrent" in (body or "").lower()
                log.warning("CFBD %s attempt %d/%d got %s", endpoint, attempt, attempts, error)
                if attempt < attempts:
                    wait = backoff_seconds(attempt, retry_after)
                    await self._sleep(max(wait, BUSY_WAIT_SECONDS) if busy and not live else wait)
                continue

            if not 400 <= status < 500:
                # Any other 5xx (501, 505, a proxy's 520 to 530) or a redirect the client does not follow:
                # CFBD did not answer the request, so it counts against the lane like a timeout. Not retried.
                location = (response.headers.get("location") or "")[:300] if 300 <= status < 400 else ""
                detail = f" to {location}" if location else (f": {body}" if body else "")
                error = f"HTTP {status}{detail}"
                self._note_failure(error, live=live)
                log.warning("CFBD %s attempt %d/%d got %s; not retried", endpoint, attempt, attempts, error)
                return None, error, False

            if status in (401, 403):
                if is_tier_gate(body):
                    log.warning("CFBD refused %s (HTTP %d): %s", endpoint, status, body or "needs a higher tier")
                else:
                    self._note_failure(f"API key rejected (HTTP {status})", live=live)
                    log.error(
                        "CFBD rejected the API key (HTTP %d): %s. Check CFBD_API_KEY in .env.",
                        status,
                        body or "no detail",
                    )
            else:
                log.warning("CFBD refused %s with HTTP %d: %s", endpoint, status, body or "no detail")
            raise CfbdRequestError(status, endpoint, body)
        return None, error, busy

    def _note_failure(self, error: str, *, live: bool = False) -> None:
        at = self._clock().isoformat(timespec="seconds")
        self.stats["session_failures"] += 1
        self.stats["last_failure_at"] = at
        self.stats["last_error"] = error
        lane = self.stats["lanes"]["live" if live else "general"]
        lane["failures"] += 1
        lane["last_failure_at"] = at
        lane["last_error"] = error

    def _maybe_schedule_reconcile(self, now: datetime) -> None:
        if self._closed or not self.quota.needs_reconcile:
            return
        if not self.quota.should_reconcile(now, live_window=self.live_window):
            return
        if self._reconcile_task is not None and not self._reconcile_task.done():
            return
        try:
            self._reconcile_task = asyncio.get_running_loop().create_task(self.reconcile())
        except RuntimeError:
            pass


def _lane_stats() -> dict[str, Any]:
    return {"calls": 0, "failures": 0, "last_success_at": None, "last_failure_at": None, "last_error": None}


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _body_excerpt(response: httpx.Response) -> str:
    try:
        text = response.text
    except Exception:  # noqa: BLE001 - a body we cannot decode is not worth failing over
        return ""
    return " ".join(text.split())[:300]


def _describe_size(payload: Any) -> str:
    if isinstance(payload, list):
        return f"{len(payload)} records"
    if isinstance(payload, dict):
        return f"object with {len(payload)} keys"
    return type(payload).__name__
