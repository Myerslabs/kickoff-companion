"""The quota ledger and guard: thresholds, live-only mode, reconciliation, cadence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.cfbd.quota import (
    RECONCILE_IDLE,
    RECONCILE_LIVE,
    RECONCILE_MIN_GAP,
    QuotaBlocked,
    QuotaGuard,
    QuotaMode,
    month_of,
)
from app.config import load_settings
from app.db import Database
from tests.conftest import TEST_KEY

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def guard(tmp_path):
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, monthly_call_budget=100, quota_hard_stop_pct=90)
    db = Database(tmp_path / "q.db")
    yield QuotaGuard(db, settings)
    db.close()


def burn(guard: QuotaGuard, calls: int, *, live: bool = False, at: datetime = NOW) -> QuotaMode:
    mode = guard.status(at).mode
    for _ in range(calls):
        mode = guard.record("/games", 200, True, live=live, now=at)
    return mode


def test_fresh_ledger_is_normal_and_unreconciled(guard):
    status = guard.status(NOW)
    assert status.mode is QuotaMode.NORMAL
    assert status.used == 0
    assert status.remaining == 100
    assert status.budget == 100
    assert status.reconciled is False
    assert "not reconciled yet" in status.reason
    assert status.month == month_of(NOW) == "2026-09"


def test_modes_change_at_the_documented_thresholds(guard):
    assert burn(guard, 74) is QuotaMode.NORMAL
    assert burn(guard, 1) is QuotaMode.WARNING  # 75 percent
    assert burn(guard, 14) is QuotaMode.WARNING  # 89
    assert burn(guard, 1) is QuotaMode.RESTRICTED  # 90, the hard stop
    assert burn(guard, 6) is QuotaMode.RESTRICTED  # 96
    assert burn(guard, 1) is QuotaMode.EXHAUSTED  # 97


def test_restricted_allows_only_live_calls(guard):
    burn(guard, 90)
    with pytest.raises(QuotaBlocked, match="only live-game calls"):
        guard.check(live=False, now=NOW)
    assert guard.check(live=True, now=NOW).mode is QuotaMode.RESTRICTED


def test_exhausted_blocks_everything_but_one_hourly_reconcile(guard):
    burn(guard, 97)
    with pytest.raises(QuotaBlocked, match="exhausted"):
        guard.check(live=True, now=NOW)
    with pytest.raises(QuotaBlocked):
        guard.check(live=False, now=NOW)
    assert guard.check(live=False, now=NOW, reconciling=True).mode is QuotaMode.EXHAUSTED
    guard.mark_reconcile_attempt(NOW)
    with pytest.raises(QuotaBlocked):
        guard.check(live=False, now=NOW + timedelta(minutes=30), reconciling=True)
    assert guard.check(live=False, now=NOW + timedelta(hours=1), reconciling=True)


def test_threshold_crossing_flags_a_reconcile(guard):
    guard.mark_reconcile_attempt(NOW)
    guard.needs_reconcile = False
    burn(guard, 74)
    assert guard.needs_reconcile is False
    burn(guard, 1)
    assert guard.needs_reconcile is True


def test_reconcile_uses_cfbd_figures_and_counts_down(guard):
    burn(guard, 10)
    status = guard.reconcile(
        remaining=990, budget=1000, tier_level=0, tier_name="Free",
        raw={"usedCalls": 10, "resetAt": "2026-10-01T00:00:00.000Z"}, now=NOW,
    )
    assert status.reconciled is True
    assert status.budget == 1000
    assert status.remaining == 990
    assert status.used == 10
    assert status.tier_name == "Free"
    assert status.reset_at == "2026-10-01T00:00:00.000Z"
    assert status.upstream_used == 10
    assert "CFBD's remaining-calls figure" in status.reason
    burn(guard, 5, at=NOW + timedelta(minutes=1))
    later = guard.status(NOW + timedelta(minutes=2))
    assert later.remaining == 985
    assert later.used == 15
    assert later.calls_since_reconcile == 5
    assert later.ledger_calls_this_month == 15


def test_reconcile_without_a_number_keeps_the_ledger(guard):
    burn(guard, 3)
    status = guard.reconcile(remaining=None, budget=None, tier_level=None, tier_name=None, raw="weird", now=NOW)
    assert status.reconciled is False
    assert status.used == 3
    assert status.budget == 100


def test_reconcile_from_a_previous_month_is_ignored(guard):
    august = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    guard.reconcile(remaining=5, budget=1000, tier_level=0, tier_name="Free", raw={}, now=august)
    status = guard.status(NOW)
    assert status.reconciled is False
    assert status.budget == 100
    assert status.mode is QuotaMode.NORMAL


def test_ledger_counts_only_the_current_month(guard):
    burn(guard, 50, at=datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert guard.status(NOW).used == 0


def test_exhausted_when_cfbd_says_nothing_is_left(guard):
    guard.reconcile(remaining=0, budget=1000, tier_level=0, tier_name="Free", raw={}, now=NOW)
    assert guard.status(NOW).mode is QuotaMode.EXHAUSTED


def test_adaptive_reconcile_cadence(guard):
    assert guard.should_reconcile(NOW, live_window=False) is True  # never checked
    guard.reconcile(remaining=900, budget=1000, tier_level=0, tier_name="Free", raw={}, now=NOW)
    assert guard.should_reconcile(NOW + timedelta(minutes=5), live_window=False) is False
    assert guard.should_reconcile(NOW + RECONCILE_LIVE, live_window=False) is False
    assert guard.should_reconcile(NOW + RECONCILE_IDLE, live_window=False) is True
    assert guard.should_reconcile(NOW + RECONCILE_LIVE, live_window=True) is True
    guard.needs_reconcile = True
    assert guard.should_reconcile(NOW + RECONCILE_MIN_GAP - timedelta(seconds=1), live_window=False) is False
    assert guard.should_reconcile(NOW + RECONCILE_MIN_GAP, live_window=False) is True


def test_failed_attempts_are_counted_too(guard):
    guard.record("/games", None, False, live=False, now=NOW)
    guard.record("/games", 503, False, live=False, now=NOW)
    assert guard.status(NOW).used == 2


def test_calls_by_endpoint_and_live_flag(guard):
    burn(guard, 3)
    guard.record("/live/plays", 200, True, live=True, now=NOW)
    rows = guard.calls_by_endpoint(NOW)
    assert rows[0] == {"endpoint": "/games", "calls": 3, "ok": 3}
    assert rows[1] == {"endpoint": "/live/plays", "calls": 1, "ok": 1}
    with guard.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM quota_calls WHERE live = 1").fetchone()[0] == 1
